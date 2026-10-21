# -*- coding: utf-8 -*-
"""Isolate calendar failures while preserving account-level recovery and queues."""

import sqlite3

import pytest

from calendar_app.application.calendar_sync_contract import CalendarSyncError, RemoteCalendarError
from calendar_app.infrastructure.calendar_sync.engine import CalendarSyncEngine
from tests.test_calendar_sync_engine import repo, setup, task


@pytest.mark.parametrize(
    "error",
    [
        CalendarSyncError("invalid_event_time"),
        CalendarSyncError("duplicate_remote_event"),
        RemoteCalendarError(403),
        RemoteCalendarError(404),
    ],
)
def test_bad_calendar_does_not_starve_healthy_calendar(repo, error):
    provider, broken, engine = setup(repo)
    healthy = repo.register("account", {"id": "healthy", "name": "Healthy", "can_edit": True})
    with repo.conn:
        repo.import_task(broken, task("Unsent local"))
    calls = []

    def events(calendar, *_):
        calls.append(calendar)
        if calendar == "calendar":
            raise error
        return [{"id": "healthy-event", "etag": "1", "task": task("Healthy event")}]

    provider.events = events
    result = engine.run()
    assert calls == ["calendar", "healthy"]
    assert result["calendar_errors"] == {broken: str(error)}
    assert result["issues"] == 1
    assert result["imported"] == 1
    assert repo.tasks(healthy)[0]["name"] == "Healthy event"
    assert repo.tasks(broken)[0]["name"] == "Unsent local"
    assert provider.writes == []


def test_mid_push_network_loss_stops_remaining_writes_and_recovers(repo):
    provider, key, engine = setup(repo)
    with repo.conn:
        for name in ("First", "Second", "Third"):
            repo.import_task(key, task(name))
    original = provider.create
    attempts = []

    def offline(*args):
        attempts.append(args)
        raise CalendarSyncError("network_unavailable")

    provider.create = offline
    with pytest.raises(CalendarSyncError, match="^network_unavailable$"):
        engine.run()
    assert len(attempts) == 1
    assert repo.issues("account") == []
    assert len(repo.tasks(key)) == 3
    provider.create = original
    assert engine.run()["created"] == 3
    assert len(provider.remote) == 3


@pytest.mark.parametrize(
    "error",
    [
        CalendarSyncError("network_unavailable"),
        *[RemoteCalendarError(n) for n in (401, 408, 429, 503)],
    ],
)
def test_service_outage_does_not_spend_delete_retry_allowance(repo, error):
    provider, key, engine = setup(repo)
    with repo.conn:
        for identifier in ("first", "second"):
            repo.conn.execute(
                "INSERT INTO calendar_sync_delete_queue(event_id,calendar_id,etag) VALUES(?,?,'1')",
                (identifier, key),
            )
    attempts = []

    def unavailable(identifier):
        attempts.append(identifier)
        raise error

    provider.event = unavailable
    for _ in range(6):
        with pytest.raises(CalendarSyncError):
            engine._deletions(key)
    assert attempts == ["first"] * 6
    queue = list(repo.conn.execute("SELECT attempts,error FROM calendar_sync_delete_queue"))
    assert [(row["attempts"], row["error"]) for row in queue] == [(0, None), (0, None)]


def test_missing_calendar_preserves_selection_and_recovers_permissions(repo):
    _, missing, _ = setup(repo)
    healthy = repo.register("account", {"id": "healthy", "name": "Healthy", "can_edit": True})
    paused = repo.register("account", {"id": "paused", "name": "Paused", "can_edit": True})
    with repo.conn:
        repo.conn.execute("UPDATE calendar SET is_active=0 WHERE id=?", (paused,))
    errors = repo.refresh_calendar_metadata(
        "account", [{"id": "healthy", "name": "Healthy renamed", "can_edit": True}]
    )
    assert errors == {missing: "calendar_access_lost"}
    selected = {row["local_id"]: row for row in repo.calendars("account")}
    assert selected[missing]["is_active"] == 1
    assert selected[missing]["can_edit"] == 0
    assert selected[healthy]["can_edit"] == 1
    assert selected[paused]["is_active"] == 0
    assert (
        repo.refresh_calendar_metadata(
            "account",
            [
                {"id": "calendar", "name": "Returned", "can_edit": True},
                {"id": "healthy", "name": "Healthy renamed", "can_edit": True},
            ],
        )
        == {}
    )
    assert (
        next(row for row in repo.calendars("account") if row["local_id"] == missing)["can_edit"]
        == 1
    )


def test_calendar_metadata_update_rolls_back_if_later_record_fails(repo):
    _, first, _ = setup(repo)
    second = repo.register("account", {"id": "second", "name": "Second", "can_edit": True})
    repo.conn.execute(
        f"CREATE TRIGGER reject_second BEFORE UPDATE ON calendar WHEN NEW.id = '{second}' "
        "BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END;"
    )
    with pytest.raises(sqlite3.IntegrityError):
        repo.refresh_calendar_metadata(
            "account", [{"id": "second", "name": "Changed", "can_edit": False}]
        )
    assert (
        next(row for row in repo.calendars("account") if row["local_id"] == first)["can_edit"] == 1
    )
    assert (
        repo.conn.execute("SELECT access_role FROM calendar WHERE id=?", (first,)).fetchone()[0]
        == "writer"
    )


def test_known_missing_calendar_is_skipped_while_healthy_one_syncs(repo):
    provider, missing, _ = setup(repo)
    healthy = repo.register("account", {"id": "healthy", "name": "Healthy", "can_edit": True})
    calls = []

    def events(calendar, *_):
        calls.append(calendar)
        return [{"id": "one", "etag": "1", "task": task()}]

    provider.events = events
    summary = CalendarSyncEngine(
        provider, repo, "account", calendar_errors={missing: "calendar_access_lost"}
    ).run()
    assert calls == ["healthy"]
    assert summary["issues"] == 1
    assert len(repo.tasks(healthy)) == 1
