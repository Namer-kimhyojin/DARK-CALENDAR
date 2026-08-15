# -*- coding: utf-8 -*-
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QToolButton,
    QWidget,
)

from calendar_app.presentation.dialogs.away_settings_dialog import AwaySettingsDialog
from calendar_app.presentation.dialogs.checklist_manager_dialog_advanced import (
    BulkOperationsDialog,
    ChecklistItemEditDialog,
)
from calendar_app.presentation.dialogs.daily_summary_dialog import DailySummaryDialog
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
    build_dialog_stylesheet,
    get_dialog_theme_tokens,
)
from calendar_app.presentation.dialogs.gcal_settings_dialog import GCalSettingsDialog
from calendar_app.presentation.dialogs.help_center_dialog import HelpCenterDialog


def _show_and_polish(dialog: QDialog) -> None:
    dialog.show()
    QApplication.processEvents()
    QApplication.processEvents()


class _SettingsParent(QWidget):
    def __init__(self, name: str):
        super().__init__()
        self.settings = QSettings("CodexTests", name)


class DialogUsabilityAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_common_dialog_adds_accessibility_and_fits_active_screen(self):
        dialog = QDialog()
        self.addCleanup(dialog.close)
        dialog.setWindowTitle("접근성 및 화면 맞춤")
        form = QFormLayout(dialog)

        field_label = QLabel("일정 이름:")
        field = QLineEdit()
        form.addRow(field_label, field)

        icon_button = QPushButton()
        icon_button.setToolTip("일정 새로 고침")
        form.addRow(icon_button)

        combo = QComboBox()
        combo.addItem("아주 긴 캘린더 선택 항목")
        form.addRow("캘린더:", combo)

        footer, ok_button, cancel_button = build_dialog_footer()
        form.addRow(footer)
        apply_common_dialog_style(dialog, minimum_width=1200, size=(1400, 1000))
        _show_and_polish(dialog)

        available = dialog.screen().availableGeometry()
        self.assertLessEqual(dialog.width(), max(360, available.width() - 32))
        self.assertLessEqual(dialog.height(), max(280, available.height() - 56))
        self.assertEqual(dialog.accessibleName(), dialog.windowTitle())
        self.assertIs(field_label.buddy(), field)
        self.assertEqual(field.accessibleName(), "일정 이름")
        self.assertEqual(icon_button.accessibleName(), "일정 새로 고침")
        self.assertGreaterEqual(combo.minimumContentsLength(), 18)
        self.assertTrue(ok_button.isDefault())
        self.assertFalse(cancel_button.autoDefault())
        self.assertGreaterEqual(ok_button.height(), 44)
        self.assertGreaterEqual(cancel_button.height(), 44)

    def test_common_dialog_default_labels_use_secondary_not_hint_text(self):
        tokens = get_dialog_theme_tokens()
        stylesheet = build_dialog_stylesheet()

        self.assertIn(
            f"QLabel {{\n    color: {tokens['text_secondary']};\n}}",
            stylesheet,
        )
        self.assertIn(
            f'QLabel[role="dialogSubtitle"], QLabel#dialogSubtitle, QLabel#dialog_subtitle {{\n'
            f"    color: {tokens['title_subtext']};",
            stylesheet,
        )

    def test_daily_summary_keeps_long_content_scrollable_and_footer_consistent(self):
        with (
            patch.object(
                DailySummaryDialog,
                "_load_schedule",
                return_value=["• 월간 계획 검토 09:00 ~ 10:00"],
            ),
            patch.object(
                DailySummaryDialog,
                "_load_due_routines",
                return_value=[("배포 체크", "(1/3)", "업무 · 중요")],
            ),
        ):
            dialog = DailySummaryDialog()
        self.addCleanup(dialog.close)
        _show_and_polish(dialog)

        self.assertIsInstance(dialog.summary_scroll, QScrollArea)
        self.assertTrue(dialog.summary_scroll.widgetResizable())
        self.assertTrue(dialog.ok_btn.property("dialogFooter"))
        self.assertTrue(dialog.ok_btn.isDefault())
        self.assertGreaterEqual(dialog.ok_btn.height(), 44)

    def test_help_center_is_resizable_compact_and_named(self):
        dialog = HelpCenterDialog()
        self.addCleanup(dialog.close)
        _show_and_polish(dialog)

        self.assertTrue(dialog.isSizeGripEnabled())
        self.assertLessEqual(dialog.width(), 1080)
        available = dialog.screen().availableGeometry()
        self.assertLessEqual(dialog.height(), max(280, available.height() - 56))
        self.assertLessEqual(dialog.height(), 720)
        self.assertTrue(dialog.search_input.accessibleName())
        self.assertTrue(dialog.search_input.accessibleDescription())
        self.assertTrue(dialog.nav_list.accessibleName())
        close_button = dialog.findChild(QPushButton, "primary_btn")
        self.assertIsNotNone(close_button)
        self.assertTrue(close_button.property("dialogFooter"))
        self.assertGreaterEqual(close_button.height(), 44)

    def test_away_settings_uses_compact_shell_and_larger_toolbar_targets(self):
        dialog = AwaySettingsDialog()
        self.addCleanup(dialog.close)
        _show_and_polish(dialog)

        self.assertTrue(dialog.isSizeGripEnabled())
        self.assertLessEqual(dialog.width(), 900)
        available = dialog.screen().availableGeometry()
        self.assertLessEqual(dialog.height(), max(280, available.height() - 56))
        self.assertLessEqual(dialog.height(), 720)
        self.assertEqual(dialog.section_tabs.count(), 2)
        self.assertTrue(dialog.section_tabs.accessibleName())
        self.assertTrue(dialog.message_scroll.widgetResizable())
        self.assertTrue(dialog.options_scroll.widgetResizable())
        self.assertIs(dialog.content_scroll, dialog.message_scroll)
        self.assertNotEqual(
            dialog.section_tabs.tabText(0),
            dialog.section_tabs.tabText(1),
        )
        tool_buttons = [
            button
            for button in dialog.findChildren(QToolButton)
            if button.property("awayToolbarAction")
        ]
        self.assertTrue(tool_buttons)
        self.assertTrue(all(button.width() >= 36 for button in tool_buttons))
        self.assertTrue(all(button.accessibleName() for button in tool_buttons))
        save_button = dialog.findChild(QPushButton, "primary_btn")
        cancel_button = dialog.findChild(QPushButton, "ghost_btn")
        self.assertIsNotNone(save_button)
        self.assertIsNotNone(cancel_button)
        self.assertTrue(save_button.isDefault())
        self.assertFalse(cancel_button.autoDefault())
        dialog.section_tabs.setCurrentIndex(1)
        QApplication.processEvents()
        self.assertTrue(save_button.isVisible())

    def test_gcal_navigation_and_calendar_actions_expose_state_and_targets(self):
        parent = _SettingsParent("GCalDialogUsability")
        dialog = GCalSettingsDialog(parent=parent)
        self.addCleanup(dialog.close)
        self.addCleanup(parent.close)
        _show_and_polish(dialog)

        self.assertEqual(dialog.accessibleName(), dialog.windowTitle())
        self.assertTrue(dialog.isSizeGripEnabled())
        self.assertLessEqual(dialog.width(), 980)
        self.assertLessEqual(dialog.height(), 680)
        self.assertTrue(dialog._nav_btns)
        self.assertTrue(all(button.isCheckable() for button in dialog._nav_btns))
        self.assertEqual(sum(button.isChecked() for button in dialog._nav_btns), 1)
        self.assertTrue(all(button.accessibleName() for button in dialog._nav_btns))

        row = dialog._make_calendar_row_widget(
            {
                "id": 1,
                "name": "업무",
                "type": "local",
                "color": "#4da6ff",
                "is_visible": 1,
                "is_default": 0,
            }
        )
        self.addCleanup(row.close)
        action_names = (
            "calendarDefaultButton",
            "calendarVisibilityButton",
            "calendarEditButton",
            "calendarDeleteButton",
        )
        for object_name in action_names:
            button = row.findChild(QPushButton, object_name)
            self.assertIsNotNone(button)
            self.assertGreaterEqual(button.width(), 40)
            self.assertGreaterEqual(button.height(), 40)
            self.assertTrue(button.accessibleName())

    def test_checklist_subdialogs_share_footer_and_field_accessibility(self):
        item_dialog = ChecklistItemEditDialog(template_id=1)
        bulk_dialog = BulkOperationsDialog(template_id=1)
        self.addCleanup(item_dialog.close)
        self.addCleanup(bulk_dialog.close)
        _show_and_polish(item_dialog)
        _show_and_polish(bulk_dialog)

        self.assertTrue(item_dialog.property("_dc_common_style_applied"))
        self.assertTrue(item_dialog.isSizeGripEnabled())
        self.assertTrue(item_dialog.text_edit.accessibleName())
        self.assertTrue(item_dialog.desc_edit.accessibleName())
        self.assertTrue(item_dialog.guide_edit.accessibleName())
        self.assertTrue(bulk_dialog.property("_dc_common_style_applied"))
        self.assertTrue(bulk_dialog.prefix_edit.accessibleName())

        for dialog in (item_dialog, bulk_dialog):
            primary = dialog.findChild(QPushButton, "primary_btn")
            cancel = dialog.findChild(QPushButton, "ghost_btn")
            self.assertIsNotNone(primary)
            self.assertIsNotNone(cancel)
            self.assertTrue(primary.isDefault())
            self.assertFalse(cancel.autoDefault())
            self.assertGreaterEqual(primary.height(), 44)
            self.assertGreaterEqual(cancel.height(), 44)


if __name__ == "__main__":
    unittest.main()
