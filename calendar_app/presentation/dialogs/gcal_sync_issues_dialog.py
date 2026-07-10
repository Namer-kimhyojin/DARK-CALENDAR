# -*- coding: utf-8 -*-
"""Dialog listing unresolved Google sync issues with detailed guidance."""

import json

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.db import task_repo
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_editor_styles import (
    build_editor_quick_button_style,
    build_editor_text_style,
)
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
    set_footer_loading,
)
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic

_DELETE_RETRY_LIMIT = 5


def _gcal_issue_style_bundle(tokens=None, metrics=None):
    tokens = dict(tokens or get_dialog_theme_tokens())
    metrics = dict(metrics or get_dialog_metric_tokens(apply_overrides=True))
    base_font_px = max(12, int(metrics.get("base_font_pt", 14)))
    list_radius = max(8, int(metrics.get("list_radius", 8)))
    group_radius = max(10, int(metrics.get("group_radius", 10)))
    border = tokens.get("border", "rgba(255,255,255,0.16)")
    border_soft = tokens.get("border_soft", "rgba(255,255,255,0.10)")
    surface_item = tokens.get("surface_item", "#1e1e26")
    surface_alt = tokens.get("surface_alt", "#1a1a22")
    surface_hover = tokens.get("surface_hover", "#252530")
    text_primary = tokens.get("text_primary", "#e7ecf4")
    text_secondary = tokens.get("text_secondary", "#cbd5e0")
    text_muted = tokens.get("text_muted", "#99aab5")
    return {
        "header_title": build_editor_text_style(
            tokens, tone="accent", font_px=base_font_px + 3, weight=700
        ),
        "header_body": build_editor_text_style(
            tokens, tone="muted", font_px=max(12, base_font_px - 1)
        ),
        "table": (
            "QTableWidget { "
            f"background-color: {surface_item}; alternate-background-color: {surface_alt}; "
            f"gridline-color: transparent; border: 1px solid {border}; border-radius: {list_radius}px; "
            f"font-size: {base_font_px}px; selection-background-color: {tokens.get('list_selected_bg', surface_hover)}; "
            f"selection-color: {tokens.get('list_selected_text', text_primary)}; "
            "}"
            "QTableWidget::item { "
            f"padding: 8px; border-bottom: 1px solid {border_soft}; "
            "}"
            "QHeaderView::section { "
            f"background-color: {surface_hover}; color: {text_muted}; padding: 10px; border: none; "
            f"border-bottom: 1px solid {border}; font-weight: 700; font-size: {base_font_px}px; "
            "}"
        ),
        "guidance_box": (
            "QFrame#GuidanceBox { "
            f"background-color: {surface_alt}; border: 1px solid {border}; border-radius: {group_radius}px; "
            "}"
        ),
        "guidance_icon": build_editor_text_style(
            tokens, tone="accent", font_px=base_font_px + 2, weight=700
        ),
        "guidance_title": build_editor_text_style(
            tokens, tone="accent", font_px=max(13, base_font_px), weight=700
        ),
        "guidance_text": build_editor_text_style(
            tokens, tone="secondary", font_px=max(12, base_font_px - 1), background="transparent"
        ),
        "diff_panel": (
            "QFrame#DiffPanel { "
            f"background-color: {surface_alt}; border: 1px solid {tokens.get('accent_soft_border', border)}; "
            f"border-radius: {group_radius}px; "
            "}"
        ),
        "diff_local_title": build_editor_text_style(
            tokens, tone="accent", font_px=max(12, base_font_px - 1), weight=700
        ),
        "diff_remote_title": build_editor_text_style(
            tokens, tone="success", font_px=max(12, base_font_px - 1), weight=700
        ),
        "diff_text": (
            "QTextEdit { "
            f"background-color: {surface_item}; color: {text_secondary}; border: 1px solid {border_soft}; "
            f"border-radius: {max(6, list_radius - 2)}px; padding: 6px; font-size: {max(12, base_font_px - 1)}px; "
            "}"
        ),
        "button_secondary": build_editor_quick_button_style(tokens, metrics, tone="secondary"),
        "button_accent": build_editor_quick_button_style(tokens, metrics, tone="accent"),
        "button_warning": build_editor_quick_button_style(tokens, metrics, tone="warning"),
        "status_manual": tokens.get("danger_hex", "#ff5f5f"),
        "status_retry": tokens.get("accent", "#4da6ff"),
        "status_healed": tokens.get("success_hex", "#42b883"),
        "status_ignored": text_muted,
    }


class GCalSyncIssuesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.app = parent
        self._ui_tokens = get_dialog_theme_tokens()
        self._dialog_metrics = get_dialog_metric_tokens(apply_overrides=True)
        self._style_bundle = _gcal_issue_style_bundle(self._ui_tokens, self._dialog_metrics)
        apply_dialog_title(self, t("gcal.issues_title", "구글 동기화 문제 해결"))
        apply_common_dialog_style(self, minimum_width=1000, size=(1100, 720))

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        # 1. Header with description
        header_container = QWidget()
        header_layout = QVBoxLayout(header_container)
        header_layout.setContentsMargins(0, 0, 0, 5)
        header_layout.setSpacing(4)

        main_title = QLabel(t("gcal.issues_title", "구글 동기화 문제 해결"), self)
        main_title.setStyleSheet(self._style_bundle["header_title"])
        header_layout.addWidget(main_title)

        description = QLabel(
            t(
                "gcal_settings.diagnostics_summary",
                "동기화 상태와 미해결 문제를 확인하고 조치할 수 있습니다. 시스템이 자동으로 해결한 내역도 포함됩니다.",
            ),
            self,
        )
        description.setStyleSheet(self._style_bundle["header_body"])
        header_layout.addWidget(description)
        root.addWidget(header_container)

        # 2. Table with more detailed columns
        self.table = QTableWidget(0, 6, self)
        self.table.setHorizontalHeaderLabels(
            [
                t("gcal.issues_type", "유형"),
                t("gcal.issues_name", "상세 내용"),
                t("gcal.issues_deadline", "시각/기한"),
                t("gcal.issues_error", "발생 현상"),
                t("gcal.issues_action_taken", "시스템 조치"),
                t("gcal.issues_status", "현재 상태"),
            ]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setStyleSheet(self._style_bundle["table"])

        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        root.addWidget(self.table, 5)

        # 3. Guidance Panel (Redesigned)
        self.guidance_box = QFrame(self)
        self.guidance_box.setObjectName("GuidanceBox")
        self.guidance_box.setStyleSheet(self._style_bundle["guidance_box"])
        guidance_layout = QVBoxLayout(self.guidance_box)
        guidance_layout.setContentsMargins(15, 12, 15, 12)

        guidance_header = QHBoxLayout()
        guidance_icon = QLabel()
        guidance_icon.setPixmap(_ic(ICON.TIP).pixmap(16, 16))
        guidance_icon.setStyleSheet(self._style_bundle["guidance_icon"])
        guidance_header.addWidget(guidance_icon)

        guidance_title = QLabel(
            t("gcal.issues_guidance", "조치 안내 및 상태 상세 설명"), self.guidance_box
        )
        guidance_title.setStyleSheet(self._style_bundle["guidance_title"])
        guidance_header.addWidget(guidance_title)
        guidance_header.addStretch()
        guidance_layout.addLayout(guidance_header)

        self.guidance_text = QTextEdit(self.guidance_box)
        self.guidance_text.setReadOnly(True)
        self.guidance_text.setFrameShape(QFrame.Shape.NoFrame)
        self.guidance_text.setStyleSheet(self._style_bundle["guidance_text"])
        self.guidance_text.setPlaceholderText(
            t(
                "gcal.issues_select_hint",
                "항목을 선택하면 이 문제가 왜 발생했는지, 시스템이 어떤 처리를 했는지 자세히 안내해 드립니다.",
            )
        )
        guidance_layout.addWidget(self.guidance_text)

        root.addWidget(self.guidance_box, 2)

        # [1] Diff panel — hidden until a conflict row is selected
        self._diff_panel = QFrame(self)
        self._diff_panel.setObjectName("DiffPanel")
        self._diff_panel.setStyleSheet(self._style_bundle["diff_panel"])
        diff_layout = QHBoxLayout(self._diff_panel)
        diff_layout.setContentsMargins(12, 10, 12, 10)
        diff_layout.setSpacing(12)

        _local_col = QVBoxLayout()
        _local_title = QLabel(t("gcal.diff.local_title", "로컬 버전"))
        _local_title.setStyleSheet(self._style_bundle["diff_local_title"])
        _local_col.addWidget(_local_title)
        self._diff_local = QTextEdit()
        self._diff_local.setReadOnly(True)
        self._diff_local.setMaximumHeight(140)
        self._diff_local.setFrameShape(QFrame.Shape.NoFrame)
        self._diff_local.setStyleSheet(self._style_bundle["diff_text"])
        _local_col.addWidget(self._diff_local)
        diff_layout.addLayout(_local_col, 1)

        _remote_col = QVBoxLayout()
        _remote_title = QLabel(t("gcal.diff.remote_title", "구글 버전"))
        _remote_title.setStyleSheet(self._style_bundle["diff_remote_title"])
        _remote_col.addWidget(_remote_title)
        self._diff_remote = QTextEdit()
        self._diff_remote.setReadOnly(True)
        self._diff_remote.setMaximumHeight(140)
        self._diff_remote.setFrameShape(QFrame.Shape.NoFrame)
        self._diff_remote.setStyleSheet(self._style_bundle["diff_text"])
        _remote_col.addWidget(self._diff_remote)
        diff_layout.addLayout(_remote_col, 1)

        self._diff_panel.setVisible(False)
        root.addWidget(self._diff_panel, 2)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        # 4. Action Buttons
        button_container = QWidget()
        btn_layout = QHBoxLayout(button_container)
        btn_layout.setContentsMargins(0, 5, 0, 0)
        btn_layout.setSpacing(10)

        # Group 1: Refresh/Retry
        self.refresh_btn = QPushButton(t("dialog.common.refresh", "새로고침"))
        self.refresh_btn.setIcon(_ic(ICON.REFRESH))
        self.refresh_btn.setMinimumHeight(40)
        self.refresh_btn.setStyleSheet(self._style_bundle["button_secondary"])
        self.refresh_btn.clicked.connect(self.load_rows)
        btn_layout.addWidget(self.refresh_btn)

        self.retry_btn = QPushButton(t("gcal.issues_retry", "재시도"))
        self.retry_btn.setIcon(_ic(ICON.STATUS_IN_PROGRESS))
        self.retry_btn.setMinimumHeight(40)
        self.retry_btn.setStyleSheet(self._style_bundle["button_accent"])
        self.retry_btn.setToolTip(
            t("gcal.issues_retry_tooltip", "문제가 해결되었다면 다시 동기화를 시도합니다.")
        )
        self.retry_btn.clicked.connect(self.retry_selected)
        btn_layout.addWidget(self.retry_btn)

        # [1] Conflict resolution buttons
        self.keep_local_btn = QPushButton(t("gcal.issues_keep_local", "로컬 유지"))
        self.keep_local_btn.setIcon(_ic(ICON.PRESET))
        self.keep_local_btn.setMinimumHeight(40)
        self.keep_local_btn.setStyleSheet(self._style_bundle["button_accent"])
        self.keep_local_btn.setToolTip(
            t("gcal.issues_keep_local_tooltip", "로컬 변경 내용을 유지하고 구글에 덮어씁니다.")
        )
        self.keep_local_btn.clicked.connect(self.resolve_keep_local)
        self.keep_local_btn.setEnabled(False)
        btn_layout.addWidget(self.keep_local_btn)

        self.use_remote_btn = QPushButton(t("gcal.issues_use_remote", "구글 버전 적용"))
        self.use_remote_btn.setIcon(_ic(ICON.CLOUD))
        self.use_remote_btn.setMinimumHeight(40)
        self.use_remote_btn.setStyleSheet(self._style_bundle["button_secondary"])
        self.use_remote_btn.setToolTip(
            t("gcal.issues_use_remote_tooltip", "구글 캘린더 버전으로 로컬 데이터를 덮어씁니다.")
        )
        self.use_remote_btn.clicked.connect(self.resolve_use_remote)
        self.use_remote_btn.setEnabled(False)
        btn_layout.addWidget(self.use_remote_btn)

        btn_layout.addSpacing(20)

        # Orphan scan button
        self.scan_orphan_btn = QPushButton(t("gcal.issues_scan_orphans", "구글 고아 스캔"))
        self.scan_orphan_btn.setIcon(_ic(ICON.SEARCH))
        self.scan_orphan_btn.setMinimumHeight(40)
        self.scan_orphan_btn.setStyleSheet(self._style_bundle["button_secondary"])
        self.scan_orphan_btn.setToolTip(
            t(
                "gcal.issues_scan_orphans_tooltip",
                "구글에 남아있지만 로컬에는 없는 일정을 찾아 표시합니다 (최근 6개월).",
            )
        )
        self.scan_orphan_btn.clicked.connect(self.run_orphan_scan)
        btn_layout.addWidget(self.scan_orphan_btn)

        # Delete-from-google button (orphan rows only)
        self.delete_remote_btn = QPushButton(t("gcal.issues_delete_remote", "구글에서 삭제"))
        self.delete_remote_btn.setIcon(_ic(ICON.DELETE))
        self.delete_remote_btn.setMinimumHeight(40)
        self.delete_remote_btn.setStyleSheet(self._style_bundle["button_warning"])
        self.delete_remote_btn.setToolTip(
            t(
                "gcal.issues_delete_remote_tooltip",
                "선택한 고아 이벤트를 구글 캘린더에서 삭제 큐에 추가합니다. 다음 동기화에서 실제 삭제됩니다.",
            )
        )
        self.delete_remote_btn.clicked.connect(self.delete_selected_remote)
        self.delete_remote_btn.setEnabled(False)
        btn_layout.addWidget(self.delete_remote_btn)

        # Group 2: Management
        self.clear_btn = QPushButton(t("gcal.issues_clear", "오류 기록 지우기"))
        self.clear_btn.setIcon(_ic(ICON.DELETE))
        self.clear_btn.setMinimumHeight(40)
        self.clear_btn.setStyleSheet(self._style_bundle["button_secondary"])
        self.clear_btn.setToolTip(
            t(
                "gcal.issues_clear_tooltip",
                "단순히 목록에서 이 표시만 제거합니다. 근본적인 원인이 해결되지 않으면 다시 나타날 수 있습니다.",
            )
        )
        self.clear_btn.clicked.connect(self.clear_selected_error)
        btn_layout.addWidget(self.clear_btn)

        self.force_ignore_btn = QPushButton(t("gcal.issues_force_ignore", "동기화 포기"))
        self.force_ignore_btn.setIcon(_ic(ICON.STATUS_CANCELED))
        self.force_ignore_btn.setMinimumHeight(40)
        self.force_ignore_btn.setStyleSheet(self._style_bundle["button_warning"])
        self.force_ignore_btn.setToolTip(
            t(
                "gcal.issues_force_ignore_tooltip",
                "이 항목의 구글 동기화를 완전히 중단하고 로컬 일정으로만 유지합니다.",
            )
        )
        self.force_ignore_btn.clicked.connect(self.force_ignore_selected)
        btn_layout.addWidget(self.force_ignore_btn)

        btn_layout.addStretch(1)

        # Group 3: Clean up
        self.clear_healed_btn = QPushButton(t("gcal.issues_clear_healed", "해결된 항목 정리"))
        self.clear_healed_btn.setIcon(_ic(ICON.STATUS_COMPLETED))
        self.clear_healed_btn.setMinimumHeight(40)
        self.clear_healed_btn.setStyleSheet(self._style_bundle["button_secondary"])
        self.clear_healed_btn.clicked.connect(self.clear_all_resolved)
        btn_layout.addWidget(self.clear_healed_btn)

        self.close_btn = QPushButton(t("dialog.common.close", "닫기"))
        self.close_btn.setObjectName("ghost_btn")
        self.close_btn.setMinimumHeight(40)
        self.close_btn.setMinimumWidth(100)
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)

        root.addWidget(button_container)

        # Cached orphan scan results (populated by run_orphan_scan)
        self._orphan_rows = []

        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.load_rows()

    def _map_error_to_friendly(self, error_raw):
        if not error_raw:
            return "-", "-"

        raw_msg = str(error_raw).lower()
        if "remote_newer_than_local" in raw_msg:
            return t("gcal.errors.remote_newer_than_local", "서버 버전 우선"), t(
                "gcal.treatments.mirrored", "데이터 동기화"
            )
        if "not_found" in raw_msg:
            return t("gcal.errors.not_found", "일정 찾지 못함"), t(
                "gcal.treatments.auto_healing", "자동 복원"
            )
        if "forbidden" in raw_msg or "403" in raw_msg:
            return t("gcal.errors.forbidden", "권한 없음"), t(
                "gcal.treatments.stopped", "시도 중단"
            )
        if "auth_required" in raw_msg or "auth" in raw_msg or "401" in raw_msg:
            return t("gcal.errors.auth_required", "인증 필요"), t(
                "gcal.treatments.stopped", "시도 중단"
            )
        if "delete_failed" in raw_msg:
            return t("gcal.errors.delete_failed", "삭제 실패"), t(
                "gcal.treatments.pending_retry", "재시도 대기"
            )
        if "push_failed" in raw_msg:
            return t("gcal.errors.push_failed", "전송 실패"), t(
                "gcal.treatments.pending_retry", "재시도 대기"
            )

        return error_raw, t("gcal.treatments.manual", "수동 확인")

    def _load_snapshot_json(self, raw_json):
        if not raw_json:
            return {}
        if isinstance(raw_json, dict):
            return raw_json
        try:
            loaded = json.loads(raw_json)
            return loaded if isinstance(loaded, dict) else {}
        except Exception:
            return {}

    def _append_issue_row(
        self,
        row_index,
        issue_type,
        name,
        deadline,
        error_friendly,
        treatment_friendly,
        status_friendly,
        meta,
    ):
        values = [
            issue_type,
            name,
            deadline,
            error_friendly,
            treatment_friendly,
            status_friendly,
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            if col == 0:
                item.setData(Qt.ItemDataRole.UserRole, meta)

            # Status styling
            if col == 5:
                st = str(value)
                if st == t("gcal.issues_manual_needed", "사용자 확인 필요") or st == t(
                    "gcal.issues_retry_exhausted", "재시도 한도 초과"
                ):
                    item.setText(st)
                    item.setForeground(QColor(self._style_bundle["status_manual"]))
                elif st == t("gcal.issues_retry_scheduled", "재시도 예정"):
                    item.setText(st)
                    item.setForeground(QColor(self._style_bundle["status_retry"]))
                elif st == t("gcal.issues_auto_healed", "시스템 자동 복구"):
                    item.setText(st)
                    item.setForeground(QColor(self._style_bundle["status_healed"]))
                elif st == t("gcal.issues_ignored", "무시됨"):
                    item.setText(st)
                    item.setForeground(QColor(self._style_bundle["status_ignored"]))

            self.table.setItem(row_index, col, item)

    def load_rows(self):
        self.table.setRowCount(0)
        rows = []
        # 1. Unified tasks errors
        for row in task_repo.get_unified_task_gcal_errors():
            raw_err = row.get("gcal_sync_error")
            err_text, treatment = self._map_error_to_friendly(raw_err)

            dirty = int(row.get("gcal_dirty") or 0) == 1
            status = (
                t("gcal.issues_retry_scheduled", "재시도 예정")
                if dirty
                else t("gcal.issues_manual_needed", "사용자 확인 필요")
            )

            if "not_found" in str(raw_err or "").lower():
                status = t("gcal.issues_auto_healed", "시스템 자동 복구")

            rows.append(
                {
                    "type": "task",
                    "id": row.get("id"),
                    "issue_type": t("gcal.issues_type_task", "일정"),
                    "name": row.get("name") or t("panel.common.no_title", "(제목 없음)"),
                    "deadline": row.get("deadline") or "-",
                    "error": err_text,
                    "raw_error": raw_err,
                    "treatment": treatment,
                    "status": status,
                    "dirty": dirty,
                }
            )

        # 2. Sync conflict queue
        for row in task_repo.list_gcal_sync_conflicts(only_unresolved=True, limit=500):
            conflict_kind = str(row.get("conflict_kind") or "remote_overwrite")
            raw_err = (
                "remote_newer_than_local" if conflict_kind == "remote_overwrite" else conflict_kind
            )
            err_text, _ = self._map_error_to_friendly(raw_err)
            local_snapshot = self._load_snapshot_json(row.get("local_snapshot_json"))
            remote_snapshot = self._load_snapshot_json(row.get("remote_snapshot_json"))
            local_task_id = row.get("local_task_id")
            local_task = task_repo.get_unified_task(local_task_id) if local_task_id else None
            local_name = (
                (local_task or {}).get("name")
                or local_snapshot.get("name")
                or remote_snapshot.get("summary")
                or t("panel.common.no_title", "(제목 없음)")
            )
            event_id = str(row.get("gcal_event_id") or "").strip()
            display_error = f"{err_text} [{event_id}]" if event_id else err_text
            rows.append(
                {
                    "type": "conflict",
                    "id": row.get("id"),
                    "local_task_id": local_task_id,
                    "issue_type": t("gcal.issues_type_conflict", "동기화 충돌"),
                    "name": local_name,
                    "deadline": row.get("created_at") or "-",
                    "error": display_error,
                    "raw_error": raw_err,
                    "treatment": t("gcal.treatments.manual", "수동 확인"),
                    "status": t("gcal.issues_manual_needed", "사용자 확인 필요"),
                    "dirty": True,
                    "local_snapshot": local_snapshot,
                    "remote_snapshot": remote_snapshot,
                }
            )

        # 3.5 Orphan remote events (only after user runs scan)
        for orphan in getattr(self, "_orphan_rows", []):
            event_id = orphan.get("gcal_event_id", "")
            cal_summary = orphan.get("calendar_summary", "")
            start_text = orphan.get("start", "") or "-"
            name = orphan.get("summary") or "(제목 없음)"
            display_name = f"[{cal_summary}] {name}" if cal_summary else name
            rows.append(
                {
                    "type": "google_orphan",
                    "id": event_id,
                    "gcal_event_id": event_id,
                    "gcal_calendar_id": orphan.get("gcal_calendar_id"),
                    "calendar_summary": cal_summary,
                    "issue_type": t("gcal.issues_type_orphan", "구글 고아"),
                    "name": display_name,
                    "deadline": start_text,
                    "error": t(
                        "gcal.errors.remote_orphan",
                        "구글에만 존재 (로컬 매칭 없음)",
                    ),
                    "raw_error": "remote_orphan",
                    "treatment": t("gcal.treatments.manual", "수동 확인"),
                    "status": t("gcal.issues_manual_needed", "사용자 확인 필요"),
                    "dirty": False,
                }
            )

        # 3. Delete queue errors
        for row in task_repo.get_gcal_delete_queue():
            if not row.get("last_error"):
                continue
            retry_count = int(row.get("retry_count") or 0)
            exhausted = retry_count >= _DELETE_RETRY_LIMIT
            raw_err = row.get("last_error")
            err_text, treatment = self._map_error_to_friendly(raw_err)
            status = (
                t("gcal.issues_retry_exhausted", "재시도 한도 초과")
                if exhausted
                else t("gcal.issues_retry_scheduled", "재시도 예정")
            )
            if exhausted:
                treatment = t(
                    "gcal.treatments.manual_retry",
                    "오류 확인 후 수동 재시도",
                )

            rows.append(
                {
                    "type": "delete_queue",
                    "id": row.get("id"),
                    "issue_type": t("gcal.issues_type_delete", "삭제 대기"),
                    "name": t("gcal.issues_delete_queue", "삭제 대기 이벤트"),
                    "deadline": row.get("created_at") or "-",
                    "error": f"{err_text} ({retry_count}/{_DELETE_RETRY_LIMIT})",
                    "raw_error": raw_err,
                    "treatment": treatment,
                    "status": status,
                    "dirty": False,
                    "retry_exhausted": exhausted,
                }
            )

        self.table.setRowCount(len(rows))
        for idx, row in enumerate(rows):
            self._append_issue_row(
                idx,
                row["issue_type"],
                row["name"],
                row["deadline"],
                row["error"],
                row["treatment"],
                row["status"],
                row,
            )

        # Adjust column widths
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

    def run_orphan_scan(self):
        """Scan Google calendars for orphan events (no local match)."""
        if not self.app or not hasattr(self.app, "gcal_sync"):
            QMessageBox.information(
                self,
                t("gcal.issues_scan_orphans", "구글 고아 스캔"),
                t(
                    "gcal.issues_scan_no_sync",
                    "구글 동기화가 설정되지 않아 스캔할 수 없습니다.",
                ),
            )
            return

        set_footer_loading(
            self.scan_orphan_btn,
            True,
            loading_text=t("gcal.issues_scanning", "스캔 중..."),
        )
        try:
            from calendar_app.infrastructure.google_sync.engine import (
                scan_orphan_remote_events,
            )

            try:
                orphans = scan_orphan_remote_events(self.app, lookback_days=180)
            except Exception:
                import logging as _logging

                _logging.getLogger(__name__).exception("orphan scan failed")
                orphans = []

            self._orphan_rows = orphans or []
            self.load_rows()

            if self.app and hasattr(self.app, "show_toast"):
                if orphans:
                    self.app.show_toast(
                        t("gcal.issues_scan_orphans", "구글 고아 스캔"),
                        t(
                            "gcal.issues_scan_found",
                            "구글 고아 이벤트 {n}건 발견. 목록에서 확인 후 삭제하세요.",
                        ).format(n=len(orphans)),
                    )
                else:
                    self.app.show_toast(
                        t("gcal.issues_scan_orphans", "구글 고아 스캔"),
                        t(
                            "gcal.issues_scan_clean",
                            "구글 고아 이벤트 없음. 깨끗합니다.",
                        ),
                    )
        finally:
            set_footer_loading(self.scan_orphan_btn, False)

    def delete_selected_remote(self):
        """Queue selected orphan event for deletion from Google."""
        meta = self._selected_meta()
        if not meta or meta.get("type") != "google_orphan":
            return

        event_id = str(meta.get("gcal_event_id") or "").strip()
        cal_id = str(meta.get("gcal_calendar_id") or "").strip()
        if not event_id:
            return

        reply = QMessageBox.question(
            self,
            t("gcal.issues_delete_remote", "구글에서 삭제"),
            t(
                "gcal.issues_delete_remote_confirm",
                "이 이벤트를 구글 캘린더에서 삭제합니다.\n\n"
                "이벤트: {name}\n캘린더: {cal}\n\n"
                "삭제 큐에 추가되며 다음 동기화 시 처리됩니다. 계속하시겠습니까?",
            ).format(
                name=meta.get("name") or "(제목 없음)",
                cal=meta.get("calendar_summary") or cal_id or "(알 수 없음)",
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        ok = False
        try:
            ok = bool(
                task_repo.queue_gcal_delete(
                    event_id,
                    local_task_id=None,
                    gcal_calendar_id=cal_id or None,
                )
            )
        except Exception:
            import logging as _logging

            _logging.getLogger(__name__).exception("queue_gcal_delete failed for orphan")
            ok = False

        if ok:
            # Remove from local cache so it doesn't reappear after reload
            self._orphan_rows = [o for o in self._orphan_rows if o.get("gcal_event_id") != event_id]
            if self.app and hasattr(self.app, "sync_google_calendar"):
                import contextlib

                with contextlib.suppress(Exception):
                    self.app.sync_google_calendar(silent=True)
            if self.app and hasattr(self.app, "show_toast"):
                self.app.show_toast(
                    t("gcal.issues_delete_remote", "구글에서 삭제"),
                    t(
                        "gcal.issues_delete_queued",
                        "삭제 큐에 추가했습니다. 동기화가 끝나면 구글에서 사라집니다.",
                    ),
                )
            self.load_rows()
        else:
            QMessageBox.warning(
                self,
                t("gcal.issues_delete_remote", "구글에서 삭제"),
                t(
                    "gcal.issues_delete_failed",
                    "삭제 큐에 추가하지 못했습니다. 로그를 확인하세요.",
                ),
            )

    def _format_snapshot(self, snap: dict) -> str:
        """Return a human-readable text summary of a conflict snapshot dict."""
        if not snap:
            return t("gcal.diff.empty", "(비어 있음)")
        empty = t("gcal.diff.empty", "(비어 있음)")
        lines = [
            f"{t('gcal.diff.field_name', '제목')}: {snap.get('name') or snap.get('summary') or empty}",
            f"{t('gcal.diff.field_start', '시작')}: {snap.get('deadline') or snap.get('start') or empty}",
            f"{t('gcal.diff.field_end', '종료')}: {snap.get('end_date') or snap.get('end') or empty}",
            f"{t('gcal.diff.field_desc', '설명')}: {(snap.get('description') or empty)[:120]}",
            f"{t('gcal.diff.field_location', '장소')}: {snap.get('location') or empty}",
        ]
        return "\n".join(lines)

    def _on_selection_changed(self):
        meta = self._selected_meta()
        if not meta:
            self.guidance_text.setHtml("")
            self._diff_panel.setVisible(False)
            self.keep_local_btn.setEnabled(False)
            self.use_remote_btn.setEnabled(False)
            if hasattr(self, "delete_remote_btn"):
                self.delete_remote_btn.setEnabled(False)
            return

        is_orphan = meta.get("type") == "google_orphan"
        if hasattr(self, "delete_remote_btn"):
            self.delete_remote_btn.setEnabled(is_orphan)

        is_conflict = meta.get("type") == "conflict"
        if is_conflict:
            local_snap = self._load_snapshot_json(
                meta.get("local_snapshot_json") or meta.get("local_snapshot")
            )
            remote_snap = self._load_snapshot_json(
                meta.get("remote_snapshot_json") or meta.get("remote_snapshot")
            )
            self._diff_local.setPlainText(self._format_snapshot(local_snap))
            self._diff_remote.setPlainText(self._format_snapshot(remote_snap))
            self._diff_panel.setVisible(True)
            self.guidance_box.setVisible(False)
        else:
            self._diff_panel.setVisible(False)
            self.guidance_box.setVisible(True)

        self.keep_local_btn.setEnabled(is_conflict)
        self.use_remote_btn.setEnabled(is_conflict)

        raw = str(meta.get("raw_error") or "").lower()
        html_content = ""

        if meta.get("type") == "delete_queue" and meta.get("retry_exhausted"):
            html_content = t(
                "gcal.guidance.delete_retry_exhausted",
                "삭제 요청이 자동 재시도 한도에 도달해 일시 중지되었습니다. "
                "마지막 오류와 Google 캘린더 권한을 확인한 뒤 '재시도'를 누르세요. "
                "항목은 자동 삭제되지 않으며 진단 목록에 계속 보존됩니다.",
            )
        elif raw == "remote_orphan":
            html_content = t(
                "gcal.guidance.remote_orphan",
                "이 이벤트는 구글 캘린더에는 있지만 로컬 DB에는 매칭되는 일정이 "
                "없습니다.<br><br>"
                "<b>원인</b>: 과거 중복 push 버그로 구글에 사본이 두 개 생성된 뒤 "
                "하나만 로컬에서 추적되었거나, 다른 기기/웹에서 직접 만든 이벤트일 수 "
                "있습니다.<br><br>"
                "<b>조치</b>: 본인이 만든 게 맞다면 <b>구글에서 삭제</b> 버튼으로 "
                "구글 캘린더에서 제거할 수 있습니다. 다른 도구로 만든 이벤트라면 "
                "그대로 두세요.",
            )
        elif "remote_newer_than_local" in raw:
            html_content = t("gcal.guidance.remote_newer")
        elif "not_found" in raw:
            html_content = t("gcal.guidance.not_found")
        elif "forbidden" in raw or "403" in raw:
            html_content = t("gcal.guidance.forbidden")
        elif "auth" in raw or "401" in raw:
            html_content = t("gcal.guidance.auth")
        elif "rate_limit" in raw or "429" in raw:
            html_content = t("gcal.guidance.rate_limit")
        else:
            html_content = t("gcal.guidance.generic", error=str(meta.get("raw_error") or "-"))

        if not html_content.startswith("<"):
            html_content = html_content.replace("\n", "<br>")

        self.guidance_text.setHtml(f"<div style='line-height: 1.6;'>{html_content}</div>")

    def _selected_meta(self):
        current = self.table.currentRow()
        if current < 0:
            return None
        item = self.table.item(current, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def retry_selected(self):
        meta = self._selected_meta()
        if not meta:
            return

        set_footer_loading(
            self.retry_btn, True, loading_text=t("dialog.common.loading", "처리 중...")
        )
        try:
            if meta.get("type") == "task":
                task_repo.clear_unified_task_gcal_error(meta.get("id"))
            elif meta.get("type") == "conflict":
                task_repo.mark_gcal_sync_conflict_resolved(meta.get("id"), resolution="retry")
                if meta.get("local_task_id"):
                    task_repo.clear_unified_task_gcal_error(meta.get("local_task_id"))
            elif meta.get("type") == "delete_queue":
                task_repo.clear_gcal_delete_queue_error(meta.get("id"))

            if self.app and hasattr(self.app, "show_toast"):
                self.app.show_toast(
                    t("gcal.issues_retry", "동기화 재시도"),
                    t(
                        "gcal.issues_retrying_msg",
                        "수동으로 해당 항목 동기화를 다시 시도합니다. 잠시만 기다려주세요 (완료 시 알림).",
                    ),
                )

            if self.app and hasattr(self.app, "sync_google_calendar"):
                self.app.sync_google_calendar(silent=False)
            if self.app and hasattr(self.app, "update_sync_status"):
                self.app.update_sync_status()
        finally:
            set_footer_loading(self.retry_btn, False)
        self.load_rows()

    def resolve_keep_local(self):
        """[1] Mark conflict resolved by keeping local version; set gcal_dirty=1 to push it."""
        meta = self._selected_meta()
        if not meta or meta.get("type") != "conflict":
            return
        conflict_id = meta.get("id")
        local_task_id = meta.get("local_task_id")
        task_repo.mark_gcal_sync_conflict_resolved(conflict_id, resolution="keep_local")
        if local_task_id:
            task_repo.update_unified_task(local_task_id, {"gcal_dirty": 1}, mark_gcal_dirty=False)
        if self.app and hasattr(self.app, "show_toast"):
            self.app.show_toast(
                t("gcal.issues_keep_local", "로컬 유지"),
                t(
                    "gcal.issues_keep_local_done",
                    "로컬 버전을 유지합니다. 다음 동기화 시 구글에 덮어씁니다.",
                ),
            )
        if self.app and hasattr(self.app, "wake_gcal_sync"):
            self.app.wake_gcal_sync()
        self.load_rows()

    def resolve_use_remote(self):
        """[1] Apply remote (Google) snapshot to local task, mark conflict resolved."""
        meta = self._selected_meta()
        if not meta or meta.get("type") != "conflict":
            return
        conflict_id = meta.get("id")
        local_task_id = meta.get("local_task_id")
        remote_snap = self._load_snapshot_json(
            meta.get("remote_snapshot_json") or meta.get("remote_snapshot")
        )
        if local_task_id and remote_snap:
            payload = {}
            if remote_snap.get("summary"):
                payload["name"] = remote_snap["summary"]
            if remote_snap.get("start"):
                payload["deadline"] = remote_snap["start"]
            if remote_snap.get("end"):
                payload["end_date"] = remote_snap["end"]
            if "description" in remote_snap:
                payload["description"] = remote_snap["description"]
            if "location" in remote_snap:
                payload["location"] = remote_snap["location"]
            if payload:
                payload["gcal_dirty"] = 0
                task_repo.update_unified_task(local_task_id, payload, mark_gcal_dirty=False)
        task_repo.mark_gcal_sync_conflict_resolved(conflict_id, resolution="use_remote")
        if self.app and hasattr(self.app, "show_toast"):
            self.app.show_toast(
                t("gcal.issues_use_remote", "구글 버전 적용"),
                t("gcal.issues_use_remote_done", "구글 버전으로 로컬 데이터를 덮어씁니다."),
            )
        if self.app and hasattr(self.app, "_refresh_all_panels"):
            self.app._refresh_all_panels()
        self.load_rows()

    def clear_selected_error(self):
        meta = self._selected_meta()
        if not meta:
            return

        reply = QMessageBox.question(
            self,
            t("gcal.issues_clear", "오류 지우기"),
            t("gcal.issues_clear_confirm", "선택한 동기화 문제 표시를 지울까요?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if meta.get("type") == "task":
            task_repo.update_unified_task(
                meta.get("id"), {"gcal_sync_error": None}, mark_gcal_dirty=False
            )
        elif meta.get("type") == "conflict":
            task_repo.mark_gcal_sync_conflict_resolved(meta.get("id"), resolution="cleared")
        elif meta.get("type") == "delete_queue":
            task_repo.clear_gcal_delete_queue_error(meta.get("id"))
        if self.app and hasattr(self.app, "update_sync_status"):
            self.app.update_sync_status()
        self.load_rows()

    def force_ignore_selected(self):
        meta = self._selected_meta()
        if not meta:
            return

        reply = QMessageBox.warning(
            self,
            t("gcal.issues_force_ignore", "동기화 포기"),
            t(
                "gcal.issues_force_ignore_confirm",
                "이 항목의 동기화를 영구적으로 포기하고 목록에서 지우시겠습니까?\n이후 더 이상 동기화를 재시도하지 않습니다.",
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if meta.get("type") == "task":
            task_repo.update_unified_task(
                meta.get("id"), {"gcal_sync_error": None}, mark_gcal_dirty=False
            )
        elif meta.get("type") == "conflict":
            task_repo.mark_gcal_sync_conflict_resolved(meta.get("id"), resolution="ignored")
            if meta.get("local_task_id"):
                task_repo.clear_unified_task_gcal_error(meta.get("local_task_id"))
        elif meta.get("type") == "delete_queue":
            task_repo.mark_gcal_delete_done(meta.get("id"))

        if self.app and hasattr(self.app, "update_sync_status"):
            self.app.update_sync_status()
        self.load_rows()

    def _on_cell_double_clicked(self, row, col):
        meta = self._selected_meta_by_row(row)
        if not meta:
            return
        task_id = None
        if meta.get("type") == "task":
            task_id = meta.get("id")
        elif meta.get("type") == "conflict":
            task_id = meta.get("local_task_id")
        if task_id and self.app and hasattr(self.app, "open_modify_task_dialog"):
            self.app.open_modify_task_dialog(task_id)

    def _selected_meta_by_row(self, row):
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def clear_all_resolved(self):
        healed_label = t("gcal.issues_auto_healed", "시스템 자동 복구")

        reply = QMessageBox.question(
            self,
            t("gcal.issues_clear_healed", "해결된 항목 모두 지우기"),
            t(
                "gcal.issues_clear_healed_confirm",
                "이미 해결되었거나 시스템이 자동 복구한 모든 동기화 문제를 목록에서 지울까요?",
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        count = 0
        for i in range(self.table.rowCount()):
            m = self._selected_meta_by_row(i)
            if (
                m
                and (m.get("status") == healed_label or "auto_healed" in str(m.get("status", "")))
                and m.get("type") == "task"
            ):
                task_repo.update_unified_task(
                    m.get("id"), {"gcal_sync_error": None}, mark_gcal_dirty=False
                )
                count += 1

        if count > 0:
            self.load_rows()
            if self.app and hasattr(self.app, "update_sync_status"):
                self.app.update_sync_status()
