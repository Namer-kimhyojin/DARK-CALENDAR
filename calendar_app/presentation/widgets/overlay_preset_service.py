# -*- coding: utf-8 -*-
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
) -> bool:
    if old_name in built_in_names:
        return False
    presets = _preset_store.load_user_presets(settings, prefix)
    if not _preset_logic.has_user_entry(presets, old_name):
        return False
    updated_presets, renamed = _preset_logic.rename_user_preset(
        presets,
        old_name,
        new_name,
        fallback_template=fallback_template,
    )
    if not renamed:
        return False
    _preset_store.save_user_presets(settings, prefix, updated_presets)
    return True


def apply_delete_preset_policy(
    settings,
    prefix: str,
    *,
    name: str,
    kind: str,
    built_in_names: set[str],
) -> bool:
    if kind != "user" or name in built_in_names:
        return False
    presets = _preset_store.load_user_presets(settings, prefix)
    if not _preset_logic.has_user_entry(presets, name):
        return False
    updated_presets = _preset_logic.remove_user_preset(presets, name)
    _preset_store.save_user_presets(settings, prefix, updated_presets)
    return True


def restore_fixed_builtin_presets(
    settings,
    prefix: str,
    built_in_names: set[str],
    *,
    copy_suffix: str,
) -> list[dict[str, str]]:
    """Restore hidden built-ins and preserve old overrides as user copies."""

    presets = _preset_store.load_user_presets(settings, prefix)
    migrated, changed = _preset_logic.migrate_builtin_name_conflicts(
        presets,
        built_in_names,
        copy_suffix=copy_suffix,
    )
    hidden = _preset_store.load_hidden_builtins(settings, prefix)
    if changed:
        _preset_store.save_user_presets(settings, prefix, migrated)
    if hidden:
        _preset_store.save_hidden_builtins(settings, prefix, set())
    return migrated
