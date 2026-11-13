# -*- coding: utf-8 -*-
"""Text-edit keys and short feedback respect their owning dialog's lifetime."""

import os
from unittest.mock import Mock, call

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QPushButton, QTableWidgetItem
import pytest

from calendar_app.presentation.dialogs import checklist_manager_dialog_advanced as checklist
from calendar_app.presentation.dialogs.help_center_dialog import HelpCenterDialog


@pytest.fixture
def qapp():
    application = QApplication.instance() or QApplication([])
    yield application
    application.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def checklist_ui(qapp, monkeypatch):
    monkeypatch.setattr(checklist.checklist_repo, "seed_default_templates", Mock())
    monkeypatch.setattr(checklist.ChecklistManagerDialog, "load_templates", Mock())
    monkeypatch.setattr(checklist.ChecklistManagerDialog, "_select_template_in_list", Mock())
    actions = {}
    for name in ("_delete_items", "_edit_item", "_move_item"):
        actions[name] = Mock()
        monkeypatch.setattr(checklist.ChecklistManagerDialog, name, actions[name])
    actions["save"] = Mock(return_value=True)
    monkeypatch.setattr(checklist.checklist_repo, "update_checklist_template", actions["save"])
    dialog = checklist.ChecklistManagerDialog()
    dialog.current_template_id = 123
    dialog.template_name_edit.setText("ABCDE")
    dialog.template_desc_edit.setPlainText("Description")
    dialog._set_editor_visible(True)
    dialog.items_table.setRowCount(2)
    dialog.items_table.setItem(0, 1, QTableWidgetItem("First item"))
    dialog.items_table.setItem(1, 1, QTableWidgetItem("Second item"))
    dialog.show()
    dialog.activateWindow()
    for _ in range(3):
        qapp.processEvents()
    yield dialog, actions
    if not sip.isdeleted(dialog):
        dialog.close()
        dialog.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def test_delete_in_template_name_edits_text_without_deleting_items(qapp, checklist_ui):
    dialog, actions = checklist_ui
    field = dialog.template_name_edit
    field.setFocus()
    field.setSelection(1, 2)
    qapp.processEvents()
    QTest.keyClick(field, Qt.Key.Key_Delete)
    assert field.text() == "ADE"
    actions["_delete_items"].assert_not_called()
    assert dialog.items_table.rowCount() == 2


def test_return_in_description_inserts_newline_without_editing_items(qapp, checklist_ui):
    dialog, actions = checklist_ui
    field = dialog.template_desc_edit
    field.setPlainText("Description")
    field.moveCursor(QTextCursor.MoveOperation.End)
    field.setFocus()
    qapp.processEvents()
    QTest.keyClick(field, Qt.Key.Key_Return)
    assert field.toPlainText() == "Description\n"
    actions["_edit_item"].assert_not_called()
    actions["save"].assert_not_called()


def test_control_arrows_in_description_do_not_reorder_table_items(qapp, checklist_ui):
    dialog, actions = checklist_ui
    field = dialog.template_desc_edit
    field.setPlainText("First paragraph\nSecond paragraph")
    field.setFocus()
    qapp.processEvents()
    QTest.keyClick(field, Qt.Key.Key_Up, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(field, Qt.Key.Key_Down, Qt.KeyboardModifier.ControlModifier)
    actions["_move_item"].assert_not_called()
    assert field.toPlainText() == "First paragraph\nSecond paragraph"


def test_table_keeps_delete_edit_and_reorder_shortcuts(qapp, checklist_ui):
    dialog, actions = checklist_ui
    table = dialog.items_table
    table.setCurrentCell(0, 1)
    table.setFocus()
    qapp.processEvents()
    QTest.keyClick(table, Qt.Key.Key_Delete)
    QTest.keyClick(table, Qt.Key.Key_Return)
    QTest.keyClick(table, Qt.Key.Key_Up, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(table, Qt.Key.Key_Down, Qt.KeyboardModifier.ControlModifier)
    actions["_delete_items"].assert_called_once_with()
    actions["_edit_item"].assert_called_once_with()
    assert actions["_move_item"].call_args_list == [call(-1), call(1)]
    actions["save"].assert_not_called()


def test_repeated_save_feedback_expires_to_the_original_label(checklist_ui):
    dialog, actions = checklist_ui
    original_text = dialog.save_base_btn.text()
    original_style = dialog.save_base_btn.styleSheet()
    dialog._save_template_info()
    saved_text = dialog.save_base_btn.text()
    assert saved_text != original_text
    QTest.qWait(700)
    dialog._save_template_info()
    QTest.qWait(650)
    assert dialog.save_base_btn.text() == saved_text
    QTest.qWait(700)
    assert dialog.save_base_btn.text() == original_text
    assert dialog.save_base_btn.styleSheet() == original_style
    assert actions["save"].call_count == 2


def test_deleting_checklist_dialog_cancels_pending_save_feedback(qapp, checklist_ui):
    dialog, _actions = checklist_ui
    dialog._save_template_info()
    button = dialog.save_base_btn
    dialog.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(dialog)
    assert sip.isdeleted(button)
    # A global callback against the destroyed button previously raised in Qt.
    QTest.qWait(1300)
    qapp.processEvents()


@pytest.mark.parametrize("query", ("", "잠금"))
@pytest.mark.parametrize("key", (Qt.Key.Key_Return, Qt.Key.Key_Enter))
def test_help_search_enter_searches_and_does_not_close(qapp, query, key):
    dialog = HelpCenterDialog()
    dialog.show()
    dialog.activateWindow()
    dialog.search_input.setText(query)
    dialog.search_input.setFocus()
    qapp.processEvents()
    try:
        QTest.keyClick(dialog.search_input, key)
        assert dialog.isVisible()
        expected = "search" if query else dialog._selected_page_id
        assert dialog.page_stack.currentIndex() == dialog._page_indexes[expected]
        close = dialog.findChild(QPushButton, "primary_btn")
        assert not close.isDefault()
        assert not close.autoDefault()
        QTest.mouseClick(close, Qt.MouseButton.LeftButton)
        assert not dialog.isVisible()
    finally:
        dialog.close()
        dialog.deleteLater()
