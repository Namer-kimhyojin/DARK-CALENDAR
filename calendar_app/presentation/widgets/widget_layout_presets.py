# -*- coding: utf-8 -*-
"""Detached, transactional user layout presets independent of built-in presets."""

import json
import logging
import re
import unicodedata
from uuid import uuid4

from calendar_app.presentation.widgets.widget_free_layout import validate_free_layout

logger = logging.getLogger(__name__)
USER_LAYOUT_PRESETS_KEY = "widget_mode_user_layout_presets"
SELECTED_LAYOUT_PRESET_KEY = "widget_mode_user_layout_id"
MAX_LAYOUT_PRESETS = 100
MAX_PRESET_NAME_LENGTH = 80
MAX_PRESET_JSON_BYTES = 2 * 1024 * 1024
_ID_PATTERN = re.compile(r"user_[0-9a-f]{32}")


def _validate_name(name):
    if not isinstance(name, str):
        raise ValueError("preset name must be text")
    if any(unicodedata.category(character) in {"Cc", "Cf", "Cs"} for character in name):
        raise ValueError("preset name cannot contain control characters")
    result = name.strip()
    if not result or len(result) > MAX_PRESET_NAME_LENGTH:
        raise ValueError("preset name must contain 1 to 80 characters")
    return result


def _validate_id(preset_id):
    if not isinstance(preset_id, str) or not _ID_PATTERN.fullmatch(preset_id):
        raise ValueError("invalid user layout preset id")
    return preset_id


def _serialize(presets):
    try:
        payload = json.dumps(
            {"version": 1, "presets": presets},
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        if len(payload.encode("utf-8", errors="strict")) > MAX_PRESET_JSON_BYTES:
            raise ValueError("user layout presets exceed the size limit")
    except (TypeError, OverflowError, UnicodeError, RecursionError) as error:
        raise ValueError("user layout presets must be valid JSON") from error
    return payload


def _validate_presets(presets):
    if not isinstance(presets, list) or len(presets) > MAX_LAYOUT_PRESETS:
        raise ValueError("user layout presets must be a list of at most 100 entries")
    _serialize(presets)
    result, ids, names = [], set(), set()
    for preset in presets:
        if not isinstance(preset, dict) or set(preset) != {"id", "name", "layout"}:
            raise ValueError("each preset must contain only id, name and layout")
        preset_id = _validate_id(preset["id"])
        name = _validate_name(preset["name"])
        if preset_id in ids or name.casefold() in names:
            raise ValueError("preset ids and names must be unique")
        ids.add(preset_id)
        names.add(name.casefold())
        result.append(
            {"id": preset_id, "name": name, "layout": validate_free_layout(preset["layout"])}
        )
    _serialize(result)
    return result


def read_layout_presets(settings):
    """Read detached presets; invalid or future settings are never rewritten."""
    raw = settings.value(USER_LAYOUT_PRESETS_KEY, None)
    if raw is None:
        return []
    try:
        if isinstance(raw, str):
            if len(raw.encode("utf-8", errors="strict")) > MAX_PRESET_JSON_BYTES:
                raise ValueError("user layout presets exceed the size limit")
            envelope = json.loads(raw)
        else:
            envelope = raw
        if (
            not isinstance(envelope, dict)
            or set(envelope) != {"version", "presets"}
            or type(envelope["version"]) is not int
            or envelope["version"] != 1
        ):
            raise ValueError("unsupported user layout presets version")
        return _validate_presets(envelope["presets"])
    except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError):
        logger.warning("Invalid user widget layout presets; using an empty library")
        return []


def write_layout_presets(settings, presets):
    """Persist the validated library only when explicitly requested."""
    result = _validate_presets(presets)
    settings.setValue(USER_LAYOUT_PRESETS_KEY, _serialize(result))
    return result


def get_layout_preset(presets, preset_id):
    """Return a detached matching preset, or None for an unknown id."""
    return next(
        (preset for preset in _validate_presets(presets) if preset["id"] == preset_id), None
    )


def create_layout_preset(presets, name, layout):
    result = _validate_presets(presets)
    preset_id = "user_" + uuid4().hex
    while any(preset["id"] == preset_id for preset in result):
        preset_id = "user_" + uuid4().hex
    result.append({"id": preset_id, "name": name, "layout": layout})
    return _validate_presets(result), preset_id


def _find_preset(presets, preset_id):
    _validate_id(preset_id)
    for preset in presets:
        if preset["id"] == preset_id:
            return preset
    raise ValueError("unknown user layout preset id")


def update_layout_preset(presets, preset_id, layout):
    result = _validate_presets(presets)
    _find_preset(result, preset_id)["layout"] = layout
    return _validate_presets(result)


def rename_layout_preset(presets, preset_id, name):
    result = _validate_presets(presets)
    _find_preset(result, preset_id)["name"] = name
    return _validate_presets(result)


def delete_layout_preset(presets, preset_id):
    result = _validate_presets(presets)
    _find_preset(result, preset_id)
    return [preset for preset in result if preset["id"] != preset_id]
