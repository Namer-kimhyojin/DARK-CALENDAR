# -*- coding: utf-8 -*-
"""Untrusted provider responses cannot exhaust memory or escape destinations."""

from functools import partial
from io import BytesIO
import json
from unittest.mock import Mock

import pytest
from urllib3.response import HTTPResponse

from calendar_app.application.calendar_sync_contract import CalendarSyncError
from calendar_app.infrastructure.caldav_sync import client as caldav
from calendar_app.infrastructure.caldav_sync import credentials
from calendar_app.infrastructure.caldav_sync.conversion import records
from calendar_app.infrastructure.calendar_sync import http_response
from calendar_app.infrastructure.outlook_sync import auth, graph
from tests.test_caldav_sync import BASE, Response, Session, multi, xml_row
from tests.test_outlook_graph import response as graph_response


@pytest.fixture(params=["outlook", "caldav"])
def request_case(request):
    if request.param == "outlook":
        session = Mock()
        client = graph.GraphClient("synthetic-token", session)
        reply = graph_response({"value": []})
        session.request.return_value = reply
        call = partial(client.request, "GET", "/me/events")
        module = graph
    else:
        reply = Response(b"synthetic body", 200)
        session = Session(reply)
        client = caldav.CalDAVClient("icloud", "fixture", "synthetic-password", session)
        call = partial(client.request, "GET", BASE)
        module = caldav
    return client, reply, session, call, module


def test_byte_limit_applies_before_any_calendar_snapshot_can_return(request_case, monkeypatch):
    _client, reply, _session, call, module = request_case
    monkeypatch.setattr(module, "MAX_RESPONSE", 8)
    with pytest.raises(CalendarSyncError, match="calendar_response_too_large"):
        call()
    if isinstance(reply, Response):
        assert reply.closed
    else:
        reply.close.assert_called_once()


def test_identity_encoding_and_streaming_are_explicit(request_case):
    _client, reply, session, call, _module = request_case
    reply.headers = {"content-encoding": "identity"}
    call()
    options = (
        session.calls[0][2] if isinstance(session, Session) else session.request.call_args.kwargs
    )
    assert options["stream"] is True
    assert options["headers"]["Accept-Encoding"] == "identity"
    assert options["allow_redirects"] is False


def test_oversized_content_length_is_rejected_before_read_or_integer_conversion(request_case):
    _client, reply, _session, call, _module = request_case
    reply.headers = {"content-length": "9" * 5000}
    reply.raw = Mock()
    with pytest.raises(CalendarSyncError, match="calendar_response_too_large"):
        call()
    reply.raw.read1.assert_not_called()


def test_unsupported_encoding_is_rejected_without_decompressing(request_case):
    _client, reply, _session, call, _module = request_case
    reply.headers = {"Content-Encoding": "gzip"}
    reply.raw = Mock()
    with pytest.raises(CalendarSyncError, match="invalid_.*_response"):
        call()
    reply.raw.read1.assert_not_called()


def test_cancel_during_body_read_closes_response(request_case):
    client, reply, _session, call, _module = request_case
    checks = iter((False, False, True))
    client.cancelled = lambda: next(checks, True)
    with pytest.raises(CalendarSyncError, match="cancelled"):
        call()
    if isinstance(reply, Response):
        assert reply.closed
    else:
        reply.close.assert_called_once()


def test_trickling_body_observes_deadline_between_raw_reads(request_case, monkeypatch):
    _client, reply, _session, call, module = request_case
    monkeypatch.setattr(module, "monotonic", lambda: 0)
    times = iter((0, 1, 61))
    monkeypatch.setattr(http_response, "monotonic", lambda: next(times, 61))
    reply.raw = Mock()
    reply.raw.read1.return_value = b"x"
    with pytest.raises(CalendarSyncError, match="network_unavailable"):
        call()
    assert reply.raw.read1.call_count == 1


def test_raw_transport_failure_is_safe_and_closed(request_case):
    _client, reply, _session, call, _module = request_case
    reply.raw = Mock()
    reply.raw.read1.side_effect = OSError("https://private.invalid/?token=synthetic")
    with pytest.raises(CalendarSyncError) as caught:
        call()
    assert str(caught.value) == "network_unavailable"
    if isinstance(reply, Response):
        assert reply.closed
    else:
        reply.close.assert_called_once()


