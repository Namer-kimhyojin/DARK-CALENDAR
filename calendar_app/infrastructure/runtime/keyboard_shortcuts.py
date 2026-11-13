# -*- coding: utf-8 -*-
"""Single source of truth for global keyboard shortcuts."""

from __future__ import annotations

from collections.abc import Callable
import contextlib
import html
import logging
import re
import weakref

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QGuiApplication, QKeySequence, QShortcut, QWindow
from PyQt6.QtWidgets import QApplication, QDockWidget, QWidget

from calendar_app.infrastructure.runtime import win32_input
from calendar_app.infrastructure.runtime.menu_paths import SELECTED_ITEM_MENU_KEY, format_menu_path

logger = logging.getLogger(__name__)


SHORTCUTS: list[dict] = [
    {
        "id": "new_schedule",
        "key": "Ctrl+N",
        "group": "register",
        "label_ko": "새 일정 등록",
        "action": "open_task_dialog",
    },
    {
        "id": "new_routine",
        "key": "Ctrl+R",
        "group": "register",
        "label_ko": "루틴 등록",
        "action": "open_routine_add_dialog",
    },
    {
        "id": "new_directive",
        "key": "Ctrl+G",
        "group": "register",
        "label_ko": "지시사항 등록",
        "action": "open_directive_dialog",
    },
    {
        "id": "checklist",
        "key": "Ctrl+L",
        "group": "register",
        "label_ko": "체크리스트 관리",
        "action": "open_checklist_manager",
    },
    {
        "id": "today",
        "key": "Ctrl+T",
        "group": "navigate",
        "label_ko": "오늘로 이동",
        "action": "jump_to_today",
    },
    {
        "id": "prev_day",
        "key": "Ctrl+Left",
        "group": "navigate",
        "label_ko": "이전 날짜",
        "action": "prev_day",
    },
    {
        "id": "next_day",
        "key": "Ctrl+Right",
        "group": "navigate",
        "label_ko": "다음 날짜",
        "action": "next_day",
    },
    {
        "id": "command_palette",
        "key": "Ctrl+K",
        "group": "navigate",
        "label_ko": "커맨드 팔레트",
        "action": None,
    },
    {
        "id": "focus_mode",
        "key": "Ctrl+F",
        "group": "mode",
        "label_ko": "집중 모드 토글",
        "action": "toggle_focus_mode",
    },
    {
        "id": "focus_pause",
        "key": "Ctrl+Shift+P",
        "group": "mode",
        "label_ko": "집중 일시정지",
        "action": "toggle_focus_pause",
    },
    {
        "id": "lock_mode",
        "key": "Ctrl+Shift+L",
        "group": "mode",
        "label_ko": "잠금 모드",
        "action": None,
    },
    {
        "id": "magnet_mode",
        "key": "Ctrl+M",
        "group": "mode",
        "label_ko": "자석 모드",
        "action": "toggle_magnet_mode",
    },
    {
        "id": "away_lock",
        "key": "Ctrl+Alt+W",
        "group": "mode",
        "label_ko": "자리비움 잠금",
        "action": None,
    },
    {
        "id": "topbar",
        "key": "Ctrl+Shift+B",
        "group": "view",
        "label_ko": "상단 바 자동 숨기기",
        "action": "toggle_top_bar",
    },
    {
        "id": "navigation_rail",
        "key": "Ctrl+Shift+R",
        "group": "view",
        "label_ko": "빠른 이동 표시",
        "action": "toggle_navigation_rail",
    },
    {
        "id": "cal_toolbar",
        "key": "Ctrl+Shift+T",
        "group": "view",
        "label_ko": "캘린더 툴바 토글",
        "action": "toggle_calendar_toolbar",
    },
    {
        "id": "fullscreen",
        "key": "F11",
        "group": "view",
        "label_ko": "전체화면 토글",
        "action": "toggle_fullscreen",
    },
    {
        "id": "save_layout",
        "key": "Ctrl+Shift+S",
        "group": "view",
        "label_ko": "현재 레이아웃 저장",
        "action": None,
    },
    {
        "id": "layout_1",
        "key": "Ctrl+Shift+1",
        "group": "view",
        "label_ko": "레이아웃 프리셋 1",
        "action": None,
    },
    {
        "id": "layout_2",
        "key": "Ctrl+Shift+2",
        "group": "view",
        "label_ko": "레이아웃 프리셋 2",
        "action": None,
    },
    {
        "id": "layout_3",
        "key": "Ctrl+Shift+3",
        "group": "view",
        "label_ko": "레이아웃 프리셋 3",
        "action": None,
    },
    {
        "id": "layout_4",
        "key": "Ctrl+Shift+4",
        "group": "view",
        "label_ko": "레이아웃 프리셋 4",
        "action": None,
    },
    {
        "id": "layout_5",
        "key": "Ctrl+Shift+5",
        "group": "view",
        "label_ko": "레이아웃 프리셋 5",
        "action": None,
    },
    {
        "id": "calendar_print",
        "key": "Ctrl+P",
        "group": "system",
        "label_ko": "캘린더 인쇄",
        "action": "open_calendar_print_dialog",
    },
    {
        "id": "sync_gcal",
        "key": "F5",
        "group": "system",
        "label_ko": "모든 캘린더 동기화",
        "action": "sync_calendars",
    },
    {
        "id": "routine_mgr",
        "key": "Ctrl+Alt+R",
        "group": "admin",
        "label_ko": "루틴 관리자",
        "action": None,
    },
    {
        "id": "color_assign",
        "key": "Ctrl+Alt+C",
        "group": "admin",
        "label_ko": "색상 자동 지정",
        "action": "auto_assign_color_tags_to_selection",
    },
    {
        "id": "show_hide",
        # System-wide hotkey; Ctrl+F1 would take Office's ribbon toggle away.
        "key": "Ctrl+Alt+Shift+F1",
        "group": "window",
        "label_ko": "창 표시/숨기기",
        "action": "toggle_overlay",
    },
    {
        "id": "widget_mode",
        "key": "F12",
        "group": "window",
        "label_ko": "위젯 모드 전환",
        "action": "toggle_widget_mode_panel",
    },
    {
        "id": "restore_pos",
        "key": "Ctrl+0",
        "group": "window",
        "label_ko": "창 위치 복원",
        "action": "restore_window_to_safe_area",
    },
    {
        "id": "opacity_up",
        "key": "Ctrl+=",
        "group": "window",
        "label_ko": "불투명도 증가",
        "action": None,
    },
    {
        "id": "opacity_down",
        "key": "Ctrl+-",
        "group": "window",
        "label_ko": "불투명도 감소",
        "action": None,
    },
    {
        "id": "monitor_left",
        "key": "Ctrl+Alt+Shift+Left",
        "group": "window",
        "label_ko": "이전 모니터로 이동",
        "action": "move_to_previous_monitor",
    },
    {
        "id": "monitor_right",
        "key": "Ctrl+Alt+Shift+Right",
        "group": "window",
        "label_ko": "다음 모니터로 이동",
        "action": "move_to_next_monitor",
    },
    {
        "id": "help",
        "key": "F1",
        "group": "system",
        "label_ko": "단축키 안내",
        "action": "show_shortcut_guide",
    },
    {
        "id": "delete",
        "key": "Delete",
        "group": "edit",
        "label_ko": "선택 항목 삭제",
        "action": None,
    },
    {
        "id": "escape",
        "key": "Escape",
        "group": "edit",
        "label_ko": "선택 해제",
        # Guide entry only: the main window's keyPressEvent handles Esc so open
        # popups such as the command palette still receive it first.
        "action": None,
    },
    {
        "id": "force_unlock",
        "key": "Ctrl+Alt+Shift+F12",
        "group": "emergency",
        "label_ko": "강제 잠금 해제",
        "action": None,
    },
]

