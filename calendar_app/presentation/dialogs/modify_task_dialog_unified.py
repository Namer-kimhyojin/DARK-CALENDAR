"""Thin compatibility wrapper — modify dialog now delegates to UnifiedTaskDialog."""

from calendar_app.infrastructure.db import task_repo
from calendar_app.infrastructure.google_sync import queue_task_sync_to_google  # noqa: F401
from calendar_app.presentation.dialogs.task_dialog_unified import UnifiedTaskDialog


class UnifiedModifyTaskDialog(UnifiedTaskDialog):
    """Thin compatibility wrapper.

    All create/modify logic lives in UnifiedTaskDialog.
    Pass ``task_id`` to activate modify mode.
    """

    def __init__(self, task_id, parent=None):
        task_data = task_repo.get_unified_task(task_id)
        task_type = (task_data or {}).get("type", "schedule")
        super().__init__(parent=parent, task_type=task_type, task_id=task_id)
