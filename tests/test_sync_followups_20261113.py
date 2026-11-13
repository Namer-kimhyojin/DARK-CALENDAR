# -*- coding: utf-8 -*-
"""External calendar sync follow-ups from the 2026-11-13 audit."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QWidget
import pytest
import requests

from calendar_app.infrastructure.calendar_sync.engine import CalendarSyncEngine
from calendar_app.infrastructure.calendar_sync.http_retry import retry_after_seconds
from calendar_app.infrastructure.google_sync import common as google_common
from calendar_app.infrastructure.google_sync import service, token_store
from calendar_app.infrastructure.ics.subscriptions import subscription_errors
from calendar_app.presentation.dialogs.calendar_sync_hub import CalendarSyncHub
from calendar_app.presentation.main_window import caldav_sync_controller as caldav
from calendar_app.presentation.main_window import calendar_sync_coordinator as coordinator_module
from calendar_app.presentation.main_window import outlook_sync_controller as outlook
from tests.test_calendar_sync_engine import Provider, repo, task  # noqa: F401
from tests.test_calendar_sync_redesign import sync_ui  # noqa: F401
from tests.test_ics_snapshot_safety import event, feed, rows, snapshot  # noqa: F401
from tests.test_sync_controller_lifecycle import controller  # noqa: F401


class Settings:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def value(self, key, default=None, **kwargs):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


def _signal():
    return SimpleNamespace(connect=lambda callback: None)


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def berlin(monkeypatch):
    monkeypatch.setattr(google_common, "_system_time_zone", lambda: "Europe/Berlin")


# 1. Without a saved zone, sync uses this PC's zone instead of Asia/Seoul.


def test_sync_time_zone_prefers_the_saved_zone_then_the_system_zone(berlin):
    assert google_common.sync_time_zone(Settings({"gcal_timezone": "Asia/Tokyo"})) == "Asia/Tokyo"
    assert google_common.sync_time_zone(Settings()) == "Europe/Berlin"


@pytest.mark.parametrize("service_name", ["outlook", "icloud", "naver"])
def test_account_workers_receive_the_system_zone_without_a_setting(
    qapp, berlin, service_name, tmp_path, monkeypatch
):
    host = QWidget()
    host.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    host._bg_workers = []
    host.schedule_panel_refresh = Mock()
    prefix = "outlook_" if service_name == "outlook" else "caldav_" + service_name + "_"
    host.settings.setValue(prefix + "account_id", "synthetic-account")
    host.settings.setValue("outlook_client_id", "synthetic-client")
    zones = []

    def factory(*args, **kwargs):
        zones.append(args[5] if service_name == "outlook" else args[6])
        return SimpleNamespace(
            operation="sync",
            result=_signal(),
            failed=_signal(),
            finished=_signal(),
            start=lambda: None,
        )

    if service_name == "outlook":
        monkeypatch.setattr(outlook, "OutlookWorker", factory)
        ctrl = outlook.OutlookSyncController(host)
    else:
        monkeypatch.setattr(caldav, "CalDAVWorker", factory)
        ctrl = caldav.CalDAVSyncController(host, service_name)
        ctrl.startup_timer.stop()
    ctrl.timer.stop()
    try:
        assert ctrl.start("sync") is True
        assert zones == ["Europe/Berlin"]
    finally:
        host._is_shutting_down = True
        ctrl.worker = None
        host._bg_workers.clear()
        host.close()


def test_ics_worker_receives_the_system_zone_without_a_setting(berlin, monkeypatch):
    zones = []

    class Worker:
        def __init__(self, calendars, parent, local_zone=None):
            zones.append(local_zone)
            self.result = self.finished = _signal()

        def start(self):
            pass

    monkeypatch.setattr(coordinator_module, "IcsSyncWorker", Worker)
    fake = SimpleNamespace(
        ics_worker=None,
        _ics_pending_ids=set(),
        _ics_accept_empty={},
        app=SimpleNamespace(_bg_workers=[]),
        settings=Settings(),
        _calendars=lambda: [
            {"id": "ics::fixture", "type": "ics", "ics_url": "https://example.invalid/feed.ics"}
        ],
        refresh=Mock(),
        _ics_result=Mock(),
        _ics_finished=Mock(),
    )
    assert coordinator_module.CalendarSyncCoordinator.sync_ics(fake, force=True)
    assert zones == ["Europe/Berlin"]


def test_sync_hub_offers_the_system_zone_without_a_setting(berlin, sync_ui, monkeypatch):
    monkeypatch.setattr(coordinator_module.IcsSyncWorker, "start", Mock())
    hub = CalendarSyncHub(sync_ui.host, section="services")
    try:
        assert hub.timezone.currentText() == "Europe/Berlin"
        assert sync_ui.host.settings.value("gcal_timezone") is None
    finally:
        hub.close()
        hub.deleteLater()


# 2. An ICS response without any event must not wipe the mirrored events.


def test_empty_ics_feed_keeps_existing_mirrors_and_reports_it(snapshot, monkeypatch):
    from calendar_app.infrastructure.ics import ics_fetcher

    monkeypatch.setattr(ics_fetcher, "_now", lambda: datetime(2026, 10, 5, tzinfo=UTC))
    conn, sync = snapshot
    assert sync(feed(event("one")))[2] is None
    before = rows(conn)
    assert sync(feed()) == (0, 0, "calendar_report_incomplete")
    assert rows(conn) == before
    assert not conn.in_transaction


def test_empty_ics_feed_without_mirrors_is_a_valid_snapshot(snapshot):
    conn, sync = snapshot
    assert sync(feed()) == (0, 0, None)
    assert rows(conn) == []


def test_empty_feed_error_is_kept_as_a_subscription_diagnostic():
    settings = Settings({"sync_ics_error_codes": {"ics::fixture": "calendar_report_incomplete"}})
    assert subscription_errors(settings) == {"ics::fixture": "calendar_report_incomplete"}


# 3. A Retry-After header pauses sync (manual included) for at most an hour.


def test_retry_after_is_capped_at_one_hour():
    assert retry_after_seconds("86400") == 3600


def test_day_long_retry_after_blocks_manual_sync_for_at_most_an_hour(controller, monkeypatch):
    _, host, ctrl, prefix, module, _ = controller
    monkeypatch.setattr(module, "monotonic", lambda: 100.0)
    host.settings.setValue("outlook_client_id", "fixture")
    ctrl.worker = SimpleNamespace(operation="sync", retry_after=86_400)
    ctrl._failed("graph_http_429" if prefix == "outlook_" else "remote_http_429")
    ctrl.worker = None
    assert ctrl.timer.interval() == 3_600_000
    factory = Mock()
    monkeypatch.setattr(
        module, "OutlookWorker" if prefix == "outlook_" else "CalDAVWorker", factory
    )
    monkeypatch.setattr(module, "monotonic", lambda: 3_700.5)
    ctrl.sync(force=True)
    factory.assert_called_once()
    ctrl.worker = None
    host._bg_workers.clear()


# 4. Linked events that ended before the sync window are not fetched one by one.


def test_unchanged_link_that_ended_before_the_window_is_not_refetched(repo):
    provider = Provider()
    key = repo.calendars("account")[0]["local_id"]
    engine = CalendarSyncEngine(provider, repo, "account")
    # The repo fixture pins the engine clock to 2026-10-06 (window from 2026-06-08).
    record = {**task(), "deadline": "2026-03-02T10:00:00", "end_date": "2026-03-02T11:00:00"}
    provider.remote["remote"] = {"id": "remote", "etag": "1", "task": record}
    engine.run()
    tid = repo.tasks(key)[0]["id"]
    # The remote window no longer contains the event.
    provider.events = lambda *args: []
    provider.event = Mock(side_effect=AssertionError("unchanged old event was fetched"))
    engine.run()
    assert provider.writes == []
    # A local edit of the same old event is still pushed.
    provider.event = Mock(return_value=deepcopy(provider.remote["remote"]))
    with repo.conn:
        repo.conn.execute("UPDATE unified_task SET name='Edited' WHERE id=?", (tid,))
    engine.run()
    provider.event.assert_called_once_with("remote")
    assert provider.writes == ["update"]


# 5. Disconnect revokes the long-lived refresh token.


def _capture_revocation(monkeypatch, tmp_path, token_data):
    from urllib import request

    path = tmp_path / "token.json"
    path.write_bytes(b"synthetic-placeholder")
    monkeypatch.setattr(service, "TOKEN_PATH", str(path))
    monkeypatch.setattr(token_store, "load_token_json", lambda: json.dumps(token_data))
    sent = []

    def urlopen(req, **_kwargs):
        sent.append(parse_qs(req.data.decode("utf-8", errors="strict")))
        context = Mock()
        context.__enter__ = Mock(return_value=SimpleNamespace(status=200))
        context.__exit__ = Mock(return_value=False)
        return context

    monkeypatch.setattr(request, "urlopen", urlopen)
    assert service.CalendarSyncService().revoke_token()
    return sent


def test_disconnect_revokes_the_refresh_token(monkeypatch, tmp_path):
    sent = _capture_revocation(
        monkeypatch, tmp_path, {"token": "synthetic-access", "refresh_token": "synthetic-refresh"}
    )
    assert sent == [{"token": ["synthetic-refresh"]}]


def test_disconnect_falls_back_to_the_access_token(monkeypatch, tmp_path):
    sent = _capture_revocation(monkeypatch, tmp_path, {"token": "synthetic-access"})
    assert sent == [{"token": ["synthetic-access"]}]


# 6. Outlook transport failures are shown as a network problem.


@pytest.mark.parametrize(
    "failure", [requests.ConnectionError("synthetic"), requests.Timeout("synthetic")]
)
def test_outlook_worker_reports_transport_failure_as_network_unavailable(
    qapp, failure, monkeypatch
):

    class OfflineAuth:
        account_home_id = ""

        def __init__(self, client_id):
            pass

        def token(self, **kwargs):
            raise failure

    monkeypatch.setattr(outlook, "MicrosoftAuth", OfflineAuth)
    worker = outlook.OutlookWorker("sync", "synthetic-client", "synthetic-account", None)
    codes = []
    worker.failed.connect(codes.append)
    worker.run()
    assert codes == ["network_unavailable"]


def test_outlook_authority_discovery_offline_reaches_the_ui_as_network_unavailable(
    qapp, monkeypatch
):
    monkeypatch.setattr(
        "msal.PublicClientApplication", Mock(side_effect=requests.ConnectTimeout("synthetic"))
    )
    worker = outlook.OutlookWorker(
        "sync", "12345678-1234-1234-1234-123456789abc", "synthetic-account", None
    )
    codes = []
    worker.failed.connect(codes.append)
    worker.run()
    assert codes == ["network_unavailable"]


# 8. A zero-length Google event stays zero-length when the app pushes an edit.


class _Request:
    def __init__(self, result):
        self.result = result
        self.headers = {}

    def execute(self):
        return self.result


class _Events:
    def __init__(self, remote):
        self.remote = remote
        self.body = None

    def get(self, **kwargs):
        return _Request(deepcopy(self.remote))

    def update(self, **kwargs):
        self.body = kwargs["body"]
        return _Request({**kwargs["body"], "updated": "2026-03-14T02:00:00Z"})


def _push_edit(remote_end):
    events = _Events(
        {
            "id": "evt-1",
            "updated": "2026-03-14T00:00:00Z",
            "etag": '"stable"',
            "start": {"dateTime": "2026-03-14T09:00:00+09:00"},
            "end": {"dateTime": remote_end},
        }
    )
    sync = service.CalendarSyncService(time_zone="Asia/Seoul")
    sync.is_authenticated = True
    sync.service = SimpleNamespace(events=lambda: events)
    assert sync.update_event(
        "evt-1",
        "Edited title",
        "2026-03-14 09:00:00",
        "2026-03-14 09:00:00",
        expected_remote_updated_at="2026-03-14T00:00:00Z",
    )
    start = datetime.fromisoformat(events.body["start"]["dateTime"])
    return datetime.fromisoformat(events.body["end"]["dateTime"]) - start


def test_zero_length_google_event_is_not_extended_by_an_edit():
    assert _push_edit("2026-03-14T00:00:00Z") == timedelta(0)


def test_equal_local_times_still_get_an_hour_when_the_remote_had_a_duration():
    assert _push_edit("2026-03-14T10:00:00+09:00") == timedelta(hours=1)
