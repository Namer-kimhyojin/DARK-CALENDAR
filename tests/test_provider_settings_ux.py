# -*- coding: utf-8 -*-
"""User-visible provider setup boundaries without accounts, network or native data."""

import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QObject, QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLineEdit, QWidget
import pytest

from calendar_app.infrastructure.calendar_sync.repository import CalendarSyncRepository, fingerprint
from calendar_app.presentation.dialogs import caldav_settings_dialog as caldav
from calendar_app.presentation.dialogs import outlook_settings_dialog as outlook
from calendar_app.presentation.main_window import caldav_sync_controller, outlook_sync_controller
from tests.test_sync_controller_lifecycle import controller as lifecycle_controller  # noqa: F401


class Controller(QObject):
    changed = pyqtSignal()

    def __init__(self, settings, provider):
        super().__init__()
        self.settings, self.provider = settings, provider
        self.prefix = "outlook_" if provider == "outlook" else "caldav_" + provider + "_"
        self.busy, self.status, self.summary = False, "refreshed", {}
        self.retry_remaining_seconds = 0
        self.worker = None
        self.available = [
            {
                "id": "https://example.invalid/" + provider + "/" + str(i),
                "name": "<b>Calendar " + str(i) + "</b>",
                ("canEdit" if provider == "outlook" else "can_edit"): provider != "naver",
            }
            for i in range(12)
        ]
        self.start, self.sync = Mock(return_value=True), Mock()

    @property
    def account(self):
        return self.settings.value(self.prefix + "account_id", "", type=str)


@pytest.fixture(params=["outlook", "icloud", "naver"])
def ui(request, tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    host.schedule_panel_refresh = Mock()
    host._bg_workers = []
    provider = request.param
    path = tmp_path / "calendar.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE calendar(id TEXT PRIMARY KEY,type TEXT,name TEXT,color TEXT,is_active INTEGER,access_role TEXT);"
        "CREATE TABLE unified_task(id INTEGER PRIMARY KEY,name TEXT,calendar_id TEXT,deadline TEXT,end_date TEXT,all_day INTEGER,description TEXT,location TEXT,type TEXT,gcal_dirty INTEGER,gcal_sync_mode TEXT,updated_at TEXT);"
    )
    CalendarSyncRepository(conn)
    conn.close()
    monkeypatch.setattr(outlook, "DB_PATH", str(path))
    monkeypatch.setattr(caldav, "DB_PATH", str(path))
    controller = Controller(host.settings, provider)
    host.settings.setValue(controller.prefix + "account_id", provider + "::synthetic")
    host.settings.setValue(controller.prefix + "account_name", "<b>Test account</b>")
    host.settings.setValue("outlook_client_id", "11111111-1111-1111-1111-111111111111")
    dialog = (
        outlook.OutlookSettingsDialog(host, controller)
        if provider == "outlook"
        else caldav.CalDAVSettingsDialog(host, {provider: controller}, provider)
    )
    yield app, host, dialog, controller, path, provider
    dialog.close()
    host.close()
    app.processEvents()


def test_repeated_status_keeps_check_draft_item_selection_and_scroll(ui, monkeypatch):
    app, _, dialog, controller, _, _ = ui
    dialog.tabs.setCurrentIndex(1)
    dialog.resize(620, 720)
    dialog.show()
    app.processEvents()
    item = dialog.calendars.item(10)
    item.setCheckState(Qt.CheckState.Checked)
    dialog.calendars.setCurrentItem(item)
    dialog.calendars.verticalScrollBar().setValue(120)
    scroll = dialog.calendars.verticalScrollBar().value()
    method = "_connection" if hasattr(dialog, "_connection") else "_db"
    connection = Mock(wraps=getattr(dialog, method))
    monkeypatch.setattr(dialog, method, connection)
    controller.changed.emit()
    controller.changed.emit()
    connection.assert_not_called()
    assert dialog.calendars.item(10) is item
    assert item.checkState() == Qt.CheckState.Checked
    assert dialog.calendars.currentItem() is item
    assert dialog.calendars.verticalScrollBar().value() == scroll


