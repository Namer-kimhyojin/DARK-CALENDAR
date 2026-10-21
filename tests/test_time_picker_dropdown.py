# -*- coding: utf-8 -*-
"""Clock-list interactions, including atomic choices across midnight."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QDateTime, QSettings, Qt, QTime
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDateTimeEdit, QWidget
import pytest

from calendar_app.presentation.dialogs.dialog_styles import get_dialog_theme_tokens
from calendar_app.presentation.dialogs.time_picker_widget import TimePickerWidget


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path):
    old_format = QSettings.defaultFormat()
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.SystemScope, str(tmp_path))
    yield
    QSettings.setDefaultFormat(old_format)


@pytest.fixture
def picker(qt_app):
    widget = TimePickerWidget(QTime(14, 10))
    yield widget
    widget.close()
    widget.deleteLater()
    qt_app.processEvents()


def test_dropdown_is_opt_in_and_retains_exact_time_and_stepper(picker):
    original_width = picker.minimumWidth()
    assert picker._dropdown_button is None
    picker.show_time_dropdown()
    assert picker._dropdown_popup is None
    picker.enable_dropdown()
    assert picker.minimumWidth() == original_width + 28
    picker.enable_dropdown()
    assert picker.minimumWidth() == original_width + 28
    assert picker.time() == QTime(14, 10)
    picker.setCurrentSection(QDateTimeEdit.Section.MinuteSection)
    picker.stepBy(1)
    assert picker.time() == QTime(14, 15)
    picker.enable_dropdown(False)
    assert picker.minimumWidth() == original_width


def test_native_time_changed_survives_atomic_blocked_updates(picker):
    changes = []
    picker.timeChanged.connect(changes.append)
    picker.setTime(QTime(23, 45))
    assert changes == [QTime(23, 45)]
    was_blocked = picker.blockSignals(True)
    picker.setTime(QTime(22, 0))
    picker.blockSignals(was_blocked)
    assert changes == [QTime(23, 45)]
    picker.setTime(QTime(23, 30))
    assert changes == [QTime(23, 45), QTime(23, 30)]
    picker.setTime(QTime(23, 30))
    assert len(changes) == 2
    picker.setCurrentSection(QDateTimeEdit.Section.MinuteSection)
    picker.stepBy(1)
    assert changes[-1] == QTime(23, 35)


@pytest.mark.parametrize("digits", ["930", "0930", "1410"])
def test_dropdown_keeps_continuous_numeric_entry(picker, digits):
    picker.enable_dropdown()
    QTest.keyClicks(picker, digits)
    assert picker.time() == (QTime(14, 10) if digits == "1410" else QTime(9, 30))


def test_clock_list_includes_half_hours_and_exact_current_value(picker):
    choices = picker._time_choices()
    times = [value.time() for _, value in choices]
    assert len(times) == 49
    assert QTime(14, 0) in times
    assert QTime(14, 10) in times
    assert QTime(14, 30) in times
    assert times == sorted(times)


def test_end_choices_include_duration_midnight_and_multiday_current(picker):
    start = QDateTime(QDate(2026, 10, 21), QTime(23, 40))
    end = QDateTime(QDate(2026, 10, 21), QTime(23, 55))
    picker.set_schedule_context(lambda: (start, end))
    choices = picker._time_choices()
    assert choices[1][1] == QDateTime(QDate(2026, 10, 22), QTime(0, 0))
    assert "00:00" in choices[1][0]
    assert "20" in choices[1][0]
    assert "·" in choices[1][0]
    assert choices[0][1] == end
    assert len(choices) == 49


def test_end_choices_keep_manually_selected_multiday_date(picker):
    start = QDateTime(QDate(2026, 10, 21), QTime(23, 40))
    end = QDateTime(QDate(2026, 10, 24), QTime(1, 10))
    picker.set_schedule_context(lambda: (start, end))
    choices = picker._time_choices()
    assert len(choices) == 49
    assert all(value.date() == end.date() for _, value in choices)
    assert end in [value for _, value in choices]
    assert QDateTime(end.date(), QTime(15, 0)) in [value for _, value in choices]
    assert all("3" in label for label, _ in choices)


def test_end_list_keeps_exact_current_end_without_duplicate(picker):
    start = QDateTime(QDate(2026, 10, 21), QTime(14, 0))
    end = start.addSecs(3600)
    picker.set_schedule_context(lambda: (start, end))
    choices = picker._time_choices()
    assert len(choices) == 48
    assert [value for _, value in choices].count(end) == 1


def test_keyboard_popup_selects_current_nearby_slot_and_escape_does_not_edit(picker, qt_app):
    picker.enable_dropdown()
    picker.show()
    qt_app.processEvents()
    QTest.keyClick(picker, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)
    qt_app.processEvents()
    popup_list = picker._dropdown_list
    assert picker._dropdown_popup.isVisible()
    current = popup_list.currentItem()
    assert current.data(Qt.ItemDataRole.UserRole).time() == QTime(14, 10)
    assert popup_list.visualItemRect(current).intersects(popup_list.viewport().rect())
    QTest.keyClick(popup_list, Qt.Key.Key_Down)
    QTest.keyClick(popup_list, Qt.Key.Key_Return)
    assert picker.time() == QTime(14, 30)
    assert not picker._dropdown_popup.isVisible()
    QTest.keyClick(picker, Qt.Key.Key_F4)
    QTest.keyClick(popup_list, Qt.Key.Key_Down)
    QTest.keyClick(popup_list, Qt.Key.Key_Escape)
    assert picker.time() == QTime(14, 30)
    assert not picker._dropdown_popup.isVisible()


def test_end_selection_emits_datetime_without_transient_time_change(picker, qt_app):
    start = QDateTime(QDate(2026, 10, 21), QTime(23, 30))
    end = start.addSecs(15 * 60)
    picker.setTime(end.time())
    picker.enable_dropdown()
    picker.set_schedule_context(lambda: (start, end))
    selected = []
    time_changes = []
    picker.dateTimeSelected.connect(selected.append)
    picker.timeChanged.connect(time_changes.append)
    picker.show()
    qt_app.processEvents()
    QTest.mouseClick(picker._dropdown_button, Qt.MouseButton.LeftButton)
    qt_app.processEvents()
    midnight = QDateTime(QDate(2026, 10, 22), QTime(0, 0))
    popup_list = picker._dropdown_list
    item = next(
        popup_list.item(row)
        for row in range(popup_list.count())
        if popup_list.item(row).data(Qt.ItemDataRole.UserRole) == midnight
    )
    QTest.mouseClick(
        popup_list.viewport(),
        Qt.MouseButton.LeftButton,
        pos=popup_list.visualItemRect(item).center(),
    )
    assert selected == [midnight]
    assert time_changes == []
    assert picker.time() == end.time()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_popup_inherits_dialog_theme_tokens(qt_app, theme):
    parent = QWidget()
    tokens = get_dialog_theme_tokens(text_theme=theme, apply_overrides=False)
    parent._ui_tokens = lambda: tokens
    picker = TimePickerWidget(QTime(14, 0), parent)
    picker.enable_dropdown()
    parent.show()
    qt_app.processEvents()
    picker.show_time_dropdown()
    assert tokens["surface_bg"] in picker._dropdown_popup.styleSheet()
    assert tokens["text_primary"] in picker._dropdown_popup.styleSheet()
    assert tokens["accent_text"] in picker._dropdown_popup.styleSheet()
    parent.close()
    parent.deleteLater()
    qt_app.processEvents()
