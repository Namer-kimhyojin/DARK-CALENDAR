"""Unified task/schedule creation and modification dialog."""

from datetime import datetime

from PyQt6.QtCore import QDate, Qt, QTime, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.db import checklist_repo, common_repo, routine_repo, task_repo
from calendar_app.infrastructure.db import checklist_repository as checklist_template_repo
from calendar_app.infrastructure.google_sync.helpers import (
    queue_task_delete_from_google,
    queue_task_sync_to_google,
)
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    polish_calendar_popup,
)
from calendar_app.presentation.dialogs.routine_recurrence_wizard import (
    get_cycle_labels,
    get_weekday_names,
)
from calendar_app.presentation.dialogs.task_dialog_base import BaseTaskDialog
from calendar_app.presentation.dialogs.time_picker_widget import TimePickerWidget


class UnifiedTaskDialog(BaseTaskDialog):
    """일정과 일반업무를 통합한 등록/수정 다이얼로그"""

    task_added = pyqtSignal(dict)
    task_modified = pyqtSignal(dict)
    task_deleted = pyqtSignal(int)

    def __init__(
        self,
        parent=None,
        initial_date=None,
        initial_time=None,
        end_date=None,
        task_type="schedule",
        template_id=None,
        end_time=None,
        task_id=None,
        prefill_dict: dict | None = None,
    ):
        super().__init__(parent)
        self.task_id = task_id
        self._is_modify = task_id is not None

        if self._is_modify:
            self.task_data = task_repo.get_unified_task(task_id)
            if not self.task_data:
                QMessageBox.critical(None, t("dialog.task.error"), t("dialog.task.not_found"))
                return
            task_type = self.task_data["type"]

        # task_type이 None일 경우 기본값 'schedule' 할당
        if task_type is None:
            task_type = "schedule"

        # 시작일 처리 (문자열 또는 QDate 대응)
        if isinstance(initial_date, str):
            self.initial_date = QDate.fromString(initial_date, Qt.DateFormat.ISODate)
        elif isinstance(initial_date, QDate):
            self.initial_date = initial_date
        else:
            self.initial_date = QDate.currentDate()
        # 기본값 설정: 일정(09:00-18:00), 일반업무(12:00)
        if isinstance(initial_time, str):
            self.initial_time = QTime.fromString(initial_time, Qt.DateFormat.ISODate)
        elif isinstance(initial_time, QTime):
            self.initial_time = initial_time
        else:
            self.initial_time = QTime(9, 0) if task_type == "schedule" else QTime(12, 0)
        self.preset_end_date = end_date
        if isinstance(end_time, str):
            self.preset_end_time = QTime.fromString(end_time, Qt.DateFormat.ISODate)
        elif isinstance(end_time, QTime):
            self.preset_end_time = end_time
        else:
            self.preset_end_time = QTime(18, 0) if task_type == "schedule" else None
        self.task_type = task_type
        self.template_id = template_id
        self._saved_task_id = None
        self._init_common_state()

        if initial_time and end_time and self.preset_end_time:
            self._auto_end_duration_mins = max(
                15, self.initial_time.secsTo(self.preset_end_time) // 60
            )

        if self._is_modify:
            title = (
                t("dialog.task.mod_routine")
                if task_type == "routine"
                else t("dialog.task.mod_schedule")
            )
            size = (660, 500 if task_type == "routine" else 540)
        else:
            title = (
                t("dialog.task.reg_routine")
                if task_type == "routine"
                else t("dialog.task.reg_schedule")
            )
            size = (660, 540 if task_type == "routine" else 600)
        apply_dialog_title(self, title)
        apply_common_dialog_style(self, minimum_width=640, size=size)

        self.init_ui()

        if self._is_modify:
            self._load_data()
        elif template_id:
            self._load_from_template(template_id)
        elif prefill_dict:
            self._apply_prefill(prefill_dict)

    def init_ui(self):
        outer = QVBoxLayout()
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(8)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_basic_tab(), t("dialog.tabs.basic"))
        self.tabs.addTab(self._build_additional_tab(), t("dialog.tabs.detail"))
        if self.task_type == "routine":
            self.tabs.addTab(self._build_checklist_tab(), t("dialog.tabs.checklist"))
        outer.addWidget(self.tabs)

        # ── 구분선 ─────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {self._ui_tokens().get('border_soft', '#252530')};")
        outer.addWidget(sep)

        # ── 하단 액션 바 ───────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 2, 0, 0)
        btn_row.setSpacing(8)

        if self._is_modify:
            delete_btn = QPushButton(t("dialog.common.delete"))
            delete_btn.setObjectName("DangerBtn")
            delete_btn.setFixedHeight(34)
            delete_btn.setMinimumWidth(80)
            delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            delete_btn.clicked.connect(self._delete_task)
            btn_row.addWidget(delete_btn)

        # 일반업무에만 체크리스트 관리 버튼 표시
        if self.task_type == "routine":
            manage_btn = QPushButton(t("dialog.checklist.manage"))
            manage_btn.setFixedWidth(80)
            manage_btn.setFixedHeight(34)
            manage_btn.setObjectName("SecondaryBtn")
            manage_btn.setToolTip(t("menu.checklist_mgmt"))
            manage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            manage_btn.clicked.connect(self._open_checklist_manager)
            btn_row.addWidget(manage_btn)

        btn_row.addStretch()

        cancel_btn = QPushButton(t("dialog.common.cancel"))
        cancel_btn.setFixedHeight(34)
        cancel_btn.setMinimumWidth(90)
        cancel_btn.setObjectName("SecondaryBtn")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)

        save_label = t("dialog.common.save") if self._is_modify else t("menu.register_btn")
        save_btn = QPushButton(save_label)
        save_btn.setDefault(True)
        save_btn.setFixedHeight(34)
        save_btn.setMinimumWidth(90)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self.save_data)
        self.save_btn = save_btn

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        outer.addLayout(btn_row)

        self.setLayout(outer)

        if self.task_type == "routine":
            self._update_period_display()

    # ── Basic tab ─────────────────────────────────────────────────────────
    def _build_basic_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 10, 14, 8)

        name_label = (
            t("dialog.task.name_routine")
            if self.task_type == "routine"
            else t("dialog.task.name_schedule")
        )
        name_hint = (
            t("dialog.task.name_hint_routine")
            if self.task_type == "routine"
            else t("dialog.task.name_hint_schedule")
        )

        from calendar_app.presentation.dialogs.label_settings_dialog import EmojiLineEdit

        # ── 제목 입력 섹션 ──────────────────────────────────────────────────
        title_group = QWidget()
        title_vbox = QVBoxLayout(title_group)
        title_vbox.setContentsMargins(0, 0, 0, 0)
        title_vbox.setSpacing(3)

        lbl_name = QLabel(name_label)
        lbl_name.setStyleSheet(
            f"color: {self._ui_tokens().get('text_muted', '#7f8a99')}; font-size: 13px; font-weight: 700;"
        )
        title_vbox.addWidget(lbl_name)

        self.name_edit = EmojiLineEdit()
        self.name_edit.setPlaceholderText(name_hint)
        self.name_edit.setMinimumHeight(34)
        self.name_edit.setMaximumHeight(36)
        title_vbox.addWidget(self.name_edit)
        layout.addWidget(title_group)

        # ── 캘린더 선택 (일정만, 일반업무는 로컬 DB 전용) ──────────────────
        if self.task_type != "routine":
            self._build_calendar_selector(layout)

        if self.task_type == "routine":
            # 분류 태그
            from PyQt6.QtWidgets import QLineEdit as _QLineEdit

            tag_group, tag_layout = self._create_section(t("dialog.task.tags_section", "분류 태그"))
            self.tags_edit = _QLineEdit()
            self.tags_edit.setPlaceholderText(
                t("dialog.task.tags_placeholder", "쉼표로 구분 (예: 업무, 프로젝트A)")
            )
            self.tags_edit.setMinimumHeight(34)
            self.tags_edit.setMaximumHeight(36)
            tag_layout.addWidget(self.tags_edit)
            layout.addWidget(tag_group)
            # 수행 방식 설정 (플랫 레이아웃)
            layout.addLayout(self._build_cycle_type_selector())

        schedule_group, schedule_layout = self._create_section(
            t("dialog.task.section_time_schedule")
            if self.task_type == "schedule"
            else t("dialog.task.section_time_routine"),
            icon="⏰",
        )

        if self.task_type == "schedule":
            # ── 상단 옵션 (종일/자동유지) ──────────────────────────────────
            option_row = QHBoxLayout()
            option_row.setContentsMargins(2, 0, 0, 5)
            self.all_day_check = QCheckBox(t("dialog.task.all_day"))
            self.all_day_check.setChecked(not self._is_modify)
            self.all_day_check.setStyleSheet(
                f"QCheckBox {{ color: {self._ui_tokens().get('text_secondary', '#d7dbe3')}; font-weight: 700; margin-right: 15px; }}"
            )
            self.all_day_check.toggled.connect(self._on_all_day_toggled)
            option_row.addWidget(self.all_day_check)

            self.auto_end_check = QCheckBox(t("dialog.task.auto_end"))
            self.auto_end_check.setChecked(True)
            self.auto_end_check.setStyleSheet(
                f"QCheckBox {{ color: {self._ui_tokens().get('text_muted', '#8c8c9a')}; font-weight: 500; }}"
            )
            self.auto_end_check.toggled.connect(
                lambda checked: self._apply_auto_end_from_start() if checked else None
            )
            option_row.addWidget(self.auto_end_check)
            option_row.addStretch()
            schedule_layout.addLayout(option_row)

            # ── 일정 기간 설정 (좌측: 시작 / 우측: 종료) ──────────────────────────
            times_row = QHBoxLayout()
            times_row.setSpacing(30)

            # L: 시작 섹션
            start_col = QVBoxLayout()
            start_col.setSpacing(5)
            self.start_label_widget = QLabel(t("dialog.task.start_dt"))
            start_col.addWidget(self.start_label_widget)

            start_edit_row = QHBoxLayout()
            start_edit_row.setSpacing(8)
            self.start_date = QDateEdit(self.initial_date)
            self.start_date.setCalendarPopup(True)
            self.start_date.setDisplayFormat("yyyy-MM-dd")
            self.start_date.setMinimumWidth(130)
            polish_calendar_popup(self.start_date)

            self.start_time = TimePickerWidget(self.initial_time)
            self._set_editor_height(self.start_date)
            start_edit_row.addWidget(self.start_date)
            start_edit_row.addWidget(self.start_time)
            start_edit_row.addStretch()
            start_col.addLayout(start_edit_row)
            times_row.addLayout(start_col, 1)

            # R: 종료 섹션
            end_col = QVBoxLayout()
            end_col.setSpacing(5)
            self.end_label_widget = QLabel(t("dialog.task.end_dt"))
            end_col.addWidget(self.end_label_widget)

            end_edit_row = QHBoxLayout()
            end_edit_row.setSpacing(8)
            end_qdate = self.preset_end_date if self.preset_end_date else self.initial_date
            self.end_date = QDateEdit(end_qdate)
            self.end_date.setCalendarPopup(True)
            self.end_date.setDisplayFormat("yyyy-MM-dd")
            self.end_date.setMinimumWidth(130)
            polish_calendar_popup(self.end_date)

            e_time = (
                self.preset_end_time if self.preset_end_time else self.initial_time.addSecs(3600)
            )
            self.end_time = TimePickerWidget(e_time)
            self._set_editor_height(self.end_date)
            end_edit_row.addWidget(self.end_date)
            end_edit_row.addWidget(self.end_time)
            end_edit_row.addStretch()
            end_col.addLayout(end_edit_row)
            times_row.addLayout(end_col, 1)

            schedule_layout.addLayout(times_row)

            # 초기 상태 반영 (종일 등)
            if not self._is_modify:
                from PyQt6.QtCore import QTimer

                QTimer.singleShot(
                    0, lambda: self._on_all_day_toggled(self.all_day_check.isChecked())
                )

            # 일정 길이 요약
            self.duration_summary_label = QLabel()
            self.duration_summary_label.setStyleSheet(
                f"color: {self._ui_tokens().get('text_muted', '#8c8c9a')}; font-size: 14px; margin-top: 4px;"
            )
            schedule_layout.addWidget(self.duration_summary_label)
            self._update_duration_summary()

            self.routine_period_end_date = None

        elif self.task_type == "routine":
            # ── 마감기한 (날짜+시간 입력) ──────────────────────
            # ── 일반업무 수행 기간 (좌측: 시작 / 우측: 종료) ────────────────────
            routine_dates_row = QHBoxLayout()
            routine_dates_row.setSpacing(30)

            # L: 시작 섹션
            start_col = QVBoxLayout()
            start_col.setSpacing(5)
            self.start_label_widget = QLabel(t("dialog.task.start_day_routine"))
            start_col.addWidget(self.start_label_widget)

            dt_row = QHBoxLayout()
            dt_row.setSpacing(8)
            self.start_date = QDateEdit(self.initial_date)
            self.start_date.setCalendarPopup(True)
            self.start_date.setDisplayFormat("yyyy-MM-dd")
            self.start_date.setMinimumWidth(130)
            polish_calendar_popup(self.start_date)

            self.start_time = TimePickerWidget(self.initial_time)
            self._set_editor_height(self.start_date)
            dt_row.addWidget(self.start_date)
            dt_row.addWidget(self.start_time)
            dt_row.addStretch()
            start_col.addLayout(dt_row)
            routine_dates_row.addLayout(start_col, 1)

            # R: 종료 섹션 (컨테이너)
            if not self._is_modify:
                self.routine_end_container = QWidget()
                end_col = QVBoxLayout(self.routine_end_container)
                end_col.setContentsMargins(0, 0, 0, 0)
                end_col.setSpacing(5)

                end_lbl = QLabel(t("dialog.task.end_day_routine"))
                end_col.addWidget(end_lbl)

                self.routine_period_end_date = QDateEdit(self.initial_date.addDays(14))
                self.routine_period_end_date.setCalendarPopup(True)
                self.routine_period_end_date.setDisplayFormat("yyyy-MM-dd")
                self.routine_period_end_date.setMinimumWidth(130)
                polish_calendar_popup(self.routine_period_end_date)
                self._set_editor_height(self.routine_period_end_date)

                end_edit_row = QHBoxLayout()
                end_edit_row.addWidget(self.routine_period_end_date)
                end_edit_row.addStretch()
                end_col.addLayout(end_edit_row)

                routine_dates_row.addWidget(self.routine_end_container, 1)
            else:
                self.routine_period_end_date = None

            schedule_layout.addLayout(routine_dates_row)

            # 생성 예정 미리보기
            self.routine_preview_label = QLabel()
            self.routine_preview_label.setStyleSheet(
                f"color: {self._ui_tokens().get('accent', '#4da6ff')}; font-size: 14px; margin-top: 5px;"
            )
            schedule_layout.addWidget(self.routine_preview_label)

            self.end_date = None
            self.end_time = None

        else:
            self.end_date = None
            self.end_time = None
            self.routine_period_end_date = None

        layout.addWidget(schedule_group)

        if self.task_type == "routine":
            self.start_date.dateChanged.connect(self._update_routine_mode_ui)
            if not self._is_modify and self.routine_period_end_date is not None:
                self.routine_period_end_date.dateChanged.connect(self._update_routine_preview)
        self.start_date.dateChanged.connect(self._handle_start_datetime_changed)
        self.start_time.timeChanged.connect(self._handle_start_datetime_changed)
        if self.task_type == "schedule":
            self.end_date.dateChanged.connect(self._handle_end_datetime_changed)
            self.end_time.timeChanged.connect(self._handle_end_datetime_changed)
        if (
            self.task_type == "routine"
            and not self._is_modify
            and self.routine_period_end_date is not None
        ):
            self.start_date.dateChanged.connect(
                lambda d: self.routine_period_end_date.setMinimumDate(d)
            )
            self.routine_period_end_date.setMinimumDate(self.start_date.date())

        # ── 부가 정보 (담당자/장소) ───────────────────────────────────────
        layout.addWidget(self._create_additional_info_section())

        # ── 알람 설정 (기본 탭 하단) ────────────────────────────────────────
        layout.addWidget(self._build_alarm_section())

        layout.addStretch()
        return w

    # ── Cycle type selector ───────────────────────────────────────────────
    def _build_cycle_type_selector(self):
        """일반업무 유형 및 세부 반복 설정 통합 위젯"""
        outer_layout = QVBoxLayout()
        outer_layout.setSpacing(6)
        outer_layout.setContentsMargins(0, 2, 0, 2)

        # 제목 (그룹박스 대신 간단한 텍스트)
        mode_header = QLabel(t("dialog.recurrence.header"))
        mode_header.setStyleSheet(
            f"color: {self._ui_tokens().get('text_muted', '#7f8a99')}; font-size: 13px; font-weight: bold;"
        )
        outer_layout.addWidget(mode_header)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        self.routine_mode_group = QButtonGroup()
        self.single_task_radio = QRadioButton(t("dialog.recurrence.single"))
        self.repeat_task_radio = QRadioButton(t("dialog.recurrence.repeat"))
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
        self.rule_mode_combo.addItem(t("dialog.recurrence.specific_date"), "day_of_month")
        self.rule_mode_combo.addItem(t("dialog.recurrence.nth_weekday"), "nth_weekday")
        self.rule_mode_combo.setFixedWidth(116)

        self.repeat_mode_controls = QWidget()
        repeat_mode_layout = QHBoxLayout(self.repeat_mode_controls)
        repeat_mode_layout.setContentsMargins(0, 0, 0, 0)
        repeat_mode_layout.setSpacing(8)
        repeat_mode_layout.addWidget(self.repeat_cycle_combo)
        repeat_mode_layout.addWidget(self.rule_mode_combo)

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

        self.routine_wizard_group = QGroupBox(t("dialog.recurrence.wizard_title"))
        inner_layout = QVBoxLayout()
        inner_layout.setSpacing(8)

        self.recurrence_form = QGridLayout()
        self.recurrence_form.setHorizontalSpacing(10)
        self.recurrence_form.setVerticalSpacing(8)
        self.recurrence_form.setColumnStretch(1, 1)
        self.recurrence_form.setColumnStretch(3, 1)

        self.lbl_slot = QLabel(t("dialog.recurrence.slot_month"))
        self.slot_combo = QComboBox()

        self.lbl_day = QLabel(t("dialog.recurrence.day_label"))
        self.day_combo = QComboBox()
        for d in range(1, 32):
            self.day_combo.addItem(f"{d}{t('dialog.recurrence.day_unit')}", d)
        self.day_combo.addItem(t("dialog.recurrence.last_day"), "last")

        self.nth_combo = QComboBox()
        for t_key, v in [
            ("dialog.recurrence.nth_first", 1),
            ("dialog.recurrence.nth_second", 2),
            ("dialog.recurrence.nth_third", 3),
            ("dialog.recurrence.nth_fourth", 4),
            ("dialog.recurrence.nth_fifth", 5),
            ("dialog.recurrence.nth_last", "last"),
        ]:
            self.nth_combo.addItem(t(t_key), v)
        self.weekday_combo = QComboBox()
        for i, name in enumerate(get_weekday_names()):
            self.weekday_combo.addItem(name, i)

        self.lbl_rule_value = QLabel(t("dialog.recurrence.specific_date"))
        self.rule_value_wrap = QWidget()
        self.rule_value_layout = QHBoxLayout(self.rule_value_wrap)
        self.rule_value_layout.setContentsMargins(0, 0, 0, 0)
        self.rule_value_layout.setSpacing(6)
        self.rule_value_layout.addWidget(self.nth_combo)
        self.rule_value_layout.addWidget(self.weekday_combo)

        self.lbl_rule_value = QLabel(t("dialog.recurrence.day_label"))

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

    # ── Checklist (dispatches to DB or UI based on mode) ─────────────────
    def _refresh_checklist_display(self):
        """체크리스트 표기/진행률 동기화"""
        if self._is_modify:
            self._load_checklist_items()
            return
        # UI-only mode (create)
        total = self.checklist_widget.count()
        completed = 0
        for i in range(total):
            item = self.checklist_widget.item(i)
            raw_text = item.data(Qt.ItemDataRole.UserRole) or ""
            is_checked = bool(item.data(Qt.ItemDataRole.UserRole + 1))
            prefix = (
                f"{i + 1}. " if getattr(self, "checklist_display_type", "list") == "process" else ""
            )
            checkbox = "☑" if is_checked else "☐"
            item.setText(f"{checkbox} {prefix}{raw_text}")
            if is_checked:
                completed += 1
        percentage = (completed / total * 100) if total > 0 else 0
        if hasattr(self, "progress_label"):
            self.progress_label.setText(
                f"{t('dialog.checklist.progress')}: {completed}/{total} ({percentage:.1f}%)"
            )

    def _add_checklist_item(self):
        from PyQt6.QtWidgets import QInputDialog

        text, ok = QInputDialog.getText(
            self, t("dialog.checklist.add_item"), t("dialog.checklist.item_content")
        )
        if not ok or not text.strip():
            return
        if self._is_modify:
            order = self.checklist_widget.count()
            checklist_repo.add_checklist_item(
                self.task_id, text.strip(), order, display_type=self.checklist_display_type
            )
            self._load_checklist_items()
        else:
            self._add_checklist_item_to_ui(text.strip())

    def _add_checklist_item_to_ui(self, text):
        item = QListWidgetItem("")
        item.setData(Qt.ItemDataRole.UserRole, text)
        item.setData(Qt.ItemDataRole.UserRole + 1, False)
        self.checklist_widget.addItem(item)
        self._refresh_checklist_display()

    def _remove_checklist_item(self):
        current_item = self.checklist_widget.currentItem()
        if not current_item:
            return
        if self._is_modify:
            link_id = current_item.data(Qt.ItemDataRole.UserRole)
            reply = QMessageBox.question(
                self,
                t("dialog.checklist.delete_title"),
                t("dialog.checklist.delete_confirm"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                conn = common_repo.get_connection()
                if conn:
                    cur = conn.cursor()
                    cur.execute("DELETE FROM task_checklist_link WHERE id=?", (link_id,))
                    conn.commit()
                    self._load_checklist_items()
        else:
            self.checklist_widget.takeItem(self.checklist_widget.row(current_item))
            self._refresh_checklist_display()

    def _toggle_checklist_item(self, item):
        if self._is_modify:
            link_id = item.data(Qt.ItemDataRole.UserRole)
            checklist_repo.toggle_checklist_item(link_id)
            self._load_checklist_items()
        else:
            current_state = bool(item.data(Qt.ItemDataRole.UserRole + 1))
            item.setData(Qt.ItemDataRole.UserRole + 1, not current_state)
            self._refresh_checklist_display()

    def _load_checklist_from_template(self, template_id):
        if self._is_modify:
            template = checklist_template_repo.get_checklist_template(template_id)
            display_type = (template or {}).get("checklist_type", "list")
            self.checklist_display_type = display_type
            items = checklist_template_repo.get_checklist_items(template_id)
            current_count = self.checklist_widget.count()
            for item in items:
                checklist_repo.add_checklist_item(
                    self.task_id,
                    item["item_text"],
                    current_count,
                    display_type=display_type,
                )
                current_count += 1
            checklist_repo.set_task_checklist_display_type(self.task_id, display_type)
            self._load_checklist_items()
            QMessageBox.information(
                self, t("dialog.checklist.done"), f"{len(items)}{t('dialog.checklist.items_added')}"
            )
        else:
            template = checklist_template_repo.get_checklist_template(template_id)
            self.checklist_display_type = (template or {}).get("checklist_type", "list")
            items = checklist_template_repo.get_checklist_items(template_id)
            for item in items:
                item_text = item["item_text"]
                if item.get("is_required"):
                    item_text = f"{t('dialog.checklist.required')} {item_text}"
                tooltip_parts = []
                if item.get("item_description"):
                    tooltip_parts.append(
                        f"{t('dialog.checklist.description', '설명')}: {item['item_description']}"
                    )
                if item.get("item_guide"):
                    tooltip_parts.append(
                        f"{t('dialog.checklist.guide', '안내')}: {item['item_guide']}"
                    )
                list_item = QListWidgetItem("")
                list_item.setData(Qt.ItemDataRole.UserRole, item_text)
                list_item.setData(Qt.ItemDataRole.UserRole + 1, False)
                if tooltip_parts:
                    list_item.setToolTip("\n\n".join(tooltip_parts))
                self.checklist_widget.addItem(list_item)
            self._refresh_checklist_display()
            QMessageBox.information(
                self, t("dialog.checklist.done"), f"{len(items)}{t('dialog.checklist.items_added')}"
            )

    def _apply_prefill(self, data: dict):
        """Prefill fields from a dictionary (e.g. when copying from subscription)."""
        if data.get("name"):
            self.name_edit.setText(data["name"])
        if data.get("memo"):
            self.memo_edit.setPlainText(data["memo"])
        if data.get("priority"):
            idx = self.priority_combo.findData(data["priority"])
            if idx >= 0:
                self.priority_combo.setCurrentIndex(idx)
        if data.get("location") and hasattr(self, "location_edit"):
            self.location_edit.setText(data["location"])
        if data.get("assignee") and hasattr(self, "assignee_edit"):
            self.assignee_edit.setText(data["assignee"])
        if data.get("bg_color"):
            self.color_swatch.set_color(data["bg_color"])

    # ── Template loader (create mode) ─────────────────────────────────────
    def _load_from_template(self, template_id):
        self.template_id = template_id
        template = routine_repo.get_routine_template(template_id)
        if not template:
            return

        self.name_edit.setText(template["name"])
        if template.get("priority"):
            idx = self.priority_combo.findData(template["priority"])
            if idx >= 0:
                self.priority_combo.setCurrentIndex(idx)
        if template.get("bg_color"):
            self.color_swatch.set_color(template["bg_color"])
        if template.get("description") and self.memo_edit:
            self.memo_edit.setPlainText(template["description"])
        if template.get("location") and hasattr(self, "location_edit"):
            self.location_edit.setText(template["location"])
        if template.get("assignee") and hasattr(self, "assignee_edit"):
            self.assignee_edit.setText(template["assignee"])

        self._load_template_checklist(template_id)
        self._apply_routine_recurrence(
            template.get("cycle_type") or "single", template.get("recurrence")
        )

    def _load_template_checklist(self, template_id):
        conn = common_repo.get_connection()
        if not conn:
            return
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ct.id, ct.checklist_type FROM checklist_template ct
            JOIN routine_template rt ON ct.name = rt.name
            WHERE rt.id = ?
        """,
            (template_id,),
        )
        row = cur.fetchone()
        if not row:
            return
        checklist_id = row["id"]
        self.checklist_display_type = (
            (row["checklist_type"] or "list") if "checklist_type" in row else "list"
        )
        cur.execute(
            """
            SELECT item_text, item_order FROM checklist_item
            WHERE checklist_id = ? ORDER BY item_order
        """,
            (checklist_id,),
        )
        items = cur.fetchall()
        self.checklist_widget.clear()
        for item in items:
            self._add_checklist_item_to_ui(item["item_text"])

    # ── Routine preview ────────────────────────────────────────────────────
    def _update_routine_preview(self):
        """반복업무 생성 예정 건수 미리보기 업데이트"""
        if not hasattr(self, "routine_preview_label"):
            return
        if not hasattr(self, "repeat_task_radio") or self.single_task_radio.isChecked():
            self.routine_preview_label.setText("")
            return
        if not hasattr(self, "routine_period_end_date") or self.routine_period_end_date is None:
            return
        cycle_type = self._get_routine_cycle_type()
        if cycle_type in (None, "single"):
            self.routine_preview_label.setText("")
            return
        start = self.start_date.date()
        end = self.routine_period_end_date.date()
        dates = self._iter_routine_dates(start, end, cycle_type)
        count = len(dates)
        tokens = self._ui_tokens()
        if count == 0:
            self.routine_preview_label.setText(t("dialog.recurrence.preview_none"))
            self.routine_preview_label.setStyleSheet(
                f"color: {tokens.get('danger_hex', '#ff6b6b')}; font-size: 14px;"
            )
        elif count > 12:
            first = dates[0].toString("M/d")
            last = dates[-1].toString("M/d")
            self.routine_preview_label.setText(
                f"📋 {count} {t('dialog.checklist.done')}  ({first} → {last})"
            )
            self.routine_preview_label.setStyleSheet(
                f"color: {tokens.get('warning_hex', '#ffd34d')}; font-size: 14px;"
            )
        else:
            date_strs = [d.toString("M/d") for d in dates]
            self.routine_preview_label.setText(
                f"📋 {count} {t('dialog.checklist.done')}: {', '.join(date_strs)}"
            )
            self.routine_preview_label.setStyleSheet(
                f"color: {tokens.get('accent', '#4da6ff')}; font-size: 14px;"
            )

    # ── Routine date iteration helpers ────────────────────────────────────
    def _iter_routine_dates(self, start_date: QDate, end_date: QDate, cycle_type: str):
        if not start_date.isValid() or not end_date.isValid() or end_date < start_date:
            return []

        def _next_date(d: QDate) -> QDate:
            if cycle_type == "daily":
                return d.addDays(1)
            if cycle_type == "weekly":
                return d.addDays(7)
            if cycle_type == "monthly":
                return d.addMonths(1)
            if cycle_type == "quarterly":
                return d.addMonths(3)
            if cycle_type == "half_yearly":
                return d.addMonths(6)
            if cycle_type == "yearly":
                return d.addYears(1)
            return d.addDays(1)

        dates = []
        cur = QDate(start_date)
        guard = 0
        while cur <= end_date and guard < 2000:
            dates.append(QDate(cur))
            nxt = _next_date(cur)
            if nxt <= cur:
                nxt = cur.addDays(1)
            cur = nxt
            guard += 1
        return dates

    def _routine_exists_for_date(self, name: str, target_date_str: str) -> bool:
        conn = common_repo.get_connection()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM unified_task WHERE type='routine' AND name=? AND target_date=? LIMIT 1",
            (name, target_date_str),
        )
        return cur.fetchone() is not None

    def _copy_checklist_to_task(self, task_id: int):
        # checklist는 routine에만 존재 — schedule은 위젯 없음
        if not hasattr(self, "checklist_widget"):
            return
        for i in range(self.checklist_widget.count()):
            item = self.checklist_widget.item(i)
            item_text = item.data(Qt.ItemDataRole.UserRole)
            link_id = checklist_repo.add_checklist_item(
                task_id, item_text, i, display_type=self.checklist_display_type
            )
            if link_id and item.data(Qt.ItemDataRole.UserRole + 1):
                checklist_repo.toggle_checklist_item(link_id)

    # ── Save / Delete (dispatches to create or modify logic) ─────────────
    def save_data(self):
        # 중복 클릭 가드: DB commit이 백그라운드 sync와 lock 경합 시 버퍼링되는
        # 동안 큐잉된 추가 클릭이 중복 등록을 일으키는 것을 방지
        if getattr(self, "_is_saving", False):
            return
        self._is_saving = True
        if hasattr(self, "save_btn"):
            self.save_btn.setEnabled(False)
        try:
            if self._is_modify:
                self._save_changes()
            else:
                self._create_task()
        finally:
            # accept()로 닫히지 않은 경우(검증 실패 등) 재시도 허용
            self._is_saving = False
            if hasattr(self, "save_btn"):
                self.save_btn.setEnabled(True)

    def _create_task(self):
        """Create mode: save new task(s) to DB."""
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, t("dialog.task.entry_error"), t("dialog.task.name_required"))
            return

        priority = self.priority_combo.currentData()
        status_val = self.status_combo.currentData()

        deadline_dt = f"{self.start_date.date().toString('yyyy-MM-dd')} {self.start_time.time().toString('HH:mm:ss')}"

        end_date_str = None
        if hasattr(self, "end_date") and self.end_date:
            end_date_str = f"{self.end_date.date().toString('yyyy-MM-dd')} {self.end_time.time().toString('HH:mm:ss')}"

        selected_alarms = [str(mins) for mins, cb in self.alarm_checks.items() if cb.isChecked()]
        alarm_time_str = ",".join(selected_alarms) if selected_alarms else None

        cycle_type = None
        recurrence = None
        if self.task_type == "routine":
            cycle_type = self._get_routine_cycle_type()
            recurrence = "mode=single" if cycle_type == "single" else None

        task_data = {
            "name": self.name_edit.text().strip(),
            "type": self.task_type,
            "priority": priority,
            "status": status_val,
            "deadline": deadline_dt,
            "end_date": end_date_str,
            "alarm_time": alarm_time_str,
            "bg_color": self.color_swatch.selected_color() or None,
            "icon": None,
            "recurrence": recurrence,
            "template_id": self.template_id if self.task_type == "routine" else None,
            "target_date": self.start_date.date().toString("yyyy-MM-dd")
            if self.task_type == "routine"
            else None,
            "cycle_type": cycle_type,
            "all_day": 1
            if hasattr(self, "all_day_check") and self.all_day_check.isChecked()
            else 0,
            "description": self.memo_edit.toPlainText()
            if hasattr(self, "memo_edit") and self.memo_edit
            else None,
            "location": self.location_edit.text().strip()
            if hasattr(self, "location_edit")
            else None,
            "assignee": self.assignee_edit.text().strip()
            if hasattr(self, "assignee_edit")
            else None,
            "calendar_id": None
            if self.task_type == "routine"
            else self._get_selected_calendar_id(),
            "tags": self.tags_edit.text().strip()
            if self.task_type == "routine" and hasattr(self, "tags_edit")
            else None,
        }

        created_ids = []
        skipped = 0

        is_repeat_routine = (
            self.task_type == "routine"
            and hasattr(self, "repeat_task_radio")
            and self.repeat_task_radio.isChecked()
            and cycle_type not in (None, "single")
        )

        if is_repeat_routine:
            period_end = (
                self.routine_period_end_date.date()
                if self.routine_period_end_date
                else self.start_date.date()
            )
            if period_end < self.start_date.date():
                QMessageBox.warning(
                    self, t("dialog.task.entry_error"), t("dialog.task.routine_end_error")
                )
                return

            for d in self._iter_routine_dates(self.start_date.date(), period_end, cycle_type):
                target_date = d.toString("yyyy-MM-dd")
                if self._routine_exists_for_date(task_data["name"], target_date):
                    skipped += 1
                    continue
                item_payload = dict(task_data)
                item_payload["target_date"] = target_date
                item_payload["deadline"] = (
                    f"{target_date} {self.start_time.time().toString('HH:mm:ss')}"
                )
                item_payload["end_date"] = None
                task_id = task_repo.create_unified_task(item_payload)
                if task_id:
                    created_ids.append(task_id)
                    self._copy_checklist_to_task(task_id)
        else:
            task_id = task_repo.create_unified_task(task_data)
            if task_id:
                created_ids.append(task_id)
                self._copy_checklist_to_task(task_id)

        if not created_ids:
            QMessageBox.critical(
                self, t("dialog.task.save_failed"), t("dialog.task.no_tasks_saved")
            )
            return

        self._saved_task_id = created_ids[0]
        task_data["id"] = created_ids[0]
        self.task_added.emit(task_data)

        if is_repeat_routine:
            msg = t("dialog.task.routine_count_msg").format(count=len(created_ids))
            QMessageBox.information(self, t("dialog.task.reg_done"), msg)
        else:
            success_msg = (
                t("dialog.task.routine_reg_success")
                if self.task_type == "routine"
                else t("dialog.task.schedule_reg_success")
            )
            QMessageBox.information(self, t("dialog.task.save_done"), success_msg)
        self.accept()

    # ── Modify mode: data loading ─────────────────────────────────────────
    def _load_data(self):
        """수정 모드: 기존 데이터를 UI에 로드"""
        self.name_edit.setText(self.task_data.get("name", ""))

        prio_val = self.task_data.get("priority", "normal")
        for i in range(self.priority_combo.count()):
            if self.priority_combo.itemData(i) == prio_val:
                self.priority_combo.setCurrentIndex(i)
                break

        status_val = self.task_data.get("status", "pending")
        for i in range(self.status_combo.count()):
            if self.status_combo.itemData(i) == status_val:
                self.status_combo.setCurrentIndex(i)
                break

        if self.task_data.get("deadline"):
            dt_str = self.task_data["deadline"]
            dt = None
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]:
                try:
                    dt = datetime.strptime(dt_str[:19] if len(fmt) > 16 else dt_str[:16], fmt)
                    break
                except ValueError:
                    continue
            if dt:
                self.start_date.setDate(QDate(dt.year, dt.month, dt.day))
                self.start_time.setTime(QTime(dt.hour, dt.minute, dt.second if dt.second else 0))

        if hasattr(self, "end_date") and self.end_date and self.task_data.get("end_date"):
            dt_str = self.task_data["end_date"]
            dt = None
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]:
                try:
                    dt = datetime.strptime(dt_str[:19] if len(fmt) > 16 else dt_str[:16], fmt)
                    break
                except ValueError:
                    continue
            if dt:
                self.end_date.setDate(QDate(dt.year, dt.month, dt.day))
                self.end_time.setTime(QTime(dt.hour, dt.minute, dt.second if dt.second else 0))

        if self.task_data.get("bg_color"):
            self.color_swatch.set_color(self.task_data["bg_color"])

        alarm_raw = self.task_data.get("alarm_time")
        if alarm_raw:
            try:
                for mins_str in alarm_raw.split(","):
                    mins = int(mins_str.strip())
                    if mins in self.alarm_checks:
                        self.alarm_checks[mins].setChecked(True)
            except Exception:
                pass

        if self.task_type == "routine":
            self._apply_routine_recurrence(
                self.task_data.get("cycle_type") or "single",
                self.task_data.get("recurrence"),
            )

        memo_text = self.task_data.get("description") or self.task_data.get("memo")
        if self.memo_edit and memo_text:
            self.memo_edit.setPlainText(memo_text)

        # 태그 복원 (일반업무)
        if self.task_type == "routine" and hasattr(self, "tags_edit"):
            self.tags_edit.setText(self.task_data.get("tags") or "")

        # 캘린더 선택 복원 (일정만)
        if self.task_type != "routine":
            cal_id = self.task_data.get("calendar_id")
            if cal_id and hasattr(self, "calendar_combo"):
                for i in range(self.calendar_combo.count()):
                    if self.calendar_combo.itemData(i) == cal_id:
                        self.calendar_combo.setCurrentIndex(i)
                        break

        if self.task_data.get("location") and hasattr(self, "location_edit"):
            self.location_edit.setText(self.task_data["location"])

        if hasattr(self, "all_day_check"):
            is_all_day = bool(self.task_data.get("all_day", 0))
            self.all_day_check.setChecked(is_all_day)
            self._on_all_day_toggled(is_all_day)
        if self.task_data.get("assignee") and hasattr(self, "assignee_edit"):
            self.assignee_edit.setText(self.task_data["assignee"])

        # 체크리스트는 routine에만 존재 — schedule은 위젯 미생성 (AttributeError 방지)
        if self.task_type == "routine":
            self._load_checklist_templates()
            self._load_checklist_items()

        if self.task_type == "schedule" and self.end_date is not None and self.end_time is not None:
            self._sync_auto_end_duration_from_controls()
        self._update_duration_summary()
        self._update_alarm_summary()

    def _load_checklist_items(self):
        """수정 모드: DB에서 체크리스트 로드"""
        self.checklist_widget.clear()
        items = checklist_repo.get_task_checklist_items(self.task_id)
        if items:
            self.checklist_display_type = items[0].get("display_type", "list")
        else:
            self.checklist_display_type = "list"

        for i, item in enumerate(items):
            checkbox = "✓" if item["is_completed"] else "○"
            prefix = f"{i + 1}. " if self.checklist_display_type == "process" else ""
            text = f"{checkbox} {prefix}{item['item_text']}"
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.ItemDataRole.UserRole, item["id"])
            list_item.setData(Qt.ItemDataRole.UserRole + 1, item["is_completed"])
            self.checklist_widget.addItem(list_item)

        self._update_progress()

    def _update_progress(self):
        """수정 모드: DB 진행률 업데이트"""
        progress = checklist_repo.get_task_checklist_progress(self.task_id)
        total = progress["total"]
        completed = progress["completed"]
        percentage = (completed / total * 100) if total > 0 else 0
        self.progress_label.setText(
            f"{t('dialog.checklist.progress')} {completed}/{total} ({percentage:.1f}%)"
        )

    # ── Modify mode: save / delete ────────────────────────────────────────
    def _save_changes(self):
        """수정 모드: 변경사항 저장"""
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, t("dialog.task.entry_error"), t("dialog.task.name_required"))
            return

        priority = self.priority_combo.currentData()
        status_val = self.status_combo.currentData()

        deadline_dt = f"{self.start_date.date().toString('yyyy-MM-dd')} {self.start_time.time().toString('HH:mm:ss')}"

        end_date_str = None
        if hasattr(self, "end_date") and self.end_date:
            end_date_str = f"{self.end_date.date().toString('yyyy-MM-dd')} {self.end_time.time().toString('HH:mm:ss')}"

        selected_alarms = [str(mins) for mins, cb in self.alarm_checks.items() if cb.isChecked()]
        alarm_time = ",".join(selected_alarms) if selected_alarms else ""

        updates = {
            "name": self.name_edit.text().strip(),
            "priority": priority,
            "status": status_val,
            "deadline": deadline_dt,
            "end_date": end_date_str,
            "target_date": self.start_date.date().toString("yyyy-MM-dd")
            if self.task_type == "routine"
            else None,
            "alarm_time": alarm_time,
            "bg_color": self.color_swatch.selected_color() or None,
            "icon": None,
            "all_day": 1
            if hasattr(self, "all_day_check") and self.all_day_check.isChecked()
            else 0,
            "description": self.memo_edit.toPlainText().strip()
            if hasattr(self, "memo_edit") and self.memo_edit
            else None,
            "location": self.location_edit.text().strip()
            if hasattr(self, "location_edit")
            else None,
            "assignee": self.assignee_edit.text().strip()
            if hasattr(self, "assignee_edit")
            else None,
            "calendar_id": None
            if self.task_type == "routine"
            else self._get_selected_calendar_id(),
            "tags": self.tags_edit.text().strip()
            if self.task_type == "routine" and hasattr(self, "tags_edit")
            else None,
        }

        if self.task_type == "routine":
            updates["cycle_type"] = self._get_routine_cycle_type()
            updates["recurrence"] = self._build_recurrence_rule()
            updates["target_date"] = self.start_date.date().toString("yyyy-MM-dd")

        # ── Calendar move 처리 ─────────────────────────────────────────────
        # 캘린더 변경 시 Google 측에서도 이동이 일어나려면 _previous_gcal_calendar_id
        # 를 sync 페이로드에 전달하고, 기존 gcal_source/target_calendar_id 는 비워
        # 리졸버가 NEW calendar_id 로 매핑된 Google 캘린더를 사용하도록 한다.
        prev_gcal_cal_id = self.task_data.get("gcal_source_calendar_id") or self.task_data.get(
            "gcal_target_calendar_id"
        )
        prev_gcal_event_id = self.task_data.get("gcal_event_id")
        old_local_cal = str(self.task_data.get("calendar_id") or "")
        new_local_cal = str(updates.get("calendar_id") or "")
        calendar_changed = bool(old_local_cal != new_local_cal and prev_gcal_event_id)

        # gcal → 비-gcal (local::/ics::) 이동 감지
        moving_off_gcal = (
            calendar_changed
            and new_local_cal
            and "::" in new_local_cal
            and not new_local_cal.startswith("gcal::")
        )

        if moving_off_gcal:
            reply = QMessageBox.question(
                self,
                t("dialog.task.purge_gcal_title", "구글 캘린더에서 제거"),
                t(
                    "dialog.task.purge_gcal_confirm",
                    "이 일정을 로컬 캘린더로 옮기면 구글 캘린더에서는 삭제됩니다.\n"
                    "(로컬 일정으로만 유지되며 동기화되지 않습니다.)\n\n계속하시겠습니까?",
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return  # abort save — keep the existing gcal binding

            # Queue delete for the previous Google event
            try:
                from calendar_app.infrastructure.db import task_repo as _tr_purge

                _tr_purge.queue_gcal_delete(
                    prev_gcal_event_id,
                    gcal_calendar_id=prev_gcal_cal_id,
                    local_task_id=self.task_id,
                )
            except Exception as e:
                print(f"GCal purge enqueue error: {e}")

            # Clear gcal binding on the local task so future syncs ignore it
            updates["gcal_event_id"] = None
            updates["gcal_source_calendar_id"] = None
            updates["gcal_target_calendar_id"] = None
            updates["gcal_dirty"] = 0
            updates["gcal_sync_error"] = None

            # Skip the normal sync_task_to_google path — task is now local-only
            sync_payload = None
        else:
            sync_payload = dict(self.task_data)
            sync_payload.update(updates)
            sync_payload["gcal_event_id"] = self.task_data.get("gcal_event_id")
            if calendar_changed:
                if prev_gcal_cal_id:
                    sync_payload["_previous_gcal_calendar_id"] = prev_gcal_cal_id
                # 리졸버가 NEW calendar_id 를 사용하도록 OLD gcal 라우팅 키 제거
                sync_payload.pop("gcal_source_calendar_id", None)
                sync_payload.pop("gcal_target_calendar_id", None)

        if sync_payload is not None:
            try:
                _app = self.parent()
                if _app and hasattr(_app, "gcal_sync"):
                    queue_task_sync_to_google(_app, sync_payload)
            except Exception as e:
                print(f"GCal sync error in modify dialog: {e}")
        else:
            # Trigger sync to drain the delete-queue (Google event removal)
            try:
                _app = self.parent()
                if _app and hasattr(_app, "sync_google_calendar"):
                    _app.sync_google_calendar(silent=True)
            except Exception as e:
                print(f"GCal purge sync trigger error: {e}")

        success = task_repo.update_unified_task(self.task_id, updates)
        if success:
            updates["id"] = self.task_id
            self.task_modified.emit(updates)
            QMessageBox.information(self, t("dialog.task.save_done"), t("dialog.task.mod_success"))
            self.accept()
        else:
            QMessageBox.critical(self, t("dialog.task.save_failed"), t("dialog.task.save_error_db"))

    def _delete_task(self):
        type_str = t("panel.routine") if self.task_type == "routine" else t("panel.today_schedule")
        msg = t("dialog.task.del_confirm_specific").format(type=type_str)
        reply = QMessageBox.question(
            self,
            t("dialog.task.del_title"),
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self.task_type == "schedule":
                try:
                    gcal_event_id = self.task_data.get("gcal_event_id")
                    queue_task_delete_from_google(self, gcal_event_id, local_task_id=self.task_id)
                except Exception as e:
                    print(f"GCal delete error in modify dialog: {e}")
            success = task_repo.delete_unified_task(self.task_id)
            if success:
                self.task_deleted.emit(self.task_id)
                QMessageBox.information(
                    self, t("dialog.task.del_title"), t("dialog.task.del_success")
                )
                self.accept()
            else:
                QMessageBox.critical(self, t("dialog.task.save_failed"), t("dialog.task.del_fail"))

    def _on_all_day_toggled(self, checked):
        """종합일정(종일) 선택 시 시간 입력 위젯 활성/비활성"""
        if self.task_type == "schedule":
            if hasattr(self, "start_time") and self.start_time:
                self.start_time.setVisible(not checked)
            if hasattr(self, "end_time") and self.end_time:
                self.end_time.setVisible(not checked)

            if hasattr(self, "start_time_shortcuts"):
                self.start_time_shortcuts.setVisible(not checked)
            if hasattr(self, "end_time_shortcuts"):
                # 종일 일정이어도 +1일 등의 날짜 조정은 유용할 수 있으나,
                # 사용자의 요청은 "시간 입력 안하고 날짜만 입력"이므로 일단 숨깁니다.
                self.end_time_shortcuts.setVisible(not checked)

        elif self.task_type == "routine":
            pass

    # ── Calendar selector helpers ─────────────────────────────────────────

    def _build_calendar_selector(self, layout):
        """캘린더 선택 드롭다운을 layout에 추가합니다."""
        cal_row = QHBoxLayout()
        cal_row.setContentsMargins(0, 0, 0, 0)
        cal_row.setSpacing(6)

        lbl = QLabel(t("dialog.task.calendar", "캘린더"))
        lbl.setStyleSheet(
            f"color: {self._ui_tokens().get('text_muted', '#7f8a99')}; font-size: 13px; font-weight: 700;"
        )
        lbl.setFixedWidth(52)
        cal_row.addWidget(lbl)

        self.calendar_combo = QComboBox()
        self.calendar_combo.setMinimumHeight(30)
        self.calendar_combo.setMaximumHeight(32)
        tokens = self._ui_tokens()
        self.calendar_combo.setStyleSheet(
            f"QComboBox {{ background: {tokens.get('surface_item', '#1e2535')}; color: {tokens.get('text_primary', '#d7dbe3')}; border: 1px solid {tokens.get('border', '#2e3a4e')}; "
            "border-radius: 6px; padding: 4px 10px; } "
            "QComboBox::drop-down { border: none; } "
            f"QComboBox QAbstractItemView {{ background: {tokens.get('surface_item', '#1e2535')}; color: {tokens.get('text_primary', '#d7dbe3')}; "
            f"selection-background-color: {self._accent_rgba(0.22)}; border: 1px solid {tokens.get('border', '#2e3a4e')}; }}"
        )

        _TYPE_ICON = {"gcal": "🔵", "ics": "🌐", "local": "📁", "shared": "👥"}
        default_index = 0
        try:
            from calendar_app.infrastructure.db.calendar_repo import (
                get_default_calendar,
                list_calendars,
            )

            calendars = list_calendars(include_inactive=False)
            default_cal = get_default_calendar()
            default_id = default_cal["id"] if default_cal else None

            for i, cal in enumerate(calendars):
                # ICS 및 GCal reader는 쓰기 불가 → 비활성화
                is_readonly = cal.get("type") == "ics"
                icon = _TYPE_ICON.get(cal.get("type", "local"), "📁")
                label = f"{icon} {cal['name']}"
                self.calendar_combo.addItem(label, cal["id"])
                if is_readonly:
                    # QComboBox 아이템 비활성화
                    model = self.calendar_combo.model()
                    item = model.item(i)
                    if item:
                        item.setEnabled(False)
                if cal["id"] == default_id:
                    default_index = i

            # 캘린더가 한 개도 없으면 기본 로컬 캘린더를 자동 생성 후 추가
            if self.calendar_combo.count() == 0:
                from calendar_app.infrastructure.db.calendar_repo import upsert_calendar

                upsert_calendar(
                    "local::기본",
                    "local",
                    "기본",
                    color="#3c8cff",
                    is_default=True,
                    is_active=True,
                    is_visible=True,
                )
                self.calendar_combo.addItem("📁 기본", "local::기본")
                default_index = 0
        except Exception:
            self.calendar_combo.addItem("📁 기본", None)

        self.calendar_combo.setCurrentIndex(default_index)
        cal_row.addWidget(self.calendar_combo, 1)
        layout.addLayout(cal_row)

    def _get_selected_calendar_id(self) -> str | None:
        """현재 선택된 캘린더 ID를 반환합니다."""
        if not hasattr(self, "calendar_combo"):
            return None
        return self.calendar_combo.currentData()
