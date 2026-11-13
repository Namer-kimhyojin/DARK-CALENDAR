# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
import sqlite3

from calendar_app.infrastructure.db.database_unified import db_manager, logger

# 상수 정의

OWNER_TYPE_ROUTINE = "routine"

OWNER_TYPE_SCHEDULE = "schedule"

TASK_STATUS_PENDING = "pending"

TASK_STATUS_DONE = "done"

TASK_TYPE_SPECIAL = "unified_task"

_TASK_DIRECTIVE_COLUMNS_CACHE = {}


def get_connection():
    """싱글톤 데이터베이스 관리자를 통해 연결을 획득합니다."""

    return db_manager.get_connection()


def _task_directive_columns(cur, refresh=False):
    try:
        db_row = cur.connection.execute("PRAGMA database_list").fetchone()

        cache_key = db_row[2] if db_row and len(db_row) > 2 else "__default__"

    except Exception:
        cache_key = "__default__"

    if not refresh and cache_key in _TASK_DIRECTIVE_COLUMNS_CACHE:
        return _TASK_DIRECTIVE_COLUMNS_CACHE[cache_key]

    cur.execute("PRAGMA table_info(task_directive)")

    columns = {row[1] for row in cur.fetchall()}

    _TASK_DIRECTIVE_COLUMNS_CACHE[cache_key] = columns

    return columns


def is_task_on_date(task_recurrence, start_date_str, target_date):
    """

    Helper to check if a task with given recurrence and start date should appear on target_date.

    target_date should be a datetime object.

    """

    import calendar
    from datetime import datetime

    start_dt = datetime.strptime(start_date_str[:10], "%Y-%m-%d")

    if start_dt.date() > target_date.date():
        return False

    if not task_recurrence or task_recurrence == "none":
        return False  # Should be handled by non-recurrent SQL filter

    base = task_recurrence.split(":")[0]

    if base == "daily":
        return True

    elif base == "weekly":
        if ":" in task_recurrence:
            days = task_recurrence.split(":")[1].split(",")

            current_dow = str(target_date.weekday() + 1)  # 1=Mon, 7=Sun

            return current_dow in days

        else:
            return start_dt.weekday() == target_date.weekday()

    elif base == "monthly":
        if ":" in task_recurrence:
            parts = task_recurrence.split(":")

            if parts[1] == "day" and len(parts) > 2:
                return target_date.day == int(parts[2])

            elif parts[1] == "rel" and len(parts) > 3:
                w_idx = int(parts[2])  # 1, 2, 3, 4, -1

                d_idx = int(parts[3])  # 1-7

                if (target_date.weekday() + 1) == d_idx:
                    if w_idx == -1:
                        last_day = calendar.monthrange(target_date.year, target_date.month)[1]

                        return target_date.day + 7 > last_day

                    else:
                        nth = (target_date.day - 1) // 7 + 1

                        return nth == w_idx

        else:
            return start_dt.day == target_date.day

    return False


def get_recent_directives(limit=200):
    conn = get_connection()
    if not conn:
        return []
    rows = []
    try:
        cur = conn.cursor()
        columns = _task_directive_columns(cur)
        receiver_expr = (
            "receiver_name"
            if "receiver_name" in columns
            else ("requester" if "requester" in columns else "NULL")
        )
        memo_expr = "memo" if "memo" in columns else ("details" if "details" in columns else "NULL")
        bg_expr = "bg_color" if "bg_color" in columns else "NULL"
        sql = (
            f"SELECT id, content, status, {receiver_expr}, deadline, {memo_expr}, {bg_expr} "
            "FROM task_directive "
            "ORDER BY COALESCE(deadline, '9999-12-31') ASC, id DESC "
            "LIMIT ?"
        )
        try:
            cur.execute(sql, (int(limit or 200),))
        except sqlite3.OperationalError:
            columns = _task_directive_columns(cur, refresh=True)
            receiver_expr = (
                "receiver_name"
                if "receiver_name" in columns
                else ("requester" if "requester" in columns else "NULL")
            )
            memo_expr = (
                "memo" if "memo" in columns else ("details" if "details" in columns else "NULL")
            )
            bg_expr = "bg_color" if "bg_color" in columns else "NULL"
            sql = (
                f"SELECT id, content, status, {receiver_expr}, deadline, {memo_expr}, {bg_expr} "
                "FROM task_directive "
                "ORDER BY COALESCE(deadline, '9999-12-31') ASC, id DESC "
                "LIMIT ?"
            )
            cur.execute(sql, (int(limit or 200),))
        rows = cur.fetchall()
    except Exception as e:
        logger.exception("Error fetching directives: %s", e)

    return rows


