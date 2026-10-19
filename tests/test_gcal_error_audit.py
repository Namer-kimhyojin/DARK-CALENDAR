# -*- coding: utf-8 -*-
"""Synthetic Google API failures; no Google requests or personal credentials."""

import json
from types import MethodType, SimpleNamespace

from googleapiclient.errors import HttpError
from httplib2 import Response
import pytest

from calendar_app.infrastructure.db import task_repo
from calendar_app.infrastructure.google_sync import engine, service
from calendar_app.presentation.dialogs.gcal_settings_dialog import GCalSettingsDialog
from calendar_app.presentation.dialogs.sync_feedback import sync_error_message


def google_error(status, reason):
    payload = {
        "error": {
            "code": status,
            "message": "Synthetic API failure",
            "errors": [{"domain": "usageLimits", "reason": reason}],
        }
    }
    return HttpError(
        Response({"status": str(status)}),
        json.dumps(payload).encode("utf-8", errors="strict"),
    )


@pytest.mark.parametrize("reason", ["rateLimitExceeded", "userRateLimitExceeded"])
def test_google_403_rate_limits_retry_and_recover(monkeypatch, reason):
    sync = service.CalendarSyncService()
    calls = []
    waits = []
    monkeypatch.setattr(service.time, "sleep", waits.append)

    def request():
        calls.append(1)
        if len(calls) == 1:
            raise google_error(403, reason)
        return {"items": []}

    assert sync._execute_request(request, retries=1) == {"items": []}
    assert len(calls) == 2
    assert len(waits) == 1 and waits[0] > 0


@pytest.mark.parametrize("reason", ["forbidden", "insufficientPermissions", "quotaExceeded"])
def test_google_403_permanent_errors_do_not_retry(monkeypatch, reason):
    sync = service.CalendarSyncService()
    calls = []
    monkeypatch.setattr(service.time, "sleep", lambda _: pytest.fail("Must not retry"))

    def request():
        calls.append(1)
        raise google_error(403, reason)

    with pytest.raises(HttpError):
        sync._execute_request(request, retries=3)
    assert len(calls) == 1


def test_google_429_still_honors_retry_after(monkeypatch):
    sync = service.CalendarSyncService()
    failure = google_error(429, "rateLimitExceeded")
    failure.resp["retry-after"] = "2"
    calls = []
    waits = []
    monkeypatch.setattr(service.time, "sleep", waits.append)

    def request():
        calls.append(1)
        if len(calls) == 1:
            raise failure
        return "recovered"

    assert sync._execute_request(request, retries=1) == "recovered"
    assert waits == [2.0]


def test_google_rate_limit_retries_stop_at_bound(monkeypatch):
    sync = service.CalendarSyncService()
    failure = google_error(403, "rateLimitExceeded")
    calls = []
    waits = []
    monkeypatch.setattr(service.time, "sleep", waits.append)

    def request():
        calls.append(1)
        raise failure

    with pytest.raises(HttpError):
        sync._execute_request(request, retries=2)
    assert len(calls) == 3
    assert len(waits) == 2


def test_google_diagnostics_preserves_authentication_error(monkeypatch):
    values = {}

    def meta(name):
        return (None, SimpleNamespace(setText=lambda value: values.__setitem__(name, value)))

    for name in (
        "count_unified_task_gcal_errors",
        "count_gcal_delete_queue_errors",
        "count_gcal_sync_conflicts",
    ):
        monkeypatch.setattr(task_repo, name, lambda: 0)
    monkeypatch.setattr(task_repo, "get_gcal_delete_queue", lambda: [])
    dialog = SimpleNamespace(
        parent_app=SimpleNamespace(
            gcal_sync=SimpleNamespace(
                is_authenticated=False,
                last_error_kind="auth_required",
                last_error_message="Synthetic authentication failure",
            )
        ),
        settings=SimpleNamespace(value=lambda *args: ""),
        issue_meta=meta("issues"),
        delete_queue_meta=meta("delete"),
        bound_calendar_meta=meta("bound"),
        last_error_meta=meta("error"),
    )
    dialog._friendly_error = MethodType(GCalSettingsDialog._friendly_error, dialog)
    GCalSettingsDialog._refresh_diagnostics(dialog)
    assert values["error"] == sync_error_message("login_required")


