import logging

from PyQt6.QtCore import QModelIndex, QSortFilterProxyModel, Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from calendar_app.application import (
    directive_management_usecases,
    routine_management_usecases,
    task_delete_usecases,
    task_management_usecases,
)
from calendar_app.domain.task_constants import (
    PRIORITY_MENU_ITEMS,
    STATUS_FILTER_ITEMS,
    STATUS_MENU_ITEMS,
)
from calendar_app.domain.task_status_view import normalize_status as _normalize_status
from calendar_app.infrastructure.db import directive_repo, search_repo, task_repo
from calendar_app.infrastructure.google_sync.helpers import (
    queue_task_delete_from_google,
    queue_task_sync_to_google,
    resolve_app_context,
)
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    get_dialog_theme_tokens,
)

logger = logging.getLogger(__name__)


def _bulk_priority_items():
    """Return current priority items ??evaluated at call time."""
    return list(PRIORITY_MENU_ITEMS)


def _priority_value_from_label(label):
    for text, value in _bulk_priority_items():
        if text == label:
            return value
    return "normal"


def _status_value_from_label(label):
    for text, value in STATUS_MENU_ITEMS:
        if text == label:
            return value
    return "pending"


def _status_background(status):
    status = _normalize_status(status)
    if status == "completed":
        return QColor(18, 99, 58)
    if status == "in_progress":
        return QColor(111, 76, 16)
    if status == "pending":
        return QColor(92, 92, 28)
    return QColor(95, 39, 39)


# ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
# Proxy model
# ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????


class MultiColumnFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_text = ""
        self._status_text = STATUS_FILTER_ITEMS[0] if STATUS_FILTER_ITEMS else ""
        self._calendar_text = ""  # empty = all
        self._search_columns = []
        self._status_column = -1
        self._calendar_column = -1
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def setSearchColumns(self, columns):
        self._search_columns = list(columns)

    def setStatusColumn(self, column):
        self._status_column = column

    def setCalendarColumn(self, column):
        self._calendar_column = column

    def setSearchText(self, text):
        self._search_text = (text or "").strip().lower()
        self.invalidateFilter()

    def setStatusText(self, text):
        self._status_text = text or (STATUS_FILTER_ITEMS[0] if STATUS_FILTER_ITEMS else "")
        self.invalidateFilter()

    def setCalendarText(self, text):
        self._calendar_text = (text or "").strip()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        all_status_text = STATUS_FILTER_ITEMS[0] if STATUS_FILTER_ITEMS else ""
        if self._status_column >= 0 and self._status_text != all_status_text:
            idx = self.sourceModel().index(source_row, self._status_column, source_parent)
            if (idx.data() or "") != self._status_text:
                return False

            # 嶺?瑗????熬곥굤??        if self._calendar_column >= 0 and self._calendar_text:
            idx = self.sourceModel().index(source_row, self._calendar_column, source_parent)
            if (idx.data() or "") != self._calendar_text:
                return False

        if not self._search_text:
            return True

        for column in self._search_columns:
            idx = self.sourceModel().index(source_row, column, source_parent)
            value = (idx.data() or "").lower()
            if self._search_text in value:
                return True
        return False


# ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
# Base dialog
# ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????


