# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
import re

_TIME_PATTERNS = (
    ("kr_meridiem", re.compile(r"(오전|오후|저녁|밤|아침|새벽)\s*(\d+)[:시](?:\s*(\d+)분?)?")),
    ("en_meridiem", re.compile(r"\b(\d+)(?::(\d+))?\s*(am|pm)\b", re.IGNORECASE)),
    ("kr_clock", re.compile(r"(?<!\d)(\d+)시(?:\s*(\d+)분)?")),
    ("clock", re.compile(r"\b(\d+):(\d{2})\b")),
)


def _extract_time(title):
    candidates = [
        (match.start(), priority, kind, match)
        for priority, (kind, pattern) in enumerate(_TIME_PATTERNS)
        if (match := pattern.search(title)) is not None
    ]
    if not candidates:
        return title, None
    _, _, kind, match = min(candidates, key=lambda item: item[:2])
    if kind == "kr_meridiem":
        marker, hour, minute = match.groups()
    elif kind == "en_meridiem":
        hour, minute, marker = match.groups()
        marker = marker.lower()
    else:
        hour, minute = match.groups()
        marker = None
    minute = minute or "0"
    # Validate the entire token before removing it, including malformed clocks.
    # Length checks also bound integer conversion for exceptionally long input.
    if len(hour) > 2 or len(minute) > 2:
        return title, None
    h, m = int(hour), int(minute)
    if not 0 <= m < 60 or not (1 <= h <= 12 if marker else 0 <= h < 24):
        return title, None
    if marker in {"오후", "저녁", "밤", "pm"} and h < 12:
        h += 12
    elif marker in {"오전", "아침", "새벽", "밤", "am"} and h == 12:
        h = 0
    title = (title[: match.start()] + title[match.end() :]).strip()
    return title, f"{h:02d}:{m:02d}"


def parse_nlp_task(text: str):
    """
    Parses natural language text into task components.
    Supported (KR/EN):
    - "내일 3시 회의", "Tomorrow meeting at 3pm"
    - "오후 4:30 운동", "4:30 PM working out"
    - "목요일 점심 약속", "Lunch on Thursday"
    """
    now = datetime.now()
    target_date = now.date()
    target_time = None
    title = re.sub(r"\s+", " ", text.strip())

    # 1. Date Extraction
    date_found = False

    # Relative dates (KR/EN)
    rel_dates = {
        "그저께": -2,
        "어제": -1,
        "오늘": 0,
        "내일": 1,
        "모레": 2,
        "글피": 3,
        "yesterday": -1,
        "today": 0,
        "tomorrow": 1,
        "day after tomorrow": 2,
    }
    for kw, offset in sorted(rel_dates.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{kw}\b", title.lower()):
            target_date = (now + timedelta(days=offset)).date()
            # Case-insensitive replacement
            title = re.sub(rf"\b{kw}\b", "", title, flags=re.IGNORECASE).strip()
            date_found = True
            break

    # Weekdays (KR)
    kr_weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    kr_weekday_map = {w: i for i, w in enumerate(kr_weekdays)}

    weekday_match = re.search(r"(이번\s*주|다음\s*주)?\s*([월화수목금토일])요일?", title)
    if weekday_match:
        prefix = weekday_match.group(1)
        wd_str = weekday_match.group(2)
        target_wd = kr_weekday_map[wd_str]
        current_wd = now.weekday()

        days_ahead = target_wd - current_wd
        if prefix and prefix.replace(" ", "") == "다음주" or not prefix and days_ahead <= 0:
            days_ahead += 7
        target_date = (now + timedelta(days=days_ahead)).date()
        title = title.replace(weekday_match.group(0), "").strip()
        date_found = True

    # Weekdays (EN)
    en_weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    en_weekday_short = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    en_weekday_map = {w: i for i, w in enumerate(en_weekdays)}
    en_weekday_map.update({w: i for i, w in enumerate(en_weekday_short)})

    wd_en_regex = r"\b(next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b"
    wd_en_match = re.search(wd_en_regex, title.lower())
    if wd_en_match:
        prefix = wd_en_match.group(1)
        wd_str = wd_en_match.group(2)
        target_wd = en_weekday_map[wd_str]
        current_wd = now.weekday()
        days_ahead = target_wd - current_wd
        if prefix and "next" in prefix or days_ahead <= 0:
            days_ahead += 7
        target_date = (now + timedelta(days=days_ahead)).date()
        title = re.sub(wd_en_regex, "", title, flags=re.IGNORECASE).strip()
        date_found = True

    # Month/Day (MM/DD or MM월 DD일 or Month DD)
    md_match = re.search(r"(\d{1,2})[월/.]\s*(\d{1,2})일?", title)
    if md_match:
        m = int(md_match.group(1))
        d = int(md_match.group(2))
        try:
            candidate_date = datetime(now.year, m, d).date()
            if (
                candidate_date < now.date() and not date_found
            ):  # If date is passed, assume next year
                candidate_date = datetime(now.year + 1, m, d).date()
            target_date = candidate_date
            title = title.replace(md_match.group(0), "").strip()
            date_found = True
        except ValueError:
            pass

    # 2. Time extraction preserves invalid input for the user to correct.
    title, target_time = _extract_time(title)
    title = re.sub(r"\s+", " ", title).strip()
    # Only remove temporal connectors at the edges, never words inside a title.
    if date_found or target_time is not None:
        title = re.sub(
            r"^(?:at|on|in|to)\b|\b(?:at|on|in|to)$", "", title, flags=re.IGNORECASE
        ).strip()

    return {
        "title": title or "제목 없음",
        "date": target_date.isoformat(),
        "time": target_time,
    }
