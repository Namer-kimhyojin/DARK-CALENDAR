# -*- coding: utf-8 -*-
"""

체크리스트 관리 다이얼로그

- 체크리스트 목록 관리

- 기본 정보 편집

- 체크리스트 항목 편집

- 일괄 작업 / 가져오기 / 내보내기

"""

from datetime import datetime
from html import escape
import json
import os
import re

from PyQt6.QtCore import QSignalBlocker, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.db import checklist_template_repo as checklist_repo
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_editor_styles import (
    build_editor_hint_style,
    build_editor_quick_button_style,
    build_editor_text_style,
    build_settings_style_bundle,
    build_task_editor_stylesheet,
)
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
    build_dialog_menu_stylesheet,
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic
from calendar_app.shared.typography import get_typography_scale

DIALOG_STYLE = ""


def _resolve_checklist_theme_inputs(
    tokens: dict | None = None,
    metrics: dict | None = None,
) -> tuple[dict, dict]:
    resolved_tokens = dict(get_dialog_theme_tokens())
    if tokens:
        resolved_tokens.update(tokens)

    resolved_metrics = dict(get_dialog_metric_tokens(apply_overrides=True))
    if metrics:
        resolved_metrics.update(metrics)

    return resolved_tokens, resolved_metrics


def _checklist_shell_stylesheet(tokens: dict | None = None, metrics: dict | None = None) -> str:
    tokens, metrics = _resolve_checklist_theme_inputs(tokens=tokens, metrics=metrics)

    accent = tokens["accent"]
    surface_bg = tokens.get("surface_bg", tokens["surface_alt"])
    surface_alt = tokens["surface_alt"]
    surface_item = tokens.get("surface_item", surface_alt)
    surface_hover = tokens.get("surface_hover", surface_alt)
    text_primary = tokens["text_primary"]
    text_secondary = tokens["text_secondary"]
    border = tokens["border"]
    border_soft = tokens["border_soft"]
    check_indicator_bg = tokens.get("check_indicator_bg", surface_hover)
    check_indicator_border = tokens.get("check_indicator_border", border_soft)
    check_checked_bg = tokens.get("check_checked_bg", accent)
    check_checked_border = tokens.get("check_checked_border", accent)

    base_font_px = max(13, int(metrics["base_font_pt"]))
    field_radius = max(6, int(metrics["field_radius"]))
    field_height = max(30, int(metrics["field_height"]))
    field_padding_y = max(4, int(metrics["field_padding_y"]))
    field_padding_x = max(10, int(metrics["field_padding_x"]))
    group_radius = max(8, int(metrics["group_radius"]))
    group_margin_top = max(8, int(metrics["group_margin_top"]))
    checkbox_spacing = max(6, int(metrics["checkbox_spacing"]))
    indicator_size = max(14, int(metrics["checkbox_indicator_size"]))

    return f"""
QWidget#sidebar {{
    background-color: {surface_alt};
    border-right: 1px solid {border_soft};
    min-width: 244px;
    max-width: 300px;
}}
QWidget#editor_area {{
    background-color: {surface_bg};
}}
QGroupBox {{
    border: 1px solid {border};
    border-radius: {group_radius}px;
    margin-top: {group_margin_top}px;
    padding-top: 14px;
    background-color: {surface_alt};
    color: {text_primary};
    font-weight: 700;
    font-size: {base_font_px}px;
}}
QGroupBox::title {{
    subcontrol-origin: border;
    subcontrol-position: top left;
    left: 12px;
    top: -8px;
    padding: 1px 8px;
    color: {accent};
    background-color: {surface_bg};
}}
QLineEdit, QTextEdit, QComboBox {{
    background-color: {surface_item};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: {field_radius}px;
    padding: {field_padding_y}px {field_padding_x}px;
    font-size: {base_font_px}px;
    min-height: {field_height}px;
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
    border: 1px solid {accent};
    background-color: {surface_bg};
}}
QCheckBox, QRadioButton {{
    color: {text_secondary};
    spacing: {checkbox_spacing}px;
    font-size: {max(12, base_font_px - 1)}px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: {indicator_size}px;
    height: {indicator_size}px;
    border: 2px solid {check_indicator_border};
    background: {check_indicator_bg};
    border-radius: 4px;
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {check_checked_bg};
    border-color: {check_checked_border};
    image: none;
}}
""".strip()


def _dialog_style(tokens: dict | None = None, metrics: dict | None = None) -> str:
    return _checklist_shell_stylesheet(tokens=tokens, metrics=metrics)


def _checklist_editor_stylesheet(tokens: dict | None = None, metrics: dict | None = None) -> str:
    tokens, metrics = _resolve_checklist_theme_inputs(tokens=tokens, metrics=metrics)
    return "\n".join(
        [
            _dialog_style(tokens=tokens, metrics=metrics),
            build_task_editor_stylesheet(tokens=tokens, metrics=metrics),
            # This manager shares the editor's input skin, but its same-row
            # footer actions use the common density instead of editor CTA padding.
            f"""
QDialog#TaskEditorDialog QPushButton#primary_btn[dialogFooter="true"] {{
    padding: {int(metrics["button_padding_y"])}px {int(metrics["button_padding_x"])}px;
    border: 1px solid transparent;
    font-size: {int(metrics["base_font_pt"])}px;
}}
QDialog#TaskEditorDialog QPushButton#primary_btn[dialogFooter="true"]:focus {{
    border-color: {tokens["text_primary"]};
}}
""",
        ]
    )


