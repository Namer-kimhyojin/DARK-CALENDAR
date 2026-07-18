# -*- coding: utf-8 -*-
"""Overlay weather widget using local GeoNames lookup and MET Norway data."""

from __future__ import annotations

import base64
import contextlib
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import json
import logging
import re

from PyQt6.QtCore import QBuffer, QIODevice, QPoint, Qt, QTimer, QUrl, QUrlQuery
from PyQt6.QtNetwork import QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import QFrame, QLabel, QMenu, QVBoxLayout

from calendar_app.app_metadata import APP_VERSION
from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.runtime.network import get_network_manager
from calendar_app.infrastructure.weather.geonames import find_city
from calendar_app.infrastructure.weather.met_norway import (
    GEONAMES_LICENSE_URL,
    MET_FORECAST_ENDPOINT,
    MET_LICENSE_URL,
    parse_locationforecast,
)
from calendar_app.presentation.widgets.overlay_base import (
    _DLG_SS,
    _apply_align_tags,
    _apply_span,
    _BaseOverlayWidget,
    _GripFrame,
    _inject_global_lh,
    _protect_align_tags,
)

logger = logging.getLogger(__name__)

# WMO 코드 → mdi6 아이콘명 매핑
WEATHER_ICON_MAP: dict[int, str] = {
    0: "mdi6.weather-sunny",  # Clear sky
    1: "mdi6.weather-sunny",  # Mainly clear
    2: "mdi6.weather-partly-cloudy",  # Partly cloudy
    3: "mdi6.weather-cloudy",  # Overcast
    45: "mdi6.weather-fog",  # Fog
    48: "mdi6.weather-fog",  # Depositing rime fog
    51: "mdi6.weather-partly-rainy",  # Drizzle: Light
    53: "mdi6.weather-partly-rainy",  # Drizzle: Moderate
    55: "mdi6.weather-rainy",  # Drizzle: Dense
    61: "mdi6.weather-rainy",  # Rain: Slight
    63: "mdi6.weather-rainy",  # Rain: Moderate
    65: "mdi6.weather-pouring",  # Rain: Heavy
    71: "mdi6.weather-snowy",  # Snow: Slight
    73: "mdi6.weather-snowy",  # Snow: Moderate
    75: "mdi6.weather-snowy-heavy",  # Snow: Heavy
    77: "mdi6.snowflake",  # Snow grains
    80: "mdi6.weather-partly-rainy",  # Rain showers: Slight
    81: "mdi6.weather-rainy",  # Rain showers: Moderate
    82: "mdi6.weather-pouring",  # Rain showers: Violent
    85: "mdi6.weather-partly-snowy",  # Snow showers: Slight
    86: "mdi6.weather-snowy-heavy",  # Snow showers: Heavy
    95: "mdi6.weather-lightning",  # Thunderstorm
    96: "mdi6.weather-lightning-rainy",  # Thunderstorm + slight hail
    99: "mdi6.weather-lightning-rainy",  # Thunderstorm + heavy hail
}
_WEATHER_ICON_FALLBACK = "mdi6.weather-partly-cloudy"


def _weather_icon_b64(wmo_code: int, color: str, size: int) -> str:
    """WMO 코드 → mdi6 아이콘 → base64 PNG → HTML <img> 태그 반환."""
    qta_name = WEATHER_ICON_MAP.get(wmo_code, _WEATHER_ICON_FALLBACK)
    try:
        import qtawesome as qta

        qicon = qta.icon(qta_name, color=color)
        px = qicon.pixmap(size, size)
    except Exception:
        return ""

    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    px.save(buf, "PNG")
    buf.close()
    b64 = base64.b64encode(bytes(buf.data())).decode("utf-8", errors="replace")
    return f'<img src="data:image/png;base64,{b64}" width="{size}" height="{size}" />'


_NETWORK_TIMEOUT_MS = 10_000  # abort reply after 10 s
_APP_HOMEPAGE = "https://namer-kimhyojin.github.io/dark_calendar/"
_MET_USER_AGENT = f"DarkCalendar/{APP_VERSION} {_APP_HOMEPAGE}".encode("utf-8", errors="strict")

