# -*- coding: utf-8 -*-
"""Pure/mocked debugger tests: no process, debugger or GUI is started locally."""

from copy import deepcopy
import struct
from unittest.mock import Mock

import pytest
from scripts import native_exception_observer as observer


@pytest.mark.parametrize(
    "kind,code,first,initial,expected",
    [
        (1, 0x80000003, True, True, 0x10002),
        (1, 0x80000003, False, True, 0x80010001),
        (1, 0x80000003, True, False, 0x80010001),
        (1, 0x8001010D, True, True, 0x80010001),
        (1, 0x8001010D, False, False, 0x80010001),
        (1, 0xC0000005, True, False, 0x80010001),
        (5, 0, False, False, 0x10002),
    ],
)
def test_original_application_exception_dispatch_is_preserved(kind, code, first, initial, expected):
    assert observer.continuation(kind, code, first, initial) == expected


def trace():
    return {
        "pid": 42,
        "attached": True,
        "completed": True,
        "exit_code": 0,
        "events": [
            {"kind": 1, "pid": 42, "code": "0x8001010d", "first_chance": True},
            {"kind": 5, "pid": 42},
        ],
    }


def test_exact_rpc_needs_complete_first_chance_and_exit_process_zero_evidence():
    report = observer.classify_rpc(trace(), 1, 42)
    assert report["classification"] == "handled_first_chance"
    assert report["rpc_event_count"] == 1
    assert "not determined" in report["handler_identity"]
    assert "timing" in report["debugger_timing_limitation"]


@pytest.mark.parametrize(
    "change",
    [
        {"attached": False},
        {"completed": False},
        {"error": "observer stopped"},
        {"pid": 43},
        {"exit_code": 1},
        {"events": []},
    ],
)
def test_incomplete_or_failed_debuggee_never_classifies_as_recovered(change):
    value = trace()
    value.update(change)
    with pytest.raises(RuntimeError):
        observer.classify_rpc(value, 1, 42)


def test_second_chance_or_different_pid_or_unmatched_log_fails():
    value = trace()
    value["events"][0]["first_chance"] = False
    with pytest.raises(RuntimeError, match="second-chance"):
        observer.classify_rpc(value, 1, 42)
    value = trace()
    value["events"][0]["pid"] = 43
    with pytest.raises(RuntimeError, match="unrelated"):
        observer.classify_rpc(value, 1, 42)
    with pytest.raises(RuntimeError, match="do not match"):
        observer.classify_rpc(trace(), 0, 42)


@pytest.mark.parametrize("code", ["0xc0000005", "0xc00000fd", "0x8001010e"])
def test_unknown_native_error_cannot_pass_even_without_a_faulthandler_log(code):
    value = trace()
    value["events"][0]["code"] = code
    with pytest.raises(RuntimeError, match="unclassified"):
        observer.classify_rpc(value, 0, 42)


def test_native_rip_debugger_error_cannot_pass():
    value = trace()
    value["events"].append({"kind": 9, "pid": 42})
    with pytest.raises(RuntimeError, match="RIP"):
        observer.classify_rpc(value, 1, 42)


def test_guard_precedes_debugger_or_thread_creation():
    guard = Mock(side_effect=RuntimeError("CI only"))
    with pytest.raises(RuntimeError, match="CI only"):
        observer.ExceptionObserver(42, guard)
    guard.assert_called_once_with()


