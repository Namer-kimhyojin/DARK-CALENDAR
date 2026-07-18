# -*- coding: utf-8 -*-
"""Extensible skin registry for widget-only mode.

Skins are presentation presets: they select a light/dark foundation and then
override semantic widget tokens. Registering a skin here is enough for every
widget-mode skin menu to discover it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
import json
import logging
from pathlib import Path
import re
from types import MappingProxyType
from uuid import uuid4

from calendar_app.app_paths import get_app_data_dir

logger = logging.getLogger(__name__)

WIDGET_MODE_SKIN_SETTING_KEY = "widget_mode_skin"
WIDGET_MODE_LAYOUT_SETTING_KEY = "widget_mode_layout"
DEFAULT_WIDGET_MODE_SKIN_ID = "classic_light"
DEFAULT_WIDGET_MODE_LAYOUT_ID = "stacked"


@dataclass(frozen=True, slots=True)
class WidgetModeLayout:
    layout_id: str
    label_key: str
    label_default: str
    placements: tuple[tuple[str, int, int, int, int], ...]
    preferred_size: tuple[int, int] = (360, 560)
    row_stretches: tuple[tuple[int, int], ...] = ()
    column_stretches: tuple[tuple[int, int], ...] = ()
    spacing: int = 14
    content_margins: tuple[int, int, int, int] = (18, 18, 18, 18)
    hero_margins: tuple[int, int, int, int] = (16, 16, 16, 16)
    hero_spacing: int = 12
    calendar_cell_size: tuple[int, int] = (42, 54)
    calendar_spacing: int = 6
    calendar_margins: tuple[int, int, int, int] = (0, 0, 0, 0)
    filter_margins: tuple[int, int, int, int] = (0, 0, 0, 0)
    filter_spacing: int = 6
    agenda_margins: tuple[int, int, int, int] = (0, 0, 0, 0)
    agenda_spacing: int = 8
    show_eyebrow: bool = True
    show_hint: bool = True

    def __post_init__(self) -> None:
        normalized_id = str(self.layout_id or "").strip().lower()
        if not normalized_id or not normalized_id.replace("_", "").isalnum():
            raise ValueError("layout_id must contain only letters, numbers, and underscores")
        valid_sections = {"hero", "calendar", "filters", "agenda"}
        seen: set[str] = set()
        for section, row, column, row_span, column_span in self.placements:
            if section not in valid_sections or section in seen:
                raise ValueError(f"invalid or duplicated layout section: {section}")
            if min(row, column) < 0 or min(row_span, column_span) < 1:
                raise ValueError("layout grid coordinates and spans must be positive")
            seen.add(section)
        if "hero" not in seen or "agenda" not in seen:
            raise ValueError("widget-mode layouts must contain hero and agenda sections")
        width, height = self.preferred_size
        if width < 300 or height < 360:
            raise ValueError("preferred_size is too small for widget mode")
        object.__setattr__(self, "layout_id", normalized_id)
        object.__setattr__(self, "placements", tuple(tuple(item) for item in self.placements))
        object.__setattr__(self, "preferred_size", (int(width), int(height)))
        for field_name in ("row_stretches", "column_stretches"):
            object.__setattr__(
                self, field_name, tuple(tuple(item) for item in getattr(self, field_name))
            )
        for field_name in (
            "content_margins",
            "hero_margins",
            "calendar_cell_size",
            "calendar_margins",
            "filter_margins",
            "agenda_margins",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))


@dataclass(frozen=True, slots=True)
class WidgetModeSkin:
    skin_id: str
    label_key: str
    label_default: str
    base_theme: str = "light"
    legacy_layout_id: str = DEFAULT_WIDGET_MODE_LAYOUT_ID
    token_overrides: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized_id = str(self.skin_id or "").strip().lower()
        if not normalized_id or not normalized_id.replace("_", "").isalnum():
            raise ValueError("skin_id must contain only letters, numbers, and underscores")
        normalized_theme = str(self.base_theme or "light").strip().lower()
        if normalized_theme not in {"light", "dark"}:
            raise ValueError("base_theme must be 'light' or 'dark'")
        object.__setattr__(self, "skin_id", normalized_id)
        object.__setattr__(self, "base_theme", normalized_theme)
        object.__setattr__(
            self,
            "legacy_layout_id",
            str(self.legacy_layout_id or "stacked").strip().lower(),
        )
        object.__setattr__(self, "token_overrides", MappingProxyType(dict(self.token_overrides)))


_SKINS: dict[str, WidgetModeSkin] = {}
_LAYOUTS: dict[str, WidgetModeLayout] = {}
USER_STYLES_PATH = get_app_data_dir() / "widget_mode_styles.json"
_CSS_COLOR_RE = re.compile(r"^(#[0-9a-fA-F]{6}|rgba?\([0-9., ]+\))$")


def register_widget_mode_layout(layout: WidgetModeLayout, *, replace: bool = False) -> None:
    if not isinstance(layout, WidgetModeLayout):
        raise TypeError("layout must be a WidgetModeLayout")
    if layout.layout_id in _LAYOUTS and not replace:
        raise ValueError(f"widget-mode layout already registered: {layout.layout_id}")
    _LAYOUTS[layout.layout_id] = layout


def widget_mode_layouts() -> tuple[WidgetModeLayout, ...]:
    return tuple(_LAYOUTS.values())


def get_widget_mode_layout(layout_id: object) -> WidgetModeLayout:
    normalized = str(layout_id or "").strip().lower()
    return _LAYOUTS.get(normalized, _LAYOUTS[DEFAULT_WIDGET_MODE_LAYOUT_ID])


def register_widget_mode_skin(skin: WidgetModeSkin, *, replace: bool = False) -> None:
    """Register a skin for automatic discovery by widget-mode UIs."""
    if not isinstance(skin, WidgetModeSkin):
        raise TypeError("skin must be a WidgetModeSkin")
    if skin.legacy_layout_id not in _LAYOUTS:
        raise ValueError(f"unknown legacy widget-mode layout: {skin.legacy_layout_id}")
    if skin.skin_id in _SKINS and not replace:
        raise ValueError(f"widget-mode skin already registered: {skin.skin_id}")
    _SKINS[skin.skin_id] = skin


def widget_mode_skins() -> tuple[WidgetModeSkin, ...]:
    return tuple(_SKINS.values())


def get_widget_mode_skin(skin_id: object) -> WidgetModeSkin:
    normalized = str(skin_id or "").strip().lower()
    return _SKINS.get(normalized, _SKINS[DEFAULT_WIDGET_MODE_SKIN_ID])


def read_widget_mode_skin_id(settings) -> str:
    """Read the selected skin, falling back to the legacy light/dark setting."""
    raw = settings.value(WIDGET_MODE_SKIN_SETTING_KEY, None) if settings is not None else None
    normalized = str(raw or "").strip().lower()
    if normalized in _SKINS:
        return normalized

    legacy = (
        str(settings.value("widget_mode_panel_theme", "light") or "light").strip().lower()
        if settings is not None
        else "light"
    )
    return "classic_dark" if legacy == "dark" else DEFAULT_WIDGET_MODE_SKIN_ID


def write_widget_mode_skin_id(settings, skin_id: object) -> str:
    skin = get_widget_mode_skin(skin_id)
    if settings is not None:
        if settings.value(WIDGET_MODE_LAYOUT_SETTING_KEY, None) in (None, ""):
            settings.setValue(WIDGET_MODE_LAYOUT_SETTING_KEY, read_widget_mode_layout_id(settings))
        settings.setValue(WIDGET_MODE_SKIN_SETTING_KEY, skin.skin_id)
        # Keep old code and older app versions visually compatible.
        settings.setValue("widget_mode_panel_theme", skin.base_theme)
    return skin.skin_id


def read_widget_mode_layout_id(settings) -> str:
    raw = settings.value(WIDGET_MODE_LAYOUT_SETTING_KEY, None) if settings is not None else None
    normalized = str(raw or "").strip().lower()
    if normalized in _LAYOUTS:
        return normalized
    skin = get_widget_mode_skin(read_widget_mode_skin_id(settings))
    return (
        skin.legacy_layout_id
        if skin.legacy_layout_id in _LAYOUTS
        else DEFAULT_WIDGET_MODE_LAYOUT_ID
    )


def write_widget_mode_layout_id(settings, layout_id: object) -> str:
    layout = get_widget_mode_layout(layout_id)
    if settings is not None:
        settings.setValue(WIDGET_MODE_LAYOUT_SETTING_KEY, layout.layout_id)
    return layout.layout_id


def apply_widget_mode_skin(tokens: Mapping[str, str], skin_id: object) -> dict[str, str]:
    updated = dict(tokens)
    updated.update(get_widget_mode_skin(skin_id).token_overrides)
    return updated


def _read_user_style_document(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"version": 1, "skins": [], "layouts": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        logger.exception("Failed to read widget-mode user styles: %s", path)
        return {"version": 1, "skins": [], "layouts": []}
    if not isinstance(payload, dict):
        return {"version": 1, "skins": [], "layouts": []}
    return payload


def _write_user_style_document(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
        errors="strict",
    )


def load_user_widget_styles(path: Path | None = None) -> tuple[int, int]:
    document = _read_user_style_document(path or USER_STYLES_PATH)
    loaded_layouts = 0
    loaded_skins = 0
    for raw in document.get("layouts", []):
        if not isinstance(raw, dict):
            continue
        try:
            layout = WidgetModeLayout(**raw)
            register_widget_mode_layout(layout, replace=True)
            loaded_layouts += 1
        except (TypeError, ValueError):
            logger.warning("Ignoring invalid user widget layout", exc_info=True)
    for raw in document.get("skins", []):
        if not isinstance(raw, dict):
            continue
        try:
            overrides = raw.get("token_overrides", {})
            if not isinstance(overrides, dict) or any(
                not _CSS_COLOR_RE.fullmatch(str(value).strip()) for value in overrides.values()
            ):
                raise ValueError("skin token overrides must be CSS colors")
            skin = WidgetModeSkin(**raw)
            register_widget_mode_skin(skin, replace=True)
            loaded_skins += 1
        except (TypeError, ValueError):
            logger.warning("Ignoring invalid user widget skin", exc_info=True)
    return loaded_skins, loaded_layouts


def create_user_widget_skin(
    name: str,
    *,
    base_theme: str,
    accent: str,
    path: Path | None = None,
) -> WidgetModeSkin:
    label = str(name or "").strip()
    color = str(accent or "").strip()
    if not label:
        raise ValueError("skin name is required")
    if not _CSS_COLOR_RE.fullmatch(color):
        raise ValueError("accent must be a CSS color")
    skin_id = f"user_skin_{uuid4().hex[:12]}"
    skin = WidgetModeSkin(
        skin_id,
        f"widget_mode.{skin_id}",
        label,
        base_theme=base_theme,
        token_overrides={"accent": color, "accent_deep": color},
    )
    target = path or USER_STYLES_PATH
    document = _read_user_style_document(target)
    skins = list(document.get("skins", []))
    skins.append(
        {
            "skin_id": skin.skin_id,
            "label_key": skin.label_key,
            "label_default": skin.label_default,
            "base_theme": skin.base_theme,
            "legacy_layout_id": skin.legacy_layout_id,
            "token_overrides": dict(skin.token_overrides),
        }
    )
    document.update({"version": 1, "skins": skins})
    _write_user_style_document(target, document)
    register_widget_mode_skin(skin)
    return skin


def create_user_widget_layout(
    name: str,
    *,
    template_id: str,
    preferred_size: tuple[int, int],
    show_eyebrow: bool,
    show_hint: bool,
    path: Path | None = None,
) -> WidgetModeLayout:
    label = str(name or "").strip()
    if not label:
        raise ValueError("layout name is required")
    layout_id = f"user_layout_{uuid4().hex[:12]}"
    layout = replace(
        get_widget_mode_layout(template_id),
        layout_id=layout_id,
        label_key=f"widget_mode.{layout_id}",
        label_default=label,
        preferred_size=(int(preferred_size[0]), int(preferred_size[1])),
        show_eyebrow=bool(show_eyebrow),
        show_hint=bool(show_hint),
    )
    target = path or USER_STYLES_PATH
    document = _read_user_style_document(target)
    layouts = list(document.get("layouts", []))
    layouts.append(asdict(layout))
    document.update({"version": 1, "layouts": layouts})
    _write_user_style_document(target, document)
    register_widget_mode_layout(layout)
    return layout


def _register_builtin_layouts() -> None:
    layouts = (
        WidgetModeLayout(
            "stacked",
            "widget_mode.layout_stacked",
            "세로 집중형",
            placements=(
                ("hero", 0, 0, 1, 1),
                ("calendar", 1, 0, 1, 1),
                ("filters", 2, 0, 1, 1),
                ("agenda", 3, 0, 1, 1),
            ),
            row_stretches=((3, 1),),
        ),
        WidgetModeLayout(
            "dashboard",
            "widget_mode.layout_dashboard",
            "좌우 대시보드형",
            placements=(
                ("hero", 0, 0, 1, 2),
                ("calendar", 1, 0, 1, 1),
                ("filters", 2, 0, 1, 1),
                ("agenda", 1, 1, 2, 1),
            ),
            preferred_size=(720, 520),
            row_stretches=((1, 1),),
            column_stretches=((0, 1), (1, 1)),
            hero_margins=(18, 14, 18, 14),
            hero_spacing=9,
            calendar_cell_size=(38, 50),
            calendar_spacing=5,
            calendar_margins=(12, 12, 12, 12),
            filter_margins=(10, 8, 10, 8),
            agenda_margins=(16, 14, 16, 14),
            agenda_spacing=10,
        ),
        WidgetModeLayout(
            "agenda_first",
            "widget_mode.layout_agenda_first",
            "일정 우선형",
            placements=(
                ("hero", 0, 0, 1, 1),
                ("filters", 1, 0, 1, 1),
                ("agenda", 2, 0, 1, 1),
                ("calendar", 3, 0, 1, 1),
            ),
            preferred_size=(410, 650),
            row_stretches=((2, 1),),
            hero_margins=(14, 13, 14, 13),
            hero_spacing=9,
            calendar_cell_size=(42, 48),
            calendar_margins=(10, 10, 10, 10),
            agenda_margins=(10, 10, 10, 10),
        ),
        WidgetModeLayout(
            "magazine",
            "widget_mode.layout_magazine",
            "매거진 보드형",
            placements=(
                ("hero", 0, 0, 1, 2),
                ("agenda", 1, 0, 2, 1),
                ("calendar", 1, 1, 1, 1),
                ("filters", 2, 1, 1, 1),
            ),
            preferred_size=(740, 540),
            row_stretches=((1, 1),),
            column_stretches=((0, 3), (1, 2)),
            hero_margins=(18, 14, 18, 14),
            hero_spacing=9,
            calendar_cell_size=(40, 50),
            calendar_spacing=5,
            calendar_margins=(12, 12, 12, 12),
            filter_margins=(12, 9, 12, 9),
            agenda_margins=(16, 14, 16, 14),
            agenda_spacing=10,
        ),
        WidgetModeLayout(
            "minimal",
            "widget_mode.layout_minimal",
            "미니멀 리스트형",
            placements=(
                ("hero", 0, 0, 1, 1),
                ("filters", 1, 0, 1, 1),
                ("agenda", 2, 0, 1, 1),
            ),
            preferred_size=(350, 500),
            row_stretches=((2, 1),),
            spacing=10,
            content_margins=(14, 14, 14, 14),
            hero_margins=(14, 12, 14, 12),
            hero_spacing=7,
            filter_margins=(8, 6, 8, 6),
            filter_spacing=5,
            agenda_margins=(10, 9, 10, 9),
            agenda_spacing=6,
            show_eyebrow=False,
            show_hint=False,
        ),
    )
    for layout in layouts:
        register_widget_mode_layout(layout)


def _register_builtin_skins() -> None:
    builtins = (
        WidgetModeSkin(
            "classic_light",
            "widget_mode.skin_classic_light",
            "클래식 라이트",
        ),
        WidgetModeSkin(
            "classic_dark",
            "widget_mode.skin_classic_dark",
            "클래식 다크",
            base_theme="dark",
        ),
        WidgetModeSkin(
            "midnight_blue",
            "widget_mode.skin_midnight_blue",
            "미드나이트 블루",
            base_theme="dark",
            legacy_layout_id="dashboard",
            token_overrides={
                "accent": "#65a7ff",
                "accent_deep": "#9ac7ff",
                "panel_bg_start": "rgba(8, 18, 38, 248)",
                "panel_bg_mid": "rgba(12, 27, 54, 246)",
                "panel_bg_end": "rgba(17, 36, 66, 244)",
                "panel_bg": "rgba(9, 21, 43, 242)",
                "surface_bg": "rgba(14, 31, 57, 222)",
                "surface_alt": "rgba(20, 42, 73, 206)",
                "section_bg": "rgba(18, 39, 70, 190)",
                "section_bg_alt": "rgba(27, 54, 91, 226)",
                "card_bg": "rgba(17, 37, 66, 206)",
                "hero_bg": "rgba(101, 167, 255, 30)",
                "hero_bg_strong": "rgba(101, 167, 255, 58)",
                "hero_border": "rgba(101, 167, 255, 128)",
            },
        ),
        WidgetModeSkin(
            "forest_mist",
            "widget_mode.skin_forest_mist",
            "포레스트 미스트",
            base_theme="dark",
            legacy_layout_id="agenda_first",
            token_overrides={
                "accent": "#62d29f",
                "accent_deep": "#8ce4bb",
                "panel_bg_start": "rgba(9, 30, 27, 248)",
                "panel_bg_mid": "rgba(13, 42, 36, 244)",
                "panel_bg_end": "rgba(19, 50, 42, 242)",
                "panel_bg": "rgba(10, 32, 28, 242)",
                "surface_bg": "rgba(15, 45, 38, 218)",
                "surface_alt": "rgba(24, 58, 49, 202)",
                "section_bg": "rgba(18, 50, 42, 186)",
                "section_bg_alt": "rgba(29, 70, 58, 220)",
                "card_bg": "rgba(18, 48, 41, 200)",
                "hero_bg": "rgba(98, 210, 159, 28)",
                "hero_bg_strong": "rgba(98, 210, 159, 54)",
                "hero_border": "rgba(98, 210, 159, 120)",
            },
        ),
        WidgetModeSkin(
            "sunset_glow",
            "widget_mode.skin_sunset_glow",
            "선셋 글로우",
            legacy_layout_id="magazine",
            token_overrides={
                "accent": "#e46f51",
                "accent_deep": "#9d3f2c",
                "panel_bg_start": "rgba(255, 246, 235, 248)",
                "panel_bg_mid": "rgba(252, 235, 222, 244)",
                "panel_bg_end": "rgba(247, 224, 217, 246)",
                "panel_bg": "rgba(251, 237, 225, 242)",
                "surface_bg": "rgba(255, 249, 241, 226)",
                "surface_alt": "rgba(247, 227, 215, 208)",
                "section_bg": "rgba(255, 250, 244, 232)",
                "section_bg_alt": "rgba(247, 222, 207, 220)",
                "card_bg": "rgba(255, 252, 247, 238)",
                "text_primary": "#4e302c",
                "text_secondary": "#77554d",
                "text_faint": "#a1786e",
                "calendar_text": "#563833",
                "calendar_muted": "#9b746c",
                "card_text_primary": "#4e302c",
                "card_text_secondary": "#806058",
            },
        ),
        WidgetModeSkin(
            "lavender_dream",
            "widget_mode.skin_lavender_dream",
            "라벤더 드림",
            legacy_layout_id="minimal",
            token_overrides={
                "accent": "#8266cc",
                "accent_deep": "#574095",
                "panel_bg_start": "rgba(246, 243, 255, 248)",
                "panel_bg_mid": "rgba(236, 231, 250, 244)",
                "panel_bg_end": "rgba(229, 225, 247, 246)",
                "panel_bg": "rgba(238, 234, 250, 242)",
                "surface_bg": "rgba(250, 248, 255, 226)",
                "surface_alt": "rgba(231, 225, 247, 208)",
                "section_bg": "rgba(251, 249, 255, 232)",
                "section_bg_alt": "rgba(226, 217, 246, 220)",
                "card_bg": "rgba(252, 251, 255, 238)",
                "text_primary": "#39304f",
                "text_secondary": "#645a78",
                "text_faint": "#9187a4",
                "calendar_text": "#44385d",
                "calendar_muted": "#817792",
                "card_text_primary": "#39304f",
                "card_text_secondary": "#6d637f",
            },
        ),
    )
    for skin in builtins:
        register_widget_mode_skin(skin)


_register_builtin_layouts()
_register_builtin_skins()
load_user_widget_styles()


__all__ = [
    "DEFAULT_WIDGET_MODE_SKIN_ID",
    "DEFAULT_WIDGET_MODE_LAYOUT_ID",
    "WIDGET_MODE_SKIN_SETTING_KEY",
    "WIDGET_MODE_LAYOUT_SETTING_KEY",
    "WidgetModeSkin",
    "WidgetModeLayout",
    "apply_widget_mode_skin",
    "create_user_widget_layout",
    "create_user_widget_skin",
    "get_widget_mode_skin",
    "get_widget_mode_layout",
    "read_widget_mode_skin_id",
    "load_user_widget_styles",
    "read_widget_mode_layout_id",
    "register_widget_mode_skin",
    "register_widget_mode_layout",
    "widget_mode_layouts",
    "widget_mode_skins",
    "write_widget_mode_skin_id",
    "write_widget_mode_layout_id",
]
