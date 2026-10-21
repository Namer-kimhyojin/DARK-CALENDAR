# -*- coding: utf-8 -*-
"""Shared user-facing recovery messages and plain-text conflict comparisons."""

from datetime import UTC, datetime
from functools import wraps
import json
import sqlite3

from calendar_app.application.calendar_sync_contract import CalendarSyncError
from calendar_app.infrastructure.calendar_sync.status import load_calendar_errors
from calendar_app.infrastructure.i18n import t

_GOOGLE_ERROR_CODES = {
    "account_mismatch",
    "account_unverified",
    "login_required",
    "operation_failed",
    "network_unavailable",
    "dependency_unavailable",
    "database_failed",
    "google_pull_invalid_datetime",
    "invalid_remote_event",
    "invalid_calendar_data",
    "invalid_calendar_response",
    "duplicate_remote_event",
    "calendar_report_incomplete",
    "calendar_access_lost",
    "no_calendars",
    "google_fetch_failed",
    "pull_apply_failed",
    "auth_client_missing",
    "auth_client_invalid",
    "auth_client_type",
    "auth_redirect",
    "auth_timeout",
    "auth_denied",
    "auth_browser",
    "auth_listener",
    "auth_token_write",
    "calendar_move",
    "calendar_move_unconfirmed",
    "calendar_move_local_state",
    "completed_with_issues",
    "cancelled",
    "sync_already_running",
}
_GOOGLE_ERROR_ALIASES = {
    "auth": "login_required",
    "auth_required": "login_required",
    "reauth_required": "login_required",
    "auth_modules": "dependency_unavailable",
    "network": "network_unavailable",
    "fetch_exception": "network_unavailable",
    "fetch": "google_fetch_failed",
    "calendar_list": "google_fetch_failed",
    "invalid_google_pull_datetime": "google_pull_invalid_datetime",
    "auth_cancelled": "cancelled",
    "sync_in_progress": "sync_already_running",
}


def google_sync_error_code(error, http_status=None):
    """Keep known diagnostic codes; never persist exception text or API payloads."""
    code = error if isinstance(error, str) else ""
    if code in _GOOGLE_ERROR_CODES:
        return code
    if code.startswith("remote_http_"):
        suffix = code.removeprefix("remote_http_")
        if len(suffix) == 3 and suffix.isascii() and suffix.isdigit():
            status = int(suffix)
            if 400 <= status <= 599:
                return "login_required" if status == 401 else f"remote_http_{status}"
    # Legacy services supplied a kind and HTTP status separately. Only remote
    # operations may use that status; a stale HTTP error must not hide DB/data errors.
    if (
        code in {"fetch", "fetch_exception", "calendar_list", "create", "update", "delete", "move"}
        and isinstance(http_status, int)
        and not isinstance(http_status, bool)
        and 400 <= http_status <= 599
    ):
        return "login_required" if http_status == 401 else f"remote_http_{http_status}"
    return _GOOGLE_ERROR_ALIASES.get(code, "operation_failed")


def guard_sync_database(action):
    """Keep database/conversion failures inside a Qt dialog's action boundary."""

    @wraps(action)
    def guarded(dialog, *args, **kwargs):
        try:
            return action(dialog, *args, **kwargs)
        except (sqlite3.Error, CalendarSyncError) as exc:
            code = str(exc) if isinstance(exc, CalendarSyncError) else "operation_failed"
            dialog.controller.status = code
            dialog.status.setText(
                sync_error_message(code)
                if isinstance(exc, CalendarSyncError)
                else t("dialog.task.save_error_db", "데이터베이스 업데이트에 실패했습니다.")
            )
            if hasattr(dialog, "_available_key"):
                dialog._available_key = None
            return False

    return guarded


