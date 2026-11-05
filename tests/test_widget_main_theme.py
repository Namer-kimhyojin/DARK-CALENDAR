# -*- coding: utf-8 -*-
"""The widget-only workspace inherits the effective main theme without data writes."""

import json
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QFont, QPalette
from PyQt6.QtWidgets import QApplication
import pytest

from calendar_app.presentation.dialogs.widget_customization_dialog import WidgetCustomizationDialog
from calendar_app.presentation.main_window.theme_actions import ThemeActionsMixin
from calendar_app.presentation.widgets.panel_widget_theme import _build_widget_mode_theme_tokens
from calendar_app.presentation.widgets.unified_widget_mode import _widget_theme_tokens
from calendar_app.presentation.widgets.widget_mode_coordinator import (
    WidgetModeCoordinator,
    WidgetModeState,
)
from calendar_app.presentation.widgets.widget_mode_skins import widget_mode_skins
from calendar_app.shared.system_theme import set_runtime_system_text_theme
from calendar_app.shared.theme_snapshot import build_theme_snapshot
from calendar_app.shared.ui_tokens import get_ui_tokens
from tests.test_widget_mode_ux import (
    Host,
    workspace,  # noqa: F401
)

ROLE_MAP = {
    "accent": "accent",
    "text_primary": "text_primary",
    "text_secondary": "text_secondary",
    "text_faint": "text_faint",
    "input_bg": "input_bg",
    "input_border": "input_border",
    "panel_bg": "bg_main",
    "header_bg": "bg_top",
    "section_bg": "content_bg",
    "card_bg": "bg_item",
    "card_hover": "bg_item_hover",
    "calendar_text": "text_primary",
    "calendar_muted": "text_muted",
    "panel_border": "border",
}


