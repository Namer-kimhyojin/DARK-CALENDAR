# -*- coding: utf-8 -*-
"""ActionHandlers mixin composition root."""

import logging

from PyQt6.QtWidgets import QApplication, QMessageBox

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


def _build_exit_confirmation_box(parent) -> QMessageBox:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(t("app.exit_title", "종료 안내"))
    box.setText(
        t(
            "app.exit_message",
            "Dark Calendar를 종료합니다.\n트레이로 전환되지 않고 프로그램이 완전히 종료됩니다.\n계속하시겠습니까?",
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
        if getattr(self, "_is_shutting_down", False):
            return

        self._is_shutting_down = True
        logger.info("Shutting down background workers...")

        if hasattr(self, "close_widget_mode_panels"):
            try:
                self.close_widget_mode_panels()
            except Exception:
                logger.exception("Failed to close widget-mode panels")

        # 1. Stop all timers
        for timer_name in (
            "gcal_sync_timer",
            "gcal_quick_sync_timer",
            "gcal_sleep_timer",
            "gcal_sleep_poll_timer",
            "search_debounce_timer",
            "_ui_refresh_timer",
            "_sync_anim_timer",
            "_system_theme_refresh_timer",
        ):
            timer = getattr(self, timer_name, None)
            if timer is not None:
                try:
                    timer.stop()
                except Exception:
                    logger.exception("Failed to stop timer %s", timer_name)

        def _is_running(w) -> bool:
            """Qt 객체가 이미 삭제된 경우 RuntimeError를 무시하고 False를 반환."""
            try:
                return w is not None and w.isRunning()
            except RuntimeError:
                return False

        # 2. Stop GCal sync worker
        sync_worker = getattr(self, "_sync_worker", None)
        if _is_running(sync_worker):
            sync_worker.requestInterruption()
            if not sync_worker.wait(wait_ms):
                logger.warning("Force terminating sync_worker")
                sync_worker.terminate()
                sync_worker.wait(200)

        # 3. Stop general background workers
        for worker in list(getattr(self, "_bg_workers", [])):
            if _is_running(worker):
                worker.requestInterruption()
                if not worker.wait(wait_ms):
                    logger.warning("Force terminating background worker")
                    worker.terminate()
                    worker.wait(200)

        # 4. Stop AlarmWorker (Idle Detector)
        alarm_worker = getattr(self, "alarm_worker", None)
        if _is_running(alarm_worker):
            try:
                alarm_worker.stop()
                if not alarm_worker.wait(wait_ms):
                    logger.warning("Force terminating alarm_worker")
                    alarm_worker.terminate()
                    alarm_worker.wait(200)
            except RuntimeError:
                pass
            except Exception:
                logger.exception("Failed to stop alarm worker")

        # 5. Stop TaskAlarmChecker
        task_alarm_checker = getattr(self, "task_alarm_checker", None)
        if task_alarm_checker is not None:
            try:
                task_alarm_checker.stop()
            except Exception:
                logger.exception("Failed to stop task_alarm_checker")

    def request_app_exit(self, checked=False):
        if not self._confirm_app_exit():
            return

        self.shutdown_background_workers()
        tray_icon = getattr(self, "tray_icon", None)
        if tray_icon is not None:
            tray_icon.hide()

        # 종료 전 윈도우 레이아웃 저장
        from calendar_app.presentation.main_window.window_restore_helpers import save_window_layout

        save_window_layout(self)

        # Explicitly release single instance lock if it exists to help with restarts
        app = QApplication.instance()
        if hasattr(app, "_shared_memory"):
            # Deleting the shared memory object or detaching it helps the new process start
            del app._shared_memory

        self.close()
        app.quit()

    def set_language(self, lang_code):
        import os
        import sys

        from PyQt6.QtCore import QProcess

        from calendar_app.infrastructure.i18n import t

        if self.settings.value("language") == lang_code:
            return

        self.settings.setValue("language", lang_code)
        self.settings.sync()  # Ensure it's saved

        msg = t(
            "system_msg.lang_saved_msg",
            "언어 설정이 저장되었습니다.\n변경사항을 적용하기 위해 앱을 재시작합니다.",
        )
        title = t("system_msg.lang_saved_title", "언어 설정")

        QMessageBox.information(self, title, msg)

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

        # Use startDetached with working directory for better stability on Windows
        QProcess.startDetached(executable, args, cwd)

        # Shutdown background workers and release the lock immediately
        self.shutdown_background_workers(wait_ms=200)
        app = QApplication.instance()
        if hasattr(app, "_shared_memory"):
            app._shared_memory.detach()
            del app._shared_memory

        # Give a small window for the OS to see the detach, then force exit
        logger.info("Application restarting, forcing exit in 500ms...")
        from PyQt6.QtCore import QTimer

        QTimer.singleShot(500, lambda: os._exit(0))

    def _restart_application_for_locale_tools(self):
        import os
        import sys

        from PyQt6.QtCore import QProcess, QTimer

        if getattr(sys, "frozen", False):
            executable = sys.executable
            args = sys.argv[1:]
        else:
            executable = sys.executable
            args = [os.path.abspath(sys.argv[0])] + sys.argv[1:]

        cwd = os.path.dirname(os.path.abspath(sys.argv[0]))
        logger.info("Restarting application via %s %s in %s", executable, args, cwd)
        QProcess.startDetached(executable, args, cwd)

        self.shutdown_background_workers(wait_ms=200)
        app = QApplication.instance()
        if hasattr(app, "_shared_memory"):
            app._shared_memory.detach()
            del app._shared_memory

        logger.info("Application restarting from locale tools, forcing exit in 500ms...")
        QTimer.singleShot(500, lambda: os._exit(0))

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
