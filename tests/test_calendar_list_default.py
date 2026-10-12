# -*- coding: utf-8 -*-
"""List radios persist new-event defaults without changing selection or ownership."""

import sqlite3
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QPoint, QSettings, Qt, pyqtSignal
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QComboBox, QRadioButton, QWidget
import pytest

from calendar_app.application import calendar_preferences
from calendar_app.infrastructure.db import calendar_repo, database_unified, task_repo
from calendar_app.presentation.dialogs import calendar_manager_page as manager
from calendar_app.presentation.dialogs.task_dialog_unified import UnifiedTaskDialog


class DatabaseSnapshotCoordinator(QObject):
    """Use the real unified repository while keeping external workers absent."""

    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.states = {"ics": {"busy": False}}
        self.refresh()

    def refresh(self):
        self.calendar_rows = calendar_repo.list_calendars(include_inactive=True)
        self.calendar_providers = {
            row["id"]: {"gcal": "google", "outlook": "outlook", "ics": "ics", "caldav": "naver"}[
                row["type"]
            ]
            for row in self.calendar_rows
            if row["type"] in {"gcal", "outlook", "ics", "caldav"}
        }
        self.changed.emit()


@pytest.fixture
def list_ui(tmp_path, monkeypatch):
    qapp = QApplication.instance() or QApplication([])
    database_unified.db_manager.close_all_connections()
    previous_path = database_unified.DB_PATH
    monkeypatch.setattr(database_unified, "DB_PATH", str(tmp_path / "calendar.db"))
    database_unified.initialize_unified_database()
    connection = calendar_repo.db_manager.get_connection()
    connection.execute("DELETE FROM calendar")
    connection.commit()
    for order, (identity, kind, active, visible, role) in enumerate(
        (
            ("local::personal", "local", True, True, None),
            ("local::secondary", "local", True, True, None),
            ("gcal::team@example.test", "gcal", True, False, "owner"),
            ("gcal::holidays", "gcal", True, True, "reader"),
            ("gcal::paused", "gcal", False, True, "writer"),
            ("ics::feed", "ics", True, True, None),
            ("outlook::work", "outlook", True, True, "writer"),
            ("outlook::paused", "outlook", False, True, "writer"),
            ("caldav::naver", "caldav", True, True, "reader"),
        )
    ):
        assert calendar_repo.upsert_calendar(
            identity,
            kind,
            identity,
            color="#5294f7",
            sort_order=order,
            is_active=active,
            is_visible=visible,
            access_role=role,
            is_default=identity == "local::personal",
            gcal_calendar_id=identity.split("::", 1)[1] if kind == "gcal" else None,
        )
    host = QWidget()
    host.settings = QSettings(str(tmp_path / "preferences.ini"), QSettings.Format.IniFormat)
    host.settings.setValue("gcal_calendar_id", "old@example.test")
    host.settings.setValue("gcal_primary_resolved_id", "owner@example.test")
    host.schedule_panel_refresh = Mock()
    host.refresh_gcal_sync_state = Mock()
    coordinator = DatabaseSnapshotCoordinator()
    page = manager.CalendarManagerPage(host, coordinator, Mock())
    coordinator.changed.connect(page.reload)
    page.resize(1100, 780)
    page.show()
    qapp.processEvents()
    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *error: errors.append(error))
    yield SimpleNamespace(
        qapp=qapp,
        host=host,
        coordinator=coordinator,
        page=page,
        connection=connection,
        path=tmp_path,
        errors=errors,
    )
    page.close()
    page.deleteLater()
    host.close()
    host.deleteLater()
    qapp.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    database_unified.db_manager.close_all_connections()
    monkeypatch.setattr(database_unified, "DB_PATH", previous_path)
    assert not errors, [str(error[1]) for error in errors]


def checked_ids(page):
    return {identity for identity, button in page.default_controls.items() if button.isChecked()}


def saved_default_ids(ui):
    return {row[0] for row in ui.connection.execute("SELECT id FROM calendar WHERE is_default=1")}


