# -*- coding: utf-8 -*-
"""Coordinate existing provider engines without copying events between services."""

from datetime import datetime
from pathlib import Path
import sqlite3
import threading

from PyQt6.QtCore import QMetaObject, QObject, Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

from calendar_app.app_paths import DB_PATH, TOKEN_PATH
from calendar_app.application.calendar_provider_catalog import (
    CALDAV_SERVICES,
    PROVIDER_NAMES,
    PROVIDERS,
    account_provider,
)
from calendar_app.infrastructure.google_sync.common import is_gcal_enabled
from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.ics.subscriptions import ICS_ERRORS, subscription_errors
from calendar_app.presentation.dialogs.sync_feedback import (
    google_sync_error_code,
    sync_error_message,
)
from calendar_app.presentation.dialogs.sync_recovery import requires_account_reconnection
from calendar_app.presentation.main_window.top_bar_builder import build_sync_toolbar_styles
from calendar_app.shared.icon_map import ICON, icon

_NORMAL = {
    "idle",
    "connected",
    "disconnected",
    "completed",
    "completed_with_issues",
    "selection_saved",
    "refreshed",
    "cancelled",
}


def provider_name(provider):
    if provider == "naver":
        return t("caldav.naver", "네이버")
    if provider == "ics":
        return t("sync_unified.ics", "ICS 구독")
    return PROVIDER_NAMES[provider]


