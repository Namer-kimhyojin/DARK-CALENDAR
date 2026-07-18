"""Shared primitives for Google sync modules."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def _setting_value(settings, key, default=None):
    if settings is None:
        return default
    if hasattr(settings, "value"):
        try:
            return settings.value(key, default)
        except Exception:
            return default
    if isinstance(settings, dict):
        return settings.get(key, default)
    return getattr(settings, key, default)


def _coerce_bool_setting(value, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off", ""}:
            return False
    return bool(value)


def infer_initial_gcal_enabled(settings=None) -> bool:
    """Infer a safe first-run Google sync default.

    Fresh installs should start local-only. Existing users that already have
    Google auth or a bound non-primary calendar should keep sync enabled.
    """
    explicit = _setting_value(settings, "gcal_enabled", None)
    if explicit is not None:
        return _coerce_bool_setting(explicit, default=False)

    try:
        from calendar_app.app_paths import TOKEN_PATH

        if os.path.exists(TOKEN_PATH):
            return True
    except Exception:
        pass

    for key in ("gcal_calendar_id", "gcal_bound_calendar_id"):
        raw = str(_setting_value(settings, key, "") or "").strip()
        if raw and raw != "primary":
            return True

    return False


def is_gcal_enabled(settings, default: bool | None = None) -> bool:
    explicit = _setting_value(settings, "gcal_enabled", None)
    if explicit is None:
        if default is None:
            default = infer_initial_gcal_enabled(settings)
        return bool(default)
    return _coerce_bool_setting(explicit, default=bool(default) if default is not None else False)


def ensure_gcal_startup_defaults(settings, *, suppress_first_run_prompt: bool = True) -> bool:
    """Persist non-invasive defaults for startup UX.

    Returns the effective Google sync enabled state after normalization.
    """
    enabled = infer_initial_gcal_enabled(settings)

    if _setting_value(settings, "gcal_enabled", None) is None and hasattr(settings, "setValue"):
        settings.setValue("gcal_enabled", "true" if enabled else "false")

    if (
        suppress_first_run_prompt
        and _setting_value(settings, "gcal_setup_wizard_shown", None) is None
        and hasattr(settings, "setValue")
    ):
        settings.setValue("gcal_setup_wizard_shown", "true")

    return is_gcal_enabled(settings, default=enabled)


def get_default_gcal_calendar_id() -> str:
    """DB의 기본 캘린더(is_default=1) 중 gcal 타입의 gcal_calendar_id 를 반환한다.

    - gcal 기본 캘린더가 있으면 그 gcal_calendar_id 반환
    - 없으면 "primary" 반환 (Google API 호환 fallback)
    """
    try:
        from calendar_app.infrastructure.db.calendar_repo import (
            get_default_calendar,
            list_calendars,
        )

        # 1순위: is_default=1 인 gcal 캘린더
        default_cal = get_default_calendar()
        if default_cal and default_cal.get("type") == "gcal":
            gcal_id = str(default_cal.get("gcal_calendar_id") or "").strip()
            if gcal_id and gcal_id != "primary":
                return gcal_id
        # 2순위: gcal 캘린더 중 첫 번째 writable (is_active=1)
        for cal in list_calendars(include_inactive=False):
            if cal.get("type") == "gcal":
                gcal_id = str(cal.get("gcal_calendar_id") or "").strip()
                if gcal_id and gcal_id != "primary":
                    return gcal_id
    except Exception:
        pass
    return "primary"


def normalize_calendar_id(calendar_id) -> str:
    value = str(calendar_id or "").strip()
    return value or "primary"


def _default_primary_summary() -> str:
    try:
        from calendar_app.infrastructure.db.calendar_repo import get_default_calendar

        default_cal = get_default_calendar()
        gcal_id = str((default_cal or {}).get("gcal_calendar_id") or "").strip().lower()
        if (
            default_cal
            and default_cal.get("type") == "gcal"
            and gcal_id == "primary"
            and default_cal.get("name")
        ):
            return default_cal["name"]
    except Exception:
        pass
    return "Primary"


def build_calendar_source_summary_map(include_inactive: bool = True) -> dict[str, str]:
    """Build source calendar id -> display summary map from local DB sources."""
    summary_map: dict[str, str] = {}

    # Legacy subscription table.
    try:
        from calendar_app.infrastructure.db import task_repo as _task_repo

        for row in _task_repo.list_gcal_subscriptions(include_inactive=include_inactive):
            cid = normalize_calendar_id(row.get("calendar_id"))
            summary = str(row.get("summary") or cid).strip() or cid
            summary_map[cid] = summary
    except Exception:
        logger.exception("Failed to load Google subscription summary map")

    # New calendar table (preferred).
    try:
        from calendar_app.infrastructure.db.calendar_repo import list_calendars

        for cal in list_calendars(include_inactive=include_inactive):
            if cal.get("type") != "gcal":
                continue
            gcal_id = normalize_calendar_id(cal.get("gcal_calendar_id"))
            if gcal_id and cal.get("name"):
                summary_map[gcal_id] = cal["name"]
    except Exception:
        logger.exception("Failed to load calendar table summary map")

    # "primary" 키가 아직 없으면 DB의 기본 gcal 캘린더 이름으로 채운다.
    if "primary" not in summary_map:
        summary_map["primary"] = _default_primary_summary()
    return summary_map


def resolve_calendar_source_summary(
    source_calendar_id, summary_map: dict[str, str] | None = None
) -> str | None:
    """Resolve display summary for source calendar id."""
    raw = str(source_calendar_id or "").strip()
    if raw.startswith("gcal::"):
        raw = raw[len("gcal::") :]
    if not raw:
        return None

    source_calendar_id = normalize_calendar_id(raw)
    if summary_map is None:
        summary_map = build_calendar_source_summary_map(include_inactive=True)
    if source_calendar_id in summary_map:
        return summary_map[source_calendar_id]
    if source_calendar_id == "primary":
        return _default_primary_summary()
    return source_calendar_id


def resolve_task_target_calendar_id(task, default_calendar_id: str | None = None) -> str | None:
    """
    Resolve target Google calendar id from a task-like dict.
    Returns None for explicit non-gcal namespaces (local::/ics::/etc).

    default_calendar_id 가 None 이면 DB 기본 gcal 캘린더를 자동으로 사용한다.
    """
    task = task or {}
    raw = task.get("gcal_target_calendar_id") or task.get("gcal_source_calendar_id")
    if raw:
        return normalize_calendar_id(raw)

    cal_id = str(task.get("calendar_id") or "").strip()
    if cal_id.startswith("gcal::"):
        return normalize_calendar_id(cal_id[len("gcal::") :])

    if "::" in cal_id:
        namespace = cal_id.split("::", 1)[0].strip().lower()
        if namespace and namespace != "gcal":
            return None

    if default_calendar_id is False:
        return None

    # default_calendar_id 가 명시되지 않으면 DB 기본 gcal 캘린더 사용
    if default_calendar_id is None:
        return get_default_gcal_calendar_id()
    if default_calendar_id == "primary":
        return "primary"
    return normalize_calendar_id(default_calendar_id)
