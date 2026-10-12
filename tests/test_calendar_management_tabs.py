# -*- coding: utf-8 -*-
"""Dedicated management tabs preserve scope, saved preferences and ICS recovery."""

import sqlite3
import sys
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QCheckBox, QDialog, QRadioButton, QScrollArea
import pytest

from calendar_app.presentation.dialogs import calendar_manager_page as manager
from calendar_app.presentation.dialogs.calendar_sync_hub import CalendarSyncHub
from calendar_app.presentation.main_window import calendar_sync_coordinator as sync_module
from tests.test_calendar_sync_redesign import select_calendar, sync_ui  # noqa: F401


@pytest.fixture
def tabs_ui(sync_ui, monkeypatch):
    """Keep repository writes and every potential worker inside the fixture DB."""
    connection = sqlite3.connect(sync_ui.path)
    connection.execute("ALTER TABLE calendar ADD COLUMN gcal_calendar_id TEXT")
    connection.execute("ALTER TABLE calendar ADD COLUMN sort_order INTEGER DEFAULT 0")
    connection.execute("UPDATE calendar SET is_default=1 WHERE id='local::personal'")
    connection.commit()
    monkeypatch.setattr(manager.calendar_repo.db_manager, "get_connection", lambda: connection)
    worker_start = Mock()
    monkeypatch.setattr(sync_module.IcsSyncWorker, "start", worker_start)
    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *error: errors.append(error))
    sync_ui.add_calendar("local::secondary", kind="local", role="owner")
    sync_ui.add_calendar("gcal::team", kind="gcal", role="owner")
    sync_ui.add_calendar("ics::one")
    sync_ui.add_calendar("ics::two", active=False)
    hubs = []

    def open_hub(section="calendars"):
        hub = CalendarSyncHub(sync_ui.host, section=section)
        hubs.append(hub)
        hub.resize(1100, 850)
        hub.show()
        sync_ui.qapp.processEvents()
        return hub

    yield SimpleNamespace(
        **vars(sync_ui),
        connection=connection,
        open_hub=open_hub,
        worker_start=worker_start,
        errors=errors,
    )
    for hub in hubs:
        hub.close()
        hub.deleteLater()
    sync_ui.qapp.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    connection.close()
    assert not errors, [str(error[1]) for error in errors]


def row_ids(page):
    return {
        page.calendars.item(index).data(Qt.ItemDataRole.UserRole)["id"]
        for index in range(page.calendars.count())
    }


def checked_defaults(page):
    return {identity for identity, button in page.default_controls.items() if button.isChecked()}


