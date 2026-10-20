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
    from scripts.verify_sqlite_runtime import verify_payload
except ModuleNotFoundError:
    from verify_sqlite_runtime import verify_payload

SETTINGS_KEY = r"Software\kimhyojin\Dark Calendar"
FIXTURE_NAME = "Native release synthetic persistence fixture"
FIXTURE_CALENDAR = "native-release-fixture"
BASELINE_EXE_SHA256 = "1363e829f3c71e4e38222497076237c84fff5875d056ca6f50a7f6067e5100d5"
ERROR_PATTERN = re.compile(
    r"Unhandled exception|Traceback \(most recent call last\)|Database startup aborted|"
    r"database disk image is malformed|Database initialization failed|\[(?:ERROR|CRITICAL)\]",
    re.IGNORECASE,
)


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


def validate_launch_log(text: str, version: str, database: Path, sqlite_version: str) -> None:
    if ERROR_PATTERN.search(text):
        raise RuntimeError("Fresh application log contains an error or traceback")
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


def _main_window(processes):
    from pywinauto import Desktop
    import win32gui
    import win32process

    pids = {process.pid for process in processes}
    handles = set()

    def collect(handle, _context):
        if win32process.GetWindowThreadProcessId(handle)[1] in pids:
            title = win32gui.GetWindowText(handle)
            if ERROR_PATTERN.search(title) or "cannot start" in title.lower():
                raise RuntimeError(f"Native error window: {title}")
            if title == "Air Calendar" and win32gui.IsWindowVisible(handle):
                handles.add(handle)

    def top(handle, _context):
        collect(handle, None)
        win32gui.EnumChildWindows(handle, collect, None)

    win32gui.EnumWindows(top, None)
    if len(handles) > 1:
        raise RuntimeError("More than one candidate main window exists")
    if not handles:
        return None
    return Desktop(backend="uia").window(handle=handles.pop()).wrapper_object()


def _capture(window, destination: Path, *, main: bool = True) -> dict:
    # Window-bound capture and UIA ownership are both recorded; the reviewer sees
    # the actual rendered image, not a source-rendered substitute.
    if main:
        window.set_focus()
        time.sleep(0.3)
    image = window.capture_as_image()
    statistics = validate_capture(image) if main else {"width": image.width, "height": image.height}
    image.save(destination, format="PNG")
    return {
        **statistics,
        "path": destination.name,
        "sha256": sha256(destination),
        "window_handle": window.handle,
        "process_id": window.process_id(),
    }


def _normal_exit(window, process_ids: set[int], evidence: Path) -> None:
    from pywinauto import Desktop

    buttons = [
        item
        for item in window.descendants(control_type="Button")
        if item.window_text().strip() in {"System", "Settings", "시스템"}
    ]
    if len(buttons) != 1:
        raise RuntimeError("Cannot identify the native System menu for normal Exit")
    buttons[0].click_input()
    time.sleep(0.5)
    desktop = Desktop(backend="uia")
    menus = []
    for owner in desktop.windows():
        if owner.process_id() in process_ids:
            menus.extend(
                item
                for item in owner.descendants(control_type="MenuItem")
                if item.window_text().strip() in {"Exit", "종료"}
            )
    if len(menus) != 1:
        raise RuntimeError("Cannot identify the application's Exit menu item")
    menus[0].click_input()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        dialogs = [
            item
            for item in desktop.windows()
            if item.process_id() in process_ids
            and item.window_text() in {"Exit", "Exit Confirmation", "종료 안내", "Exit Notice"}
        ]
        for dialog in dialogs:
            buttons = [
                item
                for item in dialog.descendants(control_type="Button")
                if item.window_text().replace("&", "").strip() in {"Yes", "예", "예(Y)"}
            ]
            if len(buttons) == 1:
                _capture(dialog, evidence / "normal-exit-confirmation.png", main=False)
                buttons[0].click_input()
                return
        time.sleep(0.2)
    raise RuntimeError("Normal Exit confirmation was not observed")


def _launch_cycle(
    payload: Path,
    profile: Path,
    evidence: Path,
    *,
    version: str,
    sqlite_version: str,
    baseline: bool = False,
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
    started = time.time()
    process = subprocess.Popen([str(executable)], cwd=payload, env=environment)
    deadline = time.monotonic() + 90
    window = None
    while time.monotonic() < deadline:
        candidates = _related_processes(executable, started)
        if process.poll() is not None and not candidates:
            raise RuntimeError(f"Native app exited before UI readiness: {process.returncode}")
        window = _main_window(candidates)
        if window is not None and len(window.descendants()) >= 20:
            break
        time.sleep(0.5)
    if window is None:
        raise RuntimeError("No actual main window appeared before timeout")
    time.sleep(2)
    candidates = _related_processes(executable, started)
    ui_process = next((item for item in candidates if item.pid == window.process_id()), None)
    if ui_process is None:
        raise RuntimeError("Window belongs to a different executable")
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
    capture = _capture(window, evidence / "main-window.png")
    controls = [
        {"name": item.window_text(), "control_type": item.element_info.control_type}
        for item in window.descendants()
    ]
    write_json(evidence / "accessibility.json", controls)
    if not any(item["name"].strip() in {"System", "Settings", "시스템"} for item in controls):
        raise RuntimeError("Main-window accessibility tree lacks the application System menu")
    _normal_exit(window, {item.pid for item in candidates}, evidence)
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
    if ERROR_PATTERN.search(text):
        raise RuntimeError("Fresh application log contains an error")
    if not baseline:
        validate_launch_log(text, version, database, sqlite_version)
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
    }


def launch_cycle(payload: Path, profile: Path, evidence: Path, **options) -> dict:
    require_hosted_runner(os.environ, sys.platform, evidence)
    try:
        return _launch_cycle(payload, profile, evidence, **options)
    except Exception:
        # Preserve failure evidence too. These profiles exist only in this new
        # hosted VM and contain public defaults plus synthetic data.
        evidence.mkdir(exist_ok=True)
        crash_log = profile / "kimhyojin/Dark Calendar/crash.log"
        if crash_log.exists():
            shutil.copyfile(crash_log, evidence / "failure-application.log")
        raise


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
    require_fresh_state(_settings_exists(), shared.exists(), running)
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
            )
            summary["baseline"] = baseline_record
            inspect_database(engine, database, True)
        for index in range(3):
            record = launch_cycle(
                candidate,
                profile,
                args.evidence / f"{scenario}-{index + 1}",
                version=args.expected_version,
                sqlite_version=native["sqlite_version"],
            )
            record["database"] = inspect_database(
                engine, database, scenario == "upgrade" or index > 0
            )
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
