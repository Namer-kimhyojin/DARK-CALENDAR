# -*- coding: utf-8 -*-
"""Pin the top bar, or let it slide in from the top edge and push the panels down."""

from PyQt6.QtCore import QEvent, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QCursor, QPainter
from PyQt6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.runtime.keyboard_shortcuts import get_key
from calendar_app.shared.color_utils import hex_to_rgba, parse_css_color
from calendar_app.shared.icon_map import ICON, icon
from calendar_app.shared.theme_snapshot import build_theme_snapshot

TOP_BAR_AUTO_HIDE_KEY = "topbar_auto_hide"
_REVEAL_DELAY_MS = 120
_HIDE_DELAY_MS = 480
_HOVER_POLL_MS = 60
_EDGE_HEIGHT = 8
_HANDLE_HEIGHT = 4
# The gap between a pinned bar and the panels matches the gaps between panels.
_GAP_HEIGHT = 3
# A pull tab hanging from the handle; the top centre rarely holds panel buttons.
_FLOATING_PIN_WIDTH = 44
_FLOATING_PIN_HEIGHT = 18


class _ShelfButton(QToolButton):
    """Support Enter as well as the standard Space activation."""

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not event.isAutoRepeat():
                self.click()
            event.accept()
            return
        super().keyPressEvent(event)


