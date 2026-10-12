# -*- coding: utf-8 -*-
"""Corrupt widget settings cannot stop restoration, rendering or later alarms."""

from datetime import datetime
import json
import math
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt6.QtCore import QPoint, QSettings
from PyQt6.QtWidgets import QApplication, QMenu, QWidget
import pytest

from calendar_app.presentation.theme.style_builder import (
    _build_app_menu_style,
    apply_top_menu_theme,
    build_global_stylesheet,
    build_tooltip_stylesheet,
)
from calendar_app.presentation.widgets.alarm_checker import TaskAlarmChecker
from calendar_app.presentation.widgets.keydeck.model import normalize_deck
from calendar_app.presentation.widgets.overlay_clock import OverlayClockWidget
from calendar_app.presentation.widgets.overlay_color_utils import _parse_rgba
from calendar_app.presentation.widgets.overlay_manager import OverlayWidgetManager
from calendar_app.presentation.widgets.overlay_stopwatch import OverlayStopwatchWidget
from calendar_app.presentation.widgets.overlay_text import OverlayTextWidget
from calendar_app.presentation.widgets.widget_mode_skins import load_user_widget_styles
from calendar_app.presentation.widgets.widget_mode_typography import read_widget_typography


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def owner(tmp_path):
    widget = QWidget()
    widget.settings = QSettings(str(tmp_path / "widgets.ini"), QSettings.Format.IniFormat)
    yield widget
    widget.close()


@pytest.mark.parametrize("raw", ["#zz123456", "#ggffffff", "#aaZZZZZZ", "invalid"])
def test_corrupt_rgba_uses_fallback(raw):
    color, alpha = _parse_rgba(raw, "#123456", 87)
    assert color.name() == "#123456"
    assert alpha == 87


def test_valid_argb_keeps_explicit_alpha():
    color, alpha = _parse_rgba("#80123456", "#ffffff", 255)
    assert (color.name(), alpha) == ("#123456", 128)


@pytest.mark.parametrize("raw_type", [[], {}, None, 17])
def test_restore_skips_invalid_type_and_retains_valid_instance(owner, raw_type):
    settings = owner.settings
    settings.setValue(
        "overlay_instances",
        json.dumps(
            [
                {"id": "clock_0", "type": raw_type},
                {"id": "text_0", "type": "text", "name": "memo", "enabled": False},
            ]
        ),
    )
    manager = OverlayWidgetManager(owner)
    child = Mock()
    child.is_enabled.return_value = False
    manager._create_widget = Mock(return_value=child)
    manager._attach_widget_callbacks = Mock()
    manager.restore_all()
    assert set(manager._widgets) == {"text_0"}
    assert json.loads(settings.value("overlay_instances"))[0]["name"] == "memo"


@pytest.mark.parametrize("value", ["garbage", "NaN", "Infinity", -3, float("inf")])
def test_stopwatch_recovers_elapsed_without_overwriting_stored_value(owner, value):
    owner.settings.setValue("overlay_stopwatch_sw_elapsed_ms", value)
    widget = OverlayStopwatchWidget(owner)
    try:
        assert widget._sw_elapsed_ms() == 0.0
        assert widget.get_elapsed_text() == "00:00.0"
        assert "00:00.0" in widget._resolve_sw_template("{elapsed}", value, False)
        assert owner.settings.value("overlay_stopwatch_sw_elapsed_ms") == value
    finally:
        widget.close()


@pytest.mark.parametrize("field", ["sw_started_mono", "sw_started_boot_epoch", "sw_started_wall"])
def test_stopwatch_ignores_invalid_clock_anchor(owner, field):
    widget = OverlayStopwatchWidget(owner)
    try:
        for key, value in {
            "sw_elapsed_ms": 1000,
            "sw_running": True,
            "sw_started_mono": 90.0,
            "sw_started_wall": 990.0,
            "sw_started_boot_epoch": 900.0,
        }.items():
            widget._set(key, value)
        widget._set(field, "-Infinity")
        with (
            patch(
                "calendar_app.presentation.widgets.overlay_stopwatch.time.time", return_value=1000.0
            ),
            patch(
                "calendar_app.presentation.widgets.overlay_stopwatch.time.monotonic",
                return_value=100.0,
            ),
        ):
            elapsed = widget._sw_elapsed_ms()
        assert math.isfinite(elapsed)
        assert elapsed >= 1000.0
    finally:
        widget.close()