def test_graph_cumulative_page_limit_never_returns_a_partial_collection(monkeypatch):
    first = {"value": [{"id": "one"}], "@odata.nextLink": graph.BASE + "/me/events?page=2"}
    second = {"value": [{"id": "two", "body": "x" * 100}]}
    first_size = len(json.dumps(first).encode("utf-8", errors="strict"))
    monkeypatch.setattr(graph, "MAX_COLLECTION_BYTES", first_size + 10)
    session = Mock()
    replies = [graph_response(first), graph_response(second)]
    session.request.side_effect = replies
    with pytest.raises(CalendarSyncError, match="calendar_response_too_large"):
        graph.GraphClient("synthetic-token", session).collection("/me/events")
    assert session.request.call_count == 2
    for reply in replies:
        reply.close.assert_called_once()


def test_graph_item_limit_never_returns_a_partial_collection(monkeypatch):
    monkeypatch.setattr(graph, "MAX_COLLECTION_ITEMS", 1)
    session = Mock()
    session.request.return_value = graph_response({"value": [{"id": "one"}, {"id": "two"}]})
    with pytest.raises(CalendarSyncError, match="calendar_response_too_large"):
        graph.GraphClient("synthetic-token", session).collection("/me/events")


@pytest.mark.parametrize(
    "target",
    [
        "https://other.invalid/v1.0/me/events",
        "https://graph.microsoft.com@other.invalid/v1.0/me/events",
        "https://graph.microsoft.com:444/v1.0/me/events",
        "https://graph.microsoft.com/v1.0/me/events#ignored",
        "https://graph.microsoft.com/v1.0/me/\nevents",
        "https://[invalid/v1.0/me/events",
        "file:///private",
    ],
)
def test_invalid_graph_nextlink_never_receives_credentials(target):
    session = Mock()
    session.request.return_value = graph_response({"value": [], "@odata.nextLink": target})
    with pytest.raises(CalendarSyncError, match="unsafe_graph_url"):
        graph.GraphClient("synthetic-token", session).collection("/me/events")
    assert session.request.call_count == 1


def test_graph_redirect_is_closed_without_reading_or_following_body():
    session = Mock()
    reply = graph_response({"ignored": "synthetic"}, 302)
    reply.headers = {"Location": "https://other.invalid/"}
    reply.raw = Mock()
    session.request.return_value = reply
    with pytest.raises(CalendarSyncError, match="graph_http_302"):
        graph.GraphClient("synthetic-token", session).collection("/me/events")
    assert session.request.call_count == 1
    reply.raw.read1.assert_not_called()
    reply.close.assert_called_once()


@pytest.mark.parametrize("byte_order", ["little", "big"])
def test_caldav_utf16_dtd_cannot_bypass_entity_rejection(byte_order):
    xml = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<!DOCTYPE d:multistatus [<!ENTITY injected "/calendar/other.ics">]>'
        + multi(xml_row("&injected;", "<d:getetag>synthetic</d:getetag>"))
    )
    # Construct UTF-16 bytes without adding a non-UTF-8 encoding API exemption.
    data = (b"\xff\xfe" if byte_order == "little" else b"\xfe\xff") + b"".join(
        ord(char).to_bytes(2, byte_order) for char in xml
    )
    with pytest.raises(CalendarSyncError, match="invalid_calendar_response"):
        caldav.multistatus(data)


def test_caldav_valid_utf16_response_remains_supported():
    xml = '<?xml version="1.0" encoding="UTF-16"?>' + multi(
        xml_row("/calendar/event.ics", "<d:getetag>synthetic</d:getetag>")
    )
    data = b"\xff\xfe" + b"".join(ord(char).to_bytes(2, "little") for char in xml)
    assert caldav.multistatus(data)[0][0] == "/calendar/event.ics"


@pytest.mark.parametrize("shape", ["deep", "wide"])
def test_caldav_xml_structure_limits_fail_closed(shape, monkeypatch):
    if shape == "deep":
        monkeypatch.setattr(caldav, "MAX_XML_DEPTH", 4)
        xml = multi("<x>" * 5 + "</x>" * 5)
    else:
        monkeypatch.setattr(caldav, "MAX_XML_ELEMENTS", 3)
        xml = multi("<x/>" * 4)
    with pytest.raises(CalendarSyncError, match="invalid_calendar_response"):
        caldav.multistatus(xml.encode("utf-8", errors="strict"))


