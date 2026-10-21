# -*- coding: utf-8 -*-
"""Partial completion and delayed worker signals preserve accurate provider state."""

import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QObject, pyqtSignal
import pytest

from tests.test_calendar_sync_coordinator import ui as coordinated_ui  # noqa: F401
from tests.test_sync_controller_lifecycle import controller  # noqa: F401


@pytest.mark.parametrize("issues", [1, 3])
def test_partial_completion_preserves_full_success_time(controller, issues):
    _, host, ctrl, prefix, _, _ = controller
    previous = "2026-10-06T09:00:00+09:00"
    host.settings.setValue(prefix + "last_success", previous)
    host.settings.setValue(prefix + "last_error", "network_unavailable")
    summary = {"imported": 2, "updated": 1, "created": 0, "deleted": 0, "issues": issues}
    result = summary if prefix == "outlook_" else {"summary": summary, "calendars": []}
    ctrl._result("sync", result)
    assert host.settings.value(prefix + "last_success") == previous
    assert ctrl.status == "completed_with_issues"
    assert ctrl.summary == summary
    assert not host.settings.contains(prefix + "last_error")
    host.schedule_panel_refresh.assert_called_once_with(left=True, center=True, right=True)


def test_complete_cycle_records_full_success(controller):
    _, host, ctrl, prefix, _, _ = controller
    host.settings.setValue(prefix + "last_success", "previous")
    summary = {"imported": 1, "updated": 0, "created": 0, "deleted": 0, "issues": 0}
    result = summary if prefix == "outlook_" else {"summary": summary, "calendars": []}
    ctrl._result("sync", result)
    assert host.settings.value(prefix + "last_success") != "previous"
    assert ctrl.status == "completed"


def test_calendar_failures_persist_and_clear_after_recovery(controller):
    from calendar_app.infrastructure.calendar_sync.status import load_calendar_errors

    _, host, ctrl, prefix, _, _ = controller
    key = ("outlook" if prefix == "outlook_" else "caldav") + "::fixture"
    previous = "2026-10-06T09:00:00+09:00"
    host.settings.setValue(prefix + "last_success", previous)
    summary = {"issues": 1, "calendar_errors": {key: "calendar_access_lost"}}
    result = summary if prefix == "outlook_" else {"summary": summary, "calendars": []}
    ctrl._result("sync", result)
    assert load_calendar_errors(host.settings, prefix) == {key: "calendar_access_lost"}
    assert host.settings.value(prefix + "last_success") == previous
    assert ctrl.status == "completed_with_issues"
    summary = {"issues": 0, "calendar_errors": {}}
    result = summary if prefix == "outlook_" else {"summary": summary, "calendars": []}
    ctrl._result("sync", result)
    assert load_calendar_errors(host.settings, prefix) == {}
    assert ctrl.status == "completed"


def test_discovery_result_persists_missing_calendar_diagnostic(controller):
    from calendar_app.infrastructure.calendar_sync.status import load_calendar_errors

    _, host, ctrl, prefix, _, _ = controller
    key = ("outlook" if prefix == "outlook_" else "caldav") + "::fixture"
    ctrl._result("refresh", {"calendars": [], "calendar_errors": {key: "calendar_access_lost"}})
    assert load_calendar_errors(host.settings, prefix) == {key: "calendar_access_lost"}
    ctrl._result("disconnect", {})
    assert load_calendar_errors(host.settings, prefix) == {}


def test_transport_failure_uses_existing_service_backoff(controller):
    _, host, ctrl, prefix, _, _ = controller
    previous = "2026-10-06T09:00:00+09:00"
    host.settings.setValue(prefix + "last_success", previous)
    ctrl.worker = SimpleNamespace(operation="sync", retry_after=None)
    ctrl._failed("network_unavailable")
    ctrl.worker = None
    assert ctrl.failures == 1
    assert ctrl.timer.interval() == 600_000
    assert ctrl.status == "network_unavailable"
    assert host.settings.value(prefix + "last_success") == previous


def test_calendar_list_refresh_cannot_clear_unverified_event_failure(controller):
    from calendar_app.infrastructure.calendar_sync.status import (
        load_calendar_errors,
        save_calendar_errors,
    )

    _, host, ctrl, prefix, _, _ = controller
    provider = "outlook" if prefix == "outlook_" else "caldav"
    invalid, missing = provider + "::invalid", provider + "::missing"
    save_calendar_errors(
        host.settings, prefix, {invalid: "invalid_event_time", missing: "calendar_access_lost"}
    )
    ctrl._result("refresh", {"calendars": [], "calendar_errors": {}})
    assert load_calendar_errors(host.settings, prefix) == {invalid: "invalid_event_time"}


