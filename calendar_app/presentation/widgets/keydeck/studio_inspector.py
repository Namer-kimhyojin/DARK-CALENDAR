# -*- coding: utf-8 -*-
"""KeyDeck Studio inspector panels and their building-block controls."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QIcon,
    QImage,
    QImageReader,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QCompleter,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.keydeck.model import (
    ACTION_TYPES,
    CASE_STYLES,
    COMMANDS,
    INSERT_FITS,
    INSERT_KINDS,
    KEY_MODES,
    LED_MODES,
    LEGEND_LAYOUTS,
    LEGEND_WEIGHTS,
    MATERIALS,
    PAGE_TARGETS,
    PANORAMA_FITS,
    PANORAMA_ZOOM_RANGE,
    PLAYBACK_MODES,
    PROFILES,
    SOUND_CHOICES,
    SWITCHES,
    TOGGLE_INDICATORS,
    default_deck,
    normalize_action,
    panorama_align_for,
    panorama_keys,
    panorama_rect,
)
from calendar_app.presentation.widgets.keydeck.physics import switch_profile
from calendar_app.presentation.widgets.keydeck.renderer import (
    DeckGeometry,
    KeyDeckRenderer,
    fit_scale,
)
from calendar_app.presentation.widgets.keydeck.resources import (
    IMAGE_SUFFIXES,
    glyph_pixmap,
    is_animated,
    panorama_image,
    pattern_image,
)
from calendar_app.presentation.widgets.launcher_keycap_assets import KEYCAP_ASSETS
from calendar_app.presentation.widgets.launcher_keycap_icons import KEYCAP_ICON_ASSETS

CAP_SWATCHES = (
    "#e8f0ff",
    "#ffffff",
    "#1a1d24",
    "#3b3f46",
    "#efe6d2",
    "#ff7a1a",
    "#7c5cff",
    "#2fbf71",
)
INSERT_SWATCHES = (
    "#233a63",
    "#2c2458",
    "#12454f",
    "#fde2e4",
    "#dff0ea",
    "#fff1e2",
    "#ee0979",
    "#11998e",
)
LEGEND_SWATCHES = (
    "#ffffff",
    "#f5f8ff",
    "#2b2f38",
    "#1d1f23",
    "#ff8a5b",
    "#5ab8ff",
    "#ffd166",
    "#3ddc84",
)
LED_SWATCHES = (
    "#5ab8ff",
    "#ff3df0",
    "#3dd9ff",
    "#ff5f7e",
    "#ffb35c",
    "#ffe45c",
    "#5cf29a",
    "#9b7bff",
)
CASE_SWATCHES = (
    "#171b23",
    "#0b0d12",
    "#2a2d33",
    "#c9ced6",
    "#e7ecf5",
    "#6b4226",
    "#1f3a5f",
    "#3a1f4f",
)
COMMON_HOTKEYS = (
    ("Ctrl+C", "widget.launcher.key.copy", "복사"),
    ("Ctrl+V", "widget.launcher.key.paste", "붙여넣기"),
    ("Ctrl+X", "widget.launcher.key.cut", "잘라내기"),
    ("Ctrl+Z", "widget.launcher.key.undo", "실행 취소"),
    ("Ctrl+Y", "widget.launcher.key.redo", "다시 실행"),
    ("Ctrl+S", "widget.launcher.key.save", "저장"),
    ("Win+Shift+S", "widget.launcher.hotkey.screenshot", "화면 캡처"),
    ("Win+D", "widget.launcher.hotkey.desktop", "바탕화면 보기"),
    ("Alt+Tab", "widget.launcher.hotkey.switch_app", "앱 전환"),
    ("VolumeMute", "widget.launcher.key.mute", "음소거"),
    ("VolumeDown", "widget.launcher.key.volume_down", "볼륨 -"),
    ("VolumeUp", "widget.launcher.key.volume_up", "볼륨 +"),
    ("MediaPlay", "widget.launcher.key.play_pause", "재생"),
    ("MediaNext", "widget.launcher.key.next_track", "다음 곡"),
    ("MediaPrevious", "widget.launcher.hotkey.prev_track", "이전 곡"),
)


def _label(options, option_id: str) -> str:
    for item_id, key, fallback in options:
        if item_id == option_id:
            return str(t(key, fallback))
    return option_id


def _section(text: str, parent=None) -> QLabel:
    label = QLabel(text, parent)
    label.setObjectName("kdSection")
    return label


def _hint(text: str, parent=None) -> QLabel:
    label = QLabel(text, parent)
    label.setObjectName("kdHint")
    label.setWordWrap(True)
    return label


def _form(parent=None) -> QFormLayout:
    form = QFormLayout()
    form.setContentsMargins(0, 2, 0, 6)
    form.setHorizontalSpacing(12)
    form.setVerticalSpacing(8)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    del parent
    return form


def _scroll_page(parent=None) -> tuple[QScrollArea, QVBoxLayout]:
    scroll = QScrollArea(parent)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    host = QWidget(scroll)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(4, 8, 10, 8)
    layout.setSpacing(6)
    scroll.setWidget(host)
    return scroll, layout


def color_chip_icon(color: str, size: int = 16, ring: bool = False) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QColor(0, 0, 0, 90) if not ring else QColor(255, 255, 255, 200))
    painter.setBrush(QColor(color))
    painter.drawEllipse(QRectF(1, 1, size - 2, size - 2))
    painter.end()
    return QIcon(pixmap)


def switch_icon(switch_id: str, size: int = 18) -> QIcon:
    stem = QColor(switch_profile(switch_id).stem_color)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(40, 44, 52))
    painter.drawRoundedRect(QRectF(1, 1, size - 2, size - 2), 4, 4)
    painter.setBrush(stem)
    arm, thick = size * 0.56, size * 0.18
    painter.drawRect(QRectF((size - arm) / 2, (size - thick) / 2, arm, thick))
    painter.drawRect(QRectF((size - thick) / 2, (size - arm) / 2, thick, arm))
    painter.end()
    return QIcon(pixmap)


def ui_icon(name: str, color: str = "#aab4c6", size: int = 18) -> QIcon:
    """Vector UI icon (qtawesome ``mdi6.*`` name) for tabs and option buttons."""
    del size  # QIcon scales the vector glyph to whatever size the widget asks for
    try:
        import qtawesome as qta  # type: ignore[import]

        return qta.icon(name, color=QColor(color))
    except Exception:  # pragma: no cover - qtawesome optional
        return QIcon()


def key_preview_icon(deck: dict, key: dict, size: int, *, header: bool = False) -> QIcon:
    """Render one keycap (on the deck's plate) as an icon."""
    mini = deepcopy(default_deck())
    mini.update(
        {k: deepcopy(deck[k]) for k in ("unit", "gap", "case", "led_brightness", "panorama")}
    )
    sample = deepcopy(key)
    sample.update({"x": 0.0, "y": 0.0})
    mini["pages"][0]["keys"] = [sample]
    renderer = KeyDeckRenderer()
    scale = fit_scale(mini, 0, size, size, header=header)
    renderer.set_deck(mini, 0, scale=scale, header=header)
    rendered = renderer.render_pixmap(dpr=2.0)
    canvas = QPixmap(size * 2, size * 2)
    canvas.setDevicePixelRatio(2.0)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    geometry = renderer.geometry
    painter.drawPixmap(QPointF((size - geometry.width) / 2, (size - geometry.height) / 2), rendered)
    painter.end()
    return QIcon(canvas)


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------


class ColorButton(QPushButton):
    """Swatch button that opens a colour picker."""

    colorChanged = pyqtSignal(str)

    def __init__(self, parent=None, *, allow_alpha: bool = False):
        super().__init__(parent)
        self._color = "#ffffff"
        self._allow_alpha = allow_alpha
        self.setObjectName("kdColorButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(104)
        self.clicked.connect(self._pick)
        self._refresh()

    def color(self) -> str:
        return self._color

    def set_color(self, color: str) -> None:
        self._color = QColor(color).name() if QColor(color).isValid() else "#ffffff"
        self._refresh()

    def _refresh(self) -> None:
        self.setIcon(color_chip_icon(self._color, 16))
        self.setText(self._color.upper())

    def _pick(self) -> None:
        chosen = QColorDialog.getColor(
            QColor(self._color), self, t("widget.launcher.studio.pick_color", "색상 선택")
        )
        if chosen.isValid():
            self.set_color(chosen.name())
            self.colorChanged.emit(self._color)


class SwatchRow(QWidget):
    colorPicked = pyqtSignal(str)

    def __init__(self, colors, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        for color in colors:
            button = QToolButton(self)
            button.setObjectName("kdSwatch")
            button.setIcon(color_chip_icon(color, 18))
            button.setIconSize(QSize(18, 18))
            button.setToolTip(color.upper())
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, c=color: self.colorPicked.emit(c))
            layout.addWidget(button)
        layout.addStretch()


class Segmented(QWidget):
    """Grid of exclusive toggle buttons (segmented control)."""

    changed = pyqtSignal(str)

    def __init__(
        self,
        options,
        parent=None,
        *,
        columns: int = 3,
        icons: dict | None = None,
        text_under_icon: bool = False,
    ):
        super().__init__(parent)
        self._text_under_icon = text_under_icon
        self._buttons: dict[str, QToolButton] = {}
        self._value = ""
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        for index, (option_id, key, fallback) in enumerate(options):
            button = QToolButton(self)
            button.setObjectName("kdSeg")
            button.setCheckable(True)
            button.setText(str(t(key, fallback)))
            button.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextUnderIcon
                if text_under_icon
                else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            )
            # 글자 폭이 인스펙터 폭을 밀어내지 않도록 최소 폭을 두지 않는다 (가로 넘침 방지).
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            button.setMinimumWidth(40)
            if text_under_icon:
                # 공용 QSS의 QToolButton 최대 높이를 풀어 주는 세로형 버튼 (studio QSS 참고)
                button.setProperty("tall", "true")
            button.setToolTip(str(t(key, fallback)))
            if icons and option_id in icons:
                button.setIcon(icons[option_id])
                button.setIconSize(QSize(20, 20))
            button.clicked.connect(lambda _checked=False, oid=option_id: self._clicked(oid))
            grid.addWidget(button, index // columns, index % columns)
            self._buttons[option_id] = button

    def value(self) -> str:
        return self._value

    def set_value(self, option_id: str) -> None:
        self._value = option_id
        for key, button in self._buttons.items():
            button.setChecked(key == option_id)

    def set_icons(self, icons: dict) -> None:
        for key, icon in icons.items():
            if key in self._buttons:
                side = 34 if self._text_under_icon else 26
                self._buttons[key].setIcon(icon)
                self._buttons[key].setIconSize(QSize(side, side))

    def _clicked(self, option_id: str) -> None:
        self.set_value(option_id)
        self.changed.emit(option_id)


class NoWheelSlider(QSlider):
    """Slider that leaves wheel scrolling to the surrounding inspector."""

    def wheelEvent(self, event) -> None:  # noqa: N802
        event.ignore()


class NoWheelComboBox(QComboBox):
    """Combo box that changes only through an explicit selection."""

    def wheelEvent(self, event) -> None:  # noqa: N802
        event.ignore()


class LabeledSlider(QWidget):
    valueChanged = pyqtSignal(int)

    def __init__(self, low: int, high: int, suffix: str = "", parent=None, *, step: int = 1):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.slider = NoWheelSlider(Qt.Orientation.Horizontal, self)
        self.slider.setRange(low, high)
        self.slider.setSingleStep(step)
        self.slider.setPageStep(step * 5)
        self._suffix = suffix
        self._value_label = QLabel(self)
        self._value_label.setObjectName("kdValue")
        self._value_label.setMinimumWidth(46)
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self._value_label)
        self.slider.valueChanged.connect(self._changed)
        self._refresh()

    def value(self) -> int:
        return self.slider.value()

    def set_value(self, value: int) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(int(value))
        self.slider.blockSignals(False)
        self._refresh()

    def _refresh(self) -> None:
        self._value_label.setText(f"{self.slider.value()}{self._suffix}")

    def _changed(self, value: int) -> None:
        self._refresh()
        self.valueChanged.emit(value)


def _searchable(combo: QComboBox, placeholder: str) -> None:
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    combo.lineEdit().setPlaceholderText(placeholder)
    completer = combo.completer()
    if completer is not None:
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)


