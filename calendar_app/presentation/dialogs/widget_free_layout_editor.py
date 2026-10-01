# -*- coding: utf-8 -*-
"""Transactional composition workspace with an isolated native widget preview."""

from copy import deepcopy
import logging

from PyQt6.QtCore import QCoreApplication, QDate, QEvent, Qt, QTimer
from PyQt6.QtGui import QFont, QKeySequence, QPalette, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
    get_dialog_theme_tokens,
)
from calendar_app.presentation.widgets.panel_widget_style import css_to_qcolor
from calendar_app.presentation.widgets.widget_free_layout import (
    BLOCK_MINIMUM_SIZES,
    CANVAS_MAXIMUM_SIZE,
    CANVAS_MINIMUM_SIZE,
    read_free_layout,
    seed_free_layout,
    validate_free_layout,
)
from calendar_app.presentation.widgets.widget_layout_editor_canvas import (
    LayoutEditorCanvas,
    _block_labels,
    align_selection,
    distribute_selection,
    overlap_pairs,
)
from calendar_app.presentation.widgets.widget_layout_editor_io import (
    load_layout_file,
    save_layout_file,
)
from calendar_app.presentation.widgets.widget_layout_presets import (
    SELECTED_LAYOUT_PRESET_KEY,
    create_layout_preset,
    delete_layout_preset,
    get_layout_preset,
    read_layout_presets,
    rename_layout_preset,
    update_layout_preset,
    write_layout_presets,
)
from calendar_app.presentation.widgets.widget_mode_opacity import read_widget_opacities
from calendar_app.presentation.widgets.widget_mode_skins import (
    read_widget_mode_layout_id,
    read_widget_mode_skin_id,
    widget_mode_layouts,
    widget_mode_skins,
)
from calendar_app.presentation.widgets.widget_mode_typography import read_widget_typography

logger = logging.getLogger(__name__)


