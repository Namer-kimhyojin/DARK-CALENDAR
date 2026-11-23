# -*- coding: utf-8 -*-
"""Widget-only mode support checks (2026-11-23): date picker, icon buttons,
edge resizing, monitor return and clock options."""

import os
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QEvent, QPoint, QPointF, QRect, Qt, QTime
from PyQt6.QtGui import QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication, QWidget
import pytest

from calendar_app.presentation.widgets.unified_widget_mode import (
    UnifiedWidgetController,
    _EdgeResizeHandle,
)
from calendar_app.presentation.widgets.widget_date_picker import (
    VIEW_DAYS,
    VIEW_MONTHS,
    VIEW_YEARS,
    WidgetDatePickerPopup,
    month_grid_dates,
    year_block_start,
)
from calendar_app.presentation.widgets.widget_mode_clock import (
    ClockOptions,
    format_clock_date,
    format_clock_time,
    ms_until_next_tick,
    read_clock_options,
)
from calendar_app.presentation.widgets.widget_mode_display import (
    LayoutDisplay,
    write_layout_display,
)

_APP = QApplication.instance() or QApplication([])


class Settings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=None, type=None):
        value = self.values.get(key, default)
        if type is bool and isinstance(value, str):
            return value.lower() == "true"
        return value

    def setValue(self, key, value):
        self.values[key] = value


class Host(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = Settings()
        self.current_date = QDate(2026, 11, 23)
        self._latest_calendar_range_data = {}
        self._latest_directive_data = {}
        self.schedule_panel_refresh = Mock()


@pytest.fixture
def window():
    host = Host()
    controller = UnifiedWidgetController(host)
    controller.show_widget()
    _APP.processEvents()
    yield host, controller, controller.widget
    controller.widget.hide()
    controller.widget.deleteLater()
    host.deleteLater()
    _APP.processEvents()


# ----- date picker ----------------------------------------------------------
def test_picker_reaches_any_month_through_year_and_month_views():
    chosen = []
    picker = WidgetDatePickerPopup(QDate(2026, 11, 23))
    picker.dateSelected.connect(chosen.append)
    assert picker.view == VIEW_DAYS
    picker.title_btn.click()
    assert picker.view == VIEW_MONTHS
    picker.title_btn.click()
    assert picker.view == VIEW_YEARS
    assert picker.year_buttons[0].text() == str(year_block_start(2026))
    picker.prev_btn.click()  # previous 12-year block
    picker.year_buttons[0].click()
    assert picker.view == VIEW_MONTHS
    picker.month_buttons[2].click()  # March
    assert picker.view == VIEW_DAYS
    expected_year = year_block_start(2026) - 12
    index = next(
        i
        for i, date in enumerate(month_grid_dates(expected_year, 3))
        if date.month() == 3 and date.day() == 15
    )
    picker.day_buttons[index].click()
    assert chosen == [QDate(expected_year, 3, 15)]
    picker.deleteLater()


def test_picker_keyboard_moves_and_confirms():
    chosen = []
    picker = WidgetDatePickerPopup(QDate(2026, 1, 31))
    picker.dateSelected.connect(chosen.append)
    for key in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_PageDown):
        picker.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))
    assert picker.title_btn.text()  # still rendered
    picker.keyPressEvent(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    )
    # Jan 31 -> Feb 1 -> Feb 8 -> Mar 8
    assert chosen == [QDate(2026, 3, 8)]
    picker.deleteLater()


def test_picker_title_names_year_before_month_in_korean_default():
    picker = WidgetDatePickerPopup(QDate(2026, 11, 23))
    title = picker.title_btn.text()
    assert "2026" in title and title.index("2026") < len(title) - 1
    picker.deleteLater()