def test_oversized_calendar_diagnostics_do_not_escape_result_slot(controller):
    from calendar_app.infrastructure.calendar_sync.status import (
        load_calendar_errors,
        save_calendar_errors,
    )

    _, host, ctrl, prefix, _, _ = controller
    provider = "outlook" if prefix == "outlook_" else "caldav"
    previous = {provider + "::previous": "invalid_remote_event"}
    save_calendar_errors(host.settings, prefix, previous)
    host.settings.setValue(prefix + "last_success", "previous-success")
    errors = {provider + "::" + str(n) + "x" * 220: "invalid_event_time" for n in range(700)}
    summary = {"issues": len(errors), "calendar_errors": errors}
    result = summary if prefix == "outlook_" else {"summary": summary, "calendars": []}
    ctrl._result("sync", result)
    assert ctrl.status == "operation_failed"
    assert host.settings.value(prefix + "last_success") == "previous-success"
    assert load_calendar_errors(host.settings, prefix) == previous


class FinishedWorker(QObject):
    finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.deleteLater = Mock()


def test_old_worker_finish_keeps_current_worker_busy(controller):
    _, host, ctrl, _, _, _ = controller
    old, current = FinishedWorker(), FinishedWorker()
    host._bg_workers[:] = [old, current]
    ctrl.worker = current
    old.finished.connect(ctrl._finished)
    old.finished.emit()
    assert ctrl.worker is current
    assert ctrl.busy
    assert host._bg_workers == [current]
    old.deleteLater.assert_called_once()
    ctrl.worker = None
    host._bg_workers.clear()


@pytest.mark.parametrize("service", ["outlook", "icloud", "naver"])
def test_partial_summary_remains_visible_if_issue_metadata_lags(coordinated_ui, service):
    fixture = coordinated_ui
    ctrl = fixture.coordinator.controllers()[service]
    ctrl.status = "completed_with_issues"
    ctrl.summary = {"issues": 2}
    fixture.coordinator.refresh()
    state = fixture.coordinator.states[service]
    assert state["issues"] == 2
    assert not state["error"]
    assert state["can_sync"]
    assert fixture.host.sync_status_text_lbl.text()


def test_retry_after_blocks_manual_auto_and_refresh_until_deadline(controller, monkeypatch):
    _, host, ctrl, prefix, module, _ = controller
    monkeypatch.setattr(module, "monotonic", lambda: 100.0, raising=False)
    host.settings.setValue("outlook_client_id", "fixture")
    host.settings.setValue(prefix + "enabled", True)
    ctrl.worker = SimpleNamespace(operation="sync", retry_after=9_000)
    code = "graph_http_429" if prefix == "outlook_" else "remote_http_429"
    ctrl._failed(code)
    ctrl.worker = None
    worker_factory = Mock()
    monkeypatch.setattr(
        module, "OutlookWorker" if prefix == "outlook_" else "CalDAVWorker", worker_factory
    )
    assert ctrl.timer.interval() >= 9_000_000
    assert ctrl.start("sync") is False
    ctrl.status = "selection_saved"
    assert ctrl.start("refresh") is False
    assert ctrl.status == code
    ctrl.sync(force=True)
    ctrl.sync()
    worker_factory.assert_not_called()
    assert ctrl.timer.interval() >= 9_000_000
    monkeypatch.setattr(module, "monotonic", lambda: 9_101.0)
    assert ctrl.start("sync") is True
    worker_factory.assert_called_once()
    ctrl.worker = None
    host._bg_workers.clear()


@pytest.mark.parametrize("delay", [None, "9000", True, -1, 0])
def test_invalid_retry_delay_retains_normal_error_backoff(controller, delay):
    _, _, ctrl, prefix, _, _ = controller
    ctrl.worker = SimpleNamespace(operation="sync", retry_after=delay)
    ctrl._failed("graph_http_429" if prefix == "outlook_" else "remote_http_429")
    ctrl.worker = None
    assert ctrl.timer.interval() == 600_000


def test_successful_connection_clears_prior_retry_deadline(controller, monkeypatch):
    _, host, ctrl, prefix, module, result = controller
    monkeypatch.setattr(module, "monotonic", lambda: 100.0, raising=False)
    ctrl.worker = SimpleNamespace(operation="sync", retry_after=9_000)
    ctrl._failed("graph_http_429" if prefix == "outlook_" else "remote_http_429")
    ctrl.worker = None
    result["account"] = "old-account"
    ctrl._result("login", result)
    host.settings.setValue("outlook_client_id", "fixture")
    factory = Mock()
    monkeypatch.setattr(
        module, "OutlookWorker" if prefix == "outlook_" else "CalDAVWorker", factory
    )
    assert ctrl.start("refresh") is True
    factory.assert_called_once()
    ctrl.worker = None
    host._bg_workers.clear()


