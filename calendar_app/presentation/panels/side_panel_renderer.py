import logging

from PyQt6.QtCore import QDate, QEvent, QLocale, QObject, Qt, QTimer
from PyQt6.QtGui import QColor, QMouseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from calendar_app.domain.routine_cycle import cycle_display_name, cycle_order_value
from calendar_app.domain.task_constants import (
    PRIORITY_MENU_ITEMS,
    STATUS_MENU_ITEMS,
    priority_icon,
    status_icon,
)
from calendar_app.domain.task_status_view import normalize_status as _normalize_task_status
from calendar_app.infrastructure.db import checklist_repo, directive_repo, search_repo
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.theme.ui_tokens import get_ui_shape_tokens
from calendar_app.presentation.widgets.ui_components import install_hover_info
from calendar_app.shared.color_utils import derive_text_palette, parse_hex_color, rgba_from_qcolor
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.icon_map import strip_leading_emoji as _se
from calendar_app.shared.qt_helpers import find_parent_dock
from calendar_app.shared.search_utils import clean_display_text as _tooltip_text_without_tags
from calendar_app.shared.search_utils import matches_search_query
from calendar_app.shared.theme_settings import (
    fpt as _fpt,
)
from calendar_app.shared.theme_settings import (
    get_text_theme_and_panel_base,
    get_theme_color,
)
from calendar_app.shared.theme_settings import (
    panel_palette as _panel_palette,
)

logger = logging.getLogger(__name__)
_panel_calendar_cache = None  # dict | None: {calendar_id: color}


def _shape_tokens() -> dict:
    return get_ui_shape_tokens()


def _calendar_color_for_task(task: dict) -> str | None:
    """Resolve fallback calendar color for subscription or linked calendar tasks."""
    global _panel_calendar_cache
    if _panel_calendar_cache is None:
        try:
            from calendar_app.infrastructure.db.calendar_repo import list_calendars

            _panel_calendar_cache = {
                c["id"]: c.get("color") for c in list_calendars(include_inactive=True)
            }
        except Exception:
            _panel_calendar_cache = {}
    cal_id = task.get("calendar_id")
    if not cal_id:
        src = task.get("gcal_source_calendar_id")
        if src:
            cal_id = f"gcal::{src}"
    if cal_id:
        return _panel_calendar_cache.get(cal_id)
    return None


def invalidate_panel_calendar_cache():
    global _panel_calendar_cache
    _panel_calendar_cache = None


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


class _PanelItemFilter(QObject):
    """Separate single-click selection from double-click open behavior."""

    def __init__(self, app, tid, is_directive, main_handler):
        super().__init__()
        self._app = app
        self._tid = tid
        self._is_directive = is_directive
        self._main_handler = main_handler
        self._pending_single_click = False
        self._pending_ctrl = False
        self._single_click_timer = QTimer(self)
        self._single_click_timer.setSingleShot(True)
        self._single_click_timer.timeout.connect(self._flush_single_click)

    def _flush_single_click(self):
        if self._pending_single_click:
            _handle_panel_item_click(self._app, self._tid, self._is_directive, self._pending_ctrl)
        self._pending_single_click = False

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self._pending_single_click = True
                self._pending_ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
                interval = 250
                app = QApplication.instance()
                if app is not None:
                    interval = max(200, int(app.doubleClickInterval()))
                self._single_click_timer.start(interval)
                # Keep press events flowing so Qt can still detect true double-clicks.
                return False
        elif (
            event.type() == QEvent.Type.MouseButtonDblClick
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self._single_click_timer.stop()
            self._pending_single_click = False
            if self._main_handler:
                self._main_handler()
            return True
        return False


def _handle_panel_item_click(app, tid, is_directive, ctrl):
    """Update task or directive selection state from panel item clicks."""
    if not hasattr(app, "selected_task_ids"):
        app.selected_task_ids = set()
    if not hasattr(app, "selected_directive_ids"):
        app.selected_directive_ids = set()

    selected = app.selected_directive_ids if is_directive else app.selected_task_ids

    if ctrl:
        if tid in selected:
            selected.discard(tid)
        else:
            selected.add(tid)
    else:
        app.selected_task_ids.clear()
        app.selected_directive_ids.clear()
        selected.add(tid)

    _refresh_panel_selection_visuals(app)
    if hasattr(app, "update_task_selection_status"):
        app.update_task_selection_status()


def _apply_panel_item_style(container, selected, bg_color):
    """Apply consistent card style for panel items across normal/selected states."""
    _tc = get_theme_color()
    shape = _shape_tokens()
    card_radius = int(shape.get("panel_item_radius", 0))
    tag_bg = "rgba(255, 255, 255, 13)"
    tag_hover_bg = "rgba(255, 255, 255, 23)"
    tag_selected_bg = _tc_rgba(40)
    selected_hover_bg = _tc_rgba(55)
    left_color = "transparent"
    selected_left_color = _tc

    if bg_color:
        _tc_left = _color_rgba(bg_color, 255, _tc)
        left_color = _tc_left
        selected_left_color = _tc_left
        try:
            from PyQt6.QtGui import QColor

            _tag = QColor(str(bg_color))
            if _tag.isValid():
                tag_bg = f"rgba({_tag.red()}, {_tag.green()}, {_tag.blue()}, 30)"
                tag_hover_bg = f"rgba({_tag.red()}, {_tag.green()}, {_tag.blue()}, 44)"
                tag_selected_bg = f"rgba({_tag.red()}, {_tag.green()}, {_tag.blue()}, 52)"
                selected_hover_bg = f"rgba({_tag.red()}, {_tag.green()}, {_tag.blue()}, 64)"
        except Exception:
            pass

    if selected:
        container.setStyleSheet(f"""
            QFrame {{
                background-color: {tag_selected_bg};
                border-radius: {card_radius}px;
                border: 1px solid {_tc_rgba(180)};
                border-left-color: {selected_left_color};
                border-left-width: 3px;
                border-left-style: solid;
                margin: 1px 4px;
            }}
            QFrame:hover {{
                background-color: {selected_hover_bg};
                border: 1px solid {_tc_rgba(200)};
                border-left-color: {selected_left_color};
                border-left-width: 3px;
                border-left-style: solid;
            }}
        """)
    else:
        container.setStyleSheet(f"""
            QFrame {{
                background-color: {tag_bg};
                border-radius: {card_radius}px;
                border: 1px solid rgba(255, 255, 255, 30);
                border-left-color: {left_color};
                border-left-width: 3px;
                border-left-style: solid;
                margin: 1px 4px;
            }}
            QFrame:hover {{
                background-color: {tag_hover_bg};
                border: 1px solid rgba(255, 255, 255, 56);
                border-left-color: {left_color};
                border-left-width: 3px;
                border-left-style: solid;
            }}
        """)


def _refresh_panel_selection_visuals(app):
    """Refresh selection styling for all visible panel task and directive items."""
    task_sel = getattr(app, "selected_task_ids", set())
    dir_sel = getattr(app, "selected_directive_ids", set())
    import contextlib

    for tid, (container, bg_color) in list(getattr(app, "_panel_task_frames", {}).items()):
        with contextlib.suppress(RuntimeError):
            _apply_panel_item_style(container, tid in task_sel, bg_color)
    for did, (container, bg_color) in list(getattr(app, "_panel_directive_frames", {}).items()):
        with contextlib.suppress(RuntimeError):
            _apply_panel_item_style(container, did in dir_sel, bg_color)


def clear_panel_selections(app):
    """Clear panel selections and return whether any selection actually changed."""
    changed = bool(getattr(app, "selected_task_ids", None)) or bool(
        getattr(app, "selected_directive_ids", None)
    )
    if hasattr(app, "selected_task_ids"):
        app.selected_task_ids.clear()
    if hasattr(app, "selected_directive_ids"):
        app.selected_directive_ids.clear()
    if changed:
        _refresh_panel_selection_visuals(app)
        if hasattr(app, "update_task_selection_status"):
            app.update_task_selection_status()
    return changed


def _tc_rgba(alpha_0_to_255: int) -> str:
    """테마 컬러에 알파값을 적용한 rgba 문자열을 반환합니다."""
    c = QColor(get_theme_color())
    if not c.isValid():
        c = QColor("#4da6ff")
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha_0_to_255})"


