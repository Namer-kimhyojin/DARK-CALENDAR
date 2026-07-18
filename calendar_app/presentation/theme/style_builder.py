# -*- coding: utf-8 -*-
"""Theme and stylesheet builders for presentation layer."""

from calendar_app.presentation.theme.ui_tokens import get_ui_shape_tokens
from calendar_app.shared.color_utils import (
    derive_text_palette,
    derive_ui_palette,
    hex_to_rgba,
    hue_shifted_rgba,
)
from calendar_app.shared.theme_settings import get_theme_palette_inputs


def _hex_to_rgba(hex_color, alpha_0_to_1):
    """hex to rgba(r,g,b,alpha) string helper."""
    return hex_to_rgba(hex_color, alpha_0_to_1)


def _hue_shifted_rgba(hex_color, hue_shift, alpha):
    """Hue shifted rgba helper."""
    return hue_shifted_rgba(hex_color, hue_shift, alpha)


def _scaled_pt(base_pt=10, delta=0, minimum=8):
    safe_base = max(10, base_pt if base_pt > 0 else 10)
    return max(minimum, safe_base + delta)


def build_global_stylesheet(
    family="Outfit, Inter, Segoe UI, sans-serif",
    base_pt=10,
    theme_color="#4da6ff",
    text_theme="dark",
    panel_base_color="#1c1c1c",
    palette=None,
):
    """Generates the comprehensive application stylesheet with modern aesthetics."""
    if base_pt is None or base_pt <= 0:
        base_pt = 10

    def tc(a):
        return _hex_to_rgba(theme_color, a)

    if palette is None:
        palette = derive_ui_palette(text_theme, panel_base_color, theme_color=theme_color)

    p = palette
    shape = get_ui_shape_tokens()
    global_task_radius = int(shape.get("global_task_button_radius", 0))
    drag_range_radius = int(shape.get("drag_range_cap_radius", 0))
    _cell_border = "rgba(255,255,255,0.18)"

    return f"""
        /* Global Reset & Selection */
        * {{
            selection-background-color: {tc(0.7)};
            selection-color: white;
            outline: none;
        }}

        /* Calendar Surface & Cells */
        ClickableCell {{
            background-color: {p["cell_bg"]};
            border: 1px solid {_cell_border};
            border-radius: 0px;
        }}
        ClickableCell:hover {{
            background-color: {tc(0.08)};
            border: 1px solid {tc(0.3)};
        }}
        ClickableCell[is_today="true"] {{
            background-color: {tc(0.04)};
            border: 1.5px solid {tc(0.5)};
        }}
        ClickableCell[selected_date="true"] {{
            background-color: {tc(0.10)};
            border: 1px solid {tc(0.44)};
        }}
        ClickableCell[drag_range_preview="true"] {{
            background-color: {tc(0.10)};
            border-top: 2px solid {tc(0.45)};
            border-bottom: 2px solid {tc(0.45)};
            border-left: none;
            border-right: none;
        }}
        ClickableCell[drag_range_preview="true"][drag_range_start="true"] {{
            border-left: 2px solid {tc(0.45)};
            border-top-left-radius: {drag_range_radius}px;
            border-bottom-left-radius: {drag_range_radius}px;
        }}
        ClickableCell[drag_range_preview="true"][drag_range_end="true"] {{
            border-right: 2px solid {tc(0.45)};
            border-top-right-radius: {drag_range_radius}px;
            border-bottom-right-radius: {drag_range_radius}px;
        }}
        ClickableCell[drag_mode="move"] {{
            background-color: {tc(0.30)};
            border: 2.5px solid {theme_color};
            border-radius: 4px;
        }}
        ClickableCell[drag_mode="move"] QLabel#dayNumLabel {{
            color: #ffffff;
            font-weight: 800;
            background-color: {theme_color};
            border-radius: 4px;
            padding: 1px 6px;
        }}
        ClickableCell[drag_mode="copy"] {{
            background-color: {_hue_shifted_rgba(theme_color, 120, 0.25)};
            border: 2.5px solid {_hue_shifted_rgba(theme_color, 120, 1.0)};
            border-radius: 4px;
        }}
        ClickableCell[drag_mode="copy"] QLabel#dayNumLabel {{
            color: {p["text_inverse"]};
            font-weight: 800;
            background-color: {_hue_shifted_rgba(theme_color, 120, 1.0)};
            border-radius: 4px;
            padding: 1px 6px;
        }}
        ClickableCell[drag_mode="copy"][drag_batch="true"] {{
            background-color: {_hue_shifted_rgba(theme_color, 120, 0.32)};
        }}

        /* Typography */
        QLabel#dayNumLabel {{
            color: {p["weekday_normal"]}; font-weight: 600; background: transparent;
            font-family: {family}; font-size: {base_pt}pt;
            padding: 2px 4px;
        }}
        ClickableCell[is_today="true"] QLabel#dayNumLabel {{
            color: {tc(0.92)};
        }}
        ClickableCell[is_other_month="true"] QLabel#dayNumLabel {{
            color: {p["weekday_other"]};
        }}

        /* Task Buttons - Premium Look */
        DraggableTaskButton {{
            border: 1px solid rgba(255, 255, 255, 0.08);
            background-color: rgba(255, 255, 255, 0.03);
            color: {p["task_btn_text"]};
            font-family: {family};
            font-size: {base_pt}pt;
            text-align: left;
            padding: 5px 10px;
            border-radius: {global_task_radius}px;
            margin: 2px 4px;
        }}
        DraggableTaskButton:hover {{
            background-color: {tc(0.15)};
            border: 1px solid {tc(0.4)};
        }}
        DraggableTaskButton[dragging="true"] {{
            background-color: {tc(0.06)};
            border: 1px solid {tc(0.20)};
            color: {_hex_to_rgba(p["task_btn_text"], 0.35)};
        }}
        DraggableTaskButton[selected="true"] {{
            border: 2px solid {tc(0.8)} !important;
            background-color: {tc(0.2)} !important;
            color: #ffffff;
            font-weight: 600;
        }}

        /* Form Inputs */
        QLineEdit, QComboBox, QSpinBox, QDateTimeEdit {{
            background-color: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 6px;
            padding: 4px 8px;
            color: {p["text_primary"]};
            font-family: {family};
            font-size: {base_pt}pt;
        }}
        QLineEdit:focus, QComboBox:focus {{
            border: 1px solid {tc(0.8)};
            background-color: rgba(255, 255, 255, 0.08);
        }}

        /* Scrollbars - Minimalist */
        QScrollBar:vertical {{
            border: none; background: transparent; width: 4px; margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: rgba(255,255,255,0.1); border-radius: 2px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {tc(0.8)};
        }}

        /* Global Buttons & Dialogs */
        QPushButton {{
            background-color: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 6px;
            padding: 5px 12px;
            color: {p["text_secondary"]};
            font-family: {family};
            font-size: {base_pt}pt;
            min-width: 60px;
        }}
        QPushButton:hover {{
            background-color: rgba(255, 255, 255, 0.15);
            border-color: rgba(255, 255, 255, 0.25);
            color: {p["text_primary"]};
        }}
        QPushButton:pressed {{
            background-color: rgba(255, 255, 255, 0.05);
        }}
        QPushButton:default, QPushButton[default="true"] {{
            background-color: {tc(0.12)};
            border: 1px solid {tc(0.55)};
            color: {theme_color};
            font-weight: bold;
        }}
        QPushButton:default:hover, QPushButton[default="true"]:hover {{
            background-color: {tc(0.20)};
            border-color: {theme_color};
            color: white;
        }}

        QMessageBox, QDialog {{
            background-color: {panel_base_color};
        }}
        QMessageBox QLabel {{
            color: {p["text_primary"]};
            font-size: {_scaled_pt(base_pt, 1)}pt;
        }}
    """


