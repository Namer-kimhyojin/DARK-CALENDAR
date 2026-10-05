# -*- coding: utf-8 -*-
"""Shared user-facing recovery messages and plain-text conflict comparisons."""

from functools import wraps
import json
import sqlite3

from calendar_app.application.calendar_sync_contract import CalendarSyncError
from calendar_app.infrastructure.i18n import t


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
    )


def sync_error_message(code):
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
