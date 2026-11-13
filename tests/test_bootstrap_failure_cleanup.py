# -*- coding: utf-8 -*-
"""Failed startup phases must stop before the UI and release runtime resources."""

import sqlite3
from unittest.mock import Mock, patch

import pytest

from calendar_app import bootstrap


@pytest.fixture(autouse=True)
def isolate_app_icon(monkeypatch):
    # The startup tests substitute QApplication, so icon loading must not create a pixmap.
    monkeypatch.setattr(bootstrap, "QIcon", Mock())


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


@pytest.mark.parametrize("choice", ["restore", "close", "restore-fails"])
def test_corruption_offers_snapshot_restore_and_relaunches_only_after_cleanup(choice):
    app, splash, lock = Mock(), Mock(), Mock()
    error = sqlite3.DatabaseError("database disk image is malformed")
    error.sqlite_errorcode = sqlite3.SQLITE_CORRUPT
    error.sqlite_errorname = "SQLITE_CORRUPT"
    order = Mock()

    def phase(*args, work=None, **kwargs):
        return work() if work else None

    with (
        patch.object(bootstrap, "QApplication", return_value=app),
        patch.object(bootstrap, "_install_qt_message_handler"),
        patch.object(bootstrap, "_acquire_single_instance_lock", return_value=(True, lock)),
        patch.object(bootstrap, "_apply_saved_font"),
        patch.object(bootstrap, "_run_splash_phase", side_effect=phase),
        patch.object(bootstrap, "_finalize_runtime", side_effect=lambda *a: order.finalize()),
        patch.object(bootstrap, "_relaunch_application", side_effect=order.relaunch),
        patch.object(bootstrap, "_show_database_restore_failure") as restore_failure,
        patch.object(
            bootstrap, "_show_database_startup_error", return_value=choice != "close"
        ) as explain,
        patch("calendar_app.presentation.splash_screen.SplashScreen", return_value=splash),
        patch("calendar_app.presentation.dialogs.dialog_styles.install_common_dialog_style_filter"),
        patch("calendar_app.infrastructure.runtime.network.NetworkManager.instance"),
        patch(
            "calendar_app.infrastructure.db.database_unified.initialize_unified_database",
            side_effect=error,
        ),
        patch(
            "calendar_app.infrastructure.db.db_backup.find_restorable_backup",
            return_value="snapshot.db",
        ),
        patch(
            "calendar_app.infrastructure.db.db_backup.restore_latest_backup",
            return_value=None if choice == "restore-fails" else "snapshot.db",
        ) as restore,
    ):
        assert bootstrap.run(overlay_cls=Mock(), build_ui_font=Mock()) == 1

    assert explain.call_args.kwargs["offer_restore"] is True
    if choice == "close":
        restore.assert_not_called()
    else:
        restore.assert_called_once_with(explain.call_args.kwargs["database_path"])
    if choice == "restore":
        assert [call[0] for call in order.mock_calls] == ["finalize", "relaunch"]
        restore_failure.assert_not_called()
    else:
        assert [call[0] for call in order.mock_calls] == ["finalize"]
    if choice == "restore-fails":
        restore_failure.assert_called_once_with(None)


def test_successful_startup_takes_daily_snapshot_without_blocking_on_failure():
    with (
        patch(
            "calendar_app.infrastructure.db.db_backup.create_daily_backup",
            side_effect=sqlite3.DatabaseError("Database snapshot failed its integrity check"),
        ) as snapshot,
    ):
        bootstrap._create_daily_database_snapshot()
    snapshot.assert_called_once()
