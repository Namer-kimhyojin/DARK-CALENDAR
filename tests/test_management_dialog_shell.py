# -*- coding: utf-8 -*-
"""Tabbed management pages share only the outer modal's window chrome."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QSettings, Qt, QTimer
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QFrame, QToolButton, QWidget

from calendar_app.presentation.dialogs.dialog_chrome import ensure_dialog_chrome
from calendar_app.presentation.dialogs.dialog_styles import install_common_dialog_style_filter
from calendar_app.presentation.dialogs.management_dialogs import (
    STATUS_FILTER_ITEMS,
    MultiColumnFilterProxyModel,
    WorkManagementTabbedDialog,
)
from tests.support import TemporaryDatabaseTestCase


class ManagementDialogShellTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = QApplication.instance() or QApplication([])
        install_common_dialog_style_filter(cls.app)

    def setUp(self):
        super().setUp()
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.host = QWidget()
        self.addCleanup(self.host.close)
        self.host.settings = QSettings(
            str(Path(temp.name) / "management.ini"), QSettings.Format.IniFormat
        )
        self.host.settings.setValue("theme_color", "#c5a3f5")
        self.host.settings.setValue("panel_base_color", "#121827")
        self.host.settings.setValue("text_theme", "dark")
        schedule = {"id": 101, "name": "Schedule sample", "deadline": "2026-11-06 09:00:00"}
        routine = {"id": 102, "name": "Routine sample", "target_date": "2026-11-06"}
        source_patch = patch(
            "calendar_app.presentation.dialogs.management_dialogs.search_repo.get_tasks_by_type",
            side_effect=lambda kind: [schedule if kind == "schedule" else routine],
        )
        self.task_source = source_patch.start()
        self.addCleanup(source_patch.stop)
        directive_patch = patch(
            "calendar_app.presentation.dialogs.management_dialogs.directive_repo.get_all_directives_for_management",
            return_value=[(103, "Directive sample", "Team", "normal", "2026-11-06", "pending")],
        )
        self.directive_source = directive_patch.start()
        self.addCleanup(directive_patch.stop)

    def dialog(self, start_tab="schedule"):
        dialog = WorkManagementTabbedDialog(self.host, start_tab=start_tab)
        self.addCleanup(dialog.close)
        dialog.show()
        for _ in range(4):
            self.app.processEvents()
        return dialog

    def test_one_outer_header_precedes_tabs_and_embedded_pages_have_no_chrome(self):
        dialog = self.dialog()
        for index in range(3):
            dialog.tabs.setCurrentIndex(index)
            self.app.processEvents()
        controller = dialog._dc_dialog_chrome_controller
        self.assertIs(controller.header.parentWidget(), dialog)
        headers = dialog.findChildren(QFrame, "CommonDialogHeader")
        self.assertEqual(headers, [controller.header])
        self.assertEqual(len(dialog.findChildren(QToolButton, "CommonDialogClose")), 1)
        self.assertLess(
            controller.header.geometry().bottom(),
            dialog.tabs.tabBar().mapTo(dialog, QPoint()).y(),
        )
        self.assertEqual(controller.title_label.text(), dialog.windowTitle())
        for page in dialog._tab_instances.values():
            self.assertFalse(page.isWindow())
            self.assertFalse(hasattr(page, "_dc_dialog_chrome_controller"))
            self.assertFalse(ensure_dialog_chrome(page))

    def test_outer_close_and_escape_close_every_selected_tab(self):
        for index in range(3):
            for action in ("close", "escape", "window-close"):
                with self.subTest(tab=index, action=action):
                    dialog = self.dialog()
                    dialog.tabs.setCurrentIndex(index)
                    self.app.processEvents()
                    page = dialog._tab_instances[index]
                    if action == "close":
                        callback = dialog._dc_dialog_chrome_controller.close_button.click
                    elif action == "escape":
                        page.search_input.setFocus()

                        def callback(page=page):
                            QTest.keyClick(page.search_input, Qt.Key.Key_Escape)
                    else:
                        callback = dialog.close
                    closed_by_action = []

                    def invoke(callback=callback, dialog=dialog, closed_by_action=closed_by_action):
                        callback()
                        closed_by_action.append(not dialog.isVisible())

                    QTimer.singleShot(0, invoke)
                    # A broken close must fail instead of hanging the test runner.
                    fallback = QTimer(dialog)
                    fallback.setSingleShot(True)
                    fallback.timeout.connect(dialog.reject)
                    fallback.start(500)
                    result = dialog.exec()
                    fallback.stop()
                    self.assertEqual(result, QDialog.DialogCode.Rejected)
                    self.assertFalse(dialog.isVisible())
                    self.assertEqual(closed_by_action, [True])

    def test_tab_data_and_refresh_actions_survive_lazy_switching(self):
        dialog = self.dialog()
        original_pages = {}
        for index in range(3):
            dialog.tabs.setCurrentIndex(index)
            self.app.processEvents()
            page = dialog._tab_instances[index]
            original_pages[index] = page
            self.assertEqual(page.model.rowCount(), 1)
            cells_before = [
                page.model.index(0, column).data() for column in range(page.model.columnCount())
            ]
            self.assertTrue(page.search_input.placeholderText())
            self.assertEqual(
                page.search_input.accessibleName(), page.search_input.placeholderText()
            )
            self.assertTrue(page.add_btn.isVisible())
            self.assertTrue(page.delete_btn.isVisible())
            page.refresh_btn.click()
            self.assertEqual(page.model.rowCount(), 1)
            self.assertEqual(
                [page.model.index(0, column).data() for column in range(page.model.columnCount())],
                cells_before,
            )
        for index in (0, 2, 1, 0):
            dialog.tabs.setCurrentIndex(index)
            self.app.processEvents()
            self.assertIs(dialog._tab_instances[index], original_pages[index])
            self.assertEqual(original_pages[index].model.rowCount(), 1)

    def test_calendar_and_status_filters_work_independently_and_together(self):
        model = QStandardItemModel(0, 3)
        for values in (
            ("Calendar A", "Alpha", "Pending"),
            ("Calendar B", "Beta", "Pending"),
            ("Calendar B", "Gamma", "Completed"),
        ):
            model.appendRow([QStandardItem(value) for value in values])
        proxy = MultiColumnFilterProxyModel()
        proxy.setSourceModel(model)
        proxy.setCalendarColumn(0)
        proxy.setSearchColumns([1])
        proxy.setStatusColumn(2)
        proxy.setStatusText("Pending")
        self.assertEqual(proxy.rowCount(), 2)
        proxy.setStatusText(STATUS_FILTER_ITEMS[0])
        proxy.setCalendarText("Calendar B")
        self.assertEqual(proxy.rowCount(), 2)
        proxy.setStatusText("Pending")
        self.assertEqual(proxy.rowCount(), 1)
        self.assertEqual(proxy.index(0, 1).data(), "Beta")
        proxy.setSearchText("gamma")
        self.assertEqual(proxy.rowCount(), 0)
        proxy.setStatusText(STATUS_FILTER_ITEMS[0])
        self.assertEqual(proxy.rowCount(), 1)
        self.assertEqual(proxy.index(0, 1).data(), "Gamma")
