# -*- coding: utf-8 -*-
"""File audit regressions with synthetic provider responses and no account access."""

from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from unittest.mock import patch

from googleapiclient.errors import HttpError
from httplib2 import Response
import pytest

from calendar_app.application.calendar_sync_contract import CalendarSyncError
from calendar_app.infrastructure.caldav_sync import conversion
from calendar_app.infrastructure.google_sync import common, engine, helpers, oauth, service
from tests.support import TemporaryDatabaseTestCase
from tests.test_gcal_sync_integration import (
    FakeDate,
    FakeGoogleEvent,
    FakeSettings,
    FakeSyncService,
)


@pytest.mark.parametrize("end", ["", "2026-10-08T10:00:00", "2026-10-08T09:00:00"])
def test_google_batch_create_supplies_the_same_default_hour_as_single_create(end):
    sync = service.CalendarSyncService(time_zone="Asia/Seoul")
    body = sync._build_event_body_from_op(
        {"summary": "Fixture", "start_iso": "2026-10-08T10:00:00", "end_iso": end}
    )
    start = datetime.fromisoformat(body["start"]["dateTime"])
    finish = datetime.fromisoformat(body["end"]["dateTime"])
    assert finish - start == timedelta(hours=1)


@pytest.mark.parametrize("month,offset", [(1, "-05:00"), (7, "-04:00")])
def test_google_batch_create_uses_the_event_date_for_dst(monkeypatch, month, offset):
    sync = service.CalendarSyncService(time_zone="America/New_York")
    monkeypatch.setattr(service, "timezone_offset_for_name", lambda _: "+09:00")
    body = sync._build_event_body_from_op(
        {
            "summary": "Fixture",
            "start_iso": f"2026-{month:02d}-08T10:00:00",
            "end_iso": f"2026-{month:02d}-08T11:00:00",
        }
    )
    assert body["start"]["dateTime"].endswith(offset)
    assert body["end"]["dateTime"].endswith(offset)


@pytest.mark.parametrize("value", ["-1", "NaN", "-inf", "0"])
def test_google_invalid_retry_after_preserves_positive_retry_delay(value):
    sync = service.CalendarSyncService()
    failure = HttpError(Response({"status": "429", "retry-after": value}), b"{}")
    assert sync._get_retry_after_secs(failure, 2.0) == 2.0


@pytest.mark.parametrize("field", ["client_id", "client_secret", "auth_uri", "token_uri"])
@pytest.mark.parametrize("value", [{"invalid": "value"}, ["invalid"]])
def test_google_invalid_client_field_types_are_safe_errors(tmp_path, field, value):
    config = {
        "installed": {
            "client_id": "fixture",
            "client_secret": "fixture",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    config["installed"][field] = value
    path = tmp_path / "client.json"
    path.write_text(json.dumps(config), encoding="utf-8", errors="strict")
    with pytest.raises(oauth.GoogleAuthError) as caught:
        oauth.load_desktop_client_config(path)
    assert caught.value.kind == "auth_client_invalid"


@pytest.mark.parametrize("property_name", ["DTSTART", "DTEND", "RDATE", "EXDATE"])
def test_caldav_unresolved_timezone_is_not_silently_imported_as_floating(property_name):
    properties = {"DTSTART": "20261008T100000", "DTEND": "20261008T110000"}
    properties[property_name + ";TZID=Unknown/Synthetic"] = (
        properties.pop(property_name) if property_name in properties else "20261009T100000"
    )
    data = "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "BEGIN:VEVENT",
            "UID:fixture",
            *[f"{key}:{value}" for key, value in properties.items()],
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        ]
    )
    with pytest.raises(CalendarSyncError, match="invalid_event_time"):
        conversion.records(
            "https://caldav.icloud.com/calendar/fixture.ics",
            "etag",
            data,
            datetime(2026, 10, 1, tzinfo=UTC),
            datetime(2026, 11, 1, tzinfo=UTC),
        )


