# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

import build_store


class BuildStoreTests(unittest.TestCase):
    def test_prepare_store_payload_removes_runtime_state_and_copies_clean_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            dist_dir = temp_root / "payload"
            dist_dir.mkdir(parents=True, exist_ok=True)
            internal_dir = dist_dir / "_internal"
            internal_dir.mkdir(parents=True, exist_ok=True)

            original_db_path = build_store.DEFAULT_DB_PATH
            try:
                build_store.DEFAULT_DB_PATH = temp_root / build_store.DEFAULT_DB_NAME
                build_store.DEFAULT_DB_PATH.write_bytes(b"source-db-must-not-change")

                for name in build_store.SENSITIVE_PATTERNS:
                    (dist_dir / name).write_text("local-state", encoding="utf-8", errors="strict")

                build_store.prepare_store_payload(dist_dir)

                for name in build_store.SENSITIVE_PATTERNS:
                    self.assertFalse((dist_dir / name).exists(), name)

                bundled_db = internal_dir / build_store.DEFAULT_DB_NAME
                self.assertTrue(bundled_db.exists())
                self.assertFalse((dist_dir / build_store.DEFAULT_DB_NAME).exists())

                conn = sqlite3.connect(str(bundled_db))
                try:
                    cur = conn.cursor()
                    calendar_rows = cur.execute("SELECT id, type, name FROM calendar").fetchall()
                    gcal_subscription_rows = cur.execute(
                        "SELECT COUNT(*) FROM gcal_subscription"
                    ).fetchone()[0]
                finally:
                    conn.close()

                self.assertEqual([("local::기본", "local", "기본")], calendar_rows)
                self.assertEqual(0, gcal_subscription_rows)
                self.assertEqual(
                    b"source-db-must-not-change",
                    build_store.DEFAULT_DB_PATH.read_bytes(),
                )
            finally:
                build_store.DEFAULT_DB_PATH = original_db_path


if __name__ == "__main__":
    unittest.main()
