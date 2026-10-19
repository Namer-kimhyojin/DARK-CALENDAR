# -*- coding: utf-8 -*-
"""Imported templates must be complete or leave no imported rows behind."""

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from calendar_app.infrastructure.db import checklist_template_repo as repo
from calendar_app.presentation.dialogs import checklist_manager_dialog_advanced as ui
from tests.support import TemporaryDatabaseTestCase


class TestChecklistImportAtomicity(TemporaryDatabaseTestCase):
    def import_payload(self, payload):
        filename = self._tmpdir.name + "/import.json"
        with open(filename, "w", encoding="utf-8", errors="strict") as stream:
            json.dump(payload, stream)
        owner = SimpleNamespace(
            current_template_id=99,
            load_templates=Mock(),
            _select_template_in_list=Mock(),
            checklist_changed=SimpleNamespace(emit=Mock()),
        )
        with (
            patch.object(ui.QFileDialog, "getOpenFileName", return_value=(filename, "")),
            patch.object(ui.QMessageBox, "information") as success,
            patch.object(ui.QMessageBox, "critical") as error,
        ):
            ui.ChecklistManagerDialog._import_template(owner)
        return owner, success, error

    @staticmethod
    def payload():
        return {
            "template": {"name": "Imported", "checklist_type": "list"},
            "items": [
                {"item_text": "First", "is_required": 1},
                {"item_text": "Second"},
            ],
        }

    def test_valid_import_preserves_item_order_and_reports_success(self):
        owner, success, error = self.import_payload(self.payload())
        rows = repo.get_checklist_items(owner.current_template_id)
        assert [row["item_text"] for row in rows] == ["First", "Second"]
        assert [row["item_order"] for row in rows] == [0, 1]
        assert rows[0]["is_required"] == 1
        success.assert_called_once()
        error.assert_not_called()
        owner.checklist_changed.emit.assert_called_once()

    def test_malformed_second_item_does_not_leave_a_partial_template(self):
        payload = self.payload()
        payload["items"][1] = None
        owner, success, error = self.import_payload(payload)
        assert repo.get_all_checklist_templates() == []
        assert (
            repo.get_connection().execute("SELECT count(*) FROM checklist_item").fetchone()[0] == 0
        )
        assert owner.current_template_id == 99
        success.assert_not_called()
        error.assert_called_once()

    def test_database_failure_rolls_back_all_imported_rows(self):
        conn = repo.get_connection()
        conn.execute(
            "CREATE TRIGGER block_second BEFORE INSERT ON checklist_item "
            "WHEN NEW.item_text='Second' BEGIN SELECT RAISE(ABORT, 'blocked'); END"
        )
        conn.commit()
        owner, success, error = self.import_payload(self.payload())
        assert repo.get_all_checklist_templates() == []
        assert conn.execute("SELECT count(*) FROM checklist_item").fetchone()[0] == 0
        assert not conn.in_transaction
        assert owner.current_template_id == 99
        success.assert_not_called()
        error.assert_called_once()

    def test_invalid_required_flag_is_rejected_before_writing(self):
        payload = self.payload()
        payload["items"][1]["is_required"] = "false"
        _, success, error = self.import_payload(payload)
        assert repo.get_all_checklist_templates() == []
        success.assert_not_called()
        error.assert_called_once()

    def test_success_preserves_the_callers_uncommitted_transaction(self):
        conn = repo.get_connection()
        conn.execute("INSERT INTO checklist_template(name) VALUES ('Outer')")
        imported = repo.import_checklist_template(self.payload())
        assert imported is not None
        assert conn.in_transaction
        assert len(repo.get_all_checklist_templates()) == 2
        conn.rollback()
        assert repo.get_all_checklist_templates() == []

    def test_failure_preserves_the_callers_uncommitted_rows(self):
        conn = repo.get_connection()
        conn.execute(
            "CREATE TRIGGER block_second BEFORE INSERT ON checklist_item "
            "WHEN NEW.item_text='Second' BEGIN SELECT RAISE(ABORT, 'blocked'); END"
        )
        conn.commit()
        conn.execute("INSERT INTO checklist_template(name) VALUES ('Outer')")
        assert repo.import_checklist_template(self.payload()) is None
        assert conn.in_transaction
        assert [row["name"] for row in repo.get_all_checklist_templates()] == ["Outer"]
        conn.rollback()
        assert repo.get_all_checklist_templates() == []

    def test_failed_import_can_retry_without_duplicate_partial_rows(self):
        conn = repo.get_connection()
        conn.execute(
            "CREATE TRIGGER block_second BEFORE INSERT ON checklist_item "
            "WHEN NEW.item_text='Second' BEGIN SELECT RAISE(ABORT, 'blocked'); END"
        )
        conn.commit()
        assert repo.import_checklist_template(self.payload()) is None
        conn.execute("DROP TRIGGER block_second")
        template_id = repo.import_checklist_template(self.payload())
        assert template_id is not None
        assert len(repo.get_all_checklist_templates()) == 1
        assert len(repo.get_checklist_items(template_id)) == 2

    def test_autocommit_connection_also_rolls_back_the_entire_import(self):
        conn = repo.get_connection()
        conn.isolation_level = None
        conn.execute(
            "CREATE TRIGGER block_second BEFORE INSERT ON checklist_item "
            "WHEN NEW.item_text='Second' BEGIN SELECT RAISE(ABORT, 'blocked'); END"
        )
        assert repo.import_checklist_template(self.payload()) is None
        assert repo.get_all_checklist_templates() == []
        assert not conn.in_transaction

    def test_readonly_database_reports_failure(self):
        conn = repo.get_connection()
        conn.execute("PRAGMA query_only=ON")
        assert repo.import_checklist_template(self.payload()) is None
        assert not conn.in_transaction
        assert repo.get_all_checklist_templates() == []

    def test_process_and_empty_templates_remain_supported(self):
        payload = self.payload()
        payload["template"]["checklist_type"] = "process"
        payload["items"] = []
        template_id = repo.import_checklist_template(payload)
        assert repo.get_checklist_template(template_id)["checklist_type"] == "process"
        assert repo.get_checklist_items(template_id) == []
