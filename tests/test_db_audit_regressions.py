# -*- coding: utf-8 -*-
"""Regressions found by the 2026-11-13 repository audit (DB layer)."""

import os
import sqlite3
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from calendar_app.infrastructure.db import database_unified


class _TempDbCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database_unified.DB_PATH
        database_unified.db_manager.close_all_connections()
        self.db_path = os.path.join(self._tmpdir.name, "audit.db")
        database_unified.DB_PATH = self.db_path

    def tearDown(self):
        database_unified.db_manager.close_all_connections()
        database_unified.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()
        super().tearDown()

    def _init(self):
        database_unified.db_manager.close_all_connections()
        database_unified.initialize_unified_database(raise_on_error=True)
        database_unified.db_manager.close_all_connections()

    def _query(self, sql, params=()):
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def _execute(self, sql, params=()):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(sql, params)
            conn.commit()
        finally:
            conn.close()


class LegacyTableMigrationTests(_TempDbCase):
    def test_legacy_tables_are_copied_once(self):
        self._execute("CREATE TABLE special_task (id INTEGER PRIMARY KEY, name TEXT)")
        self._execute("INSERT INTO special_task (id, name) VALUES (1, 'Old schedule')")
        self._execute(
            "CREATE TABLE routine_task (id INTEGER PRIMARY KEY, name TEXT, deadline TEXT)"
        )
        self._execute(
            "INSERT INTO routine_task (id, name, deadline) VALUES (1, 'Old routine', '2026-01-02')"
        )

        self._init()
        first = self._query("SELECT name, type FROM unified_task ORDER BY id")
        self._execute("DELETE FROM unified_task WHERE name = 'Old schedule'")
        self._init()
        self._init()

        self.assertIn(("Old routine", "routine"), first)
        self.assertIn(("Old schedule", "schedule"), first)
        self.assertEqual(
            self._query("SELECT name FROM unified_task ORDER BY id"), [("Old routine",)]
        )
        tables = {
            row[0] for row in self._query("SELECT name FROM sqlite_master WHERE type='table'")
        }
        self.assertNotIn("routine_task", tables)
        self.assertNotIn("special_task", tables)


class GoogleImportSelectionStartupTests(_TempDbCase):
    def test_restart_keeps_unchecked_writable_google_calendar_inactive(self):
        self._init()
        self._execute(
            "INSERT INTO calendar (id, type, name, color, is_active, gcal_calendar_id, access_role) "
            "VALUES ('gcal::work', 'gcal', 'Work', '#4285f4', 0, 'work@example.com', 'owner')"
        )

        self._init()

        self.assertEqual(
            self._query("SELECT is_active FROM calendar WHERE id = 'gcal::work'"), [(0,)]
        )


class TrashRestoreTests(_TempDbCase):
    def test_restore_keeps_calendar_and_tags(self):
        from calendar_app.infrastructure.db import db_repository_unified as task_repo

        self._init()
        self._execute(
            "INSERT INTO calendar (id, type, name, color) VALUES ('local::x', 'local', 'X', '#123456')"
        )
        task_id = task_repo.create_unified_task(
            {
                "name": "Keep me",
                "type": "schedule",
                "deadline": "2026-11-13 09:00:00",
                "calendar_id": "local::x",
                "tags": "t1",
            }
        )
        self.assertTrue(task_repo.move_task_to_trash(task_id, reason="test"))
        archive_id = task_repo.list_task_trash()[0]["id"]

        restored = task_repo.get_unified_task(task_repo.restore_task_from_trash(archive_id))

        self.assertEqual(restored["calendar_id"], "local::x")
        self.assertEqual(restored["tags"], "t1")


class FocusQueryTests(_TempDbCase):
    def test_focus_queries_rank_priority_and_list_each_task_once(self):
        from calendar_app.infrastructure.db import db_repository

        self._init()
        for name, priority in (("Normal one", "normal"), ("High one", "high"), ("Low one", "low")):
            self._execute(
                "INSERT INTO unified_task (name, type, priority, status, deadline, is_completed) "
                "VALUES (?, 'schedule', ?, 'pending', '2026-11-13 09:00:00', 0)",
                (name, priority),
            )

        task_id, task_name = db_repository.get_most_urgent_pending_task("2026-11-13")
        names = [task["name"] for task in db_repository.get_incomplete_tasks()]

        self.assertEqual(task_name, "High one")
        self.assertEqual(names, ["High one", "Normal one", "Low one"])


if __name__ == "__main__":
    unittest.main()