_KEY_BY_ID: dict[str, str] = {item["id"]: item["key"] for item in SHORTCUTS}
_GROUP_LABELS_KO: dict[str, str] = {
    "register": "등록",
    "navigate": "이동",
    "mode": "모드",
    "view": "보기",
    "admin": "관리",
    "window": "창",
    "system": "시스템",
    "edit": "편집",
    "emergency": "긴급",
}
_GUIDE_GROUPS = [
    "register",
    "navigate",
    "mode",
    "view",
    "admin",
    "window",
    "system",
    "edit",
    "emergency",
]
_GUIDE_COLUMNS: list[list[str]] = [
    ["register", "navigate"],
    ["view"],
    ["mode", "admin", "system"],
    ["window", "edit", "emergency"],
]
_GUIDE_GROUP_DESCRIPTIONS_KO: dict[str, str] = {
    "register": "새 일정, 루틴, 지시사항을 빠르게 시작합니다.",
    "navigate": "날짜와 선택 흐름을 이동하거나 빠르게 호출합니다.",
    "mode": "집중, 자석, 잠금 같은 작업 모드를 제어합니다.",
    "view": "툴바, 전체화면, 레이아웃을 다룹니다.",
    "admin": "관리 화면과 자동 정리 도구를 엽니다.",
    "window": "창 위치, 모니터, 투명도 같은 창 동작을 조절합니다.",
    "system": "도움말과 시스템 보조 기능을 확인합니다.",
    "edit": "현재 선택 항목을 정리하거나 해제합니다.",
    "emergency": "예상치 못한 잠금 상태를 강제로 복구합니다.",
}
_GUIDE_PRIORITY_SHORTCUT_IDS: list[str] = [
    "topbar",
    "magnet_mode",
    "lock_mode",
    "force_unlock",
]
_GUIDE_PRIORITY_META_KO: dict[str, tuple[str, str]] = {
    "topbar": ("상단 바 고정", "자동 숨기기를 켜고 끄며, 숨은 상단 바를 바로 고정합니다."),
    "magnet_mode": ("자석 전환", "패널 이동과 부착 가능 상태를 빠르게 바꿉니다."),
    "lock_mode": ("고정 해제", "잠금 상태에서도 메인 화면에서 바로 토글합니다."),
    "force_unlock": ("긴급 복구", "예상치 못한 잠금 상태를 강제로 해제합니다."),
}
_GUIDE_SPOTLIGHT_GROUPS: list[str] = ["register", "mode", "view", "window"]
_GUIDE_SPOTLIGHT_LIMITS: dict[str, int] = {
    "register": 4,
    "mode": 4,
    "view": 4,
    "window": 5,
}
_GUIDE_REFERENCE_COLUMNS: list[list[str]] = [
    ["register", "navigate", "view", "edit"],
    ["mode", "window", "admin", "system", "emergency"],
]
# Shortcuts that also live in a menu: the path is the i18n keys the menu builder
# passes to t(), rendered live so a renamed item cannot leave a stale help path.
# Other shortcuts keep a translatable category in shortcut.entries.<id>.menu_path.
_LAYOUT_PRESETS_PATH = ("menu.display_btn", "menu.layout_presets")
SHORTCUT_MENU_PATHS: dict[str, tuple[str, ...]] = {
    "new_schedule": ("menu.register_btn", "menu.add_schedule"),
    "new_routine": ("menu.register_btn", "menu.add_routine"),
    "new_directive": ("menu.register_btn", "menu.add_directive"),
    "checklist": ("menu.work_btn", "menu.checklist_mgmt"),
    "routine_mgr": ("menu.work_btn", "menu.routine_status"),
    "focus_mode": ("menu.display_btn", "menu.focus_view_options", "menu.focus_mode"),
    "widget_mode": ("menu.display_btn", "menu.focus_view_options", "menu.widget_mode_toggle"),
    "away_lock": ("menu.display_btn", "menu.focus_view_options", "menu.instant_away"),
    "topbar": ("menu.display_btn", "menu.window_view_options", "menu.auto_hide_topbar"),
    "navigation_rail": ("menu.display_btn", "menu.window_view_options", "topbar.navigation_rail"),
    "cal_toolbar": ("menu.display_btn", "menu.window_view_options", "menu.hide_calendar_toolbar"),
    "fullscreen": ("menu.display_btn", "menu.window_view_options", "menu.fullscreen"),
    "save_layout": (*_LAYOUT_PRESETS_PATH, "menu.save_layout"),
    "layout_1": _LAYOUT_PRESETS_PATH,
    "layout_2": _LAYOUT_PRESETS_PATH,
    "layout_3": _LAYOUT_PRESETS_PATH,
    "layout_4": _LAYOUT_PRESETS_PATH,
    "layout_5": _LAYOUT_PRESETS_PATH,
    "sync_gcal": ("menu.system", "sync_unified.menu", "sync_unified.sync_all"),
    "help": ("menu.system", "menu.shortcuts"),
    # The calendar panel's own toolbar, not the top bar.
    "calendar_print": ("panel.main_calendar", "calendar.options", "print.menu"),
    # The calendar and the side panels label this submenu with the same keys.
    "color_assign": (SELECTED_ITEM_MENU_KEY, "context_menu.color_tag", "context_menu.color_auto"),
}
_SHORTCUT_HELP_META_KO: dict[str, dict] = {
    "new_schedule": {
        "description": "일정 입력 창을 바로 엽니다.",
        "tags": ["일정", "추가", "등록", "schedule"],
    },
    "new_routine": {
        "description": "반복 업무 루틴을 빠르게 추가합니다.",
        "tags": ["루틴", "업무", "반복", "routine"],
    },
    "new_directive": {
        "description": "지시나 협조 항목 입력 창을 엽니다.",
        "tags": ["지시", "협조", "directive"],
    },
    "checklist": {
        "description": "체크리스트 템플릿과 항목 구성을 관리합니다.",
        "tags": ["체크리스트", "템플릿", "checklist"],
    },
    "today": {
        "description": "선택 날짜를 오늘로 즉시 이동합니다.",
        "menu_path": "탐색",
        "tags": ["오늘", "날짜", "today"],
    },
    "prev_day": {
        "description": "현재 기준 하루 전으로 이동합니다.",
        "menu_path": "탐색",
        "tags": ["이전", "날짜", "left", "prev"],
    },
    "next_day": {
        "description": "현재 기준 하루 뒤로 이동합니다.",
        "menu_path": "탐색",
        "tags": ["다음", "날짜", "right", "next"],
    },
    "command_palette": {
        "description": "명령 검색창을 열어 기능을 바로 찾습니다.",
        "menu_path": "직접 호출",
        "tags": ["검색", "명령", "팔레트", "palette"],
    },
    "focus_mode": {
        "description": "집중 모드를 켜거나 끕니다.",
        "tags": ["집중", "focus", "pomodoro"],
        "aliases": ["Ctrl+Space"],
    },
    "focus_pause": {
        "description": "집중 진행을 잠시 멈추거나 재개합니다.",
        "menu_path": "집중 모드",
        "tags": ["집중", "일시정지", "pause"],
    },
    "lock_mode": {
        "description": "데스크톱 잠금 모드를 전환합니다.",
        "menu_path": "상단 바 버튼",
        "tags": ["잠금", "lock"],
    },
    "magnet_mode": {
        "description": "패널 정렬과 부착을 돕는 자석 모드를 전환합니다.",
        "menu_path": "상단 바 버튼",
        "tags": ["자석", "패널", "magnet"],
    },
    "away_lock": {
        "description": "자리비움 잠금을 즉시 시작합니다.",
        "tags": ["자리비움", "away", "lock"],
    },
    "topbar": {
        "description": "상단 바 자동 숨기기를 켜거나 끕니다. 끄면 상단 바가 고정됩니다.",
        "tags": ["메뉴바", "상단 바", "topbar", "자동 숨기기", "고정", "복구"],
    },
    "navigation_rail": {
        "description": "왼쪽 빠른 이동 막대를 표시하거나 숨깁니다.",
        "tags": ["빠른 이동", "레일", "navigation", "rail"],
    },
    "cal_toolbar": {
        "description": "캘린더 툴바를 숨기거나 다시 표시합니다.",
        "tags": ["캘린더", "툴바", "toolbar"],
    },
    "fullscreen": {
        "description": "전체화면 표시를 전환합니다.",
        "tags": ["전체화면", "fullscreen"],
    },
    "widget_mode": {
        "description": "위젯 전용 패널 모드를 엽니다.",
        "tags": ["위젯", "widget", "panel"],
    },
    "save_layout": {
        "description": "현재 패널 배치를 프리셋으로 저장합니다.",
        "tags": ["레이아웃", "프리셋", "저장", "layout"],
    },
    "layout_1": {
        "description": "기본 4패널 도킹 배치를 적용합니다.",
        "tags": ["레이아웃", "프리셋", "도킹", "1"],
    },
    "layout_2": {
        "description": "캘린더 중심 배치를 적용합니다.",
        "tags": ["레이아웃", "캘린더", "2"],
    },
    "layout_3": {
        "description": "업무 중심 배치를 적용합니다.",
        "tags": ["레이아웃", "업무", "3"],
    },
    "layout_4": {
        "description": "탭 분할 배치를 적용합니다.",
        "tags": ["레이아웃", "탭", "분할", "4"],
    },
    "layout_5": {
        "description": "분리형 배치를 적용합니다.",
        "tags": ["레이아웃", "분리", "부동", "5"],
    },
    "calendar_print": {
        "description": "현재 보기 또는 지정 기간의 캘린더를 미리보고 인쇄합니다.",
        "tags": ["인쇄", "프린터", "PDF", "print"],
    },
    "sync_gcal": {
        "description": "연결된 모든 캘린더의 동기화를 바로 시작합니다.",
        "tags": ["Google", "Outlook", "iCloud", "네이버", "ICS", "동기화", "캘린더", "F5", "sync"],
    },
    "routine_mgr": {
        "description": "루틴 관리자 탭을 바로 엽니다.",
        "tags": ["루틴", "관리", "routine"],
    },
    "color_assign": {
        "description": "선택 항목에 색상을 자동으로 배정합니다.",
        "tags": ["색상", "태그", "자동", "color"],
    },
    "show_hide": {
        "description": "메인 창을 숨기거나 다시 표시합니다.",
        "menu_path": "창 제어",
        "tags": ["창", "숨기기", "보이기", "overlay"],
    },
    "restore_pos": {
        "description": "창을 안전한 화면 위치로 복원합니다.",
        "menu_path": "창 제어",
        "tags": ["창", "복원", "위치", "restore"],
    },
    "opacity_up": {
        "description": "창 불투명도를 올립니다.",
        "menu_path": "창 제어",
        "tags": ["투명도", "opacity", "밝게"],
    },
    "opacity_down": {
        "description": "창 불투명도를 낮춥니다.",
        "menu_path": "창 제어",
        "tags": ["투명도", "opacity", "낮춤"],
    },
    "monitor_left": {
        "description": "창을 다른 모니터로 이동합니다.",
        "menu_path": "창 제어",
        "tags": ["모니터", "화면", "left", "display"],
    },
    "monitor_right": {
        "description": "창을 다른 모니터로 이동합니다.",
        "menu_path": "창 제어",
        "tags": ["모니터", "화면", "right", "display"],
    },
    "help": {
        "description": "도움말 센터를 엽니다.",
        "tags": ["도움말", "help", "F1"],
    },
    "delete": {
        "description": "현재 선택한 일정이나 항목을 삭제합니다.",
        "menu_path": "선택 상태",
        "tags": ["삭제", "지우기", "delete"],
    },
    "escape": {
        "description": "현재 선택이나 포커스를 정리합니다.",
        "menu_path": "선택 상태",
        "tags": ["선택 해제", "취소", "escape"],
    },
    "force_unlock": {
        "description": "예상치 못한 잠금 상태를 강제로 해제합니다.",
        "menu_path": "긴급 복구",
        "tags": ["강제", "잠금 해제", "복구", "emergency"],
    },
}


