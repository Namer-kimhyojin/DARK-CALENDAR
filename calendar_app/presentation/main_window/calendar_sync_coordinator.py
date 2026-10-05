# -*- coding: utf-8 -*-
"""Coordinate existing provider engines without copying events between services."""

from datetime import datetime
from pathlib import Path
import sqlite3

from PyQt6.QtCore import QMetaObject, QObject, Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

from calendar_app.app_paths import DB_PATH, TOKEN_PATH
from calendar_app.infrastructure.google_sync.common import is_gcal_enabled
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.sync_feedback import sync_error_message
from calendar_app.shared.icon_map import ICON, icon

PROVIDERS = ("google", "outlook", "icloud", "naver", "ics")
_NORMAL = {"idle", "connected", "disconnected", "completed", "selection_saved", "refreshed"}


def provider_name(provider):
    return {
        "google": "Google Calendar",
        "outlook": "Outlook · Microsoft 365",
        "icloud": "iCloud",
        "naver": t("caldav.naver", "네이버"),
        "ics": t("sync_unified.ics", "ICS 구독"),
    }[provider]


def provider_status(state):
    if state["busy"]:
        return t("sync_ui.working", "작업 중...")
    if state.get("error"):
        return sync_error_message(state["error"])
    if not state["connected"]:
        return t("sync_ui.not_connected", "연결되지 않음")
    if state.get("needs_selection"):
        return t("sync_unified.select_first", "가져올 캘린더를 선택하고 저장하세요.")
    if state["issues"]:
        return t("sync_unified.issue_count", "확인할 문제 {count}건").format(count=state["issues"])
    return (
        t("sync_ui.auto_on", "자동 동기화 켜짐")
        if state["auto"]
        else t("sync_ui.auto_off", "자동 동기화 꺼짐")
    )


class IcsSyncWorker(QThread):
    result = pyqtSignal(object)

    def __init__(self, calendars, parent, local_zone=None):
        super().__init__(parent)
        self.calendars = calendars
        self.local_zone = local_zone

    def run(self):
        results = {}
        try:
            from calendar_app.infrastructure.ics.ics_fetcher import fetch_and_sync

            for calendar in self.calendars:
                if self.isInterruptionRequested():
                    break
                try:
                    results[calendar["id"]] = fetch_and_sync(
                        calendar["id"],
                        calendar["ics_url"],
                        local_zone=self.local_zone,
                        cancelled=self.isInterruptionRequested,
                    )
                except Exception:
                    results[calendar["id"]] = (0, 0, "operation_failed")
            self.result.emit(results)
        finally:
            from calendar_app.shared.background_worker import _close_db_connection

            _close_db_connection()


