# -*- coding: utf-8 -*-
"""Dialogs freed by the cyclic GC must clean up their helpers without crashing.

The destroyed slot used to be a lambda reachable only through the dialog. Depending
on the order in which the GC cleared things, PyQt either dropped it (the registry
leaked) or called it after the GC had cleared it; the call raised inside Qt and
PyQt ended the process with qFatal (0xC0000409, no traceback). Each order runs in a
child process because that failure ends the interpreter.
"""

import os
from pathlib import Path
import subprocess
import sys

import pytest

MODULE = (
    Path(__file__).resolve().parents[1] / "calendar_app/presentation/dialogs/dialog_lifetime.py"
)

CHILD = r"""
import gc
import importlib.util
import sys

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication, QDialog, QWidget

from calendar_app.shared import qt_lifetime

spec = importlib.util.spec_from_file_location("dialog_lifetime_under_test", sys.argv[1])
dl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dl)
app = QApplication([])
gc.disable()
order = sys.argv[2]
if order == "own_cycle":
    dialog = QDialog()
    dialog.me = dialog
    owner = None
else:
    owner = QWidget()
    owner.me = owner
    dialog = QDialog(owner)
    if order == "slot_younger":
        gc.collect(0)  # promote both wrappers so the slot is the youngest object
dl.keep_dialog_helper(dialog, "probe", QObject(dialog))
del dialog, owner
gc.collect()
print("left", len(dl._WATCHED), len(qt_lifetime._HOOKS), len(dl._HELPERS))
"""


@pytest.mark.parametrize("order", ["slot_younger", "own_cycle", "parent_cycle"])
def test_gc_freed_dialog_forgets_its_helpers(order):
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    result = subprocess.run(
        [sys.executable, "-c", CHILD, str(MODULE), order],
        cwd=MODULE.parents[3],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    assert result.stdout.strip().splitlines()[-1] == "left 0 0 0", result.stdout
