# -*- coding: utf-8 -*-
from pathlib import Path
import unittest

from PyQt6.QtGui import QColor

from calendar_app.presentation.calendar.month_renderer import (
    _calendar_default_accent,
    _calendar_scroll_style,
    _calendar_surface_style,
    _calendar_toolbar_shell_style,
    _calendar_toolbar_style_bundle,
    _subscription_detail_style_bundle,
    _theme_harmonized_color,
)
from calendar_app.presentation.dialogs.away_settings_dialog import _away_style_bundle
from calendar_app.presentation.dialogs.checklist_manager_dialog_advanced import (
    DIALOG_STYLE as CHECKLIST_DIALOG_STYLE,
)
from calendar_app.presentation.dialogs.checklist_manager_dialog_advanced import (
    _checklist_editor_stylesheet,
    _checklist_main_style_bundle,
    _checklist_row_palette,
    _checklist_shell_stylesheet,
    _checklist_subdialog_style_bundle,
)
from calendar_app.presentation.dialogs.checklist_manager_dialog_advanced import (
    _dialog_style as _checklist_dialog_style,
)
from calendar_app.presentation.dialogs.dialog_editor_styles import (
    build_editor_counter_style,
    build_editor_hint_style,
    build_editor_quick_button_style,
    build_editor_text_style,
    build_task_editor_stylesheet,
    build_transparent_stack_stylesheet,
)
from calendar_app.presentation.dialogs.dialog_styles import (
    DIALOG_METRIC_DEFAULTS,
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)
from calendar_app.presentation.dialogs.dialog_token_editor_dialog import (
    _dialog_token_editor_style_bundle,
)
from calendar_app.presentation.dialogs.eod_report_dialog import _eod_report_style_bundle
from calendar_app.presentation.dialogs.focus_log_dialog import _focus_log_style_bundle
from calendar_app.presentation.dialogs.gcal_settings_dialog import (
    _GCAL_STYLE_TEMPLATE,
    _build_gcal_stylesheet,
    _gcal_editor_dialog_stylesheet,
    _gcal_runtime_style_bundle,
    _gcal_visibility_button_style,
)
from calendar_app.presentation.dialogs.gcal_sync_issues_dialog import _gcal_issue_style_bundle
from calendar_app.presentation.dialogs.label_settings_dialog import (
    _emoji_picker_stylesheet,
    _label_settings_style_bundle,
)
from calendar_app.presentation.dialogs.management_dialogs import (
    _management_header_style,
    _status_background,
)
from calendar_app.presentation.dialogs.panel_color_picker_dialog import (
    _build_picker_extra_stylesheet,
)
from calendar_app.presentation.dialogs.routine_recurrence_wizard import (
    _build_routine_wizard_stylesheet,
)
from calendar_app.presentation.main_window.app_window import OverlayApp
from calendar_app.presentation.panels.side_panel_renderer import (
    _panel_menu_style,
    _panel_scroll_style,
    _panel_surface_style,
    _toolbar_button_style,
)
from calendar_app.presentation.theme.style_builder import build_global_stylesheet
from calendar_app.presentation.theme.ui_tokens import get_ui_shape_tokens
from calendar_app.presentation.widgets.alarm_popup import (
    _alarm_popup_style_bundle,
    _alarm_time_label_style,
    _build_alarm_popup_stylesheet,
)
from calendar_app.presentation.widgets.command_palette import (
    _build_command_palette_stylesheet,
    _command_palette_style_bundle,
)
from calendar_app.presentation.widgets.overlay_base import (
    _apply_widget_dialog_tokens,
    _build_overlay_dialog_stylesheet,
    _overlay_color_button_style,
    _overlay_dialog_style_bundle,
    _overlay_hint_toggle_style,
    _overlay_menu_style,
)
from calendar_app.presentation.widgets.overlay_datecard import (
    _datecard_contrast_text,
    _datecard_qcolor,
    _datecard_theme_bundle,
    _week_strip_label_style,
)
from calendar_app.presentation.widgets.overlay_manager import _default_menu_style
from calendar_app.presentation.widgets.overlay_manager_dialog import (
    _build_web_ui_stylesheet,
    _overlay_action_icon_style,
    _overlay_manager_style_bundle,
    _overlay_toggle_styles,
)
from calendar_app.presentation.widgets.ui_components import (
    _checklist_row_style_bundle,
    _contrast_pen_color,
    _hover_info_popup_stylesheet,
    _qcolor,
    _selection_overlay_style,
    _task_chip_style_bundle,
    _task_context_menu_style,
    _task_detail_card_style,
    _task_title_label_style,
)
from calendar_app.shared.color_utils import derive_ui_palette
from calendar_app.shared.theme_snapshot import (
    build_shape_tokens,
    build_theme_snapshot,
    build_widget_mode_tokens,
)
from calendar_app.shared.ui_tokens import get_shared_qss, get_ui_tokens


class _FakeSettings:
    def __init__(self):
        self.values = {}

    def setValue(self, key, value):
        self.values[key] = value

    def value(self, key, default=None, type=None):
        return self.values.get(key, default)

    def remove(self, key):
        self.values.pop(key, None)


class _FakePaletteHost:
    def __init__(self):
        self.settings = _FakeSettings()
        self.theme_apply_calls = 0

    def apply_theme_settings(self):
        self.theme_apply_calls += 1


