"""Application usecases for end-of-day summary dialogs."""

from __future__ import annotations

from calendar_app.application import review_usecases


def _load_events_for_day(report_repo, today_str: str):
    if hasattr(report_repo, "get_calendar_events"):
        return list(report_repo.get_calendar_events(today_str) or [])
    return []


def _load_directives_for_day(directive_repo, today_str: str):
    if hasattr(directive_repo, "get_directives_by_date"):
        rows = directive_repo.get_directives_by_date(today_str) or []
        return [
            (
                row.get("id"),
                row.get("content"),
                row.get("status"),
                row.get("receiver_name"),
                row.get("deadline"),
                row.get("memo"),
                row.get("bg_color"),
                row.get("priority"),
            )
            for row in rows
        ]

    rows = []
    if hasattr(directive_repo, "get_recent_directives"):
        for row in directive_repo.get_recent_directives(limit=200) or []:
            deadline = row[4] if len(row) > 4 else None
            if str(deadline or "")[:10] == today_str:
                rows.append(row)
    return rows


def get_eod_summary(report_repo, directive_repo, today_str: str):
    """Load EOD summary payload with date-scoped directives and combined counts."""
    return {
        "events": _load_events_for_day(report_repo, today_str),
        "directives": _load_directives_for_day(directive_repo, today_str),
        "summary": review_usecases.build_daily_review(
            report_repo,
            today_str,
            directive_repo=directive_repo,
        ),
    }
