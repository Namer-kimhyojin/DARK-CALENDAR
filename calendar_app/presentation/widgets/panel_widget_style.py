"""Premium widget-mode stylesheet helpers.

The widget mode leans on a layered editorial card language:
  - soft multi-stop surfaces instead of flat panels
  - thin luminous borders instead of hard separators
  - strong typography hierarchy with restrained accent use
  - light interaction feedback without heavy visual effects
"""

from __future__ import annotations

import re

from PyQt6.QtGui import QColor

from calendar_app.shared.theme_snapshot import build_widget_mode_tokens

_RGBA_RE = re.compile(
    r"^rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*([0-9]*\.?[0-9]+)\s*\)$",
    re.IGNORECASE,
)


def css_to_qcolor(value: object, fallback: str = "#000000") -> QColor:
    raw = str(value or "").strip()
    if raw:
        match = _RGBA_RE.match(raw)
        if match:
            try:
                r, g, b, a_raw = match.groups()
                alpha = float(a_raw)
                if alpha <= 1.0:
                    alpha *= 255.0
                return QColor(
                    max(0, min(255, int(r))),
                    max(0, min(255, int(g))),
                    max(0, min(255, int(b))),
                    max(0, min(255, int(round(alpha)))),
                )
            except Exception:
                pass
        resolved = QColor(raw)
        if resolved.isValid():
            return resolved
    fallback_color = QColor(fallback)
    return fallback_color if fallback_color.isValid() else QColor("#000000")


def rgba(value: object, alpha: int, fallback: str = "#000000") -> str:
    qcolor = value if isinstance(value, QColor) else css_to_qcolor(value, fallback)
    return (
        f"rgba({qcolor.red()}, {qcolor.green()}, {qcolor.blue()}, {max(0, min(255, int(alpha)))})"
    )


def blend(base: QColor, mix: QColor, ratio: float) -> QColor:
    clamped = max(0.0, min(1.0, float(ratio)))
    return QColor(
        int(round(base.red() * (1 - clamped) + mix.red() * clamped)),
        int(round(base.green() * (1 - clamped) + mix.green() * clamped)),
        int(round(base.blue() * (1 - clamped) + mix.blue() * clamped)),
    )


def int_token(tokens: dict[str, str], key: str, default: int) -> int:
    try:
        return max(0, int(float(tokens.get(key, default))))
    except Exception:
        return int(default)


def resolve_tokens(
    tokens: dict[str, str] | None = None,
    *,
    settings=None,
    preset_name: str | None = None,
) -> dict[str, str]:
    resolved = dict(
        build_widget_mode_tokens(settings=settings, preset_name=preset_name or "Light Aqua Form")
    )
    if tokens:
        resolved.update(tokens)
    return resolved


