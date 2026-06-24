"""Infrastructure bootstrap and runtime wiring (Tray, Shortcuts, Window Control)."""

from __future__ import annotations

import logging
import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from calendar_app.app_paths import APP_ICON_PATH
from calendar_app.infrastructure.runtime.keyboard_shortcuts import get_key, register_all
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.icon_map import strip_leading_emoji as _se
from calendar_app.shared.theme_settings import opacity_percent_to_byte

logger = logging.getLogger(__name__)


def setup_app_infrastructure(app) -> None:
    """Initialize system tray, shortcuts, and other OS-level infrastructure."""
    init_tray_icon(app)
    init_shortcuts(app)
    init_idle_detector(app)


def init_idle_detector(app):
    """유휴 상태 감지기를 초기화하고 시작합니다."""
    from calendar_app.infrastructure.runtime.idle_detector import AlarmWorker

    # 이미 실행 중인 워커가 있다면 정지
    if hasattr(app, "alarm_worker"):
        try:
            app.alarm_worker.stop()
            app.alarm_worker.wait(2000)
        except Exception:
            pass

    app.alarm_worker = AlarmWorker(app)
    # 유휴 상태 변화 시 toggle_idle_lock 호출 연동
    app.alarm_worker.idle_status_changed.connect(app.toggle_idle_lock)
    app.alarm_worker.start()
    logger.info("Idle detector (AlarmWorker) initialized and started.")


def _tray_menu_style():
    return """
        QMenu {
            background-color: rgba(28, 28, 36, 250);
            color: #e8e8e8;
            border: 1px solid rgba(255, 255, 255, 18);
            padding: 4px;
            border-radius: 6px;
            font-size: 10pt;
            font-family: 'Segoe UI Emoji', 'Segoe UI Symbol', 'Segoe UI', sans-serif;
        }
        QMenu::item {
            padding: 6px 35px 6px 12px;
            border-radius: 4px;
            margin: 1px 2px;
        }
        QMenu::indicator {
            subcontrol-origin: padding;
            subcontrol-position: center right;
            right: 12px;
            width: 16px;
            height: 16px;
        }
        QMenu::indicator:checked {
            image: none;
            border: 1px solid rgba(77, 166, 255, 0.7);
            border-radius: 3px;
            background: rgba(77, 166, 255, 0.25);
        }
        QMenu::indicator:unchecked { image: none; }
        QMenu::item:selected {
            background-color: rgba(77, 166, 255, 0.25);
            color: #ffffff;
        }
        QMenu::item:disabled {
            color: rgba(255, 255, 255, 40);
        }
        QMenu::separator {
            height: 1px;
            background: rgba(255, 255, 255, 20);
            margin: 4px 8px;
        }
    """


def _create_action(app, label, handler, shortcut_id=None, parent_menu=None):
    """트레이 메뉴용 QAction을 생성한다. 실제 QShortcut 등록은 register_all()이 담당한다.

    setShortcut을 호출하면 QShortcut(ApplicationShortcut)과 충돌할 수 있으므로
    여기서는 레이블에 힌트(\tKEY)만 추가하여 보여준다.
    """
    clean = _se(label)
    act = QAction(clean, app)
    if shortcut_id:
        key = get_key(shortcut_id)
        if key:
            act.setText(f"{clean}\t{key}")
    act.triggered.connect(handler)
    if parent_menu:
        parent_menu.addAction(act)
    return act


