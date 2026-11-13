# -*- coding: utf-8 -*-
"""A noninteractive outer shadow that leaves each dialog's client layout intact."""

from dataclasses import dataclass
from math import ceil

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QRegion
from PyQt6.QtWidgets import QDialog, QWidget

from calendar_app.presentation.dialogs.dialog_lifetime import (
    dialog_helper,
    keep_dialog_helper,
    owning_dialog,
)
from calendar_app.shared.app_lifecycle import is_app_exiting

_SPREAD = 28
_OFFSET_Y = 0
_BOTTOM_MARGIN = _SPREAD
_MAX_BUFFER_BYTES = 64 * 1024 * 1024
# Window corners are rounded by the same radius the shadow is cut with.
_MAX_CORNER_RADIUS = 20


@dataclass(frozen=True)
class ShadowStyle:
    """One elevation look. Layer alphas follow ``strength * (1 - d / S) ** exponent``."""

    color: tuple[int, int, int]
    strength: int
    exponent: float
    rim: tuple[int, int, int, int]


# A near-black halo reads as dirty on a pale surface, and a soft slate one
# vanishes on a dark desktop, so each mode gets its own look:
#   light - cool slate tint, wide and gentle (about a/105 at 3px, a/20 at 20px)
#   dark  - pure black, deeper and tighter (about a/190 at 3px, a/9 at 20px),
#           with a light rim so the edge still separates from a black backdrop.
SHADOW_STYLES = {
    "light": ShadowStyle(color=(22, 32, 56), strength=11, exponent=1.0, rim=(15, 23, 42, 40)),
    "dark": ShadowStyle(color=(0, 0, 0), strength=53, exponent=2.4, rim=(255, 255, 255, 70)),
}


def shadow_style(dark: bool) -> ShadowStyle:
    return SHADOW_STYLES["dark" if dark else "light"]


def rounded_window_region(width: int, height: int, radius: int) -> QRegion:
    """An exact rounded rectangle: two bars plus four corner ellipses."""
    r = max(0, min(int(radius), int(width) // 2, int(height) // 2))
    if r <= 0:
        return QRegion(0, 0, int(width), int(height))
    d = 2 * r
    region = QRegion(r, 0, width - d, height).united(QRegion(0, r, width, height - d))
    for x, y in ((0, 0), (width - d, 0), (0, height - d), (width - d, height - d)):
        region = region.united(QRegion(x, y, d, d, QRegion.RegionType.Ellipse))
    return region


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
        style = shadow_style(self.dark)
        # The window itself is rounded with this radius, so the shadow is cut
        # along the same curve and also fills the notch outside each corner.
        window_path = QPainterPath()
        window_path.addRoundedRect(owner_rect, self.radius, self.radius)
        # Paint the perimeter only, rather than repeatedly filling the client's
        # much larger reading area before clearing it again.
        outside = QPainterPath()
        outside.addRect(QRectF(self.rect()))
        outside.addPath(window_path)
        painter.setClipPath(outside)
        red, green, blue = style.color
        for spread in range(_SPREAD, 0, -1):
            alpha = round(style.strength * (1 - spread / (_SPREAD + 1)) ** style.exponent)
            if alpha:
                painter.setBrush(QColor(red, green, blue, alpha))
                painter.drawRoundedRect(
                    cast.adjusted(-spread, -spread, spread, spread),
                    self.radius + spread,
                    self.radius + spread,
                )
        # A shadow alone disappears against a desktop of the same lightness; a
        # narrow rim in the opposite tone keeps each edge readable.
        edge = QColor(*style.rim[:3])
        edge.setAlpha(style.rim[3])
        painter.setPen(QPen(edge, 2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(cast.adjusted(-1, -1, 1, 1), self.radius + 1, self.radius + 1)
        # The tool is above its owner on Windows. Clear the whole rounded window
        # so no text, controls or existing alpha changes.
        painter.setClipping(False)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillPath(window_path, Qt.GlobalColor.transparent)


class _DialogShadowController(QObject):
    def __init__(self, dialog, *, settings=None):
        super().__init__(dialog)
        self._settings = settings
        self.surface = _DialogShadowSurface(dialog)
        dialog.installEventFilter(self)
        self.refresh_style(settings=settings)
        self.sync_geometry()

    def refresh_style(self, *, settings=None):
        if settings is not None:
            self._settings = settings
        dialog = owning_dialog(self)
        if dialog is None or sip.isdeleted(self.surface) or is_app_exiting():
            return
        from calendar_app.presentation.dialogs.dialog_styles import (
            _dialog_settings,
            dialog_theme_tokens,
            get_dialog_metric_tokens,
        )

        profile = _dialog_settings(dialog, self._settings)
        tokens = dialog_theme_tokens(dialog, self._settings)
        metrics = get_dialog_metric_tokens(settings=profile)
        self.surface.radius = max(0, min(_MAX_CORNER_RADIUS, int(metrics["group_radius"])))
        self.surface.dark = QColor(tokens["base_hex"]).lightnessF() < 0.5
        self.surface.update()
        self._sync_window_mask(dialog)

    def _sync_window_mask(self, dialog):
        """Round the real window, not just the shadow around it."""
        radius = int(self.surface.radius)
        # A maximized or full-screen window fills the display edge to edge.
        square = radius <= 1 or dialog.isMaximized() or dialog.isFullScreen()
        key = None if square else (dialog.width(), dialog.height(), radius)
        if key == getattr(self, "_mask_key", None):
            return
        self._mask_key = key
        if key is None:
            dialog.clearMask()
        else:
            dialog.setMask(rounded_window_region(dialog.width(), dialog.height(), radius))

    def sync_geometry(self):
        dialog = owning_dialog(self)
        if dialog is None or sip.isdeleted(self.surface) or is_app_exiting():
            return
        if not dialog.isVisible() or dialog.isMinimized() or not dialog.isWindow():
            self.surface.hide()
            return
        self._sync_window_mask(dialog)
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
        surface = getattr(self, "surface", None)
        if surface is None or is_app_exiting():
            return False
        dialog = owning_dialog(self)
        if dialog is None or sip.isdeleted(surface):
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
    controller = dialog_helper(dialog, "shadow")
    if controller is None:
        controller = keep_dialog_helper(
            dialog, "shadow", _DialogShadowController(dialog, settings=settings)
        )
        # Python-created dialogs keep this attribute; existing callers read it.
        dialog._dc_dialog_shadow_controller = controller
    else:
        controller.refresh_style(settings=settings)
        controller.sync_geometry()
    return True
