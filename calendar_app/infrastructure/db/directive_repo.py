# -*- coding: utf-8 -*-
"""Directive-focused adapter for legacy directive table access."""

import contextlib
import json
import logging

from calendar_app.infrastructure.db import db_repository as _legacy

logger = logging.getLogger(__name__)

# SET clause for a status write; bind the new status once more. completed_at is stamped when
# a directive becomes completed, kept while it stays completed and cleared otherwise. SET
# expressions read the old row, so "status" here is the status before this write.
COMPLETED_AT_ASSIGNMENT = (
    "completed_at = CASE WHEN COALESCE(?, '') != 'completed' THEN NULL "
    "WHEN status = 'completed' THEN completed_at "
    "ELSE datetime('now', 'localtime') END"
)


def _directive_columns(cur):
    cur.execute("PRAGMA table_info(task_directive)")
    return {row[1] for row in cur.fetchall()}


def _ensure_directive_schema(cur):
    columns = _directive_columns(cur)
    required = [
        ("receiver_name", "TEXT"),
        ("memo", "TEXT"),
        ("priority", "TEXT DEFAULT 'normal'"),
        ("completed_at", "TEXT"),
    ]
    for col_name, col_type in required:
        if col_name not in columns:
            cur.execute(f"ALTER TABLE task_directive ADD COLUMN {col_name} {col_type}")
            columns.add(col_name)
    if "requester" in columns and "receiver_name" in columns:
        cur.execute(
            "UPDATE task_directive "
            "SET receiver_name = COALESCE(NULLIF(receiver_name, ''), requester) "
            "WHERE COALESCE(receiver_name, '') = '' AND COALESCE(requester, '') != ''"
        )
    if "details" in columns and "memo" in columns:
        cur.execute(
            "UPDATE task_directive "
            "SET memo = COALESCE(NULLIF(memo, ''), details) "
            "WHERE COALESCE(memo, '') = '' AND COALESCE(details, '') != ''"
        )
    return columns


def _ensure_directive_trash_archive_table(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS directive_trash_archive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_directive_id INTEGER,
            content TEXT,
            receiver_name TEXT,
            priority TEXT,
            status TEXT,
            deadline TEXT,
            trashed_reason TEXT,
            trashed_at TEXT DEFAULT (datetime('now', 'localtime')),
            snapshot_json TEXT
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_directive_trash_time ON directive_trash_archive (trashed_at, id)"
    )


def update_directive_bg_color(directive_id, color_hex):
    conn = _legacy.get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        if color_hex is None:
            cur.execute("UPDATE task_directive SET bg_color=NULL WHERE id=?", (directive_id,))
        else:
            cur.execute(
                "UPDATE task_directive SET bg_color=? WHERE id=?", (color_hex, directive_id)
            )
        conn.commit()
        return True
    except Exception:
        logger.exception("update_directive_bg_color failed id=%s", directive_id)
        return False


def update_directive_status(directive_id, new_status):
    conn = _legacy.get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        _ensure_directive_schema(cur)
        cur.execute(
            f"UPDATE task_directive SET status=?, {COMPLETED_AT_ASSIGNMENT} WHERE id=?",
            (new_status, new_status, directive_id),
        )
        conn.commit()
        # A directive deleted elsewhere matches no row; report it so callers keep no stale state.
        return cur.rowcount > 0
    except Exception:
        logger.exception("update_directive_status failed id=%s", directive_id)
        return False


def get_directive_completed_at(directive_id):
    """Stored completion time of a directive (None when unset). Raises if it cannot be read."""
    conn = _legacy.get_connection()
    if not conn:
        raise RuntimeError("no database connection")
    row = conn.execute(
        "SELECT completed_at FROM task_directive WHERE id=?", (directive_id,)
    ).fetchone()
    return row[0] if row else None


