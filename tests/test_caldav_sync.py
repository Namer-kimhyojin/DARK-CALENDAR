# -*- coding: utf-8 -*-
"""Protocol and independent iCalendar regressions, without real user calendars."""

from datetime import UTC, datetime
from pathlib import Path
import sqlite3
import uuid

from icalendar import Calendar
import pytest

from calendar_app.application.calendar_sync_contract import CalendarSyncError, RemoteCalendarError
from calendar_app.infrastructure.caldav_sync.client import CalDAVClient, multistatus
from calendar_app.infrastructure.caldav_sync.conversion import (
    edited_calendar,
    new_calendar,
    records,
)
from calendar_app.infrastructure.caldav_sync.credentials import CalDAVCredentials
from calendar_app.infrastructure.caldav_sync.profiles import account_key, validate_url

BASE = "https://caldav.icloud.com/"
HREF = BASE + "calendar/event.ics"
ICS = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:fixture\r\nDTSTART:20261005T010000Z\r\nDTEND:20261005T020000Z\r\nSUMMARY:Meeting\r\nDESCRIPTION:Original\r\nBEGIN:VALARM\r\nACTION:DISPLAY\r\nTRIGGER:-PT15M\r\nDESCRIPTION:Reminder\r\nEND:VALARM\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"


class Response:
    def __init__(self, data=b"", status=207, headers=None):
        self.data = data.encode("utf-8", errors="strict") if isinstance(data, str) else data
        self.status_code, self.headers = status, headers or {}
        self.closed = False

    def iter_content(self, size):
        yield self.data

    def close(self):
        self.closed = True


class Session:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def xml_row(href, properties, status="200 OK"):
    return f"<d:response><d:href>{href}</d:href><d:propstat><d:prop>{properties}</d:prop><d:status>HTTP/1.1 {status}</d:status></d:propstat></d:response>"


def multi(rows):
    return (
        '<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
        + rows
        + "</d:multistatus>"
    )


def test_discovery_uses_principal_home_and_explicit_permissions():
    session = Session(
        Response(
            multi(
                xml_row(
                    "/",
                    "<d:current-user-principal><d:href>/user/</d:href></d:current-user-principal>",
                )
            )
        ),
        Response(
            multi(
                xml_row(
                    "/user/", "<c:calendar-home-set><d:href>/home/</d:href></c:calendar-home-set>"
                )
            )
        ),
        Response(
            multi(
                xml_row(
                    "/home/calendar/",
                    "<d:resourcetype><c:calendar/></d:resourcetype><d:displayname>Personal</d:displayname><d:current-user-privilege-set><d:privilege><d:write/></d:privilege></d:current-user-privilege-set>",
                )
            )
        ),
    )
    calendars = CalDAVClient("icloud", "fixture", "synthetic", session).calendars()
    assert calendars == [{"id": BASE + "home/calendar/", "name": "Personal", "can_edit": True}]
    assert [c[1] for c in session.calls] == [BASE, BASE + "user/", BASE + "home/"]
    assert session.calls[-1][2]["headers"]["Depth"] == "1"


@pytest.mark.parametrize(
    "url",
    [
        "http://caldav.icloud.com/",
        "https://evil.invalid/",
        "https://caldav.icloud.com.evil.invalid/",
        "https://user@caldav.icloud.com/",
        "https://caldav.icloud.com:444/",
        "https://caldav.icloud.com/?token=x",
    ],
)
def test_unsafe_endpoints_rejected_before_credentials_are_sent(url):
    session = Session()
    with pytest.raises(CalendarSyncError):
        CalDAVClient("icloud", "fixture", "synthetic", session).request("GET", url)
    assert not session.calls


def test_redirect_never_sends_credentials_to_external_host():
    response = Response(status=302, headers={"Location": "https://evil.invalid/"})
    session = Session(response)
    with pytest.raises(CalendarSyncError, match="unsafe_caldav_url"):
        CalDAVClient("icloud", "fixture", "synthetic", session).request(
            "PROPFIND", BASE, redirect=True
        )
    assert len(session.calls) == 1 and response.closed


