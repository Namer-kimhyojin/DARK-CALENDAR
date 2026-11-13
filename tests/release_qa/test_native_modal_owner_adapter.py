# -*- coding: utf-8 -*-
"""Pure QA ownership contracts; no native desktop, app, settings or network."""

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from scripts import native_release_smoke as original_smoke

_PATH = Path(__file__).with_name("native_modal_owner_adapter.py")
_SPEC = importlib.util.spec_from_file_location("air_modal_owner_adapter", _PATH)
adapter = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(adapter)


def row(**changes):
    return {
        "handle": 20,
        "pid": 42,
        "parent": 0,
        "visible": True,
        "title": "Exit",
        "class_name": "Qt6120QWindowIcon",
        **changes,
    }


def identities():
    base = {
        "native_is_window": True,
        "native_pid": 42,
        "native_style": 0,
        "native_get_parent": 0,
        "native_actual_parent": 0,
        "native_owner": 0,
        "native_root_owner": 10,
    }
    return {10: dict(base), 20: {**base, "native_owner": 10}}


def controls():
    return [
        {
            "name": "Air Calendar is closing.\nThe program will fully exit without minimizing to tray.\nContinue?",
            "control_type": "Text",
            "visible": True,
        },
        {"name": "&Yes", "control_type": "Button", "visible": True, "enabled": True},
        {"name": "&No", "control_type": "Button", "visible": True, "enabled": True},
    ]


@pytest.mark.parametrize("parent", [0, 10])
def test_only_exact_live_owner_supplies_a_missing_selector_parent(parent):
    table = identities()
    table[20]["native_get_parent"] = parent
    raw = row(parent=parent)
    result, decisions = adapter.owner_checked_metadata([raw], 42, 10, table.__getitem__)
    assert result[0]["parent"] == 10
    assert result[0]["native_owner"] == 10
    assert raw["parent"] == parent
    assert decisions[0]["eligible"] is True
    assert (decisions[0]["normalization"] != "none") is (parent == 0)


@pytest.mark.parametrize(
    "case",
    [
        "owner_zero",
        "other_owner",
        "dialog_pid",
        "main_pid",
        "metadata_pid",
        "dead_main",
        "dead_dialog",
        "child",
        "parent_conflict",
        "parent_race",
        "self",
    ],
)
def test_pid_title_or_parent_alone_never_establishes_ownership(case):
    table = identities()
    raw = row()
    if case == "owner_zero":
        table[20]["native_owner"] = 0
    elif case == "other_owner":
        table[20]["native_owner"] = 999
    elif case == "dialog_pid":
        table[20]["native_pid"] = 999
    elif case == "main_pid":
        table[10]["native_pid"] = 999
    elif case == "metadata_pid":
        raw["pid"] = 999
    elif case == "dead_main":
        table[10]["native_is_window"] = False
    elif case == "dead_dialog":
        table[20]["native_is_window"] = False
    elif case == "child":
        table[20]["native_style"] = 0x40000000
    elif case == "parent_conflict":
        raw["parent"] = table[20]["native_get_parent"] = 999
    elif case == "parent_race":
        table[20]["native_get_parent"] = 10
    elif case == "self":
        raw["handle"] = 10
    result, decisions = adapter.owner_checked_metadata([raw], 42, 10, table.__getitem__)
    assert result == []
    assert decisions[0]["eligible"] is False


def test_native_probe_records_distinct_parent_owner_rootowner_and_pid(monkeypatch):
    gui = SimpleNamespace(
        IsWindow=Mock(return_value=True),
        GetParent=Mock(return_value=0),
        GetAncestor=Mock(side_effect=lambda _hwnd, kind: {1: 7, 3: 10}[kind]),
        GetWindow=Mock(return_value=10),
        GetWindowLong=Mock(return_value=0),
    )
    monkeypatch.setitem(sys.modules, "win32gui", gui)
    monkeypatch.setitem(
        sys.modules,
        "win32con",
        SimpleNamespace(GA_PARENT=1, GA_ROOTOWNER=3, GW_OWNER=4, GWL_STYLE=-16),
    )
    monkeypatch.setitem(
        sys.modules,
        "win32process",
        SimpleNamespace(GetWindowThreadProcessId=Mock(return_value=(9, 42))),
    )
    assert adapter.read_window_identity(20) == {
        "native_is_window": True,
        "native_get_parent": 0,
        "native_actual_parent": 7,
        "native_owner": 10,
        "native_root_owner": 10,
        "native_style": 0,
        "native_pid": 42,
    }
    gui.GetWindow.assert_called_once_with(20, 4)


