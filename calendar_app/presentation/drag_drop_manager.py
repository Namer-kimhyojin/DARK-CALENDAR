"""Task drag/drop compatibility helpers."""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, QDataStream, QIODevice, QMimeData, QPoint, QRect, Qt
from PyQt6.QtGui import QBrush, QColor, QDrag, QFont, QPainter, QPixmap

from calendar_app.infrastructure import task_drop_service
from calendar_app.infrastructure.db import task_repo


def _safe_task_ids(widget, task_id):
    app = widget.window() if widget is not None else None
    selected = list(getattr(app, "selected_task_ids", []) or [])
    if task_id not in selected:
        selected = [task_id]
    return [int(tid) for tid in selected]


def _write_int_list(task_ids):
    data = QByteArray()
    stream = QDataStream(data, QIODevice.OpenModeFlag.WriteOnly)
    stream.writeInt32(len(task_ids))
    for tid in task_ids:
        stream.writeInt32(int(tid))
    return data


def _span_days_for_task(task):
    try:
        st = (task or {}).get("deadline")
        et = (task or {}).get("end_date")
        if not st or not et:
            return 1
        from datetime import datetime

        d1 = datetime.fromisoformat(str(st).replace(" ", "T")).date()
        d2 = datetime.fromisoformat(str(et).replace(" ", "T")).date()
        return max(1, (d2 - d1).days + 1)
    except Exception:
        return 1


def start_task_drag(widget, _event, task_id):
    task_ids = _safe_task_ids(widget, task_id)

    mime = QMimeData()
    mime.setData("application/x-task-item", _write_int_list(task_ids))

    # Used by calendar cells for range preview while dragging.
    span_data = QByteArray()
    span_stream = QDataStream(span_data, QIODevice.OpenModeFlag.WriteOnly)
    span = _span_days_for_task(task_repo.get_unified_task(task_ids[0])) if task_ids else 1
    span_stream.writeInt32(int(span))
    mime.setData("application/x-task-span-days", span_data)

    app = widget.window() if widget is not None else None
    if app is not None:
        app._is_dragging = True

    drag = QDrag(widget)
    drag.setMimeData(mime)

    # ---- 드래그 픽맵: 심플 카드 스타일 ----
    try:
        from calendar_app.infrastructure.i18n import t
        from calendar_app.shared.icon_map import ICON
        from calendar_app.shared.icon_map import icon as _ic
        from calendar_app.shared.ui_tokens import get_ui_tokens

        tokens = get_ui_tokens()

        count = len(task_ids)

        # 힌트 텍스트
        hint_text = t("drag.hint_copy", "Ctrl: 복사  /  기본: 이동")

        # 크기: 숫자 배지를 크게 표시하기 위해 높이 확보
        width, height = 200, 72

        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 배경: 반투명 어두운 카드
        bg = QColor(tokens.get("bg_alt", "#1e2230"))
        bg.setAlpha(230)
        accent = QColor(tokens.get("accent", "#4da6ff"))
        accent.setAlpha(220)

        painter.setBrush(QBrush(bg))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRect(0, 0, width, height), 10, 10)

        # 왼쪽 액센트 바 (4px)
        painter.setBrush(QBrush(accent))
        painter.drawRoundedRect(QRect(0, 0, 4, height), 2, 2)

        # 아이콘 (28×28px)
        icon_rect = QRect(12, 10, 28, 28)
        _ic(ICON.CALENDAR, color=accent.name()).paint(painter, icon_rect)

        # 숫자 배지: 크고 굵게
        count_color = QColor(tokens.get("text_primary", "#f0f4ff"))
        count_font = QFont("Malgun Gothic", 22, QFont.Weight.ExtraBold)
        painter.setFont(count_font)
        painter.setPen(count_color)
        painter.drawText(
            QRect(46, 4, width - 54, 44),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            str(count),
        )

        # "개 일정" 레이블 (숫자 옆에 작게)
        label_color = QColor(tokens.get("text_secondary", "#8899aa"))
        label_font = QFont("Malgun Gothic", 11)
        painter.setFont(label_font)
        painter.setPen(label_color)
        painter.setFont(QFont("Malgun Gothic", 22, QFont.Weight.ExtraBold))
        num_width = painter.fontMetrics().horizontalAdvance(str(count))
        painter.setFont(label_font)
        label_x = 46 + num_width + 4
        painter.drawText(
            QRect(label_x, 18, width - label_x - 6, 24),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "개 일정",
        )

        # 힌트
        hint_color = QColor(tokens.get("text_secondary", "#8899aa"))
        hint_font = QFont("Malgun Gothic", 8)
        painter.setFont(hint_font)
        painter.setPen(hint_color)
        painter.drawText(
            QRect(12, 50, width - 18, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            hint_text,
        )

        painter.end()
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(14, height // 2))
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(f"Failed to create drag pixmap: {e}")

    action = drag.exec(
        Qt.DropAction.CopyAction | Qt.DropAction.MoveAction, Qt.DropAction.MoveAction
    )

    if app is not None:
        app._is_dragging = False

    return action


def handle_task_drop(app, task_id_list, target_date, target_time, action):
    return task_drop_service.handle_task_drop(app, task_id_list, target_date, target_time, action)
