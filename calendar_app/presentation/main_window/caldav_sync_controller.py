# -*- coding: utf-8 -*-
"""Independent CalDAV service workers, account selection and retry scheduling."""

from contextlib import suppress
from datetime import datetime
from math import ceil
import sqlite3
from time import monotonic

from PyQt6.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal

from calendar_app.app_paths import DB_PATH
from calendar_app.application.calendar_sync_contract import CalendarSyncError, RemoteCalendarError
from calendar_app.infrastructure.caldav_sync.client import CalDAVClient
from calendar_app.infrastructure.caldav_sync.credentials import CalDAVCredentials
from calendar_app.infrastructure.caldav_sync.profiles import PROFILES, account_key
from calendar_app.infrastructure.caldav_sync.resource_cache import CalDAVResourceCache
from calendar_app.infrastructure.calendar_sync.engine import CalendarSyncEngine
from calendar_app.infrastructure.calendar_sync.http_retry import MAX_RETRY_AFTER_SECONDS
from calendar_app.infrastructure.calendar_sync.repository import CalendarSyncRepository


class CalDAVWorker(QThread):
    result = pyqtSignal(str, object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        service,
        operation,
        account,
        parent,
        username="",
        password="",
        local_zone="Asia/Seoul",
        server_url=None,
    ):
        super().__init__(parent)
        self.service, self.operation, self.account = service, operation, account
        self.username, self.password = username, password
        self.local_zone = local_zone
        self.server_url = server_url
        self.retry_after = None

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
                if self.server_url:
                    credentials["server_url"] = self.server_url
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
                    {
                        "account": account,
                        "name": credentials["username"],
                        "calendars": calendars,
                        "server_url": self.server_url or PROFILES[self.service]["url"],
                    },
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
            self.retry_after = getattr(exc, "retry_after", None)
            self.failed.emit(f"remote_http_{exc.status}")
        except CalendarSyncError as exc:
            self.retry_after = getattr(exc, "retry_after", None)
            self.failed.emit(str(exc))
        except ImportError:
            self.failed.emit("dependency_unavailable")
        except Exception:
            self.failed.emit("operation_failed")
        finally:
            self.password = ""
            if client is not None:
                client.auth = ("", "")
                # Cleanup must not leak a second exception out of QThread.run.
                with suppress(Exception):
                    client.session.close()


class CalDAVSyncController(QObject):
    changed = pyqtSignal()

    def __init__(self, app, service):
        super().__init__(app)
        self.app, self.settings, self.service = app, app.settings, service
        self.prefix = "caldav_" + service + "_"
        self.worker = None
        self._retry_not_before = 0.0
        self.available, self.summary = [], {}
        self.status, self.failures = (
            self.settings.value(self.prefix + "last_error", "idle", type=str),
            0,
        )
        self.timer = QTimer(app)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
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
    def retry_remaining_seconds(self):
        return max(0, ceil(self._retry_not_before - monotonic()))

    @property
    def account(self):
        return self.settings.value(self.prefix + "account_id", "", type=str)

    def start(self, operation, username="", password="", server_url=None):
        if self.busy or getattr(self.app, "_is_shutting_down", False):
            return False
        if operation in {"sync", "refresh"} and monotonic() < self._retry_not_before:
            self.timer.setInterval(max(1, ceil((self._retry_not_before - monotonic()) * 1000)))
            self.status = self.settings.value(self.prefix + "last_error", self.status, type=str)
            self.changed.emit()
            return False
        if operation in {"sync", "refresh"} and self._retry_not_before:
            self._retry_not_before = 0.0
            self.timer.setInterval(5 * 60 * 1000)
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
            server_url=server_url,
        )
        self.worker = worker
        self.app._bg_workers.append(worker)
        worker.result.connect(self._result)
        worker.failed.connect(self._failed)
        worker.finished.connect(self._finished)
        try:
            worker.start()
        except Exception:
            self.worker = None
            if worker in self.app._bg_workers:
                self.app._bg_workers.remove(worker)
            worker.password = ""
            worker.deleteLater()
            self._failed("operation_failed")
            return False
        self.changed.emit()
        return True

    def sync(self, force=False):
        if self.account and (
            force or self.settings.value(self.prefix + "enabled", False, type=bool)
        ):
            if force and monotonic() >= self._retry_not_before:
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
        self._retry_not_before = 0.0
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
            if result.get("server_url"):
                self.settings.setValue(self.prefix + "server_url", result["server_url"])
        elif operation == "disconnect":
            self.settings.setValue(self.prefix + "enabled", False)
            self.settings.remove(self.prefix + "account_id")
            self.settings.remove(self.prefix + "account_name")
            self.available = []
        elif operation == "sync":
            self.summary = result["summary"]
            if not self.summary.get("issues"):
                self.settings.setValue(
                    self.prefix + "last_success",
                    datetime.now().astimezone().isoformat(timespec="seconds"),
                )
        self.available = result.get("calendars", self.available)
        self.status = {
            "login": "connected",
            "disconnect": "disconnected",
            "refresh": "refreshed",
        }.get(operation, "completed_with_issues" if self.summary.get("issues") else "completed")
        self.app.schedule_panel_refresh(left=True, center=True, right=True)
        self.changed.emit()

    def _failed(self, code):
        if getattr(self.app, "_is_shutting_down", False):
            return
        if code == "cancelled" or (
            self.worker and getattr(self.worker, "isInterruptionRequested", lambda: False)() is True
        ):
            self.status = "cancelled"
            if self.worker and self.worker.operation in {"sync", "refresh"}:
                self.app.schedule_panel_refresh(left=True, center=True, right=True)
            self.changed.emit()
            return
        self.status = code
        self.settings.setValue(self.prefix + "last_error", code)
        self.failures += 1
        retry_after = getattr(self.worker, "retry_after", None)
        if type(retry_after) is int and retry_after > 0:
            self._retry_not_before = max(
                self._retry_not_before, monotonic() + min(retry_after, MAX_RETRY_AFTER_SECONDS)
            )
        delay = min(60, 5 * 2 ** min(self.failures, 4)) * 60 * 1000
        remaining = max(0, ceil((self._retry_not_before - monotonic()) * 1000))
        self.timer.setInterval(max(delay, remaining))
        if self.worker and self.worker.operation in {"sync", "refresh"}:
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