def init_tray_icon(app):
    """Initialize system tray icon with optimized and icon-rich menu."""
    if not QSystemTrayIcon.isSystemTrayAvailable():
        logger.warning("System tray not available on this system.")
        return

    app.tray_icon = QSystemTrayIcon(app)

    # Resolve icon path
    possible_paths = [
        APP_ICON_PATH,
        os.path.join(os.getcwd(), "app_icon.ico"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "app_icon.ico"),
    ]
    icon_path = next((p for p in possible_paths if p and os.path.exists(p)), None)

    if icon_path:
        icon = QIcon()
        for size in (16, 24, 32, 48):
            px = QPixmap(icon_path).scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            icon.addPixmap(px)
        app.tray_icon.setIcon(icon)
    else:
        app.tray_icon.setIcon(app.style().standardIcon(app.style().StandardPixmap.SP_ComputerIcon))

    style = _tray_menu_style()
    tray_menu = QMenu()
    tray_menu.setStyleSheet(style)

    from calendar_app.infrastructure.i18n import t

    # --- 1. View & Window Area ---
    _create_action(app, t("tray.show_hide"), app.toggle_overlay, "show_hide", tray_menu).setIcon(
        _ic(ICON.HIDE)
    )
    _create_action(app, t("tray.topbar"), app.toggle_top_bar, "topbar", tray_menu).setIcon(
        _ic(ICON.SCREEN_MGMT)
    )
    _create_action(
        app, t("tray.calendar_topbar"), app.toggle_calendar_toolbar, "cal_toolbar", tray_menu
    ).setIcon(_ic(ICON.TOOLBAR))
    _create_action(
        app, t("tray.fullscreen"), app.toggle_fullscreen, "fullscreen", tray_menu
    ).setIcon(_ic(ICON.FULLSCREEN))
    _create_action(
        app, t("tray.restore"), app.restore_window_to_safe_area, "restore_pos", tray_menu
    ).setIcon(_ic(ICON.RESET_POS))

    tray_menu.addSeparator()

    # --- 2. Registration & Management ---
    add_menu = QMenu(_se(t("tray.add_schedule")), tray_menu)
    add_menu.setIcon(_ic(ICON.ADD))
    add_menu.setStyleSheet(style)
    _create_action(
        app, t("tray.add_schedule"), app.open_task_dialog, "new_schedule", add_menu
    ).setIcon(_ic(ICON.EDIT))
    _create_action(
        app, t("tray.add_routine"), app.open_routine_add_dialog, "new_routine", add_menu
    ).setIcon(_ic(ICON.ROUTINE))
    _create_action(
        app, t("tray.add_directive"), app.open_directive_dialog, "new_directive", add_menu
    ).setIcon(_ic(ICON.DIRECTIVE))
    tray_menu.addMenu(add_menu)

    mgr_menu = QMenu(_se(t("tray.presets")), tray_menu)
    mgr_menu.setIcon(_ic(ICON.SETTINGS))
    mgr_menu.setStyleSheet(style)
    # Routine Manager (Tabs)
    _create_action(
        app,
        t("tray.routine_manager"),
        lambda: app.open_work_management_dialog(start_tab="schedule"),
        None,
        mgr_menu,
    ).setIcon(_ic(ICON.ALL_SCHEDULES))
    # Routine Settings (Dialog)
    _create_action(
        app,
        t("tray.routine_manager").replace("관리자", "설정"),
        app.open_routine_management_dialog,
        "routine_mgr",
        mgr_menu,
    ).setIcon(_ic(ICON.SETTINGS))
    # Checklist Manager
    _create_action(
        app, t("tray.checklist_manager"), app.open_checklist_manager, "checklist", mgr_menu
    ).setIcon(_ic(ICON.CHECKLIST))
    # Layout Presets
    _create_action(
        app,
        t("tray.presets"),
        lambda: app.preset_manager._save_with_prompt() if hasattr(app, "preset_manager") else None,
        "save_layout",
        mgr_menu,
    ).setIcon(_ic(ICON.SAVE))
    tray_menu.addMenu(mgr_menu)

    tray_menu.addSeparator()

    # --- 3. Navigation & Calendar Control ---
    nav_menu = QMenu(_se(t("tray.today")), tray_menu)
    nav_menu.setIcon(_ic(ICON.VIEW_CALENDAR))
    nav_menu.setStyleSheet(style)
    _create_action(app, t("tray.today"), app.jump_to_today, "today", nav_menu).setIcon(
        _ic(ICON.GOTO_TODAY)
    )
    _create_action(app, t("tray.prev_day"), app.prev_day, "prev_day", nav_menu).setIcon(
        _ic(ICON.NAV_PREV)
    )
    _create_action(app, t("tray.next_day"), app.next_day, "next_day", nav_menu).setIcon(
        _ic(ICON.NAV_NEXT)
    )
    _create_action(app, t("tray.view_toggle"), app.toggle_view_mode, None, nav_menu).setIcon(
        _ic(ICON.VIEW_MONTHLY)
    )
    tray_menu.addMenu(nav_menu)

    tray_menu.addSeparator()

    # --- 4. Special Modes ---
    act_focus = _create_action(
        app, t("tray.focus_mode"), app.toggle_focus_mode, "focus_mode", tray_menu
    )
    act_focus.setIcon(_ic(ICON.POMODORO))
    act_pomo = _create_action(
        app,
        t("tray.focus_timer_settings", "Pomodoro Settings..."),
        app.open_pomodoro_settings_dialog,
        None,
        tray_menu,
    )
    act_pomo.setIcon(_ic(ICON.SETTINGS))
    act_flog = _create_action(app, t("tray.focus_log"), app.open_focus_log_dialog, None, tray_menu)
    act_flog.setIcon(_ic(ICON.DOCS))
    act_away = _create_action(
        app,
        t("menu.instant_away"),
        lambda: app.toggle_idle_lock(True, manual=True)
        if hasattr(app, "toggle_idle_lock")
        else None,
        "away_lock",
        tray_menu,
    )
    act_away.setIcon(_ic(ICON.LOCK))
    act_lock = _create_action(
        app, t("tray.lock_mode"), lambda: _toggle_lock_via_shortcut(app), "lock_mode", tray_menu
    )
    act_lock.setIcon(_ic(ICON.LOCK))
    act_magnet = _create_action(
        app, t("tray.magnet_mode"), app.toggle_magnet_mode, "magnet_mode", tray_menu
    )
    act_magnet.setIcon(_ic(ICON.MAGNET))

    tray_menu.addSeparator()

    # --- 5. Service & Sync ---
    act_gsync = _create_action(
        app, t("tray.sync_google"), app.sync_google_calendar, None, tray_menu
    )
    act_gsync.setIcon(_ic(ICON.SYNC))
    act_gissues = _create_action(
        app, t("tray.google_issues"), app.open_gcal_sync_issues_dialog, None, tray_menu
    )
    act_gissues.setIcon(_ic(ICON.WARNING))

    opacity_menu = tray_menu.addMenu(_se(t("tray.opacity")))
    opacity_menu.setIcon(_ic(ICON.OPACITY))
    opacity_menu.setStyleSheet(style)
    for label, value in [
        (t("tray.opacity_level.v25"), 25),
        (t("tray.opacity_level.v50"), 50),
        (t("tray.opacity_level.v75"), 75),
        (t("tray.opacity_level.v100"), 100),
    ]:
        _create_action(
            app,
            label,
            lambda checked=False, v=value: app.slider.setValue(opacity_percent_to_byte(v)),
            None,
            opacity_menu,
        )

    opacity_step = opacity_percent_to_byte(10)
    opacity_floor = opacity_percent_to_byte(20)
    act_op_up = _create_action(
        app,
        t("tray.opacity_up"),
        lambda: app.slider.setValue(min(app.slider.value() + opacity_step, 255)),
        "opacity_up",
        opacity_menu,
    )
    act_op_up.setIcon(_ic(ICON.OPACITY_UP))
    act_op_dn = _create_action(
        app,
        t("tray.opacity_down"),
        lambda: app.slider.setValue(max(app.slider.value() - opacity_step, opacity_floor)),
        "opacity_down",
        opacity_menu,
    )
    act_op_dn.setIcon(_ic(ICON.OPACITY_DOWN))

    tray_menu.addSeparator()
    act_lang = _create_action(
        app, t("menu.language"), app.open_language_settings_dialog, None, tray_menu
    )
    act_lang.setIcon(_ic(ICON.LOCALE_MGMT))
    act_theme = _create_action(
        app,
        t("menu.ui_theme_open", "UI 테마 지정..."),
        app.open_panel_background_color_dialog,
        None,
        tray_menu,
    )
    act_theme.setIcon(_ic(ICON.COLOR_PICKER))

    # Autostart (Checkable)
    from calendar_app.infrastructure.runtime import system_manager

    act_auto = QAction(t("menu.autostart"), app)
    act_auto.setCheckable(True)
    act_auto.setChecked(system_manager.is_autostart_enabled())
    act_auto.triggered.connect(app.toggle_autostart)
    tray_menu.addAction(act_auto)
    app.autostart_act = act_auto  # Sync with existing action in Top Menu if any

    tray_menu.addSeparator()
    act_exit = _create_action(app, t("tray.exit"), app.request_app_exit, None, tray_menu)
    act_exit.setIcon(_ic(ICON.CLOSE))

    app.tray_icon.setContextMenu(tray_menu)
    app.tray_icon.activated.connect(lambda reason: _handle_tray_activation(app, reason))
    app.tray_icon.show()
    logger.info("System tray and unified shortcuts initialized.")


