from collections.abc import Callable
import contextlib

from PyQt6.QtCore import QDate, QLocale, QPoint, QPropertyAnimation, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QMouseEvent, QPainter, QPen
from PyQt6.QtWidgets import (
    QCalendarWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStackedLayout,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.panel_widget_common import _relative_day_label, _WidgetEntry
from calendar_app.presentation.widgets.panel_widget_shell import _FloatingWidgetBase
from calendar_app.presentation.widgets.panel_widget_theme import (
    _resolve_widget_mode_tokens,
    _widget_mode_calendar_paint_palette,
    _widget_mode_calendar_stylesheet,
    _widget_mode_chip_stylesheet,
    _widget_mode_entry_style_bundle,
    _widget_mode_int_token,
    _widget_mode_quick_add_stylesheet,
)


class _WidgetCalendar(QCalendarWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setGridVisible(False)
        self.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.SingleLetterDayNames)
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.setNavigationBarVisible(True)
        self._tokens: dict[str, str] = {}
        # dict[date_str, event_count] — also accepts set[str] via set_visual_state
        self._marked_dates: dict[str, int] = {}
        self._today = QDate.currentDate()
        self._selected = QDate.currentDate()
        self._style_cache_key: tuple | None = None
        self._paint_cache_key: tuple | None = None
        self._paint_cache: dict[str, object] = {}
        self._last_visual_state_key: tuple | None = None

        # ── Navigation Icons & Month Selector Refinement ──────────
        # Access internal widgets of QCalendarWidget header
        prev_btn = self.findChild(QToolButton, "qt_calendar_prevmonth") or self.findChild(
            QPushButton, "qt_calendar_prevmonth"
        )
        next_btn = self.findChild(QToolButton, "qt_calendar_nextmonth") or self.findChild(
            QPushButton, "qt_calendar_nextmonth"
        )
        if prev_btn:
            prev_btn.setIcon(QIcon())
            prev_btn.setText("‹")
        if next_btn:
            next_btn.setIcon(QIcon())
            next_btn.setText("›")

        # Monthly selection should be consistent with year entry
        # The month selector in QCalendarWidget is usually a QToolButton or QComboBox
        # We ensure it's styled and behaves like the year input
        month_menu = self.findChild(QWidget, "qt_calendar_monthbutton")
        if month_menu:
            month_menu.setCursor(Qt.CursorShape.PointingHandCursor)

        # slide transition state
        self._anim_out: QPropertyAnimation | None = None
        self._anim_in: QPropertyAnimation | None = None
        self._anim_dir: int = 0
        self._refresh_navigation_texts()

    def _refresh_navigation_texts(self) -> None:
        prev_btn = self.findChild(QToolButton, "qt_calendar_prevmonth") or self.findChild(
            QPushButton, "qt_calendar_prevmonth"
        )
        next_btn = self.findChild(QToolButton, "qt_calendar_nextmonth") or self.findChild(
            QPushButton, "qt_calendar_nextmonth"
        )
        if prev_btn is not None:
            prev_btn.setText("‹")
            prev_btn.setToolTip(t("widget_mode.month_prev", "이전 달"))
            prev_btn.setAccessibleName(t("widget_mode.month_prev", "이전 달"))
        if next_btn is not None:
            next_btn.setText("›")
            next_btn.setToolTip(t("widget_mode.month_next", "다음 달"))
            next_btn.setAccessibleName(t("widget_mode.month_next", "다음 달"))

    @staticmethod
    def _token_signature(tokens: dict[str, str]) -> tuple:
        return tuple(sorted((str(key), str(value)) for key, value in (tokens or {}).items()))

    def set_visual_state(
        self,
        tokens: dict[str, str],
        marked_dates: "dict[str, int] | set[str]",
        today: QDate,
        selected: QDate,
    ) -> None:
        resolved_tokens = _resolve_widget_mode_tokens(tokens=tokens)
        if isinstance(marked_dates, dict):
            normalized_marks = {
                str(k): max(1, int(v)) for k, v in marked_dates.items() if str(k).strip()
            }
        else:
            normalized_marks = {str(raw): 1 for raw in marked_dates if str(raw).strip()}
        resolved_today = today if today.isValid() else QDate.currentDate()
        resolved_selected = selected if selected.isValid() else QDate()
        visual_state_key = (
            self._token_signature(resolved_tokens),
            tuple(sorted(normalized_marks.items())),
            resolved_today.toString("yyyy-MM-dd"),
            resolved_selected.toString("yyyy-MM-dd") if resolved_selected.isValid() else "",
        )
        if visual_state_key == self._last_visual_state_key:
            return
        self._last_visual_state_key = visual_state_key
        self._tokens = resolved_tokens
        self._marked_dates = normalized_marks
        self._today = resolved_today
        self._selected = resolved_selected
        self._update_calendar_style()
        self.updateCells()

    def _update_calendar_style(self) -> None:
        if not self._tokens:
            return
        style_key = self._token_signature(self._tokens)
        if style_key != self._style_cache_key:
            self.setStyleSheet(_widget_mode_calendar_stylesheet(tokens=self._tokens))
            self._style_cache_key = style_key
        if style_key != self._paint_cache_key:
            palette = _widget_mode_calendar_paint_palette(tokens=self._tokens)
            base_font = QFont(self.font())
            base_font.setPointSizeF(max(10.0, base_font.pointSizeF() or 10.0))
            normal_font = QFont(base_font)
            normal_font.setWeight(QFont.Weight.Normal)
            medium_font = QFont(base_font)
            medium_font.setWeight(QFont.Weight.Medium)
            demi_font = QFont(base_font)
            demi_font.setWeight(QFont.Weight.DemiBold)
            bold_font = QFont(base_font)
            bold_font.setWeight(QFont.Weight.Bold)
            self._paint_cache = {
                "accent": QColor(palette["accent"]),
                "accent_deep": QColor(palette["accent_deep"]),
                "text_primary": QColor(palette["text_primary"]),
                "text_muted": QColor(palette["text_muted"]),
                "hero_bg": QColor(palette["hero_bg"]),
                "hero_bg_strong": QColor(palette["hero_bg_strong"]),
                "hero_border": QColor(palette["hero_border"]),
                "cell_radius": _widget_mode_int_token(
                    self._tokens, "widget_calendar_cell_radius", 10
                ),
                "today_radius": _widget_mode_int_token(
                    self._tokens, "widget_calendar_today_radius", 11
                ),
                "cell_inset_x": _widget_mode_int_token(
                    self._tokens, "widget_calendar_cell_inset_x", 5
                ),
                "cell_inset_y": _widget_mode_int_token(
                    self._tokens, "widget_calendar_cell_inset_y", 4
                ),
                "text_top_pad": _widget_mode_int_token(
                    self._tokens, "widget_calendar_text_top_pad", 1
                ),
                "text_bottom_pad": _widget_mode_int_token(
                    self._tokens, "widget_calendar_text_bottom_pad", 2
                ),
                "marker_lane": _widget_mode_int_token(
                    self._tokens, "widget_calendar_marker_lane_height", 11
                ),
                "marker_gap": _widget_mode_int_token(self._tokens, "widget_calendar_marker_gap", 5),
                "marker_bottom_pad": _widget_mode_int_token(
                    self._tokens, "widget_calendar_marker_bottom_pad", 4
                ),
                "dot_spacing": _widget_mode_int_token(
                    self._tokens, "widget_calendar_dot_spacing", 7
                ),
                "font_normal": normal_font,
                "font_medium": medium_font,
                "font_demi": demi_font,
                "font_bold": bold_font,
            }
            self._paint_cache_key = style_key

    def visual_marked_dates(self) -> dict[str, int]:
        return dict(self._marked_dates)

    def visual_state(self) -> tuple[QDate, QDate]:
        return self._today, self._selected

    # ------------------------------------------------------------------
    # Slide transition animation
    # ------------------------------------------------------------------

    def _prepare_transition(self, direction: int) -> None:
        """Slide the calendar out then in.  direction: +1=next, -1=prev."""
        from PyQt6.QtCore import QEasingCurve as _EC
        from PyQt6.QtCore import QPropertyAnimation as _PA

        # stop any running anim
        for a in (self._anim_out, self._anim_in):
            if a is not None and a.state() == _PA.State.Running:
                a.stop()
                a.deleteLater()
        self._anim_out = None
        self._anim_in = None
        self._anim_dir = direction

        W = self.width() or max(self.sizeHint().width(), 200)
        orig_y = self.pos().y()

        out = _PA(self, b"pos", self)
        out.setDuration(110)
        out.setStartValue(QPoint(0, orig_y))
        out.setEndValue(QPoint(-direction * W, orig_y))
        out.setEasingCurve(_EC.Type.InCubic)

        in_ = _PA(self, b"pos", self)
        in_.setDuration(130)
        in_.setStartValue(QPoint(direction * W, orig_y))
        in_.setEndValue(QPoint(0, orig_y))
        in_.setEasingCurve(_EC.Type.OutCubic)

        self._anim_out = out
        self._anim_in = in_
        out.finished.connect(self._start_in_anim)
        out.start()

    def _start_in_anim(self) -> None:
        d = self._anim_dir
        W = self.width() or max(self.sizeHint().width(), 200)
        self.move(d * W, self.pos().y())
        if self._anim_in is not None:
            self._anim_in.start()

    # ------------------------------------------------------------------
    # Cell painting
    # ------------------------------------------------------------------

    def _cell_layout_metrics(self, rect, *, is_marked: bool) -> dict[str, object]:
        from PyQt6.QtCore import QRectF as _RF

        cache = self._paint_cache or {}
        inset_x = float(cache.get("cell_inset_x", 5))
        inset_y = float(cache.get("cell_inset_y", 4))
        text_top_pad = float(cache.get("text_top_pad", 1))
        text_bottom_pad = float(cache.get("text_bottom_pad", 2))
        marker_lane = float(cache.get("marker_lane", 11))
        marker_gap = float(cache.get("marker_gap", 5))
        marker_bottom_pad = float(cache.get("marker_bottom_pad", 4))
        dot_spacing = float(cache.get("dot_spacing", 7))

        if not is_marked:
            marker_lane = 0.0
            marker_gap = 0.0
            marker_bottom_pad = max(2.0, marker_bottom_pad - 1.0)

        cell = _RF(
            rect.adjusted(
                int(round(inset_x)),
                int(round(inset_y)),
                -int(round(inset_x)),
                -int(round(inset_y)),
            )
        )
        reserved_bottom = marker_lane + marker_gap + marker_bottom_pad
        text_rect = _RF(
            cell.adjusted(
                0,
                int(round(text_top_pad)),
                0,
                -int(round(reserved_bottom + text_bottom_pad)),
            )
        )
        highlight_rect = _RF(cell.adjusted(0.5, 0.5, -0.5, -0.5))
        mark_rect = _RF(
            cell.adjusted(
                1,
                1,
                -1,
                -max(1, int(round(reserved_bottom - 1.0))),
            )
        )
        available_marker_width = max(16.0, cell.width() - 10.0)
        dot_radius = min(
            3.2,
            max(
                2.1, min(available_marker_width / 10.0, marker_lane * 0.28 if marker_lane else 2.4)
            ),
        )
        dot_spacing = max(dot_spacing, dot_radius * 1.7)
        marker_center_y = (
            float(cell.bottom()) - marker_bottom_pad - max(marker_lane / 2.0, dot_radius)
        )

        return {
            "cell": cell,
            "highlight_rect": highlight_rect,
            "mark_rect": mark_rect,
            "text_rect": text_rect,
            "marker_center_y": marker_center_y,
            "dot_radius": dot_radius,
            "dot_spacing": dot_spacing,
        }

    def paintCell(self, painter: QPainter, rect, date: QDate) -> None:
        from PyQt6.QtCore import QRectF as _RF

        tokens = self._tokens
        if not tokens:
            super().paintCell(painter, rect, date)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        day_key = date.toString("yyyy-MM-dd")
        selected = self.selectedDate()
        if not selected.isValid():
            selected = self._selected

        is_current_month = date.month() == self.monthShown() and date.year() == self.yearShown()
        is_today = self._today.isValid() and date == self._today
        is_selected = selected.isValid() and date == selected
        event_count = self._marked_dates.get(day_key, 0)
        is_marked = event_count > 0

        paint_cache = self._paint_cache
        accent = QColor(paint_cache["accent"])
        accent_deep = QColor(paint_cache["accent_deep"])
        text_primary = QColor(paint_cache["text_primary"])
        text_muted = QColor(paint_cache["text_muted"])
        hero_bg = QColor(paint_cache["hero_bg"])
        hero_bg_strong = QColor(paint_cache["hero_bg_strong"])
        hero_border = QColor(paint_cache["hero_border"])
        cell_radius = int(paint_cache["cell_radius"])
        today_radius = int(paint_cache["today_radius"])

        if not is_current_month:
            painter.restore()
            return

        layout = self._cell_layout_metrics(rect, is_marked=is_marked)
        cell = layout["cell"]
        highlight_rect = layout["highlight_rect"]
        mark_rect = layout["mark_rect"]
        text_rect = layout["text_rect"]
        number_color = QColor(text_primary)
        if number_color.alpha() == 0:
            number_color.setAlpha(255)

        # ---- marked background (light tint, only when not today/selected)
        if is_marked and not is_today and not is_selected and mark_rect.height() > 8:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(hero_bg))
            painter.drawRoundedRect(mark_rect, cell_radius, cell_radius)

        # ---- today highlight
        if is_today and not is_selected:
            today_fill = QColor(hero_bg_strong)
            today_fill.setAlpha(156)
            today_bord = QColor(hero_border)
            today_bord.setAlpha(166)
            painter.setPen(QPen(today_bord, 1))
            painter.setBrush(today_fill)
            painter.drawRoundedRect(highlight_rect, today_radius, today_radius)
            number_color = QColor(accent_deep)

        # ---- selected highlight
        if is_selected:
            sel_fill = QColor(accent)
            sel_fill.setAlpha(62)
            sel_bord = QColor(accent)
            sel_bord.setAlpha(150)
            painter.setPen(QPen(sel_bord, 1))
            painter.setBrush(sel_fill)
            painter.drawRoundedRect(highlight_rect, today_radius, today_radius)
            number_color = QColor(accent_deep)

        # ---- day number
        if is_selected:
            font = paint_cache["font_bold"]
        elif is_today:
            font = paint_cache["font_demi"]
        elif is_marked:
            font = paint_cache["font_medium"]
        else:
            font = paint_cache["font_normal"]
        painter.setFont(font)
        painter.setPen(number_color)
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignCenter), str(date.day()))

        # ---- event dots (up to 3)
        if is_marked:
            n_dots = min(event_count, 3)
            dot_r = float(layout["dot_radius"])
            spacing = float(layout["dot_spacing"])
            total_w = n_dots * dot_r * 2 + (n_dots - 1) * spacing
            cx0 = float(cell.center().x()) - total_w / 2 + dot_r
            cy = float(layout["marker_center_y"])

            if is_selected:
                dot_q = QColor(255, 255, 255, 200)
            elif is_today:
                dot_q = QColor(accent_deep)
                dot_q.setAlpha(200)
            else:
                dot_q = QColor(accent if is_current_month else text_muted)
                dot_q.setAlpha(220 if is_current_month else 90)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(dot_q)
            for i in range(n_dots):
                cx = cx0 + i * (dot_r * 2 + spacing)
                painter.drawEllipse(_RF(cx - dot_r, cy - dot_r, dot_r * 2, dot_r * 2))

        painter.restore()


