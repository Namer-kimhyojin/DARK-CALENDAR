"""Bulk operations dialog for routine tasks."""

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from calendar_app.application import routine_advanced_service as routine_service
from calendar_app.infrastructure.db import checklist_repo, common_repo
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import apply_common_dialog_style


class RoutineBulkOperationsDialog(QDialog):
    """Bulk operations dialog for routines."""

    operations_completed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        apply_dialog_title(self, t("dialog.routine_bulk.title"))

        apply_common_dialog_style(self, minimum_width=1000)
        self.resize(1000, 700)

        self.init_ui()

        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout()

        layout.setContentsMargins(15, 15, 15, 15)

        # ???꾩젽

        self.tabs = QTabWidget()

        self.tabs.addTab(self._build_bulk_tab(), t("dialog.routine_bulk.tab_bulk"))

        self.tabs.addTab(self._build_copy_tab(), t("dialog.routine_bulk.tab_copy"))

        layout.addWidget(self.tabs)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        close_btn = QPushButton(t("common.close"))
        close_btn.setObjectName("ghost_btn")
        close_btn.clicked.connect(self.accept)

        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def _build_bulk_tab(self):
        """Build bulk operations tab."""

        widget = QWidget()

        layout = QVBoxLayout(widget)

        # ?꾪꽣 ?곸뿭

        filter_group = QGroupBox(t("dialog.routine_bulk.filter"))

        filter_layout = QHBoxLayout()

        filter_layout.addWidget(QLabel(t("dialog.routine_bulk.cycle")))

        self.filter_cycle = QComboBox()

        self.filter_cycle.addItem(t("dialog.routine_bulk.all_cycles"), None)

        self.filter_cycle.addItem(t("recurrence.weekly"), "weekly")

        self.filter_cycle.addItem(t("recurrence.monthly"), "monthly")

        self.filter_cycle.addItem(t("recurrence.quarterly"), "quarterly")

        self.filter_cycle.addItem(t("recurrence.half_yearly"), "half_yearly")

        self.filter_cycle.addItem(t("recurrence.yearly"), "yearly")

        filter_layout.addWidget(self.filter_cycle)

        filter_layout.addWidget(QLabel(t("dialog.routine_bulk.status")))

        self.filter_status = QComboBox()

        self.filter_status.addItem(t("dialog.routine_bulk.all_cycles"), None)

        self.filter_status.addItem(t("dialog.routine_bulk.not_completed"), 0)

        self.filter_status.addItem(t("dialog.routine_bulk.completed"), 1)

        filter_layout.addWidget(self.filter_status)

        apply_filter_btn = QPushButton(t("dialog.routine_bulk.apply_filter"))

        apply_filter_btn.clicked.connect(self.load_data)

        filter_layout.addWidget(apply_filter_btn)

        filter_layout.addStretch()

        filter_group.setLayout(filter_layout)

        layout.addWidget(filter_group)

        # ?뚯씠釉?
        self.bulk_table = QTableWidget()

        self.bulk_table.setColumnCount(7)

        self.bulk_table.setHorizontalHeaderLabels(
            [
                t("dialog.routine_bulk.col_select"),
                t("dialog.routine_bulk.col_name"),
                t("dialog.routine_bulk.col_cycle"),
                t("dialog.routine_bulk.col_target_date"),
                t("dialog.routine_bulk.col_priority"),
                t("dialog.routine_bulk.col_status"),
                t("dialog.routine_bulk.col_progress"),
            ]
        )

        self.bulk_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        self.bulk_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.bulk_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        layout.addWidget(self.bulk_table)

        # ?좏깮 愿由?
        select_layout = QHBoxLayout()

        select_all_btn = QPushButton(t("dialog.routine_bulk.select_all"))

        select_all_btn.clicked.connect(self.select_all)

        deselect_all_btn = QPushButton(t("dialog.routine_bulk.deselect_all"))

        deselect_all_btn.clicked.connect(self.deselect_all)

        select_layout.addWidget(select_all_btn)

        select_layout.addWidget(deselect_all_btn)

        select_layout.addStretch()

        layout.addLayout(select_layout)

        # ?쇨큵 ?묒뾽 踰꾪듉

        action_group = QGroupBox(t("dialog.routine_bulk.action_group"))

        action_layout = QHBoxLayout()

        complete_btn = QPushButton(t("dialog.routine_bulk.complete_btn"))

        complete_btn.setObjectName("success_btn")

        complete_btn.clicked.connect(self.bulk_complete)

        action_layout.addWidget(complete_btn)

        priority_layout = QHBoxLayout()

        priority_layout.addWidget(QLabel(t("dialog.routine_bulk.change_priority")))

        self.bulk_priority_combo = QComboBox()

        self.bulk_priority_combo.addItem(t("priority.low"), "low")

        self.bulk_priority_combo.addItem(t("priority.normal"), "normal")

        self.bulk_priority_combo.addItem(t("priority.high"), "high")

        self.bulk_priority_combo.addItem(t("priority.urgent"), "urgent")

        priority_layout.addWidget(self.bulk_priority_combo)

        change_priority_btn = QPushButton(t("dialog.routine_bulk.apply_priority"))

        change_priority_btn.clicked.connect(self.bulk_change_priority)

        priority_layout.addWidget(change_priority_btn)

        action_layout.addLayout(priority_layout)

        delete_btn = QPushButton(t("dialog.routine_bulk.delete_btn"))

        delete_btn.setObjectName("danger_btn")

        delete_btn.clicked.connect(self.bulk_delete)

        action_layout.addWidget(delete_btn)

        action_group.setLayout(action_layout)

        layout.addWidget(action_group)

        return widget

    def _build_copy_tab(self):
        """Build copy/duplicate tab."""

        widget = QWidget()

        layout = QVBoxLayout(widget)

        # 설명

        info_label = QLabel(t("dialog.routine_bulk.copy_info"))

        info_label.setProperty("role", "dialogSubtitle")

        layout.addWidget(info_label)

        # ?먮낯 ?좏깮

        source_group = QGroupBox(t("dialog.routine_bulk.source_select"))

        source_layout = QVBoxLayout()

        self.source_table = QTableWidget()

        self.source_table.setColumnCount(5)

        self.source_table.setHorizontalHeaderLabels(
            [
                t("management.header_id"),
                t("dialog.routine_bulk.col_name"),
                t("dialog.routine_bulk.col_cycle"),
                t("dialog.routine_bulk.col_target_date"),
                t("dialog.routine_bulk.col_status"),
            ]
        )

        self.source_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        self.source_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.source_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        self.source_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        source_layout.addWidget(self.source_table)

        source_group.setLayout(source_layout)

        layout.addWidget(source_group)

        # 蹂듭젣 ?ㅼ젙

        copy_group = QGroupBox(t("dialog.routine_bulk.copy_settings"))

        copy_layout = QVBoxLayout()

        date_layout = QHBoxLayout()

        date_layout.addWidget(QLabel(t("dialog.routine_bulk.new_target_date")))

        self.copy_target_date = QDateEdit()

        self.copy_target_date.setCalendarPopup(True)

        self.copy_target_date.setDate(QDate.currentDate())

        date_layout.addWidget(self.copy_target_date)

        date_layout.addStretch()

        copy_layout.addLayout(date_layout)

        self.copy_checklist_check = QCheckBox(t("dialog.routine_bulk.copy_checklist"))

        self.copy_checklist_check.setChecked(True)

        copy_layout.addWidget(self.copy_checklist_check)

        copy_group.setLayout(copy_layout)

        layout.addWidget(copy_group)

        # 蹂듭젣 踰꾪듉

        copy_btn = QPushButton(t("dialog.routine_bulk.execute_copy"))

        copy_btn.setObjectName("primary_btn")

        copy_btn.clicked.connect(self.duplicate_routine)

        layout.addWidget(copy_btn)

        layout.addStretch()

        # 蹂듭궗 ???쒖꽦?????곗씠??濡쒕뱶

        self.tabs.currentChanged.connect(self._on_tab_changed)

        return widget

    def load_data(self):
        """Load filtered routine rows for bulk operations."""

        cycle_type = self.filter_cycle.currentData()

        is_completed = self.filter_status.currentData()

        routines = routine_service.search_routines(cycle_type=cycle_type, is_completed=is_completed)

        self.bulk_table.setRowCount(0)

        for routine in routines:
            row = self.bulk_table.rowCount()

            self.bulk_table.insertRow(row)

            # 泥댄겕諛뺤뒪

            checkbox = QCheckBox()

            checkbox_widget = QWidget()

            checkbox_layout = QHBoxLayout(checkbox_widget)

            checkbox_layout.addWidget(checkbox)

            checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            checkbox_layout.setContentsMargins(0, 0, 0, 0)

            self.bulk_table.setCellWidget(row, 0, checkbox_widget)

            checkbox.setProperty("task_id", routine["id"])

            # ?낅Т紐?
            icon = routine.get("icon", "\U0001f4cc")

            name_item = QTableWidgetItem(f"{icon} {routine['name']}")

            self.bulk_table.setItem(row, 1, name_item)

            # 二쇨린

            cycle_name = common_repo.get_cycle_type_display_name(
                routine.get("cycle_type", "monthly")
            )

            self.bulk_table.setItem(row, 2, QTableWidgetItem(cycle_name))

            # 湲곗???
            target_date = routine.get("target_date", "")

            self.bulk_table.setItem(row, 3, QTableWidgetItem(target_date))

            # ?곗꽑?쒖쐞

            priority_names = {
                "low": t("priority.low"),
                "normal": t("priority.normal"),
                "high": t("priority.high"),
                "urgent": t("priority.urgent"),
            }

            priority = priority_names.get(routine.get("priority", "normal"), t("priority.normal"))

            priority_item = QTableWidgetItem(priority)

            priority_colors = {
                "low": QColor(100, 100, 100),
                "normal": QColor(77, 166, 255),
                "high": QColor(255, 157, 77),
                "urgent": QColor(255, 77, 77),
            }

            color = priority_colors.get(routine.get("priority", "normal"))

            if color:
                priority_item.setForeground(color)

            self.bulk_table.setItem(row, 4, priority_item)

            # ?곹깭

            is_completed = routine.get("is_completed", 0)

            status = (
                t("dialog.routine_bulk.status_done")
                if is_completed
                else t("dialog.routine_bulk.status_in_progress")
            )

            status_item = QTableWidgetItem(status)

            if is_completed:
                status_item.setForeground(QColor(77, 255, 77))

            self.bulk_table.setItem(row, 5, status_item)

            # 吏꾪뻾瑜?
            progress = checklist_repo.get_task_checklist_progress(routine["id"])

            if progress["total"] > 0:
                pct = progress["completed"] / progress["total"] * 100

                progress_text = f"{progress['completed']}/{progress['total']} ({pct:.0f}%)"

            else:
                progress_text = "-"

            self.bulk_table.setItem(row, 6, QTableWidgetItem(progress_text))

    def load_source_data(self):
        """Load source routine rows for duplication tab."""

        routines = routine_service.search_routines()

        self.source_table.setRowCount(0)

        for routine in routines:
            row = self.source_table.rowCount()

            self.source_table.insertRow(row)

            self.source_table.setItem(row, 0, QTableWidgetItem(str(routine["id"])))

            icon = routine.get("icon", "\U0001f4cc")

            self.source_table.setItem(row, 1, QTableWidgetItem(f"{icon} {routine['name']}"))

            cycle_name = common_repo.get_cycle_type_display_name(
                routine.get("cycle_type", "monthly")
            )

            self.source_table.setItem(row, 2, QTableWidgetItem(cycle_name))

            target_date = routine.get("target_date", "")

            self.source_table.setItem(row, 3, QTableWidgetItem(target_date))

            is_completed = routine.get("is_completed", 0)

            status = (
                t("dialog.routine_bulk.status_done")
                if is_completed
                else t("dialog.routine_bulk.status_in_progress")
            )

            self.source_table.setItem(row, 4, QTableWidgetItem(status))

    def _on_tab_changed(self, index):
        """Handle tab change."""

        if index == 1:  # 蹂듭궗 ??
            self.load_source_data()

    def select_all(self):
        """Select all rows in the bulk table."""

        for row in range(self.bulk_table.rowCount()):
            checkbox_widget = self.bulk_table.cellWidget(row, 0)

            if checkbox_widget:
                checkbox = checkbox_widget.findChild(QCheckBox)

                if checkbox:
                    checkbox.setChecked(True)

    def deselect_all(self):
        """Clear all row selections in the bulk table."""

        for row in range(self.bulk_table.rowCount()):
            checkbox_widget = self.bulk_table.cellWidget(row, 0)

            if checkbox_widget:
                checkbox = checkbox_widget.findChild(QCheckBox)

                if checkbox:
                    checkbox.setChecked(False)

    def get_selected_task_ids(self):
        """Return selected routine task IDs."""

        selected_ids = []

        for row in range(self.bulk_table.rowCount()):
            checkbox_widget = self.bulk_table.cellWidget(row, 0)

            if checkbox_widget:
                checkbox = checkbox_widget.findChild(QCheckBox)

                if checkbox and checkbox.isChecked():
                    task_id = checkbox.property("task_id")

                    if task_id:
                        selected_ids.append(task_id)

        return selected_ids

    def bulk_complete(self):
        """Bulk-complete selected routines."""

        selected_ids = self.get_selected_task_ids()

        if not selected_ids:
            QMessageBox.warning(
                self, t("common.selection_required"), t("dialog.routine_bulk.select_warn_complete")
            )

            return

        reply = QMessageBox.question(
            self,
            t("common.confirm"),
            t("dialog.routine_bulk.confirm_complete", count=len(selected_ids)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            success_count = routine_service.batch_complete_routines(selected_ids)

            QMessageBox.information(
                self,
                t("common.notification"),
                t("dialog.routine_bulk.done_complete", count=success_count),
            )

            self.load_data()

            self.operations_completed.emit()

    def bulk_change_priority(self):
        """Bulk change priority."""

        selected_ids = self.get_selected_task_ids()

        if not selected_ids:
            QMessageBox.warning(
                self, t("common.selection_required"), t("dialog.routine_bulk.select_warn_priority")
            )

            return

        new_priority = self.bulk_priority_combo.currentData()

        reply = QMessageBox.question(
            self,
            t("common.confirm"),
            t("dialog.routine_bulk.confirm_priority", count=len(selected_ids)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            success_count = routine_service.batch_update_routine_priority(
                selected_ids, new_priority
            )

            QMessageBox.information(
                self,
                t("common.notification"),
                t("dialog.routine_bulk.done_priority", count=success_count),
            )

            self.load_data()

            self.operations_completed.emit()

    def bulk_delete(self):
        """Bulk-delete selected routines."""

        selected_ids = self.get_selected_task_ids()

        if not selected_ids:
            QMessageBox.warning(
                self, t("common.selection_required"), t("dialog.routine_bulk.select_warn_delete")
            )

            return

        reply = QMessageBox.question(
            self,
            t("common.confirm"),
            t("dialog.routine_bulk.confirm_delete", count=len(selected_ids)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            success_count = routine_service.batch_delete_routines(selected_ids)

            QMessageBox.information(
                self,
                t("common.notification"),
                t("dialog.routine_bulk.done_delete", count=success_count),
            )

            self.load_data()

            self.operations_completed.emit()

    def duplicate_routine(self):
        """Duplicate selected routine to target date."""

        selected_rows = self.source_table.selectedIndexes()

        if not selected_rows:
            QMessageBox.warning(
                self, t("common.selection_required"), t("dialog.routine_bulk.select_warn_copy")
            )

            return

        row = selected_rows[0].row()

        task_id = int(self.source_table.item(row, 0).text())

        new_target_date = self.copy_target_date.date().toString("yyyy-MM-dd")

        include_checklist = self.copy_checklist_check.isChecked()

        new_task_id = routine_service.duplicate_routine(task_id, new_target_date, include_checklist)

        if new_task_id:
            QMessageBox.information(
                self, t("common.notification"), t("dialog.routine_bulk.done_copy", id=new_task_id)
            )

            self.operations_completed.emit()

        else:
            QMessageBox.critical(self, t("common.error"), t("dialog.routine_bulk.fail_copy"))
