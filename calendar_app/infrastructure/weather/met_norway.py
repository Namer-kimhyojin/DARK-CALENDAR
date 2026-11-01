# -*- coding: utf-8 -*-
"""MET Norway Locationforecast response helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import math
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MET_FORECAST_ENDPOINT = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
MET_LICENSE_URL = "https://api.met.no/doc/License"
GEONAMES_LICENSE_URL = "https://www.geonames.org/export/"


def symbol_code_to_wmo(symbol_code: str) -> int:
    """Map MET Norway symbol codes to the widget's existing WMO-style icons."""

    symbol = str(symbol_code or "").lower()
    for suffix in ("_day", "_night", "_polartwilight"):
        if symbol.endswith(suffix):
            symbol = symbol[: -len(suffix)]
            break

    if "thunder" in symbol:
        return 95
    if "heavysnow" in symbol:
        return 75
    if "snow" in symbol or "sleet" in symbol:
        return 71
    if "heavyrain" in symbol:
        return 65
    if "rainshowers" in symbol:
        return 80
    if "rain" in symbol:
        return 61
    if "fog" in symbol:
        return 45
    if symbol == "cloudy":
        return 3
    if symbol in {"partlycloudy", "fair"}:
        return 2
    if symbol == "clearsky":
        return 0
    return 2


def symbol_code_to_day_period(symbol_code: str) -> str:
    """Preserve MET's day/night hint for weather illustration selection."""

    symbol = str(symbol_code or "").strip().lower()
    if symbol.endswith("_night"):
        return "night"
    if symbol.endswith("_polartwilight"):
        return "twilight"
    return "day"


def _first_forecast_entry(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("forecast must be an object")
    properties = payload.get("properties") or {}
    if not isinstance(properties, dict):
        raise ValueError("properties must be an object")
    timeseries = properties.get("timeseries") or []
    if not isinstance(timeseries, list) or not timeseries:
        raise KeyError("properties.timeseries")
    first = timeseries[0]
    if not isinstance(first, dict):
        raise KeyError("properties.timeseries[0]")
    return first


def parse_locationforecast(
    payload: dict[str, Any],
    display_name: str,
    unit: str = "celsius",
    *,
    now: datetime | None = None,
    timezone_name: str = "UTC",
) -> dict[str, Any]:
    """Read the current forecast step and six actual future steps, in city time.

    Six-hour precipitation totals are never presented as one-hour amounts. The
    temperature range covers the remaining local-day forecast, not observations.
    Older payloads without timestamps retain their original single-step contract.
    """

    entry = _first_forecast_entry(payload)
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        zone = UTC
        timezone_name = "UTC"
    timeline = []
    for item in payload["properties"]["timeseries"]:
        if not isinstance(item, dict):
            continue
        stamp = _forecast_datetime(item.get("time"))
        if stamp is None:
            continue
        try:
            value = float(item["data"]["instant"]["details"]["air_temperature"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(value):
            timeline.append((stamp, item, value))
    timeline.sort(key=lambda step: step[0])
    if timeline:
        past = [step for step in timeline if step[0] <= now]
        entry = (past[-1] if past else timeline[0])[1]
    data = entry.get("data") or {}
    if not isinstance(data, dict):
        raise ValueError("data must be an object")
    instant = data.get("instant") or {}
    if not isinstance(instant, dict):
        raise ValueError("instant must be an object")
    details = instant.get("details") or {}
    if not isinstance(details, dict):
        raise ValueError("details must be an object")
    if "air_temperature" not in details:
        raise KeyError("air_temperature")

    temperature = float(details["air_temperature"])
    if not math.isfinite(temperature):
        raise ValueError("air_temperature must be finite")
    if unit == "fahrenheit":
        temperature = temperature * 9 / 5 + 32
        unit_label = "°F"
    else:
        unit_label = "°C"

    summary: dict[str, Any] = {}
    for period_key in ("next_1_hours", "next_6_hours", "next_12_hours"):
        period = data.get(period_key) or {}
        if isinstance(period, dict) and isinstance(period.get("summary"), dict):
            summary = period["summary"]
            break

    symbol_code = str(summary.get("symbol_code") or "")
    result = {
        "city": display_name,
        "temp": f"{temperature:.1f}".rstrip("0").rstrip("."),
        "unit": unit_label,
        "humidity": str(details.get("relative_humidity", "--")),
        "wind": str(details.get("wind_speed", "--")),
        "_wmo": symbol_code_to_wmo(symbol_code),
        "_day_period": symbol_code_to_day_period(symbol_code),
    }
    if timeline:
        current_time = _forecast_datetime(entry.get("time"))
        today = now.astimezone(zone).date()
        upcoming = [step for step in timeline if now < step[0] <= now + timedelta(hours=6)]
        result["hourly"] = [
            _hourly_step(stamp, item, value, unit, zone) for stamp, item, value in upcoming[:6]
        ]
        remaining = [
            value
            for stamp, _, value in timeline
            if stamp >= (current_time or now) and stamp.astimezone(zone).date() == today
        ]
        result.update(
            forecast_time=current_time.isoformat() if current_time else "",
            timezone=timezone_name,
            forecast_high=_temperature_text(max(remaining), unit) if remaining else "--",
            forecast_low=_temperature_text(min(remaining), unit) if remaining else "--",
            _forecast_expired=timeline[-1][0] < now,
        )
    return result


def _forecast_datetime(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def _temperature_text(value: float, unit: str) -> str:
    if unit == "fahrenheit":
        value = value * 9 / 5 + 32
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _hourly_step(stamp: datetime, item: dict, value: float, unit: str, zone) -> dict:
    data = item.get("data")
    data = data if isinstance(data, dict) else {}
    period = data.get("next_1_hours")
    period = period if isinstance(period, dict) else {}
    summary = period.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    symbol = str(summary.get("symbol_code") or "")
    if not symbol:
        for key in ("next_6_hours", "next_12_hours"):
            fallback = data.get(key)
            summary = fallback.get("summary") if isinstance(fallback, dict) else {}
            symbol = str(summary.get("symbol_code") or "") if isinstance(summary, dict) else ""
            if symbol:
                break
    details = period.get("details")
    amount = details.get("precipitation_amount") if isinstance(details, dict) else None
    try:
        amount = float(amount)
        if not math.isfinite(amount) or amount < 0:
            amount = None
    except (TypeError, ValueError, OverflowError):
        amount = None
    return {
        "time": stamp.isoformat(),
        "label": stamp.astimezone(zone).strftime("%H:%M"),
        "temp": _temperature_text(value, unit),
        "_wmo": symbol_code_to_wmo(symbol),
        "_day_period": symbol_code_to_day_period(symbol),
        "precip_mm": amount,
    }
