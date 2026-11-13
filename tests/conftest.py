# -*- coding: utf-8 -*-
"""Keep every test run away from the developer's real application data.

``calendar_app.app_paths`` resolves the database, log and OAuth token paths from
LOCALAPPDATA at import time. Tests that do not swap ``DB_PATH`` themselves used to
open the developer's real database, and a test run overlapping a development launch
left that database damaged. LOCALAPPDATA is redirected before any application module
is imported; child processes started by tests inherit the same isolated folder.
"""

import atexit
import gc
import os
from pathlib import Path
import shutil
import sys
import tempfile

from PyQt6 import QtCore
import pytest

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

# Tests assert the Korean source UI. Without a saved language the i18n singleton
# follows the OS locale, so an English CI runner (or a German desktop) failed them.
# The language is pinned in the isolated store before any application import.
# AIR_CALENDAR_TEST_UI_LANGUAGE runs a session in another language (the Korean-leak
# smoke test starts such sessions; module-level t() values then match the real app).
TEST_UI_LANGUAGE = os.environ.get("AIR_CALENDAR_TEST_UI_LANGUAGE") or "ko"


def _pin_ui_language(store):
    store.setValue("language", TEST_UI_LANGUAGE)
    store.sync()


_pin_ui_language(QtCore.QSettings("kimhyojin", "Dark Calendar"))


def _drop_deleted_translators(manager):
    # A module that created and then released its QApplication deletes the Qt
    # translators the singleton still references; re-applying any language would
    # then raise "wrapped C/C++ object ... has been deleted".
    from PyQt6 import sip

    for name in ("_qt_translator", "_button_translator"):
        translator = getattr(manager, name, None)
        if translator is not None and sip.isdeleted(translator):
            setattr(manager, name, None)


def pytest_runtest_setup(item):
    # Every test starts from an empty app settings store; values written by one
    # test used to change the outcome of tests that ran after it.
    store = QtCore.QSettings("kimhyojin", "Dark Calendar")
    store.clear()
    _pin_ui_language(store)
    # A test that switched languages and restored "no saved language" left the
    # singleton on the OS language; reload it so the next test sees the pinned one.
    module = sys.modules.get("calendar_app.infrastructure.i18n")
    manager = getattr(module, "i18n", None)
    if manager is None:
        return
    _drop_deleted_translators(manager)
    if getattr(manager, "lang", None) != TEST_UI_LANGUAGE:
        manager._load_translations()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item, nextitem):
    yield
    # Windows a test leaves in reference cycles (closed but never deleted) are freed
    # by the cyclic GC at an arbitrary later moment. Their destroyed slots then run,
    # and one that raised (dialog_lifetime) ended the run inside another module's
    # tests with 0xC0000409 and no traceback. Collecting here frees them while the
    # module that made them is current, so such a failure points at that module.
    if nextitem is None or getattr(nextitem, "module", None) is not getattr(item, "module", None):
        gc.collect()


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
    from calendar_app.infrastructure.i18n import i18n

    if i18n.lang != TEST_UI_LANGUAGE:
        raise RuntimeError(f"Test UI language is {i18n.lang!r}, not {TEST_UI_LANGUAGE!r}")
