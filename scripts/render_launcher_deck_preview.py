# -*- coding: utf-8 -*-
"""Render representative launcher-deck arrays for visual QA."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QWidget

from calendar_app.infrastructure.i18n import i18n, resolve_locale_file_path
from calendar_app.presentation.widgets.launcher_deck_dialog import (
    KeycapAppearanceDialog,
    KeycapInteractionDialog,
    LauncherDeckEditorDialog,
)
from calendar_app.presentation.widgets.launcher_deck_model import (
    DECK_TEMPLATES,
    new_key,
    template_deck,
)
from calendar_app.presentation.widgets.launcher_keycap_assets import KEYCAP_ASSETS
from calendar_app.presentation.widgets.overlay_launcher_deck import OverlayLauncherDeckWidget


class _PreviewOwner(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("codex_qa", "launcher_deck_preview")
        self.settings.clear()


def main() -> int:
    app = QApplication.instance() or QApplication([])
    app.setFont(QFont("Malgun Gothic", 9))
    english_path = resolve_locale_file_path("en", prefer_user=False)
    if english_path is not None:
        english = i18n._load_locale_json(str(english_path), "en")
        i18n.lang = "en"
        i18n.translations = english
        i18n.bundled_translations = {}
        i18n.fallback_translations = english
    output_dir = Path("artifacts/launcher-deck")
    output_dir.mkdir(parents=True, exist_ok=True)
    owner = _PreviewOwner()

    for template_id, _key, _fallback, _factory in DECK_TEMPLATES:
        owner.settings.clear()
        widget = OverlayLauncherDeckWidget(owner)
        widget._store_deck(template_deck(template_id))
        widget._rebuild_keys()
        widget._apply_and_resize()
        widget.show()
        widget.adjustSize()
        app.processEvents()
        widget.grab().save(str(output_dir / f"{template_id}.png"), "PNG")
        widget.close()

    owner.settings.clear()
    custom_deck = template_deck("mixed_4x3")
    assets = ("spark", "orbit", "grid", "waves", "circuit", "blossom", "pixels", "constellation")
    icons = ("star", "bolt", "calendar", "play", "folder", "globe", "plus", "search")
    colors = ("#6f9fe6ff", "#b593ecff", "#ef9b72ff", "#52c9b5ff")
    for index, key in enumerate(custom_deck["keys"]):
        key["asset_id"] = assets[index % len(assets)]
        key["asset_opacity"] = 52
        key["asset_scale"] = 118
        key["icon"] = icons[index % len(icons)]
        key["label_layout"] = "icon_left" if key["width"] > 1 else "icon_above"
        key["custom_top"] = colors[index % len(colors)]
        key["radius_override"] = (6, 12, 18, 24)[index % 4]
        key["press_effect"] = ("depress", "ripple", "glow", "bounce")[index % 4]
        key["hover_effect"] = ("lift", "glow", "pulse", "none")[index % 4]
        key["interaction_mode"] = "toggle" if index in {0, 4, 6} else "action"
        key["active"] = index in {0, 6}
        key["enabled"] = index != 2
    widget = OverlayLauncherDeckWidget(owner)
    widget._store_deck(custom_deck)
    widget._rebuild_keys()
    widget._apply_and_resize()
    widget.show()
    app.processEvents()
    widget.grab().save(str(output_dir / "customized-keycaps.png"), "PNG")
    widget.close()

    catalog_assets = [asset for asset in KEYCAP_ASSETS if asset.filename]
    catalog_keys = []
    catalog_styles = ("air_glass", "soft_clay", "arcade_glow", "mechanical_pbt")
    for index, asset in enumerate(catalog_assets):
        key = new_key(
            asset.asset_id.replace("_", " ").upper(),
            index // 5,
            index % 5,
            style=catalog_styles[index % len(catalog_styles)],
            action_type="internal",
            target="command_palette",
        )
        key["asset_id"] = asset.asset_id
        key["asset_opacity"] = 62
        key["asset_scale"] = 112
        key["icon"] = "none"
        key["font_scale"] = 72
        catalog_keys.append(key)
    catalog = {
        "version": 2,
        "columns": 5,
        "rows": (len(catalog_keys) + 4) // 5,
        "gap": 7,
        "keys": catalog_keys,
    }
    widget = OverlayLauncherDeckWidget(owner)
    widget._store_deck(catalog)
    widget._rebuild_keys()
    widget._apply_and_resize()
    widget.show()
    app.processEvents()
    widget.grab().save(str(output_dir / "keycap-asset-catalog.png"), "PNG")
    widget.close()

    editor = LauncherDeckEditorDialog(template_deck("mixed_4x3"))
    editor._selected_ids = {editor._deck["keys"][0]["id"]}
    editor._rebuild_canvas()
    editor.show()
    app.processEvents()
    editor.grab().save(str(output_dir / "array-editor.png"), "PNG")
    editor.close()
    designer = KeycapAppearanceDialog(custom_deck["keys"][0])
    designer.show()
    app.processEvents()
    designer.grab().save(str(output_dir / "keycap-designer.png"), "PNG")
    scroll_bar = designer._controls_scroll.verticalScrollBar()
    scroll_bar.setValue(scroll_bar.maximum())
    app.processEvents()
    designer.grab().save(str(output_dir / "keycap-designer-assets.png"), "PNG")
    designer.close()
    interaction = KeycapInteractionDialog(custom_deck["keys"][0])
    interaction.show()
    app.processEvents()
    interaction.grab().save(str(output_dir / "keycap-interaction-studio.png"), "PNG")
    interaction._tabs.setCurrentIndex(2)
    interaction._simulate("active")
    app.processEvents()
    interaction.grab().save(str(output_dir / "keycap-state-designer.png"), "PNG")
    interaction._tabs.setCurrentIndex(3)
    interaction._sound_combo.setCurrentIndex(interaction._sound_combo.findData("chime"))
    app.processEvents()
    interaction.grab().save(str(output_dir / "keycap-sound-media.png"), "PNG")
    interaction.close()
    owner.settings.clear()
    owner.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
