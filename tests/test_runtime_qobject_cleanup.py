# -*- coding: utf-8 -*-
"""Orderly Qt disposal before interpreter exit, without deleting widget data."""

import json
from unittest.mock import Mock, call, patch

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QSettings, QThread, QTimer, QUrl
from PyQt6.QtNetwork import QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QVBoxLayout, QWidget
import pytest

from calendar_app import bootstrap
from calendar_app.infrastructure.runtime.network import NetworkManager
from calendar_app.infrastructure.weather.request_pool import pooled_weather_reply
from calendar_app.presentation.dialogs import dialog_chrome, dialog_shadow, dialog_styles
from calendar_app.presentation.main_window.action_handlers import ActionHandlersMixin
from calendar_app.presentation.widgets.overlay_manager import OverlayWidgetManager
from calendar_app.shared import app_lifecycle
from calendar_app.shared.app_lifecycle import EXITING_PROPERTY, mark_app_exiting


@pytest.fixture
def application():
    app = QApplication.instance() or QApplication([])
    previous_exiting = app.property(EXITING_PROPERTY)
    previous_complete = getattr(app, "_runtime_shutdown_complete", False)
    previous_quit = app.quitOnLastWindowClosed()
    app.setProperty(EXITING_PROPERTY, False)
    app._runtime_shutdown_complete = False
    app.setQuitOnLastWindowClosed(False)
    yield app
    app.setProperty(EXITING_PROPERTY, previous_exiting)
    app._runtime_shutdown_complete = previous_complete
    app.setQuitOnLastWindowClosed(previous_quit)
    NetworkManager.release()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_about_to_quit_disposes_ui_then_network_before_database_and_lock(application, tmp_path):
    events = []
    settings = QSettings(str(tmp_path / "widgets.ini"), QSettings.Format.IniFormat)
    host = QWidget()
    host.settings = settings
    manager = OverlayWidgetManager(host)
    inst_id = manager.add_instance("clock", "보존할 위젯")
    widget = manager.get_widget(inst_id)
    prefix = f"oi_{inst_id}_{widget._pref()}"
    manager.show_instance(inst_id)
    widget.move(211, 322)
    widget._set("font_size", 47)
    settings.setValue("unrelated_custom_value", "preserved")
    host.show()
    dialog = QDialog(host)
    dialog.setLayout(QVBoxLayout())
    dialog_chrome.ensure_dialog_chrome(dialog, settings=settings)
    shadow = dialog._dc_dialog_shadow_controller.surface
    network = NetworkManager.instance()
    qnam = network.qnam()
    assert network.parent() is application
    pump = QTimer(application)
    pump.start(200)
    application._sigint_pump = pump

    def shutdown():
        events.append("workers_and_widget_save")
        manager.shutdown()
        return True

    host.shutdown_background_workers = shutdown
    host.destroyed.connect(lambda: events.append("ui_destroyed"))
    network.destroyed.connect(lambda: events.append("network_destroyed"))

    def finalized():
        bootstrap._finalize_runtime(application, host)

    application.aboutToQuit.connect(finalized)
    try:
        with (
            patch(
                "calendar_app.presentation.main_window.action_handlers."
                "_save_window_layout_for_shutdown",
                side_effect=lambda _host: events.append("layout_save"),
            ),
            patch(
                "calendar_app.infrastructure.db.database_unified.db_manager.close_all_connections",
                side_effect=lambda: events.append("database_close"),
            ),
            patch(
                "calendar_app.presentation.main_window.action_handlers._release_single_instance_lock",
                side_effect=lambda _app: events.append("lock_release"),
            ),
        ):
            QTimer.singleShot(0, application.exit)
            assert application.exec() == 0
            bootstrap._finalize_runtime(application, host)
    finally:
        application.aboutToQuit.disconnect(finalized)

    assert events == [
        "workers_and_widget_save",
        "layout_save",
        "ui_destroyed",
        "network_destroyed",
        "database_close",
        "lock_release",
    ]
    assert all(sip.isdeleted(obj) for obj in (host, widget, dialog, shadow, network, qnam, pump))
    assert application._sigint_pump is None
    assert NetworkManager._instance is None
    assert QCoreApplication.instance() is application
    assert settings.value("unrelated_custom_value") == "preserved"
    assert settings.value(f"{prefix}_font_size", type=int) == 47
    assert settings.value(f"{prefix}_pos_x", type=int) == 211
    assert settings.value(f"{prefix}_pos_y", type=int) == 322
    assert json.loads(settings.value("overlay_instances")) == [
        {"id": inst_id, "type": "clock", "name": "보존할 위젯", "enabled": True}
    ]


