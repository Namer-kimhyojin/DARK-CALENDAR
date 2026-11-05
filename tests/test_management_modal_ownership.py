# -*- coding: utf-8 -*-
"""Real management row activation keeps the editor above the invoking modal."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QSettings, Qt, QTimer
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QMainWindow

from calendar_app.infrastructure.db import calendar_repo, task_repo
from calendar_app.presentation.dialogs.dialog_router import DialogActionsMixin
from calendar_app.presentation.dialogs.dialog_styles import install_common_dialog_style_filter
from calendar_app.presentation.dialogs.management_dialogs import WorkManagementTabbedDialog
from calendar_app.presentation.dialogs.modify_task_dialog_unified import UnifiedModifyTaskDialog
from calendar_app.presentation.dialogs.task_dialog_unified import UnifiedTaskDialog
from tests.support import TemporaryDatabaseTestCase


class _Host(QMainWindow, DialogActionsMixin):
    def __init__(self, settings):
        QMainWindow.__init__(self)
        self.settings = settings
        self.active_editing_task_ids = set()
        self.refresh_count = 0
        self.setObjectName("MainCalendarFixture")
        self.setCentralWidget(QLabel("캘린더"))

    def _refresh_all_panels(self):
        self.refresh_count += 1

    def handle_task_added(self, task):
        pass


class ManagementModalOwnershipTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = QApplication.instance() or QApplication([])
        install_common_dialog_style_filter(cls.app)

    def test_table_double_click_keeps_app_context_and_uses_invoking_modal_as_transient_owner(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        settings = QSettings(str(Path(temporary.name) / "owner.ini"), QSettings.Format.IniFormat)
        settings.setValue("gcal_enabled", "false")
        settings.setValue("font_size", 11)
        host = _Host(settings)
        self.addCleanup(lambda: None if sip.isdeleted(host) else host.close())
        host.resize(1000, 700)
        host.show()
        calendar_id = "local::modal-owner-test"
        calendar_repo.upsert_calendar(calendar_id, "local", "소유 창 검증")
        task_id = task_repo.create_unified_task(
            {
                "name": "관리 표 더블클릭 검증",
                "type": "schedule",
                "priority": "normal",
                "status": "pending",
                "deadline": "2026-11-06 09:00:00",
                "end_date": "2026-11-06 10:00:00",
                "calendar_id": calendar_id,
            }
        )
        manager = WorkManagementTabbedDialog(host)
        self.addCleanup(lambda: None if sip.isdeleted(manager) else manager.close())
        page = manager._tab_instances[0]
        observations = {}
        heartbeat = []
        tick = QTimer(host)
        tick.setInterval(5)
        tick.timeout.connect(lambda: heartbeat.append(True))
        tick.start()

        class ObservedEditor(UnifiedModifyTaskDialog):
            def exec(editor):
                observations.update(
                    active_before_is_manager=QApplication.activeModalWidget() is manager,
                    manager_is_app_descendant=host.isAncestorOf(manager),
                    before_exec_transient_is_manager=(
                        editor.windowHandle() is not None
                        and editor.windowHandle().transientParent() is manager.windowHandle()
                    ),
                )

                def inspect():
                    handle = editor.windowHandle()
                    transient = handle.transientParent() if handle is not None else None
                    observations.update(
                        active_modal_is_editor=QApplication.activeModalWidget() is editor,
                        transient_is_manager=transient is manager.windowHandle(),
                        transient_is_main=transient is host.windowHandle(),
                        app_context_preserved=editor.parentWidget() is host,
                        edit_lock_held=task_id in host.active_editing_task_ids,
                        calendar_id=editor.calendar_combo.currentData(),
                        heartbeat_count=len(heartbeat),
                        editor_visible=editor.isVisible(),
                        manager_visible=manager.isVisible(),
                    )
                    editor.reject()

                QTimer.singleShot(40, inspect)
                return super().exec()

        def activate():
            index = page.proxy.index(0, 2)
            page.table.setCurrentIndex(index)
            rect = page.table.visualRect(index)
            QTest.mouseClick(page.table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
            QTest.mouseDClick(page.table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
            manager.reject()

        fallback = QTimer(manager)
        fallback.setSingleShot(True)
        fallback.timeout.connect(manager.reject)
        spy = QSignalSpy(page.table.doubleClicked)
        with patch(
            "calendar_app.presentation.dialogs.modify_task_dialog_unified.UnifiedModifyTaskDialog",
            ObservedEditor,
        ):
            QTimer.singleShot(20, activate)
            fallback.start(2000)
            manager.exec()
        fallback.stop()
        tick.stop()
        self.assertEqual(len(spy), 1)
        self.assertTrue(observations, "The editor was never opened from the table")
        output = Path("artifacts/modal-palette-20261105")
        output.mkdir(parents=True, exist_ok=True)
        suffix = "fixed" if observations["transient_is_manager"] else "before"
        (output / f"management-modal-ownership-{suffix}.json").write_text(
            json.dumps(observations, ensure_ascii=False, indent=2),
            encoding="utf-8",
            errors="strict",
        )
        self.assertTrue(observations["active_modal_is_editor"])
        self.assertTrue(observations["editor_visible"] and observations["manager_visible"])
        self.assertGreater(observations["heartbeat_count"], 0)
        self.assertTrue(observations["app_context_preserved"])
        self.assertTrue(observations["edit_lock_held"])
        self.assertEqual(observations["calendar_id"], calendar_id)
        self.assertEqual(task_repo.get_unified_task(task_id)["calendar_id"], calendar_id)
        self.assertFalse(host.active_editing_task_ids)
        self.assertTrue(observations["transient_is_manager"], observations)
        manager.deleteLater()
        host.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_management_add_uses_the_same_modal_owner_without_changing_app_parent(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        settings = QSettings(str(Path(temporary.name) / "create.ini"), QSettings.Format.IniFormat)
        host = _Host(settings)
        self.addCleanup(lambda: None if sip.isdeleted(host) else host.close())
        host.show()
        manager = WorkManagementTabbedDialog(host)
        self.addCleanup(lambda: None if sip.isdeleted(manager) else manager.close())
        observations = {}

        class ObservedCreate(UnifiedTaskDialog):
            def exec(editor):
                def inspect():
                    observations.update(
                        active=QApplication.activeModalWidget() is editor,
                        app_parent=editor.parentWidget() is host,
                        owner=editor.windowHandle().transientParent() is manager.windowHandle(),
                        create=not editor._is_modify,
                    )
                    editor.reject()

                QTimer.singleShot(30, inspect)
                return super().exec()

        def activate():
            manager._tab_instances[0].add_btn.click()
            manager.reject()

        with patch(
            "calendar_app.presentation.dialogs.task_dialog_unified.UnifiedTaskDialog",
            ObservedCreate,
        ):
            QTimer.singleShot(20, activate)
            manager.exec()
        self.assertEqual(
            observations, {"active": True, "app_parent": True, "owner": True, "create": True}
        )
        self.assertFalse(host.active_editing_task_ids)
        manager.deleteLater()
        host.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