def test_icloud_shard_redirect_is_supported():
    session = Session(
        Response(status=301, headers={"Location": "https://p42-caldav.icloud.com/home/"}),
        Response(b"ok", 200),
    )
    url, _, data = CalDAVClient("icloud", "fixture", "synthetic", session).request(
        "PROPFIND", BASE, redirect=True
    )
    assert url == "https://p42-caldav.icloud.com/home/" and data == b"ok"


def test_partial_report_is_rejected_in_full():
    good = xml_row(
        "/calendar/event.ics",
        '<d:getetag>"1"</d:getetag><c:calendar-data>' + ICS + "</c:calendar-data>",
    )
    bad = xml_row("/calendar/bad.ics", "<c:calendar-data/>", "403 Forbidden")
    client = CalDAVClient("icloud", "fixture", "synthetic", Session(Response(multi(good + bad))))
    with pytest.raises(CalendarSyncError, match="calendar_report_incomplete"):
        client.events(BASE + "calendar/", "2026-10-01T00:00:00+00:00", "2026-10-09T00:00:00+00:00")


def test_report_normalizes_utc_to_local_task_and_requires_same_collection():
    prop = '<d:getetag>"1"</d:getetag><c:calendar-data>' + ICS + "</c:calendar-data>"
    client = CalDAVClient(
        "icloud",
        "fixture",
        "synthetic",
        Session(Response(multi(xml_row("/calendar/event.ics", prop)))),
    )
    event = client.events(
        BASE + "calendar/", "2026-10-01T00:00:00+00:00", "2026-10-09T00:00:00+00:00"
    )[0]
    assert event["task"]["deadline"] == "2026-10-05T10:00:00"
    assert event["etag"] == '"1"'
    with pytest.raises(CalendarSyncError, match="unsafe_caldav_resource"):
        client.resource_url(BASE + "calendar/", "/other/event.ics")


@pytest.mark.parametrize(
    "data",
    [
        b"<!DOCTYPE a><a/>",
        b"not XML",
        b"<d:multistatus xmlns:d='DAV:'><d:response/></d:multistatus>",
    ],
)
def test_malformed_xml_never_returns_partial_results(data):
    with pytest.raises(CalendarSyncError):
        multistatus(data)


def test_recurrence_exclusions_and_overrides_have_stable_ids():
    data = ICS.replace(
        "SUMMARY:Meeting", "RRULE:FREQ=DAILY;COUNT=3\r\nEXDATE:20261006T010000Z\r\nSUMMARY:Meeting"
    )
    events = records(
        HREF, "1", data, datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 9, tzinfo=UTC)
    )
    assert len(events) == 2
    assert all(e["read_only"] and "#aircal-rid=" in e["id"] for e in events)
    assert len({e["id"] for e in events}) == 2
    with pytest.raises(CalendarSyncError, match="event_read_only"):
        edited_calendar(events[0]["task"], events[0])
    client = CalDAVClient("icloud", "fixture", "synthetic", Session())
    client.cache[HREF] = ("1", data)
    assert client.event(events[1]["id"])["task"]["deadline"] == "2026-10-07T10:00:00"
    with pytest.raises(CalendarSyncError, match="event_read_only"):
        client.delete(events[0]["id"], "1")
    assert client.session.calls == []


def test_removed_occurrence_is_not_replaced_by_master():
    data = ICS.replace("SUMMARY:Meeting", "RRULE:FREQ=DAILY;COUNT=3\r\nSUMMARY:Meeting")
    event = records(
        HREF, "1", data, datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 9, tzinfo=UTC)
    )[1]
    client = CalDAVClient("icloud", "fixture", "synthetic", Session())
    client.cache[HREF] = (
        "2",
        data.replace(
            "RRULE:FREQ=DAILY;COUNT=3", "RRULE:FREQ=DAILY;COUNT=3\r\nEXDATE:20261006T010000Z"
        ),
    )
    with pytest.raises(RemoteCalendarError) as error:
        client.event(event["id"])
    assert error.value.status == 404


