# -*- coding: utf-8 -*-
"""Application usecases for routine management dialog."""

from __future__ import annotations

from calendar_app.application.common_status_usecases import (
    normalized_status,
    priority_display,
    status_display,
)
from calendar_app.domain.routine_cycle import cycle_display_name
from calendar_app.application.common_task_ops_usecases import (
    bulk_update_priority,
    bulk_update_status,
    collect_gcal_ids_for_delete,
    delete_tasks,
    inline_update_task,
)


def cycle_label(cycle_type: str | None) -> str:
    return cycle_display_name(cycle_type, scope="recurrence")


def build_table_payload(rows):
    payload = []
    for row in rows:
        raw_status = normalized_status(row.get("status"))
        payload.append(
            {
                "cells": [
                    row.get("name", ""),
                    cycle_label(row.get("cycle_type")),
                    row.get("location", ""),
                    row.get("assignee", ""),
                    priority_display(row.get("priority")),
                    row.get("deadline") or row.get("target_date", ""),
                    status_display(raw_status),
                ],
                "meta": {
                    "id": row["id"],
                    "status": raw_status,
                    "priority": row.get("priority", "normal"),
                },
            }
        )
    return payload