class BaseManagementDialog(QDialog):
    title = ""
    header_text = ""
    headers = []
    status_column = -1
    search_columns = []
    status_filter_items = STATUS_FILTER_ITEMS

    def __init__(self, parent=None, size=(800, 600)):
        super().__init__(parent)
        apply_dialog_title(self, self.title)
        apply_common_dialog_style(self, size=size)
        self._ui_tokens = get_dialog_theme_tokens()
        self._loading = False
        self._editable_columns = set()
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(180)
        self._filter_timer.timeout.connect(self._apply_filters)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        header_layout = QHBoxLayout()
        header = QLabel(self.header_text)
        header.setStyleSheet(
            "font-size: 18px; font-weight: bold; "
            f"color: {self._ui_tokens.get('accent', '#4da6ff')}; "
            "margin-bottom: 10px;"
        )
        header_layout.addWidget(header)
        header_layout.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setFixedWidth(200)
        self.search_input.textChanged.connect(lambda: self._filter_timer.start())
        header_layout.addWidget(self.search_input)

        self.status_filter = QComboBox()
        self.status_filter.addItems(self.status_filter_items)
        self.status_filter.currentTextChanged.connect(lambda: self._filter_timer.start())
        header_layout.addWidget(self.status_filter)

        # 嶺?瑗????熬곥굤?????リ옇????⑤챷紐드슖????, ??類λ땹???????고뱺????戮?뻣
        self.calendar_filter = QComboBox()
        self.calendar_filter.setMinimumWidth(130)
        self.calendar_filter.currentTextChanged.connect(lambda: self._filter_timer.start())
        self.calendar_filter.hide()
        header_layout.addWidget(self.calendar_filter)

        layout.addLayout(header_layout)

        self.model = QStandardItemModel(0, len(self.headers), self)
        self.model.setHorizontalHeaderLabels(self.headers)
        self.model.itemChanged.connect(self._on_item_changed)

        self.proxy = MultiColumnFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSearchColumns(self.search_columns)
        self.proxy.setStatusColumn(self.status_column)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.table.doubleClicked.connect(self.edit_selected_index)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.open_context_menu)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        self._build_buttons(layout)
        self.load_data()
        if self.headers and self.headers[0] == "ID":
            self.table.hideColumn(0)

    def _build_buttons(self, layout):
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        btn_layout = QHBoxLayout()
        self.refresh_btn = QPushButton(t("dialog.common.refresh"))
        self.refresh_btn.setObjectName("ghost_btn")
        self.refresh_btn.clicked.connect(self.load_data)
        btn_layout.addWidget(self.refresh_btn)

        for button in self.extra_buttons():
            btn_layout.addWidget(button)

        for widget in self.bulk_action_widgets():
            btn_layout.addWidget(widget)

        btn_layout.addStretch()

        for button in self.tail_buttons():
            btn_layout.addWidget(button)

        layout.addLayout(btn_layout)

    def extra_buttons(self):
        return []

    def bulk_action_widgets(self):
        self.bulk_priority_combo = QComboBox()
        self.bulk_priority_combo.addItems([label for label, _ in _bulk_priority_items()])
        self.bulk_priority_combo.setMinimumWidth(110)

        self.bulk_priority_btn = QPushButton(t("dialog.common.bulk_priority"))
        self.bulk_priority_btn.setObjectName("SecondaryBtn")
        self.bulk_priority_btn.clicked.connect(
            lambda: self.bulk_priority_update(
                _priority_value_from_label(self.bulk_priority_combo.currentText())
            )
        )

        self.bulk_status_combo = QComboBox()
        self.bulk_status_combo.addItems([label for label, _ in STATUS_MENU_ITEMS])
        self.bulk_status_combo.setMinimumWidth(110)

        self.bulk_status_btn = QPushButton(t("dialog.common.bulk_status"))
        self.bulk_status_btn.setObjectName("SecondaryBtn")
        self.bulk_status_btn.clicked.connect(
            lambda: self.bulk_status_update(
                _status_value_from_label(self.bulk_status_combo.currentText())
            )
        )

        return [
            self.bulk_priority_combo,
            self.bulk_priority_btn,
            self.bulk_status_combo,
            self.bulk_status_btn,
        ]

    def tail_buttons(self):
        return []

    def _apply_filters(self):
        self.proxy.setSearchText(self.search_input.text())
        self.proxy.setStatusText(self.status_filter.currentText())
        # calendar filter: first item(index=0) means all
        if not self.calendar_filter.isHidden() and self.calendar_filter.currentIndex() > 0:
            self.proxy.setCalendarText(self.calendar_filter.currentText())
        else:
            self.proxy.setCalendarText("")

    def _selected_source_rows(self):
        rows = []
        for proxy_index in self.table.selectionModel().selectedRows():
            source_index = self.proxy.mapToSource(proxy_index)
            rows.append(source_index.row())
        return sorted(set(rows))

    def _selected_ids(self):
        ids = []
        for row in self._selected_source_rows():
            item = self.model.item(row, 0)
            if item is not None:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids

    def _append_row(self, row_values, row_meta, editable_columns=None, status_value=None):
        editable_columns = editable_columns or set()
        items = []
        for col, value in enumerate(row_values):
            item = QStandardItem(str(value or ""))
            item.setEditable(col in editable_columns)
            item.setData(row_meta.get("id"), Qt.ItemDataRole.UserRole)
            item.setData(row_meta, Qt.ItemDataRole.UserRole + 1)
            if col == self.status_column:
                item.setBackground(_status_background(status_value))
            items.append(item)
        self.model.appendRow(items)

    def _set_combo_to_first(self, combo: QComboBox):
        if combo is None:
            return
        combo.blockSignals(True)
        if combo.count() > 0:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _set_widgets_enabled(self, widgets, enabled: bool):
        for widget in widgets:
            if widget is not None:
                widget.setEnabled(enabled)

    def _sync_common_trash_mode_ui(
        self,
        *,
        toggle_text_normal: str,
        toggle_text_trash: str,
        disable_widgets,
        reset_combos=(),
    ):
        if self._trash_mode:
            self.trash_toggle_btn.setText(toggle_text_trash)
            self.delete_btn.setText(t("dialog.management.btn_purge", "Purge"))
            self.restore_btn.setVisible(True)
            self._set_widgets_enabled(disable_widgets, False)
            self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self._set_combo_to_first(self.status_filter)
            for combo in reset_combos:
                self._set_combo_to_first(combo)
            return

        self.trash_toggle_btn.setText(toggle_text_normal)
        self.delete_btn.setText(t("dialog.common.delete"))
        self.restore_btn.setVisible(False)
        self._set_widgets_enabled(disable_widgets, True)
        self.table.setEditTriggers(self._normal_edit_triggers)

    def _open_trash_context_menu(self, pos):
        menu = QMenu(self)
        has_selection = bool(self._selected_ids())

        restore_act = QAction(t("dialog.management.btn_restore_from_trash", "Restore"), self)
        restore_act.setEnabled(has_selection)
        restore_act.triggered.connect(self.restore_selected)
        menu.addAction(restore_act)
        menu.addSeparator()

        purge_act = QAction(t("dialog.management.btn_purge", "Purge"), self)
        purge_act.setEnabled(has_selection)
        purge_act.triggered.connect(self.delete_selected)
        menu.addAction(purge_act)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _confirm_restore_from_trash(self) -> bool:
        return (
            QMessageBox.question(
                self,
                t("dialog.management.btn_restore_from_trash", "Restore"),
                t("dialog.management.trash_restore_confirm", "Restore selected items from trash?"),
            )
            == QMessageBox.StandardButton.Yes
        )

    def _confirm_purge_from_trash(self) -> bool:
        return (
            QMessageBox.question(
                self,
                t("dialog.management.btn_purge", "Purge"),
                t(
                    "dialog.management.trash_purge_confirm",
                    "Permanently delete selected trashed items?\nThis action cannot be undone.",
                ),
            )
            == QMessageBox.StandardButton.Yes
        )

    def _confirm_move_to_trash(self) -> bool:
        return (
            QMessageBox.question(
                self,
                t("dialog.common.delete"),
                t("dialog.management.trash_move_confirm", "Move selected items to trash?"),
            )
            == QMessageBox.StandardButton.Yes
        )

    def _restore_task_items_from_trash(self, archive_ids):
        if not archive_ids:
            return []
        return task_management_usecases.restore_trashed_tasks(task_repo, archive_ids)

    def _purge_task_items_from_trash(self, archive_ids, *, log_message: str):
        if not archive_ids:
            return 0
        purged, gcal_refs = task_management_usecases.purge_trashed_tasks(task_repo, archive_ids)
        try:
            task_delete_usecases.queue_google_deletes_for_refs(
                gcal_refs,
                queue_delete_fn=lambda event_id,
                local_task_id,
                gcal_calendar_id: queue_task_delete_from_google(
                    self,
                    event_id,
                    local_task_id=local_task_id,
                    gcal_calendar_id=gcal_calendar_id,
                ),
            )
        except Exception:
            logger.exception(log_message)
        return purged

    def _apply_task_inline_update(self, item, *, field_map, inline_update_fn):
        if self._trash_mode:
            return
        field = field_map.get(item.column())
        if not field:
            return
        row_id = item.data(Qt.ItemDataRole.UserRole)
        task = inline_update_fn(task_repo, row_id, field, item.text())
        if task:
            queue_task_sync_to_google(self, task, create_if_missing=True)

    def _open_unified_task_create_dialog(self, *, task_type: str, post_success=None):
        from calendar_app.presentation.dialogs.task_dialog_unified import UnifiedTaskDialog

        dlg = UnifiedTaskDialog(self, task_type=task_type)
        app = resolve_app_context(self)
        if app and hasattr(app, "handle_task_added"):
            dlg.task_added.connect(app.handle_task_added)
        if dlg.exec():
            if callable(post_success):
                post_success()
            self.load_data()

    def _open_unified_task_modify_dialog(self, row_id):
        if self._trash_mode:
            return
        from calendar_app.presentation.dialogs.modify_task_dialog_unified import (
            UnifiedModifyTaskDialog,
        )

        dlg = UnifiedModifyTaskDialog(int(row_id), self)
        if dlg.exec():
            self.load_data()

    def _bulk_task_status_update(self, new_status, *, bulk_update_fn):
        if self._trash_mode:
            return
        ids = self._selected_ids()
        if not ids:
            return
        tasks = bulk_update_fn(task_repo, ids, new_status)
        for task in tasks:
            queue_task_sync_to_google(self, task, create_if_missing=True)
        self.load_data()

    def _bulk_task_priority_update(self, new_priority, *, bulk_update_fn):
        if self._trash_mode:
            return
        ids = self._selected_ids()
        if not ids:
            return
        bulk_update_fn(task_repo, ids, new_priority)
        self.load_data()

    def _restore_selected_task_rows(self):
        if not self._trash_mode:
            return
        ids = self._selected_ids()
        if not ids:
            return
        if not self._confirm_restore_from_trash():
            return
        self._restore_task_items_from_trash(ids)
        self.load_data()

    def _delete_selected_task_rows(self, *, trash_reason: str, purge_log_message: str):
        ids = self._selected_ids()
        if not ids:
            return

        if self._trash_mode:
            if not self._confirm_purge_from_trash():
                return
            self._purge_task_items_from_trash(ids, log_message=purge_log_message)
            self.load_data()
            return

        if not self._confirm_move_to_trash():
            return
        task_management_usecases.move_tasks_to_trash(task_repo, ids, reason=trash_reason)
        self.load_data()

    def load_data(self):
        raise NotImplementedError

    def _on_item_changed(self, item):
        if self._loading:
            return
        self.on_item_changed(item)

    def on_item_changed(self, item):
        return

    def edit_selected_index(self, proxy_index: QModelIndex):
        if not proxy_index.isValid():
            return
        source_index = self.proxy.mapToSource(proxy_index)
        item = self.model.item(source_index.row(), 0)
        if item is not None:
            self.edit_by_id(item.data(Qt.ItemDataRole.UserRole))

    def edit_by_id(self, row_id):
        raise NotImplementedError

    def open_context_menu(self, pos):
        menu = QMenu(self)
        priority_menu = menu.addMenu(t("dialog.common.bulk_priority"))
        for label, value in PRIORITY_MENU_ITEMS:
            act = QAction(label, self)
            act.triggered.connect(lambda _=False, v=value: self.bulk_priority_update(v))
            priority_menu.addAction(act)

        status_menu = menu.addMenu(t("dialog.common.bulk_status"))
        for label, value in STATUS_MENU_ITEMS:
            act = QAction(label, self)
            act.triggered.connect(lambda _=False, v=value: self.bulk_status_update(v))
            status_menu.addAction(act)
        menu.addSeparator()
        delete_act = QAction(t("dialog.common.delete_selected"), self)
        delete_act.triggered.connect(self.delete_selected)
        menu.addAction(delete_act)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def bulk_status_update(self, new_status):
        raise NotImplementedError

    def bulk_priority_update(self, new_priority):
        raise NotImplementedError

    def delete_selected(self):
        raise NotImplementedError


# ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
# DirectiveManagementDialog
# ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????


class DirectiveManagementDialog(BaseManagementDialog):
    @property
    def title(self):
        return t("dialog.management.directive_title")

    @property
    def header_text(self):
        return t("dialog.management.directive_header")

    @property
    def headers(self):
        return [
            t("dialog.management.header_content"),
            t("dialog.management.header_receiver"),
            t("dialog.management.header_priority"),
            t("dialog.management.header_deadline"),
            t("dialog.management.header_status"),
        ]

    status_column = 4
    search_columns = [0, 1]

    def __init__(self, parent=None):
        self._trash_mode = False
        self._normal_edit_triggers = (
            QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        super().__init__(parent, size=(720, 540))
        self._sync_trash_mode_ui()

    def extra_buttons(self):
        self.add_btn = QPushButton(t("dialog.management.btn_add_directive"))
        self.add_btn.setObjectName("PrimaryBtn")
        self.add_btn.clicked.connect(self.add_new)
        return [self.add_btn]

    def tail_buttons(self):
        self.trash_toggle_btn = QPushButton(t("dialog.management.btn_toggle_trash", "Trash"))
        self.trash_toggle_btn.setObjectName("SecondaryBtn")
        self.trash_toggle_btn.clicked.connect(self.toggle_trash_mode)

        self.restore_btn = QPushButton(t("dialog.management.btn_restore_from_trash", "Restore"))
        self.restore_btn.setObjectName("PrimaryBtn")
        self.restore_btn.clicked.connect(self.restore_selected)

        self.complete_btn = QPushButton(t("dialog.management.btn_mark_done"))
        self.complete_btn.setObjectName("PrimaryBtn")
        self.complete_btn.clicked.connect(self.mark_as_done)
        self.delete_btn = QPushButton(t("dialog.common.delete"))
        self.delete_btn.setObjectName("DangerBtn")
        self.delete_btn.clicked.connect(self.delete_selected)
        return [self.complete_btn, self.trash_toggle_btn, self.restore_btn, self.delete_btn]

    def _sync_trash_mode_ui(self):
        self._sync_common_trash_mode_ui(
            toggle_text_normal=t("dialog.management.btn_toggle_trash", "Trash"),
            toggle_text_trash=t("dialog.management.btn_toggle_trash_back", "Directives"),
            disable_widgets=[
                self.add_btn,
                self.complete_btn,
                self.bulk_priority_combo,
                self.bulk_priority_btn,
                self.bulk_status_combo,
                self.bulk_status_btn,
            ],
        )

    def toggle_trash_mode(self):
        self._trash_mode = not self._trash_mode
        self._sync_trash_mode_ui()
        self.load_data()

    def load_data(self):
        self._loading = True
        self.model.removeRows(0, self.model.rowCount())
        if self._trash_mode:
            rows = directive_management_usecases.list_trashed(directive_repo)
            payloads = directive_management_usecases.build_trash_table_payload(rows)
            editable_columns = set()
        else:
            rows = directive_repo.get_all_directives_for_management()
            payloads = directive_management_usecases.build_table_payload(rows)
            editable_columns = {0, 1, 3}
        for payload in payloads:
            self._append_row(
                payload["cells"],
                payload["meta"],
                editable_columns=editable_columns,
                status_value=payload["meta"]["status"],
            )
        self._loading = False
        self.table.sortByColumn(2, Qt.SortOrder.AscendingOrder)
        self._apply_filters()

    def on_item_changed(self, item):
        if self._trash_mode:
            return
        field_map = {0: "content", 1: "receiver_name", 3: "deadline"}
        if item.column() not in field_map:
            return
        row_id = item.data(Qt.ItemDataRole.UserRole)
        directive_management_usecases.update_inline_field(
            directive_repo,
            row_id,
            field_map[item.column()],
            item.text(),
        )

    def add_new(self):
        from calendar_app.presentation.dialogs.directive_dialog import DirectiveDialog

        dlg = DirectiveDialog(self)
        if dlg.exec():
            self.load_data()

    def edit_by_id(self, row_id):
        if self._trash_mode:
            return
        from calendar_app.presentation.dialogs.directive_dialog import DirectiveDialog

        dlg = DirectiveDialog(self, task_id=row_id)
        if dlg.exec():
            self.load_data()

    def bulk_status_update(self, new_status):
        if self._trash_mode:
            return
        ids = self._selected_ids()
        if not ids:
            return
        directive_management_usecases.bulk_update_status(directive_repo, ids, new_status)
        self.load_data()

    def bulk_priority_update(self, new_priority):
        if self._trash_mode:
            return
        ids = self._selected_ids()
        if not ids:
            return
        directive_management_usecases.bulk_update_priority(directive_repo, ids, new_priority)
        self.load_data()

    def mark_as_done(self):
        if self._trash_mode:
            return
        ids = self._selected_ids()
        if not ids:
            return
        self.bulk_status_update("completed")

    def open_context_menu(self, pos):
        if not self._trash_mode:
            super().open_context_menu(pos)
            return
        self._open_trash_context_menu(pos)

    def restore_selected(self):
        if not self._trash_mode:
            return
        ids = self._selected_ids()
        if not ids:
            return
        if not self._confirm_restore_from_trash():
            return
        directive_management_usecases.restore_selected_from_trash(directive_repo, ids)
        self.load_data()

    def delete_selected(self):
        ids = self._selected_ids()
        if not ids:
            return

        if self._trash_mode:
            if not self._confirm_purge_from_trash():
                return
            directive_management_usecases.purge_selected_from_trash(directive_repo, ids)
            self.load_data()
            return

        if not self._confirm_move_to_trash():
            return
        directive_management_usecases.move_selected_to_trash(
            directive_repo, ids, reason="manual_trash_directive"
        )
        self.load_data()


# ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
# TaskManagementDialog  ??嶺?瑗?????롫맩???熬곥굤???怨뺣뼺?
# ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????


class TaskManagementDialog(BaseManagementDialog):
    @property
    def title(self):
        return t("dialog.management.schedule_title")

    @property
    def header_text(self):
        return t("dialog.management.schedule_header")

    @property
    def headers(self):
        return [
            t("dialog.management.header_id", "ID"),  # col 0 (hidden)
            t("dialog.management.header_calendar", "Calendar"),  # col 1
            t("dialog.management.header_name"),  # col 2
            t("dialog.management.header_deadline"),  # col 3
            t("dialog.management.header_location"),  # col 4
            t("dialog.management.header_assignee"),  # col 5
            t("dialog.management.header_priority"),  # col 6
            t("dialog.management.header_status"),  # col 7
        ]

    status_column = 7
    search_columns = [2, 4, 5]  # name, location, assignee
    _calendar_col = 1

    def __init__(self, parent=None):
        self._calendar_map = {}  # str(id) ??name
        self._trash_mode = False
        self._normal_edit_triggers = (
            QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        super().__init__(parent, size=(960, 650))
        # 嶺?瑗?????롫맩???熬곣뫁夷???繹먮굞夷?& ?熬곥굤????戮?뻣
        self.proxy.setCalendarColumn(self._calendar_col)
        self._populate_calendar_filter()
        self.calendar_filter.show()
        # ID ??롫맩????節뗢뵛??        self.table.hideColumn(0)
        self._sync_trash_mode_ui()

    def _populate_calendar_filter(self):
        """DB?????嶺?瑗???嶺뚮ㅄ維뽨빳??????꽑 ?熬곥굤???袁좊걞??⑥낯筌먦끇裕??嶺??????덈펲."""
        try:
            from calendar_app.infrastructure.db.calendar_repo import list_calendars

            calendars = list_calendars(include_inactive=True)
        except Exception:
            calendars = []

        self._calendar_map = {str(c["id"]): c["name"] for c in calendars}
        all_label = t("dialog.management.calendar_all", "All Calendars")
        self.calendar_filter.blockSignals(True)
        self.calendar_filter.clear()
        self.calendar_filter.addItem(all_label)
        for cal in calendars:
            self.calendar_filter.addItem(cal["name"])
        self.calendar_filter.blockSignals(False)

    def _calendar_name_for(self, row):
        """task row?????嶺?瑗??????藥???꾩룇瑗???紐껊퉵??"""
        cal_id = str(row.get("calendar_id") or "")
        return self._calendar_map.get(cal_id, t("dialog.management.calendar_local", "Local"))

    def extra_buttons(self):
        self.add_btn = QPushButton(t("dialog.management.btn_add_schedule"))
        self.add_btn.setObjectName("PrimaryBtn")
        self.add_btn.clicked.connect(self.add_new)
        return [self.add_btn]

    def tail_buttons(self):
        self.trash_toggle_btn = QPushButton(t("dialog.management.btn_toggle_trash", "Trash"))
        self.trash_toggle_btn.setObjectName("SecondaryBtn")
        self.trash_toggle_btn.clicked.connect(self.toggle_trash_mode)

        self.restore_btn = QPushButton(t("dialog.management.btn_restore_from_trash", "Restore"))
        self.restore_btn.setObjectName("PrimaryBtn")
        self.restore_btn.clicked.connect(self.restore_selected)

        self.delete_btn = QPushButton(t("dialog.common.delete"))
        self.delete_btn.setObjectName("DangerBtn")
        self.delete_btn.clicked.connect(self.delete_selected)
        return [self.trash_toggle_btn, self.restore_btn, self.delete_btn]

    def _sync_trash_mode_ui(self):
        self._sync_common_trash_mode_ui(
            toggle_text_normal=t("dialog.management.btn_toggle_trash", "Trash"),
            toggle_text_trash=t("dialog.management.btn_toggle_trash_back", "Schedules"),
            disable_widgets=[
                self.add_btn,
                self.bulk_priority_combo,
                self.bulk_priority_btn,
                self.bulk_status_combo,
                self.bulk_status_btn,
                self.calendar_filter,
            ],
            reset_combos=[self.calendar_filter],
        )

    def toggle_trash_mode(self):
        self._trash_mode = not self._trash_mode
        self._sync_trash_mode_ui()
        self.load_data()

    def load_data(self):
        self._loading = True
        self.model.removeRows(0, self.model.rowCount())
        if self._trash_mode:
            rows = task_management_usecases.list_trashed_tasks(task_repo, task_type="schedule")
            payloads = task_management_usecases.build_trash_table_payload(rows)
            editable_columns = set()
        else:
            rows = search_repo.get_tasks_by_type("schedule")
            payloads = task_management_usecases.build_table_payload(rows)
            editable_columns = {2, 3, 4, 5}
        for row, payload in zip(rows, payloads, strict=False):
            cells_orig = payload["cells"]  # [name, deadline, location, assignee, priority, status]
            cal_name = self._calendar_name_for(row)
            full_cells = [
                str(payload["meta"].get("id", "")),  # col 0: ID (hidden)
                cal_name,  # col 1: calendar
                cells_orig[0],  # col 2: name
                cells_orig[1],  # col 3: deadline
                cells_orig[2],  # col 4: location
                cells_orig[3],  # col 5: assignee
                cells_orig[4],  # col 6: priority
                cells_orig[5],  # col 7: status
            ]
            self._append_row(
                full_cells,
                payload["meta"],
                editable_columns=editable_columns,
                status_value=payload["meta"]["status"],
            )
        self._loading = False
        self.table.sortByColumn(3, Qt.SortOrder.AscendingOrder)
        self._apply_filters()

    def on_item_changed(self, item):
        # ??롫맩?????덈뒆??+2 (ID, 嶺?瑗????怨뺣뼺?)
        self._apply_task_inline_update(
            item,
            field_map={2: "name", 3: "deadline", 4: "location", 5: "assignee"},
            inline_update_fn=task_management_usecases.inline_update_task,
        )

    def add_new(self):
        self._open_unified_task_create_dialog(
            task_type="schedule", post_success=self._populate_calendar_filter
        )

    def edit_by_id(self, row_id):
        self._open_unified_task_modify_dialog(row_id)

    def bulk_status_update(self, new_status):
        self._bulk_task_status_update(
            new_status, bulk_update_fn=task_management_usecases.bulk_update_status
        )

    def bulk_priority_update(self, new_priority):
        self._bulk_task_priority_update(
            new_priority,
            bulk_update_fn=task_management_usecases.bulk_update_priority,
        )

    def open_context_menu(self, pos):
        if not self._trash_mode:
            super().open_context_menu(pos)
            return
        self._open_trash_context_menu(pos)

    def restore_selected(self):
        self._restore_selected_task_rows()

    def delete_selected(self):
        self._delete_selected_task_rows(
            trash_reason="manual_trash",
            purge_log_message="Failed to queue Google delete for purged schedule task",
        )


# ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
# RoutineManagementDialog
# ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????


class RoutineManagementDialog(BaseManagementDialog):
    @property
    def title(self):
        return t("dialog.management.routine_title")

    @property
    def header_text(self):
        return t("dialog.management.routine_header")

    @property
    def headers(self):
        return [
            t("dialog.management.header_work_name"),
            t("dialog.management.header_cycle"),
            t("dialog.management.header_location"),
            t("dialog.management.header_assignee"),
            t("dialog.management.header_priority"),
            t("dialog.management.header_deadline"),
            t("dialog.management.header_status"),
        ]

    status_column = 6
    search_columns = [0, 2, 3]

    def __init__(self, parent=None):
        self._trash_mode = False
        self._normal_edit_triggers = (
            QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        super().__init__(parent, size=(820, 620))
        self._sync_trash_mode_ui()

    def extra_buttons(self):
        self.add_btn = QPushButton(t("dialog.management.btn_add_routine"))
        self.add_btn.setObjectName("PrimaryBtn")
        self.add_btn.clicked.connect(self.add_new)
        return [self.add_btn]

    def tail_buttons(self):
        self.trash_toggle_btn = QPushButton(t("dialog.management.btn_toggle_trash", "Trash"))
        self.trash_toggle_btn.setObjectName("SecondaryBtn")
        self.trash_toggle_btn.clicked.connect(self.toggle_trash_mode)

        self.restore_btn = QPushButton(t("dialog.management.btn_restore_from_trash", "Restore"))
        self.restore_btn.setObjectName("PrimaryBtn")
        self.restore_btn.clicked.connect(self.restore_selected)

        self.delete_btn = QPushButton(t("dialog.common.delete"))
        self.delete_btn.setObjectName("DangerBtn")
        self.delete_btn.clicked.connect(self.delete_selected)
        return [self.trash_toggle_btn, self.restore_btn, self.delete_btn]

    def _sync_trash_mode_ui(self):
        self._sync_common_trash_mode_ui(
            toggle_text_normal=t("dialog.management.btn_toggle_trash", "Trash"),
            toggle_text_trash=t("dialog.management.btn_toggle_trash_back", "Routines"),
            disable_widgets=[
                self.add_btn,
                self.bulk_priority_combo,
                self.bulk_priority_btn,
                self.bulk_status_combo,
                self.bulk_status_btn,
            ],
        )

    def toggle_trash_mode(self):
        self._trash_mode = not self._trash_mode
        self._sync_trash_mode_ui()
        self.load_data()

    def load_data(self):
        self._loading = True
        self.model.removeRows(0, self.model.rowCount())
        if self._trash_mode:
            rows = task_management_usecases.list_trashed_tasks(task_repo, task_type="routine")
            for row in rows:
                raw_status = routine_management_usecases.normalized_status(row.get("status"))
                self._append_row(
                    [
                        row.get("name", ""),
                        routine_management_usecases.cycle_label(row.get("cycle_type")),
                        row.get("location", ""),
                        row.get("assignee", ""),
                        routine_management_usecases.priority_display(row.get("priority")),
                        row.get("target_date") or row.get("deadline", ""),
                        routine_management_usecases.status_display(raw_status),
                    ],
                    {"id": row.get("id"), "status": raw_status},
                    editable_columns=set(),
                    status_value=raw_status,
                )
        else:
            rows = search_repo.get_tasks_by_type("routine")
            for payload in routine_management_usecases.build_table_payload(rows):
                self._append_row(
                    payload["cells"],
                    payload["meta"],
                    editable_columns={0, 2, 3, 5},
                    status_value=payload["meta"]["status"],
                )
        self._loading = False
        self.table.sortByColumn(5, Qt.SortOrder.AscendingOrder)
        self._apply_filters()

    def on_item_changed(self, item):
        self._apply_task_inline_update(
            item,
            field_map={0: "name", 2: "location", 3: "assignee", 5: "target_date"},
            inline_update_fn=routine_management_usecases.inline_update_task,
        )

    def add_new(self):
        self._open_unified_task_create_dialog(task_type="routine")

    def edit_by_id(self, row_id):
        self._open_unified_task_modify_dialog(row_id)

    def bulk_status_update(self, new_status):
        self._bulk_task_status_update(
            new_status, bulk_update_fn=routine_management_usecases.bulk_update_status
        )

    def bulk_priority_update(self, new_priority):
        self._bulk_task_priority_update(
            new_priority,
            bulk_update_fn=routine_management_usecases.bulk_update_priority,
        )

    def open_context_menu(self, pos):
        if not self._trash_mode:
            super().open_context_menu(pos)
            return
        self._open_trash_context_menu(pos)

    def restore_selected(self):
        self._restore_selected_task_rows()

    def delete_selected(self):
        self._delete_selected_task_rows(
            trash_reason="manual_trash_routine",
            purge_log_message="Failed to queue Google delete for purged routine task",
        )


class WorkManagementTabbedDialog(QDialog):
    """Unified tabbed management dialog for schedule/routine/directive."""

    def __init__(self, parent=None, start_tab: str = "schedule"):
        super().__init__(parent)
        apply_dialog_title(self, t("dialog.management.work_hub_title", "전체 업무 관리"))
        apply_common_dialog_style(self, size=(1180, 760))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)
        layout.addWidget(self.tabs)

        self._tab_defs = [
            ("schedule", t("dialog.management.tab_schedule", "일정 관리"), TaskManagementDialog),
            ("routine", t("dialog.management.tab_routine", "⭐ 일반업무"), RoutineManagementDialog),
            (
                "directive",
                t("dialog.management.tab_directive", "📋 지시/협조사항"),
                DirectiveManagementDialog,
            ),
        ]
        self._tab_hosts = []
        self._tab_instances = {}

        for _key, label, _cls in self._tab_defs:
            host = QWidget(self.tabs)
            host_layout = QVBoxLayout(host)
            host_layout.setContentsMargins(0, 0, 0, 0)
            host_layout.setSpacing(0)
            self.tabs.addTab(host, label)
            self._tab_hosts.append(host)

        self.tabs.currentChanged.connect(self._on_tab_changed)

        start_idx = 0
        for idx, (key, _label, _cls) in enumerate(self._tab_defs):
            if key == str(start_tab or "").strip():
                start_idx = idx
                break
        self.tabs.setCurrentIndex(start_idx)
        self._ensure_tab_loaded(start_idx)

    def _ensure_tab_loaded(self, index: int):
        if index in self._tab_instances:
            return self._tab_instances[index]
        if index < 0 or index >= len(self._tab_defs):
            return None

        _key, _label, dialog_cls = self._tab_defs[index]
        host = self._tab_hosts[index]
        child = dialog_cls(self)
        child.setWindowFlags(Qt.WindowType.Widget)
        host.layout().addWidget(child)
        child.show()
        self._tab_instances[index] = child
        return child

    def _on_tab_changed(self, index: int):
        child = self._ensure_tab_loaded(index)
        if child is not None and hasattr(child, "load_data"):
            try:
                child.load_data()
            except Exception:
                logger.exception("Failed to refresh tab %s in WorkManagementTabbedDialog", index)


__all__ = [
    "DirectiveManagementDialog",
    "TaskManagementDialog",
    "RoutineManagementDialog",
    "WorkManagementTabbedDialog",
]
