# -*- coding: utf-8 -*-
"""With "완료 포함" on, a work item completed today stays listed, checked, for the rest of the day.

Completing an overdue or undated directive dropped it from the widget at once: the overdue
and no-deadline sections skipped every completed row. A routine listed on its due date (its
period end, with another target date) vanished at the next republish, because the widget
data only carried the open routines of other days. task_directive.completed_at now records
when a directive was completed; routines use unified_task.completed_at. Only items completed
that day come back, never older completions.
"""

import os
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate
import pytest

from tests.test_widget_completion_refresh import (  # noqa: F401  (fixtures)
    _add_directive,
    _add_routine,
    _enter_with,
    _pump,
    _routine_texts,
    _widget_item,
    temp_db,
    widget_session,
)


def _conn():
    from calendar_app.infrastructure.db import db_repository_unified as unified_repo

    return unified_repo.get_connection()


def _today():
    return QDate.currentDate().toString("yyyy-MM-dd")


def _day(offset):
    return QDate.currentDate().addDays(offset).toString("yyyy-MM-dd")


def _listed(controller, source, item_id):
    return any(
        item.get("source") == source and item.get("item_id") == item_id
        for item in controller.widget._last_items
    )


def _completed_at(directive_id):
    row = (
        _conn()
        .execute("SELECT completed_at FROM task_directive WHERE id=?", (directive_id,))
        .fetchone()
    )
    return row[0]


def _set_completed_at(table, row_id, value):
    _conn().execute(f"UPDATE {table} SET completed_at=? WHERE id=?", (value, row_id))
    _conn().commit()


def _add_undated_directive(content, status):
    cur = _conn().execute(
        "INSERT INTO task_directive (content, status) VALUES (?, ?)", (content, status)
    )
    _conn().commit()
    return cur.lastrowid


# --------------------------------------------------------------------------- directive data


def test_database_initialization_adds_completed_at_and_its_index(temp_db):
    cur = _conn().cursor()
    columns = {row[1] for row in cur.execute("PRAGMA table_info(task_directive)").fetchall()}
    indexes = {row[1] for row in cur.execute("PRAGMA index_list('task_directive')").fetchall()}
    assert "completed_at" in columns
    assert "idx_task_directive_status_completed_at" in indexes


def test_directive_status_writes_stamp_keep_and_clear_completed_at(temp_db):
    from calendar_app.infrastructure.db import directive_repo

    first = _add_directive("a", QDate.currentDate().addDays(-2), "pending")
    second = _add_directive("b", QDate.currentDate().addDays(-2), "pending")
    assert directive_repo.update_directive_status(first, "completed")
    stamped = _completed_at(first)
    assert stamped and stamped[:10] == _today()

    _set_completed_at("task_directive", first, "2000-01-01 09:00:00")
    assert directive_repo.update_directive_status(first, "completed")
    assert _completed_at(first) == "2000-01-01 09:00:00"  # still completed: kept
    assert directive_repo.update_directive_status(first, "pending")
    assert _completed_at(first) is None

    assert directive_repo.bulk_update_directive_status([first, second], "completed") == 2
    assert directive_repo.directive_ids_completed_on(_today()) == {first, second}
    assert directive_repo.bulk_update_directive_status([second], "in_progress") == 1
    assert _completed_at(second) is None
    assert directive_repo.directive_ids_completed_on(_today()) == {first}
    assert directive_repo.directive_ids_completed_on("2000-01-01") == set()


def test_status_write_adds_a_missing_completed_at_column(temp_db):
    from calendar_app.infrastructure.db import directive_repo

    directive_id = _add_directive("a", QDate.currentDate(), "pending")
    _conn().execute("DROP INDEX idx_task_directive_status_completed_at")
    _conn().execute("ALTER TABLE task_directive DROP COLUMN completed_at")
    _conn().commit()

    assert directive_repo.update_directive_status(directive_id, "completed")
    assert _completed_at(directive_id)[:10] == _today()


def test_directive_dialog_saves_stamp_keep_and_clear_completed_at(temp_db, monkeypatch):
    from calendar_app.infrastructure.db import database_unified
    from calendar_app.presentation.dialogs import directive_dialog

    _conn()  # the app's own connection opens before connections are tracked below
    opened = []
    real_connect = sqlite3.connect

    def tracked_connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    def save(task_id, status, content="report"):
        dialog = directive_dialog.DirectiveDialog(task_id=task_id)
        try:
            dialog.content_edit.setText(content)
            dialog.status_combo.setCurrentIndex(dialog.status_combo.findData(status))
            dialog.save_data()
        finally:
            dialog.deleteLater()
            _pump()

    def fail_on_error_box(_parent, _title, text, *_args, **_kwargs):
        raise AssertionError(f"save failed: {text}")  # a modal box would block the run

    with monkeypatch.context() as patched:
        patched.setattr(directive_dialog, "DB_PATH", database_unified.DB_PATH)
        patched.setattr(directive_dialog.QMessageBox, "critical", fail_on_error_box)
        patched.setattr(sqlite3, "connect", tracked_connect)
        try:
            save(None, "completed", "created done")
            save(None, "pending", "created open")
            done_id, open_id = (
                row[0] for row in _conn().execute("SELECT id FROM task_directive ORDER BY id")
            )
            assert _completed_at(done_id)[:10] == _today()
            assert _completed_at(open_id) is None

            save(open_id, "completed")
            assert _completed_at(open_id)[:10] == _today()
            _set_completed_at("task_directive", open_id, "2000-01-01 09:00:00")
            save(open_id, "completed")  # edited while completed: the time is kept
            assert _completed_at(open_id) == "2000-01-01 09:00:00"
            save(open_id, "in_progress")
            assert _completed_at(open_id) is None

            _set_completed_at("task_directive", done_id, None)
            save(done_id, "completed")  # legacy row: completion time unknown, stays NULL
            assert _completed_at(done_id) is None
        finally:
            for connection in opened:
                connection.close()


