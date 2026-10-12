# -*- coding: utf-8 -*-
import contextlib
from datetime import datetime
import os
import shutil
import sqlite3
from types import SimpleNamespace
import webbrowser
from zoneinfo import ZoneInfo, available_timezones

from PyQt6.QtCore import QSettings, QSize, Qt, QTimer, QTimeZone
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from calendar_app.app_paths import APP_NAME, APP_VENDOR, CREDENTIALS_PATH, TOKEN_PATH
from calendar_app.infrastructure.google_sync.oauth import (
    GoogleAuthError,
    load_desktop_client_config,
)
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_editor_styles import (
    build_settings_dialog_stylesheet,
    build_settings_style_bundle,
    build_task_editor_stylesheet,
)
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
    schedule_dialog_text_fit,
)
from calendar_app.presentation.dialogs.gcal_auth_worker import (
    GCalAuthWorker,
    GCalQueryWorker,
    GCalRevokeWorker,
)
from calendar_app.presentation.dialogs.sync_feedback import (
    google_sync_error_code,
    sync_error_message,
)
from calendar_app.shared.calendar_defaults import DEFAULT_CALENDAR_COLOR
from calendar_app.shared.datetime_utils import timezone_offset_for_name
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.icon_map import strip_leading_emoji as _se

_GCAL_STYLE_TEMPLATE = ""


def _gcal_auth_error_text(kind):
    messages = {
        "auth_client_type": (
            "client_type",
            "선택한 파일은 웹 애플리케이션용 OAuth 인증 파일입니다. Google Cloud에서 클라이언트 유형을 '데스크톱 앱'으로 생성하고 다운로드한 JSON 파일을 선택하세요. 웹용 파일은 redirect_uri_mismatch 오류를 일으킬 수 있습니다.",
        ),
        "auth_client_invalid": (
            "client_invalid",
            "올바른 Google OAuth 인증 파일이 아닙니다. Google Cloud에서 '데스크톱 앱' 클라이언트의 JSON 파일을 다시 다운로드하세요.",
        ),
        "auth_client_missing": (
            "client_missing",
            "인증 파일을 찾을 수 없습니다. Google Cloud에서 '데스크톱 앱' OAuth 클라이언트의 JSON 파일을 다운로드하고 선택하세요.",
        ),
        "auth_timeout": (
            "timeout",
            "3분 동안 인증 응답을 받지 못했습니다. 브라우저에 redirect_uri_mismatch가 표시되면 '데스크톱 앱' OAuth 파일인지 확인하세요. 파일을 확인한 뒤 인증을 다시 실행하세요.",
        ),
        "auth_cancelled": ("cancelled", "Google 인증을 취소했습니다. 기존 연결 정보는 유지됩니다."),
        "auth_browser": (
            "browser",
            "로그인 브라우저를 열 수 없습니다. Windows 기본 브라우저 설정을 확인한 뒤 다시 시도하세요.",
        ),
        "auth_listener": (
            "listener",
            "인증 응답을 받을 로컬 주소를 열 수 없습니다. 보안 프로그램과 방화벽 설정을 확인한 뒤 다시 시도하세요.",
        ),
        "auth_redirect": (
            "redirect",
            "Google이 인증 주소를 거절했습니다 (redirect_uri_mismatch). Google Cloud에서 '데스크톱 앱'으로 생성한 OAuth JSON 파일을 선택하세요.",
        ),
        "auth_denied": (
            "denied",
            "Google 로그인이 거절되었거나 권한 동의가 취소되었습니다. 계정과 OAuth 앱의 접근 권한을 확인한 뒤 다시 시도하세요.",
        ),
        "auth_token_write": (
            "token_write",
            "인증 정보를 저장하지 못했습니다. 저장 공간과 앱 데이터 폴더의 쓰기 권한을 확인하세요. 기존 연결 정보는 유지됩니다.",
        ),
        "auth_modules": (
            "modules",
            "Google Calendar 인증 구성 요소를 불러오지 못했습니다. 앱을 업데이트한 뒤 다시 시도하세요.",
        ),
    }
    key, fallback = messages.get(
        kind,
        (
            "failed",
            "Google 인증을 완료하지 못했습니다. 네트워크 연결과 데스크톱 앱용 OAuth 파일을 확인한 뒤 다시 시도하세요.",
        ),
    )
    return t(f"gcal_settings.auth_error_{key}", fallback)


def _build_gcal_stylesheet(tokens=None):
    return build_settings_dialog_stylesheet(tokens or get_dialog_theme_tokens())


def _gcal_runtime_style_bundle(tokens=None, metrics=None):
    return build_settings_style_bundle(
        tokens or get_dialog_theme_tokens(),
        metrics or get_dialog_metric_tokens(apply_overrides=True),
    )


def _gcal_editor_dialog_stylesheet(tokens=None, metrics=None):
    return build_task_editor_stylesheet(
        tokens or get_dialog_theme_tokens(),
        metrics or get_dialog_metric_tokens(apply_overrides=True),
    )


def _gcal_visibility_button_style(is_visible, tokens=None):
    tokens = dict(tokens or get_dialog_theme_tokens())
    if is_visible:
        return (
            f"QPushButton {{ color: {tokens.get('accent', '')}; "
            f"border: 1px solid {tokens.get('accent_soft_border', tokens.get('border', ''))}; }}"
        )
    return f"QPushButton {{ color: {tokens.get('text_muted', '')}; border: 1px solid {tokens.get('border', '')}; }}"


_COMMON_TIMEZONES = [
    "UTC",
    "Asia/Seoul",
    "Asia/Tokyo",
    "Asia/Singapore",
    "Asia/Bangkok",
    "Asia/Dubai",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Toronto",
    "Australia/Sydney",
    "Pacific/Auckland",
]


