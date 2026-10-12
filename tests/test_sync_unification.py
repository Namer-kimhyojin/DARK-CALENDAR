# -*- coding: utf-8 -*-
"""Subscription input, responsive metadata queries and toolbar geometry regressions."""

import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QSettings, Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QToolButton, QVBoxLayout, QWidget
import pytest

from calendar_app.infrastructure.ics.subscriptions import normalize_subscription_url
from calendar_app.presentation.dialogs.gcal_settings_dialog import GCalSettingsDialog
from calendar_app.presentation.dialogs.ics_subscription_dialog import IcsSubscriptionDialog


@pytest.fixture
def host(tmp_path):
    app = QApplication.instance() or QApplication([])
    parent = QWidget()
    parent.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    parent._bg_workers = []
    yield parent
    for worker in parent._bg_workers:
        worker.requestInterruption()
        worker.wait(2000)
    parent.close()
    app.processEvents()


@pytest.mark.parametrize(
    "value",
    [
        "file:///feed.ics",
        "https://user:pass@x.invalid/feed",
        "https://x.invalid:abc",
        "https://x.invalid/feed\n?q=secret",
        "javascript:alert(1)",
        "",
        "https:///feed",
        "https://x.invalid:0/feed",
    ],
)
def test_invalid_subscription_url_is_rejected(value):
    with pytest.raises(ValueError, match="invalid_subscription_url"):
        normalize_subscription_url(value)


def test_url_normalization_preserves_signed_query():
    assert (
        normalize_subscription_url(" webcal://EXAMPLE.invalid:443/feed.ics?token=A%2FB&v=2#ignore ")
        == "https://example.invalid/feed.ics?token=A%2FB&v=2"
    )


def test_subscription_dialog_validates_both_fields_without_persisting(host):
    dialog = IcsSubscriptionDialog(host)
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    dialog.name.setText("Holidays")
    dialog.url.setText("file:///private.ics")
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    dialog.url.setText("webcal://EXAMPLE.invalid/feed.ics")
    dialog.accept()
    assert dialog.subscription_name == "Holidays"
    assert dialog.subscription_url == "https://example.invalid/feed.ics"
    dialog.close()


def test_google_dialog_initialization_does_not_query_network(host):
    host.gcal_sync = SimpleNamespace(
        is_authenticated=True,
        service=Mock(),
        list_accessible_calendars=Mock(side_effect=AssertionError("UI thread network")),
    )
    dialog = GCalSettingsDialog(host)
    host.gcal_sync.list_accessible_calendars.assert_not_called()
    host.gcal_sync.service.calendarList.assert_not_called()
    dialog.close()


def test_invalid_google_timezone_is_not_saved_or_used_for_auth(host, monkeypatch):
    dialog = GCalSettingsDialog(host)
    dialog.enable_cb.setChecked(False)
    dialog.timezone_combo.setEditText("Invalid/Zone")
    dialog.save_settings()
    assert host.settings.value("gcal_timezone") is None
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.timezone_preview.text()
    check = Mock(side_effect=AssertionError("Auth must not start with invalid timezone"))
    monkeypatch.setattr(dialog, "_copy_credentials_if_needed", check)
    dialog.run_auth()
    assert dialog._auth_worker is None
    check.assert_not_called()
    dialog.close()


def test_google_query_keeps_ui_responsive_and_close_cancels(host):
    started = threading.Event()

    def query(**kwargs):
        started.set()
        while not kwargs["is_cancelled"]():
            time.sleep(0.005)
        return []

    host.gcal_sync = SimpleNamespace(
        is_authenticated=True, service=object(), list_accessible_calendars=query, last_error_kind=""
    )
    dialog = GCalSettingsDialog(host)
    dialog.show()
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(5)
    dialog._load_accessible_calendars()
    for _ in range(100):
        QTest.qWait(10)
        if started.is_set() and len(ticks) >= 3:
            break
    assert started.is_set() and len(ticks) >= 2
    assert not dialog.save_btn.isEnabled()
    dialog.reject()
    for _ in range(200):
        QTest.qWait(10)
        if dialog._query_worker is None:
            break
    assert dialog._query_worker is None
    assert host._bg_workers == []
    assert not dialog.isVisible()
    timer.stop()
    dialog.close()


def test_google_metadata_refresh_preserves_user_preferences_and_sync_token(host, monkeypatch):
    from calendar_app.infrastructure.db import calendar_repo

    host.gcal_sync = SimpleNamespace(is_authenticated=True, service=object())
    host.schedule_panel_refresh = Mock()
    host.sync_google_calendar_silent = Mock()
    host.settings.setValue("gcal_sync_token::team", "incremental-token")
    monkeypatch.setattr(
        calendar_repo,
        "list_calendars",
        lambda **kwargs: [
            {
                "id": "gcal::team",
                "color": "#123456",
                "is_default": 1,
                "is_visible": 0,
                "is_active": 0,
                "sort_order": 7,
            }
        ],
    )
    save = Mock(return_value=True)
    monkeypatch.setattr(calendar_repo, "upsert_calendar", save)
    dialog = GCalSettingsDialog(host)
    dialog._refresh_google_calendar_list(
        notify=False,
        calendars=[{"id": "team", "summary": "Team", "primary": True, "accessRole": "owner"}],
    )
    saved = save.call_args.kwargs
    assert saved["is_default"] and not saved["is_visible"] and not saved["is_active"]
    assert saved["color"] == "#123456" and saved["sort_order"] == 7
    assert host.settings.value("gcal_sync_token::team") == "incremental-token"
    dialog.close()


