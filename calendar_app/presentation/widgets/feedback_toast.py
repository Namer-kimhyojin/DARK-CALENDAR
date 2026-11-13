# -*- coding: utf-8 -*-
"""Brief branded feedback for reversible in-app actions, separate from alarms."""

from PyQt6.QtCore import QEvent, Qt, QThread, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from calendar_app.app_metadata import APP_NAME
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_styles import (
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)
from calendar_app.shared.brand_assets import brand_mark_pixmap
from calendar_app.shared.color_utils import parse_css_color
from calendar_app.shared.icon_map import ICON, icon, strip_leading_emoji

_TOAST_NAME = "air_calendar_feedback_toast"
_DURATION_MS = 3200


def _feedback_toast_stylesheet(tokens: dict, metrics: dict) -> str:
    base = int(metrics.get("base_font_pt", 14))
    radius = int(metrics.get("group_radius", 12))
    return f"""
QFrame#{_TOAST_NAME} {{ background: transparent; border: none; }}
QFrame#FeedbackToastCard {{
    background-color: {tokens["floating_bg"]};
    border: 1px solid {tokens["border"]}; border-radius: {radius}px;
}}
QLabel {{ background: transparent; border: none; margin: 0; padding: 0; }}
QLabel#FeedbackToastBrand {{ color: {tokens["text_muted"]}; font-size: {max(11, base - 2)}px; font-weight: 600; }}
QLabel#FeedbackToastTitle {{ color: {tokens["text_primary"]}; font-size: {base + 1}px; font-weight: 700; }}
QLabel#FeedbackToastMessage {{ color: {tokens["text_secondary"]}; font-size: {base}px; font-weight: 400; }}
QPushButton#FeedbackToastClose {{
    background: transparent; color: {tokens["text_secondary"]}; border: none;
    border-radius: {int(metrics.get("button_radius", 10))}px; padding: 0;
    min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px;
}}
QPushButton#FeedbackToastClose:hover {{ background: {tokens["surface_hover"]}; }}
"""


class FeedbackToast(QFrame):
    """One reusable, nonactivating feedback card owned by the application window."""

    def __init__(self, owner: QWidget):
        super().__init__(
            owner,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setObjectName(_TOAST_NAME)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._owner = owner
        self._hovering = False
        self._duration_ms = _DURATION_MS
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        owner.installEventFilter(self)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.card = QFrame()
        self.card.setObjectName("FeedbackToastCard")
        outer.addWidget(self.card)
        content = QHBoxLayout(self.card)
        content.setContentsMargins(14, 12, 10, 14)
        content.setSpacing(12)

        self.status_icon = QLabel()
        self.status_icon.setFixedSize(24, 24)
        content.addWidget(self.status_icon, 0, Qt.AlignmentFlag.AlignTop)
        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(4)
        self.brand_label = QLabel(APP_NAME)
        self.brand_label.setObjectName("FeedbackToastBrand")
        self.title_label = QLabel()
        self.title_label.setObjectName("FeedbackToastTitle")
        self.title_label.setWordWrap(True)
        self.message_label = QLabel()
        self.message_label.setObjectName("FeedbackToastMessage")
        self.message_label.setWordWrap(True)
        for label in (self.brand_label, self.title_label, self.message_label):
            label.setTextFormat(Qt.TextFormat.PlainText)
            text_column.addWidget(label)
        content.addLayout(text_column, 1)
        self.close_button = QPushButton()
        self.close_button.setObjectName("FeedbackToastClose")
        self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_button.setAccessibleName(t("common.close", "닫기"))
        self.close_button.setToolTip(self.close_button.accessibleName())
        self.close_button.clicked.connect(self.hide)
        content.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)

    def _target_screen(self):
        active = QApplication.activeModalWidget() or QApplication.activeWindow()
        if active is not None and active is not self and active.isVisible():
            return active.screen()
        if self._owner.isVisible():
            return self._owner.screen()
        from PyQt6.QtGui import QCursor

        return (
            QApplication.screenAt(QCursor.pos())
            or self._owner.screen()
            or QApplication.primaryScreen()
        )

    def _reposition(self):
        screen = self._target_screen()
        if screen is None:
            return
        available = screen.availableGeometry()
        margin = min(20, max(4, available.width() // 40))
        width = max(1, min(400, available.width() - margin * 2))
        self.setFixedWidth(width)
        self.message_label.setMaximumHeight(self.message_label.fontMetrics().lineSpacing() * 5)
        self.setMaximumHeight(max(1, available.height() - margin * 2))
        self.adjustSize()
        self.move(
            max(available.left() + margin, available.right() - self.width() - margin + 1),
            max(available.top() + margin, available.bottom() - self.height() - margin + 1),
        )

    def show_feedback(self, title: str, message: str):
        settings = getattr(self._owner, "settings", None)
        tokens = get_dialog_theme_tokens(settings=settings)
        metrics = get_dialog_metric_tokens(settings=settings)
        self.setStyleSheet(_feedback_toast_stylesheet(tokens, metrics))
        self.status_icon.setPixmap(
            brand_mark_pixmap(
                tokens["accent"],
                24,
                background=tokens["floating_bg"],
                base=tokens["base_hex"],
                dpr=self.devicePixelRatioF(),
            )
        )
        self.close_button.setIcon(
            icon(ICON.CLOSE, color=parse_css_color(tokens["text_primary"]).name())
        )
        title = strip_leading_emoji(str(title or ""))
        message = str(message or "")
        self.title_label.setText(title)
        self.title_label.setToolTip(title)
        self.message_label.setText(message)
        self.message_label.setToolTip(message)
        self.setAccessibleName(f"{APP_NAME} · {title}")
        self.setAccessibleDescription(message)
        self.ensurePolished()
        self._reposition()
        self.show()
        self.raise_()
        if not self._hovering:
            self._timer.start(self._duration_ms)

    def enterEvent(self, event):
        self._hovering = True
        self._timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovering = False
        if self.isVisible():
            self._timer.start(self._duration_ms)
        super().leaveEvent(event)

    def hideEvent(self, event):
        self._timer.stop()
        self._hovering = False
        super().hideEvent(event)

    def eventFilter(self, watched, event):
        if watched is self._owner:
            if event.type() in (QEvent.Type.Close, QEvent.Type.Hide):
                self.hide()
            elif event.type() in (QEvent.Type.Move, QEvent.Type.Resize) and self.isVisible():
                self._reposition()
        return super().eventFilter(watched, event)


def show_feedback_toast(owner: QWidget, title: str, message: str) -> FeedbackToast | None:
    """Coalesce ordinary confirmations into one GUI-owned card; keep OS fallback."""
    app = QApplication.instance()
    if app is None or not isinstance(owner, QWidget) or QThread.currentThread() != app.thread():
        return None
    toast = owner.findChild(FeedbackToast, _TOAST_NAME)
    if toast is None:
        toast = FeedbackToast(owner)
    toast.show_feedback(title, message)
    return toast
