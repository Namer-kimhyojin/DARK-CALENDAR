# -*- coding: utf-8 -*-
"""Microsoft account connection, calendar selection and conflict resolution."""

import sqlite3
import uuid

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
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
from calendar_app.infrastructure.calendar_sync.repository import CalendarSyncRepository
from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.outlook_sync.graph import GraphClient
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_collapsible_section,
    build_dialog_footer,
    get_dialog_theme_tokens,
)
from calendar_app.presentation.dialogs.provider_settings_widgets import (
    calendar_snapshot_key,
    plain_label,
    scroll_page,
    update_calendar_items,
    update_issue_items,
)
from calendar_app.presentation.dialogs.sync_feedback import (
    add_sync_hub_return,
    calendar_recovery_issues,
    calendar_selection_style,
    conflict_text,
    guard_sync_database,
    recovery_issue_label,
    recovery_issue_text,
    sync_error_message,
)
from calendar_app.presentation.dialogs.sync_recovery import (
    requires_account_reconnection,
    sync_recovery_action,
)

SETUP_URL = "https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app"


class OutlookSettingsDialog(QDialog):
    def __init__(self, app, controller):
        super().__init__(app)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.app, self.controller, self.settings = app, controller, app.settings
        self._last_status = None
        self._cancel_requested = False
        self._available_key = None
        self._was_busy = False
        self.setWindowTitle(t("outlook.title", "Outlook · Microsoft 365 동기화"))
        apply_common_dialog_style(
            self,
            minimum_width=620,
            extra_stylesheet=calendar_selection_style(get_dialog_theme_tokens()),
        )
        self.resize(680, 720)
        outer = QVBoxLayout(self)
        add_sync_hub_return(self, outer, app)
        self.account = plain_label()
        outer.addWidget(self.account)
        self.status = plain_label()
        outer.addWidget(self.status)
        self.next_step = plain_label()
        outer.addWidget(self.next_step)
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
        connection_tab = QWidget()
        root = QVBoxLayout(connection_tab)
        self.tabs.addTab(scroll_page(connection_tab), t("caldav.connection", "1. 계정 연결"))
        outer.addWidget(self.tabs, 1)
        guide = QLabel(
            t(
                "outlook.setup_intro",
                "개인 Outlook 및 회사·학교 계정을 연결합니다.\n최초 연결 전에 Entra 앱 등록이 필요합니다. 비밀 키는 사용하지 않습니다.",
            )
        )
        guide.setWordWrap(True)
        root.addWidget(guide)
        technical = QWidget()
        technical_layout = QVBoxLayout(technical)
        details = plain_label(
            t(
                "outlook.setup_steps",
                "앱 등록: 개인 Microsoft 계정 + 모든 조직 디렉터리 지원\n플랫폼: 모바일 및 데스크톱 / 리디렉션 URI: http://localhost\nGraph 위임 권한: Calendars.ReadWrite, User.Read",
            )
        )
        details.setWordWrap(True)
        technical_layout.addWidget(details)
        setup = QPushButton(t("outlook.setup_guide", "Microsoft 앱 등록 안내 열기"))
        setup.setObjectName("ghost_btn")
        setup.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(SETUP_URL)))
        technical_layout.addWidget(setup)
        section, self.technical_toggle = build_collapsible_section(
            t("provider_ui.technical_setup", "앱 등록 · 연결 준비 안내"),
            technical,
            expanded=not bool(self.settings.value("outlook_client_id", "", type=str)),
        )
        root.addLayout(section)
        root.addWidget(QLabel(t("outlook.client_id", "애플리케이션(클라이언트) ID")))
        self.client_id = QLineEdit(self.settings.value("outlook_client_id", "", type=str))
        self.client_id.setPlaceholderText(
            t("outlook.client_id_hint", "Entra 앱 등록의 클라이언트 ID (비밀 키 아님)")
        )
        self.client_id.setAccessibleName(t("outlook.client_id", "애플리케이션(클라이언트) ID"))
        self.client_id.returnPressed.connect(self._login)
        root.addWidget(self.client_id)
        row = QHBoxLayout()
        self.login = QPushButton(t("outlook.login", "Microsoft 로그인"))
        self.login.setObjectName("primary_btn")
        self.login.clicked.connect(self._login)
        row.addWidget(self.login)
        self.disconnect = QPushButton(t("outlook.disconnect", "연결 해제"))
        self.disconnect.setObjectName("ghost_btn")
        self.disconnect.clicked.connect(lambda: self._disconnect())
        row.addWidget(self.disconnect)
        root.addLayout(row)
        root.addStretch()
        calendar_tab = QWidget()
        root = QVBoxLayout(calendar_tab)
        self.tabs.addTab(scroll_page(calendar_tab), t("caldav.selection", "2. 캘린더 선택"))
        root.addWidget(
            plain_label(
                t(
                    "provider_ui.selection_help",
                    "가져올 캘린더를 체크하세요. 읽기 전용 캘린더도 가져올 수 있습니다.",
                )
            )
        )
        self.refresh_list = QPushButton(t("caldav.refresh", "목록 새로고침"))
        self.refresh_list.clicked.connect(lambda: controller.start("refresh"))
        root.addWidget(self.refresh_list)
        self.calendars = QListWidget()
        self.calendars.setObjectName("SyncCalendarSelection")
        self.calendars.setAccessibleName(t("outlook.calendar_selection", "동기화할 캘린더 선택"))
        self.calendars.setMinimumHeight(140)
        self.calendars.itemChanged.connect(self._update_actions)
        root.addWidget(self.calendars, 1)
        self.selection_info = plain_label()
        root.addWidget(self.selection_info)
        self.enable = QCheckBox(t("outlook.auto_sync", "5분마다 자동 동기화"))
        self.enable.setChecked(self.settings.value("outlook_enabled", False, type=bool))
        self.enable.toggled.connect(self._enable)
        root.addWidget(self.enable)
        self.save = QPushButton(t("outlook.save_calendars", "선택 캘린더 저장"))
        self.save.setObjectName("ghost_btn")
        self.save.clicked.connect(lambda: self._save())
        root.addWidget(self.save)
        self.sync = QPushButton(t("outlook.sync_now", "지금 동기화"))
        self.sync.setObjectName("primary_btn")
        self.sync.clicked.connect(self._save_and_sync)
        root.addWidget(self.sync)
        note = plain_label(
            t(
                "outlook.scope",
                "조회 범위: 지난 120일 ~ 앞으로 400일. 반복 일정은 개별 회차로 표시합니다.\n원격에서 삭제된 일정은 로컬에 보존하고 문제 목록에 표시합니다.\n반복 규칙 편집·서비스 간 이동·초대 응답은 이번 단계에서 지원하지 않습니다.",
            )
        )
        root.addWidget(note)
        problem_tab = QWidget()
        root = QVBoxLayout(problem_tab)
        self.tabs.addTab(scroll_page(problem_tab), t("caldav.problems", "3. 확인할 문제"))
        self.issues = QListWidget()
        self.issues.setMinimumHeight(100)
        root.addWidget(self.issues, 1)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(90)
        self.preview.setMaximumHeight(160)
        self.preview.setPlaceholderText(
            t("sync_ui.compare_hint", "충돌을 선택하면 내 변경과 서비스 내용을 비교할 수 있습니다.")
        )
        root.addWidget(self.preview)
        self.issues.currentItemChanged.connect(self._preview)
        choices = QVBoxLayout()
        self.local = QPushButton(t("outlook.keep_local", "선택 충돌: 내 변경 유지"))
        self.remote = QPushButton(t("outlook.keep_remote", "선택 충돌: Outlook 내용 적용"))
        self.local.clicked.connect(lambda: self._resolve("local"))
        self.remote.clicked.connect(lambda: self._resolve("remote"))
        choices.addWidget(self.local)
        choices.addWidget(self.remote)
        root.addLayout(choices)
        queue_actions = QVBoxLayout()
        self.retry_delete = QPushButton(t("outlook.retry_delete", "선택 삭제 다시 시도"))
        self.cancel_delete = QPushButton(
            t("outlook.cancel_delete", "선택 삭제 취소 · Outlook 일정 유지")
        )
        self.retry_delete.clicked.connect(lambda: self._queue_action("retry"))
        self.cancel_delete.clicked.connect(lambda: self._queue_action("cancel"))
        queue_actions.addWidget(self.retry_delete)
        queue_actions.addWidget(self.cancel_delete)
        root.addLayout(queue_actions)
        footer, close, _ = build_dialog_footer(
            ok_label=t("outlook.close", "닫기"), cancel_label=None
        )
        close.clicked.connect(self.accept)
        close.setAutoDefault(False)
        close.setDefault(False)
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
            button.setDefault(False)
        outer.addLayout(footer)
        self._countdown = QTimer(self)
        self._countdown.setInterval(1000)
        self._countdown.timeout.connect(self._update_actions)
        self._countdown.start()
        controller.changed.connect(self._refresh)
        self._refresh()

    def _update_actions(self, *_):
        busy = self.controller.busy
        connected = bool(self.settings.value("outlook_account_id", "", type=str))
        selected = sum(
            self.calendars.item(i).checkState() == Qt.CheckState.Checked
            for i in range(self.calendars.count())
        )
        saved = len(getattr(self.calendars, "_provider_saved", set()))
        remaining = getattr(self.controller, "retry_remaining_seconds", 0)
        error = self.settings.value("outlook_last_error", "", type=str)
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
        self.refresh_list.setEnabled(
            connected and not busy and not remaining and not requires_account_reconnection(error)
        )
        self.enable.setEnabled(connected and not busy and saved > 0)
        dirty = selected != saved or any(
            (self.calendars.item(i).checkState() == Qt.CheckState.Checked)
            != (
                self.calendars.item(i).data(Qt.ItemDataRole.UserRole)["id"]
                in getattr(self.calendars, "_provider_saved", set())
            )
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
        self._recovery = sync_recovery_action("outlook", state)
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
                self.client_id.setFocus()

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

    def _connection(self):
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _login(self):
        if self.controller.busy:
            return
        try:
            client_id = str(uuid.UUID(self.client_id.text().strip()))
        except ValueError:
            self.controller.status = "client_id_required"
            self._refresh()
            self.client_id.setFocus()
            self.client_id.selectAll()
            return
        previous = self.settings.value("outlook_client_id", "", type=str)
        if (
            previous
            and previous != client_id
            and self.settings.value("outlook_account_id", "", type=str)
        ):
            self.controller.status = "disconnect_first"
            self._refresh()
            return
        self.settings.setValue("outlook_client_id", client_id)
        self.controller.start("login")

    @guard_sync_database
    def _populate(self):
        account = self.settings.value("outlook_account_id", "", type=str)
        if not account:
            update_calendar_items(self.calendars, account, [], [])
            return
        conn = self._connection()
        try:
            repo = CalendarSyncRepository(conn)
            saved = repo.calendars(account)
            available = self.controller.available or [
                {
                    "id": row["remote_id"],
                    "name": conn.execute(
                        "SELECT name FROM calendar WHERE id=?", (row["local_id"],)
                    ).fetchone()[0],
                    "canEdit": row["can_edit"],
                }
                for row in saved
            ]
            choices = []
            for calendar in available:
                own = next((row for row in saved if row["remote_id"] == calendar["id"]), None)
                name = own["display_name"] if own else calendar["name"]
                if not calendar.get("canEdit"):
                    name += " · " + t("outlook.read_only", "읽기 전용")
                choices.append((name, calendar))
            update_calendar_items(self.calendars, account, choices, saved)
        finally:
            conn.close()

    @guard_sync_database
    def _save(self):
        if self.controller.busy:
            return
        account = self.settings.value("outlook_account_id", "", type=str)
        if not account:
            return
        conn = self._connection()
        try:
            repo = CalendarSyncRepository(conn)
            repo.save_selection(
                account,
                [
                    self.calendars.item(index).data(Qt.ItemDataRole.UserRole)
                    for index in range(self.calendars.count())
                    if self.calendars.item(index).checkState() == Qt.CheckState.Checked
                ],
            )
        finally:
            conn.close()
        self.app.schedule_panel_refresh(left=True, center=True, right=True)
        if not any(
            self.calendars.item(i).checkState() == Qt.CheckState.Checked
            for i in range(self.calendars.count())
        ):
            self.settings.setValue("outlook_enabled", False)
            self.enable.blockSignals(True)
            self.enable.setChecked(False)
            self.enable.blockSignals(False)
        self.controller.status = "selection_saved"
        self._available_key = None
        self._refresh()
        return True

    def _enable(self, enabled):
        self.settings.setValue("outlook_enabled", enabled)
        self._update_actions()

    @guard_sync_database
    def _disconnect(self):
        if self.controller.busy:
            return
        account = self.settings.value("outlook_account_id", "", type=str)
        conn = self._connection()
        try:
            CalendarSyncRepository(conn).deactivate(account)
        finally:
            conn.close()
        self.settings.setValue("outlook_enabled", False)
        self.enable.setChecked(False)
        self.controller.start("disconnect")

    def _preview(self, *_):
        item = self.issues.currentItem()
        task_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        detail = item.data(int(Qt.ItemDataRole.UserRole) + 2) if item else None
        conflict = isinstance(task_id, int) and bool(detail and detail.get("kind") == "conflict")
        recovery = bool(detail and detail.get("recovery_issue"))
        busy = self.controller.busy
        self.local.setEnabled(conflict and not busy)
        self.remote.setEnabled(conflict and not busy)
        self.retry_delete.setEnabled(
            isinstance(task_id, str)
            and not busy
            and not getattr(self.controller, "retry_remaining_seconds", 0)
        )
        self.cancel_delete.setEnabled(isinstance(task_id, str) and not busy and not recovery)
        self.retry_delete.setText(
            t("sync_recovery.recheck", "다시 확인")
            if recovery
            else t("outlook.retry_delete", "선택 삭제 다시 시도")
        )
        preview = (
            conflict_text(
                detail, GraphClient, self.settings.value("gcal_timezone", "Asia/Seoul", type=str)
            )
            if conflict
            else recovery_issue_text(detail)
            if recovery
            else ""
        )
        if self.preview.toPlainText() != preview:
            self.preview.setPlainText(preview)

    @guard_sync_database
    def _resolve(self, choice):
        if self.controller.busy:
            return
        item = self.issues.currentItem()
        if not item:
            return
        task_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(task_id, int):
            return
        conn = self._connection()
        resolved = False
        try:
            # Conversion methods have no network/authentication dependency.
            if CalendarSyncRepository(conn).resolve(
                task_id,
                choice,
                self.settings.value("gcal_timezone", "Asia/Seoul", type=str),
                GraphClient,
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
    def _queue_action(self, choice):
        if self.controller.busy:
            return
        item = self.issues.currentItem()
        if not item:
            return
        event_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(event_id, str) or choice not in {"retry", "cancel"}:
            return
        detail = item.data(int(Qt.ItemDataRole.UserRole) + 2)
        if detail and detail.get("recovery_issue"):
            if choice == "retry":
                self.controller.sync(force=True)
            return
        calendar_id = item.data(int(Qt.ItemDataRole.UserRole) + 1)
        conn = self._connection()
        try:
            with conn:
                if choice == "retry":
                    changed = conn.execute(
                        "UPDATE calendar_sync_delete_queue SET attempts=0,error=NULL WHERE event_id=? AND calendar_id=? AND calendar_id IN (SELECT local_id FROM calendar_sync_calendar WHERE account_id=?)",
                        (
                            event_id,
                            calendar_id,
                            self.settings.value("outlook_account_id", "", type=str),
                        ),
                    ).rowcount
                elif choice == "cancel":
                    conn.execute(
                        "DELETE FROM calendar_sync_delete_queue WHERE event_id=? AND calendar_id=? AND calendar_id IN (SELECT local_id FROM calendar_sync_calendar WHERE account_id=?)",
                        (
                            event_id,
                            calendar_id,
                            self.settings.value("outlook_account_id", "", type=str),
                        ),
                    )
        finally:
            conn.close()
        self._available_key = None
        self._refresh()
        if choice == "retry" and changed:
            self.controller.sync(force=True)

    @staticmethod
    def _issue_label(kind):
        return {
            "conflict": t("outlook.issue_conflict", "양쪽에서 수정됨 · 유지할 내용을 선택하세요"),
            "remote_deleted": t("outlook.issue_deleted", "Outlook에서 삭제됨 · 로컬 일정 보존"),
            "delete_conflict": t(
                "outlook.issue_delete_conflict", "Outlook 내용이 바뀌어 삭제를 보류함"
            ),
            "calendar_move_not_supported": t(
                "outlook.issue_move", "캘린더 이동 미지원 · 원래 캘린더로 되돌려 주세요"
            ),
            "calendar_read_only": t("outlook.issue_read_only", "캘린더 쓰기 권한이 없음"),
            "recurrence_not_supported": t("outlook.issue_recurrence", "반복 규칙 편집 미지원"),
            "online_meeting_body_not_supported": t(
                "outlook.issue_meeting", "온라인 회의 본문은 Outlook에서 편집해 주세요"
            ),
        }.get(kind, sync_error_message(kind))

    @guard_sync_database
    def _refresh(self):
        busy = self.controller.busy
        if not busy and self._cancel_requested:
            self._cancel_requested = False
            if self.controller.status in {"login", "sync", "refresh", "disconnect"}:
                self.controller.status = "cancelled"
        account = self.settings.value("outlook_account_name", "", type=str)
        self.account.setText(
            account or t("outlook.not_connected", "연결된 Microsoft 계정이 없습니다.")
        )
        for button in (
            self.login,
            self.disconnect,
            self.save,
            self.sync,
            self.local,
            self.remote,
            self.client_id,
            self.enable,
            self.calendars,
        ):
            button.setEnabled(not busy)
        connected = bool(self.settings.value("outlook_account_id", "", type=str))
        for button in (
            self.disconnect,
            self.save,
            self.sync,
            self.local,
            self.remote,
            self.enable,
            self.refresh_list,
        ):
            button.setEnabled(connected and not busy)
        self.retry_delete.setEnabled(connected and not busy)
        self.cancel_delete.setEnabled(connected and not busy)
        code = self.controller.status
        signature = calendar_snapshot_key(
            self.settings.value("outlook_account_id", "", type=str), self.controller.available
        )
        refresh_data = not busy and (
            signature != self._available_key or code != self._last_status or self._was_busy
        )
        self._was_busy = busy
        if refresh_data and self._populate() is False:
            return
        if code == "connected" and self._last_status != "connected" and not busy:
            self.tabs.setCurrentIndex(1)
            self.technical_toggle.setChecked(False)
        if not busy:
            self._last_status = code
        messages = {
            "idle": t("provider_ui.connected", "계정이 연결되어 있습니다.")
            if connected
            else t("outlook.status_idle", "로그인 후 캘린더를 선택해 저장하세요."),
            "login": t(
                "outlook.status_login",
                "브라우저에서 Microsoft 로그인을 완료하세요. 최대 2분 대기합니다.",
            ),
            "sync": t("outlook.status_sync", "Outlook 일정을 동기화하고 있습니다..."),
            "completed": t("outlook.status_completed", "동기화 완료"),
            "completed_with_issues": sync_error_message("completed_with_issues"),
            "connected": t("provider_ui.connected", "계정이 연결되어 있습니다."),
            "disconnected": t(
                "outlook.status_disconnected", "연결 해제됨. 기존 일정은 보존됩니다."
            ),
            "selection_saved": t("outlook.status_saved", "캘린더 선택을 저장했습니다."),
            "refresh": t("caldav.refreshing", "캘린더 목록을 새로고침하고 있습니다..."),
            "refreshed": t(
                "caldav.refreshed", "목록을 새로고침했습니다. 선택을 확인하고 저장하세요."
            ),
            "client_id_required": t(
                "outlook.status_client", "유효한 애플리케이션(클라이언트) ID를 입력하세요."
            ),
            "login_required": t(
                "outlook.status_auth",
                "Microsoft 로그인이 필요합니다. 권한 동의나 조직 정책도 확인하세요.",
            ),
            "disconnect_first": t(
                "outlook.status_disconnect_first",
                "클라이언트 ID를 바꾸기 전에 기존 연결을 해제하세요.",
            ),
            "dependency_unavailable": t(
                "provider_ui.module_missing",
                "로그인 기능을 사용할 수 없습니다. 앱을 업데이트한 뒤 다시 연결하세요.",
            ),
            "cancelled": t(
                "provider_ui.cancelled", "작업을 중단했습니다. 기존 일정과 연결은 유지됩니다."
            ),
            "network_unavailable": t(
                "outlook.status_network", "네트워크 연결을 확인하고 다시 시도하세요."
            ),
            "calendar_access_lost": t(
                "outlook.status_access",
                "캘린더 접근 권한을 잃어 동기화를 중단했습니다. 로그인과 캘린더 선택을 다시 확인하세요.",
            ),
        }
        text = messages.get(
            code,
            sync_error_message(code),
        )
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
        self.status.setText(text)
        last = self.settings.value("outlook_last_success", "", type=str)
        if last:
            self.status.setText(
                text + "\n" + t("caldav.last_success", "마지막 성공: {time}").format(time=last)
            )
        entries = []
        if connected and refresh_data:
            conn = self._connection()
            try:
                repo = CalendarSyncRepository(conn)
                for issue in repo.issues(self.settings.value("outlook_account_id", "", type=str)):
                    label = t("outlook.issue", "일정 #{id}: {kind}").format(
                        id=issue["task_id"], kind=self._issue_label(issue["kind"])
                    )
                    entries.append((label, {0: issue["task_id"], 2: issue}))
                account_id = self.settings.value("outlook_account_id", "", type=str)
                for row in conn.execute(
                    "SELECT q.* FROM calendar_sync_delete_queue q JOIN calendar_sync_calendar c ON c.local_id=q.calendar_id WHERE c.account_id=?",
                    (account_id,),
                ):
                    label = t("outlook.delete_issue", "삭제 대기 · {attempts}/5회 · {kind}").format(
                        attempts=row["attempts"],
                        kind=self._issue_label(row["error"] or t("outlook.pending", "대기 중")),
                    )
                    entries.append((label, {0: row["event_id"], 1: row["calendar_id"]}))
                for row in calendar_recovery_issues(repo, self.settings, "outlook_", account_id):
                    entries.append(
                        (
                            recovery_issue_label(row),
                            {
                                0: row.get("transaction_id") or row["calendar_id"],
                                1: row["calendar_id"],
                                2: row,
                            },
                        )
                    )
            finally:
                conn.close()
        if refresh_data:
            update_issue_items(
                self.issues, self.settings.value("outlook_account_id", "", type=str), entries
            )
            self._available_key = signature
        self._update_actions()