def _box_bg(color_hex, alpha=160):
    if not color_hex:
        return "rgba(28, 28, 36, 160)"
    try:
        c = QColor(color_hex)
        if not c.isValid():
            return "rgba(28, 28, 36, 160)"
        return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"
    except Exception:
        return "rgba(28, 28, 36, 160)"


def _color_rgba(color_hex, alpha=255, fallback="#4da6ff"):
    return rgba_from_qcolor(parse_hex_color(color_hex or fallback, fallback), alpha)


def _panel_text_palette() -> dict:
    """Return panel text palette dict (primary/secondary/muted/accent)."""
    text_theme, _ = get_text_theme_and_panel_base()
    return derive_text_palette(str(text_theme), get_theme_color())


def _panel_text_color() -> str:
    """패널 텍스트기본 색"""
    return _panel_text_palette()["text_primary"]


def _panel_text_secondary() -> str:
    """패널 蹂댁“ 텍스트 색"""
    return _panel_text_palette()["text_secondary"]


def _panel_text_muted() -> str:
    """패널 흐릿한 보조 텍스트 색"""
    return _panel_text_palette()["text_muted"]


def _panel_text_faint() -> str:
    """패널 가장 희미한 텍스트/비활성 텍스트 색"""
    return _panel_text_palette()["text_faint"]


def _app_locale() -> QLocale:
    # QLocale default is set by I18nManager._apply_qt_locale() at startup
    return QLocale()


def _localized_weekday_short(qd: QDate) -> str:
    try:
        short_name = _app_locale().standaloneDayName(qd.dayOfWeek(), QLocale.FormatType.ShortFormat)
        if short_name:
            return short_name
    except Exception:
        pass
    day_names = [
        t("weekday.mon", "Mon"),
        t("weekday.tue", "Tue"),
        t("weekday.wed", "Wed"),
        t("weekday.thu", "Thu"),
        t("weekday.fri", "Fri"),
        t("weekday.sat", "Sat"),
        t("weekday.sun", "Sun"),
    ]
    return day_names[qd.dayOfWeek() - 1]


def _panel_surface_style():
    pal = _panel_palette()
    shape = _shape_tokens()
    surface_radius = int(shape.get("panel_surface_radius", 0))
    return f"""
        QFrame#panel_surface {{
            background-color: {pal["surface_bg"]};
            border-radius: {surface_radius}px;
            border: none;
        }}
    """


def _panel_toolbar_style():
    pal = _panel_palette()
    shape = _shape_tokens()
    toolbar_radius = int(shape.get("panel_toolbar_radius", 0))
    return f"""
        QWidget#panel_toolbar {{
            background-color: {pal["toolbar_bg"]};
            border-radius: {toolbar_radius}px;
            border: none;
        }}
    """


def _toolbar_button_style():
    txt = _panel_text_secondary()
    shape = _shape_tokens()
    btn_radius = int(shape.get("panel_toolbar_button_radius", 0))
    hover_bg = "rgba(255, 255, 255, 0.08)"
    hover_border = "rgba(255, 255, 255, 0.06)"
    hover_txt = _panel_text_color()
    return f"""
        QPushButton {{
            color: {txt};
            background-color: transparent;
            font-weight: bold;
            font-size: {_fpt()};
            border-radius: {btn_radius}px;
            padding: 2px 7px;
            border: none;
            min-width: 24px;
            min-height: 22px;
        }}
        QPushButton:hover {{
            background-color: {hover_bg};
            border: 1px solid {hover_border};
            color: {hover_txt};
        }}
    """


def _panel_menu_style():
    from PyQt6.QtCore import QSettings

    s = QSettings("kimhyojin", "Dark Calendar")
    base = QColor(str(s.value("panel_base_color", "#1c1c1c")))
    if not base.isValid():
        base = QColor("#1c1c1c")
    opacity_raw = s.value("last_opacity", 200, type=int)
    if opacity_raw <= 100:
        opacity_raw = int(opacity_raw * 255 / 100)
    opacity = max(0.0, min(1.0, opacity_raw / 255.0))
    menu_bg = f"rgba({base.red()}, {base.green()}, {base.blue()}, {max(210, int(242 * opacity))})"
    menu_txt = _panel_text_secondary()
    menu_muted = _panel_text_muted()
    menu_disabled = _panel_text_faint()
    menu_border = "rgba(255, 255, 255, 18)"
    sep_color = "rgba(255,255,255,20)"
    sel_txt = _panel_text_color()
    shape = _shape_tokens()
    menu_radius = int(shape.get("panel_menu_radius", 0))
    menu_item_radius = int(shape.get("panel_menu_item_radius", 0))
    return f"""
        QMenu {{
            background-color: {menu_bg};
            color: {menu_txt};
            border: 1px solid {menu_border};
            padding: 4px;
            border-radius: {menu_radius}px;
        }}
        QMenu::item {{
            padding: 6px 24px 6px 10px;
            border-radius: {menu_item_radius}px;
            margin: 2px;
            color: {menu_txt};
        }}
        QMenu::item:selected {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {_tc_rgba(40)}, stop:1 {_tc_rgba(78)});
            border: 1px solid {_tc_rgba(120)};
            color: {sel_txt};
        }}
        QMenu::item:disabled {{
            color: {menu_disabled};
        }}
        QMenu::right-arrow {{
            color: {menu_muted};
        }}
        QMenu::separator {{
            height: 1px;
            background: {sep_color};
            margin: 4px 10px;
        }}
    """


def _directive_group_header(receiver_name):
    wrap = QWidget()
    row = QHBoxLayout(wrap)
    row.setContentsMargins(2, 8, 2, 4)
    row.setSpacing(8)

    badge = QLabel("BY")
    shape = _shape_tokens()
    badge_radius = int(shape.get("panel_group_badge_radius", 0))
    badge.setFixedSize(20, 20)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setStyleSheet(
        f"background-color: {_tc_rgba(30)}; "
        f"border: 1px solid {_tc_rgba(80)}; "
        f"border-radius: {badge_radius}px; "
        f"color: {get_theme_color()}; font-size: {_fpt(-2)};"
    )
    row.addWidget(badge)

    name = QLabel(receiver_name)
    name.setStyleSheet(
        f"color: {_panel_text_color()}; font-size: {_fpt(-1)}; font-weight: bold; "
        "background: transparent; border: none; padding: 0 2px 0 0;"
    )
    row.addWidget(name)

    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(
        f"background-color: {_tc_rgba(55)}; border: none; min-height: 1px; max-height: 1px;"
    )
    row.addWidget(line, 1)

    return wrap


def _deadline_group_header(deadline_text):
    wrap = QWidget()
    row = QHBoxLayout(wrap)
    row.setContentsMargins(2, 8, 2, 4)
    row.setSpacing(8)

    badge = QLabel("📅")
    shape = _shape_tokens()
    badge_radius = int(shape.get("panel_group_badge_radius", 0))
    badge.setFixedSize(20, 20)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setStyleSheet(
        f"background-color: {_tc_rgba(30)}; "
        f"border: 1px solid {_tc_rgba(80)}; "
        f"border-radius: {badge_radius}px; "
        f"color: {get_theme_color()}; font-size: {_fpt(-2)};"
    )
    row.addWidget(badge)

    name = QLabel(f"{deadline_text}{t('panel.deadline_suffix', ' 마감')}")
    name.setStyleSheet(
        f"color: {_panel_text_color()}; font-size: {_fpt(-1)}; font-weight: bold; "
        "background: transparent; border: none; padding: 0 2px 0 0;"
    )
    row.addWidget(name)

    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(
        f"background-color: {_tc_rgba(55)}; border: none; min-height: 1px; max-height: 1px;"
    )
    row.addWidget(line, 1)

    return wrap


