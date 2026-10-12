# -*- coding: utf-8 -*-
"""Calendar ownership and display policy regressions without UI or storage."""

from copy import deepcopy

import pytest

from calendar_app.domain.calendar_visibility import CalendarVisibility


def _calendar(identity, *, visible=True, kind="gcal", remote=None, active=True):
    row = {
        "id": identity,
        "type": kind,
        "is_visible": visible,
        "is_active": active,
    }
    if remote is not None:
        row["gcal_calendar_id"] = remote
    return row


@pytest.fixture
def calendars():
    return [
        _calendar("local::personal", kind="local"),
        _calendar("local::hidden", visible=False, kind="local"),
        _calendar("gcal::team@example.test", visible=False, remote="team@example.test"),
        _calendar("gcal::family@example.test", remote="family@example.test"),
        _calendar("ics::feed", kind="ics"),
    ]


@pytest.mark.parametrize("mode", ["remote_mirror", None])
def test_google_concrete_source_hides_stale_primary_alias(calendars, mode):
    alias = _calendar("gcal::primary", remote="primary")
    policy = CalendarVisibility([*calendars, alias])
    task = {
        "calendar_id": "gcal::primary",
        "gcal_source_calendar_id": "team@example.test",
        "gcal_sync_mode": mode,
    }

    assert policy.calendar_for_task(task) is calendars[2]
    assert policy.is_visible(task) is False


def test_google_concrete_source_overrides_hidden_stale_primary_alias(calendars):
    alias = _calendar("gcal::primary", visible=False, remote="primary")
    policy = CalendarVisibility([*calendars, alias])
    task = {
        "calendar_id": "gcal::primary",
        "gcal_source_calendar_id": "family@example.test",
        "gcal_sync_mode": "remote_mirror",
    }

    assert policy.calendar_for_task(task) is calendars[3]
    assert policy.is_visible(task) is True


def test_remote_mirror_concrete_source_overrides_stale_concrete_stored_calendar(calendars):
    policy = CalendarVisibility(calendars)
    task = {
        "calendar_id": "gcal::family@example.test",
        "gcal_source_calendar_id": "team@example.test",
        "gcal_sync_mode": "remote_mirror",
    }

    assert policy.calendar_for_task(task) is calendars[2]
    assert policy.is_visible(task) is False


@pytest.mark.parametrize("source", ["primary", "gcal::primary", "", None])
def test_concrete_target_wins_over_primary_source_alias(calendars, source):
    policy = CalendarVisibility(calendars, primary_gcal_id="family@example.test")
    task = {
        "calendar_id": "gcal::primary",
        "gcal_source_calendar_id": source,
        "gcal_target_calendar_id": "team@example.test",
        "gcal_sync_mode": "remote_mirror",
    }

    assert policy.calendar_for_task(task) is calendars[2]
    assert policy.is_visible(task) is False


@pytest.mark.parametrize("identity", ["primary", "gcal::primary"])
def test_primary_alias_resolves_to_concrete_calendar(calendars, identity):
    policy = CalendarVisibility(calendars, primary_gcal_id="team@example.test")
    task = {"calendar_id": identity, "gcal_sync_mode": "remote_mirror"}

    assert policy.calendar_for_task(task) is calendars[2]
    assert policy.is_visible(task) is False


def test_unresolved_primary_alias_uses_registered_alias():
    alias = _calendar("gcal::primary", visible=False, remote="primary")
    policy = CalendarVisibility([alias])

    assert policy.calendar_for_task({"calendar_id": "primary"}) is alias
    assert policy.is_visible({"calendar_id": "gcal::primary"}) is False


@pytest.mark.parametrize(
    "stored,visible", [("gcal::team@example.test", False), ("gcal::family@example.test", True)]
)
def test_local_owned_google_move_keeps_current_owner_until_source_is_updated(
    calendars, stored, visible
):
    policy = CalendarVisibility(calendars)
    old_source = "family@example.test" if not visible else "team@example.test"
    task = {
        "calendar_id": stored,
        "gcal_source_calendar_id": old_source,
        "gcal_sync_mode": "local_owned",
    }
    assert policy.calendar_for_task(task)["id"] == stored
    assert policy.is_visible(task) is visible


def test_local_owned_missing_google_owner_does_not_inherit_hidden_previous_source(calendars):
    task = {
        "calendar_id": "gcal::new-owner@example.test",
        "gcal_source_calendar_id": "team@example.test",
        "gcal_sync_mode": "local_owned",
    }
    policy = CalendarVisibility(calendars)
    assert policy.is_visible(task)
    assert not policy.is_visible(task, hide_gcal_items=True)


@pytest.mark.parametrize("identity", ["gcal::team@example.test", "team@example.test"])
def test_google_canonical_or_remote_id_maps_to_same_calendar(calendars, identity):
    policy = CalendarVisibility(calendars)

    assert policy.calendar_for_task({"calendar_id": identity}) is calendars[2]
    assert policy.is_visible({"calendar_id": identity}) is False


def test_google_row_without_remote_metadata_maps_by_canonical_id():
    calendar = _calendar("gcal::team@example.test", visible=False)
    policy = CalendarVisibility([calendar])

    assert policy.calendar_for_task({"gcal_source_calendar_id": "team@example.test"}) is calendar
    assert policy.is_visible({"gcal_source_calendar_id": "team@example.test"}) is False


