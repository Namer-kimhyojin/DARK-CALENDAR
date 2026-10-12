# -*- coding: utf-8 -*-
"""Provider workers preserve retry guidance and release resources on every exit."""

import threading
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtWidgets import QApplication
import pytest

from calendar_app.application.calendar_sync_contract import CalendarSyncError, RemoteCalendarError
from calendar_app.infrastructure.outlook_sync.graph import GraphError
from calendar_app.presentation.main_window import caldav_sync_controller as caldav
from calendar_app.presentation.main_window import outlook_sync_controller as outlook


@pytest.fixture(params=["outlook", "icloud", "naver"])
def worker_case(request, monkeypatch):
    qapp = QApplication.instance() or QApplication([])
    service = request.param
    module = outlook if service == "outlook" else caldav
    account = "microsoft::fixture" if service == "outlook" else "caldav::fixture"
    client = SimpleNamespace(
        profile=Mock(return_value={"id": "fixture", "mail": "synthetic@example.invalid"}),
        calendars=Mock(return_value=[{"id": "remote", "name": "Fixture"}]),
        session=SimpleNamespace(close=Mock()),
        auth=("synthetic", "synthetic-password"),
        headers={"Authorization": "Bearer synthetic-token"},
    )
    client_factory = Mock(return_value=client)
    store = SimpleNamespace(
        load=Mock(
            return_value={
                "service": service,
                "username": "synthetic@example.invalid",
                "password": "synthetic-password",
            }
        ),
        save=Mock(),
        remove=Mock(),
    )
    auth = SimpleNamespace(
        token=Mock(return_value="synthetic-token"), account_home_id="fixture-home"
    )
    connection = SimpleNamespace(close=Mock())
    connect = Mock(return_value=connection)
    repository = SimpleNamespace(calendars=Mock(return_value=[]), register=Mock())
    summary = {"imported": 1, "updated": 0, "created": 0, "deleted": 0, "issues": 0}
    engine = SimpleNamespace(run=Mock(return_value=summary))
    engine_factory = Mock(return_value=engine)
    monkeypatch.setattr(module.sqlite3, "connect", connect)
    monkeypatch.setattr(module, "CalendarSyncRepository", Mock(return_value=repository))
    monkeypatch.setattr(module, "CalendarSyncEngine", engine_factory)
    if service == "outlook":
        monkeypatch.setattr(module, "MicrosoftAuth", Mock(return_value=auth))
        monkeypatch.setattr(module, "GraphClient", client_factory)
        worker = module.OutlookWorker("sync", "synthetic-client", account, None)
    else:
        monkeypatch.setattr(module, "CalDAVCredentials", Mock(return_value=store))
        monkeypatch.setattr(module, "CalDAVClient", client_factory)
        monkeypatch.setattr(module, "CalDAVResourceCache", Mock())
        worker = module.CalDAVWorker(
            service,
            "sync",
            account,
            None,
            username="synthetic@example.invalid",
            password="synthetic-password",
        )
    failures, results, finished = [], [], []
    worker.failed.connect(failures.append)
    worker.result.connect(lambda operation, result: results.append((operation, result)))
    worker.finished.connect(lambda: finished.append(True))
    case = SimpleNamespace(
        qapp=qapp,
        service=service,
        module=module,
        worker=worker,
        client=client,
        client_factory=client_factory,
        store=store,
        auth=auth,
        connect=connect,
        connection=connection,
        engine=engine,
        engine_factory=engine_factory,
        failures=failures,
        results=results,
        finished=finished,
    )
    yield case
    if worker.isRunning():
        worker.requestInterruption()
        assert worker.wait(3000), "Synthetic worker did not finish before cleanup"
    worker.deleteLater()
    qapp.processEvents()


@pytest.mark.parametrize("stage", ["discovery", "engine"])
@pytest.mark.parametrize("status,retry_after", [(429, 9_000), (503, 120.5), (429, None)])
def test_http_failure_preserves_retry_delay_before_failed_signal(
    worker_case, stage, status, retry_after
):
    case = worker_case
    error = (
        GraphError(status, retry_after)
        if case.service == "outlook"
        else RemoteCalendarError(status)
    )
    if case.service != "outlook":
        error.retry_after = retry_after
    target = case.client.calendars if stage == "discovery" else case.engine.run
    target.side_effect = error
    seen_delay = []
    case.worker.failed.connect(lambda _code: seen_delay.append(case.worker.retry_after))
    assert case.worker.retry_after is None
    case.worker.run()
    expected = f"graph_http_{status}" if case.service == "outlook" else f"remote_http_{status}"
    assert case.failures == [expected]
    assert not case.results
    assert seen_delay == [retry_after]
    assert case.worker.retry_after == retry_after
    if stage == "engine":
        case.connection.close.assert_called_once()
    else:
        case.connect.assert_not_called()
    case.client.session.close.assert_called_once()
    if case.service == "outlook":
        assert case.client.headers == {}
    else:
        assert case.worker.password == ""
        assert case.client.auth == ("", "")


