# -*- coding: utf-8 -*-
"""Local weather design gallery with real, shared HTML/face previews."""

from __future__ import annotations

from copy import deepcopy
from html import escape

from PyQt6.QtCore import QPoint, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPixmap, QTextDocument
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QVBoxLayout,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)
from calendar_app.presentation.widgets.overlay_base import _build_face_ss
from calendar_app.presentation.widgets.overlay_color_utils import _parse_rgba, _rgba_css
from calendar_app.presentation.widgets.overlay_display_presets import overlay_display_preset
from calendar_app.presentation.widgets.weather_asset_packs import get_weather_asset_pack
from calendar_app.presentation.widgets.weather_designs import (
    WEATHER_DESIGN_CATEGORIES,
    WeatherDesign,
    weather_design,
    weather_designs,
)
from calendar_app.presentation.widgets.weather_template import render_weather_template
from calendar_app.presentation.widgets.widget_placement import NoWheelComboBox
from calendar_app.presentation.widgets.widget_shapes import get_widget_shape

_THUMB = QSize(168, 104)
_DETAIL = QSize(264, 188)


def weather_design_preview_pixmap(
    design: WeatherDesign, data: dict, size: QSize, *, dpr: float = 1.0
) -> QPixmap:
    """Render a native QLabel and the same preset face used by the real widget.

    The temporary face has no owner, settings, timer or network manager. Its
    proportional fit changes only the preview painter, never the actual recipe.
    """
    preset = overlay_display_preset(design.appearance_preset_id)
    if preset is None:
        raise ValueError(f"Unknown weather appearance: {design.appearance_preset_id}")
    fg, fg_alpha = _parse_rgba(preset.text_rgba)
    bg, bg_alpha = _parse_rgba(preset.background_rgba)
    border, border_alpha = _parse_rgba(preset.border_rgba)
    shape = get_widget_shape(design.shape)
    params = dict(preset.style_params)
    if shape.shape_id != "card":
        params.update(radius=shape.radius, margins=list(shape.margins))
    margins = params.get("margins", [18, 10, 18, 10])
    families = set(QFontDatabase.families())
    family = next(
        (candidate for candidate in preset.font_candidates if candidate in families),
        QApplication.font().family(),
    )
    font = QFont(family, design.font_size)
    html = render_weather_template(
        design.template,
        data,
        asset_pack_id=design.asset_pack_id,
        base_font_size=design.font_size,
        icon_color=fg.name(),
    )
    frame = QFrame()
    frame.setObjectName("weatherDesignFace")
    frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    frame.setStyleSheet(
        _build_face_ss(
            "weatherDesignFace", params, bg, bg_alpha, border, border_alpha, fg, fg_alpha
        )
    )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(*margins)
    layout.setSpacing(0)
    label = QLabel(frame)
    label.setObjectName("weatherDesignText")
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(False)
    label.setFont(font)
    label.setStyleSheet(
        f"QLabel#weatherDesignText {{ font-family: '{escape(family)}'; "
        f"font-size: {design.font_size}pt; background: transparent; border: none; padding: 0; }}"
    )
    label.setText(
        f"<div style=\"color:{_rgba_css(fg, fg_alpha)};font-family:'{escape(family)}';"
        f'text-align:center">{html}</div>'
    )
    layout.addWidget(label)
    frame.ensurePolished()
    label.ensurePolished()
    document = QTextDocument()
    document.setDefaultFont(label.font())
    document.setDocumentMargin(0)
    document.setHtml(label.text())
    content = label.sizeHint().expandedTo(document.size().toSize())
    insets = frame.contentsMargins()
    width = max(80, content.width() + margins[0] + margins[2] + insets.left() + insets.right() + 8)
    height = max(
        40, content.height() + margins[1] + margins[3] + insets.top() + insets.bottom() + 8
    )
    if design.shape == "circle":
        width = height = max(120, width + 104, height + 104)
    elif design.shape == "capsule":
        width = max(width, height * 2)
    elif design.shape == "poster":
        height = max(height, round(width / float(shape.aspect_ratio or 0.72)))
    frame.resize(width, height)
    layout.activate()
    # Activating a styled native layout can grow the frame to its minimum size.
    # Fit and clipping must use that final geometry, rather than the requested size.
    width, height = frame.width(), frame.height()
    if design.shape == "circle" and width != height:
        frame.resize(max(width, height), max(width, height))
        layout.activate()
        width, height = frame.width(), frame.height()
    if design.shape in {"circle", "capsule"}:
        # Match the final window mask's radius rather than the shape's nominal radius.
        params["radius"] = min(width, height) // 2
        frame.setStyleSheet(
            _build_face_ss(
                "weatherDesignFace", params, bg, bg_alpha, border, border_alpha, fg, fg_alpha
            )
        )
        frame.ensurePolished()
        label.ensurePolished()
        layout.activate()
        width, height = frame.width(), frame.height()
    canvas = QPixmap(round(size.width() * dpr), round(size.height() * dpr))
    canvas.setDevicePixelRatio(dpr)
    # A shared desktop sample makes transparent typography readable in light dialogs.
    desktop_preset = overlay_display_preset("midnight_glass")
    desktop, _ = _parse_rgba(desktop_preset.background_rgba)
    canvas.fill(desktop)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    scale = min((size.width() - 12) / width, (size.height() - 12) / height)
    painter.translate((size.width() - width * scale) / 2, (size.height() - height * scale) / 2)
    painter.scale(scale, scale)
    if design.shape in {"circle", "capsule"}:
        path = QPainterPath()
        rect = QRectF(0, 0, width, height)
        if design.shape == "circle":
            path.addEllipse(rect)
        else:
            radius = min(width, height) / 2
            path.addRoundedRect(rect, radius, radius)
        painter.setClipPath(path)
    frame.render(painter, QPoint())
    painter.end()
    frame.deleteLater()
    return canvas


