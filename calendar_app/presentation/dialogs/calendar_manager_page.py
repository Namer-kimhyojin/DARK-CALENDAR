# -*- coding: utf-8 -*-
"""Service-neutral local presentation settings and calendar creation."""

from urllib.parse import urlparse

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.db import calendar_repo
from calendar_app.infrastructure.i18n import t


class CalendarManagerPage(QWidget):
    def __init__(self, app, coordinator, open_service):
        super().__init__()
        self.app, self.coordinator, self.open_service = app, coordinator, open_service
        root = QVBoxLayout(self)
        note = QLabel(
            t(
                "sync_unified.calendar_hint",
                "모든 캘린더의 표시·색상·기본 저장 대상을 함께 관리합니다. 원격 동기화 선택은 해당 서비스 설정에서 변경하세요.",
            )
        )
        note.setWordWrap(True)
        root.addWidget(note)
        row = QHBoxLayout()
        for label, callback in [
            (t("sync_unified.add_local", "로컬 캘린더 추가"), self._add_local),
            (t("sync_unified.add_ics", "ICS 구독 추가"), self._add_ics),
        ]:
            button = QPushButton(label)
            button.setObjectName("ghost_btn")
            button.clicked.connect(callback)
            row.addWidget(button)
        root.addLayout(row)
        self.calendars = QListWidget()
        self.calendars.setAccessibleName(t("sync_unified.calendars", "전체 캘린더"))
        self.calendars.currentItemChanged.connect(self._selection)
        root.addWidget(self.calendars, 1)
        self.visible = QCheckBox(t("sync_unified.show_calendar", "일정 화면에 표시"))
        self.visible.toggled.connect(self._visible)
        root.addWidget(self.visible)
        self.subscription_active = QCheckBox(
            t("sync_unified.subscription_active", "이 ICS 구독 동기화")
        )
        self.subscription_active.toggled.connect(self._subscription_active)
        root.addWidget(self.subscription_active)
        self.subscription_info = QLabel()
        self.subscription_info.setWordWrap(True)
        self.subscription_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.subscription_info)
        row = QHBoxLayout()
        self.rename = QPushButton(t("sync_unified.rename", "이름 변경"))
        self.color = QPushButton(t("sync_unified.color", "색상 변경"))
        self.default = QPushButton(t("sync_unified.default", "기본 저장 대상으로"))
        for button, callback in (
            (self.rename, self._rename),
            (self.color, self._color),
            (self.default, self._default),
        ):
            button.setObjectName("ghost_btn")
            button.clicked.connect(callback)
            row.addWidget(button)
        root.addLayout(row)
        row = QHBoxLayout()
        self.service = QPushButton(t("sync_unified.service_settings", "서비스 선택·세부 설정"))
        self.service.clicked.connect(self._service)
        row.addWidget(self.service)
        self.remove = QPushButton(t("sync_unified.remove_calendar", "로컬 목록에서 제거"))
        self.remove.setObjectName("danger_btn")
        self.remove.clicked.connect(self._remove)
        row.addWidget(self.remove)
        root.addLayout(row)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        root.addWidget(self.feedback)
        self.reload()

    def current(self):
        item = self.calendars.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def reload(self):
        selected = (self.current() or {}).get("id")
        self.calendars.clear()
        rows = self.coordinator.calendar_rows if self.coordinator else []
        for calendar in rows:
            readonly = calendar_repo.is_calendar_row_read_only(calendar)
            label = calendar.get("name") or calendar["id"]
            label += " · " + self._source_label(calendar)
            if readonly:
                label += " · " + t("outlook.read_only", "읽기 전용")
            if calendar.get("is_default"):
                label += " · " + t("sync_unified.default_marker", "기본")
            if not calendar.get("is_active", 1):
                label += " · " + t("sync_unified.inactive", "동기화 선택 해제")
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, calendar)
            item.setToolTip(label)
            self.calendars.addItem(item)
            if calendar["id"] == selected:
                self.calendars.setCurrentItem(item)
        self._selection()

    def _provider(self, calendar):
        if self.coordinator:
            return self.coordinator.calendar_providers.get(calendar["id"])
        return None

    def _source_label(self, calendar):
        from calendar_app.presentation.main_window.calendar_sync_coordinator import provider_name

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
        calendar = self.current()
        for button in (self.visible, self.rename, self.color, self.default, self.remove):
            button.setEnabled(bool(calendar))
        self.service.setEnabled(
            bool(calendar and (self._provider(calendar) or calendar.get("type") == "ics"))
        )
        self.visible.blockSignals(True)
        self.visible.setChecked(bool(calendar and calendar.get("is_visible", 1)))
        self.visible.blockSignals(False)
        self.default.setEnabled(
            bool(
                calendar
                and calendar.get("is_active", 1)
                and not calendar_repo.is_calendar_row_read_only(calendar)
            )
        )
        self.rename.setEnabled(bool(calendar and calendar.get("type") != "gcal"))
        ics = bool(calendar and calendar.get("type") == "ics")
        self.subscription_active.setVisible(ics)
        self.subscription_active.blockSignals(True)
        self.subscription_active.setChecked(bool(ics and calendar.get("is_active", 1)))
        self.subscription_active.blockSignals(False)
        self.subscription_active.setEnabled(ics and not self._ics_busy())
        self.subscription_info.setVisible(ics)
        self.subscription_info.setText((calendar.get("ics_url") or "") if ics else "")
        if ics and calendar["id"] in self.app.settings.value("sync_ics_failed_ids", []):
            self.subscription_info.setText(
                self.subscription_info.text()
                + "\n"
                + t(
                    "sync_ui.ics_fetch",
                    "구독을 갱신하지 못했습니다. 주소와 인터넷 연결을 확인하고 다시 동기화하세요.",
                )
            )
        self.service.setText(
            t("sync_unified.refresh_subscription", "ICS 구독 다시 동기화")
            if ics
            else t("sync_unified.service_settings", "서비스 선택·세부 설정")
        )
        self.service.setEnabled(
            bool(calendar and (self._provider(calendar) or ics))
            and not (ics and (self._ics_busy() or not calendar.get("is_active", 1)))
        )
        self.remove.setEnabled(
            bool(calendar and calendar.get("type") in {"local", "ics"})
            and not (ics and self._ics_busy())
        )

    def _ics_busy(self):
        return bool(self.coordinator and self.coordinator.states.get("ics", {}).get("busy"))

    def _subscription_active(self, checked):
        calendar = self.current()
        if calendar and calendar.get("type") == "ics" and not self._ics_busy():
            self._changed(calendar_repo.set_calendar_active(calendar["id"], checked))

    def _changed(self, success):
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

    def _visible(self, checked):
        calendar = self.current()
        if calendar:
            self._changed(calendar_repo.set_calendar_visible(calendar["id"], checked))

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

    def _color(self):
        calendar = self.current()
        if calendar:
            color = QColorDialog.getColor(QColor(calendar.get("color") or "#3478c5"), self)
            if color.isValid():
                self._changed(calendar_repo.set_calendar_color(calendar["id"], color.name()))

    def _default(self):
        calendar = self.current()
        if (
            calendar
            and calendar.get("is_active", 1)
            and not calendar_repo.is_calendar_row_read_only(calendar)
        ):
            self._changed(calendar_repo.set_calendar_default(calendar["id"]))

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
            self._changed(calendar_repo.upsert_calendar(key, "local", name.strip()))

    def _add_ics(self):
        url, ok = QInputDialog.getText(
            self,
            t("sync_unified.add_ics", "ICS 구독 추가"),
            t("sync_unified.ics_url", "캘린더 구독 URL"),
        )
        if not ok:
            return
        url = url.strip()
        try:
            parsed = urlparse(url)
            valid = (
                parsed.scheme in {"https", "http"}
                and parsed.hostname
                and not parsed.username
                and not parsed.password
            )
        except ValueError:
            valid = False
        if not valid:
            self.feedback.setText(
                t("sync_unified.invalid_ics", "HTTP 또는 HTTPS 캘린더 구독 주소를 입력하세요.")
            )
            return
        key = calendar_repo.make_ics_id(url)
        if calendar_repo.get_calendar(key):
            self.feedback.setText(t("sync_unified.exists", "이미 등록된 캘린더입니다."))
            return
        name, ok = QInputDialog.getText(
            self,
            t("sync_unified.add_ics", "ICS 구독 추가"),
            t("sync_unified.calendar_name", "캘린더 이름"),
        )
        if ok and name.strip():
            self._changed(calendar_repo.upsert_calendar(key, "ics", name.strip(), ics_url=url))
            if self.coordinator:
                self.coordinator.sync("ics")

    def _service(self):
        calendar = self.current()
        if calendar:
            if calendar.get("type") == "ics":
                if self.coordinator:
                    self.coordinator.sync("ics")
                return
            self.open_service(self._provider(calendar) or "ics", "calendars")

    def _remove(self):
        calendar = self.current()
        if not calendar or calendar.get("type") not in {"local", "ics"}:
            return
        if calendar.get("type") == "ics" and self._ics_busy():
            return
        if (
            QMessageBox.question(
                self,
                t("sync_unified.remove_calendar", "로컬 목록에서 제거"),
                t(
                    "sync_unified.remove_confirm",
                    "이 캘린더를 목록에서 제거할까요? 기존 일정은 로컬 사본으로 보존하며 서비스 원본은 삭제하지 않습니다.",
                ),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        if calendar.get("type") != "ics" or not self._ics_busy():
            self._changed(calendar_repo.delete_calendar(calendar["id"]))
