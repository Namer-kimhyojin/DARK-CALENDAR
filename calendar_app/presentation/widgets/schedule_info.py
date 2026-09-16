# -*- coding: utf-8 -*-
"""Shared schedule information rules for hover previews and pinned detail cards."""

from dataclasses import dataclass
import datetime as _datetime
import html as _html
import re as _re

from calendar_app.domain.task_constants import priority_icon
from calendar_app.infrastructure.i18n import t
from calendar_app.shared.color_utils import derive_ui_palette
from calendar_app.shared.search_utils import clean_calendar_description, clean_display_text
from calendar_app.shared.theme_settings import fpt, get_theme_palette_inputs

_PLACEHOLDER_VALUES = {"", "-", "none", "null"}
_ICON_TIME = "🕒"
_ICON_LOCATION = "📍"
_ICON_SOURCE = "📡"
_ICON_ASSIGNEE = "👤"
_ICON_DESCRIPTION = "📝"


@dataclass(frozen=True)
class ScheduleInfoRow:
    key: str
    label: str
    value: str


@dataclass(frozen=True)
class ScheduleInfo:
    title: str
    rows: tuple[ScheduleInfoRow, ...]

    @property
    def has_rows(self) -> bool:
        return bool(self.rows)

    @property
    def has_more_than_all_day(self) -> bool:
        """Whether a panel preview adds more than a single-day all-day marker."""
        return any(row.key != "all_day" for row in self.rows)


def _clean(value) -> str:
    text = clean_display_text(value)
    if text.strip().lower() in _PLACEHOLDER_VALUES:
        return ""
    return text.strip()


def _parse_date(raw_value) -> _datetime.date | None:
    raw = str(raw_value or "").strip()
    if len(raw) < 10:
        return None
    try:
        return _datetime.datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _parse_time(raw_value) -> str:
    raw = str(raw_value or "").strip()
    match = _re.search(r"(?:T|\s)(\d{2}:\d{2})(?::\d{2})?", raw)
    return match.group(1) if match else ""


def _is_all_day(task_row: dict) -> bool:
    if "all_day" in task_row and task_row.get("all_day") is not None:
        return bool(task_row.get("all_day"))
    start_raw = str(task_row.get("deadline") or task_row.get("_start_raw") or "").strip()
    end_raw = str(task_row.get("end_date") or task_row.get("_end_raw") or "").strip()
    return bool(start_raw and "T" not in start_raw and " " not in start_raw) or bool(
        start_raw
        and end_raw
        and _parse_time(start_raw) == "00:00"
        and _parse_time(end_raw) == "00:00"
    )


def _date_text(value: _datetime.date | None) -> str:
    return value.strftime("%Y.%m.%d") if value else ""


def _when_row(task_row: dict, context: str) -> ScheduleInfoRow | None:
    start_raw = task_row.get("deadline") or task_row.get("_start_raw")
    end_raw = task_row.get("end_date") or task_row.get("_end_raw")
    start_date = _parse_date(start_raw)
    end_date = _parse_date(end_raw) or start_date
    all_day = _is_all_day(task_row)
    is_multiday = bool(start_date and end_date and start_date < end_date)

    if is_multiday:
        value = f"{_date_text(start_date)} ~ {_date_text(end_date)}"
        if all_day:
            value += f" · {t('tooltip.all_day', '종일')}"
        return ScheduleInfoRow(
            "period",
            f"{_ICON_TIME} {t('tooltip.label_period', '기간')}",
            value,
        )

    start_time = _parse_time(start_raw)
    end_time = _parse_time(end_raw)
    if all_day:
        value = t("tooltip.all_day", "종일")
        key = "all_day"
    elif start_time and end_time and start_time != end_time:
        value = f"{start_time} - {end_time}"
        key = "time"
    else:
        value = start_time or end_time
        key = "time"

    if context in {"week", "detail"} and start_date:
        date_value = _date_text(start_date)
        value = f"{date_value} · {value}" if value else date_value
    if not value:
        return None
    return ScheduleInfoRow(key, f"{_ICON_TIME} {t('tooltip.label_time', '시간')}", value)


