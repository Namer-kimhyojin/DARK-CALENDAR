# -*- coding: utf-8 -*-
"""Untrusted checklist files must stay within budgets before parsing or writing."""

import json
from types import SimpleNamespace
from unittest.mock import Mock, mock_open, patch

import pytest

from calendar_app.infrastructure.db import checklist_template_repo as repo
from calendar_app.presentation.dialogs import checklist_manager_dialog_advanced as ui
from tests.support import TemporaryDatabaseTestCase


def payload():
    return {"template": {"name": "Imported"}, "items": [{"item_text": "First"}]}


def import_file(filename):
    owner = SimpleNamespace(
        current_template_id=99,
        load_templates=Mock(),
        _select_template_in_list=Mock(),
        checklist_changed=SimpleNamespace(emit=Mock()),
    )
    with (
        patch.object(ui.QFileDialog, "getOpenFileName", return_value=(str(filename), "")),
        patch.object(ui.QMessageBox, "information") as success,
        patch.object(ui.QMessageBox, "critical") as error,
    ):
        ui.ChecklistManagerDialog._import_template(owner)
    return owner, success, error


def assert_rejected(owner, success, error):
    assert owner.current_template_id == 99
    owner.load_templates.assert_not_called()
    owner._select_template_in_list.assert_not_called()
    owner.checklist_changed.emit.assert_not_called()
    success.assert_not_called()
    error.assert_called_once()


def test_oversized_file_is_rejected_before_reading_parsing_or_writing(tmp_path):
    filename = tmp_path / "large.json"
    filename.write_bytes(b" " * (repo.MAX_CHECKLIST_IMPORT_BYTES + 1))
    opened = mock_open()
    with (
        filename.open("rb") as stream,
        patch("builtins.open", opened),
        patch.object(ui.json, "loads") as parse,
        patch.object(repo, "get_connection") as connect,
    ):
        opened.return_value.fileno.return_value = stream.fileno()
        assert_rejected(*import_file(filename))
    opened.return_value.read.assert_not_called()
    parse.assert_not_called()
    connect.assert_not_called()


def test_file_growth_after_stat_is_bounded_before_parsing():
    opened = mock_open(read_data=b" " * (repo.MAX_CHECKLIST_IMPORT_BYTES + 1))
    with (
        patch("builtins.open", opened),
        patch.object(ui.os, "fstat", return_value=SimpleNamespace(st_size=0)),
        patch.object(ui.json, "loads") as parse,
        patch.object(repo, "get_connection") as connect,
    ):
        assert_rejected(*import_file("growing.json"))
    opened().read.assert_called_once_with(repo.MAX_CHECKLIST_IMPORT_BYTES + 1)
    parse.assert_not_called()
    connect.assert_not_called()


