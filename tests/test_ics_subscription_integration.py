# -*- coding: utf-8 -*-
"""Exercise the real HTTP reader, ICS worker, settings feedback and SQLite snapshot together."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import threading
from unittest.mock import Mock

from PyQt6.QtCore import QSettings
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget

from calendar_app.infrastructure.db import calendar_repo, database_unified, task_repo
from calendar_app.infrastructure.ics import subscription_http
from calendar_app.presentation.main_window.calendar_sync_coordinator import CalendarSyncCoordinator


def test_subscription_http_worker_import_failure_recovery_and_automatic_pause(
    tmp_path, monkeypatch
):
    payload = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:fixture\r\n"
        "DTSTART:20261006T100000Z\r\nSUMMARY:Shared event\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    ).encode("utf-8", errors="strict")
    response = {"status": 200, "body": payload, "requests": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            response["requests"] += 1
            self.send_response(response["status"])
            self.send_header("Content-Type", "text/calendar; charset=utf-8")
            self.send_header("Content-Length", str(len(response["body"])))
            self.end_headers()
            self.wfile.write(response["body"])

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    def fixture_connection(address, timeout, source_address=None, **_kwargs):
        # This worker/reader fixture deliberately uses a synthetic loopback
        # server. Destination enforcement is covered by test_ics_request_security.
        assert address == ("127.0.0.1", server.server_port)
        return socket.create_connection(address, timeout, source_address)

    monkeypatch.setattr(subscription_http, "_connect_public", fixture_connection)
    qtapp = QApplication.instance() or QApplication([])
    host = QWidget()
    host.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    host.settings.setValue("gcal_enabled", "false")
    host.settings.setValue("gcal_timezone", "Asia/Seoul")
    host._bg_workers = []
    host._caldav_sync_controllers = {}
    host.schedule_panel_refresh = Mock()
    monkeypatch.setattr(database_unified, "DB_PATH", str(tmp_path / "calendar.db"))
    database_unified.initialize_unified_database()
    for name in (
        "count_unified_task_gcal_errors",
        "count_gcal_delete_queue_errors",
        "count_gcal_sync_conflicts",
    ):
        monkeypatch.setattr(task_repo, name, lambda: 0)
    url = f"http://127.0.0.1:{server.server_port}/feed.ics"
    key = calendar_repo.make_ics_id(url)
    assert calendar_repo.upsert_calendar(key, "ics", "Fixture", ics_url=url)
    coordinator = CalendarSyncCoordinator(host, str(tmp_path / "calendar.db"))

    def synchronize():
        assert coordinator.sync_ics(force=True, calendar_ids=[key])
        for _attempt in range(200):
            QTest.qWait(10)
            if coordinator.ics_worker is None:
                break
        assert coordinator.ics_worker is None
        assert not host._bg_workers

    try:
        synchronize()
        conn = database_unified.db_manager.get_connection()
        row = conn.execute(
            "SELECT id,name,deadline FROM unified_task WHERE calendar_id=?", (key,)
        ).fetchone()
        assert row is not None and row[1:] == ("Shared event", "2026-10-06 19:00")
        task_id = row[0]
        fetched = calendar_repo.get_calendar(key)["ics_last_fetched"]
        assert fetched and not coordinator.states["ics"]["issues"]
        response.update(status=403, body=b"synthetic-private-key")
        synchronize()
        assert coordinator.states["ics"]["issues"] == 1
        assert host.settings.value("sync_ics_error_codes") == {key: "ics_access_denied"}
        assert calendar_repo.get_calendar(key)["ics_last_fetched"] == fetched
        assert (
            conn.execute("SELECT name FROM unified_task WHERE id=?", (task_id,)).fetchone()[0]
            == "Shared event"
        )
        response.update(status=200, body=payload.replace(b"Shared event", b"Updated event"))
        synchronize()
        assert not coordinator.states["ics"]["issues"]
        assert host.settings.value("sync_ics_error_codes") == {}
        assert conn.execute(
            "SELECT id,name FROM unified_task WHERE calendar_id=?", (key,)
        ).fetchone()[:] == (task_id, "Updated event")
        coordinator.set_auto("ics", False)
        requests = response["requests"]
        assert not coordinator.sync_ics()
        assert response["requests"] == requests
        synchronize()  # Explicit manual sync still works while automatic sync is paused.
    finally:
        coordinator.stop()
        if coordinator.ics_worker:
            coordinator.ics_worker.wait(3000)
        qtapp.processEvents()
        host.close()
        database_unified.db_manager.close_connection()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)
