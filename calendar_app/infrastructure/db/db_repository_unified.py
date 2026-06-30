from datetime import UTC, datetime, timedelta
import json

from calendar_app.domain.routine_cycle import cycle_display_name
from calendar_app.domain.task_status_view import can_transition_status
from calendar_app.domain.task_validation import normalize_task_payload
from calendar_app.infrastructure.db.database_unified import db_manager, logger
from calendar_app.infrastructure.db.period_utils import (
    calculate_period_bounds as _calculate_period_bounds,
)

_GCAL_META_ONLY_FIELDS = {
    "gcal_event_id",
    "gcal_dirty",
    "gcal_last_synced_at",
    "gcal_remote_updated_at",
    "gcal_sync_error",
    "updated_at",
}

_schema_cache: dict[tuple[str, str], set] = {}


def _now_local_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _now_utc_iso():
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_connection():
    """Singleton 데이터베이스 관리자를 통해 연결을 획득합니다."""
    return db_manager.get_connection()


def _table_columns(cur, table_name: str) -> set:
    db_path = ""
    try:
        cur.execute("PRAGMA database_list")
        for row in cur.fetchall():
            if row[1] == "main":
                db_path = str(row[2] or "")
                break
    except Exception:
        db_path = ""

    cache_key = (db_path, table_name)
    if cache_key not in _schema_cache:
        cur.execute(f"PRAGMA table_info({table_name})")
        _schema_cache[cache_key] = {row[1] for row in cur.fetchall()}
    return _schema_cache[cache_key]


# ==================== 일반업무 유형별 기간 계산 ====================


def calculate_period_bounds(target_date_str, cycle_type):
    """Backward-compatible proxy to period_utils.calculate_period_bounds."""
    return _calculate_period_bounds(target_date_str, cycle_type)


def get_cycle_type_display_name(cycle_type):
    """Returns the localized display name of the routine type."""
    return cycle_display_name(cycle_type, scope="recurrence")


# ==================== CRUD: Create ====================


def create_unified_task(task_data, commit=True):
    """
    통합 task 생성 (일정 또는 일반업무)

    Args:
        task_data: dict 형태의 task 정보
            필수: name, type ('schedule' or 'routine')
            선택: priority, deadline, end_date, alarm_time, recurrence,
                  template_id, target_date, cycle_type, bg_color, icon,
                  description, memo, all_day, gcal_event_id

    Returns:
        생성된 task의 ID
    """
    task_data, issues = normalize_task_payload(task_data, is_update=False)
    if any(issue.field == "name" and issue.code == "required" for issue in issues):
        logger.error("Error creating unified task: task name is required")
        return None
    if task_data.get("status") == "completed":
        task_data["is_completed"] = 1
        task_data["completed_at"] = task_data.get("completed_at") or _now_local_str()
    else:
        task_data["is_completed"] = int(bool(task_data.get("is_completed")))
        if not task_data["is_completed"]:
            task_data["completed_at"] = None

    conn = get_connection()
    if not conn:
        return None

    cur = conn.cursor()

    # 일반업무인 경우 period_start, period_end 자동 계산
    period_start = None
    period_end = None
    if task_data.get("type") == "routine":
        target_date = task_data.get("target_date") or task_data.get("deadline")
        cycle_type = task_data.get("cycle_type", "monthly")
        if target_date:
            period_start, period_end = calculate_period_bounds(target_date, cycle_type)

    try:
        created_at = _now_local_str()
        has_gcal_id = bool((task_data.get("gcal_event_id") or "").strip())
        gcal_dirty = task_data.get("gcal_dirty")
        if gcal_dirty is None:
            gcal_dirty = 0 if has_gcal_id else 1
        gcal_last_synced_at = task_data.get("gcal_last_synced_at") or (
            created_at if has_gcal_id else None
        )
        gcal_remote_updated_at = task_data.get("gcal_remote_updated_at")
        gcal_sync_error = task_data.get("gcal_sync_error")

        cur.execute(
            """
            INSERT INTO unified_task (
                name, type, priority, status, deadline, end_date, alarm_time,
                recurrence, template_id, target_date, cycle_type,
                period_start, period_end, bg_color, icon, description, memo,
                location, assignee, all_day, calendar_id, gcal_event_id, gcal_dirty,
                gcal_last_synced_at, gcal_remote_updated_at, gcal_sync_error,
                updated_at, created_at, tags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                task_data["name"],
                task_data.get("type", "schedule"),
                task_data.get("priority", "normal"),
                task_data.get("status", "in_progress"),
                task_data.get("deadline"),
                task_data.get("end_date"),
                task_data.get("alarm_time"),
                task_data.get("recurrence"),
                task_data.get("template_id"),
                task_data.get("target_date"),
                task_data.get("cycle_type"),
                period_start,
                period_end,
                task_data.get("bg_color"),
                task_data.get("icon"),
                task_data.get("description"),
                task_data.get("memo"),
                task_data.get("location"),
                task_data.get("assignee"),
                task_data.get("all_day", 0),
                task_data.get("calendar_id"),
                task_data.get("gcal_event_id"),
                int(bool(gcal_dirty)),
                gcal_last_synced_at,
                gcal_remote_updated_at,
                gcal_sync_error,
                created_at,
                created_at,
                task_data.get("tags"),
            ),
        )

        task_id = cur.lastrowid
        unified_cols = _table_columns(cur, "unified_task")
        extra_sets = []
        extra_params = []
        for col in (
            "is_completed",
            "completed_at",
            "series_id",
            "series_order",
            "series_total",
            "gcal_source_calendar_id",
            "gcal_source_summary",
            "gcal_target_calendar_id",
            "gcal_sync_mode",
        ):
            if col in unified_cols and col in task_data:
                extra_sets.append(f"{col}=?")
                extra_params.append(task_data.get(col))
        if extra_sets:
            extra_sets.append("updated_at=?")
            extra_params.append(created_at)
            extra_params.append(task_id)
            cur.execute(
                f"UPDATE unified_task SET {', '.join(extra_sets)} WHERE id=?",
                tuple(extra_params),
            )
        if commit:
            conn.commit()
        return task_id

    except Exception as e:
        logger.error(f"Error creating unified task: {e}")
        if commit:
            conn.rollback()
        return None


# ==================== CRUD: Read ====================


def get_unified_task(task_id):
    """특정 task 조회 (dict 형태 반환)"""
    conn = get_connection()
    if not conn:
        return None

    cur = conn.cursor()
    cur.execute("SELECT * FROM unified_task WHERE id=?", (task_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def find_orphan_candidate(name, deadline_str, calendar_id=None):
    """
    구글 고아(Orphan) 일정의 자가 치유를 위해, 로컬에서 gcal_event_id가 아직 연동되지 않은(NULL)
    동일 제목(name)과 시작시간(deadline)을 가진 일정을 검색합니다.
    """
    if not name or not deadline_str:
        return None
    conn = get_connection()
    if not conn:
        return None

    cur = conn.cursor()
    if calendar_id:
        cur.execute(
            "SELECT * FROM unified_task WHERE gcal_event_id IS NULL AND name = ? AND deadline = ? AND calendar_id = ? LIMIT 1",
            (name, deadline_str, calendar_id),
        )
    else:
        cur.execute(
            "SELECT * FROM unified_task WHERE gcal_event_id IS NULL AND name = ? AND deadline = ? LIMIT 1",
            (name, deadline_str),
        )
    row = cur.fetchone()
    return dict(row) if row else None


def get_google_sync_tasks():
    """Return unified tasks eligible for Google Calendar push sync."""
    conn = get_connection()
    if not conn:
        return []

    cur = conn.cursor()
    columns = {row[1] for row in cur.execute("PRAGMA table_info(unified_task)").fetchall()}
    sync_mode_filter = ""
    if "gcal_sync_mode" in columns:
        sync_mode_filter = (
            "AND COALESCE(NULLIF(trim(gcal_sync_mode), ''), 'local_owned') != 'unknown'"
        )
    if "gcal_dirty" in columns:
        cur.execute(
            f"""
            SELECT *
            FROM unified_task
            WHERE deadline IS NOT NULL
              AND trim(deadline) != ''
              AND type != 'routine'
              AND COALESCE(gcal_dirty, CASE WHEN gcal_event_id IS NULL OR trim(gcal_event_id) = '' THEN 1 ELSE 0 END) = 1
              {sync_mode_filter}
            ORDER BY id ASC
            """
        )
    else:
        cur.execute(
            f"""
            SELECT *
            FROM unified_task
            WHERE deadline IS NOT NULL
              AND trim(deadline) != ''
              AND type != 'routine'
              {sync_mode_filter}
            ORDER BY id ASC
            """
        )
    rows = cur.fetchall()
    return [dict(row) for row in rows]


def detach_all_gcal_links(mark_dirty=True):
    conn = get_connection()
    if not conn:
        return 0
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE unified_task
            SET gcal_event_id=NULL,
                gcal_dirty=?,
                gcal_last_synced_at=NULL,
                gcal_remote_updated_at=NULL,
                gcal_sync_error=NULL,
                updated_at=?
            WHERE gcal_event_id IS NOT NULL
              AND trim(gcal_event_id) != ''
            """,
            (1 if mark_dirty else 0, _now_local_str()),
        )
        conn.commit()
        return int(cur.rowcount or 0)
    except Exception as e:
        logger.error(f"Error detaching Google Calendar links: {e}")
        conn.rollback()
        return 0


