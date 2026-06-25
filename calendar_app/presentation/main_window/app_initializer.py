"""OverlayApp initialization helpers."""

from __future__ import annotations

import logging

from PyQt6.QtCore import QDate, QSettings, Qt, QTimer

from calendar_app.infrastructure.google_sync.common import ensure_gcal_startup_defaults
from calendar_app.presentation.main_window.ui_builder import setup_idle_lock_ui, setup_main_ui
from calendar_app.preset_manager import PresetManager

logger = logging.getLogger(__name__)


def initialize_overlay_app(app) -> None:
    app.settings = QSettings("kimhyojin", "Dark Calendar")
    ensure_gcal_startup_defaults(app.settings)
    _initialize_focus_timer_defaults(app)
    app.old_pos_drag = None
    app.is_visible = True
    app.is_focus_mode = False
    app.is_fullscreen = False
    app._resize_dir = None
    app._screen_fill_active = False
    app._last_clicked_date = None
    app.cal_show_weekends = app.settings.value("cal_show_weekends", True, type=bool)
    app.cal_start_monday = app.settings.value("cal_start_monday", True, type=bool)
    app.cal_show_month = app.settings.value("cal_show_month", False, type=bool)
    app.cal_show_weekday = app.settings.value("cal_show_weekday", False, type=bool)
    app.view_mode_state = app.settings.value("view_mode_state", "monthly", type=str)
    app.setMouseTracking(True)
    app.preset_manager = PresetManager(app)
    app.selected_task_ids = set()
    app.selected_directive_ids = set()
    app._panel_task_frames = {}
    app._panel_directive_frames = {}
    import json as _json

    _raw_exp = app.settings.value("expanded_task_ids", "[]")
    try:
        app.expanded_tids = set(_json.loads(str(_raw_exp)))
    except Exception:
        app.expanded_tids = set()
    del _json
    app._latest_agenda_data = None
    app._latest_calendar_range_data = None
    app._latest_directive_data = None
    app._last_clicked_task_id = None

    app.gcal_sync = None
    app._bg_workers = []
    app._sync_worker = None
    app._auth_worker = None
    app._is_shutting_down = False
    app._is_dragging = False

    from calendar_app.domain.task_constants import load_custom_labels

    load_custom_labels()

    app.is_locked = app.settings.value("is_locked", False, type=bool)
    last_date_str = app.settings.value("last_working_date")
    if last_date_str:
        app.current_date = QDate.fromString(last_date_str, Qt.DateFormat.ISODate)
    else:
        app.current_date = QDate.currentDate()

    setup_main_ui(app)
    setup_idle_lock_ui(app)
    _setup_command_palette(app)
    app.init_overlay_manager()
    _initialize_routine_rollover(app)

    if hasattr(app, "lock_btn"):
        app.lock_btn.setChecked(app.is_locked)
        app.toggle_lock_mode()

    app.generate_today_routines()
    app.init_gcal_sync_timer()
    _initialize_alarm_checker(app)
    _initialize_daily_summary(app)

    from calendar_app.infrastructure.runtime import infra_manager

    infra_manager.setup_app_infrastructure(app)
    app.check_first_time_setup()
    app.refresh_gcal_sync_state(authenticate_silently=True)

    # Global icon is now set in bootstrap.py

    # Final post-startup recovery: re-dock/refresh panels if legacy window state was broken.
    QTimer.singleShot(0, lambda: _force_restore_docks_and_panels(app))


def _initialize_focus_timer_defaults(app) -> None:
    defaults = {
        "focus_mode_type": "pomodoro",
        "pomodoro_focus_minutes": 25,
        "pomodoro_short_break_minutes": 5,
        "pomodoro_long_break_minutes": 15,
        "pomodoro_long_break_every": 4,
        "pomodoro_auto_start_break": True,
        "pomodoro_auto_start_focus": True,
        "pomodoro_daily_goal_cycles": 8,
    }
    for key, default in defaults.items():
        if app.settings.value(key, None) is None:
            app.settings.setValue(key, default)

    migration_key = "pomodoro_auto_start_transition_defaults_v2"
    if app.settings.value(migration_key, None) is None:
        app.settings.setValue("pomodoro_auto_start_break", True)
        app.settings.setValue("pomodoro_auto_start_focus", True)
        app.settings.setValue(migration_key, True)


def _initialize_alarm_checker(app) -> None:
    try:
        from calendar_app.presentation.widgets.alarm_checker import TaskAlarmChecker

        app.task_alarm_checker = TaskAlarmChecker(app, parent=app)
    except Exception:
        logger.exception("Failed to initialize TaskAlarmChecker")


def _initialize_routine_rollover(app) -> None:
    try:
        from calendar_app.application import routine_advanced_service as routine_service
        from calendar_app.infrastructure.db import db_repository as legacy_db_repository

        legacy_db_repository.register_checklist_routine_rollover_hook(
            routine_service.auto_create_next_routine
        )

        created = routine_service.ensure_overdue_routines_rollover()
        if created:
            app.schedule_panel_refresh(left=True, center=True, right=True)
    except Exception:
        logger.exception("Failed initial overdue routine rollover")


def _force_restore_docks_and_panels(app) -> None:
    try:
        # dock_manager is now self (OverlayApp), no separate show() needed.
        if hasattr(app, "focus_frame"):
            app.focus_frame.hide()

        dock_specs = [
            ("left_dock", Qt.DockWidgetArea.LeftDockWidgetArea),
            ("center_dock", Qt.DockWidgetArea.LeftDockWidgetArea),
            ("routine_dock", Qt.DockWidgetArea.RightDockWidgetArea),
            ("directive_dock", Qt.DockWidgetArea.RightDockWidgetArea),
        ]
        for attr, area in dock_specs:
            dock = getattr(app, attr, None)
            if dock is None:
                continue
            # Floating docks are intentionally detached – preserve their state.
            # Only re-add to the dock manager when a panel is invisible and not floating
            # (i.e., truly lost due to a broken legacy state).
            if not dock.isVisible() and not dock.isFloating():
                app.dock_manager.addDockWidget(area, dock)
            dock.show()

        if hasattr(app, "sync_panel_menu_state"):
            app.sync_panel_menu_state()
        if hasattr(app, "_on_any_dock_float_changed"):
            app._on_any_dock_float_changed()
        if hasattr(app, "schedule_panel_refresh"):
            app.schedule_panel_refresh(left=True, center=True, right=True)
    except Exception:
        logger.exception("Failed post-startup dock/panel recovery")


def _initialize_daily_summary(app) -> None:
    try:
        from calendar_app.presentation.dialogs.daily_summary_dialog import (
            maybe_show_daily_summary,
            schedule_daily_summary_timer,
        )

        app._daily_summary_timer = schedule_daily_summary_timer(app)
        QTimer.singleShot(3000, lambda: maybe_show_daily_summary(app))
    except Exception:
        logger.exception("Failed to initialize daily summary")


def _setup_command_palette(app) -> None:
    try:
        from calendar_app.presentation.widgets.command_palette import CommandPalette

        app.command_palette = CommandPalette(app)
        app.command_palette.execute_command.connect(app.handle_palette_command)
    except Exception:
        logger.exception("Failed to initialize CommandPalette")
