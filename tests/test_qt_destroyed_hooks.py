# -*- coding: utf-8 -*-
"""Callbacks on Qt ``destroyed`` must run once, also when the cyclic GC frees the sender.

A lambda connected straight to ``destroyed`` was reachable only through the sender:
PyQt dropped it, or called it after the GC had cleared it and the process ended with
qFatal (0xC0000409). The GC orders run in child processes for that reason.
"""

import ast
import gc
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
import weakref

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication, QWidget
import pytest

from calendar_app.shared.qt_lifetime import call_when_destroyed

ROOT = Path(__file__).resolve().parents[1]

CHILD = r"""
import gc
import sys

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication, QWidget

from calendar_app.shared import qt_lifetime

app = QApplication([])
gc.disable()
calls = []
order = sys.argv[1]
if order == "own_cycle":
    sender = QWidget()
    sender.me = sender
    owner = None
else:
    owner = QWidget()
    owner.me = owner
    sender = QObject(owner)
    if order == "hook_younger":
        gc.collect(0)  # promote both wrappers so the hook is the youngest object
qt_lifetime.call_when_destroyed(sender, calls.append, "gone")
del sender, owner
gc.collect()
print("calls", calls, "hooks", len(qt_lifetime._HOOKS))
"""


CHILD_WEATHER = r"""
import gc
from unittest.mock import Mock

from PyQt6 import sip
from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkRequest
from PyQt6.QtWidgets import QApplication, QWidget

from calendar_app.infrastructure.weather.request_pool import pooled_weather_reply
from calendar_app.shared import qt_lifetime


class Reply(QObject):
    finished = pyqtSignal()

    def isRunning(self):
        return True

    def abort(self):
        pass


app = QApplication([])
gc.disable()
manager = Mock()
physical = manager.get.return_value = Reply()
owner = QWidget()
owner.me = owner
pooled_weather_reply(manager, QNetworkRequest(QUrl("https://example.invalid/forecast")), owner)
sip.delete(physical)  # at shutdown the physical reply can die before its client
del owner, physical
gc.collect()
print("hooks", len(qt_lifetime._HOOKS), "pending", len(manager._air_calendar_weather_pool.pending))
"""

CHILD_MIXER = r"""
import gc

from PyQt6.QtWidgets import QApplication

from calendar_app.infrastructure.runtime import loop_mixer_audio as audio
from calendar_app.shared import qt_lifetime

app = QApplication([])
gc.disable()
mixer = audio.LoopMixer(threaded=False)
mixer.me = mixer
del mixer
gc.collect()
print("hooks", len(qt_lifetime._HOOKS))
"""


def _run_child(script, *args):
    result = subprocess.run(
        [sys.executable, "-c", script, *args],
        cwd=ROOT,
        env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    return result.stdout.strip().splitlines()[-1]


# hook_younger crashed and own_cycle lost the call with a plain lambda; parent_cycle
# worked before too and guards against regressions.
@pytest.mark.parametrize("order", ["hook_younger", "own_cycle", "parent_cycle"])
def test_hook_runs_once_when_the_gc_frees_the_sender(order):
    assert _run_child(CHILD, order) == "calls ['gone'] hooks 0"


def test_no_lambda_or_partial_is_connected_to_destroyed():
    offenders = []
    for path in sorted((ROOT / "calendar_app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8", errors="strict"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "connect"
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "destroyed"
                and node.args
                and isinstance(node.args[0], (ast.Lambda, ast.Call))
            ):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert offenders == [], "use calendar_app.shared.qt_lifetime.call_when_destroyed"


def test_weather_client_freed_after_its_physical_reply_releases_cleanly():
    assert _run_child(CHILD_WEATHER) == "hooks 0 pending 0"


def test_gc_freed_loop_mixer_leaves_no_hook():
    assert _run_child(CHILD_MIXER) == "hooks 0"


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def _delete_later_now():
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_sync_issue_popup_survives_gc_and_reopens_after_close(app):
    from calendar_app.presentation.main_window.action_handlers_gcal import GCalActionsMixin
    from calendar_app.presentation.widgets.alarm_popup import AlarmPopupWindow

    class Host:
        def open_gcal_sync_issues_dialog(self):
            pass

    host = Host()
    with patch.object(AlarmPopupWindow, "_play_notification_sound"):
        GCalActionsMixin._show_sync_issue_popup(host, "boom")
        popup = host._sync_issue_popup
        assert not sip.ispyowned(popup)
        gc.collect()
        assert not sip.isdeleted(popup) and popup.isVisible()

        GCalActionsMixin._show_sync_issue_popup(host, "again")
        assert host._sync_issue_popup is popup

        popup.close()
        _delete_later_now()
        assert sip.isdeleted(popup)
        GCalActionsMixin._show_sync_issue_popup(host, "later")
        reopened = host._sync_issue_popup
        try:
            assert reopened is not popup and reopened.isVisible()
        finally:
            reopened.close()
            _delete_later_now()


def test_deleted_popups_leave_their_tracking_collections(app):
    from calendar_app.presentation import focus_mode
    from calendar_app.presentation.widgets import alarm_checker

    alarm_popups = []
    alarm_popup, toast = QWidget(), QWidget()
    alarm_popups.append(alarm_popup)
    focus_mode._active_phase_toasts.add(toast)
    call_when_destroyed(
        alarm_popup, alarm_checker._forget_popup, alarm_popups, weakref.ref(alarm_popup)
    )
    call_when_destroyed(toast, focus_mode._forget_phase_toast, weakref.ref(toast))

    sip.delete(alarm_popup)
    sip.delete(toast)

    assert alarm_popups == []
    assert toast not in focus_mode._active_phase_toasts


def test_deleted_loop_mixer_still_shuts_down_through_its_destroyed_hook(app):
    from calendar_app.infrastructure.runtime import loop_mixer_audio as audio

    mixer = audio.LoopMixer(threaded=False)
    with patch.object(audio.LoopMixer, "shutdown", autospec=True) as shutdown:
        sip.delete(mixer)
    shutdown.assert_called_once_with(mixer)
    audio.LoopMixer.shutdown(mixer)
