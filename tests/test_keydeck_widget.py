# -*- coding: utf-8 -*-
"""KeyDeck overlay widget integration: persistence, migration, actions, input routing."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings, Qt, QUrl
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from calendar_app.presentation.widgets.keydeck import model as m
from calendar_app.presentation.widgets.overlay_launcher_deck import (
    DATA_KEY,
    LEGACY_DATA_KEY,
    OverlayLauncherDeckWidget,
)
from calendar_app.shared.app_lifecycle import EXITING_PROPERTY

_MODULE = "calendar_app.presentation.widgets.overlay_launcher_deck"


class _Owner(QWidget):
    def __init__(self):
        super().__init__()
        # 테스트마다 독립된 INI 파일을 써서 레지스트리 공유 설정의 동기화 타이밍 간섭을 없앤다.
        self._settings_dir = tempfile.TemporaryDirectory()
        self.settings = QSettings(
            os.path.join(self._settings_dir.name, "keydeck.ini"), QSettings.Format.IniFormat
        )
        self.calls = []
        self.overlay_manager = type(
            "_Manager", (), {"_open_manager_dialog": lambda inner: self.calls.append("widgets")}
        )()

    def open_task_dialog(self):
        self.calls.append("new_task")

    def jump_to_today(self):
        self.calls.append("today")

    def sync_google_calendar(self):
        self.calls.append("sync_google")

    def show_command_palette(self):
        self.calls.append("command_palette")

    def toggle_focus_mode(self):
        raise RuntimeError("boom")


def _prefixed(key: str) -> str:
    return f"overlay_launcher_deck_{key}"


class KeyDeckWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self._app.setProperty(EXITING_PROPERTY, False)
        self.addCleanup(self._app.setProperty, EXITING_PROPERTY, False)
        self.owner = _Owner()
        self.widget = self._make_widget()

    def _make_widget(self) -> OverlayLauncherDeckWidget:
        widget = OverlayLauncherDeckWidget(self.owner)
        widget._set("enabled", True)
        widget.apply_initial_settings()
        self._app.processEvents()
        widget._canvas._armed_at = 0.0
        return widget

    def tearDown(self):
        self.widget.close()
        self.owner.settings.clear()
        self.owner.settings.sync()
        self.owner.close()
        super().tearDown()

    def test_default_widget_renders_the_template_and_never_takes_focus(self):
        deck = self.widget.deck()
        self.assertEqual(len(deck["pages"][0]["keys"]), len(m.template_keys(m.DEFAULT_TEMPLATE_ID)))
        self.assertTrue(self.widget.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus)
        self.assertTrue(self.owner.settings.contains(_prefixed(DATA_KEY)))
        self.assertFalse(self.widget.grab().isNull())
        self.assertGreaterEqual(self.widget.width(), self.widget._canvas.sizeHint().width() - 2)

    def test_v3_data_is_migrated_non_destructively(self):
        self.widget.close()
        self.owner.settings.clear()
        legacy = {
            "version": 3,
            "keys": [
                {
                    "id": "old1",
                    "label": "레거시",
                    "row": 0,
                    "column": 0,
                    "width": 2,
                    "action_type": "url",
                    "target": "https://example.com",
                }
            ],
        }
        self.owner.settings.setValue(_prefixed(LEGACY_DATA_KEY), json.dumps(legacy))
        self.owner.settings.sync()
        self.widget = self._make_widget()
        key = self.widget.deck()["pages"][0]["keys"][0]
        self.assertEqual((key["label"], key["w"], key["action"]["type"]), ("레거시", 2.0, "url"))
        self.assertTrue(self.owner.settings.contains(_prefixed(LEGACY_DATA_KEY)))
        stored = json.loads(self.owner.settings.value(_prefixed(DATA_KEY)))
        self.assertEqual(stored["version"], 4)

    def test_commands_run_through_a_whitelist(self):
        run = self.widget._execute_action
        self.assertTrue(run({"type": "command", "target": "new_task"}))
        self.assertTrue(run({"type": "command", "target": "widget_manager"}))
        self.assertFalse(run({"type": "command", "target": "format_disk"}))
        self.assertFalse(run({"type": "command", "target": "focus_mode"}))
        self.assertEqual(self.owner.calls, ["new_task", "widgets"])

    def test_urls_require_http_and_placeholders_are_unassigned(self):
        with patch(f"{_MODULE}.QDesktopServices.openUrl", return_value=True) as open_url:
            self.assertTrue(
                self.widget._execute_action({"type": "url", "target": "https://example.com"})
            )
            self.assertFalse(self.widget._execute_action({"type": "url", "target": "file:///C:/x"}))
            self.assertIsNone(self.widget._execute_action({"type": "url", "target": "https://"}))
        self.assertEqual(open_url.call_count, 1)
        self.assertIsNone(self.widget._execute_action({"type": "none", "target": ""}))

    def test_apps_open_files_but_block_scripts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            safe = Path(tmpdir) / "notes.txt"
            safe.write_text("ok", encoding="utf-8", errors="strict")
            script = Path(tmpdir) / "run.ps1"
            script.write_text("echo no", encoding="utf-8", errors="strict")
            with patch(f"{_MODULE}.QDesktopServices.openUrl", return_value=True) as open_url:
                self.assertTrue(self.widget._execute_action({"type": "app", "target": str(safe)}))
                self.assertFalse(
                    self.widget._execute_action({"type": "app", "target": str(script)})
                )
                self.assertFalse(
                    self.widget._execute_action({"type": "app", "target": str(safe) + ".gone"})
                )
            self.assertEqual(open_url.call_count, 1)
            self.assertEqual(QUrl.fromLocalFile(str(safe)), open_url.call_args[0][0])

    def test_hotkeys_and_text_snippets_target_the_active_app(self):
        with patch(f"{_MODULE}.send_hotkey", return_value=True) as sender:
            self.assertTrue(
                self.widget._execute_action({"type": "hotkey", "target": "Ctrl+Shift+K"})
            )
            sender.assert_called_once_with("Ctrl+Shift+K")
        self.assertTrue(
            self.widget._execute_action({"type": "text", "target": "서명입니다", "paste": False})
        )
        self.assertEqual(QGuiApplication.clipboard().text(), "서명입니다")
        self.assertIsNone(self.widget._execute_action({"type": "text", "target": ""}))

    def test_page_actions_switch_pages_and_resize_the_window(self):
        deck = self.widget.deck()
        deck["pages"].append(m.new_page("둘"))
        self.widget._apply_deck(deck)
        self.assertTrue(self.widget._execute_action({"type": "page", "target": "next"}))
        self.assertEqual(self.widget.deck()["page"], 1)
        self.widget._go_to_page(0)
        self.assertEqual(self.widget.deck()["page"], 0)

    def test_toggle_keys_flip_and_persist(self):
        deck = self.widget.deck()
        key = deck["pages"][0]["keys"][0]
        key.update(
            {"mode": "toggle", "action": {"type": "command", "target": "today", "paste": False}}
        )
        self.widget._run_key(key["id"], "tap")
        self.assertTrue(self.widget.deck()["pages"][0]["keys"][0]["active"])
        self.widget.save_position()
        stored = m.deck_from_json(self.owner.settings.value(_prefixed(DATA_KEY)))
        self.assertTrue(stored["pages"][0]["keys"][0]["active"])

    def test_sticky_modifiers_join_the_next_key_then_release(self):
        with patch(f"{_MODULE}.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            self.widget._apply_template("keyboard_60")
        keys = self.widget.deck()["pages"][0]["keys"]
        shift = next(key for key in keys if key["label"] == "Shift")
        ctrl = next(key for key in keys if key["label"] == "Ctrl")
        letter = next(key for key in keys if key["label"] == "A")
        with patch(f"{_MODULE}.send_hotkey", return_value=True) as sender:
            self.widget._run_key(shift["id"], "tap")
            self.widget._run_key(ctrl["id"], "tap")
            sender.assert_not_called()
            self.assertTrue(shift["active"] and ctrl["active"])
            self.widget._run_key(letter["id"], "tap")
            sender.assert_called_once_with("Shift+Ctrl+A")
        self.assertFalse(shift["active"] or ctrl["active"])
        with patch(f"{_MODULE}.send_hotkey", return_value=True) as sender:
            self.widget._run_key(letter["id"], "tap")
            sender.assert_called_once_with("A")

    def test_big_keyboards_shrink_to_fit_the_screen(self):
        deck = m.build_template_deck("keyboard_full")
        deck["unit"], deck["scale"] = 112, 220
        self.widget._apply_deck(deck)
        available = self.widget.screen().availableGeometry()
        from calendar_app.presentation.widgets.keydeck.renderer import DeckGeometry

        geometry = DeckGeometry(self.widget.deck())
        self.assertTrue(geometry.width <= available.width() or self.widget.deck()["scale"] == 60)
        self.assertLess(self.widget.deck()["scale"], 220)

    def test_hold_runs_the_secondary_action(self):
        key = self.widget.deck()["pages"][0]["keys"][0]
        key["action"] = {"type": "command", "target": "today", "paste": False}
        key["hold_action"] = {"type": "command", "target": "sync_google", "paste": False}
        self.widget._run_key(key["id"], "hold")
        self.assertEqual(self.owner.calls, ["sync_google"])

    def test_dropping_an_image_on_a_key_sets_its_insert(self):
        key = self.widget.deck()["pages"][0]["keys"][0]
        with patch(f"{_MODULE}.import_launcher_asset", return_value="C:/managed/art.png"):
            self.widget._on_image_dropped(key["id"], "C:/Users/me/art.png")
        self.assertEqual(key["insert"]["kind"], "image")
        self.assertEqual(key["insert"]["path"], "C:/managed/art.png")

    def test_dropping_files_adds_keys_but_skips_scripts(self):
        before = len(self.widget.deck()["pages"][0]["keys"])
        with tempfile.TemporaryDirectory() as tmpdir:
            doc = Path(tmpdir) / "report.docx"
            doc.write_text("x", encoding="utf-8", errors="strict")
            script = Path(tmpdir) / "evil.bat"
            script.write_text("x", encoding="utf-8", errors="strict")
            self.widget._on_targets_dropped(
                [("app", str(doc)), ("app", str(script)), ("url", "https://calendar.google.com")]
            )
        keys = self.widget.deck()["pages"][0]["keys"]
        self.assertEqual(len(keys), before + 2)
        self.assertEqual(keys[-2]["label"], "report")
        self.assertEqual(keys[-1]["label"], "calendar.google.com")
        self.assertFalse(m.has_overlaps(keys))

    def test_resizing_zooms_the_deck_instead_of_fitting_fonts(self):
        self.widget._fit_font_to_size(900, 700, live=True)
        self.assertEqual(self.widget.width(), 900)
        self.widget._fit_font_to_size(900, 700)
        self.assertGreater(self.widget.deck()["scale"], 100)
        self.assertIsNone(self.widget._normalized_fixed_dimension("fixed_w"))
        self.widget._action_reset_size()
        self.assertEqual(self.widget.deck()["scale"], 100)

    def test_mouse_over_keys_goes_to_the_canvas_not_the_drag_handler(self):
        from PyQt6.QtTest import QTest

        canvas = self.widget._canvas
        key = self.widget.deck()["pages"][0]["keys"][1]
        center = (
            canvas.renderer.geometry.key_rect(key).center() + canvas.content_offset()
        ).toPoint()
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center)
        self.assertTrue(canvas.is_pressing())
        self.assertIsNone(self.widget._drag_offset)
        QTest.mouseRelease(
            canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center
        )
        self.assertFalse(canvas.is_pressing())

    def test_theme_and_template_menus_apply(self):
        self.widget._apply_theme("walnut_studio")
        self.assertEqual(self.widget.deck()["case"]["style"], "walnut")
        with patch(f"{_MODULE}.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            self.widget._apply_template("stream_5x3")
        self.assertEqual(len(self.widget.deck()["pages"][0]["keys"]), 15)

    def test_close_button_hides_the_deck_and_explains_how_to_restore_once(self):
        toasts = []
        self.owner.show_toast = lambda title, message: toasts.append((title, message))
        self.widget._canvas.closeRequested.emit()
        self.assertFalse(self.widget.isVisible())
        self.assertFalse(self.widget.is_enabled())
        self.assertEqual(len(toasts), 1)
        self.widget.set_enabled(True)
        self.widget.hide_from_user()
        self.assertEqual(len(toasts), 1)

    def test_close_event_flushes_pending_edits_and_never_vetoes(self):
        key = self.widget.deck()["pages"][0]["keys"][0]
        key["label"] = "닫기 전 저장"
        self.widget._schedule_save()
        self.assertTrue(self.widget.close())
        stored = m.deck_from_json(self.owner.settings.value(_prefixed(DATA_KEY)))
        self.assertEqual(stored["pages"][0]["keys"][0]["label"], "닫기 전 저장")
        self.assertFalse(self.widget._canvas._active)

    def test_deferred_key_runs_are_dropped_during_app_exit(self):
        key = self.widget.deck()["pages"][0]["keys"][0]
        key["action"] = {"type": "command", "target": "today", "paste": False}
        self._app.setProperty(EXITING_PROPERTY, True)
        self.widget._run_key(key["id"], "tap")
        self.assertEqual(self.owner.calls, [])

    def test_open_studio_is_closed_without_prompt_when_the_app_exits(self):
        from calendar_app.presentation.widgets.keydeck.studio import KeyDeckStudioDialog

        studio = KeyDeckStudioDialog(self.widget.deck(), self.widget)
        studio.show()
        studio._mark_dirty()
        self.widget._studio = studio
        self._app.setProperty(EXITING_PROPERTY, True)
        with patch.object(studio, "_ask_unsaved_changes") as ask:
            self.widget._set_runtime_active(False)
            ask.assert_not_called()
        self.assertFalse(studio.isVisible())
        self.assertIsNone(self.widget._studio)

    def test_exit_action_uses_the_main_window_exit_flow(self):
        calls = []
        self.owner.request_app_exit = lambda: calls.append("exit")
        self.widget._request_app_exit()
        self._app.processEvents()
        self.assertEqual(calls, ["exit"])

    def test_studio_cannot_open_during_exit(self):
        self._app.setProperty(EXITING_PROPERTY, True)
        with patch(
            "calendar_app.presentation.widgets.keydeck.studio.KeyDeckStudioDialog.exec"
        ) as execute:
            self.widget._open_settings()
            execute.assert_not_called()

    def test_hiding_pauses_the_canvas(self):
        self.widget._set_runtime_active(False)
        self.assertFalse(self.widget._canvas._active)
        self.widget._set_runtime_active(True)
        self.assertTrue(self.widget._canvas._active)


if __name__ == "__main__":
    unittest.main()
