# -*- coding: utf-8 -*-
"""Bounded workspace documents and local-time automation, independent of Qt."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import json
import math
import re

STATE_KEY = "widget_studio_state"
CALENDAR_SCOPE_KEY = "widget_mode_calendar_scope"
STYLE_KEYS = frozenset(
    {
        "appearance_preset",
        "display_style",
        "text_color_rgba",
        "bg_color_rgba",
        "border_color_rgba",
        "widget_shape",
        "font_size",
        "font_family",
        "font_weight",
        "widget_opacity",
        "fixed_w",
        "fixed_h",
        "placement_locked",
        "graphic_collection",
        "graphics_motion",
        "graphics_auto_contrast",
        "graphics_font_reference",
        "text_shadow_enabled",
        "text_shadow_color",
        "text_shadow_opacity",
        "text_shadow_blur",
        "text_shadow_distance",
        "weather_scene",
        "weather_motion",
        "weather_asset_pack",
        "datecard_animation",
        "datecard_animation_motion",
        "weather_auto_contrast",
        "scale",
    }
)
MODE_KEYS = frozenset(
    {
        "widget_mode_layout",
        "widget_mode_skin",
        "widget_mode_layout_mode",
        "widget_mode_free_layout",
        "widget_mode_user_layout_id",
        "widget_mode_filter",
        "widget_mode_font_size",
        "widget_mode_font_family",
        "widget_mode_font_weight",
        "widget_mode_text_opacity",
        "widget_mode_background_opacity",
        "widget_mode_density",
        "widget_mode_panel_theme",
        "widget_mode_always_top",
        "widget_mode_placement_locked",
        "widget_mode_show_clock",
        "widget_mode_show_week",
        "widget_mode_show_hint",
        "widget_mode_show_completed",
        "widget_mode_calendar_scope",
    }
)


def mode_setting_allowed(key):
    return (
        key in MODE_KEYS
        or key.startswith("widget_mode_calendar_visible_")
        or key.startswith("widget_mode_geometry_")
        or key.startswith("unified_widget_geometry_")
        or key.startswith("unified_widget_size")
        or key == "unified_widget_pos"
    )


def default_state():
    return {
        "version": 1,
        "profiles": [],
        "active": "",
        "stacks": [],
        "rules": [],
        "options": {"motion": "balanced", "pause_fullscreen": False, "automatic": False},
    }


def json_value(value, depth=0):
    if depth > 8:
        raise ValueError("workspace value is too deeply nested")
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, str) and len(value) <= 1_000_000:
        return value
    if isinstance(value, list | tuple) and len(value) <= 512:
        return [json_value(item, depth + 1) for item in value]
    if isinstance(value, dict) and len(value) <= 512:
        return {str(key): json_value(item, depth + 1) for key, item in value.items()}
    raise ValueError("unsupported workspace value")


def valid_rect(raw):
    if not isinstance(raw, list | tuple) or len(raw) != 4:
        raise ValueError("invalid widget rectangle")
    if any(
        isinstance(item, bool) or not isinstance(item, int | float) or not math.isfinite(item)
        for item in raw
    ):
        raise ValueError("invalid rectangle coordinate")
    x, y, w, h = (round(item) for item in raw)
    if abs(x) > 200_000 or abs(y) > 200_000 or not (1 <= w <= 8192 and 1 <= h <= 8192):
        raise ValueError("rectangle outside supported desktop bounds")
    return [x, y, w, h]


def validate_snapshot(raw):
    if (
        not isinstance(raw, dict)
        or not isinstance(raw.get("widgets"), list)
        or len(raw["widgets"]) > 128
    ):
        raise ValueError("invalid workspace snapshot")
    result = {
        "widgets": [],
        "mode": {},
        "mode_active": bool(raw.get("mode_active", False)),
        "stacks": [],
    }
    ids = set()
    for entry in raw["widgets"]:
        iid = str(entry.get("id", ""))
        if not re.fullmatch(r"[a-z_]+_\d+", iid) or iid in ids:
            raise ValueError("invalid or duplicate widget id")
        ids.add(iid)
        style = {
            key: json_value(value)
            for key, value in entry.get("style", {}).items()
            if key in STYLE_KEYS
        }
        item = {
            "id": iid,
            "type": str(entry.get("type", "")),
            "name": str(entry.get("name", iid))[:160],
            "enabled": bool(entry.get("enabled", False)),
            "rect": valid_rect(entry.get("rect")),
            "screen": str(entry.get("screen", ""))[:256],
            "style": style,
        }
        if "available" in entry:
            item["available"] = valid_rect(entry["available"])
        if "deck_visual" in entry:
            item["deck_visual"] = deck_visual_values(entry["deck_visual"])
        result["widgets"].append(item)
    for key, value in raw.get("mode", {}).items():
        if mode_setting_allowed(key) and len(key) < 160:
            result["mode"][key] = json_value(value)
    result["stacks"] = validate_stacks(raw.get("stacks", []))
    return result


def deck_visual_values(raw):
    result = {"case": {}, "keys": {}, "scale": max(60, min(220, int(raw.get("scale", 100))))}
    result["case"] = {
        field: str(value)[:64]
        for field, value in raw.get("case", {}).items()
        if field in {"color", "accent"}
    }
    for key_id, groups in list(raw.get("keys", {}).items())[:512]:
        result["keys"][str(key_id)[:128]] = {
            group: {
                field: str(value)[:64]
                for field, value in values.items()
                if field in ({"color", "color2"} if group == "insert" else {"color"})
            }
            for group, values in groups.items()
            if group in {"cap", "legend", "led", "insert"}
        }
    return result


def validate_stacks(raw):
    if not isinstance(raw, list) or len(raw) > 32:
        raise ValueError("invalid widget stacks")
    result, assigned = [], set()
    for group in raw:
        members = list(dict.fromkeys(str(iid) for iid in group.get("members", [])))
        if not 2 <= len(members) <= 32 or any(
            not re.fullmatch(r"[a-z_]+_\d+", iid) or iid in assigned for iid in members
        ):
            raise ValueError("a widget can belong to only one stack")
        assigned.update(members)
        originals = {}
        for iid, item in group.get("originals", {}).items():
            if iid in members:
                originals[iid] = {
                    "rect": valid_rect(item["rect"]),
                    "enabled": bool(item.get("enabled", True)),
                }
        result.append(
            {
                "id": str(group.get("id", ""))[:64],
                "name": str(group.get("name", ""))[:80],
                "members": members,
                "index": max(0, int(group.get("index", 0))) % len(members),
                "rotate": bool(group.get("rotate", False)),
                "originals": originals,
            }
        )
    return result


def validate_rule(raw, profile_ids):
    profile = str(raw.get("profile", ""))
    days = sorted(set(int(day) for day in raw.get("days", [])))
    start, end = str(raw.get("start", "")), str(raw.get("end", ""))
    if profile not in profile_ids or not days or any(day not in range(1, 8) for day in days):
        raise ValueError("select a workspace and weekdays")
    for value in (start, end):
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("invalid automation time")
    return {
        "profile": profile,
        "days": days,
        "start": start,
        "end": end,
        "enabled": bool(raw.get("enabled", True)),
    }


def validate_state(raw):
    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise ValueError("unsupported workspace document")
    result = default_state()
    profiles, ids = raw.get("profiles", []), set()
    if not isinstance(profiles, list) or len(profiles) > 30:
        raise ValueError("too many saved workspaces")
    for profile in profiles:
        pid, name = str(profile.get("id", "")), str(profile.get("name", "")).strip()
        if not pid or len(pid) > 64 or pid in ids or not name or len(name) > 80:
            raise ValueError("invalid workspace name or id")
        ids.add(pid)
        result["profiles"].append(
            {
                "id": pid,
                "name": name,
                "snapshot": validate_snapshot(profile["snapshot"]),
                "thumbnail": str(profile.get("thumbnail", ""))[:180_000],
            }
        )
    result["active"] = str(raw.get("active", "")) if raw.get("active") in ids else ""
    result["stacks"] = validate_stacks(raw.get("stacks", []))
    rules = raw.get("rules", [])
    if not isinstance(rules, list) or len(rules) > 32:
        raise ValueError("too many automation rules")
    result["rules"] = [validate_rule(rule, ids) for rule in rules]
    options = raw.get("options", {})
    motion = str(options.get("motion", "balanced"))
    if motion not in {"rich", "balanced", "static"}:
        raise ValueError("invalid motion mode")
    result["options"] = {
        "motion": motion,
        "pause_fullscreen": bool(options.get("pause_fullscreen", False)),
        "automatic": bool(options.get("automatic", False)),
    }
    if len(json.dumps(result, ensure_ascii=False)) > 5_000_000:
        raise ValueError("workspace document exceeds the storage budget")
    return result


def load_state(raw):
    if not raw:
        return default_state()
    if not isinstance(raw, str) or len(raw) > 5_000_000:
        raise ValueError("invalid workspace settings")
    try:
        return validate_state(json.loads(raw))
    except (TypeError, AttributeError, KeyError, OverflowError) as exc:
        raise ValueError("invalid workspace structure") from exc


def matching_rule(rules, now: datetime):
    """Ordered rules; overnight intervals belong to their starting weekday."""
    minute = now.hour * 60 + now.minute
    for index, rule in enumerate(rules):
        if not rule.get("enabled", True):
            continue
        start = int(rule["start"][:2]) * 60 + int(rule["start"][3:])
        end = int(rule["end"][:2]) * 60 + int(rule["end"][3:])
        day = now.isoweekday()
        if start == end:
            matched = day in rule["days"]
        elif start < end:
            matched = day in rule["days"] and start <= minute < end
        else:
            matched = (minute >= start and day in rule["days"]) or (
                minute < end and (now - timedelta(days=1)).isoweekday() in rule["days"]
            )
        if matched:
            return index, rule["profile"]
    return None


def arrange_rectangles(rects, action):
    """Return a draft arrangement; never resize or mutate the source rectangles."""
    result = deepcopy(rects)
    if not result:
        return result
    if action in {"left", "top"}:
        axis = 0 if action == "left" else 1
        edge = min(rect[axis] for rect in result.values())
        for rect in result.values():
            rect[axis] = edge
    elif action in {"horizontal", "vertical"} and len(result) > 2:
        axis, length = (0, 2) if action == "horizontal" else (1, 3)
        ordered = sorted(result, key=lambda iid: result[iid][axis])
        first, last = result[ordered[0]], result[ordered[-1]]
        span = last[axis] + last[length] - first[axis]
        gap = (span - sum(result[iid][length] for iid in ordered)) / (len(ordered) - 1)
        position = first[axis]
        for iid in ordered:
            result[iid][axis] = round(position)
            position += result[iid][length] + gap
    return result


def calendar_scope(raw):
    try:
        parsed = json.loads(str(raw or "null"))
        return {str(value) for value in parsed} if isinstance(parsed, list) else None
    except (ValueError, TypeError):
        return None


def calendar_matches(row, selected):
    return selected is None or str(row.get("calendar_id") or "local") in selected
