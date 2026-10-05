# -*- coding: utf-8 -*-
"""MET Norway Locationforecast response helpers."""

from __future__ import annotations

import math
from typing import Any

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
    payload: dict[str, Any], display_name: str, unit: str = "celsius"
) -> dict[str, Any]:
    """Parse the first Locationforecast time step for the weather widget."""

    entry = _first_forecast_entry(payload)
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
    return {
        "city": display_name,
        "temp": f"{temperature:.1f}".rstrip("0").rstrip("."),
        "unit": unit_label,
        "humidity": str(details.get("relative_humidity", "--")),
        "wind": str(details.get("wind_speed", "--")),
        "_wmo": symbol_code_to_wmo(symbol_code),
        "_day_period": symbol_code_to_day_period(symbol_code),
    }