def get_key(shortcut_id: str, fallback: str = "") -> str:
    return _KEY_BY_ID.get(shortcut_id, fallback)


def get_shortcut_group_label(group: str, fallback: str = "") -> str:
    from calendar_app.infrastructure.i18n import t

    ko_fallback = _GROUP_LABELS_KO.get(group, fallback or group)
    return t(f"shortcut.groups.{group}.label", ko_fallback)


def get_shortcut_group_description(group: str, fallback: str = "") -> str:
    from calendar_app.infrastructure.i18n import t

    ko_fallback = _GUIDE_GROUP_DESCRIPTIONS_KO.get(group, fallback)
    return t(f"shortcut.groups.{group}.description", ko_fallback)


def _shortcut_group_entries(group: str) -> list[dict]:
    return [item for item in SHORTCUTS if item["group"] == group]


def _shortcut_by_id(shortcut_id: str) -> dict | None:
    for item in SHORTCUTS:
        if item["id"] == shortcut_id:
            return item
    return None


def get_shortcut_guide_entries() -> list[dict]:
    from calendar_app.infrastructure.i18n import t

    entries: list[dict] = []
    for index, item in enumerate(SHORTCUTS):
        shortcut_id = str(item["id"])
        help_meta = _SHORTCUT_HELP_META_KO.get(shortcut_id, {})
        aliases = [
            str(alias).strip() for alias in help_meta.get("aliases", []) if str(alias).strip()
        ]
        ko_tags = [str(tag).strip() for tag in help_meta.get("tags", []) if str(tag).strip()]
        badge_ko, note_ko = _GUIDE_PRIORITY_META_KO.get(shortcut_id, ("", ""))
        entry = dict(item)
        entry["index"] = index

        # Translated fields, each falling back to the bundled Korean copy when the
        # active locale (or the bundled/fallback locale files) has no override yet.
        ns = f"shortcut.entries.{shortcut_id}"
        entry["label_ko"] = t(f"{ns}.label", str(item.get("label_ko") or ""))
        entry["description_ko"] = t(
            f"{ns}.description", str(help_meta.get("description", "") or "")
        )
        menu_keys = SHORTCUT_MENU_PATHS.get(shortcut_id)
        entry["menu_path_ko"] = (
            format_menu_path(menu_keys)
            if menu_keys
            else t(f"{ns}.menu_path", str(help_meta.get("menu_path", "") or ""))
        )
        entry["aliases"] = aliases
        translated_tags = t(f"{ns}.tags", None)
        entry["tags_ko"] = (
            [str(tag).strip() for tag in translated_tags if str(tag).strip()]
            if isinstance(translated_tags, list)
            else ko_tags
        )
        entry["group_label_ko"] = get_shortcut_group_label(str(item.get("group") or ""))
        entry["group_description_ko"] = get_shortcut_group_description(str(item.get("group") or ""))
        entry["recovery"] = shortcut_id in _GUIDE_PRIORITY_SHORTCUT_IDS
        entry["priority_badge_ko"] = (
            t(f"shortcut.priority.{shortcut_id}.badge", badge_ko) if badge_ko else ""
        )
        entry["priority_note_ko"] = (
            t(f"shortcut.priority.{shortcut_id}.note", note_ko) if note_ko else ""
        )
        search_parts = [
            str(item.get("id") or ""),
            str(entry["label_ko"] or ""),
            str(item.get("key") or ""),
            entry["description_ko"],
            entry["menu_path_ko"],
            entry["group_label_ko"],
            " ".join(aliases),
            " ".join(entry["tags_ko"]),
        ]
        entry["search_text_ko"] = " ".join(part for part in search_parts if part).strip()
        entries.append(entry)
    return entries


