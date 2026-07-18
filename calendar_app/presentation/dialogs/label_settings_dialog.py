"""Dialog for customizing priority/status icon and text labels."""

from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from calendar_app.domain import task_constants
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_editor_styles import (
    build_editor_quick_button_style,
    build_editor_text_style,
    build_settings_dialog_stylesheet,
    build_settings_style_bundle,
)
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_collapsible_section,
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)

# ?? ?대え吏 ?붾젅???곗씠?????????????????????????????????????
_EMOJI_PALETTE = {
    t("dialog.label_settings.emoji_categories.priority"): [
        "\U0001f525",
        "\U0001f6a8",
        "\u2b50",
        "\u26a1",
        "\U0001f4cc",
        "\U0001f3af",
        "\u2705",
        "\u23f0",
        "\U0001f4cd",
        "\U0001f9ed",
        "\U0001f6d1",
        "\U0001f534",
        "\U0001f7e0",
        "\U0001f7e1",
        "\U0001f7e2",
        "\U0001f535",
        "\U0001f7e3",
        "\u26a0\ufe0f",
        "\u2757",
        "\u2755",
        "1\ufe0f\u20e3",
        "2\ufe0f\u20e3",
        "3\ufe0f\u20e3",
        "4\ufe0f\u20e3",
        "5\ufe0f\u20e3",
        "\u2b06\ufe0f",
        "\u2b07\ufe0f",
        "\u2705",
        "\u274c",
        "\u23f3",
    ],
    t("dialog.label_settings.emoji_categories.status"): [
        "\U0001f195",
        "\U0001f4e5",
        "\U0001f4dd",
        "\U0001f504",
        "\u23f3",
        "\u231b",
        "\U0001f6a7",
        "\U0001f3c3",
        "\u2705",
        "\u2714\ufe0f",
        "\u2611\ufe0f",
        "\U0001f4cc",
        "\U0001f4c5",
        "\U0001f4cd",
        "\U0001f6e0\ufe0f",
        "\U0001f9ea",
        "\U0001f4e4",
        "\U0001f4e6",
        "\U0001f512",
        "\U0001f513",
        "\U0001f7e2",
        "\U0001f7e1",
        "\U0001f534",
        "\u26aa",
        "\u26ab",
        "\U0001f552",
        "\U0001f558",
        "\U0001f55b",
        "\U0001f680",
        "\U0001f3c1",
    ],
    t("dialog.label_settings.emoji_categories.face"): [
        "\U0001f600",
        "\U0001f603",
        "\U0001f604",
        "\U0001f601",
        "\U0001f606",
        "\U0001f605",
        "\U0001f602",
        "\U0001f923",
        "\U0001f60a",
        "\U0001f642",
        "\U0001f609",
        "\U0001f60d",
        "\U0001f618",
        "\U0001f617",
        "\U0001f619",
        "\U0001f61a",
        "\U0001f60b",
        "\U0001f61b",
        "\U0001f61c",
        "\U0001f92a",
        "\U0001f928",
        "\U0001f9d0",
        "\U0001f913",
        "\U0001f60e",
        "\U0001f973",
        "\U0001f634",
        "\U0001f92f",
        "\U0001f607",
        "\U0001f917",
        "\U0001f914",
    ],
    t("dialog.label_settings.emoji_categories.nature"): [
        "\U0001f33f",
        "\U0001f331",
        "\U0001f335",
        "\U0001f334",
        "\U0001f333",
        "\U0001f332",
        "\U0001f338",
        "\U0001f33c",
        "\U0001f33b",
        "\U0001f33a",
        "\U0001f337",
        "\U0001f339",
        "\U0001f340",
        "\U0001f341",
        "\U0001f342",
        "\U0001f343",
        "\U0001f436",
        "\U0001f431",
        "\U0001f42d",
        "\U0001f439",
        "\U0001f430",
        "\U0001f98a",
        "\U0001f43b",
        "\U0001f43c",
        "\U0001f428",
        "\U0001f42f",
        "\U0001f981",
        "\U0001f42e",
        "\U0001f437",
        "\U0001f438",
    ],
    t("dialog.label_settings.emoji_categories.food"): [
        "\U0001f34e",
        "\U0001f34a",
        "\U0001f34c",
        "\U0001f349",
        "\U0001f347",
        "\U0001f353",
        "\U0001f352",
        "\U0001f34d",
        "\U0001f95d",
        "\U0001f951",
        "\U0001f966",
        "\U0001f955",
        "\U0001f33d",
        "\U0001f345",
        "\U0001f346",
        "\U0001f954",
        "\U0001f35e",
        "\U0001f950",
        "\U0001f956",
        "\U0001f9c0",
        "\U0001f373",
        "\U0001f953",
        "\U0001f354",
        "\U0001f355",
        "\U0001f363",
        "\U0001f35c",
        "\U0001f957",
        "\U0001f369",
        "\U0001f36a",
        "\U0001f36b",
    ],
    t("dialog.label_settings.emoji_categories.activity"): [
        "\u26bd",
        "\U0001f3c0",
        "\U0001f3c8",
        "\u26be",
        "\U0001f3be",
        "\U0001f3d0",
        "\U0001f3c9",
        "\U0001f3b1",
        "\U0001f3d3",
        "\U0001f3f8",
        "\U0001f94a",
        "\U0001f94b",
        "\U0001f3ae",
        "\U0001f3af",
        "\U0001f3b2",
        "\U0001f9e9",
        "\U0001f3b5",
        "\U0001f3a7",
        "\U0001f3a4",
        "\U0001f3b9",
        "\U0001f3b8",
        "\U0001f3bb",
        "\U0001f941",
        "\U0001f4f7",
        "\U0001f3ac",
        "\U0001f3a8",
        "\U0001f9ea",
        "\U0001f4da",
        "\u2708\ufe0f",
        "\U0001f9d7",
    ],
    t("dialog.label_settings.emoji_categories.travel"): [
        "\U0001f697",
        "\U0001f695",
        "\U0001f699",
        "\U0001f68c",
        "\U0001f68e",
        "\U0001f3ce\ufe0f",
        "\U0001f693",
        "\U0001f691",
        "\U0001f692",
        "\U0001f69a",
        "\U0001f69b",
        "\U0001f69c",
        "\U0001f6f5",
        "\U0001f3cd\ufe0f",
        "\U0001f6b2",
        "\U0001f6f4",
        "\U0001f681",
        "\u2708\ufe0f",
        "\U0001f680",
        "\U0001f6f8",
        "\U0001f6a2",
        "\u26f5",
        "\U0001f6a4",
        "\U0001f6f6",
        "\U0001f686",
        "\U0001f684",
        "\U0001f687",
        "\U0001f689",
        "\U0001f5fa\ufe0f",
        "\U0001f9ed",
    ],
    t("dialog.label_settings.emoji_categories.object"): [
        "\U0001f4a1",
        "\U0001f526",
        "\U0001f9ef",
        "\U0001f50b",
        "\U0001f50c",
        "\U0001f4bb",
        "\u2328\ufe0f",
        "\U0001f5b1\ufe0f",
        "\U0001f5a8\ufe0f",
        "\U0001f4f1",
        "\u260e\ufe0f",
        "\U0001f4f7",
        "\U0001f4f9",
        "\U0001f50d",
        "\U0001f512",
        "\U0001f511",
        "\U0001f9f0",
        "\U0001f6e0\ufe0f",
        "\U0001f527",
        "\U0001f528",
        "\U0001fa9b",
        "\u2699\ufe0f",
        "\U0001f4cc",
        "\U0001f4ce",
        "\u2702\ufe0f",
        "\U0001f4d0",
        "\U0001f4cf",
        "\U0001f5c2\ufe0f",
        "\U0001f4e6",
        "\U0001f5d1\ufe0f",
    ],
    t("dialog.label_settings.emoji_categories.symbol"): [
        "\u2764\ufe0f",
        "\U0001f9e1",
        "\U0001f49b",
        "\U0001f49a",
        "\U0001f499",
        "\U0001f49c",
        "\U0001f90d",
        "\U0001f5a4",
        "\U0001f90e",
        "\U0001f494",
        "\u2763\ufe0f",
        "\U0001f495",
        "\U0001f4af",
        "\u2728",
        "\u26a0\ufe0f",
        "\u2757",
        "\u2753",
        "\U0001f514",
        "\U0001f515",
        "\u2705",
        "\u2611\ufe0f",
        "\u274c",
        "\u2b55",
        "\u2795",
        "\u2796",
        "\u2797",
        "\u267b\ufe0f",
        "\U0001f501",
        "\U0001f502",
        "\u3030\ufe0f",
    ],
}


