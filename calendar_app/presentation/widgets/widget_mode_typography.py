# -*- coding: utf-8 -*-
"""Semantic typography scale for the unified widget workspace."""

from dataclasses import dataclass

FONT_SIZE_KEY = "widget_mode_font_size"


@dataclass(frozen=True)
class WidgetTypography:
    """A compact type ramp derived from one user-facing size preference."""

    preference: int
    body: float
    title: float
    date: float
    control: float
    section: float
    secondary: float
    calendar: float


def _step(start: float, end: float, progress: float) -> float:
    return round(start + ((end - start) * progress), 1)


def read_widget_typography(settings) -> WidgetTypography:
    """Return a bounded, internally consistent type ramp for the widget UI.

    The legacy 10-18 preference is retained for settings compatibility, but it
    now scales every text role together instead of making agenda titles alone
    grow to 18pt.
    """

    try:
        preference = int(settings.value(FONT_SIZE_KEY, 12)) if settings is not None else 12
    except (TypeError, ValueError):
        preference = 12
    preference = max(10, min(18, preference))
    progress = (preference - 10) / 8
    return WidgetTypography(
        preference=preference,
        body=_step(9.0, 11.0, progress),
        # Agenda titles use weight, not an oversized font, for emphasis.
        title=_step(9.0, 11.0, progress),
        date=_step(9.5, 11.5, progress),
        control=_step(8.7, 10.7, progress),
        section=_step(8.4, 9.8, progress),
        secondary=_step(7.9, 9.3, progress),
        calendar=_step(8.8, 10.8, progress),
    )
