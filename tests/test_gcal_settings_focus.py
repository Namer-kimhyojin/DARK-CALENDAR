# -*- coding: utf-8 -*-
"""Google-only settings, deferred import choices, and main-default ownership."""

from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QWidget
import pytest

from calendar_app.application.calendar_preferences import CalendarImportSelectionResult
from calendar_app.presentation.dialogs import gcal_settings_dialog as module


@pytest.fixture
def focused_dialog(tmp_path, monkeypatch):
    from calendar_app.infrastructure.db import calendar_repo, task_repo
    from calendar_app.infrastructure.google_sync import common

    app = QApplication.instance() or QApplication([])
    rows = [
        {
            "id": "local::default",
            "type": "local",
            "name": "기본",
            "is_default": 1,
            "is_active": 1,
            "is_visible": 1,
        },
        {
            "id": "gcal::team",
            "type": "gcal",
            "name": "팀 캘린더",
            "gcal_calendar_id": "team",
            "access_role": "owner",
            "is_default": 0,
            "is_active": 1,
            "is_visible": 1,
        },
        {
            "id": "gcal::holidays",
            "type": "gcal",
            "name": "대한민국의 휴일",
            "gcal_calendar_id": "holidays",
            "access_role": "reader",
            "is_default": 0,
            "is_active": 0,
            "is_visible": 1,
        },
    ]
    monkeypatch.setattr(
        calendar_repo, "list_calendars", lambda **kwargs: [dict(row) for row in rows]
    )
    monkeypatch.setattr(common, "get_default_gcal_calendar_id", lambda settings=None: "team")
    for name in (
        "count_unified_task_gcal_errors",
        "count_gcal_delete_queue_errors",
        "count_gcal_sync_conflicts",
    ):
        monkeypatch.setattr(task_repo, name, lambda: 0)
    monkeypatch.setattr(task_repo, "get_gcal_delete_queue", lambda: [])
    monkeypatch.setattr(module, "CREDENTIALS_PATH", str(tmp_path / "credentials.json"))
    monkeypatch.setattr(module, "TOKEN_PATH", str(tmp_path / "token.json"))
    monkeypatch.setattr(module.QMessageBox, "information", Mock())
    parent = QWidget()
    parent.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    parent.settings.setValue("gcal_enabled", "true")
    parent.settings.setValue("gcal_import_selection_configured", True)
    parent.settings.setValue("gcal_calendar_id", "team")
    parent.gcal_sync = SimpleNamespace(
        is_authenticated=True, service=object(), calendar_id="team", time_zone="Asia/Seoul"
    )
    parent._bg_workers = []
    parent.update_gcal_sync_timer = Mock()
    parent.update_sync_status = Mock()
    parent.load_center_panel = Mock()
    dialog = module.GCalSettingsDialog(parent, initial_tab="calendar")
    monkeypatch.setattr(dialog, "_copy_credentials_if_needed", lambda: True)
    dialog.show()
    app.processEvents()
    yield dialog, parent, rows
    dialog.close()
    parent.close()
    app.processEvents()


def test_import_page_exposes_google_selection_and_hides_duplicate_write_picker(focused_dialog):
    dialog, _, _ = focused_dialog
    assert dialog._stack.currentIndex() == 1
    assert len(dialog._nav_btns) == 5
    assert not dialog.cal_id_edit.isVisible()
    assert not dialog.calendar_choice_combo.isVisible()
    assert dialog.import_list.isVisible()
    assert set(dialog._calendar_import_checks) == {"gcal::team", "gcal::holidays"}
    assert all(checkbox.accessibleName() for checkbox in dialog._calendar_import_checks.values())
    assert dialog.save_btn.isVisible()
    assert not dialog.auth_btn.isVisible()
    assert not dialog.reset_btn.isVisible()
    dialog._switch_section(0)
    QApplication.processEvents()
    assert dialog.auth_btn.isVisible() and dialog.reset_btn.isVisible()


def test_connected_persisted_calendars_replace_initial_auth_hint(focused_dialog):
    dialog, _, _ = focused_dialog
    assert "2" in dialog.calendar_choice_hint.text()
    idle_hint = module.t(
        "gcal_settings.calendar_choice_hint",
        "인증 완료 후 내 계정에서 사용 가능한 캘린더 목록을 불러올 수 있습니다.",
    )
    assert dialog.calendar_choice_hint.text() != idle_hint
    dialog._set_query_feedback("Network query failed", "error")
    dialog._refresh_calendar_table()
    assert dialog.calendar_choice_hint.text() == "Network query failed"


