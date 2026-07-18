# -*- coding: utf-8 -*-
"""Local GeoNames city lookup for the bundled ``cities15000`` dataset."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import logging
import re
import unicodedata

from calendar_app.app_paths import get_resource_path

logger = logging.getLogger(__name__)

_GEONAMES_RELATIVE_PATH = ("geonames", "cities15000.txt")


@dataclass(frozen=True)
class GeoNameCity:
    name: str
    latitude: float
    longitude: float
    country_code: str
    population: int


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    return re.sub(r"\s+", " ", value)


def _split_query(query: str) -> tuple[str, str | None]:
    parts = [part.strip() for part in str(query or "").split(",") if part.strip()]
    if not parts:
        return "", None
    country = parts[-1].upper() if len(parts) > 1 and len(parts[-1]) == 2 else None
    city = ",".join(parts[:-1] if country else parts).strip()
    return _normalize(city), country


@lru_cache(maxsize=256)
def find_city(query: str) -> GeoNameCity | None:
    """Return the largest exact GeoNames city match for ``query``.

    ``query`` may optionally end in a two-letter country code, for example
    ``"Springfield, US"``. Names and alternate names are matched case-insensitively.
    """

    normalized_query, country_filter = _split_query(query)
    if not normalized_query:
        return None

    dataset_path = get_resource_path(*_GEONAMES_RELATIVE_PATH)
    best: GeoNameCity | None = None
    best_score = -1

    try:
        with open(dataset_path, encoding="utf-8", errors="strict") as dataset:
            for raw_line in dataset:
                fields = raw_line.rstrip("\n").split("\t")
                if len(fields) < 15:
                    continue

                country_code = fields[8].strip().upper()
                if country_filter and country_code != country_filter:
                    continue

                primary_name = fields[1].strip()
                ascii_name = fields[2].strip()
                matched = normalized_query in {_normalize(primary_name), _normalize(ascii_name)}
                if not matched and fields[3]:
                    matched = any(
                        _normalize(alias) == normalized_query for alias in fields[3].split(",")
                    )
                if not matched:
                    continue

                try:
                    latitude = float(fields[4])
                    longitude = float(fields[5])
                    population = int(fields[14] or 0)
                except (TypeError, ValueError):
                    continue

                feature_code = fields[7].strip().upper()
                capital_bonus = 10**12 if feature_code == "PPLC" else 0
                score = capital_bonus + population
                if score > best_score:
                    best = GeoNameCity(
                        name=primary_name,
                        latitude=latitude,
                        longitude=longitude,
                        country_code=country_code,
                        population=population,
                    )
                    best_score = score
    except OSError as exc:
        logger.error("GeoNames city dataset unavailable at %s: %s", dataset_path, exc)
        return None

    return best