def get_shortcut_guide_entry(shortcut_id: str) -> dict | None:
    for entry in get_shortcut_guide_entries():
        if entry["id"] == shortcut_id:
            return entry
    return None


def search_shortcut_guide_entries(query: str) -> list[dict]:
    terms = [
        term.strip().lower() for term in re.split(r"\s+", str(query or "").strip()) if term.strip()
    ]
    entries = get_shortcut_guide_entries()
    if not terms:
        return entries

    ranked: list[tuple[int, int, dict]] = []
    for entry in entries:
        label = str(entry.get("label_ko") or "").lower()
        key = str(entry.get("key") or "").lower()
        aliases = " ".join(entry.get("aliases", [])).lower()
        menu_path = str(entry.get("menu_path_ko") or "").lower()
        description = str(entry.get("description_ko") or "").lower()
        tags = " ".join(entry.get("tags_ko", [])).lower()
        combined = " ".join(
            (label, key, aliases, menu_path, description, tags, str(entry.get("id") or "").lower())
        )

        score = 0
        matched = True
        for term in terms:
            if term not in combined:
                matched = False
                break
            if term == label:
                score += 120
            elif term in label:
                score += 80
            if term == key:
                score += 100
            elif term in key:
                score += 70
            if term and term in aliases:
                score += 65
            if term and term in menu_path:
                score += 40
            if term and term in tags:
                score += 35
            if term and term in description:
                score += 20
        if matched:
            if entry.get("recovery"):
                score += 4
            ranked.append((score, int(entry.get("index", 0)), entry))

    ranked.sort(key=lambda row: (-row[0], row[1]))
    return [entry for _, _, entry in ranked]


def _render_keycaps_html(
    key_sequence: str, *, accent: bool = False, tokens: dict | None = None
) -> str:
    key_bg = "rgba(77,166,255,0.18)" if accent else "rgba(255,255,255,0.05)"
    key_border = "rgba(77,166,255,0.40)" if accent else "rgba(255,255,255,0.10)"
    key_text = "#eef6ff" if accent else "#d7e5f7"
    separator = "rgba(155, 177, 203, 0.68)"
    if tokens:
        key_bg = tokens.get("accent_soft_bg" if accent else "surface_item", key_bg)
        key_border = tokens.get("accent_soft_border" if accent else "border_soft", key_border)
        key_text = tokens.get("text_primary", key_text)
        separator = tokens.get("text_muted", separator)
    parts: list[str] = []
    for idx, raw_part in enumerate(str(key_sequence or "").split("+")):
        part = html.escape(raw_part.strip() or "+")
        if idx > 0:
            parts.append(
                f"<span style='color:{separator}; font-size:11px; padding:0 4px;'>+</span>"
            )
        parts.append(
            "<span style='display:inline-block; margin:0 0 4px 0; padding:4px 8px; "
            f"background:{key_bg}; border:1px solid {key_border}; border-radius:8px; "
            f'color:{key_text}; font-family:"Consolas", "D2Coding", monospace; '
            f"font-size:11px; font-weight:700; letter-spacing:0.2px;'>{part}</span>"
        )
    return "".join(parts)


