# -*- coding: utf-8 -*-
"""Minimal Google Calendar sync helper compatibility module."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from calendar_app.infrastructure.google_sync.common import (
    google_create_idempotency_key,
)
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
    """Walk QObject parents to find the main application context."""
    current = ctx
    visited = set()
    fallback = ctx
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if hasattr(current, "gcal_sync") or (
            hasattr(current, "settings")
            and hasattr(current, "open_task_dialog")
            and hasattr(current, "open_modify_task_dialog")
        ):
            return current

        parent_getter = getattr(current, "parent", None)
        if not callable(parent_getter):
            parent_getter = getattr(current, "parentWidget", None)
        try:
            current = parent_getter() if callable(parent_getter) else None
        except RuntimeError:
            current = None
    return fallback


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
    """Recover a verified account alias without guessing another calendar's event."""
    candidates = []
    seen = set()
    attempted = _normalize_calendar_id(attempted_calendar_id) if attempted_calendar_id else None
    resolved_primary = str(_setting_value(settings, "gcal_primary_resolved_id", "") or "").strip()

    def _canonical(calendar_id):
        normalized = _normalize_calendar_id(calendar_id)
        return resolved_primary if normalized == "primary" and resolved_primary else normalized

    def _add(calendar_id):
        raw = str(calendar_id or "").strip()
        if not raw:
            return
        normalized = _normalize_calendar_id(raw)
        if normalized == attempted or normalized in seen:
            return
        if not attempted or _canonical(normalized) != _canonical(attempted):
            return
        seen.add(normalized)
        candidates.append(normalized)

    _add(_setting_value(settings, "gcal_calendar_id", None))
    _add(getattr(sync, "calendar_id", None))

    return candidates


def google_push_snapshot(task):
    """Fields whose change invalidates a queued Google write or its receipt."""
    fields = (
        "name",
        "summary",
        "deadline",
        "end_date",
        "description",
        "location",
        "bg_color",
        "all_day",
        "is_completed",
        "calendar_id",
        "gcal_source_calendar_id",
        "gcal_target_calendar_id",
        "gcal_event_id",
        "gcal_recurring_series_id",
        "created_at",
    )
    return {field: task[field] for field in fields if field in task}


def google_push_snapshot_matches(task, current):
    """Use the same stale-write guard for individual and batch creates."""
    return bool(current) and all(
        current.get(field) == value for field, value in google_push_snapshot(task).items()
    )


def google_remote_revision(task):
    """Reject the local-clock placeholder written by older app versions."""
    revision = str(task.get("gcal_remote_updated_at") or "").strip()
    last_synced = str(task.get("gcal_last_synced_at") or "").strip()
    return revision if revision and revision != last_synced else None


