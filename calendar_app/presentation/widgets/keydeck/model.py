# -*- coding: utf-8 -*-
"""KeyDeck v4 data model.

Schema, validation, v3 migration, layout utilities, layout templates and themes.
The module deliberately avoids QtGui/QtWidgets so the model stays cheap to test.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import math
from pathlib import PureWindowsPath
import re
import uuid

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.launcher_keycap_assets import keycap_asset_ids
from calendar_app.presentation.widgets.launcher_keycap_icons import keycap_icon_ids
from calendar_app.presentation.widgets.launcher_keycap_sounds import KEYCAP_SOUNDS

DECK_VERSION = 4
GRID_STEP = 0.25
MAX_GRID_W = 24.0
MAX_GRID_H = 10.0
MIN_KEY_U = 1.0
MAX_KEY_W = 6.25
MAX_KEY_H = 4.0
MAX_PAGES = 12
MAX_KEYS_PER_PAGE = 112
HOLD_DELAY_MS = 550
DEFAULT_TEMPLATE_ID = "creator_mixed"
DEFAULT_THEME_ID = "crystal_night"
CUSTOM_THEME_ID = "custom"

# (id, i18n key, Korean fallback)
Option = tuple[str, str, str]

ACTION_TYPES: tuple[Option, ...] = (
    ("app", "widget.launcher.action.app", "앱 · 파일 · 폴더 열기"),
    ("url", "widget.launcher.action.url", "웹 주소 열기"),
    ("hotkey", "widget.launcher.action.hotkey", "단축키 보내기"),
    ("text", "widget.launcher.action.text", "텍스트 스니펫"),
    ("command", "widget.launcher.action.command", "Air Calendar 명령"),
    ("page", "widget.launcher.action.page", "페이지 이동"),
    ("none", "widget.launcher.action.none", "동작 없음"),
)
COMMANDS: tuple[Option, ...] = (
    ("new_task", "widget.launcher.command.new_task", "새 일정"),
    ("today", "widget.launcher.command.today", "오늘로 이동"),
    ("sync_google", "sync_unified.sync_all", "연결된 모든 캘린더 동기화"),
    ("command_palette", "widget.launcher.command.command_palette", "명령 팔레트"),
    ("widget_manager", "widget.launcher.command.widget_manager", "위젯 관리자"),
    ("focus_mode", "widget.launcher.command.focus_mode", "집중 모드"),
    ("view_mode", "widget.launcher.command.view_mode", "보기 전환"),
    ("daily_summary", "widget.launcher.command.daily_summary", "오늘 요약"),
)
PAGE_TARGETS: tuple[Option, ...] = (
    ("next", "widget.launcher.page_target.next", "다음 페이지"),
    ("prev", "widget.launcher.page_target.prev", "이전 페이지"),
)
KEY_MODES: tuple[Option, ...] = (
    ("tap", "widget.launcher.mode.tap", "한 번 누르기"),
    ("toggle", "widget.launcher.mode.toggle", "켜기/끄기 (토글)"),
)
# 토글 키의 켜짐/꺼짐 표시 모양
TOGGLE_INDICATORS: tuple[Option, ...] = (
    ("switch", "widget.launcher.indicator.switch", "미니 스위치"),
    ("bar", "widget.launcher.indicator.bar", "불빛 막대"),
    ("dot", "widget.launcher.indicator.dot", "표시등"),
    ("ring", "widget.launcher.indicator.ring", "테두리 빛"),
    ("none", "widget.launcher.indicator.none", "표시 안 함"),
)
INSERT_KINDS: tuple[Option, ...] = (
    ("none", "widget.launcher.insert.none", "없음 (투명)"),
    ("color", "widget.launcher.insert.color", "단색"),
    ("gradient", "widget.launcher.insert.gradient", "그라데이션"),
    ("pattern", "widget.launcher.insert.pattern", "패턴"),
    ("image", "widget.launcher.insert.image", "내 이미지"),
    ("panorama", "widget.launcher.insert.panorama", "덱 파노라마"),
)
INSERT_FITS: tuple[Option, ...] = (
    ("cover", "widget.launcher.fit.cover", "채우기"),
    ("contain", "widget.launcher.fit.contain", "맞추기"),
    ("stretch", "widget.launcher.fit.stretch", "늘이기"),
)
PLAYBACK_MODES: tuple[Option, ...] = (
    ("hover", "widget.launcher.playback.hover", "마우스를 올릴 때 재생"),
    ("always", "widget.launcher.playback.always", "항상 재생"),
    ("never", "widget.launcher.playback.never", "첫 프레임 고정"),
)
LEGEND_LAYOUTS: tuple[Option, ...] = (
    ("stack", "widget.launcher.legend.stack", "아이콘 + 이름"),
    ("caption", "widget.launcher.legend.caption", "그림 + 아래 이름"),
    ("corner", "widget.launcher.legend.corner", "모서리 글자"),
    ("center", "widget.launcher.legend.center", "이름만 크게"),
    ("glyph", "widget.launcher.legend.glyph", "아이콘만"),
    ("art", "widget.launcher.legend.art", "그림만"),
)
LEGEND_WEIGHTS: tuple[Option, ...] = (
    ("regular", "widget.launcher.weight.regular", "보통"),
    ("medium", "widget.launcher.weight.medium", "중간"),
    ("bold", "widget.launcher.weight.bold", "굵게"),
)
MATERIALS: tuple[Option, ...] = (
    ("crystal", "widget.launcher.material.crystal", "크리스탈 (투명)"),
    ("frosted", "widget.launcher.material.frosted", "프로스티드 (반투명)"),
    ("smoke", "widget.launcher.material.smoke", "스모크"),
    ("pudding", "widget.launcher.material.pudding", "푸딩"),
    ("solid", "widget.launcher.material.solid", "솔리드 PBT"),
)
PROFILES: tuple[Option, ...] = (
    ("cylindrical", "widget.launcher.profile.cylindrical", "체리 · 표준"),
    ("oem", "widget.launcher.profile.oem", "OEM · 일반 키보드"),
    ("spherical", "widget.launcher.profile.spherical", "SA · 높고 둥글게"),
    ("mt3", "widget.launcher.profile.mt3", "MT3 · 깊은 곡면"),
    ("flat", "widget.launcher.profile.flat", "DSA · 낮고 평평"),
    ("xda", "widget.launcher.profile.xda", "XDA · 넓은 윗면"),
    ("low", "widget.launcher.profile.low", "로우 · 얇은 키"),
    ("round", "widget.launcher.profile.round", "원형 · 타자기"),
)
SWITCHES: tuple[Option, ...] = (
    ("linear", "widget.launcher.switch.linear", "적축 · 부드럽게"),
    ("tactile", "widget.launcher.switch.tactile", "갈축 · 걸리는 느낌"),
    ("clicky", "widget.launcher.switch.clicky", "청축 · 딸깍"),
    ("silent", "widget.launcher.switch.silent", "흑축 · 조용하게"),
)
LED_MODES: tuple[Option, ...] = (
    ("reactive", "widget.launcher.led.reactive", "누를 때 켜짐"),
    ("static", "widget.launcher.led.static", "항상 켜짐"),
    ("breathe", "widget.launcher.led.breathe", "토글이 켜진 동안 숨쉬기"),
    ("off", "widget.launcher.led.off", "끔"),
)
CASE_STYLES: tuple[Option, ...] = (
    ("anodized", "widget.launcher.case.anodized", "아노다이즈드 알루미늄"),
    ("silver", "widget.launcher.case.silver", "실버 알루미늄"),
    ("acrylic", "widget.launcher.case.acrylic", "아크릴 샌드위치"),
    ("walnut", "widget.launcher.case.walnut", "월넛 우드"),
    ("floating", "widget.launcher.case.floating", "플로팅 (케이스 없음)"),
)
SOUND_CHOICES: tuple[Option, ...] = (
    ("auto", "widget.launcher.sound.auto", "실제 타건음 (스위치·키캡·케이스 반영)"),
    ("none", "widget.launcher.sound.none", "소리 없음"),
    *((sound.sound_id, sound.label_key, sound.label_default) for sound in KEYCAP_SOUNDS),
    ("custom", "widget.launcher.sound.custom", "내 WAV 파일"),
)


def option_ids(options: tuple[Option, ...]) -> frozenset[str]:
    return frozenset(item[0] for item in options)


def option_label(options: tuple[Option, ...], option_id: str) -> str:
    for item_id, key, fallback in options:
        if item_id == option_id:
            return str(t(key, fallback))
    return option_id


_ACTION_IDS = option_ids(ACTION_TYPES)
COMMAND_IDS = option_ids(COMMANDS)
_MODE_IDS = option_ids(KEY_MODES)
_INDICATOR_IDS = option_ids(TOGGLE_INDICATORS)
_INSERT_KIND_IDS = option_ids(INSERT_KINDS)
_FIT_IDS = option_ids(INSERT_FITS)
# 파노라마는 한 장을 여러 키에 나눠 끼우므로 비율을 깨는 '늘이기'는 제외한다.
PANORAMA_FITS: tuple[Option, ...] = INSERT_FITS[:2]
_PANORAMA_FIT_IDS = option_ids(PANORAMA_FITS)
PANORAMA_ZOOM_RANGE = (100, 400)
_PLAYBACK_IDS = option_ids(PLAYBACK_MODES)
_LAYOUT_IDS = option_ids(LEGEND_LAYOUTS)
_WEIGHT_IDS = option_ids(LEGEND_WEIGHTS)
_MATERIAL_IDS = option_ids(MATERIALS)
_PROFILE_IDS = option_ids(PROFILES)
_SWITCH_IDS = option_ids(SWITCHES)
_LED_IDS = option_ids(LED_MODES)
_CASE_IDS = option_ids(CASE_STYLES)
_SOUND_IDS = option_ids(SOUND_CHOICES)
_PATTERN_IDS = frozenset(keycap_asset_ids() - {"none"})
_ROTATIONS = (0, 90, 180, 270)
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


# ---------------------------------------------------------------------------
# Primitive validators
# ---------------------------------------------------------------------------


def new_id() -> str:
    return uuid.uuid4().hex[:10]


def clean_color(value: object, fallback: str) -> str:
    raw = str(value or "").strip()
    return raw.lower() if _HEX_RE.match(raw) else fallback


def _choice(value: object, allowed: frozenset[str], fallback: str) -> str:
    raw = str(value or "")
    return raw if raw in allowed else fallback


def _bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _int(value: object, low: int, high: int, fallback: int) -> int:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    if math.isnan(number) or math.isinf(number):
        return fallback
    return max(low, min(high, int(round(number))))


def _float(value: object, low: float, high: float, fallback: float) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    if math.isnan(number) or math.isinf(number):
        return fallback
    return max(low, min(high, number))


def _text(value: object, limit: int) -> str:
    return str(value if value is not None else "")[:limit]


def snap_u(value: float) -> float:
    """Snap a u-coordinate to the 0.25u editing grid."""
    return round(round(float(value) / GRID_STEP) * GRID_STEP, 4)


def shade(color: str, factor: float) -> str:
    """Lighten (factor > 1) or darken (factor < 1) a #rrggbb colour without Qt."""
    raw = clean_color(color, "#808080")[:7]
    channels = [int(raw[index : index + 2], 16) for index in (1, 3, 5)]
    if factor >= 1.0:
        mixed = [int(value + (255 - value) * min(1.0, factor - 1.0)) for value in channels]
    else:
        mixed = [int(value * max(0.0, factor)) for value in channels]
    return "#" + "".join(f"{max(0, min(255, value)):02x}" for value in mixed)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def default_action() -> dict:
    return {"type": "none", "target": "", "paste": False}


