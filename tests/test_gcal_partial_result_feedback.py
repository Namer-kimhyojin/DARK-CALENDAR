# -*- coding: utf-8 -*-
"""Committed Google changes remain visible when the overall run fails."""

from types import MethodType, SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QSettings
import pytest

from calendar_app.presentation.main_window import action_handlers_gcal as actions
from calendar_app.presentation.main_window.calendar_sync_coordinator import CalendarSyncCoordinator


@pytest.fixture(params=["automatic", "manual"])
def feedback(request, tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("last_successful_sync", "2000-01-01 00:00:00")
    settings.setValue("sync_google_last_error", "network_unavailable")
    coordinator = SimpleNamespace(settings=settings)
    coordinator.record_google_result = Mock(
        wraps=MethodType(CalendarSyncCoordinator.record_google_result, coordinator)
    )
    host = SimpleNamespace(
        settings=settings,
        _calendar_sync_coordinator=coordinator,
        _last_gcal_sync_outcome="failed",
        _last_gcal_sync_changed_any=True,
        _last_gcal_sync_refresh_left=True,
        _last_gcal_sync_stats={"push_failures": 1, "pull_changes": 1},
        update_sync_status=Mock(),
        schedule_panel_refresh=Mock(),
        _increase_gcal_failure_backoff=Mock(),
        _reset_gcal_failure_backoff=Mock(),
        _show_sync_issue_popup=Mock(),
    )
    coordinator.app = host
    host._handle_gcal_sync_success = Mock(
        wraps=MethodType(actions.GCalActionsMixin._handle_gcal_sync_success, host)
    )
    monkeypatch.setattr(actions.QApplication, "topLevelWidgets", lambda: [])
    warning, information = Mock(), Mock()
    monkeypatch.setattr(actions.QMessageBox, "warning", warning)
    monkeypatch.setattr(actions.QMessageBox, "information", information)
    callback = (
        actions.GCalActionsMixin._on_sync_finished_manual
        if request.param == "manual"
        else actions.GCalActionsMixin._on_sync_finished
    )
    yield SimpleNamespace(
        host=host,
        settings=settings,
        callback=callback,
        warning=warning,
        information=information,
        manual=request.param == "manual",
    )
    settings.sync()


@pytest.mark.parametrize("refresh_left", [True, False])
def test_partial_failure_refreshes_committed_changes_without_success(feedback, refresh_left):
    ui = feedback
    ui.host._last_gcal_sync_refresh_left = refresh_left
    ui.callback(ui.host, False, "Synthetic partial sync failure")
    ui.host.schedule_panel_refresh.assert_called_once_with(left=refresh_left, center=True)
    assert ui.settings.value("last_successful_sync") == "2000-01-01 00:00:00"
    assert ui.settings.value("sync_google_last_error") == "operation_failed"
    ui.host._handle_gcal_sync_success.assert_not_called()
    ui.host._reset_gcal_failure_backoff.assert_not_called()
    ui.host._increase_gcal_failure_backoff.assert_called_once()
    ui.information.assert_not_called()
    if ui.manual:
        ui.warning.assert_called_once()
        ui.host._show_sync_issue_popup.assert_called_once_with(
            actions._sync_failure_message(ui.host)
        )


def test_failed_run_without_changes_does_not_refresh_panels(feedback):
    ui = feedback
    ui.host._last_gcal_sync_changed_any = False
    ui.callback(ui.host, False, "Synthetic sync failure")
    ui.host.schedule_panel_refresh.assert_not_called()
    assert ui.settings.value("last_successful_sync") == "2000-01-01 00:00:00"
    assert ui.settings.value("sync_google_last_error") == "operation_failed"


def test_skipped_run_does_not_reuse_stale_changed_flag(feedback):
    ui = feedback
    ui.host._last_gcal_sync_outcome = "skipped"
    ui.callback(ui.host, False, "Synthetic skipped sync")
    ui.host.schedule_panel_refresh.assert_not_called()
    ui.host._increase_gcal_failure_backoff.assert_not_called()
    assert ui.settings.value("last_successful_sync") == "2000-01-01 00:00:00"
    assert ui.settings.value("sync_google_last_error") == "network_unavailable"
    ui.warning.assert_not_called()


def test_complete_success_still_updates_success_time_and_panels(feedback):
    ui = feedback
    ui.host._last_gcal_sync_outcome = "success"
    ui.host._last_gcal_sync_stats = {}
    ui.callback(ui.host, True, "Synthetic complete sync")
    assert ui.settings.value("last_successful_sync") != "2000-01-01 00:00:00"
    assert ui.settings.value("sync_google_last_error") == ""
    ui.host._handle_gcal_sync_success.assert_called_once()
    ui.host._reset_gcal_failure_backoff.assert_called_once()
    ui.host._increase_gcal_failure_backoff.assert_not_called()
    if ui.manual:
        ui.host.schedule_panel_refresh.assert_called_once_with(left=True, center=True)
        ui.information.assert_called_once()
    else:
        ui.host.schedule_panel_refresh.assert_called_once_with(center=True)


def test_partial_changes_refresh_even_without_a_failure_message(feedback):
    ui = feedback
    ui.callback(ui.host, False, "")
    ui.host.schedule_panel_refresh.assert_called_once_with(left=True, center=True)
    assert ui.settings.value("last_successful_sync") == "2000-01-01 00:00:00"
    assert ui.settings.value("sync_google_last_error") == "operation_failed"
    ui.host._handle_gcal_sync_success.assert_not_called()
