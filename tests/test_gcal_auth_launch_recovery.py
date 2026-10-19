# -*- coding: utf-8 -*-
"""Authentication and metadata worker launch failures must not escape Qt slots."""

from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QWidget
import pytest

from calendar_app.presentation.main_window import action_handlers_gcal as actions
from calendar_app.shared import background_worker


class Host(QWidget, actions.GCalActionsMixin):
    pass


@pytest.fixture(params=["authentication", "metadata"])
def launch(request, tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    host = Host()
    host.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    host.settings.setValue("gcal_enabled", True)
    host.settings.setValue("last_successful_sync", "2000-01-01 00:00:00")
    host._auth_worker = None
    host._bg_workers = []
    host.gcal_sync = None
    host._last_gcal_sync_outcome = "success"
    host._last_gcal_sync_changed_any = True
    host._last_gcal_sync_stats = {"pull_changes": 5}
    host.update_sync_status = Mock()
    host.update_gcal_sync_timer = Mock()
    host.schedule_panel_refresh = Mock()
    control = SimpleNamespace(failure=None, running_before_error=False, workers=[])

    def factory(*args, **kwargs):
        if control.failure == "constructor":
            raise RuntimeError("opaque-launch-details")
        worker = SimpleNamespace(
            result_ready=SimpleNamespace(connect=Mock()),
            finished=SimpleNamespace(connect=Mock()),
            task_done=SimpleNamespace(connect=Mock()),
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
            worker.task_done.connect.side_effect = RuntimeError("opaque-launch-details")
        control.workers.append(worker)
        return worker

    monkeypatch.setattr(
        background_worker,
        "AuthWorker" if request.param == "authentication" else "DbTaskWorker",
        factory,
    )
    # The code imports TOKEN_PATH lazily; no real token or account is consulted.
    import calendar_app.app_paths as paths

    token = tmp_path / "synthetic-token"
    token.write_bytes(b"untouched")
    monkeypatch.setattr(paths, "TOKEN_PATH", str(token))
    invoke = (
        host.refresh_gcal_sync_state
        if request.param == "authentication"
        else host._refresh_calendar_access_roles_bg
    )
    yield SimpleNamespace(
        host=host,
        control=control,
        invoke=invoke,
        auth=request.param == "authentication",
        token=token,
    )
    host._auth_worker = None
    host._bg_workers.clear()
    host.close()
    app.processEvents()


@pytest.mark.parametrize("failure", ["constructor", "connection", "start"])
def test_auth_or_metadata_launch_failure_recovers_without_token_changes(launch, failure, caplog):
    ui = launch
    ui.control.failure = failure
    assert ui.invoke() is False
    assert ui.host._auth_worker is None
    assert ui.host._bg_workers == []
    assert ui.host.settings.value("sync_google_last_error") == "operation_failed"
    assert ui.host.settings.value("last_successful_sync") == "2000-01-01 00:00:00"
    assert ui.host._last_gcal_sync_outcome == "success"
    assert ui.host._last_gcal_sync_changed_any
    assert ui.host._last_gcal_sync_stats == {"pull_changes": 5}
    assert ui.token.read_bytes() == b"untouched"
    assert "opaque-launch-details" not in caplog.text
    ui.host.schedule_panel_refresh.assert_not_called()
    if ui.control.workers:
        ui.control.workers[-1].deleteLater.assert_called_once()
    ui.control.failure = None
    assert ui.invoke() is True
    if ui.auth:
        assert ui.host._auth_worker_running()
    else:
        assert len(ui.host._bg_workers) == 1


def test_running_worker_keeps_its_owner_and_is_not_deleted(launch):
    ui = launch
    ui.control.failure = "start"
    ui.control.running_before_error = True
    assert ui.invoke() is False
    worker = ui.control.workers[-1]
    assert (ui.host._auth_worker is worker) if ui.auth else (worker in ui.host._bg_workers)
    worker.requestInterruption.assert_called_once()
    worker.deleteLater.assert_not_called()