class CalendarSyncCoordinator(QObject):
    changed = pyqtSignal()

    def __init__(self, app, database_path=DB_PATH, calendar_source=None):
        super().__init__(app)
        self.app, self.settings = app, app.settings
        self.database_path = database_path
        self.calendar_source = calendar_source
        self.ics_worker = None
        self.states = {}
        self.issue_rows = []
        self.calendar_rows = []
        self.calendar_providers = {}
        self.local_change_timer = QTimer(self)
        self.local_change_timer.setSingleShot(True)
        self.local_change_timer.timeout.connect(self._flush_local_change)
        self._local_change_include_google = False
        for controller in self.controllers().values():
            if controller:
                controller.changed.connect(self.refresh)
        self.refresh()

    def controllers(self):
        return {
            "outlook": getattr(self.app, "_outlook_sync_controller", None),
            **getattr(self.app, "_caldav_sync_controllers", {}),
        }

    def _metadata(self):
        counts, selected, issues = {}, {}, []
        if not Path(self.database_path).exists():
            return counts, selected, issues
        conn = sqlite3.connect(self.database_path, timeout=1)
        conn.row_factory = sqlite3.Row
        try:
            tables = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if "calendar_sync_calendar" in tables:
                for row in conn.execute(
                    "SELECT account_id,local_id,is_active FROM calendar_sync_calendar c JOIN calendar v ON v.id=c.local_id"
                ):
                    account = row["account_id"]
                    self.calendar_providers[row["local_id"]] = (
                        "naver"
                        if account.startswith("caldav::naver::")
                        else "icloud"
                        if account.startswith("caldav::icloud::")
                        else "outlook"
                    )
                    if row["is_active"]:
                        selected[account] = selected.get(account, 0) + 1
                if {"calendar_sync_issue", "calendar_sync_event", "unified_task"} <= tables:
                    for row in conn.execute(
                        "SELECT c.account_id,i.task_id,i.kind,t.name FROM calendar_sync_issue i JOIN calendar_sync_event e ON e.task_id=i.task_id JOIN calendar_sync_calendar c ON c.local_id=e.calendar_id LEFT JOIN unified_task t ON t.id=i.task_id"
                    ):
                        counts[row["account_id"]] = counts.get(row["account_id"], 0) + 1
                        issues.append(dict(row))
                if "calendar_sync_delete_queue" in tables:
                    for row in conn.execute(
                        "SELECT c.account_id,q.event_id,q.error AS kind FROM calendar_sync_delete_queue q JOIN calendar_sync_calendar c ON c.local_id=q.calendar_id WHERE q.error IS NOT NULL"
                    ):
                        counts[row["account_id"]] = counts.get(row["account_id"], 0) + 1
                        issues.append(dict(row))
        finally:
            conn.close()
        return counts, selected, issues

    def _calendars(self):
        if self.calendar_source:
            return self.calendar_source()
        from calendar_app.infrastructure.db.calendar_repo import list_calendars

        return list_calendars(include_inactive=True)

    @pyqtSlot()
    def refresh(self, refresh_issues=True):
        app = QApplication.instance()
        if app and app.thread() != QThread.currentThread():
            QMetaObject.invokeMethod(self, "refresh", Qt.ConnectionType.QueuedConnection)
            return
        if getattr(self.app, "_is_shutting_down", False):
            return
        counts, selected = {}, {}
        try:
            counts, selected, self.issue_rows = self._metadata()
            self.calendar_rows = self._calendars()
            self.calendar_providers.update(
                {
                    c["id"]: "google" if c["type"] == "gcal" else c["type"]
                    for c in self.calendar_rows
                    if c["type"] in {"gcal", "outlook", "ics"}
                }
            )
            if refresh_issues:
                from calendar_app.infrastructure.db import task_repo

                self.app._gcal_sync_issue_count = (
                    task_repo.count_unified_task_gcal_errors()
                    + task_repo.count_gcal_delete_queue_errors()
                    + task_repo.count_gcal_sync_conflicts()
                )
        except (sqlite3.Error, OSError, RuntimeError):
            # Keep previous issues when metadata temporarily cannot be read.
            counts = {
                s.get("account", ""): s["issues"]
                for k, s in self.states.items()
                if k not in {"google", "ics"}
            }
            selected = {s.get("account", ""): s.get("selected", 0) for s in self.states.values()}
        google = getattr(self.app, "gcal_sync", None)
        enabled = is_gcal_enabled(self.settings)
        authenticated = bool(google and getattr(google, "is_authenticated", False))
        connected = enabled and (authenticated or Path(TOKEN_PATH).exists())
        waiting = (
            enabled and not authenticated and getattr(self.app, "_gcal_waiting_for_auth", False)
        )
        busy = (
            getattr(self.app, "_gcal_sync_in_progress", False)
            or self._worker_running("_sync_worker")
            or self._worker_running("_auth_worker")
        )
        states = {
            "google": {
                "connected": connected,
                "busy": busy,
                "auto": self.settings.value("sync_google_auto", True, type=bool),
                "issues": int(getattr(self.app, "_gcal_sync_issue_count", 0)),
                "can_sync": connected and not waiting,
                "error": "login_required"
                if waiting
                else self.settings.value("sync_google_last_error", "", type=str)
                if enabled
                else "",
                "last_success": self.settings.value("last_successful_sync", "", type=str),
            }
        }
        for key, controller in self.controllers().items():
            prefix = "outlook_" if key == "outlook" else "caldav_" + key + "_"
            account = self.settings.value(prefix + "account_id", "", type=str)
            status = controller.status if controller else "idle"
            states[key] = {
                "account": account,
                "connected": bool(account),
                "busy": bool(controller and controller.busy),
                "auto": self.settings.value(prefix + "enabled", False, type=bool),
                "selected": selected.get(account, 0),
                "needs_selection": bool(account) and not selected.get(account),
                "issues": counts.get(account, 0),
                "can_sync": bool(account and controller and selected.get(account)),
                "error": status
                if status not in _NORMAL and not (controller and controller.busy)
                else "",
                "last_success": self.settings.value(prefix + "last_success", "", type=str),
            }
        ics = [
            c
            for c in self.calendar_rows
            if c.get("type") == "ics" and c.get("is_active", 1) and c.get("ics_url")
        ]
        states["ics"] = {
            "connected": bool(ics),
            "busy": self.ics_worker is not None,
            "auto": self.settings.value("sync_ics_auto", True, type=bool),
            "issues": self.settings.value("sync_ics_issue_count", 0, type=int) if ics else 0,
            "can_sync": bool(ics),
            "error": self.settings.value("sync_ics_last_error", "", type=str) if ics else "",
            "last_success": self.settings.value("sync_ics_last_success", "", type=str),
        }
        changed = states != self.states
        self.states = states
        self._paint_status()
        if changed:
            self.changed.emit()

    def _worker_running(self, attribute):
        worker = getattr(self.app, attribute, None)
        try:
            return bool(worker and worker.isRunning())
        except RuntimeError:
            return False

    def sync(self, provider=None):
        if getattr(self.app, "_is_shutting_down", False):
            return []
        if provider is not None and provider not in PROVIDERS:
            return []
        self.refresh()
        started = []
        for key in [provider] if provider in PROVIDERS else PROVIDERS:
            state = self.states.get(key, {})
            if not state.get("can_sync") or state.get("busy"):
                continue
            try:
                if key == "google":
                    self.app.sync_google_calendar(silent=True)
                    started.append(key)
                elif key == "ics":
                    if self.sync_ics(force=True):
                        started.append(key)
                else:
                    controller = self.controllers().get(key)
                    if controller and controller.start("sync"):
                        started.append(key)
            except Exception:
                import logging

                logging.getLogger(__name__).warning("Sync dispatch failed for provider %s", key)
                if key == "google":
                    self.settings.setValue("sync_google_last_error", "operation_failed")
                elif key == "ics":
                    self.settings.setValue("sync_ics_last_error", "ics_fetch_failed")
                else:
                    self.controllers()[key].status = "operation_failed"
        self.refresh()
        return started

    def set_auto(self, provider, enabled):
        if provider not in PROVIDERS:
            return
        key = {
            "google": "sync_google_auto",
            "outlook": "outlook_enabled",
            "icloud": "caldav_icloud_enabled",
            "naver": "caldav_naver_enabled",
            "ics": "sync_ics_auto",
        }[provider]
        self.settings.setValue(key, bool(enabled))
        if provider == "google":
            self.app.update_gcal_sync_timer()
        self.refresh(refresh_issues=False)

    def schedule_local_change(self, include_google=False):
        if getattr(self.app, "_is_shutting_down", False):
            return
        self._local_change_include_google |= include_google
        self.local_change_timer.start(800)

    def _flush_local_change(self):
        include_google = self._local_change_include_google
        self._local_change_include_google = False
        self.sync_after_local_change(include_google)

    def sync_after_local_change(self, include_google=True):
        """Debounced writes honor automatic pause and service failure backoff."""
        if getattr(self.app, "_is_shutting_down", False):
            return
        self.refresh(refresh_issues=False)
        for key in ("google", "outlook", "icloud") if include_google else ("outlook", "icloud"):
            state = self.states.get(key, {})
            if (
                not state.get("auto")
                or not state.get("can_sync")
                or state.get("busy")
                or state.get("error")
            ):
                continue
            try:
                if key == "google":
                    self.app.sync_google_calendar_silent()
                else:
                    self.controllers()[key].sync()
            except Exception:
                import logging

                logging.getLogger(__name__).warning(
                    "Automatic sync dispatch failed for provider %s", key
                )
        self.refresh(refresh_issues=False)

    def sync_ics(self, force=False):
        if self.ics_worker or getattr(self.app, "_is_shutting_down", False):
            return False
        if not force and not self.settings.value("sync_ics_auto", True, type=bool):
            return False
        calendars = [
            c
            for c in self._calendars()
            if c.get("type") == "ics" and c.get("is_active", 1) and c.get("ics_url")
        ]
        if not calendars:
            return False
        worker = IcsSyncWorker(
            calendars, self, self.settings.value("gcal_timezone", "Asia/Seoul", type=str)
        )
        self.ics_worker = worker
        self.app._bg_workers.append(worker)
        worker.result.connect(self._ics_result)
        worker.finished.connect(self._ics_finished)
        worker.start()
        self.refresh(refresh_issues=False)
        return True

    def _ics_result(self, results):
        if getattr(self.app, "_is_shutting_down", False):
            return
        if self.ics_worker and self.ics_worker.isInterruptionRequested():
            return
        errors = sum(bool(row[2]) for row in results.values())
        self.settings.setValue(
            "sync_ics_failed_ids", [key for key, row in results.items() if row[2]]
        )
        self.settings.setValue("sync_ics_issue_count", errors)
        self.settings.setValue("sync_ics_last_error", "ics_fetch_failed" if errors else "")
        if results and not errors:
            self.settings.setValue(
                "sync_ics_last_success", datetime.now().astimezone().isoformat(timespec="seconds")
            )
        if any(row[0] or row[1] for row in results.values()):
            self.app.schedule_panel_refresh(left=True, center=True, right=True)

    def _ics_finished(self):
        worker = self.sender()
        if worker in self.app._bg_workers:
            self.app._bg_workers.remove(worker)
        self.ics_worker = None
        worker.deleteLater()
        self.refresh()

    def record_google_result(self, success, skipped=False):
        if not skipped:
            self.settings.setValue("sync_google_last_error", "" if success else "operation_failed")

    def stop(self):
        self.local_change_timer.stop()
        if self.ics_worker:
            self.ics_worker.requestInterruption()

    def _paint_status(self):
        connected = sum(s["connected"] for s in self.states.values())
        busy = sum(s["busy"] for s in self.states.values())
        issues = sum(s["issues"] for s in self.states.values())
        failed = any(s.get("error") and s["connected"] for s in self.states.values())
        if busy:
            text, symbol = (
                t("sync_unified.running", "동기화 중 {count}").format(count=busy),
                ICON.SYNC,
            )
        elif issues or failed:
            text, symbol = t("sync_unified.attention", "동기화 확인 필요"), ICON.WARNING
        elif connected:
            text, symbol = (
                t("sync_unified.connected_count", "연결 {count}").format(count=connected),
                ICON.CLOUD,
            )
        else:
            text, symbol = t("sync_unified.local_only", "로컬 모드"), ICON.SYNC
        tooltip = (
            t("sync_unified.sync_all", "연결된 모든 캘린더 동기화")
            + "\n"
            + "\n".join(
                provider_name(k) + ": " + provider_status(s) for k, s in self.states.items()
            )
        )
        color = (
            "#d39a2a"
            if (issues or failed) and not busy
            else self.settings.value("theme_color", "#4da6ff", type=str)
        )
        button = getattr(self.app, "sync_action_btn", None)
        if button:
            button.setIcon(icon(symbol, color=color))
            button.setToolTip(tooltip)
            button.setAccessibleName(t("sync_unified.sync_all", "연결된 모든 캘린더 동기화"))
            button.setAccessibleDescription(tooltip)
        label = getattr(self.app, "sync_status_text_lbl", None)
        if label:
            label.setText(text)
            label.setToolTip(tooltip)
        old_label = getattr(self.app, "sync_status_lbl", None)
        if old_label and button:
            old_label.hide()
