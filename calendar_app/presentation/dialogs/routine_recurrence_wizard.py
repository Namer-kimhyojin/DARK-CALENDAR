# -*- coding: utf-8 -*-

from calendar_app.domain.policies.routine_policy import parse_recurrence_rule
from calendar_app.domain.routine_cycle import cycle_display_name
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.locale_names import weekday_names


def get_cycle_labels():
    return {
        key: cycle_display_name(key, scope="recurrence")
        for key in ("weekly", "monthly", "quarterly", "half_yearly", "yearly")
    }


def get_weekday_names():
    """Monday-first short weekday names from Qt's locale data."""
    return weekday_names()


def _ordinal_name(number):
    if number == "last":
        return t("recurrence.last_week")
    return t(f"recurrence.ordinal_{number}")


def default_recurrence_config(target_date, cycle_type="monthly"):
    config = {
        "mode": "day_of_month",
        "slot": 1,
        "day": "last" if target_date.day() == target_date.daysInMonth() else target_date.day(),
        "nth": ((target_date.day() - 1) // 7) + 1,
        "weekday": target_date.dayOfWeek() - 1,
    }
    if cycle_type == "quarterly":
        config["slot"] = ((target_date.month() - 1) % 3) + 1
    elif cycle_type == "half_yearly":
        config["slot"] = ((target_date.month() - 1) % 6) + 1
    elif cycle_type == "yearly":
        config["slot"] = target_date.month()
    return config


def normalize_recurrence_config(target_date, cycle_type, recurrence):
    config = default_recurrence_config(target_date, cycle_type)
    parsed = parse_recurrence_rule(recurrence)
    if not parsed:
        return config
    config["mode"] = parsed.get("mode", config["mode"])
    if "slot" in parsed:
        config["slot"] = int(parsed["slot"])
    if "day" in parsed:
        config["day"] = int(parsed["day"]) if parsed["day"] != "last" else "last"
    if "nth" in parsed:
        config["nth"] = int(parsed["nth"]) if parsed["nth"] != "last" else "last"
    if "weekday" in parsed:
        config["weekday"] = int(parsed["weekday"])
    if cycle_type == "weekly":
        config["mode"] = "weekly"
    return config


def build_recurrence_rule(cycle_type, config):
    if cycle_type == "single":
        return "mode=single"
    if cycle_type == "weekly":
        return f"mode=weekly;weekday={config['weekday']}"
    if config["mode"] == "nth_weekday":
        return f"mode=nth_weekday;slot={config['slot']};nth={config['nth']};weekday={config['weekday']}"
    return f"mode=day_of_month;slot={config['slot']};day={config['day']}"


def cycle_slot_options(cycle_type):
    if cycle_type == "quarterly":
        return [
            (t("recurrence.quarter_1"), 1),
            (t("recurrence.quarter_2"), 2),
            (t("recurrence.quarter_3"), 3),
        ]
    if cycle_type == "half_yearly":
        return [(t("recurrence.suffix_day", n=i), i) for i in range(1, 7)]
    if cycle_type == "yearly":
        return [(t("recurrence.suffix_day", n=month), month) for month in range(1, 13)]
    return []


def month_day_options():
    """(label, value) pairs for the day-of-month combo: days 1-31, then the last day."""
    options = [
        (t("dialog.recurrence.day_of_month", "{day}일", day=day), day) for day in range(1, 32)
    ]
    options.append((t("dialog.recurrence.last_day"), "last"))
    return options


def recurrence_summary(target_date, cycle_type, recurrence):
    if cycle_type == "single":
        return t("recurrence.summary_single", date=target_date.toString("yyyy-MM-dd"))
    config = normalize_recurrence_config(target_date, cycle_type, recurrence)
    cycle_name = get_cycle_labels().get(cycle_type, cycle_type)
    wd_names = get_weekday_names()
    if cycle_type == "weekly":
        return t("recurrence.summary_weekly", cycle=cycle_name, weekday=wd_names[config["weekday"]])

    slot_map = dict(cycle_slot_options(cycle_type))
    slot_text = slot_map.get(config["slot"], "")
    slot_prefix = f"{slot_text} · " if slot_text else ""

    if config["mode"] == "nth_weekday":
        nth = _ordinal_name(config["nth"])
        return t(
            "recurrence.summary_nth",
            cycle=cycle_name,
            slot=slot_prefix,
            nth=nth,
            weekday=wd_names[config["weekday"]],
        )

    day_text = (
        t("recurrence.last_day")
        if config["day"] == "last"
        else t("dialog.recurrence.day_of_month", "{day}일", day=config["day"])
    )
    return t("recurrence.summary_day", cycle=cycle_name, slot=slot_prefix, day=day_text)
