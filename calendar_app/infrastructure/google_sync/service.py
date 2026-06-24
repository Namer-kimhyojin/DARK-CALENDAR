from dataclasses import dataclass
import datetime
import logging
import os.path
import socket
import ssl
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


from PyQt6.QtWidgets import QMessageBox  # noqa: E402

from calendar_app.app_paths import CREDENTIALS_PATH, TOKEN_PATH  # noqa: E402
from calendar_app.shared.datetime_utils import (  # noqa: E402
    _extract_tz_offset,
    parse_datetime_str,
    timezone_offset_for_datetime_str,
    timezone_offset_for_name,
    to_iso_with_tz,
)

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    HAS_GOOGLE_API = True


except ImportError:
    Request = None

    Credentials = None

    InstalledAppFlow = None

    build = None

    HttpError = Exception

    HAS_GOOGLE_API = False


SCOPES = ["https://www.googleapis.com/auth/calendar"]


@dataclass
class GoogleEvent:
    id: str

    summary: str

    description: Optional[str]

    start_time: str

    end_time: str

    location: Optional[str]

    status: str = "confirmed"

    color_id: Optional[str] = None

    updated_time: Optional[str] = None

    source_calendar_id: Optional[str] = None

    # 반복 일정 지원 (item 2)
    recurring_event_id: Optional[str] = None  # 부모 시리즈 ID (recurringEventId)
    recurrence: Optional[list] = None  # ["RRULE:FREQ=WEEKLY;..."] — 마스터 이벤트에만 존재
    original_start_time: Optional[str] = None  # 이 인스턴스의 원래 시작시각 (instance identity)

    # 참석자 / 첨부파일 (item 9)
    attendees: Optional[list] = None  # [{"email", "displayName", "responseStatus"}]
    attachments: Optional[list] = None  # [{"fileUrl", "title", "mimeType"}]

    # extendedProperties.private dict (item 10 — completion guard)
    extended_properties_private: Optional[dict] = None


def prepare_calendar_sync_service(
    existing_service=None, calendar_id="primary", time_zone="Asia/Seoul", reset_auth=False
):
    """Return a sync service configured for the requested calendar/timezone."""

    service = existing_service or CalendarSyncService(calendar_id=calendar_id, time_zone=time_zone)

    service.calendar_id = service._normalize_calendar_id(calendar_id)

    service.time_zone = time_zone

    if reset_auth:
        service.is_authenticated = False

        service.service = None

    return service


def _credentials_support_scopes(creds) -> bool:
    if creds is None:
        return False

    granted = set(getattr(creds, "scopes", None) or [])

    if not granted:
        return False

    return set(SCOPES).issubset(granted)


def _token_file_supports_scopes(token_path: str) -> bool:
    try:
        json_mod = __import__("json")

        with open(token_path, encoding="utf-8", errors="strict") as fh:
            payload = json_mod.load(fh)

    except Exception:
        return False

    granted = set(payload.get("scopes") or [])

    if not granted:
        return False

    return set(SCOPES).issubset(granted)