class _EntryListWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setMouseTracking(True)
        # Widget Pool: dict of lists to recycle specific types
        self._pool: dict[str, list[QWidget]] = {
            "empty": [],
            "section": [],
            "divider": [],
            "row": [],
        }
        # Render State Cache
        self._slot_kinds: list[str] = []
        self._style_cache_key: tuple | None = None
        self._style_bundle: dict[str, str] = {}

    def _get_style_bundle(self, tokens: dict[str, str], scale: float) -> dict[str, str]:
        key = (id(tokens), scale, tokens.get("accent"), tokens.get("panel_bg"))
        if key != self._style_cache_key:
            self._style_bundle = _widget_mode_entry_style_bundle(tokens=tokens, scale=scale)
            self._style_cache_key = key
        return self._style_bundle

    def set_entries(
        self,
        entries: list[_WidgetEntry],
        tokens: dict[str, str],
        empty_text: str,
        *,
        scale: float = 1.0,
    ) -> None:
        style_bundle = self._get_style_bundle(tokens, scale)

        # Build desired structure
        desired: list[tuple[str, _WidgetEntry | None]] = []
        if not entries:
            desired.append(("empty", None))
        else:
            for e in entries:
                if e.is_section and e.title == "---":
                    desired.append(("divider", e))
                else:
                    desired.append(("section" if e.is_section else "row", e))
        sequence_flags = [
            (
                idx > 0 and desired[idx - 1][0] == "row",
                idx + 1 < len(desired) and desired[idx + 1][0] == "row",
            )
            for idx in range(len(desired))
        ]

        # 1. Clean up Trailing Stretches (internal layout management)
        while self._layout.count() > 0:
            item = self._layout.itemAt(self._layout.count() - 1)
            if item.widget() is None:
                self._layout.takeAt(self._layout.count() - 1)
                continue
            break

        # 2. Synchronize Layout with Desired Structure
        # We reuse existing widgets at the same index if kind matches.
        # If not, we move current to pool and pull correct kind from pool.
        for i, (kind, entry) in enumerate(desired):
            current_kind = self._slot_kinds[i] if i < len(self._slot_kinds) else None

            if current_kind != kind:
                # Type Mismatch at this slot -> Replace with pooled widget
                # a. Push current to pool if it exists
                if i < self._layout.count():
                    item = self._layout.takeAt(i)
                    old_w = item.widget()
                    if old_w:
                        old_w.hide()
                        self._pool[current_kind or "row"].append(old_w)

                # b. Pull from pool or create new
                new_w = self._get_from_pool(kind)
                self._layout.insertWidget(i, new_w)

                # Update tracking
                if i < len(self._slot_kinds):
                    self._slot_kinds[i] = kind
                else:
                    self._slot_kinds.append(kind)

            # c. Update Content (Dirty Checking: only set text/style if changed)
            has_prev_row, has_next_row = sequence_flags[i]
            self._update_widget_content(
                self._layout.itemAt(i).widget(),
                kind,
                entry,
                style_bundle,
                tokens,
                empty_text,
                has_prev_row=has_prev_row,
                has_next_row=has_next_row,
            )

        # 3. Excess widgets to Pool
        while self._layout.count() > len(desired):
            item = self._layout.takeAt(len(desired))
            trash_w = item.widget()
            if trash_w:
                trash_w.hide()
                trash_kind = self._slot_kinds.pop(len(desired))
                self._pool[trash_kind].append(trash_w)

        # Always ensure exactly one stretch at the bottom
        self._layout.addStretch(1)

    def _get_from_pool(self, kind: str) -> QWidget:
        if self._pool[kind]:
            w = self._pool[kind].pop()
            w.show()
            return w

        # Generator for new widgets
        if kind == "section":
            section = QLabel("", self)
            section.setWordWrap(True)
            section.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            section.setMinimumHeight(24)
            return section
        elif kind == "empty":
            return QLabel("", self)
        elif kind == "divider":
            d = QFrame(self)
            d.setFixedHeight(1)
            d.setObjectName("widget_entry_divider")
            return d
        else:  # row
            w = QFrame(self)
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            outer = QVBoxLayout(w)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(0)
            btn = QPushButton("", w)
            btn.setObjectName("widget_entry_btn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.setFlat(True)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            btn_layout = QHBoxLayout(btn)
            btn_layout.setContentsMargins(10, 10, 12, 10)
            btn_layout.setSpacing(8)

            time_label = QLabel("", btn)
            time_label.setObjectName("widget_entry_time_label")
            time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            time_label.setWordWrap(True)
            time_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            time_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            time_label.setFixedWidth(58)
            btn_layout.addWidget(time_label, 0)

            timeline_col = QFrame(btn)
            timeline_col.setObjectName("widget_entry_timeline_col")
            timeline_col.setFixedWidth(18)
            timeline_stack = QStackedLayout(timeline_col)
            timeline_stack.setContentsMargins(0, 0, 0, 0)
            timeline_stack.setSpacing(0)
            timeline_stack.setStackingMode(QStackedLayout.StackingMode.StackAll)

            track_host = QWidget(timeline_col)
            track_layout = QHBoxLayout(track_host)
            track_layout.setContentsMargins(0, 0, 0, 0)
            track_layout.setSpacing(0)
            track_layout.addStretch(1)
            track = QFrame(track_host)
            track.setObjectName("widget_entry_timeline_track")
            track.setFixedWidth(2)
            track.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
            track_layout.addWidget(track)
            track_layout.addStretch(1)

            dot_host = QWidget(timeline_col)
            dot_layout = QVBoxLayout(dot_host)
            dot_layout.setContentsMargins(0, 0, 0, 0)
            dot_layout.setSpacing(0)
            dot_layout.addStretch(1)
            dot = QFrame(dot_host)
            dot.setObjectName("widget_entry_timeline_dot")
            dot.setFixedSize(12, 12)
            dot_layout.addWidget(dot, 0, Qt.AlignmentFlag.AlignHCenter)
            dot_layout.addStretch(1)

            timeline_stack.addWidget(track_host)
            timeline_stack.addWidget(dot_host)
            btn_layout.addWidget(timeline_col, 0)

            content = QWidget(btn)
            content.setObjectName("widget_entry_content")
            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(0, 0, 0, 0)
            content_layout.setSpacing(4)
            title_label = QLabel("", content)
            title_label.setObjectName("widget_entry_title")
            title_label.setWordWrap(True)
            title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            title_label.setMinimumWidth(0)
            subtitle_label = QLabel("", content)
            subtitle_label.setObjectName("widget_entry_subtitle")
            subtitle_label.setWordWrap(True)
            subtitle_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            subtitle_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            subtitle_label.setMinimumWidth(0)
            memo_label = QLabel("", content)
            memo_label.setObjectName("widget_entry_memo")
            memo_label.setWordWrap(False)
            memo_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            memo_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            memo_label.setCursor(Qt.CursorShape.PointingHandCursor)
            memo_label.setVisible(False)
            content_layout.addWidget(title_label)
            content_layout.addWidget(subtitle_label)
            content_layout.addWidget(memo_label)
            btn_layout.addWidget(content, 1)
            outer.addWidget(btn)
            w._entry_btn = btn
            w._entry_time_label = time_label
            w._entry_timeline_track = track
            w._entry_timeline_dot = dot
            w._entry_content = content
            w._entry_title_label = title_label
            w._entry_subtitle_label = subtitle_label
            w._entry_memo_label = memo_label
            w._entry_row_render_key = None
            w._entry_button_callback_key = None
            w._entry_context_callback_key = None
            w._entry_memo_callback_key = None
            return w

    @staticmethod
    def _split_timeline_text(subtitle: str) -> tuple[str, str]:
        parts = [part.strip() for part in str(subtitle or "").splitlines() if part.strip()]
        if not parts:
            return "", ""
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], "\n".join(parts[1:])

    def _update_widget_content(
        self,
        w: QWidget,
        kind: str,
        entry: "_WidgetEntry",
        bundle,
        tokens,
        empty_text,
        *,
        has_prev_row: bool = False,
        has_next_row: bool = False,
    ):
        if not w:
            return

        if kind == "empty":
            if w.text() != empty_text:
                w.setText(empty_text)
            w.setObjectName("widget_entry_empty")
            if w.styleSheet() != bundle["empty"]:
                w.setStyleSheet(bundle["empty"])

        elif kind == "section":
            title = entry.title if entry else ""
            if w.text() != title:
                w.setText(title)
            w.setObjectName("widget_entry_section")
            if w.styleSheet() != bundle["section"]:
                w.setStyleSheet(bundle["section"])

        elif kind == "divider":
            style = f"background: {tokens.get('section_border_soft', 'rgba(255,255,255,10)')}; margin: 3px 8px;"
            if w.styleSheet() != style:
                w.setStyleSheet(style)

        else:  # row
            btn = getattr(w, "_entry_btn", None) or w.findChild(QPushButton, "widget_entry_btn")
            time_label = getattr(w, "_entry_time_label", None) or w.findChild(
                QLabel, "widget_entry_time_label"
            )
            track = getattr(w, "_entry_timeline_track", None) or w.findChild(
                QFrame, "widget_entry_timeline_track"
            )
            title_label = getattr(w, "_entry_title_label", None) or w.findChild(
                QLabel, "widget_entry_title"
            )
            subtitle_label = getattr(w, "_entry_subtitle_label", None) or w.findChild(
                QLabel, "widget_entry_subtitle"
            )
            memo_label = getattr(w, "_entry_memo_label", None) or w.findChild(
                QLabel, "widget_entry_memo"
            )
            if (
                not btn
                or not title_label
                or not subtitle_label
                or time_label is None
                or track is None
            ):
                return
            w._entry_btn = btn
            w._entry_time_label = time_label
            w._entry_timeline_track = track
            w._entry_title_label = title_label
            w._entry_subtitle_label = subtitle_label
            if memo_label is not None:
                w._entry_memo_label = memo_label

            memo_text = getattr(entry, "memo", "")
            memo_full = getattr(entry, "memo_full", "")

            timeline_text, detail_text = self._split_timeline_text(entry.subtitle or "")
            label = entry.title if not entry.subtitle else f"{entry.title}\n{entry.subtitle}"
            width_key = max(w.width(), btn.width(), self.width(), 240)
            row_render_key = (
                label,
                width_key,
                bundle["button"],
                timeline_text,
                detail_text,
                memo_text,
                bool(has_prev_row),
                bool(has_next_row),
                id(entry.callback),
                id(entry.context_menu_callback),
            )
            if getattr(w, "_entry_row_render_key", None) == row_render_key:
                return
            w._entry_row_render_key = row_render_key

            if btn.text():
                btn.setText("")
            if btn.styleSheet() != bundle["button"]:
                btn.setStyleSheet(bundle["button"])
            if time_label.text() != timeline_text:
                time_label.setText(timeline_text)
            time_label.setVisible(True)
            track.setVisible(bool(has_prev_row or has_next_row))
            if title_label.text() != entry.title:
                title_label.setText(entry.title)
            subtitle_text = detail_text
            if subtitle_label.text() != subtitle_text:
                subtitle_label.setText(subtitle_text)
            subtitle_label.setVisible(bool(subtitle_text))
            if memo_label is not None:
                memo_display = f"📝 {memo_text}" if memo_text else ""
                if memo_label.text() != memo_display:
                    memo_label.setText(memo_display)
                memo_label.setVisible(bool(memo_text))
                if memo_text:
                    memo_label.setToolTip(memo_full if memo_full else memo_text)
                memo_callback_key = memo_full if memo_full else None
                if getattr(w, "_entry_memo_callback_key", None) != memo_callback_key:
                    with contextlib.suppress(Exception):
                        memo_label.mousePressEvent = None  # type: ignore[assignment]
                    if memo_full:

                        def _make_memo_handler(full_text: str):
                            def _on_memo_click(_ev, _ft=full_text):
                                from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QTextEdit
                                from PyQt6.QtWidgets import QVBoxLayout as _VBL

                                dlg = QDialog(w)
                                dlg.setWindowTitle(t("widget_mode.memo_popup_title", "메모"))
                                dlg.setMinimumWidth(320)
                                vbox = _VBL(dlg)
                                vbox.setContentsMargins(12, 12, 12, 12)
                                vbox.setSpacing(8)
                                te = QTextEdit(dlg)
                                te.setReadOnly(True)
                                te.setPlainText(_ft)
                                te.setMinimumHeight(120)
                                vbox.addWidget(te)
                                bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, dlg)
                                bb.accepted.connect(dlg.accept)
                                vbox.addWidget(bb)
                                dlg.exec()

                            return _on_memo_click

                        memo_label.mousePressEvent = _make_memo_handler(memo_full)  # type: ignore[method-assign]
                    w._entry_memo_callback_key = memo_callback_key
            tooltip_lines = [entry.title]
            if timeline_text:
                tooltip_lines.append(timeline_text)
            if subtitle_text:
                tooltip_lines.append(subtitle_text)
            btn.setToolTip("\n".join(part for part in tooltip_lines if part))
            body_width = max(150, width_key - 142)
            title_height = (
                title_label.heightForWidth(body_width)
                if title_label.hasHeightForWidth()
                else title_label.sizeHint().height()
            )
            subtitle_height = 0
            if subtitle_text:
                subtitle_height = (
                    subtitle_label.heightForWidth(body_width)
                    if subtitle_label.hasHeightForWidth()
                    else subtitle_label.sizeHint().height()
                )
            memo_height = 0
            if memo_text and memo_label is not None:
                memo_height = memo_label.sizeHint().height()
            btn.setMinimumHeight(max(74, title_height + subtitle_height + memo_height + 34))

            button_callback_key = id(entry.callback) if entry.callback else None
            if getattr(w, "_entry_button_callback_key", None) != button_callback_key:
                with contextlib.suppress(BaseException):
                    btn.clicked.disconnect()
                if entry.callback:
                    btn.clicked.connect(lambda _checked=False, cb=entry.callback: cb())
                w._entry_button_callback_key = button_callback_key

            context_callback_key = (
                id(entry.context_menu_callback) if entry.context_menu_callback else None
            )
            if getattr(w, "_entry_context_callback_key", None) != context_callback_key:
                with contextlib.suppress(BaseException):
                    btn.customContextMenuRequested.disconnect()
                if entry.context_menu_callback:
                    btn.customContextMenuRequested.connect(
                        lambda pos, anchor=btn, cb=entry.context_menu_callback: cb(anchor, pos)
                    )
                w._entry_context_callback_key = context_callback_key
            btn.setCursor(
                Qt.CursorShape.PointingHandCursor
                if entry.callback is not None
                else Qt.CursorShape.ArrowCursor
            )

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        super().mouseDoubleClickEvent(event)