def get_tasks_by_type(task_type, date_filter=None, status_filter=None):
    """
    타입별 task 조회 (schedule 또는 routine)
    """
    conn = get_connection()
    if not conn:
        return []

    cur = conn.cursor()

    query = "SELECT * FROM unified_task WHERE type=?"
    params = [task_type]

    if date_filter:
        if task_type == "routine":
            query += " AND date(target_date) = date(?)"
        else:
            query += " AND date(deadline) = date(?)"
        params.append(date_filter)

    if status_filter:
        query += " AND status=?"
        params.append(status_filter)

    query += " ORDER BY deadline ASC"

    cur.execute(query, params)
    rows = cur.fetchall()
    return [dict(row) for row in rows]


def get_routines_by_period(cycle_type, period_start, period_end=None):
    """
    특정 기간의 일반업무 조회
    """
    conn = get_connection()
    if not conn:
        return []

    if not period_end:
        period_end = period_start

    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM unified_task
        WHERE type='routine'
          AND cycle_type=?
          AND period_start <= ?
          AND period_end >= ?
        ORDER BY target_date ASC
    """,
        (cycle_type, period_end, period_start),
    )

    rows = cur.fetchall()
    return [dict(row) for row in rows]


def get_all_routines_grouped_by_cycle():
    """
    모든 일반업무를 cycle_type별로 그룹화하여 반환
    """
    conn = get_connection()
    if not conn:
        return {}

    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM unified_task
        WHERE type='routine'
        ORDER BY cycle_type, target_date DESC
    """)

    rows = cur.fetchall()
    grouped = {"weekly": [], "monthly": [], "quarterly": [], "half_yearly": [], "yearly": []}

    for row in rows:
        task = dict(row)
        cycle = task.get("cycle_type", "monthly")
        if cycle in grouped:
            grouped[cycle].append(task)

    return grouped


# ==================== CRUD: Update ====================


def update_unified_task(task_id, updates, mark_gcal_dirty=None):
    """
    통합 task 수정
    """
    conn = get_connection()
    if not conn:
        return False

    cur = conn.cursor()
    updates = dict(updates or {})
    cur.execute("SELECT * FROM unified_task WHERE id=?", (task_id,))
    existing = cur.fetchone()
    if not existing:
        return False
    existing_task = dict(existing)

    updates, issues = normalize_task_payload(
        updates,
        is_update=True,
        existing_task=existing_task,
    )
    if any(issue.field == "name" and issue.code == "required" for issue in issues):
        return False
    if "status" in updates and not can_transition_status(
        existing_task.get("status"), updates.get("status")
    ):
        return False
    if "status" in updates:
        if updates.get("status") == "completed":
            updates["is_completed"] = 1
            updates["completed_at"] = (
                updates.get("completed_at") or existing_task.get("completed_at") or _now_local_str()
            )
        else:
            updates["is_completed"] = 0
            updates["completed_at"] = None

    # period_start, period_end 재계산 필요 여부 확인 (routine 타입만)
    if "target_date" in updates or "cycle_type" in updates:
        cur.execute("SELECT target_date, cycle_type, type FROM unified_task WHERE id=?", (task_id,))
        row = cur.fetchone()
        if row and row["type"] == "routine":
            target_date = updates.get("target_date", row["target_date"])
            cycle_type = updates.get("cycle_type", row["cycle_type"])
            period_start, period_end = calculate_period_bounds(target_date, cycle_type)
            updates["period_start"] = period_start
            updates["period_end"] = period_end

    updates = dict(updates or {})
    updates["updated_at"] = _now_local_str()
    if mark_gcal_dirty is None:
        business_keys = set(updates.keys()) - _GCAL_META_ONLY_FIELDS
        if business_keys:
            updates["gcal_dirty"] = 1
    else:
        updates["gcal_dirty"] = 1 if mark_gcal_dirty else 0

    # 동적 UPDATE 쿼리 생성
    set_clause = ", ".join([f"{k}=?" for k in updates])
    values = list(updates.values()) + [task_id]

    try:
        cur.execute(f"UPDATE unified_task SET {set_clause} WHERE id=?", values)
        changed = cur.rowcount > 0
        conn.commit()
        return changed
    except Exception as e:
        logger.error(f"Error updating unified task: {e}")
        conn.rollback()
        return False


