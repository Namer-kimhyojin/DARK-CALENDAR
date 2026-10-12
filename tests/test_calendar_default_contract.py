# -*- coding: utf-8 -*-
"""Default save destination and Google import preferences must stay independent."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QApplication, QMessageBox

from calendar_app.application.calendar_preferences import (
    set_default_calendar,
    set_google_calendar_import_selection,
)
from calendar_app.infrastructure.db import calendar_repo, task_repo
from calendar_app.infrastructure.google_sync import engine
from calendar_app.infrastructure.google_sync.common import (
    get_default_gcal_calendar_id,
    resolve_task_target_calendar_id,
)
from tests.support import TemporaryDatabaseTestCase


class FakeSettings:
    def __init__(self, values=None):
        self.data = dict(values or {})

    def value(self, key, default=None, type=None):
        value = self.data.get(key, default)
        return type(value) if type is not None and value is not None else value

    def setValue(self, key, value):
        self.data[key] = value


class CalendarDefaultContractTests(TemporaryDatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.conn = calendar_repo.db_manager.get_connection()
        self.conn.execute("DELETE FROM calendar")
        self.conn.commit()
        self.add_calendar("local::default", "local", default=True)

    def add_calendar(
        self, identity, provider, *, default=False, active=True, visible=True, role=None, order=1
    ):
        self.assertTrue(
            calendar_repo.upsert_calendar(
                identity,
                provider,
                identity,
                is_default=default,
                is_active=active,
                is_visible=visible,
                access_role=role,
                sort_order=order,
                gcal_calendar_id=identity.removeprefix("gcal::") if provider == "gcal" else None,
            )
        )

    def snapshot(self):
        return [dict(row) for row in self.conn.execute("SELECT * FROM calendar ORDER BY id")]

    def test_google_default_beats_stale_legacy_target(self):
        self.add_calendar("gcal::family", "gcal", role="owner")
        self.add_calendar("gcal::team", "gcal", role="writer")
        self.assertTrue(calendar_repo.set_calendar_default("gcal::family"))
        settings = FakeSettings({"gcal_calendar_id": "team"})
        self.assertEqual(get_default_gcal_calendar_id(settings), "family")
        self.assertEqual(engine._get_default_gcal_id(SimpleNamespace(settings=settings)), "family")

    def test_global_selection_updates_google_compatibility_without_touching_primary_identity(self):
        self.add_calendar("gcal::team", "gcal", role="writer", visible=False)
        settings = FakeSettings({"gcal_primary_resolved_id": "owner@example.test"})
        self.assertTrue(set_default_calendar("gcal::team", settings, repository=calendar_repo))
        self.assertEqual(settings.data["gcal_calendar_id"], "team")
        self.assertEqual(settings.data["gcal_primary_resolved_id"], "owner@example.test")
        self.assertFalse(calendar_repo.get_calendar("gcal::team")["is_visible"])

    def test_local_default_keeps_local_save_route_and_google_connection_fallback(self):
        self.add_calendar("gcal::team", "gcal", role="writer")
        settings = FakeSettings({"gcal_calendar_id": "team"})
        self.assertTrue(set_default_calendar("local::default", settings, repository=calendar_repo))
        self.assertEqual(calendar_repo.get_default_calendar()["id"], "local::default")
        self.assertEqual(settings.data["gcal_calendar_id"], "team")
        self.assertEqual(get_default_gcal_calendar_id(settings), "team")
        self.assertIsNone(
            resolve_task_target_calendar_id({"calendar_id": "local::default"}, "team")
        )

    def test_primary_alias_never_resolves_to_the_selected_team(self):
        self.add_calendar("gcal::primary", "gcal", role="owner")
        self.add_calendar("gcal::team", "gcal", role="writer")
        settings = FakeSettings(
            {"gcal_calendar_id": "team", "gcal_primary_resolved_id": "owner@example.test"}
        )
        self.assertTrue(calendar_repo.set_calendar_default("gcal::primary"))
        self.assertEqual(get_default_gcal_calendar_id(settings), "primary")
        app = SimpleNamespace(settings=settings)
        self.assertEqual(engine._get_default_gcal_id(app), "owner@example.test")
        self.assertTrue(calendar_repo.set_calendar_default("gcal::team"))
        self.assertEqual(engine._resolved_primary_alias_id(app), "owner@example.test")

    def test_existing_task_target_and_other_provider_owner_survive_default_change(self):
        self.add_calendar("gcal::team", "gcal", role="writer")
        self.assertTrue(calendar_repo.set_calendar_default("gcal::team"))
        task = {
            "calendar_id": "gcal::family",
            "gcal_event_id": "event-old",
            "gcal_target_calendar_id": "family",
        }
        before = dict(task)
        self.assertEqual(resolve_task_target_calendar_id(task, "team"), "family")
        self.assertEqual(task, before)
        for provider in ("outlook", "caldav"):
            self.assertIsNone(
                resolve_task_target_calendar_id(
                    {**task, "calendar_id": provider + "::fixture"}, "team"
                )
            )

    def test_unavailable_default_requests_preserve_the_current_default(self):
        candidates = (
            ("ics::feed", "ics", True, None),
            ("gcal::readonly", "gcal", True, "reader"),
            ("gcal::inactive", "gcal", False, "writer"),
            ("outlook::readonly", "outlook", True, "reader"),
            ("caldav::readonly", "caldav", True, "reader"),
            ("local::inactive", "local", False, None),
        )
        for identity, provider, active, role in candidates:
            self.add_calendar(identity, provider, active=active, role=role)
        before = self.snapshot()
        for identity, *_ in candidates:
            self.assertFalse(calendar_repo.set_calendar_default(identity))
        self.assertFalse(calendar_repo.set_calendar_default("missing"))
        self.assertEqual(self.snapshot(), before)

    def test_writable_list_uses_actual_permissions_and_preserves_hidden_choices(self):
        self.add_calendar("gcal::reader", "gcal", active=True, role="reader")
        self.add_calendar("gcal::hidden", "gcal", visible=False, role="writer")
        self.add_calendar("caldav::inactive", "caldav", active=False, role="writer")
        keys = {row["id"] for row in calendar_repo.get_writable_calendars()}
        self.assertEqual(keys, {"local::default", "gcal::hidden"})

    def test_default_read_falls_back_from_invalid_flag_without_modifying_records(self):
        self.add_calendar("gcal::reader", "gcal", active=True, role="reader")
        self.conn.execute(
            "UPDATE calendar SET is_default=CASE WHEN id='gcal::reader' THEN 1 ELSE 0 END"
        )
        self.conn.commit()
        before = self.snapshot()
        self.assertEqual(calendar_repo.get_default_calendar()["id"], "local::default")
        self.assertEqual(self.snapshot(), before)

    def test_known_readonly_legacy_target_is_not_a_google_fallback(self):
        self.add_calendar("gcal::reader", "gcal", role="reader")
        self.add_calendar("gcal::writer", "gcal", role="writer")
        self.assertEqual(
            get_default_gcal_calendar_id(FakeSettings({"gcal_calendar_id": "reader"})), "writer"
        )

    def test_unknown_premigration_legacy_target_remains_compatible(self):
        self.assertEqual(
            get_default_gcal_calendar_id(FakeSettings({"gcal_calendar_id": "old-team"})), "old-team"
        )

    def test_unmarked_database_fallback_does_not_replace_a_legacy_selected_google_target(self):
        self.conn.execute("DELETE FROM calendar")
        self.conn.commit()
        self.add_calendar("gcal::family", "gcal", role="writer", order=0)
        self.add_calendar("gcal::team", "gcal", role="writer", order=1)
        self.assertEqual(calendar_repo.get_default_calendar()["id"], "gcal::family")
        self.assertEqual(
            get_default_gcal_calendar_id(FakeSettings({"gcal_calendar_id": "team"})), "team"
        )

    def test_default_change_rolls_back_on_a_database_failure(self):
        self.add_calendar("gcal::team", "gcal", role="writer")
        self.conn.execute(
            "CREATE TRIGGER fail_default BEFORE UPDATE OF is_default ON calendar BEGIN SELECT RAISE(FAIL, 'fixture'); END"
        )
        before = self.snapshot()
        self.assertFalse(calendar_repo.set_calendar_default("gcal::team"))
        self.assertEqual(self.snapshot(), before)

    def test_import_selection_is_atomic_for_unknown_and_other_provider_rows(self):
        self.add_calendar("gcal::team", "gcal", role="writer")
        before = self.snapshot()
        for invalid in ("missing", "local::default"):
            self.assertFalse(
                calendar_repo.set_google_calendar_import_selection(
                    {"gcal::team": False, invalid: True}
                )
            )
            self.assertEqual(self.snapshot(), before)

    def test_disabling_default_import_selects_local_default_and_preserves_events(self):
        self.add_calendar("gcal::team", "gcal", role="writer")
        self.assertTrue(calendar_repo.set_calendar_default("gcal::team"))
        task_id = task_repo.create_unified_task(
            {
                "name": "Existing",
                "type": "schedule",
                "deadline": "2026-10-07 09:00:00",
                "calendar_id": "gcal::team",
                "gcal_event_id": "old-event",
                "gcal_source_calendar_id": "team",
                "gcal_target_calendar_id": "team",
            }
        )
        before_task = dict(task_repo.get_unified_task(task_id))
        settings = FakeSettings({"gcal_calendar_id": "team"})
        result = set_google_calendar_import_selection(
            {"gcal::team": False}, settings, repository=calendar_repo
        )
        self.assertTrue(result.success and result.default_changed)
        self.assertEqual(result.default_calendar["id"], "local::default")
        self.assertEqual(calendar_repo.get_default_calendar()["id"], "local::default")
        self.assertEqual(dict(task_repo.get_unified_task(task_id)), before_task)
        self.assertTrue(settings.data["gcal_import_selection_configured"])

    def test_last_writable_default_cannot_be_disabled_without_a_replacement(self):
        self.conn.execute("DELETE FROM calendar")
        self.conn.commit()
        self.add_calendar("gcal::only", "gcal", role="writer", default=True)
        before = self.snapshot()
        result = set_google_calendar_import_selection(
            {"gcal::only": False}, FakeSettings(), repository=calendar_repo
        )
        self.assertFalse(result.success)
        self.assertEqual(self.snapshot(), before)

    def test_readonly_google_may_be_imported_without_becoming_default(self):
        self.add_calendar("gcal::holiday", "gcal", active=False, role="reader")
        result = set_google_calendar_import_selection(
            {"gcal::holiday": True}, FakeSettings(), repository=calendar_repo
        )
        self.assertTrue(result.success)
        self.assertFalse(result.default_changed)
        self.assertTrue(calendar_repo.get_calendar("gcal::holiday")["is_active"])
        self.assertEqual(calendar_repo.get_default_calendar()["id"], "local::default")
        self.assertFalse(calendar_repo.set_calendar_default("gcal::holiday"))

    def test_explicit_import_selection_excludes_visible_inactive_and_bound_calendars(self):
        self.add_calendar("gcal::team", "gcal", active=False, visible=True, role="writer")
        self.add_calendar("gcal::holiday", "gcal", active=True, visible=False, role="reader")
        app = SimpleNamespace(settings=FakeSettings({"gcal_import_selection_configured": True}))
        self.assertEqual(engine._active_sync_calendar_ids(app, "team"), ["holiday"])

    def test_explicit_empty_import_selection_does_not_reintroduce_primary(self):
        self.add_calendar("gcal::team", "gcal", active=False, role="writer")
        app = SimpleNamespace(settings=FakeSettings({"gcal_import_selection_configured": "true"}))
        self.assertEqual(engine._active_sync_calendar_ids(app, "primary"), [])

    def test_legacy_readonly_visible_import_compatibility_is_retained_before_first_save(self):
        self.add_calendar("gcal::holiday", "gcal", active=False, visible=True, role="reader")
        app = SimpleNamespace(settings=FakeSettings({"gcal_import_selection_configured": "false"}))
        self.assertEqual(engine._active_sync_calendar_ids(app, "primary"), ["primary", "holiday"])

    def test_calendar_discovery_preserves_import_choices_and_does_not_select_new_calendars(self):
        self.add_calendar("gcal::team", "gcal", active=False, role="writer")
        sync = Mock(is_authenticated=True)
        sync.list_accessible_calendars.return_value = [
            {"id": "team", "summary": "Team", "accessRole": "writer"},
            {"id": "new", "summary": "New", "accessRole": "owner"},
        ]
        app = SimpleNamespace(
            settings=FakeSettings({"gcal_import_selection_configured": True}), gcal_sync=sync
        )
        self.assertTrue(engine._refresh_calendar_list_from_google(app))
        self.assertFalse(calendar_repo.get_calendar("gcal::team")["is_active"])
        self.assertFalse(calendar_repo.get_calendar("gcal::new")["is_active"])

    def test_default_binding_change_preserves_pending_deletions_and_task_links(self):
        self.conn.execute(
            "INSERT INTO gcal_delete_queue(gcal_event_id,gcal_calendar_id) VALUES('old-event','family')"
        )
        self.conn.commit()
        before = [tuple(row) for row in self.conn.execute("SELECT * FROM gcal_delete_queue")]
        app = SimpleNamespace(settings=FakeSettings({"gcal_bound_calendar_id": "family"}))
        self.assertTrue(engine._apply_calendar_binding_change(app, "family", "team"))
        self.assertEqual(
            [tuple(row) for row in self.conn.execute("SELECT * FROM gcal_delete_queue")], before
        )

    def test_import_selection_repairs_a_missing_default_after_permission_refresh(self):
        self.add_calendar("gcal::former_writer", "gcal", role="reader")
        self.conn.execute("UPDATE calendar SET is_default=0")
        self.conn.commit()
        result = set_google_calendar_import_selection(
            {"gcal::former_writer": True}, FakeSettings(), repository=calendar_repo
        )
        self.assertTrue(result.success)
        self.assertEqual(calendar_repo.get_default_calendar()["id"], "local::default")
        self.assertTrue(calendar_repo.get_calendar("local::default")["is_default"])
        self.assertFalse(calendar_repo.get_calendar("gcal::former_writer")["is_default"])


class CalendarDefaultDialogTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.conn = calendar_repo.db_manager.get_connection()
        self.conn.execute("DELETE FROM calendar")
        self.conn.commit()
        for identity, kind, role in (
            ("local::default", "local", None),
            ("gcal::family", "gcal", "owner"),
            ("gcal::team", "gcal", "writer"),
            ("gcal::holiday", "gcal", "reader"),
        ):
            self.assertTrue(
                calendar_repo.upsert_calendar(
                    identity,
                    kind,
                    identity,
                    access_role=role,
                    gcal_calendar_id=identity.removeprefix("gcal::") if kind == "gcal" else None,
                    is_default=identity == "local::default",
                    is_visible=identity != "gcal::team",
                )
            )
        self.dialogs = []
        self.addCleanup(self.close_dialogs)

    def close_dialogs(self):
        for dialog in self.dialogs:
            dialog.close()
            dialog.deleteLater()
        self.app.processEvents()

    def dialog(self, **kwargs):
        from calendar_app.presentation.dialogs.task_dialog_unified import UnifiedTaskDialog

        dialog = UnifiedTaskDialog(initial_date=QDate(2026, 10, 7), task_type="schedule", **kwargs)
        self.dialogs.append(dialog)
        return dialog

    def save(self, dialog, *, edit=False):
        with (
            patch.object(QMessageBox, "information"),
            patch.object(QMessageBox, "critical") as failure,
            patch.object(QMessageBox, "question") as question,
        ):
            dialog._save_changes() if edit else dialog._create_task()
        failure.assert_not_called()
        question.assert_not_called()

    def existing(self, identity="gcal::family", *, linked=True):
        return task_repo.create_unified_task(
            {
                "name": "Existing",
                "type": "schedule",
                "deadline": "2026-10-07 09:00:00",
                "end_date": "2026-10-07 10:00:00",
                "calendar_id": identity,
                "gcal_event_id": "old-event" if linked else None,
                "gcal_source_calendar_id": identity.removeprefix("gcal::"),
                "gcal_target_calendar_id": identity.removeprefix("gcal::"),
                "gcal_sync_mode": "local_owned",
            }
        )

    def test_create_uses_the_main_default_even_when_it_is_hidden(self):
        self.assertTrue(calendar_repo.set_calendar_default("gcal::team"))
        dialog = self.dialog()
        self.assertEqual(dialog._get_selected_calendar_id(), "gcal::team")
        dialog.name_edit.setText("New in hidden default")
        self.save(dialog)
        saved = task_repo.get_unified_task(dialog._saved_task_id)
        self.assertEqual(saved["calendar_id"], "gcal::team")
        self.assertEqual(resolve_task_target_calendar_id(saved, "family"), "team")

    def test_copy_prefill_uses_the_current_default_and_clears_remote_identity(self):
        original_id = self.existing("gcal::holiday")
        original = task_repo.get_unified_task(original_id)
        self.assertTrue(calendar_repo.set_calendar_default("gcal::team"))
        dialog = self.dialog(prefill_dict=original)
        self.assertEqual(dialog._get_selected_calendar_id(), "gcal::team")
        self.save(dialog)
        copied = task_repo.get_unified_task(dialog._saved_task_id)
        self.assertEqual(copied["calendar_id"], "gcal::team")
        self.assertIsNone(copied["gcal_event_id"])
        self.assertIsNone(copied["gcal_source_calendar_id"])
        self.assertEqual(task_repo.get_unified_task(original_id), original)

    def test_edit_paused_owner_keeps_original_calendar_and_google_link(self):
        original_id = self.existing()
        self.assertTrue(calendar_repo.set_calendar_active("gcal::family", False))
        dialog = self.dialog(task_id=original_id)
        self.assertEqual(dialog._get_selected_calendar_id(), "gcal::family")
        item = dialog.calendar_combo.model().item(dialog.calendar_combo.currentIndex())
        self.assertFalse(item.isEnabled())
        self.assertTrue(item.toolTip())
        dialog.name_edit.setText("Only the title changed")
        self.save(dialog, edit=True)
        saved = task_repo.get_unified_task(original_id)
        self.assertEqual(saved["calendar_id"], "gcal::family")
        self.assertEqual(saved["gcal_target_calendar_id"], "family")
        self.assertEqual(saved["gcal_event_id"], "old-event")

    def test_explicit_move_persists_the_new_target_and_preserves_previous_source(self):
        original_id = self.existing()
        dialog = self.dialog(task_id=original_id)
        dialog.calendar_combo.setCurrentIndex(dialog.calendar_combo.findData("gcal::team"))
        self.save(dialog, edit=True)
        saved = task_repo.get_unified_task(original_id)
        self.assertEqual(saved["calendar_id"], "gcal::team")
        self.assertEqual(saved["gcal_target_calendar_id"], "team")
        self.assertEqual(saved["gcal_source_calendar_id"], "family")
        self.assertEqual(resolve_task_target_calendar_id(saved, "family"), "team")
        self.assertEqual(
            dialog.post_commit_gcal_sync_overrides["_previous_gcal_calendar_id"], "family"
        )

    def test_unsynced_move_to_local_removes_the_stale_google_target(self):
        original_id = self.existing(linked=False)
        dialog = self.dialog(task_id=original_id)
        dialog.calendar_combo.setCurrentIndex(dialog.calendar_combo.findData("local::default"))
        self.save(dialog, edit=True)
        saved = task_repo.get_unified_task(original_id)
        self.assertEqual(saved["calendar_id"], "local::default")
        self.assertIsNone(saved["gcal_target_calendar_id"])
        self.assertIsNone(saved["gcal_source_calendar_id"])
        self.assertIsNone(resolve_task_target_calendar_id(saved, "team"))
        self.assertTrue(dialog.skip_post_commit_gcal_sync)
