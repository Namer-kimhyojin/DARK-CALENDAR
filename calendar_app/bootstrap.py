"""Application bootstrap/runtime entry helpers."""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time

from PyQt6.QtCore import (
    QCoreApplication,
    QSettings,
    QSharedMemory,
    QTimer,
    QtMsgType,
    qInstallMessageHandler,
)
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from calendar_app.app_metadata import APP_NAME
from calendar_app.app_paths import APP_ICON_PATH
from calendar_app.domain.i18n import set_translator as set_domain_translator
from calendar_app.infrastructure.i18n import t

set_domain_translator(t)

_STARTUP_PHASE_SPECS = (
    ("preparing_runtime", 2, False),
    ("loading_ui_modules", 4, False),
    ("loading_font", 2, False),
    ("initializing_db", 7, True),
    ("migrating_data", 4, True),
    ("loading_labels", 2, True),
    ("starting_ui", 5, False),
    ("ready", 1, False),
)
_STARTUP_PHASE_MIN_MS = {
    "preparing_runtime": 40,
    "loading_ui_modules": 80,
    "loading_font": 30,
    "initializing_db": 80,
    "migrating_data": 50,
    "loading_labels": 20,
    "starting_ui": 120,
    "ready": 80,
}
_STARTUP_PHASE_SOFT_CAP_RATIO = 0.84


def _install_qt_message_handler() -> None:
    qt_logger = logging.getLogger("Qt")

    def _qt_message_handler(msg_type, _, msg):
        if "Point size" in msg and "<=" in msg:
            return
        if "QWidgetWindow(" in msg and "must be a top level window" in msg:
            return
        # Qt6 + Windows high-DPI: Tool windows briefly report a geometry mismatch
        # while layout sizes are being negotiated during resize/init.  These are
        # harmless and extremely noisy, so suppress them entirely.
        if "QWindowsWindow::setGeometry: Unable to set geometry" in msg:
            return
        if msg_type == QtMsgType.QtDebugMsg:
            qt_logger.debug(msg)
        elif msg_type == QtMsgType.QtWarningMsg:
            qt_logger.warning(msg)
        elif msg_type == QtMsgType.QtCriticalMsg:
            qt_logger.error(msg)
        elif msg_type == QtMsgType.QtFatalMsg:
            qt_logger.critical("Qt FATAL: %s", msg)

    qInstallMessageHandler(_qt_message_handler)


def _acquire_single_instance_lock() -> tuple[bool, QSharedMemory]:
    import time

    shared_memory = QSharedMemory("DarkCalendar_SingleInstance_Lock")
    # Try for up to 2 seconds to allow previous process to exit (for restarts)
    for _ in range(20):
        if shared_memory.create(1):
            return True, shared_memory
        time.sleep(0.1)
    return False, shared_memory


def _apply_saved_font(app: QApplication, build_ui_font) -> None:
    settings = QSettings("kimhyojin", "Dark Calendar")
    family = settings.value("font_family", "Segoe UI")
    size = settings.value("font_size", 10, type=int)
    if size <= 0:
        size = 10
        settings.setValue("font_size", size)
    app.setFont(build_ui_font(family, size))


def _build_startup_phase_ranges(specs=_STARTUP_PHASE_SPECS) -> dict[str, tuple[float, float]]:
    total_weight = sum(max(0, int(weight)) for _, weight, _ in specs) or 1
    ranges: dict[str, tuple[float, float]] = {}
    consumed = 0

    for phase_name, weight, _threaded in specs:
        phase_weight = max(0, int(weight))
        start = consumed / total_weight
        consumed += phase_weight
        end = consumed / total_weight
        ranges[phase_name] = (start, end)

    return ranges


def _phase_soft_cap(start: float, end: float) -> float:
    span = max(0.0, end - start)
    if span <= 0.0:
        return end
    soft_ratio = 0.90 if end >= 1.0 else _STARTUP_PHASE_SOFT_CAP_RATIO
    soft_cap = start + (span * soft_ratio)
    soft_cap = min(end - 0.008, soft_cap)
    soft_cap = max(start + min(0.02, span), soft_cap)
    return min(end, max(start, soft_cap))


