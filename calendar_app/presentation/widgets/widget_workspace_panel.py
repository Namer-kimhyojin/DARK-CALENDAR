# -*- coding: utf-8 -*-
"""Unified workspace presets, calendar scopes and policy entry points."""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, QSize, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from calendar_app.domain.widget_workspace import CALENDAR_SCOPE_KEY, calendar_scope
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_styles import (
    build_dialog_footer,
)
from calendar_app.presentation.locale_names import calendar_display_name
from calendar_app.presentation.widgets.widget_management_ui import (
    apply_hub_dialog_style,
    hub_button,
    hub_label,
)
from calendar_app.presentation.widgets.widget_workspace_preview import (
    thumbnail_icon,
    workspace_thumbnail,
)


class SaveWorkspaceDialog(QDialog):
    def __init__(self, service, profile=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("widget_studio.save_workspace", "현재 작업 공간 저장"))
        apply_hub_dialog_style(self, parent, minimum_width=500, size=(600, 410))
        root = QVBoxLayout(self)
        root.addWidget(
            hub_label(
                t(
                    "widget_studio.save_help",
                    "위젯 조합·외관·위치와 전용 모드 구성을 함께 저장합니다. 위젯 내용과 실행 중인 타이머는 공유합니다.",
                )
            )
        )
        self.name_edit = QLineEdit(profile["name"] if profile else "")
        self.name_edit.setPlaceholderText(
            t("widget_studio.workspace_name", "예: 업무용, 집중용, 퇴근 후")
        )
        self.name_edit.setAccessibleName(t("widget_studio.workspace", "작업 공간"))
        self.name_edit.setMaxLength(80)
        root.addWidget(self.name_edit)
        self.all_calendars = QCheckBox(
            t("widget_studio.all_calendars", "불러온 모든 일정 캘린더 표시")
        )
        settings = profile["snapshot"]["mode"] if profile else None
        scope = calendar_scope(
            settings.get(CALENDAR_SCOPE_KEY, "")
            if settings is not None
            else service.settings.value(CALENDAR_SCOPE_KEY, "")
        )
        self.all_calendars.setChecked(scope is None)
        root.addWidget(self.all_calendars)
        self.calendar_checks = {}
        scroll = QScrollArea()
        scroll.setObjectName("hubDialogScroll")
        scroll.viewport().setObjectName("hubDialogViewport")
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("hubDialogBody")
        choices = QVBoxLayout(body)
        cache = getattr(service.owner, "_latest_calendar_range_data", {})
        rows = cache.get("rows", []) if isinstance(cache, dict) else []
        calendars = {
            str(row.get("calendar_id") or "local"): str(
                calendar_display_name(row.get("calendar_id"), row.get("calendar_name"))
                or (
                    t("widget_studio.local_calendar", "기본 캘린더")
                    if not row.get("calendar_id")
                    else t("widget_studio.calendar_value", "캘린더 {id}").format(
                        id=row["calendar_id"]
                    )
                )
            )
            for row in rows
            if isinstance(row, dict)
        }
        for cid in scope or []:
            calendars.setdefault(
                cid,
                calendar_display_name(cid, "")
                or t("widget_studio.calendar_value", "캘린더 {id}").format(id=cid),
            )
        for cid, name in calendars.items():
            check = QCheckBox(name)
            check.setChecked(scope is None or cid in scope)
            choices.addWidget(check)
            self.calendar_checks[cid] = check
        choices.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll, 1)
        root.addWidget(
            hub_label(
                t(
                    "widget_studio.calendar_scope_help",
                    "현재 메인 화면에서 불러온 일정 안에서 필터링합니다. 업무·지시는 기존 보기 설정을 따르며, 캘린더를 선택하지 않으면 일정만 숨깁니다.",
                )
            )
        )
        self.feedback = hub_label("")
        root.addWidget(self.feedback)
        self.all_calendars.toggled.connect(lambda checked: scroll.setEnabled(not checked))
        scroll.setEnabled(not self.all_calendars.isChecked())
        footer, save, cancel = build_dialog_footer(
            ok_label=t("common.save", "저장"), cancel_label=t("common.cancel", "취소")
        )
        save.clicked.connect(self._save)
        cancel.clicked.connect(self.reject)
        root.addLayout(footer)
        self.service, self.profile = service, profile

    def _save(self):
        ids = (
            None
            if self.all_calendars.isChecked()
            else [cid for cid, check in self.calendar_checks.items() if check.isChecked()]
        )
        try:
            self.profile_id = self.service.save_profile(
                self.name_edit.text(),
                profile_id=self.profile["id"] if self.profile else None,
                calendar_ids=ids,
                thumbnail=workspace_thumbnail(self.service.manager),
            )
        except ValueError:
            self.feedback.setText(
                t(
                    "widget_studio.invalid_name",
                    "중복되지 않는 이름을 입력하세요. 작업 공간은 최대 30개까지 저장할 수 있습니다.",
                )
            )
            return
        self.accept()