class GlyphCombo(NoWheelComboBox):
    glyphChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIconSize(QSize(20, 20))
        self.setMaxVisibleItems(14)
        for asset in KEYCAP_ICON_ASSETS:
            pixmap = glyph_pixmap(asset.icon_id, "#7d8aa0", 20, 2.0) if asset.icon_key else None
            self.addItem(
                QIcon(pixmap) if pixmap is not None else QIcon(),
                str(t(asset.label_key, asset.label_default)),
                asset.icon_id,
            )
        _searchable(self, str(t("widget.launcher.studio.search_glyph", "아이콘 검색")))
        self.activated.connect(lambda _index: self.glyphChanged.emit(str(self.currentData())))

    def set_glyph(self, glyph_id: str) -> None:
        index = self.findData(glyph_id)
        self.blockSignals(True)
        self.setCurrentIndex(max(0, index))
        self.blockSignals(False)


class PatternGallery(QListWidget):
    patternChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setIconSize(QSize(40, 40))
        self.setGridSize(QSize(52, 52))
        self.setMovement(QListView.Movement.Static)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setFixedHeight(128)
        self.setObjectName("kdGallery")
        for asset in KEYCAP_ASSETS:
            if not asset.filename:
                continue
            item = QListWidgetItem(self._icon(asset.asset_id), "")
            item.setData(Qt.ItemDataRole.UserRole, asset.asset_id)
            item.setToolTip(str(t(asset.label_key, asset.label_default)))
            self.addItem(item)
        self.itemClicked.connect(
            lambda item: self.patternChanged.emit(str(item.data(Qt.ItemDataRole.UserRole)))
        )

    @staticmethod
    def _icon(pattern_id: str) -> QIcon:
        pixmap = QPixmap(80, 80)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#253450"))
        painter.drawRoundedRect(QRectF(2, 2, 76, 76), 14, 14)
        image = pattern_image(pattern_id, "#dfe9ff", 76)
        if image is not None:
            painter.drawImage(QRectF(2, 2, 76, 76), image)
        painter.end()
        return QIcon(pixmap)

    def set_pattern(self, pattern_id: str) -> None:
        self.blockSignals(True)
        for row in range(self.count()):
            item = self.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == pattern_id:
                self.setCurrentItem(item)
                break
        self.blockSignals(False)


