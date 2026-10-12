# -*- coding: utf-8 -*-
"""Calendar-manager display visibility across actual calendar renderers."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication, QEvent, QPointF, QSettings, Qt
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

from calendar_app.infrastructure.db import calendar_repo, db_repository_unified, task_repo
from calendar_app.presentation.calendar import month_renderer
from calendar_app.presentation.calendar.week_time_grid import WeekTimeGrid
from calendar_app.presentation.dialogs.calendar_manager_page import CalendarManagerPage
from calendar_app.presentation.widgets.ui_components import DraggableTaskButton
from tests.support import TemporaryDatabaseTestCase
from tests.test_week_planner_integration import CalendarRenderHost


class CalendarVisibilityIntegrationTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.settings = QSettings(
            str(Path(self._tmpdir.name) / "visibility.ini"), QSettings.Format.IniFormat
        )
        self.settings.setValue("gcal_enabled", True)
        self.settings.setValue("gcal_primary_resolved_id", "team@example.test")
        self.settings.setValue("theme_color", "#5294f7")
        self.settings.setValue("text_theme", "light")
        self.settings.setValue("panel_base_color", "#202735")
        self.settings.setValue("last_opacity", 255)
        self.settings.setValue("last_opacity_unit", "byte")
        self.host = CalendarRenderHost(self.settings)
        self.host.resize(1800, 1300)
        self.theme_patch = patch(
            "calendar_app.shared.theme_settings.QSettings", return_value=self.settings
        )
        self.snapshot_patch = patch(
            "calendar_app.shared.theme_snapshot.QSettings", return_value=self.settings
        )
        self.primary_patch = patch.object(
            db_repository_unified,
            "_resolved_primary_gcal_id_for_query",
            return_value="team@example.test",
        )
        self.theme_patch.start()
        self.snapshot_patch.start()
        self.primary_patch.start()
        month_renderer.invalidate_calendar_meta_cache()
        for identity, kind, name, google in (
            ("local::work", "local", "Local Work", None),
            ("gcal::team@example.test", "gcal", "Visibility Team", "team@example.test"),
            ("gcal::primary", "gcal", "Legacy Primary", "primary"),
            ("gcal::holidays@example.test", "gcal", "Public Holidays", "holidays@example.test"),
        ):
            self.assertTrue(
                calendar_repo.upsert_calendar(
                    identity,
                    kind,
                    name,
                    "#5294f7",
                    gcal_calendar_id=google,
                    access_role="owner" if kind == "gcal" else None,
                    is_default=kind == "local",
                    is_visible=True,
                )
            )
        self.coordinator = SimpleNamespace(calendar_rows=[], calendar_providers={}, states={})

        def refresh():
            self.coordinator.calendar_rows = calendar_repo.list_calendars(include_inactive=True)
            self.coordinator.calendar_providers = {
                row["id"]: "google"
                for row in self.coordinator.calendar_rows
                if row["type"] == "gcal"
            }

        self.coordinator.refresh = refresh
        refresh()
        self.page = CalendarManagerPage(self.host, self.coordinator, lambda *_: None)
        self._select_team()

    def tearDown(self):
        self.page.close()
        self.page.deleteLater()
        self.host.close()
        self.host.deleteLater()
        self.qt_app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.primary_patch.stop()
        self.snapshot_patch.stop()
        self.theme_patch.stop()
        month_renderer.invalidate_calendar_meta_cache()
        super().tearDown()

    def _select_team(self):
        for index in range(self.page.calendars.count()):
            item = self.page.calendars.item(index)
            if item.data(Qt.ItemDataRole.UserRole)["id"] == "gcal::team@example.test":
                self.page.calendars.setCurrentItem(item)
                return
        self.fail("Team calendar was not available in the real manager list")

    def _task(self, name, *, day=7, all_day=False, calendar_id=None, **google):
        date = f"2026-10-{day:02d}"
        identity = task_repo.create_unified_task(
            {
                "name": name,
                "type": "schedule",
                "priority": "normal",
                "status": "in_progress",
                "deadline": date if all_day else date + " 09:00:00",
                "end_date": date if all_day else date + " 10:00:00",
                "target_date": date,
                "all_day": int(all_day),
                "calendar_id": calendar_id,
                **google,
            }
        )
        self.assertIsNotNone(identity)
        return identity

    def _render(self, mode="hourly"):
        self.host.view_mode_state = "monthly" if mode == "monthly" else "weekly_1"
        self.host.cal_week_layout = "date" if mode == "date" else "time"
        with patch.object(month_renderer, "_get_subscription_events", return_value=[]):
            month_renderer.render_calendar(self.host)
        self.host.show()
        self.qt_app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def _source_ids(self):
        return {row["id"] for row in self.host._latest_calendar_range_data["rows"]}

    def _rendered_ids(self, mode):
        if mode == "hourly":
            grids = self.host.center_frame.findChildren(WeekTimeGrid)
            self.assertEqual(len(grids), 1)
            return {segment.task["id"] for segment in [*grids[0]._segments, *grids[0]._all_day]}
        return {
            button.task_id for button in self.host.center_frame.findChildren(DraggableTaskButton)
        }

    def _raw_tasks(self):
        conn = db_repository_unified.get_connection()
        return [dict(row) for row in conn.execute("SELECT * FROM unified_task ORDER BY id")]

    def test_manager_checkbox_hides_and_restores_google_variants_in_every_view_and_widget_cache(
        self,
    ):
        team_ids = set()
        for index, variant in enumerate(
            ("canonical", "primary", "missing", "source-only", "stale-local")
        ):
            for all_day in (False, True):
                stored = {
                    "canonical": "gcal::team@example.test",
                    "primary": "gcal::primary",
                    "missing": None,
                    "source-only": "",
                    "stale-local": "local::work",
                }[variant]
                google = {"gcal_source_calendar_id": "team@example.test"}
                if variant != "source-only":
                    google.update(
                        gcal_event_id=f"{variant}-{int(all_day)}", gcal_sync_mode="remote_mirror"
                    )
                else:
                    google.update(gcal_event_id=None, gcal_sync_mode="")
                team_ids.add(
                    self._task(
                        f"{variant}-{int(all_day)}",
                        day=5 + index,
                        all_day=all_day,
                        calendar_id=stored,
                        **google,
                    )
                )
        local_linked = self._task(
            "Locally owned with outbound Google linkage",
            day=5,
            calendar_id="local::work",
            gcal_event_id="outbound-local",
            gcal_sync_mode="local_owned",
            gcal_source_calendar_id="team@example.test",
            gcal_target_calendar_id="team@example.test",
        )
        local_holiday = self._task("한글날", day=6, all_day=True, gcal_sync_mode="local_owned")
        google_holiday = self._task(
            "한글날",
            day=7,
            all_day=True,
            calendar_id="gcal::holidays@example.test",
            gcal_event_id="public-holiday",
            gcal_sync_mode="remote_mirror",
            gcal_source_calendar_id="holidays@example.test",
        )
        other_ids = {local_linked, local_holiday, google_holiday}
        before = self._raw_tasks()
        for mode in ("hourly", "date", "monthly"):
            with self.subTest(mode=mode):
                self._render(mode)
                self.assertEqual(self._source_ids(), team_ids | other_ids)
                self.assertEqual(self._rendered_ids(mode), team_ids | other_ids)
                self._select_team()
                self.assertTrue(self.page.visible.isChecked())
                self.page.visible.click()
                self.assertFalse(
                    calendar_repo.get_calendar("gcal::team@example.test")["is_visible"]
                )
                self.assertEqual(
                    self.host.refreshes[-1], {"left": True, "center": True, "right": True}
                )
                self._render(mode)
                self.assertEqual(self._source_ids(), other_ids)
                self.assertEqual(self._rendered_ids(mode), other_ids)
                self._select_team()
                self.assertFalse(self.page.visible.isChecked())
                self.page.visible.click()
                self._render(mode)
                self.assertEqual(self._source_ids(), team_ids | other_ids)
                self.assertEqual(self._rendered_ids(mode), team_ids | other_ids)
        self.assertEqual(self._raw_tasks(), before)

    def test_hidden_default_remains_selected_for_creation_and_keeps_saved_ownership(self):
        from calendar_app.presentation.dialogs.task_dialog_unified import UnifiedTaskDialog

        self.assertTrue(calendar_repo.set_calendar_default("gcal::team@example.test"))
        self.page.visible.click()
        selector_host = QWidget()
        selector = SimpleNamespace(
            _ui_tokens=lambda: {}, _accent_rgba=lambda *_: "rgba(82,148,247,0.22)"
        )
        try:
            UnifiedTaskDialog._build_calendar_selector(selector, QVBoxLayout(selector_host))
            selected = UnifiedTaskDialog._get_selected_calendar_id(selector)
            self.assertEqual(selected, "gcal::team@example.test")
            identity = self._task(
                "New task in hidden default", calendar_id=selected, gcal_sync_mode="local_owned"
            )
            saved = task_repo.get_unified_task(identity)
            for mode in ("hourly", "date", "monthly"):
                self._render(mode)
                self.assertNotIn(identity, self._source_ids())
                self.assertNotIn(identity, self._rendered_ids(mode))
            self._select_team()
            self.page.visible.click()
            self._render()
            self.assertIn(identity, self._source_ids())
            self.assertEqual(task_repo.get_unified_task(identity), saved)
            self.assertEqual(calendar_repo.get_default_calendar()["id"], selected)
        finally:
            selector_host.close()
            selector_host.deleteLater()

    def test_equal_title_holidays_keep_their_distinct_sources_in_weekly_hover(self):
        local_id = self._task(
            "한글날", day=9, all_day=True, calendar_id="local::work", gcal_sync_mode="local_owned"
        )
        holiday_id = self._task(
            "한글날",
            day=9,
            all_day=True,
            calendar_id="gcal::holidays@example.test",
            gcal_event_id="holiday-source",
            gcal_sync_mode="remote_mirror",
            gcal_source_calendar_id="holidays@example.test",
        )
        self.page.visible.click()
        self._render()
        self.assertEqual(self._source_ids(), {local_id, holiday_id})
        grid = self.host.center_frame.findChildren(WeekTimeGrid)[0]
        expected = {local_id: "Local Work", holiday_id: "Public Holidays"}
        grid._relayout()
        for segment, rect in grid._all_day_rects:
            point = rect.center()
            grid._move(
                grid._all_day_canvas,
                point,
                QPointF(grid._all_day_canvas.mapToGlobal(point.toPoint())),
            )
            self.assertIn("한글날", grid._all_day_canvas.toolTip())
            self.assertIn(expected[segment.task["id"]], grid._all_day_canvas.toolTip())
