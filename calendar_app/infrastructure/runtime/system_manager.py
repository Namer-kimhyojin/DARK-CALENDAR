# -*- coding: utf-8 -*-
"""Windows integration helpers for login startup registration."""

from __future__ import annotations

import asyncio
import contextlib
import ctypes
from pathlib import Path
import subprocess
import sys

from PyQt6.QtCore import QSettings

_ORG = "kimhyojin"
_APP = "Dark Calendar"
_KEY = "autostart_enabled"
_MIGRATION_KEY = "autostart_registration_v2_migrated"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE_NAME = "DarkCalendar"
_STARTUP_TASK_ID = "DarkCalendarStartup"


def _new_settings() -> QSettings:
    return QSettings(_ORG, _APP)


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _has_package_identity() -> bool:
    """Return True when the current process is running inside an MSIX package."""
    if sys.platform != "win32":
        return False
    try:
        length = ctypes.c_uint32(0)
        result = ctypes.windll.kernel32.GetCurrentPackageFullName(
            ctypes.byref(length),
            None,
        )
        return result in {0, 122}  # ERROR_SUCCESS / ERROR_INSUFFICIENT_BUFFER
    except (AttributeError, OSError):
        return False


def _get_packaged_startup_task():
    if not _has_package_identity():
        return None
    try:
        from winrt.windows.applicationmodel import StartupTask

        return asyncio.run(StartupTask.get_async(_STARTUP_TASK_ID))
    except (ImportError, OSError, RuntimeError):
        return None


def _task_state_name(task) -> str:
    state = getattr(task, "state", None)
    return str(getattr(state, "name", state) or "").upper()


def _is_packaged_task_enabled(task) -> bool:
    return _task_state_name(task) in {"ENABLED", "ENABLED_BY_POLICY"}


def _enable_packaged_task(task) -> bool:
    try:
        state = asyncio.run(task.request_enable_async())
    except (OSError, RuntimeError):
        return False
    state_name = str(getattr(state, "name", state) or "").upper()
    return state_name in {"ENABLED", "ENABLED_BY_POLICY"}


def _disable_packaged_task(task) -> bool:
    try:
        task.disable()
    except OSError:
        return False
    return not _is_packaged_task_enabled(task)


def _standalone_command() -> str:
    executable = str(Path(sys.executable).resolve())
    if _is_frozen():
        args = [executable]
    else:
        project_root = Path(__file__).resolve().parents[3]
        args = [executable, str(project_root / "main.py")]
    return subprocess.list2cmdline(args)


def _registry_autostart_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _value_type = winreg.QueryValueEx(key, _RUN_VALUE_NAME)
        return bool(str(value).strip())
    except (FileNotFoundError, OSError):
        return False


def _set_registry_autostart(enabled: bool) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            if enabled:
                winreg.SetValueEx(
                    key,
                    _RUN_VALUE_NAME,
                    0,
                    winreg.REG_SZ,
                    _standalone_command(),
                )
            else:
                with contextlib.suppress(FileNotFoundError):
                    winreg.DeleteValue(key, _RUN_VALUE_NAME)
        return _registry_autostart_enabled() is bool(enabled)
    except OSError:
        return False


def _persist_status(settings: QSettings, enabled: bool, *, migrated: bool = False) -> None:
    settings.setValue(_KEY, bool(enabled))
    if migrated:
        settings.setValue(_MIGRATION_KEY, True)
    settings.sync()


def is_autostart_enabled() -> bool:
    settings = _new_settings()
    legacy_enabled = settings.value(_KEY, False, type=bool)
    migrated = settings.value(_MIGRATION_KEY, False, type=bool)

    task = _get_packaged_startup_task()
    if task is not None:
        enabled = _is_packaged_task_enabled(task)
        if legacy_enabled and not migrated and _task_state_name(task) == "DISABLED":
            enabled = _enable_packaged_task(task)
            migrated = True
        _persist_status(settings, enabled, migrated=migrated)
        return enabled

    if _has_package_identity():
        # A packaged build must never register its versioned WindowsApps path in Run.
        return False

    if not _is_frozen():
        return bool(legacy_enabled)

    enabled = _registry_autostart_enabled()
    if legacy_enabled and not migrated and not enabled:
        enabled = _set_registry_autostart(True)
        migrated = True
    _persist_status(settings, enabled, migrated=migrated)
    return enabled


def set_autostart(enabled: bool) -> bool:
    requested = bool(enabled)
    settings = _new_settings()

    task = _get_packaged_startup_task()
    if task is not None:
        if requested:
            changed = _enable_packaged_task(task)
            actual = changed or _is_packaged_task_enabled(task)
        else:
            changed = _disable_packaged_task(task)
            actual = _is_packaged_task_enabled(task)
        _persist_status(settings, actual, migrated=True)
        return changed and actual == requested

    if _has_package_identity():
        return False

    if _is_frozen():
        changed = _set_registry_autostart(requested)
        actual = _registry_autostart_enabled()
        _persist_status(settings, actual, migrated=True)
        return changed and actual == requested

    # Source runs retain the preference without installing a development path.
    _persist_status(settings, requested)
    return True
