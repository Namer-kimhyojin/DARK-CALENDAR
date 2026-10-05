# -*- coding: utf-8 -*-
"""Single-event/occurrence conversion with explicit all-day end semantics."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from .auth import OutlookError


def _datetime(text, zone):
    try:
        value = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
        return value if value.tzinfo else value.replace(tzinfo=ZoneInfo(zone))
    except (ValueError, KeyError) as exc:
        raise OutlookError("invalid_event_time") from exc


def to_graph(task, local_zone="Asia/Seoul"):
    if task.get("recurrence"):
        raise OutlookError("recurrence_not_supported")
    if not str(task.get("name") or "").strip():
        raise OutlookError("event_name_required")
    start = _datetime(task.get("deadline"), local_zone)
    all_day = bool(task.get("all_day"))
    end = _datetime(task.get("end_date") or task.get("deadline"), local_zone)
    if all_day:
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = end.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        # All-day Graph events must use midnight in the same timezone.
        graph_zone = local_zone
        start_text, end_text = (
            start.replace(tzinfo=None).isoformat(),
            end.replace(tzinfo=None).isoformat(),
        )
    else:
        if end <= start:
            if task.get("end_date"):
                raise OutlookError("invalid_event_range")
            end = start + timedelta(hours=1)
        graph_zone = "UTC"
        start_text, end_text = [
            v.astimezone(UTC).replace(tzinfo=None).isoformat() for v in (start, end)
        ]
    if end <= start:
        raise OutlookError("invalid_event_range")
    return {
        "subject": task["name"],
        "start": {"dateTime": start_text, "timeZone": graph_zone},
        "end": {"dateTime": end_text, "timeZone": graph_zone},
        "isAllDay": all_day,
        "body": {"contentType": "text", "content": task.get("description") or ""},
        "location": {"displayName": task.get("location") or ""},
    }


def from_graph(event, local_zone="Asia/Seoul"):
    all_day = bool(event.get("isAllDay"))
    start = _datetime(event["start"]["dateTime"], "UTC")
    end = _datetime(event["end"]["dateTime"], "UTC")
    zone = ZoneInfo(local_zone)
    if all_day:
        # Graph UTC preference expresses original midnight as a UTC instant.
        start_text = start.astimezone(zone).date().isoformat()
        end_text = (end.astimezone(zone).date() - timedelta(days=1)).isoformat()
    else:
        start_text, end_text = [
            v.astimezone(zone).replace(tzinfo=None).isoformat(timespec="seconds")
            for v in (start, end)
        ]
    # bodyPreview is plain text; do not interpret external HTML in task widgets.
    return {
        "name": event.get("subject") or "(Untitled)",
        "deadline": start_text,
        "end_date": end_text,
        "all_day": int(all_day),
        "description": (
            (event.get("body") or {}).get("content")
            if str((event.get("body") or {}).get("contentType", "")).lower() == "text"
            else event.get("bodyPreview")
        )
        or "",
        "location": (event.get("location") or {}).get("displayName") or "",
    }
