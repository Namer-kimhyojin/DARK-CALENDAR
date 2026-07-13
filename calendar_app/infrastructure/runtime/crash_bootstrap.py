# -*- coding: utf-8 -*-
"""Crash/log bootstrap helpers for app entrypoint."""

from __future__ import annotations

import faulthandler
import logging
import logging.handlers
import os
import sys
from typing import TextIO

# 로그 파일 크기 상한: 5MB × (본 파일 + 백업 2개)
_LOG_MAX_BYTES = 5 * 1024 * 1024
_LOG_BACKUP_COUNT = 2


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
