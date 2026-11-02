# -*- coding: utf-8 -*-
"""Staged motion settings and ordered weekday/time workspace rules."""

from copy import deepcopy

from PyQt6.QtCore import QTime
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLayout,
    QListWidget,
    QScrollArea,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from calendar_app.domain.widget_workspace import validate_rule
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_styles import (
    build_dialog_footer,
)
from calendar_app.presentation.widgets.widget_management_ui import (
    apply_hub_dialog_style,
    hub_button,
    hub_label,
)


def weekday_labels():
    return [
        t("widget_studio.day_" + key, text)
        for key, text in (
            ("mon", "월"),
            ("tue", "화"),
            ("wed", "수"),
            ("thu", "목"),
            ("fri", "금"),
            ("sat", "토"),
            ("sun", "일"),
        )
    ]


class WorkspaceRuleDialog(QDialog):
    def __init__(self, profiles, rule=None, parent=None):
        super().__init__(parent)
        self.profiles, self.rule = profiles, None
        self.setWindowTitle(t("widget_studio.rule_title", "자동 전환 규칙"))
        apply_hub_dialog_style(self, parent, minimum_width=480, size=(560, 330))
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.profile = QComboBox()
        for profile in profiles:
            self.profile.addItem(profile["name"], profile["id"])
        form.addRow(t("widget_studio.workspace", "작업 공간"), self.profile)
        self.start, self.end = QTimeEdit(QTime(9, 0)), QTimeEdit(QTime(18, 0))
        for edit in (self.start, self.end):
            edit.setDisplayFormat("HH:mm")
        form.addRow(t("widget_studio.start", "시작"), self.start)
        form.addRow(t("widget_studio.end", "종료"), self.end)
        root.addLayout(form)
        weekdays = QHBoxLayout()
        self.days = []
        for index, text in enumerate(weekday_labels()):
            check = QCheckBox(text)
            check.setChecked(index < 5)
            self.days.append(check)
            weekdays.addWidget(check)
        root.addLayout(weekdays)
        self.enabled = QCheckBox(t("widget_studio.rule_enabled", "이 규칙 사용"))
        self.enabled.setChecked(True)
        root.addWidget(self.enabled)
        root.addWidget(
            hub_label(
                t(
                    "widget_studio.overnight_help",
                    "종료가 시작보다 이르면 다음 날까지 적용합니다. 같은 시간은 선택한 요일 하루 전체에 적용합니다.",
                )
            )
        )
        self.feedback = hub_label("")
        root.addWidget(self.feedback)
        footer, ok, cancel = build_dialog_footer(
            ok_label=t("common.apply", "적용"), cancel_label=t("common.cancel", "취소")
        )
        ok.clicked.connect(self._accept_rule)
        cancel.clicked.connect(self.reject)
        root.addLayout(footer)
        if rule:
            self.profile.setCurrentIndex(max(0, self.profile.findData(rule["profile"])))
            self.start.setTime(QTime.fromString(rule["start"], "HH:mm"))
            self.end.setTime(QTime.fromString(rule["end"], "HH:mm"))
            self.enabled.setChecked(rule["enabled"])
            for day, check in enumerate(self.days, 1):
                check.setChecked(day in rule["days"])

    def _accept_rule(self):
        try:
            self.rule = validate_rule(
                {
                    "profile": self.profile.currentData(),
                    "days": [day for day, check in enumerate(self.days, 1) if check.isChecked()],
                    "start": self.start.time().toString("HH:mm"),
                    "end": self.end.time().toString("HH:mm"),
                    "enabled": self.enabled.isChecked(),
                },
                {p["id"] for p in self.profiles},
            )
        except ValueError:
            self.feedback.setText(
                t("widget_studio.rule_invalid", "작업 공간과 적용 요일을 선택하세요.")
            )
            return
        self.accept()


