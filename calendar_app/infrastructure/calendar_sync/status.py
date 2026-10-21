# -*- coding: utf-8 -*-
"""Account-scoped, safe calendar diagnostics shared by controllers and views."""

import json
import re

from calendar_app.application.calendar_sync_contract import CalendarSyncError

_MAX_STATE_CHARS = 131072
_ERROR_CODE = re.compile(r"[a-z][a-z0-9_]{0,79}\Z")


def _safe_errors(errors):
    if not isinstance(errors, dict):
        return {}
    return {
        key: code
        for key, code in errors.items()
        if isinstance(key, str)
        and key.startswith(("outlook::", "caldav::"))
        and len(key) <= 256
        and not any(ord(char) < 32 for char in key)
        and isinstance(code, str)
        and _ERROR_CODE.fullmatch(code)
    }


def save_calendar_errors(settings, prefix, errors):
    account = settings.value(prefix + "account_id", "", type=str)
    payload = json.dumps({"account": account, "errors": _safe_errors(errors)})
    if len(payload) > _MAX_STATE_CHARS:
        raise CalendarSyncError("operation_failed")
    settings.setValue(prefix + "calendar_errors", payload)


def load_calendar_errors(settings, prefix):
    raw = settings.value(prefix + "calendar_errors", "", type=str)
    if not isinstance(raw, str) or len(raw) > _MAX_STATE_CHARS:
        return {}
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    account = settings.value(prefix + "account_id", "", type=str)
    if not account or not isinstance(payload, dict) or payload.get("account") != account:
        return {}
    return _safe_errors(payload.get("errors"))


def save_calendar_discovery_errors(settings, prefix, errors):
    """A refreshed calendar list only resolves access errors, not invalid events."""
    current = {
        key: code
        for key, code in load_calendar_errors(settings, prefix).items()
        if code != "calendar_access_lost"
    }
    current.update(_safe_errors(errors))
    save_calendar_errors(settings, prefix, current)