def test_running_child_thread_prevents_ui_and_network_disposal(application):
    host = QWidget()
    worker = QThread(host)
    network = NetworkManager.instance()
    worker.start()
    try:
        assert worker.isRunning()
        assert bootstrap._dispose_runtime_qobjects(application) is False
        assert not sip.isdeleted(host)
        assert not sip.isdeleted(network)
    finally:
        worker.quit()
        assert worker.wait(5000)
        host.deleteLater()


@pytest.mark.parametrize("raises", [False, True])
def test_failed_worker_shutdown_never_forces_parent_disposal(application, raises):
    window = Mock()
    window.shutdown_background_workers.side_effect = (
        RuntimeError("worker did not stop") if raises else [False, False]
    )
    with (
        patch.object(bootstrap, "_dispose_runtime_qobjects") as dispose,
        patch(
            "calendar_app.presentation.main_window.action_handlers._save_window_layout_for_shutdown"
        ),
        patch(
            "calendar_app.infrastructure.db.database_unified.db_manager.close_all_connections"
        ) as close_database,
        patch(
            "calendar_app.presentation.main_window.action_handlers._release_single_instance_lock"
        ) as release_lock,
    ):
        bootstrap._finalize_runtime(application, window)
        dispose.assert_not_called()
        close_database.assert_called_once()
        release_lock.assert_called_once()
    if not raises:
        assert window.shutdown_background_workers.call_args.kwargs == {"wait_ms": 1000}


def test_release_does_not_create_an_unused_network_service(application):
    assert NetworkManager._instance is None
    with patch.object(NetworkManager, "__init__", side_effect=AssertionError("created at exit")):
        NetworkManager.release()
    assert NetworkManager._instance is None


def test_cancelled_exit_does_not_mark_or_dispose_the_application(application):
    window = Mock()
    window._confirm_app_exit.return_value = False
    with patch.object(bootstrap, "_dispose_runtime_qobjects") as dispose:
        ActionHandlersMixin.request_app_exit(window)
        dispose.assert_not_called()
    window.shutdown_background_workers.assert_not_called()
    assert not app_lifecycle.is_app_exiting()


def test_shutdown_guard_checks_static_state_before_application_wrapper():
    with (
        patch.object(QCoreApplication, "closingDown", return_value=True),
        patch.object(
            QCoreApplication,
            "instance",
            side_effect=AssertionError("looked up application during destruction"),
        ),
    ):
        assert app_lifecycle.is_app_exiting()


def test_disposal_drains_deletes_without_running_queued_ui_work(application):
    host = QWidget()
    callback = Mock()
    timer = QTimer(application)
    timer.setSingleShot(True)
    timer.timeout.connect(callback)
    timer.start(0)
    mark_app_exiting(application)
    assert bootstrap._dispose_runtime_qobjects(application)
    assert sip.isdeleted(host)
    callback.assert_not_called()
    timer.stop()
    timer.deleteLater()


