# -*- coding: utf-8 -*-
"""Connect the weekly time grid to the existing editors and sync queues."""

from __future__ import annotations

import logging
import math

from PyQt6.QtCore import QDate, QDateTime, QTime

from calendar_app.application import week_planner_usecases
from calendar_app.domain.calendar_visibility import CalendarVisibility
from calendar_app.infrastructure.db import calendar_repo, task_repo
from calendar_app.infrastructure.google_sync.common import is_gcal_enabled
from calendar_app.infrastructure.google_sync.push_queue import gcal_push_queue
from calendar_app.infrastructure.i18n import t

logger = logging.getLogger(__name__)


def set_week_layout(app, layout: str) -> None:
    """Persist the weekly presentation without changing its selected date."""
    app.cal_week_layout = "date" if layout == "date" else "time"
    app.settings.setValue("cal_week_layout", app.cal_week_layout)
    app.schedule_panel_refresh(center=True)


def prepare_week_tasks(tasks, calendar_rows, primary_gcal_id="primary") -> list[dict]:
    """Detach render records and apply current calendar colors and permissions."""
    policy = CalendarVisibility(calendar_rows, primary_gcal_id)
    records = []
    for task in policy.filter_tasks(tasks):
        row = dict(task)
        calendar_id = str(row.get("calendar_id") or "")
        if not calendar_id and row.get("gcal_source_calendar_id"):
            calendar_id = f"gcal::{row['gcal_source_calendar_id']}"
        calendar = policy.calendar_for_task(row)
        row["read_only"] = bool(
            row.get("read_only")
            or row.get("is_subscription")
            or calendar_id.startswith("ics::")
            or calendar_repo.is_calendar_row_read_only(calendar)
        )
        row["bg_color"] = row.get("bg_color") or (calendar or {}).get("color")
        records.append(row)
    return records


def create_week_schedule(app, date_str: str, start_minutes: int, duration_minutes: int) -> None:
    """Open the normal create editor with the exact dragged time range."""
    date = QDate.fromString(date_str, "yyyy-MM-dd")
    if not date.isValid() or not 0 <= start_minutes < 1440 or duration_minutes < 15:
        return
    start = QDateTime(date, QTime(0, 0)).addSecs(start_minutes * 60)
    end = start.addSecs(duration_minutes * 60)
    app.open_task_dialog(
        initial_date=start.date(),
        task_type="schedule",
        initial_time=start.time(),
        end_date=end.date(),
        end_time=end.time(),
    )


def edit_week_schedule(app, task: dict) -> None:
    if task.get("read_only") or task.get("is_subscription"):
        from calendar_app.presentation.calendar.month_renderer import _show_subscription_detail

        _show_subscription_detail(task, app)
        return
    app.open_modify_task_dialog(int(task["id"]))


def set_week_interaction(app, active: bool) -> None:
    """Defer background re-renders until the pointer gesture is finished."""
    app._is_dragging = bool(active)
    if not active and getattr(app, "_drag_pending_refresh", False):
        app._drag_pending_refresh = False
        app.schedule_panel_refresh(left=True, center=True)


def _notify(app, title: str, message: str) -> None:
    if hasattr(app, "show_toast"):
        app.show_toast(title, message)


def reschedule_week_schedule(
    app, task: dict, date_str: str, start_minutes: int, duration_minutes: int
) -> bool:
    """Save one period atomically, then use the normal calendar sync triggers."""
    try:
        task_id = int(task.get("id") or 0)
        current = task_repo.get_unified_task(task_id) if task_id > 0 else None
        reason = week_planner_usecases.scheduling_block_reason(task)
        if current:
            reason = reason or week_planner_usecases.scheduling_block_reason(current)
            if calendar_repo.is_calendar_read_only(current.get("calendar_id")):
                reason = "read_only"
        if reason == "read_only":
            _notify(
                app,
                t("dialog.task.calendar_read_only", "읽기 전용 캘린더"),
                t("gcal.errors.forbidden", "해당 캘린더에 대한 수정 권한이 없습니다."),
            )
            return False
        if reason == "recurring":
            _notify(
                app,
                t("week_planner.recurring_title", "반복 일정"),
                t("week_planner.recurring_hint", "반복 일정은 상세 편집에서 변경해 주세요."),
            )
            return False
        if not current:
            _notify(
                app,
                t("dialog.task.save_failed", "저장 실패"),
                t("dialog.task.not_found", "일정을 찾을 수 없습니다."),
            )
            return False
        interval = week_planner_usecases.normalized_task_interval(current)
        preserve_duration = bool(
            interval
            and not current.get("all_day")
            and duration_minutes == math.ceil((interval[1] - interval[0]).total_seconds() / 60)
        )
        saved = week_planner_usecases.reschedule_task_and_get_sync_payload(
            task_repo,
            task_id,
            date_str,
            start_minutes,
            duration_minutes,
            is_calendar_read_only=calendar_repo.is_calendar_read_only,
            preserve_duration=preserve_duration,
        )
        if not saved:
            _notify(
                app,
                t("dialog.task.save_failed", "저장 실패"),
                t("dialog.task.save_error_db", "데이터베이스 업데이트에 실패했습니다."),
            )
            return False
        if hasattr(app, "wake_calendar_sync"):
            app.wake_calendar_sync()
        if is_gcal_enabled(app.settings):
            gcal_push_queue.enqueue(app, saved, create_if_missing=True)
        return True
    except Exception:
        logger.exception("Weekly time-grid save failed task_id=%s", task.get("id"))
        _notify(
            app,
            t("dialog.task.save_failed", "저장 실패"),
            t("dialog.task.save_error_db", "데이터베이스 업데이트에 실패했습니다."),
        )
        return False
    finally:
        # The grid previews the proposed position; rebuild from persisted data
        # after failure as well so a rejected gesture never looks like a save.
        app.schedule_panel_refresh(left=True, center=True, right=True)
