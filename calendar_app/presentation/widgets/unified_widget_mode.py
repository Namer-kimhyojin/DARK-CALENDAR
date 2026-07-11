# -*- coding: utf-8 -*-
from PyQt6.QtCore import QDate, QLocale, QPoint, QSize, Qt, QTime, QTimer, pyqtSignal
from PyQt6.QtGui import QContextMenuEvent
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.panel_widget_mode import (
    _format_compact_date_with_weekday,
    _format_widget_datetime_label,
    _normalize_status,
    _parse_qdate,
    _parse_quick_add_text,
    _resolve_widget_mode_tokens,
)
from calendar_app.presentation.widgets.panel_widget_theme import (
    _apply_configured_widget_color,
    _apply_registered_widget_mode_skin,
    _widget_mode_menu_stylesheet,
)
from calendar_app.presentation.widgets.widget_mode_skins import (
    get_widget_mode_layout,
    read_widget_mode_layout_id,
    read_widget_mode_skin_id,
    widget_mode_layouts,
    widget_mode_skins,
    write_widget_mode_layout_id,
    write_widget_mode_skin_id,
)


def _safe_text(value) -> str:
    return str(value or "").strip()


def _widget_theme_tokens(host: QWidget) -> dict[str, str]:
    tokens = _resolve_widget_mode_tokens(app=host)
    settings = getattr(host, "settings", None)
    tokens = _apply_registered_widget_mode_skin(tokens, settings)
    return _apply_configured_widget_color(tokens, settings)


def _relative_widget_day(date: QDate) -> str:
    if not isinstance(date, QDate) or not date.isValid():
        return t("widget_mode.today", "Today")
    today = QDate.currentDate()
    delta = today.daysTo(date)
    if delta == 0:
        return t("widget_mode.today", "Today")
    if delta == 1:
        return t("widget_mode.tomorrow", "Tomorrow")
    if delta == -1:
        return t("widget_mode.yesterday", "Yesterday")
    return _format_compact_date_with_weekday(date)


