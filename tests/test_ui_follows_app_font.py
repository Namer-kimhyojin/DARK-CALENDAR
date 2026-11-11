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

from PyQt6.QtGui import QFont, QFontInfo
from PyQt6.QtWidgets import QApplication

from calendar_app.presentation import drag_drop_manager

ROOT = Path(__file__).resolve().parents[1] / "calendar_app"

# (path relative to calendar_app, line text fragment) -> reason.
ALLOWED = {
    ("bootstrap.py", 'family = "Segoe UI"'): "default when the saved font is missing",
    ("bootstrap.py", 'settings.value("font_family", "Segoe UI")'): "default when missing",
    ("infrastructure/runtime/keyboard_shortcuts.py", 'font-family:"Consolas"'): "keycap monospace",
    (
        "presentation/dialogs/away_settings_dialog.py",
        "font-family: 'Consolas'",
    ): "monospace source editor",
    ("presentation/splash_screen.py", "FONT_FAMILY ="): "splash, drawn before the saved font",
    ("presentation/splash_screen.py", 'QFont("Segoe UI"'): "splash, drawn before the saved font",
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
    (
        "presentation/widgets/widget_graphics.py",
        'self.family = "Segoe UI"',
    ): "default; callers pass font_family()",
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
