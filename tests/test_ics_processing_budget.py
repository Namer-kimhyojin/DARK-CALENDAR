# -*- coding: utf-8 -*-
"""A costly ICS recurrence cannot monopolize the parser or replace cached rows."""

from contextlib import nullcontext
import json
from pathlib import Path
import subprocess
import sys

import pytest

from calendar_app.application.calendar_sync_contract import CalendarSyncError
from calendar_app.infrastructure.ics import ics_fetcher
from calendar_app.infrastructure.ics.processing_budget import processing_budget
from tests.test_ics_snapshot_safety import event, feed, snapshot


@pytest.mark.parametrize(
    "mode,expected", [("timeout", "ics_processing_timeout"), ("cancel", "cancelled")]
)
def test_sparse_ancient_recurrence_stops_before_first_page(mode, expected):
    # Keep an independent outer deadline so a lost inner guard fails this test
    # without hanging pytest. This child only parses synthetic bytes, with no DB.
    script = """
import json, sys, threading, time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo
import icalendar
from calendar_app.application.calendar_sync_contract import CalendarSyncError
from calendar_app.infrastructure.ics import ics_fetcher

ics_fetcher._now = lambda: datetime(2026, 10, 20, tzinfo=UTC)
ics_fetcher.MAX_PROCESS_SECONDS = 0.15 if sys.argv[1] == 'timeout' else 10
cancelled = threading.Event()
timer = threading.Timer(0.15, cancelled.set) if sys.argv[1] == 'cancel' else None
def previous_trace(frame, event, arg):
    return previous_trace
sys.settrace(previous_trace)
raw = (b'BEGIN:VCALENDAR\\r\\nVERSION:2.0\\r\\nBEGIN:VEVENT\\r\\nUID:one\\r\\n'
       b'DTSTART:00010101T000000Z\\r\\nRRULE:FREQ=SECONDLY;INTERVAL=86400\\r\\n'
       b'END:VEVENT\\r\\nEND:VCALENDAR\\r\\n')
started = time.monotonic()
if timer:
    timer.start()
try:
    ics_fetcher._snapshot(raw, icalendar, ZoneInfo('Asia/Seoul'), cancelled.is_set)
    result = 'unexpected_success'
except CalendarSyncError as exc:
    result = str(exc)
finally:
    if timer:
        timer.cancel()
print(json.dumps({'result': result, 'seconds': time.monotonic() - started,
                  'trace_restored': sys.gettrace() is previous_trace}))
sys.settrace(None)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, mode],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=5,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["result"] == expected
    assert payload["seconds"] < 2
    assert payload["trace_restored"]


def test_processing_timeout_preserves_snapshot_and_last_success(snapshot, monkeypatch):
    conn, sync = snapshot
    assert sync(feed(event("one"), event("old"))) == (2, 0, None)
    before = conn.execute("SELECT * FROM unified_task ORDER BY id").fetchall()
    fetched = conn.execute("SELECT ics_last_fetched FROM calendar").fetchone()
    monkeypatch.setattr(ics_fetcher, "MAX_PROCESS_SECONDS", 0)
    assert sync(feed(event("one", "Changed"))) == (0, 0, "ics_processing_timeout")
    assert conn.execute("SELECT * FROM unified_task ORDER BY id").fetchall() == before
    assert conn.execute("SELECT ics_last_fetched FROM calendar").fetchone() == fetched
    assert not conn.in_transaction


@pytest.mark.parametrize("failure", [False, True])
def test_parser_budget_chains_and_restores_existing_trace(failure):
    import icalendar

    seen = []

    def previous_local(frame, event, arg):
        if event == "line":
            seen.append(frame.f_code.co_name)
        return previous_local

    def previous(frame, event, arg):
        if frame.f_globals.get("__name__") == ics_fetcher.__name__:
            seen.append(event)
            return previous_local
        return None

    original = sys.gettrace()
    try:
        sys.settrace(previous)
        with (
            pytest.raises(RuntimeError) if failure else nullcontext(),
            processing_budget(lambda: False, 5),
        ):
            ics_fetcher._snapshot_rows(feed(event("one")), icalendar, None, lambda: False)
            if failure:
                raise RuntimeError("synthetic")
        assert sys.gettrace() is previous
        assert "call" in seen and "_snapshot_rows" in seen
    finally:
        sys.settrace(original)


def test_parser_budget_does_not_change_another_threads_trace():
    import threading

    result = []
    with processing_budget(lambda: False, 5):
        worker = threading.Thread(target=lambda: result.append(sys.gettrace()))
        worker.start()
        worker.join(timeout=2)
    assert not worker.is_alive()
    assert result == [None]


def test_parser_error_recovery_cannot_swallow_budget_interruption():
    from types import FunctionType

    swallowed = []
    checks = 0

    def cancellation():
        nonlocal checks
        checks += 1
        return checks > 1

    def parsing_loop():
        try:
            total = 0
            for index in range(10000):
                total += index
        except Exception:
            swallowed.append(True)

    parser = FunctionType(
        parsing_loop.__code__,
        {"__name__": "icalendar.synthetic"},
        closure=parsing_loop.__closure__,
    )
    with pytest.raises(CalendarSyncError, match="cancelled"), processing_budget(cancellation, 5):
        parser()
    assert not swallowed