def test_forecast_client_destruction_runs_before_its_network_service(application):
    events = []
    host = QWidget()
    service = NetworkManager.instance()
    manager = service.qnam()

    class PhysicalReply(QNetworkReply):
        def __init__(self):
            super().__init__(manager)
            self.running = True

        def isRunning(self):  # noqa: N802
            return self.running

        def abort(self):
            events.append("physical_abort")
            self.running = False
            self.finished.emit()

    physical = PhysicalReply()
    with patch.object(manager, "get", return_value=physical):
        client = pooled_weather_reply(
            manager, QNetworkRequest(QUrl("https://fixture.invalid/forecast")), host
        )
    service.destroyed.connect(lambda: events.append("network_destroyed"))
    mark_app_exiting(application)
    assert bootstrap._dispose_runtime_qobjects(application)
    assert events == ["physical_abort", "network_destroyed"]
    assert all(sip.isdeleted(obj) for obj in (client, physical, service))


def test_cosmetic_filters_do_no_new_work_after_exit_is_marked(application):
    host = QWidget()
    dialog = QDialog(host)
    dialog.setLayout(QVBoxLayout())
    assert dialog_chrome.ensure_dialog_chrome(dialog)
    chrome = dialog._dc_dialog_chrome_controller
    shadow = dialog._dc_dialog_shadow_controller
    message = QMessageBox(host)
    style_filter = dialog_styles._CommonDialogStyleFilter(application)
    mark_app_exiting(application)
    with (
        patch.object(dialog_chrome, "_restore_tool_dialog_owner") as restore_owner,
        patch.object(chrome, "_update_header_geometry") as geometry,
        patch.object(style_filter, "_style_dialog") as style,
        patch.object(shadow.surface, "show") as show_shadow,
    ):
        assert not dialog_chrome._eligible(dialog)
        assert not dialog_chrome.prepare_dialog_chrome(message)
        assert not dialog_shadow.ensure_dialog_shadow(dialog)
        chrome.eventFilter(dialog, QEvent(QEvent.Type.WinIdChange))
        chrome.eventFilter(dialog, QEvent(QEvent.Type.Resize))
        shadow.sync_geometry()
        shadow.eventFilter(dialog, QEvent(QEvent.Type.Show))
        style_filter.eventFilter(message, QEvent(QEvent.Type.Show))
        restore_owner.assert_not_called()
        geometry.assert_not_called()
        style.assert_not_called()
        show_shadow.assert_not_called()
    host.deleteLater()


def test_bootstrap_restores_sigint_and_parents_its_pump():
    application, splash, window, lock = Mock(), Mock(), Mock(), Mock()
    application.exec.return_value = 0
    original = object()
    current_handler = {"value": original}

    def set_handler(_signum, handler):
        current_handler["value"] = handler

    def phase(*_args, work=None, **_kwargs):
        return work() if work else None

    with (
        patch.object(bootstrap, "QApplication", return_value=application),
        patch.object(bootstrap, "_install_qt_message_handler"),
        patch.object(
            bootstrap.signal, "getsignal", side_effect=lambda _sig: current_handler["value"]
        ),
        patch.object(bootstrap.signal, "signal", side_effect=set_handler),
        patch.object(bootstrap, "QTimer") as timer,
        patch.object(bootstrap, "_acquire_single_instance_lock", return_value=(True, lock)),
        patch.object(bootstrap, "_apply_saved_font"),
        patch.object(bootstrap, "_run_splash_phase", side_effect=phase),
        patch.object(bootstrap, "_finalize_runtime"),
        patch("calendar_app.presentation.splash_screen.SplashScreen", return_value=splash),
        patch("calendar_app.presentation.dialogs.dialog_styles.install_common_dialog_style_filter"),
        patch.object(NetworkManager, "instance"),
        patch(
            "calendar_app.infrastructure.db.database_unified.initialize_unified_database",
            return_value=True,
        ),
        patch(
            "calendar_app.infrastructure.db.calendar_repo.migrate_from_gcal_subscription",
            return_value=True,
        ),
    ):
        assert bootstrap.run(overlay_cls=Mock(return_value=window), build_ui_font=Mock()) == 0
    # The SIGINT pump and the daily database snapshot timer are both app-owned.
    assert timer.call_args_list == [call(application)] * 2
    assert current_handler["value"] is original
    application.aboutToQuit.disconnect.assert_called_once_with(
        application.aboutToQuit.connect.call_args.args[0]
    )
