# -*- coding: utf-8 -*-
"""Directives as focus targets, and the OS-wide show/hide hotkey (2026-11-13)."""

import ctypes
import logging
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QEvent, QSettings
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from calendar_app.application import focus_usecases
from calendar_app.infrastructure.db import database_unified, legacy_focus_repo
from calendar_app.infrastructure.runtime import infra_wiring, keyboard_shortcuts, win32_input
from calendar_app.presentation import focus_mode
from calendar_app.presentation.dialogs import focus_task_selector
from calendar_app.presentation.main_window.action_handlers import ActionHandlersMixin
from tests.support import TemporaryDatabaseTestCase


def _qt_app():
    return QApplication.instance() or QApplication([])


class _FocusRepo:
    def __init__(self, *, tasks_by_date=None, incomplete=None, directives=None, urgent=None):
        self.tasks_by_date = tasks_by_date or {}
        self.incomplete = list(incomplete or [])
        self.directives = list(directives or [])
        self.urgent = urgent or (None, None)
        self.inserted = []

    def get_tasks_by_date(self, date_str):
        return list(self.tasks_by_date.get(date_str, []))

    def get_incomplete_tasks(self):
        return list(self.incomplete)

    def get_recent_directives(self, limit=200):
        return list(self.directives[:limit])

    def get_most_urgent_pending_task(self, today_str):
        return self.urgent

    def insert_worklog_entry(self, task_id, elapsed_secs, task_type="schedule"):
        self.inserted.append((task_id, elapsed_secs, task_type))
        return True


def _task(task_id, name, deadline, *, done=False, priority="normal"):
    return {
        "id": task_id,
        "name": name,
        "priority": priority,
        "deadline": deadline,
        "type": "schedule",
        "is_completed": done,
    }


class DirectiveFocusCandidateTests(unittest.TestCase):
    def test_today_and_directives_lists_open_directives_with_their_kind(self):
        repo = _FocusRepo(
            tasks_by_date={
                "2026-04-02": [
                    _task(12, "Today task", "2026-04-02 09:00:00"),
                    _task(13, "Finished task", "2026-04-02 10:00:00", done=True),
                ]
            },
            directives=[
                (12, "Directive twelve", "pending", "", "2026-04-05 10:00:00", "", None),
                (14, "Finished directive", "done", "", "2026-04-03 10:00:00", "", None),
                (15, "Past directive", "pending", "", "2026-04-01 10:00:00", "", None),
            ],
        )

        items = focus_usecases.get_filtered_focus_tasks(repo, "today_and_directives", "2026-04-02")

        self.assertEqual(
            [
                (item["id"], item["name"], focus_usecases.focus_target_kind(item.get("type")))
                for item in items
            ],
            [(12, "Today task", "schedule"), (12, "Directive twelve", "directive")],
        )

    def test_all_filter_offers_tasks_and_directives(self):
        repo = _FocusRepo(
            incomplete=[_task(3, "Soon task", "2026-04-03 09:00:00")],
            directives=[(3, "Soon directive", "in_progress", "", "", "", None)],
        )

        items = focus_usecases.get_filtered_focus_tasks(repo, "all", "2026-04-02")

        self.assertEqual(
            [(item["name"], item["type"]) for item in items],
            [("Soon task", "schedule"), ("Soon directive", "directive")],
        )

    def test_persist_focus_log_records_the_target_kind(self):
        repo = _FocusRepo()

        self.assertTrue(focus_usecases.persist_focus_log(repo, 12, 300, task_type="directive"))
        self.assertTrue(focus_usecases.persist_focus_log(repo, 12, 60))
        self.assertTrue(focus_usecases.persist_focus_log(repo, 12, 30, task_type="routine"))

        self.assertEqual(
            repo.inserted, [(12, 300, "directive"), (12, 60, "schedule"), (12, 30, "schedule")]
        )

    def test_auto_pick_never_falls_back_to_a_directive(self):
        repo = _FocusRepo(urgent=(None, None))

        task_id, task_name = focus_usecases.select_auto_focus_task(
            repo,
            "2026-04-02",
            fallback_tasks=[
                {"id": 5, "name": "Directive five", "deadline": "", "type": "directive"},
                {"id": 6, "name": "Task six", "deadline": "", "type": "schedule"},
            ],
        )

        self.assertEqual((task_id, task_name), (6, "Task six"))


