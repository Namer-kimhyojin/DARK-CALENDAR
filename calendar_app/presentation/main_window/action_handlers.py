# -*- coding: utf-8 -*-
"""ActionHandlers mixin composition root."""

import contextlib
import logging

from PyQt6.QtWidgets import QApplication, QMessageBox

from calendar_app.app_metadata import APP_NAME
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_router import DialogActionsMixin
from calendar_app.presentation.main_window.action_handlers_gcal import GCalActionsMixin
from calendar_app.presentation.main_window.action_handlers_tasks import TaskActionsMixin
from calendar_app.presentation.main_window.away_lock_actions import AwayLockMixin
from calendar_app.presentation.main_window.calendar_view_actions import CalendarViewActionsMixin
from calendar_app.presentation.main_window.refresh_scheduler import RefreshSchedulerMixin
from calendar_app.presentation.main_window.routine_actions import RoutineActionsMixin
from calendar_app.presentation.main_window.theme_actions import ThemeActionsMixin
from calendar_app.presentation.main_window.window_shell_actions import WindowShellActionsMixin

logger = logging.getLogger(__name__)

_SHUTDOWN_TIMER_ATTRS = (
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
)


def _release_single_instance_lock(app) -> None:
    """Detach the shared-memory lock explicitly and tolerate Qt teardown."""

    shared_memory = getattr(app, "_shared_memory", None) if app is not None else None
    if shared_memory is None:
        return
    try:
        if shared_memory.isAttached():
            shared_memory.detach()
    except (AttributeError, RuntimeError):
        logger.debug("Single-instance lock was already released", exc_info=True)
    with contextlib.suppress(AttributeError, RuntimeError):
        delattr(app, "_shared_memory")


def _save_window_layout_for_shutdown(window) -> bool:
    """Best-effort layout persistence that never prevents application exit."""

    if getattr(window, "_layout_saved", False):
        return True
    try:
        from calendar_app.presentation.main_window.window_restore_helpers import (
            save_window_layout,
        )

        return bool(save_window_layout(window))
    except Exception:
        logger.exception("Failed to save window layout during shutdown")
        return False


def _detached_process_started(result) -> bool:
    """Normalize PyQt's platform-dependent startDetached return shape."""

    if isinstance(result, tuple):
        return bool(result[0]) if result else False
    return bool(result)


def _build_exit_confirmation_box(parent) -> QMessageBox:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(t("app.exit_title", "종료 안내"))
    box.setText(
        t(
            "app.exit_message",
            f"{APP_NAME}를 종료합니다.\n트레이로 전환되지 않고 프로그램이 완전히 종료됩니다.\n계속하시겠습니까?",
        )
    )
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.No)
    box.setStyleSheet("QLabel { font-size: 10pt; }")
    return box