def mark_routine_completed(task_id):
    """일반업무 완료 처리"""
    conn = get_connection()
    if not conn:
        return False

    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        cur.execute(
            """
            UPDATE unified_task
            SET is_completed=1, completed_at=?, status='done'
            WHERE id=? AND type='routine'
        """,
            (now, task_id),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error marking routine completed: {e}")
        conn.rollback()
        return False


def mark_routine_incomplete(task_id):
    """일반업무 미완료 처리"""
    conn = get_connection()
    if not conn:
        return False

    cur = conn.cursor()

    try:
        cur.execute(
            """
            UPDATE unified_task
            SET is_completed=0, completed_at=NULL, status='in_progress'
            WHERE id=? AND type='routine'
        """,
            (task_id,),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error marking routine incomplete: {e}")
        conn.rollback()
        return False


# ==================== CRUD: Delete ====================


def delete_unified_task(task_id):
    """
    통합 task 삭제
    """
    conn = get_connection()
    if not conn:
        return False

    cur = conn.cursor()

    try:
        cur.execute("DELETE FROM task_checklist_link WHERE owner_id=?", (task_id,))
        cur.execute("DELETE FROM unified_task WHERE id=?", (task_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error deleting unified task: {e}")
        conn.rollback()
        return False


def delete_unified_tasks_by_series_id(series_id):
    """
    동일 series_id를 가진 모든 통합 task 및 체크리스트 관계 삭제
    """
    if not series_id:
        return False
    conn = get_connection()
    if not conn:
        return False

    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM unified_task WHERE series_id = ?", (series_id,))
        task_ids = [row[0] for row in cur.fetchall()]

        if task_ids:
            # placeholders 생성 (?, ?, ...)
            placeholders = ",".join("?" for _ in task_ids)
            cur.execute(
                f"DELETE FROM task_checklist_link WHERE owner_id IN ({placeholders})", task_ids
            )
            cur.execute("DELETE FROM unified_task WHERE series_id = ?", (series_id,))
            conn.commit()
            return True
        return False
    except Exception as e:
        logger.error(f"Error deleting unified tasks by series_id {series_id}: {e}")
        conn.rollback()
        return False


def _load_archive_snapshot(snapshot_json):
    if not snapshot_json:
        return {}
    try:
        parsed = json.loads(snapshot_json)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _serialize_snapshot_json(snapshot):
    if snapshot is None:
        return None
    if isinstance(snapshot, str):
        text = snapshot.strip()
        return text or None
    try:
        return json.dumps(snapshot, ensure_ascii=False, default=str)
    except Exception:
        try:
            return json.dumps(str(snapshot), ensure_ascii=False)
        except Exception:
            return None


def _archive_calendar_id_from_task(task: dict | None):
    task = task or {}
    return (
        str(
            task.get("gcal_source_calendar_id") or task.get("gcal_target_calendar_id") or ""
        ).strip()
        or None
    )


def move_task_to_trash(task_id, reason="manual_trash"):
    return archive_gcal_deleted_task(task_id, reason=reason)


def list_task_trash(task_type=None):
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM gcal_deleted_task_archive
            ORDER BY archived_at DESC, id DESC
            """
        )
        rows = []
        wanted_type = str(task_type or "").strip()
        for raw in cur.fetchall():
            archive_row = dict(raw)
            snapshot = _load_archive_snapshot(archive_row.get("snapshot_json"))
            task = snapshot.get("task") if isinstance(snapshot.get("task"), dict) else {}

            row_type = str(task.get("type") or "").strip() or "schedule"
            if wanted_type and row_type != wanted_type:
                continue

            rows.append(
                {
                    "id": archive_row.get("id"),
                    "original_task_id": archive_row.get("original_task_id"),
                    "type": row_type,
                    "name": task.get("name") or archive_row.get("name") or "",
                    "deadline": task.get("deadline") or archive_row.get("deadline") or "",
                    "end_date": task.get("end_date") or archive_row.get("end_date") or "",
                    "location": task.get("location") or archive_row.get("location") or "",
                    "assignee": task.get("assignee") or "",
                    "priority": task.get("priority") or "normal",
                    "status": task.get("status") or "pending",
                    "cycle_type": task.get("cycle_type"),
                    "target_date": task.get("target_date"),
                    "is_completed": task.get("is_completed", 0),
                    "completed_at": task.get("completed_at"),
                    "gcal_event_id": task.get("gcal_event_id")
                    or archive_row.get("gcal_event_id")
                    or "",
                    "gcal_calendar_id": _archive_calendar_id_from_task(task),
                    "archived_at": archive_row.get("archived_at"),
                    "archived_reason": archive_row.get("archived_reason") or "",
                }
            )
        return rows
    except Exception as e:
        logger.error(f"Error listing task trash: {e}")
        return []


def restore_task_from_trash(archive_id):
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM gcal_deleted_task_archive WHERE id=?", (archive_id,))
        row = cur.fetchone()
        if not row:
            return None
        archive_row = dict(row)
        snapshot = _load_archive_snapshot(archive_row.get("snapshot_json"))
        task = snapshot.get("task") if isinstance(snapshot.get("task"), dict) else {}
        checklist_items = (
            snapshot.get("checklist_items")
            if isinstance(snapshot.get("checklist_items"), list)
            else []
        )

        task_data = {
            "name": task.get("name") or archive_row.get("name") or "Untitled",
            "type": task.get("type") or "schedule",
            "priority": task.get("priority") or "normal",
            "status": task.get("status") or "pending",
            "deadline": task.get("deadline") or archive_row.get("deadline"),
            "end_date": task.get("end_date") or archive_row.get("end_date"),
            "alarm_time": task.get("alarm_time"),
            "recurrence": task.get("recurrence"),
            "template_id": task.get("template_id"),
            "target_date": task.get("target_date"),
            "cycle_type": task.get("cycle_type"),
            "bg_color": task.get("bg_color"),
            "icon": task.get("icon"),
            "description": task.get("description") or archive_row.get("description"),
            "memo": task.get("memo"),
            "location": task.get("location") or archive_row.get("location"),
            "assignee": task.get("assignee"),
            "all_day": int(bool(task.get("all_day") or archive_row.get("all_day"))),
            "gcal_event_id": task.get("gcal_event_id") or archive_row.get("gcal_event_id"),
            "gcal_dirty": task.get("gcal_dirty", 1),
            "gcal_last_synced_at": task.get("gcal_last_synced_at"),
            "gcal_remote_updated_at": task.get("gcal_remote_updated_at"),
            "gcal_sync_error": task.get("gcal_sync_error"),
        }

        new_task_id = create_unified_task(task_data, commit=False)
        if not new_task_id:
            conn.rollback()
            return None

        unified_cols = _table_columns(cur, "unified_task")
        extra_cols = []
        extra_values = []
        for col in (
            "gcal_source_calendar_id",
            "gcal_source_summary",
            "gcal_target_calendar_id",
            "gcal_sync_mode",
        ):
            if col in unified_cols:
                extra_cols.append(f"{col}=?")
                extra_values.append(task.get(col))
        if extra_cols:
            extra_cols.append("updated_at=?")
            extra_values.append(_now_local_str())
            extra_values.append(new_task_id)
            cur.execute(
                f"UPDATE unified_task SET {', '.join(extra_cols)} WHERE id=?",
                tuple(extra_values),
            )

        for item in checklist_items:
            if not isinstance(item, dict):
                continue
            item_text = str(item.get("item_text") or "").strip()
            if not item_text:
                continue
            cur.execute(
                """
                INSERT INTO task_checklist_link (
                    owner_type, owner_id, item_text, item_order, display_type, is_completed, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.get("owner_type") or task_data.get("type") or "schedule",
                    new_task_id,
                    item_text,
                    int(item.get("item_order") or 0),
                    item.get("display_type") or "list",
                    int(bool(item.get("is_completed", item.get("is_checked", 0)))),
                    item.get("completed_at") or item.get("checked_at"),
                ),
            )

        cur.execute("DELETE FROM gcal_deleted_task_archive WHERE id=?", (archive_id,))
        conn.commit()
        return new_task_id
    except Exception as e:
        logger.error(f"Error restoring task from trash: {e}")
        conn.rollback()
        return None


def purge_task_trash(archive_id):
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT gcal_event_id, snapshot_json FROM gcal_deleted_task_archive WHERE id=?",
            (archive_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        row = dict(row)
        snapshot = _load_archive_snapshot(row.get("snapshot_json"))
        task = snapshot.get("task") if isinstance(snapshot.get("task"), dict) else {}
        result = {
            "gcal_event_id": task.get("gcal_event_id") or row.get("gcal_event_id"),
            "gcal_calendar_id": _archive_calendar_id_from_task(task),
        }
        cur.execute("DELETE FROM gcal_deleted_task_archive WHERE id=?", (archive_id,))
        conn.commit()
        return result
    except Exception as e:
        logger.error(f"Error purging task trash item: {e}")
        conn.rollback()
        return None


def purge_task_trash_older_than(cutoff_datetime):
    conn = get_connection()
    if not conn:
        return 0
    try:
        if isinstance(cutoff_datetime, (int, float)):
            cutoff_datetime = (
                datetime.now() - timedelta(days=max(int(cutoff_datetime), 0))
            ).strftime("%Y-%m-%d %H:%M:%S")
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM gcal_deleted_task_archive WHERE datetime(archived_at) < datetime(?)",
            (cutoff_datetime,),
        )
        deleted = int(cur.rowcount or 0)
        conn.commit()
        return deleted
    except Exception as e:
        logger.error(f"Error purging old task trash items: {e}")
        conn.rollback()
        return 0


def is_gcal_event_in_task_trash(gcal_event_id, gcal_calendar_id=None):
    event_id = str(gcal_event_id or "").strip()
    if not event_id:
        return False
    conn = get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT gcal_event_id, snapshot_json FROM gcal_deleted_task_archive WHERE gcal_event_id=?",
            (event_id,),
        )
        rows = cur.fetchall()
        if not rows:
            return False
        target_calendar_id = str(gcal_calendar_id or "").strip()
        if not target_calendar_id:
            return True
        for raw in rows:
            row = dict(raw)
            snapshot = _load_archive_snapshot(row.get("snapshot_json"))
            task = snapshot.get("task") if isinstance(snapshot.get("task"), dict) else {}
            if _archive_calendar_id_from_task(task) == target_calendar_id:
                return True
        return False
    except Exception as e:
        logger.error(f"Error checking gcal event in task trash: {e}")
        return False


def purge_gcal_event_manual_trash(gcal_event_id, gcal_calendar_id=None):
    event_id = str(gcal_event_id or "").strip()
    if not event_id:
        return 0
    conn = get_connection()
    if not conn:
        return 0
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, snapshot_json FROM gcal_deleted_task_archive WHERE gcal_event_id=?",
            (event_id,),
        )
        rows = cur.fetchall()
        if not rows:
            return 0

        target_calendar_id = str(gcal_calendar_id or "").strip()
        purge_ids = []
        for raw in rows:
            row = dict(raw)
            if not target_calendar_id:
                purge_ids.append(row["id"])
                continue
            snapshot = _load_archive_snapshot(row.get("snapshot_json"))
            task = snapshot.get("task") if isinstance(snapshot.get("task"), dict) else {}
            if _archive_calendar_id_from_task(task) == target_calendar_id:
                purge_ids.append(row["id"])

        if not purge_ids:
            return 0

        placeholders = ",".join("?" for _ in purge_ids)
        cur.execute(
            f"DELETE FROM gcal_deleted_task_archive WHERE id IN ({placeholders})",
            tuple(purge_ids),
        )
        deleted = int(cur.rowcount or 0)
        conn.commit()
        return deleted
    except Exception as e:
        logger.error(f"Error purging manual Google trash rows: {e}")
        conn.rollback()
        return 0


def archive_gcal_deleted_task(
    local_task_id, gcal_event_id=None, reason="remote_deleted", commit=True
):
    conn = get_connection()
    if not conn or not local_task_id:
        return False
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM unified_task WHERE id=?", (local_task_id,))
        row = cur.fetchone()
        if not row:
            return False
        task = dict(row)
        cur.execute(
            """
            SELECT *
            FROM task_checklist_link
            WHERE owner_id=?
            ORDER BY item_order ASC, id ASC
            """,
            (local_task_id,),
        )
        checklist_rows = [dict(item) for item in cur.fetchall()]
        snapshot = {
            "task": task,
            "checklist_items": checklist_rows,
        }
        cur.execute(
            """
            INSERT INTO gcal_deleted_task_archive (
                original_task_id, gcal_event_id, name, deadline, end_date, description,
                location, all_day, archived_reason, snapshot_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                local_task_id,
                gcal_event_id or task.get("gcal_event_id"),
                task.get("name"),
                task.get("deadline"),
                task.get("end_date"),
                task.get("description"),
                task.get("location"),
                int(bool(task.get("all_day"))),
                str(reason or "remote_deleted")[:100],
                json.dumps(snapshot, ensure_ascii=True, default=str),
            ),
        )
        cur.execute("DELETE FROM task_checklist_link WHERE owner_id=?", (local_task_id,))
        cur.execute("DELETE FROM unified_task WHERE id=?", (local_task_id,))
        if commit:
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error archiving Google-deleted task: {e}")
        if commit:
            conn.rollback()
        return False


def list_gcal_subscriptions(include_inactive=True):
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        query = "SELECT * FROM gcal_subscription"
        params = ()
        if not include_inactive:
            query += " WHERE is_active=1"
        query += (
            " ORDER BY is_primary DESC, is_active DESC, lower(COALESCE(summary, calendar_id)) ASC"
        )
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"Error listing Google subscriptions: {e}")
        return []


def upsert_gcal_subscription(
    calendar_id,
    summary="",
    time_zone="",
    access_role="",
    is_primary=0,
    is_external=1,
    is_active=1,
    last_error=None,
    preserve_existing_active=False,
):
    conn = get_connection()
    if not conn or not calendar_id:
        return False
    try:
        cur = conn.cursor()
        now = _now_local_str()
        cur.execute(
            """
            INSERT INTO gcal_subscription (
                calendar_id, summary, time_zone, access_role, is_active, is_primary, is_external,
                last_error, last_seen_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(calendar_id) DO UPDATE SET
                summary=excluded.summary,
                time_zone=excluded.time_zone,
                access_role=excluded.access_role,
                is_primary=excluded.is_primary,
                is_external=excluded.is_external,
                is_active=CASE
                    WHEN ? THEN COALESCE(gcal_subscription.is_active, excluded.is_active)
                    ELSE excluded.is_active
                END,
                last_error=excluded.last_error,
                last_seen_at=excluded.last_seen_at,
                updated_at=excluded.updated_at
            """,
            (
                calendar_id,
                summary,
                time_zone,
                access_role,
                int(bool(is_active)),
                int(bool(is_primary)),
                int(bool(is_external)),
                last_error,
                now,
                now,
                now,
                int(bool(preserve_existing_active)),
            ),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error upserting Google subscription: {e}")
        conn.rollback()
        return False


def set_gcal_subscription_active(calendar_id, is_active):
    conn = get_connection()
    if not conn or not calendar_id:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE gcal_subscription
            SET is_active=?, updated_at=?
            WHERE calendar_id=?
            """,
            (int(bool(is_active)), _now_local_str(), calendar_id),
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Error updating Google subscription active flag: {e}")
        conn.rollback()
        return False


def delete_gcal_subscription(calendar_id):
    conn = get_connection()
    if not conn or not calendar_id:
        return False
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM gcal_subscription WHERE calendar_id=?", (calendar_id,))
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Error deleting Google subscription: {e}")
        conn.rollback()
        return False


# ==================== 구글 캘린더 삭제 큐 관리 ====================


def queue_gcal_sync_conflict(
    local_task_id,
    gcal_event_id,
    gcal_calendar_id=None,
    conflict_kind="remote_overwrite",
    local_snapshot=None,
    remote_snapshot=None,
    local_snapshot_json=None,
    remote_snapshot_json=None,
):
    conn = get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        local_snapshot_json = _serialize_snapshot_json(
            local_snapshot if local_snapshot_json is None else local_snapshot_json
        )
        remote_snapshot_json = _serialize_snapshot_json(
            remote_snapshot if remote_snapshot_json is None else remote_snapshot_json
        )
        normalized_calendar_id = str(gcal_calendar_id or "").strip() or None
        normalized_conflict_kind = (
            str(conflict_kind or "remote_overwrite").strip() or "remote_overwrite"
        )
        created_at = _now_local_str()

        cur.execute(
            """
            SELECT id
            FROM gcal_sync_conflict_queue
            WHERE COALESCE(is_resolved, 0) = 0
              AND COALESCE(local_task_id, 0) = COALESCE(?, 0)
              AND COALESCE(gcal_event_id, '') = COALESCE(?, '')
              AND COALESCE(gcal_calendar_id, '') = COALESCE(?, '')
              AND COALESCE(conflict_kind, 'remote_overwrite') = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (local_task_id, gcal_event_id, normalized_calendar_id, normalized_conflict_kind),
        )
        existing = cur.fetchone()

        if existing:
            cur.execute(
                """
                UPDATE gcal_sync_conflict_queue
                SET local_snapshot_json=?,
                    remote_snapshot_json=?,
                    created_at=?
                WHERE id=?
                """,
                (local_snapshot_json, remote_snapshot_json, created_at, existing["id"]),
            )
        else:
            cur.execute(
                """
                INSERT INTO gcal_sync_conflict_queue (
                    local_task_id, gcal_event_id, gcal_calendar_id, conflict_kind,
                    local_snapshot_json, remote_snapshot_json, is_resolved, resolution, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL, ?)
                """,
                (
                    local_task_id,
                    gcal_event_id,
                    normalized_calendar_id,
                    normalized_conflict_kind,
                    local_snapshot_json,
                    remote_snapshot_json,
                    created_at,
                ),
            )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error queueing Google sync conflict: {e}")
        conn.rollback()
        return False


def list_gcal_sync_conflicts(include_resolved=False, only_unresolved=None, limit=None):
    if only_unresolved is not None:
        include_resolved = not bool(only_unresolved)
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        query = "SELECT * FROM gcal_sync_conflict_queue"
        if not include_resolved:
            query += " WHERE COALESCE(is_resolved, 0) = 0"
        query += " ORDER BY id ASC"
        if limit and str(limit).isdigit():
            query += f" LIMIT {limit}"
        cur.execute(query)
        return [dict(row) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"Error listing Google sync conflicts: {e}")
        return []


def mark_gcal_sync_conflict_resolved(conflict_id, resolution):
    conn = get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE gcal_sync_conflict_queue
            SET is_resolved=1,
                resolution=?,
                resolved_at=?
            WHERE id=?
            """,
            (resolution or "resolved", _now_local_str(), conflict_id),
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Error resolving Google sync conflict: {e}")
        conn.rollback()
        return False


def queue_gcal_delete(gcal_event_id, gcal_calendar_id=None, local_task_id=None):
    if not gcal_event_id:
        return False
    conn = get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        queue_cols = _table_columns(cur, "gcal_delete_queue")
        has_calendar_col = "gcal_calendar_id" in queue_cols
        has_retry_col = "next_retry_at" in queue_cols

        normalized_calendar_id = str(gcal_calendar_id or "").strip() or None
        if not normalized_calendar_id and local_task_id:
            try:
                cur.execute(
                    "SELECT gcal_source_calendar_id, gcal_target_calendar_id "
                    "FROM unified_task WHERE id=?",
                    (local_task_id,),
                )
                row = cur.fetchone()
                if row:
                    normalized_calendar_id = (
                        str(
                            row["gcal_source_calendar_id"] or row["gcal_target_calendar_id"] or ""
                        ).strip()
                        or None
                    )
            except Exception:
                pass

        if has_calendar_col:
            cur.execute(
                "SELECT id FROM gcal_delete_queue "
                "WHERE gcal_event_id=? "
                "AND COALESCE(trim(gcal_calendar_id), '') = COALESCE(trim(?), '') "
                "LIMIT 1",
                (str(gcal_event_id), normalized_calendar_id),
            )
        else:
            cur.execute(
                "SELECT id FROM gcal_delete_queue WHERE gcal_event_id=? LIMIT 1",
                (str(gcal_event_id),),
            )
        existing = cur.fetchone()

        if existing:
            cur.execute(
                "UPDATE gcal_delete_queue SET local_task_id=COALESCE(?, local_task_id) WHERE id=?",
                (local_task_id, existing["id"]),
            )
            conn.commit()
            return True

        if has_retry_col and has_calendar_col:
            cur.execute(
                "INSERT INTO gcal_delete_queue (gcal_event_id, gcal_calendar_id, local_task_id, next_retry_at) "
                "VALUES (?, ?, ?, datetime('now', 'localtime'))",
                (str(gcal_event_id), normalized_calendar_id, local_task_id),
            )
        elif has_retry_col:
            cur.execute(
                "INSERT INTO gcal_delete_queue (gcal_event_id, local_task_id, next_retry_at) "
                "VALUES (?, ?, datetime('now', 'localtime'))",
                (str(gcal_event_id), local_task_id),
            )
        elif has_calendar_col:
            cur.execute(
                "INSERT INTO gcal_delete_queue (gcal_event_id, gcal_calendar_id, local_task_id) "
                "VALUES (?, ?, ?)",
                (str(gcal_event_id), normalized_calendar_id, local_task_id),
            )
        else:
            cur.execute(
                "INSERT INTO gcal_delete_queue (gcal_event_id, local_task_id) VALUES (?, ?)",
                (str(gcal_event_id), local_task_id),
            )
        conn.commit()
        return True
    except Exception:
        return False


def is_gcal_delete_queued(gcal_event_id, gcal_calendar_id=None):
    event_id = str(gcal_event_id or "").strip()
    if not event_id:
        return False
    conn = get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        queue_cols = _table_columns(cur, "gcal_delete_queue")
        if "gcal_calendar_id" in queue_cols:
            cur.execute(
                """
                SELECT 1
                FROM gcal_delete_queue
                WHERE gcal_event_id=?
                  AND COALESCE(trim(gcal_calendar_id), '') = COALESCE(trim(?), '')
                LIMIT 1
                """,
                (event_id, gcal_calendar_id),
            )
        else:
            cur.execute(
                "SELECT 1 FROM gcal_delete_queue WHERE gcal_event_id=? LIMIT 1", (event_id,)
            )
        return cur.fetchone() is not None
    except Exception as e:
        logger.error(f"Error checking Google delete queue: {e}")
        return False


def get_gcal_delete_queue():
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM gcal_delete_queue ORDER BY id ASC")
        return [dict(row) for row in cur.fetchall()]
    except Exception:
        return []


def get_gcal_delete_queue_ready(max_retry_count=5):
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        queue_cols = _table_columns(cur, "gcal_delete_queue")
        if "next_retry_at" in queue_cols:
            cur.execute(
                "SELECT * FROM gcal_delete_queue WHERE retry_count < ? AND (next_retry_at IS NULL OR datetime(next_retry_at) <= datetime('now', 'localtime')) ORDER BY id ASC",
                (max_retry_count,),
            )
        else:
            cur.execute(
                "SELECT * FROM gcal_delete_queue WHERE retry_count < ? ORDER BY id ASC",
                (max_retry_count,),
            )
        return [dict(row) for row in cur.fetchall()]
    except Exception:
        return []


def mark_gcal_delete_done(queue_id, *, commit=True):
    # commit kwarg accepted for engine API compatibility; this impl always
    # commits within the same call (chunk-level commits in the engine still
    # work because conn.commit is idempotent after a successful execute).
    conn = get_connection()
    if not conn:
        return False
    cur = conn.cursor()
    cur.execute("DELETE FROM gcal_delete_queue WHERE id=?", (queue_id,))
    if commit:
        conn.commit()
    return True


def mark_gcal_delete_failed(queue_id, error_message, *, commit=True):
    conn = get_connection()
    if not conn:
        return False
    cur = conn.cursor()
    queue_cols = _table_columns(cur, "gcal_delete_queue")
    if "next_retry_at" in queue_cols:
        cur.execute(
            "UPDATE gcal_delete_queue SET retry_count=retry_count+1, last_error=?, "
            "next_retry_at=datetime('now', 'localtime', '+5 minutes') WHERE id=?",
            (str(error_message)[:500], queue_id),
        )
    else:
        cur.execute(
            "UPDATE gcal_delete_queue SET retry_count=retry_count+1, last_error=? WHERE id=?",
            (str(error_message)[:500], queue_id),
        )
    if commit:
        conn.commit()
    return True


def clear_gcal_delete_queue_error(queue_id):
    conn = get_connection()
    if not conn:
        return False
    cur = conn.cursor()
    queue_cols = _table_columns(cur, "gcal_delete_queue")
    if "next_retry_at" in queue_cols:
        cur.execute(
            "UPDATE gcal_delete_queue "
            "SET last_error=NULL, retry_count=0, next_retry_at=datetime('now', 'localtime') "
            "WHERE id=?",
            (queue_id,),
        )
    else:
        cur.execute(
            "UPDATE gcal_delete_queue SET last_error=NULL, retry_count=0 WHERE id=?",
            (queue_id,),
        )
    conn.commit()
    return True


def force_remove_gcal_delete_queue(queue_id):
    return mark_gcal_delete_done(queue_id)


def clear_gcal_delete_queue():
    conn = get_connection()
    if not conn:
        return False
    cur = conn.cursor()
    cur.execute("DELETE FROM gcal_delete_queue")
    conn.commit()
    return True


# ==================== 체크리스트 관리 ====================


def add_checklist_item(owner_id, item_text, item_order=0, display_type=None):
    """
    체크리스트 항목 추가
    """

    conn = get_connection()
    if not conn:
        return None

    cur = conn.cursor()

    cur.execute("SELECT type FROM unified_task WHERE id=?", (owner_id,))
    row = cur.fetchone()
    if not row:
        return None

    owner_type = row["type"]

    try:
        cur.execute(
            """
            INSERT INTO task_checklist_link
            (owner_type, owner_id, item_text, item_order, display_type)
            VALUES (?, ?, ?, ?, ?)
        """,
            (owner_type, owner_id, item_text, item_order, display_type),
        )

        link_id = cur.lastrowid
        conn.commit()
        return link_id
    except Exception as e:
        logger.error(f"Error adding checklist item: {e}")
        conn.rollback()
        return None


def toggle_checklist_item(link_id):
    """체크리스트 항목 완료/미완료 토글"""
    conn = get_connection()
    if not conn:
        return False

    cur = conn.cursor()

    try:
        cur.execute(
            """
            UPDATE task_checklist_link
            SET is_completed = 1 - is_completed,
                completed_at = CASE
                    WHEN is_completed=0 THEN datetime('now', 'localtime')
                    ELSE NULL
                END
            WHERE id=?
        """,
            (link_id,),
        )

        changed = cur.rowcount > 0
        conn.commit()
        return changed
    except Exception as e:
        logger.error(f"Error toggling checklist item: {e}")
        conn.rollback()
        return False


def reset_checklist_items(owner_id):
    """체크리스트 항목 전체 초기화 (is_completed=0, completed_at=NULL)"""
    conn = get_connection()
    if not conn:
        return False
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE task_checklist_link SET is_completed=0, completed_at=NULL WHERE owner_id=?",
            (owner_id,),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error resetting checklist items: {e}")
        conn.rollback()
        return False


def get_task_checklist_items(owner_id):
    """
    특정 task의 체크리스트 항목 조회
    """
    conn = get_connection()
    if not conn:
        return []

    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, item_text, item_order, is_completed, completed_at, display_type
        FROM task_checklist_link
        WHERE owner_id=?
        ORDER BY item_order
    """,
        (owner_id,),
    )

    rows = cur.fetchall()
    return [dict(row) for row in rows]


def get_task_checklist_items_for_owners(owner_ids):
    normalized_ids = []
    seen_ids = set()
    for owner_id in owner_ids or []:
        if owner_id is None or owner_id in seen_ids:
            continue
        normalized_ids.append(owner_id)
        seen_ids.add(owner_id)

    if not normalized_ids:
        return {}

    conn = get_connection()
    if not conn:
        return {}

    placeholders = ", ".join("?" for _ in normalized_ids)
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT id, owner_id, item_text, item_order, is_completed, completed_at, display_type
        FROM task_checklist_link
        WHERE owner_id IN ({placeholders})
        ORDER BY owner_id, item_order
    """,
        tuple(normalized_ids),
    )

    rows = cur.fetchall()
    from collections import defaultdict

    result = defaultdict(list)
    for row in rows:
        result[row["owner_id"]].append(dict(row))
    return result


def set_task_checklist_display_type(owner_id, display_type):
    conn = get_connection()
    if not conn:
        return False

    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE task_checklist_link SET display_type=? WHERE owner_id=?",
            (display_type, owner_id),
        )
        changed = cur.rowcount > 0
        conn.commit()
        return changed
    except Exception as e:
        logger.error(f"Error setting display type: {e}")
        conn.rollback()
        return False


def get_task_checklist_progress(task_id):
    conn = get_connection()
    if not conn:
        return {"total": 0, "completed": 0}

    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN is_completed=1 THEN 1 ELSE 0 END) as completed
        FROM task_checklist_link
        WHERE owner_id=?
    """,
        (task_id,),
    )

    row = cur.fetchone()
    return {"total": row["total"] or 0, "completed": row["completed"] or 0}


def get_template_checklist_progress(template_id, target_date):
    conn = get_connection()
    if not conn:
        return {"total": 0, "completed": 0}

    cur = conn.cursor()
    cur.execute(
        """
        SELECT id FROM unified_task
        WHERE type='routine'
          AND template_id=?
          AND date(target_date)=date(?)
    """,
        (template_id, target_date),
    )

    task_ids = [row["id"] for row in cur.fetchall()]

    if not task_ids:
        return {"total": 0, "completed": 0}

    placeholders = ",".join("?" * len(task_ids))
    cur.execute(
        f"""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN is_completed=1 THEN 1 ELSE 0 END) as completed
        FROM task_checklist_link
        WHERE owner_id IN ({placeholders})
    """,
        task_ids,
    )

    row = cur.fetchone()
    return {"total": row["total"] or 0, "completed": row["completed"] or 0}


# ==================== 템플릿 관리 ====================


def get_routine_templates(active_only=True):
    conn = get_connection()
    if not conn:
        return []

    cur = conn.cursor()
    if active_only:
        cur.execute("SELECT * FROM routine_template WHERE is_active=1 ORDER BY name")
    else:
        cur.execute("SELECT * FROM routine_template ORDER BY name")

    rows = cur.fetchall()
    return [dict(row) for row in rows]


def get_routine_template(template_id):
    conn = get_connection()
    if not conn:
        return None

    cur = conn.cursor()
    cur.execute("SELECT * FROM routine_template WHERE id=?", (template_id,))
    row = cur.fetchone()
    return dict(row) if row else None


# ==================== 검색 및 통계 ====================


def search_unified_tasks(keyword, task_type=None):
    conn = get_connection()
    if not conn:
        return []

    cur = conn.cursor()
    query = "SELECT * FROM unified_task WHERE (name LIKE ? OR description LIKE ? OR memo LIKE ?)"
    params = [f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"]

    if task_type:
        query += " AND type=?"
        params.append(task_type)

    query += " ORDER BY deadline DESC"
    cur.execute(query, params)
    rows = cur.fetchall()
    return [dict(row) for row in rows]


def get_all_tasks_by_date(date_str, hide_gcal_items=False):
    conn = get_connection()
    if not conn:
        return []

    cur = conn.cursor()
    # 일정도 포함하도록 type='schedule' 필터 유지
    filters = [
        "(date(t.deadline) = date(?) OR date(t.target_date) = date(?))",
        "(c.is_visible IS NULL OR c.is_visible = 1)",
    ]
    params = [date_str, date_str]
    if hide_gcal_items:
        filters.append("(c.type IS NULL OR c.type != 'gcal')")
    query = f"""
        SELECT t.*
        FROM unified_task t
        LEFT JOIN calendar c ON t.calendar_id = c.id
        WHERE {" AND ".join(filters)}
        ORDER BY t.priority ASC, t.deadline ASC
    """
    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    return [dict(row) for row in rows]


def _apply_checklist_progress(task_dict):
    prog = get_task_checklist_progress(task_dict["id"])
    task_dict["progress"] = prog
    task_dict["checklist_total"] = prog["total"]
    task_dict["checklist_completed"] = prog["completed"]


def get_checklist_progress_for_owners(owner_ids):
    """여러 task의 체크리스트 진행률을 단일 쿼리로 조회 (N+1 방지)."""
    ids = []
    seen_ids = set()
    for oid in owner_ids or []:
        if oid is None or oid in seen_ids:
            continue
        ids.append(oid)
        seen_ids.add(oid)
    if not ids:
        return {}
    conn = get_connection()
    if not conn:
        return {}
    cur = conn.cursor()
    placeholders = ",".join("?" * len(ids))
    cur.execute(
        f"""
        SELECT owner_id,
            COUNT(*) as total,
            SUM(CASE WHEN is_completed=1 THEN 1 ELSE 0 END) as completed
        FROM task_checklist_link
        WHERE owner_id IN ({placeholders})
        GROUP BY owner_id
        """,
        tuple(ids),
    )
    result = {}
    for row in cur.fetchall():
        result[row["owner_id"]] = {"total": row["total"] or 0, "completed": row["completed"] or 0}
    return result


def _resolved_primary_gcal_id_for_query():
    try:
        from PyQt6.QtCore import QSettings

        from calendar_app.app_paths import APP_NAME, APP_VENDOR

        settings = QSettings(APP_VENDOR, APP_NAME)
        resolved = str(settings.value("gcal_primary_resolved_id", "") or "").strip()
        if resolved and resolved != "primary":
            return resolved
    except Exception:
        pass
    return "primary"


def _canonical_gcal_calendar_id_for_query(calendar_id):
    cid = str(calendar_id or "").strip()
    if cid.startswith("gcal::"):
        cid = cid[len("gcal::") :]
    if not cid:
        cid = "primary"
    if cid == "primary":
        resolved = _resolved_primary_gcal_id_for_query()
        if resolved and resolved != "primary":
            return resolved
    return cid


def _gcal_row_dedupe_key(task):
    event_id = str(task.get("gcal_event_id") or "").strip()
    if not event_id:
        return ("local", task.get("id"))
    raw_calendar_id = (
        task.get("gcal_source_calendar_id")
        or task.get("gcal_target_calendar_id")
        or task.get("calendar_id")
        or "primary"
    )
    return ("gcal", _canonical_gcal_calendar_id_for_query(raw_calendar_id), event_id)


def _gcal_row_priority(task):
    source_id = str(task.get("gcal_source_calendar_id") or "").strip()
    target_id = str(task.get("gcal_target_calendar_id") or "").strip()
    calendar_id = str(task.get("calendar_id") or "").strip()
    uses_primary_alias = (
        source_id == "primary" or target_id == "primary" or calendar_id == "gcal::primary"
    )
    sync_mode = str(task.get("gcal_sync_mode") or "").strip()
    try:
        row_id = int(task.get("id") or 0)
    except Exception:
        row_id = 0
    return (
        1 if uses_primary_alias else 0,
        0 if sync_mode == "remote_mirror" else 1,
        -row_id,
    )


def _dedupe_gcal_schedule_rows(tasks):
    deduped = {}
    passthrough = []
    for task in tasks:
        if not str(task.get("gcal_event_id") or "").strip():
            passthrough.append(task)
            continue
        key = _gcal_row_dedupe_key(task)
        current = deduped.get(key)
        if current is None or _gcal_row_priority(task) < _gcal_row_priority(current):
            deduped[key] = task
    result = [*passthrough, *deduped.values()]
    result.sort(key=lambda item: (str(item.get("deadline") or ""), int(item.get("id") or 0)))
    return result


def _apply_checklist_progress_batch(tasks):
    """task 목록에 진행률을 배치로 주입 (개별 쿼리 없음)."""
    prog_map = get_checklist_progress_for_owners([t["id"] for t in tasks])
    for t in tasks:
        prog = prog_map.get(t["id"]) or {"total": 0, "completed": 0}
        t["progress"] = prog
        t["checklist_total"] = prog["total"]
        t["checklist_completed"] = prog["completed"]


def get_all_tasks_by_date_with_progress(date_str, hide_gcal_items=False):
    tasks = get_all_tasks_by_date(date_str, hide_gcal_items=hide_gcal_items)
    _apply_checklist_progress_batch(tasks)
    return tasks


def get_tasks_by_type_with_progress(task_type, date_filter=None, status_filter=None):
    tasks = get_tasks_by_type(task_type, date_filter, status_filter)
    _apply_checklist_progress_batch(tasks)
    return tasks


def get_schedule_tasks_overlapping_range_with_progress(
    start_date_str,
    end_date_str,
    hide_gcal_items=False,
):
    conn = get_connection()
    if not conn:
        return []

    cur = conn.cursor()
    filters = [
        "("
        "t.type='schedule' OR "
        "(COALESCE(t.gcal_sync_mode, '') = 'remote_mirror' "
        "AND COALESCE(trim(t.gcal_event_id), '') != '')"
        ")",
        "(c.is_visible IS NULL OR c.is_visible = 1)",
        # deadline 이 NULL 인 일정은 target_date 로 대체하여 범위 비교 (NULL 비교 누락 방지)
        "date(COALESCE(t.deadline, t.target_date)) <= date(?)",
        "date(COALESCE(t.end_date, t.deadline, t.target_date)) >= date(?)",
    ]
    params = [end_date_str, start_date_str]
    if hide_gcal_items:
        filters.append("(c.type IS NULL OR c.type != 'gcal')")
    query = f"""
        SELECT t.* FROM unified_task t
        LEFT JOIN calendar c ON t.calendar_id = c.id
        WHERE {" AND ".join(filters)}
        ORDER BY t.deadline ASC
    """
    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    tasks = [dict(row) for row in rows]
    tasks = _dedupe_gcal_schedule_rows(tasks)
    _apply_checklist_progress_batch(tasks)
    return tasks


def get_routine_completion_stats(cycle_type, start_date, end_date):
    conn = get_connection()
    if not conn:
        return {"total": 0, "completed": 0, "completion_rate": 0.0}

    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN is_completed=1 THEN 1 ELSE 0 END) as completed
        FROM unified_task
        WHERE type='routine'
          AND cycle_type=?
          AND date(target_date) BETWEEN date(?) AND date(?)
    """,
        (cycle_type, start_date, end_date),
    )

    row = cur.fetchone()
    total = row["total"] or 0
    completed = row["completed"] or 0
    rate = (completed / total * 100) if total > 0 else 0.0

    return {"total": total, "completed": completed, "completion_rate": round(rate, 1)}