@pytest.mark.parametrize("operation", ["sync", "refresh", "login"])
def test_client_session_is_closed_after_success_or_login(worker_case, operation):
    case = worker_case
    case.worker.operation = operation
    case.worker.run()
    assert not case.failures
    assert len(case.results) == 1
    assert case.results[0][0] == operation
    case.client.session.close.assert_called_once()
    if operation == "login":
        case.connect.assert_not_called()
    else:
        case.connection.close.assert_called_once()
    if case.service == "outlook":
        assert case.client.headers == {}
    else:
        assert case.worker.password == ""
        assert case.client.auth == ("", "")


@pytest.mark.parametrize("operation", ["sync", "refresh", "login"])
def test_real_thread_interruption_during_discovery_prevents_result_and_db_write(
    worker_case, operation
):
    case = worker_case
    case.worker.operation = operation
    started, release = threading.Event(), threading.Event()

    def discover():
        started.set()
        assert release.wait(3), "Synthetic discovery was not released"
        return [{"id": "remote", "name": "Fixture"}]

    case.client.calendars.side_effect = discover
    try:
        case.worker.start()
        assert started.wait(2)
        case.worker.requestInterruption()
        release.set()
        assert case.worker.wait(2000)
        case.qapp.processEvents()
        assert case.finished == [True]
        assert not case.worker.isRunning()
        assert not case.results
        assert not case.failures
        case.connect.assert_not_called()
        case.engine_factory.assert_not_called()
        case.store.save.assert_not_called()
        case.client.session.close.assert_called_once()
        if case.service == "outlook":
            assert case.client.headers == {}
        else:
            assert case.worker.password == ""
            assert case.client.auth == ("", "")
    finally:
        release.set()
        case.worker.requestInterruption()
        assert case.worker.wait(3000)


def test_real_thread_engine_cancellation_closes_db_and_client(worker_case):
    case = worker_case
    started, release = threading.Event(), threading.Event()

    def run_engine():
        started.set()
        assert release.wait(3), "Synthetic engine was not released"
        assert case.engine_factory.call_args.kwargs["cancelled"]()
        raise CalendarSyncError("cancelled")

    case.engine.run.side_effect = run_engine
    try:
        case.worker.start()
        assert started.wait(2)
        case.worker.requestInterruption()
        release.set()
        assert case.worker.wait(2000)
        case.qapp.processEvents()
        assert case.finished == [True]
        assert not case.worker.isRunning()
        assert case.failures == ["cancelled"]
        assert not case.results
        assert case.worker.retry_after is None
        case.connection.close.assert_called_once()
        case.client.session.close.assert_called_once()
        assert callable(case.client_factory.call_args.kwargs["cancelled"])
        if case.service == "outlook":
            assert case.client.headers == {}
        else:
            assert case.worker.password == ""
            assert case.client.auth == ("", "")
    finally:
        release.set()
        case.worker.requestInterruption()
        assert case.worker.wait(3000)


def test_failure_before_client_creation_has_safe_error_and_clears_password(worker_case):
    case = worker_case
    if case.service == "outlook":
        case.auth.token.side_effect = CalendarSyncError("auth_required")
    else:
        case.store.load.side_effect = CalendarSyncError("auth_required")
    case.worker.run()
    assert case.failures == ["auth_required"]
    assert not case.results
    assert case.worker.retry_after is None
    case.client_factory.assert_not_called()
    case.connect.assert_not_called()
    if case.service != "outlook":
        assert case.worker.password == ""


@pytest.mark.parametrize("outcome", ["success", "failure"])
def test_cleanup_exception_cannot_escape_or_emit_duplicate_failure(worker_case, outcome, caplog):
    case = worker_case
    case.client.session.close.side_effect = RuntimeError("synthetic-private-cleanup-error")
    if outcome == "failure":
        error = GraphError(429, 9000) if case.service == "outlook" else RemoteCalendarError(429)
        error.retry_after = 9000
        case.client.calendars.side_effect = error
    case.worker.run()
    case.client.session.close.assert_called_once()
    if outcome == "success":
        assert len(case.results) == 1
        assert case.failures == []
        case.connection.close.assert_called_once()
    else:
        assert not case.results
        assert case.failures == [
            "graph_http_429" if case.service == "outlook" else "remote_http_429"
        ]
        assert case.worker.retry_after == 9000
        case.connect.assert_not_called()
    if case.service == "outlook":
        assert case.client.headers == {}
    else:
        assert case.worker.password == ""
        assert case.client.auth == ("", "")
    assert "synthetic-private-cleanup-error" not in caplog.text
