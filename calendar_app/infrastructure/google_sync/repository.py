from datetime import UTC, datetime

from PyQt6.QtCore import QSettings

from calendar_app.app_paths import APP_NAME, APP_VENDOR
from calendar_app.infrastructure.db import task_repo
from calendar_app.infrastructure.db.database_unified import db_manager, logger
from calendar_app.infrastructure.google_sync.common import (
    normalize_calendar_id as _normalize_calendar_id,
)


def _now_utc_iso():
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolved_primary_calendar_id():
    try:
        settings = QSettings(APP_VENDOR, APP_NAME)
        resolved = _normalize_calendar_id(settings.value("gcal_primary_resolved_id", "") or "")
        if resolved and resolved != "primary":
            return resolved
    except Exception:
        pass

    return "primary"


def _canonical_lookup_calendar_id(calendar_id):
    normalized = _normalize_calendar_id(calendar_id)
    if normalized == "primary":
        default_calendar_id = _resolved_primary_calendar_id()
        if default_calendar_id and default_calendar_id != "primary":
            return default_calendar_id
    return normalized


def make_gcal_event_lookup_key(calendar_id, event_id):
    return f"{_canonical_lookup_calendar_id(calendar_id)}::{str(event_id or '').strip()}"


def get_connection():
    return db_manager.get_connection()


def _lookup_row_raw_calendar_ids(row):
    ids = []
    source_calendar_id = _normalize_calendar_id(row["gcal_source_calendar_id"])
    target_calendar_id = _normalize_calendar_id(row["gcal_target_calendar_id"])
    if source_calendar_id:
        ids.append(source_calendar_id)
    if target_calendar_id and target_calendar_id not in ids:
        ids.append(target_calendar_id)
    if not ids:
        ids.append(_resolved_primary_calendar_id())
    return ids


def _lookup_row_priority(row, canonical_calendar_id):
    raw_ids = _lookup_row_raw_calendar_ids(row)
    explicit_calendar_id = str(row["calendar_id"] or "").strip()
    explicit_gcal_calendar_id = (
        explicit_calendar_id[len("gcal::") :] if explicit_calendar_id.startswith("gcal::") else ""
    )
    has_canonical_link = (
        canonical_calendar_id in raw_ids or explicit_gcal_calendar_id == canonical_calendar_id
    )
    uses_primary_alias = "primary" in raw_ids or explicit_gcal_calendar_id == "primary"
    sync_mode = str(row["gcal_sync_mode"] or "").strip().lower()
    try:
        row_id = int(row["id"])
    except Exception:
        row_id = 0
    return (
        0 if has_canonical_link and canonical_calendar_id != "primary" else 1,
        0 if not uses_primary_alias else 1,
        0 if sync_mode == "remote_mirror" else 1,
        -row_id,
    )


def _choose_lookup_row(rows, canonical_calendar_id):
    if not rows:
        return None
    return min(rows, key=lambda row: _lookup_row_priority(row, canonical_calendar_id))


def _has_legacy_gcal_rows(cur):
    return False


def cleanup_duplicate_gcal_rows():
    conn = get_connection()
    if not conn:
        return 0

    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, gcal_event_id, gcal_source_calendar_id, gcal_target_calendar_id,
                   gcal_sync_mode, calendar_id
            FROM unified_task
            WHERE gcal_event_id IS NOT NULL
              AND trim(gcal_event_id) != ''
            ORDER BY id ASC
            """
        )
        rows = [dict(row) for row in cur.fetchall()]
        if not rows:
            return 0

        grouped = {}
        for row in rows:
            event_id = str(row["gcal_event_id"] or "").strip()
            if not event_id:
                continue
            for raw_calendar_id in _lookup_row_raw_calendar_ids(row):
                key = make_gcal_event_lookup_key(raw_calendar_id, event_id)
                grouped.setdefault(key, []).append(row)

        delete_ids = set()
        for key, dup_rows in grouped.items():
            unique_rows = {int(row["id"]): row for row in dup_rows}
            if len(unique_rows) <= 1:
                continue
            canonical_calendar_id = key.split("::", 1)[0]
            keep_row = _choose_lookup_row(list(unique_rows.values()), canonical_calendar_id)
            keep_id = int(keep_row["id"]) if keep_row else None
            for row_id, _row in unique_rows.items():
                if keep_id is None or row_id == keep_id:
                    continue
                # BUG-P02: previously only remote_mirror rows were cleaned up;
                # local_owned / unknown duplicates accumulated indefinitely.
                # Now all sync_mode values are eligible for deduplication.
                delete_ids.add(row_id)

        if not delete_ids:
            return 0

        placeholders = ",".join("?" for _ in delete_ids)
        cur.execute(
            f"DELETE FROM task_checklist_link WHERE owner_id IN ({placeholders})",
            tuple(sorted(delete_ids)),
        )
        cur.execute(
            f"DELETE FROM unified_task WHERE id IN ({placeholders})",
            tuple(sorted(delete_ids)),
        )
        conn.commit()
        return int(len(delete_ids))
    except Exception as e:
        logger.error(f"Error cleaning duplicate gcal rows: {e}")
        conn.rollback()
        return 0


def get_all_gcal_tasks_map():
    """
    unified_task에서 gcal_event_id가 있는 항목을 찾아
    { gcal_id: (table_name, local_id) } 맵을 반환합니다.
    """
    conn = get_connection()
    if not conn:
        return {}

    mapping = {}
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, gcal_event_id, gcal_source_calendar_id, gcal_target_calendar_id,
                   gcal_sync_mode, calendar_id
            FROM unified_task
            WHERE gcal_event_id IS NOT NULL
              AND trim(gcal_event_id) != ''
              AND type != 'routine'
            """
        )
        rows = [dict(row) for row in cur.fetchall()]
        grouped = {}
        event_groups = {}
        for row in rows:
            event_id = str(row["gcal_event_id"] or "").strip()
            if not event_id:
                continue

            for calendar_id in _lookup_row_raw_calendar_ids(row):
                key = make_gcal_event_lookup_key(calendar_id, event_id)
                canonical_calendar_id = key.split("::", 1)[0]
                current = grouped.get(key)
                if current is None:
                    grouped[key] = row
                    continue
                if _lookup_row_priority(row, canonical_calendar_id) < _lookup_row_priority(
                    current, canonical_calendar_id
                ):
                    grouped[key] = row

        for key, row in grouped.items():
            info = ("unified_task", row["id"])
            mapping[key] = info
            event_id = str(row["gcal_event_id"] or "").strip()
            event_groups.setdefault(event_id, set()).add(info)

        for event_id, infos in event_groups.items():
            if len(infos) == 1:
                mapping[event_id] = next(iter(infos))

    except Exception as e:
        logger.error(f"Error building gcal map: {e}")

    return mapping


