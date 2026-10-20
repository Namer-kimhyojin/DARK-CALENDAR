# -*- coding: utf-8 -*-
"""Beatmaker Studio presets preserve draft edits, navigation and sound selection."""

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from calendar_app.presentation.widgets.keydeck import model as m
from calendar_app.presentation.widgets.keydeck.beatmaker import (
    BEATMAKER_TEMPLATE_KITS,
    beatmaker_state,
)
from calendar_app.presentation.widgets.keydeck.layout_dialog import (
    LayoutLibraryDialog,
    resolve_request,
)
from calendar_app.presentation.widgets.keydeck.studio import KeyDeckStudioDialog
from calendar_app.shared.app_lifecycle import EXITING_PROPERTY


class BeatmakerStudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings = QSettings(
            str(Path(self.directory.name) / "beatmaker-ui.ini"), QSettings.Format.IniFormat
        )
        for module in (
            "calendar_app.infrastructure.i18n",
            "calendar_app.presentation.dialogs.dialog_styles",
            "calendar_app.shared.theme_snapshot",
        ):
            patcher = patch(f"{module}.QSettings", return_value=self.settings)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch(
            "calendar_app.presentation.widgets.keydeck.canvas.sound_bank", return_value=Mock()
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app.setProperty(EXITING_PROPERTY, False)
        self.original = m.build_template_deck("beatmaker_4x4")
        self.executed = Mock(return_value=True)
        self.dialog = KeyDeckStudioDialog(self.original, execute_callback=self.executed)
        self.dialog.show()
        self.app.processEvents()
        self.addCleanup(self._close_dialog)

    def _close_dialog(self):
        self.dialog.force_close()
        self.dialog.deleteLater()
        self.app.processEvents()

    def test_gallery_exposes_beatmaker_and_explains_included_sounds(self):
        gallery = LayoutLibraryDialog(
            self.original, self.dialog, library_root=Path(self.directory.name) / "layouts"
        )
        try:
            rows = {
                gallery.grid.item(index).data(Qt.ItemDataRole.UserRole)[1]: index
                for index in range(gallery.grid.count())
            }
            self.assertEqual(gallery.grid.count(), 13)
            for template_id, kit in BEATMAKER_TEMPLATE_KITS.items():
                with self.subTest(kit=kit):
                    gallery.grid.setCurrentRow(rows[template_id])
                    label = {"lofi": "Lo-fi Desk", "neon": "Neon Beat", "arcade": "8-bit Arcade"}[
                        kit
                    ]
                    self.assertIn(label, gallery.grid.currentItem().text())
                    self.assertIn(label, gallery.detail_meta.text())
                    self.assertIn("4×4", gallery.detail_meta.text())
                    self.assertEqual(
                        gallery.grid.currentItem().toolTip(),
                        gallery.grid.currentItem().text().replace("\n", " · "),
                    )
                    self.assertIn("\n", gallery.grid.currentItem().text())
            self.assertEqual(gallery.grid.textElideMode(), Qt.TextElideMode.ElideNone)
        finally:
            gallery.deleteLater()

    def test_all_three_kit_captions_fit_in_the_first_row_at_gallery_sizes(self):
        with patch(
            "calendar_app.presentation.dialogs.dialog_styles._available_dialog_bounds",
            return_value=(1800, 1100),
        ):
            gallery = LayoutLibraryDialog(
                self.original, self.dialog, library_root=Path(self.directory.name) / "layouts"
            )
            try:
                gallery.show()
                self.app.processEvents()
                self.app.processEvents()
                for width, height in ((1000, 660), (1300, 800)):
                    with self.subTest(width=width):
                        gallery.resize(width, height)
                        self.app.processEvents()
                        self.assertEqual(gallery.width(), width)
                        first_row = []
                        for index in range(3):
                            item = gallery.grid.item(index)
                            rect = gallery.grid.visualItemRect(item)
                            self.assertTrue(gallery.grid.viewport().rect().contains(rect))
                            self.assertGreaterEqual(
                                rect.height(),
                                gallery.grid.iconSize().height()
                                + 2 * gallery.grid.fontMetrics().height(),
                            )
                            self.assertEqual(len(item.text().splitlines()), 2)
                            first_row.append(rect.y())
                        self.assertEqual(len(set(first_row)), 1)
            finally:
                gallery.reject()
                gallery.deleteLater()

    def test_each_kit_card_adds_its_sounds_and_preserves_custom_pages(self):
        source = m.build_template_deck("macro_3x3")
        custom = m.new_page("Customized")
        key = m.make_key("Keep me")
        key["sound"] = "custom"
        key["sound_path"] = "private-sound.wav"
        key["sound_volume"] = 37
        custom["keys"].append(key)
        source["pages"].append(custom)
        saved = deepcopy(source)
        for template_id, kit in BEATMAKER_TEMPLATE_KITS.items():
            with self.subTest(kit=kit):
                gallery = LayoutLibraryDialog(
                    source, self.dialog, library_root=Path(self.directory.name) / "layouts"
                )
                try:
                    row = next(
                        index
                        for index in range(gallery.grid.count())
                        if gallery.grid.item(index).data(Qt.ItemDataRole.UserRole)
                        == ("template", template_id)
                    )
                    gallery.grid.setCurrentRow(row)
                    gallery.new_page_button.click()
                    self.assertEqual(gallery.request, ("template", template_id, "new_page"))
                    result = resolve_request(source, gallery.request)
                    self.assertEqual(source, saved)
                    self.assertEqual(result["pages"][:2], saved["pages"])
                    self.assertEqual(len(result["pages"]), 4)
                    self.assertEqual(
                        beatmaker_state(result["pages"][result["page"]]),
                        {"kit": kit, "bank": "drums"},
                    )
                    for page in result["pages"][2:]:
                        self.assertTrue(
                            all(pad["sound"].startswith(f"beat_{kit}_") for pad in page["keys"])
                        )
                finally:
                    gallery.deleteLater()

    def test_full_deck_replacement_keeps_all_other_pages_for_each_kit_card(self):
        source = m.build_template_deck("macro_3x3")
        while len(source["pages"]) < m.MAX_PAGES:
            page = m.new_page(f"Keep page {len(source['pages'])}")
            page["keys"].append(m.make_key("Customized pad"))
            source["pages"].append(page)
        saved = deepcopy(source)
        for template_id, kit in BEATMAKER_TEMPLATE_KITS.items():
            with self.subTest(kit=kit):
                gallery = LayoutLibraryDialog(
                    source, self.dialog, library_root=Path(self.directory.name) / "layouts"
                )
                try:
                    row = next(
                        index
                        for index in range(gallery.grid.count())
                        if gallery.grid.item(index).data(Qt.ItemDataRole.UserRole)
                        == ("template", template_id)
                    )
                    gallery.grid.setCurrentRow(row)
                    self.assertFalse(gallery.new_page_button.isEnabled())
                    with patch(
                        "calendar_app.presentation.widgets.keydeck.layout_dialog._ChoiceDialog.exec",
                        return_value=1,
                    ):
                        gallery.apply_button.click()
                    result = resolve_request(source, gallery.request)
                    self.assertEqual(source, saved)
                    self.assertEqual(len(result["pages"]), m.MAX_PAGES)
                    self.assertEqual(result["pages"][1:], saved["pages"][1:])
                    self.assertEqual(
                        beatmaker_state(result["pages"][0]), {"kit": kit, "bank": "drums"}
                    )
                    self.assertTrue(
                        all(
                            pad["sound"].startswith(f"beat_{kit}_")
                            for pad in result["pages"][0]["keys"]
                        )
                    )
                finally:
                    gallery.deleteLater()

    def test_controls_follow_current_page_and_hide_on_launcher_pages(self):
        self.assertTrue(self.dialog.beatmaker_controls.isVisible())
        normal = m.new_page("Launcher")
        normal["keys"].append(m.make_key("App"))
        self.dialog.deck["pages"].append(normal)
        self.dialog._load_page(2, [])
        self.assertFalse(self.dialog.beatmaker_controls.isVisible())
        self.assertFalse(self.dialog.deck_inspector.beatmaker_controls.isVisible())
        self.dialog._load_page(1, [])
        self.assertEqual(self.dialog.beatmaker_controls.bank_combo.currentData(), "melody")

    def test_kit_choice_is_one_undoable_draft_edit_and_preserves_other_pages(self):
        original = deepcopy(self.original)
        melody = deepcopy(self.dialog.deck["pages"][1])
        combo = self.dialog.beatmaker_controls.kit_combo
        index = combo.findData("neon")
        combo.setCurrentIndex(index)
        combo.activated.emit(index)
        self.assertEqual(beatmaker_state(self.dialog.deck["pages"][0])["kit"], "neon")
        self.assertTrue(
            all(key["sound"].startswith("beat_neon_") for key in self.dialog.current_keys())
        )
        self.assertEqual(self.dialog.deck["pages"][1], melody)
        self.assertEqual(self.original, original)
        self.assertEqual(len(self.dialog._undo), 1)
        self.dialog.undo()
        self.assertEqual(self.dialog.result_deck(), original)
        self.assertEqual(combo.currentData(), "lofi")
        self.dialog.redo()
        self.assertEqual(combo.currentData(), "neon")

    def test_bank_navigation_keeps_customized_pads_without_replacing_them(self):
        first = self.dialog.current_keys()[0]
        first["label"] = "Customized drum"
        first["sound_volume"] = 38
        saved = deepcopy(self.dialog.deck["pages"][0])
        self.dialog.set_beatmaker_bank("melody")
        self.assertEqual(self.dialog.deck["page"], 1)
        self.dialog.set_beatmaker_bank("drums")
        self.assertEqual(self.dialog.deck["pages"][0], saved)
        self.assertFalse(self.dialog._dirty)
        self.assertFalse(self.dialog._undo)

    def test_missing_bank_adds_a_page_and_undo_restores_the_previous_deck(self):
        self.dialog.deck["pages"].pop()
        saved = deepcopy(self.dialog.deck)
        self.dialog.set_beatmaker_bank("melody")
        self.assertEqual(len(self.dialog.deck["pages"]), 2)
        self.assertEqual(self.dialog.deck["pages"][0], saved["pages"][0])
        self.assertEqual(beatmaker_state(self.dialog.deck["pages"][1])["bank"], "melody")
        self.dialog.undo()
        self.assertEqual(self.dialog.deck, saved)

    def test_full_deck_cannot_replace_existing_pads_when_a_bank_is_missing(self):
        self.dialog.deck["pages"].pop()
        while len(self.dialog.deck["pages"]) < m.MAX_PAGES:
            self.dialog.deck["pages"].append(m.new_page("Launcher"))
        saved = deepcopy(self.dialog.deck)
        self.dialog.set_beatmaker_bank("melody")
        self.assertEqual(self.dialog.deck, saved)
        self.assertEqual(self.dialog.beatmaker_controls.bank_combo.currentData(), "drums")
        self.assertFalse(self.dialog._undo)

    def test_preview_uses_selected_or_first_pad_without_running_an_action(self):
        first_id = self.dialog.current_keys()[0]["id"]
        last_id = self.dialog.current_keys()[-1]["id"]
        with patch.object(self.dialog.canvas, "press_visual") as play:
            self.dialog.beatmaker_controls.preview_button.click()
            play.assert_called_once_with(first_id, force_sound=True)
        self.dialog.canvas.select([last_id])
        with patch.object(self.dialog.canvas, "press_visual") as play:
            self.dialog.beatmaker_controls.preview_button.click()
            play.assert_called_once_with(last_id, force_sound=True)
        self.executed.assert_not_called()
        self.assertFalse(self.dialog._dirty)

    def test_sound_action_editor_has_no_target_field_and_testing_plays_locally(self):
        key = self.dialog.current_keys()[0]
        self.dialog.canvas.select([key["id"]])
        editor = self.dialog.key_inspector.action_editor
        self.assertEqual(editor.type_combo.currentData(), "sound")
        self.assertEqual(editor.action()["target"], "")
        self.assertFalse(editor.path_edit.isVisible())
        with patch.object(self.dialog.canvas, "press_visual") as play:
            self.dialog.test_action("action")
            play.assert_called_once_with(key["id"])
        self.executed.assert_not_called()

    def test_individual_volume_keeps_master_and_other_pads_and_supports_undo(self):
        first, second = self.dialog.current_keys()[:2]
        original_master = self.dialog.deck["sound_volume"]
        self.dialog.canvas.select([first["id"]])
        self.dialog.key_inspector.sound_volume_slider.slider.setValue(34)
        self.assertEqual(first["sound_volume"], 34)
        self.assertEqual(second["sound_volume"], 100)
        self.assertEqual(self.dialog.deck["sound_volume"], original_master)
        self.assertEqual(self.original["pages"][0]["keys"][0]["sound_volume"], 100)
        self.dialog.undo()
        self.assertEqual(self.dialog.current_keys()[0]["sound_volume"], 100)
        self.assertEqual(self.dialog.key_inspector.sound_volume_slider.value(), 100)

    def test_sound_catalog_is_searchable_and_typing_does_not_change_saved_sound(self):
        key = self.dialog.current_keys()[0]
        self.dialog.canvas.select([key["id"]])
        combo = self.dialog.key_inspector.sound_combo
        sound = key["sound"]
        self.assertTrue(combo.isEditable())
        self.assertGreaterEqual(combo.findData("beat_arcade_note_c6"), 0)
        combo.lineEdit().selectAll()
        QTest.keyClicks(combo.lineEdit(), "Neon")
        self.assertEqual(key["sound"], sound)
        self.assertFalse(self.dialog._dirty)
        index = combo.findData("beat_neon_kick")
        combo.setCurrentIndex(index)
        combo.activated.emit(index)
        self.assertEqual(key["sound"], "beat_neon_kick")

    def test_label_typing_does_not_trigger_performance_playback_in_studio(self):
        key = self.dialog.current_keys()[0]
        self.dialog.canvas.select([key["id"]])
        edit = self.dialog.key_inspector.label_edit
        edit.setFocus()
        edit.selectAll()
        with patch.object(self.dialog.canvas, "press_visual") as play:
            QTest.keyClicks(edit, "QWER1234")
        self.assertEqual(key["label"], "QWER1234")
        play.assert_not_called()


class BeatmakerLocaleTests(unittest.TestCase):
    def test_all_bundled_locales_include_the_same_new_keys(self):
        root = Path(__file__).resolve().parents[1] / "locales"
        english = json.loads((root / "en.json").read_text(encoding="utf-8", errors="strict"))
        keys = set(english["beatmaker"])
        sounds = {key for key in english["widget"]["launcher"]["sound"] if key.startswith("beat_")}
        self.assertEqual(len(sounds), 96)
        paths = list(root.glob("*.json"))
        self.assertEqual(len(paths), 19)
        for path in paths:
            data = json.loads(path.read_text(encoding="utf-8", errors="strict"))
            with self.subTest(locale=path.stem):
                self.assertEqual(set(data["beatmaker"]), keys)
                self.assertTrue(sounds <= set(data["widget"]["launcher"]["sound"]))
                self.assertIn("sound", data["widget"]["launcher"]["action"])
                self.assertIn("beatmaker_4x4", data["widget"]["launcher"]["template"])
                self.assertTrue(
                    set(BEATMAKER_TEMPLATE_KITS) <= set(data["widget"]["launcher"]["template"])
                )
                self.assertIn("{kit}", data["beatmaker"]["gallery_detail"])


if __name__ == "__main__":
    unittest.main()
