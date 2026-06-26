"""Deprecated compatibility wrapper over calendar_app.infrastructure.i18n."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from importlib import import_module

from PyQt6.QtCore import QSettings

try:
    _infra_module = import_module("calendar_app.infrastructure.i18n")
    _infra_i18n = _infra_module.i18n
    _t = _infra_module.t
except ModuleNotFoundError:
    _infra_i18n = None

    def _t(key: str, fallback: str | None = None, **kwargs) -> str:
        text = str(fallback if fallback is not None else key)
        try:
            return text.format(**kwargs)
        except Exception:
            return text


_change_listeners: list[Callable[[], None]] = []


def _reload_infra_i18n() -> None:
    """Reload infrastructure i18n manager from current settings."""
    try:
        if _infra_i18n is None:
            return
        _infra_i18n._load_translations()  # noqa: SLF001 - intentional compatibility bridge
    except Exception:
        pass


def _notify_change_listeners() -> None:
    for listener in list(_change_listeners):
        with suppress(Exception):
            listener()


def _infra_translate(key: str, fallback: str | None = None, **kwargs) -> str:
    """Translate through infrastructure i18n, with a local formatting fallback."""
    try:
        return str(_t(key, fallback if fallback is not None else key, **kwargs))
    except Exception:
        text = str(fallback if fallback is not None else key)
        try:
            return text.format(**kwargs)
        except Exception:
            return text


def tr(text: str, **kwargs) -> str:
    """Compatibility translate function using infrastructure i18n."""
    return _infra_translate(text, text, **kwargs)


def get_language() -> str:
    if _infra_i18n is None:
        return "en"
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
    with suppress(ValueError):
        _change_listeners.remove(fn)
