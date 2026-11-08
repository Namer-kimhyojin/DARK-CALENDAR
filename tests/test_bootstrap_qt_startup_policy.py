# -*- coding: utf-8 -*-
"""Startup argument policy must run before Qt without changing lifecycle gates."""

from contextlib import ExitStack, contextmanager
import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from calendar_app import bootstrap
from calendar_app.infrastructure.runtime.qt_startup_options import QtStartupOptions


@contextmanager
def _startup(*, failure=None, paint=False):
    events = []
    app, window, splash, lock = Mock(), Mock(), Mock(), Mock()
    callbacks = []
    settings = Mock()
    settings.value.side_effect = lambda _key, default=None, **_kwargs: default
    window.first_paint.connect.side_effect = callbacks.append
    splash.finish.side_effect = lambda: events.append("first_paint_finish")

    def application(arguments):
        events.append("qapplication")
        # QApplication may consume its own argument list in native bindings.
        arguments.append("qt-consumed-copy")
        return app

    def phase(*_args, work=None, **_kwargs):
        return work() if work else None

    def font(*_args):
        events.append("font")

    def database(**_kwargs):
        events.append("database")
        return failure != "database"

    def migrate(**_kwargs):
        events.append("migration")
        return failure != "migration"

    def labels():
        events.append("labels")

    def construct():
        events.append("construct")
        if failure == "constructor":
            raise RuntimeError("constructor failed")
        return window

    def show():
        events.append("show")
        if failure == "show":
            raise RuntimeError("show failed")
        if paint:
            for callback in callbacks:
                callback()

    def execute():
        events.append("exec")
        return 0

    window.show.side_effect = show
    app.exec.side_effect = execute
    with ExitStack() as stack:
        application_type = stack.enter_context(
            patch.object(bootstrap, "QApplication", side_effect=application)
        )
        overlay = Mock(side_effect=construct)
        finalize = stack.enter_context(patch.object(bootstrap, "_finalize_runtime"))
        timer = stack.enter_context(patch.object(bootstrap, "QTimer"))
        stack.enter_context(patch.object(bootstrap, "QCoreApplication"))
        stack.enter_context(patch.object(bootstrap, "QSettings", return_value=settings))
        stack.enter_context(patch.object(bootstrap, "QIcon"))
        stack.enter_context(patch.object(bootstrap, "_install_qt_message_handler"))
        stack.enter_context(
            patch.object(bootstrap, "_acquire_single_instance_lock", return_value=(True, lock))
        )
        stack.enter_context(patch.object(bootstrap, "_apply_saved_font", side_effect=font))
        stack.enter_context(patch.object(bootstrap, "_run_splash_phase", side_effect=phase))
        stack.enter_context(patch.object(bootstrap.signal, "signal"))
        stack.enter_context(patch.object(bootstrap.sip, "isdeleted", return_value=False))
        stack.enter_context(patch.object(bootstrap.i18n, "apply_application_locale"))
        stack.enter_context(
            patch("calendar_app.presentation.splash_screen.SplashScreen", return_value=splash)
        )
        stack.enter_context(
            patch(
                "calendar_app.presentation.dialogs.dialog_styles.install_common_dialog_style_filter"
            )
        )
        stack.enter_context(
            patch("calendar_app.infrastructure.runtime.network.NetworkManager.instance")
        )
        stack.enter_context(
            patch(
                "calendar_app.infrastructure.db.database_unified.initialize_unified_database",
                side_effect=database,
            )
        )
        stack.enter_context(
            patch(
                "calendar_app.infrastructure.db.calendar_repo.migrate_from_gcal_subscription",
                side_effect=migrate,
            )
        )
        stack.enter_context(
            patch("calendar_app.domain.task_constants.load_custom_labels", side_effect=labels)
        )
        yield SimpleNamespace(
            app=app,
            window=window,
            splash=splash,
            application_type=application_type,
            overlay=overlay,
            finalize=finalize,
            timer=timer,
            events=events,
        )


def _options(arguments):
    return QtStartupOptions(
        tuple(arguments), "gdi", "windows_default", "windows_startup_compatibility", True
    )