def update_task_from_gcal(
    table,
    local_id,
    summary,
    start_str,
    end_str,
    description="",
    location="",
    all_day=0,
    bg_color=None,
    remote_updated_at=None,
    gcal_event_id=None,
    source_calendar_id=None,
    source_calendar_summary=None,
    target_calendar_id=None,
    commit=True,
):
    """
    Google Calendar에서 가져온 정보로 로컬 DB를 업데이트합니다.
    """
    conn = get_connection()
    if not conn:
        return False

    cur = conn.cursor()
    try:
        if table != "unified_task":
            return False

        # calendar_id = "gcal::{source_calendar_id}" 로 자동 연결
        cal_db_id = f"gcal::{source_calendar_id}" if source_calendar_id else None
        cur.execute(
            """
            UPDATE unified_task
            SET name=?, deadline=?, end_date=?, description=?, location=?, target_date=?, all_day=?, bg_color=?,
                gcal_event_id=COALESCE(?, gcal_event_id),
                gcal_source_calendar_id=?, gcal_source_summary=?,
                gcal_target_calendar_id=COALESCE(?, gcal_target_calendar_id),
                calendar_id=COALESCE(?, calendar_id),
                gcal_sync_mode='remote_mirror',
                gcal_dirty=0, gcal_last_synced_at=?,
                gcal_remote_updated_at=?, gcal_sync_error=NULL, updated_at=datetime('now', 'localtime')
            WHERE id=?
        """,
            (
                summary,
                start_str,
                end_str,
                description,
                location,
                start_str[:10],
                int(bool(all_day)),
                bg_color,
                gcal_event_id,
                source_calendar_id,
                source_calendar_summary,
                target_calendar_id,
                cal_db_id,
                _now_utc_iso(),
                remote_updated_at,
                local_id,
            ),
        )

        if commit:
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error updating task from gcal: {e}")
        if commit:
            conn.rollback()
        return False


