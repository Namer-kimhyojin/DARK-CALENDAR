import sqlite3

from calendar_app.infrastructure.db import database_unified, db_repository, directive_repo
from tests.support import TemporaryDatabaseTestCase


class DirectiveSchemaCompatibilityTests(TemporaryDatabaseTestCase):
    def test_initialize_unified_database_adds_receiver_name_and_backfills_legacy_data(self):
        conn = database_unified.db_manager.get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO task_directive (content, requester, details, deadline, status, bg_color) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "Legacy directive",
                "Alice",
                "Legacy memo",
                "2026-03-18 09:00",
                "in_progress",
                "#112233",
            ),
        )
        conn.commit()

        database_unified.initialize_unified_database()

        cur = conn.cursor()
        cur.execute("PRAGMA table_info(task_directive)")
        columns = {row[1] for row in cur.fetchall()}
        self.assertIn("receiver_name", columns)
        self.assertIn("memo", columns)
        self.assertIn("priority", columns)

        cur.execute(
            "SELECT receiver_name, memo FROM task_directive WHERE content='Legacy directive'"
        )
        receiver_name, memo = cur.fetchone()
        self.assertEqual(receiver_name, "Alice")
        self.assertEqual(memo, "Legacy memo")

    def test_get_recent_directives_reads_legacy_requester_schema(self):
        conn = database_unified.db_manager.get_connection()
        cur = conn.cursor()
        cur.execute("DROP TABLE task_directive")
        cur.execute(
            """
            CREATE TABLE task_directive (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                details TEXT,
                requester TEXT,
                deadline TEXT,
                status TEXT DEFAULT 'in_progress',
                bg_color TEXT
            )
            """
        )
        cur.execute(
            "INSERT INTO task_directive (content, details, requester, deadline, status, bg_color) VALUES (?, ?, ?, ?, ?, ?)",
            ("Old schema", "Detail memo", "Bob", "2026-03-18 11:00", "in_progress", "#445566"),
        )
        conn.commit()

        rows = db_repository.get_recent_directives(limit=10)

        self.assertEqual(len(rows), 1)
        directive_id, content, status, receiver_name, deadline, memo, bg_color = rows[0]
        self.assertIsNotNone(directive_id)
        self.assertEqual(content, "Old schema")
        self.assertEqual(status, "in_progress")
        self.assertEqual(receiver_name, "Bob")
        self.assertEqual(deadline, "2026-03-18 11:00")
        self.assertEqual(memo, "Detail memo")
        self.assertEqual(bg_color, "#445566")

    def test_directive_repo_ensure_schema_allows_receiver_name_queries(self):
        conn = database_unified.db_manager.get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO task_directive (content, requester, deadline, status) VALUES (?, ?, ?, ?)",
            (
                "Needs migration",
                "Chris",
                "2026-03-18 12:00",
                "in_progress",
            ),
        )
        conn.commit()

        rows = directive_repo.get_all_directives_for_management()

        self.assertEqual(len(rows), 1)
        _id, content, receiver_name, priority, deadline, status = rows[0]
        self.assertEqual(content, "Needs migration")
        self.assertEqual(receiver_name, "Chris")
        self.assertEqual(priority, "normal")
        self.assertEqual(deadline, "2026-03-18 12:00")
        self.assertEqual(status, "in_progress")

    def test_get_directives_by_date_returns_normalized_dict_rows(self):
        conn = database_unified.db_manager.get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO task_directive (content, requester, details, deadline, status, bg_color) VALUES (?, ?, ?, ?, ?, ?)",
            ("Date query", "Dana", "Memo text", "2026-03-18 14:30", "pending", "#123456"),
        )
        conn.commit()

        rows = directive_repo.get_directives_by_date("2026-03-18")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["content"], "Date query")
        self.assertEqual(rows[0]["receiver_name"], "Dana")
        self.assertEqual(rows[0]["memo"], "Memo text")
        self.assertEqual(rows[0]["priority"], "normal")