class _QuickAddInput(QWidget):
    def __init__(
        self,
        parent: QWidget | None = None,
        placeholder: str = "",
        submit_callback: Callable[[str], None] | None = None,
    ):
        super().__init__(parent)
        self._submit_callback = submit_callback
        self._style_cache_key: tuple | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setClearButtonEnabled(True)
        self.edit.returnPressed.connect(self._handle_submit)
        layout.addWidget(self.edit, 1)

        self.submit_btn = QToolButton(self)
        self.submit_btn.setText(t("widget_mode.quick_add_submit", "Add"))
        self.submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.submit_btn.clicked.connect(self._handle_submit)
        layout.addWidget(self.submit_btn)

    def set_submit_callback(self, callback: Callable[[str], None] | None) -> None:
        self._submit_callback = callback

    def _handle_submit(self) -> None:
        text = self.edit.text().strip()
        if not text:
            return
        if self._submit_callback is not None:
            self._submit_callback(text)
        self.edit.clear()
        # 포커스 유지 및 다음 입력 준비
        self.edit.setFocus()
        self.edit.selectAll()

    def apply_palette(self, tokens: dict[str, str], scale: float = 1.0) -> None:
        resolved_tokens = _resolve_widget_mode_tokens(tokens=tokens)
        min_height = max(34, int(round(34 * scale)))
        if self.edit.minimumHeight() != min_height:
            self.edit.setMinimumHeight(min_height)
        style_key = (
            int(round(scale * 100)),
            tuple(sorted((str(key), str(value)) for key, value in resolved_tokens.items())),
        )
        if style_key != self._style_cache_key:
            self.setStyleSheet(
                _widget_mode_quick_add_stylesheet(tokens=resolved_tokens, scale=scale)
            )
            self._style_cache_key = style_key


