"""Shared token-driven styles for task/directive editor dialogs."""

from __future__ import annotations

from PyQt6.QtGui import QColor

from calendar_app.presentation.dialogs.dialog_styles import (
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)


def _resolve_tokens(tokens: dict | None = None) -> dict:
    return dict(tokens or get_dialog_theme_tokens())


def _resolve_metrics(metrics: dict | None = None) -> dict:
    return dict(metrics or get_dialog_metric_tokens(apply_overrides=True))


def _qcolor(value: object, fallback: str) -> QColor:
    q = QColor(str(value or fallback))
    if q.isValid():
        return q
    q = QColor(fallback)
    return q if q.isValid() else QColor("#000000")


def _rgba(value: object, alpha: float, fallback: str) -> str:
    q = _qcolor(value, fallback)
    alpha_i = max(0, min(255, int(round(max(0.0, min(1.0, float(alpha))) * 255.0))))
    return f"rgba({q.red()}, {q.green()}, {q.blue()}, {alpha_i})"


def _tone_color(tokens: dict, tone: str) -> str:
    tone_map = {
        "primary": tokens.get("text_primary", "#e1e1e6"),
        "secondary": tokens.get("text_secondary", "#c8ccd4"),
        "muted": tokens.get("text_muted", "#9aa0ad"),
        "faint": tokens.get("text_faint", "#7a7a8a"),
        "accent": tokens.get("accent", "#4da6ff"),
        "warning": tokens.get("warning_hex", "#ffd34d"),
        "danger": tokens.get("danger_hex", "#ff6b6b"),
        "success": tokens.get("success_hex", "#47d27e"),
    }
    return str(tone_map.get(str(tone or "muted").lower(), tokens.get("text_muted", "#9aa0ad")))


def _hint_surface(tokens: dict, tone: str) -> tuple[str, str, str]:
    tone_key = str(tone or "accent").lower()
    if tone_key == "danger":
        base = tokens.get("danger_hex", "#ff6b6b")
        return (
            tokens.get("text_secondary", "#c8ccd4"),
            tokens.get("danger_soft_bg", _rgba(base, 0.14, "#ff6b6b")),
            _rgba(base, 0.34, "#ff6b6b"),
        )
    if tone_key == "warning":
        base = tokens.get("warning_hex", "#ffd34d")
        return (
            tokens.get("text_secondary", "#c8ccd4"),
            tokens.get("warning_soft_bg", _rgba(base, 0.14, "#ffd34d")),
            _rgba(base, 0.32, "#ffd34d"),
        )
    if tone_key == "muted":
        return (
            tokens.get("text_muted", "#9aa0ad"),
            tokens.get("surface_hover", "#18181f"),
            tokens.get("border_soft", "rgba(255,255,255,0.10)"),
        )
    return (
        tokens.get("text_secondary", "#c8ccd4"),
        tokens.get("accent_soft_bg", _rgba(tokens.get("accent"), 0.10, "#4da6ff")),
        tokens.get("accent_soft_border", _rgba(tokens.get("accent"), 0.28, "#4da6ff")),
    )


