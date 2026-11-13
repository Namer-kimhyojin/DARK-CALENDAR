# -*- coding: utf-8 -*-
"""Disconnects, account recovery and in-flight subscription edits retain their scope."""

import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QObject, pyqtSignal
import pytest

from calendar_app.infrastructure.calendar_sync.repository import CalendarSyncRepository
from calendar_app.infrastructure.calendar_sync.status import (
    load_calendar_errors,
    save_calendar_errors,
)
from calendar_app.presentation.main_window import calendar_sync_coordinator as module
from tests.test_calendar_sync_coordinator import ui as coordinated_ui  # noqa: F401
from tests.test_sync_controller_lifecycle import controller  # noqa: F401


def _registered_calendars(controller):
    _, host, ctrl, prefix, provider_module, _ = controller
    conn = sqlite3.connect(provider_module.DB_PATH)
    repo = CalendarSyncRepository(conn, "outlook" if prefix == "outlook_" else "caldav")
    own = repo.register("old-account", {"id": "own", "name": "Own", "can_edit": True})
    other = repo.register("other-account", {"id": "other", "name": "Other", "can_edit": True})
    with conn:
        conn.execute("INSERT INTO unified_task(id,calendar_id) VALUES(1,?)", (own,))
        conn.execute(
            "INSERT INTO calendar_sync_pending_delete(calendar_id,transaction_id,baseline) "
            "VALUES(?,'pending','baseline')",
            (own,),
        )
        conn.execute(
            "INSERT INTO calendar_sync_delete_queue(calendar_id,event_id,etag) "
            "VALUES(?,'event','revision')",
            (own,),
        )
    host.settings.setValue(prefix + "enabled", True)
    conn.row_factory = None
    return conn, own, other


def _disconnect_worker(controller, monkeypatch):
    _, _, _, prefix, provider_module, _ = controller
    remove = Mock()
    if prefix == "outlook_":

        class CacheFolder:
            def __truediv__(self, _filename):
                return SimpleNamespace(unlink=remove)

        monkeypatch.setattr(provider_module, "get_app_data_dir", CacheFolder)
        worker = provider_module.OutlookWorker(
            "disconnect", "11111111-1111-1111-1111-111111111111", "old-account", None
        )
    else:
        monkeypatch.setattr(
            provider_module, "CalDAVCredentials", lambda: SimpleNamespace(remove=remove)
        )
        worker = provider_module.CalDAVWorker(
            prefix.removeprefix("caldav_").removesuffix("_"), "disconnect", "old-account", None
        )
    return worker, remove


def test_successful_disconnect_revokes_only_its_account_and_preserves_pending_work(
    controller, monkeypatch
):
    _, host, ctrl, prefix, _, _ = controller
    conn, own, other = _registered_calendars(controller)
    try:
        worker, remove = _disconnect_worker(controller, monkeypatch)
        worker.result.connect(ctrl._result)
        worker.run()
        remove.assert_called_once()
        assert ctrl.status == "disconnected"
        assert not host.settings.value(prefix + "account_id")
        assert conn.execute(
            "SELECT is_active,access_role FROM calendar WHERE id=?", (own,)
        ).fetchone() == (0, "reader")
        assert conn.execute(
            "SELECT can_edit FROM calendar_sync_calendar WHERE local_id=?", (own,)
        ).fetchone() == (0,)
        assert conn.execute(
            "SELECT is_active,access_role FROM calendar WHERE id=?", (other,)
        ).fetchone() == (1, "writer")
        assert conn.execute("SELECT calendar_id FROM unified_task WHERE id=1").fetchone() == (own,)
        assert conn.execute("SELECT COUNT(*) FROM calendar_sync_pending_delete").fetchone() == (1,)
        assert conn.execute("SELECT COUNT(*) FROM calendar_sync_delete_queue").fetchone() == (1,)
    finally:
        conn.close()


def test_disconnect_revocation_is_durable_before_completion_is_delivered(controller, monkeypatch):
    conn, own, _ = _registered_calendars(controller)
    try:
        worker, remove = _disconnect_worker(controller, monkeypatch)
        results = []
        worker.result.connect(lambda operation, result: results.append((operation, result)))
        worker.run()
        assert results and results[0][0] == "disconnect"
        remove.assert_called_once()
        # Shutdown can ignore a queued UI signal. Permissions must already be safe.
        assert conn.execute(
            "SELECT is_active,access_role FROM calendar WHERE id=?", (own,)
        ).fetchone() == (0, "reader")
    finally:
        conn.close()