def build_tooltip_stylesheet(
    base_pt=10, theme_color="#4da6ff", text_theme="dark", panel_base_color="#1c1c1c", palette=None
):
    if base_pt is None or base_pt <= 0:
        base_pt = 10
    if palette is None:
        palette = derive_ui_palette(text_theme, panel_base_color, theme_color=theme_color)

    from PyQt6.QtGui import QColor as _QC

    pb = _QC(panel_base_color)
    if not pb.isValid():
        pb = _QC("#1c1c1c")
    r = max(0, min(255, pb.red() - 10))
    g = max(0, min(255, pb.green() - 10))
    b_val = max(0, min(255, pb.blue() - 10))
    tip_bg = f"rgba({r},{g},{b_val},246)"
    tip_text = palette["text_primary"]
    shape = get_ui_shape_tokens()
    tooltip_radius = int(shape.get("tooltip_radius", 0))

    return f"""
        QToolTip {{
            background-color: {tip_bg};
            color: {tip_text};
            border: 1px solid {theme_color};
            padding: 6px 10px;
            border-radius: {tooltip_radius}px;
            font-size: {base_pt}pt;
        }}
    """


def _build_top_menu_button_style(menu_btn_pt, theme_color, text_theme="dark"):
    def _ta(a):
        return _hex_to_rgba(theme_color, round(a / 255, 3))

    shape = get_ui_shape_tokens()
    top_menu_btn_radius = int(shape.get("top_menu_button_radius", 0))
    text_pal = derive_text_palette(text_theme, theme_color)
    btn_color = text_pal["text_primary"]
    return f"""
        QToolButton {{
            color: {btn_color}; background: transparent; border: none;
            padding: 6px 12px; font-weight: normal; font-size: {menu_btn_pt}pt;
            border-radius: {top_menu_btn_radius}px;
        }}
        QToolButton:hover {{ background: {_ta(40)}; color: {btn_color}; }}
        QToolButton:pressed, QToolButton[popupMode="0"]:open {{
            background: {_ta(64)};
            color: {btn_color};
            border-top: 2px solid {theme_color};
        }}
        QToolButton::menu-indicator {{ image: none; }}
    """