def get_tasks_by_date(date_str):
    """Fetch tasks touching the given date from unified_task.

    Includes tasks whose deadline falls on that date, AND multi-day tasks
    that span over that date — matching what the calendar's own "today"
    views already show. Multi-day span is read from deadline..end_date
    (the columns actually populated by the schedule editor) and, as a
    fallback for callers that use it, period_start..period_end. Without
    this, an in-progress multi-day item (e.g. a schedule running 9/15-10/5)
    would silently disappear from focus-mode task pickers on any day other
    than its exact deadline, even though the main calendar lists it as
    today's item.
    """

    conn = get_connection()

    if not conn:
        return []

    tasks = []

    seen_ids = set()

    try:
        cur = conn.cursor()

        cur.execute(
            """

            SELECT id, name, priority, deadline, type, is_completed

            FROM unified_task

            WHERE date(substr(deadline, 1, 10)) = date(?)

               OR (

                    end_date IS NOT NULL

                    AND date(?) BETWEEN date(substr(deadline, 1, 10))

                                     AND date(substr(end_date, 1, 10))

               )

               OR (

                    period_start IS NOT NULL AND period_end IS NOT NULL

                    AND date(?) BETWEEN date(substr(period_start, 1, 10))

                                     AND date(substr(period_end, 1, 10))

               )

            ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'low' THEN 3 ELSE 2 END, deadline ASC

        """,
            (date_str, date_str, date_str),
        )

        for row in cur.fetchall():
            task_id = row[0]
            if task_id in seen_ids:
                continue
            seen_ids.add(task_id)
            tasks.append(
                {
                    "id": task_id,
                    "name": row[1],
                    "priority": row[2] or "normal",
                    "deadline": row[3],
                    "type": row[4] or "schedule",
                    "is_completed": bool(row[5]),
                }
            )

    except Exception as e:
        logger.exception("Unexpected error in get_tasks_by_date: %s", e)

    return tasks