def render_keycaps_html(
    key_sequence: str, *, accent: bool = False, tokens: dict | None = None
) -> str:
    return _render_keycaps_html(key_sequence, accent=accent, tokens=tokens)


def _render_info_pill_html(text: str, *, accent: bool = False) -> str:
    bg = "rgba(77,166,255,0.14)" if accent else "rgba(255,255,255,0.05)"
    border = "rgba(77,166,255,0.24)" if accent else "rgba(255,255,255,0.08)"
    color = "#dff0ff" if accent else "#a9bdd7"
    return (
        "<span style='display:inline-block; margin-left:6px; padding:6px 10px; "
        f"background:{bg}; border:1px solid {border}; border-radius:999px; "
        f"color:{color}; font-size:10px; font-weight:700;'>{html.escape(text)}</span>"
    )


def _render_shortcut_entry_html(
    item: dict, *, compact: bool = False, accent_keys: bool = False
) -> str:
    label = html.escape(str(item.get("label_ko") or ""))
    label_color = "#f1f6ff" if not compact else "#d8e5f5"
    label_size = "12px" if not compact else "11px"
    entry_padding = "8px 0px" if not compact else "7px 0px"
    key_html = _render_keycaps_html(str(item.get("key") or ""), accent=accent_keys)
    return (
        "<div style='padding:"
        f"{entry_padding};'>"
        "<table cellspacing='0' cellpadding='0' style='width:100%; border:none;'>"
        "<tr>"
        f"<td valign='middle' style='padding-right:14px; color:{label_color}; font-size:{label_size}; font-weight:700; line-height:1.45;'>{label}</td>"
        f"<td valign='middle' align='right' style='white-space:nowrap; text-align:right;'>{key_html}</td>"
        "</tr>"
        "</table>"
        "</div>"
    )


def _render_card_grid_html(cards: list[str], *, columns: int, gap_px: int = 12) -> str:
    if not cards:
        return ""
    rows: list[str] = []
    width = round(100 / max(1, columns), 2)
    for start in range(0, len(cards), columns):
        row_cards = cards[start : start + columns]
        cells: list[str] = []
        for idx, card in enumerate(row_cards):
            right_padding = gap_px if idx < len(row_cards) - 1 else 0
            cells.append(
                "<td valign='top' style='vertical-align:top; "
                f"width:{width}%; padding:0 {right_padding}px {gap_px}px 0;'>"
                f"{card}</td>"
            )
        while len(cells) < columns:
            cells.append(
                "<td valign='top' style='vertical-align:top; "
                f"width:{width}%; padding:0 0 {gap_px}px 0;'></td>"
            )
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return (
        "<table cellspacing='0' cellpadding='0' style='width:100%; table-layout:fixed; border:none;'>"
        f"{''.join(rows)}"
        "</table>"
    )


def _render_priority_card_html(shortcut_id: str) -> str:
    item = _shortcut_by_id(shortcut_id)
    if item is None:
        return ""
    badge, note = _GUIDE_PRIORITY_META_KO.get(shortcut_id, ("Quick Recovery", ""))
    label = html.escape(str(item.get("label_ko") or ""))
    note_html = html.escape(note)
    return (
        "<div style='height:100%; padding:14px 15px 14px 15px; "
        "background:rgba(11,18,30,0.96); border:1px solid rgba(77,166,255,0.16); "
        "border-radius:16px;'>"
        f"<div style='color:#7db4ff; font-size:10px; font-weight:800; letter-spacing:1px;'>{html.escape(badge)}</div>"
        f"<div style='margin-top:10px;'>{_render_keycaps_html(str(item.get('key') or ''), accent=True)}</div>"
        f"<div style='margin-top:10px; color:#f5f8ff; font-size:14px; font-weight:800;'>{label}</div>"
        f"<div style='margin-top:6px; color:#8fa6c5; font-size:11px; line-height:1.5;'>{note_html}</div>"
        "</div>"
    )


def _render_spotlight_group_card_html(group: str) -> str:
    all_entries = _shortcut_group_entries(group)
    if not all_entries:
        return ""
    limit = _GUIDE_SPOTLIGHT_LIMITS.get(group, 4)
    entries = all_entries[:limit]
    group_label = html.escape(_GROUP_LABELS_KO.get(group, group))
    group_desc = html.escape(_GUIDE_GROUP_DESCRIPTIONS_KO.get(group, ""))
    rows = "".join(
        _render_shortcut_entry_html(item, compact=True, accent_keys=True) for item in entries
    )
    extra_count = max(0, len(all_entries) - len(entries))
    extra_html = ""
    if extra_count:
        extra_html = (
            "<div style='margin-top:6px; color:#6f86a3; font-size:10px; line-height:1.45;'>"
            f"나머지 {extra_count}개는 아래 전체 분류에서 이어서 확인할 수 있습니다."
            "</div>"
        )
    return (
        "<div style='height:100%; padding:16px 16px 14px 16px; "
        "background:rgba(10,16,28,0.92); border:1px solid rgba(255,255,255,0.08); "
        "border-radius:18px;'>"
        f"<div style='color:#f5f8ff; font-size:15px; font-weight:800; letter-spacing:0.2px;'>{group_label}</div>"
        f"<div style='margin-top:6px; color:#8fa6c5; font-size:11px; line-height:1.5;'>{group_desc}</div>"
        f"<div style='margin-top:10px;'>{rows}</div>"
        f"{extra_html}"
        "</div>"
    )


def _render_reference_group_html(group: str) -> str:
    entries = _shortcut_group_entries(group)
    if not entries:
        return ""
    group_label = html.escape(_GROUP_LABELS_KO.get(group, group))
    group_desc = html.escape(_GUIDE_GROUP_DESCRIPTIONS_KO.get(group, ""))
    rows = "".join(
        _render_shortcut_entry_html(item, compact=True, accent_keys=False) for item in entries
    )
    return (
        "<div style='margin-bottom:12px; padding:14px 14px 12px 14px; "
        "background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06); "
        "border-radius:16px;'>"
        f"<div style='color:#f5f8ff; font-size:13px; font-weight:800; letter-spacing:0.2px;'>{group_label}</div>"
        f"<div style='margin-top:5px; color:#7f95b2; font-size:10px; line-height:1.45;'>{group_desc}</div>"
        f"<div style='margin-top:8px;'>{rows}</div>"
        "</div>"
    )