def test_sync_applies_current_draft_before_calling_provider(ui):
    _, _, dialog, controller, path, provider = ui
    dialog.calendars.item(1).setCheckState(Qt.CheckState.Checked)

    def sync(force=False):
        conn = sqlite3.connect(path)
        rows = CalendarSyncRepository(
            conn, "outlook" if provider == "outlook" else "caldav"
        ).calendars(controller.account)
        assert [row["remote_id"] for row in rows if row["is_active"]] == [
            controller.available[1]["id"]
        ]
        conn.close()
        assert force

    controller.sync.side_effect = sync
    dialog.sync.click()
    controller.sync.assert_called_once_with(force=True)


def test_save_failure_preserves_draft_and_never_calls_sync(ui, monkeypatch):
    _, _, dialog, controller, _, provider = ui
    dialog.calendars.item(0).setCheckState(Qt.CheckState.Checked)
    monkeypatch.setattr(
        dialog,
        "_connection" if provider == "outlook" else "_db",
        Mock(side_effect=sqlite3.OperationalError("locked")),
    )
    dialog.sync.click()
    controller.sync.assert_not_called()
    assert controller.status == "operation_failed"
    assert dialog.calendars.item(0).checkState() == Qt.CheckState.Checked
    assert dialog.status.text()


def test_empty_selection_retry_wait_and_reauthentication_block_sync(ui):
    _, host, dialog, controller, _, _ = ui
    assert not dialog.sync.isEnabled()
    dialog._save_and_sync()
    controller.sync.assert_not_called()
    dialog.calendars.item(0).setCheckState(Qt.CheckState.Checked)
    controller.retry_remaining_seconds = 45
    controller.status = "remote_http_429"
    controller.changed.emit()
    assert not dialog.sync.isEnabled()
    assert not (
        dialog.refresh_list if hasattr(dialog, "refresh_list") else dialog.refresh
    ).isEnabled()
    assert "45" in dialog.next_step.text()
    dialog._save_and_sync()
    controller.sync.assert_not_called()
    controller.retry_remaining_seconds = 0
    dialog._update_actions()
    assert dialog.sync.isEnabled()
    host.settings.setValue(controller.prefix + "last_error", "reauth_required")
    controller.changed.emit()
    assert not dialog.sync.isEnabled()
    dialog._save()
    assert not dialog.sync.isEnabled()
    assert dialog._recovery["kind"] == "reconnect"


def test_metadata_refresh_keeps_draft_but_updates_read_only_capability(ui):
    _, _, dialog, controller, _, provider = ui
    dialog.calendars.item(0).setCheckState(Qt.CheckState.Checked)
    controller.available = [dict(remote) for remote in controller.available]
    controller.available[0]["canEdit" if provider == "outlook" else "can_edit"] = False
    controller.changed.emit()
    assert dialog.calendars.item(0).checkState() == Qt.CheckState.Checked
    assert not dialog.calendars.item(0).data(Qt.ItemDataRole.UserRole)[
        "canEdit" if provider == "outlook" else "can_edit"
    ]
    assert dialog.sync.isEnabled()


def test_changed_account_never_inherits_old_check_draft(ui):
    _, host, dialog, controller, _, _ = ui
    dialog.calendars.item(0).setCheckState(Qt.CheckState.Checked)
    host.settings.setValue(controller.prefix + "account_id", "different::synthetic")
    controller.changed.emit()
    assert dialog.calendars.item(0).checkState() == Qt.CheckState.Unchecked
    assert not dialog.sync.isEnabled()


def test_empty_saved_selection_stops_automatic_sync(ui):
    _, host, dialog, controller, path, provider = ui
    dialog.calendars.item(0).setCheckState(Qt.CheckState.Checked)
    dialog._save()
    dialog.enable.setChecked(True)
    dialog.calendars.item(0).setCheckState(Qt.CheckState.Unchecked)
    dialog._save()
    assert not host.settings.value(controller.prefix + "enabled", True, type=bool)
    assert not dialog.sync.isEnabled()
    conn = sqlite3.connect(path)
    rows = CalendarSyncRepository(conn, "outlook" if provider == "outlook" else "caldav").calendars(
        controller.account
    )
    assert not any(row["is_active"] for row in rows)
    conn.close()