def test_google_update_local_persistence_failure_is_not_a_success(monkeypatch):
    task = {
        "id": 7,
        "gcal_event_id": "fixture",
        "calendar_id": "gcal::team",
        "gcal_source_calendar_id": "team",
        "deadline": "2026-10-08T10:00:00",
        "gcal_remote_updated_at": "2026-10-07T00:00:00Z",
        "gcal_last_synced_at": "2026-10-07T00:01:00Z",
    }
    monkeypatch.setattr(helpers, "_is_gcal_enabled", lambda _: True)
    monkeypatch.setattr(engine.task_repo, "get_unified_task", lambda _: task.copy())
    monkeypatch.setattr(helpers, "_mark_task_synced", lambda *args, **kwargs: False)
    sync = SimpleNamespace(
        is_authenticated=True, calendar_id="team", update_event=lambda *a, **k: True
    )
    result = helpers.sync_task_to_google(SimpleNamespace(gcal_sync=sync), task)
    assert not result.success
    assert result.error_kind == "local_state"


@pytest.mark.parametrize("missing_callback", [False, True])
def test_google_batch_create_requires_local_persistence_and_every_callback(
    monkeypatch, missing_callback
):
    tasks = [
        {"id": number, "calendar_id": "gcal::team", "deadline": "2026-10-08T10:00:00"}
        for number in (7, 8)
    ]
    failures = []
    monkeypatch.setattr(engine, "_get_default_gcal_id", lambda _: "team")
    monkeypatch.setattr(engine, "_writable_gcal_ids", lambda: {"team"})
    monkeypatch.setattr(engine.task_repo, "get_google_sync_tasks", lambda: tasks)
    monkeypatch.setattr(
        engine.task_repo,
        "get_unified_task",
        lambda number: next(t for t in tasks if t["id"] == number),
    )
    monkeypatch.setattr(
        engine.task_repo, "mark_unified_task_gcal_synced", lambda *a, **k: missing_callback
    )
    monkeypatch.setattr(
        engine.task_repo, "mark_unified_task_gcal_failed", lambda *a, **k: failures.append(a)
    )
    results = [
        {"local_task_id": number, "success": True, "event_id": f"remote-{number}"}
        for number in ((7,) if missing_callback else (7, 8))
    ]
    sync = SimpleNamespace(is_authenticated=True, batch_create_events=lambda _: results)
    assert engine._push_local_changes_to_google(SimpleNamespace(gcal_sync=sync)) == (
        (1, 1, 0) if missing_callback else (0, 2, 0)
    )
    assert len(failures) == (1 if missing_callback else 2)


def test_google_create_key_survives_local_edits_and_failure_timestamp_updates():
    task = {"id": 7, "created_at": "2026-10-08 10:00:00", "updated_at": "2026-10-08 10:00:00"}
    first = common.google_create_idempotency_key(task)
    task.update(name="Latest", updated_at="2026-10-08 11:00:00")
    assert common.google_create_idempotency_key(task) == first
    assert first != common.google_create_idempotency_key({**task, "id": 8})


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("same_payload", [False, True])
def test_google_create_retry_conflict_requires_a_verified_matching_receipt(
    monkeypatch, batch, same_payload
):
    failure = HttpError(Response({"status": "409"}), b"{}")
    sync = service.CalendarSyncService(time_zone="UTC")
    sync.is_authenticated = True
    op = {
        "local_task_id": 7,
        "summary": "Fixture",
        "start_iso": "2026-10-08T10:00:00Z",
        "end_iso": "2026-10-08T11:00:00Z",
        "idempotency_key": "task7",
        "calendar_id": "team",
    }
    remote = {**sync._build_event_body_from_op(op), "id": "task7"}
    if not same_payload:
        remote["summary"] = "Preserve remote edit"
    writes = []
    reads = []

    def insert(**kwargs):
        writes.append(kwargs)
        return SimpleNamespace(execute=lambda: (_ for _ in ()).throw(failure))

    def get(**kwargs):
        reads.append(kwargs)
        return SimpleNamespace(execute=lambda: remote)

    class Batch:
        def __init__(self, callback):
            self.callback = callback

        def add(self, request, request_id):
            self.request_id = request_id

        def execute(self):
            self.callback(self.request_id, None, failure)

    sync.service = SimpleNamespace(
        events=lambda: SimpleNamespace(insert=insert, get=get),
        new_batch_http_request=lambda callback: Batch(callback),
    )
    monkeypatch.setattr(service.time, "sleep", lambda _: None)
    if batch:
        result = sync.batch_create_events([op])
        assert result[0]["success"] is same_payload
    else:
        result = sync.create_event(
            op["summary"],
            op["start_iso"],
            op["end_iso"],
            calendar_id="team",
            idempotency_key="task7",
        )
        assert result == ("task7" if same_payload else None)
    assert writes and all(write["body"]["id"] == "task7" for write in writes)
    assert reads == [{"calendarId": "team", "eventId": "task7"}]


