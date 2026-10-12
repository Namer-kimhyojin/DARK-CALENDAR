# -*- coding: utf-8 -*-
"""Selection shortcuts clear both item types and protect text editing."""

from unittest.mock import patch

from PyQt6.QtCore import QEvent, QSettings, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)
import pytest

from calendar_app.infrastructure.runtime.keyboard_shortcuts import register_all
from calendar_app.presentation.main_window import action_handlers_tasks as actions
from calendar_app.presentation.main_window.window_shell_actions import WindowShellActionsMixin


class _Host(WindowShellActionsMixin, actions.TaskActionsMixin, QMainWindow):
    def __init__(self, path):
        super().__init__()
        self.settings = QSettings(str(path), QSettings.Format.IniFormat)
        self.selected_task_ids = set()
        self.selected_directive_ids = set()
        self._global_shortcuts = []
        self.selection_counts = []
        body = QWidget(self)
        layout = QVBoxLayout(body)
        task, directive = QFrame(body), QFrame(body)
        self.editor = QLineEdit(body)
        for widget in (task, directive, self.editor):
            layout.addWidget(widget)
        self._panel_task_frames = {7: (task, None)}
        self._panel_directive_frames = {9: (directive, None)}
        self.setCentralWidget(body)
        register_all(self)

    def update_task_selection_status(self):
        self.selection_counts.append(
            (len(self.selected_task_ids), len(self.selected_directive_ids))
        )


@pytest.fixture
def host(tmp_path):
    application = QApplication.instance() or QApplication([])
    window = _Host(tmp_path / "selection.ini")
    window.show()
    window.activateWindow()
    window.setFocus()
    application.processEvents()
    yield window
    for shortcut in window._global_shortcuts:
        shortcut.setEnabled(False)
    window.close()
    window.deleteLater()
    application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()


@pytest.mark.parametrize("tasks,directives", [({7}, set()), (set(), {9}), ({7}, {9})])
def test_escape_clears_all_panel_selections_before_a_following_delete(host, tasks, directives):
    host.selected_task_ids.update(tasks)
    host.selected_directive_ids.update(directives)
    host._update_selection_visuals()
    QTest.keyClick(host, Qt.Key.Key_Escape)
    assert not host.selected_task_ids
    assert not host.selected_directive_ids
    assert host.selection_counts[-1] == (0, 0)
    counts = list(host.selection_counts)
    QTest.keyClick(host, Qt.Key.Key_Escape)
    assert host.selection_counts == counts
    with (
        patch.object(actions.QMessageBox, "question") as prompt,
        patch.object(actions.db_directive, "delete_directives") as delete,
    ):
        QTest.keyClick(host, Qt.Key.Key_Delete)
    prompt.assert_not_called()
    delete.assert_not_called()


def test_cancelled_mixed_selection_delete_keeps_both_sets_and_does_not_write(host):
    host.selected_task_ids.add(7)
    host.selected_directive_ids.add(9)
    with (
        patch.object(actions.QMessageBox, "question", return_value=QMessageBox.StandardButton.No),
        patch.object(actions.db_directive, "delete_directives") as delete,
    ):
        QTest.keyClick(host, Qt.Key.Key_Delete)
    assert host.selected_task_ids == {7}
    assert host.selected_directive_ids == {9}
    delete.assert_not_called()


def test_delete_inside_text_input_edits_text_without_deleting_selected_items(host):
    host.selected_task_ids.add(7)
    host.selected_directive_ids.add(9)
    host.editor.setText("abc")
    host.editor.setCursorPosition(0)
    host.editor.setFocus()
    QApplication.processEvents()
    with patch.object(actions.QMessageBox, "question") as prompt:
        QTest.keyClick(host.editor, Qt.Key.Key_Delete)
    assert host.editor.text() == "bc"
    assert host.selected_task_ids == {7}
    assert host.selected_directive_ids == {9}
    prompt.assert_not_called()
