# -*- coding: utf-8 -*-
"""Infrastructure bootstrap and runtime wiring (Tray, Shortcuts, Window Control)."""

from __future__ import annotations

import logging
import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from calendar_app.app_paths import APP_ICON_PATH
from calendar_app.infrastructure.runtime.keyboard_shortcuts import (
    get_key,
    register_app_shortcuts,
)
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.icon_map import strip_leading_emoji as _se
from calendar_app.shared.theme_settings import opacity_percent_to_byte

logger = logging.getLogger(__name__)


def setup_app_infrastructure(app) -> bool:
    """Initialize system tray, shortcuts, and other OS-level infrastructure."""
    tray_available = init_tray_icon(app)
    init_shortcuts(app)
    init_idle_detector(app)
    return tray_available


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


def _create_tray_autostart_action(app, parent_menu):
    """Create the tray autostart action with the same icon contract as other items."""
    from calendar_app.infrastructure.i18n import t
    from calendar_app.infrastructure.runtime import system_manager

    action = _create_action(app, t("menu.autostart"), app.toggle_autostart, None, parent_menu)
    action.setIcon(_ic(ICON.AUTOSTART))
    action.setCheckable(True)
    action.setChecked(system_manager.is_autostart_enabled())
    app.autostart_tray_act = action
    return action


def tray_tooltip_text() -> str:
    """Tray hover text: program name and version side by side."""
    from calendar_app.app_metadata import APP_NAME, APP_VERSION_LABEL

    return f"{APP_NAME} {APP_VERSION_LABEL}"


