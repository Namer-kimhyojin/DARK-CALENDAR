# -*- coding: utf-8 -*-
"""Common chrome keeps the dialog's own controls, results and close semantics."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPoint, QPointF, QSettings, Qt, QTimer
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSizeGrip,
    QToolButton,
    QVBoxLayout,
)

from calendar_app.presentation.dialogs.dialog_chrome import (
    ensure_dialog_chrome,
    prepare_dialog_chrome,
)
from calendar_app.presentation.dialogs.dialog_styles import apply_common_dialog_style


class DialogChromeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.settings = QSettings(
            str(Path(temporary.name) / "chrome.ini"), QSettings.Format.IniFormat
        )
        self.settings.setValue("text_theme", "dark")
        self.settings.setValue("panel_base_color", "#121827")
        self.settings.setValue("theme_color", "#c5a3f5")

    def _simple(self):
        dialog = QDialog()
        self.addCleanup(dialog.close)
        dialog.setWindowTitle("일반업무 등록")
        prepare_dialog_chrome(dialog, settings=self.settings)
        layout = QVBoxLayout(dialog)
        duplicate = QLabel(dialog.windowTitle())
        duplicate.setProperty("role", "dialogTitle")
        layout.addWidget(duplicate)
        field = QLineEdit("기존 업무 내용")
        layout.addWidget(field)
        apply_common_dialog_style(dialog, settings=self.settings)
        ensure_dialog_chrome(dialog, settings=self.settings)
        dialog.resize(420, 260)
        return dialog, layout, duplicate, field

    def test_repeated_install_keeps_one_header_close_and_original_layout(self):
        dialog, layout, duplicate, field = self._simple()
        for _ in range(4):
            ensure_dialog_chrome(dialog, settings=self.settings)
        self.assertTrue(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint)
        self.assertIs(dialog.layout(), layout)
        self.assertEqual(layout.count(), 2)
        self.assertEqual(field.text(), "기존 업무 내용")
        self.assertTrue(duplicate.isHidden())
        self.assertEqual(len(dialog.findChildren(QFrame, "CommonDialogHeader")), 1)
        self.assertEqual(len(dialog.findChildren(QToolButton, "CommonDialogClose")), 1)
        dialog.show()
        self.app.processEvents()
        dialog.hide()
        dialog.show()
        self.app.processEvents()
        self.assertEqual(len(dialog.findChildren(QToolButton, "CommonDialogClose")), 1)

    def test_header_reserves_body_space_and_keeps_resize_grip(self):
        dialog, _, _, field = self._simple()
        dialog.show()
        self.app.processEvents()
        controller = dialog._dc_dialog_chrome_controller
        self.assertLess(controller.header.geometry().bottom(), dialog.contentsRect().top())
        self.assertTrue(dialog.isSizeGripEnabled())
        self.assertEqual(len(dialog.findChildren(QSizeGrip)), 1)
        dialog.resize(640, 360)
        self.app.processEvents()
        self.assertEqual(controller.header.width(), dialog.width())
        self.assertEqual(field.text(), "기존 업무 내용")

    def test_existing_task_header_close_action_is_reused(self):
        dialog = QDialog()
        self.addCleanup(dialog.close)
        dialog.setWindowTitle("새 일정 추가")
        root = QVBoxLayout(dialog)
        header = QFrame()
        header.setObjectName("TaskEditorHeader")
        row = QHBoxLayout(header)
        heading = QLabel(dialog.windowTitle())
        row.addWidget(heading)
        close = QToolButton()
        close.setObjectName("TaskEditorClose")
        close.clicked.connect(lambda checked=False: dialog.done(42))
        row.addWidget(close)
        root.addWidget(header)
        original_margins = dialog.contentsMargins()
        prepare_dialog_chrome(dialog, settings=self.settings)
        ensure_dialog_chrome(dialog)
        self.assertFalse(dialog.findChildren(QFrame, "CommonDialogHeader"))
        self.assertTrue(close.property("dialogChromeClose"))
        self.assertEqual(dialog.contentsMargins(), original_margins)
        QTimer.singleShot(0, close.click)
        self.assertEqual(dialog.exec(), 42)

    def test_embedded_qdialog_is_not_promoted_to_a_window_or_adopted_as_outer_header(self):
        outer = QDialog()
        self.addCleanup(outer.close)
        outer.setWindowTitle("Outer manager")
        root = QVBoxLayout(outer)
        page = QDialog(outer)
        page.setWindowFlags(Qt.WindowType.Widget)
        page.setWindowTitle("Embedded page")
        page_layout = QVBoxLayout(page)
        header = QFrame(page)
        header.setObjectName("TaskEditorHeader")
        header.setProperty("role", "dialogHeader")
        row = QHBoxLayout(header)
        row.addWidget(QLabel(page.windowTitle()))
        inner_close = QToolButton(header)
        inner_close.setObjectName("TaskEditorClose")
        row.addWidget(inner_close)
        page_layout.addWidget(header)
        field = QLineEdit("Page data", page)
        page_layout.addWidget(field)
        root.addWidget(page)
        self.assertFalse(prepare_dialog_chrome(page, settings=self.settings))
        self.assertFalse(ensure_dialog_chrome(page))
        self.assertFalse(page.isWindow())
        ensure_dialog_chrome(outer, settings=self.settings)
        controller = outer._dc_dialog_chrome_controller
        self.assertIs(controller.header.parentWidget(), outer)
        self.assertIsNot(controller.close_button, inner_close)
        self.assertFalse(inner_close.property("dialogChromeClose"))
        self.assertEqual(field.text(), "Page data")

    def test_real_child_modal_keeps_its_own_header_and_close_result(self):
        outer, _, _, _ = self._simple()
        outer.show()
        child = QDialog(outer)
        self.addCleanup(child.close)
        child.setWindowTitle("Nested confirmation")
        QVBoxLayout(child).addWidget(QLabel("Nested content"))
        self.assertTrue(ensure_dialog_chrome(child, settings=self.settings))
        self.assertTrue(child.isWindow())
        QTimer.singleShot(0, child._dc_dialog_chrome_controller.close_button.click)
        self.assertEqual(child.exec(), QDialog.DialogCode.Rejected)
        self.assertTrue(outer.isVisible())

    def test_esc_and_header_close_keep_reject_and_close_event_semantics(self):
        dialog, _, _, _ = self._simple()
        QTimer.singleShot(0, lambda: QTest.keyClick(dialog, Qt.Key.Key_Escape))
        self.assertEqual(dialog.exec(), QDialog.DialogCode.Rejected)

        class GuardedDialog(QDialog):
            block_close = True
            close_calls = 0

            def closeEvent(self, event):
                self.close_calls += 1
                if self.block_close:
                    event.ignore()
                else:
                    super().closeEvent(event)

        guarded = GuardedDialog()
        self.addCleanup(guarded.close)
        guarded.setWindowTitle("변경 확인")
        QVBoxLayout(guarded).addWidget(QLabel("보존할 내용"))
        prepare_dialog_chrome(guarded, settings=self.settings)
        ensure_dialog_chrome(guarded)
        guarded.show()
        self.app.processEvents()
        guarded._dc_dialog_chrome_controller.close_button.click()
        self.assertTrue(guarded.isVisible())
        self.assertEqual(guarded.close_calls, 1)
        guarded.block_close = False
        guarded._dc_dialog_chrome_controller.close_button.click()
        self.assertFalse(guarded.isVisible())
        self.assertEqual(guarded.result(), QDialog.DialogCode.Rejected)

    def test_message_box_grid_buttons_and_cancel_result_are_preserved(self):
        box = QMessageBox()
        self.addCleanup(box.close)
        box.setWindowTitle("설정 저장")
        box.setText("변경 내용을 저장할까요?")
        box.setStandardButtons(QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        original_layout = box.layout()
        prepare_dialog_chrome(box, settings=self.settings)
        ensure_dialog_chrome(box)
        self.assertIs(box.layout(), original_layout)
        QTimer.singleShot(0, box._dc_dialog_chrome_controller.close_button.click)
        box.exec()
        self.assertIs(box.clickedButton(), box.button(QMessageBox.StandardButton.Cancel))

    def test_popup_and_native_file_chooser_keep_their_original_flags(self):
        popup = QDialog(None, Qt.WindowType.Popup)
        self.addCleanup(popup.close)
        QVBoxLayout(popup).addWidget(QLabel("색상 선택"))
        self.assertFalse(prepare_dialog_chrome(popup))
        chooser = QFileDialog()
        self.addCleanup(chooser.close)
        self.assertFalse(prepare_dialog_chrome(chooser))
        chooser.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        self.assertTrue(prepare_dialog_chrome(chooser, settings=self.settings))
        self.assertTrue(ensure_dialog_chrome(chooser))

    def test_window_title_updates_plain_header_text(self):
        dialog, _, _, _ = self._simple()
        dialog.setWindowTitle("문자 <b>제목</b>")
        self.app.processEvents()
        title = dialog._dc_dialog_chrome_controller.title_label
        self.assertEqual(title.text(), "문자 <b>제목</b>")
        self.assertEqual(title.textFormat(), Qt.TextFormat.PlainText)

    def test_generic_header_mark_uses_current_accent_without_duplicating_chrome(self):
        dialog, _, _, _ = self._simple()
        controller = dialog._dc_dialog_chrome_controller
        self.assertFalse(controller.mark_label.pixmap().isNull())
        old_mark = controller.mark_label.pixmap().cacheKey()
        self.settings.setValue("theme_color", "#f3b968")
        prepare_dialog_chrome(dialog, settings=self.settings)
        self.assertEqual(controller._mark_palette[0], "#f3b968")
        self.assertNotEqual(controller.mark_label.pixmap().cacheKey(), old_mark)
        self.assertEqual(len(dialog.findChildren(QToolButton, "CommonDialogClose")), 1)

    def test_fallback_header_drag_moves_without_touching_form_contents(self):
        dialog, _, _, field = self._simple()
        controller = dialog._dc_dialog_chrome_controller
        dialog.move(100, 100)
        pressed = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(5, 5),
            QPointF(120, 120),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        moved = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(75, 35),
            QPointF(190, 150),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        with patch.object(
            dialog, "windowHandle", return_value=SimpleNamespace(startSystemMove=lambda: False)
        ):
            self.assertTrue(controller.eventFilter(controller.title_label, pressed))
            self.assertTrue(controller.eventFilter(controller.title_label, moved))
        self.assertEqual(dialog.pos(), QPoint(170, 130))
        self.assertEqual(field.text(), "기존 업무 내용")

    def test_final_qt_events_after_python_gc_clear_are_ignored(self):
        dialog, _, _, _ = self._simple()
        controller = dialog._dc_dialog_chrome_controller
        controller.__dict__.clear()
        self.assertFalse(controller.eventFilter(dialog, QEvent(QEvent.Type.LayoutRequest)))
        dialog.resize(480, 300)
        self.app.processEvents()

    def test_windows_frameless_header_uses_qt_moves_and_stops_on_release(self):
        dialog, _, _, field = self._simple()
        controller = dialog._dc_dialog_chrome_controller
        dialog.move(100, 100)
        start_native = Mock(return_value=True)
        pressed = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(5, 5),
            QPointF(120, 120),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        moved = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(75, 35),
            QPointF(190, 150),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        released = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(75, 35),
            QPointF(190, 150),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        with (
            patch.object(QApplication, "platformName", return_value="windows"),
            patch.object(
                dialog,
                "windowHandle",
                return_value=SimpleNamespace(startSystemMove=start_native),
            ),
        ):
            self.assertFalse(controller.eventFilter(field, pressed))
            self.assertFalse(controller.eventFilter(controller.close_button, pressed))
            self.assertTrue(controller.eventFilter(controller.title_label, pressed))
            self.assertTrue(controller.eventFilter(controller.title_label, moved))
            self.assertEqual(dialog.pos(), QPoint(170, 130))
            self.assertTrue(controller.eventFilter(controller.title_label, released))
            self.assertIsNone(controller._drag_origin)
            self.assertFalse(controller.eventFilter(controller.title_label, moved))
        start_native.assert_not_called()
        self.assertEqual(dialog.pos(), QPoint(170, 130))
        self.assertEqual(field.text(), "기존 업무 내용")

    def test_windows_size_grip_resizes_with_limits_and_rtl_anchor(self):
        def mouse(kind, global_position, button, buttons):
            return QMouseEvent(
                kind,
                QPointF(5, 5),
                QPointF(global_position),
                button,
                buttons,
                Qt.KeyboardModifier.NoModifier,
            )

        for rtl in (False, True):
            with self.subTest(rtl=rtl):
                dialog, _, _, field = self._simple()
                dialog.setLayoutDirection(
                    Qt.LayoutDirection.RightToLeft if rtl else Qt.LayoutDirection.LeftToRight
                )
                dialog.setMinimumSize(560, 500)
                dialog.setMaximumSize(700, 660)
                dialog.setGeometry(100, 100, 700, 660)
                controller = dialog._dc_dialog_chrome_controller
                grip = dialog.findChild(QSizeGrip)
                self.assertIsNotNone(grip)
                with patch.object(QApplication, "platformName", return_value="windows"):
                    self.assertTrue(
                        controller.eventFilter(
                            grip,
                            mouse(
                                QEvent.Type.MouseButtonPress,
                                QPoint(1000, 800),
                                Qt.MouseButton.LeftButton,
                                Qt.MouseButton.LeftButton,
                            ),
                        )
                    )
                    for delta_x, delta_y, expected in (
                        (50 if rtl else -50, -40, (650, 620)),
                        (500 if rtl else -500, -500, (560, 500)),
                        (-500 if rtl else 500, 500, (700, 660)),
                    ):
                        self.assertTrue(
                            controller.eventFilter(
                                grip,
                                mouse(
                                    QEvent.Type.MouseMove,
                                    QPoint(1000 + delta_x, 800 + delta_y),
                                    Qt.MouseButton.NoButton,
                                    Qt.MouseButton.LeftButton,
                                ),
                            )
                        )
                        self.assertEqual((dialog.width(), dialog.height()), expected)
                        self.assertEqual(
                            dialog.pos(), QPoint(800 - expected[0] if rtl else 100, 100)
                        )
                        self.assertEqual(field.text(), "기존 업무 내용")
                    self.assertTrue(
                        controller.eventFilter(
                            grip,
                            mouse(
                                QEvent.Type.MouseButtonRelease,
                                QPoint(1000, 800),
                                Qt.MouseButton.LeftButton,
                                Qt.MouseButton.NoButton,
                            ),
                        )
                    )
                    self.assertIsNone(controller._resize_origin)
                    self.assertFalse(
                        controller.eventFilter(
                            grip,
                            mouse(
                                QEvent.Type.MouseMove,
                                QPoint(1100, 900),
                                Qt.MouseButton.NoButton,
                                Qt.MouseButton.LeftButton,
                            ),
                        )
                    )

    def test_other_platform_size_grip_keeps_native_event_handling(self):
        dialog, _, _, _ = self._simple()
        controller = dialog._dc_dialog_chrome_controller
        grip = dialog.findChild(QSizeGrip)
        pressed = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(5, 5),
            QPointF(1000, 800),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        with patch.object(QApplication, "platformName", return_value="offscreen"):
            self.assertFalse(controller.eventFilter(grip, pressed))
        self.assertIsNone(controller._resize_origin)

    def test_reported_native_move_keeps_fallback_if_qt_pressed_moves_still_arrive(self):
        for native_already_moved in (False, True):
            with self.subTest(native_already_moved=native_already_moved):
                dialog, _, _, field = self._simple()
                controller = dialog._dc_dialog_chrome_controller
                dialog.move(100, 100)

                def start_native(already_moved=native_already_moved, target=dialog):
                    if already_moved:
                        target.move(170, 130)
                    return True

                pressed = QMouseEvent(
                    QEvent.Type.MouseButtonPress,
                    QPointF(5, 5),
                    QPointF(120, 120),
                    Qt.MouseButton.LeftButton,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                )
                moved = QMouseEvent(
                    QEvent.Type.MouseMove,
                    QPointF(75, 35),
                    QPointF(190, 150),
                    Qt.MouseButton.NoButton,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                )
                with patch.object(
                    dialog,
                    "windowHandle",
                    return_value=SimpleNamespace(startSystemMove=start_native),
                ):
                    self.assertTrue(controller.eventFilter(controller.title_label, pressed))
                    self.assertTrue(controller.eventFilter(controller.title_label, moved))
                self.assertEqual(dialog.pos(), QPoint(170, 130))
                self.assertEqual(field.text(), "기존 업무 내용")


if __name__ == "__main__":
    unittest.main()
