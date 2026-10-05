# -*- coding: utf-8 -*-
"""Splash screen shown on application startup."""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import QApplication, QWidget

from calendar_app.app_metadata import APP_NAME, APP_VERSION_DISPLAY
from calendar_app.app_paths import APP_ICON_PATH, APP_ICON_TOAST_PATH, get_resource_path
from calendar_app.infrastructure.i18n import t

_COMPLETE_HOLD_MS = 100  # hold after reaching 100%
_FADE_MS = 150  # fade-out duration
_PROGRESS_TICK_MS = 20  # display progress chase cadence


class SplashScreen(QWidget):
    """Frameless, translucent splash screen with premium aesthetics.

    All elements are visible immediately. The progress bar chases logical
    targets in small steps so fast startup phases still feel incremental.
    """

    W, H = 560, 340
    RADIUS = 18
    finished = pyqtSignal()

    BG_COLOR_START = QColor("#111D2B")
    BG_COLOR_END = QColor("#111D2B")
    NAME_COLOR = QColor(250, 250, 250)
    META_COLOR = QColor(164, 170, 184, 210)
    FONT_FAMILY = "Malgun Gothic"
    ACCENT_GRADIENT = [
        (0.0, QColor(255, 42, 117)),
        (0.5, QColor(140, 52, 235)),
        (1.0, QColor(42, 213, 255)),
    ]

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedSize(self.W, self.H)
        self._center_on_screen()

        self._status_text = "Initializing..."
        self._headline_text = t("splash.organizing_today", "오늘을 정리하는 중")
        self._progress = 0.0
        self._progress_anim = 0.0
        self._finish_requested = False
        self._is_fading_out = False

        self._icon_opacity = 1.0
        self._icon_offset = 0.0
        self._text_opacity = 1.0
        self._text_offset = 0.0
        self._glow_opacity = 1.0
        self._glow_pulse = 0.0
        self._glow_direction = 1

        self._icon = QPixmap(get_resource_path("Assets/splash_icon.png"))
        if self._icon.isNull():
            self._icon = QPixmap(APP_ICON_TOAST_PATH)
        if self._icon.isNull():
            self._icon = QPixmap(APP_ICON_PATH)

        self._setup_animations()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_status(self, text: str, progress: float | None = None) -> None:
        """Directly update status and target progress."""
        self._status_text = text
        if progress is not None:
            target = max(0.0, min(1.0, progress))
            if 0.0 < target < 1.0:
                target = max(target, 0.04)
            if target >= 1.0:
                self._finish_requested = True
                self._finish_hold_timer.stop()
                self.finished.emit()
            if target > self._progress:
                self._progress = target
            self._start_progress_chase()
        self.update()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_animations(self) -> None:
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(_PROGRESS_TICK_MS)
        self._progress_timer.timeout.connect(self._advance_progress_display)

        self._finish_hold_timer = QTimer(self)
        self._finish_hold_timer.setSingleShot(True)
        self._finish_hold_timer.timeout.connect(self._start_fade_out)

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)  # ~60 FPS
        self._anim_timer.timeout.connect(self._pulse_glow)
        # Static identity: repaint only when startup progress changes.

    def _pulse_glow(self) -> None:
        """Update glow pulse level for continuous background animation."""
        step = 0.015
        self._glow_pulse += step * self._glow_direction
        if self._glow_pulse >= 1.0:
            self._glow_pulse = 1.0
            self._glow_direction = -1
        elif self._glow_pulse <= 0.0:
            self._glow_pulse = 0.0
            self._glow_direction = 1
        self.update()

    def _start_progress_chase(self) -> None:
        if not self._progress_timer.isActive():
            self._progress_timer.start()

    def _progress_step(self, delta: float) -> float:
        if self._progress >= 1.0:
            return max(0.008, min(0.024, delta * 0.10))
        return max(0.003, min(0.016, delta * 0.05))

    def _advance_progress_display(self) -> None:
        delta = self._progress - self._progress_anim
        if delta <= 0.0005:
            self._progress_anim = self._progress
            self.update()
            self._progress_timer.stop()
            if self._finish_requested and self._progress_anim >= 0.999:
                self._schedule_finish_hold()
            return

        self._progress_anim = min(
            self._progress,
            self._progress_anim + self._progress_step(delta),
        )
        self.update()

        if self._finish_requested and self._progress_anim >= 0.999:
            self._progress_anim = 1.0
            self.update()
            self._progress_timer.stop()
            self._schedule_finish_hold()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            rect = screen.availableGeometry()
            self.move(
                rect.x() + (rect.width() - self.W) // 2,
                rect.y() + (rect.height() - self.H) // 2,
            )

    def _schedule_finish_hold(self) -> None:
        if not self._finish_hold_timer.isActive() and not self._is_fading_out:
            self._finish_hold_timer.start(_COMPLETE_HOLD_MS)

    def _start_fade_out(self) -> None:
        if not self.isVisible() or self._is_fading_out:
            return
        self._is_fading_out = True

        # Stop background animation timer to save resources
        if hasattr(self, "_anim_timer"):
            self._anim_timer.stop()

        self._fade_out_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_out_anim.setDuration(_FADE_MS)
        self._fade_out_anim.setStartValue(float(self.windowOpacity()))
        self._fade_out_anim.setEndValue(0.0)
        self._fade_out_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade_out_anim.finished.connect(self.close)
        self._fade_out_anim.start()

    def finish(self) -> None:
        """Trigger immediate finish sequence (ignoring hold timers)."""
        self._finish_requested = True
        if self._progress_anim < 1.0:
            self._progress_anim = 1.0
            self.update()
        self._start_fade_out()

    @staticmethod
    def _make_accent_grad(x: float, w: float) -> QLinearGradient:
        grad = QLinearGradient(x, 0, x + w, 0)
        for pos, col in SplashScreen.ACCENT_GRADIENT:
            grad.setColorAt(pos, col)
        return grad

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        try:
            self._paint(painter)
        finally:
            painter.end()

    def _paint(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        background = QPainterPath()
        background.addRoundedRect(QRectF(0, 0, self.W, self.H), self.RADIUS, self.RADIUS)
        painter.fillPath(background, QColor("#111D2B"))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#293B4B"), 1.0))
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.W - 1, self.H - 1), self.RADIUS, self.RADIUS)

        if not self._icon.isNull():
            # The symbol has transparent margins; the displayed mark is 82px tall.
            painter.drawPixmap(212, 35, 136, 136, self._icon)
        painter.setPen(self.NAME_COLOR)
        painter.setFont(QFont("Segoe UI", 25, QFont.Weight.DemiBold))
        painter.drawText(QRectF(32, 166, self.W - 64, 44), Qt.AlignmentFlag.AlignCenter, APP_NAME)

        painter.setFont(QFont(self.FONT_FAMILY, 10))
        painter.setPen(QColor("#A8BAC6"))
        metrics = QFontMetrics(painter.font())
        headline = metrics.elidedText(self._headline_text, Qt.TextElideMode.ElideRight, 440)
        painter.drawText(QRectF(60, 214, 440, 24), Qt.AlignmentFlag.AlignCenter, headline)

        bar_x, bar_y, bar_w, bar_h = 140, 254, 280, 3
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#304353"))
        painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 1.5, 1.5)
        if self._progress_anim > 0:
            painter.setBrush(QColor("#43CDB9"))
            painter.drawRoundedRect(
                QRectF(bar_x, bar_y, bar_w * self._progress_anim, bar_h), 1.5, 1.5
            )

        painter.setPen(QColor("#A8BAC6"))
        painter.setFont(QFont(self.FONT_FAMILY, 9))
        status = QFontMetrics(painter.font()).elidedText(
            self._status_text, Qt.TextElideMode.ElideRight, 440
        )
        painter.drawText(QRectF(60, 271, 440, 22), Qt.AlignmentFlag.AlignCenter, status)
        painter.setPen(QColor("#7F94A5"))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(
            QRectF(32, 307, self.W - 64, 18), Qt.AlignmentFlag.AlignCenter, APP_VERSION_DISPLAY
        )
