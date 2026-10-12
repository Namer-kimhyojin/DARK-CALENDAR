# -*- coding: utf-8 -*-
"""Stay-on-top D-Day overlay widget."""

from __future__ import annotations

from html import escape
import re

from PyQt6.QtCore import QDate, QLocale, QPoint, QSize, Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QLabel, QMenu, QVBoxLayout

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.moment_asset_packs import (
    DEFAULT_MOMENT_ASSET_PACK_ID,
    EMPTY_MOMENT_ART,
    get_moment_asset_pack,
    moment_art_size,
    moment_asset_html,
    moment_asset_packs,
    moment_pack_icon,
    moment_pack_preview_pixmap,
    remove_empty_moment_rows,
)
from calendar_app.presentation.widgets.overlay_base import (
    _DLG_SS,
    _apply_align_tags,
    _apply_span,
    _BaseOverlayWidget,
    _GripFrame,
    _strftime_to_qt,
)


class OverlayDDayWidget(_BaseOverlayWidget):
    """Free-floating D-Day counter widget."""

    _PREFIX = "overlay_dday"
    _DEFAULT_BG_RGBA = "#d6101418"
    _DEFAULT_BORDER_RGBA = "#20ffffff"

    _STYLES = [
        ("default", "Default - Card"),
        ("minimal", "Minimal - No Border"),
        ("pill", "Pill - Rounded Corners"),
        ("neon", "Neon - Thick Border"),
        ("compact", "Compact - Smaller Padding"),
        ("banner", "Banner - Left Accent Bar"),
        ("glass", "Glass - Transparent Look"),
        ("big", "Big - Larger Numbers"),
        ("retro", "Retro - Double Border"),
        ("urgent", "Urgent - Red Highlight"),
    ]
    _STYLE_I18N_PREFIX = "widget.dday"
    _TEMPLATE_KEY = "dd_template"

    _DLG_SS = _DLG_SS

    def _settings_prefix(self):
        return self._PREFIX

    def _default_font_size(self):
        return 36

    def _build_face(self) -> QFrame:
        frame = _GripFrame(self)
        frame.setObjectName("ddayFace")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 14, 20, 12)
        layout.setSpacing(4)

        self._dday_label = QLabel("D-?", frame)
        self._dday_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subtitle_label = QLabel(t("widget.dday.no_target_hint", "Set date"), frame)
        self._subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subtitle_label.setWordWrap(True)
        self._subtitle_label.setTextFormat(Qt.TextFormat.PlainText)

        self._template_label = QLabel("", frame)
        self._template_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._template_label.setWordWrap(True)
        self._template_label.setTextFormat(Qt.TextFormat.RichText)
        self._template_label.setVisible(False)

        for w in [self._dday_label, self._subtitle_label, self._template_label]:
            layout.addWidget(w)

        self._start_dd_timer()
        self._tick_dd()
        return frame

    # ------------------------------------------------------------------
    # Data Logic
    # ------------------------------------------------------------------

    def _dd_target_date(self, override_iso: str | None = None) -> QDate | None:
        raw = str(
            override_iso if override_iso is not None else self._get("dd_target_date", "") or ""
        ).strip()
        if not raw:
            return None
        d = QDate.fromString(raw, "yyyy-MM-dd")
        return d if d.isValid() else None

    def _dd_display(
        self, target_date: QDate | None = None, label: str | None = None
    ) -> tuple[str, str]:
        target = target_date if target_date is not None else self._dd_target_date()
        if target is None or not target.isValid():
            return "D-?", t("widget.dday.no_target_hint", "Set date")

        delta = QDate.currentDate().daysTo(target)
        dday_str = "D-Day" if delta == 0 else (f"D-{delta}" if delta > 0 else f"D+{abs(delta)}")

        lbl = label if label is not None else str(self._get("dd_label", "") or "")
        date_str = target.toString("yyyy.MM.dd")
        return dday_str, (f"{lbl}  {date_str}".strip() if lbl else date_str)

    def get_dday_text(self) -> str:
        return self._dd_display()[0]

    def _tick_dd(self):
        if self._resizing and not self._measuring:
            return
        dday_str, subtitle = self._dd_display()

        if self._is_template_mode():
            html = self._resolve_dd_template(
                self._widget_template(),
                dday_str,
                str(self._get("dd_label", "") or ""),
                self._dd_target_date(),
            )
            self._set_template_label(html)
            self._update_template_word_wrap(html)
            self._dday_label.setVisible(False)
            self._subtitle_label.setVisible(False)
        else:
            self._template_label.setVisible(False)
            self._dday_label.setVisible(True)
            self._subtitle_label.setVisible(True)
            self._dday_label.setText(dday_str)
            self._subtitle_label.setText(subtitle)

    def _update_template_word_wrap(self, html: str) -> None:
        """Let compact content use its natural width without overflowing the screen."""
        fixed = self._get("fixed_w") not in (None, "", "None") and self._get("fixed_h") not in (
            None,
            "",
            "None",
        )
        multiline = bool(
            re.search(r"<br\s*/?>|[\r\n]|</(?:div|p|li)>\s*<(?:div|p|li)\b", html, re.IGNORECASE)
        )
        wrap = fixed or self._measuring or self.widget_shape_id() != "card" or multiline
        self._template_label.setWordWrap(wrap)
        if not wrap:
            margins = self.face.layout().contentsMargins() if hasattr(self, "face") else None
            padding = margins.left() + margins.right() if margins is not None else 40
            # QWidget.adjustSize() caps top-level natural windows at two thirds
            # of the screen. Keep some room for frame and shadow chrome.
            safe_width = int(self._screen_bounds()[0] * 0.6)
            if self._template_label.sizeHint().width() + padding > safe_width:
                self._template_label.setWordWrap(True)

    def _apply_appearance(self) -> None:
        self._apply_base_appearance()
        size, style, family = self.font_size(), self.display_style(), self.font_family()

        self._dday_label.setFont(
            QFont(family, size + 12 if style == "big" else size, QFont.Weight.Bold)
        )
        sub_size = (
            max(8, size - 16)
            if style == "compact"
            else (max(8, size - 10) if style == "big" else max(8, size - 14))
        )
        self._subtitle_label.setFont(QFont(family, sub_size))

        fg_css = f"color: {self._text_color_str()};"
        for lbl in [self._dday_label, self._subtitle_label, self._template_label]:
            lbl.setStyleSheet(f"background:transparent; border:none; {fg_css}")
        self._tick_dd()

    def _refresh_face(self):
        self._tick_dd()

    def _start_dd_timer(self):
        if not hasattr(self, "_dd_timer"):
            self._dd_timer = QTimer(self)
            self._dd_timer.timeout.connect(self._tick_dd)
        if self.is_enabled() and not self._dd_timer.isActive():
            self._dd_timer.start(60_000)

    def _set_runtime_active(self, active: bool) -> None:
        if active:
            self._start_dd_timer()
        elif hasattr(self, "_dd_timer"):
            self._dd_timer.stop()

    # ------------------------------------------------------------------
    # Template Engine
    # ------------------------------------------------------------------

    _DEFAULT_TEMPLATE = (
        "{art|size=56}\n{dday|size=36|bold}\n{label|size=13}  {date:%Y.%m.%d|size=11}"
    )

    def _resolve_dd_template(
        self, template: str, dday_str: str, label: str, target_date: QDate | None
    ) -> str:
        from calendar_app.presentation.widgets.overlay_base import (
            _inject_global_lh,
            _protect_align_tags,
        )

        template = _inject_global_lh(template)
        template = _protect_align_tags(template)

        if target_date is not None and not target_date.isValid():
            target_date = None
        delta = QDate.currentDate().daysTo(target_date) if target_date else 0
        vals = {
            "dday": dday_str,
            "label": label,
            "days": abs(int(delta)) if target_date else "?",
            "sign": ("" if delta == 0 else ("-" if delta > 0 else "+")) if target_date else "-",
            "date": target_date.toString("yyyy.MM.dd") if target_date else "?",
            "date_short": target_date.toString("M.d") if target_date else "?",
        }
        condition_values = dict(vals)
        condition_values["days"] = abs(int(delta))
        template = self._process_conditionals(template, condition_values)

        def _replace(m: re.Match) -> str:
            inner = m.group(1).split("|")
            key, hints = inner[0].strip(), inner[1:]
            if key == "art":
                image = moment_asset_html(
                    self._selected_dialog_asset_pack(),
                    self._selected_dialog_moment(),
                    moment_art_size(hints, self._template_render_font_size()),
                )
                return (
                    _apply_span(image, [h for h in hints if not h.strip().startswith("size=")])
                    if image
                    else EMPTY_MOMENT_ART
                )
            if key.startswith("date:"):
                value = (
                    QLocale().toString(target_date, _strftime_to_qt(key[5:]))
                    if target_date
                    else "?"
                )
                return _apply_span(escape(value), hints)
            value = vals.get(key, "")
            return _apply_span(escape(str(value if value is not None else "")), hints)

        resolved = re.sub(r"\{([^}]+)\}", _replace, template)
        return _apply_align_tags(remove_empty_moment_rows(resolved))

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _open_settings(self):
        extra = [
            {
                "key": "dday_asset_pack",
                "label": t("widget.dday.asset_pack", "일러스트 팩:"),
                "type": "combo",
                "options": [
                    (t(pack.label_key, pack.label_default), pack.pack_id)
                    for pack in moment_asset_packs()
                ],
                "default": DEFAULT_MOMENT_ASSET_PACK_ID,
            },
            {
                "key": "dday_moment",
                "label": t("widget.dday.moment", "장면:"),
                "type": "combo",
                "options": [
                    (t(f"widget.moment.{key}", label), key)
                    for key, label in (
                        ("birthday", "Birthday"),
                        ("anniversary", "Anniversary"),
                        ("deadline", "Deadline"),
                        ("launch", "Launch"),
                        ("travel", "Travel"),
                        ("study", "Study"),
                        ("health", "Health"),
                        ("celebration", "Celebration"),
                        ("calm", "Calm"),
                        ("sparkle", "Sparkle"),
                    )
                ],
                "default": "celebration",
            },
            {
                "key": "dd_label",
                "label": t("widget.dday.name_label", "Label:"),
                "type": "text",
                "default": str(self._get("dd_label", "") or ""),
            },
            {
                "key": "dd_target_date",
                "label": t("widget.dday.target_date", "Target Date:"),
                "type": "date",
                "default": self._get("dd_target_date", QDate.currentDate().toString("yyyy-MM-dd")),
            },
        ]

        def _preview(tmpl: str, fields: dict) -> str:
            dt = QDate.fromString(fields.get("dd_target_date"), "yyyy-MM-dd")
            d_str, _ = self._dd_display(dt, fields.get("dd_label"))
            return self._resolve_dd_template(tmpl, d_str, fields.get("dd_label"), dt)

        if self._open_standard_settings_dialog(
            title=t("widget.dday.settings_title", "D-Day Settings"),
            extra_fields=extra,
            has_template=True,
            default_template=self._DEFAULT_TEMPLATE,
            template_hint=t(
                "widget.dday.template_hint", "{dday}, {days}, {label}, {date:%Y.%m.%d}, {art}"
            ),
            preview_render_fn=lambda tmpl: (
                _preview(
                    tmpl,
                    {k: self._get_field_value(w) for k, w in self._active_settings_widgets.items()},
                )
                if hasattr(self, "_active_settings_widgets")
                else ""
            ),
            extra_basic_setup_fn=self._setup_moment_asset_preview,
        ):
            self._tick_dd()

    def _selected_dialog_asset_pack(self) -> str:
        fields = (
            getattr(self, "_active_settings_widgets", {})
            if self._template_preview_base_size is not None
            else {}
        )
        combo = fields.get("dday_asset_pack")
        value = combo.currentData() if combo is not None and hasattr(combo, "currentData") else None
        return get_moment_asset_pack(
            value or self._get("dday_asset_pack", DEFAULT_MOMENT_ASSET_PACK_ID)
        ).pack_id

    def _selected_dialog_moment(self) -> str:
        fields = (
            getattr(self, "_active_settings_widgets", {})
            if self._template_preview_base_size is not None
            else {}
        )
        combo = fields.get("dday_moment")
        value = combo.currentData() if combo is not None and hasattr(combo, "currentData") else None
        return str(value or self._get("dday_moment", "celebration"))

    def _setup_moment_asset_preview(self, basic, dialog) -> None:
        preview = QLabel(dialog)
        preview.setObjectName("momentAssetPreview")
        preview.setMinimumHeight(104)
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setStyleSheet(
            "QLabel#momentAssetPreview { background: rgba(127, 145, 168, 24); "
            "border: 1px solid rgba(127, 145, 168, 56); border-radius: 12px; }"
        )
        basic.addWidget(preview)
        pack_combo = self._active_settings_widgets["dday_asset_pack"]
        moment_combo = self._active_settings_widgets["dday_moment"]
        pack_combo.setIconSize(QSize(34, 34))
        pack_combo.setMinimumHeight(44)
        for index, pack in enumerate(moment_asset_packs()):
            pack_combo.setItemIcon(index, moment_pack_icon(pack.pack_id))

        def _refresh_preview() -> None:
            preview.setPixmap(moment_pack_preview_pixmap(pack_combo.currentData(), QSize(300, 96)))

        pack_combo.currentIndexChanged.connect(_refresh_preview)
        moment_combo.currentIndexChanged.connect(_refresh_preview)
        _refresh_preview()

    def _build_context_menu(self, menu: QMenu):
        menu.addAction(
            t("widget.dday.date_name_settings", "D-Day Settings..."), self._open_settings
        )
        pack_menu = menu.addMenu(t("widget.dday.asset_pack", "일러스트 팩"))
        current = get_moment_asset_pack(
            self._get("dday_asset_pack", DEFAULT_MOMENT_ASSET_PACK_ID)
        ).pack_id
        for pack in moment_asset_packs():
            action = pack_menu.addAction(
                t(pack.label_key, pack.label_default),
                lambda *_, selected=pack.pack_id: self._set_moment_pack(selected),
            )
            action.setCheckable(True)
            action.setChecked(pack.pack_id == current)
        self._add_reversible_reset_action(
            menu,
            t("widget.dday.clear_all", "Reset D-Day"),
            ("dd_target_date", "dd_label"),
            lambda: (self._set("dd_target_date", ""), self._set("dd_label", ""), self._tick_dd()),
            self._tick_dd,
            enabled=self._dd_target_date() is not None or bool(self._get("dd_label", "")),
        )

    def _set_moment_pack(self, pack_id: str) -> None:
        self._set("dday_asset_pack", get_moment_asset_pack(pack_id).pack_id)
        self._refresh_face()

    def _on_double_click(self) -> bool:
        self._open_settings()
        return True

    def apply_initial_settings(self):
        self._tick_dd()
        self._apply_and_resize()
        self.restore_position(QPoint(-230, 430))
        self._start_dd_timer()
        if self.is_enabled():
            self._show_with_correct_size()
