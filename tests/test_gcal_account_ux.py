# -*- coding: utf-8 -*-
"""Account guidance, cancellation and settings safety through native Qt controls."""

import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog
import pytest

from calendar_app.application.calendar_preferences import CalendarImportSelectionResult
from calendar_app.presentation.dialogs import gcal_settings_dialog as module
from calendar_app.presentation.dialogs.gcal_auth_worker import GCalQueryWorker
from tests.test_gcal_settings_focus import focused_dialog  # noqa: F401


@pytest.mark.parametrize("value", ["broken", "", None, [], -1, 0, 999999])
def test_corrupt_interval_settings_recover_without_rewriting_storage(focused_dialog, value):
    dialog, parent, _ = focused_dialog
    parent.settings.setValue("gcal_sync_interval", value)
    parent.settings.setValue("gcal_quick_sync_interval", value)
    dialog._load_state()
    assert dialog.interval_spin.value() == 10
    assert dialog.quick_interval_spin.value() == 30
    assert parent.settings.value("gcal_sync_interval") == value


def test_connected_account_hides_technical_file_and_offers_same_account_reauthentication(
    focused_dialog,
):
    dialog, _, _ = focused_dialog
    dialog._switch_section(0)
    assert dialog.auth_btn.text() == module.t("gcal_ux.reconnect", "계정 다시 연결")
    assert not dialog.credentials_panel.isVisible()
    QTest.mouseClick(dialog.credentials_details_btn, Qt.MouseButton.LeftButton)
    assert dialog.credentials_panel.isVisible()
    assert dialog.creds_path_edit.accessibleName()


def test_disabling_sync_preserves_authenticated_connection_and_token_route(
    focused_dialog, monkeypatch
):
    from calendar_app.application import calendar_preferences

    dialog, parent, _ = focused_dialog
    old_service = parent.gcal_sync.service
    monkeypatch.setattr(
        calendar_preferences,
        "set_google_calendar_import_selection",
        lambda *args, **kwargs: CalendarImportSelectionResult(True),
    )
    dialog.enable_cb.setChecked(False)
    dialog.save_settings()
    assert parent.settings.value("gcal_enabled") == "false"
    assert parent.gcal_sync.is_authenticated and parent.gcal_sync.service is old_service
    assert dialog.isVisible()
    assert not dialog.save_btn.isEnabled()
    module.QMessageBox.information.assert_not_called()


def test_parent_sync_locks_writes_but_keeps_navigation_and_close_available(
    focused_dialog, monkeypatch
):
    from calendar_app.application import calendar_preferences

    dialog, parent, _ = focused_dialog
    dialog.enable_cb.setChecked(False)
    save = Mock()
    monkeypatch.setattr(calendar_preferences, "set_google_calendar_import_selection", save)
    parent._calendar_sync_coordinator = SimpleNamespace(states={"google": {"busy": True}})
    dialog._refresh_operation_availability()
    assert not dialog.enable_cb.isEnabled()
    assert not dialog.interval_spin.isEnabled()
    assert not dialog.save_btn.isEnabled()
    assert not dialog.reset_sync_state_btn.isEnabled()
    assert dialog.close_btn.isEnabled() and all(button.isEnabled() for button in dialog._nav_btns)
    dialog.save_settings()
    save.assert_not_called()
    assert parent.settings.value("gcal_enabled") == "true"
    parent._calendar_sync_coordinator.states["google"]["busy"] = False
    dialog._refresh_operation_availability()
    assert dialog.enable_cb.isEnabled() and dialog.save_btn.isEnabled()


def test_close_after_saved_settings_preserves_caller_refresh_without_saving_later_draft(
    focused_dialog, monkeypatch
):
    from calendar_app.application import calendar_preferences

    dialog, parent, _ = focused_dialog
    save = Mock(return_value=CalendarImportSelectionResult(True))
    monkeypatch.setattr(calendar_preferences, "set_google_calendar_import_selection", save)
    dialog.enable_cb.setChecked(False)
    dialog.save_settings()
    assert dialog.isVisible()
    dialog.enable_cb.setChecked(True)
    dialog.reject()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert parent.settings.value("gcal_enabled") == "false"
    save.assert_called_once()


def test_parent_busy_blocks_disconnect_and_cache_reset_before_confirmation(
    focused_dialog, monkeypatch
):
    dialog, parent, _ = focused_dialog
    parent._calendar_sync_coordinator = SimpleNamespace(states={"google": {"busy": True}})
    question, warning = Mock(), Mock()
    monkeypatch.setattr(module.QMessageBox, "question", question)
    monkeypatch.setattr(module.QMessageBox, "warning", warning)
    dialog.reset_auth()
    dialog._reset_sync_state()
    question.assert_not_called()
    warning.assert_not_called()
    assert parent.gcal_sync.is_authenticated and dialog._query_worker is None


