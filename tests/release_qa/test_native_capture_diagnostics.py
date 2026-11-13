# -*- coding: utf-8 -*-
"""Native diagnostics never change the gate or operate an actual desktop here."""

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

_PATH = Path(__file__).with_name("native_capture_diagnostics.py")
_SPEC = importlib.util.spec_from_file_location("air_native_diagnostics", _PATH)
diagnostics = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(diagnostics)


def smoke_fixture(original):
    return SimpleNamespace(
        _verify_capture_visibility=original,
        require_hosted_runner=Mock(),
        os=SimpleNamespace(environ={}),
        sys=SimpleNamespace(platform="unit-test"),
        write_json=Mock(),
    )


def test_original_visibility_result_and_exact_arguments_are_preserved(tmp_path):
    expected = {"passed": True}
    original = Mock(return_value=expected)
    smoke = smoke_fixture(original)
    snapshot = Mock(return_value={"observed": True})
    window, controls = object(), [{"name": "System"}]
    with diagnostics.install_diagnostics(smoke, snapshot=snapshot):
        result = smoke._verify_capture_visibility(window, tmp_path, controls, "prepared")
    assert result is expected
    original.assert_called_once_with(window, tmp_path, controls, "prepared")
    snapshot.assert_called_once_with(smoke, window, tmp_path, controls, "prepared-before-gate")
    assert smoke._verify_capture_visibility is original


@pytest.mark.parametrize("snapshot_fails", [False, True])
def test_original_failure_is_reraised_with_before_and_after_evidence(tmp_path, snapshot_fails):
    failure = RuntimeError("Actual main window is not foreground or is obscured")
    original = Mock(side_effect=failure)
    smoke = smoke_fixture(original)
    snapshot = (
        Mock(side_effect=OSError("capture unavailable"))
        if snapshot_fails
        else Mock(return_value={})
    )
    with (
        diagnostics.install_diagnostics(smoke, snapshot=snapshot),
        pytest.raises(RuntimeError) as error,
    ):
        smoke._verify_capture_visibility(object(), tmp_path, [], "prepared")
    assert error.value is failure
    assert snapshot.call_count == 2
    assert smoke.write_json.call_args_list[0].args[0].name == "diagnostic-prepared-before-gate.json"
    assert smoke.write_json.call_args_list[1].args[0].name == "diagnostic-prepared-gate-failed.json"
    assert smoke._verify_capture_visibility is original


def test_local_guard_rejects_before_snapshot_and_original_gate(tmp_path):
    original = Mock()
    smoke = smoke_fixture(original)
    smoke.require_hosted_runner.side_effect = RuntimeError("hosted only")
    snapshot = Mock()
    with (
        diagnostics.install_diagnostics(smoke, snapshot=snapshot),
        pytest.raises(RuntimeError, match="hosted"),
    ):
        smoke._verify_capture_visibility(object(), tmp_path, [], "prepared")
    snapshot.assert_not_called()
    original.assert_not_called()


@pytest.mark.parametrize("fails", [False, True])
def test_diagnostic_write_failure_cannot_replace_original_result_or_error(tmp_path, fails):
    expected = RuntimeError("original occlusion") if fails else {"original": "success"}
    original = Mock(side_effect=expected) if fails else Mock(return_value=expected)
    smoke = smoke_fixture(original)
    smoke.write_json.side_effect = OSError("diagnostic disk full")
    with diagnostics.install_diagnostics(smoke, snapshot=Mock(return_value={})):
        if fails:
            with pytest.raises(RuntimeError) as error:
                smoke._verify_capture_visibility(object(), tmp_path, [], "prepared")
            assert error.value is expected
        else:
            assert smoke._verify_capture_visibility(object(), tmp_path, [], "prepared") is expected
    original.assert_called_once()


