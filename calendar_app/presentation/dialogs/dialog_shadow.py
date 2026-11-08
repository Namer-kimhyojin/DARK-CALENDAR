# -*- coding: utf-8 -*-
"""A noninteractive outer shadow that leaves each dialog's client layout intact."""

from math import ceil
import weakref

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QRegion
from PyQt6.QtWidgets import QDialog, QWidget

from calendar_app.shared.app_lifecycle import is_app_exiting

_SPREAD = 28
_OFFSET_Y = 0
_BOTTOM_MARGIN = _SPREAD
_MAX_BUFFER_BYTES = 64 * 1024 * 1024


def _shadow_buffer_fits(width: int, height: int, ratio: float) -> bool:
    """Bound the tool's ARGB backing allocation before creating/resizing it."""
    try:
        physical_width, physical_height = ceil(width * ratio), ceil(height * ratio)
    except (TypeError, ValueError, OverflowError):
        return False
    return (
        physical_width > 0
        and physical_height > 0
        and physical_width * physical_height * 4 <= _MAX_BUFFER_BYTES
    )


class _DialogShadowSurface(QWidget):
    """An owned tool surface paints only outside its owner's window rectangle."""

    def __init__(self, dialog):
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.NoDropShadowWindowHint
        )
        super().__init__(dialog, flags)
        self.setObjectName("CommonDialogShadow")
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.radius = 12
        self.dark = False
        self.setStyleSheet("QWidget#CommonDialogShadow { background: transparent; border: none; }")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        owner_rect = QRectF(
            _SPREAD,
            _SPREAD,
            max(0, self.width() - 2 * _SPREAD),
            max(0, self.height() - _SPREAD - _BOTTOM_MARGIN),
        )
        cast = owner_rect.translated(0, _OFFSET_Y)
        # Paint the perimeter only, rather than repeatedly filling the client's
        # much larger reading area before clearing it again.
        painter.setClipRegion(QRegion(self.rect()).subtracted(QRegion(owner_rect.toRect())))
        strength = 36 if self.dark else 28
        for spread in range(_SPREAD, 0, -1):
            alpha = round(strength * (1 - spread / (_SPREAD + 1)) ** 2)
            if alpha:
                painter.setBrush(QColor(3, 8, 20, alpha))
                painter.drawRoundedRect(
                    cast.adjusted(-spread, -spread, spread, spread),
                    self.radius + spread,
                    self.radius + spread,
                )
        # A black shadow alone disappears against an equally black desktop.
        # A narrow neutral halo makes each edge readable without tinting text.
        edge = QColor(Qt.GlobalColor.white if self.dark else Qt.GlobalColor.black)
        edge.setAlpha(88 if self.dark else 52)
        painter.setPen(QPen(edge, 2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(cast.adjusted(-1, -1, 1, 1), self.radius + 1, self.radius + 1)
        # The tool is above its owner on Windows. Clear the entire owner rect,
        # including its corners, so no text, controls or existing alpha changes.
        painter.setClipping(False)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(owner_rect, Qt.GlobalColor.transparent)


class _DialogShadowController(QObject):
    def __init__(self, dialog, *, settings=None):
        super().__init__(dialog)
        self._dialog_ref = weakref.ref(dialog)
        self._settings = settings
        self.surface = _DialogShadowSurface(dialog)
        dialog.installEventFilter(self)
        self.refresh_style(settings=settings)
        self.sync_geometry()

    def refresh_style(self, *, settings=None):
        if settings is not None:
            self._settings = settings
        dialog = self._dialog_ref()
        if (
            dialog is None
            or sip.isdeleted(dialog)
            or sip.isdeleted(self.surface)
            or is_app_exiting()
        ):
            return
        from calendar_app.presentation.dialogs.dialog_styles import (
            _dialog_settings,
            get_dialog_metric_tokens,
            get_dialog_theme_tokens,
        )

        profile = _dialog_settings(dialog, self._settings)
        tokens = get_dialog_theme_tokens(settings=profile)
        metrics = get_dialog_metric_tokens(settings=profile)
        self.surface.radius = max(0, int(metrics["group_radius"]))
        self.surface.dark = QColor(tokens["base_hex"]).lightnessF() < 0.5
        self.surface.update()

    def sync_geometry(self):
        dialog = self._dialog_ref()
        if (
            dialog is None
            or sip.isdeleted(dialog)
            or sip.isdeleted(self.surface)
            or is_app_exiting()
        ):
            return
        if not dialog.isVisible() or dialog.isMinimized() or not dialog.isWindow():
            self.surface.hide()
            return
        geometry = dialog.geometry()
        target = geometry.adjusted(-_SPREAD, -_SPREAD, _SPREAD, _BOTTOM_MARGIN)
        if not _shadow_buffer_fits(target.width(), target.height(), dialog.devicePixelRatioF()):
            self.surface.hide()
            return
        resized = self.surface.size() != target.size()
        if self.surface.geometry() != target:
            self.surface.setGeometry(target)
        if not self.surface.isVisible():
            # ShowWithoutActivating + WindowDoesNotAcceptFocus preserve the
            # modal's focus; the tool has no global AlwaysOnTop hint.
            self.surface.show()
        if resized:
            self.surface.update()

    def eventFilter(self, watched, event):
        reference = getattr(self, "_dialog_ref", None)
        surface = getattr(self, "surface", None)
        if reference is None or surface is None or is_app_exiting():
            return False
        dialog = reference()
        if dialog is None or sip.isdeleted(dialog) or sip.isdeleted(surface):
            return False
        kind = event.type()
        if kind == QEvent.Type.Hide:
            surface.hide()
        elif kind in (
            QEvent.Type.Show,
            QEvent.Type.Move,
            QEvent.Type.Resize,
            QEvent.Type.WindowStateChange,
            QEvent.Type.DevicePixelRatioChange,
        ):
            self.sync_geometry()
        elif kind in (QEvent.Type.PaletteChange, QEvent.Type.StyleChange):
            self.refresh_style()
        return False


def ensure_dialog_shadow(dialog, *, settings=None) -> bool:
    """Install one outer surface for eligible, independently shown dialogs only."""
    if (
        not isinstance(dialog, QDialog)
        or sip.isdeleted(dialog)
        or not dialog.isWindow()
        or dialog.property("dcSkipDialogChrome")
        or not dialog.property("dcCommonChrome")
        or dialog.windowType() in (Qt.WindowType.Popup, Qt.WindowType.ToolTip)
        or is_app_exiting()
    ):
        return False
    controller = getattr(dialog, "_dc_dialog_shadow_controller", None)
    if controller is None:
        controller = _DialogShadowController(dialog, settings=settings)
        dialog._dc_dialog_shadow_controller = controller
    else:
        controller.refresh_style(settings=settings)
        controller.sync_geometry()
    return True
