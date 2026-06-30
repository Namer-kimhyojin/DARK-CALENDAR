import sqlite3
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from calendar_app.infrastructure.db import db_repository_unified
from calendar_app.infrastructure.google_sync import engine, repository
from calendar_app.infrastructure.google_sync import helpers as gcal_sync_helpers
from calendar_app.infrastructure.google_sync import service as gcal_service
from calendar_app.shared import datetime_utils


class FakeSyncService:
    def __init__(
        self,
        update_result=False,
        error_kind="update",
        created_id=None,
        *,
        calendar_id="primary",
        accessible_calendar_ids=None,
        update_results_by_calendar=None,
    ):
        self.is_authenticated = True

        self.last_error_kind = None

        self.update_result = update_result

        self.error_kind = error_kind

        self.created_id = created_id

        self.update_calls = 0

        self.create_calls = 0

        self.calendar_id = calendar_id

        self.accessible_calendar_ids = list(accessible_calendar_ids or [calendar_id or "primary"])

        self.update_results_by_calendar = dict(update_results_by_calendar or {})

        self.update_calendar_ids = []

    def update_event(self, *args, **kwargs):
        self.update_calls += 1

        calendar_id = kwargs.get("calendar_id")

        self.update_calendar_ids.append(calendar_id)

        if self.update_results_by_calendar:
            result = bool(self.update_results_by_calendar.get(calendar_id, False))

            self.last_error_kind = None if result else self.error_kind

            return result

        self.last_error_kind = None if self.update_result else self.error_kind

        return self.update_result

    def create_event(self, *args, **kwargs):
        self.create_calls += 1

        return self.created_id

    def delete_event(self, event_id, calendar_id=None):
        return bool(event_id)

    def authenticate(self, *args, **kwargs):
        return True

    def fetch_sync_events(self, sync_token, calendar_id=None):
        return ([], "next-token", False)

    def fetch_events(self, date_from, date_to, calendar_id=None):
        return []

    def list_accessible_calendars(self):
        return [
            {
                "id": calendar_id,
                "summary": "Primary" if calendar_id == "primary" else calendar_id,
                "accessRole": "owner",
            }
            for calendar_id in self.accessible_calendar_ids
        ]