@pytest.mark.parametrize("value", ["broken", {}, float("inf"), 10**30])
def test_saved_overlay_position_falls_back_to_reachable_owner(owner, value):
    widget = OverlayTextWidget(owner)
    try:
        widget._set("pos_x", value)
        widget._set("pos_y", value)
        offset = QPoint(-230, 24)
        expected = widget._clamp_restored_position(owner.frameGeometry().topRight() + offset)
        widget.restore_position(offset)
        assert widget.pos() == expected
    finally:
        widget.close()


@pytest.mark.parametrize("value", ["broken", {}, float("inf")])
def test_invalid_font_setting_uses_default(owner, value):
    widget = OverlayTextWidget(owner)
    try:
        widget._set("font_size", value)
        assert widget.font_size() == widget._default_font_size()
    finally:
        widget.close()


def test_nonfinite_fixed_dimension_is_removed(owner):
    widget = OverlayTextWidget(owner)
    try:
        widget._set("fixed_w", float("inf"))
        assert widget._normalized_fixed_dimension("fixed_w") is None
    finally:
        widget.close()


@pytest.mark.parametrize("value", [float("inf"), 10**30, 961, -961, []])
def test_invalid_clock_timezone_uses_local_time(owner, value):
    owner.settings.setValue("overlay_clock_tz_offset_mins", value)
    widget = OverlayClockWidget(owner)
    try:
        assert widget._tz_offset_minutes() is None
        assert widget._now_tz().isValid()
    finally:
        widget.close()


@pytest.mark.parametrize("value", [10**400, -(10**400)])
def test_keydeck_large_numeric_settings_recover(value):
    result = normalize_deck({"unit": value, "pages": [{"keys": [{"w": value}]}]})
    assert result["unit"] == 68
    assert result["pages"][0]["keys"][0]["w"] == 1.0


@pytest.mark.parametrize("field", ["skins", "layouts"])
@pytest.mark.parametrize("value", [None, 17])
def test_user_style_bad_collection_does_not_break_import(tmp_path, field, value):
    path = tmp_path / "styles.json"
    path.write_text(json.dumps({field: value}), encoding="utf-8", errors="strict")
    assert load_user_widget_styles(path) == (0, 0)


def test_typography_nonfinite_setting_uses_default(owner):
    owner.settings.setValue("widget_mode_font_size", float("inf"))
    assert read_widget_typography(owner.settings).preference == 12


def test_alarm_digit_like_strings_and_overflow_do_not_discard_other_offsets():
    assert TaskAlarmChecker._parse_offsets("²,10," + "9" * 5000 + ",60") == [10, 60]


def test_alarm_overflow_in_first_task_does_not_block_later_task(qt_app):
    checker = TaskAlarmChecker.__new__(TaskAlarmChecker)
    checker._fired = set()
    checker._confirmed = set()
    checker._snoozed = {}
    deadline = datetime.now().strftime("%Y-%m-%d %H:%M")
    checker._fetch_alarm_tasks = Mock(
        return_value=[
            {"id": 1, "deadline": deadline, "alarm_time": "9" * 100},
            {"id": 2, "deadline": deadline, "alarm_time": "0"},
        ]
    )
    checker._show_popup = Mock()
    with patch("calendar_app.infrastructure.db.db_repository_unified.record_fired_alarm") as record:
        checker._do_poll()
    record.assert_called_once_with(2, 0)
    assert checker._show_popup.call_count == 1


def test_alarm_stop_also_cancels_pending_startup_poll(qt_app):
    with patch.object(TaskAlarmChecker, "_load_fired_alarms"):
        checker = TaskAlarmChecker(SimpleNamespace())
    assert checker._startup_timer.isActive()
    checker.stop()
    assert not checker._startup_timer.isActive()
    assert not checker._timer.isActive()
    checker.deleteLater()


@pytest.mark.parametrize("value", ["broken", None, float("inf"), float("nan")])
def test_stylesheet_font_sizes_recover_corrupt_numeric_values(value):
    for build in (build_global_stylesheet, build_tooltip_stylesheet):
        stylesheet = build(base_pt=value)
        assert "font-size: 10pt" in stylesheet
        assert "nanpt" not in stylesheet and "infpt" not in stylesheet


