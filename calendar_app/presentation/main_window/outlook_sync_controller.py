# -*- coding: utf-8 -*-
"""UI-thread coordinator with isolated DB connections in background workers."""

from datetime import datetime
import sqlite3

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

from calendar_app.app_paths import DB_PATH, get_app_data_dir
from calendar_app.application.calendar_sync_contract import CalendarSyncError
from calendar_app.infrastructure.calendar_sync.engine import CalendarSyncEngine
from calendar_app.infrastructure.calendar_sync.repository import CalendarSyncRepository
from calendar_app.infrastructure.outlook_sync.auth import MicrosoftAuth
from calendar_app.infrastructure.outlook_sync.graph import GraphClient


class OutlookWorker(QThread):
    result = pyqtSignal(str, object)
    failed = pyqtSignal(str)

    def __init__(self, operation, client_id, account, parent, home_id="", local_zone="Asia/Seoul"):
        super().__init__(parent)
        self.operation, self.client_id, self.account = operation, client_id, account
        self.home_id = home_id
        self.local_zone = local_zone

    def run(self):
        try:
            if self.operation == "disconnect":
                import uuid

                client_id = str(uuid.UUID(self.client_id))
                (get_app_data_dir() / f"outlook-{client_id}.cache").unlink(missing_ok=True)
                self.result.emit(self.operation, {})
                return
            auth = MicrosoftAuth(self.client_id)
            client = GraphClient(
                auth.token(interactive=self.operation == "login", account_home_id=self.home_id),
                cancelled=self.isInterruptionRequested,
            )
            if self.isInterruptionRequested():
                return
            profile = client.profile()
            account = "microsoft::" + profile["id"]
            if self.operation != "login" and account != self.account:
                raise CalendarSyncError("account_mismatch")
            calendars = client.calendars()
            if self.operation == "login":
                self.result.emit(
                    self.operation,
                    {
                        "account": account,
                        "home_id": auth.account_home_id,
                        "name": profile.get("mail")
                        or profile.get("userPrincipalName")
                        or profile.get("displayName"),
                        "calendars": calendars,
                    },
                )
                return
            conn = sqlite3.connect(DB_PATH, timeout=10)
            try:
                repository = CalendarSyncRepository(conn)
                for calendar in repository.calendars(account):
                    if not calendar["is_active"]:
                        continue
                    fresh = next((c for c in calendars if c["id"] == calendar["remote_id"]), None)
                    if not fresh:
                        with conn:
                            conn.execute(
                                "UPDATE calendar SET is_active=0,access_role='reader' WHERE id=?",
                                (calendar["local_id"],),
                            )
                        raise CalendarSyncError("calendar_access_lost")
                    repository.register(account, fresh)
                if self.operation == "refresh":
                    self.result.emit(self.operation, {"calendars": calendars})
                    return
                summary = CalendarSyncEngine(
                    client,
                    repository,
                    account,
                    self.local_zone,
                    cancelled=self.isInterruptionRequested,
                ).run()
                self.result.emit(self.operation, summary)
            finally:
                conn.close()
        except CalendarSyncError as exc:
            self.failed.emit(str(exc))
        except ImportError:
            self.failed.emit("dependency_unavailable")
        except Exception:
            # Do not expose OAuth responses, user data or secrets through logs/UI.
            self.failed.emit("operation_failed")


