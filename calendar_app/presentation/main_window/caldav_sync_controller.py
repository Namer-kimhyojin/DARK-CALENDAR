# -*- coding: utf-8 -*-
"""Independent CalDAV service workers, account selection and retry scheduling."""

from datetime import datetime
import sqlite3

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

from calendar_app.app_paths import DB_PATH
from calendar_app.application.calendar_sync_contract import CalendarSyncError, RemoteCalendarError
from calendar_app.infrastructure.caldav_sync.client import CalDAVClient
from calendar_app.infrastructure.caldav_sync.credentials import CalDAVCredentials
from calendar_app.infrastructure.caldav_sync.profiles import account_key
from calendar_app.infrastructure.caldav_sync.resource_cache import CalDAVResourceCache
from calendar_app.infrastructure.calendar_sync.engine import CalendarSyncEngine
from calendar_app.infrastructure.calendar_sync.repository import CalendarSyncRepository


class CalDAVWorker(QThread):
    result = pyqtSignal(str, object)
    failed = pyqtSignal(str)

    def __init__(
        self, service, operation, account, parent, username="", password="", local_zone="Asia/Seoul"
    ):
        super().__init__(parent)
        self.service, self.operation, self.account = service, operation, account
        self.username, self.password = username, password
        self.local_zone = local_zone

    def run(self):
        client = None
        try:
            store = CalDAVCredentials()
            if self.operation == "disconnect":
                if self.account:
                    store.remove(self.account)
                self.result.emit(self.operation, {})
                return
            if self.operation == "login":
                account = account_key(self.service, self.username)
                credentials = {
                    "service": self.service,
                    "username": self.username,
                    "password": self.password,
                }
            else:
                account = self.account
                credentials = store.load(account)
                if credentials["service"] != self.service:
                    raise CalendarSyncError("account_mismatch")
            client = CalDAVClient(
                **credentials, cancelled=self.isInterruptionRequested, local_zone=self.local_zone
            )
            calendars = client.calendars()
            if self.isInterruptionRequested():
                return
            if self.operation == "login":
                store.save(**credentials)
                self.result.emit(
                    self.operation,
                    {"account": account, "name": credentials["username"], "calendars": calendars},
                )
                return
            conn = sqlite3.connect(DB_PATH, timeout=10)
            try:
                repo = CalendarSyncRepository(conn, "caldav")
                client.resource_cache = CalDAVResourceCache(conn, account)
                saved = repo.calendars(account)
                available = {c["id"]: c for c in calendars}
                missing = [c for c in saved if c["is_active"] and c["remote_id"] not in available]
                if missing:
                    with conn:
                        for calendar in missing:
                            conn.execute(
                                "UPDATE calendar SET is_active=0,access_role='reader' WHERE id=?",
                                (calendar["local_id"],),
                            )
                    raise CalendarSyncError("calendar_access_lost")
                for calendar in saved:
                    if calendar["remote_id"] in available:
                        repo.register(account, available[calendar["remote_id"]])
                if self.operation == "refresh":
                    self.result.emit(self.operation, {"calendars": calendars})
                else:
                    summary = CalendarSyncEngine(
                        client,
                        repo,
                        account,
                        self.local_zone,
                        cancelled=self.isInterruptionRequested,
                    ).run()
                    self.result.emit(self.operation, {"summary": summary, "calendars": calendars})
            finally:
                conn.close()
        except RemoteCalendarError as exc:
            self.failed.emit(f"remote_http_{exc.status}")
        except CalendarSyncError as exc:
            self.failed.emit(str(exc))
        except ImportError:
            self.failed.emit("dependency_unavailable")
        except Exception:
            self.failed.emit("operation_failed")
        finally:
            self.password = ""
            if client:
                client.auth = ("", "")
                client.session.close()


