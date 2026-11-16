# -*- coding: utf-8 -*-
"""Desktop lock ("바탕화면 고정"): the two lock types, the status badge text and the intro.

- Layout lock ("배치 고정"): windows, panels and widgets cannot be moved, resized
  or docked, but the calendar stays usable (check tasks, open details, select).
  The top bar stays.
- Full lock ("완전 고정"): view only, like a wallpaper. Input is blocked and,
  with the tray options, clicks pass through to the desktop or the calendar sits
  behind the desktop icons. This is the behaviour the lock had before the split.

A badge in the bottom-right corner shows the lock in both types and unlocks it.
The first lock of each type explains once how to release it.
"""

from __future__ import annotations

from calendar_app.infrastructure.i18n import t

LOCK_KIND_KEY = "lock_kind"
KIND_LAYOUT = "layout"
KIND_FULL = "full"
_INTRO_KEY = "lock_intro_shown_{kind}"


def lock_kind(settings) -> str:
    """The chosen lock type; full lock unless the user picked layout lock."""
    try:
        value = str(settings.value(LOCK_KIND_KEY, KIND_FULL) or KIND_FULL)
    except Exception:
        return KIND_FULL
    return KIND_LAYOUT if value == KIND_LAYOUT else KIND_FULL


def full_lock_active(window) -> bool:
    return bool(getattr(window, "is_locked", False)) and (
        lock_kind(getattr(window, "settings", None)) == KIND_FULL
    )


def badge_text(kind: str, state: str = "idle") -> str:
    """Text of the corner badge: what is locked, or how to release it."""
    if state == "ready":
        return t("lock.overlay_unlock_ready", "클릭하면 고정 해제")
    if kind == KIND_LAYOUT:
        return t("lock.badge_layout", "배치 고정 중")
    return t("lock.badge_full", "바탕화면 고정 중")


def badge_tooltip(kind: str, click_through: bool) -> str:
    if kind == KIND_LAYOUT:
        return t(
            "lock.badge_layout_hint",
            "클릭하면 배치 고정을 해제합니다. (Ctrl+Shift+L)",
        )
    if click_through:
        return t(
            "lock.badge_full_hover_hint",
            "마우스를 잠시 올려 두면 누를 수 있습니다. 누르면 고정을 해제합니다. (Ctrl+Shift+L)",
        )
    return t("lock.overlay_unlock_hint", "바탕화면 고정을 해제합니다. (Ctrl+Shift+L)")


def intro_message(kind: str, click_through: bool) -> str:
    if kind == KIND_LAYOUT:
        return t(
            "lock.intro_layout",
            "창·패널·위젯의 위치와 크기가 고정됩니다. 일정은 그대로 쓸 수 있고, "
            "오른쪽 아래 배지나 Ctrl+Shift+L로 해제합니다.",
        )
    if click_through:
        return t(
            "lock.intro_full",
            "클릭은 달력 아래 바탕화면으로 전달됩니다. 오른쪽 아래 배지에 마우스를 잠시 "
            "올려 두면 해제할 수 있고, 트레이 메뉴나 Ctrl+Shift+L로도 해제됩니다.",
        )
    return t(
        "lock.intro_full_blocking",
        "달력이 입력을 막습니다. 오른쪽 아래 배지를 누르거나 트레이 메뉴, Ctrl+Shift+L로 해제합니다.",
    )


def show_intro_once(window, kind: str, click_through: bool) -> bool:
    """Explain how to release the lock the first time each type is used."""
    settings = getattr(window, "settings", None)
    show_toast = getattr(window, "show_toast", None)
    if settings is None or not callable(show_toast):
        return False
    key = _INTRO_KEY.format(kind=kind)
    try:
        if str(settings.value(key, "false")).lower() == "true":
            return False
        settings.setValue(key, "true")
    except Exception:
        return False
    title = (
        t("lock.kind_layout_title", "배치 고정")
        if kind == KIND_LAYOUT
        else t("lock.kind_full_title", "바탕화면 고정")
    )
    show_toast(title, intro_message(kind, click_through))
    return True
