"""Preset persistence/policy service helpers extracted from overlay_base."""

from __future__ import annotations

from calendar_app.presentation.widgets import overlay_preset_logic as _preset_logic
from calendar_app.presentation.widgets import overlay_preset_store as _preset_store


def has_name_conflict(settings, prefix: str, name: str, built_in_names: set[str]) -> bool:
    user_presets = _preset_store.load_user_presets(settings, prefix)
    return _preset_logic.is_name_conflict(name, built_in_names, user_presets)


def upsert_user_preset_entry(
    settings,
    prefix: str,
    name: str,
    template: str,
    *,
    allow_overwrite: bool,
) -> bool:
    presets = _preset_store.load_user_presets(settings, prefix)
    updated_presets, saved = _preset_logic.upsert_user_preset(
        presets,
        name,
        template,
        allow_overwrite=allow_overwrite,
    )
    if not saved:
        return False
    _preset_store.save_user_presets(settings, prefix, updated_presets)
    return True


def remove_user_preset_entry(settings, prefix: str, name: str) -> None:
    presets = _preset_store.load_user_presets(settings, prefix)
    updated = _preset_logic.remove_user_preset(presets, name)
    _preset_store.save_user_presets(settings, prefix, updated)


def apply_rename_preset_policy(
    settings,
    prefix: str,
    *,
    old_name: str,
    new_name: str,
    built_in_names: set[str],
    fallback_template: str,
) -> None:
    presets = _preset_store.load_user_presets(settings, prefix)
    hidden = _preset_store.load_hidden_builtins(settings, prefix)
    updated_presets, updated_hidden, _ = _preset_logic.apply_rename_with_builtin_policy(
        presets,
        hidden,
        old_name=old_name,
        new_name=new_name,
        built_in_names=built_in_names,
        fallback_template=fallback_template,
    )
    _preset_store.save_user_presets(settings, prefix, updated_presets)
    _preset_store.save_hidden_builtins(settings, prefix, updated_hidden)


def apply_delete_preset_policy(
    settings,
    prefix: str,
    *,
    name: str,
    kind: str,
    built_in_names: set[str],
) -> None:
    presets = _preset_store.load_user_presets(settings, prefix)
    hidden = _preset_store.load_hidden_builtins(settings, prefix)
    updated_presets, updated_hidden = _preset_logic.apply_delete_with_builtin_policy(
        presets,
        hidden,
        name=name,
        kind=kind,
        built_in_names=built_in_names,
    )
    _preset_store.save_user_presets(settings, prefix, updated_presets)
    _preset_store.save_hidden_builtins(settings, prefix, updated_hidden)