def default_insert() -> dict:
    return {
        "kind": "none",
        "color": "#26344f",
        "color2": "#0d1424",
        "pattern": "spark",
        "path": "",
        "fit": "cover",
        "zoom": 100,
        "ox": 0,
        "oy": 0,
        "rotate": 0,
        "opacity": 100,
        "playback": "hover",
    }


def default_legend() -> dict:
    return {
        "layout": "stack",
        "size": 100,
        "color": "#f4f7ff",
        "weight": "bold",
        "glyph": "auto",
        "glyph_color": "",
        "shadow": True,
    }


def default_cap() -> dict:
    return {"material": "crystal", "profile": "cylindrical", "color": "#e6eeff"}


def default_led() -> dict:
    return {"mode": "reactive", "color": "#5ab8ff"}


def default_key() -> dict:
    return {
        "id": new_id(),
        "x": 0.0,
        "y": 0.0,
        "w": 1.0,
        "h": 1.0,
        "label": "",
        "sublabel": "",
        "action": default_action(),
        "hold_action": default_action(),
        "mode": "tap",
        "active": False,
        "indicator": "switch",
        "enabled": True,
        "insert": default_insert(),
        "legend": default_legend(),
        "cap": default_cap(),
        "led": default_led(),
        "switch": "tactile",
        "sound": "auto",
        "sound_path": "",
    }


def default_panorama() -> dict:
    return {"path": "", "name": "", "fit": "cover", "x": 0, "y": 0, "zoom": 100}


def normalize_panorama(raw: object) -> dict:
    data = raw if isinstance(raw, dict) else {}
    base = default_panorama()
    path = _text(data.get("path"), 1024).strip()
    return {
        "path": path,
        "name": _text(data.get("name"), 160).strip() if path else "",
        "fit": _choice(data.get("fit"), _PANORAMA_FIT_IDS, base["fit"]),
        "x": _int(data.get("x"), -100, 100, base["x"]),
        "y": _int(data.get("y"), -100, 100, base["y"]),
        "zoom": _int(data.get("zoom"), *PANORAMA_ZOOM_RANGE, base["zoom"]),
    }


def panorama_rect(
    area: tuple[float, float, float, float], image_size: tuple[int, int], panorama: dict
) -> tuple[float, float, float, float]:
    """Where the deck panorama lands over ``area`` as (left, top, width, height).

    ``cover`` fills the area, ``contain`` shows the whole picture, and ``zoom`` enlarges on
    top of either.  ``x``/``y`` align the picture: -100 puts its left/top edge on the area's
    left/top edge, 100 its right/bottom edge, 0 centres it.
    """
    left, top, width, height = (float(value) for value in area)
    image_w = max(1, int(image_size[0]))
    image_h = max(1, int(image_size[1]))
    pick = max if panorama.get("fit", "cover") == "cover" else min
    scale = pick(width / image_w, height / image_h)
    scale *= max(1.0, float(panorama.get("zoom", 100)) / 100.0)
    shown_w, shown_h = image_w * scale, image_h * scale
    align_x = (_float(panorama.get("x", 0), -100.0, 100.0, 0.0) + 100.0) / 200.0
    align_y = (_float(panorama.get("y", 0), -100.0, 100.0, 0.0) + 100.0) / 200.0
    return (
        left + (width - shown_w) * align_x,
        top + (height - shown_h) * align_y,
        shown_w,
        shown_h,
    )


def panorama_align_for(area_extent: float, shown_extent: float, offset: float) -> int | None:
    """Inverse of the ``panorama_rect`` alignment along one axis (None when it cannot move)."""
    slack = float(area_extent) - float(shown_extent)
    if abs(slack) < 0.5:
        return None
    return int(round(max(-100.0, min(100.0, float(offset) / slack * 200.0 - 100.0))))


def suggest_panorama_fit(
    image_size: tuple[int, int], area_size: tuple[float, float], *, transparent: bool = False
) -> str:
    """Default framing for a newly picked panorama.

    Photos fill the keys (``cover``) so no key is left empty.  A see-through graphic such as
    a logo is shown whole (``contain``) when filling would crop away more than half of it.
    """
    image_w, image_h = (float(value) for value in image_size)
    area_w, area_h = (float(value) for value in area_size)
    if not transparent or min(image_w, image_h, area_w, area_h) <= 0:
        return "cover"
    image_ratio = image_w / image_h
    area_ratio = area_w / area_h
    visible = min(image_ratio, area_ratio) / max(image_ratio, area_ratio)
    return "cover" if visible >= 0.5 else "contain"


def panorama_keys(deck: dict, page_index: int | None = None) -> list[dict]:
    """Keys showing the deck panorama (on one page, or on every page when None)."""
    pages = deck.get("pages", [])
    if page_index is not None:
        pages = pages[page_index : page_index + 1]
    return [
        key for page in pages for key in page.get("keys", []) if key["insert"]["kind"] == "panorama"
    ]


def default_case() -> dict:
    return {"style": "anodized", "color": "#1a1e27", "accent": "#5ab8ff", "header": True}


def new_page(name: str = "") -> dict:
    return {"id": new_id(), "name": _text(name, 24), "keys": []}


def default_deck() -> dict:
    return {
        "version": DECK_VERSION,
        "name": "",
        "unit": 68,
        "gap": 6,
        "scale": 100,
        "case": default_case(),
        "led_brightness": 80,
        "sound_enabled": True,
        "sound_volume": 60,
        "reduce_motion": False,
        "panorama": default_panorama(),
        "theme": DEFAULT_THEME_ID,
        "page": 0,
        "pages": [new_page(str(t("widget.launcher.page_main", "메인")))],
    }


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def normalize_action(raw: object) -> dict:
    data = raw if isinstance(raw, dict) else {}
    kind = _choice(data.get("type"), _ACTION_IDS, "none")
    target = _text(data.get("target"), 4000 if kind == "text" else 1024)
    if kind != "text":
        target = target.strip()
    if kind == "command" and target not in COMMAND_IDS:
        target = ""
    if kind == "page" and not target:
        target = "next"
    if kind == "none":
        target = ""
    return {"type": kind, "target": target, "paste": _bool(data.get("paste"), False)}


