# -*- coding: utf-8 -*-
"""A worker launch failure must remain diagnosable and permit a later retry."""

import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QWidget
import pytest

from calendar_app.infrastructure.calendar_sync.repository import CalendarSyncRepository
from calendar_app.presentation.main_window import caldav_sync_controller as caldav
from calendar_app.presentation.main_window import calendar_sync_coordinator as common
from calendar_app.presentation.main_window import outlook_sync_controller as outlook


@pytest.fixture(params=["outlook", "icloud", "naver"])
def launch_failure(request, tmp_path, monkeypatch):
    qapp = QApplication.instance() or QApplication([])
    host = QWidget()
    host.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    host._bg_workers = []
    host.schedule_panel_refresh = Mock()
    service = request.param
    module = outlook if service == "outlook" else caldav
    worker_class = module.OutlookWorker if service == "outlook" else module.CalDAVWorker
    prefix = "outlook_" if service == "outlook" else "caldav_" + service + "_"
    account = "microsoft::fixture" if service == "outlook" else "caldav::" + service + "::fixture"
    host.settings.setValue(prefix + "account_id", account)
    host.settings.setValue(prefix + "enabled", True)
    host.settings.setValue("outlook_client_id", "12345678-1234-1234-1234-123456789abc")
    path = tmp_path / "calendar.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE calendar(id TEXT PRIMARY KEY,type TEXT,name TEXT,color TEXT,
                is_active INTEGER DEFAULT 1,access_role TEXT,is_visible INTEGER DEFAULT 1,
                is_default INTEGER DEFAULT 0,ics_url TEXT);
            CREATE TABLE unified_task(id INTEGER PRIMARY KEY,name TEXT,calendar_id TEXT,
                deadline TEXT,end_date TEXT,all_day INTEGER,description TEXT,location TEXT,
                type TEXT,gcal_dirty INTEGER,gcal_sync_mode TEXT,updated_at TEXT);
        """)
        repo = CalendarSyncRepository(conn, "outlook" if service == "outlook" else "caldav")
        repo.register(account, {"id": "remote", "name": "Fixture", "can_edit": service != "naver"})
    monkeypatch.setattr(module, "DB_PATH", str(path))
    controller = (
        module.OutlookSyncController(host)
        if service == "outlook"
        else module.CalDAVSyncController(host, service)
    )
    controller.timer.stop()
    if hasattr(controller, "startup_timer"):
        controller.startup_timer.stop()
    host._outlook_sync_controller = controller if service == "outlook" else None
    host._caldav_sync_controllers = {service: controller} if service != "outlook" else {}

    def calendars():
        with sqlite3.connect(path) as database:
            database.row_factory = sqlite3.Row
            return [dict(row) for row in database.execute("SELECT * FROM calendar")]

    from calendar_app.infrastructure.db import task_repo

    for name in (
        "count_unified_task_gcal_errors",
        "count_gcal_delete_queue_errors",
        "count_gcal_sync_conflicts",
    ):
        monkeypatch.setattr(task_repo, name, lambda: 0)
    monkeypatch.setattr(common, "TOKEN_PATH", str(tmp_path / "absent-token"))
    coordinator = common.CalendarSyncCoordinator(host, str(path), calendars)
    monkeypatch.setattr(
        worker_class, "start", Mock(side_effect=RuntimeError("synthetic launch failure"))
    )
    yield SimpleNamespace(
        host=host,
        service=service,
        controller=controller,
        prefix=prefix,
        coordinator=coordinator,
        worker_class=worker_class,
    )
    host._is_shutting_down = True
    controller.timer.stop()
    if hasattr(controller, "startup_timer"):
        controller.startup_timer.stop()
    for worker in host._bg_workers:
        worker.requestInterruption()
        worker.deleteLater()
    controller.worker = None
    host._bg_workers.clear()
    coordinator.stop()
    host.close()
    qapp.processEvents()


def test_launch_failure_clears_busy_and_allows_explicit_retry(launch_failure, monkeypatch):
    ui = launch_failure
    assert ui.controller.start("sync") is False
    assert not ui.controller.busy
    assert ui.host._bg_workers == []
    assert ui.controller.status == "operation_failed"
    assert ui.host.settings.value(ui.prefix + "last_error") == "operation_failed"
    monkeypatch.setattr(ui.worker_class, "start", lambda self: None)
    assert ui.controller.start("sync") is True
    assert ui.controller.busy


def test_common_dispatch_reports_failure_instead_of_permanent_working(launch_failure):
    ui = launch_failure
    assert ui.coordinator.sync(ui.service) == []
    state = ui.coordinator.states[ui.service]
    assert not state["busy"]
    assert state["error"] == "operation_failed"
    assert state["can_sync"]
