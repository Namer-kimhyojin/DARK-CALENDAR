# -*- coding: utf-8 -*-
"""Common dispatch, independent status, calendar ownership and UI navigation."""

import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QObject, QPoint, QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QPalette
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLabel, QScrollArea, QToolButton, QVBoxLayout, QWidget
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


@pytest.mark.parametrize("theme,base", [("dark", "#0d1b2e"), ("light", "#fafafa")])
def test_toolbar_warning_style_clears_on_local_status_and_theme_refresh(
    ui, monkeypatch, theme, base
):
    from calendar_app.presentation.main_window.action_handlers_gcal import GCalActionsMixin
    from calendar_app.shared.icon_map import ICON

    ui.host.settings.setValue("text_theme", theme)
    ui.host.settings.setValue("panel_base_color", base)
    ui.host.sync_status_text_lbl.setStyleSheet("color: #ff9d4d; font-weight: bold;")
    capture = Mock(return_value=QIcon())
    monkeypatch.setattr(module, "icon", capture)
    for state in ui.coordinator.states.values():
        state.update(connected=False, busy=False, issues=0, error="")
    ui.coordinator.states["google"].update(connected=True, issues=1)
    ui.coordinator._paint_status()
    assert capture.call_args.args[0] == ICON.WARNING
    warning_color = capture.call_args.kwargs["color"]
    ui.coordinator.states["google"].update(connected=False, issues=0)
    ui.coordinator._paint_status()
    ui.host.sync_status_text_lbl.ensurePolished()
    assert capture.call_args.args[0] == ICON.SYNC_SETTINGS
    assert capture.call_args.kwargs["color"] != warning_color
    assert not ui.host.sync_status_text_lbl.font().bold()
    assert (
        ui.host.sync_status_text_lbl.palette().color(QPalette.ColorRole.WindowText).name()
        != "#ff9d4d"
    )
    before = ui.host.sync_status_text_lbl.styleSheet()
    refresh = Mock()
    monkeypatch.setattr(ui.coordinator, "refresh", refresh)
    ui.host.update_sync_status = lambda refresh_issue_count=True: (
        CalendarSyncActionsMixin.update_sync_status(ui.host, refresh_issue_count)
    )
    GCalActionsMixin.refresh_sync_status_theme(ui.host)
    refresh.assert_called_once_with(False)
    assert ui.host.sync_status_text_lbl.styleSheet() == before


def test_toolbar_hub_remains_open_after_sync_action(ui, monkeypatch):
    from calendar_app.presentation.main_window import top_bar_builder

    monkeypatch.setattr(top_bar_builder, "build_top_left_menus", lambda *args: None)
    monkeypatch.setattr(top_bar_builder, "apply_top_menu_theme", lambda *args, **kwargs: None)
    observations = []

    def open_hub(checked=False):
        hub = CalendarSyncHub(ui.host)

        def run_sync():
            hub._run_sync()
            observations.append(
                (hub.isVisible(), ui.host.top_bar_frame.isVisible(), bool(hub.sync_feedback.text()))
            )

        QTimer.singleShot(20, run_sync)
        QTimer.singleShot(80, hub.reject)
        hub.exec()

    ui.host.open_calendar_sync_hub = open_hub
    for name in (
        "toggle_lock_mode",
        "toggle_magnet_mode",
        "handle_search_changed",
        "toggle_widget_mode_panel",
    ):
        setattr(ui.host, name, Mock())
    top_bar_builder.setup_top_bar(ui.host, 10, "#4da6ff", lambda value: "#4da6ff")
    layout = QVBoxLayout(ui.host)
    layout.addWidget(ui.host.top_bar_frame)
    ui.host.resize(850, 150)
    ui.host.show()
    ui.qapp.processEvents()
    QTest.mouseClick(ui.host.sync_action_btn, Qt.MouseButton.LeftButton)
    assert observations == [(True, True, True)]
    ui.host.sync_google_calendar.assert_called_once_with(silent=True)
    for controller in ui.coordinator.controllers().values():
        controller.start.assert_called_once_with("sync")
    assert ui.host.top_bar_frame.isVisible()


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
    assert ui.coordinator.states["google"]["connected"]
    assert ui.coordinator.states["google"]["paused"]
    assert not ui.coordinator.states["google"]["can_sync"]
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
    assert hub.tabs.count() == 5 and hub.tabs.currentWidget() is hub.section_pages["issues"]
    assert hub.issue_list.count() == 1
    assert hub.sync_buttons["icloud"].isEnabled()
    hub._open("google", "calendars")
    ui.host.open_gcal_settings_dialog.assert_called_once_with(
        initial_tab="calendar", from_sync_hub=True
    )
    hub._open("google", "issues")
    ui.host.open_gcal_sync_issues_dialog.assert_called_once()
    hub._open("ics")
    assert hub.tabs.currentWidget() is hub.section_pages["ics"]
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
    assert not page.default_controls[ui.keys["naver"]].isEnabled() and not page.remove.isEnabled()
    page._default(ui.keys["naver"])
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
    assert not page.edit_subscription.isEnabled()
    page._remove()
    page._subscription_active(False)
    remove.assert_not_called()
    active.assert_not_called()
    page.close()


