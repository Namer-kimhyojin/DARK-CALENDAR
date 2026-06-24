"""
아이콘 매핑 테이블 — 이모지 → qtawesome (Font Awesome 6 / Material Design Icons)

사용 방법:
    import qtawesome as qta
    from calendar_app.shared.icon_map import ICON, icon

    # QIcon 생성
    ic = icon(ICON.REFRESH)
    # 색상 지정
    ic = icon(ICON.REFRESH, color="#3c8cff")
    # QAction / QPushButton 에 적용
    act = menu.addAction("새로고침")
    act.setIcon(icon(ICON.REFRESH))

의존성:
    pip install qtawesome   # Font Awesome 6 + Material Design Icons 번들

TODO (Phase 2+):
    - [ ] qtawesome 를 requirements.txt 에 추가
    - [ ] icon() 헬퍼 실제 구현체 활성화 (현재 스텁 상태)
    - [ ] 각 사용처에서 이모지 텍스트 제거 후 setIcon() 으로 교체
    - [ ] 날씨 위젯(overlay_weather.py) 아이콘은 SVG 파일 방식 별도 검토
"""

from __future__ import annotations

from dataclasses import dataclass
import re

# Matches one or more leading emoji/symbol characters followed by optional whitespace.
# Covers: supplementary-plane emoji (U+10000+), Misc Technical+Symbols+Dingbats
# (U+2300-27BF, includes ⌨ U+2328 and ⏱ U+23F1), Misc Symbols Extended
# (U+2B00-2BFF), Variation Selectors (U+FE00-FE0F), and ZWJ (U+200D).
# Used to strip duplicate emoji from menu text when qtawesome icons are also set.
_LEADING_EMOJI_RE = re.compile(
    r"^(?:[\U00010000-\U0010FFFF]|‍|[⌀-➿]|[⬀-⯿]|[︀-️])+"
    r"\s*",
    re.UNICODE,
)


def strip_leading_emoji(text: str) -> str:
    """Remove leading emoji/symbol prefix and surrounding whitespace from menu label text."""
    return _LEADING_EMOJI_RE.sub("", str(text)).lstrip()


