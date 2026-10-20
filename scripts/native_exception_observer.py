# -*- coding: utf-8 -*-
"""Observe Windows exception dispatch without consuming application exceptions.

Only the disposable-runner harness may instantiate this observer. Attaching a
debugger changes timing; the report explicitly records that limitation. The
initial attach breakpoint is continued, while every application exception is
passed to the application's original exception handlers.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from datetime import UTC, datetime
import threading
import time


class _ExceptionRecord(ctypes.Structure):
    pass


_ExceptionRecord._fields_ = [
    ("code", wintypes.DWORD),
    ("flags", wintypes.DWORD),
    ("record", ctypes.POINTER(_ExceptionRecord)),
    ("address", ctypes.c_void_p),
    ("parameter_count", wintypes.DWORD),
    ("parameters", ctypes.c_size_t * 15),
]


class _ExceptionInfo(ctypes.Structure):
    _fields_ = [("record", _ExceptionRecord), ("first_chance", wintypes.DWORD)]


class _CreateProcessInfo(ctypes.Structure):
    _fields_ = [
        ("file", wintypes.HANDLE),
        ("process", wintypes.HANDLE),
        ("thread", wintypes.HANDLE),
        ("image_base", ctypes.c_void_p),
        ("debug_offset", wintypes.DWORD),
        ("debug_size", wintypes.DWORD),
        ("thread_base", ctypes.c_void_p),
        ("start_address", ctypes.c_void_p),
        ("image_name", ctypes.c_void_p),
        ("unicode", wintypes.WORD),
    ]


class _LoadDllInfo(ctypes.Structure):
    _fields_ = [
        ("file", wintypes.HANDLE),
        ("image_base", ctypes.c_void_p),
        ("debug_offset", wintypes.DWORD),
        ("debug_size", wintypes.DWORD),
        ("image_name", ctypes.c_void_p),
        ("unicode", wintypes.WORD),
    ]


class _DebugPayload(ctypes.Union):
    _fields_ = [
        ("exception", _ExceptionInfo),
        ("created", _CreateProcessInfo),
        ("loaded", _LoadDllInfo),
        ("exit_code", wintypes.DWORD),
    ]


class _DebugEvent(ctypes.Structure):
    _fields_ = [
        ("kind", wintypes.DWORD),
        ("pid", wintypes.DWORD),
        ("tid", wintypes.DWORD),
        ("payload", _DebugPayload),
    ]


def continuation(kind: int, code: int, first_chance: bool, attach_breakpoint: bool) -> int:
    # DBG_CONTINUE is reserved for the debugger's one initial breakpoint.
    if kind != 1 or (attach_breakpoint and code == 0x80000003 and first_chance):
        return 0x00010002
    return 0x80010001  # DBG_EXCEPTION_NOT_HANDLED: invoke original app handlers.


def classify_rpc(trace: dict, diagnostic_count: int, pid: int) -> dict:
    """Require complete direct first/second-chance and normal-process-exit evidence."""
    if trace.get("error") or not trace.get("attached") or not trace.get("completed"):
        raise RuntimeError("Native exception observer was incomplete")
    if trace.get("pid") != pid or trace.get("exit_code") != 0:
        raise RuntimeError("Observed native process did not finish with exit code zero")
    if any(event["pid"] != pid for event in trace["events"]):
        raise RuntimeError("Exception observer recorded an unrelated process")
    exits = [event for event in trace["events"] if event["kind"] == 5]
    if len(exits) != 1:
        raise RuntimeError("Missing unique Windows EXIT_PROCESS_DEBUG_EVENT")
    exceptions = [event for event in trace["events"] if event["kind"] == 1]
    if any(not event["first_chance"] for event in exceptions):
        raise RuntimeError("A second-chance native exception was observed")
    for event in exceptions:
        code = int(event["code"], 16)
        if (
            code & 0x80000000
            and code not in {0x8001010D, 0xE06D7363, 0xE0434352}
            and not event.get("attach_breakpoint")
        ):
            raise RuntimeError("An unclassified native error exception was observed")
    if any(event["kind"] == 9 for event in trace["events"]):
        raise RuntimeError("A native RIP debugger error was observed")
    rpc = [event for event in exceptions if event["code"] == "0x8001010d"]
    if len(rpc) != diagnostic_count:
        raise RuntimeError("RPC faulthandler diagnostics do not match observed first-chance events")
    return {
        "classification": "handled_first_chance" if rpc else "none",
        "rpc_event_count": len(rpc),
        "first_chance_only": True,
        "process_exit_code": 0,
        "handler_identity": "not determined; original Windows/application handlers ran",
        "debugger_timing_limitation": "Debugger attachment may alter exception/UI timing",
    }


class ExceptionObserver:
    def __init__(self, pid: int, guard):
        guard()  # Caller repeats the hosted-runner safety contract before attach.
        self.pid = pid
        self.ready = threading.Event()
        self.stop_requested = threading.Event()
        self.trace = {"pid": pid, "attached": False, "completed": False, "events": []}
        self.worker = threading.Thread(target=self._observe, daemon=True)

    def start(self):
        self.worker.start()
        if not self.ready.wait(10) or self.trace.get("error"):
            self.close()
            raise RuntimeError(f"Cannot observe native exception dispatch: {self.trace}")
        return self

    def close(self):
        self.stop_requested.set()
        self.worker.join(timeout=5)
        if self.worker.is_alive():
            self.trace["error"] = "Exception observer thread did not finish"
        return self.trace

    def finish(self):
        self.worker.join(timeout=5)
        if self.worker.is_alive():
            self.close()
        return self.trace

    def _observe(self):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.DebugActiveProcess.argtypes = [wintypes.DWORD]
        kernel.DebugActiveProcess.restype = wintypes.BOOL
        kernel.DebugActiveProcessStop.argtypes = [wintypes.DWORD]
        kernel.DebugActiveProcessStop.restype = wintypes.BOOL
        kernel.DebugSetProcessKillOnExit.argtypes = [wintypes.BOOL]
        kernel.DebugSetProcessKillOnExit.restype = wintypes.BOOL
        kernel.WaitForDebugEvent.argtypes = [ctypes.POINTER(_DebugEvent), wintypes.DWORD]
        kernel.WaitForDebugEvent.restype = wintypes.BOOL
        kernel.ContinueDebugEvent.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
        kernel.ContinueDebugEvent.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        attached = False
        initial_breakpoint = True
        try:
            if not kernel.DebugActiveProcess(self.pid):
                raise ctypes.WinError(ctypes.get_last_error())
            attached = True
            # Never let harness failure or debugger exit kill the tested app.
            if not kernel.DebugSetProcessKillOnExit(False):
                raise ctypes.WinError(ctypes.get_last_error())
            self.trace["attached"] = True
            self.ready.set()
            while not self.stop_requested.is_set():
                event = _DebugEvent()
                if not kernel.WaitForDebugEvent(ctypes.byref(event), 200):
                    if ctypes.get_last_error() == 121:  # ERROR_SEM_TIMEOUT
                        continue
                    raise ctypes.WinError(ctypes.get_last_error())
                code, first = 0, False
                item = {
                    "kind": event.kind,
                    "pid": event.pid,
                    "tid": event.tid,
                    "observed_at": datetime.now(UTC).isoformat(),
                    "monotonic": time.monotonic(),
                }
                if event.kind == 1:
                    code = event.payload.exception.record.code
                    first = bool(event.payload.exception.first_chance)
                    item.update(code=f"0x{code:08x}", first_chance=first)
                    item["attach_breakpoint"] = initial_breakpoint and code == 0x80000003
                if event.kind == 5:
                    self.trace["exit_code"] = int(event.payload.exit_code)
                self.trace["events"].append(item)
                status = continuation(event.kind, code, first, initial_breakpoint)
                if event.kind == 1 and code == 0x80000003 and first and initial_breakpoint:
                    initial_breakpoint = False
                if event.kind == 3 and event.payload.created.file:
                    kernel.CloseHandle(event.payload.created.file)
                if event.kind == 6 and event.payload.loaded.file:
                    kernel.CloseHandle(event.payload.loaded.file)
                if not kernel.ContinueDebugEvent(event.pid, event.tid, status):
                    raise ctypes.WinError(ctypes.get_last_error())
                if event.kind == 5:
                    self.trace["completed"] = True
                    attached = False
                    break
        except Exception as error:
            self.trace["error"] = f"{type(error).__name__}: {error}"
        finally:
            if attached:
                self.trace["detached_without_termination"] = bool(
                    kernel.DebugActiveProcessStop(self.pid)
                )
            self.ready.set()
