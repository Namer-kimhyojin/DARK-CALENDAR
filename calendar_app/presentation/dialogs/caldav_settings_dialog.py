# -*- coding: utf-8 -*-
"""CalDAV connection with explicit capabilities, selection and conflict recovery."""

import sqlite3

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from calendar_app.app_paths import DB_PATH
from calendar_app.application.calendar_provider_catalog import CALDAV_SERVICES
from calendar_app.infrastructure.caldav_sync.client import CalDAVClient
from calendar_app.infrastructure.caldav_sync.profiles import PROFILES, server_urls
from calendar_app.infrastructure.calendar_sync.repository import CalendarSyncRepository
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.main_window.calendar_sync_coordinator import provider_name

from .dialog_styles import (
    apply_common_dialog_style,
    build_collapsible_section,
    build_dialog_footer,
    get_dialog_theme_tokens,
)
from .provider_settings_widgets import (
    calendar_snapshot_key,
    plain_label,
    scroll_page,
    update_calendar_items,
    update_issue_items,
)
from .sync_feedback import (
    add_sync_hub_return,
    calendar_recovery_issues,
    calendar_selection_style,
    conflict_text,
    guard_sync_database,
    recovery_issue_label,
    recovery_issue_text,
    sync_error_message,
)
from .sync_recovery import requires_account_reconnection, sync_recovery_action


