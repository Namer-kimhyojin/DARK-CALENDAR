# -*- coding: utf-8 -*-
from PyQt6.QtCore import (
    QDate,
    QEvent,
    QLocale,
    QPoint,
    QSize,
    Qt,
    QTime,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QContextMenuEvent,
    QFont,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCalendarWidget,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizeGrip,
    QSizePolicy,
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
from calendar_app.presentation.widgets.panel_widget_style import css_to_qcolor
from calendar_app.presentation.widgets.panel_widget_theme import (
    _apply_configured_widget_color,
    _apply_registered_widget_mode_skin,
    _widget_mode_menu_stylesheet,
)
from calendar_app.presentation.widgets.widget_mode_density import (
    DENSITIES,
    DENSITY_KEY,
    read_widget_density,
)
from calendar_app.presentation.widgets.widget_mode_geometry import (
    best_available_geometry,
    clamp_rect,
    deserialize_geometry,
    geometry_key,
    legacy_rect,
    restore_rect,
    serialize_geometry,
)
from calendar_app.presentation.widgets.widget_mode_opacity import (
    apply_widget_opacity,
    read_widget_opacities,
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
from calendar_app.presentation.widgets.widget_mode_typography import (
    read_widget_typography,
)
from calendar_app.presentation.widgets.widget_mode_visibility import (
    read_widget_calendar_visibility,
    write_widget_calendar_visibility,
)
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic


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
            font-size: 15pt;
            font-weight: 800;
            letter-spacing: 0px;
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
        QFrame#unified_empty_state {{
            background: {tk.get("surface_alt", tk["section_bg"])};
            border: 1px solid {tk.get("section_border_soft", tk.get("panel_border_soft", tk["panel_border"]))};
            border-radius: 16px;
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


class _CompletionCheckBox(QCheckBox):
    """Theme-aware indicator retaining native checkbox keyboard/accessibility behavior."""

    def __init__(self, controller, parent):
        super().__init__(parent)
        self._controller = controller
        self.setFixedSize(24, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        tokens = _widget_theme_tokens(self._controller.main_window)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(
            QPen(QColor(tokens["accent"] if self.isChecked() else tokens["text_secondary"]), 1.5)
        )
        background = css_to_qcolor(tokens["section_bg"])
        background.setAlpha(
            round(
                background.alpha()
                * read_widget_opacities(self._controller.main_window.settings)[1]
                / 100
            )
        )
        painter.setBrush(background)
        painter.drawRoundedRect(3, 3, 18, 18, 5, 5)
        if self.isChecked():
            painter.drawPixmap(5, 5, _ic(ICON.CHECK, color=tokens["accent"]).pixmap(14, 14))
        if self.hasFocus():
            painter.setPen(QPen(QColor(tokens["accent"]), 1, Qt.PenStyle.DotLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(1, 1, 22, 22, 6, 6)
        painter.end()


class _AgendaTitleButton(QPushButton):
    """Keep the full accessible title while fitting long text into a small row."""

    def __init__(self, title, parent):
        super().__init__(title, parent)
        self._full_title = title

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.setText(
            self.fontMetrics().elidedText(
                self._full_title, Qt.TextElideMode.ElideRight, max(0, self.width() - 4)
            )
        )


class AgendaItemWidget(QFrame):
    def __init__(
        self,
        title: str,
        time_text: str,
        *,
        is_task: bool = False,
        item=None,
        controller=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("agenda_item_task" if is_task else "agenda_item_schedule")
        density = read_widget_density(controller.main_window.settings if controller else None)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, density.vertical_margin, 10, density.vertical_margin)
        layout.setSpacing(8)

        marker = QFrame(self)
        marker.setObjectName(
            "agenda_item_marker_task" if is_task else "agenda_item_marker_schedule"
        )
        marker.setFixedSize(10, 10)
        marker_slot = QWidget(self)
        marker_slot.setObjectName("agenda_item_marker_slot")
        marker_slot.setFixedSize(24, 28)
        marker_layout = QVBoxLayout(marker_slot)
        marker_layout.setContentsMargins(0, 0, 0, 0)
        marker_layout.addWidget(marker, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(marker_slot, 0, Qt.AlignmentFlag.AlignTop)
        item = item or {}
        self.setProperty("completed", bool(item.get("completed")))
        if is_task and item.get("item_id") and controller is not None:
            marker_slot.hide()
            check = _CompletionCheckBox(controller, self)
            check.setObjectName("agenda_complete")
            check.setChecked(bool(item.get("completed")))
            check.setAccessibleName(
                t("widget_mode.complete_named", "완료 상태 변경: {name}", name=title)
            )
            check.setToolTip(check.accessibleName())
            check.clicked.connect(lambda checked: controller.set_item_completed(item, checked))
            layout.insertWidget(0, check, 0, Qt.AlignmentFlag.AlignTop)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(3)
        layout.addLayout(body, 1)

        title_label = (
            _AgendaTitleButton(title, self)
            if item.get("item_id") and controller
            else QLabel(title, self)
        )
        title_label.setObjectName("agenda_item_title")
        if isinstance(title_label, QPushButton):
            title_label.setFlat(True)
            title_label.setCursor(Qt.CursorShape.PointingHandCursor)
            title_label.clicked.connect(lambda: controller.open_item(item))
            title_label.setAccessibleName(t("widget_mode.open_named", "열기: {name}", name=title))
            title_label.setMinimumWidth(0)
            typography = read_widget_typography(controller.main_window.settings)
            title_label.setMinimumHeight(
                max(28, int(typography.title * 1.5 + density.title_padding))
            )
            title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        else:
            title_label.setWordWrap(True)
        title_label.setToolTip(title)
        body.addWidget(title_label)

        # Section headings already identify schedules/work. Keep only useful metadata.
        time_label = QLabel(_safe_text(time_text), self)
        time_label.setObjectName("agenda_item_time")
        time_label.setVisible(bool(_safe_text(time_text)))
        if density.key == "compact":
            layout.addWidget(time_label, 0, Qt.AlignmentFlag.AlignVCenter)
        else:
            body.addWidget(time_label)
        if item.get("item_id") and controller is not None:
            more_btn = QToolButton(self)
            more_btn.setObjectName("agenda_item_more")
            more_btn.setText("⋯")
            more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            more_btn.setFixedSize(30, 30)
            more_btn.setAccessibleName(
                t("widget_mode.item_more_named", "항목 작업: {name}", name=title)
            )
            more_btn.setToolTip(more_btn.accessibleName())
            more_btn.clicked.connect(
                lambda _checked=False, anchor=more_btn: controller.open_item_menu(
                    item, anchor.mapToGlobal(anchor.rect().bottomLeft())
                )
            )
            layout.addWidget(more_btn, 0, Qt.AlignmentFlag.AlignTop)

            self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.customContextMenuRequested.connect(
                lambda pos: controller.open_item_menu(item, self.mapToGlobal(pos))
            )
        self.setMinimumHeight(body.minimumSize().height() + density.vertical_margin * 2)


class _CompactMonthCalendar(QWidget):
    """Transparent six-week month grid using the widget's semantic tokens."""

    dateClicked = pyqtSignal(QDate)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("unified_month_calendar")
        self.setAccessibleName(t("widget_mode.month_calendar", "월간 날짜 선택"))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._tokens: dict[str, str] = {}
        self._selected_date = QDate.currentDate()
        self._dates: list[QDate] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)
        navigation = QHBoxLayout()
        navigation.setContentsMargins(0, 0, 0, 0)
        navigation.setSpacing(4)
        self.previous_btn = QToolButton(self)
        self.previous_btn.setObjectName("unified_month_nav")
        self.previous_btn.setArrowType(Qt.ArrowType.LeftArrow)
        self.previous_btn.setAccessibleName(t("widget_mode.month_prev", "이전 달"))
        self.previous_btn.setToolTip(self.previous_btn.accessibleName())
        self.previous_btn.clicked.connect(lambda: self._navigate_month(-1))
        navigation.addWidget(self.previous_btn)
        navigation.addStretch(1)
        self.month_label = QLabel(self)
        self.month_label.setObjectName("unified_month_title")
        self.month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.month_label.setMinimumWidth(110)
        self.month_label.setFixedHeight(30)
        navigation.addWidget(self.month_label)
        navigation.addStretch(1)
        self.next_btn = QToolButton(self)
        self.next_btn.setObjectName("unified_month_nav")
        self.next_btn.setArrowType(Qt.ArrowType.RightArrow)
        self.next_btn.setAccessibleName(t("widget_mode.month_next", "다음 달"))
        self.next_btn.setToolTip(self.next_btn.accessibleName())
        self.next_btn.clicked.connect(lambda: self._navigate_month(1))
        navigation.addWidget(self.next_btn)
        root.addLayout(navigation)

        self.weekday_row = QHBoxLayout()
        self.weekday_row.setContentsMargins(0, 0, 0, 0)
        self.weekday_row.setSpacing(2)
        self.weekday_labels: list[QLabel] = []
        weekday_keys = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
        for key in weekday_keys:
            label = QLabel(self)
            label.setObjectName("unified_month_weekday")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFixedHeight(24)
            label.setText(t(f"weekday.{key}", key.title()))
            self.weekday_row.addWidget(label, 1)
            self.weekday_labels.append(label)
        root.addLayout(self.weekday_row)

        self.day_grid = QGridLayout()
        self.day_grid.setContentsMargins(0, 0, 0, 0)
        self.day_grid.setHorizontalSpacing(2)
        self.day_grid.setVerticalSpacing(2)
        self.day_buttons: list[QToolButton] = []
        for index in range(42):
            button = QToolButton(self)
            button.setObjectName("unified_month_day")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, idx=index: self._emit_clicked(idx))
            self.day_grid.addWidget(button, index // 7, index % 7)
            self.day_buttons.append(button)
        root.addLayout(self.day_grid, 1)
        self.update_month(self._selected_date)

    def selectedDate(self) -> QDate:
        return QDate(self._selected_date)

    def setSelectedDate(self, selected: QDate) -> None:
        if not isinstance(selected, QDate) or not selected.isValid():
            return
        self._selected_date = QDate(selected)
        self.update_month(selected)

    def set_theme_tokens(
        self,
        tokens: dict[str, str],
        *,
        opacities=(100, 100),
        font_size: float = 9.4,
    ) -> None:
        normalized = dict(tokens or {})
        normalized["_text_opacity"], normalized["_background_opacity"] = opacities
        normalized["_font_size"] = float(font_size)
        if normalized == self._tokens:
            return
        self._tokens = normalized
        self._apply_style()
        self.update_month(self._selected_date, force=True)

    def apply_layout_metrics(self, *, cell_height: int, spacing: int) -> None:
        height = max(25, int(cell_height * 0.62))
        for button in self.day_buttons:
            button.setMinimumSize(24, height)
            button.setMaximumHeight(height)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        gap = max(1, min(4, int(spacing)))
        self.day_grid.setHorizontalSpacing(gap)
        self.day_grid.setVerticalSpacing(gap)
        self.setMinimumHeight(62 + (height * 6) + (gap * 5))

    def _apply_style(self) -> None:
        tk = self._tokens
        if not tk:
            return
        font_size = float(tk.get("_font_size", 9.4))
        self.setStyleSheet(
            apply_widget_opacity(
                f"""
                QWidget#unified_month_calendar {{ background: transparent; border: none; }}
                QLabel#unified_month_title {{ color: {tk["text_primary"]};
                    background: transparent; font-size: {font_size:.1f}pt;
                    font-weight: 700; }}
                QLabel#unified_month_weekday {{ color: {tk["text_secondary"]};
                    background: transparent; font-size: {max(7.5, font_size - 1.2):.1f}pt;
                    font-weight: 600; padding: 2px 0; }}
                QToolButton#unified_month_nav {{ color: {tk["text_secondary"]};
                    background: transparent; border: 1px solid transparent;
                    border-radius: 6px; min-width: 28px; min-height: 26px; }}
                QToolButton#unified_month_nav:hover {{ color: {tk["text_primary"]};
                    background: {tk.get("button_hover", tk["surface_alt"])}; }}
                """,
                tk.get("_text_opacity", 100),
                tk.get("_background_opacity", 100),
            )
        )

    def _day_stylesheet(self, day: QDate, *, current_month: int, today: QDate) -> str:
        tk = self._tokens
        if not tk:
            return ""
        text = (
            tk.get("text_faint", tk["text_secondary"])
            if day.month() != current_month
            else tk["text_secondary"]
        )
        if day.month() == current_month and day.dayOfWeek() in {
            Qt.DayOfWeek.Saturday.value,
            Qt.DayOfWeek.Sunday.value,
        }:
            text = tk.get("accent_deep", tk["text_primary"])
        background = "transparent"
        border = "transparent"
        weight = 500
        if day == today:
            border = tk.get("hero_border", tk["accent"])
            text = tk["text_primary"]
        if day == self._selected_date:
            background = tk.get("hero_bg_strong", tk["surface_alt"])
            border = tk.get("hero_border", tk["accent"])
            text = tk.get("accent_deep", tk["text_primary"])
            weight = 700
        font_size = float(tk.get("_font_size", 9.4))
        return apply_widget_opacity(
            f"""
            QToolButton {{ color: {text}; background: {background};
                border: 1px solid {border}; border-radius: 7px;
                font-size: {font_size:.1f}pt; font-weight: {weight}; padding: 2px; }}
            QToolButton:hover {{ color: {tk["text_primary"]};
                background: {tk.get("button_hover", tk["surface_alt"])}; }}
            """,
            tk.get("_text_opacity", 100),
            tk.get("_background_opacity", 100),
        )

    def _navigate_month(self, delta: int) -> None:
        self.dateClicked.emit(self._selected_date.addMonths(int(delta)))

    def _emit_clicked(self, index: int) -> None:
        if 0 <= index < len(self._dates):
            self.dateClicked.emit(self._dates[index])

    def update_month(self, selected: QDate, *, force: bool = False) -> None:
        if not isinstance(selected, QDate) or not selected.isValid():
            return
        self._selected_date = QDate(selected)
        first = QDate(selected.year(), selected.month(), 1)
        grid_start = first.addDays(1 - first.dayOfWeek())
        self.month_label.setText(f"{selected.year()}. {selected.month():02d}")
        weekday_keys = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
        for key, label in zip(weekday_keys, self.weekday_labels, strict=True):
            label.setText(t(f"weekday.{key}", key.title()))
        self._dates = []
        today = QDate.currentDate()
        for index, button in enumerate(self.day_buttons):
            day = grid_start.addDays(index)
            self._dates.append(day)
            button.setText(str(day.day()))
            button.setToolTip(_format_compact_date_with_weekday(day))
            button.setAccessibleName(button.toolTip())
            button.setStyleSheet(
                self._day_stylesheet(day, current_month=selected.month(), today=today)
            )


class CompactCalendarGrid(QWidget):
    dateClicked = pyqtSignal(QDate)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tokens: dict[str, str] = {}
        self._buttons = []
        self._last_render_state = None
        self._display_mode = "week"
        self._selected_date = QDate.currentDate()
        self.setObjectName("unified_calendar_section")
        self._root_layout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(6)

        self._week_strip = QWidget(self)
        self._week_strip.setObjectName("unified_week_strip")
        self._row_layout = QHBoxLayout(self._week_strip)
        self._row_layout.setContentsMargins(0, 0, 0, 0)
        self._row_layout.setSpacing(6)
        self._root_layout.addWidget(self._week_strip)

        for index in range(7):
            button = QToolButton(self)
            button.setObjectName("unified_day_btn")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedSize(42, 54)
            button.clicked.connect(lambda _checked=False, idx=index: self._emit_clicked(idx))
            self._row_layout.addWidget(button)
            self._buttons.append(button)

        self.month_calendar = _CompactMonthCalendar(self)
        self.month_calendar.dateClicked.connect(self.dateClicked)
        self.month_calendar.hide()
        self._root_layout.addWidget(self.month_calendar, 1)

        self._dates = []
        self.update_grid()

    @property
    def display_mode(self) -> str:
        return self._display_mode

    def set_display_mode(self, mode: str) -> None:
        normalized = "month" if str(mode).lower() == "month" else "week"
        if normalized == self._display_mode:
            return
        self._display_mode = normalized
        self._week_strip.setVisible(normalized == "week")
        self.month_calendar.setVisible(normalized == "month")
        self._last_render_state = None
        self.update_grid(self._selected_date)

    def apply_layout_metrics(
        self,
        *,
        cell_size: tuple[int, int],
        spacing: int,
        margins: tuple[int, int, int, int],
    ) -> None:
        width, height = cell_size
        for button in self._buttons:
            button.setMinimumSize(28, max(38, height))
            button.setMaximumSize(16777215, max(38, height))
        self.month_calendar.apply_layout_metrics(cell_height=height, spacing=spacing)
        self._row_layout.setSpacing(max(0, spacing))
        self._root_layout.setContentsMargins(*margins)

    def set_theme_tokens(
        self,
        tokens: dict[str, str],
        *,
        opacities=(100, 100),
        font_size: float = 9.4,
    ) -> None:
        normalized = dict(tokens or {})
        normalized["_text_opacity"], normalized["_background_opacity"] = opacities
        normalized["_font_size"] = float(font_size)
        if normalized == self._tokens:
            return
        self._tokens = normalized
        self._last_render_state = None
        self.month_calendar.set_theme_tokens(
            tokens,
            opacities=opacities,
            font_size=font_size,
        )

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
        border = "transparent"
        border_bottom = "transparent"
        background = "transparent"
        text = tk.get("text_secondary", "#b0b8d0")
        weight = "500"
        if day == today:
            border = tk.get("section_border_soft", tk.get("hero_border", border))
            border_bottom = tk.get("accent", tk.get("hero_border", border))
            background = tk.get("hero_bg", tk.get("surface_alt", background))
            text = tk.get("text_primary", "#ffffff")
            weight = "600"
        if day == selected:
            border = tk.get("hero_border", tk.get("accent", border))
            border_bottom = tk.get("accent_deep", tk.get("accent", border))
            background = (
                "qlineargradient("
                "x1: 0, y1: 0, x2: 1, y2: 1,"
                f"stop: 0 {tk.get('hero_bg_strong', tk.get('surface_alt', background))},"
                f"stop: 1 {tk.get('section_bg_alt', tk.get('surface_alt', background))}"
                ")"
            )
            text = tk.get("accent_deep", tk.get("text_primary", "#ffffff"))
            weight = "700"
        return apply_widget_opacity(
            (
                "QToolButton {"
                f"background: {background};"
                f"border: 1px solid {border};"
                f"border-bottom: 3px solid {border_bottom};"
                "border-radius: 8px;"
                f"color: {text};"
                f"font-size: {float(tk.get('_font_size', 9.4)):.1f}pt;"
                f"font-weight: {weight};"
                "padding: 5px 2px 4px 2px;"
                "}"
                "QToolButton:hover {"
                f"background: {tk.get('button_hover', tk.get('section_bg_alt', 'rgba(255, 255, 255, 12)'))};"
                f"border: 1px solid {tk.get('hero_border', border)};"
                f"border-bottom: 3px solid {border_bottom};"
                "}"
                "QToolButton:focus {"
                f"border: 2px solid {tk.get('accent', tk.get('hero_border', border))};"
                "}"
            ),
            tk.get("_text_opacity", 100),
            tk.get("_background_opacity", 100),
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
        self._selected_date = selected
        today = QDate.currentDate()
        week_start = selected.addDays(1 - selected.dayOfWeek())
        locale = QLocale()
        state = (
            self._display_mode,
            selected.toString("yyyy-MM-dd"),
            today.toString("yyyy-MM-dd"),
            week_start.toString("yyyy-MM-dd"),
            locale.name(),
        )
        if state == self._last_render_state:
            return
        self._last_render_state = state
        self.month_calendar.setSelectedDate(selected)

        self._dates = []
        for offset, button in enumerate(self._buttons):
            day = week_start.addDays(offset)
            self._dates.append(day)
            weekday = locale.dayName(
                day.dayOfWeek(), QLocale.FormatType.ShortFormat
            ).strip() or day.toString("ddd")
            button.setText(f"{weekday}\n{day.day()}")
            button.setProperty(
                "dateState",
                "selected" if day == selected else "today" if day == today else "default",
            )
            button.setStyleSheet(self._button_stylesheet(day, today, selected))


class UnifiedWidgetWindow(QWidget):
    def __init__(self, controller):
        super().__init__(None)
        self.controller = controller
        settings = controller.main_window.settings
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setWindowFlag(
            Qt.WindowType.WindowStaysOnTopHint,
            str(settings.value("widget_mode_always_top", "true")).lower() == "true",
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
        self._data_state = "ready"
        self._drag_offset = None
        self._feedback_timer = QTimer(self)
        self._feedback_timer.setSingleShot(True)
        self._feedback_timer.timeout.connect(self.clear_feedback)

        self._build_ui()
        self._setup_refresh_timer()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.surface = QFrame(self)
        self.surface.setObjectName("unified_surface")
        main_layout.addWidget(self.surface)
        surface_layout = QVBoxLayout(self.surface)
        surface_layout.setContentsMargins(14, 10, 14, 8)
        surface_layout.setSpacing(4)

        self.toolbar = QFrame(self)
        self.toolbar.setObjectName("unified_toolbar")
        bar = QHBoxLayout(self.toolbar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(2)
        self.toolbar.installEventFilter(self)
        self.restore_btn = self._button(
            t("widget_mode.return_main", "메인 화면으로"), self.controller.return_to_main
        )
        bar.addWidget(self.restore_btn)
        bar.addStretch(1)
        self.pin_btn = self._button(t("widget_mode.pin", "항상 위"), self._toggle_pin)
        self.pin_btn.setCheckable(True)
        self.pin_btn.setChecked(bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))
        bar.addWidget(self.pin_btn)
        self.customize_btn = self._button(
            t("widget_mode.customize", "꾸미기"), self.open_customization
        )
        bar.addWidget(self.customize_btn)
        self.more_btn = self._button("...", self._show_more_menu)
        self.more_btn.setAccessibleName(t("widget_mode.more", "더 보기"))
        self.more_btn.setToolTip(self.more_btn.accessibleName())
        bar.addWidget(self.more_btn)
        surface_layout.addWidget(self.toolbar)

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
        self.hero_layout.addLayout(actions)

        self.previous_week_btn = self._button(
            "‹",
            lambda: self.controller.set_target_date(self.controller._current_date().addDays(-7)),
        )
        self.previous_week_btn.setToolTip(t("widget_mode.previous_week", "이전 주"))
        self.previous_week_btn.setAccessibleName(self.previous_week_btn.toolTip())
        actions.addWidget(self.previous_week_btn)
        self.date_picker_btn = self._button(
            t("widget_mode.pick_date", "날짜 선택"), self._pick_date
        )
        actions.addWidget(self.date_picker_btn)
        self.next_week_btn = self._button(
            "›", lambda: self.controller.set_target_date(self.controller._current_date().addDays(7))
        )
        self.next_week_btn.setToolTip(t("widget_mode.next_week", "다음 주"))
        self.next_week_btn.setAccessibleName(self.next_week_btn.toolTip())
        actions.addWidget(self.next_week_btn)
        actions.addStretch(1)

        self.today_btn = QToolButton(self.hero)
        self.today_btn.setObjectName("unified_action_btn")
        self.today_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.today_btn.clicked.connect(lambda: self.controller.set_target_date(QDate.currentDate()))
        actions.addWidget(self.today_btn)

        self.add_btn = QToolButton(self.hero)
        self.add_btn.setObjectName("unified_primary_action")
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.clicked.connect(self._add_item)

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
            ("directive", t("widget_mode.filter_directive", "지시")),
        ):
            btn = QToolButton(self.container)
            btn.setObjectName("unified_filter_btn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setText(label)
            btn.setMinimumWidth(0)
            btn.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda _checked=False, m=mode: self._set_filter(m))
            self.filter_row.addWidget(btn, 1)
            self._filter_buttons[mode] = btn
        self.filter_row.addStretch(1)
        self.week_toggle_btn = self._button(t("widget_mode.week_toggle", "주간"), self._toggle_week)
        self.week_toggle_btn.setCheckable(True)
        self.filter_row.addWidget(self.week_toggle_btn)
        self.filter_row.addWidget(self.add_btn)

        self.agenda_section = QFrame(self.container)
        self.agenda_section.setObjectName("unified_agenda_section")
        self.agenda_layout = QVBoxLayout(self.agenda_section)
        self.agenda_layout.setContentsMargins(0, 0, 0, 0)
        self.agenda_layout.setSpacing(8)

        self.agenda_header = QLabel(t("widget_mode.focus_list", "FOCUS LIST"), self.agenda_section)
        self.agenda_header.setObjectName("unified_section")
        self.agenda_header.hide()

        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("unified_scroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.viewport().setObjectName("unified_scroll_viewport")
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("unified_scroll_content")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(8)
        self.scroll_layout.addStretch()
        self.scroll.setWidget(self.scroll_content)
        self.agenda_layout.addWidget(self.scroll, 1)

        surface_layout.addWidget(self.container, 1)
        footer = QHBoxLayout()
        self.completed_btn = self._button(
            t("widget_mode.show_completed", "완료 업무 보기"), self._toggle_completed
        )
        self.completed_btn.setCheckable(True)
        self.completed_btn.setChecked(
            str(
                self.controller.main_window.settings.value("widget_mode_show_completed", "false")
            ).lower()
            == "true"
        )
        footer.addWidget(self.completed_btn)
        footer.addStretch(1)
        self.undo_btn = self._button(
            t("widget_mode.undo", "실행 취소"), self.controller.undo_completion
        )
        self.undo_btn.hide()
        footer.addWidget(self.undo_btn)
        footer.addWidget(self.count_chip)
        footer.addWidget(self.clock_label)
        self.size_grip = QSizeGrip(self)
        footer.addWidget(self.size_grip)
        surface_layout.addLayout(footer)
        self.feedback_label = QLabel(self)
        self.feedback_label.setWordWrap(True)
        self.feedback_label.setObjectName("unified_hint")
        self.feedback_label.hide()
        surface_layout.addWidget(self.feedback_label)
        # Reuse existing routes/controls while removing the separate hero/navigation rows.
        bar.insertWidget(1, self.date_picker_btn)
        bar.insertWidget(3, self.today_btn)
        self.date_picker_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.date_picker_btn.setMinimumWidth(0)
        self.date_picker_btn.setArrowType(Qt.ArrowType.DownArrow)
        self.date_picker_btn.setProperty("datePicker", True)
        for button in (self.restore_btn, self.pin_btn, self.customize_btn, self.more_btn):
            button.setProperty("compactControl", True)
        self.date_label.hide()
        self.previous_week_btn.hide()
        self.next_week_btn.hide()
        self.apply_selected_layout(resize_to_layout=True)
        self.apply_theme()
        self._sync_filter_buttons()

    def _button(self, text, callback):
        button = QToolButton(self)
        button.setObjectName("unified_action_btn")
        button.setText(text)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setToolTip(text)
        button.setAccessibleName(text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(32)
        button.clicked.connect(callback)
        return button

    def _toggle_pin(self):
        self.controller.set_always_top(self.pin_btn.isChecked())

    def _toggle_week(self):
        self.controller._save_geometry()
        self.controller._restoring_geometry = True
        try:
            write_widget_calendar_visibility(
                self.controller.main_window.settings,
                self._active_layout_id or "stacked",
                self.week_toggle_btn.isChecked(),
            )
            self.apply_selected_layout(force=True)
        finally:
            self.controller._restoring_geometry = False
        self.controller._restore_geometry(preserve_position_if_new=True)

    def set_density(self, key):
        if key not in {density.key for density in DENSITIES}:
            return
        self.controller.main_window.settings.setValue(DENSITY_KEY, key)
        self.apply_selected_layout(force=True)
        self.apply_theme()

    def _toggle_completed(self):
        self.controller.main_window.settings.setValue(
            "widget_mode_show_completed", self.completed_btn.isChecked()
        )
        self.controller.force_refresh()

    def _add_item(self):
        if self._active_filter == "work":
            self.controller._open_task_dialog("", default_task_type="routine")
        elif self._active_filter == "schedule":
            self.controller.open_quick_add_dialog()
        elif self._active_filter == "directive":
            self.controller._open_directive_dialog()
        else:
            menu = QMenu(self)
            for kind, label in (
                ("schedule", t("widget_mode.action_add_schedule", "일정 추가")),
                ("routine", t("widget_mode.add_work", "업무 추가")),
                ("directive", t("widget_mode.add_directive", "지시·협조 추가")),
            ):
                menu.addAction(
                    label,
                    lambda selected=kind: (
                        self.controller._open_task_dialog("", default_task_type=selected)
                        if selected != "directive"
                        else self.controller._open_directive_dialog()
                    ),
                )
            menu.addSeparator()
            menu.addAction(
                t("menu.directive_status", "지시·협조 관리"),
                lambda: self.controller.open_work_management("directive"),
            )
            menu.addAction(
                t("menu.work_management", "전체 업무 관리"),
                lambda: self.controller.open_work_management("schedule"),
            )
            menu.exec(self.add_btn.mapToGlobal(self.add_btn.rect().bottomLeft()))

    def _pick_date(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(t("widget_mode.pick_date", "날짜 선택"))
        layout = QVBoxLayout(dialog)
        calendar = QCalendarWidget(dialog)
        calendar.setSelectedDate(self.controller._current_date())
        layout.addWidget(calendar)
        calendar.clicked.connect(
            lambda date: (self.controller.set_target_date(date), dialog.accept())
        )
        dialog.exec()

    def open_customization(self):
        from calendar_app.presentation.dialogs.widget_customization_dialog import (
            WidgetCustomizationDialog,
        )

        dialog = WidgetCustomizationDialog(self.controller, self)
        dialog.exec()
        dialog.deleteLater()

    def _show_more_menu(self):
        self._open_menu(self.more_btn.mapToGlobal(self.more_btn.rect().bottomLeft()))

    def eventFilter(self, watched, event):
        if watched is self.toolbar:
            if (
                event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
            ):
                self._drag_offset = event.globalPosition().toPoint() - self.pos()
                return True
            if event.type() == QEvent.Type.MouseMove and self._drag_offset is not None:
                self.move(event.globalPosition().toPoint() - self._drag_offset)
                return True
            if event.type() == QEvent.Type.MouseButtonRelease and self._drag_offset is not None:
                self._drag_offset = None
                self.controller.save_position(self.pos())
                return True
        return super().eventFilter(watched, event)

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

        self.container_layout.setContentsMargins(0, 4, 0, 4)
        self.container_layout.setHorizontalSpacing(min(10, layout_spec.spacing))
        self.container_layout.setVerticalSpacing(min(10, layout_spec.spacing))
        # Keep saved layout identity; only its presentation adapts to narrow windows.
        target_width = (
            self.controller.saved_size_for_layout(layout_spec).width()
            if resize_to_layout
            else self.width()
        )
        compact = target_width < 640 and layout_spec.layout_id in {"dashboard", "magazine"}
        calendar_supported = any(
            section == "calendar" for section, *_placement in layout_spec.placements
        )
        calendar_visible = calendar_supported and read_widget_calendar_visibility(
            settings, layout_spec.layout_id
        )
        calendar_collapsed = calendar_supported and not calendar_visible
        if calendar_collapsed:
            placements = (
                ("hero", 0, 0, 1, 1),
                ("filters", 1, 0, 1, 1),
                ("agenda", 2, 0, 1, 1),
            )
        else:
            placements = (
                get_widget_mode_layout("stacked").placements if compact else layout_spec.placements
            )
        self._compact_layout = compact
        for section_name, row, column, row_span, column_span in placements:
            section = sections[section_name]
            self.container_layout.addWidget(section, row, column, row_span, column_span)
            section.setVisible(True)
        active_row_stretches = (
            ((2, 1),) if calendar_collapsed else ((3, 1),) if compact else layout_spec.row_stretches
        )
        active_column_stretches = (
            ((0, 1),) if calendar_collapsed or compact else layout_spec.column_stretches
        )
        for row, stretch in active_row_stretches:
            self.container_layout.setRowStretch(row, stretch)
        for column, stretch in active_column_stretches:
            self.container_layout.setColumnStretch(column, stretch)

        self.hero_layout.setContentsMargins(0, 8, 0, 8)
        self.hero_layout.setSpacing(6)
        self.filter_row.setContentsMargins(0, 4, 0, 4)
        self.filter_row.setSpacing(layout_spec.filter_spacing)
        self.agenda_layout.setContentsMargins(0, 8, 0, 0)
        self.agenda_layout.setSpacing(layout_spec.agenda_spacing)
        self.scroll_layout.setSpacing(read_widget_density(settings).row_spacing)
        self.cal_grid.apply_layout_metrics(
            cell_size=layout_spec.calendar_cell_size,
            spacing=layout_spec.calendar_spacing,
            margins=layout_spec.calendar_margins,
        )
        calendar_mode = "month" if layout_spec.layout_id in {"dashboard", "magazine"} else "week"
        self.cal_grid.set_display_mode(calendar_mode)
        if not calendar_visible:
            self.cal_grid.hide()
        self.week_toggle_btn.setChecked(calendar_visible)
        self.week_toggle_btn.setVisible(calendar_supported)
        if calendar_mode == "month":
            self.week_toggle_btn.setText(t("widget_mode.month_toggle", "월간"))
            self.week_toggle_btn.setToolTip(
                t("widget_mode.month_toggle_help", "월간 날짜 표시 / 접기")
            )
        else:
            self.week_toggle_btn.setText(t("widget_mode.week_toggle", "주간"))
            self.week_toggle_btn.setToolTip(
                t("widget_mode.week_toggle_help", "주간 날짜 표시 / 접기")
            )
        self.eyebrow_label.setVisible(
            layout_spec.show_eyebrow and layout_spec.layout_id.startswith("user_layout_")
        )
        self.status_chip.hide()
        self.clock_label.setVisible(
            str(settings.value("widget_mode_show_clock", "true")).lower() == "true"
        )
        self.hint_label.setVisible(
            str(settings.value("widget_mode_show_hint", "false")).lower() == "true"
        )
        self.caption_label.hide()
        self.hero.setVisible(not self.eyebrow_label.isHidden() or not self.hint_label.isHidden())

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
        settings = self.controller.main_window.settings
        opacities = read_widget_opacities(settings)
        family = str(settings.value("widget_mode_font_family", QApplication.font().family()))
        weight = int(settings.value("widget_mode_font_weight", 500))
        weight = weight if weight in {400, 500, 600, 700} else 500
        typography = read_widget_typography(settings)
        signature = (
            tuple(sorted(tokens.items())),
            family,
            weight,
            typography,
            read_widget_density(settings).key,
            opacities,
        )
        if signature == self._style_signature:
            return
        self._style_signature = signature
        base_font = QFont(family, int(round(typography.body)))
        self.setFont(base_font)
        css_family = (
            family.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")
        )
        self.setStyleSheet(
            apply_widget_opacity(
                _unified_widget_stylesheet(tokens)
                + f"""
            QWidget {{ font-family: "{css_family}"; }}
            QFrame#unified_surface {{ background: {tokens["panel_bg"]};
                border: 1px solid {tokens["panel_border"]}; border-radius: 16px; }}
            QFrame#unified_toolbar, QFrame#unified_container, QFrame#unified_hero {{
                background: transparent; border: none; border-radius: 0; }}
            QFrame#unified_container[widgetLayout] QFrame#unified_agenda_section,
            QFrame#unified_container[widgetLayout] QFrame#unified_filter_section,
            QFrame#unified_container[widgetLayout] QWidget#unified_calendar_section {{
                background: transparent; border: none; border-radius: 0; }}
            QLabel#unified_eyebrow {{ font-size: {typography.secondary:.1f}pt; }}
            QLabel#unified_date {{ font-size: {typography.date:.1f}pt; }}
            QLabel#unified_caption, QLabel#unified_hint,
            QLabel#unified_chip, QLabel#unified_chip_accent {{
                font-size: {typography.secondary:.1f}pt; }}
            QLabel#unified_section {{ letter-spacing: 0; font-size: {typography.section:.1f}pt; font-weight: 600;
                color: {tokens["text_secondary"]}; }}
            QLabel#unified_clock {{ font-size: {typography.control:.1f}pt; font-weight: 500; letter-spacing: 0; }}
            QLabel#unified_empty {{ font-size: {typography.body:.1f}pt; }}
            QToolButton#unified_action_btn, QToolButton#unified_filter_btn,
            QToolButton#unified_primary_action {{ border-radius: 7px; letter-spacing: 0;
                font-size: {typography.control:.1f}pt; font-weight: 500; }}
            QToolButton#unified_action_btn {{ background: transparent; border: 1px solid transparent; }}
            QToolButton#unified_action_btn:hover {{ background: {tokens["section_bg"]}; }}
            QToolButton#unified_primary_action:hover,
            QToolButton#unified_primary_action:pressed {{
                color: {tokens["text_primary"]};
                background: {tokens.get("button_primary_hover_bg", tokens["section_bg_alt"])};
                border: 1px solid {tokens.get("button_primary_hover_border", tokens["accent"])}; }}
            QFrame#agenda_item_task, QFrame#agenda_item_schedule {{
                background: {tokens["section_bg"]}; border: 1px solid {tokens["panel_border"]}; border-radius: 10px; }}
            QPushButton#agenda_item_title {{ color: {tokens["text_primary"]}; text-align: left;
                background: transparent; border: none; padding: 0; font-size: {typography.title:.1f}pt; font-weight: {weight}; }}
            QLabel#agenda_item_title {{ font-size: {typography.title:.1f}pt; font-weight: {weight}; }}
            QLabel#agenda_item_time {{ background: transparent; border: none; padding: 0;
                color: {tokens["text_secondary"]}; font-size: {typography.secondary:.1f}pt; }}
            QFrame[completed="true"] QPushButton#agenda_item_title {{ color: {tokens["text_secondary"]}; text-decoration: line-through; }}
            QPushButton#agenda_item_title:hover {{ color: {tokens["accent"]}; }}
            QToolButton#agenda_item_more {{ color: {tokens["text_secondary"]}; background: transparent;
                border: 1px solid transparent; border-radius: 6px; font-size: {typography.control:.1f}pt; }}
            QToolButton#agenda_item_more:hover, QToolButton#agenda_item_more:focus {{
                color: {tokens["text_primary"]}; background: {tokens["section_bg_alt"]};
                border: 1px solid {tokens["hero_border"]}; }}
            QToolButton:focus, QPushButton#agenda_item_title:focus {{ border: 2px solid {tokens["accent"]}; }}
            QToolButton#unified_action_btn {{ padding: 4px 8px; }}
            QToolButton[compactControl="true"] {{ padding: 2px; }}
            QToolButton#unified_action_btn[datePicker="true"] {{
                font-size: {typography.date:.1f}pt; }}
            QToolButton#unified_action_btn:checked {{ border: 2px solid {tokens["accent"]}; color: {tokens["text_primary"]}; }}
            QCheckBox {{ color: {tokens["text_primary"]}; }}
            QCheckBox#agenda_complete {{ background: transparent; border: none; }}
            QCheckBox::indicator {{ width: 20px; height: 20px; }}
        """,
                *opacities,
            )
        )
        color = tokens.get("text_primary", "#ffffff")
        self.customize_btn.setIcon(_ic(ICON.DISPLAY_STYLE, color=color))
        self.restore_btn.setIcon(_ic(ICON.CALENDAR, color=color))
        self.pin_btn.setIcon(_ic(ICON.ALWAYS_ON_TOP, color=color))
        for button in (self.restore_btn, self.customize_btn, self.pin_btn):
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setIconSize(QSize(16, 16))
            button.setFixedWidth(28)
        self.customize_btn.setIconSize(QSize(18, 18))
        self.customize_btn.setFixedWidth(32)
        self.more_btn.setFixedWidth(28)
        self.setWindowOpacity(1.0)
        self.cal_grid.set_theme_tokens(
            tokens,
            opacities=opacities,
            font_size=typography.calendar,
        )
        self.cal_grid.update_grid(self.controller._current_date())
        self._last_render_key = None
        self._refresh_locale_texts()

    def _sync_filter_buttons(self) -> None:
        for mode, btn in self._filter_buttons.items():
            btn.setChecked(mode == self._active_filter)
        text = (
            t("widget_mode.add_work", "업무 추가")
            if self._active_filter == "work"
            else t("widget_mode.add_directive", "지시·협조 추가")
            if self._active_filter == "directive"
            else t("widget_mode.action_add_schedule", "일정 추가")
            if self._active_filter == "schedule"
            else t("widget_mode.add_any", "+ 추가")
        )
        self.add_btn.setText(text)
        self.add_btn.setToolTip(text)
        self.add_btn.setAccessibleName(text)

    def _set_filter(self, mode: str) -> None:
        target = str(mode or "all").strip().lower()
        if target not in {"all", "schedule", "work", "directive"}:
            target = "all"
        if target == self._active_filter:
            self._sync_filter_buttons()
            return
        self._active_filter = target
        self.controller.main_window.settings.setValue("widget_mode_filter", target)
        self.clear_feedback()
        self._sync_filter_buttons()
        self._last_render_key = None
        self.update_agenda(self._last_items)

    def set_filter(self, mode: str) -> None:
        self._set_filter(mode)

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
            source = _safe_text(item.get("source")).lower()
            include = (
                (self._active_filter == "schedule" and item_kind == "schedule")
                or (self._active_filter == "work" and item_kind == "work" and source != "directive")
                or (self._active_filter == "directive" and source == "directive")
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
        self._sync_filter_buttons()
        labels = {
            "all": t("widget_mode.filter_all", "전체"),
            "schedule": t("widget_mode.filter_schedule", "일정"),
            "work": t("widget_mode.filter_work", "업무"),
            "directive": t("widget_mode.filter_directive", "지시"),
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
                widget.hide()
                widget.deleteLater()

    def update_header(self, target_date: QDate) -> None:
        label = _format_compact_date_with_weekday(target_date)
        self.date_label.setText(label)
        self.date_picker_btn.setText(label)
        self.date_picker_btn.setToolTip(t("widget_mode.pick_date", "날짜 선택"))
        self.date_picker_btn.setAccessibleName(
            f"{label} · {t('widget_mode.pick_date', '날짜 선택')}"
        )
        self.caption_label.setText(t("widget_mode.header_caption", "Selected day agenda and work"))
        self.status_chip.setText(_relative_widget_day(target_date))
        self.cal_grid.update_grid(target_date)

    def update_agenda(self, items: list[dict[str, object]]) -> None:
        self._last_items = [dict(item) for item in items]
        filtered_items = self._filter_items(self._last_items)
        if self._active_filter == "schedule":
            filtered_items = [item for item in filtered_items if not item.get("is_section")]
        render_key = tuple(
            [self._active_filter, read_widget_density(self.controller.main_window.settings).key]
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
                else t("widget_mode.filter_directive", "지시")
                if self._active_filter == "directive"
                else t("widget_mode.filter_work", "Work")
            )
        self.hint_label.setText(
            t("widget_mode.widget_hint_actions", "Tap a day to refocus")
            if visible_items
            else t("widget_mode.widget_hint_empty", "No items for the selected date.")
        )

        self._clear_items()
        if self._data_state != "ready":
            text = (
                t("widget_mode.loading", "일정을 불러오는 중…")
                if self._data_state == "loading"
                else t(
                    "widget_mode.load_delayed",
                    "일정을 아직 불러오지 못했습니다. 다시 시도해 주세요.",
                )
            )
            state_frame = QFrame(self.scroll_content)
            state_frame.setObjectName("unified_empty_state")
            state_layout = QVBoxLayout(state_frame)
            state_layout.setContentsMargins(16, 16, 16, 16)
            state_label = QLabel(text, state_frame)
            state_label.setObjectName("unified_empty")
            state_label.setWordWrap(True)
            state_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            state_layout.addWidget(state_label)
            self.scroll_layout.insertWidget(0, state_frame)
            if self._data_state == "delayed":
                retry = self._button(
                    t("widget_mode.retry", "다시 시도"), self.controller.retry_refresh
                )
                state_layout.addWidget(retry, 0, Qt.AlignmentFlag.AlignLeft)
            if not filtered_items:
                return
        if not filtered_items:
            empty_text = (
                t("widget_mode.empty_schedule_filter", "No schedules for this date.")
                if self._active_filter == "schedule"
                else t("widget_mode.empty_directive_filter", "이 날짜에 지시·협조사항이 없습니다.")
                if self._active_filter == "directive"
                else t("widget_mode.empty_work_filter", "No work for this date.")
                if self._active_filter == "work"
                else t("widget_mode.empty_panel", "No items for this date.")
            )
            empty_state = QFrame(self.scroll_content)
            empty_state.setObjectName("unified_empty_state")
            empty_layout = QVBoxLayout(empty_state)
            empty_layout.setContentsMargins(14, 12, 14, 12)
            empty_layout.setSpacing(8)

            empty = QLabel(empty_text, empty_state)
            empty.setWordWrap(True)
            empty.setObjectName("unified_empty")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setAccessibleName(empty_text)
            empty_layout.addWidget(empty)

            actions = QHBoxLayout()
            actions.setSpacing(7)
            actions.addStretch(1)

            add_action = QToolButton(empty_state)
            add_action.setObjectName("unified_primary_action")
            if self._active_filter == "work":
                action_label = t("panel.empty.add_routine", "루틴 만들기")
                add_action.clicked.connect(
                    lambda _checked=False: self.controller._open_task_dialog(
                        "", default_task_type="routine"
                    )
                )
            elif self._active_filter == "directive":
                action_label = t("widget_mode.add_directive", "지시·협조 추가")
                add_action.clicked.connect(
                    lambda _checked=False: self.controller._open_directive_dialog()
                )
            else:
                action_label = t("panel.empty.add_schedule", "일정 만들기")
                add_action.clicked.connect(
                    lambda _checked=False: self.controller.open_quick_add_dialog()
                )
            add_action.setText(action_label)
            add_action.setToolTip(action_label)
            add_action.setAccessibleName(action_label)
            add_action.setCursor(Qt.CursorShape.PointingHandCursor)
            add_action.setMinimumHeight(32)
            actions.addWidget(add_action)

            if self._active_filter != "all":
                show_all = QToolButton(empty_state)
                show_all.setObjectName("unified_action_btn")
                show_all_label = t("widget_mode.show_all", "전체 보기")
                show_all.setText(show_all_label)
                show_all.setToolTip(show_all_label)
                show_all.setAccessibleName(show_all_label)
                show_all.setCursor(Qt.CursorShape.PointingHandCursor)
                show_all.setMinimumHeight(32)
                show_all.clicked.connect(lambda _checked=False: self.set_filter("all"))
                actions.addWidget(show_all)

            actions.addStretch(1)
            empty_layout.addLayout(actions)
            self.scroll_layout.insertWidget(0, empty_state)
            return

        for insert_at, item in enumerate(filtered_items, start=int(self._data_state != "ready")):
            if item.get("is_section"):
                section = QLabel(_safe_text(item.get("title")), self.scroll_content)
                section.setObjectName("unified_section")
                self.scroll_layout.insertWidget(insert_at, section)
            else:
                widget = AgendaItemWidget(
                    _safe_text(item.get("title")) or t("widget_mode.untitled", "Untitled"),
                    _safe_text(item.get("time")),
                    is_task=bool(item.get("is_task")),
                    item=item,
                    controller=self.controller,
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
        self.controller.notify_hidden()

    def update_time(self) -> None:
        current_text = QTime.currentTime().toString("HH:mm")
        if self.clock_label.text() != current_text:
            self.clock_label.setText(current_text)
        today = QDate.currentDate()
        if today != self._last_today and self.isVisible():
            follow_today = self.controller._current_date() == self._last_today
            self._last_today = today
            if follow_today:
                self.controller.set_target_date(today)
            else:
                self.controller.refresh_data()
        self._schedule_next_clock_tick()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self._open_menu(event.globalPos())

    def _open_menu(self, global_pos) -> None:
        tokens = _widget_theme_tokens(self.controller.main_window)
        menu = QMenu(self)
        menu.setStyleSheet(_widget_mode_menu_stylesheet(tokens))
        density_menu = menu.addMenu(t("widget_mode.density", "목록 밀도"))
        current_density = read_widget_density(self.controller.main_window.settings).key
        for density in DENSITIES:
            action = density_menu.addAction(t(f"widget_mode.density_{density.key}", density.label))
            action.setCheckable(True)
            action.setChecked(density.key == current_density)
            action.triggered.connect(lambda checked=False, key=density.key: self.set_density(key))
        monthly = self.cal_grid.display_mode == "month"
        previous_week = menu.addAction(
            t("widget_mode.month_prev", "이전 달")
            if monthly
            else t("widget_mode.previous_week", "이전 주")
        )
        previous_week.triggered.connect(
            lambda: self.controller.set_target_date(
                self.controller._current_date().addMonths(-1)
                if monthly
                else self.controller._current_date().addDays(-7)
            )
        )
        next_week = menu.addAction(
            t("widget_mode.month_next", "다음 달")
            if monthly
            else t("widget_mode.next_week", "다음 주")
        )
        next_week.triggered.connect(
            lambda: self.controller.set_target_date(
                self.controller._current_date().addMonths(1)
                if monthly
                else self.controller._current_date().addDays(7)
            )
        )
        menu.addSeparator()

        directive_management_action = menu.addAction(t("menu.directive_status", "지시·협조 관리"))
        work_management_action = menu.addAction(t("menu.work_management", "전체 업무 관리"))
        menu.addSeparator()

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
        close_action = menu.addAction(t("widget_mode.return_main", "메인 화면으로"))
        hide_action = menu.addAction(t("widget_mode.hide_tray", "트레이로 숨기기"))
        recover_action = menu.addAction(t("widget_mode.recover_position", "화면 안으로 이동"))
        editor_action = menu.addAction(t("widget_mode.editor_title", "위젯 스타일 만들기"))
        manager = getattr(self.controller.main_window, "overlay_manager", None)
        if manager is not None:
            widget_menu = menu.addMenu(t("widget_mode.desktop_widgets", "바탕화면 위젯 관리"))
            manager.build_widgets_menu(widget_menu, _widget_mode_menu_stylesheet(tokens))
        selected = menu.exec(global_pos)
        if selected == editor_action:
            from calendar_app.presentation.dialogs.widget_style_editor_dialog import (
                WidgetStyleEditorDialog,
            )

            editor = WidgetStyleEditorDialog(self)
            if editor.exec():
                if editor.created_kind == "skin":
                    self.controller.set_skin(editor.created_id)
                elif editor.created_kind == "layout":
                    self.controller.set_layout(editor.created_id)
        elif selected == directive_management_action:
            self.controller.open_work_management("directive")
        elif selected == work_management_action:
            self.controller.open_work_management("schedule")
        elif selected == refresh_action:
            self.controller.force_refresh()
        elif selected == close_action:
            self.controller.return_to_main()
        elif selected == hide_action:
            self.controller.hide_to_tray()
        elif selected == recover_action:
            self.controller._handle_screen_change()

    def set_data_state(self, state):
        if state != self._data_state:
            self._data_state = state
            self._last_render_key = None

    def show_feedback(self, text, *, undo=False):
        self.feedback_label.setText(text)
        self.feedback_label.setAccessibleName(text)
        self.feedback_label.show()
        self.undo_btn.setVisible(undo)
        self._feedback_timer.start(8000 if undo else 4500)

    def clear_feedback(self) -> None:
        self._feedback_timer.stop()
        self.feedback_label.hide()
        self.undo_btn.hide()
        if hasattr(self, "controller"):
            self.controller._undo_completion = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.width() < 640 and self._active_layout_id in {"dashboard", "magazine"}
        if hasattr(self, "_compact_layout") and compact != self._compact_layout:
            self.apply_selected_layout(force=True)
        if not self.isMinimized() and self.isVisible():
            self.controller.save_size(self.size())


class UnifiedWidgetController:
    POSITION_KEY = "unified_widget_pos"
    SIZE_KEY = "unified_widget_size"

    def __init__(self, main_window, *, on_hidden=None):
        self.main_window = main_window
        self.widget = None
        self._on_hidden = on_hidden
        self._restoring_geometry = False
        self._changing_window_flags = False
        self._cache_refresh_pending = False
        self._last_display_signature = None
        self._items_cache = {}
        self._status_overrides = {}
        self._undo_completion = None
        self._load_timer = QTimer(main_window)
        self._load_timer.setSingleShot(True)
        self._load_timer.timeout.connect(self._loading_delayed)
        app = QApplication.instance()
        if app is not None:
            app.screenRemoved.connect(self._handle_screen_change)
            main_window.destroyed.connect(
                lambda: app.screenRemoved.disconnect(self._handle_screen_change)
            )

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
        if self.is_visible():
            self.hide_widget()
        else:
            self.show_widget()

    def show_widget(self, filter_mode: str | None = None) -> None:
        if self.widget is None:
            self.widget = UnifiedWidgetWindow(self)
            self._restore_geometry()
        if filter_mode is None:
            filter_mode = str(self.main_window.settings.value("widget_mode_filter", "all"))
        self.widget.set_filter(filter_mode)
        self.widget.show()
        self.widget.raise_()

    def hide_widget(self) -> None:
        if self.widget is not None:
            self._save_geometry()
            self.widget.hide()

    def prepare_shutdown(self) -> None:
        """Cancel delayed UI work before the Qt event loop begins teardown."""

        self._load_timer.stop()

    def is_visible(self) -> bool:
        return self.widget is not None and self.widget.isVisible()

    def notify_hidden(self) -> None:
        if getattr(self, "_changing_window_flags", False):
            return
        self._load_timer.stop()
        if self._on_hidden is not None:
            self._on_hidden()

    def return_to_main(self):
        coordinator = getattr(self.main_window, "_widget_mode_coordinator", None)
        if coordinator is not None:
            coordinator.return_to_main()
        else:
            self.hide_widget()
            self.main_window.showNormal()

    def hide_to_tray(self):
        coordinator = getattr(self.main_window, "_widget_mode_coordinator", None)
        if coordinator is not None:
            coordinator.hide_to_tray()
        else:
            self.hide_widget()

    def set_always_top(self, enabled, *, persist=True):
        if persist:
            self.main_window.settings.setValue("widget_mode_always_top", bool(enabled))
        if self.widget is None:
            return
        visible = self.widget.isVisible()
        geometry = self.widget.geometry()
        self._changing_window_flags = True
        try:
            self.widget.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(enabled))
            self.widget.setGeometry(geometry)
            self.widget.pin_btn.setChecked(bool(enabled))
            if visible:
                self.widget.show()
        finally:
            self._changing_window_flags = False

    def _run_main_dialog(self, callback, *args, **kwargs):
        pinned = self.is_visible() and bool(
            self.widget.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        )
        if pinned:
            self.set_always_top(False, persist=False)
        try:
            return callback(*args, **kwargs)
        finally:
            if pinned and self.is_visible():
                self.set_always_top(True, persist=False)

    def open_item(self, item):
        item_id = int(item.get("item_id") or 0)
        if item_id <= 0:
            return
        if item.get("read_only"):
            if self.widget is not None:
                self.widget.show_feedback(t("dialog.task.calendar_read_only", "읽기 전용 캘린더"))
            return
        if item.get("source") == "directive":
            callback = getattr(self.main_window, "open_directive_dialog", None)
            if callback:
                self._run_main_dialog(callback, task_id=item_id)
        else:
            callback = getattr(self.main_window, "open_modify_task_dialog", None)
            if callback:
                self._run_main_dialog(callback, item_id)

    def open_item_menu(self, item, global_pos) -> None:
        item_id = int(item.get("item_id") or 0)
        if item_id <= 0 or self.widget is None:
            return
        read_only = bool(item.get("read_only"))
        tokens = _widget_theme_tokens(self.main_window)
        menu = QMenu(self.widget)
        menu.setStyleSheet(_widget_mode_menu_stylesheet(tokens))
        open_action = menu.addAction(
            t(
                "widget_mode.menu_edit_directive"
                if item.get("source") == "directive"
                else "widget_mode.menu_edit_task",
                "열기/수정",
            )
        )
        if read_only:
            open_action.setText(t("dialog.task.calendar_read_only", "읽기 전용 캘린더"))
            open_action.setEnabled(False)
        completion_action = None
        if item.get("is_task") and not read_only:
            completion_action = menu.addAction(
                t("widget_mode.menu_reopen", "다시 진행")
                if item.get("completed")
                else t(
                    "widget_mode.menu_complete_directive"
                    if item.get("source") == "directive"
                    else "widget_mode.menu_complete_task",
                    "완료 처리",
                )
            )

        priority_actions = {}
        delete_action = None
        if not read_only:
            menu.addSeparator()
            priority_menu = menu.addMenu(t("widget_mode.menu_priority", "우선순위"))
            for key, label in (
                ("urgent", t("widget_mode.priority_urgent", "긴급")),
                ("high", t("widget_mode.priority_high", "높음")),
                ("normal", t("widget_mode.priority_normal", "보통")),
                ("low", t("widget_mode.priority_low", "낮음")),
            ):
                priority_actions[priority_menu.addAction(label)] = key
            menu.addSeparator()
            delete_action = menu.addAction(
                t(
                    "widget_mode.menu_delete_directive"
                    if item.get("source") == "directive"
                    else "widget_mode.menu_delete_task",
                    "삭제",
                )
            )

        selected = menu.exec(global_pos)
        if selected is None:
            return
        if selected == open_action:
            self.open_item(item)
        elif selected == completion_action:
            self.set_item_completed(item, not bool(item.get("completed")))
        elif selected == delete_action:
            self._delete_item(item)
        elif selected in priority_actions:
            self._set_item_priority(item, priority_actions[selected])

    def _set_item_priority(self, item, priority: str) -> None:
        callback = getattr(
            self.main_window,
            "handle_directive_priority_changed"
            if item.get("source") == "directive"
            else "handle_task_priority_changed",
            None,
        )
        if callable(callback):
            callback(int(item["item_id"]), priority)
            self.force_refresh()

    def _delete_item(self, item) -> None:
        item_id = int(item.get("item_id") or 0)
        if item_id <= 0:
            return
        if item.get("source") == "directive":
            callback = getattr(self.main_window, "delete_selected_directives", None)
            if not callable(callback):
                return
            previous = set(getattr(self.main_window, "selected_directive_ids", set()))
            try:
                self.main_window.selected_directive_ids = {item_id}
                self._run_main_dialog(callback)
            finally:
                self.main_window.selected_directive_ids = previous
        else:
            callback = getattr(self.main_window, "handle_task_deleted", None)
            if callable(callback):
                self._run_main_dialog(callback, item_id)

    def _write_status(self, item, status):
        callback = getattr(
            self.main_window,
            "handle_directive_status_changed"
            if item.get("source") == "directive"
            else "handle_task_status_changed",
            None,
        )
        try:
            success = callback and callback(int(item["item_id"]), status)
        except Exception:
            success = False
        if not success:
            self.widget.show_feedback(
                t("widget_mode.save_failed", "저장하지 못했습니다. 다시 시도해 주세요.")
            )
            self.widget._last_render_key = None
            self.widget.update_agenda(self.widget._last_items)
            return False
        self._status_overrides[(item["source"], item["item_id"])] = status
        self.force_refresh()
        return True

    def set_item_completed(self, item, completed):
        if not item.get("item_id"):
            return
        previous = str(item.get("status") or "pending")
        status = "completed" if completed else "pending"
        if self._write_status(item, status):
            self._undo_completion = (dict(item), previous)
            self.widget.show_feedback(
                t("widget_mode.saved_status", "업무 상태를 저장했습니다."), undo=True
            )

    def undo_completion(self):
        if self._undo_completion is None:
            return
        item, previous = self._undo_completion
        if self._write_status(item, previous):
            self._undo_completion = None
            self.widget.show_feedback(t("widget_mode.undone", "이전 상태로 되돌렸습니다."))

    def _effective_status(self, source, item_id, status):
        key = (source, item_id)
        override = self._status_overrides.get(key)
        if override == status:
            self._status_overrides.pop(key, None)
        return override if override is not None else status

    def _loading_delayed(self):
        if self.is_visible() and self._cache_refresh_pending:
            self.widget.set_data_state("delayed")
            self.widget.update_agenda(self.widget._last_items)

    def retry_refresh(self):
        self._load_timer.stop()
        self.main_window.schedule_panel_refresh(center=True, right=True)
        self.force_refresh()

    def save_position(self, pos: QPoint) -> None:
        del pos
        self._save_geometry()

    def save_size(self, size: QSize) -> None:
        if self._restoring_geometry:
            return
        layout_id = self.widget.active_layout_id() if self.widget is not None else "stacked"
        self.main_window.settings.setValue(
            self._layout_size_key(layout_id, self._calendar_visible_for_layout(layout_id)), size
        )
        self._save_geometry(size_override=size)

    def _save_geometry(self, *, size_override: QSize | None = None) -> None:
        if self.widget is None or self._restoring_geometry:
            return
        screen = self.widget.screen()
        if screen is None:
            screen_info = best_available_geometry(
                QApplication.screens(), point=self.widget.frameGeometry().center()
            )
            if screen_info is None:
                return
            available, screen_name = screen_info
        else:
            available, screen_name = screen.availableGeometry(), screen.name()
        rect = self.widget.geometry()
        if size_override is not None:
            rect.setSize(size_override)
        raw = serialize_geometry(rect, available, screen_name)
        layout_id = self.widget.active_layout_id()
        self.main_window.settings.setValue(
            geometry_key(
                self._geometry_layout_id(layout_id, self._calendar_visible_for_layout(layout_id))
            ),
            raw,
        )

    def _restore_geometry(self, *, preserve_position_if_new: bool = False) -> None:
        if self.widget is None:
            return
        layout_id = self.widget.active_layout_id()
        calendar_visible = self._calendar_visible_for_layout(layout_id)
        payload = deserialize_geometry(
            self.main_window.settings.value(
                geometry_key(self._geometry_layout_id(layout_id, calendar_visible))
            )
        )
        screen_info = best_available_geometry(
            QApplication.screens(),
            screen_name=str(payload.get("screen") or "") if payload else "",
        )
        if screen_info is None:
            return
        available, _screen_name = screen_info
        if payload is not None:
            target = restore_rect(payload, available)
        else:
            stored_pos = self.main_window.settings.value(self.POSITION_KEY)
            stored_size = self.saved_size_for_layout(
                get_widget_mode_layout(layout_id), calendar_visible=calendar_visible
            )
            if preserve_position_if_new:
                target = self.widget.geometry()
                target.setSize(stored_size)
                target = clamp_rect(target, available)
            elif isinstance(stored_pos, QPoint):
                target = legacy_rect(stored_pos, stored_size, available)
            else:
                target = clamp_rect(
                    self.widget.geometry().translated(
                        available.right() - self.widget.width() - 39 - self.widget.x(),
                        available.top() + 40 - self.widget.y(),
                    ),
                    available,
                )
        self._restoring_geometry = True
        try:
            self.widget.setGeometry(target)
        finally:
            self._restoring_geometry = False

    def _handle_screen_change(self, _screen=None) -> None:
        if not self.is_visible():
            return
        screen_info = best_available_geometry(
            QApplication.screens(), point=self.widget.frameGeometry().center()
        )
        if screen_info is None:
            return
        available, _screen_name = screen_info
        self._restoring_geometry = True
        try:
            self.widget.setGeometry(clamp_rect(self.widget.geometry(), available))
        finally:
            self._restoring_geometry = False
        self._save_geometry()

    def _calendar_visible_for_layout(self, layout_id: str) -> bool:
        layout_spec = get_widget_mode_layout(layout_id)
        if not any(section == "calendar" for section, *_ in layout_spec.placements):
            return True
        return read_widget_calendar_visibility(self.main_window.settings, layout_spec.layout_id)

    @staticmethod
    def _geometry_layout_id(layout_id: str, calendar_visible: bool) -> str:
        return layout_id if calendar_visible else f"{layout_id}_calendar_hidden"

    def _layout_size_key(self, layout_id: str, calendar_visible: bool = True) -> str:
        suffix = "" if calendar_visible else "_calendar_hidden"
        return f"{self.SIZE_KEY}_{layout_id}{suffix}"

    def saved_size_for_layout(self, layout_spec, *, calendar_visible: bool | None = None) -> QSize:
        if calendar_visible is None:
            calendar_visible = self._calendar_visible_for_layout(layout_spec.layout_id)
        stored = self.main_window.settings.value(
            self._layout_size_key(layout_spec.layout_id, calendar_visible)
        )
        if stored is None and layout_spec.layout_id == "stacked" and calendar_visible:
            stored = self.main_window.settings.value(self.SIZE_KEY)
        if isinstance(stored, QSize) and stored.width() > 40 and stored.height() > 40:
            return stored
        width, height = layout_spec.preferred_size
        if not calendar_visible and any(
            section == "calendar" for section, *_ in layout_spec.placements
        ):
            if layout_spec.layout_id in {"dashboard", "magazine"}:
                width = min(width, 420)
            else:
                height = max(360, height - 170)
        return QSize(width, height)

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
        self._save_geometry()
        write_widget_mode_layout_id(self.main_window.settings, layout_id)
        if self.widget is None:
            return
        self._restoring_geometry = True
        try:
            self.widget.apply_selected_layout(resize_to_layout=True)
        finally:
            self._restoring_geometry = False
        self._restore_geometry()
        self.widget._style_signature = None
        self.widget.apply_theme()

    def force_refresh(self) -> None:
        self._cache_refresh_pending = False
        if self.widget is not None:
            self.widget.set_data_state("ready")
        self._last_display_signature = None
        self._items_cache.clear()
        self.refresh_data()

    def open_quick_add_dialog(self) -> None:
        self._open_task_dialog("", default_task_type="schedule")

    def _open_directive_dialog(self) -> None:
        callback = getattr(self.main_window, "open_directive_dialog", None)
        if callable(callback):
            self._run_main_dialog(callback, initial_date=self._current_date())

    def open_work_management(self, start_tab: str = "schedule") -> None:
        callback = getattr(self.main_window, "open_work_management_dialog", None)
        if callable(callback):
            self._run_main_dialog(callback, start_tab=start_tab)

    def handle_quick_add(self, text: str) -> None:
        self._open_task_dialog(text)

    def _open_task_dialog(self, text: str, *, default_task_type: str = "directive") -> None:
        if default_task_type == "directive":
            self._open_directive_dialog()
            return
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
        self._run_main_dialog(self.main_window.open_task_dialog, **kwargs)

    def set_target_date(self, target: QDate) -> None:
        if not isinstance(target, QDate) or not target.isValid():
            return
        if self.widget is not None:
            self.widget.clear_feedback()
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
        show_completed = (
            str(self.main_window.settings.value("widget_mode_show_completed", "false")).lower()
            == "true"
        )
        for row in cache.get("routine_rows", []) or []:
            if not isinstance(row, dict):
                continue
            raw_status = _normalize_status(row.get("status"))
            if row.get("is_completed") in (1, True):
                raw_status = "completed"
            status = self._effective_status("task", row.get("id"), raw_status)
            completed = status in {"done", "completed"}
            if completed and not show_completed:
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
                        "time": "",
                        "is_task": True,
                        "item_kind": "work",
                        "item_id": row.get("id"),
                        "source": "task",
                        "status": status,
                        "completed": completed,
                    }
                )

        directive_items = []
        overdue_directive_items = []
        undated_directive_items = []
        done_statuses = {"done", "completed", "deferred", "canceled", "cancelled"}
        for row in cache.get("directive_rows", []) or []:
            if not isinstance(row, (tuple, list)) or len(row) < 5:
                continue
            status = self._effective_status("directive", row[0], _normalize_status(row[2]))
            completed = status in {"done", "completed"}
            if status in done_statuses and not (completed and show_completed):
                continue
            deadline_qd = _parse_qdate(row[4])
            directive_item = {
                "title": _safe_text(row[1]) or t("widget_mode.untitled", "Untitled"),
                "time": "",
                "is_task": True,
                "item_kind": "work",
                "item_id": row[0],
                "source": "directive",
                "status": status,
                "completed": completed,
            }
            if deadline_qd.isValid() and deadline_qd == target:
                directive_items.append(directive_item)
            elif target == QDate.currentDate() and not completed:
                if deadline_qd.isValid() and deadline_qd < target:
                    directive_item["time"] = _format_compact_date_with_weekday(deadline_qd)
                    overdue_directive_items.append(directive_item)
                elif not deadline_qd.isValid():
                    undated_directive_items.append(directive_item)

        if routine_items:
            items.append(
                {
                    "title": t("widget_mode.section_routine_today", "Work"),
                    "is_section": True,
                    "section_kind": "work",
                }
            )
            items.extend(routine_items)
        if directive_items:
            items.append(
                {
                    "title": t("widget_mode.section_directive_today", "Directive"),
                    "is_section": True,
                    "section_kind": "work",
                }
            )
            items.extend(directive_items)
        if overdue_directive_items:
            items.append(
                {
                    "title": t("widget_mode.section_directive_overdue", "기한 지난 지시·협조"),
                    "is_section": True,
                    "section_kind": "work",
                }
            )
            items.extend(overdue_directive_items)
        if undated_directive_items:
            items.append(
                {
                    "title": t("widget_mode.section_directive_no_deadline", "기한 없는 지시·협조"),
                    "is_section": True,
                    "section_kind": "work",
                }
            )
            items.extend(undated_directive_items)
        return items

    def _schedule_items_for_date(self, target: QDate) -> list[dict[str, object]]:
        rows = self._schedule_rows_for_date(target)
        if not rows:
            return []
        items = [
            {
                "title": t("widget_mode.filter_schedule", "일정"),
                "is_section": True,
                "section_kind": "schedule",
            }
        ]
        for row in rows:
            items.append(
                {
                    "title": _safe_text(row.get("name")) or t("widget_mode.untitled", "Untitled"),
                    "time": _format_widget_datetime_label(
                        row.get("deadline"), reference_date=target
                    ),
                    "is_task": False,
                    "item_kind": "schedule",
                    "item_id": row.get("id"),
                    "source": "task",
                    "read_only": bool(row.get("read_only") or row.get("is_subscription")),
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
            self._load_timer.stop()
            return True
        if self._cache_refresh_pending:
            return False
        if hasattr(self.main_window, "schedule_panel_refresh"):
            self.main_window.schedule_panel_refresh(center=not has_schedule, right=not has_work)
        self._cache_refresh_pending = True
        self._load_timer.start(10000)
        return False

    def refresh_data(self):
        if self.widget is None or not self.widget.isVisible():
            return

        self.widget.apply_theme()
        target = self._current_date()
        self.widget.update_header(target)
        if not self._ensure_cache_coverage(target):
            if self.widget._data_state != "delayed":
                self.widget.set_data_state("loading")
        else:
            self.widget.set_data_state("ready")

        signature = self._display_signature(target)
        if signature == self._last_display_signature and self.widget._last_render_key is not None:
            return

        items = self._get_cached_items(signature)
        if items is None:
            items = []
            items.extend(self._schedule_items_for_date(target))
            items.extend(self._work_items_for_date(target))
            self._remember_items(signature, items)

        self._last_display_signature = signature
        self.widget.update_agenda(items)
