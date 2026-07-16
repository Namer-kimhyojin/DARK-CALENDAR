# -*- coding: utf-8 -*-
"""Google Calendar style color swatch widget.

Displays a horizontal row of 12 circular color buttons (11 GCal colors + "none").
Clicking a swatch selects it and shows a white check mark, matching Google Calendar UX.
"""

from PyQt6.QtCore import QEventLoop, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QPushButton, QSizePolicy, QWidget

from calendar_app.presentation.dialogs.dialog_styles import (
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)
from calendar_app.shared.google_color_palette import get_google_event_palette
from calendar_app.shared.theme_snapshot import build_shape_tokens

# Korean names for the 11 GCal palette entries
_KR_NAMES = {
    "1": "라벤더",
    "2": "세이지",
    "3": "포도",
    "4": "플라밍고",
    "5": "바나나",
    "6": "탄저린",
    "7": "피콕",
    "8": "그래파이트",
    "9": "블루베리",
    "10": "바질",
    "11": "토마토",
}


def _resolve_color_swatch_inputs(
    tokens: dict | None = None,
    metrics: dict | None = None,
    shape: dict | None = None,
) -> tuple[dict, dict, dict]:
    resolved_tokens = dict(get_dialog_theme_tokens())
    if tokens:
        resolved_tokens.update(tokens)

    resolved_metrics = dict(get_dialog_metric_tokens(apply_overrides=True))
    if metrics:
        resolved_metrics.update(metrics)

    resolved_shape = dict(build_shape_tokens())
    if shape:
        resolved_shape.update(shape)

    return resolved_tokens, resolved_metrics, resolved_shape


def _color_swatch_button_shell_stylesheet() -> str:
    return (
        "QPushButton {"
        " background: transparent;"
        " border: none;"
        " min-width: 0px;"
        " padding: 0px;"
        " margin: 0px;"
        "}"
    )


def _color_swatch_theme_bundle(
    tokens: dict | None = None,
    metrics: dict | None = None,
    shape: dict | None = None,
) -> dict[str, object]:
    resolved_tokens, resolved_metrics, resolved_shape = _resolve_color_swatch_inputs(
        tokens=tokens,
        metrics=metrics,
        shape=shape,
    )
    popup_bg = resolved_tokens.get("surface_alt", resolved_tokens.get("surface_bg"))
    popup_border = resolved_tokens.get("accent_soft_border", resolved_tokens.get("border"))
    none_fill = resolved_tokens.get("surface_item", popup_bg)
    none_border = resolved_tokens.get("border", popup_border)
    none_ring = resolved_tokens.get("accent", resolved_tokens.get("text_secondary"))
    none_slash = resolved_tokens.get("danger_hex", resolved_tokens.get("text_primary"))
    check_color = resolved_tokens.get("text_primary", resolved_tokens.get("text_secondary"))
    return {
        "button_shell": _color_swatch_button_shell_stylesheet(),
        "popup_bg": popup_bg,
        "popup_border": popup_border,
        "popup_radius": max(
            int(resolved_metrics.get("field_radius", 7)),
            int(resolved_shape.get("context_menu_radius", 10)),
        ),
        "popup_padding_x": max(8, int(resolved_metrics.get("field_padding_x", 10))),
        "popup_padding_y": max(6, int(resolved_metrics.get("field_padding_y", 4)) + 2),
        "swatch_padding_y": max(2, int(resolved_metrics.get("field_padding_y", 4))),
        "swatch_diameter": max(18, min(24, int(resolved_metrics.get("button_height", 34)) - 14)),
        "hover_ring": popup_border,
        "none_fill": none_fill,
        "none_border": none_border,
        "none_ring": none_ring,
        "none_slash": none_slash,
        "check_color": check_color,
    }


def _color_swatch_popup_stylesheet(theme: dict[str, object] | None = None) -> str:
    resolved = dict(theme or _color_swatch_theme_bundle())
    return (
        "ColorSwatchPopup {"
        f" background: {resolved['popup_bg']};"
        f" border: 1px solid {resolved['popup_border']};"
        f" border-radius: {int(resolved['popup_radius'])}px;"
        "}"
    )


