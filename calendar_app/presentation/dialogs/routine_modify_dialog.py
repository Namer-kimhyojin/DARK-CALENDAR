"""Dedicated modify dialog for 일반업무 (routine type tasks)."""

from datetime import datetime

from PyQt6.QtCore import QDate, Qt, QTime, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.db import checklist_repo, common_repo, task_repo
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    polish_calendar_popup,
)
from calendar_app.presentation.dialogs.label_settings_dialog import EmojiLineEdit
from calendar_app.presentation.dialogs.routine_recurrence_wizard import (
    get_cycle_labels,
    get_weekday_names,
)
from calendar_app.presentation.dialogs.task_dialog_base import BaseTaskDialog
from calendar_app.presentation.dialogs.time_picker_widget import TimePickerWidget


class RoutineModifyDialog(BaseTaskDialog):
    """Dedicated modify dialog for routine tasks (일반업무)."""

    task_modified = pyqtSignal(dict)
    task_deleted = pyqtSignal(int)

    def __init__(self, task_id: int, parent=None):
        super().__init__(parent)
        self.task_id = task_id
        self.task_type = "routine"
        self._is_modify = True

        self._init_common_state()

        self.task_data = task_repo.get_unified_task(task_id)
        if not self.task_data:
            QMessageBox.critical(
                self,
                t("dialog.task.error", "오류"),
                t("dialog.task.not_found", "업무를 찾을 수 없습니다."),
            )
            return

        self.initial_date = QDate.currentDate()
        self.initial_time = QTime(12, 0)
        self._parse_task_datetime()

        apply_dialog_title(self, t("dialog.task.mod_routine", "일반업무 수정"))
        apply_common_dialog_style(self, minimum_width=640, size=(660, 580))

        self._build_ui()
        self._load_data()
        self._update_routine_mode_ui()

    # ── Datetime parsing ──────────────────────────────────────────────────

    def _parse_task_datetime(self):
        dt_str = self.task_data.get("deadline") or self.task_data.get("target_date")
        if not dt_str:
            return
        for fmt, sample in [
            ("%Y-%m-%d %H:%M:%S", "2000-01-01 00:00:00"),
            ("%Y-%m-%d %H:%M", "2000-01-01 00:00"),
            ("%Y-%m-%d", "2000-01-01"),
        ]:
            try:
                dt = datetime.strptime(dt_str[: len(sample)], fmt)
                self.initial_date = QDate(dt.year, dt.month, dt.day)
                self.initial_time = QTime(dt.hour, dt.minute)
                return
            except ValueError:
                continue

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout()
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(8)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_basic_tab(), t("dialog.task.tab_basic", "기본"))
        self.tabs.addTab(self._build_detail_tab(), t("dialog.task.tab_detail", "상세"))
        self.tabs.addTab(self._build_checklist_tab(), t("dialog.task.tab_checklist", "체크리스트"))
        outer.addWidget(self.tabs)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        outer.addWidget(sep)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 2, 0, 0)
        btn_row.setSpacing(8)

        del_btn = QPushButton(t("dialog.common.delete", "삭제"))
        del_btn.setObjectName("danger_btn")
        del_btn.setFixedHeight(34)
        del_btn.setMinimumWidth(80)
        del_btn.clicked.connect(self._delete_task)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()

        cancel_btn = QPushButton(t("dialog.common.cancel", "취소"))
        cancel_btn.setFixedHeight(34)
        cancel_btn.setMinimumWidth(90)
        cancel_btn.setObjectName("ghost_btn")
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton(t("dialog.common.save", "저장"))
        save_btn.setDefault(True)
        save_btn.setFixedHeight(34)
        save_btn.setMinimumWidth(90)
        save_btn.setObjectName("primary_btn")
        save_btn.clicked.connect(self._save_changes)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        outer.addLayout(btn_row)
        self.setLayout(outer)

    def _build_basic_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 10, 14, 8)

        name_group, name_layout = self._create_section(t("dialog.task.name_section", "업무 제목"))
        self.name_edit = EmojiLineEdit()
        self.name_edit.setPlaceholderText(t("dialog.task.name_placeholder_routine", "업무명 입력"))
        self._set_editor_height(self.name_edit)
        name_layout.addWidget(self.name_edit)
        layout.addWidget(name_group)

        tag_group, tag_layout = self._create_section(t("dialog.task.tags_section", "분류 태그"))
        tag_row = QHBoxLayout()
        tag_row.setSpacing(6)
        self.tags_edit = EmojiLineEdit()
        self.tags_edit.setPlaceholderText(
            t("dialog.task.tags_placeholder", "쉼표로 구분 (예: 업무, 프로젝트A)")
        )
        self._set_editor_height(self.tags_edit)
        tag_row.addWidget(self.tags_edit)
        tag_layout.addLayout(tag_row)
        layout.addWidget(tag_group)

        cycle_group, cycle_layout = self._create_section(
            t("dialog.task.cycle_section", "반복 설정")
        )
        cycle_layout.addLayout(self._build_cycle_type_selector())
        layout.addWidget(cycle_group)

        date_group, date_layout = self._create_section(
            t("dialog.task.routine_datetime_section", "수행 일시")
        )
        dt_row = QHBoxLayout()
        dt_row.setSpacing(8)

        self.start_date = QDateEdit(self.initial_date)
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("yyyy-MM-dd")
        self.start_date.setMinimumWidth(130)
        self._set_editor_height(self.start_date)
        polish_calendar_popup(self.start_date)

        self.start_time = TimePickerWidget(self.initial_time)
        dt_row.addWidget(self.start_date)
        dt_row.addWidget(self.start_time)
        dt_row.addStretch()
        date_layout.addLayout(dt_row)

        self.end_date = None
        self.end_time = None
        self.routine_period_end_date = None

        self.start_date.dateChanged.connect(self._handle_start_datetime_changed)
        self.start_time.timeChanged.connect(self._handle_start_datetime_changed)

        layout.addWidget(date_group)
        layout.addStretch()
        return w

    def _build_detail_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 10, 14, 8)

        layout.addWidget(self._create_ops_section())
        layout.addWidget(self._build_alarm_section())
        layout.addWidget(self._create_additional_info_section())

        memo_group, memo_layout = self._create_section(t("dialog.task.memo_section", "메모"))
        self.memo_edit = QTextEdit()
        self.memo_edit.setMinimumHeight(60)
        self.memo_edit.setMaximumHeight(100)
        self.memo_edit.setPlaceholderText(t("dialog.task.memo_placeholder", "메모를 입력하세요"))
        memo_layout.addWidget(self.memo_edit)
        layout.addWidget(memo_group)

        layout.addStretch()
        return w

    def _build_checklist_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(6)
        layout.setContentsMargins(14, 10, 14, 8)

        self.checklist_display_type = "list"
        self.checklist_widget = QListWidget()
        self.checklist_widget.setMinimumHeight(180)
        self.checklist_widget.itemDoubleClicked.connect(self._toggle_checklist_item)

        btn_row = QHBoxLayout()
        add_btn = QPushButton(t("dialog.checklist.add", "+ 항목 추가"))
        add_btn.clicked.connect(self._add_checklist_item)
        rm_btn = QPushButton(t("dialog.checklist.remove", "항목 삭제"))
        rm_btn.clicked.connect(self._remove_checklist_item)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(rm_btn)
        btn_row.addStretch()

        self.progress_label = QLabel()

        layout.addWidget(self.checklist_widget)
        layout.addLayout(btn_row)
        layout.addWidget(self.progress_label)
        return w

    # ── Cycle type selector (mirrors UnifiedTaskDialog._build_cycle_type_selector) ──

    def _build_cycle_type_selector(self):
        outer_layout = QVBoxLayout()
        outer_layout.setSpacing(6)
        outer_layout.setContentsMargins(0, 2, 0, 2)

        mode_header = QLabel(t("dialog.recurrence.header", "업무 유형"))
        mode_header.setStyleSheet(
            f"color: {self._ui_tokens().get('text_muted', '#7f8a99')}; font-size: 13px; font-weight: bold;"
        )
        outer_layout.addWidget(mode_header)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        self.routine_mode_group = QButtonGroup()
        self.single_task_radio = QRadioButton(t("dialog.recurrence.single", "단일 업무"))
        self.repeat_task_radio = QRadioButton(t("dialog.recurrence.repeat", "반복 업무"))
        self.single_task_radio.setChecked(True)
        self.routine_mode_group.addButton(self.single_task_radio)
        self.routine_mode_group.addButton(self.repeat_task_radio)
        mode_row.addWidget(self.single_task_radio)
        mode_row.addWidget(self.repeat_task_radio)

        self.repeat_cycle_combo = QComboBox()
        for val, label in get_cycle_labels().items():
            self.repeat_cycle_combo.addItem(label, val)
        self.repeat_cycle_combo.setFixedWidth(86)

        self.rule_mode_combo = QComboBox()
        self.rule_mode_combo.addItem(
            t("dialog.recurrence.specific_date", "특정 날짜"), "day_of_month"
        )
        self.rule_mode_combo.addItem(
            t("dialog.recurrence.nth_weekday", "N번째 요일"), "nth_weekday"
        )
        self.rule_mode_combo.setFixedWidth(116)

        self.repeat_mode_controls = QWidget()
        rmc_layout = QHBoxLayout(self.repeat_mode_controls)
        rmc_layout.setContentsMargins(0, 0, 0, 0)
        rmc_layout.setSpacing(8)
        rmc_layout.addWidget(self.repeat_cycle_combo)
        rmc_layout.addWidget(self.rule_mode_combo)

        self.repeat_mode_placeholder = QWidget()
        self.repeat_mode_placeholder.setFixedSize(210, 34)

        self.repeat_mode_stack = QStackedWidget()
        self.repeat_mode_stack.setObjectName("RepeatModeStack")
        self.repeat_mode_stack.setStyleSheet(
            "QStackedWidget#RepeatModeStack { background: transparent; border: none; }"
        )
        self.repeat_mode_stack.setFixedHeight(38)
        self.repeat_mode_stack.setMinimumWidth(210)
        self.repeat_mode_stack.setMaximumWidth(210)
        self.repeat_mode_stack.addWidget(self.repeat_mode_placeholder)
        self.repeat_mode_stack.addWidget(self.repeat_mode_controls)
        mode_row.addWidget(self.repeat_mode_stack)
        mode_row.addStretch()
        outer_layout.addLayout(mode_row)

        self.routine_wizard_group = QGroupBox(t("dialog.recurrence.wizard_title", "반복 상세 설정"))
        inner_layout = QVBoxLayout()
        inner_layout.setSpacing(8)

        self.recurrence_form = QGridLayout()
        self.recurrence_form.setHorizontalSpacing(10)
        self.recurrence_form.setVerticalSpacing(8)
        self.recurrence_form.setColumnStretch(1, 1)
        self.recurrence_form.setColumnStretch(3, 1)

        self.lbl_slot = QLabel(t("dialog.recurrence.slot_month", "월"))
        self.slot_combo = QComboBox()

        self.lbl_day = QLabel(t("dialog.recurrence.day_label", "일"))
        self.day_combo = QComboBox()
        for dc in range(1, 32):
            self.day_combo.addItem(f"{dc}{t('dialog.recurrence.day_unit', '일')}", dc)
        self.day_combo.addItem(t("dialog.recurrence.last_day", "마지막 날"), "last")

        self.nth_combo = QComboBox()
        for t_key, nv in [
            ("dialog.recurrence.nth_first", 1),
            ("dialog.recurrence.nth_second", 2),
            ("dialog.recurrence.nth_third", 3),
            ("dialog.recurrence.nth_fourth", 4),
            ("dialog.recurrence.nth_fifth", 5),
            ("dialog.recurrence.nth_last", "last"),
        ]:
            self.nth_combo.addItem(t(t_key), nv)

        self.weekday_combo = QComboBox()
        for wi, wn in enumerate(get_weekday_names()):
            self.weekday_combo.addItem(wn, wi)

        self.lbl_rule_value = QLabel(t("dialog.recurrence.day_label", "일"))
        self.rule_value_wrap = QWidget()
        self.rule_value_layout = QHBoxLayout(self.rule_value_wrap)
        self.rule_value_layout.setContentsMargins(0, 0, 0, 0)
        self.rule_value_layout.setSpacing(6)
        self.rule_value_layout.addWidget(self.nth_combo)
        self.rule_value_layout.addWidget(self.weekday_combo)

        inner_layout.addLayout(self.recurrence_form)
        self.routine_wizard_group.setLayout(inner_layout)

        self.routine_wizard_placeholder = QWidget()
        self.routine_wizard_placeholder.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.routine_wizard_placeholder.setMinimumHeight(128)
        self.routine_wizard_placeholder.setMaximumHeight(128)

        self.routine_wizard_stack = QStackedWidget()
        self.routine_wizard_stack.setObjectName("RoutineWizardStack")
        self.routine_wizard_stack.setStyleSheet(
            "QStackedWidget#RoutineWizardStack { background: transparent; border: none; }"
        )
        self.routine_wizard_stack.addWidget(self.routine_wizard_placeholder)
        self.routine_wizard_stack.addWidget(self.routine_wizard_group)
        outer_layout.addWidget(self.routine_wizard_stack)

        self.repeat_cycle_combo.currentIndexChanged.connect(self._sync_from_recurrence_controls)
        self.rule_mode_combo.currentIndexChanged.connect(self._sync_from_recurrence_controls)
        self.slot_combo.currentIndexChanged.connect(self._sync_from_recurrence_controls)
        self.day_combo.currentIndexChanged.connect(self._sync_from_recurrence_controls)
        self.nth_combo.currentIndexChanged.connect(self._sync_from_recurrence_controls)
        self.weekday_combo.currentIndexChanged.connect(self._sync_from_recurrence_controls)

        self.single_task_radio.toggled.connect(self._update_routine_mode_ui)
        self.repeat_task_radio.toggled.connect(self._update_routine_mode_ui)

        self._update_routine_mode_ui()
        return outer_layout

    # ── Data loading ──────────────────────────────────────────────────────

    def _load_data(self):
        dc = self.task_data
        self.name_edit.setText(dc.get("name", ""))

        for attr, val in [
            ("priority_combo", dc.get("priority", "normal")),
            ("status_combo", dc.get("status", "in_progress")),
        ]:
            combo = getattr(self, attr, None)
            if combo:
                idx = combo.findData(val)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

        self.start_date.setDate(self.initial_date)
        self.start_time.setTime(self.initial_time)

        if dc.get("bg_color") and hasattr(self, "color_swatch"):
            self.color_swatch.set_color(dc["bg_color"])

        alarm_raw = dc.get("alarm_time")
        if alarm_raw and hasattr(self, "alarm_checks"):
            for ms in alarm_raw.split(","):
                ms = ms.strip()
                if ms:
                    try:
                        mins = int(ms)
                        if mins in self.alarm_checks:
                            self.alarm_checks[mins].setChecked(True)
                    except ValueError:
                        pass

        tags_val = dc.get("tags") or ""
        if hasattr(self, "tags_edit"):
            self.tags_edit.setText(tags_val)

        if dc.get("location") and hasattr(self, "location_edit"):
            self.location_edit.setText(dc["location"])
        if dc.get("assignee") and hasattr(self, "assignee_edit"):
            self.assignee_edit.setText(dc["assignee"])

        memo = dc.get("description") or dc.get("memo", "")
        if memo and hasattr(self, "memo_edit"):
            self.memo_edit.setPlainText(memo)

        self._load_checklist_items()

        self._apply_routine_recurrence(
            dc.get("cycle_type") or "single",
            dc.get("recurrence"),
        )
        self._update_alarm_summary()

    # ── Checklist helpers ─────────────────────────────────────────────────

    def _load_checklist_items(self):
        self.checklist_widget.clear()
        items = checklist_repo.get_task_checklist_items(self.task_id)
        if items:
            self.checklist_display_type = items[0].get("display_type", "list")
        total = len(items)
        completed = sum(1 for it in items if it.get("is_completed"))
        for idx, item in enumerate(items):
            is_done = bool(item.get("is_completed"))
            mark = "✓" if is_done else "○"
            prefix = f"{idx + 1}. " if self.checklist_display_type == "process" else ""
            text = f"{mark} {prefix}{item['item_text']}"
            li = QListWidgetItem(text)
            li.setData(Qt.ItemDataRole.UserRole, item["id"])
            li.setData(Qt.ItemDataRole.UserRole + 1, is_done)
            self.checklist_widget.addItem(li)
        pct = (completed / total * 100) if total > 0 else 0.0
        self.progress_label.setText(
            f"{t('dialog.checklist.progress', '진행률')} {completed}/{total} ({pct:.1f}%)"
        )

    def _toggle_checklist_item(self, item):
        link_id = item.data(Qt.ItemDataRole.UserRole)
        checklist_repo.toggle_checklist_item(link_id)
        self._load_checklist_items()

    def _add_checklist_item(self):
        from PyQt6.QtWidgets import QInputDialog

        text, ok = QInputDialog.getText(
            self,
            t("dialog.checklist.add_title", "항목 추가"),
            t("dialog.checklist.add_prompt", "항목 내용:"),
        )
        if ok and text.strip():
            order = self.checklist_widget.count()
            checklist_repo.add_checklist_item(
                self.task_id,
                text.strip(),
                order,
                display_type=self.checklist_display_type,
            )
            self._load_checklist_items()

    def _remove_checklist_item(self):
        cur = self.checklist_widget.currentItem()
        if not cur:
            return
        link_id = cur.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self,
            t("dialog.checklist.delete_title", "항목 삭제"),
            t("dialog.checklist.delete_confirm", "선택한 항목을 삭제하시겠습니까?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            conn = common_repo.get_connection()
            if conn:
                cur_db = conn.cursor()
                cur_db.execute("DELETE FROM task_checklist_link WHERE id=?", (link_id,))
                conn.commit()
                self._load_checklist_items()

    # ── Save / Delete ─────────────────────────────────────────────────────

    def _save_changes(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(
                self,
                t("dialog.task.entry_error", "입력 오류"),
                t("dialog.task.name_required", "업무명을 입력해주세요."),
            )
            return

        target_date = self.start_date.date().toString("yyyy-MM-dd")
        time_str = self.start_time.time().toString("HH:mm:ss")
        deadline_dt = f"{target_date} {time_str}"

        selected_alarms = (
            [str(mins) for mins, cb in self.alarm_checks.items() if cb.isChecked()]
            if hasattr(self, "alarm_checks")
            else []
        )

        updates = {
            "name": name,
            "target_date": target_date,
            "deadline": deadline_dt,
            "cycle_type": self._get_routine_cycle_type(),
            "recurrence": self._build_recurrence_rule(),
            "priority": self.priority_combo.currentData()
            if hasattr(self, "priority_combo")
            else None,
            "status": self.status_combo.currentData() if hasattr(self, "status_combo") else None,
            "alarm_time": ",".join(selected_alarms) if selected_alarms else "",
            "bg_color": self.color_swatch.selected_color()
            if hasattr(self, "color_swatch")
            else None,
            "description": self.memo_edit.toPlainText().strip()
            if hasattr(self, "memo_edit")
            else None,
            "location": self.location_edit.text().strip()
            if hasattr(self, "location_edit")
            else None,
            "assignee": self.assignee_edit.text().strip()
            if hasattr(self, "assignee_edit")
            else None,
            "calendar_id": None,
            "tags": self.tags_edit.text().strip() if hasattr(self, "tags_edit") else None,
        }

        success = task_repo.update_unified_task(self.task_id, updates)
        if success:
            updates["id"] = self.task_id
            self.task_modified.emit(updates)
            self.accept()
        else:
            QMessageBox.critical(
                self,
                t("dialog.task.save_failed", "저장 실패"),
                t("dialog.task.save_error_db", "저장 중 오류가 발생했습니다."),
            )

    def _delete_task(self):
        reply = QMessageBox.question(
            self,
            t("dialog.task.del_title", "업무 삭제"),
            t("dialog.task.del_confirm", "이 일반업무를 삭제하시겠습니까?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            success = task_repo.delete_unified_task(self.task_id)
            if success:
                self.task_deleted.emit(self.task_id)
                self.accept()
            else:
                QMessageBox.critical(
                    self,
                    t("dialog.task.save_failed", "오류"),
                    t("dialog.task.del_fail", "삭제 중 오류가 발생했습니다."),
                )