def _handle_tray_activation(app, reason: QSystemTrayIcon.ActivationReason) -> None:
    """Handle tray icon click events."""
    if reason in (
        QSystemTrayIcon.ActivationReason.Trigger,
        QSystemTrayIcon.ActivationReason.DoubleClick,
    ):
        if hasattr(app, "is_widget_mode_active") and app.is_widget_mode_active():
            if hasattr(app, "stop_widget_mode"):
                app.stop_widget_mode()
            return
        if app.isVisible():
            app.hide()
            app.is_visible = False
        else:
            app.show()
            app.is_visible = True
            if app.isMinimized():
                app.showNormal()
            app.activateWindow()
            app.raise_()
            if hasattr(app, "_refresh_all_panels"):
                app._refresh_all_panels()


def _toggle_lock_via_shortcut(app):
    """Toggle lock mode via tray or shortcut."""
    if hasattr(app, "lock_btn"):
        app.lock_btn.setChecked(not app.lock_btn.isChecked())
        app.toggle_lock_mode()


def init_shortcuts(app):
    """전역 단축키를 keyboard_shortcuts.register_all()에 위임하여 일괄 등록한다."""
    register_all(app)


def toggle_overlay(app) -> None:
    """Toggle 'Always on Top' (overlay) mode."""
    if getattr(app, "is_visible", True):
        app.hide()
        app.is_visible = False
    else:
        app.show()
        app.is_visible = True


def toggle_fullscreen(app) -> None:
    """Toggle fullscreen mode."""
    if app.isFullScreen():
        app.showNormal()
        app.is_fullscreen = False
    else:
        app.showFullScreen()
        app.is_fullscreen = True