class _SwatchButton(QPushButton):
    """Single circular color swatch button."""

    DIAMETER = 20  # circle diameter px (compact for dialog width safety)
    CHECK_THICKNESS = 2  # check-mark pen width
    BORDER_SELECTED = 2  # selection ring thickness
    BORDER_HOVER = 1

    def __init__(
        self,
        color_hex: str | None,
        tooltip: str,
        parent=None,
        theme: dict[str, object] | None = None,
    ):
        super().__init__(parent)
        self._color_hex = color_hex  # None → "색상 없음"
        self._selected = False
        self._hovered = False
        self._theme = dict(theme or _color_swatch_theme_bundle())
        self._diameter = int(self._theme.get("swatch_diameter", self.DIAMETER))

        self.setFixedSize(QSize(self._diameter + 4, self._diameter + 4))
        self.setToolTip(tooltip)
        self.setCheckable(False)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Transparent base — we paint everything ourselves
        self.setStyleSheet(str(self._theme["button_shell"]))

    # ── public API ────────────────────────────────────────────────────────
    @property
    def color_hex(self):
        return self._color_hex

    def set_selected(self, value: bool):
        if self._selected != value:
            self._selected = value
            self.update()

    def is_selected(self) -> bool:
        return self._selected

    def set_theme(self, theme: dict[str, object]):
        self._theme = dict(theme or self._theme)
        self._diameter = int(self._theme.get("swatch_diameter", self.DIAMETER))
        self.setFixedSize(QSize(self._diameter + 4, self._diameter + 4))
        self.update()

    # ── painting ──────────────────────────────────────────────────────────
    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        r = self._diameter / 2

        if self._color_hex:
            fill = QColor(self._color_hex)
        else:
            fill = QColor(str(self._theme["none_fill"]))

        # ── selection / hover ring ───────────────────────────────────────
        if self._selected:
            ring_color = fill if self._color_hex else QColor(str(self._theme["none_ring"]))
            ring_pen = QPen(ring_color, self.BORDER_SELECTED)
            painter.setPen(ring_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(
                int(cx - r - 4), int(cy - r - 4), int((r + 4) * 2), int((r + 4) * 2)
            )
        elif self._hovered:
            painter.setPen(QPen(QColor(str(self._theme["hover_ring"])), self.BORDER_HOVER))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(
                int(cx - r - 3), int(cy - r - 3), int((r + 3) * 2), int((r + 3) * 2)
            )

        # ── main circle ─────────────────────────────────────────────────
        if self._color_hex:
            painter.setPen(Qt.PenStyle.NoPen)
        else:
            painter.setPen(QPen(QColor(str(self._theme["none_border"])), 1))
        painter.setBrush(QBrush(fill))
        painter.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))

        # ── "no color" cross-out slash ───────────────────────────────────
        if not self._color_hex:
            slash_pen = QPen(QColor(str(self._theme["none_slash"])), 2)
            slash_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(slash_pen)
            offset = r * 0.55
            painter.drawLine(
                int(cx - offset),
                int(cy + offset),
                int(cx + offset),
                int(cy - offset),
            )

        # ── check mark ──────────────────────────────────────────────────
        if self._selected:
            check_color = (
                QColor(str(self._theme["check_color"]))
                if self._color_hex
                else QColor(str(self._theme["none_slash"]))
            )
            check_pen = QPen(check_color, self.CHECK_THICKNESS)
            check_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            check_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(check_pen)
            # Short tick at bottom-left, long stroke to top-right
            painter.drawLine(
                int(cx - r * 0.45),
                int(cy + 0),
                int(cx - r * 0.05),
                int(cy + r * 0.45),
            )
            painter.drawLine(
                int(cx - r * 0.05),
                int(cy + r * 0.45),
                int(cx + r * 0.5),
                int(cy - r * 0.4),
            )

        painter.end()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)


