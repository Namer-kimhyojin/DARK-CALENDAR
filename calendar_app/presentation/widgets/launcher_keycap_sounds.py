# -*- coding: utf-8 -*-
"""Bundled short UI sounds for launcher-deck key feedback."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from calendar_app.app_paths import get_resource_path


@dataclass(frozen=True, slots=True)
class KeycapSound:
    sound_id: str
    label_key: str
    label_default: str
    filename: str

    def path(self) -> Path:
        return Path(get_resource_path(f"Assets/keycaps/sounds/{self.filename}"))


KEYCAP_SOUNDS = (
    KeycapSound("soft_click", "widget.launcher.sound.soft_click", "소프트 클릭", "soft-click.wav"),
    KeycapSound(
        "crisp_click", "widget.launcher.sound.crisp_click", "크리스프 클릭", "crisp-click.wav"
    ),
    KeycapSound("mechanical", "widget.launcher.sound.mechanical", "메커니컬 키", "mechanical.wav"),
    KeycapSound("pop", "widget.launcher.sound.pop", "라이트 팝", "pop.wav"),
    KeycapSound("glass", "widget.launcher.sound.glass", "글래스 탭", "glass.wav"),
    KeycapSound("toggle_on", "widget.launcher.sound.toggle_on", "토글 켜짐", "toggle-on.wav"),
    KeycapSound("toggle_off", "widget.launcher.sound.toggle_off", "토글 꺼짐", "toggle-off.wav"),
    KeycapSound("success", "widget.launcher.sound.success", "성공 차임", "success.wav"),
    KeycapSound("error", "widget.launcher.sound.error", "오류 알림", "error.wav"),
    KeycapSound("whoosh", "widget.launcher.sound.whoosh", "소프트 우시", "whoosh.wav"),
    KeycapSound("chime", "widget.launcher.sound.chime", "에어 차임", "chime.wav"),
    KeycapSound("pulse", "widget.launcher.sound.pulse", "디지털 펄스", "pulse.wav"),
    KeycapSound("wood_tap", "widget.launcher.sound.wood_tap", "우드 탭", "wood-tap.wav"),
    KeycapSound("bamboo", "widget.launcher.sound.bamboo", "뱀부 톡", "bamboo.wav"),
    KeycapSound("deep_thock", "widget.launcher.sound.deep_thock", "로우 톡", "deep-thock.wav"),
    KeycapSound("felt_key", "widget.launcher.sound.felt_key", "펠트 키", "felt-key.wav"),
    KeycapSound("typewriter", "widget.launcher.sound.typewriter", "타자기", "typewriter.wav"),
    KeycapSound("ceramic", "widget.launcher.sound.ceramic", "세라믹 탭", "ceramic.wav"),
    KeycapSound("marimba", "widget.launcher.sound.marimba", "마림바", "marimba.wav"),
    KeycapSound("water_drop", "widget.launcher.sound.water_drop", "워터 드롭", "water-drop.wav"),
    KeycapSound(
        "digital_blip", "widget.launcher.sound.digital_blip", "디지털 블립", "digital-blip.wav"
    ),
    KeycapSound("retro_beep", "widget.launcher.sound.retro_beep", "레트로 삡", "retro-beep.wav"),
    KeycapSound("warm_pluck", "widget.launcher.sound.warm_pluck", "웜 플럭", "warm-pluck.wav"),
    KeycapSound("double_tap", "widget.launcher.sound.double_tap", "더블 탭", "double-tap.wav"),
)
_SOUND_BY_ID = {sound.sound_id: sound for sound in KEYCAP_SOUNDS}


def keycap_sound(sound_id: object) -> KeycapSound | None:
    return _SOUND_BY_ID.get(str(sound_id or ""))


def keycap_sound_ids() -> set[str]:
    return set(_SOUND_BY_ID)


__all__ = ["KEYCAP_SOUNDS", "KeycapSound", "keycap_sound", "keycap_sound_ids"]
