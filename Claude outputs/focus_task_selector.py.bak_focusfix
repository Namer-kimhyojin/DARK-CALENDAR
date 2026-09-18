# -*- coding: utf-8 -*-

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from calendar_app.application import focus_usecases
from calendar_app.infrastructure.db import legacy_focus_repo
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_editor_styles import build_editor_text_style
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)
from calendar_app.presentation.dialogs.focus_history_panel import FocusHistoryPanel
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
        self._logs_loaded = False

        self.settings = getattr(parent, "settings", None) or QSettings("kimhyojin", "Dark Calendar")

        apply_dialog_title(self, t("focus_selector.title"))

        apply_common_dialog_style(self, minimum_width=650, size=(720, 560))
        self._ui_tokens = get_dialog_theme_tokens(settings=self.settings)

        self._init_ui()

        self.load_tasks()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        main_layout.setContentsMargins(15, 15, 15, 15)

        main_layout.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.setAccessibleName(t("focus_selector.title"))
        self.tabs.setAccessibleDescription(t("focus_selector.pick_prompt"))

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

        self.tabs.currentChanged.connect(self._on_tab_changed)

        main_layout.addWidget(self.tabs)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        main_layout.addWidget(sep)

        btn_layout = QHBoxLayout()

        btn_layout.addStretch()

        close_btn = QPushButton(t("common.close"))
        close_btn.setObjectName("ghost_btn")
        close_btn.setAccessibleName(close_btn.text())
        close_btn.setAutoDefault(False)
        close_btn.clicked.connect(self.reject)

        btn_layout.addWidget(close_btn)

        main_layout.addLayout(btn_layout)

    def _init_task_tab(self):
        layout = QVBoxLayout(self.task_tab)

        layout.setContentsMargins(15, 15, 15, 15)

        layout.setSpacing(12)

        prompt = QLabel(t("focus_selector.pick_prompt"))
        prompt.setWordWrap(True)
        prompt.setStyleSheet(
            build_editor_text_style(self._ui_tokens, tone="secondary", font_px=13, weight=500)
        )
        layout.addWidget(prompt)

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
        self.task_list.setAccessibleName(t("focus_selector.pick_prompt"))
        self.task_list.setAccessibleDescription(t("focus_selector.select_done"))
        self.task_list.itemDoubleClicked.connect(self.on_task_selected)

        layout.addWidget(self.task_list)

        btn_layout = QHBoxLayout()

        auto_btn = QPushButton(t("focus_selector.auto_pick"))
        auto_btn.setObjectName("ghost_btn")
        auto_btn.setAccessibleName(auto_btn.text())
        auto_btn.setAutoDefault(False)
        auto_btn.clicked.connect(self.on_auto_select)

        btn_layout.addWidget(auto_btn)

        btn_layout.addStretch()

        select_btn = QPushButton(t("focus_selector.select_done"))
        select_btn.setObjectName("primary_btn")
        select_btn.setAccessibleName(select_btn.text())
        select_btn.setDefault(True)
        select_btn.clicked.connect(self.on_task_selected)

        btn_layout.addWidget(select_btn)

        layout.addLayout(btn_layout)

    def _init_log_tab(self):
        layout = QVBoxLayout(self.log_tab)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        self.focus_history_panel = FocusHistoryPanel(
            self.log_tab,
            tokens=self._ui_tokens,
            metrics=get_dialog_metric_tokens(apply_overrides=True),
        )
        layout.addWidget(self.focus_history_panel, 1)

        # Compatibility aliases for callers and accessibility tests.
        self.log_summary_lbl = self.focus_history_panel.summary_label
        self.log_table = self.focus_history_panel.table
        self.delete_btn = self.focus_history_panel.delete_button

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
        hint.setStyleSheet(
            build_editor_text_style(self._ui_tokens, tone="secondary", font_px=13, weight=500)
        )
        layout.addWidget(hint)

        self.pomodoro_settings_panel = PomodoroSettingsPanel(self.settings, self.settings_tab)
        layout.addWidget(self.pomodoro_settings_panel, 1)

        status_row = QHBoxLayout()
        self._settings_saved_label = QLabel("")
        status_row.addWidget(self._settings_saved_label, 1)

        save_btn = QPushButton(t("common.save", "Save"))
        save_btn.setObjectName("primary_btn")
        save_btn.setAccessibleName(save_btn.text())
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
        self.focus_history_panel.reload()
        self._logs_loaded = True

    def _on_tab_changed(self, index):
        if index == self.tabs.indexOf(self.log_tab) and not self._logs_loaded:
            self.load_logs()

    def on_delete_log(self):
        self.focus_history_panel.delete_selected()

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
