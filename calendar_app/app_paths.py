from __future__ import annotations

import contextlib
import os
from pathlib import Path
import shutil
import sys

APP_VENDOR = "kimhyojin"
APP_NAME = "Dark Calendar"


def get_project_dir() -> Path:
    return Path(__file__).resolve().parent


def get_resource_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return get_project_dir()


def get_app_data_dir() -> Path:
    base_dir = os.environ.get("LOCALAPPDATA")
    if base_dir:
        app_dir = Path(base_dir) / APP_VENDOR / APP_NAME
    else:
        app_dir = Path.home() / "AppData" / "Local" / APP_VENDOR / APP_NAME
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_resource_path(*parts: str) -> str:
    # First, check the root project directory (fallback_path)
    # This allows a root app_icon.ico to take precedence over an internal one.
    # Note: get_project_dir() returns calendar_app here, we want the actual root.

    # We define the actual root as the parent of get_project_dir()
    # since get_project_dir() returns the package folder (calendar_app)
    actual_root = get_project_dir().parent
    root_path = actual_root.joinpath(*parts)
    if root_path.exists():
        return str(root_path)

    # Check Assets folder in root
    assets_path = actual_root.joinpath("Assets", *parts)
    if assets_path.exists():
        return str(assets_path)

    resource_path = get_resource_dir().joinpath(*parts)
    if resource_path.exists():
        return str(resource_path)

    # Check Assets folder in calendar_app
    pkg_assets = get_project_dir().joinpath("Assets", *parts)
    if pkg_assets.exists():
        return str(pkg_assets)

    fallback_path = get_project_dir().joinpath(*parts)
    if fallback_path.exists():
        return str(fallback_path)

    return str(resource_path)


def migrate_legacy_runtime_files() -> None:
    app_data_dir = get_app_data_dir()
    runtime_files = (
        "desk_calendar.db",
        "desk_calendar.db-shm",
        "desk_calendar.db-wal",
        "desk_calendar.log",
        "credentials.json",
        "token.json",
    )

    legacy_dirs: list[Path] = []

    # Developer convenience for source runs only.
    # For frozen builds, never migrate from bundled directories.
    if not getattr(sys, "frozen", False):
        legacy_dirs.append(get_project_dir())

    # Migrate from historical app folders (old product names).
    base_dir = os.environ.get("LOCALAPPDATA")
    if base_dir:
        base_path = Path(base_dir) / APP_VENDOR
    else:
        base_path = Path.home() / "AppData" / "Local" / APP_VENDOR
    for legacy_name in ("Desk Calendar",):
        candidate = base_path / legacy_name
        if candidate.exists():
            legacy_dirs.append(candidate)

    app_data_resolved = app_data_dir.resolve()
    for source_dir in legacy_dirs:
        try:
            if source_dir.resolve() == app_data_resolved:
                continue
        except OSError:
            continue

        for filename in runtime_files:
            legacy_path = source_dir / filename
            target_path = app_data_dir / filename
            if legacy_path.exists() and not target_path.exists():
                with contextlib.suppress(OSError):
                    shutil.copy2(legacy_path, target_path)

        legacy_locales_dir = source_dir / "locales_user"
        if legacy_locales_dir.is_dir():
            target_locales_dir = app_data_dir / "locales_user"
            try:
                target_locales_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                continue
            for legacy_file in legacy_locales_dir.glob("*.json"):
                target_file = target_locales_dir / legacy_file.name
                if not target_file.exists():
                    with contextlib.suppress(OSError):
                        shutil.copy2(legacy_file, target_file)

    # Bundle default DB logic
    default_db_src = get_resource_dir() / "desk_calendar_default.db"
    main_db_path = app_data_dir / "desk_calendar.db"
    if default_db_src.exists() and not main_db_path.exists():
        with contextlib.suppress(OSError):
            shutil.copy2(default_db_src, main_db_path)


_APP_DATA_DIR = get_app_data_dir()
migrate_legacy_runtime_files()

APP_DATA_DIR = str(_APP_DATA_DIR)
DB_PATH = str(_APP_DATA_DIR / "desk_calendar.db")
LOG_PATH = str(_APP_DATA_DIR / "desk_calendar.log")
CREDENTIALS_PATH = str(_APP_DATA_DIR / "credentials.json")
TOKEN_PATH = str(_APP_DATA_DIR / "token.json")
APP_ICON_PATH = get_resource_path("app_icon.ico")
APP_ICON_TOAST_PATH = get_resource_path("app_icon.png")
DEFAULT_PRESETS_PATH = get_resource_path("default_presets.json")
