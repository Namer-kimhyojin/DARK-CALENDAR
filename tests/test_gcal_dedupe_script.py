from scripts.gcal_dedupe import EventRow, _choose_keep_event, _group_duplicates


def _event(
    event_id: str,
    summary: str,
    start_value: str,
    end_value: str,
    *,
    location: str = "",
    description: str = "",
    created: str = "",
    updated: str = "",
    is_all_day: bool = False,
) -> EventRow:
    return EventRow(
        event_id=event_id,
        summary=summary,
        start_value=start_value,
        end_value=end_value,
        location=location,
        description=description,
        created=created,
        updated=updated,
        is_all_day=is_all_day,
    )


def test_group_duplicates_non_strict_groups_same_title_and_time():
    events = [
        _event(
            "a",
            "Team Sync",
            "2026-03-19T09:00:00+09:00",
            "2026-03-19T10:00:00+09:00",
            location="Room 1",
        ),
        _event(
            "b",
            "Team Sync",
            "2026-03-19T09:00:00+09:00",
            "2026-03-19T10:00:00+09:00",
            location="Room 2",
        ),
        _event("c", "Other", "2026-03-19T11:00:00+09:00", "2026-03-19T12:00:00+09:00"),
    ]

    groups = _group_duplicates(events, strict=False)

    assert len(groups) == 1
    group = next(iter(groups.values()))
    assert sorted(item.event_id for item in group) == ["a", "b"]


def test_group_duplicates_strict_keeps_location_distinct():
    events = [
        _event(
            "a",
            "Team Sync",
            "2026-03-19T09:00:00+09:00",
            "2026-03-19T10:00:00+09:00",
            location="Room 1",
        ),
        _event(
            "b",
            "Team Sync",
            "2026-03-19T09:00:00+09:00",
            "2026-03-19T10:00:00+09:00",
            location="Room 2",
        ),
    ]

    groups = _group_duplicates(events, strict=True)

    assert len(groups) == 0


def test_choose_keep_event_prefers_oldest_created_then_updated():
    events = [
        _event("b", "Meeting", "2026-03-19", "2026-03-20", created="2026-03-10T00:00:00Z"),
        _event("a", "Meeting", "2026-03-19", "2026-03-20", created="2026-03-09T00:00:00Z"),
    ]

    keep = _choose_keep_event(events)

    assert keep.event_id == "a"
