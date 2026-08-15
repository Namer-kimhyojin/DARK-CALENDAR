# -*- coding: utf-8 -*-

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QDialog, QWidget

from calendar_app.infrastructure.google_sync.helpers import resolve_app_context
from calendar_app.presentation.dialogs.dialog_router import DialogActionsMixin


class _DialogHost(QWidget, DialogActionsMixin):
    def __init__(self):
        super().__init__()
        self.modify_calls = []
        self.refresh_calls = 0

    def open_modify_task_dialog(self, task_id, tab_index=0):
        self.modify_calls.append((task_id, tab_index))

    def schedule_panel_refresh(self, left=False, center=False):
        self.refresh_calls += 1


class _FakeDialog:
    last_kwargs = None

    def __init__(self, parent, **kwargs):
        self.parent = parent
        self.kwargs = kwargs
        _FakeDialog.last_kwargs = kwargs

    def exec(self):
        return False


class _FakeSettings:
    def __init__(self, enabled="true"):
        self.enabled = enabled

    def value(self, key, default=None):
        if key == "gcal_enabled":
            return self.enabled
        return default


class _ModifyDialog:
    result = QDialog.DialogCode.Accepted

    def __init__(self, task_id, parent):
        self.task_id = task_id
        self.parent = parent
        self.skip_post_commit_gcal_sync = False
        self.post_commit_gcal_sync_overrides = {"_previous_gcal_calendar_id": "old-cal"}

    def exec(self):
        return self.result


class _ModifyHost(QWidget, DialogActionsMixin):
    def __init__(self):
        super().__init__()
        self.settings = _FakeSettings()
        self.refresh_calls = 0

    def _refresh_all_panels(self):
        self.refresh_calls += 1


class DialogRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_open_task_dialog_ignores_checked_bool_from_qt_signals(self):
        host = _DialogHost()
        self.addCleanup(host.close)
        _FakeDialog.last_kwargs = None

        with patch(
            "calendar_app.presentation.dialogs.task_dialog_unified.UnifiedTaskDialog",
            _FakeDialog,
        ):
            result = host.open_task_dialog(False)

        self.assertEqual([], host.modify_calls)
        self.assertIsNotNone(_FakeDialog.last_kwargs)
        self.assertIsNone(_FakeDialog.last_kwargs["initial_date"])
        self.assertIsNone(_FakeDialog.last_kwargs["task_type"])
        self.assertFalse(result)

    def test_open_task_dialog_still_routes_plain_int_to_modify_dialog(self):
        host = _DialogHost()
        self.addCleanup(host.close)

        with patch(
            "calendar_app.presentation.dialogs.task_dialog_unified.UnifiedTaskDialog",
            _FakeDialog,
        ):
            host.open_task_dialog(123)

        self.assertEqual([(123, 0)], host.modify_calls)

    def test_modify_sync_is_queued_once_after_accept_with_move_context(self):
        host = _ModifyHost()
        self.addCleanup(host.close)
        task_before = {"id": 7, "type": "schedule", "calendar_id": "gcal::old"}
        task_after = {"id": 7, "type": "schedule", "calendar_id": "gcal::new"}

        with (
            patch(
                "calendar_app.presentation.dialogs.modify_task_dialog_unified.UnifiedModifyTaskDialog",
                _ModifyDialog,
            ),
            patch(
                "calendar_app.infrastructure.db.task_repo.get_unified_task",
                side_effect=[task_before, task_after],
            ),
            patch(
                "calendar_app.infrastructure.google_sync.push_queue.gcal_push_queue.enqueue"
            ) as enqueue,
        ):
            result = host.open_modify_task_dialog(7)

        self.assertEqual(result, QDialog.DialogCode.Accepted)
        self.assertEqual(host.refresh_calls, 1)
        enqueue.assert_called_once()
        queued_task = enqueue.call_args.args[1]
        self.assertEqual(queued_task["calendar_id"], "gcal::new")
        self.assertEqual(queued_task["_previous_gcal_calendar_id"], "old-cal")

    def test_focus_log_action_uses_dedicated_history_dialog(self):
        host = _DialogHost()
        self.addCleanup(host.close)

        with patch(
            "calendar_app.presentation.dialogs.focus_log_dialog.FocusLogDialog"
        ) as dialog_cls:
            host.open_focus_log_dialog()

        dialog_cls.assert_called_once_with(host)

    def test_resolve_app_context_walks_dialog_parent_chain(self):
        root = _ModifyHost()
        middle = QWidget(root)
        child = QWidget(middle)
        self.addCleanup(root.close)

        self.assertIs(resolve_app_context(child), root)


if __name__ == "__main__":
    unittest.main()