def test_credential_removal_failure_rolls_back_disconnect_permissions(controller, monkeypatch):
    conn, own, _ = _registered_calendars(controller)
    try:
        worker, remove = _disconnect_worker(controller, monkeypatch)
        remove.side_effect = OSError("synthetic credential storage failure")
        failures, results = [], []
        worker.failed.connect(failures.append)
        worker.result.connect(lambda *args: results.append(args))
        worker.run()
        assert failures == ["operation_failed"]
        assert not results
        assert conn.execute(
            "SELECT is_active,access_role FROM calendar WHERE id=?", (own,)
        ).fetchone() == (1, "writer")
    finally:
        conn.close()


def test_database_lock_prevents_disconnect_from_removing_credentials(controller, monkeypatch):
    _, _, _, _, provider_module, _ = controller
    conn, _, _ = _registered_calendars(controller)
    try:
        conn.execute("BEGIN IMMEDIATE")
        worker, remove = _disconnect_worker(controller, monkeypatch)
        real_connect = sqlite3.connect
        monkeypatch.setattr(
            provider_module.sqlite3, "connect", lambda path, **kwargs: real_connect(path, timeout=0)
        )
        failures = []
        worker.failed.connect(failures.append)
        worker.run()
        assert failures == ["operation_failed"]
        remove.assert_not_called()
    finally:
        conn.rollback()
        conn.close()


def test_deactivation_respects_an_existing_transaction(controller):
    conn, own, _ = _registered_calendars(controller)
    try:
        repo = CalendarSyncRepository(conn)
        conn.execute("BEGIN IMMEDIATE")
        repo.deactivate("old-account")
        assert conn.in_transaction
        conn.rollback()
        assert tuple(
            conn.execute("SELECT is_active,access_role FROM calendar WHERE id=?", (own,)).fetchone()
        ) == (1, "writer")
    finally:
        conn.close()


def test_failed_disconnect_keeps_account_selection_and_permissions(controller):
    _, host, ctrl, prefix, _, _ = controller
    conn, own, _ = _registered_calendars(controller)
    try:
        ctrl.worker = SimpleNamespace(operation="disconnect", retry_after=None)
        ctrl._failed("operation_failed")
        ctrl.worker = None
        assert host.settings.value(prefix + "account_id") == "old-account"
        assert host.settings.value(prefix + "enabled", type=bool)
        assert conn.execute(
            "SELECT is_active,access_role FROM calendar WHERE id=?", (own,)
        ).fetchone() == (1, "writer")
    finally:
        ctrl.worker = None
        conn.close()


@pytest.mark.parametrize("operation", ["login", "disconnect"])
def test_account_change_clears_previous_accounts_summary_and_success_time(controller, operation):
    _, host, ctrl, prefix, _, login = controller
    ctrl.summary = {"issues": 7, "created": 3}
    host.settings.setValue(prefix + "last_success", "previous-account-success")
    ctrl._result(operation, login if operation == "login" else {})
    assert ctrl.summary == {}
    assert not host.settings.value(prefix + "last_success")


def test_same_account_reauthentication_keeps_unresolved_calendar_failures(controller):
    _, host, ctrl, prefix, _, login = controller
    key = ("outlook" if prefix == "outlook_" else "caldav") + "::invalid"
    errors = {key: "invalid_event_time"}
    save_calendar_errors(host.settings, prefix, errors)
    ctrl.summary = {"issues": 1}
    host.settings.setValue(prefix + "last_success", "previous-success")
    ctrl._result("login", {**login, "account": "old-account"})
    assert load_calendar_errors(host.settings, prefix) == errors
    assert ctrl.summary == {"issues": 1}
    assert host.settings.value(prefix + "last_success") == "previous-success"


def test_rejected_outlook_disconnect_preserves_selection_and_automatic_sync(tmp_path, monkeypatch):
    from calendar_app.presentation.dialogs import outlook_settings_dialog
    from tests.test_outlook_settings_dialog import Controller, database, host

    app, window = host(tmp_path)
    path = tmp_path / "calendar.db"
    database(path)
    monkeypatch.setattr(outlook_settings_dialog, "DB_PATH", str(path))
    window.settings.setValue("outlook_account_id", "microsoft::test")
    window.settings.setValue("outlook_enabled", True)
    ctrl = Controller()
    ctrl.start.return_value = False
    with sqlite3.connect(path) as conn:
        key = CalendarSyncRepository(conn).register("microsoft::test", ctrl.available[0])
    dialog = outlook_settings_dialog.OutlookSettingsDialog(window, ctrl)
    try:
        dialog._disconnect()
        with sqlite3.connect(path) as conn:
            assert conn.execute(
                "SELECT is_active,access_role FROM calendar WHERE id=?", (key,)
            ).fetchone() == (1, "writer")
        assert window.settings.value("outlook_enabled", type=bool)
    finally:
        dialog.close()
        window.close()
        app.processEvents()


