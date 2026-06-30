from types import SimpleNamespace
from unittest.mock import patch

from PyQt6.QtCore import QSettings

from calendar_app.app_paths import APP_NAME, APP_VENDOR
from calendar_app.infrastructure.db import database_unified, search_repo, task_repo
from calendar_app.infrastructure.google_sync import engine, repository
from tests.support import TemporaryDatabaseTestCase


class FakeSettings:
    def __init__(self, initial=None):
        self.data = dict(initial or {})

    def value(self, key, default=None, type=None):
        value = self.data.get(key, default)
        if type is not None and value is not None:
            return type(value)
        return value

    def setValue(self, key, value):
        self.data[key] = value


class FakeDate:
    def __init__(self, date_str):
        self._date_str = date_str

    def toString(self, fmt):
        return self._date_str


class FakeGoogleEvent:
    def __init__(
        self,
        event_id,
        summary,
        start_time,
        end_time,
        *,
        description="",
        location="",
        status="confirmed",
        color_id=None,
        updated_time="2026-03-14T00:00:00Z",
    ):
        self.id = event_id
        self.summary = summary
        self.description = description
        self.start_time = start_time
        self.end_time = end_time
        self.location = location
        self.status = status
        self.color_id = color_id
        self.updated_time = updated_time


class FakeSyncService:
    def __init__(self, events=None, authenticate_result=True, next_token="next-token"):
        self.is_authenticated = authenticate_result
        self.events = list(events or [])
        self.authenticate_result = authenticate_result
        self.next_token = next_token
        self.calendar_id = "primary"
        self.time_zone = "Asia/Seoul"

    def authenticate(self, parent_widget=None, interactive=True):
        self.is_authenticated = self.authenticate_result
        return self.authenticate_result

    def fetch_sync_events(self, sync_token, calendar_id=None):
        return list(self.events), self.next_token, False

    def delete_event(self, event_id, calendar_id=None):
        return True

    def update_event(self, *args, **kwargs):
        return True

    def create_event(self, *args, **kwargs):
        return "created-id"


