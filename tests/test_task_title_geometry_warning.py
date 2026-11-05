# -*- coding: utf-8 -*-
"""Task title CSS must fit text without overflowing Qt's widget size limit."""

import math

from PyQt6.QtCore import QCoreApplication, QEvent, qInstallMessageHandler
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QDialog, QLineEdit, QVBoxLayout
import pytest

from calendar_app.presentation.dialogs.dialog_editor_styles import build_task_editor_stylesheet


@pytest.mark.parametrize("base_points", [10, 11, 24])
@pytest.mark.parametrize("sheet_layout", [False, True])
def test_title_polish_has_no_maximum_size_warning(base_points, sheet_layout):
    app = QApplication.instance() or QApplication([])
    original_font = QFont(app.font())
    font = QFont(original_font)
    font.setPointSize(base_points)
    app.setFont(font)
    messages = []
    previous = qInstallMessageHandler(lambda _kind, _context, message: messages.append(message))
    dialog = QDialog()
    try:
        dialog.setObjectName("TaskEditorDialog")
        dialog.setProperty("sheetLayout", sheet_layout)
        layout = QVBoxLayout(dialog)
        editor = QLineEdit("월간회의 및 업무 점검", dialog)
        editor.setObjectName("TaskTitleEdit")
        editor.setMinimumHeight(52 if sheet_layout else 34)
        if not sheet_layout:
            editor.setMaximumHeight(36)
        layout.addWidget(editor)
        stylesheet = build_task_editor_stylesheet(
            metrics={
                "base_font_pt": math.ceil(base_points * 96 / 72),
                "title_font_pt": math.ceil((base_points + 5) * 96 / 72),
            }
        )
        for _ in range(2):
            dialog.setStyleSheet(stylesheet)
            dialog.ensurePolished()
            editor.ensurePolished()
            dialog.show()
            app.processEvents()
        assert editor.height() >= editor.fontMetrics().height()
        size_warnings = [
            message for message in messages if "QWidget::setMaximumSize:" in message
        ]
        assert size_warnings == []
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qInstallMessageHandler(previous)
        app.setFont(original_font)
