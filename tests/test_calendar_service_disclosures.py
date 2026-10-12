# -*- coding: utf-8 -*-
"""Independent service disclosures preserve drafts, active connections and policy."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QCoreApplication, QEvent, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QPushButton, QScrollArea
import pytest

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.calendar_sync_hub import CalendarSyncHub
from calendar_app.presentation.main_window import calendar_sync_coordinator as sync_module
from tests.test_calendar_sync_redesign import sync_ui  # noqa: F401

EXTRA_PROVIDERS = ("outlook", "icloud", "naver")


@pytest.fixture
def disclosure_ui(sync_ui, monkeypatch):
    sync_ui.host.settings.setValue("gcal_timezone", "Asia/Seoul")
    worker_start = Mock()
    monkeypatch.setattr(sync_module.IcsSyncWorker, "start", worker_start)
    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *error: errors.append(error))
    hub = CalendarSyncHub(sync_ui.host, section="services")
    hub.resize(1100, 850)
    hub.show()
    sync_ui.qapp.processEvents()
    yield SimpleNamespace(**vars(sync_ui), hub=hub, worker_start=worker_start)
    hub.close()
    hub.deleteLater()
    sync_ui.qapp.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not errors, [str(error[1]) for error in errors]
    worker_start.assert_not_called()
    sync_ui.host.sync_google_calendar.assert_not_called()


def prefix_for(provider):
    return "outlook_" if provider == "outlook" else "caldav_" + provider + "_"


def activate(ui, button, action="mouse"):
    ancestor = button.parentWidget()
    while ancestor is not None and not isinstance(ancestor, QScrollArea):
        ancestor = ancestor.parentWidget()
    if ancestor is not None:
        ancestor.ensureWidgetVisible(button)
    ui.qapp.processEvents()
    assert button.isVisible() and button.isEnabled()
    if action == "keyboard":
        button.setFocus()
        QTest.keyClick(button, Qt.Key.Key_Space)
    else:
        QTest.mouseClick(button, Qt.MouseButton.LeftButton, pos=button.rect().center())
    ui.qapp.processEvents()


@pytest.mark.parametrize("action", ["mouse", "keyboard"])
def test_disclosures_toggle_independently_and_update_their_action_labels(disclosure_ui, action):
    ui, hub = disclosure_ui, disclosure_ui.hub
    common_closed, services_closed = hub.advanced_toggle.text(), hub.more_services.text()
    assert not hub.advanced_toggle.isChecked()
    assert hub.advanced.isHidden()
    assert not hub.more_services.isChecked()
    assert all(hub.service_cards[provider].isHidden() for provider in EXTRA_PROVIDERS)

    activate(ui, hub.advanced_toggle, action)
    assert hub.advanced_toggle.isChecked()
    assert not hub.advanced.isHidden()
    assert hub.advanced_toggle.text() != common_closed
    assert hub.advanced_toggle.accessibleName() == hub.advanced_toggle.text()
    assert hub.more_services.text() == services_closed
    assert all(hub.service_cards[provider].isHidden() for provider in EXTRA_PROVIDERS)

    activate(ui, hub.more_services, action)
    assert hub.more_services.isChecked()
    assert hub.more_services.text() != services_closed
    assert hub.more_services.accessibleName() == hub.more_services.text()
    assert not hub.advanced.isHidden()
    assert all(not hub.service_cards[provider].isHidden() for provider in EXTRA_PROVIDERS)

    activate(ui, hub.advanced_toggle, action)
    assert hub.advanced.isHidden()
    assert hub.advanced_toggle.text() == common_closed
    assert hub.advanced_toggle.accessibleName() == hub.advanced_toggle.text()
    assert all(not hub.service_cards[provider].isHidden() for provider in EXTRA_PROVIDERS)
    activate(ui, hub.more_services, action)
    assert hub.more_services.text() == services_closed
    assert hub.more_services.accessibleName() == hub.more_services.text()
    assert all(hub.service_cards[provider].isHidden() for provider in EXTRA_PROVIDERS)


def test_timezone_draft_survives_service_toggle_refresh_and_common_settings_collapse(disclosure_ui):
    ui, hub = disclosure_ui, disclosure_ui.hub
    activate(ui, hub.advanced_toggle)
    hub.timezone.setEditText("Europe/Paris")
    activate(ui, hub.more_services)
    activate(ui, hub.more_services)
    activate(ui, hub.advanced_toggle)
    ui.coordinator.refresh()
    activate(ui, hub.advanced_toggle)
    assert hub.timezone.currentText() == "Europe/Paris"
    assert ui.host.settings.value("gcal_timezone") == "Asia/Seoul"
    assert not hub.more_services.isChecked()
    assert hub.advanced_toggle.isChecked()


@pytest.mark.parametrize("provider", EXTRA_PROVIDERS)
@pytest.mark.parametrize("state", ["connected", "busy", "failed"])
def test_collapsing_additional_accounts_keeps_an_active_or_failed_service_visible(
    disclosure_ui, provider, state
):
    ui, hub = disclosure_ui, disclosure_ui.hub
    controller = ui.coordinator.controllers()[provider]
    if state == "connected":
        ui.host.settings.setValue(
            prefix_for(provider) + "account_id", "fixture-account-" + provider
        )
    elif state == "busy":
        controller.busy = True
    else:
        controller.status = "network_unavailable"
    ui.coordinator.refresh()
    activate(ui, hub.more_services)
    activate(ui, hub.more_services)
    assert not hub.more_services.isChecked()
    assert not hub.service_cards[provider].isHidden()
    assert hub.labels[provider].text()
    assert all(
        hub.service_cards[other].isHidden() for other in EXTRA_PROVIDERS if other != provider
    )
    assert not hub.more_services_header.isHidden()
    assert not hub.advanced_toggle.isChecked()


def test_all_connected_services_hide_only_the_additional_accounts_header(disclosure_ui):
    ui, hub = disclosure_ui, disclosure_ui.hub
    for provider in EXTRA_PROVIDERS:
        ui.host.settings.setValue(
            prefix_for(provider) + "account_id", "fixture-account-" + provider
        )
    ui.coordinator.refresh()
    assert hub.more_services_header.isHidden()
    assert all(not hub.service_cards[provider].isHidden() for provider in EXTRA_PROVIDERS)
    assert hub.advanced_toggle.isVisible()
    activate(ui, hub.advanced_toggle)
    assert not hub.advanced.isHidden()
    assert all(not hub.service_cards[provider].isHidden() for provider in EXTRA_PROVIDERS)
    ui.host.settings.remove("caldav_naver_account_id")
    ui.coordinator.refresh()
    assert not hub.more_services_header.isHidden()
    assert hub.service_cards["naver"].isHidden()
    assert not hub.service_cards["outlook"].isHidden()
    assert not hub.service_cards["icloud"].isHidden()
    assert not hub.advanced.isHidden()


@pytest.mark.parametrize("zone,accepted", [("Asia/Tokyo", True), ("Invalid/Zone", False)])
def test_common_timezone_save_click_validates_before_changing_preferences(
    disclosure_ui, zone, accepted
):
    ui, hub = disclosure_ui, disclosure_ui.hub
    activate(ui, hub.advanced_toggle)
    hub.timezone.setEditText(zone)
    activate(ui, hub.save_timezone)
    assert ui.host.settings.value("gcal_timezone") == (zone if accepted else "Asia/Seoul")
    assert hub.timezone_feedback.text()
    assert hub.timezone.currentText() == zone
    assert hub.advanced_toggle.isChecked()
    if accepted:
        assert ui.host.gcal_sync.time_zone == zone
    else:
        assert not hasattr(ui.host.gcal_sync, "time_zone")


def test_timezone_save_keeps_the_draft_and_saved_value_while_a_service_is_busy(disclosure_ui):
    ui, hub = disclosure_ui, disclosure_ui.hub
    activate(ui, hub.advanced_toggle)
    hub.timezone.setEditText("Asia/Tokyo")
    ui.coordinator.controllers()["outlook"].busy = True
    ui.coordinator.refresh()
    activate(ui, hub.save_timezone)
    assert ui.host.settings.value("gcal_timezone") == "Asia/Seoul"
    assert hub.timezone.currentText() == "Asia/Tokyo"
    assert hub.timezone_feedback.text() == t(
        "sync_ui.wait_timezone", "진행 중인 동기화가 끝난 뒤 시간대를 변경하세요."
    )
    assert not hub.service_cards["outlook"].isHidden()


def test_global_auto_click_changes_only_connected_services_and_keeps_accounts(disclosure_ui):
    ui, hub = disclosure_ui, disclosure_ui.hub
    ui.add_calendar("ics::auto-policy")
    ui.host.settings.setValue("outlook_account_id", "fixture-outlook-account")
    ui.host.settings.setValue("caldav_icloud_enabled", False)
    ui.host.settings.setValue("caldav_naver_enabled", True)
    ui.coordinator.refresh()
    activate(ui, hub.advanced_toggle)

    def auto_button(enabled):
        label = (
            t("sync_unified.auto_resume", "자동 동기화 모두 켜기")
            if enabled
            else t("sync_unified.auto_pause", "자동 동기화 모두 끄기")
        )
        return next(
            button for button in hub.advanced.findChildren(QPushButton) if button.text() == label
        )

    for enabled in (False, True):
        activate(ui, auto_button(enabled))
        for key in ("sync_google_auto", "sync_ics_auto", "outlook_enabled"):
            assert ui.host.settings.value(key, type=bool) is enabled
        assert ui.host.settings.value("caldav_icloud_enabled", type=bool) is False
        assert ui.host.settings.value("caldav_naver_enabled", type=bool) is True
        assert ui.host.settings.value("outlook_account_id") == "fixture-outlook-account"
        assert ui.host.settings.value("gcal_enabled") == "true"
        assert ui.host.gcal_sync.is_authenticated
        assert hub.advanced_toggle.isChecked()
        assert not hub.more_services.isChecked()
    assert ui.host.update_gcal_sync_timer.call_count == 2
