# -*- coding: utf-8 -*-

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu, QToolButton

from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.runtime.keyboard_shortcuts import get_key
from calendar_app.presentation.main_window.top_menus.common import (
    format_top_menu_button_text,
    set_themed_icon,
)
from calendar_app.shared.color_utils import contrast_safe_color
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.icon_map import strip_leading_emoji as _se
from calendar_app.shared.theme_snapshot import build_theme_snapshot


def _toggle_dock(app, dock_attr: str, visible: bool) -> None:
    """패널 토글: floating 상태를 보존하면서 show/hide. 숨겼다가 다시 켤 때
    floating이었다면 그대로 floating으로 복원하고, 도킹 상태였다면 dock_manager에 재추가한다."""
    from PyQt6.QtCore import Qt

    dock = getattr(app, dock_attr, None)
    if dock is None:
        return

    if not visible:
        dock.hide()
        return

    # 이미 보이고 있으면 raise만
    if dock.isVisible():
        dock.raise_()
        return

    if dock.isFloating():
        # floating 상태: show()로 충분
        dock.show()
        dock.raise_()
    else:
        # 도킹 상태: dock_manager에 연결되지 않은 경우 재추가
        _AREA_MAP = {
            "left_dock": Qt.DockWidgetArea.LeftDockWidgetArea,
            "center_dock": Qt.DockWidgetArea.LeftDockWidgetArea,
            "routine_dock": Qt.DockWidgetArea.RightDockWidgetArea,
            "directive_dock": Qt.DockWidgetArea.RightDockWidgetArea,
        }
        if hasattr(app, "dock_manager"):
            area = _AREA_MAP.get(dock_attr, Qt.DockWidgetArea.LeftDockWidgetArea)
            app.dock_manager.addDockWidget(area, dock)
        dock.show()


def _update_calendar_visibility_menu(app, menu: "QMenu", menu_style: str) -> None:
    """캘린더 가시성 토글 서브메뉴를 동적으로 구성합니다.

    메인 캘린더 화면(옵션 메뉴)의 캘린더 표시 항목과 동일한 표현을 사용:
    - 캘린더 type 별 아이콘(gcal/ics/local/shared) + 캘린더 색상으로 틴팅
    - read-only 캘린더는 LOCK 아이콘 + 툴팁
    - 비활성 캘린더 포함 표시
    - 하단에 "캘린더 관리..." 진입점 추가
    """
    menu.clear()
    menu.setStyleSheet(getattr(app, "_last_menu_style", "") or menu_style)
    snapshot = build_theme_snapshot(app.settings)
    neutral_icon = snapshot.text_palette["text_primary"]
    try:
        from calendar_app.infrastructure.db.calendar_repo import (
            is_calendar_row_read_only,
            list_calendars,
            set_calendar_visible,
        )

        calendars = list_calendars(include_inactive=True)
    except Exception:
        menu.addAction(t("menu.calendar_load_error", "캘린더 로드 실패")).setEnabled(False)
        return

    if not calendars:
        menu.addAction(t("menu.no_calendars", "캘린더 없음")).setEnabled(False)
        return

    _TYPE_ICON = {
        "gcal": ICON.GCAL,
        "ics": ICON.LINK,
        "local": ICON.ALL_SCHEDULES,
        "shared": ICON.ALL_SCHEDULES,
    }
    _READ_ONLY_ICON = ICON.LOCK

    def _make_toggle(cal_id):
        def _fn(checked):
            try:
                set_calendar_visible(cal_id, checked)
                # 메인 캘린더 옵션 메뉴와 동일한 캐시 무효화 + 패널 갱신 흐름
                from calendar_app.presentation.calendar.month_renderer import (
                    invalidate_calendar_meta_cache,
                )
                from calendar_app.presentation.panels.side_panel_renderer import (
                    invalidate_panel_calendar_cache,
                )

                invalidate_calendar_meta_cache()
                invalidate_panel_calendar_cache()
                if hasattr(app, "schedule_panel_refresh"):
                    app.schedule_panel_refresh(left=True, center=True)
            except Exception:
                pass

        return _fn

    for cal in calendars:
        is_read_only = is_calendar_row_read_only(cal)
        type_icon = (
            _READ_ONLY_ICON
            if is_read_only
            else _TYPE_ICON.get(cal.get("type", "local"), ICON.ALL_SCHEDULES)
        )
        cal_color = contrast_safe_color(
            cal.get("color") or neutral_icon,
            snapshot.panel_base_color,
            minimum=3.0,
        )
        final_icon = _ic(type_icon, color=cal_color)

        act = menu.addAction(final_icon, cal.get("name") or cal.get("id") or "")
        act.setCheckable(True)
        act.setChecked(bool(cal.get("is_visible", 1)))
        if is_read_only:
            act.setToolTip(t("dialog.task.calendar_read_only", "Read-only calendar"))
        act.triggered.connect(_make_toggle(cal.get("id") or ""))

    menu.addSeparator()
    manage_act = menu.addAction(t("menu.calendar_manage", "캘린더 관리..."))
    set_themed_icon(manage_act, ICON.CHECKLIST, neutral_icon)

    def _open_manage():
        if hasattr(app, "open_gcal_settings_dialog"):
            app.open_gcal_settings_dialog(initial_tab="calendar")

    manage_act.triggered.connect(_open_manage)


