from datetime import datetime
import sqlite3

from calendar_app.infrastructure.db.database_unified import db_manager, logger

# 상수 정의

OWNER_TYPE_ROUTINE = "routine"

OWNER_TYPE_SCHEDULE = "schedule"

TASK_STATUS_PENDING = "pending"

TASK_STATUS_DONE = "done"

TASK_TYPE_SPECIAL = "unified_task"

_CHECKLIST_ROUTINE_ROLLOVER_HOOK = None
_TASK_DIRECTIVE_COLUMNS_CACHE = {}


def register_checklist_routine_rollover_hook(handler):
    """Register callback invoked when process checklist completes a routine."""

    global _CHECKLIST_ROUTINE_ROLLOVER_HOOK

    _CHECKLIST_ROUTINE_ROLLOVER_HOOK = handler


def _run_checklist_routine_rollover(owner_id):
    hook = _CHECKLIST_ROUTINE_ROLLOVER_HOOK

    if hook is None:
        return

    try:
        hook(owner_id)

    except Exception:
        logger.exception("Failed checklist routine rollover hook owner_id=%s", owner_id)


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


def get_today_eod_summary(today_str):
    conn = get_connection()

    if not conn:
        return 0, 0, 0, "No Database"

    fm = 0

    dir_done = 0

    rout_done = 0

    error_msg = ""

    try:
        cur = conn.cursor()

        cur.execute(
            "SELECT ifnull(SUM(elapsed_secs), 0) FROM worklog WHERE date(logged_at) = date('now', 'localtime')"
        )

        fm = cur.fetchone()[0] // 60

        cur.execute(
            "SELECT COUNT(*) FROM task_directive WHERE status = 'done' AND date(deadline) = date(?)",
            (today_str,),
        )

        dir_done = cur.fetchone()[0]

        # Use task_checklist_link for routine completion count

        cur.execute(
            "SELECT COUNT(DISTINCT owner_id) FROM task_checklist_link WHERE owner_type='routine' AND is_completed = 1"
        )

        rout_done = cur.fetchone()[0]

    except Exception as e:
        error_msg = str(e)

    return fm, dir_done, rout_done, error_msg


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


def get_today_schedules(today_str):
    conn = get_connection()

    if not conn:
        return []

    rows = []

    try:
        cur = conn.cursor()

        cur.execute(
            """

            SELECT id, name, deadline, priority

            FROM unified_task

            WHERE status IN ('pending', 'in_progress') AND type='schedule' AND (recurrence IS NULL OR recurrence='none')

              AND date(substr(deadline, 1, 10)) <= date(?)

              AND date(substr(ifnull(end_date, deadline), 1, 10)) >= date(?)

            ORDER BY deadline ASC

        """,
            (today_str, today_str),
        )

        rows = list(cur.fetchall())

        # 2. Process recurring schedules

        cur.execute("""SELECT id, name, deadline, priority, recurrence

                       FROM unified_task

                       WHERE status IN ('pending', 'in_progress') AND type='schedule' AND recurrence IS NOT NULL AND recurrence != 'none'

                    """)

        recur_candidates = cur.fetchall()

        from datetime import datetime

        target_dt = datetime.strptime(today_str, "%Y-%m-%d")

        for cand in recur_candidates:
            cid, cname, cdead, cprio, crecur = cand

            if is_task_on_date(crecur, cdead, target_dt):
                rows.append((cid, cname, cdead, cprio))

    except Exception:
        pass

    return rows


def get_routine_templates():
    conn = get_connection()

    if not conn:
        return []

    try:
        cur = conn.cursor()

        cur.execute(
            "SELECT id, name, cycle_type, description FROM routine_template WHERE is_active=1 ORDER BY id DESC"
        )

        return cur.fetchall()

    except sqlite3.Error as e:
        logger.error(f"Database error in get_routine_templates: {e}")

        return []

    except Exception as e:
        logger.exception(f"Unexpected error in get_routine_templates: {e}")

        return []


