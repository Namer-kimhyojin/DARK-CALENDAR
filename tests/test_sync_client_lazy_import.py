# -*- coding: utf-8 -*-
"""Outlook/CalDAV client libraries load at the first sync, not during app start.

Importing requests, MSAL glue, the Graph client and the CalDAV client (icalendar,
dateutil) cost about 0.27 s on the GUI thread before the window could show. The
controllers now import them on first use. These tests pin that start stays free of
them and that a sync, and the error codes it reports, behave as before.
"""

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QWidget
import pytest
import requests

from calendar_app.application.calendar_sync_contract import RemoteCalendarError
from calendar_app.infrastructure.caldav_sync import client as caldav_client
from calendar_app.infrastructure.outlook_sync import auth as outlook_auth
from calendar_app.infrastructure.outlook_sync import graph as outlook_graph
from calendar_app.presentation.main_window import caldav_sync_controller as caldav
from calendar_app.presentation.main_window import outlook_sync_controller as outlook

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = {"imported": 1, "updated": 0, "created": 0, "deleted": 0, "issues": 0}
CALENDARS = [{"id": "remote", "name": "Fixture"}]

# The child isolates settings and app data before anything imports calendar_app,
# the same way tests/conftest.py does for this process.
CHILD = r"""
import json
import os
from pathlib import Path
import sqlite3
import sys

root = Path(sys.argv[1])
os.environ["LOCALAPPDATA"] = str(root)

from PyQt6 import QtCore

_RealQSettings = QtCore.QSettings


class _IsolatedQSettings(_RealQSettings):
    def __init__(self, *args, **kwargs):
        if len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], str):
            name = "".join(ch if ch.isalnum() else "_" for ch in f"{args[0]}_{args[1]}")
            super().__init__(str(root / f"{name}.ini"), _RealQSettings.Format.IniFormat, *args[2:])
        else:
            super().__init__(*args, **kwargs)


QtCore.QSettings = _IsolatedQSettings
WATCH = ("requests", "urllib3", "charset_normalizer", "icalendar", "dateutil")


def loaded():
    return sorted(name for name in WATCH if name in sys.modules)


from PyQt6.QtWidgets import QApplication

app = QApplication([])
from calendar_app.application.calendar_provider_catalog import CALDAV_SERVICES
from calendar_app.presentation.main_window import caldav_sync_controller as caldav
from calendar_app.presentation.main_window import outlook_sync_controller as outlook

report = {"after_import": loaded()}
host = QtCore.QObject()
host.settings = _IsolatedQSettings(str(root / "host.ini"), _RealQSettings.Format.IniFormat)
host._bg_workers = []
host.schedule_panel_refresh = lambda **kwargs: None
controllers = [outlook.OutlookSyncController(host)]
controllers += [caldav.CalDAVSyncController(host, service) for service in CALDAV_SERVICES]
for controller in controllers:
    controller.timer.stop()
    if hasattr(controller, "startup_timer"):
        controller.startup_timer.stop()
report["after_construct"] = loaded()
report["placeholder_is_exception"] = issubclass(outlook.RequestException, Exception)
report["placeholders"] = [
    outlook.RequestException is outlook._RequestsUnavailable,
    outlook.MicrosoftAuth is None,
    outlook.GraphClient is None,
    caldav.CalDAVClient is None,
]


def locked_repository(conn):
    raise sqlite3.OperationalError("database is locked")


# Disconnect never loads the clients, so its database failure reaches
# `except RequestException` while that name still holds the placeholder.
outlook.CalendarSyncRepository = locked_repository
worker = outlook.OutlookWorker(
    "disconnect", "12345678-1234-1234-1234-123456789abc", "microsoft::fixture", None
)
codes = []
worker.failed.connect(codes.append)
worker.run()
report["disconnect_codes"] = codes
report["after_disconnect"] = loaded()

import requests


class OfflineAuth:
    account_home_id = ""

    def __init__(self, client_id):
        pass

    def token(self, **kwargs):
        raise requests.ConnectTimeout("synthetic")


outlook.MicrosoftAuth = OfflineAuth
worker = outlook.OutlookWorker("sync", "synthetic-client", "microsoft::fixture", None)
codes = []
worker.failed.connect(codes.append)
worker.run()
report["offline_sync_codes"] = codes
report["filled"] = [
    outlook.RequestException is requests.RequestException,
    outlook.MicrosoftAuth is OfflineAuth,
    outlook.GraphClient.__module__,
]
client_type = caldav._caldav_client_type()
report["caldav_client"] = [client_type.__module__, caldav.CalDAVClient is client_type]
report["after_first_use"] = loaded()
print(json.dumps(report))
"""


