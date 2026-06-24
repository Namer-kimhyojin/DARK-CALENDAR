from datetime import UTC, datetime, timedelta
from datetime import date as _date
import json
import logging

from calendar_app.infrastructure.db import task_repo
from calendar_app.infrastructure.google_sync import repository as gcal_db_adapter
from calendar_app.infrastructure.google_sync.common import (
    build_calendar_source_summary_map as _build_calendar_source_summary_map,
)
from calendar_app.infrastructure.google_sync.common import (
    get_default_gcal_calendar_id,
    is_gcal_enabled,
)
from calendar_app.infrastructure.google_sync.common import (
    normalize_calendar_id as _normalize_calendar_id,
)
from calendar_app.infrastructure.google_sync.common import (
    resolve_task_target_calendar_id as _resolve_task_target_calendar_id,
)


def _get_default_gcal_id(app) -> str:
    """app.settings의 gcal_calendar_id 가 실제 ID면 그것을, 없으면 DB 기본 gcal 캘린더를 반환."""
    raw = str(app.settings.value("gcal_calendar_id", "") or "").strip()
    if raw:
        normalized = _normalize_calendar_id(raw)
        if normalized == "primary":
            resolved_primary_id = _resolved_primary_alias_id(app)
            return resolved_primary_id if resolved_primary_id != "primary" else "primary"
        return normalized
    return get_default_gcal_calendar_id()


from calendar_app.infrastructure.google_sync.helpers import sync_task_to_google  # noqa: E402
from calendar_app.shared.datetime_utils import (  # noqa: E402
    parse_datetime_str,
    timezone_offset_for_name,
)
from calendar_app.shared.google_color_palette import color_id_to_hex  # noqa: E402

logger = logging.getLogger(__name__)

_GCAL_DELETE_MAX_RETRIES = 5
_SYNC_TOKEN_FAIL_LIMIT = 3
_INCREMENTAL_BACKFILL_LOOKBACK_DAYS = 120
_INCREMENTAL_BACKFILL_LOOKAHEAD_DAYS = 400

SYNC_OUTCOME_SUCCESS = "success"
SYNC_OUTCOME_SKIPPED = "skipped"
SYNC_OUTCOME_FAILED = "failed"


def _settings_set(app, key, value):
    settings = getattr(app, "settings", None)
    if settings is not None:
        settings.setValue(key, value)


def _sync_token_key(calendar_id: str) -> str:
    return f"gcal_sync_token::{calendar_id}"


def _sync_fail_count_key(calendar_id: str) -> str:
    return f"gcal_sync_token_fails::{calendar_id}"


def _bound_calendar_key() -> str:
    return "gcal_bound_calendar_id"


def _incremental_backfill_probe_key(calendar_id: str) -> str:
    return f"gcal_incremental_backfill_probe::{calendar_id}"


def _should_run_incremental_backfill_probe(app, calendar_id: str) -> bool:
    settings = getattr(app, "settings", None)
    if settings is None:
        return True
    key = _incremental_backfill_probe_key(calendar_id)
    today = datetime.now().strftime("%Y-%m-%d")
    last = str(settings.value(key, "", type=str) or "").strip()
    if last == today:
        return False
    _settings_set(app, key, today)
    return True


def _date_only(value):
    if not value:
        return None
    return str(value)[:10]


def _calendar_source_summary_map():
    return _build_calendar_source_summary_map(include_inactive=True)


def _resolved_primary_alias_id(app) -> str:
    settings = getattr(app, "settings", None)
    if settings is not None:
        resolved = _normalize_calendar_id(settings.value("gcal_primary_resolved_id", "") or "")
        if resolved and resolved != "primary":
            return resolved
    return "primary"


def _refresh_resolved_primary_alias_id(app) -> str:
    sync_service = getattr(app, "gcal_sync", None)
    if sync_service is None or not getattr(sync_service, "is_authenticated", False):
        return _resolved_primary_alias_id(app)

    try:
        calendars = sync_service.list_accessible_calendars() or []
    except Exception:
        logger.exception("Failed to resolve actual primary Google calendar ID")
        return _resolved_primary_alias_id(app)

    actual_primary_id = ""
    for calendar in calendars:
        if calendar.get("primary"):
            actual_primary_id = _normalize_calendar_id(calendar.get("id"))
            break

    if actual_primary_id and actual_primary_id != "primary":
        _settings_set(app, "gcal_primary_resolved_id", actual_primary_id)
        return actual_primary_id
    return _resolved_primary_alias_id(app)


def _active_sync_calendar_ids(app, bound_calendar_id):
    calendar_ids = []
    seen = set()
    canonical_primary_id = _resolved_primary_alias_id(app)

    def _add(calendar_id):
        cid = _normalize_calendar_id(calendar_id)
        if cid == "primary" and canonical_primary_id and canonical_primary_id != "primary":
            cid = canonical_primary_id
        if cid in seen:
            return
        seen.add(cid)
        calendar_ids.append(cid)

    _add(bound_calendar_id)

    # calendar table first.
    # Include writable calendars (is_active=1) and also visible read-only calendars
    # (is_active=0, is_visible=1) for pull-only sync.
    try:
        from calendar_app.infrastructure.db.calendar_repo import list_calendars

        for cal in list_calendars(include_inactive=True):
            if cal.get("type") != "gcal":
                continue
            gcal_id = cal.get("gcal_calendar_id")
            if not gcal_id:
                continue
            is_active = bool(cal.get("is_active", 1))
            is_visible = bool(cal.get("is_visible", 1))
            if not is_active and not is_visible:
                continue
            _add(gcal_id)
        return calendar_ids
    except Exception:
        pass

    # fallback: 湲곗〈 gcal_subscription ?뚯씠釉?
    try:
        for row in task_repo.list_gcal_subscriptions(include_inactive=False):
            if int(row.get("is_active") or 0) != 1:
                continue
            _add(row.get("calendar_id"))
    except Exception:
        logger.exception("Failed to load active Google subscriptions for multi-calendar sync")
    return calendar_ids


def _task_target_calendar_id(task, default_calendar_id):
    return _resolve_task_target_calendar_id(task, default_calendar_id)


def _extract_rrule(recurrence_list) -> "str | None":
    """GCal recurrence 리스트에서 RRULE 문자열을 추출한다."""
    if not recurrence_list:
        return None
    for item in recurrence_list:
        s = str(item or "").strip().upper()
        if s.startswith("RRULE:"):
            return str(item).strip()[6:]  # "RRULE:" prefix 제거
    return None


def _upsert_recurring_series_if_needed(event, source_calendar_id: str, start_str: str):
    """반복 일정 인스턴스이면 gcal_recurring_series 테이블에 시리즈를 upsert한다."""
    series_id = getattr(event, "recurring_event_id", None)
    if not series_id:
        return
    rrule = _extract_rrule(getattr(event, "recurrence", None))
    try:
        from calendar_app.infrastructure.db import task_repo as _task_repo

        _task_repo.upsert_gcal_recurring_series(
            series_id=series_id,
            gcal_calendar_id=source_calendar_id,
            title=getattr(event, "summary", None),
            rrule=rrule,
            first_instance=start_str,
        )
    except AttributeError:
        # task_repo에 upsert_gcal_recurring_series 없는 경우(구버전 DB)는 무시
        pass
    except Exception:
        logger.exception("_upsert_recurring_series_if_needed failed for series %s", series_id)