def test_google_disconnect_preserves_ics_subscriptions(host, monkeypatch):
    from calendar_app.infrastructure.db import calendar_repo, task_repo

    host.gcal_sync = SimpleNamespace(is_authenticated=True, service=object())
    monkeypatch.setattr(
        calendar_repo,
        "list_calendars",
        lambda **kwargs: [
            {"id": "ics::keep", "type": "ics"},
            {"id": "gcal::remove", "type": "gcal"},
            {"id": "local::keep", "type": "local"},
        ],
    )
    remove = Mock(return_value=True)
    monkeypatch.setattr(calendar_repo, "delete_calendar", remove)
    monkeypatch.setattr(task_repo, "list_gcal_subscriptions", lambda **kwargs: [])
    monkeypatch.setattr(task_repo, "clear_gcal_delete_queue", lambda: None)
    host.settings.setValue("sync_ics_error_codes", {"ics::keep": "network_unavailable"})
    dialog = GCalSettingsDialog(host)
    dialog._complete_reset_auth(notify=False)
    remove.assert_called_once_with("gcal::remove")
    assert host.settings.value("sync_ics_error_codes") == {"ics::keep": "network_unavailable"}
    assert host.settings.value("gcal_enabled") == "false"
    dialog.close()


def test_google_disconnect_runs_off_ui_thread_and_close_finishes_local_cleanup(host, monkeypatch):
    from calendar_app.presentation.dialogs import gcal_settings_dialog as module

    started, release = threading.Event(), threading.Event()

    def revoke():
        started.set()
        release.wait(2)
        return False  # Offline revocation must not prevent the authorized local disconnect.

    host.gcal_sync = SimpleNamespace(is_authenticated=True, service=object(), revoke_token=revoke)
    monkeypatch.setattr(
        module.QMessageBox, "warning", lambda *args: module.QMessageBox.StandardButton.Yes
    )
    dialog = GCalSettingsDialog(host)
    dialog.show()
    dialog.reset_auth()
    for _ in range(100):
        QTest.qWait(10)
        if started.is_set():
            break
    assert started.is_set()
    assert not dialog.reset_btn.isEnabled()
    dialog.reject()
    assert dialog._query_worker is not None
    release.set()
    for _ in range(200):
        QTest.qWait(10)
        if dialog._query_worker is None:
            break
    assert dialog._query_worker is None and not dialog.isVisible()
    assert host.settings.value("gcal_enabled") == "false"
    assert host._bg_workers == [] and not host.gcal_sync.is_authenticated
    dialog.close()


def test_toolbar_sync_opens_hub_and_status_has_separate_geometry(host, monkeypatch):
    from calendar_app.presentation.main_window import top_bar_builder as module

    monkeypatch.setattr(module, "build_top_left_menus", lambda *args: None)
    monkeypatch.setattr(module, "apply_top_menu_theme", lambda *args, **kwargs: None)
    for name in (
        "sync_calendars",
        "open_calendar_sync_hub",
        "open_calendar_sync_issues",
        "toggle_lock_mode",
        "toggle_magnet_mode",
        "handle_search_changed",
        "toggle_widget_mode_panel",
    ):
        setattr(host, name, Mock())
    module.setup_top_bar(host, 12, "#4da6ff", lambda value: "#4da6ff")
    layout = QVBoxLayout(host)
    layout.addWidget(host.top_bar_frame)
    host.resize(850, 100)
    host.show()
    QApplication.processEvents()
    button = host.sync_action_btn
    assert button.width() >= button.iconSize().width() + 8
    assert button.menu() is None
    assert host.top_bar_frame.findChild(QToolButton, "SyncToolbarMenu") is None
    assert not host.sync_status_lbl.isVisible() and host.sync_status_lbl.width() == 0
    for text in ("로컬 모드", "동기화 중 5", "동기화 확인 필요", "Sync needs attention"):
        host.sync_status_text_lbl.setText(text)
        QApplication.processEvents()
        assert button.geometry().right() < host.sync_status_text_lbl.geometry().left()
        assert (
            host.sync_status_text_lbl.width()
            >= host.sync_status_text_lbl.fontMetrics().horizontalAdvance(text)
        )
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    QTest.keyClick(button, Qt.Key.Key_Space)
    assert host.open_calendar_sync_hub.call_count == 2
    host.sync_calendars.assert_not_called()
    assert host.top_bar_frame.isVisible()