def _schedule_group_header(label_text, icon="📅"):
    wrap = QWidget()
    row = QHBoxLayout(wrap)
    row.setContentsMargins(2, 8, 2, 4)
    row.setSpacing(8)

    badge = QLabel(icon)
    shape = _shape_tokens()
    badge_radius = int(shape.get("panel_group_badge_radius", 0))
    badge.setFixedSize(20, 20)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setStyleSheet(
        f"background-color: {_tc_rgba(30)}; "
        f"border: 1px solid {_tc_rgba(80)}; "
        f"border-radius: {badge_radius}px; "
        f"color: {get_theme_color()}; font-size: {_fpt(-2)};"
    )
    row.addWidget(badge)

    name = QLabel(label_text)
    name.setStyleSheet(
        f"color: {_panel_text_color()}; font-size: {_fpt(-1)}; font-weight: bold; "
        "background: transparent; border: none; padding: 0 2px 0 0;"
    )
    row.addWidget(name)

    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(
        f"background-color: {_tc_rgba(55)}; border: none; min-height: 1px; max-height: 1px;"
    )
    row.addWidget(line, 1)

    return wrap


def _routine_group_header(label_text, icon="🔄"):
    wrap = QWidget()
    row = QHBoxLayout(wrap)
    row.setContentsMargins(2, 8, 2, 4)
    row.setSpacing(8)

    badge = QLabel(icon)
    shape = _shape_tokens()
    badge_radius = int(shape.get("panel_group_badge_radius", 0))
    badge.setFixedSize(20, 20)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setStyleSheet(
        f"background-color: {_tc_rgba(30)}; "
        f"border: 1px solid {_tc_rgba(80)}; "
        f"border-radius: {badge_radius}px; "
        f"color: {get_theme_color()}; font-size: {_fpt(-2)};"
    )
    row.addWidget(badge)

    name = QLabel(label_text)
    name.setStyleSheet(
        f"color: {_panel_text_color()}; font-size: {_fpt(-1)}; font-weight: bold; "
        "background: transparent; border: none; padding: 0 2px 0 0;"
    )
    row.addWidget(name)

    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(
        f"background-color: {_tc_rgba(55)}; border: none; min-height: 1px; max-height: 1px;"
    )
    row.addWidget(line, 1)

    return wrap


def _normalized_directive_status(status):
    return _normalize_task_status(status)


def _build_checklist_items(app, steps):
    """Return (display_type, items).

    items = [(raw_text, is_completed, handler)] — 번호 prefix는 붙이지 않는다.
    목록형/프로세스형 구분은 렌더러(create_task_box)가 인디케이터로 표현한다.
    """
    if not steps:
        return ("list", [])
    display_type = steps[0].get("display_type", "list")
    items = []
    for step in steps:
        items.append(
            (
                step["item_text"],
                step["is_completed"],
                lambda *args, sid=step["id"]: app.toggle_checklist_item(sid),
            )
        )
    return (display_type, items)


class DockTitleBar(QWidget):
    """Panel title bar with draggable dock behavior."""

    def __init__(
        self,
        title_text,
        title_style=None,
        add_handler=None,
        manage_handler=None,
        icon_text="*",
        trailing_widget=None,
    ):
        super().__init__()
        self._dock_ref = None
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("panel_toolbar")
        self.setStyleSheet(_panel_toolbar_style())
        self.setCursor(Qt.CursorShape.SizeAllCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 8, 4)
        layout.setSpacing(6)

        icon = QLabel(icon_text)
        icon.setStyleSheet(
            f"color: {get_theme_color()}; font-size: {_fpt(-2)}; background: transparent; border: none;"
        )
        layout.addWidget(icon)

        title = QLabel(title_text)
        if not title_style:
            title_style = f"color: {_panel_text_color()}; font-weight: bold; font-size: {_fpt()}; background: transparent; border: none;"
        title.setStyleSheet(title_style)
        layout.addWidget(title)
        layout.addStretch(1)

        if trailing_widget is not None:
            layout.addWidget(trailing_widget)

        icon_btn_style = _toolbar_button_style()

        if add_handler:
            add_btn = QPushButton("+")
            add_btn.setToolTip(t("panel.toolbar.add"))
            add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            add_btn.setStyleSheet(icon_btn_style)
            add_btn.clicked.connect(add_handler)
            layout.addWidget(add_btn)

        if manage_handler:
            manage_btn = QPushButton("...")
            manage_btn.setToolTip(t("panel.toolbar.manage"))
            manage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            manage_btn.setStyleSheet(icon_btn_style)
            manage_btn.clicked.connect(manage_handler)
            layout.addWidget(manage_btn)

    def _dock(self):
        return find_parent_dock(self, self._dock_ref)

    def bind_dock(self, dock):
        self._dock_ref = dock

    def mousePressEvent(self, event: QMouseEvent):
        dock = self._dock()
        if dock:
            dock.mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        dock = self._dock()
        if dock:
            dock.mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        dock = self._dock()
        if dock:
            dock.mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        dock = self._dock()
        if dock:
            # Explicitly toggle floating so double-click works even when tabified.
            dock.setFloating(not dock.isFloating())


def create_panel(
    app,
    title_text,
    items,
    hotkey_hint=None,
    add_handler=None,
    manage_handler=None,
    title_style=None,
    trailing_widget=None,
):
    icon_map = {
        t("panel.today_schedule", "Today's Schedule"): "📅",
        t("panel.this_week_schedule", "이번 주 일정"): "📅",
        t("panel.routine", "Routine Tasks"): "🔁",
        t("panel.directive", "Directions"): "📣",
    }
    title_bar = DockTitleBar(
        title_text,
        title_style=title_style,
        add_handler=add_handler,
        manage_handler=manage_handler,
        icon_text=icon_map.get(title_text, "*"),
        trailing_widget=trailing_widget,
    )

    frame = QFrame()
    frame.setObjectName("panel_surface")
    frame.setStyleSheet(_panel_surface_style())

    if add_handler:

        def dbl_click(_event):
            add_handler()

        frame.mouseDoubleClickEvent = dbl_click

    layout = QVBoxLayout()
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(7)

    search_query = (
        getattr(app, "search_edit", None).text() if getattr(app, "search_edit", None) else ""
    )
    for item in items:
        if isinstance(item, QWidget):
            layout.addWidget(item)
            continue

        if isinstance(item, tuple):
            text, handler = item
            if not matches_search_query(search_query, text):
                continue

            btn = QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            _btn_txt = _panel_text_color()
            _btn_bg = "rgba(255,255,255,0.07)"
            _btn_hover_txt = _panel_text_color()
            btn.setStyleSheet(f"""
                QPushButton {{
                    color: {_btn_txt}; text-align: left; padding: 4px 8px;
                    border: none;
                    border-radius: 0px;
                    background: {_btn_bg};
                    font-size: {_fpt()};
                }}
            """)
            btn.clicked.connect(handler)
            layout.addWidget(btn)
        else:
            lbl = QLabel(str(item))
            _empty_txt = _panel_text_faint()
            lbl.setStyleSheet(
                f"color: {_empty_txt}; padding: 6px 8px; font-size: {_fpt(-1)}; font-style: italic;"
            )
            lbl.setWordWrap(True)
            layout.addWidget(lbl)

    layout.addStretch(1)
    frame.setLayout(layout)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
    scroll.setWidget(frame)

    return scroll, title_bar


def _left_panel_mode(app):
    raw = getattr(app, "left_panel_mode", None)
    if raw:
        return str(raw)
    if hasattr(app, "settings"):
        raw = app.settings.value("left_panel_mode", "today")
        return str(raw or "today")
    return "today"


def _set_left_panel_mode(app, mode):
    mode = "week" if str(mode).lower() == "week" else "today"
    app.left_panel_mode = mode
    if hasattr(app, "settings"):
        app.settings.setValue("left_panel_mode", mode)
    if hasattr(app, "schedule_panel_refresh"):
        app.schedule_panel_refresh(left=True)


