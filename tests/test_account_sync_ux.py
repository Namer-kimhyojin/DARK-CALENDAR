# -*- coding: utf-8 -*-
"""State transitions and real click paths for account recovery and sync feedback."""

from types import MethodType
from unittest.mock import Mock

from PyQt6.QtCore import Qt, QTimer
import pytest

from calendar_app.presentation.dialogs.calendar_sync_hub import CalendarSyncHub
from calendar_app.presentation.dialogs.sync_recovery import sync_recovery_action
from calendar_app.presentation.main_window.action_handlers_gcal import GCalActionsMixin
from tests.test_calendar_sync_coordinator import ui  # noqa: F401
from tests.test_calendar_sync_redesign import sync_ui  # noqa: F401


@pytest.fixture
def google_runtime(sync_ui, monkeypatch):
    host = sync_ui.host
    for name in (
        "refresh_gcal_sync_state",
        "refresh_gcal_sync_state_internal",
        "update_gcal_sync_timer",
        "_effective_quick_sync_interval_ms",
        "_auth_worker_running",
        "_sync_worker_running",
        "set_gcal_sync_enabled",
        "sync_google_calendar_silent",
        "sync_google_calendar",
        "_manual_sync_setup_state",
        "_silent_sync_waiting_for_auth",
        "_on_auth_finished",
        "_release_auth_worker",
    ):
        setattr(host, name, MethodType(getattr(GCalActionsMixin, name), host))
    host.gcal_sync_timer = QTimer(host)
    host.gcal_quick_sync_timer = QTimer(host)
    host.update_sync_status = Mock()
    host._auth_worker = None
    host._sync_worker = None
    host.gcal_sync.service = object()
    host.gcal_sync._normalize_calendar_id = lambda value: value
    monkeypatch.setattr(
        "calendar_app.infrastructure.google_sync.common.get_default_gcal_calendar_id",
        lambda settings: "primary",
    )
    yield host
    host.settings.setValue("gcal_enabled", False)
    host.gcal_sync_timer.stop()
    host.gcal_quick_sync_timer.stop()


@pytest.mark.parametrize(
    "value, minutes, seconds",
    [
        (None, 10, 30),
        ("broken", 10, 30),
        ("", 10, 30),
        ([], 10, 30),
        (10**20, 240, 300),
        (-5, 0, 5),
        (0, 0, 5),
        ("15", 15, 15),
    ],
)
def test_corrupt_or_extreme_sync_intervals_keep_runtime_timers_safe(
    google_runtime, value, minutes, seconds
):
    host = google_runtime
    host.settings.setValue("gcal_sync_interval", value)
    host.settings.setValue("gcal_quick_sync_interval", value)
    host.update_gcal_sync_timer()
    assert host._gcal_quick_interval_secs == seconds
    assert host.gcal_sync_timer.isActive() == (minutes > 0)
    assert host.gcal_quick_sync_timer.isActive() == (minutes > 0)
    if minutes:
        assert host.gcal_sync_timer.interval() == minutes * 60000
        assert host.gcal_quick_sync_timer.interval() == seconds * 1000
    host.settings.setValue("gcal_enabled", False)
    host.update_gcal_sync_timer()
    assert not host.gcal_sync_timer.isActive() and not host.gcal_quick_sync_timer.isActive()


def test_resume_existing_connection_restarts_timers_without_an_auth_job(
    google_runtime, monkeypatch
):
    host = google_runtime
    service = host.gcal_sync.service
    worker = Mock()
    schedule = Mock()
    monkeypatch.setattr("calendar_app.shared.background_worker.AuthWorker", worker)
    monkeypatch.setattr(QTimer, "singleShot", schedule)
    host.set_gcal_sync_enabled(False, show_message=False)
    assert not host.gcal_sync_timer.isActive() and not host.gcal_quick_sync_timer.isActive()
    host.set_gcal_sync_enabled(True, show_message=False)
    assert host.gcal_sync_timer.isActive() and host.gcal_quick_sync_timer.isActive()
    assert host.gcal_sync.service is service and host.gcal_sync.is_authenticated
    worker.assert_not_called()
    schedule.assert_called_once_with(300, host.sync_google_calendar_silent)