def _save_event_extra_fields(
    conn, local_id: int, event, attendees_json: str, attachments_json: str
):
    """pull 후 신규 컬럼(반복 일정 + 참석자/첨부파일)을 unified_task에 저장한다.

    commit=True: 호출자의 트랜잭션 내에서 처리.
    컬럼이 없으면(구버전 DB) 조용히 무시한다.
    """
    if not conn or not local_id:
        return
    series_id = getattr(event, "recurring_event_id", None)
    orig_start = getattr(event, "original_start_time", None)
    recurrence = getattr(event, "recurrence", None)
    rrule_str = _extract_rrule(recurrence) if recurrence else None
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE unified_task
            SET gcal_recurring_series_id      = COALESCE(?, gcal_recurring_series_id),
                gcal_instance_original_start  = COALESCE(?, gcal_instance_original_start),
                gcal_recurrence_rule          = COALESCE(?, gcal_recurrence_rule),
                attendees_json                = ?,
                attachments_json              = ?
            WHERE id = ?
            """,
            (
                series_id,
                orig_start,
                rrule_str,
                attendees_json or None,
                attachments_json or None,
                local_id,
            ),
        )
    except Exception:
        # 컬럼 부재 등 무시
        pass


def _is_date_only_gcal_value(value):
    text = str(value or "").strip()
    return bool(text) and "T" not in text and " " not in text


def _parse_sync_dt(value):
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            dt = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if dt.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo or UTC
        return dt.replace(tzinfo=local_tz).astimezone(UTC)
    return dt.astimezone(UTC)


def _pending_calendar_binding_change(app, calendar_id):
    previous_calendar_id = app.settings.value(_bound_calendar_key(), "", type=str) or ""
    if not previous_calendar_id or previous_calendar_id == calendar_id:
        return ""
    return previous_calendar_id


def _apply_calendar_binding_change(app, previous_calendar_id, calendar_id):
    if not previous_calendar_id or previous_calendar_id == calendar_id:
        return False
    task_repo.clear_gcal_delete_queue()
    _settings_set(app, _sync_token_key(previous_calendar_id), "")
    _settings_set(app, _sync_fail_count_key(previous_calendar_id), 0)
    _settings_set(app, _sync_token_key(calendar_id), "")
    _settings_set(app, _sync_fail_count_key(calendar_id), 0)
    _settings_set(app, _bound_calendar_key(), calendar_id)
    logger.warning(
        "Detected Google Calendar binding change from %s to %s; preserved local links and forced full resync",
        previous_calendar_id,
        calendar_id,
    )
    return True


def _remote_is_newer_than_local_base(task, event):
    remote_dt = _parse_sync_dt(getattr(event, "updated_time", None))
    if remote_dt is None:
        return False
    base_dt = _parse_sync_dt(task.get("gcal_last_synced_at"))
    if base_dt is None:
        return False
    return remote_dt > base_dt


def _remote_text_is_newer_than_local_base(task, remote_updated_at):
    remote_dt = _parse_sync_dt(remote_updated_at)
    if remote_dt is None:
        return False
    base_dt = _parse_sync_dt(task.get("gcal_last_synced_at"))
    if base_dt is None:
        return False
    return remote_dt > base_dt


def _mark_sync_failure(task_id, message, commit=True):
    if not task_id:
        return
    try:
        task_repo.mark_unified_task_gcal_failed(task_id, message, commit=commit)
    except Exception:
        logger.exception("Failed to store sync error for task %s", task_id)


def _normalize_gcal_event_datetimes(event, target_tz_offset="+09:00"):
    """GCal 이벤트 시작/종료를 로컬 datetime 문자열로 정규화한다.

    종일 이벤트는 순수 date 산술(DST 영향 없음)로 처리하고,
    시간 포함 이벤트는 기존 timezone-aware 경로를 유지한다.
    """
    is_all_day = _is_date_only_gcal_value(event.start_time)

    if is_all_day:
        # 날짜 전용 값에는 오프셋을 적용하지 않아 DST 경계 오류를 방지한다.
        try:
            st_date = _date.fromisoformat(str(event.start_time).strip()[:10])
        except ValueError:
            return None, None, False

        end_raw = str(event.end_time or "").strip()
        if end_raw and _is_date_only_gcal_value(end_raw):
            try:
                # GCal 종일 이벤트 end_date 는 exclusive (마지막 날 다음 날)
                en_date_exclusive = _date.fromisoformat(end_raw[:10])
                en_date = en_date_exclusive - timedelta(days=1)
                if en_date < st_date:
                    en_date = st_date
            except ValueError:
                en_date = st_date
        else:
            en_date = st_date

        start_str = st_date.strftime("%Y-%m-%d 00:00:00")
        end_str = en_date.strftime("%Y-%m-%d 00:00:00")
        return start_str, end_str, True

    # 시간 포함 이벤트: 기존 timezone-aware 경로 유지
    st_dt = parse_datetime_str(event.start_time, target_tz_offset=target_tz_offset)
    en_dt = parse_datetime_str(event.end_time, target_tz_offset=target_tz_offset)
    if not st_dt:
        return None, None, False

    start_str = st_dt.strftime("%Y-%m-%d %H:%M:%S")
    end_str = en_dt.strftime("%Y-%m-%d %H:%M:%S") if en_dt else ""
    return start_str, end_str, False


def _writable_gcal_ids() -> set:
    """쓰기 가능한 gcal 캘린더의 gcal_calendar_id 집합을 반환한다 (push 필터 용도).
    is_calendar_row_read_only() 기준을 따르므로 ICS·read-only GCal 은 제외된다."""
    try:
        from calendar_app.infrastructure.db.calendar_repo import (
            is_calendar_row_read_only,
            list_calendars,
        )

        return {
            cal["gcal_calendar_id"]
            for cal in list_calendars(include_inactive=True)
            if cal.get("type") == "gcal"
            and cal.get("gcal_calendar_id")
            and not is_calendar_row_read_only(cal)
        }
    except Exception:
        return set()


def _deactivate_missing_gcal_calendar(app, gcal_calendar_id: str) -> None:
    """404濡??묎렐 遺덇???罹섎┛?붾? DB?먯꽌 is_active=0 ?쇰줈 ?쒖떆?⑸땲??"""
    try:
        from calendar_app.infrastructure.db.calendar_repo import (
            make_gcal_id,
            set_calendar_active,
            set_calendar_visible,
        )

        cal_db_id = make_gcal_id(gcal_calendar_id)
        if set_calendar_active(cal_db_id, False):
            logger.warning(
                "Calendar %s returned 404 (removed from Google); marked is_active=0 in DB",
                gcal_calendar_id,
            )
        # Hide removed calendars so they are excluded from pull candidates.
        set_calendar_visible(cal_db_id, False)
        # sync token 珥덇린??(?ы솢?깊솕??full resync 蹂댁옣)
        _settings_set(app, _sync_token_key(gcal_calendar_id), "")
        _settings_set(app, _sync_fail_count_key(gcal_calendar_id), 0)
    except Exception:
        logger.exception("Failed to deactivate missing calendar %s", gcal_calendar_id)


_CAL_LIST_REFRESH_KEY = "gcal_cal_list_last_refresh"
_CAL_LIST_REFRESH_INTERVAL_SECS = 3600  # 1?쒓컙留덈떎 罹섎┛??紐⑸줉 媛깆떊


def _should_refresh_calendar_list(app) -> bool:
    """마지막 캘린더 목록 갱신으로부터 1시간 이내이면 True."""
    last = int(app.settings.value(_CAL_LIST_REFRESH_KEY, 0, type=int) or 0)
    import time

    return (time.time() - last) >= _CAL_LIST_REFRESH_INTERVAL_SECS


def _refresh_calendar_list_from_google(app) -> bool:
    """
    Google Calendar API에서 캘린더 목록을 받아 calendar 테이블을 갱신한다.
    - ??罹섎┛?? 異붽? (is_active=1)
    - 湲곗〈 罹섎┛?? ?대쫫 媛깆떊
    - Google?먯꽌 ?놁뼱吏?罹섎┛?? is_active=0 ?쒖떆
    반환값: 변경이 있었으면 True
    """
    import time

    try:
        from calendar_app.infrastructure.db.calendar_repo import (
            get_calendar,
            list_calendars,
            make_gcal_id,
            set_calendar_active,
            upsert_calendar,
        )

        if not getattr(app, "gcal_sync", None) or not app.gcal_sync.is_authenticated:
            return False

        remote_cals = app.gcal_sync.list_accessible_calendars()
        if not remote_cals:
            logger.warning("_refresh_calendar_list_from_google: empty calendar list returned")
            return False

        remote_ids = {c["id"] for c in remote_cals}
        changed = False

        # 1) ??罹섎┛??異붽? + ?대쫫 媛깆떊
        for rc in remote_cals:
            gcal_id = rc["id"]
            # "primary" 별칭은 실제 캘린더 ID가 아니므로 무시한다.
            # Google API는 실제 ID(이메일 등)를 반환하며, primary=True 플래그로 구분한다.
            if gcal_id == "primary":
                logger.debug("Calendar list refresh: skipping 'primary' alias entry")
                continue
            cal_db_id = make_gcal_id(gcal_id)
            existing = get_calendar(cal_db_id)
            is_writable = rc.get("accessRole") in ("owner", "writer")
            if existing is None:
                # 새로운 캘린더 추가
                upsert_calendar(
                    calendar_id=cal_db_id,
                    cal_type="gcal",
                    name=rc.get("summary") or gcal_id,
                    is_active=is_writable,
                    is_visible=is_writable,
                    gcal_calendar_id=gcal_id,
                    access_role=rc.get("accessRole") or None,
                )
                logger.info(
                    "Calendar list refresh: added new calendar %s (%s)", gcal_id, rc.get("summary")
                )
                changed = True
            else:
                # 이름 변경 감지
                remote_name = rc.get("summary") or gcal_id
                if existing.get("name") != remote_name:
                    from calendar_app.infrastructure.db.calendar_repo import rename_calendar

                    rename_calendar(cal_db_id, remote_name)
                    logger.info(
                        "Calendar list refresh: renamed %s ??%s", existing.get("name"), remote_name
                    )
                    changed = True
                # Sync access_role so read-only detection stays accurate
                remote_role = rc.get("accessRole") or None
                if remote_role and existing.get("access_role") != remote_role:
                    from calendar_app.infrastructure.db.calendar_repo import (
                        update_calendar_access_role,
                    )

                    update_calendar_access_role(cal_db_id, remote_role)
                    logger.info(
                        "Calendar list refresh: updated access_role for %s -> %s",
                        gcal_id,
                        remote_role,
                    )
                    changed = True
                # 비활성화됐다가 다시 활성화된 경우 재활성화 (writable)
                if not existing.get("is_active") and is_writable:
                    set_calendar_active(cal_db_id, True)
                    _settings_set(app, _sync_token_key(gcal_id), "")
                    _settings_set(app, _sync_fail_count_key(gcal_id), 0)
                    logger.info("Calendar list refresh: re-activated %s", gcal_id)
                    changed = True

        # 2) Google?먯꽌 ?щ씪吏?罹섎┛????is_active=0
        # "primary" 별칭 row 제거: Google API가 실제 "primary" ID를 반환하지 않는데
        # gcal::primary row가 DB에 있으면 유령 항목이므로 삭제한다.
        if "primary" not in remote_ids:
            from calendar_app.infrastructure.db.calendar_repo import delete_calendar

            primary_alias_rows = [
                c
                for c in list_calendars(include_inactive=True)
                if c.get("type") == "gcal" and c.get("gcal_calendar_id") == "primary"
            ]
            real_primary = next((c for c in remote_cals if c.get("primary")), None)
            if real_primary and primary_alias_rows:
                for par in primary_alias_rows:
                    try:
                        delete_calendar(par["id"])
                        logger.info(
                            "Calendar list refresh: removed phantom gcal::primary row (real primary is %s)",
                            real_primary["id"],
                        )
                        changed = True
                    except Exception:
                        logger.exception("Failed to delete phantom gcal::primary row")

        local_gcal_cals = [
            c
            for c in list_calendars(include_inactive=True)
            if c.get("type") == "gcal" and c.get("gcal_calendar_id")
        ]
        for lc in local_gcal_cals:
            if lc["gcal_calendar_id"] not in remote_ids and lc.get("is_active"):
                set_calendar_active(lc["id"], False)
                _settings_set(app, _sync_token_key(lc["gcal_calendar_id"]), "")
                _settings_set(app, _sync_fail_count_key(lc["gcal_calendar_id"]), 0)
                logger.info(
                    "Calendar list refresh: deactivated removed calendar %s (%s)",
                    lc["gcal_calendar_id"],
                    lc.get("name"),
                )
                changed = True

        _settings_set(app, _CAL_LIST_REFRESH_KEY, int(time.time()))
        logger.info(
            "Calendar list refreshed from Google (%d remote, changed=%s)", len(remote_cals), changed
        )
        return changed

    except Exception:
        logger.exception("_refresh_calendar_list_from_google failed")
        return False


def _push_local_changes_to_google(app):
    pushed = 0
    failed = 0
    auto_healed = 0
    default_target_calendar_id = _get_default_gcal_id(app)
    sync = getattr(app, "gcal_sync", None)
    tasks = task_repo.get_google_sync_tasks()
    # NEW-F01: tasks=None 諛⑹뼱 (DB ?ㅻ쪟 ??
    if tasks is None:
        logger.error("get_google_sync_tasks returned None; skipping push")
        return 0, 0, 0
    if tasks:
        no_id_count = sum(1 for task in tasks if not (task.get("gcal_event_id") or "").strip())
        if len(tasks) >= 100 and no_id_count == len(tasks):
            logger.warning(
                "Skipping GCal push: detected %d dirty tasks with no Google IDs (possible orphaned pull data)",
                len(tasks),
            )
            return 0, 0, 0

    writable_ids = _writable_gcal_ids()

    # ── 배치 최적화: gcal_event_id 없는 순수 create 태스크를 50개씩 배치 처리 ──
    # update / 복잡한 태스크(read-only, remote_newer 등)는 아래 sequential 루프에서 처리한다.
    batch_create_eligible = []
    batch_update_eligible = []
    remaining_tasks = []
    from calendar_app.shared.google_color_palette import hex_to_color_id as _hex_to_color_id

    for _t in tasks:
        _has_id = bool(str(_t.get("gcal_event_id") or "").strip())
        _cal_id = _task_target_calendar_id(_t, default_target_calendar_id)
        _is_writable = (
            (not writable_ids)
            or (_cal_id in writable_ids)
            or bool(_t.get("gcal_target_calendar_id"))
        )

        if not _is_writable or _remote_text_is_newer_than_local_base(
            _t, _t.get("gcal_remote_updated_at")
        ):
            remaining_tasks.append(_t)
            continue

        if not _has_id and _cal_id:
            batch_create_eligible.append(_t)
        elif _has_id and _cal_id:
            batch_update_eligible.append(_t)
        else:
            remaining_tasks.append(_t)

    # 1) Batch Create
    can_batch_create = (
        batch_create_eligible
        and sync
        and getattr(sync, "is_authenticated", False)
        and hasattr(sync, "batch_create_events")
    )
    if can_batch_create:
        BATCH_SIZE = 50
        for _chunk_start in range(0, len(batch_create_eligible), BATCH_SIZE):
            _chunk = batch_create_eligible[_chunk_start : _chunk_start + BATCH_SIZE]
            _ops = []
            _redirect_to_update = []  # BUG-L01: tasks that already have a gcal_event_id in DB
            for _bt in _chunk:
                _local_id = _bt.get("id")
                # BUG-L01 guard: re-read DB to check if another worker already created
                # a GCal event for this task between the dirty-task query and now.
                _db_event_id = None
                try:
                    _fresh = task_repo.get_unified_task(_local_id)
                    _db_event_id = str((_fresh or {}).get("gcal_event_id") or "").strip() or None
                except Exception:
                    pass
                if _db_event_id:
                    logger.info(
                        "BUG-L01 guard: task %s already has gcal_event_id %s in DB; "
                        "redirecting to update instead of batch create",
                        _local_id,
                        _db_event_id,
                    )
                    _redirect_to_update.append(_bt)
                    continue
                _cal = _task_target_calendar_id(_bt, default_target_calendar_id)
                # Build idempotency key so GCal server rejects duplicate inserts
                # with HTTP 409 instead of creating a second event.
                _upd_raw = (
                    str(_bt.get("updated_at") or "")
                    .replace("-", "")
                    .replace(":", "")
                    .replace(" ", "")
                    .replace("T", "")[:14]
                )
                _batch_ikey = f"task{_local_id}{_upd_raw}" if _upd_raw else f"task{_local_id}"
                _ops.append(
                    {
                        "local_task_id": _local_id,
                        "calendar_id": _cal,
                        "summary": _bt.get("name") or _bt.get("summary") or "Untitled",
                        "start_iso": _bt.get("deadline") or "",
                        "end_iso": _bt.get("end_date") or "",
                        "description": _bt.get("description") or "",
                        "location": _bt.get("location") or "",
                        "color_id": _hex_to_color_id(_bt.get("bg_color"), sync),
                        "all_day": bool(_bt.get("all_day")),
                        "idempotency_key": _batch_ikey,
                    }
                )
            # Redirected tasks go to remaining for sequential update handling
            remaining_tasks.extend(_redirect_to_update)
            if not _ops:
                continue
            _batch_results = sync.batch_create_events(_ops)
            if not _batch_results:
                remaining_tasks.extend(_chunk)
                logger.warning(
                    "batch_create_events failed for chunk of %d; falling back to sequential",
                    len(_chunk),
                )
            else:
                _task_map = {str(_bt.get("id")): _bt for _bt in _chunk}
                for _res in _batch_results:
                    _ltid = _res.get("local_task_id")
                    _bt2 = _task_map.get(str(_ltid))
                    if _res.get("success") and _res.get("event_id"):
                        _src_cal = _task_target_calendar_id(_bt2 or {}, default_target_calendar_id)
                        task_repo.mark_unified_task_gcal_synced(
                            _ltid,
                            event_id=_res["event_id"],
                            commit=True,
                            source_calendar_id=_src_cal,
                            source_calendar_summary=None,
                            target_calendar_id=_src_cal,
                        )
                        pushed += 1
                        logger.info(
                            "Batch created GCal event %s for task %s", _res["event_id"], _ltid
                        )
                    else:
                        _err = _res.get("error") or "batch_create_failed"
                        task_repo.mark_unified_task_gcal_failed(_ltid, _err, commit=True)
                        failed += 1
                        logger.warning("Batch create failed for task %s: %s", _ltid, _err)

    elif batch_create_eligible:
        remaining_tasks.extend(batch_create_eligible)

    # 2) Batch Update
    can_batch_update = (
        batch_update_eligible
        and sync
        and getattr(sync, "is_authenticated", False)
        and hasattr(sync, "batch_update_events")
    )
    if can_batch_update:
        BATCH_SIZE = 50
        for _chunk_start in range(0, len(batch_update_eligible), BATCH_SIZE):
            _chunk = batch_update_eligible[_chunk_start : _chunk_start + BATCH_SIZE]
            _ops = []
            for _ut in _chunk:
                _cal = _task_target_calendar_id(_ut, default_target_calendar_id)
                _ops.append(
                    {
                        "local_task_id": _ut.get("id"),
                        "event_id": _ut.get("gcal_event_id"),
                        "calendar_id": _cal,
                        "summary": _ut.get("name") or _ut.get("summary") or "Untitled",
                        "start_iso": _ut.get("deadline") or "",
                        "end_iso": _ut.get("end_date") or "",
                        "description": _ut.get("description") or "",
                        "location": _ut.get("location") or "",
                        "color_id": _hex_to_color_id(_ut.get("bg_color"), sync),
                        "all_day": bool(_ut.get("all_day")),
                        "completed": bool(_ut.get("is_completed")),
                        "hide_completed": False,  # TODO: app-wide setting if needed
                    }
                )
            _batch_results = sync.batch_update_events(_ops)
            if not _batch_results:
                remaining_tasks.extend(_chunk)
                logger.warning(
                    "batch_update_events failed for chunk of %d; falling back to sequential",
                    len(_chunk),
                )
            else:
                for _res in _batch_results:
                    _ltid = _res.get("local_task_id")
                    if _res.get("success"):
                        task_repo.mark_unified_task_gcal_synced(_ltid, commit=True)
                        pushed += 1
                        logger.debug(
                            "Batch updated GCal event %s for task %s", _res.get("event_id"), _ltid
                        )
                    else:
                        _st = _res.get("status")
                        if _st == 404 or _st == 410:
                            # Auto-heal: GCal event missing, move to remaining to re-create
                            _task_map = {str(_bt.get("id")): _bt for _bt in _chunk}
                            remaining_tasks.append(_task_map[str(_ltid)])
                            logger.info("Batch update 404 for task %s; moving to re-create", _ltid)
                        else:
                            _err = _res.get("error") or "batch_update_failed"
                            task_repo.mark_unified_task_gcal_failed(_ltid, _err, commit=True)
                            failed += 1
                            logger.warning("Batch update failed for task %s: %s", _ltid, _err)

    # tasks 변수를 남은 태스크(update + 복잡한 태스크)로 교체
    if batch_update_eligible and not can_batch_update:
        remaining_tasks.extend(batch_update_eligible)

    tasks = remaining_tasks

    for task in tasks:
        try:
            target_calendar_id = _task_target_calendar_id(task, default_target_calendar_id)
            if not target_calendar_id:
                logger.info(
                    "Skipped push for task %s: non-gcal calendar (%s)",
                    task.get("id"),
                    task.get("calendar_id"),
                )
                try:  # noqa: SIM105
                    task_repo.mark_unified_task_gcal_synced(task.get("id"), commit=True)
                except Exception:
                    pass
                continue
            explicit_target_calendar_id = _normalize_calendar_id(
                task.get("gcal_target_calendar_id")
            )
            # read-only 罹섎┛??is_active=0, 怨듯쑕?????먮뒗 push 湲덉?
            if (
                writable_ids
                and target_calendar_id not in writable_ids
                and not explicit_target_calendar_id
            ):
                logger.info(
                    "Skipped push for task %s: calendar %s is read-only or inactive",
                    task.get("id"),
                    target_calendar_id,
                )
                _mark_sync_failure(task.get("id"), "read_only_calendar_skipped", commit=True)
                failed += 1
                continue
            if task.get("gcal_event_id") and _remote_text_is_newer_than_local_base(
                task, task.get("gcal_remote_updated_at")
            ):
                _mark_sync_failure(task.get("id"), "remote_newer_than_local", commit=True)
                failed += 1
                logger.info(
                    "Skipped push for task %s because remote change is newer than last synced state",
                    task.get("id"),
                )
                continue
            before_id = task.get("gcal_event_id")
            result = sync_task_to_google(
                app,
                task,
                create_if_missing=True,
                commit=True,
                target_calendar_id=target_calendar_id,
            )
            if not result.success:
                failed += 1
                error_summary = result.error_kind or "push_failed"
                err_msg = getattr(result, "error_message", "") or ""
                if err_msg:
                    error_summary = f"[{error_summary}] {err_msg}"

                # BUG-B02: HTTP 오류 상태코드 처리
                err_status = getattr(getattr(app, "gcal_sync", None), "last_error_status", None)

                if err_status == 429:
                    _retry_hint = getattr(
                        getattr(app, "gcal_sync", None), "_last_retry_after_secs", 0
                    )
                    logger.warning(
                        "GCal push hit rate limit (429) on task %s; aborting push loop for this cycle "
                        "(Retry-After hint: %.0fs)",
                        task.get("id"),
                        _retry_hint,
                    )
                    _mark_sync_failure(task.get("id"), "rate_limit_429", commit=True)
                    break
                elif err_status == 401:
                    # 인증 만료: 재인증 필요, 이번 push 루프 전체 중단
                    logger.warning(
                        "GCal push got 401 (auth expired) on task %s; aborting push loop and marking auth invalid",
                        task.get("id"),
                    )
                    if getattr(app, "gcal_sync", None):
                        app.gcal_sync.is_authenticated = False
                        app.gcal_sync.service = None
                    _mark_sync_failure(task.get("id"), "auth_expired_401", commit=True)
                    break  # 루프 중단

                elif err_status == 403:
                    if "virtualCalendarManipulation" in err_msg or "read-only" in err_msg.lower():
                        # read-only 캘린더: 표시만 불가능하므로 dirty 클리어
                        try:  # noqa: SIM105
                            task_repo.mark_unified_task_gcal_synced(task.get("id"), commit=True)
                        except Exception:
                            pass
                        logger.warning(
                            "Cleared gcal_dirty for task %s: calendar %s is read-only",
                            task.get("id"),
                            target_calendar_id,
                        )
                    else:
                        # 다른 403 (권한 부족): 실패 기록
                        _mark_sync_failure(task.get("id"), error_summary, commit=True)
                        logger.warning(
                            "GCal push 403 (permission denied) for task %s on calendar %s: %s (%s)",
                            task.get("id"),
                            target_calendar_id,
                            result.error_kind or "push_failed",
                            err_msg or "no detail",
                        )

                else:
                    _mark_sync_failure(task.get("id"), error_summary, commit=True)
                    logger.warning(
                        "Failed to push local task %s to Google calendar %s: %s (%s)",
                        task.get("id"),
                        target_calendar_id,
                        result.error_kind or "push_failed",
                        err_msg or "no detail",
                    )
                continue
            event_id = result.event_id
            # NEW-F02: result.success=True인데 event_id가 없으면 create 실패로 처리
            # (helpers.py에서 success=True 반환했지만 event_id=None인 케이스 방지)
            if not before_id and not event_id:
                # 새 이벤트 create인데 event_id가 없음 -> 실패로 기록하여 무한 루프 방지
                _mark_sync_failure(task.get("id"), "created_but_no_event_id", commit=True)
                failed += 1
                logger.error(
                    "NEW-F02: sync_task_to_google returned success=True for task %s but event_id is None; "
                    "marking as failed to prevent infinite loop",
                    task.get("id"),
                )
                continue
            if event_id and event_id != before_id:
                pushed += 1
            if getattr(result, "auto_healed", False):
                auto_healed += 1
        except Exception as e:
            failed += 1
            _mark_sync_failure(task.get("id"), f"[push_failed] {str(e)}", commit=True)
            logger.exception("Failed to push local task %s to Google", task.get("id"))

    return pushed, failed, auto_healed


def _process_google_delete_queue(app):
    deleted = 0
    failed = 0
    sync = getattr(app, "gcal_sync", None)
    if not sync or not sync.is_authenticated:
        return 0, 0

    queue_rows = task_repo.get_gcal_delete_queue_ready(max_retry_count=_GCAL_DELETE_MAX_RETRIES)
    if not queue_rows:
        return 0, 0

    conn = gcal_db_adapter.get_connection()
    BATCH_SIZE = 50
    for i in range(0, len(queue_rows), BATCH_SIZE):
        chunk = queue_rows[i : i + BATCH_SIZE]
        ops = []
        for row in chunk:
            event_id = row.get("gcal_event_id")
            if row.get("recurring_scope") == "all" and row.get("local_task_id"):
                _lt = task_repo.get_unified_task(row.get("local_task_id"))
                if _lt and _lt.get("gcal_recurring_series_id"):
                    event_id = _lt.get("gcal_recurring_series_id")

            ops.append(
                {
                    "local_task_id": row.get("id"),
                    "event_id": event_id,
                    "calendar_id": row.get("gcal_calendar_id"),
                }
            )

        batch_results = sync.batch_delete_events(ops)
        if not batch_results:
            logger.warning("batch_delete_events failed for chunk; continuing to next chunk")
            continue

        for res in batch_results:
            qid = res.get("local_task_id")
            if res.get("success"):
                task_repo.mark_gcal_delete_done(qid, commit=True)
                deleted += 1
            else:
                st = res.get("status")
                if st in (404, 409, 410):
                    # 404/410 = already deleted; 409 = event ID conflict (event doesn't exist
                    # under this ID in GCal) — all three mean nothing left to delete.
                    task_repo.mark_gcal_delete_done(qid, commit=True)
                    deleted += 1
                elif st == 401:
                    logger.warning(
                        "Delete queue: 401 auth expired; committing current results and aborting"
                    )
                    if conn:
                        conn.commit()
                    return deleted, failed
                elif st == 429:
                    logger.warning(
                        "Delete queue: 429 rate limit; committing current results and aborting"
                    )
                    if conn:
                        conn.commit()
                    return deleted, failed
                else:
                    task_repo.mark_gcal_delete_failed(
                        qid, res.get("error") or "delete_failed", commit=True
                    )
                    failed += 1

        # Commit chunk at once to minimize locking
        if conn:
            conn.commit()

    # NEW-A04: max_retry zombie cleanup
    try:
        zombie_rows = task_repo.get_gcal_delete_queue_zombies(
            max_retry_count=_GCAL_DELETE_MAX_RETRIES, min_age_days=7
        )
        if zombie_rows and conn:
            for zrow in zombie_rows:
                logger.warning(
                    "NEW-A04: Removing zombie delete-queue entry id=%s (event=%s, retries=%s, age>7d)",
                    zrow.get("id"),
                    zrow.get("gcal_event_id"),
                    zrow.get("retry_count"),
                )
                task_repo.mark_gcal_delete_done(zrow.get("id"), commit=True)
            conn.commit()
    except Exception as _zombie_exc:
        logger.debug("NEW-A04: Zombie cleanup skipped or failed: %s", _zombie_exc)

    return deleted, failed


def sync_google_calendar(app, silent=False):
    """Bi-directional sync with local push followed by Google pull."""
    try:
        from calendar_app.infrastructure.google_sync.service import CalendarSyncService

        if getattr(app, "_gcal_sync_in_progress", False):
            app._last_gcal_sync_outcome = SYNC_OUTCOME_SKIPPED
            app._last_gcal_sync_error = "sync_in_progress"
            return False
        app._gcal_sync_in_progress = True
        app._last_gcal_sync_changed_any = False
        app._last_gcal_sync_refresh_left = False
        app._last_gcal_sync_outcome = SYNC_OUTCOME_SKIPPED
        app._last_gcal_sync_error = None
        app._last_gcal_sync_stats = {
            "binding_changed": False,
            "deleted_count": 0,
            "delete_failures": 0,
            "pushed_count": 0,
            "push_failures": 0,
            "pull_calendar_count": 0,
            "pull_changes": 0,
            "pull_apply_failures": 0,
            "pull_fetch_failures": 0,
            "auto_healed": 0,
        }

        if hasattr(app, "update_sync_status"):
            app.update_sync_status()

        if not is_gcal_enabled(app.settings):
            app._last_gcal_sync_error = "disabled"
            return False

        cal_id = _get_default_gcal_id(app)
        tz = app.settings.value("gcal_timezone", "Asia/Seoul")
        source_summary_map = _calendar_source_summary_map()
        source_summary_map.setdefault(cal_id, cal_id)

        if not hasattr(app, "gcal_sync") or app.gcal_sync is None:
            app.gcal_sync = CalendarSyncService(calendar_id=cal_id, time_zone=tz)
        else:
            app.gcal_sync.calendar_id = cal_id
            app.gcal_sync.time_zone = tz

        auth_success = app.gcal_sync.authenticate(None, interactive=not silent)
        if not auth_success:
            app._last_gcal_sync_error = getattr(app.gcal_sync, "last_error_kind", None) or "auth"
            app._last_gcal_sync_outcome = SYNC_OUTCOME_FAILED
            if hasattr(app, "update_sync_status"):
                app.update_sync_status()
            if not silent:
                raise Exception("Google Calendar authentication failed.")
            return False

        resolved_primary_id = _refresh_resolved_primary_alias_id(app)
        if cal_id == "primary" and resolved_primary_id != "primary":
            cal_id = resolved_primary_id
            app.gcal_sync.calendar_id = cal_id
        source_summary_map.setdefault(cal_id, cal_id)
        previous_calendar_id = _pending_calendar_binding_change(app, cal_id)
        binding_changed = _apply_calendar_binding_change(app, previous_calendar_id, cal_id)
        app._last_gcal_sync_stats["binding_changed"] = binding_changed

        deleted_count, delete_failures = _process_google_delete_queue(app)
        app._last_gcal_sync_stats["deleted_count"] = deleted_count
        app._last_gcal_sync_stats["delete_failures"] = delete_failures
        if delete_failures:
            logger.warning("GCal delete queue completed with %d failures", delete_failures)
        elif deleted_count:
            logger.info("GCal delete queue removed %d Google events", deleted_count)

        pushed_count, push_failures, auto_healed = _push_local_changes_to_google(app)
        app._last_gcal_sync_stats["pushed_count"] = pushed_count
        app._last_gcal_sync_stats["push_failures"] = push_failures
        app._last_gcal_sync_stats["auto_healed"] = auto_healed
        if push_failures:
            logger.warning("GCal local push completed with %d failures", push_failures)
        elif pushed_count:
            logger.info("GCal local push created %d new Google events", pushed_count)

        # 罹섎┛??紐⑸줉 ?먮룞 媛깆떊 (1?쒓컙留덈떎)
        if _should_refresh_calendar_list(app):
            _refresh_calendar_list_from_google(app)

        deduped_rows = gcal_db_adapter.cleanup_duplicate_gcal_rows()
        if deduped_rows:
            logger.warning(
                "GCal sync cleaned up %d duplicate local mirror row(s) before pull",
                deduped_rows,
            )

        local_gcal_map = gcal_db_adapter.get_all_gcal_tasks_map()
        # BUG-D01: calendar ID 목록은 루프 진입 전 1번만 스냅샷으로 고정.
        # 루프 도중 사용자가 캘린더를 삭제/추가해도 한 번 sync 주기에는 영향 없음.
        sync_calendar_ids = list(_active_sync_calendar_ids(app, cal_id))
        app._last_gcal_sync_stats["pull_calendar_count"] = len(sync_calendar_ids)
        changed_dates = set()
        changed_any = False
        pull_changes = 0
        pull_apply_failures = 0
        pull_fetch_failures = 0
        conn = gcal_db_adapter.get_connection()

        for sync_calendar_id in sync_calendar_ids:
            token_key = _sync_token_key(sync_calendar_id)
            fail_key = _sync_fail_count_key(sync_calendar_id)
            sync_token = app.settings.value(token_key, "", type=str) or None
            if binding_changed and sync_calendar_id == cal_id:
                sync_token = None

            token_fail_count = int(app.settings.value(fail_key, 0, type=int) or 0)
            if sync_token and token_fail_count >= _SYNC_TOKEN_FAIL_LIMIT:
                logger.warning(
                    "GCal sync token failed %d times in a row for calendar %s; forcing full resync",
                    token_fail_count,
                    sync_calendar_id,
                )
                _settings_set(app, token_key, "")
                _settings_set(app, fail_key, 0)
                sync_token = None

            events, next_sync_token, reset_required = app.gcal_sync.fetch_sync_events(
                sync_token,
                calendar_id=sync_calendar_id,
            )
            if reset_required:
                # BUG-B01: 410 sync token 만료 후 full resync 재시도
                reset_retry_count = token_fail_count + 1
                if reset_retry_count > _SYNC_TOKEN_FAIL_LIMIT:
                    pull_fetch_failures += 1
                    logger.warning(
                        "GCal full resync retry skipped for calendar %s: token reset retries exceeded (%d/%d)",
                        sync_calendar_id,
                        reset_retry_count,
                        _SYNC_TOKEN_FAIL_LIMIT,
                    )
                    continue
                _settings_set(app, token_key, "")
                _settings_set(app, fail_key, reset_retry_count)
                events, next_sync_token, reset_required = app.gcal_sync.fetch_sync_events(
                    None,
                    calendar_id=sync_calendar_id,
                )
                if events is None:
                    # BUG-B01: full resync 재시도도 실패 시 오류 상태코드 처리
                    err_status = getattr(getattr(app, "gcal_sync", None), "last_error_status", None)
                    if err_status == 404:
                        _deactivate_missing_gcal_calendar(app, sync_calendar_id)
                        continue
                    elif err_status == 401:
                        logger.error(
                            "GCal full resync after 410 got 401 (auth expired) for calendar %s; "
                            "marking auth invalid",
                            sync_calendar_id,
                        )
                        if getattr(app, "gcal_sync", None):
                            app.gcal_sync.is_authenticated = False
                            app.gcal_sync.service = None
                        pull_fetch_failures += 1
                        continue
                    elif err_status == 429:
                        logger.warning(
                            "GCal full resync after 410 hit rate limit (429) for calendar %s; "
                            "will retry next cycle",
                            sync_calendar_id,
                        )
                        pull_fetch_failures += 1
                        continue
                    else:
                        pull_fetch_failures += 1
                        _settings_set(app, fail_key, reset_retry_count + 1)
                        logger.error(
                            "GCal full resync after 410 also failed for calendar %s (status=%s); "
                            "will retry next cycle",
                            sync_calendar_id,
                            err_status,
                        )
                        continue

            if events is None:
                # 404: 罹섎┛?붽? Google?먯꽌 ??젣????DB?먯꽌 鍮꾪솢?깊솕, ?ㅽ뙣 移댁슫???놁쓬
                err_status = getattr(getattr(app, "gcal_sync", None), "last_error_status", None)
                if err_status == 404:
                    _deactivate_missing_gcal_calendar(app, sync_calendar_id)
                    continue
                elif err_status == 401:
                    logger.error(
                        "GCal fetch got 401 (auth expired) for calendar %s; marking auth invalid",
                        sync_calendar_id,
                    )
                    if getattr(app, "gcal_sync", None):
                        app.gcal_sync.is_authenticated = False
                        app.gcal_sync.service = None
                    pull_fetch_failures += 1
                    continue
                elif err_status == 429:
                    logger.warning(
                        "GCal fetch hit rate limit (429) for calendar %s; will retry next cycle",
                        sync_calendar_id,
                    )
                    pull_fetch_failures += 1
                    continue
                pull_fetch_failures += 1
                _settings_set(app, fail_key, token_fail_count + 1)
                logger.warning(
                    "GCal fetch failed for calendar %s (status=%s, fail count: %d/%d)",
                    sync_calendar_id,
                    err_status,
                    token_fail_count + 1,
                    _SYNC_TOKEN_FAIL_LIMIT,
                )
                continue

            _settings_set(app, fail_key, 0)
            full_sync = sync_token is None or reset_required
            # Incremental sync can miss pre-existing events if a sync token survives
            # across DB resets/migrations. Probe a near-term window once per day and
            # backfill remote events that are absent locally.
            if (
                not full_sync
                and events is not None
                and _should_run_incremental_backfill_probe(app, sync_calendar_id)
            ):
                probe_start = (
                    datetime.now() - timedelta(days=_INCREMENTAL_BACKFILL_LOOKBACK_DAYS)
                ).strftime("%Y-%m-%d")
                probe_end = (
                    datetime.now() + timedelta(days=_INCREMENTAL_BACKFILL_LOOKAHEAD_DAYS)
                ).strftime("%Y-%m-%d")
                probe_events = app.gcal_sync.fetch_events(
                    probe_start,
                    probe_end,
                    calendar_id=sync_calendar_id,
                )
                if probe_events:
                    existing_event_keys = {
                        gcal_db_adapter.make_gcal_event_lookup_key(
                            _normalize_calendar_id(
                                getattr(ev, "source_calendar_id", None) or sync_calendar_id
                            ),
                            ev.id,
                        )
                        for ev in events
                    }
                    backfill_events = []
                    for probe_event in probe_events:
                        source_calendar_id = _normalize_calendar_id(
                            getattr(probe_event, "source_calendar_id", None) or sync_calendar_id
                        )
                        event_key = gcal_db_adapter.make_gcal_event_lookup_key(
                            source_calendar_id, probe_event.id
                        )
                        if event_key in existing_event_keys:
                            continue
                        if event_key in local_gcal_map:
                            continue
                        backfill_events.append(probe_event)
                        existing_event_keys.add(event_key)
                    if backfill_events:
                        events = [*events, *backfill_events]
                        logger.info(
                            "GCal incremental backfill added %d missing event(s) for calendar %s "
                            "(window: %s~%s)",
                            len(backfill_events),
                            sync_calendar_id,
                            probe_start,
                            probe_end,
                        )
            fetched_event_keys = set()
            calendar_apply_failures = 0
            calendar_committed_any = False
            # BUG-B04: cancelled 처리 실패를 별도 카운터로 추적.
            # cancelled 실패는 sync token 재설정을 막지 않는다(무한 재시도 방지).
            # 따라서 실패 횟수를 QSettings에 기록해 일정 횟수 초과 시 스킵한다.
            _cancelled_fail_key = f"gcal_cancelled_fail::{sync_calendar_id}"
            cancelled_fail_base = int(app.settings.value(_cancelled_fail_key, 0, type=int) or 0)
            cancelled_fail_this_run = 0
            _CANCELLED_FAIL_SKIP_LIMIT = 5  # 5회 실패 후 해당 이벤트는 스킵

            # BUG-H04: 이벤트 처리 루프 전체를 try/except로 감싸 예외 시 rollback 보장.
            # commit=True로 개별 처리하면 루프 중간 예외 시 DB가 불완전하게 커밋되지 않도록 한다.
            try:
                for event in events:
                    source_calendar_id = _normalize_calendar_id(
                        getattr(event, "source_calendar_id", None) or sync_calendar_id
                    )
                    event_key = gcal_db_adapter.make_gcal_event_lookup_key(
                        source_calendar_id, event.id
                    )
                    fetched_event_keys.add(event_key)

                    local_info = local_gcal_map.get(event_key)
                    if local_info is None:
                        legacy_event_key = str(getattr(event, "id", "") or "").strip()
                        if legacy_event_key:
                            local_info = local_gcal_map.get(legacy_event_key)
                            if local_info is not None:
                                local_gcal_map[event_key] = local_info

                    if event.status == "cancelled":
                        # [10] Skip deletion if this event was cancelled by our own completion-hide logic
                        _ext_priv = getattr(event, "extended_properties_private", None) or {}
                        if _ext_priv.get("dark_calendar_completed") == "1":
                            continue
                        if local_info:
                            table, local_id = local_info
                            if table == "unified_task":
                                local_task = task_repo.get_unified_task(local_id)
                                if local_task:
                                    changed_dates.add(_date_only(local_task.get("deadline")))
                            if gcal_db_adapter.delete_task_by_gcal_id(table, local_id):
                                changed_any = True
                                pull_changes += 1
                                local_gcal_map.pop(event_key, None)
                            else:
                                cancelled_fail_this_run += 1
                                pull_apply_failures += 1
                                # BUG-B04: 실패 횟수가 상한을 초과하면 경고 후 스킵
                                total_fails = cancelled_fail_base + cancelled_fail_this_run
                                if total_fails >= _CANCELLED_FAIL_SKIP_LIMIT:
                                    logger.error(
                                        "BUG-B04: Cancelled event %s (cal %s) failed %d times; "
                                        "removing from local_gcal_map to prevent infinite retry",
                                        event.id,
                                        source_calendar_id,
                                        total_fails,
                                    )
                                    local_gcal_map.pop(event_key, None)
                                else:
                                    logger.warning(
                                        "Failed to archive/delete cancelled Google event %s on calendar %s "
                                        "(attempt %d/%d)",
                                        event.id,
                                        source_calendar_id,
                                        total_fails,
                                        _CANCELLED_FAIL_SKIP_LIMIT,
                                    )
                        continue

                    target_tz_offset = timezone_offset_for_name(tz)
                    start_str, end_str, is_all_day = _normalize_gcal_event_datetimes(
                        event, target_tz_offset=target_tz_offset
                    )
                    if not start_str:
                        continue
                    description = (event.description or "").strip()
                    location = (event.location or "").strip()
                    bg_color = color_id_to_hex(event.color_id, getattr(app, "gcal_sync", None))
                    remote_updated_at = getattr(event, "updated_time", None)
                    source_calendar_summary = source_summary_map.get(
                        source_calendar_id, source_calendar_id
                    )
                    # [9] attendees/attachments for pull-through storage
                    _raw_attendees = getattr(event, "attendees", None) or []
                    attendees_json = json.dumps(_raw_attendees[:50]) if _raw_attendees else None
                    _raw_attachments = getattr(event, "attachments", None) or []
                    attachments_json = json.dumps(_raw_attachments) if _raw_attachments else None

                    if local_info:
                        table, local_id = local_info
                        if table == "unified_task":
                            local_task = task_repo.get_unified_task(local_id)
                            if local_task:
                                if int(
                                    local_task.get("gcal_dirty") or 0
                                ) == 1 and _remote_is_newer_than_local_base(local_task, event):
                                    try:
                                        task_repo.queue_gcal_sync_conflict(
                                            local_id,
                                            event.id,
                                            gcal_calendar_id=source_calendar_id,
                                            conflict_kind="remote_overwrite",
                                            local_snapshot={
                                                "name": local_task.get("name"),
                                                "deadline": local_task.get("deadline"),
                                                "end_date": local_task.get("end_date"),
                                                "description": local_task.get("description"),
                                                "location": local_task.get("location"),
                                                "all_day": int(local_task.get("all_day") or 0),
                                                "bg_color": local_task.get("bg_color"),
                                                "gcal_remote_updated_at": local_task.get(
                                                    "gcal_remote_updated_at"
                                                ),
                                                "gcal_dirty": int(
                                                    local_task.get("gcal_dirty") or 0
                                                ),
                                            },
                                            remote_snapshot={
                                                "summary": event.summary,
                                                "start": start_str,
                                                "end": end_str,
                                                "description": description,
                                                "location": location,
                                                "all_day": int(is_all_day),
                                                "bg_color": bg_color,
                                                "updated_time": remote_updated_at,
                                            },
                                        )
                                    except Exception:
                                        logger.exception(
                                            "Failed to queue gcal sync conflict for task %s",
                                            local_id,
                                        )
                                    logger.warning(
                                        "GCal conflict on task %s: remote newer than local dirty change, remote version wins",
                                        local_id,
                                    )
                                same_payload = (
                                    (local_task.get("name") or "") == event.summary
                                    and (local_task.get("deadline") or "") == start_str
                                    and (local_task.get("end_date") or "") == end_str
                                    and (local_task.get("description") or "") == description
                                    and (local_task.get("location") or "") == location
                                    and int(local_task.get("all_day") or 0) == int(is_all_day)
                                    and (local_task.get("bg_color") or None) == bg_color
                                    and (local_task.get("gcal_source_calendar_id") or "")
                                    == source_calendar_id
                                    and (local_task.get("gcal_source_summary") or "")
                                    == source_calendar_summary
                                    and (local_task.get("gcal_target_calendar_id") or "")
                                    == source_calendar_id
                                    and (local_task.get("gcal_sync_mode") or "local_owned")
                                    == "remote_mirror"
                                    and (local_task.get("gcal_remote_updated_at") or None)
                                    == remote_updated_at
                                )
                                if same_payload:
                                    needs_clear = int(
                                        local_task.get("gcal_dirty") or 0
                                    ) == 1 or bool(
                                        (local_task.get("gcal_sync_error") or "").strip()
                                    )
                                    if needs_clear:
                                        cleared = task_repo.mark_unified_task_gcal_synced(
                                            local_id,
                                            event_id=event.id,
                                            commit=True,
                                            source_calendar_id=source_calendar_id,
                                            source_calendar_summary=source_calendar_summary,
                                            target_calendar_id=source_calendar_id,
                                        )
                                        if cleared:
                                            calendar_committed_any = True
                                        else:
                                            calendar_apply_failures += 1
                                            pull_apply_failures += 1
                                            logger.warning(
                                                "Failed to clear gcal_dirty for unchanged event %s on calendar %s",
                                                event.id,
                                                source_calendar_id,
                                            )
                                    continue
                                changed_dates.add(_date_only(local_task.get("deadline")))

                        changed_dates.add(_date_only(start_str))
                        applied = gcal_db_adapter.update_task_from_gcal(
                            table,
                            local_id,
                            event.summary,
                            start_str,
                            end_str,
                            description,
                            location,
                            is_all_day,
                            bg_color,
                            remote_updated_at,
                            source_calendar_id=source_calendar_id,
                            source_calendar_summary=source_calendar_summary,
                            target_calendar_id=source_calendar_id,
                            commit=True,
                        )
                        if applied:
                            changed_any = True
                            pull_changes += 1
                            calendar_committed_any = True
                            # [2][9] save recurring/attendees extra fields after update
                            if table == "unified_task" and conn:
                                _upsert_recurring_series_if_needed(
                                    event, source_calendar_id, start_str
                                )
                                _save_event_extra_fields(
                                    conn, local_id, event, attendees_json, attachments_json
                                )
                            local_gcal_map[event_key] = (table, local_id)
                        else:
                            calendar_apply_failures += 1
                            pull_apply_failures += 1
                            logger.warning(
                                "Failed to apply remote update for Google event %s on calendar %s",
                                event.id,
                                source_calendar_id,
                            )
                    else:
                        if task_repo.is_gcal_event_in_task_trash(
                            event.id,
                            gcal_calendar_id=source_calendar_id,
                        ):
                            # If a matching remote event still exists but delete queue has
                            # no pending entry, treat the manual-trash marker as stale and
                            # restore it to local mirror.
                            if task_repo.is_gcal_delete_queued(event.id):
                                continue
                            purged = task_repo.purge_gcal_event_manual_trash(
                                event.id,
                                gcal_calendar_id=source_calendar_id,
                            )
                            if purged:
                                logger.info(
                                    "Cleared stale manual trash marker for event %s on calendar %s (%d row(s))",
                                    event.id,
                                    source_calendar_id,
                                    purged,
                                )
                            if task_repo.is_gcal_event_in_task_trash(
                                event.id,
                                gcal_calendar_id=source_calendar_id,
                            ):
                                continue
                        relink_local_id = (
                            gcal_db_adapter.find_unlinked_unified_task_for_gcal_payload(
                                event.summary,
                                start_str,
                                end_str,
                                all_day=is_all_day,
                                source_calendar_id=source_calendar_id,
                            )
                        )
                        if relink_local_id:
                            relinked = gcal_db_adapter.update_task_from_gcal(
                                "unified_task",
                                relink_local_id,
                                event.summary,
                                start_str,
                                end_str,
                                description,
                                location,
                                is_all_day,
                                bg_color,
                                remote_updated_at,
                                gcal_event_id=event.id,
                                source_calendar_id=source_calendar_id,
                                source_calendar_summary=source_calendar_summary,
                                target_calendar_id=source_calendar_id,
                                commit=True,
                            )
                            if relinked:
                                local_info = ("unified_task", relink_local_id)
                                local_gcal_map[event_key] = local_info
                                changed_dates.add(_date_only(start_str))
                                changed_any = True
                                pull_changes += 1
                                calendar_committed_any = True
                                # [2][9] save recurring/attendees extra fields after relink
                                if conn:
                                    _upsert_recurring_series_if_needed(
                                        event, source_calendar_id, start_str
                                    )
                                    _save_event_extra_fields(
                                        conn,
                                        relink_local_id,
                                        event,
                                        attendees_json,
                                        attachments_json,
                                    )
                                continue

                        inserted = gcal_db_adapter.insert_gcal_event_to_unified(
                            event.summary,
                            start_str,
                            end_str,
                            event.id,
                            description,
                            location,
                            is_all_day,
                            bg_color,
                            remote_updated_at,
                            source_calendar_id=source_calendar_id,
                            source_calendar_summary=source_calendar_summary,
                            target_calendar_id=source_calendar_id,
                            commit=True,
                        )
                        if inserted:
                            if isinstance(inserted, int) and inserted > 0:
                                local_info = ("unified_task", inserted)
                                local_gcal_map[event_key] = local_info
                            changed_dates.add(_date_only(start_str))
                            changed_any = True
                            pull_changes += 1
                            calendar_committed_any = True
                            # [2][9] save recurring/attendees extra fields after insert
                            if isinstance(inserted, int) and inserted > 0 and conn:
                                _upsert_recurring_series_if_needed(
                                    event, source_calendar_id, start_str
                                )
                                _save_event_extra_fields(
                                    conn, inserted, event, attendees_json, attachments_json
                                )
                        else:
                            calendar_apply_failures += 1
                            pull_apply_failures += 1
                            logger.warning(
                                "Failed to insert remote Google event %s on calendar %s into local DB",
                                event.id,
                                source_calendar_id,
                            )

                # 이벤트 루프 정상 완료 후 commit
                if calendar_committed_any and conn:
                    conn.commit()

            except Exception as _pull_exc:
                # BUG-H04: 루프 중 예외 시 rollback 후 해당 캘린더 skip
                calendar_committed_any = False
                if conn:
                    try:  # noqa: SIM105
                        conn.rollback()
                    except Exception:
                        pass
                calendar_apply_failures += 1
                pull_apply_failures += 1
                logger.exception(
                    "BUG-H04: Unexpected error processing events for calendar %s; "
                    "rolled back uncommitted changes",
                    sync_calendar_id,
                )

            if full_sync:
                calendar_prefix = f"{_normalize_calendar_id(sync_calendar_id)}::"
                missing_event_keys = [
                    key
                    for key in list(local_gcal_map.keys())
                    if isinstance(key, str)
                    and "::" in key
                    and key.startswith(calendar_prefix)
                    and key not in fetched_event_keys
                ]
                for missing_key in missing_event_keys:
                    info = local_gcal_map.get(missing_key)
                    if not info:
                        continue
                    table, local_id = info
                    if table == "unified_task":
                        local_task = task_repo.get_unified_task(local_id)
                        if local_task:
                            changed_dates.add(_date_only(local_task.get("deadline")))
                    if gcal_db_adapter.delete_task_by_gcal_id(table, local_id):
                        changed_any = True
                        pull_changes += 1
                        local_gcal_map.pop(missing_key, None)
                    else:
                        calendar_apply_failures += 1
                        pull_apply_failures += 1
                        logger.warning(
                            "Failed to archive/delete missing Google event key %s for local row %s",
                            missing_key,
                            local_id,
                        )

            # BUG-B04: cancelled 실패 카운터 갱신 (성공하면 리셋)
            if cancelled_fail_this_run:
                _settings_set(
                    app, _cancelled_fail_key, cancelled_fail_base + cancelled_fail_this_run
                )
            else:
                _settings_set(app, _cancelled_fail_key, 0)

            # apply 실패가 반복될 때 sync token이 영구 정체되는 것을 방지
            apply_fail_streak_key = f"gcal_apply_fail_streak::{sync_calendar_id}"
            apply_fail_streak = int(app.settings.value(apply_fail_streak_key, 0, type=int) or 0)
            force_advance_limit = 3
            if next_sync_token and calendar_apply_failures == 0:
                _settings_set(app, token_key, next_sync_token)
                _settings_set(app, apply_fail_streak_key, 0)
            elif next_sync_token and calendar_apply_failures:
                apply_fail_streak += 1
                _settings_set(app, apply_fail_streak_key, apply_fail_streak)
                if apply_fail_streak >= force_advance_limit:
                    logger.error(
                        "Forcing sync token advance for calendar %s after %d apply-failure runs "
                        "(failures this run: %d)",
                        sync_calendar_id,
                        apply_fail_streak,
                        calendar_apply_failures,
                    )
                    _settings_set(app, token_key, next_sync_token)
                    _settings_set(app, apply_fail_streak_key, 0)
                else:
                    logger.warning(
                        "GCal pull apply had %d failures for calendar %s; sync token advancement skipped "
                        "(streak %d/%d)",
                        calendar_apply_failures,
                        sync_calendar_id,
                        apply_fail_streak,
                        force_advance_limit,
                    )
            else:
                _settings_set(app, apply_fail_streak_key, 0)

        if pull_fetch_failures:
            app._last_gcal_sync_error = getattr(app.gcal_sync, "last_error_kind", None) or "fetch"
            app._last_gcal_sync_outcome = SYNC_OUTCOME_FAILED
            app._last_gcal_sync_stats["pull_fetch_failures"] = pull_fetch_failures
            if hasattr(app, "update_sync_status"):
                app.update_sync_status()
            if not silent:
                raise Exception("Google Calendar fetch failed for one or more calendars.")
            return False

        _settings_set(app, _bound_calendar_key(), cal_id)
        app._last_gcal_sync_stats["pull_changes"] = pull_changes
        app._last_gcal_sync_stats["pull_apply_failures"] = pull_apply_failures
        app._last_gcal_sync_stats["pull_fetch_failures"] = pull_fetch_failures

        if changed_any:
            current_date_str = app.current_date.toString("yyyy-MM-dd")
            refresh_left = current_date_str in changed_dates
            app._last_gcal_sync_changed_any = True
            app._last_gcal_sync_refresh_left = refresh_left
            if hasattr(app, "mark_panel_dirty"):
                app.mark_panel_dirty(left=refresh_left, center=True)

        if hasattr(app, "update_sync_status"):
            app.update_sync_status()
        app._last_gcal_sync_outcome = SYNC_OUTCOME_SUCCESS
        return True

    except Exception as e:
        app._last_gcal_sync_outcome = SYNC_OUTCOME_FAILED
        # [NEW] Include more detail in the last error message
        error_detail = str(e)
        if hasattr(app, "gcal_sync") and app.gcal_sync:
            kind = getattr(app.gcal_sync, "last_error_kind", None)
            msg = getattr(app.gcal_sync, "last_error_message", None)
            if kind or msg:
                error_detail = (
                    f"{error_detail} (GCal service: {kind or 'unknown'}: {msg or 'no msg'})"
                )

        app._last_gcal_sync_error = error_detail
        logger.exception("Unexpected error during Google Calendar sync: %s", error_detail)

        if hasattr(app, "update_sync_status"):
            app.update_sync_status()
        if not silent:
            raise e
        return False
    finally:
        if hasattr(app, "_gcal_sync_in_progress"):
            app._gcal_sync_in_progress = False


def resolve_drop_sync_task_ids(task_ids, copied_ids, action):
    raw_ids = copied_ids if action == "copy" else task_ids
    resolved = []
    for value in raw_ids or []:
        try:
            tid = int(value)
        except Exception:
            continue
        if tid not in resolved:
            resolved.append(tid)
    return resolved


def push_task_ids_to_google(app, task_ids):
    from calendar_app.infrastructure.db import task_repo as _task_repo
    from calendar_app.infrastructure.google_sync.helpers import sync_task_to_google

    pushed = 0
    default_target_calendar_id = _get_default_gcal_id(app)
    for tid in resolve_drop_sync_task_ids(task_ids, copied_ids=None, action="move"):
        task = _task_repo.get_unified_task(tid)
        if not task:
            continue
        target_calendar_id = _task_target_calendar_id(task, default_target_calendar_id)
        if not target_calendar_id:
            continue
        result = sync_task_to_google(
            app,
            task,
            create_if_missing=True,
            target_calendar_id=target_calendar_id,
        )
        if getattr(result, "success", False):
            pushed += 1
    return pushed


def handle_task_dropped(app, task_ids, target_date, target_time, action):
    from calendar_app.infrastructure.task_drop_service import handle_task_drop

    changed, copied_ids = handle_task_drop(app, task_ids, target_date, target_time, action)

    if changed > 0 and is_gcal_enabled(app.settings):
        push_ids = resolve_drop_sync_task_ids(task_ids, copied_ids, action)
        push_task_ids_to_google(app, push_ids)

    if hasattr(app, "wake_gcal_sync"):
        app.wake_gcal_sync()
    return changed, copied_ids
