# -*- coding: utf-8 -*-
"""Read-only collection previews; only the parent commits an explicit choice."""

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QLabel,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
)
from calendar_app.presentation.widgets.overlay_color_utils import _parse_rgba
from calendar_app.presentation.widgets.overlay_display_presets import overlay_display_preset
from calendar_app.presentation.widgets.widget_graphic_catalog import graphic_collections
from calendar_app.presentation.widgets.widget_graphics import (
    WidgetGraphicSurface,
    keydeck_collection_deck,
)
from calendar_app.presentation.widgets.widget_placement import NoWheelComboBox


def collection_preview(widget, collection, size=QSize(220, 160)) -> QPixmap:
    kind = widget._graphic_kind()
    if kind == "weather":
        from calendar_app.presentation.widgets.weather_scene import render_scene_preview

        scene = collection.weather_scene
        preset = overlay_display_preset(collection.appearance)
        fg, text_alpha = _parse_rgba(preset.text_rgba)
        bg, bg_alpha = _parse_rgba(preset.background_rgba)
        if collection.widget_kind:
            fg, bg = QColor(collection.foreground), QColor(collection.background)
            bg_alpha = 240
        return render_scene_preview(
            scene,
            widget._weather_data,
            size,
            dpr=2,
            foreground=fg.name(),
            background_alpha=bg_alpha / 255,
            text_alpha=text_alpha / 255,
            family=widget.font_family(),
            background_override=bg.name()
            if collection.widget_kind or collection.collection_id == "air_instrument"
            else "",
            graphic_design=collection.collection_id,
        )
    if kind == "launcher_deck":
        from calendar_app.presentation.widgets.keydeck.renderer import KeyDeckRenderer

        renderer = KeyDeckRenderer()
        renderer.set_deck(keydeck_collection_deck(widget.deck(), collection.collection_id))
        picture = renderer.render_pixmap({}, dpr=2)
        return picture.scaled(
            size * 2, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
    preset = overlay_display_preset(collection.appearance)
    fg, text_alpha = _parse_rgba(preset.text_rgba)
    bg, bg_alpha = _parse_rgba(preset.background_rgba)
    if collection.widget_kind:
        fg, bg = QColor(collection.foreground), QColor(collection.background)
        bg_alpha = 240
    surface = WidgetGraphicSurface()
    surface.resize(320, 220)
    surface.configure(
        kind=kind,
        collection_id=collection.collection_id,
        data=widget._graphic_data(),
        family=widget.font_family(),
        foreground=fg.name(),
        background=bg.name(),
        background_alpha=bg_alpha / 255,
        text_alpha=text_alpha / 255,
        motion=False,
    )
    canvas = QPixmap(size * 2)
    canvas.setDevicePixelRatio(2)
    canvas.fill(QColor("#101a28"))
    painter = QPainter(canvas)
    factor = min((size.width() - 8) / 320, (size.height() - 8) / 220)
    painter.translate((size.width() - 320 * factor) / 2, (size.height() - 220 * factor) / 2)
    painter.scale(factor, factor)
    surface.render(painter)
    painter.end()
    surface.deleteLater()
    return canvas


class GraphicCollectionDialog(QDialog):
    def __init__(self, widget, *, allow_group=False):
        super().__init__(widget)
        apply_dialog_title(self, t("widget_graphics.choose", "그래픽 컬렉션"))
        apply_common_dialog_style(self, minimum_width=800)
        self.collection_id = widget.graphic_collection_id()
        self.apply_group = False
        self.motion = widget._get("graphics_motion", True, type_=bool)
        self.auto_contrast = widget._get("graphics_auto_contrast", True, type_=bool)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        scroll = QScrollArea(self)
        self._scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(scroll)
        root = QVBoxLayout(content)
        root.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        heading = QLabel(
            t(
                "widget_graphics.hint",
                "숫자·재질·배치를 함께 미리 보세요. 적용 전에는 위젯이 바뀌지 않습니다.",
            ),
            self,
        )
        heading.setWordWrap(True)
        root.addWidget(heading)
        cards = QGridLayout()
        cards.setHorizontalSpacing(16)
        cards.setVerticalSpacing(18)
        self.selection = QButtonGroup(self)
        self.radios = {}
        for index, collection in enumerate(graphic_collections(widget._graphic_kind())):
            card = QFrame(content)
            column = QVBoxLayout(card)
            column.setContentsMargins(0, 0, 0, 0)
            picture = QLabel(card)
            picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
            picture.setPixmap(collection_preview(widget, collection))
            picture.setFixedSize(228, 168)
            column.addWidget(picture)
            radio = QRadioButton(
                t("widget_graphics.designs." + collection.collection_id, collection.label)
                if collection.widget_kind
                else collection.label,
                card,
            )
            self.selection.addButton(radio)
            radio.setChecked(self.collection_id == collection.collection_id)
            radio.toggled.connect(
                lambda checked, selected=collection.collection_id: (
                    self._choose(selected) if checked else None
                )
            )
            self.radios[collection.collection_id] = radio
            column.addWidget(radio)
            description = QLabel(
                t(
                    "widget_graphics.layouts." + collection.layout
                    if collection.widget_kind
                    else "widget_graphics.description." + collection.collection_id,
                    collection.description,
                ),
                card,
            )
            description.setWordWrap(True)
            column.addWidget(description)
            cards.addWidget(card, index // 3, index % 3)
        root.addLayout(cards)
        legacy = QRadioButton(t("widget_graphics.original", "기존 디자인 · 개별 설정 유지"), self)
        self.selection.addButton(legacy)
        legacy.setChecked(not self.collection_id)
        legacy.toggled.connect(lambda checked: self._choose("") if checked else None)
        self.radios[""] = legacy
        outer.addWidget(legacy)
        self.motion_check = QCheckBox(t("widget_graphics.motion", "상태 변화 애니메이션"), self)
        self.motion_check.setChecked(self.motion)
        outer.addWidget(self.motion_check)
        self.contrast_check = QCheckBox(t("widget_graphics.contrast", "글자 대비 자동 보정"), self)
        self.contrast_check.setChecked(self.auto_contrast)
        outer.addWidget(self.contrast_check)
        self.scope = NoWheelComboBox(self)
        self.scope.addItem(t("widget_graphics.scope_one", "이 위젯에 적용"), False)
        if allow_group:
            self.scope.addItem(
                t("widget_graphics.scope_visible", "표시 중인 위젯 전체에 적용"), True
            )
        outer.addWidget(self.scope)
        note = QLabel(
            t(
                "widget_graphics.preserve",
                "내용·목표 시각·위치·키 동작은 유지됩니다. 기존 디자인으로 돌아가면 컬렉션이 바꾼 외관을 복원합니다.",
            ),
            self,
        )
        note.setWordWrap(True)
        outer.addWidget(note)
        footer, self.apply_button, cancel = build_dialog_footer(
            t("common.apply", "적용"), t("common.cancel", "취소")
        )
        self.apply_button.clicked.connect(self._apply)
        cancel.clicked.connect(self.reject)
        outer.addLayout(footer)
        self.setMinimumHeight(480)
        self.resize(820, 740)

    def _choose(self, collection_id):
        self.collection_id = collection_id

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        radio = self.radios.get(self.collection_id)
        if radio is not None and self.collection_id:
            self._scroll.ensureWidgetVisible(radio, 0, 24)

    def _apply(self):
        self.motion = self.motion_check.isChecked()
        self.auto_contrast = self.contrast_check.isChecked()
        self.apply_group = bool(self.scope.currentData())
        self.accept()
