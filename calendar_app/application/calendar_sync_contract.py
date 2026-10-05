# -*- coding: utf-8 -*-
"""Provider-neutral operations required by the calendar synchronization engine.

Adapters normalize remote event IDs, revision tags and task payloads. A future
CalDAV adapter supplies these operations without importing Microsoft/Google code.
"""

from typing import Protocol


class CalendarSyncError(RuntimeError):
    """Safe diagnostic code suitable for the UI; excludes credentials."""


class RemoteCalendarError(CalendarSyncError):
    def __init__(self, status: int):
        self.status = status
        super().__init__(f"remote_http_{status}")


class CalendarProvider(Protocol):
    def events(self, calendar: str, start: str, end: str) -> list[dict]: ...
    def event(self, event_id: str) -> dict: ...
    def create(self, calendar: str, payload: dict, transaction_id: str) -> dict: ...
    def update(self, event_id: str, payload: dict, etag: str) -> dict: ...
    def delete(self, event_id: str, etag: str) -> dict: ...
    def to_task(self, event: dict, local_zone: str) -> dict: ...
    def from_task(self, task: dict, local_zone: str) -> dict: ...
    def edit_payload(self, task: dict, remote: dict, local_zone: str) -> dict: ...
