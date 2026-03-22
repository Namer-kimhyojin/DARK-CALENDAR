# -*- coding: utf-8 -*-
"""Shared delete flows for task removal + Google delete queue handling."""

from __future__ import annotations

from typing import Callable, Iterable

from calendar_app.application.common_task_ops_usecases import delete_tasks as _delete_tasks


QueueDeleteFn = Callable[[str, int | None, str | None], object]


def queue_google_deletes_for_task_ids(task_repo, task_ids: Iterable[int], *, queue_delete_fn: QueueDeleteFn) -> int:
    """Queue Google event deletes for a list of local task ids."""
    queued = 0
    for task_id in task_ids or []:
        task = task_repo.get_unified_task(task_id)
        if not task:
            continue
        gcal_event_id = task.get("gcal_event_id")
        if not gcal_event_id:
            continue
        queue_delete_fn(gcal_event_id, int(task_id), None)
        queued += 1
    return queued


def queue_google_deletes_for_task_rows(tasks, *, queue_delete_fn: QueueDeleteFn) -> int:
    """Queue Google event deletes from preloaded task rows."""
    queued = 0
    for task in tasks or []:
        gcal_event_id = task.get("gcal_event_id")
        if not gcal_event_id:
            continue
        task_id = task.get("id")
        queue_delete_fn(gcal_event_id, int(task_id) if task_id else None, None)
        queued += 1
    return queued


def queue_google_deletes_for_refs(gcal_refs, *, queue_delete_fn: QueueDeleteFn) -> int:
    """Queue Google event deletes from purge refs dict list."""
    queued = 0
    for ref in gcal_refs or []:
        gcal_event_id = ref.get("gcal_event_id")
        if not gcal_event_id:
            continue
        queue_delete_fn(gcal_event_id, None, ref.get("gcal_calendar_id"))
        queued += 1
    return queued


def delete_tasks_with_google_queue(task_repo, task_ids: Iterable[int], *, queue_delete_fn: QueueDeleteFn) -> int:
    """Queue Google deletes first, then delete local tasks."""
    queue_google_deletes_for_task_ids(task_repo, task_ids, queue_delete_fn=queue_delete_fn)
    return _delete_tasks(task_repo, task_ids)


def delete_tasks_on_date_with_google_queue(search_repo, task_repo, date_str: str, *, queue_delete_fn: QueueDeleteFn) -> int:
    """Queue Google deletes for all tasks on date, then delete them locally."""
    tasks = search_repo.get_all_tasks_by_date(date_str)
    queue_google_deletes_for_task_rows(tasks, queue_delete_fn=queue_delete_fn)
    return int(task_repo.delete_all_tasks_by_date(date_str) or 0)

