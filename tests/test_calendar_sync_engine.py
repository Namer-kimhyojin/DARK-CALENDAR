# -*- coding: utf-8 -*-
"""Independent in-memory regressions for provider-neutral sync safety."""

from copy import deepcopy
import sqlite3

import pytest

from calendar_app.application.calendar_sync_contract import CalendarSyncError, RemoteCalendarError
from calendar_app.infrastructure.calendar_sync.engine import CalendarSyncEngine
from calendar_app.infrastructure.calendar_sync.repository import CalendarSyncRepository
from calendar_app.infrastructure.outlook_sync.conversion import from_graph, to_graph


@pytest.fixture
def repo():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE calendar(id TEXT PRIMARY KEY,type TEXT,name TEXT,color TEXT,is_active INTEGER,access_role TEXT);
        CREATE TABLE unified_task(id INTEGER PRIMARY KEY,name TEXT,deadline TEXT,end_date TEXT,all_day INTEGER,description TEXT,location TEXT,calendar_id TEXT,type TEXT,gcal_dirty INTEGER,gcal_sync_mode TEXT,recurrence TEXT,updated_at TEXT);
    """)
    repository = CalendarSyncRepository(conn)
    repository.register("account", {"id": "calendar", "name": "Outlook", "canEdit": True})
    yield repository
    conn.close()


def task(name="Meeting"):
    return {
        "name": name,
        "deadline": "2026-10-05T10:00:00",
        "end_date": "2026-10-05T11:00:00",
        "all_day": 0,
        "description": "notes",
        "location": "office",
    }


class Provider:
    """Uses plain normalized records, deliberately independent of Graph JSON."""

    def __init__(self):
        self.remote = {}
        self.writes = []
        self.before_write = lambda: None
        self.fail_read = False

    def events(self, calendar, start, end):
        if self.fail_read:
            raise CalendarSyncError("network_unavailable")
        return deepcopy(list(self.remote.values()))

    def event(self, event_id):
        if event_id not in self.remote:
            raise RemoteCalendarError(404)
        return deepcopy(self.remote[event_id])

    def create(self, calendar, payload, transaction_id):
        self.before_write()
        old = next(
            (r for r in self.remote.values() if r.get("transaction_id") == transaction_id), None
        )
        if old:
            return deepcopy(old)
        event = {
            "id": "event-" + transaction_id,
            "etag": "1",
            "task": deepcopy(payload),
            "transaction_id": transaction_id,
        }
        self.remote[event["id"]] = event
        self.writes.append("create")
        return deepcopy(event)

    def update(self, event_id, payload, etag):
        self.before_write()
        if self.remote[event_id]["etag"] != etag:
            raise RemoteCalendarError(412)
        event = {**self.remote[event_id], "task": deepcopy(payload), "etag": str(int(etag) + 1)}
        self.remote[event_id] = event
        self.writes.append("update")
        return deepcopy(event)

    def delete(self, event_id, etag):
        if self.remote[event_id]["etag"] != etag:
            raise RemoteCalendarError(412)
        del self.remote[event_id]
        self.writes.append("delete")
        return {}

    @staticmethod
    def to_task(event, local_zone):
        return deepcopy(event["task"])

    @staticmethod
    def from_task(local, local_zone):
        return {k: local.get(k) for k in task()}

    @classmethod
    def edit_payload(cls, local, remote, local_zone):
        return cls.from_task(local, local_zone)


def setup(repo):
    provider = Provider()
    key = repo.calendars("account")[0]["local_id"]
    engine = CalendarSyncEngine(provider, repo, "account")
    return provider, key, engine


def imported(repo):
    provider, key, engine = setup(repo)
    provider.remote["remote"] = {"id": "remote", "etag": "1", "task": task()}
    engine.run()
    return provider, key, engine, repo.tasks(key)[0]["id"]


def test_import_is_idempotent_and_never_pushes_mirrors(repo):
    provider, key, engine, tid = imported(repo)
    engine.run()
    assert len(repo.tasks(key)) == 1
    assert provider.writes == []
    assert repo.task(tid)["gcal_dirty"] == 0


def test_create_and_update_use_own_calendar(repo):
    provider, key, engine = setup(repo)
    with repo.conn:
        tid = repo.import_task(key, task())
        repo.import_task("local::other", task("Unrelated"))
    engine.run()
    with repo.conn:
        repo.conn.execute("UPDATE unified_task SET name='Changed' WHERE id=?", (tid,))
    engine.run()
    assert provider.writes == ["create", "update"]
    assert list(provider.remote.values())[0]["task"]["name"] == "Changed"


def test_remote_update_applies_without_local_changes(repo):
    provider, key, engine, tid = imported(repo)
    provider.remote["remote"].update(etag="2", task=task("Remote"))
    engine.run()
    assert repo.task(tid)["name"] == "Remote"
    assert not provider.writes


def test_move_during_remote_conversion_preserves_current_calendar_and_content(repo):
    provider, key, engine, tid = imported(repo)
    provider.remote["remote"].update(etag="2", task=task("Remote"))
    original = provider.to_task

    def move_then_convert(event, zone):
        with repo.conn:
            repo.conn.execute(
                "UPDATE unified_task SET calendar_id='local::other' WHERE id=?", (tid,)
            )
        return original(event, zone)

    provider.to_task = move_then_convert
    engine.run()
    assert repo.task(tid)["calendar_id"] == "local::other"
    assert repo.task(tid)["name"] == "Meeting"
    assert repo.issues("account")[0]["kind"] == "calendar_move_not_supported"
    assert repo.task_link(tid)["etag"] == "1"


def test_stale_conflict_cannot_be_resolved_after_move(repo):
    provider, key, engine, tid = imported(repo)
    with repo.conn:
        repo.conn.execute("UPDATE unified_task SET name='Local' WHERE id=?", (tid,))
    provider.remote["remote"].update(etag="2", task=task("Remote"))
    original = provider.to_task

    def move_then_convert(event, zone):
        with repo.conn:
            repo.conn.execute(
                "UPDATE unified_task SET calendar_id='local::other' WHERE id=?", (tid,)
            )
        return original(event, zone)

    provider.to_task = move_then_convert
    engine.run()
    assert not repo.resolve(tid, "remote", "UTC", provider)
    assert repo.task(tid)["name"] == "Local"


def test_move_before_push_does_not_update_former_calendar(repo):
    provider, key, engine, tid = imported(repo)
    with repo.conn:
        repo.conn.execute("UPDATE unified_task SET name='Local' WHERE id=?", (tid,))
    original = provider.to_task

    def move_then_convert(event, zone):
        with repo.conn:
            repo.conn.execute(
                "UPDATE unified_task SET calendar_id='local::other' WHERE id=?", (tid,)
            )
        return original(event, zone)

    provider.to_task = move_then_convert
    engine.run()
    assert provider.writes == []


def test_restoring_move_clears_resolved_issue(repo):
    provider, key, engine, tid = imported(repo)
    with repo.conn:
        repo.conn.execute("UPDATE unified_task SET calendar_id='local::other' WHERE id=?", (tid,))
        repo.conn.execute("UPDATE unified_task SET calendar_id=? WHERE id=?", (key, tid))
    assert repo.issues("account")
    engine.run()
    assert not repo.issues("account")


def test_cancel_after_remote_read_cannot_delete(repo):
    provider, key, engine, tid = imported(repo)
    with repo.conn:
        repo.conn.execute("DELETE FROM unified_task WHERE id=?", (tid,))
    cancelled = [False]
    original = provider.event

    def read_and_cancel(event_id):
        event = original(event_id)
        cancelled[0] = True
        return event

    provider.event = read_and_cancel
    engine.cancelled = lambda: cancelled[0]
    with pytest.raises(CalendarSyncError, match="cancelled"):
        engine.run()
    assert provider.writes == []
    assert repo.conn.execute("SELECT COUNT(*) FROM calendar_sync_delete_queue").fetchone()[0] == 1


def test_deselection_during_conversion_prevents_remote_apply(repo):
    provider, key, engine, tid = imported(repo)
    provider.remote["remote"].update(etag="2", task=task("Remote"))
    original = provider.to_task

    def deselect(event, zone):
        with repo.conn:
            repo.conn.execute("UPDATE calendar SET is_active=0 WHERE id=?", (key,))
        return original(event, zone)

    provider.to_task = deselect
    engine.run()
    assert repo.task(tid)["name"] == "Meeting"
    assert provider.writes == []


def test_conflict_preserves_both_and_requires_explicit_resolution(repo):
    provider, key, engine, tid = imported(repo)
    with repo.conn:
        repo.conn.execute("UPDATE unified_task SET name='Local' WHERE id=?", (tid,))
    provider.remote["remote"].update(etag="2", task=task("Remote"))
    engine.run()
    assert repo.task(tid)["name"] == "Local"
    assert repo.issues("account")[0]["kind"] == "conflict"
    assert provider.writes == []
    assert repo.resolve(tid, "local", "Asia/Seoul", provider)
    engine.run()
    assert provider.remote["remote"]["task"]["name"] == "Local"


def test_resolution_rejects_newer_local_edit(repo):
    provider, key, engine, tid = imported(repo)
    with repo.conn:
        repo.conn.execute("UPDATE unified_task SET name='Local' WHERE id=?", (tid,))
    provider.remote["remote"].update(etag="2", task=task("Remote"))
    engine.run()
    with repo.conn:
        repo.conn.execute("UPDATE unified_task SET name='Newer' WHERE id=?", (tid,))
    assert not repo.resolve(tid, "remote", "Asia/Seoul", provider)
    assert repo.task(tid)["name"] == "Newer"


def test_delete_is_durable_and_remote_revision_protected(repo):
    provider, key, engine, tid = imported(repo)
    with repo.conn:
        repo.conn.execute("DELETE FROM unified_task WHERE id=?", (tid,))
    provider.remote["remote"]["etag"] = "2"
    engine.run()
    assert not repo.tasks(key)
    assert "remote" in provider.remote
    row = repo.conn.execute("SELECT * FROM calendar_sync_delete_queue").fetchone()
    assert row["error"] == "delete_conflict"


def test_local_delete_reaches_remote_without_resurrection(repo):
    provider, key, engine, tid = imported(repo)
    with repo.conn:
        repo.conn.execute("DELETE FROM unified_task WHERE id=?", (tid,))
    engine.run()
    assert not repo.tasks(key)
    assert provider.remote == {}
    assert provider.writes == ["delete"]


def test_remote_deleted_task_is_preserved_without_recreation(repo):
    provider, key, engine, tid = imported(repo)
    del provider.remote["remote"]
    engine.run()
    engine.run()
    assert repo.task(tid)
    assert repo.issues("account")[0]["kind"] == "remote_deleted"
    assert provider.writes == []


def test_partial_read_failure_does_not_push(repo):
    provider, key, engine = setup(repo)
    with repo.conn:
        repo.import_task(key, task())
    provider.fail_read = True
    with pytest.raises(CalendarSyncError):
        engine.run()
    assert provider.writes == []


def test_edit_during_http_write_stays_dirty(repo):
    provider, key, engine, tid = imported(repo)
    with repo.conn:
        repo.conn.execute("UPDATE unified_task SET name='First' WHERE id=?", (tid,))

    def edit():
        with repo.conn:
            repo.conn.execute("UPDATE unified_task SET name='Second' WHERE id=?", (tid,))

    provider.before_write = edit
    engine.run()
    assert provider.remote["remote"]["task"]["name"] == "First"
    assert repo.task(tid)["name"] == "Second"
    provider.before_write = lambda: None
    engine.run()
    assert provider.remote["remote"]["task"]["name"] == "Second"


def test_delete_during_create_is_queued_without_orphan(repo):
    provider, key, engine = setup(repo)
    with repo.conn:
        tid = repo.import_task(key, task())

    def remove():
        with repo.conn:
            repo.conn.execute("DELETE FROM unified_task WHERE id=?", (tid,))

    provider.before_write = remove
    engine.run()
    assert not repo.task(tid)
    assert not repo.task_link(tid)
    assert not provider.remote


def test_lost_create_response_reconciles_transaction_without_duplicate(repo):
    provider, key, engine = setup(repo)
    with repo.conn:
        repo.import_task(key, task())
    create = provider.create

    def lost(*args):
        create(*args)
        raise CalendarSyncError("network_unavailable")

    provider.create = lost
    engine.run()
    provider.create = create
    engine.run()
    assert len(repo.tasks(key)) == 1
    assert provider.writes == ["create"]


def test_read_only_calendar_cannot_push(repo):
    provider, key, engine = setup(repo)
    repo.register("account", {"id": "calendar", "name": "Read only", "canEdit": False})
    with repo.conn:
        repo.import_task(key, task())
    engine.run()
    assert provider.writes == []
    assert repo.issues("account")[0]["kind"] == "calendar_read_only"


def test_calendar_move_is_flagged_without_duplicate(repo):
    provider, key, engine, tid = imported(repo)
    second = repo.register("account", {"id": "second", "name": "Other", "canEdit": True})
    with repo.conn:
        repo.conn.execute("UPDATE unified_task SET calendar_id=? WHERE id=?", (second, tid))
    engine.run()
    assert provider.writes == []
    assert repo.issues("account")[0]["kind"] == "calendar_move_not_supported"


def test_all_day_inclusive_local_end_round_trips():
    local = {**task(), "all_day": 1, "deadline": "2026-10-05", "end_date": "2026-10-06"}
    payload = to_graph(local)
    assert payload["end"]["dateTime"] == "2026-10-07T00:00:00"
    remote = {
        **payload,
        "start": {"dateTime": "2026-10-04T15:00:00", "timeZone": "UTC"},
        "end": {"dateTime": "2026-10-06T15:00:00", "timeZone": "UTC"},
    }
    restored = from_graph(remote)
    assert restored["deadline"] == local["deadline"]
    assert restored["end_date"] == local["end_date"]


def test_long_plain_text_description_and_time_are_preserved():
    local = task()
    local["description"] = "Long note " * 100
    assert from_graph(to_graph(local)) == local


def test_provider_neutral_engine_accepts_future_caldav_adapter(repo):
    caldav = CalendarSyncRepository(repo.conn, provider="caldav")
    key = caldav.register(
        "caldav::account",
        {"id": "https://example.invalid/calendar/", "name": "CalDAV fixture", "can_edit": True},
    )
    with caldav.conn:
        caldav.import_task(key, task())
    provider = Provider()
    CalendarSyncEngine(provider, caldav, "caldav::account").run()
    assert key.startswith("caldav::")
    assert provider.writes == ["create"]


def test_permission_failure_stops_remaining_writes(repo):
    provider, key, engine = setup(repo)
    with repo.conn:
        repo.import_task(key, task("One"))
        repo.import_task(key, task("Two"))
    attempts = []

    def denied(*args):
        attempts.append(True)
        raise RemoteCalendarError(403)

    provider.create = denied
    with pytest.raises(RemoteCalendarError):
        engine.run()
    assert len(attempts) == 1


def test_identical_remote_ids_are_isolated_between_accounts(repo):
    first = repo.calendars("account")[0]["local_id"]
    other = repo.register("other-account", {"id": "calendar", "name": "Other", "can_edit": True})
    with repo.conn:
        for key in (first, other):
            repo.conn.execute(
                "INSERT INTO calendar_sync_delete_queue(event_id,calendar_id,etag) VALUES('same',?,'1')",
                (key,),
            )
    provider = Provider()
    provider.remote["same"] = {"id": "same", "etag": "1", "task": task()}
    engine = CalendarSyncEngine(provider, repo, "account")
    assert engine._deletions(first) == 1
    rows = list(repo.conn.execute("SELECT calendar_id FROM calendar_sync_delete_queue"))
    assert [r[0] for r in rows] == [other]


def test_other_account_delete_queue_does_not_suppress_import(repo):
    other = repo.register("other-account", {"id": "calendar", "name": "Other", "can_edit": True})
    with repo.conn:
        repo.conn.execute(
            "INSERT INTO calendar_sync_delete_queue(event_id,calendar_id,etag) VALUES('same',?,'1')",
            (other,),
        )
    provider = Provider()
    provider.remote["same"] = {"id": "same", "etag": "1", "task": task()}
    result = CalendarSyncEngine(provider, repo, "account").run()
    assert result["imported"] == 1


@pytest.mark.parametrize("status", [401, 403, 429, 503])
def test_delete_auth_or_server_failure_stops_queue(repo, status):
    key = repo.calendars("account")[0]["local_id"]
    with repo.conn:
        for event_id in ("one", "two"):
            repo.conn.execute(
                "INSERT INTO calendar_sync_delete_queue(event_id,calendar_id,etag) VALUES(?,?,'1')",
                (event_id, key),
            )
    provider = Provider()
    attempts = []

    def denied(event_id):
        attempts.append(event_id)
        raise RemoteCalendarError(status)

    provider.event = denied
    with pytest.raises(RemoteCalendarError):
        CalendarSyncEngine(provider, repo, "account")._deletions(key)
    assert len(attempts) == 1
    assert repo.conn.execute("SELECT COUNT(*) FROM calendar_sync_delete_queue").fetchone()[0] == 2


def test_legacy_delete_queue_migration_preserves_pending_work(repo):
    from calendar_app.infrastructure.calendar_sync.repository import initialize

    repo.conn.execute("DROP TRIGGER calendar_sync_capture_delete")
    repo.conn.execute("DROP TABLE calendar_sync_delete_queue")
    repo.conn.execute(
        "CREATE TABLE calendar_sync_delete_queue(event_id TEXT PRIMARY KEY,calendar_id TEXT NOT NULL,etag TEXT,attempts INTEGER NOT NULL DEFAULT 0,error TEXT)"
    )
    repo.conn.execute(
        "INSERT INTO calendar_sync_delete_queue VALUES('old','calendar','tag',3,'delete_conflict')"
    )
    repo.conn.commit()
    initialize(repo.conn)
    initialize(repo.conn)
    row = repo.conn.execute(
        "SELECT event_id,calendar_id,etag,attempts,error FROM calendar_sync_delete_queue"
    ).fetchone()
    assert tuple(row) == ("old", "calendar", "tag", 3, "delete_conflict")
    repo.conn.execute(
        "INSERT INTO calendar_sync_delete_queue(event_id,calendar_id,etag,attempts,error) VALUES('old','another','tag',0,NULL)"
    )
    assert repo.conn.execute("SELECT COUNT(*) FROM calendar_sync_delete_queue").fetchone()[0] == 2


def test_metadata_only_remote_change_does_not_create_content_conflict(repo):
    provider, key, engine = setup(repo)
    provider.remote["fixture"] = {"id": "fixture", "etag": "1", "task": task()}
    engine.run()
    tid = repo.tasks(key)[0]["id"]
    provider.remote["fixture"]["etag"] = "2"
    summary = engine.run()
    assert summary["updated"] == 0
    assert repo.task_link(tid)["etag"] == "2"
    with repo.conn:
        repo.conn.execute("UPDATE unified_task SET name='Local edit' WHERE id=?", (tid,))
    provider.remote["fixture"]["etag"] = "3"
    engine.run()
    assert repo.issues("account") == []
    assert provider.remote["fixture"]["task"]["name"] == "Local edit"


def test_server_default_end_time_does_not_cause_repeated_writes(repo):
    provider, key, engine = setup(repo)
    with repo.conn:
        tid = repo.import_task(key, {**task(), "end_date": ""})
    original = provider.create

    def canonical_create(calendar, payload, transaction):
        event = original(calendar, payload, transaction)
        event["task"]["end_date"] = "2026-10-05T11:00:00"
        provider.remote[event["id"]] = event
        return event

    provider.create = canonical_create
    engine.run()
    assert repo.task(tid)["end_date"] == "2026-10-05T11:00:00"
    engine.run()
    assert provider.writes == ["create"]


def test_local_calendar_label_is_preserved_while_remote_label_tracks_changes(repo):
    key = repo.calendars("account")[0]["local_id"]
    repo.register("account", {"id": "calendar", "name": "Remote renamed", "can_edit": True})
    assert (
        repo.conn.execute("SELECT name FROM calendar WHERE id=?", (key,)).fetchone()[0]
        == "Remote renamed"
    )
    with repo.conn:
        repo.conn.execute("UPDATE calendar SET name='My label' WHERE id=?", (key,))
    repo.register("account", {"id": "calendar", "name": "Another remote label", "can_edit": False})
    assert repo.conn.execute("SELECT name,access_role FROM calendar WHERE id=?", (key,)).fetchone()[
        :
    ] == ("My label", "reader")


def test_calendar_selection_failure_rolls_back_the_entire_selection(repo):
    key = repo.calendars("account")[0]["local_id"]
    with pytest.raises(KeyError):
        repo.save_selection(
            "account", [{"id": "new", "name": "New", "can_edit": True}, {"id": "broken"}]
        )
    assert repo.conn.execute("SELECT is_active FROM calendar WHERE id=?", (key,)).fetchone()[0] == 1
    assert len(repo.calendars("account")) == 1


def test_same_account_overlapping_run_is_rejected(repo):
    provider, key, engine = setup(repo)

    def snapshot(*args):
        with pytest.raises(CalendarSyncError, match="sync_already_running"):
            CalendarSyncEngine(Provider(), repo, "account").run()
        return []

    provider.events = snapshot
    engine.run()


def test_create_404_does_not_mark_never_created_event_as_remote_deleted(repo):
    provider, key, engine = setup(repo)
    with repo.conn:
        tid = repo.import_task(key, task())
    provider.create = lambda *args: (_ for _ in ()).throw(RemoteCalendarError(404))
    with pytest.raises(CalendarSyncError, match="calendar_access_lost"):
        engine.run()
    assert not repo.task_link(tid)["remote_deleted"]
    assert repo.task(tid) is not None
