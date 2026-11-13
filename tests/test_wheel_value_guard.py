# -*- coding: utf-8 -*-
"""Mouse wheels scroll content without editing focused or unfocused controls."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication, QDate, QDateTime, QEvent, QPoint, QPointF, Qt, QTime
from PyQt6.QtGui import QFont, QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QCalendarWidget,
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QDial,
    QDialog,
    QDoubleSpinBox,
    QFontComboBox,
    QLabel,
    QLineEdit,
    QScrollArea,
    QScrollBar,
    QSlider,
    QSpinBox,
    QStyle,
    QStyleOptionSpinBox,
    QTabBar,
    QTableView,
    QTableWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)
import pytest

from calendar_app.presentation.widgets.wheel_value_guard import install_wheel_value_guard


@pytest.fixture
def wheel_app():
    application = QApplication.instance() or QApplication([])
    install_wheel_value_guard(application)
    yield application
    application.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _wheel(widget, *, angle=None, pixels=None, modifiers=Qt.KeyboardModifier.NoModifier):
    point = widget.rect().center()
    event = QWheelEvent(
        QPointF(point),
        QPointF(widget.mapToGlobal(point)),
        pixels if pixels is not None else QPoint(),
        angle if angle is not None else QPoint(0, 120),
        Qt.MouseButton.NoButton,
        modifiers,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(widget, event)
    return event


def _control(kind):
    if kind == "integer":
        widget = QSpinBox()
        widget.setRange(-100, 100)
        widget.setValue(20)
        return widget, widget.value
    if kind == "decimal":
        widget = QDoubleSpinBox()
        widget.setRange(-100.0, 100.0)
        widget.setValue(12.5)
        return widget, widget.value
    if kind == "date":
        widget = QDateEdit(QDate(2026, 11, 5))
        widget.setCurrentSection(QDateEdit.Section.YearSection)
        return widget, widget.date
    if kind == "time":
        widget = QTimeEdit(QTime(10, 30))
        widget.setCurrentSection(QTimeEdit.Section.HourSection)
        return widget, widget.time
    if kind == "datetime":
        widget = QDateTimeEdit(QDateTime(QDate(2026, 11, 5), QTime(10, 30)))
        widget.setCurrentSection(QDateTimeEdit.Section.YearSection)
        return widget, widget.dateTime
    if kind in {"combo", "editable-combo"}:
        widget = QComboBox()
        widget.addItems(["First", "Second", "Third"])
        widget.setCurrentIndex(1)
        widget.setEditable(kind == "editable-combo")
        return widget, lambda: (widget.currentIndex(), widget.currentText())
    if kind == "font":
        widget = QFontComboBox()
        widget.setCurrentFont(QFont("Malgun Gothic"))
        return widget, lambda: widget.currentFont().toString()
    if kind in {"horizontal-slider", "vertical-slider", "dial"}:
        widget = (
            QDial()
            if kind == "dial"
            else QSlider(
                Qt.Orientation.Horizontal
                if kind == "horizontal-slider"
                else Qt.Orientation.Vertical
            )
        )
        widget.setRange(0, 100)
        widget.setValue(50)
        return widget, widget.value
    if kind == "tabs":
        widget = QTabBar()
        for label in ("First", "Second", "Third"):
            widget.addTab(label)
        widget.setCurrentIndex(1)
        return widget, widget.currentIndex
    raise AssertionError(f"Unknown test control: {kind}")


@pytest.mark.parametrize(
    "kind",
    (
        "integer",
        "decimal",
        "date",
        "time",
        "datetime",
        "combo",
        "editable-combo",
        "font",
        "horizontal-slider",
        "vertical-slider",
        "dial",
        "tabs",
    ),
)
@pytest.mark.parametrize("focused", (False, True))
def test_wheel_never_edits_controls_even_when_focused(wheel_app, kind, focused):
    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    control, read_value = _control(kind)
    other = QLineEdit()
    layout.addWidget(control)
    layout.addWidget(other)
    dialog.show()
    dialog.activateWindow()
    (control if focused else other).setFocus()
    wheel_app.processEvents()
    focus = wheel_app.focusWidget()
    if focused:
        assert focus is control or (focus is not None and control.isAncestorOf(focus))
    else:
        assert focus is other
    before = read_value()
    try:
        for delta in (120, -120, 360):
            _wheel(control, angle=QPoint(0, delta))
            assert read_value() == before
        _wheel(control, pixels=QPoint(0, -30), angle=QPoint())
        _wheel(control, angle=QPoint(120, 0))
        _wheel(control, modifiers=Qt.KeyboardModifier.ControlModifier)
        assert read_value() == before
    finally:
        dialog.close()
        dialog.deleteLater()


@pytest.mark.parametrize("kind", ("integer", "decimal", "date", "time", "editable-combo"))
def test_wheel_delivered_to_inner_editor_cannot_bypass_guard(wheel_app, kind):
    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    control, read_value = _control(kind)
    layout.addWidget(control)
    dialog.show()
    editor = control.lineEdit()
    editor.setFocus()
    wheel_app.processEvents()
    before = read_value()
    try:
        _wheel(editor)
        _wheel(editor, angle=QPoint(0, -120))
        assert read_value() == before
    finally:
        dialog.close()
        dialog.deleteLater()


def test_install_is_idempotent_and_keeps_one_guard(wheel_app):
    first = install_wheel_value_guard(wheel_app)
    for _ in range(5):
        assert install_wheel_value_guard(wheel_app) is first


def test_guard_keeps_keyboard_and_pointer_editing(wheel_app):
    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    spin = QSpinBox()
    spin.setRange(0, 100)
    spin.setValue(20)
    combo = QComboBox()
    combo.addItems(["First", "Second", "Third"])
    layout.addWidget(spin)
    layout.addWidget(combo)
    dialog.show()
    wheel_app.processEvents()
    try:
        spin.setFocus()
        QTest.keyClick(spin, Qt.Key.Key_Up)
        assert spin.value() == 21
        option = QStyleOptionSpinBox()
        spin.initStyleOption(option)
        up = spin.style().subControlRect(
            QStyle.ComplexControl.CC_SpinBox, option, QStyle.SubControl.SC_SpinBoxUp, spin
        )
        QTest.mouseClick(spin, Qt.MouseButton.LeftButton, pos=up.center())
        assert spin.value() == 22
        combo.setFocus()
        QTest.keyClick(combo, Qt.Key.Key_Down)
        assert combo.currentIndex() == 1
    finally:
        dialog.close()
        dialog.deleteLater()


def test_control_wheel_scrolls_parent_once_without_changing_value(wheel_app):
    area = QScrollArea()
    area.setWidgetResizable(True)
    body = QWidget()
    layout = QVBoxLayout(body)
    label = QLabel("Scroll reference")
    spin = QSpinBox()
    spin.setValue(20)
    layout.addWidget(label)
    layout.addWidget(spin)
    spacer = QWidget()
    spacer.setMinimumHeight(1200)
    layout.addWidget(spacer)
    area.setWidget(body)
    area.resize(360, 220)
    area.show()
    wheel_app.processEvents()
    bar = area.verticalScrollBar()
    try:
        assert bar.maximum() > 0
        _wheel(area.viewport(), angle=QPoint(0, -120))
        reference = bar.value()
        assert reference > 0
        bar.setValue(0)
        for _ in range(3):
            install_wheel_value_guard(wheel_app)
        spin.setFocus()
        blocked = _wheel(spin.lineEdit(), angle=QPoint(0, -120))
        assert spin.value() == 20
        assert blocked.isAccepted()
        assert bar.value() == reference
    finally:
        area.close()
        area.deleteLater()


def test_guard_covers_controls_in_a_new_secondary_window(wheel_app):
    owner = QWidget()
    dialog = QDialog(owner)
    layout = QVBoxLayout(dialog)
    spin = QSpinBox()
    spin.setValue(30)
    layout.addWidget(spin)
    dialog.show()
    wheel_app.processEvents()
    try:
        _wheel(spin, angle=QPoint(0, -120))
        assert spin.value() == 30
    finally:
        dialog.close()
        dialog.deleteLater()
        owner.deleteLater()


def test_table_cell_combo_is_an_editor_not_a_popup_scroll_list(wheel_app):
    table = QTableWidget(1, 1)
    combo = QComboBox(table)
    combo.addItems(["Pending", "In progress", "Complete"])
    combo.setCurrentIndex(1)
    table.setCellWidget(0, 0, combo)
    table.show()
    wheel_app.processEvents()
    try:
        _wheel(combo, angle=QPoint(0, 120))
        _wheel(combo, angle=QPoint(0, -120))
        assert combo.currentIndex() == 1
    finally:
        table.close()
        table.deleteLater()


def test_calendar_popup_view_cannot_change_month_or_date_with_wheel(wheel_app):
    calendar = QCalendarWidget()
    calendar.setSelectedDate(QDate(2026, 11, 5))
    calendar.show()
    wheel_app.processEvents()
    viewport = calendar.findChild(QTableView).viewport()
    before = calendar.yearShown(), calendar.monthShown(), calendar.selectedDate()
    try:
        _wheel(viewport)
        _wheel(viewport, angle=QPoint(0, -120))
        assert (calendar.yearShown(), calendar.monthShown(), calendar.selectedDate()) == before
    finally:
        calendar.close()
        calendar.deleteLater()


def test_scrollbar_wheel_remains_content_scrolling(wheel_app):
    bar = QScrollBar(Qt.Orientation.Vertical)
    bar.setRange(0, 1000)
    bar.setValue(500)
    bar.show()
    wheel_app.processEvents()
    try:
        _wheel(bar, angle=QPoint(0, -120))
        assert bar.value() > 500
    finally:
        bar.close()
        bar.deleteLater()


def test_open_combo_popup_can_scroll_its_list_without_committing_a_value(wheel_app):
    combo = QComboBox()
    combo.addItems([f"Item {index}" for index in range(150)])
    combo.setCurrentIndex(75)
    combo.show()
    combo.showPopup()
    wheel_app.processEvents()
    view = combo.view()
    bar = view.verticalScrollBar()
    before = bar.value()
    try:
        assert bar.maximum() > 0
        _wheel(view.viewport(), angle=QPoint(0, -120))
        assert bar.value() > before
        assert combo.currentIndex() == 75
    finally:
        combo.hidePopup()
        combo.close()
        combo.deleteLater()


def test_custom_value_control_property_covers_its_child(wheel_app):
    class WheelEditedCard(QWidget):
        value = 10

        def wheelEvent(self, event):
            self.value += event.angleDelta().y() // 120
            event.accept()

    card = WheelEditedCard()
    card.setProperty("dcWheelValueControl", True)
    layout = QVBoxLayout(card)
    label = QLabel("Custom editable card")
    layout.addWidget(label)
    card.show()
    wheel_app.processEvents()
    try:
        _wheel(card)
        _wheel(label)
        assert card.value == 10
    finally:
        card.close()
        card.deleteLater()
