# -*- coding: utf-8 -*-
"""An explicit Google move must retain its destination through retries."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from calendar_app.infrastructure.google_sync import helpers


@pytest.fixture
def pending_move(monkeypatch):
    task = {
        "id": 1,
        "type": "schedule",
        "name": "Moving event",
        "deadline": "2026-10-07 09:00:00",
        "calendar_id": "gcal::team",
        "gcal_event_id": "original-event",
        "gcal_source_calendar_id": "family",
        "gcal_target_calendar_id": "team",
        "gcal_sync_mode": "local_owned",
        "gcal_remote_updated_at": "2026-10-06T00:00:00Z",
        "gcal_last_synced_at": "2026-10-06T00:01:00Z",
    }
    sync = SimpleNamespace(
        is_authenticated=True,
        calendar_id="team",
        last_error_kind=None,
        last_error_message=None,
        move_event=Mock(return_value=True),
        update_event=Mock(return_value=True),
        create_event=Mock(return_value="duplicate"),
        list_accessible_calendars=Mock(return_value=[{"id": "family"}, {"id": "team"}]),
    )
    app = SimpleNamespace(
        settings={"gcal_enabled": True, "gcal_calendar_id": "family"}, gcal_sync=sync
    )
    monkeypatch.setattr(
        "calendar_app.infrastructure.db.task_repo.get_unified_task", lambda task_id: dict(task)
    )
    mark = Mock(return_value=True)
    monkeypatch.setattr(helpers, "_mark_task_synced", mark)
    return task, sync, app, mark


@pytest.mark.parametrize("error", ["network", "move", "auth_required", "permission"])
def test_failed_move_does_not_update_the_old_calendar_or_create_a_duplicate(pending_move, error):
    task, sync, app, mark = pending_move
    original = dict(task)
    sync.move_event.return_value = False
    sync.last_error_kind = error
    result = helpers.sync_task_to_google(app, task)
    assert not result.success and result.error_kind == error
    assert result.event_id == "original-event"
    assert task == original
    sync.update_event.assert_not_called()
    sync.create_event.assert_not_called()
    sync.list_accessible_calendars.assert_not_called()
    mark.assert_not_called()


def test_move_exception_preserves_pending_destination(pending_move):
    task, sync, app, mark = pending_move
    sync.move_event.side_effect = RuntimeError("Transient move error")
    result = helpers.sync_task_to_google(app, task)
    assert not result.success and result.error_kind == "calendar_move"
    sync.update_event.assert_not_called()
    sync.create_event.assert_not_called()
    mark.assert_not_called()


def test_missing_source_retry_checks_only_the_intended_destination(pending_move):
    task, sync, app, mark = pending_move
    sync.move_event.return_value = False
    sync.last_error_kind = "not_found"
    result = helpers.sync_task_to_google(app, task)
    assert result.success and result.event_id == "original-event"
    assert sync.update_event.call_count == 1
    assert sync.update_event.call_args.kwargs["calendar_id"] == "team"
    assert mark.call_args.kwargs["source_calendar_id"] == "team"
    assert mark.call_args.kwargs["target_calendar_id"] == "team"
    sync.create_event.assert_not_called()


def test_event_missing_from_source_and_destination_remains_pending(pending_move):
    task, sync, app, mark = pending_move
    sync.move_event.return_value = False
    sync.update_event.return_value = False
    sync.last_error_kind = "not_found"
    result = helpers.sync_task_to_google(app, task)
    assert not result.success and result.error_kind == "calendar_move_unconfirmed"
    assert sync.update_event.call_count == 1
    sync.list_accessible_calendars.assert_not_called()
    sync.create_event.assert_not_called()
    mark.assert_not_called()


def test_successful_move_with_missing_destination_does_not_auto_create(pending_move):
    task, sync, app, mark = pending_move
    sync.update_event.return_value = False
    sync.last_error_kind = "not_found"
    result = helpers.sync_task_to_google(app, task)
    assert not result.success and result.error_kind == "calendar_move_unconfirmed"
    sync.create_event.assert_not_called()
    sync.list_accessible_calendars.assert_not_called()
    mark.assert_not_called()


def test_move_target_conflict_remains_an_error(pending_move):
    task, sync, app, mark = pending_move
    sync.update_event.return_value = False
    sync.last_error_kind = "conflict"
    result = helpers.sync_task_to_google(app, task)
    assert not result.success and result.error_kind == "conflict"
    sync.create_event.assert_not_called()
    mark.assert_not_called()


def test_successful_move_marks_only_the_new_target(pending_move):
    task, sync, app, mark = pending_move
    result = helpers.sync_task_to_google(app, task)
    assert result.success
    sync.move_event.assert_called_once_with(
        "original-event",
        "family",
        "team",
        expected_remote_updated_at="2026-10-06T00:00:00Z",
        result_metadata={},
    )
    assert sync.update_event.call_args.kwargs["calendar_id"] == "team"
    assert mark.call_args.kwargs["source_calendar_id"] == "team"
    assert mark.call_args.kwargs["target_calendar_id"] == "team"


def test_successful_remote_move_with_failed_local_mark_stays_pending(pending_move):
    task, sync, app, mark = pending_move
    mark.return_value = False
    result = helpers.sync_task_to_google(app, task)
    assert not result.success and result.error_kind == "calendar_move_local_state"
    assert result.event_id == "original-event"
    assert task["gcal_source_calendar_id"] == "family"
    assert task["gcal_target_calendar_id"] == "team"
    sync.create_event.assert_not_called()


def test_default_change_alone_does_not_move_an_existing_event(pending_move):
    task, sync, app, mark = pending_move
    task.update(calendar_id="gcal::family", gcal_target_calendar_id="family")
    result = helpers.sync_task_to_google(app, task)
    assert result.success
    sync.move_event.assert_not_called()
    assert sync.update_event.call_args.kwargs["calendar_id"] == "family"
    assert mark.call_args.kwargs["target_calendar_id"] == "family"


@pytest.mark.parametrize("namespace", ["local", "shared", "ics", "outlook", "caldav"])
def test_new_non_google_owner_ignores_stale_google_target(pending_move, namespace):
    task, sync, app, mark = pending_move
    task.update(calendar_id=namespace + "::current", gcal_event_id=None)
    result = helpers.sync_task_to_google(app, task)
    assert result.success and result.error_kind == "skipped_non_gcal"
    sync.move_event.assert_not_called()
    sync.update_event.assert_not_called()
    sync.create_event.assert_not_called()


def test_legacy_linked_local_row_keeps_its_explicit_google_route(pending_move):
    task, sync, app, mark = pending_move
    task.update(
        calendar_id="local::legacy",
        gcal_source_calendar_id="family",
        gcal_target_calendar_id="family",
    )
    result = helpers.sync_task_to_google(app, task)
    assert result.success
    sync.move_event.assert_not_called()
    assert sync.update_event.call_args.kwargs["calendar_id"] == "family"
