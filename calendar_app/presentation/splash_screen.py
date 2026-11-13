# -*- coding: utf-8 -*-
"""Splash screen shown on application startup."""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QSettings, Qt, QTimer, pyqtSignal
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
from calendar_app.app_paths import APP_ICON_PATH
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_styles import get_dialog_theme_tokens
from calendar_app.shared.brand_assets import brand_mark_pixmap
from calendar_app.shared.color_utils import composite_color, contrast_safe_color, parse_css_color
from calendar_app.shared.typography import DEFAULT_UI_FONT, ui_text_families

_COMPLETE_HOLD_MS = 100  # hold after reaching 100%
_FADE_MS = 150  # fade-out duration
_PROGRESS_TICK_MS = 20  # display progress chase cadence


class SplashScreen(QWidget):
    """Frameless, translucent splash screen with premium aesthetics.

    All elements are visible immediately. The progress bar chases logical
    targets in small steps so fast startup phases still feel incremental.
    """

    W, H = 480, 280
    RADIUS = 16
    finished = pyqtSignal()

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

        settings = QSettings("kimhyojin", "Dark Calendar")
        self._theme_tokens = get_dialog_theme_tokens(
            settings=settings,
            theme_color=None if settings.contains("theme_color") else "#c5a3f5",
            panel_base_color=None if settings.contains("panel_base_color") else "#121827",
        )
        self._status_text = t("splash.preparing_runtime", "런타임 준비 중...")
        self._headline_text = t("splash.organizing_today", "오늘을 정리하는 중")
        self.setAccessibleName(APP_NAME)
        self.setAccessibleDescription(self._headline_text)
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

        self._icon = brand_mark_pixmap(
            self._theme_tokens["accent"],
            64,
            background=self._theme_tokens["floating_bg"],
            base=self._theme_tokens["base_hex"],
            dpr=self.devicePixelRatioF(),
        )
        if self._icon.isNull():
            self._icon = QPixmap(APP_ICON_PATH)

        self._setup_animations()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_status(self, text: str, progress: float | None = None) -> None:
        """Directly update status and target progress."""
        self._status_text = text
        self.setAccessibleDescription(str(text))
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

    def _display_progress_percent(self) -> int:
        """Match the visible bar, never announce 100% before it is complete."""
        return max(0, min(100, int(self._progress_anim * 100 + 1e-9)))

    def _make_accent_grad(self, x: float, w: float) -> QLinearGradient:
        grad = QLinearGradient(x, 0, x + w, 0)
        surface = composite_color(self._theme_tokens["floating_bg"], self._theme_tokens["base_hex"])
        for position, key in ((0.0, "accent"), (1.0, "accent_hover")):
            color = contrast_safe_color(self._theme_tokens[key], surface, minimum=3.0)
            grad.setColorAt(position, QColor(color))
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

    @staticmethod
    def _text_font(points: int, weight=QFont.Weight.Normal) -> QFont:
        """Font for translated text: the UI language's own (Korean keeps Malgun Gothic)."""
        # A fixed base, not QFont() (the app font), so the hinting and style
        # strategy stay the same before and after the saved font applies.
        families = ui_text_families()
        font = QFont(families[0], points, weight)
        font.setFamilies(families)
        return font

    def _paint(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        tokens = self._theme_tokens
        background = QPainterPath()
        background.addRoundedRect(QRectF(0, 0, self.W, self.H), self.RADIUS, self.RADIUS)
        painter.fillPath(background, parse_css_color(tokens["floating_bg"]))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(parse_css_color(tokens["border"]), 1.0))
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.W - 1, self.H - 1), self.RADIUS, self.RADIUS)

        if not self._icon.isNull():
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(28, 31, 64, 64, self._icon)
        painter.setPen(parse_css_color(tokens["text_primary"]))
        painter.setFont(QFont(DEFAULT_UI_FONT, 22, QFont.Weight.DemiBold))
        painter.drawText(
            QRectF(108, 32, self.W - 136, 40),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            APP_NAME,
        )
        painter.setPen(parse_css_color(tokens["text_muted"]))
        painter.setFont(QFont(DEFAULT_UI_FONT, 9))
        painter.drawText(
            QRectF(110, 74, self.W - 138, 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            APP_VERSION_DISPLAY,
        )

        painter.setPen(QPen(parse_css_color(tokens["border_soft"]), 1.0))
        painter.drawLine(28, 114, self.W - 28, 114)

        painter.setFont(self._text_font(14, QFont.Weight.DemiBold))
        painter.setPen(parse_css_color(tokens["text_primary"]))
        metrics = QFontMetrics(painter.font())
        headline = metrics.elidedText(self._headline_text, Qt.TextElideMode.ElideRight, self.W - 56)
        painter.drawText(
            QRectF(28, 133, self.W - 56, 30),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            headline,
        )

        painter.setPen(parse_css_color(tokens["text_secondary"]))
        painter.setFont(self._text_font(10))
        status = QFontMetrics(painter.font()).elidedText(
            self._status_text, Qt.TextElideMode.ElideRight, self.W - 56
        )
        painter.drawText(
            QRectF(28, 170, self.W - 56, 24),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            status,
        )

        painter.setPen(parse_css_color(tokens["text_muted"]))
        painter.setFont(QFont(DEFAULT_UI_FONT, 10, QFont.Weight.DemiBold))
        painter.drawText(
            QRectF(28, 205, self.W - 56, 20),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{self._display_progress_percent()}%",
        )

        bar_x, bar_y, bar_w, bar_h = 28, 235, self.W - 56, 4
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(parse_css_color(tokens["border"]))
        painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 2, 2)
        if self._progress_anim > 0:
            painter.setBrush(self._make_accent_grad(bar_x, bar_w))
            painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_w * self._progress_anim, bar_h), 2, 2)
