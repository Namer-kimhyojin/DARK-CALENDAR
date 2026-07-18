"""Preset list/data manipulation helpers extracted from overlay_base."""

from __future__ import annotations


def normalize_built_in_presets(
    built_in_presets: list[tuple[str, str]],
) -> tuple[list[tuple[str, str]], set[str]]:
    cleaned = [
        (str(label).strip(), str(template))
        for label, template in built_in_presets
        if str(label).strip()
    ]
    names = {label for label, template in cleaned if template != ""}
    return cleaned, names


def has_user_entry(user_presets: list[dict[str, str]], name: str) -> bool:
    if not name:
        return False
    return any(str(entry.get("name") or "") == name for entry in user_presets)


def is_name_conflict(
    name: str,
    built_in_names: set[str],
    user_presets: list[dict[str, str]],
) -> bool:
    return bool(name) and (name in built_in_names or has_user_entry(user_presets, name))


def build_effective_entries(
    built_in_presets: list[tuple[str, str]],
    user_presets: list[dict[str, str]],
    hidden_builtins: set[str],
) -> list[dict[str, str]]:
    user_map = {
        str(entry.get("name") or ""): str(entry.get("template") or "")
        for entry in user_presets
        if str(entry.get("name") or "")
    }
    entries: list[dict[str, str]] = []
    for label, template in built_in_presets:
        if label in hidden_builtins:
            continue
        effective_template = user_map.pop(label, template)
        effective_kind = "user" if has_user_entry(user_presets, label) else "builtin"
        entries.append(
            {
                "name": label,
                "template": effective_template,
                "kind": effective_kind,
            }
        )
    for name, template in user_map.items():
        entries.append({"name": name, "template": template, "kind": "user"})
    return entries


def upsert_user_preset(
    presets: list[dict[str, str]],
    name: str,
    template: str,
    *,
    allow_overwrite: bool,
) -> tuple[list[dict[str, str]], bool]:
    updated = [dict(item) for item in presets]
    existing = next((item for item in updated if item.get("name") == name), None)
    if existing is not None and not allow_overwrite:
        return updated, False
    if existing is None:
        updated.append({"name": name, "template": template})
    else:
        existing["template"] = template
    return updated, True


def rename_user_preset(
    presets: list[dict[str, str]],
    old_name: str,
    new_name: str,
    *,
    fallback_template: str,
) -> tuple[list[dict[str, str]], bool]:
    updated = [dict(item) for item in presets]
    renamed = False
    for entry in updated:
        if entry.get("name") == old_name:
            entry["name"] = new_name
            renamed = True
            break
    if not renamed:
        updated.append({"name": new_name, "template": fallback_template})
    return updated, renamed


def remove_user_preset(presets: list[dict[str, str]], name: str) -> list[dict[str, str]]:
    return [dict(entry) for entry in presets if entry.get("name") != name]


def apply_rename_with_builtin_policy(
    presets: list[dict[str, str]],
    hidden_builtins: set[str],
    *,
    old_name: str,
    new_name: str,
    built_in_names: set[str],
    fallback_template: str,
) -> tuple[list[dict[str, str]], set[str], bool]:
    updated_presets, renamed = rename_user_preset(
        presets,
        old_name,
        new_name,
        fallback_template=fallback_template,
    )
    updated_hidden = set(hidden_builtins)
    if not renamed and old_name in built_in_names:
        updated_hidden.add(old_name)
    return updated_presets, updated_hidden, renamed


def apply_delete_with_builtin_policy(
    presets: list[dict[str, str]],
    hidden_builtins: set[str],
    *,
    name: str,
    kind: str,
    built_in_names: set[str],
) -> tuple[list[dict[str, str]], set[str]]:
    updated_presets = remove_user_preset(presets, name)
    updated_hidden = set(hidden_builtins)
    if kind == "builtin" and name in built_in_names:
        updated_hidden.add(name)
    return updated_presets, updated_hidden


def build_row_entries(
    built_in_presets: list[tuple[str, str]],
    user_presets: list[dict[str, str]],
) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for name, template in built_in_presets:
        entries.append({"name": name, "template": template, "kind": "builtin"})
    for entry in user_presets:
        name = str(entry.get("name") or "")
        template = str(entry.get("template") or "")
        if not name:
            continue
        entries.append({"name": name, "template": template, "kind": "user"})
    return entries


def find_selection_index(
    entries: list[dict[str, str]],
    select_name: str | None,
    select_kind: str | None = None,
    *,
    start_index: int = 0,
    default_index: int = 0,
) -> int:
    if not select_name:
        return default_index
    for idx in range(max(0, start_index), len(entries)):
        entry = entries[idx]
        if str(entry.get("name") or "") != select_name:
            continue
        if select_kind is None or str(entry.get("kind") or "") == select_kind:
            return idx
    return default_index


def row_button_states(*, current_kind: str, item_count: int) -> dict[str, bool]:
    has_any = item_count > 0
    is_user = current_kind == "user"
    return {
        "apply": has_any,
        "update": is_user,
        "delete": is_user,
    }


def manager_button_states(
    *,
    has_selection: bool,
    editor_text: str,
    current_template: str,
) -> dict[str, bool]:
    has_template = bool(str(editor_text).strip())
    dirty = str(editor_text) != str(current_template)
    can_customize = has_selection
    return {
        "add": has_template,
        "update": has_selection and has_template and dirty,
        "rename": can_customize,
        "delete": can_customize,
    }