# ==================== 기타 헬퍼 ====================


def update_unified_task_duration(task_id, minutes):
    conn = get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute("SELECT deadline FROM unified_task WHERE id=?", (task_id,))
        row = cur.fetchone()
        if row and row["deadline"]:
            start_dt = datetime.strptime(row["deadline"][:16], "%Y-%m-%d %H:%M")
            end_dt = start_dt + timedelta(minutes=minutes)
            end_str = end_dt.strftime("%Y-%m-%d %H:%M")
            cur.execute(
                "UPDATE unified_task SET end_date=?, updated_at=?, gcal_dirty=1 WHERE id=?",
                (end_str, _now_local_str(), task_id),
            )
            conn.commit()
            return True
    except Exception:
        pass
    return False


def mark_unified_task_gcal_synced(
    task_id,
    event_id=None,
    commit=True,
    source_calendar_id=None,
    source_calendar_summary=None,
    target_calendar_id=None,
):
    conn = get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        now_local = _now_local_str()
        now_utc = _now_utc_iso()
        columns = _table_columns(cur, "unified_task")

        source_calendar_id = str(source_calendar_id or "").strip() or None
        source_calendar_summary = str(source_calendar_summary or "").strip() or None
        target_calendar_id = str(target_calendar_id or "").strip() or source_calendar_id

        sets = [
            "gcal_dirty=0",
            "gcal_last_synced_at=?",
            "gcal_remote_updated_at=?",
            "gcal_sync_error=NULL",
            "updated_at=?",
        ]
        params = [now_utc, now_utc, now_local]

        if event_id is not None:
            sets.insert(0, "gcal_event_id=?")
            params.insert(0, event_id)
        if "gcal_source_calendar_id" in columns and source_calendar_id:
            sets.append("gcal_source_calendar_id=?")
            params.append(source_calendar_id)
        if "gcal_source_summary" in columns and source_calendar_summary:
            sets.append("gcal_source_summary=?")
            params.append(source_calendar_summary)
        if "gcal_target_calendar_id" in columns and target_calendar_id:
            sets.append("gcal_target_calendar_id=?")
            params.append(target_calendar_id)

        sql = f"UPDATE unified_task SET {', '.join(sets)} WHERE id=?"
        params.append(task_id)
        cur.execute(sql, tuple(params))
        if commit:
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error marking unified task synced: {e}")
        conn.rollback()
        return False


