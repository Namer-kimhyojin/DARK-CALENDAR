# -*- coding: utf-8 -*-
"""Small editor for persistent user widget-mode skins and layouts."""

from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
)
from calendar_app.presentation.widgets.widget_mode_skins import (
    create_user_widget_layout,
    create_user_widget_skin,
    widget_mode_layouts,
)


class WidgetStyleEditorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.created_kind = ""
        self.created_id = ""
        self._accent = QColor("#5b8def")
        self.setWindowTitle(t("widget_mode.editor_title", "위젯 스타일 만들기"))
        self.resize(460, 350)
        apply_common_dialog_style(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)
        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._build_skin_tab(), t("widget_mode.editor_skin", "색상 스킨"))
        self.tabs.addTab(self._build_layout_tab(), t("widget_mode.editor_layout", "레이아웃"))
        root.addWidget(self.tabs, 1)
        footer, save_btn, cancel_btn = build_dialog_footer(
            ok_label=t("common.save", "저장"),
            cancel_label=t("common.cancel", "취소"),
        )
        save_btn.clicked.connect(self._save)
        if cancel_btn is not None:
            cancel_btn.clicked.connect(self.reject)
        root.addLayout(footer)

    def _build_skin_tab(self) -> QWidget:
        tab = QWidget(self)
        form = QFormLayout(tab)
        self.skin_name = QLineEdit(tab)
        self.skin_base = QComboBox(tab)
        self.skin_base.addItem(t("widget_mode.editor_light", "밝은 기반"), "light")
        self.skin_base.addItem(t("widget_mode.editor_dark", "어두운 기반"), "dark")
        self.accent_btn = QPushButton(tab)
        self.accent_btn.clicked.connect(self._pick_accent)
        self._sync_accent_button()
        form.addRow(t("common.name", "이름"), self.skin_name)
        form.addRow(t("widget_mode.editor_base", "기반 테마"), self.skin_base)
        form.addRow(t("widget_mode.editor_accent", "강조 색상"), self.accent_btn)
        return tab

    def _build_layout_tab(self) -> QWidget:
        tab = QWidget(self)
        form = QFormLayout(tab)
        self.layout_name = QLineEdit(tab)
        self.layout_template = QComboBox(tab)
        for layout in widget_mode_layouts():
            if layout.layout_id.startswith("user_layout_"):
                continue
            self.layout_template.addItem(
                t(layout.label_key, layout.label_default), layout.layout_id
            )
        self.layout_width = QSpinBox(tab)
        self.layout_width.setRange(300, 1600)
        self.layout_width.setValue(420)
        self.layout_height = QSpinBox(tab)
        self.layout_height.setRange(360, 1400)
        self.layout_height.setValue(600)
        self.show_eyebrow = QCheckBox(
            t("widget_mode.editor_show_eyebrow", "상단 보조 제목 표시"), tab
        )
        self.show_eyebrow.setChecked(True)
        self.show_hint = QCheckBox(t("widget_mode.editor_show_hint", "안내 문구 표시"), tab)
        self.show_hint.setChecked(True)
        form.addRow(t("common.name", "이름"), self.layout_name)
        form.addRow(t("widget_mode.editor_template", "구성 템플릿"), self.layout_template)
        form.addRow(t("widget_mode.editor_width", "기본 너비"), self.layout_width)
        form.addRow(t("widget_mode.editor_height", "기본 높이"), self.layout_height)
        form.addRow("", self.show_eyebrow)
        form.addRow("", self.show_hint)
        return tab

    def _pick_accent(self) -> None:
        selected = QColorDialog.getColor(self._accent, self)
        if selected.isValid():
            self._accent = selected
            self._sync_accent_button()

    def _sync_accent_button(self) -> None:
        color = self._accent.name()
        self.accent_btn.setText(color.upper())
        self.accent_btn.setStyleSheet(f"background-color: {color};")

    def _save(self) -> None:
        try:
            if self.tabs.currentIndex() == 0:
                skin = create_user_widget_skin(
                    self.skin_name.text(),
                    base_theme=str(self.skin_base.currentData()),
                    accent=self._accent.name(),
                )
                self.created_kind, self.created_id = "skin", skin.skin_id
            else:
                layout = create_user_widget_layout(
                    self.layout_name.text(),
                    template_id=str(self.layout_template.currentData()),
                    preferred_size=(self.layout_width.value(), self.layout_height.value()),
                    show_eyebrow=self.show_eyebrow.isChecked(),
                    show_hint=self.show_hint.isChecked(),
                )
                self.created_kind, self.created_id = "layout", layout.layout_id
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, t("common.notification", "알림"), str(exc))
            return
        self.accept()
