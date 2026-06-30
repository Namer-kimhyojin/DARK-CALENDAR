import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QPushButton

from calendar_app.infrastructure.db import db_repository_unified as unified_repo
from calendar_app.presentation.dialogs.task_dialog_unified import UnifiedTaskDialog
from tests.support import TemporaryDatabaseTestCase


class TaskDialogStyleTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def test_editor_token_skin_is_applied_to_unified_task_dialog(self):
        dialog = UnifiedTaskDialog(task_type="schedule")
        self.addCleanup(dialog.close)

        self.assertEqual(dialog.objectName(), "TaskEditorDialog")
        self.assertEqual(dialog.tabs.objectName(), "TaskEditorTabs")
        self.assertEqual(dialog.name_edit.objectName(), "TaskTitleEdit")
        self.assertEqual(dialog.calendar_combo.objectName(), "TaskCalendarCombo")

        stylesheet = dialog.styleSheet()
        self.assertIn("QDialog#TaskEditorDialog QTabWidget#TaskEditorTabs::pane", stylesheet)
        self.assertIn("QPushButton#primary_btn", stylesheet)
        self.assertIn('QPushButton#ghost_btn[accentVariant="true"]', stylesheet)
        self.assertIn("QLineEdit#TaskTitleEdit", stylesheet)
        self.assertIn("QDialog#TaskEditorDialog QStackedWidget", stylesheet)
        self.assertNotIn("background: #eef1f4;", stylesheet)

        create_buttons = [
            btn for btn in dialog.findChildren(QPushButton) if btn.objectName() == "primary_btn"
        ]
        self.assertGreaterEqual(len(create_buttons), 1)

    def test_modify_dialog_uses_same_editor_token_skin(self):
        task_id = unified_repo.create_unified_task(
            {
                "name": "Modify palette target",
                "type": "schedule",
                "priority": "normal",
                "status": "in_progress",
                "deadline": "2026-03-26 12:00:00",
                "end_date": "2026-03-26 13:00:00",
                "target_date": "2026-03-26",
            }
        )
        self.assertIsNotNone(task_id)

        dialog = UnifiedTaskDialog(task_type="schedule", task_id=task_id)
        self.addCleanup(dialog.close)

        stylesheet = dialog.styleSheet()
        self.assertIn("QDialog#TaskEditorDialog QTabWidget#TaskEditorTabs::pane", stylesheet)
        self.assertIn("QPushButton#primary_btn", stylesheet)
        self.assertNotIn("background: #eef1f4;", stylesheet)
        self.assertIn("QDialog#TaskEditorDialog QStackedWidget", stylesheet)


if __name__ == "__main__":
    unittest.main()