def test_import_toggle_is_a_draft_and_survives_metadata_render(focused_dialog):
    dialog, parent, rows = focused_dialog
    checkbox = dialog._calendar_import_checks["gcal::team"]
    QTest.mouseClick(checkbox, Qt.MouseButton.LeftButton)
    assert dialog._calendar_import_selection["gcal::team"] is False
    assert rows[1]["is_active"] == 1
    assert parent.settings.value("gcal_calendar_id") == "team"
    assert dialog._settings_dirty
    dialog._refresh_calendar_table()
    assert not dialog._calendar_import_checks["gcal::team"].isChecked()
    dialog.reject()
    assert rows[1]["is_active"] == 1


def test_readonly_calendars_can_be_selected_for_import(focused_dialog):
    dialog, _, rows = focused_dialog
    checkbox = dialog._calendar_import_checks["gcal::holidays"]
    assert checkbox.isEnabled() and not checkbox.isChecked()
    QTest.mouseClick(checkbox, Qt.MouseButton.LeftButton)
    assert dialog._calendar_import_selection["gcal::holidays"] is True
    assert rows[2]["access_role"] == "reader" and rows[2]["is_active"] == 0


def test_legacy_visible_reader_starts_selected_until_explicit_selection(focused_dialog):
    dialog, parent, _ = focused_dialog
    parent.settings.remove("gcal_import_selection_configured")
    dialog._calendar_import_selection.clear()
    dialog._refresh_calendar_table()
    assert dialog._calendar_import_checks["gcal::holidays"].isChecked()


def test_save_uses_batch_import_api_and_preserves_main_default_target(focused_dialog, monkeypatch):
    from calendar_app.application import calendar_preferences
    from calendar_app.infrastructure.db import calendar_repo

    dialog, parent, _ = focused_dialog
    parent.settings.setValue("gcal_calendar_id", "chosen-on-main")
    dialog.cal_id_edit.setText("obsolete-dialog-target")
    save = Mock(return_value=CalendarImportSelectionResult(True))
    monkeypatch.setattr(calendar_preferences, "set_google_calendar_import_selection", save)
    dialog.save_settings()
    save.assert_called_once_with(
        {"gcal::team": True, "gcal::holidays": False}, parent.settings, repository=calendar_repo
    )
    assert parent.settings.value("gcal_calendar_id") == "chosen-on-main"
    assert parent.gcal_sync.calendar_id == "team"
    assert dialog.isVisible() and not dialog._settings_dirty
    assert not dialog.save_btn.isEnabled()


def test_failed_import_save_leaves_other_preferences_unchanged(focused_dialog, monkeypatch):
    from calendar_app.application import calendar_preferences

    dialog, parent, _ = focused_dialog
    save = Mock(return_value=CalendarImportSelectionResult(False))
    monkeypatch.setattr(calendar_preferences, "set_google_calendar_import_selection", save)
    dialog.interval_spin.setValue(44)
    dialog.save_settings()
    assert parent.settings.value("gcal_sync_interval") is None
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog._stack.currentIndex() == 1
    assert dialog.calendar_choice_hint.text()


def test_invalid_timezone_prevents_import_save_and_reveals_advanced_controls(
    focused_dialog, monkeypatch
):
    from calendar_app.application import calendar_preferences

    dialog, _, _ = focused_dialog
    save = Mock(side_effect=AssertionError("Invalid timezone must not persist import choices"))
    monkeypatch.setattr(calendar_preferences, "set_google_calendar_import_selection", save)
    dialog.timezone_combo.setEditText("Invalid/Zone")
    dialog.save_settings()
    save.assert_not_called()
    assert dialog._stack.currentIndex() == 2
    assert dialog.timezone_details_btn.isChecked()
    assert dialog.timezone_card.isVisible()


def test_auto_sync_can_be_paused_without_disabling_account(focused_dialog, monkeypatch):
    from calendar_app.application import calendar_preferences

    dialog, parent, _ = focused_dialog
    monkeypatch.setattr(
        calendar_preferences,
        "set_google_calendar_import_selection",
        lambda *args, **kwargs: CalendarImportSelectionResult(True),
    )
    dialog.auto_sync_cb.setChecked(False)
    assert not dialog.interval_spin.isEnabled()
    assert not dialog.quick_interval_spin.isEnabled()
    dialog.save_settings()
    assert parent.settings.value("sync_google_auto") == "false"
    assert parent.settings.value("gcal_enabled") == "true"
    assert parent.gcal_sync.is_authenticated and parent.gcal_sync.service is not None