class DirectiveFocusStorageTests(TemporaryDatabaseTestCase):
    """A directive that shares a numeric id with a task keeps its own focus time."""

    SHARED_ID = 41

    def setUp(self):
        super().setUp()
        self.qt_app = _qt_app()
        conn = database_unified.db_manager.get_connection()
        conn.execute(
            "INSERT INTO unified_task (id, name, type, status) VALUES (?, ?, 'schedule', 'pending')",
            (self.SHARED_ID, "Task forty-one"),
        )
        conn.execute(
            "INSERT INTO task_directive (id, content, status) VALUES (?, ?, 'in_progress')",
            (self.SHARED_ID, "Directive forty-one"),
        )
        conn.execute(
            "INSERT INTO task_checklist_link (owner_type, owner_id, item_text, item_order) "
            "VALUES ('schedule', ?, 'Task step', 0)",
            (self.SHARED_ID,),
        )
        conn.commit()

    def _focus_app(self, kind):
        app = type("App", (), {})()
        app._focus_task_id = self.SHARED_ID
        app._focus_task_type = kind
        app._focus_sessions_saved = 0
        app._focus_saved_secs = 0
        app.show_toast = MagicMock()
        return app

    def _task_snapshot(self):
        conn = database_unified.db_manager.get_connection()
        task = conn.execute(
            "SELECT name, status, is_completed FROM unified_task WHERE id=?", (self.SHARED_ID,)
        ).fetchone()
        steps = conn.execute(
            "SELECT item_text, is_completed FROM task_checklist_link WHERE owner_id=?",
            (self.SHARED_ID,),
        ).fetchall()
        return tuple(task), [tuple(step) for step in steps]

    def test_directive_focus_time_is_stored_and_listed_against_the_directive(self):
        before = self._task_snapshot()

        focus_mode._persist_completed_pomodoro_focus(self._focus_app("directive"), 300)
        focus_mode._persist_completed_pomodoro_focus(self._focus_app("schedule"), 120)

        conn = database_unified.db_manager.get_connection()
        rows = conn.execute(
            "SELECT task_id, task_type, elapsed_secs FROM worklog ORDER BY id"
        ).fetchall()
        self.assertEqual(
            [tuple(row) for row in rows],
            [(self.SHARED_ID, "directive", 300), (self.SHARED_ID, "schedule", 120)],
        )

        snapshot = focus_usecases.get_focus_history_snapshot(legacy_focus_repo, limit=10)
        listed = sorted(
            (entry.task_type, entry.task_name, entry.elapsed_secs) for entry in snapshot.entries
        )
        self.assertEqual(
            listed,
            [("directive", "Directive forty-one", 300), ("schedule", "Task forty-one", 120)],
        )
        self.assertEqual(self._task_snapshot(), before)

    def test_directive_focus_shows_no_task_checklist(self):
        host = QWidget()
        self.addCleanup(host.deleteLater)
        layout = QVBoxLayout(host)

        focus_mode._build_focus_checklist_panel(self._focus_app("directive"), layout)
        self.assertEqual(layout.count(), 0)

        focus_mode._build_focus_checklist_panel(self._focus_app("schedule"), layout)
        self.assertEqual(layout.count(), 1)


class _Selector:
    def __init__(self, selection, kind=None):
        self._selection = selection
        if kind is not None:
            self.get_selected_task_type = lambda: kind

    def get_selected_task(self):
        return self._selection


class FocusSelectionKindTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = _qt_app()

    def _dialog(self, items):
        with patch.object(
            focus_task_selector.focus_usecases, "get_filtered_focus_tasks", return_value=items
        ):
            dialog = focus_task_selector.FocusTaskSelectorDialog(QDate(2026, 4, 2))
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_selector_defaults_to_today_and_directives_and_keeps_the_kind(self):
        dialog = self._dialog(
            [
                _task(7, "Task seven", "2026-04-02 09:00:00"),
                {"id": 7, "name": "Directive seven", "deadline": "", "type": "directive"},
            ]
        )

        self.assertEqual(
            dialog.filter_group.checkedButton().property("filter"), "today_and_directives"
        )
        dialog.task_list.setCurrentRow(1)
        dialog.on_task_selected()
        self.assertEqual(dialog.get_selected_task(), (7, "Directive seven"))
        self.assertEqual(dialog.get_selected_task_type(), "directive")

        dialog.task_list.setCurrentRow(0)
        dialog.on_task_selected()
        self.assertEqual(dialog.get_selected_task(), (7, "Task seven"))
        self.assertEqual(dialog.get_selected_task_type(), "schedule")

    def test_auto_pick_selects_a_task(self):
        dialog = self._dialog([])
        with patch.object(
            focus_task_selector.focus_usecases, "select_auto_focus_task", return_value=(3, "Pick")
        ):
            dialog.on_auto_select()

        self.assertEqual(dialog.get_selected_task(), (3, "Pick"))
        self.assertEqual(dialog.get_selected_task_type(), "schedule")

    def test_focus_session_takes_the_selected_kind(self):
        app = type("App", (), {})()

        name = focus_mode._apply_focus_selection(app, _Selector((7, "Directive"), "directive"))
        self.assertEqual(
            (app._focus_task_id, app._focus_task_type, name), (7, "directive", "Directive")
        )

        focus_mode._apply_focus_selection(app, _Selector((8, "Task")))
        self.assertEqual((app._focus_task_id, app._focus_task_type), (8, "schedule"))

        focus_mode._reset_focus_runtime_refs(app)
        self.assertIsNone(app._focus_task_type)


class Win32HotkeyParsingTests(unittest.TestCase):
    def test_parse_hotkey_maps_qt_key_text_to_win32_codes(self):
        ctrl = win32_input.MOD_CONTROL | win32_input.MOD_NOREPEAT
        self.assertEqual(win32_input.parse_hotkey("Ctrl+F1"), (ctrl, 0x70))
        self.assertEqual(
            win32_input.parse_hotkey("Ctrl+Alt+Shift+Left"),
            (ctrl | win32_input.MOD_ALT | win32_input.MOD_SHIFT, 0x25),
        )
        self.assertEqual(win32_input.parse_hotkey("Ctrl+Alt+K"), (ctrl | win32_input.MOD_ALT, 0x4B))
        self.assertEqual(win32_input.parse_hotkey("Ctrl+="), (ctrl, 0xBB))
        self.assertIsNone(win32_input.parse_hotkey("Ctrl+NoSuchKey"))
        self.assertIsNone(win32_input.parse_hotkey(""))

    @unittest.skipUnless(sys.platform == "win32", "Win32 MSG layout")
    def test_hotkey_id_is_read_from_a_wm_hotkey_message_only(self):
        from ctypes import wintypes

        msg = wintypes.MSG()
        msg.message = win32_input.WM_HOTKEY
        msg.wParam = 0x0A1C
        self.assertEqual(win32_input.hotkey_id_from_message(ctypes.addressof(msg)), 0x0A1C)
        msg.message = 0x0100  # WM_KEYDOWN
        self.assertIsNone(win32_input.hotkey_id_from_message(ctypes.addressof(msg)))
        self.assertIsNone(win32_input.hotkey_id_from_message(0))


class _HotkeyHost(QMainWindow):
    def __init__(self):
        super().__init__()
        self._global_shortcuts = []
        self._global_hotkeys = None
        self.toggle_calls = 0
        self.toasts = []
        self.settings = QSettings("kimhyojin", "Dark Calendar")

    def toggle_overlay(self):
        self.toggle_calls += 1

    def show_toast(self, title, message):
        self.toasts.append((title, message))


