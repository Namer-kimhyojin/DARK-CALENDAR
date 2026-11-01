# -*- coding: utf-8 -*-
"""Forecast time, shared requests, premium editing and animation lifecycle."""

import base64
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
import json
from unittest.mock import Mock, patch

from PyQt6.QtCore import QByteArray, QObject, QSettings, QSize, pyqtSignal
from PyQt6.QtNetwork import QNetworkReply, QNetworkRequest
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget
import pytest

from calendar_app.infrastructure.weather.geonames import find_city
from calendar_app.infrastructure.weather.met_norway import parse_locationforecast
from calendar_app.infrastructure.weather.request_pool import pooled_weather_reply
from calendar_app.presentation.widgets.overlay_weather import OverlayWeatherWidget
from calendar_app.presentation.widgets.weather_scene import WeatherSceneSurface

NOW = datetime(2026, 10, 31, 14, 30, tzinfo=UTC)


def forecast():
    return {
        "properties": {
            "timeseries": [
                {
                    "time": (NOW.replace(minute=0) + timedelta(hours=i)).isoformat(),
                    "data": {
                        "instant": {
                            "details": {
                                "air_temperature": 20 + i,
                                "relative_humidity": 62,
                                "wind_speed": 2.4,
                            }
                        },
                        "next_1_hours": {
                            "summary": {"symbol_code": "partlycloudy_night"},
                            "details": {"precipitation_amount": 0.2},
                        },
                    },
                }
                for i in range(-1, 8)
            ]
        }
    }


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_current_step_and_six_future_steps_use_city_time_and_temperature_units():
    data = parse_locationforecast(
        forecast(), "Seoul", "fahrenheit", now=NOW, timezone_name="Asia/Seoul"
    )
    assert data["temp"] == "68"
    assert data["hourly"][0]["label"] == "00:00"
    assert data["hourly"][0]["temp"] == "69.8"
    assert len(data["hourly"]) == 6
    assert data["forecast_high"] == data["forecast_low"] == "68"
    assert data["timezone"] == "Asia/Seoul"
    assert not data["_forecast_expired"]
    assert find_city("Seoul").timezone == "Asia/Seoul"


def test_six_hour_rain_is_not_reported_as_hourly_and_missing_slots_are_not_invented():
    payload = forecast()
    payload["properties"]["timeseries"] = payload["properties"]["timeseries"][::3]
    for step in payload["properties"]["timeseries"]:
        step["data"]["next_6_hours"] = step["data"].pop("next_1_hours")
    data = parse_locationforecast(payload, "Seoul", now=NOW)
    assert len(data["hourly"]) == 2
    assert all(item["precip_mm"] is None for item in data["hourly"])
    assert data["hourly"][1]["time"] != data["hourly"][0]["time"]


def test_expired_forecast_and_invalid_timezone_remain_explicit():
    data = parse_locationforecast(
        forecast(), "Seoul", now=NOW + timedelta(days=3), timezone_name="missing/zone"
    )
    assert data["_forecast_expired"]
    assert data["hourly"] == []
    assert data["forecast_high"] == "--"
    assert data["timezone"] == "UTC"


class Reply(QObject):
    finished = pyqtSignal()

    def __init__(self, status=200):
        super().__init__()
        self.status, self.running, self.aborted = status, True, False
        self.headers = {
            b"Expires": format_datetime(datetime.now(UTC) + timedelta(hours=1)).encode(
                "utf-8", errors="strict"
            )
        }

    def rawHeader(self, name):  # noqa: N802
        return QByteArray(self.headers.get(name, b""))

    def attribute(self, _attribute):
        return self.status

    def error(self):
        return QNetworkReply.NetworkError.NoError

    def readAll(self):  # noqa: N802
        return QByteArray(json.dumps(forecast()).encode("utf-8", errors="strict"))

    def isRunning(self):  # noqa: N802
        return self.running

    def isFinished(self):  # noqa: N802
        return not self.running

    def abort(self):
        self.aborted = True
        self.finish()

    def finish(self):
        self.running = False
        self.finished.emit()


def request():
    from PyQt6.QtCore import QUrl

    return QNetworkRequest(
        QUrl("https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=37.5660&lon=126.9784")
    )


