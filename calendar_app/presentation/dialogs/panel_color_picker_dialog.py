# -*- coding: utf-8 -*-
"""사용자 중심 모양 설정 다이얼로그."""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFontComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    get_dialog_metric_overrides,
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
    get_dialog_token_overrides,
)
from calendar_app.shared.color_utils import _shift_rgb, derive_panel_palette, parse_hex_color
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.theme_settings import opacity_percent_label
from calendar_app.shared.theme_snapshot import build_theme_snapshot
from calendar_app.shared.ui_tokens import get_ui_tokens


# ---------------------------------------------------------------------------
# Curated preset palettes (name_key, name_fallback, panel_base_hex, theme_hex, text_colors_dict)
# text_colors_dict keys: primary, secondary, muted, faint
# ---------------------------------------------------------------------------
def _preset_text(
    primary: str,
    secondary: str,
    muted: str,
    faint: str,
    *,
    input_bg: str | None = None,
) -> dict[str, str]:
    colors = {
        "primary": primary,
        "secondary": secondary,
        "muted": muted,
        "faint": faint,
    }
    if input_bg:
        colors["input"] = input_bg
    return colors


_DARK_PRESETS = [
    (
        "dialog.theme.preset.navy",
        "Navy Night",
        "#0d1b2e",
        "#4da6ff",
        _preset_text("#e8f0fe", "#b8ccf0", "#8aa6cc", "#5e7ea8", input_bg="#09121f"),
    ),
    (
        "dialog.theme.preset.deep_purple",
        "Deep Purple",
        "#1a0b2e",
        "#bd93f9",
        _preset_text("#f8f8f2", "#d1d1e0", "#a2a2b0", "#7a7a8a", input_bg="#120821"),
    ),
    (
        "dialog.theme.preset.midnight",
        "Midnight",
        "#0f111a",
        "#7c83ff",
        _preset_text("#e8eaf6", "#b0b8e8", "#8088cc", "#5860a0", input_bg="#0a0c12"),
    ),
    (
        "dialog.theme.preset.crimson",
        "Crimson Red",
        "#1a0d0d",
        "#ff5555",
        _preset_text("#ffe8e8", "#f0b0b0", "#cc8080", "#a05858", input_bg="#120909"),
    ),
    (
        "dialog.theme.preset.emerald_night",
        "Emerald Night",
        "#0d1a14",
        "#50fa7b",
        _preset_text("#e8f9ed", "#b0e8c4", "#80cc9c", "#58a074", input_bg="#09120e"),
    ),
    (
        "dialog.theme.preset.slate",
        "Slate Blue",
        "#151d28",
        "#8be9fd",
        _preset_text("#e6f8ff", "#a4dce8", "#74a8b0", "#507880", input_bg="#0e141c"),
    ),
    (
        "dialog.theme.preset.charcoal",
        "Charcoal Gray",
        "#121212",
        "#f8f8f2",
        _preset_text("#ffffff", "#e0e0e0", "#b0b0b0", "#808080", input_bg="#0a0a0a"),
    ),
    (
        "dialog.theme.preset.dusk_gold",
        "Dusk Gold",
        "#1f1710",
        "#f1fa8c",
        _preset_text("#fffce8", "#e8e4b0", "#c4c080", "#8f8c58", input_bg="#15100b"),
    ),
    (
        "dialog.theme.preset.deep_teal",
        "Deep Teal",
        "#0b1a1a",
        "#8be9fd",
        _preset_text("#e8fafa", "#b0e8e8", "#80cccc", "#58a0a0", input_bg="#071111"),
    ),
    (
        "dialog.theme.preset.burnt_orange",
        "Burnt Orange",
        "#1a120b",
        "#ffb86c",
        _preset_text("#fff4e8", "#e8d0b0", "#c4a880", "#8f7858", input_bg="#120c08"),
    ),
]

_LIGHT_PRESETS = [
    (
        "dialog.theme.preset.pastel_mint",
        "Pastel Mint",
        "#e6fcf5",
        "#099268",
        _preset_text("#1d2b26", "#415a51", "#759489", "#a8c0b6"),
    ),
    (
        "dialog.theme.preset.pastel_sky",
        "Pastel Sky",
        "#e7f5ff",
        "#1971c2",
        _preset_text("#1d2630", "#415161", "#75899c", "#a8b8c7"),
    ),
    (
        "dialog.theme.preset.pastel_lavender",
        "Pastel Lavender",
        "#f3f0ff",
        "#7950f2",
        _preset_text("#2b2a33", "#5a586e", "#8b89a0", "#b6b4cc"),
    ),
    (
        "dialog.theme.preset.pastel_peach",
        "Pastel Peach",
        "#fff4e6",
        "#d9480f",
        _preset_text("#30261f", "#635141", "#9c8975", "#c7b8a8"),
    ),
    (
        "dialog.theme.preset.pastel_rose",
        "Pastel Rose",
        "#fff0f6",
        "#d6336c",
        _preset_text("#301f26", "#63414d", "#9c7582", "#c7a8b3"),
    ),
    (
        "dialog.theme.preset.pastel_coral",
        "Pastel Coral",
        "#fff1eb",
        "#e76f51",
        _preset_text("#36231d", "#6c4a40", "#9d786d", "#ccb0a6"),
    ),
    (
        "dialog.theme.preset.pastel_lemon",
        "Pastel Lemon",
        "#fff9db",
        "#e0b100",
        _preset_text("#332c14", "#66572d", "#9b8856", "#cdbd93"),
    ),
    (
        "dialog.theme.preset.pastel_aqua",
        "Pastel Aqua",
        "#e3fafc",
        "#0b7285",
        _preset_text("#1f2b2d", "#415a5e", "#75949a", "#a8c0c4"),
    ),
    (
        "dialog.theme.preset.pastel_sand",
        "Pastel Sand",
        "#f8f1e7",
        "#b7791f",
        _preset_text("#2f281d", "#615241", "#94816c", "#c4b6a2"),
    ),
    (
        "dialog.theme.preset.pastel_sage",
        "Pastel Sage",
        "#f4fce3",
        "#5c940d",
        _preset_text("#262b1d", "#4f5a41", "#899475", "#b8c0a8"),
    ),
    (
        "dialog.theme.preset.pastel_ice",
        "Pastel Ice",
        "#f1f5f9",
        "#5b7c99",
        _preset_text("#1f2833", "#4b5d70", "#7b8b99", "#a7b2bd"),
    ),
    (
        "dialog.theme.preset.pastel_blush",
        "Pastel Blush",
        "#fff4f6",
        "#d16d87",
        _preset_text("#322128", "#65414b", "#987480", "#c8a9b2"),
    ),
]

_PRESETS = _DARK_PRESETS + _LIGHT_PRESETS

# User-facing style families pair a dark and light variant. The complete
# legacy preset list remains available behind "show all styles".
_STYLE_FAMILIES = [
    (
        "ocean",
        "dialog.theme.preset.navy",
        "dialog.theme.preset.pastel_sky",
    ),
    (
        "violet",
        "dialog.theme.preset.deep_purple",
        "dialog.theme.preset.pastel_lavender",
    ),
    (
        "neutral",
        "dialog.theme.preset.charcoal",
        "dialog.theme.preset.pastel_ice",
    ),
    (
        "forest",
        "dialog.theme.preset.emerald_night",
        "dialog.theme.preset.pastel_mint",
    ),
    (
        "warm",
        "dialog.theme.preset.burnt_orange",
        "dialog.theme.preset.pastel_peach",
    ),
    (
        "rose",
        "dialog.theme.preset.crimson",
        "dialog.theme.preset.pastel_rose",
    ),
    (
        "teal",
        "dialog.theme.preset.deep_teal",
        "dialog.theme.preset.pastel_aqua",
    ),
    (
        "gold",
        "dialog.theme.preset.dusk_gold",
        "dialog.theme.preset.pastel_sand",
    ),
]

_PRESET_INDEX_BY_KEY = {name_key: index for index, (name_key, *_) in enumerate(_PRESETS)}
_PRESET_BY_KEY = {name_key: preset for preset in _PRESETS for name_key in (preset[0],)}
_FAMILY_BY_PRESET_KEY = {
    preset_key: family_id
    for family_id, dark_key, light_key in _STYLE_FAMILIES
    for preset_key in (dark_key, light_key)
}

_SWATCH_SIZE = 44
_PREVIEW_H = 140

# ---------------------------------------------------------------------------
# Point-color presets (name_key, name_fallback, hex)
# ---------------------------------------------------------------------------
_POINT_COLORS = [
    ("dialog.theme.point.blue", "Blue", "#4da6ff"),
    ("dialog.theme.point.sky", "Sky", "#29b6f6"),
    ("dialog.theme.point.emerald", "Emerald", "#2ecc71"),
    ("dialog.theme.point.mint", "Mint", "#1abc9c"),
    ("dialog.theme.point.violet", "Violet", "#9b59b6"),
    ("dialog.theme.point.pink", "Pink", "#e91e8c"),
    ("dialog.theme.point.orange", "Orange", "#e67e22"),
    ("dialog.theme.point.red", "Red", "#e74c3c"),
    ("dialog.theme.point.gold", "Gold", "#f1c40f"),
    ("dialog.theme.point.gray", "Gray", "#9e9e9e"),
]

_DARK_PRESET_KEYS = {name_key for name_key, *_ in _DARK_PRESETS}
_LIGHT_PRESET_KEYS = {name_key for name_key, *_ in _LIGHT_PRESETS}


def _preset_mode_for_key(name_key: str) -> str:
    if name_key in _LIGHT_PRESET_KEYS:
        return "light"
    if name_key in _DARK_PRESET_KEYS:
        return "dark"
    return "all"


def _is_light_base_color(hex_color: str) -> bool:
    c = QColor(str(hex_color or ""))
    if not c.isValid():
        c = QColor("#1c1c1c")
    return c.lightnessF() >= 0.58


def _relative_luminance(color_value: str) -> float:
    color = parse_hex_color(color_value, "#000000")

    def _linear(channel: int) -> float:
        value = channel / 255.0
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * _linear(color.red())
        + 0.7152 * _linear(color.green())
        + 0.0722 * _linear(color.blue())
    )


def _contrast_ratio(foreground: str, background: str) -> float:
    first = _relative_luminance(foreground)
    second = _relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def _blend_color(foreground: QColor, background: QColor, amount: float) -> QColor:
    ratio = max(0.0, min(1.0, float(amount)))
    return QColor(
        round(foreground.red() * (1.0 - ratio) + background.red() * ratio),
        round(foreground.green() * (1.0 - ratio) + background.green() * ratio),
        round(foreground.blue() * (1.0 - ratio) + background.blue() * ratio),
    )


def _tone_for_minimum_contrast(background: str, anchor: str, minimum: float) -> str:
    bg = parse_hex_color(background, "#1c1c1c")
    source = parse_hex_color(anchor, "#ffffff")
    best = source
    for step in range(1, 101):
        candidate = _blend_color(source, bg, step / 100.0)
        if _contrast_ratio(candidate.name(), bg.name()) < minimum:
            break
        best = candidate
    return best.name(QColor.NameFormat.HexRgb)


def _accessible_text_palette(background: str) -> dict[str, str]:
    bg = parse_hex_color(background, "#1c1c1c")
    black = QColor("#000000")
    white = QColor("#ffffff")
    anchor = (
        black
        if _contrast_ratio(black.name(), bg.name()) >= _contrast_ratio(white.name(), bg.name())
        else white
    )
    anchor_hex = anchor.name(QColor.NameFormat.HexRgb)
    return {
        "primary": anchor_hex,
        "secondary": _tone_for_minimum_contrast(bg.name(), anchor_hex, 4.5),
        "muted": _tone_for_minimum_contrast(bg.name(), anchor_hex, 3.0),
        "faint": _tone_for_minimum_contrast(bg.name(), anchor_hex, 2.0),
    }


def _token_px_to_int(value: object, fallback: int) -> int:
    raw = str(value or "").strip().lower()
    if raw.endswith("px"):
        raw = raw[:-2]
    try:
        return max(0, int(round(float(raw))))
    except Exception:
        return fallback


def _picker_shape_metrics(tokens: dict | None = None) -> dict[str, int]:
    source = tokens or get_ui_tokens()
    return {
        "panel_radius": _token_px_to_int(source.get("panel_radius"), 12),
        "item_radius": _token_px_to_int(source.get("panel_item_radius"), 6),
        "field_radius": _token_px_to_int(source.get("field_radius"), 7),
        "button_radius": _token_px_to_int(source.get("button_radius"), 8),
        "toolbar_button_radius": _token_px_to_int(source.get("toolbar_button_radius"), 8),
    }


