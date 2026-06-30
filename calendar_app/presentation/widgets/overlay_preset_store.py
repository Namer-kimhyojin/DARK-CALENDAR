"""Preset storage helpers extracted from overlay_base."""

from __future__ import annotations

import json


def _user_presets_key(prefix: str) -> str:
    return f"{prefix}_user_presets"


def _hidden_builtins_key(prefix: str) -> str:
    return f"{prefix}_hidden_builtin_presets"


def load_user_presets(settings, prefix: str) -> list[dict[str, str]]:
    raw = settings.value(_user_presets_key(prefix), "[]")
    try:
        data = json.loads(str(raw or "[]"))
    except Exception:
        return []
    presets = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        template = str(item.get("template") or "")
        if name:
            presets.append({"name": name, "template": template})
    return presets


def save_user_presets(settings, prefix: str, presets: list[dict[str, str]]) -> None:
    clean = []
    for item in presets:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        template = str(item.get("template") or "")
        if name:
            clean.append({"name": name, "template": template})
    settings.setValue(
        _user_presets_key(prefix),
        json.dumps(clean, ensure_ascii=False),
    )


def load_hidden_builtins(settings, prefix: str) -> set[str]:
    raw = settings.value(_hidden_builtins_key(prefix), "[]")
    try:
        data = json.loads(str(raw or "[]"))
    except Exception:
        return set()
    hidden: set[str] = set()
    for item in data if isinstance(data, list) else []:
        name = str(item or "").strip()
        if name:
            hidden.add(name)
    return hidden


def save_hidden_builtins(settings, prefix: str, hidden: set[str]) -> None:
    settings.setValue(
        _hidden_builtins_key(prefix),
        json.dumps(sorted(hidden), ensure_ascii=False),
    )