class ActionEditor(QWidget):
    """Edits one action dict (type + target + paste)."""

    changed = pyqtSignal()

    def __init__(self, parent=None, *, browse_callback=None):
        super().__init__(parent)
        self._loading = False
        self._browse_callback = browse_callback
        self._pages: list[dict] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.type_combo = NoWheelComboBox(self)
        type_glyphs = {
            "app": "rocket",
            "url": "globe",
            "hotkey": "keyboard",
            "text": "clipboard",
            "command": "star",
            "page": "layers",
            "none": "close",
        }
        for action_id, key, fallback in ACTION_TYPES:
            pixmap = glyph_pixmap(type_glyphs.get(action_id, "play"), "#7d8aa0", 18, 2.0)
            self.type_combo.addItem(
                QIcon(pixmap) if pixmap else QIcon(), str(t(key, fallback)), action_id
            )
        self.type_combo.currentIndexChanged.connect(self._type_changed)
        layout.addWidget(self.type_combo)
        self.stack = QStackedWidget(self)
        layout.addWidget(self.stack)
        self._pages_by_type: dict[str, int] = {}

        app_page = QWidget(self.stack)
        app_layout = QHBoxLayout(app_page)
        app_layout.setContentsMargins(0, 0, 0, 0)
        self.path_edit = QLineEdit(app_page)
        self.path_edit.setPlaceholderText(
            t("widget.launcher.studio.path_placeholder", "프로그램 · 파일 · 폴더 경로")
        )
        self.path_edit.editingFinished.connect(self._emit)
        file_button = QPushButton(t("widget.launcher.studio.browse_file", "파일…"), app_page)
        folder_button = QPushButton(t("widget.launcher.studio.browse_folder", "폴더…"), app_page)
        file_button.clicked.connect(lambda: self._browse("file"))
        folder_button.clicked.connect(lambda: self._browse("folder"))
        app_layout.addWidget(self.path_edit, 1)
        app_layout.addWidget(file_button)
        app_layout.addWidget(folder_button)
        self._add_page("app", app_page)

        url_page = QWidget(self.stack)
        url_layout = QVBoxLayout(url_page)
        url_layout.setContentsMargins(0, 0, 0, 0)
        self.url_edit = QLineEdit(url_page)
        self.url_edit.setPlaceholderText("https://")
        self.url_edit.editingFinished.connect(self._emit)
        self.url_edit.textChanged.connect(self._validate_url)
        self.url_warning = _hint(
            t("widget.launcher.studio.url_warning", "http:// 또는 https:// 주소만 열 수 있습니다."),
            url_page,
        )
        self.url_warning.setObjectName("kdWarn")
        url_layout.addWidget(self.url_edit)
        url_layout.addWidget(self.url_warning)
        self._add_page("url", url_page)

        hotkey_page = QWidget(self.stack)
        hotkey_layout = QVBoxLayout(hotkey_page)
        hotkey_layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.hotkey_edit = QKeySequenceEdit(hotkey_page)
        self.hotkey_edit.setMaximumSequenceLength(1)
        self.hotkey_edit.editingFinished.connect(self._hotkey_edited)
        clear_button = QPushButton(t("widget.launcher.studio.clear", "지우기"), hotkey_page)
        clear_button.clicked.connect(self._clear_hotkey)
        row.addWidget(self.hotkey_edit, 1)
        row.addWidget(clear_button)
        hotkey_layout.addLayout(row)
        self.common_combo = NoWheelComboBox(hotkey_page)
        self.common_combo.addItem(
            t("widget.launcher.studio.common_hotkeys", "자주 쓰는 키에서 고르기…"), ""
        )
        for sequence, key, fallback in COMMON_HOTKEYS:
            self.common_combo.addItem(f"{t(key, fallback)}  ·  {sequence}", sequence)
        self.common_combo.activated.connect(self._common_picked)
        hotkey_layout.addWidget(self.common_combo)
        self.hotkey_value = QLabel(hotkey_page)
        self.hotkey_value.setObjectName("kdValue")
        hotkey_layout.addWidget(self.hotkey_value)
        hotkey_layout.addWidget(
            _hint(
                t(
                    "widget.launcher.studio.hotkey_note",
                    "덱은 포커스를 가져가지 않으므로 지금 작업 중인 창으로 전송됩니다.",
                ),
                hotkey_page,
            )
        )
        self._hotkey_target = ""
        self._add_page("hotkey", hotkey_page)

        text_page = QWidget(self.stack)
        text_layout = QVBoxLayout(text_page)
        text_layout.setContentsMargins(0, 0, 0, 0)
        self.text_edit = QPlainTextEdit(text_page)
        self.text_edit.setPlaceholderText(
            t(
                "widget.launcher.studio.text_placeholder",
                "복사할 텍스트 (서명, 주소, 자주 쓰는 문구…)",
            )
        )
        self.text_edit.setFixedHeight(84)
        self._text_timer = QTimer(self)
        self._text_timer.setSingleShot(True)
        self._text_timer.setInterval(350)
        self._text_timer.timeout.connect(self._emit)
        self.text_edit.textChanged.connect(
            lambda: None if self._loading else self._text_timer.start()
        )
        self.paste_check = QCheckBox(
            t("widget.launcher.studio.paste_after_copy", "복사한 뒤 바로 붙여넣기 (Ctrl+V)"),
            text_page,
        )
        self.paste_check.toggled.connect(self._emit)
        text_layout.addWidget(self.text_edit)
        text_layout.addWidget(self.paste_check)
        self._add_page("text", text_page)

        self.command_combo = NoWheelComboBox(self.stack)
        for command_id, key, fallback in COMMANDS:
            self.command_combo.addItem(str(t(key, fallback)), command_id)
        self.command_combo.currentIndexChanged.connect(self._emit)
        self._add_page("command", self.command_combo)

        self.page_combo = NoWheelComboBox(self.stack)
        self.page_combo.currentIndexChanged.connect(self._emit)
        self._add_page("page", self.page_combo)

        self._add_page(
            "none",
            _hint(
                t(
                    "widget.launcher.studio.none_hint",
                    "누르면 소리와 움직임만 있고 동작은 실행되지 않습니다.",
                ),
                self.stack,
            ),
        )

    def _add_page(self, action_type: str, widget: QWidget) -> None:
        self._pages_by_type[action_type] = self.stack.addWidget(widget)

    def set_pages(self, pages: list[dict]) -> None:
        self._pages = pages

    def _fill_page_combo(self, current: str) -> None:
        self.page_combo.blockSignals(True)
        self.page_combo.clear()
        for target_id, key, fallback in PAGE_TARGETS:
            self.page_combo.addItem(str(t(key, fallback)), target_id)
        for page in self._pages:
            self.page_combo.addItem(page["name"], page["id"])
        self.page_combo.setCurrentIndex(max(0, self.page_combo.findData(current)))
        self.page_combo.blockSignals(False)

    def set_action(self, action: dict) -> None:
        self._loading = True
        kind = action.get("type", "none")
        target = str(action.get("target", ""))
        self.type_combo.setCurrentIndex(max(0, self.type_combo.findData(kind)))
        self._show_page(kind)
        self._set_text(self.path_edit, target if kind == "app" else "")
        self._set_text(self.url_edit, target if kind == "url" else "")
        self._hotkey_target = target if kind == "hotkey" else ""
        self.hotkey_edit.setKeySequence(
            QKeySequence.fromString(self._hotkey_target, QKeySequence.SequenceFormat.PortableText)
        )
        self._refresh_hotkey_label()
        snippet = target if kind == "text" else ""
        if self.text_edit.toPlainText() != snippet:
            self.text_edit.setPlainText(snippet)
        self.paste_check.setChecked(bool(action.get("paste")))
        self.command_combo.setCurrentIndex(max(0, self.command_combo.findData(target)))
        self._fill_page_combo(target if kind == "page" else "next")
        self._validate_url()
        self._loading = False

    @staticmethod
    def _set_text(edit: QLineEdit, text: str) -> None:
        if edit.text() != text:
            edit.setText(text)

    def action(self) -> dict:
        kind = str(self.type_combo.currentData())
        target = ""
        if kind == "app":
            target = self.path_edit.text().strip()
        elif kind == "url":
            target = self.url_edit.text().strip()
        elif kind == "hotkey":
            target = self._hotkey_target
        elif kind == "text":
            target = self.text_edit.toPlainText()
        elif kind == "command":
            target = str(self.command_combo.currentData())
        elif kind == "page":
            target = str(self.page_combo.currentData() or "next")
        return normalize_action(
            {"type": kind, "target": target, "paste": self.paste_check.isChecked()}
        )

    def _show_page(self, kind: str) -> None:
        index = self._pages_by_type.get(kind, 0)
        self.stack.setCurrentIndex(index)
        # 스택 높이를 현재 페이지에 맞춘다 (가장 큰 페이지 높이만큼 빈 공간이 생기지 않게).
        for page_index in range(self.stack.count()):
            policy = (
                QSizePolicy.Policy.Preferred if page_index == index else QSizePolicy.Policy.Ignored
            )
            self.stack.widget(page_index).setSizePolicy(QSizePolicy.Policy.Preferred, policy)
        self.stack.adjustSize()

    def _type_changed(self) -> None:
        kind = str(self.type_combo.currentData())
        self._show_page(kind)
        if kind == "url" and not self.url_edit.text():
            self.url_edit.setText("https://")
        self._emit()

    def _emit(self) -> None:
        if not self._loading:
            self.changed.emit()

    def _validate_url(self) -> None:
        text = self.url_edit.text().strip().lower()
        valid = text.startswith(("http://", "https://")) or not text
        self.url_warning.setVisible(not valid)

    def _clear_hotkey(self) -> None:
        self.hotkey_edit.clear()
        self._hotkey_target = ""
        self._refresh_hotkey_label()
        self._emit()

    def _common_picked(self) -> None:
        sequence = str(self.common_combo.currentData() or "")
        self.common_combo.setCurrentIndex(0)
        if not sequence:
            return
        self._hotkey_target = sequence
        self.hotkey_edit.setKeySequence(
            QKeySequence.fromString(sequence, QKeySequence.SequenceFormat.PortableText)
        )
        self._refresh_hotkey_label()
        self._emit()

    def _refresh_hotkey_label(self) -> None:
        if self._hotkey_target:
            self.hotkey_value.setText(
                t(
                    "widget.launcher.studio.hotkey_value",
                    "전송할 키: {keys}",
                    keys=self._hotkey_target,
                )
            )
        else:
            self.hotkey_value.setText(
                t("widget.launcher.studio.hotkey_empty", "키 조합을 눌러 기록하세요")
            )

    def _hotkey_edited(self) -> None:
        sequence = self.hotkey_edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        self._hotkey_target = sequence.split(",")[0].strip()
        self._refresh_hotkey_label()
        self._emit()

    def _browse(self, mode: str) -> None:
        if self._browse_callback is None:
            return
        path = self._browse_callback(mode)
        if path:
            self.path_edit.setText(path)
            self._emit()


class InsertPreview(QWidget):
    """Large keycap preview where the insert art is positioned by dragging."""

    panned = pyqtSignal(int, int)
    zoomed = pyqtSignal(int)
    resetRequested = pyqtSignal()
    imageDropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(196)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._renderer = KeyDeckRenderer()
        self._deck: dict | None = None
        self._key: dict | None = None
        self._drag_origin: QPointF | None = None
        self._start_offset = (0, 0)
        self._pixmap: QPixmap | None = None
        self._offset = QPointF()

    def set_key(self, deck: dict | None, key: dict | None) -> None:
        self._deck = deck
        self._key = key
        self._rebuild()

    def _rebuild(self) -> None:
        self._pixmap = None
        if self._deck is None or self._key is None:
            self.update()
            return
        mini = deepcopy(default_deck())
        mini.update(
            {
                k: deepcopy(self._deck[k])
                for k in ("unit", "gap", "case", "led_brightness", "panorama")
            }
        )
        mini["case"]["header"] = False
        sample = deepcopy(self._key)
        sample.update({"x": 0.0, "y": 0.0})
        mini["pages"][0]["keys"] = [sample]
        width = max(40, self.width() - 24)
        height = max(40, self.height() - 34)
        scale = min(3.2, fit_scale(mini, 0, width, height, header=False))
        self._renderer.set_deck(mini, 0, scale=scale, header=False)
        self._pixmap = self._renderer.render_pixmap(dpr=self.devicePixelRatioF())
        geometry = self._renderer.geometry
        self._offset = QPointF(
            (self.width() - geometry.width) / 2, (self.height() - 18 - geometry.height) / 2
        )
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._rebuild()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QColor(255, 255, 255, 26))
        painter.setBrush(QColor(12, 15, 21, 235))
        painter.drawRoundedRect(rect, 12, 12)
        if self._pixmap is not None:
            painter.drawPixmap(self._offset, self._pixmap)
        painter.setPen(QColor(200, 210, 228, 150))
        hint = t(
            "widget.launcher.studio.preview_hint",
            "드래그: 위치 · 더블클릭: 초기화 · 이미지를 끌어다 놓기",
        )
        painter.drawText(
            rect.adjusted(8, 0, -8, -6),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
            hint,
        )
        painter.end()
        del event

    def _window(self) -> QRectF | None:
        if self._key is None or self._renderer.geometry is None:
            return None
        key = self._renderer.geometry.keys[0]
        return self._renderer.insert_window(key)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._key is not None:
            self._drag_origin = event.position()
            self._start_offset = (self._key["insert"]["ox"], self._key["insert"]["oy"])
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        window = self._window()
        if self._drag_origin is None or window is None or window.width() <= 0:
            return
        delta = event.position() - self._drag_origin
        ox = int(max(-100, min(100, self._start_offset[0] + delta.x() / window.width() * 100)))
        oy = int(max(-100, min(100, self._start_offset[1] + delta.y() / window.height() * 100)))
        self.panned.emit(ox, oy)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_origin = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        del event

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.resetRequested.emit()
        del event

    def wheelEvent(self, event) -> None:  # noqa: N802
        event.ignore()

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if (
            urls
            and urls[0].isLocalFile()
            and Path(urls[0].toLocalFile()).suffix.lower() in IMAGE_SUFFIXES
        ):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.imageDropped.emit(urls[0].toLocalFile())
            event.acceptProposedAction()


# ---------------------------------------------------------------------------
# Deck panorama
# ---------------------------------------------------------------------------

_PREVIEW_MAX_PX = 900


def _image_pixel_size(path: str) -> tuple[int, int]:
    size = QImageReader(path).size()
    return (size.width(), size.height()) if size.isValid() else (0, 0)


