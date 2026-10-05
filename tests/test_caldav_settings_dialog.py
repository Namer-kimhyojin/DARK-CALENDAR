# -*- coding: utf-8 -*-
"""Service selection, credential input, conflict UI and settings isolation."""

import sqlite3
from unittest.mock import Mock

from PyQt6.QtCore import QObject, QSettings, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QLineEdit, QWidget
import pytest

from calendar_app.infrastructure.calendar_sync.repository import CalendarSyncRepository, fingerprint
from calendar_app.presentation.dialogs import caldav_settings_dialog as module
from calendar_app.presentation.dialogs.calendar_sync_hub import CalendarSyncHub
from calendar_app.presentation.main_window.caldav_sync_controller import CalDAVSyncController


class Controller(QObject):
    changed = pyqtSignal()

    def __init__(self, settings, service):
        super().__init__()
        self.settings = settings
        self.prefix = "caldav_" + service + "_"
        self.busy, self.status, self.summary = False, "idle", {}
        self.available = [
            {
                "id": "https://example.invalid/" + service + "/",
                "name": "Personal",
                "can_edit": service == "icloud",
            }
        ]
        self.start, self.sync = Mock(return_value=True), Mock()

    @property
    def account(self):
        return self.settings.value(self.prefix + "account_id", "", type=str)


@pytest.fixture
def ui(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    host.schedule_panel_refresh = Mock()
    host.open_gcal_settings_dialog = Mock()
    host._bg_workers = []
    path = tmp_path / "calendar.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE calendar(id TEXT PRIMARY KEY,type TEXT,name TEXT,color TEXT,is_active INTEGER,access_role TEXT); CREATE TABLE unified_task(id INTEGER PRIMARY KEY,name TEXT,calendar_id TEXT,deadline TEXT,end_date TEXT,all_day INTEGER,description TEXT,location TEXT,type TEXT,gcal_dirty INTEGER,gcal_sync_mode TEXT,updated_at TEXT); INSERT INTO calendar VALUES('gcal::existing','gcal','Google','#123456',1,'writer');"
    )
    CalendarSyncRepository(conn)
    conn.close()
    monkeypatch.setattr(module, "DB_PATH", str(path))
    host._caldav_sync_controllers = {
        service: Controller(host.settings, service) for service in ("icloud", "naver")
    }
    for service in ("icloud", "naver"):
        host.settings.setValue(
            "caldav_" + service + "_account_id", "caldav::" + service + "::fixture"
        )
    yield app, host, path
    host.close()


def test_service_selection_only_saves_current_service(ui):
    app, host, path = ui
    dialog = module.CalDAVSettingsDialog(host, host._caldav_sync_controllers)
    dialog.calendars.item(0).setCheckState(Qt.CheckState.Checked)
    dialog._save()
    dialog.enable.setChecked(True)
    dialog.service.setCurrentIndex(1)
    assert not dialog.enable.isChecked()
    dialog.calendars.item(0).setCheckState(Qt.CheckState.Checked)
    dialog._save()
    conn = sqlite3.connect(path)
    rows = conn.execute(
        "SELECT account_id,can_edit FROM calendar_sync_calendar ORDER BY account_id"
    ).fetchall()
    assert rows == [("caldav::icloud::fixture", 1), ("caldav::naver::fixture", 0)]
    assert host.settings.value("caldav_icloud_enabled", False, type=bool)
    assert not host.settings.value("caldav_naver_enabled", False, type=bool)
    assert (
        conn.execute("SELECT is_active FROM calendar WHERE id='gcal::existing'").fetchone()[0] == 1
    )
    conn.close()
    dialog.close()


def test_password_is_masked_cleared_and_not_written_to_settings(ui):
    app, host, path = ui
    dialog = module.CalDAVSettingsDialog(host, host._caldav_sync_controllers)
    assert dialog.password.echoMode() == QLineEdit.EchoMode.Password
    dialog.username.setText("fixture")
    dialog.password.setText("synthetic")
    dialog._connect()
    assert dialog.password.text() == ""
    host._caldav_sync_controllers["icloud"].start.assert_called_once_with(
        "login", "fixture", "synthetic"
    )
    assert not any("password" in key or "secret" in key for key in host.settings.allKeys())
    dialog.close()


def test_busy_state_disables_changes_and_empty_conflicts_disable_resolution(ui):
    app, host, path = ui
    controller = host._caldav_sync_controllers["icloud"]
    controller.busy = True
    dialog = module.CalDAVSettingsDialog(host, host._caldav_sync_controllers)
    assert not dialog.connect_btn.isEnabled()
    assert not dialog.password.isEnabled()
    assert not dialog.calendars.isEnabled()
    assert not dialog.save.isEnabled()
    assert not dialog.local.isEnabled()
    assert not dialog.retry.isEnabled()
    controller.busy = False
    controller.changed.emit()
    assert dialog.save.isEnabled()
    assert not dialog.local.isEnabled()
    dialog.close()


def test_unsubmitted_selection_survives_status_update(ui):
    app, host, path = ui
    dialog = module.CalDAVSettingsDialog(host, host._caldav_sync_controllers)
    dialog.calendars.item(0).setCheckState(Qt.CheckState.Checked)
    host._caldav_sync_controllers["icloud"].status = "network_unavailable"
    host._caldav_sync_controllers["icloud"].changed.emit()
    assert dialog.calendars.item(0).checkState() == Qt.CheckState.Checked
    assert "network_unavailable" not in dialog.status.text()
    dialog.close()


