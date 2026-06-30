"""Idle detection worker using win32api when available."""

import logging
import time

from PyQt6.QtCore import QThread, pyqtSignal

try:
    import win32api

    HAS_WIN32 = True
except ImportError:
    win32api = None
    HAS_WIN32 = False

logger = logging.getLogger(__name__)


def _safe_last_input_tick():
    if not HAS_WIN32:
        return None
    try:
        return int(win32api.GetLastInputInfo()) & 0xFFFFFFFF
    except Exception:
        return None


def _safe_tick_count():
    if not HAS_WIN32:
        return None
    try:
        return int(win32api.GetTickCount()) & 0xFFFFFFFF
    except Exception:
        return None


def _safe_cursor_pos():
    if not HAS_WIN32:
        return None
    try:
        return win32api.GetCursorPos()
    except Exception:
        return None


class AlarmWorker(QThread):
    idle_status_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.app = parent
        self.is_running = True
        self._is_idle = False
        self._last_elapsed_ms = 0
        self._idle_timeout_ms = 5 * 60 * 1000
        self._last_cursor_pos = None
        self.suppress_unlock = False
        self._suppress_lock_until = 0.0

        if parent and hasattr(parent, "settings"):
            interval = int(parent.settings.value("away_interval", 5))
            self._idle_timeout_ms = interval * 60 * 1000

    @property
    def is_idle(self):
        return self._is_idle

    @is_idle.setter
    def is_idle(self, value):
        self._is_idle = bool(value)

    @property
    def idle_timeout_ms(self):
        return self._idle_timeout_ms

    @idle_timeout_ms.setter
    def idle_timeout_ms(self, value):
        self._idle_timeout_ms = int(value)

    def update_idle_timeout(self, minutes):
        self.idle_timeout_ms = minutes * 60 * 1000
        logger.info("Idle timeout updated to %s minutes.", minutes)

    def _has_activity_resumed(self, elapsed_ms):
        """
        Detect fresh input after idle by noticing elapsed idle time reset,
        or by detecting cursor movement when GetLastInputInfo is unchanged.
        """
        if elapsed_ms < 0:
            return True
        if elapsed_ms < 5000:
            return True
        if elapsed_ms < self._last_elapsed_ms:
            return True

        pos = _safe_cursor_pos()
        if pos is not None:
            if self._last_cursor_pos is not None and pos != self._last_cursor_pos:
                self._last_cursor_pos = pos
                return True
            self._last_cursor_pos = pos
        return False

    def run(self):
        if not HAS_WIN32:
            logger.warning("win32api not found. Idle detection is disabled on this device.")
            while self.is_running and not self.isInterruptionRequested():
                self.msleep(500)
            return

        logger.info("AlarmWorker (IdleDetector) started.")
        while self.is_running and not self.isInterruptionRequested():
            try:
                last_input_tick = _safe_last_input_tick()
                current_tick = _safe_tick_count()
                if last_input_tick is None or current_tick is None:
                    self.msleep(200)
                    continue

                elapsed = (current_tick - last_input_tick) & 0xFFFFFFFF

                if (
                    not self._is_idle
                    and elapsed >= self._idle_timeout_ms
                    and time.monotonic() >= self._suppress_lock_until
                ):
                    self._is_idle = True
                    self._last_cursor_pos = _safe_cursor_pos()
                    logger.info(
                        "[LOCK] Idle detected. elapsed=%s timeout=%s cursor=%s",
                        elapsed,
                        self._idle_timeout_ms,
                        self._last_cursor_pos,
                    )
                    self.idle_status_changed.emit(True)
                elif self._is_idle and self._has_activity_resumed(elapsed):
                    if self.suppress_unlock:
                        self._last_elapsed_ms = max(0, int(elapsed))
                        pos = _safe_cursor_pos()
                        if pos is not None:
                            self._last_cursor_pos = pos
                        continue
                    self._is_idle = False
                    logger.info(
                        "[UNLOCK] Activity detected. elapsed=%s last_elapsed=%s cursor=%s",
                        elapsed,
                        self._last_elapsed_ms,
                        self._last_cursor_pos,
                    )
                    self.idle_status_changed.emit(False)
                elif self._is_idle:
                    logger.debug(
                        "[IDLE-WAIT] elapsed=%s last_elapsed=%s cursor=%s",
                        elapsed,
                        self._last_elapsed_ms,
                        self._last_cursor_pos,
                    )

                self._last_elapsed_ms = max(0, int(elapsed))
            except Exception:
                pass

            for _ in range(10):
                if not self.is_running or self.isInterruptionRequested():
                    break
                self.msleep(100)

    def stop(self):
        self.is_running = False
        self.requestInterruption()
        logger.info("AlarmWorker stopping...")
