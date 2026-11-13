# -*- coding: utf-8 -*-
"""Away-lock (idle lock) related action mixin."""

import logging
import os
import time

from PyQt6.QtCore import QDate, QLocale, QObject
from PyQt6.QtWidgets import QApplication, QDialog

from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.runtime import win32_input
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.shared.password_hash import hash_password, is_password_hash, verify_password
from calendar_app.shared.value_parsers import as_bool, as_int

_LOGGER = logging.getLogger(__name__)
_WIN32_WARNING_LOGGED = False


def _warn_win32_unavailable_once():
    global _WIN32_WARNING_LOGGED
    if not win32_input.AVAILABLE and not _WIN32_WARNING_LOGGED:
        _LOGGER.warning(
            "Win32 input APIs are unavailable. Away-lock input tracking uses reduced fallback mode."
        )
        _WIN32_WARNING_LOGGED = True


def _lock_screen_date_text(date: QDate, locale: QLocale | None = None) -> str:
    """Date line above the lock-screen clock, in the UI locale.

    Korean keeps the compact "2026.11.13 (금)"; other languages get Qt's own long
    date, which already includes the weekday in the right order and words.
    """
    # QLocale default is set by I18nManager._apply_qt_locale() at startup
    loc = locale if locale is not None else QLocale()
    if loc.language() == QLocale.Language.Korean:
        return loc.toString(date, "yyyy.MM.dd (ddd)")
    return loc.toString(date, QLocale.FormatType.LongFormat)


def _safe_get_last_input_tick():
    _warn_win32_unavailable_once()
    try:
        return win32_input.last_input_tick()
    except OSError:
        return None


def _safe_get_cursor_pos():
    _warn_win32_unavailable_once()
    try:
        return win32_input.cursor_pos()
    except OSError:
        return None