# priority/status display labels
def _get_priority_display():
    return {
        "urgent": t("priority.urgent"),
        "high": t("priority.high"),
        "normal": t("priority.normal"),
        "low": t("priority.low"),
    }


def _get_status_display():
    return {
        "pending": t("status.pending"),
        "in_progress": t("status.in_progress"),
        "completed": t("status.completed"),
        "deferred": t("status.deferred"),
    }


def _label_settings_style_bundle(tokens=None, metrics=None):
    tokens = dict(tokens or get_dialog_theme_tokens())
    metrics = dict(metrics or get_dialog_metric_tokens(apply_overrides=True))
    base_bundle = build_settings_style_bundle(tokens, metrics)

    base_font_px = max(12, int(metrics.get("base_font_pt", 14)))
    field_radius = max(6, int(metrics.get("field_radius", 7)))
    border_soft = tokens.get("border_soft", "rgba(255,255,255,0.10)")
    surface_alt = tokens.get("surface_alt", "#1c1c23")
    surface_hover = tokens.get("surface_hover", "#18181f")
    text_primary = tokens.get("text_primary", "#ffffff")

    custom_bundle = {
        "hint": build_editor_text_style(
            tokens, tone="muted", font_px=max(11, base_font_px - 3), padding="0 2px"
        ),
        "scroll_shell": "QScrollArea { background: transparent; border: none; }",
        "inner_shell": "background: transparent;",
        "divider": f"background: {border_soft}; max-height: 1px; margin: 2px 0;",
        "header": build_editor_text_style(
            tokens, tone="muted", font_px=max(11, base_font_px - 3), weight=400
        ),
        "row_label": build_editor_text_style(
            tokens, tone="secondary", font_px=max(12, base_font_px - 1), weight=700
        ),
        "icon_edit": (
            f"font-size: {max(16, base_font_px + 2)}px; padding: 1px 2px; "
            f"border-radius: {field_radius}px;"
        ),
        "picker_button": (
            "QToolButton { "
            f"background: {surface_alt}; color: {text_primary}; border: 1px solid {border_soft}; "
            f"border-radius: {field_radius}px; font-size: {max(15, base_font_px + 1)}px; "
            "}"
            "QToolButton:hover { "
            f"background: {surface_hover}; border-color: {tokens.get('accent', '#4da6ff')}; "
            "}"
        ),
        "text_edit": f"padding: 2px 8px; border-radius: {field_radius}px;",
        "button_secondary": build_editor_quick_button_style(tokens, metrics, tone="secondary"),
        "button_accent": build_editor_quick_button_style(tokens, metrics, tone="accent"),
        "button_danger": build_editor_quick_button_style(tokens, metrics, tone="danger"),
    }
    return {**base_bundle, **custom_bundle}


