from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QTextCharFormat
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_editor_styles import (
    build_editor_hint_style,
    build_editor_quick_button_style,
    build_editor_text_style,
    build_settings_style_bundle,
)
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)
from calendar_app.shared.value_parsers import as_bool

# ?? 怨듯넻 移섏닔 ?곸닔 ????????????????????????????????????????????????

_H = 31


def _fit_btn(btn, minimum=76, extra=10):
    # Reduced extra padding and standardized size

    btn.setMinimumHeight(31)

    btn.setMaximumHeight(31)

    width = btn.fontMetrics().horizontalAdvance(btn.text()) + extra

    btn.setMinimumWidth(max(minimum, width))


def _btn_ss(tokens=None, metrics=None):
    return build_editor_quick_button_style(tokens=tokens, metrics=metrics)


def _away_style_bundle(tokens=None, metrics=None):
    tokens = dict(tokens or get_dialog_theme_tokens())
    metrics = dict(metrics or get_dialog_metric_tokens(apply_overrides=True))
    base_bundle = build_settings_style_bundle(tokens, metrics)

    radius = max(6, int(metrics.get("field_radius", 7)))
    tool_radius = max(4, int(metrics.get("toolbutton_radius", 6)))
    accent_soft_bg = tokens.get("accent_soft_bg", "rgba(77,166,255,0.18)")
    accent_soft_border = tokens.get(
        "accent_soft_border", tokens.get("button_primary_border", "rgba(77,166,255,0.55)")
    )
    border = tokens.get("border", "rgba(255,255,255,0.16)")
    border_soft = tokens.get("border_soft", "rgba(255,255,255,0.10)")
    surface_alt = tokens.get("surface_alt", "#1e1e24")
    surface_item = tokens.get("surface_item", "#15151a")
    surface_top = tokens.get("surface_top", "#23232b")
    text_primary = tokens.get("text_primary", "#e1e1e6")

    text_muted = tokens.get("text_muted", "#9aa8b8")
    accent = tokens.get("accent", "#4da6ff")

    custom_bundle = {
        "hint": build_editor_text_style(tokens, tone="faint", font_px=12),
        "html_hint": build_editor_hint_style(tokens, metrics, tone="muted", font_px=11),
        "rich_editor": (
            "QTextEdit { "
            f"background: {surface_top}; "
            f"border: 1px solid {border_soft}; "
            f"border-radius: {radius}px; "
            f"color: {text_primary}; margin: 2px; }}"
        ),
        "html_editor": (
            "QTextEdit { "
            f"background: {surface_item}; "
            f"color: {accent}; "
            f"border: 1px solid {border}; "
            f"border-radius: {radius}px; "
            "font-family: 'Consolas', 'Courier New', monospace; font-size: 11pt; padding: 8px; }"
        ),
        "preview_title": build_editor_text_style(tokens, tone="faint", font_px=12),
        "preview_box": (
            "QFrame { "
            f"background: {surface_item}; "
            f"border: 1px solid {border}; "
            f"border-radius: {radius}px; }}"
        ),
        "preview_label": build_editor_text_style(tokens, tone="primary", font_px=13),
        "toolbar": (
            "#AwayFormatToolbar { "
            f"background: {surface_alt}; "
            f"border: 1px solid {border}; "
            f"border-radius: {radius}px; }}"
        ),
        "tool_btn": (
            f"QToolButton {{ background: transparent; color: {text_muted}; border: none; border-radius: {tool_radius}px; "
            "font-size: 14px; padding: 0; }"
            f"QToolButton:hover {{ background: {tokens.get('button_secondary_hover_bg', surface_top)}; color: {text_primary}; }}"
            f"QToolButton:checked {{ background: {accent_soft_bg}; color: {accent}; border: 1px solid {accent_soft_border}; }}"
        ),
        "align_btn": (
            f"QPushButton {{ background: transparent; color: {text_muted}; border: none; border-radius: {tool_radius}px; "
            "font-size: 12px; padding: 0 10px; }"
            f"QPushButton:hover {{ background: {tokens.get('button_secondary_hover_bg', surface_top)}; color: {text_primary}; }}"
            f"QPushButton:checked {{ background: {accent_soft_bg}; color: {accent}; border: 1px solid {accent_soft_border}; }}"
        ),
        "separator": f"background: {border_soft}; border:none; margin:0 3px;",
        "option_label": build_editor_text_style(tokens, tone="secondary", font_px=13),
        "strong_label": build_editor_text_style(tokens, tone="primary", font_px=13),
        "checkbox_label": build_editor_text_style(tokens, tone="primary", font_px=13),
        "swatch_border": border,
    }
    return {**base_bundle, **custom_bundle}


class AwaySettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.settings = parent.settings if parent else None

        apply_dialog_title(self, t("away_settings.title"))

        apply_common_dialog_style(self, minimum_width=860, size=(900, 800))

        base_font = self.font()

        base_font.setPointSize(11)

        self.setFont(base_font)

        self._ui_tokens = get_dialog_theme_tokens()
        self._dialog_metrics = get_dialog_metric_tokens(apply_overrides=True)
        self._style_bundle = _away_style_bundle(self._ui_tokens, self._dialog_metrics)
        self._fmt_color = QColor(self._ui_tokens.get("accent", "#4da6ff"))
        self._syncing_editors = False

        self._preview_timer = None

        self._html_sync_timer = None

        self._init_ui()

        self._load_settings()

    # ?????????????????????????????????????????????????????????????

    # UI 援ъ꽦

    # ?????????????????????????????????????????????????????????????

    def _init_ui(self):
        root = QVBoxLayout(self)

        root.setSpacing(12)

        root.setContentsMargins(18, 16, 18, 16)

        root.addWidget(self._build_editor_section(), 3)  # 硫붿떆吏 ?몄쭛

        root.addWidget(self._build_options_section(), 2)  # ?좉툑/鍮꾩＜???ㅼ젙

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        root.addLayout(self._build_button_bar())

    # ?? 硫붿떆吏 ?몄쭛湲?(WYSIWYG) ???????????????????????????????????????

    def _build_editor_section(self):
        group = QGroupBox(t("away_settings.msg_group"))

        lay = QVBoxLayout(group)

        lay.setContentsMargins(10, 20, 10, 10)

        lay.setSpacing(8)

        hint = QLabel(t("away_settings.hint_editor"))

        hint.setStyleSheet(self._style_bundle["hint"])

        lay.addWidget(hint)

        self.editor_tabs = QTabWidget()

        rich_tab = QWidget()

        rich_lay = QVBoxLayout(rich_tab)

        rich_lay.setContentsMargins(8, 8, 8, 8)

        rich_lay.setSpacing(6)

        self.msg_edit = QTextEdit()

        self.msg_edit.setAcceptRichText(True)

        self.msg_edit.setPlaceholderText(t("away_settings.placeholder_msg"))

        self.msg_edit.setMinimumHeight(180)

        self.msg_edit.setStyleSheet(self._style_bundle["rich_editor"])

        self.msg_edit.cursorPositionChanged.connect(self._sync_toolbar)

        self.msg_edit.textChanged.connect(self._on_rich_text_changed)

        rich_lay.addWidget(self.msg_edit)

        html_tab = QWidget()

        html_lay = QVBoxLayout(html_tab)

        html_lay.setContentsMargins(8, 8, 8, 8)

        html_lay.setSpacing(6)

        html_tip = QLabel(t("away_settings.html_tip"))

        html_tip.setStyleSheet(self._style_bundle["html_hint"])

        html_lay.addWidget(html_tip)

        self.html_edit = QTextEdit()

        self.html_edit.setMinimumHeight(180)

        self.html_edit.setStyleSheet(self._style_bundle["html_editor"])

        self.html_edit.textChanged.connect(self._on_html_text_changed_debounced)

        html_lay.addWidget(self.html_edit)

        self.editor_tabs.addTab(rich_tab, t("away_settings.tab_rich"))

        self.editor_tabs.addTab(html_tab, t("away_settings.tab_html"))

        self.editor_tabs.currentChanged.connect(self._on_editor_tab_changed)

        lay.addWidget(self.editor_tabs)

        lay.addWidget(self._build_toolbar())

        preview_title = QLabel(t("away_settings.preview"))

        preview_title.setStyleSheet(self._style_bundle["preview_title"])

        lay.addWidget(preview_title)

        preview_box = QFrame()

        preview_box.setMinimumHeight(122)

        preview_box.setStyleSheet(self._style_bundle["preview_box"])

        preview_lay = QVBoxLayout(preview_box)

        preview_lay.setContentsMargins(10, 8, 10, 8)

        preview_lay.setSpacing(0)

        self.preview_lbl = QLabel("")

        self.preview_lbl.setTextFormat(Qt.TextFormat.RichText)

        self.preview_lbl.setWordWrap(True)

        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.preview_lbl.setStyleSheet(self._style_bundle["preview_label"])

        preview_lay.addWidget(self.preview_lbl)

        lay.addWidget(preview_box)

        return group

    # ?? ?쒖떇 ?대컮 ????????????????????????????????????????????????????

    def _build_toolbar(self):
        bar = QWidget()

        bar.setObjectName("AwayFormatToolbar")

        bar.setFixedHeight(31 + 12)

        bar.setStyleSheet(self._style_bundle["toolbar"])

        row = QHBoxLayout(bar)

        row.setContentsMargins(8, 6, 8, 6)

        row.setSpacing(5)

        tb_h = _H
        tool_btn_style = self._style_bundle["tool_btn"]
        align_btn_style = self._style_bundle["align_btn"]

        def _tb_btn(text, tip):
            b = QToolButton()

            b.setText(text)

            b.setCheckable(True)

            b.setToolTip(tip)

            b.setFixedSize(tb_h, tb_h)

            b.setStyleSheet(tool_btn_style)

            return b

        def _fit_text_btn(btn, minimum=42, padding=20):
            width = btn.fontMetrics().horizontalAdvance(btn.text()) + padding

            btn.setMinimumWidth(max(minimum, width))

            btn.setMinimumHeight(tb_h)

            btn.setMaximumHeight(tb_h)

            btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        def _vsep():
            s = QFrame()

            s.setFrameShape(QFrame.Shape.VLine)

            s.setFixedSize(1, max(16, tb_h - 8))

            s.setStyleSheet(self._style_bundle["separator"])

            return s

        self.bold_btn = _tb_btn("B", t("away_settings.btn_bold"))

        bold_font = QFont(self.bold_btn.font())

        bold_font.setBold(True)

        self.bold_btn.setFont(bold_font)

        self.italic_btn = _tb_btn("I", t("away_settings.btn_italic"))

        italic_font = QFont(self.italic_btn.font())

        italic_font.setItalic(True)

        self.italic_btn.setFont(italic_font)

        self.underline_btn = _tb_btn("U", t("away_settings.btn_underline"))

        underline_font = QFont(self.underline_btn.font())

        underline_font.setUnderline(True)

        self.underline_btn.setFont(underline_font)

        row.addWidget(self.bold_btn)

        row.addWidget(self.italic_btn)

        row.addWidget(self.underline_btn)

        row.addWidget(_vsep())

        self.al_btn = QPushButton(t("away_settings.btn_align_left"))

        self.al_btn.setCheckable(True)

        self.al_btn.setToolTip(t("away_settings.btn_align_left"))

        self.al_btn.setStyleSheet(align_btn_style)

        _fit_text_btn(self.al_btn, minimum=62, padding=22)

        self.ac_btn = QPushButton(t("away_settings.btn_align_center"))

        self.ac_btn.setCheckable(True)

        self.ac_btn.setToolTip(t("away_settings.btn_align_center"))

        self.ac_btn.setStyleSheet(align_btn_style)

        _fit_text_btn(self.ac_btn, minimum=70, padding=22)

        self.ar_btn = QPushButton(t("away_settings.btn_align_right"))

        self.ar_btn.setCheckable(True)

        self.ar_btn.setToolTip(t("away_settings.btn_align_right"))

        self.ar_btn.setStyleSheet(align_btn_style)

        _fit_text_btn(self.ar_btn, minimum=70, padding=22)

        row.addWidget(self.al_btn)

        row.addWidget(self.ac_btn)

        row.addWidget(self.ar_btn)

        row.addWidget(_vsep())

        size_lbl = QLabel(t("away_settings.label_size"))

        size_lbl.setStyleSheet(self._style_bundle["option_label"])

        row.addWidget(size_lbl)

        self.size_spin = QSpinBox()

        self.size_spin.setRange(8, 96)

        self.size_spin.setValue(16)

        self.size_spin.setMinimumHeight(31)

        self.size_spin.setMaximumHeight(31)

        self.size_spin.setMinimumWidth(66)

        self.size_spin.setToolTip(t("away_settings.tip_size"))

        row.addWidget(self.size_spin)

        row.addWidget(_vsep())

        self.color_swatch = QPushButton()

        self.color_swatch.setFixedSize(26, 26)

        self.color_swatch.setCheckable(False)

        self.color_swatch.setToolTip(t("away_settings.tip_color"))

        self._refresh_swatch()

        self.color_swatch.clicked.connect(self._pick_color)

        row.addWidget(self.color_swatch)

        row.addStretch()

        self.apply_btn = QPushButton(t("away_settings.btn_apply"))

        self.apply_btn.setCheckable(False)

        self.apply_btn.setToolTip(t("away_settings.tip_apply"))

        self.apply_btn.setObjectName("primary_btn")

        _fit_text_btn(self.apply_btn, minimum=86, padding=24)

        self.clr_btn = QPushButton(t("away_settings.btn_reset"))

        self.clr_btn.setObjectName("ghost_btn")

        _fit_text_btn(self.clr_btn, minimum=86, padding=24)

        row.addWidget(self.apply_btn)

        row.addWidget(self.clr_btn)

        self.bold_btn.clicked.connect(self._toggle_bold)

        self.italic_btn.clicked.connect(self._toggle_italic)

        self.underline_btn.clicked.connect(self._toggle_underline)

        self.al_btn.clicked.connect(lambda: self._set_align(Qt.AlignmentFlag.AlignLeft))

        self.ac_btn.clicked.connect(lambda: self._set_align(Qt.AlignmentFlag.AlignHCenter))

        self.ar_btn.clicked.connect(lambda: self._set_align(Qt.AlignmentFlag.AlignRight))

        self.apply_btn.clicked.connect(self._apply_fmt)

        self.clr_btn.clicked.connect(self._clear_fmt)

        return bar

    # ?? ?듭뀡 ?뱀뀡 (?좉툑 + 鍮꾩＜?? ??以? ????????????????????????????

    def _build_options_section(self):
        group = QGroupBox(t("away_settings.group_settings"))

        outer = QVBoxLayout(group)

        outer.setContentsMargins(10, 20, 10, 10)

        outer.setSpacing(8)

        row = QHBoxLayout()

        row.setSpacing(24)

        row.setAlignment(Qt.AlignmentFlag.AlignTop)

        lock_col = QVBoxLayout()

        lock_col.setSpacing(6)

        lock_col.addWidget(QLabel(t("away_settings.label_lock")))

        iv_row = QHBoxLayout()

        iv_row.setSpacing(8)

        iv_lbl = QLabel(t("away_settings.label_idle_lock"))

        iv_lbl.setStyleSheet(self._style_bundle["strong_label"])

        iv_row.addWidget(iv_lbl)

        self.interval_spin = QSpinBox()
        self.interval_spin.setStyleSheet(self._style_bundle.get("input_spin", ""))

        self.interval_spin.setRange(1, 1440)

        self.interval_spin.setSuffix(t("away_settings.suffix_minute"))

        self.interval_spin.setMinimumHeight(31)

        self.interval_spin.setMinimumWidth(116)

        iv_row.addWidget(self.interval_spin)

        iv_row.addStretch()

        lock_col.addLayout(iv_row)

        self.unlock_idle_radio = QRadioButton(t("away_settings.method_idle"))

        self.unlock_pw_radio = QRadioButton(t("away_settings.method_password"))

        for r in (self.unlock_idle_radio, self.unlock_pw_radio):
            r.setStyleSheet(self._style_bundle["checkbox_label"])

        self.unlock_group = QButtonGroup(self)

        self.unlock_group.addButton(self.unlock_idle_radio)

        self.unlock_group.addButton(self.unlock_pw_radio)

        self.unlock_idle_radio.setChecked(True)

        lock_col.addWidget(self.unlock_idle_radio)

        lock_col.addWidget(self.unlock_pw_radio)

        self.pw_edit = QLineEdit()
        self.pw_edit.setStyleSheet(self._style_bundle.get("input_line", ""))

        self.pw_edit.setEchoMode(QLineEdit.EchoMode.Password)

        self.pw_edit.setPlaceholderText(t("away_settings.placeholder_pw_input"))

        self.pw_edit.setMinimumHeight(31)

        self.pw_edit.setEnabled(False)

        lock_col.addWidget(self.pw_edit)

        lock_col.addStretch()

        self.unlock_pw_radio.toggled.connect(self._set_pw_style)

        self.unlock_idle_radio.toggled.connect(lambda checked: self._set_pw_style(not checked))

        self._set_pw_style(self.unlock_pw_radio.isChecked())

        row.addLayout(lock_col, 1)

        vline = QFrame()

        vline.setFrameShape(QFrame.Shape.VLine)

        vline.setStyleSheet(self._style_bundle["separator"])

        row.addWidget(vline)

        vis_col = QVBoxLayout()

        vis_col.setSpacing(6)

        vis_col.addWidget(QLabel(t("away_settings.label_visual")))

        self.show_clock_cb = QCheckBox(t("away_settings.show_clock"))

        self.show_clock_cb.setStyleSheet(self._style_bundle["checkbox_label"])

        vis_col.addWidget(self.show_clock_cb)

        vis_col.addWidget(QLabel(t("away_settings.label_bg")))

        bg_row = QHBoxLayout()

        bg_row.setSpacing(6)

        self.bg_path_edit = QLineEdit()
        self.bg_path_edit.setStyleSheet(self._style_bundle.get("input_line", ""))

        self.bg_path_edit.setPlaceholderText(t("away_settings.placeholder_bg"))

        self.bg_path_edit.setMinimumHeight(31)

        self.bg_path_edit.setReadOnly(True)

        bg_row.addWidget(self.bg_path_edit, 1)

        br_btn = QPushButton(t("away_settings.btn_browse"))

        br_btn.setObjectName("ghost_btn")

        _fit_btn(br_btn, minimum=68, extra=24)

        br_btn.clicked.connect(self._browse_bg)

        bg_row.addWidget(br_btn)

        clr_bg = QPushButton(t("away_settings.btn_clear"))

        _fit_btn(clr_bg, minimum=62, extra=24)

        clr_bg.setToolTip(t("away_settings.tip_clear_bg"))

        clr_bg.setStyleSheet(_btn_ss(self._ui_tokens, self._dialog_metrics))

        clr_bg.clicked.connect(lambda: self.bg_path_edit.setText(""))

        bg_row.addWidget(clr_bg)

        vis_col.addLayout(bg_row)

        op_row = QHBoxLayout()

        op_row.setSpacing(8)

        op_row.addWidget(QLabel(t("away_settings.label_opacity", "배경 투명도")))

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)

        self.opacity_slider.setRange(20, 100)

        self.opacity_slider.setValue(100)

        self.opacity_slider.setMinimumHeight(24)

        self.op_lbl = QLabel("100%")

        self.op_lbl.setMinimumWidth(42)

        self.opacity_slider.valueChanged.connect(lambda v: self.op_lbl.setText(f"{v}%"))

        op_row.addWidget(self.opacity_slider, 1)

        op_row.addWidget(self.op_lbl)

        vis_col.addLayout(op_row)

        vis_col.addStretch()

        row.addLayout(vis_col, 1)

        outer.addLayout(row)

        return group

    # ?? ?섎떒 踰꾪듉 諛??????????????????????????????????????????????????

    def _build_button_bar(self):
        row = QHBoxLayout()

        row.setSpacing(6)

        row.setContentsMargins(0, 4, 0, 0)

        reset_btn = QPushButton(t("away_settings.btn_default"))

        reset_btn.setObjectName("ghost_btn")

        _fit_btn(reset_btn, minimum=82, extra=28)

        reset_btn.clicked.connect(self._reset_to_default)

        row.addWidget(reset_btn)

        save_btn = QPushButton(t("dialog.common.ok"))

        save_btn.setDefault(True)

        _fit_btn(save_btn, minimum=82, extra=28)

        save_btn.clicked.connect(self._save_settings)

        row.addWidget(save_btn)

        close_btn = QPushButton(t("common.cancel"))

        close_btn.setObjectName("ghost_btn")

        _fit_btn(close_btn, minimum=82, extra=28)

        close_btn.clicked.connect(self.reject)

        row.addWidget(close_btn)

        return row

    # ?????????????????????????????????????????????????????????????

    # ?쒖떇 ?숈옉

    # ?????????????????????????????????????????????????????????????

    def _refresh_swatch(self):
        c = self._fmt_color.name()

        self.color_swatch.setStyleSheet(
            f"background: {c}; border: 1px solid {self._style_bundle['swatch_border']}; border-radius: 12px;"
        )

    def _pick_color(self):
        c = QColorDialog.getColor(self._fmt_color, self, t("away_settings.tip_color"))

        if c.isValid():
            self._fmt_color = c

            self._refresh_swatch()

    def _apply_fmt(self):
        cur = self.msg_edit.textCursor()

        if not cur.hasSelection():
            return

        fmt = QTextCharFormat()

        fmt.setFontPointSize(self.size_spin.value())

        fmt.setForeground(self._fmt_color)

        cur.mergeCharFormat(fmt)

    def _clear_fmt(self):
        cur = self.msg_edit.textCursor()

        if not cur.hasSelection():
            return

        cur.setCharFormat(QTextCharFormat())

    def _toggle_bold(self):
        w = QFont.Weight.Bold if self.bold_btn.isChecked() else QFont.Weight.Normal

        fmt = QTextCharFormat()

        fmt.setFontWeight(w)

        self.msg_edit.textCursor().mergeCharFormat(fmt)

        self.msg_edit.setFontWeight(w)

    def _toggle_italic(self):
        v = self.italic_btn.isChecked()

        fmt = QTextCharFormat()

        fmt.setFontItalic(v)

        self.msg_edit.textCursor().mergeCharFormat(fmt)

        self.msg_edit.setFontItalic(v)

    def _toggle_underline(self):
        v = self.underline_btn.isChecked()

        fmt = QTextCharFormat()

        fmt.setFontUnderline(v)

        self.msg_edit.textCursor().mergeCharFormat(fmt)

        self.msg_edit.setFontUnderline(v)

    def _set_align(self, align):
        self.msg_edit.setAlignment(align)

        self.al_btn.setChecked(align == Qt.AlignmentFlag.AlignLeft)

        self.ac_btn.setChecked(align == Qt.AlignmentFlag.AlignHCenter)

        self.ar_btn.setChecked(align == Qt.AlignmentFlag.AlignRight)

    def _sync_toolbar(self):
        fmt = self.msg_edit.currentCharFormat()

        self.bold_btn.setChecked(fmt.fontWeight() >= QFont.Weight.Bold)

        self.italic_btn.setChecked(fmt.fontItalic())

        self.underline_btn.setChecked(fmt.fontUnderline())

        align = self.msg_edit.alignment()

        self.al_btn.setChecked(align == Qt.AlignmentFlag.AlignLeft)

        self.ac_btn.setChecked(align == Qt.AlignmentFlag.AlignHCenter)

        self.ar_btn.setChecked(align == Qt.AlignmentFlag.AlignRight)

        pt = fmt.fontPointSize()

        if pt > 0:
            self.size_spin.blockSignals(True)

            self.size_spin.setValue(int(pt))

            self.size_spin.blockSignals(False)

    # ?????????????????????????????????????????????????????????????

    # HTML ?뚯뒪

    # ?????????????????????????????????????????????????????????????

    def _on_editor_tab_changed(self, index):
        if index == 1:
            self._sync_html_from_rich()

        else:
            self._sync_rich_from_html()

    def _sync_html_from_rich(self):
        if self._syncing_editors:
            return

        self._syncing_editors = True

        self.html_edit.setPlainText(self.msg_edit.toHtml())

        self._syncing_editors = False

    def _sync_rich_from_html(self):
        if self._syncing_editors:
            return

        self._syncing_editors = True

        self.msg_edit.setHtml(self.html_edit.toPlainText())

        self._syncing_editors = False

        self._refresh_preview()

    def _on_html_text_changed_debounced(self):
        if self._syncing_editors:
            return

        if self._html_sync_timer is None:
            from PyQt6.QtCore import QTimer

            self._html_sync_timer = QTimer(self)

            self._html_sync_timer.setSingleShot(True)

            self._html_sync_timer.timeout.connect(self._sync_rich_from_html)

        self._html_sync_timer.start(300)

    def _on_rich_text_changed(self):
        if self._syncing_editors:
            return

        self._sync_html_from_rich()

        self._refresh_preview()

    def _refresh_preview(self):
        if not hasattr(self, "preview_lbl"):
            return

        if self._preview_timer is None:
            from PyQt6.QtCore import QTimer

            self._preview_timer = QTimer(self)

            self._preview_timer.setSingleShot(True)

            self._preview_timer.timeout.connect(self._do_refresh_preview)

        self._preview_timer.start(150)

    def _do_refresh_preview(self):
        if hasattr(self, "preview_lbl"):
            self.preview_lbl.setText(self.msg_edit.toHtml())

    # ?????????????????????????????????????????????????????????????

    # 鍮꾩＜???ы띁

    # ?????????????????????????????????????????????????????????????

    def _set_pw_style(self, enabled):
        self.pw_edit.setEnabled(enabled)

        # Global style handles focus/enable states

    def _browse_bg(self):
        p, _ = QFileDialog.getOpenFileName(
            self,
            t("away_settings.pick_bg_title"),
            "",
            "?대?吏 ?뚯씪 (*.png *.jpg *.jpeg *.bmp *.webp)",
        )

        if p:
            self.bg_path_edit.setText(p)

    def _group_ss(self):
        return ""

    # ?????????????????????????????????????????????????????????????

    # ?ㅼ젙 濡쒕뱶 / ???/ 珥덇린??

    # ?????????????????????????????????????????????????????????????

    def _default_message_html(self):
        if not self.settings:
            return t("away_lock.default_msg")

        return self.settings.value("away_default_message", t("away_lock.default_msg"))

    def _load_settings(self):
        if not self.settings:
            self._reset_to_default()

            return

        raw = self.settings.value("away_message", self._default_message_html())

        raw = str(raw or "")

        if raw.strip().startswith("<"):
            self.msg_edit.setHtml(raw)

        else:
            self.msg_edit.setPlainText(raw)

        self.interval_spin.setValue(int(self.settings.value("away_interval", 5)))

        if self.settings.value("away_unlock_method", "idle") == "password":
            self.unlock_pw_radio.setChecked(True)

        else:
            self.unlock_idle_radio.setChecked(True)

        self._set_pw_style(self.unlock_pw_radio.isChecked())

        self.pw_edit.setText(self.settings.value("away_password", ""))

        saved_color = self.settings.value(
            "away_font_color", self._ui_tokens.get("accent", "#4da6ff")
        )

        self._fmt_color = QColor(saved_color)

        self._refresh_swatch()

        self.show_clock_cb.setChecked(
            as_bool(self.settings.value("away_show_clock", True), default=True)
        )

        self.bg_path_edit.setText(self.settings.value("away_bg_path", ""))

        self.opacity_slider.setValue(int(self.settings.value("away_bg_opacity", 100)))

        self.editor_tabs.setCurrentIndex(0)

        self._sync_html_from_rich()

        self._refresh_preview()

    def _reset_to_default(self):
        self.msg_edit.setHtml(self._default_message_html())

        self.interval_spin.setValue(5)

        self.unlock_idle_radio.setChecked(True)

        self.pw_edit.setText("")

        self._fmt_color = QColor(self._ui_tokens.get("accent", "#4da6ff"))

        self._refresh_swatch()

        self.show_clock_cb.setChecked(True)

        self.bg_path_edit.setText("")

        self.opacity_slider.setValue(100)

        self.editor_tabs.setCurrentIndex(0)

        self._sync_html_from_rich()

        self._refresh_preview()

    def _save_settings(self):
        if not self._persist_settings():
            return

        self.accept()

    def _persist_settings(self):
        if not self._validate_settings():
            return False

        s = self.settings

        form_values = self._collect_form_settings()

        for key, value in form_values.items():
            s.setValue(key, value)

        parent = self.parent()

        if parent and hasattr(parent, "alarm_worker"):
            parent.alarm_worker.update_idle_timeout(self.interval_spin.value())

        return True

    def _validate_settings(self):
        if self.unlock_pw_radio.isChecked() and not self.pw_edit.text().strip():
            QMessageBox.warning(self, t("common.warning"), t("away_settings.err_pw_required"))

            return False

        return True

    def _collect_form_settings(self):
        if self.editor_tabs.currentIndex() == 1:
            self.msg_edit.setHtml(self.html_edit.toPlainText())

        return {
            "away_message": self.msg_edit.toHtml(),
            "away_interval": self.interval_spin.value(),
            "away_unlock_method": "password" if self.unlock_pw_radio.isChecked() else "idle",
            "away_password": self.pw_edit.text(),
            "away_font_color": self._fmt_color.name(),
            "away_show_clock": self.show_clock_cb.isChecked(),
            "away_bg_path": self.bg_path_edit.text(),
            "away_bg_opacity": self.opacity_slider.value(),
        }