def apply_dark_theme(tokens: dict[str, str]) -> dict[str, str]:
    updated = dict(tokens)

    accent_q = css_to_qcolor(updated.get("accent", "#4da6ff"), "#4da6ff")
    ink_q = QColor("#0b1018")
    layer_q = QColor("#111826")
    card_q = QColor("#141f31")
    wash_q = blend(accent_q, QColor("#ffffff"), 0.18)

    updated.update(
        {
            "text_primary": "#f4f7ff",
            "text_secondary": "#c0cade",
            "text_faint": "#7c88a3",
            "calendar_text": "#eff4ff",
            "calendar_muted": "#8995af",
            "card_text_primary": "#f5f8ff",
            "card_text_secondary": "#c5d0e3",
            "panel_bg": rgba(ink_q, 238),
            "panel_bg_start": rgba(blend(ink_q, accent_q, 0.08), 248),
            "panel_bg_mid": rgba(blend(layer_q, accent_q, 0.10), 244),
            "panel_bg_end": rgba(blend(card_q, QColor("#ffffff"), 0.02), 244),
            "header_bg": rgba(blend(layer_q, QColor("#ffffff"), 0.02), 236),
            "header_shell_bg": rgba(blend(layer_q, accent_q, 0.07), 232),
            "header_shell_border": rgba("#ffffff", 26),
            "surface_bg": rgba(layer_q, 214),
            "surface_alt": rgba(card_q, 196),
            "section_bg": rgba(card_q, 178),
            "section_bg_alt": rgba(blend(card_q, accent_q, 0.12), 222),
            "section_border": rgba("#ffffff", 22),
            "section_border_soft": rgba("#ffffff", 12),
            "panel_border": rgba(blend(wash_q, QColor("#ffffff"), 0.55), 40),
            "panel_border_soft": rgba("#ffffff", 16),
            "card_bg": rgba(card_q, 194),
            "card_hover": rgba(blend(card_q, accent_q, 0.16), 232),
            "card_border": rgba("#ffffff", 14),
            "card_pressed": rgba(blend(card_q, accent_q, 0.28), 240),
            "chip_bg": rgba(blend(card_q, accent_q, 0.10), 160),
            "chip_border": rgba(accent_q, 86, accent_q.name()),
            "input_bg": rgba(blend(layer_q, QColor("#ffffff"), 0.02), 214),
            "input_border": rgba("#ffffff", 18),
            "button_bg": rgba(card_q, 172),
            "button_hover": rgba(blend(card_q, accent_q, 0.15), 230),
            "button_text": "#d4dded",
            "accent_deep": blend(accent_q, QColor("#ffffff"), 0.10).name(QColor.NameFormat.HexRgb),
            "hero_bg": rgba(accent_q, 28, accent_q.name()),
            "hero_bg_strong": rgba(accent_q, 56, accent_q.name()),
            "hero_border": rgba(accent_q, 120, accent_q.name()),
            "shell_outline": rgba("#ffffff", 24),
            "shell_outline_soft": rgba("#ffffff", 10),
            "scroll_track": rgba(ink_q, 88),
            "scroll_thumb": rgba(accent_q, 72, accent_q.name()),
            "scroll_thumb_hover": rgba(accent_q, 112, accent_q.name()),
        }
    )
    return updated


