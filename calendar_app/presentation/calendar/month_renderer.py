import datetime
import html as _html_mod
import logging

from PyQt6.QtCore import QDate, QPoint, QSize, Qt
from PyQt6.QtGui import QAction, QBrush, QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from calendar_app.domain.task_constants import priority_icon
from calendar_app.infrastructure.google_sync.common import is_gcal_enabled
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.theme.ui_tokens import get_ui_shape_tokens
from calendar_app.shared.color_utils import derive_ui_palette
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.qt_helpers import find_parent_dock
from calendar_app.shared.search_utils import clean_calendar_description
from calendar_app.shared.search_utils import clean_display_text as _tooltip_clean_text
from calendar_app.shared.theme_settings import (
    fpt as _fpt,
)
from calendar_app.shared.theme_settings import (
    get_theme_color,
    get_theme_palette_inputs,
)
from calendar_app.shared.ui_tokens import get_ui_tokens

logger = logging.getLogger(__name__)

_calendar_meta_cache = None


def invalidate_calendar_meta_cache():
    global _calendar_meta_cache
    _calendar_meta_cache = None


def _build_color_icon(color_hex: str | None, size: int = 14) -> QIcon:
    """Build a circular color icon for use in menus."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    fallback_accent = _calendar_default_accent()
    color = QColor(str(color_hex or fallback_accent))
    if not color.isValid():
        color = QColor(fallback_accent)

    painter.setBrush(QBrush(color))
    # Subtle border to ensure visibility on all backgrounds
    border_color = color.lighter(120) if color.lightness() < 50 else color.darker(120)
    painter.setPen(QPen(border_color, 0.5))

    painter.drawEllipse(1, 1, size - 3, size - 3)
    painter.end()
    return QIcon(px)


def _ui_palette():
    text_theme, panel_base, opacity_factor = get_theme_palette_inputs()
    return derive_ui_palette(text_theme, panel_base, opacity_factor)


def _ui_tokens(settings=None):
    return get_ui_tokens(settings=settings)


def _shape_tokens(settings=None):
    return get_ui_shape_tokens(settings=settings)


def _resolve_calendar_tokens(tokens=None, settings=None):
    resolved = dict(_ui_tokens(settings=settings))
    if tokens:
        resolved.update(tokens)
    return resolved


def _resolve_calendar_shape(shape=None, settings=None):
    resolved = dict(_shape_tokens(settings=settings))
    if shape:
        resolved.update(shape)
    return resolved


def _calendar_default_accent(tokens=None) -> str:
    resolved = _resolve_calendar_tokens(tokens=tokens)
    return str(resolved.get("accent", _ui_tokens().get("accent", "#4da6ff")))


def _month_grid_start(first_day: QDate, start_monday: bool = True) -> QDate:
    weekday = first_day.dayOfWeek()
    offset = (weekday - 1) if start_monday else (weekday % 7)
    return first_day.addDays(-offset)


def _month_grid_end(last_day: QDate, start_monday: bool = True) -> QDate:
    weekday = last_day.dayOfWeek()
    if start_monday:
        trailing = 7 - weekday
    else:
        trailing = (6 - (weekday % 7)) % 7
    return last_day.addDays(trailing)


def _build_month_dates(
    target_date: QDate, *, show_weekends: bool = True, start_monday: bool = True
) -> list[QDate]:
    """Return the minimal full-week date span needed to render the selected month."""
    if not isinstance(target_date, QDate) or not target_date.isValid():
        return []

    first_day = QDate(target_date.year(), target_date.month(), 1)
    last_day = first_day.addMonths(1).addDays(-1)
    start_grid = _month_grid_start(first_day, start_monday=start_monday)
    end_grid = _month_grid_end(last_day, start_monday=start_monday)

    dates: list[QDate] = []
    day = start_grid
    while day <= end_grid:
        if show_weekends or day.dayOfWeek() < 6:
            dates.append(day)
        day = day.addDays(1)
    return dates


def _calendar_scroll_style() -> str:
    return "QScrollArea { background: transparent; border: none; }"


def _accent_rgba(alpha: float, tokens=None):
    color = QColor(_calendar_default_accent(tokens=tokens))
    if not color.isValid():
        color = QColor(_calendar_default_accent())
    return f"rgba({color.red()},{color.green()},{color.blue()},{alpha})"


def _calendar_surface_style(tokens=None, shape=None):
    tokens = _resolve_calendar_tokens(tokens=tokens)
    shape = _resolve_calendar_shape(shape=shape)
    surface_radius = int(shape.get("calendar_surface_radius", 8))
    cell_border = tokens["divider"]
    accent = _accent_rgba(0.5, tokens)
    accent_soft = _accent_rgba(0.1, tokens)
    accent_hover = _accent_rgba(0.08, tokens)
    accent_selected = _accent_rgba(0.10, tokens)
    accent_selected_border = _accent_rgba(0.44, tokens)
    return f"""
        QFrame#calendar_surface {{
            background-color: {tokens["bg_main"]};
            border-radius: {surface_radius}px;
            border: 1px solid {tokens["divider"]};
        }}
        ClickableCell {{
            background-color: {tokens.get("cell_bg", "transparent")};
            border: 1px solid {cell_border};
            border-radius: 0px;
        }}
        ClickableCell:hover {{
            background-color: {accent_hover};
            border: 1px solid {_accent_rgba(0.3, tokens)};
        }}
        ClickableCell[is_today="true"] {{
            background-color: {accent_soft};
            border: 1.5px solid {accent};
        }}
        ClickableCell[selected_date="true"] {{
            background-color: {accent_selected};
            border: 1px solid {accent_selected_border};
        }}
    """


def _calendar_toolbar_shell_style(expanded: bool, tokens=None, shape=None):
    if not expanded:
        return """
            QWidget#calendar_toolbar {
                background-color: transparent;
                border: none;
            }
        """
    tokens = _resolve_calendar_tokens(tokens=tokens)
    shape = _resolve_calendar_shape(shape=shape)
    toolbar_radius = int(shape.get("calendar_toolbar_surface_radius", 8))
    return f"""
        QWidget#calendar_toolbar {{
            background-color: {tokens["bg_top"]};
            border-radius: {toolbar_radius}px;
            border: 1px solid {tokens["divider"]};
        }}
    """


def _calendar_toolbar_style_bundle(tokens=None, shape=None):
    tokens = _resolve_calendar_tokens(tokens=tokens)
    shape = _resolve_calendar_shape(shape=shape)
    button_radius = int(shape.get("calendar_toolbar_button_radius", 8))
    menu_radius = int(shape.get("calendar_menu_radius", 6))
    menu_item_radius = int(shape.get("calendar_menu_item_radius", 4))
    date_radius = int(shape.get("calendar_date_badge_radius", 9))
    selection_radius = int(shape.get("calendar_selection_badge_radius", 10))
    more_radius = int(shape.get("calendar_more_button_radius", 4))
    btn_txt = tokens["text_primary"]
    btn_subtxt = tokens["text_secondary"]
    btn_bg = tokens["bg_item"]
    btn_hover = tokens.get("bg_item_hover", tokens.get("bg_hover", btn_bg))
    btn_border = tokens["border"]
    btn_border_strong = tokens.get(
        "border_strong", tokens.get("accent_border", _accent_rgba(0.25, tokens))
    )
    accent_soft = tokens.get("accent_soft", _accent_rgba(0.16, tokens))
    accent_border = tokens.get("accent_border", _accent_rgba(0.40, tokens))
    accent_soft_strong = _accent_rgba(0.24, tokens)
    accent_soft_hover = _accent_rgba(0.32, tokens)
    accent_soft_pressed = _accent_rgba(0.40, tokens)
    menu_bg = tokens.get("bg_alt", tokens["bg_main"])
    menu_txt = tokens["text_primary"]
    menu_checked = tokens["accent"]
    divider = tokens["divider"]
    return {
        "today_btn": f"""
            QPushButton {{
                color: {btn_txt};
                background: {accent_soft_strong};
                font-weight: bold;
                font-size: {_fpt()};
                border-radius: {button_radius}px;
                padding: 4px 12px;
                border: 1px solid {accent_border};
            }}
            QPushButton:hover {{
                background: {accent_soft_hover};
                border: 1px solid {accent_border};
                color: {btn_txt};
            }}
            QPushButton:pressed {{
                background: {accent_soft_pressed};
                border: 1px solid {accent_border};
            }}
        """,
        "nav_btn": f"""
            QPushButton {{
                color: {btn_txt};
                background: {btn_bg};
                font-weight: bold;
                font-size: {_fpt(-1)};
                border-radius: {button_radius}px;
                padding: 3px 8px;
                border: 1px solid {btn_border};
                min-width: 30px;
                max-width: 30px;
            }}
            QPushButton:hover {{
                color: {btn_txt};
                background: {accent_soft};
                border: 1px solid {btn_border_strong};
            }}
            QPushButton:pressed {{
                background: {accent_soft_strong};
                border: 1px solid {accent_border};
            }}
        """,
        "menu_btn": f"""
            QPushButton {{
                color: {btn_txt};
                background: {btn_bg};
                font-weight: bold;
                font-size: {_fpt()};
                border-radius: {button_radius}px;
                padding: 4px 12px;
                border: 1px solid {btn_border};
            }}
            QPushButton:hover {{
                color: {btn_txt};
                background: {accent_soft};
                border: 1px solid {btn_border_strong};
            }}
            QPushButton:open {{
                background: {accent_soft_strong};
                border: 1px solid {accent_border};
                color: {btn_txt};
            }}
            QPushButton::menu-indicator {{
                image: none;
                width: 0px;
            }}
        """,
        "icon_btn": f"""
            QPushButton {{
                color: {btn_txt};
                background: {btn_bg};
                border: 1px solid {btn_border};
                font-size: {_fpt(-1)};
                width: 28px;
                height: 28px;
                border-radius: {button_radius}px;
                padding: 0;
            }}
            QPushButton:hover {{
                color: {btn_txt};
                background: {accent_soft_strong};
                border: 1px solid {btn_border_strong};
            }}
            QPushButton:pressed {{
                background: {accent_soft_hover};
                border: 1px solid {accent_border};
            }}
        """,
        "dropdown_menu": f"""
            QMenu {{
                background-color: {menu_bg};
                color: {menu_txt};
                border: 1px solid {btn_border};
                padding: 4px;
                border-radius: {menu_radius}px;
                font-size: {_fpt()};
            }}
            QMenu::item {{
                padding: 6px 20px 6px 12px;
                border-radius: {menu_item_radius}px;
                margin: 1px 2px;
            }}
            QMenu::item:selected {{
                background: {accent_soft_strong};
                border: 1px solid {accent_border};
                color: {menu_txt};
            }}
            QMenu::item:checked {{
                color: {menu_checked};
            }}
            QMenu::separator {{
                height: 1px;
                background: {divider};
                margin: 4px 8px;
            }}
        """,
        "date_label": (
            f"color: {btn_txt}; font-weight: 700; font-size: {_fpt(1)}; "
            f"padding: 2px 10px; border-radius: {date_radius}px; "
            f"background: {btn_bg}; border: 1px solid {btn_border};"
        ),
        "selection_label": (
            f"color: {btn_subtxt}; padding: 2px 12px; "
            f"background: {accent_soft}; border: 1px solid {accent_border}; "
            f"border-radius: {selection_radius}px;"
        ),
        "more_btn": (
            f"QPushButton {{ color: {btn_subtxt}; font-size: {_fpt(-1)}; font-weight: bold; "
            f"background: transparent; border: none; text-align: left; padding: 2px 5px; "
            f"border-radius: {more_radius}px; }} "
            f"QPushButton:hover {{ background-color: {btn_hover}; color: {btn_txt}; }}"
        ),
    }


def _subscription_detail_style_bundle(tokens=None, shape=None):
    tokens = _resolve_calendar_tokens(tokens=tokens)
    shape = _resolve_calendar_shape(shape=shape)
    detail_radius = int(shape.get("calendar_menu_item_radius", 4))
    return {
        "title": f"font-size: {_fpt(3)}; font-weight: bold; color: {tokens['accent']}; padding-bottom: 10px;",
        "separator": f"color: {tokens['divider']}; margin-bottom: 10px;",
        "scroll": _calendar_scroll_style(),
        "inner": "background: transparent;",
        "key_label": (
            f"color: {tokens['text_secondary']}; font-size: {_fpt(-1)}; "
            "min-width: 78px; max-width: 78px;"
        ),
        "value": f"color: {tokens['text_primary']}; font-size: {_fpt()};",
        "value_muted": f"color: {tokens['text_muted']}; font-size: {_fpt()};",
        "copy_btn": (
            f"QPushButton {{ color: {tokens['text_secondary']}; font-size: {_fpt(-2)}; "
            f"border: 1px solid {tokens['border']}; "
            f"border-radius: {detail_radius}px; padding: 1px 4px; }} "
            f"QPushButton:hover {{ color: {tokens['accent']}; "
            f"border-color: {tokens.get('accent_border', _accent_rgba(0.4, tokens))}; }}"
        ),
        "divider": f"color: {tokens['divider']}; margin: 2px 0;",
    }


class _CalToolbarWidget(QWidget):
    """Toolbar widget that supports dock drag and collapse/expand behavior."""

    def __init__(self):
        super().__init__()
        self._dock_ref = None
        self._content_widget = None
        self._expanded = True
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("calendar_toolbar")
        self._apply_visual_style(expanded=True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def _apply_visual_style(self, expanded: bool):
        self.setStyleSheet(_calendar_toolbar_shell_style(expanded))

    def set_content_widget(self, content: QWidget):
        self._content_widget = content

    def set_toolbar_expanded(self, expanded: bool):
        expanded = bool(expanded)
        self._expanded = expanded
        if self._content_widget is not None:
            self._content_widget.setVisible(expanded)
        self._apply_visual_style(expanded)
        if expanded:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
        else:
            self.setFixedHeight(6)
        self.updateGeometry()

    def is_toolbar_expanded(self):
        return self._expanded

    def _dock(self):
        return find_parent_dock(self, self._dock_ref)

    def bind_dock(self, dock):
        self._dock_ref = dock

    def mousePressEvent(self, event):
        dock = self._dock()
        if dock:
            dock.mousePressEvent(event)

    def mouseMoveEvent(self, event):
        dock = self._dock()
        if dock:
            dock.mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        dock = self._dock()
        if dock:
            dock.mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        dock = self._dock()
        if dock:
            dock.mouseDoubleClickEvent(event)


class _CalendarSurfaceFrame(QFrame):
    """Background drag zone delegating to native Qt dock drag when toolbar is collapsed."""

    def __init__(self, app):
        super().__init__()
        self._app = app
        self._drag_delegating = False
        self._sys_drag_active = False
        self._sys_drag_mode = None
        self.setMouseTracking(True)

    def _center_dock(self):
        return getattr(self._app, "center_dock", None)

    def _toolbar_collapsed(self):
        tb = getattr(self._app, "calendar_toolbar_widget", None)
        if tb is not None and hasattr(tb, "is_toolbar_expanded"):
            return not tb.is_toolbar_expanded()
        if hasattr(self._app, "_calendar_toolbar_visible_setting"):
            return not self._app._calendar_toolbar_visible_setting()
        return False

    def _floating_drag_zone(self, dock, global_pos, corner_px=16, edge_px=10):
        g = dock.frameGeometry()
        x = global_pos.x() - g.left()
        y = global_pos.y() - g.top()
        w = g.width()
        h = g.height()
        if x < 0 or y < 0 or x > w or y > h:
            return None
        if x <= corner_px and y <= corner_px:
            return "corner_tl"
        if x >= (w - corner_px) and y <= corner_px:
            return "corner_tr"
        if x <= corner_px and y >= (h - corner_px):
            return "corner_bl"
        if x >= (w - corner_px) and y >= (h - corner_px):
            return "corner_br"
        if x <= edge_px or x >= (w - edge_px) or y <= edge_px or y >= (h - edge_px):
            return "edge_move"
        return None

    def _start_system_move(self, dock):
        try:
            win = dock.windowHandle()
            if win is None or not hasattr(win, "startSystemMove"):
                return False
            return bool(win.startSystemMove())
        except Exception:
            return False

    def _start_system_resize(self, dock, edges):
        try:
            win = dock.windowHandle()
            if win is None or not hasattr(win, "startSystemResize"):
                return False
            return bool(win.startSystemResize(edges))
        except Exception:
            return False

    def _dock_under_cursor(self, global_pos):
        dock = self._center_dock()
        dm = getattr(self._app, "dock_manager", None)
        if dm is None:
            return None

        w = QApplication.widgetAt(global_pos)
        while w is not None and not isinstance(w, QDockWidget):
            w = w.parentWidget()
        if isinstance(w, QDockWidget) and w is not dock and not w.isFloating() and w.isVisible():
            return w

        # Relax hit-test: allow snapping to a nearby dock even when cursor is on splitter/gap.
        snap_px = 80
        nearest = None
        nearest_dist2 = None
        for cand in dm.findChildren(QDockWidget):
            if cand is dock or cand.isFloating() or not cand.isVisible():
                continue
            g = cand.frameGeometry()
            inflated = g.adjusted(-snap_px, -snap_px, snap_px, snap_px)
            if not inflated.contains(global_pos):
                continue
            cx = min(max(global_pos.x(), g.left()), g.right())
            cy = min(max(global_pos.y(), g.top()), g.bottom())
            dx = global_pos.x() - cx
            dy = global_pos.y() - cy
            dist2 = (dx * dx) + (dy * dy)
            if nearest is None or dist2 < nearest_dist2:
                nearest = cand
                nearest_dist2 = dist2

        if nearest is not None:
            return nearest
        return None

    def _nearest_side_in_rect(self, x, y, w, h):
        w = max(1, w)
        h = max(1, h)
        d_left = x
        d_right = w - x
        d_top = y
        d_bottom = h - y
        min_d = min(d_left, d_right, d_top, d_bottom)
        if min_d == d_left:
            return "left"
        if min_d == d_right:
            return "right"
        if min_d == d_top:
            return "top"
        return "bottom"

    def _split_side_in_rect(self, x, y, w, h):
        """Use center-line based split decision so docking triggers earlier."""
        w = max(1, w)
        h = max(1, h)
        nx = min(1.0, max(0.0, x / w))
        ny = min(1.0, max(0.0, y / h))
        dx = nx - 0.5
        dy = ny - 0.5
        # Make top/bottom split easier than left/right:
        # 1) Strong vertical zones near top/bottom always map vertically.
        # 2) Around center, apply a vertical bias factor.
        if ny <= 0.45:
            return "top"
        if ny >= 0.55:
            return "bottom"

        vertical_bias = 1.35
        if abs(dy) * vertical_bias >= abs(dx):
            return "bottom" if dy >= 0 else "top"
        return "right" if dx >= 0 else "left"

    def _relaxed_redock(self, global_pos):
        dock = self._center_dock()
        dm = getattr(self._app, "dock_manager", None)
        if dock is None or dm is None or not dock.isFloating():
            return False

        target = self._dock_under_cursor(global_pos)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)

        try:
            if target is not None:
                local = target.mapFromGlobal(global_pos)
                # Relaxed rule: crossing target midline is enough to select docking side.
                side = self._split_side_in_rect(
                    local.x(), local.y(), target.width(), target.height()
                )
                target_area = dm.dockWidgetArea(target)
                if target_area == Qt.DockWidgetArea.NoDockWidgetArea:
                    target_area = Qt.DockWidgetArea.LeftDockWidgetArea
                dm.addDockWidget(target_area, dock)
                orientation = (
                    Qt.Orientation.Horizontal
                    if side in ("left", "right")
                    else Qt.Orientation.Vertical
                )
                dm.splitDockWidget(target, dock, orientation)
                if side in ("left", "top"):
                    dm.splitDockWidget(dock, target, orientation)
                dock.setFloating(False)
                if hasattr(self._app, "sync_panel_menu_state"):
                    self._app.sync_panel_menu_state()
                return True
        except Exception:
            pass

        # Fallback: dock by nearest side of the whole dock manager.
        top_left = dm.mapToGlobal(QPoint(0, 0))
        rel_x = global_pos.x() - top_left.x()
        rel_y = global_pos.y() - top_left.y()
        if rel_x < 0 or rel_y < 0 or rel_x > dm.width() or rel_y > dm.height():
            return False
        side = self._split_side_in_rect(rel_x, rel_y, dm.width(), dm.height())
        area_map = {
            "left": Qt.DockWidgetArea.LeftDockWidgetArea,
            "right": Qt.DockWidgetArea.RightDockWidgetArea,
            "top": Qt.DockWidgetArea.TopDockWidgetArea,
            "bottom": Qt.DockWidgetArea.BottomDockWidgetArea,
        }
        dm.addDockWidget(area_map[side], dock)
        dock.setFloating(False)
        if hasattr(self._app, "sync_panel_menu_state"):
            self._app.sync_panel_menu_state()
        return True

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._toolbar_collapsed():
            dock = self._center_dock()
            if dock is not None:
                if dock.isFloating():
                    zone = self._floating_drag_zone(dock, event.globalPosition().toPoint())
                    if zone and zone.startswith("corner_"):
                        edge_map = {
                            "corner_tl": Qt.Edge.TopEdge | Qt.Edge.LeftEdge,
                            "corner_tr": Qt.Edge.TopEdge | Qt.Edge.RightEdge,
                            "corner_bl": Qt.Edge.BottomEdge | Qt.Edge.LeftEdge,
                            "corner_br": Qt.Edge.BottomEdge | Qt.Edge.RightEdge,
                        }
                        self._sys_drag_active = self._start_system_resize(dock, edge_map[zone])
                        self._sys_drag_mode = "resize"
                        if self._sys_drag_active:
                            event.accept()
                            return
                    elif zone == "edge_move":
                        self._sys_drag_active = self._start_system_move(dock)
                        self._sys_drag_mode = "move"
                        if self._sys_drag_active:
                            event.accept()
                            return

                self._drag_delegating = True
                dock.mousePressEvent(event)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._toolbar_collapsed()
            and self._drag_delegating
            and (event.buttons() & Qt.MouseButton.LeftButton)
        ):
            dock = self._center_dock()
            if dock is not None:
                dock.mouseMoveEvent(event)
                event.accept()
                return
        if self._toolbar_collapsed() and not (event.buttons() & Qt.MouseButton.LeftButton):
            dock = self._center_dock()
            if dock is not None:
                if dock.isFloating():
                    zone = self._floating_drag_zone(dock, event.globalPosition().toPoint())
                    if zone in ("corner_tl", "corner_br"):
                        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                    elif zone in ("corner_tr", "corner_bl"):
                        self.setCursor(Qt.CursorShape.SizeBDiagCursor)
                    elif zone == "edge_move":
                        self.setCursor(Qt.CursorShape.SizeAllCursor)
                    else:
                        self.unsetCursor()
                else:
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.unsetCursor()

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        dock = self._center_dock()
        if self._sys_drag_active and self._sys_drag_mode == "move":
            self._relaxed_redock(event.globalPosition().toPoint())
        if self._drag_delegating and dock is not None:
            dock.mouseReleaseEvent(event)
            self._relaxed_redock(event.globalPosition().toPoint())
            event.accept()
            self._drag_delegating = False
            self._sys_drag_active = False
            self._sys_drag_mode = None
            return
        self._drag_delegating = False
        self._sys_drag_active = False
        self._sys_drag_mode = None
        super().mouseReleaseEvent(event)


import time  # noqa: E402

from calendar_app.infrastructure.db import search_repo, task_repo  # noqa: E402
from calendar_app.presentation.widgets.ui_components import (  # noqa: E402
    ClickableCell,
    DraggableTaskButton,
    install_hover_info,
)
from calendar_app.shared.search_utils import matches_search_query  # noqa: E402


def _coerce_qdate(value):
    if value is None:
        return None
    if isinstance(value, QDate):
        return value if value.isValid() else None

    text = str(value).strip()
    if not text:
        return None

    normalized = text.replace("/", "-").replace(".", "-")
    date_part = normalized.split(" ")[0]
    if "T" in date_part:
        date_part = date_part.split("T", 1)[0]
    date_part = date_part[:10]
    qdate = QDate.fromString(date_part, "yyyy-MM-dd")
    if qdate.isValid():
        return qdate

    iso_candidate = normalized
    if iso_candidate.endswith("Z"):
        iso_candidate = f"{iso_candidate[:-1]}+00:00"
    try:
        dt = datetime.datetime.fromisoformat(iso_candidate.replace(" ", "T"))
        return QDate(dt.year, dt.month, dt.day)
    except Exception:
        pass

    qdate = QDate.fromString(normalized, Qt.DateFormat.ISODate)
    if qdate.isValid():
        return qdate
    qdate = QDate.fromString(normalized, Qt.DateFormat.ISODateWithMs)
    return qdate if qdate.isValid() else None


def _task_date_range(task_row):
    cached_start = task_row.get("_cached_start_qdate")
    cached_end = task_row.get("_cached_end_qdate")
    if (
        isinstance(cached_start, QDate)
        and cached_start.isValid()
        and isinstance(cached_end, QDate)
        and cached_end.isValid()
    ):
        return cached_start, cached_end

    start_date = _coerce_qdate(task_row.get("deadline")) or _coerce_qdate(
        task_row.get("target_date")
    )
    if not start_date:
        return None, None

    end_date = _coerce_qdate(task_row.get("end_date")) or start_date
    if end_date < start_date:
        end_date = start_date
    task_row["_cached_start_qdate"] = start_date
    task_row["_cached_end_qdate"] = end_date
    return start_date, end_date


def _is_multi_day_task(task_row):
    start_date, end_date = _task_date_range(task_row)
    return bool(start_date and end_date and start_date < end_date)


def _task_matches_search(task_row, search_query):
    return matches_search_query(
        search_query,
        task_row.get("name", ""),
        task_row.get("memo") or task_row.get("description"),
        task_row.get("location"),
        task_row.get("assignee"),
    )


def _subscription_source_text(task_row):
    return str(
        task_row.get("_subscription_summary") or task_row.get("_subscription_calendar_id") or ""
    ).strip()


def _normalize_subscription_event(subscription_row, event, index):
    all_day = bool(
        str(getattr(event, "start_time", "")).strip()
        and "T" not in str(getattr(event, "start_time", ""))
    )
    start_value = str(getattr(event, "start_time", "") or "").strip()
    end_value = str(getattr(event, "end_time", "") or "").strip()
    if all_day:
        start_str = f"{start_value[:10]} 00:00:00" if start_value else ""
        end_str = start_str
        if end_value:
            try:
                exclusive = datetime.datetime.strptime(end_value[:10], "%Y-%m-%d").date()
                inclusive = exclusive - datetime.timedelta(days=1)
                end_str = f"{inclusive.isoformat()} 00:00:00"
            except Exception:
                end_str = f"{end_value[:10]} 00:00:00"
    else:
        start_str = start_value.replace("T", " ")[:19]
        end_str = end_value.replace("T", " ")[:19]

    summary = (
        subscription_row.get("summary") or subscription_row.get("calendar_id") or "Subscription"
    )
    synthetic_id = -1 * (
        abs(hash((subscription_row.get("calendar_id"), getattr(event, "id", ""), index)))
        % 2_000_000_000
        + 1
    )
    return {
        "id": synthetic_id,
        "name": getattr(event, "summary", "") or t("common.no_title"),
        "deadline": start_str,
        "end_date": end_str,
        "_start_raw": str(getattr(event, "start_time", "") or "").strip(),
        "_end_raw": str(getattr(event, "end_time", "") or "").strip(),
        "description": getattr(event, "description", "") or "",
        "memo": getattr(event, "description", "") or "",
        "location": getattr(event, "location", "") or "",
        "assignee": "",
        "all_day": int(all_day),
        "priority": "",
        "bg_color": None,
        "is_subscription": True,
        "read_only": True,
        "_subscription_summary": summary,
        "_subscription_calendar_id": subscription_row.get("calendar_id") or "",
        "_gcal_event_id": getattr(event, "id", "") or "",
        "_gcal_status": getattr(event, "status", "") or "",
        "_gcal_updated": getattr(event, "updated_time", "") or "",
    }


def _get_subscription_events(app, start_date_str, end_date_str):
    if not getattr(app, "gcal_sync", None):
        return []
    if (
        not getattr(app.gcal_sync, "is_authenticated", False)
        or getattr(app.gcal_sync, "service", None) is None
    ):
        return []

    primary_calendar_id = ""
    if hasattr(app, "settings"):
        try:
            primary_calendar_id = str(
                app.settings.value("gcal_calendar_id", "primary") or ""
            ).strip()
        except Exception:
            primary_calendar_id = ""

    # calendar 테이블 기반: is_visible=0 → 숨김, 등록된 gcal_id → unified_task 경로 사용(중복 방지)
    _hidden_gcal_ids: set[str] = set()
    _registered_gcal_ids: set[str] = set()
    try:
        from calendar_app.infrastructure.db.calendar_repo import list_calendars as _list_cals

        for _cal in _list_cals(include_inactive=True):
            _gid = str(_cal.get("gcal_calendar_id") or "").strip()
            if not _gid:
                continue
            if not bool(_cal.get("is_visible", 1)):
                _hidden_gcal_ids.add(_gid)
            # calendar 테이블에 등록된 gcal 캘린더는 unified_task로 관리 → subscription 경로 제외
            _registered_gcal_ids.add(_gid)
    except Exception:
        pass

    subscriptions = [
        row
        for row in task_repo.list_gcal_subscriptions(include_inactive=False)
        if int(row.get("is_active") or 0) == 1
        and str(row.get("calendar_id") or "").strip() != primary_calendar_id
        and str(row.get("calendar_id") or "").strip() not in _hidden_gcal_ids
        and str(row.get("calendar_id") or "").strip() not in _registered_gcal_ids
    ]
    if not subscriptions:
        return []

    cache_key = (
        start_date_str,
        end_date_str,
        tuple(sorted(row.get("calendar_id") or "" for row in subscriptions)),
    )
    cache = getattr(app, "_gcal_subscription_events_cache", {})
    cached = cache.get(cache_key)
    if cached and (time.time() - cached["ts"]) < 300:
        return list(cached["rows"])

    rows = []
    for subscription in subscriptions:
        events = app.gcal_sync.fetch_events(
            start_date_str,
            end_date_str,
            calendar_id=subscription.get("calendar_id") or "",
        )
        if not events:
            continue
        for index, event in enumerate(events):
            rows.append(_normalize_subscription_event(subscription, event, index))

    cache[cache_key] = {"ts": time.time(), "rows": list(rows)}
    app._gcal_subscription_events_cache = cache
    return rows


def _connect_task_button_signals(app, btn):
    btn.taskStatusChanged.connect(app.handle_task_status_changed)
    btn.taskPriorityChanged.connect(app.handle_task_priority_changed)
    btn.taskDeleted.connect(app.handle_task_deleted)
    btn.taskClicked.connect(app.handle_task_clicked)
    btn.doubleClicked.connect(app.open_modify_task_dialog)
    btn.colorAutoAssignRequested.connect(app.handle_color_auto_assign_requested)
    btn.colorChangeRequested.connect(app.handle_color_change_requested)
    btn.colorClearRequested.connect(app.handle_color_clear_requested)
    btn.checklistRequested.connect(app.handle_checklist_requested)
    btn.alarmClearRequested.connect(app.handle_alarm_clear_requested)
    btn.taskRenameRequested.connect(app.handle_task_rename_requested)
    btn.taskResized.connect(app.handle_task_resized)


def _format_task_period_text(task_row):
    start_date, end_date = _task_date_range(task_row)
    if not start_date:
        return ""
    if start_date == end_date:
        return start_date.toString("yyyy.MM.dd")
    return f"{start_date.toString('yyyy.MM.dd')} ~ {end_date.toString('yyyy.MM.dd')}"


def _tooltip_html_text(value):
    cleaned = _tooltip_clean_text(value)
    if not cleaned:
        return ""
    return _html_mod.escape(cleaned).replace("\n", "<br>")


def _tooltip_time_range(task_row):
    start_raw = str(task_row.get("deadline") or "").strip()
    end_raw = str(task_row.get("end_date") or "").strip()

    def _extract_hhmm(raw):
        parts = raw.split()
        if len(parts) < 2:
            return ""
        hhmm = parts[1][:5]
        return hhmm if len(hhmm) == 5 else ""

    start_hhmm = _extract_hhmm(start_raw)
    end_hhmm = _extract_hhmm(end_raw)

    if start_hhmm and end_hhmm and start_hhmm != end_hhmm:
        return f"{start_hhmm} - {end_hhmm}"
    return start_hhmm or end_hhmm


def _build_tooltip_rows(rows):
    pal = _ui_palette()
    if not rows:
        return ""

    html_rows = []
    for label, value, extra_style in rows:
        if not value:
            continue
        label_style = (
            "width:74px; min-width:74px; padding:0 8px 2px 0; "
            f"vertical-align:top; color:{pal['text_secondary']}; white-space:nowrap;"
        )
        value_style = f"padding:0 0 2px 0; vertical-align:top; color:{pal['text_primary']};"
        if extra_style:
            label_style += extra_style
            value_style += extra_style
        html_rows.append(
            f"<tr><td style='{label_style}'>{label}</td><td style='{value_style}'>{value}</td></tr>"
        )
    if not html_rows:
        return ""
    return (
        "<table cellspacing='0' cellpadding='0' style='margin-top:5px; border-collapse:collapse;'>"
        + "".join(html_rows)
        + "</table>"
    )


_ICON_TIME = "🕒"
_ICON_LOCATION = "📍"
_ICON_ASSIGNEE = "👤"
_ICON_DESC = "📝"


def _task_span_days(task_row):
    start_date, end_date = _task_date_range(task_row)
    if not start_date or not end_date:
        return 1
    return max(1, start_date.daysTo(end_date) + 1)


def _theme_harmonized_color(theme_hex, seed_value, tokens=None):
    """Generate a deterministic, theme-harmonized accent color for multiday bars."""
    from PyQt6.QtGui import QColor

    base = QColor(theme_hex)
    if not base.isValid():
        base = QColor(_calendar_default_accent(tokens=tokens))

    # Deterministic "random" hue shifts around theme color.
    shifts = [-42, -30, -20, -10, 8, 18, 28, 40, 52]
    idx = abs(int(seed_value)) % len(shifts)
    hue_shift = shifts[idx]

    h, s, v, _ = base.getHsvF()
    if h < 0:
        h = 0.58  # fallback blue-ish hue
    h = (h + (hue_shift / 360.0)) % 1.0
    s = min(1.0, max(0.42, s + 0.08))
    v = min(1.0, max(0.66, v + 0.04))
    return QColor.fromHsvF(h, s, v).name()


def _build_multiday_tooltip_html(task_row, theme_color):
    title = _tooltip_clean_text(task_row.get("name")) or t("common.no_title")
    period_text = _format_task_period_text(task_row)
    location = _tooltip_html_text(task_row.get("location"))
    assignee = _tooltip_html_text(task_row.get("assignee"))
    memo_text = clean_calendar_description(
        task_row.get("memo") or task_row.get("description"),
        source_calendar_id=task_row.get("gcal_source_calendar_id")
        or task_row.get("_subscription_calendar_id"),
        sync_mode=task_row.get("gcal_sync_mode"),
    )
    memo = _tooltip_html_text(memo_text)
    source = _tooltip_html_text(_subscription_source_text(task_row))

    prio_icon = priority_icon(task_row.get("priority")) if task_row.get("priority") else ""
    title_text = f"{prio_icon} {title}" if prio_icon else title
    title_html = _html_mod.escape(title_text)
    detail_rows = _build_tooltip_rows(
        [
            (
                f"{_ICON_TIME} {t('tooltip.label_period', '기간')}",
                _html_mod.escape(period_text),
                "",
            ),
            (f"\U0001f4e1 {t('tooltip.label_source', '출처')}", source, ""),
            (f"{_ICON_LOCATION} {t('tooltip.label_location', '장소')}", location, ""),
            (f"{_ICON_ASSIGNEE} {t('tooltip.label_assignee', '담당')}", assignee, ""),
            (f"{_ICON_DESC} {t('tooltip.label_description', '설명')}", memo, "line-height:1.3;"),
        ]
    )
    pal = _ui_palette()
    return f"<div style='text-align:left; color:{pal['text_primary']};'><div style='font-size:{_fpt()}; margin-bottom:1px;'><b style='color:{theme_color};'>{title_html}</b></div>{detail_rows}</div>"


def _build_single_task_tooltip_html(task_row, theme_color):
    """Build rich hover tooltip HTML for single-day events."""
    title = _tooltip_clean_text(task_row.get("name")) or t("common.no_title")
    time_hint = _tooltip_time_range(task_row)
    location = _tooltip_html_text(task_row.get("location"))
    assignee = _tooltip_html_text(task_row.get("assignee"))
    memo_text = clean_calendar_description(
        task_row.get("memo") or task_row.get("description"),
        source_calendar_id=task_row.get("gcal_source_calendar_id")
        or task_row.get("_subscription_calendar_id"),
        sync_mode=task_row.get("gcal_sync_mode"),
    )
    memo = _tooltip_html_text(memo_text)
    source = _tooltip_html_text(_subscription_source_text(task_row))

    prio_icon = priority_icon(task_row.get("priority")) if task_row.get("priority") else ""
    title_text = f"{prio_icon} {title}" if prio_icon else title
    title_html = _html_mod.escape(title_text)
    if memo and len(_tooltip_clean_text(memo_text)) > 120:
        memo = _html_mod.escape(_tooltip_clean_text(memo_text)[:120] + "...").replace("\n", "<br>")
    detail_rows = _build_tooltip_rows(
        [
            (f"{_ICON_TIME} {t('tooltip.label_time', '시간')}", _html_mod.escape(time_hint), ""),
            (f"\U0001f4e1 {t('tooltip.label_source', '출처')}", source, ""),
            (f"{_ICON_LOCATION} {t('tooltip.label_location', '장소')}", location, ""),
            (f"{_ICON_ASSIGNEE} {t('tooltip.label_assignee', '담당')}", assignee, ""),
            (f"{_ICON_DESC} {t('tooltip.label_description', '설명')}", memo, "line-height:1.3;"),
        ]
    )
    pal = _ui_palette()
    return f"<div style='text-align:left; color:{pal['text_primary']};'><div style='font-size:{_fpt()}; margin-bottom:1px;'><b style='color:{theme_color};'>{title_html}</b></div>{detail_rows}</div>"


def _show_subscription_detail(task_row, parent=None):
    import re as _re

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (
        QApplication,
        QDialog,
        QFrame,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QScrollArea,
        QVBoxLayout,
        QWidget,
    )

    from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
    from calendar_app.presentation.dialogs.dialog_styles import apply_common_dialog_style

    dlg = QDialog(parent)
    apply_dialog_title(dlg, t("subscription.detail_title", "일정 상세 정보"))
    apply_common_dialog_style(dlg, size=(460, 440))
    dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

    root = QVBoxLayout(dlg)
    root.setContentsMargins(20, 16, 20, 16)
    root.setSpacing(0)

    tokens = _resolve_calendar_tokens()
    detail_styles = _subscription_detail_style_bundle(tokens=tokens)

    title = str(task_row.get("name") or t("common.no_title", "(제목 없음)")).strip()
    title_lbl = QLabel(title)
    title_lbl.setWordWrap(True)
    title_lbl.setStyleSheet(detail_styles["title"])
    root.addWidget(title_lbl)

    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(detail_styles["separator"])
    root.addWidget(sep)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setStyleSheet(detail_styles["scroll"])
    inner = QWidget()
    inner.setStyleSheet(detail_styles["inner"])
    form = QVBoxLayout(inner)
    form.setContentsMargins(0, 0, 0, 0)
    form.setSpacing(8)

    def _add_row(icon_label, value, copyable=False, muted=False):
        if not value or not str(value).strip():
            return
        row = QHBoxLayout()
        row.setSpacing(10)
        lbl_key = QLabel(icon_label)
        lbl_key.setStyleSheet(detail_styles["key_label"])
        lbl_key.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        val_text = str(value).strip()
        lbl_val = QLabel(val_text)
        lbl_val.setWordWrap(True)
        lbl_val.setStyleSheet(detail_styles["value_muted" if muted else "value"])
        lbl_val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(lbl_key)
        row.addWidget(lbl_val, 1)
        if copyable:
            copy_btn = QPushButton(t("common.copy", "복사"))
            copy_btn.setObjectName("ghostBtn")
            copy_btn.setFixedSize(44, 22)
            copy_btn.setStyleSheet(detail_styles["copy_btn"])
            copy_btn.clicked.connect(lambda *_, v=val_text: QApplication.clipboard().setText(v))
            row.addWidget(copy_btn)
        form.addLayout(row)

    def _add_divider():
        d = QFrame()
        d.setFrameShape(QFrame.Shape.HLine)
        d.setStyleSheet(detail_styles["divider"])
        form.addWidget(d)

    def _fmt_datetime(raw):
        if not raw:
            return ""
        raw = raw.strip()
        if _re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$", raw):
            return raw.replace("-", ".")
        m = _re.match(r"^([0-9]{4}-[0-9]{2}-[0-9]{2})T([0-9]{2}:[0-9]{2})(?::[0-9]{2})?(.*)$", raw)
        if m:
            date_part = m.group(1).replace("-", ".")
            time_part = m.group(2)
            tz_part = m.group(3)
            tz_str = ""
            tz_m = _re.match(r"([+-][0-9]{2}:[0-9]{2})", tz_part)
            if tz_m:
                tz_str = f" (UTC{tz_m.group(1)})"
            elif "Z" in tz_part:
                tz_str = " (UTC)"
            return f"{date_part} {time_part}{tz_str}"
        return raw

    all_day = bool(task_row.get("all_day"))
    start_raw = str(task_row.get("_start_raw") or task_row.get("deadline") or "").strip()
    end_raw = str(task_row.get("_end_raw") or task_row.get("end_date") or "").strip()

    if all_day:
        start_disp = _fmt_datetime(start_raw[:10] if start_raw else "")
        end_disp = _fmt_datetime(end_raw[:10] if end_raw else "")
        all_day_label = t("subscription.all_day", "(종일)")
        if start_disp and end_disp and start_disp != end_disp:
            time_str = f"{start_disp} ~ {end_disp}  {all_day_label}"
        else:
            time_str = f"{start_disp or end_disp}  {all_day_label}"
    else:
        start_disp = _fmt_datetime(start_raw)
        end_disp = _fmt_datetime(end_raw)
        if start_disp == end_disp or not end_disp:
            time_str = start_disp
        else:
            sd = start_raw[:10]
            ed = end_raw[:10]
            if sd and ed and sd == ed:
                end_time_only = end_disp.split(" ")[1] if " " in end_disp else end_disp
                time_str = f"{start_disp} ~ {end_time_only}"
            else:
                time_str = f"{start_disp} ~ {end_disp}"

    _lbl = _ICON_TIME + chr(32) + t("tooltip.label_period", "기간")
    _add_row(_lbl, time_str)

    source = _subscription_source_text(task_row)
    _lbl = "\U0001f4e1" + chr(32) + t("tooltip.label_calendar", "캘린더")
    _add_row(_lbl, source)

    location = str(task_row.get("location") or "").strip()
    _lbl = _ICON_LOCATION + chr(32) + t("tooltip.label_location", "장소")
    _add_row(_lbl, location)

    assignee = str(task_row.get("assignee") or "").strip()
    if assignee:
        _lbl = _ICON_ASSIGNEE + chr(32) + t("tooltip.label_assignee", "담당")
        _add_row(_lbl, assignee)

    desc = clean_calendar_description(
        task_row.get("description") or task_row.get("memo"),
        source_calendar_id=task_row.get("_subscription_calendar_id")
        or task_row.get("gcal_source_calendar_id"),
        sync_mode=task_row.get("gcal_sync_mode"),
    )
    _lbl = _ICON_DESC + chr(32) + t("tooltip.label_description", "설명")
    _add_row(_lbl, desc)

    status_raw = str(task_row.get("_gcal_status") or "").strip()
    _STATUS_LABEL = {
        "confirmed": t("subscription.status_confirmed", "확정"),
        "tentative": t("subscription.status_tentative", "미정"),
        "cancelled": t("subscription.status_cancelled", "취소됨"),
    }
    if status_raw and status_raw != "confirmed":
        _lbl = chr(0x1F516) + chr(32) + t("subscription.label_status", "상태")
        _add_row(_lbl, _STATUS_LABEL.get(status_raw, status_raw))

    updated_raw = str(task_row.get("_gcal_updated") or "").strip()
    if updated_raw:
        _add_divider()
        _lbl = chr(0x1F504) + chr(32) + t("subscription.label_updated", "수정일")
        _add_row(_lbl, _fmt_datetime(updated_raw), muted=True)

    event_id = str(task_row.get("_gcal_event_id") or "").strip()
    if event_id:
        _lbl = chr(0x1F511) + chr(32) + t("subscription.label_event_id", "이벤트 ID")
        _add_row(_lbl, event_id, copyable=True, muted=True)

    form.addStretch(1)
    scroll.setWidget(inner)
    root.addWidget(scroll, 1)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(10)

    # Copy button
    copy_btn = QPushButton(t("subscription.action_copy", "내 일정으로 복사"))
    copy_btn.setObjectName("SecondaryBtn")  # Secondary accent color
    copy_btn.setMinimumWidth(130)
    copy_btn.setFixedHeight(32)

    def _do_copy():
        if hasattr(parent, "copy_subscription_to_local"):
            parent.copy_subscription_to_local(task_row)
            dlg.accept()

    copy_btn.clicked.connect(_do_copy)
    btn_row.addWidget(copy_btn)

    btn_row.addStretch()

    # Close button
    close_btn = QPushButton(t("common.close", "닫기"))
    close_btn.setObjectName("PrimaryBtn")
    close_btn.setFixedWidth(80)
    close_btn.setFixedHeight(32)
    close_btn.clicked.connect(dlg.accept)
    btn_row.addWidget(close_btn)

    root.addSpacing(15)
    root.addLayout(btn_row)

    dlg.exec()


def _assign_lane(start_col: int, end_col: int, lane_occupancy: list) -> int:
    """Find the first free lane for [start_col, end_col] and record occupancy.

    ``lane_occupancy`` is a list of lists of (start_col, end_col) tuples,
    one sublist per lane.  A new lane is appended when no existing lane fits.
    Returns the assigned lane index.
    """
    for idx, occ_ranges in enumerate(lane_occupancy):
        conflict = any(
            not (end_col < occ_start or start_col > occ_end) for occ_start, occ_end in occ_ranges
        )
        if not conflict:
            lane_occupancy[idx].append((start_col, end_col))
            return idx
    lane_occupancy.append([(start_col, end_col)])
    return len(lane_occupancy) - 1


def _build_multiday_segments(tasks, visible_dates, cols):
    if not tasks or not visible_dates or cols <= 0:
        return [], {}

    date_info = [
        {"week": i // cols, "col": i % cols, "date": d} for i, d in enumerate(visible_dates)
    ]
    week_segments = {}

    for task_row in tasks:
        start_date, end_date = _task_date_range(task_row)
        if not start_date or not end_date or start_date >= end_date:
            continue

        active_indices = [i for i, d in enumerate(visible_dates) if start_date <= d <= end_date]
        # Even if only one day is visible (e.g., Fri->Sun with weekends hidden),
        # keep a segment so the multiday task does not disappear.
        if len(active_indices) < 1:
            continue

        seg_list = []
        segment_start_idx = active_indices[0]
        prev_idx = active_indices[0]
        prev_week = date_info[prev_idx]["week"]

        for idx in active_indices[1:]:
            curr_week = date_info[idx]["week"]
            if idx != prev_idx + 1 or curr_week != prev_week:
                start_info = date_info[segment_start_idx]
                end_info = date_info[prev_idx]
                seg_list.append(
                    {
                        "task": task_row,
                        "week": start_info["week"],
                        "start_col": start_info["col"],
                        "end_col": end_info["col"],
                        "segment_start": start_info["date"] == start_date,
                        "segment_end": end_info["date"] == end_date,
                    }
                )
                segment_start_idx = idx
            prev_idx = idx
            prev_week = curr_week

        start_info = date_info[segment_start_idx]
        end_info = date_info[prev_idx]
        seg_list.append(
            {
                "task": task_row,
                "week": start_info["week"],
                "start_col": start_info["col"],
                "end_col": end_info["col"],
                "segment_start": start_info["date"] == start_date,
                "segment_end": end_info["date"] == end_date,
            }
        )

        for seg in seg_list:
            week_segments.setdefault(seg["week"], []).append(seg)

    if not week_segments:
        return [], {}

    placed_segments = []
    week_lane_counts = {}

    for week, segments in week_segments.items():
        # Keep placement deterministic within the week.
        sorted_segments = sorted(
            segments,
            key=lambda seg: (
                seg["start_col"],
                -(seg["end_col"] - seg["start_col"] + 1),
                str(seg["task"].get("id", id(seg["task"]))),
            ),
        )

        lane_occupancy = []  # list[list[(start_col, end_col)]]
        for seg in sorted_segments:
            seg["lane"] = _assign_lane(seg["start_col"], seg["end_col"], lane_occupancy)
            placed_segments.append(seg)

        week_lane_counts[week] = len(lane_occupancy)

    return placed_segments, week_lane_counts


def render_calendar(app):
    raw_mode = str(getattr(app, "view_mode_state", "") or "")

    # Normalization & Backward compatibility mapping
    mode_map = {
        "월간보기": "monthly",
        "주간보기": "weekly_1",
        "주간보기(1주)": "weekly_1",
        "주간보기(2주)": "weekly_2",
        "주간보기(3주)": "weekly_3",
    }

    normalized_mode = mode_map.get(raw_mode, raw_mode)
    if normalized_mode not in {"monthly", "weekly_1", "weekly_2", "weekly_3"}:
        normalized_mode = "monthly"

    if app.view_mode_state != normalized_mode:
        app.view_mode_state = normalized_mode

    app.reset_frame(app.center_frame)
    new_layout = QVBoxLayout()
    # center_frame은 반드시 0 마진 — resizeEvent 체인 cascade 방지
    new_layout.setContentsMargins(0, 0, 0, 0)
    app.center_frame.setLayout(new_layout)

    tokens = _ui_tokens(getattr(app, "settings", None))
    shape = _shape_tokens(getattr(app, "settings", None))
    toolbar_styles = _calendar_toolbar_style_bundle(tokens=tokens, shape=shape)
    _icon_color = tokens.get("text_primary", "#f4f7fb")

    frame = _CalendarSurfaceFrame(app)
    frame.setObjectName("calendar_surface")
    frame.setStyleSheet(_calendar_surface_style(tokens=tokens, shape=shape))

    inner_v = QVBoxLayout()
    view_mode = app.view_mode_state
    search_query = (
        getattr(app, "search_edit", None).text() if getattr(app, "search_edit", None) else ""
    )
    is_week_mode = view_mode.startswith("weekly")
    is_month_mode = view_mode == "monthly"

    # 캘린더전용 툴바 (내비게이션+ 날짜 표시 + 보기 모드)
    cal_toolbar = QHBoxLayout()
    cal_toolbar.setSpacing(8)
    cal_toolbar.setContentsMargins(4, 2, 4, 2)

    _tc = get_theme_color(app.settings)

    # 캘린더 색상 캐시 로딩 (calendar_id → color)
    global _calendar_meta_cache
    if _calendar_meta_cache is None:
        try:
            from calendar_app.infrastructure.db.calendar_repo import list_calendars as _lc

            _calendar_meta_cache = {c["id"]: c.get("color") for c in _lc(include_inactive=True)}
        except Exception:
            _calendar_meta_cache = {}

    # 툴바 버튼 기본 색상
    # 드롭다운 메뉴
    # 선택 상태 레이블

    today_btn_style = toolbar_styles["today_btn"]
    nav_btn_style = toolbar_styles["nav_btn"]
    menu_btn_style = toolbar_styles["menu_btn"]
    icon_btn_style = toolbar_styles["icon_btn"]
    dropdown_menu_style = toolbar_styles["dropdown_menu"]

    today_btn = QPushButton(t("calendar.today"))
    today_btn.setStyleSheet(today_btn_style)
    today_btn.setMinimumWidth(58)
    today_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    today_btn.clicked.connect(app.jump_to_today)

    prev_btn = QPushButton()
    prev_btn.setIcon(_ic(ICON.NAV_PREV, color=_icon_color))
    prev_btn.setIconSize(QSize(14, 14))
    prev_btn.setStyleSheet(nav_btn_style)
    prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    prev_btn.clicked.connect(app.prev_day)

    next_btn = QPushButton()
    next_btn.setIcon(_ic(ICON.NAV_NEXT, color=_icon_color))
    next_btn.setIconSize(QSize(14, 14))
    next_btn.setStyleSheet(nav_btn_style)
    next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    next_btn.clicked.connect(app.next_day)

    # ?쒖떆 ?뺤떇 ?좏깮 (?붽컙: '2026.03', 二쇨컙: '2026.03.01 (??')
    if is_month_mode:
        date_text = app.current_date.toString("yyyy.MM")
    else:
        day_names = t("calendar.weekdays")
        target_day_name = day_names[app.current_date.dayOfWeek() - 1]
        date_text = app.current_date.toString("yyyy.MM.dd") + f" ({target_day_name})"

    date_lbl = QLabel(f"  {date_text}")
    date_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
    date_lbl.setStyleSheet(toolbar_styles["date_label"])

    # Determine display label for the current view mode
    display_name_map = {
        "monthly": t("view_mode.monthly"),
        "weekly_1": t("view_mode.weekly_1"),
        "weekly_2": t("view_mode.weekly_2"),
        "weekly_3": t("view_mode.weekly_3"),
    }
    view_btn_label = display_name_map.get(view_mode, view_mode)

    view_btn = QPushButton(f"  {view_btn_label}")
    view_btn.setIcon(_ic(ICON.VIEW_CALENDAR))
    view_btn.setStyleSheet(menu_btn_style)
    view_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    view_menu = QMenu(app)
    view_menu.setStyleSheet(dropdown_menu_style)
    mode_list = [
        ("weekly_1", t("view_mode.weekly_1")),
        ("weekly_2", t("view_mode.weekly_2")),
        ("weekly_3", t("view_mode.weekly_3")),
        ("monthly", t("view_mode.monthly")),
    ]
    for internal_mode, display_name in mode_list:
        act = QAction(display_name, app, checkable=True)
        act.setChecked(internal_mode == view_mode)

        def _make_view_handler(mode, name, a):
            def _handler(checked):
                if checked:
                    view_btn.setText(f"  {name}")
                    app.change_view_mode(mode)
                    for other in view_menu.actions():
                        if other is not a:
                            other.setChecked(False)

            return _handler

        act.toggled.connect(_make_view_handler(internal_mode, display_name, act))
        view_menu.addAction(act)
    view_btn.setMenu(view_menu)

    opt_btn = QPushButton(t("calendar.options"))
    opt_btn.setStyleSheet(menu_btn_style)
    opt_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    opt_menu = QMenu(app)
    opt_menu.setStyleSheet(dropdown_menu_style)

    wknd_action = QAction(t("calendar.opt_weekend"), app, checkable=True)
    wknd_action.setChecked(app.cal_show_weekends)
    wknd_action.toggled.connect(app.toggle_weekends)

    show_month_action = QAction(t("calendar.opt_month"), app, checkable=True)
    show_month_action.setChecked(getattr(app, "cal_show_month", False))
    show_month_action.toggled.connect(app.toggle_show_month)

    show_weekday_action = QAction(t("calendar.opt_weekday"), app, checkable=True)
    show_weekday_action.setChecked(getattr(app, "cal_show_weekday", False))
    show_weekday_action.toggled.connect(app.toggle_show_weekday)

    opt_menu.addAction(wknd_action)
    opt_menu.addSeparator()
    opt_menu.addAction(show_month_action)
    opt_menu.addAction(show_weekday_action)

    # ?? 캘린더蹂닿린/?④린湲??좉? ?????????????????????????????????????????
    def _rebuild_calendar_visibility_actions():
        for act in list(opt_menu.actions()):
            if getattr(act, "_cal_vis_action", False):
                opt_menu.removeAction(act)
        try:
            from calendar_app.infrastructure.db.calendar_repo import (
                is_calendar_row_read_only,
                list_calendars,
                set_calendar_visible,
            )

            calendars = list_calendars(include_inactive=True)
        except Exception:
            return
        if not calendars:
            return

        sep_cal = opt_menu.addSeparator()
        sep_cal._cal_vis_action = True

        def _make_toggle(cal_id):
            def _fn(checked):
                try:
                    set_calendar_visible(cal_id, checked)
                    invalidate_calendar_meta_cache()
                    from calendar_app.presentation.panels.side_panel_renderer import (
                        invalidate_panel_calendar_cache,
                    )

                    invalidate_panel_calendar_cache()
                    if hasattr(app, "schedule_panel_refresh"):
                        app.schedule_panel_refresh(center=True)
                except Exception:
                    pass

            return _fn

        _TYPE_ICON = {
            "gcal": ICON.GCAL,
            "ics": ICON.LINK,
            "local": ICON.ALL_SCHEDULES,
            "shared": ICON.ALL_SCHEDULES,
        }
        _READ_ONLY_ICON = ICON.LOCK
        for cal in calendars:
            is_read_only = is_calendar_row_read_only(cal)
            type_icon = (
                _READ_ONLY_ICON
                if is_read_only
                else _TYPE_ICON.get(cal.get("type", "local"), ICON.ALL_SCHEDULES)
            )

            # Create a professional icon using the type icon and the calendar's color
            cal_color = cal.get("color")
            # If read-only, we could potentially stack icons, but for now we prioritize visibility
            final_icon = _ic(type_icon, color=cal_color)

            act = QAction(cal["name"], app, checkable=True)
            act.setIcon(final_icon)
            act.setChecked(bool(cal.get("is_visible", 1)))
            if is_read_only:
                act.setToolTip(t("dialog.task.calendar_read_only", "Read-only calendar"))

            act._cal_vis_action = True
            act.toggled.connect(_make_toggle(cal["id"]))
            opt_menu.addAction(act)

        sep2 = opt_menu.addSeparator()
        sep2._cal_vis_action = True
        manage_act = QAction(t("menu.calendar_manage", "캘린더 관리..."), app)
        manage_act.setIcon(_ic(ICON.CHECKLIST))
        manage_act._cal_vis_action = True

        def _open_manage():
            if hasattr(app, "open_gcal_settings_dialog"):
                app.open_gcal_settings_dialog(initial_tab="calendar")

        manage_act.triggered.connect(_open_manage)
        opt_menu.addAction(manage_act)

    _rebuild_calendar_visibility_actions()
    opt_menu.aboutToShow.connect(_rebuild_calendar_visibility_actions)
    opt_btn.setMenu(opt_menu)

    add_btn = QPushButton()
    add_btn.setIcon(_ic(ICON.ADD, color=_icon_color))
    add_btn.setIconSize(QSize(15, 15))
    add_btn.setToolTip(t("calendar.add_hint"))
    add_btn.setStyleSheet(icon_btn_style)
    add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    add_btn.clicked.connect(app.open_task_dialog)

    sync_btn = QPushButton()
    sync_btn.setIcon(_ic(ICON.SYNC, color=_icon_color))
    sync_btn.setIconSize(QSize(15, 15))
    sync_btn.setToolTip(t("calendar.sync_hint"))
    sync_btn.setStyleSheet(icon_btn_style)
    sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    sync_btn.clicked.connect(app.sync_google_calendar)

    # 선택 상태 ?쒖떆 ?쇰꺼 (캘린더?대컮 ?곗륫 諛곗튂)
    from PyQt6.QtGui import QFont as _QFont
    from PyQt6.QtWidgets import QLabel as _QLabel

    app.selection_status_lbl = _QLabel(t("calendar.selection_hint"))
    app.selection_status_lbl.setAlignment(
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
    )
    _lbl_font = _QFont("Segoe UI")
    _lbl_font.setPointSize(max(6, QApplication.instance().font().pointSize() - 1))
    app.selection_status_lbl.setFont(_lbl_font)
    app.selection_status_lbl.setStyleSheet(toolbar_styles["selection_label"])
    app.selection_status_lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    cal_toolbar.addWidget(today_btn)
    cal_toolbar.addWidget(prev_btn)
    cal_toolbar.addWidget(next_btn)
    cal_toolbar.addWidget(date_lbl)

    cal_toolbar.addStretch(1)  # 以묒븰 ?щ갚 ?뺣낫
    cal_toolbar.addWidget(app.selection_status_lbl)  # ?곗륫 ?덈궡 臾멸뎄 諛곗튂
    cal_toolbar.addSpacing(10)

    cal_toolbar.addWidget(add_btn)
    cal_toolbar.addWidget(sync_btn)
    cal_toolbar.addSpacing(10)

    cal_toolbar.addWidget(opt_btn)
    cal_toolbar.addWidget(view_btn)

    cal_toolbar_content = QWidget()
    cal_toolbar_vbox = QVBoxLayout(cal_toolbar_content)
    cal_toolbar_vbox.setContentsMargins(6, 4, 6, 2)
    cal_toolbar_vbox.setSpacing(0)
    cal_toolbar_vbox.addLayout(cal_toolbar)

    cal_toolbar_widget = _CalToolbarWidget()
    host_layout = QVBoxLayout(cal_toolbar_widget)
    host_layout.setContentsMargins(0, 0, 0, 0)
    host_layout.setSpacing(0)
    host_layout.addWidget(cal_toolbar_content)
    cal_toolbar_widget.set_content_widget(cal_toolbar_content)
    cal_toolbar_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    cal_toolbar_widget.setMinimumWidth(100)
    # Explicitly delete the previous title bar widget before replacing it.
    # If the old widget is still alive when setTitleBarWidget is called, Qt may
    # render both simultaneously, producing a duplicate toolbar row.
    # Skip when the dock is float-wrapped — FloatingDockBehavior manages the
    # wrapper layout and replacing titleBarWidget on a wrapped floating dock
    # corrupts the layout and produces duplicate rows.
    from calendar_app.presentation.main_window.dock_sections.floating_dock_behavior import (
        is_dock_float_wrapped,
    )

    app.calendar_toolbar_widget = cal_toolbar_widget
    if not is_dock_float_wrapped(app.center_dock):
        old_tb = app.center_dock.titleBarWidget()
        if old_tb is not None and old_tb is not cal_toolbar_widget:
            app.center_dock.setTitleBarWidget(None)
            old_tb.deleteLater()
        app.center_dock.setTitleBarWidget(cal_toolbar_widget)
    cal_toolbar_widget.bind_dock(app.center_dock)
    if hasattr(app, "_calendar_toolbar_visible_setting"):
        cal_toolbar_widget.set_toolbar_expanded(app._calendar_toolbar_visible_setting())

    # 珥덇린 ?곹깭 諛섏쁺
    if hasattr(app, "update_task_selection_status"):
        app.update_task_selection_status()

    days_layout = QVBoxLayout()
    days_layout.setSpacing(6)
    toolbar_visible = True
    if hasattr(app, "_calendar_toolbar_visible_setting"):
        toolbar_visible = app._calendar_toolbar_visible_setting()
    days_layout.setContentsMargins(6, 4 if toolbar_visible else 0, 6, 6)

    is_grid_view = is_week_mode or is_month_mode
    cols = 7 if app.cal_show_weekends else 5

    dates_to_render = []
    if is_month_mode:
        dates_to_render = _build_month_dates(
            app.current_date,
            show_weekends=bool(getattr(app, "cal_show_weekends", True)),
            start_monday=bool(getattr(app, "cal_start_monday", True)),
        )

    elif is_week_mode:
        days_offset = app.current_date.dayOfWeek() - 1
        monday = app.current_date.addDays(-days_offset)

        span = 7
        if "weekly_1" in view_mode:
            span = 7
        elif "weekly_2" in view_mode:
            span = 14
        elif "weekly_3" in view_mode:
            monday = monday.addDays(-7)
            span = 21

        for i in range(span):
            idx_date = monday.addDays(i)
            if not app.cal_show_weekends and idx_date.dayOfWeek() >= 6:
                continue
            dates_to_render.append(idx_date)
    else:
        dates_to_render.append(app.current_date)

    app._calendar_cells_by_date = {}
    app._drag_range_preview_cells = []

    if not is_grid_view:
        # ?쇨컙 紐⑤뱶 ??湲고? ?덈퉬 泥섎━
        pass
    else:
        weeks = []
        current_week = []
        for d in dates_to_render:
            current_week.append(d)
            if len(current_week) == cols:
                weeks.append(current_week)
                current_week = []
        if current_week:
            weeks.append(current_week)

        if not dates_to_render:
            inner_v.addLayout(days_layout, 1)
            frame.setLayout(inner_v)
            app._multiday_bridge_overlay = None
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setStyleSheet(_calendar_scroll_style())
            scroll.setWidget(frame)
            new_layout.addWidget(scroll)
            return

        range_start = dates_to_render[0].toString("yyyy-MM-dd")
        range_end = dates_to_render[-1].toString("yyyy-MM-dd")
        gcal_enabled = True
        try:
            if hasattr(app, "settings"):
                raw_enabled = app.settings.value("gcal_enabled", None)
                gcal_enabled = is_gcal_enabled(app.settings)
                logger.debug(
                    "render range=%s~%s gcal=%s (raw=%s)",
                    range_start,
                    range_end,
                    gcal_enabled,
                    raw_enabled,
                )
        except Exception:
            gcal_enabled = True

        all_tasks = search_repo.get_schedule_tasks_overlapping_range_with_progress(
            range_start,
            range_end,
            hide_gcal_items=not gcal_enabled,
        )
        app._latest_calendar_range_data = {
            "range_start": range_start,
            "range_end": range_end,
            "rows": list(all_tasks or []),
        }
        logger.debug("fetched %d tasks from repo", len(all_tasks))
        for task in all_tasks:
            if str(task.get("calendar_id") or "").startswith("ics::"):
                task["is_subscription"] = True
                task["read_only"] = True

        subscription_tasks = (
            _get_subscription_events(app, range_start, range_end) if gcal_enabled else []
        )

        # Deduplicate: synced Google events are in all_tasks, direct fetch in subscription_tasks.
        # Prefer synced items (all_tasks) as they might have local edits/priorities.
        seen_gcal_ids = set()
        seen_content_keys = set()  # (name, start_date)

        for tk in all_tasks:
            # 1. Track IDs
            gid = tk.get("gcal_event_id") or tk.get("_gcal_event_id")
            if gid:
                seen_gcal_ids.add(str(gid).strip())

            # 2. Track Content (Name + StartDate) as fallback
            name = (tk.get("name") or "").strip()
            s_date, _ = _task_date_range(tk)
            if name and s_date:
                seen_content_keys.add((name, s_date.toString("yyyy-MM-dd")))

        unique_subs = []
        for sk in subscription_tasks:
            # 1. ID check
            sgid = sk.get("gcal_event_id") or sk.get("_gcal_event_id")
            if sgid and str(sgid).strip() in seen_gcal_ids:
                continue

            # 2. Content check (Fallback for holidays or inconsistent IDs)
            s_name = (sk.get("name") or "").strip()
            ss_date, _ = _task_date_range(sk)
            if s_name and ss_date:
                ckey = (s_name, ss_date.toString("yyyy-MM-dd"))
                if ckey in seen_content_keys:
                    continue

            unique_subs.append(sk)

        filtered_all = [
            task for task in [*all_tasks, *unique_subs] if _task_matches_search(task, search_query)
        ]
        logger.debug("filtered_all count: %d (deduplicated)", len(filtered_all))

        # When weekends are hidden, surface how many events are currently hidden
        # so users can quickly understand why Saturday/Sunday events are missing.
        hidden_weekend_events = 0
        if not app.cal_show_weekends:
            visible_range_start = QDate.fromString(range_start, "yyyy-MM-dd")
            visible_range_end = QDate.fromString(range_end, "yyyy-MM-dd")
            if visible_range_start.isValid() and visible_range_end.isValid():
                seen_hidden = set()
                for task in filtered_all:
                    start_qdate, end_qdate = _task_date_range(task)
                    if not start_qdate:
                        continue
                    if end_qdate < visible_range_start or start_qdate > visible_range_end:
                        continue
                    day = start_qdate if start_qdate > visible_range_start else visible_range_start
                    last_day = end_qdate if end_qdate < visible_range_end else visible_range_end
                    while day <= last_day:
                        if day.dayOfWeek() >= 6:
                            seen_hidden.add(str(task.get("id")))
                            break
                        day = day.addDays(1)
                hidden_weekend_events = len(seen_hidden)

        if hidden_weekend_events > 0:
            base_weekend_label = t("calendar.opt_weekend", "Show Weekends")
            wknd_action.setText(
                t(
                    "calendar.opt_weekend_hidden",
                    "{label} ({count} hidden)",
                    label=base_weekend_label,
                    count=hidden_weekend_events,
                )
            )
            opt_btn.setText(
                t(
                    "calendar.options_with_hidden",
                    "{label} ({count})",
                    label=t("calendar.options", "Options"),
                    count=hidden_weekend_events,
                )
            )
            opt_btn.setToolTip(
                t(
                    "calendar.opt_weekend_hidden_hint",
                    "{count} weekend event(s) are hidden. Enable 'Show Weekends' in Options.",
                    count=hidden_weekend_events,
                )
            )
        else:
            wknd_action.setText(t("calendar.opt_weekend"))
            opt_btn.setText(t("calendar.options"))
            opt_btn.setToolTip("")

        week_count = max(1, len(weeks))
        center_height = max(
            0,
            getattr(app, "center_frame", QWidget()).height() if hasattr(app, "center_frame") else 0,
        )
        days_spacing = days_layout.spacing()
        day_margins = days_layout.contentsMargins()
        chrome_height = 28
        if center_height > 0:
            available_days_height = max(
                120,
                center_height
                - day_margins.top()
                - day_margins.bottom()
                - (days_spacing * max(0, week_count - 1)),
            )
            week_height_hint = max(80, available_days_height // week_count)
        else:
            week_height_hint = 140 if is_month_mode else 220
        event_slot_height = 24
        total_event_slots = max(
            1, (max(0, week_height_hint - chrome_height - 8)) // event_slot_height
        )

        for _week_idx, week_dates in enumerate(weeks):
            week_start_qdate = week_dates[0]
            week_end_qdate = week_dates[-1]

            # 二??⑥쐞 而⑦뀒?대꼫 (洹몃━???덉씠?꾩썐)
            week_widget = QWidget()
            week_widget.setObjectName("week_grid_container")
            week_widget.setMinimumHeight(0)
            week_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
            week_grid = QGridLayout(week_widget)
            week_grid.setSpacing(0)
            week_grid.setContentsMargins(0, 0, 0, 0)

            # 오늘 날짜 — 루프 밖에서 한 번만 계산 (is_today 판정은 항상 실제 오늘 기준)
            today_qdate = QDate.currentDate()
            day_names = t("calendar.weekdays")
            show_month = getattr(app, "cal_show_month", False)
            show_weekday = getattr(app, "cal_show_weekday", False)

            for col_idx, target_date in enumerate(week_dates):
                day_str = target_date.toString("M/d") if show_month else target_date.toString("d")
                if show_weekday:
                    day_name = day_names[target_date.dayOfWeek() - 1]
                    day_str = f"{day_str} ({day_name})"

                is_today = target_date == today_qdate
                if is_today:
                    day_str = f"★ {day_str}"

                cell_frame = ClickableCell(target_date)
                cell_frame.doubleClicked.connect(app.open_task_dialog)
                cell_frame.clicked.connect(app.handle_cell_click)
                cell_frame.shiftClicked.connect(app.handle_cell_shift_click)
                cell_frame.taskDropped.connect(app.handle_task_dropped)

                cell_frame.setProperty("is_today", is_today)
                cell_frame.setProperty(
                    "is_other_month",
                    is_month_mode and target_date.month() != app.current_date.month(),
                )
                cell_frame.setProperty(
                    "selected_date", getattr(app, "_last_clicked_date", None) == target_date
                )
                cell_frame.setProperty("day_of_week", target_date.dayOfWeek())
                cell_frame.setProperty("drag_range_preview", False)
                cell_frame.setProperty("drag_range_start", False)
                cell_frame.setProperty("drag_range_end", False)
                app._calendar_cells_by_date[target_date.toString("yyyy-MM-dd")] = cell_frame

                # ?대? ?섏쭅 ?덉씠?꾩썐 (諛곌꼍??
                bg_v = QVBoxLayout(cell_frame)
                bg_v.setContentsMargins(0, 0, 4, 0)
                bg_v.setSpacing(0)
                bg_v.setAlignment(Qt.AlignmentFlag.AlignTop)

                # ?좎쭨 ?쇰꺼 (泥?以?怨좎젙)
                day_lbl = QLabel(day_str)
                day_lbl.setObjectName("dayNumLabel")
                day_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                day_lbl.setFixedHeight(24)
                bg_v.addWidget(day_lbl)

                # 諛곌꼍 ????ш쾶 諛곗튂 (Row Span 理쒕???
                # ?ㅼ젣 일정??異붽????뚮쭏??Grid??Row媛 ?섏뼱?섏?留?
                # 諛곌꼍 ?? ??긽 Row 0遺??留됰컮吏源뚯? ?뺤옣?섎룄濡???Row Span??以??
                week_grid.addWidget(cell_frame, 0, col_idx, 999, 1)
                cell_frame.lower()
                week_grid.setColumnStretch(col_idx, 1)

            # 2. ??二쇱감(Week)???랁븳 일정???꾪꽣留?諛??좊떦
            week_multi_tasks = []
            week_single_tasks = {}  # col_idx -> list
            for c in range(cols):
                week_single_tasks[c] = []

            for task in filtered_all:
                s_date, e_date = _task_date_range(task)
                if not s_date:
                    continue

                # ?대떦 二쇱감? 寃뱀튂?붿? 확인
                if e_date < week_start_qdate or s_date > week_end_qdate:
                    continue

                if _is_multi_day_task(task):
                    week_multi_tasks.append(task)
                else:
                    # ?⑥씪 일정??寃쎌슦 ?대뒓 ??Col)?몄? 李얜뒗??
                    try:
                        col_idx = week_dates.index(s_date)
                        week_single_tasks[col_idx].append(task)
                    except ValueError:
                        pass  # 二쇰쭚 ?④? ?깆뿉 ?섑빐 由ъ뒪?몄뿉 ?놁쓣 ???덉쓬

            # 3. ?ㅼ쨷 일정 諛곗튂 怨꾩궛 (Lane ?좊떦)
            # ?곗냽 留됰?媛 寃뱀튂吏 ?딅룄濡?Lane(?????좊떦?쒕떎.
            lanes = []  # list of lists, each sublist contains (start_col, end_col)
            multiday_placements = []  # list of dicts

            # 일정???쒖옉???? 洹몃━怨?湲?테스트?쒖쑝濡??뺣젹?섏뿬 諛곗튂
            sorted_multi = sorted(
                week_multi_tasks,
                key=lambda t: (
                    max(week_start_qdate, _task_date_range(t)[0]),
                    -(
                        min(week_end_qdate, _task_date_range(t)[1]).toJulianDay()
                        - max(week_start_qdate, _task_date_range(t)[0]).toJulianDay()
                    ),
                ),
            )

            for task in sorted_multi:
                s_date, e_date = _task_date_range(task)

                # ?꾩옱 ?쒖떆以묒씤 二쇱쓽 ??Col) ?몃뜳?ㅻ줈 蹂??
                display_s_date = max(s_date, week_start_qdate)
                display_e_date = min(e_date, week_end_qdate)

                try:
                    start_col = week_dates.index(display_s_date)
                except ValueError:
                    # ?쒖옉?쇱씠 ?쒖떆 ????됱씪 ?쒖떆 紐⑤뱶?먯꽌 二쇰쭚 ?????꾨땺寃쎌슦, 媛??媛源뚯슫 ?쒖떆?섎뒗 ?붿씪 李얘린
                    found = False
                    for c_idx, wd in enumerate(week_dates):
                        if wd >= display_s_date:
                            start_col = c_idx
                            found = True
                            break
                    if not found:
                        continue

                try:
                    end_col = week_dates.index(display_e_date)
                except ValueError:
                    found = False
                    for c_idx in reversed(range(len(week_dates))):
                        if week_dates[c_idx] <= display_e_date:
                            end_col = c_idx
                            found = True
                            break
                    if not found:
                        continue

                if start_col > end_col:
                    continue

                # 鍮?Lane 李얘린
                lane_idx = _assign_lane(start_col, end_col, lanes)

                multiday_placements.append(
                    {
                        "task": task,
                        "lane": lane_idx,
                        "start_col": start_col,
                        "end_col": end_col,
                        "is_start": s_date == display_s_date,
                        "is_end": e_date == display_e_date,
                    }
                )

            # 理쒕? Lane ???쒗븳 泥섎━ + ?꾩옱 ? ?믪씠??留욌뒗 ?쒖떆 媛??????諛섏쁺
            static_multiday_limit = 5 if is_month_mode else 15
            hidden_multiday_exists = len(lanes) > min(static_multiday_limit, total_event_slots)
            lane_budget = (
                max(0, total_event_slots - 1) if hidden_multiday_exists else total_event_slots
            )
            max_multiday_lanes = min(static_multiday_limit, lane_budget)
            visible_multiday = [p for p in multiday_placements if p["lane"] < max_multiday_lanes]
            hidden_multiday = [p for p in multiday_placements if p["lane"] >= max_multiday_lanes]

            hidden_counts_by_col = {c: 0 for c in range(cols)}
            for hm in hidden_multiday:
                for c in range(hm["start_col"], hm["end_col"] + 1):
                    hidden_counts_by_col[c] += 1

            # Reserve row 0 for day-number breathing room and start events from row 1.
            week_grid.setRowMinimumHeight(0, 28)
            event_base_row = 1

            def _build_task_button(task_row, label_text, is_multiday, is_origin):
                tid = task_row["id"]
                _tprio = task_row["priority"]
                tcol = task_row.get("bg_color")

                # task 자체 색상 없으면 캘린더 색상을 fallback으로 사용
                if not tcol:
                    cal_id = task_row.get("calendar_id")
                    if not cal_id:
                        src = task_row.get("gcal_source_calendar_id")
                        if src:
                            cal_id = f"gcal::{src}"
                    if cal_id and _calendar_meta_cache:
                        tcol = _calendar_meta_cache.get(cal_id)

                btn = DraggableTaskButton(tid, label_text)
                is_subscription = bool(task_row.get("is_subscription"))

                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

                if is_subscription:

                    def _on_sub_click(e, tr=task_row, b=btn):
                        if e.button() == Qt.MouseButton.LeftButton:
                            from calendar_app.presentation.widgets.ui_components import (
                                get_hover_info_popup,
                            )

                            get_hover_info_popup().hide_for(b)
                            _show_subscription_detail(tr, b.window())
                            e.accept()

                    btn.mousePressEvent = _on_sub_click
                    btn.setProperty("is_subscription", True)
                    if tid in app.selected_task_ids:
                        btn.set_selected(True)

                if not tcol and is_multiday:
                    tcol = _theme_harmonized_color(_tc, tid)
                if not tcol and is_subscription:
                    tcol = _theme_harmonized_color(_tc, tid)

                # Always apply tag frame style (even when color is None) so the
                # local stylesheet overrides the global border-radius/padding rules.
                btn.set_tag_color(tcol)

                if is_subscription:
                    btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    btn.mousePressEvent = lambda e, tr=task_row, b=btn: (
                        _show_subscription_detail(tr, b.window())
                        if e.button() == Qt.MouseButton.LeftButton
                        else None
                    )
                else:
                    _connect_task_button_signals(app, btn)

                if tid in app.selected_task_ids:
                    btn.set_selected(True)

                if is_multiday:
                    btn.setProperty("is_multiday_bar", True)
                    btn.setProperty("hide_tag_strip", not is_origin)
                    install_hover_info(
                        btn, _build_multiday_tooltip_html(task_row, _tc), mode="inline_center"
                    )

                return btn

            # ?ㅼ쨷 일정 ?꾩젽 異붽?
            visible_lane_count = min(len(lanes), max_multiday_lanes)
            for lane_idx in range(visible_lane_count):
                # ??lane_idx ???대떦?섎뒗 일정??
                lane_tasks = [p for p in visible_multiday if p["lane"] == lane_idx]
                for p in lane_tasks:
                    task = p["task"]
                    span = p["end_col"] - p["start_col"] + 1

                    label = task["name"]
                    if not p["is_start"]:
                        label = f"... {label}"
                    if not p["is_end"]:
                        label = f"{label} ..."

                    is_origin = p["is_start"]
                    if task.get("is_subscription") and is_origin:
                        label = f"\U0001f4e1 {label}"
                    elif is_origin and task.get("priority"):
                        label = f"{priority_icon(task['priority'])} {label}"

                    btn = _build_task_button(task, label, True, is_origin)
                    btn.set_multiday_segment_shape(not p["is_start"], not p["is_end"])
                    if not is_origin:
                        btn.set_title_watermark(True)

                    # ?쎄컙???곹븯 ?щ갚怨?醫뚯슦 ?덉쓣 ?꾪빐 而⑦뀒?대꼫 ?ъ슜
                    container = QWidget()
                    vbox = QVBoxLayout(container)
                    vbox.setContentsMargins(0, 0, 0, 2)
                    vbox.setSpacing(0)
                    vbox.addWidget(btn)

                    # 洹몃━??諛곗튂: ??start_col), ??event_base_row + lane_idx)
                    week_grid.addWidget(
                        container, event_base_row + lane_idx, p["start_col"], 1, span
                    )

            # 媛??댁씠 ?ㅼ젣濡???씤 硫?곕뜲??lane ?섎? 怨꾩궛??
            # ?ㅻⅨ ?댁쓽 硫?곕뜲???뚮Ц??遺덊븘?뷀븳 鍮?以꾩씠 ?앷린吏 ?딄쾶 ?쒕떎.
            lane_count_by_col = {c: 0 for c in range(cols)}
            for c in range(cols):
                lane_ids = {
                    p["lane"] for p in visible_multiday if p["start_col"] <= c <= p["end_col"]
                }
                lane_count_by_col[c] = max(lane_ids) + 1 if lane_ids else 0

            # ?⑥씪 일정/?붾낫湲곕뒗 ?대퀎濡??쒖옉 ?됱쓣 ?낅┰ 怨꾩궛?쒕떎.
            max_row_used = event_base_row + visible_lane_count - 1
            for c in range(cols):
                tasks_for_col = week_single_tasks[c]
                multiday_rows = lane_count_by_col[c]

                single_capacity = max(0, total_event_slots - multiday_rows)
                visible_single_tasks = tasks_for_col[:single_capacity]
                remaining_single = len(tasks_for_col) - len(visible_single_tasks)
                total_hidden = hidden_counts_by_col[c] + remaining_single
                if (
                    total_hidden > 0
                    and visible_single_tasks
                    and (multiday_rows + len(visible_single_tasks) >= total_event_slots)
                ):
                    visible_single_tasks = visible_single_tasks[:-1]

                for idx, task in enumerate(visible_single_tasks):
                    title = str(task.get("name") or "").strip()
                    row = event_base_row + multiday_rows + idx
                    logger.debug(
                        "rendering task %s (%s) at r=%d c=%d", task.get("id"), title, row, c
                    )
                    if task.get("is_subscription"):
                        label = f"\U0001f4e1 {title}"
                    else:
                        label = (
                            f"{priority_icon(task.get('priority'))} {title}"
                            if task.get("priority")
                            else title
                        )
                    btn = _build_task_button(task, label, False, True)
                    install_hover_info(
                        btn, _build_single_task_tooltip_html(task, _tc), mode="inline_center"
                    )

                    container = QWidget()
                    vbox = QVBoxLayout(container)
                    vbox.setContentsMargins(0, 0, 0, 2)
                    vbox.setSpacing(0)
                    vbox.addWidget(btn)

                    week_grid.addWidget(container, row, c, 1, 1)
                    if row > max_row_used:
                        max_row_used = row

                remaining_single = len(tasks_for_col) - len(visible_single_tasks)
                total_hidden = hidden_counts_by_col[c] + remaining_single
                if total_hidden > 0:
                    more_btn = QPushButton(f"+ {total_hidden}개 더보기")
                    more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    more_btn.setStyleSheet(toolbar_styles["more_btn"])
                    more_btn.clicked.connect(lambda _, d=week_dates[c]: _jump_to_daily_view(app, d))

                    container = QWidget()
                    vbox = QVBoxLayout(container)
                    vbox.setContentsMargins(0, 0, 0, 0)  # 醫뚯슦 ?⑤뵫 ?쒓굅?섏뿬 ?뺣젹
                    vbox.addWidget(more_btn)

                    more_row = event_base_row + multiday_rows + len(visible_single_tasks)
                    week_grid.addWidget(container, more_row, c, 1, 1)
                    if more_row > max_row_used:
                        max_row_used = more_row

            # 洹몃━?쒖쓽 ?⑤뒗 怨듦컙??理쒗븯???щ챸 ?됱쑝濡?梨꾩썙???꾩젽?ㅼ씠 ?꾨줈 ?뺣젹?섎룄濡???
            week_grid.setRowStretch(max_row_used + 1, 1)

            days_layout.addWidget(week_widget, 1)

            # 援щ텇?????? 寃쎄퀎留??ъ슜???ㅼ젣 ?щ젰??媛源뚯슫 ?쒓컖 援ъ“ ?좎?.

    inner_v.addLayout(days_layout, 1)
    frame.setLayout(inner_v)
    app._multiday_bridge_overlay = None

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setStyleSheet(_calendar_scroll_style())
    scroll.setWidget(frame)

    new_layout.addWidget(scroll)


def _jump_to_daily_view(app, target_qdate):
    app.current_date = QDate(target_qdate)
    app.view_mode_state = "weekly_1"
    app.load_left_panel()
    app.load_center_panel()
