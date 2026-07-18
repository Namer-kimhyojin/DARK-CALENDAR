"""Application usecases for directive management dialog."""

from __future__ import annotations

from calendar_app.application.common_status_usecases import (
    normalized_status,
    priority_display,
    status_display,
)


def build_table_payload(rows):
    payload = []
    for row in rows:
        row_id, content, receiver, priority, deadline, status = row
        norm_status = normalized_status(status)
        payload.append(
            {
                "cells": [
                    content,
                    receiver or "",
                    priority_display(priority),
                    deadline or "",
                    status_display(norm_status),
                ],
                "meta": {
                    "id": row_id,
                    "status": norm_status,
                    "priority": priority or "normal",
                },
            }
        )
    return payload


def build_trash_table_payload(rows):
    payload = []
    for row in rows:
        norm_status = normalized_status(row.get("status"))
        payload.append(
            {
                "cells": [
                    row.get("content", ""),
                    row.get("receiver_name", ""),
                    priority_display(row.get("priority")),
                    row.get("deadline", ""),
                    status_display(norm_status),
                ],
                "meta": {
                    "id": row.get("id"),  # archive id
                    "status": norm_status,
                    "priority": row.get("priority") or "normal",
                },
            }
        )
    return payload


def update_inline_field(repo, row_id: int, field: str, value: str):
    return repo.update_directive_field(row_id, field, value)


def bulk_update_status(repo, ids, new_status: str):
    return repo.bulk_update_directive_status(ids, new_status)


def bulk_update_priority(repo, ids, new_priority: str):
    return repo.bulk_update_directive_priority(ids, new_priority)


def delete_selected(repo, ids):
    return repo.delete_directives(ids)


def move_selected_to_trash(repo, ids, reason: str = "manual_trash"):
    moved = 0
    for directive_id in ids:
        if repo.move_directive_to_trash(directive_id, reason=reason):
            moved += 1
    return moved


def list_trashed(repo):
    return repo.list_directive_trash()


def restore_selected_from_trash(repo, archive_ids):
    restored = []
    for archive_id in archive_ids:
        new_id = repo.restore_directive_from_trash(archive_id)
        if new_id:
            restored.append(new_id)
    return restored


def purge_selected_from_trash(repo, archive_ids):
    purged = 0
    for archive_id in archive_ids:
        if repo.purge_directive_trash(archive_id):
            purged += 1
    return purged