class WidgetFreeLayoutEditorDialog(QDialog):
    def __init__(self, controller, parent=None, *, preset_id=None):
        super().__init__(parent)
        self.controller = controller
        settings = controller.main_window.settings
        self.presets = read_layout_presets(settings)
        self._initial_presets = deepcopy(self.presets)
        self.selected_preset_id = str(
            preset_id or settings.value(SELECTED_LAYOUT_PRESET_KEY, "") or ""
        )
        selected_preset = get_layout_preset(self.presets, self.selected_preset_id)
        if selected_preset is None:
            self.selected_preset_id = ""
        self._editing_preset_id = str(preset_id or "") if selected_preset is not None else ""
        self.draft = read_free_layout(settings)
        if preset_id and selected_preset is not None:
            self.draft = deepcopy(selected_preset["layout"])
        text_opacity, background_opacity = read_widget_opacities(settings)
        try:
            weight = int(settings.value("widget_mode_font_weight", 500))
        except (TypeError, ValueError, OverflowError):
            weight = 500
        self.appearance = {
            "widget_mode_skin": read_widget_mode_skin_id(settings),
            "widget_mode_font_family": str(
                settings.value("widget_mode_font_family", QApplication.font().family())
                or QApplication.font().family()
            ),
            "widget_mode_font_size": read_widget_typography(settings).preference,
            "widget_mode_font_weight": weight if weight in (400, 500, 600, 700) else 500,
            "widget_mode_text_opacity": text_opacity,
            "widget_mode_background_opacity": background_opacity,
        }
        self._history = [self._snapshot()]
        self._history_index = 0
        self._renderer = None
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._refresh_preview)
        self.setWindowTitle(t("widget_mode.free_layout_title", "위젯 구성 편집"))
        if self._editing_preset_id:
            self.setWindowTitle(
                t("widget_mode.preset_edit", "배치 수정…") + " · " + selected_preset["name"]
            )
        apply_common_dialog_style(self, minimum_width=760)
        tokens = get_dialog_theme_tokens()
        palette = self.palette()
        for role, key in (
            (QPalette.ColorRole.Window, "base_hex"),
            (QPalette.ColorRole.Base, "base_hex"),
            (QPalette.ColorRole.AlternateBase, "surface_item"),
            (QPalette.ColorRole.Text, "text_primary"),
            (QPalette.ColorRole.WindowText, "text_primary"),
            (QPalette.ColorRole.Highlight, "accent"),
            (QPalette.ColorRole.Mid, "text_muted"),
        ):
            palette.setColor(role, css_to_qcolor(tokens[key], tokens["base_hex"]))
        self.setPalette(palette)
        self.resize(1200, 800)
        root = QVBoxLayout(self)
        root.setSpacing(10)
        intro = QLabel(
            t(
                "widget_mode.free_wysiwyg_intro",
                "위젯에서 요소를 바로 선택해 이동·크기와 모양을 바꾸세요. 적용하기 전까지 현재 위젯은 바뀌지 않습니다.",
            ),
            self,
        )
        intro.setWordWrap(True)
        root.addWidget(intro)
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        root.addWidget(self.splitter, 1)
        self.controls_scroll = QScrollArea(self)
        self.controls_scroll.setWidgetResizable(True)
        self.controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.controls_scroll.setMinimumWidth(290)
        self.controls_scroll.setMaximumWidth(410)
        self.preferences_tabs = QTabWidget(self)
        self.preferences_tabs.tabBar().setUsesScrollButtons(True)
        self.controls_scroll.setWidget(self.preferences_tabs)
        self.controls_scroll.viewport().setPalette(palette)
        self.splitter.addWidget(self.controls_scroll)
        self._wheel_controls = []
        self.canvas = LayoutEditorCanvas(self.draft)
        self.canvas.setPalette(palette)
        self.component_checks = {}
        self.component_buttons = {}
        self.preferences_tabs.addTab(
            self._component_tab(), t("widget_mode.free_layout_components", "구성 요소")
        )
        self.preferences_tabs.addTab(
            self._geometry_tab(), t("widget_mode.free_tab_geometry", "위치·크기")
        )
        self.preferences_tabs.addTab(self._canvas_tab(), t("widget_mode.free_tab_canvas", "캔버스"))
        self.preferences_tabs.addTab(
            self._appearance_tab(), t("widget_mode.preferences_appearance", "모양")
        )
        self.presets_tab_index = self.preferences_tabs.addTab(
            self._presets_tab(), t("widget_mode.user_layouts", "내 배치")
        )
        workspace = QWidget(self)
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_checkbox = QCheckBox(t("widget_mode.free_live_preview", "미리보기"), workspace)
        self.preview_checkbox.setChecked(True)
        self.preview_checkbox.toggled.connect(self._preview_toggled)
        toolbar = QHBoxLayout()
        toolbar.addWidget(self.preview_checkbox)
        self.preset_manage_btn = self._button(
            t("widget_mode.user_layouts", "내 배치"),
            lambda: self.preferences_tabs.setCurrentIndex(self.presets_tab_index),
            workspace,
        )
        toolbar.addWidget(self.preset_manage_btn)
        toolbar.addStretch()
        self.zoom_combo = QComboBox(workspace)
        for scale in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
            self.zoom_combo.addItem(f"{round(scale * 100)}%", scale)
        self.zoom_combo.setCurrentIndex(self.zoom_combo.findData(1.0))
        self.zoom_combo.setAccessibleName(t("widget_mode.free_zoom", "확대"))
        self.zoom_combo.setFixedWidth(100)
        self.zoom_combo.currentIndexChanged.connect(self._change_zoom)
        toolbar.addWidget(self.zoom_combo)
        self.fit_btn = self._button(
            t("widget_mode.free_fit", "화면에 맞춤"), self.fit_canvas, workspace
        )
        toolbar.addWidget(self.fit_btn)
        workspace_layout.addLayout(toolbar)
        self.canvas_scroll = QScrollArea(workspace)
        self.canvas_scroll.setWidget(self.canvas)
        self.canvas_scroll.setWidgetResizable(False)
        self.canvas_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas_scroll.viewport().setPalette(palette)
        workspace_layout.addWidget(self.canvas_scroll, 1)
        self.status_label = QLabel(workspace)
        self.status_label.setWordWrap(True)
        workspace_layout.addWidget(self.status_label)
        self.source_badge = QLabel(workspace)
        workspace_layout.addWidget(self.source_badge)
        help_label = QLabel(
            t(
                "widget_mode.free_editor_help",
                "Ctrl·Shift+클릭: 여러 요소 · Delete: 숨기기 · Alt: 정렬 해제",
            ),
            workspace,
        )
        help_label.setWordWrap(True)
        workspace_layout.addWidget(help_label)
        self.splitter.addWidget(workspace)
        self.splitter.setHandleWidth(2)
        self.splitter.handle(1).setPalette(palette)
        self.splitter.handle(1).setAutoFillBackground(True)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([330, 850])
        self.canvas.selectionChanged.connect(self._sync_fields)
        self.canvas.selectionSetChanged.connect(self._sync_fields)
        self.canvas.previewChanged.connect(self._preview_changed)
        self.canvas.editCommitted.connect(self._commit)
        actions = QWidget(self)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        self.undo_btn = self._button(
            t("widget_mode.free_layout_undo", "실행 취소"), self.undo, actions
        )
        self.redo_btn = self._button(
            t("widget_mode.free_layout_redo", "다시 실행"), self.redo, actions
        )
        self.import_btn = self._button(
            t("widget_mode.free_import", "불러오기…"), self._import_file, actions
        )
        self.export_btn = self._button(
            t("widget_mode.free_export", "내보내기…"), self._export_file, actions
        )
        for button in (self.undo_btn, self.redo_btn, self.import_btn, self.export_btn):
            actions_layout.addWidget(button)
        footer, self.apply_btn, self.cancel_btn = build_dialog_footer(
            t("common.apply", "적용"), t("common.cancel", "취소"), extra_left_widget=actions
        )
        self.apply_btn.clicked.connect(self._apply)
        self.cancel_btn.clicked.connect(self.reject)
        for button in (self.apply_btn, self.cancel_btn):
            button.ensurePolished()
            button.setMaximumWidth(16777215)
            button.setMinimumWidth(button.fontMetrics().horizontalAdvance(button.text()) + 36)
        root.addLayout(footer)
        self._shortcuts = []
        for key, callback in (
            (QKeySequence.StandardKey.Undo, self.undo),
            (QKeySequence.StandardKey.Redo, self.redo),
        ):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)
        self._register_wheel_control(self.zoom_combo)
        self._sync_fields()
        self._preview_timer.start(0)
        if self.screen() is not None:
            available = self.screen().availableGeometry()
            self.resize(min(1200, available.width() - 36), min(800, available.height() - 36))

    def _button(self, text, callback, parent):
        button = QPushButton(text, parent)
        button.setObjectName("ghost_btn")
        button.setAccessibleName(text)
        button.clicked.connect(callback)
        button.ensurePolished()
        button.setMinimumWidth(button.fontMetrics().horizontalAdvance(text) + 36)
        return button

    def _tab(self):
        tab = QWidget(self)
        tab.setPalette(self.palette())
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)
        return tab, layout

    def _component_tab(self):
        tab, layout = self._tab()
        for block in self.draft["blocks"]:
            block_id = block["id"]
            label = _block_labels()[block_id]
            row = QHBoxLayout()
            check = QCheckBox(tab)
            check.setAccessibleName(
                t("widget_mode.free_toggle_component", "{name} 표시", name=label)
            )
            check.toggled.connect(
                lambda enabled, block_id=block_id: self._toggle_block(block_id, enabled)
            )
            button = self._button(
                label,
                lambda _checked=False, block_id=block_id: self._select_component(block_id),
                tab,
            )
            button.setCheckable(True)
            row.addWidget(check)
            row.addWidget(button, 1)
            layout.addLayout(row)
            self.component_checks[block_id] = check
            self.component_buttons[block_id] = button
        layout.addWidget(QLabel(t("widget_mode.free_layer", "요소 순서·잠금"), tab))
        order_row = QHBoxLayout()
        self.front_btn = self._button(
            t("widget_mode.free_front", "맨 앞으로"), lambda: self._change_order(True), tab
        )
        self.back_btn = self._button(
            t("widget_mode.free_back", "맨 뒤로"), lambda: self._change_order(False), tab
        )
        order_row.addWidget(self.front_btn)
        order_row.addWidget(self.back_btn)
        layout.addLayout(order_row)
        self.lock_btn = self._button(t("widget_mode.free_lock", "잠금"), self._toggle_lock, tab)
        layout.addWidget(self.lock_btn)
        layout.addStretch()
        return tab

    def _geometry_tab(self):
        tab, layout = self._tab()
        self.selected_label = QLabel(tab)
        self.selected_label.setWordWrap(True)
        layout.addWidget(self.selected_label)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        layout.addLayout(form)
        self.rect_spins = {}
        for key, name in (
            ("x", "가로 위치"),
            ("y", "세로 위치"),
            ("width", "너비"),
            ("height", "높이"),
        ):
            spin = QSpinBox(tab)
            spin.setAccessibleName(t(f"widget_mode.free_layout_{key}", name))
            spin.valueChanged.connect(self._change_rect)
            self.rect_spins[{"width": "w", "height": "h"}.get(key, key)] = spin
            form.addRow(spin.accessibleName(), spin)
            self._register_wheel_control(spin)
        layout.addWidget(QLabel(t("widget_mode.free_align", "정렬"), tab))
        alignment = QGridLayout()
        self.align_buttons = {}
        for index, (kind, fallback) in enumerate(
            (
                ("left", "왼쪽"),
                ("center_x", "가로 중앙"),
                ("right", "오른쪽"),
                ("top", "위쪽"),
                ("center_y", "세로 중앙"),
                ("bottom", "아래쪽"),
            )
        ):
            button = self._button(
                t(f"widget_mode.free_align_{kind}", fallback),
                lambda _checked=False, kind=kind: self._align(kind),
                tab,
            )
            alignment.addWidget(button, index, 0)
            self.align_buttons[kind] = button
        layout.addLayout(alignment)
        self.distribute_buttons = {}
        for axis, fallback in (("x", "가로 간격 맞춤"), ("y", "세로 간격 맞춤")):
            button = self._button(
                t(f"widget_mode.free_distribute_{axis}", fallback),
                lambda _checked=False, axis=axis: self._distribute(axis),
                tab,
            )
            layout.addWidget(button)
            self.distribute_buttons[axis] = button
        layout.addStretch()
        return tab

    def _canvas_tab(self):
        tab, layout = self._tab()
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        layout.addLayout(form)
        self.canvas_width = QSpinBox(tab)
        self.canvas_height = QSpinBox(tab)
        for axis, spin, key, fallback in (
            (0, self.canvas_width, "canvas_width", "캔버스 너비"),
            (1, self.canvas_height, "canvas_height", "캔버스 높이"),
        ):
            spin.setRange(CANVAS_MINIMUM_SIZE[axis], CANVAS_MAXIMUM_SIZE[axis])
            spin.setAccessibleName(t(f"widget_mode.free_layout_{key}", fallback))
            spin.valueChanged.connect(lambda value, axis=axis: self._change_canvas(axis, value))
            form.addRow(spin.accessibleName(), spin)
            self._register_wheel_control(spin)
        self.calendar_mode_combo = QComboBox(tab)
        self.calendar_mode_combo.addItem(t("widget_mode.week_toggle", "주간"), "week")
        self.calendar_mode_combo.addItem(t("widget_mode.month_toggle", "월간"), "month")
        self.calendar_mode_combo.setAccessibleName(
            t("widget_mode.free_layout_calendar_mode", "달력 보기")
        )
        self.calendar_mode_combo.currentIndexChanged.connect(self._change_calendar_mode)
        form.addRow(self.calendar_mode_combo.accessibleName(), self.calendar_mode_combo)
        self._register_wheel_control(self.calendar_mode_combo)
        self.snap_checkbox = QCheckBox(t("widget_mode.free_layout_snap", "격자에 맞추기"), tab)
        self.snap_checkbox.toggled.connect(self._change_snap)
        layout.addWidget(self.snap_checkbox)
        self.guides_checkbox = QCheckBox(t("widget_mode.free_guides", "요소에 맞추기"), tab)
        self.guides_checkbox.setChecked(True)
        self.guides_checkbox.toggled.connect(self._change_guides)
        layout.addWidget(self.guides_checkbox)
        snap_help = QLabel(
            t(
                "widget_mode.free_layout_snap_help",
                "8px 격자에 맞춥니다. Alt를 누르면 자유롭게 이동·크기 조절합니다. 방향키는 1px, Shift+방향키는 10px 이동합니다.",
            ),
            tab,
        )
        snap_help.setWordWrap(True)
        layout.addWidget(snap_help)
        self.preset_combo = QComboBox(tab)
        for preset in widget_mode_layouts():
            self.preset_combo.addItem(t(preset.label_key, preset.label_default), preset.layout_id)
        self.preset_combo.setCurrentIndex(
            max(
                0,
                self.preset_combo.findData(
                    read_widget_mode_layout_id(self.controller.main_window.settings)
                ),
            )
        )
        self.preset_combo.setAccessibleName(t("widget_mode.preferences_layout", "배치"))
        self._register_wheel_control(self.preset_combo)
        layout.addWidget(self.preset_combo)
        self.reset_btn = self._button(
            t("widget_mode.free_layout_reset", "프리셋에서 다시 시작"), self._reset_from_preset, tab
        )
        layout.addWidget(self.reset_btn)
        layout.addStretch()
        return tab

    def _appearance_tab(self):
        tab, layout = self._tab()
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        layout.addLayout(form)
        self.skin_combo = QComboBox(tab)
        for skin in widget_mode_skins():
            self.skin_combo.addItem(t(skin.label_key, skin.label_default), skin.skin_id)
        self.font_family = QFontComboBox(tab)
        self.font_size = QSpinBox(tab)
        self.font_size.setRange(10, 18)
        self.font_weight = QComboBox(tab)
        for weight, key, label in (
            (400, "font_regular", "보통"),
            (500, "font_medium", "중간"),
            (600, "font_semibold", "약간 굵게"),
            (700, "font_bold", "굵게"),
        ):
            self.font_weight.addItem(t(f"widget_mode.{key}", label), weight)
        self.text_opacity = QSpinBox(tab)
        self.text_opacity.setRange(20, 100)
        self.background_opacity = QSpinBox(tab)
        self.background_opacity.setRange(0, 100)
        self._appearance_controls = (
            ("widget_mode_skin", self.skin_combo, "style_color_skin", "색상 스킨"),
            ("widget_mode_font_family", self.font_family, "font_family", "글꼴"),
            ("widget_mode_font_size", self.font_size, "font_size", "글꼴 크기"),
            ("widget_mode_font_weight", self.font_weight, "font_weight", "글꼴 굵기"),
            ("widget_mode_text_opacity", self.text_opacity, "text_opacity", "글자 불투명도"),
            (
                "widget_mode_background_opacity",
                self.background_opacity,
                "background_opacity",
                "배경 불투명도",
            ),
        )
        for key, control, label_key, fallback in self._appearance_controls:
            control.setAccessibleName(t(f"widget_mode.{label_key}", fallback))
            form.addRow(control.accessibleName(), control)
            self._register_wheel_control(control)
            if isinstance(control, QFontComboBox):
                control.currentFontChanged.connect(
                    lambda font, key=key: self._change_appearance(key, font.family())
                )
            elif isinstance(control, QComboBox):
                control.currentIndexChanged.connect(
                    lambda _index, key=key, control=control: self._change_appearance(
                        key, control.currentData()
                    )
                )
            else:
                if "opacity" in key:
                    control.setSuffix("%")
                control.valueChanged.connect(
                    lambda value, key=key: self._change_appearance(key, value)
                )
        layout.addStretch()
        return tab

    def _presets_tab(self):
        tab, layout = self._tab()
        label = QLabel(
            t(
                "widget_mode.user_layouts_empty",
                "저장한 배치가 없습니다. 구성 편집에서 프리셋으로 저장하세요.",
            ),
            tab,
        )
        label.setWordWrap(True)
        self.presets_empty_label = label
        layout.addWidget(label)
        self.preset_library_combo = QComboBox(tab)
        self.preset_library_combo.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        self.preset_library_combo.setAccessibleName(
            t("widget_mode.preset_select", "저장한 배치 선택")
        )
        self.preset_library_combo.currentIndexChanged.connect(self._select_preset)
        self._register_wheel_control(self.preset_library_combo)
        layout.addWidget(self.preset_library_combo)
        self.preset_details = QLabel(tab)
        self.preset_details.setWordWrap(True)
        layout.addWidget(self.preset_details)
        self.preset_save_btn = self._button(
            t("widget_mode.preset_save_as", "새 프리셋으로 저장…"),
            lambda: self._prompt_preset_name(False),
            tab,
        )
        self.preset_update_btn = self._button(
            t("widget_mode.preset_update", "선택 프리셋 덮어쓰기"), self.update_selected_preset, tab
        )
        self.preset_rename_btn = self._button(
            t("widget_mode.preset_rename", "이름 변경…"),
            lambda: self._prompt_preset_name(True),
            tab,
        )
        self.preset_delete_btn = self._button(
            t("widget_mode.preset_delete", "삭제"), self._confirm_delete_preset, tab
        )
        self.preset_delete_btn.setObjectName("danger_btn")
        for button in (
            self.preset_save_btn,
            self.preset_update_btn,
            self.preset_rename_btn,
            self.preset_delete_btn,
        ):
            layout.addWidget(button)
        note = QLabel(
            t("widget_mode.preset_draft_note", "프리셋 변경도 적용을 눌러야 저장됩니다."), tab
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        return tab

    def _sync_preset_fields(self):
        self.preset_library_combo.blockSignals(True)
        self.preset_library_combo.clear()
        self.preset_library_combo.addItem(t("widget_mode.preset_modified", "수정한 배치"), "")
        for preset in self.presets:
            self.preset_library_combo.addItem(preset["name"], preset["id"])
        self.preset_library_combo.setCurrentIndex(
            max(0, self.preset_library_combo.findData(self.selected_preset_id))
        )
        self.preset_library_combo.blockSignals(False)
        self.presets_empty_label.setVisible(not self.presets)
        selected = get_layout_preset(self.presets, self.selected_preset_id)
        for button in (self.preset_update_btn, self.preset_rename_btn, self.preset_delete_btn):
            button.setEnabled(selected is not None)
        detail = (
            t("widget_mode.preset_loaded", "불러온 배치: {name}", name=selected["name"])
            if selected
            else t("widget_mode.preset_modified", "수정한 배치")
        )
        if selected and selected["layout"] != self.draft:
            detail += " · " + t("widget_mode.preset_modified", "수정한 배치")
        self.preset_details.setText(detail)

    def _select_preset(self, _index):
        self.selected_preset_id = self.preset_library_combo.currentData() or ""
        preset = get_layout_preset(self.presets, self.selected_preset_id)
        self._replace(preset["layout"] if preset is not None else self.draft)

    def save_as_preset(self, name):
        self.presets, self.selected_preset_id = create_layout_preset(self.presets, name, self.draft)
        self._commit()
        return self.selected_preset_id

    def update_selected_preset(self):
        self.presets = update_layout_preset(self.presets, self.selected_preset_id, self.draft)
        self._commit()

    def rename_selected_preset(self, name):
        self.presets = rename_layout_preset(self.presets, self.selected_preset_id, name)
        self._commit()

    def delete_selected_preset(self):
        self.presets = delete_layout_preset(self.presets, self.selected_preset_id)
        self.selected_preset_id = ""
        self._commit()

    def _prompt_preset_name(self, rename):
        preset = get_layout_preset(self.presets, self.selected_preset_id)
        dialog = QInputDialog(self)
        dialog.setWindowTitle(
            t("widget_mode.preset_rename", "이름 변경…")
            if rename
            else t("widget_mode.preset_save_as", "새 프리셋으로 저장…")
        )
        dialog.setLabelText(t("widget_mode.preset_name", "배치 이름"))
        dialog.setTextValue(preset["name"] if rename and preset else "")
        apply_common_dialog_style(dialog)
        edit = dialog.findChild(QLineEdit)
        if edit is not None:
            edit.setMaxLength(80)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.rename_selected_preset(dialog.textValue()) if rename else self.save_as_preset(
                    dialog.textValue()
                )
            except ValueError:
                message = QMessageBox(self)
                message.setIcon(QMessageBox.Icon.Warning)
                message.setWindowTitle(t("widget_mode.user_layouts", "내 배치"))
                message.setText(
                    t(
                        "widget_mode.preset_invalid_name",
                        "이름은 1~80자이며 다른 배치와 중복될 수 없습니다.",
                    )
                )
                apply_common_dialog_style(message)
                message.exec()

    def _confirm_delete_preset(self):
        preset = get_layout_preset(self.presets, self.selected_preset_id)
        if preset is None:
            return
        message = QMessageBox(self)
        message.setWindowTitle(t("widget_mode.preset_delete", "삭제"))
        message.setText(
            t(
                "widget_mode.preset_delete_confirm",
                "“{name}” 배치를 삭제할까요?",
                name=preset["name"],
            )
        )
        delete = message.addButton(
            t("widget_mode.preset_delete", "삭제"), QMessageBox.ButtonRole.DestructiveRole
        )
        delete.setObjectName("danger_btn")
        cancel = message.addButton(QMessageBox.StandardButton.Cancel)
        message.setDefaultButton(cancel)
        apply_common_dialog_style(message)
        message.exec()
        if message.clickedButton() is delete:
            self.delete_selected_preset()

    def _change_appearance(self, key, value):
        self.appearance[key] = value
        self._commit()

    def _snapshot(self):
        snapshot = deepcopy(self.draft)
        snapshot["_appearance"] = deepcopy(self.appearance)
        snapshot["_presets"] = deepcopy(self.presets)
        snapshot["_preset_id"] = self.selected_preset_id
        return snapshot

    def _register_wheel_control(self, control):
        control.installEventFilter(self)
        self._wheel_controls.append(control)
        if isinstance(control, (QSpinBox, QComboBox)) and control.lineEdit() is not None:
            control.lineEdit().installEventFilter(self)
            self._wheel_controls.append(control.lineEdit())

    def _selected_blocks(self):
        return [block for block in self.draft["blocks"] if block["id"] in self.canvas.selected_ids]

    def _sync_fields(self, _selected=None):
        selected = self._selected_blocks()
        primary = next(
            (block for block in selected if block["id"] == self.canvas.selected_id), None
        )
        self.selected_label.setText(
            t("widget_mode.free_multi_selected", "{count}개 선택", count=len(selected))
            if len(selected) > 1
            else _block_labels()[primary["id"]]
            if primary
            else t("widget_mode.free_layout_empty", "왼쪽에서 구성 요소를 선택하세요.")
        )
        for index, spin in enumerate(self.rect_spins.values()):
            spin.blockSignals(True)
            spin.setEnabled(
                len(selected) == 1 and primary is not None and not primary.get("locked", False)
            )
            if primary:
                x, y, width, height = primary["rect"]
                minimum_width, minimum_height = BLOCK_MINIMUM_SIZES[primary["id"]]
                bounds = (
                    (0, self.draft["canvas"][0] - width),
                    (0, self.draft["canvas"][1] - height),
                    (minimum_width, self.draft["canvas"][0] - x),
                    (minimum_height, self.draft["canvas"][1] - y),
                )
                spin.setRange(*bounds[index])
                spin.setValue(primary["rect"][index])
            else:
                spin.setValue(0)
            spin.blockSignals(False)
        for block in self.draft["blocks"]:
            check = self.component_checks[block["id"]]
            check.blockSignals(True)
            check.setChecked(block["enabled"])
            check.blockSignals(False)
            self.component_buttons[block["id"]].setChecked(block["id"] in self.canvas.selected_ids)
            self.component_buttons[block["id"]].setToolTip(
                _block_labels()[block["id"]]
                + (" · " + t("widget_mode.free_lock", "잠금") if block.get("locked") else "")
            )
        for control, value in (
            (self.canvas_width, self.draft["canvas"][0]),
            (self.canvas_height, self.draft["canvas"][1]),
            (self.snap_checkbox, self.draft["snap"]),
        ):
            control.blockSignals(True)
            control.setChecked(value) if isinstance(control, QCheckBox) else control.setValue(value)
            control.blockSignals(False)
        self.calendar_mode_combo.blockSignals(True)
        self.calendar_mode_combo.setCurrentIndex(
            self.calendar_mode_combo.findData(self.draft["calendar_mode"])
        )
        self.calendar_mode_combo.blockSignals(False)
        for key, control, _label, _fallback in self._appearance_controls:
            control.blockSignals(True)
            value = self.appearance[key]
            if isinstance(control, QFontComboBox):
                control.setCurrentFont(QFont(value))
            elif isinstance(control, QComboBox):
                control.setCurrentIndex(control.findData(value))
            else:
                control.setValue(value)
            control.blockSignals(False)
        movable = [block for block in selected if block["enabled"] and not block.get("locked")]
        for button in self.align_buttons.values():
            button.setEnabled(bool(movable))
        for button in self.distribute_buttons.values():
            button.setEnabled(len(movable) >= 3)
        for button in (self.front_btn, self.back_btn, self.lock_btn):
            button.setEnabled(bool(selected))
        self.lock_btn.setText(
            t("widget_mode.free_unlock", "잠금 해제")
            if selected and all(block.get("locked") for block in selected)
            else t("widget_mode.free_lock", "잠금")
        )
        self.lock_btn.setAccessibleName(self.lock_btn.text())
        self.undo_btn.setEnabled(self._history_index > 0)
        self.redo_btn.setEnabled(self._history_index < len(self._history) - 1)
        self._sync_preset_fields()
        self._update_status()

    def _update_status(self):
        text = t(
            "widget_mode.free_status",
            "{visible}개 표시 · {width} × {height}px",
            visible=sum(block["enabled"] for block in self.draft["blocks"]),
            width=self.draft["canvas"][0],
            height=self.draft["canvas"][1],
        )
        overlaps = overlap_pairs(self.draft)
        if overlaps:
            text += " · " + t(
                "widget_mode.free_overlap",
                "{count}곳 겹침 · 요소 순서로 조절하세요.",
                count=len(overlaps),
            )
        locked = sum(block.get("locked", False) for block in self._selected_blocks())
        if locked:
            text += " · " + t("widget_mode.free_locked_count", "{count}개 잠김", count=locked)
        self.status_label.setText(text)
        self.status_label.setAccessibleName(text)

    def _replace(self, data, *, remember=True):
        if "_appearance" in data:
            self.appearance = deepcopy(data["_appearance"])
        if "_presets" in data:
            self.presets = deepcopy(data["_presets"])
            self.selected_preset_id = data["_preset_id"]
        self.draft = validate_free_layout(data)
        self.canvas.set_data(self.draft)
        if remember:
            self._commit()
        else:
            self._sync_fields()
            self._schedule_preview()

    def _preview_changed(self, data):
        self.draft = deepcopy(data)
        self._sync_fields()
        self._schedule_preview()

    def _commit(self):
        self.draft = deepcopy(self.canvas.data)
        snapshot = self._snapshot()
        if snapshot != self._history[self._history_index]:
            self._history = self._history[: self._history_index + 1] + [snapshot]
            self._history_index += 1
        self._sync_fields()
        self._schedule_preview()

    def undo(self):
        if self._history_index > 0:
            self._history_index -= 1
            self._replace(self._history[self._history_index], remember=False)

    def redo(self):
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self._replace(self._history[self._history_index], remember=False)

    def _select_component(self, block_id):
        modifiers = QApplication.keyboardModifiers()
        self.canvas.select_block(
            block_id,
            additive=bool(
                modifiers
                & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
            ),
        )

    def _toggle_block(self, block_id, enabled):
        candidate = deepcopy(self.draft)
        next(block for block in candidate["blocks"] if block["id"] == block_id)["enabled"] = enabled
        self._replace(candidate)
        if enabled:
            self.canvas.select_block(block_id)

    def _change_rect(self, _value):
        if not self.canvas.selected_id:
            return
        candidate = deepcopy(self.draft)
        block = next(
            block for block in candidate["blocks"] if block["id"] == self.canvas.selected_id
        )
        if block.get("locked") or len(self.canvas.selected_ids) != 1:
            return
        block["rect"] = [spin.value() for spin in self.rect_spins.values()]
        self._replace(candidate)

    def _change_canvas(self, axis, value):
        candidate = deepcopy(self.draft)
        candidate["canvas"][axis] = value
        self._replace(candidate)

    def _change_snap(self, value):
        candidate = deepcopy(self.draft)
        candidate["snap"] = value
        self._replace(candidate)

    def _change_guides(self, value):
        self.canvas.guides_enabled = value

    def _change_calendar_mode(self, _index):
        candidate = deepcopy(self.draft)
        candidate["calendar_mode"] = self.calendar_mode_combo.currentData()
        self._replace(candidate)

    def _align(self, kind):
        self._replace(align_selection(self.draft, self.canvas.selected_ids, kind))

    def _distribute(self, axis):
        self._replace(distribute_selection(self.draft, self.canvas.selected_ids, axis))

    def _change_order(self, front):
        candidate = deepcopy(self.draft)
        selected = [
            block_id for block_id in candidate["order"] if block_id in self.canvas.selected_ids
        ]
        others = [block_id for block_id in candidate["order"] if block_id not in selected]
        candidate["order"] = others + selected if front else selected + others
        self._replace(candidate)

    def _toggle_lock(self):
        selected = self._selected_blocks()
        lock = not all(block.get("locked") for block in selected)
        candidate = deepcopy(self.draft)
        for block in candidate["blocks"]:
            if block["id"] in self.canvas.selected_ids:
                block["locked"] = lock
        self._replace(candidate)

    def _reset_from_preset(self):
        self.selected_preset_id = ""
        self._replace(seed_free_layout(self.preset_combo.currentData()))

    def _change_zoom(self, _index):
        self.canvas.set_zoom(float(self.zoom_combo.currentData()))

    def fit_canvas(self):
        viewport = self.canvas_scroll.viewport().size()
        width, height = self.draft["canvas"]
        scale = max(
            0.1, min(2.0, (viewport.width() - 24) / width, (viewport.height() - 24) / height)
        )
        self.zoom_combo.blockSignals(True)
        if self.zoom_combo.count() > 7:
            self.zoom_combo.removeItem(7)
        self.zoom_combo.addItem(f"{round(scale * 100)}%", scale)
        self.zoom_combo.setCurrentIndex(self.zoom_combo.count() - 1)
        self.zoom_combo.blockSignals(False)
        self.canvas.set_zoom(scale)

    def _preview_toggled(self, enabled):
        if enabled:
            self._schedule_preview()
        else:
            self._preview_timer.stop()
            self.canvas.set_preview_image(None)

    def _schedule_preview(self):
        if self.preview_checkbox.isChecked():
            self._preview_timer.start(50)

    def _refresh_preview(self):
        if not self.preview_checkbox.isChecked():
            return
        from calendar_app.presentation.widgets.widget_layout_editor_preview import PreviewRenderer

        if self._renderer is None:
            self._renderer = PreviewRenderer(self.controller.main_window.settings, parent=self)
        for key, value in self.appearance.items():
            self._renderer.settings.setValue(key, value)
        widget = getattr(self.controller, "widget", None)
        items = getattr(widget, "_last_items", None)
        items = items if isinstance(items, list) else None
        current_date = None
        get_date = getattr(self.controller, "_current_date", None)
        if callable(get_date):
            current_date = get_date()
        if not isinstance(current_date, QDate) or not current_date.isValid():
            current_date = QDate.currentDate()
        self.source_badge.setText(
            t("widget_mode.free_current_items", "현재 위젯의 항목")
            if items is not None
            else t("widget_mode.free_example_items", "예시 일정")
        )
        clock_label = getattr(widget, "clock_label", None)
        clock_text = clock_label.text() if isinstance(clock_label, QLabel) else None
        self.canvas.set_preview_image(
            self._renderer.render(
                self.draft,
                items=items,
                current_date=current_date,
                active_filter=getattr(widget, "_active_filter", None),
                clock_text=clock_text,
            )
        )

    def load_configuration(self, path):
        self._replace(load_layout_file(path))

    def save_configuration(self, path):
        return save_layout_file(path, self.draft)

    def _file_error(self):
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Icon.Warning)
        message.setWindowTitle(self.windowTitle())
        message.setText(t("widget_mode.free_file_error", "구성 파일을 처리하지 못했습니다."))
        apply_common_dialog_style(message)
        message.exec()

    def _import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            t("widget_mode.free_import", "불러오기…"),
            "",
            t("widget_mode.free_file_filter", "위젯 구성 (*.airlayout.json *.json)"),
        )
        if path:
            try:
                self.load_configuration(path)
            except (OSError, ValueError, TypeError, OverflowError):
                logger.warning("Cannot load widget configuration", exc_info=True)
                self._file_error()

    def _export_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            t("widget_mode.free_export", "내보내기…"),
            "widget.airlayout.json",
            t("widget_mode.free_file_filter", "위젯 구성 (*.airlayout.json *.json)"),
        )
        if path:
            try:
                self.save_configuration(path)
            except (OSError, ValueError, TypeError, OverflowError):
                logger.warning("Cannot save widget configuration", exc_info=True)
                self._file_error()

    def _apply(self):
        data = validate_free_layout(self.draft)
        settings = self.controller.main_window.settings
        if (
            self._editing_preset_id
            and self.selected_preset_id == self._editing_preset_id
            and get_layout_preset(self.presets, self.selected_preset_id) is not None
        ):
            self.presets = update_layout_preset(self.presets, self.selected_preset_id, data)
        if self.presets != self._initial_presets:
            write_layout_presets(settings, self.presets)
        settings.setValue(SELECTED_LAYOUT_PRESET_KEY, self.selected_preset_id)
        for key, value in self.appearance.items():
            settings.setValue(key, value)
        self.controller.apply_free_layout(data)
        if hasattr(settings, "sync"):
            settings.sync()
        self.accept()

    def done(self, result):
        self._preview_timer.stop()
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None
        super().done(result)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Wheel and watched in getattr(self, "_wheel_controls", ()):
            viewport = (
                self.canvas_scroll.viewport()
                if watched is self.zoom_combo
                else self.controls_scroll.viewport()
            )
            QCoreApplication.sendEvent(viewport, event)
            return True
        return super().eventFilter(watched, event)
