# -*- coding: utf-8 -*-
"""Verified daily snapshots of the personal database and restore after corruption.

Snapshots use SQLite's online backup API, which is consistent while the app writes
in WAL mode. A snapshot is kept only when the copy passes ``PRAGMA quick_check``, so
a damaged source never rotates good snapshots out. Restore never deletes data: the
damaged file and its WAL/SHM companions are renamed aside before a verified copy
takes their place.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta
import logging
import os
from pathlib import Path
import re
import sqlite3

logger = logging.getLogger(__name__)

BACKUP_DIR_NAME = "backups"
KEEP_COUNT = 7
MIN_INTERVAL = timedelta(hours=20)
_STAMP_FORMAT = "%Y%m%d-%H%M%S"
# A stale WAL applied to a restored file would corrupt it again, so companions
# always move together with the damaged database.
_COMPANION_SUFFIXES = ("-wal", "-shm", "-journal")


def backup_dir(db_path) -> Path:
    return Path(db_path).parent / BACKUP_DIR_NAME


def list_backups(db_path) -> list[tuple[datetime, Path]]:
    """Return snapshots newest first, ordered by the timestamp in their name."""
    pattern = re.compile(rf"^{re.escape(Path(db_path).stem)}-(\d{{8}}-\d{{6}})\.db$")
    try:
        entries = list(backup_dir(db_path).iterdir())
    except OSError:
        return []
    found = []
    for entry in entries:
        match = pattern.match(entry.name)
        if match is None:
            continue
        try:
            stamp = datetime.strptime(match.group(1), _STAMP_FORMAT)
        except ValueError:
            continue
        if entry.is_file():
            found.append((stamp, entry))
    found.sort(key=lambda item: item[0], reverse=True)
    return found


def _passes_quick_check(path: Path) -> bool:
    try:
        conn = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error:
        return False
    try:
        return conn.execute("PRAGMA quick_check").fetchall() == [("ok",)]
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def _copy_verified(source: Path, target: Path) -> None:
    """Atomically write a self-contained copy of ``source`` that passed quick_check."""
    if not source.is_file():
        raise FileNotFoundError(2, "Database snapshot source is missing", str(source))
    partial = target.with_name(target.name + ".partial")
    with contextlib.suppress(FileNotFoundError):
        partial.unlink()
    try:
        src = sqlite3.connect(str(source), timeout=5)
        try:
            dst = sqlite3.connect(str(partial))
            try:
                src.backup(dst)
                # The copy carries the source's WAL flag; a standalone file must not
                # depend on companion files that are never copied with it.
                dst.execute("PRAGMA journal_mode = DELETE")
                verified = dst.execute("PRAGMA quick_check").fetchall() == [("ok",)]
            finally:
                dst.close()
        finally:
            src.close()
        if not verified:
            raise sqlite3.DatabaseError("Database snapshot failed its integrity check")
        os.replace(partial, target)
    except BaseException:
        with contextlib.suppress(OSError):
            partial.unlink()
        raise


def create_daily_backup(
    db_path, *, now: datetime | None = None, keep: int = KEEP_COUNT, min_interval=MIN_INTERVAL
) -> Path | None:
    """Save a verified snapshot unless a recent one exists; return its path."""
    db_path = Path(db_path)
    if not db_path.is_file():
        return None
    now = now or datetime.now()
    existing = list_backups(db_path)
    if existing and timedelta(0) <= now - existing[0][0] < min_interval:
        return None
    directory = backup_dir(db_path)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{db_path.stem}-{now.strftime(_STAMP_FORMAT)}.db"
    _copy_verified(db_path, target)
    for _stamp, stale in list_backups(db_path)[max(1, keep) :]:
        with contextlib.suppress(OSError):
            stale.unlink()
    logger.info("Database snapshot saved: %s", target.name)
    return target


def find_restorable_backup(db_path) -> Path | None:
    """Return the newest snapshot that still passes quick_check."""
    for _stamp, candidate in list_backups(db_path):
        if _passes_quick_check(candidate):
            return candidate
    return None


def restore_latest_backup(db_path, *, now: datetime | None = None) -> Path | None:
    """Replace a damaged database with the newest verified snapshot.

    The damaged database and its companions are kept as ``<name>.corrupt-<stamp>``,
    with a numeric suffix if that archive name is already in use.
    Returns the snapshot used, or ``None`` when no usable snapshot exists. All
    database connections to ``db_path`` must be closed by the caller.
    """
    db_path = Path(db_path)
    candidate = find_restorable_backup(db_path)
    if candidate is None:
        return None
    staged = db_path.with_name(db_path.name + ".restoring")
    _copy_verified(candidate, staged)
    stamp = (now or datetime.now()).strftime(_STAMP_FORMAT)
    archive_base = db_path.with_name(f"{db_path.name}.corrupt-{stamp}")
    archive = archive_base
    suffixes = (*_COMPANION_SUFFIXES, "")
    moved: list[tuple[Path, Path]] = []
    try:
        sequence = 1
        while any(Path(f"{archive}{suffix}").exists() for suffix in suffixes):
            archive = archive_base.with_name(f"{archive_base.name}-{sequence}")
            sequence += 1
        # Keep the old companions away from the new database.
        for suffix in suffixes:
            current = Path(f"{db_path}{suffix}")
            if current.exists():
                archived = Path(f"{archive}{suffix}")
                os.replace(current, archived)
                moved.append((current, archived))
        os.replace(staged, db_path)
    except BaseException:
        for current, archived in reversed(moved):
            try:
                if current.exists():
                    logger.error("Restore rollback kept %s because %s exists", archived, current)
                else:
                    os.replace(archived, current)
            except OSError:
                logger.exception("Restore rollback could not return %s to %s", archived, current)
        with contextlib.suppress(OSError):
            staged.unlink()
        raise
    logger.warning(
        "Database restored from snapshot %s; damaged file kept as %s",
        candidate.name,
        archive.name,
    )
    return candidate
