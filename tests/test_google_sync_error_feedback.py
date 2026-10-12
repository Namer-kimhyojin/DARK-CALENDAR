# -*- coding: utf-8 -*-
"""Safe Google failure codes and actionable recovery in the calendar workspace."""

from unittest.mock import Mock

from PyQt6.QtCore import QPoint
import pytest

from calendar_app.presentation.dialogs.calendar_sync_hub import CalendarSyncHub
from calendar_app.presentation.dialogs.sync_feedback import (
    google_sync_error_code,
    sync_error_message,
)
from calendar_app.presentation.dialogs.sync_recovery import sync_recovery_action
from tests.test_calendar_sync_redesign import sync_ui  # noqa: F401


@pytest.mark.parametrize(
    "code",
    [
        "account_mismatch",
        "account_unverified",
        "network_unavailable",
        "dependency_unavailable",
        "google_pull_invalid_datetime",
        "database_failed",
        "invalid_remote_event",
        "duplicate_remote_event",
        "pull_apply_failed",
        "auth_client_type",
        "auth_client_invalid",
        "auth_client_missing",
        "auth_token_write",
    ],
)
def test_known_failure_survives_result_recording_and_stale_service_http(sync_ui, code):
    sync_ui.host._last_gcal_sync_error = code
    sync_ui.host.gcal_sync.last_error_status = 401
    sync_ui.coordinator.record_google_result(False)
    sync_ui.coordinator.refresh()
    assert sync_ui.host.settings.value("sync_google_last_error") == code
    assert sync_ui.coordinator.states["google"]["error"] == code


@pytest.mark.parametrize("status", [400, 403, 404, 412, 429, 500, 503])
def test_saved_http_snapshot_survives_service_error_clearing(sync_ui, status):
    code = f"remote_http_{status}"
    sync_ui.host._last_gcal_sync_error = code
    sync_ui.host.gcal_sync.last_error_status = None
    sync_ui.coordinator.record_google_result(False)
    assert sync_ui.host.settings.value("sync_google_last_error") == code


@pytest.mark.parametrize("code", ["remote_http_401", "auth", "auth_required", "reauth_required"])
def test_authentication_failure_has_explicit_reconnection_action(sync_ui, code):
    sync_ui.host._last_gcal_sync_error = code
    sync_ui.coordinator.record_google_result(False)
    sync_ui.coordinator.refresh()
    assert sync_ui.coordinator.states["google"]["error"] == "login_required"
    assert (
        sync_recovery_action("google", sync_ui.coordinator.states["google"])["kind"] == "reconnect"
    )


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("invalid_google_pull_datetime", "google_pull_invalid_datetime"),
        ("auth_modules", "dependency_unavailable"),
        ("network", "network_unavailable"),
        ("fetch_exception", "network_unavailable"),
        ("fetch", "google_fetch_failed"),
        ("calendar_list", "google_fetch_failed"),
    ],
)
def test_legacy_error_kinds_have_safe_specific_codes(raw, expected):
    assert google_sync_error_code(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "Exception: secret-user@example.invalid token=private-token",
        "remote_http_403 https://example.invalid/private?token=private-token",
        "remote_http_４０３",
        "remote_http_403/private-token",
        "remote_http_999",
        "database_failed: private calendar name",
        None,
        {"token": "private-token"},
    ],
)
def test_unknown_exception_and_payload_never_enter_persisted_diagnostics(sync_ui, raw):
    sync_ui.host._last_gcal_sync_error = raw
    sync_ui.host.gcal_sync.last_error_status = 401
    sync_ui.coordinator.record_google_result(False)
    sync_ui.coordinator.refresh()
    assert sync_ui.host.settings.value("sync_google_last_error") == "operation_failed"
    hub = CalendarSyncHub(sync_ui.host, section="issues")
    assert "private-token" not in hub.issue_detail.text()
    assert "secret-user" not in hub.issue_detail.text()
    hub.close()