def _mark_task_synced(
    local_id,
    event_id=None,
    commit=True,
    source_calendar_id=None,
    target_calendar_id=None,
    remote_updated_at=None,
    expected_snapshot=None,
    created=False,
):
    if not local_id:
        return True
    try:
        from calendar_app.infrastructure.db import task_repo as _task_repo

        marked = _task_repo.mark_unified_task_gcal_synced(
            local_id,
            event_id=event_id,
            commit=commit,
            source_calendar_id=source_calendar_id,
            source_calendar_summary=_resolve_source_summary(source_calendar_id),
            target_calendar_id=target_calendar_id,
            remote_updated_at=remote_updated_at,
            expected_snapshot=expected_snapshot,
        )
        if marked:
            return True

        if created and event_id:
            conn = _task_repo.get_connection()
            if conn:
                current = conn.execute(
                    "SELECT gcal_event_id FROM unified_task WHERE id=?", (local_id,)
                ).fetchone()
                if current is None or (current[0] and current[0] != event_id):
                    # Reuse the persistent delete queue if the task was deleted
                    # or another create won while the HTTP request was in flight.
                    queued = _task_repo.queue_gcal_delete(
                        event_id, local_task_id=None, gcal_calendar_id=source_calendar_id
                    )
                    logger.warning(
                        "Created event %s outlived local task %s; cleanup queued=%s",
                        event_id,
                        local_id,
                        queued,
                    )
        return False
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
    expected_remote_updated_at=None,
):
    if not app:
        existing_id = task_data.get("gcal_event_id") if isinstance(task_data, dict) else None
        return SyncTaskResult(event_id=existing_id)

    settings = getattr(app, "settings", None)
    if not _is_gcal_enabled(settings):
        existing_id = task_data.get("gcal_event_id") if isinstance(task_data, dict) else None
        return SyncTaskResult(event_id=existing_id)

    sync = getattr(app, "gcal_sync", None)
    if sync is not None and getattr(sync, "_account_identity_mismatch", False) is True:
        existing_id = task_data.get("gcal_event_id") if isinstance(task_data, dict) else None
        code = getattr(sync, "_account_identity_error_kind", "account_mismatch")
        return SyncTaskResult(
            event_id=existing_id, success=False, error_kind=code, error_message=code
        )
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
    if effective_calendar_id.split("::", 1)[0].lower() in {"outlook", "caldav"}:
        return SyncTaskResult(event_id=None, success=True, error_kind="skipped_non_gcal")
    # Explicit non-gcal namespace task(local::/ics::/etc) should not fallback-push to default Google calendar.
    if (
        effective_calendar_id
        and "::" in effective_calendar_id
        and not effective_calendar_id.startswith("gcal::")
        and (not has_explicit_gcal_route or not existing_id)
    ):
        _mark_task_synced(local_id, commit=commit, source_calendar_id=None, target_calendar_id=None)
        return SyncTaskResult(event_id=None, success=True, error_kind="skipped_non_gcal")

    if local_id and not google_push_snapshot_matches(task_data, fresh):
        return SyncTaskResult(
            event_id=existing_id,
            success=False,
            error_kind="local_state",
            error_message="local_task_changed_before_push",
        )

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

    write_metadata = {}
    write_snapshot = google_push_snapshot(fresh or task_data)
    if existing_id and not expected_remote_updated_at:
        stored_revision = google_remote_revision(fresh or task_data)
        # Older versions wrote the local sync clock into both columns. Such a
        # value cannot authorize an overwrite: the regular pull must reconcile it.
        if not stored_revision:
            return SyncTaskResult(
                event_id=existing_id,
                success=False,
                error_kind="conflict",
                error_message="remote_revision_requires_pull",
            )
        expected_remote_updated_at = stored_revision

    calendar_move_pending = False
    if existing_id:
        # ── Calendar move detection ─────────────────────────────────────────
        # 사용자가 일정 수정 다이얼로그에서 캘린더를 변경한 경우, Google API의
        # update_event 만으로는 캘린더 간 이동이 안 된다. previous_gcal_calendar_id
        # 가 명시되었거나 fresh DB 의 gcal_source_calendar_id 가 새 target 과 다르면
        # events.move 를 먼저 호출한 뒤 update_event 로 메타데이터를 갱신한다.
        try:
            _prev_raw = (
                task_data.get("_previous_gcal_calendar_id")
                or (fresh or {}).get("gcal_source_calendar_id")
                or task_data.get("gcal_source_calendar_id")
            )
            _prev_gcal_id = _normalize_calendar_id(_prev_raw) if _prev_raw else None
            if _prev_gcal_id and source_calendar_id and _prev_gcal_id != source_calendar_id:
                calendar_move_pending = True
                move_metadata = {}
                moved_ok = sync.move_event(
                    existing_id,
                    _prev_gcal_id,
                    source_calendar_id,
                    expected_remote_updated_at=expected_remote_updated_at,
                    result_metadata=move_metadata,
                )
                if moved_ok:
                    expected_remote_updated_at = (
                        move_metadata.get("remote_updated_at") or expected_remote_updated_at
                    )
                    logger.info(
                        "Moved GCal event %s from %s to %s (task %s)",
                        existing_id,
                        _prev_gcal_id,
                        source_calendar_id,
                        local_id,
                    )
                else:
                    # A missing source may mean a previous move completed before
                    # the local mark failed. Only the intended destination may
                    # confirm that retry; transient failures remain pending.
                    move_error = getattr(sync, "last_error_kind", None)
                    if move_error != "not_found":
                        return SyncTaskResult(
                            event_id=existing_id,
                            success=False,
                            error_kind=move_error or "calendar_move",
                            error_message="calendar_move_failed",
                        )
        except Exception:
            logger.exception("Calendar move failed; preserving the pending destination")
            return SyncTaskResult(
                event_id=existing_id,
                success=False,
                error_kind="calendar_move",
                error_message="calendar_move_failed",
            )

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
        revision_kwargs = (
            {"revision_event_id": existing_id} if _update_target_id != existing_id else {}
        )
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
            expected_remote_updated_at=expected_remote_updated_at,
            result_metadata=write_metadata,
            **revision_kwargs,
        )
        if ok:
            marked = _mark_task_synced(
                local_id,
                existing_id,
                commit=commit,
                source_calendar_id=source_calendar_id_for_mark,
                target_calendar_id=source_calendar_id_for_mark,
                remote_updated_at=write_metadata.get("remote_updated_at"),
                expected_snapshot=write_snapshot,
            )
            if not marked:
                logger.warning("Failed to mark task %s as synced after update", local_id)
                if calendar_move_pending:
                    return SyncTaskResult(
                        event_id=existing_id,
                        success=False,
                        error_kind="calendar_move_local_state",
                        error_message="calendar_move_local_state_not_saved",
                    )
                return SyncTaskResult(
                    event_id=existing_id,
                    success=False,
                    error_kind="local_state",
                    error_message="remote_updated_but_local_mark_failed",
                )
            return SyncTaskResult(event_id=existing_id, success=True)
        if getattr(sync, "last_error_kind", None) != "not_found":
            return SyncTaskResult(
                event_id=existing_id,
                success=False,
                error_kind=getattr(sync, "last_error_kind", None) or "update",
                error_message=getattr(sync, "last_error_message", None),
            )
        if calendar_move_pending:
            # Updating an old calendar would silently undo the user's move,
            # while creating in the destination could duplicate the old event.
            return SyncTaskResult(
                event_id=existing_id,
                success=False,
                error_kind="calendar_move_unconfirmed",
                error_message="calendar_move_destination_unconfirmed",
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
                expected_remote_updated_at=expected_remote_updated_at,
                result_metadata=write_metadata,
                **revision_kwargs,
            )
            if not recovered:
                continue
            marked = _mark_task_synced(
                local_id,
                existing_id,
                commit=commit,
                source_calendar_id=recovery_calendar_id,
                target_calendar_id=recovery_calendar_id,
                remote_updated_at=write_metadata.get("remote_updated_at"),
                expected_snapshot=write_snapshot,
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
                    success=False,
                    error_kind="local_state",
                    error_message="remote_updated_but_local_mark_failed",
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
                if not fresh:
                    return SyncTaskResult(
                        event_id=existing_id,
                        success=False,
                        error_kind="local_state",
                        error_message="local_task_deleted_before_create",
                    )
                if not google_push_snapshot_matches(task_data, fresh):
                    return SyncTaskResult(
                        event_id=existing_id,
                        success=False,
                        error_kind="local_state",
                        error_message="local_task_changed_before_create",
                    )
                write_snapshot = google_push_snapshot(fresh)
                current_event_id = str(fresh.get("gcal_event_id") or "").strip() or None
                if current_event_id != existing_id:
                    return SyncTaskResult(
                        event_id=current_event_id,
                        success=False,
                        error_kind="local_state",
                        error_message="local_task_changed_before_create",
                    )
            except Exception:
                logger.warning(
                    "DB re-read failed for task %s before Google create; deferring the write",
                    local_id,
                )
                return SyncTaskResult(
                    event_id=existing_id,
                    success=False,
                    error_kind="db_reread_failed",
                    error_message="pre_create_db_reread_error",
                )

        # Build idempotency key from task identity so that GCal server rejects
        # a duplicate insert (HTTP 409) if this create_event() call is retried.
        # updated_at changes even when merely recording a failed sync, so it
        # cannot identify a retried create after the remote write succeeded.
        _ikey = google_create_idempotency_key(fresh or task_data)

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
            result_metadata=write_metadata,
        )
        if created:
            _persist_gcal_event_id(task_data, created)
            marked = _mark_task_synced(
                local_id,
                created,
                commit=commit,
                source_calendar_id=source_calendar_id,
                target_calendar_id=source_calendar_id,
                remote_updated_at=write_metadata.get("remote_updated_at"),
                expected_snapshot=write_snapshot,
                created=True,
            )
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
    if not sync or not event_id or getattr(sync, "_account_identity_mismatch", False) is True:
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