def guard_calendar_action(action):
    """Keep local calendar changes and subscription registration inside the UI boundary."""

    @wraps(action)
    def guarded(page, *args, **kwargs):
        try:
            return action(page, *args, **kwargs)
        except (sqlite3.Error, OSError, RuntimeError, CalendarSyncError):
            page.feedback.setText(
                t(
                    "sync_unified.calendar_save_failed",
                    "설정을 저장하지 못했습니다. 다시 시도하세요.",
                )
            )
            page.reload()
            return False

    return guarded


def add_sync_hub_return(dialog, layout, app):
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QPushButton

    button = QPushButton(t("sync_unified.back", "전체 캘린더 설정으로"))
    button.setObjectName("ghost_btn")

    def go_back():
        dialog.reject()
        if not dialog.property("syncHubChild") and hasattr(app, "open_calendar_sync_hub"):
            QTimer.singleShot(0, app.open_calendar_sync_hub)

    button.clicked.connect(go_back)
    layout.addWidget(button)
    return button


def calendar_selection_style(tokens):
    """Match list check indicators to the dialog's theme, including dark mode."""
    return (
        "QListWidget#SyncCalendarSelection::indicator { width: 16px; height: 16px; "
        "border-radius: 4px; border: 2px solid " + tokens["check_indicator_border"] + "; "
        "background: " + tokens["check_indicator_bg"] + "; }"
        "QListWidget#SyncCalendarSelection::indicator:checked { background: "
        + tokens["check_checked_bg"]
        + "; border-color: "
        + tokens["check_checked_border"]
        + "; }"
        "QPushButton#primary_btn:disabled, QPushButton#ghost_btn:disabled { "
        "background: "
        + tokens["button_disabled_bg"]
        + "; color: "
        + tokens["button_disabled_text"]
        + "; border-color: "
        + tokens["button_disabled_border"]
        + "; }"
    )


def calendar_recovery_issues(repo, settings, prefix, account):
    """Use one diagnostic representation for both provider settings dialogs."""
    rows = [
        dict(row, kind="pending_delete_unconfirmed", recovery_issue=True)
        for row in repo.pending_deletes(account)
    ]
    calendars = {row["local_id"]: row for row in repo.calendars(account)}
    for key, code in load_calendar_errors(settings, prefix).items():
        if key in calendars and calendars[key]["is_active"]:
            rows.append(
                {
                    "calendar_id": key,
                    "calendar_name": calendars[key]["display_name"],
                    "kind": code,
                    "recovery_issue": True,
                }
            )
    return rows


def recovery_issue_label(row):
    return t("sync_recovery.calendar_issue", "{calendar} · {reason}").format(
        calendar=row.get("calendar_name") or row["calendar_id"],
        reason=(
            t("sync_recovery.pending_delete", "삭제 결과 확인 필요")
            if row["kind"] == "pending_delete_unconfirmed"
            else sync_error_message(row["kind"])
        ),
    )


def recovery_issue_text(row):
    text = sync_error_message(row["kind"])
    if row["kind"] == "pending_delete_unconfirmed":
        try:
            stamp = datetime.fromisoformat(row.get("created_at") or "")
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=UTC)
            when = stamp.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError, OverflowError, OSError):
            when = t("sync_recovery.time_unknown", "이전 버전 기록 · 시각 정보 없음")
        text += "\n" + t("sync_recovery.pending_since", "발생 시각: {time}").format(time=when)
    return text


