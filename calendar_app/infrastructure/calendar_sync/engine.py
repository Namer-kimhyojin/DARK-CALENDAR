# -*- coding: utf-8 -*-
"""Pull before push; preserve conflicting local changes and remote deletions."""

from datetime import UTC, datetime, timedelta
import threading
import uuid

from calendar_app.application.calendar_sync_contract import (
    CalendarProvider,
    CalendarSyncError,
    RemoteCalendarError,
)

from .repository import fingerprint

_LEASE_GUARD = threading.Lock()
_LEASES = {}


class CalendarSyncEngine:
    def __init__(
        self,
        client: CalendarProvider,
        repository,
        account,
        local_zone="Asia/Seoul",
        cancelled=lambda: False,
    ):
        self.client, self.repo, self.account = client, repository, account
        self.zone, self.cancelled = local_zone, cancelled

    def _check(self):
        if self.cancelled():
            raise CalendarSyncError("cancelled")

    def run(self):
        database = self.repo.conn.execute("PRAGMA database_list").fetchone()[2]
        key = (database or id(self.repo.conn), self.account)
        with _LEASE_GUARD:
            lease = _LEASES.setdefault(key, threading.Lock())
        if not lease.acquire(blocking=False):
            raise CalendarSyncError("sync_already_running")
        try:
            return self._run()
        finally:
            lease.release()

    def _run(self):
        counts = {"imported": 0, "updated": 0, "created": 0, "deleted": 0, "issues": 0}
        now = datetime.now(UTC)
        start, end = [(now + timedelta(days=n)).isoformat() for n in (-120, 400)]
        for calendar in self.repo.calendars(self.account):
            self._check()
            if not calendar["is_active"]:
                continue
            key = calendar["local_id"]
            # Fetch every page before applying any changes for this calendar.
            events = self.client.events(calendar["remote_id"], start, end)
            remote = {e["id"]: e for e in events}
            if len(remote) != len(events):
                raise CalendarSyncError("duplicate_remote_event")
            identities = [(e["uid"], e.get("recurrence_id", "")) for e in events if e.get("uid")]
            if len(set(identities)) != len(identities):
                raise CalendarSyncError("duplicate_remote_event")
            links = self.repo.links(key)
            event_links = {v["event_id"]: v for v in links.values() if v["event_id"]}
            pending_creates = {v["transaction_id"]: v for v in links.values() if not v["event_id"]}
            queued = {
                r[0]
                for r in self.repo.conn.execute(
                    "SELECT event_id FROM calendar_sync_delete_queue WHERE calendar_id=?", (key,)
                )
            }
            for event in events:
                self._check()
                if event["id"] in queued or event.get("cancelled"):
                    continue
                link = event_links.get(event["id"])
                if link:
                    continue
                pending = pending_creates.get(event.get("transaction_id"))
                if pending and self.repo.task(pending["task_id"]):
                    with self.repo.atomic():
                        self._check()
                        current = self.repo.task(pending["task_id"])
                        if not current or current["calendar_id"] != key or not self._selected(key):
                            continue
                        self.repo.link(
                            pending["task_id"],
                            key,
                            event["id"],
                            event.get("etag"),
                            fingerprint(self.client.to_task(event, self.zone)),
                            pending["transaction_id"],
                            remote=event,
                        )
                    continue
                if self._recover_resource_identity(key, event, remote):
                    continue
                task = self.client.to_task(event, self.zone)
                with self.repo.atomic():
                    self._check()
                    if not self._selected(key):
                        continue
                    if self.repo.conn.execute(
                        "SELECT 1 FROM calendar_sync_delete_queue WHERE event_id=? AND calendar_id=?",
                        (event["id"], key),
                    ).fetchone():
                        continue
                    tid = self.repo.import_task(key, task)
                    self.repo.link(
                        tid,
                        key,
                        event["id"],
                        event.get("etag"),
                        fingerprint(task),
                        str(uuid.uuid4()),
                        remote=event,
                    )
                counts["imported"] += 1
            # Re-read local rows after network I/O; never overwrite a concurrent edit.
            for task in self.repo.tasks(key):
                self._check()
                tid = task["id"]
                link = self.repo.task_link(tid)
                if link and link["calendar_id"] != key:
                    with self.repo.atomic():
                        self.repo.issue(tid, "calendar_move_not_supported", task)
                    continue
                if not link:
                    transaction = str(uuid.uuid4())
                    with self.repo.atomic():
                        current = self.repo.task(tid)
                        if (
                            not current
                            or current["calendar_id"] != key
                            or not self._selected(key)
                            or fingerprint(current) != fingerprint(task)
                        ):
                            continue
                        self.repo.link(tid, key, None, None, fingerprint(task), transaction)
                    link = self.repo.links(key)[tid]
                if link["remote_deleted"]:
                    continue
                try:
                    if not link["event_id"]:
                        if not calendar["can_edit"]:
                            raise CalendarSyncError("calendar_read_only")
                        payload = self.client.from_task(task, self.zone)
                        with self.repo.atomic():
                            if not self._current_snapshot(tid, key, task, link):
                                continue
                        event = self.client.create(
                            calendar["remote_id"], payload, link["transaction_id"]
                        )
                        self._save_write(tid, key, event, task, link)
                        counts["created"] += 1
                        continue
                    event = remote.get(link["event_id"])
                    if event is None:
                        event = self.client.event(link["event_id"])
                    if not self._same_identity(link, event):
                        raise CalendarSyncError("remote_identity_changed")
                    if event.get("cancelled"):
                        raise RemoteCalendarError(404)
                    local_changed = fingerprint(task) != link["baseline"]
                    fresh = self.client.to_task(event, self.zone)
                    remote_changed = fingerprint(fresh) != link["baseline"]
                    if local_changed and remote_changed:
                        with self.repo.atomic():
                            if not self._current_snapshot(tid, key, task, link):
                                continue
                            self.repo.issue(tid, "conflict", task, event)
                        continue
                    if remote_changed:
                        with self.repo.atomic():
                            if not self._current_snapshot(tid, key, task, link):
                                continue
                            self.repo.apply_remote(tid, fresh)
                            self.repo.link(
                                tid,
                                key,
                                event["id"],
                                event.get("etag"),
                                fingerprint(fresh),
                                link["transaction_id"],
                                remote=event,
                            )
                            self.repo.clear_issue(tid)
                        counts["updated"] += 1
                    elif local_changed:
                        if not calendar["can_edit"]:
                            raise CalendarSyncError("calendar_read_only")
                        payload = self.client.edit_payload(task, event, self.zone)
                        with self.repo.atomic():
                            if not self._current_snapshot(tid, key, task, link):
                                continue
                        event = self.client.update(
                            event["id"],
                            payload,
                            event.get("etag"),
                        )
                        self._save_write(tid, key, event, task, link)
                        counts["updated"] += 1
                    else:
                        # Reminder/metadata changes are not a content conflict and
                        # should not be reported as a visible task modification.
                        with self.repo.atomic():
                            if not self._current_snapshot(tid, key, task, link):
                                continue
                            self.repo.link(
                                tid,
                                key,
                                event["id"],
                                event.get("etag"),
                                fingerprint(fresh),
                                link["transaction_id"],
                                remote=event,
                            )
                            self.repo.clear_issue(tid)
                except CalendarSyncError as exc:
                    if str(exc) == "cancelled":
                        raise
                    if isinstance(exc, RemoteCalendarError) and (
                        exc.status in {401, 403, 429} or exc.status >= 500
                    ):
                        raise
                    with self.repo.atomic():
                        if isinstance(exc, RemoteCalendarError) and exc.status == 404:
                            if not link["event_id"]:
                                raise CalendarSyncError("calendar_access_lost") from exc
                            self.repo.conn.execute(
                                "UPDATE calendar_sync_event SET remote_deleted=1 WHERE task_id=?",
                                (tid,),
                            )
                            self.repo.issue(tid, "remote_deleted", task)
                        else:
                            self.repo.issue(tid, str(exc), task)
            if calendar["can_edit"]:
                counts["deleted"] += self._deletions(key)
        counts["issues"] = (
            len(self.repo.issues(self.account))
            + self.repo.conn.execute(
                "SELECT COUNT(*) FROM calendar_sync_delete_queue q JOIN calendar_sync_calendar c ON q.calendar_id=c.local_id WHERE c.account_id=? AND q.error IS NOT NULL",
                (self.account,),
            ).fetchone()[0]
        )
        return counts

    def _recover_resource_identity(self, key, event, remote):
        """CalDAV URLs can change; require stable UID/recurrence and confirmed old 404."""
        if self.repo.provider != "caldav" or not event.get("uid"):
            return False
        params = (key, event["uid"], event.get("recurrence_id", ""))
        links = list(
            self.repo.conn.execute(
                "SELECT * FROM calendar_sync_event WHERE calendar_id=? AND remote_uid=? AND COALESCE(recurrence_id,'')=?",
                params,
            )
        )
        queue = list(
            self.repo.conn.execute(
                "SELECT * FROM calendar_sync_delete_queue WHERE calendar_id=? AND remote_uid=? AND COALESCE(recurrence_id,'')=?",
                params,
            )
        )
        candidates = links + queue
        if not candidates:
            return False
        if len(candidates) != 1:
            raise CalendarSyncError("duplicate_remote_event")
        previous = dict(candidates[0])
        old = previous["event_id"]
        if not old or old in remote:
            raise CalendarSyncError("duplicate_remote_event")
        try:
            self.client.event(old)
        except RemoteCalendarError as exc:
            if exc.status != 404:
                raise
        else:
            raise CalendarSyncError("duplicate_remote_event")
        with self.repo.atomic():
            self._check()
            if not self._selected(key):
                return True
            if links:
                current = self.repo.task(previous["task_id"])
                if not current:
                    # Deletion can race with the old URL's 404 verification.
                    self.repo.conn.execute(
                        "UPDATE calendar_sync_delete_queue SET event_id=? WHERE calendar_id=? AND event_id=? AND remote_uid=? AND COALESCE(recurrence_id,'')=?",
                        (
                            event["id"],
                            key,
                            old,
                            previous["remote_uid"],
                            previous["recurrence_id"] or "",
                        ),
                    )
                    return True
                if self.repo.task_link(previous["task_id"]) != previous:
                    return True
                if current["calendar_id"] != key:
                    self.repo.issue(previous["task_id"], "calendar_move_not_supported", current)
                    return True
                self.repo.conn.execute(
                    "UPDATE calendar_sync_event SET event_id=?,etag=?,remote_deleted=0 WHERE task_id=?",
                    (event["id"], event.get("etag"), previous["task_id"]),
                )
                self.repo.conn.execute(
                    "DELETE FROM calendar_sync_issue WHERE task_id=? AND kind='remote_deleted'",
                    (previous["task_id"],),
                )
            else:
                current = self.repo.conn.execute(
                    "SELECT * FROM calendar_sync_delete_queue WHERE calendar_id=? AND event_id=?",
                    (key, old),
                ).fetchone()
                if current and dict(current) == previous:
                    # Preserve the old ETag: relocation must never bypass deletion conflicts.
                    self.repo.conn.execute(
                        "UPDATE calendar_sync_delete_queue SET event_id=? WHERE calendar_id=? AND event_id=?",
                        (event["id"], key, old),
                    )
        return True

    def _selected(self, key):
        return (
            self.repo.conn.execute(
                "SELECT 1 FROM calendar c JOIN calendar_sync_calendar s ON s.local_id=c.id WHERE c.id=? AND c.is_active=1 AND s.account_id=?",
                (key, self.account),
            ).fetchone()
            is not None
        )

    def _current_snapshot(self, tid, key, task, link):
        """Read under the writer lock; content alone cannot detect a calendar move."""
        self._check()
        current, current_link = self.repo.task(tid), self.repo.task_link(tid)
        return (
            current
            and current["calendar_id"] == key
            and current_link == link
            and self._selected(key)
            and fingerprint(current) == fingerprint(task)
        )

    def _save_write(self, tid, key, event, task, link):
        with self.repo.atomic():
            current = self.repo.task(tid)
            if not current:
                # A user deleted this row while the HTTP write was in flight.
                self.repo.conn.execute(
                    "INSERT INTO calendar_sync_delete_queue(event_id,calendar_id,etag,remote_uid,recurrence_id) VALUES(?,?,?,?,?) ON CONFLICT(calendar_id,event_id) DO UPDATE SET etag=excluded.etag,remote_uid=COALESCE(excluded.remote_uid,remote_uid),recurrence_id=COALESCE(excluded.recurrence_id,recurrence_id)",
                    (
                        event["id"],
                        key,
                        event.get("etag"),
                        event.get("uid"),
                        event.get("recurrence_id"),
                    ),
                )
                self.repo.conn.execute("DELETE FROM calendar_sync_event WHERE task_id=?", (tid,))
                return
            canonical = self.client.to_task(event, self.zone)
            if current["calendar_id"] == key and fingerprint(current) == fingerprint(task):
                # Store server defaults (for example a missing end time) only if
                # the user has not edited again while the HTTP request was running.
                self.repo.apply_remote(tid, canonical)
            self.repo.link(
                tid,
                key,
                event["id"],
                event.get("etag"),
                fingerprint(canonical),
                link["transaction_id"],
                remote=event,
            )
            if current["calendar_id"] != key:
                self.repo.issue(tid, "calendar_move_not_supported", current)
            else:
                self.repo.clear_issue(tid)

    def _same_identity(self, link, event):
        if self.repo.provider != "caldav" or not link["remote_uid"]:
            return True
        return (link["remote_uid"], link["recurrence_id"] or "") == (
            event.get("uid"),
            event.get("recurrence_id", ""),
        )

    def _deletions(self, key):
        count = 0
        queue = list(
            self.repo.conn.execute(
                "SELECT * FROM calendar_sync_delete_queue WHERE calendar_id=? AND attempts<5 AND COALESCE(error,'') NOT IN ('event_read_only','delete_conflict')",
                (key,),
            )
        )
        for row in queue:
            self._check()
            try:
                event = self.client.event(row["event_id"])
                self._check()
                if not self._selected(key):
                    break
                if not self._same_identity(row, event) or event.get("etag") != row["etag"]:
                    raise CalendarSyncError("delete_conflict")
                self.client.delete(row["event_id"], row["etag"])
            except RemoteCalendarError as exc:
                if exc.status != 404:
                    self._delete_failure(row, str(exc))
                    if exc.status in {401, 403, 429} or exc.status >= 500:
                        raise
                    continue
            except CalendarSyncError as exc:
                if str(exc) == "cancelled":
                    raise
                self._delete_failure(row, str(exc))
                continue
            with self.repo.atomic():
                self.repo.conn.execute(
                    "DELETE FROM calendar_sync_delete_queue WHERE event_id=? AND calendar_id=?",
                    (row["event_id"], key),
                )
            count += 1
        return count

    def _delete_failure(self, row, code):
        with self.repo.atomic():
            self.repo.conn.execute(
                "UPDATE calendar_sync_delete_queue SET attempts=attempts+1,error=? WHERE event_id=? AND calendar_id=?",
                (code, row["event_id"], row["calendar_id"]),
            )
