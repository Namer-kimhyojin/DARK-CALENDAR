# -*- coding: utf-8 -*-
"""Bounded, validated and atomic read-only ICS subscription snapshots."""

from datetime import UTC, date, datetime, timedelta
from http.client import HTTPException
import logging
import sqlite3
import time
import urllib.error
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from calendar_app.application.calendar_sync_contract import CalendarSyncError
from calendar_app.infrastructure.ics.processing_budget import processing_budget
from calendar_app.infrastructure.ics.subscription_http import open_subscription
from calendar_app.infrastructure.ics.subscriptions import normalize_subscription_url

logger = logging.getLogger("IcsFetcher")
MAX_FEED_BYTES = 8 * 1024 * 1024
MAX_EVENTS = 10000
MAX_FETCH_SECONDS = 45
MAX_PROCESS_SECONDS = 10


def _read_feed(response, cancelled, deadline):
    """Check cancellation between socket reads, including slowly streamed feeds."""
    headers = getattr(response, "headers", None) or {}
    status = getattr(response, "status", None)
    if status is None and hasattr(response, "getcode"):
        status = response.getcode()
    # A subscription is a full snapshot. A range response must never determine
    # which cached events are absent, even if its body ends with END:VCALENDAR.
    if status == 206 or headers.get("Content-Range") is not None:
        raise CalendarSyncError("ics_fetch_failed")
    declared_length = headers.get("Content-Length")
    if declared_length is not None:
        try:
            declared_length = int(declared_length)
            if declared_length < 0:
                raise ValueError
        except (TypeError, ValueError):
            raise CalendarSyncError("network_unavailable") from None
        if declared_length > MAX_FEED_BYTES:
            raise CalendarSyncError("response_too_large")
    payload = bytearray()
    read = getattr(response, "read1", response.read)
    while len(payload) <= MAX_FEED_BYTES:
        _check(cancelled)
        if time.monotonic() >= deadline:
            raise CalendarSyncError("network_unavailable")
        chunk = read(min(65536, MAX_FEED_BYTES + 1 - len(payload)))
        _check(cancelled)
        if time.monotonic() >= deadline:
            raise CalendarSyncError("network_unavailable")
        if not chunk:
            # HTTPResponse.read1() can reach EOF on a truncated body without
            # raising IncompleteRead, unlike a single unbounded read().
            if declared_length is not None and len(payload) != declared_length:
                raise CalendarSyncError("network_unavailable")
            return bytes(payload)
        payload.extend(chunk)
        if len(payload) > MAX_FEED_BYTES:
            raise CalendarSyncError("response_too_large")
    raise CalendarSyncError("response_too_large")


def _now():
    return datetime.now(UTC)


def _try_import_icalendar():
    try:
        import icalendar

        return icalendar
    except ImportError:
        return None


def _check(cancelled):
    if cancelled():
        raise CalendarSyncError("cancelled")


def _validate_timezones(event):
    """An unresolved TZID is not a floating time; retain the previous snapshot."""
    for key in ("DTSTART", "DTEND", "RECURRENCE-ID", "RDATE", "EXDATE"):
        properties = event.get(key)
        if properties is None:
            continue
        if not isinstance(properties, list):
            properties = [properties]
        for prop in properties:
            if not prop.params.get("TZID"):
                continue
            for item in getattr(prop, "dts", [prop]):
                values = item.dt if isinstance(item.dt, tuple) else (item.dt,)
                if any(isinstance(value, datetime) and value.tzinfo is None for value in values):
                    raise CalendarSyncError("invalid_calendar_timezone")


def _event_identity(value):
    if not isinstance(value, date):
        raise CalendarSyncError("invalid_recurrence")
    return (
        value.astimezone(UTC).isoformat()
        if isinstance(value, datetime) and value.tzinfo
        else value.isoformat()
    )


def _snapshot(raw, icalendar, zone, cancelled):
    """Validate the whole feed before any database write or missing-event deletion."""
    with processing_budget(cancelled, MAX_PROCESS_SECONDS):
        return _snapshot_rows(raw, icalendar, zone, cancelled)


