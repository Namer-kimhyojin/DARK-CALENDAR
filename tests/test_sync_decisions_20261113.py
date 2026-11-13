# -*- coding: utf-8 -*-
"""Decisions on the open external-sync questions from the 2026-11-13 audit."""

from datetime import UTC, datetime
import json
import socket
import sqlite3
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox
import pytest

from calendar_app.application.calendar_sync_contract import CalendarSyncError
from calendar_app.infrastructure.calendar_sync.engine import CalendarSyncEngine
from calendar_app.infrastructure.calendar_sync.repository import (
    CalendarSyncRepository,
    fingerprint,
)
from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.ics import ics_fetcher, subscription_http
from calendar_app.presentation.dialogs.calendar_manager_page import CalendarManagerPage
from calendar_app.presentation.dialogs.sync_feedback import sync_error_message
from calendar_app.presentation.main_window import calendar_sync_coordinator as coordinator_module
from tests.test_calendar_sync_engine import Provider, imported, repo, task  # noqa: F401
from tests.test_calendar_sync_redesign import sync_ui  # noqa: F401
from tests.test_ics_snapshot_safety import event, feed, rows, snapshot  # noqa: F401
from tests.test_provider_settings_ux import ui  # noqa: F401

ROLE = int(Qt.ItemDataRole.UserRole)


def _queue(repo):
    return [
        dict(row)
        for row in repo.conn.execute("SELECT * FROM calendar_sync_delete_queue ORDER BY event_id")
    ]


# 1. An ICS subscription that was really emptied can be accepted once.


def test_confirmed_empty_feed_removes_only_the_confirmed_number_of_mirrors(snapshot, monkeypatch):
    monkeypatch.setattr(ics_fetcher, "_now", lambda: datetime(2026, 10, 5, tzinfo=UTC))
    conn, sync = snapshot
    assert sync(feed(event("one"), event("two")))[2] is None
    before = rows(conn)
    # A stale confirmation (another count) keeps the protection.
    assert sync(feed(), accept_empty=1) == (0, 0, "calendar_report_incomplete")
    assert rows(conn) == before
    assert sync(feed(), accept_empty=2) == (0, 2, None)
    assert rows(conn) == []


def test_empty_feed_acceptance_does_not_change_a_feed_with_events(snapshot, monkeypatch):
    monkeypatch.setattr(ics_fetcher, "_now", lambda: datetime(2026, 10, 5, tzinfo=UTC))
    conn, sync = snapshot
    assert sync(feed(event("one"), event("two")))[2] is None
    assert sync(feed(event("one"), event("two")), accept_empty=2) == (2, 0, None)
    assert len(rows(conn)) == 2


def _ics_page(sync_ui, monkeypatch, key="ics::emptied"):
    sync_ui.add_calendar(key)
    sync_ui.host.settings.setValue("sync_ics_error_codes", {key: "calendar_report_incomplete"})
    sync_ui.coordinator.refresh()
    monkeypatch.setattr(coordinator_module.IcsSyncWorker, "start", Mock())
    page = CalendarManagerPage(sync_ui.host, sync_ui.coordinator, Mock(), scope="ics")
    assert page.select_calendar(key)
    return page


def test_empty_feed_button_confirms_the_count_and_refreshes_once(sync_ui, monkeypatch):
    key = "ics::emptied"
    page = _ics_page(sync_ui, monkeypatch, key)
    monkeypatch.setattr(ics_fetcher, "mirror_count", lambda calendar_id: 7)
    asked = []

    def question(parent, title, text, *args):
        asked.append(text)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", question)
    try:
        assert not page.accept_empty.isHidden()
        assert page.accept_empty.isEnabled()
        page.accept_empty.click()
        assert len(asked) == 1 and "7" in asked[0]
        worker = sync_ui.coordinator.ics_worker
        assert worker is not None
        assert [(c["id"], c.get("accept_empty")) for c in worker.calendars] == [(key, 7)]
        # The acceptance belongs to that one refresh only.
        sync_ui.coordinator.ics_worker = None
        sync_ui.host._bg_workers.clear()
        assert sync_ui.coordinator.sync_ics(force=True, calendar_ids=[key])
        assert sync_ui.coordinator.ics_worker.calendars[0].get("accept_empty") is None
    finally:
        sync_ui.coordinator.ics_worker = None
        sync_ui.host._bg_workers.clear()
        page.close()