class _PanelWidget(_FloatingWidgetBase):
    """통합 패널 위젯 — 캘린더(일정)와 오늘 업무를 하나의 창에 표시.

    Layout (top → bottom):
      header bar  (drag / scale / close)
      calendar    (compact QCalendarWidget)
      quick-add   (일정 빠른 추가 입력)
      entry list  (선택날짜 일정 + 오늘 업무/지시 — 섹션 구분)
    """

    def __init__(self, app: QWidget):
        super().__init__(app, t("widget_mode.panel_title", "일정 · 업무"), "◈")
        self.on_date_changed: Callable[[], None] | None = None
        self.on_month_changed: Callable[[], None] | None = None
        self.on_add_schedule_with_text_requested: Callable[[QDate, str], None] | None = None
        self._marked_dates: dict[str, int] = {}
        self._last_calendar_state_key: tuple | None = None
        self._last_entry_render_key: tuple | None = None
        self._last_entry_count: int = 0
        self._rendered_entries: list[_WidgetEntry] = []
        self._calendar_visible = True  # 캘린더 표시 상태

        self.calendar = _WidgetCalendar(self.content_container)
        self._apply_calendar_geometry(1.0)
        self.calendar.setNavigationBarVisible(True)
        self.calendar.setLocale(QLocale())
        self.calendar.setFirstDayOfWeek(QLocale().firstDayOfWeek())
        self.calendar.selectionChanged.connect(self._on_date_changed)
        self.calendar.currentPageChanged.connect(lambda *_: self._on_month_changed())
        self.calendar.activated.connect(self._on_calendar_double_clicked)
        self.content_layout.addWidget(self.calendar)
        self.meta_bar = QFrame(self.content_container)
        self.meta_bar.setObjectName("widget_mode_meta_bar")
        self.meta_layout = QHBoxLayout(self.meta_bar)
        self.meta_layout.setContentsMargins(0, 0, 0, 0)
        self.meta_layout.setSpacing(6)
        self.context_chip = QLabel("", self.meta_bar)
        self.context_chip.setObjectName("widget_mode_context_chip")
        self.count_chip = QLabel("", self.meta_bar)
        self.count_chip.setObjectName("widget_mode_count_chip")
        self.meta_hint = QLabel("", self.meta_bar)
        self.meta_hint.setObjectName("widget_mode_meta_hint")
        self.meta_layout.addWidget(self.context_chip)
        self.meta_layout.addWidget(self.count_chip)
        self.meta_layout.addStretch(1)
        self.meta_layout.addWidget(self.meta_hint)
        self.content_layout.addWidget(self.meta_bar)

        self.list_widget = _EntryListWidget(self.content_container)
        self.content_layout.addWidget(self.list_widget, 1)

        # 캘린더 토글 버튼 연결
        self.toggle_calendar_btn.setVisible(True)
        self.toggle_calendar_btn.clicked.connect(self._toggle_calendar_visibility)

    # ── Size ──────────────────────────────────────────────────────
    def minimumSizeHint(self) -> QSize:
        return QSize(300, 480)

    @staticmethod
    def _calendar_height_bounds(scale: float) -> tuple[int, int]:
        s = max(0.75, float(scale or 1.0))
        min_height = max(266, int(round(272 * s)))
        max_height = max(min_height, int(round(356 * s)))
        return min_height, max_height

    def _apply_calendar_geometry(self, scale: float) -> None:
        min_height, max_height = self._calendar_height_bounds(scale)
        if self.calendar.minimumHeight() != min_height:
            self.calendar.setMinimumHeight(min_height)
        if self.calendar.maximumHeight() != max_height:
            self.calendar.setMaximumHeight(max_height)

    # ── Date helpers ─────────────────────────────────────────────
    def selected_date(self) -> QDate:
        return self.calendar.selectedDate()

    def visible_month_bounds(self) -> tuple[QDate, QDate]:
        first = QDate(self.calendar.yearShown(), self.calendar.monthShown(), 1)
        return first, first.addMonths(1).addDays(-1)

    # ── Resize handling ───────────────────────────────────────────
    def resizeEvent(self, event) -> None:
        """패널 리사이징 시 캘린더 높이 동적 조정"""
        super().resizeEvent(event)
        if self.content_container and self.list_widget:
            # 현재 창 높이 기반 스케일 계산
            total_height = self.content_container.height()
            if total_height > 0:
                # 기준선 300px에서 1.0 스케일
                scale = max(0.75, min(1.5, (total_height / 300)))
                self._apply_calendar_geometry(scale)

    # ── Calendar visibility ───────────────────────────────────────
    def _toggle_calendar_visibility(self) -> None:
        """캘린더 표시/숨김 토글"""
        self._calendar_visible = not self._calendar_visible
        self.calendar.setVisible(self._calendar_visible)
        self.meta_bar.setVisible(self._calendar_visible)

        # 버튼 텍스트 업데이트
        self.toggle_calendar_btn.setText("📅" if self._calendar_visible else "📄")
        self.toggle_calendar_btn.setToolTip(
            t("widget_mode.show_calendar", "캘린더 표시")
            if not self._calendar_visible
            else t("widget_mode.hide_calendar", "캘린더 숨김")
        )

    # ── Internal signals → callbacks ─────────────────────────────
    def _on_date_changed(self) -> None:
        if self.on_date_changed is not None:
            self.on_date_changed()

    def _on_month_changed(self) -> None:
        if self.on_month_changed is not None:
            self.on_month_changed()

    def _update_meta_bar(self, *, item_count: int | None = None) -> None:
        if item_count is not None:
            self._last_entry_count = max(0, int(item_count))
        selected = self.selected_date()
        self.context_chip.setText(_relative_day_label(selected))
        self.count_chip.setText(
            t("widget_mode.item_count_chip", "{count} items", count=self._last_entry_count)
        )
        if self._last_entry_count > 0:
            self.meta_hint.setText(
                t("widget_mode.quick_hint_actions", "Tap a card for quick actions")
            )
        else:
            self.meta_hint.setText(t("widget_mode.quick_hint", "Selected day schedule and work"))

    # ── Calendar marks ───────────────────────────────────────────
    def set_calendar_marks(
        self,
        marked_dates: "dict[QDate, int] | set[QDate]",
        *,
        today: QDate,
        selected: QDate,
    ) -> None:
        if isinstance(marked_dates, dict):
            normalized_marks = {
                k.toString("yyyy-MM-dd"): max(1, int(v))
                for k, v in marked_dates.items()
                if isinstance(k, QDate) and k.isValid()
            }
        else:
            normalized_marks = {
                k.toString("yyyy-MM-dd"): 1
                for k in marked_dates
                if isinstance(k, QDate) and k.isValid()
            }
        state_key = (
            today.toString("yyyy-MM-dd") if isinstance(today, QDate) and today.isValid() else "",
            selected.toString("yyyy-MM-dd")
            if isinstance(selected, QDate) and selected.isValid()
            else "",
            tuple(sorted(normalized_marks.items())),
        )
        if state_key == self._last_calendar_state_key:
            return
        self._last_calendar_state_key = state_key
        self._marked_dates = dict(normalized_marks)
        self.calendar.set_visual_state(self.theme_tokens(), self._marked_dates, today, selected)
        self._update_meta_bar()

    def _on_calendar_double_clicked(self, date: QDate) -> None:
        if self.on_add_schedule_with_text_requested:
            self.on_add_schedule_with_text_requested(date, "")

    def _refresh_locale_texts(self) -> None:
        self.title_label.setText(t("widget_mode.panel_title", "일정 · 업무"))
        self.restore_btn.setToolTip(t("widget_mode.back_to_main", "메인 화면 보기"))
        self.close_btn.setToolTip(t("widget_mode.close", "위젯 닫기"))
        self.calendar.setLocale(QLocale())
        self.calendar.setFirstDayOfWeek(QLocale().firstDayOfWeek())
        self.calendar._refresh_navigation_texts()
        self._update_meta_bar()

    def _handle_widget_resize(self) -> None:
        self._last_entry_render_key = None
        if self._rendered_entries:
            self.render_entries(list(self._rendered_entries))

    # ── Palette ──────────────────────────────────────────────────
    def apply_palette(self, scale: float = 1.0) -> None:
        _FloatingWidgetBase.apply_palette(self, scale)
        tokens = self.theme_tokens()
        self._apply_calendar_geometry(scale)
        self._refresh_locale_texts()
        chip_ss = _widget_mode_chip_stylesheet(tokens, scale=scale)
        self.context_chip.setStyleSheet(chip_ss)
        self.count_chip.setStyleSheet(chip_ss)
        self.meta_hint.setStyleSheet(
            f"color: {tokens.get('text_faint', '#6a7290')};"
            f" font-size: {8.0 * scale}pt;"
            " font-weight: 500;"
            " letter-spacing: 0.2px;"
        )
        self.calendar.set_visual_state(
            tokens, self._marked_dates, QDate.currentDate(), self.selected_date()
        )
        self._update_meta_bar()

    # ── Entry rendering ──────────────────────────────────────────
    def render_entries(self, entries: list[_WidgetEntry]) -> None:
        self._rendered_entries = list(entries)
        tokens = self._theme_cache or self.theme_tokens()
        item_count = sum(1 for entry in entries if not entry.is_section)
        render_key = (
            int(round(self._last_scale * 100)),
            max(self.width(), self.list_widget.width(), 0),
            tokens.get("accent"),
            tokens.get("panel_bg"),
            tokens.get("section_bg"),
            tokens.get("section_bg_alt"),
            tokens.get("hero_border"),
            tokens.get("text_primary"),
            tokens.get("text_secondary"),
            tuple(
                (
                    entry.title,
                    entry.subtitle,
                    bool(entry.is_section),
                    id(entry.callback),
                    id(entry.double_click_callback),
                    id(entry.delete_callback),
                    id(entry.context_menu_callback),
                )
                for entry in entries
            ),
        )
        if render_key == self._last_entry_render_key:
            return
        self._last_entry_render_key = render_key
        self._update_meta_bar(item_count=item_count)
        self.list_widget.set_entries(
            entries,
            tokens,
            t("widget_mode.empty_panel", "정돈된 상태입니다."),
            scale=self._last_scale,
        )