def get_template_steps(template_id):
    conn = get_connection()

    if not conn:
        return []

    try:
        cur = conn.cursor()

        cur.execute(
            "SELECT id, step_name, step_order FROM template_step WHERE template_id=? ORDER BY step_order ASC",
            (template_id,),
        )

        return cur.fetchall()

    except sqlite3.Error as e:
        logger.error(f"Database error in get_template_steps: {e}")

        return []

    except Exception as e:
        logger.exception(f"Unexpected error in get_template_steps: {e}")

        return []


def save_routine_template(tid, name, cycle, desc, steps):
    """Create/update a routine template and its checklist steps."""

    conn = get_connection()

    if not conn:
        return

    try:
        cur = conn.cursor()

        if tid:
            cur.execute(
                "UPDATE routine_template SET name=?, cycle_type=?, description=? WHERE id=?",
                (name, cycle, desc, tid),
            )

            cur.execute("DELETE FROM template_step WHERE template_id=?", (tid,))

        else:
            cur.execute(
                "INSERT INTO routine_template (name, cycle_type, description) VALUES (?, ?, ?)",
                (name, cycle, desc),
            )

            tid = cur.lastrowid

        for idx, sname in enumerate(steps):
            cur.execute(
                "INSERT INTO template_step (template_id, step_name, step_order) VALUES (?, ?, ?)",
                (tid, sname, idx),
            )

        conn.commit()

    except sqlite3.Error as e:
        logger.error(f"Database error in save_routine_template: {e}")

        conn.rollback()

    except Exception as e:
        logger.exception(f"Unexpected error in save_routine_template: {e}")

        conn.rollback()


def save_routine_template_unified(tid, name, cycle, desc, checklist_template_id):
    """Save routine template with optional checklist template id."""

    conn = get_connection()

    if not conn:
        return None

    try:
        cur = conn.cursor()

        if tid:
            cur.execute(
                """

                UPDATE routine_template

                SET name=?, cycle_type=?, description=?, checklist_template_id=?

                WHERE id=?

            """,
                (name, cycle, desc, checklist_template_id, tid),
            )

        else:
            cur.execute(
                """

                INSERT INTO routine_template (name, cycle_type, description, checklist_template_id)

                VALUES (?, ?, ?, ?)

            """,
                (name, cycle, desc, checklist_template_id),
            )

            tid = cur.lastrowid

        conn.commit()

        return tid

    except sqlite3.Error as e:
        logger.error(f"Database error in save_routine_template_unified: {e}")

        conn.rollback()

        return None

    except Exception as e:
        logger.exception(f"Unexpected error in save_routine_template_unified: {e}")

        conn.rollback()

        return None


def get_routine_status(target_date=None):
    """

    Query routine status.

    Includes routines where target date is today or today's date is within period.

    """

    if not target_date:
        from datetime import datetime

        target_date = datetime.now().strftime("%Y-%m-%d")

    conn = get_connection()

    if not conn:
        return []

    try:
        cur = conn.cursor()

        # Query routine tasks from unified_task (period-based), optimized subquery

        cur.execute(
            """

            SELECT t.id, t.name, COALESCE(t.cycle_type, 'monthly') as cycle_type,

                   COUNT(tcl.id) as total,

                   SUM(CASE WHEN tcl.is_completed = 1 THEN 1 ELSE 0 END) as comp

            FROM unified_task t

            LEFT JOIN task_checklist_link tcl ON tcl.owner_id = t.id AND tcl.owner_type = 'routine'

            WHERE (t.status IN ('pending', 'in_progress') OR t.type='routine')

              AND (

                -- Today is within the period

                (t.period_start IS NOT NULL AND t.period_end IS NOT NULL

                 AND date(?) BETWEEN date(t.period_start) AND date(t.period_end))

                OR

                -- target_date is today

                (date(t.target_date) = date(?))

                OR

                -- No period and still incomplete

                (t.period_start IS NULL AND t.is_completed = 0)

              )

            GROUP BY t.id, t.name, t.cycle_type, t.is_completed, t.priority, t.created_at

            ORDER BY t.is_completed ASC, t.priority DESC, t.created_at DESC

        """,
            (target_date, target_date),
        )

        return cur.fetchall()

    except sqlite3.Error as e:
        logger.error(f"Database error in get_routine_status: {e}")

        return []

    except Exception as e:
        logger.exception(f"Unexpected error in get_routine_status: {e}")

        return []


