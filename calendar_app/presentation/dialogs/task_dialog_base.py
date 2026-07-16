# -*- coding: utf-8 -*-
"""Shared base class for unified task add/modify dialogs."""

from PyQt6.QtCore import QDate, QDateTime, Qt, QTime
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from calendar_app.domain.policies import routine_policy
from calendar_app.domain.task_constants import (
    PRIORITY_COMBO_ITEMS,
    STATUS_COMBO_ITEMS,
)
from calendar_app.infrastructure.db import checklist_template_repo
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.color_swatch_widget import GoogleColorSwatch
from calendar_app.presentation.dialogs.dialog_editor_styles import (
    build_editor_hint_style,
    build_editor_text_style,
)
from calendar_app.presentation.dialogs.dialog_styles import (
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)
from calendar_app.presentation.dialogs.routine_recurrence_wizard import (
    build_recurrence_rule as build_routine_recurrence_rule,
)
from calendar_app.presentation.dialogs.routine_recurrence_wizard import (
    cycle_slot_options,
    default_recurrence_config,
    normalize_recurrence_config,
    parse_recurrence_rule,
    recurrence_summary,
)
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.icon_map import strip_leading_emoji as _se


class BaseTaskDialog(QDialog):
    """Shared base for UnifiedTaskDialog and UnifiedModifyTaskDialog."""

    # ── Common state initializer ──────────────────────────────────────────
    def _init_common_state(self):
        self._auto_end_duration_mins = 60
        self._updating_end_controls = False
        self._routine_cycle_type = "monthly"
        self._routine_recurrence = None
        self._dialog_ui_tokens = None
        self._dialog_metric_tokens = None
        self.start_date = None
        self.start_time = None
        self.end_date = None
        self.end_time = None
        self.auto_end_check = None

    def _ui_tokens(self):
        if self._dialog_ui_tokens is None:
            self._dialog_ui_tokens = get_dialog_theme_tokens()
        return self._dialog_ui_tokens

    def _dialog_metrics(self):
        if self._dialog_metric_tokens is None:
            self._dialog_metric_tokens = get_dialog_metric_tokens(apply_overrides=True)
        return self._dialog_metric_tokens

    def _accent_rgba(self, alpha: float) -> str:
        accent = QColor(self._ui_tokens().get("accent", "#4da6ff"))
        a = max(0.0, min(1.0, float(alpha)))
        return f"rgba({accent.red()},{accent.green()},{accent.blue()},{a:.2f})"

    # ── Layout helpers ────────────────────────────────────────────────────
    def _create_section(self, title, icon=None):
        """QGroupBox 대신 경량 헤더(구분선+레이블) + 내용 컨테이너를 반환."""
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 4, 0, 2)
        outer.setSpacing(0)

        # 헤더 행: 아이콘+제목 레이블 + 우측으로 늘어나는 수평선
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 4)
        header_row.setSpacing(6)

        if icon:
            icon_lbl = QLabel()
            icon_lbl.setPixmap(_ic(icon).pixmap(14, 14))
            header_row.addWidget(icon_lbl)
        lbl = QLabel(title)
        lbl.setObjectName("TaskDialogSectionLabel")
        header_row.addWidget(lbl)

        line = QFrame()
        line.setObjectName("TaskDialogSectionLine")
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header_row.addWidget(line, 1)
        outer.addLayout(header_row)

        # 내용 영역
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(7)
        layout.setContentsMargins(4, 4, 4, 6)
        outer.addWidget(content)

        return container, layout

    def _set_editor_height(self, *widgets, min_height=34):
        for widget in widgets:
            if widget is not None:
                widget.setMinimumHeight(min_height)
                widget.setMaximumHeight(min_height + 4)

    def _create_additional_info_section(self):
        context_group, context_layout = self._create_section(
            t("dialog.task.additional_info"), icon=ICON.PERSON
        )
        context_layout.setSpacing(8)

        for lbl_key, placeholder_key, attr in [
            (t("dialog.task.assignee"), t("dialog.task.assignee_placeholder"), "assignee_edit"),
            (t("dialog.task.location"), t("dialog.task.location_placeholder"), "location_edit"),
        ]:
            row = QHBoxLayout()
            row.setSpacing(10)
            lbl = QLabel(lbl_key)
            lbl.setFixedWidth(52)
            edit = QLineEdit()
            edit.setPlaceholderText(placeholder_key)
            self._set_editor_height(edit)
            setattr(self, attr, edit)
            row.addWidget(lbl)
            row.addWidget(edit)
            context_layout.addLayout(row)
        return context_group

    def _create_ops_section(self):
        ops_group, ops_inner = self._create_section(
            t("dialog.task.ops_section"), icon=ICON.SETTINGS
        )
        ops_inner.setSpacing(10)

        # 우선순위 + 상태 가로 배치
        combo_row = QHBoxLayout()
        combo_row.setSpacing(20)

        for lbl_key, attr, items, default_data in [
            (t("dialog.task.priority"), "priority_combo", PRIORITY_COMBO_ITEMS, None),
            (t("dialog.task.status"), "status_combo", STATUS_COMBO_ITEMS, "in_progress"),
        ]:
            col = QVBoxLayout()
            col.setSpacing(5)
            col.addWidget(QLabel(lbl_key))
            combo = QComboBox()
            for label, value in items:
                combo.addItem(label, value)
            if default_data:
                idx = combo.findData(default_data)
                combo.setCurrentIndex(idx if idx >= 0 else 0)
            self._set_editor_height(combo)
            combo.setFixedWidth(155)
            col.addWidget(combo)
            setattr(self, attr, combo)
            combo_row.addLayout(col)

        combo_row.addStretch()
        ops_inner.addLayout(combo_row)

        # 색상 태그
        color_column = QVBoxLayout()
        color_column.setSpacing(4)
        color_lbl = QLabel(t("dialog.task.color_tag", "색상 태그"))
        color_lbl.setWordWrap(True)
        color_column.addWidget(color_lbl)
        self.color_swatch = GoogleColorSwatch(
            tokens=self._ui_tokens(),
            metrics=self._dialog_metrics(),
        )
        self.color_swatch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        color_column.addWidget(self.color_swatch)
        ops_inner.addLayout(color_column)
        return ops_group

    def _make_quick_btn(self, label, accent=False):
        btn = QPushButton(label)
        btn.setObjectName("ghost_btn")
        btn.setMinimumHeight(34)
        btn.setMaximumHeight(34)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setProperty("accentVariant", bool(accent))
        return btn

    def _build_quick_action_row(self, actions):
        row = QHBoxLayout()
        row.setSpacing(4)
        for label, handler in actions:
            btn = self._make_quick_btn(label)
            btn.clicked.connect(handler)
            row.addWidget(btn)
        row.addStretch()
        return row

    def _build_end_adjust_row(self):
        """종료 시간 조정 버튼 행 (수정 다이얼로그에서 사용)."""
        row = QHBoxLayout()
        row.setSpacing(4)
        for label, minutes in [
            (f"+1{t('dialog.task.unit_hour')}", 60),
            (f"+3{t('dialog.task.unit_hour')}", 180),
            (f"+5{t('dialog.task.unit_hour')}", 300),
            (f"+1{t('dialog.task.unit_day')}", 1440),
            (f"+2{t('dialog.task.unit_day')}", 2880),
            (f"+3{t('dialog.task.unit_day')}", 4320),
            (f"+5{t('dialog.task.unit_day')}", 7200),
        ]:
            btn = self._make_quick_btn(label)
            btn.clicked.connect(lambda _=False, mins=minutes: self._set_end_from_start_offset(mins))
            row.addWidget(btn)
        row.addStretch()
        row.addWidget(self.auto_end_check)
        return row

    # ── DateTime helpers ──────────────────────────────────────────────────
    def _date_time_value(self, date_edit, time_edit):
        return QDateTime(
            date_edit.date(), QTime(time_edit.time().hour(), time_edit.time().minute())
        )

    def _set_date_time_value(self, date_edit, time_edit, value):
        old_date = date_edit.blockSignals(True)
        old_time = time_edit.blockSignals(True)
        date_edit.setDate(value.date())
        time_edit.setTime(QTime(value.time().hour(), value.time().minute()))
        time_edit.blockSignals(old_time)
        date_edit.blockSignals(old_date)

    def _update_duration_summary(self):
        if not hasattr(self, "duration_summary_label"):
            return
        tokens = self._ui_tokens()
        if (
            not hasattr(self, "end_date")
            or self.end_date is None
            or not hasattr(self, "end_time")
            or self.end_time is None
        ):
            self.duration_summary_label.setText(t("dialog.task.managed_by_base"))
            self.duration_summary_label.setStyleSheet(
                build_editor_text_style(tokens, tone="muted", font_px=14)
            )
            return
        start_value = self._date_time_value(self.start_date, self.start_time)
        end_value = self._date_time_value(self.end_date, self.end_time)
        secs = start_value.secsTo(end_value)
        if secs < 0:
            self.duration_summary_label.setText(t("dialog.task.end_before_start"))
            self.duration_summary_label.setStyleSheet(
                build_editor_text_style(tokens, tone="danger", font_px=14)
            )
            return
        minutes = secs // 60
        hours, remain = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        parts = []
        if days:
            parts.append(f"{days}{t('dialog.task.unit_day')}")
        if hours:
            parts.append(f"{hours}{t('dialog.task.unit_hour')}")
        if remain or not parts:
            parts.append(f"{remain}{t('dialog.task.unit_min')}")
        self.duration_summary_label.setText(f"{t('dialog.task.duration_prefix')} {' '.join(parts)}")
        self.duration_summary_label.setStyleSheet(
            build_editor_text_style(tokens, tone="accent", font_px=14, weight=600)
        )

    def _update_alarm_summary(self):
        if not hasattr(self, "alarm_summary_value"):
            return
        if not hasattr(self, "alarm_checks"):
            self.alarm_summary_value.setText(t("dialog.task.no_alarm"))
            return
        selected = [
            checkbox.text()
            for _mins, checkbox in sorted(
                self.alarm_checks.items(), key=lambda item: item[0], reverse=True
            )
            if checkbox.isChecked()
        ]
        self.alarm_summary_value.setText(
            ", ".join(selected) if selected else t("dialog.task.no_alarm")
        )

    def _apply_start_quick_action(self, action):
        current = self._date_time_value(self.start_date, self.start_time)
        if action == "today":
            value = QDateTime(QDate.currentDate(), current.time())
        elif action == "tomorrow":
            value = QDateTime(QDate.currentDate().addDays(1), current.time())
        elif action == "week_1":
            value = QDateTime(QDate.currentDate().addDays(7), current.time())
        elif action == "week_2":
            value = QDateTime(QDate.currentDate().addDays(14), current.time())
        elif action == "month_1":
            value = QDateTime(QDate.currentDate().addMonths(1), current.time())
        elif action == "now":
            now = QDateTime.currentDateTime()
            value = QDateTime(now.date(), QTime(now.time().hour(), now.time().minute()))
        else:
            hour, minute = action
            value = QDateTime(current.date(), QTime(hour, minute))
        self._set_date_time_value(self.start_date, self.start_time, value)
        self._handle_start_datetime_changed()

    def _set_end_from_start_offset(self, minutes):
        if (
            not hasattr(self, "end_date")
            or self.end_date is None
            or not hasattr(self, "end_time")
            or self.end_time is None
        ):
            return
        if hasattr(self, "auto_end_check") and self.auto_end_check:
            self.auto_end_check.setChecked(True)
        self._auto_end_duration_mins = max(15, int(minutes))
        self._apply_auto_end_from_start()

    def _set_end_to_day_end(self):
        if (
            not hasattr(self, "end_date")
            or self.end_date is None
            or not hasattr(self, "end_time")
            or self.end_time is None
        ):
            return
        if hasattr(self, "auto_end_check") and self.auto_end_check:
            self.auto_end_check.setChecked(False)
        start_value = self._date_time_value(self.start_date, self.start_time)
        self._updating_end_controls = True
        self._set_date_time_value(
            self.end_date, self.end_time, QDateTime(start_value.date(), QTime(23, 59))
        )
        self._updating_end_controls = False
        self._handle_end_datetime_changed()

    def _sync_auto_end_duration_from_controls(self):
        if (
            not hasattr(self, "end_date")
            or self.end_date is None
            or not hasattr(self, "end_time")
            or self.end_time is None
        ):
            return
        start_value = self._date_time_value(self.start_date, self.start_time)
        end_value = self._date_time_value(self.end_date, self.end_time)
        minutes = start_value.secsTo(end_value) // 60
        self._auto_end_duration_mins = max(15, minutes if minutes > 0 else 60)

    def _apply_auto_end_from_start(self):
        if (
            not hasattr(self, "end_date")
            or self.end_date is None
            or not hasattr(self, "end_time")
            or self.end_time is None
            or not hasattr(self, "auto_end_check")
            or self.auto_end_check is None
            or not self.auto_end_check.isChecked()
        ):
            return
        start_value = self._date_time_value(self.start_date, self.start_time)
        end_value = start_value.addSecs(self._auto_end_duration_mins * 60)
        self._updating_end_controls = True
        self._set_date_time_value(self.end_date, self.end_time, end_value)
        self._updating_end_controls = False

    def _handle_start_datetime_changed(self):
        if self.task_type == "routine":
            self._update_routine_mode_ui()
        elif (
            hasattr(self, "end_date")
            and self.end_date is not None
            and hasattr(self, "end_time")
            and self.end_time is not None
            and hasattr(self, "auto_end_check")
            and self.auto_end_check is not None
            and self.auto_end_check.isChecked()
        ):
            self._apply_auto_end_from_start()
        self._update_duration_summary()

    def _handle_end_datetime_changed(self):
        if self._updating_end_controls or self.end_date is None or self.end_time is None:
            return
        if self.auto_end_check.isChecked():
            self._sync_auto_end_duration_from_controls()
        self._update_duration_summary()

    # ── Recurrence helpers ────────────────────────────────────────────────
    def _build_recurrence_rule(self):
        if self.task_type != "routine":
            return None
        if self.single_task_radio.isChecked():
            return "mode=single"
        if self._routine_recurrence:
            return self._routine_recurrence
        return build_routine_recurrence_rule(
            self._get_routine_cycle_type(),
            default_recurrence_config(self.start_date.date(), self._get_routine_cycle_type()),
        )

    def _parse_recurrence_rule(self, recurrence):
        return parse_recurrence_rule(recurrence)

    def _get_routine_cycle_type(self):
        if self.task_type != "routine":
            return None
        if hasattr(self, "single_task_radio") and self.single_task_radio.isChecked():
            return "single"
        return self._routine_cycle_type or "monthly"

    def _describe_routine_rule(self):
        if self.task_type != "routine":
            return ""
        return recurrence_summary(
            self.start_date.date() if hasattr(self, "start_date") else QDate.currentDate(),
            self._get_routine_cycle_type(),
            self._build_recurrence_rule(),
        )

    def _update_next_occurrence_preview(self):
        if not hasattr(self, "routine_next_label"):
            return
        if not hasattr(self, "start_date"):
            self.routine_next_label.setText(t("dialog.recurrence.next_occurrence_hint"))
            return
        if self.single_task_radio.isChecked():
            self.routine_next_label.setText(t("dialog.recurrence.next_occurrence_none"))
            return
        self.routine_next_label.setText(
            t(
                "dialog.recurrence.next_occurrence_prefix",
                date=routine_policy.get_next_occurrence(
                    self.start_date.date().toString("yyyy-MM-dd"),
                    self._get_routine_cycle_type(),
                    routine_policy.parse_recurrence_rule(self._build_recurrence_rule()),
                )
                or t("dialog.common.unspecified"),
            )
        )

    def _apply_routine_recurrence(self, cycle_type=None, recurrence=None):
        if self.task_type != "routine":
            return
        cycle_type = cycle_type or "single"
        self._routine_cycle_type = "monthly" if cycle_type == "single" else cycle_type
        self._routine_recurrence = recurrence

        if cycle_type == "single":
            self.single_task_radio.setChecked(True)
        else:
            self.repeat_task_radio.setChecked(True)

        base_date = self.start_date.date() if hasattr(self, "start_date") else QDate.currentDate()
        self._recurrence_config = normalize_recurrence_config(
            base_date, self._routine_cycle_type, recurrence
        )
        self._apply_recurrence_to_controls()
        self._sync_from_recurrence_controls()

    def _update_routine_mode_ui(self):
        if self.task_type != "routine":
            return
        is_repeat = self.repeat_task_radio.isChecked()
        if hasattr(self, "start_label_widget"):
            # 시작일/기한 라벨 변경: 반복업무면 "반복 시작", 단일업무면 "마감 기한" (또는 적절한 용어)
            self.start_label_widget.setText(
                t("dialog.task.start_day_routine")
                if is_repeat
                else t("dialog.task.end_day_routine")
            )

        # 반복 마법사 스택 (상세 조건 입력 영역)
        if hasattr(self, "routine_wizard_stack"):
            self.routine_wizard_stack.setCurrentIndex(1 if is_repeat else 0)
        elif hasattr(self, "routine_wizard_group"):
            self.routine_wizard_group.setVisible(is_repeat)

        # 반복 주기 선택 스택 (매월, 매주 등 콤보박스 영역)
        if hasattr(self, "repeat_mode_stack"):
            self.repeat_mode_stack.setCurrentIndex(1 if is_repeat else 0)
        elif hasattr(self, "repeat_cycle_combo"):
            self.repeat_cycle_combo.setVisible(is_repeat)

        # 시간 위젯: 반복업무는 날짜 단위이므로 반복 설정 시 숨김
        if hasattr(self, "start_time") and self.start_time is not None:
            self.start_time.setVisible(not is_repeat)

        # 반복 종료일 설정: 반복 업무일 때만 표시
        if hasattr(self, "routine_end_container"):
            self.routine_end_container.setVisible(is_repeat)
        elif hasattr(self, "routine_period_end_date") and self.routine_period_end_date is not None:
            self.routine_period_end_date.setVisible(is_repeat)

        if is_repeat:
            if not self._routine_recurrence:
                base_date = (
                    self.start_date.date() if hasattr(self, "start_date") else QDate.currentDate()
                )
                config = normalize_recurrence_config(base_date, self._routine_cycle_type, "")
                self._routine_recurrence = build_routine_recurrence_rule(
                    self._routine_cycle_type, config
                )
            self._apply_recurrence_to_controls()

        self._sync_from_recurrence_controls()
        # 높이 안정화 로직 호출
        self._sync_routine_stable_heights()

        if hasattr(self, "_update_routine_preview"):
            self._update_routine_preview()

    def _update_period_display(self):
        """Signal-compatible wrapper — calls _update_routine_mode_ui once."""
        self._update_routine_mode_ui()

    # ── Recurrence control sync ───────────────────────────────────────────
    def _apply_recurrence_to_controls(self):
        if not hasattr(self, "rule_mode_combo"):
            return
        config = getattr(self, "_recurrence_config", None)
        if not config:
            return

        idx = self.repeat_cycle_combo.findData(self._routine_cycle_type)
        if idx >= 0:
            old = self.repeat_cycle_combo.blockSignals(True)
            self.repeat_cycle_combo.setCurrentIndex(idx)
            self.repeat_cycle_combo.blockSignals(old)

        self._populate_slot_combo()
        for combo, val in [
            (
                self.rule_mode_combo,
                "nth_weekday" if config["mode"] == "nth_weekday" else "day_of_month",
            ),
            (self.slot_combo, config.get("slot")),
            (self.day_combo, config.get("day")),
            (self.nth_combo, config.get("nth")),
            (self.weekday_combo, config.get("weekday")),
        ]:
            idx = combo.findData(val)
            if idx >= 0:
                combo.setCurrentIndex(idx)

    def _populate_slot_combo(self):
        options = cycle_slot_options(self._routine_cycle_type)
        current = self.slot_combo.currentData()
        self.slot_combo.blockSignals(True)
        self.slot_combo.clear()
        for label_text, v in options:
            self.slot_combo.addItem(label_text, v)
        idx = self.slot_combo.findData(current if current is not None else 1)
        self.slot_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.slot_combo.blockSignals(False)

    def _sync_from_recurrence_controls(self):
        if not hasattr(self, "rule_mode_combo"):
            return
        from PyQt6.QtWidgets import QApplication

        focused_widget = QApplication.focusWidget()
        self._routine_cycle_type = self.repeat_cycle_combo.currentData() or "monthly"
        self._populate_slot_combo()

        config = {
            "mode": "weekly"
            if self._routine_cycle_type == "weekly"
            else self.rule_mode_combo.currentData(),
            "slot": self.slot_combo.currentData() or 1,
            "day": self.day_combo.currentData() or 1,
            "nth": self.nth_combo.currentData() or 1,
            "weekday": self.weekday_combo.currentData() or 0,
        }
        self._recurrence_config = config
        self._routine_recurrence = build_routine_recurrence_rule(self._routine_cycle_type, config)

        is_repeat = (
            self.repeat_task_radio.isChecked() if hasattr(self, "repeat_task_radio") else True
        )
        is_weekly = self._routine_cycle_type == "weekly"
        has_slot = bool(cycle_slot_options(self._routine_cycle_type))
        is_nth = config["mode"] == "nth_weekday"

        # 포커스 점프 방지를 위해 removeWidget 대신 가시성/위치만 제어
        for widget in [
            self.lbl_slot,
            self.slot_combo,
            self.lbl_day,
            self.day_combo,
            self.lbl_rule_value,
            self.rule_value_wrap,
        ]:
            widget.hide()

        row = 0
        if is_weekly:
            self.lbl_rule_value.setText(t("dialog.recurrence.rule_weekday"))
            self.recurrence_form.addWidget(
                self.lbl_rule_value, row, 0, Qt.AlignmentFlag.AlignVCenter
            )
            self.recurrence_form.addWidget(
                self.rule_value_wrap, row, 1, 1, 3, Qt.AlignmentFlag.AlignVCenter
            )
            self.lbl_rule_value.show()
            self.rule_value_wrap.show()
            self.nth_combo.hide()
            self.weekday_combo.show()
        elif is_nth:
            if has_slot:
                self.recurrence_form.addWidget(self.lbl_slot, row, 0, Qt.AlignmentFlag.AlignVCenter)
                self.recurrence_form.addWidget(
                    self.slot_combo, row, 1, Qt.AlignmentFlag.AlignVCenter
                )
                self.lbl_slot.show()
                self.slot_combo.show()
                self.recurrence_form.addWidget(
                    self.lbl_rule_value, row, 2, Qt.AlignmentFlag.AlignVCenter
                )
                self.recurrence_form.addWidget(
                    self.rule_value_wrap, row, 3, Qt.AlignmentFlag.AlignVCenter
                )
            else:
                self.recurrence_form.addWidget(
                    self.lbl_rule_value, row, 0, Qt.AlignmentFlag.AlignVCenter
                )
                self.recurrence_form.addWidget(
                    self.rule_value_wrap, row, 1, 1, 3, Qt.AlignmentFlag.AlignVCenter
                )
            self.lbl_rule_value.setText(t("dialog.recurrence.rule_specific_day"))
            self.lbl_rule_value.show()
            self.rule_value_wrap.show()
            self.nth_combo.show()
            self.weekday_combo.show()
        else:
            if has_slot:
                self.recurrence_form.addWidget(self.lbl_slot, row, 0, Qt.AlignmentFlag.AlignVCenter)
                self.recurrence_form.addWidget(
                    self.slot_combo, row, 1, Qt.AlignmentFlag.AlignVCenter
                )
                self.lbl_slot.show()
                self.slot_combo.show()
                self.recurrence_form.addWidget(self.lbl_day, row, 2, Qt.AlignmentFlag.AlignVCenter)
                self.recurrence_form.addWidget(
                    self.day_combo, row, 3, Qt.AlignmentFlag.AlignVCenter
                )
            else:
                self.recurrence_form.addWidget(self.lbl_day, row, 0, Qt.AlignmentFlag.AlignVCenter)
                self.recurrence_form.addWidget(
                    self.day_combo, row, 1, 1, 3, Qt.AlignmentFlag.AlignVCenter
                )
            self.lbl_day.show()
            self.day_combo.show()

        if hasattr(self, "repeat_mode_stack"):
            self.repeat_mode_stack.setCurrentIndex(1 if is_repeat else 0)
        else:
            self.repeat_cycle_combo.setVisible(is_repeat)
        self.rule_mode_combo.setVisible(is_repeat and not is_weekly)
        self.rule_mode_combo.setEnabled(is_repeat and not is_weekly)
        self._sync_routine_stable_heights()

        # 4. 포커스 복원 (레이아웃 재구성 후 포커스가 튐 방지)
        if focused_widget and focused_widget.isVisible():
            focused_widget.setFocus()

        if hasattr(self, "_update_routine_preview"):
            self._update_routine_preview()

    def _sync_routine_stable_heights(self):
        """반복업무 설정 변경 시 레이아웃 흔들림을 방지하기 위해 높이를 고정합니다."""
        # 1. 반복 주기 선택 영역 (매월/매주 등 콤보박스)
        if hasattr(self, "repeat_mode_controls") and hasattr(self, "repeat_mode_placeholder"):
            # 최소 38px 확보
            target_height = max(self.repeat_mode_controls.sizeHint().height(), 38)
            self.repeat_mode_placeholder.setFixedSize(210, target_height)
            if hasattr(self, "repeat_mode_stack"):
                self.repeat_mode_stack.setFixedHeight(target_height + 2)

        # 2. 반복 상세 마법사 영역 (슬롯/일자 등 상세 설정)
        if hasattr(self, "routine_wizard_group") and hasattr(self, "routine_wizard_placeholder"):
            self.routine_wizard_group.adjustSize()
            # 공백 최소화를 위해 높이 조정 (94px -> 82px)
            stable_height = 82

            is_repeat = (
                self.repeat_task_radio.isChecked() if hasattr(self, "repeat_task_radio") else True
            )

            if is_repeat:
                actual_min = max(stable_height, self.routine_wizard_group.sizeHint().height())
                if hasattr(self, "routine_wizard_stack"):
                    self.routine_wizard_stack.setMinimumHeight(actual_min)
                    self.routine_wizard_stack.setMaximumHeight(actual_min)
                    # 정책을 확장형으로 고정 (포커스 튀지 않게 함)
                    self.routine_wizard_stack.setSizePolicy(
                        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
                    )
            else:
                if hasattr(self, "routine_wizard_stack"):
                    self.routine_wizard_stack.setMinimumHeight(0)
                    self.routine_wizard_stack.setMaximumHeight(0)
                self.routine_wizard_placeholder.setFixedHeight(0)

    # ── Shared tab builders ───────────────────────────────────────────────
    def _build_alarm_section(self):
        """알람 설정 섹션 위젯을 생성하여 반환한다."""
        alarm_group, alarm_layout = self._create_section(
            t("dialog.task.alarm_settings"), icon=ICON.ALARM
        )
        self.alarm_opts = {
            t("dialog.task.alarm_1w"): 10080,
            t("dialog.task.alarm_1d"): 1440,
            t("dialog.task.alarm_1h"): 60,
            t("dialog.task.alarm_10m"): 10,
        }
        self.alarm_checks = {}
        alarm_grid = QGridLayout()
        alarm_grid.setHorizontalSpacing(12)
        alarm_grid.setVerticalSpacing(6)
        alarm_grid.setContentsMargins(0, 0, 0, 0)

        # 기본값 로드
        from PyQt6.QtCore import QSettings

        settings = QSettings("DarkCalendar", "TaskDialog")
        default_alarms = settings.value("default_alarms", "10,60")  # 기본값 10분, 1시간
        if isinstance(default_alarms, str):
            default_alarms = [int(x.strip()) for x in default_alarms.split(",") if x.strip()]
        else:
            default_alarms = []

        for index, (text, mins) in enumerate(self.alarm_opts.items()):
            cb = QCheckBox(text)
            cb.toggled.connect(self._update_alarm_summary)
            if mins in default_alarms and not getattr(self, "_is_modify", False):
                cb.setChecked(True)
            alarm_grid.addWidget(cb, index // 2, index % 2)
            self.alarm_checks[mins] = cb

        # 기본값 설정 버튼
        self.set_default_alarm_btn = QPushButton(
            t("dialog.task.save_alarm_default", "알람 기본값 저장")
        )
        self.set_default_alarm_btn.setObjectName("ghost_btn")
        self.set_default_alarm_btn.ensurePolished()
        required_width = (
            self.set_default_alarm_btn.fontMetrics().horizontalAdvance(
                self.set_default_alarm_btn.text()
            )
            + 48
        )
        self.set_default_alarm_btn.setMinimumWidth(max(152, required_width))
        self.set_default_alarm_btn.setMinimumHeight(30)
        self.set_default_alarm_btn.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        self.set_default_alarm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_default_alarm_btn.clicked.connect(self._save_default_alarms)
        alarm_grid.addWidget(self.set_default_alarm_btn, 0, 2, 2, 1)
        alarm_grid.setColumnStretch(3, 1)

        alarm_layout.addLayout(alarm_grid)
        return alarm_group

    def _save_default_alarms(self):
        from PyQt6.QtCore import QSettings

        settings = QSettings("DarkCalendar", "TaskDialog")
        selected = [str(mins) for mins, cb in self.alarm_checks.items() if cb.isChecked()]
        settings.setValue("default_alarms", ",".join(selected))
        QMessageBox.information(
            self,
            t("dialog.common.save", "저장"),
            t("dialog.task.alarm_default_saved", "알람 기본값이 저장되었습니다."),
        )

    def _build_additional_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 10, 14, 8)

        # ── 운영 설정 (우선순위/상태/색상) ────────────────────
        layout.addWidget(self._create_ops_section())

        # ── 상세 메모 ─────────────────────────────────────────
        memo_group, memo_layout = self._create_section(
            t("dialog.task.memo_section"), icon=ICON.MEMO
        )
        self.memo_edit = QTextEdit()
        self.memo_edit.setPlaceholderText(t("dialog.task.memo_placeholder_detail"))
        self.memo_edit.setMinimumHeight(300)
        from calendar_app.shared.tag_highlighter import HashTagHighlighter

        self._memo_highlighter = HashTagHighlighter(self.memo_edit.document())
        memo_layout.addWidget(self.memo_edit)

        tag_hint = QLabel(t("dialog.task.tag_hint"))
        tag_hint.setWordWrap(True)
        tag_hint.setStyleSheet(
            build_editor_hint_style(
                self._ui_tokens(),
                self._dialog_metrics(),
                tone="accent",
                font_px=11,
            )
        )
        memo_layout.addWidget(tag_hint)

        layout.addWidget(memo_group)
        layout.addStretch()
        return w

    def _build_checklist_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 20, 15, 15)

        template_row = QHBoxLayout()
        template_row.addWidget(QLabel(t("dialog.checklist.template")))
        self.checklist_template_combo = QComboBox()
        self._load_checklist_templates()
        self.checklist_template_combo.currentIndexChanged.connect(
            self._on_checklist_template_selected
        )
        template_row.addWidget(self.checklist_template_combo, 1)
        layout.addLayout(template_row)

        self.progress_label = QLabel()
        layout.addWidget(self.progress_label)

        # 항목 유형 선택 (목록형 / 프로세스형)
        type_row = QHBoxLayout()
        type_row.addWidget(QLabel(t("dialog.checklist.type_label")))
        self.type_list_radio = QRadioButton(t("dialog.checklist.type_list"))
        self.type_process_radio = QRadioButton(t("dialog.checklist.type_process"))
        self.type_list_radio.setChecked(True)
        self.checklist_display_type = "list"

        self.type_list_radio.toggled.connect(self._on_checklist_type_toggled)
        self.type_process_radio.toggled.connect(self._on_checklist_type_toggled)

        type_row.addWidget(self.type_list_radio)
        type_row.addWidget(self.type_process_radio)
        type_row.addStretch()
        layout.addLayout(type_row)

        layout.addWidget(QLabel(t("dialog.checklist.items_label")))

        self.checklist_widget = QListWidget()
        self.checklist_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.checklist_widget.itemDoubleClicked.connect(self._toggle_checklist_item)
        layout.addWidget(self.checklist_widget)
        self._refresh_checklist_display()

        btn_layout = QHBoxLayout()
        add_btn = QPushButton(_se(t("dialog.checklist.add_btn")))
        add_btn.setIcon(_ic(ICON.ADD))
        add_btn.clicked.connect(self._add_checklist_item)
        remove_btn = QPushButton(_se(t("dialog.checklist.del_btn")))
        remove_btn.setIcon(_ic(ICON.DELETE))
        remove_btn.clicked.connect(self._remove_checklist_item)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return w

    # ── Checklist template helpers ────────────────────────────────────────
    def _load_checklist_templates(self):
        """체크리스트 템플릿 목록 로드"""
        self.checklist_template_combo.clear()
        self.checklist_template_combo.addItem("-- 템플릿 선택 --", None)
        templates = checklist_template_repo.get_all_checklist_templates(active_only=True)
        for t_item in templates:
            item_count = len(checklist_template_repo.get_checklist_items(t_item["id"]))
            type_str = (
                t("dialog.checklist.type_list")
                if t_item.get("checklist_type") == "list"
                else t("dialog.checklist.type_process")
            )
            self.checklist_template_combo.addItem(
                f"  {t_item['name']} [{type_str}] ({item_count}{t('dialog.checklist.item_unit')})",
                t_item["id"],
            )

    def _on_checklist_template_selected(self, _index):
        """체크리스트 템플릿 선택 시 항목 로드"""
        template_id = self.checklist_template_combo.currentData()
        if not template_id:
            return
        reply = QMessageBox.question(
            self,
            t("dialog.checklist.apply_template_title"),
            t("dialog.checklist.apply_template_msg"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._load_checklist_from_template(template_id)

    def _on_checklist_manager_closed(self):
        """체크리스트 관리자 닫힌 후 템플릿 목록 새로고침"""
        current_template_id = self.checklist_template_combo.currentData()
        self._load_checklist_templates()
        if current_template_id:
            for i in range(self.checklist_template_combo.count()):
                if self.checklist_template_combo.itemData(i) == current_template_id:
                    self.checklist_template_combo.setCurrentIndex(i)
                    break

    def _open_checklist_manager(self):
        """체크리스트 관리 다이얼로그 열기"""
        from calendar_app.presentation.dialogs.checklist_manager_dialog_advanced import (
            ChecklistManagerDialog,
        )

        dlg = ChecklistManagerDialog(self)
        dlg.checklist_changed.connect(self._on_checklist_manager_closed)
        dlg.exec()

    def _on_checklist_type_toggled(self):
        if self.type_list_radio.isChecked():
            self.checklist_display_type = "list"
        else:
            self.checklist_display_type = "process"
        self._refresh_checklist_display()

    # ── Subclass interface (override in each subclass) ────────────────────
    def _refresh_checklist_display(self):
        """No-op in base; overridden by create dialog to update UI state."""
        pass

    def _load_checklist_from_template(self, _template_id):
        raise NotImplementedError

    def _add_checklist_item(self):
        raise NotImplementedError

    def _remove_checklist_item(self):
        raise NotImplementedError

    def _toggle_checklist_item(self, _item):
        raise NotImplementedError