def _build_tray_icon(icon_path: str) -> QIcon:
    """Build tray pixmaps from the largest frame with the transparent margin trimmed.

    The .ico art leaves ~20% empty space around the glyph, which makes it look
    small next to other tray icons. Trimming keeps the shape and fills the slot.
    """
    source = QIcon(icon_path)
    sizes = source.availableSizes()
    largest = max(sizes, key=lambda s: s.width()) if sizes else None
    image = source.pixmap(largest).toImage() if largest else QImage(icon_path)
    image = image.convertToFormat(QImage.Format.Format_ARGB32)

    left, top, right, bottom = image.width(), image.height(), -1, -1
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() > 16:
                left, right = min(left, x), max(right, x)
                top, bottom = min(top, y), max(bottom, y)
    if right >= left and bottom >= top:
        image = image.copy(left, top, right - left + 1, bottom - top + 1)

    side = max(image.width(), image.height())
    square = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    square.fill(Qt.GlobalColor.transparent)
    painter = QPainter(square)
    painter.drawImage((side - image.width()) // 2, (side - image.height()) // 2, image)
    painter.end()

    icon = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64):
        icon.addPixmap(
            QPixmap.fromImage(
                square.scaled(
                    size,
                    size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        )
    return icon


def init_tray_icon(app):
    """Initialize system tray icon with optimized and icon-rich menu."""
    app._tray_available = False
    if not QSystemTrayIcon.isSystemTrayAvailable():
        logger.warning("System tray not available on this system.")
        return False

    app.tray_icon = QSystemTrayIcon(app)

    # Resolve icon path
    possible_paths = [
        APP_ICON_PATH,
        os.path.join(os.getcwd(), "app_icon.ico"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "app_icon.ico"),
    ]
    icon_path = next((p for p in possible_paths if p and os.path.exists(p)), None)

    if icon_path:
        app.tray_icon.setIcon(_build_tray_icon(icon_path))
    else:
        app.tray_icon.setIcon(app.style().standardIcon(app.style().StandardPixmap.SP_ComputerIcon))
    app.tray_icon.setToolTip(tray_tooltip_text())

    style = _tray_menu_style()
    tray_menu = QMenu()
    tray_menu.setStyleSheet(style)

    from calendar_app.infrastructure.i18n import t

    # Tray layout (2026-11-23): what you reach for from the taskbar comes first,
    # then tools and windows, then sync and settings, then exit.
    #   창 표시/숨기기 · 위젯 전용 모드
    #   새로 만들기 ▸ · 오늘 날짜로 이동
    #   집중 및 잠금 ▸ · 화면 및 창 ▸ · 관리 ▸
    #   동기화 ▸ · 설정 ▸
    #   종료
    def submenu(label, icon_key):
        menu = QMenu(_se(label), tray_menu)
        menu.setIcon(_ic(icon_key))
        menu.setStyleSheet(style)
        return menu

    _create_action(
        app,
        t("tray.show_hide_window", "창 표시/숨기기"),
        app.toggle_overlay,
        "show_hide",
        tray_menu,
    ).setIcon(_ic(ICON.HIDE))
    if hasattr(app, "toggle_widget_mode_panel"):
        _create_action(
            app,
            t("tray.widget_mode", "위젯 전용 모드"),
            app.toggle_widget_mode_panel,
            "widget_mode",
            tray_menu,
        ).setIcon(_ic(ICON.WIDGET_DATECARD))

    tray_menu.addSeparator()

    add_menu = submenu(t("tray.new_menu", "새로 만들기"), ICON.ADD)
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
    _create_action(app, t("tray.today"), app.jump_to_today, "today", tray_menu).setIcon(
        _ic(ICON.GOTO_TODAY)
    )

    tray_menu.addSeparator()

    # --- 4. Special Modes ---
    focus_menu = QMenu(_se(t("tray.focus_tools", "집중 및 잠금")), tray_menu)
    focus_menu.setIcon(_ic(ICON.POMODORO))
    focus_menu.setStyleSheet(style)
    act_focus = _create_action(
        app, t("tray.focus_mode"), app.toggle_focus_mode, "focus_mode", focus_menu
    )
    act_focus.setIcon(_ic(ICON.POMODORO))
    act_pomo = _create_action(
        app,
        t("tray.focus_timer_settings", "Pomodoro Settings..."),
        app.open_pomodoro_settings_dialog,
        None,
        focus_menu,
    )
    act_pomo.setIcon(_ic(ICON.SETTINGS))
    act_flog = _create_action(app, t("tray.focus_log"), app.open_focus_log_dialog, None, focus_menu)
    act_flog.setIcon(_ic(ICON.DOCS))
    act_away = _create_action(
        app,
        t("menu.instant_away"),
        lambda: (
            app.toggle_idle_lock(True, manual=True) if hasattr(app, "toggle_idle_lock") else None
        ),
        "away_lock",
        focus_menu,
    )
    act_away.setIcon(_ic(ICON.LOCK))
    act_lock = _create_action(
        app, t("tray.lock_mode"), lambda: _toggle_lock_via_shortcut(app), "lock_mode", focus_menu
    )
    act_lock.setIcon(_ic(ICON.LOCK))
    from PyQt6.QtGui import QActionGroup

    from calendar_app.presentation.main_window import desktop_lock
    from calendar_app.presentation.main_window.lock_click_through import click_through_enabled

    # Lock type: layout only, or full (view only). One menu for every lock option.
    lock_options = QMenu(t("lock.kind_menu", "고정 방식"), focus_menu)
    lock_options.setStyleSheet(style)
    kind_group = QActionGroup(lock_options)
    kind_group.setExclusive(True)
    current_kind = desktop_lock.lock_kind(getattr(app, "settings", None))
    app._lock_kind_actions = []
    for value, label in (
        (desktop_lock.KIND_LAYOUT, t("lock.kind_layout", "배치만 고정 (일정은 그대로 사용)")),
        (desktop_lock.KIND_FULL, t("lock.kind_full", "완전 고정 (바탕화면처럼 보기만)")),
    ):
        kind_action = lock_options.addAction(label)
        kind_action.setCheckable(True)
        kind_action.setChecked(value == current_kind)
        kind_group.addAction(kind_action)
        if hasattr(app, "set_lock_kind"):
            kind_action.triggered.connect(lambda _c=False, v=value: app.set_lock_kind(v))
        app._lock_kind_actions.append((kind_action, value))
    lock_options.addSeparator()
    focus_menu.addMenu(lock_options)

    act_click_through = lock_options.addAction(
        t("tray.lock_click_through", "고정 중 클릭 통과 (바탕화면 사용)")
    )
    act_click_through.setCheckable(True)
    act_click_through.setChecked(click_through_enabled(getattr(app, "settings", None)))
    act_click_through.setToolTip(
        t(
            "tray.lock_click_through_hint",
            "완전 고정 중에는 클릭이 달력 아래 바탕화면으로 전달됩니다. "
            "오른쪽 아래 배지에 마우스를 잠시 올려 두면 다시 누를 수 있습니다.",
        )
    )
    if hasattr(app, "set_lock_click_through"):
        act_click_through.toggled.connect(app.set_lock_click_through)
    app.tray_lock_click_through_action = act_click_through
    from calendar_app.presentation.main_window.lock_click_through import behind_icons_enabled

    act_behind_icons = lock_options.addAction(
        t("tray.lock_behind_icons", "고정 중 바탕화면 아이콘 뒤로 보내기")
    )
    act_behind_icons.setCheckable(True)
    act_behind_icons.setChecked(behind_icons_enabled(getattr(app, "settings", None)))
    act_behind_icons.setToolTip(
        t(
            "tray.lock_behind_icons_hint",
            "완전 고정 중에는 달력을 배경화면처럼 바탕화면 아이콘 아래에 둡니다. "
            "오른쪽 아래 배지에 마우스를 잠시 올려 두면 다시 꺼내 누를 수 있습니다.",
        )
    )
    if hasattr(app, "set_lock_behind_icons"):
        act_behind_icons.toggled.connect(app.set_lock_behind_icons)
    app.tray_lock_behind_icons_action = act_behind_icons
    act_magnet = _create_action(
        app, t("tray.magnet_mode"), app.toggle_magnet_mode, "magnet_mode", focus_menu
    )
    act_magnet.setIcon(_ic(ICON.MAGNET))
    tray_menu.addMenu(focus_menu)

    # --- 화면 및 창 (투명도 포함) ---
    view_menu = submenu(t("tray.view_options", "화면 및 창"), ICON.SCREEN_MGMT)
    _create_action(
        app,
        t("menu.auto_hide_topbar", "상단 바 자동 숨기기"),
        app.toggle_top_bar,
        "topbar",
        view_menu,
    ).setIcon(_ic(ICON.TOOLBAR))
    _create_action(
        app, t("tray.calendar_topbar"), app.toggle_calendar_toolbar, "cal_toolbar", view_menu
    ).setIcon(_ic(ICON.TOOLBAR))
    _create_action(
        app, t("tray.fullscreen"), app.toggle_fullscreen, "fullscreen", view_menu
    ).setIcon(_ic(ICON.FULLSCREEN))
    _create_action(
        app, t("tray.restore"), app.restore_window_to_safe_area, "restore_pos", view_menu
    ).setIcon(_ic(ICON.RESET_POS))
    view_menu.addSeparator()
    opacity_menu = view_menu.addMenu(_se(t("tray.opacity")))
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
    opacity_menu.addSeparator()
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
    tray_menu.addMenu(view_menu)

    # --- 관리 ---
    mgr_menu = submenu(t("tray.manage_menu", "관리"), ICON.ALL_SCHEDULES)
    _create_action(
        app,
        t("tray.routine_manager"),
        lambda: app.open_work_management_dialog(start_tab="schedule"),
        None,
        mgr_menu,
    ).setIcon(_ic(ICON.ALL_SCHEDULES))
    _create_action(
        app,
        t("tray.routine_settings", "일반업무 설정"),
        app.open_routine_management_dialog,
        "routine_mgr",
        mgr_menu,
    ).setIcon(_ic(ICON.SETTINGS))
    _create_action(
        app, t("tray.checklist_manager"), app.open_checklist_manager, "checklist", mgr_menu
    ).setIcon(_ic(ICON.CHECKLIST))
    mgr_menu.addSeparator()
    _create_action(
        app,
        t("tray.save_layout_preset", "레이아웃 프리셋 저장..."),
        lambda: app.preset_manager._save_with_prompt() if hasattr(app, "preset_manager") else None,
        "save_layout",
        mgr_menu,
    ).setIcon(_ic(ICON.SAVE))
    tray_menu.addMenu(mgr_menu)

    tray_menu.addSeparator()

    # --- 동기화 ---
    sync_menu = submenu(t("tray.sync_menu", "동기화"), ICON.SYNC)
    _create_action(
        app,
        t("sync_unified.sync_all", "연결된 모든 캘린더 동기화"),
        app.sync_calendars,
        None,
        sync_menu,
    ).setIcon(_ic(ICON.SYNC))
    _create_action(
        app,
        t("sync_unified.issues", "전체 동기화 문제"),
        app.open_calendar_sync_issues,
        None,
        sync_menu,
    ).setIcon(_ic(ICON.WARNING))
    sync_menu.addSeparator()
    _create_action(
        app,
        t("sync_ui.hub_title", "캘린더 · 계정 및 동기화"),
        app.open_calendar_sync_hub,
        None,
        sync_menu,
    ).setIcon(_ic(ICON.SYNC_SETTINGS))
    tray_menu.addMenu(sync_menu)

    # --- 설정 ---
    settings_menu = submenu(t("tray.settings_menu", "설정"), ICON.SETTINGS)
    _create_action(
        app,
        t("menu.ui_theme_open", "UI 테마 지정..."),
        app.open_panel_background_color_dialog,
        None,
        settings_menu,
    ).setIcon(_ic(ICON.COLOR_PICKER))
    _create_action(
        app, t("menu.language"), app.open_language_settings_dialog, None, settings_menu
    ).setIcon(_ic(ICON.LOCALE_MGMT))
    _create_tray_autostart_action(app, settings_menu)
    tray_menu.addMenu(settings_menu)

    tray_menu.addSeparator()
    act_exit = _create_action(app, t("tray.exit"), app.request_app_exit, None, tray_menu)
    act_exit.setIcon(_ic(ICON.CLOSE))

    app.tray_icon.setContextMenu(tray_menu)
    app.tray_icon.activated.connect(lambda reason: _handle_tray_activation(app, reason))
    app.tray_icon.show()
    app._tray_available = app.tray_icon.isVisible()
    logger.info("System tray and unified shortcuts initialized.")
    return app._tray_available


def _set_overlay_visible(app, visible: bool, *, refresh: bool = False) -> None:
    """Apply one authoritative main-window visibility transition."""
    if visible:
        if app.isMinimized():
            app.showNormal()
        else:
            app.show()
        app.is_visible = app.isVisible()
        if refresh and hasattr(app, "_refresh_all_panels"):
            app._refresh_all_panels()
        app.raise_()
        app.activateWindow()
        return

    app.hide()
    app.is_visible = False


def _return_to_main_from_widget_mode(app) -> bool:
    """Treat a tray restore request as explicit navigation to the calendar."""
    if not getattr(app, "is_widget_mode_active", lambda: False)():
        return False
    coordinator = getattr(app, "_widget_mode_coordinator", None)
    return_to_main = getattr(coordinator, "return_to_main", None)
    if callable(return_to_main):
        return_to_main()
    else:
        stop_widget_mode = getattr(app, "stop_widget_mode", None)
        if callable(stop_widget_mode):
            stop_widget_mode()
        _set_overlay_visible(app, True, refresh=True)
    return True


def _handle_tray_activation(app, reason: QSystemTrayIcon.ActivationReason) -> None:
    """Toggle on a single click and always reveal on a double click."""
    if reason not in (
        QSystemTrayIcon.ActivationReason.Trigger,
        QSystemTrayIcon.ActivationReason.DoubleClick,
    ):
        return
    if _return_to_main_from_widget_mode(app):
        return
    should_reveal = (
        reason == QSystemTrayIcon.ActivationReason.DoubleClick
        or app.isMinimized()
        or not app.isVisible()
    )
    _set_overlay_visible(app, should_reveal, refresh=should_reveal)


def _toggle_lock_via_shortcut(app):
    """Toggle lock mode via tray or shortcut."""
    if hasattr(app, "lock_btn"):
        app.lock_btn.setChecked(not app.lock_btn.isChecked())
        app.toggle_lock_mode()


def init_shortcuts(app):
    """OS 전역 단축키(창 표시/숨기기)와 앱 내 단축키를 일괄 등록한다."""
    register_app_shortcuts(app)


def toggle_overlay(app) -> None:
    """Toggle main-window visibility using the actual Qt window state."""
    if _return_to_main_from_widget_mode(app):
        return
    _set_overlay_visible(app, app.isMinimized() or not app.isVisible())


def toggle_fullscreen(app) -> None:
    """Toggle fullscreen mode."""
    if getattr(app, "is_focus_mode", False):
        from calendar_app.presentation.focus_mode import toggle_focus_fullscreen

        if toggle_focus_fullscreen(app):
            return
    if app.isFullScreen():
        app.showNormal()
        app.is_fullscreen = False
    else:
        app.showFullScreen()
        app.is_fullscreen = True
