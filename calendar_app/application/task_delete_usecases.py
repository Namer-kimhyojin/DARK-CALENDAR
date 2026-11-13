# -*- coding: utf-8 -*-
"""Shared delete flows for task removal + Google delete queue handling."""

from __future__ import annotations

from collections.abc import Callable, Iterable

QueueDeleteFn = Callable[[str, int | None, str | None], object]


def _default_is_read_only(calendar_id):
    from calendar_app.infrastructure.db.calendar_repo import is_calendar_read_only

    return is_calendar_read_only(calendar_id)


def read_only_task_ids(task_repo, task_ids: Iterable[int], *, is_read_only=None) -> list:
    """Tasks on a calendar the user cannot write to; a delete there cannot reach it."""
    check = is_read_only or _default_is_read_only
    blocked = []
    for task_id in task_ids or []:
        task = task_repo.get_unified_task(task_id)
        if task and task.get("calendar_id") and check(task.get("calendar_id")):
            blocked.append(task_id)
    return blocked


def queue_google_deletes_for_task_ids(
    task_repo, task_ids: Iterable[int], *, queue_delete_fn: QueueDeleteFn
) -> int:
    """Queue Google event deletes for a list of local task ids."""
    queued = 0
    for task_id in task_ids or []:
        task = task_repo.get_unified_task(task_id)
        if not task:
            continue
        if task.get("type") != "schedule":
            continue
        gcal_event_id = task.get("gcal_event_id")
        if not gcal_event_id:
            continue
        gcal_calendar_id = task.get("gcal_source_calendar_id") or task.get(
            "gcal_target_calendar_id"
        )
        if queue_delete_fn(gcal_event_id, int(task_id), gcal_calendar_id) is not False:
            queued += 1
    return queued


def queue_google_deletes_for_task_rows(tasks, *, queue_delete_fn: QueueDeleteFn) -> int:
    """Queue Google event deletes from preloaded task rows."""
    queued = 0
    for task in tasks or []:
        if task.get("type") != "schedule":
            continue
        gcal_event_id = task.get("gcal_event_id")
        if not gcal_event_id:
            continue
        task_id = task.get("id")
        gcal_calendar_id = task.get("gcal_source_calendar_id") or task.get(
            "gcal_target_calendar_id"
        )
        if (
            queue_delete_fn(gcal_event_id, int(task_id) if task_id else None, gcal_calendar_id)
            is not False
        ):
            queued += 1
    return queued


def queue_google_deletes_for_refs(gcal_refs, *, queue_delete_fn: QueueDeleteFn) -> int:
    """Queue Google event deletes from purge refs dict list."""
    queued = 0
    for ref in gcal_refs or []:
        gcal_event_id = ref.get("gcal_event_id")
        if not gcal_event_id:
            continue
        if queue_delete_fn(gcal_event_id, None, ref.get("gcal_calendar_id")) is not False:
            queued += 1
    return queued


def delete_tasks_with_google_queue(
    task_repo, task_ids: Iterable[int], *, queue_delete_fn: QueueDeleteFn, is_read_only=None
) -> int:
    """Delete tasks without losing a required Google delete request.

    Tasks on read-only calendars are skipped: the remote copy would bring them back.
    """
    task_ids = list(task_ids or [])
    blocked = set(read_only_task_ids(task_repo, task_ids, is_read_only=is_read_only))
    deleted = 0
    atomic_delete = getattr(task_repo, "delete_unified_task_with_gcal_outbox", None)
    for task_id in task_ids:
        if task_id in blocked:
            continue
        if callable(atomic_delete):
            if atomic_delete(task_id):
                deleted += 1
            continue

        task = task_repo.get_unified_task(task_id)
        if not task:
            continue
        event_id = task.get("gcal_event_id") if task.get("type") == "schedule" else None
        if event_id:
            calendar_id = task.get("gcal_source_calendar_id") or task.get("gcal_target_calendar_id")
            if queue_delete_fn(event_id, int(task_id), calendar_id) is False:
                continue
        if task_repo.delete_unified_task(task_id):
            deleted += 1
    return deleted


def delete_tasks_on_date_with_google_queue(
    search_repo, task_repo, date_str: str, *, queue_delete_fn: QueueDeleteFn, is_read_only=None
) -> int:
    """Queue Google deletes for all tasks on date, then delete them locally."""
    tasks = search_repo.get_all_tasks_by_date(date_str)
    schedules = [task for task in tasks if task.get("type") == "schedule"]
    check = is_read_only or _default_is_read_only
    if any(task.get("calendar_id") and check(task.get("calendar_id")) for task in schedules):
        # Keep read-only calendars' events; delete the rest one by one.
        return delete_tasks_with_google_queue(
            task_repo,
            [task.get("id") for task in schedules if task.get("id")],
            queue_delete_fn=queue_delete_fn,
            is_read_only=check,
        )
    atomic_delete = getattr(task_repo, "delete_unified_task_with_gcal_outbox", None)
    if callable(atomic_delete):
        deleted = 0
        for task in schedules:
            task_id = task.get("id")
            if not task_id or not atomic_delete(task_id):
                continue
            deleted += 1
        return deleted

    expected_google_deletes = sum(
        1 for task in schedules if task.get("type") == "schedule" and task.get("gcal_event_id")
    )
    queued = queue_google_deletes_for_task_rows(schedules, queue_delete_fn=queue_delete_fn)
    if queued != expected_google_deletes:
        return 0
    return int(task_repo.delete_all_tasks_by_date(date_str) or 0)
