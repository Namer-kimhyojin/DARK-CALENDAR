# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QSignalSpy
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

from calendar_app.presentation.widgets.alarm_popup import (
    AlarmPopupWindow,
    _alarm_popup_style_bundle,
    _build_alarm_popup_stylesheet,
)
from calendar_app.shared.color_utils import contrast_ratio, contrasting_text_color


class AlarmPopupStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_narrow_alarm_actions_keep_signal_and_timer_contracts(self):
        for action_name, signal_name in (("ConfirmBtn", "confirmed"), ("DoneBtn", "completed")):
            with (
                self.subTest(action=action_name),
                patch.object(AlarmPopupWindow, "_play_notification_sound"),
                patch(
                    "calendar_app.presentation.widgets.alarm_popup._popup_width", return_value=320
                ),
            ):
                popup = AlarmPopupWindow(
                    {"id": 17, "name": "Meeting and preparation details", "location": "Office"},
                    datetime.now() + timedelta(minutes=30),
                )
                popup.show()
                self._app.processEvents()
                for button in popup.findChildren(QPushButton):
                    bounds = QRect(button.mapTo(popup, QPoint()), button.size())
                    self.assertTrue(popup.rect().contains(bounds), button.objectName())
                spy = QSignalSpy(getattr(popup, signal_name))
                popup.findChild(QPushButton, action_name).click()
                self.assertEqual(list(spy), [[17]])
                self.assertFalse(popup._tick_timer.isActive())
                self.assertFalse(popup._auto_snooze_timer.isActive())

    def test_snooze_menu_retains_selected_delay(self):
        with patch.object(AlarmPopupWindow, "_play_notification_sound"):
            popup = AlarmPopupWindow(
                {"id": 23, "name": "Reminder"}, datetime.now() + timedelta(minutes=30)
            )
        spy = QSignalSpy(popup.snoozed)
        popup._snooze_btn.menu().actions()[2].trigger()
        self.assertEqual(list(spy), [[23, 30]])
        self.assertFalse(popup._tick_timer.isActive())
        self.assertFalse(popup._auto_snooze_timer.isActive())

    def test_accent_action_uses_shared_readable_text_for_each_state(self):
        for accent in ("#9274ce", "#808080", "#7950b8", "#b799eb", "#f2b96b"):
            with self.subTest(accent=accent):
                bundle = _alarm_popup_style_bundle(
                    tokens={"accent": accent, "accent_hover": QColor(accent).lighter(110).name()}
                )
                for background, text in (
                    (bundle["accent"], bundle["text_on_accent"]),
                    (bundle["accent_hover"], bundle["text_on_accent_hover"]),
                    (bundle["accent_pressed"], bundle["text_on_accent_pressed"]),
                ):
                    self.assertEqual(text, contrasting_text_color(background))
                    self.assertGreaterEqual(contrast_ratio(text, background), 4.5)
                stylesheet = _build_alarm_popup_stylesheet(bundle)
                self.assertIn(f"color: {bundle['text_on_accent_hover']};", stylesheet)
                self.assertIn(f"color: {bundle['text_on_accent_pressed']};", stylesheet)

    def test_valid_long_text_scrolls_without_clipping_or_hiding_actions(self):
        screen = Mock()
        screen.availableGeometry.return_value = QRect(0, 0, 640, 400)
        screen_patch = patch(
            "calendar_app.presentation.widgets.alarm_popup.QApplication.screenAt",
            return_value=screen,
        )
        screen_patch.start()
        self.addCleanup(screen_patch.stop)
        with (
            patch.object(AlarmPopupWindow, "_play_notification_sound"),
            patch("calendar_app.presentation.widgets.alarm_popup._popup_width", return_value=320),
        ):
            popup = AlarmPopupWindow(
                {
                    "id": 29,
                    "name": ("사업 추진 계획 및 예산 집행 현황 점검 회의 " * 9)[:200],
                    "location": ("포항테크노파크 본부동 연수실 담당 부서 안내 " * 10)[:255],
                },
                datetime.now() + timedelta(minutes=30),
            )
        self.addCleanup(popup.close)
        popup.show()
        self._app.processEvents()
        self._app.processEvents()
        available = screen.availableGeometry()
        self.assertLessEqual(popup.height(), available.height() - 32)
        self.assertGreater(popup._body_scroll.verticalScrollBar().maximum(), 0)
        for label in (popup._title_label, popup.findChild(QLabel, "LocationLabel")):
            self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()))
        for button in popup.findChildren(QPushButton):
            self.assertFalse(popup._body_scroll.isAncestorOf(button))
            self.assertTrue(
                popup.rect().contains(QRect(button.mapTo(popup, QPoint()), button.size()))
            )
        popup._body_scroll.verticalScrollBar().setValue(
            popup._body_scroll.verticalScrollBar().maximum()
        )
        self._app.processEvents()
        location = popup.findChild(QLabel, "LocationLabel")
        viewport = popup._body_scroll.viewport()
        self.assertLessEqual(
            location.mapTo(viewport, QPoint(0, location.height())).y(), viewport.height()
        )
        spy = QSignalSpy(popup.confirmed)
        popup.findChild(QPushButton, "ConfirmBtn").click()
        self.assertEqual(list(spy), [[29]])
        self.assertFalse(popup._tick_timer.isActive())
        self.assertFalse(popup._auto_snooze_timer.isActive())

    def test_style_bundle_forces_opaque_surface_colors(self):
        tokens = {
            "accent": "#22c3ca",
            "accent_hover": "#5de0e5",
            "bg_main": "rgba(12,24,36,230)",
            "bg_alt": "rgba(18,30,42,220)",
            "bg_item_hover": "rgba(255,255,255,0.08)",
            "bg_hover": "rgba(255,255,255,0.12)",
            "border": "rgba(255,255,255,0.16)",
            "text_primary": "#eff4fa",
            "text_secondary": "#c3cfdd",
            "text_muted": "#93a1b4",
            "warning_hex": "#f0a030",
            "success_hex": "#46CC71",
            "danger_hex": "#e05050",
        }

        bundle = _alarm_popup_style_bundle(tokens=tokens)
        stylesheet = _build_alarm_popup_stylesheet(bundle)

        self.assertEqual(bundle["card_bg"], "#0c1824")
        self.assertEqual(bundle["card_surface"], "#121e2a")
        self.assertEqual(bundle["card_hover"], "#25303b")
        self.assertIn("background: #0c1824;", stylesheet)
        self.assertIn("background-color: #121e2a;", stylesheet)


if __name__ == "__main__":
    unittest.main()
