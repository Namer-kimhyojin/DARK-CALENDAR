# -*- coding: utf-8 -*-
"""Provider startup exceptions retain ownership only for running workers."""

from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QWidget
import pytest

from calendar_app.presentation.main_window import caldav_sync_controller as caldav
from calendar_app.presentation.main_window import outlook_sync_controller as outlook


@pytest.fixture(params=["outlook", "icloud", "naver"])
def launch(request, tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    host._bg_workers = []
    host.schedule_panel_refresh = Mock()
    service = request.param
    module = outlook if service == "outlook" else caldav
    prefix = "outlook_" if service == "outlook" else "caldav_" + service + "_"
    host.settings.setValue(prefix + "account_id", "synthetic-account")
    host.settings.setValue("outlook_client_id", "synthetic-client")
    controller = (
        outlook.OutlookSyncController(host)
        if service == "outlook"
        else caldav.CalDAVSyncController(host, service)
    )
    controller.timer.stop()
    if hasattr(controller, "startup_timer"):
        controller.startup_timer.stop()
    control = SimpleNamespace(failure=None, running=False, workers=[])

    def connect(callback):
        if control.failure == "connect":
            raise RuntimeError("synthetic signal connection failure")

    def factory(*args, **kwargs):
        if control.failure == "construct":
            raise RuntimeError("synthetic construction failure")
        worker = SimpleNamespace(
            operation="sync",
            result=SimpleNamespace(connect=connect),
            failed=SimpleNamespace(connect=connect),
            finished=SimpleNamespace(connect=connect),
            isRunning=lambda: control.running,
            requestInterruption=Mock(),
            deleteLater=Mock(),
            password="synthetic-password",
        )

        def start():
            if control.failure == "start":
                raise RuntimeError("synthetic start failure")

        worker.start = start
        control.workers.append(worker)
        return worker

    monkeypatch.setattr(
        module, "OutlookWorker" if service == "outlook" else "CalDAVWorker", factory
    )
    yield SimpleNamespace(host=host, controller=controller, control=control, prefix=prefix)
    host._is_shutting_down = True
    controller.timer.stop()
    if hasattr(controller, "startup_timer"):
        controller.startup_timer.stop()
    controller.worker = None
    host._bg_workers.clear()
    host.close()
    app.processEvents()


@pytest.mark.parametrize("stage", ["construct", "connect", "start"])
def test_provider_launch_failure_is_recorded_and_retryable(launch, stage):
    ui = launch
    ui.control.failure = stage
    assert ui.controller.start("sync") is False
    assert not ui.controller.busy
    assert not ui.host._bg_workers
    assert ui.controller.status == "operation_failed"
    assert ui.host.settings.value(ui.prefix + "last_error") == "operation_failed"
    if ui.control.workers:
        worker = ui.control.workers[-1]
        worker.deleteLater.assert_called_once()
        if ui.prefix != "outlook_":
            assert worker.password == ""
    ui.control.failure = None
    assert ui.controller.start("sync") is True
    assert ui.controller.busy


def test_started_worker_is_interrupted_and_retained_on_start_exception(launch):
    ui = launch
    ui.control.failure = "start"
    ui.control.running = True
    assert ui.controller.start("sync") is False
    worker = ui.control.workers[-1]
    assert ui.controller.worker is worker
    assert ui.host._bg_workers == [worker]
    worker.requestInterruption.assert_called_once()
    worker.deleteLater.assert_not_called()
    assert ui.controller.status == "operation_failed"
