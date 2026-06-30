"""Splash screen shown on application startup."""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
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
from calendar_app.app_paths import APP_ICON_PATH, APP_ICON_TOAST_PATH

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

    BG_COLOR_START = QColor(18, 19, 24)
    BG_COLOR_END = QColor(8, 9, 12)
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
        self._anim_timer.start()

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

        outer_rect = QRectF(0, 0, self.W, self.H)
        bg_path = QPainterPath()
        bg_path.addRoundedRect(outer_rect, self.RADIUS, self.RADIUS)
        painter.setClipPath(bg_path)

        bg_grad = QLinearGradient(0, 0, self.W, self.H)
        bg_grad.setColorAt(0.0, self.BG_COLOR_START)
        bg_grad.setColorAt(0.56, QColor(13, 15, 22))
        bg_grad.setColorAt(1.0, self.BG_COLOR_END)
        painter.fillPath(bg_path, bg_grad)

        side_grad = QLinearGradient(0, 0, self.W, 0)
        side_grad.setColorAt(0.0, QColor(255, 42, 117, 38))
        side_grad.setColorAt(0.42, QColor(42, 213, 255, 20))
        side_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillPath(bg_path, side_grad)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 8))
        painter.drawRoundedRect(QRectF(18, 18, self.W - 36, self.H - 36), 14, 14)

        painter.setBrush(QColor(9, 10, 15, 205))
        painter.drawRoundedRect(QRectF(20, 20, self.W - 40, self.H - 40), 13, 13)

        painter.setClipping(False)
        border_path = QPainterPath()
        border_path.addRoundedRect(
            self.rect().toRectF().adjusted(0.5, 0.5, -0.5, -0.5),
            self.RADIUS,
            self.RADIUS,
        )
        border_grad = QLinearGradient(0, 0, self.W, self.H)
        border_grad.setColorAt(0.0, QColor(255, 255, 255, 48))
        border_grad.setColorAt(0.55, QColor(115, 120, 255, 22))
        border_grad.setColorAt(1.0, QColor(255, 255, 255, 8))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QBrush(QColor(0, 0, 0, 170)), 1.0))
        painter.drawPath(border_path)
        painter.setPen(QPen(QBrush(border_grad), 1.0))
        painter.drawPath(border_path)

        content_x = 48
        title_x = content_x + 62
        top_y = 54
        icon_size = 46
        if not self._icon.isNull():
            painter.setOpacity(self._icon_opacity)
            painter.drawPixmap(
                content_x, top_y + int(self._icon_offset), icon_size, icon_size, self._icon
            )

        painter.setOpacity(self._text_opacity)
        text_y_offset = int(self._text_offset)

        font_name = QFont(self.FONT_FAMILY, 22, QFont.Weight.DemiBold)
        painter.setFont(font_name)
        painter.setPen(self.NAME_COLOR)
        painter.drawText(
            title_x,
            top_y + 2 + text_y_offset,
            230,
            34,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            APP_NAME,
        )

        font_small = QFont(self.FONT_FAMILY, 9)
        painter.setFont(font_small)
        painter.setPen(self.META_COLOR)
        painter.drawText(
            title_x,
            top_y + 44 + text_y_offset,
            230,
            22,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            APP_VERSION_DISPLAY,
        )

        painter.setPen(QColor(207, 213, 226, 230))
        painter.setFont(QFont(self.FONT_FAMILY, 12, QFont.Weight.Medium))
        painter.drawText(
            content_x,
            152 + text_y_offset,
            250,
            28,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "오늘을 정리하는 중",
        )

        status_y = 224
        bar_x = content_x
        bar_w = 286
        font_status = QFont(self.FONT_FAMILY, 9)
        painter.setFont(font_status)
        painter.setPen(QColor(158, 165, 181, 210))
        metrics = QFontMetrics(font_status)
        elided_text = metrics.elidedText(
            self._status_text,
            Qt.TextElideMode.ElideRight,
            bar_w,
        )
        painter.drawText(
            bar_x,
            status_y,
            bar_w,
            20,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            elided_text,
        )

        percent = f"{int(round(self._progress_anim * 100)):d}%"
        painter.setPen(QColor(205, 212, 226, 230))
        painter.drawText(
            bar_x + bar_w - 54,
            status_y,
            54,
            20,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            percent,
        )

        painter.setOpacity(1.0)
        bar_y = status_y + 30
        bar_h = 6
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 18))
        painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 3, 3)

        fill_w = int(bar_w * self._progress_anim)
        if fill_w > 0:
            painter.setBrush(self._make_accent_grad(bar_x, bar_w))
            painter.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 3, 3)

        panel_rect = QRectF(364, 56, 144, 210)
        painter.setBrush(QColor(16, 18, 26, 238))
        painter.setPen(QPen(QColor(255, 255, 255, 32), 1.0))
        painter.drawRoundedRect(panel_rect, 12, 12)

        painter.setPen(QColor(237, 240, 248, 232))
        painter.setFont(QFont(self.FONT_FAMILY, 10, QFont.Weight.DemiBold))
        painter.drawText(382, 76, 104, 18, Qt.AlignmentFlag.AlignLeft, "Startup")

        painter.setPen(QColor(155, 163, 181, 210))
        painter.setFont(QFont(self.FONT_FAMILY, 8))
        painter.drawText(382, 98, 104, 18, Qt.AlignmentFlag.AlignLeft, "calendar view")

        day_names = ["M", "T", "W", "T", "F"]
        painter.setFont(QFont(self.FONT_FAMILY, 7, QFont.Weight.Medium))
        for index, day_name in enumerate(day_names):
            x = 382 + index * 20
            painter.setPen(QColor(133, 143, 164, 210))
            painter.drawText(x, 126, 18, 14, Qt.AlignmentFlag.AlignHCenter, day_name)

        grid_top = 148
        for row in range(3):
            for col in range(5):
                x = 382 + col * 20
                y = grid_top + row * 22
                active = (row * 5 + col) / 14.0 <= self._progress_anim
                if active:
                    cell_grad = QLinearGradient(x, y, x + 18, y + 18)
                    cell_grad.setColorAt(0.0, QColor(255, 42, 117, 210))
                    cell_grad.setColorAt(1.0, QColor(42, 213, 255, 190))
                    painter.setBrush(cell_grad)
                    painter.setPen(Qt.PenStyle.NoPen)
                else:
                    painter.setBrush(QColor(255, 255, 255, 13))
                    painter.setPen(QPen(QColor(255, 255, 255, 16), 1.0))
                painter.drawRoundedRect(QRectF(x, y, 16, 16), 4, 4)

        pulse_x = 382 + (self._glow_pulse * 92)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(42, 213, 255, 120))
        painter.drawRoundedRect(QRectF(pulse_x, 236, 24, 3), 1.5, 1.5)