_DLG_SS = """
    QPushButton#btn_custom {
        background-color: rgba(77,166,255,0.12);
        border-color: rgba(77,166,255,0.30);
    }
    QPushButton#btn_custom:hover {
        background-color: rgba(77,166,255,0.22);
    }
    QPushButton#btn_preset_filter {
        font-size: 12px;
        padding: 4px 10px;
        border-radius: 8px;
    }
    QPushButton#btn_preset_filter[active="true"] {
        background-color: rgba(77,166,255,0.20);
        border-color: rgba(77,166,255,0.45);
    }
    QCheckBox#chk_auto_preset_text {
        font-size: 12px;
        color: rgba(230,240,255,0.92);
        spacing: 6px;
    }
    QCheckBox#chk_auto_preset_text::indicator {
        width: 14px;
        height: 14px;
    }
    QPushButton#btn_apply_preset_text {
        background-color: rgba(102,187,106,0.12);
        border-color: rgba(102,187,106,0.35);
        color: #a8dca8;
        font-size: 12px;
        padding: 6px 12px;
    }
    QPushButton#btn_apply_preset_text:hover {
        background-color: rgba(102,187,106,0.22);
    }
    QPushButton#btn_point_custom {
        background-color: rgba(255,255,255,0.06);
        border-color: rgba(255,255,255,0.20);
        font-size: 12px;
        padding: 6px 14px;
    }
    QPushButton#btn_point_custom:hover {
        background-color: rgba(255,255,255,0.13);
    }
    QPushButton#btn_point_color {
        border-radius: 20px;
        padding: 0px;
        min-width: 40px;
        max-width: 40px;
        min-height: 40px;
        max-height: 40px;
        border: 2px solid rgba(255,255,255,0.12);
    }
    QPushButton#btn_point_color:hover {
        border: 2px solid rgba(255,255,255,0.45);
    }
    QPushButton#btn_color_swatch {
        border-radius: {shape['field_radius']}px;
        padding: 0px;
        min-width: 28px;
        max-width: 28px;
        min-height: 28px;
        max-height: 28px;
    }
    QSlider::groove:horizontal {
        height: 4px;
        background: rgba(255,255,255,0.18);
        border-radius: 2px;
    }
    QSlider::handle:horizontal {
        width: 14px;
        height: 14px;
        margin: -5px 0;
        background: #4da6ff;
        border-radius: 7px;
    }
    QSlider::sub-page:horizontal {
        background: #4da6ff;
        border-radius: 2px;
    }
    QDialogButtonBox QPushButton {
        min-width: 70px;
    }
"""


def _build_picker_extra_stylesheet(tokens: dict | None = None) -> str:
    """피커 고유 스타일(슬라이더/포인트 버튼 등)에 accent 토큰을 적용해 반환."""
    tokens = tokens or get_ui_tokens()
    shape = _picker_shape_metrics(tokens)
    accent = tokens.get("accent", "#4da6ff")
    c = QColor(accent)

    def _acc(alpha: str) -> str:
        return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"

    css = _DLG_SS
    replacements = {
        "#4da6ff": accent,
        "rgba(77,166,255,0.12)": _acc("0.12"),
        "rgba(77,166,255,0.15)": _acc("0.15"),
        "rgba(77,166,255,0.22)": _acc("0.22"),
        "rgba(77,166,255,0.30)": _acc("0.30"),
        "rgba(77,166,255,0.35)": _acc("0.35"),
    }
    for old, new in replacements.items():
        css = css.replace(old, new)
    css = css.replace(
        "color: rgba(230,240,255,0.92);",
        f"color: {tokens.get('text_secondary', '#c8ccd4')};",
    )

    # QFontComboBox는 QComboBox를 상속하지만 Qt stylesheet 상속이 안 될 수 있으므로 명시
    surface_item = tokens.get("bg_item", tokens.get("surface_item", "#1e1e26"))
    surface_hover = tokens.get("bg_item_hover", tokens.get("surface_hover", "#18181f"))
    border_soft = tokens.get("border", tokens.get("border_soft", "rgba(255,255,255,0.10)"))
    border_focus = tokens.get("border_strong", tokens.get("border", "rgba(255,255,255,0.30)"))
    text_primary = tokens.get("text_primary", "#e1e1e6")

    css += f"""
    QFontComboBox {{
        background: {surface_item};
        color: {text_primary};
        border: 1px solid {border_soft};
        border-radius: {shape["field_radius"]}px;
        padding: 4px 8px;
        selection-background-color: {_acc("0.25")};
    }}
    QFontComboBox::drop-down {{
        border: none;
        width: 0px;
        subcontrol-origin: padding;
        subcontrol-position: top right;
    }}
    QPushButton#fontComboPopupButton {{
        min-width: 34px;
        max-width: 34px;
        padding: 0px;
    }}
    QFontComboBox:hover {{
        background: {surface_hover};
        border-color: {border_focus};
    }}
    QFontComboBox:focus {{
        border-color: {accent};
    }}
    QFontComboBox QAbstractItemView {{
        background: {surface_item};
        color: {text_primary};
        border: 1px solid {border_soft};
        selection-background-color: {_acc("0.20")};
    }}
    """

    css += f"""
    QPushButton#btn_preset_filter {{
        border-radius: {shape["toolbar_button_radius"]}px;
    }}
    QPushButton#btn_point_color {{
        border-radius: {shape["toolbar_button_radius"]}px;
    }}
    QPushButton#btn_color_swatch {{
        border-radius: {shape["item_radius"]}px;
    }}
    """
    return css


def _make_swatch_pixmap(base_hex: str, theme_hex: str, size: int) -> QPixmap:
    base = parse_hex_color(base_hex, "#1c1c1c")
    theme = parse_hex_color(theme_hex, "#4da6ff")

    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    bg = QColor(base)
    bg.setAlpha(160)
    p.setBrush(bg)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(2, 2, size - 4, size - 4, 5, 5)

    th = QColor(theme)
    th.setAlpha(200)
    p.setBrush(th)
    p.drawRoundedRect(2, 2, size - 4, 7, 3, 3)

    item = QColor(255, 255, 255, 35)
    p.setBrush(item)
    p.drawRoundedRect(6, 14, size - 12, 6, 2, 2)
    p.drawRoundedRect(6, 24, size - 18, 6, 2, 2)

    p.end()
    return px