def _refresh_display_menu_i18n(self):
    refs = {
        "display_menu_btn": ("setText", ("menu.display_btn", "화면")),
    }

    for attr, (method_name, (key, fallback)) in refs.items():
        obj = getattr(self, attr, None)
        if obj is not None:
            getattr(obj, method_name)(format_top_menu_button_text(t(key, fallback)))

    # Update theme mode menu item check states
    if hasattr(self, "theme_mode_menu"):
        current_mode = self.settings.value("text_theme", "dark")
        for action in self.theme_mode_menu.actions():
            if action.text() == t("theme.dark_mode", "다크 모드"):
                action.setChecked(current_mode == "dark")
            elif action.text() == t("theme.light_mode", "라이트 모드"):
                action.setChecked(current_mode == "light")
            elif action.text() == t("theme.system_default", "시스템 기본"):
                action.setChecked(current_mode == "auto")


def build_display_menu(self, top_bar, menu_btn_style, menu_style):
    icon_color = getattr(self, "_tb_icon_color", "#f4f7fb")
    self.display_menu_btn = QToolButton()

    self.display_menu_btn.setText(format_top_menu_button_text(t("menu.display_btn", "화면")))
    set_themed_icon(self.display_menu_btn, ICON.SCREEN_MGMT, icon_color)
    self.display_menu_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

    self.display_menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

    self.display_menu_btn.setStyleSheet(menu_btn_style)

    self.display_menu = QMenu(self)

    self.display_menu.setStyleSheet(menu_style)

    def _refresh_layout_preset_labels():
        if hasattr(self, "layout_preset_actions"):
            from calendar_app.presentation.main_window.dock_sections.dock_layout_presets import (
                LAYOUT_PRESET_DEFS,
            )

            for i, act in enumerate(self.layout_preset_actions):
                if i < len(LAYOUT_PRESET_DEFS):
                    name, shortcut = LAYOUT_PRESET_DEFS[i]

                    act.setText(f"{name}\t{shortcut}")

    self.refresh_layout_preset_labels = _refresh_layout_preset_labels

    act_tv = self.display_menu.addAction(_se(t("menu.toggle_view")), self.toggle_view_mode)
    set_themed_icon(act_tv, ICON.VIEW_CALENDAR, icon_color)

    self.panel_menu = self.display_menu.addMenu(_se(t("menu.panel_settings")))
    set_themed_icon(self.panel_menu, ICON.DISPLAY_STYLE, icon_color)

    self.act_today = self.panel_menu.addAction(_se(t("menu.panel_today")))
    set_themed_icon(self.act_today, ICON.STATUS_TODAY, icon_color)
    self.act_today.setCheckable(True)

    self.act_today.triggered.connect(
        lambda *args: _toggle_dock(self, "left_dock", self.act_today.isChecked())
    )

    self.act_calendar = self.panel_menu.addAction(_se(t("menu.panel_calendar")))
    set_themed_icon(self.act_calendar, ICON.VIEW_CALENDAR, icon_color)
    self.act_calendar.setCheckable(True)

    self.act_calendar.triggered.connect(
        lambda *args: _toggle_dock(self, "center_dock", self.act_calendar.isChecked())
    )

    self.act_routine = self.panel_menu.addAction(_se(t("menu.panel_routine")))
    set_themed_icon(self.act_routine, ICON.ROUTINE, icon_color)
    self.act_routine.setCheckable(True)

    self.act_routine.triggered.connect(
        lambda *args: _toggle_dock(self, "routine_dock", self.act_routine.isChecked())
    )

    self.act_directive = self.panel_menu.addAction(_se(t("menu.panel_directive")))
    set_themed_icon(self.act_directive, ICON.DIRECTIVE, icon_color)
    self.act_directive.setCheckable(True)

    self.act_directive.triggered.connect(
        lambda *args: _toggle_dock(self, "directive_dock", self.act_directive.isChecked())
    )

    self.display_menu.addSeparator()

    self.display_window_menu = self.display_menu.addMenu(
        _se(t("menu.window_view_options", "화면 및 창"))
    )
    set_themed_icon(self.display_window_menu, ICON.SCREEN_MGMT, icon_color)
    self.display_window_menu.setStyleSheet(menu_style)

    self.act_topbar = self.display_window_menu.addAction(
        f"{_se(t('menu.hide_topbar'))}\t{get_key('topbar')}"
    )
    set_themed_icon(self.act_topbar, ICON.HIDE, icon_color)
    self.act_topbar.setCheckable(True)

    self.act_topbar.setChecked(True)

    self.act_topbar.triggered.connect(self.toggle_top_bar)

    self.act_calendar_toolbar = self.display_window_menu.addAction(
        f"{_se(t('menu.hide_calendar_toolbar'))}\t{get_key('cal_toolbar')}"
    )
    set_themed_icon(self.act_calendar_toolbar, ICON.SCREEN_MGMT, icon_color)
    self.act_calendar_toolbar.setCheckable(True)

    self.act_calendar_toolbar.setChecked(self._calendar_toolbar_visible_setting())

    self.act_calendar_toolbar.triggered.connect(self.set_calendar_toolbar_visible)

    act_fs = self.display_window_menu.addAction(
        f"{_se(t('menu.fullscreen'))}\t{get_key('fullscreen')}", self.toggle_fullscreen
    )
    set_themed_icon(act_fs, ICON.FULLSCREEN, icon_color)

    self.display_mode_menu = self.display_menu.addMenu(
        _se(t("menu.focus_view_options", "집중 및 잠금"))
    )
    set_themed_icon(self.display_mode_menu, ICON.POMODORO, icon_color)
    self.display_mode_menu.setStyleSheet(menu_style)

    act_fm = self.display_mode_menu.addAction(
        f"{_se(t('menu.focus_mode'))}\t{get_key('focus_mode')}", self.toggle_focus_mode
    )
    set_themed_icon(act_fm, ICON.POMODORO, icon_color)

    act_wm = self.display_mode_menu.addAction(
        f"{_se(t('menu.widget_mode_toggle', '위젯 전용 모드'))}\t{get_key('widget_mode', 'F12')}",
        self.toggle_widget_mode_panel,
    )
    set_themed_icon(act_wm, ICON.WIDGET_MGR, icon_color)

    self.instant_away_act = self.display_mode_menu.addAction(
        _se(t("menu.instant_away")), lambda: self.toggle_idle_lock(True, manual=True)
    )
    set_themed_icon(self.instant_away_act, ICON.LOCK, icon_color)

    self.display_menu.addSeparator()

    self.calendar_visibility_menu = self.display_menu.addMenu(
        _se(t("menu.calendar_visibility", "캘린더 표시"))
    )
    set_themed_icon(self.calendar_visibility_menu, ICON.VIEW_CALENDAR, icon_color)
    self.calendar_visibility_menu.aboutToShow.connect(
        lambda: _update_calendar_visibility_menu(self, self.calendar_visibility_menu, menu_style)
    )

    self.display_menu.addSeparator()

    self.theme_mode_menu = self.display_menu.addMenu(_se(t("menu.theme_mode", "테마 모드")))
    set_themed_icon(self.theme_mode_menu, ICON.COLOR_PICKER, icon_color)

    current_mode = self.settings.value("text_theme", "dark")

    act_dark = self.theme_mode_menu.addAction(
        t("theme.dark_mode", "다크 모드"), lambda: self.change_text_theme("dark")
    )
    set_themed_icon(act_dark, ICON.THEME_DARK, icon_color)
    act_dark.setCheckable(True)
    act_dark.setChecked(current_mode == "dark")

    act_light = self.theme_mode_menu.addAction(
        t("theme.light_mode", "라이트 모드"), lambda: self.change_text_theme("light")
    )
    set_themed_icon(act_light, ICON.THEME_LIGHT, icon_color)
    act_light.setCheckable(True)
    act_light.setChecked(current_mode == "light")

    act_auto = self.theme_mode_menu.addAction(
        t("theme.system_default", "시스템 기본"), self.set_system_default_theme
    )
    set_themed_icon(act_auto, ICON.THEME_AUTO, icon_color)
    act_auto.setCheckable(True)
    act_auto.setChecked(current_mode == "auto")

    act_theme = self.display_menu.addAction(
        _se(t("menu.ui_theme_open", "모양 설정...")),
        self.open_panel_background_color_dialog,
    )
    set_themed_icon(act_theme, ICON.COLOR_PICKER, icon_color)

    self.display_menu.addSeparator()

    from calendar_app.presentation.main_window.dock_sections.dock_layout_presets import (
        LAYOUT_PRESET_DEFS,
        apply_layout_preset,
    )

    layout_menu = self.display_menu.addMenu(_se(t("menu.layout_presets")))
    set_themed_icon(layout_menu, ICON.DISPLAY_STYLE, icon_color)

    layout_menu.setStyleSheet(menu_style)

    self.layout_preset_actions = []

    for idx, (name, shortcut) in enumerate(LAYOUT_PRESET_DEFS):
        act = layout_menu.addAction(f"{name}\t{shortcut}")

        act.triggered.connect(lambda *_, i=idx: apply_layout_preset(self, i))

        self.layout_preset_actions.append(act)

    layout_menu.addSeparator()

    self.preset_load_menu = layout_menu.addMenu(_se(t("menu.load_preset")))
    set_themed_icon(self.preset_load_menu, ICON.PRESET_LOAD, icon_color)

    self.preset_load_menu.aboutToShow.connect(self.preset_manager.update_load_menu)

    layout_menu.addSeparator()

    self.preset_save_menu = layout_menu.addMenu(
        f"{_se(t('menu.save_layout'))}\t{get_key('save_layout')}"
    )
    set_themed_icon(self.preset_save_menu, ICON.SAVE, icon_color)

    self.preset_save_menu.aboutToShow.connect(self.preset_manager.update_save_menu)

    self.preset_rename_menu = layout_menu.addMenu(_se(t("menu.rename_preset")))
    set_themed_icon(self.preset_rename_menu, ICON.EDIT, icon_color)

    self.preset_rename_menu.aboutToShow.connect(self.preset_manager.update_rename_menu)

    self.preset_delete_menu = layout_menu.addMenu(_se(t("menu.delete_preset")))
    set_themed_icon(self.preset_delete_menu, ICON.DELETE, "#d25a66", role="danger")

    self.preset_delete_menu.aboutToShow.connect(self.preset_manager.update_delete_menu)

    self._last_menu_style = menu_style  # stored so manager can reuse it

    # 호환성용 더미 참조 (다른 코드에서 hasattr 체크하는 경우 대비)
    self.theme_menu = None
    self.appearance_menu = self.display_menu
    self.panel_bg_menu = None
    self.panel_bg_recent_menu = None

    self.display_menu_btn.setMenu(self.display_menu)

    def _on_display_menu_show():
        _refresh_display_menu_i18n(self)
        if hasattr(self, "act_topbar") and hasattr(self, "top_bar_frame"):
            self.act_topbar.setChecked(self.top_bar_frame.isVisible())
            any_floating = any(
                getattr(self, attr).isFloating()
                for attr in ("left_dock", "center_dock", "routine_dock", "directive_dock")
                if hasattr(self, attr)
            )
            self.act_topbar.setEnabled(not any_floating)

    self.display_menu.aboutToShow.connect(_on_display_menu_show)
    top_bar.addWidget(self.display_menu_btn)
