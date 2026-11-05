# -*- coding: utf-8 -*-
"""Minimize only the proven hosted paging-notice process's remaining surface."""

from __future__ import annotations

from contextlib import contextmanager, suppress
import json
from pathlib import Path

_NOTICE_FILES = (
    "runner-paging-notice.json",
    "runner-paging-notice-result.json",
    "runner-paging-notice-acknowledged.json",
)


class Win32RunnerSurface:
    def __init__(self):
        import psutil
        import win32con
        import win32gui
        import win32process

        self.psutil, self.constants = psutil, win32con
        self.gui, self.process = win32gui, win32process

    def describe(self, handle):
        result = {"handle": handle, "exists": bool(self.gui.IsWindow(handle))}
        if result["exists"]:
            pid = self.process.GetWindowThreadProcessId(handle)[1]
            process = self.psutil.Process(pid)
            result.update(
                pid=pid,
                executable=process.exe(),
                process_created=process.create_time(),
                title=self.gui.GetWindowText(handle),
                class_name=self.gui.GetClassName(handle),
                visible=bool(self.gui.IsWindowVisible(handle)),
                minimized=bool(self.gui.IsIconic(handle)),
                rectangle=list(self.gui.GetWindowRect(handle)),
            )
        return result

    def windows(self):
        values = []

        def observe(handle, _context):
            try:
                values.append(self.describe(handle))
            except Exception as error:
                values.append({"handle": handle, "identity_error": str(error)})

        self.gui.EnumWindows(observe, None)
        return values

    def minimize(self, handle):
        self.gui.ShowWindow(handle, self.constants.SW_MINIMIZE)


def _exact_executable(value, expected):
    path = Path(value)
    return path.parent == expected.parent and path.resolve() == expected


def acknowledged_notice(smoke, evidence, app_pid, executable):
    values = []
    for name in _NOTICE_FILES:
        path = evidence / name
        if path.is_symlink() or not path.resolve().is_relative_to(evidence.resolve()):
            raise ValueError("Paging provenance must remain in this evidence directory")
        values.append(json.loads(path.read_text(encoding="utf-8", errors="strict")))
    notice, result, acknowledged = values
    button = smoke.select_paging_notice(notice, app_pid)
    before = result.get("before", {})
    keys = ("handle", "pid", "title", "class_name", "executable")
    if (
        button is None
        or smoke.select_paging_notice(before, app_pid) != button
        or any(before.get(key) != notice.get(key) for key in keys)
        or type(notice.get("pid")) is not int
        or not _exact_executable(notice["executable"], executable)
        or acknowledged.get("handle") != notice["handle"]
        or acknowledged.get("ok_clicked") is not True
        or acknowledged.get("settings_changed") is not False
        or result.get("handle") != notice["handle"]
        or result.get("button") != button
        or result.get("ok_clicked") is not True
        or result.get("notice_still_exists") is not False
    ):
        raise ValueError("No exact newly acknowledged System32 performance paging notice")
    return {"notice": notice, "result": result, "acknowledged": acknowledged}


def matches_surface(value, notice, app_pid, executable):
    return (
        value.get("exists") is True
        and value.get("visible") is True
        and value.get("minimized") is False
        and value.get("pid") == notice["pid"]
        and value.get("pid") != app_pid
        and value.get("title") == "Performance Options"
        and value.get("class_name") == "#32770"
        and _exact_executable(value.get("executable", ""), executable)
    )


@contextmanager
def install_runner_surface_adapter(smoke, *, backend_factory=Win32RunnerSurface):
    """Run original notice handling, then all original main visibility gates."""
    original = smoke._dismiss_paging_notice

    def dismiss(window, evidence):
        smoke.require_hosted_runner(smoke.os.environ, smoke.sys.platform, evidence)
        existing = [
            name
            for name in _NOTICE_FILES
            if (evidence / name).exists() or (evidence / name).is_symlink()
        ]
        result = original(window, evidence)
        report = {"settings_changed": False, "operation": "none", "existing_provenance": existing}
        try:
            if existing or not all((evidence / name).is_file() for name in _NOTICE_FILES):
                report["reason"] = "No new exact paging acknowledgement in this evidence directory"
                return result
            executable = (
                Path(smoke.os.environ["SYSTEMROOT"]) / "System32/SystemPropertiesPerformance.exe"
            ).resolve(strict=True)
            proof = acknowledged_notice(smoke, evidence, window.process_id(), executable)
            report["paging_provenance"] = proof
            backend = backend_factory()
            if backend.describe(proof["notice"]["handle"]).get("exists") is not False:
                raise ValueError(
                    "Acknowledged notice HWND exists again; no surface operation allowed"
                )
            raw = backend.windows()
            report["raw_windows"] = raw
            candidates = [
                value
                for value in raw
                if matches_surface(value, proof["notice"], window.process_id(), executable)
            ]
            if len(candidates) != 1:
                report["reason"] = "No unique exact Performance Options surface"
                return result
            selected = candidates[0]
            current = backend.describe(selected["handle"])
            report.update(selected=selected, before_minimize=current)
            if (
                not matches_surface(current, proof["notice"], window.process_id(), executable)
                or current.get("handle") != selected["handle"]
                or current.get("process_created") != selected.get("process_created")
            ):
                raise ValueError("Performance Options identity changed before minimization")
            backend.minimize(current["handle"])
            report.update(
                operation="SW_MINIMIZE",
                reason="Same newly acknowledged paging-notice PID and exact System32 executable",
                after=backend.describe(current["handle"]),
            )
        except Exception as error:
            # Keep original foreground/content/physical visibility checks authoritative.
            report["observation_error"] = str(error)
        finally:
            with suppress(Exception):
                smoke.write_json(evidence / "runner-performance-surface.json", report)
        return result

    smoke._dismiss_paging_notice = dismiss
    try:
        yield smoke
    finally:
        smoke._dismiss_paging_notice = original
