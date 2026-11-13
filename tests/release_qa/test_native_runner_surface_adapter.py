# -*- coding: utf-8 -*-
"""Pure disposable-runner surface contracts; no real window or settings input."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from scripts import native_release_smoke as original_smoke

_PATH = Path(__file__).with_name("native_runner_surface_adapter.py")
_SPEC = importlib.util.spec_from_file_location("air_runner_surface_adapter", _PATH)
adapter = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(adapter)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    system = tmp_path / "Windows"
    executable = system / "System32/SystemPropertiesPerformance.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"synthetic identity fixture; never execute")
    monkeypatch.setenv("SYSTEMROOT", str(system))
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    notice = {
        "handle": 50,
        "pid": 636,
        "title": "System Properties",
        "class_name": "#32770",
        "executable": str(executable),
        "children": [
            {"handle": 51, "class_name": "Button", "text": "OK", "control_id": 2},
            {"handle": 52, "class_name": "Static", "text": original_smoke.PAGING_NOTICE},
        ],
    }
    result = {
        "handle": 50,
        "button": 51,
        "before": deepcopy(notice),
        "ok_clicked": True,
        "notice_still_exists": False,
    }
    acknowledged = {"handle": 50, "ok_clicked": True, "settings_changed": False}
    proofs = [notice, result, acknowledged]

    def dismiss(_window, directory):
        for name, value in zip(adapter._NOTICE_FILES, proofs, strict=True):
            (directory / name).write_text(json.dumps(value), encoding="utf-8", errors="strict")
        return "original-dismiss-result"

    smoke = SimpleNamespace(
        _dismiss_paging_notice=Mock(side_effect=dismiss),
        require_hosted_runner=Mock(),
        os=SimpleNamespace(environ={"SYSTEMROOT": str(system)}),
        sys=SimpleNamespace(platform="unit-test"),
        select_paging_notice=original_smoke.select_paging_notice,
        write_json=Mock(),
    )
    window = SimpleNamespace(handle=10, process_id=lambda: 42)
    surface = {
        "handle": 100,
        "exists": True,
        "pid": 636,
        "executable": str(executable),
        "process_created": 123.0,
        "title": "Performance Options",
        "class_name": "#32770",
        "visible": True,
        "minimized": False,
    }
    state = {"minimized": False, "notice_reused": False, "current_changes": {}}

    def describe(handle):
        if handle == 50:
            return {"handle": handle, "exists": state["notice_reused"]}
        return {**surface, **state["current_changes"], "minimized": state["minimized"]}

    def minimize(_handle):
        state["minimized"] = True

    backend = SimpleNamespace(
        windows=Mock(side_effect=lambda: [dict(surface)]),
        describe=Mock(side_effect=describe),
        minimize=Mock(side_effect=minimize),
    )
    return SimpleNamespace(
        smoke=smoke,
        window=window,
        evidence=evidence,
        executable=executable,
        notice=notice,
        result=result,
        acknowledged=acknowledged,
        backend=backend,
        surface=surface,
        state=state,
    )


def test_only_newly_proven_exact_surface_is_minimized_and_original_result_is_preserved(fixture):
    f = fixture
    original = f.smoke._dismiss_paging_notice
    with adapter.install_runner_surface_adapter(f.smoke, backend_factory=lambda: f.backend):
        assert f.smoke._dismiss_paging_notice(f.window, f.evidence) == "original-dismiss-result"
    assert f.smoke._dismiss_paging_notice is original
    f.backend.minimize.assert_called_once_with(100)
    report = f.smoke.write_json.call_args.args[1]
    assert report["operation"] == "SW_MINIMIZE"
    assert report["settings_changed"] is False
    assert report["paging_provenance"]["notice"]["pid"] == 636
    assert report["raw_windows"] == [f.surface]
    assert report["after"]["minimized"] is True


@pytest.mark.parametrize(
    "key,value",
    [
        ("pid", 777),
        ("pid", 42),
        ("title", "Other settings"),
        ("class_name", "Qt6120QWindow"),
        ("visible", False),
        ("exists", False),
        ("minimized", True),
        ("executable", "C:/untrusted/SystemPropertiesPerformance.exe"),
    ],
)
def test_other_process_title_class_executable_or_invisible_surface_is_untouched(
    fixture, key, value
):
    f = fixture
    f.surface[key] = value
    with adapter.install_runner_surface_adapter(f.smoke, backend_factory=lambda: f.backend):
        f.smoke._dismiss_paging_notice(f.window, f.evidence)
    f.backend.minimize.assert_not_called()


@pytest.mark.parametrize(
    "problem",
    ["notice_exe", "notice_body", "before_identity", "ack", "settings", "still_exists", "button"],
)
def test_incomplete_or_changed_original_notice_proof_never_operates_any_window(fixture, problem):
    f = fixture
    if problem == "notice_exe":
        f.notice["executable"] = "C:/untrusted/SystemPropertiesPerformance.exe"
    elif problem == "notice_body":
        f.notice["children"][1]["text"] = "Unrelated notice"
    elif problem == "before_identity":
        f.result["before"]["pid"] = 777
    elif problem == "ack":
        f.acknowledged["ok_clicked"] = False
    elif problem == "settings":
        f.acknowledged["settings_changed"] = True
    elif problem == "still_exists":
        f.result["notice_still_exists"] = True
    elif problem == "button":
        f.result["button"] = 999
    factory = Mock(return_value=f.backend)
    with adapter.install_runner_surface_adapter(f.smoke, backend_factory=factory):
        f.smoke._dismiss_paging_notice(f.window, f.evidence)
    factory.assert_not_called()
    f.backend.minimize.assert_not_called()


@pytest.mark.parametrize(
    "problem", ["stale", "missing", "reused", "ambiguous", "pid_race", "exe_race", "time_race"]
)
def test_no_stale_provenance_handle_reuse_ambiguity_or_identity_race_is_accepted(fixture, problem):
    f = fixture
    if problem == "stale":
        (f.evidence / adapter._NOTICE_FILES[0]).write_bytes(b"{}")
    elif problem == "missing":
        f.smoke._dismiss_paging_notice = Mock(return_value="no notice")
    elif problem == "reused":
        f.state["notice_reused"] = True
    elif problem == "ambiguous":
        f.backend.windows.side_effect = lambda: [dict(f.surface), {**f.surface, "handle": 101}]
    elif problem == "pid_race":
        f.state["current_changes"] = {"pid": 777}
    elif problem == "exe_race":
        f.state["current_changes"] = {"executable": "C:/other.exe"}
    elif problem == "time_race":
        f.state["current_changes"] = {"process_created": 456.0}
    with adapter.install_runner_surface_adapter(f.smoke, backend_factory=lambda: f.backend):
        f.smoke._dismiss_paging_notice(f.window, f.evidence)
    f.backend.minimize.assert_not_called()


def test_guard_precedes_original_provenance_reads_and_native_imports(fixture):
    f = fixture
    f.smoke.require_hosted_runner.side_effect = RuntimeError("hosted and temp only")
    factory = Mock()
    with (
        adapter.install_runner_surface_adapter(f.smoke, backend_factory=factory),
        pytest.raises(RuntimeError, match="hosted and temp"),
    ):
        f.smoke._dismiss_paging_notice(f.window, f.evidence)
    f.smoke._dismiss_paging_notice.assert_not_called()
    factory.assert_not_called()


def test_original_notice_failure_is_preserved_and_adapter_restores(fixture):
    f = fixture
    error = RuntimeError("original notice input failed")
    f.smoke._dismiss_paging_notice.side_effect = error
    original = f.smoke._dismiss_paging_notice
    factory = Mock()
    with (
        adapter.install_runner_surface_adapter(f.smoke, backend_factory=factory),
        pytest.raises(RuntimeError) as caught,
    ):
        f.smoke._dismiss_paging_notice(f.window, f.evidence)
    assert caught.value is error
    assert f.smoke._dismiss_paging_notice is original
    factory.assert_not_called()


@pytest.mark.parametrize("gate_fails,io_fails", [(False, False), (True, False), (False, True)])
def test_real_original_prepare_keeps_foreground_and_exact_visibility_gate(
    fixture, monkeypatch, gate_fails, io_fails
):
    f = fixture
    gui = SimpleNamespace(
        EnumWindows=lambda _callback, _context: None, ShowWindow=Mock(), SetForegroundWindow=Mock()
    )
    monkeypatch.setitem(sys.modules, "win32gui", gui)
    monkeypatch.setitem(sys.modules, "win32con", SimpleNamespace(SW_RESTORE=9))
    monkeypatch.setattr(original_smoke, "require_hosted_runner", Mock())
    monkeypatch.setattr(original_smoke, "_dismiss_paging_notice", f.smoke._dismiss_paging_notice)
    write = Mock(side_effect=OSError("diagnostic disk failure")) if io_fails else Mock()
    monkeypatch.setattr(original_smoke, "write_json", write)
    monkeypatch.setattr(original_smoke.time, "sleep", lambda _seconds: None)
    error = RuntimeError("original foreground/physical visibility gate failed")
    gate = Mock(side_effect=error) if gate_fails else Mock(return_value={"original_gate": True})
    monkeypatch.setattr(original_smoke, "_verify_capture_visibility", gate)
    with adapter.install_runner_surface_adapter(original_smoke, backend_factory=lambda: f.backend):
        if gate_fails:
            with pytest.raises(RuntimeError) as caught:
                original_smoke._prepare_visible_main(f.window, f.evidence)
            assert caught.value is error
        elif io_fails:
            # The original final evidence write may fail; its own failure is preserved too.
            with pytest.raises(OSError, match="diagnostic disk failure"):
                original_smoke._prepare_visible_main(f.window, f.evidence)
        else:
            assert original_smoke._prepare_visible_main(f.window, f.evidence)["original_gate"]
    f.backend.minimize.assert_called_once_with(100)
    gui.ShowWindow.assert_called_once_with(10, 9)
    gui.SetForegroundWindow.assert_called_once_with(10)
    gate.assert_called_once_with(f.window, f.evidence, [], "prepared")


def test_native_minimizer_has_only_the_exact_sw_minimize_operation(monkeypatch):
    show = Mock()
    monkeypatch.setitem(sys.modules, "win32gui", SimpleNamespace(ShowWindow=show))
    monkeypatch.setitem(sys.modules, "win32con", SimpleNamespace(SW_MINIMIZE=6))
    monkeypatch.setitem(sys.modules, "win32process", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "psutil", SimpleNamespace())
    adapter.Win32RunnerSurface().minimize(100)
    show.assert_called_once_with(100, 6)