def test_graph_deep_json_is_reported_without_exposing_payload():
    session = Mock()
    reply = graph_response({})
    reply.raw = HTTPResponse(
        body=BytesIO(b'{"private":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}"),
        preload_content=False,
    )
    session.request.return_value = reply
    with pytest.raises(CalendarSyncError, match="invalid_graph_response"):
        graph.GraphClient("synthetic-token", session).collection("/me/events")
    reply.close.assert_called_once()


def test_caldav_protection_failure_preserves_existing_credentials_without_plaintext(
    tmp_path, monkeypatch
):
    store = credentials.CalDAVCredentials(tmp_path)
    account = credentials.account_key("icloud", "fixture@example.invalid")
    path = store.path(account)
    path.write_bytes(b"previous encrypted fixture")
    monkeypatch.setattr(
        credentials, "crypt", Mock(side_effect=OSError("synthetic protection failure"))
    )
    with pytest.raises(CalendarSyncError, match="credential_protection_failed"):
        store.save("icloud", "fixture@example.invalid", "synthetic-password")
    assert path.read_bytes() == b"previous encrypted fixture"
    assert list(tmp_path.iterdir()) == [path]


def test_outlook_protection_failure_never_writes_plaintext_or_replaces_cache(tmp_path, monkeypatch):
    value = auth.MicrosoftAuth.__new__(auth.MicrosoftAuth)
    value.cache_path = tmp_path / "outlook-fixture.cache"
    value.cache_path.write_bytes(b"previous encrypted fixture")
    value.cache = Mock(has_state_changed=True)
    value.cache.serialize.return_value = '{"access_token":"synthetic-token"}'
    monkeypatch.setattr(
        auth, "_dpapi_crypt", Mock(side_effect=OSError("synthetic protection failure"))
    )
    with pytest.raises(OSError):
        value._save()
    assert value.cache_path.read_bytes() == b"previous encrypted fixture"
    assert list(tmp_path.iterdir()) == [value.cache_path]


def test_caldav_decrypted_credentials_for_another_account_are_rejected(tmp_path, monkeypatch):
    store = credentials.CalDAVCredentials(tmp_path)
    requested = credentials.account_key("icloud", "requested@example.invalid")
    store.path(requested).write_bytes(b"encrypted fixture")
    content = json.dumps(
        {"service": "icloud", "username": "other@example.invalid", "password": "synthetic"}
    ).encode("utf-8", errors="strict")
    monkeypatch.setattr(credentials, "crypt", lambda *_args: content)
    with pytest.raises(CalendarSyncError, match="login_required"):
        store.load(requested)


def test_caldav_custom_timezone_definitions_are_isolated_between_resources():
    def document(offset=None):
        timezone = (
            "BEGIN:VTIMEZONE\r\nTZID:AirCalendar/Synthetic-Isolation\r\nBEGIN:STANDARD\r\n"
            f"DTSTART:19700101T000000\r\nTZOFFSETFROM:{offset}\r\nTZOFFSETTO:{offset}\r\n"
            "END:STANDARD\r\nEND:VTIMEZONE\r\n"
            if offset
            else ""
        )
        return (
            "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n" + timezone + "BEGIN:VEVENT\r\nUID:synthetic\r\n"
            "DTSTART;TZID=AirCalendar/Synthetic-Isolation:20261005T100000\r\n"
            "DTEND;TZID=AirCalendar/Synthetic-Isolation:20261005T110000\r\n"
            "SUMMARY:Synthetic\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
        )

    first = records(BASE + "first/event.ics", "1", document("+0900"), zone="UTC")[0]
    second = records(BASE + "second/event.ics", "1", document("-0500"), zone="UTC")[0]
    assert first["task"]["deadline"] == "2026-10-05T01:00:00"
    assert second["task"]["deadline"] == "2026-10-05T15:00:00"
    with pytest.raises(CalendarSyncError, match="invalid_event_time"):
        records(BASE + "third/event.ics", "1", document(), zone="UTC")


def test_caldav_resource_text_cannot_be_interpreted_as_a_local_filename(tmp_path):
    from tests.test_caldav_sync import ICS

    local_file = tmp_path / "synthetic-local-calendar.ics"
    local_file.write_text(ICS, encoding="utf-8", errors="strict")
    with pytest.raises(CalendarSyncError, match="invalid_calendar_data"):
        records(BASE + "remote/event.ics", "1", str(local_file), zone="UTC")