class WidgetWorkspaceOptionsDialog(QDialog):
    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self.rules = deepcopy(service.state["rules"])
        self.setWindowTitle(t("widget_studio.options", "자동 전환·움직임 설정"))
        apply_hub_dialog_style(self, parent, minimum_width=580, size=(720, 620))
        outer = QVBoxLayout(self)
        self.controls_scroll = QScrollArea()
        self.controls_scroll.setObjectName("hubDialogScroll")
        self.controls_scroll.viewport().setObjectName("hubDialogViewport")
        self.controls_scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("hubDialogBody")
        root = QVBoxLayout(content)
        root.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        self.controls_scroll.setWidget(content)
        outer.addWidget(self.controls_scroll, 1)
        motion_group = QGroupBox(t("widget_studio.motion_title", "움직임과 절전"))
        form = QFormLayout(motion_group)
        self.motion = QComboBox()
        for key, text in (
            ("rich", t("widget_studio.motion_rich", "풍부하게")),
            ("balanced", t("widget_studio.motion_balanced", "균형")),
            ("static", t("widget_studio.motion_static", "정적")),
        ):
            self.motion.addItem(text, key)
        self.motion.setCurrentIndex(self.motion.findData(service.state["options"]["motion"]))
        form.addRow(t("widget_studio.motion_mode", "애니메이션"), self.motion)
        self.fullscreen = QCheckBox(
            t("widget_studio.pause_fullscreen", "다른 앱 전체 화면 사용 중 움직임 일시정지")
        )
        self.fullscreen.setChecked(service.state["options"]["pause_fullscreen"])
        form.addRow(self.fullscreen)
        form.addRow(
            hub_label(
                t(
                    "widget_studio.motion_help",
                    "시계·타이머 기능은 계속 동작합니다. 위젯별 움직임 끔과 Windows 애니메이션·절전 설정을 함께 따릅니다.",
                )
            )
        )
        root.addWidget(motion_group)
        automation = QGroupBox(t("widget_studio.automation", "상황별 자동 전환"))
        layout = QVBoxLayout(automation)
        self.automatic = QCheckBox(
            t("widget_studio.automatic_enabled", "요일·시간에 따라 작업 공간 자동 전환")
        )
        self.automatic.setChecked(service.state["options"]["automatic"])
        layout.addWidget(self.automatic)
        layout.addWidget(
            hub_label(
                t(
                    "widget_studio.automation_help",
                    "위쪽의 일치하는 규칙부터 적용합니다. 직접 작업 공간을 바꾸면 자동 전환을 1시간 쉽니다. 전용 모드 실행 여부는 자동으로 바꾸지 않습니다.",
                )
            )
        )
        self.list = QListWidget()
        self.list.setMinimumHeight(160)
        self.list.itemDoubleClicked.connect(lambda _: self.edit_rule())
        layout.addWidget(self.list, 1)
        buttons = QHBoxLayout()
        add = hub_button(t("widget_studio.rule_add", "규칙 추가"), self.add_rule)
        add.setEnabled(bool(service.state["profiles"]))
        buttons.addWidget(add)
        buttons.addWidget(hub_button(t("widget_studio.rule_edit", "수정"), self.edit_rule))
        buttons.addWidget(hub_button(t("widget_studio.rule_delete", "삭제"), self.remove_rule))
        buttons.addWidget(
            hub_button(t("widget_studio.rule_up", "위로"), lambda: self.move_rule(-1))
        )
        buttons.addWidget(
            hub_button(t("widget_studio.rule_down", "아래로"), lambda: self.move_rule(1))
        )
        layout.addLayout(buttons)
        root.addWidget(automation, 1)
        self.feedback = hub_label("")
        root.addWidget(self.feedback)
        footer, ok, cancel = build_dialog_footer(
            ok_label=t("common.apply", "적용"), cancel_label=t("common.cancel", "취소")
        )
        ok.clicked.connect(self._apply)
        cancel.clicked.connect(self.reject)
        outer.addLayout(footer)
        self._render()

    def _render(self):
        selected = self.list.currentRow()
        self.list.clear()
        names = {p["id"]: p["name"] for p in self.service.state["profiles"]}
        labels = weekday_labels()
        for rule in self.rules:
            days = "·".join(labels[day - 1] for day in rule["days"])
            state = "" if rule["enabled"] else t("widget_studio.rule_off", "[사용 안 함] ")
            self.list.addItem(
                f"{state}{names.get(rule['profile'], '')}  ·  {days}  {rule['start']}–{rule['end']}"
            )
        self.list.setCurrentRow(min(max(0, selected), len(self.rules) - 1))

    def add_rule(self):
        dialog = WorkspaceRuleDialog(self.service.state["profiles"], parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.rules.append(dialog.rule)
            self._render()
        dialog.deleteLater()

    def edit_rule(self):
        index = self.list.currentRow()
        if index < 0:
            return
        dialog = WorkspaceRuleDialog(self.service.state["profiles"], self.rules[index], self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.rules[index] = dialog.rule
            self._render()
        dialog.deleteLater()

    def remove_rule(self):
        index = self.list.currentRow()
        if index >= 0:
            self.rules.pop(index)
            self._render()

    def move_rule(self, step):
        index, target = self.list.currentRow(), self.list.currentRow() + step
        if 0 <= index < len(self.rules) and 0 <= target < len(self.rules):
            self.rules[index], self.rules[target] = self.rules[target], self.rules[index]
            self._render()
            self.list.setCurrentRow(target)

    def _apply(self):
        if self.automatic.isChecked() and not self.rules:
            self.feedback.setText(
                t("widget_studio.rule_required", "자동 전환을 사용하려면 규칙을 추가하세요.")
            )
            return
        self.service.configure(
            {
                "motion": self.motion.currentData(),
                "pause_fullscreen": self.fullscreen.isChecked(),
                "automatic": self.automatic.isChecked(),
            },
            self.rules,
        )
        self.accept()