def sync_error_message(code):
    if code == "account_unverified":
        return t(
            "sync_ui.account_unverified",
            "로그인 후 계정의 기본 캘린더를 확인하지 못했습니다. 기존 연결은 유지했습니다. 네트워크와 Google Calendar 권한을 확인한 뒤 인증을 다시 실행하세요.",
        )
    http = code.rsplit("_", 1)[-1] if code.startswith(("remote_http_", "graph_http_")) else ""
    if http == "401":
        return t(
            "sync_ui.auth", "인증이 만료되었거나 암호가 잘못되었습니다. 계정을 다시 연결하세요."
        )
    if http == "403":
        return t(
            "sync_ui.permission",
            "캘린더 접근 권한이 없습니다. 계정 권한과 서비스 지원 여부를 확인하세요.",
        )
    if http == "429":
        return t(
            "sync_ui.rate_limit",
            "서비스의 요청 제한에 도달했습니다. 자동 재시도 간격을 늘렸습니다. 잠시 후 다시 시도하세요.",
        )
    if http.isdigit() and int(http) >= 500:
        return t(
            "sync_ui.server",
            "서비스 서버가 일시적으로 응답하지 않습니다. 일정은 보존되며 나중에 다시 시도합니다.",
        )
    if http == "412":
        return t(
            "sync_ui.changed",
            "원격 일정이 먼저 변경되었습니다. 다시 동기화한 뒤 두 내용을 비교하세요.",
        )
    if http == "405":
        return t(
            "sync_ui.unsupported_service",
            "서비스에서 이 연결 방식을 허용하지 않습니다. 해당 서비스의 지원 정책을 확인하세요.",
        )
    messages = {
        "google_pull_invalid_datetime": t(
            "sync_google.invalid_datetime",
            "Google 일정의 날짜·시간 형식을 해석하지 못해 이번 가져오기를 중단했습니다. 기존 일정과 미전송 변경은 보존했습니다. Google Calendar에서 일정 날짜와 시간을 확인한 뒤 다시 동기화하세요.",
        ),
        "database_failed": t(
            "sync_google.database_failed",
            "가져온 일정을 앱에 저장하지 못해 이번 동기화를 중단했습니다. 기존 일정과 미전송 변경은 보존했습니다. 저장 공간과 앱 데이터 폴더의 쓰기 권한을 확인한 뒤 다시 동기화하세요.",
        ),
        "pull_apply_failed": t(
            "sync_google.apply_failed",
            "가져온 일정을 앱에 반영하지 못했습니다. 기존 일정과 미전송 변경은 보존했습니다. 일정 데이터와 앱 저장 환경을 확인한 뒤 다시 동기화하세요.",
        ),
        "google_fetch_failed": t(
            "sync_google.fetch_failed",
            "Google Calendar에서 일정을 가져오지 못했습니다. 인터넷 연결과 선택한 캘린더의 접근 권한을 확인한 뒤 다시 동기화하세요. 기존 일정은 보존했습니다.",
        ),
        "auth_client_type": t(
            "gcal_settings.auth_error_client_type",
            "선택한 파일은 웹 애플리케이션용 OAuth 인증 파일입니다. Google Cloud에서 '데스크톱 앱'으로 생성한 JSON 파일을 선택하세요.",
        ),
        "auth_client_invalid": t(
            "gcal_settings.auth_error_client_invalid",
            "올바른 Google OAuth 인증 파일이 아닙니다. '데스크톱 앱' 클라이언트의 JSON 파일을 다시 다운로드하세요.",
        ),
        "auth_client_missing": t(
            "gcal_settings.auth_error_client_missing",
            "Google OAuth 인증 파일을 찾을 수 없습니다. '데스크톱 앱' 클라이언트의 JSON 파일을 선택하세요.",
        ),
        "auth_redirect": t(
            "gcal_settings.auth_error_redirect",
            "Google이 인증 주소를 거절했습니다. '데스크톱 앱'으로 생성한 OAuth JSON 파일을 선택하세요.",
        ),
        "auth_timeout": t(
            "gcal_settings.auth_error_timeout",
            "인증 응답을 받지 못했습니다. 로그인 브라우저와 '데스크톱 앱' OAuth 파일을 확인한 뒤 인증을 다시 실행하세요.",
        ),
        "auth_denied": t(
            "gcal_settings.auth_error_denied",
            "Google 로그인이 거절되었거나 권한 동의가 취소되었습니다. 계정과 OAuth 앱의 접근 권한을 확인하세요.",
        ),
        "auth_browser": t(
            "gcal_settings.auth_error_browser",
            "로그인 브라우저를 열 수 없습니다. Windows 기본 브라우저 설정을 확인하세요.",
        ),
        "auth_listener": t(
            "gcal_settings.auth_error_listener",
            "인증 응답을 받을 로컬 주소를 열 수 없습니다. 보안 프로그램과 방화벽 설정을 확인하세요.",
        ),
        "auth_token_write": t(
            "gcal_settings.auth_error_token_write",
            "인증 정보를 저장하지 못했습니다. 저장 공간과 앱 데이터 폴더의 쓰기 권한을 확인하세요. 기존 연결 정보는 유지됩니다.",
        ),
        "completed_with_issues": t(
            "sync_ui.partial",
            "일부 일정의 동기화에 확인이 필요합니다. 문제 해결 탭에서 보류된 항목을 확인하세요.",
        ),
        "account_mismatch": t(
            "sync_ui.account_mismatch",
            "연결된 계정이 기존 일정의 계정과 다릅니다. 원래 계정으로 다시 연결하고 캘린더 목록을 확인하세요. 기존 일정과 미전송 변경은 보존했습니다.",
        ),
        "calendar_move": t(
            "gcal_focus.move_failed_help",
            "선택한 캘린더로 일정을 이동하지 못했습니다. 이동 대상은 유지했습니다. 인터넷 연결과 두 캘린더의 수정 권한을 확인한 뒤 다시 동기화하세요.",
        ),
        "calendar_move_unconfirmed": t(
            "gcal_focus.move_unconfirmed_help",
            "선택한 캘린더에서 이동한 일정을 확인하지 못했습니다. 새 사본을 만들지 않고 이동 대상을 유지했습니다. Google에서 일정 위치와 권한을 확인한 뒤 다시 동기화하세요.",
        ),
        "calendar_move_local_state": t(
            "gcal_focus.move_local_state_help",
            "Google의 일정 이동은 확인했지만 앱에 연결 정보를 저장하지 못했습니다. 같은 이동 대상으로 다시 동기화해 연결을 복구하세요.",
        ),
        "ics_access_denied": t(
            "sync_unified.ics_access_denied",
            "구독 주소의 접근이 거부되었습니다. 원래 서비스에서 공유 설정을 확인하거나 새 ICS 주소를 발급한 뒤 '구독 주소 수정'으로 변경하세요.",
        ),
        "ics_not_found": t(
            "sync_unified.ics_not_found",
            "구독 주소를 찾을 수 없거나 만료되었습니다. 원래 서비스의 최신 ICS 주소를 확인하고 '구독 주소 수정'으로 변경하세요.",
        ),
        "ics_rate_limited": t(
            "sync_unified.ics_rate_limited",
            "구독 서버의 요청 제한에 도달했습니다. 기존 일정은 보존했습니다. 잠시 후 다시 동기화하세요.",
        ),
        "ics_server_error": t(
            "sync_unified.ics_server_error",
            "구독 서버에 일시적인 오류가 있습니다. 기존 일정은 보존했습니다. 잠시 후 다시 동기화하세요.",
        ),
        "ics_processing_timeout": t(
            "sync_recovery.ics_processing_timeout",
            "반복 일정 계산이 오래 걸려 이번 갱신을 중단했습니다. 기존 일정은 보존했습니다. 원래 서비스에서 반복 일정이나 구독 범위를 확인하세요.",
        ),
        "pending_delete_unconfirmed": t(
            "sync_recovery.pending_delete_hint",
            "생성 결과를 확인하기 전에 앱에서 삭제한 일정입니다. 원격 일정의 일치 여부를 확인할 때까지 삭제를 보류합니다. '다시 확인'으로 조회할 수 있으며, 확인되지 않은 원격 일정은 삭제하지 않습니다.",
        ),
        "invalid_subscription_url": t(
            "sync_unified.invalid_ics", "HTTP · HTTPS · webcal 캘린더 구독 주소를 입력하세요."
        ),
        "invalid_timezone": t(
            "sync_ui.invalid_timezone", "올바른 시간대를 선택하세요. 예: Asia/Seoul"
        ),
        "invalid_calendar_timezone": t(
            "sync_ui.calendar_timezone",
            "구독 일정에 해석할 수 없는 시간대가 있습니다. 원래 캘린더 서비스의 시간대 설정이나 구독 주소를 확인하세요. 기존 일정은 보존했습니다.",
        ),
        "invalid_remote_event": t(
            "sync_ui.remote_event",
            "서비스에서 받은 일정 형식이 올바르지 않아 반영을 보류했습니다. 원래 일정의 날짜와 시간을 확인하고 다시 동기화하세요.",
        ),
        "response_too_large": t(
            "sync_unified.ics_too_large",
            "구독 일정 파일이 너무 큽니다. 원래 서비스에서 구독할 일정 범위를 줄인 뒤 다시 시도하세요.",
        ),
        "ics_fetch_failed": t(
            "sync_unified.ics_failed",
            "ICS 구독을 갱신하지 못했습니다. 전체 캘린더에서 구독 주소를 확인하고 다시 동기화하세요.",
        ),
        "invalid_event_range": t(
            "sync_ui.event_range",
            "종료 시각은 시작 시각보다 뒤여야 합니다. 일정의 날짜와 시간을 확인하세요.",
        ),
        "invalid_event_time": t(
            "sync_ui.event_time",
            "일정의 날짜 또는 시간대를 해석할 수 없습니다. 원래 일정의 시간 설정을 확인하세요.",
        ),
        "event_name_required": t("sync_ui.event_name", "일정 제목을 입력한 뒤 다시 동기화하세요."),
        "etag_required": t(
            "sync_ui.etag",
            "서비스에서 일정 버전 정보를 받지 못해 수정을 보류했습니다. 다시 동기화하세요.",
        ),
        "create_conflict": t(
            "sync_ui.create_conflict",
            "같은 생성 식별자의 다른 일정이 있어 생성을 보류했습니다. 원본을 덮어쓰지 않았습니다.",
        ),
        "conflict_snapshot_changed": t(
            "sync_ui.stale_conflict",
            "비교 후 일정 내용이 다시 바뀌었습니다. 다시 동기화하고 최신 내용을 비교하세요.",
        ),
        "network_unavailable": t(
            "sync_ui.network",
            "인터넷 연결을 확인하세요. 기존 일정은 보존되며 연결 복구 후 다시 시도합니다.",
        ),
        "login_required": t(
            "sync_ui.login", "계정을 다시 연결하세요. 자동 동기화에서는 로그인 창을 열지 않습니다."
        ),
        "credentials_required": t("sync_ui.credentials", "계정과 앱 전용 암호를 입력하세요."),
        "credential_protection_failed": t(
            "sync_ui.protection",
            "Windows 암호화 저장에 실패했습니다. 현재 Windows 사용자 환경을 확인하세요.",
        ),
        "calendar_access_lost": t(
            "sync_ui.access_lost",
            "선택한 캘린더의 접근 권한이 사라졌습니다. 기존 일정은 보존했습니다. 목록을 새로고침해 다시 선택하세요.",
        ),
        "sync_already_running": t(
            "sync_ui.busy", "이 계정의 동기화가 이미 진행 중입니다. 완료 후 다시 시도하세요."
        ),
        "calendar_report_incomplete": t(
            "sync_ui.incomplete",
            "일부 일정의 응답이 누락되어 이번 동기화를 중단했습니다. 다시 시도하세요.",
        ),
        "invalid_calendar_data": t(
            "sync_ui.invalid_data",
            "서비스에서 올바르지 않은 일정 데이터를 받았습니다. 이번 동기화는 반영하지 않았습니다.",
        ),
        "invalid_calendar_response": t(
            "sync_ui.invalid_response",
            "서비스 응답을 해석할 수 없습니다. 계정과 서비스 상태를 확인하세요.",
        ),
        "invalid_recurrence": t(
            "sync_ui.recurrence",
            "반복 일정 데이터를 해석하지 못했습니다. 서비스에서 반복 설정을 확인하세요.",
        ),
        "no_calendars": t(
            "sync_ui.no_calendars",
            "접근 가능한 캘린더가 없습니다. 서비스에서 캘린더를 먼저 만들거나 공유 권한을 확인하세요.",
        ),
        "calendar_discovery_failed": t(
            "sync_ui.discovery",
            "캘린더 위치를 찾지 못했습니다. 계정과 서비스의 CalDAV 지원 여부를 확인하세요.",
        ),
        "unsafe_caldav_url": t(
            "sync_ui.unsafe", "신뢰할 수 없는 서버 주소가 반환되어 연결을 중단했습니다."
        ),
        "unsafe_caldav_resource": t(
            "sync_ui.unsafe", "신뢰할 수 없는 서버 주소가 반환되어 연결을 중단했습니다."
        ),
        "event_read_only": t(
            "sync_ui.event_read_only",
            "반복·초대 일정은 조회 전용입니다. 원래 서비스에서 수정하거나 삭제하세요.",
        ),
        "calendar_read_only": t(
            "sync_ui.read_only", "읽기 전용 캘린더입니다. 원래 서비스에서 수정하세요."
        ),
        "recurrence_not_supported": t(
            "sync_ui.recurrence_edit", "반복 규칙은 원래 서비스에서 설정하세요."
        ),
        "remote_deleted": t(
            "sync_ui.remote_deleted", "서비스에서 삭제된 일정입니다. 로컬 사본을 보존했습니다."
        ),
        "delete_conflict": t(
            "sync_ui.delete_conflict", "삭제 전에 원격 내용이 바뀌어 삭제를 보류했습니다."
        ),
        "remote_identity_changed": t(
            "sync_ui.identity_changed",
            "서버 주소에 다른 일정이 연결되어 수정을 보류했습니다. 원래 서비스의 일정을 확인하세요.",
        ),
        "conflict": t("sync_ui.conflict", "양쪽에서 수정됨 · 내용을 비교하고 선택하세요."),
        "calendar_move_not_supported": t(
            "sync_ui.move",
            "연결된 일정의 캘린더 이동은 지원하지 않습니다. 원래 캘린더로 되돌리거나 사본을 만드세요.",
        ),
        "cancelled": t("sync_ui.cancelled", "작업이 취소되었습니다. 기존 일정은 보존됩니다."),
        "dependency_unavailable": t(
            "sync_ui.dependency",
            "동기화 구성요소가 누락되었습니다. 최신 프로그램을 다시 설치하세요.",
        ),
        "duplicate_remote_event": t(
            "sync_ui.duplicate", "중복된 일정 응답을 받았습니다. 안전을 위해 반영을 중단했습니다."
        ),
        "too_many_events": t(
            "sync_ui.too_many",
            "조회할 일정이 너무 많아 중단했습니다. 서비스에서 반복 일정 범위를 확인하세요.",
        ),
    }
    return messages.get(
        code,
        t(
            "sync_ui.failed",
            "작업을 완료하지 못했습니다. 기존 일정은 보존했습니다. 계정 설정을 확인하고 다시 시도하세요.",
        ),
    )


def conflict_text(issue, provider, zone="Asia/Seoul"):
    if not issue or not issue.get("remote_json") or not issue.get("local_json"):
        return ""
    try:
        local = json.loads(issue["local_json"])
        remote = provider.to_task(json.loads(issue["remote_json"]), zone)
    except (ValueError, KeyError, TypeError, CalendarSyncError):
        return ""
    if not isinstance(local, dict) or not isinstance(remote, dict):
        return ""

    def describe(task):
        return "\n".join(
            str(task.get(key) or "")
            for key in ("name", "deadline", "end_date", "location", "description")
        )

    return (
        t("sync_ui.local", "내 변경")
        + "\n"
        + describe(local)
        + "\n\n"
        + t("sync_ui.remote", "서비스 내용")
        + "\n"
        + describe(remote)
    )
