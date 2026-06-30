"""Overlay date-card widget."""

from __future__ import annotations

import re

from PyQt6.QtCore import QDate, QDateTime, QPoint, QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.overlay_base import (
    _DLG_SS,
    _apply_align_tags,
    _apply_span,
    _BaseOverlayWidget,
    _GripFrame,
    _strftime_to_qt,
)
from calendar_app.presentation.widgets.overlay_color_utils import _to_rgba_str
from calendar_app.shared.color_utils import parse_css_alpha_to_unit
from calendar_app.shared.theme_snapshot import build_theme_snapshot
from calendar_app.shared.ui_tokens import get_ui_tokens

_RGBA_COLOR_RE = re.compile(
    r"^rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*([0-9]*\.?[0-9]+)\s*\)$",
    re.IGNORECASE,
)


def _datecard_qcolor(value: object, fallback: QColor | str) -> QColor:
    if isinstance(value, QColor):
        color = QColor(value)
    else:
        raw = str(value or "").strip()
        match = _RGBA_COLOR_RE.match(raw)
        if match:
            r, g, b, alpha_raw = match.groups()
            try:
                alpha = max(0.0, min(1.0, parse_css_alpha_to_unit(alpha_raw)))
            except Exception:
                alpha = 1.0
            color = QColor(int(r), int(g), int(b), int(round(alpha * 255)))
        else:
            color = QColor(raw)
    if color.isValid():
        return QColor(color)
    fallback_color = fallback if isinstance(fallback, QColor) else QColor(str(fallback))
    return QColor(fallback_color) if fallback_color.isValid() else QColor("#fcfdfe")


def _datecard_contrast_text(
    background: QColor | str, light: QColor | str, dark: QColor | str
) -> QColor:
    bg = _datecard_qcolor(background, dark)
    light_q = _datecard_qcolor(light, "#fcfdfe")
    dark_q = _datecard_qcolor(dark, "#101418")
    return QColor(dark_q if bg.lightnessF() >= 0.62 else light_q)


def _datecard_theme_bundle(settings=None) -> dict:
    snapshot = build_theme_snapshot(settings=settings)
    tokens = get_ui_tokens(settings=settings, snapshot=snapshot)

    accent = _datecard_qcolor(tokens.get("accent"), snapshot.theme_color)

    saturday = QColor(accent)
    saturday = saturday.lighter(135)

    sunday = _datecard_qcolor(
        tokens.get("danger_hex"), snapshot.ui_palette.get("danger_hex", "#ff7070")
    )

    text = _datecard_qcolor(
        tokens.get("text_primary"), snapshot.text_palette.get("text_primary", "#fcfdfe")
    )

    bg = _datecard_qcolor(
        snapshot.panel_base_color or tokens.get("bg_main"), tokens.get("bg_main", "#101418")
    )

    return {
        "accent": accent,
        "saturday": saturday,
        "sunday": sunday,
        "text": text,
        "text_rgba": _to_rgba_str(text, 252),
        "bg_rgba": _to_rgba_str(bg, 214),
        "border_rgba": _to_rgba_str(accent, 72),
    }


def _week_strip_label_style(color: QColor | str, *, bold: bool = False) -> str:
    qcolor = _datecard_qcolor(color, "#fcfdfe")
    weight = "bold" if bold else "normal"
    return (
        "background:transparent; border:none; "
        f"color:{qcolor.name(QColor.NameFormat.HexRgb)}; font-weight:{weight};"
    )


def _weekday_labels_mon_first() -> list[str]:
    return [
        t("weekday.mon", "월"),
        t("weekday.tue", "화"),
        t("weekday.wed", "수"),
        t("weekday.thu", "목"),
        t("weekday.fri", "금"),
        t("weekday.sat", "토"),
        t("weekday.sun", "일"),
    ]


# ---------------------------------------------------------------------------
# Mini calendar grid widget (QPainter-based)
# ---------------------------------------------------------------------------