def test_empty_feed_acceptance_is_dropped_when_its_refresh_cannot_start(sync_ui, monkeypatch):
    key = "ics::emptied"
    page = _ics_page(sync_ui, monkeypatch, key)
    monkeypatch.setattr(ics_fetcher, "mirror_count", lambda calendar_id: 2)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(sync_ui.coordinator, "sync_ics", Mock(return_value=False))
    try:
        page.accept_empty.click()
        assert sync_ui.coordinator._ics_accept_empty == {}
    finally:
        page.close()


def test_empty_feed_button_does_nothing_when_declined_or_for_other_errors(sync_ui, monkeypatch):
    key = "ics::emptied"
    page = _ics_page(sync_ui, monkeypatch, key)
    monkeypatch.setattr(ics_fetcher, "mirror_count", lambda calendar_id: 3)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    try:
        page.accept_empty.click()
        assert sync_ui.coordinator.ics_worker is None
        sync_ui.host.settings.setValue("sync_ics_error_codes", {key: "ics_server_error"})
        page._selection()
        assert page.accept_empty.isHidden()
    finally:
        page.close()


# 2. Delete-queue rows that cannot progress are explained and resolvable.


def _conflicted_delete(repo):
    provider, key, engine, tid = imported(repo)
    with repo.conn:
        repo.conn.execute("DELETE FROM unified_task WHERE id=?", (tid,))
    provider.remote["remote"]["etag"] = "2"
    provider.remote["remote"]["task"]["name"] = "Edited remotely"
    engine.run()
    return provider, key, engine


def test_delete_conflict_keeps_the_remote_revision_for_review(repo):
    provider, key, _ = _conflicted_delete(repo)
    [row] = _queue(repo)
    assert row["error"] == "delete_conflict"
    assert json.loads(row["remote_json"])["task"]["name"] == "Edited remotely"
    assert "remote" in provider.remote


def test_confirmed_delete_removes_exactly_the_reviewed_revision(repo):
    provider, key, engine = _conflicted_delete(repo)
    [row] = _queue(repo)
    assert repo.confirm_delete("account", key, "remote", row["remote_json"])
    result = engine.run()
    assert provider.writes == ["delete"]
    assert "remote" not in provider.remote
    assert _queue(repo) == []
    assert result["issues"] == 0


def test_confirmed_delete_conflicts_again_when_the_remote_changed_after_review(repo):
    provider, key, engine = _conflicted_delete(repo)
    [row] = _queue(repo)
    assert repo.confirm_delete("account", key, "remote", row["remote_json"])
    provider.remote["remote"]["etag"] = "3"
    provider.remote["remote"]["task"]["name"] = "Edited again"
    engine.run()
    assert provider.writes == []
    [row] = _queue(repo)
    assert row["error"] == "delete_conflict"
    assert json.loads(row["remote_json"])["task"]["name"] == "Edited again"


def test_stale_confirmation_is_rejected(repo):
    provider, key, engine = _conflicted_delete(repo)
    assert not repo.confirm_delete("account", key, "remote", '{"etag": "2"}')
    assert not repo.confirm_delete("other-account", key, "remote", _queue(repo)[0]["remote_json"])
    assert _queue(repo)[0]["error"] == "delete_conflict"


def test_dropping_a_conflicted_delete_brings_the_remote_event_back(repo):
    provider, key, engine = _conflicted_delete(repo)
    with repo.conn:
        repo.conn.execute("DELETE FROM calendar_sync_delete_queue")
    result = engine.run()
    assert result["imported"] == 1
    [local] = repo.tasks(key)
    assert local["name"] == "Edited remotely"
    assert repo.task_link(local["id"])["event_id"] == "remote"
    assert provider.writes == []


