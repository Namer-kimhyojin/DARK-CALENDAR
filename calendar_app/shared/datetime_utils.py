from datetime import datetime, timedelta
from functools import lru_cache
import re
from zoneinfo import ZoneInfo

_FIXED_TZ_OFFSETS = {
    "UTC": "+00:00",
    "Etc/UTC": "+00:00",
    "Asia/Seoul": "+09:00",
    "Asia/Tokyo": "+09:00",
}

_US_DST_ZONES = {
    "America/New_York": ("-05:00", "-04:00"),
    "America/Detroit": ("-05:00", "-04:00"),
    "America/Chicago": ("-06:00", "-05:00"),
    "America/Denver": ("-07:00", "-06:00"),
    "America/Los_Angeles": ("-08:00", "-07:00"),
}

_EU_DST_ZONES = {
    "Europe/London": ("+00:00", "+01:00"),
    "Europe/Berlin": ("+01:00", "+02:00"),
    "Europe/Paris": ("+01:00", "+02:00"),
    "Europe/Madrid": ("+01:00", "+02:00"),
    "Europe/Rome": ("+01:00", "+02:00"),
}


def _nth_weekday_of_month(year: int, month: int, weekday: int, occurrence: int) -> datetime:
    first = datetime(year, month, 1)
    days_until = (weekday - first.weekday()) % 7
    day = 1 + days_until + (occurrence - 1) * 7
    return datetime(year, month, day)


def _last_weekday_of_month(year: int, month: int, weekday: int) -> datetime:
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)
    last = next_month - timedelta(days=1)
    days_back = (last.weekday() - weekday) % 7
    return datetime(last.year, last.month, last.day) - timedelta(days=days_back)


def _fallback_timezone_offset(tz_name: str, when: datetime) -> str | None:
    if tz_name in _FIXED_TZ_OFFSETS:
        return _FIXED_TZ_OFFSETS[tz_name]
    if tz_name in _US_DST_ZONES:
        standard, daylight = _US_DST_ZONES[tz_name]
        year = when.year
        dst_start = _nth_weekday_of_month(year, 3, 6, 2).replace(hour=2)
        dst_end = _nth_weekday_of_month(year, 11, 6, 1).replace(hour=2)
        return daylight if dst_start <= when < dst_end else standard
    if tz_name in _EU_DST_ZONES:
        standard, daylight = _EU_DST_ZONES[tz_name]
        year = when.year
        dst_start = _last_weekday_of_month(year, 3, 6).replace(hour=1)
        dst_end = _last_weekday_of_month(year, 10, 6).replace(hour=2)
        return daylight if dst_start <= when < dst_end else standard
    return None


@lru_cache(maxsize=256)
def _extract_tz_offset(dt_str: str) -> str | None:
    s = dt_str.strip()
    if s.endswith("Z"):
        return "+00:00"
    m = re.search(r"([+-]\d{2}:\d{2})$", s)
    return m.group(1) if m else None


def _strip_tz(dt_str: str) -> str:
    s = dt_str.strip()
    if s.endswith("Z"):
        s = s[:-1]
    # remove trailing timezone offset like +09:00 or -04:00
    s = re.sub(r"([+-]\d{2}:\d{2})$", "", s)
    return s


def timezone_offset_for_name(tz_name: str, when: datetime | None = None) -> str:
    reference = when or datetime.now()
    try:
        zone = ZoneInfo(tz_name)
        if reference.tzinfo is None:
            dt = datetime(
                reference.year,
                reference.month,
                reference.day,
                reference.hour,
                reference.minute,
                reference.second,
                reference.microsecond,
                tzinfo=zone,
            )
        else:
            dt = reference.astimezone(zone)
    except Exception:
        return _fallback_timezone_offset(tz_name, reference) or "+09:00"
    offset = dt.utcoffset() or timedelta(0)
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    hours, minutes = divmod(total_minutes, 60)
    return f"{sign}{hours:02d}:{minutes:02d}"


def timezone_offset_for_datetime_str(dt_str: str, tz_name: str, fallback: str = "+09:00") -> str:
    if not dt_str:
        return fallback
    clean_s = _strip_tz(dt_str).replace("T", " ")
    parsed = None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            if fmt == "%Y-%m-%d":
                parsed = datetime.strptime(clean_s[:10], fmt)
            elif fmt == "%Y-%m-%d %H:%M":
                parsed = datetime.strptime(clean_s[:16], fmt)
            else:
                parsed = datetime.strptime(clean_s[:19], fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        return fallback
    return timezone_offset_for_name(tz_name, when=parsed)


@lru_cache(maxsize=512)
def parse_datetime_str(dt_str: str, target_tz_offset: str = "+09:00") -> datetime | None:
    if not dt_str:
        return None

    # ISO-8601 parsing with timezone awareness (simple version)
    s = dt_str.strip()
    is_utc = s.endswith("Z")
    offset = _extract_tz_offset(s)

    clean_s = _strip_tz(s).replace("T", " ")

    base_dt = None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            # We only need the first part
            if fmt == "%Y-%m-%d":
                base_dt = datetime.strptime(clean_s[:10], fmt)
            elif fmt == "%Y-%m-%d %H:%M":
                base_dt = datetime.strptime(clean_s[:16], fmt)
            else:
                base_dt = datetime.strptime(clean_s[:19], fmt)
            break
        except ValueError:
            continue

    if not base_dt:
        return None

    # Timezone conversion if needed (target: target_tz_offset)
    target_h = int(target_tz_offset[1:3])
    target_m = int(target_tz_offset[4:6])
    target_sign = 1 if target_tz_offset[0] == "+" else -1
    target_total_mins = target_sign * (target_h * 60 + target_m)
    if is_utc:
        base_dt += timedelta(minutes=target_total_mins)
    elif offset and offset != target_tz_offset:
        try:
            h = int(offset[1:3])
            m = int(offset[4:6])
            sign = 1 if offset[0] == "+" else -1
            total_offset_mins = sign * (h * 60 + m)
            diff_mins = target_total_mins - total_offset_mins
            base_dt += timedelta(minutes=diff_mins)
        except Exception:
            pass

    return base_dt


def to_iso_with_tz(dt_str: str, tz_offset: str = "+09:00") -> str | None:
    tz_from_input = _extract_tz_offset(dt_str)
    if tz_from_input:
        tz_offset = tz_from_input
    dt = parse_datetime_str(dt_str, target_tz_offset=tz_offset)
    if not dt:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + tz_offset


def end_iso_from(
    start_str: str, end_str: str | None = None, tz_offset: str = "+09:00", default_hours: int = 1
) -> str | None:
    start_dt = parse_datetime_str(start_str, target_tz_offset=tz_offset)
    if end_str:
        end_dt = parse_datetime_str(end_str, target_tz_offset=tz_offset)
        if start_dt and end_dt and end_dt > start_dt:
            return end_dt.strftime("%Y-%m-%dT%H:%M:%S") + tz_offset
    dt = start_dt
    if not dt:
        return None
    return (dt + timedelta(hours=default_hours)).strftime("%Y-%m-%dT%H:%M:%S") + tz_offset
