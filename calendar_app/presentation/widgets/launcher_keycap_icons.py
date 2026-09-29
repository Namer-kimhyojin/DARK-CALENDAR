# -*- coding: utf-8 -*-
"""Searchable vector icon registry for launcher-deck keycaps."""

from __future__ import annotations

from dataclasses import dataclass

from calendar_app.shared.icon_map import ICON


@dataclass(frozen=True, slots=True)
class KeycapIconAsset:
    icon_id: str
    label_key: str
    label_default: str
    icon_key: str


@dataclass(frozen=True, slots=True)
class KeycapIconPack:
    pack_id: str
    label_key: str
    label_default: str
    color: str


KEYCAP_ICON_PACKS = (
    KeycapIconPack("glass_line", "widget.launcher.icon_pack.glass", "Glass Line", "#f7fbffff"),
    KeycapIconPack("neon_cyan", "widget.launcher.icon_pack.neon", "Neon Cyan", "#55efffff"),
    KeycapIconPack("violet_glow", "widget.launcher.icon_pack.violet", "Violet Glow", "#e1c4ffff"),
    KeycapIconPack("warm_sunset", "widget.launcher.icon_pack.sunset", "Warm Sunset", "#ffe0b2ff"),
    KeycapIconPack("mono_ink", "widget.launcher.icon_pack.ink", "Mono Ink", "#172033ff"),
)
_PACK_BY_ID = {pack.pack_id: pack for pack in KEYCAP_ICON_PACKS}
DEFAULT_KEYCAP_ICON_PACK_ID = "glass_line"


KEYCAP_ICON_ASSETS = (
    KeycapIconAsset("auto", "widget.launcher.icon.auto", "동작에 맞게 자동", ""),
    KeycapIconAsset("none", "widget.launcher.icon.none", "아이콘 없음", ""),
    KeycapIconAsset("star", "widget.launcher.icon.star", "별", ICON.STAR),
    KeycapIconAsset("bolt", "widget.launcher.icon.bolt", "번개", ICON.PRIORITY_URGENT),
    KeycapIconAsset("play", "widget.launcher.icon.play", "실행", ICON.PLAY),
    KeycapIconAsset("folder", "widget.launcher.icon.folder", "폴더", ICON.FOLDER),
    KeycapIconAsset("globe", "widget.launcher.icon.globe", "웹", ICON.GLOBE),
    KeycapIconAsset("calendar", "widget.launcher.icon.calendar", "캘린더", ICON.CALENDAR),
    KeycapIconAsset("plus", "widget.launcher.icon.plus", "추가", ICON.ADD),
    KeycapIconAsset("search", "widget.launcher.icon.search", "검색", ICON.SEARCH),
    KeycapIconAsset("sync", "widget.launcher.icon.sync", "동기화", ICON.SYNC),
    KeycapIconAsset("check", "widget.launcher.icon.check", "완료", ICON.CHECK),
    KeycapIconAsset("close", "widget.launcher.icon.close", "닫기", ICON.CLOSE),
    KeycapIconAsset("warning", "widget.launcher.icon.warning", "경고", ICON.WARNING),
    KeycapIconAsset("info", "widget.launcher.icon.info", "정보", ICON.INFO),
    KeycapIconAsset("settings", "widget.launcher.icon.settings", "설정", ICON.SETTINGS),
    KeycapIconAsset("save", "widget.launcher.icon.save", "저장", ICON.SAVE),
    KeycapIconAsset("edit", "widget.launcher.icon.edit", "편집", ICON.EDIT),
    KeycapIconAsset("delete", "widget.launcher.icon.delete", "삭제", ICON.DELETE),
    KeycapIconAsset("lock", "widget.launcher.icon.lock", "잠금", ICON.LOCK),
    KeycapIconAsset("unlock", "widget.launcher.icon.unlock", "잠금 해제", ICON.UNLOCK),
    KeycapIconAsset("cloud", "widget.launcher.icon.cloud", "클라우드", ICON.CLOUD),
    KeycapIconAsset("link", "widget.launcher.icon.link", "링크", ICON.LINK),
    KeycapIconAsset("alarm", "widget.launcher.icon.alarm", "알람", ICON.ALARM),
    KeycapIconAsset("memo", "widget.launcher.icon.memo", "메모", ICON.MEMO),
    KeycapIconAsset("timer", "widget.launcher.icon.timer", "타이머", ICON.POMODORO),
    KeycapIconAsset("pause", "widget.launcher.icon.pause", "일시정지", ICON.PAUSE),
    KeycapIconAsset("forward", "widget.launcher.icon.forward", "다음", ICON.FORWARD),
    KeycapIconAsset("broadcast", "widget.launcher.icon.broadcast", "방송", ICON.BROADCAST),
    KeycapIconAsset("repeat", "widget.launcher.icon.repeat", "반복", ICON.REPEAT),
    KeycapIconAsset("filter", "widget.launcher.icon.filter", "필터", ICON.FILTER),
    KeycapIconAsset("palette", "widget.launcher.icon.palette", "팔레트", ICON.DISPLAY_STYLE),
    KeycapIconAsset("focus", "widget.launcher.icon.focus", "집중", ICON.FOCUS_DONE),
    KeycapIconAsset("coffee", "widget.launcher.icon.coffee", "휴식", ICON.BREAK_SHORT),
    KeycapIconAsset("rocket", "widget.launcher.icon.rocket", "빠른 실행", ICON.AUTOSTART),
)
_ICON_BY_ID = {asset.icon_id: asset for asset in KEYCAP_ICON_ASSETS}


def keycap_icon_asset(icon_id: object) -> KeycapIconAsset:
    return _ICON_BY_ID.get(str(icon_id or "auto"), _ICON_BY_ID["auto"])


def keycap_icon_ids() -> set[str]:
    return set(_ICON_BY_ID)


def keycap_icon_pack(pack_id: object) -> KeycapIconPack:
    return _PACK_BY_ID.get(
        str(pack_id or DEFAULT_KEYCAP_ICON_PACK_ID),
        _PACK_BY_ID[DEFAULT_KEYCAP_ICON_PACK_ID],
    )


def keycap_icon_pack_ids() -> set[str]:
    return set(_PACK_BY_ID)


__all__ = [
    "DEFAULT_KEYCAP_ICON_PACK_ID",
    "KEYCAP_ICON_ASSETS",
    "KEYCAP_ICON_PACKS",
    "KeycapIconAsset",
    "KeycapIconPack",
    "keycap_icon_asset",
    "keycap_icon_ids",
    "keycap_icon_pack",
    "keycap_icon_pack_ids",
]
