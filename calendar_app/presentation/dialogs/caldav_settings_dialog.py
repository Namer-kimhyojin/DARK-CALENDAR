# -*- coding: utf-8 -*-
"""CalDAV connection with explicit capabilities, selection and conflict recovery."""

import sqlite3

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from calendar_app.app_paths import DB_PATH
from calendar_app.infrastructure.caldav_sync.client import CalDAVClient
from calendar_app.infrastructure.caldav_sync.profiles import PROFILES
from calendar_app.infrastructure.calendar_sync.repository import CalendarSyncRepository
from calendar_app.infrastructure.i18n import t

from .dialog_styles import apply_common_dialog_style, build_dialog_footer, get_dialog_theme_tokens
from .sync_feedback import (
    add_sync_hub_return,
    calendar_selection_style,
    conflict_text,
    guard_sync_database,
    sync_error_message,
)


class CalDAVSettingsDialog(QDialog):
    def __init__(self, app, controllers, service="icloud"):
        super().__init__(app)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.app, self.controllers, self.settings = app, controllers, app.settings
        self._available_key = None
        self.setWindowTitle(t("caldav.title", "iCloud · 네이버 캘린더 연결"))
        apply_common_dialog_style(
            self,
            minimum_width=620,
            extra_stylesheet=calendar_selection_style(get_dialog_theme_tokens()),
        )
        self.resize(740, 780)
        outer = QVBoxLayout(self)
        add_sync_hub_return(self, outer, app)
        row = QHBoxLayout()
        row.addWidget(QLabel(t("caldav.service", "연결 서비스")))
        self.service = QComboBox()
        self.service.addItem("iCloud", "icloud")
        self.service.addItem(t("caldav.naver", "네이버"), "naver")
        self.service.setCurrentIndex(0 if service == "icloud" else 1)
        row.addWidget(self.service, 1)
        outer.addLayout(row)
        self.guide = QLabel()
        self.guide.setWordWrap(True)
        outer.addWidget(self.guide)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        connection = QWidget()
        root = QVBoxLayout(connection)
        self.tabs.addTab(connection, t("caldav.connection", "1. 계정 연결"))
        root.addWidget(QLabel(t("caldav.username", "계정")))
        self.username = QLineEdit()
        self.username.setAccessibleName(t("caldav.username", "계정"))
        root.addWidget(self.username)
        root.addWidget(QLabel(t("caldav.password", "앱 전용 암호")))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setAccessibleName(t("caldav.password", "앱 전용 암호"))
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
        self.tabs.addTab(sync, t("caldav.selection", "2. 캘린더 선택"))
        row = QHBoxLayout()
        row.addWidget(QLabel(t("outlook.calendar_selection", "동기화할 캘린더 선택")), 1)
        self.refresh = QPushButton(t("caldav.refresh", "목록 새로고침"))
        self.refresh.clicked.connect(lambda: self.controller.start("refresh"))
        row.addWidget(self.refresh)
        root.addLayout(row)
        self.calendars = QListWidget()
        self.calendars.setObjectName("SyncCalendarSelection")
        self.calendars.setAccessibleName(t("outlook.calendar_selection", "동기화할 캘린더 선택"))
        root.addWidget(self.calendars, 1)
        self.enable = QCheckBox(t("outlook.auto_sync", "5분마다 자동 동기화"))
        self.enable.toggled.connect(
            lambda enabled: self.settings.setValue(self.prefix + "enabled", enabled)
        )
        root.addWidget(self.enable)
        row = QHBoxLayout()
        self.save = QPushButton(t("caldav.save", "선택 저장"))
        self.save.clicked.connect(lambda: self._save())
        row.addWidget(self.save)
        self.sync = QPushButton(t("outlook.sync_now", "지금 동기화"))
        self.sync.setObjectName("primary_btn")
        self.sync.clicked.connect(lambda: self.controller.sync(force=True))
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
        self.tabs.addTab(problems, t("caldav.problems", "3. 확인할 문제"))
        self.issues = QListWidget()
        self.issues.currentItemChanged.connect(self._preview)
        root.addWidget(self.issues, 1)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText(
            t("sync_ui.compare_hint", "충돌을 선택하면 내 변경과 서비스 내용을 비교할 수 있습니다.")
        )
        self.preview.setMaximumHeight(160)
        root.addWidget(self.preview)
        row = QHBoxLayout()
        self.local = QPushButton(t("outlook.keep_local", "선택 충돌: 내 변경 유지"))
        self.remote = QPushButton(t("caldav.keep_remote", "서비스 내용 적용"))
        self.local.clicked.connect(lambda: self._resolve("local"))
        self.remote.clicked.connect(lambda: self._resolve("remote"))
        row.addWidget(self.local)
        row.addWidget(self.remote)
        root.addLayout(row)
        row = QHBoxLayout()
        self.retry = QPushButton(t("outlook.retry_delete", "선택 삭제 다시 시도"))
        self.cancel_delete = QPushButton(t("caldav.cancel_delete", "삭제 취소 · 서비스 일정 유지"))
        self.retry.clicked.connect(lambda: self._queue("retry"))
        self.cancel_delete.clicked.connect(lambda: self._queue("cancel"))
        row.addWidget(self.retry)
        row.addWidget(self.cancel_delete)
        root.addLayout(row)
        self.account = QLabel()
        self.status = QLabel()
        for label in (self.account, self.status):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            outer.addWidget(label)
        footer, close, _ = build_dialog_footer(
            ok_label=t("outlook.close", "닫기"), cancel_label=None
        )
        close.clicked.connect(self.accept)
        outer.addLayout(footer)
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

    def _db(self):
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        CalendarSyncRepository(conn, "caldav")
        return conn

    def _service_changed(self, *_):
        self.password.clear()
        self.show_password.setChecked(False)
        self.username.setText(self.settings.value(self.prefix + "account_name", "", type=str))
        self.username.setPlaceholderText(
            t("caldav.icloud_user", "Apple 계정 이메일")
            if self.service.currentData() == "icloud"
            else t("caldav.naver_user", "네이버 아이디")
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
        self.enable.blockSignals(True)
        self.enable.setChecked(self.settings.value(self.prefix + "enabled", False, type=bool))
        self.enable.blockSignals(False)
        self._available_key = None
        self._populate()
        self._refresh()

    def _connect(self):
        if self.controller.start("login", self.username.text(), self.password.text()):
            self.password.clear()
            self.show_password.setChecked(False)

    @guard_sync_database
    def _populate(self):
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
            self.calendars.clear()
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
                item = QListWidgetItem(label)
                item.setToolTip(remote["name"])
                item.setData(Qt.ItemDataRole.UserRole, remote)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                selected = any(r["remote_id"] == remote["id"] and r["is_active"] for r in saved)
                item.setCheckState(Qt.CheckState.Checked if selected else Qt.CheckState.Unchecked)
                self.calendars.addItem(item)
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
        self.controller.status = "selection_saved"
        self.app.schedule_panel_refresh(left=True, center=True, right=True)
        self._refresh()

    def _preview(self, *_):
        item = self.issues.currentItem()
        data = item.data(Qt.ItemDataRole.UserRole) if item else {}
        conflict = data.get("kind") == "conflict"
        queued = "event_id" in data
        self.local.setEnabled(conflict and not self.controller.busy)
        self.remote.setEnabled(conflict and not self.controller.busy)
        self.retry.setEnabled(queued and not self.controller.busy)
        self.cancel_delete.setEnabled(queued and not self.controller.busy)
        self.preview.setPlainText(
            conflict_text(
                data, CalDAVClient, self.settings.value("gcal_timezone", "Asia/Seoul", type=str)
            )
            if conflict
            else sync_error_message(data["kind"])
            if data.get("kind")
            else ""
        )

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
        self._refresh()
        if resolved and choice == "local":
            self.controller.sync(force=True)

    @guard_sync_database
    def _queue(self, choice):
        item = self.issues.currentItem()
        if not item or self.controller.busy:
            return
        row = item.data(Qt.ItemDataRole.UserRole)
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
        self._refresh()
        if changed and choice == "retry":
            self.controller.sync(force=True)

    @guard_sync_database
    def _refresh(self):
        if self.sender() in self.controllers.values() and self.sender() is not self.controller:
            return
        connected, busy = bool(self.controller.account), self.controller.busy
        for widget in (self.username, self.password, self.connect_btn, self.show_password):
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
        messages = {
            "idle": t("caldav.idle", "계정을 연결한 뒤 동기화할 캘린더를 선택하고 저장하세요."),
            "login": t("caldav.connecting", "계정을 확인하고 캘린더를 찾고 있습니다..."),
            "connected": t("caldav.connected", "연결 완료. 캘린더를 선택하고 저장하세요."),
            "sync": t("caldav.syncing", "일정을 동기화하고 있습니다..."),
            "refresh": t("caldav.refreshing", "캘린더 목록을 새로고침하고 있습니다..."),
            "refreshed": t(
                "caldav.refreshed", "목록을 새로고침했습니다. 선택을 확인하고 저장하세요."
            ),
            "selection_saved": t("outlook.status_saved", "캘린더 선택을 저장했습니다."),
            "completed": t("outlook.status_completed", "동기화 완료"),
            "disconnect": t("caldav.disconnecting", "연결을 해제하고 있습니다..."),
            "disconnected": t(
                "outlook.status_disconnected", "연결 해제됨. 기존 일정은 보존됩니다."
            ),
        }
        text = messages.get(code) or sync_error_message(code)
        if code == "completed":
            text += " · " + t(
                "outlook.summary",
                "가져옴 {imported} / 수정 {updated} / 생성 {created} / 삭제 {deleted} / 확인 필요 {issues}",
            ).format(**self.controller.summary)
        last = self.settings.value(self.prefix + "last_success", "", type=str)
        if last:
            text += "\n" + t("caldav.last_success", "마지막 성공: {time}").format(time=last)
        self.status.setText(text)
        signature = (
            self.controller.account,
            tuple((c["id"], c["name"], c["can_edit"]) for c in self.controller.available),
        )
        if not busy and signature != self._available_key:
            self._available_key = signature
            self._populate()
            if code == "connected":
                self.tabs.setCurrentIndex(1)
        self.issues.clear()
        if connected and not busy:
            conn = self._db()
            try:
                issues = CalendarSyncRepository(conn, "caldav").issues(self.controller.account)
                for issue in issues:
                    task = conn.execute(
                        "SELECT name FROM unified_task WHERE id=?", (issue["task_id"],)
                    ).fetchone()
                    item = QListWidgetItem(
                        (task[0] if task else str(issue["task_id"]))
                        + " · "
                        + sync_error_message(issue["kind"])
                    )
                    item.setData(Qt.ItemDataRole.UserRole, issue)
                    self.issues.addItem(item)
                for row in conn.execute(
                    "SELECT q.* FROM calendar_sync_delete_queue q JOIN calendar_sync_calendar c ON c.local_id=q.calendar_id WHERE c.account_id=?",
                    (self.controller.account,),
                ):
                    data = dict(row)
                    data["kind"] = data["error"] or "delete_pending"
                    item = QListWidgetItem(
                        t("caldav.delete_pending", "삭제 대기 · {attempts}/5회").format(
                            attempts=data["attempts"]
                        )
                    )
                    item.setData(Qt.ItemDataRole.UserRole, data)
                    self.issues.addItem(item)
            finally:
                conn.close()
        self._preview()