@pytest.mark.parametrize("success", [False, True])
def test_slow_auth_is_not_announced_as_success_and_blocks_overlapping_sync(
    google_runtime, monkeypatch, success
):
    host = google_runtime
    connection = host.gcal_sync
    host.gcal_sync = None
    worker = Mock()
    worker.isRunning.return_value = True
    auth = Mock(return_value=worker)
    sync = Mock()
    messages = []
    monkeypatch.setattr("calendar_app.shared.background_worker.AuthWorker", auth)
    monkeypatch.setattr("calendar_app.shared.background_worker.SyncWorker", sync)
    monkeypatch.setattr(
        "calendar_app.presentation.main_window.action_handlers_gcal.os.path.exists",
        lambda path: True,
    )
    monkeypatch.setattr(
        "calendar_app.presentation.main_window.action_handlers_gcal.QMessageBox.information",
        lambda parent, title, text: messages.append(text),
    )
    host.set_gcal_sync_enabled(True)
    auth.assert_called_once_with(host)
    assert len(messages) == 1 and "인증" in messages[0]
    host.sync_google_calendar_silent()
    assert not host.sync_google_calendar(silent=True)
    sync.assert_not_called()
    auth.assert_called_once()
    # Completion restores automatic timers even though AuthWorker used update_ui=False.
    host.gcal_sync_timer.stop()
    host.gcal_quick_sync_timer.stop()
    worker.isRunning.return_value = False
    if success:
        host.gcal_sync = connection
    host._on_auth_finished(success, "synthetic")
    assert host.gcal_sync_timer.isActive() and host.gcal_quick_sync_timer.isActive()
    assert host.gcal_sync is (connection if success else None)
    status_updates = host.update_sync_status.call_count
    host._release_auth_worker()
    assert host._auth_worker is None
    assert host.update_sync_status.call_count == status_updates + 1
    if success:
        host._on_sync_finished = Mock()
        host._release_sync_worker = Mock()
        host.sync_google_calendar_silent()
        sync.assert_called_once_with(host, silent=True)


@pytest.mark.parametrize(
    "error",
    [
        "login_required",
        "auth",
        "remote_http_401",
        "graph_http_401",
        "account_mismatch",
        "account_unverified",
        "auth_client_invalid",
    ],
)
def test_expired_or_unverified_account_routes_to_connection_instead_of_retry(sync_ui, error):
    sync_ui.host.settings.setValue("sync_google_last_error", error)
    sync_ui.coordinator.refresh()
    hub = CalendarSyncHub(sync_ui.host, section="issues")
    assert not hub.sync_buttons["google"].isEnabled()
    assert not hub.retry_selected.isEnabled()
    assert (
        sync_recovery_action("google", sync_ui.coordinator.states["google"])["kind"] == "reconnect"
    )
    hub.resolve_selected.click()
    sync_ui.host.open_gcal_settings_dialog.assert_called_once_with(
        initial_tab=None, from_sync_hub=True
    )
    sync_ui.host.open_gcal_sync_issues_dialog.assert_not_called()
    sync_ui.host.sync_google_calendar.assert_not_called()
    hub.close()


def test_google_pause_preserves_account_and_leads_to_resume_settings(sync_ui):
    sync_ui.host.settings.setValue("gcal_enabled", False)
    sync_ui.coordinator.refresh()
    state = sync_ui.coordinator.states["google"]
    assert state["connected"] and state["paused"]
    assert not state["can_sync"] and not state["auto"]
    hub = CalendarSyncHub(sync_ui.host, section="services")
    assert not hub.sync_buttons["google"].isEnabled()
    assert hub.connect_buttons["google"].isEnabled()
    assert sync_recovery_action("google", state)["kind"] == "resume"
    hub.connect_buttons["google"].click()
    sync_ui.host.open_gcal_settings_dialog.assert_called_once()
    assert sync_ui.host.gcal_sync.is_authenticated
    hub.close()


