# -*- coding: utf-8 -*-
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings, QUrl
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QApplication, QWidget

from calendar_app.presentation.widgets.launcher_deck_dialog import (
    KeycapAppearanceDialog,
    KeycapInteractionDialog,
    LauncherDeckEditorDialog,
)
from calendar_app.presentation.widgets.launcher_deck_model import (
    DECK_TEMPLATES,
    INTERACTION_DEFAULTS,
    apply_pattern,
    clear_keycap_interaction,
    clear_keycap_overrides,
    deck_from_json,
    deck_to_json,
    keycap_style,
    preserve_deck_visuals,
    reflow_deck,
    template_deck,
)
from calendar_app.presentation.widgets.overlay_launcher_deck import (
    LauncherKeycapButton,
    OverlayLauncherDeckWidget,
)


def _occupied_cells(deck):
    cells = []
    for key in deck["keys"]:
        cells.extend(
            (row, column)
            for row in range(key["row"], key["row"] + key["height"])
            for column in range(key["column"], key["column"] + key["width"])
        )
    return cells


class _Owner(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("codex_test", "launcher_deck")
        self.settings.clear()
        self.calls = []
        self.overlay_manager = type("_Manager", (), {"_open_manager_dialog": lambda inner: None})()

    def open_task_dialog(self):
        self.calls.append("new_task")

    def jump_to_today(self):
        self.calls.append("today")

    def sync_google_calendar(self):
        self.calls.append("sync_google")

    def show_command_palette(self):
        self.calls.append("command_palette")


class LauncherDeckModelTests(unittest.TestCase):
    def test_six_templates_have_valid_mixed_key_arrays(self):
        self.assertEqual(len(DECK_TEMPLATES), 6)
        mixed_templates = 0
        for template_id, *_rest in DECK_TEMPLATES:
            deck = reflow_deck(template_deck(template_id))
            cells = _occupied_cells(deck)
            self.assertEqual(len(cells), len(set(cells)), template_id)
            if any(key["width"] > 1 or key["height"] > 1 for key in deck["keys"]):
                mixed_templates += 1
        self.assertGreaterEqual(mixed_templates, 4)

    def test_templates_are_graphic_first_by_default(self):
        for template_id, *_rest in DECK_TEMPLATES:
            deck = template_deck(template_id)
            self.assertEqual(deck["version"], 3)
            self.assertTrue(deck["keys"], template_id)
            for key in deck["keys"]:
                self.assertNotEqual(key["asset_id"], "none", template_id)
                self.assertNotIn(key["icon"], {"auto", "none"}, template_id)
                self.assertGreaterEqual(key["asset_opacity"], 70, template_id)
                self.assertGreaterEqual(key["asset_scale"], 132, template_id)
                self.assertLessEqual(key["font_scale"], 82, template_id)

    def test_json_round_trip_preserves_korean_labels_and_sizes(self):
        deck = template_deck("mixed_4x3")
        deck["keys"][0]["label"] = "한글 키"
        restored = deck_from_json(deck_to_json(deck))
        self.assertEqual(restored["keys"][0]["label"], "한글 키")
        self.assertEqual(restored["keys"][0]["width"], 2)

    def test_mosaic_and_icon_pack_round_trip(self):
        deck = template_deck("regular_3x3")
        deck.update(
            {
                "icon_pack": "neon_cyan",
                "mosaic_enabled": True,
                "mosaic_path": "C:/art/deck.gif",
                "mosaic_opacity": 84,
                "mosaic_show_labels": False,
            }
        )
        restored = deck_from_json(deck_to_json(deck))
        self.assertEqual(restored["icon_pack"], "neon_cyan")
        self.assertTrue(restored["mosaic_enabled"])
        self.assertEqual(restored["mosaic_path"], "C:/art/deck.gif")
        self.assertEqual(restored["mosaic_opacity"], 84)
        self.assertFalse(restored["mosaic_show_labels"])

    def test_template_change_preserves_deck_wide_visual_system(self):
        source = template_deck("regular_3x3")
        source.update(
            {
                "icon_pack": "violet_glow",
                "mosaic_enabled": True,
                "mosaic_path": "C:/art/panorama.png",
                "mosaic_opacity": 88,
                "mosaic_show_labels": False,
            }
        )
        switched = preserve_deck_visuals(source, template_deck("command_strip"))
        self.assertEqual(switched["columns"], 8)
        self.assertEqual(switched["rows"], 1)
        self.assertEqual(switched["icon_pack"], "violet_glow")
        self.assertTrue(switched["mosaic_enabled"])
        self.assertEqual(switched["mosaic_path"], "C:/art/panorama.png")
        self.assertEqual(switched["mosaic_opacity"], 88)
        self.assertFalse(switched["mosaic_show_labels"])

    def test_pattern_can_target_only_selected_keys(self):
        deck = template_deck("mixed_4x3")
        selected_id = deck["keys"][0]["id"]
        before = {key["id"]: key["style"] for key in deck["keys"]}
        changed = apply_pattern(deck, "function_groups", {selected_id})
        after = {key["id"]: key["style"] for key in changed["keys"]}
        self.assertEqual(after[selected_id], "air_glass")
        for key_id in before.keys() - {selected_id}:
            self.assertEqual(after[key_id], before[key_id])

    def test_unknown_style_falls_back_to_air_glass(self):
        self.assertEqual(keycap_style("missing").style_id, "air_glass")

    def test_custom_appearance_round_trip_is_clamped_and_clearable(self):
        deck = template_deck("mixed_4x3")
        key = deck["keys"][0]
        key.update(
            {
                "custom_top": "#112233ff",
                "custom_bottom": "#223344ff",
                "custom_border": "#aabbccff",
                "custom_text": "#ffffffff",
                "depth_override": 99,
                "radius_override": 99,
                "font_scale": 999,
                "icon": "star",
                "label_layout": "icon_left",
                "asset_id": "spark",
                "asset_opacity": 1,
                "asset_scale": 999,
            }
        )
        restored = deck_from_json(deck_to_json(deck))["keys"][0]
        self.assertEqual(restored["custom_top"], "#112233ff")
        self.assertEqual(restored["depth_override"], 14)
        self.assertEqual(restored["radius_override"], 28)
        self.assertEqual(restored["font_scale"], 160)
        self.assertEqual(restored["asset_opacity"], 10)
        self.assertEqual(restored["asset_scale"], 160)
        clear_keycap_overrides(restored)
        self.assertEqual(restored["custom_top"], "")
        self.assertEqual(restored["asset_id"], "none")

    def test_interaction_settings_round_trip_are_validated_and_clearable(self):
        deck = template_deck("mixed_4x3")
        key = deck["keys"][0]
        key.update(
            {
                "enabled": False,
                "interaction_mode": "toggle",
                "activation_trigger": "long",
                "long_press_ms": 9999,
                "press_effect": "ripple",
                "hover_effect": "pulse",
                "active_effect": "breathe",
                "success_effect": "flash",
                "error_effect": "shake",
                "animation_speed": 999,
                "feedback_duration_ms": 9999,
                "sound_profile": "custom",
                "sound_path": "C:/sound.wav",
                "sound_volume": 999,
                "asset_playback": "active",
                "reduce_motion": True,
                "active": True,
            }
        )
        restored = deck_from_json(deck_to_json(deck))["keys"][0]
        self.assertFalse(restored["enabled"])
        self.assertEqual(restored["interaction_mode"], "toggle")
        self.assertEqual(restored["activation_trigger"], "long")
        self.assertEqual(restored["long_press_ms"], 2000)
        self.assertEqual(restored["animation_speed"], 200)
        self.assertEqual(restored["feedback_duration_ms"], 3000)
        self.assertEqual(restored["sound_volume"], 100)
        self.assertTrue(restored["active"])
        clear_keycap_interaction(restored)
        self.assertEqual(
            {field: restored[field] for field in INTERACTION_DEFAULTS},
            INTERACTION_DEFAULTS,
        )


class LauncherDeckWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.owner = _Owner()
        self.widget = OverlayLauncherDeckWidget(self.owner)
        self.widget.apply_initial_settings()
        self.widget.show()
        self.__class__._app.processEvents()

    def tearDown(self):
        self.widget.close()
        self.owner.settings.clear()
        self.owner.close()
        super().tearDown()

    def test_default_widget_renders_mixed_size_keycaps(self):
        deck = self.widget._deck()
        self.assertGreaterEqual(len(deck["keys"]), 6)
        self.assertTrue(any(key["width"] > 1 for key in deck["keys"]))
        self.assertEqual(len(self.widget._key_buttons), len(deck["keys"]))
        self.assertFalse(self.widget.grab().isNull())

    def test_switching_array_clears_manual_size_and_refits_content(self):
        self.widget._set("fixed_w", 1240)
        self.widget._set("fixed_h", 720)
        self.widget.resize(1240, 720)

        self.widget._apply_template("command_strip")
        self.__class__._app.processEvents()

        self.assertIsNone(self.widget._normalized_fixed_dimension("fixed_w"))
        self.assertIsNone(self.widget._normalized_fixed_dimension("fixed_h"))
        self.assertLess(self.widget.width(), 900)
        self.assertLess(self.widget.height(), 180)

    def test_internal_command_uses_whitelist(self):
        self.assertTrue(
            self.widget._execute_key(
                {"action_type": "internal", "target": "new_task", "label": "일정"}
            )
        )
        self.assertEqual(self.owner.calls, ["new_task"])
        self.assertFalse(
            self.widget._execute_key(
                {"action_type": "internal", "target": "arbitrary", "label": "위험"}
            )
        )

    def test_file_open_blocks_scripts_and_uses_desktop_service_for_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            safe_file = Path(tmpdir) / "notes.txt"
            safe_file.write_text("ok", encoding="utf-8", errors="strict")
            script = Path(tmpdir) / "run.cmd"
            script.write_text("echo no", encoding="utf-8", errors="strict")
            with (
                patch.object(QUrl, "fromLocalFile", wraps=QUrl.fromLocalFile),
                patch(
                    "calendar_app.presentation.widgets.overlay_launcher_deck.QDesktopServices.openUrl",
                    return_value=True,
                ) as open_url,
            ):
                self.assertTrue(
                    self.widget._execute_key(
                        {"action_type": "open", "target": str(safe_file), "label": "메모"}
                    )
                )
                self.assertEqual(open_url.call_count, 1)
                self.assertFalse(
                    self.widget._execute_key(
                        {"action_type": "open", "target": str(script), "label": "스크립트"}
                    )
                )

    def test_hotkey_action_uses_validated_windows_sender(self):
        with patch(
            "calendar_app.presentation.widgets.overlay_launcher_deck.send_hotkey",
            return_value=True,
        ) as sender:
            self.assertTrue(
                self.widget._execute_key(
                    {"action_type": "hotkey", "target": "Ctrl+Shift+K", "label": "단축키"}
                )
            )
            sender.assert_called_once_with("Ctrl+Shift+K")

    def test_editor_batch_style_and_size_are_draft_only(self):
        original = self.widget._deck()
        dialog = LauncherDeckEditorDialog(original, self.widget)
        first_two = {key["id"] for key in dialog._deck["keys"][:2]}
        dialog._deck["keys"][0]["custom_top"] = "#123456ff"
        dialog._deck["keys"][0]["asset_id"] = "spark"
        dialog._selected_ids = first_two
        dialog._style_combo.setCurrentIndex(dialog._style_combo.findData("soft_clay"))
        dialog._apply_style()
        dialog._size_combo.setCurrentIndex(1)
        dialog._apply_size()
        draft = dialog.result_deck()
        self.assertTrue(
            all(key["style"] == "soft_clay" for key in draft["keys"] if key["id"] in first_two)
        )
        self.assertTrue(
            all(not key["custom_top"] for key in draft["keys"] if key["id"] in first_two)
        )
        self.assertTrue(
            all(key["asset_id"] == "none" for key in draft["keys"] if key["id"] in first_two)
        )
        self.assertEqual(self.widget._deck(), original)
        dialog.close()

    def test_editor_records_portable_hotkey_action(self):
        dialog = LauncherDeckEditorDialog(self.widget._deck(), self.widget)
        key = dialog._deck["keys"][0]
        dialog._selected_ids = {key["id"]}
        dialog._sync_selection_controls()
        dialog._action_combo.setCurrentIndex(dialog._action_combo.findData("hotkey"))
        dialog._hotkey_edit.setKeySequence(QKeySequence("Ctrl+Shift+K"))
        dialog._commit_key_fields()
        self.assertEqual(key["action_type"], "hotkey")
        self.assertEqual(key["target"], "Ctrl+Shift+K")
        self.assertFalse(dialog._hotkey_edit.isHidden())
        dialog.close()

    def test_keycap_designer_exposes_live_custom_controls(self):
        dialog = KeycapAppearanceDialog(self.widget._deck()["keys"][0], self.widget)
        dialog._depth_spin.setValue(0)
        dialog._radius_spin.setValue(24)
        dialog._font_scale_spin.setValue(145)
        dialog._icon_combo.setCurrentIndex(dialog._icon_combo.findData("star"))
        dialog._layout_combo.setCurrentIndex(dialog._layout_combo.findData("icon_left"))
        dialog._asset_combo.setCurrentIndex(dialog._asset_combo.findData("spark"))
        dialog._asset_opacity_spin.setValue(65)
        dialog._asset_scale_spin.setValue(130)
        appearance = dialog.result_appearance()
        self.assertEqual(appearance["depth_override"], 0)
        self.assertEqual(appearance["radius_override"], 24)
        self.assertEqual(appearance["font_scale"], 145)
        self.assertEqual(appearance["icon"], "star")
        self.assertEqual(appearance["label_layout"], "icon_left")
        self.assertEqual(appearance["asset_id"], "spark")
        self.assertEqual(appearance["asset_opacity"], 65)
        self.assertFalse(dialog._preview.grab().isNull())
        dialog.close()

    def test_interaction_studio_exposes_profiles_states_and_media(self):
        dialog = KeycapInteractionDialog(self.widget._deck()["keys"][0], self.widget)
        dialog._mode_combo.setCurrentIndex(dialog._mode_combo.findData("toggle"))
        dialog._trigger_combo.setCurrentIndex(dialog._trigger_combo.findData("long"))
        dialog._press_effect_combo.setCurrentIndex(dialog._press_effect_combo.findData("ripple"))
        dialog._asset_playback_combo.setCurrentIndex(
            dialog._asset_playback_combo.findData("active")
        )
        dialog._sound_combo.setCurrentIndex(dialog._sound_combo.findData("system"))
        dialog._sound_event_combo.setCurrentIndex(dialog._sound_event_combo.findData("result"))
        dialog._volume_slider.setValue(42)
        result = dialog.result_interaction()
        self.assertEqual(result["interaction_mode"], "toggle")
        self.assertEqual(result["activation_trigger"], "long")
        self.assertEqual(result["press_effect"], "ripple")
        self.assertEqual(result["asset_playback"], "active")
        self.assertEqual(result["sound_profile"], "system")
        self.assertEqual(result["sound_event"], "result")
        self.assertEqual(result["sound_volume"], 42)
        dialog._simulate("disabled")
        self.assertFalse(dialog._preview.key_data["enabled"])
        self.assertFalse(dialog._preview.grab().isNull())
        dialog.close()

    def test_toggle_key_persists_state_and_disabled_key_does_not_execute(self):
        key = self.widget._deck()["keys"][0]
        key["interaction_mode"] = "toggle"
        key["active"] = False
        calls = []
        states = []
        button = LauncherKeycapButton(
            key,
            lambda _key: calls.append("run") or True,
            self.widget,
            state_callback=lambda changed: states.append(bool(changed["active"])),
        )
        button._execute()
        self.assertEqual(calls, ["run"])
        self.assertEqual(states, [True])
        key["enabled"] = False
        button._execute()
        self.assertEqual(calls, ["run"])
        button.close()


if __name__ == "__main__":
    unittest.main()