def panel_stylesheet(tokens: dict[str, str], *, scale: float = 1.0) -> str:
    tk = tokens
    s = max(0.75, float(scale or 1.0))
    surface_radius = int(round(int_token(tk, "widget_surface_radius", 18) * s))
    header_radius = int(round(int_token(tk, "widget_header_radius", 14) * s))
    control_radius = int(round(int_token(tk, "widget_control_radius", 11) * s))
    chip_radius = int(round(int_token(tk, "widget_chip_radius", 12) * s))
    card_radius = int(round(int_token(tk, "widget_entry_radius", 12) * s))
    input_radius = int(round(int_token(tk, "widget_input_radius", 12) * s))
    return f"""
        QWidget#widget_mode_panel {{
            background: transparent;
        }}
        QFrame#widget_mode_surface {{
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 1,
                stop: 0 {tk.get("panel_bg_start", tk["panel_bg"])},
                stop: 0.46 {tk.get("panel_bg_mid", tk["panel_bg"])},
                stop: 1 {tk.get("panel_bg_end", tk["panel_bg"])}
            );
            border: 1px solid {tk.get("panel_border", "rgba(255,255,255,24)")};
            border-radius: {surface_radius}px;
        }}
        QFrame#widget_mode_header {{
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 0,
                stop: 0 {tk.get("header_shell_bg", tk["header_bg"])},
                stop: 1 {tk.get("surface_alt", tk["header_bg"])}
            );
            border: 1px solid {tk.get("header_shell_border", tk.get("panel_border_soft", "rgba(255,255,255,18)"))};
            border-radius: {header_radius}px;
        }}
        QLabel#widget_mode_header_icon {{
            color: {tk.get("accent_deep", tk["text_primary"])};
            font-size: {8.2 * s}pt;
            font-weight: 800;
            letter-spacing: 1.5px;
            background: {tk.get("hero_bg", tk["section_bg"])};
            border: 1px solid {tk.get("hero_border", tk["panel_border_soft"])};
            border-radius: {control_radius}px;
            min-width: {int(round(26 * s))}px;
            min-height: {int(round(26 * s))}px;
            padding: 0px 4px;
        }}
        QLabel#widget_mode_header_title {{
            color: {tk["text_primary"]};
            font-size: {10.4 * s}pt;
            font-weight: 700;
            letter-spacing: 0.4px;
            background: transparent;
            border: none;
        }}
        QToolButton#widget_mode_restore_btn,
        QToolButton#widget_mode_close_btn {{
            color: {tk.get("button_text", tk["text_secondary"])};
            background: {tk.get("button_bg", tk["section_bg"])};
            border: 1px solid {tk.get("section_border_soft", tk["panel_border_soft"])};
            border-radius: {control_radius}px;
            padding: 4px 9px;
            min-height: {int(round(24 * s))}px;
            font-size: {7.8 * s}pt;
            font-weight: 600;
            letter-spacing: 0.4px;
        }}
        QToolButton#widget_mode_restore_btn:hover,
        QToolButton#widget_mode_close_btn:hover {{
            color: {tk["text_primary"]};
            background: {tk.get("button_hover", tk["section_bg_alt"])};
            border: 1px solid {tk.get("hero_border", tk["panel_border"])};
        }}
        QFrame#widget_mode_content_container,
        QFrame#widget_mode_size_grip_container,
        QFrame#widget_mode_accent_bar {{
            background: transparent;
            border: none;
        }}
        QFrame#widget_mode_meta_bar {{
            background: {tk.get("surface_alt", tk["section_bg"])};
            border: 1px solid {tk.get("section_border_soft", tk["panel_border_soft"])};
            border-radius: {chip_radius + 2}px;
            padding: 4px 6px;
        }}
        QLabel#widget_mode_meta_hint {{
            color: {tk.get("text_faint", tk["text_secondary"])};
            background: transparent;
            border: none;
        }}
        QLabel#widget_entry_empty {{
            qproperty-alignment: AlignLeft | AlignVCenter;
        }}
        QFrame#widget_entry_actions {{
            background: transparent;
            border: none;
        }}
        QFrame#widget_entry_divider {{
            background: {tk.get("section_border_soft", "rgba(255,255,255,12)")};
            border-radius: 1px;
            margin: 4px 10px;
        }}
        QPushButton#widget_entry_btn {{
            color: transparent;
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 1,
                stop: 0 {tk.get("card_bg", tk["section_bg"])},
                stop: 1 {tk.get("surface_alt", tk["section_bg_alt"])}
            );
            border: 1px solid {tk.get("card_border", tk.get("section_border_soft", "rgba(255,255,255,14)"))};
            border-radius: {card_radius}px;
            padding: 0px;
            text-align: left;
        }}
        QPushButton#widget_entry_btn:hover {{
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 1,
                stop: 0 {tk.get("card_hover", tk["section_bg_alt"])},
                stop: 1 {tk.get("hero_bg_strong", tk["section_bg_alt"])}
            );
            border: 1px solid {tk.get("hero_border", tk["panel_border"])};
        }}
        QPushButton#widget_entry_btn:pressed {{
            background: {tk.get("card_pressed", tk.get("card_hover", tk["section_bg_alt"]))};
        }}
        QPushButton#widget_entry_btn QLabel#widget_entry_title {{
            color: {tk.get("card_text_primary", tk["text_primary"])};
            font-size: {9.2 * s}pt;
            font-weight: 700;
            letter-spacing: 0.1px;
            background: transparent;
        }}
        QPushButton#widget_entry_btn QLabel#widget_entry_time_label {{
            color: {tk.get("accent_deep", tk.get("card_text_primary", tk["text_primary"]))};
            font-size: {7.5 * s}pt;
            font-weight: 700;
            letter-spacing: 0.2px;
            background: transparent;
            padding-top: 2px;
        }}
        QPushButton#widget_entry_btn QLabel#widget_entry_subtitle {{
            color: {tk.get("card_text_secondary", tk["text_secondary"])};
            font-size: {7.9 * s}pt;
            font-weight: 500;
            letter-spacing: 0.15px;
            background: transparent;
            margin-top: 1px;
        }}
        QPushButton#widget_entry_btn QFrame#widget_entry_timeline_col {{
            background: transparent;
            border: none;
        }}
        QPushButton#widget_entry_btn QFrame#widget_entry_timeline_track {{
            background: {tk.get("hero_border", tk.get("chip_border", tk["panel_border"]))};
            border: none;
            border-radius: 1px;
        }}
        QPushButton#widget_entry_btn QFrame#widget_entry_timeline_dot {{
            background: {tk.get("accent", tk.get("hero_border", "#22c3ca"))};
            border: 2px solid {tk.get("hero_bg_strong", tk.get("hero_bg", "rgba(34,195,202,48)"))};
            border-radius: 6px;
        }}
        QToolButton#widget_entry_secondary_btn {{
            color: {tk.get("accent_deep", tk["text_primary"])};
            background: {tk.get("hero_bg", tk.get("chip_bg", "transparent"))};
            border: 1px solid {tk.get("hero_border", tk.get("chip_border", tk["panel_border_soft"]))};
            border-radius: {control_radius}px;
            padding: 4px 10px;
            min-width: {int(round(34 * s))}px;
            min-height: {int(round(30 * s))}px;
            font-size: {8.1 * s}pt;
            font-weight: 700;
            letter-spacing: 0.3px;
        }}
        QToolButton#widget_entry_secondary_btn:hover {{
            color: {tk["text_primary"]};
            background: {tk.get("hero_bg_strong", tk["section_bg_alt"])};
        }}
        QLineEdit {{
            border-radius: {input_radius}px;
        }}
        QScrollBar:vertical {{
            background: {tk.get("scroll_track", "transparent")};
            width: 10px;
            border-radius: 5px;
            margin: 4px 0;
        }}
        QScrollBar::handle:vertical {{
            background: {tk.get("scroll_thumb", tk.get("hero_border", "rgba(0,0,0,0)"))};
            min-height: 28px;
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {tk.get("scroll_thumb_hover", tk.get("hero_border", "rgba(0,0,0,0)"))};
        }}
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical,
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {{
            background: transparent;
            border: none;
        }}
        QSizeGrip {{
            width: 10px;
            height: 10px;
        }}
    """