class GoogleColorSwatch(QWidget):
    """Horizontal row of circular color swatches (Google Calendar style).

    Emits ``color_changed(hex_or_empty)`` when the user picks a colour.
    ``hex_or_empty`` is a hex string like ``"#a4bdfc"`` or ``""`` for none.
    """

    color_changed = pyqtSignal(str)

    def __init__(
        self,
        parent=None,
        *,
        tokens: dict | None = None,
        metrics: dict | None = None,
        shape: dict | None = None,
    ):
        super().__init__(parent)
        self._selected_hex: str = ""  # "" = no color
        self._buttons: list[_SwatchButton] = []
        self._theme = _color_swatch_theme_bundle(tokens=tokens, metrics=metrics, shape=shape)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            0,
            int(self._theme.get("swatch_padding_y", 4)),
            0,
            int(self._theme.get("swatch_padding_y", 4)),
        )
        layout.setSpacing(1)

        # "No color" button first
        none_btn = _SwatchButton(None, "색상 없음")
        none_btn.clicked.connect(lambda: self._on_click(none_btn))
        none_btn.set_theme(self._theme)
        layout.addWidget(none_btn)
        self._buttons.append(none_btn)

        # 11 palette colours
        for entry in get_google_event_palette():
            name = _KR_NAMES.get(entry["id"], entry["name"])
            btn = _SwatchButton(entry["hex"], name)
            btn.clicked.connect(lambda _checked, b=btn: self._on_click(b))
            btn.set_theme(self._theme)
            layout.addWidget(btn)
            self._buttons.append(btn)

        layout.addStretch()
        self._sync_visuals()

    # ── public API ────────────────────────────────────────────────────────
    def selected_color(self) -> str:
        """Return current hex string (``""`` if none selected)."""
        return self._selected_hex

    def set_color(self, hex_color: str | None):
        """Set selection programmatically.  Pass ``None`` or ``""`` for no color."""
        self._selected_hex = (hex_color or "").lower().strip()
        self._sync_visuals()

    def apply_dialog_theme(
        self,
        *,
        tokens: dict | None = None,
        metrics: dict | None = None,
        shape: dict | None = None,
    ):
        self._theme = _color_swatch_theme_bundle(tokens=tokens, metrics=metrics, shape=shape)
        layout = self.layout()
        if isinstance(layout, QHBoxLayout):
            pad_y = int(self._theme.get("swatch_padding_y", 4))
            layout.setContentsMargins(0, pad_y, 0, pad_y)
        for btn in self._buttons:
            btn.set_theme(self._theme)
        self._sync_visuals()

    # ── internals ─────────────────────────────────────────────────────────
    def _on_click(self, btn: _SwatchButton):
        new_hex = btn.color_hex or ""
        # Clicking the already-selected colour deselects (toggles off)
        if new_hex == self._selected_hex:
            self._selected_hex = ""
        else:
            self._selected_hex = new_hex
        self._sync_visuals()
        self.color_changed.emit(self._selected_hex)

    def _sync_visuals(self):
        for btn in self._buttons:
            btn.set_selected((btn.color_hex or "") == self._selected_hex)


class ColorSwatchPopup(QFrame):
    """Floating popup that shows a GoogleColorSwatch and blocks until the user picks.

    Usage::

        result = ColorSwatchPopup.pick(parent_widget, current_hex)
        # result is a hex string like "#a4bdfc", "" for none, or None if cancelled

    The popup appears near the global cursor position, styled to match the dark
    context-menu theme of the app.
    """

    def __init__(
        self,
        current_hex: str | None,
        parent=None,
        *,
        tokens: dict | None = None,
        metrics: dict | None = None,
        shape: dict | None = None,
    ):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("ColorSwatchPopup")
        self._theme = _color_swatch_theme_bundle(tokens=tokens, metrics=metrics, shape=shape)
        self.setStyleSheet(_color_swatch_popup_stylesheet(self._theme))

        self._result: str | None = None  # None = cancelled
        self._loop = QEventLoop()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            int(self._theme.get("popup_padding_x", 10)),
            int(self._theme.get("popup_padding_y", 8)),
            int(self._theme.get("popup_padding_x", 10)),
            int(self._theme.get("popup_padding_y", 8)),
        )
        layout.setSpacing(0)

        self._swatch = GoogleColorSwatch(tokens=tokens, metrics=metrics, shape=shape)
        self._swatch.set_color(current_hex)
        self._swatch.color_changed.connect(self._on_picked)
        layout.addWidget(self._swatch)

        self.adjustSize()

    # ── public API ────────────────────────────────────────────────────────
    @staticmethod
    def pick(
        parent,
        current_hex: str | None = None,
        *,
        tokens: dict | None = None,
        metrics: dict | None = None,
        shape: dict | None = None,
    ) -> str | None:
        """Show popup near cursor and return chosen hex, ``""`` for none, ``None`` if cancelled."""
        popup = ColorSwatchPopup(
            current_hex,
            parent,
            tokens=tokens,
            metrics=metrics,
            shape=shape,
        )

        # Position: appear just below the current cursor position
        from PyQt6.QtGui import QCursor as _QCursor

        pos = _QCursor.pos()
        screen_obj = QApplication.screenAt(pos) or QApplication.primaryScreen()
        screen = screen_obj.availableGeometry()
        pw, ph = popup.width(), popup.height()
        x = min(pos.x(), screen.right() - pw - 4)
        y = pos.y() + 4
        if y + ph > screen.bottom():
            y = pos.y() - ph - 4
        popup.move(x, y)
        popup.show()
        popup._loop.exec()
        return popup._result

    # ── internals ─────────────────────────────────────────────────────────
    def _on_picked(self, hex_color: str):
        self._result = hex_color
        self._loop.quit()
        self.hide()

    def mouseReleaseEvent(self, event):
        # Click outside the swatch area dismisses without selecting
        super().mouseReleaseEvent(event)

    def hideEvent(self, event):
        # Ensure the loop always exits (e.g. focus lost / Escape)
        if self._loop.isRunning():
            self._loop.quit()
        super().hideEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._result = None
            self._loop.quit()
            self.hide()
        else:
            super().keyPressEvent(event)
