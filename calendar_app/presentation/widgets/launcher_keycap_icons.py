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
    # 아래 항목은 ICON 매핑 대신 qtawesome 이름을 직접 사용한다 (KeyDeck 전용 글리프).
    KeycapIconAsset("arrow_up", "widget.launcher.icon.arrow_up", "위쪽", "mdi6.arrow-up-bold"),
    KeycapIconAsset(
        "arrow_down", "widget.launcher.icon.arrow_down", "아래쪽", "mdi6.arrow-down-bold"
    ),
    KeycapIconAsset(
        "arrow_left", "widget.launcher.icon.arrow_left", "왼쪽", "mdi6.arrow-left-bold"
    ),
    KeycapIconAsset(
        "arrow_right", "widget.launcher.icon.arrow_right", "오른쪽", "mdi6.arrow-right-bold"
    ),
    KeycapIconAsset("copy", "widget.launcher.icon.copy", "복사", "mdi6.content-copy"),
    KeycapIconAsset("paste", "widget.launcher.icon.paste", "붙여넣기", "mdi6.content-paste"),
    KeycapIconAsset("cut", "widget.launcher.icon.cut", "잘라내기", "mdi6.content-cut"),
    KeycapIconAsset("undo", "widget.launcher.icon.undo", "실행 취소", "mdi6.undo"),
    KeycapIconAsset("redo", "widget.launcher.icon.redo", "다시 실행", "mdi6.redo"),
    KeycapIconAsset("music", "widget.launcher.icon.music", "음악", "mdi6.music"),
    KeycapIconAsset(
        "play_pause", "widget.launcher.icon.play_pause", "재생/일시정지", "mdi6.play-pause"
    ),
    KeycapIconAsset("next_track", "widget.launcher.icon.next_track", "다음 곡", "mdi6.skip-next"),
    KeycapIconAsset(
        "prev_track", "widget.launcher.icon.prev_track", "이전 곡", "mdi6.skip-previous"
    ),
    KeycapIconAsset("volume_up", "widget.launcher.icon.volume_up", "볼륨 크게", "mdi6.volume-high"),
    KeycapIconAsset("volume_mute", "widget.launcher.icon.volume_mute", "음소거", "mdi6.volume-off"),
    KeycapIconAsset("mic", "widget.launcher.icon.mic", "마이크", "mdi6.microphone"),
    KeycapIconAsset(
        "mic_off", "widget.launcher.icon.mic_off", "마이크 끄기", "mdi6.microphone-off"
    ),
    KeycapIconAsset("camera", "widget.launcher.icon.camera", "카메라", "mdi6.camera-outline"),
    KeycapIconAsset("video", "widget.launcher.icon.video", "영상", "mdi6.video-outline"),
    KeycapIconAsset("mail", "widget.launcher.icon.mail", "메일", "mdi6.email-outline"),
    KeycapIconAsset("chat", "widget.launcher.icon.chat", "채팅", "mdi6.chat-outline"),
    KeycapIconAsset("phone", "widget.launcher.icon.phone", "전화", "mdi6.phone-outline"),
    KeycapIconAsset("code", "widget.launcher.icon.code", "코드", "mdi6.code-braces"),
    KeycapIconAsset("terminal", "widget.launcher.icon.terminal", "터미널", "mdi6.console"),
    KeycapIconAsset("image", "widget.launcher.icon.image", "이미지", "mdi6.image-outline"),
    KeycapIconAsset("chart", "widget.launcher.icon.chart", "차트", "mdi6.chart-line"),
    KeycapIconAsset("home", "widget.launcher.icon.home", "홈", "mdi6.home-outline"),
    KeycapIconAsset("user", "widget.launcher.icon.user", "사용자", "mdi6.account-outline"),
    KeycapIconAsset("keyboard", "widget.launcher.icon.keyboard", "키보드", "mdi6.keyboard-outline"),
    KeycapIconAsset("monitor", "widget.launcher.icon.monitor", "모니터", "mdi6.monitor"),
    KeycapIconAsset(
        "document", "widget.launcher.icon.document", "문서", "mdi6.file-document-outline"
    ),
    KeycapIconAsset(
        "spreadsheet", "widget.launcher.icon.spreadsheet", "스프레드시트", "mdi6.file-excel-outline"
    ),
    KeycapIconAsset(
        "slides", "widget.launcher.icon.slides", "프레젠테이션", "mdi6.file-powerpoint-outline"
    ),
    KeycapIconAsset(
        "calculator", "widget.launcher.icon.calculator", "계산기", "mdi6.calculator-variant-outline"
    ),
    KeycapIconAsset("notebook", "widget.launcher.icon.notebook", "노트", "mdi6.notebook-outline"),
    KeycapIconAsset("idea", "widget.launcher.icon.idea", "아이디어", "mdi6.lightbulb-outline"),
    KeycapIconAsset("heart", "widget.launcher.icon.heart", "하트", "mdi6.heart-outline"),
    KeycapIconAsset("fire", "widget.launcher.icon.fire", "불꽃", "mdi6.fire"),
    KeycapIconAsset("game", "widget.launcher.icon.game", "게임", "mdi6.gamepad-variant-outline"),
    KeycapIconAsset("headphones", "widget.launcher.icon.headphones", "헤드폰", "mdi6.headphones"),
    KeycapIconAsset("power", "widget.launcher.icon.power", "전원", "mdi6.power"),
    KeycapIconAsset("night", "widget.launcher.icon.night", "야간", "mdi6.weather-night"),
    KeycapIconAsset("brightness", "widget.launcher.icon.brightness", "밝기", "mdi6.brightness-6"),
    KeycapIconAsset(
        "clipboard", "widget.launcher.icon.clipboard", "클립보드", "mdi6.clipboard-text-outline"
    ),
    KeycapIconAsset("translate", "widget.launcher.icon.translate", "번역", "mdi6.translate"),
    KeycapIconAsset("printer", "widget.launcher.icon.printer", "프린터", "mdi6.printer-outline"),
    KeycapIconAsset("map", "widget.launcher.icon.map", "지도", "mdi6.map-marker-outline"),
    KeycapIconAsset("cart", "widget.launcher.icon.cart", "쇼핑", "mdi6.cart-outline"),
    KeycapIconAsset("bookmark", "widget.launcher.icon.bookmark", "북마크", "mdi6.bookmark-outline"),
    KeycapIconAsset("brush", "widget.launcher.icon.brush", "브러시", "mdi6.brush-outline"),
    KeycapIconAsset(
        "dashboard", "widget.launcher.icon.dashboard", "대시보드", "mdi6.view-dashboard-outline"
    ),
    KeycapIconAsset("layers", "widget.launcher.icon.layers", "레이어", "mdi6.layers-outline"),
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