def _snapshot_rows(raw, icalendar, zone, cancelled):
    """Build a complete snapshot; a processing timeout must discard every row."""
    envelope = raw.strip().removeprefix(b"\xef\xbb\xbf").upper()
    if not envelope.startswith(b"BEGIN:VCALENDAR") or not envelope.endswith(b"END:VCALENDAR"):
        raise CalendarSyncError("invalid_calendar_data")
    from calendar_app.infrastructure.calendar_sync.ical_parser import parse_calendar

    calendar = parse_calendar(raw)
    if calendar.name != "VCALENDAR" or any(c.errors for c in calendar.walk()):
        raise CalendarSyncError("invalid_calendar_data")
    # iTIP requests, replies and cancellations describe selected events, not
    # a full subscription snapshot. Their omissions cannot authorize deletion.
    method = calendar.get("METHOD")
    if method is not None and str(method).upper() != "PUBLISH":
        raise CalendarSyncError("invalid_calendar_data")
    components = calendar.walk("VEVENT")
    if len(components) > MAX_EVENTS:
        raise CalendarSyncError("too_many_events")
    groups = {}
    for event in components:
        _check(cancelled)
        uid = str(event.get("UID", "")).strip()
        if not uid:
            raise CalendarSyncError("invalid_calendar_data")
        _validate_timezones(event)
        if str(event.get("STATUS", "")).upper() != "CANCELLED":
            _event_dates(event, zone)
        groups.setdefault(uid, []).append(event)

    now = _now()
    start, end = now - timedelta(days=120), now + timedelta(days=400)
    rows = {}
    for uid, events in groups.items():
        _check(cancelled)
        recurring = any(
            e.get("RRULE") or e.get("RDATE") or e.get("EXDATE") or e.get("RECURRENCE-ID")
            for e in events
        )
        if len(events) > 1 and not recurring:
            raise CalendarSyncError("duplicate_remote_event")
        if recurring:
            masters = [e for e in events if not e.get("RECURRENCE-ID")]
            identities = [
                _event_identity(e["RECURRENCE-ID"].dt) for e in events if e.get("RECURRENCE-ID")
            ]
            if len(masters) > 1 or len(set(identities)) != len(identities):
                raise CalendarSyncError("duplicate_remote_event")
            if masters and masters[0].get("DTSTART") is not None:
                original = masters[0]["DTSTART"].dt
                for event in events:
                    rid = event.get("RECURRENCE-ID")
                    if rid is None:
                        continue
                    value = rid.dt
                    if (type(value) is date) != (type(original) is date) or (
                        isinstance(value, datetime)
                        and isinstance(original, datetime)
                        and (value.tzinfo is None) != (original.tzinfo is None)
                    ):
                        raise CalendarSyncError("invalid_recurrence")
            # Reject dense recurrences before the library materializes their occurrences.
            for event in events:
                rule = event.get("RRULE")
                if not rule:
                    continue
                if "COUNT" in rule and "UNTIL" in rule:
                    raise CalendarSyncError("invalid_recurrence")
                frequency = str(rule.get("FREQ", [""])[0]).upper()
                per_day = {"SECONDLY": 86400, "MINUTELY": 1440, "HOURLY": 24}.get(frequency, 1)
                interval = int(rule.get("INTERVAL", [1])[0])
                if interval < 1:
                    raise CalendarSyncError("invalid_recurrence")
                window_days = (end - start).days + 2
                estimate = (window_days * per_day + interval - 1) // interval
                # Filters bound the units per day independently of INTERVAL. Taking
                # the smaller bound avoids counting a sparse filter as an expansion,
                # without dividing twice when the filter aligns with the interval.
                filtering = {
                    "SECONDLY": (("BYHOUR", 24), ("BYMINUTE", 60), ("BYSECOND", 60)),
                    "MINUTELY": (("BYHOUR", 24), ("BYMINUTE", 60)),
                    "HOURLY": (("BYHOUR", 24),),
                }.get(frequency, ())
                filtered_per_day = per_day
                for key, cardinality in filtering:
                    values = rule.get(key)
                    if values:
                        filtered_per_day = filtered_per_day // cardinality * len(set(values))
                estimate = min(estimate, window_days * filtered_per_day)
                # Only finer units expand a rule's density.
                expanding = {
                    "SECONDLY": (),
                    "MINUTELY": ("BYSECOND",),
                    "HOURLY": ("BYMINUTE", "BYSECOND"),
                }.get(frequency, ("BYHOUR", "BYMINUTE", "BYSECOND"))
                for key in expanding:
                    estimate *= max(1, len(rule.get(key, [])))
                if "COUNT" in rule:
                    counts = rule["COUNT"]
                    if len(counts) != 1 or int(counts[0]) < 1:
                        raise CalendarSyncError("invalid_recurrence")
                    estimate = min(estimate, int(counts[0]))
                if estimate > MAX_EVENTS:
                    raise CalendarSyncError("too_many_events")
            import recurring_ical_events

            series = icalendar.Calendar()
            for component in calendar.subcomponents:
                if component.name == "VTIMEZONE":
                    series.add_component(component)
            for event in events:
                series.add_component(event)
            expanded = []
            for page in recurring_ical_events.of(series).paginate(
                100, earliest_end=start, latest_start=end
            ):
                _check(cancelled)
                expanded.extend(page)
                if len(expanded) + len(rows) > MAX_EVENTS:
                    raise CalendarSyncError("too_many_events")
            events = expanded
        for event in events:
            _check(cancelled)
            if str(event.get("STATUS", "")).upper() == "CANCELLED":
                continue
            event_id = uid
            if recurring:
                rid = event.get("RECURRENCE-ID")
                if not rid:
                    raise CalendarSyncError("invalid_recurrence")
                identity = _event_identity(rid.dt)
                event_id += "#aircal-rid=" + quote(identity, safe="")
            if event_id in rows:
                raise CalendarSyncError("duplicate_remote_event")
            deadline, finish, all_day = _event_dates(event, zone, expanded=recurring)
            rows[event_id] = (
                str(event.get("SUMMARY", "")),
                deadline,
                finish,
                int(all_day),
                str(event.get("DESCRIPTION", "")) or None,
                str(event.get("LOCATION", "")) or None,
            )
    return rows


