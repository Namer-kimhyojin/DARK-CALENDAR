from __future__ import annotations

from collections import OrderedDict
import contextlib

from PyQt6.QtCore import QDate, QPoint, QSize, Qt, QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QMenu, QWidget

from calendar_app.infrastructure.db import directive_repo, search_repo
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.panel_widget_common import (  # noqa: F401
    _REF_SCREEN_WIDTH,
    _SCHEDULE_WIDGET_HEIGHT_REF,
    _WIDGET_PANEL_WIDTH_REF,
    _format_compact_date,
    _format_compact_date_with_weekday,
    _format_widget_datetime_label,
    _normalize_status,
    _parse_qdate,
    _parse_qdatetime,
    _parse_quick_add_text,
    _priority_rank,
    _safe_text,
    _top_level_widget,
    _WidgetEntry,
)
from calendar_app.presentation.widgets.panel_widget_shell import (  # noqa: F401
    _FloatingWidgetBase,
    _WidgetModeLauncher,
)
from calendar_app.presentation.widgets.panel_widget_theme import (  # noqa: F401
    _apply_panel_theme_override,
    _apply_widget_color_override,
    _build_widget_mode_theme_tokens,
    _read_widget_color_mode_from_settings,
    _resolve_widget_mode_tokens,
)
from calendar_app.presentation.widgets.panel_widget_views import (  # noqa: F401
    _EntryListWidget,
    _PanelWidget,
    _QuickAddInput,
)
from calendar_app.shared.background_worker import DbTaskWorker


def _build_date_section_title(date: QDate) -> str:
    """선택된 날짜를 '4월 6일 일  오늘' 형태로 반환."""
    if not date.isValid():
        return t("widget_mode.schedule_title", "일정")
    from PyQt6.QtCore import QLocale as _QL

    _loc = _QL()
    month = date.month()
    day = date.day()
    weekday = _loc.standaloneDayName(date.dayOfWeek(), _QL.FormatType.ShortFormat) or ""
    base = f"{month}{t('common.month', '월')} {day}{t('common.day', '일')} {weekday}".strip()
    today = QDate.currentDate()
    delta = today.daysTo(date)
    if delta == 0:
        rel = t("common.today", "오늘")
    elif delta == 1:
        rel = t("common.tomorrow", "내일")
    elif delta == -1:
        rel = t("common.yesterday", "어제")
    else:
        rel = ""
    return f"{base}  {rel}".rstrip() if rel else base