@pytest.mark.parametrize("background_completion", [False, True])
def test_google_pause_and_settings_close_preserve_authenticated_service(
    sync_ui, monkeypatch, background_completion
):
    host = sync_ui.host
    connection = host.gcal_sync
    connection.service = object()
    service = connection.service
    host.update_sync_status = Mock()
    host.refresh_gcal_sync_state_internal = MethodType(
        GCalActionsMixin.refresh_gcal_sync_state_internal, host
    )
    host.refresh_gcal_sync_state = MethodType(GCalActionsMixin.refresh_gcal_sync_state, host)
    auth_worker = Mock()
    monkeypatch.setattr("calendar_app.shared.background_worker.AuthWorker", auth_worker)
    monkeypatch.setattr(
        "calendar_app.presentation.main_window.action_handlers_gcal.os.path.exists",
        lambda path: True,
    )
    host.settings.setValue("gcal_enabled", False)

    if background_completion:
        # An auth job may observe the pause before it starts its work.
        assert not host.refresh_gcal_sync_state_internal(update_ui=False)
        host.update_sync_status.assert_not_called()
    # The settings opener refreshes runtime state after an applied change is closed.
    assert not host.refresh_gcal_sync_state(authenticate_silently=True)
    auth_worker.assert_not_called()
    assert host.gcal_sync is connection and connection.service is service
    assert connection.is_authenticated
    host.update_gcal_sync_timer.assert_called_once()
    host.update_sync_status.assert_called_once()
    sync_ui.coordinator.refresh()
    assert sync_ui.coordinator.states["google"]["paused"]

    prepare = Mock(return_value=connection)
    monkeypatch.setattr(
        "calendar_app.infrastructure.google_sync.service.prepare_calendar_sync_service", prepare
    )
    monkeypatch.setattr(
        "calendar_app.infrastructure.google_sync.common.get_default_gcal_calendar_id",
        lambda settings: "primary",
    )
    host.settings.setValue("gcal_enabled", True)
    assert host.refresh_gcal_sync_state_internal(authenticate_silently=False)
    assert prepare.call_args.args == (connection,)
    assert connection.service is service and connection.is_authenticated
    sync_ui.coordinator.refresh()
    assert sync_ui.coordinator.states["google"]["can_sync"]


def test_google_pause_on_fresh_install_does_not_create_an_auth_worker(sync_ui, monkeypatch):
    host = sync_ui.host
    host.gcal_sync = None
    host.settings.setValue("gcal_enabled", False)
    host.update_sync_status = Mock()
    host.refresh_gcal_sync_state_internal = MethodType(
        GCalActionsMixin.refresh_gcal_sync_state_internal, host
    )
    worker = Mock()
    monkeypatch.setattr("calendar_app.shared.background_worker.AuthWorker", worker)
    assert not GCalActionsMixin.refresh_gcal_sync_state(host)
    assert host.gcal_sync is None
    worker.assert_not_called()


def test_disabling_all_google_imports_keeps_existing_edit_sync_available(sync_ui):
    sync_ui.add_calendar("gcal::existing", kind="gcal", active=False, role="owner")
    sync_ui.host.settings.setValue("gcal_import_selection_configured", True)
    sync_ui.coordinator.refresh()
    state = sync_ui.coordinator.states["google"]
    assert state["import_paused"] and not state["needs_selection"] and state["can_sync"]
    assert sync_recovery_action("google", state)["can_retry"]


def test_missing_explicit_import_metadata_routes_to_calendar_selection(sync_ui):
    sync_ui.host.settings.setValue("gcal_import_selection_configured", True)
    sync_ui.coordinator.refresh()
    hub = CalendarSyncHub(sync_ui.host, section="services")
    assert not hub.sync_buttons["google"].isEnabled()
    hub.connect_buttons["google"].click()
    sync_ui.host.open_gcal_settings_dialog.assert_called_once_with(
        initial_tab="calendar", from_sync_hub=True
    )
    hub.close()


def test_busy_connection_can_be_opened_to_view_progress(sync_ui):
    hub = CalendarSyncHub(sync_ui.host, section="services")
    hub.sync_buttons["google"].click()
    assert not hub.sync_buttons["google"].isEnabled()
    assert hub.connect_buttons["google"].isEnabled()
    hub.connect_buttons["google"].click()
    sync_ui.host.open_gcal_settings_dialog.assert_called_once()
    hub.close()


def test_sync_result_remains_visible_and_requires_a_new_success_record(sync_ui):
    hub = CalendarSyncHub(sync_ui.host, section="services")
    hub._run_sync("google")
    started = hub.sync_feedback.text()
    sync_ui.host._gcal_sync_in_progress = False
    sync_ui.host.settings.setValue("last_successful_sync", "2026-10-07T13:00:00+09:00")
    sync_ui.coordinator.refresh()
    assert not hub.sync_feedback.isHidden()
    assert hub.sync_feedback.text() != started
    confirmed = hub.sync_feedback.text()
    hub._run_sync("google")
    sync_ui.host._gcal_sync_in_progress = False
    sync_ui.coordinator.refresh()
    assert hub.sync_feedback.text() != confirmed
    hub.close()


def test_refused_google_dispatch_does_not_claim_a_started_job(sync_ui):
    sync_ui.host.sync_google_calendar = Mock(return_value=False)
    assert sync_ui.coordinator.sync("google") == []


