"""UI 테마 지정 다이얼로그 — 배경색 프리셋, 글자색, 투명도 통합."""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFontComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
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
    ):
        super().__init__(parent)
        self._building = True  # suppress redundant _refresh_preview during init
        apply_dialog_title(self, t("dialog.theme.title", "UI 테마"))
        self.setMinimumWidth(620)
        self._wheel_blocker = WheelBlocker(self)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._base_hex = current_base
        self._theme_hex = current_theme
        self._point_hex = current_theme
        self._point_hex_original = current_theme
        self._opacity = max(0, min(255, current_opacity))
        self._border_opacity = max(0, min(255, current_border_opacity))
        self._text_opacity = max(0, min(255, current_text_opacity))
        self._input_bg = current_input_bg
        self._selected_preset: int | None = None
        self._preset_filter_mode: str = "light" if _is_light_base_color(current_base) else "dark"
        self._preset_modes: list[str] = []
        self._preset_btns: list[QPushButton] = []
        self._preset_grid: QGridLayout | None = None
        self._preset_filter_btns: dict[str, QPushButton] = {}
        self._text_theme = current_text_theme
        self._font_family_orig = current_font_family
        self._font_size_orig = current_font_size

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
        self._auto_select_matching_preset()
        self._building = False
        self._refresh_preview()

    def is_light_mode(self) -> bool:
        return self._text_theme == "light"

    @staticmethod
    def _parse_color_str(val: str, fallback: str) -> str:
        c = QColor(val)
        if c.isValid():
            return c.name(QColor.NameFormat.HexRgb)
        return QColor(fallback).name(QColor.NameFormat.HexRgb)

    def _resolved_dialog_text_theme(self) -> str:
        if self._text_theme in {"dark", "light"}:
            return self._text_theme
        return "light" if _is_light_base_color(self._base_hex) else "dark"

    def _rebuild_theme_context(self):
        self._theme_snapshot = build_theme_snapshot(
            theme_color=self._theme_hex,
            text_theme=self._resolved_dialog_text_theme(),
            panel_base_color=self._base_hex,
            opacity_factor=self._opacity / 255.0,
            input_bg=self._input_bg,
        )
        self._ui_tokens = get_ui_tokens(snapshot=self._theme_snapshot)
        self._dialog_metrics = get_dialog_metric_tokens(apply_overrides=True)

    def _auto_select_matching_preset(self):
        """Auto-select matching preset based on current base color."""
        matched = False
        for i, (name_key, _, base, _, _) in enumerate(_PRESETS):
            if base.lower() == self._base_hex.lower():
                self._selected_preset = i
                mode = _preset_mode_for_key(name_key)
                self._text_theme = mode
                if mode in {"dark", "light"}:
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

    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)

        lbl_title = QLabel(t("dialog.theme.title", "UI 테마"))
        lbl_title.setStyleSheet(
            f"font-size: 15px; font-weight: bold; color: {self._ui_tokens.get('text_primary', '#ffffff')};"
        )
        root.addWidget(lbl_title)

        tabs = QTabWidget()
        tabs.addTab(self._build_bg_tab(), t("dialog.theme.tab.background", "배경"))
        tabs.addTab(self._build_text_tab(), t("dialog.theme.tab.text", "글자"))
        tabs.addTab(self._build_point_tab(), t("dialog.theme.tab.accent", "포인트"))
        tabs.addTab(self._build_font_tab(), t("dialog.theme.tab.font", "폰트"))
        root.addWidget(tabs)

        # ---- Preview ----
        lbl_pre = QLabel(t("dialog.theme.preview.title", "미리보기"))
        lbl_pre.setStyleSheet(
            f"font-size: 12px; font-weight: bold; color: {self._ui_tokens.get('text_muted', 'rgba(255,255,255,0.55)')};"
        )
        root.addWidget(lbl_pre)

        self._preview_container = QVBoxLayout()
        self._preview_container.setContentsMargins(0, 0, 0, 0)
        # Create preview frame once to avoid flickering
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
        root.addLayout(self._preview_container)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(
            f"border: none; border-top: 1px solid {self._ui_tokens.get('border_soft', 'rgba(255,255,255,0.10)')};"
        )
        root.addWidget(sep)

        # 하단 행: 고급 토큰 편집 버튼(좌) + Ok/Cancel(우)
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        adv_btn = QPushButton(t("dialog.theme.advanced", "고급 토큰"))
        adv_btn.setIcon(_ic(ICON.ADVANCED))
        adv_btn.setToolTip(t("dialog.theme.advanced_tip", "상세 색상 토큰 편집"))
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

        bottom_row.addStretch(1)

        from calendar_app.presentation.dialogs.dialog_styles import build_dialog_footer

        _, ok_btn, cancel_btn = build_dialog_footer(
            ok_label=t("common.apply", "적용"),
            cancel_label=t("common.cancel", "취소"),
        )
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        bottom_row.addWidget(ok_btn)
        bottom_row.addWidget(cancel_btn)
        root.addLayout(bottom_row)

    # ------------------------------------------------------------------
    def _build_bg_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        lbl_sub = QLabel(
            t(
                "dialog.theme.bg.subtitle",
                "Choose a preset palette or pick a custom background color.",
            )
        )
        lbl_sub.setStyleSheet(
            f"font-size: 12px; color: {self._ui_tokens.get('text_muted', 'rgba(255,255,255,0.50)')};"
        )
        lay.addWidget(lbl_sub)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)

        filter_lbl = QLabel(t("dialog.theme.preset.filter_label", "Preset Type"))
        filter_lbl.setStyleSheet(
            f"font-size: 11px; color: {self._ui_tokens.get('text_faint', 'rgba(255,255,255,0.45)')};"
        )
        filter_row.addWidget(filter_lbl)

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
            filter_row.addWidget(btn)

        filter_row.addStretch()
        lay.addLayout(filter_row)

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
        lay.addWidget(self._chk_auto_apply_preset_text)

        self._preset_btns = []
        self._preset_modes = []
        grid_widget = QWidget()
        self._preset_grid = QGridLayout(grid_widget)
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
        lay.addWidget(grid_widget)

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
        lay.addLayout(btn_row)

        _lbl_ss = f"font-size: 12px; color: {self._ui_tokens.get('text_secondary', 'rgba(255,255,255,0.70)')};"
        _val_ss = f"font-size: 12px; color: {self._ui_tokens.get('text_muted', 'rgba(255,255,255,0.50)')};"

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(
            f"border: none; border-top: 1px solid {self._ui_tokens.get('border_soft', 'rgba(255,255,255,0.10)')}; margin: 2px 0;"
        )
        lay.addWidget(sep2)

        op_header = QLabel(t("dialog.theme.opacity", "불투명도"))
        op_header.setStyleSheet(
            f"font-size: 11px; font-weight: bold; color: {self._ui_tokens.get('text_muted', 'rgba(255,255,255,0.50)')};"
        )
        lay.addWidget(op_header)
        op_hint = QLabel(t("dialog.theme.opacity_hint", "0% = 완전 투명, 100% = 완전 불투명"))
        op_hint.setStyleSheet(
            f"font-size: 11px; color: {self._ui_tokens.get('text_faint', 'rgba(255,255,255,0.42)')};"
        )
        lay.addWidget(op_hint)

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

        lay.addLayout(bg_row)
        lay.addLayout(bd_row)
        lay.addLayout(txt_row)

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
            row.color_changed.connect(self._refresh_preview)

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

        return w

    def _reset_all_text(self):
        for row in (self._row_primary, self._row_secondary, self._row_muted, self._row_faint):
            row._hex = row._default
            row._update_swatch()
        self._refresh_preview()

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
        self._rebuild_theme_context()
        for i, btn in enumerate(self._point_btns):
            btn.setStyleSheet(self._point_btn_ss(i == idx))
        self._refresh_point_display()
        self._refresh_preview()

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
        self._rebuild_theme_context()
        # 프리셋 선택 해제
        for btn in self._point_btns:
            btn.setStyleSheet(self._point_btn_ss(False))
        self._refresh_point_display()
        self._refresh_preview()

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

    def _apply_preset_text_colors(self):
        """선택된 프리셋의 권장 글자색을 각 행에 적용."""
        if self._selected_preset is None:
            return
        _, _, _, _, text_dict = _PRESETS[self._selected_preset]
        self._row_primary.set_value(text_dict["primary"])
        self._row_secondary.set_value(text_dict["secondary"])
        self._row_muted.set_value(text_dict["muted"])
        self._row_faint.set_value(text_dict["faint"])

    # ------------------------------------------------------------------
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
    def _select_preset(self, idx: int):
        self._selected_preset = idx
        name_key, _, base, theme, text_dict = _PRESETS[idx]
        self._base_hex = base
        self._theme_hex = theme
        mode = _preset_mode_for_key(name_key)
        self._text_theme = mode  # Update text_theme to match preset mode (dark/light)
        self._rebuild_theme_context()

        if mode in {"dark", "light"} and self._preset_filter_mode != mode:
            self._preset_filter_mode = mode
            self._refresh_preset_filter_buttons()
            self._rebuild_preset_grid()
        for i, btn in enumerate(self._preset_btns):
            btn.setStyleSheet(self._preset_btn_ss(i == idx))

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
            self._apply_preset_text_colors()

        self._refresh_preview()

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
        self._preset_filter_mode = "light" if _is_light_base_color(self._base_hex) else "dark"
        for btn in self._preset_btns:
            btn.setStyleSheet(self._preset_btn_ss(False))
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
        self._refresh_preview()

    def _on_opacity_changed(self, value: int):
        self._opacity = value
        self._op_lbl.setText(opacity_percent_label(value))
        self._refresh_preview()

    def _on_border_opacity_changed(self, value: int):
        self._border_opacity = value
        self._bd_op_lbl.setText(opacity_percent_label(value))
        self._refresh_preview()

    def _on_text_opacity_changed(self, value: int):
        self._text_opacity = value
        self._txt_op_lbl.setText(opacity_percent_label(value))
        self._refresh_preview()

    def _refresh_preview(self):
        if getattr(self, "_building", False):
            return

        if hasattr(self, "_row_input_bg"):
            self._input_bg = self._row_input_bg.hex_value()
        self._rebuild_theme_context()

        # Update swatch displays in the tab
        px = QPixmap(22, 22)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(self._base_hex))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(1, 1, 20, 20, 4, 4)
        p.end()
        if hasattr(self, "_swatch_lbl"):
            self._swatch_lbl.setPixmap(px)
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

    def _apply_preset_text_colors(self):
        """Calculates and applies recommended text colors for the current background."""
        idx = self._selected_preset
        if idx is not None:
            _, _, _, _, text_dict = _PRESETS[idx]
            self._row_primary.set_value(text_dict["primary"])
            self._row_secondary.set_value(text_dict["secondary"])
            self._row_muted.set_value(text_dict["muted"])
            self._row_faint.set_value(text_dict["faint"])
            if "input" in text_dict:
                self._row_input_bg.set_value(text_dict["input"])
            else:
                base_color = QColor(self._base_hex)
                if base_color.isValid() and base_color.lightnessF() > 0.55:
                    self._row_input_bg.set_value("#ffffff")
                else:
                    self._row_input_bg.set_value(
                        _shift_rgb(base_color, -16).name(QColor.NameFormat.HexRgb)
                        if base_color.isValid()
                        else "#0a0a0a"
                    )
        else:
            # Custom color logic
            c = QColor(self._base_hex)
            is_light = c.lightnessF() > 0.55
            if is_light:
                self._row_primary.set_value("#1a1a1a")
                self._row_secondary.set_value("#444444")
                self._row_muted.set_value("#777777")
                self._row_faint.set_value("#aaaaaa")
                self._row_input_bg.set_value("#ffffff")
            else:
                self._row_primary.set_value("#ffffff")
                self._row_secondary.set_value("#e0e0e0")
                self._row_muted.set_value("#b0b0b0")
                self._row_faint.set_value("#808080")
                self._row_input_bg.set_value(_shift_rgb(c, -16).name(QColor.NameFormat.HexRgb))
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
        family_row.addWidget(family_lbl)
        family_row.addWidget(self._font_combo, 1)
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

        self._font_combo.currentFontChanged.connect(lambda _: _update_font_preview())
        self._font_size_spin.valueChanged.connect(lambda _: _update_font_preview())
        _update_font_preview()

        lay.addStretch()
        return w

    def _open_token_editor(self):
        """고급 UI 토큰 편집 서브 다이얼로그를 엽니다."""
        from calendar_app.presentation.dialogs.dialog_token_editor_dialog import (
            DialogTokenEditorDialog,
        )

        dlg = DialogTokenEditorDialog(self)
        dlg.exec()
