# -*- coding: utf-8 -*-
"""Cross-dialog styling contracts and floating task action lifecycle regressions."""

import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton, QVBoxLayout, QWidget

from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_stylesheet,
    get_dialog_theme_tokens,
    install_common_dialog_style_filter,
)
from calendar_app.presentation.widgets.ui_components import DraggableTaskButton
from calendar_app.shared.color_utils import contrast_ratio
from calendar_app.shared.color_utils import contrasting_text_color as _accent_text


class DialogVisualSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        install_common_dialog_style_filter(cls.app)

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = QSettings(str(Path(self.temp.name) / "visual.ini"), QSettings.Format.IniFormat)
        self.settings.setValue("theme_color", "#c5a3f5")
        self.settings.setValue("panel_base_color", "#121827")
        self.settings.setValue("text_theme", "dark")

    def test_explicit_profile_controls_color_and_metric_overrides(self):
        self.settings.setValue("dialog_token.button_primary_bg", "#f0a540")
        self.settings.setValue("dialog_token.metric.button_radius", 15)
        tokens = get_dialog_theme_tokens(settings=self.settings)
        stylesheet = build_dialog_stylesheet(settings=self.settings)
        self.assertEqual(tokens["button_primary_bg"], "#f0a540")
        self.assertGreaterEqual(contrast_ratio(tokens["button_primary_text"], "#f0a540"), 4.5)
        self.assertIn("border-radius: 15px;", stylesheet)
        self.assertIn("background-color: #f0a540;", stylesheet)
        self.assertIn("DC_DIALOG_VISUAL_SYSTEM", stylesheet)

    def test_shared_primary_is_readable_in_dark_light_and_custom_palettes(self):
        for mode, base, accent in (
            ("dark", "#121827", "#c5a3f5"),
            ("light", "#f3f1fa", "#7950b8"),
            ("custom", "#103d42", "#f5aa51"),
        ):
            with self.subTest(mode=mode):
                tokens = get_dialog_theme_tokens(
                    accent, mode, base, apply_overrides=False, settings=self.settings
                )
                self.assertEqual(tokens["button_primary_bg"], tokens["accent"])
                self.assertGreaterEqual(
                    contrast_ratio(tokens["button_primary_text"], tokens["button_primary_bg"]), 4.5
                )

    def test_partial_accent_bundle_updates_primary_derived_roles(self):
        self.settings.setValue("theme_color", "#245588")
        stylesheet = build_dialog_stylesheet(settings=self.settings, tokens={"accent": "#f1cc55"})
        primary = re.findall(r"QPushButton#primary_btn\s*\{([^}]+)\}", stylesheet)[-1]
        self.assertIn("background-color: #f1cc55;", primary)
        self.assertIn(f"color: {_accent_text('#f1cc55')};", primary)

    def test_common_style_inherits_nearest_owner_profile(self):
        owner = QWidget()
        owner.settings = self.settings
        self.addCleanup(owner.close)
        middle = QWidget(owner)
        dialog = QDialog(middle)
        self.addCleanup(dialog.close)
        self.settings.setValue("dialog_token.metric.field_radius", 14)
        apply_common_dialog_style(dialog)
        self.assertIn("#c5a3f5", dialog.styleSheet())
        self.assertIn("border-radius: 14px;", dialog.styleSheet())

    def test_custom_dialog_keeps_skin_and_receives_base_only_once(self):
        dialog = QDialog()
        self.addCleanup(dialog.close)
        skin = "QDialog#LocalSkin { padding: 3px; }"
        dialog.setObjectName("LocalSkin")
        dialog.setStyleSheet(skin)
        dialog.show()
        self.app.processEvents()
        dialog.hide()
        dialog.show()
        self.app.processEvents()
        self.assertIn(skin, dialog.styleSheet())
        self.assertEqual(dialog.styleSheet().count("/* DC_DIALOG_BASE */"), 1)

    def test_translucent_popup_retains_outer_transparency_and_window_opacity(self):
        dialog = QDialog()
        self.addCleanup(dialog.close)
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dialog.setWindowOpacity(0.62)
        dialog.show()
        self.app.processEvents()
        self.assertTrue(dialog.property("_dc_common_style_applied"))
        self.assertTrue(dialog.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        self.assertIn('QDialog[dcCommonTranslucent="true"]', dialog.styleSheet())
        self.assertAlmostEqual(dialog.windowOpacity(), 0.62, delta=0.01)

    def test_standard_message_roles_preserve_safe_default_and_shared_actions(self):
        dialog = QMessageBox()
        self.addCleanup(dialog.close)
        dialog.setText("변경 내용을 저장할까요?")
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
        )
        dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)
        dialog.show()
        self.app.processEvents()
        self.assertEqual(dialog.button(QMessageBox.StandardButton.Save).objectName(), "primary_btn")
        self.assertEqual(dialog.button(QMessageBox.StandardButton.Discard).objectName(), "danger_btn")
        self.assertEqual(dialog.button(QMessageBox.StandardButton.Cancel).objectName(), "ghost_btn")
        self.assertIs(dialog.defaultButton(), dialog.button(QMessageBox.StandardButton.Cancel))
        self.assertTrue(all(button.property("dialogFooter") for button in dialog.buttons()))

    def test_explicitly_styled_message_also_receives_standard_action_roles_once(self):
        dialog = QMessageBox()
        self.addCleanup(dialog.close)
        dialog.setText("배치를 저장할까요?")
        dialog.setStandardButtons(QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel)
        apply_common_dialog_style(dialog, settings=self.settings)
        dialog.show()
        self.app.processEvents()
        self.assertEqual(dialog.button(QMessageBox.StandardButton.Save).objectName(), "primary_btn")
        self.assertTrue(all(button.property("dialogFooter") for button in dialog.buttons()))
        stylesheet = dialog.styleSheet()
        dialog.hide()
        dialog.show()
        self.app.processEvents()
        self.assertEqual(dialog.styleSheet(), stylesheet)


class TaskDetailActionLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_repeated_rebuilds_reuse_exactly_two_buttons_without_deferred_deletes(self):
        button = DraggableTaskButton(123, "업무자동화 교육")
        self.addCleanup(button.close)
        button._render_detail_actions({"status": "pending"})
        original = button.actions_widget.findChildren(QPushButton)
        for index in range(30):
            button._render_detail_actions({"status": "completed" if index % 2 else "pending"})
            self.assertEqual(button.actions_layout.count(), 2)
            self.assertEqual(button.actions_widget.findChildren(QPushButton), original)

    def test_status_click_uses_latest_state_once_after_rebuild(self):
        button = DraggableTaskButton(123, "교육")
        self.addCleanup(button.close)
        changes = []
        button.taskStatusChanged.connect(lambda task_id, status: changes.append((task_id, status)))
        for _ in range(10):
            button._render_detail_actions({"status": "pending"})
        button._detail_status_button.click()
        button._render_detail_actions({"status": "done"})
        button._detail_status_button.click()
        self.assertEqual(changes, [(123, "completed"), (123, "pending")])

    def test_repeated_expansion_and_owner_switch_keep_one_visible_action_row(self):
        from calendar_app.presentation.widgets.ui_components import get_detail_overlay

        host = QWidget()
        layout = QVBoxLayout(host)
        buttons = [DraggableTaskButton(201, "교육"), DraggableTaskButton(202, "회의")]
        for button in buttons:
            layout.addWidget(button)
        host.show()
        self.app.processEvents()
        overlay = get_detail_overlay()
        self.addCleanup(host.close)
        self.addCleanup(overlay._do_collapse)
        task = {"name": "교육", "deadline": "2026-11-05 10:00:00", "status": "pending"}
        show_counts = []
        original_show = overlay.show

        def show_populated_card():
            show_counts.append(overlay._owner.actions_layout.count())
            original_show()

        with (
            patch("calendar_app.presentation.widgets.ui_components.task_repo.get_unified_task", return_value=task),
            patch("calendar_app.presentation.widgets.ui_components.checklist_repo.get_task_checklist_items", return_value=[]),
            patch.object(overlay, "show", side_effect=show_populated_card),
        ):
            for button in buttons * 6:
                button._animate_detail(True)
                self.app.processEvents()
                button._fade_anim.setCurrentTime(button._fade_anim.duration())
                self.app.processEvents()
                self.assertEqual(len(button.actions_widget.findChildren(QPushButton)), 2)
                self.assertTrue(all(child.isVisible() for child in button.actions_widget.findChildren(QPushButton)))
                overlay._do_collapse(button)
        self.assertEqual(show_counts, [2] * 12)


if __name__ == "__main__":
    unittest.main()
