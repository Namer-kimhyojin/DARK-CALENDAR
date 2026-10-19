# -*- coding: utf-8 -*-
"""Corrupt recurrence rules and date limits must not crash previews or generation."""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from calendar_app.application.routine_batch_generator import RoutineBatchGenerator
from calendar_app.domain.policies import routine_policy


@pytest.mark.parametrize(
    "cycle", ["daily", "weekly", "monthly", "quarterly", "half_yearly", "yearly"]
)
def test_last_representable_day_has_no_next_occurrence(cycle):
    assert routine_policy.get_next_occurrence("9999-12-31", cycle, {}) is None


@pytest.mark.parametrize(
    "cycle,rule",
    [
        ("weekly", {"weekday": "bad"}),
        ("weekly", {"weekday": 7}),
        ("weekly", {"weekday": -1}),
        ("monthly", {"day": 0}),
        ("monthly", {"day": 32}),
        ("monthly", {"day": float("inf")}),
        ("monthly", {"mode": "nth_weekday", "weekday": 8}),
        ("monthly", {"mode": "nth_weekday", "nth": 0}),
        ("monthly", {"mode": "nth_weekday", "nth": -10}),
        ("quarterly", {"slot": 4}),
        ("yearly", {"slot": -1}),
        ("yearly", {"slot": 13}),
        ("monthly", []),
    ],
)
def test_malformed_rule_does_not_raise_or_schedule_on_an_unintended_day(cycle, rule):
    assert routine_policy.get_next_occurrence("2026-10-15", cycle, rule) is None


@pytest.mark.parametrize("current", [None, [], {}, "bad", "2026-10-15junk"])
def test_invalid_date_is_not_used_for_recurrence(current):
    assert routine_policy.get_next_occurrence(current, "daily", {}) is None


@pytest.mark.parametrize("current", ["2026-10-15", date(2026, 10, 15), datetime(2026, 10, 15)])
def test_valid_daily_inputs_still_advance_one_day(current):
    assert routine_policy.get_next_occurrence(current, "daily", {}) == "2026-10-16"


def generator():
    repo = SimpleNamespace(
        get_routine_template=Mock(return_value={"name": "Daily", "cycle_type": "daily"}),
        get_routines_by_period=Mock(return_value=[]),
        create_unified_task=Mock(side_effect=range(1, 100)),
    )
    return RoutineBatchGenerator(repo), repo


def test_daily_batch_does_not_skip_every_other_day():
    service, repo = generator()
    assert service.generate_future_instances(1, "2026-10-01", "2026-10-04") == [1, 2, 3]
    assert [call.args[0]["target_date"] for call in repo.create_unified_task.call_args_list] == [
        "2026-10-02",
        "2026-10-03",
        "2026-10-04",
    ]


def test_batch_ending_on_date_limit_keeps_last_created_result():
    service, repo = generator()
    assert service.generate_future_instances(1, "9999-12-30", "9999-12-31") == [1]
    assert repo.create_unified_task.call_count == 1


def test_existing_daily_instance_does_not_skip_the_following_day():
    service, repo = generator()
    repo.get_routines_by_period.side_effect = [
        [{"template_id": 1, "target_date": "2026-10-02"}],
        [],
        [],
    ]
    assert service.generate_future_instances(1, "2026-10-01", "2026-10-04") == [1, 2]
    assert [call.args[0]["target_date"] for call in repo.create_unified_task.call_args_list] == [
        "2026-10-03",
        "2026-10-04",
    ]
