import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


from calendar_app.infrastructure.db import database_unified


class TemporaryDatabaseTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()

        self._tmpdir = tempfile.TemporaryDirectory()

        self._original_db_path = database_unified.DB_PATH

        database_unified.db_manager.close_all_connections()

        database_unified.DB_PATH = os.path.join(self._tmpdir.name, "test.db")

        database_unified.initialize_unified_database()

    def tearDown(self):
        database_unified.db_manager.close_all_connections()

        database_unified.DB_PATH = self._original_db_path

        self._tmpdir.cleanup()

        super().tearDown()