class _AwayForceUnlockFilter(QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self._owner = owner

    def eventFilter(self, watched, event):
        owner = self._owner
        if getattr(owner, "is_away_locked", False) and owner._is_force_unlock_key_event(event):
            owner._handle_force_unlock_request()
            return True
        return False


class _AwayAdminUnlockDialog(QDialog):
    def __init__(self, parent=None):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout

        from calendar_app.presentation.dialogs.dialog_styles import apply_common_dialog_style

        super().__init__(parent)
        apply_dialog_title(self, t("away_settings.method_password", "비밀번호로 해제"))
        self.setModal(True)
        apply_common_dialog_style(self, minimum_width=320, size=(380, 190))
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel(t("away_lock.placeholder_pw", "비밀번호를 입력하세요"))
        self.password_edit = QLineEdit(self)
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText(
            t("away_settings.placeholder_pw_input", "비밀번호 입력")
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_btn is not None:
            ok_btn.setObjectName("PrimaryBtn")
        if cancel_btn is not None:
            cancel_btn.setObjectName("SecondaryBtn")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(title)
        layout.addWidget(self.password_edit)
        layout.addWidget(buttons)

    def showEvent(self, event):
        super().showEvent(event)
        self.password_edit.setFocus()
        self.password_edit.selectAll()


class AwayLockMixin:
    AWAY_FORCE_UNLOCK_SHORTCUT = "Ctrl+Alt+Shift+F12"
    AWAY_ADMIN_HOTSPOT_SIZE = 44
    AWAY_ADMIN_HOLD_MS = 2000

    def _away_show_clock_enabled(self):
        raw = self.settings.value("away_show_clock", True)
        return as_bool(raw, default=True)

    def _away_default_message_html(self):
        return self.settings.value("away_default_message", t("away_lock.default_msg"))

    def _ensure_admin_hold_timer(self):
        if hasattr(self, "_away_admin_hold_timer"):
            return self._away_admin_hold_timer
        from PyQt6.QtCore import QTimer

        self._away_admin_hold_timer = QTimer(self)
        self._away_admin_hold_timer.setSingleShot(True)
        self._away_admin_hold_timer.timeout.connect(self._trigger_admin_unlock_dialog)
        return self._away_admin_hold_timer

    def _clear_admin_unlock_hold(self):
        timer = getattr(self, "_away_admin_hold_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()
        self._set_admin_hold_indicator(False)
        self._away_admin_hold_overlay = None

    def _set_admin_hold_indicator(self, active):
        overlay = getattr(self, "_away_admin_hold_overlay", None)
        if overlay is None:
            return
        indicator = overlay.get("admin_hint")
        if indicator is not None:
            indicator.setVisible(bool(active))

    def _is_admin_unlock_hotspot(self, pos):
        if pos is None:
            return False
        try:
            x = int(pos.x())
            y = int(pos.y())
        except Exception:
            return False
        size = int(self.AWAY_ADMIN_HOTSPOT_SIZE)
        return 0 <= x <= size and 0 <= y <= size

    def _begin_admin_unlock_hold(self, overlay, pos):
        if not getattr(self, "is_away_locked", False):
            return False
        if not self._is_admin_unlock_hotspot(pos):
            self._clear_admin_unlock_hold()
            return False
        self._away_admin_hold_overlay = overlay
        self._set_admin_hold_indicator(True)
        self._ensure_admin_hold_timer().start(int(self.AWAY_ADMIN_HOLD_MS))
        return True

    def _handle_admin_unlock_mouse_move(self, overlay, pos):
        if overlay is None or overlay is not getattr(self, "_away_admin_hold_overlay", None):
            return False
        if self._is_admin_unlock_hotspot(pos):
            return True
        self._clear_admin_unlock_hold()
        return False

    def _verify_away_password(self, password):
        """Check the lock password; upgrade a legacy plain-text value to a hash."""
        entered = str(password or "")
        stored = str(self.settings.value("away_password", "") or "")
        if not stored:
            return not entered
        if not verify_password(entered, stored):
            return False
        if not is_password_hash(stored):
            self.settings.setValue("away_password", hash_password(entered))
        return True

    def _handle_force_unlock_request(self):
        """Emergency key: never skip the password, only bring its input back."""
        if self._password_unlock_active():
            self._ensure_password_entry_ready(force_activate=True)
        else:
            self._do_away_unlock()

    def _prompt_admin_unlock_password(self, parent=None):
        dialog = _AwayAdminUnlockDialog(parent or self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        return self._verify_away_password(dialog.password_edit.text())

    def _trigger_admin_unlock_dialog(self):
        overlay = getattr(self, "_away_admin_hold_overlay", None)
        self._clear_admin_unlock_hold()
        if not getattr(self, "is_away_locked", False):
            return
        if not self._password_unlock_active():
            self._do_away_unlock()
            return
        parent = overlay.get("window") if overlay else self
        if self._prompt_admin_unlock_password(parent=parent):
            self._do_away_unlock()

    def _clear_aux_away_overlays(self):
        self._clear_admin_unlock_hold()
        overlays = getattr(self, "_away_aux_overlays", [])
        for overlay in overlays:
            win = overlay.get("window")
            if win is not None:
                win.hide()
                win.deleteLater()
        self._away_aux_overlays = []

    def _current_away_overlay(self):
        for overlay in getattr(self, "_away_aux_overlays", []):
            if overlay.get("is_current_screen"):
                return overlay
        return None

    def _resolve_primary_away_overlay(self):
        overlays = [
            overlay
            for overlay in getattr(self, "_away_aux_overlays", [])
            if overlay.get("window") is not None
        ]
        if not overlays:
            return None

        active_window = QApplication.activeWindow()
        if active_window is not None:
            for overlay in overlays:
                if overlay.get("window") is active_window:
                    for item in overlays:
                        item["is_current_screen"] = item is overlay
                    return overlay

        try:
            cursor_pos = self.cursor().pos()
            screen = QApplication.screenAt(cursor_pos)
        except Exception:
            screen = None
        if screen is not None:
            for overlay in overlays:
                window = overlay.get("window")
                try:
                    if window is not None and window.screen() is screen:
                        for item in overlays:
                            item["is_current_screen"] = item is overlay
                        return overlay
                except Exception:
                    continue

        current = self._current_away_overlay()
        if current is not None:
            return current

        fallback = overlays[0]
        for item in overlays:
            item["is_current_screen"] = item is fallback
        return fallback

    def _password_unlock_active(self):
        return self.settings.value("away_unlock_method", "idle") == "password"

    def _password_focus_target(self):
        primary_overlay = self._resolve_primary_away_overlay()
        if primary_overlay is not None:
            return primary_overlay, primary_overlay.get("window"), primary_overlay.get("pw_edit")
        return None, None, getattr(self, "lock_pw_edit", None)

    def _request_focusable_window_activation(self, window):
        if window is None:
            return False
        try:
            from PyQt6.QtCore import Qt as _Qt2

            flags = window.windowFlags()
            if flags & _Qt2.WindowType.WindowDoesNotAcceptFocus:
                return False
            window.activateWindow()
            handle = window.windowHandle()
            if handle is None:
                return False
            handle.requestActivate()
            return True
        except Exception:
            return False

    def _set_password_inputs_enabled(self):
        password_mode = self._password_unlock_active()
        has_aux_overlays = bool(getattr(self, "_away_aux_overlays", []))

        for overlay in getattr(self, "_away_aux_overlays", []):
            edit = overlay.get("pw_edit")
            widget = overlay.get("pw_widget")
            is_primary = bool(overlay.get("is_current_screen", False))
            if widget is not None:
                widget.setVisible(password_mode and is_primary)
            if edit is not None:
                edit.setEnabled(password_mode and is_primary)
                edit.setReadOnly(not (password_mode and is_primary))
                if not is_primary:
                    edit.clear()

        if hasattr(self, "lock_pw_widget"):
            self.lock_pw_widget.setVisible(password_mode and not has_aux_overlays)
        if hasattr(self, "lock_pw_edit"):
            self.lock_pw_edit.setEnabled(password_mode and not has_aux_overlays)
            self.lock_pw_edit.setReadOnly(not (password_mode and not has_aux_overlays))
            if has_aux_overlays:
                self.lock_pw_edit.clear()

    @staticmethod
    def _show_overlay_fullscreen(window) -> None:
        """Full-screen an overlay; no-focus overlays must not be activated (Qt warns)."""
        from PyQt6.QtCore import Qt as _Qt2

        if window.windowFlags() & _Qt2.WindowType.WindowDoesNotAcceptFocus:
            # showFullScreen() calls activateWindow(), which Qt rejects for these windows.
            window.setWindowState(window.windowState() | _Qt2.WindowState.WindowFullScreen)
            window.show()
        else:
            window.showFullScreen()

    def _ensure_password_entry_ready(self, *, force_activate=False):
        if not getattr(self, "is_away_locked", False) or not self._password_unlock_active():
            return False

        self._set_password_inputs_enabled()
        _overlay, window, edit = self._password_focus_target()
        if edit is None:
            return False

        if window is not None:
            from PyQt6.QtCore import Qt as _Qt2

            flags = window.windowFlags()
            if flags & _Qt2.WindowType.WindowDoesNotAcceptFocus:
                flags &= ~_Qt2.WindowType.WindowDoesNotAcceptFocus
                window.setWindowFlags(flags)
                window.setAttribute(_Qt2.WidgetAttribute.WA_ShowWithoutActivating, False)
                window.showFullScreen()
            elif not window.isVisible():
                window.showFullScreen()
            window.raise_()
            if force_activate:
                self._request_focusable_window_activation(window)

        edit.setEnabled(True)
        edit.setReadOnly(False)
        edit.show()
        self._schedule_password_focus_pulse(window, edit, force_activate=force_activate)
        return True

    def _schedule_password_focus_pulse(self, window, edit, *, force_activate=False):
        if edit is None:
            return

        from PyQt6.QtCore import Qt as _Qt2
        from PyQt6.QtCore import QTimer

        def _focus_once():
            if not getattr(self, "is_away_locked", False) or not self._password_unlock_active():
                return
            try:
                if window is not None:
                    window.raise_()
                    if force_activate:
                        self._request_focusable_window_activation(window)
                edit.setFocus(_Qt2.FocusReason.ActiveWindowFocusReason)
                edit.activateWindow()
                edit.selectAll()
            except Exception:
                pass

        _focus_once()
        QTimer.singleShot(0, _focus_once)
        QTimer.singleShot(60, _focus_once)
        QTimer.singleShot(180, _focus_once)

    def _start_password_focus_watchdog(self):
        if not hasattr(self, "_away_password_focus_timer"):
            from PyQt6.QtCore import QTimer

            self._away_password_focus_timer = QTimer(self)
            self._away_password_focus_timer.timeout.connect(self._maintain_password_entry_focus)
        self._away_password_focus_timer.start(800)

    def _install_force_unlock_event_filter(self):
        from PyQt6.QtCore import QObject

        app = QApplication.instance()
        if app is None:
            return
        if not getattr(self, "_away_force_unlock_filter_installed", False):
            if not isinstance(getattr(self, "_away_force_unlock_filter", None), QObject):
                self._away_force_unlock_filter = _AwayForceUnlockFilter(self)
            app.installEventFilter(self._away_force_unlock_filter)
            self._away_force_unlock_filter_installed = True

    def _remove_force_unlock_event_filter(self):
        app = QApplication.instance()
        if app is None:
            self._away_force_unlock_filter_installed = False
            return
        if getattr(self, "_away_force_unlock_filter_installed", False):
            filter_obj = getattr(self, "_away_force_unlock_filter", None)
            if filter_obj is not None:
                app.removeEventFilter(filter_obj)
            self._away_force_unlock_filter_installed = False

    def _is_force_unlock_key_event(self, event):
        from PyQt6.QtCore import QEvent
        from PyQt6.QtCore import Qt as _Qt

        if event is None or event.type() != QEvent.Type.KeyPress:
            return False
        key = event.key()
        modifiers = event.modifiers()
        has_ctrl = bool(modifiers & _Qt.KeyboardModifier.ControlModifier)
        has_alt = bool(modifiers & _Qt.KeyboardModifier.AltModifier)
        has_shift = bool(modifiers & _Qt.KeyboardModifier.ShiftModifier)
        return key == _Qt.Key.Key_F12 and has_ctrl and has_alt and has_shift

    def _stop_password_focus_watchdog(self):
        if hasattr(self, "_away_password_focus_timer"):
            self._away_password_focus_timer.stop()

    def _maintain_password_entry_focus(self):
        if not getattr(self, "is_away_locked", False) or not self._password_unlock_active():
            self._stop_password_focus_watchdog()
            return

        from PyQt6.QtWidgets import QLineEdit

        _overlay, window, edit = self._password_focus_target()
        focus_widget = QApplication.focusWidget()
        has_valid_focus = (
            focus_widget is not None
            and focus_widget is edit
            and isinstance(focus_widget, QLineEdit)
            and focus_widget.isEnabled()
            and not focus_widget.isReadOnly()
        )
        force_activate = window is not None and QApplication.activeWindow() is not window
        if edit is None or not has_valid_focus or not edit.isEnabled() or edit.isReadOnly():
            self._ensure_password_entry_ready(force_activate=force_activate)

    def _build_aux_away_overlays(self):
        self._clear_aux_away_overlays()

        current_screen = None
        try:
            if self.windowHandle() is not None:
                current_screen = self.windowHandle().screen()
        except Exception:
            current_screen = None
        if current_screen is None:
            try:
                current_screen = QApplication.screenAt(self.frameGeometry().center())
            except Exception:
                current_screen = None
        if current_screen is None:
            current_screen = QApplication.primaryScreen()

        # Build top-level overlays for every connected monitor, including the
        # current one, so the primary screen also covers the full monitor area.
        screens = [s for s in QApplication.screens() if s is not None]

        from PyQt6.QtCore import Qt as _Qt
        from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

        overlays = []
        for screen in screens:
            if screen is None:
                continue

            win = QWidget(None)
            win.setWindowFlags(
                _Qt.WindowType.FramelessWindowHint
                | _Qt.WindowType.Window
                | _Qt.WindowType.WindowStaysOnTopHint
                | _Qt.WindowType.WindowDoesNotAcceptFocus
            )
            win.setAttribute(_Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            win.setGeometry(screen.geometry())

            # ALT+F4 등으로 오버레이 창이 닫히려 할 때:
            # - 비밀번호 모드: 완전 차단
            # - idle 모드: 전체 잠금 해제
            _main_ref = self

            def _overlay_close_event(event, _ref=_main_ref):
                event.ignore()  # Keep overlay window from being closed directly by Qt.
                if not getattr(_ref, "is_away_locked", False):
                    return
                unlock_method = _ref.settings.value("away_unlock_method", "idle")
                if unlock_method == "password":
                    return  # 비밀번호 모드에서는 ALT+F4 완전 차단
                _ref._do_away_unlock()

            win.closeEvent = _overlay_close_event

            bg_label = QLabel(win)
            bg_label.setScaledContents(True)
            bg_label.setGeometry(win.rect())
            bg_label.lower()

            lay = QVBoxLayout(win)
            lay.setAlignment(_Qt.AlignmentFlag.AlignCenter)
            lay.setContentsMargins(24, 50, 24, 50)
            lay.setSpacing(16)

            clock_lbl = QLabel()
            clock_lbl.setAlignment(_Qt.AlignmentFlag.AlignCenter)
            clock_lbl.setStyleSheet("color: white; font-weight: bold;")
            lay.addWidget(clock_lbl)

            msg_lbl = QLabel()
            msg_lbl.setAlignment(_Qt.AlignmentFlag.AlignCenter)
            msg_lbl.setWordWrap(True)
            msg_lbl.setTextFormat(_Qt.TextFormat.RichText)
            msg_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            msg_lbl.setMinimumWidth(320)
            lay.addWidget(msg_lbl)

            admin_hint = QLabel(win)
            admin_hint.setText(t("away_lock.secondary_screen_hint", "보조 잠금 화면"))
            admin_hint.move(10, 10)
            admin_hint.setStyleSheet(
                "QLabel { background: rgba(0, 0, 0, 0.72); color: white; "
                "border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; "
                "padding: 4px 8px; font-size: 10pt; }"
            )
            admin_hint.hide()

            from PyQt6.QtWidgets import (
                QHBoxLayout as _QHBoxLayout,
            )
            from PyQt6.QtWidgets import (
                QLineEdit as _QLineEdit,
            )
            from PyQt6.QtWidgets import (
                QPushButton as _QPushButton,
            )
            from PyQt6.QtWidgets import (
                QWidget as _QWidget,
            )

            _pw_widget = _QWidget()
            _pw_h_lay = _QHBoxLayout(_pw_widget)
            _pw_h_lay.setContentsMargins(0, 0, 0, 0)
            _pw_h_lay.setSpacing(8)

            _pw_edit = _QLineEdit()
            _pw_edit.setEchoMode(_QLineEdit.EchoMode.Password)
            _pw_edit.setPlaceholderText(t("away_lock.placeholder_pw"))
            _pw_edit.setAccessibleName(t("away_lock.placeholder_pw"))
            _pw_edit.setAccessibleDescription(t("away_lock.placeholder_pw"))
            _pw_edit.setMinimumWidth(240)
            _pw_edit.setMaximumWidth(360)
            _pw_edit.setStyleSheet(
                "QLineEdit { background: rgba(255,255,255,0.15); color: white; "
                "border: 1px solid rgba(255,255,255,0.3); border-radius: 4px; "
                "padding: 6px 10px; font-size: 14pt; }"
                "QLineEdit:focus { border: 1px solid #4da6ff; }"
            )
            _pw_h_lay.addWidget(_pw_edit)

            _pw_btn = _QPushButton(t("away_lock.unlock_btn"))
            _pw_btn.setAccessibleName(t("away_lock.unlock_btn"))
            _pw_btn.setAccessibleDescription(t("away_lock.unlock_btn"))
            _pw_btn.setStyleSheet(
                "QPushButton { background: #4da6ff; color: white; border-radius: 4px; "
                "padding: 6px 18px; font-size: 14pt; font-weight: bold; border: none; }"
                "QPushButton:hover { background: #3d8fe0; }"
                "QPushButton:pressed { background: #2d7fca; }"
            )
            _pw_h_lay.addWidget(_pw_btn)

            _main_win = self
            _pw_btn.clicked.connect(
                lambda checked=False, e=_pw_edit, mw=_main_win: mw._perform_away_unlock(e)
            )
            _pw_edit.returnPressed.connect(
                lambda e=_pw_edit, mw=_main_win: mw._perform_away_unlock(e)
            )

            _pw_widget.hide()
            lay.addWidget(_pw_widget, alignment=_Qt.AlignmentFlag.AlignCenter)

            overlay_ref = {
                "window": win,
                "bg_label": bg_label,
                "clock_label": clock_lbl,
                "msg_label": msg_lbl,
                "pw_widget": _pw_widget,
                "pw_edit": _pw_edit,
                "admin_hint": admin_hint,
                "is_current_screen": screen == current_screen,
            }

            def _bind_admin_unlock_mouse_handlers(widget, overlay):
                if widget is None:
                    return

                def _mouse_press(
                    event, _overlay=overlay, _base=getattr(widget, "mousePressEvent", None)
                ):
                    if (
                        event.button() == _Qt.MouseButton.LeftButton
                        and self._begin_admin_unlock_hold(_overlay, event.position().toPoint())
                    ):
                        event.accept()
                        return
                    if callable(_base):
                        _base(event)

                def _mouse_move(
                    event, _overlay=overlay, _base=getattr(widget, "mouseMoveEvent", None)
                ):
                    if self._handle_admin_unlock_mouse_move(_overlay, event.position().toPoint()):
                        event.accept()
                        return
                    if callable(_base):
                        _base(event)

                def _mouse_release(event, _base=getattr(widget, "mouseReleaseEvent", None)):
                    self._clear_admin_unlock_hold()
                    if callable(_base):
                        _base(event)

                widget.setMouseTracking(True)
                widget.mousePressEvent = _mouse_press
                widget.mouseMoveEvent = _mouse_move
                widget.mouseReleaseEvent = _mouse_release

            _bind_admin_unlock_mouse_handlers(win, overlay_ref)
            _bind_admin_unlock_mouse_handlers(bg_label, overlay_ref)
            _bind_admin_unlock_mouse_handlers(clock_lbl, overlay_ref)
            _bind_admin_unlock_mouse_handlers(msg_lbl, overlay_ref)

            # 강제 해제 단축키 설치 (비밀번호 모드 포함)
            self._install_force_unlock_shortcut(win)
            self._install_force_unlock_shortcut(_pw_widget)
            self._install_force_unlock_shortcut(_pw_edit)

            overlays.append(overlay_ref)

        self._away_aux_overlays = overlays

    def _restore_window_after_away_lock(self):
        prev_opacity = getattr(self, "_away_prev_window_opacity", None)
        if prev_opacity is not None:
            try:
                self.setWindowOpacity(float(prev_opacity))
            except Exception:
                self.setWindowOpacity(1.0)
            self._away_prev_window_opacity = None

        if not getattr(self, "_away_forced_fullscreen", False):
            return

        self.showNormal()
        if getattr(self, "_away_prev_was_maximized", False):
            self.showMaximized()
        else:
            prev_geometry = getattr(self, "_away_prev_geometry", None)
            if prev_geometry is not None:
                self.setGeometry(prev_geometry)
        self._away_forced_fullscreen = False

    def toggle_idle_lock(self, is_idle, manual=False):
        import logging as _log

        _logger = _log.getLogger(__name__)
        _logger.info(
            "[toggle_idle_lock] is_idle=%s manual=%s is_away_locked=%s",
            is_idle,
            manual,
            getattr(self, "is_away_locked", False),
        )
        if is_idle:
            if getattr(self, "is_away_locked", False):
                return
            try:
                self._away_prev_window_opacity = self.windowOpacity()
            except Exception:
                self._away_prev_window_opacity = 1.0
            self.setWindowOpacity(1.0)
            self._away_prev_geometry = self.geometry()
            self._away_prev_was_maximized = self.isMaximized()
            # aux 오버레이가 모든 모니터를 덮으므로 메인 창은 showFullScreen()을 쓰지 않는다.
            # WindowStaysOnBottomHint|Tool 창은 showFullScreen 뒤 showNormal로 돌아올 때
            # WA_TranslucentBackground 렌더링이 깨질 수 있다.
            self._away_forced_fullscreen = False
            self.is_away_locked = True
            self._build_aux_away_overlays()
            self._install_force_unlock_event_filter()
            self.refresh_idle_lock_ui()
            self.lock_frame.hide()
            _unlock_method_on_lock = self.settings.value("away_unlock_method", "idle")
            _password_mode = _unlock_method_on_lock == "password"
            for overlay in getattr(self, "_away_aux_overlays", []):
                win = overlay.get("window")
                if win is not None:
                    win.raise_()
                    self._show_overlay_fullscreen(win)

            _logger.info(
                "[LOCK] locked. password_mode=%s overlay_count=%s manual=%s",
                _password_mode,
                len(getattr(self, "_away_aux_overlays", [])),
                manual,
            )
            # idle 해제 모드: 잠금 직후의 입력으로 바로 풀리지 않도록 해제 감지를 조금 늦게 설치
            if not _password_mode:
                from PyQt6.QtCore import QTimer as _QT

                _QT.singleShot(300, self._install_overlay_unlock_filters)

            # 비밀번호 해제 모드: 현재 화면의 비밀번호 입력칸에 포커스를 강제로 맞춘다.
            if _password_mode:
                from PyQt6.QtCore import QTimer as _QTimer

                for _e in self._all_lock_pw_edits():
                    _e.clear()
                self._ensure_password_entry_ready(force_activate=True)
                self._start_password_focus_watchdog()
                _QTimer.singleShot(
                    150, lambda: self._ensure_password_entry_ready(force_activate=True)
                )
                _QTimer.singleShot(
                    900, lambda: self._ensure_password_entry_ready(force_activate=True)
                )
            else:
                self._stop_password_focus_watchdog()

            # 수동 잠금: 잠금 이후 "새 입력"이 있을 때만 해제되도록 기준값 저장
            self._manual_lock_active = bool(manual)
            self._manual_lock_input_tick = None
            if self._manual_lock_active:
                self._manual_lock_input_tick = _safe_get_last_input_tick()
                self._manual_lock_cursor_pos = _safe_get_cursor_pos()
                if self._manual_lock_input_tick is None:
                    # Fallback when last input tick cannot be queried.
                    self._last_manual_lock_time = time.time()
            else:
                self._last_manual_lock_time = None

            # alarm_worker도 잠금 상태로 맞춘다 (잠금 직후 idle 감지기가 바로 해제하지 않도록)
            if hasattr(self, "alarm_worker"):
                self.alarm_worker.is_idle = True
                self.alarm_worker.suppress_unlock = True  # idle_detector unlock emit 차단
                self.alarm_worker._last_cursor_pos = _safe_get_cursor_pos()

            # 잠금 화면 시계 갱신 타이머 시작 (시계 표시를 켠 경우)
            if self._away_show_clock_enabled():
                if not hasattr(self, "_lock_clock_timer"):
                    from PyQt6.QtCore import QTimer

                    self._lock_clock_timer = QTimer(self)
                    self._lock_clock_timer.timeout.connect(self._update_lock_clock)
                self._update_lock_clock()  # 즉시 1회 갱신
                self._lock_clock_timer.start(1000)
        else:
            if not getattr(self, "is_away_locked", False):
                return

            _logger.info(
                "[UNLOCK-ENTRY] manual=%s method=%s",
                getattr(self, "_manual_lock_active", False),
                self.settings.value("away_unlock_method", "idle"),
            )
            # 수동 잠금은 잠금 이후 새 입력이 있었을 때만 해제한다
            if getattr(self, "_manual_lock_active", False):
                lock_tick = getattr(self, "_manual_lock_input_tick", None)
                has_new_input = False
                if lock_tick is not None:
                    current_input_tick = _safe_get_last_input_tick()
                    if current_input_tick is not None:
                        # tick은 32비트 unsigned라 wrap-around를 고려
                        diff = (current_input_tick - lock_tick) & 0xFFFFFFFF
                        has_new_input = 0 < diff < 0x80000000
                else:
                    # 입력 tick을 읽지 못하면 잠금 후 경과 시간으로 판단
                    if hasattr(self, "_last_manual_lock_time"):
                        has_new_input = (time.time() - self._last_manual_lock_time) >= 2.0
                # 보조 감지: GetLastInputInfo가 마우스 이동을 놓치는 경우 커서 위치로 확인
                if not has_new_input:
                    lock_cursor = getattr(self, "_manual_lock_cursor_pos", None)
                    if lock_cursor is not None:
                        cur_pos = _safe_get_cursor_pos()
                        if cur_pos is not None and cur_pos != lock_cursor:
                            has_new_input = True
                            self._manual_lock_cursor_pos = cur_pos
                if not has_new_input:
                    _logger.info(
                        "[UNLOCK-MANUAL] final has_new_input=%s lock_tick=%s lock_cursor=%s",
                        has_new_input,
                        getattr(self, "_manual_lock_input_tick", None),
                        getattr(self, "_manual_lock_cursor_pos", None),
                    )
                    if hasattr(self, "alarm_worker"):
                        self.alarm_worker.is_idle = True
                    return

            unlock_method = self.settings.value("away_unlock_method", "idle")
            if unlock_method == "password":
                self._ensure_password_entry_ready(force_activate=True)
            else:
                self._do_away_unlock()

    def open_away_settings_dialog(self):
        from calendar_app.presentation.dialogs.away_settings_dialog import AwaySettingsDialog

        dlg = AwaySettingsDialog(self)
        if dlg.exec():
            # 변경된 자리비움 시간을 AlarmScheduler에 즉시 반영
            if hasattr(self, "alarm_worker"):
                interval = as_int(
                    self.settings.value("away_interval", 5), 5, minimum=1, maximum=1440
                )
                self.alarm_worker.idle_timeout_ms = interval * 60 * 1000
            # 잠금 화면 UI 즉시 갱신
            self.refresh_idle_lock_ui()

    def refresh_idle_lock_ui(self):
        """저장된 설정으로 잠금 화면 UI를 갱신합니다."""
        if not hasattr(self, "lock_lbl"):
            return

        import html as _html

        from PyQt6.QtCore import Qt as _Qt
        from PyQt6.QtGui import QPixmap

        def _wrap_message_html(body_html):
            return (
                '<div align="center" '
                'style="margin:0; padding:0 8px; line-height:1.30; '
                'word-break:keep-all; white-space:normal;">'
                f"{body_html}</div>"
            )

        unlock_method = self.settings.value("away_unlock_method", "idle")

        raw = self.settings.value(
            "away_message",
            self._away_default_message_html(),
        )
        raw = str(raw or "")

        show_clock = self._away_show_clock_enabled()
        bg_path = self.settings.value("away_bg_path", "")
        color = self.settings.value("away_font_color", "#4da6ff")
        bold = self.settings.value("away_font_bold", True, type=bool)
        italic = self.settings.value("away_font_italic", False, type=bool)
        base_pt = as_int(self.settings.value("font_size", 10), 10, minimum=1, maximum=256)
        from calendar_app.presentation.theme.style_builder import _scaled_pt

        clock_pt = _scaled_pt(base_pt, 24, 48)
        alpha_pct = as_int(
            self.settings.value("away_bg_opacity", 100), 100, minimum=20, maximum=100
        )
        alpha = max(0, min(255, int(round(alpha_pct * 255 / 100))))

        pixmap = None
        if bg_path and os.path.exists(bg_path):
            p = QPixmap(bg_path)
            if not p.isNull():
                pixmap = p

        overlay_targets = list(getattr(self, "_away_aux_overlays", []))
        if not overlay_targets:
            overlay_targets = [
                {
                    "frame": self.lock_frame,
                    "bg_label": getattr(self, "lock_bg_label", None),
                    "clock_label": getattr(self, "lock_clock_lbl", None),
                    "msg_label": getattr(self, "lock_lbl", None),
                }
            ]

        for target in overlay_targets:
            frame = target.get("frame") or target.get("window")
            msg_lbl = target.get("msg_label")
            clock_lbl = target.get("clock_label")
            bg_lbl = target.get("bg_label")
            if frame is None or msg_lbl is None:
                continue

            frame_width = frame.width() if frame.width() > 0 else self.width()
            msg_lbl.setMaximumWidth(max(360, frame_width - 48))
            msg_lbl.setTextFormat(_Qt.TextFormat.RichText)
            if raw.strip().startswith("<"):
                msg_lbl.setText(_wrap_message_html(raw))
            else:
                size = as_int(self.settings.value("away_font_size", 24), 24, minimum=1)
                if frame_width < 620:
                    size = min(size, 20)
                style = f"font-size:{size}pt; color:{color};"
                if bold:
                    style += " font-weight:bold;"
                if italic:
                    style += " font-style:italic;"
                plain_html = _html.escape(raw).replace(chr(10), "<br>")
                msg_lbl.setText(_wrap_message_html(f'<span style="{style}">{plain_html}</span>'))

            if clock_lbl is not None:
                clock_lbl.setVisible(show_clock)
                if show_clock:
                    clock_lbl.setStyleSheet(
                        f"color: white; font-weight: bold; font-size: {clock_pt}pt; background: transparent;"
                    )

            if bg_lbl is not None:
                if pixmap is not None:
                    bg_lbl.setPixmap(pixmap)
                    bg_lbl.show()
                else:
                    bg_lbl.hide()
                bg_lbl.setGeometry(frame.rect())

            frame.setStyleSheet(f"background-color: rgba(10, 10, 10, {alpha});")

            # 비밀번호 모드: 현재 화면의 오버레이에만 pw_widget 표시
            if "pw_widget" in target:
                pw_widget_obj = target.get("pw_widget")
                if pw_widget_obj is not None:
                    is_primary = target.get("is_current_screen", False)
                    pw_widget_obj.setVisible(unlock_method == "password" and is_primary)
            else:
                pw_widget_obj = getattr(self, "lock_pw_widget", None)
                if pw_widget_obj is not None:
                    pw_widget_obj.setVisible(
                        unlock_method == "password"
                        and not bool(getattr(self, "_away_aux_overlays", []))
                    )
        # Keep clock timer state in sync with current setting while locked.
        if getattr(self, "is_away_locked", False):
            if show_clock:
                if not hasattr(self, "_lock_clock_timer"):
                    from PyQt6.QtCore import QTimer

                    self._lock_clock_timer = QTimer(self)
                    self._lock_clock_timer.timeout.connect(self._update_lock_clock)
                    self._update_lock_clock()
                if not self._lock_clock_timer.isActive():
                    self._lock_clock_timer.start(1000)
            elif hasattr(self, "_lock_clock_timer"):
                self._lock_clock_timer.stop()
            if unlock_method == "password":
                self._ensure_password_entry_ready(force_activate=False)

    def _all_lock_pw_edits(self):
        """잠금 화면의 모든 비밀번호 입력칸을 반환합니다."""
        edits = []
        if hasattr(self, "lock_pw_edit") and not getattr(self, "_away_aux_overlays", []):
            edits.append(self.lock_pw_edit)
        for overlay in getattr(self, "_away_aux_overlays", []):
            e = overlay.get("pw_edit")
            if e is not None:
                edits.append(e)
        return edits

    def _perform_away_unlock(self, pw_edit=None):
        """입력한 비밀번호를 확인한 뒤 잠금을 해제합니다."""
        if pw_edit is None:
            pw_edit = getattr(self, "lock_pw_edit", None)
        if pw_edit is None:
            return

        if self._verify_away_password(pw_edit.text()):
            self._do_away_unlock()
        else:
            # 비밀번호 오류: 모든 pw 입력칸을 비우고 빨간 테두리로 표시
            _err_style = (
                "QLineEdit { background: rgba(255,255,255,0.15); color: white; "
                "border: 1px solid #ff4444; border-radius: 4px; "
                "padding: 6px 10px; font-size: 14pt; }"
                "QLineEdit:focus { border: 1px solid #ff4444; }"
            )
            for e in self._all_lock_pw_edits():
                e.clear()
                e.setStyleSheet(_err_style)
            if pw_edit is not None:
                pw_edit.setFocus()
            from PyQt6.QtCore import QTimer

            QTimer.singleShot(900, self._reset_pw_field_styles)

    def _reset_pw_field_styles(self):
        """비밀번호 입력칸 스타일을 기본값으로 되돌립니다."""
        _normal_style = (
            "QLineEdit { background: rgba(255,255,255,0.15); color: white; "
            "border: 1px solid rgba(255,255,255,0.3); border-radius: 4px; "
            "padding: 6px 10px; font-size: 14pt; }"
            "QLineEdit:focus { border: 1px solid #4da6ff; }"
        )
        for e in self._all_lock_pw_edits():
            e.setStyleSheet(_normal_style)

    def _do_away_unlock(self):
        """자리비움 잠금을 해제합니다."""
        # 비밀번호 입력칸 포커스 해제 (해제 뒤 숨은 입력칸에 Qt 포커스가 남지 않도록)
        for e in self._all_lock_pw_edits():
            e.clearFocus()
        # 오버레이 위젯을 잠시 숨겨 잠금 해제 전환 중 깜빡임 방지
        _overlay_manager = getattr(self, "overlay_manager", None)
        _widgets_to_restore = []
        if _overlay_manager is not None:
            for _iid, _name, _wtype, _w in _overlay_manager.all_instances():
                if _w.isVisible():
                    _w.hide()
                    _widgets_to_restore.append(_w)

        self.lock_frame.hide()
        self._clear_aux_away_overlays()
        self._restore_window_after_away_lock()
        self.is_away_locked = False
        self._manual_lock_active = False
        self._manual_lock_input_tick = None
        self._stop_password_focus_watchdog()
        self._remove_force_unlock_event_filter()
        if hasattr(self, "_overlay_unlock_timer"):
            self._overlay_unlock_timer.stop()
        if hasattr(self, "_lock_clock_timer"):
            self._lock_clock_timer.stop()
        self._restore_away_preview_settings_if_needed()
        # alarm_worker 상태 초기화 (해제 직후 is_idle이 True로 남아 다시 잠기지 않도록)
        if hasattr(self, "alarm_worker"):
            self.alarm_worker.is_idle = False
            self.alarm_worker.suppress_unlock = False
            import time as _t_unlock

            self.alarm_worker._suppress_lock_until = (
                _t_unlock.monotonic() + 3.0
            )  # 3초 동안 재잠금 방지
        # aux 오버레이를 닫은 뒤 메인 창을 다시 활성화한다. ApplicationShortcut은 active window가
        # 있어야 동작하므로, 오버레이가 사라진 뒤 메인 창이 포커스를 받지 못하면 단축키가 멈춘다.
        self.activateWindow()
        self.raise_()
        # Refresh panels after unlocking.
        if hasattr(self, "schedule_panel_refresh"):
            self.schedule_panel_refresh(left=True, center=True, right=True)
        # 숨겼던 오버레이 위젯 복원 (메인 창이 올라온 뒤)
        if _widgets_to_restore:
            from PyQt6.QtCore import QTimer as _QT_unlock

            def _restore_overlays(_ws=_widgets_to_restore):
                for _w in _ws:
                    try:
                        _w.show()
                        _w.raise_()
                    except Exception:
                        pass

            _QT_unlock.singleShot(80, _restore_overlays)

    def _restore_away_preview_settings_if_needed(self):
        backup = getattr(self, "_away_preview_backup_settings", None)
        if not backup:
            return
        if not hasattr(self, "settings"):
            self._away_preview_backup_settings = None
            return

        for key, value in backup.items():
            if value is None:
                self.settings.remove(key)
            else:
                self.settings.setValue(key, value)
        self._away_preview_backup_settings = None

        if hasattr(self, "alarm_worker"):
            try:
                interval = as_int(
                    self.settings.value("away_interval", 5), 5, minimum=1, maximum=1440
                )
                self.alarm_worker.idle_timeout_ms = interval * 60 * 1000
            except Exception:
                pass

    def _update_lock_clock(self):
        """잠금 화면 시계를 현재 시각으로 갱신합니다."""
        if not hasattr(self, "lock_clock_lbl"):
            return
        if not getattr(self, "is_away_locked", False):
            return
        from PyQt6.QtCore import QDateTime

        now = QDateTime.currentDateTime()
        time_str = now.toString("HH:mm:ss")
        date_str = _lock_screen_date_text(now.date())
        clock_html = f'<div align="center"><span style="font-size: 14pt; color: #bbb;">{date_str}</span><br>{time_str}</div>'
        self.lock_clock_lbl.setText(clock_html)
        for overlay in getattr(self, "_away_aux_overlays", []):
            clock_lbl = overlay.get("clock_label")
            if clock_lbl is not None:
                clock_lbl.setText(clock_html)

    def _install_overlay_unlock_filters(self):
        """idle 모드 잠금 중 마우스·키보드 입력이 들어오면 잠금을 해제합니다.
        WindowDoesNotAcceptFocus 오버레이는 키 이벤트를 받지 못하므로
        QTimer 폴링으로 GetCursorPos + GetLastInputInfo를 직접 확인합니다."""
        from PyQt6.QtCore import QTimer

        self._overlay_lock_cursor = _safe_get_cursor_pos()
        self._overlay_lock_input_tick = _safe_get_last_input_tick()

        import time as _time

        self._overlay_lock_time = _time.monotonic()
        self._overlay_grace_ticks = 0  # grace 구간 카운터
        if not hasattr(self, "_overlay_unlock_timer"):
            self._overlay_unlock_timer = QTimer(self)
            self._overlay_unlock_timer.timeout.connect(self._poll_overlay_unlock)
        self._overlay_unlock_timer.start(200)
        import logging as _lg

        _lg.getLogger(__name__).info(
            "[POLL-INSTALL] lock_cursor=%s lock_tick=%s",
            self._overlay_lock_cursor,
            self._overlay_lock_input_tick,
        )

    def _poll_overlay_unlock(self):
        """200ms마다 커서 위치와 입력 tick을 확인해 idle 잠금을 해제합니다."""
        if not getattr(self, "is_away_locked", False):
            if hasattr(self, "_overlay_unlock_timer"):
                self._overlay_unlock_timer.stop()
            return
        unlock_method = self.settings.value("away_unlock_method", "idle")
        if unlock_method == "password":
            if hasattr(self, "_overlay_unlock_timer"):
                self._overlay_unlock_timer.stop()
            return
        cur = _safe_get_cursor_pos()
        tick = _safe_get_last_input_tick()
        if cur is None and tick is None:
            return

        lock_cursor = getattr(self, "_overlay_lock_cursor", None)
        lock_tick = getattr(self, "_overlay_lock_input_tick", None)

        # grace period: 잠금 후 1.5초 동안은 기준값만 갱신하고 해제하지 않는다
        import time as _time2

        _elapsed = _time2.monotonic() - getattr(self, "_overlay_lock_time", 0)
        _grace = 1.5  # seconds
        if _elapsed < _grace:
            # grace period: update baseline so prior movement is not counted
            self._overlay_lock_cursor = cur
            self._overlay_lock_input_tick = tick
            return

        moved = lock_cursor is not None and cur != lock_cursor
        new_input = False
        if lock_tick is not None:
            diff = (tick - lock_tick) & 0xFFFFFFFF
            new_input = 0 < diff < 0x80000000

        import logging as _lg2

        _lg2.getLogger(__name__).debug(
            "[POLL] cur=%s lock_cursor=%s moved=%s tick=%s lock_tick=%s new_input=%s",
            cur,
            lock_cursor,
            moved,
            tick,
            lock_tick,
            new_input,
        )
        if moved or new_input:
            if hasattr(self, "_overlay_unlock_timer"):
                self._overlay_unlock_timer.stop()
            self._do_away_unlock()

    # ------------------------------------------------------------------ #
    # 강제 잠금 해제 단축키 (오버레이 창에 QShortcut 등록) #
    # ------------------------------------------------------------------ #
    def _install_force_unlock_shortcut(self, win):
        """오버레이 창에 강제 해제 QShortcut을 등록합니다."""
        from PyQt6.QtCore import Qt as _Qt2
        from PyQt6.QtGui import QKeySequence, QShortcut

        _main_ref = self
        sequence = self.AWAY_FORCE_UNLOCK_SHORTCUT
        sc = QShortcut(QKeySequence(sequence), win)
        sc.setContext(_Qt2.ShortcutContext.ApplicationShortcut)
        sc.activated.connect(lambda: _main_ref._handle_force_unlock_request())
        if not hasattr(self, "_away_force_unlock_shortcuts"):
            self._away_force_unlock_shortcuts = []
        self._away_force_unlock_shortcuts.append(sc)
        win._away_force_unlock_shortcut = sc
        if win is not self and not hasattr(self, "_away_main_force_unlock_shortcut"):
            main_sc = QShortcut(QKeySequence(sequence), self)
            main_sc.setContext(_Qt2.ShortcutContext.ApplicationShortcut)
            main_sc.activated.connect(lambda: _main_ref._handle_force_unlock_request())
            self._away_force_unlock_shortcuts.append(main_sc)
            self._away_main_force_unlock_shortcut = main_sc
        return sc
