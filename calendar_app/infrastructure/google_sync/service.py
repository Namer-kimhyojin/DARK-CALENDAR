# -*- coding: utf-8 -*-
from dataclasses import dataclass
import datetime
import errno
import json
import logging
import math
import os.path
import socket
import ssl
import threading
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)


from calendar_app.app_paths import CREDENTIALS_PATH, TOKEN_PATH  # noqa: E402
from calendar_app.infrastructure.google_sync.common import (  # noqa: E402
    google_summary_for_task_name,
    sync_time_zone,
    untitled_event_name,
)
from calendar_app.infrastructure.google_sync.oauth import (  # noqa: E402
    GoogleAuthError,
    check_auth_cancelled,
    load_desktop_client_config,
    run_desktop_auth,
)
from calendar_app.shared.datetime_utils import (  # noqa: E402
    _extract_tz_offset,
    parse_datetime_str,
    timezone_offset_for_datetime_str,
    timezone_offset_for_name,
    to_iso_with_tz,
)

try:
    from google.auth import exceptions as google_auth_exceptions
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    HAS_GOOGLE_API = True


except ImportError:
    google_auth_exceptions = None

    Request = None

    Credentials = None

    InstalledAppFlow = None

    build = None

    HttpError = Exception

    HAS_GOOGLE_API = False


SCOPES = ["https://www.googleapis.com/auth/calendar"]


# Plain OSError codes for an unavailable network/host (POSIX and WinSock).
_NETWORK_UNAVAILABLE_ERRNOS = frozenset(
    code
    for code in (
        getattr(errno, "ENETDOWN", None),
        getattr(errno, "ENETUNREACH", None),
        getattr(errno, "EHOSTDOWN", None),
        getattr(errno, "EHOSTUNREACH", None),
        10050,  # WSAENETDOWN
        10051,  # WSAENETUNREACH
        10064,  # WSAEHOSTDOWN
        10065,  # WSAEHOSTUNREACH
    )
    if code is not None
)


def _is_network_unavailable_error(error) -> bool:
    if isinstance(error, (ConnectionError, TimeoutError, socket.gaierror, ssl.SSLError)):
        return True
    if isinstance(error, OSError) and error.errno in _NETWORK_UNAVAILABLE_ERRNOS:
        return True
    # httplib2 (the Calendar API transport) wraps DNS failures while offline in
    # ServerNotFoundError, which is not a ConnectionError subclass.
    return type(error).__name__ == "ServerNotFoundError" and type(error).__module__.startswith(
        "httplib2"
    )


def _google_refresh_failure_kind(error):
    """Only a confirmed OAuth rejection should send an existing user to sign-in."""
    if _is_network_unavailable_error(error):
        return "network_unavailable"
    if google_auth_exceptions is not None:
        if isinstance(error, google_auth_exceptions.TransportError):
            return "network_unavailable"
        if isinstance(error, google_auth_exceptions.RefreshError):
            # google-auth supplies the parsed OAuth response separately from its
            # free-form message. Never parse/log descriptions or credential URLs.
            code = next((arg.get("error") for arg in error.args if isinstance(arg, dict)), None)
            if not isinstance(code, str):
                code = None
            if code in {"invalid_grant", "access_denied", "invalid_scope"}:
                return "auth_required"
            if code in {"invalid_client", "unauthorized_client"}:
                return "auth_client_invalid"
            if error.retryable or code in {"server_error", "temporarily_unavailable"}:
                return "network_unavailable"
    return "operation_failed"


def is_google_rate_limit_error(status, error=None) -> bool:
    """Distinguish temporary Calendar API quotas from other HTTP 403 failures."""
    if status == 429:
        return True
    if status != 403:
        return False
    reasons = {"rateLimitExceeded", "userRateLimitExceeded"}
    content = getattr(error, "content", None)
    if content is not None:
        try:
            payload = json.loads(content)
            return any(
                item.get("reason") in reasons
                for item in payload.get("error", {}).get("errors", [])
                if isinstance(item, dict)
            )
        except (ValueError, TypeError, AttributeError):
            return False
    # Engine results contain the safe error text already saved by the service.
    message = str(error or "").lower()
    return any(reason.lower() in message for reason in reasons)


def is_google_insufficient_scope_error(status, error) -> bool:
    if status != 403:
        return False
    try:
        payload = json.loads(getattr(error, "content", None)).get("error", {})
        return any(
            item.get("reason") == reason
            for field, reason in (
                ("errors", "insufficientPermissions"),
                ("details", "ACCESS_TOKEN_SCOPE_INSUFFICIENT"),
            )
            for item in (payload.get(field) or ())
            if isinstance(item, dict)
        )
    except (ValueError, TypeError, AttributeError):
        return False


def _google_error_code(kind, error, status=None):
    """Keep remote payloads/URLs out of stored errors and diagnostic messages."""
    if is_google_rate_limit_error(status, error):
        return "rateLimitExceeded"
    if isinstance(error, ValueError) and str(error).startswith(
        (
            "invalid_google_",
            "incomplete_google_",
            "missing_google_",
            "ambiguous_google_",
            "duplicate_google_",
        )
    ):
        return "invalid_google_event"
    if isinstance(error, str) and error in {
        "token_write_failed",
        "empty_response",
        "missing_id_in_response",
        "existing_create_not_verified",
    }:
        return error
    if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599:
        return f"http_{status}"
    return kind


@dataclass
class GoogleEvent:
    id: str

    summary: str

    description: str | None

    start_time: str

    end_time: str

    location: str | None

    status: str = "confirmed"

    color_id: str | None = None

    updated_time: str | None = None

    source_calendar_id: str | None = None

    # 반복 일정 지원 (item 2)
    recurring_event_id: str | None = None  # 부모 시리즈 ID (recurringEventId)
    recurrence: list | None = None  # ["RRULE:FREQ=WEEKLY;..."] — 마스터 이벤트에만 존재
    original_start_time: str | None = None  # 이 인스턴스의 원래 시작시각 (instance identity)

    # 참석자 / 첨부파일 (item 9)
    attendees: list | None = None  # [{"email", "displayName", "responseStatus"}]
    attachments: list | None = None  # [{"fileUrl", "title", "mimeType"}]

    # extendedProperties.private dict (item 10 — completion guard)
    extended_properties_private: dict | None = None


def prepare_calendar_sync_service(
    existing_service=None, calendar_id="primary", time_zone=None, reset_auth=False
):
    """Return a sync service configured for the requested calendar/timezone."""

    time_zone = time_zone or sync_time_zone(None)
    service = existing_service or CalendarSyncService(calendar_id=calendar_id, time_zone=time_zone)

    service.calendar_id = service._normalize_calendar_id(calendar_id)

    service.time_zone = time_zone

    if reset_auth:
        service.is_authenticated = False

        service.service = None

    return service