def _render_priority_band_html() -> str:
    cards = [
        _render_priority_card_html(shortcut_id) for shortcut_id in _GUIDE_PRIORITY_SHORTCUT_IDS
    ]
    cards = [card for card in cards if card]
    return (
        "<div style='margin-top:18px; padding:0;'>"
        "<div style='color:#7db4ff; font-size:11px; font-weight:800; "
        "letter-spacing:1.3px; text-transform:uppercase; margin-bottom:6px;'>Quick Recovery</div>"
        "<div style='color:#f5f8ff; font-size:18px; font-weight:800; margin-bottom:4px;'>"
        "잠금과 메뉴 숨김 상태에서 먼저 확인할 키</div>"
        "<div style='color:#8fa6c5; font-size:11px; line-height:1.55; margin-bottom:14px;'>"
        "당황할 때 가장 먼저 찾게 되는 복구 키만 따로 모았습니다. 아래에는 자주 쓰는 핵심 그룹과 전체 분류가 이어집니다."
        "</div>"
        f"{_render_card_grid_html(cards, columns=2, gap_px=12)}"
        "</div>"
    )


def build_shortcut_guide_html(
    app_version: str = "", app_author: str = "", app_email: str = ""
) -> str:
    spotlight_cards = [
        _render_spotlight_group_card_html(group)
        for group in _GUIDE_SPOTLIGHT_GROUPS
        if _shortcut_group_entries(group)
    ]
    reference_columns = []
    for groups in _GUIDE_REFERENCE_COLUMNS:
        body = "".join(_render_reference_group_html(group) for group in groups)
        reference_columns.append(body)

    footer = ""
    version_label = (app_version or "").strip()
    if version_label and not version_label.lower().startswith("v"):
        version_label = f"v{version_label}"
    author_label = (app_author or "").strip()
    if app_email:
        author_label = f"{author_label} ({app_email})" if author_label else app_email

    from calendar_app.app_metadata import APP_NAME

    footer_parts = [f"<b style='color:#f4f8ff; font-size:11px;'>{APP_NAME}</b>"]
    if version_label:
        footer_parts.append(f"<span style='color:#9fb3d1;'>{html.escape(version_label)}</span>")
    if author_label:
        footer_parts.append(f"<span style='color:#6f86a3;'>{html.escape(author_label)}</span>")

    if len(footer_parts) > 1:
        info_html = footer_parts[0]
        meta_html = " &nbsp; <span style='color:#2e3b4b;'>|</span> &nbsp; ".join(footer_parts[1:])
        footer = (
            "<div style='margin-top:18px; padding:12px 4px 0 4px;'>"
            "<table cellspacing='0' cellpadding='0' style='width:100%; border:none;'>"
            "<tr>"
            f"<td style='font-size:11px;'>{info_html}</td>"
            f"<td align='right' style='font-size:10px; color:#5d6d7e;'>{meta_html}</td>"
            "</tr>"
            "</table>"
            "</div>"
        )

    shortcut_count = len(SHORTCUTS)
    group_count = len([group for group in _GUIDE_GROUPS if _shortcut_group_entries(group)])
    summary_badges = "".join(
        [
            _render_info_pill_html("핵심 4개", accent=True),
            _render_info_pill_html(f"전체 {shortcut_count}개"),
            _render_info_pill_html(f"분류 {group_count}개"),
        ]
    )
    spotlight_html = _render_card_grid_html(spotlight_cards, columns=2, gap_px=12)
    reference_html = _render_card_grid_html(reference_columns, columns=2, gap_px=14)
    html_content = (
        "<div style='padding:4px 6px 14px 6px;'>"
        "<div style='padding:22px 24px; background:rgba(10,15,25,0.98); "
        "border:1px solid rgba(77,166,255,0.14); border-radius:22px;'>"
        "<table cellspacing='0' cellpadding='0' style='width:100%; border:none;'>"
        "<tr>"
        "<td valign='top'>"
        "<div style='color:#7db4ff; font-size:11px; font-weight:800; letter-spacing:1.4px; "
        "text-transform:uppercase;'>Shortcut Guide</div>"
        "<div style='color:#f5f8ff; font-size:26px; font-weight:800; margin-top:8px;'>"
        "단축키 한눈에 보기</div>"
        "<div style='color:#9fb3d1; font-size:12px; line-height:1.62; margin-top:10px;'>"
        "핵심 복구키와 자주 쓰는 작업 흐름을 먼저 보여주고, 전체 목록은 아래 카드에 정리했습니다."
        "</div>"
        "</td>"
        f"<td valign='top' align='right' style='white-space:nowrap;'>{summary_badges}</td>"
        "</tr>"
        "</table>"
        "</div>"
        f"{_render_priority_band_html()}"
        "<div style='margin-top:18px;'>"
        "<div style='color:#7db4ff; font-size:11px; font-weight:800; letter-spacing:1.3px; text-transform:uppercase; margin-bottom:6px;'>Core Flow</div>"
        "<div style='color:#f5f8ff; font-size:18px; font-weight:800; margin-bottom:4px;'>자주 쓰는 핵심 그룹</div>"
        "<div style='color:#8fa6c5; font-size:11px; line-height:1.55; margin-bottom:14px;'>"
        "등록, 보기, 모드, 창 제어처럼 메인 화면에서 자주 쓰는 묶음만 먼저 추렸습니다."
        "</div>"
        f"{spotlight_html}"
        "</div>"
        "<div style='margin-top:14px;'>"
        "<div style='color:#7db4ff; font-size:11px; font-weight:800; letter-spacing:1.3px; text-transform:uppercase; margin-bottom:6px;'>Reference</div>"
        "<div style='color:#f5f8ff; font-size:17px; font-weight:800; margin-bottom:4px;'>전체 분류</div>"
        "<div style='color:#8fa6c5; font-size:11px; line-height:1.55; margin-bottom:14px;'>"
        "세부 단축키는 아래에서 빠르게 찾아볼 수 있습니다."
        "</div>"
        f"{reference_html}"
        "</div>"
        f"{footer}"
        "</div>"
    )
    return html_content


