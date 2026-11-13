# -*- coding: utf-8 -*-
"""Delayed editor feedback must respect widget lifetime and newer messages."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from calendar_app.presentation.dialogs.task_dialog_unified import UnifiedTaskDialog
from tests.support import TemporaryDatabaseTestCase


class TaskFeedbackLifetimeTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.dialogs = []

    def tearDown(self):
        self.app.processEvents()
        for dialog in self.dialogs:
            if not sip.isdeleted(dialog):
                dialog.close()
                dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        super().tearDown()

    def dialog(self, task_type="schedule"):
        dialog = UnifiedTaskDialog(task_type=task_type)
        self.dialogs.append(dialog)
        # Complete initial zero-delay layout work before exercising destruction.
        for _ in range(3):
            self.app.processEvents()
        return dialog

    def test_deleting_editor_cancels_feedback_before_its_deadline(self):
        for task_type in ("schedule", "routine"):
            with self.subTest(task_type=task_type):
                dialog = self.dialog(task_type)
                dialog._show_status_feedback("Saved", auto_hide_ms=30)
                label = dialog.status_feedback_label
                dialog.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                self.assertTrue(sip.isdeleted(dialog))
                self.assertTrue(sip.isdeleted(label))
                # The former global singleShot raises in Qt at this point.
                QTest.qWait(70)
                self.app.processEvents()

    def test_new_feedback_restarts_its_own_visible_period(self):
        dialog = self.dialog()
        dialog._show_status_feedback("First save", auto_hide_ms=120)
        QTest.qWait(70)
        dialog._show_status_feedback("Second save", auto_hide_ms=180)
        QTest.qWait(80)
        self.assertFalse(dialog.status_feedback_label.isHidden())
        self.assertEqual(dialog.status_feedback_label.text(), "Second save")
        QTest.qWait(130)
        self.assertTrue(dialog.status_feedback_label.isHidden())

    def test_persistent_error_cancels_previous_success_deadline(self):
        dialog = self.dialog()
        dialog._show_status_feedback("Saved", auto_hide_ms=30)
        dialog._show_status_feedback("Enter a task name", is_error=True)
        QTest.qWait(70)
        self.assertFalse(dialog.status_feedback_label.isHidden())
        self.assertEqual(dialog.status_feedback_label.text(), "Enter a task name")
