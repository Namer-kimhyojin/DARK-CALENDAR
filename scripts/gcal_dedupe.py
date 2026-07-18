import argparse
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from PyQt6.QtCore import QSettings

from calendar_app.app_paths import APP_NAME, APP_VENDOR
from calendar_app.infrastructure.google_sync.service import CalendarSyncService


@dataclass
class EventRow:
    event_id: str
    summary: str
    start_value: str
    end_value: str
    location: str
    description: str
    created: str
    updated: str
    is_all_day: bool


def _normalize_text(value: str) -> str:
    return (value or "").strip()


def _as_event_row(item: dict) -> EventRow:
    start_raw = item.get("start", {}) or {}
    end_raw = item.get("end", {}) or {}
    start_value = start_raw.get("dateTime") or start_raw.get("date") or ""
    end_value = end_raw.get("dateTime") or end_raw.get("date") or ""
    return EventRow(
        event_id=item.get("id", ""),
        summary=_normalize_text(item.get("summary", "")),
        start_value=start_value,
        end_value=end_value,
        location=_normalize_text(item.get("location", "")),
        description=_normalize_text(item.get("description", "")),
        created=item.get("created", "") or "",
        updated=item.get("updated", "") or "",
        is_all_day=("T" not in start_value),
    )


def _event_key(event: EventRow, strict: bool) -> tuple[str, str, str, int, str, str]:
    if strict:
        return (
            event.summary,
            event.start_value,
            event.end_value,
            int(event.is_all_day),
            event.location,
            event.description,
        )
    return (
        event.summary,
        event.start_value,
        event.end_value,
        int(event.is_all_day),
        "",
        "",
    )


def _group_duplicates(
    events: Iterable[EventRow], strict: bool
) -> dict[tuple[str, str, str, int, str, str], list[EventRow]]:
    groups: dict[tuple[str, str, str, int, str, str], list[EventRow]] = defaultdict(list)
    for event in events:
        if not event.event_id:
            continue
        groups[_event_key(event, strict)].append(event)
    return {k: v for k, v in groups.items() if len(v) > 1}


def _choose_keep_event(events: list[EventRow]) -> EventRow:
    # Prefer the oldest created event, then oldest updated, then stable ID ordering.
    return sorted(events, key=lambda e: (e.created or "9999", e.updated or "9999", e.event_id))[0]


def _fetch_all_events(
    service: CalendarSyncService, calendar_id: str, time_min: str, time_max: str
) -> list[EventRow]:
    page_token = None
    events: list[EventRow] = []
    while True:
        params = {
            "calendarId": calendar_id,
            "maxResults": 2500,
            "singleEvents": True,
            "showDeleted": False,
        }
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max
        if page_token:
            params["pageToken"] = page_token
        response = service.service.events().list(**params).execute()
        for item in response.get("items", []):
            events.append(_as_event_row(item))
        page_token = response.get("nextPageToken")
        if not page_token:
            return events


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find and optionally delete duplicate Google Calendar events."
    )
    parser.add_argument(
        "--calendar-id",
        default="",
        help="Calendar ID. Default: read from app settings, fallback primary",
    )
    parser.add_argument(
        "--timezone", default="Asia/Seoul", help="Timezone for service setup. Default: Asia/Seoul"
    )
    parser.add_argument(
        "--time-min", default="", help="RFC3339 start bound, e.g. 2025-01-01T00:00:00+09:00"
    )
    parser.add_argument(
        "--time-max", default="", help="RFC3339 end bound, e.g. 2026-12-31T23:59:59+09:00"
    )
    parser.add_argument(
        "--strict", action="store_true", help="Include location/description in duplicate key"
    )
    parser.add_argument(
        "--apply", action="store_true", help="Delete duplicate events (dry-run by default)"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt when used with --apply",
    )
    return parser.parse_args()


def _calendar_id_from_settings() -> str:
    try:
        settings = QSettings(APP_VENDOR, APP_NAME)
        return str(settings.value("gcal_calendar_id", "") or "").strip()
    except Exception:
        return ""


def main() -> int:
    args = _parse_args()
    calendar_id = (args.calendar_id or "").strip() or _calendar_id_from_settings() or "primary"

    service = CalendarSyncService(calendar_id=calendar_id, time_zone=args.timezone)
    if not service.authenticate(interactive=True):
        print("Authentication failed.")
        return 1

    if not service.service:
        print("Google Calendar service is not available.")
        return 1

    events = _fetch_all_events(service, calendar_id, args.time_min, args.time_max)
    dup_groups = _group_duplicates(events, strict=args.strict)

    print(f"Calendar ID: {calendar_id}")
    print(f"Events fetched: {len(events)}")
    print(f"Duplicate groups: {len(dup_groups)}")

    delete_targets: list[EventRow] = []
    for group_index, (_, group) in enumerate(
        sorted(dup_groups.items(), key=lambda kv: (kv[0][1], kv[0][0])), start=1
    ):
        keep = _choose_keep_event(group)
        to_delete = [event for event in group if event.event_id != keep.event_id]
        delete_targets.extend(to_delete)
        print(
            f"[{group_index}] keep={keep.event_id} "
            f"summary={keep.summary!r} start={keep.start_value} end={keep.end_value} "
            f"duplicates={len(to_delete)}"
        )

    print(f"Delete candidates: {len(delete_targets)}")

    if not args.apply:
        print("Dry-run mode. Use --apply to delete duplicates.")
        return 0

    if delete_targets and not args.yes:
        confirm = input("Delete duplicate events now? (y/N): ").strip().lower()
        if confirm not in {"y", "yes"}:
            print("Cancelled.")
            return 0

    deleted = 0
    failed = 0
    for target in delete_targets:
        try:
            service.service.events().delete(
                calendarId=calendar_id, eventId=target.event_id
            ).execute()
            deleted += 1
        except Exception as exc:
            failed += 1
            print(f"Delete failed: id={target.event_id} error={exc}")

    print(f"Deleted: {deleted}, Failed: {failed}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
