from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from calendar_app.application import focus_usecases
from calendar_app.infrastructure.db import legacy_focus_repo
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_editor_styles import (
    build_editor_quick_button_style,
    build_editor_text_style,
)
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)


def _focus_log_style_bundle(tokens=None, metrics=None):
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
    text_muted = tokens.get("text_muted", "#99aab5")
    return {
        "header": build_editor_text_style(
            tokens, tone="accent", font_px=base_font_px + 2, weight=700
        ),
        "table": (
            "QTableWidget { "
            f"background-color: {surface_item}; alternate-background-color: {surface_alt}; "
            f"gridline-color: {border_soft}; border: 1px solid {border}; border-radius: {list_radius}px; "
            f"font-size: {base_font_px - 1}px; selection-background-color: {tokens.get('list_selected_bg', surface_hover)}; "
            f"selection-color: {tokens.get('list_selected_text', text_primary)}; "
            "}"
            "QTableWidget::item { "
            "padding: 5px; "
            "}"
            "QHeaderView::section { "
            f"background-color: {surface_hover}; color: {text_muted}; padding: 4px; border: none; font-weight: 700; "
            "}"
        ),
        "button_secondary": build_editor_quick_button_style(tokens, metrics, tone="secondary"),
        "button_primary": build_editor_quick_button_style(tokens, metrics, tone="accent"),
    }


class FocusLogDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        apply_dialog_title(self, t("dialog.focus_log.title"))
        apply_common_dialog_style(self, minimum_width=500, size=(550, 600))
        self._ui_tokens = get_dialog_theme_tokens()
        self._dialog_metrics = get_dialog_metric_tokens(apply_overrides=True)
        self._style_bundle = _focus_log_style_bundle(self._ui_tokens, self._dialog_metrics)
        self._init_ui()
        self._load_logs()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # 헤더
        header = QLabel(t("dialog.focus_log.header"))
        header.setStyleSheet(self._style_bundle["header"])
        layout.addWidget(header)

        # 테이블
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            [
                t("focus_selector.col_datetime"),
                t("focus_selector.col_task"),
                t("focus_selector.col_duration"),
                "ID",
            ]
        )

        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(self._style_bundle["table"])

        # 헤더 설정
        h_header = self.table.horizontalHeader()
        h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self.table)

        footer, close_btn, _ = build_dialog_footer(
            ok_label=t("dialog.focus_log.close", "닫기"),
            cancel_label=None,
            ok_object_name="ghost_btn",
        )
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet(self._style_bundle["button_secondary"])

        refresh_btn = QPushButton(t("dialog.focus_log.refresh", "새로고침"))
        refresh_btn.setObjectName("ghost_btn")
        refresh_btn.setStyleSheet(self._style_bundle["button_secondary"])
        refresh_btn.clicked.connect(self._load_logs)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(refresh_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _load_logs(self):
        logs = focus_usecases.get_focus_logs(legacy_focus_repo, limit=100)
        self.table.setRowCount(0)

        for log in logs:
            # (w_id, task_id, name, duration_seconds, logged_at)
            w_id, t_id, t_name, secs, dt_str = log

            row = self.table.rowCount()
            self.table.insertRow(row)

            # 1. 날짜/시간
            self.table.setItem(row, 0, QTableWidgetItem(str(dt_str)))
            # 2. 수행 업무
            name_text = t_name if t_name else f"{t('focus_selector.deleted_task')} (ID:{t_id})"
            self.table.setItem(row, 1, QTableWidgetItem(name_text))
            # 3. 소요 시간
            mins = secs // 60
            left_secs = secs % 60
            duration_text = t("focus_selector.duration", minutes=mins, seconds=left_secs)
            self.table.setItem(row, 2, QTableWidgetItem(duration_text))
            # 4. ID (히든 데이터용일 수 있으나 일단 표시)
            self.table.setItem(row, 3, QTableWidgetItem(str(w_id)))

            # 가운데 정렬 등 스타일
            for col in range(4):
                item = self.table.item(row, col)
                if col != 1:  # 업무명 빼고 가운데 정렬
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