def _advance_phase_progress(progress: float, soft_cap: float) -> float:
    delta = soft_cap - progress
    if delta <= 0.0005:
        return soft_cap
    step = max(0.0025, min(0.012, delta * 0.22))
    return min(soft_cap, progress + step)


def _settle_splash_phase(
    app: QApplication,
    splash,
    *,
    text: str,
    progress: float,
    end: float,
    started_at: float,
    min_duration_ms: int,
) -> None:
    min_duration_s = max(0, int(min_duration_ms)) / 1000.0
    while time.monotonic() - started_at < min_duration_s:
        app.processEvents()
        time.sleep(0.012)
    splash.set_status(text, end)
    app.processEvents()


def _run_splash_phase(
    app: QApplication,
    splash,
    *,
    text: str,
    start: float,
    end: float,
    work=None,
    threaded: bool = True,
    min_duration_ms: int = 0,
):
    started_at = time.monotonic()
    progress = max(0.0, start)
    soft_cap = _phase_soft_cap(start, end)
    splash.set_status(text, progress)
    app.processEvents()

    if work is None:
        _settle_splash_phase(
            app,
            splash,
            text=text,
            progress=progress,
            end=end,
            started_at=started_at,
            min_duration_ms=min_duration_ms,
        )
        return None

    if not threaded:
        result = work()
        _settle_splash_phase(
            app,
            splash,
            text=text,
            progress=progress,
            end=end,
            started_at=started_at,
            min_duration_ms=min_duration_ms,
        )
        return result

    state = {"result": None, "exc": None, "tb": None}

    def _runner():
        try:
            state["result"] = work()
        except BaseException as exc:  # pragma: no cover - re-raised on main thread
            state["exc"] = exc
            state["tb"] = exc.__traceback__

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    while thread.is_alive():
        progress = _advance_phase_progress(progress, soft_cap)
        splash.set_status(text, progress)
        app.processEvents()
        thread.join(0.015)
        time.sleep(0.005)

    _settle_splash_phase(
        app,
        splash,
        text=text,
        progress=progress,
        end=end,
        started_at=started_at,
        min_duration_ms=min_duration_ms,
    )
    if state["exc"] is not None:
        raise state["exc"].with_traceback(state["tb"])
    return state["result"]


