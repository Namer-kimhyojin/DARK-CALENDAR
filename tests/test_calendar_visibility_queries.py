# -*- coding: utf-8 -*-
"""Screen queries honor calendar ownership while management remains unfiltered."""

from unittest.mock import patch

from calendar_app.infrastructure.db import calendar_repo
from calendar_app.infrastructure.db import db_repository_unified as repo
from tests.support import TemporaryDatabaseTestCase


class CalendarVisibilityQueryTests(TemporaryDatabaseTestCase):
    date = "2026-10-09"

    def setUp(self):
        super().setUp()
        self._primary = patch.object(
            repo, "_resolved_primary_gcal_id_for_query", return_value="family@example.test"
        )
        self._primary.start()
        self.addCleanup(self._primary.stop)
        self._calendar("local::personal", kind="local")
        self._calendar("local::hidden", kind="local", visible=False)
        self._calendar("gcal::team@example.test", remote="team@example.test", visible=False)
        self._calendar("gcal::family@example.test", remote="family@example.test")
        self._calendar("gcal::primary", remote="primary")

    def _calendar(self, identity, *, kind="gcal", remote=None, visible=True, active=True):
        self.assertTrue(
            calendar_repo.upsert_calendar(
                identity,
                kind,
                identity,
                is_visible=visible,
                is_active=active,
                gcal_calendar_id=remote,
            )
        )

    def _task(self, kind="schedule", **ownership):
        payload = {
            "name": "Same holiday",
            "type": kind,
            "priority": "normal",
            "status": "in_progress",
            "deadline": self.date + " 12:00:00",
            "end_date": self.date + " 13:00:00",
            "target_date": self.date,
            **ownership,
        }
        task_id = repo.create_unified_task(payload)
        self.assertIsNotNone(task_id)
        return task_id

    def _snapshot(self):
        connection = repo.get_connection()
        return {
            table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY id")]
            for table in ("calendar", "unified_task", "task_checklist_link")
        }

    def _assert_screen_rows(self, expected_ids, *, kind="schedule", hide_google=False):
        before = self._snapshot()
        queries = [
            lambda: repo.get_all_tasks_by_date(self.date, hide_gcal_items=hide_google),
            lambda: repo.get_all_tasks_by_date_with_progress(
                self.date, hide_gcal_items=hide_google
            ),
        ]
        if kind == "schedule":
            queries.append(
                lambda: repo.get_schedule_tasks_overlapping_range_with_progress(
                    self.date, self.date, hide_gcal_items=hide_google
                )
            )
        if not hide_google:
            queries.append(lambda: repo.get_tasks_by_type_with_progress(kind, self.date))
            queries.append(lambda: repo.get_tasks_by_type_with_progress(kind))
        for query_index, query in enumerate(queries):
            with self.subTest(query=query_index, kind=kind, hide_google=hide_google):
                self.assertEqual({row["id"] for row in query()}, set(expected_ids))
                self.assertEqual(self._snapshot(), before)

    def test_hidden_source_hides_primary_null_and_stale_local_mirrors(self):
        for stored in ("gcal::primary", None, "local::personal"):
            self._task(
                calendar_id=stored,
                gcal_source_calendar_id="team@example.test",
                gcal_target_calendar_id="team@example.test",
                gcal_sync_mode="remote_mirror",
                gcal_event_id="hidden-" + str(stored),
            )
        visible = self._task(calendar_id="gcal::family@example.test")

        self._assert_screen_rows([visible])

    def test_routine_screen_hides_legacy_source_without_event_or_mode(self):
        for stored in ("gcal::primary", None, "local::personal"):
            self._task(
                "routine",
                calendar_id=stored,
                gcal_source_calendar_id="team@example.test",
                gcal_sync_mode=None,
                gcal_event_id=None,
            )
        visible = self._task("routine", calendar_id="local::personal")

        self._assert_screen_rows([visible], kind="routine")

    def test_hidden_primary_alias_does_not_exclude_visible_concrete_source(self):
        self.assertTrue(calendar_repo.set_calendar_visible("gcal::primary", False))
        task = self._task(
            calendar_id="gcal::primary",
            gcal_source_calendar_id="family@example.test",
            gcal_sync_mode="remote_mirror",
            gcal_event_id="visible-primary-alias",
        )

        self._assert_screen_rows([task])

    def test_hidden_primary_alias_does_not_exclude_visible_routine_source(self):
        self.assertTrue(calendar_repo.set_calendar_visible("gcal::primary", False))
        task = self._task(
            "routine",
            calendar_id="gcal::primary",
            gcal_source_calendar_id="family@example.test",
            gcal_sync_mode="remote_mirror",
            gcal_event_id="visible-routine-primary",
        )

        self._assert_screen_rows([task], kind="routine")

    def test_hide_google_items_hides_source_only_legacy_row_without_calendar_metadata(self):
        self._task(
            calendar_id=None,
            gcal_source_calendar_id="not-registered@example.test",
            gcal_sync_mode=None,
            gcal_event_id=None,
        )
        local = self._task(calendar_id="local::personal", gcal_sync_mode="local_owned")

        self._assert_screen_rows([local], hide_google=True)

    def test_local_owned_visible_calendar_is_preserved_with_hidden_source_and_target(self):
        task = self._task(
            calendar_id="local::personal",
            gcal_sync_mode="local_owned",
            gcal_source_calendar_id="team@example.test",
            gcal_target_calendar_id="team@example.test",
            gcal_event_id="local-linked",
        )

        self._assert_screen_rows([task])
        self._assert_screen_rows([task], hide_google=True)

    def test_local_owned_hidden_calendar_stays_hidden_with_visible_google_target(self):
        self._task(
            calendar_id="local::hidden",
            gcal_sync_mode="local_owned",
            gcal_source_calendar_id="family@example.test",
            gcal_target_calendar_id="family@example.test",
            gcal_event_id="local-hidden-linked",
        )

        self._assert_screen_rows([])

    def test_local_owned_routine_uses_local_visibility_with_google_provenance(self):
        visible = self._task(
            "routine",
            calendar_id="local::personal",
            gcal_sync_mode="local_owned",
            gcal_source_calendar_id="team@example.test",
            gcal_target_calendar_id="team@example.test",
        )
        self._task(
            "routine",
            calendar_id="local::hidden",
            gcal_sync_mode="local_owned",
            gcal_source_calendar_id="family@example.test",
        )

        self._assert_screen_rows([visible], kind="routine")

    def test_raw_management_type_query_retains_hidden_calendar_records(self):
        schedule = self._task(calendar_id="gcal::team@example.test")
        routine = self._task("routine", calendar_id="local::hidden")
        before = self._snapshot()

        self.assertEqual({row["id"] for row in repo.get_tasks_by_type("schedule")}, {schedule})
        self.assertEqual({row["id"] for row in repo.get_tasks_by_type("routine")}, {routine})
        self.assertEqual(self._snapshot(), before)

    def test_paused_google_subscription_remains_visible_when_display_enabled(self):
        self._calendar("gcal::holiday", remote="holiday", active=False)
        task = self._task(
            calendar_id="gcal::holiday",
            gcal_source_calendar_id="holiday",
            gcal_sync_mode="remote_mirror",
            gcal_event_id="holiday-event",
        )

        self._assert_screen_rows([task])

    def test_null_visibility_flag_and_unassigned_local_rows_default_visible(self):
        connection = repo.get_connection()
        connection.execute("UPDATE calendar SET is_visible=NULL WHERE id='local::personal'")
        connection.commit()
        assigned = self._task(calendar_id="local::personal", gcal_sync_mode="local_owned")
        unassigned = self._task(calendar_id=None, gcal_sync_mode="local_owned")

        self._assert_screen_rows([assigned, unassigned])

    def test_primary_alias_without_source_uses_resolved_primary_calendar_visibility(self):
        self.assertTrue(calendar_repo.set_calendar_visible("gcal::family@example.test", False))
        self._task(
            calendar_id="gcal::primary",
            gcal_sync_mode="remote_mirror",
            gcal_event_id="primary-no-source",
        )

        self._assert_screen_rows([])

    def test_same_title_from_another_visible_calendar_remains_after_hiding_team(self):
        self._task(
            calendar_id="gcal::team@example.test",
            gcal_source_calendar_id="team@example.test",
            gcal_sync_mode="remote_mirror",
            gcal_event_id="team-holiday",
        )
        family = self._task(
            calendar_id="gcal::family@example.test",
            gcal_source_calendar_id="family@example.test",
            gcal_sync_mode="remote_mirror",
            gcal_event_id="family-holiday",
        )
        local = self._task(calendar_id=None, gcal_sync_mode="local_owned")

        self._assert_screen_rows([family, local])