class WidgetWorkspacePanel(QWidget):
    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.setObjectName("hubWorkspaceBody")
        self.service = service
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)
        root.addWidget(
            hub_label(
                t("widget_studio.workspace_title", "하나의 이름으로 바탕화면 전체를 전환하세요"),
                "hubTitle",
            )
        )
        root.addWidget(
            hub_label(
                t(
                    "widget_studio.workspace_help",
                    "업무용·집중용·개인용으로 저장하고 필요할 때 불러오세요. 기존 개별 디자인과 자유 구성을 함께 사용할 수 있습니다.",
                )
            )
        )
        tools = QHBoxLayout()
        tools.addWidget(
            hub_button(
                t("widget_studio.save_new", "현재 상태 새로 저장"), self.save_new, primary=True
            )
        )
        self.update_button = hub_button(
            t("widget_studio.update_profile", "선택 구성 수정"), self.update_profile
        )
        tools.addWidget(self.update_button)
        self.delete_button = hub_button(
            t("widget_studio.delete_profile", "삭제"), self.delete_profile
        )
        tools.addWidget(self.delete_button)
        tools.addStretch()
        root.addLayout(tools)
        self.list = QListWidget()
        self.list.setObjectName("studioProfiles")
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setIconSize(QSize(220, 110))
        self.list.setGridSize(QSize(250, 155))
        self.list.setWordWrap(True)
        self.list.currentItemChanged.connect(lambda *_: self._selection())
        root.addWidget(self.list, 1)
        self.summary = hub_label("")
        root.addWidget(self.summary)
        actions = QHBoxLayout()
        self.apply_button = hub_button(
            t("widget_studio.apply_workspace", "선택 작업 공간 적용"),
            self.apply_profile,
            primary=True,
        )
        self.open_button = hub_button(
            t("widget_studio.apply_open", "적용하고 저장 모드로 열기"),
            lambda: self.apply_profile(open_mode=True),
        )
        self.undo_button = hub_button(
            t("widget_studio.undo", "최근 적용 되돌리기"), self.service.undo
        )
        actions.addWidget(self.apply_button)
        actions.addWidget(self.open_button)
        actions.addWidget(self.undo_button)
        actions.addStretch()
        root.addLayout(actions)
        root.addWidget(
            hub_label(
                t(
                    "widget_studio.apply_help",
                    "적용하면 저장하지 않은 위젯은 숨깁니다. 삭제된 위젯은 복원하지 않으며, 일반 적용은 현재 모드 실행 여부를 유지합니다.",
                )
            )
        )
        bottom = QHBoxLayout()
        bottom.addWidget(
            hub_button(t("widget_studio.options", "자동 전환·움직임 설정"), self.open_options)
        )
        self.runtime_status = hub_label("")
        bottom.addWidget(self.runtime_status, 1)
        root.addLayout(bottom)
        self.feedback = hub_label("")
        root.addWidget(self.feedback)
        self._initialized = False
        self.service.changed.connect(self.refresh)
        self.refresh()

    def selected_profile(self):
        item = self.list.currentItem()
        pid = item.data(Qt.ItemDataRole.UserRole) if item else None
        return next((p for p in self.service.state["profiles"] if p["id"] == pid), None)

    def refresh(self):
        if self._initialized and not self.isVisible():
            return
        self._initialized = True
        current = self.selected_profile()
        selected_id = current["id"] if current else None
        self.list.blockSignals(True)
        self.list.clear()
        chosen = None
        for profile in self.service.state["profiles"]:
            item = QListWidgetItem(
                profile["name"]
                + (
                    " · " + t("widget_studio.applied", "적용됨")
                    if profile["id"] == self.service.state["active"]
                    else ""
                )
            )
            item.setData(Qt.ItemDataRole.UserRole, profile["id"])
            item.setSizeHint(QSize(244, 149))
            item.setToolTip(profile["name"])
            if profile["thumbnail"]:
                pixmap = QPixmap()
                pixmap.loadFromData(
                    QByteArray.fromBase64(profile["thumbnail"].encode("utf-8", errors="strict")),
                )
                item.setIcon(thumbnail_icon(pixmap))
            self.list.addItem(item)
            if profile["id"] == selected_id:
                chosen = item
        self.list.setCurrentItem(chosen or (self.list.item(0) if self.list.count() else None))
        self.list.blockSignals(False)
        self._selection()
        self.undo_button.setEnabled(self.service._undo is not None)
        options = self.service.state["options"]
        automatic = (
            t("widget_studio.auto_on", "자동 전환 사용")
            if options["automatic"]
            else t("widget_studio.auto_off", "수동 전환")
        )
        motion = {
            "rich": t("widget_studio.motion_rich", "풍부하게"),
            "balanced": t("widget_studio.motion_balanced", "균형"),
            "static": t("widget_studio.motion_static", "정적"),
        }[options["motion"]]
        self.runtime_status.setText(automatic + " · " + motion)
        if self.service.last_error:
            self.feedback.setText(
                t(
                    "widget_studio.auto_failed",
                    "자동 전환하지 못했습니다. 저장한 작업 공간을 확인하세요.",
                )
            )
        if self.service.load_error:
            self.feedback.setText(
                t(
                    "widget_studio.load_error",
                    "저장한 작업 공간을 읽지 못했습니다. 원본 설정을 보존했습니다.",
                )
            )

    def _selection(self):
        profile = self.selected_profile()
        for button in (self.update_button, self.delete_button, self.apply_button, self.open_button):
            button.setEnabled(profile is not None)
        if profile:
            count = sum(entry["enabled"] for entry in profile["snapshot"]["widgets"])
            self.summary.setText(
                t(
                    "widget_studio.profile_summary", "표시 위젯 {count}개 · 저장한 모드 {mode}"
                ).format(
                    count=count,
                    mode=t("widget_hub.mode_tab", "위젯 전용 모드")
                    if profile["snapshot"]["mode_active"]
                    else t("widget_studio.main_mode", "메인 화면"),
                )
            )
        else:
            self.summary.setText(
                t(
                    "widget_studio.no_profiles",
                    "원하는 위젯을 배치한 뒤 ‘현재 상태 새로 저장’을 눌러 시작하세요.",
                )
            )

    def save_new(self):
        self._save(None)

    def update_profile(self):
        profile = self.selected_profile()
        if profile:
            self._save(profile)

    def _save(self, profile):
        dialog = SaveWorkspaceDialog(self.service, profile, self.window())
        dialog.exec()
        dialog.deleteLater()

    def apply_profile(self, *, open_mode=False):
        profile = self.selected_profile()
        if profile is None:
            return
        try:
            missing = self.service.apply_profile(profile["id"], open_mode=open_mode)
            self.feedback.setText(
                t(
                    "widget_studio.profile_applied",
                    "작업 공간을 적용했습니다. 삭제된 위젯 {count}개는 제외했습니다.",
                ).format(count=len(missing))
            )
        except (ValueError, RuntimeError, StopIteration):
            self.feedback.setText(
                t("widget_studio.apply_failed", "적용하지 못해 이전 작업 공간으로 복원했습니다.")
            )
        self.window().show()
        self.window().raise_()

    def delete_profile(self):
        profile = self.selected_profile()
        if (
            profile
            and QMessageBox.question(
                self,
                t("widget_studio.delete_profile", "삭제"),
                t(
                    "widget_studio.delete_confirm",
                    "이 작업 공간과 연결된 자동 전환 규칙을 삭제할까요? 실제 위젯은 유지합니다.",
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.service.remove_profile(profile["id"])

    def open_options(self):
        from calendar_app.presentation.dialogs.widget_workspace_options_dialog import (
            WidgetWorkspaceOptionsDialog,
        )

        dialog = WidgetWorkspaceOptionsDialog(self.service, self.window())
        dialog.exec()
        dialog.deleteLater()
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
