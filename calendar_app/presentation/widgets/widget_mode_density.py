# -*- coding: utf-8 -*-
"""List density changes spacing, never the user's font or layout preferences."""

from dataclasses import dataclass

DENSITY_KEY = "widget_mode_density"


@dataclass(frozen=True)
class WidgetDensity:
    key: str
    label: str
    vertical_margin: int
    row_spacing: int
    title_padding: int


DENSITIES = (
    WidgetDensity("compact", "촘촘하게", 4, 4, 4),
    WidgetDensity("standard", "표준", 6, 6, 8),
    WidgetDensity("comfortable", "여유롭게", 12, 10, 14),
)


def read_widget_density(settings) -> WidgetDensity:
    key = str(settings.value(DENSITY_KEY, "standard")) if settings is not None else "standard"
    return next((density for density in DENSITIES if density.key == key), DENSITIES[1])