def test_policy_precedes_qapplication_and_passes_an_independent_argument_list(monkeypatch):
    original = ["AirCalendar.exe", "--document", "C:/fixture/calendar.ics"]
    monkeypatch.setattr(bootstrap.sys, "argv", original)
    options = _options((*original, "-platform", "windows:fontengine=gdi"))
    resolved = []
    with _startup() as startup:

        def resolve(argv, environment, platform):
            assert startup.events == []
            assert argv is original
            assert environment is bootstrap.os.environ
            assert platform == bootstrap.sys.platform
            resolved.append(True)
            return options

        with patch.object(bootstrap, "resolve_qt_startup_options", side_effect=resolve):
            assert bootstrap.run(overlay_cls=startup.overlay, build_ui_font=Mock()) == 0

        assert resolved == [True]
        received = startup.application_type.call_args.args[0]
        assert received == [*options.argv, "qt-consumed-copy"]
        assert received is not original
        assert original == ["AirCalendar.exe", "--document", "C:/fixture/calendar.ics"]
        assert options.argv[-2:] == ("-platform", "windows:fontengine=gdi")
        assert startup.events == [
            "qapplication",
            "font",
            "database",
            "migration",
            "labels",
            "construct",
            "show",
            "exec",
        ]
        startup.splash.finish.assert_not_called()
        startup.finalize.assert_called_once_with(startup.app, startup.window)


@pytest.mark.parametrize("explicit_platform", [False, True])
def test_policy_log_contains_only_selection_metadata_not_private_cli(
    monkeypatch, caplog, explicit_platform
):
    private = "PRIVATE-TOKEN-ONLY-FIXTURE-71d7"
    arguments = ["AirCalendar.exe", "--token=" + private, "C:/private-secret-user/secret.ics"]
    monkeypatch.setattr(bootstrap.sys, "argv", arguments)
    if explicit_platform:
        arguments.extend(["-platform", "windows:fontengine=" + private])
        options = QtStartupOptions(
            tuple(arguments), private, "command_line", "explicit_platform_preserved"
        )
    else:
        options = _options((*arguments, "-platform", "windows:fontengine=gdi"))
    caplog.set_level(logging.INFO, logger="calendar_app.bootstrap")
    with (
        _startup() as startup,
        patch.object(bootstrap, "resolve_qt_startup_options", return_value=options),
    ):
        assert bootstrap.run(overlay_cls=startup.overlay, build_ui_font=Mock()) == 0
    records = [record for record in caplog.records if record.name == "calendar_app.bootstrap"]
    messages = "\n".join(record.getMessage() for record in records)
    assert options.source in messages
    assert options.reason in messages
    for secret in (private, "private-secret-user", "secret.ics", "--token="):
        assert secret not in messages
        assert secret not in repr([(record.msg, record.args) for record in records])


def test_first_paint_still_finishes_splash_and_defers_widget_workspace():
    options = _options(["AirCalendar.exe", "-platform", "windows:fontengine=gdi"])
    with (
        _startup(paint=True) as startup,
        patch.object(bootstrap, "resolve_qt_startup_options", return_value=options),
    ):
        assert bootstrap.run(overlay_cls=startup.overlay, build_ui_font=Mock()) == 0
        assert startup.events[-3:] == ["show", "first_paint_finish", "exec"]
        startup.splash.finish.assert_called_once_with()
        startup.timer.singleShot.assert_called_once()
        assert startup.timer.singleShot.call_args.args[0] == 0
        assert callable(startup.timer.singleShot.call_args.args[1])


@pytest.mark.parametrize("failure", ["database", "migration", "constructor", "show"])
def test_policy_integration_preserves_failure_boundaries_and_cleanup(failure):
    options = _options(["AirCalendar.exe", "-platform", "windows:fontengine=gdi"])
    expected = {
        "database": ("Database initialization", ["qapplication", "font", "database"]),
        "migration": ("Calendar migration", ["qapplication", "font", "database", "migration"]),
        "constructor": (
            "constructor failed",
            ["qapplication", "font", "database", "migration", "labels", "construct"],
        ),
        "show": (
            "show failed",
            ["qapplication", "font", "database", "migration", "labels", "construct", "show"],
        ),
    }
    with (
        _startup(failure=failure) as startup,
        patch.object(bootstrap, "resolve_qt_startup_options", return_value=options) as resolve,
    ):
        with pytest.raises(RuntimeError, match=expected[failure][0]):
            bootstrap.run(overlay_cls=startup.overlay, build_ui_font=Mock())
        resolve.assert_called_once()
        assert startup.events == expected[failure][1]
        startup.app.exec.assert_not_called()
        startup.splash.finish.assert_not_called()
        startup.splash.close.assert_called_once()
        startup.finalize.assert_called_once_with(
            startup.app, startup.window if failure == "show" else None
        )
