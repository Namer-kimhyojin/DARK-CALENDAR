# -*- coding: utf-8 -*-
"""Overlay weather widget using local GeoNames lookup and MET Norway data."""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import escape
import json
import logging
import math
import time

from PyQt6.QtCore import QPoint, QSize, Qt, QTimer, QUrl, QUrlQuery
from PyQt6.QtNetwork import QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QMenu,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
)

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
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
)
from calendar_app.presentation.widgets.overlay_base import (
    _DLG_SS,
    _BaseOverlayWidget,
    _GripFrame,
    _parse_rgba,
    _rgba_css,
)
from calendar_app.presentation.widgets.overlay_template_utils import _preview_base_size
from calendar_app.presentation.widgets.weather_asset_packs import (
    DEFAULT_WEATHER_ASSET_PACK_ID,
    get_weather_asset_pack,
    weather_asset_html,
    weather_asset_packs,
    weather_pack_icon,
    weather_pack_preview_pixmap,
)
from calendar_app.presentation.widgets.weather_template import (
    render_weather_template,
    scale_weather_preview_images,
)

logger = logging.getLogger(__name__)


def _weather_icon_b64(wmo_code: int, color: str, size: int) -> str:
    """WMO 코드 → mdi6 아이콘 → base64 PNG → HTML <img> 태그 반환."""
    return weather_asset_html("classic", wmo_code, "day", size, color=color)


_NETWORK_TIMEOUT_MS = 10_000  # abort reply after 10 s
_APP_HOMEPAGE = "https://namer-kimhyojin.github.io/DARK-CALENDAR/"
_MET_USER_AGENT = f"AirCalendar/{APP_VERSION} {_APP_HOMEPAGE}".encode("utf-8", errors="strict")


