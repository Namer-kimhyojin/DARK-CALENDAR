import os
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QSettings
from PyQt6.QtWidgets import QApplication, QWidget

from calendar_app.infrastructure.db import database_unified, search_repo, task_repo
from calendar_app.presentation.main_window.app_window import OverlayApp
from calendar_app.presentation.widgets.command_palette import CommandPalette
from tests.support import TemporaryDatabaseTestCase


class _PaletteHost(QWidget):
    _method_names = {
        "open_task_dialog",
        "open_routine_add_dialog",
        "open_directive_dialog",
        "open_checklist_manager",
        "open_work_management_dialog",
        "jump_to_today",
        "prev_day",
        "next_day",
        "toggle_focus_mode",
        "toggle_focus_pause",
        "open_focus_log_dialog",
        "open_pomodoro_settings_dialog",
        "toggle_top_bar",
        "toggle_calendar_toolbar",
        "toggle_fullscreen",
        "toggle_widget_mode_panel",
        "open_widget_manager",
        "open_schedule_widget_panel",
        "open_work_widget_panel",
        "open_all_widget_panels",
        "change_text_theme",
        "set_system_default_theme",
        "open_panel_background_color_dialog",
        "open_label_settings_dialog",
        "open_away_settings_dialog",
        "open_font_settings_dialog",
        "sync_google_calendar",
        "open_gcal_settings_dialog",
        "open_gcal_sync_issues_dialog",
        "apply_layout_preset",
        "toggle_lock_mode",
        "toggle_magnet_mode",
        "toggle_idle_lock",
        "restore_window_to_safe_area",
        "move_to_next_monitor",
        "toggle_autostart",
        "open_language_settings_dialog",
        "show_shortcut_guide",
        "request_app_exit",
        "open_modify_task_dialog",
    }

    def __init__(self):
        super().__init__()
        self.settings = QSettings("CodexTests", "CommandPaletteBehavior")
        self.settings.clear()
        self.command_calls = []
        self.preset_manager = types.SimpleNamespace(
            _save_with_prompt=lambda: self.command_calls.append(("save_layout", (), {}))
        )

    def __getattr__(self, name):
        if name in self._method_names:

            def _recorder(*args, **kwargs):
                self.command_calls.append((name, args, kwargs))

            return _recorder
        raise AttributeError(name)


class _ActionHost:
    def __init__(self):
        self.current_date = QDate(2026, 4, 1)
        self.modify_calls = []
        self.directive_calls = []
        self.refresh_calls = []
        self.toast_calls = []

    def open_modify_task_dialog(self, task_id, tab_index=0):
        self.modify_calls.append((task_id, tab_index))

    def open_directive_dialog(self, task_id=None, checked=False):
        self.directive_calls.append(task_id)

    def schedule_panel_refresh(self, left=False, center=False, right=False):
        self.refresh_calls.append((left, center, right))

    def show_toast(self, title, message):
        self.toast_calls.append((title, message))


class CommandPaletteTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def _insert_directive(self, content: str, deadline: str) -> int:
        conn = database_unified.db_manager.get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO task_directive (content, receiver_name, deadline, status, priority, memo) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (content, "Team", deadline, "in_progress", "normal", "Follow-up"),
        )
        conn.commit()
        return int(cur.lastrowid)

    def test_palette_record_prefix_filters_to_existing_items(self):
        task_repo.create_unified_task(
            {
                "name": "Alpha Review",
                "type": "schedule",
                "deadline": "2026-04-04 10:00:00",
            }
        )
        self._insert_directive("Alpha Directive", "2026-04-05 11:00:00")

        host = _PaletteHost()
        self.addCleanup(host.close)
        palette = CommandPalette(parent=host)
        self.addCleanup(palette.close)

        palette._on_search_changed("/alpha")

        self.assertTrue(palette._result_entries)
        self.assertTrue(all(entry["kind"] == "record" for entry in palette._result_entries))
        result_ids = {entry["id"] for entry in palette._result_entries}
        self.assertIn("task:1", result_ids)
        self.assertIn("directive:1", result_ids)

    def test_palette_command_prefix_filters_to_commands(self):
        host = _PaletteHost()
        self.addCleanup(host.close)
        palette = CommandPalette(parent=host)
        self.addCleanup(palette.close)

        palette._on_search_changed(">focus")

        self.assertTrue(palette._result_entries)
        self.assertTrue(all(entry["kind"] == "command" for entry in palette._result_entries))
        self.assertIn("toggle_focus_mode", [entry["id"] for entry in palette._result_entries])

    def test_palette_create_mode_emits_nlp_command(self):
        host = _PaletteHost()
        self.addCleanup(host.close)
        palette = CommandPalette(parent=host)
        self.addCleanup(palette.close)

        emitted = []
        palette.execute_command.connect(lambda cmd_id, params: emitted.append((cmd_id, params)))

        palette._on_search_changed("+tomorrow planning 3pm")

        self.assertTrue(palette._result_entries)
        self.assertEqual("create", palette._result_entries[0]["kind"])
        palette._dispatch_entry(palette._result_entries[0])

        self.assertEqual(1, len(emitted))
        self.assertEqual("create_task_nlp", emitted[0][0])
        self.assertEqual("planning", emitted[0][1]["title"].casefold())
        self.assertTrue(emitted[0][1]["time"].startswith("15:00"))

    def test_handle_palette_command_creates_schedule_from_nlp_payload(self):
        host = _ActionHost()

        OverlayApp.handle_palette_command(
            host,
            "create_task_nlp",
            {"title": "Quarterly Planning", "date": "2026-04-06", "time": "14:30"},
        )

        rows = search_repo.search_unified_tasks("Quarterly")
        self.assertEqual(1, len(rows))
        self.assertEqual("2026-04-06 14:30:00", rows[0]["deadline"])
        self.assertTrue(host.refresh_calls)
        self.assertTrue(host.toast_calls)

    def test_handle_palette_command_opens_records_and_jumps_date(self):
        host = _ActionHost()

        OverlayApp.handle_palette_command(host, "open_task_record", {"task_id": 42})
        OverlayApp.handle_palette_command(host, "open_directive_record", {"directive_id": 77})
        OverlayApp.handle_palette_command(host, "jump_to_date", {"date": "2026-04-08"})

        self.assertEqual([(42, 0)], host.modify_calls)
        self.assertEqual([77], host.directive_calls)
        self.assertEqual("2026-04-08", host.current_date.toString("yyyy-MM-dd"))
        self.assertEqual((True, True, True), host.refresh_calls[-1])


if __name__ == "__main__":
    unittest.main()
