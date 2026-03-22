# -*- coding: utf-8 -*-
"""Deprecated compatibility wrapper over calendar_app.infrastructure.i18n."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QSettings

from calendar_app.infrastructure.i18n import i18n as _infra_i18n
from calendar_app.infrastructure.i18n import t as _t

_change_listeners: list[Callable[[], None]] = []


def _reload_infra_i18n() -> None:
    """Reload infrastructure i18n manager from current settings."""
    try:
        _infra_i18n._load_translations()  # noqa: SLF001 - intentional compatibility bridge
    except Exception:
        pass


def _notify_change_listeners() -> None:
    for listener in list(_change_listeners):
        try:
            listener()
        except Exception:
            pass


def tr(text: str, **kwargs) -> str:
    """Compatibility translate function using infrastructure i18n."""
    return str(_t(text, text, **kwargs))


def get_language() -> str:
    return str(getattr(_infra_i18n, "lang", "en") or "en")


def set_language(lang: str) -> None:
    language = str(lang or "").strip() or "en"
    settings = QSettings("kimhyojin", "Dark Calendar")
    # Keep both keys to avoid surprises in old callers.
    settings.setValue("language", language)
    settings.setValue("app_language", language)
    _reload_infra_i18n()
    _notify_change_listeners()


def init_from_settings() -> None:
    _reload_infra_i18n()
    _notify_change_listeners()


def save_language_to_settings(lang: str) -> None:
    language = str(lang or "").strip() or "en"
    settings = QSettings("kimhyojin", "Dark Calendar")
    settings.setValue("language", language)
    settings.setValue("app_language", language)


def add_language_change_listener(fn: Callable[[], None]) -> None:
    if fn not in _change_listeners:
        _change_listeners.append(fn)


def remove_language_change_listener(fn: Callable[[], None]) -> None:
    try:
        _change_listeners.remove(fn)
    except ValueError:
        pass