@pytest.mark.parametrize(
    "status,reason",
    [(403, "rateLimitExceeded"), (403, "userRateLimitExceeded"), (429, "rateLimitExceeded")],
)
def test_google_delete_queue_stops_and_preserves_remaining_on_rate_limit(
    monkeypatch, status, reason
):
    sync = SimpleNamespace(
        is_authenticated=True,
        last_error_status=status,
        last_error_message=str(google_error(status, reason)),
    )
    rows = [{"id": index, "gcal_event_id": f"event-{index}"} for index in (1, 2)]
    calls = []
    monkeypatch.setattr(engine.task_repo, "get_gcal_delete_queue_ready", lambda **_: rows)
    monkeypatch.setattr(engine.gcal_db_adapter, "get_connection", lambda: None)
    monkeypatch.setattr(
        engine, "delete_task_from_google", lambda *a, **k: calls.append(a[1]) or False
    )
    monkeypatch.setattr(
        engine.task_repo,
        "mark_gcal_delete_done",
        lambda *a: pytest.fail("Must preserve queued delete"),
    )
    monkeypatch.setattr(
        engine.task_repo,
        "mark_gcal_delete_failed",
        lambda *a, **k: pytest.fail("Rate limit must not consume permanent-failure retries"),
    )
    assert engine._process_google_delete_queue(SimpleNamespace(gcal_sync=sync)) == (0, 1)
    assert calls == ["event-1"]


@pytest.mark.parametrize(
    "status,reason",
    [(403, "rateLimitExceeded"), (403, "userRateLimitExceeded"), (429, "rateLimitExceeded")],
)
def test_google_push_stops_on_rate_limit_and_retains_pending_tasks(monkeypatch, status, reason):
    sync = SimpleNamespace(is_authenticated=True, last_error_status=status)
    app = SimpleNamespace(gcal_sync=sync)
    tasks = [{"id": index, "gcal_event_id": f"event-{index}"} for index in (1, 2)]
    calls = []
    failures = []
    monkeypatch.setattr(engine, "_get_default_gcal_id", lambda _: "team")
    monkeypatch.setattr(engine, "_task_target_calendar_id", lambda *a: "team")
    monkeypatch.setattr(engine, "_writable_gcal_ids", lambda: {"team"})
    monkeypatch.setattr(engine.task_repo, "get_google_sync_tasks", lambda: tasks)
    monkeypatch.setattr(engine, "_mark_sync_failure", lambda *a, **k: failures.append(a))

    def fail(*args, **kwargs):
        calls.append(args[1]["id"])
        return SimpleNamespace(
            success=False, error_kind="update", error_message=str(google_error(status, reason))
        )

    monkeypatch.setattr(engine, "sync_task_to_google", fail)
    assert engine._push_local_changes_to_google(app) == (0, 1, 0)
    assert calls == [1]
    assert failures[0][0] == 1
    assert failures[0][1] == f"rate_limit_{status}"


@pytest.mark.parametrize(
    "content",
    [b"invalid-json", b"[]", b'{"error":null}', b'{"error":{"errors":null}}'],
)
def test_malformed_google_403_is_not_a_retryable_quota(content):
    assert not service.is_google_rate_limit_error(403, SimpleNamespace(content=content))


