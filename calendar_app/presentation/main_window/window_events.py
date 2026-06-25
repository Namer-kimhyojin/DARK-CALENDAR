"""Window drag/resize/multi-monitor behavior for main overlay window."""

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

logger = logging.getLogger(__name__)

RESIZE_MARGIN = 10
SAFE_SCREEN_MARGIN = 6
TITLE_DRAG_HEIGHT = 60


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

        frame = self.frameGeometry()
        probe_points = [
            frame.center(),
            frame.topLeft(),
            frame.topRight(),
            frame.bottomLeft(),
            frame.bottomRight(),
        ]
        for point in probe_points:
            screen = QGuiApplication.screenAt(point)
            if screen:
                return screen.availableGeometry()

        primary = QGuiApplication.primaryScreen()
        return primary.availableGeometry() if primary else None

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
            self.old_pos_drag = event.globalPosition().toPoint()
            return

        self.old_pos_drag = None
        return super().mousePressEvent(event)

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
        self.old_pos_drag = None
        self._resize_dir = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.ensure_window_on_screen()
        _set_window_bottom(int(self.winId()))
        return super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        self.old_pos_drag = None
        self._resize_dir = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)

    def closeEvent(self, event):
        from calendar_app.presentation.main_window.window_restore_helpers import save_window_layout

        # 종료 플래그를 먼저 설정 — 이후 타이머 콜백이 새 워커를 시작하지 못하게 함
        self._is_shutting_down = True

        # 모든 타이머 정리 — 종료 후 타이머 콜백이 파괴된 객체에 접근하는 것을 방지
        for _timer_attr in (
            # GCal 관련
            "gcal_sync_timer",
            "gcal_quick_sync_timer",
            "gcal_sleep_timer",
            "gcal_sleep_poll_timer",
            "gcal_idle_timer",
            "_wake_sync_timer",
            "search_debounce_timer",
            "_sync_anim_timer",
            # 오버레이 텍스트 위젯
            "_stopwatch_timer",
            "_countdown_timer",
            "_slow_text_timer",
            # 패널 갱신
            "_ui_refresh_timer",
            # 잠금화면
            "_away_admin_hold_timer",
            "_away_password_focus_timer",
            "_lock_clock_timer",
            "_overlay_unlock_timer",
            "_daily_summary_timer",
        ):
            _t = getattr(self, _timer_attr, None)
            if _t is not None:
                import contextlib

                with contextlib.suppress(RuntimeError):
                    _t.stop()

        # 백그라운드 QThread 워커 종료 — msleep 중인 스레드가 이벤트 루프 소멸 후
        # Qt 내부 시설에 접근해 SIGABRT를 일으키는 것을 방지
        for _worker_attr in ("alarm_worker",):
            _w = getattr(self, _worker_attr, None)
            if _w is not None:
                try:
                    if hasattr(_w, "stop"):
                        _w.stop()
                    _w.quit()
                    _w.wait(2000)
                except RuntimeError:
                    pass

        save_window_layout(self)
        super().closeEvent(event)

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

        # Keep lock overlay/background aligned with resized window.
        if hasattr(self, "lock_frame") and self.lock_frame.isVisible():
            self.lock_frame.setGeometry(0, 0, self.width(), self.height())
            if hasattr(self, "lock_bg_label"):
                self.lock_bg_label.setGeometry(self.lock_frame.rect())

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

    def move_to_next_monitor(self):
        from PyQt6.QtGui import QGuiApplication

        screens = QGuiApplication.screens()
        if len(screens) <= 1:
            return

        current_screen = QGuiApplication.screenAt(self.geometry().center())
        if not current_screen:
            current_screen = screens[0]

        idx = screens.index(current_screen)
        next_idx = (idx + 1) % len(screens)
        target_screen = screens[next_idx]

        old_geom = current_screen.geometry()
        new_geom = target_screen.geometry()

        rel_x = (self.x() - old_geom.x()) / old_geom.width()
        rel_y = (self.y() - old_geom.y()) / old_geom.height()

        new_x = new_geom.x() + int(rel_x * new_geom.width())
        new_y = new_geom.y() + int(rel_y * new_geom.height())

        self.move(new_x, new_y)
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