class CalendarSyncService:
    def __init__(self, calendar_id="primary", time_zone="Asia/Seoul"):
        self.is_authenticated = False

        self.service = None

        self.calendar_id = self._normalize_calendar_id(calendar_id)

        self.time_zone = time_zone

        # googleapiclient/httplib2 service is not thread-safe.

        # Serialize API access across UI sync timer + background workers.

        self._service_lock = threading.RLock()

        self.last_error_kind = None

        self.last_error_status = None

        self.last_error_message = None

        # 마지막 429 응답의 Retry-After 값(초). engine.py 로깅용.
        self._last_retry_after_secs: float = 0.0

    def _clear_auth_state(self):
        self.is_authenticated = False

        self.service = None

    def _clear_last_error(self):
        self.last_error_kind = None

        self.last_error_status = None

        self.last_error_message = None

    def _set_last_error(self, kind: str, message: str, status: Optional[int] = None):
        self.last_error_kind = kind

        self.last_error_status = status

        self.last_error_message = message

    def _default_tz_offset(self) -> str:
        return timezone_offset_for_name(self.time_zone)

    def _normalize_calendar_id(self, calendar_id: Optional[str] = None) -> str:
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

            if status in {408, 409, 425, 429, 500, 502, 503, 504}:
                return True

            if status == 400:
                msg = str(exc).lower()

                if "sequence" in msg:
                    return True

            return False

        if isinstance(exc, TimeoutError | socket.timeout | ssl.SSLError):
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
            if secs > 3600:
                return default
            return min(secs, 60.0)
        except Exception:
            return default

    def _execute_request(self, request_callable, retries: int = 2, retry_delay: float = 1.5):
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

                # 429 응답이면 Retry-After 헤더를 우선 사용
                is_429 = False
                if HAS_GOOGLE_API:
                    try:
                        from googleapiclient.errors import HttpError as _HttpError

                        if isinstance(exc, _HttpError):
                            _status = int(getattr(getattr(exc, "resp", None), "status", 0) or 0)
                            if _status == 429:
                                is_429 = True
                    except Exception:
                        pass

                if is_429:
                    wait = self._get_retry_after_secs(exc, retry_delay * (attempt + 1))
                    self._last_retry_after_secs = wait
                    logger.warning(
                        "GCal 429 rate-limit (attempt %d/%d), honouring Retry-After=%.0fs",
                        attempt + 1,
                        retries,
                        wait,
                    )
                else:
                    wait = retry_delay * (attempt + 1)
                    logger.warning(
                        "GCal transient error (attempt %d/%d), retrying in %.1fs: %s",
                        attempt + 1,
                        retries,
                        wait,
                        exc,
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

            with open(TOKEN_PATH, encoding="utf-8", errors="strict") as fh:
                token_data = _json.load(fh)
            # google-auth 라이브러리가 저장하는 키: "token" (access_token)
            token = str(token_data.get("token") or token_data.get("access_token") or "").strip()
            if not token:
                logger.info(
                    "revoke_token: no access_token found in token file; skipping revoke call"
                )
                return True
            body = f"token={token}".encode("utf-8", errors="strict")
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
            logger.warning("Google OAuth token revocation failed (non-critical): %s", exc)
            return False

    def authenticate(self, parent_widget=None, interactive=True) -> bool:
        with self._service_lock:
            if self.is_authenticated and self.service is not None:
                return True

            self._clear_auth_state()

            self._clear_last_error()

        if not HAS_GOOGLE_API:
            if parent_widget:
                QMessageBox.warning(
                    parent_widget, "Google Calendar", "Google Calendar modules are not installed."
                )

            return False

        creds = None

        if os.path.exists(TOKEN_PATH):
            try:
                if not _token_file_supports_scopes(TOKEN_PATH):
                    logger.warning(
                        "authenticate(non-interactive): token file at %s is missing required scopes; "
                        "re-authentication required.",
                        TOKEN_PATH,
                    )
                    raise ValueError("token_missing_required_scopes")

                creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

                if not _credentials_support_scopes(creds):
                    logger.warning(
                        "authenticate(non-interactive): loaded credentials object is missing required scopes "
                        "(has_scopes=%s); discarding.",
                        getattr(creds, "scopes", None),
                    )
                    creds = None

            except Exception as _load_exc:
                logger.warning(
                    "authenticate(non-interactive): failed to load/validate token file: %s",
                    _load_exc,
                )
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())

                    if not _credentials_support_scopes(creds):
                        logger.warning(
                            "authenticate(non-interactive): refreshed token is missing required scopes; discarding."
                        )
                        creds = None

                except Exception as _refresh_exc:
                    logger.warning(
                        "authenticate(non-interactive): token refresh failed: %s",
                        _refresh_exc,
                    )
                    creds = None

            if not creds or not creds.valid:
                if not interactive:
                    logger.warning(
                        "authenticate(non-interactive): cannot proceed without valid credentials "
                        "(interactive=False). creds_present=%s, creds_valid=%s",
                        creds is not None,
                        getattr(creds, "valid", None),
                    )
                    return False

                if not os.path.exists(CREDENTIALS_PATH):
                    if parent_widget:
                        QMessageBox.critical(
                            parent_widget,
                            "Google Calendar",
                            "credentials.json was not found.",
                        )

                    return False

                try:
                    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)

                    creds = flow.run_local_server(port=0)

                except Exception as exc:
                    self._set_last_error("auth", str(exc))

                    if parent_widget:
                        QMessageBox.warning(
                            parent_widget, "Google Calendar", f"Authentication failed: {exc}"
                        )

                    return False

            try:
                with open(TOKEN_PATH, "w", encoding="utf-8", errors="strict") as token:
                    token.write(creds.to_json())

            except OSError as exc:
                self._set_last_error("auth", f"token_write_failed: {exc}")

                if parent_widget:
                    QMessageBox.warning(
                        parent_widget, "Google Calendar", f"Failed to save token: {exc}"
                    )

                return False

        try:
            with self._service_lock:
                try:
                    import httplib2

                    authorized_http = creds.authorize(httplib2.Http(timeout=12))

                    self.service = build(
                        "calendar", "v3", http=authorized_http, cache_discovery=False
                    )

                except Exception:
                    self.service = build("calendar", "v3", credentials=creds, cache_discovery=False)

                self.is_authenticated = True

            if parent_widget:
                QMessageBox.information(
                    parent_widget, "Google Calendar", "Authentication completed."
                )

            return True

        except Exception as exc:
            with self._service_lock:
                self._clear_auth_state()

            self._set_last_error("auth", str(exc))

            if parent_widget:
                QMessageBox.critical(
                    parent_widget, "Google Calendar", f"API connection failed: {exc}"
                )

            return False

    def fetch_events(
        self,
        start_date_str: str,
        end_date_str: Optional[str] = None,
        calendar_id: Optional[str] = None,
    ) -> Optional[list[GoogleEvent]]:
        if not self.is_authenticated or not self.service:
            return []
        self._clear_last_error()

        try:
            tz_offset = self._tz_offset_for_value(start_date_str)
            time_min = f"{start_date_str}T00:00:00{tz_offset}"
            end_base = end_date_str or start_date_str
            time_max = f"{end_base}T23:59:59{self._tz_offset_for_value(end_base)}"
            calendar_id = self._normalize_calendar_id(calendar_id)

            response = self._execute_request(
                lambda: self.service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=200,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            return [
                self._to_google_event(item, source_calendar_id=calendar_id)
                for item in response.get("items", [])
            ]
        except Exception as exc:
            self._set_last_error(
                "fetch", str(exc), getattr(getattr(exc, "resp", None), "status", None)
            )
            if hasattr(exc, "content"):
                print(
                    f"Google fetch err (HttpError): {exc.content.decode('utf-8', errors='replace')}"
                )
            else:
                print("Google fetch err:", exc)
            return None

    def fetch_sync_events(
        self,
        sync_token: Optional[str] = None,
        calendar_id: Optional[str] = None,
    ) -> tuple[Optional[list[GoogleEvent]], Optional[str], bool]:
        if not self.is_authenticated or not self.service:
            return [], None, False
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
            old_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(12)
            try:
                while True:
                    if page_token:
                        page_token_str = str(page_token)
                        if page_token_str in seen_page_tokens:
                            raise RuntimeError(
                                f"Duplicate Google events page token detected: {page_token_str}"
                            )
                        seen_page_tokens.add(page_token_str)

                    request_params = dict(params)
                    if page_token:
                        request_params["pageToken"] = page_token

                    response = self._execute_request(
                        lambda request_params=request_params: self.service.events()
                        .list(**request_params)
                        .execute()
                    )
                    source_calendar_id = str(
                        request_params.get("calendarId") or resolved_calendar_id or ""
                    ).strip()
                    events.extend(
                        self._to_google_event(item, source_calendar_id=source_calendar_id)
                        for item in response.get("items", [])
                    )

                    page_token = response.get("nextPageToken")
                    fetched_pages += 1
                    if not page_token:
                        next_sync_token = response.get("nextSyncToken")
                        break
                    if fetched_pages >= max_pages:
                        raise RuntimeError(
                            f"Google events pagination exceeded max pages ({max_pages})"
                        )

            except HttpError as _page_exc:
                _page_status = getattr(getattr(_page_exc, "resp", None), "status", None)
                if _page_status == 410:
                    self._set_last_error("sync_token_expired", str(_page_exc), 410)
                    print("Google incremental sync token expired (mid-page). Full resync required.")
                    socket.setdefaulttimeout(old_timeout)
                    return None, None, True
                self._set_last_error("fetch", str(_page_exc), _page_status)
                if events:
                    logger.warning(
                        "fetch_sync_events: HttpError %s on page %s; returning %d already-fetched events",
                        _page_status,
                        page_token,
                        len(events),
                    )
                    socket.setdefaulttimeout(old_timeout)
                    return events, None, False
                socket.setdefaulttimeout(old_timeout)
                raise

            except Exception as _page_exc2:
                self._set_last_error("fetch", str(_page_exc2))
                if events:
                    logger.warning(
                        "fetch_sync_events: Exception on page %s; returning %d already-fetched events: %s",
                        page_token,
                        len(events),
                        _page_exc2,
                    )
                    socket.setdefaulttimeout(old_timeout)
                    return events, None, False
                socket.setdefaulttimeout(old_timeout)
                raise

            finally:
                socket.setdefaulttimeout(old_timeout)

            return events, next_sync_token, False

        except HttpError as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            if status == 410:
                self._set_last_error("sync_token_expired", str(exc), 410)
                print("Google incremental sync token expired. Full resync required.")
                return None, None, True

            self._set_last_error("fetch", str(exc), status)
            if hasattr(exc, "content"):
                print(
                    f"Google incremental fetch err (HttpError): {exc.content.decode('utf-8', errors='replace')}"
                )
            else:
                print(f"Google incremental fetch err: {exc}")
            return None, None, False

        except Exception as exc:
            self._set_last_error("fetch", str(exc))
            if self._is_transient_error(exc):
                logger.warning("GCal incremental fetch: transient network error (skipped): %s", exc)
            else:
                logger.error("GCal incremental fetch err: %s", exc)
            return None, None, False

    def list_accessible_calendars(self) -> list[dict]:
        if not self.is_authenticated or not self.service:
            return []
        self._clear_last_error()

        calendars: list[dict] = []
        page_token = None
        seen_page_tokens: set[str] = set()
        max_pages = 200
        fetched_pages = 0

        try:
            while True:
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
                    lambda request_params=request_params: self.service.calendarList()
                    .list(**request_params)
                    .execute()
                )
                for item in response.get("items", []):
                    calendars.append(
                        {
                            "id": item.get("id", ""),
                            "summary": item.get("summaryOverride")
                            or item.get("summary")
                            or item.get("id", ""),
                            "timeZone": item.get("timeZone") or "",
                            "accessRole": item.get("accessRole") or "",
                            "primary": bool(item.get("primary")),
                        }
                    )

                page_token = response.get("nextPageToken")
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

        except Exception as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            if status == 403 and (
                "insufficient" in str(exc).lower() or "scope" in str(exc).lower()
            ):
                self._clear_auth_state()
                self._set_last_error(
                    "reauth_required",
                    "Stored token does not have calendar subscription permission. Please re-authenticate.",
                    403,
                )
                logger.warning(
                    "GCal calendar list fetch requires re-authentication with broader scopes."
                )
                return []

            self._set_last_error("calendar_list", str(exc), status)
            if calendars:
                logger.warning(
                    "GCal calendar list fetch failed mid-page (status=%s); returning %d already-fetched calendars: %s",
                    status,
                    len(calendars),
                    exc,
                )
                calendars.sort(
                    key=lambda item: (not item.get("primary"), (item.get("summary") or "").lower())
                )
                return calendars

            logger.warning("GCal calendar list fetch failed: %s", exc)
            return []

    def subscribe_calendar(self, calendar_id: str) -> Optional[dict]:
        calendar_id = self._normalize_calendar_id(calendar_id)

        if not self.is_authenticated or not self.service or not calendar_id:
            return None

        try:
            response = self._execute_request(
                lambda: self.service.calendarList().insert(body={"id": calendar_id}).execute()
            )

            return {
                "id": response.get("id", calendar_id),
                "summary": response.get("summaryOverride")
                or response.get("summary")
                or calendar_id,
                "timeZone": response.get("timeZone") or "",
                "accessRole": response.get("accessRole") or "",
                "primary": bool(response.get("primary")),
            }

        except Exception as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)

            if status == 403 and (
                "insufficient" in str(exc).lower() or "scope" in str(exc).lower()
            ):
                self._clear_auth_state()

                self._set_last_error(
                    "reauth_required",
                    "Stored token does not have calendar subscription permission. Please re-authenticate.",
                    403,
                )

            else:
                self._set_last_error("subscribe", str(exc), status)

            logger.warning("GCal calendar subscription failed for %s: %s", calendar_id, exc)

            return None

    def unsubscribe_calendar(self, calendar_id: str) -> bool:
        calendar_id = self._normalize_calendar_id(calendar_id)

        if not self.is_authenticated or not self.service or not calendar_id:
            return False

        try:
            self._execute_request(
                lambda: self.service.calendarList().delete(calendarId=calendar_id).execute()
            )

            return True

        except Exception as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)

            if status == 403 and (
                "insufficient" in str(exc).lower() or "scope" in str(exc).lower()
            ):
                self._clear_auth_state()

                self._set_last_error(
                    "reauth_required",
                    "Stored token does not have calendar subscription permission. Please re-authenticate.",
                    403,
                )

            else:
                self._set_last_error("unsubscribe", str(exc), status)

            logger.warning("GCal calendar unsubscribe failed for %s: %s", calendar_id, exc)

            return False

    def _to_google_event(
        self, event: dict, source_calendar_id: Optional[str] = None
    ) -> GoogleEvent:
        start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", ""))

        end = event.get("end", {}).get("dateTime", event.get("end", {}).get("date", ""))

        # 반복 일정 원래 시작시각 (인스턴스 identity)
        _orig_start_raw = event.get("originalStartTime") or {}
        _orig_start = _orig_start_raw.get("dateTime") or _orig_start_raw.get("date") or None

        return GoogleEvent(
            id=event.get("id", ""),
            summary=event.get("summary", "Untitled"),
            description=event.get("description", ""),
            start_time=start,
            end_time=end,
            location=event.get("location", ""),
            status=event.get("status", "confirmed"),
            color_id=event.get("colorId"),
            updated_time=event.get("updated"),
            source_calendar_id=source_calendar_id or self.calendar_id,
            # 반복 일정 필드
            recurring_event_id=event.get("recurringEventId") or None,
            recurrence=event.get("recurrence") or None,
            original_start_time=_orig_start,
            # 참석자 / 첨부파일
            attendees=event.get("attendees") or None,
            attachments=event.get("attachments") or None,
            # extendedProperties.private (item 10)
            extended_properties_private=event.get("extendedProperties", {}).get("private") or None,
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
        calendar_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Optional[str]:
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

                logger.debug(
                    "GCal create all-day: summary=%r date=%s~%s", summary, start_date, end_date
                )
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

                logger.debug("GCal create: summary=%r start=%s end=%s", summary, start_iso, end_iso)
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

            # HTTP 409 Conflict means the event already exists under this id — treat as
            # idempotent success and return the key as the event_id.
            _last_status = getattr(self, "_last_error_status", None)
            if not created_event and _last_status == 409 and _sanitized_key:
                logger.info(
                    "create_event: 409 Conflict for idempotency_key %s on calendar %s; "
                    "treating as idempotent success",
                    _sanitized_key,
                    calendar_id,
                )
                self._clear_last_error()
                return _sanitized_key
            if not created_event:
                logger.error(
                    "create_event: API returned empty response for calendar %s", calendar_id
                )
                self._set_last_error("create", "empty_response", None)
                return None

            event_id = created_event.get("id")
            if not event_id or not str(event_id).strip():
                logger.error(
                    "create_event: API response missing 'id' for calendar %s (response keys: %s)",
                    calendar_id,
                    list(created_event.keys()),
                )
                self._set_last_error("create", "missing_id_in_response", None)
                return None
            return event_id

        except Exception as exc:
            self._set_last_error(
                "create", str(exc), getattr(getattr(exc, "resp", None), "status", None)
            )
            if hasattr(exc, "content"):
                print(
                    f"GCal Create Error (HttpError): {exc.content.decode('utf-8', errors='replace')}"
                )
            else:
                print(f"GCal Create Error: {exc}")
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
        calendar_id: Optional[str] = None,
        completed: bool = False,
        hide_completed: bool = False,
    ) -> bool:
        if not self.is_authenticated or not self.service or not event_id:
            return False
        self._clear_last_error()

        calendar_id = self._normalize_calendar_id(calendar_id)

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
                if sdt and edt and edt <= sdt:
                    tz_offset = _extract_tz_offset(start_iso) or tz_offset
                    end_iso = (sdt + datetime.timedelta(hours=1)).strftime(
                        "%Y-%m-%dT%H:%M:%S"
                    ) + tz_offset

                start_block = {"dateTime": start_iso, "timeZone": self.time_zone}
                end_block = {"dateTime": end_iso, "timeZone": self.time_zone}

            def _do_update():
                ev = self.service.events().get(calendarId=calendar_id, eventId=event_id).execute()
                ev["summary"] = summary
                ev["description"] = description
                if location:
                    ev["location"] = location
                elif "location" in ev:
                    ev.pop("location", None)
                if color_id:
                    ev["colorId"] = str(color_id)
                else:
                    ev.pop("colorId", None)
                ev["start"] = start_block
                ev["end"] = end_block
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
                return (
                    self.service.events()
                    .update(
                        calendarId=calendar_id,
                        eventId=event_id,
                        body=ev,
                    )
                    .execute()
                )

            self._execute_request(_do_update)
            return True

        except HttpError as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            self._set_last_error("not_found" if status == 404 else "update", str(exc), status)
            if hasattr(exc, "content"):
                print(
                    f"GCal Update Error (HttpError): {exc.content.decode('utf-8', errors='replace')}"
                )
            else:
                print(f"GCal Update Error: {exc}")
            return False

        except Exception as exc:
            self._set_last_error("update", str(exc))
            if hasattr(exc, "content"):
                print(
                    f"GCal Update Error (HttpError): {exc.content.decode('utf-8', errors='replace')}"
                )
            else:
                print(f"GCal Update Error: {exc}")
            return False

    def delete_event(self, event_id: str, calendar_id: Optional[str] = None) -> bool:
        if not self.is_authenticated or not self.service or not event_id:
            return False
        self._clear_last_error()

        calendar_id = self._normalize_calendar_id(calendar_id)

        try:
            self._execute_request(
                lambda: self.service.events()
                .delete(calendarId=calendar_id, eventId=event_id)
                .execute()
            )
            return True

        except HttpError as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            if status in (404, 410):
                self._set_last_error("not_found", str(exc), status)
                return True
            self._set_last_error("delete", str(exc), status)
            print(f"GCal Delete Error: {exc}")
            return False

        except Exception as exc:
            self._set_last_error("delete", str(exc))
            print(f"GCal Delete Error: {exc}")
            return False

    def batch_create_events(self, operations: list) -> list:
        """최대 50개의 이벤트 생성을 단일 HTTP 배치 요청으로 처리한다."""
        return self._execute_batch("insert", operations)

    def batch_update_events(self, operations: list) -> list:
        """최대 50개의 이벤트 수정을 단일 HTTP 배치 요청으로 처리한다.
        각 operation: {"event_id", "calendar_id", "summary", "start_iso", "end_iso", ...}
        """
        return self._execute_batch("patch", operations)

    def batch_delete_events(self, operations: list) -> list:
        """최대 50개의 이벤트 삭제를 단일 HTTP 배치 요청으로 처리한다.
        각 operation: {"event_id", "calendar_id", "local_task_id"}
        """
        return self._execute_batch("delete", operations)

    def _execute_batch(self, method: str, operations: list) -> list:
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
                if _st == 409 and _ikey:
                    import re as _re

                    _sk = _re.sub(r"[^a-v0-9]", "", str(_ikey).lower())
                    if len(_sk) >= 5:
                        logger.info(
                            "batch insert 409 (idempotent) for task %s; using key %s as event_id",
                            ltid,
                            _sk,
                        )
                        results.append(
                            {
                                "local_task_id": ltid,
                                "success": True,
                                "event_id": _sk,
                                "error": None,
                            }
                        )
                        return
                results.append(
                    {
                        "local_task_id": ltid,
                        "success": False,
                        "event_id": op.get("event_id"),
                        "error": f"http_{_st}" if _st else str(exception),
                        "status": _st,
                    }
                )
            else:
                eid = (response or {}).get("id") or op.get("event_id")
                results.append(
                    {"local_task_id": ltid, "success": True, "event_id": eid, "error": None}
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

                elif method == "patch":
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
                    # Patch completion status
                    if op.get("completed"):
                        ext = body.setdefault("extendedProperties", {})
                        ext.setdefault("private", {})["dark_calendar_completed"] = "1"
                        if op.get("hide_completed"):
                            body["status"] = "cancelled"
                        else:
                            body["transparency"] = "transparent"
                    else:
                        ext = body.setdefault("extendedProperties", {})
                        ext.setdefault("private", {})["dark_calendar_completed"] = None  # Remove
                        body["status"] = "confirmed"
                        body["transparency"] = "opaque"

                    batch.add(
                        self.service.events().patch(calendarId=cal_id, eventId=eid, body=body),
                        request_id=rid,
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
                logger.error("batch_%s_events: batch.execute() failed: %s", method, exc)
                return []
        return results

    def _build_event_body_from_op(self, op: dict) -> "dict | None":
        return self._build_event_body(
            summary=op.get("summary") or "Untitled",
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
        from calendar_app.shared.datetime_utils import parse_datetime_str, timezone_offset_for_name

        tz_name = getattr(self, "time_zone", "Asia/Seoul") or "Asia/Seoul"
        tz_offset = timezone_offset_for_name(tz_name) or "+09:00"

        if all_day:
            try:
                from datetime import datetime as _dt
                from datetime import timedelta as _td

                s = start_iso[:10]
                _dt.strptime(s, "%Y-%m-%d")
                e_raw = (end_iso or start_iso)[:10]
                e_dt = _dt.strptime(e_raw, "%Y-%m-%d") + _td(days=1)
                start_block = {"date": s}
                end_block = {"date": e_dt.strftime("%Y-%m-%d")}
            except (ValueError, TypeError):
                return None
        else:
            st = parse_datetime_str(start_iso, target_tz_offset=tz_offset)
            en = (
                parse_datetime_str(end_iso or start_iso, target_tz_offset=tz_offset)
                if (end_iso or start_iso)
                else st
            )
            if not st:
                return None
            start_block = {
                "dateTime": st.strftime("%Y-%m-%dT%H:%M:%S") + tz_offset,
                "timeZone": tz_name,
            }
            end_block = (
                {"dateTime": en.strftime("%Y-%m-%dT%H:%M:%S") + tz_offset, "timeZone": tz_name}
                if en
                else start_block
            )

        ev: dict = {"summary": summary, "start": start_block, "end": end_block}
        if description:
            ev["description"] = description
        if location:
            ev["location"] = location
        if color_id:
            ev["colorId"] = str(color_id)
        return ev