# ---------------------------------------------------------------------------
# 아이콘 키 상수
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _IconKeys:
    """아이콘 키 상수 모음. ICON.KEY 형태로 사용."""

    # ── 우선순위 (Priority) ────────────────────────────────────────────────
    PRIORITY_URGENT: str = "priority_urgent"
    PRIORITY_HIGH: str = "priority_high"
    PRIORITY_NORMAL: str = "priority_normal"
    PRIORITY_LOW: str = "priority_low"

    # ── 상태 (Status) ──────────────────────────────────────────────────────
    STATUS_PENDING: str = "status_pending"
    STATUS_IN_PROGRESS: str = "status_in_progress"
    STATUS_COMPLETED: str = "status_completed"
    STATUS_DEFERRED: str = "status_deferred"
    STATUS_OVERDUE: str = "status_overdue"
    STATUS_CANCELED: str = "status_canceled"

    # ── CRUD / 일반 액션 ───────────────────────────────────────────────────
    ADD: str = "add"
    EDIT: str = "edit"
    DELETE: str = "delete"
    REFRESH: str = "refresh"
    SYNC: str = "sync"
    SEARCH: str = "search"
    SAVE: str = "save"
    CANCEL: str = "cancel"

    # ── 보기 / 탐색 ────────────────────────────────────────────────────────
    VIEW_CALENDAR: str = "view_calendar"
    VIEW_MONTHLY: str = "view_monthly"
    GOTO_TODAY: str = "goto_today"
    NAV_PREV: str = "nav_prev"
    NAV_NEXT: str = "nav_next"

    # ── 필터 / 정렬 ────────────────────────────────────────────────────────
    FILTER: str = "filter"
    FILTER_ALL: str = "filter_all"
    FILTER_OVERDUE: str = "filter_overdue"
    FILTER_PROGRESS: str = "filter_progress"
    SORT_MODE: str = "sort_mode"
    SORT_BY_TIME: str = "sort_by_time"
    SORT_BY_PRIORITY: str = "sort_by_priority"

    # ── 그룹화 ────────────────────────────────────────────────────────────
    GROUP_BY_DATE: str = "group_by_date"
    GROUP_BY_CYCLE: str = "group_by_cycle"
    GROUP_BY_RECEIVER: str = "group_by_receiver"

    # ── 화면 / 레이아웃 ───────────────────────────────────────────────────
    SCREEN_MGMT: str = "screen_mgmt"
    NEXT_MONITOR: str = "next_monitor"
    SNAP_LEFT: str = "snap_left"
    SNAP_RIGHT: str = "snap_right"
    SNAP_TOP: str = "snap_top"
    SNAP_BOTTOM: str = "snap_bottom"
    SNAP_CENTER: str = "snap_center"
    OPACITY: str = "opacity"
    OPACITY_UP: str = "opacity_up"
    OPACITY_DOWN: str = "opacity_down"
    MAGNET: str = "magnet"
    MAGNET_OFF: str = "magnet_off"
    TOOLBAR: str = "toolbar"

    # ── 구글 캘린더 ───────────────────────────────────────────────────────
    GCAL: str = "gcal"
    SYNC_SETTINGS: str = "sync_settings"
    LOCK: str = "lock"
    UNLOCK: str = "unlock"
    AUTH: str = "auth"
    LINK: str = "link"
    CLOUD: str = "cloud"
    BLOCKED: str = "blocked"

    # ── 일정 / 관리 ───────────────────────────────────────────────────────
    ALL_SCHEDULES: str = "all_schedules"
    CHECKLIST: str = "checklist"
    ROUTINE: str = "routine"
    DIRECTIVE: str = "directive"
    PRESET: str = "preset"
    PRESET_LOAD: str = "preset_load"
    ALARM: str = "alarm"
    MEMO: str = "memo"
    PERSON: str = "person"
    STATUS_TODAY: str = "status_today"

    # ── 위젯 UI ───────────────────────────────────────────────────────────
    SETTINGS: str = "settings"
    WIDGET_MGR: str = "widget_mgr"
    ALWAYS_ON_TOP: str = "always_on_top"
    HIDE: str = "hide"
    RESET_POS: str = "reset_pos"
    RESET_SIZE: str = "reset_size"
    FONT: str = "font"
    TEXT_COLOR: str = "text_color"
    APPEARANCE: str = "appearance"
    DISPLAY_STYLE: str = "display_style"
    FULLSCREEN: str = "fullscreen"
    COLOR_PICKER: str = "color_picker"
    ADVANCED: str = "advanced"

    # ── 뽀모도로 / 포커스 ──────────────────────────────────────────────────
    POMODORO: str = "pomodoro"
    BREAK_SHORT: str = "break_short"
    BREAK_LONG: str = "break_long"
    FOCUS_DONE: str = "focus_done"

    # ── 문서 / 로케일 ─────────────────────────────────────────────────────
    DOCS: str = "docs"
    LOCALE_MGMT: str = "locale_mgmt"
    LOCALE_FILE: str = "locale_file"
    OAUTH_GUIDE: str = "oauth_guide"
    TIP: str = "tip"

    # ── 상태 표시 (GCal 동기화 스피너 등) ────────────────────────────────
    SYNCING: str = "syncing"
    ERROR: str = "error"
    WARNING: str = "warning"
    INFO: str = "info"
    STAR: str = "star"
    STAR_EMPTY: str = "star_empty"
    BROADCAST: str = "broadcast"
    REPEAT: str = "repeat"
    CHECK: str = "check"
    CLOSE: str = "close"

    # ── 위젯 개별 아이콘 ──────────────────────────────────────────────────
    WIDGET_CLOCK: str = "widget_clock"
    WIDGET_WEATHER: str = "widget_weather"
    WIDGET_STOPWATCH: str = "widget_stopwatch"
    WIDGET_COUNTDOWN: str = "widget_countdown"
    WIDGET_DATECARD: str = "widget_datecard"
    WIDGET_DDAY: str = "widget_dday"
    WIDGET_TEXT: str = "widget_text"
    FOLDER: str = "folder"
    AUTOSTART: str = "autostart"
    THEME_DARK: str = "theme_dark"
    THEME_LIGHT: str = "theme_light"
    THEME_AUTO: str = "theme_auto"
    # ── 기타 공통 아이콘 ──────────────────────────────────────────────────
    CALENDAR: str = "calendar"
    GLOBE: str = "globe"
    PEOPLE: str = "people"
    VALIDATE: str = "validate"


