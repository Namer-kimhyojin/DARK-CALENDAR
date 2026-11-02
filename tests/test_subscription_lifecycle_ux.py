# -*- coding: utf-8 -*-
"""Regression journeys for subscription archives, resuming and recovery feedback."""

from io import BytesIO
import json
from pathlib import Path
import sqlite3
from string import Formatter
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from calendar_app.domain.calendar_visibility import CalendarVisibility
from calendar_app.infrastructure.db import calendar_repo, database_unified
from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.ics import ics_fetcher
from calendar_app.presentation.dialogs import calendar_manager_page as manager
from calendar_app.presentation.dialogs.calendar_sync_hub import CalendarSyncHub
from calendar_app.presentation.dialogs.sync_recovery import sync_recovery_action
from tests.test_calendar_sync_redesign import sync_ui  # noqa: F401

URL = "https://example.invalid/subscription.ics?token=synthetic"
KEY = calendar_repo.make_ics_id(URL)
PAYLOAD = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:synthetic\r\n"
    "DTSTART:20261104T100000Z\r\nSUMMARY:Meeting\r\nDESCRIPTION:Keep my notes\r\n"
    "END:VEVENT\r\nEND:VCALENDAR\r\n"
).encode("utf-8", errors="strict")


@pytest.fixture
def subscription_db(tmp_path, monkeypatch):
    database_unified.db_manager.close_all_connections()
    monkeypatch.setattr(database_unified, "DB_PATH", str(tmp_path / "calendar.db"))
    database_unified.initialize_unified_database()
    conn = database_unified.db_manager.get_connection()
    monkeypatch.setattr(ics_fetcher, "open_subscription", lambda *a, **k: BytesIO(PAYLOAD))
    assert calendar_repo.upsert_calendar(KEY, "ics", "Team", color="#123456", ics_url=URL)
    assert ics_fetcher.fetch_and_sync(KEY, URL, "Asia/Seoul")[2] is None
    yield conn
    database_unified.db_manager.close_all_connections()


def tasks(conn):
    cursor = conn.execute("SELECT * FROM unified_task ORDER BY id")
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def test_unsubscribe_rejoin_preserves_editable_archive_without_visible_duplicates(subscription_db):
    conn = subscription_db
    before = tasks(conn)[0]
    assert calendar_repo.archive_ics_subscription(KEY, "Team · Archive")
    assert calendar_repo.get_calendar(KEY) is None
    archived = tasks(conn)[0]
    archive = calendar_repo.get_calendar(archived["calendar_id"])
    assert archive["type"] == "local" and not archive["is_visible"]
    assert archive["name"] == "Team · Archive" and archive["color"] == "#123456"
    assert not archive["ics_url"] and not archive["gcal_calendar_id"] and not archive["is_default"]
    assert not calendar_repo.is_calendar_row_read_only(archive)
    assert archived["id"] == before["id"] and archived["description"] == before["description"]
    assert archived["gcal_sync_mode"] == "local_owned" and archived["gcal_dirty"] == 0
    for field in ("gcal_event_id", "gcal_source_calendar_id", "gcal_target_calendar_id"):
        assert archived[field] is None
    assert conn.execute("SELECT COUNT(*) FROM gcal_delete_queue").fetchone()[0] == 0
    conn.execute(
        "UPDATE unified_task SET description='Edited archive' WHERE id=?", (archived["id"],)
    )
    conn.commit()
    assert calendar_repo.upsert_calendar(KEY, "ics", "Team", ics_url=URL)
    assert ics_fetcher.fetch_and_sync(KEY, URL, "Asia/Seoul")[2] is None
    rows = tasks(conn)
    assert len(rows) == 2 and rows[0]["description"] == "Edited archive"
    policy = CalendarVisibility(calendar_repo.list_calendars())
    assert [row["id"] for row in rows if policy.is_visible(row)] == [rows[1]["id"]]
    assert calendar_repo.set_calendar_visible(archive["id"], True)
    assert all(CalendarVisibility(calendar_repo.list_calendars()).is_visible(row) for row in rows)


