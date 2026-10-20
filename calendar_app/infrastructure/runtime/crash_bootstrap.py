# -*- coding: utf-8 -*-
"""Crash/log bootstrap helpers for app entrypoint."""

from __future__ import annotations

import faulthandler
import logging
import logging.handlers
import os
import sqlite3
import sys
from typing import TextIO

# 로그 파일 크기 상한: 5MB × (본 파일 + 백업 2개)
_LOG_MAX_BYTES = 5 * 1024 * 1024
_LOG_BACKUP_COUNT = 2


def show_database_startup_error(
    error: sqlite3.Error | OSError, *, database_path: str | None = None
) -> None:
    """Show a data-preserving diagnostic, including failures before bootstrap imports."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QMessageBox

    from calendar_app.domain.i18n import t

    # Keep the application alive while an import-time error's dialog is modal.
    application = QApplication.instance() or QApplication(sys.argv)
    code = (getattr(error, "sqlite_errorcode", 0) or 0) & 0xFF
    if code in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB):
        message = t(
            "startup_database.corrupt",
            "일정 데이터베이스의 손상이 확인됐습니다. 원본 파일을 보존한 뒤 복구가 필요합니다.",
        )
    elif code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
        message = t(
            "startup_database.locked",
            "다른 프로세스가 일정 데이터베이스를 사용 중입니다. 다른 Air Calendar 실행을 닫고 다시 시도해 주세요.",
        )
    else:
        message = t(
            "startup_database.unavailable",
            "일정 데이터베이스를 열 수 없습니다. 저장 공간과 앱 데이터 폴더의 접근 권한을 확인해 주세요.",
        )
    dialog = QMessageBox()
    dialog.setIcon(QMessageBox.Icon.Critical)
    dialog.setWindowTitle(t("startup_database.title", "Air Calendar를 시작할 수 없습니다"))
    dialog.setTextFormat(Qt.TextFormat.PlainText)
    dialog.setText(message)
    dialog.setInformativeText(
        t(
            "startup_database.details",
            "자세히 보기를 열면 데이터베이스 경로와 원래 오류를 확인할 수 있습니다.",
        )
    )
    path = (
        database_path
        or getattr(error, "database_path", None)
        or getattr(error, "filename", None)
        or ""
    )
    source = getattr(error, "database_source", None)
    context = f"{path}\nsource={source}" if source else path
    dialog.setDetailedText(
        f"{context}\n{getattr(error, 'sqlite_errorname', type(error).__name__)}\n{error}"
    )
    dialog.setStandardButtons(QMessageBox.StandardButton.Close)
    dialog.exec()
    # An application created only for this failure has no main event loop to enter.
    application.processEvents()


def _trim_oversized_log(log_path: str) -> None:
    """로테이션 도입 전 무한히 커진 기존 로그 파일을 정리한다."""
    try:
        if os.path.exists(log_path) and os.path.getsize(log_path) > _LOG_MAX_BYTES * (
            _LOG_BACKUP_COUNT + 1
        ):
            os.remove(log_path)
    except OSError:
        pass


def setup_crash_logging(log_path: str | None = None) -> TextIO | None:
    if log_path is None:
        # Use AppData/Local for writable log file when frozen or installed.
        base_dir = os.environ.get("LOCALAPPDATA")
        if not base_dir:
            base_dir = os.path.join(os.path.expanduser("~"), "AppData", "Local")

        app_dir = os.path.join(base_dir, "kimhyojin", "Dark Calendar")
        try:
            if not os.path.exists(app_dir):
                os.makedirs(app_dir, exist_ok=True)
            log_path = os.path.join(app_dir, "crash.log")
        except Exception:
            # Fallback to temp dir if AppData fails
            log_path = os.path.join(os.environ.get("TEMP", "."), "desk_calendar_crash.log")

    _trim_oversized_log(log_path)

    # 개인정보 최소 기록 원칙: 기본 INFO. 진단 시에만 환경변수로 DEBUG 활성화.
    debug_enabled = os.environ.get("DARK_CALENDAR_DEBUG", "").strip() in ("1", "true", "on")
    logging.basicConfig(
        level=logging.DEBUG if debug_enabled else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
        handlers=[
            logging.handlers.RotatingFileHandler(
                log_path,
                maxBytes=_LOG_MAX_BYTES,
                backupCount=_LOG_BACKUP_COUNT,
                encoding="utf-8",
                errors="strict",
            ),
            logging.StreamHandler(sys.stdout),
        ],
    )
    crash_logger = logging.getLogger("crash")

    stream: TextIO | None = None
    try:
        stream = open(log_path, "a", encoding="utf-8", errors="strict")  # noqa: SIM115
        faulthandler.enable(file=stream, all_threads=True)
    except Exception:
        crash_logger.exception("Failed to enable faulthandler")

    def _global_excepthook(exc_type, exc_value, exc_tb):
        """미처리 예외를 crash.log에 기록하고 콘솔에도 출력"""
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        crash_logger.critical(
            "Unhandled exception:",
            exc_info=(exc_type, exc_value, exc_tb),
        )

    sys.excepthook = _global_excepthook
    return stream


def teardown_crash_logging(stream: TextIO | None) -> None:
    try:
        faulthandler.disable()
        if stream is not None:
            stream.close()
    except Exception:
        pass
