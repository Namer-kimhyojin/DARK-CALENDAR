"""

체크리스트 관리 다이얼로그

- 체크리스트 목록 관리

- 기본 정보 편집

- 체크리스트 항목 편집

- 일괄 작업 / 가져오기 / 내보내기

"""

from datetime import datetime
import json
import re

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeySequence, QShortcut
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
    QMessageBox,
    QPushButton,
    QRadioButton,
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
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic

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
    min-width: 280px;
    max-width: 320px;
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
        ]
    )


def _checklist_main_style_bundle(
    tokens: dict | None = None, metrics: dict | None = None
) -> dict[str, str]:
    tokens, metrics = _resolve_checklist_theme_inputs(tokens=tokens, metrics=metrics)
    title_px = max(18, int(metrics["base_font_pt"]) + 4)
    section_px = max(14, int(metrics["base_font_pt"]))
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
        "subtitle": build_editor_text_style(tokens, tone="muted", font_px=12),
        "section": build_editor_text_style(tokens, tone="accent", font_px=section_px, weight=700),
        "badge": build_editor_hint_style(tokens, metrics, tone="accent", font_px=12, weight=600),
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
            font_px=14,
            padding="24px 16px",
            background=tokens["surface_alt"],
            border_css=f"1px dashed {border}",
            radius=empty_radius,
        ),
    }
    base_bundle = build_settings_style_bundle(tokens, metrics)
    return {**base_bundle, **custom_bundle}