def _build_app_menu_style(
    menu_pt,
    theme_color,
    text_theme="dark",
    *,
    panel_base_color=None,
    opacity_factor=None,
    settings=None,
    persist_opacity=True,
):
    from PyQt6.QtCore import QSettings
    from PyQt6.QtGui import QColor

    def _ta(a):
        return _hex_to_rgba(theme_color, round(a / 255, 3))

    text_pal = derive_text_palette(text_theme, theme_color)
    cfg = settings or QSettings("kimhyojin", "Dark Calendar")
    _, effective_base, effective_opacity = get_theme_palette_inputs(
        cfg,
        persist_opacity=persist_opacity,
    )
    panel_base = panel_base_color or effective_base
    opacity = effective_opacity if opacity_factor is None else float(opacity_factor)
    base = QColor(str(panel_base))
    if not base.isValid():
        base = QColor("#1c1c1c")
    menu_bg = f"rgba({base.red()},{base.green()},{base.blue()},{max(210, int(242 * opacity))})"
    menu_color = text_pal["text_primary"]
    menu_border = "rgba(255,255,255,0.12)"
    sep_color = "rgba(255,255,255,0.10)"
    shape = get_ui_shape_tokens()
    app_menu_radius = int(shape.get("app_menu_radius", 0))
    app_menu_item_radius = int(shape.get("app_menu_item_radius", 0))

    return f"""
        QMenu {{
            background-color: {menu_bg}; color: {menu_color}; border: 1px solid {menu_border};
            padding: 4px; border-radius: {app_menu_radius}px; font-size: {menu_pt}pt;
        }}
        QMenu::item {{
            padding: 6px 28px 6px 6px;
            border-radius: {app_menu_item_radius}px; margin: 2px;
            min-width: 170px;
        }}
        QMenu::item:selected {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {_ta(40)}, stop:1 {_ta(78)});
            color: {menu_color};
            border: 1px solid {_ta(120)};
        }}
        QMenu::item:checked {{ color: {theme_color}; }}
        QMenu::separator {{ height: 1px; background: {sep_color}; margin: 4px 10px; }}
        QMenu::indicator {{
            subcontrol-origin: padding;
            subcontrol-position: center right;
            right: 8px;
            width: 12px;
            height: 12px;
        }}
    """


