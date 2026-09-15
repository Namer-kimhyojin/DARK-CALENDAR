# -*- coding: utf-8 -*-
"""Transactional widget preferences with a real, isolated widget preview."""

from PyQt6.QtCore import QDate, QEvent, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFontComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
)
from calendar_app.presentation.widgets.widget_mode_density import (
    DENSITIES,
    DENSITY_KEY,
    read_widget_density,
)
from calendar_app.presentation.widgets.widget_mode_opacity import (
    BACKGROUND_OPACITY_KEY,
    TEXT_OPACITY_KEY,
    read_widget_opacities,
)
from calendar_app.presentation.widgets.widget_mode_skins import (
    get_widget_mode_layout,
    read_widget_mode_layout_id,
    read_widget_mode_skin_id,
    widget_mode_layouts,
    widget_mode_skins,
)
from calendar_app.presentation.widgets.widget_mode_visibility import (
    read_widget_calendar_visibility,
    write_widget_calendar_visibility,
)


class _DraftSettings:
    def __init__(self, settings):
        self.source = settings
        self.values = {}

    def value(self, key, default=None, type=None):
        value = self.values.get(key, self.source.value(key, default))
        return type(value) if type is not None else value

    def setValue(self, key, value):
        self.values[key] = value


class WidgetCustomizationDialog(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.draft = _DraftSettings(controller.main_window.settings)
        self.draft.setValue("widget_mode_layout", read_widget_mode_layout_id(self.draft))
        self.draft.setValue("widget_mode_skin", read_widget_mode_skin_id(self.draft))
        self._building = True
        self.setWindowTitle(t("widget_mode.customize", "꾸미기"))
        self.resize(940, 680)
        apply_common_dialog_style(self)
        root = QVBoxLayout(self)
        body = QHBoxLayout()
        root.addLayout(body, 1)
        controls = QScrollArea(self)
        controls.setWidgetResizable(True)
        controls.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        controls.setMinimumWidth(410)
        tabs = QTabWidget(self)
        tabs.tabBar().setUsesScrollButtons(False)
        controls.setWidget(tabs)
        body.addWidget(controls, 1)
        tabs.addTab(self._layout_tab(), t("widget_mode.preferences_layout", "배치"))
        tabs.addTab(self._appearance_tab(), t("widget_mode.preferences_appearance", "모양"))
        tabs.addTab(self._visibility_tab(), t("widget_mode.preferences_visibility", "표시 항목"))

        self.preview_frame = QWidget(self)
        preview_column = QVBoxLayout(self.preview_frame)
        body.addWidget(self.preview_frame, 1)
        preview_column.addWidget(QLabel(t("widget_mode.preview", "미리보기 · 예시 일정"), self))
        self.preview_label = QLabel(self)
        self.preview_label.installEventFilter(self)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.preview_label.setMinimumSize(280, 350)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_column.addWidget(self.preview_label, 1)
        note = QLabel(
            t("widget_mode.preview_note", "적용하면 저장됩니다. 취소하면 기존 설정을 유지합니다."),
            self,
        )
        note.setWordWrap(True)
        preview_column.addWidget(note)
        footer, apply_btn, cancel_btn = build_dialog_footer(
            ok_label=t("common.apply", "적용"), cancel_label=t("common.cancel", "취소")
        )
        root.addLayout(footer)
        apply_btn.clicked.connect(self._apply)
        cancel_btn.clicked.connect(self.reject)
        self._build_preview()
        self._building = False
        self._refresh_preview()
        if self.screen() is not None:
            available = self.screen().availableGeometry()
            if available.width() < 760:
                body.removeWidget(self.preview_frame)
                tabs.addTab(self.preview_frame, t("widget_mode.preview", "미리보기 · 예시 일정"))
                tabs.tabBar().setUsesScrollButtons(True)
                tabs.currentChanged.connect(self._refresh_preview)
                controls.setMinimumWidth(280)
                self.preview_label.setMinimumSize(220, 220)
            if available.height() < 640:
                self.preview_label.setMinimumHeight(220)
            self.resize(min(940, available.width() - 40), min(680, available.height() - 40))

    def _layout_tab(self):
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        self.layout_group = QButtonGroup(self)
        self.layout_buttons = {}
        current = read_widget_mode_layout_id(self.draft)
        recommended = {"minimal", "agenda_first", "dashboard"}
        for spec in widget_mode_layouts():
            button = QToolButton(tab)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setText(t(spec.label_key, spec.label_default))
            button.setAccessibleName(button.text())
            button.setIcon(self._layout_icon(spec))
            button.setIconSize(QSize(90, 42))
            button.setCheckable(True)
            button.setStyleSheet(
                "QToolButton { min-height: 76px; max-height: 76px; min-width: 180px; padding: 4px; }"
                "QToolButton:checked { border: 2px solid #65a7ff; border-radius: 6px; }"
            )
            button.setChecked(spec.layout_id == current)
            button.setVisible(spec.layout_id in recommended or spec.layout_id == current)
            button.clicked.connect(
                lambda _checked=False, key=spec.layout_id: self._change("widget_mode_layout", key)
            )
            self.layout_group.addButton(button)
            self.layout_buttons[spec.layout_id] = button
            layout.addWidget(button)
        more = QPushButton(t("widget_mode.all_layouts", "전체 배치 보기"), tab)
        more.clicked.connect(lambda: [button.show() for button in self.layout_buttons.values()])
        layout.addWidget(more)
        layout.addStretch(1)
        return tab

    @staticmethod
    def _layout_icon(spec):
        pixmap = QPixmap(90, 58)
        pixmap.fill(QColor("#142235"))
        painter = QPainter(pixmap)
        rows = max(row + rs for _, row, col, rs, cs in spec.placements)
        cols = max(col + cs for _, row, col, rs, cs in spec.placements)
        for section, row, col, rs, cs in spec.placements:
            painter.fillRect(
                4 + int(col * 82 / cols),
                4 + int(row * 50 / rows),
                max(4, int(cs * 82 / cols) - 3),
                max(4, int(rs * 50 / rows) - 3),
                QColor("#65a7ff" if section == "agenda" else "#71839b"),
            )
        painter.end()
        return QIcon(pixmap)

    def _appearance_tab(self):
        tab = QWidget(self)
        form = QFormLayout(tab)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.skin_combo = QComboBox(tab)
        for skin in widget_mode_skins():
            swatch = QPixmap(20, 20)
            swatch.fill(
                QColor(
                    skin.token_overrides.get(
                        "accent", "#27374d" if skin.base_theme == "dark" else "#dce8f7"
                    )
                )
            )
            self.skin_combo.addItem(
                QIcon(swatch), t(skin.label_key, skin.label_default), skin.skin_id
            )
        self.skin_combo.setCurrentIndex(
            self.skin_combo.findData(read_widget_mode_skin_id(self.draft))
        )
        self.skin_combo.currentIndexChanged.connect(
            lambda: self._change("widget_mode_skin", self.skin_combo.currentData())
        )
        form.addRow(t("widget_mode.style_color_skin", "색상 스킨"), self.skin_combo)
        self.font_family = QFontComboBox(tab)
        self.font_family.setCurrentFont(
            QFont(
                str(
                    self.draft.value(
                        "widget_mode_font_family", self.controller.widget.font().family()
                    )
                )
            )
        )
        self.font_family.setMinimumWidth(0)
        self.font_family.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.font_family.currentFontChanged.connect(
            lambda font: self._change("widget_mode_font_family", font.family())
        )
        font_family_row = QHBoxLayout()
        font_family_row.setContentsMargins(0, 0, 0, 0)
        font_family_row.setSpacing(6)
        font_family_row.addWidget(self.font_family, 1)
        self.font_dropdown_btn = QToolButton(tab)
        self.font_dropdown_btn.setObjectName("font_dropdown_btn")
        self.font_dropdown_btn.setArrowType(Qt.ArrowType.DownArrow)
        self.font_dropdown_btn.setFixedSize(38, 36)
        self.font_dropdown_btn.setToolTip(t("widget_mode.font_dropdown", "글꼴 목록 열기"))
        self.font_dropdown_btn.setAccessibleName(self.font_dropdown_btn.toolTip())
        self.font_dropdown_btn.clicked.connect(self.font_family.showPopup)
        font_family_row.addWidget(self.font_dropdown_btn)
        form.addRow(t("widget_mode.font_family", "글꼴"), font_family_row)
        self.font_size = QSpinBox(tab)
        self.font_size.setRange(10, 18)
        self.font_size.setValue(int(self.draft.value("widget_mode_font_size", 12)))
        self.font_size.valueChanged.connect(
            lambda value: self._change("widget_mode_font_size", value)
        )
        font_size_label = QLabel(t("widget_mode.font_size", "전체 글자 크기"), tab)
        font_size_help = t(
            "widget_mode.font_size_help",
            "날짜, 버튼, 캘린더와 목록을 같은 비율로 조절합니다.",
        )
        font_size_label.setToolTip(font_size_help)
        self.font_size.setToolTip(font_size_help)
        self.font_size.setAccessibleDescription(font_size_help)
        form.addRow(font_size_label, self.font_size)
        self.font_weight = QComboBox(tab)
        for value, key, label in (
            (400, "regular", "보통"),
            (500, "medium", "중간"),
            (600, "semibold", "약간 굵게"),
            (700, "bold", "굵게"),
        ):
            self.font_weight.addItem(t(f"widget_mode.font_{key}", label), value)
        self.font_weight.setCurrentIndex(
            max(0, self.font_weight.findData(int(self.draft.value("widget_mode_font_weight", 500))))
        )
        self.font_weight.currentIndexChanged.connect(
            lambda: self._change("widget_mode_font_weight", self.font_weight.currentData())
        )
        form.addRow(t("widget_mode.font_weight", "제목 굵기"), self.font_weight)
        text_opacity, background_opacity = read_widget_opacities(self.draft)
        self.text_opacity = self._opacity_control(
            tab,
            form,
            TEXT_OPACITY_KEY,
            t("widget_mode.text_opacity", "글자 불투명도"),
            text_opacity,
            20,
        )
        self.background_opacity = self._opacity_control(
            tab,
            form,
            BACKGROUND_OPACITY_KEY,
            t("widget_mode.background_opacity", "배경 불투명도"),
            background_opacity,
            0,
        )
        opacity_help = QLabel(
            t(
                "widget_mode.split_opacity_help",
                "값이 높을수록 진하게 표시됩니다. 배경만 낮추면 글자는 선명하게 유지됩니다.",
            ),
            tab,
        )
        opacity_help.setWordWrap(True)
        opacity_help.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        form.addRow(opacity_help)
        return tab

    def _opacity_control(self, parent, form, key, title, value, minimum):
        row = QHBoxLayout()
        label = QLabel(title, parent)
        percent = QLabel(f"{value}%", parent)
        row.addWidget(label)
        row.addStretch(1)
        row.addWidget(percent)
        slider = QSlider(Qt.Orientation.Horizontal, parent)
        slider.setRange(minimum, 100)
        slider.setValue(value)
        slider.setAccessibleName(title)
        label.setBuddy(slider)
        slider.valueChanged.connect(lambda value: percent.setText(f"{value}%"))
        slider.valueChanged.connect(lambda value: self._change(key, value))
        form.addRow(row)
        form.addRow(slider)
        return slider

    def _visibility_tab(self):
        tab = QWidget(self)
        form = QVBoxLayout(tab)
        form.addWidget(QLabel(t("widget_mode.density", "목록 밀도"), tab))
        self.density_combo = QComboBox(tab)
        for density in DENSITIES:
            self.density_combo.addItem(
                t(f"widget_mode.density_{density.key}", density.label), density.key
            )
        self.density_combo.setCurrentIndex(
            self.density_combo.findData(read_widget_density(self.draft).key)
        )
        self.density_combo.setAccessibleName(t("widget_mode.density", "목록 밀도"))
        self.density_combo.currentIndexChanged.connect(
            lambda: self._change(DENSITY_KEY, self.density_combo.currentData())
        )
        form.addWidget(self.density_combo)
        help_label = QLabel(
            t("widget_mode.density_help", "글자 크기는 유지하고 행 간격과 시간 배치를 조절합니다."),
            tab,
        )
        help_label.setWordWrap(True)
        form.addWidget(help_label)
        for key, label, default in (
            ("widget_mode_show_clock", t("widget_mode.show_clock", "시계 표시"), "true"),
            (
                "widget_mode_show_week",
                t("widget_mode.show_week", "주간 날짜 표시 (지원 배치)"),
                "true",
            ),
            ("widget_mode_show_hint", t("widget_mode.show_hint", "보조 설명 표시"), "false"),
            (
                "widget_mode_show_completed",
                t("widget_mode.show_completed", "완료 업무 보기"),
                "false",
            ),
        ):
            checkbox = QCheckBox(label, tab)
            if key == "widget_mode_show_week":
                checkbox.setChecked(
                    read_widget_calendar_visibility(
                        self.draft, read_widget_mode_layout_id(self.draft)
                    )
                )
                checkbox.toggled.connect(self._change_calendar_visibility)
                self.calendar_visibility_checkbox = checkbox
            else:
                checkbox.setChecked(str(self.draft.value(key, default)).lower() == "true")
                checkbox.toggled.connect(lambda value, setting=key: self._change(setting, value))
            form.addWidget(checkbox)
        form.addStretch(1)
        return tab

    def _build_preview(self):
        from calendar_app.presentation.widgets.unified_widget_mode import (
            UnifiedWidgetController,
            UnifiedWidgetWindow,
        )

        self.preview_host = QWidget(self)
        self.preview_host.hide()
        self.preview_host.settings = self.draft
        self.preview_host.current_date = QDate.currentDate()
        self.preview_controller = UnifiedWidgetController(self.preview_host)
        self.preview = UnifiedWidgetWindow(self.preview_controller)
        self.preview_controller.widget = self.preview
        # A hidden top-level preview must not inherit the dialog's control metrics.
        # It is rendered offscreen only and explicitly owned for cleanup.
        self.preview.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        # This is a static two-item sample, not an interactive scrollable window.
        self.preview.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.destroyed.connect(self.preview.deleteLater)
        self.preview.resize(420, 600)

    def _change(self, key, value):
        self.draft.setValue(key, value)
        if key == "widget_mode_layout" and hasattr(self, "calendar_visibility_checkbox"):
            visible = read_widget_calendar_visibility(self.draft, value)
            self.calendar_visibility_checkbox.blockSignals(True)
            self.calendar_visibility_checkbox.setChecked(visible)
            self.calendar_visibility_checkbox.blockSignals(False)
        if not self._building:
            self._refresh_preview()

    def _change_calendar_visibility(self, visible: bool) -> None:
        write_widget_calendar_visibility(
            self.draft,
            read_widget_mode_layout_id(self.draft),
            visible,
        )
        if not self._building:
            self._refresh_preview()

    def _refresh_preview(self):
        if getattr(self, "_rendering", False):
            return
        self._rendering = True
        try:
            self._render_preview()
        finally:
            self._rendering = False

    def _render_preview(self):
        spec = get_widget_mode_layout(read_widget_mode_layout_id(self.draft))
        self.preview.apply_selected_layout(force=True)
        self.preview.resize(max(380, spec.preferred_size[0]), spec.preferred_size[1])
        self.preview._style_signature = None
        self.preview.apply_theme()
        show_completed = (
            str(self.draft.value("widget_mode_show_completed", "false")).lower() == "true"
        )
        self.preview.completed_btn.setChecked(show_completed)
        self.preview.update_agenda(
            [
                {
                    "title": t("widget_mode.preview_schedule", "프로젝트 회의"),
                    "time": "14:00",
                    "is_task": False,
                    "item_kind": "schedule",
                    "item_id": 2,
                    "source": "task",
                },
                {
                    "title": t("widget_mode.preview_work", "회의 자료 정리"),
                    "time": "",
                    "is_task": True,
                    "item_kind": "work",
                    "item_id": 1,
                    "source": "task",
                    "completed": show_completed,
                },
            ]
        )
        self.preview.layout().activate()
        # Render the widget's own transparent layers, not the dialog's background.
        self.preview.ensurePolished()
        ratio = self.preview.devicePixelRatioF()
        raw = QPixmap(self.preview.size() * ratio)
        raw.setDevicePixelRatio(ratio)
        raw.fill(Qt.GlobalColor.transparent)
        self.preview.render(raw, flags=QWidget.RenderFlag.DrawChildren)
        self._preview_pixmap = QPixmap(raw.size())
        self._preview_pixmap.setDevicePixelRatio(raw.devicePixelRatio())
        self._preview_pixmap.fill(QColor("#26364b"))
        painter = QPainter(self._preview_pixmap)
        for y in range(0, self.preview.height(), 24):
            for x in range(0, self.preview.width(), 24):
                if (x // 24 + y // 24) % 2:
                    painter.fillRect(x, y, 24, 24, QColor("#35465b"))
        painter.drawPixmap(0, 0, raw)
        painter.end()
        self._scale_preview()

    def _scale_preview(self):
        self.preview_label.setPixmap(
            self._preview_pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_preview_pixmap") and not self._building:
            self._scale_preview()

    def eventFilter(self, watched, event):
        if (
            watched is self.preview_label
            and event.type() == QEvent.Type.Resize
            and hasattr(self, "_preview_pixmap")
        ):
            self._scale_preview()
        return super().eventFilter(watched, event)

    def _apply(self):
        allowed = {
            "widget_mode_layout",
            "widget_mode_skin",
            "widget_mode_font_size",
            "widget_mode_font_family",
            "widget_mode_font_weight",
            TEXT_OPACITY_KEY,
            BACKGROUND_OPACITY_KEY,
            DENSITY_KEY,
            "widget_mode_show_clock",
            "widget_mode_show_week",
            "widget_mode_show_hint",
            "widget_mode_show_completed",
        }
        settings = self.controller.main_window.settings
        self.controller._save_geometry()
        for key, value in self.draft.values.items():
            if (
                key in allowed or key.startswith("widget_mode_calendar_visible_")
            ) and key != "widget_mode_layout":
                settings.setValue(key, value)
        self.controller.set_layout(read_widget_mode_layout_id(self.draft))
        widget = self.controller.widget
        if widget is not None:
            widget.apply_selected_layout(force=True)
            widget._style_signature = None
            widget.apply_theme()
            widget.completed_btn.setChecked(
                str(settings.value("widget_mode_show_completed", "false")).lower() == "true"
            )
        self.controller.force_refresh()
        if hasattr(settings, "sync"):
            settings.sync()
        self.accept()
