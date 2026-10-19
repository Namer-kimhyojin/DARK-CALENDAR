# -*- coding: utf-8 -*-
"""Google worker launch failure must preserve data and permit a later retry."""

from types import MethodType, SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QWidget
import pytest

from calendar_app.presentation.main_window import action_handlers_gcal as actions
from calendar_app.presentation.main_window.calendar_sync_coordinator import CalendarSyncCoordinator
from calendar_app.shared import background_worker


class Host(QWidget, actions.GCalActionsMixin):
    pass


@pytest.fixture(params=["automatic", "silent", "manual"])
def launch(request, tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    host = Host()
    host.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    for key, value in (
        ("gcal_enabled", True),
        ("sync_google_auto", True),
        ("last_successful_sync", "2000-01-01 00:00:00"),
    ):
        host.settings.setValue(key, value)
    host._is_shutting_down = False
    host._sync_worker = None
    host._auth_worker = None
    host._manual_sync_setup_state = Mock(return_value="ready")
    host._silent_sync_waiting_for_auth = Mock(return_value=False)
    host.gcal_sync = SimpleNamespace(last_error_kind="auth_required", last_error_status=401)
    host._last_gcal_sync_outcome = "success"
    host._last_gcal_sync_changed_any = True
    host._last_gcal_sync_refresh_left = True
    host._last_gcal_sync_stats = {"pull_changes": 5}
    for method in (
        "update_sync_status",
        "schedule_panel_refresh",
        "_increase_gcal_failure_backoff",
        "_show_sync_issue_popup",
    ):
        setattr(host, method, Mock())
    coordinator = SimpleNamespace(app=host, settings=host.settings)
    coordinator.record_google_result = Mock(
        wraps=MethodType(CalendarSyncCoordinator.record_google_result, coordinator)
    )
    host._calendar_sync_coordinator = coordinator
    warning, info = Mock(), Mock()
    monkeypatch.setattr(actions.QMessageBox, "warning", warning)
    monkeypatch.setattr(actions.QMessageBox, "information", info)
    control = SimpleNamespace(failure=None, running_before_error=False, workers=[])

    def factory(*args, **kwargs):
        if control.failure == "constructor":
            raise RuntimeError("opaque-launch-details")
        worker = SimpleNamespace(
            result_ready=SimpleNamespace(connect=Mock()),
            finished=SimpleNamespace(connect=Mock()),
            running=False,
            deleteLater=Mock(),
            requestInterruption=Mock(),
        )
        worker.isRunning = lambda: worker.running

        def start():
            if control.failure == "start":
                worker.running = control.running_before_error
                raise RuntimeError("opaque-launch-details")
            worker.running = True

        worker.start = start
        if control.failure == "connection":
            worker.result_ready.connect.side_effect = RuntimeError("opaque-launch-details")
        control.workers.append(worker)
        return worker

    monkeypatch.setattr(background_worker, "SyncWorker", factory)

    def invoke():
        if request.param == "automatic":
            return host.sync_google_calendar_silent()
        return host.sync_google_calendar(silent=request.param == "silent")

    yield SimpleNamespace(
        host=host,
        control=control,
        invoke=invoke,
        warning=warning,
        info=info,
        manual=request.param == "manual",
    )
    host._sync_worker = None
    host.close()
    app.processEvents()


@pytest.mark.parametrize("failure", ["constructor", "connection", "start"])
def test_launch_failure_is_safe_recorded_and_retryable(launch, failure, caplog):
    ui = launch
    ui.control.failure = failure
    assert ui.invoke() is False
    assert ui.host._sync_worker is None
    assert not ui.host._sync_worker_running()
    assert ui.host._last_gcal_sync_outcome == "failed"
    assert ui.host.settings.value("sync_google_last_error") == "operation_failed"
    assert ui.host.settings.value("last_successful_sync") == "2000-01-01 00:00:00"
    assert not ui.host._last_gcal_sync_changed_any
    assert ui.host._last_gcal_sync_stats == {}
    ui.host.schedule_panel_refresh.assert_not_called()
    ui.host._increase_gcal_failure_backoff.assert_called_once()
    ui.info.assert_not_called()
    assert "opaque-launch-details" not in caplog.text
    if ui.control.workers:
        ui.control.workers[-1].deleteLater.assert_called_once()
    if ui.manual:
        ui.warning.assert_called_once()
        assert "opaque-launch-details" not in str(ui.warning.call_args)
    else:
        ui.warning.assert_not_called()
    ui.control.failure = None
    assert ui.invoke() is not False
    assert ui.host._sync_worker_running()


def test_successful_launch_connects_existing_callbacks_once(launch):
    ui = launch
    assert ui.invoke() is not False
    worker = ui.control.workers[-1]
    worker.result_ready.connect.assert_called_once_with(
        ui.host._on_sync_finished_manual if ui.manual else ui.host._on_sync_finished
    )
    worker.finished.connect.assert_called_once_with(ui.host._release_sync_worker)
    worker.deleteLater.assert_not_called()
    assert ui.host._sync_worker_running()
    ui.warning.assert_not_called()
    ui.info.assert_not_called()


def test_started_thread_is_retained_and_interrupted_without_unsafe_deletion(launch):
    ui = launch
    ui.control.failure = "start"
    ui.control.running_before_error = True
    assert ui.invoke() is False
    worker = ui.control.workers[-1]
    assert ui.host._sync_worker is worker
    worker.requestInterruption.assert_called_once()
    worker.deleteLater.assert_not_called()
    assert ui.host._sync_worker_running()
