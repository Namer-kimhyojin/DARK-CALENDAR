# -*- coding: utf-8 -*-
"""Render the planner to verify alpha ownership and live theme updates."""

import datetime as dt
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QPoint, QSettings, Qt
from PyQt6.QtGui import QColor, QImage, QPalette, QRegion
from PyQt6.QtWidgets import QApplication, QWidget

from calendar_app.presentation.calendar.week_time_grid import WeekTimeGrid, _css_color, _mix
from calendar_app.shared.ui_tokens import get_ui_tokens


class WeekTimeGridAppearanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.settings = QSettings(
            str(Path(self.tmpdir.name) / "appearance.ini"), QSettings.Format.IniFormat
        )
        self.settings.setFallbacksEnabled(False)
        self.tokens = self.theme("dark", 0.35)
        self.token_patch = patch(
            "calendar_app.presentation.calendar.week_time_grid.get_ui_tokens",
            return_value=self.tokens,
        )
        self.token_patch.start()
        self.addCleanup(self.token_patch.stop)
        self.grid = WeekTimeGrid()
        self.addCleanup(self.grid.close)
        self.grid.resize(960, 640)
        self.start = QDate(2028, 2, 7)
        self.grid.set_week(self.start, [], tokens=self.tokens)
        self.grid.show()
        self.app.processEvents()

    def theme(self, mode, opacity):
        return get_ui_tokens(
            settings=self.settings,
            theme_color="#4da6ff",
            text_theme=mode,
            panel_base_color="#102030" if mode == "dark" else "#f0f4f8",
            opacity_factor=opacity,
        )

    def render(self):
        image = QImage(self.grid.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        self.grid.render(image, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
        return image

    def pixel(self, canvas, point):
        image = self.render()
        return image.pixelColor(canvas.mapTo(self.grid, point))

    def test_dark_and_light_shells_retain_single_layer_alpha(self):
        for mode in ("dark", "light"):
            for opacity in (0.0, 0.35, 1.0):
                with self.subTest(mode=mode, opacity=opacity):
                    tokens = self.theme(mode, opacity)
                    self.grid.apply_theme(tokens)
                    self.app.processEvents()
                    expected = _css_color(tokens["bg_main"], QColor())
                    for canvas, point in (
                        (self.grid._header, QPoint(12, 20)),
                        (self.grid._all_day_canvas, QPoint(100, 15)),
                        (self.grid._timeline, QPoint(100, 31)),
                    ):
                        actual = self.pixel(canvas, point)
                        self.assertLessEqual(abs(actual.alpha() - expected.alpha()), 1)
                        if expected.alpha() >= 50:
                            for actual_channel, expected_channel in zip(
                                actual.getRgb()[:3], expected.getRgb()[:3], strict=True
                            ):
                                self.assertLessEqual(abs(actual_channel - expected_channel), 2)

    def test_parent_owned_surface_is_not_repainted_by_scroll_widgets(self):
        self.grid.apply_theme({**self.tokens, "calendar_bg": "transparent"})
        self.app.processEvents()
        for area in (self.grid._scroll, self.grid._all_day_scroll):
            for widget in (area, area.viewport(), area.widget()):
                self.assertFalse(widget.autoFillBackground())
                self.assertEqual(widget.palette().color(QPalette.ColorRole.Base).alpha(), 0)
        self.assertEqual(self.pixel(self.grid._timeline, QPoint(100, 31)).alpha(), 0)

    def test_reading_cards_remain_legible_at_low_shell_opacity(self):
        task = {
            "id": 1,
            "name": "예약",
            "deadline": "2028-02-07 09:00:00",
            "end_date": "2028-02-07 10:00:00",
            "all_day": 0,
        }
        for mode in ("dark", "light"):
            with self.subTest(mode=mode):
                self.grid.set_week(
                    self.start,
                    [task],
                    tokens={**self.theme(mode, 0.0), "calendar_bg": "transparent"},
                )
                self.grid.scroll_to_time(8 * 60)
                self.app.processEvents()
                rect = self.grid.event_rects()[0][2]
                color = self.pixel(
                    self.grid._timeline, QPoint(round(rect.right() - 14), round(rect.bottom() - 12))
                )
                self.assertGreaterEqual(color.alpha(), 220)
                text = self.grid._color("text_primary")
                self.assertEqual(text.alpha(), 255)
                if mode == "dark":
                    self.assertGreater(text.lightnessF(), color.lightnessF())
                else:
                    self.assertLess(text.lightnessF(), color.lightnessF())

    def test_live_theme_refresh_keeps_tasks_scroll_selection_and_drag(self):
        task = {
            "id": 1,
            "name": "예약",
            "deadline": "2028-02-07 09:00:00",
            "end_date": "2028-02-07 10:00:00",
        }
        self.grid.set_week(self.start, [task])
        self.grid.scroll_to_time(8 * 60)
        self.grid.set_selected_date(self.start.addDays(2))
        self.app.processEvents()
        selected = self.grid._segments[0].task
        self.grid._selected = selected
        self.grid._gesture = {"kind": "create", "moved": True}
        self.grid._preview = (dt.datetime(2028, 2, 7, 10), 60)
        position = self.grid._scroll.verticalScrollBar().value()
        segments = self.grid._segments
        gesture = self.grid._gesture
        preview = self.grid._preview
        visible_point = QPoint(100, position + 31)
        before = self.pixel(self.grid._timeline, visible_point)
        self.grid.apply_theme(self.theme("light", 0.75))
        self.app.processEvents()
        self.assertIs(self.grid._segments, segments)
        self.assertIs(self.grid._selected, selected)
        self.assertIs(self.grid._gesture, gesture)
        self.assertEqual(self.grid._preview, preview)
        self.assertEqual(self.grid._selected_date, self.start.addDays(2))
        self.assertEqual(self.grid._scroll.verticalScrollBar().value(), position)
        self.assertNotEqual(self.pixel(self.grid._timeline, visible_point), before)
        self.grid._cancel()

    def test_translucent_identity_colors_do_not_reduce_card_readability(self):
        for identity in ("transparent", "rgba(90,140,180,0.2)"):
            with self.subTest(identity=identity):
                task = {
                    "id": 1,
                    "name": "예약",
                    "deadline": "2028-02-07 09:00:00",
                    "end_date": "2028-02-07 10:00:00",
                    "bg_color": identity,
                }
                self.grid.set_week(
                    self.start,
                    [task],
                    tokens={**self.theme("dark", 0.0), "calendar_bg": "transparent"},
                )
                self.grid.scroll_to_time(8 * 60)
                self.app.processEvents()
                rect = self.grid.event_rects()[0][2]
                sample = QPoint(round(rect.right() - 14), round(rect.bottom() - 12))
                self.assertGreaterEqual(self.pixel(self.grid._timeline, sample).alpha(), 220)

    def test_set_week_updates_colors_and_clears_invisible_selected_date(self):
        self.grid.set_selected_date(self.start)
        before = self.pixel(self.grid._header, QPoint(12, 20))
        self.grid.set_week(self.start.addDays(7), [], tokens=self.theme("light", 1.0))
        self.app.processEvents()
        self.assertFalse(self.grid._selected_date.isValid())
        self.assertNotEqual(self.pixel(self.grid._header, QPoint(12, 20)), before)

    def test_selected_date_has_an_accent_marker(self):
        self.grid.apply_theme({**self.tokens, "calendar_bg": "transparent"})
        x = round(self.grid.GUTTER + self.grid._column_width() / 2)
        point = QPoint(x, self.grid.HEADER_HEIGHT - 4)
        before = self.pixel(self.grid._header, point)
        self.grid.set_selected_date(self.start)
        self.app.processEvents()
        after = self.pixel(self.grid._header, point)
        self.assertLess(before.alpha(), 255)
        self.assertEqual(after, self.grid._color("accent"))
        self.grid.set_selected_date(self.start.addDays(12))
        self.app.processEvents()
        self.assertEqual(self.pixel(self.grid._header, point), before)

    def test_color_interpolation_preserves_both_alphas(self):
        actual = _mix(QColor(10, 30, 50, 40), QColor(30, 50, 70, 120), 0.25)
        self.assertEqual(actual.getRgb(), (25, 45, 65, 100))

    def test_unchanged_theme_does_not_reapply_scroll_styles(self):
        with patch.object(self.grid, "_apply_scrollbar_theme") as apply_styles:
            self.grid.apply_theme(self.tokens)
        apply_styles.assert_not_called()


if __name__ == "__main__":
    unittest.main()
