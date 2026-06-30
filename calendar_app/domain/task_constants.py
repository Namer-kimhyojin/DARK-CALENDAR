# task_constants.py
# 중요도(priority)와 상태(status)에 대한 이모티콘·텍스트 정의를 한 곳에서 관리합니다.
# 이 파일만 수정하면 캘린더, 오늘 일정, 일반업무, 지시/협조사항 전체에 일괄 적용됩니다.
# QSettings에 커스텀 값이 저장된 경우 해당 값이 우선 적용됩니다.

# ── 기본값 (DEFAULT) ─────────────────────────────────────────────
from calendar_app.domain.i18n import t

_DEFAULT_PRIORITY_ICON = {
    "urgent": "🚨",
    "high": "⭐",
    "normal": "⚡",
    "low": "📌",
}
_DEFAULT_PRIORITY_TEXT = {
    "urgent": t("priority.urgent", "긴급"),
    "high": t("priority.high", "높음"),
    "normal": t("priority.normal", "보통"),
    "low": t("priority.low", "낮음"),
}
_DEFAULT_STATUS_ICON = {
    "pending": "📅",
    "in_progress": "⏳",
    "completed": "✅",
    "deferred": "⏸️",
}
_DEFAULT_STATUS_TEXT = {
    "pending": t("status.pending", "예정"),
    "in_progress": t("status.in_progress", "진행중"),
    "completed": t("status.completed", "완료"),
    "deferred": t("status.deferred", "보류"),
}

# ── 내장 프리셋 ────────────────────────────────────────────────────
# 키는 고정 영문 ID("default", "business", "minimal").
# 버튼 표시 이름은 다이얼로그에서 t("dialog.label_settings.builtin_presets.<key>") 로 번역.
# 아이콘/텍스트 값은 앱 시작 후 get_builtin_presets() 를 통해 그 시점 번역을 사용.
BUILTIN_PRESETS = {
    "default": {
        "priority": {
            "urgent": {"icon": "🚨"},
            "high": {"icon": "⭐"},
            "normal": {"icon": "⚡"},
            "low": {"icon": "📌"},
        },
        "status": {
            "pending": {"icon": "📅"},
            "in_progress": {"icon": "⏳"},
            "completed": {"icon": "✅"},
            "deferred": {"icon": "⏸️"},
        },
    },
    "business": {
        "priority": {
            "urgent": {"icon": "🔥"},
            "high": {"icon": "⭐"},
            "normal": {"icon": "⚡"},
            "low": {"icon": "📌"},
        },
        "status": {
            "pending": {"icon": "📌"},
            "in_progress": {"icon": "⏳"},
            "completed": {"icon": "✅"},
            "deferred": {"icon": "⏸️"},
        },
    },
    "minimal": {
        "priority": {
            "urgent": {"icon": "🔴"},
            "high": {"icon": "🟡"},
            "normal": {"icon": "🟢"},
            "low": {"icon": "⚪"},
        },
        "status": {
            "pending": {"icon": "◻️"},
            "in_progress": {"icon": "⏳"},
            "completed": {"icon": "✅"},
            "deferred": {"icon": "⏸️"},
        },
    },
}


def get_builtin_presets() -> dict:
    """BUILTIN_PRESETS에 현재 번역된 text 값을 합쳐 반환 (런타임 호출용)."""
    _prio_keys = ("urgent", "high", "normal", "low")
    _prio_i18n = ("priority.urgent", "priority.high", "priority.normal", "priority.low")
    _stat_keys = ("pending", "in_progress", "completed", "deferred")
    _stat_i18n = ("status.pending", "status.in_progress", "status.completed", "status.deferred")

    result = {}
    for preset_key, preset_data in BUILTIN_PRESETS.items():
        entry = {"priority": {}, "status": {}}
        for key, i18n_key in zip(_prio_keys, _prio_i18n, strict=False):
            icon = preset_data["priority"][key]["icon"]
            entry["priority"][key] = {"icon": icon, "text": t(i18n_key, key)}
        for key, i18n_key in zip(_stat_keys, _stat_i18n, strict=False):
            icon = preset_data["status"][key]["icon"]
            entry["status"][key] = {"icon": icon, "text": t(i18n_key, key)}
        result[preset_key] = entry
    return result


# ── 런타임 dict (load_custom_labels 후 실제 사용되는 값) ──────────
PRIORITY_ICON = dict(_DEFAULT_PRIORITY_ICON)
PRIORITY_TEXT = dict(_DEFAULT_PRIORITY_TEXT)