def build_task_editor_stylesheet(tokens: dict | None = None, metrics: dict | None = None) -> str:
    t = _resolve_tokens(tokens)
    m = _resolve_metrics(metrics)

    accent = t.get("accent", "#4da6ff")
    accent_soft = _rgba(accent, 0.12, "#4da6ff")
    border = t.get("border", "rgba(255,255,255,0.16)")
    border_soft = t.get("border_soft", "rgba(255,255,255,0.10)")
    surface_bg = t.get("surface_bg", "#16161b")
    surface_item = t.get("surface_item", "#111116")
    surface_hover = t.get("surface_hover", "#18181f")
    tab_idle_bg = t.get("tab_idle_bg", "rgba(255,255,255,0.02)")
    tab_active_bg = t.get("tab_active_bg", "rgba(255,255,255,0.04)")
    tab_text = t.get("tab_text", t.get("text_muted", "#9aa0ad"))
    tab_text_hover = t.get("tab_text_hover", t.get("text_secondary", "#c8ccd4"))
    tab_text_active = t.get("tab_text_active", accent)
    text_secondary = t.get("text_secondary", "#c8ccd4")
    text_primary = t.get("text_primary", "#e1e1e6")
    list_selected_bg = t.get("list_selected_bg", _rgba(accent, 0.12, "#4da6ff"))
    list_selected_border = t.get("list_selected_border", _rgba(accent, 0.25, "#4da6ff"))
    list_selected_text = t.get("list_selected_text", text_primary)

    tab_radius = int(m.get("tab_radius", 12))
    pane_radius = max(int(m.get("group_radius", 14)), tab_radius + 2)
    dialog_radius = max(pane_radius, int(m.get("field_radius", 10)) + 3)
    label_font_px = max(13, int(m.get("base_font_pt", 14)) - 1)
    title_font_px = max(17, int(m.get("base_font_pt", 14)) + 3)

    return f"""
QDialog#TaskEditorDialog {{
    background-color: {surface_bg};
    border: 1px solid {border};
    border-radius: {dialog_radius}px;
}}

/* -- Tabs: Floating Pill Style -- */
QDialog#TaskEditorDialog QTabWidget#TaskEditorTabs {{
    background: transparent;
}}
QDialog#TaskEditorDialog QTabWidget#TaskEditorTabs::pane {{
    border: 1px solid {border_soft};
    background: {tab_active_bg};
    border-radius: {pane_radius}px;
    top: -1px;
    padding: 2px;
}}
QDialog#TaskEditorDialog QTabWidget#TaskEditorTabs QTabBar {{
    background: transparent;
}}
QDialog#TaskEditorDialog QTabWidget#TaskEditorTabs QTabBar::tab {{
    background: {tab_idle_bg};
    color: {tab_text};
    border: 1px solid {border_soft};
    border-radius: {tab_radius}px;
    border-top-left-radius: {tab_radius}px;
    border-top-right-radius: {tab_radius}px;
    min-width: {int(m.get("tab_min_width", 86))}px;
    padding: {int(m.get("tab_padding_y", 10))}px {int(m.get("tab_padding_x", 24))}px;
    margin-right: 6px;
    margin-bottom: 8px;
    font-weight: 700;
    font-size: {label_font_px}px;
}}
QDialog#TaskEditorDialog QTabWidget#TaskEditorTabs QTabBar::tab:hover {{
    background: {surface_hover};
    color: {tab_text_hover};
    border-color: {border};
}}
QDialog#TaskEditorDialog QTabWidget#TaskEditorTabs QTabBar::tab:selected {{
    background: {accent_soft};
    color: {tab_text_active};
    border: 1.5px solid {accent};
    margin-bottom: 8px;
}}

/* -- Group Titles & Labels -- */
QDialog#TaskEditorDialog QLabel#TaskDialogFieldLabel,
QDialog#TaskEditorDialog QLabel#TaskDialogSectionLabel {{
    color: {text_secondary};
    font-weight: 700;
    font-size: {label_font_px}px;
    margin-bottom: 2px;
}}

/* -- Inputs: Premium Editorial Style -- */
QDialog#TaskEditorDialog QLineEdit#TaskTitleEdit {{
    color: {text_primary};
    font-size: {title_font_px}px;
    font-weight: 700;
    border: none;
    border-bottom: 2px solid {border_soft};
    border-radius: 0px;
    background: transparent;
    padding: 8px 4px;
    selection-background-color: {accent_soft};
}}
QDialog#TaskEditorDialog QLineEdit#TaskTitleEdit:focus {{
    border-bottom: 2px solid {accent};
}}

QDialog#TaskEditorDialog QComboBox#TaskCalendarCombo {{
    background: {surface_item};
    border: 1px solid {border_soft};
    border-radius: {int(m.get("field_radius", 10))}px;
    padding: 6px 12px;
}}
QDialog#TaskEditorDialog QComboBox#TaskCalendarCombo:hover {{
    border-color: {border};
}}
QDialog#TaskEditorDialog QComboBox#TaskCalendarCombo QAbstractItemView {{
    background: {surface_item};
    color: {text_primary};
    border: 1px solid {border};
    selection-background-color: {list_selected_bg};
    selection-color: {list_selected_text};
    outline: none;
}}

QDialog#TaskEditorDialog QRadioButton#TaskDialogOptionCheck,
QDialog#TaskEditorDialog QCheckBox#TaskDialogOptionCheck {{
    color: {text_secondary};
    spacing: 8px;
    font-weight: 600;
    font-size: {label_font_px}px;
}}
QDialog#TaskEditorDialog QRadioButton#TaskDialogOptionCheck::indicator,
QDialog#TaskEditorDialog QCheckBox#TaskDialogOptionCheck::indicator {{
    width: 16px;
    height: 16px;
    border: 1.5px solid {border};
    background-color: {surface_item};
}}
QDialog#TaskEditorDialog QRadioButton#TaskDialogOptionCheck::indicator:checked,
QDialog#TaskEditorDialog QCheckBox#TaskDialogOptionCheck::indicator:checked {{
    background-color: {accent};
    border-color: {accent};
}}

/* -- Buttons: Gradient & Glass -- */
QDialog#TaskEditorDialog QPushButton#primary_btn,
QDialog#TaskEditorDialog QPushButton#CreateBtn {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {accent}, stop:1 {_rgba(accent, 0.8, accent)});
    color: #ffffff;
    border: none;
    border-radius: {int(m.get("button_radius", 12))}px;
    font-weight: 800;
    padding: 10px 24px;
    font-size: {label_font_px}px;
}}
QDialog#TaskEditorDialog QPushButton#primary_btn:hover,
QDialog#TaskEditorDialog QPushButton#CreateBtn:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {_rgba(accent, 0.9, accent)}, stop:1 {accent});
    border: 1px solid {_rgba(accent, 0.6, accent)};
}}

QDialog#TaskEditorDialog QPushButton#ghost_btn[accentVariant="true"] {{
    background: {accent_soft};
    color: {accent};
    border: 1px solid {_rgba(accent, 0.3, accent)};
    font-weight: 700;
    border-radius: {int(m.get("button_radius", 12))}px;
}}
QDialog#TaskEditorDialog QPushButton#ghost_btn[accentVariant="true"]:hover {{
    background: {_rgba(accent, 0.2, accent)};
    border-color: {accent};
}}

/* -- Visual Separators -- */
QDialog#TaskEditorDialog QFrame#TaskDialogSectionLine,
QDialog#TaskEditorDialog QFrame#TaskDialogFooterLine {{
    background: {border_soft};
    min-height: 1px;
    max-height: 1px;
    border: none;
    margin: 10px 0;
}}

/* -- Lists & Stacks -- */
QDialog#TaskEditorDialog QStackedWidget {{
    background: transparent;
    border: none;
}}
QDialog#TaskEditorDialog QListWidget {{
    background: transparent;
    border: 1px solid {border_soft};
    border-radius: {int(m.get("list_radius", 10))}px;
}}
QDialog#TaskEditorDialog QListWidget::item:selected {{
    background-color: {list_selected_bg};
    color: {list_selected_text};
    border: 1px solid {list_selected_border};
    border-radius: {int(m.get("list_item_radius", 8))}px;
}}
""".strip()


