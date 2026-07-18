"""Overlay stopwatch widget."""

from __future__ import annotations

import contextlib
import re
import time

from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QFrame, QLabel, QMenu, QVBoxLayout

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.overlay_base import (
    _DLG_SS,
    _apply_align_tags,
    _apply_span,
    _BaseOverlayWidget,
    _extract_global_lh,
    _GripFrame,
    _parse_rgba,
    _rgba_css,
    _scale_template_html,
)


class OverlayStopwatchWidget(_BaseOverlayWidget):
    _PREFIX = "overlay_stopwatch"
    _DEFAULT_BG_RGBA = "#d6101418"
    _DEFAULT_BORDER_RGBA = "#20ffffff"

    _STYLES = [
        ("default", "Default - Center Block"),
        ("minimal", "Minimal - No Border"),
        ("labeled", "Labeled - Show Title"),
        ("compact", "Compact - Smaller Padding"),
        ("round", "Round - Circular Feel"),
        ("neon", "Neon - Thick Border"),
        ("pill", "Pill - Rounded Wide Shape"),
        ("ticker", "Ticker - Narrow Horizontal Strip"),
        ("frame", "Frame - Double Border"),
        ("glass", "Glass - Transparent Look"),
    ]
    _STYLE_I18N_PREFIX = "widget.stopwatch"
    _TEMPLATE_KEY = "sw_template"

    _DLG_SS = _DLG_SS

    def _settings_prefix(self):
        return self._PREFIX

    def _default_font_size(self):
        return 28

    def _build_face(self) -> QFrame:
        frame = _GripFrame(self)
        frame.setObjectName("stopwatchFace")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.setSpacing(2)

        self._title_label = QLabel(t("widget.stopwatch.title", "STOPWATCH"), frame)
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_label.setVisible(False)
        self._time_label = QLabel("00:00.0", frame)
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label = QLabel("", frame)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setVisible(False)

        self._template_label = QLabel("", frame)
        self._template_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._template_label.setWordWrap(True)
        self._template_label.setTextFormat(Qt.TextFormat.RichText)
        self._template_label.setVisible(False)

        for w in [self._title_label, self._time_label, self._status_label, self._template_label]:
            layout.addWidget(w)

        self._start_sw_timer()
        self._tick_sw()
        return frame

    # ------------------------------------------------------------------
    # Data Logic
    # ------------------------------------------------------------------

    def _sw_elapsed_ms(self) -> float:
        base = float(self._get("sw_elapsed_ms", 0.0) or 0.0)
        if self._get("sw_running", False, type_=bool):
            started = self._get("sw_started_mono")
            if started is not None:
                with contextlib.suppress(TypeError, ValueError):
                    base += max(0.0, (time.monotonic() - float(started)) * 1000.0)
        return base

    def _sw_running(self) -> bool:
        return self._get("sw_running", False, type_=bool)

    def _format_elapsed(self, ms: float) -> str:
        total_s = max(0.0, ms) / 1000.0
        h, rem = divmod(total_s, 3600)
        m, s = divmod(rem, 60)
        t_ = int((ms % 1000) // 100)
        return (
            f"{int(h):02d}:{int(m):02d}:{int(s):02d}"
            if h > 0
            else f"{int(m):02d}:{int(s):02d}.{t_:d}"
        )

    def toggle_running(self):
        running = self._sw_running()
        if running:
            self._set("sw_elapsed_ms", self._sw_elapsed_ms())
            self._set("sw_running", False)
            self._set("sw_started_mono", None)
        else:
            self._set("sw_started_mono", time.monotonic())
            self._set("sw_running", True)
        self._tick_sw()

    def reset_sw(self):
        self._set("sw_elapsed_ms", 0.0)
        self._set("sw_running", False)
        self._set("sw_started_mono", None)
        self._tick_sw()

    def _tick_sw(self):
        if self._resizing and not self._measuring:
            return
        elapsed = self._sw_elapsed_ms()
        running = self._sw_running()
        if self._is_template_mode():
            html = self._resolve_sw_template(self._widget_template(), elapsed, running)
            self._set_template_label(html)
            self._title_label.setVisible(False)
            self._time_label.setVisible(False)
            self._status_label.setVisible(False)
        else:
            self._template_label.setVisible(False)
            self._time_label.setVisible(True)
            self._time_label.setText(self._format_elapsed(elapsed))
            style = self.display_style()
            self._status_label.setText(
                t("widget.stopwatch.status_run", "RUN")
                if running
                else t("widget.stopwatch.status_stop", "STOP")
            )
            self._status_label.setVisible(style in ("neon", "frame", "glass"))
            show_title = style in ("labeled", "ticker", "frame")
            self._title_label.setVisible(show_title)
            if show_title:
                self._title_label.setText(
                    t("widget.stopwatch.short_title", "SW")
                    if style == "ticker"
                    else t("widget.stopwatch.title", "STOPWATCH")
                )

    def _apply_appearance(self) -> None:
        self._apply_base_appearance()
        size, family = self.font_size(), self.font_family()
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family() or family

        self._title_label.setFont(QFont(mono, max(8, size - 14)))
        self._title_label.setStyleSheet("background:transparent;letter-spacing:3px;")
        self._time_label.setFont(QFont(mono, size, QFont.Weight.Bold))
        self._status_label.setFont(QFont(mono, max(8, size - 16)))
        self._status_label.setStyleSheet("background:transparent;letter-spacing:2px;")
        self._template_label.setFont(QFont(mono, size))

        fg_css = f"color: {self._text_color_str()};"
        for lbl in [self._title_label, self._time_label, self._status_label, self._template_label]:
            lbl.setStyleSheet(lbl.styleSheet() + fg_css)
        style = self.display_style()
        if style == "ticker":
            self._title_label.setText(t("widget.stopwatch.short_title", "SW"))
        elif style in ("labeled", "frame"):
            self._title_label.setText(t("widget.stopwatch.title", "STOPWATCH"))
        self._tick_sw()

    def _refresh_face(self):
        self._tick_sw()

    def _start_sw_timer(self):
        if not hasattr(self, "_sw_timer"):
            self._sw_timer = QTimer(self)
            self._sw_timer.timeout.connect(self._tick_sw)
        if not self._sw_timer.isActive():
            self._sw_timer.start(100)

    def get_elapsed_text(self) -> str:
        return self._format_elapsed(self._sw_elapsed_ms())

    # ------------------------------------------------------------------
    # Template Engine
    # ------------------------------------------------------------------

    _DEFAULT_TEMPLATE = "{elapsed|size=28|bold}\n{status|size=11}"

    def _resolve_sw_template(self, template: str, elapsed_ms: float, running: bool) -> str:
        from calendar_app.presentation.widgets.overlay_base import (
            _inject_global_lh,
            _protect_align_tags,
        )

        template = _inject_global_lh(template)
        template = _protect_align_tags(template)

        total_s = max(0.0, elapsed_ms) / 1000.0
        h, rem = divmod(total_s, 3600)
        m, s = divmod(rem, 60)
        tenths = int((elapsed_ms % 1000) // 100)
        elapsed_str = (
            f"{int(h):02d}:{int(m):02d}:{int(s):02d}"
            if h > 0
            else f"{int(m):02d}:{int(s):02d}.{tenths}"
        )

        vals = {
            "elapsed": elapsed_str,
            "hours": int(h),
            "minutes": int(m),
            "seconds": int(s),
            "tenths": tenths,
            "status": t("widget.stopwatch.status_run", "RUN")
            if running
            else t("widget.stopwatch.status_stop", "STOP"),
            "status_icon": ">" if running else "[]",
        }
        template = self._process_conditionals(template, vals)

        def _replace(m2: re.Match) -> str:
            inner = m2.group(1).split("|")
            key, hints = inner[0].strip(), inner[1:]
            return _apply_span(str(vals.get(key, "")), hints)

        return _apply_align_tags(re.sub(r"\{([^}]+)\}", _replace, template))

    def set_display_text(self, elapsed_text: str, running: bool):
        """Backward-compatible text updater used by tests and legacy callers."""
        self._template_label.setVisible(False)
        self._time_label.setVisible(True)
        self._time_label.setText(str(elapsed_text or "00:00.0"))
        style = self.display_style()
        self._status_label.setText(
            t("widget.stopwatch.status_run", "RUN")
            if running
            else t("widget.stopwatch.status_stop", "STOP")
        )
        self._status_label.setVisible(style in ("neon", "frame", "glass"))
        show_title = style in ("labeled", "ticker", "frame")
        self._title_label.setVisible(show_title)
        if show_title:
            self._title_label.setText(
                t("widget.stopwatch.short_title", "SW")
                if style == "ticker"
                else t("widget.stopwatch.title", "STOPWATCH")
            )

    def _set_template_label(self, html: str, base_size: int | None = None) -> None:
        """Render template with a fixed-width font regardless of selected family."""
        if base_size is None:
            base_size = self.font_size()
        html, lh_css = _extract_global_lh(html, base_size)
        scaled_html = _scale_template_html(html, base_size)
        fg_c, fg_a = _parse_rgba(self.text_color_rgba())
        fg_css = _rgba_css(fg_c, fg_a)
        mono = (
            QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()
            or self.font_family()
        )
        lh_part = f"line-height:{lh_css};" if lh_css else ""
        self._template_label.setText(
            f"<div style=\"color:{fg_css};font-family:'{mono}';text-align:center;{lh_part}\">"
            f"{scaled_html}</div>"
        )
        self._template_label.setVisible(True)

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _open_settings(self):
        self._open_standard_settings_dialog(
            title=t("widget.stopwatch.settings_title", "Stopwatch Settings"),
            has_template=True,
            default_template=self._DEFAULT_TEMPLATE,
            template_hint=t("widget.stopwatch.template_hint", "{elapsed}, {hours}, {status}"),
            preview_render_fn=lambda tmpl: self._resolve_sw_template(
                tmpl, self._sw_elapsed_ms(), self._sw_running()
            ),
        )

    def _build_context_menu(self, menu: QMenu):
        running = self._sw_running()
        menu.addAction(t("widget.stopwatch.settings", "Stopwatch Settings..."), self._open_settings)
        menu.addSeparator()
        menu.addAction(
            t("widget.stopwatch.pause", "Pause")
            if running
            else t("widget.stopwatch.start", "Start"),
            self.toggle_running,
        )
        menu.addAction(t("widget.stopwatch.reset", "Reset"), self.reset_sw)

    def _on_double_click(self) -> bool:
        self.toggle_running()
        return True

    def apply_initial_settings(self):
        self._tick_sw()
        self._apply_and_resize()
        self.restore_position(QPoint(-230, 120))
        self._start_sw_timer()
        if self.is_enabled():
            self._show_with_correct_size()