def test_widget_date_button_opens_new_picker_and_sets_date(window):
    _host, controller, widget = window
    widget.date_picker_btn.click()
    popup = widget._date_picker_popup
    assert isinstance(popup, WidgetDatePickerPopup)
    popup.title_btn.click()
    popup.month_buttons[0].click()
    popup.day_buttons[
        next(i for i, d in enumerate(popup._day_dates) if d == QDate(2026, 1, 15))
    ].click()
    assert controller._current_date() == QDate(2026, 1, 15)


# ----- icon buttons and tooltips --------------------------------------------
def test_toolbar_buttons_have_icons_and_descriptive_tooltips(window):
    _host, _controller, widget = window
    buttons = (
        widget.restore_btn,
        widget.pin_btn,
        widget.customize_btn,
        widget.more_btn,
        widget.date_picker_btn,
        widget.today_btn,
        widget.previous_week_btn,
        widget.next_week_btn,
    )
    for button in buttons:
        assert not button.icon().isNull(), button.accessibleName()
        assert button.accessibleName()
        assert button.toolTip()
    assert widget.more_btn.text() == ""
    assert "F12" in widget.restore_btn.toolTip()
    assert widget.previous_week_btn.isVisibleTo(widget)
    assert widget.next_week_btn.isVisibleTo(widget)


def test_previous_next_follow_week_or_month_view(window):
    host, controller, widget = window
    controller.set_target_date(QDate(2026, 11, 23))
    widget.next_week_btn.click()
    assert controller._current_date() == QDate(2026, 11, 30)
    write_layout_display(host.settings, "stacked", LayoutDisplay("month", False, False))
    widget.resize(700, widget.height())
    widget.apply_selected_layout(force=True)
    if widget.cal_grid.display_mode == "month":
        widget.previous_week_btn.click()
        assert controller._current_date() == QDate(2026, 10, 30)
        assert widget.previous_week_btn.toolTip() == widget.previous_week_btn.accessibleName()


# ----- edge resize ------------------------------------------------------------
def test_edge_handles_cover_all_edges_and_hide_when_locked(window):
    _host, _controller, widget = window
    assert len(widget._edge_handles) == 8
    assert all(handle.isVisibleTo(widget) for handle in widget._edge_handles)
    widget._set_placement_locked(True)
    assert not any(handle.isVisibleTo(widget) for handle in widget._edge_handles)
    widget._set_placement_locked(False)
    assert all(handle.isVisibleTo(widget) for handle in widget._edge_handles)


def test_left_edge_fallback_resize_keeps_right_edge(window):
    _host, _controller, widget = window
    widget.setGeometry(QRect(300, 200, 420, 560))
    _APP.processEvents()
    handle = next(h for h in widget._edge_handles if h.edges == Qt.Edge.LeftEdge)
    widget._try_start_system_resize = lambda _edges: False
    right = widget.geometry().right()
    start = QPointF(handle.mapToGlobal(QPoint(2, 20)))

    def mouse(kind, point, buttons):
        return QMouseEvent(
            kind,
            QPointF(2, 20),
            point,
            Qt.MouseButton.LeftButton,
            buttons,
            Qt.KeyboardModifier.NoModifier,
        )

    handle.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton))
    moved = QPointF(start.x() - 40, start.y())
    handle.mouseMoveEvent(mouse(QEvent.Type.MouseMove, moved, Qt.MouseButton.LeftButton))
    handle.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease, moved, Qt.MouseButton.NoButton))
    assert widget.geometry().right() == right
    assert widget.width() == 460
    assert isinstance(handle, _EdgeResizeHandle)


# ----- multi-monitor ---------------------------------------------------------
def test_unplugged_monitor_keeps_saved_home_until_user_moves(window):
    host, controller, widget = window
    controller._save_geometry()
    key = next(k for k in host.settings.values if k.startswith("unified_widget_geometry"))
    saved = host.settings.values[key].replace(
        f'"screen":"{widget.screen().name()}"', '"screen":"GONE"'
    )
    host.settings.values[key] = saved
    controller._handle_screen_change(object())  # a removed screen
    assert controller._displaced_home == "GONE"
    controller._save_geometry()
    assert host.settings.values[key] == saved  # home kept
    widget._begin_placement_edit()
    widget.move(widget.x() + 30, widget.y())
    widget._finish_placement_edit()
    assert controller._displaced_home is None
    assert host.settings.values[key] != saved


