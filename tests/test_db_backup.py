# -*- coding: utf-8 -*-
"""Daily snapshots stay verified and restore keeps the damaged original."""

from datetime import datetime, timedelta
import sqlite3

import pytest

from calendar_app.infrastructure.db import db_backup

NOW = datetime(2026, 11, 9, 12, 0, 0)


def _make_database(path, rows=3000):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT)")
    conn.executemany(
        "INSERT INTO tasks (title) VALUES (?)", [(f"task {i} " + "x" * 120,) for i in range(rows)]
    )
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()


def _truncate(path, keep_fraction=0.4):
    data = path.read_bytes()
    page_size = int.from_bytes(data[16:18], "big")
    keep = max(2, int(len(data) // page_size * keep_fraction)) * page_size
    path.write_bytes(data[:keep])


def _count(path):
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        return conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    finally:
        conn.close()


def test_snapshot_is_standalone_verified_copy_of_live_wal_database(tmp_path):
    db = tmp_path / "desk_calendar.db"
    _make_database(db)
    writer = sqlite3.connect(db)
    writer.execute("INSERT INTO tasks (title) VALUES ('only in wal')")
    writer.commit()  # stays in the WAL while the app keeps its connection open
    try:
        snapshot = db_backup.create_daily_backup(db, now=NOW)
    finally:
        writer.close()

    assert snapshot == tmp_path / "backups" / "desk_calendar-20261109-120000.db"
    assert _count(snapshot) == 3001
    header = snapshot.read_bytes()[18:20]
    assert header == b"\x01\x01"  # rollback journal: no WAL companion needed
    assert not list((tmp_path / "backups").glob("*.partial"))


def test_snapshot_runs_once_per_interval_and_rotates_old_copies(tmp_path):
    db = tmp_path / "desk_calendar.db"
    _make_database(db, rows=10)

    assert db_backup.create_daily_backup(db, now=NOW) is not None
    assert db_backup.create_daily_backup(db, now=NOW + timedelta(hours=19)) is None
    for day in range(1, 10):
        assert db_backup.create_daily_backup(db, now=NOW + timedelta(days=day), keep=3)

    names = [path.name for _stamp, path in db_backup.list_backups(db)]
    assert names == [
        "desk_calendar-20261118-120000.db",
        "desk_calendar-20261117-120000.db",
        "desk_calendar-20261116-120000.db",
    ]


def test_missing_database_is_not_snapshotted(tmp_path):
    assert db_backup.create_daily_backup(tmp_path / "desk_calendar.db", now=NOW) is None
    assert not (tmp_path / "backups").exists()


def test_damaged_source_never_replaces_good_snapshots(tmp_path):
    db = tmp_path / "desk_calendar.db"
    _make_database(db)
    good = db_backup.create_daily_backup(db, now=NOW)
    _truncate(db)

    with pytest.raises(sqlite3.DatabaseError):
        db_backup.create_daily_backup(db, now=NOW + timedelta(days=1), keep=1)

    assert [path for _stamp, path in db_backup.list_backups(db)] == [good]
    assert not list((tmp_path / "backups").glob("*.partial"))


def test_restore_replaces_truncated_database_and_keeps_damaged_files(tmp_path):
    db = tmp_path / "desk_calendar.db"
    _make_database(db)
    db_backup.create_daily_backup(db, now=NOW)
    _truncate(db)
    damaged = db.read_bytes()
    (tmp_path / "desk_calendar.db-wal").write_bytes(b"stale wal")
    (tmp_path / "desk_calendar.db-shm").write_bytes(b"stale shm")

    used = db_backup.restore_latest_backup(db, now=NOW + timedelta(hours=1))

    assert used.name == "desk_calendar-20261109-120000.db"
    assert _count(db) == 3000
    assert not (tmp_path / "desk_calendar.db-wal").exists()
    assert not (tmp_path / "desk_calendar.db-shm").exists()
    kept = tmp_path / "desk_calendar.db.corrupt-20261109-130000"
    assert kept.read_bytes() == damaged
    assert (tmp_path / "desk_calendar.db.corrupt-20261109-130000-wal").read_bytes() == b"stale wal"
    assert (tmp_path / "desk_calendar.db.corrupt-20261109-130000-shm").read_bytes() == b"stale shm"
    assert not (tmp_path / "desk_calendar.db.restoring").exists()


def test_restore_skips_damaged_newest_snapshot(tmp_path):
    db = tmp_path / "desk_calendar.db"
    _make_database(db)
    older = db_backup.create_daily_backup(db, now=NOW)
    newer = db_backup.create_daily_backup(db, now=NOW + timedelta(days=1))
    _truncate(newer)
    _truncate(db)

    assert db_backup.find_restorable_backup(db) == older
    assert db_backup.restore_latest_backup(db, now=NOW + timedelta(days=2)) == older
    assert _count(db) == 3000


@pytest.mark.parametrize("failed_source", ["desk_calendar.db-shm", "desk_calendar.db.restoring"])
def test_failed_restore_puts_original_files_back(tmp_path, monkeypatch, failed_source):
    db = tmp_path / "desk_calendar.db"
    _make_database(db)
    snapshot = db_backup.create_daily_backup(db, now=NOW)
    _truncate(db)
    wal = db.with_name(db.name + "-wal")
    shm = db.with_name(db.name + "-shm")
    wal.write_bytes(b"original wal")
    shm.write_bytes(b"original shm")
    originals = {path: path.read_bytes() for path in (db, wal, shm)}
    replace = db_backup.os.replace

    def fail_one_move(source, destination):
        if source.name == failed_source:
            raise PermissionError("simulated file lock")
        return replace(source, destination)

    monkeypatch.setattr(db_backup.os, "replace", fail_one_move)
    with pytest.raises(PermissionError, match="simulated file lock"):
        db_backup.restore_latest_backup(db, now=NOW)

    assert {path: path.read_bytes() for path in originals} == originals
    assert _count(snapshot) == 3000
    assert not list(tmp_path.glob("*.corrupt-*"))
    assert not list(tmp_path.glob("*.restoring"))


def test_restore_keeps_an_earlier_archive_with_the_same_timestamp(tmp_path):
    db = tmp_path / "desk_calendar.db"
    _make_database(db)
    db_backup.create_daily_backup(db, now=NOW)
    _truncate(db)
    damaged = db.read_bytes()
    earlier = tmp_path / "desk_calendar.db.corrupt-20261109-120000"
    earlier.write_bytes(b"previous recovery attempt")

    assert db_backup.restore_latest_backup(db, now=NOW)

    assert earlier.read_bytes() == b"previous recovery attempt"
    assert (tmp_path / (earlier.name + "-1")).read_bytes() == damaged
    assert _count(db) == 3000


def test_restore_without_usable_snapshot_changes_nothing(tmp_path):
    db = tmp_path / "desk_calendar.db"
    _make_database(db)
    _truncate(db)
    damaged = db.read_bytes()

    assert db_backup.find_restorable_backup(db) is None
    assert db_backup.restore_latest_backup(db, now=NOW) is None
    assert db.read_bytes() == damaged
    assert sorted(path.name for path in tmp_path.iterdir()) == ["desk_calendar.db"]