@pytest.mark.parametrize("case", ["body", "hidden_body", "yes", "no", "disabled", "duplicate"])
def test_exit_content_needs_exact_visible_body_and_unique_enabled_yes_no(case):
    values = controls()
    assert adapter.valid_exit_controls(values)
    if case == "body":
        values[0]["name"] = "Delete the database?"
    elif case == "hidden_body":
        values[0]["visible"] = False
    elif case == "yes":
        values[1]["name"] = "Delete"
    elif case == "no":
        values.pop()
    elif case == "disabled":
        values[1]["enabled"] = False
    elif case == "duplicate":
        values.append(dict(values[1]))
    assert not adapter.valid_exit_controls(values)


def smoke_fixture(rows=None):
    smoke = SimpleNamespace(
        _window_metadata=Mock(return_value=[row()] if rows is None else rows),
        select_exit_modal=original_smoke.select_exit_modal,
        select_startup_summary=original_smoke.select_startup_summary,
        require_hosted_runner=Mock(),
        os=SimpleNamespace(environ={}),
        sys=SimpleNamespace(platform="unit-test"),
        write_json=Mock(),
    )

    def exit_phase(window, processes, _evidence, _activity):
        metadata = smoke._window_metadata(processes)
        selected = smoke.select_exit_modal(metadata, window.process_id(), window.handle)
        if selected is None:
            raise RuntimeError("Normal Exit confirmation was not observed")
        return selected

    def summary_phase(window, processes, _evidence, _fixture, _activity):
        return smoke.select_startup_summary(
            smoke._window_metadata(processes), window.process_id(), window.handle
        )

    smoke._normal_exit = exit_phase
    smoke._acknowledge_startup_summary = summary_phase
    return smoke


def main_window():
    return SimpleNamespace(handle=10, process_id=lambda: 42)


def test_guarded_exit_records_raw_owner_and_normalization_then_restores(tmp_path):
    smoke = smoke_fixture()
    saved = vars(smoke).copy()
    table = identities()
    snapshot = Mock()
    with adapter.install_owner_adapter(
        smoke,
        identity_reader=table.__getitem__,
        control_reader=lambda _hwnd: controls(),
        snapshot=snapshot,
    ):
        selected = smoke._normal_exit(main_window(), [], tmp_path, Mock())
        assert selected["handle"] == 20
        assert selected["parent"] == 10
        with pytest.raises(RuntimeError, match="guarded"):
            smoke.select_exit_modal([row()], 42, 10)
    snapshot.assert_not_called()
    report = smoke.write_json.call_args.args[1]
    assert report["windows_changed"] is False
    assert report["records"][0]["raw_metadata"][0]["parent"] == 0
    assert report["records"][0]["raw_metadata"][0]["native_owner"] == 10
    assert report["records"][0]["exit_body_and_yes_no_verified"] is True
    for name in (
        "_normal_exit",
        "_window_metadata",
        "select_exit_modal",
        "select_startup_summary",
        "_acknowledge_startup_summary",
    ):
        assert getattr(smoke, name) is saved[name]


@pytest.mark.parametrize("invalid", ["unowned", "content", "probe", "io"])
def test_original_exit_failure_remains_and_pixels_are_requested_before_reraise(tmp_path, invalid):
    smoke = smoke_fixture()
    table = identities()
    if invalid in {"unowned", "io"}:
        table[20]["native_owner"] = 0
    if invalid == "probe":
        del table[20]
    snapshot = Mock(return_value={"desktop_png": "actual.png"})
    if invalid == "io":
        snapshot.side_effect = OSError("capture unavailable")
        smoke.write_json.side_effect = OSError("disk unavailable")
    with (
        adapter.install_owner_adapter(
            smoke,
            identity_reader=table.__getitem__,
            control_reader=lambda _hwnd: [] if invalid == "content" else controls(),
            snapshot=snapshot,
        ),
        pytest.raises(RuntimeError, match="Normal Exit confirmation was not observed"),
    ):
        smoke._normal_exit(main_window(), [], tmp_path, Mock())
    snapshot.assert_called_once()
    assert snapshot.call_args.args[-1] == "exit-owner-failure"