def _checklist_main_style_bundle(
    tokens: dict | None = None, metrics: dict | None = None
) -> dict[str, str]:
    tokens, metrics = _resolve_checklist_theme_inputs(tokens=tokens, metrics=metrics)
    typography = get_typography_scale(base_pt=float(metrics["base_font_pt"]) * 0.75)
    title_px = int(metrics["title_font_pt"])
    section_px = typography.section_px
    empty_radius = max(8, int(metrics["group_radius"]) - 1)
    panel_radius = max(empty_radius, int(metrics["group_radius"]))
    item_radius = max(6, int(metrics["field_radius"]))
    surface_bg = tokens.get("surface_bg", tokens["surface_alt"])
    border = tokens["border"]
    border_soft = tokens["border_soft"]
    text_primary = tokens["text_primary"]
    text_secondary = tokens["text_secondary"]
    list_hover_bg = tokens.get(
        "list_hover_bg", tokens.get("accent_soft_bg", tokens.get("surface_hover", surface_bg))
    )
    list_selected_bg = tokens.get(
        "list_selected_bg", tokens.get("accent_soft_bg", tokens.get("surface_hover", surface_bg))
    )
    list_selected_border = tokens.get(
        "list_selected_border", tokens.get("accent_soft_border", tokens["border_soft"])
    )
    list_selected_text = tokens.get("list_selected_text", text_primary)
    header_bg = tokens.get("surface_top", surface_bg)
    custom_bundle = {
        "title": build_editor_text_style(tokens, tone="primary", font_px=title_px, weight=700),
        "subtitle": build_editor_text_style(
            tokens, tone="muted", font_px=int(metrics["subtitle_font_pt"])
        ),
        "section": build_editor_text_style(tokens, tone="accent", font_px=section_px, weight=700),
        "badge": build_editor_hint_style(
            tokens, metrics, tone="accent", font_px=int(metrics["subtitle_font_pt"]), weight=600
        ),
        "button_primary": build_editor_quick_button_style(tokens, metrics, tone="accent"),
        "button_secondary": build_editor_quick_button_style(tokens, metrics, tone="secondary"),
        "button_success": build_editor_quick_button_style(tokens, metrics, tone="success"),
        "button_danger": build_editor_quick_button_style(tokens, metrics, tone="danger"),
        "template_list": (
            "QListWidget { "
            f"background-color: {surface_bg}; color: {text_primary}; border: 1px solid {border_soft}; "
            f"border-radius: {panel_radius}px; outline: none; padding: 4px; "
            "}"
            "QListWidget::item { "
            f"padding: 9px 10px; border-radius: {item_radius}px; color: {text_secondary}; "
            "}"
            "QListWidget::item:hover { "
            f"background-color: {list_hover_bg}; color: {text_primary}; "
            "}"
            "QListWidget::item:selected { "
            f"background-color: {list_selected_bg}; color: {list_selected_text}; "
            f"border: 1px solid {list_selected_border}; "
            "}"
        ),
        "items_table": (
            "QTableWidget { "
            f"background-color: {surface_bg}; color: {text_primary}; border: 1px solid {border_soft}; "
            f"border-radius: {panel_radius}px; outline: none; gridline-color: transparent; "
            "}"
            "QHeaderView::section { "
            f"background-color: {header_bg}; color: {text_secondary}; border: none; "
            f"border-bottom: 1px solid {border_soft}; padding: 8px 10px; font-weight: 700; "
            "}"
            "QTableWidget::item { "
            f"padding: 6px 8px; color: {text_primary}; "
            "}"
            "QTableWidget::item:selected { "
            f"background-color: {list_selected_bg}; color: {list_selected_text}; "
            f"border: 1px solid {list_selected_border}; "
            "}"
        ),
        "empty": build_editor_text_style(
            tokens,
            tone="faint",
            font_px=int(metrics["base_font_pt"]),
            padding="24px 16px",
            background=tokens["surface_alt"],
            border_css=f"1px dashed {border}",
            radius=empty_radius,
        ),
    }
    base_bundle = build_settings_style_bundle(tokens, metrics)
    return {**base_bundle, **custom_bundle}


def _checklist_footer_button_style(stylesheet: str, metrics: dict) -> str:
    padding_y = max(2, int(metrics.get("button_padding_y", 4)) - 1)
    target_height = max(44 - 2 * padding_y - 2, int(metrics["button_height"]))
    return re.sub(
        r"min-height: \d+px; max-height: \d+px;",
        f"min-height: {target_height}px; max-height: {target_height}px;",
        stylesheet,
        count=1,
    )


def _checklist_subdialog_style_bundle(
    tokens: dict | None = None, metrics: dict | None = None
) -> dict[str, str]:
    tokens, metrics = _resolve_checklist_theme_inputs(tokens=tokens, metrics=metrics)
    return {
        "heading": build_editor_text_style(
            tokens, tone="primary", font_px=int(metrics["title_font_pt"]), weight=700
        ),
        "caption": build_editor_text_style(
            tokens, tone="muted", font_px=int(metrics["subtitle_font_pt"])
        ),
        "button_primary": _checklist_footer_button_style(
            build_editor_quick_button_style(tokens, metrics, tone="accent"), metrics
        ),
        "button_secondary": _checklist_footer_button_style(
            build_editor_quick_button_style(tokens, metrics, tone="secondary"), metrics
        ),
    }


_RGBA_COLOR_RE = re.compile(
    r"^rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*([0-9]*\.?[0-9]+)\s*\)$",
    re.IGNORECASE,
)


def _token_qcolor(tokens: dict, key: str, fallback: str, min_lightness: int = 0) -> QColor:
    raw = str(tokens.get(key, fallback) or "").strip()
    color = QColor(raw)
    if not color.isValid():
        match = _RGBA_COLOR_RE.match(raw)
        if match:
            try:
                r, g, b, _a = match.groups()
                color = QColor(
                    max(0, min(255, int(r))),
                    max(0, min(255, int(g))),
                    max(0, min(255, int(b))),
                )
            except Exception:
                color = QColor()
    if not color.isValid():
        color = QColor(fallback)
    if min_lightness > 0 and color.lightness() < min_lightness:
        color = QColor(fallback)
    return color


def _checklist_row_palette(tokens: dict | None = None) -> dict[str, QColor]:
    resolved_tokens, _ = _resolve_checklist_theme_inputs(tokens=tokens, metrics=None)
    default_tokens = get_dialog_theme_tokens()
    return {
        "order": _token_qcolor(
            resolved_tokens,
            "text_secondary",
            str(default_tokens.get("text_secondary", "#8fa3bf")),
            min_lightness=100,
        ),
        "description": _token_qcolor(
            resolved_tokens,
            "text_muted",
            str(default_tokens.get("text_muted", "#9cb2cd")),
            min_lightness=115,
        ),
        "required": _token_qcolor(
            resolved_tokens,
            "danger_hex",
            str(default_tokens.get("danger_hex", "#ff6b6b")),
        ),
    }


_TEMPLATE_META_ROLE = Qt.ItemDataRole.UserRole + 1
_TEMPLATE_SEARCH_ROLE = Qt.ItemDataRole.UserRole + 2


class _TemplateListDelegate(QStyledItemDelegate):
    """Give the name and its details independent space and elision."""

    def __init__(self, view, tokens):
        super().__init__(view)
        self._primary = _token_qcolor(tokens, "text_primary", "#e1e1e6")
        self._secondary = _token_qcolor(tokens, "text_secondary", "#abb1bd")
        self._selected = _token_qcolor(tokens, "list_selected_text", self._primary.name())

    def sizeHint(self, option, index):
        del index
        return QSize(0, 2 * option.fontMetrics.height() + 16)

    def paint(self, painter, option, index):
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        styled.text = ""
        widget = styled.widget
        widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, styled, painter, widget)

        painter.save()
        rect = option.rect.adjusted(12, 6, -12, -6)
        painter.setClipRect(rect)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        title_font = QFont(option.font)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(self._selected if selected else self._primary)
        title_metrics = QFontMetrics(title_font)
        title = title_metrics.elidedText(index.data(), Qt.TextElideMode.ElideRight, rect.width())
        align = Qt.AlignmentFlag.AlignLeading | Qt.AlignmentFlag.AlignTop
        painter.drawText(rect, align, title)

        painter.setFont(option.font)
        painter.setPen(self._selected if selected else self._secondary)
        meta = option.fontMetrics.elidedText(
            index.data(_TEMPLATE_META_ROLE) or "", Qt.TextElideMode.ElideRight, rect.width()
        )
        painter.drawText(rect.adjusted(0, title_metrics.height() + 2, 0, 0), align, meta)
        painter.restore()