def _weather_source_html() -> str:
    """Keep provider credits accessible without adding a permanent widget footer."""
    policy = escape(t("widget.weather.sources_policy", "이용 안내"))
    forecast = escape(t("widget.weather.forecast_source", "날씨 데이터"))
    location = escape(t("widget.weather.location_source", "도시 위치 데이터"))
    license_label = escape(t("widget.weather.sources_license", "데이터 라이선스"))
    changes = escape(
        t(
            "widget.weather.sources_changes",
            "Air Calendar는 도시 검색과 날씨 표시를 위해 데이터를 추출하고 단위·표시 형식을 변환합니다.",
        )
    )
    disclaimer = escape(
        t(
            "widget.weather.sources_disclaimer",
            "제공 데이터는 정확성·최신성·완전성을 보증하지 않습니다.",
        )
    )
    return (
        f'<p><b>{forecast}</b><br><a href="{MET_FORECAST_ENDPOINT}">MET Norway</a>'
        f' · <a href="{MET_LICENSE_URL}">{policy}</a></p>'
        f'<p><b>{location}</b><br><a href="{GEONAMES_LICENSE_URL}">GeoNames</a>'
        f' · <a href="https://download.geonames.org/export/dump/readme.txt">{policy}</a></p>'
        f'<p>{license_label}: <a href="https://creativecommons.org/licenses/by/4.0/">'
        "Creative Commons Attribution 4.0 (CC BY 4.0)</a></p>"
        f"<p>{changes}</p><p>{disclaimer}</p>"
    )


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
    _DEFAULT_TEMPLATE = (
        "{icon|size=64}\n{temp|size=28|bold}{unit|size=14}\n{city|size=12|color=muted}"
    )

    _DLG_SS = _DLG_SS

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self, owner):
        super().__init__(owner)
        self._network_manager = get_network_manager()
        # Note: Finished signal will be handled via per-request reply finished.
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._scheduled_update)
        self._pending_replies: list[QNetworkReply] = []
        self._runtime_active = False
        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self.request_update)
        self._failure_count = 0
        self._request_key: tuple[str, str] | None = None
        self._status_text = ""
        self._rate_limited_until = 0.0

        self._weather_data: dict = {
            "city": "---",
            "temp": "--",
            "unit": "°C",
            "humidity": "--",
            "wind": "--",
            "desc": "--",
            "_wmo": 0,
            "_day_period": "day",
            "error": "",
        }

        if self.is_enabled():
            self._set_runtime_active(True)

    def _settings_prefix(self) -> str:
        return self._PREFIX

    def _default_font_size(self) -> int:
        # Template text and illustrations share the same 24-point reference.
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

        self._status_label = QLabel("", frame)
        self._status_label.setObjectName("weatherStatus")
        self._status_label.setTextFormat(Qt.TextFormat.PlainText)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        return frame

    def request_update(self) -> None:
        """Fetch the latest MET Norway forecast for the configured city."""
        if not self._runtime_active:
            return
        remaining = self._rate_limited_until - time.monotonic()
        if remaining > 0:
            self._retry_timer.start(math.ceil(remaining * 1000))
            return
        location = str(self._get("location", "Seoul") or "").strip()
        request_key = (location, str(self._get("unit", "celsius")))
        if self._pending_replies and request_key == self._request_key:
            return
        if request_key != self._request_key:
            self._cancel_pending_replies()
            self._failure_count = 0
            self._weather_data.update(
                city=location,
                temp="--",
                error="",
                _wmo=-1,
                unit="°F" if request_key[1] == "fahrenheit" else "°C",
            )
        self._request_key = request_key
        self._retry_timer.stop()
        self._status_text = t("widget.weather.loading", "날씨를 불러오는 중…")
        self._refresh_face()

        # 인스턴스별 캐시 키 사용 (_get/_set 이용 → prefix 자동 적용)
        cached_loc = self._get("resolved_name", "")
        try:
            lat = float(self._get("lat"))
            lon = float(self._get("lon"))
        except (TypeError, ValueError, OverflowError):
            lat = lon = math.nan

        if location != cached_loc or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            self._geocode_location(location)
            return

        # Fetch weather using cached coords (display_name은 지오코딩 결과 사용)
        display_name = self._get("display_name", location)
        self._fetch_weather(lat, lon, display_name)

    def _scheduled_update(self) -> None:
        if not self._retry_timer.isActive():
            self.request_update()

    def _watch_reply(self, reply: QNetworkReply) -> None:
        """타임아웃 타이머 연결 — 10 s 초과 시 abort."""
        timer = QTimer(reply)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda r=reply: r.abort() if not r.isFinished() else None)
        reply.finished.connect(timer.stop)
        timer.start(_NETWORK_TIMEOUT_MS)

    def _cancel_pending_replies(self) -> None:
        replies = list(self._pending_replies)
        self._pending_replies.clear()
        for reply in replies:
            if reply.isRunning():
                reply.abort()
            reply.deleteLater()

    def _show_error(self, msg: str, *, retry_seconds: int | None = None) -> None:
        self._weather_data["error"] = msg
        self._status_text = msg
        if self._weather_data.get("temp") != "--":
            self._status_text = t("widget.weather.stale", "이전 날씨 표시 · {error}", error=msg)
        if retry_seconds is not None and self._runtime_active:
            self._failure_count += 1
            delay = max(retry_seconds, min(60 * 2 ** min(self._failure_count - 1, 4), 900))
            self._retry_timer.start(delay * 1000)
            self._status_text += " · " + t(
                "widget.weather.retry_in", "{min}분 후 재시도", min=math.ceil(delay / 60)
            )
        self._refresh_face()

    def _geocode_location(self, name: str) -> None:
        """Resolve a city using the bundled GeoNames dataset."""
        try:
            city = find_city(name)
        except (UnicodeError, ValueError):
            city = None
        if city is None:
            logger.warning("Local GeoNames lookup failed for: %s", name)
            self._show_error(t("weather.error.location_not_found", "위치를 찾을 수 없습니다"))
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
            self._status_text = t("widget.weather.cached", "저장된 최신 날씨")
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
        # Validators belong to this exact forecast and unit, not to another city.
        cache_matches = self._restore_weather_cache(
            lat, lon, display_name, unit, require_fresh=False
        )
        last_modified = (
            str(self._get("met_cache_last_modified", "") or "").strip() if cache_matches else ""
        )
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
        if reply not in self._pending_replies or not self._runtime_active:
            reply.deleteLater()
            return
        self._pending_replies.remove(reply)

        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        error_message = ""
        retry_seconds = 60
        if status == 304:
            if self._restore_weather_cache(lat, lon, display_name, unit, require_fresh=False):
                self._store_response_headers(reply)
            else:
                self._set("met_cache_last_modified", "")
                error_message = t("weather.error.parse_failed", "데이터 파싱 오류")
        elif reply.error() == QNetworkReply.NetworkError.NoError:
            try:
                data = json.loads(reply.readAll().data().decode("utf-8", errors="replace"))
                self._weather_data["error"] = ""
                self._update_weather_data(data, display_name, unit)
                self._store_weather_cache(lat, lon, display_name, unit)
                self._store_response_headers(reply)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError, OverflowError) as exc:
                logger.warning("MET Norway response parse failed: %s", exc)
                error_message = t("weather.error.parse_failed", "데이터 파싱 오류")
        elif reply.error() == QNetworkReply.NetworkError.OperationCanceledError:
            error_message = t("weather.error.timeout", "요청 시간 초과")
        elif status == 403:
            error_message = t("weather.error.denied", "날씨 서비스 접근이 거부되었습니다")
            retry_seconds = None
        elif status == 429:
            error_message = t("weather.error.busy", "날씨 서비스 요청이 많아 대기 중입니다")
            retry_after = bytes(reply.rawHeader(b"Retry-After")).decode("utf-8", errors="replace")
            try:
                retry_seconds = max(900, int(retry_after))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    retry_seconds = max(
                        900, math.ceil((retry_at - datetime.now(UTC)).total_seconds())
                    )
                except (TypeError, ValueError, OverflowError):
                    retry_seconds = 900
            retry_seconds = min(retry_seconds, 86400)
            self._rate_limited_until = time.monotonic() + retry_seconds
        else:
            error_message = t("weather.error.network", "네트워크 오류")
        if error_message:
            logger.warning("Weather request failed: status=%s error=%s", status, reply.error().name)
            self._restore_weather_cache(lat, lon, display_name, unit, require_fresh=False)
            self._show_error(error_message, retry_seconds=retry_seconds)
        else:
            self._failure_count = 0
            self._retry_timer.stop()
            self._status_text = t(
                "widget.weather.updated", "{time} 업데이트", time=datetime.now().strftime("%H:%M")
            )
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
        if expires or reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) != 304:
            self._set("met_cache_expires", expires)
        if (
            last_modified
            or reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) != 304
        ):
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
            if not isinstance(cache, dict):
                return False
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
            if not math.isfinite(float(weather.get("temp"))):
                return False
            int(weather.get("_wmo"))
            weather["city"] = display_name
            weather["error"] = ""
            self._weather_data.update(weather)
            return True
        except (json.JSONDecodeError, TypeError, ValueError, OverflowError):
            return False

    def _refresh_minutes(self) -> int:
        raw = self._get("refresh_interval", 30)
        # Older settings saved the whole (translated label, minutes) combo item.
        value = raw[-1] if isinstance(raw, (tuple, list)) and len(raw) == 2 else raw
        try:
            minutes = int(value) if not isinstance(value, bool) else 30
        except (TypeError, ValueError, OverflowError):
            minutes = 30
        if minutes not in {5, 10, 30, 60, 120}:
            minutes = 30
        if type(raw) is not int or raw != minutes:
            self._set("refresh_interval", minutes)
        return minutes

    def _update_refresh_interval(self) -> None:
        minutes = self._refresh_minutes()
        if not self._runtime_active:
            self._refresh_timer.stop()
            return
        self._refresh_timer.start(minutes * 60 * 1000)

    def _set_runtime_active(self, active: bool) -> None:
        was_active = self._runtime_active
        self._runtime_active = active
        if active:
            self._update_refresh_interval()
            if not was_active:
                QTimer.singleShot(0, self.request_update)
            return
        self._refresh_timer.stop()
        self._retry_timer.stop()
        self._cancel_pending_replies()

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

        # Text and illustration sizes both follow the current fitted font size.
        html = self._resolve_weather_template(
            self._get("weather_template", self._DEFAULT_TEMPLATE), self._weather_data
        )
        self._set_template_label(html)

        # Hide old labels if they still exist (legacy support)
        for label in (self._icon_label, self._temp_label, self._city_label):
            if label:
                label.setVisible(False)

        self._status_label.setText(self._status_text)
        # Keep successful compact/custom layouts at their original height.
        # Loading and errors remain visible even when {error} is absent from the template.
        self._status_label.setVisible(
            bool(self._weather_data.get("error"))
            or self._status_text == t("widget.weather.loading", "날씨를 불러오는 중…")
        )
        status_color = _rgba_css(*_parse_rgba(self.text_color_rgba()))
        self._status_label.setStyleSheet(
            f"font-size: 9px; color: {status_color}; background: transparent;"
        )
        self.face.setToolTip(self._status_text)

    def _refresh_face(self) -> None:
        """Re-render widget after data update."""
        self._apply_and_resize()

    def _resolve_weather_template(
        self,
        template: str,
        data: dict,
        *,
        asset_pack_id: str | None = None,
        base_font_size: int | None = None,
    ) -> str:
        """Render escaped weather values with proportional illustration sizing."""
        selected_pack_id = asset_pack_id or str(
            self._get("weather_asset_pack", DEFAULT_WEATHER_ASSET_PACK_ID)
        )
        color, _ = _parse_rgba(self.text_color_rgba())
        return render_weather_template(
            template,
            data,
            asset_pack_id=selected_pack_id,
            base_font_size=self._template_render_font_size()
            if base_font_size is None
            else base_font_size,
            icon_color=color.name(),
            resolve_text_sizes=False,
        )

    def _current_weather_design_id(self) -> str:
        """A custom edit must not keep a stale 'selected theme' indicator."""
        from calendar_app.presentation.widgets.weather_designs import weather_designs

        template = str(self._get("weather_template", self._DEFAULT_TEMPLATE))
        asset_pack = get_weather_asset_pack(
            self._get("weather_asset_pack", DEFAULT_WEATHER_ASSET_PACK_ID)
        ).pack_id
        for design in weather_designs():
            if (
                design.template == template
                and design.asset_pack_id == asset_pack
                and design.appearance_preset_id == self.display_preset_id()
                and design.shape == self.widget_shape_id()
            ):
                return design.design_id
        return ""

    def _wrap_preview_html(
        self,
        html: str,
        align: str = "center",
        preview_size: QSize | None = None,
        *,
        base_size: int | None = None,
    ) -> str:
        preview_size = preview_size or QSize(320, 240)
        html = scale_weather_preview_images(html, base_size or _preview_base_size(preview_size))
        return super()._wrap_preview_html(
            html,
            align=align,
            preview_size=preview_size,
            base_size=base_size,
        )

    def _open_design_gallery(self) -> None:
        from calendar_app.presentation.widgets.weather_design_dialog import (
            WeatherDesignGalleryDialog,
        )

        dialog = WeatherDesignGalleryDialog(
            self._weather_data,
            self,
            current_design_id=self._current_weather_design_id(),
            current_asset_pack=get_weather_asset_pack(
                self._get("weather_asset_pack", DEFAULT_WEATHER_ASSET_PACK_ID)
            ).pack_id,
            current_appearance=self.display_preset_id(),
        )
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_design:
                self._apply_weather_design(dialog.selected_design.design_id)
        finally:
            dialog.deleteLater()

    def _apply_weather_design(self, design_id: str) -> None:
        """Commit a complete design to this instance, retaining its weather/location."""
        from calendar_app.presentation.widgets.weather_designs import weather_design

        design = weather_design(design_id)
        if design is None:
            return
        original_shape = self.widget_shape_id()
        self._store_display_preset(design.appearance_preset_id)
        self._set("weather_template", design.template)
        self._set("weather_asset_pack", design.asset_pack_id)
        self._set("weather_design_id", design.design_id)
        width = self._normalized_fixed_dimension("fixed_w")
        height = self._normalized_fixed_dimension("fixed_h")
        if original_shape != design.shape or (
            design.shape != "card" and (width is None or height is None)
        ):
            if original_shape == design.shape:
                self._apply_and_resize()
            self._set_widget_shape(design.shape)
        else:
            if width is not None and height is not None:
                width, height = self._constrain_shape_size(width, height)
                self._set("fixed_w", width)
                self._set("fixed_h", height)
        self._last_content_reset = None
        self._apply_and_resize(refit=True)

    def _open_settings(self) -> None:
        """Show standardized settings dialog with schema-based fields."""
        self._refresh_minutes()
        extra = [
            {
                "key": "weather_asset_pack",
                "label": t("widget.weather.asset_pack", "일러스트 팩:"),
                "type": "combo",
                "options": [
                    (t(pack.label_key, pack.label_default), pack.pack_id)
                    for pack in weather_asset_packs()
                ],
                "default": DEFAULT_WEATHER_ASSET_PACK_ID,
            },
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
                "type": "combo",
                "options": [
                    (t("widget.weather.refresh_every", "매 {min}분", min=m), m)
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
                "widget.weather.template_hint",
                "Variables: {city} {temp} {unit} {desc} {icon} {humidity} {wind}",
            ),
            preview_render_fn=lambda tmpl: self._resolve_weather_template(
                tmpl,
                self._weather_data,
                asset_pack_id=self._selected_dialog_asset_pack(),
            ),
            extra_basic_setup_fn=self._setup_weather_asset_preview,
            extra_dialog_setup_fn=self._setup_weather_design_draft,
        ):
            # Special post-acceptance logic for weather widget
            self._update_refresh_interval()
            self.request_update()

    def _selected_dialog_asset_pack(self) -> str:
        combo = getattr(self, "_active_settings_widgets", {}).get("weather_asset_pack")
        if combo is not None and hasattr(combo, "currentData"):
            return get_weather_asset_pack(combo.currentData()).pack_id
        return get_weather_asset_pack(
            self._get("weather_asset_pack", DEFAULT_WEATHER_ASSET_PACK_ID)
        ).pack_id

    def _setup_weather_asset_preview(self, basic, dialog) -> None:
        designs = QPushButton(t("widget.weather.design_gallery", "날씨 디자인 고르기…"), dialog)
        designs.setObjectName("ghost_btn")
        designs.setProperty("weatherDesignGallery", True)
        designs.setAutoDefault(False)
        designs.setMinimumHeight(40)
        basic.addWidget(designs)
        preview_title = QLabel(t("widget.weather.asset_preview", "일러스트 미리보기"), dialog)
        preview_title.setStyleSheet("font-weight: 600; margin-top: 8px;")
        basic.addWidget(preview_title)
        preview = QLabel(dialog)
        preview.setObjectName("weatherAssetPreview")
        preview.setMinimumHeight(112)
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setStyleSheet(
            "QLabel#weatherAssetPreview { background: rgba(127, 145, 168, 24); "
            "border: 1px solid rgba(127, 145, 168, 56); border-radius: 12px; }"
        )
        basic.addWidget(preview)
        help_label = QLabel(
            t(
                "widget.weather.asset_pack_help",
                "현재 날씨와 낮·밤에 맞는 그림이 자동으로 선택됩니다.",
            ),
            dialog,
        )
        help_label.setWordWrap(True)
        basic.addWidget(help_label)
        combo = self._active_settings_widgets["weather_asset_pack"]
        combo.setIconSize(QSize(34, 34))
        combo.setMinimumHeight(44)
        for index, pack in enumerate(weather_asset_packs()):
            combo.setItemIcon(index, weather_pack_icon(pack.pack_id))

        def _refresh_preview() -> None:
            preview.setPixmap(weather_pack_preview_pixmap(combo.currentData(), QSize(300, 104)))

        combo.currentIndexChanged.connect(_refresh_preview)
        _refresh_preview()
        sources = QPushButton(t("widget.weather.sources_title", "날씨 데이터 출처"), dialog)
        sources.setObjectName("ghost_btn")
        sources.setProperty("weatherSources", True)
        sources.setAutoDefault(False)
        sources.clicked.connect(lambda checked=False: self._show_data_sources(dialog))
        basic.addWidget(sources)

    def _setup_weather_design_draft(self, dialog, controls: dict) -> None:
        """Gallery selections inside Settings stay in its draft until Save."""
        from calendar_app.presentation.widgets.weather_design_dialog import (
            WeatherDesignGalleryDialog,
        )
        from calendar_app.presentation.widgets.weather_designs import weather_designs

        tabs = dialog.findChild(QTabWidget)
        if tabs is not None:
            tabs.setCurrentIndex(0)
        footer = dialog.findChild(QDialogButtonBox)
        if footer is not None:
            save = footer.button(QDialogButtonBox.StandardButton.Ok)
            cancel = footer.button(QDialogButtonBox.StandardButton.Cancel)
            if save is not None:
                save.setText(t("common.save", "저장"))
                save.setObjectName("primary_btn")
            if cancel is not None:
                cancel.setText(t("common.cancel", "취소"))
                cancel.setObjectName("ghost_btn")

        button = next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.property("weatherDesignGallery")
        )

        def choose_design() -> None:
            appearance = str(controls["display_preset_combo"].currentData() or "custom")
            asset_pack = self._selected_dialog_asset_pack()
            shape = str(controls["shape_combo"].currentData() or "card")
            template = controls["template_editor"].toPlainText()
            current_id = next(
                (
                    design.design_id
                    for design in weather_designs()
                    if design.template == template
                    and design.asset_pack_id == asset_pack
                    and design.appearance_preset_id == appearance
                    and design.shape == shape
                ),
                "",
            )
            gallery = WeatherDesignGalleryDialog(
                self._weather_data,
                dialog,
                current_design_id=current_id,
                current_asset_pack=asset_pack,
                current_appearance=appearance,
            )
            try:
                if gallery.exec() != QDialog.DialogCode.Accepted or not gallery.selected_design:
                    return
                design = gallery.selected_design
                for combo, value in (
                    (self._active_settings_widgets["weather_asset_pack"], design.asset_pack_id),
                    (controls["display_preset_combo"], design.appearance_preset_id),
                    (controls["shape_combo"], design.shape),
                ):
                    index = combo.findData(value)
                    if index >= 0:
                        combo.setCurrentIndex(index)
                controls["template_editor"].setPlainText(design.template)
            finally:
                gallery.deleteLater()

        button.clicked.connect(choose_design)

    def _show_data_sources(self, parent=None) -> None:
        """Read-only credits, shared by the context menu and weather settings."""
        dialog = QDialog(parent if parent is not None else self)
        apply_dialog_title(dialog, t("widget.weather.sources_title", "날씨 데이터 출처"))
        apply_common_dialog_style(dialog, minimum_width=480)
        root = QVBoxLayout(dialog)
        body = QLabel(_weather_source_html(), dialog)
        body.setObjectName("weatherDataSources")
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setWordWrap(True)
        body.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.TextSelectableByMouse
        )
        body.setOpenExternalLinks(True)
        root.addWidget(body)
        footer, close, _ = build_dialog_footer(t("common.close", "닫기"), cancel_label=None)
        close.clicked.connect(dialog.accept)
        root.addLayout(footer)
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()

    def _set_weather_asset_pack(self, pack_id: str) -> None:
        normalized = get_weather_asset_pack(pack_id).pack_id
        self._set("weather_asset_pack", normalized)
        self._refresh_face()

    def _build_context_menu(self, menu: QMenu) -> None:
        menu.addAction(t("widget.weather.refresh_now", "날씨 다시 불러오기"), self.request_update)
        menu.addAction(
            t("widget.weather.design_gallery", "날씨 디자인 고르기…"), self._open_design_gallery
        )
        menu.addAction(
            t("widget.weather.settings", "Weather Settings..."),
            self._open_settings,
        )
        menu.addAction(
            t("widget.weather.sources_title", "날씨 데이터 출처"),
            lambda checked=False: self._show_data_sources(),
        )
        pack_menu = menu.addMenu(t("widget.weather.asset_pack", "일러스트 팩"))
        current_pack = get_weather_asset_pack(
            self._get("weather_asset_pack", DEFAULT_WEATHER_ASSET_PACK_ID)
        ).pack_id
        for pack in weather_asset_packs():
            action = pack_menu.addAction(
                t(pack.label_key, pack.label_default),
                lambda *_, selected=pack.pack_id: self._set_weather_asset_pack(selected),
            )
            action.setCheckable(True)
            action.setChecked(pack.pack_id == current_pack)

    # ------------------------------------------------------------------
    # Startup — identical pattern to OverlayClockWidget
    # ------------------------------------------------------------------

    def _on_double_click(self) -> bool:
        self._open_settings()
        return True

    def apply_initial_settings(self) -> None:
        self._apply_and_resize()
        self.restore_position(QPoint(-230, 420))
        if self.is_enabled():
            self._show_with_correct_size()