def _iter_shortcut_hosts(app) -> list[QWidget]:
    hosts: list[QWidget] = []
    seen: set[int] = set()

    def _add(widget):
        if widget is None or not isinstance(widget, QWidget):
            return
        widget_id = id(widget)
        if widget_id in seen:
            return
        seen.add(widget_id)
        hosts.append(widget)

    # 1. Main window as primary host
    _add(app)

    # 2. Known docks as potential floating independent windows
    for dock_name in ("left_dock", "center_dock", "routine_dock", "directive_dock"):
        _add(getattr(app, dock_name, None))

    # 3. Any dynamical children that are dock widgets or top-level windows
    if hasattr(app, "findChildren"):
        for dock in app.findChildren(QDockWidget):
            _add(dock)

    # 4. Handle edge cases where detached windows might not be children anymore
    # (Though in PyQt6 usually they remain children unless specifically reparented)

    return hosts


def _clear_registered_shortcuts(app) -> None:
    for shortcut in list(getattr(app, "_global_shortcuts", [])):
        with contextlib.suppress(Exception):
            shortcut.activated.disconnect()
        shortcut.setParent(None)
        shortcut.deleteLater()
    app._global_shortcuts = []


def _active_window_geometry(app):
    active = QApplication.activeWindow()
    if isinstance(active, QWidget) and active is not getattr(app, "command_palette", None):
        try:
            return active.frameGeometry()
        except Exception:
            return active.geometry()
    try:
        return app.frameGeometry()
    except Exception:
        return app.geometry()


def _show_command_palette(app) -> None:
    if hasattr(app, "show_command_palette"):
        app.show_command_palette()
        return
    palette = getattr(app, "command_palette", None)
    if palette is None:
        return
    palette.show_at_center(_active_window_geometry(app))


def _make_shortcut(host: QWidget, owner, key: str, handler: Callable) -> QShortcut:
    shortcut = QShortcut(QKeySequence(key), host)
    shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
    shortcut.activated.connect(handler)
    if not hasattr(owner, "_global_shortcuts"):
        owner._global_shortcuts = []
    owner._global_shortcuts.append(shortcut)
    return shortcut


# OS-wide hotkeys (RegisterHotKey). Only show/hide is global: after the window is
# hidden to the tray no window is active, so an in-app shortcut cannot reach it.
GLOBAL_HOTKEY_IDS: dict[str, int] = {"show_hide": 0x0A1C}


def _native_hotkeys_supported() -> bool:
    """RegisterHotKey needs Win32 and real native windows (not offscreen/minimal)."""
    if not win32_input.HOTKEYS_AVAILABLE or QGuiApplication.instance() is None:
        return False
    return QGuiApplication.platformName() == "windows"


class _HotkeyWindow(QWindow):
    """Never-shown native window whose HWND receives WM_HOTKEY.

    Owning a window keeps the handler's lifetime tied to this object (no filter on
    the application), and its HWND is not recreated when the main window changes
    flags for always-on-top or desktop mode.
    """

    def __init__(self, on_hotkey: Callable[[int], None]):
        super().__init__()
        self._on_hotkey = on_hotkey
        self.create()

    def nativeEvent(self, event_type, message):
        # A Python exception escaping a Qt virtual aborts the process.
        try:
            address = int(message) if message is not None else 0
            hotkey_id = win32_input.hotkey_id_from_message(address)
            if hotkey_id is not None:
                self._on_hotkey(hotkey_id)
                return True, 0
        except Exception:
            logger.exception("Global hotkey message handling failed")
        return False, 0


class GlobalHotkeys:
    """The app's RegisterHotKey registrations, keyed by shortcut id."""

    def __init__(self, on_activated: Callable[[str], None]):
        self._on_activated = on_activated
        self._keys: dict[str, str] = {}
        self.notified_failures: set[str] = set()
        self.window = _HotkeyWindow(self._dispatch)

    def _hwnd(self) -> int:
        return int(self.window.winId()) if self.window is not None else 0

    def _dispatch(self, hotkey_id: int) -> None:
        for shortcut_id, known_id in GLOBAL_HOTKEY_IDS.items():
            if known_id == hotkey_id and shortcut_id in self._keys:
                # Run the action after the native message handler has returned.
                QTimer.singleShot(0, lambda sid=shortcut_id: self._on_activated(sid))
                return

    def owns(self, shortcut_id: str, key: str) -> bool:
        return bool(key) and self._keys.get(shortcut_id) == key

    def register(self, shortcut_id: str, key: str) -> tuple[bool, int]:
        """Register ``key`` for ``shortcut_id``, replacing an older key; (ok, error)."""
        if self.owns(shortcut_id, key):
            return True, 0
        self.unregister(shortcut_id)
        codes = win32_input.parse_hotkey(key)
        if codes is None or self.window is None:
            return False, 0
        ok, error = win32_input.register_hotkey(
            self._hwnd(), GLOBAL_HOTKEY_IDS[shortcut_id], codes[0], codes[1]
        )
        if ok:
            self._keys[shortcut_id] = key
        return ok, error

    def unregister(self, shortcut_id: str) -> None:
        if self._keys.pop(shortcut_id, None) is not None:
            win32_input.unregister_hotkey(self._hwnd(), GLOBAL_HOTKEY_IDS[shortcut_id])

    def release(self) -> None:
        for shortcut_id in list(self._keys):
            self.unregister(shortcut_id)
        window, self.window = self.window, None
        if window is not None:
            window.destroy()


def _shortcut_action(app, shortcut_id: str):
    item = _shortcut_by_id(shortcut_id) or {}
    handler = getattr(app, str(item.get("action") or ""), None)
    return handler if callable(handler) else None


def _run_global_hotkey(app_ref, shortcut_id: str) -> None:
    app = app_ref()
    handler = _shortcut_action(app, shortcut_id) if app is not None else None
    if handler is None:
        return
    try:
        handler()
    except Exception:
        logger.exception("Global hotkey action '%s' failed", shortcut_id)


def _notify_global_hotkey_unavailable(app, controller, shortcut_id: str, key: str) -> None:
    if shortcut_id in controller.notified_failures:
        return
    controller.notified_failures.add(shortcut_id)
    # Tell the user once per key, not on every start while another program keeps it.
    settings = getattr(app, "settings", None)
    seen_setting = f"global_hotkey_notice_{shortcut_id}"
    if settings is not None and str(settings.value(seen_setting, "") or "") == key:
        return
    show_toast = getattr(app, "show_toast", None)
    if not callable(show_toast):
        return
    from calendar_app.infrastructure.i18n import t

    item = _shortcut_by_id(shortcut_id) or {}
    title = t(f"shortcut.entries.{shortcut_id}.label", str(item.get("label_ko") or ""))
    message = t(
        "shortcut.global_hotkey.unavailable",
        "다른 프로그램이 {shortcut} 키를 사용 중이라 이 단축키는 앱 창이 활성일 때만 "
        "동작합니다. 숨긴 창은 트레이 아이콘으로 다시 열 수 있습니다.",
        shortcut=key,
    )
    try:
        show_toast(title, message)
    except Exception:
        logger.exception("Failed to show the global hotkey notice")
        return
    if settings is not None:
        settings.setValue(seen_setting, key)


