# -*- coding: utf-8 -*-
"""Shared focus-history view used by focus dialogs."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from calendar_app.application import focus_usecases
from calendar_app.infrastructure.db import legacy_focus_repo
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_editor_styles import (
    build_editor_quick_button_style,
    build_editor_text_style,
)
from calendar_app.presentation.dialogs.dialog_styles import (
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)


def _focus_history_style_bundle(tokens=None, metrics=None):
    tokens = dict(tokens or get_dialog_theme_tokens())
    metrics = dict(metrics or get_dialog_metric_tokens(apply_overrides=True))
    base_font_px = max(12, int(metrics.get("base_font_pt", 14)))
    list_radius = max(8, int(metrics.get("list_radius", 8)))
    border = tokens.get("border", "rgba(255,255,255,0.16)")
    border_soft = tokens.get("border_soft", "rgba(255,255,255,0.10)")
    surface_item = tokens.get("surface_item", "#1e1e26")
    surface_alt = tokens.get("surface_alt", "#1a1a22")
    surface_hover = tokens.get("surface_hover", "#252530")
    text_primary = tokens.get("text_primary", "#e7ecf4")
    text_secondary = tokens.get("text_secondary", "#c8ccd4")
    header_style = build_editor_text_style(
        tokens, tone="accent", font_px=base_font_px + 2, weight=700
    )
    primary_button_style = build_editor_quick_button_style(tokens, metrics, tone="accent")
    return {
        "header": header_style,
        "heading": build_editor_text_style(
            tokens, tone="primary", font_px=base_font_px, weight=700
        ),
        "summary": build_editor_text_style(
            tokens,
            tone="accent",
            font_px=max(12, base_font_px - 1),
            weight=700,
            padding="5px 0",
        ),
        "table": (
            "QTableWidget { "
            f"background-color: {surface_item}; alternate-background-color: {surface_alt}; "
            f"gridline-color: {border_soft}; border: 1px solid {border}; "
            f"border-radius: {list_radius}px; font-size: {base_font_px - 1}px; "
            f"selection-background-color: {tokens.get('list_selected_bg', surface_hover)}; "
            f"selection-color: {tokens.get('list_selected_text', text_primary)}; "
            "}"
            "QTableWidget::item { padding: 5px; }"
            "QHeaderView::section { "
            f"background-color: {surface_hover}; color: {text_secondary}; padding: 4px; "
            "border: none; font-weight: 700; }"
        ),
        "button_secondary": build_editor_quick_button_style(tokens, metrics, tone="secondary"),
        "button_primary": primary_button_style,
    }


def _format_focus_duration(total_secs: int) -> str:
    hours, remainder = divmod(max(0, int(total_secs or 0)), 3600)
    minutes, _ = divmod(remainder, 60)
    if hours > 0:
        return t(
            "focus.duration_hours_minutes",
            "{hours}h {minutes}m",
            hours=hours,
            minutes=minutes,
        )
    return t("focus.duration_minutes", "{minutes}m", minutes=minutes)


class FocusHistoryPanel(QWidget):
    """One rendering and interaction path for persisted focus sessions."""

    def __init__(
        self,
        parent=None,
        *,
        repo=legacy_focus_repo,
        show_heading: bool = True,
        allow_delete: bool = True,
        show_controls: bool = True,
        tokens=None,
        metrics=None,
    ):
        super().__init__(parent)
        self.repo = repo
        self._styles = _focus_history_style_bundle(tokens, metrics)
        self._init_ui(
            show_heading=show_heading,
            allow_delete=allow_delete,
            show_controls=show_controls,
        )

    def _init_ui(self, *, show_heading: bool, allow_delete: bool, show_controls: bool) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        if show_heading:
            heading = QLabel(t("focus_selector.logs_recent"))
            heading.setStyleSheet(self._styles["heading"])
            layout.addWidget(heading)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(self._styles["summary"])
        self.summary_label.setAccessibleName(
            t("focus_selector.log_summary_accessible", "집중 통계")
        )
        layout.addWidget(self.summary_label)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(
            [
                t("focus_selector.col_datetime"),
                t("focus_selector.col_task"),
                t("focus_selector.col_duration"),
            ]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setAccessibleName(t("focus_selector.logs_recent"))
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(self._styles["table"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)

        self.refresh_button = None
        self.delete_button = None
        if not show_controls:
            return

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.refresh_button = QPushButton(t("dialog.common.refresh"))
        self.refresh_button.setObjectName("ghost_btn")
        self.refresh_button.setAccessibleName(self.refresh_button.text())
        self.refresh_button.setAutoDefault(False)
        self.refresh_button.setStyleSheet(self._styles["button_secondary"])
        self.refresh_button.clicked.connect(self.reload)
        button_row.addWidget(self.refresh_button)

        if allow_delete:
            self.delete_button = QPushButton(t("common.delete", "Delete"))
            self.delete_button.setObjectName("danger_btn")
            self.delete_button.setAccessibleName(self.delete_button.text())
            self.delete_button.setAutoDefault(False)
            self.delete_button.clicked.connect(self.delete_selected)
            button_row.addWidget(self.delete_button)
        layout.addLayout(button_row)

    def reload(self) -> None:
        snapshot = focus_usecases.get_focus_history_snapshot(self.repo, limit=100, stats_limit=5000)
        if snapshot.load_error:
            message = t(
                "focus_selector.log_load_error",
                "집중 기록을 불러오지 못했습니다. 잠시 후 새로고침해 주세요.",
            )
            self.summary_label.setText(message)
            self.summary_label.setAccessibleDescription(message)
        else:
            stats = snapshot.stats
            summary = t(
                "focus_selector.log_summary",
                "오늘: {today_sessions}세션 ({today_time}) | 이번달: {month_sessions}세션 ({month_time})",
                today_sessions=stats.today_sessions,
                today_time=_format_focus_duration(stats.today_secs),
                month_sessions=stats.monthly_sessions,
                month_time=_format_focus_duration(stats.monthly_secs),
            )
            self.summary_label.setText(summary)
            self.summary_label.setAccessibleDescription(summary)

        self.table.setRowCount(0)
        for entry in snapshot.entries:
            row = self.table.rowCount()
            self.table.insertRow(row)
            date_item = QTableWidgetItem(entry.logged_at)
            date_item.setData(Qt.ItemDataRole.UserRole, entry.id)
            self.table.setItem(row, 0, date_item)
            self.table.setItem(
                row,
                1,
                QTableWidgetItem(
                    entry.task_name or t("focus_selector.deleted_task", "삭제된 작업")
                ),
            )
            minutes, seconds = divmod(entry.elapsed_secs, 60)
            self.table.setItem(
                row,
                2,
                QTableWidgetItem(t("focus_selector.duration", minutes=minutes, seconds=seconds)),
            )
            for column in (0, 2):
                item = self.table.item(row, column)
                if item is not None:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

    def delete_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                t("focus_selector.delete_confirm_title", "기록 삭제"),
                t("focus_selector.delete_no_selection", "삭제할 항목을 먼저 선택하세요."),
            )
            return

        item = self.table.item(row, 0)
        log_id = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if not log_id:
            return
        answer = QMessageBox.question(
            self,
            t("focus_selector.delete_confirm_title", "기록 삭제"),
            t("focus_selector.delete_confirm_msg", "이 집중 기록을 삭제하시겠습니까?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes and focus_usecases.delete_focus_log(
            self.repo, log_id
        ):
            self.reload()
