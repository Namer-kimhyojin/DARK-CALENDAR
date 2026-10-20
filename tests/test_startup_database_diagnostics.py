# -*- coding: utf-8 -*-
"""Startup diagnostics distinguish corruption from contention without modifying data."""

import sqlite3
from unittest.mock import Mock, patch

from PyQt6.QtCore import Qt
import pytest

from calendar_app.infrastructure.runtime import crash_bootstrap


@pytest.mark.parametrize(
    ("code", "key"),
    [
        (sqlite3.SQLITE_CORRUPT, "corrupt"),
        (sqlite3.SQLITE_NOTADB, "corrupt"),
        (sqlite3.SQLITE_BUSY, "locked"),
        (sqlite3.SQLITE_LOCKED, "locked"),
        (sqlite3.SQLITE_READONLY, "unavailable"),
        (sqlite3.SQLITE_CANTOPEN, "unavailable"),
        (sqlite3.SQLITE_FULL, "unavailable"),
    ],
)
def test_diagnostic_classifies_original_error_without_opening_database(code, key):
    error = sqlite3.DatabaseError("original database error <retained>")
    error.sqlite_errorcode = code
    error.sqlite_errorname = "ORIGINAL_SQLITE_CODE"
    application, dialog = Mock(), Mock()
    with (
        patch("PyQt6.QtWidgets.QApplication") as application_type,
        patch("PyQt6.QtWidgets.QMessageBox", return_value=dialog),
        patch("calendar_app.domain.i18n.t", side_effect=lambda key, fallback: key),
        patch.object(sqlite3, "connect") as connect,
    ):
        application_type.instance.return_value = application
        crash_bootstrap.show_database_startup_error(error, database_path="C:/private/<original>.db")
        application_type.assert_not_called()
        connect.assert_not_called()
    dialog.setText.assert_called_once_with("startup_database." + key)
    dialog.setTextFormat.assert_called_once_with(Qt.TextFormat.PlainText)
    details = dialog.setDetailedText.call_args.args[0]
    assert "C:/private/<original>.db" in details
    assert "ORIGINAL_SQLITE_CODE" in details
    assert str(error) in details
    dialog.exec.assert_called_once()


@pytest.mark.parametrize("context", ["filename", "database_paths"])
def test_import_time_permission_failure_can_show_diagnostic_before_application_exists(context):
    if context == "filename":
        error = PermissionError(13, "permission denied", "C:/private/original.db")
    else:
        error = PermissionError("permission denied")
        error.database_path = "C:/private/target.db"
        error.database_source = "C:/legacy/original.db"
    application, dialog = Mock(), Mock()
    with (
        patch("PyQt6.QtWidgets.QApplication", return_value=application) as application_type,
        patch("PyQt6.QtWidgets.QMessageBox", return_value=dialog),
        patch("calendar_app.domain.i18n.t", side_effect=lambda key, fallback: key),
    ):
        application_type.instance.return_value = None
        crash_bootstrap.show_database_startup_error(error)
    application_type.assert_called_once()
    dialog.setText.assert_called_once_with("startup_database.unavailable")
    details = dialog.setDetailedText.call_args.args[0]
    if context == "filename":
        assert error.filename in details
    else:
        assert error.database_path in details
        assert error.database_source in details
    application.processEvents.assert_called_once()