def test_same_location_shares_inflight_response_and_fresh_cache(app):
    physical = Reply()
    manager = Mock()
    manager.get.return_value = physical
    first, second = (
        pooled_weather_reply(manager, request()),
        pooled_weather_reply(manager, request()),
    )
    assert manager.get.call_count == 1
    physical.finish()
    assert first.readAll() == second.readAll()
    assert first.isFinished() and second.isFinished()
    third = pooled_weather_reply(manager, request())
    app.processEvents()
    assert third.isFinished()
    assert manager.get.call_count == 1


def test_cancelling_one_widget_preserves_another_widgets_request(app):
    physical = Reply()
    manager = Mock()
    manager.get.return_value = physical
    first, second = (
        pooled_weather_reply(manager, request()),
        pooled_weather_reply(manager, request()),
    )
    first.abort()
    assert not physical.aborted
    physical.finish()
    assert second.error() == QNetworkReply.NetworkError.NoError
    assert first.error() == QNetworkReply.NetworkError.OperationCanceledError


def test_last_subscriber_cancels_physical_request(app):
    physical = Reply()
    manager = Mock()
    manager.get.return_value = physical
    client = pooled_weather_reply(manager, request())
    client.abort()
    assert physical.aborted
    assert not manager._air_calendar_weather_pool.pending


def test_destroyed_subscriber_releases_physical_request(app):
    from PyQt6.QtCore import QCoreApplication, QEvent

    physical = Reply()
    manager = Mock()
    manager.get.return_value = physical
    client = pooled_weather_reply(manager, request())
    client.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert physical.aborted


def test_shared_conditional_response_reuses_raw_payload_and_refreshes_expiry(app):
    physical = Reply()
    physical.headers[b"Expires"] = format_datetime(datetime.now(UTC) - timedelta(seconds=1)).encode(
        "utf-8", errors="strict"
    )
    physical.headers[b"Last-Modified"] = b"Fri, 30 Oct 2026 01:00:00 GMT"
    conditional = Reply(304)
    manager = Mock()
    manager.get.side_effect = [physical, conditional]
    first = pooled_weather_reply(manager, request())
    physical.finish()
    second = pooled_weather_reply(manager, request())
    conditional.finish()
    assert first.readAll() == second.readAll()
    assert second.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) == 200
    third = pooled_weather_reply(manager, request())
    app.processEvents()
    assert third.isFinished() and manager.get.call_count == 2


@pytest.fixture
def surface(app):
    with patch(
        "calendar_app.presentation.widgets.weather_scene.system_allows_weather_motion",
        return_value=True,
    ):
        widget = WeatherSceneSurface()
        widget.configure(
            scene_id="air_atmosphere",
            data=parse_locationforecast(forecast(), "Seoul", now=NOW),
            motion="subtle",
        )
        widget.resize(360, 350)
        yield widget
        widget.close()
        app.processEvents()


@pytest.mark.parametrize(
    "size,tier", [((180, 140), "compact"), ((320, 240), "standard"), ((360, 350), "expanded")]
)
def test_layout_changes_information_density_without_creating_settings(surface, size, tier):
    surface.resize(*size)
    assert surface.layout_tier() == tier
    assert not surface.grab().isNull()
    assert not surface._timer.isActive()


def test_motion_stops_when_hidden_disabled_or_reduced_by_system(surface, app):
    surface.show()
    surface.set_runtime_active(True)
    QTest.qWait(120)
    assert surface._ticks >= 1
    before = surface._ticks
    surface.hide()
    QTest.qWait(100)
    assert surface._ticks == before
    assert not surface._timer.isActive() and not surface._policy_timer.isActive()
    surface.show()
    with patch(
        "calendar_app.presentation.widgets.weather_scene.system_allows_weather_motion",
        return_value=False,
    ):
        surface._check_policy()
        assert not surface._timer.isActive()
        assert surface._policy_timer.isActive()  # Can resume after Battery Saver is turned off.
    surface.configure(scene_id="air_atmosphere", data=surface.data, motion="off")
    assert not surface._timer.isActive()


def test_animation_reuses_cached_static_layer_instead_of_restylizing_text(surface):
    surface.show()
    surface.set_runtime_active(True)
    surface.grab()
    layer = surface._layer
    QTest.qWait(120)
    assert surface._layer is layer
    assert surface._ticks > 0
    before = surface.grab().toImage()
    surface._started -= 0.7
    assert surface.grab().toImage() != before


