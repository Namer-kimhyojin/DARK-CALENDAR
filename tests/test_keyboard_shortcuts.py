import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDockWidget, QMainWindow, QWidget

from calendar_app.infrastructure.runtime.keyboard_shortcuts import (
    get_key,
    register_all,
    search_shortcut_guide_entries,
)


class _ShortcutHost(QMainWindow):
    def __init__(self):
        super().__init__()
        self._global_shortcuts = []
        self.command_palette_calls = 0
        self.layout_calls = []

        self.left_dock = QDockWidget("Left", self)
        self.center_dock = QDockWidget("Center", self)
        self.routine_dock = QDockWidget("Routine", self)
        self.directive_dock = QDockWidget("Directive", self)
        for dock in (self.left_dock, self.center_dock, self.routine_dock, self.directive_dock):
            dock.setWidget(QWidget())

    def show_command_palette(self):
        self.command_palette_calls += 1

    def open_task_dialog(self):
        pass

    def open_routine_add_dialog(self):
        pass

    def open_directive_dialog(self):
        pass

    def open_checklist_manager(self):
        pass

    def jump_to_today(self):
        pass

    def prev_day(self):
        pass

    def next_day(self):
        pass

    def toggle_focus_mode(self):
        pass

    def toggle_focus_pause(self):
        pass

    def toggle_magnet_mode(self):
        pass

    def toggle_top_bar(self):
        pass

    def toggle_calendar_toolbar(self):
        pass

    def toggle_fullscreen(self):
        pass

    def toggle_widget_mode_panel(self):
        pass

    def auto_assign_color_tags_to_selection(self):
        pass

    def toggle_overlay(self):
        pass

    def restore_window_to_safe_area(self):
        pass

    def move_to_next_monitor(self):
        pass

    def show_shortcut_guide(self):
        pass

    def clear_task_selection(self):
        pass

    def open_work_management_dialog(self, start_tab=None):
        pass

    def apply_layout_preset(self, idx):
        self.layout_calls.append(idx)


class KeyboardShortcutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_register_all_attaches_ctrl_k_to_main_window(self):
        host = _ShortcutHost()
        self.addCleanup(host.close)

        register_all(host)

        ctrl_k_shortcuts = [sc for sc in host._global_shortcuts if sc.key().toString() == "Ctrl+K"]

        self.assertEqual(1, len(ctrl_k_shortcuts))
        self.assertIs(ctrl_k_shortcuts[0].parent(), host)
        self.assertEqual(
            Qt.ShortcutContext.ApplicationShortcut,
            ctrl_k_shortcuts[0].context(),
        )

        ctrl_k_shortcuts[0].activated.emit()
        self.assertEqual(1, host.command_palette_calls)

    def test_register_all_replaces_existing_shortcuts_instead_of_duplication(self):
        host = _ShortcutHost()
        self.addCleanup(host.close)

        register_all(host)
        first_count = len(host._global_shortcuts)

        register_all(host)
        second_count = len(host._global_shortcuts)

        self.assertEqual(first_count, second_count)

    def test_register_all_exposes_widget_mode_and_all_layout_presets(self):
        host = _ShortcutHost()
        self.addCleanup(host.close)

        register_all(host)
        keys = {sc.key().toString() for sc in host._global_shortcuts}

        self.assertIn("F12", keys)
        for expected in (
            "Ctrl+Shift+1",
            "Ctrl+Shift+2",
            "Ctrl+Shift+3",
            "Ctrl+Shift+4",
            "Ctrl+Shift+5",
        ):
            self.assertIn(expected, keys)

    def test_help_search_matches_alias_and_new_shortcuts(self):
        focus_results = [entry["id"] for entry in search_shortcut_guide_entries("Ctrl+Space")]
        widget_results = [entry["id"] for entry in search_shortcut_guide_entries("위젯")]

        self.assertIn("focus_mode", focus_results)
        self.assertIn("widget_mode", widget_results)
        self.assertEqual("F12", get_key("widget_mode"))

    def test_layout_shortcuts_trigger_preset_handlers_with_real_key_input(self):
        host = _ShortcutHost()
        self.addCleanup(host.close)

        register_all(host)
        host.show()
        self._app.processEvents()

        for key in (
            Qt.Key.Key_1,
            Qt.Key.Key_2,
            Qt.Key.Key_3,
            Qt.Key.Key_4,
            Qt.Key.Key_5,
        ):
            QTest.keyClick(
                host,
                key,
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
            )
            self._app.processEvents()

        self.assertEqual([0, 1, 2, 3, 4], host.layout_calls)


if __name__ == "__main__":
    unittest.main()
