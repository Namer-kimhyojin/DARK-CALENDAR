import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QWidget

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
            host.open_task_dialog(False)

        self.assertEqual([], host.modify_calls)
        self.assertIsNotNone(_FakeDialog.last_kwargs)
        self.assertIsNone(_FakeDialog.last_kwargs["initial_date"])
        self.assertIsNone(_FakeDialog.last_kwargs["task_type"])

    def test_open_task_dialog_still_routes_plain_int_to_modify_dialog(self):
        host = _DialogHost()
        self.addCleanup(host.close)

        with patch(
            "calendar_app.presentation.dialogs.task_dialog_unified.UnifiedTaskDialog",
            _FakeDialog,
        ):
            host.open_task_dialog(123)

        self.assertEqual([(123, 0)], host.modify_calls)


if __name__ == "__main__":
    unittest.main()