def _supports_scopes(scopes) -> bool:
    if isinstance(scopes, str):
        scopes = scopes.split()
    return isinstance(scopes, (list, tuple, set, frozenset)) and set(SCOPES).issubset(scopes)


def _credentials_support_scopes(creds) -> bool:
    granted = getattr(creds, "granted_scopes", None)
    if granted is None:
        granted = getattr(creds, "scopes", None)
    return _supports_scopes(granted)


class CalendarSyncService:
    def __init__(self, calendar_id="primary", time_zone=None):
        self.is_authenticated = False

        self.service = None

        self.calendar_id = self._normalize_calendar_id(calendar_id)

        self.time_zone = time_zone or sync_time_zone(None)

        # googleapiclient/httplib2 service is not thread-safe.

        # Serialize API access across UI sync timer + background workers.

        self._service_lock = threading.RLock()

        self.last_error_kind = None

        self.last_error_status = None

        self.last_error_message = None

        self._pending_token_json = None
        self._account_identity_mismatch = False
        self._account_identity_error_kind = "account_mismatch"

        # 마지막 429 응답의 Retry-After 값(초). engine.py 로깅용.
        self._last_retry_after_secs: float = 0.0

    def _clear_auth_state(self):
        self.is_authenticated = False

        self.service = None

    def _clear_last_error(self):
        self.last_error_kind = None

        self.last_error_status = None

        self.last_error_message = None

    def _set_last_error(self, kind: str, message, status: int | None = None):
        self.last_error_kind = kind

        self.last_error_status = status

        self.last_error_message = _google_error_code(kind, message, status)

    def _remote_writes_allowed(self):
        if self._account_identity_mismatch:
            self._set_last_error(
                self._account_identity_error_kind, self._account_identity_error_kind
            )
            return False
        return True

    def _default_tz_offset(self) -> str:
        return timezone_offset_for_name(self.time_zone)

    def _normalize_calendar_id(self, calendar_id: str | None = None) -> str:
        value = str(calendar_id if calendar_id is not None else self.calendar_id or "").strip()

        if not value:
            logger.warning("GCal calendar_id is empty; falling back to primary")

            value = "primary"

        return value

    def _tz_offset_for_value(self, dt_str: str) -> str:
        return timezone_offset_for_datetime_str(
            dt_str, self.time_zone, fallback=self._default_tz_offset()
        )

    def _is_transient_error(self, exc: Exception) -> bool:
        if HAS_GOOGLE_API and isinstance(exc, HttpError):
            status = getattr(getattr(exc, "resp", None), "status", None)

            if is_google_rate_limit_error(status, exc):
                return True

            if status in {408, 409, 425, 429, 500, 502, 503, 504}:
                return True

            if status == 400:
                msg = str(exc).lower()

                if "sequence" in msg:
                    return True

            return False

        if _google_refresh_failure_kind(exc) == "network_unavailable":
            return True

        message = str(exc).lower()

        markers = [
            "timed out",
            "timeout",
            "bad record type",
            "wrong version number",
            "decryption failed",
            "bad record mac",
            "connection reset",
            "ssl",
            "tls",
        ]

        return any(marker in message for marker in markers)

    def _get_retry_after_secs(self, exc: Exception, default: float) -> float:
        """429 HttpError 응답에서 Retry-After 헤더 값(초)을 추출한다.

        없거나 파싱 불가 시 default 반환. 60초 상한 및 epoch timestamp 감지 포함.
        """
        try:
            resp = getattr(exc, "resp", None)
            if resp is None:
                return default
            # httplib2 헤더는 소문자로 정규화됨
            raw = (
                resp.get("retry-after") or resp.get("Retry-After") or resp.get("x-ratelimit-reset")
            )
            if raw is None:
                return default
            secs = float(raw)
            # epoch timestamp(>3600) 인 경우 무시하고 default 사용
            if not math.isfinite(secs) or secs <= 0 or secs > 3600:
                return default
            return min(secs, 60.0)
        except Exception:
            return default

    def _execute_request(self, request_callable, retries: int = 3, retry_delay: float = 1.0):
        last_exc = None

        for attempt in range(retries + 1):
            try:
                self._clear_last_error()

                with self._service_lock:
                    return request_callable()

            except Exception as exc:
                last_exc = exc

                if attempt >= retries or not self._is_transient_error(exc):
                    raise

                # Temporary quotas can use 403 or 429; honor Retry-After for either.
                status = getattr(getattr(exc, "resp", None), "status", None)
                is_rate_limited = (
                    HAS_GOOGLE_API
                    and isinstance(exc, HttpError)
                    and is_google_rate_limit_error(status, exc)
                )
                if is_rate_limited:
                    wait = self._get_retry_after_secs(exc, retry_delay * (2**attempt))
                    self._last_retry_after_secs = wait
                    logger.warning(
                        "GCal %s rate-limit (attempt %d/%d), honouring Retry-After=%.0fs",
                        status,
                        attempt + 1,
                        retries,
                        wait,
                    )
                else:
                    import random

                    # 지수 백오프: delay * (2^attempt) + jitter (0.1 ~ 1.0초)
                    wait = retry_delay * (2**attempt) + random.uniform(0.1, 1.0)
                    logger.warning(
                        "GCal transient error (attempt %d/%d), retrying in %.1fs (exponential backoff): %s",
                        attempt + 1,
                        retries,
                        wait,
                        _google_error_code("request_failed", exc, status),
                    )

                time.sleep(wait)

        raise last_exc

    def revoke_token(self) -> bool:
        """Google OAuth 토큰을 원격 서버에서 취소(revoke)한다.

        로컬 token.json 삭제는 호출자 담당이며, 이 메서드는 API 호출만 담당한다.
        실패해도 연동 해제 흐름을 차단하지 않도록 비치명적으로 처리한다.
        """
        if not os.path.exists(TOKEN_PATH):
            return True  # 취소할 토큰이 없음
        try:
            import json as _json
            import urllib.request as _urllib_req

            from calendar_app.infrastructure.google_sync.token_store import load_token_json

            token_text = load_token_json()
            if not token_text:
                return True  # 읽을 수 없는 토큰 — 취소할 것 없음
            token_data = _json.loads(token_text)
            # Revoking the refresh token also ends the access tokens it issued;
            # an access token alone expires but leaves the grant usable.
            token = str(
                token_data.get("refresh_token")
                or token_data.get("token")
                or token_data.get("access_token")
                or ""
            ).strip()
            if not token:
                logger.info("revoke_token: no token found in token file; skipping revoke call")
                return True
            from urllib.parse import urlencode

            body = urlencode({"token": token}).encode("utf-8", errors="strict")
            req = _urllib_req.Request(
                "https://oauth2.googleapis.com/revoke",
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            with _urllib_req.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    logger.info("Google OAuth token revoked successfully")
                    return True
                logger.warning("Google OAuth revoke returned HTTP %d", resp.status)
                return False
        except Exception as exc:
            logger.warning(
                "Google OAuth token revocation failed (non-critical): %s",
                _google_error_code("revoke_failed", exc),
            )
            return False

    def authenticate(
        self,
        interactive=True,
        *,
        force_reauth=False,
        is_cancelled=None,
        persist_token=True,
    ) -> bool:
        with self._service_lock:
            if not force_reauth and self.is_authenticated and self.service is not None:
                return True

            self._clear_auth_state()

            self._clear_last_error()

        if not HAS_GOOGLE_API:
            self._set_last_error("auth_modules", "Google Calendar modules are not installed")
            return False

        creds = None
        token_json = None
        self._pending_token_json = None

        try:
            check_auth_cancelled(is_cancelled)
        except GoogleAuthError as exc:
            self._set_last_error(exc.kind, exc.kind)
            return False

        if not force_reauth and os.path.exists(TOKEN_PATH):
            try:
                from calendar_app.infrastructure.google_sync.token_store import load_token_json

                token_text = load_token_json(TOKEN_PATH)
                token_data = json.loads(token_text) if token_text else None
                if isinstance(token_data, dict) and _supports_scopes(token_data.get("scopes")):
                    creds = Credentials.from_authorized_user_info(token_data, SCOPES)
                else:
                    logger.warning("Saved Google token is unreadable or missing required scopes.")

            except (ValueError, TypeError, AttributeError) as exc:
                logger.warning(
                    "Saved Google token could not be validated: %s",
                    _google_error_code("token_load_failed", exc),
                )
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    refresh_request = Request()

                    def bounded_refresh_request(*args, **kwargs):
                        kwargs["timeout"] = 12
                        return refresh_request(*args, **kwargs)

                    creds.refresh(bounded_refresh_request)

                    if not _credentials_support_scopes(creds):
                        logger.warning(
                            "authenticate(non-interactive): refreshed token is missing required scopes; discarding."
                        )
                        creds = None

                except Exception as _refresh_exc:
                    kind = _google_refresh_failure_kind(_refresh_exc)
                    self._set_last_error(kind, kind)
                    logger.warning(
                        "authenticate(non-interactive): token refresh failed: %s",
                        kind,
                    )
                    if kind != "auth_required":
                        # Keep the saved token for the next attempt. A transport
                        # outage must not trigger a browser or a synthetic 401.
                        return False
                    creds = None

            if not creds or not creds.valid:
                if not interactive:
                    self._set_last_error(
                        "auth_required",
                        "A valid Google OAuth token is required for silent authentication",
                        401,
                    )
                    logger.warning(
                        "authenticate(non-interactive): cannot proceed without valid credentials "
                        "(interactive=False). creds_present=%s, creds_valid=%s",
                        creds is not None,
                        getattr(creds, "valid", None),
                    )
                    return False

                if not os.path.exists(CREDENTIALS_PATH):
                    self._set_last_error("auth_client_missing", "credentials.json was not found")
                    return False

                try:
                    config = load_desktop_client_config(CREDENTIALS_PATH)
                    flow = InstalledAppFlow.from_client_config(
                        config, SCOPES, autogenerate_code_verifier=True
                    )
                    creds = run_desktop_auth(flow, is_cancelled=is_cancelled)
                    if not (
                        creds.valid and creds.refresh_token and _credentials_support_scopes(creds)
                    ):
                        raise GoogleAuthError("auth_denied")

                except Exception as exc:
                    kind = exc.kind if isinstance(exc, GoogleAuthError) else "auth"
                    self._set_last_error(kind, "Google authentication failed")
                    return False

            try:
                check_auth_cancelled(is_cancelled)
                token_json = creds.to_json()

            except GoogleAuthError as exc:
                self._set_last_error(exc.kind, "Google authentication cancelled")
                return False
            except (OSError, ValueError, TypeError):
                self._set_last_error("auth_token_write", "token_write_failed")
                return False

        try:
            check_auth_cancelled(is_cancelled)
            with self._service_lock:
                from google_auth_httplib2 import AuthorizedHttp
                import httplib2

                authorized_http = AuthorizedHttp(creds, http=httplib2.Http(timeout=12))
                api = build("calendar", "v3", http=authorized_http, cache_discovery=False)

                check_auth_cancelled(is_cancelled)
                if token_json is not None:
                    if persist_token:
                        from calendar_app.infrastructure.google_sync.token_store import (
                            save_token_json,
                        )

                        try:
                            save_token_json(token_json)
                        except OSError:
                            self._set_last_error("auth_token_write", "token_write_failed")
                            return False
                    else:
                        self._pending_token_json = token_json
                self.service = api
                self.is_authenticated = True

            return True

        except Exception as exc:
            with self._service_lock:
                self._clear_auth_state()

            if isinstance(exc, GoogleAuthError):
                self._set_last_error(exc.kind, "Google authentication cancelled")
            else:
                kind = _google_refresh_failure_kind(exc)
                self._set_last_error(kind, kind, 401 if kind == "auth_required" else None)

            return False

    def fetch_events(
        self,
        start_date_str: str,
        end_date_str: str | None = None,
        calendar_id: str | None = None,
    ) -> list[GoogleEvent] | None:
        if not self.is_authenticated or not self.service:
            self._set_last_error(
                "auth_required", "Google Calendar service is not authenticated", 401
            )
            return None
        self._clear_last_error()

        try:
            tz_offset = self._tz_offset_for_value(start_date_str)
            time_min = f"{start_date_str}T00:00:00{tz_offset}"
            end_base = end_date_str or start_date_str
            time_max = f"{end_base}T23:59:59{self._tz_offset_for_value(end_base)}"
            calendar_id = self._normalize_calendar_id(calendar_id)

            events: list[GoogleEvent] = []
            page_token = None
            seen_page_tokens: set[str] = set()
            max_pages = 200
            fetched_pages = 0

            while True:
                if page_token:
                    page_token_str = str(page_token)
                    if page_token_str in seen_page_tokens:
                        raise RuntimeError(
                            f"Duplicate Google events page token detected: {page_token_str}"
                        )
                    seen_page_tokens.add(page_token_str)

                request_params = {
                    "calendarId": calendar_id,
                    "timeMin": time_min,
                    "timeMax": time_max,
                    "maxResults": 2500,
                    "singleEvents": True,
                    "orderBy": "startTime",
                }
                if page_token:
                    request_params["pageToken"] = page_token

                response = self._execute_request(
                    lambda request_params=request_params: (
                        self.service.events().list(**request_params).execute()
                    )
                )

                page_items, page_token, _ = self._validate_events_page(response)
                events.extend(
                    self._to_google_event(item, source_calendar_id=calendar_id)
                    for item in page_items
                )

                fetched_pages += 1
                if not page_token:
                    break
                if fetched_pages >= max_pages:
                    raise RuntimeError(f"Google events pagination exceeded max pages ({max_pages})")

            return events
        except Exception as exc:
            self._set_events_fetch_error(exc)
            logger.warning("Google request failed (%s)", self.last_error_message)
            return None

    def _set_events_fetch_error(self, exc: Exception) -> None:
        status = getattr(getattr(exc, "resp", None), "status", None)
        kind = _google_refresh_failure_kind(exc)
        if is_google_insufficient_scope_error(status, exc):
            kind = "reauth_required"
        self._set_last_error("fetch" if kind == "operation_failed" else kind, exc, status)

    def fetch_sync_events(
        self,
        sync_token: str | None = None,
        calendar_id: str | None = None,
        event_ids: list[str] | None = None,
    ) -> tuple[list[GoogleEvent] | None, str | None, bool]:
        if not self.is_authenticated or not self.service:
            self._set_last_error(
                "auth_required",
                "Google Calendar service is not authenticated",
                401,
            )
            return None, None, False
        self._clear_last_error()

        resolved_calendar_id = self._normalize_calendar_id(calendar_id)
        params = {
            "calendarId": resolved_calendar_id,
            "maxResults": 2500,
            "singleEvents": True,
            "showDeleted": True,
        }
        if sync_token:
            params["syncToken"] = sync_token

        page_token = None
        next_sync_token = None
        events: list[GoogleEvent] = []
        seen_page_tokens: set[str] = set()
        max_pages = 2000
        fetched_pages = 0

        try:
            if event_ids is not None:
                # Recover only linked events when importing this calendar is off.
                # Feed them through the same validation/conflict transaction as a pull.
                for event_id in dict.fromkeys(event_ids):
                    event = self._execute_request(
                        lambda event_id=event_id: (
                            self.service.events()
                            .get(calendarId=resolved_calendar_id, eventId=event_id)
                            .execute()
                        )
                    )
                    if not isinstance(event, dict) or event.get("id") != event_id:
                        raise ValueError("invalid_google_event_identity")
                    events.append(
                        self._to_google_event(event, source_calendar_id=resolved_calendar_id)
                    )
                return events, None, False
            while True:
                if page_token:
                    page_token_str = str(page_token)
                    if page_token_str in seen_page_tokens:
                        raise ValueError("invalid_google_duplicate_page_token")
                    seen_page_tokens.add(page_token_str)

                request_params = dict(params)
                if page_token:
                    request_params["pageToken"] = page_token

                response = self._execute_request(
                    lambda request_params=request_params: (
                        self.service.events().list(**request_params).execute()
                    )
                )
                page_items, page_token, next_sync_token = self._validate_events_page(
                    response, require_sync_token=True
                )
                events.extend(
                    self._to_google_event(item, source_calendar_id=resolved_calendar_id)
                    for item in page_items
                )

                fetched_pages += 1
                if not page_token:
                    break
                if fetched_pages >= max_pages:
                    raise RuntimeError(f"Google events pagination exceeded max pages ({max_pages})")

            return events, next_sync_token, False

        except Exception as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            if status == 410 and sync_token and event_ids is None:
                self._set_last_error("sync_token_expired", exc, 410)
                logger.info("Google incremental token expired; full resync required")
                return None, None, True
            self._set_events_fetch_error(exc)
            logger.warning(
                "Google events fetch failed (%s); discarding %d partial result(s)",
                self.last_error_message,
                len(events),
            )
            return None, None, False

    def create_metadata_reader(self, *, is_cancelled=None):
        """Use an independent HTTP transport for settings queries and push workers."""
        candidate = CalendarSyncService(calendar_id=self.calendar_id, time_zone=self.time_zone)
        candidate._account_identity_mismatch = self._account_identity_mismatch
        candidate._account_identity_error_kind = self._account_identity_error_kind
        if not candidate.authenticate(
            interactive=False, persist_token=False, is_cancelled=is_cancelled
        ):
            raise GoogleAuthError(candidate.last_error_kind or "reauth_required")
        return candidate

    def list_accessible_calendars(self, *, is_cancelled=None) -> list[dict]:
        if not self.is_authenticated or not self.service:
            return []
        self._clear_last_error()

        calendars: list[dict] = []
        seen_calendar_ids: set[str] = set()
        primary_count = 0
        page_token = None
        seen_page_tokens: set[str] = set()
        max_pages = 200
        fetched_pages = 0

        try:
            while True:
                check_auth_cancelled(is_cancelled)
                if page_token:
                    page_token_str = str(page_token)
                    if page_token_str in seen_page_tokens:
                        raise RuntimeError(
                            f"Duplicate Google calendarList page token detected: {page_token_str}"
                        )
                    seen_page_tokens.add(page_token_str)

                request_params = {
                    "minAccessRole": "reader",
                    "showHidden": False,
                }
                if page_token:
                    request_params["pageToken"] = page_token

                response = self._execute_request(
                    lambda request_params=request_params: (
                        self.service.calendarList().list(**request_params).execute()
                    ),
                    retries=0 if is_cancelled else 3,
                )
                check_auth_cancelled(is_cancelled)
                page_items, page_token, _ = self._validate_events_page(response)
                for item in page_items:
                    calendar = self._to_calendar_list_entry(item)
                    if calendar["id"] in seen_calendar_ids:
                        raise ValueError("duplicate_google_calendar_identity")
                    seen_calendar_ids.add(calendar["id"])
                    if calendar["primary"]:
                        primary_count += 1
                        if primary_count > 1:
                            raise ValueError("ambiguous_google_primary_identity")
                    calendars.append(calendar)
                fetched_pages += 1
                if not page_token:
                    break
                if fetched_pages >= max_pages:
                    raise RuntimeError(
                        f"Google calendarList pagination exceeded max pages ({max_pages})"
                    )

            calendars.sort(
                key=lambda item: (not item.get("primary"), (item.get("summary") or "").lower())
            )
            return calendars

        except GoogleAuthError:
            raise
        except Exception as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            kind = _google_refresh_failure_kind(exc)
            if status == 401 or kind == "auth_required":
                kind, status = "auth_required", 401
            elif is_google_insufficient_scope_error(status, exc):
                kind = "reauth_required"
            elif kind == "operation_failed":
                kind = "calendar_list"
            if kind in {"auth_required", "reauth_required", "auth_client_invalid"}:
                self._clear_auth_state()

            self._set_last_error(kind, exc, status)
            if calendars:
                logger.warning(
                    "GCal calendar list fetch failed mid-page (status=%s) after %d calendar(s); "
                    "discarding the incomplete result: %s",
                    status,
                    len(calendars),
                    self.last_error_message,
                )
                return []

            logger.warning("GCal calendar list fetch failed (%s)", self.last_error_message)
            return []

    @staticmethod
    def _to_calendar_list_entry(item):
        """Keep metadata types intact so malformed values cannot become account evidence."""
        if not isinstance(item, dict):
            raise ValueError("invalid_google_calendar_entry")
        calendar_id = item.get("id")
        if not isinstance(calendar_id, str) or not calendar_id.strip():
            raise ValueError("invalid_google_calendar_identity")
        primary = item.get("primary", False)
        if not isinstance(primary, bool):
            raise ValueError("invalid_google_calendar_primary")
        text_values = {}
        for field in ("summaryOverride", "summary", "timeZone", "accessRole"):
            value = item.get(field)
            if value is not None and not isinstance(value, str):
                raise ValueError("invalid_google_calendar_text")
            text_values[field] = value or ""
        return {
            "id": calendar_id.strip(),
            "summary": text_values["summaryOverride"]
            or text_values["summary"]
            or calendar_id.strip(),
            "timeZone": text_values["timeZone"],
            "accessRole": text_values["accessRole"],
            "primary": primary,
        }

    @staticmethod
    def _validate_events_page(response, *, require_sync_token=False):
        """Reject incomplete or malformed pages before they become a full-sync snapshot."""
        if not isinstance(response, dict):
            raise ValueError("invalid_google_events_page")
        items = response.get("items", [])
        if not isinstance(items, list):
            raise ValueError("invalid_google_events_items")
        page_token = response.get("nextPageToken")
        sync_token = response.get("nextSyncToken")
        for key, value in (("nextPageToken", page_token), ("nextSyncToken", sync_token)):
            if key in response and (not isinstance(value, str) or not value.strip()):
                raise ValueError("invalid_google_events_token")
        if require_sync_token and (
            (page_token and sync_token) or (not page_token and not sync_token)
        ):
            raise ValueError("incomplete_google_events_page")
        return items, page_token, sync_token

    @staticmethod
    def _event_text(event, field, default=""):
        value = event.get(field)
        if value is None:
            return default
        if not isinstance(value, str):
            raise ValueError("invalid_google_event_text")
        return value

    @staticmethod
    def _event_datetime(event, field, *, required=True):
        raw = event.get(field)
        if raw is None and not required:
            return None
        if not isinstance(raw, dict):
            raise ValueError("invalid_google_event_datetime")
        date_only = raw.get("date")
        date_time = raw.get("dateTime")
        if date_only is not None and date_time is not None:
            raise ValueError("ambiguous_google_event_datetime")
        value = date_time if date_time is not None else date_only
        if not isinstance(value, str) or not value.strip():
            raise ValueError("missing_google_event_datetime")
        if date_time is not None:
            if "T" not in value:
                raise ValueError("invalid_google_event_datetime")
            parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                zone_name = raw.get("timeZone")
                if not isinstance(zone_name, str) or not zone_name.strip():
                    raise ValueError("missing_google_event_timezone")
                try:
                    parsed = parsed.replace(tzinfo=ZoneInfo(zone_name))
                except (ZoneInfoNotFoundError, ValueError) as exc:
                    raise ValueError("invalid_google_event_timezone") from exc
                value = parsed.isoformat()
        else:
            if len(value) != 10:
                raise ValueError("invalid_google_event_date")
            datetime.date.fromisoformat(value)
        return value

    def _to_google_event(self, event: dict, source_calendar_id: str | None = None) -> GoogleEvent:
        if not isinstance(event, dict):
            raise ValueError("invalid_google_event")
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("missing_google_event_identity")
        status = self._event_text(event, "status", "confirmed")
        if status not in {"confirmed", "tentative", "cancelled"}:
            raise ValueError("invalid_google_event_status")
        # Cancelled tombstones are only guaranteed to contain their ID.
        start = self._event_datetime(event, "start") if status != "cancelled" else ""
        end = self._event_datetime(event, "end") if status != "cancelled" else ""
        for field in ("attendees", "attachments", "recurrence"):
            value = event.get(field)
            if value is not None and not isinstance(value, list):
                raise ValueError("invalid_google_event_collection")
        if any(not isinstance(value, str) for value in (event.get("recurrence") or [])):
            raise ValueError("invalid_google_event_recurrence")
        properties = event.get("extendedProperties") or {}
        if not isinstance(properties, dict):
            raise ValueError("invalid_google_event_properties")
        private_properties = properties.get("private")
        if private_properties is not None and not isinstance(private_properties, dict):
            raise ValueError("invalid_google_event_private_properties")

        # 반복 일정 원래 시작시각 (인스턴스 identity)
        _orig_start = self._event_datetime(event, "originalStartTime", required=False)

        return GoogleEvent(
            id=event_id,
            summary=self._event_text(event, "summary") or untitled_event_name(),
            description=self._event_text(event, "description"),
            start_time=start,
            end_time=end,
            location=self._event_text(event, "location"),
            status=status,
            color_id=self._event_text(event, "colorId") or None,
            updated_time=self._event_text(event, "updated") or None,
            source_calendar_id=source_calendar_id or self.calendar_id,
            # 반복 일정 필드
            recurring_event_id=self._event_text(event, "recurringEventId") or None,
            recurrence=event.get("recurrence") or None,
            original_start_time=_orig_start,
            # 참석자 / 첨부파일
            attendees=event.get("attendees") or None,
            attachments=event.get("attachments") or None,
            # extendedProperties.private (item 10)
            extended_properties_private=private_properties or None,
        )

    def create_event(
        self,
        summary: str,
        start_iso: str,
        end_iso: str,
        description: str = "",
        location: str = "",
        color_id: str | None = None,
        all_day: bool = False,
        calendar_id: str | None = None,
        idempotency_key: str | None = None,
        result_metadata: dict | None = None,
    ) -> str | None:
        if not self._remote_writes_allowed():
            return None
        if not self.is_authenticated or not self.service:
            return None
        self._clear_last_error()

        calendar_id = self._normalize_calendar_id(calendar_id)

        try:
            if all_day:
                start_date = (start_iso or "")[:10]
                if not start_date:
                    print("GCal Create Error: invalid start date for all-day event")
                    return None
                end_date = (end_iso or "")[:10] if end_iso else start_date
                if end_date < start_date:
                    end_date = start_date

                import datetime as _dt

                end_date_exclusive = (
                    _dt.date.fromisoformat(end_date) + _dt.timedelta(days=1)
                ).isoformat()

                logger.debug("GCal create all-day event")
                event = {
                    "summary": summary,
                    "description": description,
                    "start": {"date": start_date},
                    "end": {"date": end_date_exclusive},
                }
            else:
                tz_offset = self._tz_offset_for_value(start_iso)
                start_iso = to_iso_with_tz(start_iso, tz_offset=tz_offset)
                if not start_iso:
                    print("GCal Create Error: invalid start datetime")
                    return None

                end_iso = to_iso_with_tz(end_iso, tz_offset=tz_offset)
                if not end_iso:
                    sdt0 = parse_datetime_str(start_iso, target_tz_offset=tz_offset)
                    tz_offset0 = _extract_tz_offset(start_iso) or tz_offset
                    end_iso = (sdt0 + datetime.timedelta(hours=1)).strftime(
                        "%Y-%m-%dT%H:%M:%S"
                    ) + tz_offset0

                sdt = parse_datetime_str(start_iso, target_tz_offset=tz_offset)
                edt = parse_datetime_str(end_iso, target_tz_offset=tz_offset)
                if sdt and edt and edt <= sdt:
                    tz_offset = _extract_tz_offset(start_iso) or tz_offset
                    end_iso = (sdt + datetime.timedelta(hours=1)).strftime(
                        "%Y-%m-%dT%H:%M:%S"
                    ) + tz_offset

                logger.debug("GCal create timed event")
                event = {
                    "summary": summary,
                    "description": description,
                    "start": {"dateTime": start_iso, "timeZone": self.time_zone},
                    "end": {"dateTime": end_iso, "timeZone": self.time_zone},
                }

            if location:
                event["location"] = location
            if color_id:
                event["colorId"] = str(color_id)

            # Idempotency key: GCal API accepts a client-supplied UUID-style token via
            # the `conferenceDataVersion` query param is NOT the right place — the
            # correct mechanism is passing `sendUpdates` param. Actually GCal insert
            # supports idempotency via a unique request body field is not available.
            # The supported way is the `X-Goog-Channel-*` approach for push; for REST
            # insert, Google recommends a client-assigned `id` field (RFC 5322 message-id
            # format is not required — any valid event ID string up to 1024 chars works).
            # We embed the idempotency_key as the event's `id` so the server rejects
            # duplicate inserts with HTTP 409 which we treat as success (return the id).
            _sanitized_key = None
            if idempotency_key:
                import re as _re

                # GCal event IDs: lowercase letters a-v and digits 0-9, 5..1024 chars
                _sanitized_key = _re.sub(r"[^a-v0-9]", "", idempotency_key.lower())
                if len(_sanitized_key) >= 5:
                    event["id"] = _sanitized_key
                else:
                    _sanitized_key = None  # key too short after sanitising; skip

            created_event = self._execute_request(
                lambda: self.service.events().insert(calendarId=calendar_id, body=event).execute()
            )

            if not created_event:
                logger.error(
                    "create_event: API returned empty response for calendar %s", calendar_id
                )
                self._set_last_error("create", "empty_response", None)
                return None

            event_id = created_event.get("id")
            if not event_id or not str(event_id).strip():
                logger.error("create_event: API response missing event identity")
                self._set_last_error("create", "missing_id_in_response", None)
                return None
            if result_metadata is not None:
                result_metadata["remote_updated_at"] = created_event.get("updated")
            return event_id

        except Exception as exc:
            if getattr(getattr(exc, "resp", None), "status", None) == 409 and _sanitized_key:
                try:
                    existing = self._execute_request(
                        lambda: (
                            self.service.events()
                            .get(calendarId=calendar_id, eventId=_sanitized_key)
                            .execute()
                        )
                    )
                    if self._matches_created_event(existing, event):
                        self._clear_last_error()
                        if result_metadata is not None:
                            result_metadata["remote_updated_at"] = existing.get("updated")
                        return _sanitized_key
                except Exception:
                    logger.warning("Could not verify the existing Google create receipt")
                self._set_last_error("create_conflict", "existing_create_not_verified", 409)
                return None
            self._set_last_error("create", exc, getattr(getattr(exc, "resp", None), "status", None))
            logger.warning("Google request failed (%s)", self.last_error_message)
            return None

    def update_event(
        self,
        event_id: str,
        summary: str,
        start_iso: str,
        end_iso: str,
        description: str = "",
        location: str = "",
        color_id: str | None = None,
        all_day: bool = False,
        calendar_id: str | None = None,
        completed: bool = False,
        hide_completed: bool = False,
        expected_remote_updated_at: str | None = None,
        result_metadata: dict | None = None,
        revision_event_id: str | None = None,
    ) -> bool:
        if not self._remote_writes_allowed():
            return False
        if not self.is_authenticated or not self.service or not event_id:
            return False
        self._clear_last_error()

        calendar_id = self._normalize_calendar_id(calendar_id)
        same_instant = False

        try:
            if all_day:
                start_date = (start_iso or "")[:10]
                if not start_date:
                    print("GCal Update Error: invalid start date for all-day event")
                    return False
                end_date = (end_iso or "")[:10] if end_iso else start_date
                if end_date < start_date:
                    end_date = start_date

                import datetime as _dt

                end_date_exclusive = (
                    _dt.date.fromisoformat(end_date) + _dt.timedelta(days=1)
                ).isoformat()
                start_block = {"date": start_date}
                end_block = {"date": end_date_exclusive}
            else:
                tz_offset = self._tz_offset_for_value(start_iso)
                start_iso = to_iso_with_tz(start_iso, tz_offset=tz_offset)
                if not start_iso:
                    print("GCal Update Error: invalid start datetime")
                    return False

                end_iso = to_iso_with_tz(end_iso, tz_offset=tz_offset)
                if not end_iso:
                    sdt0 = parse_datetime_str(start_iso, target_tz_offset=tz_offset)
                    tz_offset0 = _extract_tz_offset(start_iso) or tz_offset
                    end_iso = (sdt0 + datetime.timedelta(hours=1)).strftime(
                        "%Y-%m-%dT%H:%M:%S"
                    ) + tz_offset0

                sdt = parse_datetime_str(start_iso, target_tz_offset=tz_offset)
                edt = parse_datetime_str(end_iso, target_tz_offset=tz_offset)
                same_instant = bool(sdt and edt and edt == sdt)
                if sdt and edt and edt <= sdt:
                    tz_offset = _extract_tz_offset(start_iso) or tz_offset
                    end_iso = (sdt + datetime.timedelta(hours=1)).strftime(
                        "%Y-%m-%dT%H:%M:%S"
                    ) + tz_offset

                start_block = {"dateTime": start_iso, "timeZone": self.time_zone}
                end_block = {"dateTime": end_iso, "timeZone": self.time_zone}

            def _do_update():
                revision_id = revision_event_id or event_id
                revision_event = (
                    self.service.events().get(calendarId=calendar_id, eventId=revision_id).execute()
                )
                current_updated_at = str(revision_event.get("updated") or "").strip()
                expected_updated_at = str(expected_remote_updated_at or "").strip()
                if (expected_updated_at and current_updated_at != expected_updated_at) or (
                    revision_id != event_id and revision_event.get("recurringEventId") != event_id
                ):
                    return {
                        "_dark_calendar_conflict": True,
                        "updated": current_updated_at,
                    }
                ev = revision_event
                if revision_id != event_id:
                    ev = (
                        self.service.events()
                        .get(calendarId=calendar_id, eventId=event_id)
                        .execute()
                    )
                # An untitled placeholder stays empty unless Google already has that title.
                ev["summary"] = google_summary_for_task_name(summary, ev.get("summary"))
                ev["description"] = description
                if location:
                    ev["location"] = location
                elif "location" in ev:
                    ev.pop("location", None)
                if color_id:
                    ev["colorId"] = str(color_id)
                else:
                    ev.pop("colorId", None)
                # A pulled zero-length Google event is stored with end == start;
                # do not stretch it to the one-hour default on every edit.
                zero_length = same_instant and self._zero_length_event(ev)
                ev["start"] = start_block
                ev["end"] = dict(start_block) if zero_length else end_block
                # [10] completion status sync
                if completed:
                    ext = ev.setdefault("extendedProperties", {})
                    ext.setdefault("private", {})["dark_calendar_completed"] = "1"
                    if hide_completed:
                        ev["status"] = "cancelled"
                        ev.pop("transparency", None)
                    else:
                        ev["transparency"] = "transparent"
                        ev.pop("status", None)
                else:
                    _ext = ev.get("extendedProperties", {}).get("private", {})
                    _ext.pop("dark_calendar_completed", None)
                    ev.pop("transparency", None)
                    if ev.get("status") == "cancelled":
                        ev["status"] = "confirmed"
                update_request = self.service.events().update(
                    calendarId=calendar_id,
                    eventId=event_id,
                    body=ev,
                )
                etag = str(ev.get("etag") or "").strip()
                if etag and hasattr(update_request, "headers"):
                    update_request.headers["If-Match"] = etag
                return update_request.execute()

            update_result = self._execute_request(_do_update)
            if isinstance(update_result, dict) and update_result.get("_dark_calendar_conflict"):
                self._set_last_error(
                    "conflict",
                    "Remote event changed after pull; local update was not applied",
                    412,
                )
                return False
            if result_metadata is not None and isinstance(update_result, dict):
                # A master receipt is not the selected instance's revision.
                result_metadata["remote_updated_at"] = (
                    None if revision_event_id else update_result.get("updated")
                )
            return True

        except HttpError as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            if status == 404:
                error_kind = "not_found"
            elif status == 412:
                error_kind = "conflict"
            else:
                error_kind = "update"
            self._set_last_error(error_kind, exc, status)
            logger.warning("Google request failed (%s)", self.last_error_message)
            return False

        except Exception as exc:
            self._set_last_error("update", exc)
            logger.warning("Google request failed (%s)", self.last_error_message)
            return False

    @staticmethod
    def _zero_length_event(event):
        try:
            start, end = (
                datetime.datetime.fromisoformat(str(event[key]["dateTime"]).replace("Z", "+00:00"))
                for key in ("start", "end")
            )
        except (KeyError, TypeError, ValueError):
            return False
        return start == end

    def delete_event(self, event_id: str, calendar_id: str | None = None) -> bool:
        if not self._remote_writes_allowed():
            return False
        if not self.is_authenticated or not self.service or not event_id:
            return False
        self._clear_last_error()

        calendar_id = self._normalize_calendar_id(calendar_id)

        try:
            self._execute_request(
                lambda: (
                    self.service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
                )
            )
            return True

        except HttpError as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            if status in (404, 410):
                self._set_last_error("not_found", exc, status)
                return True
            self._set_last_error("delete", exc, status)
            logger.warning("Google request failed (%s)", self.last_error_message)
            return False

        except Exception as exc:
            self._set_last_error("delete", exc)
            logger.warning("Google request failed (%s)", self.last_error_message)
            return False

    def move_event(
        self,
        event_id: str,
        source_calendar_id: str | None,
        destination_calendar_id: str | None,
        expected_remote_updated_at: str | None = None,
        result_metadata: dict | None = None,
    ) -> bool:
        """Move an unchanged source event; missing sources require reconciliation."""
        if not self._remote_writes_allowed():
            return False
        if not self.is_authenticated or not self.service or not event_id:
            return False
        self._clear_last_error()
        src = self._normalize_calendar_id(source_calendar_id)
        dst = self._normalize_calendar_id(destination_calendar_id)
        if not src or not dst:
            self._set_last_error("move", "missing calendar id", None)
            return False
        if src == dst:
            return True
        try:

            def _do_move():
                etag = None
                if expected_remote_updated_at:
                    current = self.service.events().get(calendarId=src, eventId=event_id).execute()
                    if current.get("updated") != expected_remote_updated_at:
                        return {"_dark_calendar_conflict": True}
                    etag = current.get("etag")
                request = self.service.events().move(
                    calendarId=src, eventId=event_id, destination=dst
                )
                if etag and hasattr(request, "headers"):
                    request.headers["If-Match"] = etag
                return request.execute()

            moved = self._execute_request(_do_move)
            if isinstance(moved, dict) and moved.get("_dark_calendar_conflict"):
                self._set_last_error("conflict", "Remote event changed before move", 412)
                return False
            if result_metadata is not None and isinstance(moved, dict):
                result_metadata["remote_updated_at"] = moved.get("updated")
            return True
        except HttpError as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            if status in (404, 410):
                # Event already gone on source; nothing to move.
                self._set_last_error("not_found", exc, status)
                return False
            self._set_last_error("conflict" if status == 412 else "move", exc, status)
            logger.warning("Google request failed (%s)", self.last_error_message)
            return False
        except Exception as exc:
            self._set_last_error("move", exc)
            logger.warning("Google request failed (%s)", self.last_error_message)
            return False

    def batch_create_events(self, operations: list) -> list:
        """최대 50개의 이벤트 생성을 단일 HTTP 배치 요청으로 처리한다."""
        return self._execute_batch("insert", operations)

    @classmethod
    def _matches_created_event(cls, existing, body):
        """A 409 receipt may link only the exact payload previously sent."""
        if not isinstance(existing, dict) or existing.get("status") == "cancelled":
            return False
        if existing.get("id") != body.get("id"):
            return False
        if any(
            (existing.get(key) or "") != (body.get(key) or "")
            for key in ("summary", "description", "location", "colorId")
        ):
            return False
        try:
            for field in ("start", "end"):
                remote = cls._event_datetime(existing, field)
                requested = cls._event_datetime(body, field)
                if "date" in body[field]:
                    if remote != requested:
                        return False
                elif datetime.datetime.fromisoformat(remote.replace("Z", "+00:00")) != (
                    datetime.datetime.fromisoformat(requested.replace("Z", "+00:00"))
                ):
                    return False
        except (ValueError, KeyError, TypeError):
            return False
        return True

    def batch_delete_events(self, operations: list) -> list:
        """최대 50개의 이벤트 삭제를 단일 HTTP 배치 요청으로 처리한다.
        각 operation: {"event_id", "calendar_id", "local_task_id"}
        """
        return self._execute_batch("delete", operations)

    def _execute_batch(self, method: str, operations: list) -> list:
        if not self._remote_writes_allowed():
            return [
                {
                    "local_task_id": operation.get("local_task_id"),
                    "event_id": operation.get("event_id"),
                    "success": False,
                    "error": self._account_identity_error_kind,
                }
                for operation in operations
            ]
        if not self.is_authenticated or not self.service or not operations:
            return []

        results: list = []
        pending: dict = {}

        def _cb(request_id, response, exception):
            op = pending.get(request_id, {})
            ltid = op.get("local_task_id")
            if exception is not None:
                _st = getattr(getattr(exception, "resp", None), "status", None)
                # HTTP 409 on an insert with an idempotency_key means the event already
                # exists under that id — treat as idempotent success.
                _ikey = op.get("idempotency_key")
                if method == "insert" and _st == 409 and _ikey:
                    import re as _re

                    _sk = _re.sub(r"[^a-v0-9]", "", str(_ikey).lower())
                    if len(_sk) >= 5:
                        try:
                            body = self._build_event_body_from_op(op)
                            if body is not None:
                                body["id"] = _sk
                                existing = self._execute_request(
                                    lambda: (
                                        self.service.events()
                                        .get(
                                            calendarId=self._normalize_calendar_id(
                                                op.get("calendar_id")
                                            ),
                                            eventId=_sk,
                                        )
                                        .execute()
                                    )
                                )
                                if self._matches_created_event(existing, body):
                                    results.append(
                                        {
                                            "local_task_id": ltid,
                                            "success": True,
                                            "event_id": _sk,
                                            "error": None,
                                            "remote_updated_at": existing.get("updated"),
                                        }
                                    )
                                    return
                        except Exception:
                            logger.warning("Could not verify a Google batch create receipt")
                results.append(
                    {
                        "local_task_id": ltid,
                        "success": False,
                        "event_id": op.get("event_id"),
                        "error": _google_error_code("batch_failed", exception, _st),
                        "status": _st,
                    }
                )
            else:
                eid = (response or {}).get("id") or op.get("event_id")
                results.append(
                    {
                        "local_task_id": ltid,
                        "success": True,
                        "event_id": eid,
                        "error": None,
                        "remote_updated_at": (response or {}).get("updated"),
                    }
                )

        with self._service_lock:
            batch = self.service.new_batch_http_request(callback=_cb)
            for idx, op in enumerate(operations[:50]):
                rid = str(idx)
                pending[rid] = op
                cal_id = self._normalize_calendar_id(op.get("calendar_id"))

                if method == "insert":
                    body = self._build_event_body_from_op(op)
                    if body is None:
                        results.append(
                            {
                                "local_task_id": op.get("local_task_id"),
                                "success": False,
                                "error": "invalid_datetime",
                            }
                        )
                        continue
                    # Idempotency: embed client-supplied key as the event's id field so
                    # a duplicate insert returns HTTP 409 instead of creating a new event.
                    _ikey = op.get("idempotency_key")
                    if _ikey:
                        import re as _re

                        _sk = _re.sub(r"[^a-v0-9]", "", str(_ikey).lower())
                        if len(_sk) >= 5:
                            body["id"] = _sk
                    batch.add(
                        self.service.events().insert(calendarId=cal_id, body=body), request_id=rid
                    )

                elif method == "delete":
                    eid = op.get("event_id")
                    if not eid:
                        results.append(
                            {
                                "local_task_id": op.get("local_task_id"),
                                "success": False,
                                "error": "missing_event_id",
                            }
                        )
                        continue
                    batch.add(
                        self.service.events().delete(calendarId=cal_id, eventId=eid), request_id=rid
                    )

            try:
                batch.execute()
            except Exception as exc:
                logger.error(
                    "batch_%s_events failed (%s)",
                    method,
                    _google_error_code(
                        "batch_failed", exc, getattr(getattr(exc, "resp", None), "status", None)
                    ),
                )
                return []
        return results

    def _build_event_body_from_op(self, op: dict) -> "dict | None":
        return self._build_event_body(
            # The engine maps an untitled placeholder to "": Google keeps no title.
            summary=op.get("summary") or "",
            start_iso=op.get("start_iso") or "",
            end_iso=op.get("end_iso") or "",
            description=op.get("description") or "",
            location=op.get("location") or "",
            color_id=op.get("color_id"),
            all_day=bool(op.get("all_day")),
            calendar_id=op.get("calendar_id"),
        )

    def _build_event_body(
        self, summary, start_iso, end_iso, description, location, color_id, all_day, calendar_id
    ) -> "dict | None":
        """create_event() 과 동일한 event body dict를 생성한다. 파싱 실패 시 None."""
        tz_name = getattr(self, "time_zone", None) or sync_time_zone(None)
        tz_offset = self._tz_offset_for_value(start_iso)

        if all_day:
            try:
                from datetime import datetime as _dt
                from datetime import timedelta as _td

                s = start_iso[:10]
                _dt.strptime(s, "%Y-%m-%d")
                e_raw = (end_iso or start_iso)[:10]
                e_dt = max(_dt.strptime(e_raw, "%Y-%m-%d"), _dt.strptime(s, "%Y-%m-%d")) + _td(
                    days=1
                )
                start_block = {"date": s}
                end_block = {"date": e_dt.strftime("%Y-%m-%d")}
            except (ValueError, TypeError, OverflowError):
                return None
        else:
            start_text = to_iso_with_tz(start_iso, tz_offset=tz_offset)
            end_text = to_iso_with_tz(end_iso, tz_offset=tz_offset)
            st = parse_datetime_str(start_text, target_tz_offset=tz_offset)
            en = parse_datetime_str(end_text, target_tz_offset=tz_offset)
            if not st:
                return None
            if not en or en <= st:
                try:
                    end_text = (st + datetime.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S") + (
                        _extract_tz_offset(start_text) or tz_offset
                    )
                except OverflowError:
                    return None
            start_block = {
                "dateTime": start_text,
                "timeZone": tz_name,
            }
            end_block = {"dateTime": end_text, "timeZone": tz_name}

        ev: dict = {"summary": summary, "start": start_block, "end": end_block}
        if description:
            ev["description"] = description
        if location:
            ev["location"] = location
        if color_id:
            ev["colorId"] = str(color_id)
        return ev
