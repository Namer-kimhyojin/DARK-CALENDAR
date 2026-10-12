# -*- coding: utf-8 -*-
"""Stay-on-top text/template overlay widget."""

from __future__ import annotations

from html import escape as _escape_html
import re as _re

from PyQt6.QtCore import QDateTime, QPoint, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QLabel, QMenu, QVBoxLayout

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.overlay_base import (
    _DLG_SS,
    _apply_align_tags,
    _apply_span,
    _BaseOverlayWidget,
    _GripFrame,
    _inject_global_lh,
    _protect_align_tags,
    _scale_template_html,
    _strftime_to_qt,
)


class OverlayTextWidget(_BaseOverlayWidget):
    """Free-floating editable text label overlay.

    - Double-click to edit text inline.
    - Right-click for appearance + style options.
    """

    _PREFIX = "overlay_text"
    _DEFAULT_BG_RGBA = "#c8101418"
    _DEFAULT_BORDER_RGBA = "#40ffffff"

    _RE_UTC_OFFSET = _re.compile(r"UTC([+-])(\d+)(?::(\d+))?$")

    _STYLES = [
        ("default", "Default - Card"),
        ("minimal", "Minimal - No Border"),
        ("pill", "Pill - Rounded Corners"),
        ("outlined", "Outlined - No Background"),
        ("banner", "Banner - Left Accent Bar"),
        ("neon", "Neon - Bright Border"),
        ("sticky", "Sticky - Yellow Memo"),
        ("glass", "Glass - Transparent Look"),
        ("code", "Code - Code Block Style"),
        ("tag", "Tag - Top-right Ribbon"),
    ]
    _STYLE_I18N_PREFIX = "widget_text"
    _TEMPLATE_KEY = "label_text"

    _DLG_SS = _DLG_SS

    def _settings_prefix(self):
        return self._PREFIX

    def _default_font_size(self):
        return 20

    # ------------------------------------------------------------------
    # Template engine logic
    # ------------------------------------------------------------------

    _FAST_VARS = frozenset(["stopwatch", "time"])
    _MED_VARS = frozenset(["countdown"])
    _SLOW_VARS = frozenset(
        [
            "dday",
            "day_of_year",
            "weekday",
            "date",
            "task_count",
            "directive_count",
            "next_event",
            "custom_var",
        ]
    )
    _ALL_DYNAMIC = _FAST_VARS | _MED_VARS | _SLOW_VARS
    _DYNAMIC_TOKEN_RE = _re.compile(r"\{\s*([a-z_]\w*)\s*(?=[:|}])")
    _CONDITION_VARIABLE_RE = _re.compile(r"\{\s*if\s+([a-z_]\w*)(?=[:\s])")
    _CONDITION_START_RE = _re.compile(r"\{\s*if\s+")

    @classmethod
    def _template_variables(cls, raw: str) -> frozenset[str]:
        """Detect styled variables and condition inputs using the same names."""
        return frozenset(
            match.group(1)
            for pattern in (cls._DYNAMIC_TOKEN_RE, cls._CONDITION_VARIABLE_RE)
            for match in pattern.finditer(raw)
            if match.group(1) in cls._ALL_DYNAMIC
        )

    def refresh_tier(self) -> str:
        variables = self._template_variables(self._label_text())
        if variables & self._FAST_VARS:
            return "fast"
        if variables & self._MED_VARS:
            return "med"
        if variables & self._SLOW_VARS:
            return "slow"
        return "none"

    def _label_text(self) -> str:
        raw = self._get("label_text", t("widget_text.default_text", "Enter text"))
        return str(raw or t("widget_text.default_text", "Enter text"))

    def _is_template(self) -> bool:
        raw = self._label_text()
        return bool(self._template_variables(raw) or self._CONDITION_START_RE.search(raw))

    def resolve_template(
        self,
        countdown_remaining: str = "",
        stopwatch_text: str = "",
        app_data: dict | None = None,
        widget_registry: dict | None = None,
        override_text: str | None = None,
    ) -> str:
        raw = override_text if override_text is not None else self._label_text()
        if not raw:
            return raw
        raw = _inject_global_lh(raw)
        raw = _protect_align_tags(raw)

        now = QDateTime.currentDateTime()
        qdate = now.date()
        _ad = app_data or {}
        _reg = widget_registry or {}

        _TZ_ALIASES: dict[str, int] = {
            "UTC": 0,
            "GMT": 0,
            "KST": 540,
            "JST": 540,
            "CST": 480,
            "CET": 60,
            "EET": 120,
            "MSK": 180,
            "EDT": -240,
            "EST": -300,
            "PST": -480,
        }

        def _resolve_tz_dt(tz_str: str) -> QDateTime:
            from PyQt6.QtCore import QTimeZone

            s = tz_str.upper().strip()
            offset_mins = _TZ_ALIASES.get(s)
            if offset_mins is None:
                m2 = self._RE_UTC_OFFSET.match(s)
                if m2:
                    sign = 1 if m2.group(1) == "+" else -1
                    try:
                        h, mn = int(m2.group(2)), int(m2.group(3) or 0)
                    except (ValueError, OverflowError):
                        return now
                    if mn > 59 or h > 14 or (h == 14 and mn != 0):
                        return now
                    offset_mins = sign * (h * 60 + mn)
            if offset_mins is None:
                return now
            return QDateTime.currentDateTime().toTimeZone(QTimeZone(offset_mins * 60))

        def _strftime_compat(fmt: str, dt: QDateTime | None = None) -> str:
            selected = dt or now
            return selected.toString(_strftime_to_qt(fmt, hour=selected.time().hour()))

        eval_ctx = {
            "task_count": _ad.get("task_count", 0),
            "directive_count": _ad.get("directive_count", 0),
            "countdown": countdown_remaining,
            "stopwatch": stopwatch_text,
            "day_of_year": qdate.dayOfYear(),
        }

        def _widget_value(widget, getter_name: str, fallback: str) -> str:
            getter = getattr(widget, getter_name, None)
            if getter is None:
                return fallback
            try:
                value = getter()
            except (AttributeError, RuntimeError, TypeError, ValueError):
                return fallback
            return str(value) if value is not None else fallback

        countdown_values = {}
        stopwatch_values = {}
        dday_values = {}
        for inst_id, widget in _reg.items():
            if hasattr(widget, "get_remaining_text"):
                countdown_values[inst_id] = _widget_value(widget, "get_remaining_text", "--:--:--")
                eval_ctx[f"countdown:{inst_id}"] = countdown_values[inst_id]
            if hasattr(widget, "get_elapsed_text"):
                stopwatch_values[inst_id] = _widget_value(widget, "get_elapsed_text", "00:00.0")
                eval_ctx[f"stopwatch:{inst_id}"] = stopwatch_values[inst_id]
            if hasattr(widget, "get_dday_text"):
                dday_values[inst_id] = _widget_value(widget, "get_dday_text", "D-?")
                eval_ctx[f"dday:{inst_id}"] = dday_values[inst_id]
        eval_ctx["dday"] = next(iter(dday_values.values()), "D-?")

        raw = self._process_conditionals(raw, eval_ctx)

        def _replace(m: _re.Match) -> str:
            inner = m.group(1)
            pipe_idx = inner.find("|")
            var_expr, hints = (
                (inner[:pipe_idx], inner[pipe_idx + 1 :].split("|"))
                if pipe_idx != -1
                else (inner, [])
            )
            var_expr = var_expr.strip()

            colon = var_expr.find(":")
            name, arg = (var_expr[:colon], var_expr[colon + 1 :]) if colon != -1 else (var_expr, "")
            val: str | None = None

            if name == "time":
                if arg.startswith("tz="):
                    timezone_spec = arg[3:]
                    offset_spec = _re.fullmatch(
                        r"(UTC[+-]\d+(?::\d+)?)(?::(.*))?", timezone_spec, _re.IGNORECASE
                    )
                    if offset_spec:
                        tz_id, fmt = offset_spec.group(1), offset_spec.group(2) or "%H:%M:%S"
                    else:
                        tz_id, separator, fmt = timezone_spec.partition(":")
                        fmt = fmt if separator and fmt else "%H:%M:%S"
                    val = _strftime_compat(fmt, _resolve_tz_dt(tz_id))
                else:
                    val = _strftime_compat(arg or "%H:%M:%S")
            elif name == "date":
                val = _strftime_compat(arg or "%Y.%m.%d")
            elif name == "weekday":
                if arg == "short":
                    val = now.toString("ddd")
                elif arg == "en":
                    val = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][
                        (qdate.dayOfWeek() - 1) % 7
                    ]
                else:
                    val = now.toString("dddd")
            elif name == "day_of_year":
                val = f"D+{qdate.dayOfYear()}"
            elif name == "dday":
                val = dday_values.get(arg, "D-?") if arg else eval_ctx["dday"]
            elif name == "countdown":
                parts = arg.split(":", 1)
                inst_id = parts[0]
                sub_fmt = parts[1] if len(parts) == 2 else ("hm" if inst_id == "hm" else "")
                if inst_id == "hm":
                    inst_id = ""

                rem = countdown_values.get(inst_id, countdown_remaining)
                if sub_fmt == "hm" and rem and ":" in rem:
                    rem = rem.rsplit(":", 1)[0]
                val = rem or "--:--:--"
            elif name == "stopwatch":
                val = stopwatch_values.get(arg, stopwatch_text or "00:00.0")
            elif name == "task_count":
                val = str(_ad.get("task_count", 0))
            elif name == "directive_count":
                val = str(_ad.get("directive_count", 0))
            elif name == "next_event":
                val = str(_ad.get("next_event", "-"))
            elif name == "custom_var":
                val = str(_ad.get(f"custom_var_{arg}" if arg else "custom_var", arg or ""))

            return _apply_span(
                _escape_html(val if val is not None else var_expr, quote=False), hints
            )

        result = _re.sub(r"\{([^}]+)\}", _replace, raw)
        return _apply_align_tags(result)

    def refresh_template(
        self, countdown_remaining="", stopwatch_text="", app_data=None, widget_registry=None
    ):
        if not self._is_template():
            return
        resolved = self.resolve_template(
            countdown_remaining, stopwatch_text, app_data, widget_registry
        )
        rendered = _scale_template_html(resolved, self.font_size())
        rendered = self._resolve_template_color_aliases(rendered)
        self._text_label.setText(rendered)
        self._force_resize()

    # ------------------------------------------------------------------
    # UI Methods
    # ------------------------------------------------------------------

    def _build_face(self) -> QFrame:
        frame = _GripFrame(self)
        frame.setObjectName("textFace")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(0)
        self._text_label = QLabel(self._label_text(), frame)
        self._text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._text_label.setWordWrap(True)
        self._text_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._text_label)
        return frame

    def _apply_appearance(self) -> None:
        """Unified appearance engine."""
        self._apply_base_appearance()

        # Propagate text color
        self._text_label.setStyleSheet(
            f"color: {self._text_color_str()}; background: transparent; border: none;"
        )

        size = self.font_size()
        style = self.display_style()

        # Style specific tweaks
        self._text_label.setWordWrap(self._get("word_wrap", True, type_=bool))
        self._set_align(self._get("text_align", "center"))

        font = QFont(self.font_family(), size)
        font.setBold(style == "tag")
        self._text_label.setFont(font)

        if self._is_template():
            display_text = _scale_template_html(self.resolve_template(), size)
            display_text = self._resolve_template_color_aliases(display_text)
        else:
            display_text = _apply_align_tags(self._label_text())
        self._text_label.setText(display_text)

    def _set_align(self, alignment: str):
        self._set("text_align", alignment)
        flags = {
            "left": Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "right": Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            "center": Qt.AlignmentFlag.AlignCenter,
        }
        self._text_label.setAlignment(flags.get(alignment, Qt.AlignmentFlag.AlignCenter))

    def _open_settings(self, initial_tab=0):
        extra = [
            {
                "key": "text_align",
                "label": t("widget_text.align_label", "Alignment:"),
                "type": "combo",
                "options": [
                    (t("widget_text.align_left", "Left"), "left"),
                    (t("widget_text.align_center", "Center"), "center"),
                    (t("widget_text.align_right", "Right"), "right"),
                ],
                "default": "center",
            },
            {
                "key": "word_wrap",
                "label": t("widget_text.word_wrap", "Word wrap"),
                "type": "bool",
                "default": True,
            },
        ]

        quick_groups = [
            (
                t("widget_text.group_time_date", "Time / Date"),
                [
                    ("{time:%H:%M}", t("widget_text.var_time", "Time")),
                    ("{date:%Y.%m.%d}", t("widget_text.var_date", "Date")),
                    ("{weekday}", t("widget_text.var_weekday", "Weekday")),
                    ("{weekday:short}", t("widget_text.var_weekday_short", "Weekday (short)")),
                    ("{day_of_year}", t("widget_text.var_day_of_year", "Day of year")),
                    ("\n", t("widget_text.var_newline", "New line")),
                    ("{lh=2.0}", t("widget_text.var_line_height", "Line height")),
                ],
            ),
            (
                t("widget_text.group_widget_data", "Widget data"),
                [
                    ("{stopwatch:stopwatch_0}", t("widget_text.var_stopwatch", "Stopwatch")),
                    ("{countdown:countdown_0}", t("widget_text.var_countdown", "Countdown")),
                    ("{dday:dday_0}", "D-Day"),
                ],
            ),
            (
                t("widget_text.group_app_data", "App data"),
                [
                    ("{task_count}", t("widget_text.var_task_count", "Task count")),
                    ("{directive_count}", t("widget_text.var_directive_count", "Directive count")),
                    ("{next_event}", t("widget_text.var_next_event", "Next event")),
                    ("{custom_var}", t("widget_text.var_custom_var", "Custom var")),
                ],
            ),
            (
                t("widget_text.group_conditions", "Conditions"),
                [
                    (
                        "{if task_count > 0}Has tasks{else}No tasks{/if}",
                        t("widget_text.var_condition_block", "Conditional block"),
                    ),
                    (
                        "{if countdown:countdown_0 < 1h}Due soon!{else}{countdown:countdown_0}{/if}",
                        t("widget_text.var_countdown_condition", "Countdown condition"),
                    ),
                ],
            ),
            (
                t("widget_text.group_align", "Alignment"),
                [
                    ("{align=left}", t("widget_text.var_align_left", "Left")),
                    ("{align=center}", t("widget_text.var_align_center", "Center")),
                    ("{align=right}", t("widget_text.var_align_right", "Right")),
                ],
            ),
        ]

        self._open_standard_settings_dialog(
            title=t("widget_text.settings_title_menu", "Text/Template Settings"),
            extra_fields=extra,
            has_template=True,
            default_template="",
            template_hint=t("widget_text.template_help", "Variables: {time}, {date}, {weekday}..."),
            preview_render_fn=lambda tmpl: self.resolve_template(override_text=tmpl),
            quick_insert_groups=quick_groups,
        )

    def _build_context_menu(self, menu: QMenu):
        menu.addAction(
            t("widget_text.settings_menu", "Text/Template Widget Settings..."),
            self._open_settings,
        )
        menu.addAction(t("widget.usage.copy_text", "표시된 내용 복사"), self._copy_displayed_text)

    def _copy_displayed_text(self):
        from PyQt6.QtGui import QTextDocument
        from PyQt6.QtWidgets import QApplication

        document = QTextDocument()
        document.setHtml(self._text_label.text())
        QApplication.clipboard().setText(document.toPlainText())

    def _on_double_click(self) -> bool:
        self._open_settings()
        return True

    def apply_initial_settings(self):
        self._apply_appearance()
        self.restore_position(QPoint(-230, 460))
        if self.is_enabled():
            self._show_with_correct_size()
