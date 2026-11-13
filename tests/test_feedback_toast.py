# -*- coding: utf-8 -*-
"""Ordinary feedback remains branded, bounded and separate from system alarms."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPointF, QSettings, Qt
from PyQt6.QtGui import QEnterEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLineEdit, QMainWindow

from calendar_app.app_metadata import APP_NAME
from calendar_app.presentation.dialogs.dialog_styles import get_dialog_theme_tokens
from calendar_app.presentation.main_window.window_shell_actions import WindowShellActionsMixin
from calendar_app.presentation.widgets.feedback_toast import FeedbackToast, show_feedback_toast


class ToastHost(WindowShellActionsMixin, QMainWindow):
    pass


class FeedbackToastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.host = ToastHost()
        self.addCleanup(self.host.close)
        self.host.settings = QSettings(
            str(Path(temporary.name) / "toast.ini"), QSettings.Format.IniFormat
        )
        self.host.settings.setValue("theme_color", "#c5a3f5")
        self.host.settings.setValue("panel_base_color", "#121827")
        self.host.settings.setValue("text_theme", "dark")
        self.host.setCentralWidget(QLineEdit())
        self.host.resize(600, 400)
        self.host.show()
        self.app.processEvents()

    def test_repeated_layout_feedback_reuses_one_branded_card(self):
        first = show_feedback_toast(self.host, "레이아웃 변경", "프리셋 레이아웃이 적용되었습니다.")
        for _ in range(10):
            current = show_feedback_toast(
                self.host, "레이아웃 변경", "프리셋 레이아웃이 적용되었습니다."
            )
            self.assertIs(current, first)
        self.assertEqual(len(self.host.findChildren(FeedbackToast)), 1)
        self.assertEqual(first.brand_label.text(), APP_NAME)
        self.assertEqual(first.title_label.text(), "레이아웃 변경")
        self.assertNotIn("Python", first.accessibleName())

    def test_current_message_replaces_previous_and_stays_plain_text(self):
        toast = show_feedback_toast(self.host, "저장", "처음")
        show_feedback_toast(self.host, "<b>수정</b>", "<script>사용자 입력</script>")
        self.assertEqual(toast.title_label.textFormat(), Qt.TextFormat.PlainText)
        self.assertEqual(toast.message_label.textFormat(), Qt.TextFormat.PlainText)
        self.assertEqual(toast.message_label.text(), "<script>사용자 입력</script>")

    def test_close_and_timeout_dismiss_without_creating_another_card(self):
        toast = show_feedback_toast(self.host, "알림", "완료")
        toast.close_button.click()
        self.assertFalse(toast.isVisible())
        self.assertFalse(toast._timer.isActive())
        show_feedback_toast(self.host, "알림", "다시 표시")
        toast._timer.start(20)
        QTest.qWait(50)
        self.assertFalse(toast.isVisible())
        self.assertEqual(len(self.host.findChildren(FeedbackToast)), 1)

    def test_card_uses_current_theme_and_fits_its_monitor(self):
        toast = show_feedback_toast(self.host, "설정 저장", "현재 설정을 적용했습니다.")
        self.app.processEvents()
        tokens = get_dialog_theme_tokens(settings=self.host.settings)
        self.assertIn(tokens["floating_bg"], toast.styleSheet())
        self.assertTrue(toast.screen().availableGeometry().contains(toast.frameGeometry()))
        self.assertTrue(toast.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating))
        self.assertTrue(toast.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus)
        self.assertTrue(toast.close_button.accessibleName())
        original = toast.styleSheet()
        self.host.settings.setValue("text_theme", "light")
        self.host.settings.setValue("panel_base_color", "#f3f1fa")
        show_feedback_toast(self.host, "설정 저장", "밝은 설정")
        self.assertNotEqual(toast.styleSheet(), original)

    def test_hover_pauses_expiry_and_owner_hide_dismisses(self):
        toast = show_feedback_toast(self.host, "알림", "자세한 내용")
        self.app.sendEvent(toast, QEnterEvent(QPointF(), QPointF(), QPointF()))
        self.assertFalse(toast._timer.isActive())
        self.app.sendEvent(toast, QEvent(QEvent.Type.Leave))
        self.assertTrue(toast._timer.isActive())
        self.host.hide()
        self.assertFalse(toast.isVisible())

    def test_ordinary_feedback_avoids_native_route_and_explicit_system_preserves_it(self):
        with patch.object(self.host, "show_system_toast") as system:
            self.host.show_toast("레이아웃 변경", "적용 완료")
            system.assert_not_called()
            self.host.show_toast("시스템 알림", "중요 알림", system=True)
            system.assert_called_once_with("시스템 알림", "중요 알림")

    def test_local_delivery_failure_falls_back_to_existing_system_route(self):
        with (
            patch(
                "calendar_app.presentation.widgets.feedback_toast.show_feedback_toast",
                return_value=None,
            ),
            patch.object(self.host, "show_system_toast") as system,
        ):
            self.host.show_toast("알림", "완료")
        system.assert_called_once_with("알림", "완료")
