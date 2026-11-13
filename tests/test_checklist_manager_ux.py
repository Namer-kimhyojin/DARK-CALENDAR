# -*- coding: utf-8 -*-
"""Checklist filtering and editing preserve the selected template's draft."""

import os
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication, QEvent, QModelIndex, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QPushButton
import pytest

from calendar_app.presentation.dialogs import checklist_manager_dialog_advanced as checklist


@pytest.fixture
def manager(monkeypatch):
    app = QApplication.instance() or QApplication([])
    templates = {
        1: {
            "id": 1,
            "name": "Alpha onboarding",
            "description": "New hire setup",
            "category": "people",
            "checklist_type": "list",
        },
        2: {
            "id": 2,
            "name": "Beta review",
            "description": "Month-end review",
            "category": "finance",
            "checklist_type": "list",
        },
    }
    items = {1: [], 2: []}
    writes = []

    def update_template(template_id, updates):
        writes.append(template_id)
        templates[template_id].update(updates)
        return True

    question = Mock(return_value=QMessageBox.StandardButton.Cancel)
    monkeypatch.setattr(checklist.QMessageBox, "question", question)
    monkeypatch.setattr(checklist.checklist_repo, "seed_default_templates", Mock())
    monkeypatch.setattr(
        checklist.checklist_repo,
        "get_all_checklist_templates",
        lambda **_: [dict(template) for template in templates.values()],
    )
    monkeypatch.setattr(
        checklist.checklist_repo,
        "get_checklist_template",
        lambda template_id: dict(templates[template_id]),
    )
    monkeypatch.setattr(
        checklist.checklist_repo,
        "get_checklist_items",
        lambda template_id: [dict(item) for item in items[template_id]],
    )
    monkeypatch.setattr(checklist.checklist_repo, "update_checklist_template", update_template)
    dialog = checklist.ChecklistManagerDialog()
    dialog.show()
    app.processEvents()
    yield SimpleNamespace(
        dialog=dialog, templates=templates, items=items, writes=writes, question=question
    )
    dialog.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def _choose_template(dialog, template_id):
    template_list = dialog.template_list
    item = next(
        template_list.item(row)
        for row in range(template_list.count())
        if template_list.item(row).data(Qt.ItemDataRole.UserRole) == template_id
    )
    template_list.setCurrentItem(item)


def _visible_template_ids(dialog):
    template_list = dialog.template_list
    return [
        template_list.item(row).data(Qt.ItemDataRole.UserRole)
        for row in range(template_list.count())
        if not template_list.item(row).isHidden()
    ]


def _edit_draft(dialog):
    dialog.template_name_edit.setText("Alpha setup plan")
    dialog.template_desc_edit.setPlainText("First day\nFirst week")
    dialog.type_process_radio.setChecked(True)


def test_filter_finds_template_and_keeps_selection_after_clearing(manager):
    dialog = manager.dialog
    assert _visible_template_ids(dialog) == [1, 2]
    assert dialog.template_list.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff

    dialog.template_search.setText("REVIEW")
    assert _visible_template_ids(dialog) == [2]
    _choose_template(dialog, 2)
    assert dialog.template_name_edit.text() == "Beta review"

    dialog.template_search.clear()
    assert _visible_template_ids(dialog) == [1, 2]
    assert dialog.current_template_id == 2
    assert manager.writes == []


def test_reloading_items_and_canceling_selection_preserve_the_draft(manager):
    dialog = manager.dialog
    _edit_draft(dialog)
    manager.items[1].append(
        {
            "id": 11,
            "item_text": "Set up computer",
            "item_description": "Prepare access",
            "item_guide": "",
            "is_required": True,
        }
    )
    dialog._load_items(1)
    dialog.load_templates()
    _choose_template(dialog, 2)

    manager.question.assert_called_once()
    assert dialog.current_template_id == 1
    assert dialog.template_list.currentItem().data(Qt.ItemDataRole.UserRole) == 1
    assert dialog.template_name_edit.text() == "Alpha setup plan"
    assert dialog.template_desc_edit.toPlainText() == "First day\nFirst week"
    assert dialog.type_process_radio.isChecked()
    assert dialog.items_table.item(0, 1).data(Qt.ItemDataRole.UserRole) == 11
    assert manager.writes == []


def test_save_before_switch_updates_only_the_previously_selected_template(manager):
    dialog = manager.dialog
    original_other_template = dict(manager.templates[2])
    manager.question.return_value = QMessageBox.StandardButton.Save
    _edit_draft(dialog)
    _choose_template(dialog, 2)

    manager.question.assert_called_once()
    assert manager.writes == [1]
    assert manager.templates[1] == {
        "id": 1,
        "name": "Alpha setup plan",
        "description": "First day\nFirst week",
        "category": "people",
        "checklist_type": "process",
    }
    assert manager.templates[2] == original_other_template
    assert dialog.current_template_id == 2
    assert dialog.template_name_edit.text() == "Beta review"


def test_close_button_respects_cancel_and_discards_only_on_request(manager):
    dialog = manager.dialog
    close = next(
        button
        for button in dialog.findChildren(QPushButton)
        if button.property("dialogFooter") and button.objectName() == "ghost_btn"
    )
    _edit_draft(dialog)
    close.click()
    assert dialog.isVisible()
    assert dialog.template_name_edit.text() == "Alpha setup plan"

    manager.question.return_value = QMessageBox.StandardButton.Discard
    close.click()
    assert not dialog.isVisible()
    assert manager.templates[1]["name"] == "Alpha onboarding"
    assert manager.writes == []


def test_moving_a_whole_row_preserves_its_identity_and_persists_order(manager, monkeypatch):
    dialog = manager.dialog
    manager.items[1].extend(
        {
            "id": item_id,
            "item_text": title,
            "item_description": "",
            "item_guide": "",
            "is_required": False,
        }
        for item_id, title in [(11, "Prepare access"), (12, "Send welcome message")]
    )
    changes = []

    def reorder(template_id, item_ids):
        changes.append((template_id, item_ids))
        by_id = {item["id"]: item for item in manager.items[template_id]}
        manager.items[template_id] = [by_id[item_id] for item_id in item_ids]
        return True

    monkeypatch.setattr(checklist.checklist_repo, "reorder_checklist_items", reorder)
    dialog._load_items(1)
    table = dialog.items_table
    table.selectRow(0)
    assert not table.dragDropOverwriteMode()
    assert not table.item(0, 1).flags() & Qt.ItemFlag.ItemIsDropEnabled
    assert dialog.move_down_btn.isEnabled()
    assert not dialog.move_up_btn.isEnabled()

    model = table.model()
    root = QModelIndex()
    assert model.moveRows(root, 0, 1, root, 2)
    QApplication.processEvents()

    assert changes == [(1, [12, 11])]
    assert table.currentRow() == 1
    assert table.item(1, 1).data(Qt.ItemDataRole.UserRole) == 11
    assert table.item(1, 0).text() == "2"
    assert dialog.move_up_btn.isEnabled()
    assert not dialog.move_down_btn.isEnabled()
