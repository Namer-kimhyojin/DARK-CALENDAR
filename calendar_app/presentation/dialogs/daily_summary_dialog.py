# -*- coding: utf-8 -*-
"""Daily summary notification dialog — shows today's schedule + due routine tasks."""

import logging

from PyQt6.QtCore import QDate, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.db import db_repository_unified as repo
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_editor_styles import build_editor_text_style
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
    get_dialog_theme_tokens,
)

logger = logging.getLogger(__name__)

_SETTINGS_KEY_LAST_SHOWN = "daily_summary_last_shown"
_SETTINGS_KEY_TIME = "daily_summary_time"
_DEFAULT_TIME = "08:00"


def _today_str() -> str:
    return QDate.currentDate().toString("yyyy-MM-dd")


class DailySummaryDialog(QDialog):
    """Shows today's schedule events and due routine tasks once per day."""

    def __init__(self, parent=None, theme_color=None):
        super().__init__(parent)
        self._theme_color = theme_color
        self._dialog_settings = getattr(parent, "settings", None)
        apply_dialog_title(self, t("dialog.daily.title", "오늘의 일정 & 마감 업무"))
        apply_common_dialog_style(
            self,
            minimum_width=480,
            size=(540, 440),
            theme_color=theme_color,
        )
        self._ui_tokens = get_dialog_theme_tokens(
            theme_color=self._theme_color,
            settings=self._dialog_settings,
        )
        self._build_ui()

    def _build_ui(self):
        tokens = self._ui_tokens
        text_primary = tokens.get("text_primary", "#f4f7fb")
        text_secondary = tokens.get("text_secondary", "#c8ccd4")
        text_muted = tokens.get("text_muted", "#9aa0ad")
        border_soft = tokens.get("border_soft", "rgba(255,255,255,0.12)")
        item_bg = tokens.get("surface_item", "#111116")
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(0)

        self.summary_scroll = QScrollArea()
        self.summary_scroll.setObjectName("dailySummaryContent")
        self.summary_scroll.setWidgetResizable(True)
        self.summary_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.summary_scroll.setAccessibleName(t("dialog.daily.title", "오늘의 일정 & 마감 업무"))
        self.summary_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 10px; margin: 4px 0; }"
        )
        content = QWidget()
        content.setObjectName("dailySummaryScrollContent")
        content.setStyleSheet("QWidget#dailySummaryScrollContent { background: transparent; }")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 4, 0)
        content_layout.setSpacing(10)
        self.summary_scroll.setWidget(content)
        root.addWidget(self.summary_scroll, 1)

        today = _today_str()
        today_label = QLabel(t("dialog.daily.date_header", "오늘") + f"  {today}")
        today_label.setStyleSheet(
            build_editor_text_style(
                tokens,
                color=text_primary,
                font_px=16,
                weight=700,
                padding="0 0 4px 0",
            )
        )
        content_layout.addWidget(today_label)

        # ── 오늘의 일정 섹션 ───────────────────────────────────────────────
        sched_header = QLabel(t("dialog.daily.schedule_section", "📅 오늘의 일정"))
        sched_header.setStyleSheet(
            build_editor_text_style(tokens, tone="accent", font_px=13, weight=700, margin_top=4)
        )
        content_layout.addWidget(sched_header)

        sched_items = self._load_schedule(today)
        task_items_preview = self._load_due_routines(today)
        self.has_content = bool(sched_items) or bool(task_items_preview)

        if sched_items:
            for item in sched_items:
                lbl = QLabel(item)
                lbl.setWordWrap(True)
                lbl.setStyleSheet(
                    build_editor_text_style(
                        tokens,
                        color=text_secondary,
                        font_px=13,
                        weight=500,
                        padding="3px 0 3px 8px",
                    )
                )
                content_layout.addWidget(lbl)
        else:
            empty = QLabel(t("dialog.daily.no_schedule", "  오늘 예정된 일정이 없습니다."))
            empty.setStyleSheet(
                build_editor_text_style(
                    tokens,
                    color=text_muted,
                    font_px=13,
                    padding="3px 0 3px 8px",
                )
            )
            content_layout.addWidget(empty)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet(f"background-color: {border_soft}; max-height: 1px;")
        content_layout.addWidget(sep1)

        # ── 마감 업무 섹션 ─────────────────────────────────────────────────
        task_header = QLabel(t("dialog.daily.routine_section", "📋 오늘 마감 업무"))
        task_header.setStyleSheet(
            build_editor_text_style(tokens, tone="accent", font_px=13, weight=700)
        )
        content_layout.addWidget(task_header)

        task_items = task_items_preview
        if task_items:
            for name, pct_text, tags_text in task_items:
                row = QHBoxLayout()
                row.setSpacing(6)
                txt = f"• {name}"
                if pct_text:
                    txt += f"  {pct_text}"
                item_lbl = QLabel(txt)
                item_lbl.setWordWrap(True)
                item_lbl.setStyleSheet(
                    build_editor_text_style(
                        tokens,
                        color=text_secondary,
                        font_px=13,
                        weight=500,
                        padding="3px 0 3px 8px",
                    )
                )
                row.addWidget(item_lbl, 1)
                if tags_text:
                    tag_lbl = QLabel(tags_text)
                    tag_lbl.setStyleSheet(
                        f"font-size:11px; color:{text_muted}; padding:2px 6px;"
                        f" background:{item_bg}; border:1px solid {border_soft};"
                        " border-radius:6px;"
                    )
                    tag_lbl.setWordWrap(True)
                    tag_lbl.setMaximumWidth(150)
                    tag_lbl.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
                    row.addWidget(tag_lbl)
                content_layout.addLayout(row)
        else:
            empty2 = QLabel(t("dialog.daily.no_routines", "  오늘 마감인 업무가 없습니다."))
            empty2.setStyleSheet(
                build_editor_text_style(
                    tokens,
                    color=text_muted,
                    font_px=13,
                    padding="3px 0 3px 8px",
                )
            )
            content_layout.addWidget(empty2)

        footer, ok_btn, _ = build_dialog_footer(
            ok_label=t("btn.confirm", "확인"),
            cancel_label=None,
        )
        ok_btn.clicked.connect(self.accept)
        root.addLayout(footer)
        self.ok_btn = ok_btn

    def _load_schedule(self, today: str) -> list:
        try:
            rows = repo.get_schedule_tasks_overlapping_range_with_progress(today, today)
        except Exception:
            logger.exception("DailySummary: failed to load schedule")
            return []
        items = []
        for row in rows:
            name = row.get("name", "")
            deadline = str(row.get("deadline") or "")
            time_part = deadline[11:16] if len(deadline) > 10 else ""
            end = str(row.get("end_date") or "")
            end_time = end[11:16] if len(end) > 10 else ""
            is_all_day = bool(row.get("all_day"))
            if is_all_day:
                items.append(f"• {name}  [종일]")
            elif time_part:
                suffix = f" ~ {end_time}" if end_time else ""
                items.append(f"• {name}  {time_part}{suffix}")
            else:
                items.append(f"• {name}")
        return items

    def _load_due_routines(self, today: str) -> list:
        try:
            rows = repo.get_tasks_by_type_with_progress("routine")
        except Exception:
            logger.exception("DailySummary: failed to load routines")
            return []
        result = []
        for row in rows:
            status = str(row.get("status") or "").lower()
            if status in ("done", "completed") or row.get("is_completed"):
                continue
            target = str(row.get("target_date") or "")[:10]
            deadline = str(row.get("deadline") or "")[:10]
            due = target or deadline
            if due and due > today:
                continue
            prog = row.get("progress") or {}
            total = prog.get("total") or row.get("checklist_total", 0) or 0
            comp = prog.get("completed") or row.get("checklist_completed", 0) or 0
            pct_text = f"({comp}/{total})" if total > 0 else ""
            tags_raw = row.get("tags") or ""
            tag_list = [tg.strip() for tg in tags_raw.split(",") if tg.strip()]
            tags_text = " · ".join(tag_list) if tag_list else ""
            result.append((row.get("name", ""), pct_text, tags_text))
        return result


