# -*- coding: utf-8 -*-
"""One URL and error contract for ICS subscription entry points."""

from urllib.parse import urlsplit, urlunsplit

ICS_ERRORS = {
    "invalid_timezone",
    "invalid_calendar_timezone",
    "dependency_unavailable",
    "network_unavailable",
    "invalid_calendar_data",
    "response_too_large",
    "operation_failed",
    "invalid_event_time",
    "duplicate_remote_event",
    "too_many_events",
    "invalid_recurrence",
    "calendar_access_lost",
    "invalid_subscription_url",
    "ics_fetch_failed",
    "ics_access_denied",
    "ics_not_found",
    "ics_rate_limited",
    "ics_server_error",
}


def normalize_subscription_url(value):
    """Normalize webcal and URL identity without modifying signed query strings."""
    value = str(value or "").strip()
    if any(ord(char) < 32 or char.isspace() for char in value):
        raise ValueError("invalid_subscription_url")
    try:
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        if scheme == "webcal":
            scheme = "https"
        if (
            scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("invalid_subscription_url")
        port = parsed.port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError("invalid_subscription_url")
        host = parsed.hostname.lower()
        if ":" in host:
            host = f"[{host}]"
        if port and port != (443 if scheme == "https" else 80):
            host += f":{port}"
        return urlunsplit((scheme, host, parsed.path or "/", parsed.query, ""))
    except ValueError:
        raise ValueError("invalid_subscription_url") from None


def subscription_errors(settings):
    raw = settings.value("sync_ics_error_codes", {})
    errors = {
        str(key): code if isinstance(code, str) and code in ICS_ERRORS else "operation_failed"
        for key, code in (raw.items() if isinstance(raw, dict) else [])
    }
    failed = settings.value("sync_ics_failed_ids", [])
    if isinstance(failed, str):
        failed = [failed]
    if isinstance(failed, (list, tuple)):
        for key in failed:
            errors.setdefault(str(key), "ics_fetch_failed")
    return errors