def test_edit_preserves_alarm_uid_and_untouched_properties():
    remote = records(HREF, "1", ICS)[0]
    data = edited_calendar({**remote["task"], "name": "Changed"}, remote)
    calendar = Calendar.from_ical(data)
    event = calendar.walk("VEVENT")[0]
    assert str(event["SUMMARY"]) == "Changed"
    assert str(event["UID"]) == "fixture"
    assert str(event["DESCRIPTION"]) == "Original"
    assert len(calendar.walk("VALARM")) == 1


def test_invitations_are_read_only():
    remote = records(
        HREF,
        "1",
        ICS.replace(
            "SUMMARY:Meeting", "ORGANIZER:mailto:fixture@example.invalid\r\nSUMMARY:Meeting"
        ),
    )[0]
    assert remote["read_only"]
    with pytest.raises(CalendarSyncError):
        edited_calendar(remote["task"], remote)


def test_all_day_inclusive_local_end_round_trip():
    task = {
        "name": "Holiday",
        "deadline": "2026-10-05",
        "end_date": "2026-10-06",
        "all_day": 1,
        "description": "",
        "location": "",
    }
    data = new_calendar(task, str(uuid.uuid4()))
    assert b"DTEND;VALUE=DATE:20261007" in data
    assert records(HREF, "1", data)[0]["task"] == task


def test_record_timezone_conversion_preserves_instants_and_all_day_dates():
    remote = records(HREF, "1", ICS, zone="America/New_York")[0]
    assert remote["task"]["deadline"] == "2026-10-04T21:00:00"
    assert CalDAVClient.to_task(remote, "Asia/Seoul")["deadline"] == "2026-10-05T10:00:00"
    all_day = {
        "task": {
            **remote["task"],
            "all_day": 1,
            "deadline": "2026-10-05",
            "end_date": "2026-10-06",
        },
        "zone": "America/New_York",
    }
    assert CalDAVClient.to_task(all_day, "Asia/Seoul") == all_day["task"]


def test_create_retries_use_fixed_uid_and_conditional_put():
    transaction = str(uuid.uuid4())
    task = records(HREF, "1", ICS)[0]["task"]
    data = new_calendar(task, transaction)
    session = Session(Response(status=412), Response(data, 200, {"ETag": "tag"}))
    client = CalDAVClient("icloud", "fixture", "synthetic", session)
    event = client.create(BASE + "calendar/", client.from_task(task), transaction)
    assert event["transaction_id"] == transaction
    assert session.calls[0][2]["headers"]["If-None-Match"] == "*"
    assert transaction in session.calls[0][1]


def test_conditional_update_and_delete():
    task = records(HREF, "tag", ICS)[0]["task"]
    session = Session(
        Response(status=204), Response(ICS, 200, {"ETag": "new"}), Response(status=204)
    )
    client = CalDAVClient("icloud", "fixture", "synthetic", session)
    client.cache[HREF] = ("tag", ICS)
    client.update(
        HREF, edited_calendar({**task, "name": "Changed"}, records(HREF, "tag", ICS)[0]), "tag"
    )
    assert session.calls[0][2]["headers"]["If-Match"] == "tag"
    client.delete(HREF, "new")
    assert session.calls[-1][2]["headers"]["If-Match"] == "new"


def test_get_etag_header_is_case_insensitive():
    client = CalDAVClient(
        "icloud", "fixture", "synthetic", Session(Response(ICS, 200, {"etag": "lower-case-header"}))
    )
    assert client.event(HREF)["etag"] == "lower-case-header"


def test_naver_never_sends_a_write_request():
    client = CalDAVClient("naver", "fixture", "synthetic", Session())
    with pytest.raises(CalendarSyncError):
        client.create(
            "https://caldav.calendar.naver.com/calendar/", {"task": {}}, str(uuid.uuid4())
        )
    with pytest.raises(CalendarSyncError):
        client.delete("https://caldav.calendar.naver.com/calendar/event.ics", "1")
    assert client.session.calls == []


def test_windows_credentials_are_encrypted_and_service_isolated(tmp_path):
    store = CalDAVCredentials(tmp_path)
    first = store.save("icloud", "fixture@example.invalid", "synthetic-password-for-test")
    second = store.save("naver", "fixture@example.invalid", "different-synthetic-password")
    assert first != second
    assert b"synthetic-password-for-test" not in store.path(first).read_bytes()
    assert store.load(first)["password"] == "synthetic-password-for-test"
    assert store.load(second)["service"] == "naver"
    store.remove(first)
    assert store.path(second).exists()
    with pytest.raises(CalendarSyncError):
        store.load(first)
    with pytest.raises(CalendarSyncError):
        store.path("../escape")