@pytest.mark.parametrize("error", ["auth", "auth_required", "reauth_required"])
def test_actual_google_auth_failure_preserves_reconnection_state(sync_ui, error):
    sync_ui.host._last_gcal_sync_error = error
    sync_ui.coordinator.record_google_result(False)
    sync_ui.coordinator.refresh()
    state = sync_ui.coordinator.states["google"]
    assert state["error"] == "login_required"
    assert not state["can_sync"]
    assert sync_recovery_action("google", state)["kind"] == "reconnect"


@pytest.mark.parametrize(
    "status, expected",
    [(401, "login_required"), (403, "remote_http_403"), (429, "remote_http_429")],
)
def test_google_api_401_requires_sign_in_but_quota_and_permission_errors_remain_distinct(
    sync_ui, status, expected
):
    sync_ui.host._last_gcal_sync_error = "fetch"
    sync_ui.host.gcal_sync.last_error_status = status
    sync_ui.coordinator.record_google_result(False)
    assert sync_ui.host.settings.value("sync_google_last_error") == expected


def test_status_refresh_preserves_calendar_item_selection_search_focus_and_scroll(sync_ui):
    for number in range(18):
        sync_ui.add_calendar(f"ics::{number:02d}")
    hub = CalendarSyncHub(sync_ui.host)
    hub.show()
    page = hub.calendar_manager
    page.search.setText("ics::")
    page.calendars.setCurrentRow(12)
    page.search.setFocus()
    sync_ui.qapp.processEvents()
    page.calendars.verticalScrollBar().setValue(180)
    before = page.calendars.currentItem()
    scroll_value = page.calendars.verticalScrollBar().value()
    sync_ui.host._gcal_sync_in_progress = True
    sync_ui.coordinator.refresh()
    sync_ui.qapp.processEvents()
    assert page.calendars.currentItem() is before
    assert page.current()["id"] == before.data(Qt.ItemDataRole.UserRole)["id"]
    assert page.calendars.verticalScrollBar().value() == scroll_value
    assert page.search.text() == "ics::" and page.search.hasFocus()
    hub.close()


def test_retry_wait_cannot_be_bypassed_by_ui_and_uses_ceiling():
    state = {
        "connected": True,
        "busy": False,
        "can_sync": True,
        "retry_remaining": 2.1,
        "error": "graph_http_429",
    }
    action = sync_recovery_action("outlook", state)
    assert action["kind"] == "wait" and action["remaining"] == 3 and not action["can_retry"]


def test_controller_retry_wait_gates_dispatch_and_keeps_issue_item_during_countdown(ui):
    controller = ui.host._outlook_sync_controller
    controller.status = "graph_http_429"
    controller.retry_remaining_seconds = 45
    ui.coordinator.refresh()
    hub = CalendarSyncHub(ui.host, section="issues")
    assert not ui.coordinator.states["outlook"]["can_sync"]
    assert ui.coordinator.sync("outlook") == []
    controller.start.assert_not_called()
    assert not hub.sync_buttons["outlook"].isEnabled()
    item = next(
        hub.issue_list.item(i)
        for i in range(hub.issue_list.count())
        if hub.issue_list.item(i).data(Qt.ItemDataRole.UserRole) == "outlook"
    )
    hub.issue_list.setCurrentItem(item)
    assert not hub.retry_selected.isEnabled()
    controller.retry_remaining_seconds = 44
    ui.coordinator.refresh()
    assert hub.issue_list.currentItem() is item
    controller.retry_remaining_seconds = 0
    ui.coordinator.refresh()
    assert hub.retry_selected.isEnabled()
    hub.close()


def test_requested_stop_is_not_presented_as_a_failed_account(ui):
    controller = ui.host._outlook_sync_controller
    controller.status = "cancelled"
    ui.coordinator.refresh()
    state = ui.coordinator.states["outlook"]
    assert state["cancelled"] and not state["error"]
    assert state["connected"]


@pytest.mark.parametrize(
    "provider, prefix",
    [("outlook", "outlook_"), ("icloud", "caldav_icloud_"), ("naver", "caldav_naver_")],
)
def test_saved_auth_error_is_visible_after_restart_or_selection_save(ui, provider, prefix):
    controller = ui.coordinator.controllers()[provider]
    ui.host.settings.setValue(prefix + "last_error", "login_required")
    for status in ("idle", "selection_saved", "cancelled"):
        controller.status = status
        ui.coordinator.refresh()
        state = ui.coordinator.states[provider]
        assert state["error"] == "login_required"
        assert not state["can_sync"]
        assert ui.coordinator.sync(provider) == []
        assert sync_recovery_action(provider, state)["kind"] == "reconnect"
    controller.start.assert_not_called()