def test_conflict_comparison_stays_selected_through_status_changes(ui):
    _, host, dialog, controller, path, provider = ui
    conn = sqlite3.connect(path)
    repo = CalendarSyncRepository(conn, "outlook" if provider == "outlook" else "caldav")
    remote_calendar = dict(controller.available[0])
    if provider == "naver":
        remote_calendar["can_edit"] = True
    key = repo.register(controller.account, remote_calendar)
    task = {
        "name": "Local",
        "deadline": "2026-10-08T14:00:00",
        "end_date": "2026-10-08T15:00:00",
        "all_day": 0,
        "description": "Notes",
        "location": "Room",
    }
    remote = (
        {
            "id": "event",
            "subject": "Remote",
            "start": {"dateTime": "2026-10-08T14:00:00", "timeZone": "Asia/Seoul"},
            "end": {"dateTime": "2026-10-08T15:00:00", "timeZone": "Asia/Seoul"},
            "isAllDay": False,
        }
        if provider == "outlook"
        else {
            "id": "event",
            "task": {**task, "name": "Remote"},
            "etag": "new",
            "zone": "Asia/Seoul",
        }
    )
    with conn:
        tid = repo.import_task(key, task)
        repo.link(tid, key, "event", "old", fingerprint(task), "transaction")
        repo.issue(tid, "conflict", repo.task(tid), remote)
    controller.status = "completed_with_issues"
    controller.summary = {"issues": 1}
    controller.changed.emit()
    dialog.issues.setCurrentRow(0)
    item = dialog.issues.currentItem()
    text = dialog.preview.toPlainText()
    assert "Local" in text and "Remote" in text
    cursor = dialog.preview.textCursor()
    cursor.setPosition(2)
    cursor.setPosition(6, QTextCursor.MoveMode.KeepAnchor)
    dialog.preview.setTextCursor(cursor)
    controller.changed.emit()
    assert dialog.issues.currentItem() is item
    assert dialog.preview.toPlainText() == text
    assert dialog.preview.textCursor().anchor() == 2
    assert dialog.preview.textCursor().position() == 6
    conn.close()


def test_narrow_window_plaintext_and_cooperative_cancel(ui):
    app, _, dialog, controller, _, _ = ui
    dialog.resize(620, 720)
    dialog.show()
    app.processEvents()
    dialog.resize(620, 720)
    app.processEvents()
    assert dialog.width() == 620 and dialog.height() == 720
    assert dialog.account.textFormat() == Qt.TextFormat.PlainText
    assert dialog.status.textFormat() == Qt.TextFormat.PlainText
    assert dialog.next_step.textFormat() == Qt.TextFormat.PlainText
    controller.worker = Mock()
    controller.busy, controller.status = True, "sync"
    controller.changed.emit()
    assert not dialog.sync.isEnabled()
    assert dialog.cancel_work.isEnabled()
    dialog.cancel_work.click()
    controller.worker.requestInterruption.assert_called_once()
    assert not dialog.cancel_work.isEnabled()
    controller.busy = False
    controller.changed.emit()
    assert controller.status == "cancelled"
    assert not dialog.cancel_work.isVisible()


def test_enter_in_required_input_does_not_close_dialog(ui):
    app, _, dialog, controller, _, provider = ui
    dialog.tabs.setCurrentIndex(0)
    dialog.show()
    app.processEvents()
    if provider == "outlook":
        field = dialog.client_id
        field.setText("invalid")
    else:
        field = dialog.password
        dialog.username.setText("user")
        field.clear()
    field.setFocus()
    QTest.keyClick(field, Qt.Key.Key_Return)
    assert dialog.isVisible()
    controller.start.assert_not_called()
    assert controller.status in {"client_id_required", "credentials_required"}
    if provider != "outlook":
        assert field.echoMode() == QLineEdit.EchoMode.Password


@pytest.mark.parametrize(
    "module,cls",
    [
        (outlook_sync_controller, outlook_sync_controller.OutlookSyncController),
        (caldav_sync_controller, caldav_sync_controller.CalDAVSyncController),
    ],
)
def test_retry_remaining_property_rounds_up_without_mutating_deadline(module, cls, monkeypatch):
    monkeypatch.setattr(module, "monotonic", lambda: 100.1)
    controller = cls.__new__(cls)
    controller._retry_not_before = 101.2
    assert controller.retry_remaining_seconds == 2
    assert controller._retry_not_before == 101.2
    monkeypatch.setattr(module, "monotonic", lambda: 102)
    assert controller.retry_remaining_seconds == 0