def entry_style_bundle(tokens: dict[str, str], *, scale: float = 1.0) -> dict[str, str]:
    tk = tokens
    s = max(0.75, float(scale or 1.0))
    card_radius = int(round(int_token(tk, "widget_entry_radius", 12) * s))
    secondary_radius = int(round(int_token(tk, "widget_secondary_radius", 10) * s))
    row_bg = tk.get("section_bg", tk.get("card_bg", "rgba(24,26,34,80)"))
    row_hover = tk.get("section_bg_alt", tk.get("card_hover", row_bg))
    return {
        "empty": (
            f"color: {tk.get('text_faint', '#7c88a3')};"
            f" font-size: {8.7 * s}pt;"
            " font-style: normal;"
            " letter-spacing: 0.2px;"
            " padding: 12px 6px 10px 6px;"
        ),
        "section": (
            f"color: {tk.get('accent_deep', tk['text_secondary'])};"
            f" font-size: {7.3 * s}pt;"
            " font-weight: 800;"
            " letter-spacing: 1.8px;"
            " padding: 10px 2px 4px 2px;"
        ),
        "button": f"""
            QPushButton#widget_entry_btn {{
                color: transparent;
                background: {row_bg};
                border: 1px solid {tk.get("card_border", tk.get("section_border_soft", "rgba(255,255,255,14)"))};
                border-radius: {card_radius}px;
                padding: 0px;
                text-align: left;
            }}
            QPushButton#widget_entry_btn:hover {{
                background: {row_hover};
                border: 1px solid {tk.get("hero_border", tk["panel_border"])};
            }}
            QPushButton#widget_entry_btn:pressed {{
                background: {tk.get("card_pressed", row_hover)};
            }}
            QPushButton#widget_entry_btn QLabel#widget_entry_time_label {{
                color: {tk.get("accent_deep", tk.get("card_text_primary", tk["text_primary"]))};
                font-size: {7.4 * s}pt;
                font-weight: 700;
                letter-spacing: 0.18px;
                background: transparent;
                padding-top: 2px;
            }}
            QPushButton#widget_entry_btn QFrame#widget_entry_timeline_col {{
                background: transparent;
                border: none;
            }}
            QPushButton#widget_entry_btn QFrame#widget_entry_timeline_track {{
                background: {tk.get("hero_border", tk.get("chip_border", tk["panel_border"]))};
                border: none;
                border-radius: 1px;
            }}
            QPushButton#widget_entry_btn QFrame#widget_entry_timeline_dot {{
                background: {tk.get("accent", tk.get("hero_border", "#22c3ca"))};
                border: 2px solid {tk.get("hero_bg_strong", tk.get("hero_bg", "rgba(34,195,202,48)"))};
                border-radius: {int(round(6 * s))}px;
            }}
            QPushButton#widget_entry_btn QLabel#widget_entry_title {{
                color: {tk.get("card_text_primary", tk["text_primary"])};
                font-size: {9.1 * s}pt;
                font-weight: 700;
                background: transparent;
                padding-right: 2px;
            }}
            QPushButton#widget_entry_btn QLabel#widget_entry_subtitle {{
                color: {tk.get("card_text_secondary", tk["text_secondary"])};
                font-size: {7.9 * s}pt;
                font-weight: 500;
                background: transparent;
                padding-top: 1px;
                padding-right: 2px;
            }}
        """,
        "secondary": f"""
            QToolButton#widget_entry_open_btn,
            QToolButton#widget_entry_secondary_btn {{
                color: {tk.get("accent_deep", tk["text_primary"])};
                background: {tk.get("hero_bg", tk.get("chip_bg", "transparent"))};
                border: 1px solid {tk.get("hero_border", tk.get("chip_border", tk["panel_border_soft"]))};
                border-radius: {secondary_radius}px;
                padding: 5px 12px;
                min-width: {int(round(48 * s))}px;
                min-height: {int(round(30 * s))}px;
                font-size: {8.1 * s}pt;
                font-weight: 700;
            }}
            QToolButton#widget_entry_open_btn:hover,
            QToolButton#widget_entry_secondary_btn:hover {{
                color: {tk["text_primary"]};
                background: {tk.get("hero_bg_strong", tk["section_bg_alt"])};
            }}
            QToolButton#widget_entry_secondary_btn {{
                color: {tk.get("button_danger_text", "#9c3348")};
                background: {tk.get("button_danger_bg", rgba("#ff6f91", 28, "#ff6f91"))};
                border: 1px solid {tk.get("button_danger_border", rgba("#ff6f91", 112, "#ff6f91"))};
            }}
            QToolButton#widget_entry_secondary_btn:hover {{
                color: {tk.get("text_primary", "#ffffff")};
                background: {tk.get("button_danger_hover_bg", rgba("#ff6f91", 52, "#ff6f91"))};
                border: 1px solid {tk.get("button_danger_hover_border", "#ff6f91")};
            }}
        """,
    }


