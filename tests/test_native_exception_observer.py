# -*- coding: utf-8 -*-
"""Pure/mocked debugger tests: no process, debugger or GUI is started locally."""

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