def test_snapshot_records_foreign_root_zorder_and_actual_desktop_crop(tmp_path, monkeypatch):
    # Main is foreground, but a distinct higher-Z system window covers its left side.
    constants = SimpleNamespace(
        GW_HWNDNEXT=2,
        GW_OWNER=4,
        GA_ROOT=2,
        GA_ROOTOWNER=3,
        GWL_STYLE=-16,
        GWL_EXSTYLE=-20,
        WS_EX_LAYERED=0x80000,
        SM_XVIRTUALSCREEN=76,
        SM_YVIRTUALSCREEN=77,
        SM_CXVIRTUALSCREEN=78,
        SM_CYVIRTUALSCREEN=79,
    )
    gui = SimpleNamespace(
        GetTopWindow=lambda _value: 20,
        GetWindow=lambda handle, kind: {20: 10, 10: 0}[handle] if kind == 2 else 0,
        WindowFromPoint=lambda point: 21 if point[0] < 100 else 10,
        GetAncestor=lambda handle, _kind: 20 if handle == 21 else handle,
        GetWindowText=lambda handle: (
            "Performance Options" if handle in (20, 21) else "Air Calendar"
        ),
        GetClassName=lambda handle: "#32770" if handle in (20, 21) else "Qt6120QWindowToolSaveBits",
        GetWindowRect=lambda _handle: (0, 0, 300, 200),
        GetParent=lambda handle: 20 if handle == 21 else 0,
        IsWindowVisible=lambda _handle: True,
        IsWindowEnabled=lambda _handle: True,
        IsIconic=lambda _handle: False,
        GetWindowLong=lambda handle, kind: 0x80000 if handle == 10 and kind == -20 else 0,
        GetLayeredWindowAttributes=lambda _handle: (0, 255, 2),
        GetForegroundWindow=lambda: 10,
    )
    pixels = Mock()
    pixels.crop.return_value = Mock()
    grab = Mock(return_value=pixels)
    monkeypatch.setitem(sys.modules, "win32con", constants)
    monkeypatch.setitem(sys.modules, "win32gui", gui)
    monkeypatch.setitem(
        sys.modules,
        "win32process",
        SimpleNamespace(
            GetWindowThreadProcessId=lambda handle: (1, 99 if handle in (20, 21) else 88)
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "win32api",
        SimpleNamespace(GetSystemMetrics=lambda key: {76: 0, 77: 0, 78: 1024, 79: 768}[key]),
    )
    monkeypatch.setitem(
        sys.modules,
        "psutil",
        SimpleNamespace(
            Process=lambda pid: SimpleNamespace(exe=lambda: f"C:/system/{pid}.exe"), Error=OSError
        ),
    )
    monkeypatch.setitem(sys.modules, "PIL", SimpleNamespace(ImageGrab=SimpleNamespace(grab=grab)))
    smoke = smoke_fixture(Mock())
    smoke.capture_points = lambda _bounds, _controls: [
        {"source": "grid", "point": [50, 50]},
        {"source": "System", "point": [200, 50]},
    ]
    window = SimpleNamespace(
        handle=10, rectangle=lambda: SimpleNamespace(left=6, top=6, right=500, bottom=700)
    )
    value = diagnostics.capture_snapshot(smoke, window, tmp_path, [], "prepared")
    assert value["main_z_order"] == 1
    assert value["visible_samples"][0]["root_z_order"] == 0
    assert value["hit_windows"][1]["pid"] == 99
    assert value["top_level_windows_front_to_back"][0]["title"] == "Performance Options"
    assert value["top_level_windows_front_to_back"][1]["layered_attributes"] == [0, 255, 2]
    assert value["windows_changed"] is False
    grab.assert_called_once_with(bbox=(0, 0, 1024, 768), all_screens=True)
    pixels.crop.assert_called_once_with((6, 6, 500, 700))
    assert pixels.save.call_args.args[0].name == "diagnostic-prepared-desktop.png"


def test_diagnostic_entrypoint_delegates_original_six_cycles():
    source = _PATH.with_name("native_diagnostic_smoke.py").read_text(
        encoding="utf-8", errors="strict"
    )
    assert "return native_release_smoke.main(argv)" in source
    compact = "".join(source.split())
    assert (
        "install_adapter(native_release_smoke),install_owner_adapter(native_release_smoke),install_diagnostics(native_release_smoke)"
        in compact
    )
    for forbidden in (
        "SetForegroundWindow",
        "ShowWindow",
        "TerminateProcess",
        "classify_rpc",
        "SetWindowLong",
    ):
        assert forbidden not in _PATH.read_text(encoding="utf-8", errors="strict")