class PanoramaPreview(QWidget):
    """The current page's key windows laid over the panorama, as the deck will show it.

    Keys that use the panorama show their slice, the rest of the picture is dimmed so the
    crop is obvious.  Drag aligns the picture, Ctrl+wheel zooms, a double-click centres it,
    and an image dropped here (or a click while empty) replaces it.
    """

    panned = pyqtSignal(int, int)
    zoomed = pyqtSignal(int)
    resetRequested = pyqtSignal()
    imageDropped = pyqtSignal(str)
    chooseRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(170)
        self.setAcceptDrops(True)
        self._deck: dict | None = None
        self._highlight: set[str] = set()
        self._image: QImage | None = None
        self._image_size = (0, 0)
        self._image_key: tuple | None = None
        self._missing = False
        self._drag_origin: QPointF | None = None
        self._drag_placed: QRectF | None = None
        self._refresh_cursor()

    # -- state -------------------------------------------------------------------------

    def set_deck(self, deck: dict | None, highlight_ids=()) -> None:
        self._deck = deck
        self._highlight = set(highlight_ids)
        path = deck["panorama"]["path"] if deck else ""
        image_key = (path, Path(path).is_file()) if path else None
        if image_key != self._image_key:
            self._image_key = image_key
            self._image = None
            self._image_size = (0, 0)
            self._missing = bool(path) and not Path(path).is_file()
            source = panorama_image(path) if path and not self._missing else None
            if source is not None and not source.isNull():
                self._image_size = (source.width(), source.height())
                if max(source.width(), source.height()) > _PREVIEW_MAX_PX:
                    source = source.scaled(
                        _PREVIEW_MAX_PX,
                        _PREVIEW_MAX_PX,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                self._image = source
            elif path and not self._missing:
                self._missing = True
        self._refresh_cursor()
        self.update()

    def has_image(self) -> bool:
        return self._image is not None

    def _refresh_cursor(self) -> None:
        if self._image is not None:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _layout(self) -> tuple[DeckGeometry, QRectF, float, QPointF] | None:
        """(geometry, content area, scale, offset) mapping deck pixels into the widget."""
        if self._deck is None:
            return None
        geometry = DeckGeometry(self._deck, self._deck["page"], scale=1.0, header=False)
        area = geometry.content_rect
        avail = QRectF(self.rect()).adjusted(16, 14, -16, -30)
        if area.width() <= 0 or area.height() <= 0 or avail.width() <= 0:
            return None
        scale = min(avail.width() / area.width(), avail.height() / area.height())
        offset = QPointF(
            avail.left() + (avail.width() - area.width() * scale) / 2 - area.left() * scale,
            avail.top() + (avail.height() - area.height() * scale) / 2 - area.top() * scale,
        )
        return geometry, area, scale, offset

    @staticmethod
    def _map(rect: QRectF, scale: float, offset: QPointF) -> QRectF:
        return QRectF(
            rect.left() * scale + offset.x(),
            rect.top() * scale + offset.y(),
            rect.width() * scale,
            rect.height() * scale,
        )

    def _placed(self, area: QRectF) -> QRectF:
        left, top, width, height = panorama_rect(
            (area.left(), area.top(), area.width(), area.height()),
            self._image_size,
            self._deck["panorama"],
        )
        return QRectF(left, top, width, height)

    # -- painting ----------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        panel = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QColor(255, 255, 255, 26))
        painter.setBrush(QColor(12, 15, 21, 235))
        painter.drawRoundedRect(panel, 12, 12)
        layout = self._layout()
        if layout is not None:
            self._paint_layout(painter, panel, *layout)
        painter.setPen(QColor(200, 210, 228, 150))
        if self._image is not None:
            hint = t(
                "widget.launcher.studio.panorama_preview_hint",
                "드래그: 위치 · Ctrl+휠: 확대 · 더블클릭: 가운데로 · 이미지를 끌어다 놓아 교체",
            )
        elif self._missing:
            painter.setPen(QColor("#ffb86b"))
            hint = t(
                "widget.launcher.studio.panorama_missing",
                "이미지 파일을 찾을 수 없습니다. 다시 선택해 주세요.",
            )
        else:
            hint = t(
                "widget.launcher.studio.panorama_empty",
                "클릭해서 이미지를 선택하거나 여기로 끌어다 놓으세요",
            )
        painter.drawText(
            panel.adjusted(8, 0, -8, -7),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
            str(hint),
        )
        painter.end()
        del event

    def _paint_layout(
        self,
        painter: QPainter,
        panel: QRectF,
        geometry: DeckGeometry,
        area: QRectF,
        scale: float,
        offset: QPointF,
    ) -> None:
        image = self._image
        placed = self._map(self._placed(area), scale, offset) if image is not None else None
        clip = QPainterPath()
        clip.addRoundedRect(panel.adjusted(1, 1, -1, -1), 11, 11)
        if placed is not None:
            # 잘려 나가는 부분까지 흐리게 보여 줘 어느 부분이 키에 담기는지 알 수 있게 한다.
            painter.save()
            painter.setClipPath(clip)
            painter.setOpacity(0.28)
            painter.drawImage(placed, image)
            painter.restore()
        area_rect = self._map(area, scale, offset)
        painter.setPen(QPen(QColor(255, 255, 255, 60), 1.0, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(area_rect)
        radius = max(2.0, geometry.unit * 0.08 * scale)
        for key in geometry.keys:
            metrics = geometry.cap_metrics(key)
            window = self._map(metrics.top, scale, offset)
            path = QPainterPath()
            path.addRoundedRect(window, radius, radius)
            uses = key["insert"]["kind"] == "panorama"
            if uses and placed is not None:
                painter.save()
                painter.setClipPath(path)
                painter.fillPath(path, QColor(0, 0, 0, 90))
                painter.drawImage(placed, image)
                painter.restore()
            else:
                painter.fillPath(path, QColor(255, 255, 255, 18 if uses else 10))
            if key["id"] in self._highlight:
                pen = QPen(QColor(self._deck["case"]["accent"]), 2.0)
            elif uses:
                pen = QPen(QColor(255, 255, 255, 120), 1.0)
            else:
                pen = QPen(QColor(255, 255, 255, 46), 1.0, Qt.PenStyle.DotLine)
            painter.setPen(pen)
            painter.drawPath(path)
        if image is None:
            size = min(area_rect.width(), area_rect.height()) * 0.42
            glyph = glyph_pixmap("image", "#ffffff", int(size), self.devicePixelRatioF())
            if glyph is not None:
                painter.setOpacity(0.35)
                painter.drawPixmap(
                    QRectF(
                        area_rect.center().x() - size / 2,
                        area_rect.center().y() - size / 2,
                        size,
                        size,
                    ).toRect(),
                    glyph,
                )
                painter.setOpacity(1.0)

    # -- interaction -------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._image is None:
            self.chooseRequested.emit()
            return
        layout = self._layout()
        if layout is None:
            return
        self._drag_origin = event.position()
        self._drag_placed = self._placed(layout[1])
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_origin is None or self._drag_placed is None:
            return
        layout = self._layout()
        if layout is None:
            return
        _geometry, area, scale, _offset = layout
        delta = (event.position() - self._drag_origin) / max(scale, 1e-6)
        placed = self._drag_placed
        panorama = self._deck["panorama"]
        x = panorama_align_for(
            area.width(), placed.width(), placed.left() + delta.x() - area.left()
        )
        y = panorama_align_for(
            area.height(), placed.height(), placed.top() + delta.y() - area.top()
        )
        x = int(panorama["x"]) if x is None else x
        y = int(panorama["y"]) if y is None else y
        if (x, y) != (int(panorama["x"]), int(panorama["y"])):
            self.panned.emit(x, y)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_origin = None
        self._drag_placed = None
        self._refresh_cursor()
        del event

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if self._image is not None:
            self.resetRequested.emit()
        del event

    def wheelEvent(self, event) -> None:  # noqa: N802
        # 그냥 휠은 인스펙터 스크롤에 양보하고, Ctrl+휠만 확대한다.
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if self._image is None or self._deck is None or not ctrl:
            event.ignore()
            return
        steps = event.angleDelta().y() / 120.0
        if not steps:
            event.ignore()
            return
        low, high = PANORAMA_ZOOM_RANGE
        zoom = int(max(low, min(high, self._deck["panorama"]["zoom"] + round(steps * 10))))
        if zoom != self._deck["panorama"]["zoom"]:
            self.zoomed.emit(zoom)
        event.accept()

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if (
            urls
            and urls[0].isLocalFile()
            and Path(urls[0].toLocalFile()).suffix.lower() in IMAGE_SUFFIXES
        ):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.imageDropped.emit(urls[0].toLocalFile())
            event.acceptProposedAction()


class PanoramaEditor(QWidget):
    """Choose, frame and apply the deck panorama (shared by the deck and key inspectors)."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._loading = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.preview = PanoramaPreview(self)
        self.preview.panned.connect(
            lambda x, y: self._set({"panorama.x": x, "panorama.y": y}, "panorama.pan")
        )
        self.preview.zoomed.connect(
            lambda zoom: self._set({"panorama.zoom": zoom}, "panorama.zoom")
        )
        self.preview.resetRequested.connect(
            lambda: self._set({"panorama.x": 0, "panorama.y": 0, "panorama.zoom": 100})
        )
        self.preview.imageDropped.connect(self.controller.choose_panorama)
        self.preview.chooseRequested.connect(lambda: self.controller.choose_panorama(""))
        layout.addWidget(self.preview)
        self.info = QLabel(self)
        self.info.setObjectName("kdValue")
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        self.notice = _hint("", self)
        layout.addWidget(self.notice)
        form = _form()
        self.fit_seg = Segmented(PANORAMA_FITS, self, columns=2)
        self.fit_seg.changed.connect(lambda fit: self._set({"panorama.fit": fit}))
        form.addRow(t("widget.launcher.studio.panorama_fit", "배치"), self.fit_seg)
        self.zoom_slider = LabeledSlider(*PANORAMA_ZOOM_RANGE, "%", self, step=5)
        self.zoom_slider.valueChanged.connect(
            lambda zoom: self._set({"panorama.zoom": zoom}, "panorama.zoom")
        )
        form.addRow(t("widget.launcher.studio.panorama_zoom", "확대"), self.zoom_slider)
        layout.addLayout(form)
        buttons = QGridLayout()
        buttons.setHorizontalSpacing(6)
        buttons.setVerticalSpacing(6)
        self.choose_button = QPushButton(
            t("widget.launcher.studio.choose_panorama", "파노라마 이미지 선택…"), self
        )
        self.choose_button.setObjectName("primary_btn")
        self.choose_button.clicked.connect(lambda: self.controller.choose_panorama(""))
        self.apply_button = QPushButton(
            t("widget.launcher.studio.panorama_page", "이 페이지 전체에 적용"), self
        )
        self.apply_button.clicked.connect(self.controller.apply_panorama_to_page)
        self.clear_button = QPushButton(t("widget.launcher.studio.clear", "지우기"), self)
        self.clear_button.clicked.connect(self.controller.clear_panorama)
        buttons.addWidget(self.choose_button, 0, 0)
        buttons.addWidget(self.clear_button, 0, 1)
        buttons.addWidget(self.apply_button, 1, 0, 1, 2)
        buttons.setColumnStretch(0, 1)
        layout.addLayout(buttons)

    def load(self, deck: dict, highlight_ids=()) -> None:
        self._loading = True
        panorama = deck["panorama"]
        path = panorama["path"]
        self.preview.set_deck(deck, highlight_ids)
        has_image = self.preview.has_image()
        self.fit_seg.set_value(panorama["fit"])
        self.zoom_slider.set_value(panorama["zoom"])
        for widget in (self.fit_seg, self.zoom_slider, self.apply_button):
            widget.setEnabled(has_image)
        self.clear_button.setEnabled(bool(path) or bool(panorama_keys(deck)))
        page_keys = deck["pages"][deck["page"]]["keys"]
        page_users = panorama_keys(deck, deck["page"])
        self.apply_button.setEnabled(has_image and len(page_users) < len(page_keys))
        notice = ""
        if not path:
            info = t("widget.launcher.studio.no_image", "선택한 이미지 없음")
        elif not has_image:
            info = Path(panorama["name"] or path).name
        else:
            width, height = _image_pixel_size(path)
            info = t(
                "widget.launcher.studio.panorama_info",
                "{name} · {width}×{height}px · 키 {count}개에 적용",
                name=panorama["name"] or Path(path).name,
                width=width,
                height=height,
                count=len(panorama_keys(deck)),
            )
            if not page_users:
                notice = t(
                    "widget.launcher.studio.panorama_unused",
                    "이 페이지에는 파노라마를 쓰는 키가 없습니다. '이 페이지 전체에 적용'을 누르거나 "
                    "키를 골라 인서트를 '덱 파노라마'로 바꾸세요.",
                )
            elif self._is_low_resolution(deck, (width, height)):
                notice = t(
                    "widget.launcher.studio.panorama_lowres",
                    "원본 해상도가 낮아 키에서 흐릿하게 보일 수 있습니다. 더 큰 이미지를 권장합니다.",
                )
        self.info.setText(str(info))
        self.notice.setText(str(notice))
        self.notice.setVisible(bool(notice))
        self._loading = False

    @staticmethod
    def _is_low_resolution(deck: dict, pixel_size: tuple[int, int]) -> bool:
        """True when the picture is stretched more than 2× on a HiDPI (2×) screen."""
        if min(pixel_size) <= 0:
            return False
        geometry = DeckGeometry(deck, deck["page"], header=False)
        area = geometry.content_rect
        _left, _top, shown_w, _shown_h = panorama_rect(
            (0.0, 0.0, area.width(), area.height()), pixel_size, deck["panorama"]
        )
        return shown_w * 2.0 / pixel_size[0] > 2.0

    def _set(self, values: dict, coalesce: str = "") -> None:
        if not self._loading:
            self.controller.set_deck_fields(values, coalesce=coalesce)


# ---------------------------------------------------------------------------
# Key inspector
# ---------------------------------------------------------------------------


class KeyInspector(QWidget):
    """Tabs editing the selected key(s); style edits apply to every selected key."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._loading = False
        self._keys: list[dict] = []
        self._toggle_signature: str | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.summary = QLabel(self)
        self.summary.setObjectName("kdSummary")
        layout.addWidget(self.summary)
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("kdInspectorTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setExpanding(True)
        self.tabs.tabBar().setUsesScrollButtons(False)
        self.tabs.addTab(
            self._build_action_tab(),
            ui_icon("mdi6.gesture-tap"),
            t("widget.launcher.studio.tab_action", "기능"),
        )
        self.tabs.addTab(
            self._build_insert_tab(),
            ui_icon("mdi6.image-outline"),
            t("widget.launcher.studio.tab_insert", "그림"),
        )
        self.tabs.addTab(
            self._build_legend_tab(),
            ui_icon("mdi6.format-text"),
            t("widget.launcher.studio.tab_legend", "글자"),
        )
        self.tabs.addTab(
            self._build_cap_tab(),
            ui_icon("mdi6.keyboard-outline"),
            t("widget.launcher.studio.tab_cap", "모양·소리"),
        )
        self.tabs.setIconSize(QSize(16, 16))
        layout.addWidget(self.tabs, 1)

    # -- tab builders ---------------------------------------------------------------------

    def _build_action_tab(self) -> QWidget:
        scroll, layout = _scroll_page(self)
        layout.addWidget(_section(t("widget.launcher.studio.section_key", "이름"), self))
        form = _form()
        self.label_edit = QLineEdit(self)
        self.label_edit.setMaxLength(48)
        self.label_edit.setPlaceholderText(t("widget.launcher.studio.label_placeholder", "키 이름"))
        self.label_edit.textEdited.connect(lambda text: self._set("label", text, "label"))
        form.addRow(t("widget.launcher.studio.label", "이름"), self.label_edit)
        self.sublabel_edit = QLineEdit(self)
        self.sublabel_edit.setMaxLength(32)
        self.sublabel_edit.setPlaceholderText(
            t("widget.launcher.studio.sublabel_placeholder", "예: Ctrl+C (비워 둬도 됩니다)")
        )
        self.sublabel_edit.textEdited.connect(lambda text: self._set("sublabel", text, "sublabel"))
        form.addRow(t("widget.launcher.studio.sublabel", "작은 글자"), self.sublabel_edit)
        self.enabled_check = QCheckBox(
            t("widget.launcher.studio.enabled", "키 사용 (끄면 눌러도 반응하지 않음)"), self
        )
        self.enabled_check.toggled.connect(lambda value: self._set("enabled", bool(value)))
        form.addRow("", self.enabled_check)
        layout.addLayout(form)
        layout.addWidget(_section(t("widget.launcher.studio.section_press", "누를 때"), self))
        self.action_editor = ActionEditor(self, browse_callback=self.controller.browse_target)
        self.action_editor.changed.connect(
            lambda: self._set("action", self.action_editor.action(), "action")
        )
        layout.addWidget(self.action_editor)
        test_row = QHBoxLayout()
        self.test_button = QPushButton(t("widget.launcher.studio.test", "▶ 실행 테스트"), self)
        self.test_button.clicked.connect(lambda: self.controller.test_action("action"))
        test_row.addWidget(self.test_button)
        test_row.addStretch()
        layout.addLayout(test_row)
        layout.addWidget(_section(t("widget.launcher.studio.mode", "실행 방식"), self))
        self.mode_seg = Segmented(
            KEY_MODES,
            self,
            columns=2,
            icons={
                "tap": ui_icon("mdi6.gesture-tap", size=20),
                "toggle": ui_icon("mdi6.toggle-switch-outline", size=20),
            },
        )
        self.mode_seg.changed.connect(lambda value: self._set("mode", value))
        layout.addWidget(self.mode_seg)
        self.mode_hint = _hint("", self)
        layout.addWidget(self.mode_hint)
        layout.addWidget(self._build_toggle_box())
        layout.addWidget(
            _section(t("widget.launcher.studio.section_hold", "길게 누를 때 (0.55초)"), self)
        )
        layout.addWidget(
            _hint(
                t(
                    "widget.launcher.studio.hold_hint",
                    "보조 동작을 지정하면 길게 누를 때 실행되고, 짧게 누르면 기본 동작이 실행됩니다.",
                ),
                self,
            )
        )
        self.hold_editor = ActionEditor(self, browse_callback=self.controller.browse_target)
        self.hold_editor.changed.connect(
            lambda: self._set("hold_action", self.hold_editor.action(), "hold_action")
        )
        layout.addWidget(self.hold_editor)
        self.multi_hint = _hint(
            t(
                "widget.launcher.studio.multi_hint",
                "여러 키가 선택되어 있습니다. 이름과 동작은 키 하나만 선택했을 때 편집할 수 있습니다.",
            ),
            self,
        )
        self.multi_hint.setObjectName("kdWarn")
        layout.insertWidget(0, self.multi_hint)
        layout.addStretch()
        return scroll

    def _build_toggle_box(self) -> QWidget:
        """Options shown for toggle keys: how ON/OFF is marked and the starting state."""
        self.toggle_box = QFrame(self)
        self.toggle_box.setObjectName("kdCard")
        box = QVBoxLayout(self.toggle_box)
        box.setContentsMargins(10, 8, 10, 10)
        box.setSpacing(6)
        states = QHBoxLayout()
        states.setSpacing(10)
        self.toggle_off_icon = QLabel(self.toggle_box)
        self.toggle_on_icon = QLabel(self.toggle_box)
        for icon_label, caption_key, caption in (
            (self.toggle_off_icon, "widget.launcher.studio.toggle_off", "꺼짐"),
            (self.toggle_on_icon, "widget.launcher.studio.toggle_on", "켜짐"),
        ):
            column = QVBoxLayout()
            column.setSpacing(2)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_label.setMinimumSize(80, 80)
            text = QLabel(t(caption_key, caption), self.toggle_box)
            text.setObjectName("kdValue")
            text.setAlignment(Qt.AlignmentFlag.AlignCenter)
            column.addWidget(icon_label)
            column.addWidget(text)
            states.addLayout(column)
            if icon_label is self.toggle_off_icon:
                arrow = QLabel("→", self.toggle_box)
                arrow.setObjectName("kdValue")
                states.addWidget(arrow)
        states.addStretch()
        box.addLayout(states)
        indicator_label = QLabel(
            t("widget.launcher.studio.indicator", "표시 모양"), self.toggle_box
        )
        indicator_label.setObjectName("kdValue")
        box.addWidget(indicator_label)
        self.indicator_seg = Segmented(
            TOGGLE_INDICATORS, self.toggle_box, columns=5, text_under_icon=True
        )
        self.indicator_seg.changed.connect(lambda value: self._set("indicator", value))
        box.addWidget(self.indicator_seg)
        form = _form()
        self.toggle_color = ColorButton(self.toggle_box)
        self.toggle_color.colorChanged.connect(lambda color: self._set("led.color", color))
        form.addRow(t("widget.launcher.studio.toggle_color", "켜짐 색"), self.toggle_color)
        self.start_on_check = QCheckBox(
            t("widget.launcher.studio.start_on", "켜진 상태로 시작"), self.toggle_box
        )
        self.start_on_check.toggled.connect(lambda value: self._set("active", bool(value)))
        form.addRow("", self.start_on_check)
        box.addLayout(form)
        return self.toggle_box

    def _refresh_toggle_box(self, key: dict) -> None:
        toggle = key["mode"] == "toggle"
        self.toggle_box.setVisible(toggle)
        if key["mode"] == "toggle":
            self.mode_hint.setText(
                t(
                    "widget.launcher.studio.mode_toggle_hint",
                    "누르면 켜진 채로 눌려 있고, 다시 누르면 꺼집니다. 켤 때와 끌 때 모두 동작이 "
                    "실행되며, 켜짐/꺼짐은 아래 표시로 구분됩니다.",
                )
            )
        else:
            self.mode_hint.setText(
                t("widget.launcher.studio.mode_tap_hint", "누를 때마다 동작을 한 번 실행합니다.")
            )
        if not toggle:
            return
        self.indicator_seg.set_value(key["indicator"])
        self.toggle_color.set_color(key["led"]["color"])
        self.start_on_check.setChecked(bool(key["active"]))
        deck = self.controller.deck
        signature = json.dumps(
            [
                {k: key[k] for k in ("label", "sublabel", "insert", "legend", "cap", "led")},
                key["indicator"],
                key["action"],
                deck["case"],
                deck["unit"],
            ],
            sort_keys=True,
            ensure_ascii=False,
        )
        if signature == self._toggle_signature:
            return
        self._toggle_signature = signature
        for icon_label, on in ((self.toggle_off_icon, False), (self.toggle_on_icon, True)):
            sample = deepcopy(key)
            sample.update({"w": 1.0, "h": 1.0, "active": on, "enabled": True})
            icon_label.setPixmap(key_preview_icon(deck, sample, 76).pixmap(QSize(76, 76)))
        icons = {}
        for indicator_id, *_ in TOGGLE_INDICATORS:
            sample = deepcopy(key)
            sample.update({"w": 1.0, "h": 1.0, "active": True, "indicator": indicator_id})
            sample["label"] = ""
            sample["legend"]["layout"] = "art"
            icons[indicator_id] = key_preview_icon(deck, sample, 44)
        self.indicator_seg.set_icons(icons)

    def _build_insert_tab(self) -> QWidget:
        scroll, layout = _scroll_page(self)
        self.preview = InsertPreview(self)
        self.preview.panned.connect(
            lambda ox, oy: self._set_many({"insert.ox": ox, "insert.oy": oy}, "insert.pan")
        )
        self.preview.zoomed.connect(lambda zoom: self._set("insert.zoom", zoom, "insert.zoom"))
        self.preview.resetRequested.connect(
            lambda: self._set_many({"insert.ox": 0, "insert.oy": 0, "insert.zoom": 100})
        )
        self.preview.imageDropped.connect(self.controller.import_image_for_selection)
        layout.addWidget(self.preview)
        self.kind_seg = Segmented(INSERT_KINDS, self, columns=3)
        self.kind_seg.changed.connect(self._kind_changed)
        layout.addWidget(self.kind_seg)

        self.color_box = QWidget(self)
        color_form = _form()
        color_form.setContentsMargins(0, 0, 0, 0)
        self.color_box.setLayout(color_form)
        self.insert_color = ColorButton(self)
        self.insert_color.colorChanged.connect(lambda color: self._set("insert.color", color))
        self.insert_color2 = ColorButton(self)
        self.insert_color2.colorChanged.connect(lambda color: self._set("insert.color2", color))
        color_form.addRow(t("widget.launcher.studio.color_1", "색 1"), self.insert_color)
        self.color2_label = QLabel(t("widget.launcher.studio.color_2", "색 2"), self)
        color_form.addRow(self.color2_label, self.insert_color2)
        swatches = SwatchRow(INSERT_SWATCHES, self)
        swatches.colorPicked.connect(lambda color: self._set("insert.color", color))
        color_form.addRow("", swatches)
        layout.addWidget(self.color_box)

        self.pattern_box = QWidget(self)
        pattern_layout = QVBoxLayout(self.pattern_box)
        pattern_layout.setContentsMargins(0, 0, 0, 0)
        pattern_layout.addWidget(_section(t("widget.launcher.studio.pattern", "패턴"), self))
        self.pattern_gallery = PatternGallery(self)
        self.pattern_gallery.patternChanged.connect(
            lambda pattern: self._set("insert.pattern", pattern)
        )
        pattern_layout.addWidget(self.pattern_gallery)
        layout.addWidget(self.pattern_box)

        self.image_box = QWidget(self)
        image_layout = QVBoxLayout(self.image_box)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_row = QHBoxLayout()
        self.image_button = QPushButton(
            t("widget.launcher.studio.choose_image", "이미지 불러오기…"), self
        )
        self.image_button.setObjectName("primary_btn")
        self.image_button.clicked.connect(lambda: self.controller.import_image_for_selection(""))
        self.image_name = QLabel(self)
        self.image_name.setObjectName("kdValue")
        image_row.addWidget(self.image_button)
        image_row.addWidget(self.image_name, 1)
        image_layout.addLayout(image_row)
        image_form = _form()
        self.fit_seg = Segmented(INSERT_FITS, self, columns=3)
        self.fit_seg.changed.connect(lambda value: self._set("insert.fit", value))
        image_form.addRow(t("widget.launcher.studio.fit", "맞춤"), self.fit_seg)
        self.zoom_slider = LabeledSlider(20, 400, "%", self)
        self.zoom_slider.valueChanged.connect(
            lambda value: self._set("insert.zoom", value, "insert.zoom")
        )
        image_form.addRow(t("widget.launcher.studio.zoom", "확대"), self.zoom_slider)
        self.ox_slider = LabeledSlider(-100, 100, "", self)
        self.ox_slider.valueChanged.connect(
            lambda value: self._set("insert.ox", value, "insert.ox")
        )
        image_form.addRow(t("widget.launcher.studio.offset_x", "가로 위치"), self.ox_slider)
        self.oy_slider = LabeledSlider(-100, 100, "", self)
        self.oy_slider.valueChanged.connect(
            lambda value: self._set("insert.oy", value, "insert.oy")
        )
        image_form.addRow(t("widget.launcher.studio.offset_y", "세로 위치"), self.oy_slider)
        rotate_row = QHBoxLayout()
        rotate_left = QPushButton("⟲ 90°", self)
        rotate_right = QPushButton("⟳ 90°", self)
        rotate_left.clicked.connect(lambda: self._rotate(-90))
        rotate_right.clicked.connect(lambda: self._rotate(90))
        rotate_row.addWidget(rotate_left)
        rotate_row.addWidget(rotate_right)
        rotate_row.addStretch()
        image_form.addRow(t("widget.launcher.studio.rotate", "회전"), rotate_row)
        self.playback_combo = NoWheelComboBox(self)
        for playback_id, key, fallback in PLAYBACK_MODES:
            self.playback_combo.addItem(str(t(key, fallback)), playback_id)
        self.playback_combo.activated.connect(
            lambda _index: self._set("insert.playback", str(self.playback_combo.currentData()))
        )
        self.playback_label = QLabel(t("widget.launcher.studio.playback", "움직이는 이미지"), self)
        image_form.addRow(self.playback_label, self.playback_combo)
        image_layout.addLayout(image_form)
        layout.addWidget(self.image_box)

        self.panorama_box = QWidget(self)
        panorama_layout = QVBoxLayout(self.panorama_box)
        panorama_layout.setContentsMargins(0, 0, 0, 0)
        panorama_layout.addWidget(
            _hint(
                t(
                    "widget.launcher.studio.panorama_hint",
                    "덱 전체에 한 장의 이미지를 나눠 끼웁니다. 키 사이 간격까지 계산되어 이어져 보입니다.",
                ),
                self,
            )
        )
        self.panorama_editor = PanoramaEditor(self.controller, self)
        panorama_layout.addWidget(self.panorama_editor)
        layout.addWidget(self.panorama_box)

        opacity_form = _form()
        self.opacity_slider = LabeledSlider(10, 100, "%", self)
        self.opacity_slider.valueChanged.connect(
            lambda value: self._set("insert.opacity", value, "insert.opacity")
        )
        self.opacity_label = QLabel(t("widget.launcher.studio.opacity", "진하기"), self)
        opacity_form.addRow(self.opacity_label, self.opacity_slider)
        layout.addLayout(opacity_form)
        layout.addStretch()
        return scroll

    def _build_legend_tab(self) -> QWidget:
        scroll, layout = _scroll_page(self)
        layout.addWidget(_section(t("widget.launcher.studio.layout", "배치"), self))
        self.layout_seg = Segmented(LEGEND_LAYOUTS, self, columns=2)
        self.layout_seg.changed.connect(lambda value: self._set("legend.layout", value))
        layout.addWidget(self.layout_seg)
        form = _form()
        self.glyph_combo = GlyphCombo(self)
        self.glyph_combo.glyphChanged.connect(lambda glyph: self._set("legend.glyph", glyph))
        form.addRow(t("widget.launcher.studio.glyph", "아이콘"), self.glyph_combo)
        self.legend_color = ColorButton(self)
        self.legend_color.colorChanged.connect(lambda color: self._set("legend.color", color))
        form.addRow(t("widget.launcher.studio.legend_color", "글자 색"), self.legend_color)
        legend_swatches = SwatchRow(LEGEND_SWATCHES, self)
        legend_swatches.colorPicked.connect(lambda color: self._set("legend.color", color))
        form.addRow("", legend_swatches)
        glyph_color_row = QHBoxLayout()
        self.glyph_color = ColorButton(self)
        self.glyph_color.colorChanged.connect(lambda color: self._set("legend.glyph_color", color))
        self.glyph_same = QCheckBox(t("widget.launcher.studio.glyph_same", "글자 색과 같게"), self)
        self.glyph_same.toggled.connect(self._glyph_same_toggled)
        glyph_color_row.addWidget(self.glyph_color)
        glyph_color_row.addWidget(self.glyph_same)
        form.addRow(t("widget.launcher.studio.glyph_color", "아이콘 색"), glyph_color_row)
        self.size_slider = LabeledSlider(60, 180, "%", self)
        self.size_slider.valueChanged.connect(
            lambda value: self._set("legend.size", value, "legend.size")
        )
        form.addRow(t("widget.launcher.studio.legend_size", "크기"), self.size_slider)
        self.weight_seg = Segmented(LEGEND_WEIGHTS, self, columns=3)
        self.weight_seg.changed.connect(lambda value: self._set("legend.weight", value))
        form.addRow(t("widget.launcher.studio.weight", "굵기"), self.weight_seg)
        self.shadow_check = QCheckBox(
            t("widget.launcher.studio.shadow", "글자 그림자 (배경 위에서도 잘 보이게)"), self
        )
        self.shadow_check.toggled.connect(lambda value: self._set("legend.shadow", bool(value)))
        form.addRow("", self.shadow_check)
        layout.addLayout(form)
        layout.addStretch()
        return scroll

    def _build_cap_tab(self) -> QWidget:
        scroll, layout = _scroll_page(self)
        layout.addWidget(_section(t("widget.launcher.studio.material", "재질"), self))
        self.material_seg = Segmented(MATERIALS, self, columns=2)
        self.material_seg.changed.connect(lambda value: self._set("cap.material", value))
        layout.addWidget(self.material_seg)
        layout.addWidget(_section(t("widget.launcher.studio.profile", "키캡 모양"), self))
        self.profile_seg = Segmented(PROFILES, self, columns=2)
        self.profile_seg.changed.connect(lambda value: self._set("cap.profile", value))
        layout.addWidget(self.profile_seg)
        form = _form()
        self.cap_color = ColorButton(self)
        self.cap_color.colorChanged.connect(lambda color: self._set("cap.color", color))
        form.addRow(t("widget.launcher.studio.cap_color", "키캡 색"), self.cap_color)
        cap_swatches = SwatchRow(CAP_SWATCHES, self)
        cap_swatches.colorPicked.connect(lambda color: self._set("cap.color", color))
        form.addRow("", cap_swatches)
        layout.addLayout(form)
        layout.addWidget(_section(t("widget.launcher.studio.switch", "누르는 느낌 (스위치)"), self))
        self.switch_seg = Segmented(
            SWITCHES, self, columns=2, icons={sid: switch_icon(sid) for sid, *_ in SWITCHES}
        )
        self.switch_seg.changed.connect(lambda value: self._set("switch", value))
        layout.addWidget(self.switch_seg)
        sound_form = _form()
        sound_row = QHBoxLayout()
        self.sound_combo = NoWheelComboBox(self)
        self.sound_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.sound_combo.setMinimumContentsLength(8)
        for sound_id, key, fallback in SOUND_CHOICES:
            self.sound_combo.addItem(str(t(key, fallback)), sound_id)
        self.sound_combo.activated.connect(self._sound_changed)
        play = QPushButton("▶", self)
        play.setFixedWidth(40)
        play.setToolTip(t("widget.launcher.studio.preview_sound", "미리 듣기"))
        play.clicked.connect(self.controller.preview_sound)
        sound_row.addWidget(self.sound_combo, 1)
        sound_row.addWidget(play)
        sound_form.addRow(t("widget.launcher.studio.sound", "소리"), sound_row)
        self.sound_file_button = QPushButton(
            t("widget.launcher.studio.choose_sound", "WAV 파일 선택…"), self
        )
        self.sound_file_button.clicked.connect(self.controller.choose_sound)
        sound_form.addRow("", self.sound_file_button)
        layout.addLayout(sound_form)
        layout.addWidget(_section(t("widget.launcher.studio.led", "키 아래 불빛"), self))
        led_form = _form()
        self.led_combo = NoWheelComboBox(self)
        for led_id, key, fallback in LED_MODES:
            self.led_combo.addItem(str(t(key, fallback)), led_id)
        self.led_combo.activated.connect(
            lambda _index: self._set("led.mode", str(self.led_combo.currentData()))
        )
        led_form.addRow(t("widget.launcher.studio.led_mode", "켜지는 때"), self.led_combo)
        self.led_color = ColorButton(self)
        self.led_color.colorChanged.connect(lambda color: self._set("led.color", color))
        led_form.addRow(t("widget.launcher.studio.led_color", "불빛 색"), self.led_color)
        led_swatches = SwatchRow(LED_SWATCHES, self)
        led_swatches.colorPicked.connect(lambda color: self._set("led.color", color))
        led_form.addRow("", led_swatches)
        layout.addLayout(led_form)
        layout.addStretch()
        return scroll

    # -- loading -------------------------------------------------------------------------

    def load(self, keys: list[dict]) -> None:
        self._keys = keys
        if not keys:
            return
        key = keys[0]
        deck = self.controller.deck
        single = len(keys) == 1
        self._loading = True
        if single:
            self.summary.setText(key["label"] or t("widget.launcher.unnamed_key", "이름 없는 키"))
        else:
            self.summary.setText(
                t("widget.launcher.studio.multi_summary", "{count}개 키 선택됨", count=len(keys))
            )
        self.multi_hint.setVisible(not single)
        for widget in (
            self.label_edit,
            self.sublabel_edit,
            self.action_editor,
            self.hold_editor,
            self.test_button,
        ):
            widget.setEnabled(single)
        if self.label_edit.text() != key["label"]:
            self.label_edit.setText(key["label"])
        if self.sublabel_edit.text() != key["sublabel"]:
            self.sublabel_edit.setText(key["sublabel"])
        self.enabled_check.setChecked(bool(key["enabled"]))
        pages = deck["pages"]
        self.action_editor.set_pages(pages)
        self.hold_editor.set_pages(pages)
        self.action_editor.set_action(key["action"])
        self.hold_editor.set_action(key["hold_action"])
        self.mode_seg.set_value(key["mode"])
        self._refresh_toggle_box(key)
        insert = key["insert"]
        self.kind_seg.set_value(insert["kind"])
        self.insert_color.set_color(insert["color"])
        self.insert_color2.set_color(insert["color2"])
        self.pattern_gallery.set_pattern(insert["pattern"])
        self.image_name.setText(
            Path(insert["path"]).name
            if insert["path"]
            else t("widget.launcher.studio.no_image", "선택한 이미지 없음")
        )
        self.fit_seg.set_value(insert["fit"])
        self.zoom_slider.set_value(insert["zoom"])
        self.ox_slider.set_value(insert["ox"])
        self.oy_slider.set_value(insert["oy"])
        self.playback_combo.setCurrentIndex(
            max(0, self.playback_combo.findData(insert["playback"]))
        )
        animated = (
            insert["kind"] == "image" and bool(insert["path"]) and is_animated(insert["path"])
        )
        self.playback_label.setVisible(animated)
        self.playback_combo.setVisible(animated)
        self.opacity_slider.set_value(insert["opacity"])
        self._sync_insert_sections(insert["kind"])
        legend = key["legend"]
        self.layout_seg.set_value(legend["layout"])
        self.glyph_combo.set_glyph(legend["glyph"])
        self.legend_color.set_color(legend["color"])
        self.glyph_same.setChecked(not legend["glyph_color"])
        self.glyph_color.set_color(legend["glyph_color"] or legend["color"])
        self.glyph_color.setEnabled(bool(legend["glyph_color"]))
        self.size_slider.set_value(legend["size"])
        self.weight_seg.set_value(legend["weight"])
        self.shadow_check.setChecked(bool(legend["shadow"]))
        cap = key["cap"]
        self.material_seg.set_value(cap["material"])
        self.profile_seg.set_value(cap["profile"])
        self.cap_color.set_color(cap["color"])
        self.switch_seg.set_value(key["switch"])
        self.sound_combo.setCurrentIndex(max(0, self.sound_combo.findData(key["sound"])))
        self.sound_file_button.setVisible(key["sound"] == "custom")
        if key["sound"] == "custom" and key["sound_path"]:
            self.sound_file_button.setText(Path(key["sound_path"]).name)
        self.led_combo.setCurrentIndex(max(0, self.led_combo.findData(key["led"]["mode"])))
        self.led_color.set_color(key["led"]["color"])
        if insert["kind"] == "panorama":
            self.panorama_editor.load(deck, [item["id"] for item in keys])
        else:
            self.preview.set_key(deck, key)
        self._loading = False

    def refresh_material_icons(self) -> None:
        if not self._keys:
            return
        deck = self.controller.deck
        base = deepcopy(self._keys[0])
        icons = {}
        for material_id, *_ in MATERIALS:
            sample = deepcopy(base)
            sample.update({"w": 1.0, "h": 1.0, "label": ""})
            sample["cap"]["material"] = material_id
            sample["legend"]["layout"] = "art"
            # 재질 차이가 보이도록 인서트는 비우고 LED를 켠 샘플로 그린다.
            sample["insert"]["kind"] = "none"
            sample["led"] = {"mode": "static", "color": sample["led"]["color"]}
            sample["enabled"] = True
            icons[material_id] = key_preview_icon(deck, sample, 34)
        self.material_seg.set_icons(icons)
        profiles = {}
        for profile_id, *_ in PROFILES:
            sample = deepcopy(base)
            sample.update({"w": 1.0, "h": 1.0, "label": "", "enabled": True})
            sample["cap"]["profile"] = profile_id
            sample["legend"]["layout"] = "art"
            sample["insert"]["kind"] = "none"
            profiles[profile_id] = key_preview_icon(deck, sample, 34)
        self.profile_seg.set_icons(profiles)

    def _sync_insert_sections(self, kind: str) -> None:
        self.color_box.setVisible(kind in {"color", "gradient", "pattern"})
        self.insert_color2.setVisible(kind in {"gradient", "pattern"})
        self.color2_label.setVisible(kind in {"gradient", "pattern"})
        self.pattern_box.setVisible(kind == "pattern")
        self.image_box.setVisible(kind == "image")
        self.panorama_box.setVisible(kind == "panorama")
        # 키 하나만 그리는 미리보기로는 파노라마 조각을 보여 줄 수 없어 배치 미리보기로 대신한다.
        self.preview.setVisible(kind != "panorama")
        self.opacity_label.setVisible(kind != "none")
        self.opacity_slider.setVisible(kind != "none")

    # -- edits ---------------------------------------------------------------------------

    def _set(self, path: str, value, coalesce: str = "") -> None:
        if self._loading:
            return
        self.controller.set_key_fields({path: value}, coalesce=coalesce)

    def _set_many(self, values: dict, coalesce: str = "") -> None:
        if self._loading:
            return
        self.controller.set_key_fields(values, coalesce=coalesce)

    def _kind_changed(self, kind: str) -> None:
        self._sync_insert_sections(kind)
        if kind == "image" and self._keys and not self._keys[0]["insert"]["path"]:
            self.controller.import_image_for_selection("")
            return
        if kind == "panorama" and not self.controller.deck["panorama"]["path"]:
            # 선택한 키에 바로 적용된다. 취소하면 인스펙터를 다시 읽어 이전 종류로 돌아간다.
            self.controller.choose_panorama("")
            return
        self._set("insert.kind", kind)

    def _rotate(self, delta: int) -> None:
        if not self._keys:
            return
        current = int(self._keys[0]["insert"]["rotate"])
        self._set("insert.rotate", (current + delta) % 360)

    def _glyph_same_toggled(self, same: bool) -> None:
        self.glyph_color.setEnabled(not same)
        if self._loading:
            return
        self._set("legend.glyph_color", "" if same else self.glyph_color.color())

    def _sound_changed(self) -> None:
        choice = str(self.sound_combo.currentData())
        self.sound_file_button.setVisible(choice == "custom")
        if choice == "custom" and self._keys and not self._keys[0]["sound_path"]:
            self.controller.choose_sound()
            return
        self._set("sound", choice)


# ---------------------------------------------------------------------------
# Deck inspector
# ---------------------------------------------------------------------------


class DeckInspector(QWidget):
    """Deck-wide settings shown when no key is selected."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._loading = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        title = QLabel(t("widget.launcher.studio.deck_title", "덱 설정"), self)
        title.setObjectName("kdSummary")
        outer.addWidget(title)
        scroll, layout = _scroll_page(self)
        outer.addWidget(scroll, 1)
        layout.addWidget(
            _hint(
                t(
                    "widget.launcher.studio.deck_hint",
                    "키를 클릭하면 키 설정으로 바뀝니다. 빈 곳을 클릭하면 이 화면으로 돌아옵니다.",
                ),
                self,
            )
        )
        layout.addWidget(_section(t("widget.launcher.studio.section_deck", "덱 이름"), self))
        form = _form()
        self.name_edit = QLineEdit(self)
        self.name_edit.setMaxLength(32)
        self.name_edit.setPlaceholderText(str(t("widget.launcher.title", "KEYDECK")))
        self.name_edit.textEdited.connect(lambda text: self._set("name", text, "name"))
        form.addRow(t("widget.launcher.studio.deck_name", "덱 이름"), self.name_edit)
        self.header_check = QCheckBox(
            t("widget.launcher.studio.header", "위쪽에 이름과 페이지 표시"), self
        )
        self.header_check.toggled.connect(lambda value: self._set("case.header", bool(value)))
        form.addRow("", self.header_check)
        layout.addLayout(form)
        layout.addWidget(_section(t("widget.launcher.studio.section_case", "케이스"), self))
        self.case_seg = Segmented(CASE_STYLES, self, columns=2)
        self.case_seg.changed.connect(lambda value: self._set("case.style", value))
        layout.addWidget(self.case_seg)
        case_form = _form()
        self.case_color = ColorButton(self)
        self.case_color.colorChanged.connect(lambda color: self._set("case.color", color))
        case_form.addRow(t("widget.launcher.studio.case_color", "케이스 색"), self.case_color)
        case_swatches = SwatchRow(CASE_SWATCHES, self)
        case_swatches.colorPicked.connect(lambda color: self._set("case.color", color))
        case_form.addRow("", case_swatches)
        self.accent_color = ColorButton(self)
        self.accent_color.colorChanged.connect(lambda color: self._set("case.accent", color))
        case_form.addRow(t("widget.launcher.studio.accent", "포인트 색"), self.accent_color)
        layout.addLayout(case_form)
        layout.addWidget(_section(t("widget.launcher.studio.section_grid", "크기"), self))
        grid_form = _form()
        self.unit_slider = LabeledSlider(48, 112, " px", self, step=2)
        self.unit_slider.valueChanged.connect(lambda value: self._set("unit", value, "unit"))
        grid_form.addRow(t("widget.launcher.studio.unit", "키 크기"), self.unit_slider)
        self.gap_slider = LabeledSlider(2, 16, " px", self)
        self.gap_slider.valueChanged.connect(lambda value: self._set("gap", value, "gap"))
        grid_form.addRow(t("widget.launcher.studio.gap", "키 사이 간격"), self.gap_slider)
        layout.addLayout(grid_form)
        layout.addWidget(
            _section(t("widget.launcher.studio.section_feedback", "불빛 · 소리 · 움직임"), self)
        )
        feedback_form = _form()
        self.led_slider = LabeledSlider(0, 100, "%", self)
        self.led_slider.valueChanged.connect(
            lambda value: self._set("led_brightness", value, "led")
        )
        feedback_form.addRow(
            t("widget.launcher.studio.led_brightness", "불빛 밝기"), self.led_slider
        )
        self.sound_check = QCheckBox(
            t("widget.launcher.studio.sound_enabled", "누를 때 소리 내기"), self
        )
        self.sound_check.toggled.connect(lambda value: self._set("sound_enabled", bool(value)))
        feedback_form.addRow("", self.sound_check)
        self.volume_slider = LabeledSlider(0, 100, "%", self)
        self.volume_slider.valueChanged.connect(
            lambda value: self._set("sound_volume", value, "volume")
        )
        feedback_form.addRow(t("widget.launcher.studio.volume", "음량"), self.volume_slider)
        self.motion_check = QCheckBox(
            t("widget.launcher.studio.reduce_motion", "움직임 줄이기 (애니메이션 없이 바로 반응)"),
            self,
        )
        self.motion_check.toggled.connect(lambda value: self._set("reduce_motion", bool(value)))
        feedback_form.addRow("", self.motion_check)
        layout.addLayout(feedback_form)
        layout.addWidget(
            _section(t("widget.launcher.studio.section_panorama", "파노라마 이미지"), self)
        )
        layout.addWidget(
            _hint(
                t(
                    "widget.launcher.studio.panorama_hint",
                    "덱 전체에 한 장의 이미지를 나눠 끼웁니다. 키 사이 간격까지 계산되어 이어져 보입니다.",
                ),
                self,
            )
        )
        self.panorama_editor = PanoramaEditor(self.controller, self)
        layout.addWidget(self.panorama_editor)
        self.help_toggle = QToolButton(self)
        self.help_toggle.setObjectName("kdDisclosure")
        self.help_toggle.setCheckable(True)
        self.help_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.help_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.help_toggle.setText(t("widget.launcher.studio.section_shortcuts", "편집 요령 보기"))
        layout.addWidget(self.help_toggle)
        self.help_text = _hint(
            t(
                "widget.launcher.studio.shortcuts",
                "• 키 클릭: 선택 · Ctrl/Shift+클릭: 여러 개 선택 · 빈 곳 드래그: 범위 선택\n"
                "• 키 드래그: 옮기기 · 선택한 키의 오른쪽/아래 점: 크기 바꾸기\n"
                "• 방향키: 조금씩 옮기기 (Shift: 한 칸씩) · Delete: 삭제 · Ctrl+D: 복제\n"
                "• Ctrl+C/V: 모양 복사·붙여넣기 · Ctrl+Z/Y: 실행 취소·다시 실행",
            ),
            self,
        )
        self.help_text.setVisible(False)
        layout.addWidget(self.help_text)

        def _toggle_help(shown: bool) -> None:
            self.help_text.setVisible(shown)
            self.help_toggle.setArrowType(
                Qt.ArrowType.DownArrow if shown else Qt.ArrowType.RightArrow
            )

        self.help_toggle.toggled.connect(_toggle_help)
        layout.addStretch()

    def load(self, deck: dict) -> None:
        self._loading = True
        if self.name_edit.text() != deck["name"]:
            self.name_edit.setText(deck["name"])
        self.header_check.setChecked(bool(deck["case"]["header"]))
        self.case_seg.set_value(deck["case"]["style"])
        self.case_color.set_color(deck["case"]["color"])
        self.accent_color.set_color(deck["case"]["accent"])
        self.unit_slider.set_value(deck["unit"])
        self.gap_slider.set_value(deck["gap"])
        self.led_slider.set_value(deck["led_brightness"])
        self.sound_check.setChecked(bool(deck["sound_enabled"]))
        self.volume_slider.set_value(deck["sound_volume"])
        self.motion_check.setChecked(bool(deck["reduce_motion"]))
        self.panorama_editor.load(deck)
        self._loading = False

    def _set(self, path: str, value, coalesce: str = "") -> None:
        if not self._loading:
            self.controller.set_deck_fields({path: value}, coalesce=coalesce)


__all__ = [
    "ActionEditor",
    "ColorButton",
    "DeckInspector",
    "GlyphCombo",
    "InsertPreview",
    "KeyInspector",
    "LabeledSlider",
    "PanoramaEditor",
    "PanoramaPreview",
    "PatternGallery",
    "Segmented",
    "key_preview_icon",
]