def _emoji_picker_stylesheet(tokens=None, metrics=None) -> str:
    tokens = dict(tokens or get_dialog_theme_tokens())
    metrics = dict(metrics or get_dialog_metric_tokens(apply_overrides=True))
    field_radius = max(6, int(metrics.get("field_radius", 7)))
    border = tokens.get("border", "rgba(255,255,255,0.16)")
    border_soft = tokens.get("border_soft", "rgba(255,255,255,0.10)")
    surface_bg = tokens.get("surface_bg", "#16161b")
    surface_alt = tokens.get("surface_alt", "#1c1c23")
    surface_item = tokens.get("surface_item", "#111116")
    surface_hover = tokens.get("surface_hover", "#18181f")
    accent = tokens.get("accent", "#4da6ff")
    text_primary = tokens.get("text_primary", "#ffffff")
    text_muted = tokens.get("text_muted", "#aaa")
    return f"""
QDialog {{
    background-color: {surface_bg};
    border: 1px solid {border};
    border-radius: {field_radius + 1}px;
}}
QTabWidget::pane {{
    border: none;
    background: {surface_bg};
}}
QTabBar::tab {{
    background: {surface_alt};
    color: {text_muted};
    padding: 5px 12px;
    font-size: 12px;
    border-radius: 4px 4px 0 0;
    border: 1px solid {border_soft};
}}
QTabBar::tab:selected {{
    background: {accent};
    color: {text_primary};
    font-weight: bold;
}}
QPushButton {{
    background: {surface_item};
    color: {text_primary};
    border: 1px solid {border_soft};
    border-radius: {field_radius}px;
    font-size: 18px;
    padding: 2px;
    min-width: 36px;
    min-height: 36px;
    max-width: 36px;
    max-height: 36px;
}}
QPushButton:hover {{
    background: {surface_hover};
    color: {accent};
    border-color: {accent};
}}
""".strip()


