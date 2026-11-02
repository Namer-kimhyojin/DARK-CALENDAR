# -*- coding: utf-8 -*-
"""Workspace validation, arrangement and scheduling contracts without a Qt runtime."""

from copy import deepcopy
from datetime import datetime
import json

import pytest

from calendar_app.domain.widget_workspace import (
    arrange_rectangles,
    calendar_matches,
    calendar_scope,
    default_state,
    load_state,
    matching_rule,
    validate_snapshot,
    validate_state,
)


def sample_snapshot():
    return {
        "widgets": [
            {
                "id": "clock_0",
                "name": "Clock",
                "type": "clock",
                "enabled": True,
                "rect": [-800, 40, 300, 180],
                "style": {"font_size": 32},
            }
        ],
        "mode": {},
    }


def profile_state():
    result = default_state()
    result["profiles"] = [{"id": "work", "name": "Work", "snapshot": sample_snapshot()}]
    return result


def test_workspace_roundtrip_excludes_content_credentials_and_catalogs():
    state = profile_state()
    snapshot = state["profiles"][0]["snapshot"]
    snapshot["widgets"][0]["style"].update(
        access_token="secret", weather_template="private", cd_target_iso="live"
    )
    snapshot["mode"].update(
        widget_mode_resume=True,
        widget_mode_user_layout_presets="keep original catalog",
        widget_mode_skin="studio_porcelain",
        google_token="secret",
    )
    result = load_state(json.dumps(state))
    restored = result["profiles"][0]["snapshot"]
    assert restored["widgets"][0]["rect"][0] == -800
    assert restored["widgets"][0]["style"] == {"font_size": 32}
    assert restored["mode"] == {"widget_mode_skin": "studio_porcelain"}


@pytest.mark.parametrize(
    "raw",
    ["[]", "{", '{"version":2}', "x" * 5_000_001],
    ids=["array", "broken", "version", "oversized"],
)
def test_invalid_state_is_rejected_instead_of_silently_replacing_user_settings(raw):
    with pytest.raises(ValueError):
        load_state(raw)


@pytest.mark.parametrize(
    "rect", [[0, 0, 0, 300], [0, 0, 9000, 40], [0, 0, float("nan"), 20], [True, 0, 100, 20], [0, 0]]
)
def test_invalid_rectangles_cannot_reach_native_window_operations(rect):
    raw = sample_snapshot()
    raw["widgets"][0]["rect"] = rect
    with pytest.raises(ValueError):
        validate_snapshot(raw)


def test_duplicate_ids_and_multiple_stack_memberships_are_rejected():
    raw = sample_snapshot()
    raw["widgets"].append(deepcopy(raw["widgets"][0]))
    with pytest.raises(ValueError):
        validate_snapshot(raw)
    state = profile_state()
    state["stacks"] = [
        {"id": "a", "members": ["clock_0", "text_0"]},
        {"id": "b", "members": ["text_0", "dday_0"]},
    ]
    with pytest.raises(ValueError):
        validate_state(state)


@pytest.mark.parametrize(
    "time,expected",
    [
        ("2026-11-02T08:59", None),
        ("2026-11-02T09:00", (0, "work")),
        ("2026-11-02T17:59", (0, "work")),
        ("2026-11-02T18:00", None),
        ("2026-11-07T10:00", None),
    ],
)
def test_weekday_rules_use_inclusive_start_exclusive_end(time, expected):
    rules = [{"profile": "work", "days": [1, 2, 3, 4, 5], "start": "09:00", "end": "18:00"}]
    assert matching_rule(rules, datetime.fromisoformat(time)) == expected


@pytest.mark.parametrize(
    "time,expected",
    [
        ("2026-11-02T23:30", (0, "night")),
        ("2026-11-03T01:59", (0, "night")),
        ("2026-11-03T02:00", None),
        ("2026-11-03T23:30", None),
    ],
)
def test_overnight_rule_belongs_to_starting_day(time, expected):
    rules = [{"profile": "night", "days": [1], "start": "22:00", "end": "02:00"}]
    assert matching_rule(rules, datetime.fromisoformat(time)) == expected


def test_rule_precedence_disabled_and_full_day_semantics():
    rules = [
        {"profile": "disabled", "days": [1], "start": "00:00", "end": "00:00", "enabled": False},
        {"profile": "first", "days": [1], "start": "09:00", "end": "09:00"},
        {"profile": "later", "days": [1], "start": "09:00", "end": "18:00"},
    ]
    assert matching_rule(rules, datetime(2026, 11, 2, 0, 0)) == (1, "first")
    assert matching_rule(rules, datetime(2026, 11, 2, 10, 0)) == (1, "first")


def test_align_and_distribute_keep_sizes_input_and_outer_edges():
    raw = {"a": [10, 20, 100, 50], "b": [250, 30, 80, 60], "c": [500, 80, 150, 70]}
    original = deepcopy(raw)
    aligned = arrange_rectangles(raw, "left")
    assert {r[0] for r in aligned.values()} == {10}
    assert [r[2:] for r in aligned.values()] == [r[2:] for r in raw.values()]
    spaced = arrange_rectangles(raw, "horizontal")
    assert spaced["a"][0] == 10 and spaced["c"][0] + spaced["c"][2] == 650
    assert abs((spaced["b"][0] - 110) - (500 - spaced["b"][0] - 80)) <= 1
    assert raw == original


def test_calendar_scope_distinguishes_all_from_explicit_empty():
    assert calendar_scope("") is None and calendar_scope("null") is None
    assert calendar_scope("[]") == set()
    assert calendar_matches({"calendar_id": 3}, calendar_scope("[3]"))
    assert not calendar_matches({"calendar_id": 4}, calendar_scope("[3]"))
    assert calendar_matches({}, {"local"}) and not calendar_matches({}, set())


@pytest.mark.parametrize(
    "field,value",
    [
        ("rules", [{"profile": "deleted", "days": [1], "start": "09:00", "end": "18:00"}]),
        ("profiles", [{"id": "x", "name": " ", "snapshot": sample_snapshot()}]),
        ("options", {"motion": "invalid"}),
    ],
)
def test_invalid_references_names_and_policies_are_rejected(field, value):
    state = profile_state()
    state[field] = value
    with pytest.raises(ValueError):
        validate_state(state)


def test_state_saved_by_writer_fits_the_readers_storage_budget():
    state = profile_state()
    large = sample_snapshot()
    large["mode"]["widget_mode_free_layout"] = "x" * 1_000_000
    state["profiles"] = [
        {"id": str(index), "name": str(index), "snapshot": deepcopy(large)} for index in range(6)
    ]
    with pytest.raises(ValueError, match="storage budget"):
        validate_state(state)
