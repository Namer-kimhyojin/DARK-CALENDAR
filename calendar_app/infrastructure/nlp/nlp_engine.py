from datetime import datetime, timedelta
import re


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
    title = text.strip()

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
    for kw, offset in rel_dates.items():
        if re.search(rf"\b{kw}\b", title.lower()):
            target_date = (now + timedelta(days=offset)).date()
            # Case-insensitive replacement
            title = re.sub(rf"\b{kw}\b", "", title, flags=re.IGNORECASE).strip()
            date_found = True
            break

    # Weekdays (KR)
    kr_weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    kr_weekday_map = {w: i for i, w in enumerate(kr_weekdays)}

    weekday_match = re.search(r"(이번주|다음주)?\s*([월화수목금토일])요일?", title)
    if weekday_match:
        prefix = weekday_match.group(1)
        wd_str = weekday_match.group(2)
        target_wd = kr_weekday_map[wd_str]
        current_wd = now.weekday()

        days_ahead = target_wd - current_wd
        if days_ahead <= 0:
            days_ahead += 7
        if prefix == "다음주":
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
        if days_ahead <= 0:
            days_ahead += 7
        if prefix and "next" in prefix:
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
            target_date = datetime(now.year, m, d).date()
            if target_date < now.date() and not date_found:  # If date is passed, assume next year
                target_date = datetime(now.year + 1, m, d).date()
            title = title.replace(md_match.group(0), "").strip()
            date_found = True
        except ValueError:
            pass

    # 2. Time Extraction
    # Support: 오전/오후, am/pm, HH:MM, HH시 MM분, HH시, 3pm, 4:30pm
    # KR patterns
    kr_time_match = re.search(r"(오전|오후|저녁|밤|아침|새벽)\s*(\d{1,2})[:시](\d{1,2})?분?", title)
    if kr_time_match:
        ampm = kr_time_match.group(1)
        h = int(kr_time_match.group(2))
        m = int(kr_time_match.group(3)) if kr_time_match.group(3) else 0
        if ampm in ["오후", "저녁", "밤"] and h < 12:
            h += 12
        elif ampm in ["오전", "아침", "새벽"] and h == 12:
            h = 0
        target_time = f"{h:02d}:{m:02d}"
        title = title.replace(kr_time_match.group(0), "").strip()

    # EN patterns (3pm, 4:30 PM, 15:00)
    en_time_match = re.search(r"\b(\d{1,2})(:(\d{2}))?\s*(am|pm)\b", title, flags=re.IGNORECASE)
    if en_time_match:
        h = int(en_time_match.group(1))
        m = int(en_time_match.group(3)) if en_time_match.group(3) else 0
        ampm = en_time_match.group(4).lower()
        if ampm == "pm" and h < 12:
            h += 12
        elif ampm == "am" and h == 12:
            h = 0
        target_time = f"{h:02d}:{m:02d}"
        title = re.sub(en_time_match.group(0), "", title, flags=re.IGNORECASE).strip()
    elif not target_time:
        # Simple HH:MM pattern
        simple_time = re.search(r"\b(\d{1,2}):(\d{2})\b", title)
        if simple_time:
            h = int(simple_time.group(1))
            m = int(simple_time.group(2))
            if 0 <= h < 24 and 0 <= m < 60:
                target_time = f"{h:02d}:{m:02d}"
                title = title.replace(simple_time.group(0), "").strip()

    # Clean up title: remove words like "at", "on" if they are at start/end of remaining title
    title = re.sub(r"\b(at|on|in|to)\b", "", title, flags=re.IGNORECASE).strip()
    title = re.sub(r"\s+", " ", title).strip()

    return {
        "title": title or "제목 없음",
        "date": target_date.isoformat(),
        "time": target_time,
    }
