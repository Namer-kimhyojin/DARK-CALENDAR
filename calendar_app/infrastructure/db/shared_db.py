"""
shared_db.py — PC 공유 캘린더 DB (C:\\Users\\Public\\DarkCalendar\\shared.db)

모든 Windows 계정이 읽기/쓰기 가능한 위치에 SQLite DB를 유지합니다.
SQLite WAL 모드로 동시 접근을 안전하게 처리합니다.
"""

from datetime import datetime
import logging
import os
import sqlite3
import threading

from calendar_app.shared.calendar_defaults import DEFAULT_CALENDAR_COLOR

logger = logging.getLogger("SharedDB")

SHARED_DIR = r"C:\Users\Public\DarkCalendar"
SHARED_DB_PATH = os.path.join(SHARED_DIR, "shared.db")

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _get_connection() -> sqlite3.Connection | None:
    global _conn
    if _conn is not None:
        return _conn
    try:
        os.makedirs(SHARED_DIR, exist_ok=True)
        conn = sqlite3.connect(SHARED_DB_PATH, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _conn = conn
        _initialize_schema(conn)
        return conn
    except Exception as e:
        logger.error(f"SharedDB connection failed: {e}")
        return None


def _initialize_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS shared_calendar (
            id         TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            color      TEXT NOT NULL DEFAULT '{DEFAULT_CALENDAR_COLOR}',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS shared_task (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            type        TEXT NOT NULL DEFAULT 'schedule',
            calendar_id TEXT,
            deadline    TEXT,
            end_date    TEXT,
            all_day     INTEGER DEFAULT 0,
            description TEXT,
            memo        TEXT,
            location    TEXT,
            assignee    TEXT,
            bg_color    TEXT,
            icon        TEXT,
            status      TEXT DEFAULT 'in_progress',
            is_completed INTEGER DEFAULT 0,
            completed_at TEXT,
            created_by  TEXT,
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at  TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (calendar_id) REFERENCES shared_calendar(id) ON DELETE SET NULL
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_shared_task_calendar ON shared_task (calendar_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_shared_task_deadline ON shared_task (deadline)")
    conn.commit()


# ---------------------------------------------------------------------------
# shared_calendar CRUD
# ---------------------------------------------------------------------------


def list_shared_calendars() -> list[dict]:
    conn = _get_connection()
    if not conn:
        return []
    with _lock:
        cur = conn.cursor()
        cur.execute("SELECT * FROM shared_calendar ORDER BY name")
        return [dict(row) for row in cur.fetchall()]


def upsert_shared_calendar(cal_id: str, name: str, color: str = DEFAULT_CALENDAR_COLOR) -> bool:
    conn = _get_connection()
    if not conn:
        return False
    with _lock:
        try:
            conn.execute(
                """
                INSERT INTO shared_calendar (id, name, color)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, color=excluded.color
            """,
                (cal_id, name, color),
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"upsert_shared_calendar failed: {e}")
            return False


def delete_shared_calendar(cal_id: str) -> bool:
    conn = _get_connection()
    if not conn:
        return False
    with _lock:
        try:
            conn.execute(
                "UPDATE shared_task SET calendar_id = NULL WHERE calendar_id = ?", (cal_id,)
            )
            conn.execute("DELETE FROM shared_calendar WHERE id = ?", (cal_id,))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"delete_shared_calendar failed: {e}")
            return False


# ---------------------------------------------------------------------------
# shared_task CRUD
# ---------------------------------------------------------------------------


def list_shared_tasks(
    calendar_id: str | None = None, date_from: str | None = None, date_to: str | None = None
) -> list[dict]:
    conn = _get_connection()
    if not conn:
        return []
    with _lock:
        cur = conn.cursor()
        where = []
        params = []
        if calendar_id:
            where.append("calendar_id = ?")
            params.append(calendar_id)
        if date_from:
            where.append("(deadline >= ? OR end_date >= ?)")
            params.extend([date_from, date_from])
        if date_to:
            where.append("(deadline <= ? OR deadline IS NULL)")
            params.append(date_to)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        cur.execute(f"SELECT * FROM shared_task {clause} ORDER BY deadline", params)
        return [dict(row) for row in cur.fetchall()]


def insert_shared_task(
    name: str,
    calendar_id: str | None = None,
    deadline: str | None = None,
    end_date: str | None = None,
    all_day: bool = False,
    description: str | None = None,
    memo: str | None = None,
    location: str | None = None,
    assignee: str | None = None,
    bg_color: str | None = None,
    created_by: str | None = None,
) -> int | None:
    conn = _get_connection()
    if not conn:
        return None
    with _lock:
        try:
            cur = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                """
                INSERT INTO shared_task
                    (name, calendar_id, deadline, end_date, all_day,
                     description, memo, location, assignee, bg_color, created_by,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    name,
                    calendar_id,
                    deadline,
                    end_date,
                    1 if all_day else 0,
                    description,
                    memo,
                    location,
                    assignee,
                    bg_color,
                    created_by,
                    now,
                    now,
                ),
            )
            conn.commit()
            return cur.lastrowid
        except Exception as e:
            logger.error(f"insert_shared_task failed: {e}")
            return None


def update_shared_task(task_id: int, **kwargs) -> bool:
    conn = _get_connection()
    if not conn:
        return False
    allowed = {
        "name",
        "calendar_id",
        "deadline",
        "end_date",
        "all_day",
        "description",
        "memo",
        "location",
        "assignee",
        "bg_color",
        "status",
        "is_completed",
        "completed_at",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False
    with _lock:
        try:
            fields["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            values = list(fields.values()) + [task_id]
            conn.execute(f"UPDATE shared_task SET {set_clause} WHERE id = ?", values)
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"update_shared_task failed: {e}")
            return False


def delete_shared_task(task_id: int) -> bool:
    conn = _get_connection()
    if not conn:
        return False
    with _lock:
        try:
            conn.execute("DELETE FROM shared_task WHERE id = ?", (task_id,))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"delete_shared_task failed: {e}")
            return False


def is_available() -> bool:
    """공유 DB 접근 가능 여부를 확인합니다."""
    return _get_connection() is not None