def _build_left_panel_mode_switch(app, mode):
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)

    active_bg = _tc_rgba(56)
    active_border = _tc_rgba(120)
    shape = _shape_tokens()
    switch_radius = int(shape.get("panel_mode_switch_radius", 0))
    inactive_bg = "rgba(255,255,255,0.06)"
    inactive_border = "rgba(255,255,255,0.10)"
    active_text = _panel_text_color()
    inactive_text = _panel_text_secondary()

    def _make_btn(label, target_mode):
        is_active = mode == target_mode
        btn = QPushButton(label)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(24)
        btn.setStyleSheet(f"""
            QPushButton {{
                color: {active_text if is_active else inactive_text};
                background: {active_bg if is_active else inactive_bg};
                border: 1px solid {active_border if is_active else inactive_border};
                border-radius: {switch_radius}px;
                padding: 0 8px;
                font-size: {_fpt(-2)};
                font-weight: {"700" if is_active else "500"};
            }}
            QPushButton:hover {{
                border: 1px solid {active_border};
                background: {_tc_rgba(38)};
            }}
        """)
        btn.clicked.connect(lambda _=False, m=target_mode: _set_left_panel_mode(app, m))
        return btn

    layout.addWidget(_make_btn(t("dialog.common.today", "Today"), "today"))
    layout.addWidget(_make_btn(t("panel.this_week", "This Week"), "week"))
    return container


def show_side_panel_context_menu(app, widget, pos, tid, task_name, is_routine=False):
    from PyQt6.QtWidgets import QMenu

    task_sel = getattr(app, "selected_task_ids", set())
    if tid not in task_sel:
        task_sel.clear()
        getattr(app, "selected_directive_ids", set()).clear()
        task_sel.add(tid)
        _refresh_panel_selection_visuals(app)
        if hasattr(app, "update_task_selection_status"):
            app.update_task_selection_status()
    sel_count = len(getattr(app, "selected_task_ids", set()))

    menu_style = _panel_menu_style()
    menu = QMenu(widget)
    menu.setStyleSheet(menu_style)

    act_edit = menu.addAction(_se(t("dialog.common.modify")))
    act_edit.setIcon(_ic(ICON.EDIT))
    del_label = (
        t("dialog.common.delete_n", n=sel_count) if sel_count > 1 else t("dialog.common.delete")
    )
    act_delete = menu.addAction(del_label)
    act_delete.setIcon(_ic(ICON.DELETE))

    # 체크리스트는 일반업무(routine)에만 존재
    act_checklist = None
    if is_routine:
        act_checklist = menu.addAction(_se(t("context_menu.view_checklist", "체크리스트 보기")))
        act_checklist.setIcon(_ic(ICON.CHECKLIST))
    menu.addSeparator()

    priority_menu = menu.addMenu(_se(t("menu.priority_change")))
    priority_menu.setIcon(_ic(ICON.SORT_BY_PRIORITY))
    priority_menu.setStyleSheet(menu_style)
    priority_map = {}
    for label, value in PRIORITY_MENU_ITEMS:
        priority_map[priority_menu.addAction(_se(label))] = value

    status_menu = menu.addMenu(_se(t("menu.status_change")))
    status_menu.setIcon(_ic(ICON.STATUS_IN_PROGRESS))
    status_menu.setStyleSheet(menu_style)
    action_map = {}
    for label, value in STATUS_MENU_ITEMS:
        action_map[status_menu.addAction(_se(label))] = value
    menu.addSeparator()

    color_menu = menu.addMenu(_se(t("menu.color_tag_settings")))
    color_menu.setIcon(_ic(ICON.COLOR_PICKER))
    color_menu.setStyleSheet(menu_style)
    act_color_auto = color_menu.addAction(_se(t("menu.color_auto")))
    act_color_change = color_menu.addAction(_se(t("dialog.common.modify")))
    act_color_clear = color_menu.addAction(_se(t("menu.color_clear")))

    action = menu.exec(widget.mapToGlobal(pos))
    if act_checklist is not None and action == act_checklist:
        if hasattr(app, "handle_checklist_requested"):
            app.handle_checklist_requested(tid)
    elif action == act_edit:
        if hasattr(app, "open_modify_task_dialog"):
            app.open_modify_task_dialog(tid)
    elif action == act_delete:
        if hasattr(app, "handle_task_deleted"):
            app.handle_task_deleted(tid)
    elif action in priority_map and hasattr(app, "handle_task_priority_changed"):
        app.handle_task_priority_changed(tid, priority_map[action])
    elif action in action_map:
        app.handle_task_status_changed(tid, action_map[action])
    elif action == act_color_auto and hasattr(app, "handle_color_auto_assign_requested"):
        app.handle_color_auto_assign_requested(tid)
    elif action == act_color_change and hasattr(app, "handle_color_change_requested"):
        app.handle_color_change_requested(tid)
    elif action == act_color_clear and hasattr(app, "handle_color_clear_requested"):
        app.handle_color_clear_requested(tid)


def show_directive_context_menu(app, widget, pos, did, task_name):
    from PyQt6.QtWidgets import QMenu

    dir_sel = getattr(app, "selected_directive_ids", set())
    if did not in dir_sel:
        dir_sel.clear()
        getattr(app, "selected_task_ids", set()).clear()
        dir_sel.add(did)
        _refresh_panel_selection_visuals(app)
        if hasattr(app, "update_task_selection_status"):
            app.update_task_selection_status()
    sel_count = len(getattr(app, "selected_directive_ids", set()))

    menu_style = _panel_menu_style()
    menu = QMenu(widget)
    menu.setStyleSheet(menu_style)

    act_edit = menu.addAction(_se(t("dialog.common.modify")))
    act_edit.setIcon(_ic(ICON.EDIT))
    del_label = (
        t("dialog.common.delete_n", n=sel_count) if sel_count > 1 else t("dialog.common.delete")
    )
    act_delete = menu.addAction(del_label)
    act_delete.setIcon(_ic(ICON.DELETE))
    menu.addSeparator()

    priority_menu = menu.addMenu(_se(t("menu.priority_change")))
    priority_menu.setIcon(_ic(ICON.SORT_BY_PRIORITY))
    priority_menu.setStyleSheet(menu_style)
    priority_map = {}
    for label, value in PRIORITY_MENU_ITEMS:
        priority_map[priority_menu.addAction(_se(label))] = value

    status_menu = menu.addMenu(_se(t("menu.status_change")))
    status_menu.setIcon(_ic(ICON.STATUS_IN_PROGRESS))
    status_menu.setStyleSheet(menu_style)
    action_map = {}
    for label, value in STATUS_MENU_ITEMS:
        action_map[status_menu.addAction(_se(label))] = value
    menu.addSeparator()

    color_menu = menu.addMenu(_se(t("menu.color_tag_settings")))
    color_menu.setIcon(_ic(ICON.COLOR_PICKER))
    color_menu.setStyleSheet(menu_style)
    act_color_auto = color_menu.addAction(_se(t("menu.color_auto")))
    act_color_change = color_menu.addAction(_se(t("dialog.common.modify")))
    act_color_clear = color_menu.addAction(_se(t("menu.color_clear")))

    action = menu.exec(widget.mapToGlobal(pos))
    if action == act_edit:
        if hasattr(app, "open_directive_dialog"):
            app.open_directive_dialog(did)
    elif action == act_delete:
        if hasattr(app, "delete_selected_directives"):
            app.delete_selected_directives()
    elif action in priority_map and hasattr(app, "handle_directive_priority_changed"):
        app.handle_directive_priority_changed(did, priority_map[action])
    elif action in action_map and hasattr(app, "handle_directive_status_changed"):
        app.handle_directive_status_changed(did, action_map[action])
    elif action == act_color_auto and hasattr(app, "handle_directive_color_auto_assign_requested"):
        app.handle_directive_color_auto_assign_requested(did)
    elif action == act_color_change and hasattr(app, "handle_directive_color_change_requested"):
        app.handle_directive_color_change_requested(did)
    elif action == act_color_clear and hasattr(app, "handle_directive_color_clear_requested"):
        app.handle_directive_color_clear_requested(did)


