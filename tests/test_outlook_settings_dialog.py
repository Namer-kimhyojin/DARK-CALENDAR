# -*- coding: utf-8 -*-
import sqlite3
from unittest.mock import Mock

from PyQt6.QtCore import QObject, QSettings, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget

from calendar_app.infrastructure.calendar_sync.repository import CalendarSyncRepository
from calendar_app.presentation.dialogs import outlook_settings_dialog as module


class Controller(QObject):
    changed = pyqtSignal()
    busy = False
    status = "idle"
    summary = {}
    available = [
        {"id": "one", "name": "Personal", "canEdit": True},
        {"id": "two", "name": "Shared", "canEdit": False},
    ]

    def __init__(self):
        super().__init__()
        self.start = Mock()
        self.sync = Mock()


def host(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = QWidget()
    window.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window.schedule_panel_refresh = Mock()
    return app, window


def database(path):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE calendar(id TEXT PRIMARY KEY,type TEXT,name TEXT,color TEXT,is_active INTEGER,access_role TEXT);
        CREATE TABLE unified_task(id INTEGER PRIMARY KEY,calendar_id TEXT);
        INSERT INTO calendar VALUES('gcal::existing','gcal','Google','#123456',1,'writer');
    """)
    CalendarSyncRepository(conn)
    conn.close()


def test_calendar_selection_saves_outlook_only_and_disconnect_preserves_rows(tmp_path, monkeypatch):
    app, window = host(tmp_path)
    path = tmp_path / "calendar.db"
    database(path)
    monkeypatch.setattr(module, "DB_PATH", str(path))
    window.settings.setValue("outlook_account_id", "microsoft::test")
    window.settings.setValue("outlook_client_id", "11111111-1111-1111-1111-111111111111")
    controller = Controller()
    dialog = module.OutlookSettingsDialog(window, controller)
    dialog.calendars.item(0).setCheckState(Qt.CheckState.Checked)
    dialog.calendars.item(1).setCheckState(Qt.CheckState.Checked)
    dialog._save()
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT COUNT(*) FROM calendar WHERE type='outlook'").fetchone()[0] == 2
    dialog._disconnect()
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM calendar WHERE type='outlook' AND is_active=0 AND access_role='reader'"
        ).fetchone()[0]
        == 2
    )
    assert (
        conn.execute("SELECT is_active FROM calendar WHERE id='gcal::existing'").fetchone()[0] == 1
    )
    assert controller.start.call_args.args == ("disconnect",)
    conn.close()
    dialog.close()
    window.close()


def test_busy_worker_prevents_configuration_changes(tmp_path):
    app, window = host(tmp_path)
    controller = Controller()
    controller.busy = True
    dialog = module.OutlookSettingsDialog(window, controller)
    assert not dialog.login.isEnabled()
    assert not dialog.client_id.isEnabled()
    assert not dialog.save.isEnabled()
    dialog.close()
    window.close()


def test_invalid_client_id_never_starts_login(tmp_path):
    app, window = host(tmp_path)
    controller = Controller()
    dialog = module.OutlookSettingsDialog(window, controller)
    dialog.client_id.setText("not-a-client-id")
    dialog._login()
    assert controller.status == "client_id_required"
    controller.start.assert_not_called()
    dialog.close()
    window.close()


def test_save_database_error_is_visible_and_preserves_selection(tmp_path, monkeypatch):
    app, window = host(tmp_path)
    path = tmp_path / "calendar.db"
    database(path)
    monkeypatch.setattr(module, "DB_PATH", str(path))
    window.settings.setValue("outlook_account_id", "microsoft::test")
    controller = Controller()
    dialog = module.OutlookSettingsDialog(window, controller)
    dialog.calendars.item(0).setCheckState(Qt.CheckState.Checked)
    monkeypatch.setattr(dialog, "_connection", Mock(side_effect=sqlite3.OperationalError("locked")))
    dialog.save.click()
    assert controller.status == "operation_failed"
    assert dialog.calendars.item(0).checkState() == Qt.CheckState.Checked
    window.schedule_panel_refresh.assert_not_called()
    dialog.close()
    window.close()


def test_retry_deletion_starts_outlook_immediately(tmp_path, monkeypatch):
    app, window = host(tmp_path)
    path = tmp_path / "calendar.db"
    database(path)
    monkeypatch.setattr(module, "DB_PATH", str(path))
    window.settings.setValue("outlook_account_id", "microsoft::test")
    controller = Controller()
    conn = sqlite3.connect(path)
    repo = CalendarSyncRepository(conn)
    key = repo.register("microsoft::test", controller.available[0])
    with conn:
        conn.execute(
            "INSERT INTO calendar_sync_delete_queue(event_id,calendar_id,etag,attempts,error) VALUES('pending',?,'etag',5,'network_unavailable')",
            (key,),
        )
    dialog = module.OutlookSettingsDialog(window, controller)
    dialog.issues.setCurrentRow(0)
    dialog.retry_delete.click()
    assert tuple(
        conn.execute("SELECT attempts,error FROM calendar_sync_delete_queue").fetchone()
    ) == (0, None)
    controller.sync.assert_called_once_with(force=True)
    conn.close()
    dialog.close()
    window.close()