def _event_dates(event, zone, *, expanded=False):
    start = event.get("DTSTART")
    end = event.get("DTEND")
    duration = event.get("DURATION")
    if start is None or (end is not None and duration is not None):
        raise CalendarSyncError("invalid_event_time")
    value = start.dt
    if not isinstance(value, date):
        raise CalendarSyncError("invalid_event_time")
    if duration is not None:
        delta = duration.dt
        if not isinstance(delta, timedelta) or delta <= timedelta(0):
            raise CalendarSyncError("invalid_event_time")
        if type(value) is date and (delta.seconds or delta.microseconds or not delta.days):
            raise CalendarSyncError("invalid_event_time")
        from icalendar import vDDDTypes

        end = vDDDTypes(value + delta)
    if end is not None:
        finish = end.dt
        if (type(finish) is date) != (type(value) is date) or finish < value:
            raise CalendarSyncError("invalid_event_time")
        # The recurrence library adds a zero-length DTEND to valid point events
        # that originally have neither DTEND nor DURATION. Only allow it there.
        if finish == value and (type(value) is date or not expanded):
            raise CalendarSyncError("invalid_event_time")
    return _parse_dt(start, end, zone)


def fetch_and_sync(
    calendar_id: str, ics_url: str, local_zone: str | None = None, cancelled=lambda: False
) -> tuple[int, int, str | None]:
    """Return counts only after committing an entire validated subscription snapshot."""
    try:
        fetch_url = normalize_subscription_url(ics_url)
    except ValueError:
        return 0, 0, "invalid_subscription_url"
    try:
        zone = ZoneInfo(local_zone) if local_zone else None
    except (ZoneInfoNotFoundError, ValueError):
        return 0, 0, "invalid_timezone"
    icalendar = _try_import_icalendar()
    if not icalendar:
        return 0, 0, "dependency_unavailable"
    try:
        _check(cancelled)
        deadline = time.monotonic() + MAX_FETCH_SECONDS
        with open_subscription(fetch_url, cancelled=cancelled, deadline=deadline) as resp:
            raw = _read_feed(resp, cancelled, deadline)
        _check(cancelled)
        if len(raw) > MAX_FEED_BYTES:
            raise CalendarSyncError("response_too_large")
    except CalendarSyncError as exc:
        return 0, 0, str(exc)
    except urllib.error.HTTPError as exc:
        # Never expose the URL, response body or reason (feeds can contain access keys).
        if exc.code in {401, 403}:
            code = "ics_access_denied"
        elif exc.code in {404, 410}:
            code = "ics_not_found"
        elif exc.code == 429:
            code = "ics_rate_limited"
        elif 500 <= exc.code <= 599:
            code = "ics_server_error"
        else:
            code = "ics_fetch_failed"
        exc.close()
        logger.warning("ICS HTTP failure for calendar %s (%s)", calendar_id, code)
        return 0, 0, code
    except (urllib.error.URLError, HTTPException, OSError):
        logger.warning("ICS fetch failed for calendar %s", calendar_id)
        return 0, 0, "network_unavailable"
    except Exception:
        logger.warning("ICS fetch failed for calendar %s", calendar_id)
        return 0, 0, "operation_failed"
    try:
        rows = _snapshot(raw, icalendar, zone, cancelled)
    except CalendarSyncError as exc:
        return 0, 0, str(exc)
    except ImportError:
        return 0, 0, "dependency_unavailable"
    except Exception:
        logger.warning("ICS parse failed for calendar %s", calendar_id)
        return 0, 0, "invalid_calendar_data"

    from calendar_app.infrastructure.db.database_unified import db_manager

    try:
        conn = db_manager.get_connection()
    except Exception:
        logger.warning("ICS database unavailable for calendar %s", calendar_id)
        return 0, 0, "operation_failed"
    if not conn:
        return 0, 0, "operation_failed"
    saved = False
    try:
        _check(cancelled)
        # A savepoint also preserves unrelated work if the caller has an open transaction.
        conn.execute("SAVEPOINT ics_snapshot")
        saved = True
        # Obtain the writer lock before checking subscription identity/activation.
        conn.execute(
            "UPDATE calendar SET ics_last_fetched=ics_last_fetched WHERE id=?", (calendar_id,)
        )
        source = conn.execute(
            "SELECT type,is_active,ics_url FROM calendar WHERE id=?", (calendar_id,)
        ).fetchone()
        if not source or source[0] != "ics" or not source[1] or source[2] != ics_url:
            raise CalendarSyncError("calendar_access_lost")
        upserted = deleted = 0
        for uid, values in rows.items():
            _check(cancelled)
            cursor = conn.execute(
                """
                INSERT INTO unified_task
                    (name,type,calendar_id,deadline,end_date,all_day,description,location,
                     gcal_event_id,gcal_source_calendar_id,gcal_sync_mode,gcal_dirty,status,created_at,updated_at)
                VALUES (?,'schedule',?,?,?,?,?,?,?,?,'remote_mirror',0,'in_progress',
                        datetime('now','localtime'),datetime('now','localtime'))
                ON CONFLICT(
                    COALESCE(NULLIF(trim(gcal_source_calendar_id),''),NULLIF(trim(gcal_target_calendar_id),''),'primary'),
                    gcal_event_id
                ) WHERE gcal_event_id IS NOT NULL AND gcal_event_id != ''
                DO UPDATE SET name=excluded.name,deadline=excluded.deadline,end_date=excluded.end_date,
                    all_day=excluded.all_day,description=excluded.description,location=excluded.location,
                    updated_at=excluded.updated_at
                WHERE unified_task.calendar_id=excluded.calendar_id AND unified_task.gcal_sync_mode='remote_mirror'
            """,
                (values[0], calendar_id, *values[1:], uid, calendar_id),
            )
            if cursor.rowcount != 1:
                # A protected local-owned row with the same remote identity was
                # not updated. Do not delete other cached events or mark success.
                raise CalendarSyncError("duplicate_remote_event")
            upserted += cursor.rowcount
        existing = conn.execute(
            """
            SELECT id,gcal_event_id FROM unified_task WHERE calendar_id=? AND gcal_source_calendar_id=?
              AND gcal_sync_mode='remote_mirror' AND gcal_event_id IS NOT NULL
        """,
            (calendar_id, calendar_id),
        ).fetchall()
        for task_id, uid in existing:
            _check(cancelled)
            if uid not in rows:
                conn.execute("DELETE FROM unified_task WHERE id=?", (task_id,))
                deleted += 1
        conn.execute(
            "UPDATE calendar SET ics_last_fetched=? WHERE id=?", (_now().isoformat(), calendar_id)
        )
        _check(cancelled)
        conn.execute("RELEASE SAVEPOINT ics_snapshot")
        saved = False
    except Exception as exc:
        if saved:
            try:
                conn.execute("ROLLBACK TO SAVEPOINT ics_snapshot")
                conn.execute("RELEASE SAVEPOINT ics_snapshot")
            except sqlite3.Error:
                # SQLite can already have rolled back on disk/I/O errors.
                logger.warning("ICS savepoint already unavailable for calendar %s", calendar_id)
        code = str(exc) if isinstance(exc, CalendarSyncError) else "operation_failed"
        logger.warning("ICS snapshot not applied for calendar %s (%s)", calendar_id, code)
        return 0, 0, code
    logger.info("ICS sync [%s]: upserted=%s, deleted=%s", calendar_id, upserted, deleted)
    return upserted, deleted, None