def test_conflict_screen_compares_content_and_applies_only_selected_service(ui):
    app, host, path = ui
    conn = sqlite3.connect(path)
    repo = CalendarSyncRepository(conn, "caldav")
    account = host._caldav_sync_controllers["icloud"].account
    key = repo.register(account, host._caldav_sync_controllers["icloud"].available[0])
    local = {
        "name": "Local title",
        "deadline": "2026-10-08T14:00:00",
        "end_date": "2026-10-08T15:00:00",
        "all_day": 0,
        "description": "Local notes",
        "location": "Room A",
    }
    remote = {
        "id": "fixture-event",
        "task": {**local, "name": "Service title"},
        "etag": "new",
        "zone": "Asia/Seoul",
    }
    with conn:
        tid = repo.import_task(key, local)
        repo.link(tid, key, "fixture-event", "old", fingerprint(local), "fixture-transaction")
        repo.issue(tid, "conflict", repo.task(tid), remote)
    dialog = module.CalDAVSettingsDialog(host, host._caldav_sync_controllers)
    dialog.issues.setCurrentRow(0)
    assert "Local title" in dialog.preview.toPlainText()
    assert "Service title" in dialog.preview.toPlainText()
    assert dialog.local.isEnabled() and dialog.remote.isEnabled()
    assert not dialog.retry.isEnabled()
    dialog._resolve("remote")
    assert repo.task(tid)["name"] == "Service title"
    assert not repo.issues(account)
    assert (
        conn.execute("SELECT name FROM calendar WHERE id='gcal::existing'").fetchone()[0]
        == "Google"
    )
    conn.close()
    dialog.close()


def test_hub_lists_all_services_and_opens_google(ui):
    app, host, path = ui
    hub = CalendarSyncHub(host)
    assert set(hub.labels) == {"google", "outlook", "icloud", "naver", "ics"}
    hub._open("google")
    host.open_gcal_settings_dialog.assert_called_once()
    hub.close()


def test_hub_timezone_updates_shared_setting_and_google_engine(ui):
    app, host, path = ui
    host.gcal_sync = Mock()
    hub = CalendarSyncHub(host)
    hub.timezone.setCurrentText("America/New_York")
    hub._save_timezone()
    assert host.settings.value("gcal_timezone") == "America/New_York"
    assert host.gcal_sync.time_zone == "America/New_York"
    hub.close()


@pytest.mark.parametrize("busy", [False, True])
def test_hub_rejects_invalid_timezone_or_change_during_sync(ui, busy):
    app, host, path = ui
    host.settings.setValue("gcal_timezone", "Asia/Seoul")
    host._caldav_sync_controllers["icloud"].busy = busy
    hub = CalendarSyncHub(host)
    hub.timezone.setCurrentText("Europe/London" if busy else "Invalid/Fixture")
    hub._save_timezone()
    assert host.settings.value("gcal_timezone") == "Asia/Seoul"
    assert hub.timezone_feedback.text()
    hub.close()


def test_controller_backoff_and_shutdown_guard(ui):
    app, host, path = ui
    controller = CalDAVSyncController(host, "icloud")
    controller._failed("remote_http_429")
    assert controller.timer.interval() == 10 * 60 * 1000
    controller._failed("network_unavailable")
    assert controller.timer.interval() == 20 * 60 * 1000
    host._is_shutting_down = True
    assert not controller.start("login", "fixture", "synthetic")
    controller.stop()
    assert not controller.timer.isActive() and not controller.startup_timer.isActive()


def test_save_database_error_is_visible_and_preserves_selection(ui, monkeypatch):
    app, host, path = ui
    dialog = module.CalDAVSettingsDialog(host, host._caldav_sync_controllers)
    dialog.calendars.item(0).setCheckState(Qt.CheckState.Checked)
    monkeypatch.setattr(dialog, "_db", Mock(side_effect=sqlite3.OperationalError("locked")))
    dialog.save.click()
    assert dialog.controller.status == "operation_failed"
    assert dialog.calendars.item(0).checkState() == Qt.CheckState.Checked
    assert dialog.status.text()
    host.schedule_panel_refresh.assert_not_called()
    dialog.close()


def test_retry_deletion_starts_selected_service_only(ui):
    app, host, path = ui
    controller = host._caldav_sync_controllers["icloud"]
    conn = sqlite3.connect(path)
    repo = CalendarSyncRepository(conn, "caldav")
    key = repo.register(controller.account, controller.available[0])
    with conn:
        conn.execute(
            "INSERT INTO calendar_sync_delete_queue(event_id,calendar_id,etag,attempts,error) VALUES('pending',?,'etag',5,'network_unavailable')",
            (key,),
        )
    dialog = module.CalDAVSettingsDialog(host, host._caldav_sync_controllers)
    dialog.issues.setCurrentRow(0)
    dialog.retry.click()
    assert tuple(
        conn.execute("SELECT attempts,error FROM calendar_sync_delete_queue").fetchone()
    ) == (0, None)
    controller.sync.assert_called_once_with(force=True)
    host._caldav_sync_controllers["naver"].sync.assert_not_called()
    conn.close()
    dialog.close()