def test_legacy_conflict_without_remote_revision_is_rechecked_but_never_deleted(repo):
    provider, key, engine = _conflicted_delete(repo)
    with repo.conn:
        repo.conn.execute("UPDATE calendar_sync_delete_queue SET remote_json=NULL")
    engine.run()
    [row] = _queue(repo)
    assert row["error"] == "delete_conflict"
    assert json.loads(row["remote_json"])["etag"] == "2"
    assert provider.writes == []


def test_deletes_waiting_on_deselected_or_read_only_calendars_count_as_issues(repo):
    writable = repo.calendars("account")[0]["local_id"]
    readonly = repo.register("account", {"id": "shared", "name": "Shared", "canEdit": False})
    with repo.conn:
        repo.conn.execute("UPDATE calendar SET is_active=0 WHERE id=?", (writable,))
        repo.conn.executemany(
            "INSERT INTO calendar_sync_delete_queue(event_id,calendar_id,etag) VALUES(?,?,'1')",
            [("waiting-a", writable), ("waiting-b", readonly)],
        )
    result = CalendarSyncEngine(Provider(), repo, "account").run()
    assert result["issues"] == 2
    reasons = {row["event_id"]: row["reason"] for row in repo.delete_queue("account")}
    assert reasons == {"waiting-a": "calendar_not_selected", "waiting-b": "calendar_read_only"}


def test_hub_counts_deletes_waiting_on_a_deselected_calendar(tmp_path):
    path = tmp_path / "calendar.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE calendar(id TEXT PRIMARY KEY,type TEXT,name TEXT,color TEXT,"
        "is_active INTEGER,access_role TEXT);"
        "CREATE TABLE unified_task(id INTEGER PRIMARY KEY,name TEXT,calendar_id TEXT);"
    )
    repository = CalendarSyncRepository(conn)
    key = repository.register(
        "microsoft::account", {"id": "calendar", "name": "Work", "canEdit": True}
    )
    with conn:
        conn.execute("UPDATE calendar SET is_active=0 WHERE id=?", (key,))
        conn.execute(
            "INSERT INTO calendar_sync_delete_queue(event_id,calendar_id,etag) "
            "VALUES('waiting',?,'1')",
            (key,),
        )
    conn.close()
    fake = SimpleNamespace(database_path=str(path), calendar_providers={})
    counts, _, issues = coordinator_module.CalendarSyncCoordinator._metadata(fake)
    assert counts == {"microsoft::account": 1}
    assert issues[0]["kind"] == "calendar_not_selected"


def _dialog_queue_row(ui, error, remote=None, *, active=True, writable=True):
    _, host, dialog, controller, path, provider = ui
    host.settings.setValue("gcal_timezone", "Asia/Seoul")
    conn = sqlite3.connect(path)
    repository = CalendarSyncRepository(conn, "outlook" if provider == "outlook" else "caldav")
    remote_calendar = dict(controller.available[0])
    remote_calendar["canEdit" if provider == "outlook" else "can_edit"] = writable
    key = repository.register(controller.account, remote_calendar)
    with conn:
        conn.execute("UPDATE calendar SET is_active=? WHERE id=?", (int(active), key))
        conn.execute(
            "INSERT INTO calendar_sync_delete_queue(event_id,calendar_id,etag,attempts,error,"
            "remote_json) VALUES('event',?,'1',1,?,?)",
            (key, error, json.dumps(remote) if remote else None),
        )
    conn.close()
    dialog._available_key = None
    dialog._refresh()
    dialog.tabs.setCurrentIndex(2)

    def queued(index):
        value = dialog.issues.item(index).data(ROLE)
        return value == "event" or (isinstance(value, dict) and value.get("event_id") == "event")

    rows = [index for index in range(dialog.issues.count()) if queued(index)]
    dialog.issues.setCurrentRow(rows[0])
    return key


def _buttons(dialog, provider):
    if provider == "outlook":
        return dialog.retry_delete, dialog.cancel_delete
    return dialog.retry, dialog.cancel_delete


