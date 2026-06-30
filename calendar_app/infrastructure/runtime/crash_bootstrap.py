"""Crash/log bootstrap helpers for app entrypoint."""

from __future__ import annotations

import faulthandler
import logging
import os
import sys
from typing import TextIO


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

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8", errors="strict"),
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