def _normalize_insert(raw: object) -> dict:
    data = raw if isinstance(raw, dict) else {}
    base = default_insert()
    rotate = _int(data.get("rotate"), 0, 270, 0)
    pattern = str(data.get("pattern") or base["pattern"])
    return {
        "kind": _choice(data.get("kind"), _INSERT_KIND_IDS, base["kind"]),
        "color": clean_color(data.get("color"), base["color"]),
        "color2": clean_color(data.get("color2"), base["color2"]),
        "pattern": pattern if pattern in _PATTERN_IDS else base["pattern"],
        "path": _text(data.get("path"), 1024).strip(),
        "fit": _choice(data.get("fit"), _FIT_IDS, base["fit"]),
        "zoom": _int(data.get("zoom"), 20, 400, base["zoom"]),
        "ox": _int(data.get("ox"), -100, 100, 0),
        "oy": _int(data.get("oy"), -100, 100, 0),
        "rotate": min(_ROTATIONS, key=lambda value: abs(value - rotate)),
        "opacity": _int(data.get("opacity"), 10, 100, base["opacity"]),
        "playback": _choice(data.get("playback"), _PLAYBACK_IDS, base["playback"]),
    }


def _normalize_legend(raw: object) -> dict:
    data = raw if isinstance(raw, dict) else {}
    base = default_legend()
    glyph = str(data.get("glyph") or base["glyph"])
    glyph_color = str(data.get("glyph_color") or "")
    return {
        "layout": _choice(data.get("layout"), _LAYOUT_IDS, base["layout"]),
        "size": _int(data.get("size"), 60, 180, base["size"]),
        "color": clean_color(data.get("color"), base["color"]),
        "weight": _choice(data.get("weight"), _WEIGHT_IDS, base["weight"]),
        "glyph": glyph if glyph in keycap_icon_ids() else base["glyph"],
        "glyph_color": clean_color(glyph_color, "") if glyph_color else "",
        "shadow": _bool(data.get("shadow"), base["shadow"]),
    }


def _normalize_cap(raw: object) -> dict:
    data = raw if isinstance(raw, dict) else {}
    base = default_cap()
    return {
        "material": _choice(data.get("material"), _MATERIAL_IDS, base["material"]),
        "profile": _choice(data.get("profile"), _PROFILE_IDS, base["profile"]),
        "color": clean_color(data.get("color"), base["color"]),
    }


def _normalize_led(raw: object) -> dict:
    data = raw if isinstance(raw, dict) else {}
    base = default_led()
    return {
        "mode": _choice(data.get("mode"), _LED_IDS, base["mode"]),
        "color": clean_color(data.get("color"), base["color"]),
    }


def normalize_key(raw: object) -> dict:
    data = raw if isinstance(raw, dict) else {}
    key = default_key()
    raw_id = str(data.get("id") or "")
    if _ID_RE.match(raw_id):
        key["id"] = raw_id
    width = snap_u(_float(data.get("w"), MIN_KEY_U, MAX_KEY_W, 1.0))
    height = snap_u(_float(data.get("h"), MIN_KEY_U, MAX_KEY_H, 1.0))
    key["w"] = max(MIN_KEY_U, min(MAX_KEY_W, width))
    key["h"] = max(MIN_KEY_U, min(MAX_KEY_H, height))
    key["x"] = max(0.0, min(MAX_GRID_W - key["w"], snap_u(_float(data.get("x"), 0.0, 99.0, 0.0))))
    key["y"] = max(0.0, min(MAX_GRID_H - key["h"], snap_u(_float(data.get("y"), 0.0, 99.0, 0.0))))
    key["label"] = _text(data.get("label"), 48)
    key["sublabel"] = _text(data.get("sublabel"), 32)
    key["action"] = normalize_action(data.get("action"))
    key["hold_action"] = normalize_action(data.get("hold_action"))
    key["mode"] = _choice(data.get("mode"), _MODE_IDS, "tap")
    key["active"] = _bool(data.get("active"), False) and key["mode"] == "toggle"
    key["indicator"] = _choice(data.get("indicator"), _INDICATOR_IDS, "switch")
    key["enabled"] = _bool(data.get("enabled"), True)
    key["insert"] = _normalize_insert(data.get("insert"))
    key["legend"] = _normalize_legend(data.get("legend"))
    key["cap"] = _normalize_cap(data.get("cap"))
    key["led"] = _normalize_led(data.get("led"))
    key["switch"] = _choice(data.get("switch"), _SWITCH_IDS, "tactile")
    key["sound"] = _choice(data.get("sound"), _SOUND_IDS, "auto")
    key["sound_path"] = _text(data.get("sound_path"), 1024).strip()
    return key


def _normalize_page(raw: object, index: int, seen_key_ids: set[str]) -> dict:
    data = raw if isinstance(raw, dict) else {}
    page = new_page()
    raw_id = str(data.get("id") or "")
    if _ID_RE.match(raw_id):
        page["id"] = raw_id
    default_name = str(t("widget.launcher.page_default", "페이지 {number}", number=index + 1))
    page["name"] = _text(data.get("name"), 24).strip() or default_name
    keys = []
    raw_keys = data.get("keys") if isinstance(data.get("keys"), list) else []
    for raw_key in raw_keys[:MAX_KEYS_PER_PAGE]:
        if not isinstance(raw_key, dict):
            continue
        key = normalize_key(raw_key)
        if key["id"] in seen_key_ids:
            key["id"] = new_id()
        seen_key_ids.add(key["id"])
        keys.append(key)
    if has_overlaps(keys):
        settle_layout(keys)
    page["keys"] = keys
    return page


def _looks_like_v3(data: dict) -> bool:
    return "pages" not in data and isinstance(data.get("keys"), list)


def normalize_deck(raw: object) -> dict:
    if isinstance(raw, dict) and _looks_like_v3(raw):
        raw = migrate_v3(raw)
    if not isinstance(raw, dict):
        return build_template_deck()
    deck = default_deck()
    deck["name"] = _text(raw.get("name"), 32).strip()
    deck["unit"] = _int(raw.get("unit"), 48, 112, deck["unit"])
    deck["gap"] = _int(raw.get("gap"), 2, 16, deck["gap"])
    deck["scale"] = _int(raw.get("scale"), 60, 220, deck["scale"])
    case_raw = raw.get("case") if isinstance(raw.get("case"), dict) else {}
    base_case = default_case()
    deck["case"] = {
        "style": _choice(case_raw.get("style"), _CASE_IDS, base_case["style"]),
        "color": clean_color(case_raw.get("color"), base_case["color"]),
        "accent": clean_color(case_raw.get("accent"), base_case["accent"]),
        "header": _bool(case_raw.get("header"), True),
    }
    deck["led_brightness"] = _int(raw.get("led_brightness"), 0, 100, deck["led_brightness"])
    deck["sound_enabled"] = _bool(raw.get("sound_enabled"), True)
    deck["sound_volume"] = _int(raw.get("sound_volume"), 0, 100, deck["sound_volume"])
    deck["reduce_motion"] = _bool(raw.get("reduce_motion"), False)
    deck["panorama"] = normalize_panorama(raw.get("panorama"))
    theme = str(raw.get("theme") or "")
    deck["theme"] = theme if theme in _THEME_IDS or theme == CUSTOM_THEME_ID else CUSTOM_THEME_ID
    seen_key_ids: set[str] = set()
    seen_page_ids: set[str] = set()
    pages = []
    raw_pages = raw.get("pages") if isinstance(raw.get("pages"), list) else []
    for index, raw_page in enumerate(raw_pages[:MAX_PAGES]):
        page = _normalize_page(raw_page, index, seen_key_ids)
        if page["id"] in seen_page_ids:
            page["id"] = new_id()
        seen_page_ids.add(page["id"])
        pages.append(page)
    if not pages:
        pages = [new_page(str(t("widget.launcher.page_main", "메인")))]
    deck["pages"] = pages
    deck["page"] = _int(raw.get("page"), 0, len(pages) - 1, 0)
    valid_targets = {"next", "prev"} | {page["id"] for page in pages}
    for page in pages:
        for key in page["keys"]:
            for field in ("action", "hold_action"):
                action = key[field]
                if action["type"] == "page" and action["target"] not in valid_targets:
                    action["target"] = "next"
    return deck


def deck_from_json(raw: object) -> dict:
    if isinstance(raw, dict):
        return normalize_deck(raw)
    text = str(raw or "").strip()
    if not text:
        return build_template_deck()
    try:
        return normalize_deck(json.loads(text))
    except (TypeError, ValueError):
        return build_template_deck()