def test_multibyte_file_limit_counts_bytes(tmp_path):
    filename = tmp_path / "unicode.json"
    text = json.dumps(
        {"template": {"name": "한" * (repo.MAX_CHECKLIST_IMPORT_BYTES // 3)}, "items": []},
        ensure_ascii=False,
    )
    assert len(text) < repo.MAX_CHECKLIST_IMPORT_BYTES
    filename.write_bytes(text.encode("utf-8", errors="strict"))
    with patch.object(ui.json, "loads") as parse:
        assert_rejected(*import_file(filename))
    parse.assert_not_called()


def test_file_exactly_at_byte_limit_can_be_imported(tmp_path):
    filename = tmp_path / "boundary.json"
    raw = json.dumps(payload()).encode("utf-8", errors="strict")
    filename.write_bytes(raw + b" " * (repo.MAX_CHECKLIST_IMPORT_BYTES - len(raw)))
    with patch.object(repo, "import_checklist_template", return_value=42) as write:
        owner, success, error = import_file(filename)
    write.assert_called_once_with(payload())
    assert owner.current_template_id == 42
    success.assert_called_once()
    error.assert_not_called()


@pytest.mark.parametrize("raw", [b"[" * 2000, b"{", b"[]", b"null"])
def test_malformed_or_deep_json_leaves_ui_and_database_unchanged(tmp_path, raw):
    filename = tmp_path / "invalid.json"
    filename.write_bytes(raw)
    with patch.object(repo, "get_connection") as connect:
        assert_rejected(*import_file(filename))
    connect.assert_not_called()


def test_cancel_does_not_open_a_file():
    with patch("builtins.open") as opened:
        owner, success, error = import_file("")
    opened.assert_not_called()
    assert owner.current_template_id == 99
    success.assert_not_called()
    error.assert_not_called()


TEXT_FIELDS = [
    ("template", "name", repo.MAX_CHECKLIST_NAME_LENGTH),
    ("template", "description", repo.MAX_CHECKLIST_DETAIL_LENGTH),
    ("template", "category", repo.MAX_CHECKLIST_NAME_LENGTH),
    ("item", "item_text", repo.MAX_CHECKLIST_ITEM_TEXT_LENGTH),
    ("item", "item_description", repo.MAX_CHECKLIST_DETAIL_LENGTH),
    ("item", "item_guide", repo.MAX_CHECKLIST_DETAIL_LENGTH),
    ("root", "exported_at", repo.MAX_CHECKLIST_METADATA_LENGTH),
    ("root", "version", repo.MAX_CHECKLIST_METADATA_LENGTH),
]


def field_owner(data, section):
    if section == "template":
        return data["template"]
    if section == "item":
        return data["items"][0]
    return data


@pytest.mark.parametrize(("section", "key", "limit"), TEXT_FIELDS)
def test_oversized_text_is_rejected_before_opening_database(section, key, limit):
    data = payload()
    field_owner(data, section)[key] = "한" * (limit + 1)
    with patch.object(repo, "get_connection") as connect, pytest.raises(ValueError):
        repo.import_checklist_template(data)
    connect.assert_not_called()


@pytest.mark.parametrize(("section", "key", "limit"), TEXT_FIELDS)
def test_strings_at_the_limit_pass_prevalidation(section, key, limit):
    data = payload()
    field_owner(data, section)[key] = "한" * limit
    with patch.object(repo, "get_connection", return_value=None) as connect:
        assert repo.import_checklist_template(data) is None
    connect.assert_called_once()


@pytest.mark.parametrize("section", ["root", "template", "item"])
def test_unknown_fields_are_rejected_before_opening_database(section):
    data = payload()
    field_owner(data, section)["unknown"] = {"nested": "ignored data"}
    with patch.object(repo, "get_connection") as connect, pytest.raises(ValueError):
        repo.import_checklist_template(data)
    connect.assert_not_called()


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("root", "template", []),
        ("root", "items", {}),
        ("root", "items", [None]),
        ("root", "version", 1.0),
        ("root", "exported_at", []),
        ("template", "name", None),
        ("template", "name", "  "),
        ("template", "description", {}),
        ("template", "category", []),
        ("template", "checklist_type", ["list"]),
        ("template", "checklist_type", "unsupported"),
        ("item", "item_text", 1),
        ("item", "item_description", []),
        ("item", "item_guide", {}),
        ("item", "is_required", 1.0),
        ("item", "is_required", 2),
    ],
)
def test_invalid_json_field_types_are_rejected_before_database_access(section, key, value):
    data = payload()
    field_owner(data, section)[key] = value
    with patch.object(repo, "get_connection") as connect, pytest.raises(ValueError):
        repo.import_checklist_template(data)
    connect.assert_not_called()


def test_excess_items_are_rejected_before_database_access():
    data = payload()
    data["items"] *= repo.MAX_CHECKLIST_IMPORT_ITEMS + 1
    with patch.object(repo, "get_connection") as connect, pytest.raises(ValueError):
        repo.import_checklist_template(data)
    connect.assert_not_called()


class TestChecklistImportCompatibility(TemporaryDatabaseTestCase):
    def test_maximum_item_count_imports_all_items_in_order(self):
        data = payload()
        data["items"] = [
            {"item_text": f"Item {index}"} for index in range(repo.MAX_CHECKLIST_IMPORT_ITEMS)
        ]
        template_id = repo.import_checklist_template(data)
        items = repo.get_checklist_items(template_id)
        assert len(items) == repo.MAX_CHECKLIST_IMPORT_ITEMS
        assert [item["item_order"] for item in items] == list(range(len(items)))
        assert items[-1]["item_text"] == f"Item {len(items) - 1}"

    def test_current_export_roundtrips_nullable_text_and_metadata(self):
        template_id = repo.create_checklist_template("한글 템플릿", checklist_type="process")
        repo.create_checklist_item(template_id, "항목", is_required=True)
        owner = SimpleNamespace(current_template_id=template_id)
        filename = self._tmpdir.name + "/export.json"
        with (
            patch.object(ui.QFileDialog, "getSaveFileName", return_value=(filename, "")),
            patch.object(ui.QMessageBox, "information"),
            patch.object(ui.QMessageBox, "critical") as error,
        ):
            ui.ChecklistManagerDialog._export_template(owner)
        error.assert_not_called()
        imported, success, error = import_file(filename)
        success.assert_called_once()
        error.assert_not_called()
        template = repo.get_checklist_template(imported.current_template_id)
        items = repo.get_checklist_items(imported.current_template_id)
        assert template["name"] == "한글 템플릿"
        assert template["description"] is None
        assert template["checklist_type"] == "process"
        assert items[0]["item_text"] == "항목"
        assert items[0]["item_description"] is None
        assert items[0]["item_guide"] is None
        assert items[0]["is_required"] == 1