def test_recent_directives_keep_directives_completed_today_past_the_finished_limit(temp_db):
    from calendar_app.infrastructure.db import db_repository, directive_repo

    for i in range(250):
        _add_directive(f"old {i}", QDate.currentDate().addDays(-300 + i), "completed")
    undated = _add_undated_directive("undated", "pending")
    overdue = _add_directive("long overdue", QDate.currentDate().addDays(-400), "pending")
    earlier = _add_directive("completed earlier", QDate.currentDate().addDays(-400), "completed")
    _set_completed_at("task_directive", earlier, "2000-01-01 09:00:00")
    assert directive_repo.bulk_update_directive_status([undated, overdue], "completed") == 2

    rows = db_repository.get_recent_directives(limit=200)

    ids = {row[0] for row in rows}
    assert {undated, overdue} <= ids
    assert earlier not in ids
    assert len(rows) == 202
    assert all(len(tuple(row)) == 7 for row in rows)


# --------------------------------------------------------------------------- widget


@pytest.mark.parametrize("deadline_days", [-2, None], ids=["overdue", "undated"])
def test_directive_completed_today_stays_checked_in_widget(widget_session, deadline_days):
    host, coordinator = widget_session
    if deadline_days is None:
        directive_id = _add_undated_directive("undated", "pending")
    else:
        directive_id = _add_directive(
            "overdue", QDate.currentDate().addDays(deadline_days), "pending"
        )
    controller = _enter_with(host, coordinator)

    controller.set_item_completed(_widget_item(controller, "directive", directive_id), True)
    assert _widget_item(controller, "directive", directive_id)["completed"] is True
    published = host._latest_directive_data
    _pump(0.3)

    assert host._latest_directive_data is not published  # republished from the database
    assert directive_id in host._latest_directive_data["completed_directive_ids"]
    assert _widget_item(controller, "directive", directive_id)["completed"] is True


def test_widget_keeps_directives_completed_today_behind_many_finished_ones(widget_session):
    from calendar_app.infrastructure.db import directive_repo

    host, coordinator = widget_session
    for i in range(250):
        _add_directive(f"old {i}", QDate.currentDate().addDays(-300 + i), "completed")
    undated = _add_undated_directive("undated", "pending")
    overdue = _add_directive("long overdue", QDate.currentDate().addDays(-400), "pending")
    assert directive_repo.bulk_update_directive_status([undated, overdue], "completed") == 2

    controller = _enter_with(host, coordinator)

    published = {row[0] for row in host._latest_directive_data["directive_rows"]}
    assert {undated, overdue} <= published
    assert _widget_item(controller, "directive", undated)["completed"] is True
    assert _widget_item(controller, "directive", overdue)["completed"] is True


def test_directive_completed_on_another_day_is_not_listed(widget_session):
    host, coordinator = widget_session
    old = _add_directive("old", QDate.currentDate().addDays(-9), "completed")
    _set_completed_at("task_directive", old, "2000-01-01 09:00:00")
    legacy = _add_directive("legacy", QDate.currentDate().addDays(-9), "completed")  # NULL
    controller = _enter_with(host, coordinator)
    assert not _listed(controller, "directive", old)
    assert not _listed(controller, "directive", legacy)


def test_directive_completed_today_is_hidden_without_show_completed(widget_session):
    host, coordinator = widget_session
    host.settings.setValue("widget_mode_show_completed", "false")
    directive_id = _add_directive("overdue", QDate.currentDate().addDays(-2), "pending")
    controller = _enter_with(host, coordinator)
    controller.set_item_completed(_widget_item(controller, "directive", directive_id), True)
    _pump(0.3)
    assert not _listed(controller, "directive", directive_id)


# --------------------------------------------------------------------------- routines


def _routine_due_today(name, status):
    """Listed today by its period end only (target date three days ago)."""
    routine_id = _add_routine(name, QDate.currentDate().addDays(-3), status)
    _conn().execute("UPDATE unified_task SET period_end=? WHERE id=?", (_today(), routine_id))
    _conn().commit()
    return routine_id


def _published_routine_ids(host):
    return {row["id"] for row in host._latest_directive_data["routine_rows"]}


