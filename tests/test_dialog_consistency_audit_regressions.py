# -*- coding: utf-8 -*-
"""Native dialog regressions found by the November consistency audit."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate, QPoint, QSettings
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QPushButton, QWidget

from calendar_app.infrastructure.runtime.keyboard_shortcuts import render_keycaps_html
from calendar_app.presentation.dialogs.calendar_print_dialog import CalendarPrintDialog
from calendar_app.presentation.dialogs.checklist_manager_dialog_advanced import (
    ChecklistManagerDialog,
)
from calendar_app.presentation.dialogs.dialog_token_editor_dialog import DialogTokenEditorDialog
from calendar_app.presentation.dialogs.label_settings_dialog import LabelSettingsDialog
from calendar_app.presentation.dialogs.management_dialogs import WorkManagementTabbedDialog
from calendar_app.presentation.dialogs.routine_recurrence_wizard import RoutineRecurrenceWizard
from calendar_app.shared.color_utils import contrast_ratio
from calendar_app.shared.icon_map import ICON
from tests.support import TemporaryDatabaseTestCase


class DialogConsistencyAuditRegressions(TemporaryDatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.host = QWidget()
        self.addCleanup(self.host.close)
        self.host.settings = QSettings(
            str(Path(self.temp.name) / "audit.ini"), QSettings.Format.IniFormat
        )
        for key, value in {
            "theme_color": "#c5a3f5",
            "panel_base_color": "#121827",
            "text_theme": "dark",
            "last_opacity": 255,
        }.items():
            self.host.settings.setValue(key, value)
        self.host.current_date = QDate(2026, 11, 5)
        self.host.view_mode_state = "monthly"
        self.host.cal_show_weekends = True
        self.host.cal_start_monday = False

    def test_recurrence_preview_keeps_neutral_text_and_displays_actual_date(self):
        dialog = RoutineRecurrenceWizard(self.host.current_date, parent=self.host)
        self.addCleanup(dialog.close)
        self.assertIn(dialog.get_result()["next_occurrence"], dialog.next_label.text())
        self.assertIn(dialog._ui_tokens["text_primary"], dialog.summary_label.styleSheet())
        self.assertIn(dialog._ui_tokens["text_secondary"], dialog.next_label.styleSheet())
        self.assertNotIn("color: white", dialog.summary_label.styleSheet())
        self.assertNotIn("#9fe2a3", dialog.next_label.styleSheet())
        self.assertIn(f"background: {dialog._ui_tokens['check_checked_bg']};", dialog.styleSheet())

    def test_recurrence_compatible_with_a_prefix_without_date_placeholder(self):
        from calendar_app.presentation.dialogs import routine_recurrence_wizard as wizard

        original = wizard.t

        def translate(key, *args, **kwargs):
            return (
                "다음:"
                if key == "recurrence.next_occurrence_prefix"
                else original(key, *args, **kwargs)
            )

        with patch.object(wizard, "t", side_effect=translate):
            dialog = RoutineRecurrenceWizard(self.host.current_date, parent=self.host)
        self.addCleanup(dialog.close)
        self.assertEqual(
            dialog.next_label.text(), f"다음: {dialog.get_result()['next_occurrence']}"
        )

    def test_token_presets_are_ready_on_initial_open_and_follow_explicit_draft_mode(self):
        dialog = DialogTokenEditorDialog(self.host, text_theme="light", persist_on_apply=False)
        self.addCleanup(dialog.close)
        self.assertTrue(dialog.preset_mode_light.isChecked())
        self.assertGreater(dialog.color_preset_combo.count(), 2)
        self.assertTrue(dialog.color_preset_combo.currentText())
        self.assertTrue(dialog.color_preset_note.text())

    def test_print_scroll_content_does_not_fill_with_native_light_palette(self):
        with patch(
            "calendar_app.presentation.dialogs.calendar_print_dialog.list_calendars",
            return_value=[],
        ):
            dialog = CalendarPrintDialog(self.host)
        self.addCleanup(dialog.close)
        self.assertFalse(dialog.content_scroll.widget().autoFillBackground())
        self.assertFalse(dialog.content_scroll.viewport().autoFillBackground())

    def test_help_keycaps_use_theme_text_and_preserve_html_escaping(self):
        tokens = {
            "text_primary": "#101318",
            "text_muted": "#68717d",
            "surface_item": "#fbfaff",
            "border_soft": "#dedbe8",
        }
        result = render_keycaps_html("Ctrl+<tag>", tokens=tokens)
        self.assertIn("color:#101318", result)
        self.assertIn("&lt;tag&gt;", result)
        self.assertNotIn("#d7e5f7", result)
        self.assertGreaterEqual(contrast_ratio(tokens["text_primary"], tokens["surface_item"]), 4.5)
        self.assertIn("#d7e5f7", render_keycaps_html("Ctrl+N"))

    def test_checklist_icons_follow_effective_button_text_color(self):
        instance = SimpleNamespace(
            _main_style_bundle={
                "button_secondary": "QPushButton { color: #d7deed; background: transparent; }"
            },
            _ui_tokens={"text_primary": "#f0f2f8"},
        )
        with patch(
            "calendar_app.presentation.dialogs.checklist_manager_dialog_advanced._ic",
            return_value=QIcon(),
        ) as icon:
            button = ChecklistManagerDialog._make_icon_btn(
                instance, ICON.SAVE, "저장", "button_secondary"
            )
        self.addCleanup(button.close)
        self.assertEqual(icon.call_args.kwargs["color"], "#d7deed")

    def test_label_and_checklist_modal_footers_keep_shared_roles_and_target_height(self):
        with patch(
            "calendar_app.presentation.dialogs.dialog_styles._available_dialog_bounds",
            return_value=(1400, 1000),
        ):
            for factory in (LabelSettingsDialog, ChecklistManagerDialog):
                with self.subTest(dialog=factory.__name__):
                    dialog = factory(self.host)
                    self.addCleanup(dialog.close)
                    dialog.show()
                    for _ in range(3):
                        self.app.processEvents()
                    buttons = [
                        button
                        for button in dialog.findChildren(QPushButton)
                        if button.property("dialogFooter")
                    ]
                    self.assertEqual(len(buttons), 2)
                    self.assertEqual(
                        {button.objectName() for button in buttons}, {"primary_btn", "ghost_btn"}
                    )
                    self.assertTrue(all(button.height() >= 44 for button in buttons))
                    self.assertEqual(buttons[0].height(), buttons[1].height())
                    self.assertTrue(all(not button.styleSheet() for button in buttons))
                    dialog.close()

    def test_management_compact_footer_preserves_complete_button_labels(self):
        with patch(
            "calendar_app.presentation.dialogs.dialog_styles._available_dialog_bounds",
            return_value=(992, 712),
        ):
            dialog = WorkManagementTabbedDialog(self.host)
            self.addCleanup(dialog.close)
            dialog.show()
            for _ in range(3):
                self.app.processEvents()
            child = dialog._tab_instances[0]
            for button in child.findChildren(QPushButton):
                if not button.isVisible():
                    continue
                point = button.mapTo(dialog, QPoint())
                self.assertGreaterEqual(button.width(), button.sizeHint().width(), button.text())
                self.assertGreaterEqual(point.x(), 0)
                self.assertLessEqual(point.x() + button.width(), dialog.width(), button.text())


if __name__ == "__main__":
    unittest.main()
