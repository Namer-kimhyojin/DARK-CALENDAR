# -*- coding: utf-8 -*-
"""Sharing sync diagnostics and rendering remote names must not expose resources."""

import os
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QImage, QTextDocument
from PyQt6.QtWidgets import QApplication, QListWidget
import pytest

from calendar_app.presentation.dialogs import gcal_settings_dialog as module
from calendar_app.presentation.dialogs.calendar_manager_page import _CalendarRowLabel
from calendar_app.presentation.dialogs.provider_settings_widgets import (
    plain_tooltip,
    update_calendar_items,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _ResourceProbe(QTextDocument):
    def __init__(self):
        super().__init__()
        self.requests = []

    def loadResource(self, kind, url):
        self.requests.append(url.toString())
        return QImage()


@pytest.mark.parametrize(
    "text",
    [
        '<img src="file://127.0.0.1/share/private.png"><b>Calendar</b>',
        '<img src="http://127.0.0.1:9/private.png"> &amp; text',
        "<style>body{background:url(file:///C:/private.png)}</style>\nCalendar",
        "A & B\n<C> 'name'",
    ],
)
def test_remote_tooltips_render_only_literal_text(qapp, text):
    widget = QListWidget()
    update_calendar_items(widget, "account", [(text, {"id": "cal", "name": text})], [])
    label = _CalendarRowLabel(text, "name")
    try:
        for tooltip in (plain_tooltip(text), widget.item(0).toolTip(), label.toolTip()):
            probe = _ResourceProbe()
            probe.setHtml(tooltip)
            probe.size()
            assert probe.requests == []
            assert probe.toPlainText() == text
    finally:
        widget.close()
        label.close()


def test_resource_probe_observes_actual_rich_text(qapp):
    probe = _ResourceProbe()
    probe.setHtml('<img src="file:///C:/synthetic-probe.png">')
    probe.size()
    assert set(probe.requests) == {"file:///C:/synthetic-probe.png"}


def test_diagnostics_export_omits_account_event_and_legacy_secret_text(tmp_path, monkeypatch):
    from calendar_app import app_paths
    from calendar_app.infrastructure.db import calendar_repo, database_unified

    private = "SYNTHETIC_PRIVATE_VALUE"
    target = tmp_path / "diagnostics.txt"
    log_path = tmp_path / "synthetic.log"
    log_path.write_text(
        f"[ERROR] gcal private title {private} https://example.invalid/{private}\n"
        f"[WARNING] sync access_token={private}\n",
        encoding="utf-8",
        errors="strict",
    )
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        "CREATE TABLE unified_task "
        "(id INTEGER, name TEXT, deadline TEXT, gcal_event_id TEXT, "
        "gcal_dirty INTEGER, gcal_sync_error TEXT);"
        "CREATE TABLE gcal_deleted_task_archive (id INTEGER);"
        "CREATE TABLE gcal_delete_queue (id INTEGER);"
    )
    connection.executemany(
        "INSERT INTO unified_task VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, private, private, private, 1, f"access_token={private}"),
            (2, private, private, private, 0, "network_unavailable"),
        ],
    )
    monkeypatch.setattr(database_unified.db_manager, "get_connection", lambda: connection)
    monkeypatch.setattr(app_paths, "LOG_PATH", str(log_path))
    monkeypatch.setattr(
        calendar_repo,
        "list_calendars",
        lambda **kwargs: [
            {
                "id": private,
                "type": "gcal",
                "gcal_calendar_id": private,
                "name": private,
                "access_role": private,
                "is_active": 1,
                "is_visible": 1,
            }
        ],
    )
    monkeypatch.setattr(module.QFileDialog, "getSaveFileName", lambda *args: (str(target), ""))
    info, error = Mock(), Mock()
    monkeypatch.setattr(module.QMessageBox, "information", info)
    monkeypatch.setattr(module.QMessageBox, "critical", error)
    host = SimpleNamespace(settings=SimpleNamespace(value=lambda *args: private))
    try:
        module.GCalSettingsDialog._export_diagnostics_report(host)
        error.assert_not_called()
        info.assert_called_once()
        report = target.read_text(encoding="utf-8", errors="strict")
        assert private not in report
        assert "Total Unified Tasks: 2" in report
        assert "network_unavailable" in report
        assert "operation_failed" in report
        assert "ERROR: 1" in report and "WARNING: 1" in report
    finally:
        connection.close()