class GCalSyncIntegrationTests(TemporaryDatabaseTestCase):
    def _allow_primary_alias_duplicates(self):
        conn = database_unified.db_manager.get_connection()
        cur = conn.cursor()
        cur.execute("DROP INDEX IF EXISTS idx_unified_task_gcal_calendar_event")
        conn.commit()

    def _set_resolved_primary(self, calendar_id: str):
        settings = QSettings(APP_VENDOR, APP_NAME)
        settings.setValue("gcal_primary_resolved_id", calendar_id)
        self.addCleanup(settings.remove, "gcal_primary_resolved_id")

    def _build_app(self, settings_data, sync_service):
        return SimpleNamespace(
            settings=FakeSettings(settings_data),
            current_date=FakeDate("2026-03-14"),
            gcal_sync=sync_service,
            update_sync_status=lambda: None,
            mark_panel_dirty=lambda **kwargs: None,
        )

    def _archive_rows(self):
        conn = database_unified.db_manager.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM gcal_deleted_task_archive ORDER BY id ASC")
        return [dict(row) for row in cur.fetchall()]

    def test_full_sync_inserts_remote_event_and_stores_token(self):
        app = self._build_app(
            {
                "gcal_enabled": "true",
                "gcal_calendar_id": "primary",
                "gcal_timezone": "Asia/Seoul",
                "gcal_bound_calendar_id": "primary",
            },
            FakeSyncService(
                events=[
                    FakeGoogleEvent(
                        "evt-1",
                        "Remote Task",
                        "2026-03-14T09:00:00+09:00",
                        "2026-03-14T10:00:00+09:00",
                    )
                ]
            ),
        )

        ok = engine.sync_google_calendar(app, silent=True)

        self.assertTrue(ok)
        tasks = task_repo.get_google_sync_tasks()
        self.assertEqual(len(tasks), 0)
        conn = database_unified.db_manager.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM unified_task WHERE gcal_event_id=?", ("evt-1",))
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "Remote Task")
        self.assertEqual(app.settings.data["gcal_sync_token::primary"], "next-token")

    def test_full_sync_archives_local_task_missing_from_remote(self):
        local_id = task_repo.create_unified_task(
            {
                "name": "Local Only",
                "type": "schedule",
                "deadline": "2026-03-14 09:00:00",
                "end_date": "2026-03-14 10:00:00",
                "gcal_event_id": "evt-missing",
                "gcal_dirty": 0,
            }
        )
        app = self._build_app(
            {
                "gcal_enabled": "true",
                "gcal_calendar_id": "primary",
                "gcal_timezone": "Asia/Seoul",
                "gcal_bound_calendar_id": "primary",
            },
            FakeSyncService(events=[]),
        )

        ok = engine.sync_google_calendar(app, silent=True)

        self.assertTrue(ok)
        self.assertIsNone(task_repo.get_unified_task(local_id))
        archive_rows = self._archive_rows()
        self.assertEqual(len(archive_rows), 1)
        self.assertEqual(archive_rows[0]["gcal_event_id"], "evt-missing")
        self.assertEqual(archive_rows[0]["name"], "Local Only")

    def test_binding_change_with_auth_failure_keeps_existing_links(self):
        local_id = task_repo.create_unified_task(
            {
                "name": "Bound Task",
                "type": "schedule",
                "deadline": "2026-03-14 09:00:00",
                "end_date": "2026-03-14 10:00:00",
                "gcal_event_id": "evt-bound",
                "gcal_dirty": 0,
            }
        )
        app = self._build_app(
            {
                "gcal_enabled": "true",
                "gcal_calendar_id": "new-calendar",
                "gcal_timezone": "Asia/Seoul",
                "gcal_bound_calendar_id": "old-calendar",
            },
            FakeSyncService(events=[], authenticate_result=False),
        )

        ok = engine.sync_google_calendar(app, silent=True)

        self.assertFalse(ok)
        task = task_repo.get_unified_task(local_id)
        self.assertIsNotNone(task)
        self.assertEqual(task["gcal_event_id"], "evt-bound")
        self.assertEqual(app.settings.data["gcal_bound_calendar_id"], "old-calendar")

    def test_full_sync_respects_non_seoul_timezone_for_remote_event(self):
        app = self._build_app(
            {
                "gcal_enabled": "true",
                "gcal_calendar_id": "primary",
                "gcal_timezone": "America/New_York",
                "gcal_bound_calendar_id": "primary",
            },
            FakeSyncService(
                events=[
                    FakeGoogleEvent(
                        "evt-ny",
                        "New York Task",
                        "2026-07-15T09:00:00-04:00",
                        "2026-07-15T10:00:00-04:00",
                    )
                ]
            ),
        )

        ok = engine.sync_google_calendar(app, silent=True)

        self.assertTrue(ok)
        conn = database_unified.db_manager.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM unified_task WHERE gcal_event_id=?", ("evt-ny",))
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["deadline"], "2026-07-15 09:00:00")
        self.assertEqual(row["end_date"], "2026-07-15 10:00:00")

    def test_push_queue_excludes_unknown_sync_mode_tasks(self):
        task_repo.create_unified_task(
            {
                "name": "Unknown Origin",
                "type": "schedule",
                "deadline": "2026-03-20 09:00:00",
                "end_date": "2026-03-20 10:00:00",
                "gcal_dirty": 1,
                "gcal_sync_mode": "unknown",
            }
        )
        local_id = task_repo.create_unified_task(
            {
                "name": "Local Owned",
                "type": "schedule",
                "deadline": "2026-03-20 11:00:00",
                "end_date": "2026-03-20 12:00:00",
                "gcal_dirty": 1,
                "gcal_sync_mode": "local_owned",
            }
        )

        rows = task_repo.get_google_sync_tasks()
        ids = {int(r["id"]) for r in rows}
        self.assertIn(local_id, ids)
        self.assertEqual(len(ids), 1)

    def test_schedule_query_deduplicates_primary_alias_rows(self):
        self._allow_primary_alias_duplicates()
        self._set_resolved_primary("owner@example.com")
        rows = [
            {
                "name": "Alias duplicate",
                "type": "schedule",
                "deadline": "2026-04-03 09:00:00",
                "end_date": "2026-04-03 10:00:00",
                "gcal_event_id": "evt-dup-1",
                "gcal_source_calendar_id": "primary",
                "gcal_target_calendar_id": "primary",
                "gcal_sync_mode": "remote_mirror",
                "calendar_id": "gcal::primary",
            },
            {
                "name": "Alias duplicate",
                "type": "schedule",
                "deadline": "2026-04-03 09:00:00",
                "end_date": "2026-04-03 10:00:00",
                "gcal_event_id": "evt-dup-1",
                "gcal_source_calendar_id": "owner@example.com",
                "gcal_target_calendar_id": "owner@example.com",
                "gcal_sync_mode": "remote_mirror",
                "calendar_id": "gcal::owner@example.com",
            },
        ]
        for payload in rows:
            task_repo.create_unified_task(payload)

        results = search_repo.get_schedule_tasks_overlapping_range_with_progress(
            "2026-04-03",
            "2026-04-03",
        )

        self.assertEqual(1, len(results))
        self.assertEqual("owner@example.com", results[0]["gcal_source_calendar_id"])

    def test_cleanup_duplicate_gcal_rows_removes_primary_alias_copy(self):
        self._allow_primary_alias_duplicates()
        self._set_resolved_primary("owner@example.com")
        primary_row_id = task_repo.create_unified_task(
            {
                "name": "Primary alias row",
                "type": "schedule",
                "deadline": "2026-04-03 09:00:00",
                "end_date": "2026-04-03 10:00:00",
                "gcal_event_id": "evt-dup-clean",
                "gcal_source_calendar_id": "primary",
                "gcal_target_calendar_id": "primary",
                "gcal_sync_mode": "remote_mirror",
                "calendar_id": "gcal::primary",
            }
        )
        real_row_id = task_repo.create_unified_task(
            {
                "name": "Primary alias row",
                "type": "schedule",
                "deadline": "2026-04-03 09:00:00",
                "end_date": "2026-04-03 10:00:00",
                "gcal_event_id": "evt-dup-clean",
                "gcal_source_calendar_id": "owner@example.com",
                "gcal_target_calendar_id": "owner@example.com",
                "gcal_sync_mode": "remote_mirror",
                "calendar_id": "gcal::owner@example.com",
            }
        )

        app = self._build_app(
            {
                "gcal_enabled": "true",
                "gcal_calendar_id": "primary",
                "gcal_timezone": "Asia/Seoul",
                "gcal_bound_calendar_id": "primary",
                "gcal_primary_resolved_id": "owner@example.com",
            },
            FakeSyncService(events=[]),
        )

        deleted = repository.cleanup_duplicate_gcal_rows()

        self.assertEqual(1, deleted)
        self.assertIsNone(task_repo.get_unified_task(primary_row_id))
        self.assertIsNotNone(task_repo.get_unified_task(real_row_id))

        with (
            patch.object(engine, "_process_google_delete_queue", return_value=(0, 0)),
            patch.object(engine, "_push_local_changes_to_google", return_value=(0, 0, 0)),
            patch.object(engine, "_should_refresh_calendar_list", return_value=False),
        ):
            ok = engine.sync_google_calendar(app, silent=True)

        self.assertTrue(ok)
        conn = database_unified.db_manager.get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM unified_task WHERE gcal_event_id=?",
            ("evt-dup-clean",),
        )
        self.assertEqual(0, cur.fetchone()[0])