def provider_status(state):
    if state["busy"]:
        return t("sync_ui.working", "작업 중...")
    if state.get("paused"):
        return t(
            "sync_recovery.paused_hint",
            "계정 연결은 유지됩니다. 연결 설정에서 동기화를 다시 켜세요.",
        )
    if state.get("retry_remaining"):
        return t(
            "sync_recovery.wait_hint",
            "서비스 요청 제한으로 {seconds}초 후 다시 시도할 수 있습니다.",
            seconds=state["retry_remaining"],
        )
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
        self._cancelled = threading.Event()

    def requestInterruption(self):
        self._cancelled.set()
        super().requestInterruption()

    def is_cancelled(self):
        return self._cancelled.is_set() or self.isInterruptionRequested()

    def run(self):
        results = {}
        try:
            from calendar_app.infrastructure.ics.ics_fetcher import fetch_and_sync

            for calendar in self.calendars:
                if self.is_cancelled():
                    break
                try:
                    results[calendar["id"]] = fetch_and_sync(
                        calendar["id"],
                        calendar["ics_url"],
                        local_zone=self.local_zone,
                        cancelled=self.is_cancelled,
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
                    self.calendar_providers[row["local_id"]] = account_provider(account)
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
        previous_rows = self.calendar_rows
        previous_providers = self.calendar_providers.copy()
        previous_issues = self.issue_rows
        try:
            self.calendar_providers = {}
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
            self.calendar_rows = previous_rows
            self.calendar_providers = previous_providers
            self.issue_rows = previous_issues
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
        connected = authenticated or Path(TOKEN_PATH).exists()
        waiting = (
            enabled and not authenticated and getattr(self.app, "_gcal_waiting_for_auth", False)
        )
        busy = (
            getattr(self.app, "_gcal_sync_in_progress", False)
            or self._worker_running("_sync_worker")
            or self._worker_running("_auth_worker")
            or any(
                getattr(worker, "provider", None) == "google" and self._is_worker_running(worker)
                for worker in getattr(self.app, "_bg_workers", [])
            )
        )
        google_error = (
            "login_required"
            if waiting
            else self.settings.value("sync_google_last_error", "", type=str)
            if enabled
            else ""
        )
        google_selected = sum(
            bool(c.get("is_active", 1)) for c in self.calendar_rows if c.get("type") == "gcal"
        )
        google_has_calendars = any(c.get("type") == "gcal" for c in self.calendar_rows)
        google_needs_selection = bool(
            connected
            and enabled
            and self.settings.value("gcal_import_selection_configured", False, type=bool)
            and not google_has_calendars
        )
        states = {
            "google": {
                "connected": connected,
                "busy": busy,
                "auto": enabled and self.settings.value("sync_google_auto", True, type=bool),
                "paused": connected and not enabled,
                "selected": google_selected,
                "import_paused": google_has_calendars and not google_selected,
                "needs_selection": google_needs_selection,
                "issues": int(getattr(self.app, "_gcal_sync_issue_count", 0)),
                "can_sync": bool(
                    connected
                    and enabled
                    and not waiting
                    and not google_needs_selection
                    and not requires_account_reconnection(google_error)
                ),
                "error": google_error,
                "last_success": self.settings.value("last_successful_sync", "", type=str),
            }
        }
        for key, controller in self.controllers().items():
            prefix = "outlook_" if key == "outlook" else "caldav_" + key + "_"
            account = self.settings.value(prefix + "account_id", "", type=str)
            status = controller.status if controller else "idle"
            provider_error = (
                (
                    status
                    if status not in _NORMAL
                    else self.settings.value(prefix + "last_error", "", type=str)
                )
                if not (controller and controller.busy)
                else ""
            )
            issue_count = counts.get(account, 0)
            summary = getattr(controller, "summary", {})
            if status == "completed_with_issues" and isinstance(summary, dict):
                issue_count = max(issue_count, int(summary.get("issues") or 0))
            retry_remaining = getattr(controller, "retry_remaining_seconds", 0) if controller else 0
            states[key] = {
                "account": account,
                "connected": bool(account),
                "busy": bool(controller and controller.busy),
                "auto": self.settings.value(prefix + "enabled", False, type=bool),
                "selected": selected.get(account, 0),
                "needs_selection": bool(account) and not selected.get(account),
                "issues": issue_count,
                "can_sync": bool(
                    account
                    and controller
                    and selected.get(account)
                    and not retry_remaining
                    and not requires_account_reconnection(provider_error)
                ),
                "retry_remaining": retry_remaining,
                "cancelled": status == "cancelled",
                "error": provider_error,
                "last_success": self.settings.value(prefix + "last_success", "", type=str),
            }
        all_ics = [c for c in self.calendar_rows if c.get("type") == "ics"]
        ics = [
            c
            for c in self.calendar_rows
            if c.get("type") == "ics" and c.get("is_active", 1) and c.get("ics_url")
        ]
        errors = subscription_errors(self.settings)
        failed = [c["id"] for c in ics if c["id"] in errors]
        states["ics"] = {
            "connected": bool(all_ics),
            "busy": self.ics_worker is not None,
            "auto": self.settings.value("sync_ics_auto", True, type=bool),
            "selected": len(ics),
            "total": len(all_ics),
            "needs_selection": bool(all_ics) and not ics,
            "issues": len(failed),
            "can_sync": bool(ics),
            "error": "ics_fetch_failed"
            if failed
            else (
                "operation_failed"
                if ics
                and self.settings.value("sync_ics_last_error", "", type=str) == "operation_failed"
                else ""
            ),
            "last_success": self.settings.value("sync_ics_last_success", "", type=str),
        }
        changed = (
            states != self.states
            or previous_rows != self.calendar_rows
            or previous_providers != self.calendar_providers
            or previous_issues != self.issue_rows
        )
        self.states = states
        self._paint_status()
        if changed:
            self.changed.emit()

    def _worker_running(self, attribute):
        worker = getattr(self.app, attribute, None)
        return self._is_worker_running(worker)

    @staticmethod
    def _is_worker_running(worker):
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
                    if self.app.sync_google_calendar(silent=True) is not False:
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
                    self.settings.setValue("sync_ics_last_error", "operation_failed")
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
            **{service: "caldav_" + service + "_enabled" for service in CALDAV_SERVICES},
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
        for key in (
            (("google",) if include_google else ())
            + ("outlook",)
            + tuple(service for service in CALDAV_SERVICES if service != "naver")
        ):
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

    def sync_ics(self, force=False, calendar_ids=None):
        if self.ics_worker or getattr(self.app, "_is_shutting_down", False):
            return False
        if not force and not self.settings.value("sync_ics_auto", True, type=bool):
            return False
        try:
            calendars = [
                c
                for c in self._calendars()
                if c.get("type") == "ics"
                and c.get("is_active", 1)
                and c.get("ics_url")
                and (calendar_ids is None or c["id"] in calendar_ids)
            ]
        except (sqlite3.Error, OSError, RuntimeError):
            self.settings.setValue("sync_ics_last_error", "operation_failed")
            self.refresh(refresh_issues=False)
            return False
        if not calendars:
            return False
        worker = None
        launch_failed = False

        def deliver_result(results):
            if not launch_failed and self.ics_worker is worker:
                self._ics_result(results)

        try:
            worker = IcsSyncWorker(
                calendars, self, self.settings.value("gcal_timezone", "Asia/Seoul", type=str)
            )
            self.ics_worker = worker
            self.app._bg_workers.append(worker)
            worker.result.connect(deliver_result)
            worker.finished.connect(self._ics_finished)
            worker.start()
        except Exception:
            launch_failed = True
            if worker is not None and worker.isRunning():
                # start() may have launched the thread before reporting failure.
                # Keep its owner/reference until the normal finished cleanup.
                worker.requestInterruption()
            else:
                if self.ics_worker is worker:
                    self.ics_worker = None
                if worker is not None:
                    if worker in self.app._bg_workers:
                        self.app._bg_workers.remove(worker)
                    worker.deleteLater()
            self.settings.setValue("sync_ics_last_error", "operation_failed")
            self.refresh(refresh_issues=False)
            return False
        self.refresh(refresh_issues=False)
        return True

    def _ics_result(self, results):
        if getattr(self.app, "_is_shutting_down", False):
            return
        if self.ics_worker and self.ics_worker.is_cancelled():
            if any(row[0] or row[1] for row in results.values()):
                self.app.schedule_panel_refresh(left=True, center=True, right=True)
            return
        if not results:
            return
        committed = any(row[0] or row[1] for row in results.values())
        current_calendars = self.calendar_rows
        original = getattr(self.ics_worker, "calendars", None)
        if isinstance(original, list):
            # A queued completion must not clear errors for a replacement feed.
            try:
                current_calendars = self._calendars()
            except (sqlite3.Error, OSError, RuntimeError):
                self.settings.setValue("sync_ics_last_error", "operation_failed")
                if committed:
                    self.app.schedule_panel_refresh(left=True, center=True, right=True)
                return
            original_urls = {c["id"]: c.get("ics_url") for c in original}
            eligible = {
                c["id"]
                for c in current_calendars
                if c.get("type") == "ics"
                and c.get("is_active", 1)
                and c.get("ics_url")
                and c.get("ics_url") == original_urls.get(c["id"])
            }
            results = {key: row for key, row in results.items() if key in eligible}
            if not results:
                if committed:
                    self.app.schedule_panel_refresh(left=True, center=True, right=True)
                return
        error_codes = subscription_errors(self.settings)
        for key, row in results.items():
            if row[2] == "cancelled":
                continue
            if row[2]:
                error_codes[key] = (
                    row[2]
                    if isinstance(row[2], str) and row[2] in ICS_ERRORS
                    else "operation_failed"
                )
            else:
                error_codes.pop(key, None)
        self.settings.setValue("sync_ics_error_codes", error_codes)
        self.settings.setValue("sync_ics_failed_ids", sorted(error_codes))
        self.settings.setValue("sync_ics_issue_count", len(error_codes))
        self.settings.setValue("sync_ics_last_error", "ics_fetch_failed" if error_codes else "")
        active_ids = {
            c["id"]
            for c in current_calendars
            if c.get("type") == "ics" and c.get("is_active", 1) and c.get("ics_url")
        }
        if (
            active_ids
            and not (active_ids & error_codes.keys())
            and active_ids <= results.keys()
            and all(not r[2] for r in results.values())
        ):
            self.settings.setValue(
                "sync_ics_last_success", datetime.now().astimezone().isoformat(timespec="seconds")
            )
        if committed:
            self.app.schedule_panel_refresh(left=True, center=True, right=True)

    def _ics_finished(self):
        worker = self.sender()
        if worker in self.app._bg_workers:
            self.app._bg_workers.remove(worker)
        if self.ics_worker is worker:
            self.ics_worker = None
        if worker:
            worker.deleteLater()
        self.refresh()

    def record_google_result(self, success, skipped=False):
        if not skipped:
            code = getattr(self.app, "_last_gcal_sync_error", None)
            service = getattr(self.app, "gcal_sync", None)
            safe_code = google_sync_error_code(code, getattr(service, "last_error_status", None))
            self.settings.setValue("sync_google_last_error", "" if success else safe_code)

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
                ICON.SYNC_SETTINGS,
            )
        else:
            text, symbol = t("sync_unified.local_only", "로컬 모드"), ICON.SYNC_SETTINGS
        tooltip = (
            t("sync_ui.hub_title", "캘린더 · 계정 및 동기화")
            + "\n"
            + text
            + "\n"
            + "\n".join(
                provider_name(k) + ": " + provider_status(s) for k, s in self.states.items()
            )
        )
        styles = build_sync_toolbar_styles(
            self.settings, busy=bool(busy), attention=bool(issues or failed)
        )
        button = getattr(self.app, "sync_action_btn", None)
        if button:
            button.setIcon(icon(symbol, color=styles["icon_color"]))
            if button.styleSheet() != styles["button"]:
                button.setStyleSheet(styles["button"])
            button.setToolTip(tooltip)
            button.setAccessibleName(t("sync_ui.hub_title", "캘린더 · 계정 및 동기화"))
            button.setAccessibleDescription(tooltip)
        label = getattr(self.app, "sync_status_text_lbl", None)
        if label:
            label.setText(text)
            if label.styleSheet() != styles["label"]:
                label.setStyleSheet(styles["label"])
            label.setToolTip(tooltip)
            label.setAccessibleDescription(text)
        old_label = getattr(self.app, "sync_status_lbl", None)
        if old_label and button:
            old_label.hide()
