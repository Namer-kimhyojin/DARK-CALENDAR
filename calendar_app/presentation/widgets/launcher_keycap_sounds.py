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
)
_SOUND_BY_ID = {sound.sound_id: sound for sound in KEYCAP_SOUNDS}


def keycap_sound(sound_id: object) -> KeycapSound | None:
    return _SOUND_BY_ID.get(str(sound_id or ""))


def keycap_sound_ids() -> set[str]:
    return set(_SOUND_BY_ID)


__all__ = ["KEYCAP_SOUNDS", "KeycapSound", "keycap_sound", "keycap_sound_ids"]
