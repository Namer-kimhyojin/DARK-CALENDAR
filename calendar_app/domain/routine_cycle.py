"""Shared routine cycle constants and label helpers."""

from __future__ import annotations

from calendar_app.infrastructure.i18n import t

# Sort order used by routine list/group views.
CYCLE_ORDER = {
    "single": 0,
    "daily": 1,
    "weekly": 2,
    "monthly": 3,
    "quarterly": 4,
    "half_yearly": 5,
    "yearly": 6,
}


_RECURRENCE_LABEL_META = {
    "single": ("dialog.recurrence.single", "단일업무"),
    "daily": ("recurrence.daily", "일간"),
    "weekly": ("recurrence.weekly", "주간"),
    "monthly": ("recurrence.monthly", "월간"),
    "quarterly": ("recurrence.quarterly", "분기"),
    "half_yearly": ("recurrence.half_yearly", "반기"),
    "yearly": ("recurrence.yearly", "연간"),
}

_PANEL_LABEL_META = {
    "single": ("panel.cycle.single", "[Single]"),
    "daily": ("panel.cycle.daily", "[Daily]"),
    "weekly": ("panel.cycle.weekly", "[Weekly]"),
    "monthly": ("panel.cycle.monthly", "[Monthly]"),
    "quarterly": ("panel.cycle.quarterly", "[Quarterly]"),
    "half_yearly": ("panel.cycle.half_yearly", "[Half-yearly]"),
    "yearly": ("panel.cycle.yearly", "[Yearly]"),
}


def normalize_cycle_type(cycle_type: str | None) -> str:
    return str(cycle_type or "").strip().lower()


def cycle_order_value(cycle_type: str | None, default: int = 9) -> int:
    return CYCLE_ORDER.get(normalize_cycle_type(cycle_type), default)


def cycle_display_name(cycle_type: str | None, *, scope: str = "recurrence") -> str:
    cycle = normalize_cycle_type(cycle_type)
    if not cycle:
        return ""

    if scope == "panel":
        key, fallback = _PANEL_LABEL_META.get(cycle, ("", ""))
    else:
        key, fallback = _RECURRENCE_LABEL_META.get(cycle, ("", ""))

    if not key:
        return cycle
    return t(key, fallback)
