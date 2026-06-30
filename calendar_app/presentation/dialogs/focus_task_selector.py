from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from calendar_app.application import focus_usecases
from calendar_app.infrastructure.db import legacy_focus_repo
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import apply_common_dialog_style
from calendar_app.presentation.dialogs.pomodoro_settings_dialog import PomodoroSettingsPanel
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic


class FocusTaskSelectorDialog(QDialog):
    """Focus-mode task selector dialog."""

    def __init__(self, current_date, parent=None):
        super().__init__(parent)

        self.current_date = current_date

        self.selected_task_id = None

        self.selected_task_name = None

        self.settings = getattr(parent, "settings", None) or QSettings("kimhyojin", "Dark Calendar")

        apply_dialog_title(self, t("focus_selector.title"))

        apply_common_dialog_style(self, minimum_width=650, size=(720, 560))

        self._init_ui()

        self.load_tasks()
        self.load_logs()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        main_layout.setContentsMargins(15, 15, 15, 15)

        main_layout.setSpacing(10)

        self.tabs = QTabWidget()

        self.task_tab = QWidget()

        self.log_tab = QWidget()

        self.settings_tab = QWidget()

        self._init_task_tab()

        self._init_log_tab()

        self._init_settings_tab()

        self.tabs.addTab(self.task_tab, t("focus_selector.tab_tasks"))

        self.tabs.addTab(self.log_tab, t("focus_selector.tab_logs"))

        self.tabs.addTab(
            self.settings_tab,
            t(
                "focus_selector.tab_settings",
                t("menu.focus_timer_settings", "\U0001f345 Pomodoro Settings"),
            ),
        )

        self.tabs.currentChanged.connect(lambda idx: self.load_logs() if idx == 1 else None)

        main_layout.addWidget(self.tabs)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        main_layout.addWidget(sep)

        btn_layout = QHBoxLayout()

        btn_layout.addStretch()

        close_btn = QPushButton(t("common.close"))
        close_btn.setObjectName("ghost_btn")
        close_btn.clicked.connect(self.reject)

        btn_layout.addWidget(close_btn)

        main_layout.addLayout(btn_layout)

    def _init_task_tab(self):
        layout = QVBoxLayout(self.task_tab)

        layout.setContentsMargins(15, 15, 15, 15)

        layout.setSpacing(12)

        layout.addWidget(QLabel(t("focus_selector.pick_prompt")))

        filter_layout = QHBoxLayout()

        self.filter_group = QButtonGroup(self)

        for label, filter_val, checked in [
            (t("focus_selector.filter_today_directives"), "today_and_directives", True),
            (t("focus_selector.filter_today"), "today", False),
            (t("focus_selector.filter_urgent"), "urgent", False),
            (t("focus_selector.filter_all"), "all", False),
        ]:
            radio = QRadioButton(label)

            radio.setChecked(checked)

            radio.setProperty("filter", filter_val)

            self.filter_group.addButton(radio)

            filter_layout.addWidget(radio)

        filter_layout.addStretch()

        self.filter_group.buttonClicked.connect(self.load_tasks)

        layout.addLayout(filter_layout)

        self.task_list = QListWidget()

        self.task_list.itemDoubleClicked.connect(self.on_task_selected)

        layout.addWidget(self.task_list)

        btn_layout = QHBoxLayout()

        auto_btn = QPushButton(t("focus_selector.auto_pick"))
        auto_btn.setObjectName("ghost_btn")
        auto_btn.clicked.connect(self.on_auto_select)

        btn_layout.addWidget(auto_btn)

        btn_layout.addStretch()

        select_btn = QPushButton(t("focus_selector.select_done"))
        select_btn.setObjectName("primary_btn")
        select_btn.clicked.connect(self.on_task_selected)

        btn_layout.addWidget(select_btn)

        layout.addLayout(btn_layout)

    def _init_log_tab(self):
        layout = QVBoxLayout(self.log_tab)

        layout.setContentsMargins(15, 15, 15, 15)

        layout.setSpacing(12)

        layout.addWidget(QLabel(t("focus_selector.logs_recent")))

        self.log_summary_lbl = QLabel()
        self.log_summary_lbl.setStyleSheet("font-weight: bold; color: #4da6ff; margin: 5px 0;")
        self.log_summary_lbl.setWordWrap(True)
        layout.addWidget(self.log_summary_lbl)

        self.log_table = QTableWidget()

        self.log_table.setColumnCount(3)

        self.log_table.setHorizontalHeaderLabels(
            [
                t("focus_selector.col_datetime"),
                t("focus_selector.col_task"),
                t("focus_selector.col_duration"),
            ]
        )

        self.log_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        self.log_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        h = self.log_table.horizontalHeader()

        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self.log_table)

        btn_row = QHBoxLayout()

        btn_row.addStretch()

        refresh_btn = QPushButton(t("dialog.common.refresh"))
        refresh_btn.setObjectName("ghost_btn")
        refresh_btn.clicked.connect(self.load_logs)
        btn_row.addWidget(refresh_btn)

        self.delete_btn = QPushButton(t("common.delete", "Delete"))
        self.delete_btn.setObjectName("ghost_btn")
        self.delete_btn.setStyleSheet("color: #ff4d4d;")  # Reddish for delete
        self.delete_btn.clicked.connect(self.on_delete_log)
        btn_row.addWidget(self.delete_btn)

        layout.addLayout(btn_row)

    def _init_settings_tab(self):
        layout = QVBoxLayout(self.settings_tab)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        hint = QLabel(
            t(
                "focus_selector.settings_hint",
                "You can change Focus mode type and Pomodoro behavior here.",
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.pomodoro_settings_panel = PomodoroSettingsPanel(self.settings, self.settings_tab)
        layout.addWidget(self.pomodoro_settings_panel, 1)

        status_row = QHBoxLayout()
        self._settings_saved_label = QLabel("")
        status_row.addWidget(self._settings_saved_label, 1)

        save_btn = QPushButton(t("common.save", "Save"))
        save_btn.setObjectName("primary_btn")
        save_btn.clicked.connect(self._save_focus_settings)
        status_row.addWidget(save_btn)
        layout.addLayout(status_row)

    def _save_focus_settings(self):
        self.pomodoro_settings_panel.save_values()
        self._settings_saved_label.setText(
            t(
                "focus_selector.settings_saved",
                "Saved. New values will be used next time Focus Mode starts.",
            )
        )

    def open_settings_tab(self):
        idx = self.tabs.indexOf(self.settings_tab)
        if idx >= 0:
            self.tabs.setCurrentIndex(idx)

    def load_logs(self):
        # Update summary stats
        try:
            today_sessions, today_secs = focus_usecases.get_today_focus_stats(legacy_focus_repo)
            monthly_sessions, monthly_secs = focus_usecases.get_monthly_focus_stats(
                legacy_focus_repo
            )

            def fmt_time(s):
                h, r = divmod(s, 3600)
                m, _ = divmod(r, 60)
                if h > 0:
                    return t(
                        "focus.duration_hours_minutes", "{hours}h {minutes}m", hours=h, minutes=m
                    )
                return t("focus.duration_minutes", "{minutes}m", minutes=m)

            self.log_summary_lbl.setText(
                t(
                    "focus_selector.log_summary",
                    "오늘: {today_sessions}세션 ({today_time}) | 이번달: {month_sessions}세션 ({month_time})",
                    today_sessions=today_sessions,
                    today_time=fmt_time(today_secs),
                    month_sessions=monthly_sessions,
                    month_time=fmt_time(monthly_secs),
                )
            )
        except Exception:
            self.log_summary_lbl.setText("")

        logs = focus_usecases.get_focus_logs(legacy_focus_repo, limit=100)
        self.log_table.setRowCount(0)

        for log in logs:
            log_id = log[0]
            task_name = log[2]
            secs = log[3]
            dt_str = log[4]

            row = self.log_table.rowCount()
            self.log_table.insertRow(row)

            # Store ID in UserRole for deletion
            dt_item = QTableWidgetItem(str(dt_str))
            dt_item.setData(Qt.ItemDataRole.UserRole, log_id)
            self.log_table.setItem(row, 0, dt_item)

            self.log_table.setItem(
                row,
                1,
                QTableWidgetItem(task_name or t("focus_selector.deleted_task", "삭제된 작업")),
            )

            mins, s = divmod(int(secs or 0), 60)
            self.log_table.setItem(
                row, 2, QTableWidgetItem(t("focus_selector.duration", minutes=mins, seconds=s))
            )

            for col in (0, 2):
                it = self.log_table.item(row, col)
                if it:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

    def on_delete_log(self):
        from PyQt6.QtWidgets import QMessageBox

        row = self.log_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                t("focus_selector.delete_confirm_title", "기록 삭제"),
                t("focus_selector.delete_no_selection", "삭제할 항목을 먼저 선택하세요."),
            )
            return

        item = self.log_table.item(row, 0)
        if not item:
            return

        log_id = item.data(Qt.ItemDataRole.UserRole)
        if not log_id:
            return

        answer = QMessageBox.question(
            self,
            t("focus_selector.delete_confirm_title", "기록 삭제"),
            t("focus_selector.delete_confirm_msg", "이 집중 기록을 삭제하시겠습니까?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if answer == QMessageBox.StandardButton.Yes and focus_usecases.delete_focus_log(
            legacy_focus_repo, log_id
        ):
            self.load_logs()

    def load_tasks(self):
        self.task_list.clear()

        selected_filter = self.filter_group.checkedButton().property("filter")

        today_str = self.current_date.toString("yyyy-MM-dd")

        tasks = focus_usecases.get_filtered_focus_tasks(
            legacy_focus_repo, selected_filter, today_str
        )

        for task in tasks:
            task_id = task.get("id")

            task_name = task.get("name") or t("common.no_title")

            task_type = task.get("type", "schedule")

            deadline = task.get("deadline", "")

            type_icon_key = (
                ICON.DIRECTIVE
                if task_type == "directive"
                else (ICON.VIEW_CALENDAR if task_type == "schedule" else ICON.ALL_SCHEDULES)
            )

            deadline_text = f" ({str(deadline)[:10]})" if deadline else ""

            item = QListWidgetItem(f"{task_name}{deadline_text}")
            item.setIcon(_ic(type_icon_key))

            item.setData(Qt.ItemDataRole.UserRole, task_id)

            item.setData(Qt.ItemDataRole.UserRole + 1, task_name)

            self.task_list.addItem(item)

        if self.task_list.count() == 0:
            empty = QListWidgetItem(t("focus_selector.no_tasks"))

            empty.setFlags(Qt.ItemFlag.NoItemFlags)

            self.task_list.addItem(empty)

    def on_task_selected(self):
        item = self.task_list.currentItem()

        if item and item.flags() & Qt.ItemFlag.ItemIsEnabled:
            self.selected_task_id = item.data(Qt.ItemDataRole.UserRole)

            self.selected_task_name = item.data(Qt.ItemDataRole.UserRole + 1)

            self.accept()

    def on_auto_select(self):
        today_str = self.current_date.toString("yyyy-MM-dd")

        current_tasks = focus_usecases.get_filtered_focus_tasks(legacy_focus_repo, "all", today_str)

        task_id, task_name = focus_usecases.select_auto_focus_task(
            legacy_focus_repo,
            today_str,
            fallback_tasks=current_tasks,
        )

        if task_id:
            self.selected_task_id = task_id

            self.selected_task_name = task_name

            self.accept()

    def get_selected_task(self):
        return self.selected_task_id, self.selected_task_name