def test_query_cancel_preserves_draft_and_restores_inputs(focused_dialog):
    dialog, parent, _ = focused_dialog
    dialog._set_import_selection("gcal::team", False)
    worker = SimpleNamespace(
        requestInterruption=Mock(), is_cancelled=lambda: True, deleteLater=Mock(), success=False
    )
    dialog._query_worker, dialog._query_kind = worker, "import"
    parent._bg_workers.append(worker)
    dialog._set_operation_state(True, "Synthetic lookup")
    assert not dialog.import_list.isEnabled() and not dialog.creds_path_edit.isEnabled()
    QTest.mouseClick(dialog.cancel_operation_btn, Qt.MouseButton.LeftButton)
    worker.requestInterruption.assert_called_once()
    assert not dialog.cancel_operation_btn.isEnabled()
    dialog._finish_calendar_query()
    assert dialog._calendar_import_selection["gcal::team"] is False
    assert dialog.import_list.isEnabled() and dialog.creds_path_edit.isEnabled()
    assert not dialog.cancel_operation_btn.isVisible()
    assert "취소" in dialog.connection_feedback.text()


def test_metadata_read_failure_keeps_draft_and_blocks_save(focused_dialog, monkeypatch):
    from calendar_app.application import calendar_preferences
    from calendar_app.infrastructure.db import calendar_repo

    dialog, _, _ = focused_dialog
    dialog._set_import_selection("gcal::team", False)
    previous = dict(dialog._calendar_import_selection)
    monkeypatch.setattr(
        calendar_repo,
        "list_calendars",
        Mock(side_effect=sqlite3.OperationalError("synthetic failure")),
    )
    save = Mock()
    monkeypatch.setattr(calendar_preferences, "set_google_calendar_import_selection", save)
    dialog._refresh_calendar_table()
    assert dialog._metadata_load_failed and dialog._calendar_import_selection == previous
    assert not dialog.save_btn.isEnabled()
    dialog.save_settings()
    save.assert_not_called()
    assert "선택" in dialog.connection_feedback.text()


def test_error_guidance_does_not_expose_provider_payload(focused_dialog):
    dialog, parent, _ = focused_dialog
    parent.gcal_sync.last_error_kind = "calendar_list"
    parent.gcal_sync.last_error_message = "secret provider payload with personal identifiers"
    dialog._refresh_diagnostics()
    assert "secret provider" not in dialog.last_error_meta[1].text()
    dialog._set_query_feedback(
        dialog._friendly_error("account_mismatch"), "error", "account_mismatch"
    )
    assert dialog.feedback_bar.isVisible() and dialog.recovery_btn.isVisible()
    QTest.mouseClick(dialog.recovery_btn, Qt.MouseButton.LeftButton)
    assert dialog._stack.currentIndex() == 0
    assert dialog.auth_btn.hasFocus()


def test_missing_credentials_are_inline_and_file_field_is_reachable(
    focused_dialog, monkeypatch, tmp_path
):
    dialog, _, _ = focused_dialog
    # The production method is called directly; no network or credential copying occurs.
    monkeypatch.setattr(module.QMessageBox, "warning", Mock())
    dialog.creds_path_edit.setText(str(tmp_path / "missing.json"))
    assert not module.GCalSettingsDialog._copy_credentials_if_needed(dialog)
    assert dialog.credentials_panel.isVisible()
    assert dialog._stack.currentIndex() == 0
    assert dialog.creds_path_edit.hasFocus()
    module.QMessageBox.warning.assert_not_called()


def test_compact_sync_timestamp_retains_full_tooltip(focused_dialog):
    dialog, parent, _ = focused_dialog
    parent.settings.setValue("last_successful_sync", "2026-10-07 12:12:28")
    dialog._refresh_meta()
    assert dialog.last_sync_meta[1].text() == "10-07 12:12"
    assert dialog.last_sync_meta[1].toolTip() == "2026-10-07 12:12:28"
    dialog.resize(760, 560)
    QApplication.processEvents()
    assert dialog.close_btn.isVisible()


def test_query_worker_publishes_safe_error_code_for_unexpected_failure():
    service = SimpleNamespace(
        list_accessible_calendars=Mock(side_effect=RuntimeError("private payload")),
        _set_last_error=Mock(),
        last_error_kind=None,
    )
    worker = GCalQueryWorker(service)
    worker.run()
    assert not worker.success
    service._set_last_error.assert_called_once_with("calendar_list", "Google calendar query failed")
