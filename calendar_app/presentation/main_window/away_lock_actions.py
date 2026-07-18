"""Away-lock (idle lock) related action mixin."""

import logging
import os
import time

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication, QDialog

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.shared.value_parsers import as_bool

try:
    import win32api as _win32api
except ImportError:
    _win32api = None

_LOGGER = logging.getLogger(__name__)
_WIN32_WARNING_LOGGED = False


def _warn_win32_unavailable_once():
    global _WIN32_WARNING_LOGGED
    if _win32api is None and not _WIN32_WARNING_LOGGED:
        _LOGGER.warning(
            "win32api is unavailable. Away-lock input tracking uses reduced fallback mode."
        )
        _WIN32_WARNING_LOGGED = True


def _safe_get_last_input_tick():
    if _win32api is None:
        _warn_win32_unavailable_once()
        return None
    try:
        return int(_win32api.GetLastInputInfo()) & 0xFFFFFFFF
    except Exception:
        return None


def _safe_get_cursor_pos():
    if _win32api is None:
        _warn_win32_unavailable_once()
        return None
    try:
        return _win32api.GetCursorPos()
    except Exception:
        return None


class _AwayForceUnlockFilter(QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self._owner = owner

    def eventFilter(self, watched, event):
        owner = self._owner
        if getattr(owner, "is_away_locked", False) and owner._is_force_unlock_key_event(event):
            owner._do_away_unlock()
            return True
        return False


class _AwayAdminUnlockDialog(QDialog):
    def __init__(self, parent=None):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout

        from calendar_app.presentation.dialogs.dialog_styles import apply_common_dialog_style

        super().__init__(parent)
        apply_dialog_title(self, "관리자 잠금 해제")
        self.setModal(True)
        apply_common_dialog_style(self, minimum_width=320, size=(380, 190))
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel(t("away_lock.admin_pw_title", "관리자 비밀번호를 입력하세요."))
        self.password_edit = QLineEdit(self)
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText(
            t("away_lock.admin_pw_placeholder", "관리자 비밀번호")
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
    AWAY_ADMIN_UNLOCK_PASSWORD = "admin"
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

    def _verify_admin_unlock_password(self, password):
        return str(password or "") == self.AWAY_ADMIN_UNLOCK_PASSWORD

    def _prompt_admin_unlock_password(self, parent=None):
        dialog = _AwayAdminUnlockDialog(parent or self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        return self._verify_admin_unlock_password(dialog.password_edit.text())

    def _trigger_admin_unlock_dialog(self):
        overlay = getattr(self, "_away_admin_hold_overlay", None)
        self._clear_admin_unlock_hold()
        if not getattr(self, "is_away_locked", False):
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

            # ALT+F4 ?源놁몵占???占쎌쒔??占쎌뵠 占???占쎄돌揶쎛 ???占쏙옙??????
            # - ??占쏙옙?甕곕뜇??筌뤴뫀占? ?袁⑹읈 筌△뫀??
            # - idle 筌뤴뫀占? ?袁⑷퍥 ?醫됲닊 ??占쎌젫
            _main_ref = self

            def _overlay_close_event(event, _ref=_main_ref):
                event.ignore()  # Keep overlay window from being closed directly by Qt.
                if not getattr(_ref, "is_away_locked", False):
                    return
                unlock_method = _ref.settings.value("away_unlock_method", "idle")
                if unlock_method == "password":
                    return  # ??占쏙옙?甕곕뜇??筌뤴뫀占?占?占쏙옙??ALT+F4 ?袁⑹읈 筌△뫀??
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

            # 揶쏅벡????占쎌젫 ??占쏀뀧????占쏀뒄 (??占쏙옙?甕곕뜇??筌뤴뫀占???占?
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
            # aux ???占쎌뮅???占쎈턄?占쎌럾? 嶺뚮ㅄ維占???占쎌뻼???????占쎌쾵???嶺뚮∥???嶺뚢돦???showFullScreen()?? ?釉띾쐡???
            # WindowStaysOnBottomHint|Tool 嶺뚢돦?占썼굢??showFullScreen??占쏙옙?owNormal ??????
            # WA_TranslucentBackground ??占????占쎌뎽?????????????占쎈さ亦껋깢?????紐꾩끋??類ｋ펲.
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
                    win.showFullScreen()

            _logger.info(
                "[LOCK] locked. password_mode=%s overlay_count=%s manual=%s",
                _password_mode,
                len(getattr(self, "_away_aux_overlays", [])),
                manual,
            )
            # idle ??占쎌젫 筌뤴뫀占??????占쏙옙?????占????占쏀뒄 (??占쎌퍢????占쎌쟿??占쏙옙?甕곌쑵????占??tick??lock_tick??野껓옙????占?獄쎻뫗?)
            if not _password_mode:
                from PyQt6.QtCore import QTimer as _QT

                _QT.singleShot(300, self._install_overlay_unlock_filters)

            # ??占쏙옙?甕곕뜇????占쎌젫 筌뤴뫀占? ?袁⑹삺 ?遺얇늺????占쎌젾筌≪럥占???占쎄쉐?酉占?占???占??? ?占???占쎈뼄.
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

            # ??濡レ쭢 ??占쎈맪??? ??占쎈맪????袁⑸쐩 "?????占쎌졑"?????占쎈굵 ???占???怨몄젷 ???占쎈뮔
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

            # ???占????占????占쎈쪇占???占쎈객占?? ???占썩뵛??(??濡レ쭢 ???占쎈뺄 ??占?占쏙옙????怨몄젷 ??占쎈쪇占???占쎌룇占???????占쎌┣??
            if hasattr(self, "alarm_worker"):
                self.alarm_worker.is_idle = True
                self.alarm_worker.suppress_unlock = True  # idle_detector unlock emit 筌△뫀??
                self.alarm_worker._last_cursor_pos = _safe_get_cursor_pos()

            # ??蹂㎳????占쎌몥??袁⑤콦 ?????????戮곗굚 (??占?占쏙옙??占쎌뼔占??占쎄퍔???
            if self._away_show_clock_enabled():
                if not hasattr(self, "_lock_clock_timer"):
                    from PyQt6.QtCore import QTimer

                    self._lock_clock_timer = QTimer(self)
                    self._lock_clock_timer.timeout.connect(self._update_lock_clock)
                self._update_lock_clock()  # 嶺뚯빖占??1?????占쎌몥??袁⑤콦
                self._lock_clock_timer.start(1000)
        else:
            if not getattr(self, "is_away_locked", False):
                return

            _logger.info(
                "[UNLOCK-ENTRY] manual=%s method=%s",
                getattr(self, "_manual_lock_active", False),
                self.settings.value("away_unlock_method", "idle"),
            )
            # ??濡レ쭢 ??占쎈맪????占쎈객占????????占쎈맪????袁⑸쐩 ???占쎌젷 ???占쎌졑???占쎌룇裕뉑틦??????占썹춯?占승 ??怨몄젷 ?釉띾쐝?
            if getattr(self, "_manual_lock_active", False):
                lock_tick = getattr(self, "_manual_lock_input_tick", None)
                has_new_input = False
                if lock_tick is not None:
                    current_input_tick = _safe_get_last_input_tick()
                    if current_input_tick is not None:
                        # tick?? 32??占쏙옙??unsigned??占?占?wrap-around ?占쎌쥓??
                        diff = (current_input_tick - lock_tick) & 0xFFFFFFFF
                        has_new_input = 0 < diff < 0x80000000
                else:
                    # ??占쏙옙? ?醫됲닊 ???占쎌젙 ??占쎌퍢 野껋럡??
                    if hasattr(self, "_last_manual_lock_time"):
                        has_new_input = (time.time() - self._last_manual_lock_time) >= 2.0
                # 癰귣똻??揶쏅Ŋ?: GetLastInputInfo揶쎛 筌띾뜆?????占쏙옙????? 筌륁궢占??野껋럩???占썬끉占??袁⑺뒄占??占쎌씤
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
            # ???占쎌젧???占쎄떠??占쎄퍔?占썹뵳???占쎈さ亦껋깢???AlarmScheduler???占쎌룄?占썹댆????占쎌몥??袁⑤콦 ?熬곣뫗??
            if hasattr(self, "alarm_worker"):
                interval = int(self.settings.value("away_interval", 5))
                self.alarm_worker.idle_timeout_ms = interval * 60 * 1000
            # UI 嶺뚯빖占???占쎌룇占??(??占쎈맪????占쎌뻼????占썬늾????
            self.refresh_idle_lock_ui()

    def refresh_idle_lock_ui(self):
        """???縕ワ쭕????占쎌젧??怨쀬Ŧ ??占쏙옙???? ??占쎈맪????占쎌뻼??UI???占쎌룄????類ｋ펲."""
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
        base_pt = self.settings.value("font_size", 10, type=int)
        from calendar_app.presentation.theme.style_builder import _scaled_pt

        clock_pt = _scaled_pt(base_pt, 24, 48)
        alpha_pct = max(20, min(100, int(self.settings.value("away_bg_opacity", 100))))
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
                size = int(self.settings.value("away_font_size", 24))
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

            # ??占쏙옙?甕곕뜇??筌뤴뫀占? ?袁⑹삺 ??占쎄쾿????占쎌쒔??占쎌뵠?占?占쏙옙 pw_widget ??占쎈뻻
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
        """??占쎈맪????占쎌뻼???嶺뚮ㅄ維占??????占쎄퀡??????占쎌졑 ?熬곣뫀占???占쎌룇占???紐껊퉵??"""
        edits = []
        if hasattr(self, "lock_pw_edit") and not getattr(self, "_away_aux_overlays", []):
            edits.append(self.lock_pw_edit)
        for overlay in getattr(self, "_away_aux_overlays", []):
            e = overlay.get("pw_edit")
            if e is not None:
                edits.append(e)
        return edits

    def _perform_away_unlock(self, pw_edit=None):
        """?????占쎄퀡???占쎈ご??筌먦끉占??琉우뿰 ??占쏙옙???? ??占쎈맪?????怨몄젷??紐껊퉵??"""
        if pw_edit is None:
            pw_edit = getattr(self, "lock_pw_edit", None)
        if pw_edit is None:
            return

        entered = pw_edit.text()
        stored = str(self.settings.value("away_password", ""))

        if entered == stored:
            self._do_away_unlock()
        else:
            # ???占쎈엷?? 嶺뚮ㅄ維占?pw ?熬곣뫀占??貫?占썹뵳??+ ??紐울옙???????
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
        """?????占쎄퀡????熬곣뫀占?????占쎌쾼 ?????源녿굵 ?貫?占썹뵳??占승??占???占쎈펲."""
        _normal_style = (
            "QLineEdit { background: rgba(255,255,255,0.15); color: white; "
            "border: 1px solid rgba(255,255,255,0.3); border-radius: 4px; "
            "padding: 6px 10px; font-size: 14pt; }"
            "QLineEdit:focus { border: 1px solid #4da6ff; }"
        )
        for e in self._all_lock_pw_edits():
            e.setStyleSheet(_normal_style)

    def _do_away_unlock(self):
        """??占쏙옙???? ??占쎈맪?????怨몄젷??紐껊퉵??"""
        # ?????? ?誘る닔? ??蹂ㅽ깴 (??節딅낵占??熬곣뫗占??Qt ?????? ??關紐든춯????占쎌졑???誘⑹퐛??
        for e in self._all_lock_pw_edits():
            e.clearFocus()
        # ??占쎌쒔??占쎌뵠 ?袁⑹졐(??占쏙옙??????醫됲돵 ??占쎄볼???醫됲닊 ??占쎌젫 ?袁れ넎 ??繹먯뮆占??獄쎻뫗?
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
        # alarm_worker ??占쎈쪇占???占쎈객占??貫?占썹뵳??(?????占쎄퀡???嶺뚮ㅄ維占?????is_idle??True??占??占썰빳???貫?????占쎈굵 ?????占쎈쾳)
        if hasattr(self, "alarm_worker"):
            self.alarm_worker.is_idle = False
            self.alarm_worker.suppress_unlock = False
            import time as _t_unlock

            self.alarm_worker._suppress_lock_until = (
                _t_unlock.monotonic() + 3.0
            )  # 3?占쎈뜃占????占썸묾?獄쎻뫗?
        # aux ???占쎌뮅???占쎈턄 ??????????占?占쏙옙???占쎄랜占??        # ApplicationShortcut ?? ?繹먮끏??active window?占쎌럾? ???占쎈굵 ???占????占쎌굚?????
        # ???占쎌뮅???占쎈턄?占쎌럾? ????占쏙옙??嶺뚯쉳???嶺뚮∥???嶺뚢돦???OS ???占쎈낵???????占?占쏙옙??占승?????館???? ?占쎄랜占???
        self.activateWindow()
        self.raise_()
        # Refresh panels after unlocking.
        if hasattr(self, "schedule_panel_refresh"):
            self.schedule_panel_refresh(left=True, center=True, right=True)
        # ??占쎌쒔??占쎌뵠 ?袁⑹졐 癰귣벊??(筌롫뗄??筌≪럩?????????
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
                interval = int(self.settings.value("away_interval", 5))
                self.alarm_worker.idle_timeout_ms = interval * 60 * 1000
            except Exception:
                pass

    def _update_lock_clock(self):
        """??占쎈맪????占쎌뻼?????蹂㎳????占쎈츩?占? ?熬곣뫗????占쏙옙???怨쀬Ŧ ???占쎌몥??袁⑤콦??紐껊퉵??"""
        if not hasattr(self, "lock_clock_lbl"):
            return
        if not getattr(self, "is_away_locked", False):
            return
        from PyQt6.QtCore import QDateTime, QLocale

        now = QDateTime.currentDateTime()
        time_str = now.toString("HH:mm:ss")
        # QLocale default is set by I18nManager._apply_qt_locale() at startup
        locale = QLocale()
        date_str = locale.toString(now.date(), t("away_lock.date_format"))
        clock_html = f'<div align="center"><span style="font-size: 14pt; color: #bbb;">{date_str}</span><br>{time_str}</div>'
        self.lock_clock_lbl.setText(clock_html)
        for overlay in getattr(self, "_away_aux_overlays", []):
            clock_lbl = overlay.get("clock_label")
            if clock_lbl is not None:
                clock_lbl.setText(clock_html)

    def _install_overlay_unlock_filters(self):
        """idle 筌뤴뫀占??醫됲닊 ???占썬끉占???占쏙옙?????占?占썸에?筌띾뜆?????占쏙옙???占???揶쏅Ŋ???筌욊낯????占쎌젫??占쎈뼄.
        WindowDoesNotAcceptFocus ??占쎌쒔??占쎌뵠?占?占쏙옙 ??占쏙옙???袁り숲揶쎛 ?醫딉옙??????占쎌몵沃샕占?        QTimer ??占쏙옙??占쎌쨮 GetCursorPos + GetLastInputInfo??筌욊낯???占쎌씤??占쎈뼄."""
        from PyQt6.QtCore import QTimer

        self._overlay_lock_cursor = _safe_get_cursor_pos()
        self._overlay_lock_input_tick = _safe_get_last_input_tick()

        import time as _time

        self._overlay_lock_time = _time.monotonic()
        self._overlay_grace_ticks = 0  # 筌ｌ꼷??占??占? 疫꿸퀣? 揶쏄퉮?占쏙쭕???
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
        """200ms筌띾뜄???占썬끉占???占쏙옙??占?占쏙옙 ????占쎌젾???占쎌씤??idle ?醫됲닊????占쎌젫??占쎈뼄."""
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

        # grace period: ?醫됲닊 ??1.5????占쎈툧?? ?占썬끉占?疫꿸퀣?揶쏉옙????占쎄쑴??揶쏄퉮???占쏙옙???占쎌젫??筌띾맩??
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
    # 揶쏅벡???醫됲닊 ??占쎌젫 ??占쏀뀧??(??占쎌쒔??占쎌뵠??QShortcut ??占쏀뒄) #
    # ------------------------------------------------------------------ #
    def _install_force_unlock_shortcut(self, win):
        """??占쎌쒔??占쎌뵠 筌≪럩占?揶쏅벡????占쎌젫 QShortcut????占쏀뒄??占쎈뼄."""
        from PyQt6.QtCore import Qt as _Qt2
        from PyQt6.QtGui import QKeySequence, QShortcut

        _main_ref = self
        sequence = self.AWAY_FORCE_UNLOCK_SHORTCUT
        sc = QShortcut(QKeySequence(sequence), win)
        sc.setContext(_Qt2.ShortcutContext.ApplicationShortcut)
        sc.activated.connect(lambda: _main_ref._do_away_unlock())
        if not hasattr(self, "_away_force_unlock_shortcuts"):
            self._away_force_unlock_shortcuts = []
        self._away_force_unlock_shortcuts.append(sc)
        win._away_force_unlock_shortcut = sc
        if win is not self and not hasattr(self, "_away_main_force_unlock_shortcut"):
            main_sc = QShortcut(QKeySequence(sequence), self)
            main_sc.setContext(_Qt2.ShortcutContext.ApplicationShortcut)
            main_sc.activated.connect(lambda: _main_ref._do_away_unlock())
            self._away_force_unlock_shortcuts.append(main_sc)
            self._away_main_force_unlock_shortcut = main_sc
        return sc