class _CalendarGridWidget(QWidget):
    """Draws a compact monthly calendar grid using QPainter."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(False)

        self._today: QDate = QDate.currentDate()
        self._view_year: int = self._today.year()
        self._view_month: int = self._today.month()
        theme = _datecard_theme_bundle()
        self._fg_color: QColor = QColor(theme["text"])
        self._font_family: str = ""
        self._accent_color: QColor = QColor(theme["accent"])
        self._sat_color: QColor = QColor(theme["saturday"])
        self._sun_color: QColor = QColor(theme["sunday"])

    # ------------------------------------------------------------------ API

    def update_date(
        self,
        today: QDate,
        year: int,
        month: int,
        fg: QColor,
        font_family: str,
        accent: QColor | None = None,
        saturday: QColor | None = None,
        sunday: QColor | None = None,
    ) -> None:
        self._today = today
        self._view_year = year
        self._view_month = month
        self._fg_color = fg
        self._font_family = font_family
        if accent is not None and accent.isValid():
            self._accent_color = QColor(accent)
        if saturday is not None and saturday.isValid():
            self._sat_color = QColor(saturday)
        if sunday is not None and sunday.isValid():
            self._sun_color = QColor(sunday)
        self.update()

    # ------------------------------------------------------------------ paint

    def paintEvent(self, _event) -> None:  # noqa: N802
        now_y, now_m = self._view_year, self._view_month
        today = self._today

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H = self.width(), self.height()
        pad_x, pad_y = 10, 8
        inner_w = W - pad_x * 2

        # ---- header: "2026년 3월" (or "March 2026" for non-ko)
        hdr_h = max(18, H // 7)
        hdr_font = QFont(self._font_family, max(8, hdr_h - 4))
        hdr_font.setBold(True)
        p.setFont(hdr_font)

        month_name = QDate(now_y, now_m, 1).toString("MMMM")
        hdr_text = f"{now_y}. {now_m:02d}  {month_name}"
        header_color = QColor(self._fg_color)
        header_color.setAlpha(230)
        p.setPen(header_color)
        hdr_rect = QRect(pad_x, pad_y, inner_w, hdr_h)
        p.drawText(hdr_rect, Qt.AlignmentFlag.AlignCenter, hdr_text)

        # ---- day-of-week row
        dow_y = pad_y + hdr_h + 2
        dow_h = max(12, hdr_h - 4)
        cell_w = inner_w / 7
        dow_font = QFont(self._font_family, max(7, dow_h - 3))
        dow_labels = _weekday_labels_mon_first()
        for i, label in enumerate(dow_labels):
            cx = pad_x + i * cell_w + cell_w / 2
            cy = dow_y
            cell_rect = QRectF(cx - cell_w / 2, cy, cell_w, dow_h)
            if i == 5:  # 토 = Sat
                p.setPen(self._sat_color)
            elif i == 6:  # 일 = Sun
                p.setPen(self._sun_color)
            else:
                dim = QColor(self._fg_color)
                dim.setAlpha(140)
                p.setPen(dim)
            p.setFont(dow_font)
            p.drawText(cell_rect, Qt.AlignmentFlag.AlignCenter, label)

        # ---- date cells
        # ISO: week starts Monday (dow 0=Mon..6=Sun)
        first_day = QDate(now_y, now_m, 1)
        days_in_month = first_day.daysInMonth()
        # dayOfWeek(): 1=Mon..7=Sun → 0-based col
        start_col = first_day.dayOfWeek() - 1  # 0..6

        cell_h = max(14, dow_h + 1)
        date_font = QFont(self._font_family, max(7, cell_h - 5))
        today_font = QFont(self._font_family, max(7, cell_h - 5))
        today_font.setBold(True)

        date_area_y = dow_y + dow_h + 3
        available_h = H - date_area_y - pad_y
        rows = (start_col + days_in_month + 6) // 7
        if rows < 1:
            rows = 1
        cell_h = max(12, available_h // max(rows, 4))

        for day in range(1, days_in_month + 1):
            abs_col = (start_col + day - 1) % 7
            abs_row = (start_col + day - 1) // 7

            cx = pad_x + abs_col * cell_w + cell_w / 2
            cy = date_area_y + abs_row * cell_h + cell_h / 2

            is_today = today.year() == now_y and today.month() == now_m and today.day() == day
            is_sat = abs_col == 5
            is_sun = abs_col == 6

            if is_today:
                # filled accent circle
                r = min(cell_w, cell_h) / 2 - 1
                p.setBrush(QBrush(self._accent_color))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
                p.setFont(today_font)
                p.setPen(_datecard_contrast_text(self._accent_color, self._fg_color, "#101418"))
            else:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setFont(date_font)
                if is_sat:
                    c = QColor(self._sat_color)
                    c.setAlpha(200)
                    p.setPen(c)
                elif is_sun:
                    c = QColor(self._sun_color)
                    c.setAlpha(200)
                    p.setPen(c)
                else:
                    c = QColor(self._fg_color)
                    c.setAlpha(210)
                    p.setPen(c)

            cell_rect = QRectF(cx - cell_w / 2, cy - cell_h / 2, cell_w, cell_h)
            p.drawText(cell_rect, Qt.AlignmentFlag.AlignCenter, str(day))

        p.end()


# ---------------------------------------------------------------------------
# Date-Card overlay widget
# ---------------------------------------------------------------------------


class OverlayDateCardWidget(_BaseOverlayWidget):
    _PREFIX = "overlay_date_card"
    _DEFAULT_BG_RGBA = "#d6101418"
    _DEFAULT_BORDER_RGBA = "#20ffffff"

    _STYLES = [
        ("default", "Default - Weekday/Day/Date Vertical"),
        ("compact", "Compact - Day + Date"),
        ("horizontal", "Horizontal - Weekday + Day"),
        ("dday", "D+N - Day of Year"),
        ("fulldate", "Full Date - Large YYYY.MM.DD"),
        ("minimal", "Minimal - No Border"),
        ("pill", "Pill - Rounded Wide Shape"),
        ("week_strip", "Week Strip - Horizontal Date Row"),
        ("big_day", "Big Day - Large Day Number"),
        ("neon", "Neon - Thick Border"),
        # ── new styles ──────────────────────────────────────────────────────
        ("glass", "Glass - Frosted Overlay"),
        ("retro", "Retro - Double Border"),
        ("banner", "Banner - Left Accent"),
        ("mini_grid", "Mini Grid - Monthly Calendar"),
    ]
    _STYLE_I18N_PREFIX = "widget.datecard"
    _TEMPLATE_KEY = "dc_template"

    _DLG_SS = _DLG_SS

    def _settings_prefix(self):
        return self._PREFIX

    def _default_font_size(self):
        return 30

    def _theme_bundle(self) -> dict:
        settings = getattr(getattr(self, "owner", None), "settings", None)
        return _datecard_theme_bundle(settings=settings)

    def text_color_rgba(self) -> str:
        stored = self._get("text_color_rgba", None)
        if stored not in (None, "", "None"):
            return str(stored)
        return self._theme_bundle()["text_rgba"]

    def bg_color_rgba(self) -> str:
        stored = self._get("bg_color_rgba", None)
        if stored not in (None, "", "None"):
            return str(stored)
        return self._theme_bundle()["bg_rgba"]

    def border_color_rgba(self) -> str:
        stored = self._get("border_color_rgba", None)
        if stored not in (None, "", "None"):
            return str(stored)
        return self._theme_bundle()["border_rgba"]

    # ------------------------------------------------------------------ face

    def _build_face(self) -> QFrame:
        frame = _GripFrame(self)
        frame.setObjectName("dateCardFace")
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(20, 12, 20, 12)
        outer.setSpacing(2)
        outer.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Basic labels
        self._labels = {
            "weekday": QLabel("", frame),
            "day": QLabel("", frame),
            "date": QLabel("", frame),
            "doy": QLabel("", frame),
        }

        # Horizontal row (horizontal style)
        self._h_row = QWidget(frame)
        self._h_row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._h_row.setVisible(False)
        h_layout = QHBoxLayout(self._h_row)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(12)
        self._h_weekday = QLabel("", self._h_row)
        self._h_day = QLabel("", self._h_row)
        h_layout.addWidget(self._h_weekday)
        h_layout.addWidget(self._h_day)

        # Week-strip row — improved: one cell per day-of-week
        self._ws_row = QWidget(frame)
        self._ws_row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._ws_row.setVisible(False)
        ws_layout = QHBoxLayout(self._ws_row)
        ws_layout.setContentsMargins(0, 0, 0, 0)
        ws_layout.setSpacing(4)
        # 7 day cells for the improved week-strip
        _dow_names = ["월", "화", "수", "목", "금", "토", "일"]
        self._ws_cells: list[QLabel] = []
        for name in _dow_names:
            lbl = QLabel(name, self._ws_row)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            ws_layout.addWidget(lbl)
            self._ws_cells.append(lbl)

        # Legacy ws labels (kept for template var compatibility)
        self._ws_weekday = QLabel("", frame)
        self._ws_weekday.setVisible(False)
        self._ws_day = QLabel("", frame)
        self._ws_day.setVisible(False)
        self._ws_date = QLabel("", frame)
        self._ws_date.setVisible(False)
        self._ws_sep1 = QLabel("·", frame)
        self._ws_sep1.setVisible(False)
        self._ws_sep2 = QLabel("·", frame)
        self._ws_sep2.setVisible(False)

        # Mini-grid canvas
        self._grid_widget = _CalendarGridWidget(frame)
        self._grid_widget.setVisible(False)
        self._grid_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Template label
        self._template_label = QLabel("", frame)
        self._template_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._template_label.setWordWrap(True)
        self._template_label.setTextFormat(Qt.TextFormat.RichText)
        self._template_label.setVisible(False)

        outer.addWidget(self._h_row)
        outer.addWidget(self._ws_row)
        for lbl in self._labels.values():
            outer.addWidget(lbl)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._grid_widget)
        outer.addWidget(self._template_label)

        if not hasattr(self, "_dc_timer"):
            self._dc_timer = QTimer(self)
            self._dc_timer.timeout.connect(self._tick)
        if not self._dc_timer.isActive():
            self._dc_timer.start(60000)
        self._tick()
        return frame

    # ------------------------------------------------------------------ tick

    def _tick(self):
        if self._resizing and not self._measuring:
            return
        now = QDateTime.currentDateTime()
        style = self.display_style()

        if style == "mini_grid":
            self._template_label.setVisible(False)
            self._h_row.setVisible(False)
            self._ws_row.setVisible(False)
            for lbl in self._labels.values():
                lbl.setVisible(False)
            self._grid_widget.setVisible(True)
            fg = self._parse_fg_color()
            bundle = self._theme_bundle()
            self._grid_widget.update_date(
                now.date(),
                now.date().year(),
                now.date().month(),
                fg,
                self.font_family(),
                bundle["accent"],
                bundle["saturday"],
                bundle["sunday"],
            )
            return

        self._grid_widget.setVisible(False)

        if self._is_template_mode():
            self._set_template_label(self._resolve_dc_template(self._widget_template(), now))
            for w in [self._h_row, self._ws_row] + list(self._labels.values()):
                w.setVisible(False)
        else:
            self._template_label.setVisible(False)
            self._update_basic_display(now)

    def _parse_fg_color(self) -> QColor:
        """Return current text colour as QColor (for QPainter use)."""
        from calendar_app.presentation.widgets.overlay_color_utils import _parse_rgba

        fg_rgba = (
            self.text_color_rgba()
            if hasattr(self, "text_color_rgba")
            else self._theme_bundle()["text_rgba"]
        )
        c, _ = _parse_rgba(fg_rgba)
        return c

    # ------------------------------------------------------------------ display

    def _update_basic_display(self, now: QDateTime):
        style = self.display_style()
        w = now.toString("dddd")
        d = now.toString("dd")
        dt = now.toString("yyyy.MM.dd")
        doy = f"D+{now.date().dayOfYear()}"

        self._h_row.setVisible(style == "horizontal")
        self._labels["doy"].setVisible(style == "dday")
        self._labels["weekday"].setVisible(
            style in ("default", "minimal", "big_day", "neon", "dday", "glass", "retro", "banner")
        )
        self._labels["day"].setVisible(
            style
            in (
                "default",
                "minimal",
                "big_day",
                "neon",
                "compact",
                "pill",
                "glass",
                "retro",
                "banner",
            )
        )
        self._labels["date"].setVisible(
            style
            in (
                "default",
                "minimal",
                "big_day",
                "neon",
                "compact",
                "pill",
                "dday",
                "fulldate",
                "horizontal",
                "glass",
                "retro",
                "banner",
            )
        )

        self._labels["weekday"].setText(w)
        self._labels["day"].setText(d)
        self._labels["date"].setText(dt)
        self._labels["doy"].setText(doy)
        self._h_weekday.setText(w)
        self._h_day.setText(d)

        # ---- improved week_strip: 7-cell row with today highlighted
        is_ws = style == "week_strip"
        self._ws_row.setVisible(is_ws)
        if is_ws:
            today_col = now.date().dayOfWeek() - 1  # 0=Mon…6=Sun
            bundle = self._theme_bundle()
            for i, lbl in enumerate(self._ws_cells):
                if i == today_col:
                    lbl.setStyleSheet(_week_strip_label_style(bundle["accent"], bold=True))
                elif i == 5:  # 토
                    lbl.setStyleSheet(_week_strip_label_style(bundle["saturday"]))
                elif i == 6:  # 일
                    lbl.setStyleSheet(_week_strip_label_style(bundle["sunday"]))
                else:
                    lbl.setStyleSheet(_week_strip_label_style(bundle["text"]))

    # ------------------------------------------------------------------ appearance

    def _apply_appearance(self) -> None:
        self._apply_base_appearance()
        size = self.font_size()
        family = self.font_family()
        style = self.display_style()

        # mini_grid: fix canvas size and bail out
        if style == "mini_grid":
            cell_px = max(16, size - 4)
            grid_w = cell_px * 7 + 22
            grid_h = int(grid_w * 0.76)
            self._grid_widget.setMinimumSize(grid_w, grid_h)
            self._grid_widget.setMaximumSize(grid_w + 40, grid_h + 20)
            self._tick()
            return

        day_size = size + 10 if style == "big_day" else size
        date_size = max(8, size - 12)
        bold_f = QFont(family, day_size)
        bold_f.setBold(True)
        small_f = QFont(family, date_size)
        ws_f = QFont(family, max(8, size - 14))

        for lbl in [self._labels["day"], self._h_day, self._labels["doy"]]:
            lbl.setFont(bold_f)
        for lbl in [self._labels["date"], self._labels["weekday"], self._h_weekday]:
            lbl.setFont(small_f)
        for lbl in self._ws_cells:
            lbl.setFont(ws_f)

        self._template_label.setFont(QFont(family, size))

        fg_css = f"color: {self._text_color_str()};"
        # base labels
        for lbl in list(self._labels.values()) + [
            self._h_day,
            self._h_weekday,
            self._template_label,
        ]:
            lbl.setStyleSheet(f"background:transparent; border:none; {fg_css}")
        # ws_cells styled per-tick (don't override here)
        self._tick()

    def _refresh_face(self):
        self._tick()

    # ------------------------------------------------------------------ template engine

    _DEFAULT_TEMPLATE = "{weekday|size=13}\n{day|size=36|bold}\n{date|size=11}"

    def _resolve_dc_template(self, template: str, now_dt: QDateTime) -> str:
        from calendar_app.presentation.widgets.overlay_base import (
            _inject_global_lh,
            _protect_align_tags,
        )

        template = _inject_global_lh(template)
        template = _protect_align_tags(template)

        q = now_dt.date()
        _en = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        # ---- base values
        vals: dict[str, str] = {
            "weekday": now_dt.toString("dddd"),
            "day": now_dt.toString("d"),
            "month": now_dt.toString("M"),
            "year": now_dt.toString("yyyy"),
            "doy": f"D+{q.dayOfYear()}",
            "date": now_dt.toString("yyyy.MM.dd"),
            # ── new variables ──────────────────────────────────────────────
            "week_num": str(q.weekNumber()[0]),
            "quarter": f"Q{(q.month() - 1) // 3 + 1}",
            "days_left_month": str(q.daysInMonth() - q.day()),
            "days_in_month": str(q.daysInMonth()),
            "yesterday": now_dt.addDays(-1).toString("yyyy.MM.dd"),
            "tomorrow": now_dt.addDays(1).toString("yyyy.MM.dd"),
        }

        # numeric vals for conditionals
        num_vals = {}
        for k, v in vals.items():
            stripped = v.replace("D+", "").replace("Q", "")
            if stripped.lstrip("-").isdigit():
                num_vals[k] = int(stripped)
            else:
                num_vals[k] = v
        template = self._process_conditionals(template, num_vals)

        def _replace(m: re.Match) -> str:
            inner = m.group(1).split("|")
            key, hints = inner[0].strip(), inner[1:]
            if key.startswith("date:"):
                val = now_dt.toString(_strftime_to_qt(key[5:]))
            elif key == "weekday:short":
                val = now_dt.toString("ddd")
            elif key == "weekday:en":
                val = _en[(q.dayOfWeek() - 1) % 7]
            else:
                val = str(vals.get(key, ""))
            return _apply_span(val, hints)

        return _apply_align_tags(re.sub(r"\{([^}]+)\}", _replace, template))

    # ------------------------------------------------------------------ settings

    def _open_settings(self):
        self._open_standard_settings_dialog(
            title=t("widget.datecard.settings_title", "Date Card Settings"),
            has_template=True,
            default_template=self._DEFAULT_TEMPLATE,
            template_hint=t(
                "widget.datecard.template_hint",
                "{day}, {month}, {year}, {weekday}, {doy}, "
                "{week_num}, {quarter}, {days_left_month}, "
                "{days_in_month}, {yesterday}, {tomorrow}",
            ),
            preview_render_fn=lambda tmpl: self._resolve_dc_template(
                tmpl, QDateTime.currentDateTime()
            ),
        )

    def _build_context_menu(self, menu: QMenu):
        menu.addAction(
            t("widget.datecard.settings", "Date Card Settings..."),
            self._open_settings,
        )

    def _action_reset_position(self):
        self.center_on_owner()

    def apply_initial_settings(self):
        self._tick()
        self._apply_and_resize()
        self.restore_position(QPoint(-200, 220))
        if self.is_enabled():
            self._show_with_correct_size()