class _FakeWin32Hotkeys:
    """Records RegisterHotKey/UnregisterHotKey calls; nothing reaches the OS."""

    def __init__(self, *, fail_with=None):
        self.fail_with = fail_with
        self.registered = {}
        self.calls = []

    def register(self, hwnd, hotkey_id, modifiers, vk):
        self.calls.append(("register", hotkey_id, modifiers, vk))
        if self.fail_with:
            return False, self.fail_with
        self.registered[hotkey_id] = (modifiers, vk)
        return True, 0

    def unregister(self, hwnd, hotkey_id):
        self.calls.append(("unregister", hotkey_id))
        return self.registered.pop(hotkey_id, None) is not None


class GlobalShowHideHotkeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = _qt_app()

    def setUp(self):
        self.win32 = _FakeWin32Hotkeys()
        for target, attribute, value in (
            (keyboard_shortcuts, "_native_hotkeys_supported", lambda: True),
            (win32_input, "register_hotkey", lambda *a: self.win32.register(*a)),
            (win32_input, "unregister_hotkey", lambda *a: self.win32.unregister(*a)),
        ):
            patcher = patch.object(target, attribute, side_effect=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _host(self):
        host = _HotkeyHost()

        def _dispose():
            keyboard_shortcuts.release_global_hotkeys(host)
            for shortcut in host._global_shortcuts:
                shortcut.setEnabled(False)
            host.deleteLater()
            self.qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

        self.addCleanup(_dispose)
        return host

    @staticmethod
    def _keys(host):
        return [shortcut.key().toString() for shortcut in host._global_shortcuts]

    def test_show_hide_is_registered_os_wide_instead_of_in_app(self):
        host = self._host()

        infra_wiring.init_shortcuts(host)

        hotkey_id = keyboard_shortcuts.GLOBAL_HOTKEY_IDS["show_hide"]
        self.assertEqual(
            self.win32.registered,
            {hotkey_id: win32_input.parse_hotkey(keyboard_shortcuts.get_key("show_hide"))},
        )
        self.assertNotIn(keyboard_shortcuts.get_key("show_hide"), self._keys(host))
        self.assertIn("Ctrl+K", self._keys(host))
        self.assertEqual(host.toasts, [])

    def test_show_hide_key_avoids_office_ribbon_ctrl_f1(self):
        key = keyboard_shortcuts.get_key("show_hide")
        self.assertEqual(key, "Ctrl+Alt+Shift+F1")
        all_keys = [entry["key"] for entry in keyboard_shortcuts.SHORTCUTS]
        self.assertEqual(all_keys.count(key), 1)
        self.assertEqual(
            win32_input.parse_hotkey(key),
            (
                win32_input.MOD_CONTROL
                | win32_input.MOD_ALT
                | win32_input.MOD_SHIFT
                | win32_input.MOD_NOREPEAT,
                0x70,
            ),
        )

    def test_wm_hotkey_message_toggles_the_window_once(self):
        host = self._host()
        keyboard_shortcuts.register_app_shortcuts(host)
        hotkey_id = keyboard_shortcuts.GLOBAL_HOTKEY_IDS["show_hide"]
        window = host._global_hotkeys.window

        with patch.object(win32_input, "hotkey_id_from_message", return_value=hotkey_id):
            handled = window.nativeEvent(b"windows_generic_MSG", None)
        with patch.object(win32_input, "hotkey_id_from_message", return_value=None):
            ignored = window.nativeEvent(b"windows_generic_MSG", None)
        self.qt_app.processEvents()

        self.assertTrue(handled[0])
        self.assertFalse(ignored[0])
        self.assertEqual(host.toggle_calls, 1)

    def test_taken_key_keeps_in_app_shortcut_and_notifies_once(self):
        self.win32.fail_with = 1409  # ERROR_HOTKEY_ALREADY_REGISTERED
        host = self._host()

        with self.assertLogs(keyboard_shortcuts.logger, level=logging.WARNING) as logs:
            keyboard_shortcuts.register_app_shortcuts(host)
            keyboard_shortcuts.register_app_shortcuts(host)

        self.assertIn(keyboard_shortcuts.get_key("show_hide"), self._keys(host))
        self.assertEqual(self._keys(host).count(keyboard_shortcuts.get_key("show_hide")), 1)
        self.assertEqual(len(host.toasts), 1)
        self.assertIn(keyboard_shortcuts.get_key("show_hide"), host.toasts[0][1])
        self.assertTrue(
            any(
                keyboard_shortcuts.get_key("show_hide") in line and "1409" in line
                for line in logs.output
            )
        )

    def test_taken_key_notice_is_not_repeated_on_later_runs(self):
        self.win32.fail_with = 1409
        first = self._host()
        with self.assertLogs(keyboard_shortcuts.logger, level=logging.WARNING):
            keyboard_shortcuts.register_app_shortcuts(first)
        later_run = self._host()
        with self.assertLogs(keyboard_shortcuts.logger, level=logging.WARNING):
            keyboard_shortcuts.register_app_shortcuts(later_run)
        self.assertEqual((len(first.toasts), len(later_run.toasts)), (1, 0))

        with patch.dict(keyboard_shortcuts._KEY_BY_ID, {"show_hide": "Ctrl+Alt+F2"}):
            new_key = self._host()
            with self.assertLogs(keyboard_shortcuts.logger, level=logging.WARNING):
                keyboard_shortcuts.register_app_shortcuts(new_key)
        self.assertEqual(len(new_key.toasts), 1)

    def test_changed_key_replaces_the_os_registration(self):
        host = self._host()
        keyboard_shortcuts.register_app_shortcuts(host)
        hotkey_id = keyboard_shortcuts.GLOBAL_HOTKEY_IDS["show_hide"]
        keyboard_shortcuts.register_app_shortcuts(host)
        self.assertEqual([call[0] for call in self.win32.calls], ["register"])

        with patch.dict(keyboard_shortcuts._KEY_BY_ID, {"show_hide": "Ctrl+Alt+F2"}):
            keyboard_shortcuts.register_app_shortcuts(host)

        self.assertEqual(
            self.win32.calls[1:],
            [
                ("unregister", hotkey_id),
                (
                    "register",
                    hotkey_id,
                    win32_input.MOD_CONTROL | win32_input.MOD_ALT | win32_input.MOD_NOREPEAT,
                    0x71,
                ),
            ],
        )

    def test_release_unregisters_and_is_idempotent(self):
        host = self._host()
        keyboard_shortcuts.register_app_shortcuts(host)

        keyboard_shortcuts.release_global_hotkeys(host)
        keyboard_shortcuts.release_global_hotkeys(host)

        self.assertEqual(self.win32.registered, {})
        self.assertEqual([call[0] for call in self.win32.calls], ["register", "unregister"])
        self.assertIsNone(host._global_hotkeys)

    def test_unsupported_platform_keeps_the_in_app_shortcut_silently(self):
        host = self._host()
        with patch.object(keyboard_shortcuts, "_native_hotkeys_supported", return_value=False):
            keyboard_shortcuts.register_app_shortcuts(host)

        self.assertEqual(self.win32.calls, [])
        self.assertIn(keyboard_shortcuts.get_key("show_hide"), self._keys(host))
        self.assertEqual(host.toasts, [])

    def test_app_shutdown_releases_global_hotkeys(self):
        class _ShutdownHost:
            _is_shutting_down = False
            _shutdown_in_progress = False
            _shutdown_complete = False
            _bg_workers = []

        host = _ShutdownHost()
        with patch.object(keyboard_shortcuts, "release_global_hotkeys") as release:
            ActionHandlersMixin.shutdown_background_workers(host, wait_ms=1)

        release.assert_called_once_with(host)


if __name__ == "__main__":
    unittest.main()