def _description_text(task_row: dict, *, limit: int | None) -> str:
    description = clean_calendar_description(
        task_row.get("memo") or task_row.get("description"),
        source_calendar_id=task_row.get("gcal_source_calendar_id")
        or task_row.get("_subscription_calendar_id"),
        sync_mode=task_row.get("gcal_sync_mode"),
    )
    description = _clean(description)
    if not description:
        return ""
    if limit:
        description = " ".join(description.split())
        if len(description) > limit:
            return description[: max(1, limit - 1)].rstrip() + "…"
    return description


def build_schedule_info(
    task_row: dict,
    *,
    context: str = "calendar",
    source_text: str = "",
    detail: bool = False,
) -> ScheduleInfo:
    """Build a semantic schedule summary shared by every information surface."""
    title = _clean(task_row.get("name")) or t("common.no_title", "제목 없음")
    icon = priority_icon(task_row.get("priority")) if task_row.get("priority") else ""
    display_title = f"{icon} {title}".strip()

    rows: list[ScheduleInfoRow] = []
    when_row = _when_row(task_row, "detail" if detail else context)
    if when_row:
        rows.append(when_row)

    location = _clean(task_row.get("location"))
    if location:
        rows.append(
            ScheduleInfoRow(
                "location",
                f"{_ICON_LOCATION} {t('tooltip.label_location', '장소')}",
                location,
            )
        )

    source = _clean(source_text)
    if source:
        rows.append(
            ScheduleInfoRow(
                "source",
                f"{_ICON_SOURCE} {t('tooltip.label_calendar', '캘린더')}",
                source,
            )
        )

    if detail:
        assignee = _clean(task_row.get("assignee"))
        if assignee:
            rows.append(
                ScheduleInfoRow(
                    "assignee",
                    f"{_ICON_ASSIGNEE} {t('tooltip.label_assignee', '담당')}",
                    assignee,
                )
            )

    description = _description_text(task_row, limit=None if detail else 90)
    redundant_values = {title.casefold(), source.casefold()}
    if description and description.casefold() not in redundant_values:
        rows.append(
            ScheduleInfoRow(
                "description",
                f"{_ICON_DESCRIPTION} {t('tooltip.label_description', '설명')}",
                description,
            )
        )

    return ScheduleInfo(display_title, tuple(rows))


def build_schedule_hover_html(
    task_row: dict,
    theme_color: str,
    *,
    context: str = "calendar",
    source_text: str = "",
) -> tuple[str, ScheduleInfo]:
    info = build_schedule_info(
        task_row,
        context=context,
        source_text=source_text,
        detail=False,
    )
    text_theme, panel_base, opacity_factor = get_theme_palette_inputs()
    palette = derive_ui_palette(text_theme, panel_base, opacity_factor)

    title_html = _html.escape(info.title)
    html_rows = []
    for row in info.rows:
        html_rows.append(
            "<tr>"
            f"<td style='width:74px; min-width:74px; padding:0 8px 3px 0; vertical-align:top; color:{palette['text_secondary']}; white-space:nowrap;'>"
            f"{_html.escape(row.label)}</td>"
            f"<td style='padding:0 0 3px 0; vertical-align:top; color:{palette['text_primary']};'>"
            f"{_html.escape(row.value)}</td>"
            "</tr>"
        )
    rows_html = ""
    if html_rows:
        rows_html = (
            "<table cellspacing='0' cellpadding='0' style='margin-top:5px; border-collapse:collapse;'>"
            + "".join(html_rows)
            + "</table>"
        )
    html = (
        f"<div style='text-align:left; color:{palette['text_primary']};'>"
        f"<div style='font-size:{fpt()}; margin-bottom:1px;'><b style='color:{theme_color};'>{title_html}</b></div>"
        f"{rows_html}</div>"
    )
    return html, info
