# -*- coding: utf-8 -*-
"""KeyDeck Studio: draft editing, multi-select, undo/redo, canvas manipulation."""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox, QSizePolicy

from calendar_app.presentation.widgets.keydeck import model as m
from calendar_app.presentation.widgets.keydeck.studio import (
    KeyDeckStudioDialog,
    UnsavedChangesDialog,
)
from calendar_app.shared.app_lifecycle import EXITING_PROPERTY


class KeyDeckStudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        patcher = patch(
            "calendar_app.presentation.widgets.keydeck.studio.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self._app.setProperty(EXITING_PROPERTY, False)
        self.addCleanup(self._app.setProperty, EXITING_PROPERTY, False)
        self.original = m.build_template_deck("macro_3x3")
        self.executed = []
        self.dialog = KeyDeckStudioDialog(
            self.original, execute_callback=lambda action: self.executed.append(action) or True
        )
        self.dialog.resize(1260, 800)
        self.dialog.show()
        self._app.processEvents()

    def tearDown(self):
        self.dialog._dirty = False
        self.dialog.close()
        super().tearDown()

    def keys(self):
        return self.dialog.current_keys()

    def _point(self, key, dx=0.0, dy=0.0) -> QPoint:
        canvas = self.dialog.canvas
        rect = canvas.renderer.geometry.key_rect(key)
        return (rect.center() + canvas.content_offset()).toPoint() + QPoint(int(dx), int(dy))

    @staticmethod
    def _wheel(widget, delta: int = 120, modifiers=Qt.KeyboardModifier.NoModifier) -> QWheelEvent:
        local = QPointF(widget.rect().center())
        event = QWheelEvent(
            local,
            QPointF(widget.mapToGlobal(local.toPoint())),
            QPoint(),
            QPoint(0, delta),
            Qt.MouseButton.NoButton,
            modifiers,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        widget.wheelEvent(event)
        return event

    def test_edits_stay_in_the_draft_until_applied(self):
        first = self.keys()[0]
        self.dialog.canvas.select([first["id"]])
        self.dialog.set_key_fields({"cap.material": "smoke", "label": "초안"})
        self.assertEqual(self.original["pages"][0]["keys"][0]["cap"]["material"], "crystal")
        result = self.dialog.result_deck()
        self.assertEqual(result["pages"][0]["keys"][0]["label"], "초안")
        self.assertEqual(result["theme"], m.CUSTOM_THEME_ID)

    def test_style_edits_apply_to_every_selected_key_but_content_needs_single_selection(self):
        ids = [key["id"] for key in self.keys()[:3]]
        self.dialog.canvas.select(ids)
        self.assertIs(self.dialog.inspector_stack.currentWidget(), self.dialog.key_inspector)
        self.assertFalse(self.dialog.key_inspector.label_edit.isEnabled())
        self.dialog.key_inspector.material_seg._clicked("pudding")
        self.assertTrue(all(key["cap"]["material"] == "pudding" for key in self.keys()[:3]))
        self.assertEqual(self.keys()[3]["cap"]["material"], "crystal")

    def test_empty_selection_shows_deck_settings(self):
        self.dialog.canvas.select([])
        self.assertIs(self.dialog.inspector_stack.currentWidget(), self.dialog.deck_inspector)
        self.dialog.deck_inspector.case_seg._clicked("walnut")
        self.assertEqual(self.dialog.deck["case"]["style"], "walnut")

    def test_undo_redo_and_slider_coalescing(self):
        key = self.keys()[0]
        self.dialog.canvas.select([key["id"]])
        for value in (110, 120, 130):
            self.dialog.set_key_fields({"legend.size": value}, coalesce="legend.size")
        self.assertEqual(len(self.dialog._undo), 1)
        self.dialog.undo()
        self.assertEqual(self.keys()[0]["legend"]["size"], 100)
        self.dialog.redo()
        self.assertEqual(self.keys()[0]["legend"]["size"], 130)
        self.assertEqual(self.dialog.canvas.selection, [key["id"]])

    def test_add_duplicate_delete_keys(self):
        count = len(self.keys())
        self.dialog.add_key()
        self.assertEqual(len(self.keys()), count + 1)
        self.dialog.duplicate_selected()
        self.assertEqual(len(self.keys()), count + 2)
        self.assertFalse(m.has_overlaps(self.keys()))
        self.dialog.delete_selected()
        self.assertEqual(len(self.keys()), count + 1)
        self.assertEqual(self.dialog.canvas.selection, [])

    def test_style_clipboard(self):
        first, second = self.keys()[0], self.keys()[1]
        first["cap"]["color"] = "#abcdef"
        self.dialog.canvas.select([first["id"]])
        self.dialog.copy_style()
        self.dialog.canvas.select([second["id"]])
        self.dialog.paste_style()
        self.assertEqual(self.keys()[1]["cap"]["color"], "#abcdef")

    def test_pages_can_be_added_duplicated_and_removed(self):
        self.dialog.add_page()
        self.assertEqual((len(self.dialog.deck["pages"]), self.dialog.deck["page"]), (2, 1))
        self.dialog._duplicate_page(0)
        self.assertEqual(len(self.dialog.deck["pages"]), 3)
        self.assertEqual(len(self.dialog.deck["pages"][1]["keys"]), 9)
        self.dialog._delete_page(1)
        self.assertEqual(len(self.dialog.deck["pages"]), 2)
        self.assertEqual(self.dialog.page_tabs.count(), 2)

    def test_templates_and_scoped_themes(self):
        self.dialog._apply_template("edit_cluster")
        self.assertEqual(len(self.keys()), 10)
        target = self.keys()[0]["id"]
        self.dialog._apply_theme("smoke_neon", {target})
        self.assertEqual(self.keys()[0]["cap"]["material"], "smoke")
        self.assertEqual(self.keys()[1]["cap"]["material"], "crystal")

    def test_dragging_moves_keys_with_quarter_unit_snapping(self):
        key = self.keys()[0]
        canvas = self.dialog.canvas
        unit = canvas.renderer.geometry.unit
        start = self._point(key)
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
        QTest.mouseMove(canvas, start + QPoint(int(unit * 3.1), 0))
        QTest.mouseRelease(
            canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            start + QPoint(int(unit * 3.1), 0),
        )
        moved = next(item for item in self.keys() if item["id"] == key["id"])
        self.assertEqual(moved["x"] % 0.25, 0.0)
        self.assertGreaterEqual(moved["x"], 2.0)
        self.assertFalse(m.has_overlaps(self.keys()))
        self.assertTrue(self.dialog._undo)

    def test_dropping_on_a_same_size_key_swaps_them(self):
        first, second = self.keys()[0], self.keys()[1]
        canvas = self.dialog.canvas
        start = self._point(first)
        end = self._point(second)
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
        QTest.mouseMove(canvas, end)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
        by_id = {key["id"]: key for key in self.keys()}
        self.assertEqual((by_id[first["id"]]["x"], by_id[second["id"]]["x"]), (1.0, 0.0))

    def test_resize_handle_changes_width(self):
        key = self.keys()[0]
        canvas = self.dialog.canvas
        canvas.select([key["id"]])
        handle = (canvas._handle_centers()["e"] + canvas.content_offset()).toPoint()
        unit = canvas.renderer.geometry.unit
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, handle)
        QTest.mouseMove(canvas, handle + QPoint(int(unit * 0.5), 0))
        QTest.mouseRelease(
            canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            handle + QPoint(int(unit * 0.5), 0),
        )
        resized = next(item for item in self.keys() if item["id"] == key["id"])
        self.assertEqual(resized["w"], 1.5)
        self.assertFalse(m.has_overlaps(self.keys()))

    def test_box_select_and_keyboard_nudge(self):
        canvas = self.dialog.canvas
        corner = canvas.renderer.geometry.keys_rect.topLeft() + canvas.content_offset()
        start = corner.toPoint() + QPoint(-4, -4)
        end = self._point(self.keys()[4])
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
        QTest.mouseMove(canvas, end)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
        self.assertEqual(len(canvas.selection), 4)
        canvas.select([self.keys()[8]["id"]])
        canvas.nudge(1.0, 0.0)
        self.assertEqual(self.keys()[8]["x"], 3.0)

    def test_action_editor_records_common_hotkeys_and_snippets(self):
        key = self.keys()[0]
        self.dialog.canvas.select([key["id"]])
        editor = self.dialog.key_inspector.action_editor
        editor.type_combo.setCurrentIndex(editor.type_combo.findData("hotkey"))
        editor.common_combo.setCurrentIndex(editor.common_combo.findData("Win+Shift+S"))
        editor._common_picked()
        self.assertEqual(
            self.keys()[0]["action"], {"type": "hotkey", "target": "Win+Shift+S", "paste": False}
        )
        editor.type_combo.setCurrentIndex(editor.type_combo.findData("text"))
        editor.text_edit.setPlainText("주소: 포항")
        editor.paste_check.setChecked(True)
        editor._emit()
        self.assertEqual(self.keys()[0]["action"]["target"], "주소: 포항")
        self.assertTrue(self.keys()[0]["action"]["paste"])

    def test_insert_preview_pan_and_zoom_update_the_key(self):
        key = self.keys()[0]
        self.dialog.canvas.select([key["id"]])
        preview = self.dialog.key_inspector.preview
        preview.panned.emit(20, -10)
        preview.zoomed.emit(150)
        insert = self.keys()[0]["insert"]
        self.assertEqual((insert["ox"], insert["oy"], insert["zoom"]), (20, -10, 150))
        preview.resetRequested.emit()
        self.assertEqual(
            (self.keys()[0]["insert"]["ox"], self.keys()[0]["insert"]["zoom"]), (0, 100)
        )

    def test_inspector_wheel_scroll_never_changes_control_values(self):
        key = self.keys()[0]
        self.dialog.canvas.select([key["id"]])

        combo = self.dialog.key_inspector.action_editor.type_combo
        combo.setCurrentIndex(combo.findData("hotkey"))
        combo_index = combo.currentIndex()
        combo_event = self._wheel(combo)
        self.assertEqual(combo.currentIndex(), combo_index)
        self.assertFalse(combo_event.isAccepted())

        slider = self.dialog.key_inspector.size_slider.slider
        slider.setValue(120)
        slider_event = self._wheel(slider)
        self.assertEqual(slider.value(), 120)
        self.assertFalse(slider_event.isAccepted())

        preview = self.dialog.key_inspector.preview
        zoom = self.keys()[0]["insert"]["zoom"]
        preview_event = self._wheel(preview)
        self.assertEqual(self.keys()[0]["insert"]["zoom"], zoom)
        self.assertFalse(preview_event.isAccepted())

    def test_test_run_uses_the_widget_callback(self):
        key = self.keys()[0]
        self.dialog.canvas.select([key["id"]])
        self.dialog.test_action("action")
        self.assertEqual(self.executed, [key["action"]])

    def test_trying_keys_leaves_tools_usable_and_layout_edits_end_it(self):
        label = self.dialog.preview_button.text()
        self.dialog.preview_button.setChecked(True)
        self.assertTrue(self.dialog.canvas.preview_mode)
        self.assertNotEqual(self.dialog.preview_button.text(), label)
        for button in (
            self.dialog.add_key_button,
            self.dialog.template_button,
            self.dialog.theme_button,
            self.dialog.add_page_button,
        ):
            self.assertTrue(button.isEnabled())
        count = len(self.keys())
        self.dialog.add_key_button.click()
        self.assertFalse(self.dialog.canvas.preview_mode)
        self.assertFalse(self.dialog.preview_button.isChecked())
        self.assertEqual(self.dialog.preview_button.text(), label)
        self.assertEqual(len(self.keys()), count + 1)

    def test_pressing_a_key_while_trying_opens_its_settings(self):
        self.dialog.preview_button.setChecked(True)
        key = self.keys()[4]
        QTest.mouseClick(self.dialog.canvas, Qt.MouseButton.LeftButton, pos=self._point(key))
        self.assertEqual(self.dialog.canvas.selection, [key["id"]])
        self.assertIs(self.dialog.inspector_stack.currentWidget(), self.dialog.key_inspector)
        self.dialog.set_key_fields({"switch": "clicky"})
        self.assertEqual(self.keys()[4]["switch"], "clicky")
        self.assertTrue(self.dialog.canvas.preview_mode)

    def test_toggle_keys_flip_while_trying_and_restore_afterwards(self):
        key = self.keys()[0]
        key["mode"], key["active"] = "toggle", False
        self.dialog.canvas.refresh()
        self.dialog.preview_button.setChecked(True)
        self.dialog._preview_key_activated(key["id"], "action")
        self.assertTrue(self.keys()[0]["active"])
        self.assertFalse(self.dialog._dirty)
        escape = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        self.dialog.keyPressEvent(escape)
        self.assertTrue(escape.isAccepted())
        self.assertFalse(self.dialog.canvas.preview_mode)
        self.assertFalse(self.keys()[0]["active"])
        self.assertTrue(self.dialog.isVisible())

    def test_an_empty_page_cannot_be_tried(self):
        self.dialog.deck["pages"].append(m.new_page("빈"))
        self.dialog._load_page(1, [])
        self.dialog.preview_button.setChecked(True)
        self.assertFalse(self.dialog.canvas.preview_mode)
        self.assertFalse(self.dialog.preview_button.isChecked())

    def test_new_page_starts_with_one_selected_key_and_ends_trying(self):
        self.dialog.preview_button.setChecked(True)
        pages = len(self.dialog.deck["pages"])
        self.dialog.add_page_button.click()
        self.assertEqual(len(self.dialog.deck["pages"]), pages + 1)
        self.assertEqual(self.dialog.deck["page"], pages)
        keys = self.keys()
        self.assertEqual(len(keys), 1)
        self.assertEqual(self.dialog.canvas.selection, [keys[0]["id"]])
        self.assertFalse(self.dialog.canvas.preview_mode)
        self.dialog.undo()
        self.assertEqual(len(self.dialog.deck["pages"]), pages)

    def test_toggle_mode_shows_marker_options(self):
        key = self.keys()[0]
        self.dialog.canvas.select([key["id"]])
        inspector = self.dialog.key_inspector
        self.assertTrue(inspector.toggle_box.isHidden())
        inspector.mode_seg._clicked("toggle")
        self.assertEqual(self.keys()[0]["mode"], "toggle")
        self.assertFalse(inspector.toggle_box.isHidden())
        inspector.indicator_seg._clicked("ring")
        self.assertEqual(self.keys()[0]["indicator"], "ring")
        inspector.start_on_check.setChecked(True)
        self.assertTrue(self.keys()[0]["active"])
        inspector.mode_seg._clicked("tap")
        self.assertFalse(self.keys()[0]["active"])
        self.assertTrue(inspector.toggle_box.isHidden())

    def test_keycap_shape_offers_every_profile(self):
        self.dialog.canvas.select([self.keys()[0]["id"]])
        seg = self.dialog.key_inspector.profile_seg
        self.assertEqual(set(seg._buttons), {pid for pid, *_ in m.PROFILES})
        seg._clicked("round")
        self.assertEqual(self.keys()[0]["cap"]["profile"], "round")

    def _dirty_dialog(self):
        key = self.keys()[0]
        self.dialog.canvas.select([key["id"]])
        self.dialog.set_key_fields({"cap.material": "smoke"})
        self.assertTrue(self.dialog._dirty)
        self.assertNotEqual(self.dialog.windowTitle(), self.dialog._base_title)

    def test_closing_with_edits_offers_apply_discard_or_keep(self):
        self._dirty_dialog()
        with patch.object(self.dialog, "_ask_unsaved_changes", return_value="keep"):
            self.dialog.reject()
        self.assertTrue(self.dialog.isVisible())
        with patch.object(self.dialog, "_ask_unsaved_changes", return_value="apply"):
            self.dialog.reject()
        self.assertEqual(self.dialog.result(), self.dialog.DialogCode.Accepted)

    def test_discard_choice_rejects(self):
        self._dirty_dialog()
        with patch.object(self.dialog, "_ask_unsaved_changes", return_value="discard"):
            self.dialog.reject()
        self.assertFalse(self.dialog.isVisible())
        self.assertEqual(self.dialog.result(), self.dialog.DialogCode.Rejected)

    def test_app_exit_never_blocks_on_the_unsaved_prompt(self):
        self._dirty_dialog()
        self._app.setProperty(EXITING_PROPERTY, True)
        with patch.object(self.dialog, "_ask_unsaved_changes") as ask:
            self.dialog.reject()
            ask.assert_not_called()
        self.assertFalse(self.dialog.isVisible())

    def test_unsaved_prompt_stacks_three_choices_and_escape_keeps_editing(self):
        self._dirty_dialog()
        seen = {}

        def fake_exec(dialog):
            layout = dialog.layout()
            buttons = (dialog.apply_button, dialog.discard_button, dialog.keep_button)
            seen["order"] = [layout.indexOf(button) for button in buttons]
            seen["full_width"] = all(
                button.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
                for button in buttons
            )
            QTest.keyClick(dialog, Qt.Key.Key_Escape)
            return 0

        with patch.object(UnsavedChangesDialog, "exec", fake_exec):
            self.assertEqual(self.dialog._ask_unsaved_changes(), "keep")
        self.assertEqual(seen["order"], sorted(seen["order"]))
        self.assertTrue(all(index >= 0 for index in seen["order"]))
        self.assertTrue(seen["full_width"])

        def fake_discard(dialog):
            dialog.discard_button.click()
            return 1

        with patch.object(UnsavedChangesDialog, "exec", fake_discard):
            self.assertEqual(self.dialog._ask_unsaved_changes(), "discard")

    def test_opening_on_a_key_selects_it_on_its_page(self):
        deck = m.build_template_deck("macro_3x3")
        page = m.new_page("둘")
        page["keys"] = m.template_keys("command_bar")
        deck["pages"].append(page)
        dialog = KeyDeckStudioDialog(deck, key_id=page["keys"][2]["id"])
        self.assertEqual(dialog.deck["page"], 1)
        self.assertEqual(dialog.canvas.selection, [page["keys"][2]["id"]])
        dialog.close()

    # -- deck panorama -------------------------------------------------------------------

    def _panorama_file(self, width: int, height: int, *, transparent: bool = False) -> str:
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, True)
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(QColor(0, 0, 0, 0) if transparent else QColor("#3060a0"))
        if transparent:
            for x in range(width // 4, width * 3 // 4):
                for y in range(height // 4, height * 3 // 4):
                    image.setPixelColor(x, y, QColor("#d02040"))
        path = os.path.join(directory, "My Banner.png")
        self.assertTrue(image.save(path))
        return path

    def _no_asset_copy(self):
        patcher = patch(
            "calendar_app.presentation.widgets.keydeck.studio.import_launcher_asset",
            side_effect=lambda path, kind: path,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_choosing_a_panorama_applies_it_to_the_page_in_one_undo_step(self):
        self._no_asset_copy()
        path = self._panorama_file(640, 360)
        undo_depth = len(self.dialog._undo)
        self.assertTrue(self.dialog.choose_panorama(path))
        panorama = self.dialog.deck["panorama"]
        self.assertEqual((panorama["path"], panorama["name"]), (path, "My Banner.png"))
        self.assertEqual(panorama["fit"], "cover")
        self.assertTrue(all(key["insert"]["kind"] == "panorama" for key in self.keys()))
        self.assertEqual(len(self.dialog._undo), undo_depth + 1)
        self.assertIn("9", self.dialog.status.text())
        self.dialog.undo()
        self.assertEqual(self.dialog.deck["panorama"]["path"], "")
        self.assertFalse(m.panorama_keys(self.dialog.deck))

    def test_panorama_goes_to_the_selection_and_later_only_swaps_the_picture(self):
        self._no_asset_copy()
        chosen = [key["id"] for key in self.keys()[:2]]
        self.dialog.canvas.select(chosen)
        self.dialog.choose_panorama(self._panorama_file(640, 360))
        self.assertEqual([key["id"] for key in m.panorama_keys(self.dialog.deck)], chosen)
        self.dialog.canvas.select([])
        second = self._panorama_file(300, 300)
        self.dialog.choose_panorama(second)
        self.assertEqual(self.dialog.deck["panorama"]["path"], second)
        self.assertEqual([key["id"] for key in m.panorama_keys(self.dialog.deck)], chosen)

    def test_transparent_logo_defaults_to_the_whole_picture(self):
        self._no_asset_copy()
        self.dialog.choose_panorama(self._panorama_file(400, 100, transparent=True))
        self.assertEqual(self.dialog.deck["panorama"]["fit"], "contain")

    def test_cancelled_panorama_pick_changes_nothing(self):
        with patch.object(self.dialog, "_pick_image_path", return_value=""):
            self.assertFalse(self.dialog.choose_panorama(""))
            key = self.keys()[0]
            before = key["insert"]["kind"]
            self.dialog.canvas.select([key["id"]])
            self.dialog.key_inspector._kind_changed("panorama")
        self.assertEqual(self.keys()[0]["insert"]["kind"], before)
        self.assertEqual(self.dialog.key_inspector.kind_seg.value(), before)
        self.assertFalse(self.dialog._dirty)

    def test_clearing_the_panorama_empties_its_keys_in_one_undo_step(self):
        self._no_asset_copy()
        self.dialog.choose_panorama(self._panorama_file(640, 360))
        editor = self.dialog.deck_inspector.panorama_editor
        self.assertTrue(editor.clear_button.isEnabled())
        undo_depth = len(self.dialog._undo)
        editor.clear_button.click()
        self.assertEqual(self.dialog.deck["panorama"], m.default_panorama())
        self.assertTrue(all(key["insert"]["kind"] == "none" for key in self.keys()))
        self.assertEqual(len(self.dialog._undo), undo_depth + 1)
        self.assertFalse(editor.clear_button.isEnabled())
        self.dialog.undo()
        self.assertTrue(all(key["insert"]["kind"] == "panorama" for key in self.keys()))

    def test_deck_inspector_flags_an_unused_panorama(self):
        self._no_asset_copy()
        self.dialog.choose_panorama(self._panorama_file(640, 360))
        for key in self.keys():
            key["insert"]["kind"] = "color"
        self.dialog._reload_inspector()
        editor = self.dialog.deck_inspector.panorama_editor
        self.assertFalse(editor.notice.isHidden())
        self.assertTrue(editor.apply_button.isEnabled())
        editor.apply_button.click()
        self.assertTrue(all(key["insert"]["kind"] == "panorama" for key in self.keys()))
        self.assertFalse(editor.apply_button.isEnabled())

    def _mouse(self, kind, widget, pos: QPointF) -> QMouseEvent:
        buttons = (
            Qt.MouseButton.NoButton
            if kind == QEvent.Type.MouseButtonRelease
            else Qt.MouseButton.LeftButton
        )
        return QMouseEvent(
            kind,
            pos,
            QPointF(widget.mapToGlobal(pos.toPoint())),
            Qt.MouseButton.LeftButton,
            buttons,
            Qt.KeyboardModifier.NoModifier,
        )

    def test_panorama_preview_drag_zoom_and_reset(self):
        self._no_asset_copy()
        self.dialog.choose_panorama(self._panorama_file(640, 360))
        preview = self.dialog.deck_inspector.panorama_editor.preview
        preview.resize(380, 220)
        start = QPointF(190, 100)
        preview.mousePressEvent(self._mouse(QEvent.Type.MouseButtonPress, preview, start))
        preview.mouseMoveEvent(self._mouse(QEvent.Type.MouseMove, preview, start + QPointF(30, 25)))
        preview.mouseReleaseEvent(
            self._mouse(QEvent.Type.MouseButtonRelease, preview, start + QPointF(30, 25))
        )
        panorama = self.dialog.deck["panorama"]
        self.assertLess(panorama["x"], 0)  # 그림을 오른쪽으로 끌면 왼쪽 부분이 보인다
        self.assertEqual(panorama["y"], 0)  # 세로로 꽉 찬 축은 움직이지 않는다
        self.assertFalse(self._wheel(preview).isAccepted())  # 그냥 휠은 스크롤에 양보
        self.assertEqual(self.dialog.deck["panorama"]["zoom"], 100)
        self._wheel(preview, modifiers=Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.dialog.deck["panorama"]["zoom"], 110)
        preview.mouseDoubleClickEvent(self._mouse(QEvent.Type.MouseButtonDblClick, preview, start))
        panorama = self.dialog.deck["panorama"]
        self.assertEqual((panorama["x"], panorama["y"], panorama["zoom"]), (0, 0, 100))

    def test_panorama_keys_use_the_layout_preview_in_the_key_inspector(self):
        self._no_asset_copy()
        self.dialog.choose_panorama(self._panorama_file(640, 360))
        key = self.keys()[4]
        self.dialog.canvas.select([key["id"]])
        inspector = self.dialog.key_inspector
        self.assertTrue(inspector.preview.isHidden())
        self.assertFalse(inspector.panorama_box.isHidden())
        self.assertEqual(inspector.panorama_editor.preview._highlight, {key["id"]})


if __name__ == "__main__":
    unittest.main()
