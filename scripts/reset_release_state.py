"""Reset local runtime/profile state before creating release artifacts.

This script helps avoid leaking developer-local defaults into release tests by:
1) removing runtime files from project folders
2) clearing QSettings for known app names
3) optionally purging LOCALAPPDATA runtime folders
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil

try:
    from PyQt6.QtCore import QSettings
except Exception:  # pragma: no cover - optional at script runtime
    QSettings = None


ORG = "kimhyojin"
APP_NAMES = ("Dark Calendar", "Desk Calendar")

RUNTIME_FILES = (
    "desk_calendar.db",
    "desk_calendar.db-shm",
    "desk_calendar.db-wal",
    "dark_calendar.db",
    "dark_calendar.db-shm",
    "dark_calendar.db-wal",
    "desk_calendar.log",
    "dark_calendar.log",
    "token.json",
    "credentials.json",
)


def _remove_path(path: Path, dry_run: bool) -> bool:
    if not path.exists():
        return False
    print(f"[remove] {path}")
    if dry_run:
        return True
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)
    return True


def _clear_project_runtime_files(project_dir: Path, dry_run: bool) -> int:
    removed = 0
    for base in (project_dir, project_dir / "calendar_app"):
        for name in RUNTIME_FILES:
            if _remove_path(base / name, dry_run):
                removed += 1
    for extra_name in ("away_lock_debug.log",):
        if _remove_path(project_dir / extra_name, dry_run):
            removed += 1
    return removed


def _clear_qsettings(dry_run: bool) -> int:
    if QSettings is None:
        print("[skip] PyQt6 is unavailable, cannot clear QSettings.")
        return 0
    changed = 0
    for app_name in APP_NAMES:
        settings = QSettings(ORG, app_name)
        keys = settings.allKeys()
        if not keys:
            continue
        print(f"[clear settings] {ORG}/{app_name} ({len(keys)} keys)")
        if not dry_run:
            settings.clear()
            settings.sync()
        changed += len(keys)
    return changed


def _purge_local_appdata(dry_run: bool) -> int:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        return 0
    root = Path(local_appdata) / ORG
    removed = 0
    for app_name in APP_NAMES:
        if _remove_path(root / app_name, dry_run):
            removed += 1
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset release state for clean packaging.")
    parser.add_argument(
        "--project-dir",
        default=str(Path(__file__).resolve().parents[1]),
        help="Project root directory (default: parent of scripts/).",
    )
    parser.add_argument(
        "--purge-local-data",
        action="store_true",
        help="Also remove LOCALAPPDATA/kimhyojin/{Dark Calendar,Desk Calendar}.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be removed without changing anything.",
    )
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    print(f"[info] project_dir={project_dir}")
    print(f"[info] dry_run={args.dry_run}")
    print(f"[info] purge_local_data={args.purge_local_data}")

    removed_files = _clear_project_runtime_files(project_dir, args.dry_run)
    cleared_keys = _clear_qsettings(args.dry_run)
    purged_dirs = _purge_local_appdata(args.dry_run) if args.purge_local_data else 0

    print(
        f"[done] removed_files={removed_files}, cleared_qsettings_keys={cleared_keys}, "
        f"purged_local_dirs={purged_dirs}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
