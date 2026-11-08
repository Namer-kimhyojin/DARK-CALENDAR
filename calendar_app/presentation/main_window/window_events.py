# -*- coding: utf-8 -*-
"""Window drag/resize/multi-monitor behavior for main overlay window."""

import contextlib
import logging

try:
    import win32con
    import win32gui

    HAS_WIN32 = True
except ImportError:
    win32con = None
    win32gui = None
    HAS_WIN32 = False

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

logger = logging.getLogger(__name__)

RESIZE_MARGIN = 10
SAFE_SCREEN_MARGIN = 6
TITLE_DRAG_HEIGHT = 60


def _can_hide_to_tray(window) -> bool:
    """Return whether closing the main window can safely leave a tray entry."""
    if not getattr(window, "_tray_available", False):
        return False
    tray_icon = getattr(window, "tray_icon", None)
    if tray_icon is None:
        return False
    try:
        return QSystemTrayIcon.isSystemTrayAvailable() and tray_icon.isVisible()
    except RuntimeError:
        return False


def _set_window_bottom(hwnd):
    if not HAS_WIN32:
        return
    try:
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_BOTTOM,
            0,
            0,
            0,
            0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
        )
    except Exception:
        logger.debug("SetWindowPos failed; keeping current z-order.", exc_info=True)


