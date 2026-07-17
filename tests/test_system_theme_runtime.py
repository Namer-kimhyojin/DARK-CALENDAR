# -*- coding: utf-8 -*-
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject, Qt, QTimer
from PyQt6.QtWidgets import QApplication, QDialog

from calendar_app.presentation.dialogs.panel_color_picker_dialog import (
    _POINT_COLORS,
    PanelColorPickerDialog,
)
from calendar_app.presentation.main_window.theme_actions import ThemeActionsMixin
from calendar_app.presentation.main_window.window_ui_actions import MainWindowUiActionsMixin
from calendar_app.shared.system_theme import set_runtime_system_text_theme
from calendar_app.shared.theme_settings import (
    get_text_theme_and_panel_base,
    get_theme_color,
)
from calendar_app.shared.theme_snapshot import build_theme_snapshot


class _FakeSettings:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.set_calls = []

    def value(self, key, default=None, type=None):
        value = self.values.get(key, default)
        return type(value) if type is not None and value is not None else value

    def setValue(self, key, value):
        self.set_calls.append((key, value))
        self.values[key] = value

    def contains(self, key):
        return key in self.values

    def allKeys(self):
        return list(self.values)

    def remove(self, key):
        self.values.pop(key, None)


def _auto_family_settings(*, accent_source="family"):
    return _FakeSettings(
        {
            "text_theme": "auto",
            "panel_base_color": "#0d1b2e",
            "theme_color": "#4da6ff",
            "appearance_style_family": "ocean",
            "appearance_accent_source": accent_source,
            "appearance_family_dark_base": "#0d1b2e",
            "appearance_family_dark_accent": "#4da6ff",
            "appearance_family_light_base": "#e7f5ff",
            "appearance_family_light_accent": "#1971c2",
        }
    )


class _SystemThemeHost(ThemeActionsMixin, QObject):
    def __init__(self, text_theme="auto"):
        QObject.__init__(self)
        self.settings = _FakeSettings({"text_theme": text_theme})
        self._last_system_text_theme = "dark"
        self._last_applied_system_text_theme = "dark"
        self._pending_system_text_theme = None
        self._system_theme_apply_count = 0
        self._system_theme_refresh_timer = QTimer(self)
        self._system_theme_refresh_timer.setSingleShot(True)
        self._system_theme_refresh_timer.setInterval(50)
        self._system_theme_refresh_timer.timeout.connect(self._apply_pending_system_theme_change)
        self.apply_calls = []
        self.dialog_notifications = []

    def apply_theme_settings(self, *, persist_opacity=True):
        self.apply_calls.append(persist_opacity)

    def _notify_open_appearance_dialogs(self, resolved_theme: str):
        self.dialog_notifications.append(resolved_theme)


class _AppearanceSaveHost(MainWindowUiActionsMixin):
    def __init__(self, settings):
        self.settings = settings
        self.theme_apply_count = 0

    def apply_theme_settings(self):
        self.theme_apply_count += 1


class SystemThemeRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def tearDown(self):
        set_runtime_system_text_theme(None)

    def test_auto_theme_resolves_family_variant_without_writing_settings(self):
        settings = _auto_family_settings()
        set_runtime_system_text_theme("light")

        snapshot = build_theme_snapshot(settings, opacity_factor=1.0)

        self.assertEqual(snapshot.text_theme, "light")
        self.assertEqual(snapshot.panel_base_color, "#e7f5ff")
        self.assertEqual(snapshot.theme_color, "#1971c2")
        self.assertEqual(get_text_theme_and_panel_base(settings), ("light", "#e7f5ff"))
        self.assertEqual(get_theme_color(settings), "#1971c2")
        self.assertEqual(settings.set_calls, [])

    def test_auto_theme_preserves_custom_accent_and_explicit_mode_ignores_family(self):
        settings = _auto_family_settings(accent_source="custom")
        settings.values["theme_color"] = "#aa3377"
        set_runtime_system_text_theme("light")

        auto_snapshot = build_theme_snapshot(settings, opacity_factor=1.0)
        settings.values["text_theme"] = "dark"
        explicit_snapshot = build_theme_snapshot(settings, opacity_factor=1.0)

        self.assertEqual(auto_snapshot.panel_base_color, "#e7f5ff")
        self.assertEqual(auto_snapshot.theme_color, "#aa3377")
        self.assertEqual(explicit_snapshot.text_theme, "dark")
        self.assertEqual(explicit_snapshot.panel_base_color, "#0d1b2e")
        self.assertEqual(explicit_snapshot.theme_color, "#aa3377")

    def test_system_events_are_coalesced_and_do_not_persist_settings(self):
        host = _SystemThemeHost()

        host._on_system_color_scheme_changed(Qt.ColorScheme.Light)
        host._on_system_color_scheme_changed(Qt.ColorScheme.Light)
        self.assertTrue(host._system_theme_refresh_timer.isActive())
        self.assertEqual(host.apply_calls, [])

        host._system_theme_refresh_timer.stop()
        host._apply_pending_system_theme_change()
        host._on_system_color_scheme_changed(Qt.ColorScheme.Light)

        self.assertEqual(host.apply_calls, [False])
        self.assertEqual(host._system_theme_apply_count, 1)
        self.assertEqual(host.dialog_notifications, ["light", "light", "light"])
        self.assertEqual(host.settings.set_calls, [])
        self.assertFalse(host._system_theme_refresh_timer.isActive())

    def test_explicit_mode_notifies_open_drafts_but_does_not_restyle_app(self):
        host = _SystemThemeHost(text_theme="dark")

        host._on_system_color_scheme_changed(Qt.ColorScheme.Light)

        self.assertEqual(host.dialog_notifications, ["light"])
        self.assertEqual(host.apply_calls, [])
        self.assertFalse(host._system_theme_refresh_timer.isActive())

    def test_open_auto_dialog_switches_family_without_creating_user_change(self):
        dialog = PanelColorPickerDialog(
            current_base="#0d1b2e",
            current_theme="#4da6ff",
            current_text_theme="auto",
            current_style_family="ocean",
            current_accent_source="family",
        )
        self.addCleanup(dialog.close)

        dialog.handle_system_theme_change("light")

        self.assertEqual(dialog.selected_base_hex(), "#e7f5ff")
        self.assertEqual(dialog.selected_point_hex(), "#1971c2")
        self.assertEqual(dialog.selected_text_theme(), "auto")
        self.assertEqual(dialog._appearance_change_categories(), [])
        self.assertFalse(dialog._apply_btn.isEnabled())

    def test_open_auto_dialog_preserves_custom_accent_and_text_draft(self):
        dialog = PanelColorPickerDialog(
            current_base="#0d1b2e",
            current_theme="#4da6ff",
            current_text_theme="auto",
            current_style_family="ocean",
            current_accent_source="family",
        )
        self.addCleanup(dialog.close)
        point_index = next(
            index
            for index, (_, _, code) in enumerate(_POINT_COLORS)
            if code.lower() != dialog.selected_point_hex().lower()
        )
        dialog._select_point_color(point_index)
        dialog._row_primary.set_value("#abcdef")
        point_draft = dialog.selected_point_hex()
        text_draft = dialog._row_primary.hex_value()
        changed_before = set(dialog._appearance_change_categories())

        dialog.handle_system_theme_change("light")

        self.assertEqual(dialog.selected_base_hex(), "#e7f5ff")
        self.assertEqual(dialog.selected_point_hex(), point_draft)
        self.assertEqual(dialog._row_primary.hex_value(), text_draft)
        self.assertEqual(set(dialog._appearance_change_categories()), changed_before)

    def test_accepted_dialog_persists_family_contract_for_future_system_events(self):
        settings = _auto_family_settings()
        settings.values.update(
            {
                "last_opacity": 200,
                "last_opacity_unit": "byte",
                "last_border_opacity": 80,
                "last_text_opacity": 255,
            }
        )
        host = _AppearanceSaveHost(settings)
        set_runtime_system_text_theme("light")

        class _AcceptedDialog:
            DialogCode = QDialog.DialogCode
            received_kwargs = None

            def __init__(self, **kwargs):
                type(self).received_kwargs = kwargs

            def exec(self):
                return self.DialogCode.Accepted

            def selected_base_hex(self):
                return "#e7f5ff"

            def selected_opacity(self):
                return 200

            def selected_border_opacity(self):
                return 80

            def selected_text_opacity(self):
                return 255

            def selected_style_family(self):
                return "ocean"

            def selected_accent_source(self):
                return "family"

            def selected_style_family_variants(self):
                return {
                    "dark_base": "#0d1b2e",
                    "dark_accent": "#4da6ff",
                    "light_base": "#e7f5ff",
                    "light_accent": "#1971c2",
                }

            def point_color_changed(self):
                return False

            def selected_point_hex(self):
                return "#1971c2"

            def selected_text_theme(self):
                return "auto"

            def text_colors_changed(self):
                return False

            def font_changed(self):
                return False

            def selected_dialog_color_overrides(self):
                return {}

            def selected_dialog_metric_overrides(self):
                return {}

        with patch(
            "calendar_app.presentation.dialogs.panel_color_picker_dialog.PanelColorPickerDialog",
            _AcceptedDialog,
        ):
            host.open_panel_background_color_dialog()

        self.assertEqual(_AcceptedDialog.received_kwargs["current_base"], "#e7f5ff")
        self.assertEqual(_AcceptedDialog.received_kwargs["current_theme"], "#1971c2")
        self.assertEqual(settings.value("appearance_style_family"), "ocean")
        self.assertEqual(settings.value("appearance_accent_source"), "family")
        self.assertEqual(settings.value("appearance_family_dark_base"), "#0d1b2e")
        self.assertEqual(settings.value("appearance_family_light_accent"), "#1971c2")
        self.assertEqual(host.theme_apply_count, 1)


if __name__ == "__main__":
    unittest.main()
