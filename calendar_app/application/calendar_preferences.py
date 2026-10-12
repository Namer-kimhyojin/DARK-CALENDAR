# -*- coding: utf-8 -*-
"""Shared calendar preference operations for main-screen and connection controls."""

from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


def _update_google_compatibility_target(calendar, settings):
    """Keep old integrations compatible without turning a local default into Google."""
    if settings is None or not calendar or calendar.get("type") != "gcal":
        return
    google_id = str(calendar.get("gcal_calendar_id") or "").strip()
    if google_id and hasattr(settings, "setValue"):
        try:
            settings.setValue("gcal_calendar_id", google_id)
        except Exception:
            # The DB is authoritative; an optional compatibility write must not
            # misreport a successfully persisted calendar choice as a failure.
            logger.exception("Failed to update the legacy Google calendar preference")


def set_default_calendar(calendar_id, settings=None, *, repository) -> bool:
    """Select a writable default without moving any existing events."""
    repo = repository
    if not repo.set_calendar_default(calendar_id):
        return False
    _update_google_compatibility_target(repo.get_calendar(calendar_id), settings)
    return True


@dataclass(frozen=True)
class CalendarImportSelectionResult:
    success: bool
    default_changed: bool = False
    default_calendar: dict | None = None


def set_google_calendar_import_selection(selection, settings=None, *, repository):
    """Save one import draft and report an automatic default fallback to the UI."""
    repo = repository
    before = repo.get_default_calendar()
    if not repo.set_google_calendar_import_selection(selection):
        return CalendarImportSelectionResult(False, default_calendar=before)
    after = repo.get_default_calendar()
    changed = (before or {}).get("id") != (after or {}).get("id")
    if changed:
        _update_google_compatibility_target(after, settings)
    if settings is not None and hasattr(settings, "setValue"):
        settings.setValue("gcal_import_selection_configured", True)
    return CalendarImportSelectionResult(True, changed, after)
