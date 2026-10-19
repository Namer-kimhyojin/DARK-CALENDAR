# -*- coding: utf-8 -*-
"""Natural-language dates, valid clock ranges, and unchanged task wording."""

from datetime import datetime

import pytest

from calendar_app.infrastructure.nlp import nlp_engine


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 10, 14, 10, 0)

    monkeypatch.setattr(nlp_engine, "datetime", Clock)


@pytest.mark.parametrize(
    "phrase,date",
    [
        ("day after tomorrow", "2026-10-16"),
        ("DAY AFTER TOMORROW", "2026-10-16"),
        ("day   after   tomorrow", "2026-10-16"),
        ("tomorrow", "2026-10-15"),
        ("yesterday", "2026-10-13"),
        ("모레", "2026-10-16"),
        ("글피", "2026-10-17"),
    ],
)
def test_relative_phrase_uses_the_whole_longest_expression(phrase, date):
    assert nlp_engine.parse_nlp_task(f"{phrase} meeting at 3pm") == {
        "title": "meeting",
        "date": date,
        "time": "15:00",
    }


@pytest.mark.parametrize(
    "phrase,date",
    [
        ("수요일", "2026-10-21"),
        ("이번주 수요일", "2026-10-14"),
        ("이번주 월요일", "2026-10-12"),
        ("다음주 수요일", "2026-10-21"),
        ("다음 주 월요일", "2026-10-19"),
        ("다음주 목요일", "2026-10-22"),
        ("Wednesday", "2026-10-21"),
        ("next Wednesday", "2026-10-21"),
        ("next Monday", "2026-10-19"),
        ("next Thursday", "2026-10-22"),
    ],
)
def test_explicit_week_is_relative_to_the_current_calendar_week(phrase, date):
    result = nlp_engine.parse_nlp_task(f"{phrase} 회의")
    assert result["date"] == date
    assert result["title"] == "회의"


@pytest.mark.parametrize(
    "expression,time",
    [
        ("3시", "03:00"),
        ("15시", "15:00"),
        ("3시 30분", "03:30"),
        ("오후 4:30", "16:30"),
        ("오전 12시", "00:00"),
        ("오후 12시", "12:00"),
        ("밤 12시", "00:00"),
        ("0시", "00:00"),
        ("23시 59분", "23:59"),
        ("12am", "00:00"),
        ("12pm", "12:00"),
        ("4:30 PM", "16:30"),
        ("00:00", "00:00"),
        ("23:59", "23:59"),
    ],
)
def test_supported_clock_formats_are_valid_and_removed_from_the_title(expression, time):
    assert nlp_engine.parse_nlp_task(f"내일 {expression} 회의") == {
        "title": "회의",
        "date": "2026-10-15",
        "time": time,
    }


@pytest.mark.parametrize(
    "expression",
    [
        "오후 99시",
        "오후 3시 60분",
        "오후 3:99",
        "오전 13시",
        "99시",
        "24시",
        "13pm",
        "0am",
        "3:99pm",
        "24:00",
        "99:00",
        "100:00",
        "3:600pm",
    ],
)
def test_invalid_clock_expression_is_not_accepted_or_silently_removed(expression):
    assert nlp_engine.parse_nlp_task(f"내일 {expression} 회의") == {
        "title": f"{expression} 회의",
        "date": "2026-10-15",
        "time": None,
    }


@pytest.mark.parametrize(
    "text", ["Go to work", "Check in design", "Follow up on report", "Switch to test mode"]
)
def test_title_prepositions_survive_when_they_are_part_of_the_task(text):
    assert nlp_engine.parse_nlp_task(text)["title"] == text


def test_date_and_time_removal_preserves_prepositions_inside_the_title():
    assert nlp_engine.parse_nlp_task("tomorrow Go to work at 3pm")["title"] == "Go to work"


def test_failed_future_leap_date_does_not_leak_a_past_partial_result(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls):
            return cls(2028, 3, 1, 10, 0)

    monkeypatch.setattr(nlp_engine, "datetime", Clock)
    assert nlp_engine.parse_nlp_task("2/29 review") == {
        "title": "2/29 review",
        "date": "2028-03-01",
        "time": None,
    }


def test_month_day_rolls_forward_without_losing_the_title():
    assert nlp_engine.parse_nlp_task("1/2 review at 9am") == {
        "title": "review",
        "date": "2027-01-02",
        "time": "09:00",
    }


def test_empty_input_preserves_existing_fallback_contract():
    assert nlp_engine.parse_nlp_task("  ") == {
        "title": "제목 없음",
        "date": "2026-10-14",
        "time": None,
    }