def mark_unified_task_gcal_failed(task_id, error_message, commit=True):
    conn = get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE unified_task
            SET gcal_sync_error=?, updated_at=?
            WHERE id=?
            """,
            (str(error_message or "")[:500], _now_local_str(), task_id),
        )
        if commit:
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error marking unified task sync failure: {e}")
        conn.rollback()
        return False


def clear_unified_task_gcal_error(task_id):
    conn = get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE unified_task
            SET gcal_sync_error=NULL, updated_at=?
            WHERE id=?
            """,
            (_now_local_str(), task_id),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error clearing unified task sync failure: {e}")
        conn.rollback()
        return False


def count_unified_task_gcal_errors():
    conn = get_connection()
    if not conn:
        return 0
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM unified_task
            WHERE gcal_sync_error IS NOT NULL
              AND trim(gcal_sync_error) != ''
            """
        )
        row = cur.fetchone()
        return int((row["cnt"] if row else 0) or 0)
    except Exception as e:
        logger.error(f"Error counting unified task sync failures: {e}")
        return 0


def count_gcal_delete_queue_errors():
    conn = get_connection()
    if not conn:
        return 0
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM gcal_delete_queue
            WHERE last_error IS NOT NULL
              AND trim(last_error) != ''
            """
        )
        row = cur.fetchone()
        return int((row["cnt"] if row else 0) or 0)
    except Exception as e:
        logger.error(f"Error counting Google delete queue failures: {e}")
        return 0


