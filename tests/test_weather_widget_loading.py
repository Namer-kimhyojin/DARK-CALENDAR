# -*- coding: utf-8 -*-
"""Weather loading regressions; settings and network are isolated from the user."""

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QByteArray, QObject, QSettings, QTimer, pyqtSignal
from PyQt6.QtNetwork import QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from calendar_app.infrastructure.weather.met_norway import parse_locationforecast
from calendar_app.presentation.widgets.overlay_weather import OverlayWeatherWidget


def forecast(temperature=20):
    return {
        "properties": {
            "timeseries": [
                {
                    "data": {
                        "instant": {"details": {"air_temperature": temperature}},
                        "next_1_hours": {"summary": {"symbol_code": "clearsky_day"}},
                    }
                }
            ]
        }
    }


class FakeReply(QObject):
    finished = pyqtSignal()

    def __init__(
        self, *, status=200, body=None, error=QNetworkReply.NetworkError.NoError, headers=None
    ):
        super().__init__()
        self.status = status
        self.body = json.dumps(forecast() if body is None else body).encode(
            "utf-8", errors="strict"
        )
        self.network_error = error
        self.headers = headers or {}
        self.running = True
        self.aborted = False

    def attribute(self, _attribute):
        return self.status

    def rawHeader(self, name):
        return QByteArray(self.headers.get(name, b""))

    def error(self):
        return self.network_error

    def readAll(self):
        return QByteArray(self.body)

    def isRunning(self):
        return self.running

    def isFinished(self):
        return not self.running

    def abort(self):
        self.aborted = True
        self.network_error = QNetworkReply.NetworkError.OperationCanceledError
        self.finish()

    def finish(self):
        self.running = False
        self.finished.emit()


class WeatherWidgetLoadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.owner = QWidget()
        self.owner.settings = QSettings(
            str(Path(self.temp_dir.name) / "weather.ini"), QSettings.Format.IniFormat
        )
        self.network = Mock()
        self.replies = []
        self.network.get.side_effect = self.new_reply
        self.network_patch = patch(
            "calendar_app.presentation.widgets.overlay_weather.get_network_manager",
            return_value=self.network,
        )
        self.network_patch.start()
        self.widget = OverlayWeatherWidget(self.owner)
        self.widget._runtime_active = True

    def new_reply(self, _request):
        reply = FakeReply()
        self.replies.append(reply)
        return reply

    def tearDown(self):
        self.widget._set_runtime_active(False)
        self.widget.close()
        self.owner.close()
        self.app.processEvents()
        self.network_patch.stop()
        self.temp_dir.cleanup()

    def seed_cache(self):
        self.widget._update_weather_data(forecast(12), "Seoul", "celsius")
        self.widget._store_weather_cache(37.566, 126.9784, "Seoul", "celsius")
        self.widget._set(
            "met_cache_expires", format_datetime(datetime.now(UTC) - timedelta(hours=1))
        )
        self.widget._set("met_cache_last_modified", "Mon, 05 Oct 2026 01:00:00 GMT")

    def test_legacy_combo_tuple_is_repaired_and_timer_starts(self):
        self.widget._set("refresh_interval", ("분", 5))
        self.widget._update_refresh_interval()
        self.assertEqual(self.widget._get("refresh_interval", type_=int), 5)
        self.assertEqual(self.widget._refresh_timer.interval(), 5 * 60 * 1000)
        self.assertTrue(self.widget._refresh_timer.isActive())

    def test_saved_legacy_settings_restore_on_widget_restart(self):
        self.widget._set("refresh_interval", ("분", 5))
        self.widget._set("enabled", True)
        self.owner.settings.sync()
        self.widget._set_runtime_active(False)
        self.widget.close()
        self.owner.settings = QSettings(
            str(Path(self.temp_dir.name) / "weather.ini"), QSettings.Format.IniFormat
        )
        self.widget = OverlayWeatherWidget(self.owner)
        self.assertTrue(self.widget._runtime_active)
        self.assertEqual(self.widget._get("refresh_interval", type_=int), 5)
        self.assertTrue(self.widget._refresh_timer.isActive())

    def test_invalid_intervals_recover_without_conversion_exception(self):
        for value in (None, {}, [], "invalid", True, 0, 999):
            with self.subTest(value=value):
                self.widget._set("refresh_interval", value)
                self.assertEqual(self.widget._refresh_minutes(), 30)
                self.assertEqual(self.widget._get("refresh_interval", type_=int), 30)

    def test_settings_combo_saves_only_integer_minutes(self):
        with patch.object(
            self.widget, "_open_standard_settings_dialog", return_value=False
        ) as dialog:
            self.widget._open_settings()
        field = next(
            f for f in dialog.call_args.kwargs["extra_fields"] if f["key"] == "refresh_interval"
        )
        combo = self.widget._build_field_widget(field)
        for index, minutes in enumerate((5, 10, 30, 60, 120)):
            combo.setCurrentIndex(index)
            value = self.widget._get_field_value(combo)
            self.assertIs(type(value), int)
            self.assertEqual(value, minutes)
            self.assertIn(str(minutes), combo.currentText())
        combo.deleteLater()

    def test_corrupted_coordinates_are_resolved_again(self):
        self.widget._set("resolved_name", "Seoul")
        self.widget._set("lat", "invalid")
        self.widget._set("lon", {})
        self.widget.request_update()
        self.assertEqual(self.network.get.call_count, 1)
        self.assertAlmostEqual(self.widget._get("lat", type_=float), 37.566)

    def test_repeated_refresh_keeps_one_request_and_releases_timeout_timer(self):
        self.widget.request_update()
        self.widget.request_update()
        reply = self.replies[0]
        self.assertEqual(self.network.get.call_count, 1)
        self.assertFalse(reply.aborted)
        self.assertTrue(reply.findChild(QTimer).isActive())
        reply.finish()
        self.assertFalse(reply.findChild(QTimer).isActive())
        self.assertEqual(self.widget._weather_data["temp"], "20")
        self.assertEqual(self.widget._weather_data["error"], "")
        self.assertFalse(self.widget._pending_replies)
        self.assertTrue(self.widget._status_label.text())
        self.assertTrue(self.widget._status_label.isHidden())
        self.assertTrue(self.widget.face.toolTip())

    def test_location_change_ignores_canceled_and_late_responses(self):
        self.widget.request_update()
        previous = self.replies[0]
        self.widget._set("location", "Busan")
        self.widget.request_update()
        self.assertTrue(previous.aborted)
        self.assertEqual(self.widget._weather_data["error"], "")
        previous.network_error = QNetworkReply.NetworkError.NoError
        previous.body = json.dumps(forecast(99)).encode("utf-8", errors="strict")
        previous.finish()
        self.assertEqual(self.widget._weather_data["temp"], "--")
        self.replies[-1].finish()
        self.assertNotEqual(self.widget._weather_data["city"], "Seoul")
        self.assertEqual(self.widget._weather_data["temp"], "20")

    def test_timeout_retries_and_hidden_widget_cancels_every_timer(self):
        self.widget.request_update()
        self.replies[0].abort()
        self.assertTrue(self.widget._retry_timer.isActive())
        self.assertEqual(self.widget._retry_timer.interval(), 60_000)
        self.assertTrue(self.widget._weather_data["error"])
        self.widget._set_runtime_active(False)
        self.widget.request_update()
        self.assertFalse(self.widget._retry_timer.isActive())
        self.assertFalse(self.widget._refresh_timer.isActive())
        self.assertEqual(self.network.get.call_count, 1)

    def test_corrupt_cache_is_ignored_without_sending_old_validator(self):
        for value in (
            [],
            {"weather": []},
            {"lat": 37.566, "lon": 126.9784, "unit": "celsius", "weather": {"temp": "NaN"}},
        ):
            self.widget._set("met_cache_json", json.dumps(value))
            self.widget._set("met_cache_last_modified", "old-validator")
            self.assertFalse(
                self.widget._restore_weather_cache(
                    37.566, 126.9784, "Seoul", "celsius", require_fresh=False
                )
            )
        self.widget.request_update()
        request = self.network.get.call_args.args[0]
        self.assertFalse(request.hasRawHeader(b"If-Modified-Since"))

    def test_conditional_header_is_not_reused_for_different_city_or_unit(self):
        self.seed_cache()
        for lat, lon, unit in ((35.18, 129.07, "celsius"), (37.566, 126.9784, "fahrenheit")):
            with self.subTest(unit=unit):
                self.widget._set("unit", unit)
                self.widget._fetch_weather(lat, lon, "Test City")
                request = self.network.get.call_args.args[0]
                self.assertFalse(request.hasRawHeader(b"If-Modified-Since"))
                self.widget._cancel_pending_replies()

    def test_304_restores_matching_cache_and_updates_expiry(self):
        self.seed_cache()
        expires = format_datetime(datetime.now(UTC) + timedelta(hours=1)).encode(
            "utf-8", errors="strict"
        )
        self.widget._fetch_weather(37.566, 126.9784, "Seoul")
        request = self.network.get.call_args.args[0]
        self.assertTrue(request.hasRawHeader(b"If-Modified-Since"))
        reply = self.replies[-1]
        reply.status = 304
        reply.headers[b"Expires"] = expires
        reply.finish()
        self.assertEqual(self.widget._weather_data["temp"], "12")
        self.assertFalse(self.widget._retry_timer.isActive())
        self.assertTrue(
            self.widget._restore_weather_cache(
                37.566, 126.9784, "Seoul", "celsius", require_fresh=True
            )
        )

    def test_network_failure_preserves_weather_and_shows_stale_status(self):
        self.seed_cache()
        self.widget._fetch_weather(37.566, 126.9784, "Seoul")
        reply = self.replies[-1]
        reply.network_error = QNetworkReply.NetworkError.HostNotFoundError
        reply.finish()
        self.assertEqual(self.widget._weather_data["temp"], "12")
        self.assertEqual(self.widget._weather_data["city"], "Seoul")
        self.assertTrue(self.widget._weather_data["error"])
        self.assertTrue(self.widget._status_label.text())
        self.assertFalse(self.widget._status_label.isHidden())
        self.assertTrue(self.widget._retry_timer.isActive())

    def test_bad_forecast_shapes_and_nonfinite_temperature_are_reported(self):
        for payload in (
            [],
            {"properties": []},
            {"properties": {"timeseries": []}},
            forecast("NaN"),
            forecast("Infinity"),
        ):
            with self.subTest(payload=payload), self.assertRaises((ValueError, KeyError)):
                parse_locationforecast(payload, "Seoul")
        self.widget.request_update()
        reply = self.replies[-1]
        reply.body = b"[]"
        reply.finish()
        self.assertTrue(self.widget._weather_data["error"])
        self.assertTrue(self.widget._retry_timer.isActive())

    def test_rate_limit_respects_retry_after_and_manual_refresh(self):
        self.widget.request_update()
        reply = self.replies[-1]
        reply.status = 429
        reply.network_error = QNetworkReply.NetworkError.UnknownContentError
        reply.headers[b"Retry-After"] = b"3600"
        reply.finish()
        self.assertEqual(self.widget._retry_timer.interval(), 3_600_000)
        self.widget.request_update()
        self.widget._scheduled_update()
        self.assertEqual(self.network.get.call_count, 1)

    def test_new_response_without_cache_headers_clears_previous_headers(self):
        self.seed_cache()
        self.widget._fetch_weather(37.566, 126.9784, "Seoul")
        self.replies[-1].finish()
        self.assertEqual(self.widget._get("met_cache_expires"), "")
        self.assertEqual(self.widget._get("met_cache_last_modified"), "")

    def test_equator_is_valid_and_context_menu_offers_retry(self):
        self.widget._set("resolved_name", "Equator")
        self.widget._set("location", "Equator")
        self.widget._set("lat", 0.0)
        self.widget._set("lon", 10.0)
        self.widget.request_update()
        request = self.network.get.call_args.args[0]
        self.assertIn("lat=0.0000", request.url().toString())
        menu = QMenu(self.widget)
        self.widget._build_context_menu(menu)
        self.assertTrue(menu.actions()[0].isEnabled())


if __name__ == "__main__":
    unittest.main()
