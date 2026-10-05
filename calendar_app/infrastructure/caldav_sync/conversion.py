# -*- coding: utf-8 -*-
"""iCalendar conversion; recurring resources and invitations are view-only."""

from datetime import UTC, date, datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event
import recurring_ical_events

from calendar_app.application.calendar_sync_contract import CalendarSyncError
from calendar_app.infrastructure.calendar_sync.repository import FIELDS

MAX_OCCURRENCES = 10000


def parse(data):
    try:
        calendar = Calendar.from_ical(data)
        events = calendar.walk("VEVENT")
        if (
            not events
            or len({str(e.get("UID", "")) for e in events}) != 1
            or not events[0].get("UID")
        ):
            raise ValueError
        if any(e.errors for e in events):
            raise ValueError
        return calendar
    except Exception as exc:
        raise CalendarSyncError("invalid_calendar_data") from exc


def identity(value):
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat() if value.tzinfo else value.isoformat()
    return value.isoformat()


def to_task_component(event, zone="Asia/Seoul"):
    try:
        start = event.decoded("DTSTART")
        end = (
            event.decoded("DTEND")
            if event.get("DTEND")
            else start
            + (
                event.decoded("DURATION")
                if event.get("DURATION")
                else timedelta(days=1)
                if type(start) is date
                else timedelta(hours=1)
            )
        )
        all_day = type(start) is date
        if (type(end) is date) != all_day or end < start:
            raise ValueError
        if all_day:
            deadline, finish = start.isoformat(), (end - timedelta(days=1)).isoformat()
        else:

            def local(value):
                return (
                    (value if value.tzinfo else value.replace(tzinfo=ZoneInfo(zone)))
                    .astimezone(ZoneInfo(zone))
                    .replace(tzinfo=None)
                    .isoformat(timespec="seconds")
                )

            deadline, finish = local(start), local(end)
        return {
            "name": str(event.get("SUMMARY", "")),
            "deadline": deadline,
            "end_date": finish,
            "all_day": int(all_day),
            "description": str(event.get("DESCRIPTION", "")),
            "location": str(event.get("LOCATION", "")),
        }
    except Exception as exc:
        raise CalendarSyncError("invalid_event_time") from exc


def records(href, etag, data, start=None, end=None, zone="Asia/Seoul"):
    calendar = parse(data)
    components = calendar.walk("VEVENT")
    recurring = len(components) > 1 or any(
        e.get("RRULE") or e.get("RDATE") or e.get("RECURRENCE-ID") for e in components
    )
    invited = any(e.get("ORGANIZER") or e.get("ATTENDEE") for e in components)
    if recurring:
        if start is None or end is None:
            raise CalendarSyncError("recurrence_window_required")
        # Bound work before the recurrence library can materialize a dense series.
        days = max(1, (end - start).total_seconds() / 86400 + 2)
        for component in components:
            rule = component.get("RRULE")
            if not rule:
                continue
            frequency = str(rule.get("FREQ", [""])[0]).upper()
            per_day = {"SECONDLY": 86400, "MINUTELY": 1440, "HOURLY": 24}.get(frequency, 1)
            estimate = days * per_day
            for key in ("BYHOUR", "BYMINUTE", "BYSECOND"):
                estimate *= max(1, len(rule.get(key, [])))
            if rule.get("COUNT"):
                estimate = min(estimate, int(rule["COUNT"][0]))
            if estimate > MAX_OCCURRENCES:
                raise CalendarSyncError("too_many_events")
        try:
            expanded = []
            for page in recurring_ical_events.of(calendar).paginate(
                100, earliest_end=start, latest_start=end
            ):
                expanded.extend(page)
                if len(expanded) > MAX_OCCURRENCES:
                    raise CalendarSyncError("too_many_events")
            components = expanded
        except CalendarSyncError:
            raise
        except Exception as exc:
            raise CalendarSyncError("invalid_recurrence") from exc
    result = []
    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    for event in components:
        rid = event.get("RECURRENCE-ID")
        if recurring and not rid:
            raise CalendarSyncError("invalid_recurrence")
        event_id = href + "#aircal-rid=" + quote(identity(rid.dt), safe="") if recurring else href
        result.append(
            {
                "id": event_id,
                "uid": str(event.get("UID", "")),
                "recurrence_id": identity(rid.dt) if rid else "",
                "etag": etag,
                "data": text,
                "task": to_task_component(event, zone),
                "zone": zone,
                "read_only": recurring or invited,
                "transaction_id": str(event.get("X-AIR-CALENDAR-TRANSACTION-ID", "")),
                "cancelled": str(event.get("STATUS", "")).upper() == "CANCELLED",
            }
        )
    return result


def apply_task(event, task, zone="Asia/Seoul", fields=FIELDS):
    if task.get("recurrence"):
        raise CalendarSyncError("recurrence_not_supported")
    if not str(task.get("name") or "").strip():
        raise CalendarSyncError("event_name_required")
    try:
        start = datetime.fromisoformat(task["deadline"])
        end = datetime.fromisoformat(task.get("end_date") or task["deadline"])
        if task.get("all_day"):
            start, end = start.date(), end.date() + timedelta(days=1)
        else:
            start = start if start.tzinfo else start.replace(tzinfo=ZoneInfo(zone))
            end = end if end.tzinfo else end.replace(tzinfo=ZoneInfo(zone))
            if not task.get("end_date"):
                end = start + timedelta(hours=1)
            start, end = start.astimezone(UTC), end.astimezone(UTC)
        if end <= start:
            raise ValueError
    except (ValueError, KeyError) as exc:
        raise CalendarSyncError("invalid_event_range") from exc
    values = {
        "SUMMARY": task["name"],
        "DESCRIPTION": task.get("description") or "",
        "LOCATION": task.get("location") or "",
        "DTSTART": start,
        "DTEND": end,
    }
    wanted = {"SUMMARY" if f == "name" else f.upper() for f in fields}
    if any(f in fields for f in ("deadline", "end_date", "all_day")):
        wanted |= {"DTSTART", "DTEND"}
        event.pop("DURATION", None)
    for key in wanted & values.keys():
        event.pop(key, None)
        event.add(key, values[key])
    event.pop("DTSTAMP", None)
    event.add("DTSTAMP", datetime.now(UTC))
    event.pop("LAST-MODIFIED", None)
    event.add("LAST-MODIFIED", datetime.now(UTC))


def new_calendar(task, transaction, zone="Asia/Seoul"):
    calendar = Calendar()
    calendar.add("PRODID", "-//Air Calendar//CalDAV//EN")
    calendar.add("VERSION", "2.0")
    event = Event()
    event.add("UID", transaction + "@air-calendar")
    event.add("X-AIR-CALENDAR-TRANSACTION-ID", transaction)
    apply_task(event, task, zone)
    calendar.add_component(event)
    return calendar.to_ical()


def edited_calendar(task, remote, zone="Asia/Seoul"):
    if remote.get("read_only"):
        raise CalendarSyncError("event_read_only")
    calendar = parse(remote["data"])
    event = calendar.walk("VEVENT")[0]
    changed = [f for f in FIELDS if (task.get(f) or "") != (remote["task"].get(f) or "")]
    apply_task(event, task, zone, changed)
    sequence = int(event.get("SEQUENCE", 0)) + 1
    event.pop("SEQUENCE", None)
    event.add("SEQUENCE", sequence)
    return calendar.to_ical()