def run(overlay_cls=None, build_ui_font=None) -> int:
    QCoreApplication.setOrganizationName("kimhyojin")
    QCoreApplication.setApplicationName("Dark Calendar")

    app = QApplication(sys.argv)
    _install_qt_message_handler()

    if os.path.exists(APP_ICON_PATH):
        app.setWindowIcon(QIcon(APP_ICON_PATH))

    locked, shared_memory = _acquire_single_instance_lock()
    if not locked:
        QMessageBox.warning(None, APP_NAME, t("system_msg.already_running"))
        return 0

    # Keep references alive for whole process lifecycle.
    app._shared_memory = shared_memory

    # Show splash screen before heavy initialisation.
    from calendar_app.presentation.splash_screen import SplashScreen

    splash = SplashScreen()
    splash.show()
    splash.set_status(t("splash.preparing_runtime", "런타임 준비 중..."), 0.01)
    app.processEvents()
    phase_ranges = _build_startup_phase_ranges()

    runtime_box: dict[str, object | None] = {
        "overlay_cls": overlay_cls,
        "build_ui_font": build_ui_font,
    }

    def _resolve_runtime_ui():
        if runtime_box["overlay_cls"] is None or runtime_box["build_ui_font"] is None:
            from calendar_app.presentation.main_window.app_window import OverlayApp
            from calendar_app.presentation.main_window.app_window import (
                build_ui_font as default_build_ui_font,
            )

            runtime_box["overlay_cls"] = OverlayApp
            runtime_box["build_ui_font"] = default_build_ui_font
        return runtime_box["overlay_cls"], runtime_box["build_ui_font"]

    def _prepare_runtime_services():
        from calendar_app.infrastructure.runtime.network import NetworkManager

        NetworkManager.instance()

    # calendar 테이블 마이그레이션 (gcal_subscription → calendar, 최초 1회)
    startup_settings = QSettings("kimhyojin", "Dark Calendar")

    # "primary" 는 Google API 별칭 — DB에 저장하면 안 되므로 None 으로 정규화한다.

    class _StartupSettingsView:
        def __init__(self, values):
            self._values = dict(values)

        def value(self, key, default=None):
            return self._values.get(key, default)

    def _initialize_database():
        from calendar_app.infrastructure.db.database_unified import initialize_unified_database

        return initialize_unified_database()

    def _migrate_calendar_data():
        from calendar_app.infrastructure.db.calendar_repo import migrate_from_gcal_subscription
        from calendar_app.infrastructure.google_sync.common import infer_initial_gcal_enabled

        raw_gcal_id = startup_settings.value("gcal_calendar_id", "primary") or "primary"
        settings_values = {
            "gcal_calendar_id": None if raw_gcal_id == "primary" else raw_gcal_id,
            "gcal_enabled": "true" if infer_initial_gcal_enabled(startup_settings) else "false",
        }
        return migrate_from_gcal_subscription(settings=_StartupSettingsView(settings_values))

    def _load_custom_task_labels():
        from calendar_app.domain.task_constants import load_custom_labels

        return load_custom_labels()

    window_box: dict[str, object | None] = {"window": None}

    def _start_ui():
        app.setQuitOnLastWindowClosed(False)
        resolved_overlay_cls, _resolved_build_ui_font = _resolve_runtime_ui()
        window = resolved_overlay_cls()
        # Do NOT call window.show() here — the splash is still visible.
        # Showing the main window during the splash phase can surface the dock_manager
        # as a white top-level window before it is embedded into the parent layout.
        # window.show() is called after all phases complete (below the phase loop).
        window_box["window"] = window
        return window

    phase_plan = {
        "preparing_runtime": {
            "text": t("splash.preparing_runtime", "런타임 준비 중..."),
            "work": _prepare_runtime_services,
        },
        "loading_ui_modules": {
            "text": t("splash.loading_ui_modules", "Loading UI modules..."),
            "work": _resolve_runtime_ui,
        },
        "loading_font": {
            "text": t("splash.loading_font"),
            "work": lambda: _apply_saved_font(app, _resolve_runtime_ui()[1]),
        },
        "initializing_db": {
            "text": t("splash.initializing_db"),
            "work": _initialize_database,
        },
        "migrating_data": {
            "text": t("splash.migrating_data"),
            "work": _migrate_calendar_data,
        },
        "loading_labels": {
            "text": t("splash.loading_labels"),
            "work": _load_custom_task_labels,
        },
        "starting_ui": {
            "text": t("splash.starting_ui"),
            "work": _start_ui,
        },
        "ready": {
            "text": t("splash.ready"),
            "work": None,
        },
    }

    for phase_name, _weight, threaded in _STARTUP_PHASE_SPECS:
        phase = phase_plan[phase_name]
        start, end = phase_ranges[phase_name]
        _run_splash_phase(
            app,
            splash,
            text=phase["text"],
            start=start,
            end=end,
            work=phase.get("work"),
            threaded=threaded,
            min_duration_ms=_STARTUP_PHASE_MIN_MS.get(phase_name, 0),
        )

    window = window_box["window"]
    if window is None:
        raise RuntimeError("UI startup phase did not produce a main window")

    # Connect splash finish to main window's first actual paint event
    # to ensure the transition is seamless when the app UI is actually ready.
    window.first_paint.connect(splash.finish)
    window.show()

    signal.signal(signal.SIGINT, lambda *_: window.close())
    app._sigint_pump = QTimer()
    app._sigint_pump.timeout.connect(lambda: None)
    app._sigint_pump.start(200)

    exit_code = app.exec()

    from calendar_app.infrastructure.db.database_unified import db_manager

    db_manager.close_all_connections()
    return exit_code
