"""Daily summary notification dialog — shows today's schedule + due routine tasks."""

import logging

from PyQt6.QtCore import QDate, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from calendar_app.infrastructure.db import db_repository_unified as repo
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import apply_common_dialog_style

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
        apply_dialog_title(self, t("dialog.daily.title", "오늘의 일정 & 마감 업무"))
        apply_common_dialog_style(self, minimum_width=480, theme_color=theme_color)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(10)

        today = _today_str()
        today_label = QLabel(t("dialog.daily.date_header", "오늘") + f"  {today}")
        today_label.setStyleSheet("font-size:14px; font-weight:700;")
        root.addWidget(today_label)

        # ── 오늘의 일정 섹션 ───────────────────────────────────────────────
        sched_header = QLabel(t("dialog.daily.schedule_section", "📅 오늘의 일정"))
        sched_header.setStyleSheet("font-size:13px; font-weight:700; margin-top:4px;")
        root.addWidget(sched_header)

        sched_items = self._load_schedule(today)
        if sched_items:
            for item in sched_items:
                lbl = QLabel(item)
                lbl.setWordWrap(True)
                lbl.setStyleSheet("padding-left:8px; font-size:12px;")
                root.addWidget(lbl)
        else:
            empty = QLabel(t("dialog.daily.no_schedule", "  오늘 예정된 일정이 없습니다."))
            empty.setStyleSheet("padding-left:8px; font-size:12px; color:#888;")
            root.addWidget(empty)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep1)

        # ── 마감 업무 섹션 ─────────────────────────────────────────────────
        task_header = QLabel(t("dialog.daily.routine_section", "📋 오늘 마감 업무"))
        task_header.setStyleSheet("font-size:13px; font-weight:700;")
        root.addWidget(task_header)

        task_items = self._load_due_routines(today)
        if task_items:
            for name, pct_text, tags_text in task_items:
                row = QHBoxLayout()
                row.setSpacing(6)
                txt = f"• {name}"
                if pct_text:
                    txt += f"  {pct_text}"
                item_lbl = QLabel(txt)
                item_lbl.setWordWrap(True)
                item_lbl.setStyleSheet("padding-left:8px; font-size:12px;")
                row.addWidget(item_lbl, 1)
                if tags_text:
                    tag_lbl = QLabel(tags_text)
                    tag_lbl.setStyleSheet(
                        "font-size:11px; color:#888; padding:1px 5px;"
                        " border:1px solid #444; border-radius:4px;"
                    )
                    tag_lbl.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
                    row.addWidget(tag_lbl)
                root.addLayout(row)
        else:
            empty2 = QLabel(t("dialog.daily.no_routines", "  오늘 마감인 업무가 없습니다."))
            empty2.setStyleSheet("padding-left:8px; font-size:12px; color:#888;")
            root.addWidget(empty2)

        root.addStretch()

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep2)

        # ── 푸터 ───────────────────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer.addStretch()

        ok_btn = QPushButton(t("btn.confirm", "확인"))
        ok_btn.setObjectName("primary_btn")
        ok_btn.setFixedHeight(34)
        ok_btn.setMinimumWidth(90)
        ok_btn.clicked.connect(self.accept)
        footer.addWidget(ok_btn)

        root.addLayout(footer)
        self.resize(480, 360)

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