def test_cancelled_request_keeps_prior_error_retry_deadline_and_success_time(lifecycle_controller):
    _, host, controller, prefix, _, _ = lifecycle_controller
    host.settings.setValue(prefix + "last_success", "previous-success")
    host.settings.setValue(prefix + "last_error", "remote_http_429")
    controller.failures, controller._retry_not_before = 3, 9000
    interval = controller.timer.interval()
    controller.worker = SimpleNamespace(
        operation="sync", retry_after=9999, isInterruptionRequested=lambda: True
    )
    controller._failed("network_unavailable")
    assert controller.status == "cancelled"
    assert controller.failures == 3 and controller._retry_not_before == 9000
    assert controller.timer.interval() == interval
    assert host.settings.value(prefix + "last_success") == "previous-success"
    assert host.settings.value(prefix + "last_error") == "remote_http_429"
    host.schedule_panel_refresh.assert_called_once()
    controller.worker = None


def test_disconnect_cannot_be_cancelled_after_credential_cleanup_starts(ui):
    _, _, dialog, controller, _, _ = ui
    controller.worker = Mock()
    controller.busy, controller.status = True, "disconnect"
    controller.changed.emit()
    assert dialog.cancel_work.isHidden()
    dialog._cancel_work()
    controller.worker.requestInterruption.assert_not_called()


def test_login_result_opens_selection_after_worker_finishes(ui):
    _, _, dialog, controller, _, _ = ui
    dialog.tabs.setCurrentIndex(0)
    controller.busy, controller.status = True, "connected"
    controller.changed.emit()
    assert dialog.tabs.currentIndex() == 0
    controller.busy = False
    controller.changed.emit()
    assert dialog.tabs.currentIndex() == 1


def test_partial_summary_keeps_problem_action_when_issue_metadata_lags(ui):
    _, _, dialog, controller, _, _ = ui
    dialog.calendars.item(0).setCheckState(Qt.CheckState.Checked)
    dialog._save()
    controller.status = "completed_with_issues"
    controller.summary = {"issues": 2}
    controller.changed.emit()
    assert not dialog.issues.count()
    assert dialog._recovery["kind"] == "issues"
    assert dialog.sync.isEnabled()
    dialog.next_action.click()
    assert dialog.tabs.currentIndex() == 2


def test_disconnect_result_clears_account_after_local_credentials_removed(
    lifecycle_controller, tmp_path, monkeypatch
):
    _, host, controller, prefix, module, _ = lifecycle_controller
    client_id = "11111111-1111-1111-1111-111111111111"
    host.settings.setValue("outlook_client_id", client_id)
    host.settings.setValue(prefix + "account_name", "Fixture")
    host.settings.setValue(prefix + "enabled", True)
    if prefix == "outlook_":
        monkeypatch.setattr(module, "get_app_data_dir", lambda: tmp_path)
        cache = tmp_path / ("outlook-" + client_id + ".cache")
        cache.write_bytes(b"synthetic-cache")
        worker = module.OutlookWorker("disconnect", client_id, "old-account", controller)
    else:
        store = Mock()
        monkeypatch.setattr(module, "CalDAVCredentials", Mock(return_value=store))
        worker = module.CalDAVWorker(controller.service, "disconnect", "old-account", controller)
    monkeypatch.setattr(worker, "start", Mock())
    monkeypatch.setattr(
        module,
        "OutlookWorker" if prefix == "outlook_" else "CalDAVWorker",
        Mock(return_value=worker),
    )
    assert controller.start("disconnect")
    worker.start.assert_called_once()
    worker.run()
    assert controller.status == "disconnected"
    assert not host.settings.value(prefix + "account_id", "", type=str)
    assert not host.settings.contains(prefix + "account_name")
    assert not host.settings.value(prefix + "enabled", True, type=bool)
    if prefix == "outlook_":
        assert not cache.exists()
    else:
        store.remove.assert_called_once_with("old-account")
    worker.finished.emit()
    assert controller.worker is None and not host._bg_workers