def test_default_fallback_is_explained_after_successful_save(focused_dialog, monkeypatch):
    from calendar_app.application import calendar_preferences

    dialog, _, _ = focused_dialog
    monkeypatch.setattr(
        calendar_preferences,
        "set_google_calendar_import_selection",
        lambda *args, **kwargs: CalendarImportSelectionResult(
            True, True, {"name": "내 로컬 캘린더"}
        ),
    )
    dialog.save_settings()
    message = dialog.connection_feedback.text()
    assert "내 로컬 캘린더" in message
    module.QMessageBox.information.assert_not_called()


def test_missing_auth_is_reported_on_the_current_import_page(focused_dialog):
    dialog, parent, _ = focused_dialog
    parent.gcal_sync.is_authenticated = False
    dialog._load_accessible_calendars()
    assert dialog.calendar_choice_hint.text() == dialog.test_access_result.text()
    assert dialog.go_to_auth_btn.isVisible()
    assert dialog._query_worker is None


def test_refresh_does_not_change_timezone_from_hidden_legacy_combo(focused_dialog):
    dialog, _, _ = focused_dialog
    dialog._populate_timezones("Asia/Seoul")
    dialog._set_calendar_choices(
        [
            {
                "id": "team",
                "summary": "팀 캘린더",
                "accessRole": "owner",
                "timeZone": "America/New_York",
            }
        ]
    )
    assert dialog._current_timezone() == "Asia/Seoul"


def test_new_remote_calendars_start_unselected_after_explicit_import_choice(
    focused_dialog, monkeypatch
):
    from calendar_app.infrastructure.db import calendar_repo

    dialog, _, _ = focused_dialog
    save = Mock(return_value=True)
    monkeypatch.setattr(calendar_repo, "upsert_calendar", save)
    dialog._refresh_google_calendar_list(
        notify=False, calendars=[{"id": "new", "summary": "새 캘린더", "accessRole": "owner"}]
    )
    assert save.call_args.kwargs["is_active"] is False


def _account_switch_fixture(focused_dialog, monkeypatch):
    from calendar_app.infrastructure.db import calendar_repo

    dialog, parent, rows = focused_dialog
    parent.settings.setValue("gcal_primary_resolved_id", "old@example.com")
    parent.settings.setValue("gcal_calendar_id", "primary")
    parent.gcal_sync.calendar_id = "primary"
    parent.schedule_panel_refresh = Mock()
    parent.sync_google_calendar_silent = Mock()
    save = Mock(return_value=True)
    monkeypatch.setattr(calendar_repo, "upsert_calendar", save)
    calendars = [
        {"id": "new@example.com", "summary": "New account", "accessRole": "owner", "primary": True}
    ]
    return dialog, parent, rows, save, calendars


def test_account_change_rejects_metadata_before_choices_or_writes(focused_dialog, monkeypatch):
    dialog, parent, rows, save, calendars = _account_switch_fixture(focused_dialog, monkeypatch)
    original_choices = list(dialog._calendar_choices)
    original_rows = [dict(row) for row in rows]
    assert dialog._refresh_google_calendar_list(notify=False, calendars=calendars) is False
    save.assert_not_called()
    parent.schedule_panel_refresh.assert_not_called()
    parent.sync_google_calendar_silent.assert_not_called()
    assert dialog._calendar_choices == original_choices
    assert rows == original_rows
    assert parent.settings.value("gcal_primary_resolved_id") == "old@example.com"
    assert parent.settings.value("gcal_calendar_id") == "primary"
    assert parent.settings.value("sync_google_last_error") == "account_mismatch"
    assert "계정" in dialog.calendar_choice_hint.text()
    assert dialog.test_access_result.text() == dialog.calendar_choice_hint.text()
    assert parent.gcal_sync._account_identity_mismatch


@pytest.mark.parametrize("kind", ["import", "test"])
def test_account_change_query_returns_to_enabled_ui_without_import(
    focused_dialog, monkeypatch, kind
):
    dialog, parent, _, save, calendars = _account_switch_fixture(focused_dialog, monkeypatch)
    worker = SimpleNamespace(
        calendars=calendars, success=True, is_cancelled=lambda: False, deleteLater=Mock()
    )
    dialog._query_kind = kind
    dialog._query_worker = worker
    parent._bg_workers.append(worker)
    dialog.save_btn.setEnabled(False)
    dialog.load_calendars_btn.setEnabled(False)
    dialog._finish_calendar_query()
    save.assert_not_called()
    assert dialog._query_worker is None
    assert worker not in parent._bg_workers
    worker.deleteLater.assert_called_once()
    assert not dialog.save_btn.isEnabled() and dialog.load_calendars_btn.isEnabled()
    assert not dialog._auth_calendars_loaded
    assert parent.settings.value("sync_google_last_error") == "account_mismatch"
    assert "계정" in dialog.test_access_result.text()