def get_routine_steps(routine_id):
    conn = get_connection()

    if not conn:
        return []

    res = []

    try:
        cur = conn.cursor()

        # Use task_checklist_link as routine checklist source

        cur.execute(
            """

            SELECT id, item_text as step_name, is_completed

            FROM task_checklist_link

            WHERE owner_id=? AND owner_type='routine'

            ORDER BY item_order ASC, id ASC

        """,
            (routine_id,),
        )

        res = cur.fetchall()

    except Exception:
        pass

    return res


def instantiate_routine(template_id, target_date):
    conn = get_connection()

    if not conn:
        return

    try:
        cur = conn.cursor()

        # ?대? 議댁옱?섎㈃ 以묐났 ?앹꽦 諛⑹?

        cur.execute(
            "SELECT id FROM routine_task WHERE template_id=? AND target_date=?",
            (template_id, target_date),
        )

        if cur.fetchone():
            return

        cur.execute(
            "SELECT name, cycle_type, description FROM routine_template WHERE id=?", (template_id,)
        )

        row = cur.fetchone()

        if not row:
            return

        name, cycle, desc = row

        cur.execute(
            "INSERT INTO routine_task (template_id, name, target_date, cycle_type, description) VALUES (?, ?, ?, ?, ?)",
            (template_id, name, target_date, cycle, desc),
        )

        new_rid = cur.lastrowid

        cur.execute(
            "SELECT step_name, step_order FROM template_step WHERE template_id=? ORDER BY step_order ASC",
            (template_id,),
        )

        for sn, so in cur.fetchall():
            cur.execute(
                "INSERT INTO routine_process (routine_id, step_name, step_order) VALUES (?, ?, ?)",
                (new_rid, sn, so),
            )

        conn.commit()

    except sqlite3.Error as e:
        logger.error(f"Database error in instantiate_routine: {e}")

        conn.rollback()

    except Exception as e:
        logger.exception(f"Unexpected error in instantiate_routine: {e}")

        conn.rollback()


def delete_routine_template(tid):
    conn = get_connection()

    if not conn:
        return

    try:
        cur = conn.cursor()

        cur.execute("UPDATE routine_template SET is_active=0 WHERE id=?", (tid,))

        conn.commit()

    except sqlite3.Error as e:
        logger.error(f"Database error in delete_routine_template: {e}")

        conn.rollback()

    except Exception as e:
        logger.exception(f"Unexpected error in delete_routine_template: {e}")

        conn.rollback()


def toggle_routine_step(step_id):
    """Toggle checklist step completion (routine_process + task_checklist_link)."""

    conn = get_connection()

    if not conn:
        return

    try:
        cur = conn.cursor()

        # 1. ?좉?

        cur.execute(
            """

            UPDATE task_checklist_link

            SET is_completed = 1 - is_completed,

                completed_at = CASE WHEN is_completed = 0 THEN datetime('now', 'localtime') ELSE NULL END

            WHERE id=?

        """,
            (step_id,),
        )

        # 2. Get parent routine id

        cur.execute("SELECT owner_id FROM task_checklist_link WHERE id=?", (step_id,))

        row = cur.fetchone()

        if not row:
            conn.commit()

            return

        rid = row[0]

        # 3. Check whether all checklist items are completed

        cur.execute(
            "SELECT COUNT(*) FROM task_checklist_link WHERE owner_id=? AND owner_type='routine'",
            (rid,),
        )

        total = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM task_checklist_link WHERE owner_id=? AND owner_type='routine' AND is_completed=1",
            (rid,),
        )

        comp = cur.fetchone()[0]

        is_all_done = 1 if total > 0 and total == comp else 0

        # unified_task ?먮뒗 routine_task ?낅뜲?댄듃

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='unified_task'")

        if cur.fetchone():
            cur.execute(
                """

                UPDATE unified_task

                SET is_completed = ?,

                    completed_at = CASE WHEN ? = 1 THEN datetime('now', 'localtime') ELSE NULL END

                WHERE id=? AND (type='routine' OR type='schedule')

            """,
                (is_all_done, is_all_done, rid),
            )

        else:
            cur.execute(
                """

                UPDATE routine_task

                SET is_completed = ?,

                    completed_at = CASE WHEN ? = 1 THEN datetime('now', 'localtime') ELSE NULL END

                WHERE id=?

            """,
                (is_all_done, is_all_done, rid),
            )

        conn.commit()

    except Exception as e:
        print(f"Error toggling step: {e}")


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
    """Fetch tasks for the given date from unified_task."""

    conn = get_connection()

    if not conn:
        return []

    tasks = []

    try:
        cur = conn.cursor()

        # unified_task 議고쉶

        cur.execute(
            """

            SELECT id, name, priority, deadline, 'schedule' as type, status

            FROM unified_task

            WHERE date(substr(deadline, 1, 10)) = date(?)

            ORDER BY priority DESC, deadline ASC

        """,
            (date_str,),
        )

        for row in cur.fetchall():
            tasks.append(
                {
                    "id": row[0],
                    "name": row[1],
                    "priority": row[2] or "normal",
                    "deadline": row[3],
                    "type": "schedule",
                    "is_completed": row[5] != "pending",
                }
            )

        # unified_task 議고쉶

        cur.execute(
            """

            SELECT id, name, priority, deadline, type, is_completed

            FROM unified_task

            WHERE date(substr(deadline, 1, 10)) = date(?)

            ORDER BY priority DESC, deadline ASC

        """,
            (date_str,),
        )

        for row in cur.fetchall():
            tasks.append(
                {
                    "id": row[0],
                    "name": row[1],
                    "priority": row[2] or "normal",
                    "deadline": row[3],
                    "type": row[4],
                    "is_completed": row[5] == 1,
                }
            )

    except Exception as e:
        logger.exception("Unexpected error in get_tasks_by_date: %s", e)

    return tasks