def insert_gcal_event_to_unified(
    summary,
    start_str,
    end_str,
    gcal_id,
    description="",
    location="",
    all_day=0,
    bg_color=None,
    remote_updated_at=None,
    source_calendar_id=None,
    source_calendar_summary=None,
    target_calendar_id=None,
    commit=True,
):
    """새로운 Google Calendar 이벤트를 unified_task에 추가합니다."""
    conn = get_connection()
    if conn and gcal_id:
        try:
            cur = conn.cursor()
            normalized_source = _canonical_lookup_calendar_id(source_calendar_id)
            cur.execute(
                """
                SELECT id, gcal_event_id, gcal_source_calendar_id, gcal_target_calendar_id,
                       gcal_sync_mode, calendar_id
                FROM unified_task
                WHERE gcal_event_id=?
                """,
                (gcal_id,),
            )
            matches = [dict(row) for row in cur.fetchall()]
            row = None
            if matches:
                exact_matches = []
                for match in matches:
                    match_ids = {
                        _canonical_lookup_calendar_id(match.get("gcal_source_calendar_id")),
                        _canonical_lookup_calendar_id(match.get("gcal_target_calendar_id")),
                    }
                    explicit_calendar_id = str(match.get("calendar_id") or "").strip()
                    if explicit_calendar_id.startswith("gcal::"):
                        match_ids.add(
                            _canonical_lookup_calendar_id(explicit_calendar_id[len("gcal::") :])
                        )
                    if normalized_source in match_ids:
                        exact_matches.append(match)
                candidate_rows = exact_matches or matches
                # BUG-P01: always pick the best row via _choose_lookup_row regardless
                # of how many candidates exist. Previously, multiple non-exact matches
                # fell through to a new insert, creating duplicate local rows.
                row = _choose_lookup_row(candidate_rows, normalized_source)
            if row:
                updated = update_task_from_gcal(
                    "unified_task",
                    int(row["id"]),
                    summary,
                    start_str,
                    end_str,
                    description,
                    location,
                    all_day,
                    bg_color,
                    remote_updated_at,
                    source_calendar_id=source_calendar_id,
                    source_calendar_summary=source_calendar_summary,
                    target_calendar_id=target_calendar_id or source_calendar_id,
                    commit=commit,
                )
                return int(row["id"]) if updated else False
        except Exception as e:
            logger.error(f"Error upserting gcal unified event: {e}")
            if commit:
                conn.rollback()

    task_data = {
        "name": summary,
        "type": "schedule",
        "priority": "normal",
        "status": "pending",
        "deadline": start_str,
        "end_date": end_str,
        "target_date": start_str[:10],
        "bg_color": bg_color,
        "icon": "",
        "description": description,
        "location": location,
        "all_day": int(bool(all_day)),
        "gcal_event_id": gcal_id,
        "gcal_source_calendar_id": source_calendar_id,
        "gcal_source_summary": source_calendar_summary,
        "gcal_target_calendar_id": target_calendar_id or source_calendar_id,
        "gcal_sync_mode": "remote_mirror",
        "gcal_dirty": 0,
        "gcal_last_synced_at": _now_utc_iso(),
        "gcal_remote_updated_at": remote_updated_at,
        "calendar_id": f"gcal::{source_calendar_id}" if source_calendar_id else None,
    }
    # task_repo.create_unified_task also commits, but we cannot easily make it optional without editing it too.
    # However, it only creates a few tasks per sync (the rest are updates).
    return task_repo.create_unified_task(task_data, commit=commit)


def find_unlinked_unified_task_for_gcal_payload(
    summary,
    start_str,
    end_str,
    all_day=0,
    source_calendar_id=None,
):
    """
    Find a local row that matches remote payload but has no gcal_event_id yet.
    Used to relink rows detached by previous sync failures without creating duplicates.
    """
    conn = get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        has_sync_mode = False
        try:
            cur.execute("PRAGMA table_info(unified_task)")
            has_sync_mode = any(
                (row[1] if isinstance(row, tuple) else row["name"]) == "gcal_sync_mode"
                for row in cur.fetchall()
            )
        except Exception:
            has_sync_mode = False
        if has_sync_mode:
            cur.execute(
                """
                SELECT id
                FROM unified_task
                WHERE (gcal_event_id IS NULL OR trim(gcal_event_id) = '')
                  AND type = 'schedule'
                  AND COALESCE(gcal_sync_mode, 'unknown') IN ('unknown', 'remote_mirror')
                  AND (
                        ? IS NULL
                        OR COALESCE(NULLIF(trim(gcal_source_calendar_id), ''), NULLIF(trim(gcal_target_calendar_id), ''), 'primary') = ?
                  )
                  AND name = ?
                  AND deadline = ?
                  AND COALESCE(end_date, '') = COALESCE(?, '')
                  AND COALESCE(all_day, 0) = ?
                ORDER BY id ASC
                LIMIT 1
                """,
                (
                    _normalize_calendar_id(source_calendar_id) if source_calendar_id else None,
                    _normalize_calendar_id(source_calendar_id) if source_calendar_id else None,
                    summary,
                    start_str,
                    end_str or "",
                    int(bool(all_day)),
                ),
            )
        else:
            cur.execute(
                """
                SELECT id
                FROM unified_task
                WHERE (gcal_event_id IS NULL OR trim(gcal_event_id) = '')
                  AND type = 'schedule'
                  AND name = ?
                  AND deadline = ?
                  AND COALESCE(end_date, '') = COALESCE(?, '')
                  AND COALESCE(all_day, 0) = ?
                ORDER BY id ASC
                LIMIT 1
                """,
                (summary, start_str, end_str or "", int(bool(all_day))),
            )
        row = cur.fetchone()
        return int(row["id"]) if row else None
    except Exception as e:
        logger.error(f"Error finding unlinked unified task for gcal payload: {e}")
        return None


def delete_task_by_gcal_id(table, local_id):
    try:
        if table == "unified_task":
            return bool(task_repo.archive_gcal_deleted_task(local_id, reason="remote_deleted"))
        return False
    except Exception as e:
        logger.error(f"Error deleting task by gcal_id: {e}")
        return False