def test_malformed_saved_hourly_values_render_safely_without_mutating_input(surface):
    data = {"city": "Seoul", "hourly": [{"label": "15:00", "temp": "--", "precip_mm": "bad"}, None]}
    surface.configure(
        scene_id="air_atmosphere", data=data, motion="off", animation_dir="bad\x00path"
    )
    assert not surface.grab().isNull()
    assert surface.data["hourly"][0]["precip_mm"] is None
    assert data["hourly"][0]["precip_mm"] == "bad"


def test_malformed_future_periods_do_not_crash_forecast_parser():
    payload = forecast()
    payload["properties"]["timeseries"][2]["data"]["next_1_hours"] = {
        "summary": "bad",
        "details": [],
    }
    payload["properties"]["timeseries"][2]["data"]["next_6_hours"] = ["bad"]
    data = parse_locationforecast(payload, "Seoul", now=NOW)
    assert data["hourly"][0]["precip_mm"] is None


def test_custom_animated_webp_loads_and_pauses_with_widget(surface, app, tmp_path):
    # Two 8px red/blue frames; no imaging dependency is needed to run this test.
    (tmp_path / "partly_cloudy_night.webp").write_bytes(
        base64.b64decode(
            "UklGRoQAAABXRUJQVlA4WAoAAAACAAAABwAABwAAQU5JTQYAAAAAAAAAAABBTk1GKAAAAAAAAAAAAAcAAAcAAFAAAAJWUDhMDwAAAC8HwAEABxD9j/4HIqL/AQBBTk1GKAAAAAAAAAAAAAcAAAcAAFAAAABWUDhMDwAAAC8HwAEABxDR//4HIqL/AQA="
        )
    )
    surface.configure(scene_id="air_atmosphere", data=surface.data, animation_dir=str(tmp_path))
    surface.show()
    surface.set_runtime_active(True)
    app.processEvents()
    surface.grab()
    assert surface._movie is not None and surface._movie.isValid()
    assert not surface._timer.isActive()
    QTest.qWait(110)
    assert surface._movie.state() == surface._movie.MovieState.Running
    surface.hide()
    assert surface._movie.state() == surface._movie.MovieState.Paused


def test_invalid_custom_animation_falls_back_to_builtin(surface, tmp_path):
    (tmp_path / "partly_cloudy_night.webp").write_bytes(b"invalid animation")
    surface.configure(scene_id="air_atmosphere", data=surface.data, animation_dir=str(tmp_path))
    surface.grab()
    assert surface._movie is None


def test_recipe_switch_and_custom_template_preserve_user_configuration(app, tmp_path):
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "overlay.ini"), QSettings.Format.IniFormat)
    with patch(
        "calendar_app.presentation.widgets.overlay_weather.get_network_manager", return_value=Mock()
    ):
        weather = OverlayWeatherWidget(owner)
    try:
        weather._set("location", "Busan")
        weather._set("unit", "fahrenheit")
        weather._set("weather_motion", "off")
        weather._apply_weather_design("air_atmosphere")
        assert weather._active_scene_id() == "air_atmosphere"
        assert weather.size() == QSize(360, 350)
        assert weather._get("location") == "Busan" and weather._get("unit") == "fahrenheit"
        weather._apply_weather_design("editorial_mono")
        assert weather._get("weather_motion") == "off"
        assert weather._active_scene_id() == "editorial_mono"
        weather._set("weather_template", "{temp}{unit}")
        weather._apply_and_resize()
        assert not weather._active_scene_id()
        assert weather._scene_surface.isHidden()
    finally:
        weather._set_runtime_active(False)
        weather.close()
        owner.close()


def test_forecast_updates_do_not_reapply_whole_widget_appearance(app, tmp_path):
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "partial.ini"), QSettings.Format.IniFormat)
    with patch(
        "calendar_app.presentation.widgets.overlay_weather.get_network_manager", return_value=Mock()
    ):
        weather = OverlayWeatherWidget(owner)
    try:
        weather._apply_weather_design("soft_object")
        weather.show()
        app.processEvents()
        with patch.object(
            weather, "_apply_base_appearance", wraps=weather._apply_base_appearance
        ) as restyle:
            weather._weather_data["temp"] = "24"
            weather._refresh_face()
            restyle.assert_not_called()
        assert weather._scene_surface.data["temp"] == "24"
    finally:
        weather._set_runtime_active(False)
        weather.close()
        owner.close()
