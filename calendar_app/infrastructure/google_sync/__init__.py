# -*- coding: utf-8 -*-
"""Google Calendar sync package with lazy public exports."""

from importlib import import_module

_LAZY_EXPORTS = {
    "handle_task_dropped": ("engine", "handle_task_dropped"),
    "sync_google_calendar": ("engine", "sync_google_calendar"),
    "delete_task_from_google": ("helpers", "delete_task_from_google"),
    "queue_task_delete_from_google": ("helpers", "queue_task_delete_from_google"),
    "queue_task_sync_to_google": ("helpers", "queue_task_sync_to_google"),
    "resolve_app_context": ("helpers", "resolve_app_context"),
    "sync_task_to_google": ("helpers", "sync_task_to_google"),
    "cleanup_duplicate_gcal_rows": ("repository", "cleanup_duplicate_gcal_rows"),
    "delete_task_by_gcal_id": ("repository", "delete_task_by_gcal_id"),
    "get_all_gcal_tasks_map": ("repository", "get_all_gcal_tasks_map"),
    "insert_gcal_event_to_unified": ("repository", "insert_gcal_event_to_unified"),
    "update_task_from_gcal": ("repository", "update_task_from_gcal"),
    "CalendarSyncService": ("service", "CalendarSyncService"),
    "GoogleEvent": ("service", "GoogleEvent"),
}
_LAZY_SUBMODULES = {"common", "engine", "helpers", "repository", "service"}

__all__ = [
    "CalendarSyncService",
    "GoogleEvent",
    "cleanup_duplicate_gcal_rows",
    "delete_task_by_gcal_id",
    "delete_task_from_google",
    "get_all_gcal_tasks_map",
    "handle_task_dropped",
    "insert_gcal_event_to_unified",
    "queue_task_delete_from_google",
    "queue_task_sync_to_google",
    "resolve_app_context",
    "sync_google_calendar",
    "sync_task_to_google",
    "update_task_from_gcal",
]


def __getattr__(name: str):
    if name in _LAZY_SUBMODULES:
        value = import_module(f"{__name__}.{name}")
    else:
        target = _LAZY_EXPORTS.get(name)
        if target is None:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
        module_name, attr_name = target
        value = getattr(import_module(f"{__name__}.{module_name}"), attr_name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__) | _LAZY_SUBMODULES)