def test_account_change_auth_preserves_previous_service_and_token(focused_dialog, monkeypatch):
    from calendar_app.infrastructure.google_sync import token_store

    dialog, parent, _, save, calendars = _account_switch_fixture(focused_dialog, monkeypatch)
    original_service = parent.gcal_sync
    candidate = SimpleNamespace(
        _pending_token_json="synthetic new account token", _set_last_error=Mock()
    )
    worker = SimpleNamespace(
        calendars=calendars,
        service=candidate,
        success=True,
        is_cancelled=lambda: False,
        deleteLater=Mock(),
    )
    dialog._auth_worker = worker
    parent._bg_workers.append(worker)
    token_save = Mock()
    monkeypatch.setattr(token_store, "save_token_json", token_save)
    dialog._finish_auth()
    token_save.assert_not_called()
    save.assert_not_called()
    assert parent.gcal_sync is original_service
    assert candidate._account_identity_mismatch
    assert candidate._pending_token_json is None
    assert dialog._auth_worker is None and worker not in parent._bg_workers
    assert dialog.auth_btn.isEnabled() and not dialog.save_btn.isEnabled()
    assert parent.settings.value("gcal_primary_resolved_id") == "old@example.com"
    assert parent.settings.value("sync_google_last_error") == "account_mismatch"
    module.QMessageBox.information.assert_not_called()


def test_verified_original_account_clears_mismatch_and_imports(focused_dialog, monkeypatch):
    dialog, parent, _, save, calendars = _account_switch_fixture(focused_dialog, monkeypatch)
    parent.gcal_sync._account_identity_mismatch = True
    parent.settings.setValue("sync_google_last_error", "account_mismatch")
    parent._calendar_sync_coordinator = SimpleNamespace(refresh=Mock())
    calendars[0]["id"] = "old@example.com"
    dialog._refresh_google_calendar_list(notify=False, calendars=calendars)
    save.assert_called_once()
    assert not parent.gcal_sync._account_identity_mismatch
    assert parent.settings.value("sync_google_last_error") == ""
    parent._calendar_sync_coordinator.refresh.assert_called()
    parent.sync_google_calendar_silent.assert_not_called()


def test_empty_discovery_does_not_clear_known_account_mismatch(focused_dialog, monkeypatch):
    dialog, parent, _, save, _ = _account_switch_fixture(focused_dialog, monkeypatch)
    parent.gcal_sync._account_identity_mismatch = True
    assert dialog._refresh_google_calendar_list(notify=False, calendars=[]) is False
    assert parent.gcal_sync._account_identity_mismatch
    save.assert_not_called()
    assert parent.settings.value("sync_google_last_error") == "account_mismatch"


def test_empty_discovery_with_historical_alias_requires_identity(focused_dialog, monkeypatch):
    dialog, parent, _, save, _ = _account_switch_fixture(focused_dialog, monkeypatch)
    original_choices = list(dialog._calendar_choices)
    assert dialog._refresh_google_calendar_list(notify=False, calendars=[]) is False
    save.assert_not_called()
    parent.sync_google_calendar_silent.assert_not_called()
    assert dialog._calendar_choices == original_choices
    assert parent.settings.value("gcal_primary_resolved_id") == "old@example.com"
    assert parent.settings.value("sync_google_last_error") == "account_unverified"
    assert "기존 연결" in dialog.test_access_result.text()


