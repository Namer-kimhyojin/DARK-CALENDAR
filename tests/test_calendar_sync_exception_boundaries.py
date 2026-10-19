# -*- coding: utf-8 -*-
"""Do not persist stale remote failures after local edits or cancellation."""

from copy import deepcopy
import sqlite3

import pytest

from calendar_app.application.calendar_sync_contract import CalendarSyncError, RemoteCalendarError
from calendar_app.infrastructure.calendar_sync.engine import CalendarSyncEngine
from calendar_app.infrastructure.calendar_sync.repository import CalendarSyncRepository
from tests.test_calendar_sync_engine import imported, repo, setup, task


def test_missing_remote_during_calendar_move_preserves_live_link(repo):
    provider, key, engine, tid = imported(repo)
    provider.events = lambda *args: []

    def move_and_fail(event_id):
        with repo.conn:
            repo.conn.execute(
                "UPDATE unified_task SET calendar_id='local::other' WHERE id=?", (tid,)
            )
        raise RemoteCalendarError(404)

    provider.event = move_and_fail
    engine.run()
    assert not repo.task_link(tid)["remote_deleted"]
    assert repo.issues("account")[0]["kind"] == "calendar_move_not_supported"
    with repo.conn:
        repo.conn.execute("UPDATE unified_task SET calendar_id=? WHERE id=?", (key, tid))
    provider.events = lambda *args: list(provider.remote.values())
    engine.run()
    assert repo.issues("account") == []


def test_missing_remote_during_local_edit_defers_failure_until_new_snapshot(repo):
    provider, key, engine, tid = imported(repo)
    provider.events = lambda *args: []

    def edit_and_fail(event_id):
        with repo.conn:
            repo.conn.execute("UPDATE unified_task SET name='Newer edit' WHERE id=?", (tid,))
        raise RemoteCalendarError(404)

    provider.event = edit_and_fail
    engine.run()
    assert repo.task(tid)["name"] == "Newer edit"
    assert not repo.task_link(tid)["remote_deleted"]
    assert repo.issues("account") == []


def test_cancellation_during_missing_remote_read_does_not_apply_failure(repo):
    provider, key, engine, tid = imported(repo)
    provider.events = lambda *args: []
    cancelled = [False]

    def cancel_and_fail(event_id):
        cancelled[0] = True
        raise RemoteCalendarError(404)

    provider.event = cancel_and_fail
    engine.cancelled = lambda: cancelled[0]
    with pytest.raises(CalendarSyncError, match="^cancelled$"):
        engine.run()
    assert not repo.task_link(tid)["remote_deleted"]
    assert repo.issues("account") == []


def _deleted_pending_create(repo):
    provider, key, engine = setup(repo)
    with repo.conn:
        tid = repo.import_task(key, task())
    create = provider.create

    def lost_response(*args):
        create(*args)
        raise CalendarSyncError("network_unavailable")

    provider.create = lost_response
    engine.run()
    with repo.conn:
        repo.conn.execute("DELETE FROM unified_task WHERE id=?", (tid,))
    provider.create = create
    return provider, key, engine


def test_delete_after_lost_create_response_does_not_reimport_deleted_task(repo):
    provider, key, engine = _deleted_pending_create(repo)
    engine.run()
    assert repo.tasks(key) == []
    assert provider.remote == {}
    assert repo.conn.execute("SELECT COUNT(*) FROM calendar_sync_pending_delete").fetchone()[0] == 0


def test_pending_delete_survives_database_restart(repo, tmp_path):
    provider, key, engine = _deleted_pending_create(repo)
    path = tmp_path / "restarted.db"
    with sqlite3.connect(path) as saved:
        repo.conn.backup(saved)
    restarted = sqlite3.connect(path)
    try:
        repository = CalendarSyncRepository(restarted)
        CalendarSyncEngine(provider, repository, "account").run()
        assert repository.tasks(key) == []
        assert provider.remote == {}
    finally:
        restarted.close()


def test_failed_pull_preserves_pending_delete_for_later_receipt(repo):
    provider, key, engine = _deleted_pending_create(repo)
    provider.fail_read = True
    with pytest.raises(CalendarSyncError, match="^network_unavailable$"):
        engine.run()
    assert repo.conn.execute("SELECT COUNT(*) FROM calendar_sync_pending_delete").fetchone()[0] == 1
    assert provider.writes == ["create"]
    provider.fail_read = False
    engine.run()
    assert provider.remote == {}


def test_invalid_later_remote_event_preserves_pending_delete(repo):
    provider, key, engine = _deleted_pending_create(repo)
    provider.remote["malformed"] = {"id": "malformed", "task": task()}
    convert = provider.to_task

    def invalid(event, zone):
        if event["id"] == "malformed":
            raise CalendarSyncError("invalid_event_time")
        return convert(event, zone)

    provider.to_task = invalid
    with pytest.raises(CalendarSyncError, match="^invalid_event_time$"):
        engine.run()
    assert repo.conn.execute("SELECT COUNT(*) FROM calendar_sync_pending_delete").fetchone()[0] == 1
    assert repo.conn.execute("SELECT COUNT(*) FROM calendar_sync_delete_queue").fetchone()[0] == 0
    assert provider.writes == ["create"]