class PanelWidgetModeController:
    """통합 패널 위젯(_PanelWidget)을 관리하는 컨트롤러."""

    def __init__(self, app: QWidget):
        self._app = app
        self._panel: _PanelWidget | None = None
        self._widget_mode_active = False
        self._settings = app.settings
        self._last_palette_signature: tuple | None = None
        self._last_render_signature: tuple | None = None
        self._render_state_cache: OrderedDict[
            tuple, tuple[dict[QDate, int], list[_WidgetEntry]]
        ] = OrderedDict()
        self._is_refreshing = False
        self._refresh_worker = None
        self._cached_result: object | None = None
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(24)
        self._debounce_timer.timeout.connect(self._render_from_main_cache)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_panel(self) -> _PanelWidget:
        if self._panel is None:
            panel = _PanelWidget(self._app)
            panel.on_date_changed = self._handle_panel_date_changed
            panel.on_month_changed = self._handle_panel_month_changed
            panel.on_add_schedule_with_text_requested = self._open_schedule_create_with_text
            panel.on_realign_requested = lambda: QTimer.singleShot(0, self._position_panel)
            panel.on_scale_changed = lambda _s: QTimer.singleShot(0, self._position_panel)
            panel.screen_changed.connect(lambda: self._on_panel_screen_changed())
            panel.set_restore_callback(self.exit_widget_mode)
            self._panel = panel
            self._maybe_apply_panel_palette(self._panel, force=True)  # 최초 1회만
        return self._panel

    def _current_date(self) -> QDate:
        current = getattr(self._app, "current_date", None)
        if isinstance(current, QDate) and current.isValid():
            return current
        return QDate.currentDate()

    def _panel_context_date(self, panel: _PanelWidget | None = None) -> QDate:
        ref = panel or self._panel
        if ref is not None:
            selected = ref.selected_date()
            if isinstance(selected, QDate) and selected.isValid():
                return selected
            month_start, _month_end = ref.visible_month_bounds()
            if month_start.isValid():
                return month_start
        return self._current_date()

    def _sync_main_context_date(self, target: QDate) -> None:
        if isinstance(target, QDate) and target.isValid():
            self._app.current_date = target

    def _cache_bounds(self, cache: dict[str, object] | None) -> tuple[QDate, QDate]:
        if not isinstance(cache, dict):
            return QDate(), QDate()
        return _parse_qdate(cache.get("range_start")), _parse_qdate(cache.get("range_end"))

    def _calendar_cache(self) -> dict[str, object]:
        cache = getattr(self._app, "_latest_calendar_range_data", None)
        return cache if isinstance(cache, dict) else {}

    def _agenda_cache(self) -> dict[str, object]:
        cache = getattr(self._app, "_latest_agenda_data", None)
        return cache if isinstance(cache, dict) else {}

    def _directive_cache(self) -> dict[str, object]:
        cache = getattr(self._app, "_latest_directive_data", None)
        return cache if isinstance(cache, dict) else {}

    def _calendar_cache_covers_range(self, start: QDate, end: QDate) -> bool:
        if not start.isValid() or not end.isValid():
            return False
        cache_start, cache_end = self._cache_bounds(self._calendar_cache())
        return (
            cache_start.isValid()
            and cache_end.isValid()
            and cache_start <= start
            and cache_end >= end
        )

    def _calendar_cache_covers_date(self, target: QDate) -> bool:
        return self._calendar_cache_covers_range(target, target)

    def _directive_cache_matches_date(self, target: QDate) -> bool:
        cache = self._directive_cache()
        if not cache:
            return False
        context_date = _parse_qdate(cache.get("context_date"))
        if not context_date.isValid():
            return True
        return context_date == target

    def _invalidate_render_cache(self) -> None:
        self._last_render_signature = None
        self._render_state_cache.clear()
        if self._panel is not None:
            self._panel._last_calendar_state_key = None
            self._panel._last_entry_render_key = None

    def _cache_signature(self, cache: dict[str, object] | None, *row_keys: str) -> tuple:
        if not isinstance(cache, dict) or not cache:
            return (None,)
        parts: list[object] = [
            id(cache),
            cache.get("range_start"),
            cache.get("range_end"),
            cache.get("context_date"),
        ]
        for key in row_keys:
            rows = cache.get(key)
            if rows is None:
                rows = ()
            try:
                count = len(rows)
            except Exception:
                count = 0
            parts.extend((key, id(rows), count))
        return tuple(parts)

    def _style_signature(self, panel: _PanelWidget) -> tuple:
        tokens = panel.theme_tokens()
        return (
            int(round(panel._last_scale * 100)),
            tokens.get("accent"),
            tokens.get("panel_bg"),
            tokens.get("section_bg"),
            tokens.get("section_bg_alt"),
            tokens.get("hero_border"),
            tokens.get("text_primary"),
            tokens.get("text_secondary"),
        )

    def _palette_signature(self, panel: _PanelWidget, scale: float | None = None) -> tuple:
        resolved_scale = float(scale if scale is not None else self._ui_scale_factor(panel))
        return (
            int(round(resolved_scale * 1000)),
            panel._read_panel_theme(),
            panel._read_widget_color_mode(),
            panel._get_individual_opacity(),
            str(self._settings.value("theme_color", "#4da6ff") or "#4da6ff"),
            str(self._settings.value("ui_shape_preset", "sharp") or "sharp"),
            str(self._settings.value("dialog_token.accent", "") or ""),
        )

    def _maybe_apply_panel_palette(
        self,
        panel: _PanelWidget | None,
        *,
        scale: float | None = None,
        force: bool = False,
    ) -> None:
        if panel is None:
            return
        resolved_scale = float(scale if scale is not None else self._ui_scale_factor(panel))
        signature = self._palette_signature(panel, resolved_scale)
        if not force and signature == self._last_palette_signature:
            return
        panel.apply_palette(resolved_scale)
        self._last_palette_signature = signature

    def _data_signature(
        self, today: QDate, selected: QDate, month_start: QDate, month_end: QDate
    ) -> tuple:
        return (
            today.toString("yyyy-MM-dd") if today.isValid() else "",
            selected.toString("yyyy-MM-dd") if selected.isValid() else "",
            month_start.toString("yyyy-MM-dd") if month_start.isValid() else "",
            month_end.toString("yyyy-MM-dd") if month_end.isValid() else "",
            self._cache_signature(self._calendar_cache(), "rows"),
            self._cache_signature(self._agenda_cache(), "rows"),
            self._cache_signature(self._directive_cache(), "routine_rows", "directive_rows"),
        )

    def _get_cached_render_state(
        self, signature: tuple
    ) -> tuple[dict[QDate, int], list[_WidgetEntry]] | None:
        cached = self._render_state_cache.get(signature)
        if cached is None:
            return None
        self._render_state_cache.move_to_end(signature)
        marked, entries = cached
        return dict(marked), list(entries)

    def _remember_render_state(
        self,
        signature: tuple,
        marked: dict[QDate, int],
        entries: list[_WidgetEntry],
    ) -> None:
        self._render_state_cache[signature] = (dict(marked), list(entries))
        self._render_state_cache.move_to_end(signature)
        while len(self._render_state_cache) > 21:
            self._render_state_cache.popitem(last=False)

    def _request_main_cache_refresh(
        self, *, schedule: bool, work: bool, target_date: QDate | None = None
    ) -> None:
        if isinstance(target_date, QDate) and target_date.isValid():
            self._sync_main_context_date(target_date)
        if not schedule and not work:
            return
        if hasattr(self._app, "schedule_panel_refresh"):
            self._app.schedule_panel_refresh(center=bool(schedule), right=bool(work))

    def _ensure_main_cache_coverage(
        self, target_date: QDate, month_start: QDate, month_end: QDate
    ) -> None:
        self._request_main_cache_refresh(
            schedule=not self._calendar_cache_covers_range(month_start, month_end),
            work=not self._directive_cache_matches_date(target_date),
            target_date=target_date,
        )

    def _ui_scale_factor(self, widget: QWidget | None = None) -> float:
        geom = self._screen_available_geometry(widget)
        width = max(1024, geom.width())
        return max(0.75, min(width / _REF_SCREEN_WIDTH, 2.0))

    def _screen_available_geometry(self, widget: QWidget | None = None):
        if widget is not None:
            probe_center = (
                widget.frameGeometry().center()
                if widget.isVisible()
                else widget.geometry().center()
            )
            screen = QGuiApplication.screenAt(probe_center)
            if screen:
                return screen.availableGeometry()
            screen = widget.screen()
            if screen:
                return screen.availableGeometry()
            screen = QGuiApplication.screenAt(widget.geometry().center())
            if screen:
                return screen.availableGeometry()
        root = _top_level_widget(self._app)
        center = root.frameGeometry().center() if root is not None else QPoint(0, 0)
        screen = QGuiApplication.screenAt(center)
        if screen is None and root is not None:
            screen = root.screen()
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        return screen.availableGeometry() if screen is not None else root.geometry()

    @staticmethod
    def _clamp_pos(pos: QPoint, width: int, height: int, geom, margin: int) -> QPoint:
        x = max(geom.left() + margin, min(pos.x(), geom.right() - width - margin + 1))
        y = max(geom.top() + margin, min(pos.y(), geom.bottom() - height - margin + 1))
        return QPoint(x, y)

    def _position_panel(self, force_reset: bool = False) -> None:
        panel = self._panel
        if panel is None or not panel.isVisible():
            return
        s = self._ui_scale_factor(panel)
        geom = self._screen_available_geometry(panel)

        width_mul, height_mul = panel._size_preset_multipliers()
        width = int(round(_WIDGET_PANEL_WIDTH_REF * s * width_mul))
        height = int(round(_SCHEDULE_WIDGET_HEIGHT_REF * s * height_mul))

        use_current = (
            not force_reset
            and not bool(getattr(panel, "_size_preset_dirty", False))
            and panel.width() > 20
            and panel.height() > 20
        )
        stored_size = self._settings.value(panel.size_setting_key())
        stored_qsize = stored_size if isinstance(stored_size, QSize) else None
        if use_current:
            width, height = panel.width(), panel.height()
        elif stored_qsize is not None and stored_qsize.width() > 20 and stored_qsize.height() > 20:
            width, height = stored_qsize.width(), stored_qsize.height()
        panel._size_preset_dirty = False

        width = max(panel.minimumSizeHint().width(), width)
        height = max(panel.minimumSizeHint().height(), height)
        width = min(width, int(geom.width() * 0.72))
        height = min(height, int(geom.height() * 0.90))

        if panel.width() != width or panel.height() != height:
            panel.resize(width, height)
        self._maybe_apply_panel_palette(panel, scale=s)
        width = panel.width()
        height = panel.height()
        self._apply_always_on_top_to_widget(panel)

        margin_right = int(24 * s)
        default_pos = QPoint(
            geom.right() - width - margin_right + 1,
            geom.top() + int(32 * s),
        )
        stored = self._settings.value(panel.position_setting_key())
        stored_pos = stored if isinstance(stored, QPoint) else None
        current_pos = panel.pos()
        use_pos = not force_reset and current_pos.x() > 0 and current_pos.y() > 0
        target = current_pos if use_pos else stored_pos or default_pos
        clamped_pos = self._clamp_pos(target, width, height, geom, max(8, margin_right // 2))
        if current_pos != clamped_pos:
            panel.move(clamped_pos)

    def _on_panel_screen_changed(self) -> None:
        QTimer.singleShot(50, self._position_panel)

    def _show_main_window(self) -> None:
        self._app.show()
        self._app.is_visible = True
        if self._app.isMinimized():
            self._app.showNormal()
        self._app.raise_()
        self._app.activateWindow()
        if hasattr(self._app, "_refresh_all_panels"):
            self._app._refresh_all_panels()

    def _hide_main_window(self) -> None:
        self._app.hide()
        self._app.is_visible = False

    # ------------------------------------------------------------------
    # Action helpers (dialogs, completion, menus)
    # ------------------------------------------------------------------

    def _open_task(self, task_id: int) -> None:
        if task_id > 0 and hasattr(self._app, "open_modify_task_dialog"):
            self._app.open_modify_task_dialog(task_id)

    def _open_directive(self, directive_id: int) -> None:
        if directive_id > 0 and hasattr(self._app, "open_directive_dialog"):
            self._app.open_directive_dialog(directive_id)

    def _refresh_panel_later(self) -> None:
        self._refresh_panel()

    def _cached_row_date_range(
        self,
        row: dict[str, object],
        *,
        start_keys: tuple[str, ...],
        end_keys: tuple[str, ...],
    ) -> tuple[QDate, QDate]:
        start_qd = QDate()
        end_qd = QDate()
        for key in start_keys:
            start_qd = _parse_qdate(row.get(key))
            if start_qd.isValid():
                break
        for key in end_keys:
            end_qd = _parse_qdate(row.get(key))
            if end_qd.isValid():
                break
        if not start_qd.isValid() and end_qd.isValid():
            start_qd = end_qd
        if not end_qd.isValid() and start_qd.isValid():
            end_qd = start_qd
        if start_qd.isValid() and end_qd.isValid() and end_qd < start_qd:
            end_qd = start_qd
        return start_qd, end_qd

    def _cached_rows_for_date(self, target: QDate) -> list[dict[str, object]]:
        if self._calendar_cache_covers_date(target):
            rows = self._calendar_cache().get("rows") or []
        else:
            rows = self._agenda_cache().get("rows") or []
        return [row for row in rows if isinstance(row, dict)]

    def _cached_rows_for_month(
        self, month_start: QDate, month_end: QDate
    ) -> list[dict[str, object]]:
        if self._calendar_cache_covers_range(month_start, month_end):
            rows = self._calendar_cache().get("rows") or []
        else:
            rows = self._agenda_cache().get("rows") or []
        return [row for row in rows if isinstance(row, dict)]

    def _cached_schedule_entries_for_date(
        self,
        target: QDate,
        rows: list[dict[str, object]],
    ) -> list[_WidgetEntry]:
        if not target.isValid():
            return []

        def _overlaps_target(row: dict[str, object]) -> bool:
            start_qd, end_qd = self._cached_row_date_range(
                row,
                start_keys=("deadline", "target_date"),
                end_keys=("end_date", "end_time", "deadline", "target_date"),
            )
            return start_qd.isValid() and start_qd <= target <= end_qd

        rows = sorted(
            [row for row in rows if _overlaps_target(row)],
            key=lambda row: (
                _safe_text(row.get("deadline")) or "9999-99-99 99:99",
                int(row.get("id") or 0),
            ),
        )

        entries: list[_WidgetEntry] = []
        for row in rows[:18]:
            task_id = int(row.get("id") or 0)
            if task_id <= 0:
                continue
            title = _safe_text(row.get("name")) or t("widget_mode.untitled", "(제목 없음)")
            due_text = _format_widget_datetime_label(row.get("deadline"), reference_date=target)
            entries.append(
                _WidgetEntry(
                    title=title,
                    subtitle=due_text,
                    callback=lambda tid=task_id: self._open_task(tid),
                    delete_callback=lambda tid=task_id: self._delete_task_from_widget(tid),
                    context_menu_callback=lambda anchor, pos, tid=task_id: (
                        self._show_task_entry_menu(anchor, pos, tid)
                    ),
                )
            )
        return entries

    def _cached_month_marked_dates(
        self,
        month_start: QDate,
        month_end: QDate,
        rows: list[dict[str, object]],
    ) -> dict[QDate, int]:
        if not month_start.isValid() or not month_end.isValid():
            return {}

        marked: dict[QDate, int] = {}
        for row in rows:
            start_qd, end_qd = self._cached_row_date_range(
                row,
                start_keys=("deadline", "target_date"),
                end_keys=("end_date", "end_time", "deadline", "target_date"),
            )
            if not start_qd.isValid():
                continue
            cursor = start_qd if start_qd >= month_start else month_start
            last = end_qd if end_qd <= month_end else month_end
            while cursor.isValid() and cursor <= last:
                marked[cursor] = marked.get(cursor, 0) + 1
                cursor = cursor.addDays(1)
        return marked

    def _cached_work_entries_for_date(
        self,
        target: QDate,
        cache: dict[str, object],
    ) -> list[_WidgetEntry]:
        if not target.isValid() or not cache:
            return []

        entries: list[_WidgetEntry] = []
        routine_rows = sorted(
            [row for row in (cache.get("routine_rows") or []) if isinstance(row, dict)],
            key=lambda row: (
                _safe_text(row.get("target_date") or row.get("period_end") or row.get("deadline")),
                _priority_rank(row.get("priority")),
                int(row.get("id") or 0),
            ),
        )

        routine_entries: list[_WidgetEntry] = []
        for row in routine_rows:
            status = _normalize_status(row.get("status"))
            due_qd = _parse_qdate(
                row.get("period_end") or row.get("deadline") or row.get("target_date")
            )
            target_qd = _parse_qdate(row.get("target_date"))
            matches_target = (due_qd.isValid() and due_qd == target) or (
                target_qd.isValid() and target_qd == target
            )
            if not matches_target:
                continue
            if status in {"done", "completed"} or row.get("is_completed") in (1, True):
                continue
            rid = int(row.get("id") or 0)
            if rid <= 0:
                continue
            title = _safe_text(row.get("name")) or t("widget_mode.untitled", "(제목 없음)")
            subtitle = _format_compact_date(due_qd) if due_qd.isValid() and due_qd != target else ""
            routine_entries.append(
                _WidgetEntry(
                    title=title,
                    subtitle=subtitle,
                    callback=lambda tid=rid: self._open_task(tid),
                    delete_callback=lambda tid=rid: self._delete_task_from_widget(tid),
                    context_menu_callback=lambda anchor, pos, tid=rid: self._show_task_entry_menu(
                        anchor, pos, tid
                    ),
                )
            )
            if len(routine_entries) >= 10:
                break

        done_statuses = {"done", "completed", "deferred", "canceled", "cancelled"}
        directive_entries: list[_WidgetEntry] = []
        for row in cache.get("directive_rows") or []:
            if not isinstance(row, (tuple, list)) or len(row) < 5:
                continue
            did, content, status, _receiver, deadline = row[:5]
            status_norm = _normalize_status(status)
            deadline_qd = _parse_qdate(deadline)
            if not deadline_qd.isValid() or deadline_qd != target:
                continue
            if status_norm in done_statuses:
                continue
            did_int = int(did or 0)
            if did_int <= 0:
                continue
            title = _safe_text(content) or t("widget_mode.untitled", "(제목 없음)")
            directive_entries.append(
                _WidgetEntry(
                    title=title,
                    subtitle="",
                    callback=lambda x=did_int: self._open_directive(x),
                    delete_callback=lambda x=did_int: self._delete_directive_from_widget(x),
                    context_menu_callback=lambda anchor, pos, did=did_int: (
                        self._show_directive_entry_menu(anchor, pos, did)
                    ),
                )
            )
            if len(directive_entries) >= 10:
                break

        if routine_entries:
            entries.append(
                _WidgetEntry(title=t("widget_mode.section_routine_today", "업무"), is_section=True)
            )
            entries.extend(routine_entries)
        if directive_entries:
            entries.append(
                _WidgetEntry(
                    title=t("widget_mode.section_directive_today", "지시/협조"), is_section=True
                )
            )
            entries.extend(directive_entries)
        return entries

    def _handle_panel_date_changed(self) -> None:
        panel = self._panel
        if panel is None:
            return
        selected = self._panel_context_date(panel)
        month_start, month_end = panel.visible_month_bounds()
        self._sync_main_context_date(selected)
        self._request_main_cache_refresh(
            schedule=not self._calendar_cache_covers_range(month_start, month_end),
            work=not self._directive_cache_matches_date(selected),
            target_date=selected,
        )
        self._refresh_panel()

    def _handle_panel_month_changed(self) -> None:
        panel = self._panel
        if panel is None:
            return
        selected = self._panel_context_date(panel)
        month_start, month_end = panel.visible_month_bounds()
        self._sync_main_context_date(selected)
        self._request_main_cache_refresh(
            schedule=not self._calendar_cache_covers_range(month_start, month_end),
            work=not self._directive_cache_matches_date(selected),
            target_date=selected,
        )
        self._refresh_panel()

    def _render_from_main_cache(self) -> None:
        panel = self._panel
        if panel is None or not panel.isVisible():
            return

        today = QDate.currentDate()
        selected = panel.selected_date()
        month_start, month_end = panel.visible_month_bounds()
        data_signature = self._data_signature(today, selected, month_start, month_end)
        render_signature = data_signature + (self._style_signature(panel),)
        if render_signature == self._last_render_signature:
            return

        cached_state = self._get_cached_render_state(data_signature)
        if cached_state is None:
            marked_rows = self._cached_rows_for_month(month_start, month_end)
            schedule_rows = self._cached_rows_for_date(selected)
            directive_cache = (
                self._directive_cache() if self._directive_cache_matches_date(selected) else {}
            )

            marked = self._cached_month_marked_dates(month_start, month_end, marked_rows)
            schedule_entries = self._cached_schedule_entries_for_date(selected, schedule_rows)
            work_entries = self._cached_work_entries_for_date(selected, directive_cache)

            entries: list[_WidgetEntry] = []
            if schedule_entries:
                # 날짜 헤더: "4월 6일 일  오늘" 형태
                _sel_date_header = _build_date_section_title(selected)
                entries.append(_WidgetEntry(title=_sel_date_header, is_section=True))
                entries.extend(schedule_entries)

            if work_entries:
                entries.extend(work_entries)

            self._remember_render_state(data_signature, marked, entries)
        else:
            marked, entries = cached_state

        panel.set_calendar_marks(marked, today=today, selected=selected)
        panel.render_entries(entries)
        self._last_render_signature = render_signature

    def _open_task_dialog_helper(
        self,
        task_type: str = "schedule",
        initial_date: QDate | None = None,
        text: str | None = None,
    ) -> None:
        if initial_date is None or not initial_date.isValid():
            initial_date = self._current_date()
        time_str, name = (None, None)
        if text:
            time_str, name = _parse_quick_add_text(text)
        if hasattr(self._app, "open_task_dialog"):
            prefill = {"name": name} if name else {}
            kwargs: dict = {
                "initial_date": initial_date,
                "task_type": task_type,
                "prefill_dict": prefill,
            }
            if time_str:
                kwargs["initial_time"] = time_str
            self._app.open_task_dialog(**kwargs)

    def _open_schedule_create_with_text(self, target_date: QDate, text: str) -> None:
        self._open_task_dialog_helper(task_type="schedule", initial_date=target_date, text=text)

    def _mark_task_completed(self, task_id: int) -> None:
        if task_id <= 0:
            return
        if hasattr(self._app, "handle_task_status_changed"):
            self._app.handle_task_status_changed(task_id, "completed")
        self._invalidate_render_cache()
        self._refresh_panel()

    def _mark_directive_completed(self, directive_id: int) -> None:
        if directive_id <= 0:
            return
        if hasattr(self._app, "handle_directive_status_changed"):
            self._app.handle_directive_status_changed(directive_id, "completed")
        self._invalidate_render_cache()
        QTimer.singleShot(60, self._refresh_panel)

    def _delete_directive_from_widget(self, directive_id: int) -> None:
        if directive_id <= 0:
            return
        if hasattr(self._app, "delete_selected_directives") and hasattr(
            self._app, "selected_directive_ids"
        ):
            prev = set(getattr(self._app, "selected_directive_ids", set()))
            try:
                self._app.selected_directive_ids = {directive_id}
                self._app.delete_selected_directives()
            finally:
                self._app.selected_directive_ids = prev
        else:
            directive_repo.move_directive_to_trash(directive_id, reason="widget_mode_delete")
            if hasattr(self._app, "_refresh_all_panels"):
                self._app._refresh_all_panels()
        self._invalidate_render_cache()
        self._refresh_panel_later()

    def _delete_task_from_widget(self, task_id: int) -> None:
        if task_id <= 0:
            return
        if hasattr(self._app, "handle_task_deleted"):
            self._app.handle_task_deleted(task_id)
        self._invalidate_render_cache()
        self._refresh_panel_later()

    def _show_task_entry_menu(self, anchor: QWidget, pos: QPoint, task_id: int) -> None:
        if task_id <= 0:
            return
        menu = QMenu(anchor)
        act_open = menu.addAction(t("widget_mode.menu_edit_task", "열기/수정"))
        act_complete = menu.addAction(t("widget_mode.menu_complete_task", "완료 처리"))
        menu.addSeparator()
        prio_menu = menu.addMenu(t("widget_mode.menu_priority", "우선순위"))
        prio_actions = {
            prio_menu.addAction(t("widget_mode.priority_urgent", "긴급")): "urgent",
            prio_menu.addAction(t("widget_mode.priority_high", "높음")): "high",
            prio_menu.addAction(t("widget_mode.priority_normal", "보통")): "normal",
            prio_menu.addAction(t("widget_mode.priority_low", "낮음")): "low",
        }
        menu.addSeparator()
        act_delete = menu.addAction(t("widget_mode.menu_delete_task", "삭제"))
        chosen = menu.exec(anchor.mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == act_open:
            self._open_task(task_id)
        elif chosen == act_complete:
            self._mark_task_completed(task_id)
        elif chosen == act_delete:
            self._delete_task_from_widget(task_id)
        elif chosen in prio_actions:
            if hasattr(self._app, "handle_task_priority_changed"):
                self._app.handle_task_priority_changed(task_id, prio_actions[chosen])
            self._invalidate_render_cache()
            self._refresh_panel_later()

    def _show_directive_entry_menu(self, anchor: QWidget, pos: QPoint, directive_id: int) -> None:
        if directive_id <= 0:
            return
        menu = QMenu(anchor)
        act_open = menu.addAction(t("widget_mode.menu_edit_directive", "열기/수정"))
        act_complete = menu.addAction(t("widget_mode.menu_complete_directive", "완료 처리"))
        menu.addSeparator()
        prio_menu = menu.addMenu(t("widget_mode.menu_priority", "우선순위"))
        prio_actions = {
            prio_menu.addAction(t("widget_mode.priority_urgent", "긴급")): "urgent",
            prio_menu.addAction(t("widget_mode.priority_high", "높음")): "high",
            prio_menu.addAction(t("widget_mode.priority_normal", "보통")): "normal",
            prio_menu.addAction(t("widget_mode.priority_low", "낮음")): "low",
        }
        menu.addSeparator()
        act_delete = menu.addAction(t("widget_mode.menu_delete_directive", "삭제"))
        chosen = menu.exec(anchor.mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == act_open:
            self._open_directive(directive_id)
        elif chosen == act_complete:
            self._mark_directive_completed(directive_id)
        elif chosen == act_delete:
            self._delete_directive_from_widget(directive_id)
        elif chosen in prio_actions:
            if hasattr(self._app, "handle_directive_priority_changed"):
                self._app.handle_directive_priority_changed(directive_id, prio_actions[chosen])
            self._invalidate_render_cache()
            self._refresh_panel_later()

    # ------------------------------------------------------------------
    # Data collection
    # ------------------------------------------------------------------

    def _collect_schedule_entries_for_date(self, target: QDate) -> list[_WidgetEntry]:
        if not target.isValid():
            return []
        date_str = target.toString("yyyy-MM-dd")
        rows = sorted(
            search_repo.get_schedule_tasks_overlapping_range_with_progress(date_str, date_str)
            or [],
            key=lambda row: (
                _safe_text(row.get("deadline")) or "9999-99-99 99:99",
                int(row.get("id") or 0),
            ),
        )
        all_day_text = t("widget_mode.all_day", "종일")
        entries: list[_WidgetEntry] = []
        for row in rows[:18]:
            task_id = int(row.get("id") or 0)
            if task_id <= 0:
                continue
            title = _safe_text(row.get("name")) or t("widget_mode.untitled", "(제목 없음)")

            # ── 시간 레이블: 시작~종료 / 종일 ──────────────────────────
            start_dt = _parse_qdatetime(_safe_text(row.get("deadline")))
            end_dt = _parse_qdatetime(_safe_text(row.get("end_date") or row.get("end_time") or ""))
            has_time = start_dt.isValid() and len(_safe_text(row.get("deadline"))) >= 16
            if not has_time:
                time_label = all_day_text
            else:
                from PyQt6.QtCore import QLocale as _QL

                _loc = _QL()
                start_str = _loc.toString(start_dt.time(), _QL.FormatType.ShortFormat).strip()
                if (
                    end_dt.isValid()
                    and len(_safe_text(row.get("end_date") or row.get("end_time") or "")) >= 16
                ):
                    end_str = _loc.toString(end_dt.time(), _QL.FormatType.ShortFormat).strip()
                    time_label = f"{start_str}~{end_str}"
                else:
                    time_label = start_str

            # ── 세부정보: 장소, 담당자 ─────────────────────────────────
            detail_parts = []
            location = _safe_text(row.get("location"))
            assignee = _safe_text(row.get("assignee"))
            if location:
                detail_parts.append(f"📍 {location}")
            if assignee:
                detail_parts.append(f"👤 {assignee}")

            # 메모: 40자 초과 시 "..." 처리, 전체는 툴팁/팝업용으로 보관
            memo_raw = _safe_text(row.get("memo") or row.get("description") or "")
            memo_full = memo_raw.replace("\n", " ").strip()
            memo_display = ""
            if memo_full and memo_full not in ("none", "None", "-"):
                memo_display = (memo_full[:40] + "…") if len(memo_full) > 40 else memo_full

            # subtitle: time_label\n장소\n담당자 (메모는 별도 보관)
            subtitle_parts = [time_label] if time_label != all_day_text else []
            subtitle_parts.extend(detail_parts)
            subtitle = "\n".join(subtitle_parts)

            entries.append(
                _WidgetEntry(
                    title=title,
                    subtitle=subtitle,
                    memo=memo_display,
                    memo_full=memo_full,
                    callback=lambda tid=task_id: self._open_task(tid),
                    delete_callback=lambda tid=task_id: self._delete_task_from_widget(tid),
                    context_menu_callback=lambda anchor, pos, tid=task_id: (
                        self._show_task_entry_menu(anchor, pos, tid)
                    ),
                )
            )
        return entries

    def _collect_month_marked_dates(self, month_start: QDate, month_end: QDate) -> dict[QDate, int]:
        if not month_start.isValid() or not month_end.isValid():
            return {}
        rows = (
            search_repo.get_schedule_tasks_overlapping_range_with_progress(
                month_start.toString("yyyy-MM-dd"), month_end.toString("yyyy-MM-dd")
            )
            or []
        )
        marked: dict[QDate, int] = {}
        for row in rows:
            start_qd = _parse_qdate(row.get("deadline"))
            end_qd = _parse_qdate(row.get("end_date") or row.get("deadline"))
            if not start_qd.isValid():
                continue
            if not end_qd.isValid() or end_qd < start_qd:
                end_qd = start_qd
            cursor = start_qd if start_qd >= month_start else month_start
            last = end_qd if end_qd <= month_end else month_end
            while cursor.isValid() and cursor <= last:
                marked[cursor] = marked.get(cursor, 0) + 1
                cursor = cursor.addDays(1)
        return marked

    def _collect_today_work_entries(self) -> list[_WidgetEntry]:
        today = QDate.currentDate()
        entries: list[_WidgetEntry] = []

        routine_rows = sorted(
            search_repo.get_tasks_by_type_with_progress("routine") or [],
            key=lambda row: (
                _safe_text(row.get("target_date") or row.get("period_end") or row.get("deadline")),
                _priority_rank(row.get("priority")),
                int(row.get("id") or 0),
            ),
        )
        routine_entries: list[_WidgetEntry] = []
        for row in routine_rows:
            status = _normalize_status(row.get("status"))
            due_qd = _parse_qdate(
                row.get("period_end") or row.get("deadline") or row.get("target_date")
            )
            target_qd = _parse_qdate(row.get("target_date"))
            is_today = (due_qd.isValid() and due_qd == today) or (
                target_qd.isValid() and target_qd == today
            )
            if not is_today:
                continue
            if status in {"done", "completed"} or row.get("is_completed") in (1, True):
                continue
            rid = int(row.get("id") or 0)
            if rid <= 0:
                continue
            title = _safe_text(row.get("name")) or t("widget_mode.untitled", "(제목 없음)")
            subtitle = _format_compact_date(due_qd) if due_qd.isValid() and due_qd != today else ""
            routine_entries.append(
                _WidgetEntry(
                    title=title,
                    subtitle=subtitle,
                    callback=lambda tid=rid: self._open_task(tid),
                    delete_callback=lambda tid=rid: self._delete_task_from_widget(tid),
                    context_menu_callback=lambda anchor, pos, tid=rid: self._show_task_entry_menu(
                        anchor, pos, tid
                    ),
                )
            )
            if len(routine_entries) >= 10:
                break

        done_statuses = {"done", "completed", "deferred", "canceled", "cancelled"}
        directive_entries: list[_WidgetEntry] = []
        for row in directive_repo.get_recent_directives(limit=200) or []:
            if len(row) >= 5:
                did, content, status, _receiver, deadline = row[:5]
            elif len(row) >= 4:
                did, content, status, _receiver = row[:4]
                deadline = ""
            else:
                continue
            status_norm = _normalize_status(status)
            deadline_qd = _parse_qdate(deadline)
            if deadline_qd.isValid() and deadline_qd > today:
                continue
            if status_norm in done_statuses:
                continue
            did_int = int(did or 0)
            if did_int <= 0:
                continue
            title = _safe_text(content) or t("widget_mode.untitled", "(제목 없음)")
            subtitle = (
                _format_compact_date(deadline_qd)
                if deadline_qd.isValid() and deadline_qd != today
                else ""
            )
            directive_entries.append(
                _WidgetEntry(
                    title=title,
                    subtitle=subtitle,
                    callback=lambda x=did_int: self._open_directive(x),
                    delete_callback=lambda x=did_int: self._delete_directive_from_widget(x),
                    context_menu_callback=lambda anchor, pos, did=did_int: (
                        self._show_directive_entry_menu(anchor, pos, did)
                    ),
                )
            )
            if len(directive_entries) >= 10:
                break

        if routine_entries:
            entries.append(
                _WidgetEntry(title=t("widget_mode.section_routine_today", "업무"), is_section=True)
            )
            entries.extend(routine_entries)
        if directive_entries:
            entries.append(
                _WidgetEntry(
                    title=t("widget_mode.section_directive_today", "지시/협조"), is_section=True
                )
            )
            entries.extend(directive_entries)
        return entries

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _refresh_panel(self) -> None:
        """Coalesce repeated widget refresh requests into a short single-shot tick."""
        if self._panel is None:
            return
        self._debounce_timer.start(self._debounce_timer.interval())

    def _do_refresh_async(self) -> None:
        """실제 DB 조회를 백그라운드 스레드에서 실행."""
        panel = self._panel
        if panel is None or not panel.isVisible():
            self._is_refreshing = False
            return

        # Loading Guard: prevent stacked requests
        if self._is_refreshing:
            return
        self._is_refreshing = True

        # Clean existing worker
        if self._refresh_worker is not None and self._refresh_worker.isRunning():
            with contextlib.suppress(Exception):
                self._refresh_worker.task_done.disconnect()
            self._refresh_worker = None

        today = QDate.currentDate()
        selected = panel.selected_date()
        month_start, month_end = panel.visible_month_bounds()

        def _query(today=today, selected=selected, month_start=month_start, month_end=month_end):
            marked = self._collect_month_marked_dates(month_start, month_end)
            schedule = self._collect_schedule_entries_for_date(selected)
            work = self._collect_today_work_entries()
            return (today, selected, marked, schedule, work)

        worker = DbTaskWorker(_query)
        worker.task_done.connect(self._on_refresh_done)
        self._refresh_worker = worker
        worker.start()

    def _on_refresh_done(self, ok: bool, result: object) -> None:
        self._is_refreshing = False
        self._refresh_worker = None
        # Cache every successful query result for background pre-fetching
        if ok and result:
            self._cached_result = result

        panel = self._panel
        if not ok or panel is None:
            return

        # Unpack result (always matches structure: today, selected, marked, schedule, work)
        today, selected, marked, schedule_entries, work_entries = result
        panel.set_calendar_marks(marked, today=today, selected=selected)

        entries: list[_WidgetEntry] = []
        if schedule_entries:
            _sel_date_header = _build_date_section_title(selected)
            entries.append(_WidgetEntry(title=_sel_date_header, is_section=True))
            entries.extend(schedule_entries)

        if work_entries:
            entries.extend(work_entries)

        # Use cached tokens — avoid QSettings read on every render
        panel.list_widget.set_entries(
            entries,
            panel._theme_cache,
            t("widget_mode.empty_panel", "항목이 없습니다."),
            scale=panel._last_scale,
        )

    # ------------------------------------------------------------------
    # Always-on-top
    # ------------------------------------------------------------------

    def _apply_always_on_top_to_widget(self, widget: QWidget | None) -> None:
        if widget is None or not widget.isVisible():
            return
        enabled = str(self._settings.value("widget_mode_always_top", "false")).lower() == "true"
        flags = widget.windowFlags()
        has_flag = bool(flags & Qt.WindowType.WindowStaysOnTopHint)
        if has_flag == enabled:
            return
        if enabled:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        widget.setWindowFlags(flags)
        widget.show()

    def toggle_always_on_top(self) -> None:
        current = str(self._settings.value("widget_mode_always_top", "false")).lower() == "true"
        new_val = not current
        self._settings.setValue("widget_mode_always_top", new_val)
        self._apply_always_on_top_to_widget(self._panel)
        if hasattr(self._app, "show_toast"):
            msg = (
                t("widget_mode.toast_always_top_on", "항상 위 모드가 활성화되었습니다.")
                if new_val
                else t("widget_mode.toast_always_top_off", "항상 위 모드가 비활성화되었습니다.")
            )
            self._app.show_toast(t("widget_mode.title", "위젯 모드"), msg)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_widget_mode_active(self) -> bool:
        return bool(self._widget_mode_active)

    def open_panel(self) -> None:
        panel = self._ensure_panel()
        is_new = not panel.isVisible()

        # Singleton Guard & Focus
        if self._widget_mode_active and not is_new:
            panel.raise_()
            panel.activateWindow()
            return

        if is_new:
            panel.calendar.setSelectedDate(self._current_date())
        panel.show()
        if is_new:
            self._position_panel(force_reset=True)
        target_date = self._panel_context_date(panel)
        month_start, month_end = panel.visible_month_bounds()
        self._ensure_main_cache_coverage(target_date, month_start, month_end)
        self._render_from_main_cache()

        # 저장된 선택 상태 복현
        saved_task_ids = self._settings.value("panel_selected_task_ids", [])
        saved_directive_ids = self._settings.value("panel_selected_directive_ids", [])
        if isinstance(saved_task_ids, (list, tuple)):
            self._app.selected_task_ids = set(saved_task_ids)
        if isinstance(saved_directive_ids, (list, tuple)):
            self._app.selected_directive_ids = set(saved_directive_ids)

        panel.raise_()
        panel.activateWindow()

    def close_panel(self) -> None:
        if self._panel is not None:
            # 현재 선택 상태 저장
            task_ids = getattr(self._app, "selected_task_ids", set())
            directive_ids = getattr(self._app, "selected_directive_ids", set())
            self._settings.setValue("panel_selected_task_ids", list(task_ids))
            self._settings.setValue("panel_selected_directive_ids", list(directive_ids))
            self._panel.hide()

    # compat shims — callers that used to open individual widgets
    def open_schedule_widget(self) -> None:
        self.open_panel()

    def open_work_widget(self) -> None:
        self.open_panel()

    def open_all_widgets(self) -> None:
        self.open_panel()

    def close_widgets(self) -> None:
        self.close_panel()

    def toggle_launcher(self, *_args, **_kwargs) -> None:
        if self._panel is not None and self._panel.isVisible():
            self.close_panel()
        else:
            self.open_panel()

    def enter_widget_mode(self, *args, **kwargs) -> None:
        if self._widget_mode_active:
            if self._panel:
                self._panel.raise_()
                self._panel.activateWindow()
            return
        self._widget_mode_active = True
        self.open_panel()
        self._hide_main_window()

    def exit_widget_mode(self) -> None:
        self._widget_mode_active = False
        self.close_panel()
        self._show_main_window()

    def toggle_widget_mode(self, *args, **kwargs) -> None:
        if self._widget_mode_active:
            self.exit_widget_mode()
        else:
            self.enter_widget_mode(*args, **kwargs)

    def refresh_visible_widgets(self, *_args, **_kwargs) -> None:
        if self._panel is not None and self._panel.isVisible():
            self._maybe_apply_panel_palette(self._panel)
            self._render_from_main_cache()
