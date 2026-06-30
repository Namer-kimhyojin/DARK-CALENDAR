"""Shared task mutation helpers for task/routine management usecases."""

from __future__ import annotations


def inline_update_task(repo, row_id: int, field: str, value: str | None):
    repo.update_unified_task(row_id, {field: value or None})
    return repo.get_unified_task(row_id)


def bulk_update_status(repo, task_ids, new_status: str):
    updated = []
    for task_id in task_ids:
        repo.update_unified_task(task_id, {"status": new_status})
        task = repo.get_unified_task(task_id)
        if task:
            updated.append(task)
    return updated


def bulk_update_priority(repo, task_ids, new_priority: str):
    for task_id in task_ids:
        repo.update_unified_task(task_id, {"priority": new_priority})


def collect_gcal_ids_for_delete(repo, task_ids):
    ids = []
    for task_id in task_ids:
        task = repo.get_unified_task(task_id)
        if task and task.get("gcal_event_id"):
            ids.append(task["gcal_event_id"])
    return ids


def delete_tasks(repo, task_ids):
    deleted = 0
    for task_id in task_ids:
        if repo.delete_unified_task(task_id):
            deleted += 1
    return deleted
