# -*- coding: utf-8 -*-
"""Verify applied Qt text sizes and usable geometry without real user settings."""

from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QCoreApplication, QDate, QEvent, QSettings
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

from calendar_app import bootstrap
from calendar_app.presentation.calendar import month_renderer
from calendar_app.presentation.calendar.week_time_grid import WeekTimeGrid
from calendar_app.presentation.main_window.action_handlers_tasks import TaskActionsMixin
from calendar_app.presentation.main_window.top_bar_builder import build_top_bar_frame_style
from calendar_app.presentation.main_window.window_ui_actions import build_ui_font
from calendar_app.presentation.panels import side_panel_renderer
from calendar_app.presentation.theme.style_builder import (
    _font_points,
    build_global_stylesheet,
    build_tooltip_stylesheet,
)
from calendar_app.presentation.widgets.widget_mode_typography import read_widget_typography
from calendar_app.shared.typography import get_typography_scale
from tests.support import TemporaryDatabaseTestCase
from tests.test_week_planner_integration import CalendarRenderHost


class MainTypographyRoleTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.original_font = QFont(self.app.font())
        self.original_style = self.app.styleSheet()
        self.app.setStyleSheet("")
        self.settings = QSettings(
            str(Path(self._tmpdir.name) / "typography.ini"), QSettings.Format.IniFormat
        )
        self.settings.setFallbacksEnabled(False)
        self.settings.setValue("gcal_enabled", False)
        self.widgets = []
        self.enterContext(patch("calendar_app.shared.theme_settings.QSettings", return_value=self.settings))
        self.enterContext(patch("calendar_app.shared.theme_snapshot.QSettings", return_value=self.settings))

    def tearDown(self):
        for widget in self.widgets:
            widget.close()
            widget.deleteLater()
        self.app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.setStyleSheet(self.original_style)
        self.app.setFont(self.original_font)
        month_renderer.invalidate_calendar_meta_cache()
        super().tearDown()

    def apply_base(self, points):
        font = QFont(self.original_font)
        font.setPointSize(points)
        self.app.setFont(font)
        self.settings.setValue("font_size", points)
        return get_typography_scale(self.settings)

    def test_bootstrap_uses_eleven_only_for_new_or_invalid_preference(self):
        self.settings.setValue("font_family", self.original_font.family())
        with patch.object(bootstrap, "QSettings", return_value=self.settings):
            bootstrap._apply_saved_font(self.app, build_ui_font)
            self.assertEqual(self.app.font().pointSize(), 11)
            self.assertFalse(self.settings.contains("font_size"))
            for points in (8, 10, 14):
                with self.subTest(saved_points=points):
                    self.settings.setValue("font_size", points)
                    before = {key: self.settings.value(key) for key in self.settings.allKeys()}
                    bootstrap._apply_saved_font(self.app, build_ui_font)
                    self.assertEqual(self.app.font().pointSize(), points)
                    self.assertEqual(
                        {key: self.settings.value(key) for key in self.settings.allKeys()}, before
                    )
            self.settings.setValue("font_size", -1)
            bootstrap._apply_saved_font(self.app, build_ui_font)
            self.assertEqual(self.app.font().pointSize(), 11)

    def test_global_default_and_malformed_font_styles_match_bootstrap(self):
        for malformed in (None, "bad", float("nan"), float("inf"), -3):
            with self.subTest(value=malformed):
                self.assertEqual(_font_points(malformed), 11)
        self.assertIn("font-size: 11pt;", build_global_stylesheet())
        self.assertIn("font-size: 11pt;", build_tooltip_stylesheet())
        self.assertIn("font-size: 10pt;", build_global_stylesheet(base_pt=10))

    def test_actual_month_header_and_selection_share_roles_and_font_family(self):
        for base in (10, 11, 14):
            with self.subTest(base=base):
                scale = self.apply_base(base)
                host = CalendarRenderHost(self.settings)
                self.widgets.append(host)
                host.view_mode_state = "monthly"
                host.resize(1800, 950)
                with patch.object(month_renderer, "_get_subscription_events", return_value=[]):
                    month_renderer.render_calendar(host)
                host.show()
                self.app.processEvents()
                date = host.findChild(QPushButton, "calendar_date_selector")
                self.assertAlmostEqual(date.font().pointSizeF(), scale.display_pt, delta=0.1)
                self.assertGreaterEqual(date.height(), date.fontMetrics().height())
                host.selected_task_ids = {1, 2}
                TaskActionsMixin.update_task_selection_status(host)
                self.app.processEvents()
                hint = host.selection_status_lbl
                self.assertAlmostEqual(hint.font().pointSizeF(), scale.caption_pt, delta=0.1)
                self.assertEqual(hint.font().family(), self.app.font().family())
                self.assertGreaterEqual(hint.height(), hint.fontMetrics().height())
                host.close()

    def test_brand_label_uses_title_role_without_rewriting_preference(self):
        for base in (10, 11, 14):
            with self.subTest(base=base):
                scale = self.apply_base(base)
                frame = QWidget()
                self.widgets.append(frame)
                label = QLabel("Air Calendar", frame)
                label.setObjectName("app_brand")
                before = {key: self.settings.value(key) for key in self.settings.allKeys()}
                frame.setStyleSheet(build_top_bar_frame_style(self.settings))
                label.ensurePolished()
                self.assertAlmostEqual(label.font().pointSizeF(), scale.title_pt, delta=0.1)
                self.assertEqual(
                    {key: self.settings.value(key) for key in self.settings.allKeys()}, before
                )

    def test_checklist_rows_fit_korean_text_and_numbered_indicators(self):
        for base in (10, 11, 14):
            with self.subTest(base=base):
                scale = self.apply_base(base)
                host = CalendarRenderHost(self.settings)
                self.widgets.append(host)
                host.expanded_tids = {1}
                card = side_panel_renderer.create_task_box(
                    host,
                    "월간회의 준비",
                    lambda: None,
                    tid=1,
                    checklist_display_type="process",
                    checklist_items=[(f"{index}번째 확인 항목", False, lambda: None) for index in range(1, 12)],
                )
                self.widgets.append(card)
                card.resize(400, card.sizeHint().height())
                card.show()
                self.app.processEvents()
                toggle = card.findChild(QPushButton, "panel_checklist_toggle")
                self.assertGreaterEqual(toggle.height(), toggle.fontMetrics().height() + 4)
                for row in card.findChildren(QWidget, "panel_checklist_row"):
                    text = row.findChild(QLabel, "panel_checklist_text")
                    indicator = row.findChild(QPushButton, "panel_checklist_indicator")
                    self.assertAlmostEqual(text.font().pointSizeF(), scale.caption_pt, delta=0.1)
                    self.assertGreaterEqual(row.height(), text.fontMetrics().height() + 4)
                    self.assertGreaterEqual(
                        indicator.width(), indicator.fontMetrics().horizontalAdvance(indicator.text())
                    )
                    self.assertGreaterEqual(indicator.height(), indicator.fontMetrics().height())

    def test_week_header_and_all_day_rows_grow_with_applied_font(self):
        grid = WeekTimeGrid()
        self.widgets.append(grid)
        grid.resize(1100, 750)
        previous = 0
        for base in (10, 11, 14):
            with self.subTest(base=base):
                scale = self.apply_base(base)
                grid.setFont(self.app.font())
                grid.set_week(QDate(2026, 11, 2), [])
                grid.show()
                self.app.processEvents()
                caption = QFontMetrics(grid._role_font("caption"))
                section = QFontMetrics(grid._role_font("section"))
                body = QFontMetrics(grid._role_font())
                self.assertEqual(grid._role_font().pointSizeF(), scale.body_pt)
                self.assertGreaterEqual(grid.HEADER_HEIGHT, caption.height() + section.height() + 12)
                self.assertGreaterEqual(grid.ALL_DAY_ROW, body.height() + 8)
                self.assertGreaterEqual(grid.GUTTER, caption.horizontalAdvance("00:00") + 18)
                self.assertGreaterEqual(grid.HEADER_HEIGHT, previous)
                previous = grid.HEADER_HEIGHT

    def test_subscription_copy_and_footer_buttons_fit_larger_font(self):
        for base in (10, 14):
            with self.subTest(base=base):
                self.apply_base(base)

                def inspect(dialog):
                    self.widgets.append(dialog)
                    dialog.show()
                    self.app.processEvents()
                    copy = dialog.findChild(QPushButton, "ghostBtn")
                    self.assertIsNotNone(copy)
                    self.assertGreaterEqual(copy.height(), copy.fontMetrics().height() + 4)
                    self.assertGreaterEqual(
                        copy.width(), copy.fontMetrics().horizontalAdvance(copy.text())
                    )
                    for button in dialog.findChildren(QPushButton):
                        if button.objectName() in {"PrimaryBtn", "SecondaryBtn"}:
                            self.assertGreaterEqual(button.height(), button.fontMetrics().height())
                    dialog.close()
                    return 0

                with patch("PyQt6.QtWidgets.QDialog.exec", new=inspect):
                    month_renderer._show_subscription_detail(
                        {
                            "name": "구독 일정 상세 확인",
                            "deadline": "2026-11-05 10:00:00",
                            "end_date": "2026-11-05 11:00:00",
                            "_gcal_event_id": "read-only-subscription-event",
                        }
                    )

    def test_workspace_caption_floor_keeps_widget_preferences_and_large_faces(self):
        self.settings.setValue("font_size", 14)
        self.settings.setValue("oi_clock_font_size", 72)
        self.settings.setValue("oi_note_font_size", 36)
        previous_body = 0
        for preference in (10, 12, 18):
            with self.subTest(preference=preference):
                self.settings.setValue("widget_mode_font_size", preference)
                before = {key: self.settings.value(key) for key in self.settings.allKeys()}
                scale = read_widget_typography(self.settings)
                self.assertEqual(scale.preference, preference)
                self.assertGreaterEqual(scale.secondary, 9.5)
                self.assertGreaterEqual(scale.body, 10.5)
                self.assertGreaterEqual(scale.body, previous_body)
                self.assertEqual(scale.title, scale.body)
                previous_body = scale.body
                self.assertEqual(
                    {key: self.settings.value(key) for key in self.settings.allKeys()}, before
                )