class _RevealHandle(QWidget):
    """Thin strip that shows where the hidden top bar lives; a click opens it."""

    def __init__(self, shelf, owner):
        # An overlay on the window, not a layout row: a hidden bar leaves no gap.
        super().__init__(owner)
        self._shelf = shelf
        self.setObjectName("top_bar_reveal_handle")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(_HANDLE_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._shelf.reveal()
            event.accept()
            return
        super().mousePressEvent(event)


class TopBarShelf(QWidget):
    """Own the top bar's pinned/auto-hide state inside the main window's menu widget.

    The bar always keeps its layout slot, so revealing it moves the panels below it
    instead of drawing a translucent layer over them. A hidden bar takes no space: a
    thin handle drawn over the top edge marks it and a pull tab under it pins it again.
    """

    def __init__(self, owner, frame, banner=None):
        super().__init__(owner)
        self._owner = owner
        self._frame = frame
        self.auto_hide = owner.settings.value(TOP_BAR_AUTO_HIDE_KEY, False, type=bool)
        self._suppressed = bool(getattr(owner, "is_locked", False))
        self._revealed = False
        self._wait_for_edge_exit = False

        self._layout = QVBoxLayout(self)
        self._layout.setSpacing(3)
        self._layout.addWidget(frame)
        self.handle = _RevealHandle(self, owner)
        self.handle.hide()

        self.pin_button = _ShelfButton(frame)
        self.pin_button.setObjectName("top_bar_pin")
        self.pin_button.setCheckable(True)
        self.pin_button.setFixedSize(36, 36)
        self.pin_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.pin_button.setCursor(Qt.CursorShape.PointingHandCursor)
        frame.layout().addWidget(self.pin_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.floating_pin = _ShelfButton(owner)
        self.floating_pin.setObjectName("top_bar_floating_pin")
        self.floating_pin.setFixedSize(_FLOATING_PIN_WIDTH, _FLOATING_PIN_HEIGHT)
        self.floating_pin.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.floating_pin.setCursor(Qt.CursorShape.PointingHandCursor)
        self.floating_pin.hide()

        self._mouse_focus_buttons = [
            button
            for button in frame.findChildren(QAbstractButton)
            if button is not self.pin_button and button.focusPolicy() == Qt.FocusPolicy.StrongFocus
        ]

        if banner is not None:
            self._layout.addWidget(banner)

        self._hover_timer = QTimer(self, interval=_HOVER_POLL_MS)
        self._hover_timer.timeout.connect(self._check_hover)
        self._open_timer = QTimer(self, singleShot=True, interval=_REVEAL_DELAY_MS)
        self._open_timer.timeout.connect(self._open_on_hover)
        self._close_timer = QTimer(self, singleShot=True, interval=_HIDE_DELAY_MS)
        self._close_timer.timeout.connect(self._close_on_leave)
        self.pin_button.clicked.connect(self._on_pin_clicked)
        self.floating_pin.clicked.connect(lambda: self.set_auto_hide(False))
        for widget in (frame, owner):
            widget.installEventFilter(self)
        QApplication.instance().focusChanged.connect(self._on_focus_changed)
        self.refresh_theme()
        self._apply_mode()
        self._update_visibility()

    @property
    def available(self):
        return not self._suppressed

    @property
    def user_visible(self):
        """The bar can no longer be removed outright; it is pinned or auto-hidden."""
        return True

    def refresh_theme(self, snapshot=None):
        snapshot = snapshot or build_theme_snapshot(self._owner.settings)
        # On a translucent window an unpainted gap showed the desktop as a bright line.
        self._gap_color = parse_css_color(
            snapshot.ui_palette.get("separator_bg", "rgba(255, 255, 255, 10)")
        )
        self.update()
        palette = snapshot.ui_palette
        icon_color = parse_css_color(palette["text_primary"]).name()
        theme_color = snapshot.theme_color
        radius = snapshot.shape_tokens["panel_toolbar_button_radius"]
        for button, size in ((self.pin_button, 17), (self.floating_pin, 12)):
            button.setIcon(icon(ICON.ALWAYS_ON_TOP, color=icon_color))
            button.setIconSize(QSize(size, size))
            if button.icon().isNull():
                button.setText("▴")
        self.pin_button.setStyleSheet(
            f"""
            QToolButton#top_bar_pin {{
                padding: 0; border: 1px solid transparent; border-radius: {radius}px;
                background: transparent; color: {palette["text_primary"]};
            }}
            QToolButton#top_bar_pin:checked {{
                border-color: {hex_to_rgba(theme_color, 0.55)};
                background: {hex_to_rgba(theme_color, 0.16)};
            }}
            QToolButton#top_bar_pin:hover, QToolButton#top_bar_pin:focus {{
                border-color: {theme_color};
                background: {palette["control_bg_hover"]};
            }}
            """
        )
        # Opaque, so the corner pin stays legible over any calendar content.
        self.floating_pin.setStyleSheet(
            f"""
            QToolButton#top_bar_floating_pin {{
                padding: 0; border: 1px solid {hex_to_rgba(theme_color, 0.55)};
                border-top: none; border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px; color: {palette["text_primary"]};
                background: {snapshot.panel_palette["topbar_bg"]};
            }}
            QToolButton#top_bar_floating_pin:hover, QToolButton#top_bar_floating_pin:focus {{
                border-color: {theme_color};
            }}
            """
        )
        self.handle.setStyleSheet(
            f"""
            QWidget#top_bar_reveal_handle {{
                background: {hex_to_rgba(theme_color, 0.45)};
                border-radius: {_HANDLE_HEIGHT // 2}px;
            }}
            QWidget#top_bar_reveal_handle:hover {{ background: {theme_color}; }}
            """
        )

    def _apply_mode(self):
        shortcut = get_key("topbar")
        suffix = f" ({shortcut})" if shortcut else ""
        self.pin_button.setChecked(not self.auto_hide)
        if self.auto_hide:
            pin_label = t("topbar.pin", "상단 바 고정")
        else:
            pin_label = t("topbar.unpin", "상단 바 자동 숨기기")
        self.pin_button.setAccessibleName(pin_label)
        self.pin_button.setToolTip(pin_label + suffix)
        floating_label = t("topbar.pin", "상단 바 고정")
        self.floating_pin.setAccessibleName(floating_label)
        self.floating_pin.setToolTip(floating_label + suffix)
        self.handle.setToolTip(
            t("topbar.reveal_hint", "마우스를 올리거나 클릭하면 상단 바가 나타납니다.") + suffix
        )
        for button in self._mouse_focus_buttons:
            button.setFocusPolicy(
                Qt.FocusPolicy.TabFocus if self.auto_hide else Qt.FocusPolicy.StrongFocus
            )

    def _on_pin_clicked(self):
        if not self.auto_hide:
            # Clicked at the top edge: do not reopen until the pointer has left it.
            self._wait_for_edge_exit = True
        self.set_auto_hide(not self.auto_hide)

    def set_auto_hide(self, enabled):
        enabled = bool(enabled)
        if enabled == self.auto_hide:
            self._apply_mode()
            return
        self._stop_timers()
        self._revealed = False
        self.auto_hide = enabled
        self._owner.settings.setValue(TOP_BAR_AUTO_HIDE_KEY, enabled)
        if not enabled:
            self._wait_for_edge_exit = False
        self._apply_mode()
        self._update_visibility()

    def set_user_visible(self, visible):
        """Compatibility: showing pins the bar, hiding turns on auto-hide."""
        self.set_auto_hide(not visible)

    def set_suppressed(self, suppressed):
        self._suppressed = bool(suppressed)
        self._update_visibility()

    def toggle(self):
        if self.available:
            self.set_auto_hide(not self.auto_hide)

    def _update_visibility(self):
        allowed = self.available
        if not allowed:
            self._stop_timers()
            self._revealed = False
        frame_visible = allowed and (not self.auto_hide or self._revealed)
        hidden_chrome = allowed and self.auto_hide and not self._revealed
        self._frame.setVisible(frame_visible)
        self._layout.setContentsMargins(0, 0, 0, _GAP_HEIGHT if frame_visible else 0)
        self._update_floating_pin(hidden_chrome)
        self._sync_hover_timer()

    def _update_floating_pin(self, wanted=None):
        if wanted is None:
            wanted = self.available and self.auto_hide and not self._revealed
        if wanted and self.isVisible() and not self._owner.isMinimized():
            self._position_floating_pin()
            for widget in (self.handle, self.floating_pin):
                widget.show()
                widget.raise_()
        else:
            self.handle.hide()
            self.floating_pin.hide()

    def _position_floating_pin(self):
        area = self._owner.contentsRect()
        self.handle.setGeometry(area.x(), area.y(), area.width(), _HANDLE_HEIGHT)
        # Hangs right under the handle; _hover_target ignores it, so aiming at
        # the tab pins the bar instead of revealing it first.
        self.floating_pin.move(
            area.x() + (area.width() - _FLOATING_PIN_WIDTH) // 2,
            area.y() + _HANDLE_HEIGHT,
        )

    def reveal(self, *, focus=False):
        if not self._can_reveal():
            return
        self._revealed = True
        self._update_visibility()
        if focus:
            target = getattr(self._owner, "search_edit", self.pin_button)
            target.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._close_timer.start()

    def _stop_timers(self):
        self._hover_timer.stop()
        self._open_timer.stop()
        self._close_timer.stop()

    def _collapse(self):
        self._stop_timers()
        self._revealed = False
        self._update_visibility()

    def _can_reveal(self):
        return (
            self.auto_hide
            and self.available
            and self.isVisible()
            and not self._owner.isMinimized()
        )

    def _sync_hover_timer(self):
        if self._can_reveal() and not self._revealed:
            if not self._hover_timer.isActive():
                self._hover_timer.start()
        else:
            self._hover_timer.stop()
            self._open_timer.stop()

    def _cursor_at_top(self, global_pos):
        pos = self._owner.mapFromGlobal(global_pos)
        area = self._owner.contentsRect()
        return area.contains(pos) and pos.y() < area.top() + _EDGE_HEIGHT

    def _hover_target(self, global_pos):
        if (
            self._wait_for_edge_exit
            or QApplication.mouseButtons() != Qt.MouseButton.NoButton
            or QApplication.activePopupWidget() is not None
            or QApplication.activeModalWidget() is not None
        ):
            return False
        widget = QApplication.widgetAt(global_pos)
        return (
            widget is not None
            and widget is not self.floating_pin
            and widget.window() is self._owner
        )

    def _check_hover(self):
        # The calendar retains all pointer events, including at its top edge.
        if not self._can_reveal() or self._revealed:
            self._sync_hover_timer()
            return
        pos = QCursor.pos()
        if not self._cursor_at_top(pos):
            self._wait_for_edge_exit = False
            self._open_timer.stop()
        elif not self._hover_target(pos):
            self._open_timer.stop()
        elif not self._open_timer.isActive():
            self._open_timer.start()

    @staticmethod
    def _cursor_over(widget):
        return widget.isVisible() and widget.rect().contains(widget.mapFromGlobal(QCursor.pos()))

    def _owns_focus(self):
        widget = QApplication.focusWidget()
        return widget is not None and self._frame.isAncestorOf(widget)

    def _open_on_hover(self):
        pos = QCursor.pos()
        if self._cursor_at_top(pos) and self._hover_target(pos):
            self.reveal()

    def _close_on_leave(self):
        if not self._revealed or self._owns_focus() or self._cursor_over(self._frame):
            return
        if (
            QApplication.activePopupWidget() is not None
            or QApplication.mouseButtons() != Qt.MouseButton.NoButton
        ):
            self._close_timer.start()
            return
        self._collapse()

    def _on_focus_changed(self, _previous, _current):
        if self._revealed:
            self._close_timer.start()

    def eventFilter(self, watched, event):
        kind = event.type()
        if watched is self._frame and self.auto_hide and self._revealed:
            if kind == QEvent.Type.Enter:
                self._close_timer.stop()
            elif kind == QEvent.Type.Leave:
                self._close_timer.start()
        elif watched is self._owner:
            if kind == QEvent.Type.Resize and self.handle.isVisible():
                self._position_floating_pin()
            elif kind == QEvent.Type.WindowStateChange and self.auto_hide:
                if self._owner.isMinimized():
                    self._collapse()
                else:
                    self._update_visibility()
        return super().eventFilter(watched, event)

    def hideEvent(self, event):
        # Focus mode hides the menu widget; the corner pin goes with it.
        self._wait_for_edge_exit = False
        if self.auto_hide:
            self._stop_timers()
            self._revealed = False
            self._frame.hide()
        self.handle.hide()
        self.floating_pin.hide()
        super().hideEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._frame.isVisible():
            return
        painter = QPainter(self)
        painter.fillRect(
            0, self.height() - _GAP_HEIGHT, self.width(), _GAP_HEIGHT,
            getattr(self, "_gap_color", QColor(255, 255, 255, 10)),
        )
        painter.end()

    def showEvent(self, event):
        super().showEvent(event)
        self._update_visibility()
