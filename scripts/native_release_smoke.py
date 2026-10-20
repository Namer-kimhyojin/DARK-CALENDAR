# -*- coding: utf-8 -*-
"""Run unchanged frozen EXEs only on disposable GitHub-hosted Windows desktops.

Microsoft documents graphical UI tests on windows-latest:
https://learn.microsoft.com/en-us/windows/apps/develop/ai-assisted/testing#run-tests-in-ci
The screenshots still require release-reviewer inspection; this is not Store
package-identity validation and never declares a release complete.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

try:
    from scripts.native_exception_observer import ExceptionObserver, classify_rpc
    from scripts.verify_sqlite_runtime import verify_payload
except ModuleNotFoundError:
    from native_exception_observer import ExceptionObserver, classify_rpc
    from verify_sqlite_runtime import verify_payload

SETTINGS_KEY = r"Software\kimhyojin\Dark Calendar"
FIXTURE_NAME = "Native release synthetic persistence fixture"
FIXTURE_CALENDAR = "native-release-fixture"
BASELINE_EXE_SHA256 = "1363e829f3c71e4e38222497076237c84fff5875d056ca6f50a7f6067e5100d5"
ERROR_PATTERN = re.compile(
    r"Unhandled exception|Traceback \(most recent call last\)|Database startup aborted|"
    r"database disk image is malformed|Database initialization failed|"
    r"Windows fatal exception|Fatal Python error|\[(?:ERROR|CRITICAL)\]",
    re.IGNORECASE,
)
KNOWN_RPC = re.compile(r"^Windows fatal exception: code 0x8001010d\r?$", re.MULTILINE)
PAGING_NOTICE = (
    "Windows created a temporary paging file on your computer because of a problem that "
    "occurred with your paging file configuration when you started your computer. The total "
    "paging file size for all disk drives may be somewhat larger than the size you specified."
)


def check_runtime_log(text: str, *, observed_rpc: dict | None = None, pending=False) -> int:
    count = len(KNOWN_RPC.findall(text))
    # The original text is always retained. Only this exact diagnostic can stay
    # pending while a real Windows debugger records first/second-chance dispatch.
    if (
        count
        and not pending
        and (
            observed_rpc is None
            or observed_rpc.get("classification") != "handled_first_chance"
            or observed_rpc.get("rpc_event_count") != count
        )
    ):
        raise RuntimeError("Unclassified native RPC/fatal error diagnostic")
    checked = KNOWN_RPC.sub("", text) if pending or observed_rpc else text
    if ERROR_PATTERN.search(checked):
        raise RuntimeError("Fresh application log contains an error or traceback")
    return count


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", errors="strict")


def require_hosted_runner(environment, platform: str, evidence: Path) -> Path:
    """Refuse local runs before importing UI packages or touching app state."""
    required = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_OS": "Windows",
    }
    if platform != "win32" or any(environment.get(k) != v for k, v in required.items()):
        raise RuntimeError("Native smoke may run only on disposable GitHub-hosted Windows VMs")
    temporary = Path(environment.get("RUNNER_TEMP", "")).resolve()
    if not environment.get("RUNNER_TEMP") or evidence.resolve() == temporary:
        raise RuntimeError("Evidence must have its own directory below RUNNER_TEMP")
    if not evidence.resolve().is_relative_to(temporary):
        raise RuntimeError("Evidence must stay below RUNNER_TEMP")
    return temporary


def require_fresh_state(settings_exists: bool, shared_exists: bool, running: list) -> None:
    if settings_exists or shared_exists or running:
        raise RuntimeError("Runner already has Air Calendar state/processes; refusing to reset it")


def validate_capture(image) -> dict:
    """Reject unavailable, blank, black, and implausibly small GUI captures."""
    if image.width < 500 or image.height < 300:
        raise RuntimeError(f"Main-window capture is too small: {image.size}")
    rgb = image.convert("RGB")
    extrema = rgb.getextrema()
    histogram = rgb.histogram()
    deviations = []
    for channel in range(3):
        values = histogram[channel * 256 : (channel + 1) * 256]
        count = sum(values)
        mean = sum(index * frequency for index, frequency in enumerate(values)) / count
        variance = (
            sum((index - mean) ** 2 * frequency for index, frequency in enumerate(values)) / count
        )
        deviations.append(math.sqrt(variance))
    if max(high for _low, high in extrema) < 25:
        raise RuntimeError("Main-window capture is black")
    if max(high - low for low, high in extrema) < 30 or max(deviations) < 3:
        raise RuntimeError("Main-window capture is blank or unavailable")
    return {"width": image.width, "height": image.height, "stddev": deviations}


def validate_launch_log(
    text: str, version: str, database: Path, sqlite_version: str, *, observed_rpc=None
) -> None:
    check_runtime_log(text, observed_rpc=observed_rpc)
    marker = re.search(
        r"Database startup: pid=(\d+) app_version=(\S+) sqlite=(\S+) db=([^\r\n]+)", text
    )
    if not marker:
        raise RuntimeError("Missing fresh native database startup marker")
    if marker.group(2) != version or marker.group(3) != sqlite_version:
        raise RuntimeError("Native startup version/SQLite differs from the final payload")
    if os.path.normcase(marker.group(4)) != os.path.normcase(str(database)):
        raise RuntimeError("Native startup opened the wrong database profile")


class NativeSQLite:
    """Small C API client: checks use the verified payload DLL, never host sqlite3."""

    def __init__(self, library: Path):
        self.library = ctypes.CDLL(str(library.resolve()))
        signatures = {
            "sqlite3_open_v2": (
                [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_int, ctypes.c_char_p],
                ctypes.c_int,
            ),
            "sqlite3_close": ([ctypes.c_void_p], ctypes.c_int),
            "sqlite3_errmsg": ([ctypes.c_void_p], ctypes.c_char_p),
            "sqlite3_prepare_v2": (
                [
                    ctypes.c_void_p,
                    ctypes.c_char_p,
                    ctypes.c_int,
                    ctypes.POINTER(ctypes.c_void_p),
                    ctypes.c_void_p,
                ],
                ctypes.c_int,
            ),
            "sqlite3_step": ([ctypes.c_void_p], ctypes.c_int),
            "sqlite3_column_count": ([ctypes.c_void_p], ctypes.c_int),
            "sqlite3_column_text": ([ctypes.c_void_p, ctypes.c_int], ctypes.c_char_p),
            "sqlite3_finalize": ([ctypes.c_void_p], ctypes.c_int),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.library, name)
            function.argtypes, function.restype = arguments, result

    def query(self, database: Path, sql: str, *, writable: bool = False) -> list[list]:
        connection = ctypes.c_void_p()
        status = self.library.sqlite3_open_v2(
            str(database).encode("utf-8", errors="strict"),
            ctypes.byref(connection),
            2 if writable else 1,
            None,
        )
        statement = ctypes.c_void_p()
        try:
            if status:
                raise RuntimeError("Cannot open the isolated synthetic database")
            if self.library.sqlite3_prepare_v2(
                connection,
                sql.encode("utf-8", errors="strict"),
                -1,
                ctypes.byref(statement),
                None,
            ):
                raise RuntimeError(
                    self.library.sqlite3_errmsg(connection).decode("utf-8", errors="replace")
                )
            rows = []
            while True:
                status = self.library.sqlite3_step(statement)
                if status == 101:
                    return rows
                if status != 100:
                    raise RuntimeError(
                        self.library.sqlite3_errmsg(connection).decode("utf-8", errors="replace")
                    )
                row = []
                for index in range(self.library.sqlite3_column_count(statement)):
                    value = self.library.sqlite3_column_text(statement, index)
                    row.append(None if value is None else value.decode("utf-8", errors="replace"))
                rows.append(row)
        finally:
            if statement:
                self.library.sqlite3_finalize(statement)
            if connection:
                self.library.sqlite3_close(connection)


def inspect_database(engine: NativeSQLite, database: Path, fixture: bool) -> dict:
    if engine.query(database, "PRAGMA integrity_check") != [["ok"]]:
        raise RuntimeError("Synthetic profile failed SQLite integrity_check")
    if engine.query(database, "PRAGMA foreign_key_check"):
        raise RuntimeError("Synthetic profile has foreign-key violations")
    if fixture:
        rows = engine.query(database, f"SELECT name FROM unified_task WHERE name='{FIXTURE_NAME}'")
        if rows != [[FIXTURE_NAME]]:
            raise RuntimeError("Synthetic upgrade task was lost or duplicated")
        calendars = engine.query(
            database, f"SELECT name FROM calendar WHERE id='{FIXTURE_CALENDAR}'"
        )
        if calendars != [["Native synthetic calendar"]]:
            raise RuntimeError("Synthetic upgrade calendar was lost or modified")
    return {"integrity_check": "ok", "foreign_key_violations": 0, "fixture_preserved": fixture}


def seed_fixture(engine: NativeSQLite, database: Path) -> None:
    engine.query(
        database,
        f"INSERT INTO calendar(id,type,name,is_active,is_visible) VALUES('{FIXTURE_CALENDAR}','local','Native synthetic calendar',1,1)",
        writable=True,
    )
    columns = {row[1] for row in engine.query(database, "PRAGMA table_info(unified_task)")}
    names, values = (
        ["name", "type", "deadline", "end_date", "all_day"],
        [
            f"'{FIXTURE_NAME}'",
            "'schedule'",
            "date('now','localtime')",
            "date('now','localtime')",
            "1",
        ],
    )
    if "calendar_id" in columns:
        names.append("calendar_id")
        values.append(f"'{FIXTURE_CALENDAR}'")
    engine.query(
        database,
        f"INSERT INTO unified_task({','.join(names)}) VALUES({','.join(values)})",
        writable=True,
    )


def _desktop_preflight() -> dict:
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.OpenInputDesktop.argtypes = [ctypes.c_uint, ctypes.c_bool, ctypes.c_uint]
    user.OpenInputDesktop.restype = ctypes.c_void_p
    user.CloseDesktop.argtypes = [ctypes.c_void_p]
    desktop = user.OpenInputDesktop(0, False, 0x0001)
    if not desktop:
        raise RuntimeError("Runner has no readable interactive input desktop")
    user.CloseDesktop(desktop)
    width, height = user.GetSystemMetrics(0), user.GetSystemMetrics(1)
    if width < 800 or height < 600:
        raise RuntimeError("Runner has no usable graphical display")
    session = ctypes.c_uint()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    if not kernel.ProcessIdToSessionId(os.getpid(), ctypes.byref(session)) or session.value == 0:
        raise RuntimeError("Runner is in noninteractive session zero")
    return {"session_id": session.value, "width": width, "height": height}


def _settings_exists() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SETTINGS_KEY):
            return True
    except FileNotFoundError:
        return False


def _prepare_settings(*, clear_owned: bool = False) -> None:
    import winreg

    def delete_owned(key):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_ALL_ACCESS) as handle:
            while True:
                try:
                    child = winreg.EnumKey(handle, 0)
                except OSError:
                    break
                delete_owned(key + "\\" + child)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)

    if clear_owned:
        delete_owned(SETTINGS_KEY)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, SETTINGS_KEY) as handle:
        winreg.SetValueEx(handle, "language", 0, winreg.REG_SZ, "en")


def _related_processes(executable: Path, started: float) -> list:
    import psutil

    found = []
    for process in psutil.process_iter(["pid", "exe", "create_time", "name"]):
        try:
            if (
                process.info.get("create_time") is not None
                and process.info["create_time"] >= started - 1
                and process.info["exe"]
                and Path(process.info["exe"]).resolve() == executable.resolve()
            ):
                found.append(process)
        except (psutil.Error, OSError):
            continue
    return found


def _window_metadata(processes) -> list[dict]:
    import win32gui
    import win32process

    pids = {process.pid for process in processes}
    windows = {}
    user = ctypes.WinDLL("user32", use_last_error=True)
    dpi_for_window = getattr(user, "GetDpiForWindow", None)
    if dpi_for_window is not None:
        dpi_for_window.argtypes = [wintypes.HWND]
        dpi_for_window.restype = wintypes.UINT

    def collect(handle, _context):
        if win32process.GetWindowThreadProcessId(handle)[1] in pids:
            title = win32gui.GetWindowText(handle)
            windows[handle] = {
                "handle": handle,
                "pid": win32process.GetWindowThreadProcessId(handle)[1],
                "title": title,
                "class_name": win32gui.GetClassName(handle),
                "visible": bool(win32gui.IsWindowVisible(handle)),
                "parent": win32gui.GetParent(handle),
                "rectangle": list(win32gui.GetWindowRect(handle)),
                "extended_style": win32gui.GetWindowLong(handle, -20),
                "dpi": int(dpi_for_window(handle) or 96) if dpi_for_window else 96,
            }

    def top(handle, _context):
        collect(handle, None)
        win32gui.EnumChildWindows(handle, collect, None)

    win32gui.EnumWindows(top, None)
    return list(windows.values())


def runtime_ready(text: str) -> bool:
    return all(
        marker in text
        for marker in (
            "Unified database initialized successfully.",
            "System tray and unified shortcuts initialized.",
            "Idle detector (AlarmWorker) initialized and started.",
        )
    )


def splash_visible(windows: list[dict]) -> bool:
    for window in windows:
        left, top, right, bottom = window["rectangle"]
        scale = window["dpi"] / 96
        if (
            window["visible"]
            and window["extended_style"] & 0x88 == 0x88
            and abs(right - left - round(560 * scale)) <= 2
            and abs(bottom - top - round(340 * scale)) <= 2
        ):
            return True
    return False


def system_button(window):
    buttons = [
        item
        for item in window.descendants(control_type="Button")
        if item.window_text().strip() in {"System", "Settings", "시스템"} and item.is_visible()
    ]
    return buttons[0] if len(buttons) == 1 else None


def select_qualified_main(windows, is_child):
    qualified = [
        window
        for window in windows
        if len(window.descendants()) >= 20 and system_button(window) is not None
    ]
    roots = [
        window
        for window in qualified
        if not any(
            other is not window and is_child(other.handle, window.handle) for other in qualified
        )
    ]
    if len(roots) > 1:
        raise RuntimeError("More than one independent qualified main window exists")
    return roots[0] if roots else None


def _main_window(processes, evidence: Path, *, ready: bool, before_uia=None):
    import win32gui

    metadata = _window_metadata(processes)
    observation = {
        "runtime_ready_log": ready,
        "windows": metadata,
        "splash_visible": splash_visible(metadata),
    }
    write_json(evidence / "window-observation.json", observation)
    for window in metadata:
        if ERROR_PATTERN.search(window["title"]) or "cannot start" in window["title"].lower():
            raise RuntimeError(f"Native error window: {window['title']}")
    # Do not ask Qt's UIA provider about a window while splash processEvents()
    # is still running; synchronous provider calls can reenter startup COM work.
    if not ready or observation["splash_visible"]:
        return None
    if before_uia is not None:
        before_uia()
    from pywinauto import Desktop

    desktop = Desktop(backend="uia")
    candidates = [
        desktop.window(handle=item["handle"]).wrapper_object()
        for item in metadata
        if item["visible"] and item["title"] == "Air Calendar"
    ]
    return select_qualified_main(candidates, win32gui.IsChild)


class _LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _InputPayload(ctypes.Union):
    _fields_ = [("mi", _MouseInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("payload", _InputPayload)]


def _idle_ms(user, kernel) -> int:
    last = _LastInputInfo(cbSize=ctypes.sizeof(_LastInputInfo))
    user.GetLastInputInfo.argtypes = [ctypes.POINTER(_LastInputInfo)]
    user.GetLastInputInfo.restype = wintypes.BOOL
    kernel.GetTickCount64.restype = ctypes.c_ulonglong
    if not user.GetLastInputInfo(ctypes.byref(last)):
        raise ctypes.WinError(ctypes.get_last_error())
    return (kernel.GetTickCount64() - last.dwTime) & 0xFFFFFFFF


def _reset_runner_idle(evidence: Path) -> dict:
    require_hosted_runner(os.environ, sys.platform, evidence)
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    before = _idle_ms(user, kernel)
    movement = _Input(type=0, payload=_InputPayload(mi=_MouseInput(dx=1, dwFlags=1)))
    user.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_Input), ctypes.c_int]
    user.SendInput.restype = wintypes.UINT
    if user.SendInput(1, ctypes.byref(movement), ctypes.sizeof(movement)) != 1:
        raise RuntimeError("Disposable runner could not receive a real mouse input event")
    time.sleep(0.1)
    after = _idle_ms(user, kernel)
    result = {"before_idle_ms": before, "after_idle_ms": after, "real_mouse_input_events": 1}
    write_json(evidence / "runner-input.json", result)
    if after > 2000:
        raise RuntimeError("Runner last-input time did not update after real mouse input")
    return result


def validate_window_bounds(
    window, button, width: int, height: int, *, evidence: Path | None = None
) -> dict:
    def rectangle(item):
        rect = item.rectangle()
        return [rect.left, rect.top, rect.right, rect.bottom]

    result = {
        "display": [0, 0, width, height],
        "window": rectangle(window),
        "system_button": rectangle(button),
    }
    if evidence is not None:
        write_json(evidence / "window-bounds.json", result)
    for name in ("window", "system_button"):
        left, top, right, bottom = result[name]
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise RuntimeError(f"Native {name} is outside the visible display: {result}")
    wl, wt, wr, wb = result["window"]
    bl, bt, br, bb = result["system_button"]
    if not (wl <= bl < br <= wr and wt <= bt < bb <= wb):
        raise RuntimeError("System button is outside the native main window")
    return result


def _capture(window, destination: Path, *, main: bool = True, verify_visible=None) -> dict:
    # Window-bound capture and UIA ownership are both recorded; the reviewer sees
    # the actual rendered image, not a source-rendered substitute.
    if main and verify_visible is not None:
        verify_visible("before")
    image = window.capture_as_image()
    if main and verify_visible is not None:
        verify_visible("after")
    statistics = validate_capture(image) if main else {"width": image.width, "height": image.height}
    image.save(destination, format="PNG")
    return {
        **statistics,
        "path": destination.name,
        "sha256": sha256(destination),
        "window_handle": window.handle,
        "process_id": window.process_id(),
    }


def select_exit_modal(metadata: list[dict], pid: int, main_handle: int) -> dict | None:
    dialogs = [
        item
        for item in metadata
        if item["visible"]
        and item["pid"] == pid
        and item["parent"] == main_handle
        and item["title"] in {"Exit", "Exit Confirmation", "종료 안내", "Exit Notice"}
    ]
    if len(dialogs) > 1:
        raise RuntimeError("More than one owned Exit confirmation exists")
    return dialogs[0] if dialogs else None


def select_startup_summary(metadata: list[dict], pid: int, main_handle: int) -> dict | None:
    dialogs = [
        item
        for item in metadata
        if item["visible"]
        and item["pid"] == pid
        and item["parent"] == main_handle
        and item["title"] == "Today's Events & Due Tasks"
        and item["class_name"] == "Qt6102QWindow"
    ]
    if len(dialogs) > 1:
        raise RuntimeError("More than one owned startup daily briefing exists")
    return dialogs[0] if dialogs else None


def briefing_confirm(dialog, controls: list[dict]):
    names = [dialog.window_text(), *(item["name"] for item in controls)]
    if "Today's Briefing" not in names or not any(FIXTURE_NAME in name for name in names):
        raise RuntimeError("Startup briefing lacks its expected title and synthetic schedule")
    buttons = [
        item
        for item in dialog.descendants(control_type="Button")
        if item.window_text().replace("&", "").strip() == "Confirm"
        and item.is_visible()
        and item.is_enabled()
        and item.element_info.automation_id.split(".")[-1] == "primary_btn"
    ]
    if len(buttons) != 1:
        raise RuntimeError("Cannot identify the briefing's unique visible primary Confirm button")
    return buttons[0]


def _acknowledge_startup_summary(window, processes, evidence: Path, fixture: bool, activity):
    require_hosted_runner(os.environ, sys.platform, evidence)
    import win32gui

    metadata = _window_metadata(processes)
    write_json(evidence / "startup-window-observation.json", metadata)
    modal = select_startup_summary(metadata, window.process_id(), window.handle)
    if modal is None:
        return {"seen": False, "settings_changed_by_harness": False}
    if not fixture:
        raise RuntimeError("Unexpected daily briefing in the empty fresh profile")
    from pywinauto import Desktop

    dialog = Desktop(backend="uia").window(handle=modal["handle"]).wrapper_object()
    controls = _controls(dialog)
    write_json(evidence / "startup-briefing-accessibility.json", controls)
    button = briefing_confirm(dialog, controls)
    confirmation_id = button.element_info.automation_id
    rect = button.rectangle()
    point = (round((rect.left + rect.right) / 2), round((rect.top + rect.bottom) / 2))
    if win32gui.GetAncestor(win32gui.WindowFromPoint(point), 2) != modal["handle"]:
        raise RuntimeError("Startup briefing Confirm button is obscured")
    capture = _capture(dialog, evidence / "startup-briefing.png", main=False)
    activity("startup_briefing_fixture_observed")
    button.click_input()
    deadline = time.monotonic() + 5
    while (
        win32gui.IsWindow(modal["handle"])
        and win32gui.IsWindowVisible(modal["handle"])
        and time.monotonic() < deadline
    ):
        time.sleep(0.1)
    handle_exists = bool(win32gui.IsWindow(modal["handle"]))
    still_visible = handle_exists and bool(win32gui.IsWindowVisible(modal["handle"]))
    if still_visible:
        raise RuntimeError("Startup briefing did not close after normal Confirm")
    main_system = system_button(window)
    if main_system is None or not main_system.is_enabled():
        raise RuntimeError("Main window did not regain enabled controls after briefing Confirm")
    activity("startup_briefing_confirmed")
    result = {
        "seen": True,
        "modal": modal,
        "capture": capture,
        "button": "Confirm / primary_btn",
        "button_automation_id": confirmation_id,
        "hwnd_exists_after_confirm": handle_exists,
        "visible_after_confirm": still_visible,
        "main_controls_enabled": True,
        "synthetic_schedule_visible": True,
        "normal_ui_acknowledgement": True,
        "settings_changed_by_harness": False,
        "automatic_display_disabled": False,
    }
    write_json(evidence / "startup-briefing-acknowledged.json", result)
    return result


def validate_main_content(controls: list[dict], fixture: bool) -> dict:
    names = [item["name"].strip() for item in controls]
    cells = sum(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2} date cell", name)) for name in names)
    if "Main Calendar" not in names or "Today's Schedule" not in names or cells < 28:
        raise RuntimeError("Main screen lacks the actual calendar/task panels and date cells")
    if fixture and not any(FIXTURE_NAME in name for name in names):
        raise RuntimeError("Synthetic persisted schedule is absent from the actual main UI")
    if not fixture and "No schedules posted for today." not in names:
        raise RuntimeError("Fresh profile does not show the expected empty schedule state")
    return {"date_cells": cells, "fixture_visible": fixture, "calendar_and_task_panels": True}


def select_paging_notice(metadata: dict, application_pid: int) -> int | None:
    """Acknowledge only this exact OS information box, never app/error/settings UI."""
    executable = Path(metadata["executable"])
    windows = Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
    trusted = executable.parent in {windows / "System32", windows / "SysWOW64"}
    if (
        metadata["pid"] == application_pid
        or metadata["title"] != "System Properties"
        or metadata["class_name"] != "#32770"
        or not trusted
        or executable.name.lower()
        not in {"rundll32.exe", "systempropertiesadvanced.exe", "systempropertiesperformance.exe"}
    ):
        return None
    messages = [
        " ".join(item["text"].split())
        for item in metadata["children"]
        if item["class_name"].lower() == "static"
    ]
    if PAGING_NOTICE not in messages:
        return None
    buttons = [
        item["handle"]
        for item in metadata["children"]
        if item["class_name"].lower() == "button"
        and (
            item["control_id"] == 1
            or (
                executable.name.lower() == "systempropertiesperformance.exe"
                and item["control_id"] == 2
            )
        )
        and item["text"].replace("&", "").strip() == "OK"
    ]
    return buttons[0] if len(buttons) == 1 else None


def _dismiss_paging_notice(window, evidence: Path) -> None:
    require_hosted_runner(os.environ, sys.platform, evidence)
    import psutil
    import win32gui
    import win32process

    notices, observations = [], []

    def inspect(handle, _context):
        if (
            not win32gui.IsWindowVisible(handle)
            or win32gui.GetWindowText(handle) != "System Properties"
            or win32gui.GetClassName(handle) != "#32770"
        ):
            return
        pid = win32process.GetWindowThreadProcessId(handle)[1]
        children = []

        def child(child_handle, _unused):
            children.append(
                {
                    "handle": child_handle,
                    "class_name": win32gui.GetClassName(child_handle),
                    "text": win32gui.GetWindowText(child_handle),
                    "control_id": win32gui.GetDlgCtrlID(child_handle),
                }
            )

        win32gui.EnumChildWindows(handle, child, None)
        metadata = {
            "handle": handle,
            "pid": pid,
            "title": win32gui.GetWindowText(handle),
            "class_name": win32gui.GetClassName(handle),
            "executable": psutil.Process(pid).exe(),
            "children": children,
        }
        button = select_paging_notice(metadata, window.process_id())
        observations.append({**metadata, "recognized_paging_notice": button is not None})
        if button is not None:
            notices.append((metadata, button))

    win32gui.EnumWindows(inspect, None)
    if observations:
        write_json(evidence / "runner-system-properties-observation.json", observations)
    if len(notices) > 1:
        raise RuntimeError("More than one exact OS paging information notice exists")
    for metadata, button in notices:
        from pywinauto import Desktop

        write_json(evidence / "runner-paging-notice.json", metadata)
        control = Desktop(backend="win32").window(handle=button).wrapper_object()
        control.click_input()
        deadline = time.monotonic() + 3
        while win32gui.IsWindow(metadata["handle"]) and time.monotonic() < deadline:
            time.sleep(0.1)
        if win32gui.IsWindow(metadata["handle"]):
            raise RuntimeError("Exact OS paging information notice did not close after OK")
        write_json(
            evidence / "runner-paging-notice-acknowledged.json",
            {"handle": metadata["handle"], "ok_clicked": True, "settings_changed": False},
        )


def capture_points(rectangle, controls: list[dict]) -> list[dict]:
    left, top, right, bottom = rectangle
    samples = [
        {
            "source": "window_grid",
            "point": [round(left + (right - left) * x / 10), round(top + (bottom - top) * y / 8)],
        }
        for y in range(1, 8)
        for x in range(1, 10)
    ]
    for item in controls:
        if "rectangle" not in item:
            continue
        cl, ct, cr, cb = item["rectangle"]
        if not (left <= cl < cr <= right and top <= ct < cb <= bottom):
            continue
        samples.extend(
            {
                "source": item["name"],
                "point": [round(cl + (cr - cl) * x), round(ct + (cb - ct) * y)],
            }
            for x, y in ((0.25, 0.25), (0.5, 0.5), (0.75, 0.75))
        )
    return samples


def _verify_capture_visibility(window, evidence: Path, controls: list[dict], stage: str) -> dict:
    require_hosted_runner(os.environ, sys.platform, evidence)
    import win32gui

    rectangle = window.rectangle()
    samples = capture_points(
        [rectangle.left, rectangle.top, rectangle.right, rectangle.bottom], controls
    )
    for sample in samples:
        sample["handle"] = win32gui.WindowFromPoint(tuple(sample["point"]))
        sample["root"] = win32gui.GetAncestor(sample["handle"], 2)
    result = {
        "main_handle": window.handle,
        "foreground_handle": win32gui.GetForegroundWindow(),
        "visible_samples": samples,
        "stage": stage,
    }
    write_json(evidence / f"capture-visibility-{stage}.json", result)
    if result["foreground_handle"] != window.handle or any(
        item["root"] != window.handle for item in samples
    ):
        raise RuntimeError("Actual main window is not foreground or is obscured at capture samples")
    return result


def _prepare_visible_main(window, evidence: Path) -> dict:
    """Clear exact CI infrastructure notices; never change app flags/settings."""
    require_hosted_runner(os.environ, sys.platform, evidence)
    import win32con
    import win32gui

    _dismiss_paging_notice(window, evidence)
    minimized = []

    def minimize_host(handle, _context):
        title = win32gui.GetWindowText(handle)
        if win32gui.IsWindowVisible(handle) and r"C:\ProgramData\GitHub\Host" in title:
            minimized.append({"handle": handle, "class_name": win32gui.GetClassName(handle)})
            win32gui.ShowWindow(handle, win32con.SW_MINIMIZE)

    win32gui.EnumWindows(minimize_host, None)
    win32gui.ShowWindow(window.handle, win32con.SW_RESTORE)
    activation_error = None
    try:
        win32gui.SetForegroundWindow(window.handle)
    except Exception as error:
        activation_error = str(error)
    time.sleep(0.5)
    visible = _verify_capture_visibility(window, evidence, [], "prepared")
    result = {
        **visible,
        "minimized_runner_consoles": minimized,
        "activation_error": activation_error,
        "app_window_style_changed": False,
        "expected_translucent_panels": "default 200/255; desktop may be visible beneath panels",
    }
    write_json(evidence / "capture-visibility.json", result)
    return result


def _normal_exit(window, processes, evidence: Path, activity) -> None:
    from pywinauto import Desktop

    button = system_button(window)
    if button is None:
        raise RuntimeError("Cannot identify the native System menu for normal Exit")
    button.click_input()
    activity("system_menu_clicked")
    time.sleep(0.5)
    desktop = Desktop(backend="uia")
    menus = []
    for owner in desktop.windows():
        if owner.process_id() in {process.pid for process in processes}:
            menus.extend(
                item
                for item in owner.descendants(control_type="MenuItem")
                if item.window_text().strip() in {"Exit", "종료"}
            )
    if len(menus) != 1:
        raise RuntimeError("Cannot identify the application's Exit menu item")
    menus[0].click_input()
    activity("exit_menu_clicked")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        metadata = _window_metadata(processes)
        write_json(evidence / "exit-window-observation.json", metadata)
        modal = select_exit_modal(metadata, window.process_id(), window.handle)
        if modal:
            # Qt's owned modal can be below the main element in the UIA tree,
            # so Desktop.windows() is not a reliable enumeration of its HWND.
            dialog = desktop.window(handle=modal["handle"]).wrapper_object()
            write_json(evidence / "exit-accessibility.json", _controls(dialog))
            buttons = [
                item
                for item in dialog.descendants(control_type="Button")
                if item.window_text().replace("&", "").strip() in {"Yes", "예", "예(Y)"}
            ]
            if len(buttons) == 1:
                _capture(dialog, evidence / "normal-exit-confirmation.png", main=False)
                activity("exit_confirmation_observed")
                buttons[0].click_input()
                activity("exit_yes_clicked")
                return
        time.sleep(0.2)
    raise RuntimeError("Normal Exit confirmation was not observed")


def _controls(window) -> list[dict]:
    controls = []
    for item in window.descendants():
        name = item.window_text()
        control = {"name": name, "control_type": item.element_info.control_type}
        if name.strip() in {"Main Calendar", "Today's Schedule"} or FIXTURE_NAME in name:
            rect = item.rectangle()
            control["rectangle"] = [rect.left, rect.top, rect.right, rect.bottom]
        controls.append(control)
    return controls


def start_ready_observer(process, evidence: Path, log_path: Path, diagnostic: dict, activity):
    if "observer" not in diagnostic:
        observer = ExceptionObserver(
            process.pid, lambda: require_hosted_runner(os.environ, sys.platform, evidence)
        )
        diagnostic["observer"] = observer
        observer.start()
        write_json(
            evidence / "exception-observation-scope.json",
            {
                "pid": process.pid,
                "starts_after": "strict clean startup log, DB/worker readiness and Win32 splash gone",
                "ends_after": "normal Exit and EXIT_PROCESS_DEBUG_EVENT",
                "startup_debugger_attached": False,
                "raw_startup_log_remains_strict": True,
                "first_uia_probe_follows_observer_ready": True,
                "log_offset_at_attach": log_path.stat().st_size,
            },
        )
        activity("exception_observer_attached_before_first_uia")
    return diagnostic["observer"]


def prepare_main_capture(window, processes, evidence: Path, fixture: bool, activity):
    # A normal startup briefing legitimately disables/owns focus over main.
    # Acknowledge it before requiring active, unobscured main-window contents.
    briefing = _acknowledge_startup_summary(window, processes, evidence, fixture, activity)
    visibility = _prepare_visible_main(window, evidence)
    activity("main_foreground_verified")
    controls = _controls(window)
    write_json(evidence / "accessibility.json", controls)
    if not any(item["name"].strip() in {"System", "Settings", "시스템"} for item in controls):
        raise RuntimeError("Main-window accessibility tree lacks the application System menu")
    content = validate_main_content(controls, fixture)
    capture = _capture(
        window,
        evidence / "main-window.png",
        verify_visible=lambda stage: _verify_capture_visibility(window, evidence, controls, stage),
    )
    activity("main_calendar_and_task_capture")
    return briefing, visibility, content, capture


def _launch_cycle(
    payload: Path,
    profile: Path,
    evidence: Path,
    *,
    version: str,
    sqlite_version: str,
    baseline: bool = False,
    fixture: bool = False,
    diagnostic: dict | None = None,
) -> dict:
    evidence.mkdir()
    executable = payload / "DarkCalendar.exe"
    database = profile / "kimhyojin/Dark Calendar/desk_calendar.db"
    log_path = database.parent / "crash.log"
    previous = log_path.stat().st_size if log_path.exists() else 0
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "GH_TOKEN",
            "GITHUB_TOKEN",
            "ACTIONS_RUNTIME_TOKEN",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
        }
    }
    environment.update(LOCALAPPDATA=str(profile), APPDATA=str(profile / "Roaming"))
    input_evidence = _reset_runner_idle(evidence)
    started = time.time()
    process = subprocess.Popen([str(executable)], cwd=payload, env=environment)
    if diagnostic is None:
        diagnostic = {}
    diagnostic.update(parent=process, executable=executable, started=started)
    observer = None
    activities = []

    def activity(phase):
        activities.append(
            {
                "phase": phase,
                "observed_at": datetime.now().astimezone().isoformat(),
                "monotonic": time.monotonic(),
                "pid": process.pid,
                "process_running": process.poll() is None,
                "log_size": log_path.stat().st_size if log_path.exists() else 0,
            }
        )
        write_json(evidence / "ui-activity.json", activities)

    def attach_before_uia():
        nonlocal observer
        observer = start_ready_observer(process, evidence, log_path, diagnostic, activity)

    deadline = time.monotonic() + 90
    window = None
    while time.monotonic() < deadline:
        candidates = _related_processes(executable, started)
        if process.poll() is not None and not candidates:
            raise RuntimeError(f"Native app exited before UI readiness: {process.returncode}")
        fresh_log = (
            log_path.read_bytes()[previous:].decode("utf-8", errors="replace")
            if log_path.exists()
            else ""
        )
        check_runtime_log(fresh_log, pending=observer is not None and observer.trace["attached"])
        activity("before_main_readiness_probe")
        window = _main_window(
            candidates, evidence, ready=runtime_ready(fresh_log), before_uia=attach_before_uia
        )
        if window is not None:
            break
        time.sleep(0.5)
    if window is None:
        raise RuntimeError("No actual main window appeared before timeout")
    if observer is None:
        raise RuntimeError("UI readiness was observed without an active exception observer")
    time.sleep(2)
    candidates = _related_processes(executable, started)
    ui_process = next((item for item in candidates if item.pid == window.process_id()), None)
    if ui_process is None:
        raise RuntimeError("Window belongs to a different executable")
    if ui_process.pid != process.pid:
        raise RuntimeError("Native UI PID differs from the exception-observed process")
    activity("main_ready")
    user = ctypes.WinDLL("user32", use_last_error=True)
    bounds = validate_window_bounds(
        window,
        system_button(window),
        user.GetSystemMetrics(0),
        user.GetSystemMetrics(1),
        evidence=evidence,
    )
    write_json(
        evidence / "main-ready.json",
        {
            "pid": ui_process.pid,
            "handle": window.handle,
            "runtime_ready_log": True,
            "splash_gone": True,
            "bounds": bounds,
        },
    )
    loaded = {
        Path(item.path).name.lower(): Path(item.path).resolve()
        for item in ui_process.memory_maps()
        if item.path
    }
    bundled = {}
    for name in ("python313.dll", "qt6core.dll", "sqlite3.dll"):
        if name not in loaded or not loaded[name].is_relative_to((payload / "_internal").resolve()):
            raise RuntimeError(f"Native app did not load bundled {name}")
        bundled[name] = {"path": str(loaded[name]), "sha256": sha256(loaded[name])}
    briefing, visibility, content, capture = prepare_main_capture(
        window, candidates, evidence, fixture, activity
    )
    _normal_exit(window, candidates, evidence, activity)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and _related_processes(executable, started):
        time.sleep(0.25)
    if _related_processes(executable, started):
        raise RuntimeError("Application did not exit normally; no force-kill is used")
    return_code = process.wait(timeout=3)
    if return_code:
        raise RuntimeError(f"Application returned failure exit code {return_code}")
    text = log_path.read_bytes()[previous:].decode("utf-8", errors="replace")
    (evidence / "fresh-application.log").write_text(text, encoding="utf-8", errors="strict")
    observed_rpc = classify_rpc(observer.finish(), len(KNOWN_RPC.findall(text)), ui_process.pid)
    rpc_events = [event for event in observer.trace["events"] if event.get("code") == "0x8001010d"]
    if rpc_events and not any(
        item["phase"] == "exit_confirmation_observed"
        and item["process_running"]
        and item["monotonic"] > max(event["monotonic"] for event in rpc_events)
        for item in activities
    ):
        raise RuntimeError("No same-PID working Exit confirmation after the RPC diagnostic")
    write_json(evidence / "native-exception-events.json", observer.trace)
    write_json(evidence / "rpc-classification.json", observed_rpc)
    check_runtime_log(text, observed_rpc=observed_rpc)
    if not baseline:
        validate_launch_log(text, version, database, sqlite_version, observed_rpc=observed_rpc)
    if "Shutting down background workers" not in text or "Database connection closed" not in text:
        raise RuntimeError("Missing fresh normal shutdown/database-close evidence")
    return {
        "passed": True,
        "started_at": datetime.fromtimestamp(started).isoformat(),
        "executable": str(executable),
        "exe_sha256": sha256(executable),
        "window_pid": ui_process.pid,
        "capture": capture,
        "bundled_modules": bundled,
        "exit_code": return_code,
        "normal_exit": True,
        "force_killed": False,
        "runner_input": input_evidence,
        "bounds": bounds,
        "visibility": visibility,
        "main_content": content,
        "rpc_diagnostics": observed_rpc,
        "startup_briefing": briefing,
    }


def launch_cycle(payload: Path, profile: Path, evidence: Path, **options) -> dict:
    require_hosted_runner(os.environ, sys.platform, evidence)
    diagnostic = {}
    try:
        return _launch_cycle(payload, profile, evidence, diagnostic=diagnostic, **options)
    except Exception:
        # Preserve failure evidence too. These profiles exist only in this new
        # hosted VM and contain public defaults plus synthetic data.
        evidence.mkdir(exist_ok=True)
        crash_log = profile / "kimhyojin/Dark Calendar/crash.log"
        if crash_log.exists():
            shutil.copyfile(crash_log, evidence / "failure-application.log")
        if diagnostic:
            process = diagnostic["parent"]
            remaining = _related_processes(diagnostic["executable"], diagnostic["started"])
            write_json(
                evidence / "failure-process-state.json",
                {
                    "launched_parent_pid": process.pid,
                    "parent_exit_code": process.poll(),
                    "remaining_native_pids": [item.pid for item in remaining],
                    "force_killed": False,
                },
            )
            try:
                write_json(evidence / "failure-windows.json", _window_metadata(remaining))
            except Exception as diagnostic_error:
                write_json(
                    evidence / "failure-windows.json", {"diagnostic_error": str(diagnostic_error)}
                )
        raise
    finally:
        if diagnostic.get("observer") is not None:
            trace = diagnostic["observer"].close()
            write_json(evidence / "native-exception-events.json", trace)


def payload_manifest(payload: Path) -> dict:
    return {
        str(path.relative_to(payload)).replace("\\", "/"): sha256(path)
        for path in sorted(payload.rglob("*"))
        if path.is_file()
    }


def run(args, summary: dict) -> None:
    import psutil

    require_hosted_runner(os.environ, sys.platform, args.evidence)
    summary["desktop"] = _desktop_preflight()
    shared = Path(r"C:\Users\Public\DarkCalendar")
    running = [
        process.pid
        for process in psutil.process_iter(["name"])
        if (process.info["name"] or "").lower() == "darkcalendar.exe"
    ]
    preexisting_state = {
        "settings_key_exists": _settings_exists(),
        "shared_directory_exists": shared.exists(),
        "calendar_process_running": bool(running),
    }
    summary["preexisting_state"] = preexisting_state
    require_fresh_state(
        preexisting_state["settings_key_exists"],
        preexisting_state["shared_directory_exists"],
        running,
    )
    candidate = args.payload.resolve()
    baseline = args.baseline_payload.resolve()
    if sha256(baseline / "DarkCalendar.exe") != BASELINE_EXE_SHA256:
        raise RuntimeError("Baseline EXE is not the verified public 4.3.3 binary")
    native = verify_payload(candidate)
    summary["candidate_sqlite"] = native
    original_manifest = payload_manifest(candidate)
    write_json(args.evidence / "candidate-payload-manifest.json", original_manifest)
    engine = NativeSQLite(candidate / "_internal/sqlite3.dll")
    for scenario in ("fresh", "upgrade"):
        profile = args.evidence / f"{scenario}-profile"
        profile.mkdir()
        _prepare_settings(clear_owned=scenario == "upgrade")
        database = profile / "kimhyojin/Dark Calendar/desk_calendar.db"
        if scenario == "upgrade":
            database.parent.mkdir(parents=True)
            default = baseline / "_internal/desk_calendar_default.db"
            shutil.copyfile(default, database)
            seed_fixture(engine, database)
            baseline_record = launch_cycle(
                baseline,
                profile,
                args.evidence / "upgrade-baseline",
                version="4.3.3",
                sqlite_version="3.50.4",
                baseline=True,
                fixture=True,
            )
            summary["baseline"] = baseline_record
            inspect_database(engine, database, True)
            baseline_record["rpc_diagnostics"]["database_integrity_confirmed"] = True
        for index in range(3):
            record = launch_cycle(
                candidate,
                profile,
                args.evidence / f"{scenario}-{index + 1}",
                version=args.expected_version,
                sqlite_version=native["sqlite_version"],
                fixture=scenario == "upgrade" or index > 0,
            )
            record["database"] = inspect_database(
                engine, database, scenario == "upgrade" or index > 0
            )
            record["rpc_diagnostics"]["database_integrity_confirmed"] = True
            if scenario == "fresh" and index == 0:
                seed_fixture(engine, database)
                inspect_database(engine, database, True)
                record["synthetic_fixture_seeded_after_normal_exit"] = True
            summary["cycles"].append({"scenario": scenario, "launch": index + 1, **record})
            write_json(args.evidence / "summary.json", summary)
    if payload_manifest(candidate) != original_manifest:
        raise RuntimeError("Final candidate payload changed during native validation")
    summary["candidate_payload_unchanged"] = True
    summary["passed"] = len(summary["cycles"]) == 6
    summary["review_required"] = (
        "Review all six main-window screenshots before publishing the draft."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--baseline-payload", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args(argv)
    # The guard precedes every mutation and import that could initialize UI.
    try:
        require_hosted_runner(os.environ, sys.platform, args.evidence)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    args.evidence = args.evidence.resolve()
    args.evidence.mkdir(parents=True, exist_ok=False)
    summary = {
        "passed": False,
        "release_complete": False,
        "store_identity_checked": False,
        "cycles": [],
        "sources": [
            "https://learn.microsoft.com/en-us/windows/apps/develop/ai-assisted/testing#run-tests-in-ci",
            "https://docs.github.com/en/actions/reference/runners/github-hosted-runners",
        ],
    }
    try:
        run(args, summary)
    except Exception as error:
        summary["error"] = f"{type(error).__name__}: {error}"
        print(summary["error"], file=sys.stderr)
    finally:
        write_json(args.evidence / "summary.json", summary)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