def item_for(page, identity):
    for index in range(page.calendars.count()):
        item = page.calendars.item(index)
        if item.data(Qt.ItemDataRole.UserRole)["id"] == identity:
            return item
    raise AssertionError("Missing fixture calendar: " + identity)


def click_default(ui, identity):
    page = ui.page
    page.calendars.scrollToItem(item_for(page, identity))
    ui.qapp.processEvents()
    button = page.default_controls[identity]
    assert button.isVisible()
    QTest.mouseClick(button, Qt.MouseButton.LeftButton, pos=QPoint(10, button.height() // 2))
    ui.qapp.processEvents()


def test_default_controls_are_only_list_radios(list_ui):
    page = list_ui.page
    assert len(page.default_controls) == page.calendars.count()
    assert all(isinstance(button, QRadioButton) for button in page.default_controls.values())
    assert not hasattr(page, "quick_controls")
    assert not hasattr(page, "default")
    assert page.findChild(QComboBox, "calendar_default_selector") is None
    assert checked_ids(page) == {"local::personal"}


def test_mouse_choice_is_unique_and_persists_google_compatibility_ini(list_ui):
    page = list_ui.page
    selected = page.current()["id"]
    click_default(list_ui, "gcal::team@example.test")
    assert saved_default_ids(list_ui) == {"gcal::team@example.test"}
    assert checked_ids(page) == {"gcal::team@example.test"}
    assert page.current()["id"] == selected
    list_ui.host.settings.sync()
    reopened = QSettings(str(list_ui.path / "preferences.ini"), QSettings.Format.IniFormat)
    assert reopened.value("gcal_calendar_id") == "team@example.test"
    assert reopened.value("gcal_primary_resolved_id") == "owner@example.test"
    list_ui.host.refresh_gcal_sync_state.assert_called_once_with(authenticate_silently=False)
    list_ui.host.schedule_panel_refresh.assert_called_once_with(left=True, center=True, right=True)
    assert "gcal::team@example.test" in page.feedback.text()


def test_clicking_current_default_does_not_write_again(list_ui):
    with patch.object(calendar_preferences, "set_default_calendar") as save:
        click_default(list_ui, "local::personal")
    save.assert_not_called()
    assert checked_ids(list_ui.page) == {"local::personal"}
    assert saved_default_ids(list_ui) == {"local::personal"}
    list_ui.host.schedule_panel_refresh.assert_not_called()


def test_space_sets_default_and_keeps_keyboard_focus_on_the_row_radio(list_ui):
    page = list_ui.page
    identity = "local::secondary"
    page.calendars.scrollToItem(item_for(page, identity))
    button = page.default_controls[identity]
    button.setFocus(Qt.FocusReason.OtherFocusReason)
    list_ui.qapp.processEvents()
    assert button.hasFocus()
    QTest.keyClick(button, Qt.Key.Key_Space)
    list_ui.qapp.processEvents()
    assert checked_ids(page) == {identity}
    assert saved_default_ids(list_ui) == {identity}
    assert page.default_controls[identity].hasFocus()
    assert page.current()["id"] == "local::personal"


def test_missing_default_uses_same_writable_fallback_without_implicit_write(list_ui):
    list_ui.connection.execute("UPDATE calendar SET is_default=0")
    list_ui.connection.commit()
    list_ui.coordinator.refresh()
    expected = calendar_repo.get_default_calendar()["id"]
    assert checked_ids(list_ui.page) == {expected}
    with patch.object(calendar_preferences, "set_default_calendar") as save:
        click_default(list_ui, expected)
    save.assert_not_called()
    assert saved_default_ids(list_ui) == set()


def test_switching_between_writable_providers_keeps_exactly_one_default(list_ui):
    for identity in ("gcal::team@example.test", "outlook::work", "local::secondary"):
        click_default(list_ui, identity)
        assert checked_ids(list_ui.page) == {identity}
        assert saved_default_ids(list_ui) == {identity}
    assert list_ui.host.settings.value("gcal_calendar_id") == "team@example.test"
    assert calendar_repo.get_default_calendar()["id"] == "local::secondary"


@pytest.mark.parametrize(
    "failure", [False, sqlite3.OperationalError("locked")], ids=["false", "database_error"]
)
def test_failed_choice_restores_previous_radio_and_keeps_detail_selection(list_ui, failure):
    page = list_ui.page
    page.calendars.setCurrentItem(item_for(page, "outlook::work"))
    before_title = page.detail_title.text()
    with patch.object(
        calendar_preferences,
        "set_default_calendar",
        **(
            {"side_effect": failure}
            if isinstance(failure, Exception)
            else {"return_value": failure}
        ),
    ):
        click_default(list_ui, "local::secondary")
    assert checked_ids(page) == {"local::personal"}
    assert saved_default_ids(list_ui) == {"local::personal"}
    assert page.current()["id"] == "outlook::work"
    assert page.detail_title.text() == before_title
    assert page.feedback.text()
    assert list_ui.host.settings.value("gcal_calendar_id") == "old@example.test"
    list_ui.host.schedule_panel_refresh.assert_not_called()
    list_ui.host.refresh_gcal_sync_state.assert_not_called()


@pytest.mark.parametrize(
    "identity",
    [
        "gcal::holidays",
        "gcal::paused",
        "ics::feed",
        "outlook::paused",
        "caldav::naver",
    ],
)
def test_readonly_or_unselected_rows_cannot_become_default(list_ui, identity):
    page = list_ui.page
    radio = page.default_controls[identity]
    assert not radio.isEnabled()
    assert radio.toolTip()
    assert radio.accessibleDescription()
    with patch.object(calendar_preferences, "set_default_calendar") as save:
        click_default(list_ui, identity)
        assert page._default(identity) is False
    save.assert_not_called()
    assert checked_ids(page) == {"local::personal"}
    assert saved_default_ids(list_ui) == {"local::personal"}


def test_missing_id_and_empty_list_do_not_reset_the_default(list_ui):
    page = list_ui.page
    with patch.object(calendar_preferences, "set_default_calendar") as save:
        assert page._default("local::missing") is False
        page.search.setText("no matching calendar")
        assert page.current() is None
        assert page.default_controls == {}
        assert page._default() is False
    save.assert_not_called()
    assert saved_default_ids(list_ui) == {"local::personal"}
    page.search.clear()
    assert checked_ids(page) == {"local::personal"}


def test_hidden_default_is_allowed_and_keeps_display_off(list_ui):
    assert list_ui.page.default_controls["gcal::team@example.test"].isEnabled()
    click_default(list_ui, "gcal::team@example.test")
    row = calendar_repo.get_calendar("gcal::team@example.test")
    assert row["is_default"] == 1
    assert row["is_visible"] == 0
    assert row["is_active"] == 1


def test_filter_never_relabels_another_row_as_the_default(list_ui):
    page = list_ui.page
    click_default(list_ui, "gcal::team@example.test")
    page.search.setText("local::secondary")
    assert set(page.default_controls) == {"local::secondary"}
    assert checked_ids(page) == set()
    page.provider_filter.setCurrentIndex(page.provider_filter.findData("local"))
    page.search.clear()
    assert checked_ids(page) == set()
    page.provider_filter.setCurrentIndex(0)
    assert checked_ids(page) == {"gcal::team@example.test"}
    assert saved_default_ids(list_ui) == {"gcal::team@example.test"}


def test_radio_click_preserves_search_scroll_and_another_detail_selection(list_ui):
    for index in range(28):
        assert calendar_repo.upsert_calendar(
            f"local::extra-{index:02d}",
            "local",
            f"local::extra-{index:02d}",
            sort_order=20 + index,
        )
    list_ui.coordinator.refresh()
    page = list_ui.page
    page.provider_filter.setCurrentIndex(page.provider_filter.findData("local"))
    page.search.setText("local::")
    page.calendars.setCurrentItem(item_for(page, "local::personal"))
    page.calendars.scrollToItem(item_for(page, "local::extra-17"))
    list_ui.qapp.processEvents()
    scrollbar = page.calendars.verticalScrollBar()
    assert scrollbar.value() > 0
    before_scroll = scrollbar.value()
    before_detail = page.detail_title.text()
    before_radio = page.default_controls["local::extra-17"]
    QTest.mouseClick(
        before_radio, Qt.MouseButton.LeftButton, pos=QPoint(10, before_radio.height() // 2)
    )
    list_ui.qapp.processEvents()
    assert saved_default_ids(list_ui) == {"local::extra-17"}
    assert checked_ids(page) == {"local::extra-17"}
    assert page.current()["id"] == "local::personal"
    assert page.detail_title.text() == before_detail
    assert page.search.text() == "local::"
    assert page.provider_filter.currentData() == "local"
    assert scrollbar.value() == before_scroll


def test_repeated_status_refresh_preserves_controls_and_selected_detail(list_ui):
    page = list_ui.page
    page.calendars.setCurrentItem(item_for(page, "gcal::holidays"))
    controls = dict(page.default_controls)
    before_detail = page.detail_title.text()
    list_ui.coordinator.refresh()
    list_ui.coordinator.refresh()
    assert all(page.default_controls[key] is value for key, value in controls.items())
    assert page.detail_title.text() == before_detail
    assert page.current()["id"] == "gcal::holidays"
    assert checked_ids(page) == {"local::personal"}


def test_live_permission_loss_rejects_stale_enabled_radio(list_ui):
    list_ui.connection.execute("UPDATE calendar SET access_role='reader' WHERE id='outlook::work'")
    list_ui.connection.commit()
    assert list_ui.page.default_controls["outlook::work"].isEnabled()
    click_default(list_ui, "outlook::work")
    assert saved_default_ids(list_ui) == {"local::personal"}
    assert checked_ids(list_ui.page) == {"local::personal"}
    assert list_ui.page.feedback.text()
    list_ui.host.schedule_panel_refresh.assert_not_called()


def test_no_writable_candidate_has_no_checked_default(list_ui):
    list_ui.connection.execute("UPDATE calendar SET is_active=0")
    list_ui.connection.commit()
    list_ui.coordinator.refresh()
    assert calendar_repo.get_default_calendar() is None
    assert checked_ids(list_ui.page) == set()
    assert all(not button.isEnabled() for button in list_ui.page.default_controls.values())


def test_new_task_initial_calendar_uses_the_list_choice(list_ui):
    click_default(list_ui, "gcal::team@example.test")
    dialog = UnifiedTaskDialog(list_ui.host, initial_date="2026-10-07", task_type="schedule")
    try:
        assert dialog._get_selected_calendar_id() == "gcal::team@example.test"
        assert dialog._build_task_payload()["calendar_id"] == "gcal::team@example.test"
    finally:
        dialog.reject()
        dialog.deleteLater()


def test_existing_task_owner_and_pending_deletion_survive_default_change(list_ui):
    identity = task_repo.create_unified_task(
        {
            "name": "Existing owned event",
            "type": "schedule",
            "priority": "normal",
            "status": "pending",
            "deadline": "2026-10-07",
            "end_date": "2026-10-07",
            "calendar_id": "local::personal",
            "gcal_source_calendar_id": "old@example.test",
            "gcal_event_id": "existing",
            "gcal_sync_mode": "local_owned",
        }
    )
    before = task_repo.get_unified_task(identity)
    list_ui.connection.execute(
        "INSERT INTO gcal_delete_queue(gcal_event_id,gcal_calendar_id) VALUES('pending-delete','old@example.test')",
    )
    list_ui.connection.commit()
    queue_before = [
        tuple(row) for row in list_ui.connection.execute("SELECT * FROM gcal_delete_queue")
    ]
    click_default(list_ui, "gcal::team@example.test")
    assert task_repo.get_unified_task(identity) == before
    assert [
        tuple(row) for row in list_ui.connection.execute("SELECT * FROM gcal_delete_queue")
    ] == queue_before
    dialog = UnifiedTaskDialog(list_ui.host, task_id=identity)
    try:
        assert dialog._get_selected_calendar_id() == "local::personal"
        assert dialog._build_task_payload()["calendar_id"] == "local::personal"
    finally:
        dialog.reject()
        dialog.deleteLater()
