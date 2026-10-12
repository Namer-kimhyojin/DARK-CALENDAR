# -*- coding: utf-8 -*-
"""User journeys for calendar choices, subscription onboarding and recovery."""

from datetime import UTC, datetime, timedelta, timezone
import sqlite3
import sys
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QObject, QPoint, QSettings, Qt, pyqtSignal
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QScrollArea, QToolButton, QWidget
import pytest

from calendar_app.infrastructure.db import task_repo
from calendar_app.presentation.dialogs import calendar_manager_page as manager
from calendar_app.presentation.dialogs import ics_subscription_dialog as ics_form
from calendar_app.presentation.dialogs.calendar_sync_hub import CalendarSyncHub
from calendar_app.presentation.dialogs.sync_feedback import sync_error_message
from calendar_app.presentation.main_window import calendar_sync_coordinator as sync_module


class IdleController(QObject):
    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.busy = False
        self.status = "idle"
        self.start = Mock(return_value=False)


@pytest.fixture
def sync_ui(tmp_path, monkeypatch):
    qapp = QApplication.instance() or QApplication([])
    host = QWidget()
    host.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    host.settings.setValue("gcal_enabled", "true")
    host.gcal_sync = SimpleNamespace(is_authenticated=True)
    host._gcal_sync_in_progress = False
    host._bg_workers = []
    host._outlook_sync_controller = IdleController()
    host._caldav_sync_controllers = {key: IdleController() for key in ("icloud", "naver")}
    host.schedule_panel_refresh = Mock()
    host.update_gcal_sync_timer = Mock()
    host.open_gcal_settings_dialog = Mock()
    host.open_gcal_sync_issues_dialog = Mock()
    host.sync_action_btn = QToolButton(host)
    host.sync_status_text_lbl = QLabel(host)

    def start_google(**kwargs):
        host._gcal_sync_in_progress = True

    host.sync_google_calendar = Mock(side_effect=start_google)
    host.sync_google_calendar_silent = Mock()
    database_path = tmp_path / "calendar.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript("""
            CREATE TABLE calendar (
                id TEXT PRIMARY KEY, type TEXT, name TEXT, color TEXT DEFAULT '#3478c5',
                is_active INTEGER DEFAULT 1, access_role TEXT, is_visible INTEGER DEFAULT 1,
                is_default INTEGER DEFAULT 0, ics_url TEXT, ics_last_fetched TEXT
            );
            INSERT INTO calendar(id,type,name,access_role)
            VALUES('local::personal','local','Personal','owner');
        """)

    def calendars(**kwargs):
        with sqlite3.connect(database_path) as connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute("SELECT * FROM calendar")]

    for name in (
        "count_unified_task_gcal_errors",
        "count_gcal_delete_queue_errors",
        "count_gcal_sync_conflicts",
    ):
        monkeypatch.setattr(task_repo, name, lambda: 0)
    monkeypatch.setattr(sync_module, "TOKEN_PATH", str(tmp_path / "absent-token"))
    monkeypatch.setattr(manager.calendar_repo, "list_calendars", calendars)
    coordinator = sync_module.CalendarSyncCoordinator(host, str(database_path), calendars)
    host._calendar_sync_coordinator = coordinator

    def add_calendar(key, kind="ics", *, active=True, visible=True, role="reader", url=None):
        if kind == "ics" and url is None:
            url = "https://calendar.example.invalid/" + key.replace("::", "-") + ".ics"
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                "INSERT INTO calendar(id,type,name,is_active,is_visible,access_role,ics_url) "
                "VALUES(?,?,?,?,?,?,?)",
                (key, kind, key, int(active), int(visible), role, url),
            )
        coordinator.refresh()

    yield SimpleNamespace(
        qapp=qapp, host=host, coordinator=coordinator, path=database_path, add_calendar=add_calendar
    )
    coordinator.stop()
    for worker in list(host._bg_workers):
        worker.requestInterruption()
        worker.wait(2000)
    host.close()
    qapp.processEvents()


def select_calendar(page, key):
    for index in range(page.calendars.count()):
        item = page.calendars.item(index)
        if item.data(Qt.ItemDataRole.UserRole)["id"] == key:
            page.calendars.setCurrentItem(item)
            return
    raise AssertionError(f"Missing fixture calendar: {key}")


def test_my_calendars_is_the_entry_point_and_empty_ics_has_a_direct_add_action(
    sync_ui, monkeypatch
):
    hub = CalendarSyncHub(sync_ui.host)
    assert hub.tabs.currentIndex() == 1
    assert not hub.sync_buttons["ics"].isEnabled()
    add_subscription = Mock()
    monkeypatch.setattr(hub.ics_manager, "_add_ics", add_subscription)
    hub.tabs.setCurrentIndex(0)
    hub.connect_buttons["ics"].click()
    assert hub.tabs.currentWidget() is hub.section_pages["ics"]
    assert hub.ics_manager.provider_filter.currentData() == "ics"
    add_subscription.assert_called_once()
    assert not sync_ui.host.settings.value("sync_ics_last_success")
    hub.close()


def test_busy_sync_prevents_duplicate_request_and_explains_service_state(sync_ui, monkeypatch):
    hub = CalendarSyncHub(sync_ui.host, section="services")
    hub.show()
    sync_ui.qapp.processEvents()
    for provider in ("google", "ics"):
        assert hub.service_badges[provider].isVisible()
        assert hub.service_badges[provider].width() > 0
    hub.sync_buttons["google"].click()
    sync_ui.qapp.processEvents()
    assert sync_ui.coordinator.states["google"]["busy"]
    assert not hub.sync_buttons["google"].isEnabled()
    assert hub.service_badges["google"].text()
    assert hub.service_badges["google"].property("health") == "busy"
    assert hub.service_badges["google"].width() > 0
    assert hub.labels["google"].text()
    hub.sync_buttons["google"].click()
    hub._run_sync("google")
    sync_ui.host.sync_google_calendar.assert_called_once_with(silent=True)
    assert not hub.sync_all.isEnabled()
    sync_ui.add_calendar("ics::busy")
    start_worker = Mock()
    monkeypatch.setattr(sync_module.IcsSyncWorker, "start", start_worker)
    hub._run_sync("ics")
    worker = sync_ui.coordinator.ics_worker
    assert worker is not None
    assert not hub.sync_buttons["ics"].isEnabled()
    sync_ui.qapp.processEvents()
    assert hub.service_badges["ics"].property("health") == "busy"
    assert hub.service_badges["ics"].width() > 0
    assert not hub.sync_all.isEnabled()
    hub._run_sync("ics")
    assert sync_ui.coordinator.ics_worker is worker
    start_worker.assert_called_once()
    select_calendar(hub.ics_manager, "ics::busy")
    for action in (
        hub.ics_manager.add_ics,
        hub.ics_manager.edit_subscription,
        hub.ics_manager.subscription_active,
        hub.ics_manager.remove,
    ):
        assert not action.isEnabled()
    save_subscription = Mock()
    monkeypatch.setattr(manager.calendar_repo, "update_ics_subscription", save_subscription)
    assert not hub.ics_manager._save_subscription(
        hub.ics_manager.current(), "Updated", "https://example.invalid/updated.ics"
    )
    save_subscription.assert_not_called()
    hub.close()


def test_read_only_and_paused_calendars_explain_why_they_cannot_be_default(sync_ui, monkeypatch):
    sync_ui.add_calendar("ics::readonly")
    sync_ui.add_calendar("gcal::readonly", "gcal")
    sync_ui.add_calendar("gcal::paused", "gcal", active=False, role="writer")
    save_default = Mock()
    monkeypatch.setattr(manager.calendar_repo, "set_calendar_default", save_default)
    page = manager.CalendarManagerPage(sync_ui.host, sync_ui.coordinator, Mock())
    select_calendar(page, "local::personal")
    writable_explanation = page.selection_info.text()
    assert page.default_controls["local::personal"].isEnabled()
    for key in ("ics::readonly", "gcal::readonly", "gcal::paused"):
        select_calendar(page, key)
        assert not page.default_controls[key].isEnabled()
        assert page.selection_info.text()
        assert page.selection_info.text() != writable_explanation
        assert page.default_controls[key].toolTip()
        page._default(key)
    save_default.assert_not_called()
    page.close()


def test_ics_issue_recovery_selects_failed_subscription_and_retries_only_that_one(
    sync_ui, monkeypatch
):
    sync_ui.add_calendar("ics::paused-failed", active=False)
    sync_ui.add_calendar("ics::healthy")
    private_url = "https://calendar.example.invalid/private-feed.ics?access=fixture-token"
    sync_ui.add_calendar("ics::failed", url=private_url)
    sync_ui.host.settings.setValue(
        "sync_ics_error_codes",
        {"ics::paused-failed": "ics_not_found", "ics::failed": "ics_access_denied"},
    )
    sync_ui.host.settings.setValue("sync_ics_failed_ids", ["ics::paused-failed", "ics::failed"])
    sync_ui.coordinator.refresh()
    assert sync_ui.coordinator.states["ics"]["issues"] == 1
    hub = CalendarSyncHub(sync_ui.host, section="issues")
    hub.issue_list.setCurrentRow(0)
    assert hub.issue_detail.text()
    assert "ics::failed" in hub.issue_detail.text()
    assert sync_error_message("ics_access_denied") in hub.issue_detail.text()
    assert sync_error_message("ics_not_found") not in hub.issue_detail.text()
    assert hub.resolve_selected.isEnabled()
    hub.resolve_selected.click()
    assert hub.tabs.currentWidget() is hub.section_pages["ics"]
    assert hub.ics_manager.current()["id"] == "ics::failed"
    assert hub.ics_manager.subscription_info.text()
    assert "fixture-token" not in hub.ics_manager.subscription_address.text()
    hub.ics_manager.reveal_subscription.click()
    assert private_url in hub.ics_manager.subscription_address.text()
    select_calendar(hub.ics_manager, "ics::healthy")
    select_calendar(hub.ics_manager, "ics::failed")
    assert not hub.ics_manager.reveal_subscription.isChecked()
    assert "fixture-token" not in hub.ics_manager.subscription_address.text()
    retry = Mock(return_value=True)
    monkeypatch.setattr(sync_ui.coordinator, "sync_ics", retry)
    hub.ics_manager.service.click()
    retry.assert_called_once_with(force=True, calendar_ids=["ics::failed"])
    hub.close()


def test_completed_work_clears_starting_messages_in_hub_and_subscription_details(
    sync_ui, monkeypatch
):
    hub = CalendarSyncHub(sync_ui.host, section="services")
    hub._run_sync("google")
    assert not hub.sync_feedback.isHidden()
    sync_ui.host._gcal_sync_in_progress = False
    sync_ui.coordinator.refresh()
    assert not hub.sync_feedback.isHidden()
    assert hub.sync_feedback.text()

    sync_ui.add_calendar("ics::completed")
    monkeypatch.setattr(sync_module.IcsSyncWorker, "start", lambda self: None)
    hub.show_section("ics")
    select_calendar(hub.ics_manager, "ics::completed")
    hub.ics_manager.service.click()
    worker = sync_ui.coordinator.ics_worker
    starting_message = hub.ics_manager.feedback.text()
    assert starting_message
    assert worker is not None
    sync_ui.coordinator._ics_result({"ics::completed": (0, 0, None)})
    worker.finished.emit()
    assert not sync_ui.coordinator.states["ics"]["busy"]
    assert hub.ics_manager.feedback.text() != starting_message
    hub.close()


def test_subscription_last_fetch_displays_local_time_for_aware_timestamps(sync_ui):
    sync_ui.add_calendar("ics::timestamp")
    page = manager.CalendarManagerPage(sync_ui.host, sync_ui.coordinator, Mock())
    select_calendar(page, "ics::timestamp")
    for fetched in (
        datetime(2026, 10, 6, 12, 0, tzinfo=UTC),
        datetime(2026, 10, 6, 12, 0, tzinfo=timezone(timedelta(hours=-8))),
    ):
        with sqlite3.connect(sync_ui.path) as connection:
            connection.execute(
                "UPDATE calendar SET ics_last_fetched=? WHERE id='ics::timestamp'",
                (fetched.isoformat(),),
            )
        sync_ui.coordinator.refresh()
        page.reload()
        assert fetched.astimezone().strftime("%Y-%m-%d %H:%M") in page.subscription_info.text()
    page.close()


def test_selected_service_retry_does_not_dispatch_other_services(sync_ui, monkeypatch):
    sync_ui.host.settings.setValue("sync_google_last_error", "operation_failed")
    sync_ui.coordinator.refresh()
    hub = CalendarSyncHub(sync_ui.host, section="issues")
    hub.issue_list.setCurrentRow(0)
    dispatch = Mock(return_value=["google"])
    monkeypatch.setattr(sync_ui.coordinator, "sync", dispatch)
    hub.retry_selected.click()
    dispatch.assert_called_once_with("google")
    for controller in sync_ui.coordinator.controllers().values():
        controller.start.assert_not_called()
    hub.close()


def test_subscription_controls_are_reachable_in_a_small_window_with_long_guidance(sync_ui):
    sync_ui.add_calendar("ics::small")
    hub = CalendarSyncHub(sync_ui.host, section="ics")
    hub.resize(640, 500)
    select_calendar(hub.ics_manager, "ics::small")
    hub.show()
    page = hub.ics_manager
    page.selection_info.setText("Translated instructions with longer calendar names. " * 20)
    sync_ui.qapp.processEvents()
    scroll = hub.findChild(QScrollArea, "SyncIcs")
    assert page.calendars.height() >= 120
    assert scroll.verticalScrollBar().maximum() > 0
    for action in (page.edit_subscription, page.service, page.remove):
        scroll.ensureWidgetVisible(action)
        sync_ui.qapp.processEvents()
        position = action.mapTo(scroll.viewport(), QPoint(0, 0))
        assert 0 <= position.y() < scroll.viewport().height()
        assert position.y() + action.height() <= scroll.viewport().height()
    sync_ui.host.settings.setValue("sync_google_last_error", "operation_failed")
    sync_ui.coordinator.refresh()
    hub.show_section("issues")
    hub.issue_detail.setText(
        "Translated recovery instructions for a failed calendar connection. " * 30
    )
    sync_ui.qapp.processEvents()
    assert hub.issue_scroll.verticalScrollBar().maximum() > 0
    for action in (hub.retry_selected, hub.resolve_selected):
        hub.issue_scroll.ensureWidgetVisible(action)
        sync_ui.qapp.processEvents()
        position = action.mapTo(hub.issue_scroll.viewport(), QPoint(0, 0))
        assert 0 <= position.y() < hub.issue_scroll.viewport().height()
        assert position.y() + action.height() <= hub.issue_scroll.viewport().height()
    hub.close()


def test_pasted_ics_address_is_validated_before_submit_and_never_claims_a_fetch(
    sync_ui, monkeypatch
):
    dialog = ics_form.IcsSubscriptionDialog(sync_ui.host)
    clipboard = SimpleNamespace(value="file:///private.ics")
    clipboard.text = lambda: clipboard.value
    monkeypatch.setattr(ics_form.QApplication, "clipboard", lambda: clipboard)
    dialog.name.setText("My holidays")
    dialog.paste_button.click()
    invalid_feedback = dialog.feedback.text()
    assert invalid_feedback
    assert dialog.feedback.property("validationState") == "invalid"
    assert not dialog.submit_button.isEnabled()
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    clipboard.value = "webcal://EXAMPLE.invalid:443/feed.ics?token=A%2FB#fragment"
    dialog.paste_button.click()
    assert dialog.feedback.property("validationState") == "valid"
    assert dialog.submit_button.isEnabled()
    assert dialog.feedback.text() != invalid_feedback
    assert dialog.name.text() == "My holidays"
    assert not sync_ui.host.settings.value("sync_ics_last_success")
    dialog.resize(640, 500)
    dialog.show()
    dialog.guide_toggle.click()
    sync_ui.qapp.processEvents()
    assert dialog.scroll_area.verticalScrollBar().maximum() > 0
    for action in (dialog.submit_button, dialog.cancel_button):
        position = action.mapTo(dialog, QPoint(0, 0))
        assert position.y() >= 0
        assert position.y() + action.height() <= dialog.height()
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.subscription_name == "My holidays"
    assert dialog.subscription_url == "https://example.invalid/feed.ics?token=A%2FB"
    assert not sync_ui.host.settings.value("sync_ics_last_success")
    dialog.close()


@pytest.mark.parametrize(
    "action,kind,operation",
    [
        ("add_local", "local", "upsert_calendar"),
        ("add_ics", "ics", "upsert_calendar"),
        ("rename", "local", "rename_calendar"),
        ("color", "gcal", "set_calendar_color"),
        ("default", "gcal", "set_calendar_default"),
        ("edit_subscription", "ics", "update_ics_subscription"),
        ("remove", "local", "delete_calendar"),
        ("remove", "ics", "delete_calendar"),
    ],
)
def test_manager_mouse_click_reaches_guarded_action(sync_ui, monkeypatch, action, kind, operation):
    """Exercise clicked(bool), rather than calling the Python handlers directly."""
    from PyQt6.QtGui import QColor

    key = "local::personal" if kind == "local" else "click::" + kind
    if kind != "local":
        sync_ui.add_calendar(key, kind=kind, role="owner" if kind == "gcal" else "reader")
    page = manager.CalendarManagerPage(sync_ui.host, sync_ui.coordinator, Mock())
    select_calendar(page, key)
    page._changed = Mock()
    saved = Mock(return_value=True)
    monkeypatch.setattr(manager.calendar_repo, operation, saved)
    monkeypatch.setattr(manager.calendar_repo, "get_calendar", Mock(return_value=None))
    monkeypatch.setattr(manager.QInputDialog, "getText", Mock(return_value=("Clicked", True)))
    monkeypatch.setattr(manager.QColorDialog, "getColor", Mock(return_value=QColor("#123456")))
    monkeypatch.setattr(
        manager.QMessageBox, "question", Mock(return_value=manager.QMessageBox.StandardButton.Yes)
    )
    sync_ui.coordinator.sync_ics = Mock(return_value=True)

    class AcceptedSubscription:
        DialogCode = QDialog.DialogCode
        subscription_name = "Clicked"
        subscription_url = "https://calendar.example.invalid/clicked.ics"

        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return self.DialogCode.Accepted

    monkeypatch.setattr(manager, "IcsSubscriptionDialog", AcceptedSubscription)
    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *error: errors.append(error))
    page.resize(1100, 900)
    page.show()
    sync_ui.qapp.processEvents()
    button = page.default_controls[key] if action == "default" else getattr(page, action)
    assert button.isVisible() and button.isEnabled()
    position = QPoint(10, button.height() // 2) if action == "default" else button.rect().center()
    QTest.mouseClick(button, Qt.MouseButton.LeftButton, pos=position)
    sync_ui.qapp.processEvents()
    assert not errors, [str(error[1]) for error in errors]
    saved.assert_called_once()
    page._changed.assert_called_once_with(True)
    if action not in {"add_local", "add_ics"}:
        assert saved.call_args.args[0] == key
    if action == "color":
        assert saved.call_args.args == (key, "#123456")
    if action == "rename":
        assert saved.call_args.args == (key, "Clicked")
    page.close()


@pytest.mark.parametrize("action", ["rename", "color", "default", "visible"])
def test_manager_mouse_changes_persist_and_reload(sync_ui, monkeypatch, action):
    from PyQt6.QtGui import QColor

    if action == "default":
        # The effective initial fallback is already checked; choose another row.
        sync_ui.add_calendar("local::secondary", kind="local", role="owner")
    connection = sqlite3.connect(sync_ui.path)
    monkeypatch.setattr(manager.calendar_repo.db_manager, "get_connection", lambda: connection)
    monkeypatch.setattr(manager.QInputDialog, "getText", lambda *args, **kwargs: ("Renamed", True))
    monkeypatch.setattr(manager.QColorDialog, "getColor", lambda *args, **kwargs: QColor("#123456"))
    hub = CalendarSyncHub(sync_ui.host)
    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *error: errors.append(error))
    hub.resize(1100, 900)
    hub.show()
    sync_ui.qapp.processEvents()
    page = hub.calendar_manager
    if action == "default":
        select_calendar(page, "local::secondary")
    button = (
        page.default_controls[page.current()["id"]]
        if action == "default"
        else getattr(page, action)
    )
    # Click the checkbox indicator; its full-width center may be outside its hit region.
    position = (
        QPoint(10, button.height() // 2)
        if action in {"visible", "default"}
        else button.rect().center()
    )
    QTest.mouseClick(button, Qt.MouseButton.LeftButton, pos=position)
    sync_ui.qapp.processEvents()
    assert not errors, [str(error[1]) for error in errors]
    row = page.current()
    expected = {
        "rename": ("name", "Renamed"),
        "color": ("color", "#123456"),
        "default": ("is_default", 1),
        "visible": ("is_visible", 0),
    }
    column, value = expected[action]
    assert row[column] == value
    assert (
        connection.execute(
            "SELECT " + column + " FROM calendar WHERE id=?", (row["id"],)
        ).fetchone()[0]
        == value
    )
    assert page.feedback.text()
    sync_ui.host.schedule_panel_refresh.assert_called_once_with(left=True, center=True, right=True)
    hub.close()
    connection.close()