@pytest.mark.parametrize("reason", ["rateLimitExceeded", "userRateLimitExceeded"])
@pytest.mark.parametrize("expired_sync_token", [False, True])
def test_google_pull_rate_limit_preserves_sync_token_failure_state(
    monkeypatch, reason, expired_sync_token
):
    values = {
        "gcal_enabled": "true",
        "gcal_calendar_id": "team",
        "gcal_bound_calendar_id": "team",
        "gcal_sync_token::team": "existing-token",
        "gcal_sync_token_fails::team": 1,
    }
    requests = []
    settings = SimpleNamespace(
        value=lambda key, default=None, **kwargs: values.get(key, default),
        setValue=lambda key, value: values.__setitem__(key, value),
    )
    sync = SimpleNamespace(
        is_authenticated=True,
        authenticate=lambda *a, **k: True,
        last_error_kind="fetch",
        last_error_status=403,
        last_error_message=str(google_error(403, reason)),
    )

    def fetch(sync_token, **kwargs):
        requests.append(sync_token)
        return None, None, expired_sync_token and len(requests) == 1

    sync.fetch_sync_events = fetch
    app = SimpleNamespace(settings=settings, gcal_sync=sync)
    monkeypatch.setattr(engine, "_calendar_source_summary_map", lambda: {})
    monkeypatch.setattr(engine, "_refresh_resolved_primary_alias_id", lambda _: "team")
    monkeypatch.setattr(engine, "_process_google_delete_queue", lambda _: (0, 0))
    monkeypatch.setattr(engine, "_should_refresh_calendar_list", lambda _: False)
    monkeypatch.setattr(engine, "_active_sync_calendar_ids", lambda *a: ["team"])
    monkeypatch.setattr(engine.gcal_db_adapter, "get_all_gcal_tasks_map", lambda: {})
    monkeypatch.setattr(
        engine,
        "_push_local_changes_to_google",
        lambda *a: pytest.fail("Do not push after failed pull"),
    )
    assert not engine.sync_google_calendar(app, silent=True)
    assert app._last_gcal_sync_stats["pull_fetch_failures"] == 1
    assert values["gcal_sync_token::team"] == ("" if expired_sync_token else "existing-token")
    # An expired token records its reset once; rate limiting adds no token-failure count.
    assert values["gcal_sync_token_fails::team"] == (2 if expired_sync_token else 1)
    assert requests == (["existing-token", None] if expired_sync_token else ["existing-token"])


@pytest.mark.parametrize(
    "status,reason",
    [(403, "rateLimitExceeded"), (403, "userRateLimitExceeded"), (429, "rateLimitExceeded")],
)
def test_google_batch_create_rate_limit_defers_next_batch_and_updates(monkeypatch, status, reason):
    batch_calls = []
    tasks = [{"id": index} for index in range(1, 52)] + [
        {"id": 52, "gcal_event_id": "existing-event"}
    ]

    def batch_create(operations):
        batch_calls.append(operations)
        return [
            {
                "local_task_id": operation["local_task_id"],
                "success": False,
                "status": status,
                "error": str(google_error(status, reason)),
            }
            for operation in operations
        ]

    sync = SimpleNamespace(is_authenticated=True, batch_create_events=batch_create)
    monkeypatch.setattr(engine, "_get_default_gcal_id", lambda _: "team")
    monkeypatch.setattr(engine, "_task_target_calendar_id", lambda *a: "team")
    monkeypatch.setattr(engine, "_writable_gcal_ids", lambda: {"team"})
    monkeypatch.setattr(engine.task_repo, "get_google_sync_tasks", lambda: tasks)
    monkeypatch.setattr(
        engine.task_repo,
        "get_unified_task",
        lambda task_id: next(t for t in tasks if t["id"] == task_id),
    )
    monkeypatch.setattr(engine.task_repo, "mark_unified_task_gcal_failed", lambda *a, **k: True)
    monkeypatch.setattr(
        engine, "sync_task_to_google", lambda *a, **k: pytest.fail("Must defer remaining updates")
    )
    assert engine._push_local_changes_to_google(SimpleNamespace(gcal_sync=sync)) == (0, 50, 0)
    assert len(batch_calls) == 1