def _remote_revision(provider):
    if provider == "outlook":
        return {
            "id": "event",
            "etag": 'W/"2"',
            "subject": "Edited remotely",
            "start": {"dateTime": "2026-10-08T05:00:00"},
            "end": {"dateTime": "2026-10-08T06:00:00"},
            "isAllDay": False,
        }
    return {
        "id": "event",
        "etag": '"2"',
        "zone": "Asia/Seoul",
        "task": {
            "name": "Edited remotely",
            "deadline": "2026-10-08T14:00:00",
            "end_date": "2026-10-08T15:00:00",
            "all_day": 0,
            "description": "",
            "location": "",
        },
    }


def test_delete_conflict_row_offers_reimport_and_reviewed_delete(ui, monkeypatch):
    _, host, dialog, controller, path, provider = ui
    remote = _remote_revision(provider)
    key = _dialog_queue_row(ui, "delete_conflict", remote)
    retry, cancel = _buttons(dialog, provider)
    assert retry.text() == t("sync_delete.force", "그래도 삭제")
    assert cancel.text() == t("sync_delete.reimport", "원격 일정 다시 가져오기")
    assert retry.isEnabled() and cancel.isEnabled()
    preview = dialog.preview.toPlainText()
    assert "Edited remotely" in preview and "2026-10-08 14:00" in preview
    asked = []

    def question(parent, title, text, *args):
        asked.append(text)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", question)
    retry.click()
    assert "Edited remotely" in asked[0] and "2026-10-08 14:00" in asked[0]
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT etag,error,attempts,remote_json FROM calendar_sync_delete_queue "
            "WHERE calendar_id=?",
            (key,),
        ).fetchone()
        assert row == (remote["etag"], None, 0, None)
    finally:
        conn.close()
    controller.sync.assert_called_once_with(force=True)


def test_declined_reviewed_delete_changes_nothing(ui, monkeypatch):
    _, host, dialog, controller, path, provider = ui
    _dialog_queue_row(ui, "delete_conflict", _remote_revision(provider))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    _buttons(dialog, provider)[0].click()
    conn = sqlite3.connect(path)
    try:
        assert conn.execute("SELECT error FROM calendar_sync_delete_queue").fetchone() == (
            "delete_conflict",
        )
    finally:
        conn.close()
    controller.sync.assert_not_called()