class _ChecklistItemsTable(QTableWidget):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.columnCount() != 5:
            return
        content_width = self.viewport().width() - self.columnWidth(0) - self.columnWidth(4)
        minimum = self.horizontalHeader().minimumSectionSize()
        self.setColumnWidth(2, max(minimum, round(content_width * 0.32)))
        self.setColumnWidth(3, max(minimum, round(content_width * 0.17)))


class ChecklistManagerDialog(QDialog):
    checklist_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        apply_dialog_title(self, t("checklist_mgr.title"))

        self.setObjectName("TaskEditorDialog")
        self._ui_tokens = get_dialog_theme_tokens()
        self._dialog_metrics = get_dialog_metric_tokens(apply_overrides=True)
        self._main_style_bundle = _checklist_main_style_bundle(
            self._ui_tokens, self._dialog_metrics
        )
        apply_common_dialog_style(
            self,
            minimum_width=880,
            extra_stylesheet=_checklist_editor_stylesheet(self._ui_tokens, self._dialog_metrics),
        )
        self.resize(1060, 680)
        checklist_repo.seed_default_templates()

        self.current_template_id = None
        self._loaded_template_id = None
        self._saved_template_fields = None

        self.init_ui()

        self.setup_shortcuts()

        self.load_templates()

    def _make_icon_btn(self, icon_key, label, style_key, tooltip=None, fixed_width=None):
        """아이콘 + 짧은 텍스트 버튼 생성 헬퍼."""
        btn = QPushButton(label)
        button_style = self._main_style_bundle[style_key]
        color_match = re.search(r"(?:^|[;{])\s*color\s*:\s*([^;{}]+)", button_style)
        icon_color = _token_qcolor(
            {
                "icon": color_match.group(1).strip()
                if color_match
                else self._ui_tokens["text_primary"]
            },
            "icon",
            self._ui_tokens["text_primary"],
        ).name(QColor.NameFormat.HexRgb)
        btn.setIcon(_ic(icon_key, color=icon_color))
        btn.setStyleSheet(button_style)
        if tooltip:
            btn.setToolTip(tooltip)
        if fixed_width:
            btn.setFixedWidth(fixed_width)
        return btn

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # ── 사이드바 ────────────────────────────────────────────────────────
        sidebar = QWidget(objectName="sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 14, 12, 12)
        sidebar_layout.setSpacing(8)

        # 제목 + 배지 한 줄
        header_row = QHBoxLayout()
        header_row.setSpacing(6)
        title_label = QLabel(
            t("checklist_mgr.template_library", "체크리스트"), objectName="main_title"
        )
        title_label.setStyleSheet(self._main_style_bundle["title"])
        header_row.addWidget(title_label)
        header_row.addStretch()
        self.template_count_badge = QLabel(t("checklist_mgr.n_items", n=0), objectName="meta_badge")
        self.template_count_badge.setStyleSheet(self._main_style_bundle["badge"])
        header_row.addWidget(self.template_count_badge)
        sidebar_layout.addLayout(header_row)

        self.template_search = QLineEdit(sidebar)
        search_label = t("checklist_mgr.search_templates", "이름·설명 검색")
        self.template_search.setPlaceholderText(search_label)
        self.template_search.setAccessibleName(search_label)
        self.template_search.setClearButtonEnabled(True)
        self.template_search.textChanged.connect(self._filter_templates)
        sidebar_layout.addWidget(self.template_search)

        self.template_list = QListWidget()
        self.template_list.setStyleSheet(self._main_style_bundle["template_list"])
        self.template_list.setSpacing(1)
        self.template_list.setUniformItemSizes(True)
        self.template_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.template_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.template_list.setAccessibleName(title_label.text())
        self.template_list.setItemDelegate(
            _TemplateListDelegate(self.template_list, self._ui_tokens)
        )
        self.template_list.currentItemChanged.connect(self._on_template_selected)
        sidebar_layout.addWidget(self.template_list, 1)
        self.no_templates_found = QLabel(
            t("checklist_mgr.no_search_results", "검색 결과가 없습니다.")
        )
        self.no_templates_found.setWordWrap(True)
        self.no_templates_found.setStyleSheet(self._main_style_bundle["subtitle"])
        self.no_templates_found.hide()
        sidebar_layout.addWidget(self.no_templates_found)

        # 새로 만들기 (가장 중요 — 단독 전체 너비)
        self.new_btn = self._make_icon_btn(
            ICON.ADD, t("checklist_mgr.btn_new"), "button_success", tooltip="Ctrl+N"
        )
        self.new_btn.clicked.connect(self._create_new_template)
        sidebar_layout.addWidget(self.new_btn)

        options_btn = self._make_icon_btn(
            ICON.SETTINGS, t("checklist_mgr.template_actions", "관리 옵션"), "button_secondary"
        )
        options_menu = QMenu(options_btn)
        options_menu.setStyleSheet(
            build_dialog_menu_stylesheet(settings=getattr(self.parent(), "settings", None))
        )
        self.dup_btn = options_menu.addAction(t("checklist_mgr.btn_dup"), self._duplicate_template)
        self.del_btn = options_menu.addAction(t("common.delete"), self._delete_template)
        options_menu.addSeparator()
        self.import_btn = options_menu.addAction(
            t("checklist_mgr.btn_import"), self._import_with_draft_check
        )
        self.export_btn = options_menu.addAction(
            t("checklist_mgr.btn_export"), self._export_template
        )
        options_btn.setMenu(options_menu)
        sidebar_layout.addWidget(options_btn)

        body_layout.addWidget(sidebar)

        # ── 에디터 영역 ──────────────────────────────────────────────────────
        editor_area = QWidget(objectName="editor_area")
        editor_layout = QVBoxLayout(editor_area)
        editor_layout.setContentsMargins(14, 14, 14, 10)
        editor_layout.setSpacing(10)

        # 빈 상태 안내
        self.empty_msg = QLabel(t("checklist_mgr.prompt_empty"), objectName="empty_state")
        self.empty_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_msg.setStyleSheet(self._main_style_bundle["empty"])
        editor_layout.addWidget(self.empty_msg, 1)

        self.content_widget = QWidget()
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        # ── 기본 정보 (이름/유형 2열, 설명) ──────────────────────────────
        meta_row = QHBoxLayout()
        meta_row.setSpacing(12)

        # 왼쪽: 이름
        name_col = QVBoxLayout()
        name_col.setSpacing(4)
        name_label = QLabel(t("checklist_mgr.label_name"), objectName="TaskDialogFieldLabel")
        name_col.addWidget(name_label)
        self.template_name_edit = QLineEdit()
        self.template_name_edit.setObjectName("TaskTitleEdit")
        self.template_name_edit.setPlaceholderText(t("checklist_mgr.placeholder_name"))
        self.template_name_edit.setAccessibleName(name_label.text())
        name_label.setBuddy(self.template_name_edit)
        name_col.addWidget(self.template_name_edit)
        meta_row.addLayout(name_col, 1)

        # 오른쪽: 유형
        type_col = QVBoxLayout()
        type_col.setSpacing(4)
        type_label = QLabel(t("checklist_mgr.label_type"), objectName="TaskDialogFieldLabel")
        type_col.addWidget(type_label)
        self.template_type_group = QButtonGroup(self)
        self.type_list_radio = QRadioButton(t("checklist_mgr.type_list"))
        self.type_process_radio = QRadioButton(t("checklist_mgr.type_process"))
        self.type_list_radio.setObjectName("TaskDialogOptionCheck")
        self.type_process_radio.setObjectName("TaskDialogOptionCheck")
        self.template_type_group.addButton(self.type_list_radio)
        self.template_type_group.addButton(self.type_process_radio)
        self.type_list_radio.setChecked(True)
        radio_row = QHBoxLayout()
        radio_row.setSpacing(10)
        radio_row.addWidget(self.type_list_radio)
        radio_row.addWidget(self.type_process_radio)
        radio_row.addStretch()
        type_col.addLayout(radio_row)
        meta_row.addLayout(type_col)

        content_layout.addLayout(meta_row)

        desc_row = QVBoxLayout()
        desc_row.setSpacing(4)
        desc_label = QLabel(t("checklist_mgr.label_desc"), objectName="TaskDialogFieldLabel")
        desc_row.addWidget(desc_label)
        self.template_desc_edit = QTextEdit()
        self.template_desc_edit.setAcceptRichText(False)
        self.template_desc_edit.setFixedHeight(
            max(56, 2 * self.template_desc_edit.fontMetrics().height() + 20)
        )
        self.template_desc_edit.setPlaceholderText(t("checklist_mgr.placeholder_desc"))
        self.template_desc_edit.setAccessibleName(desc_label.text())
        desc_label.setBuddy(self.template_desc_edit)
        desc_row.addWidget(self.template_desc_edit)
        content_layout.addLayout(desc_row)

        # ── 항목 테이블 툴바 ────────────────────────────────────────────────
        items_heading = QHBoxLayout()
        items_title = QLabel(t("checklist_mgr.group_items"))
        items_title.setStyleSheet(self._main_style_bundle["section"])
        items_heading.addWidget(items_title)
        self.item_count_badge = QLabel(t("checklist_mgr.n_items", n=0), objectName="meta_badge")
        self.item_count_badge.setStyleSheet(self._main_style_bundle["badge"])
        items_heading.addWidget(self.item_count_badge)
        items_heading.addStretch()
        content_layout.addLayout(items_heading)

        tool_row = QHBoxLayout()
        tool_row.setSpacing(4)

        self.add_item_btn = self._make_icon_btn(
            ICON.ADD, t("checklist_mgr.btn_add_item"), "button_success", tooltip="Ctrl+I"
        )
        self.add_item_btn.clicked.connect(self._add_item)
        tool_row.addWidget(self.add_item_btn)

        self.edit_item_btn = self._make_icon_btn(
            ICON.EDIT, t("common.edit"), "button_secondary", tooltip="Enter"
        )
        self.edit_item_btn.clicked.connect(self._edit_item)
        tool_row.addWidget(self.edit_item_btn)

        self.delete_item_btn = self._make_icon_btn(
            ICON.DELETE, t("common.delete"), "button_danger", tooltip="Del"
        )
        self.delete_item_btn.clicked.connect(self._delete_items)
        tool_row.addWidget(self.delete_item_btn)

        tool_row.addStretch()

        self.move_up_btn = QPushButton("↑", objectName="checklistMoveUpButton")
        self.move_down_btn = QPushButton("↓", objectName="checklistMoveDownButton")
        for button, label, direction in (
            (self.move_up_btn, t("checklist_mgr.btn_up"), -1),
            (self.move_down_btn, t("checklist_mgr.btn_down"), 1),
        ):
            button.setToolTip(f"{label}  Ctrl+{button.text()}")
            button.setAccessibleName(label)
            button.setStyleSheet(
                self._main_style_bundle["button_secondary"]
                + "QPushButton { min-width: 34px; max-width: 34px; padding: 3px 0; }"
            )
            button.setFixedWidth(36)
            button.clicked.connect(lambda _checked=False, step=direction: self._move_item(step))
            tool_row.addWidget(button)

        self.bulk_btn = self._make_icon_btn(
            ICON.CHECKLIST, t("checklist_mgr.btn_bulk"), "button_secondary"
        )
        self.bulk_btn.clicked.connect(self._open_bulk_operations)
        tool_row.addWidget(self.bulk_btn)

        content_layout.addLayout(tool_row)

        self.empty_items_label = QLabel(
            t("checklist_mgr.empty_items", "아직 항목이 없습니다. 항목 추가로 시작하세요.")
        )
        self.empty_items_label.setStyleSheet(self._main_style_bundle["subtitle"])
        self.empty_items_label.setWordWrap(True)
        content_layout.addWidget(self.empty_items_label)

        # ── 항목 테이블 (공간 최대 확보) ───────────────────────────────────
        self.items_table = _ChecklistItemsTable()
        self.items_table.setStyleSheet(self._main_style_bundle["items_table"])
        self.items_table.setAccessibleName(t("checklist_mgr.group_items"))
        self.items_table.setColumnCount(5)
        self.items_table.setHorizontalHeaderLabels(
            [
                t("checklist_mgr.header_order"),
                t("checklist_mgr.header_item"),
                t("checklist_mgr.header_desc"),
                t("checklist_mgr.header_guide"),
                t("checklist_mgr.header_required"),
            ]
        )
        self.items_table.setAlternatingRowColors(True)
        self.items_table.setShowGrid(False)
        self.items_table.setWordWrap(False)
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.items_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.items_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.items_table.setDragEnabled(True)
        self.items_table.setAcceptDrops(True)
        self.items_table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.items_table.setDragDropOverwriteMode(False)
        self.items_table.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.items_table.setDropIndicatorShown(True)
        self.items_table.verticalHeader().hide()
        line_height = self.items_table.fontMetrics().height()
        self.items_table.verticalHeader().setDefaultSectionSize(max(32, line_height + 12))
        header = self.items_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.model().rowsMoved.connect(
            self._sync_dragged_order, Qt.ConnectionType.QueuedConnection
        )
        self.items_table.itemDoubleClicked.connect(lambda _: self._edit_item())
        self.items_table.itemSelectionChanged.connect(self._update_item_actions)
        content_layout.addWidget(self.items_table, 1)

        editor_layout.addWidget(self.content_widget, 1)
        self.content_widget.hide()

        # ── 하단: 저장 + 닫기 ──────────────────────────────────────────────
        footer, self.save_base_btn, close_btn = build_dialog_footer(
            ok_label=t("common.save"), cancel_label=t("common.close")
        )
        self.save_base_btn.setIcon(
            _ic(
                ICON.SAVE,
                color=_token_qcolor(self._ui_tokens, "button_primary_text", "#101318").name(
                    QColor.NameFormat.HexRgb
                ),
            )
        )
        self.save_base_btn.setToolTip("Ctrl+S")
        self.save_base_btn.clicked.connect(self._save_template_info)
        self._save_base_button_text = self.save_base_btn.text()
        self._save_base_button_style = self.save_base_btn.styleSheet()
        self._save_feedback_timer = QTimer(self.save_base_btn)
        self._save_feedback_timer.setSingleShot(True)
        self._save_feedback_timer.setInterval(1200)
        self._save_feedback_timer.timeout.connect(self._restore_save_feedback)
        close_btn.setIcon(
            _ic(
                ICON.CLOSE,
                color=_token_qcolor(self._ui_tokens, "text_primary", "#e1e1e6").name(
                    QColor.NameFormat.HexRgb
                ),
            )
        )
        close_btn.clicked.connect(self.accept)
        editor_layout.addLayout(footer)

        body_layout.addWidget(editor_area, 1)
        root_layout.addLayout(body_layout, 1)

        self._set_editor_visible(False)

    def setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self._create_new_template)

        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self._save_template_info)

        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(self._duplicate_template)

        QShortcut(QKeySequence("Ctrl+I"), self).activated.connect(self._add_item)

        for sequence, handler in (
            ("Delete", self._delete_items),
            ("Return", self._edit_item),
            ("Ctrl+Up", lambda: self._move_item(-1)),
            ("Ctrl+Down", lambda: self._move_item(1)),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self.items_table)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(handler)

    def _set_editor_visible(self, visible):
        self.empty_msg.setVisible(not visible)

        self.content_widget.setVisible(visible)

        self.save_base_btn.setEnabled(visible)

        self.type_list_radio.setEnabled(visible)

        self.type_process_radio.setEnabled(visible)

        self.del_btn.setEnabled(visible)

        self.dup_btn.setEnabled(visible)

        self.export_btn.setEnabled(visible)
        self._update_item_actions()

    def _current_checklist_type(self) -> str:
        return "process" if self.type_process_radio.isChecked() else "list"

    def _set_checklist_type(self, checklist_type: str):
        if str(checklist_type or "list") == "process":
            self.type_process_radio.setChecked(True)

        else:
            self.type_list_radio.setChecked(True)

    def _select_template_in_list(self, template_id):
        for row in range(self.template_list.count()):
            item = self.template_list.item(row)

            if item.data(Qt.ItemDataRole.UserRole) == template_id:
                self.template_list.setCurrentRow(row)

                return True

        return False

    def load_templates(self):
        templates = checklist_repo.get_all_checklist_templates(active_only=False)
        templates.sort(key=lambda item: item["name"].casefold())
        template_ids = {template["id"] for template in templates}
        target = self.current_template_id
        if target not in template_ids:
            target = templates[0]["id"] if templates else None

        with QSignalBlocker(self.template_list):
            self.template_list.clear()
            for template in templates:
                template_id = template["id"]
                name = template["name"]
                description = template.get("description") or ""
                item_count = len(checklist_repo.get_checklist_items(template_id))
                type_label = (
                    t("checklist_mgr.type_process")
                    if template.get("checklist_type") == "process"
                    else t("checklist_mgr.type_list")
                )
                details = f"{type_label} · {t('checklist_mgr.n_items', n=item_count)}"
                item = QListWidgetItem(name)
                item.setData(Qt.ItemDataRole.UserRole, template_id)
                item.setData(_TEMPLATE_META_ROLE, details)
                item.setData(_TEMPLATE_SEARCH_ROLE, f"{name} {description}".casefold())
                item.setData(Qt.ItemDataRole.AccessibleTextRole, f"{name} · {details}")
                item.setToolTip(f"<qt>{escape(name)}<br>{escape(details)}</qt>")
                self.template_list.addItem(item)
            self._select_template_in_list(target)

        if target != self._loaded_template_id and self.template_search.text():
            self.template_search.clear()
        else:
            self._filter_templates()
        if target != self._loaded_template_id:
            self._load_template_detail(target)

    def _filter_templates(self):
        terms = self.template_search.text().casefold().split()
        shown = 0
        with QSignalBlocker(self.template_list):
            for row in range(self.template_list.count()):
                item = self.template_list.item(row)
                haystack = item.data(_TEMPLATE_SEARCH_ROLE) or ""
                matches = all(term in haystack for term in terms)
                item.setHidden(not matches)
                shown += int(matches)
        self.template_count_badge.setText(t("checklist_mgr.n_items", n=shown))
        self.no_templates_found.setVisible(bool(terms) and shown == 0)

    def _on_template_selected(self, current, _previous=None):
        if current is None:
            return
        target = current.data(Qt.ItemDataRole.UserRole)
        if target == self._loaded_template_id:
            return
        allowed = self._confirm_template_edits()
        with QSignalBlocker(self.template_list):
            self._select_template_in_list(target if allowed else self._loaded_template_id)
        if allowed:
            self._load_template_detail(target)

    def _load_template_detail(self, template_id):
        template = (
            checklist_repo.get_checklist_template(template_id) if template_id is not None else None
        )
        self._loaded_template_id = template_id if template else None
        self.current_template_id = self._loaded_template_id
        self._saved_template_fields = None
        self._save_feedback_timer.stop()
        self._restore_save_feedback()

        if not template:
            self._set_editor_visible(False)
            return
        self.template_name_edit.setText(template["name"])
        self.template_name_edit.setCursorPosition(0)
        self.template_name_edit.setToolTip(f"<qt>{escape(template['name'])}</qt>")
        self.template_desc_edit.setPlainText(template["description"] or "")
        self._set_checklist_type(template.get("checklist_type", "list"))
        self._saved_template_fields = self._template_fields()
        self._set_editor_visible(True)
        self._load_items(template_id)

    def _load_items(self, template_id, selected_item_id=None):
        items = checklist_repo.get_checklist_items(template_id)
        if selected_item_id is None:
            selected_item_id = self._selected_item_id()

        self.items_table.setUpdatesEnabled(False)
        was_blocked = self.items_table.blockSignals(True)
        palette = _checklist_row_palette(getattr(self, "_ui_tokens", None))
        order_color = palette["order"]
        desc_color = palette["description"]
        required_color = palette["required"]

        try:
            self.items_table.setRowCount(len(items))
            selected_row = -1
            for row, item in enumerate(items):
                order_item = self._row_cell(str(row + 1))
                order_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                order_item.setForeground(order_color)
                self.items_table.setItem(row, 0, order_item)

                for column, key in enumerate(("item_text", "item_description", "item_guide"), 1):
                    value = item[key] or ""
                    text_item = self._row_cell(value or "—")
                    if value:
                        text_item.setToolTip("<qt>" + escape(value).replace("\n", "<br>") + "</qt>")
                    if column == 1:
                        text_item.setData(Qt.ItemDataRole.UserRole, item["id"])
                    else:
                        text_item.setForeground(desc_color)
                    self.items_table.setItem(row, column, text_item)

                required_text = (
                    t("checklist_mgr.item_required")
                    if item["is_required"]
                    else t("checklist_mgr.item_optional")
                )

                required_item = self._row_cell(required_text)

                required_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if item["is_required"]:
                    required_item.setForeground(required_color)
                    required_font = QFont(self.items_table.font())
                    required_font.setBold(True)
                    required_item.setFont(required_font)

                else:
                    required_item.setForeground(order_color)
                self.items_table.setItem(row, 4, required_item)
                if item["id"] == selected_item_id:
                    selected_row = row

            self.items_table.clearSelection()
            self.items_table.setCurrentCell(selected_row, 1 if selected_row >= 0 else -1)
        finally:
            self.items_table.blockSignals(was_blocked)
            self.items_table.setUpdatesEnabled(True)

        self._update_item_actions()

    def _template_fields(self):
        return (
            self.template_name_edit.text().strip(),
            self.template_desc_edit.toPlainText().strip(),
            self._current_checklist_type(),
        )

    def _confirm_template_edits(self):
        if (
            self._saved_template_fields is None
            or self._template_fields() == self._saved_template_fields
        ):
            return True
        button = QMessageBox.question(
            self,
            t("checklist_mgr.unsaved_title", "저장하지 않은 변경사항"),
            t(
                "checklist_mgr.unsaved_prompt",
                "체크리스트의 이름, 유형 또는 설명 변경사항을 저장할까요?",
            ),
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if button == QMessageBox.StandardButton.Save:
            return self._save_template_info()
        return button == QMessageBox.StandardButton.Discard

    def done(self, result):
        if self._confirm_template_edits():
            super().done(result)

    def _save_template_info(self):
        if not self.current_template_id:
            return False

        name, description, checklist_type = self._template_fields()
        if not name:
            QMessageBox.warning(self, t("common.warning"), t("checklist_mgr.err_name_required"))
            self.template_name_edit.setFocus()
            return False

        updates = {
            "name": name,
            "description": description,
            "checklist_type": checklist_type,
        }
        current_id = self.current_template_id
        if not checklist_repo.update_checklist_template(current_id, updates):
            QMessageBox.warning(
                self,
                t("common.warning"),
                t("checklist_mgr.save_failed", "체크리스트 정보를 저장하지 못했습니다."),
            )
            return False

        previous_fields = self._saved_template_fields
        self._saved_template_fields = (name, description, checklist_type)
        self._save_feedback_timer.stop()
        self.save_base_btn.setText(t("checklist_mgr.btn_saved"))
        self.save_base_btn.setStyleSheet(self._main_style_bundle["button_success"])
        self._save_feedback_timer.start()
        self.load_templates()
        if previous_fields is not None and previous_fields[2] != checklist_type:
            self._load_items(current_id)
        self.checklist_changed.emit()
        return True

    def _restore_save_feedback(self):
        self.save_base_btn.setText(self._save_base_button_text)
        self.save_base_btn.setStyleSheet(self._save_base_button_style)

    def _create_new_template(self):
        name, ok = QInputDialog.getText(
            self, t("checklist_mgr.new_list_title"), t("checklist_mgr.new_list_prompt")
        )

        if not ok or not name.strip() or not self._confirm_template_edits():
            return

        checklist_type = self._saved_template_fields[2] if self._saved_template_fields else "list"
        template_id = checklist_repo.create_checklist_template(
            name=name.strip(),
            description="",
            category="공통",
            checklist_type=checklist_type,
        )

        if template_id:
            self.current_template_id = template_id

            self.load_templates()

            self._select_template_in_list(template_id)

            self.checklist_changed.emit()

    def _duplicate_template(self):
        if not self.current_template_id:
            return

        template = checklist_repo.get_checklist_template(self.current_template_id)

        if not template:
            return

        new_name, ok = QInputDialog.getText(
            self,
            t("checklist_mgr.dup_list_title"),
            t("checklist_mgr.new_list_prompt"),
            text=f"{template['name']} {t('checklist_mgr.dup_list_suffix')}",
        )

        if not ok or not new_name.strip() or not self._confirm_template_edits():
            return

        new_id = checklist_repo.duplicate_checklist_template(
            self.current_template_id, new_name.strip()
        )

        if new_id:
            self.current_template_id = new_id

            self.load_templates()

            self._select_template_in_list(new_id)

            self.checklist_changed.emit()

    def _delete_template(self):
        if not self.current_template_id:
            return

        template = checklist_repo.get_checklist_template(self.current_template_id)

        if not template:
            return

        reply = QMessageBox.question(
            self,
            t("checklist_mgr.delete_list_title"),
            t("checklist_mgr.delete_list_confirm", name=template["name"]),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        if checklist_repo.delete_checklist_template(self.current_template_id):
            self.current_template_id = None

            self.load_templates()

            self.checklist_changed.emit()

    def _export_template(self):
        if not self.current_template_id:
            return

        template = checklist_repo.get_checklist_template(self.current_template_id)

        items = checklist_repo.get_checklist_items(self.current_template_id)

        export_data = {
            "template": {
                "name": template["name"],
                "description": template["description"],
                "category": "공통",
                "checklist_type": template.get("checklist_type", "list"),
            },
            "items": [
                {
                    "item_text": item["item_text"],
                    "item_description": item["item_description"],
                    "item_guide": item["item_guide"],
                    "is_required": item["is_required"],
                }
                for item in items
            ],
            "exported_at": datetime.now().isoformat(),
            "version": "1.0",
        }

        filename, _ = QFileDialog.getSaveFileName(
            self,
            t("checklist_mgr.export_title"),
            f"{template['name']}.json",
            "JSON Files (*.json)",
        )

        if not filename:
            return

        try:
            with open(filename, "w", encoding="utf-8", errors="strict") as file:
                json.dump(export_data, file, ensure_ascii=False, indent=2)

            QMessageBox.information(
                self,
                t("checklist_mgr.export_done_title"),
                t("checklist_mgr.export_done_msg", path=filename),
            )

        except Exception as exc:
            QMessageBox.critical(
                self, t("common.error"), f"{t('checklist_mgr.export_err_fail')}\n{exc}"
            )

    def _import_with_draft_check(self):
        if self._confirm_template_edits():
            self._import_template()

    def _import_template(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            t("checklist_mgr.import_title"),
            "",
            "JSON Files (*.json)",
        )

        if not filename:
            return

        try:
            try:
                limit = checklist_repo.MAX_CHECKLIST_IMPORT_BYTES
                with open(filename, "rb") as file:
                    if os.fstat(file.fileno()).st_size > limit:
                        raise ValueError("Checklist import exceeds the byte limit")
                    # Bound the read too: the file can grow after the size check.
                    raw = file.read(limit + 1)
                if len(raw) > limit:
                    raise ValueError("Checklist import exceeds the byte limit")
                data = json.loads(raw.decode("utf-8", errors="replace"))
                template_id = checklist_repo.import_checklist_template(data)
            except (ValueError, RecursionError) as exc:
                raise ValueError(t("checklist_mgr.import_err_invalid")) from exc

            if not template_id:
                raise RuntimeError(t("checklist_mgr.import_err_fail"))

            self.current_template_id = template_id

            self.load_templates()

            self._select_template_in_list(template_id)

            self.checklist_changed.emit()

            QMessageBox.information(
                self,
                t("checklist_mgr.import_done_title"),
                t("checklist_mgr.import_done_msg", name=data["template"].get("name", "체크리스트")),
            )

        except Exception as exc:
            QMessageBox.critical(
                self, t("common.error"), f"{t('checklist_mgr.import_err_fail')}\n{exc}"
            )

    def _selected_item_rows(self):
        return sorted(index.row() for index in self.items_table.selectionModel().selectedRows())

    @staticmethod
    def _row_cell(text):
        cell = QTableWidgetItem(text)
        cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsDropEnabled)
        return cell

    def _item_id_at(self, row):
        item = self.items_table.item(row, 1)
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _selected_item_id(self):
        rows = self._selected_item_rows()
        return self._item_id_at(rows[0]) if len(rows) == 1 else None

    def _update_item_actions(self):
        row_count = self.items_table.rowCount()
        rows = self._selected_item_rows()
        single_row = rows[0] if len(rows) == 1 else -1
        available = self.current_template_id is not None and not self.content_widget.isHidden()
        self.item_count_badge.setText(t("checklist_mgr.n_items", n=row_count))
        self.empty_items_label.setVisible(available and row_count == 0)
        self.add_item_btn.setEnabled(available)
        self.edit_item_btn.setEnabled(available and single_row >= 0)
        self.delete_item_btn.setEnabled(available and bool(rows))
        self.move_up_btn.setEnabled(available and single_row > 0)
        self.move_down_btn.setEnabled(available and 0 <= single_row < row_count - 1)
        self.bulk_btn.setEnabled(available and row_count > 0)

    def _open_bulk_operations(self):
        if not self.current_template_id or not self.items_table.rowCount():
            return

        dialog = BulkOperationsDialog(self.current_template_id, self)

        if dialog.exec():
            self._load_items(self.current_template_id)
            self.checklist_changed.emit()

    def _add_item(self):
        if not self.current_template_id:
            return

        dialog = ChecklistItemEditDialog(self.current_template_id, parent=self)

        if dialog.exec():
            self._load_items(self.current_template_id, selected_item_id=dialog.item_id)
            self.load_templates()
            self.checklist_changed.emit()

    def _edit_item(self):
        item_id = self._selected_item_id()
        if not self.current_template_id or item_id is None:
            return

        dialog = ChecklistItemEditDialog(self.current_template_id, item_id=item_id, parent=self)

        if dialog.exec():
            self._load_items(self.current_template_id, selected_item_id=item_id)
            self.checklist_changed.emit()

    def _delete_items(self):
        selected_rows = self._selected_item_rows()
        item_ids = [self._item_id_at(row) for row in selected_rows]
        if not self.current_template_id or not item_ids or None in item_ids:
            return

        reply = QMessageBox.question(
            self,
            t("checklist_mgr.delete_items_title"),
            t("checklist_mgr.delete_items_confirm", n=len(selected_rows)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        results = [checklist_repo.delete_checklist_item(item_id) for item_id in item_ids]
        self._load_items(self.current_template_id)
        row_count = self.items_table.rowCount()
        if row_count and self.items_table.currentRow() < 0:
            self.items_table.setCurrentCell(min(selected_rows[0], row_count - 1), 1)
        if any(results):
            self.load_templates()
            self.checklist_changed.emit()

    def _move_item(self, direction):
        rows = self._selected_item_rows()
        if len(rows) == 1:
            self._commit_reorder(rows[0], rows[0] + direction)

    def _commit_reorder(self, old_index, new_index):
        row_count = self.items_table.rowCount()
        if not self.current_template_id or not (
            0 <= old_index < row_count and 0 <= new_index < row_count
        ):
            return

        item_ids = [self._item_id_at(row) for row in range(row_count)]
        moved_item_id = item_ids[old_index]
        item_ids[old_index], item_ids[new_index] = item_ids[new_index], item_ids[old_index]
        self._persist_item_order(item_ids, moved_item_id)

    def _sync_dragged_order(self):
        # Qt may move several selected rows during one drop. The queued signal
        # lets the drop finish before reading or rebuilding the table.
        if not self.current_template_id:
            return
        item_ids = [self._item_id_at(row) for row in range(self.items_table.rowCount())]
        self._persist_item_order(item_ids, self._selected_item_id())

    def _persist_item_order(self, item_ids, selected_item_id):
        template_id = self.current_template_id
        saved_ids = [item["id"] for item in checklist_repo.get_checklist_items(template_id)]
        if item_ids == saved_ids:
            return
        complete = len(item_ids) == len(saved_ids) and set(item_ids) == set(saved_ids)
        saved = complete and checklist_repo.reorder_checklist_items(template_id, item_ids)
        self._load_items(template_id, selected_item_id=selected_item_id)
        if saved:
            self.checklist_changed.emit()


class ChecklistItemEditDialog(QDialog):
    def __init__(self, template_id, item_id=None, parent=None):
        super().__init__(parent)

        self.template_id = template_id

        self.item_id = item_id

        apply_dialog_title(
            self,
            t("checklist_mgr.header_item_edit") if item_id else t("checklist_mgr.btn_add_item"),
        )

        self.setObjectName("TaskEditorDialog")
        self._ui_tokens = getattr(parent, "_ui_tokens", get_dialog_theme_tokens())
        self._dialog_metrics = get_dialog_metric_tokens(apply_overrides=True)
        self._style_bundle = _checklist_subdialog_style_bundle(
            self._ui_tokens, self._dialog_metrics
        )
        apply_common_dialog_style(
            self,
            minimum_width=520,
            size=(560, 520),
            extra_stylesheet=_checklist_editor_stylesheet(self._ui_tokens, self._dialog_metrics),
        )
        self.setAccessibleName(self.windowTitle())
        self.setSizeGripEnabled(True)
        self.init_ui()

        if item_id:
            self._load_data()

    def init_ui(self):
        layout = QVBoxLayout(self)

        layout.setContentsMargins(14, 14, 14, 14)

        layout.setSpacing(8)

        heading = QLabel(t("checklist_mgr.group_items_edit"))
        heading.setStyleSheet(self._style_bundle["heading"])
        layout.addWidget(heading)

        caption = QLabel(t("checklist_mgr.item_edit_caption"))
        caption.setStyleSheet(self._style_bundle["caption"])
        layout.addWidget(caption)

        field_label = QLabel(t("checklist_mgr.header_item"))
        field_label.setObjectName("TaskDialogFieldLabel")
        layout.addWidget(field_label)

        self.text_edit = QLineEdit()
        self.text_edit.setObjectName("TaskTitleEdit")

        self.text_edit.setPlaceholderText(t("checklist_mgr.placeholder_item_name"))
        field_label.setBuddy(self.text_edit)
        self.text_edit.setAccessibleName(field_label.text())

        layout.addWidget(self.text_edit)

        desc_label = QLabel(t("checklist_mgr.header_desc"))
        desc_label.setObjectName("TaskDialogFieldLabel")
        layout.addWidget(desc_label)

        self.desc_edit = QTextEdit()

        self.desc_edit.setMinimumHeight(max(62, self.desc_edit.fontMetrics().height() * 2 + 16))

        self.desc_edit.setPlaceholderText(t("checklist_mgr.placeholder_item_desc"))
        desc_label.setBuddy(self.desc_edit)
        self.desc_edit.setAccessibleName(desc_label.text())

        layout.addWidget(self.desc_edit)

        guide_label = QLabel(t("checklist_mgr.header_guide"))
        guide_label.setObjectName("TaskDialogFieldLabel")
        layout.addWidget(guide_label)

        self.guide_edit = QTextEdit()

        self.guide_edit.setMinimumHeight(max(78, self.guide_edit.fontMetrics().height() * 3 + 16))

        self.guide_edit.setPlaceholderText(t("checklist_mgr.placeholder_item_guide"))
        guide_label.setBuddy(self.guide_edit)
        self.guide_edit.setAccessibleName(guide_label.text())

        layout.addWidget(self.guide_edit)

        self.req_check = QCheckBox(t("checklist_mgr.label_required_set"))
        self.req_check.setObjectName("TaskDialogOptionCheck")

        layout.addWidget(self.req_check)

        _sep = QFrame()
        _sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(_sep)

        buttons, save_btn, cancel_btn = build_dialog_footer(
            ok_label=t("common.save"),
            cancel_label=t("common.cancel"),
        )
        save_btn.setStyleSheet(self._style_bundle["button_primary"])
        save_btn.setMinimumHeight(44)
        save_btn.clicked.connect(self._save)
        cancel_btn.setStyleSheet(self._style_bundle["button_secondary"])
        cancel_btn.setMinimumHeight(44)
        cancel_btn.clicked.connect(self.reject)

        layout.addLayout(buttons)

    def _load_data(self):
        item = checklist_repo.get_checklist_item(self.item_id)

        if not item:
            return

        self.text_edit.setText(item["item_text"])

        self.desc_edit.setPlainText(item["item_description"] or "")

        self.guide_edit.setPlainText(item["item_guide"] or "")

        self.req_check.setChecked(item["is_required"] == 1)

    def _save(self):
        text = self.text_edit.text().strip()

        if not text:
            QMessageBox.warning(self, t("common.warning"), t("checklist_mgr.err_item_required"))

            return

        data = {
            "item_text": text,
            "item_description": self.desc_edit.toPlainText().strip(),
            "item_guide": self.guide_edit.toPlainText().strip(),
            "is_required": 1 if self.req_check.isChecked() else 0,
        }

        if self.item_id:
            saved = checklist_repo.update_checklist_item(self.item_id, data)
        else:
            items = checklist_repo.get_checklist_items(self.template_id)
            next_order = max((item["item_order"] or 0 for item in items), default=-1) + 1
            self.item_id = checklist_repo.create_checklist_item(
                self.template_id,
                text,
                data["item_description"],
                data["item_guide"],
                next_order,
                data["is_required"],
            )
            saved = self.item_id is not None
        if saved:
            self.accept()
        else:
            QMessageBox.warning(
                self,
                t("common.error"),
                t("checklist_mgr.err_item_save", "항목을 저장하지 못했습니다. 다시 시도해 주세요."),
            )


class BulkOperationsDialog(QDialog):
    def __init__(self, template_id, parent=None):
        super().__init__(parent)

        self.template_id = template_id

        apply_dialog_title(self, t("checklist_mgr.btn_bulk"))

        self.setObjectName("TaskEditorDialog")
        self._ui_tokens = getattr(parent, "_ui_tokens", get_dialog_theme_tokens())
        self._dialog_metrics = get_dialog_metric_tokens(apply_overrides=True)
        self._style_bundle = _checklist_subdialog_style_bundle(
            self._ui_tokens, self._dialog_metrics
        )
        apply_common_dialog_style(
            self,
            minimum_width=460,
            size=(520, 400),
            extra_stylesheet=_checklist_editor_stylesheet(self._ui_tokens, self._dialog_metrics),
        )
        self.setAccessibleName(self.windowTitle())
        self.setSizeGripEnabled(True)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        layout.setContentsMargins(18, 18, 18, 18)

        layout.setSpacing(10)

        heading = QLabel(t("checklist_mgr.btn_bulk"))
        heading.setStyleSheet(self._style_bundle["heading"])
        layout.addWidget(heading)

        caption = QLabel(t("checklist_mgr.bulk_caption"))
        caption.setStyleSheet(self._style_bundle["caption"])
        layout.addWidget(caption)

        self.op_group = QButtonGroup(self)

        op_required = QRadioButton(t("checklist_mgr.bulk_all_required"))

        self.op_group.addButton(op_required, 1)

        layout.addWidget(op_required)

        op_optional = QRadioButton(t("checklist_mgr.bulk_all_optional"))

        self.op_group.addButton(op_optional, 2)

        layout.addWidget(op_optional)

        op_prefix = QRadioButton(t("checklist_mgr.bulk_add_prefix"))

        self.op_group.addButton(op_prefix, 3)

        layout.addWidget(op_prefix)

        self.prefix_edit = QLineEdit()

        self.prefix_edit.setPlaceholderText(t("checklist_mgr.placeholder_prefix"))
        self.prefix_edit.setAccessibleName(op_prefix.text())

        self.prefix_edit.setEnabled(False)

        layout.addWidget(self.prefix_edit)

        op_prefix.toggled.connect(self.prefix_edit.setEnabled)

        layout.addStretch()

        _sep = QFrame()
        _sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(_sep)

        buttons, apply_btn, cancel_btn = build_dialog_footer(
            ok_label=t("checklist_mgr.btn_apply_bulk"),
            cancel_label=t("common.cancel"),
        )
        apply_btn.setStyleSheet(self._style_bundle["button_primary"])
        apply_btn.setMinimumHeight(44)
        apply_btn.clicked.connect(self._apply)
        cancel_btn.setStyleSheet(self._style_bundle["button_secondary"])
        cancel_btn.setMinimumHeight(44)
        cancel_btn.clicked.connect(self.reject)

        layout.addLayout(buttons)

    def _apply(self):
        op_id = self.op_group.checkedId()

        if op_id < 0:
            QMessageBox.warning(
                self, t("common.selection_required"), t("checklist_mgr.err_bulk_selection")
            )

            return

        items = checklist_repo.get_checklist_items(self.template_id)

        try:
            if op_id == 1:
                for item in items:
                    checklist_repo.update_checklist_item(item["id"], {"is_required": 1})

            elif op_id == 2:
                for item in items:
                    checklist_repo.update_checklist_item(item["id"], {"is_required": 0})

            elif op_id == 3:
                prefix = self.prefix_edit.text()

                if not prefix:
                    QMessageBox.warning(
                        self, t("common.warning"), t("checklist_mgr.err_prefix_required")
                    )

                    return

                for item in items:
                    checklist_repo.update_checklist_item(
                        item["id"], {"item_text": prefix + item["item_text"]}
                    )

            QMessageBox.information(
                self,
                t("checklist_mgr.bulk_done_title"),
                t("checklist_mgr.bulk_done_msg", n=len(items)),
            )

            self.accept()

        except Exception as exc:
            QMessageBox.critical(
                self, t("common.error"), f"{t('checklist_mgr.err_bulk_fail')}\n{exc}"
            )
