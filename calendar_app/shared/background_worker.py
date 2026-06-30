from importlib import import_module
import traceback

from PyQt6.QtCore import QThread, pyqtSignal

_DEFAULT_SYNC_OUTCOME_FAILED = "failed"
_DEFAULT_SYNC_OUTCOME_SKIPPED = "skipped"


def _translate(key: str, fallback: str = "", **kwargs) -> str:
    translator = None
    try:
        translator = getattr(import_module("calendar_app.infrastructure.i18n"), "t", None)
    except Exception:
        translator = None

    if callable(translator):
        try:
            return translator(key, fallback, **kwargs)
        except Exception:
            pass

    base = fallback if fallback not in (None, "") else str(key)
    if kwargs:
        try:
            return str(base).format(**kwargs)
        except Exception:
            return str(base)
    return str(base)


def _resolve_sync_runtime():
    sync_func = None
    failed = _DEFAULT_SYNC_OUTCOME_FAILED
    skipped = _DEFAULT_SYNC_OUTCOME_SKIPPED
    try:
        engine = import_module("calendar_app.infrastructure.google_sync.engine")
        sync_func = getattr(engine, "sync_google_calendar", None)
        failed = getattr(engine, "SYNC_OUTCOME_FAILED", failed)
        skipped = getattr(engine, "SYNC_OUTCOME_SKIPPED", skipped)
    except Exception:
        pass
    return sync_func, failed, skipped


def _close_db_connection():
    try:
        db_manager = getattr(
            import_module("calendar_app.infrastructure.db.database_unified"), "db_manager", None
        )
        if db_manager is not None:
            db_manager.close_connection()
    except Exception:
        pass


class SyncWorker(QThread):
    """Google Calendar sync work on a background thread."""

    result_ready = pyqtSignal(bool, str)

    def __init__(self, app, silent=True):
        super().__init__()
        self.app = app
        self.silent = silent
        # finished 시그널 후 deleteLater로 안전하게 삭제
        self.finished.connect(self.deleteLater)

    def run(self):
        try:
            sync_google_calendar, sync_failed, sync_skipped = _resolve_sync_runtime()
            if not callable(sync_google_calendar):
                self.result_ready.emit(False, _translate("gcal.worker.sync_failed", "Sync failed"))
                return

            success = sync_google_calendar(self.app, silent=self.silent)
            if success:
                stats = getattr(self.app, "_last_gcal_sync_stats", {}) or {}
                if stats.get("push_failures") or stats.get("delete_failures"):
                    self.result_ready.emit(
                        True,
                        _translate(
                            "gcal.worker.sync_partial",
                            "Sync complete (partial failures: push={push}, delete={delete})",
                            push=stats.get("push_failures", 0),
                            delete=stats.get("delete_failures", 0),
                        ),
                    )
                else:
                    self.result_ready.emit(
                        True, _translate("gcal.worker.sync_complete", "Sync complete")
                    )
            else:
                outcome = getattr(self.app, "_last_gcal_sync_outcome", None)
                if outcome == sync_skipped:
                    self.result_ready.emit(
                        False, _translate("gcal.worker.sync_skipped", "Sync skipped")
                    )
                elif outcome == sync_failed:
                    self.result_ready.emit(
                        False, _translate("gcal.worker.sync_failed", "Sync failed")
                    )
                else:
                    self.result_ready.emit(
                        False,
                        _translate("gcal.worker.sync_skipped_or_failed", "Sync failed or skipped"),
                    )
        except Exception as e:
            error_msg = traceback.format_exc()
            self.result_ready.emit(
                False,
                _translate(
                    "gcal.worker.sync_error",
                    "Sync error: {error}\n{details}",
                    error=e,
                    details=error_msg,
                ),
            )
        finally:
            _close_db_connection()


class AuthWorker(QThread):
    """Google Calendar auth work on a background thread."""

    result_ready = pyqtSignal(bool, str)

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.finished.connect(self.deleteLater)

    def run(self):
        try:
            success = self.app.refresh_gcal_sync_state_internal(
                authenticate_silently=True, update_ui=False
            )
            if success:
                self.result_ready.emit(
                    True, _translate("gcal.worker.auth_success", "Authentication successful")
                )
            else:
                self.result_ready.emit(
                    False, _translate("gcal.worker.auth_failed", "Authentication failed")
                )
        except Exception as e:
            self.result_ready.emit(
                False,
                _translate("gcal.worker.auth_error", "Authentication error: {error}", error=e),
            )
        finally:
            _close_db_connection()


class DbTaskWorker(QThread):
    """Generic background worker for DB tasks."""

    # QThread.finished 를 가리지 않도록 다른 이름 사용
    task_done = pyqtSignal(bool, object)

    def __init__(self, task_func, *args, **kwargs):
        super().__init__()
        self.task_func = task_func
        self.args = args
        self.kwargs = kwargs
        # QThread 내장 finished (스레드 완전 종료 후 emit) 에 deleteLater 연결
        self.finished.connect(self.deleteLater)

    def run(self):
        try:
            result = self.task_func(*self.args, **self.kwargs)
            self.task_done.emit(True, result)
        except Exception as e:
            self.task_done.emit(False, str(e))
        # Connection closure is now managed at a higher level to avoid repeated I/O overhead.
