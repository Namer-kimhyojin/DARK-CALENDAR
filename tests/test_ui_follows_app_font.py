# -*- coding: utf-8 -*-
"""User-visible text follows the user's chosen UI font.

The app may name a fixed family only where that is the design:
- a *default* used when the saved font is missing or blank,
- a *candidate list* the user's preset picks from (first installed wins),
- *monospace* code/keycap text,
- the splash, which is drawn before the saved font is applied.
Anything else is a hard-coded font that ignores the user's setting.
"""

from pathlib import Path
import re

from PyQt6.QtCore import QLocale
from PyQt6.QtGui import QFont, QFontInfo
from PyQt6.QtWidgets import QApplication
import pytest

from calendar_app.presentation import drag_drop_manager
from calendar_app.shared.typography import (
    DEFAULT_UI_FONT,
    ui_font_families,
    ui_text_families,
)

ROOT = Path(__file__).resolve().parents[1] / "calendar_app"

# (path relative to calendar_app, line text fragment) -> reason.
ALLOWED = {
    ("infrastructure/runtime/keyboard_shortcuts.py", 'font-family:"Consolas"'): "keycap monospace",
    (
        "presentation/dialogs/away_settings_dialog.py",
        "font-family: 'Consolas'",
    ): "monospace source editor",
    (
        "presentation/theme/style_builder.py",
        'family="Outfit',
    ): "default argument; callers pass the saved font",
    (
        "presentation/widgets/weather_scene.py",
        'self.family = "Segoe UI"',
    ): "default; callers pass font_family()",
    (
        "presentation/widgets/weather_scene.py",
        'family="Segoe UI"',
    ): "default; callers pass the saved font",
}

LITERAL_FAMILY = re.compile(
    r"""font-family\s*:\s*['"]?[A-Za-z]"""
    r"""|QFont\(\s*['"][A-Za-z]"""
    r"""|setFamily\(\s*['"][A-Za-z]"""
    r"""|FONT_FAMILY\s*=\s*['"][A-Za-z]"""
    r"""|self\.family\s*=\s*['"][A-Za-z]"""
    r"""|family\s*=\s*['"][A-Za-z]"""
    r"""|setFamilies\(\s*\[\s*['"][A-Za-z]"""
)


def _is_allowed(relative: str, line: str) -> bool:
    return any(relative == path and fragment in line for path, fragment in ALLOWED)


def test_no_unlisted_hard_coded_ui_font_family():
    offenders = []
    for path in sorted(ROOT.rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="strict").splitlines(), 1
        ):
            if not LITERAL_FAMILY.search(line) or line.lstrip().startswith("#"):
                continue
            if not _is_allowed(relative, line):
                offenders.append(f"{relative}:{number}: {line.strip()[:90]}")
    assert not offenders, (
        "Hard-coded UI font family that ignores the user's setting "
        "(use the app font, or add a documented allowance):\n" + "\n".join(offenders)
    )


def test_command_palette_search_box_uses_the_app_font():
    from calendar_app.presentation.widgets.command_palette_runtime import (
        _build_command_palette_stylesheet,
        _command_palette_style_bundle,
    )

    QApplication.instance() or QApplication([])
    sheet = _build_command_palette_stylesheet(_command_palette_style_bundle())
    assert "QLineEdit" in sheet
    assert "font-family" not in sheet


def test_drag_card_text_follows_the_application_font():
    app = QApplication.instance() or QApplication([])
    original = QFont(app.font())
    try:
        app.setFont(QFont("Arial", 11))
        for size, weight in ((11, QFont.Weight.DemiBold), (8, QFont.Weight.Normal)):
            font = drag_drop_manager._drag_font(size, weight)
            assert font.family() == app.font().family()
            assert font.pointSize() == size and font.weight() == weight
            assert QFontInfo(font).family()
    finally:
        app.setFont(original)


def test_saved_font_defaults_use_the_shared_default_ui_font():
    """A missing font_family once fell back to Malgun Gothic after any theme change,
    while startup used Segoe UI, so Vietnamese, Chinese, Japanese and Arabic text
    switched to mixed fallback glyphs."""
    literal_default = re.compile(r"""value\(\s*['"]font_family['"]\s*,\s*['"][A-Za-z]""")
    offenders = []
    for path in sorted(ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="strict")
        for number, line in enumerate(text.splitlines(), 1):
            if literal_default.search(line):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{number}: {line.strip()}")
    assert not offenders, "Use DEFAULT_UI_FONT for the font_family default:\n" + "\n".join(
        offenders
    )
    assert DEFAULT_UI_FONT == "Segoe UI"


_KO = QLocale(QLocale.Language.Korean, QLocale.Country.SouthKorea)
_JA = QLocale(QLocale.Language.Japanese, QLocale.Country.Japan)
_ZH_CN = QLocale(QLocale.Language.Chinese, QLocale.Country.China)
_ZH_TW = QLocale(QLocale.Language.Chinese, QLocale.Country.Taiwan)
_EN = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)


@pytest.mark.parametrize(
    "locale,expected",
    [
        (_KO, ["Segoe UI", "Malgun Gothic"]),
        (_EN, ["Segoe UI", "Malgun Gothic"]),
        (_JA, ["Segoe UI", "Yu Gothic UI", "Meiryo", "Malgun Gothic"]),
        (_ZH_CN, ["Segoe UI", "Microsoft YaHei UI", "Malgun Gothic"]),
        (_ZH_TW, ["Segoe UI", "Microsoft JhengHei UI", "Malgun Gothic"]),
    ],
)
def test_cjk_fallbacks_follow_the_ui_language(locale, expected):
    """Han characters take the shapes of the first CJK font, so Japanese and
    Chinese dates must not be drawn with the Korean font first."""
    assert ui_font_families(DEFAULT_UI_FONT, locale) == expected
    assert ui_font_families("Arial", locale) == ["Arial", *expected[1:], "Segoe UI"]


@pytest.mark.parametrize(
    "locale,first",
    [
        (_KO, "Malgun Gothic"),
        (_JA, "Yu Gothic UI"),
        (_ZH_TW, "Microsoft JhengHei UI"),
        (_EN, "Segoe UI"),
    ],
)
def test_splash_text_font_follows_the_ui_language(locale, first):
    from calendar_app.presentation.splash_screen import SplashScreen

    QApplication.instance() or QApplication([])
    original = QLocale()
    QLocale.setDefault(locale)
    try:
        assert ui_text_families()[0] == first
        assert SplashScreen._text_font(14).families()[0] == first
    finally:
        QLocale.setDefault(original)


def test_keydeck_legend_fallbacks_follow_the_ui_language():
    from calendar_app.presentation.widgets.keydeck.renderer import legend_font

    QApplication.instance() or QApplication([])
    original = QLocale()
    try:
        QLocale.setDefault(_KO)
        assert legend_font(12).families() == [
            "Segoe UI Variable Text",
            "Segoe UI",
            "Malgun Gothic",
            "Apple SD Gothic Neo",
            "Noto Sans CJK KR",
        ]
        QLocale.setDefault(_JA)
        families = legend_font(12).families()
        assert families.index("Yu Gothic UI") < families.index("Malgun Gothic")
    finally:
        QLocale.setDefault(original)