def restore_directive_completed_at(directive_id, completed_at):
    """Undo of an untick: put back the completion time the untick cleared."""
    conn = _legacy.get_connection()
    if not conn:
        return False
    try:
        cur = conn.execute(
            "UPDATE task_directive SET completed_at=? WHERE id=? AND status='completed'",
            (completed_at, directive_id),
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception:
        logger.exception("restore_directive_completed_at failed id=%s", directive_id)
        # A failed write (database locked) must not leave a transaction open on this shared
        # connection.
        with contextlib.suppress(Exception):
            conn.rollback()
        return False


def update_directive_priority(directive_id, priority):
    conn = _legacy.get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        _ensure_directive_schema(cur)
        cur.execute("UPDATE task_directive SET priority=? WHERE id=?", (priority, directive_id))
        conn.commit()
        return cur.rowcount > 0
    except Exception:
        logger.exception("update_directive_priority failed id=%s", directive_id)
        return False


def get_recent_directives(limit=200):
    return _legacy.get_recent_directives(limit=limit)


def directive_ids_completed_on(date_str):
    """Ids of the directives completed on date_str ('yyyy-MM-dd'), read from completed_at."""
    conn = _legacy.get_connection()
    if not conn:
        return set()
    try:
        cur = conn.cursor()
        # A range on completed_at (not date(completed_at)) uses the (status, completed_at) index.
        cur.execute(
            "SELECT id FROM task_directive WHERE status = 'completed' "
            "AND completed_at >= date(?) AND completed_at < date(?, '+1 day')",
            (date_str, date_str),
        )
        return {row[0] for row in cur.fetchall()}
    except Exception:
        logger.exception("directive_ids_completed_on failed date=%s", date_str)
        return set()


def get_directives_by_date(date_str: str, limit: int | None = None):
    ensure_priority_column()
    conn = _legacy.get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        _ensure_directive_schema(cur)
        sql = (
            "SELECT id, content, status, receiver_name, deadline, memo, bg_color, "
            "COALESCE(priority, 'normal') AS priority "
            "FROM task_directive "
            "WHERE date(deadline) = date(?) "
            "ORDER BY COALESCE(deadline, '9999-12-31') ASC, id DESC"
        )
        params = [date_str]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        cur.execute(sql, tuple(params))
        return [dict(row) for row in cur.fetchall()]
    except Exception:
        logger.exception("get_directives_by_date failed date=%s", date_str)
        return []


def ensure_priority_column():
    conn = _legacy.get_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        _ensure_directive_schema(cur)
        conn.commit()
    except Exception:
        pass


def get_all_directives_for_management():
    ensure_priority_column()
    conn = _legacy.get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        _ensure_directive_schema(cur)
        cur.execute(
            "SELECT id, content, receiver_name, COALESCE(priority, 'normal'), deadline, status "
            "FROM task_directive ORDER BY deadline ASC, id DESC"
        )
        return cur.fetchall()
    except Exception:
        return []


def update_directive_field(directive_id: int, field: str, value):
    if field not in {"content", "receiver_name", "deadline"}:
        return False
    conn = _legacy.get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        _ensure_directive_schema(cur)
        cur.execute(f"UPDATE task_directive SET {field}=? WHERE id=?", (value, directive_id))
        conn.commit()
        return True
    except Exception:
        logger.exception("update_directive_field failed id=%s field=%s", directive_id, field)
        return False


def bulk_update_directive_status(ids, new_status: str):
    if not ids:
        return 0
    conn = _legacy.get_connection()
    if not conn:
        return 0
    try:
        cur = conn.cursor()
        _ensure_directive_schema(cur)
        placeholders = ",".join("?" for _ in ids)
        cur.execute(
            f"UPDATE task_directive SET status=?, {COMPLETED_AT_ASSIGNMENT} "
            f"WHERE id IN ({placeholders})",
            [new_status, new_status] + list(ids),
        )
        conn.commit()
        return cur.rowcount
    except Exception:
        logger.exception("bulk_update_directive_status failed ids=%s", ids)
        return 0


def bulk_update_directive_priority(ids, new_priority: str):
    if not ids:
        return 0
    ensure_priority_column()
    conn = _legacy.get_connection()
    if not conn:
        return 0
    try:
        cur = conn.cursor()
        _ensure_directive_schema(cur)
        placeholders = ",".join("?" for _ in ids)
        cur.execute(
            f"UPDATE task_directive SET priority=? WHERE id IN ({placeholders})",
            [new_priority] + list(ids),
        )
        conn.commit()
        return cur.rowcount
    except Exception:
        logger.exception("bulk_update_directive_priority failed ids=%s", ids)
        return 0


def delete_directives(ids):
    if not ids:
        return 0
    conn = _legacy.get_connection()
    if not conn:
        return 0
    try:
        cur = conn.cursor()
        placeholders = ",".join("?" for _ in ids)
        cur.execute(f"DELETE FROM task_directive WHERE id IN ({placeholders})", list(ids))
        deleted = cur.rowcount
        conn.commit()
        return deleted
    except Exception:
        logger.exception("delete_directives failed ids=%s", ids)
        with contextlib.suppress(Exception):
            conn.rollback()
        return 0


def move_directive_to_trash(directive_id, reason="manual_trash"):
    conn = _legacy.get_connection()
    if not conn or not directive_id:
        return False
    try:
        cur = conn.cursor()
        _ensure_directive_schema(cur)
        _ensure_directive_trash_archive_table(cur)

        cur.execute("SELECT * FROM task_directive WHERE id=?", (directive_id,))
        row = cur.fetchone()
        if not row:
            return False
        directive = dict(row)

        cur.execute(
            """
            INSERT INTO directive_trash_archive (
                original_directive_id, content, receiver_name, priority, status,
                deadline, trashed_reason, snapshot_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                directive_id,
                directive.get("content") or "",
                directive.get("receiver_name") or directive.get("requester") or "",
                directive.get("priority") or "normal",
                directive.get("status") or "pending",
                directive.get("deadline"),
                str(reason or "manual_trash")[:100],
                json.dumps(directive, ensure_ascii=True, default=str),
            ),
        )
        cur.execute("DELETE FROM task_directive WHERE id=?", (directive_id,))
        conn.commit()
        return True
    except Exception:
        logger.exception("move_directive_to_trash failed id=%s", directive_id)
        with contextlib.suppress(Exception):
            conn.rollback()
        return False


def list_directive_trash():
    conn = _legacy.get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        _ensure_directive_trash_archive_table(cur)
        cur.execute("SELECT * FROM directive_trash_archive ORDER BY trashed_at DESC, id DESC")
        rows = [dict(row) for row in cur.fetchall()]
        out = []
        for row in rows:
            snapshot = {}
            try:
                snapshot = json.loads(row.get("snapshot_json") or "{}")
            except Exception:
                snapshot = {}
            if not isinstance(snapshot, dict):
                snapshot = {}
            row["content"] = row.get("content") or snapshot.get("content") or ""
            row["receiver_name"] = (
                row.get("receiver_name")
                or snapshot.get("receiver_name")
                or snapshot.get("requester")
                or ""
            )
            row["priority"] = row.get("priority") or snapshot.get("priority") or "normal"
            row["status"] = row.get("status") or snapshot.get("status") or "pending"
            row["deadline"] = row.get("deadline") or snapshot.get("deadline") or ""
            out.append(row)
        return out
    except Exception:
        logger.exception("list_directive_trash failed")
        return []


def restore_directive_from_trash(archive_id):
    conn = _legacy.get_connection()
    if not conn or not archive_id:
        return None
    try:
        cur = conn.cursor()
        _ensure_directive_schema(cur)
        _ensure_directive_trash_archive_table(cur)
        cur.execute("SELECT * FROM directive_trash_archive WHERE id=?", (archive_id,))
        row = cur.fetchone()
        if not row:
            return None
        archive = dict(row)

        snapshot = {}
        try:
            snapshot = json.loads(archive.get("snapshot_json") or "{}")
        except Exception:
            snapshot = {}
        if not isinstance(snapshot, dict):
            snapshot = {}

        table_columns = _directive_columns(cur)
        insert_data = {}
        for key, value in snapshot.items():
            if key in table_columns and key != "id":
                insert_data[key] = value

        if "content" in table_columns:
            insert_data["content"] = insert_data.get("content") or archive.get("content") or ""
        if "receiver_name" in table_columns:
            insert_data["receiver_name"] = (
                insert_data.get("receiver_name") or archive.get("receiver_name") or ""
            )
        if "priority" in table_columns:
            insert_data["priority"] = (
                insert_data.get("priority") or archive.get("priority") or "normal"
            )
        if "deadline" in table_columns:
            insert_data["deadline"] = insert_data.get("deadline") or archive.get("deadline")
        if "status" in table_columns:
            insert_data["status"] = insert_data.get("status") or archive.get("status") or "pending"

        if "requester" in table_columns and not insert_data.get("requester"):
            insert_data["requester"] = insert_data.get("receiver_name") or ""
        if "receiver_name" in table_columns and not insert_data.get("receiver_name"):
            insert_data["receiver_name"] = insert_data.get("requester") or ""

        columns = list(insert_data.keys())
        if not columns:
            return None

        placeholders = ", ".join(["?"] * len(columns))
        cols_sql = ", ".join(columns)
        cur.execute(
            f"INSERT INTO task_directive ({cols_sql}) VALUES ({placeholders})",
            [insert_data[c] for c in columns],
        )
        new_id = cur.lastrowid
        cur.execute("DELETE FROM directive_trash_archive WHERE id=?", (archive_id,))
        conn.commit()
        return int(new_id) if new_id else None
    except Exception:
        logger.exception("restore_directive_from_trash failed archive_id=%s", archive_id)
        with contextlib.suppress(Exception):
            conn.rollback()
        return None


def purge_directive_trash(archive_id):
    conn = _legacy.get_connection()
    if not conn or not archive_id:
        return False
    try:
        cur = conn.cursor()
        _ensure_directive_trash_archive_table(cur)
        cur.execute("DELETE FROM directive_trash_archive WHERE id=?", (archive_id,))
        deleted = cur.rowcount
        conn.commit()
        return deleted > 0
    except Exception:
        logger.exception("purge_directive_trash failed archive_id=%s", archive_id)
        with contextlib.suppress(Exception):
            conn.rollback()
        return False