class ThemeContractTests(unittest.TestCase):
    def test_dialog_button_object_names_use_tokenized_variants(self):
        dialogs_dir = Path("calendar_app/presentation/dialogs")
        legacy_names = ("PrimaryBtn", "SecondaryBtn", "DangerBtn")
        offenders = []

        for path in sorted(dialogs_dir.glob("*.py")):
            text = path.read_text(encoding="utf-8", errors="strict")
            for legacy_name in legacy_names:
                if legacy_name in text:
                    offenders.append(f"{path}:{legacy_name}")

        self.assertEqual([], offenders)

    def test_command_palette_theme_commands_use_apply_theme_settings(self):
        host = _FakePaletteHost()

        OverlayApp.handle_palette_command(host, "theme_dark", {})
        self.assertEqual(host.settings.value("text_theme"), "dark")
        self.assertEqual(host.settings.value("panel_base_color"), "#1c1c1c")
        self.assertEqual(host.theme_apply_calls, 1)

        OverlayApp.handle_palette_command(host, "theme_light", {})
        self.assertEqual(host.settings.value("text_theme"), "light")
        self.assertEqual(host.settings.value("panel_base_color"), "#fefefe")
        self.assertEqual(host.theme_apply_calls, 2)

    def test_command_palette_style_bundle_uses_semantic_tokens(self):
        tokens = {
            "accent": "#22c3ca",
            "accent_soft": "rgba(34,195,202,40)",
            "bg_main": "rgba(12,24,36,230)",
            "bg_item": "rgba(255,255,255,0.06)",
            "bg_item_hover": "rgba(255,255,255,0.12)",
            "bg_hover": "rgba(0,0,0,0.24)",
            "text_primary": "#eff4fa",
            "text_secondary": "#c3cfdd",
            "text_muted": "#93a1b4",
            "border": "rgba(255,255,255,0.16)",
            "border_soft": "rgba(255,255,255,0.10)",
            "divider": "rgba(255,255,255,0.08)",
        }
        metrics = {
            "field_radius": 9,
            "button_radius": 8,
            "list_item_radius": 6,
            "field_padding_x": 12,
            "field_padding_y": 5,
        }

        bundle = _command_palette_style_bundle(tokens=tokens, metrics=metrics)
        stylesheet = _build_command_palette_stylesheet(bundle)

        self.assertEqual(bundle["container_bg"], "rgba(12,24,36,230)")
        self.assertEqual(bundle["preview_text"], "#22c3ca")
        self.assertEqual(bundle["container_radius"], 16)
        self.assertEqual(bundle["input_radius"], 15)
        self.assertEqual(bundle["item_radius"], 10)
        self.assertEqual(bundle["shadow_color"].alpha(), 220)
        self.assertIn("background-color: rgba(12,24,36,230);", stylesheet)
        self.assertIn("color: #22c3ca;", stylesheet)

    def test_overlay_manager_helpers_use_dialog_tokens(self):
        tokens = {
            "accent": "#22c3ca",
            "surface_bg": "rgba(12,24,36,230)",
            "surface_alt": "rgba(18,30,42,220)",
            "surface_item": "rgba(24,36,48,220)",
            "surface_hover": "rgba(255,255,255,0.08)",
            "text_primary": "#eff4fa",
            "text_muted": "#93a1b4",
            "border": "rgba(255,255,255,0.16)",
            "border_soft": "rgba(255,255,255,0.10)",
            "success_hex": "#47d27e",
            "danger_hex": "#d25a66",
        }
        metrics = {
            "field_radius": 9,
            "list_radius": 8,
            "button_radius": 8,
            "toolbutton_radius": 7,
            "subtitle_font_pt": 11,
        }

        bundle = _overlay_manager_style_bundle(tokens=tokens, metrics=metrics)
        shell_qss = _build_web_ui_stylesheet(tokens, metrics)
        toggle = _overlay_toggle_styles(tokens=tokens, metrics=metrics)
        accent_icon = _overlay_action_icon_style(tokens=tokens, metrics=metrics, tone="accent")
        danger_icon = _overlay_action_icon_style(tokens=tokens, metrics=metrics, tone="danger")

        self.assertIn("background: rgba(18,30,42,220);", bundle["add_bar"])
        self.assertIn("color: #93a1b4;", bundle["description"])
        self.assertIn("font-size:", bundle["row_name"])
        self.assertEqual(bundle["accent"], "#22c3ca")
        self.assertEqual(bundle["danger"], "#d25a66")
        self.assertIn("border-radius: 9px;", shell_qss)
        self.assertIn("border-radius: 10px;", shell_qss)
        self.assertIn("#47d27e", toggle["on"])
        self.assertIn("#d25a66", danger_icon)
        self.assertIn("#22c3ca", accent_icon)

    def test_overlay_base_dialog_and_menu_helpers_use_dialog_metrics(self):
        tokens = {
            "accent": "#22c3ca",
            "accent_hover": "#5de0e5",
            "surface_bg": "rgba(12,24,36,230)",
            "surface_alt": "rgba(18,30,42,220)",
            "surface_item": "rgba(24,36,48,220)",
            "surface_hover": "rgba(255,255,255,0.08)",
            "surface_top": "rgba(9,16,24,230)",
            "text_primary": "#eff4fa",
            "text_secondary": "#c3cfdd",
            "text_muted": "#93a1b4",
            "text_faint": "#7b889c",
            "border": "rgba(255,255,255,0.16)",
            "border_soft": "rgba(255,255,255,0.10)",
        }
        metrics = {
            "list_radius": 9,
            "group_radius": 5,
            "tab_radius": 3,
            "field_radius": 4,
            "button_radius": 8,
            "checkbox_indicator_size": 15,
            "list_item_radius": 7,
        }

        bundle = _overlay_dialog_style_bundle(tokens=tokens, metrics=metrics)
        dialog_qss = _build_overlay_dialog_stylesheet(tokens=tokens, metrics=metrics)
        menu_qss = _overlay_menu_style(tokens=tokens, metrics=metrics)
        applied = _apply_widget_dialog_tokens(
            "QPushButton#presetBtn { border-radius: 4px; }", tokens=tokens, metrics=metrics
        )

        self.assertEqual(bundle["panel_radius"], 13)
        self.assertEqual(bundle["hint_radius"], 10)
        self.assertEqual(bundle["menu_radius"], 9)
        self.assertEqual(bundle["menu_item_radius"], 7)
        self.assertIn("background: rgba(12,24,36,230);", dialog_qss)
        self.assertIn("border-radius: 13px;", dialog_qss)
        self.assertIn("border-radius: 9px;", menu_qss)
        self.assertIn("border-radius: 7px;", menu_qss)
        self.assertIn("rgba(34,195,202,0.32)", menu_qss)
        self.assertIn("border-radius: 7px;", applied)

    def test_overlay_manager_default_menu_style_uses_overlay_menu_helper(self):
        self.assertEqual(_default_menu_style(), _overlay_menu_style())

    def test_overlay_base_button_and_hint_helpers_use_dialog_tokens(self):
        tokens = {
            "border": "rgba(255,255,255,0.16)",
            "text_muted": "#93a1b4",
            "text_secondary": "#c3cfdd",
        }
        metrics = {"button_radius": 8}

        color_btn_qss = _overlay_color_button_style(
            "rgba(12,24,36,220)", tokens=tokens, metrics=metrics
        )
        hint_toggle_qss = _overlay_hint_toggle_style(tokens=tokens)

        self.assertIn("background: rgba(12,24,36,220);", color_btn_qss)
        self.assertIn("border: 1px solid rgba(255,255,255,0.16);", color_btn_qss)
        self.assertIn("border-radius: 7px;", color_btn_qss)
        self.assertIn("color:#93a1b4", hint_toggle_qss)
        self.assertIn("color:#c3cfdd", hint_toggle_qss)

    def test_alarm_popup_helpers_use_semantic_tokens(self):
        tokens = {
            "accent": "#22c3ca",
            "accent_hover": "#5de0e5",
            "bg_main": "rgba(12,24,36,230)",
            "bg_alt": "rgba(18,30,42,220)",
            "bg_item_hover": "rgba(255,255,255,0.08)",
            "border": "rgba(255,255,255,0.16)",
            "text_primary": "#eff4fa",
            "text_secondary": "#c3cfdd",
            "text_muted": "#93a1b4",
            "warning_hex": "#f0a030",
            "success_hex": "#46CC71",
            "danger_hex": "#e05050",
        }
        metrics = {
            "button_radius": 8,
            "list_radius": 9,
            "list_item_radius": 7,
            "subtitle_font_pt": 11,
        }

        bundle = _alarm_popup_style_bundle(tokens=tokens, metrics=metrics)
        stylesheet = _build_alarm_popup_stylesheet(bundle)
        warning_style = _alarm_time_label_style("warning", bundle)
        danger_style = _alarm_time_label_style("danger", bundle)

        self.assertEqual(bundle["card_radius"], 15)
        self.assertEqual(bundle["button_radius"], 9)
        self.assertEqual(bundle["menu_radius"], 9)
        self.assertIn("background: rgba(12,24,36,230);", stylesheet)
        self.assertIn("background-color: rgba(18,30,42,220);", stylesheet)
        self.assertIn("border-radius: 9px;", stylesheet)
        self.assertIn("#f0a030", warning_style)
        self.assertIn("#e05050", danger_style)

    def test_derive_ui_palette_uses_active_theme_accent_for_text_tokens(self):
        palette = derive_ui_palette(
            text_theme="dark",
            panel_base_color="#1c1c1c",
            opacity_factor=1.0,
            theme_color="#ff00aa",
        )

        self.assertEqual(palette["text_accent"], "rgba(255, 0, 170, 255)")
        self.assertEqual(palette["text_accent_soft"], "rgba(255, 0, 170, 214)")

    def test_shared_and_dialog_tokens_share_same_theme_snapshot_core_values(self):
        settings = _FakeSettings()
        settings.setValue("theme_color", "#22c3ca")
        settings.setValue("text_theme", "light")
        settings.setValue("panel_base_color", "#eef2f6")
        settings.setValue("custom_input_bg", "#f7fbff")

        snapshot = build_theme_snapshot(settings=settings, opacity_factor=1.0)
        shared_tokens = get_ui_tokens(settings=settings, opacity_factor=1.0)
        dialog_tokens = get_dialog_theme_tokens(settings=settings, apply_overrides=False)

        self.assertEqual(snapshot.theme_color, "#22c3ca")
        self.assertEqual(shared_tokens["accent"], snapshot.theme_color)
        self.assertEqual(dialog_tokens["accent"], snapshot.theme_color)
        self.assertEqual(shared_tokens["text_primary"], dialog_tokens["text_primary"])
        self.assertEqual(shared_tokens["input_bg"], "#f7fbff")
        self.assertEqual(dialog_tokens["input_bg"], "#f7fbff")
        self.assertEqual(shared_tokens["bg_item"], dialog_tokens["surface_item"])

    def test_widget_mode_tokens_are_built_from_shared_theme_builder(self):
        settings = _FakeSettings()
        settings.setValue("theme_color", "#4da6ff")
        settings.setValue("text_theme", "dark")
        settings.setValue("panel_base_color", "#1c1c1c")
        settings.setValue("ui_shape_preset", "modern")

        tokens = build_widget_mode_tokens(settings=settings)

        self.assertEqual(tokens["accent"], "#22c3ca")
        self.assertEqual(tokens["card_text_primary"], "#31465f")
        self.assertIn("shell_gradient_start", tokens)
        self.assertEqual(tokens["widget_surface_radius"], "16")
        self.assertEqual(tokens["widget_calendar_nav_radius"], "8")
        self.assertEqual(tokens["widget_chip_radius"], "10")

    def test_shape_tokens_are_served_by_shared_builder(self):
        settings = _FakeSettings()
        settings.setValue("ui_shape_preset", "modern")

        shared_shape = build_shape_tokens(settings=settings)
        presentation_shape = get_ui_shape_tokens(settings=settings)

        self.assertEqual(shared_shape["tooltip_radius"], 10)
        self.assertEqual(presentation_shape, shared_shape)

    def test_dialog_metric_tokens_accept_shared_override_pipeline(self):
        settings = _FakeSettings()
        settings.setValue("dialog_token.metric.button_radius", 12)
        settings.setValue("dialog_token.metric.field_height", 40)

        metrics = get_dialog_metric_tokens(apply_overrides=True, settings=settings)

        self.assertEqual(metrics["button_radius"], 12)
        self.assertEqual(metrics["field_height"], 40)
        self.assertEqual(metrics["tab_radius"], DIALOG_METRIC_DEFAULTS["tab_radius"])

    def test_shared_ui_tokens_and_picker_styles_follow_shape_metric_overrides(self):
        settings = _FakeSettings()
        settings.setValue("ui_shape_preset", "modern")
        settings.setValue("dialog_token.metric.field_height", 42)
        settings.setValue("dialog_token.metric.field_radius", 11)
        settings.setValue("dialog_token.metric.button_height", 39)
        settings.setValue("dialog_token.metric.button_radius", 13)

        snapshot = build_theme_snapshot(settings=settings)
        tokens = get_ui_tokens(settings=settings)
        shared_qss = get_shared_qss(tokens)
        picker_qss = _build_picker_extra_stylesheet(tokens=tokens)

        self.assertEqual(snapshot.dialog_metrics["field_height"], 42)
        self.assertEqual(tokens["field_height"], "42px")
        self.assertEqual(tokens["field_radius"], "11px")
        self.assertEqual(tokens["button_height"], "39px")
        self.assertEqual(tokens["button_radius"], "13px")
        self.assertEqual(tokens["panel_radius"], "14px")
        self.assertEqual(tokens["toolbar_button_radius"], "8px")
        self.assertIn("border-radius: 11px;", shared_qss)
        self.assertIn("min-height: 42px;", shared_qss)
        self.assertIn("border-radius: 8px;", picker_qss)
        self.assertIn("border-radius: 10px;", picker_qss)
        self.assertIn("QPushButton#fontComboPopupButton", picker_qss)
        self.assertNotIn("data:image/svg+xml", picker_qss)

    def test_panel_style_builders_consume_semantic_tokens(self):
        tokens = {
            "bg_main": "rgba(8,18,28,230)",
            "bg_alt": "rgba(10,20,30,220)",
            "bg_item": "rgba(22,32,42,180)",
            "bg_item_hover": "rgba(40,50,60,180)",
            "text_primary": "#f5f7fb",
            "text_secondary": "#ccd5e1",
            "text_muted": "#93a1b4",
            "text_faint": "#6d7a8c",
            "border": "rgba(255,255,255,32)",
            "divider": "rgba(255,255,255,12)",
            "accent_soft": "rgba(34,195,202,40)",
            "accent_border": "rgba(34,195,202,110)",
        }
        shape = {
            "panel_surface_radius": 13,
            "panel_toolbar_button_radius": 9,
            "panel_menu_radius": 12,
            "panel_menu_item_radius": 7,
        }

        surface_qss = _panel_surface_style(tokens=tokens, shape=shape)
        toolbar_qss = _toolbar_button_style(tokens=tokens, shape=shape)
        menu_qss = _panel_menu_style(tokens=tokens, shape=shape)
        default_tokens = get_ui_tokens()
        partial_toolbar_qss = _toolbar_button_style(tokens={"accent": "#22c3ca"}, shape=shape)
        partial_menu_qss = _panel_menu_style(tokens={"accent": "#22c3ca"}, shape=shape)

        self.assertIn("background-color: rgba(8,18,28,230);", surface_qss)
        self.assertIn("border-radius: 13px;", surface_qss)
        self.assertIn("border-radius: 9px;", toolbar_qss)
        self.assertIn("background-color: rgba(40,50,60,180);", toolbar_qss)
        self.assertIn("background-color: rgba(10,20,30,220);", menu_qss)
        self.assertIn("border: 1px solid rgba(34,195,202,110);", menu_qss)
        self.assertIn("border-radius: 12px;", menu_qss)
        self.assertIn("border-radius: 7px;", menu_qss)
        self.assertIn(f"color: {default_tokens['text_secondary']};", partial_toolbar_qss)
        self.assertIn(f"background-color: {default_tokens['bg_alt']};", partial_menu_qss)
        self.assertEqual(
            _panel_scroll_style(), "QScrollArea { background: transparent; border: none; }"
        )

    def test_management_helpers_use_dialog_semantic_tokens(self):
        tokens = {
            "accent": "#22c3ca",
            "success_hex": "#35b66a",
            "warning_hex": "#d39a2a",
            "danger_hex": "#d25a66",
        }
        metrics = {"title_font_pt": 19}

        header_style = _management_header_style(tokens=tokens, metrics=metrics)
        in_progress_bg = _status_background("in_progress", tokens=tokens)
        completed_bg = _status_background("completed", tokens=tokens)

        self.assertIn("font-size: 19pt;", header_style)
        self.assertIn("color: #22c3ca;", header_style)
        self.assertEqual(in_progress_bg.name(QColor.NameFormat.HexRgb), "#22c3ca")
        self.assertEqual(in_progress_bg.alpha(), 48)
        self.assertEqual(completed_bg.name(QColor.NameFormat.HexRgb), "#35b66a")

    def test_calendar_toolbar_and_detail_helpers_use_semantic_tokens(self):
        tokens = {
            "accent": "#22c3ca",
            "accent_soft": "rgba(34,195,202,40)",
            "accent_border": "rgba(34,195,202,110)",
            "bg_main": "rgba(9,19,29,230)",
            "bg_top": "rgba(12,24,36,220)",
            "bg_alt": "rgba(16,28,40,220)",
            "bg_item": "rgba(255,255,255,0.06)",
            "bg_item_hover": "rgba(255,255,255,0.12)",
            "bg_hover": "rgba(255,255,255,0.10)",
            "text_primary": "#eff4fa",
            "text_secondary": "#c3cfdd",
            "border": "rgba(255,255,255,0.14)",
            "border_strong": "rgba(255,255,255,0.26)",
            "divider": "rgba(255,255,255,0.08)",
        }
        shape = {
            "calendar_surface_radius": 15,
            "calendar_toolbar_surface_radius": 11,
            "calendar_toolbar_button_radius": 9,
            "calendar_menu_radius": 7,
            "calendar_menu_item_radius": 5,
            "calendar_date_badge_radius": 13,
            "calendar_selection_badge_radius": 14,
            "calendar_more_button_radius": 6,
        }

        surface_qss = _calendar_surface_style(tokens=tokens, shape=shape)
        shell_qss = _calendar_toolbar_shell_style(True, tokens=tokens, shape=shape)
        bundle = _calendar_toolbar_style_bundle(tokens=tokens, shape=shape)
        detail_bundle = _subscription_detail_style_bundle(tokens=tokens, shape=shape)
        default_tokens = get_ui_tokens()
        partial_bundle = _calendar_toolbar_style_bundle(tokens={"accent": "#22c3ca"}, shape=shape)
        partial_detail = _subscription_detail_style_bundle(
            tokens={"accent": "#22c3ca"}, shape=shape
        )

        self.assertIn("background-color: rgba(9,19,29,230);", surface_qss)
        self.assertIn("border-radius: 15px;", surface_qss)
        self.assertIn("background-color: rgba(12,24,36,220);", shell_qss)
        self.assertIn("border-radius: 11px;", shell_qss)
        self.assertIn("border-radius: 9px;", bundle["today_btn"])
        self.assertIn("border-radius: 9px;", bundle["icon_btn"])
        self.assertIn("border-radius: 7px;", bundle["dropdown_menu"])
        self.assertIn("border-radius: 5px;", bundle["dropdown_menu"])
        self.assertIn("border-radius: 13px;", bundle["date_label"])
        self.assertIn("border-radius: 14px;", bundle["selection_label"])
        self.assertIn("border-radius: 6px;", bundle["more_btn"])
        self.assertIn("color: #22c3ca;", detail_bundle["title"])
        self.assertIn("border-radius: 5px;", detail_bundle["copy_btn"])
        self.assertIn("color: #eff4fa;", detail_bundle["value"])
        self.assertIn("color: #c3cfdd;", detail_bundle["key_label"])
        self.assertIn("border-radius: 9px;", partial_bundle["nav_btn"])
        self.assertEqual(partial_detail["scroll"], _calendar_scroll_style())
        self.assertIn(f"color: {default_tokens['text_secondary']};", partial_detail["key_label"])
        self.assertIn(f"color: {default_tokens['text_primary']};", partial_detail["value"])
        self.assertIn(f"color: {default_tokens['text_muted']};", detail_bundle["value_muted"])
        self.assertEqual(_calendar_default_accent({"accent": "#22c3ca"}), "#22c3ca")
        self.assertNotEqual(
            _theme_harmonized_color("not-a-color", 3, tokens={"accent": "#22c3ca"}), "#4da6ff"
        )

    def test_task_chip_helpers_follow_semantic_tokens(self):
        tokens = {
            "accent": "#22c3ca",
            "accent_soft": "rgba(34,195,202,40)",
            "accent_border": "rgba(34,195,202,110)",
            "bg_alt": "rgba(12,24,36,220)",
            "bg_item": "rgba(255,255,255,0.06)",
            "bg_item_hover": "rgba(255,255,255,0.12)",
            "bg_hover": "rgba(255,255,255,0.10)",
            "text_primary": "#eff4fa",
            "text_secondary": "#c3cfdd",
            "border": "rgba(255,255,255,0.14)",
            "border_strong": "rgba(255,255,255,0.26)",
            "divider": "rgba(255,255,255,0.08)",
        }
        shape = {
            "task_outer_radius": 11,
            "task_title_radius": 9,
            "context_menu_radius": 10,
            "context_menu_item_radius": 6,
        }

        title_style = _task_title_label_style(selected=True, watermark=False, tokens=tokens)
        chip_style = _task_chip_style_bundle("#ff6b6b", tokens=tokens, shape=shape)
        detail_style = _task_detail_card_style(tokens=tokens, shape=shape)
        menu_style = _task_context_menu_style(tokens=tokens, shape=shape)
        overlay_style = _selection_overlay_style(tokens=tokens)

        self.assertIn("color: #eff4fa;", title_style)
        self.assertIn("font-weight: bold;", title_style)
        self.assertEqual(chip_style["task_outer_radius"], 11)
        self.assertEqual(chip_style["task_title_radius"], 9)
        self.assertIn("rgba(", chip_style["selected_border"])
        self.assertIn("background-color: rgba(12,24,36,220);", detail_style)
        self.assertIn("border-bottom-left-radius: 9px;", detail_style)
        self.assertIn("border-radius: 10px;", menu_style)
        self.assertIn("border-radius: 6px;", menu_style)
        self.assertIn("background: rgba(34,195,202,40);", overlay_style)
        self.assertIn("border: 1px solid rgba(34,195,202,110);", overlay_style)
        self.assertEqual(
            _contrast_pen_color("#ffffff", tokens=tokens).name(QColor.NameFormat.HexRgb),
            _qcolor(tokens["bg_alt"]).name(QColor.NameFormat.HexRgb),
        )
        self.assertEqual(
            _contrast_pen_color("#111111", tokens=tokens).name(QColor.NameFormat.HexRgb),
            _qcolor(tokens["text_primary"]).name(QColor.NameFormat.HexRgb),
        )
        self.assertEqual(_qcolor(tokens["bg_alt"]).alpha(), 220)

        default_settings = _FakeSettings()
        default_tokens = get_ui_tokens(settings=default_settings)
        partial_chip = _task_chip_style_bundle(
            tokens={"accent": "#22c3ca"}, shape=shape, settings=default_settings
        )
        partial_checklist = _checklist_row_style_bundle(
            tokens={"accent": "#22c3ca"}, settings=default_settings
        )
        partial_hover = _hover_info_popup_stylesheet(
            tokens={"accent": "#22c3ca"}, shape=shape, settings=default_settings
        )
        self.assertEqual(partial_chip["accent"], "#22c3ca")
        self.assertEqual(partial_chip["base_bg"], default_tokens["bg_item"])
        self.assertIn(f"color: {default_tokens['text_primary']};", partial_checklist["label"])
        self.assertIn(f"background-color: {default_tokens['bg_alt']};", partial_hover)

    def test_dialog_editor_helpers_use_shared_token_contract(self):
        tokens = {
            "accent": "#22c3ca",
            "accent_soft_bg": "rgba(34,195,202,40)",
            "accent_soft_border": "rgba(34,195,202,110)",
            "surface_item": "rgba(12,24,36,220)",
            "surface_hover": "rgba(18,30,42,220)",
            "surface_alt": "rgba(16,28,40,220)",
            "text_primary": "#eff4fa",
            "text_secondary": "#c3cfdd",
            "text_muted": "#93a1b4",
            "text_faint": "#6d7a8c",
            "border": "rgba(255,255,255,0.16)",
            "border_soft": "rgba(255,255,255,0.10)",
            "tab_idle_bg": "rgba(16,28,40,220)",
            "tab_active_bg": "rgba(12,24,36,220)",
            "tab_text": "#93a1b4",
            "tab_text_hover": "#c3cfdd",
            "tab_text_active": "#22c3ca",
            "list_hover_bg": "rgba(34,195,202,24)",
            "list_selected_bg": "rgba(34,195,202,36)",
            "list_selected_border": "rgba(34,195,202,82)",
            "list_selected_text": "#eff4fa",
            "button_primary_bg": "rgba(34,195,202,44)",
            "button_primary_text": "#22c3ca",
            "button_primary_border": "rgba(34,195,202,140)",
            "button_primary_hover_bg": "rgba(34,195,202,72)",
            "button_primary_hover_text": "#eff4fa",
            "button_primary_hover_border": "#22c3ca",
            "button_secondary_bg": "rgba(20,30,40,200)",
            "button_secondary_text": "#93a1b4",
            "button_secondary_border": "rgba(255,255,255,0.12)",
            "button_secondary_hover_bg": "rgba(30,40,50,220)",
            "button_secondary_hover_text": "#eff4fa",
            "button_secondary_hover_border": "rgba(255,255,255,0.22)",
            "button_pressed_bg": "rgba(8,16,24,220)",
            "button_pressed_text": "#eff4fa",
            "button_pressed_border": "rgba(255,255,255,0.26)",
            "warning_hex": "#d39a2a",
            "warning_soft_bg": "rgba(211,154,42,40)",
            "danger_hex": "#d25a66",
            "danger_soft_bg": "rgba(210,90,102,40)",
        }
        metrics = {
            "tab_radius": 9,
            "group_radius": 11,
            "field_radius": 8,
            "tab_min_width": 96,
            "tab_padding_y": 7,
            "tab_padding_x": 18,
            "tab_gap": 4,
            "base_font_pt": 14,
            "button_height": 34,
            "button_radius": 10,
            "button_padding_y": 4,
            "button_padding_x": 16,
        }

        editor_qss = build_task_editor_stylesheet(tokens=tokens, metrics=metrics)
        quick_qss = build_editor_quick_button_style(tokens=tokens, metrics=metrics)
        accent_quick_qss = build_editor_quick_button_style(
            tokens=tokens, metrics=metrics, tone="accent"
        )
        danger_quick_qss = build_editor_quick_button_style(
            tokens=tokens, metrics=metrics, tone="danger"
        )
        hint_qss = build_editor_hint_style(tokens=tokens, metrics=metrics)
        counter_qss = build_editor_counter_style(tokens=tokens, level="danger")
        text_qss = build_editor_text_style(
            tokens=tokens, tone="accent", font_px=14, weight=600, margin_top=5
        )
        stack_qss = build_transparent_stack_stylesheet("RepeatModeStack")

        self.assertIn("QPushButton#CreateBtn", editor_qss)
        self.assertIn("QRadioButton#TaskDialogOptionCheck", editor_qss)
        self.assertIn("border-top-left-radius: 9px;", editor_qss)
        self.assertIn("border-radius: 11px;", editor_qss)
        self.assertIn("min-height: 24px;", quick_qss)
        self.assertIn("border-radius: 9px;", quick_qss)
        self.assertIn("color: #93a1b4;", quick_qss)
        self.assertIn("color: #22c3ca;", accent_quick_qss)
        self.assertIn("color: #d25a66;", danger_quick_qss)
        self.assertIn("background-color: rgba(34,195,202,40);", hint_qss)
        self.assertIn("border-radius: 7px;", hint_qss)
        self.assertIn("color: #d25a66;", counter_qss)
        self.assertIn("font-weight: bold;", counter_qss)
        self.assertIn("color: #22c3ca;", text_qss)
        self.assertIn("margin-top: 5px;", text_qss)
        self.assertEqual(
            stack_qss,
            "QStackedWidget#RepeatModeStack { background: transparent; border: none; }",
        )

    def test_routine_wizard_and_away_helpers_follow_dialog_tokens(self):
        tokens = {
            "accent": "#22c3ca",
            "accent_soft_bg": "rgba(34,195,202,40)",
            "accent_soft_border": "rgba(34,195,202,110)",
            "surface_alt": "rgba(16,28,40,220)",
            "surface_item": "rgba(12,24,36,220)",
            "surface_top": "rgba(8,18,28,220)",
            "text_primary": "#eff4fa",
            "text_secondary": "#c3cfdd",
            "text_muted": "#93a1b4",
            "text_faint": "#6d7a8c",
            "border": "rgba(255,255,255,0.16)",
            "border_soft": "rgba(255,255,255,0.10)",
            "check_indicator_bg": "rgba(8,18,28,220)",
            "check_indicator_border": "rgba(255,255,255,0.16)",
            "button_secondary_hover_bg": "rgba(28,40,52,220)",
            "success_hex": "#35b66a",
        }
        metrics = {
            "title_font_pt": 16,
            "base_font_pt": 14,
            "group_radius": 11,
            "field_radius": 8,
            "radio_indicator_size": 18,
            "radio_spacing": 10,
            "toolbutton_radius": 6,
        }

        wizard_qss = _build_routine_wizard_stylesheet(tokens=tokens, metrics=metrics)
        away_styles = _away_style_bundle(tokens=tokens, metrics=metrics)

        self.assertIn("QFrame.card", wizard_qss)
        self.assertIn("background-color: rgba(16,28,40,220);", wizard_qss)
        self.assertIn("border-radius: 11px;", wizard_qss)
        self.assertIn("QRadioButton::indicator:checked", wizard_qss)
        self.assertIn("background: #35b66a;", wizard_qss)

        self.assertIn("background: rgba(8,18,28,220);", away_styles["rich_editor"])
        self.assertIn("color: #22c3ca;", away_styles["html_editor"])
        self.assertIn("background: rgba(16,28,40,220);", away_styles["toolbar"])
        self.assertIn("border-radius: 8px;", away_styles["preview_box"])
        self.assertIn("color: #eff4fa;", away_styles["preview_label"])
        self.assertIn("background: rgba(34,195,202,40);", away_styles["tool_btn"])
        self.assertIn("background: rgba(255,255,255,0.10);", away_styles["separator"])

    def test_global_stylesheet_covers_calendar_drag_and_selection_states(self):
        qss = build_global_stylesheet(
            family="Pretendard, sans-serif",
            base_pt=11,
            theme_color="#22c3ca",
            text_theme="dark",
            panel_base_color="#1c1c1c",
        )

        self.assertIn('ClickableCell[selected_date="true"]', qss)
        self.assertIn('ClickableCell[drag_range_preview="true"]', qss)
        self.assertIn('ClickableCell[drag_mode="move"]', qss)
        self.assertIn('ClickableCell[drag_mode="copy"][drag_batch="true"]', qss)
        self.assertIn('ClickableCell[is_other_month="true"] QLabel#dayNumLabel', qss)

    def test_hover_popup_and_eod_helpers_use_semantic_tokens(self):
        tokens = {
            "accent": "#22c3ca",
            "accent_border": "rgba(34,195,202,110)",
            "bg_alt": "rgba(12,24,36,220)",
            "text_primary": "#eff4fa",
            "text_secondary": "#c3cfdd",
            "text_muted": "#93a1b4",
        }
        shape = {"tooltip_radius": 12}

        checklist_styles = _checklist_row_style_bundle(tokens=tokens)
        hover_qss = _hover_info_popup_stylesheet(tokens=tokens, shape=shape)
        eod_styles = _eod_report_style_bundle(tokens=tokens)

        self.assertIn("color: #eff4fa;", checklist_styles["label"])
        self.assertIn("background-color: rgba(12,24,36,220);", hover_qss)
        self.assertIn("border-radius: 12px;", hover_qss)
        self.assertIn("border: 1px solid rgba(34,195,202,110);", hover_qss)
        self.assertIn("color: #22c3ca;", eod_styles["title"])
        self.assertIn("color: #c3cfdd;", eod_styles["section"])
        self.assertIn("color: #93a1b4;", eod_styles["empty"])

    def test_gcal_and_checklist_dialog_helpers_accept_shared_tokens(self):
        tokens = {
            "accent": "#22c3ca",
            "accent_hover": "#3dd6dc",
            "accent_soft_bg": "rgba(34,195,202,40)",
            "accent_soft_border": "rgba(34,195,202,110)",
            "surface_bg": "rgba(8,18,28,220)",
            "surface_alt": "rgba(12,24,36,220)",
            "surface_item": "rgba(16,28,40,220)",
            "surface_hover": "rgba(24,36,48,220)",
            "surface_top": "rgba(6,16,26,220)",
            "text_primary": "#eff4fa",
            "text_secondary": "#c3cfdd",
            "text_muted": "#93a1b4",
            "text_faint": "#6d7a8c",
            "border": "rgba(255,255,255,0.16)",
            "border_soft": "rgba(255,255,255,0.10)",
            "button_base_bg": "rgba(18,30,42,220)",
            "button_base_text": "#c3cfdd",
            "button_base_border": "rgba(255,255,255,0.12)",
            "button_base_hover_bg": "rgba(24,36,48,220)",
            "button_base_hover_border": "rgba(34,195,202,110)",
            "button_base_hover_text": "#eff4fa",
            "button_primary_hover_bg": "rgba(34,195,202,72)",
            "button_primary_hover_border": "rgba(34,195,202,140)",
            "button_primary_hover_text": "#eff4fa",
            "warning_hex": "#d39a2a",
            "success_hex": "#35b66a",
            "success_soft_bg": "rgba(53,182,106,40)",
            "danger_hex": "#d25a66",
            "danger_soft_bg": "rgba(210,90,102,40)",
        }

        gcal_qss = _build_gcal_stylesheet(tokens=tokens)
        gcal_styles = _gcal_runtime_style_bundle(
            tokens=tokens,
            metrics={
                "base_font_pt": 14,
                "group_radius": 12,
                "field_radius": 9,
                "button_radius": 10,
                "button_height": 34,
            },
        )
        visible_qss = _gcal_visibility_button_style(True, tokens=tokens)
        hidden_qss = _gcal_visibility_button_style(False, tokens=tokens)
        checklist_qss = _checklist_dialog_style(tokens=tokens)
        checklist_shell_partial = _checklist_shell_stylesheet(tokens={"accent": "#22c3ca"})

        self.assertIn("background-color: rgba(8,18,28,220);", gcal_qss)
        self.assertIn("border: 1px solid rgba(34,195,202,110);", visible_qss)
        self.assertIn("color: #22c3ca;", visible_qss)
        self.assertIn("color: #93a1b4;", hidden_qss)
        self.assertIn("color: #35b66a;", gcal_styles["status_pill_connected"])
        self.assertIn("color: #d39a2a;", gcal_styles["notice_warning"])
        self.assertIn("background-color: rgba(16,28,40,220);", checklist_qss)
        self.assertIn("color: #22c3ca;", checklist_qss)
        self.assertIn("QWidget#sidebar", checklist_qss)
        self.assertIn("QGroupBox {", checklist_qss)
        dialog_defaults = get_dialog_theme_tokens()
        self.assertIn(
            f"background-color: {dialog_defaults['surface_alt']};", checklist_shell_partial
        )
        self.assertIn(
            f"border-right: 1px solid {dialog_defaults['border_soft']};", checklist_shell_partial
        )
        self.assertIn("color: #22c3ca;", checklist_shell_partial)
        self.assertNotIn("QPushButton#success_btn", CHECKLIST_DIALOG_STYLE)
        self.assertNotIn("QPushButton#ghost_btn", CHECKLIST_DIALOG_STYLE)
        self.assertNotIn("QPushButton#danger_btn", CHECKLIST_DIALOG_STYLE)
        self.assertEqual(CHECKLIST_DIALOG_STYLE.strip(), "")
        self.assertEqual(_GCAL_STYLE_TEMPLATE.strip(), "")

        checklist_editor_qss = _checklist_editor_stylesheet(
            tokens=tokens, metrics={"field_radius": 9, "group_radius": 12}
        )
        checklist_main_styles = _checklist_main_style_bundle(
            tokens=tokens,
            metrics={
                "base_font_pt": 14,
                "group_radius": 12,
                "field_radius": 9,
                "button_radius": 10,
                "button_height": 34,
            },
        )
        checklist_subdialog_styles = _checklist_subdialog_style_bundle(
            tokens=tokens,
            metrics={
                "base_font_pt": 14,
                "group_radius": 12,
                "field_radius": 9,
                "button_radius": 10,
                "button_height": 34,
            },
        )
        checklist_row_palette = _checklist_row_palette(tokens={"danger_hex": "#d25a66"})
        gcal_editor_qss = _gcal_editor_dialog_stylesheet(
            tokens=tokens, metrics={"field_radius": 9, "group_radius": 12}
        )
        self.assertIn("QDialog#TaskEditorDialog", checklist_editor_qss)
        self.assertIn("QLabel#TaskDialogFieldLabel", checklist_editor_qss)
        self.assertIn("border-radius: 12px;", checklist_editor_qss)
        self.assertIn("color: #22c3ca;", checklist_main_styles["section"])
        self.assertIn("background-color: rgba(12,24,36,220);", checklist_main_styles["empty"])
        self.assertIn("color: #22c3ca;", checklist_main_styles["button_primary"])
        self.assertIn("color: #d25a66;", checklist_main_styles["button_danger"])
        self.assertIn(
            "background-color: rgba(8,18,28,220);", checklist_main_styles["template_list"]
        )
        self.assertIn("QHeaderView::section", checklist_main_styles["items_table"])
        self.assertIn("color: #22c3ca;", checklist_subdialog_styles["button_primary"])
        self.assertIn("color: #93a1b4;", checklist_subdialog_styles["button_secondary"])
        self.assertEqual(
            checklist_row_palette["required"].name(QColor.NameFormat.HexRgb), "#d25a66"
        )
        self.assertIn("QLabel#TaskDialogFieldLabel", gcal_editor_qss)
        self.assertIn("QLineEdit#TaskTitleEdit", gcal_editor_qss)
        self.assertIn("color: #eff4fa;", gcal_styles["card_title"])
        self.assertIn("background-color: rgba(16,28,40,220);", gcal_styles["subtle_card"])
        self.assertIn("QCheckBox {", gcal_styles["check_toggle"])
        self.assertIn("background-color: #22c3ca;", gcal_styles["check_toggle"])
        self.assertIn("QLineEdit {", gcal_styles["input_line"])
        self.assertIn("QComboBox {", gcal_styles["input_combo"])
        self.assertIn("QAbstractItemView, QListView", gcal_styles["input_popup"])
        self.assertIn("QSpinBox {", gcal_styles["input_spin"])
        self.assertIn("QFrame#statusBar", gcal_styles["status_bar"])
        self.assertIn("QFrame#sidebar", gcal_styles["sidebar_shell"])
        self.assertIn("QWidget#contentArea", gcal_styles["content_area"])
        self.assertIn("QScrollBar:vertical", gcal_styles["scroll_shell"])
        self.assertIn("border-left: 3px solid transparent;", gcal_styles["nav_button"])
        self.assertIn("border-left: 3px solid #22c3ca;", gcal_styles["nav_button_active"])
        self.assertIn("border-radius: 9px;", gcal_styles["default_active"])
        self.assertIn("color: #d39a2a;", gcal_styles["default_active"])
        self.assertIn("border-radius: 9px;", gcal_styles["icon_button"])
        self.assertIn("color: #35b66a;", gcal_styles["button_success"])
        self.assertIn("color: #d25a66;", gcal_styles["button_danger"])
        issue_styles = _gcal_issue_style_bundle(
            tokens=tokens,
            metrics={
                "base_font_pt": 14,
                "group_radius": 12,
                "list_radius": 9,
                "button_radius": 10,
                "button_height": 34,
            },
        )
        focus_styles = _focus_log_style_bundle(
            tokens=tokens,
            metrics={
                "base_font_pt": 14,
                "list_radius": 9,
                "button_radius": 10,
                "button_height": 34,
            },
        )
        self.assertIn("QFrame#GuidanceBox", issue_styles["guidance_box"])
        self.assertIn("QFrame#DiffPanel", issue_styles["diff_panel"])
        self.assertIn("QTableWidget {", issue_styles["table"])
        self.assertIn("color: #22c3ca;", issue_styles["button_accent"])
        self.assertIn("color: #d39a2a;", issue_styles["button_warning"])
        self.assertEqual(issue_styles["status_retry"], "#22c3ca")
        self.assertIn("QTableWidget {", focus_styles["table"])
        self.assertIn("color: #22c3ca;", focus_styles["header"])
        self.assertIn("color: #22c3ca;", focus_styles["button_primary"])
        label_styles = _label_settings_style_bundle(
            tokens=tokens,
            metrics={
                "base_font_pt": 14,
                "field_radius": 9,
                "button_radius": 10,
                "button_height": 34,
            },
        )
        emoji_picker_qss = _emoji_picker_stylesheet(tokens=tokens, metrics={"field_radius": 9})
        token_editor_styles = _dialog_token_editor_style_bundle(
            tokens=tokens,
            metrics={
                "base_font_pt": 14,
                "field_radius": 9,
                "group_radius": 12,
                "button_radius": 10,
                "button_height": 34,
            },
        )
        self.assertIn("color: #93a1b4;", label_styles["hint"])
        self.assertIn("QToolButton {", label_styles["picker_button"])
        self.assertIn("color: #22c3ca;", label_styles["button_accent"])
        self.assertIn("QDialog {", emoji_picker_qss)
        self.assertIn("background-color: rgba(8,18,28,220);", emoji_picker_qss)
        self.assertIn("QFrame#presetBar", token_editor_styles["preset_bar"])
        self.assertIn("QFrame#tokenPreviewWrap", token_editor_styles["preview_wrap"])
        self.assertIn("border: 1px solid #d25a66;", token_editor_styles["invalid_edit"])

    def test_datecard_theme_bundle_uses_shared_snapshot_defaults(self):
        settings = _FakeSettings()
        settings.setValue("theme_color", "#22c3ca")
        settings.setValue("text_theme", "dark")
        settings.setValue("panel_base_color", "#101820")

        bundle = _datecard_theme_bundle(settings=settings)
        ui_tokens = get_ui_tokens(settings=settings)
        today_style = _week_strip_label_style(bundle["accent"], bold=True)
        weekend_style = _week_strip_label_style(bundle["sunday"])

        self.assertEqual(bundle["accent"].name(QColor.NameFormat.HexRgb), "#22c3ca")
        self.assertEqual(
            bundle["text"].name(QColor.NameFormat.HexRgb),
            QColor(ui_tokens["text_primary"]).name(QColor.NameFormat.HexRgb),
        )
        self.assertEqual(bundle["bg_rgba"].lower(), "#d6101820")
        self.assertEqual(bundle["border_rgba"].lower(), "#4822c3ca")
        self.assertEqual(bundle["text_rgba"].lower(), "#fcf4f7fb")
        self.assertIn("color:#22c3ca;", today_style)
        self.assertIn("font-weight:bold;", today_style)
        self.assertIn(f"color:{bundle['sunday'].name(QColor.NameFormat.HexRgb)};", weekend_style)
        self.assertEqual(
            _datecard_contrast_text("#ffffff", "#fcfdfe", "#101418").name(QColor.NameFormat.HexRgb),
            "#101418",
        )
        self.assertEqual(
            _datecard_contrast_text("#101418", "#fcfdfe", "#101418").name(QColor.NameFormat.HexRgb),
            "#fcfdfe",
        )
        self.assertEqual(
            _datecard_qcolor("rgba(12,24,36,220)", "#fcfdfe").name(QColor.NameFormat.HexRgb),
            "#0c1824",
        )
        self.assertEqual(_datecard_qcolor("rgba(12,24,36,220)", "#fcfdfe").alpha(), 220)


if __name__ == "__main__":
    unittest.main()