def test_hosted_guard_precedes_native_probe_uia_and_original_phase(tmp_path):
    smoke = smoke_fixture()
    phase = Mock()
    smoke._normal_exit = phase
    smoke.require_hosted_runner.side_effect = RuntimeError("hosted only")
    probe, ui, snapshot = Mock(), Mock(), Mock()
    with (
        adapter.install_owner_adapter(
            smoke, identity_reader=probe, control_reader=ui, snapshot=snapshot
        ),
        pytest.raises(RuntimeError, match="hosted only"),
    ):
        smoke._normal_exit(main_window(), [], tmp_path, Mock())
    for operation in (phase, probe, ui, snapshot):
        operation.assert_not_called()


@pytest.mark.parametrize(
    "changes", [{}, {"class_name": "Qt999QWindow"}, {"title": "Other"}, {"visible": False}]
)
def test_owner_adapter_preserves_summary_exact_class_title_visibility_and_confirm(
    tmp_path, changes
):
    value = {**row(title="Today's Events & Due Tasks", class_name="Qt6102QWindow"), **changes}
    smoke = smoke_fixture([value])
    confirm = Mock()
    smoke.briefing_confirm = confirm
    ui = Mock()
    with adapter.install_owner_adapter(
        smoke, identity_reader=identities().__getitem__, control_reader=ui, snapshot=Mock()
    ):
        selected = smoke._acknowledge_startup_summary(main_window(), [], tmp_path, True, Mock())
        assert (selected is not None) is (not changes)
        assert smoke.briefing_confirm is confirm
    ui.assert_not_called()


def test_original_selector_ambiguity_is_not_suppressed_and_context_restores(tmp_path):
    smoke = smoke_fixture([row(), row(handle=21)])
    table = identities()
    table[21] = dict(table[20])
    original = smoke.select_exit_modal
    with (
        pytest.raises(RuntimeError, match="More than one"),
        adapter.install_owner_adapter(
            smoke, identity_reader=table.__getitem__, control_reader=Mock(), snapshot=Mock()
        ),
    ):
        smoke._normal_exit(main_window(), [], tmp_path, Mock())
    assert smoke.select_exit_modal is original


def test_real_original_exit_flow_still_observes_and_clicks_only_verified_yes(tmp_path, monkeypatch):
    body, yes, no = Mock(), Mock(), Mock()
    for widget, value in zip((body, yes, no), controls(), strict=True):
        widget.window_text.return_value = value["name"]
        widget.element_info.control_type = value["control_type"]
        widget.is_visible.return_value = True
        widget.is_enabled.return_value = True
    dialog = Mock()
    dialog.descendants.return_value = [body, yes, no]
    exit_item = Mock()
    exit_item.window_text.return_value = "Exit"
    menu = Mock()
    menu.process_id.return_value = 42
    menu.descendants.return_value = [exit_item]
    desktop = Mock()
    desktop.windows.return_value = [menu]
    desktop.window.return_value.wrapper_object.return_value = dialog
    monkeypatch.setitem(sys.modules, "pywinauto", SimpleNamespace(Desktop=lambda **_kw: desktop))
    monkeypatch.setattr(original_smoke, "require_hosted_runner", Mock())
    monkeypatch.setattr(original_smoke, "system_button", lambda _window: Mock())
    monkeypatch.setattr(original_smoke, "_window_metadata", lambda _processes: [row()])
    capture = Mock(return_value={})
    monkeypatch.setattr(original_smoke, "_capture", capture)
    monkeypatch.setattr(original_smoke, "write_json", Mock())
    monkeypatch.setattr(original_smoke.time, "sleep", lambda _seconds: None)
    phases = []
    with adapter.install_owner_adapter(
        original_smoke, identity_reader=identities().__getitem__, snapshot=Mock()
    ):
        original_smoke._normal_exit(
            main_window(), [SimpleNamespace(pid=42)], tmp_path, phases.append
        )
    yes.click_input.assert_called_once_with()
    no.click_input.assert_not_called()
    assert phases[-2:] == ["exit_confirmation_observed", "exit_yes_clicked"]
    assert capture.call_args.args[1].name == "normal-exit-confirmation.png"
