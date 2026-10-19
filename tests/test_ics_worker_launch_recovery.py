# -*- coding: utf-8 -*-
"""ICS launch failures must release idle workers and retain a running thread."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from calendar_app.presentation.main_window import calendar_sync_coordinator as module


class Signal:
    def __init__(self, fail=False):
        self.callbacks = []
        self.fail = fail

    def connect(self, callback):
        if self.fail:
            raise RuntimeError("synthetic signal wiring failure")
        self.callbacks.append(callback)

    def emit(self, *args):
        for callback in self.callbacks:
            callback(*args)


class Settings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=None, **kwargs):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


@pytest.fixture
def launch(monkeypatch):
    created = []
    config = {"failure": None}
    coordinator = SimpleNamespace(
        ics_worker=None,
        app=SimpleNamespace(_bg_workers=[]),
        settings=Settings(),
        _calendars=lambda: [
            {"id": "ics::fixture", "type": "ics", "ics_url": "https://example.invalid/feed.ics"}
        ],
        refresh=Mock(),
        _ics_result=Mock(),
    )
    coordinator._ics_finished = lambda: module.CalendarSyncCoordinator._ics_finished(coordinator)

    class Worker:
        def __init__(self, *args):
            if config["failure"] == "construct":
                raise RuntimeError("synthetic constructor failure")
            created.append(self)
            self.result = Signal(config["failure"] == "result_connect")
            self.finished = Signal(config["failure"] == "finished_connect")
            self.running = False
            self.deleteLater = Mock()
            self.requestInterruption = Mock()

        def start(self):
            if config["failure"] == "start_running":
                self.running = True
            if config["failure"] in {"start_idle", "start_running"}:
                raise RuntimeError("synthetic start failure")
            self.running = True

        def isRunning(self):
            return self.running

    monkeypatch.setattr(module, "IcsSyncWorker", Worker)
    return coordinator, created, config


@pytest.mark.parametrize(
    "failure", ["construct", "result_connect", "finished_connect", "start_idle"]
)
def test_ics_idle_launch_failure_is_reported_and_allows_retry(launch, failure):
    coordinator, created, config = launch
    config["failure"] = failure
    assert not module.CalendarSyncCoordinator.sync_ics(coordinator, force=True)
    assert coordinator.ics_worker is None
    assert coordinator.app._bg_workers == []
    assert coordinator.settings.value("sync_ics_last_error") == "operation_failed"
    if created:
        created[0].deleteLater.assert_called_once()
    config["failure"] = None
    assert module.CalendarSyncCoordinator.sync_ics(coordinator, force=True)
    assert coordinator.ics_worker is created[-1]


def test_ics_start_that_raises_after_launch_retains_worker_until_finished(launch):
    coordinator, created, config = launch
    config["failure"] = "start_running"
    assert not module.CalendarSyncCoordinator.sync_ics(coordinator, force=True)
    worker = created[0]
    assert coordinator.ics_worker is worker
    assert coordinator.app._bg_workers == [worker]
    worker.requestInterruption.assert_called_once()
    worker.deleteLater.assert_not_called()
    worker.result.emit({"ics::fixture": (1, 0, None)})
    coordinator._ics_result.assert_not_called()
    assert not module.CalendarSyncCoordinator.sync_ics(coordinator, force=True)
    worker.running = False
    coordinator.sender = lambda: worker
    worker.finished.emit()
    assert coordinator.ics_worker is None
    assert coordinator.app._bg_workers == []
    worker.deleteLater.assert_called_once()


def test_failed_idle_worker_cannot_deliver_a_queued_success_to_a_retry(launch):
    coordinator, created, config = launch
    config["failure"] = "start_idle"
    assert not module.CalendarSyncCoordinator.sync_ics(coordinator, force=True)
    first = created[0]
    config["failure"] = None
    assert module.CalendarSyncCoordinator.sync_ics(coordinator, force=True)
    first.result.emit({"ics::fixture": (1, 0, None)})
    coordinator._ics_result.assert_not_called()
    created[1].result.emit({"ics::fixture": (1, 0, None)})
    coordinator._ics_result.assert_called_once()


def test_native_qthread_remains_alive_until_failed_launch_finishes(monkeypatch):
    import threading

    from PyQt6 import sip
    from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QThread, pyqtSignal
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    owner = QObject()
    coordinator = module.CalendarSyncCoordinator.__new__(module.CalendarSyncCoordinator)
    QObject.__init__(coordinator, owner)
    coordinator.ics_worker = None
    coordinator.app = SimpleNamespace(_bg_workers=[])
    coordinator.settings = Settings()
    coordinator._calendars = lambda: [
        {"id": "ics::fixture", "type": "ics", "ics_url": "https://example.invalid/feed.ics"}
    ]
    coordinator.refresh = Mock()
    coordinator._ics_result = Mock()
    entered, release = threading.Event(), threading.Event()
    created = []

    class Worker(QThread):
        result = pyqtSignal(object)

        def __init__(self, calendars, parent, local_zone):
            super().__init__(parent)
            created.append(self)

        def start(self):
            super().start()
            assert entered.wait(2)
            raise RuntimeError("synthetic failure after native thread launch")

        def run(self):
            entered.set()
            release.wait(2)
            self.result.emit({"ics::fixture": (1, 0, None)})

    monkeypatch.setattr(module, "IcsSyncWorker", Worker)
    try:
        assert not coordinator.sync_ics(force=True)
        worker = created[0]
        assert worker.isRunning()
        assert worker.isInterruptionRequested()
        app.processEvents()
        assert not sip.isdeleted(worker)
        assert coordinator.ics_worker is worker
    finally:
        release.set()
        for worker in created:
            worker.wait(3000)
        app.processEvents()
    assert coordinator.ics_worker is None
    assert coordinator.app._bg_workers == []
    coordinator._ics_result.assert_not_called()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(created[0])