def _checklist_subdialog_style_bundle(
    tokens: dict | None = None, metrics: dict | None = None
) -> dict[str, str]:
    tokens, metrics = _resolve_checklist_theme_inputs(tokens=tokens, metrics=metrics)
    return {
        "heading": build_editor_text_style(tokens, tone="primary", font_px=18, weight=700),
        "caption": build_editor_text_style(tokens, tone="muted", font_px=12),
        "button_primary": build_editor_quick_button_style(tokens, metrics, tone="accent"),
        "button_secondary": build_editor_quick_button_style(tokens, metrics, tone="secondary"),
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
            minimum_width=1060,
            extra_stylesheet=_checklist_editor_stylesheet(self._ui_tokens, self._dialog_metrics),
        )
        self.resize(1060, 680)
        checklist_repo.seed_default_templates()

        self.current_template_id = None

        self.init_ui()

        self.setup_shortcuts()

        self.load_templates()

    def _make_icon_btn(self, icon_key, label, style_key, tooltip=None, fixed_width=None):
        """아이콘 + 짧은 텍스트 버튼 생성 헬퍼."""
        btn = QPushButton(f"  {label}")
        btn.setIcon(_ic(icon_key))
        btn.setStyleSheet(self._main_style_bundle[style_key])
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
        title_label = QLabel(t("checklist_mgr.title"), objectName="main_title")
        title_label.setStyleSheet(self._main_style_bundle["title"])
        header_row.addWidget(title_label)
        header_row.addStretch()
        self.template_count_badge = QLabel(t("checklist_mgr.n_items", n=0), objectName="meta_badge")
        self.template_count_badge.setStyleSheet(self._main_style_bundle["badge"])
        header_row.addWidget(self.template_count_badge)
        sidebar_layout.addLayout(header_row)

        # 체크리스트 목록
        self.template_list = QListWidget()
        self.template_list.setStyleSheet(self._main_style_bundle["template_list"])
        self.template_list.setSpacing(1)
        self.template_list.setUniformItemSizes(True)
        self.template_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.template_list.currentItemChanged.connect(self._on_template_selected)
        sidebar_layout.addWidget(self.template_list, 1)

        # 새로 만들기 (가장 중요 — 단독 전체 너비)
        self.new_btn = self._make_icon_btn(
            ICON.ADD, t("checklist_mgr.btn_new"), "button_success", tooltip="Ctrl+N"
        )
        self.new_btn.clicked.connect(self._create_new_template)
        sidebar_layout.addWidget(self.new_btn)

        # 복제 / 삭제
        dup_del_row = QHBoxLayout()
        dup_del_row.setSpacing(6)
        self.dup_btn = self._make_icon_btn(
            ICON.EDIT, t("checklist_mgr.btn_dup"), "button_secondary", tooltip="Ctrl+D"
        )
        self.dup_btn.clicked.connect(self._duplicate_template)
        dup_del_row.addWidget(self.dup_btn, 1)

        self.del_btn = self._make_icon_btn(ICON.DELETE, t("common.delete"), "button_danger")
        self.del_btn.clicked.connect(self._delete_template)
        dup_del_row.addWidget(self.del_btn, 1)
        sidebar_layout.addLayout(dup_del_row)

        # 내보내기 / 가져오기
        io_row = QHBoxLayout()
        io_row.setSpacing(6)
        self.export_btn = self._make_icon_btn(
            ICON.SAVE, t("checklist_mgr.btn_export"), "button_secondary"
        )
        self.export_btn.clicked.connect(self._export_template)
        io_row.addWidget(self.export_btn, 1)

        self.import_btn = self._make_icon_btn(
            ICON.FOLDER, t("checklist_mgr.btn_import"), "button_secondary"
        )
        self.import_btn.clicked.connect(self._import_template)
        io_row.addWidget(self.import_btn, 1)
        sidebar_layout.addLayout(io_row)

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
        name_col.addWidget(self.template_name_edit)
        meta_row.addLayout(name_col, 3)

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
        meta_row.addLayout(type_col, 2)

        content_layout.addLayout(meta_row)

        # 설명
        desc_row = QHBoxLayout()
        desc_row.setSpacing(10)
        desc_label = QLabel(t("checklist_mgr.label_desc"), objectName="TaskDialogFieldLabel")
        desc_label.setFixedWidth(50)
        desc_row.addWidget(desc_label)
        self.template_desc_edit = QTextEdit()
        self.template_desc_edit.setFixedHeight(38)
        self.template_desc_edit.setPlaceholderText(t("checklist_mgr.placeholder_desc"))
        desc_row.addWidget(self.template_desc_edit, 1)
        content_layout.addLayout(desc_row)

        # ── 항목 테이블 툴바 ────────────────────────────────────────────────
        tool_row = QHBoxLayout()
        tool_row.setSpacing(4)

        add_item_btn = self._make_icon_btn(
            ICON.ADD, t("checklist_mgr.btn_add_item"), "button_success", tooltip="Ctrl+I"
        )
        add_item_btn.clicked.connect(self._add_item)
        tool_row.addWidget(add_item_btn)

        edit_item_btn = self._make_icon_btn(
            ICON.EDIT, t("common.edit"), "button_secondary", tooltip="Enter"
        )
        edit_item_btn.clicked.connect(self._edit_item)
        tool_row.addWidget(edit_item_btn)

        delete_item_btn = self._make_icon_btn(
            ICON.DELETE, t("common.delete"), "button_danger", tooltip="Del"
        )
        delete_item_btn.clicked.connect(self._delete_items)
        tool_row.addWidget(delete_item_btn)

        tool_row.addStretch()

        # 순서 이동 (아이콘만, 좁게)
        up_btn = QPushButton()
        up_btn.setIcon(_ic(ICON.NAV_PREV))
        up_btn.setFixedWidth(32)
        up_btn.setToolTip(f"{t('checklist_mgr.btn_up')}  Ctrl+↑")
        up_btn.setStyleSheet(self._main_style_bundle["button_secondary"])
        up_btn.clicked.connect(lambda: self._move_item(-1))
        tool_row.addWidget(up_btn)

        down_btn = QPushButton()
        down_btn.setIcon(_ic(ICON.NAV_NEXT))
        down_btn.setFixedWidth(32)
        down_btn.setToolTip(f"{t('checklist_mgr.btn_down')}  Ctrl+↓")
        down_btn.setStyleSheet(self._main_style_bundle["button_secondary"])
        down_btn.clicked.connect(lambda: self._move_item(1))
        tool_row.addWidget(down_btn)

        self.bulk_btn = self._make_icon_btn(
            ICON.CHECKLIST, t("checklist_mgr.btn_bulk"), "button_secondary"
        )
        self.bulk_btn.clicked.connect(self._open_bulk_operations)
        tool_row.addWidget(self.bulk_btn)

        content_layout.addLayout(tool_row)

        # ── 항목 테이블 (공간 최대 확보) ───────────────────────────────────
        self.items_table = QTableWidget()
        self.items_table.setStyleSheet(self._main_style_bundle["items_table"])
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
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.items_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.items_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.items_table.setDragEnabled(True)
        self.items_table.setAcceptDrops(True)
        self.items_table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.items_table.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.items_table.setDropIndicatorShown(True)
        self.items_table.verticalHeader().hide()
        self.items_table.verticalHeader().setDefaultSectionSize(32)
        self.items_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.items_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.items_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.items_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.items_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        self.items_table.model().rowsMoved.connect(self._on_rows_moved)
        self.items_table.itemDoubleClicked.connect(lambda _: self._edit_item())
        content_layout.addWidget(self.items_table, 1)

        editor_layout.addWidget(self.content_widget, 1)
        self.content_widget.hide()

        # ── 하단: 저장 + 닫기 ──────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer.addStretch()
        self.save_base_btn = self._make_icon_btn(
            ICON.SAVE, t("common.save"), "button_primary", tooltip="Ctrl+S"
        )
        self.save_base_btn.clicked.connect(self._save_template_info)
        footer.addWidget(self.save_base_btn)
        close_btn = self._make_icon_btn(ICON.CLOSE, t("common.close"), "button_secondary")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        editor_layout.addLayout(footer)

        body_layout.addWidget(editor_area, 1)
        root_layout.addLayout(body_layout, 1)

        self._set_editor_visible(False)

    def setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self._create_new_template)

        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self._save_template_info)

        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(self._duplicate_template)

        QShortcut(QKeySequence("Ctrl+I"), self).activated.connect(self._add_item)

        QShortcut(QKeySequence("Delete"), self).activated.connect(self._delete_items)

        QShortcut(QKeySequence("Return"), self).activated.connect(self._edit_item)

        QShortcut(QKeySequence("Ctrl+Up"), self).activated.connect(lambda: self._move_item(-1))

        QShortcut(QKeySequence("Ctrl+Down"), self).activated.connect(lambda: self._move_item(1))

    def _set_editor_visible(self, visible):
        self.empty_msg.setVisible(not visible)

        self.content_widget.setVisible(visible)

        self.bulk_btn.setEnabled(visible)

        self.save_base_btn.setEnabled(visible)

        self.type_list_radio.setEnabled(visible)

        self.type_process_radio.setEnabled(visible)

        self.del_btn.setEnabled(visible)

        self.dup_btn.setEnabled(visible)

        self.export_btn.setEnabled(visible)

    def _current_checklist_type(self) -> str:
        return "process" if self.type_process_radio.isChecked() else "list"

    def _set_checklist_type(self, checklist_type: str):
        if str(checklist_type or "list") == "process":
            self.type_process_radio.setChecked(True)

        else:
            self.type_list_radio.setChecked(True)

    def _set_selected_template_meta(self, template):
        return

    def _select_template_in_list(self, template_id):
        for row in range(self.template_list.count()):
            item = self.template_list.item(row)

            if item.data(Qt.ItemDataRole.UserRole) == template_id:
                self.template_list.setCurrentRow(row)

                return True

        return False

    def load_templates(self):
        self.template_list.clear()

        templates = checklist_repo.get_all_checklist_templates(active_only=False)

        templates.sort(key=lambda item: item["name"].lower())

        for template in templates:
            item_count = len(checklist_repo.get_checklist_items(template["id"]))

            type_str = (
                t("checklist_mgr.type_list")
                if template.get("checklist_type") == "list"
                else t("checklist_mgr.type_process")
            )

            item = QListWidgetItem(
                f"{template['name']} [{type_str}] ({t('checklist_mgr.n_items', n=item_count)})"
            )

            item.setData(Qt.ItemDataRole.UserRole, template["id"])

            self.template_list.addItem(item)

        self.template_count_badge.setText(t("checklist_mgr.n_items", n=len(templates)))

        if self.current_template_id and self._select_template_in_list(self.current_template_id):
            return

        if not templates:
            self.current_template_id = None

            self._set_editor_visible(False)

            self._set_selected_template_meta(None)

        elif not self.current_template_id:
            self.template_list.setCurrentRow(0)

    def _on_template_selected(self, current, previous=None):
        if not current:
            self.current_template_id = None

            self._set_editor_visible(False)

            self._set_selected_template_meta(None)

            return

        self.current_template_id = current.data(Qt.ItemDataRole.UserRole)

        self._set_editor_visible(True)

        self._load_template_detail(self.current_template_id)

    def _load_template_detail(self, template_id):
        template = checklist_repo.get_checklist_template(template_id)

        if not template:
            self._set_editor_visible(False)

            self._set_selected_template_meta(None)

            return

        self.template_name_edit.setText(template["name"])

        self.template_desc_edit.setPlainText(template["description"] or "")

        tmpl_type = template.get("checklist_type", "list")

        self._set_checklist_type(tmpl_type)

        self._set_selected_template_meta(template)

        self._load_items(template_id)

    def _load_items(self, template_id):
        items = checklist_repo.get_checklist_items(template_id)

        self.items_table.setUpdatesEnabled(False)
        self.items_table.blockSignals(True)
        self.items_table.setRowCount(len(items))

        template = checklist_repo.get_checklist_template(template_id)

        is_process = (template.get("checklist_type") == "process") if template else False
        palette = _checklist_row_palette(getattr(self, "_ui_tokens", None))
        order_color = palette["order"]
        desc_color = palette["description"]
        required_color = palette["required"]

        try:
            for row, item in enumerate(items):
                order_item = QTableWidgetItem(str(row + 1))

                order_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                order_item.setForeground(order_color)
                self.items_table.setItem(row, 0, order_item)

                prefix = f"{row + 1}. " if is_process else ""

                text_item = QTableWidgetItem(f"{prefix}{item['item_text']}")

                text_item.setData(Qt.ItemDataRole.UserRole, item["id"])

                self.items_table.setItem(row, 1, text_item)

                desc_item = QTableWidgetItem(item["item_description"] or "-")

                desc_item.setForeground(desc_color)
                self.items_table.setItem(row, 2, desc_item)

                guide_item = QTableWidgetItem(item["item_guide"] or "-")

                guide_item.setForeground(desc_color)
                self.items_table.setItem(row, 3, guide_item)

                required_text = (
                    t("checklist_mgr.item_required")
                    if item["is_required"]
                    else t("checklist_mgr.item_optional")
                )

                required_item = QTableWidgetItem(required_text)

                required_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if item["is_required"]:
                    required_item.setForeground(required_color)
                    required_item.setFont(QFont("Malgun Gothic", 9, QFont.Weight.Bold))

                else:
                    required_item.setForeground(order_color)
                self.items_table.setItem(row, 4, required_item)

            self.items_table.clearSelection()
        finally:
            self.items_table.blockSignals(False)
            self.items_table.setUpdatesEnabled(True)

        template = checklist_repo.get_checklist_template(template_id)

        if template:
            self._set_selected_template_meta(template)

    def _save_template_info(self):
        if not self.current_template_id:
            return

        name = self.template_name_edit.text().strip()

        if not name:
            QMessageBox.warning(self, t("common.warning"), t("checklist_mgr.err_name_required"))

            return

        updates = {
            "name": name,
            "description": self.template_desc_edit.toPlainText().strip(),
            "category": "공통",
            "checklist_type": self._current_checklist_type(),
        }

        if checklist_repo.update_checklist_template(self.current_template_id, updates):
            original_text = self.save_base_btn.text()

            self.save_base_btn.setText(t("checklist_mgr.btn_saved"))
            self.save_base_btn.setStyleSheet(self._main_style_bundle["button_success"])

            def restore_button():
                self.save_base_btn.setText(original_text)
                self.save_base_btn.setStyleSheet(self._main_style_bundle["button_primary"])

            QTimer.singleShot(1200, restore_button)

            current_id = self.current_template_id

            self.load_templates()

            self._select_template_in_list(current_id)

            self.checklist_changed.emit()

    def _create_new_template(self):
        name, ok = QInputDialog.getText(
            self, t("checklist_mgr.new_list_title"), t("checklist_mgr.new_list_prompt")
        )

        if not ok or not name.strip():
            return

        template_id = checklist_repo.create_checklist_template(
            name=name.strip(),
            description="",
            category="공통",
            checklist_type=self._current_checklist_type(),
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

        if not ok or not new_name.strip():
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
            with open(filename, encoding="utf-8", errors="strict") as file:
                data = json.load(file)

            if "template" not in data or "items" not in data:
                raise ValueError(t("checklist_mgr.import_err_invalid"))

            template_data = data["template"]

            template_id = checklist_repo.create_checklist_template(
                name=template_data.get("name", "가져온 체크리스트"),
                description=template_data.get("description", ""),
                category="공통",
                checklist_type=template_data.get("checklist_type", "list"),
            )

            if not template_id:
                raise RuntimeError(t("checklist_mgr.import_err_fail"))

            for order, item_data in enumerate(data["items"]):
                checklist_repo.create_checklist_item(
                    template_id,
                    item_data.get("item_text", ""),
                    item_data.get("item_description", ""),
                    item_data.get("item_guide", ""),
                    order,
                    item_data.get("is_required", 0),
                )

            self.current_template_id = template_id

            self.load_templates()

            self._select_template_in_list(template_id)

            self.checklist_changed.emit()

            QMessageBox.information(
                self,
                t("checklist_mgr.import_done_title"),
                t("checklist_mgr.import_done_msg", name=template_data.get("name", "체크리스트")),
            )

        except Exception as exc:
            QMessageBox.critical(
                self, t("common.error"), f"{t('checklist_mgr.import_err_fail')}\n{exc}"
            )

    def _open_bulk_operations(self):
        if not self.current_template_id:
            return

        dialog = BulkOperationsDialog(self.current_template_id, self)

        if dialog.exec():
            self._load_items(self.current_template_id)

            self.load_templates()

            self.checklist_changed.emit()

    def _add_item(self):
        if not self.current_template_id:
            return

        dialog = ChecklistItemEditDialog(self.current_template_id, parent=self)

        if dialog.exec():
            self._load_items(self.current_template_id)

            self.load_templates()

            self.checklist_changed.emit()

    def _edit_item(self):
        row = self.items_table.currentRow()

        if row < 0:
            return

        item_id = self.items_table.item(row, 1).data(Qt.ItemDataRole.UserRole)

        dialog = ChecklistItemEditDialog(self.current_template_id, item_id=item_id, parent=self)

        if dialog.exec():
            self._load_items(self.current_template_id)

            self.checklist_changed.emit()

    def _delete_items(self):
        selected_rows = sorted(
            {item.row() for item in self.items_table.selectedItems()}, reverse=True
        )

        if not selected_rows:
            return

        reply = QMessageBox.question(
            self,
            t("checklist_mgr.delete_items_title"),
            t("checklist_mgr.delete_items_confirm", n=len(selected_rows)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        for row in selected_rows:
            item_id = self.items_table.item(row, 1).data(Qt.ItemDataRole.UserRole)

            checklist_repo.delete_checklist_item(item_id)

        self._load_items(self.current_template_id)

        self.load_templates()

        self.checklist_changed.emit()

    def _move_item(self, direction):
        row = self.items_table.currentRow()

        if row < 0:
            return

        new_row = row + direction

        if new_row < 0 or new_row >= self.items_table.rowCount():
            return

        self._commit_reorder(row, new_row)

    def _on_rows_moved(self, parent, start, end, destination, row):
        self._sync_order_to_db()

    def _sync_order_to_db(self):
        if not self.current_template_id:
            return

        item_ids = []

        for row in range(self.items_table.rowCount()):
            item_ids.append(self.items_table.item(row, 1).data(Qt.ItemDataRole.UserRole))

        if checklist_repo.reorder_checklist_items(self.current_template_id, item_ids):
            self._load_items(self.current_template_id)

            self.checklist_changed.emit()

    def _commit_reorder(self, old_index, new_index):
        if not self.current_template_id:
            return

        item_ids = []

        for row in range(self.items_table.rowCount()):
            item_ids.append(self.items_table.item(row, 1).data(Qt.ItemDataRole.UserRole))

        item_ids[old_index], item_ids[new_index] = item_ids[new_index], item_ids[old_index]

        if checklist_repo.reorder_checklist_items(self.current_template_id, item_ids):
            self._load_items(self.current_template_id)

            self.items_table.selectRow(new_index)

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

        self.setMinimumWidth(520)

        self.setObjectName("TaskEditorDialog")
        self._ui_tokens = getattr(parent, "_ui_tokens", get_dialog_theme_tokens())
        self._dialog_metrics = get_dialog_metric_tokens(apply_overrides=True)
        self._style_bundle = _checklist_subdialog_style_bundle(
            self._ui_tokens, self._dialog_metrics
        )
        self.setStyleSheet(_checklist_editor_stylesheet(self._ui_tokens, self._dialog_metrics))
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

        layout.addWidget(self.text_edit)

        desc_label = QLabel(t("checklist_mgr.header_desc"))
        desc_label.setObjectName("TaskDialogFieldLabel")
        layout.addWidget(desc_label)

        self.desc_edit = QTextEdit()

        self.desc_edit.setFixedHeight(62)

        self.desc_edit.setPlaceholderText(t("checklist_mgr.placeholder_item_desc"))

        layout.addWidget(self.desc_edit)

        guide_label = QLabel(t("checklist_mgr.header_guide"))
        guide_label.setObjectName("TaskDialogFieldLabel")
        layout.addWidget(guide_label)

        self.guide_edit = QTextEdit()

        self.guide_edit.setFixedHeight(78)

        self.guide_edit.setPlaceholderText(t("checklist_mgr.placeholder_item_guide"))

        layout.addWidget(self.guide_edit)

        self.req_check = QCheckBox(t("checklist_mgr.label_required_set"))
        self.req_check.setObjectName("TaskDialogOptionCheck")

        layout.addWidget(self.req_check)

        _sep = QFrame()
        _sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(_sep)

        buttons = QHBoxLayout()

        buttons.addStretch()

        save_btn = QPushButton(t("common.save"))

        save_btn.setObjectName("primary_btn")
        save_btn.setStyleSheet(self._style_bundle["button_primary"])

        save_btn.clicked.connect(self._save)

        buttons.addWidget(save_btn)

        cancel_btn = QPushButton(t("common.cancel"))

        cancel_btn.setObjectName("ghost_btn")
        cancel_btn.setStyleSheet(self._style_bundle["button_secondary"])

        cancel_btn.clicked.connect(self.reject)

        buttons.addWidget(cancel_btn)

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
            if checklist_repo.update_checklist_item(self.item_id, data):
                self.accept()

            return

        items = checklist_repo.get_checklist_items(self.template_id)

        checklist_repo.create_checklist_item(
            self.template_id,
            text,
            data["item_description"],
            data["item_guide"],
            len(items),
            data["is_required"],
        )

        self.accept()


class BulkOperationsDialog(QDialog):
    def __init__(self, template_id, parent=None):
        super().__init__(parent)

        self.template_id = template_id

        apply_dialog_title(self, t("checklist_mgr.btn_bulk"))

        self.setMinimumSize(460, 320)

        self.setObjectName("TaskEditorDialog")
        self._ui_tokens = getattr(parent, "_ui_tokens", get_dialog_theme_tokens())
        self._dialog_metrics = get_dialog_metric_tokens(apply_overrides=True)
        self._style_bundle = _checklist_subdialog_style_bundle(
            self._ui_tokens, self._dialog_metrics
        )
        self.setStyleSheet(_checklist_editor_stylesheet(self._ui_tokens, self._dialog_metrics))
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

        self.prefix_edit.setEnabled(False)

        layout.addWidget(self.prefix_edit)

        op_prefix.toggled.connect(self.prefix_edit.setEnabled)

        layout.addStretch()

        _sep = QFrame()
        _sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(_sep)

        buttons = QHBoxLayout()

        buttons.addStretch()

        apply_btn = QPushButton(t("checklist_mgr.btn_apply_bulk"))

        apply_btn.setObjectName("primary_btn")
        apply_btn.setStyleSheet(self._style_bundle["button_primary"])

        apply_btn.clicked.connect(self._apply)

        buttons.addWidget(apply_btn)

        cancel_btn = QPushButton(t("common.cancel"))

        cancel_btn.setObjectName("ghost_btn")
        cancel_btn.setStyleSheet(self._style_bundle["button_secondary"])

        cancel_btn.clicked.connect(self.reject)

        buttons.addWidget(cancel_btn)

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