ICON = _IconKeys()


# ---------------------------------------------------------------------------
# 매핑 테이블
# key: _IconKeys 필드값  →  value: (qtawesome_name, 원래_이모지, 용도_메모)
# ---------------------------------------------------------------------------
# qtawesome 아이콘 이름 규칙 (qtawesome 1.x 기준):
#   fa6s.*   — Font Awesome 6 Solid
#   fa6b.*   — Font Awesome 6 Brands
#   mdi6.*   — Material Design Icons 6 (outline 계열 포함)
#   fa6r.*   — 지원 안 됨 → mdi6.*-outline 또는 fa6s.* 로 대체
# ---------------------------------------------------------------------------

ICON_MAPPING: dict[str, tuple[str, str, str]] = {
    # ── 우선순위 ────────────────────────────────────────────────────────────
    ICON.PRIORITY_URGENT: ("fa6s.fire-flame-curved", "", "긴급 우선순위"),
    ICON.PRIORITY_HIGH: ("fa6s.circle-chevron-up", "", "높은 우선순위"),
    ICON.PRIORITY_NORMAL: ("fa6s.circle-dot", "", "보통 우선순위"),
    ICON.PRIORITY_LOW: ("mdi6.circle-medium", "", "낮은 우선순위"),
    # ── 상태 ────────────────────────────────────────────────────────────────
    ICON.STATUS_PENDING: ("mdi6.clock-outline", "", "대기 중"),
    ICON.STATUS_IN_PROGRESS: ("fa6s.bolt-lightning", "", "진행 중"),
    ICON.STATUS_COMPLETED: ("fa6s.circle-check", "", "완료"),
    ICON.STATUS_DEFERRED: ("mdi6.clock-fast", "", "보류"),
    ICON.STATUS_OVERDUE: ("fa6s.calendar-circle-exclamation", "", "기한 초과"),
    ICON.STATUS_CANCELED: ("fa6s.ban", "", "취소"),
    # ── CRUD / 일반 액션 ────────────────────────────────────────────────────
    ICON.ADD: ("fa6s.plus", "", "추가"),
    ICON.EDIT: ("fa6s.pen-to-square", "", "편집"),
    ICON.DELETE: ("fa6s.trash-can", "", "삭제"),
    ICON.REFRESH: ("fa6s.rotate", "", "새로고침 / 갱신"),
    ICON.SYNC: ("fa6s.arrows-rotate", "", "동기화 버튼"),
    ICON.SEARCH: ("fa6s.magnifying-glass", "", "검색 / 필터"),
    ICON.SAVE: ("fa6s.floppy-disk", "", "저장"),
    ICON.CANCEL: ("fa6s.ban", "", "취소"),
    # ── 보기 / 탐색 ─────────────────────────────────────────────────────────
    ICON.VIEW_CALENDAR: ("mdi6.calendar-month-outline", "", "캘린더 뷰 버튼"),
    ICON.VIEW_MONTHLY: ("fa6s.calendar-days", "", "월간 뷰"),
    ICON.GOTO_TODAY: ("mdi6.calendar-today", "", "오늘 날짜로 이동"),
    ICON.NAV_PREV: ("fa6s.chevron-left", "", "이전"),
    ICON.NAV_NEXT: ("fa6s.chevron-right", "", "다음"),
    # ── 필터 / 정렬 ─────────────────────────────────────────────────────────
    ICON.FILTER: ("fa6s.filter", "", "필터 메뉴"),
    ICON.FILTER_ALL: ("mdi6.filter-variant", "", "전체 보기"),
    ICON.FILTER_OVERDUE: ("mdi6.calendar-alert", "", "기한 초과 필터"),
    ICON.FILTER_PROGRESS: ("fa6s.helmet-safety", "", "진행 중 필터"),
    ICON.SORT_MODE: ("fa6s.arrow-up-wide-short", "", "정렬 모드"),
    ICON.SORT_BY_TIME: ("mdi6.clock-outline", "", "시간순 정렬"),
    ICON.SORT_BY_PRIORITY: ("fa6s.flag", "", "우선순위 정렬"),
    # ── 그룹화 ──────────────────────────────────────────────────────────────
    ICON.GROUP_BY_DATE: ("mdi6.calendar-outline", "", "날짜별 그룹"),
    ICON.GROUP_BY_CYCLE: ("fa6s.arrows-spin", "", "주기별 그룹"),
    ICON.GROUP_BY_RECEIVER: ("fa6s.user-group", "", "수신자별 그룹"),
    # ── 화면 / 레이아웃 ──────────────────────────────────────────────────────
    ICON.SCREEN_MGMT: ("fa6s.desktop", "", "화면 관리"),
    ICON.NEXT_MONITOR: ("fa6s.tv", "", "다음 모니터로"),
    ICON.SNAP_LEFT: ("fa6s.arrow-left", "", "왼쪽 스냅"),
    ICON.SNAP_RIGHT: ("fa6s.arrow-right", "", "오른쪽 스냅"),
    ICON.SNAP_TOP: ("fa6s.arrow-up", "", "위 스냅"),
    ICON.SNAP_BOTTOM: ("fa6s.arrow-down", "", "아래 스냅"),
    ICON.SNAP_CENTER: ("fa6s.compress", "", "가운데 스냅"),
    ICON.OPACITY: ("mdi6.eye-outline", "", "투명도"),
    ICON.OPACITY_UP: ("mdi6.plus-thick", "", "투명도 증가"),
    ICON.OPACITY_DOWN: ("mdi6.minus-thick", "", "투명도 감소"),
    ICON.MAGNET: ("mdi6.magnet-on", "", "자석/도킹 모드 활성"),
    ICON.MAGNET_OFF: ("mdi6.magnet", "", "자석/도킹 모드 비활성"),
    ICON.TOOLBAR: ("mdi6.dock-top", "", "툴바 표시"),
    # ── 구글 캘린더 ──────────────────────────────────────────────────────────
    ICON.GCAL: ("fa6b.google", "", "Google Calendar"),
    ICON.SYNC_SETTINGS: ("mdi6.calendar-sync", "", "동기화 설정"),
    ICON.LOCK: ("fa6s.lock", "", "잠금"),
    ICON.UNLOCK: ("fa6s.lock-open", "", "잠금 해제"),
    ICON.AUTH: ("mdi6.shield-lock", "", "인증"),
    ICON.LINK: ("fa6s.link", "", "연결"),
    ICON.CLOUD: ("fa6s.cloud", "", "클라우드 콘솔"),
    ICON.BLOCKED: ("mdi6.account-off", "", "연동 해제"),
    # ── 일정 / 관리 ──────────────────────────────────────────────────────────
    ICON.ALL_SCHEDULES: ("fa6s.layer-group", "", "전체 일정"),
    ICON.CHECKLIST: ("fa6s.list-check", "", "체크리스트"),
    ICON.ROUTINE: ("fa6s.arrows-rotate", "", "루틴 관리"),
    ICON.DIRECTIVE: ("fa6s.bullhorn", "", "지시/협조사항"),
    ICON.PRESET: ("fa6s.thumbtack", "", "프리셋 슬롯"),
    ICON.PRESET_LOAD: ("fa6s.download", "", "기본 프리셋 불러오기"),
    ICON.ALARM: ("fa6s.bell", "", "알람"),
    ICON.MEMO: ("fa6s.note-sticky", "", "메모"),
    ICON.PERSON: ("fa6s.user-ninja", "", "담당자/수신자"),
    ICON.STATUS_TODAY: ("fa6s.sun", "", "오늘"),
    # ── 위젯 UI ──────────────────────────────────────────────────────────────
    ICON.SETTINGS: ("fa6s.gears", "", "설정"),
    ICON.WIDGET_MGR: ("fa6s.window-restore", "", "위젯 관리자"),
    ICON.ALWAYS_ON_TOP: ("mdi6.pin-outline", "", "항상 위에"),
    ICON.HIDE: ("fa6s.eye-slash", "", "숨기기"),
    ICON.RESET_POS: ("mdi6.map-marker-radius", "", "위치 초기화"),
    ICON.RESET_SIZE: ("fa6s.maximize", "", "크기 초기화"),
    ICON.FONT: ("fa6s.font", "", "폰트"),
    ICON.TEXT_COLOR: ("mdi6.format-color-text", "", "텍스트 색상"),
    ICON.APPEARANCE: ("fa6s.wand-magic-sparkles", "", "외관"),
    ICON.DISPLAY_STYLE: ("fa6s.palette", "", "표시 스타일"),
    ICON.FULLSCREEN: ("fa6s.expand", "", "전체 화면"),
    ICON.COLOR_PICKER: ("mdi6.palette-swatch-outline", "", "색상 선택"),
    ICON.ADVANCED: ("fa6s.screwdriver-wrench", "", "고급 설정"),
    # ── 뽀모도로 / 포커스 ────────────────────────────────────────────────────
    ICON.POMODORO: ("fa6s.stopwatch", "", "뽀모도로 작업"),
    ICON.BREAK_SHORT: ("fa6s.mug-hot", "", "짧은 휴식"),
    ICON.BREAK_LONG: ("fa6s.umbrella-beach", "", "긴 휴식"),
    ICON.FOCUS_DONE: ("fa6s.medal", "", "포커스 완료"),
    # ── 문서 / 로케일 ─────────────────────────────────────────────────────
    ICON.DOCS: ("mdi6.book-open-blank-variant", "", "공식 문서"),
    ICON.LOCALE_MGMT: ("fa6s.language", "", "로케일 파일 관리"),
    ICON.LOCALE_FILE: ("mdi6.file-code-outline", "", "현재 언어 파일 열기"),
    ICON.OAUTH_GUIDE: ("fa6s.key", "", "OAuth 가이드"),
    ICON.TIP: ("fa6s.lightbulb", "", "팁 / 안내"),
    # ── 상태 표시 ────────────────────────────────────────────────────────────
    ICON.SYNCING: ("fa6s.spinner", "", "동기화 진행 중 (스피너)"),
    ICON.ERROR: ("fa6s.circle-xmark", "", "오류"),
    ICON.WARNING: ("fa6s.triangle-exclamation", "", "경고"),
    ICON.INFO: ("fa6s.circle-info", "", "정보"),
    ICON.STAR: ("fa6s.star", "", "별 (기본 캘린더 표시)"),
    ICON.STAR_EMPTY: ("mdi6.star-outline", "", "빈 별"),
    ICON.BROADCAST: ("mdi6.broadcast", "", "공지 / 브로드캐스트"),
    ICON.REPEAT: ("fa6s.repeat", "", "반복"),
    ICON.CHECK: ("fa6s.check", "", "체크 표시"),
    ICON.CLOSE: ("fa6s.xmark", "", "닫기"),
    # ── 위젯 개별 아이콘 ──────────────────────────────────────────────────
    ICON.WIDGET_CLOCK: ("mdi6.clock-digital", "", "디지털 시계 위젯"),
    ICON.WIDGET_WEATHER: ("fa6s.cloud-sun", "", "날씨 위젯"),
    ICON.WIDGET_STOPWATCH: ("fa6s.stopwatch-20", "", "스톱워치 위젯"),
    ICON.WIDGET_COUNTDOWN: ("mdi6.timer-sand", "", "카운트다운 위젯"),
    ICON.WIDGET_DATECARD: ("mdi6.calendar-today", "", "날짜 카드 위젯"),
    ICON.WIDGET_DDAY: ("mdi6.calendar-star", "", "D-Day 위젯"),
    ICON.WIDGET_TEXT: ("mdi6.text-box-outline", "", "텍스트 위젯"),
    ICON.FOLDER: ("fa6s.folder-open", "", "폴더 열기"),
    ICON.AUTOSTART: ("fa6s.rocket", "", "윈도우 시작 시 자동 실행"),
    ICON.THEME_DARK: ("fa6s.moon", "", "다크 모드"),
    ICON.THEME_LIGHT: ("fa6s.sun", "", "라이트 모드"),
    ICON.THEME_AUTO: ("fa6s.desktop", "", "시스템 기본 테마"),
    ICON.VALIDATE: ("fa6s.file-shield", "", "검증"),
    # ── 기타 공통 ───────────────────────────────────────────────────────────
    ICON.CALENDAR: ("fa6s.calendar", "", "일반 달력"),
    ICON.GLOBE: ("fa6s.globe", "", "글로벌 / 웹 / ICS"),
    ICON.PEOPLE: ("fa6s.user-group", "", "협업 / 공유"),
}

