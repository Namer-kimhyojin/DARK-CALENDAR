# -*- coding: utf-8 -*-
"""Read actual Win32 owners without changing product HWNDs or the native gate.

GetParent may return NULL for an owned top-level window without WS_POPUP.
Microsoft directs owner queries to GetWindow(GW_OWNER):
https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getparent
https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindow
"""

from __future__ import annotations

from contextlib import contextmanager, suppress
from contextvars import ContextVar

_WS_CHILD = 0x40000000
_EXIT_BODIES = frozenset(
    {
        "Air Calendar is closing. The program will fully exit without minimizing to tray. Continue?",
        "Air Calendar를 종료합니다. 트레이로 전환되지 않고 프로그램이 완전히 종료됩니다. 계속하시겠습니까?",
    }
)


def read_window_identity(handle):
    import win32con
    import win32gui
    import win32process

    exists = bool(win32gui.IsWindow(handle))
    result = {"native_is_window": exists}
    if exists:
        result.update(
            native_get_parent=win32gui.GetParent(handle),
            native_actual_parent=win32gui.GetAncestor(handle, win32con.GA_PARENT),
            native_owner=win32gui.GetWindow(handle, win32con.GW_OWNER),
            native_root_owner=win32gui.GetAncestor(handle, win32con.GA_ROOTOWNER),
            native_style=win32gui.GetWindowLong(handle, win32con.GWL_STYLE),
            native_pid=win32process.GetWindowThreadProcessId(handle)[1],
        )
    return result


def _identity(reader, handle):
    try:
        return reader(handle)
    except Exception as error:
        return {"native_is_window": False, "native_identity_error": str(error)}


def owner_checked_metadata(metadata, pid, main_handle, identity_reader=read_window_identity):
    """Keep only provably owned dialogs; never infer ownership from PID/title."""
    main = _identity(identity_reader, main_handle)
    eligible, decisions = [], []
    for original in metadata:
        item = dict(original)
        identity = _identity(identity_reader, item["handle"])
        checks = {
            "distinct_main_and_dialog": item["handle"] != main_handle,
            "both_hwnds_exist": main.get("native_is_window") is True
            and identity.get("native_is_window") is True,
            "both_native_pids_match": main.get("native_pid") == pid
            and identity.get("native_pid") == pid
            and item["pid"] == pid,
            "exact_native_owner": identity.get("native_owner") == main_handle,
            "not_child_window": isinstance(identity.get("native_style"), int)
            and not identity["native_style"] & _WS_CHILD,
            "compatible_raw_parent": item["parent"] in (0, main_handle),
            "parent_snapshot_still_current": identity.get("native_get_parent") == item["parent"],
        }
        allowed = all(checks.values())
        decision = {
            "handle": item["handle"],
            "raw_parent": item["parent"],
            "identity": identity,
            "main_identity": main,
            "checks": checks,
            "eligible": allowed,
            "normalization": "none",
        }
        if allowed:
            item.update(identity)
            if item["parent"] == 0:
                item["parent"] = main_handle
                decision["normalization"] = (
                    "GetParent NULL; exact GW_OWNER supplies selector parent"
                )
            eligible.append(item)
        decisions.append(decision)
    return eligible, decisions


def read_exit_controls(handle):
    from pywinauto import Desktop

    dialog = Desktop(backend="uia").window(handle=handle).wrapper_object()
    return [
        {
            "name": item.window_text(),
            "control_type": item.element_info.control_type,
            "visible": bool(item.is_visible()),
            "enabled": bool(item.is_enabled()),
        }
        for item in dialog.descendants()
    ]


def valid_exit_controls(controls):
    body = any(
        item.get("visible") is True and " ".join(item.get("name", "").split()) in _EXIT_BODIES
        for item in controls
    )
    buttons = [
        item["name"].replace("&", "").strip()
        for item in controls
        if item.get("control_type") == "Button"
        and item.get("visible") is True
        and item.get("enabled") is True
    ]
    return (
        body
        and sum(name in {"Yes", "예", "예(Y)"} for name in buttons) == 1
        and sum(name in {"No", "아니요", "아니요(N)"} for name in buttons) == 1
    )


def _failure_snapshot(smoke, window, evidence, stage):
    from native_capture_diagnostics import capture_snapshot

    return capture_snapshot(smoke, window, evidence, [], stage)


@contextmanager
def install_owner_adapter(
    smoke,
    *,
    identity_reader=read_window_identity,
    control_reader=read_exit_controls,
    snapshot=_failure_snapshot,
):
    """Preserve selectors/actions and restore all observers after this QA run."""
    names = (
        "_window_metadata",
        "select_exit_modal",
        "select_startup_summary",
        "_normal_exit",
        "_acknowledge_startup_summary",
    )
    original = {name: getattr(smoke, name) for name in names}
    current = ContextVar("native_modal_owner_observation", default=None)

    def metadata(processes):
        values = original["_window_metadata"](processes)
        if current.get() is None:
            return values
        return [{**item, **_identity(identity_reader, item["handle"])} for item in values]

    def select(kind, values, pid, main_handle):
        scope = current.get()
        if scope is None:
            raise RuntimeError("Owner-aware selection requires a guarded native modal phase")
        normalized, decisions = owner_checked_metadata(values, pid, main_handle, identity_reader)
        record = {"kind": kind, "raw_metadata": values, "ownership": decisions}
        scope["records"].append(record)
        selected = original["select_exit_modal" if kind == "exit" else "select_startup_summary"](
            normalized, pid, main_handle
        )
        record["selected"] = selected
        if selected is not None and kind == "exit":
            try:
                controls = control_reader(selected["handle"])
                record["exit_controls"] = controls
                record["exit_body_and_yes_no_verified"] = valid_exit_controls(controls)
            except Exception as error:
                record["exit_controls_error"] = str(error)
                return None
            if not record["exit_body_and_yes_no_verified"]:
                return None
        return selected

    def phase(name, function, window, processes, evidence, *args):
        smoke.require_hosted_runner(smoke.os.environ, smoke.sys.platform, evidence)
        scope = {"phase": name, "windows_changed": False, "records": []}
        token = current.set(scope)
        try:
            return function(window, processes, evidence, *args)
        except BaseException:
            with suppress(Exception):
                value = snapshot(smoke, window, evidence, f"{name}-owner-failure")
                smoke.write_json(evidence / f"{name}-owner-failure.json", value)
            raise
        finally:
            with suppress(Exception):
                smoke.write_json(evidence / f"{name}-owner-observation.json", scope)
            current.reset(token)

    smoke._window_metadata = metadata
    smoke.select_exit_modal = lambda values, pid, handle: select("exit", values, pid, handle)
    smoke.select_startup_summary = lambda values, pid, handle: select(
        "summary", values, pid, handle
    )
    smoke._normal_exit = lambda window, processes, evidence, activity: phase(
        "exit", original["_normal_exit"], window, processes, evidence, activity
    )
    smoke._acknowledge_startup_summary = lambda window, processes, evidence, fixture, activity: (
        phase(
            "summary",
            original["_acknowledge_startup_summary"],
            window,
            processes,
            evidence,
            fixture,
            activity,
        )
    )
    try:
        yield smoke
    finally:
        for name, function in original.items():
            setattr(smoke, name, function)
