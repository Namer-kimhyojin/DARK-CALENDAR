# -*- coding: utf-8 -*-
"""Common dispatch, independent status, calendar ownership and UI navigation."""

import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QObject, QSettings, pyqtSignal
from PyQt6.QtWidgets import QApplication, QLabel, QToolButton, QWidget
import pytest

from calendar_app.infrastructure.calendar_sync.repository import CalendarSyncRepository
from calendar_app.presentation.dialogs import calendar_manager_page as manager
from calendar_app.presentation.dialogs.calendar_sync_hub import CalendarSyncHub
from calendar_app.presentation.main_window import calendar_sync_coordinator as module
from calendar_app.presentation.main_window.calendar_sync_actions import CalendarSyncActionsMixin


class Controller(QObject):
    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.busy, self.status = False, "idle"
        self.start = Mock(side_effect=self._start)

    def _start(self, operation):
        self.busy = True
        self.changed.emit()
        return True


@pytest.fixture
def ui(tmp_path, monkeypatch):
    qapp = QApplication.instance() or QApplication([])
    host = QWidget()
    host.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    host.settings.setValue("gcal_enabled", "true")
    host.gcal_sync = SimpleNamespace(is_authenticated=True)
    host.sync_google_calendar = Mock()
    host.sync_google_calendar_silent = Mock()
    host.update_gcal_sync_timer = Mock()
    host.schedule_panel_refresh = Mock()
    host.open_calendar_sync_hub = Mock()
    host.open_gcal_settings_dialog = Mock()
    host.open_gcal_sync_issues_dialog = Mock()
    host._bg_workers = []
    host.sync_action_btn = QToolButton(host)
    host.sync_status_text_lbl = QLabel(host)
    host._outlook_sync_controller = Controller()
    host._caldav_sync_controllers = {k: Controller() for k in ("icloud", "naver")}
    for controller in [host._outlook_sync_controller, *host._caldav_sync_controllers.values()]:
        controller.sync = Mock()
    path = tmp_path / "calendar.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE calendar(id TEXT PRIMARY KEY,type TEXT,name TEXT,color TEXT,is_active INTEGER DEFAULT 1,
            access_role TEXT,is_visible INTEGER DEFAULT 1,is_default INTEGER DEFAULT 0,ics_url TEXT);
        CREATE TABLE unified_task(id INTEGER PRIMARY KEY,name TEXT,calendar_id TEXT,deadline TEXT,end_date TEXT,
            all_day INTEGER,description TEXT,location TEXT,type TEXT,gcal_dirty INTEGER,gcal_sync_mode TEXT,updated_at TEXT);
        INSERT INTO calendar(id,type,name,access_role) VALUES('local::fixture','local','Personal','owner');
    """)
    accounts, keys = {}, {}
    for service in ("outlook", "icloud", "naver"):
        accounts[service] = (
            "outlook::fixture" if service == "outlook" else "caldav::" + service + "::fixture"
        )
        prefix = "outlook_" if service == "outlook" else "caldav_" + service + "_"
        host.settings.setValue(prefix + "account_id", accounts[service])
        host.settings.setValue(prefix + "enabled", True)
        repo = CalendarSyncRepository(conn, "outlook" if service == "outlook" else "caldav")
        keys[service] = repo.register(
            accounts[service], {"id": service, "name": service, "can_edit": service != "naver"}
        )
    conn.close()

    def calendars():
        with sqlite3.connect(path) as database:
            database.row_factory = sqlite3.Row
            return [dict(row) for row in database.execute("SELECT * FROM calendar")]

    from calendar_app.infrastructure.db import task_repo

    for name in (
        "count_unified_task_gcal_errors",
        "count_gcal_delete_queue_errors",
        "count_gcal_sync_conflicts",
    ):
        monkeypatch.setattr(task_repo, name, lambda: 0)
    monkeypatch.setattr(module, "TOKEN_PATH", str(tmp_path / "absent-token"))
    coordinator = module.CalendarSyncCoordinator(host, str(path), calendars)
    host._calendar_sync_coordinator = coordinator
    yield SimpleNamespace(
        qapp=qapp, host=host, path=path, coordinator=coordinator, accounts=accounts, keys=keys
    )
    coordinator.stop()
    if coordinator.ics_worker:
        coordinator.ics_worker.wait(2000)
        qapp.processEvents()
    host.close()


def test_common_dispatch_uses_all_connected_selected_providers(ui):
    assert ui.coordinator.sync() == ["google", "outlook", "icloud", "naver"]
    ui.host.sync_google_calendar.assert_called_once_with(silent=True)
    for controller in ui.coordinator.controllers().values():
        controller.start.assert_called_once_with("sync")
    assert ui.coordinator.sync() == ["google"]  # remote workers already running


def test_one_provider_failure_does_not_block_others(ui):
    ui.host.sync_google_calendar.side_effect = RuntimeError("synthetic")
    assert ui.coordinator.sync() == ["outlook", "icloud", "naver"]
    assert ui.coordinator.states["google"]["error"] == "operation_failed"


def test_unselected_service_is_not_called_and_prompts_selection(ui):
    with sqlite3.connect(ui.path) as conn:
        conn.execute("UPDATE calendar SET is_active=0 WHERE id=?", (ui.keys["outlook"],))
    assert "outlook" not in ui.coordinator.sync()
    assert ui.coordinator.states["outlook"]["needs_selection"]
    ui.host._outlook_sync_controller.start.assert_not_called()


def test_auto_pause_keeps_manual_sync_available_and_accounts_intact(ui):
    ui.coordinator.set_auto("google", False)
    ui.coordinator.set_auto("icloud", False)
    ui.host.update_gcal_sync_timer.assert_called_once()
    assert not ui.coordinator.states["google"]["auto"]
    assert not ui.coordinator.states["icloud"]["auto"]
    assert ui.coordinator.sync("google") == ["google"]
    assert ui.coordinator.sync("icloud") == ["icloud"]
    assert ui.host.settings.value("caldav_icloud_account_id") == ui.accounts["icloud"]


def test_shutdown_and_invalid_provider_never_dispatch(ui):
    assert not ui.coordinator.sync("unknown")
    ui.host._is_shutting_down = True
    assert not ui.coordinator.sync()
    ui.host.sync_google_calendar.assert_not_called()


def test_google_stale_waiting_flag_does_not_hide_authenticated_connection(ui):
    ui.host._gcal_waiting_for_auth = True
    ui.coordinator.refresh()
    assert ui.coordinator.states["google"]["can_sync"]
    assert not ui.coordinator.states["google"]["error"]


def test_google_disabled_does_not_mask_icloud_status(ui):
    ui.host.settings.setValue("gcal_enabled", "false")
    ui.host.settings.setValue("sync_google_last_error", "operation_failed")
    ui.coordinator.refresh()
    assert not ui.coordinator.states["google"]["connected"]
    assert not ui.coordinator.states["google"]["error"]
    assert "iCloud" in ui.host.sync_action_btn.toolTip()
    assert ui.coordinator.states["icloud"]["can_sync"]


def test_issue_counts_and_service_labels_follow_account_ownership(ui):
    with sqlite3.connect(ui.path) as conn:
        conn.execute("INSERT INTO unified_task(id,name) VALUES(10,'Fixture')")
        conn.execute(
            "INSERT INTO calendar_sync_event(task_id,calendar_id,event_id,etag,baseline,transaction_id,remote_deleted) VALUES(10,?,'remote','v1','base','tx',0)",
            (ui.keys["icloud"],),
        )
        conn.execute("INSERT INTO calendar_sync_issue(task_id,kind) VALUES(10,'conflict')")
        conn.execute(
            "INSERT INTO calendar_sync_delete_queue(event_id,calendar_id,etag,attempts,error) VALUES('same-remote',?,'v2',1,'remote_http_403')",
            (ui.keys["naver"],),
        )
    ui.coordinator.refresh()
    assert ui.coordinator.states["icloud"]["issues"] == 1
    assert ui.coordinator.states["naver"]["issues"] == 1
    assert not ui.coordinator.states["outlook"]["issues"]
    assert ui.coordinator.calendar_providers[ui.keys["naver"]] == "naver"


def test_missing_metadata_retains_previous_issues(ui, monkeypatch):
    ui.coordinator.states["icloud"]["issues"] = 3
    monkeypatch.setattr(
        ui.coordinator, "_metadata", Mock(side_effect=sqlite3.OperationalError("busy"))
    )
    ui.coordinator.refresh()
    assert ui.coordinator.states["icloud"]["issues"] == 3
    assert ui.coordinator.states["icloud"]["selected"] == 1


def test_common_action_opens_hub_when_no_service_can_run(ui):
    ui.coordinator.sync = Mock(return_value=[])
    assert CalendarSyncActionsMixin.sync_calendars(ui.host) == []
    ui.host.open_calendar_sync_hub.assert_called_once()
    ui.host.open_calendar_sync_hub.reset_mock()
    ui.coordinator.states["icloud"]["busy"] = True
    CalendarSyncActionsMixin.sync_calendars(ui.host)
    ui.host.open_calendar_sync_hub.assert_not_called()


def test_common_action_does_not_open_settings_during_shutdown(ui):
    ui.host._is_shutting_down = True
    assert CalendarSyncActionsMixin.sync_calendars(ui.host) == []
    ui.host.open_calendar_sync_hub.assert_not_called()


def test_hub_tabs_selection_navigation_and_partial_errors(ui):
    ui.host._caldav_sync_controllers["naver"].status = "remote_http_403"
    ui.coordinator.refresh()
    hub = CalendarSyncHub(ui.host, "issues")
    assert hub.tabs.count() == 3 and hub.tabs.currentIndex() == 2
    assert hub.issue_list.count() == 1
    assert hub.sync_buttons["icloud"].isEnabled()
    hub._open("google", "calendars")
    ui.host.open_gcal_settings_dialog.assert_called_once_with(
        initial_tab="calendar", from_sync_hub=True
    )
    hub._open("google", "issues")
    ui.host.open_gcal_sync_issues_dialog.assert_called_once()
    hub._open("ics")
    assert hub.tabs.currentIndex() == 1
    hub.close()


def select_calendar(page, key):
    for index in range(page.calendars.count()):
        page.calendars.setCurrentRow(index)
        if page.current()["id"] == key:
            return
    raise AssertionError("Missing fixture calendar")


def test_calendar_manager_blocks_readonly_default_and_remote_removal(ui, monkeypatch):
    default, remove = Mock(), Mock()
    monkeypatch.setattr(manager.calendar_repo, "set_calendar_default", default)
    monkeypatch.setattr(manager.calendar_repo, "delete_calendar", remove)
    page = manager.CalendarManagerPage(ui.host, ui.coordinator, Mock())
    select_calendar(page, ui.keys["naver"])
    assert not page.default.isEnabled() and not page.remove.isEnabled()
    page._default()
    page._remove()
    default.assert_not_called()
    remove.assert_not_called()
    page.close()


def test_calendar_manager_routes_service_selection_using_caldav_account(ui):
    open_service = Mock()
    page = manager.CalendarManagerPage(ui.host, ui.coordinator, open_service)
    select_calendar(page, ui.keys["naver"])
    page.service.click()
    open_service.assert_called_once_with("naver", "calendars")
    page.close()


def test_ics_busy_blocks_subscription_deactivation_and_removal(ui, monkeypatch):
    with sqlite3.connect(ui.path) as conn:
        conn.execute(
            "INSERT INTO calendar(id,type,name,access_role,ics_url) VALUES('ics::fixture','ics','Holidays','reader','https://example.invalid/calendar.ics')"
        )
    ui.coordinator.refresh()
    ui.coordinator.states["ics"]["busy"] = True
    remove, active = Mock(), Mock()
    monkeypatch.setattr(manager.calendar_repo, "delete_calendar", remove)
    monkeypatch.setattr(manager.calendar_repo, "set_calendar_active", active)
    page = manager.CalendarManagerPage(ui.host, ui.coordinator, Mock())
    select_calendar(page, "ics::fixture")
    assert not page.remove.isEnabled() and not page.subscription_active.isEnabled()
    page._remove()
    page._subscription_active(False)
    remove.assert_not_called()
    active.assert_not_called()
    page.close()


def test_ics_worker_isolates_subscription_failure_and_closes_thread_db(ui, monkeypatch):
    from calendar_app.infrastructure.ics import ics_fetcher
    from calendar_app.shared import background_worker

    fetch = Mock(side_effect=[RuntimeError("synthetic"), (2, 0, None)])
    cleanup = Mock()
    monkeypatch.setattr(ics_fetcher, "fetch_and_sync", fetch)
    monkeypatch.setattr(background_worker, "_close_db_connection", cleanup)
    worker = module.IcsSyncWorker(
        [{"id": "a", "ics_url": "https://a.invalid"}, {"id": "b", "ics_url": "https://b.invalid"}],
        ui.host,
    )
    result = Mock()
    worker.result.connect(result)
    worker.run()
    assert fetch.call_count == 2
    assert result.call_args.args[0] == {"a": (0, 0, "operation_failed"), "b": (2, 0, None)}
    cleanup.assert_called_once()


def test_ics_failed_ids_have_no_raw_error_or_url_and_no_false_success(ui):
    ui.coordinator._ics_result({"a": (0, 0, "secret-raw-url"), "b": (1, 0, None)})
    assert ui.host.settings.value("sync_ics_failed_ids") == ["a"]
    assert ui.host.settings.value("sync_ics_last_error") == "ics_fetch_failed"
    assert ui.host.settings.value("sync_ics_issue_count", type=int) == 1
    assert not ui.host.settings.value("sync_ics_last_success")
    ui.host.schedule_panel_refresh.assert_called_once()


def test_mixin_mro_routes_common_status_and_ics_before_google():
    from calendar_app.presentation.main_window.action_handlers_gcal import GCalActionsMixin
    from calendar_app.presentation.main_window.app_window import OverlayApp

    assert OverlayApp.mro().index(CalendarSyncActionsMixin) < OverlayApp.mro().index(
        GCalActionsMixin
    )
    assert OverlayApp._sync_ics_calendars is CalendarSyncActionsMixin._sync_ics_calendars
    assert OverlayApp.update_sync_status is CalendarSyncActionsMixin.update_sync_status


def test_f5_and_existing_keydeck_command_target_common_dispatch():
    from calendar_app.infrastructure.runtime.keyboard_shortcuts import SHORTCUTS
    from calendar_app.presentation.widgets.overlay_launcher_deck import _COMMAND_HANDLERS

    assert next(row for row in SHORTCUTS if row["id"] == "sync_gcal")["action"] == "sync_calendars"
    assert _COMMAND_HANDLERS["sync_google"] == "sync_calendars"


def test_local_change_wakes_enabled_writable_services_without_google(ui):
    ui.host.settings.setValue("gcal_enabled", "false")
    ui.coordinator.sync_after_local_change()
    ui.host.sync_google_calendar_silent.assert_not_called()
    ui.host._outlook_sync_controller.sync.assert_called_once()
    ui.host._caldav_sync_controllers["icloud"].sync.assert_called_once()
    ui.host._caldav_sync_controllers["naver"].sync.assert_not_called()


def test_local_change_respects_pause_busy_and_backoff(ui):
    ui.coordinator.set_auto("google", False)
    ui.host._outlook_sync_controller.busy = True
    ui.host._caldav_sync_controllers["icloud"].status = "network_unavailable"
    ui.coordinator.sync_after_local_change()
    ui.host.sync_google_calendar_silent.assert_not_called()
    for controller in ui.coordinator.controllers().values():
        controller.sync.assert_not_called()


def test_multiple_local_edits_share_one_debounce_timer(ui):
    CalendarSyncActionsMixin.wake_gcal_sync(ui.host)
    timer = ui.coordinator.local_change_timer
    CalendarSyncActionsMixin.wake_gcal_sync(ui.host)
    assert timer is ui.coordinator.local_change_timer
    assert timer.isActive() and timer.isSingleShot() and timer.interval() == 800
    timer.stop()


def test_push_only_edits_wake_remote_services_without_full_google_sync(ui):
    CalendarSyncActionsMixin.wake_calendar_sync(ui.host)
    ui.coordinator.local_change_timer.stop()
    ui.coordinator._flush_local_change()
    ui.host.sync_google_calendar_silent.assert_not_called()
    ui.host._caldav_sync_controllers["icloud"].sync.assert_called_once()


def test_google_auto_pause_blocks_immediate_post_commit_queue(ui):
    from calendar_app.infrastructure.google_sync.push_queue import GcalPushQueue

    queue = GcalPushQueue()
    ui.host.settings.setValue("sync_google_auto", False)
    queue.enqueue(ui.host, {"id": 1, "name": "Fixture"})
    assert queue._thread is None and queue._queue.empty()


def test_old_palette_command_uses_common_sync(ui):
    from calendar_app.presentation.main_window.app_window import OverlayApp

    ui.host.sync_calendars = Mock()
    OverlayApp.handle_palette_command(ui.host, "sync_google", {})
    ui.host.sync_calendars.assert_called_once()


def test_ics_auto_pause_allows_explicit_sync_and_prevents_duplicate_worker(ui, monkeypatch):
    with sqlite3.connect(ui.path) as conn:
        conn.execute(
            "INSERT INTO calendar(id,type,name,access_role,ics_url) VALUES('ics::fixture','ics','Holidays','reader','https://example.invalid/calendar.ics')"
        )
    ui.host.settings.setValue("sync_ics_auto", False)
    monkeypatch.setattr(module.IcsSyncWorker, "start", lambda self: None)
    assert not ui.coordinator.sync_ics()
    assert ui.coordinator.sync_ics(force=True)
    assert not ui.coordinator.sync_ics(force=True)
    assert ui.coordinator.states["ics"]["busy"]


def test_shutdown_ics_result_does_not_report_partial_success(ui):
    ui.host._is_shutting_down = True
    ui.coordinator._ics_result({"first": (2, 0, None)})
    assert not ui.host.settings.value("sync_ics_last_success")
    ui.host.schedule_panel_refresh.assert_not_called()


def test_ics_issue_navigation_selects_failed_subscription(ui):
    with sqlite3.connect(ui.path) as conn:
        conn.execute(
            "INSERT INTO calendar(id,type,name,access_role,ics_url) VALUES('ics::fixture','ics','Holidays','reader','https://example.invalid/calendar.ics')"
        )
    ui.host.settings.setValue("sync_ics_failed_ids", ["ics::fixture"])
    ui.coordinator.refresh()
    hub = CalendarSyncHub(ui.host)
    hub._open("ics", "issues")
    assert hub.tabs.currentIndex() == 1
    assert hub.calendar_manager.current()["id"] == "ics::fixture"
    assert hub.calendar_manager.subscription_info.text()
    hub.close()
