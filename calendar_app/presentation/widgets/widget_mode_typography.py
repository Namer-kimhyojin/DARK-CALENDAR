# -*- coding: utf-8 -*-
"""Semantic typography scale for the unified widget workspace."""

from dataclasses import dataclass

from calendar_app.shared.typography import get_typography_scale

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
    except (TypeError, ValueError, OverflowError):
        preference = 12
    preference = max(10, min(18, preference))
    progress = (preference - 10) / 8
    # This preference belongs to the workspace, independently of large clock
    # faces and user-authored text in individual overlay widgets.
    scale = get_typography_scale(base_pt=_step(10.5, 12.5, progress))
    return WidgetTypography(
        preference=preference,
        body=scale.body_pt,
        # Agenda titles use weight, not an oversized font, for emphasis.
        title=scale.body_pt,
        date=scale.section_pt,
        control=scale.body_pt,
        section=scale.body_pt,
        secondary=scale.caption_pt,
        calendar=scale.body_pt,
    )