def test_ics_empty_card_explains_how_to_register_without_google(ui):
    hub = CalendarSyncHub(ui.host)
    assert "Google" in hub.labels["ics"].text()
    assert not hub.sync_buttons["ics"].isEnabled()
    hub.close()


def test_edit_subscription_dialog_prefills_and_validates(ui):
    from PyQt6.QtWidgets import QDialog

    from calendar_app.presentation.dialogs.ics_subscription_dialog import IcsSubscriptionDialog

    calendar = {"name": "Holidays", "ics_url": "https://example.invalid/old.ics"}
    dialog = IcsSubscriptionDialog(ui.host, calendar=calendar)
    assert dialog.name.text() == "Holidays"
    assert dialog.url.text() == calendar["ics_url"]
    dialog.url.setText("file:///invalid.ics")
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    dialog.url.setText("webcal://EXAMPLE.invalid:443/new.ics?key=A%2FB")
    dialog.accept()
    assert dialog.subscription_url == "https://example.invalid/new.ics?key=A%2FB"
    assert calendar["ics_url"] == "https://example.invalid/old.ics"
    dialog.close()


@pytest.mark.parametrize("active", [True, False])
def test_save_subscription_fetches_only_edited_active_calendar(ui, monkeypatch, active):
    with sqlite3.connect(ui.path) as conn:
        conn.execute("ALTER TABLE calendar ADD COLUMN ics_last_fetched TEXT")
        conn.execute(
            "INSERT INTO calendar(id,type,name,ics_url,is_active) VALUES('ics::fixture','ics','Holidays','https://example.invalid/old.ics',?)",
            (int(active),),
        )
    from calendar_app.infrastructure.db import database_unified

    conn = sqlite3.connect(ui.path)
    monkeypatch.setattr(database_unified.db_manager, "get_connection", lambda: conn)
    fetch = Mock(return_value=True)
    monkeypatch.setattr(ui.coordinator, "sync_ics", fetch)
    try:
        ui.coordinator.refresh()
        page = manager.CalendarManagerPage(ui.host, ui.coordinator, Mock())
        select_calendar(page, "ics::fixture")
        assert page.edit_subscription.isEnabled()
        assert page._save_subscription(page.current(), "Updated", "https://example.invalid/new.ics")
        assert page.current()["name"] == "Updated"
        assert page.current()["ics_url"] == "https://example.invalid/new.ics"
        assert page.current()["id"] == "ics::fixture"
        if active:
            fetch.assert_called_once_with(force=True, calendar_ids=["ics::fixture"])
        else:
            fetch.assert_not_called()
        page.close()
    finally:
        conn.close()


