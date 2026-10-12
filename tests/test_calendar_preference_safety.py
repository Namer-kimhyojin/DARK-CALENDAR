# -*- coding: utf-8 -*-
"""Explicit ownership and import choices must survive stale metadata and DB errors."""

import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from calendar_app.infrastructure.db import calendar_repo
from calendar_app.infrastructure.google_sync import engine
from calendar_app.infrastructure.google_sync.common import resolve_task_target_calendar_id


class MemorySettings:
    def __init__(self, values):
        self.values = dict(values)

    def value(self, key, default=None, type=None):
        value = self.values.get(key, default)
        return type(value) if type is not None and value is not None else value

    def setValue(self, key, value):
        self.values[key] = value


@pytest.mark.parametrize("namespace", ["local", "ics", "shared"])
@pytest.mark.parametrize("field", ["gcal_source_calendar_id", "gcal_target_calendar_id"])
@pytest.mark.parametrize("event_id", [None, "", "   "])
def test_explicit_non_google_owner_without_link_ignores_stale_google_metadata(
    namespace, field, event_id
):
    task = {
        "calendar_id": namespace + "::default",
        "gcal_sync_mode": "local_owned",
        "gcal_event_id": event_id,
        field: "family",
    }
    before = dict(task)
    assert resolve_task_target_calendar_id(task, "team") is None
    assert resolve_task_target_calendar_id(task) is None
    assert task == before


@pytest.mark.parametrize("field", ["gcal_source_calendar_id", "gcal_target_calendar_id"])
def test_legacy_local_owned_linked_google_event_keeps_its_existing_route(field):
    task = {
        "calendar_id": "local::legacy",
        "gcal_sync_mode": "local_owned",
        "gcal_event_id": "already-linked",
        field: "family",
    }
    assert resolve_task_target_calendar_id(task, "team") == "family"


@pytest.mark.parametrize("configured", [True, "true", "1"])
def test_explicit_selection_database_failure_never_reimports_legacy_subscriptions(
    configured, monkeypatch
):
    failure = sqlite3.DatabaseError("fixture_calendar_read_failed")
    current = Mock(side_effect=failure)
    legacy = Mock(return_value=[{"calendar_id": "unchecked", "is_active": 1}])
    monkeypatch.setattr(calendar_repo, "list_calendars", current)
    monkeypatch.setattr(engine.task_repo, "list_gcal_subscriptions", legacy)
    app = SimpleNamespace(settings=MemorySettings({"gcal_import_selection_configured": configured}))
    with pytest.raises(sqlite3.DatabaseError, match="fixture_calendar_read_failed"):
        engine._active_sync_calendar_ids(app, "unchecked")
    legacy.assert_not_called()


@pytest.mark.parametrize("configured", [False, "false", "0"])
def test_legacy_selection_retains_subscription_fallback_before_explicit_save(
    configured, monkeypatch
):
    monkeypatch.setattr(
        calendar_repo, "list_calendars", Mock(side_effect=sqlite3.DatabaseError("fixture"))
    )
    legacy = Mock(return_value=[{"calendar_id": "family", "is_active": 1}])
    monkeypatch.setattr(engine.task_repo, "list_gcal_subscriptions", legacy)
    app = SimpleNamespace(settings=MemorySettings({"gcal_import_selection_configured": configured}))
    assert engine._active_sync_calendar_ids(app, "primary") == ["primary", "family"]
    legacy.assert_called_once()


@pytest.mark.parametrize("bound", ["primary", "family", "unchecked"])
def test_explicit_empty_selection_does_not_insert_the_service_fallback(bound, monkeypatch):
    monkeypatch.setattr(calendar_repo, "list_calendars", Mock(return_value=[]))
    legacy = Mock(return_value=[{"calendar_id": "unchecked", "is_active": 1}])
    monkeypatch.setattr(engine.task_repo, "list_gcal_subscriptions", legacy)
    app = SimpleNamespace(settings=MemorySettings({"gcal_import_selection_configured": True}))
    assert engine._active_sync_calendar_ids(app, bound) == []
    legacy.assert_not_called()


def test_sync_reports_explicit_selection_read_failure_without_pull_or_push(monkeypatch):
    settings = MemorySettings(
        {
            "gcal_import_selection_configured": True,
            "gcal_enabled": True,
            "gcal_calendar_id": "family",
            "gcal_bound_calendar_id": "family",
        }
    )
    service = SimpleNamespace(
        is_authenticated=True,
        authenticate=Mock(return_value=True),
        list_accessible_calendars=Mock(return_value=[]),
        fetch_sync_events=Mock(),
        last_error_kind=None,
        last_error_message=None,
    )
    app = SimpleNamespace(settings=settings, gcal_sync=service, update_sync_status=Mock())
    monkeypatch.setattr(engine, "_get_default_gcal_id", lambda _: "family")
    monkeypatch.setattr(engine, "_calendar_source_summary_map", lambda: {})
    monkeypatch.setattr(engine, "_should_refresh_calendar_list", lambda _: False)
    monkeypatch.setattr(engine, "_process_google_delete_queue", lambda _: (0, 0))
    monkeypatch.setattr(engine.gcal_db_adapter, "cleanup_duplicate_gcal_rows", lambda: 0)
    monkeypatch.setattr(engine.gcal_db_adapter, "get_all_gcal_tasks_map", lambda: {})
    monkeypatch.setattr(
        calendar_repo,
        "list_calendars",
        Mock(side_effect=sqlite3.DatabaseError("fixture_calendar_read_failed")),
    )
    legacy = Mock()
    push = Mock()
    monkeypatch.setattr(engine.task_repo, "list_gcal_subscriptions", legacy)
    monkeypatch.setattr(engine, "_push_local_changes_to_google", push)
    assert not engine.sync_google_calendar(app, silent=True)
    assert app._last_gcal_sync_outcome == engine.SYNC_OUTCOME_FAILED
    assert app._last_gcal_sync_error == "database_failed"
    assert not app._gcal_sync_in_progress
    service.fetch_sync_events.assert_not_called()
    legacy.assert_not_called()
    push.assert_not_called()