def _make_family_swatch_pixmap(dark_preset: tuple, light_preset: tuple) -> QPixmap:
    width, height = 64, 34
    px = QPixmap(width, height)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    for offset, preset in ((1, dark_preset), (width // 2, light_preset)):
        _, _, base_hex, accent_hex, _ = preset
        base = parse_hex_color(base_hex, "#1c1c1c")
        accent = parse_hex_color(accent_hex, "#4da6ff")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(base)
        painter.drawRect(offset, 2, width // 2 - 1, height - 4)
        painter.setBrush(accent)
        painter.drawRect(offset, 2, width // 2 - 1, 6)

    painter.end()
    return px


def _color_swatch_pixmap(hex_color: str, w: int = 22, h: int = 22) -> QPixmap:
    px = QPixmap(w, h)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(hex_color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(1, 1, w - 2, h - 2, 4, 4)
    p.end()
    return px


def _opacity_rgba(hex_color: str, opacity_factor: float, fallback: str) -> str:
    color = parse_hex_color(hex_color, fallback)
    alpha = max(0, min(255, int(round(max(0.0, min(1.0, opacity_factor)) * 255))))
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"


def _update_preview_style(
    frame: QFrame,
    base_hex: str,
    theme_hex: str,
    opacity_factor: float,
    text_primary: str,
    text_secondary: str,
    text_muted: str,
    border_opacity: float = 0.3,
    input_bg: str = "rgba(0,0,0,0.2)",
    text_opacity: float = 1.0,
    tokens: dict | None = None,
):
    """Efficiently updates an existing preview widget's stylesheet and components."""
    pal = derive_panel_palette(base_hex, opacity_factor)
    theme = parse_hex_color(theme_hex, "#4da6ff")
    th_name = theme.name()
    is_light = _is_light_base_color(base_hex)
    bd_base = "0,0,0" if is_light else "255,255,255"
    bd_color = f"rgba({bd_base},{border_opacity})"
    preview_tokens = tokens or get_ui_tokens(
        theme_color=theme_hex,
        text_theme="light" if is_light else "dark",
        panel_base_color=base_hex,
        opacity_factor=opacity_factor,
        input_bg=input_bg,
    )
    shape = _picker_shape_metrics(preview_tokens)
    panel_radius = shape["panel_radius"]
    item_radius = shape["item_radius"]
    field_radius = shape["field_radius"]
    item_bg = preview_tokens.get("bg_item", "rgba(255,255,255,0.05)")
    text_primary_rgba = _opacity_rgba(text_primary, text_opacity, "#f4f7fb")
    text_secondary_rgba = _opacity_rgba(text_secondary, text_opacity, "#c5cfda")
    text_muted_rgba = _opacity_rgba(text_muted, text_opacity, "#95a1ae")

    # Update internal widgets using property selectors or direct access if they were tagged
    # For simplicity, we can just update the whole frame's stylesheet with child selectors
    full_ss = f"""
        QFrame#previewContainer {{ background-color: {pal["surface_bg"]}; border-radius: {panel_radius}px; border: 1px solid {bd_color}; }}
        QFrame#previewTop {{ background-color: {pal["topbar_bg"]}; border-top-left-radius: {panel_radius}px; border-top-right-radius: {panel_radius}px; border-bottom: 1px solid {bd_color}; }}
        QLabel#previewTitle {{ color: {th_name}; font-size: 13px; font-weight: bold; background: transparent; border: none; }}
        QLabel#previewSub {{ color: {text_secondary_rgba}; font-size: 11px; background: transparent; border: none; }}
        QFrame#previewItem1 {{ background: rgba({theme.red()},{theme.green()},{theme.blue()},0.15); border: 1px solid {bd_color}; border-radius: {item_radius}px; }}
        QFrame#previewItem2 {{ background: {item_bg}; border: 1px solid {bd_color}; border-radius: {item_radius}px; }}
        QFrame#previewInput {{ background: {input_bg}; border: 1px solid {bd_color}; border-radius: {field_radius}px; }}
        QLabel#previewItemText1 {{ color: {text_primary_rgba}; font-size: 11px; font-weight: bold; background: transparent; border: none; }}
        QLabel#previewItemText2 {{ color: {text_secondary_rgba}; font-size: 11px; background: transparent; border: none; }}
        QLabel#previewInputHint {{ color: {text_muted_rgba}; font-size: 10px; background: transparent; border: none; }}
    """
    frame.setStyleSheet(full_ss)


def _build_preview_widget(
    base_hex: str,
    theme_hex: str,
    opacity_factor: float,
    text_primary: str = "#f4f7fb",
    text_secondary: str = "#c5cfda",
    text_muted: str = "#95a1ae",
    border_opacity: float = 0.3,
    input_bg: str = "rgba(0,0,0,0.2)",
    text_opacity: float = 1.0,
    tokens: dict | None = None,
    parent: QWidget | None = None,
) -> QFrame:
    frame = QFrame(parent)
    frame.setObjectName("previewContainer")
    frame.setFixedHeight(_PREVIEW_H)

    layout = QVBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    top = QFrame(frame)
    top.setObjectName("previewTop")
    top.setFixedHeight(30)
    top_lay = QHBoxLayout(top)
    top_lay.setContentsMargins(12, 0, 12, 0)

    lbl_title = QLabel(t("dialog.theme.preview.app_name", "Dark Calendar"))
    lbl_title.setObjectName("previewTitle")
    top_lay.addWidget(lbl_title)

    lbl_sub = QLabel("2026.03")
    lbl_sub.setObjectName("previewSub")
    top_lay.addStretch()
    top_lay.addWidget(lbl_sub)
    layout.addWidget(top)

    body = QWidget(frame)
    body_lay = QVBoxLayout(body)
    body_lay.setContentsMargins(12, 8, 12, 8)
    body_lay.setSpacing(6)

    # Item 1
    row1 = QFrame(body)
    row1.setObjectName("previewItem1")
    rl1 = QHBoxLayout(row1)
    rl1.setContentsMargins(10, 4, 10, 4)
    txt1 = QLabel(t("dialog.theme.preview.item_today", "오늘 할 일"))
    txt1.setObjectName("previewItemText1")
    rl1.addWidget(txt1)
    body_lay.addWidget(row1)

    # Item 2
    row2 = QFrame(body)
    row2.setObjectName("previewItem2")
    rl2 = QHBoxLayout(row2)
    rl2.setContentsMargins(10, 4, 10, 4)
    txt2 = QLabel(t("dialog.theme.preview.item_deadline", "프로젝트 마감"))
    txt2.setObjectName("previewItemText2")
    rl2.addWidget(txt2)
    body_lay.addWidget(row2)

    # Input
    inp = QFrame(body)
    inp.setObjectName("previewInput")
    inp.setFixedHeight(24)
    il = QHBoxLayout(inp)
    il.setContentsMargins(10, 2, 10, 2)
    th = QLabel(t("dialog.theme.preview.input_hint", "내용을 입력하세요..."))
    th.setObjectName("previewInputHint")
    il.addWidget(th)
    body_lay.addWidget(inp)

    body_lay.addStretch()
    layout.addWidget(body)

    _update_preview_style(
        frame,
        base_hex,
        theme_hex,
        opacity_factor,
        text_primary,
        text_secondary,
        text_muted,
        border_opacity,
        input_bg,
        text_opacity,
        tokens=tokens,
    )
    return frame


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class WheelBlocker(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            event.ignore()
            return True
        return super().eventFilter(obj, event)


class _FamilyStyleButton(QPushButton):
    navigate_requested = pyqtSignal(int)

    def keyPressEvent(self, event):
        key = event.key()
        columns = max(1, int(self.property("navigation_columns") or 2))
        if key == Qt.Key.Key_Up:
            self.navigate_requested.emit(-columns)
            return
        if key == Qt.Key.Key_Down:
            self.navigate_requested.emit(columns)
            return
        if key in {Qt.Key.Key_Left, Qt.Key.Key_Right}:
            step = -1 if key == Qt.Key.Key_Left else 1
            if self.layoutDirection() == Qt.LayoutDirection.RightToLeft:
                step *= -1
            self.navigate_requested.emit(step)
            return
        super().keyPressEvent(event)


class _ColorRow(QWidget):
    """One row: label | [color swatch btn] | hex label | [reset]"""

    color_changed = pyqtSignal()

    def __init__(self, label: str, current_hex: str, default_hex: str, parent=None):
        super().__init__(parent)
        self._hex = current_hex
        self._default = default_hex
        self._original = current_hex  # 다이얼로그 열릴 때 원래값 (변경 감지용)
        tokens = get_dialog_theme_tokens()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(8)

        lbl = QLabel(label)
        lbl.setFixedWidth(80)
        lbl.setStyleSheet(
            f"font-size: 12px; color: {tokens.get('text_secondary', 'rgba(255,255,255,0.75)')};"
        )
        lay.addWidget(lbl)

        self._swatch = QPushButton()
        self._swatch.setObjectName("btn_color_swatch")
        self._swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self._swatch.setToolTip(t("dialog.theme.tooltip.pick_color", "색상 선택"))
        self._swatch.clicked.connect(self._pick)
        lay.addWidget(self._swatch)

        self._hex_lbl = QLabel()
        self._hex_lbl.setStyleSheet(
            f"font-size: 12px; color: {tokens.get('text_muted', 'rgba(255,255,255,0.50)')};"
        )
        lay.addWidget(self._hex_lbl)

        lay.addStretch()

        # 기본값 표시 레이블
        self._default_lbl = QLabel()
        self._default_lbl.setStyleSheet(
            f"font-size: 11px; color: {tokens.get('text_faint', 'rgba(255,255,255,0.30)')};"
        )
        lay.addWidget(self._default_lbl)

        reset_btn = QPushButton(t("dialog.theme.reset_icon", "↩"))
        reset_btn.setFixedSize(26, 26)
        reset_btn.setToolTip(t("dialog.theme.tooltip.reset_default", "기본값으로 초기화"))
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.clicked.connect(self._reset)
        lay.addWidget(reset_btn)

        self._update_swatch()

    def _update_swatch(self):
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QIcon

        self._swatch.setIcon(QIcon(_color_swatch_pixmap(self._hex, 22, 22)))
        self._swatch.setIconSize(QSize(22, 22))
        self._hex_lbl.setText(self._hex)
        # 기본값과 다를 때 표시
        if self._hex != self._default:
            self._default_lbl.setText(f"← {self._default}")
        else:
            self._default_lbl.setText("")

    def _pick(self):
        from PyQt6.QtWidgets import QColorDialog

        picked = QColorDialog.getColor(
            QColor(self._hex), self, t("dialog.theme.color_picker_title", "색상 선택")
        )
        if picked.isValid():
            self._hex = picked.name(QColor.NameFormat.HexRgb)
            self._update_swatch()
            self.color_changed.emit()

    def _reset(self):
        self._hex = self._default
        self._update_swatch()
        self.color_changed.emit()

    def set_value(self, hex_color: str):
        """외부에서 색상 강제 설정 (프리셋 추천 적용 등)."""
        self._hex = hex_color
        self._update_swatch()
        self.color_changed.emit()

    def set_default(self, hex_color: str):
        """기본값 변경 (프리셋 변경 시)."""
        self._default = hex_color
        self._update_swatch()

    def mark_current_as_original(self):
        """Treat a programmatically selected preset value as the new themed baseline."""
        self._original = self._hex

    def hex_value(self) -> str:
        return self._hex

    def is_changed(self) -> bool:
        return self._hex != self._original


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------


class PanelColorPickerDialog(QDialog):
    color_applied = pyqtSignal(str)

    def __init__(
        self,
        parent=None,
        current_base: str = "#1a2236",
        current_theme: str = "#4da6ff",
        current_opacity: int = 200,
        current_border_opacity: int = 80,
        current_text_opacity: int = 255,
        current_text_primary: str = "#f4f7fb",
        current_text_secondary: str = "rgba(244,247,251,0.76)",
        current_text_muted: str = "rgba(244,247,251,0.58)",
        current_text_faint: str = "rgba(244,247,251,0.42)",
        current_text_theme: str = "dark",
        current_input_bg: str = "rgba(0,0,0,0.2)",
        current_font_family: str = "",
        current_font_size: int = 10,
        current_style_family: str = "",
        current_accent_source: str = "custom",
    ):
        super().__init__(parent)
        self._building = True  # suppress redundant _refresh_preview during init
        apply_dialog_title(self, t("dialog.theme.title", "모양 설정"))
        self.setMinimumWidth(620)
        self._wheel_blocker = WheelBlocker(self)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._base_hex = current_base
        self._theme_hex = current_theme
        self._point_hex = current_theme
        self._point_hex_original = current_theme
        self._accent_source = (
            "family" if str(current_accent_source).lower() == "family" else "custom"
        )
        self._text_source = "custom" if current_text_theme == "custom" else "family"
        self._preferred_style_family = str(current_style_family or "").strip()
        self._opacity = max(0, min(255, current_opacity))
        self._border_opacity = max(0, min(255, current_border_opacity))
        self._text_opacity = max(0, min(255, current_text_opacity))
        self._input_bg = current_input_bg
        self._selected_preset: int | None = None
        self._preset_filter_mode: str = "light" if _is_light_base_color(current_base) else "dark"
        self._preset_modes: list[str] = []
        self._preset_btns: list[QPushButton] = []
        self._family_btns: dict[str, QPushButton] = {}
        self._preset_grid: QGridLayout | None = None
        self._preset_filter_btns: dict[str, QPushButton] = {}
        self._text_theme = current_text_theme
        self._appearance_mode = (
            current_text_theme
            if current_text_theme in {"auto", "dark", "light"}
            else ("light" if _is_light_base_color(current_base) else "dark")
        )
        self._appearance_mode_btns: dict[str, QPushButton] = {}
        self._font_family_orig = current_font_family
        self._font_size_orig = current_font_size
        self._dialog_color_overrides = get_dialog_token_overrides()
        self._dialog_metric_overrides = get_dialog_metric_overrides()
        self._preview_refresh_timer = QTimer(self)
        self._preview_refresh_timer.setSingleShot(True)
        self._preview_refresh_timer.setInterval(32)
        self._preview_refresh_timer.timeout.connect(self._flush_preview_refresh)
        self._last_preview_state: tuple | None = None
        self._preview_swatch_base: str | None = None
        self._preview_apply_count = 0

        # defaults
        self._def_text_primary = "#f4f7fb"
        self._def_text_secondary = "#c5cfda"
        self._def_text_muted = "#95a1ae"
        self._def_text_faint = "#6f7b88"

        self._cur_text_primary = self._parse_color_str(current_text_primary, self._def_text_primary)
        self._cur_text_secondary = self._parse_color_str(
            current_text_secondary, self._def_text_secondary
        )
        self._cur_text_muted = self._parse_color_str(current_text_muted, self._def_text_muted)
        self._cur_text_faint = self._parse_color_str(current_text_faint, self._def_text_faint)
        self._rebuild_theme_context()
        apply_common_dialog_style(
            self,
            minimum_width=620,
            theme_color=self._theme_snapshot.theme_color,
            text_theme=self._theme_snapshot.text_theme,
            panel_base_color=self._theme_snapshot.panel_base_color,
            extra_stylesheet=_build_picker_extra_stylesheet(self._ui_tokens),
            keep_existing_stylesheet=False,
        )

        self._build_ui()
        self._fit_initial_size_to_screen()
        self._auto_select_matching_preset()
        if self._selected_preset is not None:
            selected_theme = _PRESETS[self._selected_preset][3]
            if (
                selected_theme.lower() == self._point_hex.lower()
                and not self._preferred_style_family
            ):
                self._accent_source = "family"
        self._building = False
        self._refresh_preview()
        self._initial_appearance_state = self._appearance_state()
        self._initial_text_theme = self._text_theme
        self._initial_selected_preset = self._selected_preset
        self._initial_preset_filter_mode = self._preset_filter_mode
        self._initial_accent_source = self._accent_source
        self._initial_text_source = self._text_source
        self._update_change_summary()
        self._focus_initial_appearance_control()
        QTimer.singleShot(0, self._focus_initial_appearance_control)

    def is_light_mode(self) -> bool:
        return self._theme_snapshot.text_theme == "light"

    @staticmethod
    def _parse_color_str(val: str, fallback: str) -> str:
        c = QColor(val)
        if c.isValid():
            return c.name(QColor.NameFormat.HexRgb)
        return QColor(fallback).name(QColor.NameFormat.HexRgb)

    def _resolved_dialog_text_theme(self) -> str:
        if self._text_theme in {"auto", "dark", "light"}:
            return self._text_theme
        return "light" if _is_light_base_color(self._base_hex) else "dark"

    def _rebuild_theme_context(self):
        self._theme_snapshot = build_theme_snapshot(
            theme_color=self._point_hex,
            text_theme=self._resolved_dialog_text_theme(),
            panel_base_color=self._base_hex,
            opacity_factor=self._opacity / 255.0,
            input_bg=self._input_bg,
        )
        self._ui_tokens = get_ui_tokens(snapshot=self._theme_snapshot)
        if not hasattr(self, "_dialog_metrics"):
            self._dialog_metrics = get_dialog_metric_tokens(apply_overrides=True)

    def _auto_select_matching_preset(self):
        """Auto-select matching preset based on current base color."""
        initial_mode = self._appearance_mode
        matched = False
        for i, (name_key, _, base, _, _) in enumerate(_PRESETS):
            if base.lower() == self._base_hex.lower():
                self._selected_preset = i
                mode = _preset_mode_for_key(name_key)
                if initial_mode != "auto" and self._text_theme != "custom":
                    self._text_theme = mode
                    self._appearance_mode = mode
                if mode in {"dark", "light"} and initial_mode != "auto":
                    self._preset_filter_mode = mode
                matched = True
                break
        if not matched:
            self._preset_filter_mode = "light" if _is_light_base_color(self._base_hex) else "dark"

        if self._preset_grid is not None:
            self._refresh_preset_filter_buttons()
            self._rebuild_preset_grid()

        if self._selected_preset is not None and self._selected_preset < len(self._preset_btns):
            self._preset_btns[self._selected_preset].setStyleSheet(self._preset_btn_ss(True))
        self._refresh_family_buttons()
        self._refresh_appearance_mode_buttons()

        if hasattr(self, "_point_btns"):
            for i, (_, _, code) in enumerate(_POINT_COLORS):
                if code.lower() == self._point_hex.lower():
                    self._point_btns[i].setStyleSheet(self._point_btn_ss(True))
                    break

    def _preset_filter_btn_ss(self, active: bool) -> str:
        tokens = self._ui_tokens
        shape = _picker_shape_metrics(tokens)
        accent = parse_hex_color(tokens.get("accent", "#4da6ff"), "#4da6ff")
        if active:
            return (
                "QPushButton#btn_preset_filter {"
                f"background: rgba({accent.red()},{accent.green()},{accent.blue()},0.18);"
                f"border: 1px solid rgba({accent.red()},{accent.green()},{accent.blue()},0.52);"
                f"color: {tokens.get('text_primary', '#ffffff')};"
                "font-weight: 700;"
                f"border-radius: {shape['toolbar_button_radius']}px;"
                "padding: 4px 10px;"
                "}"
            )
        return (
            "QPushButton#btn_preset_filter {"
            f"background: {tokens.get('bg_item', tokens.get('surface_item', 'rgba(255,255,255,0.05)'))};"
            f"border: 1px solid {tokens.get('border', tokens.get('border_soft', 'rgba(255,255,255,0.12)'))};"
            f"color: {tokens.get('text_secondary', '#c8ccd4')};"
            "font-weight: 600;"
            f"border-radius: {shape['toolbar_button_radius']}px;"
            "padding: 4px 10px;"
            "}"
            "QPushButton#btn_preset_filter:hover {"
            f"background: {tokens.get('bg_item_hover', tokens.get('surface_hover', 'rgba(255,255,255,0.12)'))};"
            f"border-color: {tokens.get('border_strong', tokens.get('border', 'rgba(255,255,255,0.26)'))};"
            f"color: {tokens.get('text_primary', '#ffffff')};"
            "}"
        )

    def _refresh_preset_filter_buttons(self):
        for mode, btn in self._preset_filter_btns.items():
            active = mode == self._preset_filter_mode
            btn.setChecked(active)
            btn.setProperty("active", "true" if active else "false")
            btn.setStyleSheet(self._preset_filter_btn_ss(active))

    def _set_preset_filter_mode(self, mode: str):
        mode = str(mode or "all").lower()
        if mode not in {"all", "dark", "light"}:
            mode = "all"
        self._preset_filter_mode = mode
        self._refresh_preset_filter_buttons()
        self._rebuild_preset_grid()

    def _set_all_styles_visible(self, visible: bool):
        for widget in getattr(self, "_preset_filter_widgets", []):
            widget.setVisible(bool(visible))
        grid_widget = getattr(self, "_preset_grid_widget", None)
        if grid_widget is not None:
            grid_widget.setVisible(bool(visible))

    def _select_style_family(self, family_id: str):
        family = next((item for item in _STYLE_FAMILIES if item[0] == family_id), None)
        if family is None:
            return
        _, dark_key, light_key = family
        mode = self._appearance_mode
        if mode == "auto":
            mode = self._system_mode_variant()
        if mode not in {"dark", "light"}:
            mode = "light" if _is_light_base_color(self._base_hex) else "dark"
        preset_key = light_key if mode == "light" else dark_key
        preset_index = _PRESET_INDEX_BY_KEY.get(preset_key)
        if preset_index is not None:
            self._select_preset(preset_index, appearance_mode=self._appearance_mode)

    def _system_mode_variant(self) -> str:
        snapshot = build_theme_snapshot(
            theme_color=self._point_hex,
            text_theme="auto",
            panel_base_color="#1c1c1c",
            opacity_factor=self._opacity / 255.0,
        )
        return snapshot.text_theme if snapshot.text_theme in {"dark", "light"} else "dark"

    def _set_appearance_mode(self, mode: str):
        mode = str(mode or "dark").lower()
        if mode not in {"auto", "dark", "light"}:
            return
        self._appearance_mode = mode
        self._text_theme = mode
        family_id = None
        if self._selected_preset is not None and self._selected_preset < len(_PRESETS):
            family_id = _FAMILY_BY_PRESET_KEY.get(_PRESETS[self._selected_preset][0])
        self._select_style_family(family_id or "neutral")
        self._refresh_appearance_mode_buttons()
        self._update_change_summary()

    def _refresh_appearance_mode_buttons(self):
        for mode, button in self._appearance_mode_btns.items():
            active = mode == self._appearance_mode
            button.setChecked(active)
            button.setStyleSheet(self._preset_filter_btn_ss(active))

    def _focus_family_neighbor(self, current: QPushButton, step: int):
        buttons = list(self._family_btns.values())
        if current not in buttons or not buttons:
            return
        target = buttons[(buttons.index(current) + int(step)) % len(buttons)]
        target.setFocus(Qt.FocusReason.TabFocusReason)

    def _refresh_family_buttons(self):
        selected_family = None
        if self._selected_preset is not None and self._selected_preset < len(_PRESETS):
            selected_family = _FAMILY_BY_PRESET_KEY.get(_PRESETS[self._selected_preset][0])
        for family_id, button in self._family_btns.items():
            selected = family_id == selected_family
            label = str(button.property("family_label") or button.text()).removeprefix("✓ ")
            button.setText(f"✓ {label}" if selected else label)
            button.setAccessibleName(button.text())
            button.setStyleSheet(self._preset_btn_ss(selected))

    def _rebuild_preset_grid(self):
        if self._preset_grid is None:
            return

        while self._preset_grid.count():
            item = self._preset_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setVisible(False)

        visible_indices = []
        for idx, (name_key, _, _, _, _) in enumerate(_PRESETS):
            mode = _preset_mode_for_key(name_key)
            is_visible = self._preset_filter_mode == "all" or mode == self._preset_filter_mode
            if is_visible:
                visible_indices.append(idx)

        cols = 4
        for order, idx in enumerate(visible_indices):
            row, col = divmod(order, cols)
            btn = self._preset_btns[idx]
            btn.setVisible(True)
            self._preset_grid.addWidget(btn, row, col)

    @staticmethod
    def _wrap_tab_content(widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        scroll.setWidget(widget)
        return scroll

    def _fit_initial_size_to_screen(self):
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        preferred_width = 980 if getattr(self, "_wide_appearance_layout", False) else 700
        width = min(
            max(self.minimumWidth(), preferred_width),
            max(420, available.width() - 32),
        )
        height = min(760, max(420, available.height() - 48))
        self.resize(width, height)

    def _focus_initial_appearance_control(self):
        settings_scroll = getattr(self, "_settings_scroll", None)
        if settings_scroll is not None:
            settings_scroll.verticalScrollBar().setValue(0)
        target = self._appearance_mode_btns.get(self._appearance_mode)
        if target is not None:
            target.setFocus(Qt.FocusReason.TabFocusReason)

    def _sync_disclosure(
        self,
        button: QPushButton,
        content: QWidget,
        title: str,
        expanded: bool,
    ):
        button.setText(f"{'▾' if expanded else '▸'}  {title}")
        button.setChecked(expanded)
        button.setProperty("expanded", expanded)
        button.setAccessibleName(title)
        content.setVisible(expanded)

    def _settings_section(
        self,
        section_id: str,
        title: str,
        content: QWidget,
        *,
        expanded: bool,
    ) -> QFrame:
        section = QFrame()
        section.setObjectName(f"appearanceSection_{section_id}")
        section.setAccessibleName(title)
        section.setStyleSheet(
            "QFrame#appearanceSection_"
            f"{section_id} {{ background: {self._ui_tokens.get('bg_item', 'rgba(255,255,255,0.04)')}; "
            f"border: 1px solid {self._ui_tokens.get('border_soft', 'rgba(255,255,255,0.10)')}; "
            f"border-radius: {self._dialog_metrics.get('section_radius', 10)}px; }}"
        )
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(8, 10, 8, 8)
        section_layout.setSpacing(4)

        toggle = QPushButton()
        toggle.setObjectName("appearanceSectionToggle")
        toggle.setCheckable(True)
        toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        toggle.setStyleSheet(
            "QPushButton#appearanceSectionToggle {"
            f"color: {self._ui_tokens.get('text_primary', '#ffffff')};"
            "background: transparent; border: 1px solid transparent;"
            "font-size: 13px; font-weight: 700; text-align: left; padding: 5px 6px;"
            "}"
            "QPushButton#appearanceSectionToggle:hover {"
            f"background: {self._ui_tokens.get('bg_item_hover', 'rgba(255,255,255,0.08)')};"
            "}"
            "QPushButton#appearanceSectionToggle:focus {"
            f"border-color: {self._ui_tokens.get('accent', '#4da6ff')};"
            "}"
        )
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(4)
        header_row.addWidget(toggle, 1)

        reset_label = t(
            "dialog.theme.reset_section",
            "{section} 변경 되돌리기",
            section=title,
        )
        reset_button = QPushButton()
        reset_button.setObjectName("appearanceSectionReset")
        reset_button.setIcon(
            _ic(
                ICON.REFRESH,
                color=parse_hex_color(self._ui_tokens.get("text_secondary"), "#c8ccd4").name(
                    QColor.NameFormat.HexRgb
                ),
            )
        )
        reset_button.setFixedSize(30, 30)
        reset_button.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        reset_button.setToolTip(reset_label)
        reset_button.setAccessibleName(reset_label)
        reset_button.setEnabled(False)
        reset_button.setStyleSheet(
            "QPushButton#appearanceSectionReset {"
            f"color: {self._ui_tokens.get('text_secondary', '#c8ccd4')};"
            "background: transparent; border: 1px solid transparent; font-size: 15px;"
            f"border-radius: {self._dialog_metrics.get('button_radius', 8)}px;"
            "}"
            "QPushButton#appearanceSectionReset:hover {"
            f"background: {self._ui_tokens.get('bg_item_hover', 'rgba(255,255,255,0.08)')};"
            f"border-color: {self._ui_tokens.get('border_soft', 'rgba(255,255,255,0.10)')};"
            "}"
            "QPushButton#appearanceSectionReset:focus {"
            f"border-color: {self._ui_tokens.get('accent', '#4da6ff')};"
            "}"
        )
        reset_button.clicked.connect(
            lambda _checked=False, target_section=section_id: self._restore_appearance_section(
                target_section
            )
        )
        header_row.addWidget(reset_button)
        section_layout.addLayout(header_row)
        content.setObjectName(f"appearanceSectionContent_{section_id}")
        content.setStyleSheet(
            f"QWidget#appearanceSectionContent_{section_id} {{ background: transparent; border: none; }}"
        )
        section_layout.addWidget(content)
        toggle.toggled.connect(
            lambda checked, target=toggle, body=content, label=title: self._sync_disclosure(
                target, body, label, checked
            )
        )
        self._section_toggles[section_id] = toggle
        self._section_contents[section_id] = content
        self._section_reset_buttons[section_id] = reset_button
        self._sync_disclosure(toggle, content, title, expanded)
        return section

    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)

        lbl_title = QLabel(t("dialog.theme.title", "모양 설정"))
        lbl_title.setStyleSheet(
            f"font-size: 15px; font-weight: bold; color: {self._ui_tokens.get('text_primary', '#ffffff')};"
        )
        root.addWidget(lbl_title)

        screen = self.screen() or QApplication.primaryScreen()
        available_width = screen.availableGeometry().width() if screen is not None else 1280
        self._appearance_available_width = available_width
        self._wide_appearance_layout = available_width >= 1040

        settings_widget = QWidget()
        settings_layout = QVBoxLayout(settings_widget)
        settings_layout.setContentsMargins(0, 0, 6, 0)
        settings_layout.setSpacing(10)
        self._section_toggles: dict[str, QPushButton] = {}
        self._section_contents: dict[str, QWidget] = {}
        self._section_reset_buttons: dict[str, QPushButton] = {}
        for section_id, title, content, expanded in (
            (
                "style",
                t("dialog.theme.tab.background", "스타일"),
                self._build_bg_tab(),
                True,
            ),
            (
                "accent",
                t("dialog.theme.tab.accent", "포인트 색상"),
                self._build_point_tab(),
                True,
            ),
            (
                "readability",
                t("dialog.theme.tab.text", "가독성"),
                self._build_text_tab(),
                False,
            ),
            (
                "font",
                t("dialog.theme.tab.font", "폰트"),
                self._build_font_tab(),
                False,
            ),
        ):
            settings_layout.addWidget(
                self._settings_section(
                    section_id,
                    title,
                    content,
                    expanded=expanded,
                )
            )
        settings_layout.addStretch(1)

        self._settings_scroll = self._wrap_tab_content(settings_widget)
        self._settings_scroll.setObjectName("appearanceSettingsScroll")
        self._settings_scroll.setAccessibleName(t("dialog.theme.title", "모양 설정"))

        self._preview_panel = QWidget()
        preview_layout = QVBoxLayout(self._preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(8)
        lbl_pre = QLabel(t("dialog.theme.preview.title", "미리보기"))
        lbl_pre.setStyleSheet(
            f"font-size: 12px; font-weight: bold; color: {self._ui_tokens.get('text_muted', 'rgba(255,255,255,0.55)')};"
        )
        preview_layout.addWidget(lbl_pre)

        self._preview_container = QVBoxLayout()
        self._preview_container.setContentsMargins(0, 0, 0, 0)
        self._preview_frame = _build_preview_widget(
            self._base_hex,
            self._point_hex,
            self._opacity / 255.0,
            self._cur_text_primary,
            self._cur_text_secondary,
            self._cur_text_muted,
            border_opacity=self._border_opacity / 255.0,
            input_bg=self._input_bg,
            text_opacity=self._text_opacity / 255.0,
            tokens=self._ui_tokens,
            parent=self,
        )
        self._preview_container.addWidget(self._preview_frame)
        preview_layout.addLayout(self._preview_container)
        preview_layout.addStretch(1)

        if self._wide_appearance_layout:
            workspace = QHBoxLayout()
            workspace.setSpacing(14)
            self._settings_scroll.setMinimumWidth(560)
            self._preview_panel.setMinimumWidth(300)
            workspace.addWidget(self._settings_scroll, 3)
            workspace.addWidget(self._preview_panel, 2)
        else:
            workspace = QVBoxLayout()
            workspace.setSpacing(10)
            workspace.addWidget(self._preview_panel)
            workspace.addWidget(self._settings_scroll, 1)
        root.addLayout(workspace, 1)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(
            f"border: none; border-top: 1px solid {self._ui_tokens.get('border_soft', 'rgba(255,255,255,0.10)')};"
        )
        root.addWidget(sep)

        # 하단 행: 고급 토큰 편집 버튼(좌) + Ok/Cancel(우)
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        adv_btn = QPushButton(t("dialog.theme.advanced", "고급 사용자 설정"))
        adv_btn.setIcon(_ic(ICON.ADVANCED))
        adv_btn.setToolTip(t("dialog.theme.advanced_tip", "색상, 크기와 간격을 세부 조정"))
        adv_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _tf = self._ui_tokens.get("text_faint", "rgba(255,255,255,0.45)")
        _tm = self._ui_tokens.get("text_muted", "rgba(255,255,255,0.70)")
        _bs = self._ui_tokens.get("border_soft", "rgba(255,255,255,0.12)")
        _b = self._ui_tokens.get("border", "rgba(255,255,255,0.30)")
        adv_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: 1px solid {_bs}; "
            f"border-radius: {self._dialog_metrics.get('button_radius', 8)}px; padding: 6px 14px; font-size: 12px; color: {_tf}; }}"
            f"QPushButton:hover {{ border-color: {_b}; color: {_tm}; }}"
        )
        adv_btn.clicked.connect(self._open_token_editor)
        bottom_row.addWidget(adv_btn)

        self._revert_all_btn = QPushButton(t("dialog.theme.revert_all", "전체 되돌리기"))
        self._revert_all_btn.setObjectName("ghost_btn")
        self._revert_all_btn.setIcon(
            _ic(
                ICON.REFRESH,
                color=parse_hex_color(_tm, "#c8ccd4").name(QColor.NameFormat.HexRgb),
            )
        )
        self._revert_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._revert_all_btn.setToolTip(t("dialog.theme.revert_all", "전체 되돌리기"))
        self._revert_all_btn.setAccessibleName(t("dialog.theme.revert_all", "전체 되돌리기"))
        self._revert_all_btn.setEnabled(False)
        self._revert_all_btn.clicked.connect(self._restore_all_appearance_changes)
        bottom_row.addWidget(self._revert_all_btn)

        self._change_summary_label = QLabel()
        self._change_summary_label.setObjectName("appearanceChangeSummary")
        self._change_summary_label.setStyleSheet(
            f"font-size: 11px; color: {self._ui_tokens.get('text_muted', '#9aa0ad')};"
        )
        bottom_row.addWidget(self._change_summary_label)
        bottom_row.addStretch(1)

        from calendar_app.presentation.dialogs.dialog_styles import build_dialog_footer

        _, ok_btn, cancel_btn = build_dialog_footer(
            ok_label=t("common.apply", "적용"),
            cancel_label=t("common.cancel", "취소"),
        )
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        self._apply_btn = ok_btn
        self._apply_btn.setAccessibleName(t("common.apply", "Apply"))
        cancel_btn.setAccessibleName(t("common.cancel", "Cancel"))
        bottom_row.addWidget(ok_btn)
        bottom_row.addWidget(cancel_btn)
        root.addLayout(bottom_row)

    # ------------------------------------------------------------------
    def _build_bg_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        mode_header = QLabel(t("dialog.token_editor.preset_color_mode", "Theme Mode:"))
        mode_header.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {self._ui_tokens.get('text_secondary')};"
        )
        lay.addWidget(mode_header)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)
        self._appearance_mode_group = QButtonGroup(self)
        self._appearance_mode_group.setExclusive(True)
        self._appearance_mode_btns = {}
        for mode, key, fallback in (
            ("auto", "theme.system_default", "System Default"),
            ("light", "theme.light_mode", "Light Mode"),
            ("dark", "theme.dark_mode", "Dark Mode"),
        ):
            button = QPushButton(t(key, fallback))
            button.setObjectName("btn_preset_filter")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setAccessibleName(t(key, fallback))
            button.clicked.connect(
                lambda _checked=False, selected_mode=mode: self._set_appearance_mode(selected_mode)
            )
            self._appearance_mode_group.addButton(button)
            self._appearance_mode_btns[mode] = button
            mode_row.addWidget(button)
        mode_row.addStretch()
        lay.addLayout(mode_row)
        self._refresh_appearance_mode_buttons()

        family_header = QLabel(t("dialog.theme.preset.family_title", "추천 스타일"))
        family_header.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {self._ui_tokens.get('text_secondary')};"
        )
        lay.addWidget(family_header)

        family_grid = QGridLayout()
        family_grid.setHorizontalSpacing(8)
        family_grid.setVerticalSpacing(8)
        self._family_btns = {}
        family_columns = (
            2 if self._wide_appearance_layout or self._appearance_available_width < 680 else 3
        )
        for index, (family_id, dark_key, light_key) in enumerate(_STYLE_FAMILIES):
            dark_preset = _PRESET_BY_KEY[dark_key]
            light_preset = _PRESET_BY_KEY[light_key]
            family_label = t(dark_key, dark_preset[1])
            button = _FamilyStyleButton(family_label)
            button.setProperty("family_label", family_label)
            button.setProperty("navigation_columns", family_columns)
            button.setIcon(QIcon(_make_family_swatch_pixmap(dark_preset, light_preset)))
            button.setIconSize(QSize(64, 34))
            button.setMinimumHeight(48)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setToolTip(f"{t(dark_key, dark_preset[1])} / {t(light_key, light_preset[1])}")
            button.setAccessibleName(family_label)
            button.setAccessibleDescription(button.toolTip())
            button.clicked.connect(
                lambda _checked=False, selected_family=family_id: self._select_style_family(
                    selected_family
                )
            )
            button.navigate_requested.connect(
                lambda step, current=button: self._focus_family_neighbor(current, step)
            )
            self._family_btns[family_id] = button
            row, column = divmod(index, family_columns)
            family_grid.addWidget(button, row, column)
        lay.addLayout(family_grid)

        details_title = t("dialog.theme.bg.details", "배경 세부 설정")
        self._style_details_toggle = QPushButton()
        self._style_details_toggle.setObjectName("appearanceDetailsToggle")
        self._style_details_toggle.setCheckable(True)
        self._style_details_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._style_details_toggle.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._style_details_toggle.setStyleSheet(
            "QPushButton#appearanceDetailsToggle {"
            f"color: {self._ui_tokens.get('text_secondary', '#c8ccd4')};"
            f"background: {self._ui_tokens.get('bg_item', 'rgba(255,255,255,0.04)')};"
            f"border: 1px solid {self._ui_tokens.get('border_soft', 'rgba(255,255,255,0.10)')};"
            "font-size: 12px; font-weight: 600; text-align: left; padding: 7px 9px;"
            f"border-radius: {self._dialog_metrics.get('button_radius', 8)}px;"
            "}"
            "QPushButton#appearanceDetailsToggle:hover {"
            f"background: {self._ui_tokens.get('bg_item_hover', 'rgba(255,255,255,0.08)')};"
            "}"
            "QPushButton#appearanceDetailsToggle:focus {"
            f"border-color: {self._ui_tokens.get('accent', '#4da6ff')};"
            "}"
        )
        lay.addWidget(self._style_details_toggle)

        self._style_details_content = QWidget()
        details_lay = QVBoxLayout(self._style_details_content)
        details_lay.setContentsMargins(0, 4, 0, 0)
        details_lay.setSpacing(8)
        lay.addWidget(self._style_details_content)

        self._show_all_styles = QCheckBox(t("dialog.theme.preset.show_all", "모든 스타일 보기"))
        self._show_all_styles.setCursor(Qt.CursorShape.PointingHandCursor)
        details_lay.addWidget(self._show_all_styles)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)

        filter_lbl = QLabel(t("dialog.theme.preset.filter_label", "Preset Type"))
        filter_lbl.setStyleSheet(
            f"font-size: 11px; color: {self._ui_tokens.get('text_faint', 'rgba(255,255,255,0.45)')};"
        )
        filter_row.addWidget(filter_lbl)
        self._preset_filter_widgets = [filter_lbl]

        self._preset_filter_btns = {}
        for mode, key, fallback in (
            ("all", "dialog.theme.preset.filter_all", "All"),
            ("dark", "dialog.theme.preset.filter_dark", "Dark"),
            ("light", "dialog.theme.preset.filter_light", "Light"),
        ):
            btn = QPushButton(t(key, fallback))
            btn.setObjectName("btn_preset_filter")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, m=mode: self._set_preset_filter_mode(m))
            self._preset_filter_btns[mode] = btn
            self._preset_filter_widgets.append(btn)
            filter_row.addWidget(btn)

        filter_row.addStretch()
        details_lay.addLayout(filter_row)

        self._chk_auto_apply_preset_text = QCheckBox(
            t(
                "dialog.theme.bg.auto_apply_text",
                "Auto-apply recommended text colors when selecting a preset",
            )
        )
        self._chk_auto_apply_preset_text.setObjectName("chk_auto_preset_text")
        self._chk_auto_apply_preset_text.setChecked(True)
        self._chk_auto_apply_preset_text.setToolTip(
            t(
                "dialog.theme.bg.auto_apply_text_tip",
                "When enabled, text colors are immediately adjusted for readability.",
            )
        )
        details_lay.addWidget(self._chk_auto_apply_preset_text)

        self._preset_btns = []
        self._preset_modes = []
        grid_widget = QWidget()
        self._preset_grid = QGridLayout(grid_widget)
        self._preset_grid_widget = grid_widget
        self._preset_grid.setContentsMargins(0, 0, 0, 0)
        self._preset_grid.setHorizontalSpacing(8)
        self._preset_grid.setVerticalSpacing(8)

        for i, (name_key, name_fallback, base, theme, _) in enumerate(_PRESETS):
            preset_name = t(name_key, name_fallback)
            btn = self._make_preset_button(i, preset_name, base, theme)
            self._preset_btns.append(btn)
            self._preset_modes.append(_preset_mode_for_key(name_key))

        self._refresh_preset_filter_buttons()
        self._rebuild_preset_grid()

        details_lay.addWidget(grid_widget)
        self._show_all_styles.toggled.connect(self._set_all_styles_visible)
        self._set_all_styles_visible(False)

        btn_row = QHBoxLayout()
        self._btn_custom = QPushButton(t("dialog.theme.custom_color", "Custom Color"))
        self._btn_custom.setObjectName("btn_custom")
        self._btn_custom.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_custom.clicked.connect(self._open_custom_color)
        btn_row.addWidget(self._btn_custom)
        btn_row.addStretch()

        self._swatch_lbl = QLabel()
        self._swatch_lbl.setFixedSize(24, 24)
        self._swatch_lbl.setToolTip(t("dialog.theme.tooltip.current_color", "현재 배경색"))
        btn_row.addWidget(self._swatch_lbl)
        self._hex_lbl = QLabel()
        self._hex_lbl.setStyleSheet(
            f"font-size: 12px; color: {self._ui_tokens.get('text_muted', 'rgba(255,255,255,0.50)')};"
        )
        btn_row.addWidget(self._hex_lbl)
        details_lay.addLayout(btn_row)

        _lbl_ss = f"font-size: 12px; color: {self._ui_tokens.get('text_secondary', 'rgba(255,255,255,0.70)')};"
        _val_ss = f"font-size: 12px; color: {self._ui_tokens.get('text_muted', 'rgba(255,255,255,0.50)')};"

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(
            f"border: none; border-top: 1px solid {self._ui_tokens.get('border_soft', 'rgba(255,255,255,0.10)')}; margin: 2px 0;"
        )
        details_lay.addWidget(sep2)

        op_header = QLabel(t("dialog.theme.opacity", "불투명도"))
        op_header.setStyleSheet(
            f"font-size: 11px; font-weight: bold; color: {self._ui_tokens.get('text_muted', 'rgba(255,255,255,0.50)')};"
        )
        details_lay.addWidget(op_header)
        op_hint = QLabel(t("dialog.theme.opacity_hint", "0% = 완전 투명, 100% = 완전 불투명"))
        op_hint.setStyleSheet(
            f"font-size: 11px; color: {self._ui_tokens.get('text_faint', 'rgba(255,255,255,0.42)')};"
        )
        details_lay.addWidget(op_hint)

        def _make_opacity_row(label: str, value: int):
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setFixedWidth(50)
            lbl.setStyleSheet(_lbl_ss)
            row.addWidget(lbl)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 255)
            slider.setValue(value)
            slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row.addWidget(slider)
            val_lbl = QLabel(opacity_percent_label(value))
            val_lbl.setFixedWidth(44)
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            val_lbl.setStyleSheet(_val_ss)
            row.addWidget(val_lbl)
            return row, slider, val_lbl

        bg_row, self._slider, self._op_lbl = _make_opacity_row(
            t("dialog.theme.opacity_bg", "배경:"), self._opacity
        )
        bd_row, self._border_slider, self._bd_op_lbl = _make_opacity_row(
            t("dialog.theme.opacity_border", "테두리:"), self._border_opacity
        )
        txt_row, self._text_slider, self._txt_op_lbl = _make_opacity_row(
            t("dialog.theme.opacity_text", "글씨:"), self._text_opacity
        )

        self._slider.valueChanged.connect(self._on_opacity_changed)
        self._border_slider.valueChanged.connect(self._on_border_opacity_changed)
        self._text_slider.valueChanged.connect(self._on_text_opacity_changed)

        details_lay.addLayout(bg_row)
        details_lay.addLayout(bd_row)
        details_lay.addLayout(txt_row)

        self._style_details_toggle.toggled.connect(
            lambda checked: self._sync_disclosure(
                self._style_details_toggle,
                self._style_details_content,
                details_title,
                checked,
            )
        )
        self._sync_disclosure(
            self._style_details_toggle,
            self._style_details_content,
            details_title,
            False,
        )

        return w

    # ------------------------------------------------------------------
    def _build_text_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 14, 12, 12)
        lay.setSpacing(6)

        lbl_sub = QLabel(t("dialog.theme.text.subtitle", "역할별 글자 색상을 지정합니다."))
        lbl_sub.setStyleSheet(
            f"font-size: 12px; color: {self._ui_tokens.get('text_muted', 'rgba(255,255,255,0.50)')};"
        )
        lay.addWidget(lbl_sub)

        contrast_row = QHBoxLayout()
        self._contrast_status = QLabel()
        self._contrast_status.setWordWrap(True)
        contrast_row.addWidget(self._contrast_status, 1)
        self._contrast_fix_btn = QPushButton(
            t("dialog.theme.text.contrast_fix", "읽기 편하게 자동 보정")
        )
        self._contrast_fix_btn.setIcon(_ic(ICON.APPEARANCE))
        self._contrast_fix_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._contrast_fix_btn.setToolTip(
            t(
                "dialog.theme.text.contrast_fix_tip",
                "현재 배경에 맞춰 텍스트 색상을 자동으로 조정합니다.",
            )
        )
        self._contrast_fix_btn.clicked.connect(self._auto_fix_text_contrast)
        lay.addLayout(contrast_row)

        # 프리셋 권장 글자색 적용 버튼
        preset_row = QHBoxLayout()
        self._btn_apply_preset_text = QPushButton(
            t("dialog.theme.text.apply_recommended", "권장 글자색 적용")
        )
        self._btn_apply_preset_text.setIcon(_ic(ICON.APPEARANCE))
        self._btn_apply_preset_text.setObjectName("btn_apply_preset_text")
        self._btn_apply_preset_text.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_apply_preset_text.setToolTip(
            t("dialog.theme.text.apply_recommended_tip", "배경 프리셋에 맞는 글자색 자동 적용")
        )
        self._btn_apply_preset_text.clicked.connect(self._apply_preset_text_colors)
        self._btn_apply_preset_text.setEnabled(self._selected_preset is not None)
        preset_row.addWidget(self._btn_apply_preset_text)
        preset_row.addWidget(self._contrast_fix_btn)
        preset_row.addStretch()
        lay.addLayout(preset_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(
            f"border: none; border-top: 1px solid {self._ui_tokens.get('border_soft', 'rgba(255,255,255,0.10)')}; margin: 4px 0;"
        )
        lay.addWidget(sep)

        self._row_primary = _ColorRow(
            t("dialog.theme.text.primary", "기본 글자"),
            self._cur_text_primary,
            self._def_text_primary,
        )
        self._row_secondary = _ColorRow(
            t("dialog.theme.text.secondary", "보조 글자"),
            self._cur_text_secondary,
            self._def_text_secondary,
        )
        self._row_muted = _ColorRow(
            t("dialog.theme.text.muted", "흐린 글자"),
            self._cur_text_muted,
            self._def_text_muted,
        )
        self._row_faint = _ColorRow(
            t("dialog.theme.text.faint", "희미 글자"),
            self._cur_text_faint,
            self._def_text_faint,
        )
        self._row_input_bg = _ColorRow(
            t("dialog.theme.text.input_bg", "입력 배경"),
            self._parse_color_str(self._input_bg, "rgba(0,0,0,0.2)"),
            "rgba(0,0,0,0.2)",
        )

        # Update preview on any color change
        for row in (
            self._row_primary,
            self._row_secondary,
            self._row_muted,
            self._row_faint,
            self._row_input_bg,
        ):
            row.color_changed.connect(self._on_text_colors_changed)

        lay.addWidget(self._row_primary)
        lay.addWidget(self._row_secondary)
        lay.addWidget(self._row_muted)
        lay.addWidget(self._row_faint)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(
            f"border: none; border-top: 1px solid {self._ui_tokens.get('border_soft', 'rgba(255,255,255,0.06)')}; margin: 4px 0;"
        )
        lay.addWidget(sep2)
        lay.addWidget(self._row_input_bg)

        lay.addSpacing(6)

        # Reset all
        reset_all_btn = QPushButton(t("dialog.theme.text.reset_all", "↩ 모든 글자색 초기화"))
        reset_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_all_btn.clicked.connect(self._reset_all_text)
        lay.addWidget(reset_all_btn)

        lay.addStretch()

        hint = QLabel(
            t(
                "dialog.theme.text.hint_short",
                "기본: 주요 텍스트 / 보조: 부가 텍스트 / 흐림: 메타 / 희미: 힌트",
            )
        )
        hint.setStyleSheet(
            f"font-size: 10px; color: {self._ui_tokens.get('text_faint', 'rgba(255,255,255,0.35)')};"
        )
        lay.addWidget(hint)

        self._update_contrast_status()

        return w

    def _on_text_colors_changed(self):
        self._text_source = "custom"
        self._update_contrast_status()
        self._schedule_preview_refresh()
        self._update_change_summary()

    def _set_text_row_values(self, values: dict[str, str]):
        rows = {
            "primary": self._row_primary,
            "secondary": self._row_secondary,
            "muted": self._row_muted,
            "faint": self._row_faint,
            "input": self._row_input_bg,
        }
        for key, value in values.items():
            row = rows.get(key)
            if row is None:
                continue
            blocked = row.blockSignals(True)
            row.set_value(value)
            row.blockSignals(blocked)

    def _update_contrast_status(self):
        if not hasattr(self, "_row_primary") or not hasattr(self, "_contrast_status"):
            return
        primary_ratio = _contrast_ratio(self._row_primary.hex_value(), self._base_hex)
        secondary_ratio = _contrast_ratio(self._row_secondary.hex_value(), self._base_hex)
        is_readable = primary_ratio >= 4.5 and secondary_ratio >= 4.5
        if is_readable:
            message = t(
                "dialog.theme.text.contrast_good",
                "읽기 편한 조합 · 기본 {primary}:1 / 보조 {secondary}:1",
                primary=f"{primary_ratio:.1f}",
                secondary=f"{secondary_ratio:.1f}",
            )
            color = self._ui_tokens.get("success_hex", self._ui_tokens.get("accent"))
        else:
            message = t(
                "dialog.theme.text.contrast_low",
                "대비가 낮습니다 · 기본 {primary}:1 / 보조 {secondary}:1",
                primary=f"{primary_ratio:.1f}",
                secondary=f"{secondary_ratio:.1f}",
            )
            color = self._ui_tokens.get("warning_hex", self._ui_tokens.get("accent"))
        self._contrast_status.setText(message)
        self._contrast_status.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {color};")
        self._contrast_status.setAccessibleName(message)
        self._contrast_fix_btn.setEnabled(not is_readable)

    def _auto_fix_text_contrast(self):
        palette = _accessible_text_palette(self._base_hex)
        base_color = parse_hex_color(self._base_hex, "#1c1c1c")
        input_color = _shift_rgb(base_color, 12 if _is_light_base_color(self._base_hex) else -12)
        self._set_text_row_values(
            {
                "primary": palette["primary"],
                "secondary": palette["secondary"],
                "muted": palette["muted"],
                "faint": palette["faint"],
                "input": input_color.name(QColor.NameFormat.HexRgb),
            }
        )
        self._text_source = "custom"
        self._update_contrast_status()
        self._refresh_preview()
        self._update_change_summary()

    def _reset_all_text(self):
        for row in (self._row_primary, self._row_secondary, self._row_muted, self._row_faint):
            row._hex = row._default
            row._update_swatch()
        self._text_source = "custom"
        self._refresh_preview()
        self._update_contrast_status()
        self._update_change_summary()

    # ------------------------------------------------------------------
    def _build_point_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 14, 12, 12)
        lay.setSpacing(12)

        lbl_sub = QLabel(t("dialog.theme.accent.subtitle", "UI 포인트 색상을 지정합니다."))
        lbl_sub.setStyleSheet(
            f"font-size: 12px; color: {self._ui_tokens.get('text_muted', 'rgba(255,255,255,0.50)')};"
        )
        lay.addWidget(lbl_sub)

        # 프리셋 색상 버튼들 (2행 × 5열)
        self._point_btns: list[QPushButton] = []
        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        cols = 5
        for i, (name_key, name_fallback, code) in enumerate(_POINT_COLORS):
            row_i, col_i = divmod(i, cols)
            point_name = t(name_key, name_fallback)
            btn = self._make_point_button(i, point_name, code)
            self._point_btns.append(btn)
            grid.addWidget(btn, row_i, col_i)
        lay.addWidget(grid_w)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(
            f"border: none; border-top: 1px solid {self._ui_tokens.get('border_soft', 'rgba(255,255,255,0.10)')};"
        )
        lay.addWidget(sep)

        # 직접 지정 행
        custom_row = QHBoxLayout()
        btn_custom = QPushButton(t("dialog.theme.custom_color", "직접 색상"))
        btn_custom.setIcon(_ic(ICON.COLOR_PICKER))
        btn_custom.setObjectName("btn_point_custom")
        btn_custom.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_custom.clicked.connect(self._open_custom_point_color)
        custom_row.addWidget(btn_custom)
        custom_row.addStretch()

        self._point_swatch_lbl = QLabel()
        self._point_swatch_lbl.setFixedSize(24, 24)
        self._point_swatch_lbl.setToolTip(
            t("dialog.theme.tooltip.current_accent", "현재 포인트 색상")
        )
        custom_row.addWidget(self._point_swatch_lbl)

        self._point_hex_lbl = QLabel()
        self._point_hex_lbl.setStyleSheet(
            f"font-size: 12px; color: {self._ui_tokens.get('text_muted', 'rgba(255,255,255,0.50)')};"
        )
        custom_row.addWidget(self._point_hex_lbl)
        lay.addLayout(custom_row)

        lay.addStretch()

        hint = QLabel(
            t(
                "dialog.theme.accent.hint_short",
                "포인트 색은 버튼/링크 강조에 사용됩니다. 배경 프리셋 선택 시 함께 맞춰집니다.",
            )
        )
        hint.setStyleSheet(
            f"font-size: 10px; color: {self._ui_tokens.get('text_faint', 'rgba(255,255,255,0.35)')};"
        )
        lay.addWidget(hint)

        self._refresh_point_display()
        return w

    def _make_point_button(self, idx: int, name: str, code: str) -> QPushButton:
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QIcon

        btn = QPushButton()
        btn.setObjectName("btn_point_color")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(f"{name}\n{code}")

        # 원형 색상 아이콘 (40×40)
        px = QPixmap(40, 40)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(code))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(2, 2, 36, 36)
        p.end()
        btn.setIcon(QIcon(px))
        btn.setIconSize(QSize(36, 36))

        # 이름 레이블은 버튼 위에 오버레이
        container = QWidget(btn)
        container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        container.setGeometry(0, 0, 40, 40)
        inner = QVBoxLayout(container)
        inner.setContentsMargins(0, 0, 0, 0)

        btn.setStyleSheet(self._point_btn_ss(False))
        btn.clicked.connect(lambda *_, i=idx: self._select_point_color(i))

        # 이름을 툴팁에만, 버튼 아래에 별도 레이블 없이 심플하게
        return btn

    def _point_btn_ss(self, selected: bool) -> str:
        shape = _picker_shape_metrics(self._ui_tokens)
        radius = shape["toolbar_button_radius"]
        border_soft = self._ui_tokens.get("border", "rgba(255,255,255,0.12)")
        border_strong = self._ui_tokens.get("border_strong", "rgba(255,255,255,0.50)")
        text_primary = self._ui_tokens.get("text_primary", "#ffffff")
        if selected:
            return f"""
                QPushButton#btn_point_color {{
                    border-radius: {radius}px;
                    border: 3px solid {text_primary};
                    padding: 0px;
                    min-width: 40px; max-width: 40px;
                    min-height: 40px; max-height: 40px;
                }}
            """
        return f"""
            QPushButton#btn_point_color {{
                border-radius: {radius}px;
                border: 2px solid {border_soft};
                padding: 0px;
                min-width: 40px; max-width: 40px;
                min-height: 40px; max-height: 40px;
            }}
            QPushButton#btn_point_color:hover {{
                border: 2px solid {border_strong};
            }}
        """

    def _select_point_color(self, idx: int):
        _, _, code = _POINT_COLORS[idx]
        self._point_hex = code
        self._accent_source = "custom"
        self._rebuild_theme_context()
        for i, btn in enumerate(self._point_btns):
            btn.setStyleSheet(self._point_btn_ss(i == idx))
        self._refresh_point_display()
        self._refresh_preview()
        self._update_change_summary()

    def _open_custom_point_color(self):
        from PyQt6.QtWidgets import QColorDialog

        picked = QColorDialog.getColor(
            QColor(self._point_hex),
            self,
            t("dialog.theme.accent.custom_picker_title", "포인트 색상 선택"),
        )
        if not picked.isValid():
            return
        self._point_hex = picked.name(QColor.NameFormat.HexRgb)
        self._accent_source = "custom"
        self._rebuild_theme_context()
        # 프리셋 선택 해제
        for btn in self._point_btns:
            btn.setStyleSheet(self._point_btn_ss(False))
        self._refresh_point_display()
        self._refresh_preview()
        self._update_change_summary()

    def _refresh_point_display(self):
        if not hasattr(self, "_point_swatch_lbl"):
            return
        px = QPixmap(22, 22)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(self._point_hex))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(1, 1, 20, 20)
        p.end()
        self._point_swatch_lbl.setPixmap(px)
        self._point_hex_lbl.setText(self._point_hex)

    def _make_preset_button(self, _idx: int, name: str, base: str, theme: str) -> QPushButton:
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QIcon

        btn = QPushButton()
        btn.setFixedSize(_SWATCH_SIZE + 30, _SWATCH_SIZE + 18)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(f"{name}\n{base}")
        btn.setIcon(QIcon(_make_swatch_pixmap(base, theme, _SWATCH_SIZE)))
        btn.setIconSize(QSize(_SWATCH_SIZE, _SWATCH_SIZE))
        btn.setText("")

        container = QWidget(btn)
        container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        container.setGeometry(0, _SWATCH_SIZE - 2, _SWATCH_SIZE + 30, 20)
        inner = QHBoxLayout(container)
        inner.setContentsMargins(2, 0, 2, 0)
        name_lbl = QLabel(name)
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setStyleSheet(
            f"font-size: 11px; color: {self._ui_tokens.get('text_secondary', 'rgba(255,255,255,0.65)')}; background: transparent;"
        )
        inner.addWidget(name_lbl)

        btn.setStyleSheet(self._preset_btn_ss(False))
        btn.clicked.connect(lambda *_, i=_idx: self._select_preset(i))
        return btn

    def _preset_btn_ss(self, selected: bool) -> str:
        shape = _picker_shape_metrics(self._ui_tokens)
        if selected:
            c = QColor(self._point_hex)
            if not c.isValid():
                c = QColor("#4da6ff")
            r, g, b = c.red(), c.green(), c.blue()
            br = shape["button_radius"]
            return f"""
                QPushButton {{
                    background-color: rgba({r},{g},{b},0.12);
                    border: 2px solid rgba({r},{g},{b},0.70);
                    border-radius: {br}px;
                    padding: 1px;
                }}
                QPushButton:hover {{ background-color: rgba({r},{g},{b},0.20); }}
            """
        bg_item = self._ui_tokens.get("bg_item", "rgba(255,255,255,0.05)")
        border = self._ui_tokens.get("border", "rgba(255,255,255,0.10)")
        br = shape["button_radius"]
        bg_hover = self._ui_tokens.get("bg_item_hover", "rgba(255,255,255,0.12)")
        border_strong = self._ui_tokens.get("border_strong", "rgba(255,255,255,0.25)")
        return f"""
            QPushButton {{
                background-color: {bg_item};
                border: 1px solid {border};
                border-radius: {br}px;
                padding: 2px;
            }}
            QPushButton:hover {{
                background-color: {bg_hover};
                border-color: {border_strong};
            }}
        """

    # ------------------------------------------------------------------
    def _select_preset(self, idx: int, *, appearance_mode: str | None = None):
        self._selected_preset = idx
        name_key, _, base, theme, text_dict = _PRESETS[idx]
        self._base_hex = base
        self._theme_hex = theme
        mode = _preset_mode_for_key(name_key)
        selected_mode = appearance_mode if appearance_mode in {"auto", "dark", "light"} else mode
        self._appearance_mode = selected_mode
        self._text_theme = selected_mode
        self._accent_source = "family"
        self._rebuild_theme_context()

        if mode in {"dark", "light"} and self._preset_filter_mode != mode:
            self._preset_filter_mode = mode
            self._refresh_preset_filter_buttons()
            self._rebuild_preset_grid()
        for i, btn in enumerate(self._preset_btns):
            btn.setStyleSheet(self._preset_btn_ss(i == idx))
        self._refresh_family_buttons()
        self._refresh_appearance_mode_buttons()

        self._point_hex = theme
        if hasattr(self, "_point_btns"):
            for i, (_, _, code) in enumerate(_POINT_COLORS):
                self._point_btns[i].setStyleSheet(self._point_btn_ss(code.lower() == theme.lower()))
        self._refresh_point_display()

        if hasattr(self, "_row_primary"):
            self._row_primary.set_default(text_dict["primary"])
            self._row_secondary.set_default(text_dict["secondary"])
            self._row_muted.set_default(text_dict["muted"])
            self._row_faint.set_default(text_dict["faint"])

        if hasattr(self, "_btn_apply_preset_text"):
            self._btn_apply_preset_text.setEnabled(True)
            self._btn_apply_preset_text.setToolTip(
                t(
                    "dialog.theme.text.apply_recommended_for_preset",
                    "Apply recommended text colors for this preset",
                )
            )

        if (
            getattr(self, "_chk_auto_apply_preset_text", None) is not None
            and self._chk_auto_apply_preset_text.isChecked()
        ):
            self._apply_preset_text_colors(refresh=False)
            for row in (
                self._row_primary,
                self._row_secondary,
                self._row_muted,
                self._row_faint,
                self._row_input_bg,
            ):
                row.mark_current_as_original()

        self._update_contrast_status()
        self._refresh_preview()
        self._update_change_summary()

    def _open_custom_color(self):
        from PyQt6.QtWidgets import QColorDialog

        picked = QColorDialog.getColor(
            QColor(self._base_hex),
            self,
            t("dialog.theme.bg.custom_picker_title", "Choose Background Color"),
        )
        if not picked.isValid():
            return
        self._base_hex = picked.name(QColor.NameFormat.HexRgb)
        self._selected_preset = None
        self._accent_source = "custom"
        self._text_source = "custom"
        self._preset_filter_mode = "light" if _is_light_base_color(self._base_hex) else "dark"
        for btn in self._preset_btns:
            btn.setStyleSheet(self._preset_btn_ss(False))
        self._refresh_family_buttons()
        if hasattr(self, "_btn_apply_preset_text"):
            self._btn_apply_preset_text.setEnabled(False)
            self._btn_apply_preset_text.setToolTip(
                t(
                    "dialog.theme.text.apply_recommended_disabled",
                    "Recommended text colors are available when a preset is selected",
                )
            )
        self._refresh_preset_filter_buttons()
        self._rebuild_preset_grid()
        self._update_contrast_status()
        self._refresh_preview()
        self._update_change_summary()

    def _on_opacity_changed(self, value: int):
        self._opacity = value
        self._op_lbl.setText(opacity_percent_label(value))
        self._schedule_preview_refresh()
        self._update_change_summary()

    def _on_border_opacity_changed(self, value: int):
        self._border_opacity = value
        self._bd_op_lbl.setText(opacity_percent_label(value))
        self._schedule_preview_refresh()
        self._update_change_summary()

    def _on_text_opacity_changed(self, value: int):
        self._text_opacity = value
        self._txt_op_lbl.setText(opacity_percent_label(value))
        self._schedule_preview_refresh()
        self._update_change_summary()

    def _schedule_preview_refresh(self):
        if getattr(self, "_building", False):
            return
        self._preview_refresh_timer.start()

    def _flush_preview_refresh(self):
        self._refresh_preview()

    def _refresh_preview(self):
        if getattr(self, "_building", False):
            return

        if hasattr(self, "_row_input_bg"):
            self._input_bg = self._row_input_bg.hex_value()
        preview_state = (
            self._base_hex,
            self._point_hex,
            self._opacity,
            self._border_opacity,
            self._text_opacity,
            self._resolved_dialog_text_theme(),
            self._row_primary.hex_value() if hasattr(self, "_row_primary") else "",
            self._row_secondary.hex_value() if hasattr(self, "_row_secondary") else "",
            self._row_muted.hex_value() if hasattr(self, "_row_muted") else "",
            self._input_bg,
            self._system_mode_variant() if self._appearance_mode == "auto" else "",
        )
        if preview_state == self._last_preview_state:
            return
        self._preview_refresh_timer.stop()
        self._rebuild_theme_context()

        # Update swatch displays in the tab
        if self._preview_swatch_base != self._base_hex:
            px = _color_swatch_pixmap(self._base_hex)
            if hasattr(self, "_swatch_lbl"):
                self._swatch_lbl.setPixmap(px)
            self._preview_swatch_base = self._base_hex
        if hasattr(self, "_hex_lbl"):
            self._hex_lbl.setText(self._base_hex)

        # Update existing preview frame components efficiently
        if self._preview_frame is not None:
            preview_input_bg = (
                self._row_input_bg.hex_value()
                if hasattr(self, "_row_input_bg")
                else "rgba(0,0,0,0.2)"
            )
            preview_tokens = get_ui_tokens(
                theme_color=self._point_hex,
                text_theme=self._resolved_dialog_text_theme(),
                panel_base_color=self._base_hex,
                opacity_factor=self._opacity / 255.0,
                input_bg=preview_input_bg,
            )
            _update_preview_style(
                self._preview_frame,
                self._base_hex,
                self._point_hex,
                self._opacity / 255.0,
                self._row_primary.hex_value() if hasattr(self, "_row_primary") else "#f4f7fb",
                self._row_secondary.hex_value() if hasattr(self, "_row_secondary") else "#c5cfda",
                self._row_muted.hex_value() if hasattr(self, "_row_muted") else "#95a1ae",
                border_opacity=self._border_opacity / 255.0,
                input_bg=preview_input_bg,
                text_opacity=self._text_opacity / 255.0,
                tokens=preview_tokens,
            )
            self._last_preview_state = preview_state
            self._preview_apply_count += 1

    def _sync_controls_after_restore(self):
        self._rebuild_theme_context()
        for index, button in enumerate(self._preset_btns):
            button.setStyleSheet(self._preset_btn_ss(index == self._selected_preset))
        self._refresh_family_buttons()
        self._refresh_appearance_mode_buttons()
        self._refresh_preset_filter_buttons()
        self._rebuild_preset_grid()

        for index, (_, _, code) in enumerate(_POINT_COLORS):
            self._point_btns[index].setStyleSheet(
                self._point_btn_ss(code.lower() == self._point_hex.lower())
            )
        self._refresh_point_display()
        self._btn_apply_preset_text.setEnabled(self._selected_preset is not None)
        self._update_contrast_status()
        self._refresh_preview()
        self._update_change_summary()

    def _restore_appearance_section(self, section_id: str, *, finalize: bool = True):
        initial = getattr(self, "_initial_appearance_state", None)
        if not initial or section_id not in {"style", "accent", "readability", "font"}:
            return

        if section_id == "style":
            (
                base_hex,
                appearance_mode,
                opacity,
                border_opacity,
                text_opacity,
            ) = initial["style"]
            self._base_hex = str(base_hex)
            self._appearance_mode = str(appearance_mode)
            self._text_theme = self._initial_text_theme
            self._selected_preset = self._initial_selected_preset
            self._preset_filter_mode = self._initial_preset_filter_mode
            self._opacity = int(opacity)
            self._border_opacity = int(border_opacity)
            self._text_opacity = int(text_opacity)
            for slider, value, label in (
                (self._slider, self._opacity, self._op_lbl),
                (self._border_slider, self._border_opacity, self._bd_op_lbl),
                (self._text_slider, self._text_opacity, self._txt_op_lbl),
            ):
                blocked = slider.blockSignals(True)
                slider.setValue(value)
                slider.blockSignals(blocked)
                label.setText(opacity_percent_label(value))
        elif section_id == "accent":
            accent_source, point_hex = initial["accent"]
            self._accent_source = str(accent_source)
            self._point_hex = str(point_hex)
            self._theme_hex = self._point_hex
        elif section_id == "readability":
            text_source, text_values = initial["readability"]
            self._text_source = str(text_source)
            if text_values:
                self._set_text_row_values(
                    dict(
                        zip(
                            ("primary", "secondary", "muted", "faint", "input"),
                            text_values,
                            strict=True,
                        )
                    )
                )
                self._input_bg = str(text_values[-1])
        elif section_id == "font":
            font_family, font_size = initial["font"]
            from PyQt6.QtGui import QFont

            combo_blocked = self._font_combo.blockSignals(True)
            size_blocked = self._font_size_spin.blockSignals(True)
            self._font_combo.setCurrentFont(QFont(str(font_family)))
            self._font_size_spin.setValue(int(font_size))
            self._font_combo.blockSignals(combo_blocked)
            self._font_size_spin.blockSignals(size_blocked)
            from calendar_app.presentation.main_window.window_ui_actions import build_ui_font

            self._font_preview.setFont(build_ui_font(str(font_family), int(font_size)))

        if finalize:
            self._sync_controls_after_restore()

    def _restore_all_appearance_changes(self):
        initial = getattr(self, "_initial_appearance_state", None)
        if not initial:
            return
        for section_id in ("style", "accent", "readability", "font"):
            self._restore_appearance_section(section_id, finalize=False)
        self._dialog_color_overrides = dict(initial["expert"][0])
        self._dialog_metric_overrides = dict(initial["expert"][1])
        self._text_theme = self._initial_text_theme
        self._accent_source = self._initial_accent_source
        self._text_source = self._initial_text_source
        for row in (
            self._row_primary,
            self._row_secondary,
            self._row_muted,
            self._row_faint,
            self._row_input_bg,
        ):
            row.mark_current_as_original()
        self._sync_controls_after_restore()

    def _selected_style_family_id(self) -> str:
        if self._selected_preset is None or self._selected_preset >= len(_PRESETS):
            return ""
        return _FAMILY_BY_PRESET_KEY.get(_PRESETS[self._selected_preset][0], "")

    def handle_system_theme_change(self, resolved_theme: str):
        resolved = str(resolved_theme or "").lower()
        if self._appearance_mode != "auto" or resolved not in {"dark", "light"}:
            return
        family_id = self._selected_style_family_id()
        family = next((item for item in _STYLE_FAMILIES if item[0] == family_id), None)
        if family is None:
            self._last_preview_state = None
            self._refresh_preview()
            return

        changed_before = set(self._appearance_change_categories())
        _, dark_key, light_key = family
        preset_key = light_key if resolved == "light" else dark_key
        preset_index = _PRESET_INDEX_BY_KEY[preset_key]
        _, _, base, accent, text_dict = _PRESETS[preset_index]
        self._selected_preset = preset_index
        self._preset_filter_mode = resolved
        self._base_hex = base
        self._text_theme = "auto"
        if self._accent_source == "family":
            self._point_hex = accent
            self._theme_hex = accent

        self._row_primary.set_default(text_dict["primary"])
        self._row_secondary.set_default(text_dict["secondary"])
        self._row_muted.set_default(text_dict["muted"])
        self._row_faint.set_default(text_dict["faint"])
        if self._text_source == "family":
            self._apply_preset_text_colors(refresh=False)
            for row in (
                self._row_primary,
                self._row_secondary,
                self._row_muted,
                self._row_faint,
                self._row_input_bg,
            ):
                row.mark_current_as_original()

        current = self._appearance_state()
        for category in ("style", "accent", "readability"):
            if category not in changed_before:
                self._initial_appearance_state[category] = current[category]
        if "style" not in changed_before:
            self._initial_selected_preset = preset_index
            self._initial_preset_filter_mode = resolved
        if "accent" not in changed_before:
            self._point_hex_original = self._point_hex
            self._initial_accent_source = self._accent_source
        if "readability" not in changed_before:
            self._initial_text_source = self._text_source
        self._last_preview_state = None
        self._sync_controls_after_restore()

    def _appearance_state(self) -> dict[str, object]:
        text_values = ()
        if hasattr(self, "_row_primary"):
            text_values = (
                self._row_primary.hex_value(),
                self._row_secondary.hex_value(),
                self._row_muted.hex_value(),
                self._row_faint.hex_value(),
                self._row_input_bg.hex_value(),
            )
        font_values = ()
        if hasattr(self, "_font_combo"):
            font_values = (self.selected_font_family(), self.selected_font_size())
        return {
            "style": (
                self._base_hex.lower(),
                self._appearance_mode,
                self._opacity,
                self._border_opacity,
                self._text_opacity,
            ),
            "accent": (self._accent_source, self._point_hex.lower()),
            "readability": (self._text_source, text_values),
            "font": font_values,
            "expert": (
                tuple(sorted(self._dialog_color_overrides.items())),
                tuple(sorted(self._dialog_metric_overrides.items())),
            ),
        }

    def _appearance_change_categories(self) -> list[str]:
        initial = getattr(self, "_initial_appearance_state", None)
        if not initial:
            return []
        current = self._appearance_state()
        return [
            key
            for key in ("style", "accent", "readability", "font", "expert")
            if current[key] != initial[key]
        ]

    def _update_change_summary(self):
        label = getattr(self, "_change_summary_label", None)
        apply_btn = getattr(self, "_apply_btn", None)
        if label is None or apply_btn is None:
            return
        categories = self._appearance_change_categories()
        count = len(categories)
        if count:
            message = t(
                "dialog.theme.changes_count",
                "{count} changes",
                count=count,
            )
        else:
            message = t("dialog.theme.changes_none", "No changes")
        label.setText(message)
        label.setAccessibleName(message)
        apply_btn.setEnabled(count > 0)
        apply_btn.setAccessibleDescription(message)
        revert_all = getattr(self, "_revert_all_btn", None)
        if revert_all is not None:
            revert_all.setEnabled(count > 0)
            revert_all.setAccessibleDescription(message)
        changed = set(categories)
        for section_id, button in getattr(self, "_section_reset_buttons", {}).items():
            button.setEnabled(section_id in changed)

    def _apply_preset_text_colors(self, _checked=False, *, refresh: bool = True):
        """Calculates and applies recommended text colors for the current background."""
        idx = self._selected_preset
        if idx is not None:
            _, _, _, _, text_dict = _PRESETS[idx]
            if "input" in text_dict:
                input_color = text_dict["input"]
            else:
                base_color = QColor(self._base_hex)
                if base_color.isValid() and base_color.lightnessF() > 0.55:
                    input_color = "#ffffff"
                else:
                    input_color = (
                        _shift_rgb(base_color, -16).name(QColor.NameFormat.HexRgb)
                        if base_color.isValid()
                        else "#0a0a0a"
                    )
            values = {
                "primary": text_dict["primary"],
                "secondary": text_dict["secondary"],
                "muted": text_dict["muted"],
                "faint": text_dict["faint"],
                "input": text_dict.get("input", input_color),
            }
        else:
            # Custom color logic
            c = QColor(self._base_hex)
            is_light = c.lightnessF() > 0.55
            if is_light:
                values = {
                    "primary": "#1a1a1a",
                    "secondary": "#444444",
                    "muted": "#777777",
                    "faint": "#aaaaaa",
                    "input": "#ffffff",
                }
            else:
                values = {
                    "primary": "#ffffff",
                    "secondary": "#e0e0e0",
                    "muted": "#b0b0b0",
                    "faint": "#808080",
                    "input": _shift_rgb(c, -16).name(QColor.NameFormat.HexRgb),
                }
        self._set_text_row_values(values)
        self._text_source = "family" if idx is not None else "custom"
        self._update_contrast_status()
        if refresh:
            self._refresh_preview()

    def selected_input_bg(self) -> str:
        return (
            self._row_input_bg.hex_value() if hasattr(self, "_row_input_bg") else "rgba(0,0,0,0.2)"
        )

    # ------------------------------------------------------------------
    # Result accessors
    # ------------------------------------------------------------------

    def selected_base_hex(self) -> str:
        return self._base_hex

    def selected_style_family(self) -> str:
        return self._selected_style_family_id()

    def selected_accent_source(self) -> str:
        return self._accent_source

    def selected_style_family_variants(self) -> dict[str, str]:
        family_id = self._selected_style_family_id()
        family = next((item for item in _STYLE_FAMILIES if item[0] == family_id), None)
        if family is None:
            return {}
        _, dark_key, light_key = family
        dark = _PRESET_BY_KEY[dark_key]
        light = _PRESET_BY_KEY[light_key]
        return {
            "dark_base": dark[2],
            "dark_accent": dark[3],
            "light_base": light[2],
            "light_accent": light[3],
        }

    def selected_point_hex(self) -> str:
        """포인트 컬러 탭에서 지정한 색상을 반환."""
        return self._point_hex

    def selected_text_theme(self) -> str:
        """현재 선택된 텍스트 테마 (dark, light, custom)."""
        if self.text_colors_changed():
            return "custom"
        return self._text_theme

    def point_color_changed(self) -> bool:
        return self._point_hex != self._point_hex_original

    def selected_theme_hex(self) -> str | None:
        """하위호환용. 포인트 컬러가 변경된 경우 반환."""
        if self.point_color_changed():
            return self._point_hex
        return None

    def selected_opacity(self) -> int:
        """배경 불투명도 0~255."""
        return self._opacity

    def selected_border_opacity(self) -> int:
        """테두리 불투명도 0~255."""
        return self._border_opacity

    def selected_text_opacity(self) -> int:
        """글씨 불투명도 0~255."""
        return self._text_opacity

    def text_primary_hex(self) -> str:
        return self._row_primary.hex_value()

    def text_secondary_hex(self) -> str:
        return self._row_secondary.hex_value()

    def text_muted_hex(self) -> str:
        return self._row_muted.hex_value()

    def text_faint_hex(self) -> str:
        return self._row_faint.hex_value()

    def text_colors_changed(self) -> bool:
        return (
            self._row_primary.is_changed()
            or self._row_secondary.is_changed()
            or self._row_muted.is_changed()
            or self._row_faint.is_changed()
            or self._row_input_bg.is_changed()
        )

    def selected_font_family(self) -> str:
        return self._font_combo.currentFont().family()

    def selected_font_size(self) -> int:
        return self._font_size_spin.value()

    def font_changed(self) -> bool:
        return (
            self.selected_font_family() != self._font_family_orig
            or self.selected_font_size() != self._font_size_orig
        )

    def _build_font_tab(self) -> QWidget:
        from calendar_app.presentation.main_window.window_ui_actions import build_ui_font

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(14)

        tok = self._ui_tokens
        text_muted = tok.get("text_muted", "rgba(255,255,255,0.50)")
        text_secondary = tok.get("text_secondary", "rgba(255,255,255,0.75)")

        hint = QLabel(t("dialog.theme.font.subtitle", "앱 전체 UI 글꼴을 설정합니다."))
        hint.setStyleSheet(f"font-size: 12px; color: {text_muted};")
        lay.addWidget(hint)

        # 폰트 패밀리
        family_row = QHBoxLayout()
        family_lbl = QLabel(t("dialog.theme.font.family", "글꼴:"))
        family_lbl.setStyleSheet(f"font-size: 13px; color: {text_secondary};")
        family_lbl.setFixedWidth(60)
        self._font_combo = QFontComboBox()
        self._font_combo.setFontFilters(QFontComboBox.FontFilter.ScalableFonts)
        app_font = QApplication.instance().font()
        init_family = self._font_family_orig or app_font.family()
        from PyQt6.QtGui import QFont

        self._font_combo.setCurrentFont(QFont(init_family))
        font_popup_label = t("dialog.theme.font.open_list", "글꼴 목록 펼치기")
        self._font_popup_btn = QPushButton()
        self._font_popup_btn.setObjectName("fontComboPopupButton")
        icon_color = parse_hex_color(text_secondary, "#c8ccd4").name(QColor.NameFormat.HexRgb)
        self._font_popup_btn.setIcon(_ic(ICON.NAV_DOWN, color=icon_color))
        self._font_popup_btn.setFixedSize(34, 34)
        self._font_popup_btn.setToolTip(font_popup_label)
        self._font_popup_btn.setAccessibleName(font_popup_label)
        self._font_popup_btn.setAccessibleDescription(font_popup_label)
        self._font_popup_btn.clicked.connect(self._font_combo.showPopup)
        family_row.addWidget(family_lbl)
        family_row.addWidget(self._font_combo, 1)
        family_row.addWidget(self._font_popup_btn)
        lay.addLayout(family_row)

        # 폰트 크기
        size_row = QHBoxLayout()
        size_lbl = QLabel(t("dialog.theme.font.size", "크기:"))
        size_lbl.setStyleSheet(f"font-size: 13px; color: {text_secondary};")
        size_lbl.setFixedWidth(60)
        self._font_size_spin = QSpinBox()
        self._font_size_spin.installEventFilter(self._wheel_blocker)
        self._font_size_spin.setRange(7, 24)
        init_size = (
            self._font_size_orig
            if self._font_size_orig > 0
            else (app_font.pointSize() if app_font.pointSize() > 0 else 10)
        )
        self._font_size_spin.setValue(init_size)
        self._font_size_spin.setSuffix(" pt")
        size_row.addWidget(size_lbl)
        size_row.addWidget(self._font_size_spin)
        size_row.addStretch()
        lay.addLayout(size_row)

        # 미리보기
        pre_lbl = QLabel(t("dialog.theme.preview.title", "미리보기:"))
        pre_lbl.setStyleSheet(f"font-size: 12px; color: {text_muted};")
        lay.addWidget(pre_lbl)

        self._font_preview = QLabel(
            t("dialog.theme.font.preview_sample", "가나다 ABC abc 123  오늘 할 일을 정리하세요.")
        )
        self._font_preview.setWordWrap(True)
        self._font_preview.setStyleSheet(
            f"color: {text_secondary}; border: 1px solid {tok.get('border', tok.get('border_soft', 'rgba(255,255,255,0.10)'))};"
            f"border-radius: {tok.get('field_radius', '4px')}; padding: 10px; background: {tok.get('bg_item', tok.get('surface_item', 'rgba(255,255,255,0.04)'))};"
        )
        lay.addWidget(self._font_preview)

        def _update_font_preview():
            sz = self._font_size_spin.value()
            f = build_ui_font(self._font_combo.currentFont().family(), sz)
            self._font_preview.setFont(f)
            self._update_change_summary()

        self._font_combo.currentFontChanged.connect(lambda _: _update_font_preview())
        self._font_size_spin.valueChanged.connect(lambda _: _update_font_preview())
        _update_font_preview()

        lay.addStretch()
        return w

    def _open_token_editor(self):
        """현재 모양 초안을 공유하는 고급 설정 서브 다이얼로그를 엽니다."""
        from calendar_app.presentation.dialogs.dialog_token_editor_dialog import (
            DialogTokenEditorDialog,
        )

        draft_tokens = get_dialog_theme_tokens(
            theme_color=self._point_hex,
            text_theme=self._resolved_dialog_text_theme(),
            panel_base_color=self._base_hex,
            apply_overrides=False,
        )
        if hasattr(self, "_row_primary"):
            draft_tokens.update(
                {
                    "text_primary": self._row_primary.hex_value(),
                    "text_secondary": self._row_secondary.hex_value(),
                    "text_muted": self._row_muted.hex_value(),
                    "text_faint": self._row_faint.hex_value(),
                    "placeholder_text": self._row_faint.hex_value(),
                    "title_text": self._row_primary.hex_value(),
                    "title_subtext": self._row_muted.hex_value(),
                    "input_bg": self._row_input_bg.hex_value(),
                }
            )

        dlg = DialogTokenEditorDialog(
            self,
            theme_color=self._point_hex,
            text_theme=self._resolved_dialog_text_theme(),
            panel_base_color=self._base_hex,
            base_tokens=draft_tokens,
            initial_color_overrides=self._dialog_color_overrides,
            initial_metric_overrides=self._dialog_metric_overrides,
            persist_on_apply=False,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._dialog_color_overrides = dlg.selected_color_overrides()
            self._dialog_metric_overrides = dlg.selected_metric_overrides()
            self._update_change_summary()

    def selected_dialog_color_overrides(self) -> dict:
        return dict(self._dialog_color_overrides)

    def selected_dialog_metric_overrides(self) -> dict:
        return dict(self._dialog_metric_overrides)