def test_edit_subscription_rejects_invalid_or_duplicate_url_in_ui(ui, monkeypatch):
    from calendar_app.application.calendar_sync_contract import CalendarSyncError

    page = manager.CalendarManagerPage(ui.host, ui.coordinator, Mock())
    calendar = {"id": "ics::fixture", "type": "ics"}
    save = Mock(side_effect=ValueError("invalid_subscription_url"))
    monkeypatch.setattr(manager.calendar_repo, "update_ics_subscription", save)
    assert not page._save_subscription(calendar, "Name", "file:///private")
    assert page.feedback.text()
    save.side_effect = CalendarSyncError("duplicate_subscription")
    assert not page._save_subscription(calendar, "Name", "https://example.invalid/feed.ics")
    assert page.feedback.text()
    ui.coordinator.states["ics"]["busy"] = True
    save.reset_mock()
    assert not page._save_subscription(calendar, "Name", "https://example.invalid/feed.ics")
    save.assert_not_called()
    register = Mock()
    monkeypatch.setattr(manager.calendar_repo, "upsert_calendar", register)
    assert not page._register_ics("Name", "https://example.invalid/feed.ics")
    register.assert_not_called()
    page.close()


def test_readding_original_url_does_not_overwrite_edited_subscription(ui, monkeypatch):
    url = "https://example.invalid/old.ics"
    key = manager.calendar_repo.make_ics_id(url)
    edited = {"id": key, "type": "ics", "ics_url": "https://example.invalid/new.ics"}
    monkeypatch.setattr(manager.calendar_repo, "list_calendars", lambda **k: [edited])
    monkeypatch.setattr(
        manager.calendar_repo, "get_calendar", lambda k: edited if k == key else None
    )
    save = Mock(return_value=True)
    monkeypatch.setattr(manager.calendar_repo, "upsert_calendar", save)
    monkeypatch.setattr(ui.coordinator, "sync_ics", Mock(return_value=True))
    page = manager.CalendarManagerPage(ui.host, ui.coordinator, Mock())
    assert page._register_ics("Original URL", url)
    assert save.call_args.args[0] != key
    assert save.call_args.kwargs["ics_url"] == url
    page.close()


def test_ics_http_diagnostic_survives_settings_roundtrip_and_targeted_retry(ui):
    ui.coordinator._ics_result({"a": (0, 0, "ics_access_denied"), "b": (0, 0, "ics_not_found")})
    assert ui.host.settings.value("sync_ics_error_codes") == {
        "a": "ics_access_denied",
        "b": "ics_not_found",
    }
    ui.coordinator._ics_result({"a": (1, 0, None)})
    assert ui.host.settings.value("sync_ics_error_codes") == {"b": "ics_not_found"}


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


def test_targeted_ics_retry_keeps_other_subscription_errors(ui):
    ui.host.settings.setValue(
        "sync_ics_error_codes", {"a": "network_unavailable", "b": "invalid_calendar_data"}
    )
    ui.coordinator._ics_result({"a": (1, 0, None)})
    assert ui.host.settings.value("sync_ics_error_codes") == {"b": "invalid_calendar_data"}
    assert ui.host.settings.value("sync_ics_failed_ids") == ["b"]
    assert not ui.host.settings.value("sync_ics_last_success")


def test_selected_ics_refresh_does_not_fetch_other_subscriptions(ui, monkeypatch):
    with sqlite3.connect(ui.path) as conn:
        conn.executemany(
            "INSERT INTO calendar(id,type,name,ics_url) VALUES(?,'ics',?,?)",
            [
                ("ics::a", "A", "https://a.invalid/feed.ics"),
                ("ics::b", "B", "https://b.invalid/feed.ics"),
            ],
        )
    monkeypatch.setattr(module.IcsSyncWorker, "start", lambda self: None)
    assert ui.coordinator.sync_ics(force=True, calendar_ids=["ics::b"])
    assert [c["id"] for c in ui.coordinator.ics_worker.calendars] == ["ics::b"]