@pytest.mark.parametrize("stage", ["insert", "move", "delete"])
def test_archive_failure_rolls_back_every_step_and_preserves_outer_transaction(
    subscription_db, stage
):
    conn = subscription_db
    before = tasks(conn)
    trigger = {
        "insert": "BEFORE INSERT ON calendar WHEN NEW.type='local'",
        "move": "BEFORE UPDATE OF calendar_id ON unified_task",
        "delete": "BEFORE DELETE ON calendar",
    }[stage]
    conn.execute(
        f"CREATE TRIGGER fail_archive {trigger} BEGIN SELECT RAISE(ABORT,'synthetic'); END"
    )
    conn.execute("UPDATE calendar SET name='Uncommitted user change' WHERE id=?", (KEY,))
    with pytest.raises(sqlite3.IntegrityError):
        calendar_repo.archive_ics_subscription(KEY, "Archive")
    assert conn.in_transaction
    assert calendar_repo.get_calendar(KEY)["name"] == "Uncommitted user change"
    assert tasks(conn) == before
    assert not [
        c for c in calendar_repo.list_calendars() if c["id"].startswith("local::ics_archive::")
    ]
    conn.rollback()
    assert calendar_repo.get_calendar(KEY)["name"] == "Team"


def test_successful_archive_does_not_commit_callers_transaction(subscription_db):
    conn = subscription_db
    conn.execute("UPDATE calendar SET name='Uncommitted' WHERE id=?", (KEY,))
    assert calendar_repo.archive_ics_subscription(KEY, "Archive") and conn.in_transaction
    conn.rollback()
    assert calendar_repo.get_calendar(KEY)["name"] == "Team"
    assert tasks(conn)[0]["calendar_id"] == KEY


def test_empty_missing_and_other_calendar_unsubscribe(subscription_db):
    conn = subscription_db
    calendar_repo.upsert_calendar("ics::empty", "ics", "Empty", ics_url=URL + "2")
    assert calendar_repo.archive_ics_subscription("ics::empty", "Empty archive")
    assert not [c for c in calendar_repo.list_calendars() if c["name"] == "Empty archive"]
    calendar_repo.upsert_calendar("local::keep", "local", "Keep")
    assert not calendar_repo.archive_ics_subscription("local::keep", "Do not move")
    assert not calendar_repo.archive_ics_subscription("ics::missing", "Do not create")
    assert calendar_repo.get_calendar("local::keep") is not None
    assert len(tasks(conn)) == 1


def test_legacy_delete_entry_point_also_preserves_hidden_subscription_archive(subscription_db):
    assert calendar_repo.delete_calendar(KEY)
    row = tasks(subscription_db)[0]
    archive = calendar_repo.get_calendar(row["calendar_id"])
    assert archive["type"] == "local" and not archive["is_visible"]
    assert row["gcal_sync_mode"] == "local_owned"


def test_legacy_unsubscribe_failure_keeps_callers_pending_changes(subscription_db):
    conn = subscription_db
    conn.execute(
        "CREATE TRIGGER fail_archive BEFORE DELETE ON calendar "
        "BEGIN SELECT RAISE(ABORT,'synthetic'); END"
    )
    conn.execute("UPDATE calendar SET name='Pending edit' WHERE id=?", (KEY,))
    assert not calendar_repo.delete_calendar(KEY)
    assert conn.in_transaction and calendar_repo.get_calendar(KEY)["name"] == "Pending edit"
    assert tasks(conn)[0]["calendar_id"] == KEY
    conn.rollback()


def test_fetch_finishing_after_unsubscribe_cannot_overwrite_archive(subscription_db, monkeypatch):
    def response(*args, **kwargs):
        assert calendar_repo.archive_ics_subscription(KEY, "Archive")
        return BytesIO(PAYLOAD.replace(b"Meeting", b"Stale replacement"))

    monkeypatch.setattr(ics_fetcher, "open_subscription", response)
    result = ics_fetcher.fetch_and_sync(KEY, URL, "Asia/Seoul")
    assert result[2] is not None
    assert tasks(subscription_db)[0]["name"] == "Meeting"
    assert tasks(subscription_db)[0]["gcal_sync_mode"] == "local_owned"


@pytest.mark.parametrize(
    "active,checked,saved,expected",
    [
        (False, True, True, 1),
        (False, True, False, 0),
        (True, False, True, 0),
        (True, True, True, 0),
    ],
)
def test_resume_fetches_only_on_successful_transition_even_with_auto_off(
    sync_ui, monkeypatch, active, checked, saved, expected
):
    sync_ui.add_calendar("ics::paused", active=active)
    sync_ui.host.settings.setValue("sync_ics_auto", False)
    sync_ui.coordinator.refresh()
    page = manager.CalendarManagerPage(sync_ui.host, sync_ui.coordinator, Mock(), scope="ics")
    monkeypatch.setattr(calendar_repo, "set_calendar_active", Mock(return_value=saved))
    refresh = Mock(return_value=True)
    monkeypatch.setattr(sync_ui.coordinator, "sync_ics", refresh)
    page._subscription_active(checked)
    assert refresh.call_count == expected
    if expected:
        refresh.assert_called_once_with(force=True, calendar_ids=["ics::paused"])
    page.close()


