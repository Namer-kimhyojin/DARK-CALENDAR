import logging
import sqlite3

from PyQt6.QtCore import QDate, QStringListModel, Qt, QTime
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDateEdit,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
)

from calendar_app.app_paths import DB_PATH
from calendar_app.domain.task_constants import PRIORITY_COMBO_ITEMS, STATUS_COMBO_ITEMS
from calendar_app.infrastructure.db import directive_repo
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_editor_styles import (
    build_editor_counter_style,
    build_editor_hint_style,
    build_editor_quick_button_style,
    build_task_editor_stylesheet,
)
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    FieldValidator,
    apply_common_dialog_style,
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
    polish_calendar_popup,
)

logger = logging.getLogger(__name__)

_QUICK_TIME_BTNS = [("09:00", 9, 0), ("12:00", 12, 0), ("15:00", 15, 0), ("18:00", 18, 0)]


class DirectiveDialog(QDialog):
    def __init__(self, parent=None, task_id=None, **kwargs):
        super().__init__(parent)
        self.task_id = task_id
        self._saved_task_id = None

        try:
            self._ui_tokens = get_dialog_theme_tokens()
            self._dialog_metrics = get_dialog_metric_tokens(apply_overrides=True)

            apply_dialog_title(
                self,
                t("dialog.directive.title_edit") if task_id else t("dialog.directive.title_add"),
            )
            self.setObjectName("TaskEditorDialog")
            apply_common_dialog_style(
                self,
                minimum_width=560,
                extra_stylesheet=build_task_editor_stylesheet(
                    tokens=self._ui_tokens,
                    metrics=self._dialog_metrics,
                ),
            )
            self.resize(600, 680)

            self.init_ui()
            self._setup_shortcuts()

            if self.task_id:
                self.load_data()

            if hasattr(self, "content_edit"):
                self._on_content_changed(self.content_edit.text())

        except Exception:
            logger.exception("DirectiveDialog.__init__ failed")
            QMessageBox.critical(
                self, t("dialog.common.error"), "지시사항 다이얼로그 초기화 중 오류가 발생했습니다."
            )

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(9)
        layout.setContentsMargins(16, 14, 16, 14)

        top_row = QHBoxLayout()
        content_lbl = QLabel(t("dialog.directive.label_content"))
        content_lbl.setObjectName("TaskDialogFieldLabel")
        top_row.addWidget(content_lbl)
        top_row.addStretch()
        self.char_counter = QLabel("0 / 120")
        self.char_counter.setStyleSheet(build_editor_counter_style(self._ui_tokens, level="normal"))
        top_row.addWidget(self.char_counter)
        layout.addLayout(top_row)

        self.content_edit = QLineEdit()
        self.content_edit.setPlaceholderText(t("dialog.directive.placeholder_content"))
        self.content_edit.setMaxLength(120)
        self.content_edit.textChanged.connect(self._on_content_changed)
        layout.addWidget(self.content_edit)

        self._content_err = QLabel()
        self._content_err.setProperty("role", "field_error")
        self._content_err.setVisible(False)
        layout.addWidget(self._content_err)
        self._content_validator = FieldValidator(self.content_edit, self._content_err)

        receiver_lbl = QLabel(t("dialog.directive.label_receiver"))
        receiver_lbl.setObjectName("TaskDialogFieldLabel")
        layout.addWidget(receiver_lbl)
        self.receiver_edit = QLineEdit()
        self.receiver_edit.setPlaceholderText(t("dialog.directive.placeholder_receiver"))
        self._attach_receiver_completer()
        layout.addWidget(self.receiver_edit)

        deadline_lbl = QLabel(t("dialog.directive.label_deadline"))
        deadline_lbl.setObjectName("TaskDialogFieldLabel")
        layout.addWidget(deadline_lbl)

        dt_input_row = QHBoxLayout()
        dt_input_row.setSpacing(6)
        self.deadline_date = QDateEdit(QDate.currentDate())
        self.deadline_date.setCalendarPopup(True)
        self.deadline_date.setDisplayFormat("yyyy-MM-dd")
        self.deadline_date.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.deadline_date.setMinimumHeight(30)
        polish_calendar_popup(self.deadline_date)

        self.deadline_time = QTimeEdit(QTime(12, 0))
        self.deadline_time.setDisplayFormat("HH:mm")
        self.deadline_time.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.deadline_time.setMinimumHeight(30)

        dt_input_row.addWidget(self.deadline_date, 3)
        dt_input_row.addWidget(self.deadline_time, 2)
        layout.addLayout(dt_input_row)

        date_quick_row = QHBoxLayout()
        date_quick_row.setSpacing(5)
        for label, delta in [
            (t("dialog.directive.quick_today"), 0),
            (t("dialog.directive.quick_tomorrow"), 1),
            (t("dialog.directive.quick_plus_3d"), 3),
            (t("dialog.directive.quick_plus_1w"), 7),
        ]:
            btn = QPushButton(label)
            btn.setFixedWidth(50)
            btn.setStyleSheet(
                build_editor_quick_button_style(self._ui_tokens, self._dialog_metrics)
            )
            btn.clicked.connect(
                lambda _, d=delta: self.deadline_date.setDate(QDate.currentDate().addDays(d))
            )
            date_quick_row.addWidget(btn)
        date_quick_row.addStretch()
        layout.addLayout(date_quick_row)

        time_quick_row = QHBoxLayout()
        time_quick_row.setSpacing(5)
        for label, hh, mm in _QUICK_TIME_BTNS:
            btn = QPushButton(label)
            btn.setFixedWidth(50)
            btn.setStyleSheet(
                build_editor_quick_button_style(self._ui_tokens, self._dialog_metrics)
            )
            btn.clicked.connect(lambda _, h=hh, m=mm: self.deadline_time.setTime(QTime(h, m)))
            time_quick_row.addWidget(btn)
        time_quick_row.addStretch()
        layout.addLayout(time_quick_row)

        ops_group = QGroupBox(t("dialog.directive.label_ops"))
        ops_inner = QHBoxLayout()
        ops_inner.setSpacing(16)
        ops_inner.setContentsMargins(10, 6, 10, 10)

        priority_col = QVBoxLayout()
        priority_col.setSpacing(4)
        priority_col.addWidget(QLabel(t("dialog.directive.label_priority")))
        self.priority_combo = QComboBox()
        # Use localized items from task_constants
        visible_priorities = [
            (label, code) for label, code in PRIORITY_COMBO_ITEMS if code != "low"
        ]
        for label, code in visible_priorities or [
            (t("priority.normal", "보통"), "normal"),
            (t("priority.high", "높음"), "high"),
            (t("priority.urgent", "긴급"), "urgent"),
        ]:
            self.priority_combo.addItem(label, code)
        priority_col.addWidget(self.priority_combo)
        ops_inner.addLayout(priority_col)

        status_col = QVBoxLayout()
        status_col.setSpacing(4)
        status_col.addWidget(QLabel(t("dialog.directive.label_status")))
        self.status_combo = QComboBox()
        for label, code in STATUS_COMBO_ITEMS:
            self.status_combo.addItem(label, code)
        idx_ip = self.status_combo.findData("in_progress")
        if idx_ip >= 0:
            self.status_combo.setCurrentIndex(idx_ip)
        status_col.addWidget(self.status_combo)
        ops_inner.addLayout(status_col)

        ops_group.setLayout(ops_inner)
        layout.addWidget(ops_group)

        memo_lbl = QLabel(t("dialog.directive.label_memo"))
        memo_lbl.setObjectName("TaskDialogFieldLabel")
        layout.addWidget(memo_lbl)
        self.memo_edit = QTextEdit()
        self.memo_edit.setPlaceholderText(t("dialog.directive.placeholder_memo"))
        self.memo_edit.setMinimumHeight(68)
        self.memo_edit.setMaximumHeight(100)
        layout.addWidget(self.memo_edit)

        from calendar_app.shared.tag_highlighter import HashTagHighlighter

        self._memo_highlighter = HashTagHighlighter(self.memo_edit.document())

        tag_hint = QLabel(t("dialog.directive.tag_hint"))
        tag_hint.setTextFormat(Qt.TextFormat.RichText)
        tag_hint.setWordWrap(True)
        tag_hint.setStyleSheet(
            build_editor_hint_style(
                self._ui_tokens,
                self._dialog_metrics,
                tone="accent",
                font_px=11,
            )
        )
        layout.addWidget(tag_hint)

        layout.addStretch()

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        btn_row = QHBoxLayout()
        if self.task_id:
            del_btn = QPushButton(t("dialog.directive.btn_delete"))
            del_btn.setObjectName("danger_btn")
            del_btn.clicked.connect(self.delete_data)
            btn_row.addWidget(del_btn)

        btn_row.addStretch()
        save_label = (
            t("dialog.directive.btn_save") if self.task_id else t("dialog.directive.btn_register")
        )
        self.save_btn = QPushButton(save_label)
        self.save_btn.setObjectName("primary_btn")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self.save_data)

        cancel_btn = QPushButton(t("dialog.common.cancel"))
        cancel_btn.setObjectName("ghost_btn")
        cancel_btn.clicked.connect(self.reject)

        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)
        self.setLayout(layout)

    def _setup_shortcuts(self):
        for seq in ("Ctrl+Return", "Ctrl+Enter"):
            QShortcut(QKeySequence(seq), self).activated.connect(self.save_data)

    def _on_content_changed(self, text: str):
        if text.strip() and hasattr(self, "_content_validator"):
            self._content_validator.clear()
        n = len(text)
        self.char_counter.setText(f"{n} / 120")
        if n >= 110:
            level = "danger"
        elif n >= 80:
            level = "warning"
        else:
            level = "normal"
        self.char_counter.setStyleSheet(build_editor_counter_style(self._ui_tokens, level=level))

    def _attach_receiver_completer(self):
        receivers = []
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cur = conn.cursor()
                cur.execute("PRAGMA table_info(task_directive)")
                columns = {row[1] for row in cur.fetchall()}
                receiver_col = (
                    "receiver_name"
                    if "receiver_name" in columns
                    else ("requester" if "requester" in columns else None)
                )
                if receiver_col is None:
                    raise sqlite3.OperationalError("task_directive receiver column missing")
                cur.execute(
                    f"SELECT DISTINCT {receiver_col} FROM task_directive "
                    f"WHERE {receiver_col} IS NOT NULL AND {receiver_col} != '' "
                    "ORDER BY id DESC LIMIT 40"
                )
                receivers = [r[0] for r in cur.fetchall()]
        except Exception:
            receivers = []

        if receivers:
            model = QStringListModel(receivers, self)
            comp = QCompleter(model, self)
            comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            comp.setFilterMode(Qt.MatchFlag.MatchContains)
            self.receiver_edit.setCompleter(comp)

    def set_priority(self, priority: str):
        priority = {"low": "normal"}.get(priority, priority)
        idx = self.priority_combo.findData(priority)
        if idx >= 0:
            self.priority_combo.setCurrentIndex(idx)

    def set_status(self, status: str):
        status = {"done": "completed", "overdue": "deferred", "canceled": "deferred"}.get(
            status, status
        )
        idx = self.status_combo.findData(status)
        if idx >= 0:
            self.status_combo.setCurrentIndex(idx)

    def _apply_deadline(self, deadline: str):
        if not deadline:
            return
        parts = deadline.strip().split(" ")
        date_part = parts[0]
        time_part = parts[1] if len(parts) > 1 else "00:00"
        self.deadline_date.setDate(QDate.fromString(date_part, "yyyy-MM-dd"))
        parsed_time = QTime.fromString(time_part, "HH:mm")
        if parsed_time.isValid():
            self.deadline_time.setTime(parsed_time)

    def load_data(self):
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cur = conn.cursor()
                cur.execute("PRAGMA table_info(task_directive)")
                columns = {row[1] for row in cur.fetchall()}
                receiver_col = (
                    "receiver_name"
                    if "receiver_name" in columns
                    else ("requester" if "requester" in columns else "NULL")
                )
                memo_col = (
                    "memo" if "memo" in columns else ("details" if "details" in columns else "NULL")
                )
                bg_col = "bg_color" if "bg_color" in columns else "NULL"
                priority_expr = (
                    "COALESCE(priority, 'normal')" if "priority" in columns else "'normal'"
                )
                cur.execute(
                    f"SELECT content, {receiver_col}, deadline, status, {memo_col}, {bg_col}, {priority_expr} "
                    "FROM task_directive WHERE id=?",
                    (self.task_id,),
                )
                row = cur.fetchone()
            if not row:
                return
            content, receiver, deadline, status, memo, _bg, priority = row
            self.content_edit.setText(content or "")
            self.receiver_edit.setText(receiver or "")
            self._apply_deadline(deadline or "")
            self.set_status(status or "in_progress")
            self.memo_edit.setPlainText(memo or "")
            self.set_priority(priority or "normal")
        except Exception:
            pass

    def save_data(self):
        content = self.content_edit.text().strip()
        if not self._content_validator.validate(
            lambda t: bool(t.strip()),
            t("dialog.directive.msg_content_required", "내용을 입력해 주세요."),
        ):
            self.content_edit.setFocus()
            return

        receiver = self.receiver_edit.text().strip()
        date_str = self.deadline_date.date().toString("yyyy-MM-dd")
        time_str = self.deadline_time.time().toString("HH:mm")
        deadline = f"{date_str} {time_str}"
        status = self.status_combo.currentData()
        priority = self.priority_combo.currentData()
        memo = self.memo_edit.toPlainText().strip()

        try:
            with sqlite3.connect(DB_PATH) as conn:
                cur = conn.cursor()
                cur.execute("PRAGMA table_info(task_directive)")
                columns = {row[1] for row in cur.fetchall()}
                if "receiver_name" not in columns:
                    cur.execute("ALTER TABLE task_directive ADD COLUMN receiver_name TEXT")
                    columns.add("receiver_name")
                if "memo" not in columns:
                    cur.execute("ALTER TABLE task_directive ADD COLUMN memo TEXT")
                    columns.add("memo")
                if "priority" not in columns:
                    cur.execute(
                        "ALTER TABLE task_directive ADD COLUMN priority TEXT DEFAULT 'normal'"
                    )
                    columns.add("priority")
                if "requester" in columns:
                    cur.execute(
                        "UPDATE task_directive "
                        "SET receiver_name = COALESCE(NULLIF(receiver_name, ''), requester) "
                        "WHERE COALESCE(receiver_name, '') = '' AND COALESCE(requester, '') != ''"
                    )
                if "details" in columns:
                    cur.execute(
                        "UPDATE task_directive "
                        "SET memo = COALESCE(NULLIF(memo, ''), details) "
                        "WHERE COALESCE(memo, '') = '' AND COALESCE(details, '') != ''"
                    )

                if self.task_id:
                    cur.execute(
                        "UPDATE task_directive "
                        "SET content=?, receiver_name=?, deadline=?, status=?, memo=?, priority=? "
                        "WHERE id=?",
                        (content, receiver, deadline, status, memo, priority, self.task_id),
                    )
                else:
                    cur.execute(
                        "INSERT INTO task_directive "
                        "(content, receiver_name, deadline, status, memo, priority) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (content, receiver, deadline, status, memo, priority),
                    )
                conn.commit()
            self.accept()
        except Exception as exc:
            QMessageBox.critical(
                self, t("dialog.common.error"), t("dialog.directive.msg_db_error", e=exc)
            )

    def delete_data(self):
        if not self.task_id:
            return
        reply = QMessageBox.question(
            self,
            t("dialog.common.delete"),
            t("dialog.common.delete_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            moved = directive_repo.move_directive_to_trash(
                int(self.task_id),
                reason="manual_trash_directive_dialog",
            )
            if not moved:
                raise RuntimeError("move_to_trash_failed")
            self.accept()
        except Exception as exc:
            QMessageBox.critical(
                self, t("dialog.common.error"), t("dialog.directive.msg_db_error", e=exc)
            )
