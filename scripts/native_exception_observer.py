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
from pathlib import Path
import struct
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


def classify_legacy_sip_shutdown(trace, state, activities, log, dump, exe_sha256, sip_sha256):
    """Identify only the immutable 4.3.3 post-DB-close SIP teardown fault.

    This is a FAILED historical launch, never a successful candidate launch.
    The caller must separately check the closed synthetic DB before using it as
    an upgrade-from-crashed-legacy fixture. New candidate exits remain strict.
    """
    if (
        exe_sha256 != "1363e829f3c71e4e38222497076237c84fff5875d056ca6f50a7f6067e5100d5"
        or sip_sha256 != "3f36d67b20f505dde46032f79d5e384ef3ba34faed586ee086f5827867f6bdb0"
        or trace.get("error")
        or not trace.get("attached")
        or not trace.get("completed")
        or trace.get("exit_code") != 0xC0000005
        or state.get("parent_exit_code") != 0xC0000005
        or state.get("remaining_native_pids") != []
        or state.get("force_killed") is not False
        or trace.get("pid") != state.get("launched_parent_pid")
        or not isinstance(trace.get("pid"), int)
        or trace["pid"] <= 0
    ):
        raise RuntimeError("Not the pinned historical SIP shutdown failure")
    events = trace["events"]
    if any(row.get("pid") != trace["pid"] or row["kind"] == 9 for row in events):
        raise RuntimeError("Legacy observer has unrelated or RIP events")
    if len([row for row in events if row["kind"] == 5]) != 1:
        raise RuntimeError("Missing unique historical process-exit event")
    exceptions = [row for row in events if row["kind"] == 1]
    faults = [row for row in exceptions if not row["first_chance"]]
    if len(faults) != 1 or faults[0]["code"] != "0xc0000005":
        raise RuntimeError("Legacy failure has another second-chance exception")
    for row in exceptions:
        if row["code"] not in {"0xc0000005", "0x8001010d", "0x80000003"}:
            raise RuntimeError("Legacy failure has an unclassified exception")
        if row["code"] == "0x80000003" and not row.get("attach_breakpoint"):
            raise RuntimeError("Legacy failure has an unrelated breakpoint")
    fault = faults[0]
    access = [row for row in exceptions if row["code"] == "0xc0000005"]
    if (
        len(access) != 2
        or not access[0]["first_chance"]
        or access[1]["first_chance"]
        or access[0].get("exception_address") != fault.get("exception_address")
        or access[0].get("exception_parameters") != fault.get("exception_parameters")
        or access[0].get("tid") != fault.get("tid")
        or not fault.get("exception_parameters")
        or fault["exception_parameters"][0] != 0
    ):
        raise RuntimeError("Missing exact first/second-chance legacy read-fault pair")
    if not any(
        row["phase"] == "exit_confirmation_observed"
        and row["process_running"]
        and row["monotonic"] < fault["monotonic"]
        for row in activities
    ) or not any(row["phase"] == "exit_yes_clicked" for row in activities):
        raise RuntimeError("No normal legacy Exit confirmation/input evidence")
    required = (
        "Shutting down background workers",
        "AlarmWorker stopping",
        f"Database connection closed for thread {fault['tid']}.",
    )
    if any(marker not in log for marker in required):
        raise RuntimeError("Legacy failure preceded main-thread database shutdown")
    if dump[:4] != b"MDMP" or len(dump) < 32:
        raise RuntimeError("Missing valid legacy crash dump")
    streams, directory = struct.unpack_from("<II", dump, 8)
    if streams > 1000 or directory + streams * 12 > len(dump):
        raise RuntimeError("Invalid legacy dump directory")
    address = int(fault["exception_address"], 16)
    expected_tail = b"".join(bytes((ord(c), 0)) for c in "\\PyQt6\\sip.cp313-win_amd64.pyd")
    identified = False
    for index in range(streams):
        kind, size, rva = struct.unpack_from("<III", dump, directory + index * 12)
        if kind != 4:
            continue
        if size < 4 or rva + size > len(dump):
            raise RuntimeError("Invalid legacy module stream")
        count = struct.unpack_from("<I", dump, rva)[0]
        if count > 5000 or 4 + count * 108 > size:
            raise RuntimeError("Invalid legacy module count")
        for number in range(count):
            base, image_size, _checksum, timestamp, name_rva = struct.unpack_from(
                "<QIIII", dump, rva + 4 + number * 108
            )
            if not base <= address < base + image_size:
                continue
            if name_rva + 4 > len(dump):
                raise RuntimeError("Invalid legacy module name")
            length = struct.unpack_from("<I", dump, name_rva)[0]
            if length > 8192 or length % 2 or name_rva + 4 + length > len(dump):
                raise RuntimeError("Invalid legacy module name bounds")
            name = dump[name_rva + 4 : name_rva + 4 + length]
            identified = (
                name.lower().endswith(expected_tail.lower())
                and image_size == 131072
                and timestamp == 1773058744
                and address - base == 0x10496
            )
    if not identified:
        raise RuntimeError("Legacy fault is not the pinned SIP instruction/module")
    return {
        "passed": False,
        "normal_exit": False,
        "exit_code": 0xC0000005,
        "classification": "historical_4.3.3_sip_13.11.1_post_database_close_fault",
        "fault_offset": "0x10496",
        "candidate_exit_requirement_unchanged": "all six candidate launches must exit zero",
        "profile_integrity_check_required": True,
    }


def write_crash_dump(pid: int, destination: Path) -> None:
    """Read a failed disposable debuggee from this separate observer process.

    No exception context is fabricated; the event records the fault address and
    thread separately, and the dump retains the suspended thread contexts.
    """
    import msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    process = kernel.OpenProcess(0x0410, False, pid)  # QUERY_INFORMATION | VM_READ
    if not process:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        dbghelp = ctypes.WinDLL("dbghelp", use_last_error=True)
        dbghelp.MiniDumpWriteDump.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        dbghelp.MiniDumpWriteDump.restype = wintypes.BOOL
        with destination.open("wb") as stream:
            if not dbghelp.MiniDumpWriteDump(
                process,
                pid,
                msvcrt.get_osfhandle(stream.fileno()),
                0x1000,
                None,
                None,
                None,
            ):
                raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(process)


class ExceptionObserver:
    def __init__(self, pid: int, guard, *, evidence: Path | None = None):
        guard()  # Caller repeats the hosted-runner safety contract before attach.
        self.pid = pid
        self.evidence = evidence
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
                    record = event.payload.exception.record
                    item["exception_address"] = f"0x{int(record.address or 0):016x}"
                    item["exception_parameters"] = [
                        int(record.parameters[index])
                        for index in range(min(int(record.parameter_count), 15))
                    ]
                    item["attach_breakpoint"] = initial_breakpoint and code == 0x80000003
                    if not first and self.evidence is not None:
                        try:
                            dump = self.evidence / f"native-second-chance-{event.tid}.dmp"
                            write_crash_dump(self.pid, dump)
                            item["diagnostic_dump"] = dump.name
                        except Exception as error:
                            item["diagnostic_dump_error"] = f"{type(error).__name__}: {error}"
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
