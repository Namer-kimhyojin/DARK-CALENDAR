# -*- coding: utf-8 -*-
"""Application exit state shared by windows that must never block shutdown.

Qt 6's ``QCoreApplication.quit()`` first asks every top-level window to close and
silently cancels the quit when one refuses (for example a dialog asking to
discard unsaved edits).  By that point the tray icon and main window are usually
gone, so a refused quit leaves an invisible process behind.  Exit paths call
:func:`finish_application_exit`, and dialogs consult :func:`is_app_exiting` to
skip their "discard changes?" prompts while the application is shutting down.
"""

from __future__ import annotations

from functools import partial

from PyQt6.QtCore import QCoreApplication, QTimer

EXITING_PROPERTY = "air_calendar_exiting"


def mark_app_exiting(app=None) -> None:
    app = app or QCoreApplication.instance()
    set_property = getattr(app, "setProperty", None)
    if callable(set_property):
        set_property(EXITING_PROPERTY, True)


def is_app_exiting() -> bool:
    app = QCoreApplication.instance()
    if app is None or QCoreApplication.closingDown():
        return True
    return bool(app.property(EXITING_PROPERTY))


def finish_application_exit(app=None, exit_code: int = 0) -> None:
    """Quit the event loop even when a window vetoes Qt's close-all-windows quit."""
    app = app or QCoreApplication.instance()
    if app is None:
        return
    mark_app_exiting(app)
    # quit()은 창들이 closeEvent로 상태를 저장할 기회를 준다.
    app.quit()
    # 창 하나라도 닫기를 거부하면 quit()이 무시되므로, 다음 이벤트 턴에 exit()로
    # 중첩된 대화상자 루프까지 모든 이벤트 루프를 확실히 끝낸다.
    exit_method = getattr(app, "exit", None)
    if callable(exit_method) and QCoreApplication.instance() is not None:
        QTimer.singleShot(0, partial(exit_method, int(exit_code)))


__all__ = [
    "EXITING_PROPERTY",
    "finish_application_exit",
    "is_app_exiting",
    "mark_app_exiting",
]