class WindowEventsMixin:
    first_paint = pyqtSignal()

    def _resize_region_at(self, pos):
        left = pos.x() <= RESIZE_MARGIN
        right = pos.x() >= self.width() - RESIZE_MARGIN
        top = pos.y() <= RESIZE_MARGIN
        bottom = pos.y() >= self.height() - RESIZE_MARGIN

        if top and left:
            return "tl"
        if top and right:
            return "tr"
        if bottom and left:
            return "bl"
        if bottom and right:
            return "br"
        if left:
            return "l"
        if right:
            return "r"
        if top:
            return "t"
        if bottom:
            return "b"
        return None

    def _cursor_for_resize_region(self, region):
        if region in {"tl", "br"}:
            return Qt.CursorShape.SizeFDiagCursor
        if region in {"tr", "bl"}:
            return Qt.CursorShape.SizeBDiagCursor
        if region in {"l", "r"}:
            return Qt.CursorShape.SizeHorCursor
        if region in {"t", "b"}:
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def _target_screen_geometry(self):
        from PyQt6.QtGui import QGuiApplication

        from calendar_app.presentation.widgets.widget_mode_geometry import best_screen_for_rect

        screen = best_screen_for_rect(QGuiApplication.screens(), self.frameGeometry())
        return screen.availableGeometry() if screen is not None else None

    def _apply_resize_delta(self, delta):
        rect = self.geometry()
        x = rect.x()
        y = rect.y()
        width = rect.width()
        height = rect.height()
        min_width = max(200, self.minimumWidth())
        min_height = max(120, self.minimumHeight())

        if "l" in self._resize_dir:
            new_x = min(x + delta.x(), x + width - min_width)
            width = (x + width) - new_x
            x = new_x
        if "r" in self._resize_dir:
            width = max(min_width, width + delta.x())
        if "t" in self._resize_dir:
            new_y = min(y + delta.y(), y + height - min_height)
            height = (y + height) - new_y
            y = new_y
        if "b" in self._resize_dir:
            height = max(min_height, height + delta.y())

        self.setGeometry(x, y, width, height)

    def _safe_screen_rect(self):
        available = self._target_screen_geometry()
        if not available:
            return None
        return available.adjusted(
            SAFE_SCREEN_MARGIN,
            SAFE_SCREEN_MARGIN,
            -SAFE_SCREEN_MARGIN,
            -SAFE_SCREEN_MARGIN,
        )

    def mousePressEvent(self, event):
        self._native_window_drag = False
        if hasattr(self, "_reset_idle_timer"):
            self._reset_idle_timer()

        if getattr(self, "is_locked", False):
            return super().mousePressEvent(event)

        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)

        self._resize_dir = self._resize_region_at(event.pos())
        if self._resize_dir:
            self.old_pos_drag = event.globalPosition().toPoint()
            return

        if event.pos().y() <= TITLE_DRAG_HEIGHT:
            self.old_pos_drag = None
            if self._try_start_system_move():
                self._native_window_drag = True
                event.accept()
                return
            self.old_pos_drag = event.globalPosition().toPoint()
            return

        self.old_pos_drag = None
        return super().mousePressEvent(event)

    def _try_start_system_move(self):
        if (
            self.isMaximized()
            or self.isFullScreen()
            or getattr(self, "is_fullscreen", False)
            or getattr(self, "_screen_fill_active", False)
        ):
            return False
        try:
            handle = self.windowHandle()
            return handle is not None and handle.startSystemMove()
        except RuntimeError:
            # Keep the existing logical-coordinate fallback if the platform
            # cannot start an OS move (including a disappearing native handle).
            return False

    def mouseMoveEvent(self, event):
        if getattr(self, "is_locked", False):
            return super().mouseMoveEvent(event)

        region = self._resize_dir or self._resize_region_at(event.pos())
        self.setCursor(self._cursor_for_resize_region(region))

        if self.old_pos_drag is None:
            return super().mouseMoveEvent(event)

        delta = event.globalPosition().toPoint() - self.old_pos_drag
        if self._resize_dir:
            self._apply_resize_delta(delta)
        else:
            self.move(self.pos() + delta)
        self.old_pos_drag = event.globalPosition().toPoint()

    def mouseDoubleClickEvent(self, event):
        if getattr(self, "is_locked", False):
            return super().mouseDoubleClickEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and event.pos().y() <= TITLE_DRAG_HEIGHT:
            self.old_pos_drag = None  # 진행 중인 드래그 취소
            self._toggle_screen_fill()
            event.accept()
            return
        return super().mouseDoubleClickEvent(event)

    def _toggle_screen_fill(self):
        """타이틀바 더블클릭 시 현재 모니터 전체 채우기 토글."""
        if getattr(self, "_screen_fill_active", False):
            saved = self.settings.value("pre_fill_geometry")
            if saved:
                self.restoreGeometry(saved)
            self._screen_fill_active = False
            self.settings.setValue("screen_fill_active", "false")
        else:
            self.settings.setValue("pre_fill_geometry", self.saveGeometry())
            available = self._target_screen_geometry()
            if available:
                self.setGeometry(available)
            self._screen_fill_active = True
            self.settings.setValue("screen_fill_active", "true")
        _set_window_bottom(int(self.winId()))

    def mouseReleaseEvent(self, event):
        was_interacting = (
            self.old_pos_drag is not None
            or self._resize_dir is not None
            or getattr(self, "_native_window_drag", False)
        )
        self._native_window_drag = False
        self.old_pos_drag = None
        self._resize_dir = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        if was_interacting:
            self.ensure_window_on_screen()
            # Only restore desktop layering after a window gesture.  Ordinary
            # child-control releases must not lower the window, and an active
            # popup or modal dialog must retain its owner until it closes.
            if (
                QApplication.activePopupWidget() is None
                and QApplication.activeModalWidget() is None
            ):
                _set_window_bottom(int(self.winId()))
        return super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        self._native_window_drag = False
        self.old_pos_drag = None
        self._resize_dir = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)

    def closeEvent(self, event):
        exit_without_tray = False
        if not getattr(self, "_exit_requested", False):
            if _can_hide_to_tray(self):
                event.ignore()
                self.hide()
                self.is_visible = False
                return
            # A tray-only app must not leave an unreachable background process
            # when the operating system has no usable notification area.
            self._exit_requested = True
            exit_without_tray = True

        # 종료 플래그를 먼저 설정 — 이후 타이머 콜백이 새 워커를 시작하지 못하게 함
        shutdown_already_started = bool(getattr(self, "_is_shutting_down", False))
        self._is_shutting_down = True
        self.is_visible = False

        # OverlayApp owns one idempotent shutdown entry point.  Keeping the
        # close event on that path prevents workers (notably AlarmWorker) from
        # receiving duplicate stop/wait calls.  Lightweight test/fallback
        # hosts without ActionHandlersMixin retain the local cleanup below.
        shared_shutdown = getattr(self, "shutdown_background_workers", None)
        shared_shutdown_handled = False
        if callable(shared_shutdown):
            try:
                shared_shutdown()
                shared_shutdown_handled = True
            except Exception:
                logger.exception("Shared application shutdown failed; using close-event fallback")
        elif shutdown_already_started:
            shared_shutdown_handled = True

        if not shared_shutdown_handled:
            # Persist widget-only state before fallback cleanup hides/destroys
            # its top-level windows.
            close_widget_mode = getattr(self, "close_widget_mode_panels", None)
            if not shutdown_already_started and callable(close_widget_mode):
                try:
                    close_widget_mode()
                except Exception:
                    logger.exception("Failed to persist widget mode during shutdown")

            # 모든 타이머 정리 — 종료 후 타이머 콜백이 파괴된 객체에 접근하는 것을 방지
            for _timer_attr in (
                "gcal_sync_timer",
                "gcal_quick_sync_timer",
                "gcal_sleep_timer",
                "gcal_sleep_poll_timer",
                "gcal_idle_timer",
                "ics_sync_timer",
                "_wake_sync_timer",
                "search_debounce_timer",
                "_sync_anim_timer",
                "_system_theme_refresh_timer",
                "_stopwatch_timer",
                "_countdown_timer",
                "_slow_text_timer",
                "_ui_refresh_timer",
                "_away_admin_hold_timer",
                "_away_password_focus_timer",
                "_lock_clock_timer",
                "_overlay_unlock_timer",
                "_daily_summary_timer",
                "_geom_persist_timer",
                "_dock_persist_timer",
                "_focus_timer",
            ):
                timer = getattr(self, _timer_attr, None)
                if timer is not None:
                    with contextlib.suppress(AttributeError, RuntimeError):
                        timer.stop()

            # Fallback QThread cleanup for hosts without ActionHandlersMixin.
            seen_workers: set[int] = set()
            workers = [
                getattr(self, "alarm_worker", None),
                getattr(self, "_sync_worker", None),
                getattr(self, "_auth_worker", None),
                *list(getattr(self, "_bg_workers", [])),
            ]
            for worker in workers:
                if worker is None or id(worker) in seen_workers:
                    continue
                seen_workers.add(id(worker))
                try:
                    stop_method = getattr(worker, "stop", None)
                    if callable(stop_method):
                        stop_method()
                    else:
                        request_interruption = getattr(worker, "requestInterruption", None)
                        if callable(request_interruption):
                            request_interruption()
                    quit_method = getattr(worker, "quit", None)
                    if callable(quit_method):
                        quit_method()
                    wait_method = getattr(worker, "wait", None)
                    if callable(wait_method):
                        wait_method(2000)
                except (AttributeError, RuntimeError):
                    pass
                except Exception:
                    logger.exception("Failed to stop fallback worker during close")

        try:
            from calendar_app.presentation.main_window.action_handlers import (
                _save_window_layout_for_shutdown,
            )

            _save_window_layout_for_shutdown(self)
        except Exception:
            # Import/teardown failures must not make the application refuse to
            # close.  Settings are independently synced by shared shutdown.
            logger.exception("Could not run window layout shutdown helper")
        super().closeEvent(event)
        if exit_without_tray:
            app = QApplication.instance()
            if app is not None:
                from calendar_app.shared.app_lifecycle import finish_application_exit

                finish_application_exit(app)

    def showEvent(self, event):
        super().showEvent(event)
        self.ensure_window_on_screen()
        _set_window_bottom(int(self.winId()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "size_grip"):
            self.size_grip.move(self.width() - 20, self.height() - 20)
        if hasattr(self, "_update_lock_overlay_geometry"):
            self._update_lock_overlay_geometry()
        if hasattr(self, "schedule_panel_refresh") and not getattr(
            self, "_is_shutting_down", False
        ):
            self.schedule_panel_refresh(center=True, delay_ms=16)
        self._schedule_geometry_persist()

        # Keep lock overlay/background aligned with resized window.
        if hasattr(self, "lock_frame") and self.lock_frame.isVisible():
            self.lock_frame.setGeometry(0, 0, self.width(), self.height())
            if hasattr(self, "lock_bg_label"):
                self.lock_bg_label.setGeometry(self.lock_frame.rect())

    def moveEvent(self, event):
        super().moveEvent(event)
        self._schedule_geometry_persist()

    def _schedule_geometry_persist(self):
        """Debounced reactive save of window geometry on resize/move."""
        if getattr(self, "_is_shutting_down", False):
            return
        timer = getattr(self, "_geom_persist_timer", None)
        if timer is None:
            from PyQt6.QtCore import QTimer

            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(400)

            def _do_persist():
                if getattr(self, "_is_shutting_down", False):
                    return
                try:
                    from calendar_app.presentation.main_window.window_restore_helpers import (
                        persist_dock_layout,
                    )

                    persist_dock_layout(self)
                except Exception:
                    pass

            timer.timeout.connect(_do_persist)
            self._geom_persist_timer = timer
        timer.start()

    def paintEvent(self, event):
        from PyQt6.QtGui import QColor, QPainter

        if not getattr(self, "_first_paint_done", False):
            self._first_paint_done = True
            self.first_paint.emit()

        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 1))
        painter.end()

    def ensure_window_on_screen(self):
        # Maximized / fullscreen / screen-fill windows must not be touched —
        # setGeometry silently clears the maximized flag, and applying the
        # SAFE_SCREEN_MARGIN would shrink the filled window by 6px on each
        # side. This caused (1) double-click-maximize being lost on every
        # restart and (2) pixel-level position drift between sessions.
        if (
            self.isMaximized()
            or self.isFullScreen()
            or getattr(self, "is_fullscreen", False)
            or getattr(self, "_screen_fill_active", False)
        ):
            return

        safe = self._safe_screen_rect()
        if not safe:
            return

        rect = self.geometry()
        width = min(rect.width(), safe.width())
        height = min(rect.height(), safe.height())
        x = rect.x()
        y = rect.y()

        new_x, new_y = x, y
        if x < safe.left():
            new_x = safe.left()
        elif x + width > safe.right() + 1:
            new_x = safe.right() - width + 1

        if y < safe.top():
            new_y = safe.top()
        elif y + height > safe.bottom() + 1:
            new_y = safe.bottom() - height + 1

        # Skip setGeometry entirely when the window is already inside the safe
        # area at its saved size — otherwise rounding causes a 1-pixel drift
        # that accumulates across restarts.
        if (new_x, new_y, width, height) == (x, y, rect.width(), rect.height()):
            return

        self.setGeometry(new_x, new_y, width, height)

    def restore_window_to_safe_area(self):
        safe = self._safe_screen_rect()
        if not safe:
            return

        if getattr(self, "is_fullscreen", False):
            self.showNormal()
            self.is_fullscreen = False

        width = min(max(self.minimumWidth(), int(safe.width() * 0.82)), safe.width())
        height = min(max(self.minimumHeight(), int(safe.height() * 0.82)), safe.height())
        x = safe.left() + max(0, (safe.width() - width) // 2)
        y = safe.top() + max(0, (safe.height() - height) // 2)
        self.setGeometry(x, y, width, height)
        from calendar_app.infrastructure.runtime.infra_wiring import _set_overlay_visible

        _set_overlay_visible(self, True)

    def move_to_next_monitor(self):
        self._move_to_adjacent_monitor(1)

    def move_to_previous_monitor(self):
        self._move_to_adjacent_monitor(-1)

    def _move_to_adjacent_monitor(self, step):
        from PyQt6.QtGui import QGuiApplication

        from calendar_app.presentation.widgets.widget_mode_geometry import best_screen_for_rect

        screens = QGuiApplication.screens()
        if len(screens) <= 1:
            return

        current_screen = best_screen_for_rect(screens, self.frameGeometry())
        if current_screen is None:
            return

        idx = screens.index(current_screen)
        target_screen = screens[(idx + step) % len(screens)]

        old_available = current_screen.availableGeometry()
        new_available = target_screen.availableGeometry()
        if not old_available.isValid() or not new_available.isValid():
            return

        if getattr(self, "_screen_fill_active", False):
            # Screen-fill is a windowed mode: fill the destination, not the old
            # monitor's dimensions. Keep its saved toggle/restore state intact.
            self.setGeometry(new_available)
        elif self.isMaximized() or self.isFullScreen() or getattr(self, "is_fullscreen", False):
            # QWidget.setGeometry() would clear native maximized/fullscreen state.
            self.move(new_available.topLeft())
        else:
            old_safe = old_available.adjusted(
                SAFE_SCREEN_MARGIN, SAFE_SCREEN_MARGIN, -SAFE_SCREEN_MARGIN, -SAFE_SCREEN_MARGIN
            )
            new_safe = new_available.adjusted(
                SAFE_SCREEN_MARGIN, SAFE_SCREEN_MARGIN, -SAFE_SCREEN_MARGIN, -SAFE_SCREEN_MARGIN
            )
            if not old_safe.isValid() or not new_safe.isValid():
                return
            rect = self.geometry()
            old_travel_x = old_safe.width() - rect.width()
            old_travel_y = old_safe.height() - rect.height()
            rel_x = (
                min(1.0, max(0.0, (rect.x() - old_safe.x()) / old_travel_x))
                if old_travel_x > 0
                else 0.5
            )
            rel_y = (
                min(1.0, max(0.0, (rect.y() - old_safe.y()) / old_travel_y))
                if old_travel_y > 0
                else 0.5
            )
            # Qt already reports device-independent geometry. Preserve that size
            # across DPI changes, shrinking only when the available area is smaller.
            width = min(rect.width(), new_safe.width())
            height = min(rect.height(), new_safe.height())
            x = new_safe.x() + round((new_safe.width() - width) * rel_x)
            y = new_safe.y() + round((new_safe.height() - height) * rel_y)
            self.setGeometry(x, y, width, height)
        self.ensure_window_on_screen()

    def snap_to_edge(self, edge):
        from PyQt6.QtGui import QGuiApplication

        screen = QGuiApplication.screenAt(self.geometry().center())
        if not screen:
            return

        geom = screen.availableGeometry()
        if edge == "left":
            self.move(geom.left(), self.y())
        elif edge == "right":
            self.move(geom.right() - self.width(), self.y())
        elif edge == "top":
            self.move(self.x(), geom.top())
        elif edge == "bottom":
            self.move(self.x(), geom.bottom() - self.height())
        elif edge == "center":
            self.move(geom.center() - self.rect().center())

        self.ensure_window_on_screen()
