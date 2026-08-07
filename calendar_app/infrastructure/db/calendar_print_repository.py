# -*- coding: utf-8 -*-
"""Read-only queries used by calendar printing."""

from __future__ import annotations

from collections.abc import Sequence

from calendar_app.infrastructure.db.calendar_repo import list_calendars
from calendar_app.infrastructure.db.db_repository_unified import get_connection


def _canonical_gcal_source(row: dict) -> str:
    source = str(
        row.get("gcal_source_calendar_id")
        or row.get("gcal_target_calendar_id")
        or row.get("calendar_id")
        or "primary"
    ).strip()
    return source.removeprefix("gcal::") or "primary"


def _dedupe_rows(rows: Sequence[dict]) -> list[dict]:
    """Keep one stable row for each mirrored Google event."""
    passthrough: list[dict] = []
    gcal_rows: dict[tuple[str, str], dict] = {}
    for row in rows:
        event_id = str(row.get("gcal_event_id") or "").strip()
        if not event_id:
            passthrough.append(row)
            continue
        key = (_canonical_gcal_source(row), event_id)
        current = gcal_rows.get(key)
        if current is None:
            gcal_rows[key] = row
            continue
        current_remote = str(current.get("gcal_sync_mode") or "") == "remote_mirror"
        candidate_remote = str(row.get("gcal_sync_mode") or "") == "remote_mirror"
        current_id = int(current.get("id") or 0)
        candidate_id = int(row.get("id") or 0)
        if (candidate_remote and not current_remote) or (
            candidate_remote == current_remote and candidate_id > current_id
        ):
            gcal_rows[key] = row

    result = [*passthrough, *gcal_rows.values()]
    result.sort(
        key=lambda row: (
            str(row.get("deadline") or row.get("target_date") or ""),
            int(row.get("id") or 0),
        )
    )
    return result


def load_calendar_print_source(
    start_date: str,
    end_date: str,
    calendar_ids: Sequence[str] | None = None,
) -> dict[str, list[dict]]:
    """Load a complete stored-data snapshot for an inclusive date range.

    Unlike the screen query this function can include calendars that are
    currently hidden when the user explicitly selects them in the print dialog.
    No network access or mutation occurs here.
    """
    calendars = list_calendars(include_inactive=False)
    conn = get_connection()
    if conn is None:
        return {"rows": [], "calendars": calendars}

    filters = [
        "(t.type='schedule' OR "
        "(COALESCE(t.gcal_sync_mode, '')='remote_mirror' "
        "AND COALESCE(trim(t.gcal_event_id), '') != ''))",
        "date(COALESCE(t.deadline, t.target_date)) <= date(?)",
        "date(COALESCE(t.end_date, t.deadline, t.target_date)) >= date(?)",
    ]
    params: list[str] = [str(end_date), str(start_date)]
    selected = tuple(str(item).strip() for item in (calendar_ids or ()) if str(item).strip())
    if selected:
        placeholders = ",".join("?" for _ in selected)
        filters.append(
            "(t.calendar_id IS NULL "
            f"OR t.calendar_id IN ({placeholders}) "
            f"OR ('gcal::' || COALESCE(NULLIF(trim(t.gcal_source_calendar_id), ''), "
            f"NULLIF(trim(t.gcal_target_calendar_id), ''), 'primary')) IN ({placeholders}))"
        )
        params.extend(selected)
        params.extend(selected)

    query = f"""
        SELECT t.*
        FROM unified_task t
        WHERE {" AND ".join(filters)}
        ORDER BY COALESCE(t.deadline, t.target_date) ASC, t.id ASC
    """
    cur = conn.cursor()
    cur.execute(query, tuple(params))
    rows = [dict(row) for row in cur.fetchall()]
    return {"rows": _dedupe_rows(rows), "calendars": calendars}