def deck_to_json(deck: dict) -> str:
    return json.dumps(normalize_deck(deck), ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Layout utilities (u coordinates)
# ---------------------------------------------------------------------------

_EPS = 1e-6


def key_box(key: dict) -> tuple[float, float, float, float]:
    return (float(key["x"]), float(key["y"]), float(key["w"]), float(key["h"]))


def boxes_overlap(first: tuple, second: tuple) -> bool:
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    return (
        ax < bx + bw - _EPS and bx < ax + aw - _EPS and ay < by + bh - _EPS and by < ay + ah - _EPS
    )


def has_overlaps(keys: list[dict]) -> bool:
    boxes = [key_box(key) for key in keys]
    return any(
        boxes_overlap(boxes[i], boxes[j])
        for i in range(len(boxes))
        for j in range(i + 1, len(boxes))
    )


def layout_bounds(keys: list[dict]) -> tuple[float, float, float, float]:
    """Return (min_x, min_y, max_x, max_y) of a key list, (0, 0, 0, 0) when empty."""
    if not keys:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        min(float(key["x"]) for key in keys),
        min(float(key["y"]) for key in keys),
        max(float(key["x"]) + float(key["w"]) for key in keys),
        max(float(key["y"]) + float(key["h"]) for key in keys),
    )


def find_free_slot(
    keys: list[dict],
    width: float,
    height: float,
    *,
    columns: float | None = None,
    near: tuple[float, float] | None = None,
    exclude: set[str] | frozenset[str] = frozenset(),
) -> tuple[float, float]:
    """Find the first (or nearest to ``near``) free grid slot for a width×height key."""
    boxes = [key_box(key) for key in keys if key.get("id") not in exclude]
    max_x = max((box[0] + box[2] for box in boxes), default=0.0)
    cols = columns if columns else max(max_x, 4.0)
    cols = min(MAX_GRID_W, max(cols, width))
    steps_x = int(round((cols - width) / GRID_STEP)) + 1
    steps_y = int(round((MAX_GRID_H - height) / GRID_STEP)) + 1
    best: tuple[float, float] | None = None
    best_distance = math.inf
    for iy in range(max(1, steps_y)):
        y = iy * GRID_STEP
        if near is not None and best is not None and (y - near[1]) ** 2 > best_distance:
            break
        for ix in range(max(1, steps_x)):
            x = ix * GRID_STEP
            candidate = (x, y, width, height)
            if any(boxes_overlap(candidate, box) for box in boxes):
                continue
            if near is None:
                return (x, y)
            distance = (x - near[0]) ** 2 + ((y - near[1]) ** 2) * 1.2
            if distance < best_distance:
                best, best_distance = (x, y), distance
    if best is not None:
        return best
    if cols < MAX_GRID_W:
        return find_free_slot(keys, width, height, columns=MAX_GRID_W, near=near, exclude=exclude)
    max_y = max((box[1] + box[3] for box in boxes), default=0.0)
    return (0.0, snap_u(min(max_y, MAX_GRID_H - height)))


def settle_layout(keys: list[dict], anchor_ids: set[str] | frozenset[str] = frozenset()) -> None:
    """Relocate keys that overlap anchors (or earlier keys) to their nearest free slot."""
    anchors = [key for key in keys if key["id"] in anchor_ids]
    others = sorted(
        (key for key in keys if key["id"] not in anchor_ids),
        key=lambda key: (float(key["y"]), float(key["x"])),
    )
    placed = list(anchors)
    _min_x, _min_y, max_x, _max_y = layout_bounds(keys)
    columns = max(max_x, 1.0)
    for key in others:
        box = key_box(key)
        if any(boxes_overlap(box, key_box(other)) for other in placed):
            key["x"], key["y"] = find_free_slot(
                placed, float(key["w"]), float(key["h"]), columns=columns, near=(box[0], box[1])
            )
        placed.append(key)


def normalize_origin(keys: list[dict]) -> None:
    """Shift a page so its top-left key touches (0, 0)."""
    if not keys:
        return
    min_x, min_y, _max_x, _max_y = layout_bounds(keys)
    if min_x <= _EPS and min_y <= _EPS:
        return
    for key in keys:
        key["x"] = snap_u(float(key["x"]) - min_x)
        key["y"] = snap_u(float(key["y"]) - min_y)


def reflow_keys(keys: list[dict], columns: float) -> None:
    """Pack keys in reading order into a grid ``columns`` u wide."""
    columns = max(MIN_KEY_U, min(MAX_GRID_W, float(columns)))
    placed: list[dict] = []
    for key in sorted(keys, key=lambda item: (float(item["y"]), float(item["x"]))):
        key["w"] = min(float(key["w"]), columns)
        key["x"], key["y"] = find_free_slot(
            placed, float(key["w"]), float(key["h"]), columns=columns
        )
        placed.append(key)


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

STYLE_FIELDS = ("insert", "legend", "cap", "led", "indicator", "switch", "sound", "sound_path")


def copy_key_style(key: dict) -> dict:
    return {field: deepcopy(key.get(field)) for field in STYLE_FIELDS}


def paste_key_style(key: dict, style: dict) -> None:
    glyph = key.get("legend", {}).get("glyph", "auto")
    for field in STYLE_FIELDS:
        if field in style:
            key[field] = deepcopy(style[field])
    # 글리프는 키의 정체성이므로 스타일 붙여넣기에서 유지한다.
    key["legend"]["glyph"] = glyph


def inherit_style(key: dict, reference: dict | None) -> dict:
    """Give a freshly created key the look of a sibling so new keys match the theme."""
    if reference is None:
        return key
    style = copy_key_style(reference)
    if style["insert"]["kind"] in {"image"}:
        style["insert"]["kind"] = "gradient"
        style["insert"]["path"] = ""
    paste_key_style(key, style)
    key["legend"]["glyph"] = "auto"
    return key


def duplicate_key(key: dict) -> dict:
    copy = deepcopy(key)
    copy["id"] = new_id()
    copy["active"] = False
    return copy


def make_key(label: str, action_type: str = "none", target: str = "") -> dict:
    key = default_key()
    key["label"] = _text(label, 48)
    key["action"] = normalize_action({"type": action_type, "target": target})
    return key


def current_page(deck: dict) -> dict:
    pages = deck["pages"]
    return pages[max(0, min(int(deck.get("page", 0)), len(pages) - 1))]


def page_index_by_id(deck: dict, page_id: str) -> int | None:
    for index, page in enumerate(deck["pages"]):
        if page["id"] == page_id:
            return index
    return None


def resolve_page_target(deck: dict, target: str) -> int:
    count = len(deck["pages"])
    index = int(deck.get("page", 0))
    if target == "next":
        return (index + 1) % count
    if target == "prev":
        return (index - 1) % count
    found = page_index_by_id(deck, target)
    return index if found is None else found


_HOTKEY_GLYPHS = {
    "CTRL+C": "copy",
    "CTRL+V": "paste",
    "CTRL+X": "cut",
    "CTRL+Z": "undo",
    "CTRL+Y": "redo",
    "CTRL+SHIFT+Z": "redo",
    "CTRL+S": "save",
    "CTRL+F": "search",
    "UP": "arrow_up",
    "DOWN": "arrow_down",
    "LEFT": "arrow_left",
    "RIGHT": "arrow_right",
    "VOLUMEMUTE": "volume_mute",
    "VOLUMEUP": "volume_up",
    "VOLUMEDOWN": "volume_up",
    "MEDIAPLAY": "play_pause",
    "MEDIANEXT": "next_track",
    "MEDIAPREVIOUS": "prev_track",
}
_COMMAND_GLYPHS = {
    "new_task": "plus",
    "today": "calendar",
    "sync_google": "sync",
    "command_palette": "search",
    "widget_manager": "dashboard",
    "focus_mode": "focus",
    "view_mode": "layers",
    "daily_summary": "memo",
}


def auto_glyph(action: dict) -> str:
    """Pick a glyph id that describes an action when the key uses glyph='auto'."""
    kind = str(action.get("type", "none"))
    target = str(action.get("target", ""))
    if kind == "command":
        return _COMMAND_GLYPHS.get(target, "play")
    if kind == "url":
        return "globe"
    if kind == "hotkey":
        return _HOTKEY_GLYPHS.get(target.upper().replace(" ", ""), "keyboard")
    if kind == "text":
        return "clipboard"
    if kind == "page":
        return {"next": "forward", "prev": "arrow_left"}.get(target, "layers")
    if kind == "app":
        return "rocket"
    return "none"


# ---------------------------------------------------------------------------
# v3 migration
# ---------------------------------------------------------------------------

_V3_STYLES = {
    "air_glass": ("crystal", "#e8f0ff", "#5ab8ff", "#f4f7ff"),
    "mechanical_pbt": ("solid", "#e2a23c", "#ffb347", "#241705"),
    "soft_clay": ("pudding", "#c28cf5", "#c77dff", "#ffffff"),
    "arcade_glow": ("smoke", "#173049", "#48edff", "#e8feff"),
    "minimal_mono": ("solid", "#42484f", "#c7ccd3", "#ffffff"),
}
_V3_ACTIONS = {"open": "app", "url": "url", "hotkey": "hotkey", "internal": "command"}
_V3_LAYOUTS = {
    "icon_above": "stack",
    "icon_left": "stack",
    "text_only": "center",
    "icon_only": "glyph",
}