def _parse_dt(dtstart, dtend, zone=None) -> tuple[str | None, str | None, bool]:
    """Keep floating wall time and all-day dates; convert aware timestamps for display."""
    if dtstart is None:
        return None, None, False
    val = dtstart.dt
    if isinstance(val, date) and not isinstance(val, datetime):
        end_str = (dtend.dt - timedelta(days=1)).strftime("%Y-%m-%d") if dtend is not None else None
        return val.strftime("%Y-%m-%d"), end_str, True
    if isinstance(val, datetime):
        if val.tzinfo is not None:
            val = val.astimezone(zone).replace(tzinfo=None)
        end_str = None
        if dtend is not None:
            ev = dtend.dt
            if ev.tzinfo is not None:
                ev = ev.astimezone(zone).replace(tzinfo=None)
            end_str = ev.strftime("%Y-%m-%d %H:%M")
        return val.strftime("%Y-%m-%d %H:%M"), end_str, False
    return None, None, False


def sync_all_ics_calendars() -> dict[str, tuple[int, int, str | None]]:
    from calendar_app.infrastructure.db.calendar_repo import list_calendars

    return {
        cal["id"]: fetch_and_sync(cal["id"], cal["ics_url"])
        for cal in list_calendars(include_inactive=False)
        if cal["type"] == "ics" and cal.get("ics_url")
    }
