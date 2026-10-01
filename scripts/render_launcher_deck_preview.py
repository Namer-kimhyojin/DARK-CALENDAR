# -*- coding: utf-8 -*-
"""Render KeyDeck (launcher deck v4) contact sheets and a studio capture for visual QA.

Usage:
    .venv\\Scripts\\python.exe scripts/render_launcher_deck_preview.py [--lang en] [--out DIR]

Run with the default Windows platform plugin: the offscreen plugin has no font
database, so Hangul legends would not render.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QPointF, QSettings  # noqa: E402
from PyQt6.QtGui import QColor, QPainter, QPixmap  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

from calendar_app.infrastructure.i18n import i18n, resolve_locale_file_path  # noqa: E402
from calendar_app.presentation.widgets.keydeck import model  # noqa: E402
from calendar_app.presentation.widgets.keydeck.renderer import (  # noqa: E402
    KeyDeckRenderer,
    KeyVisualState,
)


class _PreviewOwner(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("codex_qa", "keydeck_preview")
        self.settings.clear()


def _use_language(lang: str) -> None:
    path = resolve_locale_file_path(lang, prefer_user=False)
    if path is None:
        return
    data = i18n._load_locale_json(str(path), lang)
    i18n.lang = lang
    i18n.translations = data
    i18n.bundled_translations = {}
    i18n.fallback_translations = data


def _sheet(template_id: str, scale: float = 1.0) -> QPixmap:
    renders = []
    for theme in model.THEMES:
        deck = model.build_template_deck(template_id, theme.theme_id)
        keys = deck["pages"][0]["keys"]
        renderer = KeyDeckRenderer()
        renderer.set_deck(deck, 0, scale=scale)
        states = {
            keys[0]["id"]: KeyVisualState(travel=1.0, led=1.0),
            keys[1]["id"]: KeyVisualState(hover=True, travel=-0.07),
        }
        renders.append(renderer.render_pixmap(states, dpr=2.0))
    columns = 4
    cell_w = max(pixmap.width() for pixmap in renders) // 2 + 16
    cell_h = max(pixmap.height() for pixmap in renders) // 2 + 16
    rows = (len(renders) + columns - 1) // columns
    sheet = QPixmap(cell_w * columns * 2, cell_h * rows * 2)
    sheet.setDevicePixelRatio(2.0)
    sheet.fill(QColor("#5b6472"))
    painter = QPainter(sheet)
    for index, pixmap in enumerate(renders):
        painter.drawPixmap(
            QPointF((index % columns) * cell_w + 8, (index // columns) * cell_h + 8), pixmap
        )
    painter.end()
    return sheet


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lang", default="ko")
    parser.add_argument("--out", default="artifacts/launcher-deck")
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication([])
    _use_language(args.lang)
    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)
    for template_id, *_rest in model.TEMPLATES:
        _sheet(template_id).save(str(output_dir / f"{template_id}.png"), "PNG")

    from calendar_app.presentation.widgets.keydeck.studio import KeyDeckStudioDialog
    from calendar_app.presentation.widgets.overlay_launcher_deck import OverlayLauncherDeckWidget

    owner = _PreviewOwner()
    widget = OverlayLauncherDeckWidget(owner)
    widget._set("enabled", True)
    widget.apply_initial_settings()
    app.processEvents()
    widget.grab().save(str(output_dir / "overlay.png"), "PNG")
    keys = widget.deck()["pages"][0]["keys"]
    studio = KeyDeckStudioDialog(widget.deck(), widget, key_id=keys[0]["id"])
    studio.resize(1260, 800)
    studio.show()
    app.processEvents()
    for index, name in enumerate(("action", "insert", "legend", "cap")):
        studio.key_inspector.tabs.setCurrentIndex(index)
        app.processEvents()
        studio.grab().save(str(output_dir / f"studio_{name}.png"), "PNG")
    studio.canvas.select([])
    app.processEvents()
    studio.grab().save(str(output_dir / "studio_deck.png"), "PNG")
    studio._dirty = False
    studio.close()
    widget.close()
    owner.settings.clear()
    print(f"KeyDeck previews written to {output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