@pytest.mark.parametrize(
    "calendars",
    [
        [],
        [None],
        ["invalid-record"],
        [{"id": "team", "accessRole": "owner"}],
        [{"id": "primary", "primary": True}],
        [{"id": " ", "primary": True}],
        [{"id": 42, "primary": True}],
        [{"id": "new@example.com", "primary": "true"}],
        [{"id": "old@example.com", "primary": True}, {"id": "new@example.com", "primary": True}],
    ],
)
def test_auth_requires_verified_primary_before_replacing_credentials(
    focused_dialog, monkeypatch, calendars
):
    from calendar_app.infrastructure.google_sync import token_store

    dialog, parent, _, save, _ = _account_switch_fixture(focused_dialog, monkeypatch)
    original_service = parent.gcal_sync
    candidate = SimpleNamespace(_pending_token_json="synthetic token", _set_last_error=Mock())
    worker = SimpleNamespace(
        calendars=calendars,
        service=candidate,
        success=True,
        is_cancelled=lambda: False,
        deleteLater=Mock(),
    )
    dialog._auth_worker = worker
    parent._bg_workers.append(worker)
    token_save = Mock()
    monkeypatch.setattr(token_store, "save_token_json", token_save)
    dialog._finish_auth()
    token_save.assert_not_called()
    save.assert_not_called()
    assert parent.gcal_sync is original_service
    assert candidate._pending_token_json is None
    assert parent.settings.value("gcal_primary_resolved_id") == "old@example.com"
    assert parent.settings.value("sync_google_last_error") == "account_unverified"
    assert dialog.auth_btn.isEnabled() and not dialog.save_btn.isEnabled()
    assert "기존 연결" in dialog.test_access_result.text()
    module.QMessageBox.information.assert_not_called()


def test_verified_auth_saves_token_and_completes_normal_ui(focused_dialog, monkeypatch):
    from calendar_app.infrastructure.google_sync import token_store

    dialog, parent, _, save, calendars = _account_switch_fixture(focused_dialog, monkeypatch)
    calendars[0]["id"] = "old@example.com"
    candidate = SimpleNamespace(
        _pending_token_json="synthetic token",
        _set_last_error=Mock(),
        is_authenticated=True,
        service=object(),
        calendar_id="primary",
        time_zone="Asia/Seoul",
    )
    worker = SimpleNamespace(
        calendars=calendars,
        service=candidate,
        success=True,
        is_cancelled=lambda: False,
        deleteLater=Mock(),
    )
    dialog._auth_worker = worker
    parent._bg_workers.append(worker)
    token_save = Mock()
    monkeypatch.setattr(token_store, "save_token_json", token_save)
    dialog._finish_auth()
    token_save.assert_called_once_with("synthetic token")
    assert candidate._pending_token_json is None
    assert parent.gcal_sync is candidate
    save.assert_called_once()
    assert dialog._auth_calendars_loaded
    assert dialog.auth_btn.isEnabled() and not dialog.save_btn.isEnabled()
    assert dialog._stack.currentIndex() == 1
    module.QMessageBox.information.assert_not_called()


@pytest.mark.parametrize("outcome", ["cancelled", "closed", "token_save_failed"])
def test_auth_completion_failure_discards_candidate_and_keeps_connection(
    focused_dialog, monkeypatch, outcome
):
    from calendar_app.infrastructure.google_sync import token_store

    dialog, parent, _, save, calendars = _account_switch_fixture(focused_dialog, monkeypatch)
    calendars[0]["id"] = "old@example.com"
    original_service = parent.gcal_sync
    candidate = SimpleNamespace(
        _pending_token_json="synthetic token",
        last_error_kind=None,
        is_authenticated=True,
        service=object(),
        calendar_id="primary",
        time_zone="Asia/Seoul",
    )
    candidate._set_last_error = Mock(
        side_effect=lambda kind, message: setattr(candidate, "last_error_kind", kind)
    )
    worker = SimpleNamespace(
        calendars=calendars,
        service=candidate,
        success=True,
        is_cancelled=lambda: outcome == "cancelled",
        deleteLater=Mock(),
    )
    dialog._auth_worker = worker
    parent._bg_workers.append(worker)
    if outcome == "closed":
        dialog._auth_close_result = QDialog.DialogCode.Rejected
    token_save = Mock(side_effect=OSError("Synthetic token store failure"))
    monkeypatch.setattr(token_store, "save_token_json", token_save)
    monkeypatch.setattr(module.QMessageBox, "warning", Mock())
    dialog._finish_auth()
    if outcome == "token_save_failed":
        token_save.assert_called_once()
        assert candidate.last_error_kind == "auth_token_write"
    else:
        token_save.assert_not_called()
    save.assert_not_called()
    assert candidate._pending_token_json is None
    assert parent.gcal_sync is original_service
    assert dialog._auth_worker is None and worker not in parent._bg_workers
    assert dialog.auth_btn.isEnabled() and not dialog.save_btn.isEnabled()
    assert parent.settings.value("gcal_primary_resolved_id") == "old@example.com"
    module.QMessageBox.information.assert_not_called()
