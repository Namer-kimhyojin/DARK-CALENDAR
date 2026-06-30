"""Domain-local translation adapter to avoid direct infrastructure imports."""

from __future__ import annotations

import sys

_translator = None


def set_translator(translator):
    """Set translator callable: fn(key, fallback='', **kwargs) -> str."""
    global _translator
    _translator = translator


def _resolve_translator():
    global _translator
    if callable(_translator):
        return _translator

    module = sys.modules.get("calendar_app.infrastructure.i18n")
    if module is None:
        return None

    candidate = getattr(module, "t", None)
    if callable(candidate):
        _translator = candidate
        return candidate
    return None


def t(key: str, fallback: str = "", **kwargs) -> str:
    """Translate key with optional fallback and format kwargs."""
    translator = _resolve_translator()
    if callable(translator):
        return translator(key, fallback, **kwargs)

    base = fallback if fallback not in (None, "") else str(key)
    if kwargs:
        try:
            return str(base).format(**kwargs)
        except Exception:
            return str(base)
    return str(base)
