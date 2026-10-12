# -*- coding: utf-8 -*-
"""Resolve owning calendars for display without changing stored task records."""

from collections.abc import Mapping


def _text(value):
    return str(value or "").strip()


class CalendarVisibility:
    """Apply visibility to ownership, independently of fetching or save defaults."""

    def __init__(self, calendar_rows, primary_gcal_id="primary"):
        self.primary_gcal_id = _text(primary_gcal_id) or "primary"
        self.by_id = {_text(row.get("id")): row for row in calendar_rows}
        self.by_google_id = {}
        for key, row in self.by_id.items():
            if row.get("type") != "gcal" and not key.startswith("gcal::"):
                continue
            remote_id = self._google_id(row.get("gcal_calendar_id") or key)
            # The concrete row owns the setting, rather than a historical primary alias.
            if remote_id not in self.by_google_id or key == "gcal::" + remote_id:
                self.by_google_id[remote_id] = row

    def _google_id(self, value):
        key = _text(value)
        if key.startswith("gcal::"):
            key = key[len("gcal::") :]
        return self.primary_gcal_id if key == "primary" else key

    def _resolve(self, task: Mapping):
        stored_id = _text(task.get("calendar_id"))
        stored = self.by_id.get(stored_id)
        mode = _text(task.get("gcal_sync_mode"))
        source = _text(task.get("gcal_source_calendar_id"))
        subscription = _text(task.get("_subscription_calendar_id"))
        target = _text(task.get("gcal_target_calendar_id"))
        if mode == "local_owned" and stored_id not in {"", "primary", "gcal::primary"}:
            # A locally moved event may still retain its previous Google source until push.
            owned = stored or self.by_google_id.get(self._google_id(stored_id))
            return owned, bool(
                stored_id.startswith("gcal::")
                or stored_id in self.by_google_id
                or (owned and owned.get("type") == "gcal")
            )
        google = bool(
            stored_id.startswith("gcal::")
            or stored_id == "primary"
            or source
            or subscription
            or _text(task.get("gcal_event_id"))
            or _text(task.get("_gcal_event_id"))
            or mode == "remote_mirror"
            or (not stored_id and target)
            or (stored and stored.get("type") == "gcal")
            or stored_id in self.by_google_id
        )
        # A local-owned row's Google linkage is provenance/destination, not ownership.
        if (
            stored_id
            and not stored_id.startswith("gcal::")
            and stored_id != "primary"
            and stored_id not in self.by_google_id
        ):
            kind = (stored or {}).get("type")
            if (
                kind in {"ics", "outlook", "caldav", "shared"}
                or stored_id.startswith(("ics::", "outlook::", "caldav::", "shared::"))
                or not google
            ):
                return stored, False
        if not google:
            return stored, False

        candidates = [source, subscription, target]
        if (
            stored_id.startswith("gcal::")
            or stored_id == "primary"
            or stored_id in self.by_google_id
        ):
            candidates.append(stored_id)
        # A concrete source/target is more precise than an old "primary" alias.
        concrete = [key for key in candidates if key and key not in {"primary", "gcal::primary"}]
        aliases = [key for key in candidates if key in {"primary", "gcal::primary"}]
        for candidate in [*concrete, *aliases]:
            calendar = self.by_google_id.get(self._google_id(candidate))
            if calendar is not None:
                return calendar, True
        return stored, True

    def calendar_for_task(self, task):
        return self._resolve(task)[0]

    def is_visible(self, task, hide_gcal_items=False):
        calendar, google = self._resolve(task)
        if hide_gcal_items and google:
            return False
        value = (calendar or {}).get("is_visible")
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip().casefold() not in {"0", "false", "no", "off", ""}
        return bool(value)

    def filter_tasks(self, tasks, hide_gcal_items=False):
        return [task for task in tasks if self.is_visible(task, hide_gcal_items)]
