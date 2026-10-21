# -*- coding: utf-8 -*-
"""A calendar-first workspace for display, account connections and subscriptions."""

from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QBoxLayout,
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
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from calendar_app.application.calendar_provider_catalog import CALDAV_SERVICES
from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.ics.subscriptions import subscription_errors
from calendar_app.presentation.main_window.calendar_sync_coordinator import (
    provider_name,
    provider_status,
)
from calendar_app.shared.icon_map import ICON, icon

from .calendar_manager_page import CalendarManagerPage
from .calendar_sync_style import build_sync_workspace_styles
from .dialog_styles import apply_common_dialog_style, build_dialog_footer, get_dialog_theme_tokens
from .provider_settings_widgets import plain_tooltip
from .sync_feedback import sync_error_message
from .sync_recovery import sync_recovery_action


class CalendarSyncHub(QDialog):
    def __init__(self, app, section="calendars"):
        super().__init__(app)
        self.app = app
        self.coordinator = getattr(app, "_calendar_sync_coordinator", None)
        self._feedback_providers = ()
        self._feedback_baselines = {}
        self._issue_snapshot = None
        self._retry_tick = QTimer(self)
        self._retry_tick.setInterval(1000)
        self._retry_tick.timeout.connect(self._refresh_retry_wait)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(t("sync_redesign.workspace_title", "캘린더 관리"))
        self.tokens = get_dialog_theme_tokens(settings=app.settings)
        apply_common_dialog_style(
            self,
            minimum_width=620,
            theme_color=app.settings.value("theme_color", "#4da6ff", type=str),
            text_theme=app.settings.value("text_theme", "dark", type=str),
            panel_base_color=app.settings.value("panel_base_color", "#0d1b2e", type=str),
            extra_stylesheet=build_sync_workspace_styles(self.tokens),
        )
        self.resize(1040, 760)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(14)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        title = self._label(t("sync_redesign.workspace_title", "캘린더 관리"), "syncWorkspaceTitle")
        heading.addWidget(title)
        self.summary = self._label("", "syncMuted")
        heading.addWidget(self.summary)
        header.addLayout(heading, 1)
        self.sync_all = QPushButton(t("sync_redesign.sync_now", "지금 동기화"))
        self.sync_all.setObjectName("primary_btn")
        self.sync_all.setIcon(icon(ICON.SYNC, color=self.tokens["accent"]))
        self.sync_all.clicked.connect(lambda: self._run_sync())
        header.addWidget(self.sync_all)
        root.addLayout(header)
        self.sync_feedback = self._label("")
        self.sync_feedback.setObjectName("SyncWorkspaceFeedback")
        self.sync_feedback.hide()
        root.addWidget(self.sync_feedback)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("SyncManagementTabs")
        self.tabs.tabBar().setObjectName("SyncManagementTabBar")
        self.tabs.setAccessibleName(t("sync_redesign.workspace_title", "캘린더 관리"))
        self.section_pages = {}

        services = QWidget()
        services_layout = QVBoxLayout(services)
        services_layout.setContentsMargins(0, 12, 0, 0)
        services_heading = QHBoxLayout()
        services_heading.addWidget(
            self._label(
                t(
                    "sync_redesign.connections_hint",
                    "계정으로 연결하거나 구독 주소로 일정을 가져오세요.",
                ),
                "syncMuted",
            ),
            1,
        )
        services_layout.addLayout(services_heading)
        scroll = self._scroll("SyncServices", "SyncServicesBody", "SyncServicesViewport")
        services_layout.addWidget(scroll, 1)
        cards = QVBoxLayout(scroll.widget())
        cards.setContentsMargins(0, 0, 4, 0)
        cards.setSpacing(12)
        self.labels, self.auto_buttons, self.sync_buttons = {}, {}, {}
        self.connect_buttons, self.service_badges, self.service_cards, self.last_sync_labels = (
            {},
            {},
            {},
            {},
        )
        self.service_action_layouts = {}
        specs = [
            (
                "google",
                "Google Calendar",
                t("sync_redesign.google_hint", "내 Google 일정과 공유 캘린더를 연결합니다."),
            ),
            (
                "ics",
                t("sync_redesign.ics_title", "주소로 캘린더 구독"),
                t(
                    "sync_redesign.ics_hint",
                    "공유 일정·휴일을 가져옵니다. Google 로그인 없이 읽기 전용으로 사용합니다.",
                ),
            ),
            (
                "outlook",
                "Outlook · Microsoft 365",
                t("sync_redesign.outlook_hint", "Microsoft 계정의 일정과 연결합니다."),
            ),
            *[
                (
                    service,
                    provider_name(service),
                    t("sync_redesign.naver_hint", "지원되는 캘린더를 읽기 전용으로 가져옵니다.")
                    if service == "naver"
                    else t(
                        "global_caldav.capability", "개인 일정 양방향 · 반복/초대 일정 읽기 전용"
                    ),
                )
                for service in CALDAV_SERVICES
            ],
        ]
        for provider, name, capability in specs:
            if provider == "outlook":
                self.more_services_header = QFrame()
                self.more_services_header.setObjectName("SyncAvailableServices")
                account_heading = QHBoxLayout(self.more_services_header)
                account_heading.setContentsMargins(16, 12, 16, 12)
                account_description = QVBoxLayout()
                account_description.addWidget(
                    self._label(
                        t("sync_disclosures.additional_accounts", "추가 계정 연결"),
                        "syncSectionTitle",
                    )
                )
                account_description.addWidget(
                    self._label(
                        " · ".join(
                            provider_name(service) for service in ("outlook", *CALDAV_SERVICES)
                        ),
                        "syncMuted",
                    )
                )
                account_heading.addLayout(account_description, 1)
                self.more_services = QPushButton(
                    t("sync_disclosures.show_services", "서비스 목록 펼치기")
                )
                self.more_services.setObjectName("ghost_btn")
                self.more_services.setProperty("role", "syncDisclosure")
                self.more_services.setSizePolicy(
                    QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
                )
                self.more_services.setIcon(icon(ICON.NAV_NEXT, color=self.tokens["accent"]))
                self.more_services.setCheckable(True)
                self.more_services.toggled.connect(self._toggle_services)
                account_heading.addWidget(self.more_services)
                cards.addWidget(self.more_services_header)
            card = self._build_service_card(provider, name, capability)
            cards.addWidget(card)
        self.advanced_toggle = QPushButton(t("sync_disclosures.common_settings", "공통 설정"))
        self.advanced_toggle.setObjectName("ghost_btn")
        self.advanced_toggle.setProperty("role", "syncDisclosure")
        self.advanced_toggle.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.advanced_toggle.setIcon(icon(ICON.SETTINGS, color=self.tokens["accent"]))
        self.advanced_toggle.setToolTip(
            t(
                "sync_disclosures.common_settings_hint",
                "모든 연결에 적용되는 시간대와 자동 동기화 설정입니다.",
            )
        )
        self.advanced_toggle.setAccessibleDescription(self.advanced_toggle.toolTip())
        self.advanced_toggle.setCheckable(True)
        services_heading.addWidget(self.advanced_toggle)
        self.advanced = QFrame()
        self.advanced.setObjectName("SyncCommonSettings")
        self.advanced.setAccessibleName(t("sync_disclosures.common_settings", "공통 설정"))
        advanced_layout = QVBoxLayout(self.advanced)
        advanced_layout.setContentsMargins(16, 14, 16, 14)
        advanced_layout.addWidget(
            self._label(t("sync_disclosures.common_settings", "공통 설정"), "syncSectionTitle")
        )
        advanced_layout.addWidget(self._label(self.advanced_toggle.toolTip(), "syncMuted"))
        timezone_row = QHBoxLayout()
        timezone_row.addWidget(self._label(t("sync_redesign.display_timezone", "일정 표시 시간대")))
        self.timezone = QComboBox()
        self.timezone.setEditable(True)
        self.timezone.addItems(sorted(available_timezones()))
        self.timezone.setCurrentText(app.settings.value("gcal_timezone", "Asia/Seoul", type=str))
        self.timezone.setAccessibleName(t("sync_redesign.display_timezone", "일정 표시 시간대"))
        timezone_row.addWidget(self.timezone, 1)
        self.save_timezone = QPushButton(t("sync_ui.save_timezone", "시간대 저장"))
        self.save_timezone.setObjectName("ghost_btn")
        self.save_timezone.clicked.connect(self._save_timezone)
        timezone_row.addWidget(self.save_timezone)
        advanced_layout.addLayout(timezone_row)
        self.timezone_feedback = self._label(
            t("sync_ui.timezone_hint", "시간대 변경은 다음 동기화부터 반영됩니다."), "syncMuted"
        )
        advanced_layout.addWidget(self.timezone_feedback)
        autos = QHBoxLayout()
        for enabled, label in (
            (True, t("sync_unified.auto_resume", "자동 동기화 모두 켜기")),
            (False, t("sync_unified.auto_pause", "자동 동기화 모두 끄기")),
        ):
            button = QPushButton(label)
            button.setObjectName("ghost_btn")
            button.clicked.connect(lambda checked=False, value=enabled: self._set_all_auto(value))
            autos.addWidget(button)
        advanced_layout.addLayout(autos)
        cards.insertWidget(0, self.advanced)
        self.advanced.hide()
        self.advanced_toggle.toggled.connect(self._toggle_common_settings)
        cards.addStretch()
        self.tabs.addTab(services, t("sync_redesign.connections_tab", "연결 및 구독"))
        self.section_pages["services"] = services

        self.calendar_manager = CalendarManagerPage(
            app, self.coordinator, self._open, show_add_actions=False
        )
        self.calendar_manager.setObjectName("SyncCalendarsBody")
        calendar_scroll = self._scroll(
            "SyncCalendars", "SyncCalendarsBody", "SyncCalendarsViewport", self.calendar_manager
        )
        self.tabs.addTab(calendar_scroll, t("sync_redesign.calendars_tab", "내 캘린더"))
        self.section_pages["calendars"] = calendar_scroll
        self.local_manager = CalendarManagerPage(app, self.coordinator, self._open, scope="local")
        self.ics_manager = CalendarManagerPage(app, self.coordinator, self._open, scope="ics")
        for section_key, page, label in (
            ("local", self.local_manager, t("calendar_management_tabs.local_tab", "로컬 캘린더")),
            ("ics", self.ics_manager, t("calendar_management_tabs.ics_tab", "ICS 구독")),
        ):
            page.setObjectName("Sync" + section_key.title() + "Body")
            page_scroll = self._scroll(
                "Sync" + section_key.title(),
                page.objectName(),
                "Sync" + section_key.title() + "Viewport",
                page,
            )
            self.tabs.addTab(page_scroll, label)
            self.section_pages[section_key] = page_scroll

        problems = QWidget()
        problems_layout = QVBoxLayout(problems)
        problems_layout.setContentsMargins(0, 12, 0, 0)
        self.issue_summary = self._label("", "syncSectionTitle")
        problems_layout.addWidget(self.issue_summary)
        self.issues_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.issue_list = QListWidget()
        self.issue_list.setObjectName("SyncIssueList")
        self.issue_list.setMinimumHeight(120)
        self.issue_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.issue_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.issue_list.setAccessibleName(t("sync_redesign.issues_tab", "문제 해결"))
        self.issue_list.itemDoubleClicked.connect(lambda _: self._open_selected_issue())
        self.issue_list.currentItemChanged.connect(self._issue_selection)
        self.issues_layout.addWidget(self.issue_list, 1)
        self.issue_panel = QFrame()
        self.issue_panel.setObjectName("SyncIssueDetails")
        issue_layout = QVBoxLayout(self.issue_panel)
        issue_layout.setContentsMargins(16, 16, 16, 16)
        self.issue_detail = self._label("", "syncStatus")
        issue_layout.addWidget(self.issue_detail)
        issue_layout.addStretch()
        self.retry_selected = QPushButton(t("sync_redesign.retry", "다시 동기화"))
        self.retry_selected.setObjectName("primary_btn")
        self.retry_selected.clicked.connect(self._retry_selected_issue)
        issue_layout.addWidget(self.retry_selected)
        self.resolve_selected = QPushButton(
            t("sync_redesign.fix_settings", "해결 방법 · 설정 열기")
        )
        self.resolve_selected.setObjectName("ghost_btn")
        self.resolve_selected.clicked.connect(self._open_selected_issue)
        issue_layout.addWidget(self.resolve_selected)
        self.issue_scroll = self._scroll(
            "SyncIssues", "SyncIssueDetails", "SyncIssuesViewport", self.issue_panel
        )
        self.issues_layout.addWidget(self.issue_scroll, 1)
        problems_layout.addLayout(self.issues_layout, 1)
        self.tabs.addTab(problems, t("sync_redesign.issues_tab", "문제 해결"))
        self.section_pages["issues"] = problems
        self.show_section(section)
        self.tabs.currentChanged.connect(lambda: self._refresh())
        root.addWidget(self.tabs, 1)
        footer, close, _ = build_dialog_footer(
            ok_label=t("outlook.close", "닫기"), cancel_label=None
        )
        footer.insertWidget(
            0,
            self._label(
                t("sync_redesign.footer_hint", "표시와 구독 설정은 변경 즉시 저장됩니다."),
                "syncMuted",
            ),
            1,
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

    def show_section(self, section):
        self.tabs.setCurrentWidget(self.section_pages.get(section, self.section_pages["calendars"]))

    def _toggle_common_settings(self, expanded):
        self.advanced.setVisible(expanded)
        self.advanced_toggle.setText(
            t("sync_disclosures.close_common_settings", "공통 설정 접기")
            if expanded
            else t("sync_disclosures.common_settings", "공통 설정")
        )
        self.advanced_toggle.setAccessibleName(self.advanced_toggle.text())

    def _toggle_services(self, expanded):
        self.more_services.setText(
            t("sync_disclosures.hide_services", "서비스 목록 접기")
            if expanded
            else t("sync_disclosures.show_services", "서비스 목록 펼치기")
        )
        self.more_services.setAccessibleName(self.more_services.text())
        self.more_services.setIcon(
            icon(ICON.NAV_DOWN if expanded else ICON.NAV_NEXT, color=self.tokens["accent"])
        )
        self._refresh()

    @staticmethod
    def _label(text, role=None):
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        if role:
            label.setProperty("role", role)
        return label

    @staticmethod
    def _scroll(name, body_name, viewport_name, body=None):
        scroll = QScrollArea()
        scroll.setObjectName(name)
        scroll.viewport().setObjectName(viewport_name)
        scroll.viewport().setAutoFillBackground(False)
        scroll.setWidgetResizable(True)
        # Scroll the content instead of imposing its preferred height on the window.
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        if body is None:
            body = QWidget()
            body.setObjectName(body_name)
        scroll.setWidget(body)
        body.setAutoFillBackground(False)
        return scroll

    def _build_service_card(self, provider, name, capability):
        card = QFrame()
        card.setObjectName("SyncServiceCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        symbol = QLabel()
        symbol.setPixmap(
            icon(
                ICON.GLOBE if provider == "ics" else ICON.CALENDAR, color=self.tokens["accent"]
            ).pixmap(26, 26)
        )
        heading.addWidget(symbol)
        heading.addWidget(self._label(name, "syncServiceTitle"), 1)
        badge = self._label("", "syncBadge")
        badge.setWordWrap(False)
        badge.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        heading.addWidget(badge)
        self.service_badges[provider] = badge
        layout.addLayout(heading)
        layout.addWidget(self._label(capability, "syncMuted"))
        status = self._label("", "syncStatus")
        layout.addWidget(status)
        self.labels[provider] = status
        last = self._label("", "syncMuted")
        self.last_sync_labels[provider] = last
        layout.addWidget(last)
        actions = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.service_action_layouts[provider] = actions
        auto = QCheckBox(t("sync_redesign.auto_refresh", "자동으로 갱신"))
        auto.setAccessibleName(name + " " + auto.text())
        auto.toggled.connect(
            lambda enabled, key=provider: (
                self.coordinator.set_auto(key, enabled) if self.coordinator else None
            )
        )
        self.auto_buttons[provider] = auto
        actions.addWidget(auto)
        actions.addStretch()
        sync = QPushButton(t("sync_redesign.refresh", "갱신"))
        sync.setObjectName("ghost_btn")
        sync.clicked.connect(lambda checked=False, key=provider: self._run_sync(key))
        sync.setAccessibleName(name + " " + sync.text())
        self.sync_buttons[provider] = sync
        actions.addWidget(sync)
        configure = QPushButton()
        configure.setObjectName("ghost_btn")
        configure.clicked.connect(lambda checked=False, key=provider: self._configure_provider(key))
        self.connect_buttons[provider] = configure
        actions.addWidget(configure)
        layout.addLayout(actions)
        self.service_cards[provider] = card
        return card

    def _configure_provider(self, provider):
        if provider == "ics":
            self._connect_ics()
            return
        state = self.coordinator.states.get(provider, {}) if self.coordinator else {}
        self._open(provider, sync_recovery_action(provider, state)["section"])

    def _refresh_retry_wait(self):
        if self.isVisible() and self.coordinator:
            self.coordinator.refresh(refresh_issues=False)
        else:
            self._retry_tick.stop()

    def _connect_ics(self):
        self._open("ics")
        if not self.coordinator or not self.coordinator.states.get("ics", {}).get("connected"):
            self.ics_manager._add_ics()

    def _issue_selection(self, *_):
        item = self.issue_list.currentItem()
        provider = item.data(Qt.ItemDataRole.UserRole) if item else None
        state = self.coordinator.states.get(provider, {}) if self.coordinator and provider else {}
        action = sync_recovery_action(provider, state) if state else {}
        self.resolve_selected.setEnabled(bool(provider))
        self.resolve_selected.setText(
            action.get("label", t("sync_redesign.fix_settings", "해결 방법 · 설정 열기"))
        )
        self.retry_selected.setEnabled(bool(action.get("can_retry")))
        self.retry_selected.setVisible(
            action.get("kind") not in {"connect", "reconnect", "select", "resume"}
        )
        self.retry_selected.setToolTip(action.get("hint", ""))
        object_name = "primary_btn" if not action.get("can_retry") else "ghost_btn"
        if self.resolve_selected.objectName() != object_name:
            self.resolve_selected.setObjectName(object_name)
            self.resolve_selected.style().unpolish(self.resolve_selected)
            self.resolve_selected.style().polish(self.resolve_selected)
        details = provider_status(state) if state else ""
        if state.get("calendar_errors") and self.coordinator:
            names = {c["id"]: c.get("name") or c["id"] for c in self.coordinator.calendar_rows}
            details += "\n\n" + "\n\n".join(
                names.get(cid, cid) + "\n" + sync_error_message(code)
                for cid, code in state["calendar_errors"].items()
            )
        if provider == "ics" and self.coordinator:
            errors = subscription_errors(self.app.settings)
            failed = [
                str(c.get("name") or c["id"]) + "\n" + sync_error_message(errors[c["id"]])
                for c in self.coordinator.calendar_rows
                if c.get("type") == "ics"
                and c.get("is_active", 1)
                and c.get("ics_url")
                and c["id"] in errors
            ]
            if failed:
                details = "\n\n".join(failed)
        hint = action.get("hint", "")
        body = details + ("\n\n" + hint if hint and hint != details else "")
        self.issue_detail.setText(
            provider_name(provider) + "\n\n" + body if provider and state else ""
        )

    def _retry_selected_issue(self):
        item = self.issue_list.currentItem()
        if not item or not self.coordinator:
            return
        provider = item.data(Qt.ItemDataRole.UserRole)
        state = self.coordinator.states.get(provider, {})
        if not sync_recovery_action(provider, state)["can_retry"]:
            return
        if provider == "ics":
            self._feedback_baselines = {"ics": state.get("last_success", "")}
            errors = subscription_errors(self.app.settings)
            failed = [
                c["id"]
                for c in self.coordinator.calendar_rows
                if c.get("type") == "ics" and c.get("is_active", 1) and c["id"] in errors
            ]
            started = (
                self.coordinator.sync_ics(force=True, calendar_ids=failed)
                if failed
                else self.coordinator.sync_ics(force=True)
            )
            self._feedback_providers = ("ics",) if started else ()
            self.sync_feedback.setText(
                t("sync_redesign.retry_started", "문제가 있는 구독을 다시 갱신하고 있습니다.")
                if started
                else t(
                    "sync_unified.sync_not_started",
                    "동기화를 시작하지 못했습니다. 연결 상태와 진행 중인 작업을 확인하세요.",
                )
            )
            self.sync_feedback.show()
            self._refresh()
        else:
            self._run_sync(provider)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "issues_layout"):
            self.issues_layout.setDirection(
                QBoxLayout.Direction.TopToBottom
                if self.width() < 840
                else QBoxLayout.Direction.LeftToRight
            )
        for layout in getattr(self, "service_action_layouts", {}).values():
            layout.setDirection(
                QBoxLayout.Direction.TopToBottom
                if self.width() < 760
                else QBoxLayout.Direction.LeftToRight
            )

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh()

    def hideEvent(self, event):
        self._retry_tick.stop()
        super().hideEvent(event)

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

    def _open(self, provider, section="services", *, calendar_id=None):
        if provider == "google":
            if section == "issues":
                self.app.open_gcal_sync_issues_dialog()
            else:
                return_to_calendars = self.app.open_gcal_settings_dialog(
                    initial_tab="calendar" if section == "calendars" else None, from_sync_hub=True
                )
                if return_to_calendars is True:
                    self.show_section("calendars")
                    self.calendar_manager.show_provider("")
        elif provider == "outlook":
            from calendar_app.presentation.main_window.outlook_sync_controller import (
                open_outlook_settings,
            )

            open_outlook_settings(self.app, section=section, from_sync_hub=True)
        elif provider == "ics":
            self.show_section("ics")
            self.ics_manager.show_provider("ics")
            self.ics_manager.reveal_subscription.setChecked(False)
            if calendar_id and self.ics_manager.select_calendar(calendar_id):
                return
            failed = subscription_errors(self.app.settings) if section == "issues" else {}
            candidates = []
            for index in range(self.ics_manager.calendars.count()):
                item = self.ics_manager.calendars.item(index)
                calendar = item.data(Qt.ItemDataRole.UserRole)
                if calendar.get("type") == "ics":
                    candidates.append(item)
                    if (
                        calendar["id"] in failed
                        and calendar.get("is_active", 1)
                        and calendar.get("ics_url")
                    ):
                        self.ics_manager.calendars.setCurrentItem(item)
                        return
            if candidates:
                self.ics_manager.calendars.setCurrentItem(candidates[0])
            return
        elif provider == "local":
            self.show_section("local")
            self.local_manager.show_provider("local")
            if calendar_id:
                self.local_manager.select_calendar(calendar_id)
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
            self._feedback_baselines = {
                p: s.get("last_success", "") for p, s in self.coordinator.states.items()
            }
            started = self.coordinator.sync(provider)
            self._feedback_providers = tuple(started)
            self.sync_feedback.setText(
                t(
                    "sync_unified.sync_started_services",
                    "동기화를 시작했습니다: {services}",
                    services=", ".join(provider_name(p) for p in started),
                )
                if started
                else t(
                    "sync_unified.sync_not_started",
                    "동기화를 시작하지 못했습니다. 연결 상태와 진행 중인 작업을 확인하세요.",
                )
            )
            self.sync_feedback.show()
            self._refresh()

    def _set_all_auto(self, enabled):
        if self.coordinator:
            for provider, state in self.coordinator.states.items():
                if state["connected"]:
                    self.coordinator.set_auto(provider, enabled)

    def _open_selected_issue(self):
        item = self.issue_list.currentItem()
        if item:
            provider = item.data(Qt.ItemDataRole.UserRole)
            state = self.coordinator.states.get(provider, {}) if self.coordinator else {}
            action = sync_recovery_action(provider, state)
            self._open(provider, "issues" if provider == "ics" else action["section"])

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
        for key in ("outlook", *CALDAV_SERVICES):
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
                "completed_with_issues",
                "cancelled",
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
        self.summary.setText(
            t(
                "sync_redesign.connections_hint",
                "계정으로 연결하거나 구독 주소로 일정을 가져오세요.",
            )
        )
        self.sync_all.setEnabled(False)
        self.sync_all.setToolTip(
            t(
                "sync_unified.sync_not_started",
                "동기화를 시작하지 못했습니다. 연결 상태와 진행 중인 작업을 확인하세요.",
            )
        )
        for provider, button in self.sync_buttons.items():
            button.setEnabled(False)
            button.hide()
            self.auto_buttons[provider].hide()
            connected = (
                authenticated
                if provider == "google"
                else bool(
                    settings.value(
                        ("outlook_" if provider == "outlook" else "caldav_" + provider + "_")
                        + "account_id",
                        "",
                        type=str,
                    )
                )
                if provider != "ics"
                else False
            )
            configure = self.connect_buttons[provider]
            configure.setText(
                t("sync_redesign.subscribe_url", "주소로 구독")
                if provider == "ics"
                else t("sync_redesign.connection_settings", "연결 설정")
                if connected
                else t("sync_redesign.connect_account", "계정 연결")
            )
            configure.setEnabled(provider != "ics")
            self.service_badges[provider].setText(
                t("sync_ui.connected", "연결됨")
                if connected
                else t("sync_redesign.not_connected", "미연결")
            )
            if provider not in {"google", "ics"}:
                self.service_cards[provider].setVisible(connected or self.more_services.isChecked())
        self.issue_summary.setText(
            t(
                "sync_unified.sync_not_started",
                "동기화를 시작하지 못했습니다. 연결 상태와 진행 중인 작업을 확인하세요.",
            )
        )
        self.issue_list.hide()
        self.issue_scroll.hide()

    def _refresh_unified(self):
        states = self.coordinator.states
        if self._feedback_providers and not any(
            states[p]["busy"] for p in self._feedback_providers
        ):
            results = [states[p] for p in self._feedback_providers]
            if any(s.get("error") or s.get("issues") for s in results):
                message = t(
                    "sync_recovery.finished_issues",
                    "동기화가 끝났습니다. 문제 해결에서 확인이 필요한 항목을 살펴보세요.",
                )
            elif all(s.get("cancelled") for s in results):
                message = t("sync_ui.cancelled", "작업이 취소되었습니다. 기존 일정은 보존됩니다.")
            elif all(
                s.get("last_success") and s["last_success"] != self._feedback_baselines.get(p)
                for p, s in zip(self._feedback_providers, results, strict=True)
            ):
                message = t(
                    "sync_recovery.finished", "동기화가 완료되었습니다. 최신 일정을 반영했습니다."
                )
            else:
                message = t(
                    "sync_recovery.finished_unconfirmed",
                    "작업이 종료되었습니다. 마지막 갱신 기록과 연결 상태를 확인하세요.",
                )
            self._feedback_providers = ()
            self.sync_feedback.setText(message)
        self.sync_all.setEnabled(
            any(sync_recovery_action(p, s)["can_retry"] for p, s in states.items())
        )
        if self.isVisible() and any(s.get("retry_remaining") for s in states.values()):
            if not self._retry_tick.isActive():
                self._retry_tick.start()
        else:
            self._retry_tick.stop()
        rows = self.coordinator.calendar_rows
        self.summary.setText(
            t(
                "sync_redesign.overview",
                "캘린더 {total}개 · 화면에 표시 {visible}개",
                total=len(rows),
                visible=sum(bool(c.get("is_visible", 1)) for c in rows),
            )
        )
        self.sync_all.setToolTip(
            t("sync_redesign.sync_available", "연결된 캘린더의 최신 일정을 가져옵니다.")
            if self.sync_all.isEnabled()
            else t(
                "sync_redesign.sync_unavailable",
                "연결할 서비스를 선택하거나 진행 중인 갱신이 끝날 때까지 기다리세요.",
            )
        )
        selected = self.issue_list.currentItem()
        selected_provider = selected.data(Qt.ItemDataRole.UserRole) if selected else None
        issue_rows = []
        extra_disconnected = False
        for provider, state in states.items():
            action = sync_recovery_action(provider, state)
            text = provider_status(state)
            if provider == "ics" and not state["connected"]:
                text = t(
                    "sync_redesign.ics_empty",
                    "ICS 주소를 등록하면 일정을 가져옵니다. Google 로그인 없이 사용할 수 있습니다.",
                )
            elif provider == "ics" and state.get("needs_selection"):
                text = t(
                    "sync_redesign.ics_paused",
                    "구독 갱신이 일시정지되어 있습니다. 내 캘린더에서 다시 켤 수 있습니다.",
                )
            elif (
                provider == "google"
                and state.get("import_paused")
                and not state.get("error")
                and not state["busy"]
                and not state.get("paused")
            ):
                text = t(
                    "sync_recovery.import_paused",
                    "새 일정 가져오기는 꺼져 있습니다. 기존 일정의 변경 사항은 동기화할 수 있습니다.",
                )
            elif (
                state["connected"]
                and not state.get("error")
                and not state["busy"]
                and not state.get("needs_selection")
                and not state.get("paused")
                and not state.get("retry_remaining")
            ):
                text = (
                    t(
                        "sync_redesign.ics_schedule",
                        "자동 갱신을 켜면 1시간마다 새 일정을 가져옵니다.",
                    )
                    if provider == "ics"
                    else t(
                        "sync_redesign.account_ready",
                        "가져올 캘린더와 표시할 일정을 관리할 수 있습니다.",
                    )
                )
            self.labels[provider].setText(text)
            last = state.get("last_success", "")
            try:
                last = (
                    datetime.fromisoformat(last).astimezone().strftime("%Y-%m-%d %H:%M")
                    if last
                    else ""
                )
            except (ValueError, TypeError, OverflowError, OSError):
                last = ""
            self.last_sync_labels[provider].setText(
                t("sync_redesign.last_updated", "마지막 갱신 {time}", time=last)
                if last
                else t("sync_redesign.never_updated", "아직 가져온 기록이 없습니다.")
            )
            self.last_sync_labels[provider].setVisible(bool(state["connected"]))
            badge = self.service_badges[provider]
            health = (
                "busy"
                if state["busy"]
                else "attention"
                if state["issues"] or state.get("error") or state.get("needs_selection")
                else "idle"
                if state.get("paused")
                else "ok"
                if state["connected"]
                else "idle"
            )
            badge_text = (
                t("sync_ui.working", "작업 중...")
                if health == "busy"
                else t("sync_recovery.paused", "일시정지")
                if state.get("paused")
                else t("sync_redesign.check_needed", "확인 필요")
                if health == "attention"
                else t(
                    "sync_redesign.subscriptions_count",
                    "구독 {count}개",
                    count=state.get("total", 0),
                )
                if provider == "ics" and state["connected"]
                else t("sync_ui.connected", "연결됨")
                if state["connected"]
                else t("sync_redesign.not_connected", "미연결")
            )
            badge.setText(badge_text)
            if badge.property("health") != health:
                badge.setProperty("health", health)
                badge.style().unpolish(badge)
                badge.style().polish(badge)
            configure = self.connect_buttons[provider]
            configure.setText(action["label"])
            object_name = (
                "primary_btn"
                if action["kind"] in {"connect", "reconnect", "resume", "select", "issues"}
                else "ghost_btn"
            )
            if configure.objectName() != object_name:
                configure.setObjectName(object_name)
                configure.style().unpolish(configure)
                configure.style().polish(configure)
            configure.setToolTip(action["hint"])
            configure.setAccessibleName(provider_name(provider) + " " + configure.text())
            configure.setEnabled(True)
            auto = self.auto_buttons[provider]
            auto.blockSignals(True)
            auto.setChecked(state["auto"])
            auto.blockSignals(False)
            auto.setEnabled(state["connected"] and not state["busy"] and not state.get("paused"))
            auto.setVisible(bool(state["connected"]))
            self.sync_buttons[provider].setEnabled(action["can_retry"])
            self.sync_buttons[provider].setText(
                t("sync_redesign.retry", "다시 동기화")
                if state.get("error")
                else t("sync_redesign.refresh", "갱신")
            )
            self.sync_buttons[provider].setVisible(
                bool(state["connected"]) and action["kind"] not in {"reconnect", "select", "resume"}
            )
            self.sync_buttons[provider].setToolTip(action["hint"])
            self.sync_buttons[provider].setAccessibleName(
                provider_name(provider) + " " + self.sync_buttons[provider].text()
            )
            if provider not in {"google", "ics"}:
                eligible = bool(state["connected"] or state["busy"] or state.get("error"))
                extra_disconnected |= not eligible
                self.service_cards[provider].setVisible(eligible or self.more_services.isChecked())
            if state["issues"] or state.get("error") or state.get("needs_selection"):
                issue_rows.append(
                    (provider, provider_name(provider) + "\n" + provider_status(state))
                )
        if issue_rows != self._issue_snapshot:
            scroll_value = self.issue_list.verticalScrollBar().value()
            self.issue_list.blockSignals(True)
            old_providers = [
                self.issue_list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.issue_list.count())
            ]
            rebuild = old_providers != [p for p, _ in issue_rows]
            if rebuild:
                self.issue_list.clear()
            for index, (provider, text) in enumerate(issue_rows):
                item = QListWidgetItem(text) if rebuild else self.issue_list.item(index)
                item.setText(text)
                item.setToolTip(plain_tooltip(item.text()))
                item.setData(Qt.ItemDataRole.UserRole, provider)
                if rebuild:
                    self.issue_list.addItem(item)
                if selected_provider == provider:
                    self.issue_list.setCurrentItem(item)
            self.issue_list.blockSignals(False)
            self.issue_list.verticalScrollBar().setValue(scroll_value)
            self._issue_snapshot = issue_rows
        self.issue_summary.setText(
            t(
                "sync_redesign.no_issues",
                "현재 해결할 문제가 없습니다. 연결한 캘린더를 계속 사용할 수 있습니다.",
            )
            if not self.issue_list.count()
            else t(
                "sync_redesign.issues_hint",
                "문제가 있는 연결을 선택하고 다음 조치를 확인하세요.",
            )
        )
        if self.issue_list.count() and self.issue_list.currentItem() is None:
            self.issue_list.setCurrentRow(0)
        self.more_services_header.setVisible(extra_disconnected)
        self.issue_list.setVisible(bool(self.issue_list.count()))
        self.issue_panel.setVisible(bool(self.issue_list.count()))
        self.issue_scroll.setVisible(bool(self.issue_list.count()))
        self._issue_selection()
        count = self.issue_list.count()
        self.tabs.setTabText(
            self.tabs.indexOf(self.section_pages["issues"]),
            t("sync_redesign.issues_tab_count", "문제 해결 ({count})", count=count)
            if count
            else t("sync_redesign.issues_tab", "문제 해결"),
        )
        for page in (self.calendar_manager, self.local_manager, self.ics_manager):
            page.reload()


def open_calendar_sync_hub(app, section="calendars"):
    CalendarSyncHub(app, section).exec()
