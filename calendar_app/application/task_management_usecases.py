"""Application usecases for schedule task management dialog."""

from __future__ import annotations

from calendar_app.application.common_status_usecases import (
    normalized_status,
    priority_display,
    status_display,
)


def build_table_payload(rows):
    payload = []
    for row in rows:
        raw_status = normalized_status(row.get("status"))
        payload.append(
            {
                "cells": [
                    row.get("name", ""),
                    row.get("deadline", ""),
                    row.get("location", ""),
                    row.get("assignee", ""),
                    priority_display(row.get("priority")),
                    status_display(raw_status),
                ],
                "meta": {
                    "id": row["id"],
                    "status": raw_status,
                },
            }
        )
    return payload


def build_trash_table_payload(rows):
    payload = []
    for row in rows:
        raw_status = normalized_status(row.get("status"))
        payload.append(
            {
                "cells": [
                    row.get("name", ""),
                    row.get("deadline", ""),
                    row.get("location", ""),
                    row.get("assignee", ""),
                    priority_display(row.get("priority")),
                    status_display(raw_status),
                ],
                "meta": {
                    "id": row["id"],  # archive id
                    "status": raw_status,
                },
            }
        )
    return payload


def move_tasks_to_trash(repo, task_ids, reason: str = "manual_trash"):
    moved = 0
    for task_id in task_ids:
        if repo.move_task_to_trash(task_id, reason=reason):
            moved += 1
    return moved


def list_trashed_tasks(repo, task_type: str = "schedule"):
    return repo.list_task_trash(task_type=task_type)


def restore_trashed_tasks(repo, archive_ids):
    restored_task_ids = []
    for archive_id in archive_ids:
        task_id = repo.restore_task_from_trash(archive_id)
        if task_id:
            restored_task_ids.append(task_id)
    return restored_task_ids


def purge_trashed_tasks(repo, archive_ids):
    purged = 0
    gcal_refs = []
    for archive_id in archive_ids:
        result = repo.purge_task_trash(archive_id)
        if result is None:
            continue
        purged += 1
        if isinstance(result, dict):
            gcal_event_id = result.get("gcal_event_id")
            gcal_calendar_id = result.get("gcal_calendar_id")
        else:
            gcal_event_id = result
            gcal_calendar_id = None
        if gcal_event_id:
            gcal_refs.append(
                {
                    "gcal_event_id": gcal_event_id,
                    "gcal_calendar_id": gcal_calendar_id,
                }
            )
    return purged, gcal_refs
