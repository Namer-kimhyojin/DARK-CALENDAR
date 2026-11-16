"""The calendar table's colour default must be the real default colour, not a placeholder."""

from calendar_app.infrastructure.db import database_unified
from calendar_app.shared.calendar_defaults import DEFAULT_CALENDAR_COLOR
from tests.support import TemporaryDatabaseTestCase

PLACEHOLDER = "{DEFAULT_CALENDAR_COLOR}"


class CalendarDefaultColorTest(TemporaryDatabaseTestCase):
    def _connection(self):
        return database_unified.db_manager.get_connection(raise_on_error=True)

    def test_insert_without_colour_gets_default_colour(self):
        conn = self._connection()
        conn.execute(
            "INSERT INTO calendar (id, type, name) VALUES ('local::no-colour', 'local', 'x')"
        )
        conn.commit()
        color = conn.execute("SELECT color FROM calendar WHERE id='local::no-colour'").fetchone()[0]
        self.assertEqual(color, DEFAULT_CALENDAR_COLOR)

    def test_startup_repairs_rows_that_stored_the_placeholder(self):
        # Databases created by earlier versions declared the placeholder text as the default.
        conn = self._connection()
        conn.execute(
            "INSERT INTO calendar (id, type, name, color) VALUES ('local::old', 'local', 'old', ?)",
            (PLACEHOLDER,),
        )
        conn.commit()

        database_unified.initialize_unified_database()

        conn = self._connection()
        color = conn.execute("SELECT color FROM calendar WHERE id='local::old'").fetchone()[0]
        self.assertEqual(color, DEFAULT_CALENDAR_COLOR)
