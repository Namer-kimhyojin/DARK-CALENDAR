"""System integration compatibility helpers."""

from __future__ import annotations

from PyQt6.QtCore import QSettings

_ORG = "kimhyojin"
_APP = "Dark Calendar"
_KEY = "autostart_enabled"


def is_autostart_enabled() -> bool:
    settings = QSettings(_ORG, _APP)
    return settings.value(_KEY, False, type=bool)


def set_autostart(enabled: bool) -> bool:
    settings = QSettings(_ORG, _APP)
    settings.setValue(_KEY, bool(enabled))
    return True