class OutlookSyncController(QObject):
    changed = pyqtSignal()

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.settings = app.settings
        self.worker = None
        self.status = self.settings.value("outlook_last_error", "idle", type=str)
        self.available = []
        self.summary = {}
        self.failures = 0
        self.timer = QTimer(app)
        self.timer.setInterval(5 * 60 * 1000)
        self.timer.timeout.connect(self.sync)
        self.timer.start()
        QTimer.singleShot(15_000, self.sync)

    @property
    def busy(self):
        return self.worker is not None

    def start(self, operation):
        if self.busy or getattr(self.app, "_is_shutting_down", False):
            return False
        client_id = self.settings.value("outlook_client_id", "", type=str)
        if not client_id:
            self.status = "client_id_required"
            self.changed.emit()
            return False
        account = self.settings.value("outlook_account_id", "", type=str)
        self.status = operation
        worker = OutlookWorker(
            operation,
            client_id,
            account,
            self,
            self.settings.value("outlook_home_account_id", "", type=str),
            self.settings.value("gcal_timezone", "Asia/Seoul", type=str),
        )
        self.worker = worker
        self.app._bg_workers.append(worker)
        worker.result.connect(self._result)
        worker.failed.connect(self._failed)
        worker.finished.connect(self._finished)
        worker.start()
        self.changed.emit()
        return True

    def sync(self, force=False):
        if not self.settings.value("outlook_account_id", "", type=str):
            return
        if force or self.settings.value("outlook_enabled", False, type=bool):
            self.start("sync")

    def _result(self, operation, result):
        if getattr(self.app, "_is_shutting_down", False):
            return
        if self.worker and self.worker.isInterruptionRequested():
            return
        try:
            self._apply_result(operation, result)
        except sqlite3.Error:
            self._failed("operation_failed")

    def _apply_result(self, operation, result):
        self.settings.remove("outlook_last_error")
        self.failures = 0
        self.timer.setInterval(5 * 60 * 1000)
        if operation == "login":
            previous = self.settings.value("outlook_account_id", "", type=str)
            if previous and previous != result["account"]:
                self.settings.setValue("outlook_enabled", False)
                conn = sqlite3.connect(DB_PATH, timeout=10)
                try:
                    CalendarSyncRepository(conn)
                    with conn:
                        conn.execute(
                            "UPDATE calendar SET is_active=0,access_role='reader' WHERE id IN (SELECT local_id FROM calendar_sync_calendar WHERE account_id=?)",
                            (previous,),
                        )
                finally:
                    conn.close()
            self.settings.setValue("outlook_account_id", result["account"])
            self.settings.setValue("outlook_home_account_id", result["home_id"])
            self.settings.setValue("outlook_account_name", result["name"])
            self.available = result["calendars"]
        elif operation == "disconnect":
            self.settings.setValue("outlook_enabled", False)
            self.settings.remove("outlook_account_id")
            self.settings.remove("outlook_home_account_id")
            self.settings.remove("outlook_account_name")
            self.available = []
        elif operation == "refresh":
            self.available = result["calendars"]
        else:
            self.summary = result
            self.settings.setValue(
                "outlook_last_success", datetime.now().astimezone().isoformat(timespec="seconds")
            )
            self.app.schedule_panel_refresh(left=True, center=True, right=True)
        self.status = (
            "connected"
            if operation == "login"
            else "disconnected"
            if operation == "disconnect"
            else "refreshed"
            if operation == "refresh"
            else "completed"
        )
        self.changed.emit()

    def _failed(self, code):
        if getattr(self.app, "_is_shutting_down", False):
            return
        self.status = code
        self.settings.setValue("outlook_last_error", code)
        self.failures += 1
        self.timer.setInterval(min(60, 5 * 2 ** min(self.failures, 4)) * 60 * 1000)
        if self.worker and self.worker.operation == "sync":
            # Earlier calendars may already have committed before a later failure.
            self.app.schedule_panel_refresh(left=True, center=True, right=True)
        self.changed.emit()

    def _finished(self):
        worker = self.sender()
        if worker in self.app._bg_workers:
            self.app._bg_workers.remove(worker)
        self.worker = None
        worker.deleteLater()
        self.changed.emit()


def open_outlook_settings(app, section="services", from_sync_hub=False):
    from calendar_app.presentation.dialogs.outlook_settings_dialog import OutlookSettingsDialog

    dialog = OutlookSettingsDialog(app, app._outlook_sync_controller)
    dialog.setProperty("syncHubChild", from_sync_hub)
    dialog.tabs.setCurrentIndex(0 if section == "services" else 1)
    dialog.exec()