def test_return_to_home_screen_restores_when_monitor_returns(window):
    _host, controller, widget = window
    controller._displaced_home = widget.screen().name()
    controller._restore_geometry = Mock()
    controller._return_to_home_screen()
    controller._restore_geometry.assert_called_once()
    assert controller._displaced_home is None


def test_move_to_screen_keeps_size(window):
    _host, controller, widget = window
    size = widget.size()
    controller.move_to_screen(widget.screen())
    assert widget.size() == size


# ----- clock options -----------------------------------------------------------
def test_clock_formats():
    noon = QTime(14, 5, 9)
    assert format_clock_time(noon, ClockOptions()) == "14:05"
    assert format_clock_time(noon, ClockOptions(seconds=True)) == "14:05:09"
    twelve = format_clock_time(noon, ClockOptions(hour_format="12h"))
    assert "2:05" in twelve and "14" not in twelve
    assert "12:00" in format_clock_time(QTime(0, 0), ClockOptions(hour_format="12h"))
    assert ms_until_next_tick(QTime(10, 0, 0, 400), ClockOptions(seconds=True)) == 600
    assert ms_until_next_tick(QTime(10, 0, 30), ClockOptions()) == 30000
    assert "11" in format_clock_date(QDate(2026, 11, 23), ClockOptions())


def test_clock_options_read_safely():
    settings = Settings()
    settings.setValue("widget_mode_clock_format", "bogus")
    settings.setValue("widget_mode_clock_size", "huge")
    settings.setValue("widget_mode_clock_seconds", "true")
    assert read_clock_options(settings) == ClockOptions("24h", True, "small", False)


def test_large_clock_shows_time_and_date_above_content(window):
    host, _controller, widget = window
    host.settings.setValue("widget_mode_clock_size", "large")
    host.settings.setValue("widget_mode_clock_show_date", True)
    widget.apply_selected_layout(force=True)
    assert widget.clock_hero.isVisibleTo(widget)
    assert not widget.clock_label.isVisibleTo(widget)
    assert widget.clock_big_label.text()
    assert widget.clock_date_label.text()
    host.settings.setValue("widget_mode_clock_size", "small")
    widget.apply_selected_layout(force=True)
    assert not widget.clock_hero.isVisibleTo(widget)
    assert widget.clock_label.isVisibleTo(widget)
    assert "/" in widget.clock_label.text()  # date beside the small clock


# ----- right-click / 더 보기 menu (A안) ------------------------------------------
def test_widget_menu_keeps_only_items_the_toolbar_lacks(window, monkeypatch):
    from PyQt6.QtWidgets import QMenu

    _host, _controller, widget = window
    captured = {}

    def fake_exec(menu, *_args):
        captured["top"] = [a.text() for a in menu.actions() if not a.isSeparator()]
        window_menu = next(
            a.menu() for a in menu.actions() if a.menu() is not None and a.text() == "창 관리"
        )
        captured["window"] = [a.text() for a in window_menu.actions() if not a.isSeparator()]
        return None

    monkeypatch.setattr(QMenu, "exec", fake_exec)
    widget._open_menu(widget.mapToGlobal(QPoint(10, 10)))
    top = captured["top"]
    assert len(top) <= 7
    for gone in ("날짜 선택", "오늘", "이전 주", "다음 주", "꾸미기", "메인 화면으로", "목록 밀도"):
        assert gone not in top
    assert "트레이로 숨기기" in top
    assert "화면 안으로 이동" in captured["window"]
    assert "위치·크기 조정" in captured["window"]


