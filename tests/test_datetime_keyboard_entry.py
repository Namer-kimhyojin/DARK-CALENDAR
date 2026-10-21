# -*- coding: utf-8 -*-
"""Real key sequences for whole-field and section date/time editing."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QDateTime, QEvent, QSettings, Qt, QTime
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QDateTimeEdit,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
import pytest

from calendar_app.presentation.dialogs.time_picker_widget import DatePickerWidget, TimePickerWidget


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path):
    old_format = QSettings.defaultFormat()
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    for scope in (QSettings.Scope.UserScope, QSettings.Scope.SystemScope):
        QSettings.setPath(QSettings.Format.IniFormat, scope, str(tmp_path))
    yield
    QSettings.setDefaultFormat(old_format)


@pytest.fixture
def editors(qt_app):
    parent = QWidget()
    layout = QVBoxLayout(parent)
    before = QLineEdit()
    time = TimePickerWidget(QTime(8, 20))
    time.enable_dropdown()
    date = DatePickerWidget(QDate(2026, 10, 21))
    after = QLineEdit()
    for widget in (before, time, date, after):
        layout.addWidget(widget)
    parent.show()
    qt_app.processEvents()
    yield parent, before, time, date, after
    parent.close()
    parent.deleteLater()
    qt_app.processEvents()


def replace_with_keys(widget, text):
    widget.setFocus()
    QTest.keyClick(widget, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(widget, text)


@pytest.mark.parametrize("text", ["14:10", "9:30", "930", "0930", "1410"])
def test_whole_time_replacement_accepts_formatted_and_compact_keys(editors, text):
    _parent, _before, time, _date, after = editors
    replace_with_keys(time, text)
    after.setFocus()
    expected = QTime(14, 10) if text in ("14:10", "1410") else QTime(9, 30)
    assert time.time() == expected


@pytest.mark.parametrize(
    ("section", "digits", "expected"),
    [
        (QDateTimeEdit.Section.MinuteSection, "45", QTime(8, 45)),
        (QDateTimeEdit.Section.HourSection, "14", QTime(14, 20)),
    ],
)
def test_time_section_typing_preserves_the_other_section(editors, section, digits, expected):
    _parent, _before, time, _date, after = editors
    time.setFocus()
    time.setSelectedSection(section)
    QTest.keyClicks(time, digits)
    after.setFocus()
    assert time.time() == expected


def test_shifted_semicolon_keeps_the_formatted_time_entry(editors):
    _parent, _before, time, _date, after = editors
    replace_with_keys(time, "14")
    event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Semicolon, Qt.KeyboardModifier.ShiftModifier, ":"
    )
    QApplication.sendEvent(time, event)
    QTest.keyClicks(time, "10")
    after.setFocus()
    assert time.time() == QTime(14, 10)


def test_completed_compact_entry_retains_minute_section_stepping(editors):
    _parent, _before, time, _date, _after = editors
    replace_with_keys(time, "0930")
    QTest.keyClick(time, Qt.Key.Key_Up)
    assert time.time() == QTime(9, 35)


@pytest.mark.parametrize("text", ["2026-11-03", "20261103"])
def test_whole_date_replacement_accepts_formatted_and_compact_keys(editors, text):
    _parent, _before, _time, date, after = editors
    replace_with_keys(date, text)
    after.setFocus()
    assert date.date() == QDate(2026, 11, 3)


@pytest.mark.parametrize(
    ("section", "digits", "expected"),
    [
        (QDateTimeEdit.Section.MonthSection, "11", QDate(2026, 11, 21)),
        (QDateTimeEdit.Section.DaySection, "03", QDate(2026, 10, 3)),
        (QDateTimeEdit.Section.YearSection, "2027", QDate(2027, 10, 21)),
    ],
)
def test_date_section_typing_preserves_the_other_sections(editors, section, digits, expected):
    _parent, _before, _time, date, after = editors
    date.setFocus()
    date.setSelectedSection(section)
    QTest.keyClicks(date, digits)
    after.setFocus()
    assert date.date() == expected


@pytest.mark.parametrize("text", ["2460", "14:70", "14:", "14:1"])
def test_invalid_or_incomplete_time_replacement_restores_original(editors, text):
    _parent, _before, time, _date, after = editors
    replace_with_keys(time, text)
    after.setFocus()
    assert time.time() == QTime(8, 20)


@pytest.mark.parametrize("text", ["20260231", "2026-02-31", "202602", "2026-02-"])
def test_invalid_or_incomplete_date_replacement_restores_original(editors, text):
    _parent, _before, _time, date, after = editors
    replace_with_keys(date, text)
    after.setFocus()
    assert date.date() == QDate(2026, 10, 21)


def test_backspace_can_correct_a_complete_invalid_time(editors):
    _parent, _before, time, _date, after = editors
    replace_with_keys(time, "14:70")
    QTest.keyClick(time, Qt.Key.Key_Backspace)
    QTest.keyClick(time, Qt.Key.Key_Backspace)
    QTest.keyClicks(time, "10")
    after.setFocus()
    assert time.time() == QTime(14, 10)


def test_new_selection_discards_incomplete_entry_and_steps_still_work(editors):
    _parent, _before, time, _date, after = editors
    replace_with_keys(time, "14:")
    replace_with_keys(time, "0930")
    after.setFocus()
    time.setFocus()
    time.setSelectedSection(QDateTimeEdit.Section.MinuteSection)
    QTest.keyClick(time, Qt.Key.Key_Up)
    assert time.time() == QTime(9, 35)
    QTest.keyClicks(time, "45")
    after.setFocus()
    assert time.time() == QTime(9, 45)


@pytest.mark.parametrize("backwards", [False, True])
def test_popup_tab_closes_without_applying_highlight_and_traverses(editors, qt_app, backwards):
    _parent, before, time, date, _after = editors
    time.setFocus()
    QTest.keyClick(time, Qt.Key.Key_F4)
    popup_list = time._dropdown_list
    QTest.keyClick(popup_list, Qt.Key.Key_Down)
    if backwards:
        QTest.keyClick(popup_list, Qt.Key.Key_Backtab)
    else:
        QTest.keyClick(popup_list, Qt.Key.Key_Tab)
    qt_app.processEvents()
    assert not time._dropdown_popup.isVisible()
    assert time.time() == QTime(8, 20)
    assert (before if backwards else date).hasFocus()


def test_popup_opens_at_time_committed_from_formatted_keys(editors, qt_app):
    _parent, _before, time, _date, _after = editors
    replace_with_keys(time, "14:10")
    QTest.keyClick(time, Qt.Key.Key_F4)
    qt_app.processEvents()
    assert time._dropdown_list.currentItem().data(Qt.ItemDataRole.UserRole).time() == QTime(14, 10)
    QTest.keyClick(time._dropdown_list, Qt.Key.Key_Escape)
    assert time.time() == QTime(14, 10)


@pytest.mark.parametrize("pending", ["0930", "14:"])
def test_external_time_setter_discards_pending_entry(editors, pending):
    _parent, _before, time, _date, after = editors
    replace_with_keys(time, pending)
    time.setTime(QTime(12, 40))
    after.setFocus()
    assert time.time() == QTime(12, 40)


@pytest.mark.parametrize("pending", ["20261103", "2026-11-"])
def test_external_date_setter_discards_pending_entry(editors, pending):
    _parent, _before, _time, date, after = editors
    replace_with_keys(date, pending)
    date.setDate(QDate(2026, 12, 7))
    after.setFocus()
    assert date.date() == QDate(2026, 12, 7)


def test_external_datetime_setter_discards_pending_entry(editors):
    _parent, _before, time, _date, after = editors
    replace_with_keys(time, "0930")
    value = QDateTime(time.dateTime())
    value.setTime(QTime(12, 40))
    time.setDateTime(value)
    after.setFocus()
    assert time.time() == QTime(12, 40)


def test_no_focus_quick_action_is_not_reverted_on_blur(editors, qt_app):
    parent, _before, time, _date, after = editors
    quick = QPushButton("12:40", parent)
    quick.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    quick.clicked.connect(lambda: time.setTime(QTime(12, 40)))
    parent.layout().addWidget(quick)
    qt_app.processEvents()
    replace_with_keys(time, "14:")
    QTest.mouseClick(quick, Qt.MouseButton.LeftButton)
    after.setFocus()
    assert time.time() == QTime(12, 40)