def test_pending_delete_never_deletes_later_remote_edit(repo):
    provider, key, engine = _deleted_pending_create(repo)
    remote = next(iter(provider.remote.values()))
    remote.update(etag="2", task=task("Edited remotely"))
    engine.run()
    assert repo.tasks(key) == []
    assert provider.remote
    assert provider.writes == ["create"]
    pending = repo.conn.execute("SELECT * FROM calendar_sync_delete_queue").fetchone()
    assert pending["error"] == "delete_conflict"
    assert pending["etag"] == "2"


def test_pending_delete_waits_for_write_permission(repo):
    provider, key, engine = _deleted_pending_create(repo)
    repo.register("account", {"id": "calendar", "name": "Read only", "can_edit": False})
    engine.run()
    assert repo.tasks(key) == []
    assert provider.remote
    assert provider.writes == ["create"]
    assert repo.conn.execute("SELECT COUNT(*) FROM calendar_sync_delete_queue").fetchone()[0] == 1
    repo.register("account", {"id": "calendar", "name": "Writable", "can_edit": True})
    engine.run()
    assert provider.remote == {}


@pytest.mark.parametrize("other", ["account", "calendar", "provider"])
def test_pending_delete_identity_isolated_from_other_connections(repo, other):
    provider, key, engine = _deleted_pending_create(repo)
    repository = CalendarSyncRepository(repo.conn, "caldav" if other == "provider" else "outlook")
    account = "different-account" if other == "account" else "account"
    remote_id = "different-calendar" if other == "calendar" else "calendar"
    other_key = repository.register(
        account, {"id": remote_id, "name": "Unrelated", "can_edit": True}
    )
    with repo.conn:
        repo.conn.execute("UPDATE calendar SET is_active=0 WHERE id=?", (key,))
    CalendarSyncEngine(provider, repository, account).run()
    assert len(repository.tasks(other_key)) == 1
    assert provider.writes == ["create"]
    assert repo.conn.execute("SELECT COUNT(*) FROM calendar_sync_pending_delete").fetchone()[0] == 1


def test_duplicate_transaction_receipts_do_not_consume_pending_delete(repo):
    provider, key, engine = _deleted_pending_create(repo)
    event = deepcopy(next(iter(provider.remote.values())))
    event["id"] = "duplicate-receipt"
    provider.remote[event["id"]] = event
    with pytest.raises(CalendarSyncError, match="^duplicate_remote_event$"):
        engine.run()
    assert repo.conn.execute("SELECT COUNT(*) FROM calendar_sync_pending_delete").fetchone()[0] == 1
    assert repo.conn.execute("SELECT COUNT(*) FROM calendar_sync_delete_queue").fetchone()[0] == 0
    assert provider.writes == ["create"]


def test_recurring_occurrences_may_share_transaction_without_pending_delete(repo):
    provider, key, engine = setup(repo)
    for index in range(2):
        provider.remote[str(index)] = {
            "id": str(index),
            "uid": "series",
            "recurrence_id": str(index),
            "transaction_id": "shared-series-transaction",
            "task": task(),
        }
    result = engine.run()
    assert result["imported"] == 2
    assert provider.writes == []


def test_successful_inflight_create_delete_clears_pending_transaction(repo):
    provider, key, engine = setup(repo)
    with repo.conn:
        tid = repo.import_task(key, task())

    def remove():
        with repo.conn:
            repo.conn.execute("DELETE FROM unified_task WHERE id=?", (tid,))

    provider.before_write = remove
    engine.run()
    assert repo.tasks(key) == []
    assert provider.remote == {}
    assert repo.conn.execute("SELECT COUNT(*) FROM calendar_sync_pending_delete").fetchone()[0] == 0


def test_pending_delete_cancelled_during_remote_conversion_is_preserved(repo):
    provider, key, engine = _deleted_pending_create(repo)
    cancelled = [False]
    convert = provider.to_task

    def cancel(event, zone):
        cancelled[0] = True
        return convert(event, zone)

    provider.to_task = cancel
    engine.cancelled = lambda: cancelled[0]
    with pytest.raises(CalendarSyncError, match="^cancelled$"):
        engine.run()
    assert repo.conn.execute("SELECT COUNT(*) FROM calendar_sync_pending_delete").fetchone()[0] == 1
    assert provider.writes == ["create"]


def test_recovered_pending_delete_cancelled_during_remote_read_is_not_sent(repo):
    provider, key, engine = _deleted_pending_create(repo)
    read = provider.event

    def keep_remote(event_id):
        with repo.conn:
            repo.conn.execute("DELETE FROM calendar_sync_delete_queue WHERE calendar_id=?", (key,))
        return read(event_id)

    provider.event = keep_remote
    engine.run()
    assert provider.remote
    assert provider.writes == ["create"]


def test_pending_create_deleted_during_receipt_merge_cannot_be_reimported(repo):
    provider, key, engine = setup(repo)
    with repo.conn:
        tid = repo.import_task(key, task())
    create = provider.create

    def lost_response(*args):
        create(*args)
        raise CalendarSyncError("network_unavailable")

    provider.create = lost_response
    engine.run()
    provider.create = create
    read = repo.task
    removed = [False]

    def delete_before_merge(task_id):
        if task_id == tid and not removed[0]:
            removed[0] = True
            with repo.conn:
                repo.conn.execute("DELETE FROM unified_task WHERE id=?", (tid,))
        return read(task_id)

    repo.task = delete_before_merge
    engine.run()
    assert removed[0]
    assert repo.tasks(key) == []
    assert provider.remote == {}