class GCalSyncHelperTests(TestCase):
    def test_transient_update_failure_does_not_create_fallback(self):
        app = SimpleNamespace(
            settings=SimpleNamespace(gcal_enabled=True),
            gcal_sync=FakeSyncService(
                update_result=False, error_kind="update", created_id="new-id"
            ),
        )

        task_data = {
            "id": 10,
            "name": "테스트 일정",
            "deadline": "2026-03-04 09:00:00",
            "end_date": "2026-03-04 10:00:00",
            "gcal_event_id": "existing-id",
        }

        with patch(
            "calendar_app.infrastructure.google_sync.helpers._persist_gcal_event_id"
        ) as persist_mock:
            result = gcal_sync_helpers.sync_task_to_google(app, task_data, create_if_missing=True)

        self.assertEqual(result.event_id, "existing-id")
        self.assertFalse(result.success)
        self.assertEqual(result.error_kind, "update")
        self.assertEqual(app.gcal_sync.update_calls, 1)
        self.assertEqual(app.gcal_sync.create_calls, 0)
        persist_mock.assert_not_called()

    def test_not_found_update_failure_creates_fallback_and_persists_id_when_source_is_explicit(
        self,
    ):
        app = SimpleNamespace(
            settings=SimpleNamespace(gcal_enabled=True),
            gcal_sync=FakeSyncService(
                update_result=False,
                error_kind="not_found",
                created_id="replacement-id",
                calendar_id="team-cal",
                accessible_calendar_ids=["team-cal"],
            ),
        )

        task_data = {
            "id": 11,
            "name": "테스트 일정",
            "deadline": "2026-03-04 09:00:00",
            "end_date": "2026-03-04 10:00:00",
            "gcal_event_id": "missing-id",
            "gcal_source_calendar_id": "team-cal",
        }

        with patch(
            "calendar_app.infrastructure.google_sync.helpers._persist_gcal_event_id"
        ) as persist_mock:
            result = gcal_sync_helpers.sync_task_to_google(app, task_data, create_if_missing=True)

        self.assertEqual(result.event_id, "replacement-id")
        self.assertTrue(result.success)
        self.assertEqual(app.gcal_sync.update_calls, 1)
        self.assertEqual(app.gcal_sync.create_calls, 1)
        persist_mock.assert_called_once_with(task_data, "replacement-id")

    def test_not_found_update_recovers_by_searching_accessible_calendars_before_create(self):
        app = SimpleNamespace(
            settings=SimpleNamespace(gcal_enabled=True, gcal_calendar_id="primary"),
            gcal_sync=FakeSyncService(
                update_result=False,
                error_kind="not_found",
                created_id="replacement-id",
                calendar_id="primary",
                accessible_calendar_ids=["primary", "team-cal"],
                update_results_by_calendar={"primary": False, "team-cal": True},
            ),
        )
        task_data = {
            "id": 15,
            "name": "Cross-calendar event",
            "deadline": "2026-03-04 09:00:00",
            "end_date": "2026-03-04 10:00:00",
            "gcal_event_id": "evt-team",
        }

        with patch(
            "calendar_app.infrastructure.google_sync.helpers._mark_task_synced", return_value=True
        ) as mark_mock:
            result = gcal_sync_helpers.sync_task_to_google(app, task_data, create_if_missing=True)

        self.assertTrue(result.success)
        self.assertTrue(result.auto_healed)
        self.assertEqual(result.event_id, "evt-team")
        self.assertEqual(app.gcal_sync.create_calls, 0)
        self.assertEqual(app.gcal_sync.update_calendar_ids, ["primary", "team-cal"])
        _, kwargs = mark_mock.call_args
        self.assertEqual(kwargs["source_calendar_id"], "team-cal")
        self.assertEqual(kwargs["target_calendar_id"], "team-cal")

    def test_not_found_update_without_explicit_calendar_does_not_create_duplicate(self):
        app = SimpleNamespace(
            settings=SimpleNamespace(gcal_enabled=True, gcal_calendar_id="primary"),
            gcal_sync=FakeSyncService(
                update_result=False,
                error_kind="not_found",
                created_id="replacement-id",
                calendar_id="primary",
                accessible_calendar_ids=["primary"],
            ),
        )
        task_data = {
            "id": 16,
            "name": "Ambiguous calendar event",
            "deadline": "2026-03-04 09:00:00",
            "end_date": "2026-03-04 10:00:00",
            "gcal_event_id": "evt-ambiguous",
        }

        with patch(
            "calendar_app.infrastructure.google_sync.helpers._persist_gcal_event_id"
        ) as persist_mock:
            result = gcal_sync_helpers.sync_task_to_google(app, task_data, create_if_missing=True)

        self.assertFalse(result.success)
        self.assertEqual(result.error_kind, "calendar_ambiguous")
        self.assertEqual(app.gcal_sync.create_calls, 0)
        persist_mock.assert_not_called()

    def test_create_success_but_local_state_mark_failure_returns_error(self):
        app = SimpleNamespace(
            settings=SimpleNamespace(gcal_enabled=True),
            gcal_sync=FakeSyncService(
                update_result=False,
                error_kind="not_found",
                created_id="replacement-id",
                calendar_id="team-cal",
                accessible_calendar_ids=["team-cal"],
            ),
        )
        task_data = {
            "id": 12,
            "name": "test-event",
            "deadline": "2026-03-04 09:00:00",
            "end_date": "2026-03-04 10:00:00",
            "gcal_event_id": "missing-id",
            "gcal_source_calendar_id": "team-cal",
        }

        with patch(
            "calendar_app.infrastructure.google_sync.helpers._mark_task_synced", return_value=False
        ):
            result = gcal_sync_helpers.sync_task_to_google(app, task_data, create_if_missing=True)

        self.assertEqual(result.event_id, "replacement-id")
        self.assertFalse(result.success)
        self.assertEqual(result.error_kind, "local_state")

    def test_non_gcal_calendar_task_is_skipped_without_default_push(self):
        app = SimpleNamespace(
            settings=SimpleNamespace(gcal_enabled=True),
            gcal_sync=FakeSyncService(
                update_result=False, error_kind="update", created_id="new-id"
            ),
        )
        task_data = {
            "id": 13,
            "name": "Local only task",
            "deadline": "2026-03-05 09:00:00",
            "end_date": "2026-03-05 10:00:00",
            "calendar_id": "local::home",
        }

        with patch(
            "calendar_app.infrastructure.google_sync.helpers._mark_task_synced", return_value=True
        ) as mark_mock:
            result = gcal_sync_helpers.sync_task_to_google(app, task_data, create_if_missing=True)

        self.assertTrue(result.success)
        self.assertEqual(result.error_kind, "skipped_non_gcal")
        self.assertEqual(app.gcal_sync.update_calls, 0)
        self.assertEqual(app.gcal_sync.create_calls, 0)
        mark_mock.assert_called_once()

    def test_non_gcal_calendar_with_stale_event_id_is_also_skipped(self):
        app = SimpleNamespace(
            settings=SimpleNamespace(gcal_enabled=True),
            gcal_sync=FakeSyncService(update_result=True, error_kind="update", created_id=None),
        )
        task_data = {
            "id": 14,
            "name": "Moved to local",
            "deadline": "2026-03-06 09:00:00",
            "end_date": "2026-03-06 10:00:00",
            "calendar_id": "local::home",
            "gcal_event_id": "evt-stale",
        }

        with patch(
            "calendar_app.infrastructure.google_sync.helpers._mark_task_synced", return_value=True
        ) as mark_mock:
            result = gcal_sync_helpers.sync_task_to_google(app, task_data, create_if_missing=True)

        self.assertTrue(result.success)
        self.assertEqual(result.error_kind, "skipped_non_gcal")
        self.assertEqual(app.gcal_sync.update_calls, 0)
        self.assertEqual(app.gcal_sync.create_calls, 0)
        mark_mock.assert_called_once()

    def test_mark_task_synced_passes_commit_and_source_fields(self):
        with (
            patch(
                "calendar_app.infrastructure.db.task_repo.list_gcal_subscriptions",
                return_value=[],
            ),
            patch(
                "calendar_app.infrastructure.db.task_repo.mark_unified_task_gcal_synced",
                return_value=True,
            ) as mark_mock,
        ):
            gcal_sync_helpers._mark_task_synced(
                10,
                event_id="evt-10",
                commit=False,
                source_calendar_id="primary",
            )

        _, kwargs = mark_mock.call_args
        self.assertEqual(kwargs["event_id"], "evt-10")
        self.assertEqual(kwargs["commit"], False)
        self.assertEqual(kwargs["source_calendar_id"], "primary")
        self.assertEqual(kwargs["source_calendar_summary"], "Primary")

    def test_calendar_binding_change_resets_tokens_without_detaching_links(self):
        class FakeSettings:
            def __init__(self):
                self.data = {"gcal_bound_calendar_id": "old-cal"}

            def value(self, key, default=None, type=None):
                value = self.data.get(key, default)
                if type is not None and value is not None:
                    return type(value)
                return value

            def setValue(self, key, value):
                self.data[key] = value

        app = SimpleNamespace(settings=FakeSettings())

        pending = engine._pending_calendar_binding_change(app, "new-cal")
        self.assertEqual(pending, "old-cal")

        with (
            patch.object(engine.task_repo, "detach_all_gcal_links", return_value=3) as detach_mock,
            patch.object(
                engine.task_repo, "clear_gcal_delete_queue", return_value=True
            ) as clear_queue_mock,
        ):
            changed = engine._apply_calendar_binding_change(app, pending, "new-cal")

        self.assertTrue(changed)
        detach_mock.assert_not_called()
        clear_queue_mock.assert_called_once_with()
        self.assertEqual(app.settings.data["gcal_sync_token::old-cal"], "")
        self.assertEqual(app.settings.data["gcal_sync_token::new-cal"], "")
        self.assertEqual(app.settings.data["gcal_sync_token_fails::old-cal"], 0)
        self.assertEqual(app.settings.data["gcal_sync_token_fails::new-cal"], 0)
        self.assertEqual(app.settings.data["gcal_bound_calendar_id"], "new-cal")

    def test_push_routes_to_task_target_calendar(self):
        class FakeSettings:
            def value(self, key, default=None, type=None):
                if key == "gcal_calendar_id":
                    return "bound-cal"
                return default

        app = SimpleNamespace(
            settings=FakeSettings(),
            gcal_sync=SimpleNamespace(calendar_id="bound-cal"),
        )

        task = {
            "id": 99,
            "name": "Shared Event",
            "deadline": "2026-03-14 09:00:00",
            "end_date": "2026-03-14 10:00:00",
            "gcal_event_id": "evt-shared",
            "gcal_dirty": 1,
            "gcal_source_calendar_id": "shared-cal",
            "gcal_source_summary": "Shared Cal",
            "gcal_target_calendar_id": "team-writable-cal",
        }

        with (
            patch.object(engine.task_repo, "get_google_sync_tasks", return_value=[task]),
            patch.object(
                engine,
                "sync_task_to_google",
                return_value=SimpleNamespace(success=True, event_id="evt-shared"),
            ) as sync_mock,
        ):
            pushed, failed, auto_healed = engine._push_local_changes_to_google(app)

        self.assertEqual((pushed, failed, auto_healed), (0, 0, 0))
        sync_mock.assert_called_once()
        _, kwargs = sync_mock.call_args
        self.assertEqual(kwargs["commit"], True)
        self.assertEqual(kwargs["target_calendar_id"], "team-writable-cal")

    def test_push_remote_newer_skip_keeps_auto_healed_at_zero(self):
        class FakeSettings:
            def value(self, key, default=None, type=None):
                if key == "gcal_calendar_id":
                    return "primary"
                return default

        app = SimpleNamespace(
            settings=FakeSettings(),
            gcal_sync=SimpleNamespace(calendar_id="primary", is_authenticated=True),
        )

        task = {
            "id": 2891,
            "name": "Remote changed task",
            "deadline": "2026-04-06 09:00:00",
            "end_date": "2026-04-06 10:00:00",
            "gcal_event_id": "evt-2891",
            "gcal_dirty": 1,
            "gcal_remote_updated_at": "2026-04-06T11:27:29Z",
        }

        with (
            patch.object(engine.task_repo, "get_google_sync_tasks", return_value=[task]),
            patch.object(engine, "_writable_gcal_ids", return_value={"primary"}),
            patch.object(engine, "_remote_text_is_newer_than_local_base", return_value=True),
            patch.object(engine, "_mark_sync_failure", return_value=True) as failure_mock,
            patch.object(engine, "sync_task_to_google") as sync_mock,
        ):
            pushed, failed, auto_healed = engine._push_local_changes_to_google(app)

        self.assertEqual((pushed, failed, auto_healed), (0, 1, 0))
        sync_mock.assert_not_called()
        failure_mock.assert_called_once_with(2891, "remote_newer_than_local", commit=True)

    def test_process_google_delete_queue_uses_ready_rows_only(self):
        app = SimpleNamespace(gcal_sync=FakeSyncService(update_result=True))
        ready_rows = [
            {"id": 1, "gcal_event_id": "evt-1"},
            {"id": 2, "gcal_event_id": "evt-2"},
        ]

        with (
            patch.object(
                engine.task_repo, "get_gcal_delete_queue_ready", return_value=ready_rows
            ) as ready_mock,
            patch.object(engine.task_repo, "mark_gcal_delete_done", return_value=True) as done_mock,
        ):
            deleted, failed = engine._process_google_delete_queue(app)

        self.assertEqual((deleted, failed), (2, 0))
        ready_mock.assert_called_once_with(max_retry_count=5)
        self.assertEqual(done_mock.call_count, 2)

    def test_handle_task_dropped_skips_non_gcal_task_push(self):
        wake_calls = []

        class FakeSettings:
            def value(self, key, default=None, type=None):
                if key == "gcal_enabled":
                    return "true"
                if key == "gcal_calendar_id":
                    return "primary"
                return default

        app = SimpleNamespace(
            settings=FakeSettings(),
            wake_gcal_sync=lambda: wake_calls.append(True),
        )

        local_task = {
            "id": 501,
            "name": "Local item",
            "calendar_id": "local::inbox",
            "deadline": "2026-03-22 09:00:00",
            "end_date": "2026-03-22 10:00:00",
        }

        with (
            patch(
                "calendar_app.infrastructure.task_drop_service.handle_task_drop",
                return_value=(1, [501]),
            ) as drop_mock,
            patch.object(
                engine.task_repo, "get_unified_task", return_value=local_task
            ) as get_task_mock,
            patch.object(engine, "sync_task_to_google") as sync_mock,
        ):
            changed, copied_ids = engine.handle_task_dropped(
                app,
                [123],
                "2026-03-22",
                "09:00",
                "copy",
            )

        self.assertEqual((changed, copied_ids), (1, [501]))
        drop_mock.assert_called_once()
        get_task_mock.assert_called_once_with(501)
        sync_mock.assert_not_called()
        self.assertEqual(len(wake_calls), 1)

    def test_delete_task_by_gcal_id_archives_remote_deleted_task(self):
        with patch.object(
            repository.task_repo, "archive_gcal_deleted_task", return_value=True
        ) as archive_mock:
            result = repository.delete_task_by_gcal_id("unified_task", 42)

        self.assertTrue(result)
        archive_mock.assert_called_once_with(42, reason="remote_deleted")

    def test_insert_gcal_event_to_unified_carries_source_calendar_fields(self):
        with (
            patch.object(repository, "get_connection", return_value=None),
            patch.object(
                repository.task_repo, "create_unified_task", return_value=99
            ) as create_mock,
        ):
            created = repository.insert_gcal_event_to_unified(
                "Remote Task",
                "2026-03-14 09:00:00",
                "2026-03-14 10:00:00",
                "evt-1",
                source_calendar_id="team-calendar@group.calendar.google.com",
                source_calendar_summary="Team Calendar",
            )

        self.assertEqual(created, 99)
        payload = create_mock.call_args.args[0]
        self.assertEqual(
            payload["gcal_source_calendar_id"], "team-calendar@group.calendar.google.com"
        )
        self.assertEqual(payload["gcal_source_summary"], "Team Calendar")
        self.assertEqual(payload["gcal_sync_mode"], "remote_mirror")

    def test_sync_skips_token_advance_when_pull_apply_fails(self):
        class FakeSettings:
            def __init__(self):
                self.data = {
                    "gcal_enabled": "true",
                    "gcal_calendar_id": "primary",
                    "gcal_timezone": "Asia/Seoul",
                    "gcal_sync_token::primary": "old-token",
                    "gcal_sync_token_fails::primary": 0,
                    "gcal_bound_calendar_id": "primary",
                }

            def value(self, key, default=None, type=None):
                value = self.data.get(key, default)
                if type is not None and value is not None:
                    return type(value)
                return value

            def setValue(self, key, value):
                self.data[key] = value

        class FakeDate:
            def toString(self, fmt):
                return "2026-03-14"

        class FakeEvent:
            def __init__(self):
                self.id = "evt-1"
                self.summary = "Remote"
                self.description = ""
                self.start_time = "2026-03-14T09:00:00+09:00"
                self.end_time = "2026-03-14T10:00:00+09:00"
                self.location = ""
                self.status = "confirmed"
                self.color_id = None
                self.updated_time = "2026-03-14T00:00:00Z"

        app = SimpleNamespace(
            settings=FakeSettings(),
            current_date=FakeDate(),
            gcal_sync=FakeSyncService(update_result=True),
        )

        with (
            patch.object(engine, "_process_google_delete_queue", return_value=(0, 0)),
            patch.object(engine, "_push_local_changes_to_google", return_value=(0, 0, 0)),
            patch.object(engine, "_active_sync_calendar_ids", return_value=["primary"]),
            patch.object(
                engine.gcal_db_adapter,
                "get_all_gcal_tasks_map",
                return_value={"evt-1": ("unified_task", 7)},
            ),
            patch.object(
                engine.task_repo,
                "get_unified_task",
                return_value={
                    "id": 7,
                    "name": "Local",
                    "deadline": "2026-03-14 09:00:00",
                    "end_date": "2026-03-14 10:00:00",
                    "description": "",
                    "location": "",
                    "all_day": 0,
                    "bg_color": None,
                    "gcal_remote_updated_at": "2026-03-13T00:00:00Z",
                    "gcal_dirty": 0,
                },
            ),
            patch.object(engine.gcal_db_adapter, "update_task_from_gcal", return_value=False),
        ):
            app.gcal_sync.fetch_sync_events = lambda sync_token, calendar_id=None: (
                [FakeEvent()],
                "next-token",
                False,
            )
            success = engine.sync_google_calendar(app, silent=True)

        self.assertTrue(success)
        self.assertEqual(app.settings.data["gcal_sync_token::primary"], "old-token")
        self.assertEqual(app._last_gcal_sync_stats["pull_apply_failures"], 1)

    def test_sync_queues_conflict_when_remote_overwrites_local_dirty_task(self):
        class FakeSettings:
            def __init__(self):
                self.data = {
                    "gcal_enabled": "true",
                    "gcal_calendar_id": "primary",
                    "gcal_timezone": "Asia/Seoul",
                    "gcal_sync_token::primary": "old-token",
                    "gcal_sync_token_fails::primary": 0,
                    "gcal_bound_calendar_id": "primary",
                }

            def value(self, key, default=None, type=None):
                value = self.data.get(key, default)
                if type is not None and value is not None:
                    return type(value)
                return value

            def setValue(self, key, value):
                self.data[key] = value

        class FakeDate:
            def toString(self, fmt):
                return "2026-03-14"

        class FakeEvent:
            def __init__(self):
                self.id = "evt-1"
                self.summary = "Remote New"
                self.description = "remote desc"
                self.start_time = "2026-03-14T09:00:00+09:00"
                self.end_time = "2026-03-14T10:00:00+09:00"
                self.location = "Room-A"
                self.status = "confirmed"
                self.color_id = None
                self.updated_time = "2026-03-14T00:00:00Z"

        app = SimpleNamespace(
            settings=FakeSettings(),
            current_date=FakeDate(),
            gcal_sync=FakeSyncService(update_result=True),
            update_sync_status=lambda: None,
        )

        with (
            patch.object(engine, "_process_google_delete_queue", return_value=(0, 0)),
            patch.object(engine, "_push_local_changes_to_google", return_value=(0, 0, 0)),
            patch.object(engine, "_active_sync_calendar_ids", return_value=["primary"]),
            patch.object(
                engine.gcal_db_adapter,
                "get_all_gcal_tasks_map",
                return_value={"evt-1": ("unified_task", 7)},
            ),
            patch.object(
                engine.task_repo,
                "get_unified_task",
                return_value={
                    "id": 7,
                    "name": "Local Dirty",
                    "deadline": "2026-03-14 09:00:00",
                    "end_date": "2026-03-14 10:00:00",
                    "description": "",
                    "location": "",
                    "all_day": 0,
                    "bg_color": None,
                    "gcal_source_calendar_id": "primary",
                    "gcal_source_summary": "Primary",
                    "gcal_target_calendar_id": "primary",
                    "gcal_sync_mode": "local_owned",
                    "gcal_last_synced_at": "2026-03-13T00:00:00Z",
                    "gcal_remote_updated_at": "2026-03-13T00:00:00Z",
                    "gcal_dirty": 1,
                },
            ),
            patch.object(engine.gcal_db_adapter, "update_task_from_gcal", return_value=True),
            patch.object(
                engine.task_repo, "queue_gcal_sync_conflict", return_value=True
            ) as conflict_mock,
        ):
            app.gcal_sync.fetch_sync_events = lambda sync_token, calendar_id=None: (
                [FakeEvent()],
                "next-token",
                False,
            )
            success = engine.sync_google_calendar(app, silent=True)

        self.assertTrue(success)
        conflict_mock.assert_called_once()
        args, kwargs = conflict_mock.call_args
        self.assertEqual(args[0], 7)
        self.assertEqual(args[1], "evt-1")
        self.assertEqual(kwargs.get("gcal_calendar_id"), "primary")
        self.assertEqual(kwargs.get("conflict_kind"), "remote_overwrite")

    def test_archive_snapshot_contains_checklist_items(self):
        task_row = {
            "id": 7,
            "gcal_event_id": "evt-7",
            "name": "Task",
            "deadline": "2026-03-14 09:00:00",
            "end_date": "2026-03-14 10:00:00",
            "description": "desc",
            "location": "loc",
            "all_day": 0,
        }
        checklist_rows = [
            {"id": 1, "owner_id": 7, "item_text": "A", "item_order": 0, "display_type": "list"},
            {"id": 2, "owner_id": 7, "item_text": "B", "item_order": 1, "display_type": "list"},
        ]

        class FakeCursor:
            def __init__(self):
                self.snapshot_json = None
                self._fetch = []

            def execute(self, query, params=()):
                if "SELECT * FROM unified_task WHERE id=?" in query:
                    self._fetch = [task_row]
                elif "SELECT *" in query and "FROM task_checklist_link" in query:
                    self._fetch = checklist_rows
                elif "INSERT INTO gcal_deleted_task_archive" in query:
                    self.snapshot_json = params[-1]
                else:
                    self._fetch = []
                return self

            def fetchone(self):
                return self._fetch[0] if self._fetch else None

            def fetchall(self):
                return list(self._fetch)

        class FakeConn:
            def __init__(self):
                self.cur = FakeCursor()

            def cursor(self):
                return self.cur

            def commit(self):
                return None

            def rollback(self):
                return None

        fake_conn = FakeConn()
        with patch.object(db_repository_unified, "get_connection", return_value=fake_conn):
            ok = db_repository_unified.archive_gcal_deleted_task(7, reason="remote_deleted")

        self.assertTrue(ok)
        self.assertIn('"checklist_items"', fake_conn.cur.snapshot_json)
        self.assertIn('"item_text": "A"', fake_conn.cur.snapshot_json)

    def test_delete_queue_ready_falls_back_when_legacy_columns_missing(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE gcal_delete_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gcal_event_id TEXT NOT NULL,
                local_task_id INTEGER,
                created_at TEXT,
                last_error TEXT,
                retry_count INTEGER DEFAULT 0
            )
            """
        )
        cur.execute(
            """
            INSERT INTO gcal_delete_queue (gcal_event_id, local_task_id, created_at, last_error, retry_count)
            VALUES ('evt-legacy', 1, datetime('now', 'localtime'), NULL, 0)
            """
        )
        conn.commit()

        with patch.object(db_repository_unified, "get_connection", return_value=conn):
            rows = db_repository_unified.get_gcal_delete_queue_ready(max_retry_count=5)
            queued = db_repository_unified.queue_gcal_delete("evt-new", local_task_id=2)
            failed_marked = db_repository_unified.mark_gcal_delete_failed(1, "delete_failed")
            cleared = db_repository_unified.clear_gcal_delete_queue_error(1)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["gcal_event_id"], "evt-legacy")
        self.assertTrue(queued)
        self.assertTrue(failed_marked)
        self.assertTrue(cleared)

    def test_authenticate_returns_false_when_token_write_fails(self):
        class FakeCreds:
            valid = True

            def to_json(self):
                return "{}"

        svc = gcal_service.CalendarSyncService()

        def fake_exists(path):
            return path == gcal_service.CREDENTIALS_PATH

        with (
            patch.object(gcal_service, "HAS_GOOGLE_API", True),
            patch.object(gcal_service.os.path, "exists", side_effect=fake_exists),
            patch.object(gcal_service, "build", return_value=object()),
            patch("builtins.open", side_effect=OSError("disk full")),
            patch.object(gcal_service, "InstalledAppFlow") as flow_mock,
        ):
            flow_mock.from_client_secrets_file.return_value.run_local_server.return_value = (
                FakeCreds()
            )
            ok = svc.authenticate(parent_widget=None, interactive=True)

        self.assertFalse(ok)
        self.assertEqual(svc.last_error_kind, "auth")
        self.assertIn("token_write_failed", svc.last_error_message or "")

    def test_to_iso_with_tz_respects_requested_timezone_offset(self):
        iso = datetime_utils.to_iso_with_tz("2026-03-14 09:00:00", tz_offset="+00:00")
        parsed = datetime_utils.parse_datetime_str(
            "2026-03-14T09:00:00+00:00", target_tz_offset="+00:00"
        )

        self.assertEqual(iso, "2026-03-14T09:00:00+00:00")
        self.assertEqual(parsed.strftime("%Y-%m-%d %H:%M:%S"), "2026-03-14 09:00:00")

    def test_create_event_falls_back_to_primary_calendar_when_id_is_blank(self):
        class FakeInsertCall:
            def __init__(self, service):
                self.service = service

            def execute(self):
                return {"id": "created-id"}

        class FakeEventsResource:
            def __init__(self, service):
                self.service = service

            def insert(self, calendarId=None, body=None):
                self.service.last_calendar_id = calendarId
                self.service.last_body = body
                return FakeInsertCall(self.service)

        class FakeCalendarService:
            def __init__(self):
                self.last_calendar_id = None
                self.last_body = None
                self._events = FakeEventsResource(self)

            def events(self):
                return self._events

        svc = gcal_service.CalendarSyncService(calendar_id="", time_zone="Asia/Seoul")
        svc.is_authenticated = True
        svc.service = FakeCalendarService()

        created_id = svc.create_event(
            "Fallback test",
            "2026-03-19T09:00:00+09:00",
            "2026-03-19T10:00:00+09:00",
            all_day=True,
        )

        self.assertEqual(created_id, "created-id")
        self.assertEqual(svc.calendar_id, "primary")
        self.assertEqual(svc.service.last_calendar_id, "primary")

    def test_timezone_offset_for_datetime_str_handles_dst(self):
        winter = datetime_utils.timezone_offset_for_datetime_str(
            "2026-01-15 09:00:00", "America/New_York"
        )
        summer = datetime_utils.timezone_offset_for_datetime_str(
            "2026-07-15 09:00:00", "America/New_York"
        )

        self.assertEqual(winter, "-05:00")
        self.assertEqual(summer, "-04:00")

    def test_sync_sets_skipped_outcome_when_disabled(self):
        class FakeSettings:
            def value(self, key, default=None, type=None):
                data = {"gcal_enabled": "false"}
                value = data.get(key, default)
                if type is not None and value is not None:
                    return type(value)
                return value

            def setValue(self, key, value):
                return None

        app = SimpleNamespace(settings=FakeSettings(), update_sync_status=lambda: None)

        ok = engine.sync_google_calendar(app, silent=True)

        self.assertFalse(ok)
        self.assertEqual(app._last_gcal_sync_outcome, engine.SYNC_OUTCOME_SKIPPED)
        self.assertEqual(app._last_gcal_sync_error, "disabled")

    def test_sync_sets_failed_outcome_when_silent_auth_fails(self):
        class FakeSettings:
            def __init__(self):
                self.data = {
                    "gcal_enabled": "true",
                    "gcal_calendar_id": "primary",
                    "gcal_timezone": "Asia/Seoul",
                }

            def value(self, key, default=None, type=None):
                value = self.data.get(key, default)
                if type is not None and value is not None:
                    return type(value)
                return value

            def setValue(self, key, value):
                self.data[key] = value

        class FakeSyncServiceAuthFail:
            def __init__(self):
                self.calendar_id = "primary"
                self.time_zone = "Asia/Seoul"
                self.last_error_kind = "auth"

            def authenticate(self, *args, **kwargs):
                return False

        app = SimpleNamespace(
            settings=FakeSettings(),
            gcal_sync=FakeSyncServiceAuthFail(),
            update_sync_status=lambda: None,
        )

        ok = engine.sync_google_calendar(app, silent=True)

        self.assertFalse(ok)
        self.assertEqual(app._last_gcal_sync_outcome, engine.SYNC_OUTCOME_FAILED)
        self.assertEqual(app._last_gcal_sync_error, "auth")

    def test_sync_skips_when_already_in_progress(self):
        class FakeSettings:
            def value(self, key, default=None, type=None):
                value = {"gcal_enabled": "true"}.get(key, default)
                if type is not None and value is not None:
                    return type(value)
                return value

            def setValue(self, key, value):
                return None

        app = SimpleNamespace(
            settings=FakeSettings(),
            _gcal_sync_in_progress=True,
        )

        ok = engine.sync_google_calendar(app, silent=True)

        self.assertFalse(ok)
        self.assertEqual(app._last_gcal_sync_outcome, engine.SYNC_OUTCOME_SKIPPED)
        self.assertEqual(app._last_gcal_sync_error, "sync_in_progress")

    def test_delete_queue_treats_404_as_already_deleted(self):
        app = SimpleNamespace(
            gcal_sync=SimpleNamespace(
                last_error_status=404,
                last_error_message="not found",
            )
        )
        rows = [{"id": 1, "gcal_event_id": "evt-404", "gcal_calendar_id": "team-cal"}]

        with (
            patch.object(engine.task_repo, "get_gcal_delete_queue_ready", return_value=rows),
            patch.object(engine, "delete_task_from_google", return_value=False) as delete_mock,
            patch.object(engine.task_repo, "mark_gcal_delete_done", return_value=True) as done_mock,
            patch.object(
                engine.task_repo, "mark_gcal_delete_failed", return_value=True
            ) as fail_mock,
        ):
            deleted, failed = engine._process_google_delete_queue(app)

        self.assertEqual((deleted, failed), (1, 0))
        delete_mock.assert_called_once_with(app, "evt-404", calendar_id="team-cal")
        done_mock.assert_called_once_with(1)
        fail_mock.assert_not_called()

    def test_delete_queue_treats_410_as_already_deleted(self):
        app = SimpleNamespace(
            gcal_sync=SimpleNamespace(
                last_error_status=410,
                last_error_message="resource deleted",
            )
        )
        rows = [{"id": 7, "gcal_event_id": "evt-410", "gcal_calendar_id": "team-cal"}]

        with (
            patch.object(engine.task_repo, "get_gcal_delete_queue_ready", return_value=rows),
            patch.object(engine, "delete_task_from_google", return_value=False) as delete_mock,
            patch.object(engine.task_repo, "mark_gcal_delete_done", return_value=True) as done_mock,
            patch.object(
                engine.task_repo, "mark_gcal_delete_failed", return_value=True
            ) as fail_mock,
        ):
            deleted, failed = engine._process_google_delete_queue(app)

        self.assertEqual((deleted, failed), (1, 0))
        delete_mock.assert_called_once_with(app, "evt-410", calendar_id="team-cal")
        done_mock.assert_called_once_with(7)
        fail_mock.assert_not_called()

    def test_delete_queue_aborts_on_401_and_leaves_remaining_rows(self):
        app = SimpleNamespace(
            gcal_sync=SimpleNamespace(
                last_error_status=401,
                last_error_message="expired",
            )
        )
        rows = [
            {"id": 1, "gcal_event_id": "evt-auth", "gcal_calendar_id": "primary"},
            {"id": 2, "gcal_event_id": "evt-next", "gcal_calendar_id": "primary"},
        ]

        with (
            patch.object(engine.task_repo, "get_gcal_delete_queue_ready", return_value=rows),
            patch.object(engine, "delete_task_from_google", return_value=False) as delete_mock,
            patch.object(engine.task_repo, "mark_gcal_delete_done", return_value=True) as done_mock,
            patch.object(
                engine.task_repo, "mark_gcal_delete_failed", return_value=True
            ) as fail_mock,
        ):
            deleted, failed = engine._process_google_delete_queue(app)

        self.assertEqual((deleted, failed), (0, 1))
        self.assertEqual(delete_mock.call_count, 1)
        done_mock.assert_not_called()
        self.assertEqual(fail_mock.call_count, 1)
        self.assertEqual(fail_mock.call_args.args[0], 1)
        self.assertIn("[auth_expired_401]", fail_mock.call_args.args[1])

    def test_sync_fetch_404_deactivates_missing_calendar_and_succeeds(self):
        class FakeSettings:
            def __init__(self):
                self.data = {
                    "gcal_enabled": "true",
                    "gcal_calendar_id": "primary",
                    "gcal_timezone": "Asia/Seoul",
                    "gcal_bound_calendar_id": "primary",
                }

            def value(self, key, default=None, type=None):
                value = self.data.get(key, default)
                if type is not None and value is not None:
                    return type(value)
                return value

            def setValue(self, key, value):
                self.data[key] = value

        class FakeDate:
            def toString(self, fmt):
                return "2026-03-14"

        class FakeSyncService404:
            def __init__(self):
                self.calendar_id = "primary"
                self.time_zone = "Asia/Seoul"
                self.last_error_kind = "fetch"
                self.last_error_status = 404
                self.last_error_message = "missing"

            def authenticate(self, *args, **kwargs):
                return True

            def fetch_sync_events(self, sync_token, calendar_id=None):
                self.last_error_status = 404
                self.last_error_kind = "fetch"
                return None, None, False

        app = SimpleNamespace(
            settings=FakeSettings(),
            current_date=FakeDate(),
            gcal_sync=FakeSyncService404(),
            update_sync_status=lambda: None,
            mark_panel_dirty=lambda **kwargs: None,
        )

        with (
            patch.object(engine, "_process_google_delete_queue", return_value=(0, 0)),
            patch.object(engine, "_push_local_changes_to_google", return_value=(0, 0, 0)),
            patch.object(engine, "_active_sync_calendar_ids", return_value=["removed-cal"]),
            patch.object(engine, "_should_refresh_calendar_list", return_value=False),
            patch.object(engine, "_deactivate_missing_gcal_calendar") as deactivate_mock,
            patch.object(engine.gcal_db_adapter, "get_all_gcal_tasks_map", return_value={}),
        ):
            ok = engine.sync_google_calendar(app, silent=True)

        self.assertTrue(ok)
        self.assertEqual(app._last_gcal_sync_outcome, engine.SYNC_OUTCOME_SUCCESS)
        deactivate_mock.assert_called_once_with(app, "removed-cal")

    def test_sync_fetch_401_sets_failed_outcome(self):
        class FakeSettings:
            def __init__(self):
                self.data = {
                    "gcal_enabled": "true",
                    "gcal_calendar_id": "primary",
                    "gcal_timezone": "Asia/Seoul",
                    "gcal_bound_calendar_id": "primary",
                }

            def value(self, key, default=None, type=None):
                value = self.data.get(key, default)
                if type is not None and value is not None:
                    return type(value)
                return value

            def setValue(self, key, value):
                self.data[key] = value

        class FakeDate:
            def toString(self, fmt):
                return "2026-03-14"

        class FakeSyncService401:
            def __init__(self):
                self.calendar_id = "primary"
                self.time_zone = "Asia/Seoul"
                self.last_error_kind = "fetch"
                self.last_error_status = 401
                self.last_error_message = "expired"
                self.is_authenticated = True
                self.service = object()

            def authenticate(self, *args, **kwargs):
                return True

            def fetch_sync_events(self, sync_token, calendar_id=None):
                self.last_error_status = 401
                self.last_error_kind = "fetch"
                return None, None, False

        app = SimpleNamespace(
            settings=FakeSettings(),
            current_date=FakeDate(),
            gcal_sync=FakeSyncService401(),
            update_sync_status=lambda: None,
        )

        with (
            patch.object(engine, "_process_google_delete_queue", return_value=(0, 0)),
            patch.object(engine, "_push_local_changes_to_google", return_value=(0, 0, 0)),
            patch.object(engine, "_active_sync_calendar_ids", return_value=["primary"]),
            patch.object(engine, "_should_refresh_calendar_list", return_value=False),
            patch.object(engine.gcal_db_adapter, "get_all_gcal_tasks_map", return_value={}),
        ):
            ok = engine.sync_google_calendar(app, silent=True)

        self.assertFalse(ok)
        self.assertEqual(app._last_gcal_sync_outcome, engine.SYNC_OUTCOME_FAILED)
        self.assertEqual(app._last_gcal_sync_error, "fetch")
        self.assertEqual(app._last_gcal_sync_stats["pull_fetch_failures"], 1)

    def test_sync_forces_token_advance_after_three_apply_failure_runs(self):
        class FakeSettings:
            def __init__(self):
                self.data = {
                    "gcal_enabled": "true",
                    "gcal_calendar_id": "primary",
                    "gcal_timezone": "Asia/Seoul",
                    "gcal_sync_token::primary": "old-token",
                    "gcal_sync_token_fails::primary": 0,
                    "gcal_apply_fail_streak::primary": 0,
                    "gcal_bound_calendar_id": "primary",
                }

            def value(self, key, default=None, type=None):
                value = self.data.get(key, default)
                if type is not None and value is not None:
                    return type(value)
                return value

            def setValue(self, key, value):
                self.data[key] = value

        class FakeDate:
            def toString(self, fmt):
                return "2026-03-14"

        class FakeEvent:
            def __init__(self):
                self.id = "evt-1"
                self.summary = "Remote"
                self.description = ""
                self.start_time = "2026-03-14T09:00:00+09:00"
                self.end_time = "2026-03-14T10:00:00+09:00"
                self.location = ""
                self.status = "confirmed"
                self.color_id = None
                self.updated_time = "2026-03-14T00:00:00Z"

        app = SimpleNamespace(
            settings=FakeSettings(),
            current_date=FakeDate(),
            gcal_sync=FakeSyncService(update_result=True),
            update_sync_status=lambda: None,
        )
        app.gcal_sync.fetch_sync_events = lambda sync_token, calendar_id=None: (
            [FakeEvent()],
            "next-token",
            False,
        )

        with (
            patch.object(engine, "_process_google_delete_queue", return_value=(0, 0)),
            patch.object(engine, "_push_local_changes_to_google", return_value=(0, 0, 0)),
            patch.object(engine, "_active_sync_calendar_ids", return_value=["primary"]),
            patch.object(engine, "_should_refresh_calendar_list", return_value=False),
            patch.object(
                engine.gcal_db_adapter,
                "get_all_gcal_tasks_map",
                return_value={"evt-1": ("unified_task", 7)},
            ),
            patch.object(
                engine.task_repo,
                "get_unified_task",
                return_value={
                    "id": 7,
                    "name": "Local",
                    "deadline": "2026-03-14 09:00:00",
                    "end_date": "2026-03-14 10:00:00",
                    "description": "",
                    "location": "",
                    "all_day": 0,
                    "bg_color": None,
                    "gcal_remote_updated_at": "2026-03-13T00:00:00Z",
                    "gcal_dirty": 0,
                },
            ),
            patch.object(engine.gcal_db_adapter, "update_task_from_gcal", return_value=False),
        ):
            ok1 = engine.sync_google_calendar(app, silent=True)
            self.assertTrue(ok1)
            self.assertEqual(app.settings.data["gcal_sync_token::primary"], "old-token")
            self.assertEqual(app.settings.data["gcal_apply_fail_streak::primary"], 1)

            ok2 = engine.sync_google_calendar(app, silent=True)
            self.assertTrue(ok2)
            self.assertEqual(app.settings.data["gcal_sync_token::primary"], "old-token")
            self.assertEqual(app.settings.data["gcal_apply_fail_streak::primary"], 2)

            ok3 = engine.sync_google_calendar(app, silent=True)
            self.assertTrue(ok3)

        self.assertEqual(app.settings.data["gcal_sync_token::primary"], "next-token")
        self.assertEqual(app.settings.data["gcal_apply_fail_streak::primary"], 0)

    def test_active_sync_calendar_ids_include_visible_read_only_gcal(self):
        calendars = [
            {
                "type": "gcal",
                "gcal_calendar_id": "team@group.calendar.google.com",
                "is_active": 1,
                "is_visible": 1,
            },
            {
                "type": "gcal",
                "gcal_calendar_id": "holiday@group.calendar.google.com",
                "is_active": 0,
                "is_visible": 1,
            },
            {
                "type": "gcal",
                "gcal_calendar_id": "removed@group.calendar.google.com",
                "is_active": 0,
                "is_visible": 0,
            },
            {
                "type": "local",
                "gcal_calendar_id": None,
                "is_active": 1,
                "is_visible": 1,
            },
        ]
        with patch(
            "calendar_app.infrastructure.db.calendar_repo.list_calendars", return_value=calendars
        ):
            ids = engine._active_sync_calendar_ids(SimpleNamespace(), "primary")

        self.assertEqual(
            ["primary", "team@group.calendar.google.com", "holiday@group.calendar.google.com"],
            ids,
        )

    def test_active_sync_calendar_ids_deduplicates_resolved_primary_alias(self):
        calendars = [
            {
                "type": "gcal",
                "gcal_calendar_id": "owner@example.com",
                "is_active": 1,
                "is_visible": 1,
            },
            {
                "type": "gcal",
                "gcal_calendar_id": "team@group.calendar.google.com",
                "is_active": 1,
                "is_visible": 1,
            },
        ]

        class FakeSettings:
            def value(self, key, default=None, type=None):
                value = {
                    "gcal_primary_resolved_id": "owner@example.com",
                }.get(key, default)
                if type is not None and value is not None:
                    return type(value)
                return value

        with patch(
            "calendar_app.infrastructure.db.calendar_repo.list_calendars", return_value=calendars
        ):
            ids = engine._active_sync_calendar_ids(
                SimpleNamespace(settings=FakeSettings()), "primary"
            )

        self.assertEqual(
            ["owner@example.com", "team@group.calendar.google.com"],
            ids,
        )

    def test_deactivate_missing_gcal_calendar_hides_calendar(self):
        class FakeSettings:
            def __init__(self):
                self.data = {}

            def setValue(self, key, value):
                self.data[key] = value

            def value(self, key, default=None, type=None):
                value = self.data.get(key, default)
                if type is not None and value is not None:
                    return type(value)
                return value

        app = SimpleNamespace(settings=FakeSettings())
        gcal_id = "missing@group.calendar.google.com"
        cal_db_id = "gcal::missing@group.calendar.google.com"
        with (
            patch(
                "calendar_app.infrastructure.db.calendar_repo.make_gcal_id", return_value=cal_db_id
            ),
            patch(
                "calendar_app.infrastructure.db.calendar_repo.set_calendar_active",
                return_value=True,
            ) as active_mock,
            patch(
                "calendar_app.infrastructure.db.calendar_repo.set_calendar_visible",
                return_value=True,
            ) as visible_mock,
        ):
            engine._deactivate_missing_gcal_calendar(app, gcal_id)

        active_mock.assert_called_once_with(cal_db_id, False)
        visible_mock.assert_called_once_with(cal_db_id, False)
        self.assertEqual("", app.settings.data.get(f"gcal_sync_token::{gcal_id}"))
        self.assertEqual(0, app.settings.data.get(f"gcal_sync_token_fails::{gcal_id}"))