def test_early_retry_timer_reschedules_remainder_and_restores_normal_interval(
    controller, monkeypatch
):
    _, host, ctrl, prefix, module, _ = controller
    monkeypatch.setattr(module, "monotonic", lambda: 100.0)
    host.settings.setValue("outlook_client_id", "fixture")
    ctrl.worker = SimpleNamespace(operation="sync", retry_after=9_000)
    ctrl._failed("graph_http_429" if prefix == "outlook_" else "remote_http_429")
    ctrl.worker = None
    factory = Mock()
    monkeypatch.setattr(
        module, "OutlookWorker" if prefix == "outlook_" else "CalDAVWorker", factory
    )
    monkeypatch.setattr(module, "monotonic", lambda: 9_099.999)
    assert ctrl.start("sync") is False
    factory.assert_not_called()
    assert 1 <= ctrl.timer.interval() <= 2
    monkeypatch.setattr(module, "monotonic", lambda: 9_100.001)
    assert ctrl.start("sync") is True
    assert ctrl.timer.interval() == 300_000
    ctrl.worker = None
    host._bg_workers.clear()


@pytest.mark.parametrize("change", ["url", "paused", "removed", "unreadable", "unchanged"])
def test_ics_completion_metadata_applies_only_to_current_subscription(
    coordinated_ui, monkeypatch, change
):
    fixture = coordinated_ui
    key, original = "ics::fixture", "https://fixture.invalid/old.ics"
    with sqlite3.connect(fixture.path) as conn:
        conn.execute(
            "INSERT INTO calendar(id,type,name,ics_url) VALUES(?,'ics','Feed',?)", (key, original)
        )
    fixture.coordinator.refresh()
    fixture.host.settings.setValue("sync_ics_error_codes", {key: "network_unavailable"})
    fixture.host.settings.setValue("sync_ics_last_success", "previous")
    if change == "unreadable":
        monkeypatch.setattr(
            fixture.coordinator, "_calendars", Mock(side_effect=sqlite3.OperationalError("locked"))
        )
    else:
        with sqlite3.connect(fixture.path) as conn:
            if change == "url":
                conn.execute(
                    "UPDATE calendar SET ics_url='https://fixture.invalid/new.ics' WHERE id=?",
                    (key,),
                )
            elif change == "paused":
                conn.execute("UPDATE calendar SET is_active=0 WHERE id=?", (key,))
            elif change == "removed":
                conn.execute("DELETE FROM calendar WHERE id=?", (key,))
    fixture.coordinator.ics_worker = SimpleNamespace(
        calendars=[{"id": key, "ics_url": original}],
        is_cancelled=lambda: False,
    )
    try:
        fixture.coordinator._ics_result({key: (1, 0, None)})
        if change == "unchanged":
            assert fixture.host.settings.value("sync_ics_error_codes") == {}
            assert fixture.host.settings.value("sync_ics_last_success") != "previous"
        else:
            assert fixture.host.settings.value("sync_ics_error_codes") == {
                key: "network_unavailable"
            }
            assert fixture.host.settings.value("sync_ics_last_success") == "previous"
        fixture.host.schedule_panel_refresh.assert_called_once_with(
            left=True, center=True, right=True
        )
    finally:
        fixture.coordinator.ics_worker = None


def test_feed_timezone_error_has_distinct_recovery_from_app_timezone(monkeypatch):
    from calendar_app.presentation.dialogs import sync_feedback

    monkeypatch.setattr(sync_feedback, "t", lambda key, fallback: fallback)
    app_message = sync_feedback.sync_error_message("invalid_timezone")
    feed_message = sync_feedback.sync_error_message("invalid_calendar_timezone")
    assert "Asia/Seoul" in app_message
    assert "구독" in feed_message
    assert "기존 일정은 보존" in feed_message
    assert app_message != feed_message


def test_failed_calendar_refresh_updates_changed_calendar_metadata(controller):
    _, host, ctrl, _, _, _ = controller
    ctrl.worker = SimpleNamespace(operation="refresh", retry_after=None)
    try:
        ctrl._failed("calendar_access_lost")
        host.schedule_panel_refresh.assert_called_once_with(left=True, center=True, right=True)
        assert ctrl.status == "calendar_access_lost"
    finally:
        ctrl.worker = None


def test_successful_calendar_refresh_updates_changed_calendar_metadata(controller):
    _, host, ctrl, _, _, _ = controller
    ctrl._result("refresh", {"calendars": []})
    host.schedule_panel_refresh.assert_called_once_with(left=True, center=True, right=True)
    assert ctrl.status == "refreshed"


@pytest.mark.parametrize(
    "code, expected",
    [
        ("account_mismatch", "account_mismatch"),
        ("account_unverified", "account_unverified"),
        ("unsafe detail", "operation_failed"),
    ],
)
def test_google_account_guard_keeps_safe_recovery_code(coordinated_ui, code, expected):
    fixture = coordinated_ui
    fixture.host._last_gcal_sync_error = code
    fixture.coordinator.record_google_result(False)
    fixture.coordinator.refresh()
    assert fixture.coordinator.states["google"]["error"] == expected
    assert fixture.host.settings.value("sync_google_last_error") == expected
    if code in {"account_mismatch", "account_unverified"}:
        from calendar_app.presentation.dialogs.sync_feedback import sync_error_message

        message = sync_error_message(expected)
        assert message != sync_error_message("operation_failed")