# ?? ?대え吏 ?쎌빱 ?앹뾽 ??????????????????????????????????????


# ?€?€ ?대え吏€ ?쎌빱 ?앹뾽 ?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€
class EmojiPickerPopup(QDialog):
    """Category-tabbed emoji picker popup."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(_emoji_picker_stylesheet())
        self.selected_emoji = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        for category, emojis in _EMOJI_PALETTE.items():
            tab_widget = QWidget()
            grid = QGridLayout(tab_widget)
            grid.setSpacing(3)
            grid.setContentsMargins(4, 4, 4, 4)
            cols = 12

            for idx, emoji in enumerate(emojis):
                btn = QPushButton(emoji)
                btn.setToolTip(emoji)
                btn.clicked.connect(lambda _, e=emoji: self._select(e))
                grid.addWidget(btn, idx // cols, idx % cols)
            tabs.addTab(tab_widget, category)

        layout.addWidget(tabs)

    def _select(self, emoji: str):
        self.selected_emoji = emoji
        self.accept()

    def show_near(self, widget):
        """Show popup right below the given widget."""
        pos = widget.mapToGlobal(QPoint(0, widget.height() + 2))
        self.move(pos)
        self.adjustSize()
        self.exec()


class EmojiLineEdit(QLineEdit):
    """Windows emoji panel (Win + .) input-friendly line edit.

    This version avoids problematic top-level window flags and modality
    that can cause crashes when embedded in layouts.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setInputMethodHints(Qt.InputMethodHint.ImhNone)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        # Ensure the parent window is active to receive IME events
        if self.window():
            self.window().activateWindow()
        QTimer.singleShot(0, self._reactivate_input_target)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if self.window():
            self.window().activateWindow()
        QTimer.singleShot(0, self._reactivate_input_target)

    def _reactivate_input_target(self):
        if not self.hasFocus():
            return
        try:
            from PyQt6.QtGui import QGuiApplication

            im = QGuiApplication.inputMethod()
            if im:
                im.update(Qt.InputMethodQuery.ImEnabled)
        except Exception:
            pass