def build_editor_text_style(
    tokens: dict | None = None,
    *,
    tone: str = "muted",
    color: str | None = None,
    font_px: int = 13,
    weight: str | int | None = None,
    padding: str | None = None,
    margin_top: int | None = None,
    background: str | None = None,
    border_css: str | None = None,
    radius: int | None = None,
) -> str:
    t = _resolve_tokens(tokens)
    parts = [
        f"color: {color or _tone_color(t, tone)}",
        f"font-size: {int(font_px)}px",
    ]
    if weight is not None:
        parts.append(f"font-weight: {weight}")
    if padding:
        parts.append(f"padding: {padding}")
    if margin_top is not None:
        parts.append(f"margin-top: {int(margin_top)}px")
    if background:
        parts.append(f"background-color: {background}")
    if border_css:
        parts.append(f"border: {border_css}")
    if radius is not None:
        parts.append(f"border-radius: {int(radius)}px")
    return "; ".join(parts) + ";"


def build_editor_hint_style(
    tokens: dict | None = None,
    metrics: dict | None = None,
    *,
    tone: str = "accent",
    font_px: int = 11,
    weight: str | int = "normal",
) -> str:
    t = _resolve_tokens(tokens)
    m = _resolve_metrics(metrics)
    text_color, background, border = _hint_surface(t, tone)
    return build_editor_text_style(
        t,
        color=text_color,
        font_px=font_px,
        weight=weight,
        padding="6px 10px",
        margin_top=4,
        background=background,
        border_css=f"1px solid {border}",
        radius=max(4, int(m.get("field_radius", 7)) - 1),
    )


