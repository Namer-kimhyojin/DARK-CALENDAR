# -*- coding: utf-8 -*-
"""Keep every test run away from the developer's real application data.

``calendar_app.app_paths`` resolves the database, log and OAuth token paths from
LOCALAPPDATA at import time. Tests that do not swap ``DB_PATH`` themselves used to
open the developer's real database, and a test run overlapping a development launch
left that database damaged. LOCALAPPDATA is redirected before any application module
is imported; child processes started by tests inherit the same isolated folder.
"""

import atexit
import os
from pathlib import Path
import shutil
import tempfile

from PyQt6 import QtCore

_ISOLATED_LOCALAPPDATA = tempfile.mkdtemp(prefix="air-calendar-tests-")
os.environ["LOCALAPPDATA"] = _ISOLATED_LOCALAPPDATA
atexit.register(shutil.rmtree, _ISOLATED_LOCALAPPDATA, True)

# The app reads and writes QSettings("kimhyojin", "Dark Calendar"), the user's real
# registry store. setDefaultFormat/setPath cannot redirect that constructor, so the
# class itself is swapped before any application module imports it.
_ISOLATED_SETTINGS_FILE = str(Path(_ISOLATED_LOCALAPPDATA) / "settings" / "Dark Calendar.ini")
_RealQSettings = QtCore.QSettings


class _IsolatedQSettings(_RealQSettings):
    def __init__(self, *args, **kwargs):
        if len(args) >= 2 and args[0] == "kimhyojin" and isinstance(args[1], str):
            super().__init__(_ISOLATED_SETTINGS_FILE, _RealQSettings.Format.IniFormat, *args[2:])
        else:
            super().__init__(*args, **kwargs)


QtCore.QSettings = _IsolatedQSettings


def pytest_runtest_setup(item):
    # Every test starts from an empty app settings store; values written by one
    # test used to change the outcome of tests that ran after it.
    store = QtCore.QSettings("kimhyojin", "Dark Calendar")
    store.clear()
    store.sync()


def pytest_sessionstart(session):
    from calendar_app import app_paths
    from calendar_app.infrastructure.db import database_unified

    isolated = Path(_ISOLATED_LOCALAPPDATA).resolve()
    for path in (app_paths.DB_PATH, database_unified.DB_PATH, app_paths.TOKEN_PATH):
        if not Path(path).resolve().is_relative_to(isolated):
            raise RuntimeError(f"Test run is not isolated from real app data: {path}")
    store = QtCore.QSettings("kimhyojin", "Dark Calendar").fileName()
    if not Path(store).resolve().is_relative_to(isolated):
        raise RuntimeError(f"Test run is not isolated from real app settings: {store}")