@pytest.mark.parametrize("status", [403, 429])
def test_google_batch_delete_rate_limit_preserves_queue(monkeypatch, status):
    calls = []
    rows = [{"id": index, "gcal_event_id": f"event-{index}"} for index in range(1, 52)]

    def batch_delete(operations):
        calls.append(operations)
        return [
            {
                "local_task_id": 1,
                "success": False,
                "status": status,
                "error": str(google_error(status, "rateLimitExceeded")),
            }
        ]

    sync = SimpleNamespace(is_authenticated=True, batch_delete_events=batch_delete)
    monkeypatch.setattr(engine.task_repo, "get_gcal_delete_queue_ready", lambda **_: rows)
    monkeypatch.setattr(engine.gcal_db_adapter, "get_connection", lambda: None)
    monkeypatch.setattr(
        engine.task_repo,
        "mark_gcal_delete_failed",
        lambda *a, **k: pytest.fail("Preserve retry count"),
    )
    assert engine._process_google_delete_queue(SimpleNamespace(gcal_sync=sync)) == (0, 1)
    assert len(calls) == 1


@pytest.mark.parametrize("failure", ["push", "delete", "pull_apply", "pull_fetch", None])
def test_google_partial_failures_do_not_report_full_success(monkeypatch, failure):
    values = {"gcal_enabled": "true", "gcal_calendar_id": "team", "gcal_bound_calendar_id": "team"}
    settings = SimpleNamespace(
        value=lambda key, default=None, **kwargs: values.get(key, default),
        setValue=lambda key, value: values.__setitem__(key, value),
    )
    event = service.GoogleEvent(
        id="event-1",
        summary="Updated",
        description="",
        start_time="2026-10-06T09:00:00+09:00",
        end_time="2026-10-06T10:00:00+09:00",
        location="",
        updated_time="2026-10-06T00:00:00Z",
    )
    sync = SimpleNamespace(
        is_authenticated=True,
        authenticate=lambda *a, **k: True,
        fetch_sync_events=lambda *a, **k: (
            (None, None, False)
            if k.get("calendar_id") == "other"
            else ([event], "next-token", False)
        ),
        last_error_kind=None,
    )
    app = SimpleNamespace(
        settings=settings,
        gcal_sync=sync,
        current_date=SimpleNamespace(toString=lambda _: "2026-10-06"),
    )
    monkeypatch.setattr(engine, "_calendar_source_summary_map", lambda: {})
    monkeypatch.setattr(engine, "_refresh_resolved_primary_alias_id", lambda _: "team")
    monkeypatch.setattr(
        engine, "_process_google_delete_queue", lambda _: (0, int(failure == "delete"))
    )
    monkeypatch.setattr(engine, "_should_refresh_calendar_list", lambda _: False)
    monkeypatch.setattr(
        engine,
        "_active_sync_calendar_ids",
        lambda *a: ["team", "other"] if failure == "pull_fetch" else ["team"],
    )
    monkeypatch.setattr(engine.gcal_db_adapter, "get_connection", lambda: None)
    monkeypatch.setattr(
        engine.gcal_db_adapter,
        "get_all_gcal_tasks_map",
        lambda: {"team::event-1": ("unified_task", 7)},
    )
    monkeypatch.setattr(
        engine.task_repo, "get_unified_task", lambda _: {"id": 7, "name": "Old", "gcal_dirty": 0}
    )
    monkeypatch.setattr(
        engine.gcal_db_adapter, "update_task_from_gcal", lambda *a, **k: failure != "pull_apply"
    )
    monkeypatch.setattr(
        engine, "_push_local_changes_to_google", lambda *a: (2, int(failure == "push"), 0)
    )
    heal_calls = []
    monkeypatch.setattr(engine, "_should_run_auto_heal_orphans", lambda *a, **k: True)
    monkeypatch.setattr(engine, "auto_heal_google_orphans", lambda *a, **k: heal_calls.append(1))
    monkeypatch.setattr(engine, "_mark_auto_heal_orphans_run", lambda *a: None)
    result = engine.sync_google_calendar(app, silent=True)
    assert result is (failure is None)
    assert app._last_gcal_sync_outcome == (
        engine.SYNC_OUTCOME_FAILED if failure else engine.SYNC_OUTCOME_SUCCESS
    )
    assert app._last_gcal_sync_changed_any is (failure != "pull_apply")
    assert app._last_gcal_sync_stats["pull_changes"] == int(failure != "pull_apply")
    assert values.get("gcal_sync_token::team") == (
        None if failure == "pull_apply" else "next-token"
    )
    assert heal_calls == ([] if failure else [1])