def test_accounts_and_allowed_hosts():
    assert account_key("icloud", "A@EXAMPLE.invalid") == account_key("icloud", "a@example.invalid")
    assert account_key("icloud", "a") != account_key("naver", "a")
    assert validate_url("naver", "https://caldav.calendar.naver.com/")
    assert isinstance(CalDAVCredentials(Path(".")), CalDAVCredentials)


def test_override_occurrence_retains_original_recurrence_identity():
    master = ICS.replace("SUMMARY:Meeting", "RRULE:FREQ=DAILY;COUNT=3\r\nSUMMARY:Meeting")
    override = "BEGIN:VEVENT\r\nUID:fixture\r\nRECURRENCE-ID:20261006T010000Z\r\nDTSTART:20261006T030000Z\r\nDTEND:20261006T040000Z\r\nSUMMARY:Moved occurrence\r\nEND:VEVENT\r\n"
    events = records(
        HREF,
        "1",
        master.replace("END:VCALENDAR", override + "END:VCALENDAR"),
        datetime(2026, 10, 1, tzinfo=UTC),
        datetime(2026, 10, 9, tzinfo=UTC),
    )
    changed = next(e for e in events if e["task"]["name"] == "Moved occurrence")
    assert "2026-10-06T01" in changed["id"]
    assert changed["task"]["deadline"] == "2026-10-06T12:00:00"


def test_dense_recurrence_rejected_before_expansion():
    data = ICS.replace("SUMMARY:Meeting", "RRULE:FREQ=SECONDLY\r\nSUMMARY:Meeting")
    with pytest.raises(CalendarSyncError, match="too_many_events"):
        records(
            HREF, "1", data, datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 9, tzinfo=UTC)
        )


def test_encoded_path_escape_is_rejected():
    client = CalDAVClient("icloud", "fixture", "synthetic", Session())
    with pytest.raises(CalendarSyncError):
        client.resource_url(BASE + "calendar/", "/calendar/%2e%2e/other.ics")


def test_real_caldav_adapter_with_common_engine_imports_once_and_preserves_partial_failure():
    from calendar_app.infrastructure.calendar_sync.engine import CalendarSyncEngine
    from calendar_app.infrastructure.calendar_sync.repository import CalendarSyncRepository

    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE calendar(id TEXT PRIMARY KEY,type TEXT,name TEXT,color TEXT,is_active INTEGER,access_role TEXT); CREATE TABLE unified_task(id INTEGER PRIMARY KEY,name TEXT,deadline TEXT,end_date TEXT,all_day INTEGER,description TEXT,location TEXT,calendar_id TEXT,type TEXT,gcal_dirty INTEGER,gcal_sync_mode TEXT,recurrence TEXT,updated_at TEXT);"
    )
    repo = CalendarSyncRepository(conn, "caldav")
    repo.register(
        "caldav::fixture", {"id": BASE + "calendar/", "name": "Fixture", "can_edit": True}
    )
    prop = '<d:getetag>"1"</d:getetag><c:calendar-data>' + ICS + "</c:calendar-data>"
    session = Session(
        Response(multi(xml_row("/calendar/event.ics", prop))),
        Response(multi(xml_row("/calendar/event.ics", prop))),
        Response(multi(xml_row("/calendar/bad.ics", "", "403 Forbidden"))),
    )
    client = CalDAVClient("icloud", "fixture", "synthetic", session)
    engine = CalendarSyncEngine(client, repo, "caldav::fixture")
    try:
        assert engine.run()["imported"] == 1
        assert engine.run()["imported"] == 0
        with pytest.raises(CalendarSyncError):
            engine.run()
        assert conn.execute("SELECT COUNT(*) FROM unified_task").fetchone()[0] == 1
        assert conn.execute("SELECT gcal_dirty,gcal_sync_mode FROM unified_task").fetchone()[:] == (
            0,
            "unknown",
        )
    finally:
        conn.close()
