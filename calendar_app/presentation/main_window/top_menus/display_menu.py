from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu, QToolButton

from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.runtime.keyboard_shortcuts import get_key
from calendar_app.presentation.main_window.top_menus.common import format_top_menu_button_text
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.icon_map import strip_leading_emoji as _se


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
    """캘린더 가시성 토글 서브메뉴를 동적으로 구성합니다."""
    menu.clear()
    menu.setStyleSheet(menu_style)
    try:
        from PyQt6.QtGui import QColor, QIcon, QPixmap

        from calendar_app.infrastructure.db.calendar_repo import (
            list_calendars,
            set_calendar_visible,
        )

        calendars = list_calendars(include_inactive=False)
    except Exception:
        menu.addAction(t("menu.calendar_load_error", "캘린더 로드 실패")).setEnabled(False)
        return

    if not calendars:
        menu.addAction(t("menu.no_calendars", "캘린더 없음")).setEnabled(False)
        return

    for cal in calendars:
        cal_id = cal.get("id") or ""
        name = cal.get("name") or cal_id
        is_visible = bool(cal.get("is_visible", 1))
        color = cal.get("color") or "#4a9eff"

        # 16x16 색상 패치를 아이콘으로 사용
        pix = QPixmap(14, 14)
        pix.fill(QColor(color))
        color_icon = QIcon(pix)

        act = menu.addAction(color_icon, name)
        act.setCheckable(True)
        act.setChecked(is_visible)

        def _on_toggle(checked, _cal_id=cal_id):
            set_calendar_visible(_cal_id, checked)
            if hasattr(app, "schedule_panel_refresh"):
                app.schedule_panel_refresh(left=True, center=True)

        act.triggered.connect(_on_toggle)


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
    self.display_menu_btn = QToolButton()

    self.display_menu_btn.setText(format_top_menu_button_text(t("menu.display_btn", "화면")))
    self.display_menu_btn.setIcon(_ic(ICON.SCREEN_MGMT))
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
    act_tv.setIcon(_ic(ICON.VIEW_CALENDAR))

    self.panel_menu = self.display_menu.addMenu(_se(t("menu.panel_settings")))
    self.panel_menu.setIcon(_ic(ICON.DISPLAY_STYLE))

    self.act_today = self.panel_menu.addAction(_se(t("menu.panel_today")))
    self.act_today.setIcon(_ic(ICON.STATUS_TODAY))
    self.act_today.setCheckable(True)

    self.act_today.triggered.connect(
        lambda *args: _toggle_dock(self, "left_dock", self.act_today.isChecked())
    )

    self.act_calendar = self.panel_menu.addAction(_se(t("menu.panel_calendar")))
    self.act_calendar.setIcon(_ic(ICON.VIEW_CALENDAR))
    self.act_calendar.setCheckable(True)

    self.act_calendar.triggered.connect(
        lambda *args: _toggle_dock(self, "center_dock", self.act_calendar.isChecked())
    )

    self.act_routine = self.panel_menu.addAction(_se(t("menu.panel_routine")))
    self.act_routine.setIcon(_ic(ICON.ROUTINE))
    self.act_routine.setCheckable(True)

    self.act_routine.triggered.connect(
        lambda *args: _toggle_dock(self, "routine_dock", self.act_routine.isChecked())
    )

    self.act_directive = self.panel_menu.addAction(_se(t("menu.panel_directive")))
    self.act_directive.setIcon(_ic(ICON.DIRECTIVE))
    self.act_directive.setCheckable(True)

    self.act_directive.triggered.connect(
        lambda *args: _toggle_dock(self, "directive_dock", self.act_directive.isChecked())
    )

    self.display_menu.addSeparator()

    self.act_topbar = self.display_menu.addAction(
        f"{_se(t('menu.hide_topbar'))}\t{get_key('topbar')}"
    )
    self.act_topbar.setIcon(_ic(ICON.HIDE))
    self.act_topbar.setCheckable(True)

    self.act_topbar.setChecked(True)

    self.act_topbar.triggered.connect(self.toggle_top_bar)

    self.act_calendar_toolbar = self.display_menu.addAction(
        f"{_se(t('menu.hide_calendar_toolbar'))}\t{get_key('cal_toolbar')}"
    )
    self.act_calendar_toolbar.setIcon(_ic(ICON.SCREEN_MGMT))
    self.act_calendar_toolbar.setCheckable(True)

    self.act_calendar_toolbar.setChecked(self._calendar_toolbar_visible_setting())

    self.act_calendar_toolbar.triggered.connect(self.set_calendar_toolbar_visible)

    act_fs = self.display_menu.addAction(
        f"{_se(t('menu.fullscreen'))}\t{get_key('fullscreen')}", self.toggle_fullscreen
    )
    act_fs.setIcon(_ic(ICON.FULLSCREEN))

    act_fm = self.display_menu.addAction(
        f"{_se(t('menu.focus_mode'))}\t{get_key('focus_mode')}", self.toggle_focus_mode
    )
    act_fm.setIcon(_ic(ICON.POMODORO))

    act_wm = self.display_menu.addAction(
        f"{_se(t('menu.widget_mode_toggle', '위젯 전용 모드'))}\t{get_key('widget_mode', 'F12')}",
        self.toggle_widget_mode_panel,
    )
    act_wm.setIcon(_ic(ICON.WIDGET_MGR))

    self.instant_away_act = self.display_menu.addAction(
        _se(t("menu.instant_away")), lambda: self.toggle_idle_lock(True, manual=True)
    )
    self.instant_away_act.setIcon(_ic(ICON.LOCK))

    self.display_menu.addSeparator()

    self.calendar_visibility_menu = self.display_menu.addMenu(
        _se(t("menu.calendar_visibility", "캘린더 표시"))
    )
    self.calendar_visibility_menu.setIcon(_ic(ICON.VIEW_CALENDAR))
    self.calendar_visibility_menu.aboutToShow.connect(
        lambda: _update_calendar_visibility_menu(self, self.calendar_visibility_menu, menu_style)
    )

    self.display_menu.addSeparator()

    self.theme_mode_menu = self.display_menu.addMenu(_se(t("menu.theme_mode", "테마 모드")))
    self.theme_mode_menu.setIcon(_ic(ICON.COLOR_PICKER))

    current_mode = self.settings.value("text_theme", "dark")

    act_dark = self.theme_mode_menu.addAction(
        t("theme.dark_mode", "다크 모드"), lambda: self.change_text_theme("dark")
    )
    act_dark.setIcon(_ic(ICON.THEME_DARK))
    act_dark.setCheckable(True)
    act_dark.setChecked(current_mode == "dark")

    act_light = self.theme_mode_menu.addAction(
        t("theme.light_mode", "라이트 모드"), lambda: self.change_text_theme("light")
    )
    act_light.setIcon(_ic(ICON.THEME_LIGHT))
    act_light.setCheckable(True)
    act_light.setChecked(current_mode == "light")

    act_auto = self.theme_mode_menu.addAction(
        t("theme.system_default", "시스템 기본"), self.set_system_default_theme
    )
    act_auto.setIcon(_ic(ICON.THEME_AUTO))
    act_auto.setCheckable(True)
    act_auto.setChecked(current_mode == "auto")

    act_theme = self.display_menu.addAction(
        _se(t("menu.ui_theme_open", "UI 테마 상세 설정...")),
        self.open_panel_background_color_dialog,
    )
    act_theme.setIcon(_ic(ICON.COLOR_PICKER))

    self.display_menu.addSeparator()

    from calendar_app.presentation.main_window.dock_sections.dock_layout_presets import (
        LAYOUT_PRESET_DEFS,
        apply_layout_preset,
    )

    layout_menu = self.display_menu.addMenu(_se(t("menu.layout_presets")))
    layout_menu.setIcon(_ic(ICON.DISPLAY_STYLE))

    layout_menu.setStyleSheet(menu_style)

    self.layout_preset_actions = []

    for idx, (name, shortcut) in enumerate(LAYOUT_PRESET_DEFS):
        act = layout_menu.addAction(f"{name}\t{shortcut}")

        act.triggered.connect(lambda *_, i=idx: apply_layout_preset(self, i))

        self.layout_preset_actions.append(act)

    layout_menu.addSeparator()

    self.preset_load_menu = layout_menu.addMenu(_se(t("menu.load_preset")))
    self.preset_load_menu.setIcon(_ic(ICON.PRESET_LOAD))

    self.preset_load_menu.aboutToShow.connect(self.preset_manager.update_load_menu)

    layout_menu.addSeparator()

    self.preset_save_menu = layout_menu.addMenu(
        f"{_se(t('menu.save_layout'))}\t{get_key('save_layout')}"
    )
    self.preset_save_menu.setIcon(_ic(ICON.SAVE))

    self.preset_save_menu.aboutToShow.connect(self.preset_manager.update_save_menu)

    self.preset_rename_menu = layout_menu.addMenu(_se(t("menu.rename_preset")))
    self.preset_rename_menu.setIcon(_ic(ICON.EDIT))

    self.preset_rename_menu.aboutToShow.connect(self.preset_manager.update_rename_menu)

    self.preset_delete_menu = layout_menu.addMenu(_se(t("menu.delete_preset")))
    self.preset_delete_menu.setIcon(_ic(ICON.DELETE))

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
