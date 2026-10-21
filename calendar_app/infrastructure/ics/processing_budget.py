# -*- coding: utf-8 -*-
"""Interrupt Python ICS parsing, including recurrence work before its first yield."""

from contextlib import contextmanager
import sys
import time

from calendar_app.application.calendar_sync_contract import CalendarSyncError

_CHECK_EVERY = 256
_PARSER_MODULES = ("icalendar", "recurring_ical_events", "dateutil")
_PARSER_PREFIXES = tuple(name + "." for name in _PARSER_MODULES)
_FETCHER_MODULE = "calendar_app.infrastructure.ics.ics_fetcher"


class _ProcessingInterrupted(BaseException):
    """Unwind through parser handlers that catch and recover from Exception."""


@contextmanager
def processing_budget(cancelled, seconds):
    """Bound parser Python work in this thread without changing library globals.

    A page/output limit cannot stop dateutil while it searches for the first
    occurrence. Line tracing also reaches that non-yielding loop. The hook is
    thread-local, works with frozen Python bytecode, and chains/restores an
    existing debugger or coverage hook. It cannot preempt a blocking C call;
    HTTP/DNS operations therefore must remain outside this parser-only scope.
    """
    deadline = time.monotonic() + seconds
    remaining = _CHECK_EVERY
    previous = sys.gettrace()

    def check():
        if cancelled():
            raise _ProcessingInterrupted("cancelled")
        if time.monotonic() >= deadline:
            raise _ProcessingInterrupted("ics_processing_timeout")

    def budget_trace(frame, event, arg):
        nonlocal remaining
        remaining -= 1
        if remaining <= 0:
            remaining = _CHECK_EVERY
            check()
        return budget_trace

    def trace(frame, event, arg):
        module = frame.f_globals.get("__name__", "")
        guarded = (
            module == _FETCHER_MODULE
            or module in _PARSER_MODULES
            or module.startswith(_PARSER_PREFIXES)
        )
        if previous is None:
            return budget_trace if guarded else None
        previous_local = previous(frame, event, arg)
        if not guarded:
            return previous_local

        def local_trace(frame, event, arg):
            nonlocal previous_local
            if previous_local is not None:
                previous_local = previous_local(frame, event, arg)
            budget_trace(frame, event, arg)
            return local_trace

        return local_trace

    try:
        check()
        sys.settrace(trace)
        yield
        check()
    except _ProcessingInterrupted as exc:
        # Keep the internal interruption out of the worker's public contract.
        raise CalendarSyncError(str(exc)) from None
    finally:
        sys.settrace(previous)
