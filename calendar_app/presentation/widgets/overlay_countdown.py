"""Overlay countdown widget."""

from __future__ import annotations

import re

from PyQt6.QtCore import QDateTime, QPoint, Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.overlay_base import (
    _DLG_SS,
    _apply_align_tags,
    _apply_span,
    _BaseOverlayWidget,
    _GripFrame,
    _strftime_to_qt,
)


class OverlayCountdownWidget(_BaseOverlayWidget):
    _PREFIX = "overlay_countdown"
    _DEFAULT_BG_RGBA = "#d6101418"
    _DEFAULT_BORDER_RGBA = "#20ffffff"

    _STYLES = [
        ("default", "Default - Time + Target Date"),
        ("dday", "D-Day - Large Remaining Days"),
        ("compact", "Compact - Time Only"),
        ("minimal", "Minimal - No Border"),
        ("titled", "Titled - Show Top Label"),
        ("neon", "Neon - Thick Border"),
        ("pill", "Pill - Rounded Wide Shape"),
        ("urgent", "Urgent - Red Highlight Border"),
        ("glass", "Glass - Transparent Look"),
        ("flip", "Flip - Large Digits + Seconds"),
    ]
    _STYLE_I18N_PREFIX = "widget.countdown"
    _TEMPLATE_KEY = "cd_template"

    _DLG_SS = _DLG_SS

    def _settings_prefix(self):
        return self._PREFIX

    def _default_font_size(self):
        return 24

    def _build_face(self) -> QFrame:
        frame = _GripFrame(self)
        frame.setObjectName("countdownFace")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 14, 20, 12)
        layout.setSpacing(2)

        self._title_label = QLabel(t("widget.countdown.title", "COUNTDOWN"), frame)
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_label.setVisible(False)
        self._dday_label = QLabel("", frame)
        self._dday_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dday_label.setVisible(False)
        self._time_label = QLabel("∞", frame)
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._seconds_label = QLabel("", frame)
        self._seconds_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._seconds_label.setVisible(False)
        self._target_label = QLabel("", frame)
        self._target_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._target_label.setWordWrap(True)

        self._template_label = QLabel("", frame)
        self._template_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._template_label.setWordWrap(True)
        self._template_label.setTextFormat(Qt.TextFormat.RichText)
        self._template_label.setVisible(False)

        for w in [
            self._title_label,
            self._dday_label,
            self._time_label,
            self._seconds_label,
            self._target_label,
            self._template_label,
        ]:
            layout.addWidget(w)

        self._start_cd_timer()
        self._tick_cd()
        return frame

    # ------------------------------------------------------------------
    # Data & Calculation
    # ------------------------------------------------------------------

    def _cd_target_dt(self, override_iso: str | None = None) -> QDateTime | None:
        raw = str(
            override_iso if override_iso is not None else self._get("cd_target_iso", "") or ""
        ).strip()
        if not raw:
            return None
        dt = QDateTime.fromString(raw, Qt.DateFormat.ISODate)
        return dt if dt.isValid() else None

    def _cd_remaining(self, target_dt: QDateTime | None = None) -> tuple[str, str]:
        target = target_dt if target_dt is not None else self._cd_target_dt()
        if target is None:
            return "--:--:--", t("widget.countdown.no_target_hint", "Right-click -> Set target")
        now = QDateTime.currentDateTime()
        secs = now.secsTo(target)
        if secs < 0:
            return "00:00:00", t("menu.countdown_done", "Countdown Complete")

        hours, rem = divmod(secs, 3600)
        mins, seconds = divmod(rem, 60)
        days = secs // 86400
        target_str = target.toString("yyyy-MM-dd HH:mm")
        if days > 0:
            h2, m2, s2 = hours % 24, mins, seconds
            return f"{h2:02d}:{m2:02d}:{s2:02d}", t(
                "menu.countdown_d_days",
                "D-{days} remaining ({target})",
                days=days,
                target=target_str,
            )
        return f"{hours:02d}:{mins:02d}:{seconds:02d}", target_str

    def get_remaining_text(self) -> str:
        return self._cd_remaining()[0]

    def _tick_cd(self):
        if self._resizing and not self._measuring:
            return
        remaining, target_text = self._cd_remaining()

        if self._is_template_mode():
            html = self._resolve_cd_template(
                self._widget_template(), remaining, self._cd_target_dt()
            )
            self._set_template_label(html)
            for w in [
                self._title_label,
                self._dday_label,
                self._time_label,
                self._seconds_label,
                self._target_label,
            ]:
                w.setVisible(False)
        else:
            self._template_label.setVisible(False)
            self._update_basic_display(remaining, target_text)

    def _update_basic_display(self, remaining: str, target_text: str):
        style = self.display_style()
        no_target = remaining == "--:--:--"
        self._time_label.setText("∞" if no_target else remaining)
        self._target_label.setText(
            target_text if not no_target else t("widget.countdown.set_target", "Set target")
        )

        self._dday_label.setVisible(style == "dday" and not no_target and "D-" in target_text)
        if self._dday_label.isVisible():
            self._dday_label.setText(
                next((p for p in target_text.split() if p.startswith("D-")), "")
            )

        self._seconds_label.setVisible(style == "flip" and not no_target and ":" in remaining)
        if self._seconds_label.isVisible():
            parts = remaining.rsplit(":", 1)
            self._time_label.setText(parts[0])
            self._seconds_label.setText(f": {parts[1]}")

        self._title_label.setVisible(style == "titled")

    def _apply_appearance(self) -> None:
        self._apply_base_appearance()
        size, family, style = self.font_size(), self.font_family(), self.display_style()

        self._title_label.setFont(QFont(family, max(8, size - 14)))
        self._target_label.setFont(QFont(family, max(8, size - 10)))
        self._seconds_label.setFont(QFont(family, max(8, size - 6)))

        main_font = QFont(family, size + 4 if style == "flip" else size)
        main_font.setBold(True)
        self._time_label.setFont(main_font)

        self._dday_label.setFont(QFont(family, size + 6, QFont.Weight.Bold))

        fg_css = f"color: {self._text_color_str()};"
        for lbl in [
            self._time_label,
            self._target_label,
            self._title_label,
            self._seconds_label,
            self._dday_label,
        ]:
            lbl.setStyleSheet(f"background:transparent; border:none; {fg_css}")
        self._tick_cd()

    def _refresh_face(self):
        self._tick_cd()

    def _start_cd_timer(self):
        if not hasattr(self, "_cd_timer"):
            self._cd_timer = QTimer(self)
            self._cd_timer.timeout.connect(self._tick_cd)
        if not self._cd_timer.isActive():
            self._cd_timer.start(1000)

    # ------------------------------------------------------------------
    # Template engine
    # ------------------------------------------------------------------

    _DEFAULT_TEMPLATE = "{remaining|size=24|bold}\n{target|size=11}"

    def _resolve_cd_template(
        self, template: str, remaining: str, target_dt: QDateTime | None
    ) -> str:
        from calendar_app.presentation.widgets.overlay_base import (
            _inject_global_lh,
            _protect_align_tags,
        )

        template = _inject_global_lh(template)
        template = _protect_align_tags(template)

        secs = 0
        if remaining and remaining not in ("--:--:--", "∞", "00:00:00"):
            parts = remaining.split(":")
            secs = sum(int(p) * f for p, f in zip(reversed(parts), [1, 60, 3600], strict=False))

        days, rem = divmod(secs, 86400)
        hours, rem = divmod(rem, 3600)
        mins, seconds = divmod(rem, 60)
        vals = {
            "remaining": remaining or "∞",
            "hours": hours,
            "minutes": mins,
            "seconds": seconds,
            "days": days,
            "target": target_dt.toString("yyyy-MM-dd HH:mm") if target_dt else "",
        }
        template = self._process_conditionals(template, vals)

        def _replace(m: re.Match) -> str:
            inner = m.group(1).split("|")
            key, hints = inner[0].strip(), inner[1:]
            if key.startswith("target:") and target_dt:
                return _apply_span(target_dt.toString(_strftime_to_qt(key[7:])), hints)
            return _apply_span(str(vals.get(key, "")), hints)

        return _apply_align_tags(re.sub(r"\{([^}]+)\}", _replace, template))

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _open_settings(self):
        cur_iso = self._get("cd_target_iso", "")
        cur_date, cur_time = cur_iso.split("T") if "T" in cur_iso else (cur_iso, "00:00")

        extra = [
            {
                "key": "cd_target_date",
                "label": t("widget.countdown.date", "Target Date:"),
                "type": "date",
                "default": cur_date,
            },
            {
                "key": "cd_target_time",
                "label": t("widget.countdown.time", "Target Time:"),
                "type": "time",
                "default": cur_time,
            },
        ]

        def _setup_presets(layout, dlg):
            self._add_divider(layout)
            self._add_section_label(
                layout, t("widget.countdown.quick_presets", "Quick Target Selection")
            )
            row = QHBoxLayout()
            row.setSpacing(6)

            presets = [
                ("+10m", lambda: self._adjust_target_relative(minutes=10)),
                ("+30m", lambda: self._adjust_target_relative(minutes=30)),
                ("+1h", lambda: self._adjust_target_relative(hours=1)),
                (
                    t("widget.countdown.end_of_day", "End of Day (18:00)"),
                    lambda: self._set_target_preset(time="18:00"),
                ),
                (
                    t("widget.countdown.tomorrow", "Tomorrow"),
                    lambda: self._set_target_preset(date_offset=1, time="00:00"),
                ),
                ("+7d", lambda: self._adjust_target_relative(days=7)),
            ]
            for label, cb in presets:
                btn = QPushButton(label)
                btn.setObjectName("presetBtn")
                btn.setFixedHeight(28)
                btn.clicked.connect(cb)
                row.addWidget(btn)
            row.addStretch()
            layout.addLayout(row)

        def _preview(tmpl: str, fields: dict | None) -> str:
            if not fields:
                return ""
            date_val = fields.get("cd_target_date") or ""
            time_val = fields.get("cd_target_time") or "00:00"
            if not date_val or date_val == "None":
                return self._resolve_cd_template(tmpl, None, None)
            iso = f"{date_val}T{time_val}"
            dt = self._cd_target_dt(iso)
            rem, _ = self._cd_remaining(dt)
            return self._resolve_cd_template(tmpl, rem, dt)

        if self._open_standard_settings_dialog(
            title=t("widget.countdown.settings_title", "Countdown Settings"),
            extra_fields=extra,
            has_template=True,
            default_template=self._DEFAULT_TEMPLATE,
            template_hint=t(
                "widget.countdown.template_hint", "{remaining}, {days}, {hours}, {target}"
            ),
            preview_render_fn=lambda tmpl: (
                _preview(
                    tmpl,
                    {k: self._get_field_value(w) for k, w in self._active_settings_widgets.items()},
                )
                if getattr(self, "_active_settings_widgets", None)
                else ""
            ),
            extra_basic_setup_fn=_setup_presets,
        ):
            date_val = self._get("cd_target_date") or ""
            time_val = self._get("cd_target_time") or "00:00"
            if date_val and date_val != "None":
                self._set("cd_target_iso", f"{date_val}T{time_val}")
            self._tick_cd()

    def _adjust_target_relative(self, days=0, hours=0, minutes=0):
        w_date = self._active_settings_widgets.get("cd_target_date")
        w_time = self._active_settings_widgets.get("cd_target_time")
        if not w_date or not w_time:
            return
        from PyQt6.QtCore import QDateTime

        cdt = QDateTime(w_date.date(), w_time.time())
        ndt = cdt.addDays(days).addSecs(hours * 3600 + minutes * 60)
        w_date.setDate(ndt.date())
        w_time.setTime(ndt.time())

    def _set_target_preset(self, date_offset=0, time=None):
        w_date = self._active_settings_widgets.get("cd_target_date")
        w_time = self._active_settings_widgets.get("cd_target_time")
        if not w_date or not w_time:
            return
        from PyQt6.QtCore import QDate, QTime

        w_date.setDate(QDate.currentDate().addDays(date_offset))
        if time:
            w_time.setTime(QTime.fromString(time, "HH:mm"))

    def _build_context_menu(self, menu: QMenu):
        menu.addAction(t("widget.countdown.settings", "Countdown Settings..."), self._open_settings)
        menu.addAction(
            t("widget.countdown.clear_target", "Clear target"),
            lambda: (self._set("cd_target_iso", ""), self._tick_cd()),
        )

    def _on_double_click(self) -> bool:
        self._open_settings()
        return True

    def apply_initial_settings(self):
        self._tick_cd()
        self._apply_and_resize()
        self.restore_position(QPoint(-230, 340))
        self._start_cd_timer()
        if self.is_enabled():
            self._show_with_correct_size()
