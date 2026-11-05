# -*- coding: utf-8 -*-
"""Native Qt control affordances from shared semantic colors and library icons."""

from functools import lru_cache
from pathlib import Path

from PyQt6.QtCore import QDir, Qt, QTemporaryDir
from PyQt6.QtGui import QPainter, QPixmap, QTransform
from PyQt6.QtWidgets import QApplication, QStyle

from calendar_app.shared.color_utils import parse_css_color
from calendar_app.shared.icon_map import ICON, icon

_asset_directory = None


def _spin_arrow_assets(color_value: str) -> tuple[str, str] | None:
    """Cache Font Awesome arrow rasters without writing to a user's profile."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return None
    return _render_spin_arrow_assets(color_value)


@lru_cache(maxsize=64)
def _render_spin_arrow_assets(color_value: str) -> tuple[str, str] | None:
    global _asset_directory
    app = QApplication.instance()
    if _asset_directory is None:
        _asset_directory = QTemporaryDir(QDir.tempPath() + "/air-calendar-controls-XXXXXX")
    if not _asset_directory.isValid():
        return None

    color = parse_css_color(color_value)
    marker = color.name(color.NameFormat.HexArgb).removeprefix("#")
    root = Path(_asset_directory.path())
    down_path = root / f"spin-down-{marker}.png"
    up_path = root / f"spin-up-{marker}.png"
    glyph = icon(ICON.NAV_DOWN, color=color.name(color.NameFormat.HexRgb))
    if glyph.isNull():
        glyph = app.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown)
    if glyph.isNull():
        return None

    raster = QPixmap(64, 64)
    raster.fill(Qt.GlobalColor.transparent)
    painter = QPainter(raster)
    glyph.paint(painter, raster.rect())
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(raster.rect(), color)
    painter.end()
    if not raster.save(str(down_path)):
        return None
    if not raster.transformed(QTransform().rotate(180)).save(str(up_path)):
        return None
    return up_path.as_posix(), down_path.as_posix()


def build_dialog_control_styles(tokens: dict, metrics: dict) -> str:
    """Keep native spin interactions but give every state explicit visible glyphs."""
    normal = _spin_arrow_assets(str(tokens["text_primary"]))
    disabled = _spin_arrow_assets(str(tokens["text_faint"]))
    radius = max(0, int(metrics["field_radius"]))
    padding_x = max(0, int(metrics["field_padding_x"]))
    step_width = max(24, int(metrics["base_font_pt"]) + 10)
    arrows = ""
    if normal and disabled:
        arrows = f"""
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url("{normal[0]}"); width: 12px; height: 10px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url("{normal[1]}"); width: 12px; height: 10px;
}}
QSpinBox::up-arrow:disabled, QSpinBox::up-arrow:off,
QDoubleSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:off {{
    image: url("{disabled[0]}");
}}
QSpinBox::down-arrow:disabled, QSpinBox::down-arrow:off,
QDoubleSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:off {{
    image: url("{disabled[1]}");
}}
"""
    return f"""
/* DC_DIALOG_CONTROL_AFFORDANCES */
QSpinBox, QDoubleSpinBox {{ padding-right: {padding_x + step_width}px; }}
QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {tokens["text_faint"]}; background: {tokens["surface_alt"]};
}}
QSpinBox QLineEdit, QDoubleSpinBox QLineEdit {{
    background: transparent; border: none; margin: 0; padding: 0 {padding_x}px;
    min-height: 0; max-height: 16777215px;
}}
QSpinBox QLineEdit:focus, QDoubleSpinBox QLineEdit:focus {{
    background: transparent; border: none;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border; subcontrol-position: top right; width: {step_width}px;
    background: {tokens["surface_alt"]}; border: none;
    border-left: 1px solid {tokens["border_soft"]}; border-top-right-radius: {radius}px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right; width: {step_width}px;
    background: {tokens["surface_alt"]}; border: none;
    border-left: 1px solid {tokens["border_soft"]}; border-bottom-right-radius: {radius}px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {tokens["surface_hover"]};
}}
QSpinBox::up-button:pressed, QSpinBox::down-button:pressed,
QDoubleSpinBox::up-button:pressed, QDoubleSpinBox::down-button:pressed {{
    background: {tokens["accent_soft_bg"]};
}}
{arrows}
QScrollBar:vertical {{ background: transparent; border: none; width: 10px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; border: none; height: 10px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {tokens["text_faint"]}; border: none; border-radius: 4px; min-height: 28px;
}}
QScrollBar::handle:horizontal {{
    background: {tokens["text_faint"]}; border: none; border-radius: 4px; min-width: 28px;
}}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
    background: {tokens["text_muted"]};
}}
QScrollBar::handle:vertical:pressed, QScrollBar::handle:horizontal:pressed {{
    background: {tokens["accent"]};
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent; border: none;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    background: transparent; border: none; height: 0; image: none;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    background: transparent; border: none; width: 0; image: none;
}}
QScrollArea::corner {{ background: transparent; border: none; }}
"""
