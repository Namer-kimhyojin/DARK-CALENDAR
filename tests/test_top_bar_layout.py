# -*- coding: utf-8 -*-
"""Main navigation adapts without losing controls, settings, or dock state."""

from unittest.mock import Mock

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QMenu, QToolButton, QWidget
import pytest

from calendar_app.presentation.dialogs.panel_color_picker_dialog import PanelColorPickerDialog
from calendar_app.presentation.main_window import top_bar_builder
from calendar_app.presentation.main_window.window_shell_actions import WindowShellActionsMixin
from calendar_app.shared.color_utils import derive_panel_palette


@pytest.fixture
def navigation_host(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    host = QMainWindow()
    host.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    host.settings.setValue("panel_base_color", "#243541")
    host.settings.setValue("theme_color", "#efac63")
    host.settings.setValue("last_opacity", 93)
    host.settings.setValue("last_opacity_unit", "byte")
    for name in (
        "open_task_dialog",
        "open_calendar_sync_hub",
        "toggle_lock_mode",
        "toggle_magnet_mode",
        "handle_search_changed",
        "toggle_widget_mode_panel",
        "open_panel_background_color_dialog",
    ):
        setattr(host, name, Mock())

    def menus(owner, layout, *_args):
        for attr in (
            "add_menu_btn",
            "view_menu_btn",
            "display_menu_btn",
            "widgets_menu_btn",
            "sys_menu_btn",
        ):
            button = QToolButton()
            button.setText("Calendar actions")
            button.setMenu(QMenu(owner))
            setattr(owner, attr, button)
            layout.addWidget(button)
        owner.display_window_menu = QMenu(owner)
        for attr in ("act_calendar", "act_today", "act_routine", "act_directive"):
            action = QAction(attr, owner)
            action.setCheckable(True)
            setattr(owner, attr, action)

    monkeypatch.setattr(top_bar_builder, "build_top_left_menus", menus)
    monkeypatch.setattr(top_bar_builder, "apply_top_menu_theme", lambda *args, **kwargs: None)
    top_bar_builder.setup_top_bar(host, 10, "#efac63", lambda value: "#efac63")
    host.setMenuWidget(host.top_bar_frame)
    host.setCentralWidget(QWidget())
    host.show()
    yield host, app
    host.close()


def test_responsive_bar_keeps_actions_and_search_inside_window(navigation_host):
    host, app = navigation_host
    original = {key: host.settings.value(key) for key in host.settings.allKeys()}
    for width in (1800, 640, 840, 1800):
        host.resize(width, 500)
        app.processEvents()
        app.processEvents()
        bar = host.top_bar_frame
        for widget in (
            host.add_menu_btn,
            host.view_menu_btn,
            host.display_menu_btn,
            host.widgets_menu_btn,
            host.sys_menu_btn,
            host.search_edit,
            host.sync_action_btn,
            host.lock_btn,
            host.magnet_btn,
            host.widget_mode_btn,
        ):
            assert widget.isVisible()
            assert widget.geometry().left() >= 0
            assert widget.geometry().right() < bar.width()
        assert host.search_edit.geometry().right() < host.sync_action_btn.geometry().left()
        assert host.add_menu_btn.menu() is not None
        assert host.add_menu_btn.accessibleName()
    assert host.add_menu_btn.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
    assert host.add_menu_btn.text() == host.add_menu_btn.toolTip()
    host.search_edit.setText("Project review")
    host.handle_search_changed.assert_called_once_with("Project review")
    assert {key: host.settings.value(key) for key in host.settings.allKeys()} == original


def test_feather_brandmark_and_wordmark_hide_as_one_compact_group(navigation_host):
    host, app = navigation_host
    group = host.top_bar_frame.findChild(QWidget, "app_brand_group")
    mark = group.findChild(QLabel, "app_brand_icon")
    wordmark = group.findChild(QLabel, "app_brand")
    assert mark is not None and wordmark.text() == "Air Calendar"
    assert not mark.pixmap().isNull()
    for width, visible in ((1600, True), (640, False), (1600, True)):
        host.resize(width, 500)
        app.processEvents()
        app.processEvents()
        assert group.isVisible() is visible
        assert mark.isVisible() is visible
        assert wordmark.isVisible() is visible


def test_brandmark_refreshes_from_custom_accent_without_writing_settings(navigation_host):
    host, app = navigation_host
    mark = host.top_bar_frame.findChild(QLabel, "app_brand_icon")
    first = mark.pixmap().cacheKey()
    host.settings.setValue("theme_color", "#35cda5")
    original = {key: host.settings.value(key) for key in host.settings.allKeys()}
    host.top_bar_frame.setStyleSheet(top_bar_builder.build_top_bar_frame_style(host.settings))
    app.processEvents()
    assert mark.pixmap().cacheKey() != first
    assert {key: host.settings.value(key) for key in host.settings.allKeys()} == original


def test_navigation_uses_existing_panel_actions_and_restores_layout(navigation_host):
    host, app = navigation_host
    rail = host.navigation_rail
    assert host.act_calendar in rail.actions()
    host.act_calendar.setChecked(True)
    assert rail.widgetForAction(host.act_calendar).isChecked()
    rail.actions()[0].trigger()
    host.open_task_dialog.assert_called_once()
    host.addToolBar(Qt.ToolBarArea.RightToolBarArea, rail)
    rail.hide()
    saved_state = host.saveState()
    host.addToolBar(Qt.ToolBarArea.LeftToolBarArea, rail)
    rail.show()
    assert host.restoreState(saved_state)
    app.processEvents()
    assert host.toolBarArea(rail) == Qt.ToolBarArea.RightToolBarArea
    assert rail.isHidden()
    WindowShellActionsMixin._apply_lock_mode_ui(host, True)
    assert not rail.isEnabled() and host.lock_btn.isEnabled()
    WindowShellActionsMixin._apply_lock_mode_ui(host, False)
    assert rail.isEnabled()


def test_navy_lilac_choice_keeps_opacity_and_cancel_keeps_saved_colors(navigation_host):
    host, _app = navigation_host
    original = {key: host.settings.value(key) for key in host.settings.allKeys()}
    dialog = PanelColorPickerDialog(
        current_base="#243541", current_theme="#efac63", current_opacity=93
    )
    dialog._family_btns["navy_lilac"].click()
    assert dialog.selected_base_hex() == "#121827"
    assert dialog.selected_point_hex() == "#c5a3f5"
    assert dialog.selected_opacity() == 93
    dialog._set_appearance_mode("light")
    assert dialog.selected_base_hex() == "#f6f7fb"
    assert dialog.selected_opacity() == 93
    dialog.reject()
    assert {key: host.settings.value(key) for key in host.settings.allKeys()} == original


def test_dark_surfaces_keep_user_opacity_with_visible_surface_hierarchy():
    opaque = derive_panel_palette("#121827", 1.0)
    decorative_roles = ("surface_bg", "toolbar_bg", "topbar_bg", "item_bg", "item_hover_bg")
    assert len({opaque[role] for role in decorative_roles}) == len(decorative_roles)
    assert all(opaque[role].endswith(", 255)") for role in decorative_roles)
    clear = derive_panel_palette("#121827", 0.0)
    assert all(clear[role].endswith(", 0)") for role in decorative_roles)


def test_shell_surfaces_share_one_see_through_level_at_any_opacity():
    for opacity in (0.35, 0.59, 0.9):
        palette = derive_panel_palette("#121827", opacity)
        alphas = {role: palette[role].rsplit(",", 1)[1].strip(" )") for role in ("surface_bg", "topbar_bg")}
        assert alphas["surface_bg"] == alphas["topbar_bg"], (opacity, alphas)