def _unified_widget_stylesheet(tokens: dict[str, str]) -> str:
    tk = tokens
    return f"""
        QFrame#unified_container {{
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 1,
                stop: 0 {tk.get("panel_bg_start", tk["panel_bg"])},
                stop: 0.48 {tk.get("panel_bg_mid", tk["panel_bg"])},
                stop: 1 {tk.get("panel_bg_end", tk["panel_bg"])}
            );
            border: 1px solid {tk.get("panel_border", "rgba(255,255,255,22)")};
            border-radius: 28px;
        }}
        QFrame#unified_hero {{
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 0,
                stop: 0 {tk.get("header_shell_bg", tk["surface_bg"])},
                stop: 1 {tk.get("surface_alt", tk["section_bg"])}
            );
            border: 1px solid {tk.get("header_shell_border", tk.get("panel_border_soft", "rgba(255,255,255,16)"))};
            border-radius: 22px;
        }}
        QFrame#unified_filter_section,
        QFrame#unified_agenda_section {{
            background: transparent;
            border: none;
        }}
        QFrame#unified_container[widgetLayout="dashboard"] QFrame#unified_agenda_section,
        QFrame#unified_container[widgetLayout="magazine"] QFrame#unified_agenda_section {{
            background: {tk.get("card_bg", tk["section_bg"])};
            border: 1px solid {tk.get("card_border", tk.get("panel_border_soft", tk["panel_border"]))};
            border-radius: 20px;
        }}
        QFrame#unified_container[widgetLayout="agenda_first"] QFrame#unified_agenda_section,
        QFrame#unified_container[widgetLayout="minimal"] QFrame#unified_agenda_section {{
            background: {tk.get("section_bg", tk["surface_bg"])};
            border: 1px solid {tk.get("section_border_soft", tk.get("panel_border_soft", tk["panel_border"]))};
            border-radius: 18px;
        }}
        QFrame#unified_container[widgetLayout="dashboard"] QWidget#unified_calendar_section,
        QFrame#unified_container[widgetLayout="magazine"] QWidget#unified_calendar_section,
        QFrame#unified_container[widgetLayout="agenda_first"] QWidget#unified_calendar_section {{
            background: {tk.get("surface_alt", tk["section_bg"])};
            border: 1px solid {tk.get("section_border_soft", tk.get("panel_border_soft", tk["panel_border"]))};
            border-radius: 18px;
        }}
        QFrame#unified_container[widgetLayout="dashboard"] QFrame#unified_filter_section,
        QFrame#unified_container[widgetLayout="magazine"] QFrame#unified_filter_section,
        QFrame#unified_container[widgetLayout="minimal"] QFrame#unified_filter_section {{
            background: {tk.get("hero_bg", tk["section_bg"])};
            border: 1px solid {tk.get("hero_border", tk.get("panel_border_soft", tk["panel_border"]))};
            border-radius: 16px;
        }}
        QFrame#unified_container[widgetLayout="minimal"] QFrame#unified_hero {{
            border-radius: 18px;
        }}
        QLabel#unified_eyebrow {{
            color: {tk.get("text_faint", tk["text_secondary"])};
            font-size: 8pt;
            font-weight: 800;
            letter-spacing: 1.7px;
            background: transparent;
        }}
        QLabel#unified_clock {{
            color: {tk.get("text_primary", "#ffffff")};
            font-size: 27pt;
            font-weight: 800;
            letter-spacing: -0.8px;
            background: transparent;
        }}
        QLabel#unified_date {{
            color: {tk.get("text_primary", "#ffffff")};
            font-size: 10.4pt;
            font-weight: 700;
            letter-spacing: 0.2px;
            background: transparent;
        }}
        QLabel#unified_caption {{
            color: {tk.get("text_faint", tk["text_secondary"])};
            font-size: 8.7pt;
            font-weight: 500;
            letter-spacing: 0.1px;
            background: transparent;
        }}
        QToolButton#unified_action_btn,
        QToolButton#unified_primary_action,
        QToolButton#unified_filter_btn {{
            color: {tk.get("button_text", tk["text_secondary"])};
            background: {tk.get("button_bg", tk["section_bg"])};
            border: 1px solid {tk.get("section_border_soft", tk.get("panel_border_soft", "rgba(255,255,255,14)"))};
            border-radius: 14px;
            padding: 7px 12px;
            font-size: 8.8pt;
            font-weight: 700;
            letter-spacing: 0.2px;
        }}
        QToolButton#unified_action_btn:hover,
        QToolButton#unified_filter_btn:hover {{
            color: {tk.get("text_primary", "#ffffff")};
            background: {tk.get("button_hover", tk["section_bg_alt"])};
            border: 1px solid {tk.get("hero_border", tk["panel_border"])};
        }}
        QToolButton#unified_filter_btn {{
            border-radius: 12px;
            padding: 5px 11px;
            font-size: 8.1pt;
        }}
        QToolButton#unified_filter_btn:checked {{
            color: {tk.get("accent_deep", tk.get("text_primary", "#ffffff"))};
            background: {tk.get("chip_bg", tk.get("hero_bg", tk["section_bg"]))};
            border: 1px solid {tk.get("chip_border", tk.get("hero_border", tk["panel_border"]))};
        }}
        QToolButton#unified_primary_action {{
            color: {tk.get("button_primary_text", tk.get("accent_deep", tk["text_primary"]))};
            background: {tk.get("button_primary_bg", tk.get("hero_bg", tk["section_bg"]))};
            border: 1px solid {tk.get("button_primary_border", tk.get("hero_border", tk["panel_border"]))};
        }}
        QToolButton#unified_primary_action:hover {{
            color: {tk.get("button_primary_hover_text", tk.get("text_primary", "#ffffff"))};
            background: {tk.get("button_primary_hover_bg", tk.get("hero_bg_strong", tk["section_bg_alt"]))};
            border: 1px solid {tk.get("button_primary_hover_border", tk.get("hero_border", tk["panel_border"]))};
        }}
        QLabel#unified_chip,
        QLabel#unified_chip_accent {{
            border-radius: 12px;
            padding: 3px 9px;
            font-size: 7.8pt;
            font-weight: 700;
            letter-spacing: 0.8px;
        }}
        QLabel#unified_chip {{
            color: {tk.get("text_secondary", "#c0cade")};
            background: {tk.get("surface_alt", tk["section_bg"])};
            border: 1px solid {tk.get("section_border_soft", tk.get("panel_border_soft", "rgba(255,255,255,14)"))};
        }}
        QLabel#unified_chip_accent {{
            color: {tk.get("accent_deep", tk["text_primary"])};
            background: {tk.get("chip_bg", tk.get("hero_bg", tk["section_bg"]))};
            border: 1px solid {tk.get("chip_border", tk.get("hero_border", tk["panel_border"]))};
        }}
        QLabel#unified_hint {{
            color: {tk.get("text_faint", tk["text_secondary"])};
            font-size: 8.3pt;
            font-weight: 500;
            letter-spacing: 0.1px;
            background: transparent;
        }}
        QLabel#unified_section {{
            color: {tk.get("accent_deep", tk["text_secondary"])};
            font-size: 7.4pt;
            font-weight: 800;
            letter-spacing: 1.7px;
            background: transparent;
            padding: 2px 0 4px 2px;
        }}
        QLabel#unified_empty {{
            color: {tk.get("text_faint", tk["text_secondary"])};
            font-size: 9pt;
            font-weight: 500;
            background: transparent;
            padding: 10px 2px;
        }}
        QFrame#agenda_item_schedule,
        QFrame#agenda_item_task {{
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 1,
                stop: 0 {tk.get("card_bg", tk["section_bg"])},
                stop: 1 {tk.get("surface_alt", tk["section_bg_alt"])}
            );
            border: 1px solid {tk.get("card_border", tk.get("section_border_soft", "rgba(255,255,255,14)"))};
            border-radius: 18px;
        }}
        QFrame#agenda_item_marker_schedule {{
            background: {tk.get("accent_deep", tk.get("accent", "#4da6ff"))};
            border-radius: 5px;
        }}
        QFrame#agenda_item_marker_task {{
            background: {tk.get("hero_bg_strong", tk["section_bg_alt"])};
            border: 1px solid {tk.get("hero_border", tk["panel_border"])};
            border-radius: 5px;
        }}
        QLabel#agenda_item_title {{
            color: {tk.get("card_text_primary", tk["text_primary"])};
            font-size: 9.6pt;
            font-weight: 700;
            background: transparent;
        }}
        QLabel#agenda_item_meta {{
            color: {tk.get("card_text_secondary", tk["text_secondary"])};
            font-size: 8pt;
            font-weight: 500;
            background: transparent;
        }}
        QLabel#agenda_item_time {{
            color: {tk.get("accent_deep", tk["text_primary"])};
            background: {tk.get("chip_bg", tk.get("hero_bg", tk["section_bg"]))};
            border: 1px solid {tk.get("chip_border", tk.get("hero_border", tk["panel_border"]))};
            border-radius: 10px;
            padding: 3px 9px;
            font-size: 7.8pt;
            font-weight: 700;
            background-clip: padding;
        }}
        QScrollArea#unified_scroll,
        QWidget#unified_scroll_viewport,
        QWidget#unified_scroll_content {{
            background: transparent;
            border: none;
        }}
        QScrollBar:vertical {{
            background: {tk.get("scroll_track", "transparent")};
            width: 10px;
            border-radius: 5px;
            margin: 2px 0;
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
    """


