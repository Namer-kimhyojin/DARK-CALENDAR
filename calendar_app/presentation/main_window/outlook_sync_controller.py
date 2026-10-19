# -*- coding: utf-8 -*-
"""UI-thread coordinator with isolated DB connections in background workers."""

from contextlib import suppress
from datetime import datetime
from math import ceil
import sqlite3
from time import monotonic

from PyQt6.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal

from calendar_app.app_paths import DB_PATH, get_app_data_dir
from calendar_app.application.calendar_sync_contract import CalendarSyncError
from calendar_app.infrastructure.calendar_sync.engine import CalendarSyncEngine
from calendar_app.infrastructure.calendar_sync.http_retry import MAX_RETRY_AFTER_SECONDS
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
        self.retry_after = None

    def run(self):
        client = None
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
            if self.isInterruptionRequested():
                return
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
            self.retry_after = getattr(exc, "retry_after", None)
            self.failed.emit(str(exc))
        except ImportError:
            self.failed.emit("dependency_unavailable")
        except Exception:
            # Do not expose OAuth responses, user data or secrets through logs/UI.
            self.failed.emit("operation_failed")
        finally:
            if client is not None:
                try:
                    try:
                        client.headers.clear()
                    finally:
                        client.session.close()
                except Exception:
                    # Cleanup must not leak a second exception out of QThread.run.
                    pass


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
        self._retry_not_before = 0.0
        self.timer = QTimer(app)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(5 * 60 * 1000)
        self.timer.timeout.connect(self.sync)
        self.timer.start()
        QTimer.singleShot(15_000, self.sync)

    @property
    def busy(self):
        return self.worker is not None

    @property
    def retry_remaining_seconds(self):
        return max(0, ceil(self._retry_not_before - monotonic()))

    def start(self, operation):
        if self.busy or getattr(self.app, "_is_shutting_down", False):
            return False
        if operation in {"sync", "refresh"} and monotonic() < self._retry_not_before:
            self.timer.setInterval(max(1, ceil((self._retry_not_before - monotonic()) * 1000)))
            self.status = self.settings.value("outlook_last_error", self.status, type=str)
            self.changed.emit()
            return False
        if operation in {"sync", "refresh"} and self._retry_not_before:
            self._retry_not_before = 0.0
            self.timer.setInterval(5 * 60 * 1000)
        client_id = self.settings.value("outlook_client_id", "", type=str)
        if not client_id:
            self.status = "client_id_required"
            self.changed.emit()
            return False
        account = self.settings.value("outlook_account_id", "", type=str)
        self.status = operation
        worker = None
        try:
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
        except Exception:
            running = False
            if worker is not None:
                with suppress(RuntimeError):
                    running = worker.isRunning()
            if running:
                self._failed("operation_failed")
                worker.requestInterruption()
                return False
            self.worker = None
            if worker in self.app._bg_workers:
                self.app._bg_workers.remove(worker)
            if worker is not None:
                with suppress(RuntimeError):
                    worker.deleteLater()
            self._failed("operation_failed")
            return False
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
        self._retry_not_before = 0.0
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
            if not result.get("issues"):
                self.settings.setValue(
                    "outlook_last_success",
                    datetime.now().astimezone().isoformat(timespec="seconds"),
                )
        self.status = (
            "connected"
            if operation == "login"
            else "disconnected"
            if operation == "disconnect"
            else "refreshed"
            if operation == "refresh"
            else "completed_with_issues"
            if result.get("issues")
            else "completed"
        )
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
        self.settings.setValue("outlook_last_error", code)
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
            # Earlier calendars may already have committed before a later failure.
            self.app.schedule_panel_refresh(left=True, center=True, right=True)
        self.changed.emit()

    def _finished(self):
        worker = self.sender()
        if worker in self.app._bg_workers:
            self.app._bg_workers.remove(worker)
        if worker is self.worker:
            self.worker = None
        if worker:
            worker.deleteLater()
        self.changed.emit()


def open_outlook_settings(app, section="services", from_sync_hub=False):
    from calendar_app.presentation.dialogs.outlook_settings_dialog import OutlookSettingsDialog

    dialog = OutlookSettingsDialog(app, app._outlook_sync_controller)
    dialog.setProperty("syncHubChild", from_sync_hub)
    dialog.tabs.setCurrentIndex(0 if section == "services" else 1)
    dialog.exec()