# 날씨 아이콘은 WMO 코드 → 문자열 매핑이라 별도 관리
# overlay_weather.py 의 WEATHER_ICONS dict 는 SVG 파일 방식으로 교체 예정
# (qtawesome 에 날씨 아이콘 세트 없음 → Weather Icons 폰트 또는 SVG 파일 권장)
WEATHER_ICON_NOTE = (
    "날씨 아이콘(overlay_weather.py)은 WMO 코드 기반이며 "
    "qtawesome 번들에 적합한 날씨 세트가 없습니다. "
    "Erik Flowers의 'Weather Icons' 폰트 또는 "
    "OpenWeatherMap SVG 파일 세트를 별도로 추가하는 방안을 검토하세요."
)


# ---------------------------------------------------------------------------
# icon() 헬퍼 — qtawesome 가 설치된 경우에만 실제 QIcon 반환
# (미설치 시 빈 QIcon 반환하여 기존 이모지 텍스트 폴백으로 동작)
# ---------------------------------------------------------------------------


def icon(key: str, color: str | None = None, **kwargs):
    """
    아이콘 키로 QIcon 을 반환합니다.

    Args:
        key:    ICON.* 상수 값 (예: ICON.REFRESH)
        color:  hex 색상 문자열 (예: "#3c8cff"). None 이면 qtawesome 기본값.
        **kwargs: qtawesome.icon() 에 전달할 추가 인자

    Returns:
        QIcon — qtawesome 미설치 시 빈 QIcon

    Example::
        act = menu.addAction("새로고침")
        act.setIcon(icon(ICON.REFRESH, color="#ffffff"))
    """
    entry = ICON_MAPPING.get(key)
    if entry is None:
        from PyQt6.QtGui import QIcon

        return QIcon()

    qta_name = entry[0]
    try:
        import qtawesome as qta  # type: ignore[import]

        options: dict = {}
        if color:
            options["color"] = color
        options.update(kwargs)
        return qta.icon(qta_name, **options)
    except ImportError:
        from PyQt6.QtGui import QIcon

        return QIcon()
    except Exception:
        import logging

        from PyQt6.QtGui import QIcon

        logging.getLogger(__name__).warning(
            "icon_map: failed to load icon key=%s qta_name=%s",
            key,
            qta_name,
            exc_info=True,
        )
        return QIcon()


def emoji_for(key: str) -> str:
    """
    아이콘 키에 해당하는 원래 이모지 문자열을 반환합니다.
    교체 작업 중 폴백 또는 참조용으로 사용합니다.
    """
    entry = ICON_MAPPING.get(key)
    return entry[1] if entry else ""