def quick_add_stylesheet(tokens: dict[str, str], *, scale: float = 1.0) -> str:
    tk = tokens
    s = max(0.75, float(scale or 1.0))
    input_radius = int(round(int_token(tk, "widget_input_radius", 12) * s))
    submit_radius = int(round(int_token(tk, "widget_submit_radius", 12) * s))
    input_bg = tk.get("input_bg", "rgba(24,26,34,70)")
    input_border = tk.get("input_border", "rgba(255,255,255,16)")
    return f"""
        QLineEdit {{
            color: {tk.get("card_text_primary", tk["text_primary"])};
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 0,
                stop: 0 {input_bg},
                stop: 1 {tk.get("surface_alt", input_bg)}
            );
            border: 1px solid {input_border};
            border-radius: {input_radius}px;
            padding: 7px 13px;
            font-size: {9.0 * s}pt;
            font-weight: 500;
            letter-spacing: 0.15px;
        }}
        QLineEdit:focus {{
            background: {tk.get("section_bg_alt", input_bg)};
            border: 1px solid {tk.get("hero_border", input_border)};
            color: {tk["text_primary"]};
        }}
        QToolButton {{
            color: {tk.get("button_primary_text", tk.get("accent_deep", tk["text_primary"]))};
            background: {tk.get("button_primary_bg", tk.get("hero_bg", "transparent"))};
            border: 1px solid {tk.get("button_primary_border", tk.get("hero_border", input_border))};
            border-radius: {submit_radius}px;
            padding: 5px 13px;
            min-width: {int(round(42 * s))}px;
            font-size: {9.0 * s}pt;
            font-weight: 700;
            letter-spacing: 0.25px;
        }}
        QToolButton:hover {{
            background: {tk.get("button_primary_hover_bg", tk.get("hero_bg_strong", "transparent"))};
            border: 1px solid {tk.get("button_primary_hover_border", tk.get("hero_border", input_border))};
            color: {tk.get("button_primary_hover_text", tk["text_primary"])};
        }}
    """