def sync_global_hotkeys(app) -> None:
    """Register OS-wide hotkeys with their current keys; re-run after a key change.

    A key another program owns stays an in-app shortcut: it is logged on every run
    and the user is told once per key.
    """
    if not _native_hotkeys_supported():
        return
    controller = getattr(app, "_global_hotkeys", None)
    if controller is None:
        app_ref = weakref.ref(app)
        controller = GlobalHotkeys(lambda sid: _run_global_hotkey(app_ref, sid))
        app._global_hotkeys = controller
    for shortcut_id in GLOBAL_HOTKEY_IDS:
        key = get_key(shortcut_id)
        if not key or _shortcut_action(app, shortcut_id) is None:
            controller.unregister(shortcut_id)
            continue
        ok, error = controller.register(shortcut_id, key)
        if ok:
            logger.info("Global hotkey %s registered for '%s'", key, shortcut_id)
            continue
        logger.warning(
            "Global hotkey %s for '%s' is unavailable (Win32 error %s); "
            "keeping the in-app shortcut",
            key,
            shortcut_id,
            error,
        )
        _notify_global_hotkey_unavailable(app, controller, shortcut_id, key)


def release_global_hotkeys(app) -> None:
    """Unregister every OS-wide hotkey and drop the message window (idempotent)."""
    controller = getattr(app, "_global_hotkeys", None)
    if controller is None:
        return
    app._global_hotkeys = None
    try:
        controller.release()
    except Exception:
        logger.exception("Failed to release global hotkeys")


def _owned_by_global_hotkey(app, shortcut_id: str, key: str) -> bool:
    owns = getattr(getattr(app, "_global_hotkeys", None), "owns", None)
    return bool(callable(owns) and owns(shortcut_id, key))


def register_app_shortcuts(app) -> None:
    """Register OS-wide hotkeys, then the in-app shortcuts they do not cover."""
    sync_global_hotkeys(app)
    register_all(app)


def register_all(app) -> None:
    """Register shortcuts on the main window only.

    Registering identical ``ApplicationShortcut`` bindings on multiple dock hosts
    makes Qt treat them as ambiguous, which can cause shortcuts to stop firing.
    Keep a single authoritative registration point on the app window.
    """
    if not hasattr(app, "_global_shortcuts"):
        app._global_shortcuts = []
    else:
        _clear_registered_shortcuts(app)

    def _register_on_hosts(key: str, handler: Callable):
        _make_shortcut(app, app, key, handler)

    for shortcut in SHORTCUTS:
        shortcut_id = shortcut["id"]
        key = get_key(shortcut_id, shortcut["key"])
        action_name = shortcut["action"]

        if _owned_by_global_hotkey(app, shortcut_id, key):
            # The OS-wide hotkey consumes the key; a QShortcut would only double-fire.
            continue

        if action_name and hasattr(app, action_name):
            _register_on_hosts(key, getattr(app, action_name))
            continue

        if shortcut_id == "new_directive":
            if hasattr(app, "open_directive_dialog"):
                _register_on_hosts(key, app.open_directive_dialog)

        elif shortcut_id == "focus_mode":
            if hasattr(app, "toggle_focus_mode"):
                _register_on_hosts(key, app.toggle_focus_mode)
                _register_on_hosts("Ctrl+Space", app.toggle_focus_mode)

        elif shortcut_id == "command_palette":
            _register_on_hosts(key, lambda a=app: _show_command_palette(a))

        elif shortcut_id == "focus_pause":
            if hasattr(app, "toggle_focus_pause"):
                _register_on_hosts(key, app.toggle_focus_pause)

        elif shortcut_id == "lock_mode":

            def _toggle_lock(a=app):
                if hasattr(a, "lock_btn"):
                    a.lock_btn.setChecked(not a.lock_btn.isChecked())
                    a.toggle_lock_mode()

            _register_on_hosts(key, _toggle_lock)

        elif shortcut_id == "away_lock":

            def _away(a=app):
                if hasattr(a, "toggle_idle_lock"):
                    a.toggle_idle_lock(True, manual=True)

            _register_on_hosts(key, _away)

        elif shortcut_id == "save_layout":

            def _save(a=app):
                if hasattr(a, "preset_manager"):
                    a.preset_manager._save_with_prompt()

            _register_on_hosts(key, _save)

        elif shortcut_id.startswith("layout_"):
            try:
                # layout_1, layout_2, etc. -> index 0, 1, etc.
                idx = int(shortcut_id.split("_")[1]) - 1

                def _layout(checked=False, i=idx, a=app):
                    if hasattr(a, "apply_layout_preset"):
                        a.apply_layout_preset(i)

                _register_on_hosts(key, _layout)
            except (ValueError, IndexError):
                pass

        elif shortcut_id == "routine_mgr":

            def _routine_manager(a=app):
                if hasattr(a, "open_work_management_dialog"):
                    a.open_work_management_dialog(start_tab="routine")

            _register_on_hosts(key, _routine_manager)

        elif shortcut_id == "opacity_up":

            def _opacity_up(a=app):
                if hasattr(a, "slider"):
                    a.slider.setValue(min(a.slider.value() + 10, 255))

            _register_on_hosts(key, _opacity_up)

        elif shortcut_id == "opacity_down":

            def _opacity_down(a=app):
                if hasattr(a, "slider"):
                    a.slider.setValue(max(a.slider.value() - 10, 20))

            _register_on_hosts(key, _opacity_down)

        elif shortcut_id == "delete":

            def _delete(a=app):
                if hasattr(a, "delete_selected_items"):
                    a.delete_selected_items()
                elif hasattr(a, "delete_selected_tasks"):
                    a.delete_selected_tasks()

            _register_on_hosts(key, _delete)

        elif shortcut_id == "force_unlock":
            pass

        elif action_name and not hasattr(app, action_name):
            logger.debug(
                "Shortcut '%s': action '%s' not found on app - skipped.", shortcut_id, action_name
            )

    logger.info("Global shortcuts registered (ApplicationShortcut): %d", len(app._global_shortcuts))
