"""Compatibility wrapper for Google sync helper functions."""

import sys

from calendar_app.infrastructure.google_sync import helpers as _impl
from calendar_app.infrastructure.google_sync.helpers import *  # noqa: F401,F403

_persist_gcal_event_id = _impl._persist_gcal_event_id
_mark_task_synced = _impl._mark_task_synced
_is_gcal_enabled = _impl._is_gcal_enabled
SyncTaskResult = _impl.SyncTaskResult

# Legacy tests patch this module as "gcal_sync_helpers".
sys.modules.setdefault("gcal_sync_helpers", sys.modules[__name__])
