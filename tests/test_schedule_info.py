# -*- coding: utf-8 -*-

from calendar_app.presentation.widgets.schedule_info import (
    build_schedule_hover_html,
    build_schedule_info,
)


def _row(info, key):
    return next(row for row in info.rows if row.key == key)


def test_multiday_all_day_uses_period_instead_of_midnight_range():
    info = build_schedule_info(
        {
            "name": "교육과정 홍보",
            "deadline": "2026-09-15 00:00:00",
            "end_date": "2026-10-05 00:00:00",
            "all_day": True,
        }
    )

    period = _row(info, "period").value
    assert "2026.09.15" in period
    assert "2026.10.05" in period
    assert "00:00" not in period


def test_single_all_day_without_other_details_can_skip_panel_preview():
    info = build_schedule_info(
        {
            "name": "추석",
            "deadline": "2026-09-25 00:00:00",
            "end_date": "2026-09-25 00:00:00",
            "all_day": True,
        },
        context="today",
    )

    assert [row.key for row in info.rows] == ["all_day"]
    assert not info.has_more_than_all_day
    assert "00:00" not in info.rows[0].value


def test_week_preview_adds_date_and_suppresses_repeated_description():
    info = build_schedule_info(
        {
            "name": "회의",
            "deadline": "2026-09-16 14:00:00",
            "end_date": "2026-09-16 15:00:00",
            "description": "회의",
            "location": "회의실 A",
        },
        context="week",
    )

    assert _row(info, "time").value == "2026.09.16 · 14:00 - 15:00"
    assert _row(info, "location").value == "회의실 A"
    assert not any(row.key == "description" for row in info.rows)


def test_detail_contains_full_date_source_assignee_and_full_description():
    description = "상세 설명 " * 30
    info = build_schedule_info(
        {
            "name": "프로젝트 점검",
            "deadline": "2026-09-16 14:00:00",
            "end_date": "2026-09-16 15:00:00",
            "assignee": "김담당",
            "description": description,
        },
        source_text="업무 캘린더",
        detail=True,
    )

    assert _row(info, "time").value == "2026.09.16 · 14:00 - 15:00"
    assert _row(info, "source").value == "업무 캘린더"
    assert _row(info, "assignee").value == "김담당"
    assert _row(info, "description").value == description.strip()


def test_hover_html_escapes_user_content():
    html, info = build_schedule_hover_html(
        {
            "name": "<b>일정</b>",
            "deadline": "2026-09-16 09:00:00",
            "end_date": "2026-09-16 10:00:00",
            "location": "A & B",
        },
        "#44aaff",
    )

    assert info.has_rows
    assert "&lt;b&gt;일정&lt;/b&gt;" in html
    assert "A &amp; B" in html
    assert "<b>일정</b>" not in html
