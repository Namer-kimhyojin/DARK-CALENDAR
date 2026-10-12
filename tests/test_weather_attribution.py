# -*- coding: utf-8 -*-
"""Weather credits stay discoverable without occupying the desktop widget."""

from copy import deepcopy
from unittest.mock import Mock, patch

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QMenu, QPushButton, QWidget
import pytest

from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.weather.met_norway import GEONAMES_LICENSE_URL, MET_LICENSE_URL
from calendar_app.presentation.widgets.overlay_weather import OverlayWeatherWidget
from tests.test_weather_widget_loading import FakeReply, forecast


@pytest.fixture
def weather(tmp_path):
    app = QApplication.instance() or QApplication([])
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "credits.ini"), QSettings.Format.IniFormat)
    network = Mock()
    replies = []

    def new_reply(request):
        reply = FakeReply()
        replies.append(reply)
        return reply

    network.get.side_effect = new_reply
    with patch(
        "calendar_app.presentation.widgets.overlay_weather.get_network_manager",
        return_value=network,
    ):
        widget = OverlayWeatherWidget(owner)
        widget._runtime_active = True
        widget.apply_initial_settings()
        yield widget, owner, network, replies
        widget._set_runtime_active(False)
        widget.close()
        owner.close()
        app.processEvents()


def settings_snapshot(owner):
    return {key: owner.settings.value(key) for key in owner.settings.allKeys()}


def assert_no_provider_footer(widget):
    for label in widget.face.findChildren(QLabel):
        assert "MET Norway" not in label.text()
        assert "GeoNames" not in label.text()


def assert_source_links(dialog):
    label = dialog.findChild(QLabel, "weatherDataSources")
    assert label is not None
    html = label.text()
    assert "MET Norway" in html
    assert "GeoNames" in html
    assert MET_LICENSE_URL in html
    assert GEONAMES_LICENSE_URL in html
    assert "creativecommons.org/licenses/by/" in html
    assert "CC BY" in html
    assert label.openExternalLinks()


def source_button(dialog):
    return next(
        (
            button
            for button in dialog.findChildren(QPushButton)
            if button.property("weatherSources")
        ),
        None,
    )


def test_provider_footer_stays_removed_after_data_styles_and_shadows_change(weather):
    widget, _, _, _ = weather
    widget._update_weather_data(forecast(24), "Seoul", "celsius")
    widget._set("weather_template", "{temp}{unit}\n{city}")
    widget._refresh_face()
    assert "24" in widget._template_label.text()
    assert "Seoul" in widget._template_label.text()
    assert_no_provider_footer(widget)
    widget._set_display_preset("pure_type")
    widget._set_text_shadow_enabled(True)
    widget._set("font_size", 22)
    widget._apply_and_resize()
    assert "24" in widget._template_label.text()
    assert_no_provider_footer(widget)
    widget._set_text_shadow_enabled(False)
    widget._set_display_preset("pearl_mist")
    widget._refresh_face()
    assert_no_provider_footer(widget)


def test_loading_success_and_error_status_remain_available_without_credits_footer(weather):
    widget, _, network, replies = weather
    widget._set("weather_template", "{temp}{unit}")
    widget.request_update()
    assert not widget._status_label.isHidden()
    assert widget._status_label.text() == t("widget.weather.loading", "날씨를 불러오는 중…")
    assert_no_provider_footer(widget)
    replies[-1].finish()
    assert widget._weather_data["temp"] == "20"
    assert widget._status_label.isHidden()
    assert widget.face.toolTip()
    assert_no_provider_footer(widget)
    widget._show_error("Offline")
    assert not widget._status_label.isHidden()
    assert "Offline" in widget._status_label.text()
    assert widget._weather_data["temp"] == "20"
    assert_no_provider_footer(widget)
    assert network.get.call_count == 1


def test_context_menu_opens_complete_source_dialog_without_changing_widget_or_network(weather):
    widget, owner, network, _ = weather
    widget._update_weather_data(forecast(18), "Seoul", "celsius")
    widget._refresh_face()
    widget.show()
    QApplication.processEvents()
    before_settings = settings_snapshot(owner)
    before_weather = deepcopy(widget._weather_data)
    before_geometry = widget.geometry()
    before_timers = (
        widget._refresh_timer.isActive(),
        widget._refresh_timer.interval(),
        widget._retry_timer.isActive(),
    )
    seen = []

    def inspect_and_close(dialog):
        assert_source_links(dialog)
        assert dialog.parent() is widget
        assert settings_snapshot(owner) == before_settings
        seen.append(dialog)
        return QDialog.DialogCode.Rejected

    menu = QMenu(widget)
    widget._build_context_menu(menu)
    assert menu.actions()[0].text() == t("widget.weather.refresh_now", "날씨 다시 불러오기")
    source = next(
        action
        for action in menu.actions()
        if action.text() == t("widget.weather.sources_title", "날씨 데이터 출처")
    )
    with patch.object(QDialog, "exec", inspect_and_close):
        source.trigger()
    assert len(seen) == 1
    assert settings_snapshot(owner) == before_settings
    assert widget._weather_data == before_weather
    assert widget.geometry() == before_geometry
    assert network.get.call_count == 0
    assert before_timers == (
        widget._refresh_timer.isActive(),
        widget._refresh_timer.interval(),
        widget._retry_timer.isActive(),
    )


def test_settings_sources_button_uses_same_dialog_and_cancel_preserves_preferences(weather):
    widget, owner, network, _ = weather
    before = settings_snapshot(owner)
    visited = []

    def inspect_and_close(dialog):
        if dialog.findChild(QLabel, "weatherDataSources") is not None:
            assert_source_links(dialog)
            assert source_button(dialog.parent()) is not None
            visited.append("sources")
            return QDialog.DialogCode.Rejected
        button = source_button(dialog)
        assert button is not None
        assert button.objectName() == "ghost_btn"
        assert button.isEnabled()
        visited.append("settings")
        button.click()
        assert settings_snapshot(owner) == before
        return QDialog.DialogCode.Rejected

    with patch.object(QDialog, "exec", inspect_and_close):
        widget._open_settings()
    assert visited == ["settings", "sources"]
    assert settings_snapshot(owner) == before
    assert network.get.call_count == 0
