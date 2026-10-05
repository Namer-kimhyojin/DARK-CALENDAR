# -*- coding: utf-8 -*-
"""ICS timestamps use the shared display zone without moving all-day dates."""

from datetime import UTC, date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from calendar_app.infrastructure.ics import ics_fetcher


def field(value):
    return SimpleNamespace(dt=value)


def test_ics_aware_dates_convert_to_shared_zone():
    start = field(datetime(2026, 10, 5, 23, 0, tzinfo=UTC))
    end = field(datetime(2026, 10, 6, 0, 0, tzinfo=UTC))
    assert ics_fetcher._parse_dt(start, end, ZoneInfo("Asia/Seoul")) == (
        "2026-10-06 08:00",
        "2026-10-06 09:00",
        False,
    )
    assert ics_fetcher._parse_dt(start, end, ZoneInfo("America/New_York")) == (
        "2026-10-05 19:00",
        "2026-10-05 20:00",
        False,
    )


def test_ics_floating_dates_keep_original_wall_time():
    assert ics_fetcher._parse_dt(field(datetime(2026, 10, 5, 14)), None, ZoneInfo("UTC")) == (
        "2026-10-05 14:00",
        None,
        False,
    )


def test_ics_all_day_exclusive_end_stays_on_original_dates():
    assert ics_fetcher._parse_dt(
        field(date(2026, 10, 5)), field(date(2026, 10, 7)), ZoneInfo("America/New_York")
    ) == ("2026-10-05", "2026-10-06", True)


def test_invalid_shared_zone_fails_before_network_or_db(monkeypatch):
    network = Mock()
    monkeypatch.setattr(ics_fetcher.urllib.request, "urlopen", network)
    assert ics_fetcher.fetch_and_sync(
        "ics::fixture", "https://example.invalid", local_zone="Invalid/Fixture"
    ) == (0, 0, "invalid_timezone")
    network.assert_not_called()


def test_private_subscription_url_is_not_in_failure_logs(monkeypatch, caplog):
    from urllib.error import URLError

    url = "https://example.invalid/calendar.ics?token=synthetic-private-value"
    monkeypatch.setattr(ics_fetcher, "_try_import_icalendar", lambda: object())
    monkeypatch.setattr(ics_fetcher.urllib.request, "urlopen", Mock(side_effect=URLError(url)))
    assert ics_fetcher.fetch_and_sync("ics::fixture", url)[2] == "network_unavailable"
    assert "synthetic-private-value" not in caplog.text