def test_mocked_native_debug_loop_keeps_kill_on_exit_disabled_and_passes_rpc(monkeypatch):
    kernel = Mock()
    kernel.DebugActiveProcess.return_value = True
    kernel.DebugSetProcessKillOnExit.return_value = True
    kernel.ContinueDebugEvent.return_value = True
    pending = iter([(3, 0), (1, 0x80000003), (1, 0x8001010D), (5, 0)])

    def wait(pointer, _timeout):
        kind, code = next(pending)
        event = pointer._obj
        event.kind, event.pid, event.tid = kind, 42, 17
        if kind == 1:
            event.payload.exception.record.code = code
            event.payload.exception.first_chance = 1
        if kind == 5:
            event.payload.exit_code = 0
        return True

    kernel.WaitForDebugEvent.side_effect = wait
    monkeypatch.setattr(observer.ctypes, "WinDLL", lambda *_args, **_kwargs: kernel)
    instance = observer.ExceptionObserver(42, lambda: None)
    instance._observe()
    kernel.DebugSetProcessKillOnExit.assert_called_once_with(False)
    statuses = [call.args[2] for call in kernel.ContinueDebugEvent.call_args_list]
    assert statuses == [0x10002, 0x10002, 0x80010001, 0x10002]
    kernel.DebugActiveProcessStop.assert_not_called()
    assert observer.classify_rpc(instance.trace, 1, 42)["classification"] == "handled_first_chance"


def test_failed_observer_detaches_without_terminating_target(monkeypatch):
    kernel = Mock()
    kernel.DebugActiveProcess.return_value = True
    kernel.DebugSetProcessKillOnExit.return_value = True
    kernel.WaitForDebugEvent.side_effect = RuntimeError("observer interrupted")
    monkeypatch.setattr(observer.ctypes, "WinDLL", lambda *_args, **_kwargs: kernel)
    instance = observer.ExceptionObserver(42, lambda: None)
    instance._observe()
    kernel.DebugActiveProcessStop.assert_called_once_with(42)
    assert not instance.trace["completed"]
    assert "observer interrupted" in instance.trace["error"]


def test_x64_debug_event_layout_matches_windows_sdk():
    # Layout checks do not call an OS API or attach to any process.
    if observer.ctypes.sizeof(observer.ctypes.c_void_p) == 8:
        assert observer.ctypes.sizeof(observer._ExceptionRecord) == 152
        assert observer._DebugEvent.payload.offset == 16
        assert observer.ctypes.sizeof(observer._DebugEvent) == 176


@pytest.mark.parametrize("dump_fails", [False, True])
def test_second_chance_retains_fault_details_without_consuming_exception(
    tmp_path, monkeypatch, dump_fails
):
    kernel = Mock()
    kernel.DebugActiveProcess.return_value = True
    kernel.DebugSetProcessKillOnExit.return_value = True
    kernel.ContinueDebugEvent.return_value = True
    pending = iter([(1, 0x80000003, True), (1, 0xC0000005, False), (5, 0, False)])

    def wait(pointer, _timeout):
        kind, code, first = next(pending)
        event = pointer._obj
        event.kind, event.pid, event.tid = kind, 42, 17
        if kind == 1:
            record = event.payload.exception.record
            record.code, record.address = code, 0x123456789ABC
            record.parameter_count = 2
            record.parameters[0], record.parameters[1] = 0, 0xDEAD
            event.payload.exception.first_chance = first
        else:
            event.payload.exit_code = 0xC0000005
        return True

    kernel.WaitForDebugEvent.side_effect = wait
    dumper = Mock(side_effect=OSError("synthetic dump failure") if dump_fails else None)
    monkeypatch.setattr(observer.ctypes, "WinDLL", lambda *_args, **_kwargs: kernel)
    monkeypatch.setattr(observer, "write_crash_dump", dumper)
    instance = observer.ExceptionObserver(42, lambda: None, evidence=tmp_path)
    instance._observe()
    fault = instance.trace["events"][1]
    assert fault["exception_address"] == "0x0000123456789abc"
    assert fault["exception_parameters"] == [0, 0xDEAD]
    dumper.assert_called_once_with(42, tmp_path / "native-second-chance-17.dmp")
    if dump_fails:
        assert "synthetic dump failure" in fault["diagnostic_dump_error"]
    else:
        assert fault["diagnostic_dump"] == "native-second-chance-17.dmp"
    assert kernel.ContinueDebugEvent.call_args_list[1].args[2] == 0x80010001
    with pytest.raises(RuntimeError, match="exit code zero"):
        observer.classify_rpc(instance.trace, 0, 42)


