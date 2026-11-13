# -*- coding: utf-8 -*-
"""Briefing choices fit the settings column while preserving the unsaved draft."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QSettings
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QBoxLayout, QWidget
import pytest

from calendar_app.presentation.dialogs import daily_summary_dialog as daily


@pytest.mark.parametrize("base_pt", [10, 11, 14, 24])
def test_settings_column_reflows_choices_without_clipping_or_losing_draft(base_pt):
    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory() as temporary:
        parent = QWidget()
        parent.setFont(QFont("Malgun Gothic", base_pt))
        parent.settings = QSettings(str(Path(temporary) / "daily.ini"), QSettings.Format.IniFormat)
        parent.settings.setValue("font_size", base_pt)
        parent.settings.setValue("font_family", "Malgun Gothic")
        parent.settings.setValue(daily._SETTINGS_KEY_STARTUP_ENABLED, True)
        with (
            patch.object(daily.DailySummaryDialog, "_load_schedule", return_value=["일정"]),
            patch.object(
                daily.DailySummaryDialog,
                "_load_due_routines",
                return_value=[("업무", "50%", "태그")],
            ),
        ):
            dialog = daily.DailySummaryDialog(parent=parent, show_settings=True)
        try:
            dialog.settings_panel.setFixedWidth(320)
            dialog.show()
            for _ in range(5):
                app.processEvents()
            for buttons in dialog._visibility_buttons.values():
                for button in buttons.values():
                    needed = button.fontMetrics().horizontalAdvance(button.text()) + 20
                    assert button.width() >= needed, (
                        base_pt,
                        button.text(),
                        button.width(),
                        needed,
                    )
                    viewport = dialog._settings_scroll.viewport()
                    left = button.mapTo(viewport, QPoint()).x()
                    assert left >= 0
                    assert left + button.width() <= viewport.width()
            schedule = dialog._visibility_buttons["schedule"][daily._MODE_WHEN_AVAILABLE]
            routine = dialog._visibility_buttons["routine"][daily._MODE_WHEN_AVAILABLE]
            schedule.setChecked(True)
            routine.setChecked(True)
            dialog.startup_toggle.setChecked(False)
            dialog.summary_panel.hide()
            dialog.panel_divider.hide()
            dialog.settings_panel.setFixedWidth(840)
            for _ in range(5):
                app.processEvents()
            assert all(
                row.direction() == QBoxLayout.Direction.LeftToRight
                for row in dialog._visibility_choice_rows
            )
            dialog.settings_panel.setFixedWidth(320)
            for _ in range(5):
                app.processEvents()
            assert schedule.isChecked() and routine.isChecked()
            assert not dialog.startup_toggle.isChecked()
            assert daily._setting_bool(parent.settings, daily._SETTINGS_KEY_STARTUP_ENABLED, False)
            assert dialog.settings_save_btn.isVisible()
            assert not dialog.settings_footer.visibleRegion().isEmpty()
            dialog.settings_save_btn.click()
            assert (
                parent.settings.value(daily._SETTINGS_KEY_SCHEDULE_MODE)
                == daily._MODE_WHEN_AVAILABLE
            )
            assert (
                parent.settings.value(daily._SETTINGS_KEY_ROUTINE_MODE)
                == daily._MODE_WHEN_AVAILABLE
            )
            assert not daily._setting_bool(
                parent.settings, daily._SETTINGS_KEY_STARTUP_ENABLED, True
            )
        finally:
            dialog.close()
            parent.close()
            dialog.deleteLater()
            parent.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