def migrate_v3(raw: dict) -> dict:
    """Convert a v3 launcher deck (single grid of keys) into the v4 page schema."""
    mosaic = bool(raw.get("mosaic_enabled")) and bool(str(raw.get("mosaic_path") or ""))
    keys = []
    for old in raw.get("keys", []):
        if not isinstance(old, dict):
            continue
        material, cap_color, led_color, legend_color = _V3_STYLES.get(
            str(old.get("style") or ""), _V3_STYLES["air_glass"]
        )
        custom_top = clean_color(old.get("custom_top"), "")
        if custom_top:
            cap_color = custom_top[:7]
        custom_text = clean_color(old.get("custom_text"), "")
        if custom_text:
            legend_color = custom_text[:7]
        key = default_key()
        key.update(
            {
                "id": str(old.get("id") or new_id()),
                "x": old.get("column", 0),
                "y": old.get("row", 0),
                "w": old.get("width", 1),
                "h": old.get("height", 1),
                "label": str(old.get("label") or ""),
                "mode": "toggle" if old.get("interaction_mode") == "toggle" else "tap",
                "active": bool(old.get("active", False)),
                "enabled": bool(old.get("enabled", True)),
                "action": {
                    "type": _V3_ACTIONS.get(str(old.get("action_type") or ""), "app"),
                    "target": str(old.get("target") or ""),
                    "paste": False,
                },
            }
        )
        key["cap"].update({"material": material, "color": cap_color})
        key["led"].update({"color": led_color})
        icon = str(old.get("icon") or "auto")
        key["legend"].update(
            {
                "color": legend_color,
                "glyph": icon if icon in keycap_icon_ids() else "auto",
                "layout": _V3_LAYOUTS.get(str(old.get("label_layout") or ""), "stack"),
                "size": _int(old.get("font_scale"), 60, 180, 100),
            }
        )
        insert = key["insert"]
        asset_path = str(old.get("asset_path") or "")
        asset_id = str(old.get("asset_id") or "none")
        if mosaic:
            insert["kind"] = "panorama"
        elif asset_path:
            insert.update({"kind": "image", "path": asset_path})
        elif asset_id in _PATTERN_IDS:
            insert.update(
                {
                    "kind": "pattern",
                    "pattern": asset_id,
                    "color": shade(cap_color, 0.42),
                    "color2": shade(cap_color, 0.16),
                }
            )
        profile = str(old.get("sound_profile") or "none")
        if profile == "custom":
            key["sound"], key["sound_path"] = "custom", str(old.get("sound_path") or "")
        elif profile == "system":
            key["sound"] = "auto"
        else:
            key["sound"] = profile if profile in _SOUND_IDS else "none"
        keys.append(key)
    reduce_motion = any(
        bool(old.get("reduce_motion")) for old in raw.get("keys", []) if isinstance(old, dict)
    )
    return {
        "version": DECK_VERSION,
        "gap": raw.get("gap", 6),
        "theme": CUSTOM_THEME_ID,
        "reduce_motion": reduce_motion,
        "panorama": {
            "path": str(raw.get("mosaic_path") or "") if mosaic else "",
            "name": PureWindowsPath(str(raw.get("mosaic_path") or "")).name if mosaic else "",
        },
        "pages": [
            {"id": new_id(), "name": str(t("widget.launcher.page_main", "메인")), "keys": keys}
        ],
    }


# ---------------------------------------------------------------------------
# Layout templates
# ---------------------------------------------------------------------------


def _label(name: str, fallback: str) -> str:
    return str(t(f"widget.launcher.key.{name}", fallback))


def _k(
    name: str,
    fallback: str,
    x: float,
    y: float,
    w: float = 1.0,
    h: float = 1.0,
    *,
    action: tuple[str, str] = ("none", ""),
    pattern: str = "",
    layout: str = "stack",
    sublabel: str = "",
) -> dict:
    key = default_key()
    key.update({"x": x, "y": y, "w": w, "h": h, "label": _label(name, fallback)})
    key["sublabel"] = sublabel
    key["action"] = normalize_action({"type": action[0], "target": action[1]})
    key["legend"]["layout"] = layout
    if pattern:
        key["insert"]["pattern"] = pattern
    return key


def _cmd(command_id: str) -> tuple[str, str]:
    return ("command", command_id)


def _hot(sequence: str) -> tuple[str, str]:
    return ("hotkey", sequence)


def _template_macro_3x3() -> list[dict]:
    return [
        _k("new_schedule", "새 일정", 0, 0, action=_cmd("new_task"), pattern="sunburst"),
        _k("today", "오늘", 1, 0, action=_cmd("today"), pattern="grid"),
        _k("sync", "동기화", 2, 0, action=_cmd("sync_google"), pattern="orbit"),
        _k("command", "명령", 0, 1, action=_cmd("command_palette"), pattern="prism"),
        _k("folder", "폴더", 1, 1, action=("app", ""), pattern="blocks"),
        _k("web", "웹", 2, 1, action=("url", "https://"), pattern="waves"),
        _k("copy", "복사", 0, 2, action=_hot("Ctrl+C"), pattern="circuit", sublabel="Ctrl+C"),
        _k("paste", "붙여넣기", 1, 2, action=_hot("Ctrl+V"), pattern="hexmesh", sublabel="Ctrl+V"),
        _k("focus", "집중", 2, 2, action=_cmd("focus_mode"), pattern="target"),
    ]


def _template_stream_5x3() -> list[dict]:
    return [
        _k("new_schedule", "새 일정", 0, 0, action=_cmd("new_task"), pattern="sunburst"),
        _k("today", "오늘", 1, 0, action=_cmd("today"), pattern="grid"),
        _k("sync", "동기화", 2, 0, action=_cmd("sync_google"), pattern="orbit"),
        _k("command", "명령", 3, 0, action=_cmd("command_palette"), pattern="prism"),
        _k("widgets", "위젯", 4, 0, action=_cmd("widget_manager"), pattern="blocks"),
        _k("copy", "복사", 0, 1, action=_hot("Ctrl+C"), pattern="circuit"),
        _k("paste", "붙여넣기", 1, 1, action=_hot("Ctrl+V"), pattern="hexmesh"),
        _k("cut", "잘라내기", 2, 1, action=_hot("Ctrl+X"), pattern="chevrons"),
        _k("undo", "실행 취소", 3, 1, action=_hot("Ctrl+Z"), pattern="rings"),
        _k("redo", "다시 실행", 4, 1, action=_hot("Ctrl+Y"), pattern="speed"),
        _k("mute", "음소거", 0, 2, action=_hot("VolumeMute"), pattern="equalizer"),
        _k("volume_down", "볼륨 -", 1, 2, action=_hot("VolumeDown"), pattern="scanlines"),
        _k("volume_up", "볼륨 +", 2, 2, action=_hot("VolumeUp"), pattern="equalizer"),
        _k("play_pause", "재생", 3, 2, action=_hot("MediaPlay"), pattern="spark"),
        _k("next_track", "다음 곡", 4, 2, action=_hot("MediaNext"), pattern="chevrons"),
    ]


def _template_creator_mixed() -> list[dict]:
    return [
        _k("start_work", "업무 시작", 0, 0, 2, action=_cmd("command_palette"), pattern="spark"),
        _k("schedule", "일정", 2, 0, action=_cmd("new_task"), pattern="sunburst"),
        _k("today", "오늘", 3, 0, action=_cmd("today"), pattern="grid"),
        _k("design", "디자인", 0, 1, 1, 2, action=("app", ""), pattern="prism"),
        _k("folder", "폴더", 1, 1, 2, action=("app", ""), pattern="blocks"),
        _k("sync", "동기화", 3, 1, action=_cmd("sync_google"), pattern="orbit"),
        _k("web", "웹", 1, 2, action=("url", "https://"), pattern="waves"),
        _k(
            "daily_summary",
            "오늘 요약",
            2,
            2,
            2,
            action=_cmd("daily_summary"),
            pattern="constellation",
        ),
    ]


