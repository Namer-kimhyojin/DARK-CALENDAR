# -*- coding: utf-8 -*-
"""Each widget's short paths and content recovery use the actual rendered state."""

from unittest.mock import Mock, patch

from PyQt6.QtCore import QDate, QSettings, Qt
from PyQt6.QtWidgets import QApplication, QMenu, QWidget
import pytest

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.overlay_clock import OverlayClockWidget
from calendar_app.presentation.widgets.overlay_countdown import OverlayCountdownWidget
from calendar_app.presentation.widgets.overlay_datecard import OverlayDateCardWidget
from calendar_app.presentation.widgets.overlay_dday import OverlayDDayWidget
from calendar_app.presentation.widgets.overlay_stopwatch import OverlayStopwatchWidget
from calendar_app.presentation.widgets.overlay_text import OverlayTextWidget
from calendar_app.presentation.widgets.overlay_weather import OverlayWeatherWidget
from calendar_app.presentation.widgets.widget_placement import NoWheelComboBox, NoWheelSpinBox
from tests.test_widget_mode_ux import _APP  # noqa: F401


@pytest.fixture
def owner(tmp_path):
    widget = QWidget()
    widget.settings = QSettings(str(tmp_path / "convenience.ini"), QSettings.Format.IniFormat)
    yield widget
    widget.close()


@pytest.mark.parametrize(
    "kind",
    [
        OverlayClockWidget,
        OverlayDateCardWidget,
        OverlayWeatherWidget,
        OverlayCountdownWidget,
        OverlayDDayWidget,
        OverlayTextWidget,
    ],
)
def test_double_click_opens_settings_even_when_placement_is_locked(owner, kind):
    widget = kind(owner)
    widget._set_placement_locked(True)
    widget._open_settings = Mock()
    assert widget._on_double_click()
    widget._open_settings.assert_called_once()
    widget.close()


def test_clock_quick_timezone_uses_existing_offset_and_preserves_format(owner):
    widget = OverlayClockWidget(owner)
    widget._set("format", "hm")
    menu = QMenu()
    widget._build_context_menu(menu)
    zones = next(action.menu() for action in menu.actions() if action.menu())
    zone = widget._timezone_items()[11]
    next(action for action in zones.actions() if action.text() == zone[0]).trigger()
    assert widget._tz_offset_minutes() == zone[1]
    assert widget._get("format") == "hm"
    widget.close()


def test_date_card_copies_today_in_portable_format(owner):
    widget = OverlayDateCardWidget(owner)
    menu = QMenu()
    widget._build_context_menu(menu)
    with patch.object(QApplication, "clipboard") as clipboard:
        next(
            action
            for action in menu.actions()
            if action.text() == t("widget.usage.copy_date", "오늘 날짜 복사")
        ).trigger()
        clipboard.return_value.setText.assert_called_once_with(
            QDate.currentDate().toString("yyyy-MM-dd")
        )
    widget.close()


def test_text_copy_uses_visible_resolved_data_not_a_second_empty_template_resolution(owner):
    widget = OverlayTextWidget(owner)
    widget._set("text", "{task_count}")
    widget._text_label.setText("<b>12</b><br>회의 자료")
    with patch.object(QApplication, "clipboard") as clipboard:
        widget._copy_displayed_text()
        clipboard.return_value.setText.assert_called_once_with("12\n회의 자료")
    widget.close()


@pytest.mark.parametrize(
    "kind,values",
    [
        (OverlayCountdownWidget, {"cd_target_iso": "2026-10-20T18:00:00"}),
        (OverlayDDayWidget, {"dd_target_date": "2026-10-20", "dd_label": "기념일"}),
        (OverlayStopwatchWidget, {"sw_elapsed_ms": 12345.0, "sw_running": False}),
    ],
)
def test_content_reset_has_one_step_recovery_and_does_not_change_appearance(owner, kind, values):
    widget = kind(owner)
    for key, value in values.items():
        widget._set(key, value)
    widget._set("placement_locked", True)
    appearance = widget.display_preset_id()
    menu = QMenu()
    widget._build_context_menu(menu)
    # All three types put their reset after their settings / pause control.
    candidates = [
        action for action in menu.actions() if not action.isSeparator() and not action.menu()
    ]
    candidates[-1].trigger()
    assert widget._last_content_reset is not None
    menu.clear()
    widget._build_context_menu(menu)
    next(
        action
        for action in menu.actions()
        if action.text() == t("widget.usage.undo_reset", "초기화 되돌리기")
    ).trigger()
    for key, value in values.items():
        assert widget._get(key) == value
    assert widget.display_preset_id() == appearance
    assert widget.placement_is_locked()
    assert widget._last_content_reset is None
    widget.close()


def test_stopwatch_running_reset_undo_keeps_original_clock_anchor(owner):
    widget = OverlayStopwatchWidget(owner)
    with (
        patch(
            "calendar_app.presentation.widgets.overlay_stopwatch.time.monotonic", return_value=100.0
        ),
        patch("calendar_app.presentation.widgets.overlay_stopwatch.time.time", return_value=1000.0),
    ):
        widget.toggle_running()
        menu = QMenu()
        widget._build_context_menu(menu)
        [action for action in menu.actions() if not action.isSeparator()][-1].trigger()
        assert not widget._sw_running()
        widget._undo_content_reset()
        assert widget._sw_running()
        assert widget._get("sw_started_mono") == 100.0
        assert widget._get("sw_started_wall") == 1000.0
    widget.close()


@pytest.mark.parametrize(
    "raw,expected", [("false", False), ("true", True), (False, False), (True, True)]
)
def test_widget_settings_restore_boolean_intent_and_use_wheel_safe_fields(owner, raw, expected):
    widget = OverlayTextWidget(owner)
    widget._set("word_wrap", raw)
    field = widget._build_field_widget({"type": "bool", "key": "word_wrap", "default": True})
    assert field.isChecked() is expected
    assert isinstance(
        widget._build_field_widget({"type": "combo", "key": "text_align", "options": []}),
        NoWheelComboBox,
    )
    assert isinstance(widget._make_font_size_spin(24), NoWheelSpinBox)
    widget.close()
