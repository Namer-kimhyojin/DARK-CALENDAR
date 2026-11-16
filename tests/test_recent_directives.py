# -*- coding: utf-8 -*-
"""get_recent_directives() must not cut unfinished directives behind old completed ones.

Completed directives are never purged. The old query sorted every row by deadline and kept
the first 200, so once 200 older completed rows existed today's, overdue and undated
directives fell off the end: the right panel, the widget, the palette and the overlay
{directive_count} all lost them. Every unfinished directive now loads, plus the ``limit``
finished ones with the latest deadlines.
"""

from types import SimpleNamespace

from PyQt6.QtCore import QDate
import pytest

from calendar_app.infrastructure.db import database_unified, db_repository


@pytest.fixture
def temp_db(tmp_path):
    original = database_unified.DB_PATH
    database_unified.db_manager.close_all_connections()
    database_unified.DB_PATH = str(tmp_path / "test.db")
    database_unified.initialize_unified_database()
    try:
        yield db_repository.get_connection()
    finally:
        database_unified.db_manager.close_all_connections()
        database_unified.DB_PATH = original


def _insert(conn, content, status, deadline):
    cur = conn.execute(
        "INSERT INTO task_directive (content, status, deadline) VALUES (?, ?, ?)",
        (content, status, deadline),
    )
    return cur.lastrowid


def _day(offset):
    return QDate.currentDate().addDays(offset).toString("yyyy-MM-dd")


def test_every_unfinished_directive_loads_past_the_finished_limit(temp_db):
    conn = temp_db
    finished = [_insert(conn, f"old {i}", "completed", _day(-900 + i)) for i in range(250)]
    unfinished = {
        _insert(conn, "today", "pending", _day(0) + " 09:00"),
        _insert(conn, "overdue", "in_progress", _day(-2)),
        _insert(conn, "on hold", "deferred", _day(-2000)),
        _insert(conn, "no status", None, _day(-1500)),
        _insert(conn, "undated", "pending", None),
        _insert(conn, "cleared deadline", "pending", ""),
    }
    legacy_done = _insert(conn, "legacy done", "done", _day(-1))
    conn.commit()

    rows = db_repository.get_recent_directives(limit=200)

    ids = [row[0] for row in rows]
    assert unfinished <= set(ids)
    # The 200 finished rows with the latest deadlines: the legacy 'done' row and old 51..249.
    assert set(ids) - unfinished == {legacy_done, *finished[51:]}
    assert len(ids) == len(set(ids)) == len(unfinished) + 200
    keys = [(row[4] if row[4] is not None else "9999-12-31", -row[0]) for row in rows]
    assert keys == sorted(keys)
    assert all(len(tuple(row)) == 7 for row in rows)


def test_only_the_most_recent_finished_directives_load(temp_db):
    conn = temp_db
    undated_done = _insert(conn, "undated done", "completed", None)
    old_done = _insert(conn, "old done", "completed", _day(-30))
    new_done = _insert(conn, "new done", "completed", _day(-1))
    early_done = _insert(conn, "done early", "completed", _day(5))
    conn.commit()

    assert [row[0] for row in db_repository.get_recent_directives(limit=2)] == [
        new_done,
        early_done,
    ]
    assert [row[0] for row in db_repository.get_recent_directives(limit=10)] == [
        old_done,
        new_done,
        early_done,
        undated_done,
    ]


def test_widget_data_lists_todays_directive_behind_old_completed_ones(temp_db):
    from calendar_app.presentation.panels import side_panel_renderer

    conn = temp_db
    for i in range(250):
        _insert(conn, f"old {i}", "completed", _day(-900 + i))
    today_id = _insert(conn, "today", "pending", _day(0))
    conn.commit()
    app = SimpleNamespace(current_date=QDate.currentDate())

    side_panel_renderer.publish_right_panel_data(app)

    assert today_id in {row[0] for row in app._latest_directive_data["directive_rows"]}
