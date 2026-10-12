# -*- coding: utf-8 -*-
"""Service-neutral local presentation settings and calendar creation."""

from contextlib import suppress
from datetime import datetime
from urllib.parse import urlsplit
from uuid import uuid4

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QGuiApplication, QIcon
from PyQt6.QtWidgets import (
    QBoxLayout,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from calendar_app.application.calendar_sync_contract import CalendarSyncError
from calendar_app.infrastructure.db import calendar_repo
from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.ics.subscriptions import (
    normalize_subscription_url,
    subscription_errors,
)
from calendar_app.presentation.dialogs.dialog_styles import get_dialog_theme_tokens
from calendar_app.presentation.dialogs.ics_subscription_dialog import IcsSubscriptionDialog
from calendar_app.presentation.dialogs.sync_feedback import (
    guard_calendar_action,
    sync_error_message,
)
from calendar_app.shared.color_utils import contrast_safe_color
from calendar_app.shared.icon_map import ICON, icon


class _CalendarRowLabel(QLabel):
    """Keep long calendar names and source details inside their list row."""

    def __init__(self, text, role, parent=None):
        super().__init__(parent)
        self._full_text = str(text)
        self.setProperty("role", role)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setToolTip(self._full_text)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._elide()

    def _elide(self):
        self.setText(
            self.fontMetrics().elidedText(
                self._full_text,
                Qt.TextElideMode.ElideRight,
                max(0, self.contentsRect().width()),
            )
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()


class _CalendarRowDelegate(QStyledItemDelegate):
    """Let row widgets draw text while the list retains selection and accessibility."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.text = ""
        option.icon = QIcon()
        option.decorationSize = QSize(0, 0)
        option.features &= ~(
            QStyleOptionViewItem.ViewItemFeature.HasDecoration
            | QStyleOptionViewItem.ViewItemFeature.HasDisplay
        )

    def paint(self, painter, option, index):
        prepared = QStyleOptionViewItem(option)
        self.initStyleOption(prepared, index)
        widget = prepared.widget or self.parent()
        widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, prepared, painter, widget)


class CalendarManagerPage(QWidget):
    def __init__(self, app, coordinator, open_service, *, scope="all", show_add_actions=True):
        super().__init__()
        if scope not in {"all", "local", "ics"}:
            raise ValueError("invalid_calendar_manager_scope")
        self.app, self.coordinator, self.open_service = app, coordinator, open_service
        self.scope = scope
        self._overview = scope == "all" and not show_add_actions
        self._selected_id = None
        self._refresh_feedback_pending = False
        self._rows_snapshot = None
        self.default_controls = {}
        self._row_widgets = {}
        self._default_group = QButtonGroup(self)
        self._effective_default_id = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        intro = (
            t(
                "calendar_management_tabs.local_hint",
                "이 PC에 저장할 캘린더를 추가하고 이름·색상·표시와 기본 저장 대상을 관리하세요.",
            )
            if scope == "local"
            else t(
                "calendar_management_tabs.ics_hint",
                "구독 주소로 외부 일정을 읽기 전용으로 가져옵니다. 표시 여부와 자동 갱신은 따로 설정할 수 있습니다.",
            )
            if scope == "ics"
            else t(
                "calendar_list_default.intro",
                "목록의 ‘기본 저장’을 선택하면 새 일정의 기본 캘린더가 됩니다.",
            )
        )
        note = self._label(intro, "syncMuted")
        root.addWidget(note)
        toolbar = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.add_local = self.add_ics = None
        if show_add_actions and scope in {"all", "local"}:
            self.add_local = self._button(
                t("sync_unified.add_local", "로컬 캘린더 추가"),
                self._add_local,
                primary=scope == "local",
            )
            toolbar.addWidget(self.add_local)
        if show_add_actions and scope in {"all", "ics"}:
            self.add_ics = self._button(
                t("sync_unified.add_ics", "ICS 구독 추가"), self._add_ics, primary=True
            )
            toolbar.addWidget(self.add_ics)
        if toolbar.count():
            toolbar.addStretch()
            root.addLayout(toolbar)

        self.panes = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.panes.setSpacing(16)
        root.addLayout(self.panes, 1)
        self.list_panel = QWidget()
        self.list_panel.setMinimumWidth(0)
        self.list_panel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        list_layout = QVBoxLayout(self.list_panel)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(8)
        filters = QBoxLayout(QBoxLayout.Direction.TopToBottom)
        self.search = QLineEdit()
        self.search.setPlaceholderText(t("sync_unified.search_calendars", "캘린더 이름 검색"))
        self.search.setAccessibleName(self.search.placeholderText())
        self.search.textChanged.connect(self.reload)
        filters.addWidget(self.search)
        self.provider_filter = QComboBox()
        self.provider_filter.setAccessibleName(t("sync_unified.filter_service", "서비스별로 보기"))
        self.provider_filter.addItem(t("sync_unified.all_services", "모든 서비스"), "")
        from calendar_app.presentation.main_window.calendar_sync_coordinator import (
            PROVIDERS,
            provider_name,
        )

        self.provider_filter.addItem(t("sync_unified.local", "로컬"), "local")
        self.provider_filter.addItem(t("sync_unified.shared", "PC 공유"), "shared")
        for provider in PROVIDERS:
            self.provider_filter.addItem(provider_name(provider), provider)
        filters.addWidget(self.provider_filter)
        if scope != "all":
            self.provider_filter.setCurrentIndex(self.provider_filter.findData(scope))
            self.provider_filter.hide()
        self.provider_filter.currentIndexChanged.connect(self.reload)
        list_layout.addLayout(filters)
        self.count = self._label("", "syncMuted")
        list_layout.addWidget(self.count)
        self.calendars = QListWidget()
        self.calendars.setObjectName("SyncCalendarList")
        self.calendars.setItemDelegate(_CalendarRowDelegate(self.calendars))
        self.calendars.setMinimumHeight(240)
        self.calendars.setIconSize(QSize(22, 22))
        self.calendars.setSpacing(3)
        self.calendars.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.calendars.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.calendars.setAccessibleName(
            t("calendar_management_tabs.local_tab", "로컬 캘린더")
            if scope == "local"
            else t("calendar_management_tabs.ics_tab", "ICS 구독")
            if scope == "ics"
            else t("sync_unified.calendars", "전체 캘린더")
        )
        self.calendars.currentItemChanged.connect(self._selection)
        list_layout.addWidget(self.calendars, 1)
        self.empty = self._label("", "syncMuted")
        list_layout.addWidget(self.empty)
        self.panes.addWidget(self.list_panel, 5)

        self.details = QFrame()
        self.details.setObjectName("SyncCalendarDetails")
        self.details.setMinimumWidth(0)
        self.details.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        details_layout = QVBoxLayout(self.details)
        details_layout.setContentsMargins(16, 14, 16, 14)
        details_layout.setSpacing(12)
        self.detail_title = self._label("", "syncCalendarTitle")
        details_layout.addWidget(self.detail_title)
        self.detail_source = self._label("", "syncMuted")
        details_layout.addWidget(self.detail_source)
        self.selection_info = self._label("", "syncMuted")
        details_layout.addWidget(self.selection_info)

        self.display_section = QFrame()
        self.display_section.setObjectName("SyncCalendarSection")
        display_layout = QVBoxLayout(self.display_section)
        display_layout.setContentsMargins(12, 10, 12, 10)
        display_layout.setSpacing(8)
        display_layout.addWidget(
            self._label(t("calendar_list_default.display_section", "화면 표시"), "syncSectionTitle")
        )
        self.visible = QCheckBox(t("sync_unified.show_calendar", "일정 화면에 표시"))
        self.visible.toggled.connect(self._visible)
        display_layout.addWidget(self.visible)
        details_layout.addWidget(self.display_section)

        self.appearance_section = QFrame()
        self.appearance_section.setObjectName("SyncCalendarSection")
        appearance_layout = QVBoxLayout(self.appearance_section)
        appearance_layout.setContentsMargins(12, 10, 12, 10)
        appearance_layout.setSpacing(8)
        appearance_layout.addWidget(
            self._label(t("sync_redesign.appearance_section", "이름과 색상"), "syncSectionTitle")
        )
        appearance_actions = QHBoxLayout()
        self.rename = self._button(t("sync_unified.rename", "이름 변경"), self._rename)
        self.color = self._button(t("sync_unified.color", "색상 변경"), self._color)
        appearance_actions.addWidget(self.rename)
        appearance_actions.addWidget(self.color)
        appearance_layout.addLayout(appearance_actions)
        details_layout.addWidget(self.appearance_section)

        self.subscription_section = QFrame()
        self.subscription_section.setObjectName("SyncSubscriptionSection")
        subscription_layout = QVBoxLayout(self.subscription_section)
        subscription_layout.setContentsMargins(12, 10, 12, 10)
        subscription_layout.setSpacing(8)
        subscription_layout.addWidget(
            self._label(t("sync_redesign.subscription_section", "구독 갱신"), "syncSectionTitle")
        )
        self.subscription_info = self._label("", "syncStatus")
        self.subscription_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        subscription_layout.addWidget(self.subscription_info)
        self.subscription_active = QCheckBox(t("sync_redesign.subscription_active", "이 구독 갱신"))
        self.subscription_active.toggled.connect(self._subscription_active)
        subscription_layout.addWidget(self.subscription_active)
        self.subscription_hint = self._label("", "syncMuted")
        subscription_layout.addWidget(self.subscription_hint)
        self.subscription_address = self._label("", "syncMuted")
        self.subscription_address.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        subscription_layout.addWidget(self.subscription_address)
        address_actions = QHBoxLayout()
        self.reveal_subscription = self._button(
            t("sync_redesign.show_address", "주소 보기"), self._show_subscription_address
        )
        self.reveal_subscription.setCheckable(True)
        self.copy_subscription = self._button(
            t("sync_redesign.copy_address", "주소 복사"), self._copy_subscription_address
        )
        address_actions.addWidget(self.reveal_subscription)
        address_actions.addWidget(self.copy_subscription)
        subscription_layout.addLayout(address_actions)
        details_layout.addWidget(self.subscription_section)

        self.service_actions = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.edit_subscription = self._button(
            t("sync_unified.edit_ics", "구독 주소 수정"), self._edit_subscription
        )
        self.service_actions.addWidget(self.edit_subscription)
        self.service = self._button(
            t("sync_redesign.service_settings", "가져올 캘린더 선택 · 연결 설정"), self._service
        )
        self.service_actions.addWidget(self.service)
        details_layout.addLayout(self.service_actions)
        details_layout.addStretch()
        self.removal_hint = self._label("", "syncMuted")
        details_layout.addWidget(self.removal_hint)
        self.remove = self._button(
            t("sync_unified.remove_calendar", "로컬 목록에서 제거"), self._remove
        )
        self.remove.setObjectName("danger_btn")
        details_layout.addWidget(self.remove)
        self.panes.addWidget(self.details, 6)
        self.feedback = self._label("", "syncStatus")
        root.addWidget(self.feedback)
        self.reload()

    @staticmethod
    def _label(text, role):
        label = QLabel(text)
        label.setProperty("role", role)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        return label

    @staticmethod
    def _button(text, callback, primary=False):
        button = QPushButton(text)
        button.setObjectName("primary_btn" if primary else "ghost_btn")
        button.setAccessibleName(text)
        # Guarded actions accept *args, so Qt cannot discard clicked(bool) for them.
        button.clicked.connect(lambda _checked=False: callback())
        return button

    def resizeEvent(self, event):
        super().resizeEvent(event)
        narrow = event.size().width() < 780
        direction = QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight
        self.panes.setDirection(direction)
        self.calendars.setMaximumHeight(270 if narrow else 16777215)
        self.service_actions.setDirection(
            QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight
        )

    def current(self):
        item = self.calendars.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def reload(self, *_):
        if self._refresh_feedback_pending and not self._ics_busy():
            self._refresh_feedback_pending = False
            self.feedback.clear()
        rows = self.coordinator.calendar_rows if self.coordinator else []
        query = self.search.text().strip().casefold()
        provider = self.scope if self.scope != "all" else self.provider_filter.currentData()
        tokens = get_dialog_theme_tokens(settings=self.app.settings)
        snapshot = (
            [dict(row) for row in rows],
            query,
            provider,
            dict(self.coordinator.calendar_providers) if self.coordinator else {},
            tokens["accent"],
            tokens["surface_item"],
        )
        if snapshot == self._rows_snapshot:
            scroll_value = self.calendars.verticalScrollBar().value()
            self._selection()
            # Updating hidden service status can temporarily resize the list
            # while Qt settles the stacked pages, clamping its scroll position.
            # Restore after the layout requests for this refresh are delivered.
            expected_rows = self._rows_snapshot
            QTimer.singleShot(0, lambda: self._restore_scroll_position(scroll_value, expected_rows))
            return
        selected = (self.current() or {}).get("id")
        scroll_value = self.calendars.verticalScrollBar().value()
        focused_default = next(
            (identity for identity, button in self.default_controls.items() if button.hasFocus()),
            None,
        )
        self.calendars.blockSignals(True)
        for button in self.default_controls.values():
            self._default_group.removeButton(button)
        self.default_controls.clear()
        self._row_widgets.clear()
        self.calendars.clear()
        for calendar in rows:
            source = self._provider(calendar) or calendar.get("type")
            if self.scope != "all" and calendar.get("type") != self.scope:
                continue
            if provider and source != provider:
                continue
            if query and query not in str(calendar.get("name") or calendar["id"]).casefold():
                continue
            readonly = calendar_repo.is_calendar_row_read_only(calendar)
            name = calendar.get("name") or calendar["id"]
            traits = [self._source_label(calendar)]
            if readonly:
                traits.append(t("outlook.read_only", "읽기 전용"))
            if calendar.get("is_default"):
                traits.append(t("sync_redesign.default_badge", "새 일정 저장"))
            if not calendar.get("is_visible", 1):
                traits.append(t("sync_redesign.hidden_badge", "표시 안 함"))
            if not calendar.get("is_active", 1):
                traits.append(
                    t("sync_redesign.paused_badge", "갱신 중지")
                    if calendar.get("type") == "ics"
                    else t("sync_redesign.not_selected_badge", "가져오기 선택 안 함")
                )
            label = str(name) + "\n" + " · ".join(traits)
            item = QListWidgetItem(label)
            identity_color = contrast_safe_color(
                calendar.get("color") or tokens["accent"], tokens["surface_item"], minimum=3.0
            )
            item.setIcon(
                icon(
                    ICON.LINK if calendar.get("type") == "ics" else ICON.VIEW_CALENDAR,
                    color=identity_color,
                )
            )
            item.setSizeHint(QSize(0, 76))
            item.setData(Qt.ItemDataRole.UserRole, calendar)
            item.setData(Qt.ItemDataRole.AccessibleTextRole, label.replace("\n", ". "))
            item.setToolTip(str(name) + " · " + " · ".join(traits))
            self.calendars.addItem(item)
            row = QFrame()
            row.setObjectName("SyncCalendarRow")
            row.setProperty("selected", False)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 8, 12, 8)
            row_layout.setSpacing(10)
            marker = QLabel()
            marker.setPixmap(item.icon().pixmap(22, 22))
            marker.setFixedSize(24, 24)
            marker.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            row_layout.addWidget(marker)
            text_layout = QVBoxLayout()
            text_layout.setSpacing(3)
            text_layout.addWidget(_CalendarRowLabel(name, "syncCalendarName", row))
            # The checked radio conveys the default without a second visual badge.
            displayed_traits = [
                trait
                for trait in traits
                if trait != t("sync_redesign.default_badge", "새 일정 저장")
            ]
            text_layout.addWidget(_CalendarRowLabel(" · ".join(displayed_traits), "syncMuted", row))
            row_layout.addLayout(text_layout, 1)
            radio = QRadioButton(t("calendar_list_default.choose", "기본 저장"), row)
            radio.setObjectName("CalendarDefaultRadio")
            radio.setAccessibleName(
                t(
                    "calendar_list_default.accessible",
                    "{name}: 새 일정의 기본 저장 대상으로 지정",
                    name=str(name),
                )
            )
            radio.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            radio.clicked.connect(
                lambda checked, key=calendar["id"]: self._default(key) if checked else None
            )
            row_layout.addWidget(radio)
            self._default_group.addButton(radio)
            self.default_controls[calendar["id"]] = radio
            self._row_widgets[calendar["id"]] = row
            self.calendars.setItemWidget(item, row)
            if calendar["id"] == selected:
                self.calendars.setCurrentItem(item)
        if self.calendars.currentItem() is None and self.calendars.count():
            self.calendars.setCurrentRow(0)
        self.calendars.blockSignals(False)
        self.calendars.verticalScrollBar().setValue(scroll_value)
        self._rows_snapshot = snapshot
        self.count.setText(
            t("sync_redesign.calendar_count", "{count}개 캘린더").format(
                count=self.calendars.count()
            )
        )
        self.empty.setVisible(not self.calendars.count())
        self.empty.setText(
            t(
                "sync_unified.no_calendar_matches",
                "표시할 캘린더가 없습니다. 검색·서비스 필터를 확인하거나 캘린더를 추가하세요.",
            )
        )
        self._selection()
        if focused_default in self.default_controls:
            self.default_controls[focused_default].setFocus(Qt.FocusReason.OtherFocusReason)

    def _restore_scroll_position(self, value, expected_rows):
        if self._rows_snapshot is not expected_rows:
            return
        # The owning modal dialog may close before its deferred callback.
        with suppress(RuntimeError):
            self.calendars.verticalScrollBar().setValue(value)

    def _sync_default_controls(self):
        rows = self.coordinator.calendar_rows if self.coordinator else []
        writable = [row for row in rows if calendar_repo.can_calendar_be_default(row)]
        default = next((row for row in writable if row.get("is_default")), None)
        default = default or next(iter(writable), None)
        self._effective_default_id = (default or {}).get("id")
        by_id = {row["id"]: row for row in rows}
        self._default_group.setExclusive(False)
        try:
            for identity, button in self.default_controls.items():
                calendar = by_id.get(identity)
                checked = identity == self._effective_default_id
                button.blockSignals(True)
                button.setChecked(checked)
                button.blockSignals(False)
                button.setEnabled(calendar_repo.can_calendar_be_default(calendar))
                hint = (
                    t(
                        "sync_redesign.readonly_default",
                        "읽기 전용 캘린더에는 새 일정을 저장할 수 없습니다.",
                    )
                    if calendar_repo.is_calendar_row_read_only(calendar)
                    else t(
                        "sync_redesign.inactive_default",
                        "서비스에서 이 캘린더를 가져오도록 선택한 뒤 설정하세요.",
                    )
                    if not calendar or not calendar.get("is_active", 1)
                    else t("sync_redesign.current_default", "새 일정의 기본 저장 대상입니다")
                    if checked
                    else t(
                        "sync_redesign.default_hint",
                        "새 일정을 만들 때 처음 선택되는 저장 위치입니다.",
                    )
                )
                button.setToolTip(hint)
                button.setAccessibleDescription(hint)
        finally:
            self._default_group.setExclusive(True)

    def show_provider(self, provider):
        self.search.clear()
        index = self.provider_filter.findData(self.scope if self.scope != "all" else provider)
        self.provider_filter.setCurrentIndex(max(0, index))
        self.reload()

    def select_calendar(self, calendar_id):
        for index in range(self.calendars.count()):
            item = self.calendars.item(index)
            if item.data(Qt.ItemDataRole.UserRole)["id"] == calendar_id:
                self.calendars.setCurrentItem(item)
                self.calendars.scrollToItem(item)
                return True
        return False

    def _provider(self, calendar):
        if self.coordinator:
            return self.coordinator.calendar_providers.get(calendar["id"])
        return None

    def _source_label(self, calendar):
        from calendar_app.presentation.main_window.calendar_sync_coordinator import (
            provider_name,
        )

        provider = self._provider(calendar)
        if provider:
            return provider_name(provider)
        return {
            "local": t("sync_unified.local", "로컬"),
            "shared": t("sync_unified.shared", "PC 공유"),
            "gcal": "Google Calendar",
            "outlook": "Outlook",
            "caldav": "CalDAV",
            "ics": t("sync_unified.ics", "ICS 구독"),
        }.get(calendar.get("type"), t("sync_unified.local", "로컬"))

    def _selection(self, *_):
        self._sync_default_controls()
        calendar = self.current()
        selected_id = (calendar or {}).get("id")
        if self._selected_id != selected_id:
            self.reveal_subscription.blockSignals(True)
            self.reveal_subscription.setChecked(False)
            self.reveal_subscription.blockSignals(False)
            self._selected_id = selected_id
        if self.add_ics is not None:
            self.add_ics.setEnabled(bool(self.coordinator) and not self._ics_busy())
        self.detail_title.setText(
            str(calendar.get("name") or calendar["id"])
            if calendar
            else t("sync_redesign.select_calendar", "캘린더를 선택하세요")
        )
        self.detail_source.setText(self._source_label(calendar) if calendar else "")
        for identity, row in self._row_widgets.items():
            selected = identity == selected_id
            if row.property("selected") != selected:
                row.setProperty("selected", selected)
                row.style().unpolish(row)
                row.style().polish(row)
                row.update()
        self.selection_info.setText(
            t(
                "sync_unified.select_calendar_hint",
                "캘린더를 선택하면 표시·색상·저장 대상과 구독 상태를 변경할 수 있습니다.",
            )
            if not calendar
            else t(
                "sync_unified.read_only_hint",
                "읽기 전용 캘린더입니다. 기본 저장 대상으로 사용할 수 없으며 일정 수정은 원래 서비스에서 진행하세요.",
            )
            if calendar_repo.is_calendar_row_read_only(calendar)
            else t(
                "sync_redesign.unselected_hint",
                "가져오기 대상에서 제외된 캘린더입니다. 연결 설정에서 이 캘린더를 선택하면 새 일정의 저장 위치로 사용할 수 있습니다.",
            )
            if not calendar.get("is_active", 1)
            else t(
                "sync_unified.writable_hint",
                "일정을 저장할 수 있는 캘린더입니다. 기본 저장 대상으로 지정할 수 있습니다.",
            )
        )
        if (
            calendar
            and calendar["id"] == self._effective_default_id
            and not calendar.get("is_visible", 1)
        ):
            self.selection_info.setText(
                self.selection_info.text()
                + "\n"
                + t(
                    "calendar_controls.hidden_default_hint",
                    "이 캘린더의 일정은 현재 화면에서 숨겨져 있습니다.",
                )
            )
        for button in (self.visible, self.rename, self.color, self.remove):
            button.setEnabled(bool(calendar))
        for section in (self.display_section, self.appearance_section):
            section.setVisible(bool(calendar))
        self.service.setEnabled(
            bool(calendar and (self._provider(calendar) or calendar.get("type") == "ics"))
        )
        self.visible.blockSignals(True)
        self.visible.setChecked(bool(calendar and calendar.get("is_visible", 1)))
        self.visible.blockSignals(False)
        self.rename.setEnabled(bool(calendar and calendar.get("type") != "gcal"))
        self.rename.setToolTip(
            t(
                "sync_redesign.google_name_hint",
                "Google 캘린더의 이름은 Google Calendar에서 변경하세요.",
            )
            if calendar and calendar.get("type") == "gcal"
            else ""
        )
        if calendar:
            tokens = get_dialog_theme_tokens(settings=self.app.settings)
            identity_color = contrast_safe_color(
                calendar.get("color") or tokens["accent"], tokens["surface_item"], minimum=3.0
            )
            self.color.setIcon(icon(ICON.COLOR_PICKER, color=identity_color))
        ics = bool(calendar and calendar.get("type") == "ics")
        self.subscription_section.setVisible(ics)
        self.subscription_active.setVisible(ics)
        self.subscription_active.blockSignals(True)
        self.subscription_active.setChecked(bool(ics and calendar.get("is_active", 1)))
        self.subscription_active.blockSignals(False)
        self.subscription_active.setEnabled(ics and not self._ics_busy())
        self.subscription_info.setVisible(ics)
        self.edit_subscription.setVisible(ics)
        self.edit_subscription.setEnabled(ics and not self._ics_busy())
        self.reveal_subscription.setEnabled(ics)
        self.copy_subscription.setEnabled(ics)
        self._show_subscription_address()
        if ics:
            fetched = calendar.get("ics_last_fetched")
            try:
                fetched = (
                    datetime.fromisoformat(str(fetched)).astimezone().strftime("%Y-%m-%d %H:%M")
                    if fetched
                    else None
                )
            except ValueError:
                fetched = str(fetched)
            status = (
                t("sync_redesign.last_fetched", "마지막 갱신: {time}").format(time=fetched)
                if fetched
                else t("sync_redesign.not_fetched", "아직 일정을 가져오지 않았습니다.")
            )
            if self._ics_busy():
                status = t("sync_redesign.fetch_busy", "구독 갱신 중입니다…") + "\n" + status
            error = subscription_errors(self.app.settings).get(calendar["id"])
            if error:
                status += "\n" + sync_error_message(error)
            self.subscription_info.setText(status)
            overall_auto = bool(
                self.coordinator and self.coordinator.states.get("ics", {}).get("auto", True)
            )
            self.subscription_hint.setText(
                t(
                    "sync_redesign.subscription_paused_hint",
                    "갱신이 중지되어 있습니다. 이미 가져온 일정은 그대로 표시됩니다.",
                )
                if not calendar.get("is_active", 1)
                else t(
                    "sync_redesign.ics_auto_off_hint",
                    "전체 ICS 자동 갱신이 꺼져 있습니다. 아래에서 지금 갱신할 수 있습니다.",
                )
                if not overall_auto
                else t(
                    "sync_redesign.subscription_active_hint",
                    "자동 갱신에 포함됩니다. 일정 표시 여부는 위에서 따로 선택하세요.",
                )
            )
        else:
            self.subscription_info.setText("")
        self.service.setText(
            t("sync_redesign.refresh_subscription", "이 구독 지금 갱신")
            if ics
            else t("sync_redesign.service_settings", "가져올 캘린더 선택 · 연결 설정")
        )
        self.service.setAccessibleName(self.service.text())
        self.service.setEnabled(
            bool(calendar and (self._provider(calendar) or ics))
            and not (ics and (self._ics_busy() or not calendar.get("is_active", 1)))
        )
        self.service.setToolTip(
            t("sync_redesign.resume_before_refresh", "'이 구독 갱신'을 켠 뒤 다시 시도하세요.")
            if ics and not calendar.get("is_active", 1)
            else t(
                "sync_redesign.wait_for_refresh", "진행 중인 구독 갱신이 끝나면 다시 시도하세요."
            )
            if ics and self._ics_busy()
            else ""
        )
        self.remove.setEnabled(
            bool(calendar and calendar.get("type") in {"local", "ics"})
            and not (ics and self._ics_busy())
        )
        self.remove.setVisible(bool(calendar and calendar.get("type") in {"local", "ics"}))
        self.removal_hint.setVisible(bool(calendar and calendar.get("type") in {"local", "ics"}))
        self.removal_hint.setText(
            t(
                "sync_redesign.remove_subscription_hint",
                "구독을 해제해도 원본 캘린더와 가져온 일정은 삭제되지 않습니다.",
            )
            if ics
            else t(
                "sync_redesign.remove_local_hint",
                "캘린더를 제거해도 기존 일정은 로컬 사본으로 남습니다.",
            )
        )
        self.remove.setText(
            t("sync_redesign.unsubscribe", "구독 해제")
            if ics
            else t("sync_redesign.remove_local", "로컬 캘린더 제거")
        )
        self.remove.setAccessibleName(self.remove.text())
        self.service.setVisible(bool(calendar and (self._provider(calendar) or ics)))
        if self._overview and calendar and calendar.get("type") in {"local", "ics"}:
            self.appearance_section.hide()
            self.subscription_section.hide()
            self.edit_subscription.hide()
            self.remove.hide()
            self.removal_hint.hide()
            self.service.setText(
                t("calendar_management_tabs.manage_ics", "ICS 구독 관리")
                if ics
                else t("calendar_management_tabs.manage_local", "로컬 캘린더 관리")
            )
            self.service.setAccessibleName(self.service.text())
            self.service.setToolTip("")
            self.service.setEnabled(True)
            self.service.show()

    def _show_subscription_address(self, *_):
        calendar = self.current()
        raw_url = str((calendar or {}).get("ics_url") or "")
        if not calendar or calendar.get("type") != "ics":
            self.subscription_address.setText("")
            return
        revealed = self.reveal_subscription.isChecked()
        try:
            host = urlsplit(raw_url).hostname or t(
                "sync_redesign.private_address", "비공개 구독 주소"
            )
        except ValueError:
            host = t("sync_redesign.private_address", "비공개 구독 주소")
        address = raw_url if revealed else host + "/•••"
        self.subscription_address.setText(
            t("sync_redesign.subscription_address", "구독 주소: {address}").format(address=address)
        )
        self.reveal_subscription.setText(
            t("sync_redesign.hide_address", "주소 숨기기")
            if revealed
            else t("sync_redesign.show_address", "주소 보기")
        )
        self.reveal_subscription.setAccessibleName(self.reveal_subscription.text())

    def _copy_subscription_address(self):
        calendar = self.current()
        if calendar and calendar.get("type") == "ics":
            QGuiApplication.clipboard().setText(str(calendar.get("ics_url") or ""))
            self.feedback.setText(t("sync_redesign.address_copied", "구독 주소를 복사했습니다."))

    def _ics_busy(self):
        return bool(self.coordinator and self.coordinator.states.get("ics", {}).get("busy"))

    @guard_calendar_action
    def _edit_subscription(self):
        calendar = self.current()
        if not calendar or calendar.get("type") != "ics" or self._ics_busy():
            return
        dialog = IcsSubscriptionDialog(self, calendar=calendar)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._save_subscription(calendar, dialog.subscription_name, dialog.subscription_url)

    @guard_calendar_action
    def _save_subscription(self, calendar, name, url):
        if self._ics_busy():
            self.feedback.setText(sync_error_message("sync_already_running"))
            return False
        try:
            success = calendar_repo.update_ics_subscription(calendar["id"], name, url)
        except ValueError:
            self.feedback.setText(
                t(
                    "sync_unified.invalid_ics",
                    "HTTP · HTTPS · webcal 캘린더 구독 주소를 입력하세요.",
                )
            )
            return False
        except CalendarSyncError as exc:
            if str(exc) != "duplicate_subscription":
                raise
            self.feedback.setText(t("sync_unified.exists", "이미 등록된 캘린더입니다."))
            return False
        self._changed(success)
        if success and calendar.get("is_active", 1) and self.coordinator:
            self.coordinator.sync_ics(force=True, calendar_ids=[calendar["id"]])
        return success

    @guard_calendar_action
    def _subscription_active(self, checked):
        calendar = self.current()
        if calendar and calendar.get("type") == "ics" and not self._ics_busy():
            self._changed(calendar_repo.set_calendar_active(calendar["id"], checked))

    def _changed(self, success):
        self._refresh_feedback_pending = False
        self.feedback.setText(
            t("sync_unified.calendar_saved", "캘린더 설정을 반영했습니다.")
            if success
            else t(
                "sync_unified.calendar_save_failed", "설정을 저장하지 못했습니다. 다시 시도하세요."
            )
        )
        if success:
            from calendar_app.presentation.calendar.month_renderer import (
                invalidate_calendar_meta_cache,
            )
            from calendar_app.presentation.panels.side_panel_renderer import (
                invalidate_panel_calendar_cache,
            )

            invalidate_calendar_meta_cache()
            invalidate_panel_calendar_cache()
            self.app.schedule_panel_refresh(left=True, center=True, right=True)
            if self.coordinator:
                self.coordinator.refresh()
            self.reload()
        else:
            self._selection()

    @guard_calendar_action
    def _visible(self, checked):
        calendar = self.current()
        if calendar:
            self._changed(calendar_repo.set_calendar_visible(calendar["id"], checked))

    @guard_calendar_action
    def _rename(self):
        calendar = self.current()
        if not calendar or calendar.get("type") == "gcal":
            return
        name, ok = QInputDialog.getText(
            self,
            t("sync_unified.rename", "이름 변경"),
            t("sync_unified.calendar_name", "캘린더 이름"),
            text=calendar.get("name") or "",
        )
        if ok and name.strip():
            self._changed(calendar_repo.rename_calendar(calendar["id"], name.strip()))

    @guard_calendar_action
    def _color(self):
        calendar = self.current()
        if calendar:
            color = QColorDialog.getColor(QColor(calendar.get("color") or "#3478c5"), self)
            if color.isValid():
                self._changed(calendar_repo.set_calendar_color(calendar["id"], color.name()))

    @guard_calendar_action
    def _default(self, calendar_id=None):
        calendar = (
            self.current()
            if calendar_id is None
            else next(
                (
                    row
                    for row in (self.coordinator.calendar_rows if self.coordinator else [])
                    if row["id"] == calendar_id
                ),
                None,
            )
        )
        if calendar_repo.can_calendar_be_default(calendar):
            if calendar["id"] == self._effective_default_id:
                self._sync_default_controls()
                return True
            from calendar_app.application.calendar_preferences import set_default_calendar

            success = set_default_calendar(
                calendar["id"], self.app.settings, repository=calendar_repo
            )
            if success and hasattr(self.app, "refresh_gcal_sync_state"):
                self.app.refresh_gcal_sync_state(authenticate_silently=False)
            self._changed(success)
            if success:
                self.feedback.setText(
                    t(
                        "calendar_list_default.saved",
                        "새 일정은 ‘{name}’ 캘린더에 기본 저장됩니다.",
                        name=str(calendar.get("name") or calendar["id"]),
                    )
                )
            return success
        self._sync_default_controls()
        return False

    @guard_calendar_action
    def _add_local(self):
        name, ok = QInputDialog.getText(
            self,
            t("sync_unified.add_local", "로컬 캘린더 추가"),
            t("sync_unified.calendar_name", "캘린더 이름"),
        )
        if ok and name.strip():
            key = calendar_repo.make_local_id(name.strip())
            if calendar_repo.get_calendar(key):
                self.feedback.setText(t("sync_unified.exists", "이미 등록된 캘린더입니다."))
                return
            success = calendar_repo.upsert_calendar(key, "local", name.strip())
            self._changed(success)
            if success:
                self.search.clear()
                self.select_calendar(key)

    @guard_calendar_action
    def _add_ics(self):
        if self._ics_busy():
            return
        dialog = IcsSubscriptionDialog(self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._register_ics(dialog.subscription_name, dialog.subscription_url)

    @guard_calendar_action
    def _register_ics(self, name, url):
        if self._ics_busy():
            self.feedback.setText(sync_error_message("sync_already_running"))
            return False
        url = normalize_subscription_url(url)
        for calendar in calendar_repo.list_calendars(include_inactive=True):
            if calendar.get("type") != "ics":
                continue
            try:
                existing_url = normalize_subscription_url(calendar.get("ics_url") or "")
            except ValueError:
                continue
            if existing_url == url:
                self.feedback.setText(t("sync_unified.exists", "이미 등록된 캘린더입니다."))
                return False
        key = calendar_repo.make_ics_id(url)
        # An edited subscription retains its ID; re-adding its old URL must create a new row.
        if calendar_repo.get_calendar(key):
            key += "::" + uuid4().hex
        success = calendar_repo.upsert_calendar(key, "ics", name.strip(), ics_url=url)
        self._changed(success)
        if success:
            self.show_provider("ics")
            for index in range(self.calendars.count()):
                if self.calendars.item(index).data(Qt.ItemDataRole.UserRole)["id"] == key:
                    self.calendars.setCurrentRow(index)
                    break
            if self.coordinator:
                self.coordinator.sync_ics(force=True, calendar_ids=[key])
        return success

    def _service(self):
        calendar = self.current()
        if calendar:
            if self._overview and calendar.get("type") in {"local", "ics"}:
                self.open_service(calendar["type"], "calendars", calendar_id=calendar["id"])
                return
            if calendar.get("type") == "ics":
                if self.coordinator:
                    started = self.coordinator.sync_ics(force=True, calendar_ids=[calendar["id"]])
                    self._refresh_feedback_pending = bool(started)
                    self.feedback.setText(
                        t("sync_unified.refresh_started", "선택한 구독을 새로고침하고 있습니다.")
                        if started
                        else t(
                            "sync_unified.sync_not_started",
                            "동기화를 시작하지 못했습니다. 연결 상태와 진행 중인 작업을 확인하세요.",
                        )
                    )
                return
            self.open_service(self._provider(calendar) or "ics", "calendars")

    @guard_calendar_action
    def _remove(self):
        calendar = self.current()
        if not calendar or calendar.get("type") not in {"local", "ics"}:
            return
        if calendar.get("type") == "ics" and self._ics_busy():
            return
        if (
            QMessageBox.question(
                self,
                t("sync_redesign.unsubscribe", "구독 해제")
                if calendar.get("type") == "ics"
                else t("sync_redesign.remove_local", "로컬 캘린더 제거"),
                t(
                    "sync_redesign.unsubscribe_confirm",
                    "'{name}' 구독을 해제할까요? 갱신을 중지하고 구독 목록에서 제거합니다. 이미 가져온 일정은 로컬 사본으로 남으며 원본 캘린더는 삭제되지 않습니다.",
                ).format(name=calendar.get("name") or calendar["id"])
                if calendar.get("type") == "ics"
                else t(
                    "sync_redesign.remove_local_confirm",
                    "'{name}' 캘린더를 제거할까요? 기존 일정은 로컬 사본으로 남습니다.",
                ).format(name=calendar.get("name") or calendar["id"]),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        if calendar.get("type") != "ics" or not self._ics_busy():
            success = calendar_repo.delete_calendar(calendar["id"])
            if success and calendar.get("type") == "ics":
                errors = subscription_errors(self.app.settings)
                errors.pop(calendar["id"], None)
                self.app.settings.setValue("sync_ics_error_codes", errors)
                self.app.settings.setValue("sync_ics_failed_ids", sorted(errors))
            self._changed(success)