@pytest.mark.parametrize("outcome", ["success", "failure", "no_progress"])
def test_address_edit_replaces_old_banner_with_target_result_not_unrelated_failure(
    sync_ui, monkeypatch, outcome
):
    sync_ui.add_calendar("ics::target")
    sync_ui.add_calendar("ics::other")
    errors = {"ics::target": "ics_access_denied", "ics::other": "network_unavailable"}
    sync_ui.host.settings.setValue("sync_ics_error_codes", errors)
    sync_ui.coordinator.refresh()
    hub = CalendarSyncHub(sync_ui.host, section="ics")
    hub.ics_manager.select_calendar("ics::target")
    hub.sync_feedback.setText("OLD FAILURE")

    def start(**kwargs):
        sync_ui.coordinator.ics_worker = SimpleNamespace(is_cancelled=lambda: False)
        sync_ui.coordinator.refresh()
        return True

    start_mock = Mock(side_effect=start)
    monkeypatch.setattr(sync_ui.coordinator, "sync_ics", start_mock)
    with sqlite3.connect(sync_ui.path) as conn:
        monkeypatch.setattr(database_unified.db_manager, "get_connection", lambda: conn)
        assert hub.ics_manager._save_subscription(
            hub.ics_manager.current(), "Target", "https://example.invalid/fixed.ics"
        )
        assert hub.sync_feedback.text() != "OLD FAILURE"
        start_mock.assert_called_once_with(force=True, calendar_ids=["ics::target"])
        if outcome == "success":
            conn.execute(
                "UPDATE calendar SET ics_last_fetched='2026-11-02T01:00:00+00:00' WHERE id='ics::target'"
            )
            conn.commit()
        if outcome != "failure":
            errors.pop("ics::target")
        sync_ui.host.settings.setValue("sync_ics_error_codes", errors)
        sync_ui.coordinator.ics_worker = None
        sync_ui.coordinator.refresh()
        expected = {
            "success": "sync_subscription.refresh_finished",
            "failure": "sync_recovery.finished_issues",
            "no_progress": "sync_recovery.finished_unconfirmed",
        }[outcome]
        assert hub.sync_feedback.text() == t(expected)
        assert sync_ui.coordinator.states["ics"]["issues"] >= 1  # Other feed still failed.
    hub.close()


def test_archive_ui_uses_safe_route_and_explains_where_to_find_events(sync_ui, monkeypatch):
    sync_ui.add_calendar("ics::archive")
    hub = CalendarSyncHub(sync_ui.host, section="ics")
    archive = Mock(return_value=True)
    remove = Mock()
    confirm = Mock(return_value=manager.QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(calendar_repo, "archive_ics_subscription", archive)
    monkeypatch.setattr(calendar_repo, "delete_calendar", remove)
    monkeypatch.setattr(manager.QMessageBox, "question", confirm)
    hub.ics_manager._remove()
    archive.assert_called_once_with(
        "ics::archive", t("sync_subscription.archive_name", name="ics::archive")
    )
    remove.assert_not_called()
    assert confirm.call_args.args[-1] == manager.QMessageBox.StandardButton.No
    assert hub.ics_manager.feedback.text() == t("sync_subscription.archived_notice")
    hub.close()


def test_ics_recovery_uses_subscription_guidance_not_held_writes():
    state = {"connected": True, "can_sync": True, "issues": 1}
    action = sync_recovery_action("ics", state)
    assert action["hint"] == t("sync_subscription.review_hint")
    assert action["can_retry"] and action["section"] == "calendars"
    assert sync_recovery_action("google", state)["hint"] == t("sync_recovery.review_hint")


def test_all_locale_bundles_supply_subscription_copy_and_matching_parameters():
    paths = list((Path(__file__).resolve().parents[1] / "locales").glob("*.json"))
    assert len(paths) == 19
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8", errors="strict"))
        for key in (
            "archive_name",
            "unsubscribe_confirm",
            "archived_notice",
            "refresh_finished",
            "review_hint",
        ):
            value = data["sync_subscription"][key]
            fields = {field for _, field, _, _ in Formatter().parse(value) if field}
            assert fields == (
                {"name"} if key in {"archive_name", "unsubscribe_confirm"} else set()
            ), path.name
        assert data["calendar_management_tabs"]["ics_tab"] in data["sync_unified"]["ics_failed"]