def reveal_and_click(ui, button):
    ancestor = button.parentWidget()
    while ancestor is not None and not isinstance(ancestor, QScrollArea):
        ancestor = ancestor.parentWidget()
    if ancestor is not None:
        ancestor.ensureWidgetVisible(button)
    ui.qapp.processEvents()
    assert button.isVisible() and button.isEnabled()
    point = (
        QPoint(10, button.height() // 2)
        if isinstance(button, (QCheckBox, QRadioButton))
        else button.rect().center()
    )
    QTest.mouseClick(button, Qt.MouseButton.LeftButton, pos=point)
    ui.qapp.processEvents()


@pytest.mark.parametrize(
    "section,index",
    [
        ("services", 0),
        ("calendars", 1),
        ("local", 2),
        ("ics", 3),
        ("issues", 4),
    ],
)
def test_public_sections_open_the_intended_management_tab(tabs_ui, section, index):
    hub = tabs_ui.open_hub(section)
    assert hub.tabs.count() == 5
    assert hub.tabs.currentIndex() == index
    expected = {
        "calendars": hub.calendar_manager,
        "local": hub.local_manager,
        "ics": hub.ics_manager,
    }
    if section in expected:
        assert hub.tabs.currentWidget().isAncestorOf(expected[section])


def test_overview_removes_add_actions_and_each_dedicated_page_has_one(tabs_ui):
    hub = tabs_ui.open_hub()
    assert hub.calendar_manager.add_local is None
    assert hub.calendar_manager.add_ics is None
    hub.tabs.setCurrentIndex(2)
    tabs_ui.qapp.processEvents()
    assert hub.local_manager.add_local.isVisible()
    assert hub.local_manager.add_ics is None
    hub.tabs.setCurrentIndex(3)
    tabs_ui.qapp.processEvents()
    assert hub.ics_manager.add_ics.isVisible()
    assert hub.ics_manager.add_local is None


@pytest.mark.parametrize(
    "identity,section,index",
    [
        ("local::secondary", "local", 2),
        ("ics::two", "ics", 3),
    ],
)
def test_overview_management_click_opens_selected_calendar_without_fetching(
    tabs_ui, identity, section, index
):
    hub = tabs_ui.open_hub()
    page = hub.calendar_manager
    select_calendar(page, identity)
    assert page.subscription_section.isHidden()
    assert page.appearance_section.isHidden()
    assert page.remove.isHidden()
    reveal_and_click(tabs_ui, page.service)
    assert hub.tabs.currentIndex() == index
    assert getattr(hub, section + "_manager").current()["id"] == identity
    tabs_ui.worker_start.assert_not_called()


@pytest.mark.parametrize(
    "scope,other,expected",
    [
        ("local", "ics", {"local::personal", "local::secondary"}),
        ("ics", "local", {"ics::one", "ics::two"}),
    ],
)
def test_fixed_scope_survives_search_and_hidden_provider_changes(tabs_ui, scope, other, expected):
    hub = tabs_ui.open_hub(scope)
    page = getattr(hub, scope + "_manager")
    assert page.provider_filter.isHidden()
    assert row_ids(page) == expected
    index = page.provider_filter.findData(other)
    if index < 0:
        page.provider_filter.addItem("Unexpected provider", other)
        index = page.provider_filter.count() - 1
    page.provider_filter.setCurrentIndex(index)
    tabs_ui.coordinator.refresh()
    assert row_ids(page) == expected
    page.search.setText("secondary" if scope == "local" else "two")
    assert row_ids(page) == {"local::secondary" if scope == "local" else "ics::two"}
    page.show_provider("google")
    assert row_ids(page) == expected
    assert not hub.ics_manager.default_controls["ics::one"].isEnabled()


def test_local_add_mouse_click_saves_selects_and_refreshes_overview(tabs_ui, monkeypatch):
    hub = tabs_ui.open_hub("local")
    page = hub.local_manager
    page.search.setText("no matching calendar")
    assert page.calendars.count() == 0
    monkeypatch.setattr(manager.QInputDialog, "getText", Mock(return_value=("New Local", True)))
    reveal_and_click(tabs_ui, page.add_local)
    identity = manager.calendar_repo.make_local_id("New Local")
    saved = tabs_ui.connection.execute(
        "SELECT type,name FROM calendar WHERE id=?", (identity,)
    ).fetchone()
    assert saved == ("local", "New Local")
    assert page.current()["id"] == identity
    assert identity in row_ids(hub.calendar_manager)
    assert identity not in row_ids(hub.ics_manager)
    assert checked_defaults(page) == {"local::personal"}
    tabs_ui.worker_start.assert_not_called()


def test_ics_add_mouse_click_saves_selects_and_starts_only_the_new_feed(tabs_ui, monkeypatch):
    hub = tabs_ui.open_hub("ics")
    page = hub.ics_manager

    class AcceptedSubscription:
        DialogCode = QDialog.DialogCode
        subscription_name = "New feed"
        subscription_url = "webcal://CALENDAR.example.invalid/new.ics?key=fixture-signature"

        def __init__(self, *_args, **_kwargs):
            pass

        def exec(self):
            return self.DialogCode.Accepted

    monkeypatch.setattr(manager, "IcsSubscriptionDialog", AcceptedSubscription)
    reveal_and_click(tabs_ui, page.add_ics)
    saved = tabs_ui.connection.execute(
        "SELECT id,ics_url FROM calendar WHERE name='New feed'"
    ).fetchone()
    assert saved is not None
    identity, url = saved
    assert url == "https://calendar.example.invalid/new.ics?key=fixture-signature"
    assert page.current()["id"] == identity
    assert identity in row_ids(hub.calendar_manager)
    assert identity not in row_ids(hub.local_manager)
    worker = tabs_ui.coordinator.ics_worker
    assert worker is not None
    assert [calendar["id"] for calendar in worker.calendars] == [identity]
    assert "fixture-signature" not in page.subscription_address.text()
    tabs_ui.worker_start.assert_called_once()


def test_default_and_visibility_changes_refresh_other_pages_without_switching_tabs(tabs_ui):
    hub = tabs_ui.open_hub("local")
    page = hub.local_manager
    selected = page.current()["id"]
    reveal_and_click(tabs_ui, page.default_controls["local::secondary"])
    assert hub.tabs.currentIndex() == 2
    assert page.current()["id"] == selected
    assert checked_defaults(page) == {"local::secondary"}
    assert checked_defaults(hub.calendar_manager) == {"local::secondary"}
    assert tabs_ui.connection.execute("SELECT id FROM calendar WHERE is_default=1").fetchall() == [
        ("local::secondary",)
    ]
    select_calendar(page, "local::secondary")
    reveal_and_click(tabs_ui, page.visible)
    select_calendar(hub.calendar_manager, "local::secondary")
    assert not hub.calendar_manager.visible.isChecked()
    assert not hub.calendar_manager.current()["is_visible"]
    assert checked_defaults(hub.calendar_manager) == {"local::secondary"}
    assert hub.tabs.currentIndex() == 2
    tabs_ui.host.schedule_panel_refresh.assert_called_with(left=True, center=True, right=True)


def test_failed_ics_navigation_uses_dedicated_page_and_resets_private_address(tabs_ui):
    private_url = "https://calendar.example.invalid/private.ics?key=fixture-private-key"
    tabs_ui.connection.execute("UPDATE calendar SET ics_url=? WHERE id='ics::one'", (private_url,))
    tabs_ui.connection.commit()
    tabs_ui.host.settings.setValue("sync_ics_error_codes", {"ics::one": "ics_access_denied"})
    tabs_ui.host.settings.setValue("sync_ics_failed_ids", ["ics::one"])
    tabs_ui.coordinator.refresh()
    hub = tabs_ui.open_hub("issues")
    for index in range(hub.issue_list.count()):
        item = hub.issue_list.item(index)
        if item.data(Qt.ItemDataRole.UserRole) == "ics":
            hub.issue_list.setCurrentItem(item)
            break
    reveal_and_click(tabs_ui, hub.resolve_selected)
    assert hub.tabs.currentIndex() == 3
    page = hub.ics_manager
    assert page.current()["id"] == "ics::one"
    assert "fixture-private-key" not in page.subscription_address.text()
    reveal_and_click(tabs_ui, page.reveal_subscription)
    assert private_url in page.subscription_address.text()
    select_calendar(page, "ics::two")
    select_calendar(page, "ics::one")
    assert not page.reveal_subscription.isChecked()
    assert "fixture-private-key" not in page.subscription_address.text()
    tabs_ui.worker_start.assert_not_called()


def test_busy_ics_disables_dedicated_add_until_worker_completion(tabs_ui):
    hub = tabs_ui.open_hub("ics")
    page = hub.ics_manager
    assert page.add_ics.isEnabled()
    assert tabs_ui.coordinator.sync_ics(force=True, calendar_ids=["ics::one"])
    worker = tabs_ui.coordinator.ics_worker
    assert worker is not None
    assert not page.add_ics.isEnabled()
    assert not page.edit_subscription.isEnabled()
    assert not page.remove.isEnabled()
    tabs_ui.coordinator._ics_result({"ics::one": (0, 0, None)})
    worker.finished.emit()
    tabs_ui.qapp.processEvents()
    assert page.add_ics.isEnabled()
    tabs_ui.worker_start.assert_called_once()
