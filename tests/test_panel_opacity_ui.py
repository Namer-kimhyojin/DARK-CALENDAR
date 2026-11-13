# -*- coding: utf-8 -*-
import os
import re
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QFontDatabase
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication, QDialog, QFrame, QLabel, QPushButton, QScrollArea

from calendar_app.presentation.dialogs.panel_color_picker_dialog import (
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
            current_opacity=51, current_border_opacity=128, current_text_opacity=255
        )
        self.addCleanup(dialog.close)

        self.assertEqual(dialog._op_lbl.text(), opacity_percent_label(51))
        self.assertEqual(dialog._bd_op_lbl.text(), opacity_percent_label(128))
        self.assertEqual(dialog._txt_op_lbl.text(), opacity_percent_label(255))
        # Text opacity lives in Readability, not with the background sliders.
        self.assertTrue(dialog._section_contents["readability"].isAncestorOf(dialog._text_slider))
        self.assertFalse(dialog._section_contents["background"].isAncestorOf(dialog._text_slider))

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
            for section_id in ("style", "accent", "background", "readability", "font")
        ]
        self.assertTrue(all(section is not None for section in sections))
        self.assertEqual(
            [
                section.findChild(QPushButton, "appearanceSectionToggle").accessibleName()
                for section in sections
            ],
            ["화면 모드", "포인트 색상", "배경 및 투명도", "가독성", "글꼴"],
        )
        self.assertLessEqual(dialog.height(), dialog.screen().availableGeometry().height() - 48)

        font_popup_btn = dialog.findChild(QPushButton, "fontComboPopupButton")
        self.assertIsNone(font_popup_btn)
        dialog._section_toggles["font"].click()
        font_popup_btn = dialog.findChild(QPushButton, "fontComboPopupButton")
        self.assertIsNotNone(font_popup_btn)
        self.assertFalse(font_popup_btn.icon().isNull())
        self.assertTrue(font_popup_btn.accessibleName())

        self.assertEqual(dialog.windowTitle(), "모양 설정")

        # Mode, accent and background each live in one place: no style-card grid
        # beside a second accent palette, and no hidden "background details".
        for removed in (
            "_show_all_styles",
            "_preset_grid_widget",
            "_preset_filter_btns",
            "_preset_btns",
            "_point_btns",
            "_style_details_toggle",
            "_style_details_content",
        ):
            self.assertFalse(hasattr(dialog, removed), removed)
        self.assertEqual(set(dialog._appearance_mode_btns), {"auto", "light", "dark"})
        self.assertEqual(len(dialog._family_btns), 9)
        self.assertIn("navy_lilac", dialog._family_btns)
        self.assertTrue(all(not button.isHidden() for button in dialog._family_btns.values()))

        background = dialog._section_contents["background"]
        for control in (dialog._btn_auto_base, dialog._btn_custom, dialog._slider):
            self.assertTrue(background.isAncestorOf(control))
            self.assertFalse(control.isHidden())
        # The default draft's background is not a preset tone, so "custom" is shown.
        self.assertEqual(dialog._btn_custom.isChecked(), dialog._base_source == "custom")
        self.assertNotEqual(dialog._btn_auto_base.isChecked(), dialog._btn_custom.isChecked())
        dialog._select_style_family("ocean")
        self.assertTrue(dialog._btn_auto_base.isChecked())

    def test_preview_selected_day_is_readable_on_every_accent(self):
        """White text on a pale accent (e.g. #f1fa8c) made today's date invisible."""
        from PyQt6.QtGui import QColor

        from calendar_app.presentation.dialogs import panel_color_picker_dialog as module
        from calendar_app.shared.color_utils import contrast_ratio

        accents = [preset[3] for preset in module._PRESETS]
        for accent in accents + [
            "#f1fa8c",
            "#ffffff",
            "#000000",
        ]:
            for base in ("#121827", "#f8f1e7"):
                with self.subTest(accent=accent, base=base):
                    frame = module._build_preview_widget(base, accent, 1.0)
                    self.addCleanup(frame.deleteLater)
                    css = frame.styleSheet()
                    marker = 'QLabel#previewDay[selected="true"] {'
                    rule = css[css.index(marker) : css.index("}", css.index(marker))]
                    color = rule.split("color:")[-1].split(";")[0].strip()
                    self.assertTrue(QColor(color).isValid(), color)
                    self.assertGreaterEqual(contrast_ratio(color, accent), 4.5, (color, accent))

    def test_footer_has_a_single_separator_line(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)
        dialog.show()
        self._app.processEvents()

        footer = dialog.findChild(QFrame, "appearanceFooter")
        self.assertIsNotNone(footer)
        # The separator above the footer is the only rule; the footer must not add
        # its own border-top through the shared dialogFooter role.
        self.assertNotEqual(footer.property("role"), "dialogFooter")
        root = dialog.layout()
        index = root.indexOf(footer)
        previous = root.itemAt(index - 1).widget()
        self.assertEqual(previous.frameShape(), QFrame.Shape.HLine)
        two_back = root.itemAt(index - 2)
        self.assertTrue(
            two_back.widget() is None or two_back.widget().frameShape() != QFrame.Shape.HLine
        )

    def test_quick_settings_progressively_disclose_detailed_controls(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)

        for section_id in ("style", "accent", "background"):
            self.assertFalse(dialog._section_contents[section_id].isHidden(), section_id)
        self.assertTrue(dialog._section_contents["readability"].isHidden())
        self.assertTrue(dialog._section_contents["font"].isHidden())
        # Opacity is a first-level control now, not behind a details toggle.
        for slider in (dialog._slider, dialog._border_slider):
            self.assertFalse(slider.isHidden())

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
        self.assertEqual(dialog._row_primary.hex_value(), "#20283a")
        self.assertEqual(dialog._row_input_bg.hex_value(), "#ffffff")

    def test_style_family_cards_preview_only_the_current_mode_variant(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)

        ocean = dialog._family_btns["ocean"]
        self.assertEqual(ocean.objectName(), "appearanceFamilySwatch")
        self.assertEqual(ocean.text(), "")
        self.assertIn("블루", ocean.accessibleName())
        self.assertIn("네이비", ocean.accessibleName())
        self.assertEqual(ocean.property("variant_label"), "네이비")
        self.assertIn("#4da6ff", ocean.toolTip())

        dialog._set_appearance_mode("light")

        self.assertIn("블루", ocean.accessibleName())
        self.assertIn("파스텔 스카이", ocean.accessibleName())
        self.assertEqual(ocean.property("variant_label"), "파스텔 스카이")
        self.assertIn("#1971c2", ocean.toolTip())

    def test_accent_readout_follows_the_preset_variant_when_the_mode_changes(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)
        dialog._select_style_family("ocean")
        self.assertEqual(dialog._point_hex_lbl.text(), "#4da6ff")

        dialog._set_appearance_mode("light")

        self.assertEqual(dialog.selected_point_hex(), "#1971c2")
        self.assertEqual(dialog._point_hex_lbl.text(), "#1971c2")
        self.assertTrue(dialog._family_btns["ocean"].isChecked())

        dialog._apply_custom_point_color("#123456")
        self.assertTrue(dialog._point_custom_btn.isChecked())
        self.assertFalse(any(button.isChecked() for button in dialog._family_btns.values()))
        self.assertEqual(dialog._point_hex_lbl.text(), "#123456")

    def test_appearance_bounds_and_family_cards_preserve_visible_content(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)
        dialog.show()
        for _ in range(3):
            self._app.processEvents()
        preferred = dialog.property("_dc_preferred_size")
        self.assertIsNotNone(preferred)
        self.assertLessEqual(preferred.width(), 960)
        self.assertLessEqual(preferred.height(), 740)
        self.assertLessEqual(dialog.height(), 740)
        self.assertEqual(len(dialog._family_btns), 9)
        heights = {button.height() for button in dialog._family_btns.values()}
        self.assertEqual(len(heights), 1)
        self.assertLess(next(iter(heights)), 72)
        self.assertTrue(
            all(
                button.height() >= button.iconSize().height() + 16
                for button in dialog._family_btns.values()
            )
        )
        self.assertFalse(dialog._settings_scroll.viewport().autoFillBackground())

    def test_appearance_reflows_without_rebuilding_or_discarding_draft(self):
        with patch(
            "calendar_app.presentation.dialogs.dialog_styles._available_dialog_bounds",
            return_value=(1400, 1000),
        ):
            dialog = PanelColorPickerDialog()
            self.addCleanup(dialog.close)
            dialog.show()
            for _ in range(3):
                self._app.processEvents()
            dialog._select_style_family("ocean")
            dialog._slider.setValue(153)
            original_buttons = list(dialog._family_btns.values())
            original_preview = dialog._preview_frame
            draft = (dialog.selected_base_hex(), dialog.selected_point_hex(), dialog._opacity)
            for width, wide in ((960, True), (700, False), (960, True)):
                with self.subTest(width=width, wide=wide):
                    dialog.resize(width, 740)
                    for _ in range(3):
                        self._app.processEvents()
                    self.assertEqual(dialog._wide_appearance_layout, wide)
                    viewport = dialog._settings_scroll.viewport().width()
                    columns = min(9, max(1, (viewport - 54 + 8) // 52))
                    self.assertEqual(dialog._point_columns, columns)
                    self.assertEqual(list(dialog._family_btns.values()), original_buttons)
                    self.assertIs(dialog._preview_frame, original_preview)
                    self.assertEqual(
                        (dialog.selected_base_hex(), dialog.selected_point_hex(), dialog._opacity),
                        draft,
                    )
                    if not wide:
                        self.assertLess(
                            dialog._preview_panel.geometry().bottom(),
                            dialog._settings_scroll.geometry().top(),
                        )

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

    def test_preview_identifies_current_selection_and_compares_applied_appearance(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)

        self.assertIn("현재 선택:", dialog._preview_selection_label.text())
        self.assertFalse(dialog._preview_compare_btn.isEnabled())
        initial_preview = dialog._preview_frame.styleSheet()

        dialog._slider.setValue(dialog._slider.value() - 1)
        dialog._flush_preview_refresh()
        changed_preview = dialog._preview_frame.styleSheet()

        self.assertNotEqual(changed_preview, initial_preview)
        self.assertIn("배경 및 투명도", dialog._change_summary_label.toolTip())
        self.assertTrue(dialog._preview_compare_btn.isEnabled())

        dialog._preview_compare_btn.click()

        self.assertTrue(dialog._preview_compare_btn.isChecked())
        self.assertEqual(dialog._preview_compare_btn.text(), "변경 후 보기")
        self.assertEqual(dialog._preview_frame.styleSheet(), initial_preview)

        dialog._preview_compare_btn.click()

        self.assertFalse(dialog._preview_compare_btn.isChecked())
        self.assertEqual(dialog._preview_compare_btn.text(), "현재 적용값 보기")
        self.assertEqual(dialog._preview_frame.styleSheet(), changed_preview)

    def test_section_revert_preserves_changes_in_other_sections(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)
        original_point = dialog.selected_point_hex()
        original_opacity = dialog._slider.value()
        custom_accent = "#e74c3c" if original_point.lower() != "#e74c3c" else "#29b6f6"

        dialog._apply_custom_point_color(custom_accent)
        dialog._slider.setValue(original_opacity - 1)
        self.assertTrue(dialog._section_reset_buttons["accent"].isEnabled())
        self.assertTrue(dialog._section_reset_buttons["background"].isEnabled())
        self.assertFalse(dialog._section_reset_buttons["style"].isEnabled())
        self.assertEqual(
            dialog._section_reset_buttons["accent"].accessibleName(),
            "포인트 색상 변경 되돌리기",
        )
        self.assertFalse(dialog._section_reset_buttons["accent"].icon().isNull())

        dialog._section_reset_buttons["accent"].click()

        self.assertEqual(dialog.selected_point_hex(), original_point)
        self.assertEqual(dialog._slider.value(), original_opacity - 1)
        self.assertFalse(dialog._section_reset_buttons["accent"].isEnabled())
        self.assertTrue(dialog._section_reset_buttons["background"].isEnabled())
        self.assertTrue(dialog._apply_btn.isEnabled())

        dialog._section_reset_buttons["background"].click()
        self.assertEqual(dialog._slider.value(), original_opacity)
        self.assertFalse(dialog._apply_btn.isEnabled())

    def test_revert_all_restores_opening_snapshot_in_one_preview_update(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)
        initial = dialog._appearance_state()

        dialog._set_appearance_mode("light")
        dialog._slider.setValue(dialog._slider.value() - 1)
        dialog._section_toggles["font"].click()
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
        dialog._section_toggles["font"].click()
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

    def test_font_preview_renders_selected_family_size_and_restores_opening_font(self):
        families = QFontDatabase.families()
        self.assertTrue(families)
        first_family = "Courier New" if "Courier New" in families else families[0]
        other_family = "Times New Roman" if "Times New Roman" in families else families[-1]
        dialog = PanelColorPickerDialog(current_font_family=first_family, current_font_size=10)
        self.addCleanup(dialog.close)
        dialog._section_toggles["font"].click()
        dialog.show()
        QApplication.processEvents()

        for family, size in ((first_family, 24), (other_family, 18)):
            with self.subTest(family=family, size=size):
                dialog._font_combo.setCurrentFont(QFont(family))
                dialog._font_size_spin.setValue(size)
                QApplication.processEvents()
                self.assertEqual(dialog._font_preview.font().family(), family)
                self.assertAlmostEqual(dialog._font_preview.font().pointSizeF(), size)
                self.assertGreaterEqual(
                    dialog._font_preview.height(), dialog._font_preview.fontMetrics().height() + 22
                )

        dialog._section_reset_buttons["font"].click()
        QApplication.processEvents()
        self.assertEqual(dialog._font_preview.font().family(), first_family)
        self.assertAlmostEqual(dialog._font_preview.font().pointSizeF(), 10)

    def test_family_selection_uses_checkmark_and_arrow_key_navigation(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)
        dialog.show()
        self._app.processEvents()

        dialog._set_appearance_mode("light")
        dialog._select_style_family("ocean")
        selected = dialog._family_btns["ocean"]
        self.assertTrue(selected.isChecked())
        self.assertTrue(selected.accessibleName().startswith("✓ 블루"))
        self.assertIn(selected.property("variant_label"), selected.accessibleName())
        self.assertFalse(dialog._point_custom_btn.isChecked())

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

    def test_border_opacity_updates_preview_and_text_stays_opaque(self):
        dialog = PanelColorPickerDialog(
            current_opacity=255,
            current_border_opacity=255,
            current_text_primary="#ffffff",
            current_text_secondary="#cccccc",
            current_text_muted="#999999",
        )
        self.addCleanup(dialog.close)

        border = QColor(dialog._current_border_hex())
        dialog._border_slider.setValue(0)
        dialog._flush_preview_refresh()
        stylesheet = dialog._preview_frame.styleSheet()
        self.assertIn(
            f"border: 1px solid rgba({border.red()}, {border.green()}, {border.blue()}, 0)",
            stylesheet,
        )
        self.assertIn("QLabel#previewItemText1 { color: rgba(255, 255, 255, 255);", stylesheet)

    def test_rapid_preview_changes_are_coalesced(self):
        dialog = PanelColorPickerDialog()
        self.addCleanup(dialog.close)
        baseline = dialog._preview_apply_count

        dialog._slider.setValue(180)
        dialog._slider.setValue(160)
        dialog._border_slider.setValue(90)

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