def test_routine_due_today_stays_checked_after_completing_it_today(widget_session):
    host, coordinator = widget_session
    routine_id = _routine_due_today("weekly report", "pending")
    controller = _enter_with(host, coordinator)

    controller.set_item_completed(_widget_item(controller, "task", routine_id), True)
    published = host._latest_directive_data
    _pump(0.3)

    assert host._latest_directive_data is not published
    assert routine_id in _published_routine_ids(host)
    assert _widget_item(controller, "task", routine_id)["completed"] is True


def test_routine_due_on_a_viewed_day_stays_checked_after_completing_it_today(widget_session):
    host, coordinator = widget_session
    routine_id = _add_routine("weekly report", QDate.currentDate().addDays(-3), "pending")
    _conn().execute("UPDATE unified_task SET period_end=? WHERE id=?", (_day(2), routine_id))
    _conn().commit()
    controller = _enter_with(host, coordinator)
    controller.set_target_date(QDate.currentDate().addDays(2))
    _pump(0.3)

    controller.set_item_completed(_widget_item(controller, "task", routine_id), True)
    published = host._latest_directive_data
    _pump(0.3)

    assert host._latest_directive_data is not published
    assert routine_id in _published_routine_ids(host)
    assert _widget_item(controller, "task", routine_id)["completed"] is True


def test_routine_due_today_completed_on_an_earlier_day_is_not_listed(widget_session):
    host, coordinator = widget_session
    routine_id = _routine_due_today("monthly report", "completed")
    _set_completed_at("unified_task", routine_id, _day(-5) + " 09:00:00")
    controller = _enter_with(host, coordinator)
    assert routine_id not in _published_routine_ids(host)
    assert not _listed(controller, "task", routine_id)


def test_main_panel_still_hides_completed_routines_of_other_days(widget_session):
    host, coordinator = widget_session
    _enter_with(host, coordinator)
    coordinator.return_to_main()
    _pump()
    _routine_due_today("weekly report", "completed")  # completed now, due today
    _add_routine("done today", QDate.currentDate(), "completed")
    host.load_right_panel(force=True)
    _pump()
    texts = " | ".join(_routine_texts(host))
    assert "weekly report" not in texts
    assert "done today" in texts


# --------------------------------------------------------------------------- undo of an untick
# Unticking clears completed_at. Undo must put the earlier value back: stamping the undo time
# moved an item completed on another day into today's "완료 포함" list.


def _row(table, row_id):
    return tuple(
        _conn()
        .execute(f"SELECT status, completed_at FROM {table} WHERE id=?", (row_id,))
        .fetchone()
    )


def _untick(controller, source, item_id):
    controller.set_item_completed(_widget_item(controller, source, item_id), False)
    _pump(0.3)


def _view(controller, offset):
    controller.set_target_date(QDate.currentDate().addDays(offset))
    _pump(0.3)


@pytest.mark.parametrize("stamp_day", [-1, None], ids=["earlier_day", "legacy_null"])
def test_undoing_an_untick_keeps_a_directive_completion_time(widget_session, stamp_day):
    host, coordinator = widget_session
    directive_id = _add_directive("report", QDate.currentDate().addDays(-2), "completed")
    stamp = None if stamp_day is None else _day(stamp_day) + " 10:00:00"
    _set_completed_at("task_directive", directive_id, stamp)
    controller = _enter_with(host, coordinator)
    assert not _listed(controller, "directive", directive_id)

    _view(controller, -2)
    _untick(controller, "directive", directive_id)
    assert _row("task_directive", directive_id) == ("pending", None)
    controller.undo_completion()
    _pump(0.3)

    assert _row("task_directive", directive_id) == ("completed", stamp)
    _view(controller, 0)
    assert directive_id not in host._latest_directive_data["completed_directive_ids"]
    assert not _listed(controller, "directive", directive_id)


def test_ticking_again_after_an_untick_counts_as_completed_today(widget_session):
    host, coordinator = widget_session
    directive_id = _add_directive("report", QDate.currentDate().addDays(-2), "completed")
    _set_completed_at("task_directive", directive_id, _day(-1) + " 10:00:00")
    controller = _enter_with(host, coordinator)

    _view(controller, -2)
    _untick(controller, "directive", directive_id)
    controller.set_item_completed(_widget_item(controller, "directive", directive_id), True)
    _pump(0.3)

    status, completed_at = _row("task_directive", directive_id)
    assert status == "completed" and completed_at[:10] == _today()


def test_undoing_an_untick_keeps_a_routine_completion_time(widget_session):
    host, coordinator = widget_session
    routine_id = _routine_due_today("weekly report", "completed")
    stamp = _day(-2) + " 10:00:00"
    _set_completed_at("unified_task", routine_id, stamp)
    controller = _enter_with(host, coordinator)
    assert not _listed(controller, "task", routine_id)

    _view(controller, -3)
    _untick(controller, "task", routine_id)
    assert _row("unified_task", routine_id) == ("in_progress", None)
    controller.undo_completion()
    _pump(0.3)

    assert _row("unified_task", routine_id) == ("completed", stamp)
    _view(controller, 0)
    assert routine_id not in _published_routine_ids(host)
    assert not _listed(controller, "task", routine_id)