@pytest.mark.parametrize("month,utc_hour", [(1, 15), (7, 14)])
def test_google_pull_uses_event_specific_dst_offsets(month, utc_hour):
    event = SimpleNamespace(
        start_time=f"2026-{month:02d}-08T{utc_hour}:00:00Z",
        end_time=f"2026-{month:02d}-08T{utc_hour + 1}:00:00Z",
    )
    assert engine._normalize_gcal_event_datetimes(
        event, target_tz_offset="-04:00", target_tz_name="America/New_York"
    ) == (f"2026-{month:02d}-08 10:00:00", f"2026-{month:02d}-08 11:00:00", False)


def test_google_pull_retains_instants_across_the_dst_fall_back_hour():
    event = SimpleNamespace(start_time="2026-11-01T05:30:00Z", end_time="2026-11-01T06:15:00Z")
    assert engine._normalize_gcal_event_datetimes(event, target_tz_name="America/New_York") == (
        "2026-11-01 01:30:00",
        "2026-11-01 01:15:00",
        False,
    )


class GooglePullOwnershipAuditTests(TemporaryDatabaseTestCase):
    def test_full_pull_keeps_matching_unlinked_local_task_in_its_original_calendar(self):
        local_id = engine.task_repo.create_unified_task(
            {
                "name": "Fixture",
                "type": "schedule",
                "calendar_id": "local::home",
                "gcal_source_calendar_id": "team",
                "gcal_sync_mode": "unknown",
                "gcal_dirty": 0,
                "deadline": "2026-10-08 10:00:00",
                "end_date": "2026-10-08 11:00:00",
            }
        )
        event = FakeGoogleEvent(
            "remote", "Fixture", "2026-10-08T10:00:00+09:00", "2026-10-08T11:00:00+09:00"
        )
        app = SimpleNamespace(
            settings=FakeSettings(
                {
                    "gcal_enabled": "true",
                    "gcal_calendar_id": "team",
                    "gcal_bound_calendar_id": "team",
                }
            ),
            gcal_sync=FakeSyncService([event]),
            current_date=FakeDate("2026-10-08"),
        )
        with (
            patch.object(engine, "_get_default_gcal_id", return_value="team"),
            patch.object(engine, "_refresh_resolved_primary_alias_id", return_value="team"),
            patch.object(engine, "_calendar_source_summary_map", return_value={"team": "Team"}),
            patch.object(engine, "_process_google_delete_queue", return_value=(0, 0)),
            patch.object(engine, "_should_refresh_calendar_list", return_value=False),
            patch.object(engine, "_active_sync_calendar_ids", return_value=["team"]),
            patch.object(engine, "_push_local_changes_to_google", return_value=(0, 0, 0)),
            patch.object(engine, "_should_run_auto_heal_orphans", return_value=False),
        ):
            assert engine.sync_google_calendar(app, silent=True)
        local = engine.task_repo.get_unified_task(local_id)
        assert local["calendar_id"] == "local::home"
        assert not local["gcal_event_id"]
        conn = engine.gcal_db_adapter.get_connection()
        remote = conn.execute("SELECT * FROM unified_task WHERE gcal_event_id='remote'").fetchone()
        assert remote["id"] != local_id
        assert remote["calendar_id"] == "gcal::team"