def legacy_failure():
    fault = {
        "kind": 1,
        "pid": 42,
        "tid": 17,
        "code": "0xc0000005",
        "first_chance": True,
        "exception_address": "0x110496",
        "exception_parameters": [0, 123],
        "monotonic": 5,
    }
    second = {**fault, "first_chance": False}
    trace = {
        "pid": 42,
        "attached": True,
        "completed": True,
        "exit_code": 0xC0000005,
        "events": [fault, second, {"kind": 5, "pid": 42}],
    }
    state = {
        "launched_parent_pid": 42,
        "parent_exit_code": 0xC0000005,
        "remaining_native_pids": [],
        "force_killed": False,
    }
    activities = [
        {"phase": "exit_confirmation_observed", "process_running": True, "monotonic": 4},
        {"phase": "exit_yes_clicked"},
    ]
    log = "Shutting down background workers\nAlarmWorker stopping\nDatabase connection closed for thread 17."
    dump = bytearray(256)
    dump[:4] = b"MDMP"
    struct.pack_into("<II", dump, 8, 1, 32)
    struct.pack_into("<III", dump, 32, 4, 112, 44)
    struct.pack_into("<I", dump, 44, 1)
    struct.pack_into("<QIIII", dump, 48, 0x100000, 131072, 0, 1773058744, 160)
    name = b"".join(bytes((ord(c), 0)) for c in "D:\\PyQt6\\sip.cp313-win_amd64.pyd")
    struct.pack_into("<I", dump, 160, len(name))
    dump[164 : 164 + len(name)] = name
    return trace, state, activities, log, bytes(dump)


def test_known_old_shutdown_failure_remains_failed_and_requires_database_validation():
    result = observer.classify_legacy_sip_shutdown(
        *legacy_failure(),
        "1363e829f3c71e4e38222497076237c84fff5875d056ca6f50a7f6067e5100d5",
        "3f36d67b20f505dde46032f79d5e384ef3ba34faed586ee086f5827867f6bdb0",
    )
    assert result["passed"] is False and result["normal_exit"] is False
    assert result["profile_integrity_check_required"] is True
    assert "all six candidate" in result["candidate_exit_requirement_unchanged"]


@pytest.mark.parametrize(
    "change",
    [
        "candidate_exe",
        "sip_binary",
        "incomplete",
        "alive",
        "killed",
        "different_pid",
        "no_exit",
        "other_exception",
        "no_first",
        "no_confirmation",
        "no_main_db_close",
        "bad_dump",
        "wrong_module",
        "wrong_instruction",
    ],
)
def test_legacy_classification_cannot_exempt_new_or_unproven_failures(change):
    trace, state, activities, log, dump = deepcopy(legacy_failure())
    exe = "1363e829f3c71e4e38222497076237c84fff5875d056ca6f50a7f6067e5100d5"
    sip = "3f36d67b20f505dde46032f79d5e384ef3ba34faed586ee086f5827867f6bdb0"
    if change == "candidate_exe":
        exe = "0" * 64
    elif change == "sip_binary":
        sip = "0" * 64
    elif change == "incomplete":
        trace["completed"] = False
    elif change == "alive":
        state["remaining_native_pids"] = [42]
    elif change == "killed":
        state["force_killed"] = True
    elif change == "different_pid":
        state["launched_parent_pid"] = 43
    elif change == "no_exit":
        trace["events"].pop()
    elif change == "other_exception":
        trace["events"][1]["code"] = "0xc00000fd"
    elif change == "no_first":
        trace["events"].pop(0)
    elif change == "no_confirmation":
        activities.pop(0)
    elif change == "no_main_db_close":
        log = log.replace("thread 17", "thread 18")
    elif change == "bad_dump":
        dump = b"bad"
    elif change == "wrong_module":
        dump = dump.replace(b"s\x00i\x00p\x00", b"b\x00a\x00d\x00")
    elif change == "wrong_instruction":
        for event in trace["events"][:2]:
            event["exception_address"] = "0x110497"
    with pytest.raises(RuntimeError):
        observer.classify_legacy_sip_shutdown(trace, state, activities, log, dump, exe, sip)