def build_editor_counter_style(
    tokens: dict | None = None,
    *,
    level: str = "normal",
    font_px: int = 11,
) -> str:
    t = _resolve_tokens(tokens)
    level_key = str(level or "normal").lower()
    if level_key == "danger":
        color = t.get("danger_hex", "#ff6b6b")
        weight = "bold"
    elif level_key == "warning":
        color = t.get("warning_hex", "#ffd34d")
        weight = "normal"
    else:
        color = t.get("text_faint", "#7a7a8a")
        weight = "normal"
    return build_editor_text_style(t, color=color, font_px=font_px, weight=weight)


def build_editor_quick_button_style(
    tokens: dict | None = None,
    metrics: dict | None = None,
    *,
    accent: bool = False,
    tone: str | None = None,
    is_quick: bool = True,
) -> str:
    t = _resolve_tokens(tokens)
    m = _resolve_metrics(metrics)
    theme_defaults = get_dialog_theme_tokens()
    font_px = max(11, int(m.get("base_font_pt", 14)) - 3)
    height_offset = -10 if is_quick else 0
    height = max(24 if is_quick else 32, int(m.get("button_height", 34)) + height_offset)
    radius = max(5, int(m.get("button_radius", 8)) - 1)
    padding_y = max(2, int(m.get("button_padding_y", 4)) - 1)
    padding_x = max(6, int(m.get("button_padding_x", 16)) - 8)

    def _semantic_value(key: str, fallback: str) -> str:
        value = t.get(key)
        if value is None:
            return fallback
        default_value = theme_defaults.get(key)
        if default_value is not None and value == default_value:
            return fallback
        return value

    tone_key = str(tone or ("accent" if accent else "secondary")).lower()

    if tone_key in {"accent", "primary"}:
        bg = _semantic_value("accent_soft_bg", _rgba(t.get("accent"), 0.16, "#4da6ff"))
        text = _semantic_value("button_primary_text", t.get("accent", "#4da6ff"))
        border = _semantic_value("accent_soft_border", _rgba(t.get("accent"), 0.42, "#4da6ff"))
        hover_bg = _semantic_value(
            "button_primary_hover_bg", _rgba(t.get("accent"), 0.18, "#4da6ff")
        )
        hover_text = _semantic_value("button_primary_hover_text", t.get("text_primary", "#e1e1e6"))
        hover_border = _semantic_value("button_primary_hover_border", t.get("accent", "#4da6ff"))
    elif tone_key == "danger":
        bg = t.get("danger_soft_bg", _rgba(t.get("danger_hex"), 0.14, "#ff6b6b"))
        text = t.get("danger_hex", "#ff6b6b")
        border = _rgba(t.get("danger_hex"), 0.42, "#ff6b6b")
        hover_bg = _rgba(t.get("danger_hex"), 0.20, "#ff6b6b")
        hover_text = t.get("text_primary", "#e1e1e6")
        hover_border = t.get("danger_hex", "#ff6b6b")
    elif tone_key == "warning":
        bg = t.get("warning_soft_bg", _rgba(t.get("warning_hex"), 0.14, "#ffd34d"))
        text = t.get("warning_hex", "#ffd34d")
        border = _rgba(t.get("warning_hex"), 0.38, "#ffd34d")
        hover_bg = _rgba(t.get("warning_hex"), 0.20, "#ffd34d")
        hover_text = t.get("text_primary", "#e1e1e6")
        hover_border = t.get("warning_hex", "#ffd34d")
    elif tone_key == "success":
        bg = t.get("success_soft_bg", _rgba(t.get("success_hex"), 0.14, "#47d27e"))
        text = t.get("success_hex", "#47d27e")
        border = _rgba(t.get("success_hex"), 0.40, "#47d27e")
        hover_bg = _rgba(t.get("success_hex"), 0.20, "#47d27e")
        hover_text = t.get("text_primary", "#e1e1e6")
        hover_border = t.get("success_hex", "#47d27e")
    else:
        bg = _semantic_value("button_secondary_bg", t.get("surface_hover", "#18181f"))
        text = _semantic_value("button_secondary_text", t.get("text_muted", "#9aa0ad"))
        border = _semantic_value(
            "button_secondary_border", t.get("border_soft", "rgba(255,255,255,0.10)")
        )
        hover_bg = _semantic_value("button_secondary_hover_bg", t.get("surface_alt", "#1c1c23"))
        hover_text = _semantic_value(
            "button_secondary_hover_text", t.get("text_primary", "#e1e1e6")
        )
        hover_border = _semantic_value(
            "button_secondary_hover_border", t.get("border", "rgba(255,255,255,0.16)")
        )

    return (
        f"QPushButton {{ background-color: {bg}; color: {text}; font-size: {font_px}px; "
        f"padding: {padding_y}px {padding_x}px; border: 1px solid {border}; "
        f"border-radius: {radius}px; min-height: {height}px; max-height: {height}px; }}"
        f"QPushButton:hover {{ background-color: {hover_bg}; color: {hover_text}; border: 1px solid {hover_border}; }}"
        f"QPushButton:pressed {{ background-color: {t.get('button_pressed_bg', t.get('surface_top', '#13131a'))}; "
        f"color: {t.get('button_pressed_text', t.get('text_primary', '#e1e1e6'))}; "
        f"border: 1px solid {t.get('button_pressed_border', t.get('border', 'rgba(255,255,255,0.16)'))}; }}"
    )


