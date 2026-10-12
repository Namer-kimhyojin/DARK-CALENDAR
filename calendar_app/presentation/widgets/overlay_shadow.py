# -*- coding: utf-8 -*-
"""Shared, instance-scoped text shadows and draft-only appearance controls."""

from dataclasses import dataclass, replace

from PyQt6.QtCore import QSignalBlocker, Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
    get_dialog_theme_tokens,
)
from calendar_app.presentation.widgets.widget_placement import NoWheelSlider


@dataclass(frozen=True)
class TextShadow:
    enabled: bool = False
    opacity: int = 65
    blur: int = 8
    distance: int = 2
    color: str = "#000000"

    @property
    def active(self):
        return self.enabled and self.opacity > 0

    @property
    def padding(self):
        return self.blur + self.distance if self.active else 0


def read_text_shadow(get):
    def integer(key, default, maximum):
        try:
            return max(0, min(maximum, int(get("text_shadow_" + key, default))))
        except (ValueError, TypeError, OverflowError):
            return default

    enabled = str(get("text_shadow_enabled", False)).lower() in {"true", "1", "yes"}
    color = QColor(str(get("text_shadow_color", "#000000")))
    return TextShadow(
        enabled=enabled,
        opacity=integer("opacity", 65, 100),
        blur=integer("blur", 8, 20),
        distance=integer("distance", 2, 12),
        color=color.name() if color.isValid() else "#000000",
    )


def store_text_shadow(set_value, shadow):
    for field in ("enabled", "opacity", "blur", "distance", "color"):
        set_value("text_shadow_" + field, getattr(shadow, field))


def apply_text_shadow(target, shadow):
    """Reuse child effects; never attach an effect to the layered window itself."""
    effect = target.graphicsEffect()
    if not shadow.active:
        if isinstance(effect, QGraphicsDropShadowEffect) and effect.property("overlayTextShadow"):
            effect.setEnabled(False)
        return
    if effect is not None and not effect.property("overlayTextShadow"):
        return  # Preserve effects owned by other widget features.
    if effect is None:
        effect = QGraphicsDropShadowEffect(target)
        effect.setProperty("overlayTextShadow", True)
        target.setGraphicsEffect(effect)
    color = QColor(shadow.color)
    color.setAlpha(round(shadow.opacity * 255 / 100))
    if effect.color() != color:
        effect.setColor(color)
    if effect.blurRadius() != shadow.blur:
        effect.setBlurRadius(shadow.blur)
    if effect.xOffset() != 0 or effect.yOffset() != shadow.distance:
        effect.setOffset(0, shadow.distance)
    if not effect.isEnabled():
        effect.setEnabled(True)


class TextShadowControls(QWidget):
    def __init__(self, shadow, parent=None):
        super().__init__(parent)
        tokens = get_dialog_theme_tokens()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.enabled = QCheckBox(t("widget.shadow.enabled", "글자 그림자 사용"))
        root.addWidget(self.enabled)
        shortcuts = QHBoxLayout()
        for key, value in (
            ("off", None),
            ("soft", TextShadow(True, 45, 6, 1)),
            ("strong", TextShadow(True, 80, 12, 3)),
        ):
            button = QPushButton(t("widget.shadow." + key, key))
            button.setObjectName("ghost_btn")
            button.setAutoDefault(False)
            button.clicked.connect(
                lambda checked=False, preset=value: self.set_values(
                    preset if preset is not None else replace(self.values(), enabled=False)
                )
            )
            shortcuts.addWidget(button)
        root.addLayout(shortcuts)
        self.fields = QWidget(self)
        form = QFormLayout(self.fields)
        form.setContentsMargins(0, 0, 0, 0)
        self.sliders = {}
        for key, label, maximum, suffix in (
            ("opacity", t("widget.shadow.opacity", "진하기"), 100, "%"),
            ("blur", t("widget.shadow.blur", "흐림"), 20, " px"),
            ("distance", t("widget.shadow.distance", "거리"), 12, " px"),
        ):
            slider = NoWheelSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, maximum)
            slider.setAccessibleName(label)
            value_label = QLabel()
            value_label.setMinimumWidth(42)
            value_label.setText(f"{slider.value()}{suffix}")
            slider.valueChanged.connect(
                lambda v, target=value_label, unit=suffix: target.setText(f"{v}{unit}")
            )
            slider.valueChanged.connect(self._refresh_preview)
            row = QHBoxLayout()
            row.addWidget(slider, 1)
            row.addWidget(value_label)
            form.addRow(label, row)
            self.sliders[key] = slider
        self.color = shadow.color
        self.color_button = QPushButton()
        self.color_button.setObjectName("ghost_btn")
        self.color_button.setAutoDefault(False)
        self.color_button.setAccessibleName(t("widget.shadow.color", "그림자 색상"))
        self.color_button.clicked.connect(self._choose_color)
        form.addRow(t("widget.shadow.color", "그림자 색상"), self.color_button)
        root.addWidget(self.fields)
        preview = QFrame(self)
        preview.setObjectName("TextShadowPreview")
        preview.setStyleSheet(
            f"QFrame#TextShadowPreview {{ background: {tokens['surface_alt']}; "
            f"border: 1px solid {tokens['border']}; border-radius: 8px; }}"
        )
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(34, 34, 34, 34)
        self.preview = QLabel("18:47", preview)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFont(QFont("Malgun Gothic", 32, QFont.Weight.Bold))
        self.preview.setStyleSheet(
            f"color: {tokens['text_primary']}; background: transparent; border: none; "
            "font-size: 32pt; font-weight: 700;"
        )
        self.preview.setAccessibleName(t("widget.shadow.title", "글자 그림자"))
        preview_layout.addWidget(self.preview)
        root.addWidget(preview)
        hint = QLabel(
            t("widget.shadow.hint", "배경과 테두리는 유지하고 글자에만 그림자를 더합니다.")
        )
        hint.setWordWrap(True)
        root.addWidget(hint)
        self.enabled.toggled.connect(self._refresh_preview)
        self.set_values(shadow)

    def values(self):
        return TextShadow(
            self.enabled.isChecked(),
            *(self.sliders[key].value() for key in ("opacity", "blur", "distance")),
            self.color,
        )

    def set_values(self, shadow):
        # Block only the checkbox: slider signals still update their value labels.
        with QSignalBlocker(self.enabled):
            self.enabled.setChecked(shadow.enabled)
        for key, slider in self.sliders.items():
            slider.setValue(getattr(shadow, key))
        self.color = shadow.color
        self.color_button.setText(self.color.upper())
        self._refresh_preview()

    def _refresh_preview(self, *args):
        self.fields.setEnabled(self.enabled.isChecked())
        apply_text_shadow(self.preview, self.values())

    def _choose_color(self):
        chosen = QColorDialog.getColor(
            QColor(self.color), self, t("widget.shadow.color", "그림자 색상")
        )
        if chosen.isValid():
            self.color = chosen.name()
            self.color_button.setText(self.color.upper())
            self._refresh_preview()


class TextShadowDialog(QDialog):
    def __init__(self, shadow, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("widget.shadow.title", "글자 그림자"))
        apply_common_dialog_style(self, minimum_width=420)
        root = QVBoxLayout(self)
        self.controls = TextShadowControls(shadow, self)
        root.addWidget(self.controls)
        footer, save, cancel = build_dialog_footer(
            ok_label=t("common.save", "저장"), cancel_label=t("common.cancel", "취소")
        )
        save.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        root.addLayout(footer)