class GCalSettingsDialog(QDialog):
    def _open_other_services(self):
        if self.parent_app is not None:
            from PyQt6.QtCore import QTimer

            self.reject()
            if not self.property("syncHubChild"):
                QTimer.singleShot(
                    0, lambda: self.parent_app.open_calendar_sync_hub(section="calendars")
                )
            else:
                self.setProperty("returnToCalendars", True)

    def __init__(self, parent=None, initial_tab: str | None = None):
        super().__init__(parent)
        self.parent_app = parent
        self._initial_tab = initial_tab
        self.settings = (
            parent.settings
            if parent is not None and hasattr(parent, "settings")
            else QSettings(APP_VENDOR, APP_NAME)
        )
        apply_dialog_title(self, t("sync_unified.google_settings", "Google Calendar 세부 설정"))
        self.setAccessibleName(self.windowTitle())
        self.setSizeGripEnabled(True)
        self.setMinimumSize(740, 560)
        self.setProperty("_dc_preferred_size", QSize(980, 680))
        self.resize(980, 680)
        self._all_timezones = self._build_timezone_list()
        self._calendar_choices = []
        self._calendar_import_selection = {}
        self._calendar_import_checks = {}
        self._loading_settings = True
        self._settings_dirty = False
        self._applied_changes = False
        self._browse_creds_open = False
        self._auth_worker = None
        self._query_worker = None
        self._query_kind = None
        self._auth_close_result = None
        self._auth_calendars_loaded = False
        self._metadata_load_failed = False
        self._feedback_code = None
        self._nav_btns = []
        self._ui_tokens = get_dialog_theme_tokens()
        self._dialog_metrics = get_dialog_metric_tokens(apply_overrides=True)
        self._style_bundle = build_settings_style_bundle(self._ui_tokens, self._dialog_metrics)
        self._init_ui()
        schedule_dialog_text_fit(self)
        self._load_state()
        self._loading_settings = False
        self._connect_dirty_tracking()
        self._refresh_status()
        self._external_busy = None
        self._availability_timer = QTimer(self)
        self._availability_timer.setInterval(600)
        self._availability_timer.timeout.connect(self._refresh_operation_availability)
        self._availability_timer.start()
        self._refresh_operation_availability()
        # initial_tab으로 직접 이동
        if initial_tab == "calendar":
            self._switch_section(1)

    # ──────────────────────────────────────────────
    # UI 초기화
    # ──────────────────────────────────────────────

    def _init_ui(self):
        # Rebuild stylesheet on each dialog creation so token changes apply immediately.
        self.setStyleSheet(build_settings_dialog_stylesheet(self._ui_tokens))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 상태 헤더 (compact 한 줄) ──────────────
        root.addWidget(self._build_status_bar())
        root.addWidget(self._build_feedback_bar())

        # ── 사이드바 + 콘텐츠 영역 ──────────────────
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        body.addWidget(self._build_content_area(), 1)
        root.addLayout(body, 1)

        # ── 푸터 ────────────────────────────────────
        root.addWidget(self._build_footer())

        # 첫 섹션 활성화
        self._switch_section(0)

    # ──────────────────────────────────────────────
    # 상태 헤더 (compact bar)
    # ──────────────────────────────────────────────

    def _build_status_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("statusBar")
        bar.setStyleSheet(self._style_bundle["status_bar"])
        layout = QGridLayout(bar)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(4)

        # 상태 아이콘 + 텍스트
        self.status_title = QLabel()
        self.status_title.setProperty("role", "statusLabel")
        self.status_title.setStyleSheet(self._style_bundle["status_title_pending"])
        layout.addWidget(self.status_title, 0, 0)

        self.status_pill = QLabel()
        self.status_pill.setProperty("role", "pill")
        self.status_pill.setStyleSheet(self._style_bundle["status_pill_pending"])
        layout.addWidget(self.status_pill, 0, 1, 1, 1, Qt.AlignmentFlag.AlignLeft)

        # 계정 메타
        lbl_acc = QLabel(t("gcal_settings.meta_account", "계정"))
        lbl_acc.setProperty("role", "statusBarMeta")
        lbl_acc.setStyleSheet(self._style_bundle["meta_label"])
        layout.addWidget(lbl_acc, 1, 0)
        self.account_meta = (None, QLabel("-"))
        self.account_meta[1].setProperty("role", "statusBarMetaVal")
        self.account_meta[1].setStyleSheet(self._style_bundle["meta_value"])
        self.account_meta[1].setMinimumWidth(0)
        self.account_meta[1].setWordWrap(True)
        self.account_meta[1].setTextFormat(Qt.TextFormat.PlainText)
        self.account_meta[1].setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.account_meta[1], 1, 1)

        lbl_cal = QLabel(t("gcal_focus.import_meta", "가져오기"))
        lbl_cal.setProperty("role", "statusBarMeta")
        lbl_cal.setStyleSheet(self._style_bundle["meta_label"])
        layout.addWidget(lbl_cal, 1, 2)
        self.calendar_meta = (None, QLabel("-"))
        self.calendar_meta[1].setProperty("role", "statusBarMetaVal")
        self.calendar_meta[1].setStyleSheet(self._style_bundle["meta_value"])
        self.calendar_meta[1].setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.calendar_meta[1], 1, 3)

        lbl_sync = QLabel(t("gcal_settings.meta_last_sync", "마지막 동기화"))
        lbl_sync.setProperty("role", "statusBarMeta")
        lbl_sync.setStyleSheet(self._style_bundle["meta_label"])
        layout.addWidget(lbl_sync, 1, 4)
        self.last_sync_meta = (None, QLabel("-"))
        self.last_sync_meta[1].setProperty("role", "statusBarMetaVal")
        self.last_sync_meta[1].setStyleSheet(self._style_bundle["meta_value"])
        layout.addWidget(self.last_sync_meta[1], 1, 5)
        layout.setColumnStretch(1, 1)
        return bar

    def _build_feedback_bar(self):
        bar = QFrame()
        bar.setStyleSheet(self._style_bundle["subtle_card"])
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 10, 18, 10)
        self.connection_feedback = self._help_label("")
        self.connection_feedback.setAccessibleName(t("gcal_ux.feedback", "연결 및 동기화 안내"))
        self.connection_feedback.setTextFormat(Qt.TextFormat.PlainText)
        self.connection_feedback.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.connection_feedback, 1)
        self.recovery_btn = QPushButton(t("gcal_ux.review_connection", "연결 확인"))
        self._apply_section_button_style(self.recovery_btn, "secondary")
        self.recovery_btn.clicked.connect(self._run_recovery_action)
        layout.addWidget(self.recovery_btn)
        self.cancel_operation_btn = QPushButton(t("common.cancel", "취소"))
        self._apply_section_button_style(self.cancel_operation_btn, "secondary")
        self.cancel_operation_btn.clicked.connect(self._cancel_operation)
        self.cancel_operation_btn.hide()
        layout.addWidget(self.cancel_operation_btn)
        self.feedback_bar = bar
        bar.hide()
        return bar

    def _show_inline_feedback(self, text, tone="help", code=None):
        self._feedback_code = code
        self._set_feedback_label(self.connection_feedback, text, tone)
        self.feedback_bar.setVisible(bool(text))
        busy = self._auth_worker is not None or self._query_worker is not None
        self.recovery_btn.setVisible(tone in {"error", "warning"} and not busy)
        if code in {"auth_client_missing", "auth_client_invalid", "auth_client_type"}:
            label = t("gcal_ux.review_file", "인증 파일 확인")
        elif code in {
            "account_mismatch",
            "account_unverified",
            "auth_required",
            "reauth_required",
            "auth",
            "auth_denied",
            "auth_timeout",
        }:
            label = t("gcal_ux.reconnect", "계정 다시 연결")
        else:
            label = t("gcal_ux.review_connection", "연결 확인")
        self.recovery_btn.setText(label)

    def _run_recovery_action(self):
        self._switch_section(0)
        if self._feedback_code in {
            "auth_client_missing",
            "auth_client_invalid",
            "auth_client_type",
        }:
            self.credentials_details_btn.setChecked(True)
            self.creds_path_edit.setFocus()
        else:
            self.auth_btn.setFocus()

    def _set_operation_state(self, busy, text="", *, cancellable=True):
        for widget in (
            self.creds_path_edit,
            self.browse_creds_btn,
            self.credentials_details_btn,
            self.enable_cb,
            self.auto_sync_cb,
            self.hide_completed_check,
            self.timezone_combo,
            self.detect_timezone_btn,
            self.timezone_details_btn,
            self.import_list,
            self.test_access_btn,
            self.load_calendars_btn,
            self.auth_btn,
            self.reset_btn,
            self.reset_sync_state_btn,
        ):
            widget.setEnabled(not busy)
        self.save_btn.setEnabled(
            not busy and not self._metadata_load_failed and self._settings_dirty
        )
        self._update_auto_sync_controls()
        self.cancel_operation_btn.setVisible(busy and cancellable)
        self.cancel_operation_btn.setEnabled(True)
        if busy:
            if text:
                self._show_inline_feedback(text)
            if cancellable:
                self.cancel_operation_btn.setFocus()

    def _parent_google_busy(self):
        coordinator = getattr(self.parent_app, "_calendar_sync_coordinator", None)
        if coordinator and getattr(coordinator, "states", {}).get("google", {}).get("busy"):
            return True
        return any(
            worker and worker.isRunning()
            for worker in (
                getattr(self.parent_app, "_sync_worker", None),
                getattr(self.parent_app, "_auth_worker", None),
            )
        )

    def _refresh_operation_availability(self):
        if self._auth_worker is not None or self._query_worker is not None:
            return
        busy = self._parent_google_busy()
        if busy == self._external_busy:
            return
        self._external_busy = busy
        self._set_operation_state(busy, cancellable=False)
        if busy:
            self._show_inline_feedback(
                t(
                    "gcal_ux.sync_busy",
                    "Google 동기화가 진행 중입니다. 완료되면 설정을 변경할 수 있습니다.",
                )
            )
        else:
            if self.connection_feedback.text() == t(
                "gcal_ux.sync_busy",
                "Google 동기화가 진행 중입니다. 완료되면 설정을 변경할 수 있습니다.",
            ):
                self._show_inline_feedback("")
            self._refresh_status()

    def _cancel_operation(self):
        worker = self._auth_worker or self._query_worker
        if worker is None or self._query_kind == "disconnect" and self._query_worker is not None:
            return
        worker.requestInterruption()
        self.cancel_operation_btn.setEnabled(False)
        self._show_inline_feedback(
            t("gcal_ux.cancelling", "작업을 취소하고 있습니다. 기존 연결과 일정은 유지됩니다.")
        )

    # ──────────────────────────────────────────────
    # 사이드바
    # ──────────────────────────────────────────────

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setStyleSheet(self._style_bundle["sidebar_shell"])
        sidebar.setFixedWidth(152)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setSpacing(2)

        nav_items = [
            (
                t("gcal_focus.nav_connection", "계정 연결"),
                _ic(ICON.LINK, color=self._ui_tokens["text_primary"]),
            ),
            (
                t("gcal_focus.nav_calendars", "가져올 캘린더"),
                _ic(ICON.VIEW_CALENDAR, color=self._ui_tokens["text_primary"]),
            ),
            (
                t("gcal_focus.nav_sync", "동기화 설정"),
                _ic(ICON.SYNC, color=self._ui_tokens["text_primary"]),
            ),
            (
                t("gcal_focus.nav_issues", "문제 해결"),
                _ic(ICON.SEARCH, color=self._ui_tokens["text_primary"]),
            ),
            (
                t("gcal_focus.nav_help", "설정 도움말"),
                _ic(ICON.DOCS, color=self._ui_tokens["text_primary"]),
            ),
        ]

        for idx, (label, nav_icon) in enumerate(nav_items):
            btn = QPushButton(_se(label))
            btn.setIcon(nav_icon)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setAccessibleName(_se(label))
            btn.setStyleSheet(self._style_bundle["nav_button"])
            btn.clicked.connect(lambda _, i=idx: self._switch_section(i))
            self._nav_btns.append(btn)
            layout.addWidget(btn)

        layout.addStretch(1)
        return sidebar

    def _switch_section(self, idx: int):
        for i, btn in enumerate(self._nav_btns):
            is_current = i == idx
            btn.setChecked(is_current)
            btn.setStyleSheet(
                self._style_bundle["nav_button_active" if is_current else "nav_button"]
            )
        self._stack.setCurrentIndex(idx)

    # ──────────────────────────────────────────────
    # 콘텐츠 영역 (QStackedWidget)
    # ──────────────────────────────────────────────

    def _build_content_area(self) -> QWidget:
        container = QWidget()
        container.setObjectName("contentArea")
        container.setStyleSheet(self._style_bundle["content_area"])
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._wrap_scroll(self._build_connection_section()))  # 0
        self._stack.addWidget(self._wrap_scroll(self._build_calendar_section()))  # 1
        self._stack.addWidget(self._wrap_scroll(self._build_sync_section()))  # 2
        self._stack.addWidget(self._wrap_scroll(self._build_diagnostics_section()))  # 3
        self._stack.addWidget(self._wrap_scroll(self._build_guide_section()))  # 4

        layout.addWidget(self._stack)
        return container

    def _wrap_scroll(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setStyleSheet(self._style_bundle["scroll_shell"])
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(widget)
        return scroll

    # ──────────────────────────────────────────────
    # 섹션 0: 연결
    # ──────────────────────────────────────────────

    def _build_connection_section(self) -> QWidget:
        page = QWidget()
        # Inherited background was removed to fix dropdown transparency issues on Windows
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        card = self._make_card(t("gcal_focus.connection_title", "Google 계정 연결"))
        cl = card.layout()
        cl.addWidget(
            self._help_label(
                t(
                    "gcal_focus.connection_help",
                    "계정을 한 번 연결하면 선택한 Google 캘린더의 일정을 가져오고 변경 사항을 동기화할 수 있습니다.",
                )
            )
        )

        # Enable toggle
        enable_row = QHBoxLayout()
        self.enable_cb = QCheckBox(t("gcal_settings.enable", "Google Calendar 동기화 사용"))
        self.enable_cb.setStyleSheet(self._style_bundle["check_toggle"])
        enable_row.addWidget(self.enable_cb)
        enable_row.addStretch(1)
        cl.addLayout(enable_row)
        self.connection_next_step = self._help_label("")
        cl.addWidget(self.connection_next_step)

        auth_row = QHBoxLayout()
        self.auth_btn = QPushButton(t("gcal_focus.connect_account", "Google 계정 연결"))
        self.auth_btn.setIcon(_ic(ICON.AUTH, color=self._ui_tokens["text_primary"]))
        self._apply_section_button_style(self.auth_btn, "accent")
        self.auth_btn.setAutoDefault(False)
        self.auth_btn.clicked.connect(self.run_auth)
        auth_row.addWidget(self.auth_btn)
        self.reset_btn = QPushButton(t("gcal_focus.disconnect", "연결 해제"))
        self._apply_section_button_style(self.reset_btn, "secondary")
        self.reset_btn.setAutoDefault(False)
        self.reset_btn.clicked.connect(self.reset_auth)
        auth_row.addWidget(self.reset_btn)
        auth_row.addStretch(1)
        cl.addLayout(auth_row)

        self.credentials_details_btn = QPushButton(
            t("gcal_ux.credentials_details", "인증 파일 · 연결 도움말")
        )
        self.credentials_details_btn.setCheckable(True)
        self._apply_section_button_style(self.credentials_details_btn, "secondary")
        cl.addWidget(self.credentials_details_btn)
        self.credentials_panel = QWidget()
        credentials_layout = QVBoxLayout(self.credentials_panel)
        credentials_layout.setContentsMargins(0, 0, 0, 0)
        credentials_layout.setSpacing(8)
        self.credentials_details_btn.toggled.connect(self.credentials_panel.setVisible)

        # Credentials
        credentials_layout.addWidget(
            self._field_label(t("gcal_settings.creds_label", "OAuth 인증 파일"))
        )
        creds_row = QHBoxLayout()
        creds_row.setSpacing(8)
        self.creds_path_edit = QLineEdit()
        self._apply_input_style(self.creds_path_edit, "line")
        self.creds_path_edit.setPlaceholderText(
            t("gcal_settings.creds_placeholder", "credentials.json 경로")
        )
        self.creds_path_edit.setAccessibleName(t("gcal_settings.creds_label", "OAuth 인증 파일"))
        browse_btn = QPushButton(t("gcal_settings.browse", "파일 선택"))
        self.browse_creds_btn = browse_btn
        self._apply_section_button_style(browse_btn, "secondary")
        browse_btn.clicked.connect(self.browse_creds)
        creds_row.addWidget(self.creds_path_edit, 1)
        creds_row.addWidget(browse_btn)
        credentials_layout.addLayout(creds_row)
        credentials_layout.addWidget(
            self._help_label(
                t("gcal_settings.creds_help", "Desktop OAuth 클라이언트 JSON만 지원합니다.")
            )
        )

        help_btn = QPushButton(t("gcal_ux.setup_help", "인증 파일 준비 방법"))
        self._apply_section_button_style(help_btn, "secondary")
        help_btn.clicked.connect(lambda: self._switch_section(4))
        credentials_layout.addWidget(help_btn)
        cl.addWidget(self.credentials_panel)
        self.credentials_panel.hide()
        cl.addWidget(self._make_divider())

        # Test access
        test_row = QHBoxLayout()
        test_row.setSpacing(10)
        self.test_access_btn = QPushButton(t("gcal_settings.test_access", "캘린더 접근 테스트"))
        self.test_access_btn.setIcon(_ic(ICON.SEARCH, color=self._ui_tokens["text_primary"]))
        self._apply_section_button_style(self.test_access_btn, "accent")
        self.test_access_btn.clicked.connect(self._test_calendar_access)
        self.test_access_result = QLabel(
            t("gcal_settings.test_access_idle", "아직 테스트하지 않았습니다.")
        )
        self.test_access_result.setProperty("role", "help")
        self.test_access_result.setStyleSheet(self._style_bundle["help"])
        self.test_access_result.setWordWrap(True)
        test_row.addWidget(self.test_access_btn, 0)
        test_row.addWidget(self.test_access_result, 1)
        cl.addLayout(test_row)

        layout.addWidget(card)
        layout.addStretch(1)
        return page

    # ──────────────────────────────────────────────
    # 섹션 1: 캘린더
    # ──────────────────────────────────────────────

    # ── 캘린더 카드 아이템 (테이블 대체) ──────────────────────────────────

    def _build_calendar_section(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        cal_card = self._make_card(t("gcal_focus.import_title", "Google에서 가져올 캘린더"))
        cl = cal_card.layout()
        cl.addWidget(
            self._help_label(
                t(
                    "gcal_focus.import_help",
                    "가져올 캘린더를 선택하세요. 읽기 전용 캘린더도 가져올 수 있습니다. 변경 내용은 설정 저장을 누르면 적용됩니다.",
                )
            )
        )

        # Keep legacy APIs without exposing a second default-calendar picker.
        self.cal_id_edit = QLineEdit(page)
        self._apply_input_style(self.cal_id_edit, "line")
        self.cal_id_edit.setPlaceholderText("primary")
        self.cal_id_edit.setAccessibleName(
            t("gcal_settings.calendar_id_label", "GCal 쓰기 대상 캘린더 ID")
        )
        self.cal_id_edit.textChanged.connect(self._sync_edit_to_combo)
        self.cal_id_edit.hide()

        picker_row = QHBoxLayout()
        picker_row.setSpacing(8)
        self.calendar_choice_combo = QComboBox(page)
        self.calendar_choice_combo.setAccessibleName(
            t("sync_unified.google_write_target", "Google 쓰기 대상")
        )
        self.calendar_choice_combo.view().setAutoFillBackground(True)
        self._apply_combo_input_style(self.calendar_choice_combo)
        self.calendar_choice_combo.currentIndexChanged.connect(self._on_calendar_choice_changed)
        self.calendar_choice_combo.hide()
        self.load_calendars_btn = QPushButton(t("gcal_focus.refresh_calendars", "목록 새로고침"))
        self._apply_section_button_style(self.load_calendars_btn, "accent")
        self.load_calendars_btn.clicked.connect(self._load_accessible_calendars)
        picker_row.addWidget(self.load_calendars_btn)
        picker_row.addStretch(1)
        cl.addLayout(picker_row)

        self.import_list = QWidget()
        self.import_list.setAccessibleName(t("gcal_focus.import_title", "Google에서 가져올 캘린더"))
        self.import_list_layout = QVBoxLayout(self.import_list)
        self.import_list_layout.setContentsMargins(0, 0, 0, 0)
        self.import_list_layout.setSpacing(8)
        cl.addWidget(self.import_list)

        self.calendar_choice_hint = self._help_label(
            t(
                "gcal_settings.calendar_choice_hint",
                "인증 완료 후 내 계정에서 사용 가능한 캘린더 목록을 불러올 수 있습니다.",
            )
        )
        cl.addWidget(self.calendar_choice_hint)

        self.go_to_auth_btn = QPushButton(t("gcal_settings.go_to_auth", "인증 설정으로 이동"))
        self._apply_section_button_style(self.go_to_auth_btn, "secondary")
        self.go_to_auth_btn.setFixedWidth(140)
        self.go_to_auth_btn.clicked.connect(lambda: self._switch_section(0))
        self.go_to_auth_btn.hide()
        cl.addWidget(self.go_to_auth_btn)

        layout.addWidget(cal_card)
        manage_card = self._make_card(
            t("gcal_focus.main_calendar_title", "화면 표시와 기본 캘린더")
        )
        manage_card.layout().addWidget(
            self._help_label(
                t(
                    "gcal_focus.main_calendar_help",
                    "가져온 일정의 화면 표시, 색상과 새 일정의 기본 저장 캘린더는 메인 캘린더에서 설정하세요. 가져오기를 꺼도 이미 받은 일정은 보존됩니다.",
                )
            )
        )
        manage_card.layout().addWidget(
            self._help_label(
                t(
                    "gcal_focus.import_pause_help",
                    "가져오기를 끄면 Google의 새 변경 사항을 받지 않습니다. 기존 일정은 남아 있으며, 편집한 내용은 Google 자동 동기화가 켜져 있거나 직접 동기화할 때 전송됩니다.",
                )
            )
        )
        manage = QPushButton(t("gcal_focus.manage_main", "메인 캘린더 관리 열기"))
        self._apply_section_button_style(manage, "secondary")
        manage.clicked.connect(self._open_other_services)
        manage_card.layout().addWidget(manage)
        layout.addWidget(manage_card)
        layout.addStretch(1)

        self._refresh_calendar_table()
        return page

    # ── 캘린더 관리 테이블 헬퍼 ─────────────────────────────────────────

    def _refresh_calendar_table(self):
        coordinator = getattr(self.parent_app, "_calendar_sync_coordinator", None)
        if coordinator:
            coordinator.refresh()
        if hasattr(self, "import_list_layout"):
            self._render_calendar_imports()

    def _render_calendar_imports(self):
        """Show persisted Google metadata while retaining unsaved import choices."""
        from calendar_app.infrastructure.db.calendar_repo import (
            is_calendar_row_read_only,
            list_calendars,
        )

        try:
            calendars = [
                row for row in list_calendars(include_inactive=True) if row.get("type") == "gcal"
            ]
        except (sqlite3.Error, OSError, RuntimeError):
            calendars = []
            self._metadata_load_failed = True
        else:
            self._metadata_load_failed = False
            known_ids = {str(row.get("id") or "") for row in calendars}
            self._calendar_import_selection = {
                cid: checked
                for cid, checked in self._calendar_import_selection.items()
                if cid in known_ids
            }
        while self.import_list_layout.count():
            item = self.import_list_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self._calendar_import_checks = {}
        if not calendars:
            message = (
                t(
                    "gcal_ux.metadata_unavailable",
                    "저장된 캘린더 목록을 읽지 못했습니다. 선택 내용은 유지했습니다. 목록을 다시 확인한 뒤 저장하세요.",
                )
                if self._metadata_load_failed
                else t(
                    "gcal_focus.no_calendars",
                    "등록된 Google 캘린더가 없습니다. 계정을 연결한 뒤 목록을 새로고침하세요.",
                )
            )
            self.import_list_layout.addWidget(self._help_label(message))
            if hasattr(self, "save_btn"):
                self.save_btn.setEnabled(not self._metadata_load_failed and self._settings_dirty)
            return
        sync = getattr(self.parent_app, "gcal_sync", None)
        idle_hint = t(
            "gcal_settings.calendar_choice_hint",
            "인증 완료 후 내 계정에서 사용 가능한 캘린더 목록을 불러올 수 있습니다.",
        )
        if (
            sync
            and getattr(sync, "is_authenticated", False)
            and self.calendar_choice_hint.text() in ("", idle_hint)
        ):
            self._set_feedback_label(
                self.calendar_choice_hint,
                t(
                    "gcal_focus.list_loaded",
                    "{count}개 캘린더를 확인했습니다. 가져올 캘린더를 선택한 뒤 설정을 저장하세요.",
                    count=len(calendars),
                ),
            )
        for calendar in calendars:
            calendar_id = str(calendar.get("id") or "")
            if not calendar_id:
                continue
            row = QFrame()
            row.setStyleSheet(self._style_bundle["subtle_card"])
            line = QHBoxLayout(row)
            line.setContentsMargins(12, 10, 12, 10)
            text = QVBoxLayout()
            name = str(calendar.get("name") or calendar.get("gcal_calendar_id") or calendar_id)
            name_label = QLabel(name)
            name_label.setTextFormat(Qt.TextFormat.PlainText)
            name_label.setWordWrap(True)
            name_label.setStyleSheet(self._style_bundle["meta_value"])
            text.addWidget(name_label)
            hint = (
                t("gcal_focus.readonly", "일정 가져오기 · 읽기 전용")
                if is_calendar_row_read_only(calendar)
                else t("gcal_focus.writable", "일정 가져오기 · 편집 가능")
            )
            if calendar.get("is_default"):
                hint += " · " + t(
                    "gcal_focus.default_import_warning",
                    "기본 저장 캘린더: 가져오기를 끄면 기본 저장 대상이 변경됩니다.",
                )
            text.addWidget(self._help_label(hint))
            line.addLayout(text, 1)
            configured = self.settings.value("gcal_import_selection_configured", False, type=bool)
            active_default = bool(calendar.get("is_active", True))
            if not configured:
                active_default = active_default or bool(calendar.get("is_visible", True))
            active = self._calendar_import_selection.setdefault(calendar_id, active_default)
            checkbox = QCheckBox(t("gcal_focus.import_toggle", "가져오기"))
            checkbox.setAccessibleName(
                t("gcal_focus.import_accessible", "{name} 일정 가져오기", name=name)
            )
            checkbox.setStyleSheet(self._style_bundle["check_toggle"])
            checkbox.setChecked(active)
            checkbox.toggled.connect(
                lambda checked, cid=calendar_id: self._set_import_selection(cid, checked)
            )
            self._calendar_import_checks[calendar_id] = checkbox
            line.addWidget(checkbox)
            self.import_list_layout.addWidget(row)
        if hasattr(self, "save_btn"):
            self.save_btn.setEnabled(
                self._auth_worker is None and self._query_worker is None and self._settings_dirty
            )

    def _set_import_selection(self, calendar_id, checked):
        self._calendar_import_selection[calendar_id] = bool(checked)
        self._mark_settings_dirty()
        self._refresh_meta()

    def _connect_dirty_tracking(self):
        for widget in (self.enable_cb, self.auto_sync_cb, self.hide_completed_check):
            widget.toggled.connect(self._mark_settings_dirty)
        self.creds_path_edit.textChanged.connect(self._mark_settings_dirty)
        self.interval_spin.valueChanged.connect(self._mark_settings_dirty)
        self.quick_interval_spin.valueChanged.connect(self._mark_settings_dirty)
        self.timezone_combo.currentTextChanged.connect(self._mark_settings_dirty)

    def _mark_settings_dirty(self, *_):
        if self._loading_settings:
            return
        self._settings_dirty = True
        self.unsaved_label.setText(
            t(
                "gcal_ux.unsaved",
                "변경 내용은 저장 후 적용됩니다. 닫으면 저장하지 않은 변경은 취소됩니다.",
            )
        )
        self.save_btn.setEnabled(
            self._auth_worker is None
            and self._query_worker is None
            and not self._metadata_load_failed
        )

    def _set_query_feedback(self, text, tone="help", code=None):
        self._set_feedback_label(self.test_access_result, text, tone)
        self._set_feedback_label(self.calendar_choice_hint, text, tone)
        self._show_inline_feedback(text, tone, code)

    def _validate_calendar_account(self, calendars, *, sync=None):
        from calendar_app.infrastructure.google_sync.engine import (
            _assert_primary_account_identity,
            _PrimaryAccountMismatchError,
        )

        service = sync if sync is not None else getattr(self.parent_app, "gcal_sync", None)
        identity = SimpleNamespace(settings=self.settings, gcal_sync=service)
        try:
            _assert_primary_account_identity(identity, calendars)
            if getattr(service, "_account_identity_mismatch", False):
                raise _PrimaryAccountMismatchError(
                    getattr(service, "_account_identity_error_kind", None) or "account_mismatch"
                )
        except _PrimaryAccountMismatchError as exc:
            self.settings.setValue("sync_google_last_error", exc.code)
            self._set_query_feedback(sync_error_message(exc.code), "error", exc.code)
            coordinator = getattr(self.parent_app, "_calendar_sync_coordinator", None)
            if coordinator:
                coordinator.refresh()
            return False
        if any(
            isinstance(item, dict) and item.get("primary") is True for item in calendars
        ) and self.settings.value("sync_google_last_error") in {
            "account_mismatch",
            "account_unverified",
        }:
            self.settings.setValue("sync_google_last_error", "")
            coordinator = getattr(self.parent_app, "_calendar_sync_coordinator", None)
            if coordinator:
                coordinator.refresh()
        return True

    def _build_sync_section(self) -> QWidget:
        page = QWidget()
        # Inherited background was removed to fix dropdown transparency issues on Windows
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        card = self._make_card(t("gcal_settings.advanced_title", "동기화 동작"))
        cl = card.layout()

        cl.addWidget(
            self._help_label(
                t("gcal_settings.advanced_summary", "대부분의 경우 기본값으로도 충분합니다.")
            )
        )
        self.auto_sync_cb = QCheckBox(t("gcal_focus.auto_sync", "Google 자동 동기화"))
        self.auto_sync_cb.setStyleSheet(self._style_bundle["check_toggle"])
        self.auto_sync_cb.setChecked(self.settings.value("sync_google_auto", True, type=bool))
        cl.addWidget(self.auto_sync_cb)
        cl.addWidget(
            self._help_label(
                t(
                    "gcal_focus.auto_sync_help",
                    "켜면 정기적으로 동기화하고 일정 편집 후 변경 사항을 전송합니다. 꺼도 메인 화면에서 직접 동기화할 수 있습니다.",
                )
            )
        )
        cl.addWidget(self._make_divider())

        cl.addWidget(self._field_label(t("gcal_settings.sync_interval_label", "정기 동기화 간격")))
        interval_row = QHBoxLayout()
        interval_row.setSpacing(8)
        self.interval_spin = QSpinBox()
        self._apply_input_style(self.interval_spin, "spin")
        self.interval_spin.setRange(1, 240)
        self.interval_spin.setSuffix(t("gcal_settings.minutes_suffix", " 분"))
        self.interval_spin.setFixedWidth(110)
        interval_row.addWidget(self.interval_spin)
        interval_row.addWidget(
            self._help_label(t("gcal_settings.sync_interval_hint", "1 ~ 240분 사이로 설정하세요.")),
            1,
        )
        cl.addLayout(interval_row)

        cl.addSpacing(10)

        cl.addWidget(
            self._field_label(t("gcal_settings.quick_interval_label", "편집 후 빠른 동기화"))
        )
        quick_row = QHBoxLayout()
        quick_row.setSpacing(8)
        self.quick_interval_spin = QSpinBox()
        self._apply_input_style(self.quick_interval_spin, "spin")
        self.quick_interval_spin.setRange(5, 300)
        self.quick_interval_spin.setSuffix(t("gcal_settings.seconds_suffix", " 초"))
        self.quick_interval_spin.setFixedWidth(110)
        quick_row.addWidget(self.quick_interval_spin)
        quick_row.addWidget(
            self._help_label(
                t("gcal_settings.quick_interval_hint", "5 ~ 300초 사이로 설정하세요.")
            ),
            1,
        )
        cl.addLayout(quick_row)
        self.auto_sync_cb.toggled.connect(self._update_auto_sync_controls)
        self._update_auto_sync_controls()

        cl.addWidget(self._make_divider())

        # [10] Hide completed events in GCal
        self.hide_completed_check = QCheckBox(
            t("gcal_settings.hide_completed", "완료된 일정 구글 캘린더에서 숨기기")
        )
        self.hide_completed_check.setStyleSheet(self._style_bundle["check_toggle"])
        self.hide_completed_check.setChecked(
            self.settings.value("gcal_hide_completed_in_gcal", "false") == "true"
        )
        cl.addWidget(self.hide_completed_check)
        cl.addWidget(
            self._help_label(
                t(
                    "gcal_settings.hide_completed_help",
                    "일정을 완료로 표시하면 구글 캘린더에서 자동으로 숨깁니다.",
                )
            )
        )

        cl.addWidget(self._make_divider())
        cl.addWidget(
            self._help_label(
                t(
                    "gcal_settings.advanced_help",
                    "편집이 잦을 때는 빠른 동기화를, 백그라운드 부하를 줄이려면 정기 동기화 간격을 늘리세요.",
                )
            )
        )

        layout.addWidget(card)

        # ── 시간대 카드 ───────────────────────────────────────────────
        tz_card = self._make_card(t("gcal_settings.timezone_label", "시간대"))
        tl = tz_card.layout()

        tz_row = QHBoxLayout()
        tz_row.setSpacing(8)
        self.timezone_combo = QComboBox()
        self.timezone_combo.setEditable(True)
        self.timezone_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.timezone_combo.setMaxVisibleItems(20)
        self.timezone_combo.view().setAutoFillBackground(True)
        self.timezone_combo.currentTextChanged.connect(self._refresh_timezone_preview)

        completer = QCompleter(self._all_timezones, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.timezone_combo.setCompleter(completer)
        if self.timezone_combo.lineEdit():
            self.timezone_combo.lineEdit().setPlaceholderText(
                t("gcal_settings.timezone_search_placeholder", "도시명 검색 (예: Seoul)...")
            )
        self._apply_combo_input_style(self.timezone_combo)

        detect_btn = QPushButton(t("gcal_settings.detect_timezone", "현재 시간대 사용"))
        self.detect_timezone_btn = detect_btn
        self._apply_section_button_style(detect_btn, "secondary")
        detect_btn.clicked.connect(self._apply_system_timezone)
        tz_row.addWidget(self.timezone_combo, 1)
        tz_row.addWidget(detect_btn)
        tl.addLayout(tz_row)

        self.timezone_preview = QLabel()
        self.timezone_preview.setProperty("role", "help")
        self.timezone_preview.setStyleSheet(self._style_bundle["help"])
        self.timezone_preview.setWordWrap(True)
        tl.addWidget(self.timezone_preview)

        self.timezone_details_btn = QPushButton(
            t("gcal_focus.timezone_details", "시간대 · 고급 설정")
        )
        self.timezone_details_btn.setCheckable(True)
        self._apply_section_button_style(self.timezone_details_btn, "secondary")
        self.timezone_details_btn.toggled.connect(tz_card.setVisible)
        layout.addWidget(self.timezone_details_btn)
        tz_card.hide()
        self.timezone_card = tz_card
        layout.addWidget(tz_card)
        layout.addStretch(1)
        return page

    def _update_auto_sync_controls(self, *_):
        enabled = (
            self.auto_sync_cb.isChecked()
            and self._auth_worker is None
            and self._query_worker is None
            and not getattr(self, "_external_busy", False)
        )
        self.interval_spin.setEnabled(enabled)
        self.quick_interval_spin.setEnabled(enabled)

    # ──────────────────────────────────────────────
    # 섹션 3: 진단
    # ──────────────────────────────────────────────

    def _build_diagnostics_section(self) -> QWidget:
        page = QWidget()
        # Inherited background was removed to fix dropdown transparency issues on Windows
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        card = self._make_card(t("gcal_settings.diagnostics_title", "Sync Diagnostics"))
        cl = card.layout()

        cl.addWidget(
            self._help_label(
                t(
                    "gcal_settings.diagnostics_summary",
                    "Check current sync health, pending issues, and repair the local sync cache when needed.",
                )
            )
        )
        cl.addWidget(self._make_divider())

        meta_grid = QGridLayout()
        meta_grid.setHorizontalSpacing(8)
        meta_grid.setVerticalSpacing(8)
        self.issue_meta = self._make_meta_box(t("gcal_settings.meta_issues", "Open issues"))
        self.delete_queue_meta = self._make_meta_box(
            t("gcal_settings.meta_delete_queue", "Delete queue")
        )
        self.bound_calendar_meta = self._make_meta_box(
            t("gcal_settings.meta_bound_calendar", "Bound calendar")
        )
        self.last_error_meta = self._make_meta_box(t("gcal_settings.meta_last_error", "Last error"))
        meta_grid.addWidget(self.issue_meta[0], 0, 0)
        meta_grid.addWidget(self.delete_queue_meta[0], 0, 1)
        meta_grid.addWidget(self.bound_calendar_meta[0], 1, 0)
        meta_grid.addWidget(self.last_error_meta[0], 1, 1)
        cl.addLayout(meta_grid)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.open_issues_btn = QPushButton(t("gcal_settings.open_issues", "Open Issues"))
        self._apply_section_button_style(self.open_issues_btn, "accent")
        self.open_issues_btn.clicked.connect(self._open_sync_issues)
        action_row.addWidget(self.open_issues_btn)
        self.export_diagnostics_btn = QPushButton(
            t("gcal_settings.export_diagnostics", "Export Report")
        )
        self._apply_section_button_style(self.export_diagnostics_btn, "accent")
        self.export_diagnostics_btn.clicked.connect(self._export_diagnostics_report)
        action_row.addWidget(self.export_diagnostics_btn)
        self.reset_sync_state_btn = QPushButton(
            t("gcal_settings.reset_sync_state", "Reset Sync Cache")
        )
        self._apply_section_button_style(self.reset_sync_state_btn, "danger")
        self.reset_sync_state_btn.clicked.connect(self._reset_sync_state)
        action_row.addWidget(self.reset_sync_state_btn)
        action_row.addStretch(1)
        cl.addLayout(action_row)

        cl.addWidget(
            self._help_label(
                t(
                    "gcal_settings.reset_sync_state_help",
                    "Resetting the sync cache clears stored sync tokens for the current binding and forces a safe full rescan on the next sync.",
                )
            )
        )

        layout.addWidget(card)
        layout.addStretch(1)
        return page

    # ──────────────────────────────────────────────
    # 섹션 4: 가이드
    # ──────────────────────────────────────────────

    def _build_guide_section(self) -> QWidget:
        page = QWidget()
        # Inherited background was removed to fix dropdown transparency issues on Windows
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        card = self._make_card(t("gcal_settings.setup_title", "초기 설정 가이드"))
        cl = card.layout()
        cl.addWidget(self._section_eyebrow(t("gcal_settings.setup_eyebrow", "QUICK START")))

        summary = QLabel(
            t(
                "gcal_settings.setup_summary",
                "Google Cloud OAuth 데스크탑 인증 정보를 사용합니다. "
                "공식 문서를 참고하면 최신 정보를 안전하게 따라할 수 있습니다.",
            )
        )
        summary.setWordWrap(True)
        summary.setProperty("role", "help")
        summary.setStyleSheet(self._style_bundle["help"])
        cl.addWidget(summary)
        cl.addSpacing(4)

        tip_items = [
            (
                t("gcal_settings.tip_project_title", "프로젝트"),
                t(
                    "gcal_settings.tip_project_body",
                    "Google Cloud 프로젝트를 생성하거나 기존 프로젝트를 재사용하세요.",
                ),
            ),
            (
                t("gcal_settings.tip_api_title", "API 활성화"),
                t(
                    "gcal_settings.tip_api_body",
                    "인증 정보를 만들기 전에 Google Calendar API를 활성화하세요.",
                ),
            ),
            (
                t("gcal_settings.tip_oauth_title", "OAuth 설정"),
                t(
                    "gcal_settings.tip_oauth_body",
                    "데스크탑 앱 OAuth 클라이언트 ID를 생성하세요. 웹 인증 정보는 동작하지 않습니다.",
                ),
            ),
            (
                t("gcal_settings.tip_json_title", "JSON 파일"),
                t(
                    "gcal_settings.tip_json_body",
                    "인증 JSON을 다운로드하여 [연결] 섹션에서 등록하세요.",
                ),
            ),
        ]
        for idx, (title, body) in enumerate(tip_items, 1):
            cl.addWidget(self._make_step_row(idx, title, body))

        cl.addSpacing(4)
        links = QHBoxLayout()
        links.setSpacing(8)
        doc_btn = QPushButton(t("gcal_settings.open_docs", "공식 문서"))
        doc_btn.setIcon(_ic(ICON.DOCS, color=self._ui_tokens["text_primary"]))
        self._apply_section_button_style(doc_btn, "secondary")
        doc_btn.clicked.connect(
            lambda: webbrowser.open("https://developers.google.com/calendar/api/quickstart/python")
        )
        console_btn = QPushButton(t("gcal_settings.open_console", "Cloud Console"))
        console_btn.setIcon(_ic(ICON.CLOUD, color=self._ui_tokens["text_primary"]))
        self._apply_section_button_style(console_btn, "secondary")
        console_btn.clicked.connect(lambda: webbrowser.open("https://console.cloud.google.com/"))
        oauth_btn = QPushButton(t("gcal_settings.open_oauth_docs", "OAuth 가이드"))
        oauth_btn.setIcon(_ic(ICON.OAUTH_GUIDE, color=self._ui_tokens["text_primary"]))
        self._apply_section_button_style(oauth_btn, "secondary")
        oauth_btn.clicked.connect(
            lambda: webbrowser.open("https://developers.google.com/identity/protocols/oauth2")
        )
        links.addWidget(doc_btn)
        links.addWidget(console_btn)
        links.addWidget(oauth_btn)
        links.addStretch(1)
        cl.addLayout(links)

        quick_note = QLabel(
            t(
                "gcal_focus.setup_note",
                "인증은 계정마다 한 번만 진행하고, '가져올 캘린더'에서 동기화할 캘린더를 선택하세요.",
            )
        )
        quick_note.setProperty("role", "help")
        quick_note.setStyleSheet(self._style_bundle["help"])
        quick_note.setWordWrap(True)
        cl.addWidget(quick_note)

        layout.addWidget(card)
        layout.addStretch(1)
        return page

    # ──────────────────────────────────────────────
    # 푸터
    # ──────────────────────────────────────────────

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setStyleSheet(self._style_bundle["footer"])
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.setSpacing(6)

        self.unsaved_label = self._help_label(
            t("gcal_focus.saved_state", "변경한 동기화 설정은 저장 후 적용됩니다.")
        )
        layout.addWidget(self.unsaved_label, 1)
        layout.addStretch(1)

        save_btn = QPushButton(t("gcal_settings.save", "설정 저장"))
        self._apply_section_button_style(save_btn, "accent")
        # save_btn.setFixedHeight(28) # Removed for standardization
        save_btn.setMinimumWidth(80)
        save_btn.setObjectName("primary_btn")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.save_settings)
        self.save_btn = save_btn

        close_btn = QPushButton(t("common.close", "닫기"))
        self._apply_section_button_style(close_btn, "secondary")
        close_btn.setMinimumWidth(64)
        close_btn.setObjectName("ghost_btn")
        close_btn.setAutoDefault(False)
        close_btn.clicked.connect(self.reject)
        self.close_btn = close_btn

        layout.addWidget(save_btn)
        layout.addWidget(close_btn)
        return footer

    # ──────────────────────────────────────────────
    # 헬퍼 위젯
    # ──────────────────────────────────────────────

    def _make_card(self, title: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(self._style_bundle["card"])
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        label = QLabel(title)
        label.setProperty("role", "sectionTitle")
        label.setStyleSheet(self._style_bundle["card_title"])
        layout.addWidget(label)
        return card

    def _make_divider(self) -> QFrame:
        d = QFrame()
        d.setObjectName("divider")
        d.setFrameShape(QFrame.Shape.HLine)
        d.setStyleSheet(self._style_bundle["divider"])
        return d

    def _make_info_box(self, title: str, body: str) -> QFrame:
        box = QFrame()
        box.setObjectName("subtleCard")
        box.setStyleSheet(self._style_bundle["subtle_card"])
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        title_lbl = QLabel(title)
        title_lbl.setProperty("role", "tipTitle")
        title_lbl.setStyleSheet(self._style_bundle["tip_title"])
        body_lbl = QLabel(body)
        body_lbl.setProperty("role", "tipBody")
        body_lbl.setStyleSheet(self._style_bundle["tip_body"])
        body_lbl.setWordWrap(True)
        layout.addWidget(title_lbl)
        layout.addWidget(body_lbl)
        return box

    def _make_meta_box(self, title: str):
        box = QFrame()
        box.setObjectName("subtleCard")
        box.setStyleSheet(self._style_bundle["meta_box"])
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        title_lbl = QLabel(title)
        title_lbl.setProperty("role", "metaLabel")
        title_lbl.setStyleSheet(self._style_bundle["meta_label"])
        value_lbl = QLabel("-")
        value_lbl.setProperty("role", "metaValue")
        value_lbl.setStyleSheet(self._style_bundle["meta_value"])
        value_lbl.setWordWrap(True)
        layout.addWidget(title_lbl)
        layout.addWidget(value_lbl)
        return box, value_lbl

    def _section_eyebrow(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "sectionEyebrow")
        label.setStyleSheet(self._style_bundle["eyebrow"])
        return label

    def _field_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("role", "fieldLabel")
        lbl.setStyleSheet(self._style_bundle["field_label"])
        return lbl

    def _help_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("role", "help")
        lbl.setStyleSheet(self._style_bundle["help"])
        lbl.setWordWrap(True)
        return lbl

    def _apply_section_button_style(
        self, button: QPushButton, tone: str = "secondary"
    ) -> QPushButton:
        disabled_style = (
            "QPushButton:disabled { "
            f"background: {self._ui_tokens['button_disabled_bg']}; "
            f"color: {self._ui_tokens['button_disabled_text']}; "
            f"border-color: {self._ui_tokens['button_disabled_border']}; "
            "}"
        )
        button.setStyleSheet(
            self._style_bundle.get(f"button_{tone}", self._style_bundle["button_secondary"])
            + disabled_style
        )
        return button

    def _apply_input_style(self, widget: QWidget, kind: str) -> QWidget:
        widget.setStyleSheet(self._style_bundle.get(f"input_{kind}", ""))
        return widget

    def _apply_combo_input_style(self, combo: QComboBox) -> QComboBox:
        combo.setStyleSheet(self._style_bundle.get("input_combo", ""))
        if combo.view() is not None:
            combo.view().setStyleSheet(self._style_bundle.get("input_popup", ""))
        if combo.lineEdit() is not None:
            combo.lineEdit().setStyleSheet(self._style_bundle.get("input_line", ""))
        completer = combo.completer()
        if completer is not None and completer.popup() is not None:
            completer.popup().setStyleSheet(self._style_bundle.get("input_popup", ""))
        return combo

    def _set_feedback_label(self, label: QLabel, text: str, tone: str = "help") -> QLabel:
        label.setText(text)
        label.setStyleSheet(
            self._style_bundle.get(f"feedback_{tone}", self._style_bundle["help"])
            if tone != "help"
            else self._style_bundle["help"]
        )
        return label

    def _make_step_row(self, number: int, title: str, body: str) -> QFrame:
        row = QFrame()
        row.setObjectName("subtleCard")
        row.setStyleSheet(self._style_bundle["guide_row"])
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        badge = QLabel(f"{number}")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(28, 28)
        badge.setStyleSheet(self._style_bundle["step_badge"])
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title_lbl = QLabel(title)
        title_lbl.setProperty("role", "tipTitle")
        title_lbl.setStyleSheet(self._style_bundle["tip_title"])
        body_lbl = QLabel(body)
        body_lbl.setProperty("role", "tipBody")
        body_lbl.setStyleSheet(self._style_bundle["tip_body"])
        body_lbl.setWordWrap(True)
        text_col.addWidget(title_lbl)
        text_col.addWidget(body_lbl)
        layout.addLayout(text_col, 1)
        return row

    def _build_timezone_list(self) -> list[str]:
        all_zones = sorted(available_timezones())
        ordered = []
        for tz_name in _COMMON_TIMEZONES + all_zones:
            if tz_name not in ordered:
                ordered.append(tz_name)
        return ordered

    # ──────────────────────────────────────────────
    # 상태 / 데이터
    # ──────────────────────────────────────────────

    def _load_state(self):
        from calendar_app.infrastructure.google_sync.common import (
            get_default_gcal_calendar_id,
            is_gcal_enabled,
        )

        self.enable_cb.setChecked(is_gcal_enabled(self.settings))
        self.creds_path_edit.setText(CREDENTIALS_PATH if os.path.exists(CREDENTIALS_PATH) else "")
        self.cal_id_edit.setText(get_default_gcal_calendar_id(self.settings))
        self.interval_spin.setValue(self._setting_interval("gcal_sync_interval", 10, 1, 240))
        self.quick_interval_spin.setValue(
            self._setting_interval("gcal_quick_sync_interval", 30, 5, 300)
        )
        sync = getattr(self.parent_app, "gcal_sync", None)
        self.credentials_details_btn.setChecked(
            not os.path.exists(CREDENTIALS_PATH)
            and not (sync and getattr(sync, "is_authenticated", False))
        )
        self._set_calendar_choices([])
        self._populate_timezones(
            str(self.settings.value("gcal_timezone", "Asia/Seoul") or "Asia/Seoul")
        )

    def _setting_interval(self, key, default, minimum, maximum):
        try:
            value = int(self.settings.value(key, default))
        except (TypeError, ValueError, OverflowError):
            return default
        return value if minimum <= value <= maximum else default

    def _populate_timezones(self, current_tz: str):
        self.timezone_combo.clear()
        self.timezone_combo.addItems(self._all_timezones)
        idx = self.timezone_combo.findText(current_tz, Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            self.timezone_combo.setCurrentIndex(idx)
        else:
            self.timezone_combo.setEditText(current_tz)
        self._refresh_timezone_preview()

    def _current_timezone(self) -> str:
        return self.timezone_combo.currentText().strip() or "UTC"

    def _refresh_timezone_preview(self):
        tz_name = self._current_timezone()
        try:
            offset = timezone_offset_for_name(tz_name, when=datetime.now())
            preview = t(
                "gcal_settings.timezone_preview",
                "현재 오프셋: {offset}  ·  {tz}",
                offset=offset,
                tz=tz_name,
            )
            self._set_feedback_label(self.timezone_preview, preview, "help")
        except Exception:
            self._set_feedback_label(
                self.timezone_preview,
                t("gcal_settings.timezone_invalid", "선택한 시간대를 해석할 수 없습니다."),
                "error",
            )

    def _system_timezone(self) -> str:
        try:
            # QTimeZone is much more reliable on Windows than standard datetime.astimezone()
            tz_id = QTimeZone.systemTimeZoneId().data().decode("utf-8", errors="replace")
            if tz_id:
                return tz_id
        except Exception:
            pass

        local_tz = datetime.now().astimezone().tzinfo
        key = getattr(local_tz, "key", None)
        return key or "UTC"

    def _apply_system_timezone(self):
        tz_name = self._system_timezone()
        idx = self.timezone_combo.findText(tz_name, Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            self.timezone_combo.setCurrentIndex(idx)
        else:
            self.timezone_combo.setEditText(tz_name)
        self._refresh_timezone_preview()

    def _refresh_parent_state(self):
        if hasattr(self.parent_app, "update_gcal_sync_timer"):
            self.parent_app.update_gcal_sync_timer()
        if hasattr(self.parent_app, "update_sync_status"):
            self.parent_app.update_sync_status()
        if hasattr(self.parent_app, "load_center_panel"):
            self.parent_app.load_center_panel()

    def _set_calendar_choices(self, calendars: list[dict]):
        self._calendar_choices = calendars or []
        self.calendar_choice_combo.blockSignals(True)
        self.calendar_choice_combo.clear()
        self.calendar_choice_combo.addItem(
            t("gcal_settings.calendar_choice_placeholder", "Choose from accessible calendars"),
            "",
        )
        for item in self._calendar_choices:
            if item.get("accessRole") not in ("owner", "writer"):
                continue
            label = item.get("summary") or item.get("id") or "?"
            if item.get("primary"):
                label = f"{label} ({t('gcal_settings.calendar_primary', 'Primary')})"
            self.calendar_choice_combo.addItem(label, item.get("id") or "")
        current_id = self.cal_id_edit.text().strip() or "primary"
        idx = self.calendar_choice_combo.findData(current_id)
        if idx >= 0:
            self.calendar_choice_combo.setCurrentIndex(idx)
        elif current_id and current_id != "primary":
            # Show the currently saved ID even if the full searchable list hasn't been loaded yet.
            label = current_id if len(current_id) < 30 else current_id[:27] + "..."
            self.calendar_choice_combo.addItem(
                f"({t('gcal_settings.meta_calendar', 'Calendar')}) {label}", current_id
            )
            self.calendar_choice_combo.setCurrentIndex(self.calendar_choice_combo.count() - 1)
        else:
            self.calendar_choice_combo.setCurrentIndex(0)
        self.calendar_choice_combo.blockSignals(False)

    def _resolve_calendar_display_meta(self, calendar_id: str) -> tuple[str, str]:
        calendar_id = (calendar_id or "").strip()
        if not calendar_id:
            return "-", ""

        calendars = list(self._calendar_choices or [])

        matched = None
        if calendar_id == "primary":
            matched = next((item for item in calendars if item.get("primary")), None)
        if matched is None:
            matched = next(
                (item for item in calendars if (item.get("id") or "") == calendar_id), None
            )

        if matched is None:
            if calendar_id == "primary":
                return "-", ""
            return calendar_id, ""

        label = (matched.get("summary") or matched.get("id") or "-").strip() or "-"
        tooltip = (matched.get("id") or "").strip()
        return label, tooltip if tooltip != label else tooltip

    def _refresh_google_calendar_list(
        self, _=None, *, notify: bool = True, show_empty_message: bool = True, calendars=None
    ):
        """Refresh accessible Google calendars into the local list and update the dialog immediately."""
        if calendars is None:
            self._start_calendar_query("import")
            return

        if not self._validate_calendar_account(calendars):
            return False
        self._set_calendar_choices(calendars)

        if not calendars:
            self._refresh_calendar_table()
            self._refresh_meta()
            if notify and show_empty_message:
                QMessageBox.information(
                    self,
                    t("gcal_settings.load_calendars", "Google 캘린더 불러오기"),
                    t("gcal_settings.load_calendars_empty", "접근 가능한 캘린더가 없습니다."),
                )
            return

        from calendar_app.infrastructure.db.calendar_repo import (
            list_calendars,
            make_gcal_id,
            upsert_calendar,
        )

        existing = {c["id"]: c for c in list_calendars(include_inactive=True)}
        imported = 0
        already_has_default = any(c.get("is_default") for c in existing.values())
        default_assigned_this_run = False

        for item in calendars:
            gcal_id = str(item.get("id") or "").strip()
            if not gcal_id or gcal_id == "primary":
                continue

            cal_db_id = make_gcal_id(gcal_id)
            name = item.get("summary") or gcal_id
            access = item.get("accessRole", "reader")
            previous = existing.get(cal_db_id, {})
            new_calendar_active = not self.settings.value(
                "gcal_import_selection_configured", False, type=bool
            ) and access in ("owner", "writer")
            is_active = bool(previous.get("is_active", new_calendar_active))
            existing_color = previous.get("color")
            raw_color = str(item.get("backgroundColor") or "").strip()
            color = (
                existing_color
                or (raw_color if raw_color.startswith("#") else None)
                or DEFAULT_CALENDAR_COLOR
            )
            is_primary = bool(item.get("primary"))
            is_default = bool(previous.get("is_default")) and access in ("owner", "writer")
            if not previous:
                is_default = (
                    is_primary
                    and not already_has_default
                    and not default_assigned_this_run
                    and access in ("owner", "writer")
                )
            if is_default:
                default_assigned_this_run = True

            saved = upsert_calendar(
                calendar_id=cal_db_id,
                name=name,
                cal_type="gcal",
                color=color,
                is_default=is_default,
                is_active=is_active,
                is_visible=bool(previous.get("is_visible", True)),
                sort_order=previous.get("sort_order", 0),
                gcal_calendar_id=gcal_id,
                access_role=access or None,
            )
            if not saved:
                self._set_feedback_label(
                    self.calendar_choice_hint,
                    t(
                        "sync_unified.calendar_save_failed",
                        "설정을 저장하지 못했습니다. 다시 시도하세요.",
                    ),
                    "error",
                )
                return
            imported += 1

        self._refresh_calendar_table()
        self._refresh_meta()
        try:
            from calendar_app.presentation.calendar.month_renderer import (
                invalidate_calendar_meta_cache,
            )
            from calendar_app.presentation.panels.side_panel_renderer import (
                invalidate_panel_calendar_cache,
            )

            invalidate_calendar_meta_cache()
            invalidate_panel_calendar_cache()
        except Exception:
            pass
        if self.parent_app and hasattr(self.parent_app, "schedule_panel_refresh"):
            self.parent_app.schedule_panel_refresh(center=True)
        if notify:
            self._set_query_feedback(
                t(
                    "gcal_focus.list_loaded",
                    "{count}개 캘린더를 확인했습니다. 가져올 캘린더를 선택한 뒤 설정을 저장하세요.",
                    count=imported,
                )
            )

    def _load_accessible_calendars(self):
        self._start_calendar_query("import")

    def _on_calendar_choice_changed(self, index: int):
        if index <= 0:
            return
        calendar_id = self.calendar_choice_combo.itemData(index)
        if calendar_id:
            self.cal_id_edit.blockSignals(True)
            self.cal_id_edit.setText(calendar_id)
            self.cal_id_edit.blockSignals(False)

            # Auto-update timezone from calendar metadata
            for item in self._calendar_choices:
                if (item.get("id") or "primary") == calendar_id:
                    tz = item.get("timeZone")
                    if tz:
                        self._populate_timezones(tz)
                    break

    def _sync_edit_to_combo(self, text: str):
        target = text.strip() or "primary"
        idx = self.calendar_choice_combo.findData(target)
        if idx >= 0:
            self.calendar_choice_combo.blockSignals(True)
            self.calendar_choice_combo.setCurrentIndex(idx)
            self.calendar_choice_combo.blockSignals(False)

    def _export_diagnostics_report(self):
        try:
            # 1. 파일 다이얼로그 띄워 저장 경로 획득
            default_name = (
                f"dark_calendar_sync_diagnostics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            )
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                t("gcal_settings.export_diagnostics_save_title", "동기화 진단 리포트 저장"),
                os.path.join(os.path.expanduser("~"), default_name),
                "Text Files (*.txt);;All Files (*)",
            )
            if not file_path:
                return

            # 2. 리포트 생성 시작
            lines = []
            lines.append("=" * 60)
            lines.append("DARK CALENDAR - GOOGLE CALENDAR SYNC DIAGNOSTICS REPORT")
            lines.append("=" * 60)
            lines.append(f"Generated At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"OS Version: {os.name}")

            # App version 및 metadata
            from calendar_app.bootstrap import APP_VERSION

            lines.append(f"App Version: {APP_VERSION}")
            lines.append("-" * 60)

            # QSettings 진단
            lines.append("[QSettings GCal Values]")
            for key in [
                "gcal_enabled",
                "gcal_calendar_id",
                "gcal_bound_calendar_id",
                "last_successful_sync",
                "gcal_primary_resolved_id",
            ]:
                val = self.settings.value(key, None)
                lines.append(f"  {key}: {val}")

            # DB & Calendars 진단
            lines.append("-" * 60)
            lines.append("[Registered GCal Calendars]")
            try:
                from calendar_app.infrastructure.db.calendar_repo import list_calendars

                for cal in list_calendars(include_inactive=True):
                    if cal.get("type") == "gcal":
                        lines.append(
                            f"  ID: {cal.get('id')} | GCal ID: {cal.get('gcal_calendar_id')} | "
                            f"Name: {cal.get('name')} | Active: {cal.get('is_active')} | "
                            f"Visible: {cal.get('is_visible')} | AccessRole: {cal.get('access_role')}"
                        )
                        # 이 캘린더의 sync token 정보도 가져오기
                        gcal_id = cal.get("gcal_calendar_id")
                        if gcal_id:
                            token = self.settings.value(f"gcal_sync_token::{gcal_id}", None)
                            fails = self.settings.value(f"gcal_sync_token_fails::{gcal_id}", 0)
                            lines.append(
                                f"    - Sync Token Length: {len(str(token or ''))} chars | Fail Count: {fails}"
                            )
            except Exception as e:
                lines.append(f"  Failed to load calendar table: {e}")

            # DB Tasks 무결성 진단
            lines.append("-" * 60)
            lines.append("[DB Tasks Statistics]")
            try:
                from calendar_app.infrastructure.db.database_unified import db_manager

                conn = db_manager.get_connection()
                if conn:
                    cur = conn.cursor()
                    cur.execute("SELECT COUNT(*) FROM unified_task")
                    total_tasks = cur.fetchone()[0]
                    cur.execute(
                        "SELECT COUNT(*) FROM unified_task WHERE gcal_event_id IS NOT NULL AND trim(gcal_event_id) != ''"
                    )
                    gcal_tasks = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM unified_task WHERE gcal_dirty = 1")
                    dirty_tasks = cur.fetchone()[0]
                    cur.execute(
                        "SELECT COUNT(*) FROM unified_task WHERE gcal_sync_error IS NOT NULL AND trim(gcal_sync_error) != ''"
                    )
                    error_tasks = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM gcal_deleted_task_archive")
                    archive_tasks = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM gcal_delete_queue")
                    delete_queue_tasks = cur.fetchone()[0]

                    lines.append(f"  Total Unified Tasks: {total_tasks}")
                    lines.append(f"  GCal Connected Tasks: {gcal_tasks}")
                    lines.append(f"  GCal Pending Dirty Tasks: {dirty_tasks}")
                    lines.append(f"  GCal Failed Tasks: {error_tasks}")
                    lines.append(f"  Deleted Task Archive Size: {archive_tasks}")
                    lines.append(f"  Delete Queue Size: {delete_queue_tasks}")

                    # 에러 태스크 샘플링
                    if error_tasks > 0:
                        lines.append("  [Failed Tasks Detail (Up to 10)]")
                        cur.execute(
                            "SELECT id, name, gcal_sync_error, deadline FROM unified_task WHERE gcal_sync_error IS NOT NULL LIMIT 10"
                        )
                        for row in cur.fetchall():
                            lines.append(
                                f"    - Task ID {row[0]} ({row[1]}): {row[2]} (Deadline: {row[3]})"
                            )
            except Exception as e:
                lines.append(f"  Failed to load database stats: {e}")

            # 최근 로그 추출
            lines.append("-" * 60)
            lines.append("[Recent GCal Logs (Tail 150 lines)]")
            try:
                from calendar_app.app_paths import LOG_PATH

                if os.path.exists(LOG_PATH):
                    with open(LOG_PATH, encoding="utf-8", errors="replace") as fh:
                        log_lines = fh.readlines()
                    tail_lines = log_lines[-2000:]
                    gcal_logs = [
                        ln.strip()
                        for ln in tail_lines
                        if any(k in ln.lower() for k in ["gcal", "sync", "google"])
                    ]
                    for log in gcal_logs[-150:]:
                        lines.append(f"  {log}")
                else:
                    lines.append("  No log file found.")
            except Exception as e:
                lines.append(f"  Failed to load logs: {e}")

            lines.append("=" * 60)
            lines.append("END OF REPORT")
            lines.append("=" * 60)

            # 파일 저장
            with open(file_path, "w", encoding="utf-8", errors="strict") as fh:
                fh.write("\n".join(lines))
                fh.write("\n")

            QMessageBox.information(
                self,
                t("gcal_settings.export_diagnostics_success_title", "Export Complete"),
                t(
                    "gcal_settings.export_diagnostics_success_msg",
                    "Diagnostics report exported successfully to:\n{path}",
                ).format(path=file_path),
            )

        except Exception as e:
            from calendar_app.infrastructure.db.database_unified import logger as db_logger

            db_logger.exception("Failed to export diagnostics report")
            QMessageBox.critical(
                self,
                t("gcal_settings.export_diagnostics_failed_title", "Export Failed"),
                f"An error occurred while generating the report:\n{e}",
            )

    def _open_sync_issues(self):
        if self.parent_app and hasattr(self.parent_app, "open_gcal_sync_issues_dialog"):
            self.parent_app.open_gcal_sync_issues_dialog()
        self._refresh_diagnostics()

    def _reset_sync_state(self):
        if (
            self._auth_worker is not None
            or self._query_worker is not None
            or self._parent_google_busy()
        ):
            self._set_query_feedback(
                t(
                    "gcal_ux.sync_busy",
                    "Google 동기화가 진행 중입니다. 완료되면 설정을 변경할 수 있습니다.",
                )
            )
            return
        cleared = 0
        # 등록된 모든 gcal 캘린더 token 리셋
        try:
            from calendar_app.infrastructure.db.calendar_repo import list_calendars

            for cal in list_calendars(include_inactive=True):
                if cal.get("type") != "gcal":
                    continue
                gcal_id = cal.get("gcal_calendar_id") or ""
                if gcal_id:
                    self.settings.setValue(f"gcal_sync_token::{gcal_id}", "")
                    self.settings.setValue(f"gcal_sync_token_fails::{gcal_id}", 0)
                    cleared += 1
        except Exception:
            pass
        # bound/current calendar도 포함
        current_calendar = self.cal_id_edit.text().strip() or "primary"
        bound_calendar = str(self.settings.value("gcal_bound_calendar_id", "") or "")
        for calendar_id in {current_calendar, bound_calendar}:
            if not calendar_id:
                continue
            self.settings.setValue(f"gcal_sync_token::{calendar_id}", "")
            self.settings.setValue(f"gcal_sync_token_fails::{calendar_id}", 0)
            cleared += 1

        self._set_feedback_label(
            self.test_access_result,
            t("gcal_settings.test_access_idle", "No test has been run yet."),
            "help",
        )
        self._refresh_diagnostics()
        QMessageBox.information(
            self,
            t("gcal_settings.reset_sync_state_done_title", "Sync cache reset"),
            t(
                "gcal_settings.reset_sync_state_done_body",
                "Cleared sync cache for {count} calendar binding(s). The next sync will run as a full rescan.",
                count=cleared,
            ),
        )

    def _refresh_meta(self):
        account_value = t("gcal_settings.meta_not_connected", "연결되지 않음")
        if (
            hasattr(self.parent_app, "gcal_sync")
            and self.parent_app.gcal_sync
            and getattr(self.parent_app.gcal_sync, "is_authenticated", False)
            and getattr(self.parent_app.gcal_sync, "service", None) is not None
        ):
            try:
                primary_info = next(
                    (item for item in self._calendar_choices if item.get("primary")), {}
                )
                account_value = (
                    primary_info.get("id")
                    or str(self.settings.value("gcal_primary_resolved_id", "") or "")
                    or t("sync_ui.connected", "연결됨")
                )
            except Exception:
                pass
        self.account_meta[1].setText(account_value)
        self.account_meta[1].setToolTip(account_value)
        active_count = sum(self._calendar_import_selection.values())
        self.calendar_meta[1].setText(t("gcal_focus.import_count", "{count}개", count=active_count))
        self.calendar_meta[1].setToolTip(
            t(
                "gcal_focus.import_meta_help",
                "Google에서 새 일정을 가져올 캘린더 수입니다. 화면 표시 여부는 메인 캘린더에서 따로 설정합니다.",
            )
        )
        last_sync = str(self.settings.value("last_successful_sync", "") or "")
        try:
            last_sync_short = datetime.fromisoformat(last_sync).strftime("%m-%d %H:%M")
        except ValueError:
            last_sync_short = last_sync
        self.last_sync_meta[1].setText(
            last_sync_short if last_sync else t("gcal.last_sync_none", "없음")
        )
        self.last_sync_meta[1].setToolTip(last_sync)
        self._refresh_diagnostics()

    def _refresh_diagnostics(self):
        issue_count = 0
        delete_queue_count = 0
        try:
            from calendar_app.infrastructure.db import task_repo as _task_repo

            issue_count = (
                _task_repo.count_unified_task_gcal_errors()
                + _task_repo.count_gcal_delete_queue_errors()
                + _task_repo.count_gcal_sync_conflicts()
            )
            delete_queue_count = len(_task_repo.get_gcal_delete_queue())
        except Exception:
            issue_count = 0
            delete_queue_count = 0

        sync = getattr(self.parent_app, "gcal_sync", None)
        is_authenticated = bool(sync and getattr(sync, "is_authenticated", False))

        bound_calendar = (
            str(self.settings.value("gcal_bound_calendar_id", "") or "") if is_authenticated else ""
        )
        error_kind = getattr(sync, "last_error_kind", None) if sync else None
        error_kind = self.settings.value("sync_google_last_error", "") or error_kind
        error_text = (
            self._friendly_error(error_kind)
            if error_kind
            else t("gcal_settings.meta_no_error", "None")
        )

        self.issue_meta[1].setText(str(issue_count))
        self.delete_queue_meta[1].setText(str(delete_queue_count))
        self.bound_calendar_meta[1].setText(
            bound_calendar or t("gcal_settings.meta_not_bound", "Not bound yet")
        )
        self.last_error_meta[1].setText(error_text)

    def _refresh_status(self):
        authenticated = bool(
            hasattr(self.parent_app, "gcal_sync")
            and self.parent_app.gcal_sync
            and getattr(self.parent_app.gcal_sync, "is_authenticated", False)
        )
        if authenticated:
            self.status_title.setText(t("gcal_focus.service_name", "Google Calendar"))
            self.status_pill.setText(t("gcal_settings.status_pill_connected", "● 연결됨"))
            self.status_title.setStyleSheet(self._style_bundle["status_title_connected"])
            self.status_pill.setStyleSheet(self._style_bundle["status_pill_connected"])
        else:
            self.status_title.setText(t("gcal_focus.service_name", "Google Calendar"))
            self.status_pill.setText(t("gcal_settings.status_pill_pending", "● 인증 필요"))
            self.status_title.setStyleSheet(self._style_bundle["status_title_pending"])
            self.status_pill.setStyleSheet(self._style_bundle["status_pill_pending"])
        if self._auth_worker is None:
            self.auth_btn.setText(
                t("gcal_ux.reconnect", "계정 다시 연결")
                if authenticated
                else t("gcal_focus.connect_account", "Google 계정 연결")
            )
        self.reset_btn.setVisible(authenticated)
        self.go_to_auth_btn.setVisible(not authenticated)
        from calendar_app.infrastructure.google_sync.common import is_gcal_enabled

        if authenticated and not is_gcal_enabled(self.settings):
            self.status_pill.setText(t("gcal_focus.sync_disabled", "동기화 꺼짐"))
            self.status_pill.setStyleSheet(self._style_bundle["status_pill_pending"])
        error = self.settings.value("sync_google_last_error", "") or getattr(
            getattr(self.parent_app, "gcal_sync", None), "last_error_kind", None
        )
        if error in {"account_mismatch", "account_unverified", "auth_required", "reauth_required"}:
            self.status_pill.setText(t("gcal_ux.connection_review", "연결 확인 필요"))
            self.status_pill.setStyleSheet(self._style_bundle["status_pill_pending"])
            self._set_query_feedback(self._friendly_error(error), "error", error)
        self.connection_next_step.setText(
            t(
                "gcal_ux.connected_help",
                "연결된 계정을 유지합니다. 권한을 다시 확인하려면 같은 계정으로 연결하세요. 가져올 캘린더는 다음 섹션에서 선택합니다.",
            )
            if authenticated
            else t(
                "gcal_ux.connect_help",
                "인증 파일을 준비하고 Google 계정을 연결하세요. 연결 후 가져올 캘린더를 선택할 수 있습니다.",
            )
        )
        self._refresh_meta()

    def _friendly_error(self, code):
        if code and str(code).startswith("auth_") and code not in {"auth_required"}:
            return _gcal_auth_error_text(code)
        sync = getattr(self.parent_app, "gcal_sync", None)
        return sync_error_message(
            google_sync_error_code(code, getattr(sync, "last_error_status", None))
        )

    # ──────────────────────────────────────────────
    # 액션
    # ──────────────────────────────────────────────

    def browse_creds(self):
        if self._browse_creds_open:
            return

        current_path = self.creds_path_edit.text().strip()
        start_dir = os.path.dirname(current_path) if current_path else ""
        dialog = QFileDialog(
            self,
            t("gcal_settings.creds_dialog_title", "credentials.json 선택"),
            start_dir,
            "JSON Files (*.json)",
        )
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dialog.setViewMode(QFileDialog.ViewMode.Detail)
        dialog.setModal(True)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)

        self._browse_creds_open = True
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                selected = dialog.selectedFiles()
                if selected:
                    self.creds_path_edit.setText(selected[0])
        finally:
            self._browse_creds_open = False

    def _copy_credentials_if_needed(self) -> bool:
        selected_json = self.creds_path_edit.text().strip()
        if not selected_json:
            return True
        if not os.path.exists(selected_json):
            self._set_query_feedback(
                _gcal_auth_error_text("auth_client_missing"), "error", "auth_client_missing"
            )
            self._run_recovery_action()
            return False
        try:
            load_desktop_client_config(selected_json)
        except GoogleAuthError as exc:
            self._set_query_feedback(_gcal_auth_error_text(exc.kind), "error", exc.kind)
            self._run_recovery_action()
            return False
        if os.path.abspath(selected_json) == os.path.abspath(CREDENTIALS_PATH):
            return True
        try:
            shutil.copy(selected_json, CREDENTIALS_PATH)
            self.creds_path_edit.setText(CREDENTIALS_PATH)
            return True
        except (OSError, shutil.Error):
            self._set_query_feedback(
                t(
                    "gcal_ux.file_copy_failed",
                    "인증 파일을 앱에 저장하지 못했습니다. 파일과 앱 데이터 폴더의 접근 권한을 확인한 뒤 다시 선택하세요.",
                ),
                "error",
                "auth_client_invalid",
            )
            return False

    def _apply_runtime_settings(self, enabled: bool):
        from calendar_app.infrastructure.google_sync.common import get_default_gcal_calendar_id

        cal_id = get_default_gcal_calendar_id(self.settings)
        self.cal_id_edit.setText(cal_id)
        tz_name = self._current_timezone() or "UTC"
        if hasattr(self.parent_app, "gcal_sync") and self.parent_app.gcal_sync:
            self.parent_app.gcal_sync.calendar_id = cal_id
            self.parent_app.gcal_sync.time_zone = tz_name

    def _test_calendar_access(self):
        self._start_calendar_query("access")

    def _start_calendar_query(self, kind):
        if self._auth_worker is not None or self._query_worker is not None:
            return
        coordinator = getattr(self.parent_app, "_calendar_sync_coordinator", None)
        if coordinator:
            coordinator.refresh()
        if (coordinator and coordinator.states.get("google", {}).get("busy")) or any(
            worker and worker.isRunning()
            for worker in (
                getattr(self.parent_app, "_sync_worker", None),
                getattr(self.parent_app, "_auth_worker", None),
            )
        ):
            self._set_query_feedback(
                t("sync_unified.google_busy", "진행 중인 Google 작업이 끝난 뒤 다시 시도하세요."),
                "help",
            )
            return
        sync = getattr(self.parent_app, "gcal_sync", None)
        if kind != "disconnect" and (not sync or not sync.is_authenticated or sync.service is None):
            self._set_query_feedback(
                t(
                    "gcal_settings.test_access_auth_needed",
                    "먼저 인증을 완료해야 테스트할 수 있습니다.",
                ),
                "error",
            )
            self.go_to_auth_btn.show()
            return
        worker = (GCalRevokeWorker if kind == "disconnect" else GCalQueryWorker)(sync, self)
        self._query_worker, self._query_kind = worker, kind
        workers = getattr(self.parent_app, "_bg_workers", None)
        if workers is not None:
            workers.append(worker)
        self._set_operation_state(
            True,
            t(
                "gcal_ux.disconnecting",
                "Google 연결을 해제하고 있습니다. 작업이 끝날 때까지 잠시 기다려 주세요.",
            )
            if kind == "disconnect"
            else t(
                "gcal_ux.loading",
                "Google 캘린더 목록을 확인하고 있습니다. 기존 선택 내용은 유지됩니다.",
            ),
            cancellable=kind != "disconnect",
        )
        worker.finished.connect(self._finish_calendar_query)
        try:
            worker.start()
        except RuntimeError:
            worker.success = False
            self._finish_calendar_query()
        if coordinator:
            coordinator.refresh()

    def _finish_calendar_query(self):
        worker = self._query_worker
        if worker is None:
            return
        self._query_worker = None
        workers = getattr(self.parent_app, "_bg_workers", None)
        if workers is not None and worker in workers:
            workers.remove(worker)
        self._set_operation_state(False)
        worker.deleteLater()
        if self._query_kind == "disconnect":
            self._complete_reset_auth(notify=self._auth_close_result is None)
        if self._auth_close_result is not None:
            result, self._auth_close_result = self._auth_close_result, None
            self._availability_timer.stop()
            super().done(self._close_result(result))
            return
        if self._query_kind == "disconnect":
            return
        if worker.is_cancelled():
            self._set_query_feedback(
                t(
                    "gcal_ux.query_cancelled",
                    "목록 확인을 취소했습니다. 기존 연결과 선택 내용은 유지됩니다.",
                )
            )
            return
        if not worker.success:
            code = getattr(worker.service, "last_error_kind", None) or "calendar_list"
            self._set_query_feedback(self._friendly_error(code), "error", code)
            self._refresh_calendar_table()
            return
        if not self._validate_calendar_account(worker.calendars):
            return
        self._auth_calendars_loaded = True
        self._set_calendar_choices(worker.calendars)
        self._set_feedback_label(
            self.calendar_choice_hint,
            t(
                "gcal_focus.list_loaded",
                "{count}개 캘린더를 확인했습니다. 가져올 캘린더를 선택한 뒤 설정을 저장하세요.",
                count=len(worker.calendars),
            ),
            "help",
        )
        if self._query_kind == "import":
            try:
                self._refresh_google_calendar_list(notify=False, calendars=worker.calendars)
            except (OSError, RuntimeError, sqlite3.Error):
                self._set_feedback_label(
                    self.calendar_choice_hint,
                    t(
                        "sync_unified.calendar_save_failed",
                        "설정을 저장하지 못했습니다. 다시 시도하세요.",
                    ),
                    "error",
                )
                return
        cal_id = self.cal_id_edit.text().strip() or "primary"
        matched = next(
            (
                c
                for c in worker.calendars
                if c.get("id") == cal_id or (cal_id == "primary" and c.get("primary"))
            ),
            None,
        )
        self._set_query_feedback(
            t(
                "gcal_settings.test_access_ok",
                "접근 확인: {name} (계정 캘린더 {count}개)",
                name=(matched or {}).get("summary", cal_id),
                count=len(worker.calendars),
            )
            if matched
            else t(
                "sync_unified.google_target_missing",
                "계정에 접근했지만 선택한 캘린더를 찾지 못했습니다. 목록에서 다시 선택하세요.",
            ),
            "success" if matched else "warning",
        )
        self._refresh_meta()
        self._refresh_calendar_table()

    def run_auth(self):
        if self._query_worker is not None:
            return
        if self._auth_worker is None and self._parent_google_busy():
            self._set_query_feedback(
                t("sync_unified.google_busy", "진행 중인 Google 작업이 끝난 뒤 다시 시도하세요.")
            )
            return
        if (
            self._auth_worker is None
            and hasattr(self.parent_app, "_sync_worker_running")
            and self.parent_app._sync_worker_running()
        ):
            self._set_feedback_label(
                self.test_access_result,
                t("sync_unified.google_busy", "진행 중인 Google 작업이 끝난 뒤 다시 시도하세요."),
                "help",
            )
            return
        if self._auth_worker is not None:
            self._auth_worker.requestInterruption()
            self.auth_btn.setEnabled(False)
            self.auth_btn.setText(t("gcal_settings.auth_cancelling", "인증 취소 중…"))
            return
        try:
            ZoneInfo(self._current_timezone() or "UTC")
        except (KeyError, ValueError):
            self._set_feedback_label(
                self.timezone_preview,
                t("sync_ui.invalid_timezone", "올바른 시간대를 선택하세요. 예: Asia/Seoul"),
                "error",
            )
            self._switch_section(2)
            self.timezone_details_btn.setChecked(True)
            return
        if not self._copy_credentials_if_needed():
            return
        from calendar_app.infrastructure.google_sync.common import get_default_gcal_calendar_id

        cal_id = get_default_gcal_calendar_id(self.settings)
        tz_name = self._current_timezone() or "UTC"

        from calendar_app.infrastructure.google_sync.service import prepare_calendar_sync_service

        candidate = prepare_calendar_sync_service(
            None,
            calendar_id=cal_id,
            time_zone=tz_name,
            reset_auth=True,
        )

        worker = GCalAuthWorker(candidate, self)
        self._auth_worker = worker
        workers = getattr(self.parent_app, "_bg_workers", None)
        if workers is not None:
            workers.append(worker)
        worker.finished.connect(self._finish_auth)
        self._switch_section(0)
        self._set_operation_state(
            True,
            t(
                "gcal_settings.auth_waiting",
                "브라우저에서 로그인을 완료하세요. 최대 3분 동안 기다립니다. 오류가 표시되면 인증을 취소하고 인증 파일을 확인하세요.",
            ),
        )
        try:
            worker.start()
        except RuntimeError:
            candidate._set_last_error("auth_modules", "auth_worker_start_failed")
            self._finish_auth()

    def _finish_auth(self):
        worker = self._auth_worker
        if worker is None:
            return
        self._auth_worker = None
        workers = getattr(self.parent_app, "_bg_workers", None)
        if workers is not None and worker in workers:
            workers.remove(worker)
        self._set_operation_state(False)
        self._refresh_status()
        worker.deleteLater()
        if self._auth_close_result is not None:
            if hasattr(worker.service, "_pending_token_json"):
                worker.service._pending_token_json = None
            result = self._auth_close_result
            self._auth_close_result = None
            self._availability_timer.stop()
            super().done(self._close_result(result))
            return
        if worker.is_cancelled():
            worker.success = False
            worker.service._set_last_error("auth_cancelled", "Google authentication cancelled")
        if (
            worker.success
            and sum(
                isinstance(item, dict)
                and item.get("primary") is True
                and isinstance(item.get("id"), str)
                and item["id"].strip() not in {"", "primary"}
                for item in worker.calendars
            )
            != 1
        ):
            worker.service._pending_token_json = None
            self.settings.setValue("sync_google_last_error", "account_unverified")
            self._set_query_feedback(
                sync_error_message("account_unverified"), "error", "account_unverified"
            )
            return
        if worker.success and not self._validate_calendar_account(
            worker.calendars, sync=worker.service
        ):
            worker.service._pending_token_json = None
            return
        if worker.success:
            from calendar_app.infrastructure.google_sync.token_store import save_token_json

            try:
                if worker.service._pending_token_json is not None:
                    save_token_json(worker.service._pending_token_json)
                    worker.service._pending_token_json = None
            except OSError:
                worker.success = False
                worker.service._set_last_error("auth_token_write", "token_write_failed")
        if worker.success:
            self.parent_app.gcal_sync = worker.service
            self._applied_changes = True
            self._auth_calendars_loaded = True
            self._set_calendar_choices(worker.calendars)
            self.settings.setValue("gcal_enabled", "true")
            self.enable_cb.setChecked(True)
            self._refresh_parent_state()
            self._refresh_status()
            try:
                self._refresh_google_calendar_list(
                    notify=False, show_empty_message=False, calendars=worker.calendars
                )
            except (sqlite3.Error, OSError, RuntimeError):
                self._set_feedback_label(
                    self.calendar_choice_hint,
                    t(
                        "sync_unified.calendar_save_failed",
                        "설정을 저장하지 못했습니다. 다시 시도하세요.",
                    ),
                    "error",
                )
                return
            self._set_query_feedback(
                t(
                    "gcal_ux.connected_next",
                    "Google 계정을 연결했습니다. 가져올 캘린더를 선택하고 설정을 저장하세요.",
                ),
                "success",
            )
            self._switch_section(1)
        else:
            if hasattr(worker.service, "_pending_token_json"):
                worker.service._pending_token_json = None
            code = worker.service.last_error_kind
            self._set_query_feedback(
                self._friendly_error(code), "help" if code == "auth_cancelled" else "error", code
            )
            self._refresh_status()

    def _close_result(self, result):
        # Preserve the caller's post-save refresh without saving any later draft.
        return QDialog.DialogCode.Accepted if self._applied_changes else result

    def done(self, result):
        if self._query_worker is not None:
            self._auth_close_result = result
            if self._query_kind != "disconnect":
                self._query_worker.requestInterruption()
            return
        if self._auth_worker is not None:
            self._auth_close_result = result
            self._auth_worker.requestInterruption()
            self.auth_btn.setEnabled(False)
            return
        self._availability_timer.stop()
        super().done(self._close_result(result))

    def closeEvent(self, event):
        if self._auth_worker is not None or self._query_worker is not None:
            event.ignore()
            self.done(QDialog.DialogCode.Rejected)
            return
        super().closeEvent(event)

    def save_settings(self):
        if self._auth_worker is not None or self._query_worker is not None:
            return
        if self._parent_google_busy():
            self._set_query_feedback(
                t(
                    "gcal_ux.sync_busy",
                    "Google 동기화가 진행 중입니다. 완료되면 설정을 변경할 수 있습니다.",
                )
            )
            return
        if self._metadata_load_failed:
            self._set_query_feedback(
                t(
                    "gcal_ux.metadata_unavailable",
                    "저장된 캘린더 목록을 읽지 못했습니다. 선택 내용은 유지했습니다. 목록을 다시 확인한 뒤 저장하세요.",
                ),
                "error",
            )
            self._switch_section(1)
            return
        if self.enable_cb.isChecked() and not self._copy_credentials_if_needed():
            return

        try:
            ZoneInfo(self._current_timezone() or "UTC")
        except (KeyError, ValueError):
            self._set_feedback_label(
                self.timezone_preview,
                t("sync_ui.invalid_timezone", "올바른 시간대를 선택하세요. 예: Asia/Seoul"),
                "error",
            )
            self._switch_section(2)
            self.timezone_details_btn.setChecked(True)
            return
        from calendar_app.application.calendar_preferences import (
            set_google_calendar_import_selection,
        )
        from calendar_app.infrastructure.db import calendar_repo

        selection_result = set_google_calendar_import_selection(
            self._calendar_import_selection, self.settings, repository=calendar_repo
        )
        if not selection_result.success:
            self._set_feedback_label(
                self.calendar_choice_hint,
                t(
                    "gcal_focus.import_save_failed",
                    "가져오기 선택을 저장하지 못했습니다. 사용 가능한 기본 저장 캘린더가 있는지 확인하고 다시 시도하세요.",
                ),
                "error",
            )
            self._switch_section(1)
            return
        enabled = self.enable_cb.isChecked()
        tz_name = self._current_timezone() or "UTC"
        self.settings.setValue("gcal_enabled", "true" if enabled else "false")
        self.settings.setValue(
            "sync_google_auto", "true" if self.auto_sync_cb.isChecked() else "false"
        )
        self.settings.setValue("gcal_timezone", tz_name)
        self.settings.setValue("gcal_sync_interval", str(self.interval_spin.value()))
        self.settings.setValue("gcal_quick_sync_interval", str(self.quick_interval_spin.value()))
        self.settings.setValue(
            "gcal_hide_completed_in_gcal",
            "true" if self.hide_completed_check.isChecked() else "false",
        )

        self._apply_runtime_settings(enabled)
        self._refresh_parent_state()
        self._refresh_status()
        message = t("gcal_settings.saved_body", "Google 동기화 설정이 저장되었습니다.")
        if selection_result.default_changed:
            message += "\n" + t(
                "gcal_focus.default_changed",
                "가져오기를 끈 캘린더 대신 '{name}'을 새 일정의 기본 저장 캘린더로 지정했습니다. 메인 캘린더에서 변경할 수 있습니다.",
                name=(selection_result.default_calendar or {}).get("name", ""),
            )
        self._settings_dirty = False
        self._applied_changes = True
        self.unsaved_label.setText(
            t("gcal_ux.saved", "설정을 저장했습니다. 변경 내용이 적용되었습니다.")
        )
        self._show_inline_feedback(message, "success")
        self.save_btn.setEnabled(False)

    def reset_auth(self):
        if self._auth_worker is not None or self._query_worker is not None:
            return
        if self._parent_google_busy():
            self._set_query_feedback(
                t(
                    "gcal_ux.sync_busy",
                    "Google 동기화가 진행 중입니다. 완료되면 설정을 변경할 수 있습니다.",
                )
            )
            return
        reply = QMessageBox.warning(
            self,
            t("gcal_settings.reset_title", "Disconnect reset"),
            t(
                "gcal_settings.reset_confirm",
                "Delete Google auth/token data and reset linked calendar/subscription info as well?",
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        sync = getattr(self.parent_app, "gcal_sync", None)
        if sync is not None and callable(getattr(sync, "revoke_token", None)):
            self._start_calendar_query("disconnect")
        else:
            self._complete_reset_auth()

    def _complete_reset_auth(self, notify=True):
        self._applied_changes = True
        removed_calendar_count = 0
        removed_subscription_count = 0

        for path in (TOKEN_PATH, CREDENTIALS_PATH):
            if os.path.exists(path):
                with contextlib.suppress(OSError):
                    os.remove(path)

        try:
            from calendar_app.infrastructure.db.calendar_repo import delete_calendar, list_calendars

            for cal in list_calendars(include_inactive=True):
                if cal.get("type") != "gcal":
                    continue
                cal_id = str(cal.get("id") or "").strip()
                if not cal_id:
                    continue
                if delete_calendar(cal_id):
                    removed_calendar_count += 1
        except Exception:
            pass

        try:
            from calendar_app.infrastructure.db import task_repo as _task_repo

            for sub in _task_repo.list_gcal_subscriptions(include_inactive=True):
                calendar_id = str(sub.get("calendar_id") or "").strip()
                if not calendar_id:
                    continue
                if _task_repo.delete_gcal_subscription(calendar_id):
                    removed_subscription_count += 1
            _task_repo.clear_gcal_delete_queue()
        except Exception:
            pass

        try:
            for key in self.settings.allKeys():
                if key.startswith("gcal_sync_token::") or key.startswith("gcal_sync_token_fails::"):
                    self.settings.remove(key)
        except Exception:
            pass

        self.settings.setValue("gcal_enabled", "false")
        self.settings.setValue("gcal_bound_calendar_id", "")
        self.settings.setValue("last_successful_sync", "")
        self.settings.setValue("gcal_calendar_id", "primary")
        self._calendar_import_selection.clear()
        self.enable_cb.setChecked(False)
        self.creds_path_edit.clear()
        self.cal_id_edit.setText("primary")
        self._set_calendar_choices([])

        if self.parent_app and hasattr(self.parent_app, "_gcal_subscription_events_cache"):
            self.parent_app._gcal_subscription_events_cache = {}

        if hasattr(self.parent_app, "gcal_sync") and self.parent_app.gcal_sync:
            self.parent_app.gcal_sync.is_authenticated = False
            self.parent_app.gcal_sync.service = None

        self._refresh_calendar_table()

        try:
            from calendar_app.presentation.calendar.month_renderer import (
                invalidate_calendar_meta_cache,
            )
            from calendar_app.presentation.panels.side_panel_renderer import (
                invalidate_panel_calendar_cache,
            )

            invalidate_calendar_meta_cache()
            invalidate_panel_calendar_cache()
        except Exception:
            pass

        if self.parent_app and hasattr(self.parent_app, "schedule_panel_refresh"):
            self.parent_app.schedule_panel_refresh(center=True)

        self._set_feedback_label(
            self.test_access_result,
            t("gcal_settings.test_access_idle", "No test has been run yet."),
            "help",
        )

        self._refresh_parent_state()
        self._refresh_status()
        if not notify:
            return
        QMessageBox.information(
            self,
            t("gcal_settings.reset_done_title", "Reset complete"),
            t(
                "gcal_settings.reset_done_body",
                "Google auth/linkage data was cleared.\nRemoved calendars: {cal_count}\nRemoved subscriptions: {sub_count}",
                cal_count=removed_calendar_count,
                sub_count=removed_subscription_count,
            ),
        )