STATUS_ICON = {
    "pending": "📅",
    "in_progress": "⏳",
    "completed": "✅",
    "deferred": "⏸️",
    # 레거시 값 (오버라이드 대상 아님)
    "done": "✅",
    "overdue": "⏰",
    "canceled": "❌",
}
STATUS_TEXT = dict(_DEFAULT_STATUS_TEXT)

# ── 파생 상수 (아래 _rebuild_derived_constants 로 자동 갱신됨) ────
PRIORITY_LABEL: dict = {}
STATUS_LABEL: dict = {}
PRIORITY_COMBO_ITEMS: list = []
PRIORITY_MENU_ITEMS: list = []
STATUS_COMBO_ITEMS: list = []
STATUS_MENU_ITEMS: list = []
STATUS_FILTER_ITEMS: list = []


def _rebuild_derived_constants():
    """PRIORITY_LABEL, STATUS_LABEL, *_COMBO_ITEMS 등을 현재 icon/text에서 재빌드."""
    global PRIORITY_LABEL, STATUS_LABEL
    global PRIORITY_COMBO_ITEMS, PRIORITY_MENU_ITEMS
    global STATUS_COMBO_ITEMS, STATUS_MENU_ITEMS, STATUS_FILTER_ITEMS

    def _lbl(icon, text):
        return f"{icon} {text}".strip() if icon else text

    PRIORITY_LABEL.clear()
    PRIORITY_LABEL.update(
        {
            "urgent": _lbl(PRIORITY_ICON["urgent"], PRIORITY_TEXT["urgent"]),
            "high": _lbl(PRIORITY_ICON["high"], PRIORITY_TEXT["high"]),
            "normal": _lbl(PRIORITY_ICON["normal"], PRIORITY_TEXT["normal"]),
            "low": _lbl(PRIORITY_ICON["low"], PRIORITY_TEXT["low"]),
        }
    )

    STATUS_LABEL.clear()
    STATUS_LABEL.update(
        {
            "pending": _lbl(STATUS_ICON["pending"], STATUS_TEXT["pending"]),
            "in_progress": _lbl(STATUS_ICON["in_progress"], STATUS_TEXT["in_progress"]),
            "completed": _lbl(STATUS_ICON["completed"], STATUS_TEXT["completed"]),
            "deferred": _lbl(STATUS_ICON["deferred"], STATUS_TEXT["deferred"]),
            # 레거시
            "done": _lbl(STATUS_ICON["completed"], STATUS_TEXT["completed"]),
            "overdue": _lbl(STATUS_ICON["overdue"], t("status.overdue", "지연")),
            "canceled": _lbl(STATUS_ICON["canceled"], t("status.canceled", "취소")),
        }
    )

    PRIORITY_COMBO_ITEMS[:] = [
        (PRIORITY_LABEL["low"], "low"),
        (PRIORITY_LABEL["normal"], "normal"),
        (PRIORITY_LABEL["high"], "high"),
        (PRIORITY_LABEL["urgent"], "urgent"),
    ]
    PRIORITY_MENU_ITEMS[:] = [
        (PRIORITY_LABEL["urgent"], "urgent"),
        (PRIORITY_LABEL["high"], "high"),
        (PRIORITY_LABEL["normal"], "normal"),
        (PRIORITY_LABEL["low"], "low"),
    ]
    STATUS_COMBO_ITEMS[:] = [
        (STATUS_LABEL["pending"], "pending"),
        (STATUS_LABEL["in_progress"], "in_progress"),
        (STATUS_LABEL["completed"], "completed"),
        (STATUS_LABEL["deferred"], "deferred"),
    ]
    STATUS_MENU_ITEMS[:] = list(STATUS_COMBO_ITEMS)

    status_all = t("status.all_states", "모든 상태")

    STATUS_FILTER_ITEMS[:] = [status_all] + [label for label, _ in STATUS_COMBO_ITEMS]


# 모듈 로드 시 초기 빌드
_rebuild_derived_constants()


# ── QSettings 연동 ─────────────────────────────────────────────────
def load_custom_labels():
    """앱 시작 시 또는 설정 저장 후 QSettings 커스텀 값을 모듈 dict에 로드."""
    try:
        from PyQt6.QtCore import QSettings

        s = QSettings("kimhyojin", "Dark Calendar")

        for key in list(_DEFAULT_PRIORITY_ICON):
            icon = s.value(f"custom_priority_icon_{key}")
            text = s.value(f"custom_priority_text_{key}")
            PRIORITY_ICON[key] = icon if icon else _DEFAULT_PRIORITY_ICON[key]
            PRIORITY_TEXT[key] = text if text else _DEFAULT_PRIORITY_TEXT[key]

        for key in list(_DEFAULT_STATUS_ICON):
            icon = s.value(f"custom_status_icon_{key}")
            text = s.value(f"custom_status_text_{key}")
            STATUS_ICON[key] = icon if icon else _DEFAULT_STATUS_ICON[key]
            STATUS_TEXT[key] = text if text else _DEFAULT_STATUS_TEXT[key]

        _rebuild_derived_constants()
    except Exception:
        pass


