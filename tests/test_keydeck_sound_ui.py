# -*- coding: utf-8 -*-
"""Sound settings remain discoverable, draft-only, and independent of key overrides."""

from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.keydeck import model as m
from calendar_app.presentation.widgets.keydeck.studio import KeyDeckStudioDialog
from calendar_app.presentation.widgets.overlay_launcher_deck import OverlayLauncherDeckWidget
from calendar_app.shared.app_lifecycle import EXITING_PROPERTY

_STUDIO = "calendar_app.presentation.widgets.keydeck.studio"


class KeyDeckSoundUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings = QSettings(
            str(Path(self.directory.name) / "sound-ui.ini"), QSettings.Format.IniFormat
        )
        for module in (
            "calendar_app.infrastructure.i18n",
            "calendar_app.presentation.dialogs.dialog_styles",
            "calendar_app.shared.theme_snapshot",
        ):
            patcher = patch(f"{module}.QSettings", return_value=self.settings)
            patcher.start()
            self.addCleanup(patcher.stop)
        sound_patcher = patch(
            "calendar_app.presentation.widgets.keydeck.canvas.sound_bank", return_value=Mock()
        )
        sound_patcher.start()
        self.addCleanup(sound_patcher.stop)
        self.app.setProperty(EXITING_PROPERTY, False)
        self.original = m.build_template_deck("macro_3x3")
        self.dialog = KeyDeckStudioDialog(self.original)
        self.dialog.show()
        self.app.processEvents()
        self.addCleanup(self._close_dialog)

    def _close_dialog(self):
        self.dialog.force_close()
        self.dialog.deleteLater()
        self.app.processEvents()

    def _choose(self, inspector, sound_id):
        index = inspector.sound_combo.findData(sound_id)
        self.assertGreaterEqual(index, 0)
        inspector.sound_combo.setCurrentIndex(index)
        inspector.sound_combo.activated.emit(index)

    def test_header_opens_global_settings_from_a_selected_key(self):
        first = self.dialog.current_keys()[0]
        self.dialog.canvas.select([first["id"]])
        self.dialog.sound_settings_button.click()
        self.assertEqual(self.dialog.canvas.selection, [])
        self.assertIs(self.dialog.inspector_stack.currentWidget(), self.dialog.deck_inspector)
        self.assertEqual(self.dialog.deck_inspector.scroll.verticalScrollBar().value(), 0)
        self.assertFalse(self.dialog._dirty)

    def test_individual_entry_opens_the_keys_sound_tab_on_another_page(self):
        page = m.new_page("Second")
        page["keys"].append(m.make_key("Second key"))
        self.dialog.deck["pages"].append(page)
        key_id = page["keys"][0]["id"]
        self.dialog.show_sound_settings(key_id)
        self.assertEqual(self.dialog.deck["page"], 1)
        self.assertEqual(self.dialog.canvas.selection, [key_id])
        self.assertIs(self.dialog.inspector_stack.currentWidget(), self.dialog.key_inspector)
        self.assertEqual(self.dialog.key_inspector.tabs.currentIndex(), 3)

    def test_global_controls_edit_only_the_draft_and_preserve_explicit_key_sounds(self):
        original_copy = deepcopy(self.original)
        key = self.dialog.current_keys()[0]
        key["sound"] = "none"
        choice = next(
            option[0]
            for option in m.DECK_SOUND_CHOICES
            if option[0] not in {"auto", "custom", "none"}
        )
        self._choose(self.dialog.deck_inspector, choice)
        self.dialog.deck_inspector.volume_slider.slider.setValue(43)
        self.dialog.deck_inspector.sound_check.setChecked(False)
        self.assertEqual(self.dialog.result_deck()["sound"], choice)
        self.assertEqual(self.dialog.result_deck()["sound_volume"], 43)
        self.assertFalse(self.dialog.result_deck()["sound_enabled"])
        self.assertEqual(key["sound"], "none")
        self.assertEqual(self.original, original_copy)
        self.dialog.undo()
        self.assertTrue(self.dialog.deck["sound_enabled"])

    def test_cancelled_custom_sound_returns_combo_to_saved_choice(self):
        with patch(f"{_STUDIO}.QFileDialog.getOpenFileName", return_value=("", "")):
            self._choose(self.dialog.deck_inspector, "custom")
        self.assertEqual(self.dialog.deck_inspector.sound_combo.currentData(), "auto")
        self.assertFalse(self.dialog._dirty)
        key = self.dialog.current_keys()[0]
        self.dialog.canvas.select([key["id"]])
        with patch(f"{_STUDIO}.QFileDialog.getOpenFileName", return_value=("", "")):
            self._choose(self.dialog.key_inspector, "custom")
        self.assertEqual(self.dialog.key_inspector.sound_combo.currentData(), "auto")
        self.assertFalse(self.dialog._dirty)

    def test_custom_global_file_does_not_overwrite_key_custom_file(self):
        key = self.dialog.current_keys()[0]
        key["sound"], key["sound_path"] = "custom", "individual.wav"
        imported = str(Path(self.directory.name) / "global.wav")
        with (
            patch(f"{_STUDIO}.QFileDialog.getOpenFileName", return_value=("source.wav", "")),
            patch(f"{_STUDIO}.import_launcher_asset", return_value=imported),
        ):
            self.dialog.choose_deck_sound()
        self.assertEqual(self.dialog.deck["sound"], "custom")
        self.assertEqual(self.dialog.deck["sound_path"], imported)
        self.assertEqual(key["sound_path"], "individual.wav")
        self.assertEqual(self.dialog.deck_inspector.sound_file_button.text(), "global.wav")

    def test_key_status_explains_global_mute_and_zero_volume(self):
        key_id = self.dialog.current_keys()[0]["id"]
        self.dialog.canvas.select([key_id])
        self.dialog.set_deck_fields({"sound_enabled": False})
        self.assertEqual(
            self.dialog.key_inspector.sound_status.text(),
            t(
                "widget.launcher.studio.sound_muted",
                "전체 효과음이 꺼져 있어 키를 눌러도 소리가 나지 않습니다.",
            ),
        )
        self.dialog.set_deck_fields({"sound_enabled": True, "sound_volume": 0})
        self.assertIn("0%", self.dialog.key_inspector.sound_status.text())
        self.dialog.key_inspector.global_sound_button.click()
        self.assertIs(self.dialog.inspector_stack.currentWidget(), self.dialog.deck_inspector)

    def test_preview_buttons_use_global_and_individual_playback_routes(self):
        with patch.object(self.dialog.canvas, "preview_deck_sound") as preview:
            self.dialog.deck_inspector.sound_preview_button.click()
        preview.assert_called_once_with()
        key_id = self.dialog.current_keys()[0]["id"]
        self.dialog.canvas.select([key_id])
        with patch.object(self.dialog.canvas, "press_visual") as press:
            self.dialog.key_inspector.sound_preview_button.click()
        press.assert_called_once_with(key_id, force_sound=True)

    def test_overlay_routes_sound_entry_to_the_existing_studio(self):
        studio = Mock()
        host = Mock(_studio=studio)
        OverlayLauncherDeckWidget._open_settings(host, key_id="key-2", sound_settings=True)
        studio.show_sound_settings.assert_called_once_with("key-2")
        studio.raise_.assert_called_once_with()
        studio.activateWindow.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