def calendar_stylesheet(tokens: dict[str, str]) -> str:
    tk = tokens
    nav_radius = int_token(tk, "widget_calendar_nav_radius", 8)
    return f"""
        QCalendarWidget {{
            background: transparent;
        }}
        QCalendarWidget QWidget#qt_calendar_navigationbar {{
            background: {tk.get("header_shell_bg", tk["header_bg"])};
            border: 1px solid {tk.get("header_shell_border", tk.get("panel_border_soft", "rgba(255,255,255,18)"))};
            min-height: 40px;
            border-radius: {nav_radius + 2}px;
            padding: 0 3px;
        }}
        QCalendarWidget QToolButton {{
            color: {tk["calendar_text"]};
            font-size: 8.8pt;
            font-weight: 700;
            letter-spacing: 0.2px;
            background: transparent;
            border: 1px solid transparent;
            border-radius: {nav_radius}px;
            padding: 3px 6px;
            margin: 2px;
        }}
        QCalendarWidget QToolButton:hover {{
            background: {tk.get("button_hover", tk["section_bg_alt"])};
            border: 1px solid {tk.get("hero_border", tk["panel_border"])};
            color: {tk["text_primary"]};
        }}
        QCalendarWidget QToolButton#qt_calendar_prevmonth,
        QCalendarWidget QToolButton#qt_calendar_nextmonth {{
            color: {tk.get("text_primary", tk["calendar_text"])};
            background: {tk.get("button_bg", tk["section_bg"])};
            border: 1px solid {tk.get("section_border", tk.get("panel_border", "rgba(255,255,255,18)"))};
            min-width: 34px;
            max-width: 34px;
            min-height: 28px;
            max-height: 28px;
            font-size: 12.2pt;
            font-weight: 800;
            padding: 0px;
        }}
        QCalendarWidget QToolButton#qt_calendar_prevmonth:hover,
        QCalendarWidget QToolButton#qt_calendar_nextmonth:hover {{
            background: {tk.get("hero_bg", tk["button_hover"])};
            border: 1px solid {tk.get("hero_border", tk["panel_border"])};
        }}
        QCalendarWidget QHeaderView {{
            background: transparent;
        }}
        QCalendarWidget QHeaderView::section {{
            color: {tk["calendar_muted"]};
            background: transparent;
            border: none;
            font-size: 7.6pt;
            font-weight: 800;
            letter-spacing: 1.1px;
            padding: 6px 0 7px 0;
        }}
        QCalendarWidget QAbstractItemView {{
            background: transparent;
            selection-background-color: transparent;
            outline: 0;
            color: {tk["calendar_text"]};
            font-size: 8.9pt;
            font-weight: 500;
        }}
        QCalendarWidget QTableView {{
            background: transparent;
            margin: 4px 0 2px 0;
            padding: 2px 2px 6px 2px;
        }}
    """


def calendar_paint_palette(tokens: dict[str, str]) -> dict[str, QColor]:
    tk = tokens
    accent = css_to_qcolor(tk.get("accent"), "#22c3ca")
    accent_deep = css_to_qcolor(
        tk.get("accent_deep"), tk.get("card_text_primary", tk["text_primary"])
    )
    text_primary = css_to_qcolor(tk.get("calendar_text"), tk["text_primary"])
    text_muted = css_to_qcolor(tk.get("calendar_muted"), tk["text_secondary"])
    hero_bg = css_to_qcolor(tk.get("hero_bg"), accent.name(QColor.NameFormat.HexRgb))
    hero_bg_strong = css_to_qcolor(tk.get("hero_bg_strong"), accent.name(QColor.NameFormat.HexRgb))
    hero_border = css_to_qcolor(tk.get("hero_border"), accent.name(QColor.NameFormat.HexRgb))
    return {
        "accent": accent,
        "accent_deep": accent_deep,
        "text_primary": text_primary,
        "text_muted": text_muted,
        "hero_bg": hero_bg,
        "hero_bg_strong": hero_bg_strong,
        "hero_border": hero_border,
    }


