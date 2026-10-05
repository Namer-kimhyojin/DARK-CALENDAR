# -*- coding: utf-8 -*-
"""Common user actions; provider-specific engine entry points stay compatible."""

from PyQt6.QtCore import pyqtSlot


class CalendarSyncActionsMixin:
    def wake_gcal_sync(self):
        """Keep legacy callers while waking all writable, enabled services."""
        coordinator = getattr(self, "_calendar_sync_coordinator", None)
        if not coordinator or getattr(self, "_is_shutting_down", False):
            return
        coordinator.schedule_local_change(include_google=True)

    def wake_calendar_sync(self):
        """Google uses its existing individual push queue after edits."""
        coordinator = getattr(self, "_calendar_sync_coordinator", None)
        if coordinator:
            coordinator.schedule_local_change()

    def sync_calendars(self, checked=False, provider=None):
        if getattr(self, "_is_shutting_down", False):
            return []
        coordinator = getattr(self, "_calendar_sync_coordinator", None)
        if not coordinator:
            return []
        started = coordinator.sync(provider)
        if not started and not any(s["busy"] for s in coordinator.states.values()):
            self.open_calendar_sync_hub()
        return started

    @pyqtSlot()
    def update_sync_status(self, refresh_issue_count=True):
        coordinator = getattr(self, "_calendar_sync_coordinator", None)
        if coordinator:
            coordinator.refresh(refresh_issue_count)
        else:
            super().update_sync_status(refresh_issue_count)

    def _sync_ics_calendars(self):
        coordinator = getattr(self, "_calendar_sync_coordinator", None)
        if coordinator:
            return coordinator.sync_ics()
        return None
