# -*- coding: utf-8 -*-
"""Main-screen preferences persist without changing existing event ownership."""

import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QSettings, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QComboBox, QPushButton, QVBoxLayout, QWidget

from calendar_app.infrastructure.db import calendar_repo, db_repository_unified, task_repo
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.calendar import calendar_controls as controls
from calendar_app.presentation.calendar import month_renderer
from calendar_app.presentation.dialogs.task_dialog_unified import UnifiedTaskDialog
from tests import test_week_planner_integration as render_fixture
from tests.support import TemporaryDatabaseTestCase


class CalendarQuickControlsTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        cls.qapp = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.settings = QSettings(
            str(Path(self._tmpdir.name) / "quick.ini"), QSettings.Format.IniFormat
        )
        self.settings.setValue("gcal_calendar_id", "old@example.test")
        self.host = render_fixture.CalendarRenderHost(self.settings)
        self.host.refresh_gcal_sync_state = Mock()
        for identity, kind, active, visible, role in (
            ("local::personal", "local", True, True, None),
            ("gcal::team@example.test", "gcal", True, False, "owner"),
            ("gcal::holidays", "gcal", True, True, "reader"),
            ("gcal::paused", "gcal", False, True, "writer"),
            ("ics::feed", "ics", True, True, None),
            ("outlook::work", "outlook", True, True, "writer"),
            ("caldav::naver", "caldav", True, True, "reader"),
        ):
            calendar_repo.upsert_calendar(
                identity,
                kind,
                identity,
                color="#5294f7",
                is_active=active,
                is_visible=visible,
                access_role=role,
                is_default=kind == "local",
                gcal_calendar_id=identity.split("::", 1)[1] if kind == "gcal" else None,
            )
        self.widget = controls.CalendarQuickControls(self.host)

    def tearDown(self):
        self.widget.close()
        self.widget.deleteLater()
        self.host.close()
        self.host.deleteLater()
        self.qapp.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        month_renderer.invalidate_calendar_meta_cache()
        super().tearDown()

    def test_selector_includes_hidden_writable_calendars_and_excludes_readonly_or_paused(self):
        combo = self.widget.default_combo
        identities = {combo.itemData(i) for i in range(combo.count())}
        self.assertEqual(
            identities, {"local::personal", "gcal::team@example.test", "outlook::work"}
        )
        hidden_index = combo.findData("gcal::team@example.test")
        self.assertIn("숨김", combo.itemText(hidden_index))
        self.assertEqual(combo.currentData(), "local::personal")

    def test_main_choice_updates_new_task_selector_and_legacy_google_target_only(self):
        identity = task_repo.create_unified_task(
            {
                "name": "Existing owned event",
                "type": "schedule",
                "priority": "normal",
                "status": "pending",
                "deadline": "2026-10-07",
                "end_date": "2026-10-07",
                "calendar_id": "local::personal",
                "gcal_source_calendar_id": "old@example.test",
                "gcal_event_id": "existing",
                "gcal_sync_mode": "local_owned",
            }
        )
        before = task_repo.get_unified_task(identity)
        combo = self.widget.default_combo
        combo.setCurrentIndex(combo.findData("gcal::team@example.test"))
        self.assertEqual(calendar_repo.get_default_calendar()["id"], "gcal::team@example.test")
        self.assertEqual(self.settings.value("gcal_calendar_id"), "team@example.test")
        self.host.refresh_gcal_sync_state.assert_called_once_with(authenticate_silently=False)
        self.assertEqual(task_repo.get_unified_task(identity), before)
        holder = QWidget()
        selector = SimpleNamespace(
            _ui_tokens=lambda: {}, _accent_rgba=lambda *_: "rgba(82,148,247,0.22)"
        )
        UnifiedTaskDialog._build_calendar_selector(selector, QVBoxLayout(holder))
        self.assertEqual(
            UnifiedTaskDialog._get_selected_calendar_id(selector), "gcal::team@example.test"
        )
        holder.deleteLater()
        combo.setCurrentIndex(combo.findData("local::personal"))
        self.assertEqual(calendar_repo.get_default_calendar()["id"], "local::personal")
        self.assertEqual(self.settings.value("gcal_calendar_id"), "team@example.test")
        self.assertEqual(task_repo.get_unified_task(identity), before)

    def test_failed_default_save_restores_choice_and_explains_failure(self):
        with patch.object(controls, "set_default_calendar", return_value=False):
            self.widget.default_combo.setCurrentIndex(
                self.widget.default_combo.findData("gcal::team@example.test")
            )
        self.assertEqual(self.widget.default_combo.currentData(), "local::personal")
        self.assertEqual(calendar_repo.get_default_calendar()["id"], "local::personal")
        self.assertTrue(self.widget.feedback.text())
        self.assertFalse(self.host.refreshes)

    def test_database_exception_is_contained_and_default_is_preserved(self):
        with patch.object(
            controls, "set_default_calendar", side_effect=sqlite3.OperationalError("locked")
        ):
            self.widget.default_combo.setCurrentIndex(
                self.widget.default_combo.findData("gcal::team@example.test")
            )
        self.assertEqual(self.widget.default_combo.currentData(), "local::personal")
        self.assertTrue(self.widget.feedback.text())

    def test_display_form_stays_open_through_toolbar_rebuilds_and_saves_multiple_toggles(self):
        self.host.view_mode_state = "monthly"
        with patch.object(month_renderer, "_get_subscription_events", return_value=[]):
            month_renderer.render_calendar(self.host)
            self.host.show()
            dialog = controls.CalendarVisibilityDialog(self.host)
            dialog.show()
            self.qapp.processEvents()
            self.host.schedule_panel_refresh = lambda **_: month_renderer.render_calendar(self.host)
            try:
                for identity in ("local::personal", "gcal::holidays"):
                    checkbox = dialog.checkboxes[identity]
                    QTest.mouseClick(
                        checkbox, Qt.MouseButton.LeftButton, pos=QPoint(10, checkbox.height() // 2)
                    )
                    self.qapp.processEvents()
                    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                    self.assertFalse(sip.isdeleted(dialog))
                    self.assertTrue(dialog.isVisible())
                    self.assertFalse(calendar_repo.get_calendar(identity)["is_visible"])
                self.assertEqual(calendar_repo.get_default_calendar()["id"], "local::personal")
                self.assertTrue(calendar_repo.get_calendar("gcal::holidays")["is_active"])
                close = next(
                    button for button in dialog.findChildren(QPushButton) if button.isDefault()
                )
                close.click()
                self.assertFalse(dialog.isVisible())
            finally:
                dialog.close()
                dialog.deleteLater()

    def test_failed_display_save_rolls_back_checkbox_and_does_not_refresh_views(self):
        dialog = controls.CalendarVisibilityDialog(self.host)
        try:
            checkbox = dialog.checkboxes["local::personal"]
            with patch.object(calendar_repo, "set_calendar_visible", return_value=False):
                checkbox.click()
            self.assertTrue(checkbox.isChecked())
            self.assertTrue(calendar_repo.get_calendar("local::personal")["is_visible"])
            self.assertFalse(self.host.refreshes)
            self.assertTrue(dialog.feedback.text())
        finally:
            dialog.deleteLater()

    def test_main_toolbar_uses_options_without_duplicate_preferences(self):
        for mode, layout in (("monthly", "date"), ("weekly_1", "time"), ("weekly_1", "date")):
            with self.subTest(mode=mode, layout=layout):
                self.host.view_mode_state = mode
                self.host.cal_week_layout = layout
                with patch.object(month_renderer, "_get_subscription_events", return_value=[]):
                    month_renderer.render_calendar(self.host)
                toolbar = self.host.calendar_toolbar_widget
                self.assertFalse(toolbar.findChildren(controls.CalendarQuickControls))
                self.assertIsNone(toolbar.findChild(QComboBox, "calendar_default_selector"))
                self.assertIsNone(toolbar.findChild(QPushButton, "calendar_display_button"))
                self.assertIsNone(toolbar.findChild(QPushButton, "calendar_manage_button"))
                options = next(
                    button.menu()
                    for button in toolbar.findChildren(QPushButton)
                    if button.menu()
                    and any(
                        action.text() == t("menu.calendar_manage", "캘린더 관리...")
                        for action in button.menu().actions()
                    )
                )
                visible_names = {
                    action.text()
                    for action in options.actions()
                    if getattr(action, "_cal_vis_action", False) and action.isCheckable()
                }
                self.assertIn("local::personal", visible_names)
                visibility = next(
                    action
                    for action in options.actions()
                    if getattr(action, "_cal_vis_action", False)
                    and action.text() == "local::personal"
                )
                previous = visibility.isChecked()
                visibility.trigger()
                self.assertEqual(
                    bool(calendar_repo.get_calendar("local::personal")["is_visible"]), not previous
                )
                self.assertEqual(
                    self.host.refreshes[-1], {"left": True, "center": True, "right": True}
                )
                with patch.object(self.host, "open_calendar_management") as manage:
                    next(
                        action
                        for action in options.actions()
                        if action.text() == t("menu.calendar_manage", "캘린더 관리...")
                    ).trigger()
                    manage.assert_called_once()
                with patch.object(calendar_repo, "list_calendars", return_value=[]):
                    options.aboutToShow.emit()
                    self.assertTrue(
                        any(
                            action.text() == t("menu.calendar_manage", "캘린더 관리...")
                            for action in options.actions()
                        )
                    )
                with patch.object(
                    calendar_repo, "list_calendars", side_effect=sqlite3.OperationalError("locked")
                ):
                    options.aboutToShow.emit()
                    self.assertTrue(
                        any(
                            action.text() == t("menu.calendar_manage", "캘린더 관리...")
                            for action in options.actions()
                        )
                    )
                self.qapp.processEvents()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_main_preferences_do_not_delete_queued_remote_operations(self):
        conn = db_repository_unified.get_connection()
        conn.execute(
            "INSERT INTO gcal_delete_queue(gcal_event_id,gcal_calendar_id) VALUES('pending-delete','old@example.test')"
        )
        conn.commit()
        before = [tuple(row) for row in conn.execute("SELECT * FROM gcal_delete_queue")]
        self.widget.default_combo.setCurrentIndex(
            self.widget.default_combo.findData("gcal::team@example.test")
        )
        self.assertEqual(
            [tuple(row) for row in conn.execute("SELECT * FROM gcal_delete_queue")], before
        )
