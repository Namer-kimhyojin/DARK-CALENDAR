# -*- coding: utf-8 -*-
"""One entry point for provider status, capabilities and recovery."""

from zoneinfo import ZoneInfo, available_timezones

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.main_window.calendar_sync_coordinator import (
    provider_name,
    provider_status,
)

from .calendar_manager_page import CalendarManagerPage
from .dialog_styles import apply_common_dialog_style, build_dialog_footer, get_dialog_theme_tokens
from .sync_feedback import sync_error_message


class CalendarSyncHub(QDialog):
    def __init__(self, app, section="services"):
        super().__init__(app)
        self.app = app
        self.coordinator = getattr(app, "_calendar_sync_coordinator", None)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(t("sync_ui.hub_title", "캘린더 · 계정 및 동기화"))
        tokens = get_dialog_theme_tokens()
        apply_common_dialog_style(
            self,
            minimum_width=620,
            extra_stylesheet=(
                "QScrollArea#SyncServices, QWidget#SyncServicesBody, "
                "QWidget#SyncServicesViewport { background: transparent; border: none; }"
                "QFrame#SyncServiceCard { background: "
                + tokens["surface_alt"]
                + "; border: 1px solid "
                + tokens["border"]
                + "; border-radius: 10px; }"
                + 'QLabel[role="syncServiceTitle"] { font-weight: 700; color: '
                + tokens["text_primary"]
                + "; }"
            ),
        )
        self.resize(820, 740)
        root = QVBoxLayout(self)
        intro = QLabel(
            t(
                "sync_ui.hub_intro",
                "서비스를 연결하고 가져올 캘린더를 선택하세요. 계정별로 동기화하며 서로 다른 서비스 사이에서 일정을 자동 복사하지 않습니다.",
            )
        )
        intro.setWordWrap(True)
        root.addWidget(intro)
        action_row = QHBoxLayout()
        self.sync_all = QPushButton(t("sync_unified.sync_all", "연결된 모든 캘린더 동기화"))
        self.sync_all.setObjectName("primary_btn")
        self.sync_all.clicked.connect(lambda: self._run_sync())
        action_row.addWidget(self.sync_all)
        for enabled, label in (
            (True, t("sync_unified.auto_resume", "자동 동기화 모두 켜기")),
            (False, t("sync_unified.auto_pause", "자동 동기화 모두 끄기")),
        ):
            button = QPushButton(label)
            button.setObjectName("ghost_btn")
            button.clicked.connect(lambda checked=False, value=enabled: self._set_all_auto(value))
            action_row.addWidget(button)
        root.addLayout(action_row)
        timezone_row = QHBoxLayout()
        timezone_row.addWidget(QLabel(t("sync_ui.timezone", "공통 시간대")))
        self.timezone = QComboBox()
        self.timezone.setEditable(True)
        self.timezone.addItems(sorted(available_timezones()))
        self.timezone.setCurrentText(app.settings.value("gcal_timezone", "Asia/Seoul", type=str))
        self.timezone.setAccessibleName(t("sync_ui.timezone", "공통 시간대"))
        timezone_row.addWidget(self.timezone, 1)
        self.save_timezone = QPushButton(t("sync_ui.save_timezone", "시간대 저장"))
        self.save_timezone.setObjectName("ghost_btn")
        self.save_timezone.clicked.connect(self._save_timezone)
        timezone_row.addWidget(self.save_timezone)
        self.tabs = QTabWidget()
        services = QWidget()
        services_layout = QVBoxLayout(services)
        services_layout.addLayout(timezone_row)
        self.timezone_feedback = QLabel(
            t("sync_ui.timezone_hint", "시간대 변경은 다음 동기화부터 반영됩니다.")
        )
        self.timezone_feedback.setWordWrap(True)
        services_layout.addWidget(self.timezone_feedback)
        scroll = QScrollArea()
        scroll.setObjectName("SyncServices")
        scroll.viewport().setObjectName("SyncServicesViewport")
        scroll.viewport().setAutoFillBackground(False)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("SyncServicesBody")
        cards = QVBoxLayout(body)
        cards.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(body)
        services_layout.addWidget(scroll, 1)
        self.labels = {}
        self.auto_buttons, self.sync_buttons = {}, {}
        specs = [
            (
                "google",
                "Google Calendar",
                t("sync_ui.google_capability", "일정 양방향 · 공유 캘린더는 권한에 따름"),
            ),
            (
                "outlook",
                "Outlook · Microsoft 365",
                t("sync_ui.outlook_capability", "일정 양방향 · 최초 Microsoft 앱 등록 필요"),
            ),
            (
                "icloud",
                "iCloud",
                t("sync_ui.icloud_capability", "개인 일정 양방향 · 앱 전용 암호 사용"),
            ),
            (
                "naver",
                t("caldav.naver", "네이버"),
                t("sync_ui.naver_capability", "읽기 전용 · 서비스 정책에 따라 연결 제한 가능"),
            ),
            (
                "ics",
                t("sync_unified.ics", "ICS 구독"),
                t("sync_unified.ics_capability", "공유 구독 주소 · 읽기 전용"),
            ),
        ]
        for key, name, capability in specs:
            card = QFrame()
            card.setObjectName("SyncServiceCard")
            layout = QHBoxLayout(card)
            text = QVBoxLayout()
            title = QLabel(name)
            title.setProperty("role", "syncServiceTitle")
            font = title.font()
            font.setBold(True)
            title.setFont(font)
            text.addWidget(title)
            hint = QLabel(capability)
            hint.setWordWrap(True)
            text.addWidget(hint)
            status = QLabel()
            status.setTextFormat(Qt.TextFormat.PlainText)
            status.setWordWrap(True)
            text.addWidget(status)
            self.labels[key] = status
            auto = QCheckBox(t("sync_unified.auto", "자동 동기화"))
            auto.setAccessibleName(name + " " + t("sync_unified.auto", "자동 동기화"))
            auto.toggled.connect(
                lambda enabled, provider=key: (
                    self.coordinator.set_auto(provider, enabled) if self.coordinator else None
                )
            )
            text.addWidget(auto)
            self.auto_buttons[key] = auto
            layout.addLayout(text, 1)
            actions = QVBoxLayout()
            button = QPushButton(t("sync_ui.configure", "연결 · 설정"))
            button.setObjectName("ghost_btn")
            button.setAccessibleName(name + " " + t("sync_ui.configure", "연결 · 설정"))
            button.clicked.connect(lambda checked=False, provider=key: self._open(provider))
            actions.addWidget(button)
            sync = QPushButton(t("outlook.sync_now", "지금 동기화"))
            sync.setObjectName("ghost_btn")
            sync.clicked.connect(lambda checked=False, provider=key: self._run_sync(provider))
            actions.addWidget(sync)
            self.sync_buttons[key] = sync
            issues = QPushButton(t("sync_unified.review_issues", "문제 확인"))
            issues.setObjectName("ghost_btn")
            issues.clicked.connect(
                lambda checked=False, provider=key: self._open(provider, "issues")
            )
            actions.addWidget(issues)
            layout.addLayout(actions)
            cards.addWidget(card)
        self.tabs.addTab(services, t("sync_unified.services", "서비스 · 동기화"))
        self.calendar_manager = CalendarManagerPage(app, self.coordinator, self._open)
        self.tabs.addTab(self.calendar_manager, t("sync_unified.calendars", "전체 캘린더"))
        problems = QWidget()
        problems_layout = QVBoxLayout(problems)
        self.issue_summary = QLabel()
        self.issue_summary.setWordWrap(True)
        problems_layout.addWidget(self.issue_summary)
        self.issue_list = QListWidget()
        self.issue_list.itemDoubleClicked.connect(
            lambda item: self._open(item.data(Qt.ItemDataRole.UserRole), "issues")
        )
        problems_layout.addWidget(self.issue_list, 1)
        self.resolve_selected = QPushButton(
            t("sync_unified.open_issue", "선택한 서비스에서 확인·해결")
        )
        self.resolve_selected.setObjectName("primary_btn")
        self.resolve_selected.clicked.connect(self._open_selected_issue)
        problems_layout.addWidget(self.resolve_selected)
        self.issue_list.currentItemChanged.connect(
            lambda: self.resolve_selected.setEnabled(self.issue_list.currentItem() is not None)
        )
        self.tabs.addTab(problems, t("sync_unified.issues", "전체 동기화 문제"))
        self.tabs.setCurrentIndex({"services": 0, "calendars": 1, "issues": 2}.get(section, 0))
        self.tabs.currentChanged.connect(lambda: self._refresh())
        root.addWidget(self.tabs, 1)
        note = QLabel(
            t(
                "sync_ui.hub_note",
                "연결 해제와 캘린더 선택 해제는 서비스의 원본 일정을 삭제하지 않습니다. 충돌이나 실패는 각 서비스 설정에서 확인하고 해결하세요.",
            )
        )
        note.setWordWrap(True)
        root.addWidget(note)
        footer, close, _ = build_dialog_footer(
            ok_label=t("outlook.close", "닫기"), cancel_label=None
        )
        close.clicked.connect(self.accept)
        root.addLayout(footer)
        for controller in [
            getattr(app, "_outlook_sync_controller", None),
            *getattr(app, "_caldav_sync_controllers", {}).values(),
        ]:
            if controller:
                controller.changed.connect(self._refresh)
        if self.coordinator:
            self.coordinator.changed.connect(self._refresh)
        self._refresh()

    def _save_timezone(self):
        workers = [getattr(self.app, "_sync_worker", None), getattr(self.app, "_auth_worker", None)]
        controllers = [
            getattr(self.app, "_outlook_sync_controller", None),
            *getattr(self.app, "_caldav_sync_controllers", {}).values(),
        ]
        if (
            (self.coordinator and any(s["busy"] for s in self.coordinator.states.values()))
            or any(worker and worker.isRunning() for worker in workers)
            or any(controller and controller.busy for controller in controllers)
        ):
            self.timezone_feedback.setText(
                t("sync_ui.wait_timezone", "진행 중인 동기화가 끝난 뒤 시간대를 변경하세요.")
            )
            return
        zone = self.timezone.currentText().strip()
        try:
            ZoneInfo(zone)
        except (KeyError, ValueError):
            self.timezone_feedback.setText(
                t("sync_ui.invalid_timezone", "올바른 시간대를 선택하세요. 예: Asia/Seoul")
            )
            return
        self.app.settings.setValue("gcal_timezone", zone)
        google = getattr(self.app, "gcal_sync", None)
        if google:
            google.time_zone = zone
        self.timezone_feedback.setText(
            t("sync_ui.timezone_saved", "시간대를 저장했습니다. 다음 동기화부터 반영됩니다.")
        )

    def _open(self, provider, section="services"):
        if provider == "google":
            if section == "issues":
                self.app.open_gcal_sync_issues_dialog()
            else:
                self.app.open_gcal_settings_dialog(
                    initial_tab="calendar" if section == "calendars" else None, from_sync_hub=True
                )
        elif provider == "outlook":
            from calendar_app.presentation.main_window.outlook_sync_controller import (
                open_outlook_settings,
            )

            open_outlook_settings(self.app, section=section, from_sync_hub=True)
        elif provider == "ics":
            self.tabs.setCurrentIndex(1)
            failed = (
                self.app.settings.value("sync_ics_failed_ids", []) if section == "issues" else []
            )
            candidates = []
            for index in range(self.calendar_manager.calendars.count()):
                item = self.calendar_manager.calendars.item(index)
                calendar = item.data(Qt.ItemDataRole.UserRole)
                if calendar.get("type") == "ics":
                    candidates.append(item)
                    if calendar["id"] in failed:
                        self.calendar_manager.calendars.setCurrentItem(item)
                        return
            if candidates:
                self.calendar_manager.calendars.setCurrentItem(candidates[0])
            return
        else:
            from calendar_app.presentation.main_window.caldav_sync_controller import (
                open_caldav_settings,
            )

            open_caldav_settings(self.app, provider, section=section, from_sync_hub=True)
        if self.coordinator:
            self.coordinator.refresh()
        self._refresh()

    def _run_sync(self, provider=None):
        if self.coordinator:
            self.coordinator.sync(provider)
            self._refresh()

    def _set_all_auto(self, enabled):
        if self.coordinator:
            for provider, state in self.coordinator.states.items():
                if state["connected"]:
                    self.coordinator.set_auto(provider, enabled)

    def _open_selected_issue(self):
        item = self.issue_list.currentItem()
        if item:
            self._open(item.data(Qt.ItemDataRole.UserRole), "issues")

    def _refresh(self):
        if self.coordinator:
            self._refresh_unified()
            return
        settings = self.app.settings
        google = getattr(self.app, "gcal_sync", None)
        authenticated = bool(google and getattr(google, "is_authenticated", False))
        waiting = getattr(self.app, "_gcal_waiting_for_auth", False)
        self.labels["google"].setText(
            t("sync_ui.connected", "연결됨")
            if authenticated
            else t("sync_ui.reconnect", "재연결 필요")
            if waiting
            else t("sync_ui.not_connected", "연결되지 않음")
        )
        controllers = {
            "outlook": getattr(self.app, "_outlook_sync_controller", None),
            **getattr(self.app, "_caldav_sync_controllers", {}),
        }
        for key in ("outlook", "icloud", "naver"):
            prefix = "outlook_" if key == "outlook" else "caldav_" + key + "_"
            account = settings.value(prefix + "account_id", "", type=str)
            controller = controllers.get(key)
            text = (
                t("sync_ui.connected", "연결됨")
                if account
                else t("sync_ui.not_connected", "연결되지 않음")
            )
            if controller and controller.busy:
                text = t("sync_ui.working", "작업 중...")
            elif controller and controller.status not in {
                "idle",
                "connected",
                "disconnected",
                "completed",
                "selection_saved",
                "refreshed",
            }:
                text = sync_error_message(controller.status)
            if account:
                text += " · " + (
                    t("sync_ui.auto_on", "자동 동기화 켜짐")
                    if settings.value(prefix + "enabled", False, type=bool)
                    else t("sync_ui.auto_off", "자동 동기화 꺼짐")
                )
                last = settings.value(prefix + "last_success", "", type=str)
                if last:
                    text += "\n" + t("caldav.last_success", "마지막 성공: {time}").format(time=last)
            self.labels[key].setText(text)
        self.labels["ics"].setText(t("sync_unified.ics_capability", "공유 구독 주소 · 읽기 전용"))
        self.sync_all.setEnabled(False)
        for button in self.sync_buttons.values():
            button.setEnabled(False)

    def _refresh_unified(self):
        states = self.coordinator.states
        self.sync_all.setEnabled(any(s["can_sync"] and not s["busy"] for s in states.values()))
        selected = self.issue_list.currentItem()
        selected_provider = selected.data(Qt.ItemDataRole.UserRole) if selected else None
        self.issue_list.clear()
        for provider, state in states.items():
            text = provider_status(state)
            if state["last_success"]:
                text += "\n" + t("caldav.last_success", "마지막 성공: {time}").format(
                    time=state["last_success"]
                )
            self.labels[provider].setText(text)
            auto = self.auto_buttons[provider]
            auto.blockSignals(True)
            auto.setChecked(state["auto"])
            auto.blockSignals(False)
            auto.setEnabled(state["connected"] and not state["busy"])
            self.sync_buttons[provider].setEnabled(state["can_sync"] and not state["busy"])
            if state["issues"] or state.get("error"):
                item = QListWidgetItem(provider_name(provider) + " · " + provider_status(state))
                item.setData(Qt.ItemDataRole.UserRole, provider)
                self.issue_list.addItem(item)
                if selected_provider == provider:
                    self.issue_list.setCurrentItem(item)
        self.issue_summary.setText(
            t("sync_unified.no_issues", "현재 확인할 동기화 문제가 없습니다.")
            if not self.issue_list.count()
            else t(
                "sync_unified.issues_hint",
                "서비스를 선택해 충돌 내용·실패 원인을 확인하고 해결하세요. 다른 서비스의 동기화는 계속 진행됩니다.",
            )
        )
        self.resolve_selected.setEnabled(self.issue_list.currentItem() is not None)
        self.calendar_manager.reload()


def open_calendar_sync_hub(app, section="services"):
    CalendarSyncHub(app, section).exec()