class AgendaItemWidget(QFrame):
    def __init__(self, title: str, time_text: str, *, is_task: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("agenda_item_task" if is_task else "agenda_item_schedule")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        marker = QFrame(self)
        marker.setObjectName(
            "agenda_item_marker_task" if is_task else "agenda_item_marker_schedule"
        )
        marker.setFixedSize(10, 10)
        layout.addWidget(marker, 0, Qt.AlignmentFlag.AlignTop)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(3)
        layout.addLayout(body, 1)

        title_label = QLabel(title, self)
        title_label.setObjectName("agenda_item_title")
        title_label.setWordWrap(True)
        title_label.setToolTip(title)
        body.addWidget(title_label)

        meta_label = QLabel(
            t("widget_mode.task_type", "Work")
            if is_task
            else t("widget_mode.schedule_type", "Schedule"),
            self,
        )
        meta_label.setObjectName("agenda_item_meta")
        body.addWidget(meta_label)

        time_label = QLabel(_safe_text(time_text), self)
        time_label.setObjectName("agenda_item_time")
        time_label.setVisible(bool(_safe_text(time_text)))
        layout.addWidget(time_label, 0, Qt.AlignmentFlag.AlignTop)


class CompactCalendarGrid(QWidget):
    dateClicked = pyqtSignal(QDate)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tokens: dict[str, str] = {}
        self._buttons = []
        self._last_render_state = None
        self.setObjectName("unified_calendar_section")
        self._root_layout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(6)

        self._row_layout = QHBoxLayout()
        self._row_layout.setSpacing(6)
        self._root_layout.addLayout(self._row_layout)

        for index in range(7):
            button = QToolButton(self)
            button.setObjectName("unified_day_btn")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedSize(42, 54)
            button.clicked.connect(lambda _checked=False, idx=index: self._emit_clicked(idx))
            self._row_layout.addWidget(button)
            self._buttons.append(button)

        self._dates = []
        self.update_grid()

    def apply_layout_metrics(
        self,
        *,
        cell_size: tuple[int, int],
        spacing: int,
        margins: tuple[int, int, int, int],
    ) -> None:
        width, height = cell_size
        for button in self._buttons:
            button.setFixedSize(max(30, width), max(38, height))
        self._row_layout.setSpacing(max(0, spacing))
        self._root_layout.setContentsMargins(*margins)

    def set_theme_tokens(self, tokens: dict[str, str]) -> None:
        normalized = dict(tokens or {})
        if normalized == self._tokens:
            return
        self._tokens = normalized
        self._last_render_state = None

    def _button_stylesheet(self, day: QDate, today: QDate, selected: QDate) -> str:
        tk = self._tokens or {
            "surface_alt": "rgba(24, 26, 34, 180)",
            "section_border_soft": "rgba(255,255,255,14)",
            "button_hover": "rgba(255,255,255,12)",
            "text_secondary": "#b0b8d0",
            "text_primary": "#f4f7ff",
            "hero_bg": "rgba(34,195,202,20)",
            "hero_bg_strong": "rgba(34,195,202,40)",
            "hero_border": "rgba(34,195,202,110)",
            "accent_deep": "#22c3ca",
        }
        border = tk.get("section_border_soft", "rgba(255,255,255,14)")
        background = tk.get("surface_alt", "rgba(24, 26, 34, 180)")
        text = tk.get("text_secondary", "#b0b8d0")
        weight = "600"
        if day == today:
            border = tk.get("hero_border", border)
            background = tk.get("hero_bg", background)
            text = tk.get("text_primary", "#ffffff")
        if day == selected:
            border = tk.get("hero_border", border)
            background = (
                "qlineargradient("
                "x1: 0, y1: 0, x2: 1, y2: 1,"
                f"stop: 0 {tk.get('hero_bg_strong', background)},"
                f"stop: 1 {tk.get('section_bg_alt', background)}"
                ")"
            )
            text = tk.get("accent_deep", tk.get("text_primary", "#ffffff"))
            weight = "800"
        return (
            "QToolButton {"
            f"background: {background};"
            f"border: 1px solid {border};"
            "border-radius: 14px;"
            f"color: {text};"
            "font-size: 9.4pt;"
            f"font-weight: {weight};"
            "padding: 5px 0 6px 0;"
            "}"
            "QToolButton:hover {"
            f"background: {tk.get('button_hover', tk.get('section_bg_alt', 'rgba(255, 255, 255, 12)'))};"
            "}"
        )

    def _emit_clicked(self, index: int) -> None:
        if 0 <= index < len(self._dates):
            date = self._dates[index]
            if isinstance(date, QDate) and date.isValid():
                self.dateClicked.emit(date)

    def update_grid(self, selected_date: QDate | None = None) -> None:
        selected = (
            selected_date
            if isinstance(selected_date, QDate) and selected_date.isValid()
            else QDate.currentDate()
        )
        today = QDate.currentDate()
        week_start = selected.addDays(1 - selected.dayOfWeek())
        locale = QLocale()
        state = (
            selected.toString("yyyy-MM-dd"),
            today.toString("yyyy-MM-dd"),
            week_start.toString("yyyy-MM-dd"),
            locale.name(),
        )
        if state == self._last_render_state:
            return
        self._last_render_state = state

        self._dates = []
        for offset, button in enumerate(self._buttons):
            day = week_start.addDays(offset)
            self._dates.append(day)
            weekday = locale.dayName(
                day.dayOfWeek(), QLocale.FormatType.ShortFormat
            ).strip() or day.toString("ddd")
            button.setText(f"{weekday}\n{day.day()}")
            button.setStyleSheet(self._button_stylesheet(day, today, selected))


class UnifiedWidgetWindow(QWidget):
    def __init__(self, controller):
        super().__init__(None)
        self.controller = controller
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(360, 560)
        self._last_render_key = None
        self._last_items = []
        self._last_today = QDate.currentDate()
        self._style_signature = None
        self._active_layout_id = ""
        self._active_filter = "all"
        self._filter_buttons: dict[str, QToolButton] = {}

        self._build_ui()
        self._setup_refresh_timer()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        self.container = QFrame(self)
        self.container.setObjectName("unified_container")
        self.container_layout = QGridLayout(self.container)

        self.hero = QFrame(self.container)
        self.hero.setObjectName("unified_hero")
        self.hero_layout = QVBoxLayout(self.hero)
        self.hero_layout.setContentsMargins(16, 16, 16, 16)
        self.hero_layout.setSpacing(12)

        self.eyebrow_label = QLabel(t("widget_mode.hero_eyebrow", "FOCUS WIDGET"), self.hero)
        self.eyebrow_label.setObjectName("unified_eyebrow")
        self.hero_layout.addWidget(self.eyebrow_label)

        header = QHBoxLayout()
        header.setSpacing(10)
        self.hero_layout.addLayout(header)

        self.clock_label = QLabel(QTime.currentTime().toString("HH:mm"), self.hero)
        self.clock_label.setObjectName("unified_clock")
        header.addWidget(self.clock_label, 0, Qt.AlignmentFlag.AlignTop)

        date_box = QVBoxLayout()
        date_box.setContentsMargins(0, 2, 0, 0)
        date_box.setSpacing(2)
        self.date_label = QLabel("", self.hero)
        self.date_label.setObjectName("unified_date")
        self.caption_label = QLabel("", self.hero)
        self.caption_label.setObjectName("unified_caption")
        date_box.addWidget(self.date_label)
        date_box.addWidget(self.caption_label)
        header.addLayout(date_box, 1)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        header.addLayout(actions)

        self.today_btn = QToolButton(self.hero)
        self.today_btn.setObjectName("unified_action_btn")
        self.today_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.today_btn.clicked.connect(lambda: self.controller.set_target_date(QDate.currentDate()))
        actions.addWidget(self.today_btn)

        self.add_btn = QToolButton(self.hero)
        self.add_btn.setObjectName("unified_primary_action")
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.clicked.connect(self.controller.open_quick_add_dialog)
        actions.addWidget(self.add_btn)

        info_row = QHBoxLayout()
        info_row.setSpacing(6)
        self.hero_layout.addLayout(info_row)

        self.status_chip = QLabel("", self.hero)
        self.status_chip.setObjectName("unified_chip_accent")
        info_row.addWidget(self.status_chip)

        self.count_chip = QLabel("", self.hero)
        self.count_chip.setObjectName("unified_chip")
        info_row.addWidget(self.count_chip)

        self.hint_label = QLabel("", self.hero)
        self.hint_label.setObjectName("unified_hint")
        info_row.addWidget(self.hint_label, 1)

        self.cal_grid = CompactCalendarGrid(self)
        self.cal_grid.dateClicked.connect(self.controller.set_target_date)

        self.filter_section = QFrame(self.container)
        self.filter_section.setObjectName("unified_filter_section")
        self.filter_row = QHBoxLayout(self.filter_section)
        self.filter_row.setContentsMargins(0, 0, 0, 0)
        self.filter_row.setSpacing(6)

        for mode, label in (
            ("all", t("widget_mode.filter_all", "All")),
            ("schedule", t("widget_mode.filter_schedule", "Schedule")),
            ("work", t("widget_mode.filter_work", "Work")),
        ):
            btn = QToolButton(self.container)
            btn.setObjectName("unified_filter_btn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setText(label)
            btn.clicked.connect(lambda _checked=False, m=mode: self._set_filter(m))
            self.filter_row.addWidget(btn)
            self._filter_buttons[mode] = btn
        self.filter_row.addStretch(1)

        self.agenda_section = QFrame(self.container)
        self.agenda_section.setObjectName("unified_agenda_section")
        self.agenda_layout = QVBoxLayout(self.agenda_section)
        self.agenda_layout.setContentsMargins(0, 0, 0, 0)
        self.agenda_layout.setSpacing(8)

        self.agenda_header = QLabel(t("widget_mode.focus_list", "FOCUS LIST"), self.agenda_section)
        self.agenda_header.setObjectName("unified_section")
        self.agenda_layout.addWidget(self.agenda_header)

        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("unified_scroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.viewport().setObjectName("unified_scroll_viewport")
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("unified_scroll_content")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(8)
        self.scroll_layout.addStretch()
        self.scroll.setWidget(self.scroll_content)
        self.agenda_layout.addWidget(self.scroll, 1)

        main_layout.addWidget(self.container)
        self.apply_selected_layout(resize_to_layout=True)
        self.apply_theme()
        self._sync_filter_buttons()

    def active_layout_id(self) -> str:
        return self._active_layout_id

    def apply_selected_layout(self, *, resize_to_layout: bool = False, force: bool = False) -> None:
        settings = self.controller.main_window.settings
        layout_spec = get_widget_mode_layout(read_widget_mode_layout_id(settings))
        if self._active_layout_id == layout_spec.layout_id and not force:
            return

        sections = {
            "hero": self.hero,
            "calendar": self.cal_grid,
            "filters": self.filter_section,
            "agenda": self.agenda_section,
        }
        for section in sections.values():
            self.container_layout.removeWidget(section)
            section.setVisible(False)
        for index in range(8):
            self.container_layout.setRowStretch(index, 0)
            self.container_layout.setColumnStretch(index, 0)

        self.container_layout.setContentsMargins(*layout_spec.content_margins)
        self.container_layout.setHorizontalSpacing(layout_spec.spacing)
        self.container_layout.setVerticalSpacing(layout_spec.spacing)
        for section_name, row, column, row_span, column_span in layout_spec.placements:
            section = sections[section_name]
            self.container_layout.addWidget(section, row, column, row_span, column_span)
            section.setVisible(True)
        for row, stretch in layout_spec.row_stretches:
            self.container_layout.setRowStretch(row, stretch)
        for column, stretch in layout_spec.column_stretches:
            self.container_layout.setColumnStretch(column, stretch)

        self.hero_layout.setContentsMargins(*layout_spec.hero_margins)
        self.hero_layout.setSpacing(layout_spec.hero_spacing)
        self.filter_row.setContentsMargins(*layout_spec.filter_margins)
        self.filter_row.setSpacing(layout_spec.filter_spacing)
        self.agenda_layout.setContentsMargins(*layout_spec.agenda_margins)
        self.agenda_layout.setSpacing(layout_spec.agenda_spacing)
        self.scroll_layout.setSpacing(max(5, layout_spec.agenda_spacing))
        self.cal_grid.apply_layout_metrics(
            cell_size=layout_spec.calendar_cell_size,
            spacing=layout_spec.calendar_spacing,
            margins=layout_spec.calendar_margins,
        )
        self.eyebrow_label.setVisible(layout_spec.show_eyebrow)
        self.hint_label.setVisible(layout_spec.show_hint)

        self._active_layout_id = layout_spec.layout_id
        self.container.setProperty("widgetLayout", layout_spec.layout_id)
        if resize_to_layout:
            self.resize(self.controller.saved_size_for_layout(layout_spec))
        self.container.updateGeometry()
        self.updateGeometry()

    def apply_skin_layout(self, *, resize_to_layout: bool = False, force: bool = False) -> None:
        """Compatibility shim for callers from the initial combined skin/layout rollout."""
        self.apply_selected_layout(resize_to_layout=resize_to_layout, force=force)

    def apply_theme(self) -> None:
        tokens = _widget_theme_tokens(self.controller.main_window)
        signature = tuple(sorted(tokens.items()))
        if signature == self._style_signature:
            return
        self._style_signature = signature
        self.container.setStyleSheet(_unified_widget_stylesheet(tokens))
        self.cal_grid.set_theme_tokens(tokens)
        self.cal_grid.update_grid(self.controller._current_date())
        self._refresh_locale_texts()

    def _sync_filter_buttons(self) -> None:
        for mode, btn in self._filter_buttons.items():
            btn.setChecked(mode == self._active_filter)

    def _set_filter(self, mode: str) -> None:
        target = str(mode or "all").strip().lower()
        if target not in {"all", "schedule", "work"}:
            target = "all"
        if target == self._active_filter:
            self._sync_filter_buttons()
            return
        self._active_filter = target
        self._sync_filter_buttons()
        self._last_render_key = None
        self.update_agenda(self._last_items)

    def _filter_items(self, items: list[dict[str, object]]) -> list[dict[str, object]]:
        if self._active_filter == "all":
            return [dict(item) for item in items]

        filtered: list[dict[str, object]] = []
        active_section: dict[str, object] | None = None
        buffered_items: list[dict[str, object]] = []

        for item in items:
            if item.get("is_section"):
                if active_section is not None and buffered_items:
                    filtered.append(dict(active_section))
                    filtered.extend(dict(entry) for entry in buffered_items)
                active_section = dict(item)
                buffered_items = []
                continue

            item_kind = _safe_text(item.get("item_kind")).lower()
            include = (self._active_filter == "schedule" and item_kind == "schedule") or (
                self._active_filter == "work" and item_kind == "work"
            )
            if include:
                buffered_items.append(dict(item))

        if active_section is not None and buffered_items:
            filtered.append(dict(active_section))
            filtered.extend(dict(entry) for entry in buffered_items)

        return filtered

    def _setup_refresh_timer(self) -> None:
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.update_time)

    def _ms_until_next_clock_tick(self) -> int:
        current = QTime.currentTime()
        remaining = 60000 - (current.msecsSinceStartOfDay() % 60000)
        return max(1000, int(remaining or 60000))

    def _schedule_next_clock_tick(self) -> None:
        if self.isVisible():
            self.timer.start(self._ms_until_next_clock_tick())

    def _refresh_locale_texts(self) -> None:
        self.eyebrow_label.setText(t("widget_mode.hero_eyebrow", "집중 위젯"))
        self.today_btn.setText(t("widget_mode.today", "오늘"))
        self.today_btn.setToolTip(t("widget_mode.today", "오늘"))
        self.add_btn.setText(t("widget_mode.add_short", "새 일정"))
        self.add_btn.setToolTip(t("widget_mode.action_add_schedule", "일정 추가"))
        labels = {
            "all": t("widget_mode.filter_all", "전체"),
            "schedule": t("widget_mode.filter_schedule", "일정"),
            "work": t("widget_mode.filter_work", "업무"),
        }
        for mode, btn in self._filter_buttons.items():
            btn.setText(labels.get(mode, labels["all"]))
        self.update_header(self.controller._current_date())
        self.update_agenda(self._last_items)

    def _clear_items(self) -> None:
        while self.scroll_layout.count() > 1:
            item = self.scroll_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def update_header(self, target_date: QDate) -> None:
        label = _format_compact_date_with_weekday(target_date)
        self.date_label.setText(label)
        self.caption_label.setText(t("widget_mode.header_caption", "Selected day agenda and work"))
        self.status_chip.setText(_relative_widget_day(target_date))
        self.cal_grid.update_grid(target_date)

    def update_agenda(self, items: list[dict[str, object]]) -> None:
        self._last_items = [dict(item) for item in items]
        filtered_items = self._filter_items(self._last_items)
        render_key = tuple(
            [self._active_filter]
            + [tuple(sorted(item.items(), key=lambda pair: pair[0])) for item in filtered_items]
        )
        if self._last_render_key == render_key:
            return
        self._last_render_key = render_key
        visible_items = [item for item in filtered_items if not item.get("is_section")]
        total_items = [item for item in self._last_items if not item.get("is_section")]
        if self._active_filter == "all":
            self.count_chip.setText(
                t("widget_mode.item_count_chip", "{count} items", count=len(visible_items))
            )
            self.agenda_header.setText(t("widget_mode.focus_list", "FOCUS LIST"))
        else:
            self.count_chip.setText(
                t(
                    "widget_mode.filtered_count_chip",
                    "{count}/{total}",
                    count=len(visible_items),
                    total=len(total_items),
                )
            )
            self.agenda_header.setText(
                t("widget_mode.filter_schedule", "Schedule")
                if self._active_filter == "schedule"
                else t("widget_mode.filter_work", "Work")
            )
        self.hint_label.setText(
            t("widget_mode.widget_hint_actions", "Tap a day to refocus")
            if visible_items
            else t("widget_mode.widget_hint_empty", "No items for the selected date.")
        )

        self._clear_items()
        if not filtered_items:
            empty_text = (
                t("widget_mode.empty_schedule_filter", "No schedules for this date.")
                if self._active_filter == "schedule"
                else t("widget_mode.empty_work_filter", "No work for this date.")
                if self._active_filter == "work"
                else t("widget_mode.empty_panel", "No items for this date.")
            )
            empty = QLabel(empty_text, self.scroll_content)
            empty.setWordWrap(True)
            empty.setObjectName("unified_empty")
            self.scroll_layout.insertWidget(0, empty)
            return

        for insert_at, item in enumerate(filtered_items):
            if item.get("is_section"):
                section = QLabel(_safe_text(item.get("title")), self.scroll_content)
                section.setObjectName("unified_section")
                self.scroll_layout.insertWidget(insert_at, section)
            else:
                widget = AgendaItemWidget(
                    _safe_text(item.get("title")) or t("widget_mode.untitled", "Untitled"),
                    _safe_text(item.get("time")),
                    is_task=bool(item.get("is_task")),
                    parent=self.scroll_content,
                )
                self.scroll_layout.insertWidget(insert_at, widget)

    def showEvent(self, event):
        super().showEvent(event)
        self.apply_theme()
        self.update_time()
        self.controller.refresh_data()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.timer.stop()

    def update_time(self) -> None:
        current_text = QTime.currentTime().toString("HH:mm")
        if self.clock_label.text() != current_text:
            self.clock_label.setText(current_text)
        today = QDate.currentDate()
        if today != self._last_today and self.isVisible():
            self._last_today = today
            self.controller.refresh_data()
        self._schedule_next_clock_tick()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_start)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.controller.save_position(self.pos())
            event.accept()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        tokens = _widget_theme_tokens(self.controller.main_window)
        menu = QMenu(self)
        menu.setStyleSheet(_widget_mode_menu_stylesheet(tokens))

        layout_menu = menu.addMenu(t("widget_mode.style_layout", "레이아웃"))
        current_layout = read_widget_mode_layout_id(self.controller.main_window.settings)
        for layout_spec in widget_mode_layouts():
            action = layout_menu.addAction(t(layout_spec.label_key, layout_spec.label_default))
            action.setCheckable(True)
            action.setChecked(current_layout == layout_spec.layout_id)
            action.triggered.connect(
                lambda _checked=False, selected=layout_spec.layout_id: self.controller.set_layout(
                    selected
                )
            )

        skin_menu = menu.addMenu(t("widget_mode.style_color_skin", "색상 스킨"))
        current_skin = read_widget_mode_skin_id(self.controller.main_window.settings)
        for skin in widget_mode_skins():
            action = skin_menu.addAction(t(skin.label_key, skin.label_default))
            action.setCheckable(True)
            action.setChecked(current_skin == skin.skin_id)
            action.triggered.connect(
                lambda _checked=False, selected=skin.skin_id: self.controller.set_skin(selected)
            )

        menu.addSeparator()
        refresh_action = menu.addAction(t("widget_mode.menu_refresh", "새로고침"))
        close_action = menu.addAction(t("widget_mode.close", "위젯 닫기"))
        selected = menu.exec(event.globalPos())
        if selected == refresh_action:
            self.controller.force_refresh()
        elif selected == close_action:
            self.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.isMinimized() and self.isVisible():
            self.controller.save_size(self.size())


class UnifiedWidgetController:
    POSITION_KEY = "unified_widget_pos"
    SIZE_KEY = "unified_widget_size"

    def __init__(self, main_window):
        self.main_window = main_window
        self.widget = None
        self._cache_refresh_pending = False
        self._last_display_signature = None
        self._items_cache = {}

    def _current_date(self) -> QDate:
        target = getattr(self.main_window, "current_date", None)
        if isinstance(target, QDate) and target.isValid():
            return target
        return QDate.currentDate()

    def _sync_main_context_date(self, target: QDate) -> None:
        if isinstance(target, QDate) and target.isValid():
            self.main_window.current_date = target

    def _cache_bounds(self, cache) -> tuple[QDate, QDate]:
        if not isinstance(cache, dict):
            return QDate(), QDate()
        return _parse_qdate(cache.get("range_start")), _parse_qdate(cache.get("range_end"))

    def _cache_covers_date(self, cache, target: QDate) -> bool:
        if not isinstance(target, QDate) or not target.isValid():
            return False
        start, end = self._cache_bounds(cache)
        return start.isValid() and end.isValid() and start <= target <= end

    def _directive_cache_matches_date(self, target: QDate) -> bool:
        cache = getattr(self.main_window, "_latest_directive_data", None)
        if not isinstance(cache, dict):
            return False
        context_date = _parse_qdate(cache.get("context_date"))
        return context_date.isValid() and context_date == target

    def toggle_widget(self):
        if self.widget and self.widget.isVisible():
            self.widget.hide()
            return

        if not self.widget:
            self.widget = UnifiedWidgetWindow(self)
            stored_pos = self.main_window.settings.value(self.POSITION_KEY)
            if isinstance(stored_pos, QPoint):
                self.widget.move(stored_pos)
            else:
                screen = QApplication.primaryScreen().availableGeometry()
                self.widget.move(screen.right() - self.widget.width() - 40, 40)

        self.widget.show()

    def save_position(self, pos: QPoint) -> None:
        self.main_window.settings.setValue(self.POSITION_KEY, pos)

    def save_size(self, size: QSize) -> None:
        layout_id = self.widget.active_layout_id() if self.widget is not None else "stacked"
        self.main_window.settings.setValue(self._layout_size_key(layout_id), size)

    def _layout_size_key(self, layout_id: str) -> str:
        return f"{self.SIZE_KEY}_{layout_id}"

    def saved_size_for_layout(self, layout_spec) -> QSize:
        stored = self.main_window.settings.value(self._layout_size_key(layout_spec.layout_id))
        if stored is None and layout_spec.layout_id == "stacked":
            stored = self.main_window.settings.value(self.SIZE_KEY)
        if isinstance(stored, QSize) and stored.width() > 40 and stored.height() > 40:
            return stored
        return QSize(*layout_spec.preferred_size)

    def set_skin(self, skin_id: str) -> None:
        write_widget_mode_skin_id(self.main_window.settings, skin_id)
        if self.widget is not None:
            self.widget._style_signature = None
            self.widget.apply_theme()

        legacy = getattr(self.main_window, "_panel_widget_mode_controller", None)
        panel = getattr(legacy, "_panel", None)
        if panel is not None:
            panel._theme_cache.clear()
            panel.apply_palette(panel._last_scale or 1.0)

    def set_layout(self, layout_id: str) -> None:
        write_widget_mode_layout_id(self.main_window.settings, layout_id)
        if self.widget is None:
            return
        self.widget.apply_selected_layout(resize_to_layout=True)
        self.widget._style_signature = None
        self.widget.apply_theme()

    def force_refresh(self) -> None:
        self._cache_refresh_pending = False
        self._last_display_signature = None
        self._items_cache.clear()
        self.refresh_data()

    def open_quick_add_dialog(self) -> None:
        self._open_task_dialog("", default_task_type="schedule")

    def handle_quick_add(self, text: str) -> None:
        self._open_task_dialog(text)

    def _open_task_dialog(self, text: str, *, default_task_type: str = "directive") -> None:
        if not hasattr(self.main_window, "open_task_dialog"):
            return
        target_date = self._current_date()
        time_str, name = _parse_quick_add_text(text) if text else (None, "")
        kwargs = {
            "initial_date": target_date,
            "task_type": "schedule" if time_str else default_task_type,
            "prefill_dict": {"name": name} if name else {},
        }
        if time_str:
            kwargs["initial_time"] = time_str
        self.main_window.open_task_dialog(**kwargs)

    def set_target_date(self, target: QDate) -> None:
        if not isinstance(target, QDate) or not target.isValid():
            return
        self._sync_main_context_date(target)
        self._cache_refresh_pending = False
        self.refresh_data()

    def _cache_signature(self, cache, *row_keys: str) -> tuple:
        if not isinstance(cache, dict):
            return (None,)
        parts = [
            id(cache),
            cache.get("range_start"),
            cache.get("range_end"),
            cache.get("context_date"),
        ]
        for key in row_keys:
            rows = cache.get(key)
            if rows is None:
                rows = ()
            try:
                count = len(rows)
            except Exception:
                count = 0
            parts.extend((key, id(rows), count))
        return tuple(parts)

    def _display_signature(self, target: QDate) -> tuple:
        return (
            target.toString("yyyy-MM-dd"),
            self._cache_signature(
                getattr(self.main_window, "_latest_calendar_range_data", None), "rows"
            ),
            self._cache_signature(getattr(self.main_window, "_latest_agenda_data", None), "rows"),
            self._cache_signature(
                getattr(self.main_window, "_latest_directive_data", None),
                "routine_rows",
                "directive_rows",
            ),
        )

    def _get_cached_items(self, signature: tuple) -> list[dict[str, object]] | None:
        items = self._items_cache.get(signature)
        if items is None:
            return None
        self._items_cache.pop(signature, None)
        self._items_cache[signature] = items
        return [dict(item) for item in items]

    def _remember_items(self, signature: tuple, items: list[dict[str, object]]) -> None:
        self._items_cache.pop(signature, None)
        self._items_cache[signature] = [dict(item) for item in items]
        while len(self._items_cache) > 21:
            oldest_key = next(iter(self._items_cache))
            self._items_cache.pop(oldest_key, None)

    def _schedule_rows_for_date(self, target: QDate) -> list[dict]:
        calendar_cache = getattr(self.main_window, "_latest_calendar_range_data", None)
        agenda_cache = getattr(self.main_window, "_latest_agenda_data", None)
        if self._cache_covers_date(calendar_cache, target):
            rows = calendar_cache.get("rows", [])
        elif self._cache_covers_date(agenda_cache, target):
            rows = agenda_cache.get("rows", [])
        else:
            rows = []

        matched = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            start_qd = _parse_qdate(row.get("deadline") or row.get("target_date"))
            end_qd = _parse_qdate(
                row.get("end_date")
                or row.get("end_time")
                or row.get("deadline")
                or row.get("target_date")
            )
            if not start_qd.isValid():
                continue
            if not end_qd.isValid() or end_qd < start_qd:
                end_qd = start_qd
            if start_qd <= target <= end_qd:
                matched.append(row)
        return sorted(
            matched,
            key=lambda row: (
                _safe_text(row.get("deadline")) or "9999-99-99 99:99",
                int(row.get("id") or 0),
            ),
        )

    def _work_items_for_date(self, target: QDate) -> list[dict[str, object]]:
        cache = getattr(self.main_window, "_latest_directive_data", None)
        if not self._directive_cache_matches_date(target) or not isinstance(cache, dict):
            return []

        items = []
        routine_items = []
        for row in cache.get("routine_rows", []) or []:
            if not isinstance(row, dict):
                continue
            status = _normalize_status(row.get("status"))
            if status in {"done", "completed"} or row.get("is_completed") in (1, True):
                continue
            due_qd = _parse_qdate(
                row.get("period_end") or row.get("deadline") or row.get("target_date")
            )
            target_qd = _parse_qdate(row.get("target_date"))
            if (due_qd.isValid() and due_qd == target) or (
                target_qd.isValid() and target_qd == target
            ):
                routine_items.append(
                    {
                        "title": _safe_text(row.get("name"))
                        or t("widget_mode.untitled", "Untitled"),
                        "time": t("widget_mode.routine_short", "Routine"),
                        "is_task": True,
                        "item_kind": "work",
                    }
                )

        directive_items = []
        done_statuses = {"done", "completed", "deferred", "canceled", "cancelled"}
        for row in cache.get("directive_rows", []) or []:
            if not isinstance(row, (tuple, list)) or len(row) < 5:
                continue
            status = _normalize_status(row[2])
            if status in done_statuses:
                continue
            deadline_qd = _parse_qdate(row[4])
            if deadline_qd.isValid() and deadline_qd == target:
                directive_items.append(
                    {
                        "title": _safe_text(row[1]) or t("widget_mode.untitled", "Untitled"),
                        "time": "",
                        "is_task": True,
                        "item_kind": "work",
                    }
                )

        if routine_items:
            items.append(
                {
                    "title": t("widget_mode.section_routine_today", "Work"),
                    "is_section": True,
                    "section_kind": "work",
                }
            )
            items.extend(routine_items[:10])
        if directive_items:
            items.append(
                {
                    "title": t("widget_mode.section_directive_today", "Directive"),
                    "is_section": True,
                    "section_kind": "work",
                }
            )
            items.extend(directive_items[:10])
        return items

    def _schedule_items_for_date(self, target: QDate) -> list[dict[str, object]]:
        rows = self._schedule_rows_for_date(target)
        if not rows:
            return []
        items = [
            {
                "title": t("widget_mode.section_today", "Schedule"),
                "is_section": True,
                "section_kind": "schedule",
            }
        ]
        for row in rows[:18]:
            items.append(
                {
                    "title": _safe_text(row.get("name")) or t("widget_mode.untitled", "Untitled"),
                    "time": _format_widget_datetime_label(
                        row.get("deadline"), reference_date=target
                    ),
                    "is_task": False,
                    "item_kind": "schedule",
                }
            )
        return items

    def _ensure_cache_coverage(self, target: QDate) -> bool:
        self._sync_main_context_date(target)
        has_schedule = self._cache_covers_date(
            getattr(self.main_window, "_latest_calendar_range_data", None), target
        ) or self._cache_covers_date(getattr(self.main_window, "_latest_agenda_data", None), target)
        has_work = self._directive_cache_matches_date(target)
        if has_schedule and has_work:
            self._cache_refresh_pending = False
            return True
        if self._cache_refresh_pending:
            return False
        if hasattr(self.main_window, "schedule_panel_refresh"):
            self.main_window.schedule_panel_refresh(center=not has_schedule, right=not has_work)
        self._cache_refresh_pending = True
        return False

    def refresh_data(self):
        if self.widget is None or not self.widget.isVisible():
            return

        self.widget.apply_theme()
        target = self._current_date()
        self.widget.update_header(target)
        if not self._ensure_cache_coverage(target):
            self.widget.update_agenda([])
            return

        signature = self._display_signature(target)
        if signature == self._last_display_signature:
            return

        items = self._get_cached_items(signature)
        if items is None:
            items = []
            items.extend(self._schedule_items_for_date(target))
            items.extend(self._work_items_for_date(target))
            self._remember_items(signature, items)

        self._last_display_signature = signature
        self.widget.update_agenda(items)