# ?€?€ 硫붿씤 ?ㅼ씠?쇰줈洹??€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€?€
class LabelSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        apply_dialog_title(self, t("dialog.label_settings.title"))
        # Keep width slightly wider and reduce default height for denser layout.
        apply_common_dialog_style(self, minimum_width=680, size=(760, 610))
        self._ui_tokens = get_dialog_theme_tokens()
        self._dialog_metrics = get_dialog_metric_tokens(apply_overrides=True)
        self._style_bundle = _label_settings_style_bundle(self._ui_tokens, self._dialog_metrics)
        self._init_ui()
        # Defer value binding to let the dialog paint faster first.
        QTimer.singleShot(0, self._load_current_values)

    def showEvent(self, event):
        super().showEvent(event)
        self.raise_()
        self.activateWindow()

    # ??????????????????????????????????????????????
    # UI 援ъ꽦
    # ??????????????????????????????????????????????
    def _init_ui(self):
        self.setStyleSheet(build_settings_dialog_stylesheet(self._ui_tokens))
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(16, 14, 16, 14)

        # ?? ?꾨━???곸뿭 ??????????????????????????
        preset_group = QFrame()
        preset_group.setObjectName("card")
        preset_group.setStyleSheet(self._style_bundle.get("card", ""))
        preset_layout = QVBoxLayout(preset_group)
        preset_layout.setContentsMargins(20, 20, 20, 20)
        preset_layout.setSpacing(12)

        lbl_preset = QLabel(t("dialog.label_settings.preset_group"))
        lbl_preset.setStyleSheet(self._style_bundle.get("card_title", ""))
        preset_layout.addWidget(lbl_preset)

        div_preset = QFrame()
        div_preset.setFrameShape(QFrame.Shape.HLine)
        div_preset.setStyleSheet(self._style_bundle.get("divider", ""))
        preset_layout.addWidget(div_preset)

        # ?댁옣 ?꾨━??踰꾪듉 ??
        builtin_row = QHBoxLayout()
        builtin_row.addWidget(QLabel(t("dialog.label_settings.builtin")))
        for name in task_constants.BUILTIN_PRESETS:
            display_name = t(f"dialog.label_settings.builtin_presets.{name}", name)
            btn = QPushButton(display_name)
            btn.setStyleSheet(self._style_bundle["button_secondary"])
            btn.setMinimumHeight(31)
            btn.clicked.connect(lambda _, n=name: self._apply_builtin_preset(n))
            builtin_row.addWidget(btn)
        builtin_row.addStretch()
        preset_layout.addLayout(builtin_row)

        # ?ъ슜???꾨━????
        user_row = QHBoxLayout()
        user_row.addWidget(QLabel(t("dialog.label_settings.user")))
        self.user_preset_combo = QComboBox()
        self.user_preset_combo.setMinimumWidth(150)
        self.user_preset_combo.setMinimumHeight(31)
        self._refresh_user_preset_combo()
        user_row.addWidget(self.user_preset_combo)

        load_btn = QPushButton(t("dialog.label_settings.load"))
        load_btn.setStyleSheet(self._style_bundle["button_secondary"])
        load_btn.setMinimumHeight(31)
        load_btn.clicked.connect(self._load_user_preset)
        user_row.addWidget(load_btn)

        save_preset_btn = QPushButton(t("dialog.label_settings.save_current"))
        save_preset_btn.setStyleSheet(self._style_bundle["button_secondary"])
        save_preset_btn.setMinimumHeight(31)
        save_preset_btn.clicked.connect(self._save_user_preset)
        user_row.addWidget(save_preset_btn)

        del_preset_btn = QPushButton(t("dialog.label_settings.delete"))
        del_preset_btn.setMinimumHeight(31)
        del_preset_btn.setStyleSheet(self._style_bundle["button_danger"])
        del_preset_btn.clicked.connect(self._delete_user_preset)
        user_row.addWidget(del_preset_btn)

        user_row.addStretch()
        preset_layout.addLayout(user_row)

        preset_section_layout, _ = build_collapsible_section(
            t("dialog.label_settings.preset_group", "프리셋"),
            preset_group,
            expanded=False,
            settings_key="label_settings_preset_expanded",
        )
        root.addLayout(preset_section_layout)

        # ?? ?낅젰 ?덈궡 ????????????????????????????
        hint = QLabel(t("dialog.label_settings.hint"))
        hint.setStyleSheet(self._style_bundle["hint"])
        root.addWidget(hint)

        # ?? ?ㅽ겕濡??곸뿭 (以묒슂??+ ?곹깭) ??????????
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(self._style_bundle["scroll_shell"])

        inner = QWidget()
        inner.setStyleSheet(self._style_bundle["inner_shell"])
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(10)
        inner_layout.setContentsMargins(0, 0, 0, 0)

        # 以묒슂??洹몃９
        prio_group = QFrame()
        prio_group.setObjectName("card")
        prio_group.setStyleSheet(self._style_bundle.get("card", ""))
        prio_v = QVBoxLayout(prio_group)
        prio_v.setContentsMargins(20, 20, 20, 20)

        lbl_prio = QLabel(t("dialog.label_settings.priority_group"))
        lbl_prio.setStyleSheet(self._style_bundle.get("card_title", ""))
        prio_v.addWidget(lbl_prio)

        div_prio = QFrame()
        div_prio.setFrameShape(QFrame.Shape.HLine)
        div_prio.setStyleSheet(self._style_bundle.get("divider", ""))
        prio_v.addWidget(div_prio)

        prio_grid_w = QWidget()
        prio_grid = QGridLayout(prio_grid_w)
        prio_grid.setHorizontalSpacing(10)
        prio_grid.setVerticalSpacing(8)
        prio_grid.setContentsMargins(0, 0, 0, 0)
        prio_v.addWidget(prio_grid_w)
        self._add_header_row(prio_grid, 0)
        self.prio_fields = {}
        for idx, (key, display) in enumerate(_get_priority_display().items()):
            row_idx = idx + 1
            self.prio_fields[key] = self._add_row(prio_grid, row_idx, display, 0)
        prio_grid.setColumnStretch(3, 1)
        prio_group.setMinimumWidth(340)

        # ?곹깭 洹몃９
        status_group = QFrame()
        status_group.setObjectName("card")
        status_group.setStyleSheet(self._style_bundle.get("card", ""))
        status_v = QVBoxLayout(status_group)
        status_v.setContentsMargins(20, 20, 20, 20)

        lbl_status = QLabel(t("dialog.label_settings.status_group"))
        lbl_status.setStyleSheet(self._style_bundle.get("card_title", ""))
        status_v.addWidget(lbl_status)

        div_status = QFrame()
        div_status.setFrameShape(QFrame.Shape.HLine)
        div_status.setStyleSheet(self._style_bundle.get("divider", ""))
        status_v.addWidget(div_status)

        status_grid_w = QWidget()
        status_grid = QGridLayout(status_grid_w)
        status_grid.setHorizontalSpacing(10)
        status_grid.setVerticalSpacing(8)
        status_grid.setContentsMargins(0, 0, 0, 0)
        status_v.addWidget(status_grid_w)
        self._add_header_row(status_grid, 0)
        self.status_fields = {}
        for idx, (key, display) in enumerate(_get_status_display().items()):
            row_idx = idx + 1
            self.status_fields[key] = self._add_row(status_grid, row_idx, display, 0)
        status_grid.setColumnStretch(3, 1)
        status_group.setMinimumWidth(340)

        two_col_row = QHBoxLayout()
        two_col_row.setSpacing(10)
        two_col_row.addWidget(prio_group, 1)
        two_col_row.addWidget(status_group, 1)
        inner_layout.addLayout(two_col_row)

        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        # ?? ?섎떒 踰꾪듉 ??????????????????????????
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(self._style_bundle["divider"])
        root.addWidget(divider)

        btn_row = QHBoxLayout()
        self.reset_btn = QPushButton(t("dialog.label_settings.reset"))
        self.reset_btn.setObjectName("danger_btn")
        self.reset_btn.clicked.connect(self._reset_to_default)
        btn_row.addWidget(self.reset_btn)
        btn_row.addStretch()

        self.save_btn = QPushButton(t("dialog.common.save"))
        self.save_btn.setObjectName("primary_btn")
        self.save_btn.setStyleSheet(self._style_bundle["button_accent"])
        self.save_btn.clicked.connect(self._save)
        btn_row.addWidget(self.save_btn)

        self.cancel_btn = QPushButton(t("dialog.common.cancel"))
        self.cancel_btn.setObjectName("ghost_btn")
        self.cancel_btn.setStyleSheet(self._style_bundle["button_secondary"])
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        root.addLayout(btn_row)

    def _add_header_row(self, grid, col_offset=0):
        headers = [
            t("dialog.label_settings.header_type"),
            t("dialog.label_settings.header_icon"),
            "",
            t("dialog.label_settings.header_name"),
        ]

        for col, text in enumerate(headers):
            lbl = QLabel(text)
            lbl.setStyleSheet(self._style_bundle["header"])
            grid.addWidget(lbl, 0, col + col_offset)

    def _add_row(self, grid, row, display_name, col_offset=0):
        """Add one editable row and return icon/text editors."""
        # col 0: 구분 이름 (긴급, 높음, … / 예정, 진행중, …)
        lbl = QLabel(display_name)
        lbl.setStyleSheet(self._style_bundle["row_label"])
        grid.addWidget(lbl, row, col_offset + 0)

        # col 1: ?꾩씠肄?吏곸젒 ?낅젰
        # setMaxLength 誘몄궗????UTF-16 surrogate pair 怨꾩궛 ?ㅻ쪟濡??대え吏 ?낅젰 李⑤떒??
        # ???textChanged ?쒓렇?먯뿉??肄붾뱶?ъ씤??湲곗? 4??珥덇낵遺??섎씪??
        icon_edit = EmojiLineEdit()
        icon_edit.setFixedWidth(68)
        icon_edit.setMinimumHeight(31)
        icon_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_edit.setStyleSheet(self._style_bundle["icon_edit"])
        icon_edit.setPlaceholderText(t("dialog.label_settings.emoji_placeholder"))
        # Win + . ?대え吏 패널? 議고빀 ?낅젰??嫄곗튂誘濡??낅젰 以묒뿉???먮Ⅴ吏 ?딅뒗??
        # ????몄쭛???앸궗???뚮쭔 ??μ슜 湲몄씠濡??뺣━?쒕떎.
        icon_edit.editingFinished.connect(lambda ie=icon_edit: self._normalize_icon_edit(ie))
        grid.addWidget(icon_edit, row, col_offset + 1)

        # col 2: ?붾젅???닿린 踰꾪듉
        picker_btn = QToolButton()
        picker_btn.setText(chr(0x1F600))
        picker_btn.setFixedSize(31, 31)
        picker_btn.setToolTip(t("dialog.label_settings.open_palette"))
        picker_btn.setStyleSheet(self._style_bundle["picker_button"])
        picker_btn.clicked.connect(lambda _, ie=icon_edit, pb=picker_btn: self._open_picker(ie, pb))
        grid.addWidget(picker_btn, row, col_offset + 2)

        # col 3: 텍스트?낅젰
        text_edit = QLineEdit()
        text_edit.setMaxLength(10)
        text_edit.setMinimumWidth(100)
        text_edit.setMinimumHeight(31)
        text_edit.setStyleSheet(self._style_bundle["text_edit"])
        grid.addWidget(text_edit, row, col_offset + 3)

        # ?ㅼ떆媛??곕룞 (?꾩슂 ??濡쒖쭅 泥섎━)

        icon_edit.textChanged.connect(lambda _: self._update_previews())

        text_edit.textChanged.connect(lambda _: self._update_previews())

        return (icon_edit, text_edit)

    def _open_picker(self, icon_edit: QLineEdit, anchor_widget):
        """Open emoji picker and apply selected emoji to icon_edit."""

        popup = EmojiPickerPopup(self)

        popup.show_near(anchor_widget)

        if popup.selected_emoji:
            icon_edit.setText(popup.selected_emoji)

            self._normalize_icon_edit(icon_edit)

            icon_edit.setFocus()

    # ??????????????????????????????????????????????

    # ?곗씠??濡쒕뱶/???
    # ??????????????????????????????????????????????

    def _load_current_values(self):
        current = task_constants.get_current_labels()

        for key, (icon_edit, text_edit) in self.prio_fields.items():
            icon_edit.setText(current["priority"][key]["icon"])

            text_edit.setText(current["priority"][key]["text"])

        for key, (icon_edit, text_edit) in self.status_fields.items():
            icon_edit.setText(current["status"][key]["icon"])

            text_edit.setText(current["status"][key]["text"])

        self._update_previews()

    def _collect_data(self):
        priority_data = {
            key: {
                "icon": self._normalized_icon_text(icon_edit.text())
                or task_constants._DEFAULT_PRIORITY_ICON[key],
                "text": text_edit.text().strip() or task_constants._DEFAULT_PRIORITY_TEXT[key],
            }
            for key, (icon_edit, text_edit) in self.prio_fields.items()
        }

        status_data = {
            key: {
                "icon": self._normalized_icon_text(icon_edit.text())
                or task_constants._DEFAULT_STATUS_ICON[key],
                "text": text_edit.text().strip() or task_constants._DEFAULT_STATUS_TEXT[key],
            }
            for key, (icon_edit, text_edit) in self.status_fields.items()
        }

        return priority_data, status_data

    def _save(self):
        priority_data, status_data = self._collect_data()

        task_constants.save_custom_labels(priority_data, status_data)

        self.accept()

    def _reset_to_default(self):
        reply = QMessageBox.question(
            self,
            t("dialog.label_settings.reset"),
            t("dialog.label_settings.reset_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            task_constants.reset_custom_labels()

            self._load_current_values()

    # ??????????????????????????????????????????????

    # ?꾨━??
    # ??????????????????????????????????????????????

    def _apply_preset_data(self, preset: dict):
        for key, vals in preset.get("priority", {}).items():
            if key in self.prio_fields:
                icon_edit, text_edit = self.prio_fields[key]

                icon_edit.setText(vals.get("icon", ""))

                text_edit.setText(vals.get("text", ""))

        for key, vals in preset.get("status", {}).items():
            if key in self.status_fields:
                icon_edit, text_edit = self.status_fields[key]

                icon_edit.setText(vals.get("icon", ""))

                text_edit.setText(vals.get("text", ""))

        self._update_previews()

    def _apply_builtin_preset(self, name: str):
        preset = task_constants.get_builtin_presets().get(name)

        if preset:
            self._apply_preset_data(preset)

    def _refresh_user_preset_combo(self):
        self.user_preset_combo.clear()

        presets = task_constants.get_user_presets()

        if not presets:
            self.user_preset_combo.addItem(t("dialog.label_settings.no_user_presets"))

        else:
            for p in presets:
                self.user_preset_combo.addItem(p["name"])

    def _load_user_preset(self):
        presets = task_constants.get_user_presets()

        if not presets:
            QMessageBox.information(
                self, t("dialog.common.notification"), t("dialog.label_settings.none_to_load")
            )

            return

        idx = self.user_preset_combo.currentIndex()

        if 0 <= idx < len(presets):
            self._apply_preset_data(presets[idx])

    def _save_user_preset(self):
        name, ok = QInputDialog.getText(
            self,
            t("dialog.label_settings.save_preset_title"),
            t("dialog.label_settings.enter_preset_name"),
            text="",
        )

        if not ok or not name.strip():
            return

        name = name.strip()

        if name in task_constants.BUILTIN_PRESETS:
            QMessageBox.warning(
                self,
                t("dialog.task.error"),
                t("dialog.label_settings.error_builtin_name", name=name),
            )

            return

        priority_data, status_data = self._collect_data()

        task_constants.save_user_preset(name, priority_data, status_data)

        self._refresh_user_preset_combo()

        idx = self.user_preset_combo.findText(name)

        if idx >= 0:
            self.user_preset_combo.setCurrentIndex(idx)

        QMessageBox.information(
            self,
            t("dialog.label_settings.save_done"),
            t("dialog.label_settings.save_success_msg", name=name),
        )

    def _delete_user_preset(self):
        presets = task_constants.get_user_presets()

        if not presets:
            QMessageBox.information(
                self, t("dialog.common.notification"), t("dialog.label_settings.none_to_delete")
            )

            return

        idx = self.user_preset_combo.currentIndex()

        if idx < 0 or idx >= len(presets):
            return

        name = presets[idx]["name"]

        reply = QMessageBox.question(
            self,
            t("dialog.label_settings.delete"),
            t("dialog.label_settings.delete_confirm", name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            task_constants.delete_user_preset(name)

            self._refresh_user_preset_combo()

    # ??????????????????????????????????????????????

    # 誘몃━蹂닿린 媛깆떊

    # ??????????????????????????????????????????????

    def _update_previews(self):
        """Update preview widgets."""

        pass

    def _normalized_icon_text(self, text: str) -> str:
        text = (text or "").strip()

        if not text:
            return ""

        # ??μ? 吏㏐쾶 ?좎??섎릺, 議고빀 ?낅젰 以묒뿉??嫄대뱶由ъ? ?딄린 ?꾪빐 ?몄텧 ?쒖젏?먮쭔 ?뺣━?쒕떎.

        codepoints = list(text)

        return "".join(codepoints[:8]).strip()

    def _normalize_icon_edit(self, icon_edit: QLineEdit):
        normalized = self._normalized_icon_text(icon_edit.text())

        if normalized != icon_edit.text():
            icon_edit.blockSignals(True)

            icon_edit.setText(normalized)

            icon_edit.blockSignals(False)

        self._update_previews()

    # ??????????????????????????????????????????????

    # ?ㅽ????ы띁

    # ??????????????????????????????????????????????

    def _group_style(self):
        return ""

    def _secondary_btn_style(self):
        return ""
