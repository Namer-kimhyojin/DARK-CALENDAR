# -*- coding: utf-8 -*-
"""Behavior checks for weekly interval display and guarded schedule persistence."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math

import pytest

from calendar_app.application.week_planner_usecases import (
    build_week_schedule_updates,
    normalized_task_interval,
    reschedule_task_and_get_sync_payload,
    scheduling_block_reason,
    split_task_into_day_segments,
)
from calendar_app.infrastructure.db import task_repo
from tests.support import TemporaryDatabaseTestCase


def _task(**overrides):
    return {
        "id": 7,
        "name": "Weekly planning",
        "type": "schedule",
        "calendar_id": "local::Work",
        "target_date": "2026-10-05",
        "deadline": "2026-10-05 09:00:00",
        "end_date": "2026-10-05 10:00:00",
        "all_day": 0,
        **overrides,
    }


class _Repo:
    def __init__(self, row, *, succeeds=True):
        self.row = deepcopy(row)
        self.succeeds = succeeds
        self.update_calls = []
        self.read_calls = []

    def get_unified_task(self, task_id):
        self.read_calls.append(task_id)
        if not self.row or self.row.get("id") != task_id:
            return None
        return deepcopy(self.row)

    def update_unified_task(self, task_id, updates):
        self.update_calls.append((task_id, dict(updates)))
        if not self.succeeds:
            return False
        self.row.update(updates)
        self.row["gcal_dirty"] = 1
        self.row["updated_at"] = "fresh persistence timestamp"
        return True


def _reschedule(repo, *, permission=lambda _calendar_id: False, **kwargs):
    return reschedule_task_and_get_sync_payload(
        repo,
        7,
        "2026-10-07",
        13 * 60 + 15,
        kwargs.pop("duration_minutes", 60),
        is_calendar_read_only=permission,
        **kwargs,
    )


def test_offset_aware_api_values_convert_to_same_local_wall_interval():
    seoul = timezone(timedelta(hours=9))
    interval = normalized_task_interval(
        _task(deadline="2026-10-05T00:05:30Z", end_date="2026-10-05T01:25:45+00:00"),
        local_timezone=seoul,
    )
    assert interval == (datetime(2026, 10, 5, 9, 5, 30), datetime(2026, 10, 5, 10, 25, 45))


def test_subscription_raw_api_values_override_display_dates_and_shift_local_day():
    interval = normalized_task_interval(
        _task(
            deadline="2026-10-04",
            end_date="2026-10-04",
            _start_raw="2026-10-04T23:05:30Z",
            _end_raw="2026-10-05T00:25:45+00:00",
        ),
        local_timezone=timezone(timedelta(hours=9)),
    )
    assert interval == (datetime(2026, 10, 5, 8, 5, 30), datetime(2026, 10, 5, 9, 25, 45))


@pytest.mark.parametrize("all_day", [1, True, "true", "1"])
def test_all_day_flag_keeps_midnight_tasks_out_of_timed_grid(all_day):
    assert normalized_task_interval(_task(all_day=all_day, deadline="2026-10-05 00:00:00")) is None


@pytest.mark.parametrize("all_day", [0, False, "0", "false", None])
def test_explicit_midnight_is_timed_when_all_day_flag_is_false(all_day):
    interval = normalized_task_interval(
        _task(all_day=all_day, deadline="2026-10-05 00:00:00", end_date="2026-10-05 00:20:00")
    )
    assert interval == (datetime(2026, 10, 5), datetime(2026, 10, 5, 0, 20))


@pytest.mark.parametrize("start", ["2026-10-05", "bad start", None])
def test_date_only_or_invalid_start_has_no_timed_interval(start):
    assert normalized_task_interval(_task(deadline=start)) is None


@pytest.mark.parametrize("end", [None, "bad end", "2026-10-05 08:00:00"])
def test_legacy_missing_or_invalid_end_has_a_small_display_block(end):
    assert normalized_task_interval(_task(end_date=end)) == (
        datetime(2026, 10, 5, 9),
        datetime(2026, 10, 5, 9, 15),
    )


def test_cross_midnight_interval_splits_without_a_phantom_midnight_day():
    row = _task(deadline="2026-10-05 23:30:00", end_date="2026-10-07 00:00:00")
    segments = split_task_into_day_segments(row, "2026-10-05")
    assert [(s["date"], s["start_minutes"], s["end_minutes"]) for s in segments] == [
        ("2026-10-05", 1410, 1440),
        ("2026-10-06", 0, 1440),
    ]
    assert [s["offset_minutes"] for s in segments] == [0, 30]
    assert [s["continues_before"] for s in segments] == [False, True]
    assert [s["continues_after"] for s in segments] == [True, False]
    assert all(s["duration_minutes"] == 1470 for s in segments)


def test_long_interval_clips_at_both_week_edges_and_retains_original_offset():
    segments = split_task_into_day_segments(
        _task(deadline="2026-10-04 23:00:00", end_date="2026-10-13 01:00:00"), "2026-10-05"
    )
    assert len(segments) == 7
    assert segments[0]["offset_minutes"] == 60
    assert all(s["continues_before"] and s["continues_after"] for s in segments)


def test_all_day_to_timed_updates_calendar_target_and_flag_in_one_payload():
    row = _task(all_day=1, end_date="2026-10-08")
    original = deepcopy(row)
    updates = build_week_schedule_updates(row, "2026-10-07", 14 * 60 + 15, 20)
    assert updates == {
        "deadline": "2026-10-07 14:15:00",
        "end_date": "2026-10-07 14:35:00",
        "target_date": "2026-10-07",
        "all_day": 0,
        "calendar_id": "local::Work",
    }
    assert row == original


def test_multi_day_duration_is_saved_without_truncation():
    updates = build_week_schedule_updates(_task(), "2026-10-07", 23 * 60 + 45, 1500)
    assert updates["end_date"] == "2026-10-09 00:45:00"


@pytest.mark.parametrize(
    ("date_str", "start", "duration"),
    [
        ("2026-02-30", 540, 15),
        ("2026-10-07T00:00", 540, 15),
        ("20261007", 540, 15),
        ("2026-10-07", -1, 15),
        ("2026-10-07", 1440, 15),
        ("2026-10-07", math.nan, 15),
        ("2026-10-07", 540, 0),
        ("2026-10-07", 540, 14),
        ("2026-10-07", 540, math.inf),
        ("9999-12-31", 1430, 30),
    ],
)
def test_invalid_schedule_coordinates_are_rejected(date_str, start, duration):
    with pytest.raises(ValueError):
        build_week_schedule_updates(_task(), date_str, start, duration)


@pytest.mark.parametrize(
    "restrictions",
    [
        {"read_only": True},
        {"is_subscription": True},
        {"calendar_id": "ics::source"},
    ],
)
def test_read_only_rows_are_blocked_before_any_update(restrictions):
    row = _task(**restrictions)
    repo = _Repo(row)
    assert scheduling_block_reason(row) == "read_only"
    assert _reschedule(repo) is None
    assert repo.update_calls == []


@pytest.mark.parametrize(
    "recurring",
    [
        {"recurrence": "mode=weekly;weekdays=0,2"},
        {"gcal_recurring_series_id": "google series"},
        {"gcal_instance_original_start": "2026-10-05T00:00:00Z"},
        {"gcal_recurrence_rule": "RRULE:FREQ=WEEKLY"},
        {"cycle_type": "monthly"},
        {"series_id": "local repeat series"},
    ],
)
def test_repeated_rows_do_not_silently_modify_a_series_occurrence(recurring):
    row = _task(**recurring)
    repo = _Repo(row)
    assert scheduling_block_reason(row) == "recurring"
    assert _reschedule(repo) is None
    assert repo.update_calls == []


def test_explicit_single_recurrence_is_editable():
    assert scheduling_block_reason(_task(recurrence="mode=single", cycle_type="single")) is None
    assert scheduling_block_reason(_task(read_only="false")) is None


def test_save_rechecks_current_calendar_permission_and_leaves_row_intact_on_denial():
    repo = _Repo(_task(calendar_id="gcal::current-calendar"))
    before = deepcopy(repo.row)
    checked = []

    def denied(calendar_id):
        checked.append(calendar_id)
        return True

    assert _reschedule(repo, permission=denied) is None
    assert checked == ["gcal::current-calendar"]
    assert repo.row == before
    assert repo.update_calls == []


def test_legacy_google_row_without_calendar_id_checks_its_original_calendar():
    repo = _Repo(_task(calendar_id=None, gcal_source_calendar_id="remote calendar"))
    checked = []
    assert _reschedule(repo, permission=lambda cal_id: checked.append(cal_id) or True) is None
    assert checked == ["gcal::remote calendar"]
    assert repo.update_calls == []


def test_save_performs_one_complete_update_and_returns_fresh_sync_payload():
    repo = _Repo(_task(all_day=1))
    payload = _reschedule(repo, duration_minutes=15)
    assert len(repo.update_calls) == 1
    assert repo.update_calls[0][1]["all_day"] == 0
    assert repo.read_calls == [7, 7]
    assert payload["gcal_dirty"] == 1
    assert payload["updated_at"] == "fresh persistence timestamp"
    assert payload["calendar_id"] == "local::Work"
    assert payload["target_date"] == "2026-10-07"


def test_move_retains_exact_short_existing_duration_including_seconds():
    repo = _Repo(_task(end_date="2026-10-05 09:05:30"))
    payload = _reschedule(repo, duration_minutes=6, preserve_duration=True)
    assert payload["deadline"] == "2026-10-07 13:15:00"
    assert payload["end_date"] == "2026-10-07 13:20:30"


def test_move_retains_original_multi_day_span():
    repo = _Repo(_task(end_date="2026-10-07 10:00:00"))
    payload = _reschedule(repo, duration_minutes=2940, preserve_duration=True)
    assert payload["end_date"] == "2026-10-09 14:15:00"


def test_stale_move_duration_is_rejected_before_update():
    repo = _Repo(_task(end_date="2026-10-05 09:20:00"))
    assert _reschedule(repo, duration_minutes=60, preserve_duration=True) is None
    assert repo.update_calls == []


def test_short_resize_is_rejected_and_failed_or_missing_rows_return_no_sync_payload():
    repo = _Repo(_task())
    with pytest.raises(ValueError):
        _reschedule(repo, duration_minutes=5)
    assert repo.update_calls == []
    failed = _Repo(_task(), succeeds=False)
    before = deepcopy(failed.row)
    assert _reschedule(failed) is None
    assert len(failed.update_calls) == 1
    assert failed.row == before
    missing = _Repo(None)
    assert _reschedule(missing) is None
    assert missing.update_calls == []


def test_unchanged_schedule_does_not_dirty_row_or_enqueue_sync():
    repo = _Repo(_task())
    assert (
        reschedule_task_and_get_sync_payload(
            repo, 7, "2026-10-05", 540, 60, is_calendar_read_only=lambda _cal_id: False
        )
        is None
    )
    assert repo.update_calls == []


class WeeklyScheduleRepositoryTests(TemporaryDatabaseTestCase):
    def test_real_repository_persists_short_move_and_sync_fields_together(self):
        source = _task(end_date="2026-10-05 09:05:30")
        source.pop("id")
        task_id = task_repo.create_unified_task(source)
        self.assertIsNotNone(task_id)
        result = reschedule_task_and_get_sync_payload(
            task_repo,
            task_id,
            "2026-10-07",
            13 * 60 + 15,
            6,
            is_calendar_read_only=lambda _cal_id: False,
            preserve_duration=True,
        )
        self.assertEqual(result["deadline"], "2026-10-07 13:15:00")
        self.assertEqual(result["end_date"], "2026-10-07 13:20:30")
        self.assertEqual(result["target_date"], "2026-10-07")
        self.assertEqual(result["calendar_id"], "local::Work")
        self.assertEqual(result["all_day"], 0)
        self.assertEqual(result["gcal_dirty"], 1)
        self.assertEqual(task_repo.get_unified_task(task_id), result)