def save_custom_labels(priority_data: dict, status_data: dict):
    """
    priority_data = {"urgent": {"icon": "🔥", "text": "긴급"}, ...}
    status_data   = {"pending": {"icon": "📌", "text": "예정"}, ...}
    저장 후 모듈 dict를 즉시 갱신합니다.
    """
    try:
        from PyQt6.QtCore import QSettings

        s = QSettings("kimhyojin", "Dark Calendar")

        for key, vals in priority_data.items():
            s.setValue(f"custom_priority_icon_{key}", vals["icon"])
            s.setValue(f"custom_priority_text_{key}", vals["text"])

        for key, vals in status_data.items():
            s.setValue(f"custom_status_icon_{key}", vals["icon"])
            s.setValue(f"custom_status_text_{key}", vals["text"])

        load_custom_labels()
    except Exception:
        pass


def reset_custom_labels():
    """QSettings에서 커스텀 값을 모두 삭제하고 기본값으로 복구."""
    try:
        from PyQt6.QtCore import QSettings

        s = QSettings("kimhyojin", "Dark Calendar")
        for key in _DEFAULT_PRIORITY_ICON:
            s.remove(f"custom_priority_icon_{key}")
            s.remove(f"custom_priority_text_{key}")
        for key in _DEFAULT_STATUS_ICON:
            s.remove(f"custom_status_icon_{key}")
            s.remove(f"custom_status_text_{key}")
        load_custom_labels()
    except Exception:
        pass


def get_current_labels() -> dict:
    """현재 적용 중인 icon/text 값을 반환 (설정 다이얼로그 초기화용)."""
    return {
        "priority": {
            key: {"icon": PRIORITY_ICON[key], "text": PRIORITY_TEXT[key]}
            for key in ("urgent", "high", "normal", "low")
        },
        "status": {
            key: {"icon": STATUS_ICON[key], "text": STATUS_TEXT[key]}
            for key in ("pending", "in_progress", "completed", "deferred")
        },
    }


def save_user_preset(name: str, priority_data: dict, status_data: dict):
    """사용자 프리셋을 QSettings에 JSON으로 저장."""
    import json

    try:
        from PyQt6.QtCore import QSettings

        s = QSettings("kimhyojin", "Dark Calendar")
        raw = s.value("label_user_presets", "[]")
        presets = json.loads(raw) if raw else []
        # 동일 이름 있으면 업데이트
        presets = [p for p in presets if p.get("name") != name]
        presets.append({"name": name, "priority": priority_data, "status": status_data})
        s.setValue("label_user_presets", json.dumps(presets, ensure_ascii=False))
    except Exception:
        pass


def delete_user_preset(name: str):
    """사용자 프리셋 삭제."""
    import json

    try:
        from PyQt6.QtCore import QSettings

        s = QSettings("kimhyojin", "Dark Calendar")
        raw = s.value("label_user_presets", "[]")
        presets = json.loads(raw) if raw else []
        presets = [p for p in presets if p.get("name") != name]
        s.setValue("label_user_presets", json.dumps(presets, ensure_ascii=False))
    except Exception:
        pass


def get_user_presets() -> list:
    """사용자 저장 프리셋 목록 반환."""
    import json

    try:
        from PyQt6.QtCore import QSettings

        s = QSettings("kimhyojin", "Dark Calendar")
        raw = s.value("label_user_presets", "[]")
        return json.loads(raw) if raw else []
    except Exception:
        return []


# ── 편의 함수 ──────────────────────────────────────────────────────
def priority_icon(priority: str) -> str:
    """priority 값 → 아이콘 반환. 알 수 없는 값은 빈 문자열로 처리."""
    return PRIORITY_ICON.get(priority, "")


def priority_label(priority: str) -> str:
    """priority 값 → '아이콘 텍스트' 반환."""
    return PRIORITY_LABEL.get(priority, t("priority.normal", "보통"))


def status_icon(status: str) -> str:
    """status 값 → 아이콘 반환."""
    return STATUS_ICON.get(status, "")


def status_label(status: str) -> str:
    """status 값 → '아이콘 텍스트' 반환."""
    return STATUS_LABEL.get(status, f"[{status}]")
