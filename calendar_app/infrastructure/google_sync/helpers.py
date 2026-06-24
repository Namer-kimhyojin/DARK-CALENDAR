"""Minimal Google Calendar sync helper compatibility module."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import sqlite3

from calendar_app.infrastructure.google_sync.common import (
    is_gcal_enabled as _common_is_gcal_enabled,
)
from calendar_app.infrastructure.google_sync.common import (
    normalize_calendar_id as _normalize_calendar_id,
)
from calendar_app.infrastructure.google_sync.common import (
    resolve_calendar_source_summary as _resolve_calendar_source_summary,
)
from calendar_app.infrastructure.google_sync.common import (
    resolve_task_target_calendar_id as _resolve_task_target_calendar_id,
)
from calendar_app.shared.google_color_palette import hex_to_color_id

logger = logging.getLogger(__name__)


@dataclass
class SyncTaskResult:
    event_id: str | None = None
    changed: bool = False
    success: bool = True
    error_kind: str | None = None
    error_message: str | None = None
    auto_healed: bool = False


def resolve_app_context(ctx):
    return ctx


def _setting_value(settings, key, default=None):
    if settings is None:
        return default
    if hasattr(settings, "value"):
        try:
            return settings.value(key, default)
        except Exception:
            return default
    if isinstance(settings, dict):
        return settings.get(key, default)
    return getattr(settings, key, default)


def _is_gcal_enabled(settings):
    return _common_is_gcal_enabled(settings)


def _persist_gcal_event_id(task_data, event_id):
    if isinstance(task_data, dict):
        task_data["gcal_event_id"] = event_id


def _resolve_source_summary(source_calendar_id):
    return _resolve_calendar_source_summary(source_calendar_id)


def _candidate_recovery_calendar_ids(sync, settings, attempted_calendar_id=None):
    candidates = []
    seen = set()
    attempted = _normalize_calendar_id(attempted_calendar_id) if attempted_calendar_id else None

    def _add(calendar_id):
        raw = str(calendar_id or "").strip()
        if not raw:
            return
        normalized = _normalize_calendar_id(raw)
        if normalized == attempted or normalized in seen:
            return
        seen.add(normalized)
        candidates.append(normalized)

    _add(_setting_value(settings, "gcal_calendar_id", None))
    _add(getattr(sync, "calendar_id", None))

    if hasattr(sync, "list_accessible_calendars"):
        try:
            for row in sync.list_accessible_calendars() or []:
                if isinstance(row, dict):
                    _add(row.get("id"))
                else:
                    _add(getattr(row, "id", None))
        except Exception:
            logger.exception("Failed to enumerate accessible calendars for event recovery")

    return candidates


def _mark_task_synced(
    local_id, event_id=None, commit=True, source_calendar_id=None, target_calendar_id=None
):
    if not local_id:
        return True
    try:
        from calendar_app.infrastructure.db import task_repo as _task_repo

        return _task_repo.mark_unified_task_gcal_synced(
            local_id,
            event_id=event_id,
            commit=commit,
            source_calendar_id=source_calendar_id,
            source_calendar_summary=_resolve_source_summary(source_calendar_id),
            target_calendar_id=target_calendar_id,
        )
    except Exception:
        logger.exception("Failed to mark local task %s as Google-synced", local_id)
        return False


def sync_task_to_google(
    app,
    task_data,
    create_if_missing=True,
    commit=True,
    target_calendar_id=None,
    recurring_scope=None,
):
    if not app:
        existing_id = task_data.get("gcal_event_id") if isinstance(task_data, dict) else None
        return SyncTaskResult(event_id=existing_id)

    settings = getattr(app, "settings", None)
    if not _is_gcal_enabled(settings):
        existing_id = task_data.get("gcal_event_id") if isinstance(task_data, dict) else None
        return SyncTaskResult(event_id=existing_id)

    sync = getattr(app, "gcal_sync", None)
    if not sync or not getattr(sync, "is_authenticated", False):
        existing_id = task_data.get("gcal_event_id") if isinstance(task_data, dict) else None
        return SyncTaskResult(event_id=existing_id, success=False, error_kind="auth_required")

    task_data = task_data or {}
    if str(task_data.get("type") or "").strip() == "routine":
        existing_id = str(task_data.get("gcal_event_id") or "").strip() or None
        return SyncTaskResult(event_id=existing_id, success=True, error_kind="skipped_routine")
    existing_id = str(task_data.get("gcal_event_id") or "").strip() or None
    local_id = task_data.get("id")
    fresh = None

    # If no gcal_event_id in passed data, re-read from DB to pick up a value
    # written by a concurrent create worker (race condition guard).
    if local_id:
        try:
            from calendar_app.infrastructure.db import task_repo as _task_repo

            fresh = _task_repo.get_unified_task(local_id)
            if not existing_id and fresh and fresh.get("gcal_event_id"):
                existing_id = str(fresh.get("gcal_event_id") or "").strip() or None
        except Exception:
            pass

    effective_calendar_id = str(task_data.get("calendar_id") or "").strip()
    if not effective_calendar_id and fresh:
        effective_calendar_id = str(fresh.get("calendar_id") or "").strip()
    has_explicit_gcal_route = bool(
        str(task_data.get("gcal_target_calendar_id") or "").strip()
        or str(task_data.get("gcal_source_calendar_id") or "").strip()
        or str((fresh or {}).get("gcal_target_calendar_id") or "").strip()
        or str((fresh or {}).get("gcal_source_calendar_id") or "").strip()
    )
    # Explicit non-gcal namespace task(local::/ics::/etc) should not fallback-push to default Google calendar.
    if (
        effective_calendar_id
        and "::" in effective_calendar_id
        and not effective_calendar_id.startswith("gcal::")
        and not has_explicit_gcal_route
    ):
        _mark_task_synced(local_id, commit=commit, source_calendar_id=None, target_calendar_id=None)
        return SyncTaskResult(event_id=None, success=True, error_kind="skipped_non_gcal")

    summary = task_data.get("name") or task_data.get("summary") or "Untitled"
    start_iso = task_data.get("deadline") or ""
    end_iso = task_data.get("end_date") or ""
    description = task_data.get("description") or ""
    location = task_data.get("location") or ""
    color_id = hex_to_color_id(task_data.get("bg_color"), sync)
    all_day = bool(task_data.get("all_day"))
    # [10] completion sync
    is_completed = bool(int(task_data.get("is_completed") or 0))
    hide_completed_value = _setting_value(settings, "gcal_hide_completed_in_gcal", "false")
    hide_completed = (
        hide_completed_value.lower() == "true"
        if isinstance(hide_completed_value, str)
        else bool(hide_completed_value)
    )

    raw_target = _resolve_task_target_calendar_id(
        {"gcal_target_calendar_id": target_calendar_id},
        default_calendar_id=False,
    )
    if raw_target is None:
        raw_target = _resolve_task_target_calendar_id(task_data, default_calendar_id=False)
    if raw_target is None and fresh:
        raw_target = _resolve_task_target_calendar_id(fresh, default_calendar_id=False)
    has_explicit_source = raw_target is not None
    if raw_target is None and not existing_id:
        raw_target = _normalize_calendar_id(getattr(sync, "calendar_id", ""))

    source_calendar_id = raw_target
    if not source_calendar_id:
        _sync_cal = str(getattr(sync, "calendar_id", "") or "").strip()
        if not _sync_cal:
            from calendar_app.infrastructure.google_sync.common import get_default_gcal_calendar_id

            _sync_cal = get_default_gcal_calendar_id()
        source_calendar_id = _normalize_calendar_id(_sync_cal)
    source_calendar_id_for_mark = (
        source_calendar_id if (has_explicit_source or not existing_id) else None
    )

    if existing_id:
        # [2] scope=all → update the master recurring event instead of just this instance
        _update_target_id = existing_id
        if recurring_scope == "all" and local_id:
            try:
                from calendar_app.infrastructure.db import task_repo as _task_repo2

                _fresh2 = _task_repo2.get_unified_task(local_id)
                _series_id = (_fresh2 or {}).get("gcal_recurring_series_id")
                if _series_id:
                    _update_target_id = _series_id
                    logger.info(
                        "sync_task_to_google: scope=all, updating master series %s (instance was %s)",
                        _series_id,
                        existing_id,
                    )
            except Exception:
                pass
        ok = sync.update_event(
            _update_target_id,
            summary,
            start_iso,
            end_iso,
            description,
            location,
            color_id,
            all_day,
            calendar_id=source_calendar_id,
            completed=is_completed,
            hide_completed=hide_completed,
        )
        if ok:
            marked = _mark_task_synced(
                local_id,
                existing_id,
                commit=commit,
                source_calendar_id=source_calendar_id_for_mark,
                target_calendar_id=source_calendar_id_for_mark,
            )
            if not marked:
                logger.warning("Failed to mark task %s as synced after update", local_id)
            return SyncTaskResult(event_id=existing_id, success=True)
        if getattr(sync, "last_error_kind", None) != "not_found":
            return SyncTaskResult(
                event_id=existing_id,
                success=False,
                error_kind=getattr(sync, "last_error_kind", None) or "update",
                error_message=getattr(sync, "last_error_message", None),
            )

        recovery_candidates = _candidate_recovery_calendar_ids(sync, settings, source_calendar_id)
        for recovery_calendar_id in recovery_candidates:
            recovered = sync.update_event(
                _update_target_id,
                summary,
                start_iso,
                end_iso,
                description,
                location,
                color_id,
                all_day,
                calendar_id=recovery_calendar_id,
                completed=is_completed,
                hide_completed=hide_completed,
            )
            if not recovered:
                continue
            marked = _mark_task_synced(
                local_id,
                existing_id,
                commit=commit,
                source_calendar_id=recovery_calendar_id,
                target_calendar_id=recovery_calendar_id,
            )
            if not marked:
                logger.warning(
                    "Recovered Google event %s on calendar %s but failed to mark task %s as synced",
                    existing_id,
                    recovery_calendar_id,
                    local_id,
                )
            return SyncTaskResult(
                event_id=existing_id,
                success=True,
                auto_healed=True,
            )

        if not has_explicit_source:
            logger.warning(
                "Skipped auto-create for task %s event %s because source calendar is ambiguous",
                local_id,
                existing_id,
            )
            return SyncTaskResult(
                event_id=existing_id,
                success=False,
                error_kind="calendar_ambiguous",
                error_message="existing_event_calendar_unknown",
            )

    if create_if_missing:
        # BUG-C01: create_event() 직전 DB를 재확인하여 중복 생성 방지.
        # 이전 push 시도에서 GCal 생성은 성공했지만 mark_synced DB 커밋이 실패했을 수 있음.
        if local_id:
            try:
                from calendar_app.infrastructure.db import task_repo as _task_repo

                fresh = _task_repo.get_unified_task(local_id)
                if fresh and fresh.get("gcal_event_id"):
                    existing_id = fresh["gcal_event_id"]
                    logger.info(
                        "BUG-C01 guard: found existing gcal_event_id %s for task %s before create; "
                        "switching to update to prevent duplicate",
                        existing_id,
                        local_id,
                    )
                    ok = sync.update_event(
                        existing_id,
                        summary,
                        start_iso,
                        end_iso,
                        description,
                        location,
                        color_id,
                        all_day,
                        calendar_id=source_calendar_id,
                    )
                    if ok:
                        _mark_task_synced(
                            local_id,
                            existing_id,
                            commit=commit,
                            source_calendar_id=source_calendar_id_for_mark,
                            target_calendar_id=source_calendar_id_for_mark,
                        )
                        return SyncTaskResult(event_id=existing_id, success=True, auto_healed=True)
            except Exception:
                # DB re-read itself failed: skip create to avoid potential
                # duplicate. Will be retried in the next sync cycle.
                logger.warning(
                    "BUG-C01 guard: DB re-read failed for task %s before create; "
                    "skipping create to avoid duplicate (will retry next cycle)",
                    local_id,
                )
                return SyncTaskResult(
                    event_id=None,
                    success=False,
                    error_kind="db_reread_failed",
                    error_message="pre_create_db_reread_error",
                )

        # Build idempotency key from task identity so that GCal server rejects
        # a duplicate insert (HTTP 409) if this create_event() call is retried.
        # Format: task_{local_id}_{updated_at_compact} -> sanitised to [a-v0-9].
        _ikey = None
        if local_id:
            _updated_raw = (
                str((fresh or task_data).get("updated_at") or "")
                .replace("-", "")
                .replace(":", "")
                .replace(" ", "")
                .replace("T", "")[:14]
            )
            _ikey = f"task{local_id}{_updated_raw}" if _updated_raw else f"task{local_id}"

        created = sync.create_event(
            summary,
            start_iso,
            end_iso,
            description,
            location,
            color_id,
            all_day,
            calendar_id=source_calendar_id,
            idempotency_key=_ikey,
        )
        if created:
            _persist_gcal_event_id(task_data, created)
            try:
                marked = _mark_task_synced(
                    local_id,
                    created,
                    commit=commit,
                    source_calendar_id=source_calendar_id,
                    target_calendar_id=source_calendar_id,
                )
            except sqlite3.IntegrityError:
                # BUG-C03: concurrent worker already wrote gcal_event_id -> UNIQUE violation.
                # The event we just created in GCal is now orphaned; queue it for deletion.
                try:
                    from calendar_app.infrastructure.db import task_repo as _task_repo

                    fresh2 = _task_repo.get_unified_task(local_id)
                    winner_id = (fresh2 or {}).get("gcal_event_id") or created
                except Exception:
                    winner_id = created
                # If winner differs from what we just created, our event is orphaned -> delete
                if winner_id != created:
                    try:
                        from calendar_app.infrastructure.db import task_repo as _task_repo

                        _task_repo.queue_gcal_delete(
                            created,
                            local_task_id=None,
                            gcal_calendar_id=source_calendar_id,
                        )
                        logger.warning(
                            "BUG-C03: queued orphan GCal event %s for deletion "
                            "(task %s already has winner %s)",
                            created,
                            local_id,
                            winner_id,
                        )
                    except Exception:
                        logger.warning(
                            "BUG-C03: could not queue orphan GCal event %s for deletion; "
                            "manual cleanup may be needed",
                            created,
                        )
                else:
                    logger.warning(
                        "BUG-C03: IntegrityError on mark_synced for task %s; "
                        "concurrent create detected. Winner gcal_event_id: %s",
                        local_id,
                        winner_id,
                    )
                return SyncTaskResult(event_id=winner_id, success=True, auto_healed=True)
            if not marked:
                # GCal event created but DB mark_synced failed. Log event_id for manual reconciliation.
                logger.error(
                    "BUG-C01: GCal event %s created for task %s but DB mark_synced failed. "
                    "Manual reconciliation may be needed to prevent duplicate retries.",
                    created,
                    local_id,
                )
                return SyncTaskResult(
                    event_id=created,
                    success=False,
                    changed=True,
                    error_kind="local_state",
                    error_message="remote_created_but_local_mark_failed",
                    auto_healed=False,
                )

            # Set auto_heal flag when event was re-created after not_found.
            was_healed = getattr(sync, "last_error_kind", None) == "not_found"
            return SyncTaskResult(
                event_id=created,
                changed=(created != existing_id),
                success=True,
                auto_healed=was_healed,
            )
        return SyncTaskResult(
            event_id=existing_id,
            success=False,
            error_kind=getattr(sync, "last_error_kind", None) or "create",
            error_message=getattr(sync, "last_error_message", None),
        )

    return SyncTaskResult(event_id=existing_id, success=False, error_kind="missing_remote")


def delete_task_from_google(app, event_id, calendar_id=None):
    sync = getattr(app, "gcal_sync", None)
    event_id = str(event_id or "").strip()
    if not sync or not event_id:
        return False
    try:
        return bool(sync.delete_event(event_id, calendar_id=calendar_id))
    except Exception:
        return False


def queue_task_sync_to_google(app, task_data, create_if_missing=True):
    return sync_task_to_google(app, task_data, create_if_missing=create_if_missing)


def queue_task_delete_from_google(
    app, event_id, local_task_id=None, gcal_calendar_id=None, recurring_scope=None
):
    event_id = str(event_id or "").strip()
    if not event_id:
        return False
    try:
        from calendar_app.infrastructure.db import task_repo as _task_repo

        return bool(
            _task_repo.queue_gcal_delete(
                event_id,
                local_task_id=local_task_id,
                gcal_calendar_id=gcal_calendar_id,
                recurring_scope=recurring_scope,
            )
        )
    except Exception:
        return False