def test_ics_cancellation_before_start_never_fetches(ui, monkeypatch):
    from calendar_app.infrastructure.ics import ics_fetcher

    fetch = Mock()
    monkeypatch.setattr(ics_fetcher, "fetch_and_sync", fetch)
    worker = module.IcsSyncWorker([{"id": "a", "ics_url": "https://a.invalid"}], ui.host)
    worker.requestInterruption()
    worker.run()
    fetch.assert_not_called()
    assert worker.is_cancelled()


def test_calendar_metadata_change_refreshes_ui_without_status_change(ui):
    changed = Mock()
    ui.coordinator.changed.connect(changed)
    with sqlite3.connect(ui.path) as conn:
        conn.execute("UPDATE calendar SET name='Renamed' WHERE type='local'")
    ui.coordinator.refresh()
    changed.assert_called_once()
    assert any(c["name"] == "Renamed" for c in ui.coordinator.calendar_rows)


def test_calendar_controls_remain_reachable_in_small_window_with_long_copy(ui):
    hub = CalendarSyncHub(ui.host, section="local")
    hub.resize(640, 500)
    hub.show()
    page = hub.local_manager
    page.selection_info.setText("A longer translated calendar description. " * 25)
    ui.qapp.processEvents()
    scroll = hub.findChild(QScrollArea, "SyncLocal")
    assert page.calendars.height() >= 120
    assert scroll.verticalScrollBar().maximum() > 0
    scroll.ensureWidgetVisible(page.remove)
    ui.qapp.processEvents()
    position = page.remove.mapTo(scroll.viewport(), QPoint(0, 0))
    assert 0 <= position.y() < scroll.viewport().height()
    assert position.y() + page.remove.height() <= scroll.viewport().height()
    hub.close()


def test_manager_duplicate_webcal_url_preserves_existing_subscription(ui, monkeypatch):
    existing = [
        {"id": "ics::original", "type": "ics", "ics_url": "https://EXAMPLE.invalid:443/feed.ics"}
    ]
    monkeypatch.setattr(manager.calendar_repo, "list_calendars", lambda **kwargs: existing)
    save = Mock()
    monkeypatch.setattr(manager.calendar_repo, "upsert_calendar", save)
    page = manager.CalendarManagerPage(ui.host, ui.coordinator, Mock())
    assert not page._register_ics("Duplicate", "webcal://example.invalid/feed.ics#fragment")
    save.assert_not_called()
    page.close()


def test_calendar_database_failure_restores_toggle_and_shows_recovery(ui, monkeypatch):
    def fail(*args):
        raise sqlite3.OperationalError("locked")

    monkeypatch.setattr(manager.calendar_repo, "set_calendar_visible", fail)
    page = manager.CalendarManagerPage(ui.host, ui.coordinator, Mock())
    select_calendar(page, "local::fixture")
    page.visible.click()
    assert page.visible.isChecked()
    assert page.feedback.text()
    ui.host.schedule_panel_refresh.assert_not_called()
    page.close()


def test_removed_or_paused_subscription_error_does_not_mark_toolbar_failed(ui):
    with sqlite3.connect(ui.path) as conn:
        conn.execute(
            "INSERT INTO calendar(id,type,name,is_active,ics_url) VALUES('ics::paused','ics','Paused',0,'https://a.invalid')"
        )
    ui.host.settings.setValue("sync_ics_failed_ids", ["ics::paused", "ics::removed"])
    ui.host.settings.setValue("sync_ics_last_error", "ics_fetch_failed")
    ui.coordinator.refresh()
    assert ui.coordinator.states["ics"]["issues"] == 0
    assert not ui.coordinator.states["ics"]["error"]


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
    assert hub.tabs.currentWidget() is hub.section_pages["ics"]
    assert hub.ics_manager.current()["id"] == "ics::fixture"
    assert hub.ics_manager.subscription_info.text()
    hub.close()
