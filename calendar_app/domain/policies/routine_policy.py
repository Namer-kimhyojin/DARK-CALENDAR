"""

Domain policy for routine recurrence calculation.

This module is pure logic and should not have any I/O dependencies.

"""

import calendar
from datetime import datetime, timedelta


def parse_recurrence_rule(recurrence):
    parsed = {}

    if not recurrence:
        return parsed

    for chunk in recurrence.split(";"):
        if "=" not in chunk:
            continue

        key, value = chunk.split("=", 1)

        parsed[key] = value

    return parsed


def get_next_occurrence(current_date, cycle_type, recurrence_rule):
    """

    Calculate the next occurrence date based on the current date, cycle type, and recurrence rule.

    """

    if isinstance(current_date, str):
        target_date = datetime.strptime(current_date[:10], "%Y-%m-%d")

    else:
        target_date = current_date

    if cycle_type in (None, "", "single"):
        return None

    if cycle_type == "daily":
        return (target_date + timedelta(days=1)).strftime("%Y-%m-%d")

    if cycle_type == "weekly":
        weekday = int(recurrence_rule.get("weekday", target_date.weekday()))

        day_delta = (weekday - target_date.weekday()) % 7

        if day_delta == 0:
            day_delta = 7

        return (target_date + timedelta(days=day_delta)).strftime("%Y-%m-%d")

    # For monthly, quarterly, half_yearly, yearly

    cycle_start = _get_cycle_start(target_date, cycle_type)

    next_date = _calculate_occurrence_in_cycle(
        cycle_start, cycle_type, recurrence_rule, target_date
    )

    if next_date is None or next_date <= target_date:
        cycle_start = _advance_cycle_start(cycle_start, cycle_type)

        next_date = _calculate_occurrence_in_cycle(
            cycle_start, cycle_type, recurrence_rule, target_date
        )

    return next_date.strftime("%Y-%m-%d") if next_date else None


def _get_cycle_start(target_date, cycle_type):
    if cycle_type == "monthly":
        return target_date.replace(day=1)

    if cycle_type == "quarterly":
        quarter = (target_date.month - 1) // 3

        return target_date.replace(month=quarter * 3 + 1, day=1)

    if cycle_type == "half_yearly":
        return target_date.replace(month=1 if target_date.month <= 6 else 7, day=1)

    if cycle_type == "yearly":
        return target_date.replace(month=1, day=1)

    return target_date


def _advance_cycle_start(cycle_start, cycle_type):
    if cycle_type == "monthly":
        return _add_months(cycle_start, 1)

    if cycle_type == "quarterly":
        return _add_months(cycle_start, 3)

    if cycle_type == "half_yearly":
        return _add_months(cycle_start, 6)

    if cycle_type == "yearly":
        return _add_months(cycle_start, 12)

    return cycle_start


def _add_months(source_date, months):
    month_index = source_date.month - 1 + months

    year = source_date.year + month_index // 12

    month = month_index % 12 + 1

    last_day = calendar.monthrange(year, month)[1]

    return source_date.replace(year=year, month=month, day=min(source_date.day, last_day))


def _calculate_occurrence_in_cycle(cycle_start, cycle_type, recurrence_rule, fallback_date):
    slot = int(recurrence_rule.get("slot", _get_default_slot(fallback_date, cycle_type)))

    year, month = _get_target_month(cycle_start, cycle_type, slot)

    mode = recurrence_rule.get("mode", "day_of_month")

    if mode == "nth_weekday":
        weekday = int(recurrence_rule.get("weekday", fallback_date.weekday()))

        nth = recurrence_rule.get("nth", 1)

        return _get_nth_weekday_of_month(year, month, weekday, nth)

    day = recurrence_rule.get("day", fallback_date.day)

    if day == "last":
        day = calendar.monthrange(year, month)[1]

    else:
        day = min(int(day), calendar.monthrange(year, month)[1])

    return datetime(year, month, day)


def _get_default_slot(date, cycle_type):
    if cycle_type == "quarterly":
        return (date.month - 1) % 3 + 1

    if cycle_type == "half_yearly":
        return (date.month - 1) % 6 + 1

    if cycle_type == "yearly":
        return date.month

    return 1


def _get_target_month(cycle_start, cycle_type, slot):
    if cycle_type == "monthly":
        return cycle_start.year, cycle_start.month

    offset = slot - 1

    target = _add_months(cycle_start, offset)

    return target.year, target.month


def _get_nth_weekday_of_month(year, month, weekday, nth):
    month_calendar = calendar.monthcalendar(year, month)

    days = [week[weekday] for week in month_calendar if week[weekday] != 0]

    if not days:
        return None

    if nth == "last":
        idx = -1

    else:
        idx = min(int(nth), len(days)) - 1

    return datetime(year, month, days[idx])