def get_worklog_entries(limit=100):
    """최근 초집중 모드 기록을 조회합니다.

    ``task_type='directive'`` 기록은 task_directive에서, 나머지는 unified_task에서
    이름을 찾습니다. 두 테이블의 id가 겹치므로 종류를 함께 비교합니다.
    """

    conn = db_manager.get_connection()

    if not conn:
        return []

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                w.id,
                w.task_id,
                COALESCE(
                    CASE WHEN w.task_type = 'directive' THEN d.content ELSE t.name END,
                    'Deleted/Ghost Task'
                ) as task_name,
                w.elapsed_secs,
                w.logged_at,
                w.task_type
            FROM worklog w
            LEFT JOIN unified_task t
                ON w.task_id = t.id AND COALESCE(w.task_type, '') <> 'directive'
            LEFT JOIN task_directive d
                ON w.task_id = d.id AND w.task_type = 'directive'
            ORDER BY w.logged_at DESC
            LIMIT ?
        """,
            (limit,),
        )

        return cur.fetchall()

    except Exception as e:
        logger.exception("Error in get_worklog_entries: %s", e)

        return []


def get_worklog_stats(reference_date=None):
    """Aggregate today's and current-month focus totals in SQLite."""
    conn = db_manager.get_connection()
    if not conn:
        return None
    day = str(reference_date or datetime.now().strftime("%Y-%m-%d"))[:10]
    try:
        reference = datetime.strptime(day, "%Y-%m-%d")
        day_start = reference.strftime("%Y-%m-%d 00:00:00")
        next_day_start = (reference + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
        month_start_dt = reference.replace(day=1)
        next_month_start_dt = (month_start_dt.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_start = month_start_dt.strftime("%Y-%m-%d 00:00:00")
        next_month_start = next_month_start_dt.strftime("%Y-%m-%d 00:00:00")
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                COUNT(CASE WHEN logged_at >= ? AND logged_at < ? THEN 1 END)
                    AS today_sessions,
                COALESCE(SUM(CASE WHEN logged_at >= ? AND logged_at < ?
                                  THEN MAX(COALESCE(elapsed_secs, 0), 0) ELSE 0 END), 0)
                    AS today_secs,
                COUNT(*) AS monthly_sessions,
                COALESCE(SUM(MAX(COALESCE(elapsed_secs, 0), 0)), 0)
                    AS monthly_secs
            FROM worklog
            WHERE logged_at >= ? AND logged_at < ?
            """,
            (
                day_start,
                next_day_start,
                day_start,
                next_day_start,
                month_start,
                next_month_start,
            ),
        )
        row = cur.fetchone()
        if not row:
            return {
                "today_sessions": 0,
                "today_secs": 0,
                "monthly_sessions": 0,
                "monthly_secs": 0,
            }
        return {
            "today_sessions": int(row[0] or 0),
            "today_secs": int(row[1] or 0),
            "monthly_sessions": int(row[2] or 0),
            "monthly_secs": int(row[3] or 0),
        }
    except Exception as e:
        logger.exception("Error in get_worklog_stats: %s", e)
        return None


def get_incomplete_tasks():
    """Return all incomplete tasks (unified_task)."""

    conn = get_connection()

    if not conn:
        return []

    tasks = []

    try:
        cur = conn.cursor()

        # unified_task 조회

        # One query: a second status-based query listed every open task twice.

        cur.execute("""

            SELECT id, name, priority, deadline, type, is_completed

            FROM unified_task

            WHERE is_completed=0

            ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'low' THEN 3 ELSE 2 END, deadline ASC

        """)

        for row in cur.fetchall():
            tasks.append(
                {
                    "id": row[0],
                    "name": row[1],
                    "priority": row[2] or "normal",
                    "deadline": row[3],
                    "type": row[4],
                    "is_completed": False,
                }
            )

    except Exception:
        pass

    return tasks


def get_most_urgent_pending_task(today_str):
    conn = get_connection()

    if not conn:
        return None, "No pending task available."

    task_id, task_name = None, "No pending task available."

    try:
        cur = conn.cursor()

        cur.execute(
            "SELECT id, name FROM unified_task WHERE status IN ('pending', 'in_progress') AND date(substr(deadline, 1, 10)) <= date(?) AND date(substr(ifnull(end_date, deadline), 1, 10)) >= date(?) ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'low' THEN 3 ELSE 2 END, deadline ASC LIMIT 1",
            (today_str, today_str),
        )

        row = cur.fetchone()

        if row:
            task_id, task_name = row

    except Exception:
        pass

    return task_id, task_name


def insert_worklog_entry(task_id, elapsed_secs, task_type="schedule"):
    conn = get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        # Explicitly setting logged_at using local time to ensure 'Today' filters work correctly
        cur.execute(
            """
            INSERT INTO worklog (task_id, task_type, elapsed_secs, logged_at)
            VALUES (?, ?, ?, datetime('now', 'localtime'))
        """,
            (task_id, task_type, elapsed_secs),
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Critical Database error in insert_worklog_entry: {e}")
        conn.rollback()
        return False


def delete_worklog_entry(log_id):
    """Remove a specific worklog entry by ID."""
    conn = get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM worklog WHERE id = ?", (log_id,))
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Error deleting worklog entry {log_id}: {e}")
        conn.rollback()
        return False


def get_calendar_events(target_date_str):
    conn = get_connection()

    if not conn:
        return []

    rows = []

    try:
        cur = conn.cursor()

        # 1. 일반 일정 및 기간 일정

        try:
            cur.execute(
                """SELECT id, name, priority, deadline, end_date, bg_color, icon FROM unified_task

                WHERE status IN ('pending', 'in_progress') AND (recurrence IS NULL OR recurrence='none')

                  AND date(substr(deadline, 1, 10)) <= date(?)

                  AND date(substr(ifnull(end_date, deadline), 1, 10)) >= date(?)

                ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'low' THEN 3 ELSE 2 END, deadline ASC

            """,
                (target_date_str, target_date_str),
            )

        except sqlite3.OperationalError:
            cur.execute(
                """SELECT id, name, priority, deadline, end_date, NULL, NULL FROM unified_task

                WHERE status='pending' AND recurrence IS NULL OR recurrence='none'

                  AND date(substr(deadline, 1, 10)) <= date(?)

                  AND date(substr(ifnull(end_date, deadline), 1, 10)) >= date(?)

                ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'low' THEN 3 ELSE 2 END, deadline ASC

            """,
                (target_date_str, target_date_str),
            )

        rows = cur.fetchall()

        # 2. Process recurring schedules (Daily, Weekly, Monthly)

        # Keep SQL simple and perform weekday/day matching in Python

        cur.execute(
            """SELECT id, name, priority, deadline, end_date, bg_color, icon, recurrence

                       FROM unified_task

                       WHERE status IN ('pending', 'in_progress') AND recurrence IS NOT NULL AND recurrence != 'none'

                         AND date(substr(deadline, 1, 10)) <= date(?)

                    """,
            (target_date_str,),
        )

        recur_rows = cur.fetchall()

        from datetime import datetime

        target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")

        for r in recur_rows:
            rid, rname, rprio, rdead, rend, rcol, ricon, rtype = r

            if is_task_on_date(rtype, rdead, target_dt):
                # Mark recurring entries with a repeat indicator.

                ricon = (ricon if ricon else "") + "\U0001f501"

                rows.append((rid, rname, rprio, rdead, rend, rcol, ricon))

    except Exception:
        pass

    return rows
