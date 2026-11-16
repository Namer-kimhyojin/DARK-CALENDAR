# -*- coding: utf-8 -*-
"""One point-based type ramp with logical-pixel values for Qt stylesheets."""

from dataclasses import dataclass
import math

from PyQt6.QtCore import QLocale, QSettings
from PyQt6.QtGui import QFont, QFontMetricsF, QGuiApplication

DEFAULT_FONT_PT = 11
# The UI font used when the user never chose one. A Korean font here would draw
# Vietnamese, Turkish, Chinese, Japanese and Arabic text with mixed fallback glyphs.
DEFAULT_UI_FONT = "Segoe UI"
# Windows CJK fonts by UI language. Han characters take the shapes of the first
# listed font that has them, so Japanese and Chinese readers get their own forms.
_KOREAN_UI_FONT = "Malgun Gothic"
_CJK_UI_FONTS = {
    "ja": ("Yu Gothic UI", "Meiryo"),
    "zh-CN": ("Microsoft YaHei UI",),
    "zh-TW": ("Microsoft JhengHei UI",),
}
# Saved points are preserved, but no real font is this large; such values are
# corrupt settings that would overflow Qt's int pixel sizes.
_MAX_VALID_FONT_PT = 4096


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
    if not math.isfinite(body) or body <= 0 or body > _MAX_VALID_FONT_PT:
        body = float(DEFAULT_FONT_PT)
    return TypographyScale(body, max(9.5, body - 1), body + 2, body + 5, body + 7)


def _cjk_language(locale: QLocale | None = None) -> str:
    loc = locale if locale is not None else QLocale()
    language = loc.language()
    if language == QLocale.Language.Japanese:
        return "ja"
    if language == QLocale.Language.Chinese:
        traditional = loc.script() == QLocale.Script.TraditionalHanScript
        return "zh-TW" if traditional else "zh-CN"
    if language == QLocale.Language.Korean:
        return "ko"
    return ""


def cjk_fallback_families(locale: QLocale | None = None) -> tuple[str, ...]:
    """CJK fonts in the order the UI language expects (default: Qt's locale).

    Korean and non-CJK languages keep Malgun Gothic first, as before.
    """
    return (*_CJK_UI_FONTS.get(_cjk_language(locale), ()), _KOREAN_UI_FONT)


def ui_font_families(primary: str | None, locale: QLocale | None = None) -> list[str]:
    """``primary`` followed by the UI language's CJK fallbacks and the default UI font."""
    families = [str(primary or DEFAULT_UI_FONT), *cjk_fallback_families(locale), DEFAULT_UI_FONT]
    return list(dict.fromkeys(families))


def ui_text_families(locale: QLocale | None = None) -> list[str]:
    """Families for UI-language text drawn before the saved font applies (the splash).

    CJK languages lead with their own font (Korean keeps Malgun Gothic); other
    languages use the default UI font.
    """
    if _cjk_language(locale):
        return list(dict.fromkeys([*cjk_fallback_families(locale), DEFAULT_UI_FONT]))
    return ui_font_families(DEFAULT_UI_FONT, locale)


def fitted_text_width(metrics, texts, *, minimum: int, maximum: int, padding: int = 0) -> int:
    """Width that shows the widest of ``texts`` in full, within ``minimum``..``maximum``.

    ``minimum`` is the width the layout was designed with (the Korean UI), so text
    that already fits keeps it. Past ``maximum`` the caller elides the text.
    """
    widest = max((metrics.horizontalAdvance(str(text or "")) for text in texts), default=0)
    return max(int(minimum), min(int(maximum), math.ceil(widest + padding)))


def font_scaled_width(metrics, width: int) -> int:
    """``width``, chosen for the default 11pt UI font, grown in step with ``metrics``' font.

    Width caps keep their value at the default size; a larger saved font size
    (Appearance allows up to 24pt) raises them so the same text still fits.
    """
    reference = QFontMetricsF(QFont(DEFAULT_UI_FONT, DEFAULT_FONT_PT)).height()
    if reference <= 0:
        return int(width)
    return max(int(width), round(width * metrics.height() / reference))


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