def count_gcal_sync_conflicts():
    conn = get_connection()
    if not conn:
        return 0
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM gcal_sync_conflict_queue
            WHERE resolved_at IS NULL
            """
        )
        row = cur.fetchone()
        return int((row["cnt"] if row else 0) or 0)
    except Exception as e:
        logger.error(f"Error counting Google sync conflicts: {e}")
        return 0


def get_unified_task_gcal_errors():
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, deadline, gcal_sync_error, gcal_dirty, gcal_event_id
            FROM unified_task
            WHERE gcal_sync_error IS NOT NULL
              AND trim(gcal_sync_error) != ''
              AND type != 'routine'
            """
        )
        return [dict(row) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"Error loading unified task sync failures: {e}")
        return []


def delete_all_tasks_by_date(date_str):
    conn = get_connection()
    if not conn:
        return 0
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id
            FROM unified_task
            WHERE type='schedule'
              AND (
                date(deadline) = date(?)
                OR (deadline IS NULL AND date(target_date) = date(?))
              )
            """,
            (date_str, date_str),
        )
        task_ids = [int(row["id"]) for row in cur.fetchall()]
        if not task_ids:
            return 0
        placeholders = ",".join("?" for _ in task_ids)
        cur.execute(
            f"DELETE FROM task_checklist_link WHERE owner_id IN ({placeholders})",
            tuple(task_ids),
        )
        cur.execute(
            f"DELETE FROM unified_task WHERE id IN ({placeholders})",
            tuple(task_ids),
        )
        deleted = int(cur.rowcount or 0)
        conn.commit()
        return deleted
    except Exception as e:
        logger.error(f"Error deleting tasks by date: {e}")
        conn.rollback()
        return 0


# ==================== 지시사항 관련 (필요시) ====================


def get_directives_by_date(date_str):
    conn = get_connection()
    if not conn:
        return []
    cur = conn.cursor()
    cur.execute("SELECT * FROM task_directive WHERE date(deadline) = date(?)", (date_str,))
    rows = cur.fetchall()
    return [dict(row) for row in rows]


# ==================== 알람 관련 (Fired Alarms Persistence) ====================


def cleanup_fired_alarms(days: int = 90) -> int:
    """Delete stale fired alarm rows to keep restart dedupe state small."""
    conn = get_connection()
    if not conn:
        return 0
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(fired_alarms)")
        columns = {row[1] for row in cur.fetchall()}
        if "fired_at" not in columns:
            return 0
        cutoff = datetime.now() - timedelta(days=max(int(days or 0), 0))
        cur.execute(
            "DELETE FROM fired_alarms WHERE datetime(fired_at) < datetime(?)",
            (cutoff.strftime("%Y-%m-%d %H:%M:%S"),),
        )
        deleted = cur.rowcount or 0
        conn.commit()
        return int(deleted)
    except Exception as e:
        logger.error(f"Error cleaning up fired alarms: {e}")
        conn.rollback()
        return 0


def record_fired_alarm(task_id: int, offset_mins: int) -> bool:
    """Record that an alarm has fired to prevent duplicates on restart."""
    conn = get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO fired_alarms (task_id, offset_mins) VALUES (?, ?)",
            (task_id, offset_mins),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error recording fired alarm: {e}")
        conn.rollback()
        return False


def get_fired_alarms() -> list[dict]:
    """Return all persistently recorded fired alarms."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute("SELECT task_id, offset_mins FROM fired_alarms")
        return [dict(row) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"Error loading fired alarms: {e}")
        return []


def delete_fired_alarms_for_task(task_id: int) -> bool:
    """Delete all fired alarm records for a specific task (e.g. when completed)."""
    conn = get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM fired_alarms WHERE task_id=?", (task_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error clearing fired alarms for task {task_id}: {e}")
        conn.rollback()
        return False
