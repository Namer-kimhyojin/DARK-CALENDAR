# -*- coding: utf-8 -*-
"""Data model, templates, and visual recipes for launcher-deck widgets."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import uuid

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.launcher_keycap_assets import keycap_asset_ids
from calendar_app.presentation.widgets.launcher_keycap_icons import (
    DEFAULT_KEYCAP_ICON_PACK_ID,
    KEYCAP_ICON_ASSETS,
    keycap_icon_pack_ids,
)
from calendar_app.presentation.widgets.launcher_keycap_sounds import KEYCAP_SOUNDS


@dataclass(frozen=True, slots=True)
class KeycapStyle:
    style_id: str
    label_key: str
    label_default: str
    top: str
    bottom: str
    border: str
    text: str
    depth: int
    radius: int
    glow: str = ""


KEYCAP_STYLES = (
    KeycapStyle(
        "air_glass",
        "widget.launcher.style.air_glass",
        "Air Glass",
        "#3d7dfbff",
        "#15316bff",
        "#8fc0ffff",
        "#ffffffff",
        2,
        16,
        "#5fa8ff",
    ),
    KeycapStyle(
        "mechanical_pbt",
        "widget.launcher.style.mechanical_pbt",
        "Mechanical PBT",
        "#e2a23cff",
        "#7a5316ff",
        "#ffd48aff",
        "#241705ff",
        2,
        14,
    ),
    KeycapStyle(
        "soft_clay",
        "widget.launcher.style.soft_clay",
        "Soft Clay",
        "#b45cf0ff",
        "#4c1f7aff",
        "#e6b8ffff",
        "#ffffffff",
        2,
        18,
    ),
    KeycapStyle(
        "arcade_glow",
        "widget.launcher.style.arcade_glow",
        "Arcade Glow",
        "#173049ff",
        "#050810ff",
        "#48edffff",
        "#e8feffff",
        2,
        14,
        "#48edff",
    ),
    KeycapStyle(
        "minimal_mono",
        "widget.launcher.style.minimal_mono",
        "Minimal Mono",
        "#42484fff",
        "#1a1c1fff",
        "#c7ccd3ff",
        "#ffffffff",
        2,
        14,
    ),
)
_STYLE_BY_ID = {style.style_id: style for style in KEYCAP_STYLES}
DEFAULT_KEYCAP_STYLE_ID = "air_glass"

ACTION_TYPES = (
    ("open", "widget.launcher.action.open", "프로그램·파일·폴더"),
    ("url", "widget.launcher.action.url", "웹 주소"),
    ("hotkey", "widget.launcher.action.hotkey", "키보드 단축키"),
    ("internal", "widget.launcher.action.internal", "Air Calendar 명령"),
)

INTERNAL_ACTIONS = (
    ("new_task", "widget.launcher.command.new_task", "새 일정"),
    ("today", "widget.launcher.command.today", "오늘로 이동"),
    ("sync_google", "widget.launcher.command.sync_google", "Google 동기화"),
    ("command_palette", "widget.launcher.command.command_palette", "명령 팔레트"),
    ("widget_manager", "widget.launcher.command.widget_manager", "위젯 관리자"),
)

PATTERNS = (
    ("uniform", "widget.launcher.pattern.uniform", "한 가지 스타일"),
    ("checker", "widget.launcher.pattern.checker", "체커보드"),
    ("row_groups", "widget.launcher.pattern.row_groups", "행별 구분"),
    ("hero", "widget.launcher.pattern.hero", "주요 키 강조"),
    ("flow", "widget.launcher.pattern.flow", "컬러 흐름"),
    ("function_groups", "widget.launcher.pattern.function_groups", "기능별 구분"),
)

KEYCAP_ICONS = tuple(
    (asset.icon_id, asset.label_key, asset.label_default) for asset in KEYCAP_ICON_ASSETS
)
_KEYCAP_ICON_IDS = {item[0] for item in KEYCAP_ICONS}

LABEL_LAYOUTS = (
    ("icon_above", "widget.launcher.layout.icon_above", "아이콘 위 · 글자 아래"),
    ("icon_left", "widget.launcher.layout.icon_left", "아이콘 왼쪽 · 글자 오른쪽"),
    ("text_only", "widget.launcher.layout.text_only", "글자만"),
    ("icon_only", "widget.launcher.layout.icon_only", "아이콘만"),
)
_LABEL_LAYOUT_IDS = {item[0] for item in LABEL_LAYOUTS}

INTERACTION_MODES = (
    ("action", "widget.launcher.interaction.mode_action", "실행 버튼"),
    ("toggle", "widget.launcher.interaction.mode_toggle", "켜기 · 끄기 토글"),
    ("hold", "widget.launcher.interaction.mode_hold", "누르는 동안 활성"),
)
ACTIVATION_TRIGGERS = (
    ("release", "widget.launcher.interaction.trigger_release", "눌렀다 뗄 때"),
    ("press", "widget.launcher.interaction.trigger_press", "누르는 즉시"),
    ("double", "widget.launcher.interaction.trigger_double", "두 번 누르기"),
    ("long", "widget.launcher.interaction.trigger_long", "길게 누르기"),
)
PRESS_EFFECTS = (
    ("depress", "widget.launcher.effect.depress", "실물처럼 눌림"),
    ("ripple", "widget.launcher.effect.ripple", "퍼지는 물결"),
    ("glow", "widget.launcher.effect.glow", "빛 번짐"),
    ("bounce", "widget.launcher.effect.bounce", "탄성 바운스"),
    ("none", "widget.launcher.effect.none", "효과 없음"),
)
HOVER_EFFECTS = (
    ("lift", "widget.launcher.effect.lift", "살짝 떠오름"),
    ("glow", "widget.launcher.effect.glow", "빛 번짐"),
    ("pulse", "widget.launcher.effect.pulse", "은은한 펄스"),
    ("none", "widget.launcher.effect.none", "효과 없음"),
)
ACTIVE_EFFECTS = (
    ("solid", "widget.launcher.effect.solid", "고정 강조"),
    ("glow", "widget.launcher.effect.glow", "빛 번짐"),
    ("pulse", "widget.launcher.effect.pulse", "펄스"),
    ("breathe", "widget.launcher.effect.breathe", "브리딩"),
    ("none", "widget.launcher.effect.none", "효과 없음"),
)
RESULT_EFFECTS = (
    ("ring", "widget.launcher.effect.ring", "상태 링"),
    ("flash", "widget.launcher.effect.flash", "컬러 플래시"),
    ("pulse", "widget.launcher.effect.pulse", "펄스"),
    ("shake", "widget.launcher.effect.shake", "좌우 흔들림"),
    ("none", "widget.launcher.effect.none", "효과 없음"),
)
ASSET_PLAYBACK_MODES = (
    ("always", "widget.launcher.asset_playback.always", "항상 재생"),
    ("hover", "widget.launcher.asset_playback.hover", "마우스를 올릴 때"),
    ("press", "widget.launcher.asset_playback.press", "누르는 동안"),
    ("active", "widget.launcher.asset_playback.active", "활성 상태일 때"),
    ("never", "widget.launcher.asset_playback.never", "첫 프레임만"),
)
SOUND_PROFILES = (
    ("none", "widget.launcher.sound.none", "소리 없음"),
    ("system", "widget.launcher.sound.system", "시스템 피드백음"),
    *((sound.sound_id, sound.label_key, sound.label_default) for sound in KEYCAP_SOUNDS),
    ("custom", "widget.launcher.sound.custom", "사용자 WAV 파일"),
)
SOUND_EVENTS = (
    ("press", "widget.launcher.sound_event.press", "누를 때"),
    ("success", "widget.launcher.sound_event.success", "성공할 때"),
    ("error", "widget.launcher.sound_event.error", "실패할 때"),
    ("result", "widget.launcher.sound_event.result", "성공 또는 실패할 때"),
    ("all", "widget.launcher.sound_event.all", "모든 상태 변화"),
)

INTERACTION_DEFAULTS = {
    "enabled": True,
    "interaction_mode": "action",
    "activation_trigger": "release",
    "long_press_ms": 650,
    "press_effect": "depress",
    "hover_effect": "lift",
    "active_effect": "glow",
    "success_effect": "ring",
    "error_effect": "shake",
    "animation_speed": 100,
    "feedback_duration_ms": 720,
    "active_top": "#35d39add",
    "active_border": "#9affd4ff",
    "disabled_top": "#596273b8",
    "disabled_text": "#aeb7c6cc",
    "show_status_indicator": True,
    "sound_profile": "none",
    "sound_event": "press",
    "sound_path": "",
    "sound_volume": 65,
    "asset_playback": "always",
    "reduce_motion": False,
    "active": False,
}

_INTERACTION_MODE_IDS = {item[0] for item in INTERACTION_MODES}
_ACTIVATION_TRIGGER_IDS = {item[0] for item in ACTIVATION_TRIGGERS}
_PRESS_EFFECT_IDS = {item[0] for item in PRESS_EFFECTS}
_HOVER_EFFECT_IDS = {item[0] for item in HOVER_EFFECTS}
_ACTIVE_EFFECT_IDS = {item[0] for item in ACTIVE_EFFECTS}
_RESULT_EFFECT_IDS = {item[0] for item in RESULT_EFFECTS}
_ASSET_PLAYBACK_IDS = {item[0] for item in ASSET_PLAYBACK_MODES}
_SOUND_PROFILE_IDS = {item[0] for item in SOUND_PROFILES}
_SOUND_EVENT_IDS = {item[0] for item in SOUND_EVENTS}

KEYCAP_OVERRIDE_DEFAULTS = {
    "custom_top": "",
    "custom_bottom": "",
    "custom_border": "",
    "custom_text": "",
    "depth_override": -1,
    "radius_override": -1,
    "font_scale": 100,
    "icon": "auto",
    "label_layout": "icon_above",
    "asset_id": "none",
    "asset_path": "",
    "asset_opacity": 42,
    "asset_scale": 100,
}


def keycap_style(style_id: object) -> KeycapStyle:
    return _STYLE_BY_ID.get(str(style_id or ""), _STYLE_BY_ID[DEFAULT_KEYCAP_STYLE_ID])


def new_key(
    label: str,
    row: int,
    column: int,
    *,
    width: int = 1,
    height: int = 1,
    style: str = DEFAULT_KEYCAP_STYLE_ID,
    action_type: str = "internal",
    target: str = "command_palette",
) -> dict:
    return {
        "id": uuid.uuid4().hex[:10],
        "label": str(label),
        "row": max(0, int(row)),
        "column": max(0, int(column)),
        "width": max(1, min(int(width), 3)),
        "height": max(1, min(int(height), 2)),
        "style": keycap_style(style).style_id,
        "action_type": action_type if action_type in {item[0] for item in ACTION_TYPES} else "open",
        "target": str(target),
        "accent": "",
        **KEYCAP_OVERRIDE_DEFAULTS,
        **INTERACTION_DEFAULTS,
    }


def clear_keycap_overrides(key: dict) -> dict:
    """Clear per-key appearance values while preserving its base style and action."""
    for field, value in KEYCAP_OVERRIDE_DEFAULTS.items():
        key[field] = value
    key["accent"] = ""
    return key


def clear_keycap_interaction(key: dict) -> dict:
    """Restore motion, status, sound, and activation behavior defaults."""
    for field, value in INTERACTION_DEFAULTS.items():
        key[field] = value
    return key


def _template_label(name: str, fallback: str, **kwargs) -> str:
    return str(t(f"widget.launcher.key.{name}", fallback, **kwargs))


_GRAPHIC_ASSET_CYCLE = (
    "spark",
    "orbit",
    "grid",
    "prism",
    "blocks",
    "waves",
    "circuit",
    "constellation",
    "rings",
    "sunburst",
)
_GRAPHIC_ICON_CYCLE = (
    "rocket",
    "star",
    "calendar",
    "palette",
    "folder",
    "globe",
    "bolt",
    "focus",
    "play",
    "plus",
)
_GRAPHIC_ACTION_VISUALS = {
    "new_task": ("sunburst", "plus"),
    "today": ("grid", "calendar"),
    "sync_google": ("orbit", "sync"),
    "command_palette": ("prism", "search"),
    "widget_manager": ("blocks", "settings"),
}
DECK_VISUAL_FIELDS = (
    "icon_pack",
    "mosaic_enabled",
    "mosaic_path",
    "mosaic_opacity",
    "mosaic_show_labels",
)


def _with_graphic_defaults(deck: dict) -> dict:
    """Make bundled templates visual-first while keeping labels accessible."""
    deck["version"] = 3
    deck.setdefault("icon_pack", DEFAULT_KEYCAP_ICON_PACK_ID)
    deck.setdefault("mosaic_enabled", False)
    deck.setdefault("mosaic_path", "")
    deck.setdefault("mosaic_opacity", 92)
    deck.setdefault("mosaic_show_labels", True)
    for index, key in enumerate(deck.get("keys", [])):
        target = str(key.get("target", "") or "")
        action_type = str(key.get("action_type", "") or "")
        if target in _GRAPHIC_ACTION_VISUALS:
            asset_id, icon_id = _GRAPHIC_ACTION_VISUALS[target]
        elif action_type == "url":
            asset_id, icon_id = "waves", "globe"
        else:
            asset_id = _GRAPHIC_ASSET_CYCLE[index % len(_GRAPHIC_ASSET_CYCLE)]
            icon_id = _GRAPHIC_ICON_CYCLE[index % len(_GRAPHIC_ICON_CYCLE)]

        is_feature_key = int(key.get("width", 1)) > 1 or int(key.get("height", 1)) > 1
        key.update(
            {
                "asset_id": asset_id,
                "asset_opacity": 90 if is_feature_key else 82,
                "asset_scale": 158 if is_feature_key else 142,
                "icon": icon_id,
                "label_layout": "icon_above",
                "font_scale": 74 if is_feature_key else 68,
            }
        )
    return deck


def _template_regular() -> dict:
    keys = []
    labels = (
        _template_label("schedule", "일정"),
        _template_label("today", "오늘"),
        _template_label("sync", "동기화"),
        _template_label("command", "명령"),
        _template_label("folder", "폴더"),
        _template_label("web", "웹"),
        *(_template_label("app", "앱 {number}", number=number) for number in range(1, 4)),
    )
    commands = ("new_task", "today", "sync_google", "command_palette")
    for index, label in enumerate(labels):
        action_type = "internal" if index < len(commands) else "open"
        target = commands[index] if index < len(commands) else ""
        keys.append(new_key(label, index // 3, index % 3, action_type=action_type, target=target))
    return _with_graphic_defaults({"version": 3, "columns": 3, "rows": 3, "gap": 8, "keys": keys})


def _template_mixed() -> dict:
    return _with_graphic_defaults(
        {
            "version": 3,
            "columns": 4,
            "rows": 3,
            "gap": 8,
            "keys": [
                new_key(
                    _template_label("start_work", "업무 시작"),
                    0,
                    0,
                    width=2,
                    action_type="internal",
                    target="command_palette",
                ),
                new_key(
                    _template_label("schedule", "일정"),
                    0,
                    2,
                    action_type="internal",
                    target="new_task",
                ),
                new_key(
                    _template_label("today", "오늘"), 0, 3, action_type="internal", target="today"
                ),
                new_key(
                    _template_label("design", "디자인"),
                    1,
                    0,
                    height=2,
                    style="soft_clay",
                    action_type="open",
                    target="",
                ),
                new_key(
                    _template_label("folder", "폴더"),
                    1,
                    1,
                    width=2,
                    style="mechanical_pbt",
                    action_type="open",
                    target="",
                ),
                new_key(
                    _template_label("sync", "동기화"),
                    1,
                    3,
                    style="arcade_glow",
                    action_type="internal",
                    target="sync_google",
                ),
                new_key(
                    _template_label("web", "웹"),
                    2,
                    1,
                    style="air_glass",
                    action_type="url",
                    target="https://",
                ),
                new_key(
                    _template_label("command", "명령"),
                    2,
                    2,
                    width=2,
                    style="minimal_mono",
                    action_type="internal",
                    target="command_palette",
                ),
            ],
        }
    )


def _template_rows() -> dict:
    deck = _template_regular()
    deck["columns"], deck["rows"] = 4, 3
    deck["keys"] = []
    row_specs = (
        (_template_label("work", "업무"), "mechanical_pbt"),
        (_template_label("tools", "도구"), "air_glass"),
        (_template_label("favorites", "즐겨찾기"), "soft_clay"),
    )
    for row, (prefix, style) in enumerate(row_specs):
        for column in range(4):
            deck["keys"].append(
                new_key(
                    f"{prefix} {column + 1}",
                    row,
                    column,
                    style=style,
                    action_type="open",
                    target="",
                )
            )
    return _with_graphic_defaults(deck)


def _template_keyboard() -> dict:
    keys = []
    for column in range(5):
        keys.append(new_key(f"K{column + 1}", 0, column, action_type="open", target=""))
    for column in range(4):
        keys.append(new_key(f"A{column + 1}", 1, column, action_type="open", target=""))
    keys.append(
        new_key(
            _template_label("space", "SPACE"),
            2,
            1,
            width=3,
            action_type="internal",
            target="command_palette",
        )
    )
    return _with_graphic_defaults({"version": 3, "columns": 5, "rows": 3, "gap": 7, "keys": keys})


def _template_sidebar() -> dict:
    return _with_graphic_defaults(
        {
            "version": 3,
            "columns": 3,
            "rows": 4,
            "gap": 8,
            "keys": [
                new_key(
                    _template_label("tools", "도구"),
                    0,
                    0,
                    height=2,
                    style="mechanical_pbt",
                    action_type="open",
                    target="",
                ),
                new_key(
                    _template_label("start_work", "업무 시작"),
                    0,
                    1,
                    width=2,
                    style="air_glass",
                    action_type="internal",
                    target="command_palette",
                ),
                new_key(
                    _template_label("schedule", "일정"),
                    1,
                    1,
                    action_type="internal",
                    target="new_task",
                ),
                new_key(
                    _template_label("today", "오늘"), 1, 2, action_type="internal", target="today"
                ),
                new_key(
                    _template_label("folder", "폴더"),
                    2,
                    0,
                    width=2,
                    style="soft_clay",
                    action_type="open",
                    target="",
                ),
                new_key(
                    _template_label("sync", "동기화"),
                    2,
                    2,
                    height=2,
                    style="arcade_glow",
                    action_type="internal",
                    target="sync_google",
                ),
                new_key(
                    _template_label("web", "웹"),
                    3,
                    0,
                    width=2,
                    style="minimal_mono",
                    action_type="url",
                    target="https://",
                ),
            ],
        }
    )


def _template_strip() -> dict:
    return _with_graphic_defaults(
        {
            "version": 3,
            "columns": 8,
            "rows": 1,
            "gap": 7,
            "keys": [
                new_key(
                    _template_label("new_schedule", "새 일정"),
                    0,
                    0,
                    width=2,
                    action_type="internal",
                    target="new_task",
                ),
                new_key(
                    _template_label("today", "오늘"), 0, 2, action_type="internal", target="today"
                ),
                new_key(
                    _template_label("sync", "동기화"),
                    0,
                    3,
                    width=2,
                    style="arcade_glow",
                    action_type="internal",
                    target="sync_google",
                ),
                new_key(
                    _template_label("command", "명령"),
                    0,
                    5,
                    width=3,
                    style="mechanical_pbt",
                    action_type="internal",
                    target="command_palette",
                ),
            ],
        }
    )


DECK_TEMPLATES = (
    ("regular_3x3", "widget.launcher.template.regular", "정규 3×3", _template_regular),
    ("mixed_4x3", "widget.launcher.template.mixed", "혼합 4×3", _template_mixed),
    ("category_rows", "widget.launcher.template.rows", "카테고리 행", _template_rows),
    ("keyboard_cluster", "widget.launcher.template.keyboard", "키보드 배열", _template_keyboard),
    ("sidebar_tools", "widget.launcher.template.sidebar", "사이드 도구", _template_sidebar),
    ("command_strip", "widget.launcher.template.strip", "커맨드 스트립", _template_strip),
)
_TEMPLATE_BY_ID = {item[0]: item for item in DECK_TEMPLATES}


def template_deck(template_id: object = "mixed_4x3") -> dict:
    entry = _TEMPLATE_BY_ID.get(str(template_id), _TEMPLATE_BY_ID["mixed_4x3"])
    return deepcopy(entry[3]())


def preserve_deck_visuals(source: dict, target: dict) -> dict:
    """Carry deck-wide visual settings across array-template changes."""
    result = deepcopy(target)
    for field in DECK_VISUAL_FIELDS:
        if field in source:
            result[field] = deepcopy(source[field])
    return normalize_deck(result)


def normalize_deck(data: object) -> dict:
    if not isinstance(data, dict):
        return template_deck()
    columns = max(1, min(int(data.get("columns", 4) or 4), 12))
    rows = max(1, min(int(data.get("rows", 3) or 3), 10))
    gap = max(2, min(int(data.get("gap", 8) or 8), 24))
    keys = []
    seen_ids: set[str] = set()
    for raw in data.get("keys", []):
        if not isinstance(raw, dict):
            continue
        key = new_key(
            str(
                raw.get("label", _template_label("generic", "키"))
                or _template_label("generic", "키")
            ),
            int(raw.get("row", 0) or 0),
            int(raw.get("column", 0) or 0),
            width=int(raw.get("width", 1) or 1),
            height=int(raw.get("height", 1) or 1),
            style=str(raw.get("style", DEFAULT_KEYCAP_STYLE_ID)),
            action_type=str(raw.get("action_type", "open")),
            target=str(raw.get("target", "") or ""),
        )
        key["id"] = str(raw.get("id") or key["id"])
        if key["id"] in seen_ids:
            key["id"] = uuid.uuid4().hex[:10]
        seen_ids.add(key["id"])
        key["row"] = min(key["row"], rows - 1)
        key["column"] = min(key["column"], columns - 1)
        key["width"] = min(key["width"], columns - key["column"])
        key["height"] = min(key["height"], rows - key["row"])
        key["accent"] = str(raw.get("accent", "") or "")
        key["custom_top"] = str(raw.get("custom_top", "") or "")
        key["custom_bottom"] = str(raw.get("custom_bottom", "") or "")
        key["custom_border"] = str(raw.get("custom_border", "") or raw.get("accent", "") or "")
        key["custom_text"] = str(raw.get("custom_text", "") or "")
        depth_value = raw.get("depth_override", -1)
        radius_value = raw.get("radius_override", -1)
        key["depth_override"] = max(-1, min(int(depth_value), 14))
        key["radius_override"] = max(-1, min(int(radius_value), 28))
        key["font_scale"] = max(70, min(int(raw.get("font_scale", 100) or 100), 160))
        icon_id = str(raw.get("icon", "auto") or "auto")
        key["icon"] = icon_id if icon_id in _KEYCAP_ICON_IDS else "auto"
        label_layout = str(raw.get("label_layout", "icon_above") or "icon_above")
        key["label_layout"] = label_layout if label_layout in _LABEL_LAYOUT_IDS else "icon_above"
        asset_id = str(raw.get("asset_id", "none") or "none")
        key["asset_id"] = asset_id if asset_id in keycap_asset_ids() else "none"
        key["asset_path"] = str(raw.get("asset_path", "") or "")
        key["asset_opacity"] = max(10, min(int(raw.get("asset_opacity", 42) or 42), 100))
        key["asset_scale"] = max(40, min(int(raw.get("asset_scale", 100) or 100), 160))
        key["enabled"] = bool(raw.get("enabled", True))
        interaction_mode = str(raw.get("interaction_mode", "action") or "action")
        key["interaction_mode"] = (
            interaction_mode if interaction_mode in _INTERACTION_MODE_IDS else "action"
        )
        activation_trigger = str(raw.get("activation_trigger", "release") or "release")
        key["activation_trigger"] = (
            activation_trigger if activation_trigger in _ACTIVATION_TRIGGER_IDS else "release"
        )
        key["long_press_ms"] = max(300, min(int(raw.get("long_press_ms", 650) or 650), 2000))
        press_effect = str(raw.get("press_effect", "depress") or "depress")
        key["press_effect"] = press_effect if press_effect in _PRESS_EFFECT_IDS else "depress"
        hover_effect = str(raw.get("hover_effect", "lift") or "lift")
        key["hover_effect"] = hover_effect if hover_effect in _HOVER_EFFECT_IDS else "lift"
        active_effect = str(raw.get("active_effect", "glow") or "glow")
        key["active_effect"] = active_effect if active_effect in _ACTIVE_EFFECT_IDS else "glow"
        success_effect = str(raw.get("success_effect", "ring") or "ring")
        key["success_effect"] = success_effect if success_effect in _RESULT_EFFECT_IDS else "ring"
        error_effect = str(raw.get("error_effect", "shake") or "shake")
        key["error_effect"] = error_effect if error_effect in _RESULT_EFFECT_IDS else "shake"
        key["animation_speed"] = max(50, min(int(raw.get("animation_speed", 100) or 100), 200))
        key["feedback_duration_ms"] = max(
            250, min(int(raw.get("feedback_duration_ms", 720) or 720), 3000)
        )
        for field in ("active_top", "active_border", "disabled_top", "disabled_text"):
            key[field] = str(
                raw.get(field, INTERACTION_DEFAULTS[field]) or INTERACTION_DEFAULTS[field]
            )
        key["show_status_indicator"] = bool(raw.get("show_status_indicator", True))
        sound_profile = str(raw.get("sound_profile", "none") or "none")
        key["sound_profile"] = sound_profile if sound_profile in _SOUND_PROFILE_IDS else "none"
        sound_event = str(raw.get("sound_event", "press") or "press")
        key["sound_event"] = sound_event if sound_event in _SOUND_EVENT_IDS else "press"
        key["sound_path"] = str(raw.get("sound_path", "") or "")
        key["sound_volume"] = max(0, min(int(raw.get("sound_volume", 65) or 0), 100))
        asset_playback = str(raw.get("asset_playback", "always") or "always")
        key["asset_playback"] = (
            asset_playback if asset_playback in _ASSET_PLAYBACK_IDS else "always"
        )
        key["reduce_motion"] = bool(raw.get("reduce_motion", False))
        key["active"] = bool(raw.get("active", False))
        keys.append(key)
    icon_pack = str(data.get("icon_pack", DEFAULT_KEYCAP_ICON_PACK_ID) or "")
    if icon_pack not in keycap_icon_pack_ids():
        icon_pack = DEFAULT_KEYCAP_ICON_PACK_ID
    return {
        "version": 3,
        "columns": columns,
        "rows": rows,
        "gap": gap,
        "icon_pack": icon_pack,
        "mosaic_enabled": bool(data.get("mosaic_enabled", False)),
        "mosaic_path": str(data.get("mosaic_path", "") or ""),
        "mosaic_opacity": max(10, min(int(data.get("mosaic_opacity", 92) or 92), 100)),
        "mosaic_show_labels": bool(data.get("mosaic_show_labels", True)),
        "keys": keys,
    }


def deck_from_json(raw: object) -> dict:
    if isinstance(raw, dict):
        return normalize_deck(raw)
    try:
        return normalize_deck(json.loads(str(raw)))
    except (TypeError, ValueError, json.JSONDecodeError):
        return template_deck()


def deck_to_json(deck: dict) -> str:
    return json.dumps(normalize_deck(deck), ensure_ascii=False, separators=(",", ":"))


def apply_pattern(deck: dict, pattern_id: str, selected_ids: set[str] | None = None) -> dict:
    result = normalize_deck(deepcopy(deck))
    selected = selected_ids or {key["id"] for key in result["keys"]}
    styles = [style.style_id for style in KEYCAP_STYLES]
    candidates = [key for key in result["keys"] if key["id"] in selected]
    for index, key in enumerate(candidates):
        if pattern_id == "checker":
            key["style"] = styles[(int(key["row"]) + int(key["column"])) % 2]
        elif pattern_id == "row_groups":
            key["style"] = styles[int(key["row"]) % len(styles)]
        elif pattern_id == "hero":
            key["style"] = "arcade_glow" if int(key["width"]) > 1 else "air_glass"
        elif pattern_id == "flow":
            key["style"] = styles[index % len(styles)]
        elif pattern_id == "function_groups":
            key["style"] = {
                "internal": "air_glass",
                "url": "arcade_glow",
                "open": "mechanical_pbt",
            }.get(str(key["action_type"]), "minimal_mono")
        else:
            key["style"] = DEFAULT_KEYCAP_STYLE_ID
    return result


def reflow_deck(deck: dict) -> dict:
    """Pack keys into the configured grid without overlap, growing rows if needed."""
    result = normalize_deck(deepcopy(deck))
    columns = int(result["columns"])
    occupied: set[tuple[int, int]] = set()
    max_row = int(result["rows"])
    ordered = sorted(
        result["keys"],
        key=lambda key: (int(key["row"]), int(key["column"]), str(key["id"])),
    )
    for key in ordered:
        width = min(int(key["width"]), columns)
        height = int(key["height"])
        placed = False
        for row in range(max_row + len(ordered) * 2 + 1):
            for column in range(columns - width + 1):
                cells = {
                    (candidate_row, candidate_column)
                    for candidate_row in range(row, row + height)
                    for candidate_column in range(column, column + width)
                }
                if occupied.isdisjoint(cells):
                    key["row"], key["column"] = row, column
                    occupied.update(cells)
                    max_row = max(max_row, row + height)
                    placed = True
                    break
            if placed:
                break
    result["rows"] = max(1, max_row)
    result["keys"] = ordered
    return result


__all__ = [
    "ACTION_TYPES",
    "DEFAULT_KEYCAP_STYLE_ID",
    "DECK_VISUAL_FIELDS",
    "DECK_TEMPLATES",
    "INTERNAL_ACTIONS",
    "KEYCAP_ICONS",
    "KEYCAP_OVERRIDE_DEFAULTS",
    "KEYCAP_STYLES",
    "LABEL_LAYOUTS",
    "PATTERNS",
    "KeycapStyle",
    "apply_pattern",
    "clear_keycap_overrides",
    "deck_from_json",
    "deck_to_json",
    "keycap_style",
    "new_key",
    "normalize_deck",
    "preserve_deck_visuals",
    "reflow_deck",
    "template_deck",
]
