"""Overlay digital clock widget."""

from __future__ import annotations

import re

from PyQt6.QtCore import QDateTime, QPoint, Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QLabel, QMenu, QVBoxLayout

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.overlay_base import (
    _DLG_SS,
    _apply_align_tags,
    _apply_span,
    _BaseOverlayWidget,
    _GripFrame,
    _strftime_to_qt,
)


class OverlayClockWidget(_BaseOverlayWidget):
    _PREFIX = "overlay_clock"
    _DEFAULT_BG_RGBA = "#d6101418"
    _DEFAULT_BORDER_RGBA = "#20ffffff"

    _STYLES = [
        ("default", "Default - Center Block"),
        ("minimal", "Minimal - No Border"),
        ("pill", "Pill - Rounded Corners"),
        ("neon", "Neon - Thick Border"),
        ("multiline", "Multiline - Date + Time"),
        ("digital", "Digital - Wider Letter Spacing"),
        ("retro", "Retro - AM/PM + 12-hour"),
        ("split", "Split - Hour/Minute Divider"),
        ("compact", "Compact - Smaller Padding"),
        ("glass", "Glass - Transparent Look"),
    ]
    _STYLE_I18N_PREFIX = "widget.clock"

    _DLG_SS = _DLG_SS

    def _settings_prefix(self):
        return self._PREFIX

    def _default_font_size(self):
        return 32

    def _build_face(self) -> QFrame:
        frame = _GripFrame(self)
        frame.setObjectName("clockFace")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.setSpacing(0)

        # Legacy labels (kept for non-template styles if needed, but mostly hidden now)
        self._ampm_label = QLabel("", frame)
        self._ampm_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ampm_label.setVisible(False)
        layout.addWidget(self._ampm_label)

        self._time_label = QLabel("--:--:--", frame)
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._time_label.setWordWrap(False)
        layout.addWidget(self._time_label)

        self._split_sep = QFrame(frame)
        self._split_sep.setFrameShape(QFrame.Shape.HLine)
        self._split_sep.setVisible(False)
        layout.addWidget(self._split_sep)

        self._split_bottom = QLabel("", frame)
        self._split_bottom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._split_bottom.setVisible(False)
        layout.addWidget(self._split_bottom)

        self._date_label = QLabel("", frame)
        self._date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._date_label.setWordWrap(False)
        layout.addWidget(self._date_label)

        # Main template label
        self._template_label = QLabel("", frame)
        self._template_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._template_label.setWordWrap(True)
        self._template_label.setTextFormat(Qt.TextFormat.RichText)
        self._template_label.setVisible(False)
        layout.addWidget(self._template_label)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._tick()
        return frame

    # ------------------------------------------------------------------
    # Timezone support
    # ------------------------------------------------------------------

    def _timezone_items(self) -> list[tuple[str, int | None, str]]:
        return [
            (t("widget.clock.tz.local", "Local (System)"), None, "local"),
            (t("widget.clock.tz.utc_0", "UTC+0  London"), 0, "UTC"),
            (t("widget.clock.tz.utc_1", "UTC+1  Paris/Berlin"), 60, "CET"),
            (t("widget.clock.tz.utc_2", "UTC+2  Cairo/Helsinki"), 120, "EET"),
            (t("widget.clock.tz.utc_3", "UTC+3  Moscow/Riyadh"), 180, "MSK"),
            (t("widget.clock.tz.utc_4", "UTC+4  Dubai/Baku"), 240, "GST"),
            (t("widget.clock.tz.utc_5", "UTC+5  Karachi/Tashkent"), 300, "PKT"),
            (t("widget.clock.tz.utc_5_30", "UTC+5:30 Mumbai/New Delhi"), 330, "IST"),
            (t("widget.clock.tz.utc_6", "UTC+6  Dhaka/Almaty"), 360, "BST"),
            (t("widget.clock.tz.utc_7", "UTC+7  Bangkok/Hanoi/Jakarta"), 420, "ICT"),
            (t("widget.clock.tz.utc_8", "UTC+8  Beijing/Singapore/Seoul"), 480, "CST"),
            (t("widget.clock.tz.utc_9", "UTC+9  Tokyo/Seoul"), 540, "JST"),
            (t("widget.clock.tz.utc_9_30", "UTC+9:30 Adelaide"), 570, "ACST"),
            (t("widget.clock.tz.utc_10", "UTC+10 Sydney/Vladivostok"), 600, "AEST"),
            (t("widget.clock.tz.utc_11", "UTC+11 Solomon/Magadan"), 660, "ANAT"),
            (t("widget.clock.tz.utc_12", "UTC+12 Auckland/Fiji"), 720, "NZST"),
            (t("widget.clock.tz.utc_minus_3", "UTC-3  Buenos Aires/Sao Paulo"), -180, "BRT"),
            (t("widget.clock.tz.utc_minus_4", "UTC-4  New York (EDT)/Caracas"), -240, "EDT"),
            (t("widget.clock.tz.utc_minus_5", "UTC-5  New York (EST)/Bogota"), -300, "EST"),
            (t("widget.clock.tz.utc_minus_6", "UTC-6  Chicago/Mexico City"), -360, "CST"),
            (t("widget.clock.tz.utc_minus_7", "UTC-7  Denver/Phoenix"), -420, "MST"),
            (t("widget.clock.tz.utc_minus_8", "UTC-8  Los Angeles (PST)"), -480, "PST"),
            (t("widget.clock.tz.utc_minus_9", "UTC-9  Alaska"), -540, "AKST"),
            (t("widget.clock.tz.utc_minus_10", "UTC-10 Hawaii"), -600, "HST"),
        ]

    def _tz_offset_minutes(self) -> int | None:
        raw = self._get("tz_offset_mins")
        if raw is None or str(raw) == "None":
            return None
        try:
            return int(raw)
        except (ValueError, TypeError):
            return None

    def _now_tz(self) -> QDateTime:
        offset = self._tz_offset_minutes()
        if offset is None:
            return QDateTime.currentDateTime()
        from PyQt6.QtCore import QTimeZone

        tz = QTimeZone(offset * 60)
        return QDateTime.currentDateTime().toTimeZone(tz)

    def _tz_label(self) -> str:
        offset = self._tz_offset_minutes()
        if offset is None:
            return ""
        for _label, _off, _hint in self._timezone_items():
            if _off == offset:
                return _hint
        sign = "+" if offset >= 0 else "-"
        h, m = divmod(abs(offset), 60)
        return f"UTC{sign}{h}" if m == 0 else f"UTC{sign}{h}:{m:02d}"

    def _set_tz(self, offset_mins):
        self._set("tz_offset_mins", offset_mins)
        self._tick()
        self._apply_and_resize()

    def _display_format(self) -> str:
        raw = str(self._get("format", "hms") or "hms").lower()
        return "HH:mm" if raw == "hm" else "HH:mm:ss"

    def _tick(self):
        if self._resizing and not self._measuring:
            return
        now = self._now_tz()

        if self._is_template_mode():
            html = self._resolve_clock_template(self._widget_template(), now, self._tz_label())
            self._set_template_label(html)
            self._ampm_label.setVisible(False)
            self._time_label.setVisible(False)
            self._split_sep.setVisible(False)
            self._split_bottom.setVisible(False)
            self._date_label.setVisible(False)
            return

        self._template_label.setVisible(False)
        self._time_label.setVisible(True)

        style = self.display_style()
        tz_lbl = self._tz_label()
        tz_suffix = f"  [{tz_lbl}]" if tz_lbl else ""

        if style == "retro":
            self._time_label.setText(now.toString("hh:mm:ss"))
            self._ampm_label.setText(now.toString("AP") + tz_suffix)
            self._split_bottom.setText("")
            self._date_label.setText("")
        elif style == "split":
            self._time_label.setText(now.toString("HH:mm"))
            self._split_bottom.setText(now.toString(":ss  ddd") + tz_suffix)
            self._ampm_label.setText("")
            self._date_label.setText("")
        elif style == "multiline":
            fmt = self._display_format()
            self._time_label.setText(now.toString(fmt))
            self._date_label.setText(now.toString("yyyy.MM.dd  ddd") + tz_suffix)
            self._ampm_label.setText("")
            self._split_bottom.setText("")
        elif style == "digital":
            fmt = self._display_format()
            self._time_label.setText(now.toString(fmt))
            self._date_label.setText(now.toString("ddd  yyyy-MM-dd") + tz_suffix)
            self._ampm_label.setText("")
            self._split_bottom.setText("")
        elif style == "glass":
            fmt = self._display_format()
            self._time_label.setText(now.toString(fmt))
            self._date_label.setText(now.toString("MM / dd") + tz_suffix)
            self._ampm_label.setText("")
            self._split_bottom.setText("")
        else:
            fmt = self._display_format()
            self._time_label.setText(now.toString(fmt))
            self._ampm_label.setText(tz_suffix.strip() if tz_suffix else "")
            self._split_bottom.setText("")
            self._date_label.setText("")

    def _apply_appearance(self) -> None:
        """Unified appearance update using base class engine."""
        sp = self._apply_base_appearance()

        # Propagate text color to all labels
        fg_css = f"color: {self._text_color_str()}; background: transparent; border: none;"

        # Handle style-specific letter spacing for legacy labels
        ls = sp.get("letter_spacing", 0)
        if ls:
            fg_css += f" letter-spacing: {ls}px;"

        for lbl in [
            self._time_label,
            self._date_label,
            self._ampm_label,
            self._split_bottom,
            self._template_label,
        ]:
            lbl.setStyleSheet(fg_css)

        # Also update fonts for legacy labels
        size = self.font_size()
        family = self.font_family()
        self._time_label.setFont(QFont(family, size, QFont.Weight.Bold))
        self._date_label.setFont(QFont(family, max(8, size - 20)))
        self._ampm_label.setFont(QFont(family, max(8, size - 18)))
        self._split_bottom.setFont(QFont(family, max(8, size - 16)))

        self._tick()

    def _refresh_face(self) -> None:
        """Re-render widget (tick)."""
        self._tick()

    # ------------------------------------------------------------------
    # Template engine
    # ------------------------------------------------------------------

    _DEFAULT_TEMPLATE = "{time:%H:%M|size=36|bold}\n{date:%Y.%m.%d|size=11}"
    _TEMPLATE_KEY = "clock_template"

    def _resolve_clock_template(self, template: str, now_dt, tz_label: str) -> str:
        """Resolve variables and tags in clock template."""
        from calendar_app.presentation.widgets.overlay_base import (
            _inject_global_lh,
            _protect_align_tags,
        )

        template = _inject_global_lh(template)
        template = _protect_align_tags(template)

        ctx = {
            "weekday": now_dt.toString("dddd"),
            "date": now_dt.toString("yyyy.MM.dd"),
            "tz_label": tz_label or t("widget.clock.tz.local_short", "Local"),
        }
        template = _BaseOverlayWidget._process_conditionals(template, ctx)

        def _replace(m: re.Match) -> str:
            inner = m.group(1).split("|")
            key, hints = inner[0].strip(), inner[1:]

            if key.startswith("time:"):
                val = now_dt.toString(_strftime_to_qt(key[5:]))
            elif key == "time":
                val = now_dt.toString("HH:mm:ss")
            elif key.startswith("date:"):
                val = now_dt.toString(_strftime_to_qt(key[5:]))
            elif key == "date":
                val = now_dt.toString("yyyy.MM.dd")
            elif key == "weekday":
                val = now_dt.toString("dddd")
            elif key == "weekday:short":
                val = now_dt.toString("ddd")
            elif key == "tz_label":
                val = tz_label or t("widget.clock.tz.local_short", "Local")
            else:
                val = ""

            return _apply_span(val, hints)

        result = re.sub(r"\{([^}]+)\}", _replace, template)
        return _apply_align_tags(result)

    def _open_settings(self) -> None:
        """Show unified settings dialog with schema-based fields."""
        extra = [
            {
                "key": "format",
                "label": t("widget.clock.time_format", "Time format:"),
                "type": "combo",
                "options": [("HH:mm:ss", "hms"), ("HH:mm", "hm")],
                "default": "hms",
            },
            {
                "key": "tz_offset_mins",
                "label": t("widget.clock.timezone", "Timezone:"),
                "type": "combo",
                "options": [(label, offset) for label, offset, hint in self._timezone_items()],
                "default": None,
            },
        ]

        def _preview(tmpl: str) -> str:
            return self._resolve_clock_template(tmpl, self._now_tz(), self._tz_label())

        self._open_standard_settings_dialog(
            title=t("widget.clock.settings_title", "Clock Settings"),
            extra_fields=extra,
            has_template=True,
            default_template=self._DEFAULT_TEMPLATE,
            template_hint=t(
                "widget.clock.template_hint",
                "Variables: {time:%H:%M:%S}, {date:%Y.%m.%d}, {weekday}, {tz_label}",
            ),
            preview_render_fn=_preview,
        )

    def _build_context_menu(self, menu: QMenu):
        menu.addAction(t("widget.clock.settings", "Clock Settings..."), self._open_settings)

    def _action_reset_position(self):
        self.center_on_owner()

    def apply_initial_settings(self):
        # Ensure template is initialized if missing or empty
        if self._TEMPLATE_KEY and not self._get(self._TEMPLATE_KEY, ""):
            self._set(self._TEMPLATE_KEY, self._DEFAULT_TEMPLATE)

        self._apply_and_resize()
        self.restore_position(QPoint(-230, 24))
        if self.is_enabled():
            self._show_with_correct_size()