def create_task_box(
    app,
    title_text,
    main_handler,
    info_items=None,
    checklist_items=None,
    tid=None,
    is_routine=False,
    is_directive=False,
    tooltip_title=None,
    bg_color=None,
    checklist_display_type="list",
):
    """Create a task item box used in side panels."""
    _tc = get_theme_color()
    container = QFrame()

    is_selected = False
    if tid is not None:
        selected_set = (
            getattr(app, "selected_directive_ids", set())
            if is_directive
            else getattr(app, "selected_task_ids", set())
        )
        is_selected = tid in selected_set
    _apply_panel_item_style(container, is_selected, bg_color)

    box_layout = QVBoxLayout(container)
    box_layout.setContentsMargins(4, 2, 5, 2)
    box_layout.setSpacing(0)

    top_layout = QHBoxLayout()
    top_layout.setContentsMargins(0, 0, 0, 0)
    top_layout.setSpacing(5)
    title_btn = QPushButton(title_text)
    title_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    _title_txt = _panel_text_color()
    _title_hover_txt = _panel_text_color()
    _title_hover_bg = "rgba(255,255,255,0.04)"
    shape = _shape_tokens()
    inline_hover_radius = int(shape.get("panel_inline_hover_radius", 0))
    title_btn.setStyleSheet(f"""
        QPushButton {{
            color: {_title_txt}; text-align: left; padding: 3px 5px 3px 4px; border: none;
            background: transparent; font-weight: normal; font-size: {_fpt()};
        }}
        QPushButton:hover {{ color: {_title_hover_txt}; background: {_title_hover_bg}; border-radius: {inline_hover_radius}px; }}
    """)
    if tid is None and main_handler:
        title_btn.clicked.connect(lambda checked=False: main_handler(checked))

    if tid is not None:
        title_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        if is_directive:
            title_btn.customContextMenuRequested.connect(
                lambda pos, w=title_btn, id_=tid, name=title_text: show_directive_context_menu(
                    app, w, pos, id_, name
                )
            )
        else:
            title_btn.customContextMenuRequested.connect(
                lambda pos,
                w=title_btn,
                id_=tid,
                name=title_text,
                rt=is_routine: show_side_panel_context_menu(app, w, pos, id_, name, is_routine=rt)
            )

    title_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    title_btn.setMinimumHeight(24)

    heading = tooltip_title if tooltip_title else title_text
    _sep_color = _tc_rgba(115)
    _title_color = get_theme_color()
    tooltip_lines = [
        f"<div style='font-size: {_fpt()};'><b style='color:{_title_color};'>{heading}</b></div>"
    ]
    if info_items:
        _tip_icon_color = _panel_text_muted()
        _tip_text_color = _panel_text_secondary()
        tooltip_lines.append(
            f"<div style='border-bottom: 1px solid {_sep_color}; margin:5px 0 4px 0;'></div>"
            "<table cellspacing='0' cellpadding='0' style='margin-top:1px;'>"
        )
        for icon, text in info_items:
            tooltip_lines.append(
                f"<tr>"
                f"<td style='width:16px; padding:2px 0; vertical-align:top; color:{_tip_icon_color};'>{icon}</td>"
                f"<td style='padding:2px 0 2px 6px; white-space: normal; color:{_tip_text_color};'>{text}</td>"
                f"</tr>"
            )
        tooltip_lines.append("</table>")

    tooltip_html = f"<div style='text-align: left;'>{''.join(tooltip_lines)}</div>"
    install_hover_info(title_btn, tooltip_html)

    top_layout.addWidget(title_btn)

    checklist_container = QFrame()
    checklist_container.setObjectName("ChecklistContainer")
    chk_layout = QVBoxLayout(checklist_container)
    chk_layout.setContentsMargins(4, 1, 4, 4)
    chk_layout.setSpacing(1)

    if checklist_items:
        total_cnt = len(checklist_items)
        done_cnt = sum(1 for _, sis_c, _ in checklist_items if sis_c)
        is_process = checklist_display_type == "process"

        exp_tids = getattr(app, "expanded_tids", set())
        app.expanded_tids = exp_tids
        is_initially_visible = (tid is not None) and (is_routine or (tid in app.expanded_tids))

        _tc_hex = get_theme_color()

        def _toggle_label(visible, d=done_cnt, tot=total_cnt):
            arr = "▾" if visible else "▸"
            return f"{arr}  {d}/{tot}"

        # ── Toggle button — quiet text style (테두리/배경 없음) ───────────
        toggle_btn = QPushButton(_toggle_label(is_initially_visible))
        toggle_btn.setFixedHeight(16)
        toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle_btn.setToolTip(t("panel.checklist_tooltip"))
        _pill_txt = _panel_text_muted()
        toggle_btn.setStyleSheet(f"""
            QPushButton {{
                color: {_pill_txt};
                background: transparent;
                border: none;
                font-size: {_fpt(-2)};
                padding: 0 4px;
                font-weight: 600;
            }}
            QPushButton:hover {{ color: {_tc_hex}; }}
        """)
        top_layout.addWidget(toggle_btn)

        # ── Progress bar — slim & subtle ──────────────────────────────────
        prog_bar = QProgressBar()
        prog_bar.setRange(0, max(total_cnt, 1))
        prog_bar.setValue(done_cnt)
        prog_bar.setFixedHeight(2)
        prog_bar.setTextVisible(False)
        prog_bar.setToolTip(f"완료 {done_cnt}개 / 전체 {total_cnt}개")
        prog_bar.setToolTip(f"완료 {done_cnt}개 / 전체 {total_cnt}개")
        prog_bar.setStyleSheet(f"""
            QProgressBar {{
                background: rgba(255,255,255,0.08);
                border: none;
                border-radius: 1px;
                margin: 2px 0px 5px 0px;
            }}
            QProgressBar::chunk {{
                background: {_tc_hex};
                border-radius: 1px;
            }}
        """)
        chk_layout.addWidget(prog_bar)

        # ── Item rows ─────────────────────────────────────────────────────
        # 목록형(list): 작은 사각 체크박스 / 프로세스형(process): 원형 번호 단계
        _chk_done_txt = _panel_text_muted()
        _chk_pend_txt = _panel_text_secondary()

        for idx, (stext, sis_c, chandler) in enumerate(checklist_items):
            clickable = callable(chandler)
            _locked = False
            _lock_reason = ""
            if is_process and clickable:
                if not sis_c:
                    # 완료 청루: 이전 항목이 모두 완료되어야 함
                    _locked = not all(checklist_items[i][1] for i in range(idx))
                    if _locked:
                        _lock_reason = "이전 단계를 먼저 완료하세요"
                else:
                    # 취소: 이후 항목이 모두 미완료여야 함
                    _locked = not all(
                        not checklist_items[i][1] for i in range(idx + 1, len(checklist_items))
                    )
                    if _locked:
                        _lock_reason = "이후 단계를 먼저 취소하세요"
                if _locked:
                    clickable = False

            item_w = QWidget()
            item_w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            item_w.setStyleSheet(
                "QWidget { background: transparent; border: none; outline: none; }"
                " QWidget:hover { background: rgba(255,255,255,0.03); border-radius: 3px; }"
            )
            item_w.setFixedHeight(20)
            item_l = QHBoxLayout(item_w)
            item_l.setContentsMargins(2, 0, 2, 0)
            item_l.setSpacing(1)

            ind = QPushButton()
            ind.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            ind.setFlat(True)
            # 항목별 박스/색상 태그 제거 — 번호/체크 글리프만 (무배경·무테두리·무테마색)
            _ind_style = (
                "QPushButton {{ background: transparent; border: none;"
                " padding: 0; font-size: 10px; color: {color}; font-weight: {weight}; }}"
            )
            if is_process:
                ind.setFixedSize(8, 16)
                if sis_c:
                    ind.setText("✓")
                    ind.setStyleSheet(_ind_style.format(color=_chk_done_txt, weight=700))
                else:
                    ind.setText(str(idx + 1))
                    _num_clr = "rgba(255,255,255,0.30)" if _locked else _chk_pend_txt
                    ind.setStyleSheet(_ind_style.format(color=_num_clr, weight=600))
            else:
                ind.setFixedSize(8, 14)
                if sis_c:
                    ind.setText("✓")
                    ind.setStyleSheet(_ind_style.format(color=_chk_done_txt, weight=700))
                else:
                    ind.setText("–")
                    ind.setStyleSheet(_ind_style.format(color=_chk_pend_txt, weight=400))
            if clickable:
                ind.setCursor(Qt.CursorShape.PointingHandCursor)
                ind.clicked.connect(chandler)
            elif _locked:
                ind.setCursor(Qt.CursorShape.ForbiddenCursor)
                ind.setToolTip(_lock_reason)

            # Text label
            text_lbl = QLabel(stext)
            text_lbl.setWordWrap(False)
            text_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            if sis_c:
                text_lbl.setStyleSheet(
                    f"color: {_chk_done_txt}; font-size: {_fpt(-1)};"
                    " text-decoration: line-through; background: transparent; border: none;"
                )
            else:
                _txt_clr = "rgba(255,255,255,0.35)" if _locked else _chk_pend_txt
                text_lbl.setStyleSheet(
                    f"color: {_txt_clr}; font-size: {_fpt(-1)}; background: transparent; border: none;"
                )
            if clickable:
                text_lbl.setCursor(Qt.CursorShape.PointingHandCursor)

            item_l.addWidget(ind, 0, Qt.AlignmentFlag.AlignVCenter)
            item_l.addWidget(text_lbl, 1)

            # Whole row clickable (text area → same handler)
            if clickable:
                item_w.setCursor(Qt.CursorShape.PointingHandCursor)

                def _make_handler(h, iw):
                    def _press(ev):
                        if ev.button() == Qt.MouseButton.LeftButton:
                            h()
                        # don't block right-click

                    iw.mousePressEvent = _press

                _make_handler(chandler, item_w)
            elif _locked:
                item_w.setCursor(Qt.CursorShape.ForbiddenCursor)
                item_w.setToolTip(_lock_reason)

            chk_layout.addWidget(item_w)

        # ── Container — 무테두리/무배경, 패널과 자연스럽게 어울림 ──────────
        checklist_container.setStyleSheet("""
            QFrame#ChecklistContainer {
                background: transparent;
                border: none;
                margin-left: 6px;
            }
        """)
        checklist_container.setVisible(is_initially_visible)

        if is_process and tid is not None:
            checklist_container.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

            def _show_ctx_menu(pos, c_tid=tid):
                from PyQt6.QtWidgets import QMenu

                menu = QMenu(checklist_container)
                reset_act = menu.addAction("↺  전체 초기화")
                reset_act.triggered.connect(lambda: app.reset_checklist_items(c_tid))
                menu.exec(checklist_container.mapToGlobal(pos))

            checklist_container.customContextMenuRequested.connect(_show_ctx_menu)

        def toggle_checklist(
            checked=False,
            c_widget=checklist_container,
            t_btn=toggle_btn,
            t_id=tid,
            lbl_fn=_toggle_label,
        ):
            new_visible = not c_widget.isVisible()
            c_widget.setVisible(new_visible)
            t_btn.setText(lbl_fn(new_visible))
            if new_visible:
                if t_id is not None:
                    app.expanded_tids.add(t_id)
            else:
                if t_id is not None:
                    app.expanded_tids.discard(t_id)
            import json as _json

            app.settings.setValue("expanded_task_ids", _json.dumps(list(app.expanded_tids)))

        toggle_btn.clicked.connect(toggle_checklist)

    box_layout.addLayout(top_layout)
    if checklist_items:
        box_layout.addWidget(checklist_container)

    if tid is not None:
        filter_obj = _PanelItemFilter(app, tid, is_directive, main_handler)
        title_btn.installEventFilter(filter_obj)
        container.installEventFilter(filter_obj)
        title_btn._panel_filter = filter_obj
        frames = getattr(
            app, "_panel_directive_frames" if is_directive else "_panel_task_frames", {}
        )
        frames[tid] = (container, bg_color)
        if is_directive:
            app._panel_directive_frames = frames
        else:
            app._panel_task_frames = frames

    return container


