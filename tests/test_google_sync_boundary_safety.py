# -*- coding: utf-8 -*-
"""Google identities and failures must stay within their owning calendar."""

from contextlib import closing
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt6.QtCore import QSettings

from calendar_app.app_paths import APP_NAME, APP_VENDOR
from calendar_app.infrastructure.db import calendar_repo, database_unified, task_repo
from calendar_app.infrastructure.google_sync import engine, helpers, repository
from calendar_app.infrastructure.google_sync import service as gcal_service
from tests.support import TemporaryDatabaseTestCase
from tests.test_gcal_sync_helpers import FakeSyncService
from tests.test_gcal_sync_integration import FakeDate, FakeGoogleEvent, FakeSettings


class GoogleSyncBoundarySafetyTests(TemporaryDatabaseTestCase):
    def setUp(self):
        super().setUp()
        settings = QSettings(APP_VENDOR, APP_NAME)
        settings.remove("gcal_primary_resolved_id")
        self.addCleanup(settings.remove, "gcal_primary_resolved_id")

    def _add(self, name, source, *, target=None, calendar_id=None, dirty=0):
        return task_repo.create_unified_task(
            {
                "name": name,
                "type": "schedule",
                "deadline": "2026-10-09 00:00:00",
                "end_date": "2026-10-09 00:00:00",
                "all_day": 1,
                "gcal_event_id": "same-event",
                "gcal_source_calendar_id": source,
                "gcal_target_calendar_id": target,
                "calendar_id": calendar_id or (f"gcal::{source}" if source else None),
                "gcal_sync_mode": "remote_mirror",
                "gcal_dirty": dirty,
            }
        )

    def _insert(self, source, name="Remote"):
        return repository.insert_gcal_event_to_unified(
            name,
            "2026-10-09 00:00:00",
            "2026-10-09 00:00:00",
            "same-event",
            all_day=1,
            source_calendar_id=source,
            target_calendar_id=source,
        )

    def _rows(self):
        conn = database_unified.db_manager.get_connection()
        return [dict(row) for row in conn.execute("SELECT * FROM unified_task ORDER BY id")]

    def test_insert_same_event_id_in_another_calendar_preserves_both_rows(self):
        original_id = self._add("Family", "family", target="family")
        new_id = self._insert("team", "Team")
        self.assertNotEqual(original_id, new_id)
        self.assertEqual("Family", task_repo.get_unified_task(original_id)["name"])
        self.assertEqual({"family", "team"}, {r["gcal_source_calendar_id"] for r in self._rows()})

    def test_same_calendar_retry_updates_instead_of_inserting(self):
        original_id = self._add("Old", "family", target="family")
        self.assertEqual(original_id, self._insert("family", "Updated"))
        self.assertEqual(1, len(self._rows()))
        self.assertEqual("Updated", task_repo.get_unified_task(original_id)["name"])

    def test_primary_alias_retry_reuses_account_identity(self):
        original_id = self._add("Alias", "primary", target="primary")
        QSettings(APP_VENDOR, APP_NAME).setValue("gcal_primary_resolved_id", "owner@example.com")
        self.assertEqual(original_id, self._insert("owner@example.com"))
        self.assertEqual(1, len(self._rows()))

    def test_blank_target_does_not_map_concrete_source_as_primary(self):
        row_id = self._add("Family", "family")
        mapping = repository.get_all_gcal_tasks_map()
        self.assertEqual(("unified_task", row_id), mapping["family::same-event"])
        self.assertNotIn("primary::same-event", mapping)

    def test_explicit_owner_is_used_when_legacy_route_fields_are_blank(self):
        row_id = self._add("Family", None, calendar_id="gcal::family")
        mapping = repository.get_all_gcal_tasks_map()
        self.assertEqual(("unified_task", row_id), mapping.get("family::same-event"))
        self.assertNotIn("primary::same-event", mapping)

    def test_pending_move_target_does_not_delete_other_calendar_identity(self):
        source_id = self._add("Moving Family", "family", target="team", dirty=1)
        target_id = self._add("Independent Team", "team", target="team")
        self.assertEqual(0, repository.cleanup_duplicate_gcal_rows())
        self.assertEqual({source_id, target_id}, {row["id"] for row in self._rows()})

    def _pull(self, event, *, failure_status=None, sync_token=""):
        sync = SimpleNamespace(
            is_authenticated=True,
            calendar_id="team",
            time_zone="Asia/Seoul",
            authenticate=lambda *args, **kwargs: True,
            fetch_sync_events=lambda token, calendar_id=None: (
                None
                if failure_status
                else ([] if event is None else event if isinstance(event, list) else [event]),
                None if failure_status else "next-token",
                False,
            ),
            last_error_status=failure_status,
            last_error_kind="fetch" if failure_status else None,
        )
        app = SimpleNamespace(
            settings=FakeSettings(
                {
                    "gcal_enabled": "true",
                    "gcal_calendar_id": "team",
                    "gcal_timezone": "Asia/Seoul",
                    "gcal_bound_calendar_id": "team",
                }
            ),
            current_date=FakeDate("2026-10-09"),
            gcal_sync=sync,
            update_sync_status=lambda: None,
            mark_panel_dirty=lambda **kwargs: None,
        )
        self._last_app = app
        app.settings.setValue("gcal_sync_token::team", sync_token)
        with (
            patch.object(engine, "_get_default_gcal_id", return_value="team"),
            patch.object(engine, "_refresh_resolved_primary_alias_id", return_value="primary"),
            patch.object(engine, "_active_sync_calendar_ids", return_value=["team"]),
            patch.object(engine, "_should_refresh_calendar_list", return_value=False),
            patch.object(engine, "_should_run_incremental_backfill_probe", return_value=False),
            patch.object(engine, "_process_google_delete_queue", return_value=(0, 0)),
            patch.object(engine, "_push_local_changes_to_google", return_value=(0, 0, 0)) as push,
            patch.object(engine, "auto_heal_google_orphans"),
        ):
            result = engine.sync_google_calendar(app, silent=True)
            self._last_push = push
            return result

    def _fetch_page(self, response):
        sync = gcal_service.CalendarSyncService(calendar_id="team")
        sync.is_authenticated = True
        sync.service = object()
        with patch.object(sync, "_execute_request", return_value=response):
            return sync.fetch_sync_events(calendar_id="team")

    def _raw_event(self):
        return {
            "id": "same-event",
            "summary": "Remote",
            "start": {"date": "2026-10-09"},
            "end": {"date": "2026-10-10"},
        }

    def _list_metadata(self, responses):
        sync = gcal_service.CalendarSyncService()
        sync.is_authenticated = True
        sync.service = object()
        with patch.object(sync, "_execute_request", side_effect=responses):
            result = sync.list_accessible_calendars()
        return sync, result

    def test_malformed_calendar_metadata_is_not_coerced_into_account_proof(self):
        entry = {"id": "owner@example.com", "summary": "Owner", "primary": True}
        responses = [
            None,
            [],
            {"items": {}},
            {"items": ""},
            {"items": None},
            {"items": [], "nextPageToken": 42},
            {"items": [], "nextPageToken": None},
        ]
        responses += [
            {"items": [entry | mutation]}
            for mutation in (
                {"id": ""},
                {"id": None},
                {"id": 42},
                {"id": []},
                {"primary": "false"},
                {"primary": "true"},
                {"primary": 1},
                {"primary": None},
                {"summary": 42},
                {"summaryOverride": []},
                {"timeZone": {}},
                {"accessRole": []},
            )
        ]
        responses.append({"items": [entry, None]})
        for response in responses:
            with self.subTest(response=response):
                sync, result = self._list_metadata([response])
                self.assertEqual([], result)
                self.assertEqual("calendar_list", sync.last_error_kind)

    def test_calendar_metadata_pagination_preserves_bool_and_nullable_optionals(self):
        sync, result = self._list_metadata(
            [
                {
                    "items": [
                        {
                            "id": "team",
                            "summary": None,
                            "summaryOverride": None,
                            "timeZone": None,
                            "accessRole": "writerWithoutPrivateAccess",
                        }
                    ],
                    "nextPageToken": "second",
                },
                {
                    "items": [
                        {
                            "id": "owner@example.com",
                            "primary": True,
                            "summary": "Owner",
                            "timeZone": "Asia/Seoul",
                            "accessRole": None,
                        }
                    ]
                },
            ]
        )
        self.assertIsNone(sync.last_error_kind)
        self.assertEqual(2, len(result))
        self.assertIs(result[0]["primary"], True)
        self.assertIs(result[1]["primary"], False)
        self.assertEqual("team", result[1]["summary"])
        self.assertEqual("", result[1]["timeZone"])
        self.assertEqual("writerWithoutPrivateAccess", result[1]["accessRole"])
        self.assertEqual("", result[0]["accessRole"])

    def test_malformed_metadata_final_page_discards_valid_prior_calendars(self):
        sync, result = self._list_metadata(
            [
                {
                    "items": [{"id": "owner@example.com", "primary": True}],
                    "nextPageToken": "second",
                },
                {"items": [{"id": "team", "primary": "false"}]},
            ]
        )
        self.assertEqual([], result)
        self.assertEqual("calendar_list", sync.last_error_kind)

    def test_duplicate_calendar_ids_and_multiple_primaries_reject_the_whole_list(self):
        owner = {"id": "owner@example.com", "primary": True}
        team = {"id": "team", "primary": False}
        other_owner = {"id": "other@example.com", "primary": True}
        for responses in (
            [{"items": [team, team]}],
            [{"items": [team], "nextPageToken": "second"}, {"items": [team]}],
            [{"items": [owner, other_owner]}],
            [{"items": [owner], "nextPageToken": "second"}, {"items": [other_owner]}],
        ):
            with self.subTest(responses=responses):
                sync, result = self._list_metadata(responses)
                self.assertEqual([], result)
                self.assertEqual("calendar_list", sync.last_error_kind)

    def test_subscription_metadata_uses_the_same_account_proof_validator(self):
        sync = gcal_service.CalendarSyncService()
        sync.is_authenticated = True
        sync.service = object()
        with patch.object(
            sync, "_execute_request", return_value={"id": "team", "primary": "false"}
        ):
            self.assertIsNone(sync.subscribe_calendar("team"))
        self.assertEqual("subscribe", sync.last_error_kind)

    def test_malformed_page_envelope_does_not_become_an_empty_full_sync(self):
        for response in (
            {},
            [],
            {"items": {}, "nextSyncToken": "new"},
            {"items": "", "nextSyncToken": "new"},
            {"items": [], "nextSyncToken": 17},
            {"items": [], "nextSyncToken": {}},
            {"items": [], "nextPageToken": 17},
        ):
            with self.subTest(response=response):
                self.assertEqual((None, None, False), self._fetch_page(response))

    def test_missing_items_with_valid_final_token_is_a_valid_empty_page(self):
        self.assertEqual(([], "new", False), self._fetch_page({"nextSyncToken": "new"}))

    def test_invalid_final_page_discards_previously_valid_pages(self):
        sync = gcal_service.CalendarSyncService(calendar_id="team")
        sync.is_authenticated = True
        sync.service = object()
        with patch.object(
            sync,
            "_execute_request",
            side_effect=[
                {"items": [self._raw_event()], "nextPageToken": "second"},
                {"items": []},
            ],
        ):
            self.assertEqual((None, None, False), sync.fetch_sync_events(calendar_id="team"))

    def test_valid_multiple_pages_keep_the_final_sync_token(self):
        sync = gcal_service.CalendarSyncService(calendar_id="team")
        sync.is_authenticated = True
        sync.service = object()
        with patch.object(
            sync,
            "_execute_request",
            side_effect=[
                {"items": [self._raw_event()], "nextPageToken": "second"},
                {"nextSyncToken": "final"},
            ],
        ):
            events, token, reset = sync.fetch_sync_events(calendar_id="team")
        self.assertEqual(1, len(events))
        self.assertEqual("final", token)
        self.assertFalse(reset)

    def test_malformed_remote_events_reject_the_whole_page(self):
        mutations = (
            {"id": None},
            {"id": 123},
            {"summary": 17},
            {"summary": []},
            {"description": []},
            {"location": {}},
            {"start": {}},
            {"start": {"date": "invalid"}},
            {"end": {}},
            {"end": {"date": "2026-02-30"}},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                malformed = self._raw_event() | mutation
                self.assertEqual(
                    (None, None, False),
                    self._fetch_page(
                        {"items": [self._raw_event(), malformed], "nextSyncToken": "new"},
                    ),
                )

    def test_cancelled_id_only_and_nullable_optional_text_are_valid(self):
        events, token, reset = self._fetch_page(
            {
                "items": [
                    {"id": "cancelled", "status": "cancelled"},
                    self._raw_event() | {"summary": None, "description": None, "location": None},
                ],
                "nextSyncToken": "new",
            }
        )
        self.assertEqual("new", token)
        self.assertFalse(reset)
        self.assertEqual("cancelled", events[0].status)
        self.assertEqual(
            ("Untitled", "", ""), (events[1].summary, events[1].description, events[1].location)
        )

    def test_invalid_full_sync_is_validated_before_any_row_is_applied_or_archived(self):
        self._add("Original", "team", target="team")
        second_id = task_repo.create_unified_task(
            {
                "name": "Other",
                "type": "schedule",
                "deadline": "2026-10-10 00:00:00",
                "end_date": "2026-10-10 00:00:00",
                "all_day": 1,
                "gcal_event_id": "other",
                "gcal_source_calendar_id": "team",
                "gcal_target_calendar_id": "team",
                "calendar_id": "gcal::team",
                "gcal_sync_mode": "remote_mirror",
            }
        )
        self.assertIsNotNone(second_id)
        original = self._rows()
        invalids = [
            (None, "2026-10-09", "2026-10-10", "Remote"),
            (123, "2026-10-09", "2026-10-10", "Remote"),
            ("bad", "", "2026-10-10", "Remote"),
            ("bad", "invalid", "2026-10-10", "Remote"),
            ("bad", "2026-10-09", "", "Remote"),
            ("bad", "2026-10-09", "2026-02-30", "Remote"),
            ("bad", "2026-10-09", "2026-10-10", []),
        ]
        for event_id, start, end, summary in invalids:
            with self.subTest(event_id=event_id, start=start, end=end, summary=summary):
                valid = FakeGoogleEvent("same-event", "Changed", "2026-10-09", "2026-10-10")
                invalid = FakeGoogleEvent(event_id, summary, start, end)
                self.assertFalse(self._pull([valid, invalid]))
                self.assertEqual(original, self._rows())
                self.assertEqual("", self._last_app.settings.value("gcal_sync_token::team"))
                self.assertEqual(1, self._last_app._last_gcal_sync_stats["pull_apply_failures"])
                self._last_push.assert_not_called()
        conn = database_unified.db_manager.get_connection()
        self.assertEqual(
            0, conn.execute("SELECT COUNT(*) FROM gcal_deleted_task_archive").fetchone()[0]
        )

    def test_invalid_incremental_end_preserves_token_and_blocks_outbound_push(self):
        self._add("Original", "team", target="team")
        original = self._rows()
        event = FakeGoogleEvent("same-event", "Changed", "2026-10-09T09:00:00+09:00", "")
        self.assertFalse(self._pull(event, sync_token="old-token"))
        self.assertEqual(original, self._rows())
        self.assertEqual("old-token", self._last_app.settings.value("gcal_sync_token::team"))
        self._last_push.assert_not_called()

    def test_pull_same_event_id_in_another_calendar_preserves_original(self):
        original_id = self._add("Family", "family", target="family")
        event = FakeGoogleEvent("same-event", "Team", "2026-10-09", "2026-10-10")
        self.assertTrue(self._pull(event))
        self.assertEqual("Family", task_repo.get_unified_task(original_id)["name"])
        self.assertEqual(2, len(self._rows()))

    def test_cancelled_event_in_another_calendar_does_not_archive_original(self):
        original_id = self._add("Family", "family", target="family")
        event = FakeGoogleEvent("same-event", "Cancelled Team", "", "", status="cancelled")
        self.assertTrue(self._pull(event))
        self.assertIsNotNone(task_repo.get_unified_task(original_id))

    def test_failed_identity_lookup_does_not_fall_through_to_create(self):
        broken = SimpleNamespace(
            cursor=lambda: (_ for _ in ()).throw(sqlite3.OperationalError("busy")),
            rollback=lambda: None,
        )
        with (
            patch.object(repository, "get_connection", return_value=broken),
            patch.object(repository.task_repo, "create_unified_task") as create,
        ):
            self.assertFalse(self._insert("team"))
        create.assert_not_called()

    def test_delete_conflict_keeps_the_request_for_retry(self):
        self.assertTrue(task_repo.queue_gcal_delete("same-event", gcal_calendar_id="team"))
        queue_id = task_repo.get_gcal_delete_queue()[0]["id"]
        sync = SimpleNamespace(
            is_authenticated=True,
            batch_delete_events=lambda ops: [
                {"local_task_id": queue_id, "success": False, "status": 409, "error": "http_409"}
            ],
        )
        self.assertEqual(
            (0, 1), engine._process_google_delete_queue(SimpleNamespace(gcal_sync=sync))
        )
        pending = task_repo.get_gcal_delete_queue()
        self.assertEqual(1, len(pending))
        self.assertEqual(1, pending[0]["retry_count"])

    def test_fetch_404_is_reported_as_incomplete_sync(self):
        original_id = self._add("Cached Team", "team", target="team")
        self.assertFalse(self._pull(None, failure_status=404))
        self.assertEqual(1, self._last_app._last_gcal_sync_stats["pull_fetch_failures"])
        self.assertIsNotNone(task_repo.get_unified_task(original_id))

    def test_inaccessible_calendar_keeps_cached_events_visible(self):
        calendar_repo.upsert_calendar(
            "gcal::team",
            "gcal",
            name="Team",
            is_visible=True,
            is_active=True,
            gcal_calendar_id="team",
            access_role="writer",
        )
        app = SimpleNamespace(settings=FakeSettings())
        engine._deactivate_missing_gcal_calendar(app, "team")
        calendar = calendar_repo.get_calendar("gcal::team")
        self.assertTrue(calendar["is_active"])
        self.assertTrue(calendar["is_visible"])

    def test_primary_alias_list_refresh_preserves_linked_event_identity(self):
        calendar_repo.upsert_calendar(
            "gcal::primary",
            "gcal",
            name="Primary",
            is_active=True,
            gcal_calendar_id="primary",
            access_role="owner",
        )
        row_id = self._add("Linked", "primary", target="primary")
        app = SimpleNamespace(
            settings=FakeSettings({"gcal_primary_resolved_id": "owner@example.com"}),
            gcal_sync=SimpleNamespace(
                is_authenticated=True,
                list_accessible_calendars=lambda: [
                    {
                        "id": "owner@example.com",
                        "summary": "Owner",
                        "accessRole": "owner",
                        "primary": True,
                    },
                ],
            ),
        )
        self.assertTrue(engine._refresh_calendar_list_from_google(app))
        row = task_repo.get_unified_task(row_id)
        self.assertEqual("same-event", row["gcal_event_id"])
        self.assertEqual("owner@example.com", row["gcal_source_calendar_id"])
        self.assertEqual("gcal::owner@example.com", row["calendar_id"])

    def _account_switch_app(self):
        calendar_repo.upsert_calendar(
            "gcal::primary",
            "gcal",
            name="Old account",
            is_default=True,
            is_active=True,
            is_visible=True,
            gcal_calendar_id="primary",
        )
        self._add("Pending old account", "primary", target="team", dirty=1)
        task_repo.queue_gcal_delete("old-delete", gcal_calendar_id="primary")
        return SimpleNamespace(
            settings=FakeSettings(
                {
                    "gcal_enabled": "true",
                    "gcal_calendar_id": "primary",
                    "gcal_bound_calendar_id": "primary",
                    "gcal_primary_resolved_id": "old@example.com",
                    "gcal_sync_token::primary": "old-token",
                }
            ),
            current_date=FakeDate("2026-10-09"),
            update_sync_status=lambda: None,
            gcal_sync=SimpleNamespace(
                is_authenticated=True,
                calendar_id="primary",
                authenticate=Mock(return_value=True),
                list_accessible_calendars=Mock(
                    return_value=[
                        {
                            "id": "new@example.com",
                            "summary": "New account",
                            "primary": True,
                            "accessRole": "owner",
                        },
                    ]
                ),
                batch_delete_events=Mock(return_value=[]),
                fetch_sync_events=Mock(return_value=([], "new-token", False)),
            ),
        )

    def test_primary_account_change_with_legacy_links_stops_before_mutation(self):
        app = self._account_switch_app()
        before_rows = self._rows()
        before_calendars = calendar_repo.list_calendars(include_inactive=True)
        before_queue = task_repo.get_gcal_delete_queue()
        before_settings = dict(app.settings.data)
        with (
            patch.object(engine, "_get_default_gcal_id", return_value="primary"),
            patch.object(engine, "_push_local_changes_to_google", return_value=(0, 0, 0)) as push,
        ):
            self.assertFalse(engine.sync_google_calendar(app, silent=True))
        self.assertEqual("account_mismatch", app._last_gcal_sync_error)
        self.assertEqual(before_rows, self._rows())
        self.assertEqual(before_calendars, calendar_repo.list_calendars(include_inactive=True))
        self.assertEqual(before_queue, task_repo.get_gcal_delete_queue())
        self.assertEqual(before_settings, app.settings.data)
        app.gcal_sync.batch_delete_events.assert_not_called()
        app.gcal_sync.fetch_sync_events.assert_not_called()
        push.assert_not_called()

    def test_calendar_refresh_rejects_cross_account_alias_migration(self):
        app = self._account_switch_app()
        before_rows = self._rows()
        before_calendars = calendar_repo.list_calendars(include_inactive=True)
        before_queue = task_repo.get_gcal_delete_queue()
        before_settings = dict(app.settings.data)
        self.assertFalse(engine._refresh_calendar_list_from_google(app))
        self.assertEqual(before_rows, self._rows())
        self.assertEqual(before_calendars, calendar_repo.list_calendars(include_inactive=True))
        self.assertEqual(before_queue, task_repo.get_gcal_delete_queue())
        self.assertEqual(before_settings, app.settings.data)

    def test_primary_account_change_without_alias_keeps_explicit_calendar_ownership(self):
        self._add("Explicit old owner", "old@example.com", target="old@example.com")
        task_repo.queue_gcal_delete("old-delete", gcal_calendar_id="old@example.com")
        before_rows = self._rows()
        before_queue = task_repo.get_gcal_delete_queue()
        app = SimpleNamespace(
            settings=FakeSettings(
                {
                    "gcal_primary_resolved_id": "old@example.com",
                    "gcal_calendar_id": "old@example.com",
                    "gcal_bound_calendar_id": "old@example.com",
                }
            ),
            gcal_sync=SimpleNamespace(
                is_authenticated=True,
                list_accessible_calendars=lambda: [
                    {"id": "new@example.com", "primary": True},
                ],
            ),
        )
        self.assertEqual("new@example.com", engine._refresh_resolved_primary_alias_id(app))
        self.assertEqual("new@example.com", app.settings.value("gcal_primary_resolved_id"))
        self.assertEqual(before_rows, self._rows())
        self.assertEqual(before_queue, task_repo.get_gcal_delete_queue())

    def test_primary_account_mismatch_detects_a_queue_only_alias(self):
        task_repo.queue_gcal_delete("old-delete", gcal_calendar_id="primary")
        before_queue = task_repo.get_gcal_delete_queue()
        app = SimpleNamespace(
            settings=FakeSettings(
                {
                    "gcal_primary_resolved_id": "old@example.com",
                    "gcal_calendar_id": "old@example.com",
                    "gcal_bound_calendar_id": "old@example.com",
                }
            ),
            gcal_sync=SimpleNamespace(
                is_authenticated=True,
                list_accessible_calendars=lambda: [
                    {"id": "new@example.com", "primary": True},
                ],
            ),
        )
        with self.assertRaisesRegex(RuntimeError, "account_mismatch"):
            engine._refresh_resolved_primary_alias_id(app)
        self.assertEqual("old@example.com", app.settings.value("gcal_primary_resolved_id"))
        self.assertEqual(before_queue, task_repo.get_gcal_delete_queue())
        self.assertTrue(app.gcal_sync._account_identity_mismatch)

    def test_known_account_mismatch_is_not_cleared_by_empty_discovery(self):
        app = self._account_switch_app()
        app.gcal_sync._account_identity_mismatch = True
        app.gcal_sync.list_accessible_calendars.return_value = []
        before_settings = dict(app.settings.data)
        before_queue = task_repo.get_gcal_delete_queue()
        with patch.object(engine, "_get_default_gcal_id", return_value="primary"):
            self.assertFalse(engine.sync_google_calendar(app, silent=True))
        self.assertEqual("account_mismatch", app._last_gcal_sync_error)
        self.assertEqual(before_settings, app.settings.data)
        self.assertEqual(before_queue, task_repo.get_gcal_delete_queue())
        app.gcal_sync.batch_delete_events.assert_not_called()
        app.gcal_sync.fetch_sync_events.assert_not_called()
        app.gcal_sync.list_accessible_calendars.return_value = [
            {"id": "old@example.com", "primary": True},
        ]
        self.assertEqual("old@example.com", engine._refresh_resolved_primary_alias_id(app))
        self.assertFalse(app.gcal_sync._account_identity_mismatch)
        self.assertEqual(before_settings, app.settings.data)
        self.assertEqual(before_queue, task_repo.get_gcal_delete_queue())

    def test_unverified_current_account_blocks_legacy_alias_writes_without_guessing_a_change(self):
        app = self._account_switch_app()
        app.gcal_sync.list_accessible_calendars.return_value = []
        before_settings = dict(app.settings.data)
        before_rows = self._rows()
        before_queue = task_repo.get_gcal_delete_queue()
        with (
            patch.object(engine, "_get_default_gcal_id", return_value="primary"),
            patch.object(engine, "_push_local_changes_to_google", return_value=(0, 0, 0)) as push,
        ):
            self.assertFalse(engine.sync_google_calendar(app, silent=True))
        self.assertEqual("account_unverified", app._last_gcal_sync_error)
        self.assertEqual(before_settings, app.settings.data)
        self.assertEqual(before_rows, self._rows())
        self.assertEqual(before_queue, task_repo.get_gcal_delete_queue())
        app.gcal_sync.batch_delete_events.assert_not_called()
        app.gcal_sync.fetch_sync_events.assert_not_called()
        push.assert_not_called()
        app.gcal_sync.list_accessible_calendars.return_value = [
            {"id": "old@example.com", "primary": True},
        ]
        self.assertEqual("old@example.com", engine._refresh_resolved_primary_alias_id(app))
        self.assertFalse(app.gcal_sync._account_identity_mismatch)
        self.assertEqual(before_settings, app.settings.data)
        self.assertEqual(before_queue, task_repo.get_gcal_delete_queue())

    def test_invalid_primary_metadata_cannot_replace_known_account_identity(self):
        for calendars in (
            [{"id": 42, "primary": True}],
            [{"id": "new@example.com", "primary": "true"}],
            [{"id": "primary", "primary": True}],
            [{"id": " ", "primary": True}],
            [
                {"id": "old@example.com", "primary": True},
                {"id": "new@example.com", "primary": True},
            ],
            [
                {"id": "old@example.com", "primary": True},
                {"id": "old@example.com", "primary": True},
            ],
        ):
            with self.subTest(calendars=calendars):
                app = SimpleNamespace(
                    settings=FakeSettings(
                        {
                            "gcal_primary_resolved_id": "old@example.com",
                            "gcal_calendar_id": "primary",
                        }
                    ),
                    gcal_sync=SimpleNamespace(
                        is_authenticated=True,
                        list_accessible_calendars=lambda calendars=calendars: calendars,
                    ),
                )
                with self.assertRaises(engine._PrimaryAccountMismatchError) as raised:
                    engine._refresh_resolved_primary_alias_id(app)
                self.assertEqual("account_unverified", raised.exception.code)
                self.assertEqual("old@example.com", app.settings.value("gcal_primary_resolved_id"))

    def test_known_account_mismatch_blocks_all_service_remote_write_methods(self):
        sync = gcal_service.CalendarSyncService()
        sync.is_authenticated = True
        sync.service = Mock()
        sync._account_identity_mismatch = True
        with patch.object(sync, "_execute_request") as execute:
            self.assertIsNone(sync.create_event("Title", "2026-10-09", "2026-10-09", all_day=True))
            self.assertFalse(
                sync.update_event("id", "Title", "2026-10-09", "2026-10-09", all_day=True)
            )
            self.assertFalse(sync.delete_event("id"))
            self.assertFalse(sync.move_event("id", "primary", "team"))
            for batch in (
                sync.batch_create_events,
                sync.batch_update_events,
                sync.batch_delete_events,
            ):
                result = batch([{"local_task_id": 1, "event_id": "id"}])
                self.assertEqual(1, len(result))
                self.assertFalse(result[0]["success"])
                self.assertEqual("account_mismatch", result[0]["error"])
        execute.assert_not_called()
        sync.service.events.assert_not_called()
        sync.service.new_batch_http_request.assert_not_called()
        self.assertEqual("account_mismatch", sync.last_error_kind)

    def test_alias_migration_preserves_preferences_pending_move_and_delete(self):
        calendar_repo.upsert_calendar(
            "gcal::primary",
            "gcal",
            name="Primary",
            is_default=True,
            is_active=False,
            is_visible=False,
            gcal_calendar_id="primary",
        )
        calendar_repo.upsert_calendar(
            "gcal::owner@example.com", "gcal", name="Owner", gcal_calendar_id="owner@example.com"
        )
        row_id = self._add("Moving", "primary", target="team", calendar_id="gcal::team", dirty=1)
        task_repo.queue_gcal_delete("queued-delete", gcal_calendar_id="primary")
        self.assertTrue(
            repository.migrate_primary_calendar_alias(
                "owner@example.com",
                preserve_alias_preferences=True,
            )
        )
        row = task_repo.get_unified_task(row_id)
        self.assertEqual("same-event", row["gcal_event_id"])
        self.assertEqual("owner@example.com", row["gcal_source_calendar_id"])
        self.assertEqual("team", row["gcal_target_calendar_id"])
        self.assertEqual("gcal::team", row["calendar_id"])
        self.assertEqual(1, row["gcal_dirty"])
        calendar = calendar_repo.get_calendar("gcal::owner@example.com")
        self.assertEqual(
            (0, 0, 1), (calendar["is_active"], calendar["is_visible"], calendar["is_default"])
        )
        self.assertEqual(
            "owner@example.com", task_repo.get_gcal_delete_queue()[0]["gcal_calendar_id"]
        )

    def test_alias_migration_identity_collision_rolls_back_every_change(self):
        calendar_repo.upsert_calendar(
            "gcal::primary", "gcal", name="Primary", is_visible=False, gcal_calendar_id="primary"
        )
        calendar_repo.upsert_calendar(
            "gcal::owner@example.com", "gcal", name="Owner", gcal_calendar_id="owner@example.com"
        )
        real_id = self._add("Concrete", "owner@example.com", target="owner@example.com")
        alias_id = self._add("Alias", "primary", target="primary")
        self.assertIsNotNone(alias_id)
        task_repo.queue_gcal_delete("queued-delete", gcal_calendar_id="primary")
        self.assertFalse(
            repository.migrate_primary_calendar_alias(
                "owner@example.com",
                preserve_alias_preferences=True,
            )
        )
        self.assertEqual("primary", task_repo.get_unified_task(alias_id)["gcal_source_calendar_id"])
        self.assertEqual("Concrete", task_repo.get_unified_task(real_id)["name"])
        self.assertIsNotNone(calendar_repo.get_calendar("gcal::primary"))
        self.assertTrue(calendar_repo.get_calendar("gcal::owner@example.com")["is_visible"])
        self.assertEqual("primary", task_repo.get_gcal_delete_queue()[0]["gcal_calendar_id"])

    def test_duplicate_cleanup_preserves_unsent_changes_on_alias_copy(self):
        real_id = self._add("Remote Version", "owner@example.com", target="owner@example.com")
        alias_id = self._add("Unsent Edit", "primary", target="primary", dirty=1)
        self.assertIsNotNone(alias_id)
        QSettings(APP_VENDOR, APP_NAME).setValue("gcal_primary_resolved_id", "owner@example.com")
        self.assertEqual(0, repository.cleanup_duplicate_gcal_rows())
        self.assertEqual({alias_id, real_id}, {row["id"] for row in self._rows()})

    def test_missing_batch_callback_is_counted_as_an_incomplete_delete(self):
        task_repo.queue_gcal_delete("first", gcal_calendar_id="team")
        task_repo.queue_gcal_delete("second", gcal_calendar_id="team")
        queue = task_repo.get_gcal_delete_queue()
        sync = SimpleNamespace(
            is_authenticated=True,
            batch_delete_events=lambda ops: [{"local_task_id": queue[0]["id"], "success": True}],
        )
        self.assertEqual(
            (1, 1), engine._process_google_delete_queue(SimpleNamespace(gcal_sync=sync))
        )
        pending = task_repo.get_gcal_delete_queue()
        self.assertEqual(["second"], [row["gcal_event_id"] for row in pending])

    def test_pending_move_is_preserved_when_original_disappears_during_full_pull(self):
        row_id = self._add("Moving", "team", target="family", calendar_id="gcal::family", dirty=1)
        self._pull(None)
        row = task_repo.get_unified_task(row_id)
        self.assertIsNotNone(row)
        self.assertEqual(1, row["gcal_dirty"])
        self.assertEqual("family", row["gcal_target_calendar_id"])

    def test_cancelled_only_pull_commits_the_archive_before_advancing_token(self):
        row_id = self._add("Cancelled", "team", target="team")
        event = FakeGoogleEvent("same-event", "Cancelled", "", "", status="cancelled")
        self.assertTrue(self._pull(event))
        with closing(sqlite3.connect(database_unified.DB_PATH)) as observer:
            self.assertIsNone(
                observer.execute("SELECT id FROM unified_task WHERE id=?", (row_id,)).fetchone()
            )
            self.assertEqual(
                1, observer.execute("SELECT COUNT(*) FROM gcal_deleted_task_archive").fetchone()[0]
            )

    def test_failed_cancelled_archive_does_not_advance_the_sync_token(self):
        self._add("Cancelled", "team", target="team")
        event = FakeGoogleEvent("same-event", "Cancelled", "", "", status="cancelled")
        with patch.object(repository, "delete_task_by_gcal_id", return_value=False):
            self.assertFalse(self._pull(event))
        self.assertNotEqual("next-token", self._last_app.settings.value("gcal_sync_token::team"))

    def test_failed_local_delete_completion_is_not_reported_as_success(self):
        task_repo.queue_gcal_delete("first", gcal_calendar_id="team")
        queue_id = task_repo.get_gcal_delete_queue()[0]["id"]
        sync = SimpleNamespace(
            is_authenticated=True,
            batch_delete_events=lambda ops: [{"local_task_id": queue_id, "success": True}],
        )
        with patch.object(task_repo, "mark_gcal_delete_done", return_value=False):
            self.assertEqual(
                (0, 1), engine._process_google_delete_queue(SimpleNamespace(gcal_sync=sync))
            )
        self.assertEqual(1, len(task_repo.get_gcal_delete_queue()))

    def test_push_404_does_not_modify_same_id_on_another_calendar(self):
        row_id = self._add("Family", "family", target="family")
        sync = FakeSyncService(
            update_result=False,
            error_kind="not_found",
            calendar_id="primary",
            accessible_calendar_ids=["primary", "team"],
            update_results_by_calendar={"family": False, "primary": False, "team": True},
        )
        app = SimpleNamespace(
            settings=FakeSettings({"gcal_enabled": "true", "gcal_calendar_id": "primary"}),
            gcal_sync=sync,
        )
        result = helpers.sync_task_to_google(
            app, task_repo.get_unified_task(row_id), create_if_missing=False
        )
        self.assertFalse(result.success)
        self.assertNotIn("team", sync.update_calendar_ids)
        self.assertEqual("family", task_repo.get_unified_task(row_id)["gcal_source_calendar_id"])

    def test_recovery_accepts_only_aliases_of_the_same_account_calendar(self):
        sync = SimpleNamespace(calendar_id="owner@example.com")
        settings = FakeSettings(
            {
                "gcal_calendar_id": "owner@example.com",
                "gcal_primary_resolved_id": "owner@example.com",
            }
        )
        self.assertEqual(
            ["owner@example.com"],
            helpers._candidate_recovery_calendar_ids(sync, settings, "primary"),
        )

    def _scan_unlinked(self):
        event = FakeGoogleEvent("same-event", "Ordinary Google Event", "2026-10-09", "2026-10-10")
        app = SimpleNamespace(
            settings=FakeSettings({"gcal_enabled": "true", "gcal_calendar_id": "team"}),
            gcal_sync=SimpleNamespace(
                is_authenticated=True, fetch_events=lambda *args, **kwargs: [event]
            ),
        )
        with patch.object(engine, "_active_sync_calendar_ids", return_value=["team"]):
            return engine.scan_orphan_remote_events(app)

    def test_unlinked_scan_distinguishes_same_event_id_in_other_calendars(self):
        self._add("Family", "family", target="family")
        self.assertEqual(["team"], [row["gcal_calendar_id"] for row in self._scan_unlinked()])

    def test_unlinked_scan_delete_queue_exclusion_is_calendar_scoped(self):
        task_repo.queue_gcal_delete("same-event", gcal_calendar_id="family")
        self.assertEqual(["team"], [row["gcal_calendar_id"] for row in self._scan_unlinked()])

    def test_unlinked_remote_event_is_never_automatically_queued_for_deletion(self):
        app = SimpleNamespace(
            settings=FakeSettings({"gcal_enabled": "true"}),
            gcal_sync=SimpleNamespace(is_authenticated=True),
        )
        orphan = {
            "gcal_event_id": "ordinary-event",
            "gcal_calendar_id": "team",
            "summary": "Created in Google",
            "start": "2026-10-09",
        }
        with (
            patch.object(engine, "scan_orphan_remote_events", return_value=[orphan]),
            patch.object(task_repo, "find_orphan_candidate", return_value=None),
            patch.object(task_repo, "queue_gcal_delete") as delete,
        ):
            engine.auto_heal_google_orphans(app)
        delete.assert_not_called()

    def test_unlinked_remote_event_is_not_auto_linked_by_same_title_and_date(self):
        app = SimpleNamespace(
            settings=FakeSettings({"gcal_enabled": "true"}),
            gcal_sync=SimpleNamespace(is_authenticated=True),
        )
        orphan = {
            "gcal_event_id": "ordinary-event",
            "gcal_calendar_id": "team",
            "summary": "Same Title",
            "start": "2026-10-09",
        }
        with (
            patch.object(engine, "scan_orphan_remote_events", return_value=[orphan]),
            patch.object(
                task_repo,
                "find_orphan_candidate",
                side_effect=lambda *args: {"id": 1} if len(args) == 2 else None,
            ),
            patch.object(task_repo, "mark_unified_task_gcal_synced") as link,
        ):
            engine.auto_heal_google_orphans(app)
        link.assert_not_called()