# ── Public API ────────────────────────────────────────────────────────────────


def maybe_show_daily_summary(app) -> None:
    """Show summary if not yet shown today. Called on startup and by daily timer."""
    settings = getattr(app, "settings", None)
    if settings is None:
        return

    today = _today_str()
    last_shown = settings.value(_SETTINGS_KEY_LAST_SHOWN, "")
    if last_shown == today:
        return

    settings.setValue(_SETTINGS_KEY_LAST_SHOWN, today)
    try:
        dlg = DailySummaryDialog(parent=app)
        if not dlg.has_content:
            dlg.deleteLater()
            return
        dlg.exec()
    except Exception:
        logger.exception("DailySummary: dialog failed")


def schedule_daily_summary_timer(app) -> QTimer | None:
    """Set up a QTimer to fire at the configured time each day."""
    from PyQt6.QtCore import QTime as _QTime

    settings = getattr(app, "settings", None)
    if settings is None:
        return None

    time_str = settings.value(_SETTINGS_KEY_TIME, _DEFAULT_TIME)
    try:
        hh, mm = [int(x) for x in time_str.split(":")]
    except Exception:
        hh, mm = 8, 0

    timer = QTimer(app)
    timer.setSingleShot(False)

    def _fire():
        now = _QTime.currentTime()
        target = _QTime(hh, mm)
        if abs(now.secsTo(target)) <= 65:
            maybe_show_daily_summary(app)

    timer.timeout.connect(_fire)
    timer.start(60_000)
    return timer
