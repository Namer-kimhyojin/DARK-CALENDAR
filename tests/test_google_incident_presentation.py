# -*- coding: utf-8 -*-
"""Use safe Google failure causes consistently in metadata and manual feedback."""

from types import SimpleNamespace

import pytest

from calendar_app.presentation.dialogs.sync_feedback import sync_error_message
from tests.test_gcal_partial_result_feedback import feedback  # noqa: F401
from tests.test_gcal_settings_focus import focused_dialog  # noqa: F401


@pytest.mark.parametrize(
    "code,status,expected",
    [
        ("google_pull_invalid_datetime", 401, "google_pull_invalid_datetime"),
        ("database_failed", 403, "database_failed"),
        ("pull_apply_failed", None, "pull_apply_failed"),
        ("fetch", 403, "remote_http_403"),
        ("fetch", 429, "remote_http_429"),
        ("fetch", 503, "remote_http_503"),
        ("network", None, "network_unavailable"),
        ("fetch", None, "google_fetch_failed"),
        ("https://private.invalid/?token=secret user@example.invalid", None, "operation_failed"),
    ],
)
def test_google_metadata_keeps_safe_cause_and_ignores_stale_http(
    focused_dialog, code, status, expected
):
    dialog, parent, _ = focused_dialog
    parent.gcal_sync.last_error_status = status
    text = dialog._friendly_error(code)
    assert text == sync_error_message(expected)
    assert "secret" not in text and "example.invalid" not in text


@pytest.mark.parametrize(
    "code",
    [
        "google_pull_invalid_datetime",
        "database_failed",
        "remote_http_403",
        "remote_http_429",
        "network_unavailable",
        "https://private.invalid/?token=secret user@example.invalid",
    ],
)
def test_manual_and_automatic_feedback_use_safe_diagnosis(feedback, code, caplog):
    ui = feedback
    ui.host._last_gcal_sync_error = code
    ui.host.gcal_sync = SimpleNamespace(last_error_kind=None, last_error_status=None)
    ui.callback(ui.host, False, "Traceback: private token=secret user@example.invalid")
    expected = sync_error_message(code if not code.startswith("https:") else "operation_failed")
    assert ui.settings.value("sync_google_last_error") == (
        code if not code.startswith("https:") else "operation_failed"
    )
    assert "secret" not in caplog.text and "example.invalid" not in caplog.text
    if ui.manual:
        assert ui.warning.call_args.args[2] == expected
        ui.host._show_sync_issue_popup.assert_called_once_with(expected)
    else:
        assert expected in caplog.text
        ui.warning.assert_not_called()
