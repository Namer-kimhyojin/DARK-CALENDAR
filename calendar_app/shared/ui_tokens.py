"""Shared UI token accessors built on top of a common theme snapshot."""

from calendar_app.shared.theme_snapshot import ThemeSnapshot, build_shared_ui_tokens


def get_ui_tokens(
    settings=None,
    *,
    snapshot: ThemeSnapshot | None = None,
    theme_color: str | None = None,
    text_theme: str | None = None,
    panel_base_color: str | None = None,
    opacity_factor: float | None = None,
    input_bg: str | None = None,
):
    """Return semantic UI tokens for the active theme."""
    return build_shared_ui_tokens(
        settings=settings,
        snapshot=snapshot,
        theme_color=theme_color,
        text_theme=text_theme,
        panel_base_color=panel_base_color,
        opacity_factor=opacity_factor,
        input_bg=input_bg,
    )


def get_shared_qss(tokens=None):
    """Returns a base QSS string utilizing the provided (or current) tokens."""
    t = tokens or get_ui_tokens()

    return f"""
    QWidget {{
        color: {t["text_primary"]};
        font-family: 'Segoe UI', 'Inter', 'Malgun Gothic', sans-serif;
    }}

    QLineEdit, QComboBox, QDateEdit, QTimeEdit, QSpinBox {{
        background-color: {t["input_bg"]};
        color: {t["text_primary"]};
        border: 1px solid {t["input_border"]};
        border-radius: {t.get("field_radius", t["radius_md"])};
        padding: 4px 8px;
        min-height: {t["field_height"]};
    }}

    QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{
        border: 1px solid {t["accent"]};
        background-color: {t["input_bg"]};
    }}

    QComboBox QAbstractItemView {{
        background-color: {t["input_bg"]};
        border: 1px solid {t["input_border"]};
        color: {t["text_primary"]};
        outline: none;
    }}

    QPushButton {{
        background-color: {t["bg_item"]};
        color: {t["text_primary"]};
        border: 1px solid {t["border"]};
        border-radius: {t.get("button_radius", t["radius_md"])};
        padding: {t.get("button_padding_y", "4px")} {t.get("button_padding_x", "16px")};
        font-weight: 600;
        min-height: {t["button_height"]};
    }}

    QPushButton:hover {{
        background-color: {t["bg_item_hover"]};
        border-color: {t["accent_border"]};
    }}

    QPushButton[primary="true"] {{
        background-color: {t["accent_soft"]};
        color: {t["accent"]};
        border: 1px solid {t["accent_border"]};
    }}

    QPushButton[primary="true"]:hover {{
        background-color: {t["accent"]};
        color: {t["text_inverse"]};
    }}
    """
