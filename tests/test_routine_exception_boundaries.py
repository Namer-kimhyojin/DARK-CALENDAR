# -*- coding: utf-8 -*-
"""Corrupt recurrence rules and date limits must not crash previews or generation."""

from datetime import date, datetime

import pytest

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