class ActionHandlersMixin(
    WindowShellActionsMixin,
    CalendarViewActionsMixin,
    RoutineActionsMixin,
    AwayLockMixin,
    ThemeActionsMixin,
    RefreshSchedulerMixin,
    GCalActionsMixin,
    DialogActionsMixin,
    TaskActionsMixin,
):
    def _confirm_app_exit(self) -> bool:
        reply = _build_exit_confirmation_box(self).exec()
        return reply == QMessageBox.StandardButton.Yes

    def show_calendar_help(self):
        """캘린더 도움말 표시 (DialogActionsMixin에서 상속받은 메서드 명시적 호출)"""
        if hasattr(super(), "show_calendar_help"):
            super().show_calendar_help()
        else:
            DialogActionsMixin.show_calendar_help(self)

    def shutdown_background_workers(self, wait_ms=500):
        if getattr(self, "_shutdown_complete", False):
            return True
        if getattr(self, "_shutdown_in_progress", False):
            return False

        self._is_shutting_down = True
        self._shutdown_in_progress = True
        logger.info("Shutting down background workers...")

        def _is_running(w) -> bool:
            """Qt 객체가 이미 삭제된 경우 RuntimeError를 무시하고 False를 반환."""
            try:
                return w is not None and w.isRunning()
            except RuntimeError:
                return False

        def _stop_worker(worker, label, *, stop_method=None) -> bool:
            if not _is_running(worker):
                return True

            try:
                if stop_method is not None:
                    stop_method()
                else:
                    worker.requestInterruption()
                quit_method = getattr(worker, "quit", None)
                if callable(quit_method):
                    quit_method()
            except RuntimeError:
                return True
            except Exception:
                logger.exception("Failed to request cooperative shutdown for %s", label)

            try:
                if worker.wait(wait_ms):
                    return True

                grace_ms = max(1500, int(wait_ms) * 3)
                logger.warning(
                    "%s did not stop within %dms; waiting %dms more without forced termination",
                    label,
                    wait_ms,
                    grace_ms,
                )
                if not worker.wait(grace_ms):
                    logger.error(
                        "%s is still running after cooperative shutdown; "
                        "QThread.terminate() was intentionally skipped",
                        label,
                    )
                    return False
                return True
            except RuntimeError:
                return True
            except Exception:
                logger.exception("Failed while waiting for %s shutdown", label)
                return False

        shutdown_succeeded = True
        try:
            # Stop every known application timer before waiting for workers so
            # no new refresh/auth/sync work can be scheduled during teardown.
            for timer_name in _SHUTDOWN_TIMER_ATTRS:
                timer = getattr(self, timer_name, None)
                if timer is not None:
                    try:
                        timer.stop()
                    except (AttributeError, RuntimeError):
                        continue
                    except Exception:
                        logger.exception("Failed to stop timer %s", timer_name)

            if hasattr(self, "close_widget_mode_panels"):
                try:
                    self.close_widget_mode_panels()
                except Exception:
                    logger.exception("Failed to close widget-mode panels")

            overlay_manager = getattr(self, "overlay_manager", None)
            shutdown_overlays = getattr(overlay_manager, "shutdown", None)
            if callable(shutdown_overlays):
                try:
                    shutdown_overlays()
                except Exception:
                    logger.exception("Failed to shut down desktop overlay widgets")

            seen_workers: set[int] = set()

            def _stop_once(worker, label, *, stop_method=None) -> bool:
                if worker is None or id(worker) in seen_workers:
                    return True
                seen_workers.add(id(worker))
                return _stop_worker(worker, label, stop_method=stop_method)

            if not _stop_once(getattr(self, "_sync_worker", None), "sync_worker"):
                shutdown_succeeded = False
            if not _stop_once(getattr(self, "_auth_worker", None), "auth_worker"):
                shutdown_succeeded = False
            for index, worker in enumerate(list(getattr(self, "_bg_workers", [])), start=1):
                if not _stop_once(worker, f"background_worker[{index}]"):
                    shutdown_succeeded = False

            alarm_worker = getattr(self, "alarm_worker", None)
            if not _stop_once(
                alarm_worker,
                "alarm_worker",
                stop_method=getattr(alarm_worker, "stop", None),
            ):
                shutdown_succeeded = False

            task_alarm_checker = getattr(self, "task_alarm_checker", None)
            if task_alarm_checker is not None:
                try:
                    task_alarm_checker.stop()
                except (AttributeError, RuntimeError):
                    pass
                except Exception:
                    logger.exception("Failed to stop task_alarm_checker")

            # This is a Python daemon thread, not a QThread, so it must be
            # stopped explicitly before database connections and Qt objects
            # disappear.  atexit remains only as a final fallback.
            try:
                from calendar_app.infrastructure.google_sync.push_queue import gcal_push_queue

                stopped = gcal_push_queue.stop(timeout=max(1.5, int(wait_ms) / 1000 * 3))
                if not stopped:
                    logger.error("gcal_push_queue is still running after shutdown timeout")
                    shutdown_succeeded = False
            except Exception:
                logger.exception("Failed to stop gcal_push_queue")
                shutdown_succeeded = False

            settings = getattr(self, "settings", None)
            sync_settings = getattr(settings, "sync", None)
            if callable(sync_settings):
                try:
                    sync_settings()
                except (AttributeError, RuntimeError):
                    pass
                except Exception:
                    logger.exception("Failed to flush application settings")
        finally:
            self._shutdown_in_progress = False
            self._shutdown_complete = shutdown_succeeded
        return shutdown_succeeded

    def request_app_exit(self, checked=False):
        if not self._confirm_app_exit():
            return

        self._exit_requested = True
        self.shutdown_background_workers()
        tray_icon = getattr(self, "tray_icon", None)
        if tray_icon is not None:
            tray_icon.hide()

        _save_window_layout_for_shutdown(self)

        app = QApplication.instance()
        self.close()
        if app is not None:
            app.quit()

    def set_language(self, lang_code):
        import os
        import sys

        from PyQt6.QtCore import QProcess

        from calendar_app.infrastructure.i18n import t

        previous_language = self.settings.value("language")
        if previous_language == lang_code:
            return

        self.settings.setValue("language", lang_code)
        self.settings.sync()  # Ensure it's saved

        msg = t(
            "system_msg.lang_saved_msg",
            "언어 설정이 저장되었습니다.\n변경사항을 적용하기 위해 앱을 재시작합니다.",
        )
        title = t("system_msg.lang_saved_title", "언어 설정")

        QMessageBox.information(self, title, msg)

        # Commit the live layout, overlay positions, and every pending
        # QSettings write before the replacement process can read them.
        from calendar_app.presentation.main_window.window_restore_helpers import (
            flush_window_layout,
        )

        if not flush_window_layout(self):
            logger.error("Cancelled language restart because session state could not be saved")
            self.settings.setValue("language", previous_language)
            self.settings.sync()
            QMessageBox.warning(
                self,
                title,
                t(
                    "system_msg.restart_failed",
                    "앱 상태를 저장하지 못해 자동 재시작을 취소했습니다. 다시 시도해 주세요.",
                ),
            )
            return

        # Determine the executable to run
        if getattr(sys, "frozen", False):
            # If running as a bundled executable
            executable = sys.executable
            args = sys.argv[1:]
        else:
            # If running from source
            executable = sys.executable
            # Ensure the script path is absolute for reliability
            args = [os.path.abspath(sys.argv[0])] + sys.argv[1:]

        # Extract the root directory to use as working directory
        cwd = os.path.dirname(os.path.abspath(sys.argv[0]))

        logger.info("Restarting application via %s %s in %s", executable, args, cwd)

        # Use startDetached with working directory for better stability on Windows.
        # Only tear down this process once the replacement was accepted by Qt.
        if not _detached_process_started(QProcess.startDetached(executable, args, cwd)):
            logger.error("Failed to start replacement process for language change")
            QMessageBox.warning(
                self,
                title,
                t(
                    "system_msg.restart_failed",
                    "앱을 자동으로 다시 시작하지 못했습니다. 앱을 직접 다시 실행해 주세요.",
                ),
            )
            return

        self._exit_requested = True
        self.shutdown_background_workers(wait_ms=200)
        _save_window_layout_for_shutdown(self)
        app = QApplication.instance()
        logger.info("Application restarting after graceful shutdown")
        self.close()
        if app is not None:
            app.quit()

    def _restart_application_for_locale_tools(self):
        import os
        import sys

        from PyQt6.QtCore import QProcess

        from calendar_app.presentation.main_window.window_restore_helpers import (
            flush_window_layout,
        )

        if not flush_window_layout(self):
            logger.error("Cancelled locale-tools restart because session state could not be saved")
            QMessageBox.warning(
                self,
                t("menu.locale_tools", "로케일 파일 관리"),
                t(
                    "system_msg.restart_failed",
                    "앱 상태를 저장하지 못해 자동 재시작을 취소했습니다. 다시 시도해 주세요.",
                ),
            )
            return

        if getattr(sys, "frozen", False):
            executable = sys.executable
            args = sys.argv[1:]
        else:
            executable = sys.executable
            args = [os.path.abspath(sys.argv[0])] + sys.argv[1:]

        cwd = os.path.dirname(os.path.abspath(sys.argv[0]))
        logger.info("Restarting application via %s %s in %s", executable, args, cwd)
        if not _detached_process_started(QProcess.startDetached(executable, args, cwd)):
            logger.error("Failed to start replacement process from locale tools")
            QMessageBox.warning(
                self,
                t("menu.locale_tools", "로케일 파일 관리"),
                t(
                    "system_msg.restart_failed",
                    "앱을 자동으로 다시 시작하지 못했습니다. 앱을 직접 다시 실행해 주세요.",
                ),
            )
            return

        self._exit_requested = True
        self.shutdown_background_workers(wait_ms=200)
        _save_window_layout_for_shutdown(self)
        app = QApplication.instance()
        logger.info("Application restarting from locale tools after graceful shutdown")
        self.close()
        if app is not None:
            app.quit()

    def open_locale_override_folder(self):
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices

        from calendar_app.infrastructure.i18n import get_user_locales_dir, t

        folder = get_user_locales_dir(create=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            QMessageBox.warning(
                self,
                t("menu.locale_tools", "로케일 파일 관리"),
                t("menu.locale_open_fail", "로케일 폴더를 열지 못했습니다."),
            )

    def open_current_locale_file(self):
        import os

        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices

        from calendar_app.infrastructure.i18n import ensure_user_locale_file, t

        lang_code = str(self.settings.value("language", "ko") or "ko").strip() or "ko"
        locale_path = ensure_user_locale_file(lang_code)

        opened = False
        try:
            if os.name == "nt":
                os.startfile(str(locale_path))
                opened = True
            else:
                opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(locale_path)))
        except Exception:
            opened = False

        if not opened:
            QMessageBox.warning(
                self,
                t("menu.locale_tools", "로케일 파일 관리"),
                t("menu.locale_open_file_fail", "현재 언어 파일을 열지 못했습니다."),
            )
            return

        QMessageBox.information(
            self,
            t("menu.locale_tools", "로케일 파일 관리"),
            t("menu.locale_edit_hint", "파일 수정 후 앱을 재시작하면 변경사항이 반영됩니다."),
        )

    def validate_current_locale_override(self):
        from calendar_app.infrastructure.i18n import t, validate_user_locale_file

        lang_code = str(self.settings.value("language", "ko") or "ko").strip() or "ko"
        ok, message = validate_user_locale_file(lang_code)
        if ok:
            QMessageBox.information(self, t("menu.locale_tools", "로케일 파일 관리"), message)
        else:
            QMessageBox.warning(self, t("menu.locale_tools", "로케일 파일 관리"), message)

    def reset_current_locale_override(self):
        from calendar_app.infrastructure.i18n import remove_user_locale_override, t

        lang_code = str(self.settings.value("language", "ko") or "ko").strip() or "ko"
        reply = QMessageBox.question(
            self,
            t("menu.locale_tools", "로케일 파일 관리"),
            t("menu.locale_reset_confirm", "현재 언어의 사용자 로케일 오버라이드를 삭제할까요?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        removed = remove_user_locale_override(lang_code)
        if not removed:
            QMessageBox.information(
                self,
                t("menu.locale_tools", "로케일 파일 관리"),
                t("menu.locale_reset_no_file", "삭제할 사용자 오버라이드 파일이 없습니다."),
            )
            return

        QMessageBox.information(
            self,
            t("menu.locale_tools", "로케일 파일 관리"),
            t("menu.locale_reset_done", "오버라이드 파일을 삭제했습니다. 앱을 재시작합니다."),
        )
        self._restart_application_for_locale_tools()