def build_transparent_stack_stylesheet(object_name: str) -> str:
    return f"QStackedWidget#{object_name} {{ background: transparent; border: none; }}"


def build_settings_style_bundle(
    tokens: dict | None = None, metrics: dict | None = None
) -> dict[str, str]:
    t = _resolve_tokens(tokens)
    m = _resolve_metrics(metrics)
    accent = t.get("accent", "#4da6ff")
    success = t.get("success_hex", "#5ecb8a")
    danger = t.get("danger_hex", "#d25a66")
    base_font_px = max(12, int(m.get("base_font_pt", 14)))
    group_radius = max(10, int(m.get("group_radius", 10)))
    field_radius = max(6, int(m.get("field_radius", 7)))
    surface_item = t.get("surface_item", "#161b28")
    surface_hover = t.get("surface_hover", "#1a2232")
    surface_alt = t.get("surface_alt", surface_item)
    surface_bg = t.get("surface_bg", surface_alt)
    surface_top = t.get("surface_top", "#0e1118")
    input_bg = t.get("input_bg", surface_bg)
    border = t.get("border", "rgba(255,255,255,0.16)")
    border_soft = t.get("border_soft", "rgba(255,255,255,0.10)")
    text_primary = t.get("text_primary", "#f4f7fb")
    text_secondary = t.get("text_secondary", "#d4dceb")
    text_muted = t.get("text_muted", "#8a9bbf")
    text_faint = t.get("text_faint", "#7a8da8")
    field_height = max(32, int(m.get("field_height", 34)))
    field_padding_x = max(8, int(m.get("field_padding_x", 10)))
    field_padding_y = max(3, int(m.get("field_padding_y", 4)))
    input_focus_bg = t.get("input_focus_bg", surface_bg)
    input_disabled_bg = t.get("input_disabled_bg", surface_item)
    selection_bg = t.get("list_selected_bg", t.get("accent_soft_bg", _rgba(accent, 0.12, accent)))
    selection_text = t.get("list_selected_text", text_primary)
    combo_arrow = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath fill='%239bacc8' d='M0 0l5 6 5-6z'/%3E%3C/svg%3E"

    return {
        "card": (
            "QFrame#card { "
            f"background-color: {surface_alt}; border: 1px solid {border_soft}; border-radius: {group_radius + 3}px; "
            "}"
        ),
        "status_bar": (
            "QFrame#statusBar { "
            f"background-color: {surface_top}; border-bottom: 1px solid {border_soft}; border-radius: 0; "
            "}"
        ),
        "sidebar_shell": (
            "QFrame#sidebar { "
            f"background-color: {surface_top}; border-right: 1px solid {border_soft}; border-radius: 0; "
            "}"
        ),
        "content_area": (
            "QWidget#contentArea { "
            f"background-color: {t.get('surface_bg', '#13161f')}; border-radius: 0; "
            "}"
        ),
        "scroll_shell": (
            "QScrollArea { background-color: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background-color: transparent; }"
            "QScrollBar:vertical { "
            f"background: {surface_top}; width: 6px; border-radius: 3px; "
            "}"
            "QScrollBar::handle:vertical { "
            f"background: {border}; border-radius: 3px; min-height: 30px; "
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        ),
        "subtle_card": (
            "QFrame#subtleCard { "
            f"background-color: {surface_item}; border: 1px solid {border_soft}; border-radius: {group_radius}px; "
            "}"
        ),
        "divider": f"QFrame#divider {{ background-color: {border_soft}; min-height: 1px; max-height: 1px; border: none; }}",
        "card_title": build_editor_text_style(
            t, tone="primary", font_px=base_font_px + 2, weight=700
        ),
        "eyebrow": build_editor_text_style(
            t, tone="accent", font_px=max(11, base_font_px - 2), weight=700
        ),
        "field_label": build_editor_text_style(
            t, tone="secondary", font_px=max(13, base_font_px - 1), weight=700
        ),
        "help": build_editor_text_style(t, tone="muted", font_px=max(12, base_font_px - 2)),
        "tip_title": build_editor_text_style(
            t, tone="primary", font_px=max(13, base_font_px - 1), weight=700
        ),
        "tip_body": build_editor_text_style(t, tone="muted", font_px=max(12, base_font_px - 2)),
        "meta_label": build_editor_text_style(
            t, tone="muted", font_px=max(11, base_font_px - 3), weight=600
        ),
        "meta_value": build_editor_text_style(
            t, tone="secondary", font_px=max(12, base_font_px - 1), weight=600
        ),
        "button_secondary": build_editor_quick_button_style(t, m, tone="secondary", is_quick=False),
        "button_accent": build_editor_quick_button_style(t, m, tone="accent", is_quick=False),
        "button_success": build_editor_quick_button_style(t, m, tone="success", is_quick=False),
        "button_danger": build_editor_quick_button_style(t, m, tone="danger", is_quick=False),
        "input_line": (
            "QLineEdit { "
            f"background-color: {input_bg}; color: {text_primary}; border: 1px solid {border_soft}; "
            f"border-radius: {field_radius}px; padding: {field_padding_y}px {field_padding_x}px; min-height: {field_height}px; "
            "}"
            "QLineEdit:hover { "
            f"border-color: {border}; "
            "}"
            "QLineEdit:focus { "
            f"border: 1px solid {t.get('accent', accent)}; background-color: {input_focus_bg}; "
            "}"
            "QLineEdit:disabled { "
            f"color: {text_faint}; background-color: {input_disabled_bg}; border-color: {border_soft}; "
            "}"
            "QLineEdit::placeholder { "
            f"color: {text_faint}; "
            "}"
        ),
        "input_combo": (
            "QComboBox { "
            f"background-color: {input_bg}; color: {text_primary}; border: 1px solid {border_soft}; "
            f"border-radius: {field_radius}px; padding: {field_padding_y}px {field_padding_x}px; "
            f"padding-right: {field_padding_x + 22}px; min-height: {field_height}px; combobox-popup: 0; "
            "}"
            "QComboBox:hover { "
            f"border-color: {border}; "
            "}"
            "QComboBox:focus { "
            f"border: 1px solid {t.get('accent', accent)}; background-color: {input_focus_bg}; "
            "}"
            "QComboBox:disabled { "
            f"color: {text_faint}; background-color: {input_disabled_bg}; border-color: {border_soft}; "
            "}"
            "QComboBox::drop-down { border: none; width: 32px; }"
            "QComboBox::down-arrow { "
            f'image: url("{combo_arrow}"); width: 10px; height: 6px; '
            "}"
        ),
        "input_spin": (
            "QSpinBox { "
            f"background-color: {input_bg}; color: {text_primary}; border: 1px solid {border_soft}; "
            f"border-radius: {field_radius}px; padding: {field_padding_y}px {field_padding_x}px; "
            f"padding-right: {field_padding_x + 18}px; min-height: {field_height}px; "
            "}"
            "QSpinBox:hover { "
            f"border-color: {border}; "
            "}"
            "QSpinBox:focus { "
            f"border: 1px solid {t.get('accent', accent)}; background-color: {input_focus_bg}; "
            "}"
            "QSpinBox:disabled { "
            f"color: {text_faint}; background-color: {input_disabled_bg}; border-color: {border_soft}; "
            "}"
        ),
        "input_popup": (
            "QAbstractItemView, QListView { "
            f"background-color: {surface_alt}; color: {text_primary}; selection-background-color: {selection_bg}; "
            f"selection-color: {selection_text}; border: 1px solid {border}; border-radius: {field_radius}px; "
            "outline: none; "
            "}"
        ),
        "check_toggle": (
            "QCheckBox { "
            f"color: {text_secondary}; spacing: 8px; font-weight: 600; font-size: {max(13, base_font_px - 1)}px; "
            "}"
            "QCheckBox::indicator { "
            f"border: 1.5px solid {t.get('check_indicator_border', border)}; "
            f"background-color: {t.get('check_indicator_bg', surface_bg)}; "
            "width: 16px; height: 16px; "
            "}"
            "QCheckBox::indicator:checked { "
            f"background-color: {t.get('accent', accent)}; "
            f"border-color: {t.get('accent', accent)}; "
            "}"
        ),
        "nav_button": (
            "QPushButton { "
            "background: transparent; border: none; border-left: 3px solid transparent; border-radius: 0; "
            f"color: {text_muted}; font-size: {max(12, base_font_px - 1)}px; font-weight: 600; "
            "padding: 11px 16px; text-align: left; "
            "}"
            "QPushButton:hover { "
            f"background: {t.get('list_hover_bg', surface_hover)}; color: {text_secondary}; "
            f"border-left-color: {t.get('accent_soft_border', _rgba(accent, 0.30, accent))}; "
            "}"
        ),
        "nav_button_active": (
            "QPushButton { "
            f"background: {t.get('accent_soft_bg', _rgba(accent, 0.10, accent))}; "
            f"border: none; border-left: 3px solid {t.get('accent', accent)}; border-radius: 0; "
            f"color: {text_primary}; font-size: {max(12, base_font_px - 1)}px; font-weight: 700; "
            "padding: 11px 16px; text-align: left; "
            "}"
            "QPushButton:hover { "
            f"background: {t.get('button_primary_hover_bg', _rgba(accent, 0.18, accent))}; color: {text_primary}; "
            f"border-left-color: {t.get('button_primary_hover_border', accent)}; "
            "}"
        ),
        "status_separator": f"color: {border_soft}; background: {border_soft};",
        "calendar_row": (
            "QFrame#calRow { "
            f"background: {surface_item}; border: 1px solid {border_soft}; border-radius: 10px; "
            "}"
            "QFrame#calRow:hover { "
            f"background: {surface_hover}; border-color: {border}; "
            "}"
        ),
        "calendar_name": f"color: {text_primary}; font-size: 14px; font-weight: 600; background: transparent;",
        "calendar_meta": f"color: {text_muted}; font-size: 12px; background: transparent;",
        "calendar_meta_compact": f"color: {text_muted}; font-size: 12px; margin-right: 4px;",
        "default_active": build_editor_quick_button_style(t, m, tone="warning"),
        "default_idle": build_editor_quick_button_style(t, m, tone="secondary"),
        "action_separator": f"background: {border}; margin: 8px 4px;",
        "icon_button": build_editor_quick_button_style(t, m, tone="secondary"),
        "danger_icon_button": build_editor_quick_button_style(t, m, tone="danger"),
        "empty_state": build_editor_text_style(
            t,
            tone="faint",
            font_px=max(13, base_font_px - 1),
            padding="24px 0",
        ),
        "notice_warning": build_editor_text_style(
            t, tone="warning", font_px=max(12, base_font_px - 2)
        ),
        "footer": (
            "QFrame { "
            f"background-color: {surface_top}; border-top: 1px solid {border_soft}; border-radius: 0; "
            "}"
        ),
        "step_badge": build_editor_hint_style(
            t, m, tone="accent", font_px=max(12, base_font_px - 2), weight=700
        ),
        "feedback_error": build_editor_text_style(
            t, tone="danger", font_px=max(13, base_font_px - 1), weight=600
        ),
        "feedback_warning": build_editor_text_style(
            t, tone="warning", font_px=max(13, base_font_px - 1), weight=600
        ),
        "feedback_success": build_editor_text_style(
            t, tone="success", font_px=max(13, base_font_px - 1), weight=600
        ),
        "status_title_connected": build_editor_text_style(
            t, color=text_secondary, font_px=base_font_px, weight=600
        ),
        "status_title_pending": build_editor_text_style(
            t, color=text_muted, font_px=base_font_px, weight=600
        ),
        "status_pill_connected": (
            f"background-color: {t.get('success_soft_bg', _rgba(success, 0.10, success))}; "
            f"color: {t.get('success_hex', success)}; "
            "border-radius: 10px; "
            "padding: 2px 10px; max-height: 20px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px;"
        ),
        "status_pill_pending": (
            f"background-color: {t.get('surface_hover', surface_hover)}; "
            f"color: {t.get('danger_hex', danger)}; "
            "border-radius: 10px; "
            "padding: 2px 10px; max-height: 20px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px;"
        ),
        "status_label_success": build_editor_text_style(
            t, tone="success", font_px=base_font_px, weight=600
        ),
        "status_label_muted": build_editor_text_style(
            t, color=text_muted, font_px=base_font_px, weight=600
        ),
        "status_text_faint": build_editor_text_style(
            t, color=text_faint, font_px=max(13, base_font_px - 1)
        ),
        "meta_box": (
            "QFrame#subtleCard { "
            f"background-color: {surface_item}; border: 1px solid {border_soft}; border-radius: {group_radius}px; "
            "}"
        ),
        "guide_row": (
            "QFrame#subtleCard { "
            f"background-color: {surface_item}; border: 1px solid {border_soft}; border-radius: {group_radius}px; "
            "}"
        ),
        "swatch_shell": (
            "QLineEdit { "
            f"background-color: {surface_bg}; border: 1px solid {border_soft}; border-radius: {field_radius}px; "
            f"color: {text_primary}; "
            "}"
        ),
    }


