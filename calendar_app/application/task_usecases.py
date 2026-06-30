"""Task-oriented application usecases extracted from UI handlers."""

from __future__ import annotations

from collections.abc import Iterable
import json
import random
from typing import Any

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QColor

from calendar_app.application.common_task_ops_usecases import (
    collect_gcal_ids_for_delete as _collect_gcal_ids_for_delete,
)
from calendar_app.application.common_task_ops_usecases import (
    delete_tasks as _delete_tasks,
)
from calendar_app.shared.google_color_palette import ordered_palette_from_theme


def update_task_status(repo, task_id: int, status: str) -> bool:
    """Update unified task status."""
    return bool(repo.update_unified_task(task_id, {"status": status}))


def update_task_priority(repo, task_id: int, priority: str) -> bool:
    """Update unified task priority."""
    return bool(repo.update_unified_task(task_id, {"priority": priority}))


def rename_task(repo, task_id: int, new_name: str) -> dict[str, Any] | None:
    """Rename task and return updated task payload when changed."""
    normalized = (new_name or "").strip()
    if not normalized:
        return None

    task = repo.get_unified_task(task_id)
    if not task:
        return None

    if normalized == (task.get("name") or "").strip():
        return None

    if not repo.update_unified_task(task_id, {"name": normalized}):
        return None

    task["name"] = normalized
    return task


def _build_auto_color_palette(theme_color: str) -> list[str]:
    palette = ordered_palette_from_theme(theme_color)
    if palette:
        return palette
    c = QColor(theme_color or "#4da6ff")
    return [c.name() if c.isValid() else "#4da6ff"]


def _load_auto_color_history() -> list[str]:
    settings = QSettings("kimhyojin", "Dark Calendar")
    raw = settings.value("auto_color_recent_history", "[]")
    try:
        values = json.loads(str(raw))
    except Exception:
        values = []
    cleaned: list[str] = []
    for value in values:
        color = QColor(str(value))
        if color.isValid():
            cleaned.append(color.name())
    return cleaned


def _save_auto_color_history(history: Iterable[str]) -> None:
    settings = QSettings("kimhyojin", "Dark Calendar")
    cleaned: list[str] = []
    for value in history:
        color = QColor(str(value))
        if color.isValid():
            cleaned.append(color.name())
    settings.setValue("auto_color_recent_history", json.dumps(cleaned[-36:]))


def auto_assign_theme_colors(theme_color: str, count: int = 1) -> list[str]:
    """Return varied auto-tag colors centered on the theme color with repeat suppression."""
    count = max(1, int(count or 1))
    palette = _build_auto_color_palette(theme_color)
    history = _load_auto_color_history()
    usage_counts = {color: history.count(color) for color in palette}
    recent_positions = {
        color: max((idx for idx, value in enumerate(history) if value == color), default=-1)
        for color in palette
    }

    ranked = sorted(
        palette,
        key=lambda color: (
            usage_counts.get(color, 0),
            recent_positions.get(color, -1),
            random.random(),
        ),
    )

    selected: list[str] = []
    while len(selected) < count:
        for color in ranked:
            if len(selected) >= count:
                break
            if color in selected and len(selected) < len(ranked):
                continue
            selected.append(color)
        if len(ranked) == 1:
            break

    _save_auto_color_history([*history, *selected])
    return selected[:count]


def auto_assign_theme_color(theme_color: str) -> str:
    """Return one auto-tag color from the expanded theme palette."""
    colors = auto_assign_theme_colors(theme_color, 1)
    return colors[0] if colors else QColor(theme_color or "#4da6ff").name()


def update_task_bg_color(repo, task_id: int, color_hex: str | None) -> bool:
    """Update background color tag for unified task."""
    return bool(repo.update_unified_task(task_id, {"bg_color": color_hex}))


def update_directive_bg_color(repo, directive_id: int, color_hex: str | None) -> bool:
    """Update directive color tag."""
    return bool(repo.update_directive_bg_color(directive_id, color_hex))


def clear_task_alarm(repo, task_id: int) -> bool:
    """Clear alarm for unified task."""
    return bool(repo.update_unified_task(task_id, {"alarm_time": None}))


def resolve_delete_target_ids(selected_task_ids: Iterable[int], clicked_task_id: int) -> list[int]:
    """Resolve deletion targets from current selection and clicked task id."""
    selected = list(selected_task_ids or [])
    return selected if clicked_task_id in selected else [clicked_task_id]


def delete_tasks_by_ids(repo, task_ids: Iterable[int]) -> int:
    """Delete tasks by id list and return number of successful deletions."""
    return _delete_tasks(repo, task_ids)


def collect_gcal_ids_for_task_ids(repo, task_ids: Iterable[int]) -> list[str]:
    """Collect linked Google event ids from task ids."""
    return list(_collect_gcal_ids_for_delete(repo, task_ids))


def get_tasks_for_date(repo, date_str: str):
    """Return all tasks for date string."""
    return repo.get_all_tasks_by_date(date_str)


def collect_gcal_ids_from_tasks(tasks: Iterable[dict[str, Any]]) -> list[str]:
    """Collect linked Google event ids from task rows."""
    return [t.get("gcal_event_id") for t in tasks if t.get("gcal_event_id")]


def delete_tasks_on_date(repo, date_str: str) -> int:
    """Delete all tasks on date string and return deleted count."""
    return int(repo.delete_all_tasks_by_date(date_str) or 0)


def update_directive_status(repo, directive_id: int, new_status: str) -> bool:
    """Update directive status."""
    return bool(repo.update_directive_status(directive_id, new_status))


def update_directive_priority(repo, directive_id: int, priority: str) -> bool:
    """Update directive priority."""
    return bool(repo.update_directive_priority(directive_id, priority))


def toggle_checklist_item(repo, link_id: int) -> bool:
    """Toggle checklist item completion."""
    try:
        repo.toggle_checklist_item(link_id)
        return True
    except Exception:
        return False


def apply_task_basic_modification(repo, modified_data) -> bool:
    """Apply basic task edits in legacy task table and reset status to pending."""
    try:
        repo.update_task_basic(
            modified_data["id"],
            modified_data["name"],
            modified_data["deadline"],
            modified_data["end_date"],
        )
        repo.update_task_status(modified_data["id"], "pending")
        return True
    except Exception:
        return False


def resize_task_and_get_sync_payload(repo, task_id: int, minutes: int):
    """Resize task duration and return updated task payload for sync when available."""
    if not repo.update_unified_task_duration(task_id, minutes):
        return None
    return repo.get_unified_task(task_id)