def _template_numpad() -> list[dict]:
    return [
        _k("command", "명령", 0, 0, action=_cmd("command_palette"), pattern="prism"),
        _k("schedule", "일정", 1, 0, action=_cmd("new_task"), pattern="sunburst"),
        _k("today", "오늘", 2, 0, action=_cmd("today"), pattern="grid"),
        _k("sync", "동기화", 3, 0, action=_cmd("sync_google"), pattern="orbit"),
        _k("app_1", "앱 1", 0, 1, action=("app", ""), pattern="blocks"),
        _k("app_2", "앱 2", 1, 1, action=("app", ""), pattern="circuit"),
        _k("app_3", "앱 3", 2, 1, action=("app", ""), pattern="pixels"),
        _k("volume_up", "볼륨 +", 3, 1, 1, 2, action=_hot("VolumeUp"), pattern="equalizer"),
        _k("app_4", "앱 4", 0, 2, action=("app", ""), pattern="hexmesh"),
        _k("app_5", "앱 5", 1, 2, action=("app", ""), pattern="rings"),
        _k("app_6", "앱 6", 2, 2, action=("app", ""), pattern="confetti"),
        _k("web_1", "웹 1", 0, 3, action=("url", "https://"), pattern="waves"),
        _k("web_2", "웹 2", 1, 3, action=("url", "https://"), pattern="rain"),
        _k("web_3", "웹 3", 2, 3, action=("url", "https://"), pattern="portal"),
        _k("focus", "집중", 3, 3, 1, 2, action=_cmd("focus_mode"), pattern="target"),
        _k("folder", "폴더", 0, 4, 2, action=("app", ""), pattern="blocks"),
        _k("summary", "요약", 2, 4, action=_cmd("daily_summary"), pattern="constellation"),
    ]


def _template_command_bar() -> list[dict]:
    return [
        _k("new_schedule", "새 일정", 0, 0, 1.5, action=_cmd("new_task"), pattern="sunburst"),
        _k("today", "오늘", 1.5, 0, action=_cmd("today"), pattern="grid"),
        _k("sync", "동기화", 2.5, 0, action=_cmd("sync_google"), pattern="orbit"),
        _k(
            "command_palette",
            "명령 팔레트",
            3.5,
            0,
            2.25,
            action=_cmd("command_palette"),
            pattern="prism",
        ),
        _k("widgets", "위젯", 5.75, 0, action=_cmd("widget_manager"), pattern="blocks"),
        _k("web", "웹", 6.75, 0, 1.25, action=("url", "https://"), pattern="waves"),
    ]


def _template_edit_cluster() -> list[dict]:
    return [
        _k("copy", "복사", 0, 0, action=_hot("Ctrl+C"), pattern="circuit", sublabel="Ctrl+C"),
        _k("paste", "붙여넣기", 1, 0, action=_hot("Ctrl+V"), pattern="hexmesh", sublabel="Ctrl+V"),
        _k("cut", "잘라내기", 2, 0, action=_hot("Ctrl+X"), pattern="chevrons", sublabel="Ctrl+X"),
        _k("undo", "실행 취소", 0, 1, action=_hot("Ctrl+Z"), pattern="rings", sublabel="Ctrl+Z"),
        _k("redo", "다시 실행", 1, 1, action=_hot("Ctrl+Y"), pattern="speed", sublabel="Ctrl+Y"),
        _k("save", "저장", 2, 1, action=_hot("Ctrl+S"), pattern="blocks", sublabel="Ctrl+S"),
        _k("up", "위", 1, 2.5, action=_hot("Up"), layout="glyph", pattern="grid"),
        _k("left", "왼쪽", 0, 3.5, action=_hot("Left"), layout="glyph", pattern="grid"),
        _k("down", "아래", 1, 3.5, action=_hot("Down"), layout="glyph", pattern="grid"),
        _k("right", "오른쪽", 2, 3.5, action=_hot("Right"), layout="glyph", pattern="grid"),
    ]


def _template_side_dock() -> list[dict]:
    return [
        _k("start_work", "업무 시작", 0, 0, 2, action=_cmd("command_palette"), pattern="spark"),
        _k("schedule", "일정", 0, 1, action=_cmd("new_task"), pattern="sunburst"),
        _k("today", "오늘", 1, 1, action=_cmd("today"), pattern="grid"),
        _k("sync", "동기화", 0, 2, action=_cmd("sync_google"), pattern="orbit"),
        _k("widgets", "위젯", 1, 2, action=_cmd("widget_manager"), pattern="blocks"),
        _k("folder", "폴더", 0, 3, action=("app", ""), pattern="hexmesh"),
        _k("web", "웹", 1, 3, action=("url", "https://"), pattern="waves"),
        _k("focus", "집중", 0, 4, action=_cmd("focus_mode"), pattern="target"),
        _k("summary", "요약", 1, 4, action=_cmd("daily_summary"), pattern="constellation"),
    ]


# ---------------------------------------------------------------------------
# 기본 키보드 배열 (ANSI 위치 + 두벌식 한글 각인)
# ---------------------------------------------------------------------------

_HANGUL_JAMO = dict(
    zip(
        "QWERTYUIOPASDFGHJKLZXCVBNM",
        "ㅂㅈㄷㄱㅅㅛㅕㅑㅐㅔㅁㄴㅇㄹㅎㅗㅓㅏㅣㅋㅌㅊㅍㅠㅜㅡ",
        strict=True,
    )
)
MODIFIER_KEYS = ("Ctrl", "Shift", "Alt", "Win")
_KEYCAP_LEGEND_SIZE = 120  # 각인·보조 각인(한글·기호)이 작은 키에서도 읽히도록
_MODIFIER_ALIASES = {
    "CTRL": "Ctrl",
    "CONTROL": "Ctrl",
    "SHIFT": "Shift",
    "ALT": "Alt",
    "WIN": "Win",
    "WINDOWS": "Win",
    "META": "Win",
}

# (각인, 보조 각인, 보낼 키, 너비) — 알파벳 한 글자는 한글 자모를 보조 각인으로 붙인다.
_KB_NUMBER_ROW = (
    ("1", "!", "1", 1.0),
    ("2", "@", "2", 1.0),
    ("3", "#", "3", 1.0),
    ("4", "$", "4", 1.0),
    ("5", "%", "5", 1.0),
    ("6", "^", "6", 1.0),
    ("7", "&", "7", 1.0),
    ("8", "*", "8", 1.0),
    ("9", "(", "9", 1.0),
    ("0", ")", "0", 1.0),
    ("-", "_", "Minus", 1.0),
    ("=", "+", "Equal", 1.0),
    ("Backspace", "", "Backspace", 2.0),
)
_KB_ROWS = (
    (
        ("Tab", "", "Tab", 1.5),
        *"QWERTYUIOP",
        ("[", "{", "LBracket", 1.0),
        ("]", "}", "RBracket", 1.0),
        ("\\", "|", "Backslash", 1.5),
    ),
    (
        ("Caps Lock", "", "CapsLock", 1.75),
        *"ASDFGHJKL",
        (";", ":", "Semicolon", 1.0),
        ("'", '"', "Quote", 1.0),
        ("Enter", "", "Enter", 2.25),
    ),
    (
        ("Shift", "", "Shift", 2.25),
        *"ZXCVBNM",
        (",", "<", "Comma", 1.0),
        (".", ">", "Period", 1.0),
        ("/", "?", "Slash", 1.0),
        ("Shift", "", "Shift", 2.75),
    ),
    (
        ("Ctrl", "", "Ctrl", 1.25),
        ("Win", "", "Win", 1.25),
        ("Alt", "", "Alt", 1.25),
        ("Space", "", "Space", 6.25),
        ("@hangul", "", "Hangul", 1.25),
        ("Win", "", "Win", 1.25),
        ("Menu", "", "Apps", 1.25),
        ("@hanja", "", "Hanja", 1.25),
    ),
)
_KB_FUNCTION_ROW = (
    ("Esc", "Esc", 0.0),
    ("F1", "F1", 2.0),
    ("F2", "F2", 3.0),
    ("F3", "F3", 4.0),
    ("F4", "F4", 5.0),
    ("F5", "F5", 6.5),
    ("F6", "F6", 7.5),
    ("F7", "F7", 8.5),
    ("F8", "F8", 9.5),
    ("F9", "F9", 11.0),
    ("F10", "F10", 12.0),
    ("F11", "F11", 13.0),
    ("F12", "F12", 14.0),
    ("PrtSc", "PrintScreen", 15.25),
    ("ScrLk", "ScrollLock", 16.25),
    ("Pause", "Pause", 17.25),
)
# (각인, 보낼 키, x, 줄) — 줄은 본 자판 첫 줄 기준 0~4
_KB_NAV = (
    ("Ins", "Insert", 15.25, 0),
    ("Home", "Home", 16.25, 0),
    ("PgUp", "PageUp", 17.25, 0),
    ("Del", "Delete", 15.25, 1),
    ("End", "End", 16.25, 1),
    ("PgDn", "PageDown", 17.25, 1),
    ("↑", "Up", 16.25, 3),
    ("←", "Left", 15.25, 4),
    ("↓", "Down", 16.25, 4),
    ("→", "Right", 17.25, 4),
)
# (각인, 보조 각인, 보낼 키, x, 줄, 너비, 높이)
_KB_NUMPAD = (
    ("Num", "", "NumLock", 18.5, 0, 1.0, 1.0),
    ("/", "", "NumDivide", 19.5, 0, 1.0, 1.0),
    ("*", "", "NumMultiply", 20.5, 0, 1.0, 1.0),
    ("-", "", "NumSubtract", 21.5, 0, 1.0, 1.0),
    ("7", "Home", "Num7", 18.5, 1, 1.0, 1.0),
    ("8", "↑", "Num8", 19.5, 1, 1.0, 1.0),
    ("9", "PgUp", "Num9", 20.5, 1, 1.0, 1.0),
    ("+", "", "NumAdd", 21.5, 1, 1.0, 2.0),
    ("4", "←", "Num4", 18.5, 2, 1.0, 1.0),
    ("5", "", "Num5", 19.5, 2, 1.0, 1.0),
    ("6", "→", "Num6", 20.5, 2, 1.0, 1.0),
    ("1", "End", "Num1", 18.5, 3, 1.0, 1.0),
    ("2", "↓", "Num2", 19.5, 3, 1.0, 1.0),
    ("3", "PgDn", "Num3", 20.5, 3, 1.0, 1.0),
    ("Enter", "", "Enter", 21.5, 3, 1.0, 2.0),
    ("0", "Ins", "Num0", 18.5, 4, 2.0, 1.0),
    (".", "Del", "NumDecimal", 20.5, 4, 1.0, 1.0),
)


