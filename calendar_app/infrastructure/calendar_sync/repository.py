# -*- coding: utf-8 -*-
"""Provider-neutral metadata and durable deletion/conflict records."""

from contextlib import contextmanager
import hashlib
import json
import sqlite3
import threading

FIELDS = ("name", "deadline", "end_date", "all_day", "description", "location")
_SCHEMA_GUARD = threading.RLock()


def fingerprint(task):
    values = {key: task.get(key) or (0 if key == "all_day" else "") for key in FIELDS}
    values["all_day"] = int(bool(values["all_day"]))
    return hashlib.sha256(
        json.dumps(values, sort_keys=True, ensure_ascii=False).encode("utf-8", errors="strict")
    ).hexdigest()


def calendar_key(account, remote, provider="outlook"):
    digest = hashlib.sha256(f"{account}:{remote}".encode("utf-8", errors="strict")).hexdigest()[:24]
    return f"{provider}::{digest}"


def initialize(conn):
    with _SCHEMA_GUARD:
        _initialize(conn)


def _initialize(conn):
    # Older ledgers keyed deletions by remote ID alone. IDs can overlap across
    # providers and accounts; migrate only our metadata, preserving pending work.
    columns = list(conn.execute("PRAGMA table_info(calendar_sync_delete_queue)"))
    if columns and sum(bool(row[5]) for row in columns) == 1:
        with conn:
            conn.execute("DROP TRIGGER IF EXISTS calendar_sync_capture_delete")
            conn.execute(
                "ALTER TABLE calendar_sync_delete_queue RENAME TO calendar_sync_delete_queue_legacy"
            )
            conn.execute(
                "CREATE TABLE calendar_sync_delete_queue (event_id TEXT NOT NULL, calendar_id TEXT NOT NULL, etag TEXT, attempts INTEGER NOT NULL DEFAULT 0, error TEXT, PRIMARY KEY(calendar_id,event_id))"
            )
            conn.execute(
                "INSERT INTO calendar_sync_delete_queue(event_id,calendar_id,etag,attempts,error) SELECT event_id,calendar_id,etag,attempts,error FROM calendar_sync_delete_queue_legacy"
            )
            conn.execute("DROP TABLE calendar_sync_delete_queue_legacy")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS calendar_sync_calendar (
            local_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, remote_id TEXT NOT NULL,
            can_edit INTEGER NOT NULL DEFAULT 0, remote_name TEXT
        );
        CREATE TABLE IF NOT EXISTS calendar_sync_event (
            task_id INTEGER PRIMARY KEY, calendar_id TEXT NOT NULL, event_id TEXT,
            etag TEXT, baseline TEXT NOT NULL, transaction_id TEXT NOT NULL,
            remote_deleted INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS calendar_sync_delete_queue (
            event_id TEXT NOT NULL, calendar_id TEXT NOT NULL, etag TEXT,
            attempts INTEGER NOT NULL DEFAULT 0, error TEXT,
            PRIMARY KEY(calendar_id,event_id)
        );
        CREATE TABLE IF NOT EXISTS calendar_sync_issue (
            task_id INTEGER PRIMARY KEY, kind TEXT NOT NULL, local_json TEXT,
            remote_json TEXT, created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TRIGGER IF NOT EXISTS calendar_sync_capture_delete BEFORE DELETE ON unified_task
        BEGIN
            INSERT OR IGNORE INTO calendar_sync_delete_queue(event_id,calendar_id,etag)
            SELECT event_id,calendar_id,etag FROM calendar_sync_event
            WHERE task_id=OLD.id AND event_id IS NOT NULL AND remote_deleted=0;
            DELETE FROM calendar_sync_issue WHERE task_id=OLD.id;
            DELETE FROM calendar_sync_event WHERE task_id=OLD.id;
        END;
        CREATE TRIGGER IF NOT EXISTS calendar_sync_capture_move AFTER UPDATE OF calendar_id ON unified_task
        WHEN COALESCE(OLD.calendar_id,'') != COALESCE(NEW.calendar_id,'')
        BEGIN
            INSERT OR REPLACE INTO calendar_sync_issue(task_id,kind)
            SELECT task_id,'calendar_move_not_supported' FROM calendar_sync_event WHERE task_id=NEW.id;
        END;
    """)
    if "remote_name" not in {
        r[1] for r in conn.execute("PRAGMA table_info(calendar_sync_calendar)")
    }:
        with conn:
            conn.execute("ALTER TABLE calendar_sync_calendar ADD COLUMN remote_name TEXT")
    for table in ("calendar_sync_event", "calendar_sync_delete_queue"):
        columns = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for column in ("remote_uid", "recurrence_id"):
            if column not in columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
    # Capture the stable identity before the local row and its link are removed.
    conn.executescript("""
        DROP TRIGGER IF EXISTS calendar_sync_capture_delete;
        CREATE TRIGGER calendar_sync_capture_delete BEFORE DELETE ON unified_task
        BEGIN
            INSERT OR IGNORE INTO calendar_sync_delete_queue(event_id,calendar_id,etag,remote_uid,recurrence_id)
            SELECT event_id,calendar_id,etag,remote_uid,recurrence_id FROM calendar_sync_event
            WHERE task_id=OLD.id AND event_id IS NOT NULL AND remote_deleted=0;
            DELETE FROM calendar_sync_issue WHERE task_id=OLD.id;
            DELETE FROM calendar_sync_event WHERE task_id=OLD.id;
        END;
    """)


class CalendarSyncRepository:
    def __init__(self, conn, provider="outlook"):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.provider = provider
        initialize(conn)

    @contextmanager
    def atomic(self):
        """Lock before the local snapshot read, not only before its eventual UPDATE."""
        with self.conn:
            if not self.conn.in_transaction:
                self.conn.execute("BEGIN IMMEDIATE")
            yield

    def calendars(self, account):
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT o.*,c.is_active,c.name AS display_name FROM calendar_sync_calendar o JOIN calendar c ON c.id=o.local_id WHERE account_id=?",
                (account,),
            )
        ]

    def register(self, account, remote):
        with self.conn:
            return self._register(account, remote)

    def _register(self, account, remote):
        key = calendar_key(account, remote["id"], self.provider)
        editable = int(bool(remote.get("can_edit", remote.get("canEdit", False))))
        previous = self.conn.execute(
            "SELECT c.name,o.remote_name FROM calendar c JOIN calendar_sync_calendar o ON o.local_id=c.id WHERE c.id=?",
            (key,),
        ).fetchone()
        display_name = remote["name"]
        if previous and previous["name"] != previous["remote_name"]:
            display_name = previous["name"]
        self.conn.execute(
            "INSERT INTO calendar(id,type,name,color,is_active,access_role) VALUES (?,?,?,'#3478C5',1,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,access_role=excluded.access_role",
            (key, self.provider, display_name, "writer" if editable else "reader"),
        )
        self.conn.execute(
            "INSERT INTO calendar_sync_calendar(local_id,account_id,remote_id,can_edit,remote_name) VALUES (?,?,?,?,?) ON CONFLICT(local_id) DO UPDATE SET can_edit=excluded.can_edit,remote_name=excluded.remote_name",
            (key, account, remote["id"], editable, remote["name"]),
        )
        return key

    def save_selection(self, account, calendars):
        """Apply a complete user selection atomically, without touching other accounts."""
        with self.conn:
            self.conn.execute(
                "UPDATE calendar SET is_active=0 WHERE id IN (SELECT local_id FROM calendar_sync_calendar WHERE account_id=?)",
                (account,),
            )
            for remote in calendars:
                key = self._register(account, remote)
                self.conn.execute("UPDATE calendar SET is_active=1 WHERE id=?", (key,))

    def deactivate(self, account):
        with self.conn:
            self.conn.execute(
                "UPDATE calendar SET is_active=0,access_role='reader' WHERE id IN (SELECT local_id FROM calendar_sync_calendar WHERE account_id=?)",
                (account,),
            )
            self.conn.execute(
                "UPDATE calendar_sync_calendar SET can_edit=0 WHERE account_id=?", (account,)
            )

    def tasks(self, key):
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT * FROM unified_task WHERE calendar_id=? AND type='schedule'", (key,)
            )
        ]

    def task(self, task_id):
        row = self.conn.execute("SELECT * FROM unified_task WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    def links(self, key):
        return {
            r["task_id"]: dict(r)
            for r in self.conn.execute(
                "SELECT * FROM calendar_sync_event WHERE calendar_id=?", (key,)
            )
        }

    def task_link(self, task_id):
        row = self.conn.execute(
            "SELECT * FROM calendar_sync_event WHERE task_id=?", (task_id,)
        ).fetchone()
        return dict(row) if row else None

    def link(self, task_id, key, event_id, etag, baseline, transaction_id, remote=None):
        remote = remote or {}
        self.conn.execute(
            "INSERT INTO calendar_sync_event(task_id,calendar_id,event_id,etag,baseline,transaction_id,remote_uid,recurrence_id) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET event_id=excluded.event_id,etag=excluded.etag,baseline=excluded.baseline,remote_uid=COALESCE(excluded.remote_uid,calendar_sync_event.remote_uid),recurrence_id=COALESCE(excluded.recurrence_id,calendar_sync_event.recurrence_id)",
            (
                task_id,
                key,
                event_id,
                etag,
                baseline,
                transaction_id,
                remote.get("uid"),
                remote.get("recurrence_id"),
            ),
        )

    def import_task(self, key, task):
        columns = [*FIELDS, "calendar_id", "type", "gcal_dirty", "gcal_sync_mode"]
        values = [task[k] for k in FIELDS] + [key, "schedule", 0, "unknown"]
        cursor = self.conn.execute(
            f"INSERT INTO unified_task({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
            values,
        )
        return cursor.lastrowid

    def apply_remote(self, task_id, task):
        self.conn.execute(
            f"UPDATE unified_task SET {','.join(k + '=?' for k in FIELDS)}, updated_at=datetime('now','localtime') WHERE id=?",
            [task[k] for k in FIELDS] + [task_id],
        )

    def issue(self, task_id, kind, local=None, remote=None):
        self.conn.execute(
            "INSERT INTO calendar_sync_issue(task_id,kind,local_json,remote_json) VALUES(?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET kind=excluded.kind,local_json=excluded.local_json,remote_json=excluded.remote_json,created_at=datetime('now')",
            (
                task_id,
                kind,
                json.dumps(local, ensure_ascii=False),
                json.dumps(remote, ensure_ascii=False),
            ),
        )

    def clear_issue(self, task_id):
        self.conn.execute("DELETE FROM calendar_sync_issue WHERE task_id=?", (task_id,))

    def issues(self, account):
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT i.* FROM calendar_sync_issue i JOIN calendar_sync_event e ON e.task_id=i.task_id JOIN calendar_sync_calendar c ON c.local_id=e.calendar_id WHERE c.account_id=?",
                (account,),
            )
        ]

    def resolve(self, task_id, choice, local_zone, provider):
        with self.atomic():
            row = self.conn.execute(
                "SELECT * FROM calendar_sync_issue WHERE task_id=? AND kind='conflict'", (task_id,)
            ).fetchone()
            if not row:
                return False
            try:
                remote = json.loads(row["remote_json"])
                snapshot = json.loads(row["local_json"])
            except (ValueError, TypeError):
                return False
            local = self.task(task_id)
            link = self.task_link(task_id)
            if (
                not local
                or not link
                or not isinstance(snapshot, dict)
                or not isinstance(remote, dict)
                or local["calendar_id"] != link["calendar_id"]
                or snapshot.get("calendar_id") != link["calendar_id"]
                or remote.get("id") != link["event_id"]
                or fingerprint(local) != fingerprint(snapshot)
            ):
                return False
            task = provider.to_task(remote, local_zone)
            if choice == "remote":
                self.apply_remote(task_id, task)
            elif choice != "local":
                return False
            self.conn.execute(
                "UPDATE calendar_sync_event SET etag=?,baseline=? WHERE task_id=?",
                (remote.get("etag"), fingerprint(task), task_id),
            )
            self.clear_issue(task_id)
        return True