@pytest.mark.parametrize("status", [None, True, "403", "403/private-token", 200, 600])
def test_invalid_or_successful_http_status_is_not_used_as_a_failure(status):
    assert google_sync_error_code("fetch", status) == "google_fetch_failed"


@pytest.mark.parametrize(
    "code",
    [
        "google_pull_invalid_datetime",
        "database_failed",
        "invalid_remote_event",
        "network_unavailable",
        "remote_http_403",
        "remote_http_429",
        "remote_http_503",
    ],
)
def test_specific_failure_is_shown_in_the_hub_and_retries_only_google(sync_ui, monkeypatch, code):
    sync_ui.host._last_gcal_sync_error = code
    sync_ui.coordinator.record_google_result(False)
    sync_ui.coordinator.refresh()
    hub = CalendarSyncHub(sync_ui.host, section="issues")
    assert sync_error_message(code) in hub.issue_detail.text()
    action = sync_recovery_action("google", sync_ui.coordinator.states["google"])
    assert action["kind"] == "retry" and action["can_retry"]
    assert hub.retry_selected.isEnabled()
    dispatch = Mock(return_value=["google"])
    monkeypatch.setattr(sync_ui.coordinator, "sync", dispatch)
    hub.retry_selected.click()
    dispatch.assert_called_once_with("google")
    sync_ui.host.open_gcal_settings_dialog.assert_not_called()
    hub.close()


def test_dependency_failure_blocks_ineffective_retry_and_explains_installation(sync_ui):
    sync_ui.host._last_gcal_sync_error = "auth_modules"
    sync_ui.coordinator.record_google_result(False)
    sync_ui.coordinator.refresh()
    hub = CalendarSyncHub(sync_ui.host, section="issues")
    action = sync_recovery_action("google", sync_ui.coordinator.states["google"])
    assert action["kind"] == "repair" and not action["can_retry"]
    assert sync_error_message("dependency_unavailable") in hub.issue_detail.text()
    assert not hub.retry_selected.isEnabled() and not hub.sync_all.isEnabled()
    hub.close()


def test_existing_pending_items_keep_the_review_action_when_pull_fails(sync_ui):
    state = {
        "connected": True,
        "busy": False,
        "can_sync": True,
        "issues": 2,
        "error": "google_pull_invalid_datetime",
    }
    action = sync_recovery_action("google", state)
    assert action["kind"] == "issues" and action["section"] == "issues"
    assert action["can_retry"]


@pytest.mark.parametrize(
    "success, skipped, expected",
    [
        (True, False, ""),
        (False, True, "google_pull_invalid_datetime"),
    ],
)
def test_success_clears_error_and_skipped_run_preserves_previous_diagnosis(
    sync_ui, success, skipped, expected
):
    sync_ui.host.settings.setValue("sync_google_last_error", "google_pull_invalid_datetime")
    sync_ui.host._last_gcal_sync_error = "unknown private payload"
    sync_ui.coordinator.record_google_result(success, skipped)
    assert sync_ui.host.settings.value("sync_google_last_error") == expected


@pytest.mark.parametrize("code", ["google_pull_invalid_datetime", "database_failed"])
def test_data_and_storage_guidance_actions_remain_reachable_in_narrow_window(sync_ui, code):
    sync_ui.host.settings.setValue("sync_google_last_error", code)
    sync_ui.coordinator.refresh()
    hub = CalendarSyncHub(sync_ui.host, section="issues")
    hub.resize(620, 500)
    hub.show()
    sync_ui.qapp.processEvents()
    assert hub.issue_detail.wordWrap()
    for button in (hub.retry_selected, hub.resolve_selected):
        hub.issue_scroll.ensureWidgetVisible(button)
        sync_ui.qapp.processEvents()
        point = button.mapTo(hub.issue_scroll.viewport(), QPoint(0, 0))
        assert 0 <= point.y() < hub.issue_scroll.viewport().height()
        assert point.y() + button.height() <= hub.issue_scroll.viewport().height()
        assert button.width() <= hub.issue_scroll.viewport().width()
    hub.close()