class CalDAVSettingsDialog(QDialog):
    def __init__(self, app, controllers, service="icloud"):
        super().__init__(app)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.app, self.controllers, self.settings = app, controllers, app.settings
        self._available_key = None
        self._last_status = None
        self._cancel_requested = False
        self._was_busy = False
        self.setWindowTitle(t("global_caldav.title", "CalDAV 계정 연결"))
        apply_common_dialog_style(
            self,
            minimum_width=620,
            extra_stylesheet=calendar_selection_style(get_dialog_theme_tokens()),
        )
        self.resize(700, 720)
        outer = QVBoxLayout(self)
        add_sync_hub_return(self, outer, app)
        row = QHBoxLayout()
        row.addWidget(QLabel(t("caldav.service", "연결 서비스")))
        self.service = QComboBox()
        for key in CALDAV_SERVICES:
            self.service.addItem(provider_name(key), key)
        self.service.setCurrentIndex(max(0, self.service.findData(service)))
        row.addWidget(self.service, 1)
        outer.addLayout(row)
        self.account = plain_label()
        self.status = plain_label()
        self.next_step = plain_label()
        for label in (self.account, self.status, self.next_step):
            outer.addWidget(label)
        actions = QHBoxLayout()
        self.next_action = QPushButton()
        self.next_action.setObjectName("ghost_btn")
        self.next_action.clicked.connect(self._next_action)
        actions.addWidget(self.next_action)
        self.cancel_work = QPushButton(t("provider_ui.cancel_work", "중단 요청"))
        self.cancel_work.setObjectName("ghost_btn")
        self.cancel_work.clicked.connect(self._cancel_work)
        actions.addWidget(self.cancel_work)
        outer.addLayout(actions)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        connection = QWidget()
        root = QVBoxLayout(connection)
        self.tabs.addTab(scroll_page(connection), t("caldav.connection", "1. 계정 연결"))
        self.guide = plain_label()
        root.addWidget(self.guide)
        self.server_label = QLabel(t("global_caldav.server", "계정 데이터센터 서버"))
        root.addWidget(self.server_label)
        self.server = QComboBox()
        self.server.setAccessibleName(self.server_label.text())
        self.server.currentTextChanged.connect(self._server_changed)
        root.addWidget(self.server)
        root.addWidget(QLabel(t("caldav.username", "계정")))
        self.username = QLineEdit()
        self.username.setAccessibleName(t("caldav.username", "계정"))
        self.username.returnPressed.connect(lambda: self.password.setFocus())
        root.addWidget(self.username)
        self.password_label = QLabel(t("caldav.password", "앱 전용 암호"))
        root.addWidget(self.password_label)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setAccessibleName(t("caldav.password", "앱 전용 암호"))
        self.password.returnPressed.connect(self._connect)
        self.password.setPlaceholderText(
            t("provider_ui.password_hint", "일반 로그인 암호 대신 앱 전용 암호를 입력하세요.")
        )
        root.addWidget(self.password)
        self.show_password = QCheckBox(t("caldav.show_password", "입력한 암호 표시"))
        self.show_password.toggled.connect(
            lambda value: self.password.setEchoMode(
                QLineEdit.EchoMode.Normal if value else QLineEdit.EchoMode.Password
            )
        )
        root.addWidget(self.show_password)
        help_button = QPushButton(t("caldav.help", "서비스의 인증 설정 안내"))
        help_button.setObjectName("ghost_btn")
        help_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(PROFILES[self.service.currentData()]["help"]))
        )
        root.addWidget(help_button)
        technical = QWidget()
        technical_layout = QVBoxLayout(technical)
        self.server_info = plain_label()
        technical_layout.addWidget(self.server_info)
        section, self.technical_toggle = build_collapsible_section(
            t("provider_ui.server_details", "서버 · 연결 방식 안내"),
            technical,
        )
        root.addLayout(section)
        row = QHBoxLayout()
        self.connect_btn = QPushButton(t("caldav.connect", "연결 확인 · 캘린더 찾기"))
        self.connect_btn.setObjectName("primary_btn")
        self.connect_btn.clicked.connect(self._connect)
        row.addWidget(self.connect_btn)
        self.disconnect = QPushButton(t("outlook.disconnect", "연결 해제"))
        self.disconnect.setObjectName("ghost_btn")
        self.disconnect.clicked.connect(lambda: self.controller.start("disconnect"))
        row.addWidget(self.disconnect)
        root.addLayout(row)
        privacy = QLabel(
            t(
                "caldav.privacy",
                "암호는 현재 Windows 사용자만 복호화할 수 있도록 암호화해 저장합니다. 연결 해제 후에도 기존 일정은 보존됩니다.",
            )
        )
        privacy.setWordWrap(True)
        root.addWidget(privacy)
        root.addStretch()
        sync = QWidget()
        root = QVBoxLayout(sync)
        self.tabs.addTab(scroll_page(sync), t("caldav.selection", "2. 캘린더 선택"))
        row = QHBoxLayout()
        row.addWidget(QLabel(t("outlook.calendar_selection", "동기화할 캘린더 선택")), 1)
        self.refresh = QPushButton(t("caldav.refresh", "목록 새로고침"))
        self.refresh.setObjectName("ghost_btn")
        self.refresh.clicked.connect(lambda: self.controller.start("refresh"))
        row.addWidget(self.refresh)
        root.addLayout(row)
        root.addWidget(
            plain_label(
                t(
                    "provider_ui.selection_help",
                    "가져올 캘린더를 체크하세요. 읽기 전용 캘린더도 가져올 수 있습니다.",
                )
            )
        )
        self.calendars = QListWidget()
        self.calendars.setObjectName("SyncCalendarSelection")
        self.calendars.setAccessibleName(t("outlook.calendar_selection", "동기화할 캘린더 선택"))
        self.calendars.setMinimumHeight(140)
        self.calendars.itemChanged.connect(self._update_actions)
        root.addWidget(self.calendars, 1)
        self.selection_info = plain_label()
        root.addWidget(self.selection_info)
        self.enable = QCheckBox(t("outlook.auto_sync", "5분마다 자동 동기화"))
        self.enable.toggled.connect(self._enable)
        root.addWidget(self.enable)
        row = QHBoxLayout()
        self.save = QPushButton(t("caldav.save", "선택 저장"))
        self.save.setObjectName("ghost_btn")
        self.save.clicked.connect(lambda: self._save())
        row.addWidget(self.save)
        self.sync = QPushButton(t("outlook.sync_now", "지금 동기화"))
        self.sync.setObjectName("primary_btn")
        self.sync.clicked.connect(self._save_and_sync)
        row.addWidget(self.sync)
        root.addLayout(row)
        note = QLabel(
            t(
                "caldav.scope",
                "조회 범위: 지난 120일 ~ 앞으로 400일. 반복·초대 일정은 조회 전용입니다. 선택 해제는 동기화만 멈춥니다. 서비스 사이에서 일정을 자동 복사하지 않습니다.",
            )
        )
        note.setWordWrap(True)
        root.addWidget(note)
        problems = QWidget()
        root = QVBoxLayout(problems)
        self.tabs.addTab(scroll_page(problems), t("caldav.problems", "3. 확인할 문제"))
        self.issues = QListWidget()
        self.issues.setMinimumHeight(100)
        self.issues.currentItemChanged.connect(self._preview)
        root.addWidget(self.issues, 1)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(90)
        self.preview.setPlaceholderText(
            t("sync_ui.compare_hint", "충돌을 선택하면 내 변경과 서비스 내용을 비교할 수 있습니다.")
        )
        self.preview.setMaximumHeight(160)
        root.addWidget(self.preview)
        row = QVBoxLayout()
        self.local = QPushButton(t("outlook.keep_local", "선택 충돌: 내 변경 유지"))
        self.remote = QPushButton(t("caldav.keep_remote", "서비스 내용 적용"))
        self.local.clicked.connect(lambda: self._resolve("local"))
        self.remote.clicked.connect(lambda: self._resolve("remote"))
        row.addWidget(self.local)
        row.addWidget(self.remote)
        root.addLayout(row)
        row = QVBoxLayout()
        self.retry = QPushButton(t("outlook.retry_delete", "선택 삭제 다시 시도"))
        self.cancel_delete = QPushButton(t("caldav.cancel_delete", "삭제 취소 · 서비스 일정 유지"))
        self.retry.clicked.connect(lambda: self._queue("retry"))
        self.cancel_delete.clicked.connect(lambda: self._queue("cancel"))
        row.addWidget(self.retry)
        row.addWidget(self.cancel_delete)
        root.addLayout(row)
        footer, close, _ = build_dialog_footer(
            ok_label=t("outlook.close", "닫기"), cancel_label=None
        )
        close.clicked.connect(self.accept)
        close.setDefault(False)
        close.setAutoDefault(False)
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
            button.setDefault(False)
        outer.addLayout(footer)
        self._countdown = QTimer(self)
        self._countdown.setInterval(1000)
        self._countdown.timeout.connect(self._update_actions)
        self._countdown.start()
        for controller in controllers.values():
            controller.changed.connect(self._refresh)
        self.service.currentIndexChanged.connect(self._service_changed)
        self._service_changed()

    @property
    def controller(self):
        return self.controllers[self.service.currentData()]

    @property
    def prefix(self):
        return self.controller.prefix

    def _update_actions(self, *_):
        busy, connected = self.controller.busy, bool(self.controller.account)
        selected = sum(
            self.calendars.item(i).checkState() == Qt.CheckState.Checked
            for i in range(self.calendars.count())
        )
        saved_ids = getattr(self.calendars, "_provider_saved", set())
        saved = len(saved_ids)
        remaining = getattr(self.controller, "retry_remaining_seconds", 0)
        error = self.settings.value(self.prefix + "last_error", "", type=str)
        if requires_account_reconnection(self.controller.status):
            error = self.controller.status
        can_sync = (
            connected
            and selected > 0
            and not busy
            and not remaining
            and not requires_account_reconnection(error)
        )
        self.sync.setEnabled(can_sync)
        self.refresh.setEnabled(
            connected and not busy and not remaining and not requires_account_reconnection(error)
        )
        self.enable.setEnabled(connected and not busy and saved > 0)
        dirty = any(
            (self.calendars.item(i).checkState() == Qt.CheckState.Checked)
            != (self.calendars.item(i).data(Qt.ItemDataRole.UserRole)["id"] in saved_ids)
            for i in range(self.calendars.count())
        )
        self.sync.setText(
            t("provider_ui.save_sync", "선택 저장 후 동기화")
            if dirty
            else t("outlook.sync_now", "지금 동기화")
        )
        self.selection_info.setText(
            t(
                "provider_ui.selection_count",
                "선택 {selected}개 · 저장됨 {saved}개",
                selected=selected,
                saved=saved,
            )
            + (
                "\n" + t("provider_ui.unsaved", "변경한 선택은 저장 후 적용됩니다.")
                if dirty
                else ""
            )
        )
        state = {
            "busy": busy,
            "connected": connected,
            "needs_selection": selected == 0,
            "error": error
            or (
                self.controller.status
                if self.controller.status
                not in {
                    "idle",
                    "connected",
                    "refreshed",
                    "selection_saved",
                    "completed",
                    "cancelled",
                }
                else ""
            ),
            "retry_remaining": remaining,
            "issues": max(
                self.issues.count(),
                self.controller.summary.get("issues", 0)
                if self.controller.status == "completed_with_issues"
                else 0,
            ),
            "can_sync": can_sync,
        }
        self._recovery = sync_recovery_action(self.service.currentData(), state)
        hint = self._recovery["hint"]
        if remaining and self._recovery["kind"] != "wait":
            hint += "\n" + t(
                "provider_ui.wait",
                "서비스 요청 제한: {seconds}초 후 다시 시도할 수 있습니다.",
                seconds=remaining,
            )
        if self._cancel_requested and busy:
            hint = t(
                "provider_ui.cancelling",
                "중단을 요청했습니다. 진행 중인 응답이 끝나면 작업을 멈춥니다.",
            )
        self.next_step.setText(hint)
        self.next_action.setText(self._recovery["label"])
        self.next_action.setVisible(
            not busy and self._recovery["kind"] not in {"manage", "wait", "retry"}
        )
        self.cancel_work.setVisible(busy and self.controller.status != "disconnect")
        worker = getattr(self.controller, "worker", None)
        self.cancel_work.setEnabled(
            busy
            and not self._cancel_requested
            and callable(getattr(worker, "requestInterruption", None))
        )
        self._preview()

    def _next_action(self):
        kind = self._recovery["kind"]
        if kind == "retry":
            self._save_and_sync()
        else:
            self.tabs.setCurrentIndex(2 if kind == "issues" else 1 if kind == "select" else 0)
            if kind in {"connect", "reconnect"}:
                self.password.setFocus() if self.username.text() else self.username.setFocus()

    def _cancel_work(self):
        worker = getattr(self.controller, "worker", None)
        if (
            self.controller.busy
            and self.controller.status != "disconnect"
            and callable(getattr(worker, "requestInterruption", None))
        ):
            worker.requestInterruption()
            self._cancel_requested = True
            self._update_actions()

    def _save_and_sync(self):
        self._update_actions()
        if self.sync.isEnabled() and self._save():
            self.controller.sync(force=True)

    def _enable(self, enabled):
        self.settings.setValue(self.prefix + "enabled", enabled)
        self._update_actions()

    def _db(self):
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        CalendarSyncRepository(conn, "caldav")
        return conn

    def _service_changed(self, *_):
        self._last_status = None
        self._cancel_requested = False
        self.password.clear()
        self.show_password.setChecked(False)
        self.username.setText(self.settings.value(self.prefix + "account_name", "", type=str))
        self.username.setPlaceholderText(
            t("caldav.icloud_user", "Apple 계정 이메일")
            if self.service.currentData() == "icloud"
            else t("caldav.naver_user", "네이버 아이디")
            if self.service.currentData() == "naver"
            else t("global_caldav.email", "계정 이메일 전체 주소")
        )
        icloud = self.service.currentData() in {"icloud", "yahoo", "fastmail"}
        self.password_label.setText(
            t("caldav.password", "앱 전용 암호")
            if icloud
            else t("provider_ui.auth_password", "인증 암호")
        )
        self.password.setAccessibleName(self.password_label.text())
        self.password.setPlaceholderText(
            t("provider_ui.password_hint", "일반 로그인 암호 대신 앱 전용 암호를 입력하세요.")
            if icloud
            else t(
                "provider_ui.naver_password_hint",
                "인증 안내에서 계정에 맞는 암호 종류를 확인하세요.",
            )
        )
        self.guide.setText(
            t(
                "caldav.icloud_guide",
                "iCloud: 이중 인증을 켜고 Apple 계정에서 앱 전용 암호를 발급하세요. 개인 일정은 양방향 동기화합니다.",
            )
            if self.service.currentData() == "icloud"
            else t(
                "caldav.naver_guide",
                "네이버: 읽기 전용으로 가져옵니다. 2단계 인증 사용 시 애플리케이션 비밀번호가 필요합니다. Windows 연결은 서비스 정책에 따라 제한될 수 있습니다.",
            )
        )
        service = self.service.currentData()
        if service in {"yahoo", "zoho", "fastmail"}:
            self.guide.setText(
                t(
                    "global_caldav." + service + "_guide",
                    {
                        "yahoo": "Yahoo Calendar: Yahoo 계정의 앱 암호를 발급하세요. Yahoo! JAPAN 계정은 지원하지 않습니다.",
                        "zoho": "Zoho Calendar: 웹 설정에서 CalDAV에 사용할 캘린더를 먼저 선택하세요. 계정 데이터센터 서버를 선택하고, 2단계 인증 사용 시 앱 전용 암호를 입력하세요.",
                        "fastmail": "Fastmail: CalDAV 접근 권한이 있는 앱 암호를 발급하세요. 외부 캘린더 클라이언트를 지원하는 요금제가 필요합니다.",
                    }[service],
                )
            )
        self.server.clear()
        self.server.addItems(server_urls(service))
        saved_server = self.settings.value(
            self.prefix + "server_url", PROFILES[service]["url"], type=str
        )
        self.server.setCurrentIndex(max(0, self.server.findText(saved_server)))
        self.server.setVisible(service == "zoho")
        self.server_label.setVisible(service == "zoho")
        self.server_info.setText(
            t(
                "provider_ui.server_info",
                "서버 주소는 서비스에 맞게 자동으로 설정됩니다.\n{url}",
                url=PROFILES[self.service.currentData()]["url"],
            )
        )
        self.enable.blockSignals(True)
        self.enable.setChecked(self.settings.value(self.prefix + "enabled", False, type=bool))
        self.enable.blockSignals(False)
        self._available_key = None
        self._refresh()

    def _connect(self):
        if self.controller.busy:
            return
        if not self.username.text().strip() or not self.password.text():
            self.controller.status = "credentials_required"
            self._refresh()
            self.username.setFocus() if not self.username.text().strip() else self.password.setFocus()
            return
        options = (
            {"server_url": self.server.currentText()}
            if self.service.currentData() == "zoho"
            else {}
        )
        if self.controller.start("login", self.username.text(), self.password.text(), **options):
            self.password.clear()
            self.show_password.setChecked(False)

    def _server_changed(self, url):
        if hasattr(self, "server_info") and url:
            self.server_info.setText(
                t(
                    "provider_ui.server_info",
                    "서버 주소는 서비스에 맞게 자동으로 설정됩니다.\n{url}",
                    url=url,
                )
            )

    @guard_sync_database
    def _populate(self):
        if not self.controller.account:
            update_calendar_items(self.calendars, "", [], [])
            return
        conn = self._db()
        try:
            repo = CalendarSyncRepository(conn, "caldav")
            saved = repo.calendars(self.controller.account)
            available = self.controller.available or [
                {
                    "id": r["remote_id"],
                    "name": conn.execute(
                        "SELECT name FROM calendar WHERE id=?", (r["local_id"],)
                    ).fetchone()[0],
                    "can_edit": bool(r["can_edit"]),
                }
                for r in saved
            ]
            choices = []
            for remote in available:
                own = next((row for row in saved if row["remote_id"] == remote["id"]), None)
                label = (
                    (own["display_name"] if own else remote["name"])
                    + " · "
                    + (
                        t("caldav.two_way", "양방향")
                        if remote["can_edit"]
                        else t("outlook.read_only", "읽기 전용")
                    )
                )
                choices.append((label, remote))
            update_calendar_items(self.calendars, self.controller.account, choices, saved)
        finally:
            conn.close()

    @guard_sync_database
    def _save(self):
        if self.controller.busy or not self.controller.account:
            return
        selected = [
            self.calendars.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.calendars.count())
            if self.calendars.item(i).checkState() == Qt.CheckState.Checked
        ]
        conn = self._db()
        try:
            CalendarSyncRepository(conn, "caldav").save_selection(self.controller.account, selected)
        finally:
            conn.close()
        if not selected:
            self.settings.setValue(self.prefix + "enabled", False)
            self.enable.blockSignals(True)
            self.enable.setChecked(False)
            self.enable.blockSignals(False)
        self.controller.status = "selection_saved"
        self.app.schedule_panel_refresh(left=True, center=True, right=True)
        self._available_key = None
        self._refresh()
        return True

    def _preview(self, *_):
        item = self.issues.currentItem()
        data = item.data(Qt.ItemDataRole.UserRole) if item else {}
        conflict = data.get("kind") == "conflict"
        recovery = bool(data.get("recovery_issue"))
        queued = "event_id" in data or recovery
        self.local.setEnabled(conflict and not self.controller.busy)
        self.remote.setEnabled(conflict and not self.controller.busy)
        self.retry.setEnabled(
            queued
            and not self.controller.busy
            and not getattr(self.controller, "retry_remaining_seconds", 0)
        )
        self.cancel_delete.setEnabled(queued and not self.controller.busy and not recovery)
        self.retry.setText(
            t("sync_recovery.recheck", "다시 확인")
            if recovery
            else t("outlook.retry_delete", "선택 삭제 다시 시도")
        )
        preview = (
            conflict_text(
                data, CalDAVClient, self.settings.value("gcal_timezone", "Asia/Seoul", type=str)
            )
            if conflict
            else recovery_issue_text(data)
            if recovery
            else sync_error_message(data["kind"])
            if data.get("kind")
            else ""
        )
        if self.preview.toPlainText() != preview:
            self.preview.setPlainText(preview)

    @guard_sync_database
    def _resolve(self, choice):
        item = self.issues.currentItem()
        if not item or self.controller.busy:
            return
        conn = self._db()
        resolved = False
        try:
            if CalendarSyncRepository(conn, "caldav").resolve(
                item.data(Qt.ItemDataRole.UserRole).get("task_id"),
                choice,
                self.settings.value("gcal_timezone", "Asia/Seoul", type=str),
                CalDAVClient,
            ):
                resolved = True
                self.app.schedule_panel_refresh(left=True, center=True, right=True)
            else:
                self.controller.status = "conflict_snapshot_changed"
        finally:
            conn.close()
        self._available_key = None
        self._refresh()
        if resolved and choice == "local":
            self.controller.sync(force=True)

    @guard_sync_database
    def _queue(self, choice):
        item = self.issues.currentItem()
        if not item or self.controller.busy:
            return
        row = item.data(Qt.ItemDataRole.UserRole)
        if row.get("recovery_issue"):
            if choice == "retry":
                self.controller.sync(force=True)
            return
        if "event_id" not in row or choice not in {"retry", "cancel"}:
            return
        conn = self._db()
        try:
            with conn:
                where = "WHERE event_id=? AND calendar_id=? AND calendar_id IN (SELECT local_id FROM calendar_sync_calendar WHERE account_id=?)"
                sql = (
                    "UPDATE calendar_sync_delete_queue SET attempts=0,error=NULL "
                    if choice == "retry"
                    else "DELETE FROM calendar_sync_delete_queue "
                )
                changed = conn.execute(
                    sql + where, (row["event_id"], row["calendar_id"], self.controller.account)
                ).rowcount
        finally:
            conn.close()
        self._available_key = None
        self._refresh()
        if changed and choice == "retry":
            self.controller.sync(force=True)

    @guard_sync_database
    def _refresh(self):
        if self.sender() in self.controllers.values() and self.sender() is not self.controller:
            return
        connected, busy = bool(self.controller.account), self.controller.busy
        self.service.setEnabled(not any(c.busy for c in self.controllers.values()))
        if not busy and self._cancel_requested:
            self._cancel_requested = False
            if self.controller.status in {"login", "sync", "refresh", "disconnect"}:
                self.controller.status = "cancelled"
        for widget in (
            self.username,
            self.password,
            self.connect_btn,
            self.show_password,
            self.server,
        ):
            widget.setEnabled(not busy)
        for widget in (
            self.disconnect,
            self.refresh,
            self.save,
            self.sync,
            self.enable,
            self.calendars,
        ):
            widget.setEnabled(connected and not busy)
        self.account.setText(
            self.settings.value(self.prefix + "account_name", "", type=str)
            or t("caldav.not_connected", "연결되지 않음")
        )
        code = self.controller.status
        signature = calendar_snapshot_key(self.controller.account, self.controller.available)
        refresh_data = not busy and (
            signature != self._available_key or code != self._last_status or self._was_busy
        )
        self._was_busy = busy
        messages = {
            "idle": t("provider_ui.connected", "계정이 연결되어 있습니다.")
            if connected
            else t("caldav.idle", "계정을 연결한 뒤 동기화할 캘린더를 선택하고 저장하세요."),
            "login": t("caldav.connecting", "계정을 확인하고 캘린더를 찾고 있습니다..."),
            "connected": t("provider_ui.connected", "계정이 연결되어 있습니다."),
            "sync": t("caldav.syncing", "일정을 동기화하고 있습니다..."),
            "refresh": t("caldav.refreshing", "캘린더 목록을 새로고침하고 있습니다..."),
            "refreshed": t(
                "caldav.refreshed", "목록을 새로고침했습니다. 선택을 확인하고 저장하세요."
            ),
            "selection_saved": t("outlook.status_saved", "캘린더 선택을 저장했습니다."),
            "completed": t("outlook.status_completed", "동기화 완료"),
            "completed_with_issues": sync_error_message("completed_with_issues"),
            "disconnect": t("caldav.disconnecting", "연결을 해제하고 있습니다..."),
            "disconnected": t(
                "outlook.status_disconnected", "연결 해제됨. 기존 일정은 보존됩니다."
            ),
            "cancelled": t(
                "provider_ui.cancelled", "작업을 중단했습니다. 기존 일정과 연결은 유지됩니다."
            ),
        }
        text = messages.get(code) or sync_error_message(code)
        if code in {"completed", "completed_with_issues"}:
            text += " · " + t(
                "outlook.summary",
                "가져옴 {imported} / 수정 {updated} / 생성 {created} / 삭제 {deleted} / 확인 필요 {issues}",
            ).format(
                **{
                    key: self.controller.summary.get(key, 0)
                    for key in ("imported", "updated", "created", "deleted", "issues")
                }
            )
        last = self.settings.value(self.prefix + "last_success", "", type=str)
        if last:
            text += "\n" + t("caldav.last_success", "마지막 성공: {time}").format(time=last)
        self.status.setText(text)
        if refresh_data and self._populate() is False:
            return
        if not busy and code == "connected" and self._last_status != "connected":
            self.tabs.setCurrentIndex(1)
        if not busy:
            self._last_status = code
        entries = []
        if connected and refresh_data:
            conn = self._db()
            try:
                repo = CalendarSyncRepository(conn, "caldav")
                issues = repo.issues(self.controller.account)
                for issue in issues:
                    task = conn.execute(
                        "SELECT name FROM unified_task WHERE id=?", (issue["task_id"],)
                    ).fetchone()
                    label = (
                        (task[0] if task else str(issue["task_id"]))
                        + " · "
                        + sync_error_message(issue["kind"])
                    )
                    entries.append((label, {0: issue}))
                for row in conn.execute(
                    "SELECT q.* FROM calendar_sync_delete_queue q JOIN calendar_sync_calendar c ON c.local_id=q.calendar_id WHERE c.account_id=?",
                    (self.controller.account,),
                ):
                    data = dict(row)
                    data["kind"] = data["error"] or "delete_pending"
                    label = t("caldav.delete_pending", "삭제 대기 · {attempts}/5회").format(
                        attempts=data["attempts"]
                    )
                    entries.append((label, {0: data}))
                for row in calendar_recovery_issues(
                    repo, self.settings, self.controller.prefix, self.controller.account
                ):
                    entries.append((recovery_issue_label(row), {0: row}))
            finally:
                conn.close()
        if refresh_data:
            update_issue_items(self.issues, self.controller.account, entries)
            self._available_key = signature
        self._update_actions()
