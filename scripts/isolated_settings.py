# -*- coding: utf-8 -*-
"""Force every QSettings constructor into temporary INI storage on Windows.

UI validation scripts (scripts/validate_i18n_ui.py) call ``install_settings_sandbox``
before importing the application, so the real QSettings("kimhyojin", "Dark Calendar")
registry store is only read for the before/after comparison and never written.
"""

from pathlib import Path

from PyQt6 import QtCore


def install_settings_sandbox(root):
    native = QtCore.QSettings
    original = native("kimhyojin", "Dark Calendar")
    before = {key: original.value(key) for key in original.allKeys()}

    class SandboxSettings(native):
        def __init__(self, *args, **kwargs):
            if len(args) >= 2 and args[1] == native.Format.IniFormat:
                super().__init__(*args, **kwargs)
            else:
                organization, application = (
                    args[:2] if len(args) >= 2 else ("kimhyojin", "Dark Calendar")
                )
                path = Path(root) / str(organization) / (str(application) + ".ini")
                path.parent.mkdir(parents=True, exist_ok=True)
                super().__init__(str(path), native.Format.IniFormat)

    QtCore.QSettings = SandboxSettings

    def verify_preserved():
        current = native("kimhyojin", "Dark Calendar")
        current.sync()
        after = {key: current.value(key) for key in current.allKeys()}
        assert after == before, "Native user preferences changed during validation"
        print("Native user preferences preserved.")

    return SandboxSettings, verify_preserved