def test_reimport_drops_the_conflicted_delete_and_syncs(ui):
    _, host, dialog, controller, path, provider = ui
    _dialog_queue_row(ui, "delete_conflict", _remote_revision(provider))
    _buttons(dialog, provider)[1].click()
    conn = sqlite3.connect(path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM calendar_sync_delete_queue").fetchone() == (0,)
    finally:
        conn.close()
    controller.sync.assert_called_once_with(force=True)


HINTS = {
    "event_read_only": (
        "sync_delete.event_read_only_hint",
        "반복 일정의 한 회차나 초대받은 일정은 앱에서 삭제할 수 없습니다. 원래 서비스에서 "
        "삭제하세요. '목록에서 제거'를 누르면 이 대기 항목만 지웁니다. 원격 일정은 남아 다음 "
        "동기화 때 다시 표시됩니다.",
    ),
    "calendar_not_selected": (
        "sync_delete.not_selected_hint",
        "이 캘린더를 가져오기에서 제외해 삭제를 보내지 않고 기다립니다. 캘린더를 다시 선택하면 "
        "삭제합니다. '목록에서 제거'를 누르면 원격 일정은 지우지 않고 대기만 취소합니다.",
    ),
    "calendar_read_only": (
        "sync_delete.read_only_calendar_hint",
        "이 캘린더에 쓰기 권한이 없어 삭제를 보내지 않고 기다립니다. 권한이 생기면 삭제합니다. "
        "'목록에서 제거'를 누르면 원격 일정은 지우지 않고 대기만 취소합니다.",
    ),
}


@pytest.mark.parametrize(
    ("error", "active", "writable", "reason"),
    [
        ("event_read_only", True, True, "event_read_only"),
        (None, False, True, "calendar_not_selected"),
        (None, True, False, "calendar_read_only"),
    ],
)
def test_rows_that_cannot_be_deleted_offer_only_removal_from_the_list(
    ui, error, active, writable, reason
):
    _, host, dialog, controller, path, provider = ui
    _dialog_queue_row(ui, error, active=active, writable=writable)
    retry, cancel = _buttons(dialog, provider)
    assert retry.isHidden()
    assert cancel.text() == t("sync_delete.remove_from_list", "목록에서 제거")
    assert cancel.isEnabled()
    assert dialog.preview.toPlainText() == t(*HINTS[reason])
    cancel.click()
    conn = sqlite3.connect(path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM calendar_sync_delete_queue").fetchone() == (0,)
    finally:
        conn.close()
    controller.sync.assert_not_called()


def test_waiting_row_label_names_the_reason(ui):
    _, host, dialog, controller, path, provider = ui
    _dialog_queue_row(ui, None, active=False)
    assert (
        dialog.issues.currentItem()
        .text()
        .endswith(t("sync_delete.not_selected", "캘린더 선택 해제됨"))
    )


# 3. A stalled DNS lookup is bounded by the request deadline and cancellation.


@pytest.fixture
def stalled_resolver(monkeypatch):
    release = threading.Event()

    def stalled(*args, **kwargs):
        release.wait(3)
        raise socket.gaierror("synthetic resolver failure")

    monkeypatch.setattr(subscription_http.socket, "getaddrinfo", stalled)
    yield
    release.set()


def test_stalled_dns_lookup_stops_at_the_deadline(stalled_resolver):
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        subscription_http._connect_public(
            ("feed.example.invalid", 443),
            15,
            cancelled=lambda: False,
            deadline=time.monotonic() + 0.3,
        )
    assert time.monotonic() - started < 1.5


def test_stalled_dns_lookup_stops_when_cancelled(stalled_resolver):
    started = time.monotonic()
    with pytest.raises(CalendarSyncError, match="cancelled"):
        subscription_http._connect_public(
            ("feed.example.invalid", 443),
            15,
            cancelled=lambda: time.monotonic() - started > 0.2,
            deadline=time.monotonic() + 30,
        )
    assert time.monotonic() - started < 1.5


def test_stalled_dns_lookups_do_not_pile_up_threads(stalled_resolver):
    def lookup_threads():
        return [t for t in threading.enumerate() if t.name == "ics-resolve" and t.is_alive()]

    before = len(lookup_threads())
    for _ in range(subscription_http._MAX_STALLED_LOOKUPS + 3):
        with pytest.raises(TimeoutError):
            subscription_http._connect_public(
                ("feed.example.invalid", 443),
                15,
                cancelled=lambda: False,
                deadline=time.monotonic() + 0.1,
            )
    assert len(lookup_threads()) - before <= subscription_http._MAX_STALLED_LOOKUPS


def test_bounded_lookup_still_rejects_private_addresses(monkeypatch):
    monkeypatch.setattr(
        subscription_http.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 443))
        ],
    )
    with pytest.raises(CalendarSyncError, match="invalid_subscription_url"):
        subscription_http._connect_public(
            ("feed.example.invalid", 443),
            15,
            cancelled=lambda: False,
            deadline=time.monotonic() + 5,
        )


# 4. Opening the sync repository again never re-creates the delete trigger.


