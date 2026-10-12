# -*- coding: utf-8 -*-
"""Remote-response and concurrent selection/permission boundaries, without accounts."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import Mock

import pytest

from calendar_app.application.calendar_sync_contract import CalendarSyncError
from calendar_app.infrastructure.caldav_sync.client import CalDAVClient
from calendar_app.infrastructure.caldav_sync.conversion import new_calendar, records
from calendar_app.infrastructure.calendar_sync.http_retry import (
    MAX_RETRY_AFTER_SECONDS,
    retry_after_seconds,
)
from calendar_app.infrastructure.outlook_sync.conversion import from_graph
from calendar_app.infrastructure.outlook_sync.graph import GraphClient
from tests.test_caldav_sync import BASE, HREF, ICS, Response, Session
from tests.test_calendar_sync_engine import imported, setup, task
from tests.test_calendar_sync_engine import repo as repo


def graph_response(data):
    return Mock(status_code=200, json=Mock(return_value=data))


@pytest.mark.parametrize(
    "data", [None, [], "response", {"value": None}, {"value": [None]}, {"value": ["event"]}]
)
def test_graph_malformed_success_is_a_safe_sync_error(data):
    session = Mock()
    session.request.return_value = graph_response(data)
    client = GraphClient("fixture-token", session)
    with pytest.raises(CalendarSyncError, match="invalid_graph_response"):
        client.collection("/me/calendars")
    assert session.request.call_count == 1


@pytest.mark.parametrize("next_link", [[], {}, 123])
def test_graph_malformed_next_page_cannot_apply_a_partial_collection(next_link):
    session = Mock()
    session.request.return_value = graph_response(
        {"value": [{"id": "first"}], "@odata.nextLink": next_link}
    )
    client = GraphClient("fixture-token", session)
    with pytest.raises(CalendarSyncError, match="invalid_graph_response"):
        client.collection("/me/calendars")
    assert session.request.call_count == 1


def test_invalid_later_event_preserves_the_entire_previous_snapshot(repo):
    provider, key, engine = setup(repo)
    provider.remote = {
        "first": {"id": "first", "etag": "1", "task": task()},
        "broken": {"id": "broken", "etag": "1", "task": task("Broken")},
    }
    convert = provider.to_task

    def invalid_later_event(event, zone):
        if event["id"] == "broken":
            raise CalendarSyncError("invalid_event_time")
        return convert(event, zone)

    provider.to_task = invalid_later_event
    with pytest.raises(CalendarSyncError, match="invalid_event_time"):
        engine.run()
    assert repo.tasks(key) == []
    assert repo.links(key) == {}
    assert provider.writes == []


def revoke_permission(repo, key, *, metadata=True):
    repo.conn.execute("UPDATE calendar SET access_role='reader' WHERE id=?", (key,))
    if metadata:
        repo.conn.execute("UPDATE calendar_sync_calendar SET can_edit=0 WHERE local_id=?", (key,))
    repo.conn.commit()


@pytest.mark.parametrize("metadata", [True, False])
def test_permission_revoked_during_create_conversion_never_sends_a_write(repo, metadata):
    provider, key, engine = setup(repo)
    tid = repo.import_task(key, task())
    convert = provider.from_task

    def revoke_before_write(local, zone):
        revoke_permission(repo, key, metadata=metadata)
        return convert(local, zone)

    provider.from_task = revoke_before_write
    result = engine.run()
    assert provider.writes == []
    assert repo.task(tid)["name"] == "Meeting"
    assert repo.task_link(tid)["event_id"] is None
    assert result["issues"] == 1
    assert repo.issues("account")[0]["kind"] == "calendar_read_only"


@pytest.mark.parametrize(
    "values", [[{}], [{"id": ""}], [{"id": 123}], [{"id": "same"}, {"id": "same"}]]
)
def test_graph_invalid_collection_identity_is_rejected_before_selection(values):
    session = Mock()
    session.request.return_value = graph_response({"value": values})
    with pytest.raises(CalendarSyncError, match="invalid_graph_response|duplicate_remote_event"):
        GraphClient("fixture-token", session).collection("/me/calendars")


@pytest.mark.parametrize("can_edit", ["false", "true", 0, 1, None])
def test_graph_permissions_must_be_boolean_instead_of_truthy_values(can_edit):
    session = Mock()
    session.request.return_value = graph_response(
        {"value": [{"id": "calendar", "name": "Calendar", "canEdit": can_edit}]}
    )
    with pytest.raises(CalendarSyncError, match="invalid_graph_response"):
        GraphClient("fixture-token", session).calendars()


def test_graph_missing_collection_value_is_not_an_empty_success():
    session = Mock()
    session.request.return_value = graph_response({})
    with pytest.raises(CalendarSyncError, match="invalid_graph_response"):
        GraphClient("fixture-token", session).calendars()


@pytest.mark.parametrize(
    "value, expected",
    [
        ("120", 120),
        (" 60 ", 60),
        ("0", None),
        ("-1", None),
        ("1.5", None),
        ("NaN", None),
        (None, None),
        ("999999999999", MAX_RETRY_AFTER_SECONDS),
    ],
)
def test_retry_after_is_validated_and_bounded(value, expected):
    assert retry_after_seconds(value) == expected


def test_retry_after_http_date_uses_utc_and_rejects_expired_dates():
    now = datetime(2026, 10, 7, tzinfo=UTC)
    future = format_datetime(now + timedelta(seconds=91), usegmt=True)
    assert retry_after_seconds(future, now=now) == 91
    assert retry_after_seconds(format_datetime(now, usegmt=True), now=now) is None


@pytest.mark.parametrize("status", [401, 403, 404, 412, 429, 503])
def test_graph_remote_errors_preserve_status_and_safe_retry_after(status):
    session = Mock()
    response = graph_response({"private": "never display"})
    response.status_code = status
    response.headers = {"Retry-After": "120"}
    session.request.return_value = response
    with pytest.raises(CalendarSyncError) as error:
        GraphClient("fixture-token", session).request("GET", "/me/events")
    assert error.value.status == status
    assert str(error.value) == f"graph_http_{status}"
    assert error.value.retry_after == 120


@pytest.mark.parametrize("status", [401, 403, 404, 412, 429, 503])
def test_caldav_remote_errors_preserve_status_close_response_and_retry_after(status):
    response = Response(b"private response", status, {"retry-after": "120"})
    session = Session(response)
    with pytest.raises(CalendarSyncError) as error:
        CalDAVClient("icloud", "fixture", "synthetic", session).request("REPORT", BASE)
    assert error.value.status == status
    assert str(error.value) == f"remote_http_{status}"
    assert error.value.retry_after == 120
    assert response.closed


def test_permission_revoked_during_update_conversion_preserves_local_changes(repo):
    provider, key, engine, tid = imported(repo)
    repo.conn.execute("UPDATE unified_task SET name='Local edit' WHERE id=?", (tid,))
    repo.conn.commit()
    convert = provider.edit_payload

    def revoke_before_write(local, remote, zone):
        revoke_permission(repo, key)
        return convert(local, remote, zone)

    provider.edit_payload = revoke_before_write
    result = engine.run()
    assert provider.writes == []
    assert provider.remote["remote"]["task"]["name"] == "Meeting"
    assert repo.task(tid)["name"] == "Local edit"
    assert result["issues"] == 1


def test_permission_revoked_after_delete_probe_preserves_delete_queue(repo):
    provider, key, engine, tid = imported(repo)
    repo.conn.execute("DELETE FROM unified_task WHERE id=?", (tid,))
    repo.conn.commit()
    get = provider.event

    def revoke_after_probe(event_id):
        event = get(event_id)
        revoke_permission(repo, key)
        return event

    provider.event = revoke_after_probe
    result = engine.run()
    assert provider.writes == []
    assert "remote" in provider.remote
    queue = repo.conn.execute("SELECT * FROM calendar_sync_delete_queue").fetchone()
    assert queue["error"] == "calendar_read_only"
    assert result["issues"] == 1


@pytest.mark.parametrize("all_day", [False, True])
def test_caldav_equal_explicit_end_is_rejected_instead_of_importing_an_invalid_range(all_day):
    time = ";VALUE=DATE:20261007" if all_day else ":20261007T010000Z"
    data = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:fixture\r\n"
        f"DTSTART{time}\r\nDTEND{time}\r\nSUMMARY:Invalid range\r\n"
        "END:VEVENT\r\nEND:VCALENDAR\r\n"
    ).encode("utf-8", errors="strict")
    with pytest.raises(CalendarSyncError, match="invalid_event_time"):
        records("https://caldav.icloud.com/cal/fixture.ics", '"1"', data)


def test_deselected_calendar_still_blocks_writes_after_conversion(repo):
    provider, key, engine = setup(repo)
    tid = repo.import_task(key, task())
    convert = provider.from_task

    def deselect(local, zone):
        repo.conn.execute("UPDATE calendar SET is_active=0 WHERE id=?", (key,))
        repo.conn.commit()
        return convert(local, zone)

    provider.from_task = deselect
    engine.run()
    assert provider.writes == []
    assert deepcopy(repo.task(tid))["calendar_id"] == key


@pytest.mark.parametrize(
    "event",
    [
        {},
        {"start": None, "end": None},
        {"start": {"dateTime": "2026-10-07"}, "end": "bad"},
        {"start": {"dateTime": "2026-10-07T10:00:00"}, "end": {"dateTime": "2026-10-07T09:00:00"}},
        {
            "isAllDay": True,
            "start": {"dateTime": "2026-10-07T15:00:00"},
            "end": {"dateTime": "2026-10-07T15:00:00"},
        },
    ],
)
def test_outlook_invalid_nested_times_are_safe_errors(event):
    with pytest.raises(CalendarSyncError, match="invalid_event_time|invalid_event_range"):
        from_graph(event)


def test_caldav_successful_create_receipt_cannot_link_a_different_uid():
    transaction = "de79dcf3-4503-43aa-bde9-04331b4c96a0"
    session = Session(Response(status=201), Response(ICS, 200, {"ETag": '"1"'}))
    client = CalDAVClient("icloud", "fixture", "synthetic", session)
    with pytest.raises(CalendarSyncError, match="create_conflict"):
        client.create(BASE + "calendar/", client.from_task(task()), transaction)
    assert [call[0] for call in session.calls] == ["PUT", "GET"]


def test_caldav_successful_update_receipt_cannot_reassign_an_existing_uid():
    session = Session(
        Response(status=204),
        Response(ICS.replace("UID:fixture", "UID:replacement"), 200, {"ETag": '"2"'}),
    )
    client = CalDAVClient("icloud", "fixture", "synthetic", session)
    client.cache[HREF] = ('"1"', ICS)
    payload = client.edit_payload(task("Changed"), client.event(HREF))
    with pytest.raises(CalendarSyncError, match="remote_identity_changed"):
        client.update(HREF, payload, '"1"')
    assert [call[0] for call in session.calls] == ["PUT", "GET"]


@pytest.mark.parametrize(
    "field, value",
    [
        ("subject", {}),
        ("body", "invalid"),
        ("bodyPreview", {}),
        ("body", {"contentType": "text", "content": []}),
        ("location", {"displayName": {}}),
    ],
)
def test_outlook_non_text_fields_cannot_reach_sqlite(field, value):
    event = {
        "id": "event",
        "start": {"dateTime": "2026-10-07T01:00:00"},
        "end": {"dateTime": "2026-10-07T02:00:00"},
        field: value,
    }
    with pytest.raises(CalendarSyncError, match="invalid_graph_response"):
        from_graph(event)


@pytest.mark.parametrize("identifier", [None, "", 123, "different"])
def test_graph_existing_event_receipt_cannot_change_link_identity(identifier):
    session = Mock()
    session.request.return_value = graph_response({"id": identifier})
    with pytest.raises(CalendarSyncError, match="invalid_graph_response"):
        GraphClient("fixture-token", session).event("requested")


def test_graph_canonical_permission_comes_only_from_boolean_can_edit():
    session = Mock()
    session.request.return_value = graph_response(
        {"value": [{"id": "calendar", "name": "Calendar", "canEdit": False, "can_edit": "true"}]}
    )
    calendar = GraphClient("fixture-token", session).calendars()[0]
    assert calendar["can_edit"] is False


def test_caldav_create_retry_requires_uid_and_transaction_identity():
    transaction = "de79dcf3-4503-43aa-bde9-04331b4c96a0"
    data = new_calendar(task(), transaction).replace(
        ("UID:" + transaction).encode("utf-8", errors="strict"), b"UID:replacement"
    )
    session = Session(Response(status=412), Response(data, 200, {"ETag": '"1"'}))
    client = CalDAVClient("icloud", "fixture", "synthetic", session)
    with pytest.raises(CalendarSyncError, match="create_conflict"):
        client.create(BASE + "calendar/", client.from_task(task()), transaction)
    assert [call[0] for call in session.calls] == ["PUT", "GET"]


@pytest.mark.parametrize(
    "profile",
    [
        {},
        {"id": None},
        {"id": ""},
        {"id": " "},
        {"id": 123},
        {"id": "account", "mail": []},
        {"id": "account", "userPrincipalName": {}},
        {"id": "account", "displayName": 123},
    ],
)
def test_graph_invalid_profile_cannot_create_a_fake_connected_account(profile):
    session = Mock()
    session.request.return_value = graph_response(profile)
    with pytest.raises(CalendarSyncError, match="invalid_graph_response"):
        GraphClient("fixture-token", session).profile()


@pytest.mark.parametrize(
    "field, value",
    [
        ("@odata.etag", {}),
        ("@odata.etag", ""),
        ("@odata.etag", "tag\r\nheader"),
        ("transactionId", []),
        ("transactionId", 1),
        ("isCancelled", "false"),
        ("isAllDay", "false"),
    ],
)
def test_graph_invalid_revision_transaction_and_flags_are_rejected(field, value):
    session = Mock()
    session.request.return_value = graph_response({"value": [{"id": "event", field: value}]})
    with pytest.raises(CalendarSyncError, match="invalid_graph_response"):
        GraphClient("fixture-token", session).collection("/me/events")