def test_missing_google_source_falls_back_to_stored_calendar(calendars):
    policy = CalendarVisibility(calendars)
    task = {
        "calendar_id": "gcal::team@example.test",
        "gcal_source_calendar_id": "missing@example.test",
        "gcal_sync_mode": "remote_mirror",
    }

    assert policy.calendar_for_task(task) is calendars[2]
    assert policy.is_visible(task) is False


def test_subscription_google_identity_applies_hidden_calendar(calendars):
    policy = CalendarVisibility(calendars)
    task = {
        "is_subscription": True,
        "_subscription_calendar_id": "team@example.test",
    }

    assert policy.calendar_for_task(task) is calendars[2]
    assert policy.is_visible(task) is False


def test_ics_subscription_keeps_explicit_owner_with_stale_google_metadata(calendars):
    policy = CalendarVisibility(calendars)
    task = {
        "calendar_id": "ics::feed",
        "is_subscription": True,
        "gcal_source_calendar_id": "team@example.test",
        "gcal_target_calendar_id": "team@example.test",
    }

    assert policy.calendar_for_task(task) is calendars[4]
    assert policy.is_visible(task) is True


@pytest.mark.parametrize(
    "identity, expected", [("local::personal", True), ("local::hidden", False)]
)
def test_local_owned_task_visibility_uses_local_owner_not_google_destination(
    calendars, identity, expected
):
    policy = CalendarVisibility(calendars)
    task = {
        "calendar_id": identity,
        "gcal_sync_mode": "local_owned",
        "gcal_source_calendar_id": "team@example.test",
        "gcal_target_calendar_id": "team@example.test",
    }

    assert policy.calendar_for_task(task) is calendars[0 if expected else 1]
    assert policy.is_visible(task) is expected


def test_legacy_source_without_mode_overrides_misassigned_local_owner(calendars):
    policy = CalendarVisibility(calendars)
    task = {
        "calendar_id": "local::personal",
        "gcal_source_calendar_id": "team@example.test",
    }

    assert policy.calendar_for_task(task) is calendars[2]
    assert policy.is_visible(task) is False


@pytest.mark.parametrize("flag", [None, 1, True])
def test_null_or_visible_flag_keeps_calendar_visible(flag):
    calendar = _calendar("local::one", kind="local", visible=flag)
    policy = CalendarVisibility([calendar])

    assert policy.is_visible({"calendar_id": "local::one"}) is True


def test_missing_visible_flag_defaults_visible():
    policy = CalendarVisibility([{"id": "local::one", "type": "local"}])

    assert policy.is_visible({"calendar_id": "local::one"}) is True


@pytest.mark.parametrize("active", [0, False, None])
def test_paused_calendar_is_still_visible_when_display_enabled(active):
    calendar = _calendar("gcal::one", remote="one", active=active)
    policy = CalendarVisibility([calendar])

    assert policy.is_visible({"calendar_id": "gcal::one"}) is True


@pytest.mark.parametrize("task", [{}, {"calendar_id": None}, {"calendar_id": "deleted::unknown"}])
def test_unassigned_or_unknown_calendar_is_visible(task):
    policy = CalendarVisibility([])

    assert policy.calendar_for_task(task) is None
    assert policy.is_visible(task) is True


@pytest.mark.parametrize(
    "task",
    [
        {"calendar_id": "gcal::unknown"},
        {"calendar_id": "gcal::primary"},
        {"calendar_id": "primary"},
        {"gcal_source_calendar_id": "unknown@example.test"},
        {"gcal_target_calendar_id": "unknown@example.test", "gcal_sync_mode": "remote_mirror"},
        {"gcal_event_id": "unknown-event"},
        {"gcal_sync_mode": "remote_mirror"},
        {"is_subscription": True, "_subscription_calendar_id": "unknown@example.test"},
    ],
)
def test_hide_google_items_hides_legacy_google_identity_without_metadata(task):
    policy = CalendarVisibility([])

    assert policy.is_visible(task) is True
    assert policy.is_visible(task, hide_gcal_items=True) is False


def test_hide_google_items_preserves_local_owner_with_sync_target(calendars):
    policy = CalendarVisibility(calendars)
    task = {
        "calendar_id": "local::personal",
        "gcal_sync_mode": "local_owned",
        "gcal_target_calendar_id": "team@example.test",
    }

    assert policy.is_visible(task, hide_gcal_items=True) is True


def test_filter_preserves_order_and_references_without_mutating_input(calendars):
    policy = CalendarVisibility(calendars)
    tasks = [
        {"id": 1, "calendar_id": "local::personal"},
        {"id": 2, "calendar_id": "gcal::team@example.test"},
        {"id": 3, "calendar_id": "gcal::family@example.test"},
        {"id": 4, "calendar_id": "ics::feed"},
        {"id": 5, "calendar_id": None},
    ]
    before = deepcopy((calendars, tasks))

    visible = policy.filter_tasks(tasks)

    assert [task["id"] for task in visible] == [1, 3, 4, 5]
    expected_rows = [tasks[0], tasks[2], tasks[3], tasks[4]]
    assert all(actual is expected for actual, expected in zip(visible, expected_rows, strict=True))
    assert (calendars, tasks) == before
    assert policy.filter_tasks(tasks, hide_gcal_items=True) == [tasks[0], tasks[3], tasks[4]]
    assert policy.filter_tasks([]) == []