def modifier_name(key: dict) -> str:
    """Canonical modifier (``Shift``…) when ``key`` is a sticky modifier toggle, else ``""``."""
    action = key.get("action", {})
    if key.get("mode") != "toggle" or action.get("type") != "hotkey":
        return ""
    parts = [part.strip().upper() for part in str(action.get("target", "")).split("+")]
    return _MODIFIER_ALIASES.get(parts[0], "") if len(parts) == 1 else ""


def combine_hotkey(modifiers: list[str], target: str) -> str:
    """Prefix held sticky modifiers to a hotkey (``["Shift"]`` + ``"A"`` → ``"Shift+A"``)."""
    parts: list[str] = []
    seen: set[str] = set()
    for part in [*modifiers, *str(target).split("+")]:
        part = part.strip()
        canonical = _MODIFIER_ALIASES.get(part.upper(), part).upper()
        if part and canonical not in seen:
            seen.add(canonical)
            parts.append(_MODIFIER_ALIASES.get(part.upper(), part))
    return "+".join(parts)


def _kb_key(
    label: str, sublabel: str, send: str, x: float, y: float, w: float = 1.0, h: float = 1.0
) -> dict:
    key = default_key()
    if label.startswith("@"):
        name = label[1:]
        label = _label(f"kb_{name}", {"hangul": "한/영", "hanja": "한자"}[name])
    key.update({"x": x, "y": y, "w": w, "h": h, "label": label, "sublabel": sublabel})
    key["action"] = normalize_action({"type": "hotkey", "target": send})
    key["legend"].update({"layout": "corner", "glyph": "none", "size": _KEYCAP_LEGEND_SIZE})
    key["insert"]["kind"] = "none"
    if send in MODIFIER_KEYS:
        # 조합키는 눌러 두면 켜진 채 기다렸다가 다음 키에 붙어 나간다 (화상 키보드 방식).
        key["mode"] = "toggle"
        key["indicator"] = "dot"
    return key


def _kb_main(top: float, *, escape: bool) -> list[dict]:
    """The 60% block (5 rows × 15u) starting at ``top``; ``escape`` puts Esc left of ``1``."""
    keys: list[dict] = []
    first = ("Esc", "", "Esc", 1.0) if escape else ("`", "~", "Backquote", 1.0)
    rows = ((first, *_KB_NUMBER_ROW), *_KB_ROWS)
    for row_index, row in enumerate(rows):
        x = 0.0
        for item in row:
            if isinstance(item, str):
                label, sublabel, send, width = item, _HANGUL_JAMO[item], item, 1.0
            else:
                label, sublabel, send, width = item
            keys.append(_kb_key(label, sublabel, send, x, top + row_index, width))
            x += width
    return keys


def _template_keyboard_60() -> list[dict]:
    return _kb_main(0.0, escape=True)


def _template_keyboard_tkl() -> list[dict]:
    keys = [_kb_key(label, "", send, x, 0.0) for label, send, x in _KB_FUNCTION_ROW]
    keys += _kb_main(1.25, escape=False)
    keys += [_kb_key(label, "", send, x, 1.25 + row) for label, send, x, row in _KB_NAV]
    return keys


def _template_keyboard_full() -> list[dict]:
    keys = _template_keyboard_tkl()
    keys += [
        _kb_key(label, sublabel, send, x, 1.25 + row, w, h)
        for label, sublabel, send, x, row, w, h in _KB_NUMPAD
    ]
    return keys


TEMPLATES = (
    ("macro_3x3", "widget.launcher.template.macro_3x3", "매크로 패드 3×3", _template_macro_3x3),
    ("stream_5x3", "widget.launcher.template.stream_5x3", "스트림 패드 5×3", _template_stream_5x3),
    (
        "creator_mixed",
        "widget.launcher.template.creator_mixed",
        "크리에이터 혼합",
        _template_creator_mixed,
    ),
    ("numpad", "widget.launcher.template.numpad", "넘패드", _template_numpad),
    ("command_bar", "widget.launcher.template.command_bar", "커맨드 바", _template_command_bar),
    (
        "edit_cluster",
        "widget.launcher.template.edit_cluster",
        "편집 클러스터",
        _template_edit_cluster,
    ),
    ("side_dock", "widget.launcher.template.side_dock", "사이드 독", _template_side_dock),
    (
        "keyboard_full",
        "widget.launcher.template.keyboard_full",
        "풀배열 키보드 (104키)",
        _template_keyboard_full,
    ),
    (
        "keyboard_tkl",
        "widget.launcher.template.keyboard_tkl",
        "텐키리스 키보드 (87키)",
        _template_keyboard_tkl,
    ),
    (
        "keyboard_60",
        "widget.launcher.template.keyboard_60",
        "60% 키보드 (61키)",
        _template_keyboard_60,
    ),
)
# 실제 키보드처럼 그림 없이 각인만 보이는 배열 (테마를 입혀도 인서트·레전드 유지)
KEYBOARD_TEMPLATE_IDS = frozenset({"keyboard_full", "keyboard_tkl", "keyboard_60"})
_TEMPLATE_BY_ID = {item[0]: item for item in TEMPLATES}


def template_keys(template_id: str) -> list[dict]:
    entry = _TEMPLATE_BY_ID.get(str(template_id), _TEMPLATE_BY_ID[DEFAULT_TEMPLATE_ID])
    return [normalize_key(key) for key in entry[3]()]


# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DeckTheme:
    theme_id: str
    label_key: str
    label_default: str
    case_style: str
    case_color: str
    accent: str
    material: str
    profile: str
    cap_color: str
    switch: str
    led_mode: str
    led_colors: tuple[str, ...]
    legend_color: str
    legend_weight: str
    insert_kind: str
    insert_palette: tuple[tuple[str, str], ...] = ()
    hero_cap_color: str = ""
    hero_legend_color: str = ""


