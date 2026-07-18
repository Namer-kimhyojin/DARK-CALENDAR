# -*- coding: utf-8 -*-
"""Build or sanitize a Windows Store payload for Dark Calendar."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

from calendar_app.shared.calendar_defaults import DEFAULT_CALENDAR_COLOR

ROOT = Path(__file__).resolve().parent
DIST_DIR = ROOT / "dist" / "DarkCalendar"
DEFAULT_DB_NAME = "desk_calendar_default.db"
DEFAULT_DB_PATH = ROOT / DEFAULT_DB_NAME
SENSITIVE_PATTERNS = (
    "token.json",
    "credentials.json",
    "desk_calendar.db",
    "desk_calendar.db-shm",
    "desk_calendar.db-wal",
    "desk_calendar.log",
)


def _resolve_dist_dir(dist_dir: str | Path | None = None) -> Path:
    if dist_dir is None:
        return DIST_DIR
    return Path(dist_dir)


def create_clean_default_db(output_path: str | Path | None = None) -> Path:
    """Create a bundled default DB without local data or sync state."""
    print("[1/4] creating clean bundled DB")

    target_path = Path(output_path) if output_path is not None else DEFAULT_DB_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        target_path.unlink()

    conn = sqlite3.connect(str(target_path))
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS unified_task (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'schedule',
            priority TEXT DEFAULT 'normal',
            status TEXT DEFAULT 'in_progress',
            deadline TEXT,
            end_date TEXT,
            alarm_time TEXT,
            recurrence TEXT,
            template_id INTEGER,
            target_date TEXT,
            cycle_type TEXT,
            period_start TEXT,
            period_end TEXT,
            series_id TEXT,
            series_order INTEGER,
            series_total INTEGER,
            is_completed INTEGER DEFAULT 0,
            completed_at TEXT,
            bg_color TEXT,
            icon TEXT,
            description TEXT,
            memo TEXT,
            location TEXT,
            assignee TEXT,
            all_day INTEGER DEFAULT 0,
            gcal_event_id TEXT,
            gcal_source_calendar_id TEXT,
            gcal_source_summary TEXT,
            gcal_target_calendar_id TEXT,
            gcal_sync_mode TEXT DEFAULT 'local_owned',
            gcal_dirty INTEGER DEFAULT 1,
            gcal_last_synced_at TEXT,
            gcal_remote_updated_at TEXT,
            gcal_sync_error TEXT,
            updated_at TEXT DEFAULT (datetime('now', 'localtime')),
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            calendar_id TEXT,
            FOREIGN KEY (template_id) REFERENCES routine_template(id) ON DELETE SET NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS worklog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            task_type TEXT,
            duration_seconds INTEGER,
            logged_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS gcal_delete_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gcal_event_id TEXT NOT NULL,
            gcal_calendar_id TEXT,
            local_task_id INTEGER,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            last_error TEXT,
            retry_count INTEGER DEFAULT 0,
            next_retry_at TEXT,
            last_attempt_at TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS gcal_deleted_task_archive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_task_id INTEGER,
            gcal_event_id TEXT,
            name TEXT,
            deadline TEXT,
            end_date TEXT,
            description TEXT,
            location TEXT,
            all_day INTEGER DEFAULT 0,
            archived_reason TEXT,
            archived_at TEXT DEFAULT (datetime('now', 'localtime')),
            snapshot_json TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS gcal_sync_conflict_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            local_task_id INTEGER,
            gcal_event_id TEXT,
            gcal_calendar_id TEXT,
            conflict_kind TEXT DEFAULT 'remote_overwrite',
            local_snapshot_json TEXT,
            remote_snapshot_json TEXT,
            is_resolved INTEGER DEFAULT 0,
            resolution TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            resolved_at TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fired_alarms (
            task_id INTEGER,
            offset_mins INTEGER,
            fired_at TEXT DEFAULT (datetime('now', 'localtime')),
            PRIMARY KEY (task_id, offset_mins),
            FOREIGN KEY (task_id) REFERENCES unified_task(id) ON DELETE CASCADE
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS gcal_subscription (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            calendar_id TEXT NOT NULL UNIQUE,
            summary TEXT,
            time_zone TEXT,
            access_role TEXT,
            is_active INTEGER DEFAULT 1,
            is_primary INTEGER DEFAULT 0,
            is_external INTEGER DEFAULT 1,
            last_error TEXT,
            last_seen_at TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
        """
    )

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS calendar (
            id               TEXT PRIMARY KEY,
            type             TEXT NOT NULL DEFAULT 'local',
            name             TEXT NOT NULL,
            color            TEXT NOT NULL DEFAULT '{DEFAULT_CALENDAR_COLOR}',
            is_default       INTEGER DEFAULT 0,
            is_active        INTEGER DEFAULT 1,
            is_visible       INTEGER DEFAULT 1,
            gcal_calendar_id TEXT,
            ics_url          TEXT,
            ics_last_fetched TEXT,
            sort_order       INTEGER DEFAULT 0,
            created_at       TEXT DEFAULT (datetime('now', 'localtime'))
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS task_directive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            details TEXT,
            requester TEXT,
            receiver_name TEXT,
            deadline TEXT,
            status TEXT DEFAULT 'in_progress',
            bg_color TEXT,
            memo TEXT,
            priority TEXT DEFAULT 'normal'
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS routine_template (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            cycle_type TEXT NOT NULL,
            description TEXT,
            is_active INTEGER DEFAULT 1,
            priority TEXT DEFAULT 'normal',
            icon TEXT,
            bg_color TEXT,
            alarm_time TEXT,
            location TEXT,
            assignee TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS template_step (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id INTEGER NOT NULL,
            step_name TEXT NOT NULL,
            step_order INTEGER DEFAULT 0,
            FOREIGN KEY (template_id) REFERENCES routine_template(id) ON DELETE CASCADE
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS checklist_template (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            category TEXT,
            checklist_type TEXT DEFAULT 'list',
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS checklist_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            checklist_id INTEGER NOT NULL,
            item_text TEXT NOT NULL,
            item_description TEXT,
            item_guide TEXT,
            item_order INTEGER DEFAULT 0,
            is_required INTEGER DEFAULT 0,
            FOREIGN KEY (checklist_id) REFERENCES checklist_template(id) ON DELETE CASCADE
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS task_checklist_link (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_type TEXT NOT NULL,
            owner_id INTEGER NOT NULL,
            item_text TEXT NOT NULL,
            item_order INTEGER DEFAULT 0,
            display_type TEXT DEFAULT 'list',
            is_completed INTEGER DEFAULT 0,
            completed_at TEXT
        )
        """
    )

    cur.execute(
        f"""
        INSERT OR IGNORE INTO calendar (
            id,
            type,
            name,
            color,
            is_default,
            is_active,
            is_visible,
            sort_order
        )
        VALUES ('local::기본', 'local', '기본', '{DEFAULT_CALENDAR_COLOR}', 1, 1, 1, 0)
        """
    )

    conn.commit()
    conn.close()

    size_kb = target_path.stat().st_size / 1024
    print(f"   created: {target_path} ({size_kb:.1f} KB)")
    return target_path


def clean_sensitive_files(dist_dir: str | Path | None = None) -> int:
    """Remove packaged runtime data that should never ship."""
    target_dir = _resolve_dist_dir(dist_dir)
    print(f"[3/4] removing sensitive files from {target_dir}")

    removed = 0
    for pattern in SENSITIVE_PATTERNS:
        target = target_dir / pattern
        if target.exists():
            target.unlink()
            print(f"   removed: {pattern}")
            removed += 1

    if removed == 0:
        print("   no sensitive runtime files found")
    return removed


def run_pyinstaller() -> bool:
    """Run the historical single-folder Store build."""
    print("[2/4] running PyInstaller")
    spec_file = ROOT / "DarkCalendar.spec"

    if not spec_file.exists():
        print(f"   spec file not found: {spec_file}")
        return False

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        str(spec_file),
    ]

    print(f"   running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print(f"   PyInstaller failed (exit code: {result.returncode})")
        return False

    print("   PyInstaller completed")
    return True


def copy_default_db_to_dist(dist_dir: str | Path | None = None) -> bool:
    """Copy the clean DB to the path used by a frozen app at runtime."""
    target_dir = _resolve_dist_dir(dist_dir)
    print(f"[4/4] copying {DEFAULT_DB_NAME} into {target_dir}")
    if not target_dir.exists():
        print(f"   target directory does not exist: {target_dir}")
        return False

    internal_dir = target_dir / "_internal"
    dest_dir = internal_dir if internal_dir.is_dir() else target_dir
    dest = dest_dir / DEFAULT_DB_NAME
    shutil.copy2(str(DEFAULT_DB_PATH), str(dest))
    print(f"   copied: {dest}")

    stale_root_copy = target_dir / DEFAULT_DB_NAME
    if dest_dir != target_dir and stale_root_copy.exists():
        stale_root_copy.unlink()
        print(f"   removed stale root copy: {stale_root_copy}")
    return True


def prepare_store_payload(dist_dir: str | Path | None = None) -> Path:
    """Prepare a clean payload directory for Store packaging."""
    target_dir = _resolve_dist_dir(dist_dir)
    if target_dir.exists():
        clean_sensitive_files(target_dir)
        internal_dir = target_dir / "_internal"
        runtime_dir = internal_dir if internal_dir.is_dir() else target_dir
        create_clean_default_db(runtime_dir / DEFAULT_DB_NAME)
        stale_root_copy = target_dir / DEFAULT_DB_NAME
        if runtime_dir != target_dir and stale_root_copy.exists():
            stale_root_copy.unlink()
            print(f"   removed stale root copy: {stale_root_copy}")
    else:
        print(f"[payload] target directory not found, skipping payload preparation: {target_dir}")
    return target_dir


def show_summary(dist_dir: str | Path | None = None) -> None:
    from calendar_app.app_metadata import APP_VERSION_DISPLAY

    target_dir = _resolve_dist_dir(dist_dir)
    print("\n" + "=" * 60)
    print(f"  Dark Calendar {APP_VERSION_DISPLAY} Store payload ready")
    print("=" * 60)
    print(f"  output: {target_dir}")
    print(f"  bundled DB: {DEFAULT_DB_NAME} (clean)")
    print("  local DB/log files: removed from payload")
    print("  Google credentials/token files: removed from payload")
    print("=" * 60)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or sanitize a Store payload.")
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Only create the clean DB and sanitize/copy into --dist-dir.",
    )
    parser.add_argument(
        "--dist-dir",
        default=str(DIST_DIR),
        help="Target payload directory for sanitization/copy.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_dir = _resolve_dist_dir(args.dist_dir)

    print("=" * 60)
    print("  Dark Calendar Store payload build")
    print("=" * 60)
    print()

    if args.prepare_only:
        prepare_store_payload(target_dir)
        show_summary(target_dir)
        return 0

    if not run_pyinstaller():
        print("\nBuild aborted.")
        return 1

    prepare_store_payload(target_dir)
    show_summary(target_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