@pytest.mark.parametrize("value", ["broken", float("inf"), float("nan")])
def test_menu_opacity_recovers_to_saved_theme_value(owner, value):
    stylesheet = _build_app_menu_style(
        10, "#4da6ff", opacity_factor=value, settings=owner.settings, persist_opacity=False
    )
    assert "rgba(" in stylesheet and "nan" not in stylesheet


def test_top_menus_ignore_corrupt_font_and_refresh_without_conversion_exception(owner):
    owner.settings.setValue("font_size", "broken")
    owner.sys_menu = QMenu(owner)
    apply_top_menu_theme(owner, persist_opacity=False)
    owner.sys_menu.aboutToShow.emit()
    assert "font-size: 10pt" in owner.sys_menu.styleSheet()


@pytest.mark.parametrize("value", ["broken", float("inf"), 0, -1, 10**30])
def test_alarm_popup_default_snooze_is_positive_and_fits_qtimer(owner, value):
    from calendar_app.presentation.widgets.alarm_popup import AlarmPopupWindow

    owner.settings.setValue("alarm/default_snooze", value)
    with (
        patch(
            "calendar_app.presentation.widgets.alarm_popup.QSettings", return_value=owner.settings
        ),
        patch.object(AlarmPopupWindow, "_play_notification_sound"),
    ):
        widget = AlarmPopupWindow({"id": 1, "name": "test"}, datetime.now(), parent=owner)
    try:
        assert widget._default_snooze == 5
        assert widget._auto_snooze_timer.interval() == 300_000
    finally:
        widget.close()


@pytest.mark.parametrize("value", ["broken", float("inf")])
def test_unified_widget_font_weight_recovers(owner, value):
    from PyQt6.QtCore import QDate

    from calendar_app.presentation.widgets.unified_widget_mode import UnifiedWidgetWindow

    owner.settings.setValue("widget_mode_font_weight", value)
    window = Mock()
    window.controller.main_window = owner
    window.controller._current_date.return_value = QDate.currentDate()
    window._style_signature = None
    UnifiedWidgetWindow.apply_theme(window)
    assert "font-weight: 500" in window.setStyleSheet.call_args.args[0]


def test_panel_widget_opacity_recovers_nonfinite_value(owner):
    from calendar_app.presentation.widgets.panel_widget_shell import _FloatingWidgetBase

    owner.settings.setValue("panel_opacity", float("inf"))
    panel = SimpleNamespace(_app=owner, _opacity_setting_key=lambda: "panel_opacity")
    assert _FloatingWidgetBase._get_individual_opacity(panel) == 100


def test_keydeck_invalid_local_image_path_uses_fallback():
    from calendar_app.presentation.widgets.keydeck.resources import file_stamp, source_image

    assert file_stamp("bad\x00.png") is None
    assert source_image("bad\x00.png") is None


@pytest.mark.parametrize("value", [17, "aTbTc", None])
def test_countdown_settings_accept_corrupt_saved_target_without_writing(owner, value):
    from calendar_app.presentation.widgets.overlay_countdown import OverlayCountdownWidget

    widget = OverlayCountdownWidget(owner)
    try:
        widget._set("cd_target_iso", value)
        widget._open_standard_settings_dialog = Mock(return_value=False)
        widget._open_settings()
        assert widget._open_standard_settings_dialog.call_count == 1
        assert widget._get("cd_target_iso") == value
    finally:
        widget.close()


def test_weather_overflow_response_releases_reply_and_reports_parse_error(owner):
    from PyQt6.QtNetwork import QNetworkReply

    from calendar_app.presentation.widgets.overlay_weather import OverlayWeatherWidget

    widget = OverlayWeatherWidget(owner)
    reply = Mock()
    reply.attribute.return_value = 200
    reply.error.return_value = QNetworkReply.NetworkError.NoError
    reply.readAll.return_value.data.return_value = b"{}"
    widget._pending_replies = [reply]
    widget._runtime_active = True
    widget._update_weather_data = Mock(side_effect=OverflowError("invalid external numeric field"))
    widget._restore_weather_cache = Mock(return_value=False)
    widget._show_error = Mock()
    widget._refresh_face = Mock()
    try:
        widget._on_weather_reply(reply, "Seoul", "celsius", 37.5, 127.0)
        widget._show_error.assert_called_once()
        reply.deleteLater.assert_called_once()
        assert not widget._pending_replies
    finally:
        widget.close()