def load_left_panel(app):
    app.reset_frame(app.left_frame)

    today_items = []
    panel_mode = _left_panel_mode(app)
    base_date = QDate.currentDate()
    start_qdate = base_date
    end_qdate = base_date
    if panel_mode == "week":
        start_qdate = base_date.addDays(1 - base_date.dayOfWeek())
        end_qdate = start_qdate.addDays(6)

    start_date_str = start_qdate.toString("yyyy-MM-dd")
    end_date_str = end_qdate.toString("yyyy-MM-dd")

    search_query = (
        getattr(app, "search_edit", None).text() if getattr(app, "search_edit", None) else ""
    )
    # Includes schedules whose period overlaps today (middle dates of multi-day schedules too).
    rows = search_repo.get_schedule_tasks_overlapping_range_with_progress(
        start_date_str, end_date_str
    )
    checklist_map = checklist_repo.get_task_checklist_items_for_owners(
        [task["id"] for task in rows]
    )
    left_group_by_date = (
        str(
            getattr(app, "left_group_by_date", app.settings.value("left_group_by_date", "false"))
        ).lower()
        == "true"
    )
    current_group_label = None

    for task in rows:
        t_id = task["id"]
        name = task["name"]
        deadline = task["deadline"]
        priority = task["priority"]
        location = task.get("location")
        assignee = task.get("assignee")
        memo = task.get("memo") or task.get("description")

        if not matches_search_query(search_query, name, location, assignee, memo):
            continue

        deadline_parts = deadline.split()
        date_part = deadline_parts[0] if deadline_parts else start_date_str  # yyyy-MM-dd
        start_time = deadline_parts[1][:5] if len(deadline_parts) > 1 else "All day"

        end_date_raw = task.get("end_date") or task.get("end_time", "")
        end_parts = str(end_date_raw).split() if end_date_raw else []
        end_time = end_parts[1][:5] if len(end_parts) > 1 else ""

        try:
            qd = QDate.fromString(date_part, "yyyy-MM-dd")
            date_label = f"{qd.month()}.{qd.day()} ({_localized_weekday_short(qd)})"
        except Exception:
            date_label = date_part

        icon = priority_icon(priority)

        total = task.get("checklist_total", 0) or 0
        comp = task.get("checklist_completed", 0) or 0
        progress_suffix = ""
        if total > 0:
            progress_suffix = f" ({comp}/{total})"

        main_title = f"{icon} {name}{progress_suffix}"

        def main_handler(checked=False, _tid=t_id):
            app.open_modify_task_dialog(_tid)

        tooltip_name = _tooltip_text_without_tags(name) or str(name).strip()
        tooltip_title = f"[{date_label}] {tooltip_name}"

        # Build tooltip info rows
        info_items = []
        if end_time:
            info_items.append(("[T]", f"{start_time} ~ {end_time}"))
        else:
            info_items.append(("[T]", start_time))
        clean_location = _tooltip_text_without_tags(location)
        if clean_location:
            info_items.append(("[L]", clean_location))

        clean_assignee = _tooltip_text_without_tags(assignee)
        if clean_assignee:
            info_items.append(("[A]", clean_assignee))

        clean_memo = _tooltip_text_without_tags(memo)
        if clean_memo and clean_memo not in ["none", "None", "-"]:
            import html as _html_mod

            _memo_html = _html_mod.escape(clean_memo).replace("\n", "<br>")
            info_items.append(("[M]", _memo_html))

        steps = checklist_map.get(t_id, [])
        checklist_display_type, checklist_items = _build_checklist_items(app, steps)

        if left_group_by_date and date_label != current_group_label:
            current_group_label = date_label
            today_items.append(_schedule_group_header(date_label, "📅"))

        task_box = create_task_box(
            app,
            main_title,
            main_handler,
            info_items,
            checklist_items,
            tid=t_id,
            tooltip_title=tooltip_title,
            bg_color=task.get("bg_color") or _calendar_color_for_task(task),
            checklist_display_type=checklist_display_type,
        )
        today_items.append(task_box)

    if not today_items:
        if panel_mode == "week":
            today_items = [t("panel.empty.week", "No schedules registered for this week.")]
        else:
            today_items = [t("panel.empty.today", "No items for today.")]

    panel_title = (
        t("panel.this_week_schedule", "This Week Schedule")
        if panel_mode == "week"
        else t("panel.today_schedule", "Today's Schedule")
    )
    new_panel, title_bar = create_panel(
        app,
        panel_title,
        today_items,
        add_handler=lambda: app.open_task_dialog(),
        manage_handler=lambda: app.open_work_management_dialog(start_tab="schedule"),
        trailing_widget=_build_left_panel_mode_switch(app, panel_mode),
    )
    apply_dialog_title(app.left_dock, panel_title)
    app.left_dock.setTitleBarWidget(title_bar)
    title_bar.bind_dock(app.left_dock)
    new_layout = QVBoxLayout()
    new_layout.setContentsMargins(0, 0, 0, 0)
    new_layout.addWidget(new_panel)
    app.left_frame.setLayout(new_layout)


