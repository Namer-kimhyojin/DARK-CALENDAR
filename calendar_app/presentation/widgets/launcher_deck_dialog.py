# -*- coding: utf-8 -*-
"""Visual array editor for launcher-deck overlay widgets."""

from __future__ import annotations

from copy import deepcopy

from PyQt6.QtCore import QMimeData, QPoint, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QDrag, QIcon, QKeySequence, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QCompleter,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.runtime.launcher_asset_store import import_launcher_asset
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
)
from calendar_app.presentation.widgets.launcher_deck_model import (
    ACTION_TYPES,
    ACTIVATION_TRIGGERS,
    ACTIVE_EFFECTS,
    ASSET_PLAYBACK_MODES,
    DECK_TEMPLATES,
    HOVER_EFFECTS,
    INTERACTION_DEFAULTS,
    INTERACTION_MODES,
    INTERNAL_ACTIONS,
    KEYCAP_ICONS,
    KEYCAP_OVERRIDE_DEFAULTS,
    KEYCAP_STYLES,
    LABEL_LAYOUTS,
    PATTERNS,
    PRESS_EFFECTS,
    RESULT_EFFECTS,
    SOUND_EVENTS,
    SOUND_PROFILES,
    apply_pattern,
    clear_keycap_interaction,
    clear_keycap_overrides,
    keycap_style,
    new_key,
    normalize_deck,
    preserve_deck_visuals,
    reflow_deck,
    template_deck,
)
from calendar_app.presentation.widgets.launcher_keycap_assets import (
    KEYCAP_ASSETS,
    crop_mosaic_pixmap,
)
from calendar_app.presentation.widgets.launcher_keycap_icons import (
    KEYCAP_ICON_PACKS,
    keycap_icon_asset,
    keycap_icon_pack,
)
from calendar_app.shared.icon_map import icon as _ic

_MIME_KEY_ID = "application/x-air-calendar-launcher-key"
_CUSTOM_ASSET_ID = "custom"


def _css_color(value: str, fallback: str) -> QColor:
    raw = str(value or "")
    if raw.startswith("#") and len(raw) == 9:
        try:
            return QColor(
                int(raw[1:3], 16),
                int(raw[3:5], 16),
                int(raw[5:7], 16),
                int(raw[7:9], 16),
            )
        except ValueError:
            pass
    color = QColor(raw)
    return color if color.isValid() else _css_color(fallback, "#ffffff")


def _rgba_hex(color: QColor) -> str:
    return f"#{color.red():02x}{color.green():02x}{color.blue():02x}{color.alpha():02x}"


def _asset_combo_icon(path) -> QIcon:
    source = QPixmap(str(path))
    if source.isNull():
        return QIcon()
    preview = QPixmap(36, 36)
    preview.fill(Qt.GlobalColor.transparent)
    painter = QPainter(preview)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#334155"))
    painter.drawRoundedRect(QRectF(1, 1, 34, 34), 8, 8)
    painter.drawPixmap(QRectF(5, 5, 26, 26).toRect(), source)
    painter.end()
    return QIcon(preview)


def _enable_combo_search(combo: QComboBox, placeholder: str) -> None:
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    if combo.lineEdit() is not None:
        combo.lineEdit().setPlaceholderText(placeholder)
    completer = combo.completer()
    if completer is not None:
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)


