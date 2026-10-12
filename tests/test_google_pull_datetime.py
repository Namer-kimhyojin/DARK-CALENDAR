# -*- coding: utf-8 -*-
"""Normalize real Google time semantics without weakening full-snapshot validation."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from calendar_app.infrastructure.db import database_unified, task_repo
from calendar_app.infrastructure.google_sync import engine, service
from tests.support import TemporaryDatabaseTestCase
from tests.test_gcal_sync_integration import FakeDate, FakeSettings


def _raw_event(start, end):
    return {"id": "point-event", "summary": "Synthetic event", "start": start, "end": end}


@pytest.mark.parametrize(
    "start, end, expected",
    [
        (
            "2026-10-09T09:00:00.100000+09:00",
            "2026-10-09T09:00:00.900000+09:00",
            ("2026-10-09 09:00:00", "2026-10-09 09:00:00", False),
        ),
        (
            "2026-10-09T00:00:00.999999Z",
            "2026-10-09T00:00:01Z",
            ("2026-10-09 09:00:00", "2026-10-09 09:00:01", False),
        ),
        (
            "2026-10-09T09:00:00+09:00",
            "2026-10-09T01:00:00Z",
            ("2026-10-09 09:00:00", "2026-10-09 10:00:00", False),
        ),
        (
            "2026-10-09T09:00:00+09:00",
            "2026-10-09T09:00:00+09:00",
            ("2026-10-09 09:00:00", "2026-10-09 09:00:00", False),
        ),
        ("2026-10-09", "2026-10-10", ("2026-10-09 00:00:00", "2026-10-09 00:00:00", True)),
        ("2026-03-07", "2026-03-10", ("2026-03-07 00:00:00", "2026-03-09 00:00:00", True)),
    ],
)
def test_normalization_compares_full_precision_before_local_second_projection(start, end, expected):
    event = SimpleNamespace(start_time=start, end_time=end)
    assert engine._normalize_gcal_event_datetimes(event) == expected


@pytest.mark.parametrize(
    "start, end, expected",
    [
        (
            {"dateTime": "2026-07-15T09:00:00", "timeZone": "America/New_York"},
            {"dateTime": "2026-07-15T10:00:00", "timeZone": "America/New_York"},
            ("2026-07-15 22:00:00", "2026-07-15 23:00:00", False),
        ),
        (
            {"dateTime": "2026-01-15T09:00:00", "timeZone": "America/New_York"},
            {"dateTime": "2026-01-15T10:00:00", "timeZone": "America/New_York"},
            ("2026-01-15 23:00:00", "2026-01-16 00:00:00", False),
        ),
        (
            {"dateTime": "2026-11-01T01:30:00-04:00", "timeZone": "America/New_York"},
            {"dateTime": "2026-11-01T01:30:00-05:00", "timeZone": "America/New_York"},
            ("2026-11-01 14:30:00", "2026-11-01 15:30:00", False),
        ),
    ],
)
def test_api_explicit_timezone_and_dst_offsets_are_resolved(start, end, expected):
    event = service.CalendarSyncService()._to_google_event(_raw_event(start, end))
    assert engine._normalize_gcal_event_datetimes(event) == expected


@pytest.mark.parametrize(
    "start",
    [
        {"dateTime": "2026-10-09T09:00:00"},
        {"dateTime": "2026-10-09T09:00:00", "timeZone": "invalid/calendar-zone"},
        {"dateTime": "2026-10-09T09:00:00", "timeZone": []},
    ],
)
def test_timezone_free_datetime_requires_a_valid_explicit_api_timezone(start):
    with pytest.raises(ValueError):
        service.CalendarSyncService()._to_google_event(
            _raw_event(start, {"dateTime": "2026-10-09T10:00:00+09:00"})
        )


class GooglePullDatetimeSnapshotTests(TemporaryDatabaseTestCase):
    def _add_original(self):
        return task_repo.create_unified_task(
            {
                "name": "Existing mirror",
                "type": "schedule",
                "deadline": "2026-10-09 09:00:00",
                "end_date": "2026-10-09 10:00:00",
                "gcal_event_id": "point-event",
                "gcal_source_calendar_id": "team",
                "gcal_target_calendar_id": "team",
                "calendar_id": "gcal::team",
                "gcal_sync_mode": "remote_mirror",
                "gcal_dirty": 0,
            }
        )

    def _pull(self, events, *, token="old-token", failure_status=None, failure_message=None):
        sync = SimpleNamespace(
            is_authenticated=True,
            calendar_id="team",
            time_zone="Asia/Seoul",
            authenticate=Mock(return_value=True),
            fetch_sync_events=Mock(return_value=(events, "next-token", False)),
            last_error_kind=None,
            last_error_status=None,
            last_error_message=None,
            create_event=Mock(side_effect=AssertionError("No outbound create expected")),
            update_event=Mock(side_effect=AssertionError("No outbound update expected")),
            batch_create_events=Mock(side_effect=AssertionError("No outbound batch expected")),
        )
        app = SimpleNamespace(
            settings=FakeSettings(
                {
                    "gcal_enabled": "true",
                    "gcal_calendar_id": "team",
                    "gcal_timezone": "Asia/Seoul",
                    "gcal_bound_calendar_id": "team",
                    "gcal_sync_token::team": token,
                }
            ),
            current_date=FakeDate("2026-10-09"),
            gcal_sync=sync,
            update_sync_status=Mock(),
            mark_panel_dirty=Mock(),
        )
        if failure_status:

            def fetch(token, calendar_id=None):
                sync.last_error_kind = "fetch" if calendar_id == "first" else None
                sync.last_error_status = failure_status if calendar_id == "first" else None
                sync.last_error_message = failure_message if calendar_id == "first" else None
                return (
                    (None, None, False) if calendar_id == "first" else (events, "next-token", False)
                )

            sync.fetch_sync_events.side_effect = fetch
        with (
            patch.object(engine, "_get_default_gcal_id", return_value="team"),
            patch.object(engine, "_refresh_resolved_primary_alias_id", return_value="primary"),
            patch.object(
                engine,
                "_active_sync_calendar_ids",
                return_value=["first", "team"] if failure_status else ["team"],
            ),
            patch.object(engine, "_should_refresh_calendar_list", return_value=False),
            patch.object(engine, "_should_run_incremental_backfill_probe", return_value=False),
            patch.object(engine, "_process_google_delete_queue", return_value=(0, 0)),
            patch.object(
                engine, "_push_local_changes_to_google", wraps=engine._push_local_changes_to_google
            ) as push,
            patch.object(engine, "auto_heal_google_orphans"),
        ):
            result = engine.sync_google_calendar(app, silent=True)
        return result, app, push

    def test_zero_duration_google_event_keeps_original_instant_without_outbound_write(self):
        original_id = self._add_original()
        raw = _raw_event(
            {"dateTime": "2026-10-09T09:00:00+09:00"}, {"dateTime": "2026-10-09T09:00:00+09:00"}
        )
        raw["endTimeUnspecified"] = False
        event = service.CalendarSyncService(calendar_id="team")._to_google_event(raw)
        success, app, push = self._pull([event])
        self.assertTrue(success)
        row = task_repo.get_unified_task(original_id)
        self.assertEqual(
            ("2026-10-09 09:00:00", "2026-10-09 09:00:00"), (row["deadline"], row["end_date"])
        )
        self.assertEqual(0, row["gcal_dirty"])
        self.assertEqual(0, app._last_gcal_sync_stats["pushed_count"])
        self.assertEqual("next-token", app.settings.value("gcal_sync_token::team"))
        self.assertEqual("success", app._last_gcal_sync_outcome)
        self.assertEqual([], task_repo.get_google_sync_tasks())
        push.assert_called_once()
        app.gcal_sync.create_event.assert_not_called()
        app.gcal_sync.update_event.assert_not_called()
        app.gcal_sync.batch_create_events.assert_not_called()

    def test_new_zero_duration_event_is_inserted_once_and_remains_clean_on_retry(self):
        event = service.CalendarSyncService(calendar_id="team")._to_google_event(
            _raw_event(
                {"dateTime": "2026-10-09T09:00:00+09:00"},
                {"dateTime": "2026-10-09T09:00:00+09:00"},
            )
        )
        conn = database_unified.db_manager.get_connection()
        for _ in range(2):
            success, app, _push = self._pull([event], token="")
            self.assertTrue(success)
            rows = list(conn.execute("SELECT * FROM unified_task"))
            self.assertEqual(1, len(rows))
            self.assertEqual(rows[0]["deadline"], rows[0]["end_date"])
            self.assertEqual(0, rows[0]["gcal_dirty"])
            self.assertEqual("gcal::team", rows[0]["calendar_id"])
            self.assertEqual("remote_mirror", rows[0]["gcal_sync_mode"])
            app.gcal_sync.create_event.assert_not_called()
            app.gcal_sync.update_event.assert_not_called()
            app.gcal_sync.batch_create_events.assert_not_called()

    def test_http_failure_is_retained_when_a_later_calendar_request_succeeds(self):
        original_id = self._add_original()
        valid = service.CalendarSyncService(calendar_id="team")._to_google_event(
            _raw_event(
                {"dateTime": "2026-10-09T09:00:00+09:00"},
                {"dateTime": "2026-10-09T10:00:00+09:00"},
            )
        )
        for status, message, expected in (
            (403, "forbidden", "remote_http_403"),
            (403, "userRateLimitExceeded", "remote_http_429"),
            (429, "limit", "remote_http_429"),
            (503, "unavailable", "remote_http_503"),
        ):
            with self.subTest(status=status, expected=expected):
                success, app, push = self._pull(
                    [valid], failure_status=status, failure_message=message
                )
                self.assertFalse(success)
                self.assertEqual(expected, app._last_gcal_sync_error)
                self.assertIsNone(app.gcal_sync.last_error_status)
                self.assertEqual(1, app._last_gcal_sync_stats["pull_fetch_failures"])
                self.assertEqual("Synthetic event", task_repo.get_unified_task(original_id)["name"])
                self.assertEqual("next-token", app.settings.value("gcal_sync_token::team"))
                self.assertEqual("failed", app._last_gcal_sync_outcome)
                push.assert_not_called()

    def test_subsecond_event_updates_existing_mirror_and_advances_token(self):
        original_id = self._add_original()
        event = service.CalendarSyncService(calendar_id="team")._to_google_event(
            _raw_event(
                {"dateTime": "2026-10-09T09:00:00.100000+09:00"},
                {"dateTime": "2026-10-09T09:00:00.900000+09:00"},
            )
        )
        success, app, push = self._pull([event])
        self.assertTrue(success)
        self.assertEqual("next-token", app.settings.value("gcal_sync_token::team"))
        row = task_repo.get_unified_task(original_id)
        self.assertEqual("Synthetic event", row["name"])
        self.assertEqual(
            ("2026-10-09 09:00:00", "2026-10-09 09:00:00"), (row["deadline"], row["end_date"])
        )
        self.assertEqual(0, row["gcal_dirty"])
        push.assert_called_once()

    def test_reversed_or_invalid_snapshot_preserves_all_rows_token_and_archive(self):
        original_id = self._add_original()
        before = task_repo.get_unified_task(original_id)
        valid = service.CalendarSyncService(calendar_id="team")._to_google_event(
            _raw_event(
                {"dateTime": "2026-10-09T09:00:00+09:00"},
                {"dateTime": "2026-10-09T10:00:00+09:00"},
            )
        )
        invalids = [
            ("2026-10-09T10:00:00+09:00", "2026-10-09T09:00:00+09:00"),
            ("2026-10-09T09:00:00.900000+09:00", "2026-10-09T09:00:00.100000+09:00"),
            ("2026-10-09", "2026-10-09"),
            ("2026-10-09", "2026-10-08"),
            ("2026-10-09", "2026-10-10T00:00:00+09:00"),
            ("2026-10-09T09:00:00+09:00", ""),
        ]
        for start, end in invalids:
            with self.subTest(start=start, end=end):
                invalid = SimpleNamespace(id="invalid", start_time=start, end_time=end)
                success, app, push = self._pull([valid, invalid], token="")
                self.assertFalse(success)
                self.assertEqual(before, task_repo.get_unified_task(original_id))
                self.assertEqual("", app.settings.value("gcal_sync_token::team"))
                self.assertEqual("google_pull_invalid_datetime", app._last_gcal_sync_error)
                push.assert_not_called()
        conn = database_unified.db_manager.get_connection()
        self.assertEqual(
            0, conn.execute("SELECT COUNT(*) FROM gcal_deleted_task_archive").fetchone()[0]
        )

    def test_cancelled_id_only_tombstone_remains_a_valid_incremental_delete(self):
        original_id = self._add_original()
        event = service.CalendarSyncService(calendar_id="team")._to_google_event(
            {"id": "point-event", "status": "cancelled"}
        )
        success, app, _push = self._pull([event])
        self.assertTrue(success)
        self.assertEqual("next-token", app.settings.value("gcal_sync_token::team"))
        self.assertIsNone(task_repo.get_unified_task(original_id))