def _linked_database(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE calendar(id TEXT PRIMARY KEY,type TEXT,name TEXT,color TEXT,"
        "is_active INTEGER,access_role TEXT);"
        "CREATE TABLE unified_task(id INTEGER PRIMARY KEY,name TEXT,calendar_id TEXT);"
    )
    repository = CalendarSyncRepository(conn)
    key = repository.register("account", {"id": "calendar", "name": "Work", "canEdit": True})
    with conn:
        conn.execute("INSERT INTO unified_task(id,name,calendar_id) VALUES(1,'Linked',?)", (key,))
        repository.link(1, key, "remote", "1", "baseline", "transaction")
    return conn


def test_reopening_the_repository_does_not_drop_the_delete_trigger(tmp_path):
    conn = _linked_database(tmp_path / "calendar.db")
    statements = []
    version = conn.execute("PRAGMA schema_version").fetchone()[0]
    conn.set_trace_callback(statements.append)
    try:
        CalendarSyncRepository(conn)
        CalendarSyncRepository(conn, "caldav")
    finally:
        conn.set_trace_callback(None)
    try:
        assert conn.execute("PRAGMA schema_version").fetchone()[0] == version
        assert not [s for s in statements if "DROP TRIGGER" in s.upper()]
    finally:
        conn.close()


def test_delete_on_another_connection_while_reopening_is_still_queued(tmp_path):
    path = tmp_path / "calendar.db"
    conn = _linked_database(path)
    other = sqlite3.connect(path)
    dropped = []

    def trace(statement):
        if dropped == [True] and "CREATE TRIGGER" in statement.upper():
            dropped.append(statement)
            with other:
                other.execute("DELETE FROM unified_task WHERE id=1")
        if "DROP TRIGGER" in statement.upper() and "CAPTURE_DELETE" in statement.upper():
            dropped.append(True)

    conn.set_trace_callback(trace)
    try:
        CalendarSyncRepository(conn)
    finally:
        conn.set_trace_callback(None)
    with other:
        other.execute("DELETE FROM unified_task WHERE id=1")
    try:
        queued = conn.execute("SELECT event_id FROM calendar_sync_delete_queue").fetchall()
        assert [tuple(row) for row in queued] == [("remote",)]
    finally:
        other.close()
        conn.close()


def test_outdated_delete_trigger_is_replaced_once(tmp_path):
    conn = _linked_database(tmp_path / "calendar.db")
    try:
        conn.execute("DROP TRIGGER calendar_sync_capture_delete")
        conn.execute(
            "CREATE TRIGGER calendar_sync_capture_delete BEFORE DELETE ON unified_task "
            "BEGIN DELETE FROM calendar_sync_event WHERE task_id=OLD.id; END"
        )
        CalendarSyncRepository(conn)
        with conn:
            conn.execute("DELETE FROM unified_task WHERE id=1")
        queued = conn.execute("SELECT event_id FROM calendar_sync_delete_queue").fetchall()
        assert [tuple(row) for row in queued] == [("remote",)]
    finally:
        conn.close()


# 5. Outlook problem tab: explanations for every issue and no crash on bad JSON.


@pytest.mark.parametrize(
    "kind", ["remote_deleted", "calendar_read_only", "calendar_move_not_supported"]
)
def test_outlook_issue_preview_explains_the_issue(ui, kind):
    _, host, dialog, controller, path, provider = ui
    if provider != "outlook":
        pytest.skip("Outlook problem tab")
    conn = sqlite3.connect(path)
    repository = CalendarSyncRepository(conn)
    key = repository.register(controller.account, controller.available[0])
    local = {**task(), "name": "Kept locally"}
    with conn:
        tid = repository.import_task(key, local)
        repository.link(tid, key, "event", "1", fingerprint(local), "transaction")
        repository.issue(tid, kind, local)
    conn.close()
    dialog._available_key = None
    dialog._refresh()
    dialog.issues.setCurrentRow(0)
    assert dialog.preview.toPlainText() == sync_error_message(kind)


def test_conflict_with_unreadable_remote_json_cannot_crash_resolution(ui):
    _, host, dialog, controller, path, provider = ui
    conn = sqlite3.connect(path)
    repository = CalendarSyncRepository(conn, "outlook" if provider == "outlook" else "caldav")
    remote_calendar = dict(controller.available[0])
    remote_calendar["canEdit" if provider == "outlook" else "can_edit"] = True
    key = repository.register(controller.account, remote_calendar)
    local = {**task(), "name": "Local"}
    # Valid JSON whose content cannot be converted (overflowing time / missing task).
    remote = (
        {
            "id": "event",
            "start": {"dateTime": "9999-12-31T23:00:00"},
            "end": {"dateTime": "9999-12-31T23:59:00"},
        }
        if provider == "outlook"
        else {"id": "event", "etag": "2"}
    )
    with conn:
        tid = repository.import_task(key, local)
        repository.link(tid, key, "event", "1", fingerprint(local), "transaction")
        repository.issue(tid, "conflict", repository.task(tid), remote)
    conn.close()
    host.settings.setValue("gcal_timezone", "Asia/Seoul")
    dialog._available_key = None
    dialog._refresh()
    dialog.issues.setCurrentRow(0)
    dialog._resolve("remote")
    assert controller.status == "conflict_snapshot_changed"
    conn = sqlite3.connect(path)
    try:
        assert conn.execute("SELECT name FROM unified_task").fetchone() == ("Local",)
    finally:
        conn.close()


# 6. No sync conversion silently assumes Asia/Seoul.


@pytest.fixture
def berlin(monkeypatch):
    from calendar_app.infrastructure.google_sync import common

    monkeypatch.setattr(common, "_system_time_zone", lambda: "Europe/Berlin")


def _zone_defaults():
    import inspect

    from calendar_app.infrastructure.caldav_sync import client as caldav_client
    from calendar_app.infrastructure.caldav_sync import conversion as caldav_conversion
    from calendar_app.infrastructure.calendar_sync import engine
    from calendar_app.infrastructure.google_sync import service
    from calendar_app.infrastructure.outlook_sync import conversion as outlook_conversion
    from calendar_app.presentation.dialogs import sync_feedback
    from calendar_app.presentation.main_window import caldav_sync_controller as caldav_controller
    from calendar_app.presentation.main_window import outlook_sync_controller as outlook_controller

    functions = [
        outlook_conversion.to_graph,
        outlook_conversion.from_graph,
        caldav_conversion.to_task_component,
        caldav_conversion.records,
        caldav_conversion.apply_task,
        caldav_conversion.new_calendar,
        caldav_conversion.edited_calendar,
        caldav_client.CalDAVClient.__init__,
        caldav_client.CalDAVClient.to_task,
        caldav_client.CalDAVClient.from_task,
        caldav_client.CalDAVClient.edit_payload,
        engine.CalendarSyncEngine.__init__,
        service.CalendarSyncService.__init__,
        service.prepare_calendar_sync_service,
        sync_feedback.conflict_text,
        outlook_controller.OutlookWorker.__init__,
        caldav_controller.CalDAVWorker.__init__,
    ]
    for function in functions:
        for name, parameter in inspect.signature(function).parameters.items():
            if "zone" in name:
                yield function.__qualname__, name, parameter.default


def test_no_sync_function_defaults_to_seoul():
    defaults = list(_zone_defaults())
    assert len(defaults) == 17
    assert [entry for entry in defaults if entry[2] == "Asia/Seoul"] == []


def test_pure_conversions_require_an_explicit_zone():
    import inspect

    required = {
        (qualname, name)
        for qualname, name, default in _zone_defaults()
        if default is inspect.Parameter.empty
    }
    assert {
        ("to_graph", "local_zone"),
        ("from_graph", "local_zone"),
        ("records", "zone"),
        ("new_calendar", "zone"),
        ("edited_calendar", "zone"),
        ("CalDAVClient.to_task", "local_zone"),
        ("conflict_text", "zone"),
    } <= required


def test_objects_built_without_a_zone_use_this_pc_zone(berlin, repo):  # noqa: F811
    from calendar_app.infrastructure.caldav_sync.client import CalDAVClient
    from calendar_app.infrastructure.google_sync import service
    from calendar_app.presentation.main_window import caldav_sync_controller as caldav
    from calendar_app.presentation.main_window import outlook_sync_controller as outlook

    assert CalendarSyncEngine(Provider(), repo, "account").zone == "Europe/Berlin"
    assert CalDAVClient("icloud", "fixture", "synthetic").local_zone == "Europe/Berlin"
    assert service.CalendarSyncService().time_zone == "Europe/Berlin"
    assert service.prepare_calendar_sync_service().time_zone == "Europe/Berlin"
    assert outlook.OutlookWorker("sync", "client", "account", None).local_zone == "Europe/Berlin"
    assert caldav.CalDAVWorker("icloud", "sync", "account", None).local_zone == "Europe/Berlin"