THEMES = (
    DeckTheme(
        "crystal_night",
        "widget.launcher.theme.crystal_night",
        "크리스탈 나이트",
        "anodized",
        "#171b23",
        "#5ab8ff",
        "crystal",
        "cylindrical",
        "#e8f0ff",
        "tactile",
        "reactive",
        ("#5ab8ff",),
        "#f5f8ff",
        "bold",
        "pattern",
        (("#233a63", "#0b1322"), ("#2c2458", "#0f0b24"), ("#12454f", "#071a1f")),
    ),
    DeckTheme(
        "frost_paper",
        "widget.launcher.theme.frost_paper",
        "프로스트 페이퍼",
        "silver",
        "#c9ced6",
        "#ff8a5b",
        "frosted",
        "spherical",
        "#ffffff",
        "linear",
        "static",
        ("#fff1e0",),
        "#2b2f38",
        "bold",
        "gradient",
        (
            ("#fde2e4", "#f6c1c7"),
            ("#dff0ea", "#b8e0dc"),
            ("#fff1e2", "#fbd9b8"),
            ("#e8e3f6", "#cdc2ee"),
        ),
        "#ff8a5b",
        "#ffffff",
    ),
    DeckTheme(
        "smoke_neon",
        "widget.launcher.theme.smoke_neon",
        "스모크 네온",
        "anodized",
        "#0b0d12",
        "#ff3df0",
        "smoke",
        "cylindrical",
        "#1a1d24",
        "clicky",
        "static",
        ("#ff3df0", "#3dd9ff"),
        "#ffffff",
        "bold",
        "pattern",
        (("#2a0f3d", "#07040f"), ("#062e38", "#02090c")),
    ),
    DeckTheme(
        "pudding_pop",
        "widget.launcher.theme.pudding_pop",
        "푸딩 팝",
        "acrylic",
        "#e7ecf5",
        "#7c5cff",
        "pudding",
        "spherical",
        "#f7f4ff",
        "linear",
        "reactive",
        ("#ff5f7e", "#ffb35c", "#ffe45c", "#5cf29a", "#5cc8ff", "#9b7bff"),
        "#2a2340",
        "bold",
        "color",
        (
            ("#fff0f3", "#ffd6de"),
            ("#fff6e8", "#ffe2bd"),
            ("#eefcf4", "#c9f5dc"),
            ("#eef4ff", "#cfe0ff"),
        ),
    ),
    DeckTheme(
        "graphite_pbt",
        "widget.launcher.theme.graphite_pbt",
        "그래파이트 PBT",
        "anodized",
        "#2a2d33",
        "#ff7a1a",
        "solid",
        "cylindrical",
        "#3b3f46",
        "tactile",
        "off",
        ("#ff7a1a",),
        "#eceef2",
        "medium",
        "none",
        (),
        "#ff7a1a",
        "#1d1f23",
    ),
    DeckTheme(
        "walnut_studio",
        "widget.launcher.theme.walnut_studio",
        "월넛 스튜디오",
        "walnut",
        "#6b4226",
        "#d98c3f",
        "solid",
        "spherical",
        "#efe6d2",
        "linear",
        "off",
        ("#ffcf8a",),
        "#3b2a1a",
        "bold",
        "none",
        (),
        "#d98c3f",
        "#fffaf0",
    ),
    DeckTheme(
        "floating_glass",
        "widget.launcher.theme.floating_glass",
        "플로팅 글래스",
        "floating",
        "#10141c",
        "#7cc4ff",
        "crystal",
        "flat",
        "#eef6ff",
        "silent",
        "reactive",
        ("#7cc4ff",),
        "#ffffff",
        "bold",
        "gradient",
        (
            ("#3a7bd5", "#00d2ff"),
            ("#6a3093", "#a044ff"),
            ("#11998e", "#38ef7d"),
            ("#ee0979", "#ff6a00"),
        ),
    ),
)
_THEME_BY_ID = {theme.theme_id: theme for theme in THEMES}
_THEME_IDS = frozenset(_THEME_BY_ID)
_PATTERN_CYCLE = ("spark", "orbit", "grid", "prism", "blocks", "waves", "circuit", "rings")


def deck_theme(theme_id: object) -> DeckTheme:
    return _THEME_BY_ID.get(str(theme_id or ""), _THEME_BY_ID[DEFAULT_THEME_ID])


def _is_hero(key: dict) -> bool:
    return float(key["w"]) >= 1.75 or float(key["h"]) >= 1.75


def apply_theme(
    deck: dict,
    theme_id: str,
    *,
    page_index: int | None = None,
    key_ids: set[str] | None = None,
    keep_art: bool = True,
) -> dict:
    """Apply a theme's case, keycap, LED and insert recipe; user images survive by default."""
    theme = deck_theme(theme_id)
    if page_index is None and key_ids is None:
        deck["theme"] = theme.theme_id
        deck["case"].update(
            {"style": theme.case_style, "color": theme.case_color, "accent": theme.accent}
        )
    pages = deck["pages"] if page_index is None else [deck["pages"][page_index]]
    for page in pages:
        for index, key in enumerate(page["keys"]):
            if key_ids is not None and key["id"] not in key_ids:
                continue
            hero = _is_hero(key)
            key["cap"]["material"] = theme.material
            key["cap"]["profile"] = theme.profile
            key["cap"]["color"] = (
                theme.hero_cap_color if hero and theme.hero_cap_color else theme.cap_color
            )
            key["switch"] = theme.switch
            key["led"] = {
                "mode": theme.led_mode,
                "color": theme.led_colors[index % len(theme.led_colors)],
            }
            key["legend"]["color"] = (
                theme.hero_legend_color if hero and theme.hero_legend_color else theme.legend_color
            )
            key["legend"]["weight"] = theme.legend_weight
            insert = key["insert"]
            if keep_art and insert["kind"] in {"image", "panorama"}:
                continue
            insert["kind"] = theme.insert_kind
            if hero and theme.hero_cap_color:
                insert["color"] = shade(theme.hero_cap_color, 1.14)
                insert["color2"] = theme.hero_cap_color
            elif theme.insert_palette:
                first, second = theme.insert_palette[index % len(theme.insert_palette)]
                insert["color"], insert["color2"] = first, second
            if insert.get("pattern") not in _PATTERN_IDS:
                insert["pattern"] = _PATTERN_CYCLE[index % len(_PATTERN_CYCLE)]
    return deck


def _keep_keycap_legends(keys: list[dict]) -> None:
    """Keyboard layouts stay plain printed keycaps whatever theme is applied."""
    for key in keys:
        key["insert"]["kind"] = "none"
        key["legend"]["layout"] = "corner"
        key["legend"]["glyph"] = "none"
        key["legend"]["size"] = _KEYCAP_LEGEND_SIZE


def build_template_deck(
    template_id: str = DEFAULT_TEMPLATE_ID, theme_id: str = DEFAULT_THEME_ID
) -> dict:
    deck = default_deck()
    deck["pages"][0]["keys"] = template_keys(template_id)
    apply_theme(deck, theme_id)
    if template_id in KEYBOARD_TEMPLATE_IDS:
        _keep_keycap_legends(deck["pages"][0]["keys"])
    return normalize_deck(deck)


def apply_template_to_page(deck: dict, page_index: int, template_id: str) -> dict:
    """Replace one page's keys with a layout template styled like the current deck."""
    page = deck["pages"][page_index]
    reference = page["keys"][0] if page["keys"] else None
    page["keys"] = template_keys(template_id)
    if deck.get("theme") in _THEME_IDS:
        apply_theme(deck, str(deck["theme"]), page_index=page_index)
    elif reference is not None:
        for key in page["keys"]:
            style = copy_key_style(reference)
            if style["insert"]["kind"] == "image":
                style["insert"]["kind"] = "gradient"
                style["insert"]["path"] = ""
            glyph = key["legend"]["glyph"]
            layout = key["legend"]["layout"]
            pattern = key["insert"]["pattern"]
            paste_key_style(key, style)
            key["legend"]["glyph"], key["legend"]["layout"] = glyph, layout
            key["insert"]["pattern"] = pattern
    else:
        apply_theme(deck, DEFAULT_THEME_ID, page_index=page_index)
    if template_id in KEYBOARD_TEMPLATE_IDS:
        _keep_keycap_legends(page["keys"])
    return deck


__all__ = [
    "ACTION_TYPES",
    "CASE_STYLES",
    "COMMANDS",
    "COMMAND_IDS",
    "CUSTOM_THEME_ID",
    "DECK_VERSION",
    "DEFAULT_TEMPLATE_ID",
    "DEFAULT_THEME_ID",
    "GRID_STEP",
    "HOLD_DELAY_MS",
    "INSERT_FITS",
    "INSERT_KINDS",
    "KEYBOARD_TEMPLATE_IDS",
    "KEY_MODES",
    "LED_MODES",
    "LEGEND_LAYOUTS",
    "LEGEND_WEIGHTS",
    "MATERIALS",
    "MAX_GRID_H",
    "MAX_GRID_W",
    "MAX_KEYS_PER_PAGE",
    "MAX_KEY_H",
    "MAX_KEY_W",
    "MAX_PAGES",
    "MIN_KEY_U",
    "MODIFIER_KEYS",
    "PAGE_TARGETS",
    "PANORAMA_FITS",
    "PANORAMA_ZOOM_RANGE",
    "PLAYBACK_MODES",
    "PROFILES",
    "SOUND_CHOICES",
    "STYLE_FIELDS",
    "SWITCHES",
    "TEMPLATES",
    "THEMES",
    "TOGGLE_INDICATORS",
    "DeckTheme",
    "apply_template_to_page",
    "apply_theme",
    "auto_glyph",
    "boxes_overlap",
    "build_template_deck",
    "clean_color",
    "combine_hotkey",
    "copy_key_style",
    "current_page",
    "deck_from_json",
    "deck_theme",
    "deck_to_json",
    "default_deck",
    "default_key",
    "default_panorama",
    "duplicate_key",
    "find_free_slot",
    "has_overlaps",
    "inherit_style",
    "key_box",
    "layout_bounds",
    "make_key",
    "migrate_v3",
    "modifier_name",
    "new_id",
    "new_page",
    "normalize_action",
    "normalize_deck",
    "normalize_key",
    "normalize_origin",
    "normalize_panorama",
    "option_ids",
    "option_label",
    "page_index_by_id",
    "panorama_align_for",
    "panorama_keys",
    "panorama_rect",
    "paste_key_style",
    "reflow_keys",
    "resolve_page_target",
    "settle_layout",
    "shade",
    "snap_u",
    "suggest_panorama_fit",
    "template_keys",
]
