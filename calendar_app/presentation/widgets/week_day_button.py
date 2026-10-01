# -*- coding: utf-8 -*-
"""A quiet week strip with separate weekday and date typography."""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PyQt6.QtWidgets import QToolButton

from calendar_app.presentation.widgets.panel_widget_style import css_to_qcolor


class ModernWeekDayButton(QToolButton):
    """Keep native button interaction while painting a restrained date tile."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._weekday = ""
        self._number = ""
        self._tokens = {}
        self._today = False
        self._selected = False
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def configure(self, weekday, number, tokens, *, today=False, selected=False):
        self._weekday, self._number = weekday, str(number)
        self._tokens = dict(tokens)
        self._today, self._selected = today, selected
        self.setText(f"{weekday}\n{number}")
        self.update()

    def _color(self, key, fallback, *, background=False):
        color = css_to_qcolor(self._tokens.get(key, fallback))
        opacity = self._tokens.get("_background_opacity" if background else "_text_opacity", 100)
        color.setAlphaF(color.alphaF() * max(0, min(100, float(opacity))) / 100)
        return color

    def _fit_font(self, scale, area, *, bold=False):
        font = QFont(self.font())
        font.setBold(bold)
        pixel_size = max(1, round(QFontMetricsF(font).height() * scale * 0.8))
        font.setPixelSize(min(pixel_size, max(1, int(area.height() * 0.8))))
        text = self._number if bold else self._weekday
        while font.pixelSize() > 1 and QFontMetricsF(font).horizontalAdvance(text) > area.width():
            font.setPixelSize(font.pixelSize() - 1)
        return font

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tile = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        accent = self._color("accent_deep", "#168d99")
        primary = self._color("text_primary", "#27344d")
        secondary = self._color("text_secondary", "#71809a")
        fill = QColor(Qt.GlobalColor.transparent)
        if self._selected:
            fill = self._color("hero_bg_strong", "rgba(34,195,202,32)", background=True)
        elif self.underMouse() or self.isDown():
            fill = self._color("button_hover", "rgba(128,144,168,18)", background=True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(tile, 8, 8)
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(accent, 1.5))
            painter.drawRoundedRect(tile.adjusted(1, 1, -1, -1), 7, 7)

        weekday_area = QRectF(3, 4, max(1, self.width() - 6), max(1, self.height() * 0.31))
        number_area = QRectF(
            3, self.height() * 0.35, max(1, self.width() - 6), max(1, self.height() * 0.48)
        )
        painter.setFont(self._fit_font(0.82, weekday_area))
        painter.setPen(accent if self._selected else secondary)
        painter.drawText(weekday_area, Qt.AlignmentFlag.AlignCenter, self._weekday)
        painter.setFont(self._fit_font(1.35, number_area, bold=True))
        painter.setPen(accent if self._selected else primary)
        painter.drawText(number_area, Qt.AlignmentFlag.AlignCenter, self._number)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        if self._today:
            painter.drawEllipse(QRectF((self.width() - 3) / 2, self.height() - 7, 3, 3))
        if self._selected:
            line_width = min(18, max(6, self.width() * 0.4))
            painter.drawRoundedRect(
                QRectF((self.width() - line_width) / 2, self.height() - 2, line_width, 2), 1, 1
            )