# ----- saved layout setups, Ctrl+1-9, hover preview -----------------------------
def test_saved_setup_round_trip_and_apply(window):
    from calendar_app.presentation.widgets.widget_saved_layouts import (
        SELECTED_SETUP_KEY,
        add_setup,
        capture_setup,
        read_saved_setups,
        write_saved_setups,
    )

    host, controller, widget = window
    write_layout_display(host.settings, "dashboard", LayoutDisplay("week", True, True))
    setup = capture_setup(host.settings, "업무 대시보드", "dashboard")
    write_saved_setups(host.settings, add_setup([], setup))
    write_layout_display(host.settings, "dashboard", LayoutDisplay("month", False, False))
    assert [item["name"] for item in read_saved_setups(host.settings)] == ["업무 대시보드"]
    choices = controller.layout_choices()
    assert [kind for kind, *_ in choices][:5] == ["layout"] * 4 + ["setup"]
    widget._apply_layout_shortcut(4)  # Ctrl+5
    assert host.settings.value("widget_mode_layout") == "dashboard"
    assert host.settings.value(SELECTED_SETUP_KEY) == setup["id"]
    assert host.settings.value("widget_mode_calendar_style_dashboard") == "week"
    assert widget.feedback_label.text().endswith("업무 대시보드")
    widget._apply_layout_shortcut(0)  # Ctrl+1
    assert host.settings.value("widget_mode_layout") == "stacked"
    assert host.settings.value(SELECTED_SETUP_KEY) == ""


def test_malformed_saved_setups_are_skipped_not_dropped():
    from calendar_app.presentation.widgets.widget_saved_layouts import read_saved_setups

    settings = Settings()
    good = {"id": "setup_" + "a" * 32, "name": "좋음", "layout_id": "stacked"}
    settings.setValue(
        "widget_mode_saved_setups",
        '{"version":1,"setups":[{"id":"x"},' + __import__("json").dumps(good) + "]}",
    )
    assert [item["name"] for item in read_saved_setups(settings)] == ["좋음"]


def test_dialog_layout_tab_holds_options_and_saves_setup(window):
    from calendar_app.presentation.dialogs.widget_customization_dialog import (
        WidgetCustomizationDialog,
    )
    from calendar_app.presentation.widgets.widget_saved_layouts import read_saved_setups

    host, controller, widget = window
    dialog = WidgetCustomizationDialog(controller, widget)
    try:
        layout_tab = dialog.preferences_tabs.widget(0)
        assert dialog.preferences_tabs.tabText(0) == "배치"
        assert layout_tab.isAncestorOf(dialog.calendar_style_combo)
        assert layout_tab.isAncestorOf(dialog.calendar_visibility_checkbox)
        assert not dialog.user_layout_list.isVisibleTo(dialog)
        assert dialog.user_layout_empty.isVisibleTo(dialog)
        assert not dialog.preset_rename_btn.isVisibleTo(dialog)
        dialog.layout_buttons["dashboard"].click()
        assert "좌우형" in dialog.display_group_title.text()
        dialog._save_current_setup("넓은 화면")
        assert dialog.user_layout_list.count() == 1
        assert read_saved_setups(host.settings) == []  # draft only until 적용
        dialog._apply()
        assert [item["name"] for item in read_saved_setups(host.settings)] == ["넓은 화면"]
    finally:
        dialog.close()
        dialog.deleteLater()


def test_hovering_a_layout_card_previews_then_restores(window):
    from calendar_app.presentation.dialogs.widget_customization_dialog import (
        WidgetCustomizationDialog,
    )

    _host, controller, widget = window
    dialog = WidgetCustomizationDialog(controller, widget)
    try:
        before = dialog.draft.value("widget_mode_layout")
        card = dialog.layout_buttons["minimal"]
        dialog.eventFilter(card, QEvent(QEvent.Type.Enter))
        assert dialog.preview.active_layout_id() == "minimal"
        dialog.eventFilter(card, QEvent(QEvent.Type.Leave))
        assert dialog.draft.value("widget_mode_layout") == before
    finally:
        dialog.close()
        dialog.deleteLater()