@pytest.fixture
def subscriptions(coordinated_ui, monkeypatch):
    ui = coordinated_ui
    created = []

    class Worker(QObject):
        result = pyqtSignal(object)
        finished = pyqtSignal()

        def __init__(self, calendars, parent, zone):
            super().__init__(parent)
            self.calendars = [dict(row) for row in calendars]
            self.running, self.cancelled = False, False
            self.deleteLater = Mock()
            created.append(self)

        def start(self):
            self.running = True

        def is_cancelled(self):
            return self.cancelled

        def requestInterruption(self):
            self.cancelled = True

        def wait(self, _milliseconds):
            return not self.running

        def finish(self):
            self.running = False
            self.finished.emit()

    monkeypatch.setattr(module, "IcsSyncWorker", Worker)

    def add(key):
        with sqlite3.connect(ui.path) as conn:
            conn.execute(
                "INSERT INTO calendar(id,type,name,ics_url) VALUES(?,'ics',?,?)",
                (key, key, "https://example.invalid/" + key + ".ics"),
            )

    add("ics::first")
    add("ics::second")
    ui.coordinator.refresh()
    yield SimpleNamespace(ui=ui, created=created, add=add)
    ui.coordinator.stop()
    while ui.coordinator.ics_worker:
        ui.coordinator.ics_worker.finish()


def test_edited_subscription_is_refetched_after_inflight_worker_with_current_address(subscriptions):
    ui, created = subscriptions.ui, subscriptions.created
    assert ui.coordinator.sync_ics(force=True, calendar_ids=["ics::first"])
    with sqlite3.connect(ui.path) as conn:
        conn.execute(
            "UPDATE calendar SET ics_url='https://example.invalid/replacement.ics' "
            "WHERE id='ics::first'"
        )
    assert ui.coordinator.sync_ics(force=True, calendar_ids=["ics::first"])
    assert len(created) == 1
    created[0].finish()
    assert len(created) == 2
    assert created[1].calendars[0]["ics_url"] == "https://example.invalid/replacement.ics"
    created[1].finish()
    assert ui.coordinator.ics_worker is None
    assert not ui.host._bg_workers


def test_targeted_requests_are_coalesced_and_remain_manual_while_auto_is_paused(subscriptions):
    ui, created = subscriptions.ui, subscriptions.created
    ui.host.settings.setValue("sync_ics_auto", False)
    assert ui.coordinator.sync_ics(force=True, calendar_ids=["ics::first"])
    for key in ("ics::first", "ics::second", "ics::first"):
        assert ui.coordinator.sync_ics(force=True, calendar_ids=[key])
    created[0].finish()
    assert len(created) == 2
    assert {row["id"] for row in created[1].calendars} == {"ics::first", "ics::second"}
    created[1].finish()
    assert len(created) == 2


@pytest.mark.parametrize("change", ["removed", "inactive"])
def test_queued_refresh_rechecks_subscription_existence_and_activation(subscriptions, change):
    ui, created = subscriptions.ui, subscriptions.created
    assert ui.coordinator.sync_ics(force=True, calendar_ids=["ics::first"])
    assert ui.coordinator.sync_ics(force=True, calendar_ids=["ics::second"])
    with sqlite3.connect(ui.path) as conn:
        conn.execute(
            "DELETE FROM calendar WHERE id='ics::second'"
            if change == "removed"
            else "UPDATE calendar SET is_active=0 WHERE id='ics::second'"
        )
    created[0].finish()
    assert len(created) == 1
    assert ui.coordinator.ics_worker is None


def test_stopping_clears_pending_refresh_without_restarting_a_worker(subscriptions):
    ui, created = subscriptions.ui, subscriptions.created
    assert ui.coordinator.sync_ics(force=True, calendar_ids=["ics::first"])
    assert ui.coordinator.sync_ics(force=True, calendar_ids=["ics::second"])
    ui.coordinator.stop()
    created[0].finish()
    assert len(created) == 1
    assert ui.coordinator.ics_worker is None


def test_worker_cancellation_does_not_restart_with_queued_subscription(subscriptions):
    ui, created = subscriptions.ui, subscriptions.created
    assert ui.coordinator.sync_ics(force=True, calendar_ids=["ics::first"])
    assert ui.coordinator.sync_ics(force=True, calendar_ids=["ics::second"])
    created[0].requestInterruption()
    created[0].finish()

    assert len(created) == 1
    assert ui.coordinator.ics_worker is None
    assert not ui.host._bg_workers


def test_automatic_or_full_duplicate_requests_do_not_schedule_an_extra_round(subscriptions):
    ui, created = subscriptions.ui, subscriptions.created
    assert ui.coordinator.sync_ics(force=True, calendar_ids=["ics::first"])
    assert not ui.coordinator.sync_ics(calendar_ids=["ics::second"])
    assert not ui.coordinator.sync_ics(force=True)
    created[0].finish()
    assert len(created) == 1