_WEATHER_DESC = {
    0: "Clear Sky",
    1: "Mainly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime Fog",
    51: "Light Drizzle",
    53: "Moderate Drizzle",
    55: "Dense Drizzle",
    61: "Slight Rain",
    63: "Moderate Rain",
    65: "Heavy Rain",
    71: "Slight Snow",
    73: "Moderate Snow",
    75: "Heavy Snow",
    77: "Snow Grains",
    80: "Slight Showers",
    81: "Moderate Showers",
    82: "Violent Showers",
    85: "Slight Snow Showers",
    86: "Heavy Snow Showers",
    95: "Thunderstorm",
}


class OverlayWeatherWidget(_BaseOverlayWidget):
    _PREFIX = "overlay_weather"
    _DEFAULT_TEXT_RGBA = "#4db8ffff"
    _DEFAULT_BG_RGBA = "#d6101418"
    _DEFAULT_BORDER_RGBA = "#20ffffff"

    _STYLES = [
        ("default", "Default - Card"),
        ("minimal", "Minimal - No Border"),
        ("pill", "Pill - Rounded Corners"),
        ("neon", "Neon - Thick Border"),
        ("compact", "Compact - Smaller Padding"),
        ("banner", "Banner - Left Accent Bar"),
        ("glass", "Glass - Transparent Look"),
        ("outlined", "Outlined - No Background"),
        ("retro", "Retro - Double Border"),
        ("sticky", "Sticky - Note Style"),
    ]
    _STYLE_I18N_PREFIX = "widget.weather"

    _TEMPLATE_KEY = "weather_template"
    _DEFAULT_TEMPLATE = "{icon|size=32}\n{temp|size=24|bold}{unit}\n{city|size=11|color=muted}"

    _DLG_SS = _DLG_SS

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self, owner):
        super().__init__(owner)
        self._network_manager = get_network_manager()
        # Note: Finished signal will be handled via per-request reply finished.
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.request_update)
        self._pending_replies: list[QNetworkReply] = []

        self._weather_data: dict = {
            "city": "---",
            "temp": "--",
            "unit": "°C",
            "humidity": "--",
            "wind": "--",
            "desc": "--",
            "_wmo": 0,
            "error": "",
        }

        self._update_refresh_interval()
        # Defer first network request until event loop is running
        QTimer.singleShot(0, self.request_update)

    def _settings_prefix(self) -> str:
        return self._PREFIX

    def _default_font_size(self) -> int:
        # Compact default: icon is size+6, temp is size+2, so 11pt → icon 17pt
        return 11

    # ------------------------------------------------------------------
    # Face construction
    # ------------------------------------------------------------------

    def _build_face(self) -> QFrame:
        frame = _GripFrame(self)
        frame.setObjectName("weatherFace")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(4)

        self._icon_label = QLabel("--", frame)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._icon_label)

        self._temp_label = QLabel("--°C", frame)
        self._temp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._temp_label)

        self._city_label = QLabel("---", frame)
        self._city_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._city_label)

        # Template mode label — hidden until template mode is active
        self._template_label = QLabel("", frame)
        self._template_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._template_label.setWordWrap(True)
        self._template_label.setTextFormat(Qt.TextFormat.RichText)
        self._template_label.setVisible(False)
        layout.addWidget(self._template_label)

        self._source_label = QLabel("", frame)
        self._source_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._source_label.setTextFormat(Qt.TextFormat.RichText)
        self._source_label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self._source_label.setOpenExternalLinks(True)
        layout.addWidget(self._source_label)

        return frame

    def request_update(self) -> None:
        """Fetch the latest MET Norway forecast for the configured city."""
        # Clean up old replies
        for r in self._pending_replies:
            if r.isRunning():
                r.abort()
            r.deleteLater()
        self._pending_replies.clear()

        location = self._get("location", "Seoul")

        # 인스턴스별 캐시 키 사용 (_get/_set 이용 → prefix 자동 적용)
        cached_loc = self._get("resolved_name", "")
        lat = self._get("lat", 0.0, type_=float)
        lon = self._get("lon", 0.0, type_=float)

        if location != cached_loc or lat == 0.0:
            self._geocode_location(location)
            return

        # Fetch weather using cached coords (display_name은 지오코딩 결과 사용)
        display_name = self._get("display_name", location)
        self._fetch_weather(lat, lon, display_name)

    def _watch_reply(self, reply: QNetworkReply) -> None:
        """타임아웃 타이머 연결 — 10 s 초과 시 abort."""
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda r=reply: r.abort() if not r.isFinished() else None)
        reply.finished.connect(timer.stop)
        timer.start(_NETWORK_TIMEOUT_MS)

    def _show_error(self, msg: str) -> None:
        self._weather_data["error"] = msg
        self._weather_data["city"] = msg
        self._weather_data["temp"] = "⚠"
        self._weather_data["_wmo"] = -1
        self._refresh_face()

    def _geocode_location(self, name: str) -> None:
        """Resolve a city using the bundled GeoNames dataset."""
        city = find_city(name)
        if city is None:
            logger.warning("Local GeoNames lookup failed for: %s", name)
            self._show_error(t("weather.error.location_not_found", "위치를 찾을 수 없습니다"))
            self._refresh_face()
            return

        lat = round(city.latitude, 4)
        lon = round(city.longitude, 4)
        self._set("lat", lat)
        self._set("lon", lon)
        self._set("resolved_name", name)
        self._set("display_name", city.name)
        self._fetch_weather(lat, lon, city.name)

    def _fetch_weather(self, lat: float, lon: float, display_name: str) -> None:
        """Fetch MET Norway weather data for specific coordinates."""
        unit = "fahrenheit" if self._get("unit") == "fahrenheit" else "celsius"

        if self._restore_weather_cache(lat, lon, display_name, unit, require_fresh=True):
            self._refresh_face()
            return

        url = QUrl(MET_FORECAST_ENDPOINT)
        query = QUrlQuery()
        query.addQueryItem("lat", f"{round(float(lat), 4):.4f}")
        query.addQueryItem("lon", f"{round(float(lon), 4):.4f}")
        url.setQuery(query)
        request = QNetworkRequest(url)
        request.setRawHeader(b"User-Agent", _MET_USER_AGENT)
        request.setRawHeader(b"Accept", b"application/geo+json, application/json")
        last_modified = str(self._get("met_cache_last_modified", "") or "").strip()
        if last_modified:
            request.setRawHeader(
                b"If-Modified-Since", last_modified.encode("utf-8", errors="replace")
            )

        reply = self._network_manager.get(request)
        reply.finished.connect(
            lambda r=reply, name=display_name, request_unit=unit, request_lat=lat, request_lon=lon: (
                self._on_weather_reply(r, name, request_unit, request_lat, request_lon)
            )
        )
        self._pending_replies.append(reply)
        self._watch_reply(reply)

    def _on_weather_reply(
        self,
        reply: QNetworkReply,
        display_name: str,
        unit: str,
        lat: float,
        lon: float,
    ) -> None:
        if reply in self._pending_replies:
            self._pending_replies.remove(reply)

        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if status == 304:
            self._store_response_headers(reply)
            if not self._restore_weather_cache(lat, lon, display_name, unit, require_fresh=False):
                self._show_error(t("weather.error.network", "네트워크 오류"))
        elif reply.error() == QNetworkReply.NetworkError.NoError:
            try:
                data = json.loads(reply.readAll().data().decode("utf-8", errors="replace"))
                self._weather_data["error"] = ""
                self._update_weather_data(data, display_name, unit)
                self._store_weather_cache(lat, lon, display_name, unit)
                self._store_response_headers(reply)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                logger.warning("MET Norway response parse failed: %s", exc)
                if not self._restore_weather_cache(
                    lat, lon, display_name, unit, require_fresh=False
                ):
                    self._show_error(t("weather.error.parse_failed", "데이터 파싱 오류"))
        elif reply.error() == QNetworkReply.NetworkError.OperationCanceledError:
            if not self._restore_weather_cache(lat, lon, display_name, unit, require_fresh=False):
                self._show_error(t("weather.error.timeout", "요청 시간 초과"))
        else:
            if not self._restore_weather_cache(lat, lon, display_name, unit, require_fresh=False):
                self._show_error(t("weather.error.network", "네트워크 오류"))
        reply.deleteLater()
        self._refresh_face()

    def _update_weather_data(self, json_data: dict, display_name: str, unit: str) -> None:
        parsed = parse_locationforecast(json_data, display_name, unit)
        parsed["desc"] = self._weather_code_to_text(int(parsed.get("_wmo", 2)))
        parsed["error"] = ""
        self._weather_data.update(parsed)

    def _store_weather_cache(self, lat: float, lon: float, display_name: str, unit: str) -> None:
        cache = {
            "lat": round(float(lat), 4),
            "lon": round(float(lon), 4),
            "display_name": display_name,
            "unit": unit,
            "weather": self._weather_data,
        }
        self._set("met_cache_json", json.dumps(cache, ensure_ascii=False))

    def _store_response_headers(self, reply: QNetworkReply) -> None:
        expires = bytes(reply.rawHeader(b"Expires")).decode("utf-8", errors="replace").strip()
        last_modified = (
            bytes(reply.rawHeader(b"Last-Modified")).decode("utf-8", errors="replace").strip()
        )
        if expires:
            self._set("met_cache_expires", expires)
        if last_modified:
            self._set("met_cache_last_modified", last_modified)

    def _restore_weather_cache(
        self,
        lat: float,
        lon: float,
        display_name: str,
        unit: str,
        *,
        require_fresh: bool,
    ) -> bool:
        raw_cache = str(self._get("met_cache_json", "") or "")
        if not raw_cache:
            return False
        try:
            cache = json.loads(raw_cache)
            if round(float(cache.get("lat")), 4) != round(float(lat), 4):
                return False
            if round(float(cache.get("lon")), 4) != round(float(lon), 4):
                return False
            if str(cache.get("unit")) != unit:
                return False
            if require_fresh:
                expires_text = str(self._get("met_cache_expires", "") or "").strip()
                if not expires_text:
                    return False
                expires_at = parsedate_to_datetime(expires_text)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
                if datetime.now(UTC) >= expires_at:
                    return False
            weather = cache.get("weather")
            if not isinstance(weather, dict):
                return False
            weather["city"] = display_name
            self._weather_data.update(weather)
            return True
        except (json.JSONDecodeError, TypeError, ValueError, OverflowError):
            return False

    def _update_refresh_interval(self) -> None:
        minutes = self._get("refresh_interval", 30, type_=int)
        self._refresh_timer.start(minutes * 60 * 1000)

    def _weather_code_to_text(self, code: int) -> str:
        # Simplified WMO codes
        if code == 0:
            return t("weather.desc.clear", "Clear")
        if code <= 3:
            return t("weather.desc.cloudy", "Cloudy")
        if code <= 48:
            return t("weather.desc.fog", "Fog")
        if code <= 67:
            return t("weather.desc.rain", "Rain")
        if code <= 77:
            return t("weather.desc.snow", "Snow")
        if code <= 82:
            return t("weather.desc.showers", "Showers")
        return t("weather.desc.storm", "Storm")

    # ------------------------------------------------------------------
    # Appearance — called by _apply_and_resize (base class pattern)
    #
    # Like OverlayClockWidget._apply_appearance(), this method:
    #   1. Sets fonts and colors on all labels
    #   2. Updates label TEXT from current data (_weather_data) — the "tick"
    #   3. Does NOT call _force_resize(); that is handled by _apply_and_resize()
    # ------------------------------------------------------------------

    def _apply_appearance(self) -> None:
        """Apply unified styling then render current weather to template."""
        self._apply_base_appearance()

        # We always render to the template label for maximum layout flexibility.
        # This resolves the report of scaling issues by using the base class engine.
        html = self._resolve_weather_template(
            self._get("weather_template", self._DEFAULT_TEMPLATE), self._weather_data
        )
        self._set_template_label(html)

        # Hide old labels if they still exist (legacy support)
        for label in (self._icon_label, self._temp_label, self._city_label):
            if label:
                label.setVisible(False)

        source_names = t("widget.weather.source_attribution", "MET Norway · GeoNames")
        source_html = source_names.replace(
            "MET Norway", f'<a href="{MET_LICENSE_URL}">MET Norway</a>'
        ).replace("GeoNames", f'<a href="{GEONAMES_LICENSE_URL}">GeoNames</a>')
        self._source_label.setText(source_html)
        self._source_label.setStyleSheet(
            "font-size: 8px; color: rgba(170,180,195,180); background: transparent;"
        )
        self._source_label.setVisible(True)

    def _refresh_face(self) -> None:
        """Re-render widget after data update."""
        self._apply_and_resize()

    def _resolve_weather_template(self, template: str, data: dict) -> str:
        """Resolve variables and tags in weather template."""
        template = _inject_global_lh(template)
        template = _protect_align_tags(template)
        template = _BaseOverlayWidget._process_conditionals(template, data)

        wmo = int(data.get("_wmo", 0))
        # text_color_rgba() → "#rrggbb" hex 추출 (베이스 클래스 표준 메서드)
        rgba = self.text_color_rgba()
        icon_color = rgba[:7] if rgba and rgba.startswith("#") and len(rgba) >= 7 else "#4db8ff"

        def _replace(m: re.Match) -> str:
            inner = m.group(1).split("|")
            key, hints = inner[0].strip(), inner[1:]

            # {icon} 또는 {icon|size=N} → mdi6 아이콘 <img> 태그
            if key == "icon":
                # size= 힌트 파싱
                px = 32
                for h in hints:
                    if h.startswith("size="):
                        with contextlib.suppress(ValueError):
                            px = int(h[5:])
                img = _weather_icon_b64(wmo, icon_color, px)
                return img if img else _apply_span(str(data.get("desc", "")), hints)

            val = str(data.get(key, ""))
            return _apply_span(val, hints)

        result = re.sub(r"\{([^}]+)\}", _replace, template)
        return _apply_align_tags(result)

    def _open_settings(self) -> None:
        """Show standardized settings dialog with schema-based fields."""
        extra = [
            {
                "key": "location",
                "label": t("widget.weather.location", "Location:"),
                "type": "text",
                "placeholder": t("widget.weather.location_placeholder", "Seoul"),
                "default": "Seoul",
            },
            {
                "key": "unit",
                "label": t("widget.weather.unit", "Unit:"),
                "type": "combo",
                "options": [
                    (t("widget.weather.unit_c", "Celsius (°C)"), "celsius"),
                    (t("widget.weather.unit_f", "Fahrenheit (°F)"), "fahrenheit"),
                ],
                "default": "celsius",
            },
            {
                "key": "refresh_interval",
                "label": t("widget.weather.refresh_interval", "Refresh:"),
                "type": "int_combo",
                "options": [
                    (t("widget.weather.refresh_min", f"Every {m} min", min=m), m)
                    for m in (5, 10, 30, 60, 120)
                ],
                "default": 30,
            },
        ]

        # Use the generic dialog builder!
        if self._open_standard_settings_dialog(
            title=t("widget.weather.settings_title", "Weather Settings"),
            extra_fields=extra,
            has_template=True,
            default_template=self._DEFAULT_TEMPLATE,
            template_hint=t(
                "widget.weather.template_hint", "Variables: {city} {temp} {unit} {desc} {icon}"
            ),
            preview_render_fn=lambda tmpl: self._resolve_weather_template(tmpl, self._weather_data),
        ):
            # Special post-acceptance logic for weather widget
            self._update_refresh_interval()
            self.request_update()

    def _build_context_menu(self, menu: QMenu) -> None:
        menu.addAction(
            t("widget.weather.settings", "Weather Settings..."),
            self._open_settings,
        )

    # ------------------------------------------------------------------
    # Startup — identical pattern to OverlayClockWidget
    # ------------------------------------------------------------------

    def apply_initial_settings(self) -> None:
        self._apply_and_resize()
        self.restore_position(QPoint(-230, 420))
        if self.is_enabled():
            self._show_with_correct_size()
