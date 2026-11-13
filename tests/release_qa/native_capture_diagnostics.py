# -*- coding: utf-8 -*-
"""Observe real desktop occlusion before the unchanged native visibility gate."""

from __future__ import annotations

from contextlib import contextmanager, suppress
from datetime import UTC, datetime, timezone
from pathlib import Path
import re


def capture_snapshot(smoke, window, evidence: Path, controls, stage: str) -> dict:
    """Read native pixels/window state; never activate, hide or change a window."""
    smoke.require_hosted_runner(smoke.os.environ, smoke.sys.platform, evidence)
    from PIL import ImageGrab
    import psutil
    import win32api
    import win32con
    import win32gui
    import win32process

    if re.fullmatch(r"[A-Za-z0-9_-]+", stage) is None:
        raise ValueError("Unsafe native diagnostic stage")
    rectangle = window.rectangle()
    bounds = [rectangle.left, rectangle.top, rectangle.right, rectangle.bottom]
    samples = smoke.capture_points(bounds, controls)
    handles = []
    current = win32gui.GetTopWindow(0)
    while current and current not in handles:
        handles.append(current)
        current = win32gui.GetWindow(current, win32con.GW_HWNDNEXT)
        if len(handles) > 10000:
            raise RuntimeError("Native desktop Z-order did not terminate")
    ranks = {handle: rank for rank, handle in enumerate(handles)}
    extras = set()
    for item in samples:
        hit = win32gui.WindowFromPoint(tuple(item["point"]))
        root = win32gui.GetAncestor(hit, win32con.GA_ROOT) if hit else 0
        item.update(handle=hit, root=root, root_z_order=ranks.get(root))
        extras.update((hit, root))

    def describe(handle):
        result = {"handle": handle, "z_order": ranks.get(handle)}
        try:
            tid, pid = win32process.GetWindowThreadProcessId(handle)
            result.update(
                pid=pid,
                tid=tid,
                title=win32gui.GetWindowText(handle),
                class_name=win32gui.GetClassName(handle),
                rectangle=list(win32gui.GetWindowRect(handle)),
                parent=win32gui.GetParent(handle),
                owner=win32gui.GetWindow(handle, win32con.GW_OWNER),
                root=win32gui.GetAncestor(handle, win32con.GA_ROOT),
                root_owner=win32gui.GetAncestor(handle, win32con.GA_ROOTOWNER),
                visible=bool(win32gui.IsWindowVisible(handle)),
                enabled=bool(win32gui.IsWindowEnabled(handle)),
                minimized=bool(win32gui.IsIconic(handle)),
                style=win32gui.GetWindowLong(handle, win32con.GWL_STYLE),
                extended_style=win32gui.GetWindowLong(handle, win32con.GWL_EXSTYLE),
            )
            try:
                result["executable"] = psutil.Process(pid).exe()
            except (psutil.Error, OSError) as error:
                result["executable_error"] = str(error)
            if result["extended_style"] & win32con.WS_EX_LAYERED:
                try:
                    result["layered_attributes"] = list(win32gui.GetLayeredWindowAttributes(handle))
                except Exception as error:
                    # UpdateLayeredWindow per-pixel alpha need not expose global attributes.
                    result["layered_attributes_error"] = str(error)
        except Exception as error:
            result["observation_error"] = str(error)
        return result

    desktop = [
        win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN),
        win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN),
    ]
    desktop.extend(
        (
            desktop[0] + win32api.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN),
            desktop[1] + win32api.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN),
        )
    )
    result = {
        "stage": stage,
        "observed_at": datetime.now(UTC).isoformat(),
        "main_handle": window.handle,
        "main_bounds": bounds,
        "main_z_order": ranks.get(window.handle),
        "foreground_handle": win32gui.GetForegroundWindow(),
        "desktop_bounds": desktop,
        "visible_samples": samples,
        "top_level_windows_front_to_back": [describe(handle) for handle in handles],
        "hit_windows": [describe(handle) for handle in sorted(extras - {0})],
        "native_pixels": True,
        "windows_changed": False,
    }
    try:
        pixels = ImageGrab.grab(bbox=tuple(desktop), all_screens=True)
        desktop_path = evidence / f"diagnostic-{stage}-desktop.png"
        pixels.save(desktop_path)
        result["desktop_png"] = desktop_path.name
        if not (
            desktop[0] <= bounds[0] < bounds[2] <= desktop[2]
            and desktop[1] <= bounds[1] < bounds[3] <= desktop[3]
        ):
            raise RuntimeError("Main rectangle is outside captured desktop")
        client_path = evidence / f"diagnostic-{stage}-main.png"
        pixels.crop(
            (
                bounds[0] - desktop[0],
                bounds[1] - desktop[1],
                bounds[2] - desktop[0],
                bounds[3] - desktop[1],
            )
        ).save(client_path)
        result["main_png"] = client_path.name
    except Exception as error:
        result["pixel_error"] = str(error)
    return result


@contextmanager
def install_diagnostics(smoke, *, snapshot=capture_snapshot):
    """Add evidence, then call the exact gate; every original failure propagates."""
    original = smoke._verify_capture_visibility

    def observe(window, evidence, controls, stage):
        # Reject local/native experiments before importing any capture/UI package.
        smoke.require_hosted_runner(smoke.os.environ, smoke.sys.platform, evidence)

        def preserve(suffix):
            try:
                value = snapshot(smoke, window, evidence, controls, suffix)
            except Exception as error:
                value = {"stage": suffix, "diagnostic_error": str(error)}
            # Diagnostic I/O cannot replace or prevent the original gate/result.
            with suppress(Exception):
                smoke.write_json(evidence / f"diagnostic-{suffix}.json", value)

        preserve(f"{stage}-before-gate")
        try:
            return original(window, evidence, controls, stage)
        except BaseException:
            preserve(f"{stage}-gate-failed")
            raise

    smoke._verify_capture_visibility = observe
    try:
        yield smoke
    finally:
        smoke._verify_capture_visibility = original
