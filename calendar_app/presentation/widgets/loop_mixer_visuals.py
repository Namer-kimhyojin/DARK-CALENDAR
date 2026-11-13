# -*- coding: utf-8 -*-
"""Painted transport and output displays for the loop mixer."""

from bisect import bisect_right

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QSizePolicy, QWidget

from calendar_app.infrastructure.i18n import t
from calendar_app.shared.color_utils import parse_css_color


def _with_opacity(color, opacity):
    tinted = QColor(color)
    tinted.setAlphaF(opacity)
    return tinted


class BeatTimeline(QWidget):
    """Four beats per bar, with a taller downbeat and a moving playhead."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        label = t("loop_mixer.beat_timeline", "루프 마디와 박자 진행")
        self.setAccessibleName(label)
        self.setToolTip(label)
        self._playback = (4, 0.0, "idle")
        self._accent = self.palette().highlight().color()
        self._recording = self._accent
        self._neutral = self.palette().text().color()

    def minimumSizeHint(self):  # noqa: N802
        return QSize(80, 18)

    def sizeHint(self):  # noqa: N802
        return QSize(260, 24)

    def set_theme(self, tokens):
        self._accent = parse_css_color(tokens["accent"])
        self._recording = parse_css_color(tokens["danger_hex"])
        self._neutral = parse_css_color(tokens["text_primary"])
        self.update()

    def set_playback(self, bars, fraction, mode):
        playback = (bars, max(0.0, min(1.0, fraction)) if mode != "idle" else 0.0, mode)
        if self._playback != playback:
            self._playback = playback
            self.update()

    def paintEvent(self, event):  # noqa: N802
        del event
        bars, fraction, mode = self._playback
        beats_per_bar = 4
        beats = bars * beats_per_bar
        margin = 3
        beat_width = (self.width() - 2 * margin) / (beats + 0.65 * (bars - 1))
        bar_width = (beats_per_bar + 0.65) * beat_width
        gap = min(4.0, 0.25 * beat_width)
        position = fraction * beats
        active = min(beats - 1, int(position)) if mode != "idle" else -1
        accent = self._recording if mode == "recording" else self._accent
        elapsed = _with_opacity(accent, 0.55)
        downbeat = _with_opacity(self._neutral, 0.30)
        inactive = _with_opacity(self._neutral, 0.13)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        center = self.height() * 0.60
        for index in range(beats):
            bar, beat = divmod(index, beats_per_bar)
            x = margin + bar * bar_width + beat * beat_width
            height = 12 if beat == 0 or index == active else 8
            color = downbeat if beat == 0 else inactive
            if index < active:
                color = elapsed
            elif index == active:
                color = accent
            rect = QRectF(x, center - height / 2, beat_width - gap, height)
            painter.setBrush(color)
            painter.drawRoundedRect(rect, 2, 2)
            if index == active:
                playhead = x + (position - active) * (beat_width - gap)
                painter.fillRect(QRectF(playhead - 1, 1, 2, center - 2), accent)


# PCM amplitude thresholds for a compact, roughly logarithmic peak scale.
_PEAK_BANDS = (0.01, 0.018, 0.032, 0.056, 0.10, 0.18, 0.25, 0.35, 0.50, 0.63, 0.79, 0.95)


class StereoMeter(QWidget):
    """Two independent peak meters for the left and right master output."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        label = t("loop_mixer.output_level", "출력 음량 표시")
        self.setAccessibleName(label)
        self.setToolTip(label)
        self._bands = (0, 0)
        self._text = self.palette().text().color()
        accent = self.palette().highlight().color()
        self._colors = (accent, accent, accent)

    def minimumSizeHint(self):  # noqa: N802
        font = self.fontMetrics()
        return QSize(72 + font.horizontalAdvance("R"), max(32, 2 * font.height() + 4))

    def sizeHint(self):  # noqa: N802
        return self.minimumSizeHint().expandedTo(QSize(132, 36))

    def set_theme(self, tokens):
        self._text = parse_css_color(tokens["text_secondary"])
        self._colors = tuple(
            parse_css_color(tokens[role]) for role in ("success_hex", "warning_hex", "danger_hex")
        )
        self.update()

    def set_levels(self, levels):
        left, right = levels
        bands = tuple(bisect_right(_PEAK_BANDS, peak) for peak in (left, right))
        if self._bands != bands:
            self._bands = bands
            self.update()

    def paintEvent(self, event):  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text_width = max(self.fontMetrics().horizontalAdvance(channel) for channel in ("L", "R"))
        start = text_width + 7
        width = (self.width() - start) / len(_PEAK_BANDS)
        gap = min(2.0, width / 3)
        row_height = self.height() / 2
        inactive = _with_opacity(self._text, 0.16)
        success, warning, danger = self._colors
        for row, (label, lit) in enumerate(zip(("L", "R"), self._bands, strict=True)):
            y = row * row_height
            painter.setPen(self._text)
            painter.drawText(
                QRectF(0, y, text_width, row_height), Qt.AlignmentFlag.AlignCenter, label
            )
            painter.setPen(Qt.PenStyle.NoPen)
            for index, threshold in enumerate(_PEAK_BANDS):
                color = danger if threshold >= 0.95 else warning if threshold >= 0.63 else success
                painter.setBrush(color if index < lit else inactive)
                rect = QRectF(start + index * width, y + row_height / 2 - 3, width - gap, 6)
                painter.drawRoundedRect(rect, 1, 1)
