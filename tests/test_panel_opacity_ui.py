# -*- coding: utf-8 -*-
import os
import re
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication, QDialog, QFrame, QLabel, QPushButton, QScrollArea

from calendar_app.presentation.dialogs.panel_color_picker_dialog import (
    _POINT_COLORS,
    PanelColorPickerDialog,
)
from calendar_app.presentation.panels.side_panel_renderer import (
    _panel_surface_style,
    _panel_toolbar_style,
)
from calendar_app.shared.theme_settings import opacity_percent_label

_RGBA_ALPHA_RE = re.compile(
    r"background-color:\s*rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*(\d+)\s*\)"
)


class PanelOpacityUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PyQt6.QtCore import QSettings

        from calendar_app.infrastructure.i18n import I18nManager

        settings = QSettings("kimhyojin", "Dark Calendar")
        self._orig_lang = settings.value("language")
        settings.setValue("language", "ko")
        I18nManager()._load_translations()

    def tearDown(self):
        from PyQt6.QtCore import QSettings

        from calendar_app.infrastructure.i18n import I18nManager

        settings = QSettings("kimhyojin", "Dark Calendar")
        if self._orig_lang is not None:
            settings.setValue("language", self._orig_lang)
        else:
            settings.remove("language")
        I18nManager()._load_translations()

    def test_panel_toolbar_uses_same_alpha_as_panel_surface(self):
        surface_style = _panel_surface_style()
        toolbar_style = _panel_toolbar_style()

        surface_match = _RGBA_ALPHA_RE.search(surface_style)
        toolbar_match = _RGBA_ALPHA_RE.search(toolbar_style)

        self.assertIsNotNone(surface_match)
        self.assertIsNotNone(toolbar_match)
        self.assertEqual(surface_match.group(1), toolbar_match.group(1))

    def test_theme_dialog_opacity_labels_use_percent_text(self):
        dialog = PanelColorPickerDialog(
            current_opacity=51,
            current_border_opacity=128,
            current_text_opacity=255,
        )
        self.addCleanup(dialog.close)

        self.assertEqual(dialog._op_lbl.text(), opacity_percent_label(51))
        self.assertEqual(dialog._bd_op_lbl.text(), opacity_percent_label(128))
        self.assertEqual(dialog._txt_op_lbl.text(), opacity_percent_label(255))

        dialog._slider.setValue(102)
        dialog._border_slider.setValue(64)
        dialog._text_slider.setValue(153)

        self.assertEqual(dialog._op_lbl.text(), opacity_percent_label(102))
        self.assertEqual(dialog._bd_op_lbl.text(), opacity_percent_label(64))
        self.assertEqual(dialog._txt_op_lbl.text(), opacity_percent_label(153))

    def test_theme_dialog_uses_single_settings_flow_with_persistent_preview(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)

        settings_scroll = dialog.findChild(QScrollArea, "appearanceSettingsScroll")
        self.assertIsNotNone(settings_scroll)
        self.assertFalse(settings_scroll.isAncestorOf(dialog._preview_frame))
        sections = [
            dialog.findChild(QFrame, f"appearanceSection_{section_id}")
            for section_id in ("style", "accent", "readability", "font")
        ]
        self.assertTrue(all(section is not None for section in sections))
        self.assertEqual(
            [
                section.findChild(QPushButton, "appearanceSectionToggle").accessibleName()
                for section in sections
            ],
            ["스타일", "포인트 색상", "가독성", "글꼴"],
        )
        self.assertLessEqual(dialog.height(), dialog.screen().availableGeometry().height() - 48)

        font_popup_btn = dialog.findChild(QPushButton, "fontComboPopupButton")
        self.assertIsNotNone(font_popup_btn)
        self.assertFalse(font_popup_btn.icon().isNull())
        self.assertTrue(font_popup_btn.accessibleName())

        self.assertEqual(dialog.windowTitle(), "모양 설정")

        self.assertTrue(dialog._preset_grid_widget.isHidden())
        self.assertTrue(all(button.isHidden() for button in dialog._preset_filter_btns.values()))
        self.assertEqual(len(dialog._family_btns), 8)
        self.assertTrue(all(not button.isHidden() for button in dialog._family_btns.values()))

        dialog._style_details_toggle.click()
        dialog._show_all_styles.setChecked(True)
        self.assertFalse(dialog._preset_grid_widget.isHidden())
        self.assertTrue(
            all(not button.isHidden() for button in dialog._preset_filter_btns.values())
        )

    def test_quick_settings_progressively_disclose_detailed_controls(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)

        self.assertFalse(dialog._section_contents["style"].isHidden())
        self.assertFalse(dialog._section_contents["accent"].isHidden())
        self.assertTrue(dialog._section_contents["readability"].isHidden())
        self.assertTrue(dialog._section_contents["font"].isHidden())
        self.assertTrue(dialog._style_details_content.isHidden())
        self.assertEqual(dialog._style_details_toggle.accessibleName(), "배경 세부 설정")
        self.assertTrue(dialog._style_details_toggle.text().startswith("▸"))

        dialog._style_details_toggle.click()
        self.assertFalse(dialog._style_details_content.isHidden())
        self.assertTrue(dialog._style_details_toggle.text().startswith("▾"))

        dialog._section_toggles["readability"].click()
        self.assertFalse(dialog._section_contents["readability"].isHidden())
        self.assertTrue(dialog._section_toggles["readability"].text().startswith("▾"))

    def test_theme_dialog_initial_focus_starts_at_top_mode_control(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)
        dialog.show()
        self._app.processEvents()

        self.assertEqual(dialog._settings_scroll.verticalScrollBar().value(), 0)
        self.assertIs(QApplication.focusWidget(), dialog._appearance_mode_btns["dark"])

    def test_style_family_switches_to_matching_light_variant(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)

        dialog._set_appearance_mode("light")
        dialog._select_style_family("ocean")

        self.assertEqual(dialog.selected_base_hex(), "#e7f5ff")
        self.assertEqual(dialog.selected_point_hex(), "#1971c2")
        self.assertEqual(dialog.selected_text_theme(), "light")

    def test_mode_controls_expose_system_light_and_dark(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)

        self.assertEqual(set(dialog._appearance_mode_btns), {"auto", "light", "dark"})
        self.assertTrue(dialog._appearance_mode_btns["dark"].isChecked())
        self.assertFalse(dialog._apply_btn.isEnabled())
        self.assertEqual(dialog._change_summary_label.text(), "변경사항 없음")

        with patch.object(dialog, "_system_mode_variant", return_value="light"):
            dialog._set_appearance_mode("auto")

        self.assertTrue(dialog._appearance_mode_btns["auto"].isChecked())
        self.assertEqual(dialog.selected_text_theme(), "auto")
        self.assertTrue(dialog._apply_btn.isEnabled())

    def test_apply_is_enabled_only_while_appearance_has_changes(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)
        original = dialog._slider.value()
        changed = original - 1 if original > 0 else original + 1

        dialog._slider.setValue(changed)
        self.assertTrue(dialog._apply_btn.isEnabled())
        self.assertIn("1", dialog._change_summary_label.text())

        dialog._slider.setValue(original)
        self.assertFalse(dialog._apply_btn.isEnabled())
        self.assertEqual(dialog._change_summary_label.text(), "변경사항 없음")

    def test_section_revert_preserves_changes_in_other_sections(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)
        original_point = dialog.selected_point_hex()
        original_opacity = dialog._slider.value()
        point_index = next(
            index
            for index, (_, _, code) in enumerate(_POINT_COLORS)
            if code.lower() != original_point.lower()
        )

        dialog._select_point_color(point_index)
        dialog._slider.setValue(original_opacity - 1)
        self.assertTrue(dialog._section_reset_buttons["accent"].isEnabled())
        self.assertTrue(dialog._section_reset_buttons["style"].isEnabled())
        self.assertEqual(
            dialog._section_reset_buttons["accent"].accessibleName(),
            "포인트 색상 변경 되돌리기",
        )
        self.assertFalse(dialog._section_reset_buttons["accent"].icon().isNull())

        dialog._section_reset_buttons["accent"].click()

        self.assertEqual(dialog.selected_point_hex(), original_point)
        self.assertEqual(dialog._slider.value(), original_opacity - 1)
        self.assertFalse(dialog._section_reset_buttons["accent"].isEnabled())
        self.assertTrue(dialog._section_reset_buttons["style"].isEnabled())
        self.assertTrue(dialog._apply_btn.isEnabled())

        dialog._section_reset_buttons["style"].click()
        self.assertEqual(dialog._slider.value(), original_opacity)
        self.assertFalse(dialog._apply_btn.isEnabled())

    def test_revert_all_restores_opening_snapshot_in_one_preview_update(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)
        initial = dialog._appearance_state()

        dialog._set_appearance_mode("light")
        dialog._slider.setValue(dialog._slider.value() - 1)
        dialog._font_size_spin.setValue(dialog._font_size_spin.value() + 1)
        dialog._dialog_color_overrides = {
            **dialog._dialog_color_overrides,
            "accent": "#123456",
        }
        dialog._update_change_summary()
        self.assertTrue(dialog._revert_all_btn.isEnabled())
        before_revert = dialog._preview_apply_count

        dialog._revert_all_btn.click()

        self.assertEqual(dialog._appearance_state(), initial)
        self.assertEqual(dialog._preview_apply_count, before_revert + 1)
        self.assertFalse(dialog._revert_all_btn.isEnabled())
        self.assertFalse(dialog._apply_btn.isEnabled())
        self.assertTrue(
            all(not button.isEnabled() for button in dialog._section_reset_buttons.values())
        )

    def test_readability_and_font_revert_restore_only_their_controls(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)
        original_primary = dialog._row_primary.hex_value()
        original_font_size = dialog._font_size_spin.value()

        dialog._row_primary.set_value("#010203")
        dialog._font_size_spin.setValue(original_font_size + 1)
        self.assertTrue(dialog._section_reset_buttons["readability"].isEnabled())
        self.assertTrue(dialog._section_reset_buttons["font"].isEnabled())

        dialog._section_reset_buttons["readability"].click()
        self.assertEqual(dialog._row_primary.hex_value(), original_primary)
        self.assertEqual(dialog._font_size_spin.value(), original_font_size + 1)
        self.assertFalse(dialog._section_reset_buttons["readability"].isEnabled())
        self.assertTrue(dialog._section_reset_buttons["font"].isEnabled())

        dialog._section_reset_buttons["font"].click()
        self.assertEqual(dialog._font_size_spin.value(), original_font_size)
        self.assertFalse(dialog._apply_btn.isEnabled())

    def test_family_selection_uses_checkmark_and_arrow_key_navigation(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)
        dialog.show()
        self._app.processEvents()

        dialog._set_appearance_mode("light")
        dialog._select_style_family("ocean")
        selected = dialog._family_btns["ocean"]
        self.assertTrue(selected.text().startswith("✓ "))
        self.assertEqual(selected.accessibleName(), selected.text())

        first = list(dialog._family_btns.values())[0]
        navigation = QSignalSpy(first.navigate_requested)
        QTest.keyClick(first, Qt.Key.Key_Right)
        self.assertEqual(len(navigation), 1)
        self.assertEqual(navigation[0][0], 1)

        QTest.keyClick(first, Qt.Key.Key_Down)
        self.assertEqual(len(navigation), 2)
        self.assertEqual(navigation[1][0], first.property("navigation_columns"))

    def test_low_contrast_text_can_be_fixed_automatically(self):
        dialog = PanelColorPickerDialog(current_base="#777777")
        self.addCleanup(dialog.close)

        dialog._row_primary.set_value("#777777")
        dialog._row_secondary.set_value("#777777")
        self.assertTrue(dialog._contrast_fix_btn.isEnabled())

        dialog._auto_fix_text_contrast()

        self.assertFalse(dialog._contrast_fix_btn.isEnabled())
        self.assertIn("4.", dialog._contrast_status.text())

    def test_advanced_editor_returns_staged_overrides_to_parent_dialog(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)

        class FakeTokenEditor:
            def __init__(self, _parent, **kwargs):
                self.kwargs = kwargs

            def exec(self):
                return QDialog.DialogCode.Accepted

            def selected_color_overrides(self):
                return {"accent": "#112233"}

            def selected_metric_overrides(self):
                return {"button_height": 31}

        with patch(
            "calendar_app.presentation.dialogs.dialog_token_editor_dialog.DialogTokenEditorDialog",
            FakeTokenEditor,
        ):
            dialog._open_token_editor()

        self.assertEqual(dialog.selected_dialog_color_overrides(), {"accent": "#112233"})
        self.assertEqual(dialog.selected_dialog_metric_overrides(), {"button_height": 31})

    def test_cancelled_advanced_editor_preserves_existing_draft(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)
        dialog._dialog_color_overrides = {"accent": "#445566"}
        dialog._dialog_metric_overrides = {"button_height": 33}

        class RejectedTokenEditor:
            def __init__(self, _parent, **_kwargs):
                pass

            def exec(self):
                return QDialog.DialogCode.Rejected

            def selected_color_overrides(self):
                return {"accent": "#112233"}

            def selected_metric_overrides(self):
                return {"button_height": 31}

        with patch(
            "calendar_app.presentation.dialogs.dialog_token_editor_dialog.DialogTokenEditorDialog",
            RejectedTokenEditor,
        ):
            dialog._open_token_editor()

        self.assertEqual(dialog.selected_dialog_color_overrides(), {"accent": "#445566"})
        self.assertEqual(dialog.selected_dialog_metric_overrides(), {"button_height": 33})

    def test_theme_dialog_preserves_fully_transparent_background(self):
        dialog = PanelColorPickerDialog(current_opacity=0)
        self.addCleanup(dialog.close)

        self.assertEqual(dialog._slider.value(), 0)
        self.assertEqual(dialog.selected_opacity(), 0)
        labels = [label.text() for label in dialog.findChildren(QLabel)]
        self.assertIn("0% = 완전 투명, 100% = 완전 불투명", labels)

    def test_border_and_text_opacity_update_preview_immediately(self):
        dialog = PanelColorPickerDialog(
            current_opacity=255,
            current_border_opacity=255,
            current_text_opacity=255,
            current_text_primary="#ffffff",
            current_text_secondary="#cccccc",
            current_text_muted="#999999",
        )
        self.addCleanup(dialog.close)

        dialog._border_slider.setValue(0)
        dialog._flush_preview_refresh()
        self.assertIn("border: 1px solid rgba(255,255,255,0.0)", dialog._preview_frame.styleSheet())

        dialog._text_slider.setValue(0)
        dialog._flush_preview_refresh()
        stylesheet = dialog._preview_frame.styleSheet()
        self.assertIn("QLabel#previewItemText1 { color: rgba(255, 255, 255, 0);", stylesheet)
        self.assertIn("QLabel#previewInputHint { color: rgba(153, 153, 153, 0);", stylesheet)

    def test_rapid_preview_changes_are_coalesced(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)
        baseline = dialog._preview_apply_count

        dialog._slider.setValue(180)
        dialog._slider.setValue(160)
        dialog._border_slider.setValue(90)
        dialog._text_slider.setValue(220)

        self.assertEqual(dialog._preview_apply_count, baseline)
        dialog._flush_preview_refresh()
        self.assertEqual(dialog._preview_apply_count, baseline + 1)

    def test_preset_applies_one_preview_update(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)
        baseline = dialog._preview_apply_count

        dialog._select_preset(1)

        self.assertEqual(dialog._preview_apply_count, baseline + 1)


if __name__ == "__main__":
    unittest.main()