@pytest.mark.parametrize(
    "mode,base,accent",
    [
        ("dark", "#121827", "#c5a3f5"),
        ("light", "#f6f7fb", "#7653c4"),
        ("custom", "#24413f", "#ff9d4d"),
    ],
)
@pytest.mark.parametrize("opacity", [0, 128, 255])
def test_every_skin_reuses_main_roles_and_keeps_saved_widget_identity(
    tmp_path, mode, base, accent, opacity
):
    app = QApplication.instance() or QApplication([])
    host = Host()
    host.settings = QSettings(str(tmp_path / "main.ini"), QSettings.Format.IniFormat)
    for key, value in {
        "text_theme": mode,
        "panel_base_color": base,
        "theme_color": accent,
        "last_opacity": opacity,
        "last_opacity_unit": "byte",
        "widget_mode_color_theme": "#ff00aa",
        "widget_mode_text_opacity": 20,
        "widget_mode_background_opacity": 35,
        "dialog_token.accent": "#FF00AA",
        "oi_sample_bg_color": "#12ab34",
        "oi_sample_font_color": "#ab3412",
    }.items():
        host.settings.setValue(key, value)
    try:
        for skin in widget_mode_skins():
            host.settings.setValue("widget_mode_skin", skin.skin_id)
            before = {key: host.settings.value(key) for key in host.settings.allKeys()}
            expected = get_ui_tokens(host.settings)
            tokens = _widget_theme_tokens(host)
            assert _build_widget_mode_theme_tokens(host) == tokens
            for target, source in ROLE_MAP.items():
                assert tokens[target] == expected[source], (skin.skin_id, target)
            snapshot = build_theme_snapshot(host.settings)
            assert tokens["_main_base_color"] == snapshot.panel_base_color
            assert float(tokens["_main_opacity"]) == snapshot.opacity_factor
            assert tokens["calendar_weekday_sat"] == snapshot.ui_palette["weekday_sat"]
            assert tokens["calendar_weekday_sun"] == snapshot.ui_palette["weekday_sun"]
            assert tokens["hero_bg_strong"] == snapshot.ui_palette["selection_bg"]
            assert {key: host.settings.value(key) for key in host.settings.allKeys()} == before
        output = Path("artifacts/widget-main-theme-20261106/role-metadata")
        output.mkdir(parents=True, exist_ok=True)
        (output / f"{mode}-{opacity}.json").write_text(
            json.dumps(
                {
                    "fixture": "temporary INI, no user widget instances",
                    "requested_mode": mode,
                    "effective_mode": tokens["_main_text_theme"],
                    "effective_base": tokens["_main_base_color"],
                    "accent": tokens["accent"],
                    "opacity": tokens["_main_opacity"],
                    "matching_main_roles": {key: tokens[key] for key in ROLE_MAP},
                    "skins_checked": [skin.skin_id for skin in widget_mode_skins()],
                    "individual_widget_colors_preserved": {
                        "background": host.settings.value("oi_sample_bg_color"),
                        "text": host.settings.value("oi_sample_font_color"),
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
            errors="strict",
        )
    finally:
        host.close()
        host.deleteLater()
        app.processEvents()


def test_active_theme_refresh_and_reopen_keep_mode_layout_cache_and_identity(workspace):
    host, coordinator, widget = workspace
    controller = coordinator.controller
    layout_id, geometry = widget.active_layout_id(), widget.geometry()
    schedule_cache = host._latest_calendar_range_data
    directives = host._latest_directive_data
    host.settings.setValue("oi_clock_custom_color", "#ac1234")
    for mode, base, accent in (("light", "#f6f7fb", "#7653c4"), ("dark", "#121827", "#c5a3f5")):
        for key, value in {
            "text_theme": mode,
            "panel_base_color": base,
            "theme_color": accent,
        }.items():
            host.settings.setValue(key, value)
        with patch.object(controller, "refresh_data") as data_refresh:
            controller.refresh_theme()
            data_refresh.assert_not_called()
        assert _widget_theme_tokens(host)["accent"] == accent
        assert widget.cal_grid._tokens["accent"] == accent
        assert coordinator.state is WidgetModeState.ACTIVE
        assert widget.active_layout_id() == layout_id
        assert widget.geometry() == geometry
        assert host._latest_calendar_range_data is schedule_cache
        assert host._latest_directive_data is directives
        assert host.settings.value("oi_clock_custom_color") == "#ac1234"
    coordinator.exit_widget_mode()
    coordinator.enter()
    assert coordinator.controller.widget.cal_grid._tokens["accent"] == "#c5a3f5"


def test_actual_main_apply_refreshes_existing_workspace_without_data_query():
    class ThemeHost(ThemeActionsMixin, Host):
        pass

    app = QApplication.instance() or QApplication([])
    previous_style = app.styleSheet()
    previous_font = QFont(app.font())
    previous_palette = QPalette(app.palette())
    host = ThemeHost()
    coordinator = WidgetModeCoordinator(host)
    host._widget_mode_coordinator = coordinator
    coordinator.enter()
    try:
        host.settings.setValue("text_theme", "light")
        host.settings.setValue("panel_base_color", "#f6f7fb")
        host.settings.setValue("theme_color", "#7653c4")
        with patch.object(coordinator.controller, "refresh_data") as data_refresh:
            host.apply_theme_settings(persist_opacity=False)
            data_refresh.assert_not_called()
        assert coordinator.controller.widget.cal_grid._tokens["accent"] == "#7653c4"
        host.schedule_panel_refresh.assert_called_with(
            left=True, center=True, right=True, notify_data_consumers=False
        )
    finally:
        coordinator.close_for_shutdown()
        coordinator.controller.widget.deleteLater()
        host.close()
        host.deleteLater()
        app.processEvents()
        app.setStyleSheet(previous_style)
        app.setFont(previous_font)
        app.setPalette(previous_palette)


def test_preferences_show_theme_link_and_leave_old_opacity_data_intact(workspace):
    host, coordinator, widget = workspace
    host.settings.setValue("widget_mode_background_opacity", 35)
    host.settings.setValue("widget_mode_text_opacity", 55)
    dialog = WidgetCustomizationDialog(coordinator.controller, widget)
    try:
        assert not dialog.text_opacity.isEnabled()
        assert not dialog.background_opacity.isEnabled()
        assert dialog.text_opacity.value() == 100
        assert "메인" in dialog.background_opacity.toolTip()
        before_opacity = dialog.background_opacity.value()
        dialog._sync_appearance_controls()
        assert dialog.background_opacity.value() == before_opacity
        dialog.reject()
        assert host.settings.value("widget_mode_background_opacity") == 35
        assert host.settings.value("widget_mode_text_opacity") == 55
    finally:
        dialog.close()
        dialog.deleteLater()


def test_auto_mode_uses_effective_main_family_without_rewriting_stored_colors():
    app = QApplication.instance() or QApplication([])
    host = Host()
    host.settings.values.update(
        {
            "text_theme": "auto",
            "panel_base_color": "#121827",
            "theme_color": "#c5a3f5",
            "appearance_style_family": "navy_lilac",
            "appearance_base_source": "family",
            "appearance_accent_source": "family",
            "appearance_family_dark_base": "#121827",
            "appearance_family_light_base": "#f6f7fb",
            "appearance_family_dark_accent": "#c5a3f5",
            "appearance_family_light_accent": "#7653c4",
            "widget_mode_skin": "classic_dark",
        }
    )
    before = dict(host.settings.values)
    try:
        for mode in ("light", "dark"):
            set_runtime_system_text_theme(mode)
            tokens = _widget_theme_tokens(host)
            main = get_ui_tokens(host.settings)
            for target, source in ROLE_MAP.items():
                assert tokens[target] == main[source]
            assert tokens["_main_text_theme"] == mode
            assert host.settings.values == before
    finally:
        set_runtime_system_text_theme(None)
        host.close()
        host.deleteLater()
        app.processEvents()
