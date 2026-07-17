# -*- coding: utf-8 -*-
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from calendar_app.presentation.main_window.action_handlers_gcal import GCalActionsMixin
from calendar_app.presentation.main_window.refresh_scheduler import RefreshSchedulerMixin
from calendar_app.presentation.main_window.theme_actions import _set_stylesheet_if_changed


class _StyleTarget:
    def __init__(self):
        self.value = ""
        self.apply_count = 0

    def styleSheet(self):
        return self.value

    def setStyleSheet(self, value):
        self.value = value
        self.apply_count += 1


class _FakeSettings:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def value(self, key, default=None, type=None):
        value = self.values.get(key, default)
        return type(value) if type is not None and value is not None else value


class _SyncStatusHost(GCalActionsMixin, QWidget):
    def __init__(self):
        super().__init__()
        self.settings = _FakeSettings({"gcal_enabled": "false"})
        self.gcal_sync = None
        self.sync_status_lbl = QLabel(self)
        self._gcal_sync_issue_count = 7


class _DataConsumer:
    def __init__(self):
        self.refresh_count = 0

    def refresh_data(self):
        self.refresh_count += 1


class _RefreshHost(RefreshSchedulerMixin, QWidget):
    def __init__(self):
        super().__init__()
        self.loads = []
        self._unified_widget_controller = _DataConsumer()

    def load_left_panel(self, force=False):
        self.loads.append(("left", force))

    def load_center_panel(self, force=False):
        self.loads.append(("center", force))

    def load_right_panel(self, force=False):
        self.loads.append(("right", force))


class ThemeRuntimeOptimizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_stylesheet_helper_skips_identical_value(self):
        target = _StyleTarget()

        self.assertTrue(_set_stylesheet_if_changed(target, "QWidget { color: red; }"))
        self.assertFalse(_set_stylesheet_if_changed(target, "QWidget { color: red; }"))
        self.assertTrue(_set_stylesheet_if_changed(target, "QWidget { color: blue; }"))
        self.assertEqual(target.apply_count, 2)

    def test_theme_sync_refresh_uses_cached_issue_count(self):
        host = _SyncStatusHost()
        self.addCleanup(host.close)
        with (
            patch(
                "calendar_app.infrastructure.db.task_repo.count_unified_task_gcal_errors"
            ) as task_errors,
            patch(
                "calendar_app.infrastructure.db.task_repo.count_gcal_delete_queue_errors"
            ) as delete_errors,
            patch(
                "calendar_app.infrastructure.db.task_repo.count_gcal_sync_conflicts"
            ) as conflicts,
        ):
            host.refresh_sync_status_theme()

        task_errors.assert_not_called()
        delete_errors.assert_not_called()
        conflicts.assert_not_called()
        self.assertEqual(host._gcal_sync_issue_count, 7)

    def test_theme_panel_refresh_does_not_notify_data_consumer(self):
        host = _RefreshHost()
        self.addCleanup(host.close)
        host.schedule_panel_refresh(
            left=True,
            center=True,
            right=True,
            notify_data_consumers=False,
        )

        host._flush_scheduled_refresh()
        host._ui_refresh_timer.stop()

        self.assertEqual(
            host.loads,
            [("left", False), ("center", False), ("right", False)],
        )
        self.assertEqual(host._unified_widget_controller.refresh_count, 0)

    def test_data_refresh_request_wins_when_coalesced_with_theme_refresh(self):
        host = _RefreshHost()
        self.addCleanup(host.close)
        host.schedule_panel_refresh(left=True, notify_data_consumers=False)
        host.schedule_panel_refresh(center=True, notify_data_consumers=True)

        host._flush_scheduled_refresh()
        host._ui_refresh_timer.stop()

        self.assertEqual(host.loads, [("left", False), ("center", False)])
        self.assertEqual(host._unified_widget_controller.refresh_count, 1)


if __name__ == "__main__":
    unittest.main()
