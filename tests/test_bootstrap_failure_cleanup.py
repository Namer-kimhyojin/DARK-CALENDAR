# -*- coding: utf-8 -*-
"""Failed startup phases must stop before the UI and release runtime resources."""

import sqlite3
from unittest.mock import Mock, patch

import pytest

from calendar_app import bootstrap


@pytest.mark.parametrize(
    "failure", ["database", "migration", "constructor", "show", "deleted-splash", "ui-storage"]
)
def test_startup_failure_aborts_and_finalizes_runtime(failure):
    app, splash, window, lock = Mock(), Mock(), Mock(), Mock()
    overlay = Mock(return_value=window)
    if failure in ("constructor", "deleted-splash"):
        overlay.side_effect = RuntimeError("constructor failed")
    if failure == "deleted-splash":
        splash.close.side_effect = RuntimeError("wrapped C++ object has been deleted")
    if failure == "show":
        window.show.side_effect = RuntimeError("show failed")
    if failure == "ui-storage":
        window.show.side_effect = PermissionError("UI storage failed")

    def phase(*args, work=None, **kwargs):
        return work() if work else None

    with (
        patch.object(bootstrap, "QApplication", return_value=app),
        patch.object(bootstrap, "_install_qt_message_handler"),
        patch.object(bootstrap.signal, "signal"),
        patch.object(bootstrap, "QTimer"),
        patch.object(bootstrap, "_acquire_single_instance_lock", return_value=(True, lock)),
        patch.object(bootstrap, "_apply_saved_font"),
        patch.object(bootstrap, "_run_splash_phase", side_effect=phase),
        patch.object(bootstrap, "_finalize_runtime") as finalize,
        patch("calendar_app.presentation.splash_screen.SplashScreen", return_value=splash),
        patch("calendar_app.presentation.dialogs.dialog_styles.install_common_dialog_style_filter"),
        patch("calendar_app.infrastructure.runtime.network.NetworkManager.instance"),
        patch(
            "calendar_app.infrastructure.db.database_unified.initialize_unified_database",
            return_value=failure != "database",
        ),
        patch(
            "calendar_app.infrastructure.db.calendar_repo.migrate_from_gcal_subscription",
            return_value=failure != "migration",
        ),
    ):
        message = {
            "database": "Database initialization",
            "migration": "Calendar migration",
            "constructor": "constructor failed",
            "show": "show failed",
            "deleted-splash": "constructor failed",
            "ui-storage": "UI storage failed",
        }[failure]
        expected_error = PermissionError if failure == "ui-storage" else RuntimeError
        with pytest.raises(expected_error, match=message):
            bootstrap.run(overlay_cls=overlay, build_ui_font=Mock())
        expected_window = window if failure in ("show", "ui-storage") else None
        finalize.assert_called_once_with(app, expected_window)
        splash.close.assert_called_once()
        app.exec.assert_not_called()
        if failure in ("database", "migration"):
            overlay.assert_not_called()


@pytest.mark.parametrize("failure", ["corruption", "permission"])
def test_database_failure_reports_original_error_and_exits_cleanly(failure):
    app, splash, lock = Mock(), Mock(), Mock()
    overlay = Mock()
    if failure == "corruption":
        error = sqlite3.DatabaseError("database disk image is malformed")
        error.sqlite_errorcode = sqlite3.SQLITE_CORRUPT
        error.sqlite_errorname = "SQLITE_CORRUPT"
    else:
        error = PermissionError("Database folder cannot be accessed")

    def phase(*args, work=None, **kwargs):
        return work() if work else None

    with (
        patch.object(bootstrap, "QApplication", return_value=app),
        patch.object(bootstrap, "_install_qt_message_handler"),
        patch.object(bootstrap, "_acquire_single_instance_lock", return_value=(True, lock)),
        patch.object(bootstrap, "_apply_saved_font"),
        patch.object(bootstrap, "_run_splash_phase", side_effect=phase),
        patch.object(bootstrap, "_finalize_runtime") as finalize,
        patch.object(bootstrap, "_show_database_startup_error") as explain,
        patch("calendar_app.presentation.splash_screen.SplashScreen", return_value=splash),
        patch("calendar_app.presentation.dialogs.dialog_styles.install_common_dialog_style_filter"),
        patch("calendar_app.infrastructure.runtime.network.NetworkManager.instance"),
        patch(
            "calendar_app.infrastructure.db.database_unified.initialize_unified_database",
            side_effect=error,
        ) as initialize,
    ):
        assert bootstrap.run(overlay_cls=overlay, build_ui_font=Mock()) == 1
        initialize.assert_called_once_with(raise_on_error=True)
        assert explain.call_args.args == (error,)
        assert explain.call_args.kwargs["database_path"]
        finalize.assert_called_once_with(app, None)
        overlay.assert_not_called()
        app.exec.assert_not_called()