def build_settings_dialog_stylesheet(tokens: dict | None = None) -> str:
    """Build settings-dialog stylesheet using current dialog tokens."""
    t = _resolve_tokens(tokens)
    surface_bg = t.get("surface_bg", "#13161f")
    surface_top = t.get("surface_top", "#0e1118")
    text_primary = t.get("text_primary", "#e7ecf4")
    text_secondary = t.get("text_secondary", "#d4dceb")
    border = t.get("border", "rgba(255,255,255,0.16)")
    from calendar_app.presentation.dialogs.dialog_styles import build_dialog_stylesheet

    global_stylesheet = (
        "QDialog { "
        f"background-color: {surface_bg}; color: {text_primary}; "
        "}"
        "QLabel { "
        f"color: {text_secondary}; "
        "}"
        "QScrollArea { background-color: transparent; border: none; }"
        "QScrollBar:vertical { "
        f"background: {surface_top}; width: 6px; border-radius: 3px; "
        "}"
        "QScrollBar::handle:vertical { "
        f"background: {border}; border-radius: 3px; min-height: 30px; "
        "}"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
    )
    return "\n".join([build_dialog_stylesheet(), global_stylesheet])


def build_settings_swatch_style(color_str: str, tokens: dict | None = None) -> str:
    t = _resolve_tokens(tokens)
    border_css = t.get("border", "rgba(255,255,255,0.18)")
    border_strong = t.get("border_strong", "rgba(255,255,255,0.50)")
    return (
        "QPushButton { "
        f"background-color: {color_str}; border-radius: 10px; border: 1.5px solid {border_css}; "
        "}"
        "QPushButton:hover { "
        f"border: 1.5px solid {border_strong}; "
        "}"
    )


def build_settings_visibility_button_style(
    is_visible: bool | dict,
    tokens: dict | None = None,
    metrics: dict | None = None,
    *,
    tone: str | None = None,
) -> str:
    # Backward-compatibility: some callers still pass (tokens, metrics, tone="...").
    if isinstance(is_visible, dict):
        metrics = tokens if isinstance(tokens, dict) else metrics
        tokens = is_visible
        is_visible = str(tone or "accent").lower() != "secondary"

    t = _resolve_tokens(tokens)
    m = _resolve_metrics(metrics)
    resolved_tone = "accent" if bool(is_visible) else "secondary"
    return build_editor_quick_button_style(t, m, tone=resolved_tone)