def apply_top_menu_theme(
    self,
    base_pt=None,
    theme_color=None,
    text_theme=None,
    panel_base_color=None,
    opacity_factor=None,
    *,
    persist_opacity=True,
):
    if base_pt is None:
        base_pt = self.settings.value("font_size", 10, type=int)
    if not base_pt or base_pt <= 0:
        base_pt = 10
    if theme_color is None:
        theme_color = self.settings.value("theme_color", "#4da6ff")
    if text_theme is None:
        text_theme = self.settings.value("text_theme", "dark")

    menu_btn_pt = _scaled_pt(base_pt, 0, 9)
    menu_style = _build_top_menu_button_style(menu_btn_pt, theme_color, text_theme)
    app_menu_style = _build_app_menu_style(
        base_pt,
        theme_color,
        text_theme,
        panel_base_color=panel_base_color,
        opacity_factor=opacity_factor,
        settings=self.settings,
        persist_opacity=persist_opacity,
    )
    self._last_menu_style = app_menu_style

    def _apply_menu_style_recursive(menu, style, seen):
        if menu is None:
            return
        menu_id = id(menu)
        if menu_id in seen:
            return
        seen.add(menu_id)
        menu.setStyleSheet(style)
        for action in menu.actions():
            sub = action.menu()
            if sub is not None:
                _apply_menu_style_recursive(sub, style, seen)

    for attr in (
        "add_menu_btn",
        "view_menu_btn",
        "display_menu_btn",
        "widgets_menu_btn",
        "sys_menu_btn",
    ):
        btn = getattr(self, attr, None)
        if btn is not None:
            btn.setStyleSheet(menu_style)

    seen = set()
    for attr in ("add_menu", "view_menu", "display_menu", "widgets_menu", "sys_menu"):
        _apply_menu_style_recursive(getattr(self, attr, None), app_menu_style, seen)

    for attr in (
        "panel_menu",
        "preset_load_menu",
        "preset_save_menu",
        "preset_rename_menu",
        "preset_delete_menu",
        "theme_menu",
        "appearance_menu",
        "panel_bg_menu",
        "panel_bg_recent_menu",
        "lang_menu",
    ):
        _apply_menu_style_recursive(getattr(self, attr, None), app_menu_style, seen)

    _owner = self

    def _make_on_show(menu_attr):
        def _on_show():
            menu_obj = getattr(_owner, menu_attr, None)
            if menu_obj is None:
                return
            from calendar_app.shared.theme_snapshot import build_theme_snapshot

            snapshot = build_theme_snapshot(_owner.settings)
            fresh_style = _build_app_menu_style(
                _owner.settings.value("font_size", 10, type=int) or 10,
                snapshot.theme_color,
                snapshot.text_theme,
                panel_base_color=snapshot.panel_base_color,
                opacity_factor=snapshot.opacity_factor,
                settings=_owner.settings,
                persist_opacity=False,
            )
            _owner._last_menu_style = fresh_style
            seen2 = set()
            _apply_menu_style_recursive(menu_obj, fresh_style, seen2)

        return _on_show

    _REFRESH_PROP = "_theme_refresh_connected"
    for _root_attr in ("add_menu", "view_menu", "display_menu", "widgets_menu", "sys_menu"):
        _menu = getattr(self, _root_attr, None)
        if _menu is not None and not getattr(_menu, _REFRESH_PROP, False):
            _menu.aboutToShow.connect(_make_on_show(_root_attr))
            setattr(_menu, _REFRESH_PROP, True)