def _gallery_styles() -> str:
    colors = get_dialog_theme_tokens()
    metrics = get_dialog_metric_tokens()
    return f"""
    QLabel#weatherDesignTitle {{ font-size: {metrics["title_font_pt"]}px; font-weight: 700; }}
    QLabel#weatherDesignName {{ font-size: {metrics["subtitle_font_pt"]}px; font-weight: 700; }}
    QLabel#weatherDesignHint {{ color: {colors["text_muted"]}; }}
    QFrame#weatherDesignDetail {{ background: {colors["surface_item"]};
        border: 1px solid {colors["border"]}; border-radius: {metrics["group_radius"]}px; }}
    QListWidget#weatherDesignGrid {{ border: 1px solid {colors["border"]};
        border-radius: {metrics["list_radius"]}px; padding: 4px; }}
    QListWidget#weatherDesignGrid::item {{ border: 1px solid transparent;
        border-radius: {metrics["list_item_radius"]}px; padding: 3px; }}
    QListWidget#weatherDesignGrid::item:selected {{ background: {colors["list_selected_bg"]};
        border-color: {colors["list_selected_border"]}; color: {colors["list_selected_text"]}; }}
    """


class WeatherDesignGalleryDialog(QDialog):
    """Browse local designs, returning a recipe only after explicit Apply."""

    def __init__(
        self,
        weather_data: dict,
        parent=None,
        *,
        current_design_id: str = "",
        current_asset_pack: str = "air_soft",
        current_appearance: str = "custom",
    ):
        super().__init__(parent)
        self.selected_design: WeatherDesign | None = None
        self._weather_data = deepcopy(weather_data)
        self._opening_id = current_design_id
        self._preferred_id = current_design_id
        if weather_design(current_design_id) is None:
            match = next(
                (
                    item
                    for item in weather_designs()
                    if item.asset_pack_id == current_asset_pack
                    and item.appearance_preset_id == current_appearance
                ),
                weather_designs()[0],
            )
            self._preferred_id = match.design_id
        self._icons: dict[str, QIcon] = {}
        self._preview_id: str | None = None
        self._thumb_timer = QTimer(self)
        self._thumb_timer.setSingleShot(True)
        self._thumb_timer.timeout.connect(self._render_visible_thumbnail)
        apply_dialog_title(self, t("widget.weather.designs.title", "날씨 디자인 갤러리"))
        screen = self.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        width = min(980, available.width() - 32) if available else 980
        height = min(650, available.height() - 48) if available else 650
        apply_common_dialog_style(
            self,
            minimum_width=min(900, width),
            size=(width, height),
            extra_stylesheet=_gallery_styles(),
        )
        self._build_ui()
        self._reload()
        self.search_edit.setFocus()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)
        title = QLabel(t("widget.weather.designs.heading", "날씨를 보여 주는 새로운 방식"), self)
        title.setObjectName("weatherDesignTitle")
        title.setWordWrap(True)
        root.addWidget(title)
        hint = QLabel(
            t(
                "widget.weather.designs.hint",
                "일러스트·배치·외관을 함께 미리 보고 선택하세요. 적용 전까지 위젯은 바뀌지 않습니다.",
            ),
            self,
        )
        hint.setObjectName("weatherDesignHint")
        hint.setWordWrap(True)
        root.addWidget(hint)
        filters = QHBoxLayout()
        self.search_edit = QLineEdit(self)
        search_label = str(t("widget.weather.designs.search", "디자인 이름·분위기 검색"))
        self.search_edit.setPlaceholderText(search_label)
        self.search_edit.setAccessibleName(search_label)
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._reload)
        self.search_edit.returnPressed.connect(lambda: self.grid.setFocus())
        filters.addWidget(self.search_edit, 1)
        self.category_combo = NoWheelComboBox(self)
        self.category_combo.setAccessibleName(t("widget.weather.designs.category", "디자인 분류"))
        self.category_combo.addItem(t("widget.weather.designs.all", "모든 디자인"), "")
        for category_id, key, fallback in WEATHER_DESIGN_CATEGORIES:
            self.category_combo.addItem(str(t(key, fallback)), category_id)
        self.category_combo.currentIndexChanged.connect(self._reload)
        filters.addWidget(self.category_combo)
        root.addLayout(filters)
        context = QHBoxLayout()
        current = weather_design(self._opening_id)
        current_name = (
            str(t(current.label_key, current.label_default))
            if current
            else str(t("widget.weather.designs.custom", "사용자 지정"))
        )
        current_label = QLabel(
            t("widget.weather.designs.current", "현재 디자인: {name}", name=current_name), self
        )
        current_label.setObjectName("weatherDesignHint")
        current_label.setWordWrap(True)
        context.addWidget(current_label, 1)
        self.result_count = QLabel(self)
        self.result_count.setObjectName("weatherDesignHint")
        context.addWidget(self.result_count)
        root.addLayout(context)
        body = QHBoxLayout()
        body.setSpacing(12)
        self.stack = QStackedWidget(self)
        self.grid = QListWidget(self)
        self.grid.setObjectName("weatherDesignGrid")
        self.grid.setAccessibleName(t("widget.weather.designs.list", "날씨 디자인 목록"))
        self.grid.setViewMode(QListView.ViewMode.IconMode)
        self.grid.setMovement(QListView.Movement.Static)
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setIconSize(_THUMB)
        self.grid.setGridSize(QSize(176, 148))
        self.grid.setSpacing(0)
        self.grid.setWordWrap(False)
        self.grid.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.grid.setUniformItemSizes(True)
        self.grid.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.grid.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.grid.currentItemChanged.connect(lambda *_: self._refresh_detail())
        self.grid.itemDoubleClicked.connect(lambda *_: self._refresh_detail())
        self.grid.verticalScrollBar().valueChanged.connect(self._schedule_thumbnails)
        self.stack.addWidget(self.grid)
        self.empty = QLabel(
            t(
                "widget.weather.designs.empty",
                "검색 결과가 없습니다. 검색어 또는 분류를 바꿔 보세요.",
            ),
            self,
        )
        self.empty.setObjectName("weatherDesignHint")
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(self.empty)
        body.addWidget(self.stack, 1)
        body.addWidget(self._build_detail())
        root.addLayout(body, 1)
        preservation = QLabel(
            t(
                "widget.weather.designs.preserve",
                "도시·온도 단위·갱신 주기·화면 위치는 유지됩니다.",
            ),
            self,
        )
        preservation.setObjectName("weatherDesignHint")
        preservation.setWordWrap(True)
        root.addWidget(preservation)
        separator = QFrame(self)
        separator.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(separator)
        footer, self.apply_button, cancel = build_dialog_footer(
            t("widget.weather.designs.apply", "디자인 적용"), t("common.cancel", "취소")
        )
        self.apply_button.setDefault(False)
        self.apply_button.setAutoDefault(False)
        self.apply_button.clicked.connect(self._apply)
        cancel.clicked.connect(self.reject)
        root.addLayout(footer)

    def _build_detail(self) -> QFrame:
        panel = QFrame(self)
        panel.setObjectName("weatherDesignDetail")
        panel.setFixedWidth(292)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        self.detail_preview = QLabel(panel)
        self.detail_preview.setFixedSize(_DETAIL)
        self.detail_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_preview.setAccessibleName(
            t("widget.weather.designs.preview", "디자인 미리보기")
        )
        layout.addWidget(self.detail_preview)
        self.detail_name = QLabel(panel)
        self.detail_name.setObjectName("weatherDesignName")
        self.detail_name.setWordWrap(True)
        self.detail_name.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.detail_name)
        self.detail_description = QLabel(panel)
        self.detail_description.setWordWrap(True)
        self.detail_description.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.detail_description)
        self.detail_meta = QLabel(panel)
        self.detail_meta.setObjectName("weatherDesignHint")
        self.detail_meta.setWordWrap(True)
        layout.addWidget(self.detail_meta)
        preview_note = QLabel(
            t(
                "widget.weather.designs.preview_note",
                "저장된 날씨를 예시 배경 위에 표시합니다. 실제 크기는 위젯에서 조절할 수 있습니다.",
            ),
            panel,
        )
        preview_note.setObjectName("weatherDesignHint")
        preview_note.setWordWrap(True)
        layout.addWidget(preview_note)
        layout.addStretch()
        return panel

    def selected_design_id(self) -> str | None:
        item = self.grid.currentItem()
        design_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        return str(design_id) if weather_design(design_id) else None

    def _reload(self, *_args) -> None:
        self._thumb_timer.stop()
        category = str(self.category_combo.currentData() or "")
        words = self.search_edit.text().strip().casefold().split()
        self.grid.blockSignals(True)
        self.grid.clear()
        target = 0
        categories = {item[0]: str(t(item[1], item[2])) for item in WEATHER_DESIGN_CATEGORIES}
        for design in weather_designs():
            searchable = " ".join(
                (
                    design.design_id,
                    design.label_default,
                    str(t(design.label_key, design.label_default)),
                    design.category,
                    categories[design.category],
                    design.description_default,
                    str(t(design.description_key, design.description_default)),
                    design.appearance_preset_id,
                    design.asset_pack_id,
                )
            ).casefold()
            if category and design.category != category:
                continue
            if not all(word in searchable for word in words):
                continue
            name = str(t(design.label_key, design.label_default))
            if design.design_id == self._opening_id:
                name = f"✓ {name}"
            item = QListWidgetItem(self._icons.get(design.design_id, QIcon()), name)
            item.setSizeHint(QSize(176, 148))
            item.setData(Qt.ItemDataRole.UserRole, design.design_id)
            item.setData(Qt.ItemDataRole.AccessibleTextRole, name)
            item.setToolTip(f"{name}\n{t(design.description_key, design.description_default)}")
            self.grid.addItem(item)
            if design.design_id == self._preferred_id:
                target = self.grid.count() - 1
        if self.grid.count():
            self.grid.setCurrentRow(target)
        self.grid.blockSignals(False)
        self.stack.setCurrentWidget(self.grid if self.grid.count() else self.empty)
        self.result_count.setText(
            t(
                "widget.weather.designs.count",
                "{shown} / {total}개 디자인",
                shown=self.grid.count(),
                total=len(weather_designs()),
            )
        )
        self._refresh_detail()
        self._schedule_thumbnails()

    def _refresh_detail(self) -> None:
        design_id = self.selected_design_id()
        self.apply_button.setEnabled(design_id is not None)
        if design_id is None:
            self._preview_id = None
            for label in (
                self.detail_preview,
                self.detail_name,
                self.detail_description,
                self.detail_meta,
            ):
                label.clear()
            return
        self._preferred_id = design_id
        if self._preview_id == design_id:
            return
        self._preview_id = design_id
        design = weather_design(design_id)
        self.detail_name.setText(str(t(design.label_key, design.label_default)))
        self.detail_description.setText(str(t(design.description_key, design.description_default)))
        pack = get_weather_asset_pack(design.asset_pack_id)
        preset = overlay_display_preset(design.appearance_preset_id)
        shape = get_widget_shape(design.shape)
        self.detail_meta.setText(
            f"{t(pack.label_key, pack.label_default)}\n"
            f"{t(preset.label_key, preset.label_default)} · {t(shape.label_key, shape.label_default)}"
        )
        self.detail_preview.setPixmap(
            weather_design_preview_pixmap(design, self._weather_data, _DETAIL, dpr=2.0)
        )

    def _schedule_thumbnails(self, *_args) -> None:
        if self.isVisible() and not self._thumb_timer.isActive():
            self._thumb_timer.start(0)

    def _render_visible_thumbnail(self) -> None:
        if not self.isVisible():
            return
        viewport = self.grid.viewport().rect()
        for row in range(self.grid.count()):
            item = self.grid.item(row)
            design_id = str(item.data(Qt.ItemDataRole.UserRole))
            if design_id in self._icons or not self.grid.visualItemRect(item).intersects(viewport):
                continue
            pixmap = weather_design_preview_pixmap(
                weather_design(design_id), self._weather_data, _THUMB, dpr=2.0
            )
            icon = QIcon(pixmap)
            icon.addPixmap(pixmap, QIcon.Mode.Selected)
            self._icons[design_id] = icon
            item.setIcon(icon)
            self._thumb_timer.start(0)
            return

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._schedule_thumbnails()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "grid"):
            self._schedule_thumbnails()

    def done(self, result: int) -> None:
        self._thumb_timer.stop()
        super().done(result)

    def _apply(self) -> None:
        design = weather_design(self.selected_design_id())
        if design is not None:
            self.selected_design = design
            self.accept()


__all__ = ["WeatherDesignGalleryDialog", "weather_design_preview_pixmap"]
