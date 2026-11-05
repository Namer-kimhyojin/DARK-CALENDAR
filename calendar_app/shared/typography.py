# -*- coding: utf-8 -*-
"""One point-based type ramp with logical-pixel values for Qt stylesheets."""

from dataclasses import dataclass
import math

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QFont, QFontMetricsF, QGuiApplication

DEFAULT_FONT_PT = 11


@dataclass(frozen=True)
class TypographyScale:
    body_pt: float
    caption_pt: float
    section_pt: float
    title_pt: float
    display_pt: float

    @property
    def body_px(self) -> int:
        return math.ceil(self.body_pt * 96 / 72)

    @property
    def caption_px(self) -> int:
        return math.ceil(self.caption_pt * 96 / 72)

    @property
    def section_px(self) -> int:
        return math.ceil(self.section_pt * 96 / 72)

    @property
    def title_px(self) -> int:
        return math.ceil(self.title_pt * 96 / 72)

    @property
    def display_px(self) -> int:
        return math.ceil(self.display_pt * 96 / 72)


def get_typography_scale(settings=None, *, base_pt=None) -> TypographyScale:
    """Read saved points without rewriting them or applying device-pixel ratio."""
    if base_pt is None:
        cfg = settings if settings is not None else QSettings("kimhyojin", "Dark Calendar")
        base_pt = cfg.value("font_size", DEFAULT_FONT_PT)
    try:
        body = float(base_pt)
    except (TypeError, ValueError, OverflowError):
        body = float(DEFAULT_FONT_PT)
    if not math.isfinite(body) or body <= 0:
        body = float(DEFAULT_FONT_PT)
    return TypographyScale(body, max(9.5, body - 1), body + 2, body + 5, body + 7)


def control_content_height(
    font_px: int, padding_y: int, *, minimum_outer: int = 38, settings=None
) -> int:
    """Fit text inside a QSS content box, allowing for padding and 1px borders."""
    text_height = math.ceil(font_px * 1.4)
    app = QGuiApplication.instance()
    if isinstance(app, QGuiApplication):
        font = QFont(app.font())
        if settings is not None:
            family = str(settings.value("font_family", font.family()) or font.family())
            font.setFamily(family)
        font.setPixelSize(max(1, int(font_px)))
        font.setWeight(QFont.Weight.DemiBold)
        text_height = math.ceil(QFontMetricsF(font).height())
    return max(text_height, int(minimum_outer) - 2 * int(padding_y) - 2)