_APP = None


def _app():
    # Keep a reference: a QApplication nobody holds is destroyed at once, and the
    # next QWidget then ends the process with qFatal.
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_start_imports_no_sync_client_and_the_first_sync_still_works(tmp_path):
    environment = dict(
        os.environ,
        LOCALAPPDATA=str(tmp_path),
        PYTHONIOENCODING="utf-8",
        QT_QPA_PLATFORM="offscreen",
    )
    result = subprocess.run(
        [sys.executable, "-c", CHILD, str(tmp_path)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    assert "TypeError" not in result.stderr, result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["after_import"] == []
    assert report["after_construct"] == []
    assert report["placeholder_is_exception"] is True
    assert report["placeholders"] == [True, True, True, True]
    assert report["disconnect_codes"] == ["operation_failed"]
    assert report["after_disconnect"] == []
    assert report["offline_sync_codes"] == ["network_unavailable"]
    assert report["filled"] == [True, True, "calendar_app.infrastructure.outlook_sync.graph"]
    assert report["caldav_client"] == ["calendar_app.infrastructure.caldav_sync.client", True]
    assert {"requests", "icalendar"} <= set(report["after_first_use"])


def _storage_fakes(monkeypatch, module):
    connection = SimpleNamespace(close=Mock())
    monkeypatch.setattr(module.sqlite3, "connect", Mock(return_value=connection))
    repository = SimpleNamespace(refresh_calendar_metadata=Mock(return_value={}))
    monkeypatch.setattr(module, "CalendarSyncRepository", Mock(return_value=repository))
    engine = SimpleNamespace(run=Mock(return_value=dict(SUMMARY)))
    monkeypatch.setattr(module, "CalendarSyncEngine", Mock(return_value=engine))
    return engine


def _capture(worker):
    failures, results = [], []
    worker.failed.connect(failures.append)
    worker.result.connect(lambda operation, result: results.append((operation, result)))
    return failures, results


@pytest.fixture
def outlook_first_use(monkeypatch):
    _app()
    # A fresh process: nothing loaded yet. The lazy import then reads the client
    # modules, whose classes are replaced by offline fakes.
    monkeypatch.setattr(outlook, "RequestException", outlook._RequestsUnavailable)
    monkeypatch.setattr(outlook, "MicrosoftAuth", None)
    monkeypatch.setattr(outlook, "GraphClient", None)
    auth = SimpleNamespace(
        token=Mock(return_value="synthetic-token"), account_home_id="fixture-home"
    )
    client = SimpleNamespace(
        profile=Mock(return_value={"id": "fixture", "mail": "synthetic@example.invalid"}),
        calendars=Mock(return_value=list(CALENDARS)),
        headers={"Authorization": "Bearer synthetic-token"},
        session=SimpleNamespace(close=Mock()),
    )
    auth_type = Mock(return_value=auth)
    graph_type = Mock(return_value=client)
    monkeypatch.setattr(outlook_auth, "MicrosoftAuth", auth_type)
    monkeypatch.setattr(outlook_graph, "GraphClient", graph_type)
    engine = _storage_fakes(monkeypatch, outlook)
    worker = outlook.OutlookWorker("sync", "synthetic-client", "microsoft::fixture", None)
    failures, results = _capture(worker)
    yield SimpleNamespace(
        worker=worker,
        auth_type=auth_type,
        graph_type=graph_type,
        client=client,
        engine=engine,
        failures=failures,
        results=results,
    )
    worker.deleteLater()


def test_outlook_first_sync_loads_the_client_stack_and_completes(outlook_first_use):
    case = outlook_first_use
    case.worker.run()
    assert case.failures == []
    assert case.results == [("sync", SUMMARY)]
    assert outlook.MicrosoftAuth is case.auth_type
    assert outlook.GraphClient is case.graph_type
    assert outlook.RequestException is requests.RequestException
    case.client.session.close.assert_called_once()
    assert case.client.headers == {}


@pytest.mark.parametrize(
    "error,code",
    [
        (requests.ConnectionError("synthetic"), "network_unavailable"),
        (requests.Timeout("synthetic"), "network_unavailable"),
        (outlook_graph.GraphError(503), "graph_http_503"),
        (ValueError("synthetic"), "operation_failed"),
    ],
)
def test_outlook_first_sync_still_maps_errors(outlook_first_use, error, code):
    case = outlook_first_use
    case.client.calendars.side_effect = error
    case.worker.run()
    assert case.failures == [code]
    assert case.results == []
    case.client.session.close.assert_called_once()


def test_outlook_worker_reports_a_missing_client_stack(outlook_first_use, monkeypatch):
    case = outlook_first_use
    monkeypatch.setattr(outlook, "_sync_client_types", Mock(side_effect=ImportError("synthetic")))
    case.worker.run()
    assert case.failures == ["dependency_unavailable"]
    case.auth_type.assert_not_called()


@pytest.fixture
def caldav_first_use(monkeypatch):
    _app()
    monkeypatch.setattr(caldav, "CalDAVClient", None)
    client = SimpleNamespace(
        calendars=Mock(return_value=list(CALENDARS)),
        session=SimpleNamespace(close=Mock()),
        auth=("synthetic", "synthetic-password"),
    )
    client_type = Mock(return_value=client)
    monkeypatch.setattr(caldav_client, "CalDAVClient", client_type)
    credentials = {
        "service": "icloud",
        "username": "synthetic@example.invalid",
        "password": "synthetic-password",
    }
    store = SimpleNamespace(load=Mock(return_value=dict(credentials)), save=Mock(), remove=Mock())
    monkeypatch.setattr(caldav, "CalDAVCredentials", Mock(return_value=store))
    monkeypatch.setattr(caldav, "CalDAVResourceCache", Mock())
    engine = _storage_fakes(monkeypatch, caldav)
    worker = caldav.CalDAVWorker("icloud", "sync", "caldav::fixture", None)
    failures, results = _capture(worker)
    yield SimpleNamespace(
        worker=worker,
        client=client,
        client_type=client_type,
        credentials=credentials,
        engine=engine,
        failures=failures,
        results=results,
    )
    worker.deleteLater()


def test_caldav_first_sync_loads_the_client_and_completes(caldav_first_use):
    case = caldav_first_use
    case.worker.run()
    assert case.failures == []
    assert case.results == [("sync", {"summary": SUMMARY, "calendars": CALENDARS})]
    assert caldav.CalDAVClient is case.client_type
    case.client_type.assert_called_once_with(
        **case.credentials,
        cancelled=case.worker.isInterruptionRequested,
        local_zone=case.worker.local_zone,
    )
    case.client.session.close.assert_called_once()
    assert case.client.auth == ("", "")


@pytest.mark.parametrize(
    "error,code",
    [(RemoteCalendarError(503), "remote_http_503"), (ValueError("synthetic"), "operation_failed")],
)
def test_caldav_first_sync_still_maps_errors(caldav_first_use, error, code):
    case = caldav_first_use
    case.client.calendars.side_effect = error
    case.worker.run()
    assert case.failures == [code]
    assert case.results == []
    case.client.session.close.assert_called_once()


def test_caldav_worker_reports_a_missing_client(caldav_first_use, monkeypatch):
    case = caldav_first_use
    monkeypatch.setattr(caldav, "_caldav_client_type", Mock(side_effect=ImportError("synthetic")))
    case.worker.run()
    assert case.failures == ["dependency_unavailable"]
    case.client_type.assert_not_called()
    assert case.worker.password == ""


def test_lazy_helpers_fill_placeholders_with_the_real_classes(monkeypatch):
    monkeypatch.setattr(outlook, "RequestException", outlook._RequestsUnavailable)
    monkeypatch.setattr(outlook, "MicrosoftAuth", None)
    monkeypatch.setattr(outlook, "GraphClient", None)
    monkeypatch.setattr(caldav, "CalDAVClient", None)
    outlook._sync_client_types()
    assert outlook.RequestException is requests.RequestException
    assert outlook.MicrosoftAuth is outlook_auth.MicrosoftAuth
    assert outlook.GraphClient is outlook_graph.GraphClient
    assert caldav._caldav_client_type() is caldav_client.CalDAVClient
    assert caldav.CalDAVClient is caldav_client.CalDAVClient


def test_lazy_helpers_keep_monkeypatched_names(monkeypatch):
    class SyntheticError(Exception):
        pass

    auth_type, graph_type, client_type = object(), object(), object()
    monkeypatch.setattr(outlook, "RequestException", SyntheticError)
    monkeypatch.setattr(outlook, "MicrosoftAuth", auth_type)
    monkeypatch.setattr(outlook, "GraphClient", graph_type)
    monkeypatch.setattr(caldav, "CalDAVClient", client_type)
    outlook._sync_client_types()
    assert outlook.RequestException is SyntheticError
    assert outlook.MicrosoftAuth is auth_type
    assert outlook.GraphClient is graph_type
    assert caldav._caldav_client_type() is client_type
    assert caldav.CalDAVClient is client_type


@pytest.fixture(params=["outlook", "icloud"])
def controller(request, tmp_path, monkeypatch):
    _app()
    host = QWidget()
    host.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    host.schedule_panel_refresh = Mock()
    host._bg_workers = []
    if request.param == "outlook":
        module, helper, worker_name = outlook, "_sync_client_types", "OutlookWorker"
        prefix = "outlook_"
        host.settings.setValue(prefix + "client_id", "12345678-1234-1234-1234-123456789abc")
        ctrl = outlook.OutlookSyncController(host)
    else:
        module, helper, worker_name = caldav, "_caldav_client_type", "CalDAVWorker"
        prefix = "caldav_icloud_"
        # Disconnect deactivates the calendars in the database before its worker starts.
        monkeypatch.setattr(caldav, "DB_PATH", str(tmp_path / "calendar.db"))
        monkeypatch.setattr(caldav, "CalendarSyncRepository", Mock())
        ctrl = caldav.CalDAVSyncController(host, "icloud")
    host.settings.setValue(prefix + "account_id", "fixture-account")
    ctrl.timer.stop()
    if hasattr(ctrl, "startup_timer"):
        ctrl.startup_timer.stop()
    worker_type = Mock()
    monkeypatch.setattr(module, worker_name, worker_type)
    yield SimpleNamespace(
        host=host, ctrl=ctrl, module=module, helper=helper, worker_type=worker_type, prefix=prefix
    )
    host._is_shutting_down = True
    ctrl.timer.stop()
    if hasattr(ctrl, "startup_timer"):
        ctrl.startup_timer.stop()
    host.close()
    host.deleteLater()


@pytest.mark.parametrize(
    "error,code",
    [
        (ImportError("synthetic"), "dependency_unavailable"),
        (OSError("synthetic"), "operation_failed"),
    ],
)
def test_start_reports_a_failed_client_import_without_a_worker(
    controller, monkeypatch, error, code
):
    case = controller
    monkeypatch.setattr(case.module, case.helper, Mock(side_effect=error))
    assert case.ctrl.start("sync") is False
    assert case.ctrl.status == code
    assert case.host.settings.value(case.prefix + "last_error") == code
    assert case.ctrl.worker is None
    assert case.host._bg_workers == []
    case.worker_type.assert_not_called()


@pytest.mark.parametrize("operation,warmed", [("sync", True), ("disconnect", False)])
def test_start_loads_the_client_only_for_operations_that_need_it(
    controller, monkeypatch, operation, warmed
):
    case = controller
    helper = Mock()
    monkeypatch.setattr(case.module, case.helper, helper)
    assert case.ctrl.start(operation) is True
    assert helper.called is warmed
    case.worker_type.assert_called_once()


def test_disconnect_in_a_locked_database_reports_operation_failed(tmp_path, monkeypatch):
    # In-process twin of the fresh-process check: the placeholder exception keeps
    # `except RequestException` valid, so the failure is not turned into a TypeError.
    _app()
    monkeypatch.setattr(outlook, "RequestException", outlook._RequestsUnavailable)
    monkeypatch.setattr(outlook, "DB_PATH", str(tmp_path / "calendar.db"))
    monkeypatch.setattr(
        outlook, "CalendarSyncRepository", Mock(side_effect=sqlite3.OperationalError("locked"))
    )
    worker = outlook.OutlookWorker(
        "disconnect", "12345678-1234-1234-1234-123456789abc", "microsoft::fixture", None
    )
    failures, results = _capture(worker)
    worker.run()
    assert failures == ["operation_failed"]
    assert results == []
    worker.deleteLater()