def get_worklog_entries(limit=100):
    """최근 초집중 모드 기록을 조회합니다."""

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
                COALESCE(t.name, 'Deleted/Ghost Task') as task_name,
                w.elapsed_secs,
                w.logged_at,
                w.task_type
            FROM worklog w
            LEFT JOIN unified_task t ON w.task_id = t.id
            ORDER BY w.logged_at DESC
            LIMIT ?
        """,
            (limit,),
        )

        return cur.fetchall()

    except Exception as e:
        logger.exception("Error in get_worklog_entries: %s", e)

        return []


def get_incomplete_tasks():
    """Return all incomplete tasks (unified_task)."""

    conn = get_connection()

    if not conn:
        return []

    tasks = []

    try:
        cur = conn.cursor()

        # unified_task 議고쉶

        cur.execute("""

            SELECT id, name, priority, deadline, 'schedule' as type, status

            FROM unified_task

            WHERE status IN ('pending', 'in_progress')

            ORDER BY priority DESC, deadline ASC

        """)

        for row in cur.fetchall():
            tasks.append(
                {
                    "id": row[0],
                    "name": row[1],
                    "priority": row[2] or "normal",
                    "deadline": row[3],
                    "type": "schedule",
                    "is_completed": False,
                }
            )

        # unified_task 議고쉶

        cur.execute("""

            SELECT id, name, priority, deadline, type, is_completed

            FROM unified_task

            WHERE is_completed=0

            ORDER BY priority DESC, deadline ASC

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
            "SELECT id, name FROM unified_task WHERE status IN ('pending', 'in_progress') AND date(substr(deadline, 1, 10)) <= date(?) AND date(substr(ifnull(end_date, deadline), 1, 10)) >= date(?) ORDER BY priority DESC, deadline ASC LIMIT 1",
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

        # 1. ?쇰컲 일정 諛?기간 일정

        try:
            cur.execute(
                """SELECT id, name, priority, deadline, end_date, bg_color, icon FROM unified_task

                WHERE status IN ('pending', 'in_progress') AND (recurrence IS NULL OR recurrence='none')

                  AND date(substr(deadline, 1, 10)) <= date(?)

                  AND date(substr(ifnull(end_date, deadline), 1, 10)) >= date(?)

                ORDER BY priority DESC, deadline ASC

            """,
                (target_date_str, target_date_str),
            )

        except sqlite3.OperationalError:
            cur.execute(
                """SELECT id, name, priority, deadline, end_date, NULL, NULL FROM unified_task

                WHERE status='pending' AND recurrence IS NULL OR recurrence='none'

                  AND date(substr(deadline, 1, 10)) <= date(?)

                  AND date(substr(ifnull(end_date, deadline), 1, 10)) >= date(?)

                ORDER BY priority DESC, deadline ASC

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


def get_task_by_id(task_id):
    conn = get_connection()

    if not conn:
        return None

    try:
        cur = conn.cursor()

        cur.execute(
            "SELECT name, priority, deadline, end_date, bg_color, icon, gcal_event_id, recurrence, alarm_time, memo FROM unified_task WHERE id=?",
            (task_id,),
        )

        return cur.fetchone()

    except Exception:
        pass

    return None


def update_task_dates(task_id, new_start_str, new_end_str):
    conn = get_connection()

    if not conn:
        return False

    try:
        cur = conn.cursor()

        cur.execute(
            "UPDATE unified_task SET deadline=?, end_date=? WHERE id=?",
            (new_start_str, new_end_str, task_id),
        )

        conn.commit()

        return True

    except sqlite3.Error as e:
        logger.error(f"Database error in update_task_dates: {e}")

        conn.rollback()

        return False


def insert_task(task_data, gcal_id=None):
    name = task_data.get("name")

    priority = task_data.get("priority", "normal")

    start_str = task_data.get("start_str")

    end_str = task_data.get("end_str")

    bg_color = task_data.get("bg_color")

    icon = task_data.get("icon")

    recurrence = task_data.get("recurrence")

    alarm = task_data.get("alarm")

    memo = task_data.get("memo")

    conn = get_connection()

    if not conn:
        return None

    try:
        cur = conn.cursor()

        cur.execute(
            """

            INSERT INTO unified_task (name, priority, deadline, end_date, bg_color, icon, recurrence, alarm_time, memo, status, gcal_event_id)

            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'in_progress', ?)

        """,
            (name, priority, start_str, end_str, bg_color, icon, recurrence, alarm, memo, gcal_id),
        )

        new_id = cur.lastrowid

        conn.commit()

        return new_id

    except Exception as e:
        print(f"Error inserting task: {e}")

        return None


def copy_task_with_dates(name, priority, start_str, end_str, bg_color, icon, gcal_id=None):
    conn = get_connection()

    if not conn:
        return False

    try:
        cur = conn.cursor()

        cur.execute(
            """

            INSERT INTO unified_task (name, priority, deadline, end_date, bg_color, icon, status, gcal_event_id)

            VALUES (?, ?, ?, ?, ?, ?, 'in_progress', ?)

        """,
            (name, priority, start_str, end_str, bg_color, icon, gcal_id),
        )

        conn.commit()

        return True

    except sqlite3.Error as e:
        logger.error(f"Database error in copy_task_with_dates: {e}")

        conn.rollback()

        return False


def get_all_gcal_tasks():
    conn = get_connection()

    if not conn:
        return {}

    try:
        cur = conn.cursor()

        cur.execute("SELECT id, gcal_event_id FROM unified_task WHERE gcal_event_id IS NOT NULL")

        return {row[1]: row[0] for row in cur.fetchall()}

    except Exception:
        pass

    return {}


def update_task_basic(
    task_id,
    name,
    deadline,
    end_date,
    priority="normal",
    bg_color=None,
    icon=None,
    recurrence=None,
    alarm_time=None,
    memo=None,
):
    conn = get_connection()

    if not conn:
        return

    try:
        cur = conn.cursor()

        cur.execute(
            """UPDATE unified_task SET

                        name=?, priority=?, deadline=?, end_date=?,

                        bg_color=?, icon=?, recurrence=?, alarm_time=?, memo=?

                        WHERE id=?""",
            (
                name,
                priority,
                deadline,
                end_date,
                bg_color,
                icon,
                recurrence,
                alarm_time,
                memo,
                task_id,
            ),
        )

        conn.commit()

    except Exception:
        pass


def insert_gcal_event_task(name, deadline, end_date, gcal_id):
    conn = get_connection()

    if not conn:
        return

    try:
        cur = conn.cursor()

        cur.execute(
            """

            INSERT INTO unified_task (name, priority, deadline, end_date, bg_color, icon, status, gcal_event_id)

            VALUES (?, 'normal', ?, ?, 'rgba(66, 133, 244, 0.4)', '', 'in_progress', ?)

        """,
            (name, deadline, end_date, gcal_id),
        )

        conn.commit()

    except Exception:
        pass


def delete_task(task_id):
    conn = get_connection()

    if not conn:
        return

    try:
        cur = conn.cursor()

        cur.execute("DELETE FROM unified_task WHERE id=?", (task_id,))

        conn.commit()

    except Exception:
        pass


def update_task_status(task_id, status):
    conn = get_connection()

    if not conn:
        return

    try:
        cur = conn.cursor()

        cur.execute("UPDATE unified_task SET status=? WHERE id=?", (status, task_id))

        conn.commit()

    except Exception:
        pass


def update_task_duration(task_id, minutes):
    conn = get_connection()

    if not conn:
        return

    try:
        cur = conn.cursor()

        cur.execute("SELECT deadline FROM unified_task WHERE id=?", (task_id,))

        row = cur.fetchone()

        if row and row[0]:
            from datetime import datetime, timedelta

            start_str = row[0]

            # Try various formats to be safe

            dt = None

            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(start_str.strip(), fmt)

                    break

                except ValueError:
                    continue

            if dt:
                end_dt = dt + timedelta(minutes=minutes)

                end_str = end_dt.strftime("%Y-%m-%d %H:%M")

                cur.execute("UPDATE unified_task SET end_date=? WHERE id=?", (end_str, task_id))

                conn.commit()

            else:
                print(f"Could not parse date: {start_str}")

    except Exception as e:
        print(f"Error updating duration: {e}")


# ------------------------------------------------------------

# Shared checklist CRUD

# ------------------------------------------------------------


def get_all_checklists():
    conn = get_connection()

    if not conn:
        return []

    try:
        cur = conn.cursor()

        cur.execute("SELECT id, name, description FROM checklist_template ORDER BY name ASC")

        return cur.fetchall()

    except sqlite3.Error as e:
        logger.error(f"Database error in get_all_checklists: {e}")

        return []

    except Exception as e:
        logger.exception(f"Unexpected error in get_all_checklists: {e}")

        return []


def get_checklist_items(checklist_id):
    conn = get_connection()

    if not conn:
        return []

    try:
        cur = conn.cursor()

        cur.execute(
            "SELECT id, item_text, item_order FROM checklist_item WHERE checklist_id=? ORDER BY item_order ASC",
            (checklist_id,),
        )

        return cur.fetchall()

    except sqlite3.Error as e:
        logger.error(f"Database error in get_checklist_items: {e}")

        return []

    except Exception as e:
        logger.exception(f"Unexpected error in get_checklist_items: {e}")

        return []


def save_checklist(cid, name, desc, items):
    """Create when cid is None; otherwise update checklist."""

    conn = get_connection()

    if not conn:
        return None

    try:
        cur = conn.cursor()

        if cid:
            cur.execute(
                "UPDATE checklist_template SET name=?, description=? WHERE id=?", (name, desc, cid)
            )

            cur.execute("DELETE FROM checklist_item WHERE checklist_id=?", (cid,))

        else:
            cur.execute(
                "INSERT INTO checklist_template (name, description) VALUES (?, ?)", (name, desc)
            )

            cid = cur.lastrowid

        for idx, text in enumerate(items):
            cur.execute(
                "INSERT INTO checklist_item (checklist_id, item_text, item_order) VALUES (?, ?, ?)",
                (cid, text, idx),
            )

        conn.commit()

        return cid

    except sqlite3.Error as e:
        logger.error(f"Database error in save_checklist: {e}")

        conn.rollback()

        return None

    except Exception as e:
        logger.exception(f"Unexpected error in save_checklist: {e}")

        conn.rollback()

        return None


def delete_checklist(cid):
    conn = get_connection()

    if not conn:
        return

    try:
        cur = conn.cursor()

        cur.execute("DELETE FROM checklist_item WHERE checklist_id=?", (cid,))

        cur.execute("DELETE FROM checklist_template WHERE id=?", (cid,))

        conn.commit()

    except sqlite3.Error as e:
        logger.error(f"Database error in delete_checklist: {e}")

        conn.rollback()

    except Exception as e:
        logger.exception(f"Unexpected error in delete_checklist: {e}")

        conn.rollback()


def apply_checklist_to(owner_type, owner_id, checklist_id):
    """Apply checklist template to schedule/routine by copying items."""

    conn = get_connection()

    if not conn:
        return

    try:
        cur = conn.cursor()

        cur.execute(
            "DELETE FROM task_checklist_link WHERE owner_type=? AND owner_id=?",
            (owner_type, owner_id),
        )

        cur.execute(
            "SELECT item_text, item_order FROM checklist_item WHERE checklist_id=? ORDER BY item_order ASC",
            (checklist_id,),
        )

        display_type = "list"

        try:
            cur.execute("SELECT checklist_type FROM checklist_template WHERE id=?", (checklist_id,))

            row = cur.fetchone()

            if row and row[0]:
                display_type = row[0]

        except Exception:
            pass

        for text, order in cur.fetchall():
            cur.execute(
                "INSERT INTO task_checklist_link (owner_type, owner_id, item_text, item_order, display_type) VALUES (?, ?, ?, ?, ?)",
                (owner_type, owner_id, text, order, display_type),
            )

        conn.commit()

    except sqlite3.Error as e:
        logger.error(f"Database error in apply_checklist_to: {e}")

        conn.rollback()

    except Exception as e:
        logger.exception(f"Unexpected error in apply_checklist_to: {e}")

        conn.rollback()


def get_checklist_for(owner_type, owner_id):
    conn = get_connection()

    if not conn:
        return []

    try:
        cur = conn.cursor()

        cur.execute(
            "SELECT id, item_text, item_order, is_completed, completed_at "
            "FROM task_checklist_link WHERE owner_type=? AND owner_id=? ORDER BY item_order ASC",
            (owner_type, owner_id),
        )

        return cur.fetchall()

    except sqlite3.Error as e:
        logger.error(f"Database error in get_checklist_for: {e}")

        return []

    except Exception as e:
        logger.exception(f"Unexpected error in get_checklist_for: {e}")

        return []


def save_checklist_items_for(owner_type, owner_id, items):
    """Save directly entered checklist items (items: list[str])."""

    conn = get_connection()

    if not conn:
        return

    try:
        cur = conn.cursor()

        display_type = "list"

        try:
            cur.execute(
                "SELECT display_type FROM task_checklist_link WHERE owner_type=? AND owner_id=? LIMIT 1",
                (owner_type, owner_id),
            )

            row = cur.fetchone()

            if row and row[0]:
                display_type = row[0]

        except Exception:
            pass

        cur.execute(
            "DELETE FROM task_checklist_link WHERE owner_type=? AND owner_id=?",
            (owner_type, owner_id),
        )

        for idx, text in enumerate(items):
            cur.execute(
                "INSERT INTO task_checklist_link (owner_type, owner_id, item_text, item_order, display_type) VALUES (?, ?, ?, ?, ?)",
                (owner_type, owner_id, text, idx, display_type),
            )

        conn.commit()

    except sqlite3.Error as e:
        logger.error(f"Database error in save_checklist_items_for: {e}")

        conn.rollback()

    except Exception as e:
        logger.exception(f"Unexpected error in save_checklist_items_for: {e}")

        conn.rollback()


def toggle_checklist_item(link_id):
    conn = get_connection()

    if not conn:
        return

    try:
        cur = conn.cursor()

        cur.execute(
            """

            SELECT id, owner_type, owner_id, item_order, is_completed, display_type

            FROM task_checklist_link

            WHERE id=?

        """,
            (link_id,),
        )

        row = cur.fetchone()

        if not row:
            conn.commit()

            return

        display_type = row["display_type"] or "list"

        owner_id = row["owner_id"]

        owner_type = row["owner_type"]

        item_order = row["item_order"]

        is_completed = row["is_completed"]

        if display_type != "process":
            cur.execute(
                """

                UPDATE task_checklist_link

                SET is_completed = 1 - is_completed,

                    completed_at = CASE WHEN is_completed = 0 THEN datetime('now', 'localtime') ELSE NULL END

                WHERE id=?

            """,
                (link_id,),
            )

            conn.commit()

            return

        cur.execute(
            """

            SELECT id, item_order, is_completed

            FROM task_checklist_link

            WHERE owner_id=?

            ORDER BY item_order

        """,
            (owner_id,),
        )

        items = cur.fetchall()

        if not items:
            conn.commit()

            return

        first_incomplete = next((item for item in items if item["is_completed"] == 0), None)

        if is_completed == 0:
            if not first_incomplete or first_incomplete["id"] != link_id:
                conn.commit()

                return

            cur.execute(
                """

                UPDATE task_checklist_link

                SET is_completed = 1,

                    completed_at = datetime('now', 'localtime')

                WHERE id=?

            """,
                (link_id,),
            )

        else:
            cur.execute(
                """

                UPDATE task_checklist_link

                SET is_completed = 0,

                    completed_at = NULL

                WHERE owner_id=? AND item_order >= ?

            """,
                (owner_id, item_order),
            )

        cur.execute(
            """

            SELECT COUNT(*) as total,

                   SUM(CASE WHEN is_completed=1 THEN 1 ELSE 0 END) as completed

            FROM task_checklist_link

            WHERE owner_id=?

        """,
            (owner_id,),
        )

        status = cur.fetchone()

        total = status["total"] or 0

        completed = status["completed"] or 0

        should_rollover = False

        if total > 0 and completed == total:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if owner_type == "routine":
                cur.execute(
                    """

                    UPDATE unified_task

                    SET is_completed = 1,

                        completed_at = ?

                    WHERE id=? AND type='routine'

                """,
                    (now, owner_id),
                )

                should_rollover = True

            else:
                cur.execute(
                    """

                    UPDATE unified_task

                    SET status = 'completed'

                    WHERE id=? AND type='schedule'

                """,
                    (owner_id,),
                )

        conn.commit()

        if should_rollover:
            _run_checklist_routine_rollover(owner_id)

    except Exception as e:
        print(f"Error toggling checklist item: {e}")


def save_routine_task(data, routine_id=None):
    conn = get_connection()

    if not conn:
        return None

    try:
        cur = conn.cursor()

        fields = [
            "name",
            "target_date",
            "cycle_type",
            "description",
            "priority",
            "icon",
            "bg_color",
            "alarm_time",
            "memo",
            "recurrence",
            "template_id",
        ]

        if routine_id:
            sets = ", ".join(f"{f}=?" for f in fields)

            vals = [data.get(f) for f in fields] + [routine_id]

            cur.execute(f"UPDATE routine_task SET {sets} WHERE id=?", vals)

        else:
            cols = ", ".join(fields)

            placeholders = ", ".join("?" for _ in fields)

            vals = [data.get(f) for f in fields]

            cur.execute(f"INSERT INTO routine_task ({cols}) VALUES ({placeholders})", vals)

            routine_id = cur.lastrowid

        conn.commit()

        return routine_id

    except sqlite3.Error as e:
        logger.error(f"Database error in save_routine_task: {e}")

        conn.rollback()

        return None

    except Exception as e:
        logger.exception(f"Unexpected error in save_routine_task: {e}")

        conn.rollback()

        return None


def get_routine_task(routine_id):
    conn = get_connection()

    if not conn:
        return None

    try:
        cur = conn.cursor()

        cur.execute("SELECT * FROM routine_task WHERE id=?", (routine_id,))

        return cur.fetchone()

    except sqlite3.Error as e:
        logger.error(f"Database error in get_routine_task: {e}")

        return None

    except Exception as e:
        logger.exception(f"Unexpected error in get_routine_task: {e}")

        return None


def delete_routine_task(routine_id):
    conn = get_connection()

    if not conn:
        return

    try:
        cur = conn.cursor()

        cur.execute(
            "DELETE FROM task_checklist_link WHERE owner_type='routine' AND owner_id=?",
            (routine_id,),
        )

        cur.execute("DELETE FROM routine_task WHERE id=?", (routine_id,))

        conn.commit()

    except sqlite3.Error as e:
        logger.error(f"Database error in delete_routine_task: {e}")

        conn.rollback()

    except Exception as e:
        logger.exception(f"Unexpected error in delete_routine_task: {e}")

        conn.rollback()