def chip_stylesheet(tokens: dict[str, str], *, scale: float = 1.0) -> str:
    tk = tokens
    s = max(0.75, float(scale or 1.0))
    chip_radius = int(round(int_token(tk, "widget_chip_radius", 12) * s))
    return (
        f"background: {tk.get('chip_bg', tk.get('hero_bg', 'transparent'))};"
        f" border: 1px solid {tk.get('chip_border', tk.get('hero_border', 'rgba(255,255,255,16)'))};"
        f" border-radius: {chip_radius}px;"
        f" padding: 3px 9px;"
        f" color: {tk.get('accent_deep', tk['text_primary'])};"
        f" font-size: {7.7 * s}pt;"
        " font-weight: 700;"
        " letter-spacing: 0.8px;"
    )


def work_summary_stylesheet(*_args, **_kwargs) -> str:
    return ""


def launcher_stylesheet(tokens: dict[str, str], *, scale: float = 1.0) -> str:
    tk = tokens
    s = max(0.75, float(scale or 1.0))
    launcher_radius = int(round(int_token(tk, "launcher_radius", 22) * s))
    button_radius = int(round(int_token(tk, "launcher_button_radius", 14) * s))
    return f"""
        QDialog#widget_mode_launcher {{
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 1,
                stop: 0 {tk.get("panel_bg_start", tk["panel_bg"])},
                stop: 0.5 {tk.get("panel_bg", tk["panel_bg"])},
                stop: 1 {tk.get("panel_bg_end", tk["panel_bg"])}
            );
            border: 1px solid {tk.get("panel_border", "rgba(255,255,255,20)")};
            border-radius: {launcher_radius}px;
        }}
        QLabel#widget_mode_launcher_title {{
            color: {tk["text_primary"]};
            font-size: {10.2 * s}pt;
            font-weight: 700;
            letter-spacing: 0.5px;
            background: transparent;
            border: none;
        }}
        QLabel#widget_mode_launcher_desc {{
            color: {tk.get("text_faint", tk["text_secondary"])};
            font-size: {8.7 * s}pt;
            font-weight: 500;
            line-height: 1.35;
            background: transparent;
            border: none;
        }}
        QPushButton#widget_mode_launcher_btn {{
            color: {tk.get("card_text_primary", tk["text_primary"])};
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 1,
                stop: 0 {tk.get("section_bg", tk.get("card_bg", tk["panel_bg"]))},
                stop: 1 {tk.get("surface_alt", tk["section_bg_alt"])}
            );
            border: 1px solid {tk.get("card_border", tk.get("section_border_soft", "rgba(255,255,255,14)"))};
            border-radius: {button_radius}px;
            padding: {int(round(11 * s))}px {int(round(14 * s))}px;
            text-align: left;
            font-size: {9.1 * s}pt;
            font-weight: 600;
            letter-spacing: 0.15px;
        }}
        QPushButton#widget_mode_launcher_btn:hover {{
            background: {tk.get("card_hover", tk["section_bg_alt"])};
            border: 1px solid {tk.get("hero_border", tk["panel_border"])};
            color: {tk["text_primary"]};
        }}
    """


def menu_stylesheet(tokens: dict[str, str]) -> str:
    tk = tokens
    menu_radius = int_token(tk, "widget_menu_radius", 14)
    item_radius = int_token(tk, "widget_menu_item_radius", 8)
    return f"""
        QMenu {{
            background: {tk.get("panel_bg", "rgba(13,15,20,238)")};
            color: {tk.get("text_secondary", "#c0cade")};
            border: 1px solid {tk.get("panel_border", "rgba(255,255,255,20)")};
            border-radius: {menu_radius}px;
            padding: 8px;
            font-size: 8.9pt;
            font-weight: 500;
        }}
        QMenu::item {{
            padding: 8px 22px 8px 12px;
            border-radius: {item_radius}px;
            margin: 1px 0;
            background: transparent;
        }}
        QMenu::item:selected {{
            background: {tk.get("section_bg_alt", "rgba(255,255,255,0.08)")};
            color: {tk.get("text_primary", "#ffffff")};
        }}
        QMenu::item:disabled {{
            color: {tk.get("text_faint", "#7c88a3")};
        }}
        QMenu::separator {{
            height: 1px;
            margin: 6px 8px;
            background: {tk.get("section_border_soft", "rgba(255,255,255,12)")};
        }}
    """