def deck_template_icon(deck: dict, size: QSize = QSize(148, 74)) -> QIcon:
    deck = normalize_deck(deck)
    pixmap = QPixmap(size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    columns, rows = int(deck["columns"]), int(deck["rows"])
    gap = 3.0
    cell_w = (size.width() - gap * (columns + 1)) / columns
    cell_h = (size.height() - gap * (rows + 1)) / rows
    for key in deck["keys"]:
        style = keycap_style(key["style"])
        rect = QRectF(
            gap + int(key["column"]) * (cell_w + gap),
            gap + int(key["row"]) * (cell_h + gap),
            cell_w * int(key["width"]) + gap * (int(key["width"]) - 1),
            cell_h * int(key["height"]) + gap * (int(key["height"]) - 1),
        )
        painter.setPen(QPen(_css_color(style.border, "#8aa9d9"), 1))
        painter.setBrush(_css_color(style.top, "#394965"))
        painter.drawRoundedRect(rect, 4, 4)
    painter.end()
    return QIcon(pixmap)


class _EditorKeyButton(QToolButton):
    def __init__(self, key: dict, on_selection, on_drop, parent=None):
        super().__init__(parent)
        self.key_id = str(key["id"])
        self._drag_start = QPoint()
        self._on_drop = on_drop
        self.setText(str(key["label"]))
        self.setCheckable(True)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip(t("widget.launcher.editor_drag_hint", "드래그하여 키 위치를 바꿉니다."))
        self.clicked.connect(lambda checked: on_selection(self.key_id, checked))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return super().mouseMoveEvent(event)
        if (event.position().toPoint() - self._drag_start).manhattanLength() < 10:
            return super().mouseMoveEvent(event)
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(_MIME_KEY_ID, self.key_id.encode("utf-8", errors="strict"))
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat(_MIME_KEY_ID):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        raw = bytes(event.mimeData().data(_MIME_KEY_ID))
        source_id = raw.decode("utf-8", errors="replace")
        if source_id and source_id != self.key_id:
            self._on_drop(source_id, self.key_id)
            event.acceptProposedAction()


class KeycapAppearanceDialog(QDialog):
    """Visual per-key designer whose result can be applied to one or many keys."""

    _COLOR_FIELDS = (
        ("custom_top", "widget.launcher.designer.top_color", "윗면 색상"),
        ("custom_bottom", "widget.launcher.designer.side_color", "옆면 색상"),
        ("custom_border", "widget.launcher.designer.border_color", "테두리 색상"),
        ("custom_text", "widget.launcher.designer.text_color", "글자 색상"),
    )

    def __init__(self, key: dict, parent=None):
        super().__init__(parent)
        self._draft = normalize_deck(
            {"version": 1, "columns": 3, "rows": 2, "gap": 8, "keys": [deepcopy(key)]}
        )["keys"][0]
        self._color_buttons: dict[str, QPushButton] = {}
        self._syncing = False
        apply_dialog_title(self, t("widget.launcher.designer.title", "키캡 디자인"))
        apply_common_dialog_style(self, minimum_width=760, size=(820, 650))
        self._build_ui()
        self._load_draft_into_controls()

    def result_appearance(self) -> dict:
        fields = ("style", *KEYCAP_OVERRIDE_DEFAULTS.keys())
        return {field: deepcopy(self._draft.get(field)) for field in fields}

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(12)

        heading = QLabel(t("widget.launcher.designer.heading", "나만의 키캡 만들기"), self)
        heading.setStyleSheet("font-size: 18px; font-weight: 700;")
        root.addWidget(heading)
        desc = QLabel(
            t(
                "widget.launcher.designer.desc",
                "색상과 형태, 아이콘, 데칼 에셋을 조합해 선택한 키를 디자인합니다.",
            ),
            self,
        )
        desc.setWordWrap(True)
        root.addWidget(desc)

        body = QHBoxLayout()
        preview_group = QGroupBox(t("widget.launcher.designer.preview", "실시간 미리보기"), self)
        preview_layout = QVBoxLayout(preview_group)
        from calendar_app.presentation.widgets.overlay_launcher_deck import LauncherKeycapButton

        self._preview = LauncherKeycapButton(self._draft, lambda _key: True, preview_group)
        self._preview.setCursor(Qt.CursorShape.ArrowCursor)
        self._preview.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if int(self._draft.get("height", 1)) > int(self._draft.get("width", 1)):
            self._preview.setFixedSize(190, 300)
        else:
            self._preview.setFixedSize(290, 190)
        preview_layout.addWidget(self._preview, 0, Qt.AlignmentFlag.AlignHCenter)
        preview_layout.addStretch()
        reset_button = QPushButton(
            t("widget.launcher.designer.reset_style", "스타일 기본값으로"), preview_group
        )
        reset_button.clicked.connect(self._reset_to_style)
        preview_layout.addWidget(reset_button)
        body.addWidget(preview_group, 4)

        self._controls_scroll = QScrollArea(self)
        self._controls_scroll.setWidgetResizable(True)
        self._controls_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        controls_host = QWidget(self._controls_scroll)
        controls = QVBoxLayout(controls_host)
        controls.setContentsMargins(0, 0, 4, 0)
        controls.setSpacing(9)

        base_group = QGroupBox(t("widget.launcher.designer.base", "기본 형태"), self)
        base_grid = QGridLayout(base_group)
        base_grid.addWidget(QLabel(t("widget.launcher.designer.style", "스타일")), 0, 0)
        self._style_combo = QComboBox(base_group)
        for style in KEYCAP_STYLES:
            self._style_combo.addItem(t(style.label_key, style.label_default), style.style_id)
        self._style_combo.currentIndexChanged.connect(self._style_changed)
        base_grid.addWidget(self._style_combo, 0, 1)
        base_grid.addWidget(QLabel(t("widget.launcher.designer.depth", "깊이")), 1, 0)
        self._depth_spin = QSpinBox(base_group)
        self._depth_spin.setRange(0, 14)
        self._depth_spin.setSuffix(" px")
        self._depth_spin.valueChanged.connect(self._controls_changed)
        base_grid.addWidget(self._depth_spin, 1, 1)
        base_grid.addWidget(QLabel(t("widget.launcher.designer.radius", "모서리")), 2, 0)
        self._radius_spin = QSpinBox(base_group)
        self._radius_spin.setRange(0, 28)
        self._radius_spin.setSuffix(" px")
        self._radius_spin.valueChanged.connect(self._controls_changed)
        base_grid.addWidget(self._radius_spin, 2, 1)
        base_grid.addWidget(QLabel(t("widget.launcher.designer.font_scale", "글자 크기")), 3, 0)
        self._font_scale_spin = QSpinBox(base_group)
        self._font_scale_spin.setRange(70, 160)
        self._font_scale_spin.setSuffix(" %")
        self._font_scale_spin.valueChanged.connect(self._controls_changed)
        base_grid.addWidget(self._font_scale_spin, 3, 1)
        controls.addWidget(base_group)

        color_group = QGroupBox(t("widget.launcher.designer.colors", "사용자 색상"), self)
        color_grid = QGridLayout(color_group)
        for row, (field, key, fallback) in enumerate(self._COLOR_FIELDS):
            color_grid.addWidget(QLabel(t(key, fallback), color_group), row, 0)
            button = QPushButton(color_group)
            button.setMinimumWidth(118)
            button.clicked.connect(lambda _checked=False, name=field: self._choose_color(name))
            color_grid.addWidget(button, row, 1)
            self._color_buttons[field] = button
        controls.addWidget(color_group)

        content_group = QGroupBox(t("widget.launcher.designer.content", "아이콘과 라벨"), self)
        content_grid = QGridLayout(content_group)
        content_grid.addWidget(QLabel(t("widget.launcher.designer.icon", "아이콘")), 0, 0)
        self._icon_combo = QComboBox(content_group)
        self._icon_combo.setIconSize(QSize(22, 22))
        for icon_id, key, fallback in KEYCAP_ICONS:
            icon_asset = keycap_icon_asset(icon_id)
            preview_icon = (
                _ic(icon_asset.icon_key, color="#62738b") if icon_asset.icon_key else QIcon()
            )
            self._icon_combo.addItem(preview_icon, t(key, fallback), icon_id)
        _enable_combo_search(
            self._icon_combo, t("widget.launcher.designer.search_icon", "아이콘 검색")
        )
        self._icon_combo.currentIndexChanged.connect(self._controls_changed)
        content_grid.addWidget(self._icon_combo, 0, 1)
        content_grid.addWidget(QLabel(t("widget.launcher.designer.layout", "표시 방식")), 1, 0)
        self._layout_combo = QComboBox(content_group)
        for layout_id, key, fallback in LABEL_LAYOUTS:
            self._layout_combo.addItem(t(key, fallback), layout_id)
        self._layout_combo.currentIndexChanged.connect(self._controls_changed)
        content_grid.addWidget(self._layout_combo, 1, 1)
        controls.addWidget(content_group)

        asset_group = QGroupBox(t("widget.launcher.designer.assets", "데칼 에셋"), self)
        asset_grid = QGridLayout(asset_group)
        asset_grid.addWidget(QLabel(t("widget.launcher.designer.asset", "에셋")), 0, 0)
        self._asset_combo = QComboBox(asset_group)
        self._asset_combo.setIconSize(QSize(32, 32))
        for asset in KEYCAP_ASSETS:
            asset_icon = _asset_combo_icon(asset.path()) if asset.filename else QIcon()
            self._asset_combo.addItem(
                asset_icon, t(asset.label_key, asset.label_default), asset.asset_id
            )
        self._asset_combo.addItem(t("widget.launcher.asset.custom", "내 이미지"), _CUSTOM_ASSET_ID)
        _enable_combo_search(
            self._asset_combo, t("widget.launcher.designer.search_asset", "에셋 검색")
        )
        self._asset_combo.currentIndexChanged.connect(self._asset_changed)
        asset_grid.addWidget(self._asset_combo, 0, 1)
        self._asset_path_button = QPushButton(
            t("widget.launcher.designer.choose_image", "이미지 불러오기..."), asset_group
        )
        self._asset_path_button.clicked.connect(self._choose_asset)
        asset_grid.addWidget(self._asset_path_button, 1, 0, 1, 2)
        asset_grid.addWidget(QLabel(t("widget.launcher.designer.asset_opacity", "에셋 농도")), 2, 0)
        self._asset_opacity_spin = QSpinBox(asset_group)
        self._asset_opacity_spin.setRange(10, 100)
        self._asset_opacity_spin.setSuffix(" %")
        self._asset_opacity_spin.valueChanged.connect(self._controls_changed)
        asset_grid.addWidget(self._asset_opacity_spin, 2, 1)
        asset_grid.addWidget(QLabel(t("widget.launcher.designer.asset_scale", "에셋 크기")), 3, 0)
        self._asset_scale_spin = QSpinBox(asset_group)
        self._asset_scale_spin.setRange(40, 160)
        self._asset_scale_spin.setSuffix(" %")
        self._asset_scale_spin.valueChanged.connect(self._controls_changed)
        asset_grid.addWidget(self._asset_scale_spin, 3, 1)
        controls.addWidget(asset_group)
        controls.addStretch()
        self._controls_scroll.setWidget(controls_host)
        body.addWidget(self._controls_scroll, 5)
        root.addLayout(body, 1)

        footer, apply_button, cancel_button = build_dialog_footer(
            ok_label=t("common.apply", "적용"), cancel_label=t("common.cancel", "취소")
        )
        apply_button.clicked.connect(self.accept)
        if cancel_button is not None:
            cancel_button.clicked.connect(self.reject)
        root.addLayout(footer)

    def _load_draft_into_controls(self) -> None:
        self._syncing = True
        style = keycap_style(self._draft.get("style"))
        self._style_combo.setCurrentIndex(self._style_combo.findData(style.style_id))
        self._depth_spin.setValue(
            int(self._draft["depth_override"])
            if int(self._draft["depth_override"]) >= 0
            else style.depth
        )
        self._radius_spin.setValue(
            int(self._draft["radius_override"])
            if int(self._draft["radius_override"]) >= 0
            else style.radius
        )
        self._font_scale_spin.setValue(int(self._draft["font_scale"]))
        self._icon_combo.setCurrentIndex(max(0, self._icon_combo.findData(self._draft["icon"])))
        self._layout_combo.setCurrentIndex(
            max(0, self._layout_combo.findData(self._draft["label_layout"]))
        )
        asset_id = _CUSTOM_ASSET_ID if self._draft.get("asset_path") else self._draft["asset_id"]
        self._asset_combo.setCurrentIndex(max(0, self._asset_combo.findData(asset_id)))
        self._asset_opacity_spin.setValue(int(self._draft["asset_opacity"]))
        self._asset_scale_spin.setValue(int(self._draft["asset_scale"]))
        self._syncing = False
        self._update_asset_button()
        self._update_color_buttons()
        self._preview.update()

    def _style_changed(self) -> None:
        if self._syncing:
            return
        self._draft["style"] = str(self._style_combo.currentData())
        style = keycap_style(self._draft["style"])
        self._syncing = True
        self._depth_spin.setValue(style.depth)
        self._radius_spin.setValue(style.radius)
        self._syncing = False
        for field, _key, _fallback in self._COLOR_FIELDS:
            self._draft[field] = ""
        self._controls_changed()

    def _controls_changed(self) -> None:
        if self._syncing:
            return
        self._draft["style"] = str(self._style_combo.currentData())
        self._draft["depth_override"] = self._depth_spin.value()
        self._draft["radius_override"] = self._radius_spin.value()
        self._draft["font_scale"] = self._font_scale_spin.value()
        self._draft["icon"] = str(self._icon_combo.currentData())
        self._draft["label_layout"] = str(self._layout_combo.currentData())
        asset_id = str(self._asset_combo.currentData())
        self._draft["asset_id"] = "none" if asset_id == _CUSTOM_ASSET_ID else asset_id
        if asset_id != _CUSTOM_ASSET_ID:
            self._draft["asset_path"] = ""
        self._draft["asset_opacity"] = self._asset_opacity_spin.value()
        self._draft["asset_scale"] = self._asset_scale_spin.value()
        self._update_asset_button()
        self._update_color_buttons()
        self._preview.update()

    def _choose_color(self, field: str) -> None:
        style = keycap_style(self._draft["style"])
        defaults = {
            "custom_top": style.top,
            "custom_bottom": style.bottom,
            "custom_border": style.border,
            "custom_text": style.text,
        }
        initial = _css_color(self._draft.get(field), defaults[field])
        color = QColorDialog.getColor(
            initial,
            self,
            t("widget.launcher.designer.choose_color", "색상 선택"),
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if color.isValid():
            self._draft[field] = _rgba_hex(color)
            self._update_color_buttons()
            self._preview.update()

    def _choose_asset(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            t("widget.launcher.designer.choose_image", "이미지 불러오기"),
            "",
            t(
                "widget.launcher.designer.image_filter",
                "이미지 및 아이콘 (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.svg)",
            ),
        )
        if path:
            imported = import_launcher_asset(path, "image")
            if not imported:
                QMessageBox.warning(
                    self,
                    t("widget.launcher.asset_import_failed_title", "에셋을 가져올 수 없음"),
                    t(
                        "widget.launcher.asset_import_failed",
                        "지원 형식과 25MB 이하의 파일인지 확인해 주세요.",
                    ),
                )
                return
            self._draft["asset_path"] = imported
            self._asset_combo.setCurrentIndex(self._asset_combo.findData(_CUSTOM_ASSET_ID))
            self._controls_changed()

    def _asset_changed(self) -> None:
        if self._syncing:
            return
        self._controls_changed()

    def _update_asset_button(self) -> None:
        is_custom = str(self._asset_combo.currentData()) == _CUSTOM_ASSET_ID
        self._asset_path_button.setVisible(is_custom)
        path = str(self._draft.get("asset_path", "") or "")
        self._asset_path_button.setText(
            path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            if path
            else t("widget.launcher.designer.choose_image", "이미지 불러오기...")
        )

    def _update_color_buttons(self) -> None:
        style = keycap_style(self._draft["style"])
        defaults = {
            "custom_top": style.top,
            "custom_bottom": style.bottom,
            "custom_border": style.border,
            "custom_text": style.text,
        }
        for field, button in self._color_buttons.items():
            color = _css_color(self._draft.get(field), defaults[field])
            text_color = "#111111" if color.lightness() > 160 else "#ffffff"
            button.setText(_rgba_hex(color).upper())
            button.setStyleSheet(
                f"background: {color.name()}; color: {text_color}; "
                "border: 1px solid rgba(127,145,168,96); font-weight: 600;"
            )

    def _reset_to_style(self) -> None:
        clear_keycap_overrides(self._draft)
        self._load_draft_into_controls()


class KeycapInteractionDialog(QDialog):
    """Professional interaction, motion, state, sound, and media editor."""

    _STATE_COLORS = (
        ("active_top", "widget.launcher.interaction.active_top", "활성 배경"),
        ("active_border", "widget.launcher.interaction.active_border", "활성 테두리"),
        ("disabled_top", "widget.launcher.interaction.disabled_top", "비활성 배경"),
        ("disabled_text", "widget.launcher.interaction.disabled_text", "비활성 글자"),
    )

    _PRESETS = {
        "balanced": {},
        "subtle": {
            "press_effect": "depress",
            "hover_effect": "lift",
            "active_effect": "solid",
            "success_effect": "ring",
            "error_effect": "ring",
            "animation_speed": 85,
            "sound_profile": "none",
        },
        "tactile": {
            "press_effect": "bounce",
            "hover_effect": "lift",
            "active_effect": "breathe",
            "success_effect": "pulse",
            "error_effect": "shake",
            "animation_speed": 135,
            "feedback_duration_ms": 900,
        },
        "neon": {
            "press_effect": "ripple",
            "hover_effect": "glow",
            "active_effect": "pulse",
            "success_effect": "flash",
            "error_effect": "flash",
            "active_top": "#183d55ee",
            "active_border": "#48edffff",
            "animation_speed": 120,
        },
        "accessible": {
            "press_effect": "depress",
            "hover_effect": "lift",
            "active_effect": "solid",
            "success_effect": "ring",
            "error_effect": "ring",
            "active_top": "#087f5bff",
            "active_border": "#c3fae8ff",
            "disabled_top": "#343a40ff",
            "disabled_text": "#f1f3f5ff",
            "reduce_motion": True,
            "show_status_indicator": True,
        },
    }

    def __init__(self, key: dict, parent=None):
        super().__init__(parent)
        self._draft = normalize_deck(
            {"version": 2, "columns": 3, "rows": 2, "gap": 8, "keys": [deepcopy(key)]}
        )["keys"][0]
        self._syncing = False
        self._state_color_buttons: dict[str, QPushButton] = {}
        apply_dialog_title(self, t("widget.launcher.interaction.title", "키 인터랙션 스튜디오"))
        apply_common_dialog_style(self, minimum_width=900, size=(960, 700))
        self._build_ui()
        self._load_draft_into_controls()

    def result_interaction(self) -> dict:
        return {field: deepcopy(self._draft.get(field)) for field in INTERACTION_DEFAULTS}

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)
        heading = QLabel(
            t("widget.launcher.interaction.heading", "누르는 순간부터 결과까지 디자인"), self
        )
        heading.setStyleSheet("font-size: 19px; font-weight: 750;")
        root.addWidget(heading)
        description = QLabel(
            t(
                "widget.launcher.interaction.desc",
                "실행 방식, 모션, 상태 색상, 사운드와 움직이는 에셋 재생 조건을 한곳에서 설정합니다.",
            ),
            self,
        )
        description.setWordWrap(True)
        root.addWidget(description)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel(t("widget.launcher.interaction.preset", "빠른 프리셋"), self))
        self._preset_combo = QComboBox(self)
        for preset_id, label in (
            ("balanced", t("widget.launcher.preset.balanced", "균형 잡힌 기본")),
            ("subtle", t("widget.launcher.preset.subtle", "차분하고 섬세하게")),
            ("tactile", t("widget.launcher.preset.tactile", "손맛이 느껴지는 키")),
            ("neon", t("widget.launcher.preset.neon", "네온 퍼포먼스")),
            ("accessible", t("widget.launcher.preset.accessible", "고대비 · 모션 최소화")),
        ):
            self._preset_combo.addItem(label, preset_id)
        preset_row.addWidget(self._preset_combo, 1)
        preset_button = QPushButton(t("widget.launcher.preset.apply", "프리셋 적용"), self)
        preset_button.setObjectName("primary_btn")
        preset_button.clicked.connect(self._apply_preset)
        preset_row.addWidget(preset_button)
        root.addLayout(preset_row)

        body = QHBoxLayout()
        preview_group = QGroupBox(t("widget.launcher.interaction.preview", "상태 미리보기"), self)
        preview_layout = QVBoxLayout(preview_group)
        from calendar_app.presentation.widgets.overlay_launcher_deck import LauncherKeycapButton

        self._preview = LauncherKeycapButton(
            deepcopy(self._draft), lambda _key: True, preview_group
        )
        self._preview.setFixedSize(270, 170)
        preview_layout.addWidget(self._preview, 0, Qt.AlignmentFlag.AlignHCenter)
        self._preview_state = QLabel("", preview_group)
        self._preview_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_state.setStyleSheet("font-weight: 650; color: #738198;")
        preview_layout.addWidget(self._preview_state)
        state_grid = QGridLayout()
        for index, (state_id, label) in enumerate(
            (
                ("ready", t("widget.launcher.state.ready", "대기")),
                ("active", t("widget.launcher.state.active", "활성")),
                ("success", t("widget.launcher.state.success", "성공")),
                ("error", t("widget.launcher.state.error", "실패")),
                ("disabled", t("widget.launcher.state.disabled", "비활성")),
            )
        ):
            button = QPushButton(label, preview_group)
            button.clicked.connect(lambda _checked=False, value=state_id: self._simulate(value))
            state_grid.addWidget(button, index // 2, index % 2)
        preview_layout.addLayout(state_grid)
        preview_layout.addStretch()
        body.addWidget(preview_group, 35)

        self._tabs = QTabWidget(self)
        self._tabs.addTab(self._build_behavior_tab(), t("widget.launcher.tab.behavior", "동작"))
        self._tabs.addTab(self._build_motion_tab(), t("widget.launcher.tab.motion", "모션"))
        self._tabs.addTab(self._build_state_tab(), t("widget.launcher.tab.states", "상태"))
        self._tabs.addTab(
            self._build_media_tab(), t("widget.launcher.tab.media", "사운드 · 미디어")
        )
        body.addWidget(self._tabs, 65)
        root.addLayout(body, 1)

        footer, apply_button, cancel_button = build_dialog_footer(
            ok_label=t("common.apply", "적용"), cancel_label=t("common.cancel", "취소")
        )
        apply_button.clicked.connect(self.accept)
        if cancel_button is not None:
            cancel_button.clicked.connect(self.reject)
        root.addLayout(footer)

    @staticmethod
    def _form_tab() -> tuple[QWidget, QFormLayout]:
        host = QWidget()
        form = QFormLayout(host)
        form.setContentsMargins(16, 16, 16, 16)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        return host, form

    def _combo(self, parent: QWidget, items: tuple) -> QComboBox:
        combo = QComboBox(parent)
        for item_id, key, fallback in items:
            combo.addItem(t(key, fallback), item_id)
        combo.currentIndexChanged.connect(self._controls_changed)
        return combo

    def _build_behavior_tab(self) -> QWidget:
        tab, form = self._form_tab()
        self._enabled_check = QCheckBox(t("widget.launcher.interaction.enabled", "이 키 사용"), tab)
        self._enabled_check.toggled.connect(self._controls_changed)
        form.addRow("", self._enabled_check)
        self._mode_combo = self._combo(tab, INTERACTION_MODES)
        form.addRow(t("widget.launcher.interaction.mode", "활성 방식"), self._mode_combo)
        self._trigger_combo = self._combo(tab, ACTIVATION_TRIGGERS)
        form.addRow(t("widget.launcher.interaction.trigger", "실행 시점"), self._trigger_combo)
        self._long_press_spin = QSpinBox(tab)
        self._long_press_spin.setRange(300, 2000)
        self._long_press_spin.setSingleStep(50)
        self._long_press_spin.setSuffix(" ms")
        self._long_press_spin.valueChanged.connect(self._controls_changed)
        form.addRow(
            t("widget.launcher.interaction.long_press", "길게 누르는 시간"), self._long_press_spin
        )
        self._indicator_check = QCheckBox(
            t("widget.launcher.interaction.indicator", "상태 표시점 보이기"), tab
        )
        self._indicator_check.toggled.connect(self._controls_changed)
        form.addRow("", self._indicator_check)
        return tab

    def _build_motion_tab(self) -> QWidget:
        tab, form = self._form_tab()
        self._press_effect_combo = self._combo(tab, PRESS_EFFECTS)
        form.addRow(
            t("widget.launcher.interaction.press_effect", "누름 효과"), self._press_effect_combo
        )
        self._hover_effect_combo = self._combo(tab, HOVER_EFFECTS)
        form.addRow(
            t("widget.launcher.interaction.hover_effect", "호버 효과"), self._hover_effect_combo
        )
        self._active_effect_combo = self._combo(tab, ACTIVE_EFFECTS)
        form.addRow(
            t("widget.launcher.interaction.active_effect", "활성 효과"), self._active_effect_combo
        )
        self._success_effect_combo = self._combo(tab, RESULT_EFFECTS)
        form.addRow(
            t("widget.launcher.interaction.success_effect", "성공 효과"), self._success_effect_combo
        )
        self._error_effect_combo = self._combo(tab, RESULT_EFFECTS)
        form.addRow(
            t("widget.launcher.interaction.error_effect", "실패 효과"), self._error_effect_combo
        )
        self._animation_speed_spin = QSpinBox(tab)
        self._animation_speed_spin.setRange(50, 200)
        self._animation_speed_spin.setSuffix(" %")
        self._animation_speed_spin.valueChanged.connect(self._controls_changed)
        form.addRow(t("widget.launcher.interaction.speed", "모션 속도"), self._animation_speed_spin)
        self._feedback_duration_spin = QSpinBox(tab)
        self._feedback_duration_spin.setRange(250, 3000)
        self._feedback_duration_spin.setSingleStep(50)
        self._feedback_duration_spin.setSuffix(" ms")
        self._feedback_duration_spin.valueChanged.connect(self._controls_changed)
        form.addRow(
            t("widget.launcher.interaction.duration", "결과 표시 시간"),
            self._feedback_duration_spin,
        )
        self._reduce_motion_check = QCheckBox(
            t("widget.launcher.interaction.reduce_motion", "모션 최소화"), tab
        )
        self._reduce_motion_check.toggled.connect(self._controls_changed)
        form.addRow("", self._reduce_motion_check)
        return tab

    def _build_state_tab(self) -> QWidget:
        tab, form = self._form_tab()
        for field, key, fallback in self._STATE_COLORS:
            button = QPushButton(tab)
            button.clicked.connect(
                lambda _checked=False, name=field: self._choose_state_color(name)
            )
            form.addRow(t(key, fallback), button)
            self._state_color_buttons[field] = button
        note = QLabel(
            t(
                "widget.launcher.interaction.state_note",
                "토글 키의 활성 상태는 위젯을 다시 열어도 유지됩니다.",
            ),
            tab,
        )
        note.setWordWrap(True)
        form.addRow("", note)
        return tab

    def _build_media_tab(self) -> QWidget:
        tab, form = self._form_tab()
        self._asset_playback_combo = self._combo(tab, ASSET_PLAYBACK_MODES)
        form.addRow(
            t("widget.launcher.interaction.asset_playback", "움직이는 이미지"),
            self._asset_playback_combo,
        )
        self._sound_combo = self._combo(tab, SOUND_PROFILES)
        _enable_combo_search(
            self._sound_combo, t("widget.launcher.interaction.search_sound", "사운드 검색")
        )
        form.addRow(t("widget.launcher.interaction.sound", "피드백 사운드"), self._sound_combo)
        self._sound_preview_button = QPushButton(
            t("widget.launcher.interaction.preview_sound", "사운드 미리 듣기"), tab
        )
        self._sound_preview_button.clicked.connect(self._preview_sound)
        form.addRow("", self._sound_preview_button)
        self._sound_event_combo = self._combo(tab, SOUND_EVENTS)
        form.addRow(
            t("widget.launcher.interaction.sound_event", "재생 시점"), self._sound_event_combo
        )
        self._sound_path_button = QPushButton(
            t("widget.launcher.interaction.choose_sound", "WAV 파일 선택..."), tab
        )
        self._sound_path_button.clicked.connect(self._choose_sound)
        form.addRow(
            t("widget.launcher.interaction.sound_file", "사용자 사운드"), self._sound_path_button
        )
        volume_host = QWidget(tab)
        volume_row = QHBoxLayout(volume_host)
        volume_row.setContentsMargins(0, 0, 0, 0)
        self._volume_slider = QSlider(Qt.Orientation.Horizontal, volume_host)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.valueChanged.connect(self._controls_changed)
        self._volume_value = QLabel("", volume_host)
        self._volume_value.setMinimumWidth(42)
        volume_row.addWidget(self._volume_slider, 1)
        volume_row.addWidget(self._volume_value)
        form.addRow(t("widget.launcher.interaction.volume", "음량"), volume_host)
        return tab

    def _load_draft_into_controls(self) -> None:
        self._syncing = True
        self._enabled_check.setChecked(bool(self._draft["enabled"]))
        for combo, field in (
            (self._mode_combo, "interaction_mode"),
            (self._trigger_combo, "activation_trigger"),
            (self._press_effect_combo, "press_effect"),
            (self._hover_effect_combo, "hover_effect"),
            (self._active_effect_combo, "active_effect"),
            (self._success_effect_combo, "success_effect"),
            (self._error_effect_combo, "error_effect"),
            (self._asset_playback_combo, "asset_playback"),
            (self._sound_combo, "sound_profile"),
            (self._sound_event_combo, "sound_event"),
        ):
            combo.setCurrentIndex(max(0, combo.findData(self._draft[field])))
        self._long_press_spin.setValue(int(self._draft["long_press_ms"]))
        self._indicator_check.setChecked(bool(self._draft["show_status_indicator"]))
        self._animation_speed_spin.setValue(int(self._draft["animation_speed"]))
        self._feedback_duration_spin.setValue(int(self._draft["feedback_duration_ms"]))
        self._reduce_motion_check.setChecked(bool(self._draft["reduce_motion"]))
        self._volume_slider.setValue(int(self._draft["sound_volume"]))
        self._syncing = False
        self._update_state_color_buttons()
        self._update_media_controls()
        self._refresh_preview("active" if self._draft.get("active") else "ready")

    def _controls_changed(self) -> None:
        if self._syncing:
            return
        self._draft["enabled"] = self._enabled_check.isChecked()
        self._draft["interaction_mode"] = str(self._mode_combo.currentData())
        self._draft["activation_trigger"] = str(self._trigger_combo.currentData())
        self._draft["long_press_ms"] = self._long_press_spin.value()
        self._draft["show_status_indicator"] = self._indicator_check.isChecked()
        self._draft["press_effect"] = str(self._press_effect_combo.currentData())
        self._draft["hover_effect"] = str(self._hover_effect_combo.currentData())
        self._draft["active_effect"] = str(self._active_effect_combo.currentData())
        self._draft["success_effect"] = str(self._success_effect_combo.currentData())
        self._draft["error_effect"] = str(self._error_effect_combo.currentData())
        self._draft["animation_speed"] = self._animation_speed_spin.value()
        self._draft["feedback_duration_ms"] = self._feedback_duration_spin.value()
        self._draft["reduce_motion"] = self._reduce_motion_check.isChecked()
        self._draft["asset_playback"] = str(self._asset_playback_combo.currentData())
        self._draft["sound_profile"] = str(self._sound_combo.currentData())
        self._draft["sound_event"] = str(self._sound_event_combo.currentData())
        self._draft["sound_volume"] = self._volume_slider.value()
        self._long_press_spin.setEnabled(self._draft["activation_trigger"] == "long")
        self._update_media_controls()
        self._refresh_preview("active" if self._draft.get("active") else "ready")

    def _apply_preset(self) -> None:
        clear_keycap_interaction(self._draft)
        self._draft.update(deepcopy(self._PRESETS[str(self._preset_combo.currentData())]))
        self._load_draft_into_controls()

    def _simulate(self, state: str) -> None:
        self._refresh_preview(state)

    def _refresh_preview(self, state: str) -> None:
        preview_data = deepcopy(self._draft)
        preview_data["enabled"] = state != "disabled"
        preview_data["active"] = state == "active"
        self._preview.key_data = preview_data
        self._preview._feedback = state if state in {"success", "error", "running"} else ""
        self._preview.setCursor(Qt.CursorShape.ArrowCursor)
        self._preview.setAccessibleDescription(self._preview._accessible_state_description())
        self._preview._sync_animation_state()
        self._preview.update()
        state_labels = {
            "ready": t("widget.launcher.state.ready", "대기"),
            "active": t("widget.launcher.state.active", "활성"),
            "success": t("widget.launcher.state.success", "성공"),
            "error": t("widget.launcher.state.error", "실패"),
            "disabled": t("widget.launcher.state.disabled", "비활성"),
        }
        self._preview_state.setText(state_labels.get(state, state))

    def _choose_state_color(self, field: str) -> None:
        initial = _css_color(self._draft.get(field), INTERACTION_DEFAULTS[field])
        color = QColorDialog.getColor(
            initial,
            self,
            t("widget.launcher.designer.choose_color", "색상 선택"),
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if color.isValid():
            self._draft[field] = _rgba_hex(color)
            self._update_state_color_buttons()
            self._refresh_preview("active" if "active" in field else "disabled")

    def _update_state_color_buttons(self) -> None:
        for field, button in self._state_color_buttons.items():
            color = _css_color(self._draft.get(field), INTERACTION_DEFAULTS[field])
            text_color = "#111111" if color.lightness() > 160 else "#ffffff"
            button.setText(_rgba_hex(color).upper())
            button.setStyleSheet(
                f"background: {color.name()}; color: {text_color}; "
                "border: 1px solid rgba(127,145,168,96); font-weight: 650;"
            )

    def _choose_sound(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            t("widget.launcher.interaction.choose_sound", "피드백 사운드 선택"),
            "",
            t("widget.launcher.interaction.sound_filter", "WAV 오디오 (*.wav)"),
        )
        if path:
            imported = import_launcher_asset(path, "sound")
            if not imported:
                QMessageBox.warning(
                    self,
                    t("widget.launcher.asset_import_failed_title", "사운드를 가져올 수 없음"),
                    t(
                        "widget.launcher.asset_import_failed",
                        "지원 형식과 25MB 이하의 파일인지 확인해 주세요.",
                    ),
                )
                return
            self._draft["sound_path"] = imported
            self._sound_combo.setCurrentIndex(self._sound_combo.findData("custom"))
            self._controls_changed()

    def _preview_sound(self) -> None:
        self._controls_changed()
        preview_data = deepcopy(self._draft)
        self._preview.key_data = preview_data
        configured_event = str(preview_data.get("sound_event", "press"))
        event_name = "success" if configured_event == "result" else configured_event
        event_name = "press" if event_name == "all" else event_name
        self._preview._play_sound(event_name)

    def _update_media_controls(self) -> None:
        is_custom = str(self._sound_combo.currentData()) == "custom"
        self._sound_path_button.setEnabled(is_custom)
        path = str(self._draft.get("sound_path", "") or "")
        self._sound_path_button.setText(
            path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            if path
            else t("widget.launcher.interaction.choose_sound", "WAV 파일 선택...")
        )
        self._volume_slider.setEnabled(str(self._sound_combo.currentData()) != "none")
        self._sound_preview_button.setEnabled(str(self._sound_combo.currentData()) != "none")
        self._volume_value.setText(f"{self._volume_slider.value()}%")


class LauncherDeckEditorDialog(QDialog):
    """Draft-based editor. Settings are untouched until the user accepts."""

    def __init__(self, deck: dict, parent=None):
        super().__init__(parent)
        self._deck = normalize_deck(deepcopy(deck))
        self._selected_ids: set[str] = set()
        self._canvas_buttons: dict[str, _EditorKeyButton] = {}
        self._syncing = False
        apply_dialog_title(self, t("widget.launcher.editor_title", "런처 덱 편집"))
        apply_common_dialog_style(self, minimum_width=980, size=(1120, 720))
        self._build_ui()
        self._rebuild_canvas()

    def result_deck(self) -> dict:
        return normalize_deck(deepcopy(self._deck))

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(12)

        title = QLabel(t("widget.launcher.editor_heading", "키캡 배열과 실행 동작"), self)
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        root.addWidget(title)
        description = QLabel(
            t(
                "widget.launcher.editor_desc",
                "템플릿을 고른 뒤 여러 키를 선택해 크기와 스타일을 한 번에 바꿀 수 있습니다.",
            ),
            self,
        )
        description.setWordWrap(True)
        root.addWidget(description)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self._build_template_panel())
        splitter.addWidget(self._build_canvas_panel())
        splitter.addWidget(self._build_property_panel())
        splitter.setSizes([210, 560, 300])
        root.addWidget(splitter, 1)

        footer, apply_button, cancel_button = build_dialog_footer(
            ok_label=t("common.apply", "적용"),
            cancel_label=t("common.cancel", "취소"),
        )
        apply_button.clicked.connect(self.accept)
        if cancel_button is not None:
            cancel_button.clicked.connect(self.reject)
        root.addLayout(footer)

    def _build_template_panel(self) -> QWidget:
        panel = QGroupBox(t("widget.launcher.templates", "배열 템플릿"), self)
        layout = QVBoxLayout(panel)
        self._template_list = QListWidget(panel)
        self._template_list.setIconSize(QSize(148, 74))
        self._template_list.setSpacing(5)
        for template_id, key, fallback, _factory in DECK_TEMPLATES:
            item = QListWidgetItem(deck_template_icon(template_deck(template_id)), t(key, fallback))
            item.setData(Qt.ItemDataRole.UserRole, template_id)
            item.setSizeHint(QSize(172, 96))
            self._template_list.addItem(item)
        layout.addWidget(self._template_list, 1)
        apply_button = QPushButton(t("widget.launcher.apply_template", "이 배열 적용"), panel)
        apply_button.setObjectName("primary_btn")
        apply_button.clicked.connect(self._apply_selected_template)
        layout.addWidget(apply_button)
        return panel

    def _build_canvas_panel(self) -> QWidget:
        panel = QGroupBox(t("widget.launcher.canvas", "키캡 캔버스"), self)
        layout = QVBoxLayout(panel)
        toolbar = QGridLayout()
        add_button = QPushButton(t("widget.launcher.add_key", "+ 키 추가"), panel)
        delete_button = QPushButton(t("widget.launcher.delete_selected", "선택 삭제"), panel)
        select_all_button = QPushButton(t("widget.launcher.select_all", "전체 선택"), panel)
        add_button.clicked.connect(self._add_key)
        delete_button.clicked.connect(self._delete_selected)
        select_all_button.clicked.connect(self._select_all)
        toolbar.addWidget(add_button, 0, 0)
        toolbar.addWidget(delete_button, 0, 1)
        toolbar.addWidget(select_all_button, 1, 0)
        columns_row = QHBoxLayout()
        columns_row.addWidget(QLabel(t("widget.launcher.columns", "열"), panel))
        self._columns_spin = QSpinBox(panel)
        self._columns_spin.setRange(2, 12)
        self._columns_spin.setValue(int(self._deck["columns"]))
        self._columns_spin.valueChanged.connect(self._set_columns)
        columns_row.addWidget(self._columns_spin)
        toolbar.addLayout(columns_row, 1, 1)
        layout.addLayout(toolbar)

        visual_group = QGroupBox(t("widget.launcher.visual_system", "비주얼 시스템"), panel)
        visual_grid = QGridLayout(visual_group)
        visual_grid.addWidget(QLabel(t("widget.launcher.icon_pack_label", "아이콘 팩")), 0, 0)
        self._icon_pack_combo = QComboBox(visual_group)
        for pack in KEYCAP_ICON_PACKS:
            self._icon_pack_combo.addItem(t(pack.label_key, pack.label_default), pack.pack_id)
        self._icon_pack_combo.setMinimumWidth(142)
        self._icon_pack_combo.setCurrentIndex(
            max(0, self._icon_pack_combo.findData(self._deck.get("icon_pack")))
        )
        self._icon_pack_combo.currentIndexChanged.connect(self._visual_settings_changed)
        visual_grid.addWidget(self._icon_pack_combo, 0, 1)
        self._mosaic_check = QCheckBox(
            t("widget.launcher.mosaic_mode", "한 장 이미지를 키 전체에 나눠 표시"), visual_group
        )
        self._mosaic_check.setChecked(bool(self._deck.get("mosaic_enabled", False)))
        self._mosaic_check.toggled.connect(self._visual_settings_changed)
        visual_grid.addWidget(self._mosaic_check, 1, 0, 1, 2)
        self._mosaic_button = QPushButton(visual_group)
        self._mosaic_button.clicked.connect(self._choose_mosaic_asset)
        visual_grid.addWidget(self._mosaic_button, 2, 0, 1, 2)
        visual_grid.addWidget(QLabel(t("widget.launcher.mosaic_opacity", "이미지 농도")), 3, 0)
        self._mosaic_opacity_spin = QSpinBox(visual_group)
        self._mosaic_opacity_spin.setRange(10, 100)
        self._mosaic_opacity_spin.setSuffix(" %")
        self._mosaic_opacity_spin.setValue(int(self._deck.get("mosaic_opacity", 92)))
        self._mosaic_opacity_spin.valueChanged.connect(self._visual_settings_changed)
        visual_grid.addWidget(self._mosaic_opacity_spin, 3, 1)
        self._mosaic_labels_check = QCheckBox(
            t("widget.launcher.mosaic_show_labels", "모자이크 위에 아이콘과 이름 표시"),
            visual_group,
        )
        self._mosaic_labels_check.setChecked(bool(self._deck.get("mosaic_show_labels", True)))
        self._mosaic_labels_check.toggled.connect(self._visual_settings_changed)
        visual_grid.addWidget(self._mosaic_labels_check, 4, 0, 1, 2)
        layout.addWidget(visual_group)
        self._update_mosaic_button()

        self._canvas = QFrame(panel)
        self._canvas.setObjectName("launcherDeckEditorCanvas")
        self._canvas.setStyleSheet(
            "QFrame#launcherDeckEditorCanvas { background: rgba(20,27,40,150); "
            "border: 1px solid rgba(130,155,190,70); border-radius: 14px; }"
        )
        self._canvas_layout = QGridLayout(self._canvas)
        self._canvas_layout.setContentsMargins(14, 14, 14, 14)
        self._canvas_layout.setSpacing(int(self._deck["gap"]))
        layout.addWidget(self._canvas, 1)
        self._selection_label = QLabel("", panel)
        layout.addWidget(self._selection_label)
        return panel

    def _build_property_panel(self) -> QWidget:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(320)
        panel = QWidget(scroll)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 0, 0, 0)

        batch_group = QGroupBox(t("widget.launcher.batch_style", "선택 키 일괄 꾸미기"), panel)
        batch = QVBoxLayout(batch_group)
        self._style_combo = QComboBox(batch_group)
        for style in KEYCAP_STYLES:
            self._style_combo.addItem(t(style.label_key, style.label_default), style.style_id)
        self._style_combo.activated.connect(self._apply_style)
        batch.addWidget(self._style_combo)
        self._size_combo = QComboBox(batch_group)
        for label, value in (
            ("1U", (1, 1)),
            ("2U", (2, 1)),
            ("3U", (3, 1)),
            (t("widget.launcher.vertical_key", "세로 1×2"), (1, 2)),
        ):
            self._size_combo.addItem(label, value)
        self._size_combo.activated.connect(self._apply_size)
        batch.addWidget(self._size_combo)
        self._pattern_combo = QComboBox(batch_group)
        for pattern_id, key, fallback in PATTERNS:
            self._pattern_combo.addItem(t(key, fallback), pattern_id)
        batch.addWidget(self._pattern_combo)
        pattern_button = QPushButton(t("widget.launcher.apply_pattern", "조합 적용"), batch_group)
        pattern_button.clicked.connect(self._apply_pattern)
        batch.addWidget(pattern_button)
        self._customize_button = QPushButton(
            t("widget.launcher.designer.open", "상세 꾸미기..."), batch_group
        )
        self._customize_button.setObjectName("primary_btn")
        self._customize_button.clicked.connect(self._customize_selected)
        batch.addWidget(self._customize_button)
        self._interaction_button = QPushButton(
            t("widget.launcher.interaction.open", "효과 및 피드백..."), batch_group
        )
        self._interaction_button.setObjectName("primary_btn")
        self._interaction_button.clicked.connect(self._customize_interaction_selected)
        batch.addWidget(self._interaction_button)
        self._clear_custom_button = QPushButton(
            t("widget.launcher.designer.clear", "사용자 디자인 지우기"), batch_group
        )
        self._clear_custom_button.clicked.connect(self._clear_customization)
        batch.addWidget(self._clear_custom_button)
        self._clear_interaction_button = QPushButton(
            t("widget.launcher.interaction.clear", "피드백 설정 초기화"), batch_group
        )
        self._clear_interaction_button.clicked.connect(self._clear_interaction)
        batch.addWidget(self._clear_interaction_button)
        layout.addWidget(batch_group)

        action_group = QGroupBox(t("widget.launcher.key_action", "키 동작"), panel)
        action_layout = QVBoxLayout(action_group)
        self._enabled_check = QCheckBox(
            t("widget.launcher.interaction.enabled", "이 키 사용"), action_group
        )
        self._enabled_check.toggled.connect(self._commit_key_fields)
        action_layout.addWidget(self._enabled_check)
        self._label_edit = QLineEdit(action_group)
        self._label_edit.setPlaceholderText(t("widget.launcher.key_name", "키 이름"))
        self._label_edit.editingFinished.connect(self._commit_key_fields)
        action_layout.addWidget(self._label_edit)
        self._action_combo = QComboBox(action_group)
        for action_id, key, fallback in ACTION_TYPES:
            self._action_combo.addItem(t(key, fallback), action_id)
        self._action_combo.currentIndexChanged.connect(self._action_type_changed)
        action_layout.addWidget(self._action_combo)
        self._internal_combo = QComboBox(action_group)
        for command_id, key, fallback in INTERNAL_ACTIONS:
            self._internal_combo.addItem(t(key, fallback), command_id)
        self._internal_combo.currentIndexChanged.connect(self._commit_key_fields)
        action_layout.addWidget(self._internal_combo)
        target_row = QHBoxLayout()
        self._target_edit = QLineEdit(action_group)
        self._target_edit.setPlaceholderText(
            t("widget.launcher.target_placeholder", "프로그램·파일 경로 또는 https:// 주소")
        )
        self._target_edit.editingFinished.connect(self._commit_key_fields)
        target_row.addWidget(self._target_edit, 1)
        self._browse_button = QPushButton(t("widget.launcher.browse", "찾기"), action_group)
        self._browse_button.clicked.connect(self._browse_target)
        target_row.addWidget(self._browse_button)
        action_layout.addLayout(target_row)
        self._hotkey_edit = QKeySequenceEdit(action_group)
        self._hotkey_edit.setClearButtonEnabled(True)
        self._hotkey_edit.editingFinished.connect(self._commit_key_fields)
        action_layout.addWidget(self._hotkey_edit)
        layout.addWidget(action_group)
        layout.addStretch()
        hint = QLabel(
            t(
                "widget.launcher.multi_select_hint",
                "키를 차례로 클릭하면 여러 개가 함께 선택됩니다. 선택 키에는 크기·스타일·조합이 일괄 적용됩니다.",
            ),
            panel,
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        scroll.setWidget(panel)
        return scroll

    def _key_by_id(self, key_id: str) -> dict | None:
        return next((key for key in self._deck["keys"] if key["id"] == key_id), None)

    def _rebuild_canvas(self) -> None:
        while self._canvas_layout.count():
            item = self._canvas_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._canvas_buttons.clear()
        self._canvas_layout.setSpacing(int(self._deck["gap"]))
        mosaic_source = QPixmap()
        if bool(self._deck.get("mosaic_enabled", False)):
            mosaic_source = QPixmap(str(self._deck.get("mosaic_path", "") or ""))
        for column in range(int(self._deck["columns"])):
            self._canvas_layout.setColumnStretch(column, 1)
        for key in self._deck["keys"]:
            button = _EditorKeyButton(key, self._selection_changed, self._swap_keys, self._canvas)
            button.setChecked(key["id"] in self._selected_ids)
            style = keycap_style(key["style"])
            top = str(key.get("custom_top") or style.top)[:7]
            text_color = str(key.get("custom_text") or style.text)[:7]
            border = str(key.get("custom_border") or style.border)[:7]
            if not bool(key.get("enabled", True)):
                top = str(key.get("disabled_top") or "#596273")[:7]
                text_color = str(key.get("disabled_text") or "#aeb7c6")[:7]
            radius_override = int(key.get("radius_override", -1))
            radius = radius_override if radius_override >= 0 else style.radius
            pack = keycap_icon_pack(self._deck.get("icon_pack"))
            icon_asset = keycap_icon_asset(key.get("icon"))
            if not mosaic_source.isNull():
                mosaic_key = crop_mosaic_pixmap(mosaic_source, self._deck, key)
                button.setIcon(QIcon(mosaic_key))
                button.setIconSize(QSize(64, 46))
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                if not bool(self._deck.get("mosaic_show_labels", True)):
                    button.setText("")
            elif icon_asset.icon_key:
                button.setIcon(_ic(icon_asset.icon_key, color=pack.color[:7]))
                button.setIconSize(QSize(28, 28))
            if key.get("asset_id") not in (None, "", "none") or key.get("asset_path"):
                button.setText(f"{key['label']}  ✦")
            state_marker = ""
            if not bool(key.get("enabled", True)):
                state_marker = "  ◌"
            elif str(key.get("interaction_mode", "action")) == "toggle":
                state_marker = "  ●" if bool(key.get("active", False)) else "  ○"
            if state_marker:
                button.setText(f"{button.text()}{state_marker}")
            button.setStyleSheet(
                f"QToolButton {{ background: {top}; color: {text_color}; "
                f"border: 1px solid {border}; border-radius: {radius}px; "
                "padding: 7px; font-weight: 600; } "
                "QToolButton:checked { border: 3px solid #4da3ff; }"
            )
            self._canvas_layout.addWidget(
                button,
                int(key["row"]),
                int(key["column"]),
                int(key["height"]),
                int(key["width"]),
            )
            self._canvas_buttons[key["id"]] = button
        self._sync_selection_controls()

    def _selection_changed(self, key_id: str, selected: bool) -> None:
        if selected:
            self._selected_ids.add(key_id)
        else:
            self._selected_ids.discard(key_id)
        self._sync_selection_controls()

    def _sync_selection_controls(self) -> None:
        count = len(self._selected_ids)
        self._selection_label.setText(
            t("widget.launcher.selected_count", "{count}개 키 선택", count=count)
        )
        key = self._key_by_id(next(iter(self._selected_ids))) if count == 1 else None
        self._syncing = True
        self._customize_button.setEnabled(count > 0)
        self._interaction_button.setEnabled(count > 0)
        self._clear_custom_button.setEnabled(count > 0)
        self._clear_interaction_button.setEnabled(count > 0)
        for widget in (
            self._enabled_check,
            self._label_edit,
            self._action_combo,
            self._internal_combo,
            self._target_edit,
            self._hotkey_edit,
        ):
            widget.setEnabled(key is not None)
        if key is not None:
            self._enabled_check.setChecked(bool(key.get("enabled", True)))
            self._label_edit.setText(key["label"])
            self._action_combo.setCurrentIndex(
                max(0, self._action_combo.findData(key["action_type"]))
            )
            self._internal_combo.setCurrentIndex(
                max(0, self._internal_combo.findData(key["target"]))
            )
            self._target_edit.setText(key["target"] if key["action_type"] != "internal" else "")
            self._hotkey_edit.setKeySequence(
                QKeySequence.fromString(
                    key["target"] if key["action_type"] == "hotkey" else "",
                    QKeySequence.SequenceFormat.PortableText,
                )
            )
            self._refresh_action_fields(key["action_type"])
        else:
            self._enabled_check.setChecked(False)
            self._label_edit.clear()
            self._target_edit.clear()
            self._hotkey_edit.clear()
        self._syncing = False

    def _refresh_action_fields(self, action_type: str) -> None:
        is_internal = action_type == "internal"
        is_hotkey = action_type == "hotkey"
        self._internal_combo.setVisible(is_internal)
        self._target_edit.setVisible(not is_internal and not is_hotkey)
        self._browse_button.setVisible(action_type == "open")
        self._hotkey_edit.setVisible(is_hotkey)

    def _action_type_changed(self) -> None:
        if self._syncing:
            return
        self._refresh_action_fields(str(self._action_combo.currentData()))
        self._commit_key_fields()

    def _commit_key_fields(self) -> None:
        if self._syncing or len(self._selected_ids) != 1:
            return
        key = self._key_by_id(next(iter(self._selected_ids)))
        if key is None:
            return
        key["label"] = self._label_edit.text().strip() or t("widget.launcher.unnamed_key", "새 키")
        key["enabled"] = self._enabled_check.isChecked()
        key["action_type"] = str(self._action_combo.currentData())
        if key["action_type"] == "internal":
            key["target"] = str(self._internal_combo.currentData())
        elif key["action_type"] == "hotkey":
            key["target"] = self._hotkey_edit.keySequence().toString(
                QKeySequence.SequenceFormat.PortableText
            )
        else:
            key["target"] = self._target_edit.text().strip()
        self._rebuild_canvas()

    def _browse_target(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            t("widget.launcher.choose_target", "프로그램 또는 파일 선택"),
            "",
            t(
                "widget.launcher.target_filter",
                "프로그램 및 바로가기 (*.exe *.lnk);;모든 파일 (*.*)",
            ),
        )
        if path:
            self._target_edit.setText(path)
            self._commit_key_fields()

    def _apply_selected_template(self) -> None:
        item = self._template_list.currentItem()
        if item is None:
            return
        self._deck = preserve_deck_visuals(
            self._deck,
            template_deck(item.data(Qt.ItemDataRole.UserRole)),
        )
        self._selected_ids.clear()
        self._columns_spin.blockSignals(True)
        self._columns_spin.setValue(int(self._deck["columns"]))
        self._columns_spin.blockSignals(False)
        self._sync_visual_controls()
        self._rebuild_canvas()

    def _sync_visual_controls(self) -> None:
        self._syncing = True
        self._icon_pack_combo.setCurrentIndex(
            max(0, self._icon_pack_combo.findData(self._deck.get("icon_pack")))
        )
        self._mosaic_check.setChecked(bool(self._deck.get("mosaic_enabled", False)))
        self._mosaic_opacity_spin.setValue(int(self._deck.get("mosaic_opacity", 92)))
        self._mosaic_labels_check.setChecked(bool(self._deck.get("mosaic_show_labels", True)))
        self._syncing = False
        self._update_mosaic_button()

    def _visual_settings_changed(self) -> None:
        if self._syncing:
            return
        self._deck["icon_pack"] = str(self._icon_pack_combo.currentData())
        self._deck["mosaic_enabled"] = self._mosaic_check.isChecked()
        self._deck["mosaic_opacity"] = self._mosaic_opacity_spin.value()
        self._deck["mosaic_show_labels"] = self._mosaic_labels_check.isChecked()
        self._rebuild_canvas()

    def _choose_mosaic_asset(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            t("widget.launcher.choose_mosaic", "덱 전체에 나눠 표시할 이미지 선택"),
            "",
            t(
                "widget.launcher.image_filter",
                "이미지 (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.svg)",
            ),
        )
        if not path:
            return
        imported = import_launcher_asset(path, "image")
        if not imported:
            QMessageBox.warning(
                self,
                t("widget.launcher.asset_import_failed_title", "에셋을 가져올 수 없음"),
                t(
                    "widget.launcher.asset_import_failed",
                    "지원 형식과 25MB 제한을 확인해 주세요.",
                ),
            )
            return
        self._deck["mosaic_path"] = imported
        self._deck["mosaic_enabled"] = True
        self._mosaic_check.blockSignals(True)
        self._mosaic_check.setChecked(True)
        self._mosaic_check.blockSignals(False)
        self._update_mosaic_button()
        self._rebuild_canvas()

    def _update_mosaic_button(self) -> None:
        path = str(self._deck.get("mosaic_path", "") or "")
        self._mosaic_button.setText(
            t("widget.launcher.replace_mosaic", "전체 이미지 바꾸기...")
            if path
            else t("widget.launcher.choose_mosaic", "전체 이미지 불러오기...")
        )

    def _apply_style(self) -> None:
        if self._syncing or not self._selected_ids:
            return
        style_id = str(self._style_combo.currentData())
        for key in self._deck["keys"]:
            if key["id"] in self._selected_ids:
                key["style"] = style_id
                clear_keycap_overrides(key)
        self._rebuild_canvas()

    def _apply_size(self) -> None:
        if self._syncing or not self._selected_ids:
            return
        width, height = self._size_combo.currentData()
        for key in self._deck["keys"]:
            if key["id"] in self._selected_ids:
                key["width"], key["height"] = int(width), int(height)
        self._deck = reflow_deck(self._deck)
        self._rebuild_canvas()

    def _apply_pattern(self) -> None:
        selected = self._selected_ids or {key["id"] for key in self._deck["keys"]}
        for key in self._deck["keys"]:
            if key["id"] in selected:
                clear_keycap_overrides(key)
        self._deck = apply_pattern(self._deck, str(self._pattern_combo.currentData()), selected)
        self._rebuild_canvas()

    def _customize_selected(self) -> None:
        if not self._selected_ids:
            return
        sample = next((key for key in self._deck["keys"] if key["id"] in self._selected_ids), None)
        if sample is None:
            return
        dialog = KeycapAppearanceDialog(sample, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        appearance = dialog.result_appearance()
        for key in self._deck["keys"]:
            if key["id"] in self._selected_ids:
                key.update(deepcopy(appearance))
        self._deck = normalize_deck(self._deck)
        self._rebuild_canvas()

    def _clear_customization(self) -> None:
        if not self._selected_ids:
            return
        for key in self._deck["keys"]:
            if key["id"] in self._selected_ids:
                clear_keycap_overrides(key)
        self._rebuild_canvas()

    def _customize_interaction_selected(self) -> None:
        if not self._selected_ids:
            return
        sample = next((key for key in self._deck["keys"] if key["id"] in self._selected_ids), None)
        if sample is None:
            return
        dialog = KeycapInteractionDialog(sample, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        interaction = dialog.result_interaction()
        for key in self._deck["keys"]:
            if key["id"] in self._selected_ids:
                key.update(deepcopy(interaction))
        self._deck = normalize_deck(self._deck)
        self._rebuild_canvas()

    def _clear_interaction(self) -> None:
        if not self._selected_ids:
            return
        for key in self._deck["keys"]:
            if key["id"] in self._selected_ids:
                clear_keycap_interaction(key)
        self._rebuild_canvas()

    def _set_columns(self, columns: int) -> None:
        self._deck["columns"] = int(columns)
        self._deck = reflow_deck(self._deck)
        self._rebuild_canvas()

    def _add_key(self) -> None:
        self._deck["keys"].append(
            new_key(
                t("widget.launcher.unnamed_key", "새 키"),
                int(self._deck["rows"]),
                0,
                action_type="open",
                target="",
            )
        )
        self._deck = reflow_deck(self._deck)
        self._selected_ids = {self._deck["keys"][-1]["id"]}
        self._rebuild_canvas()

    def _delete_selected(self) -> None:
        if not self._selected_ids:
            return
        self._deck["keys"] = [
            key for key in self._deck["keys"] if key["id"] not in self._selected_ids
        ]
        self._selected_ids.clear()
        self._deck = reflow_deck(self._deck)
        self._rebuild_canvas()

    def _select_all(self) -> None:
        self._selected_ids = {key["id"] for key in self._deck["keys"]}
        self._rebuild_canvas()

    def _swap_keys(self, source_id: str, target_id: str) -> None:
        source, target = self._key_by_id(source_id), self._key_by_id(target_id)
        if source is None or target is None:
            return
        source["row"], target["row"] = target["row"], source["row"]
        source["column"], target["column"] = target["column"], source["column"]
        self._deck = reflow_deck(self._deck)
        self._selected_ids = {source_id}
        self._rebuild_canvas()


__all__ = [
    "KeycapAppearanceDialog",
    "KeycapInteractionDialog",
    "LauncherDeckEditorDialog",
    "deck_template_icon",
]
