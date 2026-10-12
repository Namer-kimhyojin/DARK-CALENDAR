# -*- coding: utf-8 -*-
"""New providers preserve credential boundaries, permissions and UI routing."""

import sqlite3
from unittest.mock import Mock

import pytest

from calendar_app.application.calendar_provider_catalog import account_provider
from calendar_app.application.calendar_sync_contract import CalendarSyncError
from calendar_app.infrastructure.caldav_sync.client import CalDAVClient
from calendar_app.infrastructure.caldav_sync.credentials import CalDAVCredentials
from calendar_app.infrastructure.caldav_sync.profiles import (
    PROFILES,
    account_key,
    server_urls,
    validate_url,
)
from calendar_app.infrastructure.calendar_sync.repository import CalendarSyncRepository
from calendar_app.presentation.dialogs.calendar_sync_hub import CalendarSyncHub
from tests.test_caldav_settings_dialog import Controller, ui  # noqa: F401
from tests.test_caldav_sync import Response, Session, multi, xml_row
from tests.test_calendar_sync_coordinator import Controller as SyncController
from tests.test_calendar_sync_coordinator import ui as coordinator_ui  # noqa: F401
from tests.test_calendar_sync_redesign import sync_ui  # noqa: F401

SERVICES = ("yahoo", "zoho", "fastmail")


@pytest.mark.parametrize("service", SERVICES)
def test_discovery_and_permissions_are_service_specific(service):
    base = PROFILES[service]["url"]
    root = base.split("/.well-known")[0].rstrip("/") + "/"
    session = Session(
        Response(
            multi(
                xml_row("/", "<c:calendar-home-set><d:href>/home/</d:href></c:calendar-home-set>")
            )
        ),
        Response(
            multi(
                xml_row("/home/read/", "<d:resourcetype><c:calendar/></d:resourcetype>")
                + xml_row(
                    "/home/write/",
                    "<d:resourcetype><c:calendar/></d:resourcetype><d:current-user-privilege-set><d:privilege><d:write/></d:privilege></d:current-user-privilege-set>",
                )
            )
        ),
    )
    calendars = CalDAVClient(service, "fixture@example.invalid", "synthetic", session).calendars()
    assert [c["can_edit"] for c in calendars] == [False, True]
    assert calendars[1]["id"] == root + "home/write/"
    assert session.calls[0][1] == base


@pytest.mark.parametrize("service", SERVICES)
@pytest.mark.parametrize(
    "url",
    [
        "https://evil.invalid/",
        "http://caldav.fastmail.com/",
        "https://calendar.zoho.com.evil.invalid/",
        "https://user:password@caldav.calendar.yahoo.com/",
    ],
)
def test_invalid_destinations_are_rejected_before_network(service, url):
    session = Session()
    with pytest.raises(CalendarSyncError, match="unsafe_caldav_url"):
        CalDAVClient(service, "fixture", "synthetic", session).request("GET", url)
    assert not session.calls


def test_zoho_redirect_cannot_send_credentials_to_another_data_center():
    session = Session(Response(status=302, headers={"Location": server_urls("zoho")[1]}))
    with pytest.raises(CalendarSyncError, match="unsafe_caldav_url"):
        CalDAVClient("zoho", "fixture", "synthetic", session).request(
            "PROPFIND", server_urls("zoho")[0], redirect=True
        )
    assert len(session.calls) == 1


@pytest.mark.parametrize("service", SERVICES)
def test_encrypted_credentials_round_trip_and_account_identity(service, tmp_path):
    store = CalDAVCredentials(tmp_path)
    account = store.save(
        service, "fixture@example.invalid", "synthetic-password", server_urls(service)[0]
    )
    assert b"synthetic-password" not in store.path(account).read_bytes()
    assert store.load(account)["server_url"] == server_urls(service)[0]
    assert account_provider(account) == service
    assert account != account_key(service, "other@example.invalid")
    store.remove(account)
    assert not store.path(account).exists()


@pytest.mark.parametrize("service", SERVICES)
def test_settings_selects_provider_and_clears_password_when_switching(ui, service):
    qapp, host, _ = ui
    for key in SERVICES:
        host._caldav_sync_controllers[key] = Controller(host.settings, key)
    from calendar_app.presentation.dialogs.caldav_settings_dialog import CalDAVSettingsDialog

    dialog = CalDAVSettingsDialog(host, host._caldav_sync_controllers, service)
    assert dialog.service.currentData() == service
    dialog.username.setText("fixture@example.invalid")
    dialog.password.setText("synthetic")
    dialog._connect()
    call = host._caldav_sync_controllers[service].start.call_args
    assert call.args == ("login", "fixture@example.invalid", "synthetic")
    assert call.kwargs == ({"server_url": server_urls("zoho")[0]} if service == "zoho" else {})
    assert not dialog.password.text()
    dialog.password.setText("another-synthetic")
    dialog.service.setCurrentIndex(0)
    assert not dialog.password.text()
    dialog.close()
    qapp.processEvents()


def test_hub_cards_filter_and_settings_route_new_services(sync_ui, monkeypatch):
    from calendar_app.presentation.main_window import caldav_sync_controller

    open_settings = Mock()
    monkeypatch.setattr(caldav_sync_controller, "open_caldav_settings", open_settings)
    hub = CalendarSyncHub(sync_ui.host, section="services")
    for service in SERVICES:
        assert service in hub.service_cards
        assert hub.calendar_manager.provider_filter.findData(service) >= 0
        hub._open(service)
        assert open_settings.call_args.args == (sync_ui.host, service)
    hub.close()


def test_unknown_caldav_service_does_not_route_to_outlook():
    assert account_provider("caldav::unknown::fixture") == "caldav"
    with pytest.raises(CalendarSyncError):
        validate_url("unknown", "https://calendar.zoho.com/")


def test_new_services_dispatch_and_local_save_sync_independently(coordinator_ui):
    fixture = coordinator_ui
    with sqlite3.connect(fixture.path) as conn:
        repo = CalendarSyncRepository(conn, "caldav")
        for service in SERVICES:
            controller = SyncController()
            controller.sync = Mock()
            fixture.host._caldav_sync_controllers[service] = controller
            prefix = "caldav_" + service + "_"
            account = account_key(service, "fixture@example.invalid")
            fixture.host.settings.setValue(prefix + "account_id", account)
            fixture.host.settings.setValue(prefix + "enabled", True)
            calendar = repo.register(
                account, {"id": PROFILES[service]["url"], "name": service, "can_edit": True}
            )
            fixture.coordinator.refresh()
            assert fixture.coordinator.calendar_providers[calendar] == service
    fixture.coordinator._flush_local_change()
    for service in SERVICES:
        controller = fixture.host._caldav_sync_controllers[service]
        controller.sync.assert_called_once()
        assert fixture.coordinator.sync(service) == [service]
        controller.start.assert_called_once_with("sync")
        fixture.coordinator.set_auto(service, False)
        assert not fixture.host.settings.value("caldav_" + service + "_enabled", True, type=bool)
