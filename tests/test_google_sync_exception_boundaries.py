# -*- coding: utf-8 -*-
"""Keep failed local reads from becoming unverified Google creates."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from calendar_app.infrastructure.google_sync import engine


@pytest.mark.parametrize("change", ["deleted", "moved", "edited"])
def test_batch_create_defers_a_deleted_or_changed_local_snapshot(monkeypatch, change):
    snapshot = {
        "id": 7,
        "calendar_id": "gcal::team",
        "name": "Original",
        "deadline": "2026-10-16T10:00:00",
    }
    fresh = None if change == "deleted" else snapshot.copy()
    if change == "moved":
        fresh["calendar_id"] = "local::personal"
    elif change == "edited":
        fresh["name"] = "Newer edit"
    batch = Mock(return_value=[{"local_task_id": 7, "success": True, "event_id": "stale-created"}])
    sync = SimpleNamespace(is_authenticated=True, batch_create_events=batch)
    monkeypatch.setattr(engine, "_get_default_gcal_id", lambda _: "team")
    monkeypatch.setattr(engine, "_writable_gcal_ids", lambda: {"team"})
    monkeypatch.setattr(engine.task_repo, "get_google_sync_tasks", lambda: [snapshot])
    monkeypatch.setattr(engine.task_repo, "get_unified_task", lambda _: fresh)
    monkeypatch.setattr(engine.task_repo, "mark_unified_task_gcal_synced", Mock(return_value=True))
    monkeypatch.setattr(engine, "_mark_sync_failure", Mock())

    assert engine._push_local_changes_to_google(SimpleNamespace(gcal_sync=sync)) == (0, 0, 0)

    batch.assert_not_called()
    engine._mark_sync_failure.assert_not_called()


def test_reentrant_sync_preserves_the_active_calls_in_progress_guard():
    app = SimpleNamespace(_gcal_sync_in_progress=True)

    assert not engine.sync_google_calendar(app, silent=True)

    assert app._gcal_sync_in_progress is True
    assert app._last_gcal_sync_error == "sync_in_progress"


@pytest.mark.parametrize("with_healthy_task", [False, True])
@pytest.mark.parametrize("batch_unavailable", [False, True])
def test_batch_create_defers_failed_reread_and_continues_verified_tasks(
    monkeypatch, with_healthy_task, batch_unavailable
):
    failed_task = {"id": 7, "calendar_id": "gcal::team"}
    healthy_task = {"id": 8, "calendar_id": "gcal::team"}
    tasks = [failed_task, healthy_task] if with_healthy_task else [failed_task]
    failures = []
    synced = []
    requests = []

    def reread(task_id):
        if task_id == 7:
            raise RuntimeError("synthetic database read failure")
        return healthy_task.copy()

    def batch_create(operations):
        requests.extend(operations)
        if batch_unavailable:
            return []
        return [
            {"local_task_id": operation["local_task_id"], "success": True, "event_id": "remote-8"}
            for operation in operations
        ]

    sync = SimpleNamespace(is_authenticated=True, batch_create_events=batch_create)
    monkeypatch.setattr(engine, "_get_default_gcal_id", lambda _: "team")
    monkeypatch.setattr(engine, "_writable_gcal_ids", lambda: {"team"})
    monkeypatch.setattr(engine.task_repo, "get_google_sync_tasks", lambda: tasks)
    monkeypatch.setattr(engine.task_repo, "get_unified_task", reread)
    monkeypatch.setattr(engine, "_mark_sync_failure", lambda *args, **kwargs: failures.append(args))
    monkeypatch.setattr(
        engine.task_repo,
        "mark_unified_task_gcal_synced",
        lambda task_id, **kwargs: synced.append(task_id) or True,
    )

    def sequential_create(app, task, **kwargs):
        assert task["id"] == 8, "Do not retry an unverified create this cycle"
        return SimpleNamespace(success=True, event_id="remote-8", auto_healed=False)

    sequential = Mock(side_effect=sequential_create)
    monkeypatch.setattr(engine, "sync_task_to_google", sequential)

    result = engine._push_local_changes_to_google(SimpleNamespace(gcal_sync=sync))

    assert result == (int(with_healthy_task), 1, 0)
    assert [operation["local_task_id"] for operation in requests] == (
        [8] if with_healthy_task else []
    )
    assert synced == ([8] if with_healthy_task and not batch_unavailable else [])
    assert failures == [(7, "pre_create_db_reread_error")]
    assert sequential.call_count == int(with_healthy_task and batch_unavailable)
