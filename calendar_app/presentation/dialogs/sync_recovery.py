# -*- coding: utf-8 -*-
"""Choose a useful next action from a provider's current public state."""

from math import ceil

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.sync_feedback import sync_error_message


def requires_account_reconnection(error):
    return error in {
        "login_required",
        "auth",
        "auth_required",
        "reauth_required",
        "credentials_required",
        "account_mismatch",
        "account_unverified",
        "remote_http_401",
        "graph_http_401",
        "auth_redirect",
        "auth_timeout",
        "auth_denied",
        "auth_browser",
        "auth_listener",
    } or str(error).startswith("auth_client_")


def sync_recovery_action(provider, state):
    """Presentation policy only; retries still pass through provider controllers."""
    try:
        remaining = max(0, ceil(float(state.get("retry_remaining") or 0)))
    except (TypeError, ValueError, OverflowError):
        remaining = 0
    error = state.get("error", "")
    action = {
        "kind": "manage",
        "section": "services",
        "remaining": remaining,
        "label": t("sync_redesign.connection_settings", "연결 설정"),
        "hint": t("sync_redesign.sync_available", "연결된 캘린더의 최신 일정을 가져옵니다."),
        "can_retry": bool(state.get("can_sync") and not state.get("busy")),
    }
    if state.get("busy"):
        action.update(
            kind="busy",
            label=t("sync_recovery.progress", "진행 상태 보기"),
            hint=t("sync_ui.working", "작업 중..."),
            can_retry=False,
        )
    elif requires_account_reconnection(error):
        action.update(
            kind="reconnect",
            label=t("sync_recovery.reconnect", "다시 연결"),
            hint=t("sync_recovery.auth_hint", "연결 설정에서 인증을 다시 실행하세요."),
            can_retry=False,
        )
    elif not state.get("connected"):
        action.update(
            kind="connect",
            label=t("sync_redesign.connect_account", "계정 연결"),
            hint=t(
                "sync_recovery.connect_hint", "계정을 연결하면 가져올 캘린더를 선택할 수 있습니다."
            ),
            can_retry=False,
        )
    elif state.get("paused"):
        action.update(
            kind="resume",
            label=t("sync_recovery.resume", "동기화 다시 켜기"),
            hint=t(
                "sync_recovery.paused_hint",
                "계정 연결은 유지됩니다. 연결 설정에서 동기화를 다시 켜세요.",
            ),
            can_retry=False,
        )
    elif state.get("needs_selection") or error in {"calendar_access_lost", "no_calendars"}:
        action.update(
            kind="select",
            section="calendars",
            label=t("sync_recovery.select", "가져올 캘린더 선택"),
            hint=t("sync_unified.select_first", "가져올 캘린더를 선택하고 저장하세요."),
            can_retry=False,
        )
    elif remaining:
        action.update(
            kind="wait",
            label=t("sync_redesign.connection_settings", "연결 설정"),
            hint=t(
                "sync_recovery.wait_hint",
                "서비스 요청 제한으로 {seconds}초 후 다시 시도할 수 있습니다.",
                seconds=remaining,
            ),
            can_retry=False,
        )
    elif provider == "google" and error == "dependency_unavailable":
        action.update(kind="repair", hint=sync_error_message(error), can_retry=False)
    elif state.get("issues"):
        action.update(
            kind="issues",
            section="issues",
            label=t("sync_recovery.review", "보류된 항목 확인"),
            hint=t(
                "sync_recovery.review_hint", "문제 해결에서 보류된 일정과 처리 방법을 확인하세요."
            ),
        )
    elif provider == "google" and (
        error
        in {
            "google_pull_invalid_datetime",
            "invalid_remote_event",
            "invalid_calendar_data",
            "invalid_calendar_response",
            "duplicate_remote_event",
            "calendar_report_incomplete",
            "database_failed",
            "pull_apply_failed",
            "google_fetch_failed",
            "network_unavailable",
            "auth_token_write",
        }
        or str(error).startswith("remote_http_")
    ):
        action.update(kind="retry", hint=sync_error_message(error))
    elif error:
        action.update(
            kind="retry",
            hint=t(
                "sync_recovery.retry_hint",
                "기존 일정은 유지됩니다. 원인을 확인한 뒤 다시 동기화하세요.",
            ),
        )
    if provider == "ics":
        action["section"] = "calendars"
        action["label"] = (
            t("sync_redesign.manage_subscriptions", "구독 관리")
            if state.get("connected")
            else t("sync_redesign.subscribe_url", "주소로 구독")
        )
    return action
