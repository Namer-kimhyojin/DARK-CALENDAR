# -*- coding: utf-8 -*-
"""Start/end editors form one aligned range without distant connector gaps."""

from PyQt6.QtCore import QPoint, QSettings, QTime
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QBoxLayout

from calendar_app.presentation.dialogs.task_dialog_unified import UnifiedTaskDialog
from tests.support import TemporaryDatabaseTestCase


class ScheduleTimeRangeLayoutTests(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = QApplication.instance() or QApplication([])

    def test_range_geometry_follows_the_same_input_height_and_small_gaps(self):
        previous = QFont(self.app.font())
        settings = QSettings("kimhyojin", "Dark Calendar")
        try:
            for points in (10, 11, 14, 24):
                with self.subTest(points=points):
                    settings.setValue("font_size", points)
                    self.app.setFont(QFont("Malgun Gothic", points))
                    dialog = UnifiedTaskDialog(
                        task_type="schedule", initial_time=QTime(6, 30), end_time=QTime(7, 30)
                    )
                    try:
                        dialog.show()
                        dialog.all_day_check.setChecked(False)
                        dialog.resize(680, 640)
                        for _ in range(3):
                            self.app.processEvents()
                        dialog._update_period_layout_for_width(680)
                        dialog.layout().activate()
                        self.app.processEvents()
                        start = dialog.start_time
                        end = dialog.end_time
                        arrow = dialog._period_direction_label
                        self.assertEqual(start.height(), end.height())
                        self.assertLessEqual(abs(start.width() - end.width()), 1)
                        start_right = start.mapTo(dialog, QPoint(start.width(), 0)).x()
                        arrow_left = arrow.mapTo(dialog, QPoint()).x()
                        arrow_right = arrow.mapTo(dialog, QPoint(arrow.width(), 0)).x()
                        end_left = end.mapTo(dialog, QPoint()).x()
                        self.assertLessEqual(arrow_left - start_right, 10)
                        self.assertLessEqual(end_left - arrow_right, 10)
                        arrow_y = arrow.mapTo(dialog, arrow.contentsRect().center()).y()
                        start_y = start.mapTo(dialog, start.rect().center()).y()
                        self.assertLessEqual(abs(arrow_y - start_y), 3)
                        self.assertGreaterEqual(start.height(), start.fontMetrics().height())
                        self.assertEqual(start.time(), QTime(6, 30))
                        self.assertEqual(end.time(), QTime(7, 30))
                        dialog._update_period_layout_for_width(480)
                        self.assertEqual(
                            dialog._period_range_layout.direction(),
                            QBoxLayout.Direction.TopToBottom,
                        )
                        self.assertEqual(arrow.text(), "↓")
                        self.assertEqual(arrow.contentsMargins().top(), 0)
                    finally:
                        dialog.close()
                        dialog.deleteLater()
                        self.app.processEvents()
        finally:
            self.app.setFont(previous)