def load_right_panel(app):
    app.reset_frame(app.routine_frame)

    app.reset_frame(app.directive_frame)

    routine_items = []
    directive_items = []

    today_str = app.current_date.toString("yyyy-MM-dd")
    search_query = (
        getattr(app, "search_edit", None).text() if getattr(app, "search_edit", None) else ""
    )
    rt_today_rows = search_repo.get_tasks_by_type_with_progress("routine", today_str)
    rt_all_rows = search_repo.get_tasks_by_type_with_progress("routine")

    def _is_completed_routine(row):
        status = str(row.get("status") or "").lower()
        if status in ("done", "completed"):
            return True
        return row.get("is_completed") in (1, True)

    merged_rows = []
    seen_ids = set()
    for row in rt_today_rows:
        rid = row.get("id")
        if rid in seen_ids:
            continue
        seen_ids.add(rid)
        merged_rows.append(row)
    for row in rt_all_rows:
        rid = row.get("id")
        if rid in seen_ids:
            continue
        if not _is_completed_routine(row):
            seen_ids.add(rid)
            merged_rows.append(row)

    routine_status_filter = (
        str(
            getattr(
                app, "routine_status_filter", app.settings.value("routine_status_filter", "all")
            )
        ).lower()
        or "all"
    )
    routine_sort_mode = (
        str(
            getattr(app, "routine_sort_mode", app.settings.value("routine_sort_mode", "deadline"))
        ).lower()
        or "deadline"
    )
    routine_group_by_cycle = (
        str(
            getattr(
                app, "routine_group_by_cycle", app.settings.value("routine_group_by_cycle", "false")
            )
        ).lower()
        == "true"
    )
    routine_group_by_deadline = (
        str(
            getattr(
                app,
                "routine_group_by_deadline",
                app.settings.value("routine_group_by_deadline", "false"),
            )
        ).lower()
        == "true"
    )

    _priority_order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}

    def _routine_sort_key(r):
        cycle_k = cycle_order_value(r.get("cycle_type"), default=9)
        deadline_k = str(
            r.get("period_end") or r.get("deadline") or r.get("target_date") or "9999-12-31"
        )
        if routine_group_by_cycle:
            if routine_sort_mode == "priority":
                return (
                    cycle_k,
                    _priority_order.get(str(r.get("priority") or "normal").lower(), 2),
                    deadline_k,
                    int(r.get("id") or 0),
                )
            else:
                return (cycle_k, deadline_k, int(r.get("id") or 0))
        elif routine_group_by_deadline:
            if routine_sort_mode == "priority":
                return (
                    deadline_k,
                    _priority_order.get(str(r.get("priority") or "normal").lower(), 2),
                    int(r.get("id") or 0),
                )
            else:
                return (deadline_k, int(r.get("id") or 0))
        elif routine_sort_mode == "priority":
            return (
                _priority_order.get(str(r.get("priority") or "normal").lower(), 2),
                deadline_k,
                int(r.get("id") or 0),
            )
        elif routine_sort_mode == "registration":
            return (int(r.get("id") or 0),)
        else:  # deadline (default)
            return (
                0 if str(r.get("target_date") or "")[:10] == today_str else 1,
                deadline_k,
                int(r.get("id") or 0),
            )

    rt_rows = sorted(merged_rows, key=_routine_sort_key)
    routine_checklist_map = checklist_repo.get_task_checklist_items_for_owners(
        [task["id"] for task in rt_rows]
    )

    _cur_routine_group = None
    _cycle_label_map = {
        key: cycle_display_name(key, scope="panel")
        for key in ("daily", "weekly", "monthly", "quarterly", "half_yearly", "yearly", "single")
    }
    _cycle_icon_map = {
        "single": "📋",
        "daily": "☀️",
        "weekly": "🗓️",
        "monthly": "📅",
        "quarterly": "?뱤",
        "half_yearly": "?뱢",
        "yearly": "?룇",
    }

    for r in rt_rows:
        is_today_routine = str(r.get("target_date") or "")[:10] == today_str
        is_completed_r = _is_completed_routine(r)
        _deadline_r = r.get("period_end") or r.get("deadline")
        is_overdue_r = False
        if _deadline_r and not is_completed_r:
            is_overdue_r = str(_deadline_r)[:10] < today_str

        if routine_status_filter == "in_progress":
            if is_completed_r or is_overdue_r:
                continue
        elif routine_status_filter == "overdue":
            if not is_overdue_r:
                continue
        elif routine_status_filter == "completed":
            if not is_completed_r:
                continue
        else:
            if (not is_today_routine) and is_completed_r:
                continue

        rid = r["id"]
        rname = r["name"]
        location = r.get("location")
        assignee = r.get("assignee")
        memo = r.get("memo") or r.get("description")

        if not matches_search_query(search_query, rname, location, assignee, memo):
            continue

        priority = r.get("priority", "normal")
        icon = priority_icon(priority)

        cycle_lab = _cycle_label_map.get(str(r.get("cycle_type") or "").lower(), "")

        period_end = r.get("period_end") or r.get("deadline")
        deadline_suffix = ""
        if period_end:
            try:
                # '2026-03-31' -> '3.31'
                date_part = period_end.split()[0]
                y, m, d = date_part.split("-")
                mm_dd = f"{int(m)}.{int(d)}"
                deadline_suffix = f" (~{mm_dd})"
            except Exception:
                pass

        _cycle_type_str = str(r.get("cycle_type") or "").lower()
        _cycle_prefix = "" if _cycle_type_str == "single" else f"{cycle_lab} "
        main_title = f"{icon} {_cycle_prefix}{rname}{deadline_suffix}"

        def main_handler(checked=False, _rid=rid):
            app.open_modify_task_dialog(_rid)

        info_items = []
        tags_val = r.get("tags") or ""
        if tags_val:
            tag_list = [tg.strip() for tg in tags_val.split(",") if tg.strip()]
            if tag_list:
                info_items.append(("🏷", " · ".join(tag_list)))
        clean_location = _tooltip_text_without_tags(location)
        if clean_location:
            info_items.append((t("common.location", "[L]"), clean_location))
        clean_assignee = _tooltip_text_without_tags(assignee)
        if clean_assignee:
            info_items.append((t("common.assignee", "[A]"), clean_assignee))

        clean_memo = _tooltip_text_without_tags(memo)
        if clean_memo and clean_memo not in ["none", "None", "-"]:
            import html as _html_mod

            _memo_html = _html_mod.escape(clean_memo).replace("\n", "<br>")
            info_items.append((t("common.memo", "📝"), _memo_html))

        steps = routine_checklist_map.get(rid, [])
        checklist_display_type, checklist_items = _build_checklist_items(app, steps)

        routine_tooltip_title = _tooltip_text_without_tags(main_title) or main_title

        # 洹몃９?ㅻ뜑 ?쎌엯 (二쇨린蹂??먮뒗 마감?쇰퀎)
        if routine_group_by_cycle:
            cycle_key = str(r.get("cycle_type") or "other").lower()
            cycle_lbl = _cycle_label_map.get(cycle_key, cycle_key.capitalize())
            cycle_ico = _cycle_icon_map.get(cycle_key, "🔄")
            if cycle_lbl != _cur_routine_group:
                _cur_routine_group = cycle_lbl
                routine_items.append(_routine_group_header(cycle_lbl, cycle_ico))
        elif routine_group_by_deadline:
            _dl_raw = r.get("period_end") or r.get("deadline") or r.get("target_date") or ""
            _dl_date = str(_dl_raw)[:10]
            try:
                _y, _m, _d = _dl_date.split("-")
                _dl_label = f"{int(_m)}.{int(_d)}"
            except Exception:
                _dl_label = _dl_date or t("common.no_deadline", "留덇컧???놁쓬")
            if _dl_label != _cur_routine_group:
                _cur_routine_group = _dl_label
                routine_items.append(_routine_group_header(_dl_label, "📅"))

        task_box = create_task_box(
            app,
            main_title,
            main_handler,
            info_items,
            checklist_items,
            tid=rid,
            is_routine=True,
            tooltip_title=routine_tooltip_title,
            bg_color=r.get("bg_color") or _calendar_color_for_task(r),
            checklist_display_type=checklist_display_type,
        )
        routine_items.append(task_box)

    di_rows = directive_repo.get_recent_directives()
    status_filter = (
        str(
            getattr(
                app, "directive_status_filter", app.settings.value("directive_status_filter", "all")
            )
        ).lower()
        or "all"
    )
    group_by_receiver = (
        str(
            getattr(
                app,
                "directive_group_by_receiver",
                app.settings.value("directive_group_by_receiver", "false"),
            )
        ).lower()
        == "true"
    )
    group_by_deadline = (
        str(
            getattr(
                app,
                "directive_group_by_deadline",
                app.settings.value("directive_group_by_deadline", "false"),
            )
        ).lower()
        == "true"
    )
    sort_mode = (
        getattr(app, "directive_sort_mode", app.settings.value("directive_sort_mode", "deadline"))
        or "deadline"
    )
    today = app.current_date if hasattr(app, "current_date") else QDate.currentDate()

    normalized_rows = []
    for r in di_rows:
        if len(r) == 7:
            did, content, status, receiver, deadline, memo, bg_color = r
        elif len(r) == 6:
            did, content, status, receiver, deadline, memo = r
            bg_color = None
        else:
            did, content, status, receiver, deadline = r
            memo = None
            bg_color = None

        status = _normalized_directive_status(status)
        is_completed = status == "completed"
        is_in_progress = status == "in_progress"
        is_overdue = False
        if deadline and status not in ("completed", "deferred"):
            due = QDate.fromString(str(deadline)[:10], "yyyy-MM-dd")
            is_overdue = due.isValid() and due < today

        if status_filter == "in_progress" and not (is_in_progress and not is_overdue):
            continue
        if status_filter == "overdue" and not is_overdue:
            continue
        if status_filter == "completed" and not is_completed:
            continue
        # status_filter == "all": show everything

        normalized_rows.append(
            (did, content, status, receiver, deadline, memo, bg_color, is_overdue)
        )

    if sort_mode == "deadline":

        def _directive_sort_key(row):
            deadline = row[4] or "9999-12-31"
            receiver = (row[3] or "").strip().lower()
            if group_by_receiver:
                return (receiver or "zzz", deadline, row[0])
            if group_by_deadline:
                return (deadline, receiver, row[0])
            return (deadline, receiver, row[0])

        normalized_rows.sort(key=_directive_sort_key)

    current_receiver = None
    current_deadline_group = None
    for did, content, status, receiver, deadline, memo, bg_color, is_overdue in normalized_rows:
        if not matches_search_query(search_query, content, receiver, memo):
            continue

        if group_by_receiver:
            unspecified = t("dialog.common.unspecified", "Unspecified")
            receiver_label = (receiver or unspecified).strip() or unspecified
            if receiver_label != current_receiver:
                directive_items.append(_directive_group_header(receiver_label))
                current_receiver = receiver_label

        status_ic = status_icon("deferred" if is_overdue and status == "pending" else status)

        di_info = []
        clean_receiver = _tooltip_text_without_tags(receiver)
        if clean_receiver:
            di_info.append((t("common.assignee", "[A]"), clean_receiver))
        clean_memo = _tooltip_text_without_tags(memo)
        if clean_memo and clean_memo not in ["none", "None", "-"]:
            import html as _html_mod

            _memo_html = _html_mod.escape(clean_memo).replace("\n", "<br>")
            di_info.append((t("common.memo", "📝"), _memo_html))

        deadline_part = ""
        if deadline:
            try:
                # deadline format: 'yyyy-MM-dd HH:mm' or 'yyyy-MM-dd'
                parts = str(deadline).split()
                date_str = parts[0]
                _time_str = parts[1] if len(parts) > 1 else ""

                y, m, d = date_str.split("-")
                m = str(int(m))
                d = str(int(d))
                formatted_date = f"{m}.{d}"

                deadline_part = t("panel.deadline_label", "(~{deadline})").replace(
                    "{deadline}", formatted_date
                )

                if group_by_deadline:
                    current_group_label = f"{formatted_date}"
                    if current_group_label != current_deadline_group:
                        directive_items.append(_deadline_group_header(current_group_label))
                        current_deadline_group = current_group_label
            except Exception:
                deadline_part = f" (~{str(deadline).split()[0]})"

        display_text = f"{status_ic} {content}{deadline_part}"

        def handler(checked=False, _did=did):
            app.open_directive_dialog(_did)

        directive_tooltip_title = _tooltip_text_without_tags(display_text) or display_text
        directive_items.append(
            create_task_box(
                app,
                display_text,
                handler,
                info_items=di_info,
                tid=did,
                is_directive=True,
                tooltip_title=directive_tooltip_title,
                bg_color=bg_color,
            )
        )

    if not routine_items:
        routine_items = [t("panel.empty.routine", "No routine tasks found.")]

    if not directive_items:
        directive_items = [t("panel.empty.directive", "No directions found.")]

    panel_1, title_bar_1 = create_panel(
        app,
        t("panel.routine", "Routine Tasks"),
        routine_items,
        add_handler=lambda: app.open_routine_add_dialog(),
        manage_handler=lambda: app.open_work_management_dialog(start_tab="routine"),
    )
    app.routine_dock.setTitleBarWidget(title_bar_1)
    title_bar_1.bind_dock(app.routine_dock)

    panel_2, title_bar_2 = create_panel(
        app,
        t("panel.directive", "Directions"),
        directive_items,
        add_handler=lambda: app.open_directive_dialog(),
        manage_handler=lambda: app.open_work_management_dialog(start_tab="directive"),
    )
    app.directive_dock.setTitleBarWidget(title_bar_2)
    title_bar_2.bind_dock(app.directive_dock)

    lay1 = QVBoxLayout()
    lay1.setContentsMargins(0, 0, 0, 0)
    lay1.addWidget(panel_1)
    app.routine_frame.setLayout(lay1)

    lay2 = QVBoxLayout()
    lay2.setContentsMargins(0, 0, 0, 0)
    lay2.addWidget(panel_2)
    app.directive_frame.setLayout(lay2)