class CalDAVSyncController(QObject):
    changed = pyqtSignal()

    def __init__(self, app, service):
        super().__init__(app)
        self.app, self.settings, self.service = app, app.settings, service
        self.prefix = "caldav_" + service + "_"
        self.worker = None
        self.available, self.summary = [], {}
        self.status, self.failures = (
            self.settings.value(self.prefix + "last_error", "idle", type=str),
            0,
        )
        self.timer = QTimer(app)
        self.timer.setInterval(5 * 60 * 1000)
        self.timer.timeout.connect(self.sync)
        self.timer.start()
        self.startup_timer = QTimer(self)
        self.startup_timer.setSingleShot(True)
        self.startup_timer.timeout.connect(self.sync)
        self.startup_timer.start(20000 if service == "icloud" else 25000)

    @property
    def busy(self):
        return self.worker is not None

    @property
    def account(self):
        return self.settings.value(self.prefix + "account_id", "", type=str)

    def start(self, operation, username="", password=""):
        if self.busy or getattr(self.app, "_is_shutting_down", False):
            return False
        if operation == "login" and (not username.strip() or not password):
            self.status = "credentials_required"
            self.changed.emit()
            return False
        if operation != "login" and not self.account:
            self.status = "login_required"
            self.changed.emit()
            return False
        if operation == "disconnect":
            try:
                conn = sqlite3.connect(DB_PATH, timeout=10)
                try:
                    CalendarSyncRepository(conn, "caldav").deactivate(self.account)
                finally:
                    conn.close()
            except sqlite3.Error:
                self._failed("operation_failed")
                return False
            self.settings.setValue(self.prefix + "enabled", False)
        self.status = operation
        worker = CalDAVWorker(
            self.service,
            operation,
            self.account,
            self,
            username,
            password,
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
        if self.account and (
            force or self.settings.value(self.prefix + "enabled", False, type=bool)
        ):
            if force:
                self.timer.setInterval(5 * 60 * 1000)
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
        self.settings.remove(self.prefix + "last_error")
        self.failures = 0
        self.timer.setInterval(5 * 60 * 1000)
        if operation == "login":
            if self.account and self.account != result["account"]:
                conn = sqlite3.connect(DB_PATH, timeout=10)
                try:
                    CalendarSyncRepository(conn, "caldav").deactivate(self.account)
                finally:
                    conn.close()
                self.settings.setValue(self.prefix + "enabled", False)
            self.settings.setValue(self.prefix + "account_id", result["account"])
            self.settings.setValue(self.prefix + "account_name", result["name"])
        elif operation == "disconnect":
            self.settings.remove(self.prefix + "account_id")
            self.settings.remove(self.prefix + "account_name")
            self.available = []
        elif operation == "sync":
            self.summary = result["summary"]
            self.settings.setValue(
                self.prefix + "last_success",
                datetime.now().astimezone().isoformat(timespec="seconds"),
            )
        self.available = result.get("calendars", self.available)
        self.status = {
            "login": "connected",
            "disconnect": "disconnected",
            "refresh": "refreshed",
        }.get(operation, "completed")
        self.app.schedule_panel_refresh(left=True, center=True, right=True)
        self.changed.emit()

    def _failed(self, code):
        if getattr(self.app, "_is_shutting_down", False):
            return
        self.status = code
        self.settings.setValue(self.prefix + "last_error", code)
        self.failures += 1
        self.timer.setInterval(min(60, 5 * 2 ** min(self.failures, 4)) * 60 * 1000)
        if self.worker and self.worker.operation == "sync":
            self.app.schedule_panel_refresh(left=True, center=True, right=True)
        self.changed.emit()

    def _finished(self):
        worker = self.sender()
        if worker in self.app._bg_workers:
            self.app._bg_workers.remove(worker)
        if worker is self.worker:
            self.worker = None
        worker.deleteLater()
        self.changed.emit()

    def stop(self):
        self.timer.stop()
        self.startup_timer.stop()
        if self.worker:
            self.worker.requestInterruption()


def open_caldav_settings(app, service="icloud", section="services", from_sync_hub=False):
    from calendar_app.presentation.dialogs.caldav_settings_dialog import CalDAVSettingsDialog

    dialog = CalDAVSettingsDialog(app, app._caldav_sync_controllers, service)
    dialog.setProperty("syncHubChild", from_sync_hub)
    dialog.tabs.setCurrentIndex({"services": 0, "calendars": 1, "issues": 2}.get(section, 0))
    dialog.exec()
