# -*- coding: utf-8 -*-
"""Drag-created multi-day ranges stay visible: cell highlight, badge and dialog summary."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QLocale, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QCheckBox, QDateEdit, QLabel, QWidget
import pytest

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.main_window.action_handlers_tasks import TaskActionsMixin
from calendar_app.presentation.widgets.ui_components import (
    ClickableCell,
    create_range_badge_text,
)

START = QDate(2026, 8, 10)


class RangeHost(TaskActionsMixin, QWidget):
    def __init__(self):
        super().__init__()
        self.resize(700, 300)
        self.left_panel_mode = "today"
        self.selected_task_ids = set()
        self.selected_directive_ids = set()
        self.selection_status_lbl = QLabel(self)
        self.refreshes = []
        self.dialog_seen = None
        self.dialog_hook = None
        self._create_range_preview_cells = []
        self._calendar_cells_by_date = {}
        self.cells = []
        for index in range(7):
            date = START.addDays(index)
            cell = ClickableCell(date, parent=self)
            cell.setGeometry(index * 100, 120, 100, 80)
            day = QLabel(str(date.day()), cell)
            day.setObjectName("dayNumLabel")
            self._calendar_cells_by_date[date.toString("yyyy-MM-dd")] = cell
            self.cells.append(cell)

    def schedule_panel_refresh(self, **kwargs):
        self.refreshes.append(kwargs)

    def update_task_selection_status(self):
        self.selection_status_lbl.setText("hint")

    def open_task_dialog(self, *args):
        # Captures what the calendar shows while the modal dialog is open.
        self.dialog_seen = {
            "args": args,
            "preview": [cell.property("create_range_preview") for cell in self.cells],
            "badge": self._create_range_badge.isVisible(),
            "badge_text": self._create_range_badge.text(),
        }
        if self.dialog_hook:
            self.dialog_hook()


@pytest.fixture
def host():
    app = QApplication.instance() or QApplication([])
    widget = RangeHost()
    widget.show()
    app.processEvents()
    yield app, widget
    widget.close()
    widget.deleteLater()
    app.processEvents()


def _previewed(widget):
    return [cell.target_date for cell in widget.cells if cell.property("create_range_preview")]


def test_badge_text_names_both_ends_with_weekdays_and_count():
    end = START.addDays(4)
    pattern = t("calendar.range_badge_date", "M월 d일 (ddd)")
    text = create_range_badge_text(START, end)
    assert QLocale().toString(START, pattern) in text
    assert QLocale().toString(end, pattern) in text
    assert "5" in text
    single = create_range_badge_text(START, START)
    assert QLocale().toString(START, pattern) in single
    assert "→" not in single


def test_drag_preview_marks_ends_and_floats_a_badge_over_the_pointer_cell(host):
    app, widget = host
    widget.cells[0]._update_create_range_preview(START.addDays(3), START.addDays(1))
    app.processEvents()

    assert _previewed(widget) == [START.addDays(i) for i in (1, 2, 3)]
    assert widget.cells[1].property("create_range_start") is True
    assert widget.cells[3].property("create_range_end") is True
    assert widget.cells[2].property("create_range_start") is False
    assert widget.cells[2].property("create_range_end") is False

    badge = widget._create_range_badge
    assert badge.isVisible()
    assert badge.text() == create_range_badge_text(START.addDays(1), START.addDays(3))
    assert badge.accessibleName() == badge.text()
    # The badge sits above the pointer's cell (the drag end) and inside the window.
    pointer_cell = widget.cells[1]
    assert badge.geometry().bottom() <= pointer_cell.geometry().top()
    assert abs(badge.geometry().center().x() - pointer_cell.geometry().center().x()) <= 2
    assert badge.x() >= 0 and badge.geometry().right() <= widget.width()

    ClickableCell._clear_create_range_preview_for_app(widget)
    assert _previewed(widget) == []
    assert not badge.isVisible()
    assert widget.selection_status_lbl.text() == "hint"


def test_range_stays_highlighted_while_the_create_dialog_is_open(host):
    app, widget = host
    widget._open_cell_range_dialog(START.addDays(4), START.addDays(2))

    seen = widget.dialog_seen
    assert seen["args"] == (START.addDays(2), None, START.addDays(4))
    assert seen["preview"] == [2 <= i <= 4 for i in range(7)]
    assert seen["badge"] is True
    assert seen["badge_text"] == create_range_badge_text(START.addDays(2), START.addDays(4))
    # Cleared once the dialog closes.
    assert _previewed(widget) == []
    assert not widget._create_range_badge.isVisible()
    assert widget._create_range_pinned is None


def test_pinned_range_follows_dates_changed_in_the_dialog(host):
    app, widget = host
    dialog = QWidget()
    dialog.start_date = QDateEdit(START, dialog)
    dialog.end_date = QDateEdit(START.addDays(1), dialog)
    dialog.multiple_days_check = QCheckBox(dialog)
    dialog.show()
    observed = []

    def _edit_dates():
        widget._bind_create_range_preview(dialog)
        dialog.end_date.setDate(START.addDays(5))
        observed.append(_previewed(widget))
        observed.append(widget._create_range_badge.text())
        dialog.start_date.setDate(START.addDays(3))
        observed.append(_previewed(widget))
        dialog.end_date.hide()  # single-day schedule: only the start date counts
        dialog.multiple_days_check.setChecked(True)
        observed.append(_previewed(widget))

    widget.dialog_hook = _edit_dates
    widget._open_cell_range_dialog(START, START.addDays(1))
    dialog.close()

    assert observed[0] == [START.addDays(i) for i in range(6)]
    assert observed[1] == create_range_badge_text(START, START.addDays(5))
    assert observed[2] == [START.addDays(i) for i in (3, 4, 5)]
    assert observed[3] == [START.addDays(3)]
    assert _previewed(widget) == []


def test_binding_is_inert_without_a_pinned_range(host):
    _app, widget = host
    dialog = QWidget()
    dialog.start_date = QDateEdit(START, dialog)
    dialog.end_date = QDateEdit(START, dialog)
    widget._bind_create_range_preview(dialog)
    dialog.end_date.setDate(START.addDays(2))
    assert _previewed(widget) == []
    dialog.deleteLater()


def test_range_stylesheet_gives_only_the_ends_the_filled_pill():
    from calendar_app.presentation.theme.style_builder import build_global_stylesheet

    QApplication.instance() or QApplication([])
    qss = build_global_stylesheet(
        family="Pretendard, sans-serif",
        base_pt=11,
        theme_color="#22c3ca",
        text_theme="dark",
        panel_base_color="#1c1c1c",
    )
    ends = (
        'ClickableCell[create_range_preview="true"][create_range_start="true"] '
        'QLabel#dayNumLabel,\n        ClickableCell[create_range_preview="true"]'
        '[create_range_end="true"] QLabel#dayNumLabel'
    )
    assert ends in qss
    middle = qss.split('ClickableCell[create_range_preview="true"] QLabel#dayNumLabel {')[1]
    assert "background-color" not in middle.split("}")[0]


def test_range_fill_is_painted_inside_the_calendar_surface(host):
    """The surface's own stylesheet must not hide the range (the reported bug)."""
    from PyQt6.QtWidgets import QFrame

    from calendar_app.presentation.calendar.month_renderer import _calendar_surface_style

    app, _widget = host
    tokens = {
        "accent": "#c5a3f5",
        "bg_main": "#121827",
        "cell_bg": "#121827",
        "divider": "#2a3245",
        "text_primary": "#f4f7fb",
        "text_inverse": "#121827",
    }
    surface = QFrame()
    surface.setObjectName("calendar_surface")
    surface.setStyleSheet(_calendar_surface_style(tokens=tokens))
    surface.resize(700, 120)
    surface.selection_status_lbl = QLabel(surface)
    surface._create_range_preview_cells = []
    surface._calendar_cells_by_date = {}
    cells = []
    for index in range(7):
        date = START.addDays(index)
        cell = ClickableCell(date, parent=surface)
        cell.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        cell.setGeometry(index * 100, 20, 100, 90)
        day = QLabel(str(date.day()), cell)
        day.setObjectName("dayNumLabel")
        surface._calendar_cells_by_date[date.toString("yyyy-MM-dd")] = cell
        cells.append(cell)
    # The end day is also the "selected date" and the start has keyboard focus,
    # as in the reported screenshot; the range colours must still win.
    cells[1].setProperty("keyboardFocused", True)
    cells[4].setProperty("selected_date", True)
    surface.show()
    app.processEvents()

    ClickableCell.show_create_range_preview(surface, START.addDays(1), START.addDays(4))
    app.processEvents()

    def centre(cell):
        # Grab the opaque surface, not the cell alone, so translucent fills are
        # composited the way they appear on screen.
        image = surface.grab().toImage()
        return image.pixelColor(cell.x() + cell.width() // 2, cell.y() + cell.height() - 12)

    outside, start, middle, end = (centre(cells[i]) for i in (0, 1, 2, 4))
    accent = QColor("#c5a3f5")

    def distance(a, b):
        return abs(a.red() - b.red()) + abs(a.green() - b.green()) + abs(a.blue() - b.blue())

    # Range days get a light accent wash; the ends a little more than the middle.
    assert distance(middle, accent) < distance(outside, accent) - 25
    assert distance(start, accent) < distance(middle, accent)
    assert distance(end, accent) < distance(middle, accent)
    surface.close()
    surface.deleteLater()


def test_task_drop_states_are_painted_inside_the_calendar_surface(host):
    """Move/copy drop targets and the dropped span show inside the month surface."""
    from PyQt6.QtWidgets import QFrame

    from calendar_app.presentation.calendar.month_renderer import _calendar_surface_style

    app, _widget = host
    tokens = {
        "accent": "#c5a3f5",
        "bg_main": "#121827",
        "cell_bg": "#121827",
        "divider": "#2a3245",
        "text_primary": "#f4f7fb",
        "text_inverse": "#121827",
    }
    surface = QFrame()
    surface.setObjectName("calendar_surface")
    surface.setStyleSheet(_calendar_surface_style(tokens=tokens))
    surface.resize(500, 120)
    cells = []
    for index in range(5):
        cell = ClickableCell(START.addDays(index), parent=surface)
        cell.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        cell.setGeometry(index * 100, 20, 100, 90)
        day = QLabel(str(index + 1), cell)
        day.setObjectName("dayNumLabel")
        cells.append(cell)
    surface.show()
    app.processEvents()

    def paint(cell, **props):
        for key, value in props.items():
            cell.setProperty(key, value)
        cell.style().unpolish(cell)
        cell.style().polish(cell)
        app.processEvents()
        image = surface.grab().toImage()
        return image.pixelColor(cell.x() + cell.width() // 2, cell.y() + cell.height() - 12)

    plain = paint(cells[0])
    span = paint(cells[1], drag_range_preview=True, drag_range_start=True)
    move = paint(cells[2], drag_mode="move")
    move_pulse = paint(cells[2], drag_pulse="on")
    copy = paint(cells[3], drag_mode="copy")

    def differs(a, b, minimum=30):
        return (
            abs(a.red() - b.red()) + abs(a.green() - b.green()) + abs(a.blue() - b.blue())
            >= minimum
        )

    assert differs(span, plain)
    accent = QColor("#c5a3f5")

    def to_accent(color):
        return (
            abs(color.red() - accent.red())
            + abs(color.green() - accent.green())
            + abs(color.blue() - accent.blue())
        )

    # The target day is the strongest accent: stronger than the dropped span.
    assert differs(move, plain)
    assert to_accent(move) < to_accent(span) < to_accent(plain)
    assert differs(move_pulse, move, minimum=10)
    assert differs(copy, move)  # copy reads as a different colour from move
    surface.close()
    surface.deleteLater()


def test_today_number_stays_readable_on_a_range_end(host):
    """Today as a range start/end keeps its pill text, not accent-on-accent."""
    from PyQt6.QtGui import QPalette
    from PyQt6.QtWidgets import QFrame

    from calendar_app.presentation.calendar.month_renderer import (
        _calendar_surface_style,
        _today_pill_colors,
    )

    app, _widget = host
    tokens = {
        "accent": "#c5a3f5",
        "bg_main": "#121827",
        "cell_bg": "#121827",
        "divider": "#2a3245",
        "text_primary": "#f4f7fb",
        "text_inverse": "#121827",
    }
    _fill, today_text = _today_pill_colors(tokens)
    surface = QFrame()
    surface.setObjectName("calendar_surface")
    surface.setStyleSheet(_calendar_surface_style(tokens=tokens))
    labels = []
    for edge in ("create_range_start", "create_range_end"):
        cell = ClickableCell(START, parent=surface)
        day = QLabel("17", cell)
        day.setObjectName("dayNumLabel")
        cell.setProperty("is_today", True)
        cell.setProperty("create_range_preview", True)
        cell.setProperty(edge, True)
        labels.append(day)
    surface.show()
    app.processEvents()

    for day in labels:
        day.ensurePolished()
        text = day.palette().color(QPalette.ColorRole.WindowText)
        assert text == QColor(today_text)
    surface.close()
    surface.deleteLater()
