# -*- coding: utf-8 -*-
"""Late worker notifications must not alter a closing app or crash Qt slots."""

import sqlite3
from unittest.mock import Mock

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QWidget
import pytest

from calendar_app.presentation.main_window import caldav_sync_controller as caldav
from calendar_app.presentation.main_window import outlook_sync_controller as outlook


@pytest.fixture(params=["outlook", "icloud", "naver"])
def controller(request, tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    host.schedule_panel_refresh = Mock()
    host._bg_workers = []
    service = request.param
    module = outlook if service == "outlook" else caldav
    path = tmp_path / "calendar.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE calendar(id TEXT PRIMARY KEY,type TEXT,name TEXT,color TEXT,is_active INTEGER,access_role TEXT);
        CREATE TABLE unified_task(id INTEGER PRIMARY KEY,calendar_id TEXT);
    """)
    conn.close()
    monkeypatch.setattr(module, "DB_PATH", str(path))
    ctrl = (
        module.OutlookSyncController(host)
        if service == "outlook"
        else module.CalDAVSyncController(host, service)
    )
    ctrl.timer.stop()
    if hasattr(ctrl, "startup_timer"):
        ctrl.startup_timer.stop()
    prefix = "outlook_" if service == "outlook" else "caldav_" + service + "_"
    host.settings.setValue(prefix + "account_id", "old-account")
    result = {"account": "new-account", "name": "Fixture", "home_id": "home", "calendars": []}
    yield app, host, ctrl, prefix, module, result
    host._is_shutting_down = True
    ctrl.timer.stop()
    if hasattr(ctrl, "startup_timer"):
        ctrl.startup_timer.stop()
    host.close()


def test_shutdown_ignores_late_login_result(controller):
    app, host, ctrl, prefix, module, result = controller
    host._is_shutting_down = True
    ctrl._result("login", result)
    assert host.settings.value(prefix + "account_id") == "old-account"
    host.schedule_panel_refresh.assert_not_called()


def test_shutdown_ignores_late_error(controller):
    app, host, ctrl, prefix, module, result = controller
    host._is_shutting_down = True
    ctrl._failed("network_unavailable")
    assert not host.settings.contains(prefix + "last_error")
    assert not ctrl.timer.isActive()


def test_failed_account_switch_reports_error_and_preserves_account(controller, monkeypatch):
    app, host, ctrl, prefix, module, result = controller
    monkeypatch.setattr(
        module.sqlite3, "connect", Mock(side_effect=sqlite3.OperationalError("locked"))
    )
    ctrl._result("login", result)
    assert host.settings.value(prefix + "account_id") == "old-account"
    assert ctrl.status == "operation_failed"
    assert host.settings.value(prefix + "last_error") == "operation_failed"


def test_busy_controller_rejects_duplicate_start(controller):
    app, host, ctrl, prefix, module, result = controller
    ctrl.worker = Mock()
    assert ctrl.start("sync") is False
    assert host._bg_workers == []
    ctrl.worker = None


def test_partial_failure_refreshes_committed_calendar_data(controller):
    app, host, ctrl, prefix, module, result = controller
    ctrl.worker = Mock(operation="sync")
    ctrl._failed("network_unavailable")
    host.schedule_panel_refresh.assert_called_once_with(left=True, center=True, right=True)
    ctrl.worker = None
