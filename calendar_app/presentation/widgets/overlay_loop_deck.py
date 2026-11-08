# -*- coding: utf-8 -*-
"""Independent, touch-friendly six-channel KeyDeck and microphone loop mixer."""

import math
import os
from pathlib import Path

from PyQt6.QtCore import QEvent, QPoint, QSignalBlocker, QSize, QStandardPaths, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QScroller,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_styles import (
    build_dialog_stylesheet,
    get_dialog_theme_tokens,
)
from calendar_app.presentation.widgets.overlay_base import _BaseOverlayWidget, _GripFrame
from calendar_app.presentation.widgets.widget_placement import NoWheelComboBox, NoWheelSpinBox
from calendar_app.shared.app_lifecycle import is_app_exiting
from calendar_app.shared.typography import get_typography_scale


class TouchMixerComboBox(NoWheelComboBox):
    """Keep the input selector recognizable even when a platform arrow is absent."""

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.palette().text().color()
        if not self.isEnabled():
            color.setAlpha(100)
        painter.setPen(QPen(color, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        x, y = self.width() - 20, self.height() // 2
        painter.drawLine(x - 4, y - 2, x, y + 2)
        painter.drawLine(x, y + 2, x + 4, y - 2)


class TouchMixerSlider(QSlider):
    """The entire 44px groove is a direct-position touch target; wheel never edits."""

    def __init__(self, label, low, high, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setRange(low, high)
        self.setMinimumHeight(44)
        self.setAccessibleName(label)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):  # noqa: N802
        event.ignore()

    def _position(self, event):
        fraction = max(0.0, min(1.0, (event.position().x() - 14) / max(1, self.width() - 28)))
        if self.invertedAppearance():
            fraction = 1.0 - fraction
        self.setValue(round(self.minimum() + fraction * (self.maximum() - self.minimum())))

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.setSliderDown(True)
            self._position(event)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self.isSliderDown():
            self._position(event)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if self.isSliderDown():
            self._position(event)
            self.setSliderDown(False)
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class _Waveform(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(34)
        self.peaks = []
        self.position = None
        self.accent = QColor("#b9a0f2")

    def paintEvent(self, event):  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.height() / 2
        faded = QColor(self.accent)
        faded.setAlpha(55)
        painter.setPen(QPen(faded, 1))
        painter.drawLine(8, round(center), self.width() - 8, round(center))
        painter.setPen(QPen(self.accent, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        count = len(self.peaks)
        for index, value in enumerate(self.peaks):
            height = max(1, min(1.0, abs(float(value))) * (center - 3))
            x = 8 + index * max(1, self.width() - 16) / max(1, count - 1)
            painter.drawLine(round(x), round(center - height), round(x), round(center + height))
        if self.position is not None:
            x = round(8 + self.position * (self.width() - 16))
            painter.setPen(QPen(self.accent, 2))
            painter.drawLine(x, 1, x, self.height() - 1)


def _button(text, parent, callback=None, *, toggle=False):
    button = QPushButton(text, parent)
    button.setObjectName("ghost_btn")
    button.setMinimumHeight(48)
    button.setCheckable(toggle)
    button.setAutoDefault(False)
    if callback is not None:
        button.clicked.connect(callback)
    return button


def _touch_combo(combo):
    combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
    combo.setMinimumWidth(80)
    combo.view().setStyleSheet("QAbstractItemView::item {min-height:44px; padding:3px 8px;}")
    QScroller.grabGesture(combo.view().viewport(), QScroller.ScrollerGestureType.TouchGesture)


class _TrackCard(QFrame):
    def __init__(self, mixer_widget, index):
        super().__init__(mixer_widget)
        self.panel, self.index = mixer_widget, index
        self.setObjectName("loopTrack")
        self.setProperty("role", "dialogCard")
        self.setMinimumWidth(280)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(2)
        title = QHBoxLayout()
        self.number = QLabel(f"{index + 1:02d}", self)
        title.addWidget(self.number)
        self.name = QLineEdit(self)
        self.name.setMaxLength(40)
        self.name.setAccessibleName(
            t("loop_mixer.track_name", "트랙 {number} 이름", number=index + 1)
        )
        self.name.setMinimumHeight(44)
        self.name.editingFinished.connect(lambda: self._edit(name=self.name.text()))
        title.addWidget(self.name, 1)
        root.addLayout(title)
        self.source = TouchMixerComboBox(self)
        self.source.setMinimumHeight(44)
        _touch_combo(self.source)
        self.source.setAccessibleName(
            t("loop_mixer.source", "트랙 {number} 입력 소스", number=index + 1)
        )
        self.source.activated.connect(lambda: self._edit(source=self.source.currentData()))
        root.addWidget(self.source)
        self.wave = _Waveform(self)
        root.addWidget(self.wave)
        controls = QHBoxLayout()
        self.arm = _button(t("loop_mixer.arm", "● 대기"), self, toggle=True)
        self.arm.setToolTip(
            t("loop_mixer.arm_hint", "녹음을 누르면 대기 중인 트랙을 함께 한 바퀴 녹음합니다.")
        )
        self.mute = _button(t("loop_mixer.mute", "음소거"), self, toggle=True)
        self.solo = _button(t("loop_mixer.solo", "솔로"), self, toggle=True)
        for button, key in ((self.arm, "armed"), (self.mute, "muted"), (self.solo, "solo")):
            controls.addWidget(button, 1)
            button.toggled.connect(lambda value, field=key: self._edit(**{field: value}))
        root.addLayout(controls)
        self.volume = TouchMixerSlider(
            t("loop_mixer.track_volume", "트랙 {number} 음량", number=index + 1), 0, 100, self
        )
        self.volume_value = QLabel(self)
        self.volume.valueChanged.connect(lambda value: self._edit(volume=value))
        self.pan = TouchMixerSlider(
            t("loop_mixer.track_pan", "트랙 {number} 좌우 밸런스", number=index + 1),
            -100,
            100,
            self,
        )
        self.pan_value = QLabel(self)
        self.pan.valueChanged.connect(lambda value: self._edit(pan=value))
        for label, slider, value_label in (
            (t("loop_mixer.volume", "음량"), self.volume, self.volume_value),
            (t("loop_mixer.pan", "좌우"), self.pan, self.pan_value),
        ):
            row = QHBoxLayout()
            row.addWidget(QLabel(label, self))
            row.addWidget(slider, 1)
            value_label.setMinimumWidth(40)
            row.addWidget(value_label)
            root.addLayout(row)
        tools = QHBoxLayout()
        self.load = _button(
            t("loop_mixer.wav_load", "WAV 담기"), self, lambda: mixer_widget._load_track(index)
        )
        self.clear = _button(
            t("loop_mixer.clear", "비우기"), self, lambda: mixer_widget._clear_track(index)
        )
        tools.addWidget(self.load, 1)
        tools.addWidget(self.clear, 1)
        root.addLayout(tools)

    def _edit(self, **values):
        self.panel._edit_track(self.index, **values)

    def sync(self, data, options, fraction, running):
        if not self.name.hasFocus():
            with QSignalBlocker(self.name):
                self.name.setText(data.get("name", ""))
        current = data.get("source", "none")
        items = list(options)
        if current not in {value for _, value in items}:
            items.append(
                (t("loop_mixer.disconnected", "연결 끊김 · {source}", source=current), current)
            )
        if [
            (self.source.itemText(i), self.source.itemData(i)) for i in range(self.source.count())
        ] != items:
            with QSignalBlocker(self.source):
                self.source.clear()
                for label, value in items:
                    self.source.addItem(label, value)
        self.source.setCurrentIndex(max(0, self.source.findData(current)))
        for button, key in ((self.arm, "armed"), (self.mute, "muted"), (self.solo, "solo")):
            with QSignalBlocker(button):
                button.setChecked(bool(data.get(key)))
        for slider, key, default in ((self.volume, "volume", 100), (self.pan, "pan", 0)):
            if not slider.isSliderDown():
                with QSignalBlocker(slider):
                    slider.setValue(data.get(key, default))
        self.volume_value.setText(f"{data.get('volume', 100)}%")
        pan = data.get("pan", 0)
        self.pan_value.setText("C" if pan == 0 else f"{'L' if pan < 0 else 'R'}{abs(pan)}")
        self.wave.peaks = data.get("peaks", [])
        self.wave.position = fraction if running and data.get("has_audio") else None
        self.wave.update()
        for control in (self.source, self.load, self.clear):
            control.setEnabled(not running)
        self.clear.setEnabled(not running and bool(data.get("has_audio")))
        self.arm.setEnabled(not running)


class OverlayLoopDeckWidget(_BaseOverlayWidget):
    """Real overlay instance: no dialog exec, no embedded performance pads, no autoplay."""

    _PREFIX = "overlay_loop_deck"
    _STYLES = [("default", "Loop mixer")]
    _STYLE_I18N_PREFIX = "loop_mixer"

    def __init__(self, owner):
        self._mixer = None
        self._columns = 0
        self._layout_mode = None
        self._reflowing = False
        self._geometry_guard = False
        self._dirty = False
        self._revision = 0
        self._pending_io = None
        self._shutdown = False
        self._autosave_blocked = False
        self._last_mode = "idle"
        self._notice = ""
        self._source_options = []
        self._source_refresh_ticks = 0
        super().__init__(owner)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self._install_geometry_limits()
        self._poll = QTimer(self)
        self._poll.setInterval(50)
        self._poll.timeout.connect(self._refresh_face)
        self._save = QTimer(self)
        self._save.setSingleShot(True)
        self._save.setInterval(700)
        self._save.timeout.connect(self._autosave)
        self._restore_session()
        self._refresh_face()

    def _settings_prefix(self):
        return self._PREFIX

    def _default_font_size(self):
        return 11

    def _initialize_display_preset(self):
        pass  # A mixer is an interactive panel, never a text-template preset.

    def widget_shape_id(self):
        return "card"

    def _build_face(self):
        from calendar_app.infrastructure.runtime.loop_mixer_audio import LoopMixer

        self._mixer = LoopMixer()
        self._mixer.configure(120, 4)
        face = _GripFrame(self)
        face.setObjectName("loopMixerFace")
        root = QVBoxLayout(face)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)
        self.header = QFrame(face)
        header = QHBoxLayout(self.header)
        header.setContentsMargins(0, 0, 0, 0)
        title = QLabel(t("loop_mixer.title", "루프 믹서"), self.header)
        title.setProperty("role", "dialogTitle")
        header.addWidget(title)
        self.subtitle = QLabel(
            t("loop_mixer.touch_hint", "여러 키덱 + 마이크 · 터치로 리듬을 쌓으세요"), self.header
        )
        header.addWidget(self.subtitle, 1)
        close = _button(t("loop_mixer.hide", "×"), self.header, lambda: self.set_enabled(False))
        close.setAccessibleName(t("loop_mixer.hide_label", "루프 믹서 숨기기"))
        close.setFixedWidth(48)
        header.addWidget(close)
        root.addWidget(self.header)
        self.transport = QGridLayout()
        self.play_button = _button(t("loop_mixer.play", "▶ 재생"), face, self._play)
        self.play_button.setObjectName("primary_btn")
        self.stop_button = _button(t("loop_mixer.stop", "■ 정지"), face, self._stop)
        self.record_button = _button(t("loop_mixer.record", "● 녹음"), face, self._record)
        self.record_button.setObjectName("danger_btn")
        self.bpm = NoWheelSpinBox(face)
        self.bpm.setRange(40, 240)
        self.bpm.setSuffix(" BPM")
        self.bpm.setMinimumHeight(48)
        self.bpm.setAccessibleName(t("loop_mixer.bpm", "루프 빠르기 BPM"))
        self.bpm.valueChanged.connect(self._configure)
        self.bars = TouchMixerComboBox(face)
        _touch_combo(self.bars)
        self.bars.setMinimumHeight(48)
        self.bars.setAccessibleName(t("loop_mixer.bars", "루프 길이"))
        for number in (1, 2, 4, 8):
            self.bars.addItem(t("loop_mixer.bar_count", "{number}마디", number=number), number)
        self.bars.activated.connect(self._configure)
        for column, control in enumerate(
            (self.play_button, self.stop_button, self.record_button, self.bpm, self.bars)
        ):
            self.transport.addWidget(control, 0, column)
        root.addLayout(self.transport)
        self.inputs = QHBoxLayout()
        self.sources_label = QLabel(face)
        self.inputs.addWidget(self.sources_label)
        self.add_deck_button = _button(t("loop_mixer.add_keydeck", "+ 키덱"), face)
        self.add_deck_button.clicked.connect(self._add_deck_menu)
        self.inputs.addWidget(self.add_deck_button)
        self.mic_combo = TouchMixerComboBox(face)
        _touch_combo(self.mic_combo)
        self.mic_combo.setMinimumHeight(44)
        self.mic_combo.setAccessibleName(t("loop_mixer.mic_device", "마이크 입력 장치"))
        self.mic_combo.addItem(t("loop_mixer.mic_default", "마이크 · 시스템 기본"), "default")
        self.mic_combo.activated.connect(self._microphone_selected)
        self.inputs.addWidget(self.mic_combo, 1)
        self.mic_refresh = _button(t("loop_mixer.devices", "장치"), face, self._refresh_devices)
        self.inputs.addWidget(self.mic_refresh)
        self.mic_badge = QLabel(t("loop_mixer.mic_off", "마이크 꺼짐"), face)
        self.inputs.addWidget(self.mic_badge)
        root.addLayout(self.inputs)
        self.progress = QProgressBar(face)
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(5)
        root.addWidget(self.progress)
        self.scroll = QScrollArea(face)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        QScroller.grabGesture(self.scroll.viewport(), QScroller.ScrollerGestureType.TouchGesture)
        self.cards_body = QWidget(self.scroll)
        self.cards_body.setObjectName("loopCardsBody")
        self.grid = QGridLayout(self.cards_body)
        self.grid.setContentsMargins(0, 0, 3, 0)
        self.grid.setSpacing(10)
        self.cards = [_TrackCard(self, index) for index in range(6)]
        self.scroll.setWidget(self.cards_body)
        root.addWidget(self.scroll, 1)
        self.master_row = QHBoxLayout()
        self.master_row.addWidget(QLabel(t("loop_mixer.master", "마스터"), face))
        self.master = TouchMixerSlider(t("loop_mixer.master_volume", "마스터 음량"), 0, 100, face)
        self.master.valueChanged.connect(self._master_changed)
        self.master_row.addWidget(self.master, 1)
        self.master_value = QLabel(face)
        self.master_row.addWidget(self.master_value)
        self.level = QProgressBar(face)
        self.level.setRange(0, 1000)
        self.level.setTextVisible(False)
        self.level.setFixedWidth(100)
        self.level.setAccessibleName(t("loop_mixer.output_level", "출력 음량 표시"))
        self.master_row.addWidget(self.level)
        self.overdub = _button(t("loop_mixer.overdub", "겹쳐 녹음"), face, toggle=True)
        self.overdub.setChecked(True)
        self.master_row.addWidget(self.overdub)
        root.addLayout(self.master_row)
        self.footer = QGridLayout()
        self.open_button = _button(
            t("loop_mixer.project_open", "프로젝트 열기"), face, self._open_project
        )
        self.save_button = _button(
            t("loop_mixer.project_save", "저장"), face, self._save_project_as
        )
        self.export_button = _button(t("loop_mixer.export", "WAV 내보내기"), face, self._export)
        for column, button in enumerate((self.open_button, self.save_button, self.export_button)):
            self.footer.addWidget(button, 0, column)
        root.addLayout(self.footer)
        self.status = QLabel(face)
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setMinimumHeight(36)
        root.addWidget(self.status)
        self._reflow(3)
        return face

    def _real_settings(self):
        return getattr(self.owner, "_real", self.owner).settings

    def _apply_appearance(self):
        tokens = get_dialog_theme_tokens(settings=self._real_settings())
        typography = get_typography_scale(self._real_settings())
        accent = QColor(tokens["accent"])
        selected = f"rgba({accent.red()}, {accent.green()}, {accent.blue()}, 0.20)"
        self.face.setStyleSheet(
            build_dialog_stylesheet(settings=self._real_settings(), tokens=tokens)
            + f"""
        QFrame#loopMixerFace {{ background:{tokens["floating_bg"]}; color:{tokens["text_primary"]};
            border:1px solid {tokens["border_soft"]}; border-radius:14px; }}
        QWidget#loopCardsBody {{background:transparent;}}
        QFrame#loopTrack {{background:{tokens["content_bg"]}; border:1px solid {tokens["border_soft"]}; border-radius:12px;}}
        QPushButton, QComboBox, QLineEdit, QSpinBox {{min-height:36px; font-size:{typography.body_px}px;}}
        QPushButton {{padding:3px 10px;}}
        QPushButton#ghost_btn:checked {{background:{selected}; color:{tokens["text_primary"]}; border:1px solid {tokens["accent"]};}}
        QPushButton#ghost_btn:focus {{border:1px solid {tokens["accent"]};}}
        QComboBox::drop-down {{width:36px; border:0;}}
        QComboBox::down-arrow {{image:none; width:0; height:0;}}
        QLabel {{font-size:{typography.caption_px}px;}}
        QLabel[role="dialogTitle"] {{font-size:{typography.title_px}px; font-weight:700;}}
        QSlider::groove:horizontal {{height:6px; border-radius:3px; background:{tokens["border_soft"]};}}
        QSlider::sub-page:horizontal {{background:{tokens["accent"]}; border-radius:3px;}}
        QSlider::handle:horizontal {{background:{tokens["text_primary"]}; width:26px; height:26px; margin:-11px 0; border-radius:13px;}}
        QProgressBar {{background:{tokens["content_bg"]}; border:0; border-radius:2px;}}
        QProgressBar::chunk {{background:{tokens["accent"]}; border-radius:2px;}}
        """
        )
        for card in self.cards:
            card.wave.accent = QColor(tokens["accent"])
            card.wave.update()
        self.setWindowOpacity(self.widget_opacity())

    def apply_initial_settings(self):
        self._init_loop_deck_instance()

    def _init_loop_deck_instance(self):
        self._apply_appearance()
        screen = self.screen()
        available = screen.availableGeometry() if screen else self.owner.frameGeometry()
        width = min(1120, max(360, available.width() - 40))
        height = min(920, max(480, available.height() - 60))
        self._resize_within_limits(
            self._get("fixed_w", width), self._get("fixed_h", height), persist=True
        )
        self._reflow_for_width()

    def _geometry_limits(self):
        screen = self._placement_screen_override or self.screen()
        available = screen.availableGeometry() if screen else self.owner.frameGeometry()
        width = max(1, min(4096, available.width() - 40))
        height = max(1, min(4096, available.height() - 40))
        dpr = float(self.devicePixelRatioF())
        if not math.isfinite(dpr) or dpr <= 0:
            dpr = 1.0
        # ARGB32 backing-store budget: at most 64 MiB, including high-DPI screens.
        scale = min(
            1.0,
            8192 / (width * dpr),
            8192 / (height * dpr),
            math.sqrt(16 * 1024 * 1024 / (width * height * dpr * dpr)),
        )
        width, height = max(1, int(width * scale)), max(1, int(height * scale))
        return min(360, width), min(480, height), width, height

    def _install_geometry_limits(self):
        limits = self._geometry_limits()
        if self._geometry_guard:
            return limits
        self._geometry_guard = True
        try:
            # An interactive scroll panel owns its outer geometry. Descendant
            # layout minima must never grow its native window during DPI changes.
            if self.layout() is not None:
                self.layout().setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
            minimum = QSize(limits[0], limits[1])
            maximum = QSize(limits[2], limits[3])
            if self.minimumSize() != minimum:
                self.setMinimumSize(minimum)
            if self.maximumSize() != maximum:
                self.setMaximumSize(maximum)
        finally:
            self._geometry_guard = False
        return limits

    def _resize_within_limits(self, width, height, *, persist=False):
        low_w, low_h, high_w, high_h = self._install_geometry_limits()
        try:
            width, height = int(width), int(height)
        except (TypeError, ValueError, OverflowError):
            width, height = 1120, 880
        intended_width, intended_height = width, height
        width, height = max(low_w, min(high_w, width)), max(low_h, min(high_h, height))
        self.resize(width, height)
        if persist:
            # Corrupt native dimensions are repaired; valid user DIP sizes survive
            # a temporary fit on a smaller/DPI-changed monitor.
            self._set("fixed_w", intended_width if 40 <= intended_width <= 4096 else width)
            self._set("fixed_h", intended_height if 40 <= intended_height <= 4096 else height)

    def _release_layout_constraints(self):
        # The base implementation clears every touch-control minimum and the
        # native maximum. Keep those safeguards for this scroll-based panel.
        self._install_geometry_limits()

    def sizeHint(self):  # noqa: N802
        _low_w, _low_h, width, height = self._geometry_limits()
        return QSize(min(1120, width), min(880, height))

    def _fit_font_to_size(self, target_w, target_h, *, live=False):
        del live
        self._resize_within_limits(target_w, target_h, persist=True)

    def _force_resize(self):
        if hasattr(self, "face"):
            self._resize_within_limits(
                self._get("fixed_w", self.width()),
                self._get("fixed_h", self.height()),
                persist=True,
            )

    def _show_with_correct_size(self):
        self._force_resize()
        self.show()
        self._force_resize()
        self.raise_()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "cards"):
            self._install_geometry_limits()
            self._reflow_for_width()

    def _reflow_for_width(self):
        width = self.width()
        mode = (
            3 if width >= 1000 else 2 if width >= 680 else 1,
            width >= 900,
            width >= 680,
            width >= 800,
            width < 500,
        )
        if self._reflowing or mode == self._layout_mode:
            return
        self._layout_mode = mode
        self._reflowing = True
        try:
            self._apply_responsive_layout(width)
        finally:
            self._reflowing = False

    def _apply_responsive_layout(self, width):
        self._reflow(3 if width >= 1000 else 2 if width >= 680 else 1)
        narrow = width < 680
        self.subtitle.setVisible(width >= 900)
        self.sources_label.setVisible(width >= 680)
        self.mic_badge.setVisible(width >= 800)
        self.level.setVisible(width >= 680)
        for index, control in enumerate(
            (self.play_button, self.stop_button, self.record_button, self.bpm, self.bars)
        ):
            self.transport.removeWidget(control)
            self.transport.addWidget(
                control, index // 3 if narrow else 0, index % 3 if narrow else index
            )
        for index, control in enumerate((self.open_button, self.save_button, self.export_button)):
            self.footer.removeWidget(control)
            self.footer.addWidget(control, index if width < 500 else 0, 0 if width < 500 else index)

    def _reflow(self, columns):
        if columns == self._columns:
            return
        for card in self.cards:
            self.grid.removeWidget(card)
        for index, card in enumerate(self.cards):
            self.grid.addWidget(card, index // columns, index % columns)
        for column in range(3):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)
        self._columns = columns

    def eventFilter(self, watched, event):  # noqa: N802
        # Base drag handling must never swallow a button, fader or waveform swipe.
        current = watched
        while isinstance(current, QWidget) and current is not self.face:
            if isinstance(
                current, (QAbstractButton, QComboBox, QSpinBox, QLineEdit, QSlider, QScrollArea)
            ):
                return False
            if current is self.cards_body or current in getattr(self, "cards", []):
                return False
            current = current.parentWidget()
        if event.type() == QEvent.Type.MouseButtonDblClick:
            return False
        return super().eventFilter(watched, event)

    def _manager(self):
        return getattr(self.owner, "overlay_manager", None)

    def _sources(self):
        manager = self._manager()
        decks = manager.instances_of("launcher_deck") if manager is not None else []
        self.sources_label.setText(t("loop_mixer.connected", "키덱 {number}개", number=len(decks)))
        return [
            (t("loop_mixer.source_none", "입력 선택"), "none"),
            (t("loop_mixer.microphone", "마이크"), "mic"),
            (t("loop_mixer.source_file", "WAV 파일"), "file"),
            *[(name, identity) for identity, name, _ in decks],
        ]

    def _run(self, action):
        try:
            result = action()
            if result is False:
                self._notice = self._error_message(self._mixer.snapshot())
                self.status.setText(self._notice)
                return False
            return True
        except (OSError, ValueError, RuntimeError) as error:
            self._notice = t("loop_mixer.error", "확인 필요: {reason}", reason=str(error))
            self.status.setText(self._notice)
            return False

    def _error_message(self, snapshot):
        code = snapshot.get("error_code") or snapshot.get("error")
        errors = {
            "another_mixer_is_playing": (
                "mixer_busy",
                "다른 루프 믹서가 재생 중입니다. 먼저 정지하세요.",
            ),
            "audio_device_error": (
                "device",
                "오디오 장치를 사용할 수 없습니다. 장치 연결과 Windows 마이크 접근 설정을 확인하세요.",
            ),
            "audio_cleanup_failed": (
                "cleanup",
                "오디오 장치를 안전하게 종료하지 못했습니다. 앱을 다시 시작한 뒤 재생하세요.",
            ),
            "audio_device_stopping": (
                "stopping",
                "오디오 장치를 종료 중입니다. 잠시 후 다시 시도하세요.",
            ),
            "sound_unavailable": (
                "sound",
                "키덱의 소리 파일을 읽을 수 없습니다. 키덱의 WAV 파일을 확인하세요.",
            ),
            "no_armed_tracks": ("arm", "입력을 선택하고 트랙의 ‘● 대기’를 먼저 켜세요."),
            "transport_busy": ("stop_first", "재생·녹음을 정지한 뒤 변경하세요."),
            "recording_busy": ("recording", "현재 녹음이 끝난 뒤 변경하세요."),
            "file_operation_busy": ("file_busy", "파일 작업이 끝난 뒤 다시 시도하세요."),
            "invalid_name": ("name", "트랙 이름을 입력하세요."),
        }
        key, fallback = errors.get(
            code,
            (
                "general",
                "처리하지 못했습니다. 입력 파일 형식과 저장 위치, 오디오 장치를 확인하세요.",
            ),
        )
        return t("loop_mixer.errors." + key, fallback)

    def _edit_track(self, index, **values):
        if self._run(lambda: self._mixer.set_track(index, **values)):
            self._mark_dirty()
            self._schedule_save()
        self._refresh_face()

    def _master_changed(self, value):
        self._mixer.set_master_volume(value)
        self._mark_dirty()
        self._schedule_save()

    def _configure(self, *_args):
        if self._run(lambda: self._mixer.configure(self.bpm.value(), self.bars.currentData())):
            self._mark_dirty()
            self._schedule_save()
        self._refresh_face()

    def _play(self):
        self._notice = ""
        self._run(self._mixer.play)
        self._refresh_face()

    def _record(self):
        self._notice = ""
        snapshot = self._mixer.snapshot()
        if not any(
            track.get("armed") and track.get("source") not in ("none", "file", "")
            for track in snapshot["tracks"]
        ):
            self._notice = t(
                "loop_mixer.choose_armed", "입력을 선택하고 트랙의 ‘● 대기’를 켠 뒤 녹음하세요."
            )
        elif (
            not self.overdub.isChecked()
            and any(
                track.get("armed")
                and track.get("source") not in ("none", "file", "")
                and track.get("has_audio")
                for track in snapshot["tracks"]
            )
            and not self._confirm(
                t(
                    "loop_mixer.replace_take",
                    "대기 중인 트랙의 기존 녹음을 새 녹음으로 바꿀까요? 겹쳐 녹음을 켜면 기존 소리를 유지합니다.",
                )
            )
        ):
            return
        elif self._run(lambda: self._mixer.record(overdub=self.overdub.isChecked())):
            self._mark_dirty()
        self._refresh_face()

    def _stop(self):
        self._mixer.stop()
        self._schedule_save()
        self._refresh_face()

    def _schedule_save(self):
        if hasattr(self, "_save"):
            self._save.start()

    def _mark_dirty(self):
        self._dirty = True
        self._revision += 1

    def _submit_io(self, kind, path, action):
        if self._pending_io is not None or self._mixer.snapshot().get("busy"):
            return False
        if not self._run(action):
            return False
        self._pending_io = {
            "id": self._mixer.snapshot().get("operation_id"),
            "kind": kind,
            "path": str(path),
            "revision": self._revision,
        }
        if hasattr(self, "_poll"):
            self._poll.start()
        return True

    def _complete_io(self, snapshot):
        pending = self._pending_io
        if (
            pending is None
            or snapshot.get("busy")
            or snapshot.get("completed_operation_id") != pending["id"]
        ):
            return
        self._pending_io = None
        if not snapshot.get("operation_success"):
            self._notice = self._error_message(snapshot)
            if pending["kind"] == "restore":
                self._autosave_blocked = True
            return
        kind = pending["kind"]
        if kind in ("save", "autosave", "open", "restore"):
            self._set("project_path", pending["path"])
            self._autosave_blocked = False
        if (
            kind in ("save", "autosave")
            and pending["revision"] == self._revision
            or kind in ("open", "restore")
        ):
            self._dirty = False
        elif kind == "load":
            self._mark_dirty()
            self._schedule_save()
        if kind != "autosave":
            self._notice = t(
                "loop_mixer.file_completed",
                "파일 작업을 완료했습니다. 프로젝트는 자동 재생하지 않습니다.",
            )
        if self._dirty and kind in ("save", "autosave"):
            self._schedule_save()

    def _session_path(self):
        stored = self._get("project_path", "")
        if stored:
            return Path(stored)
        # Per-instance identity is metadata, never copied from a different deck.
        identity = getattr(self.owner, "_prefix", None) or self._PREFIX
        identity = "".join(c for c in identity if c.isalnum() or c in "_-+")[:80]
        directory = (
            Path(
                os.environ.get("LOCALAPPDATA")
                or QStandardPaths.writableLocation(
                    QStandardPaths.StandardLocation.GenericDataLocation
                )
            )
            / "DarkCalendar/loop-mixer"
            / identity
        )
        return directory / "session.airloop"

    def _restore_session(self):
        path = self._session_path()
        if path.is_file():
            self._submit_io("restore", path, lambda: self._mixer.load_project(path))
        elif self._get("project_path", ""):
            self._autosave_blocked = True
            self._notice = t(
                "loop_mixer.missing_project",
                "저장된 프로젝트 파일을 찾을 수 없습니다. 파일을 열거나 새 위치에 저장하세요.",
            )

    def _autosave(self):
        if self.isVisible() and (
            self.master.isSliderDown()
            or any(
                card.volume.isSliderDown() or card.pan.isSliderDown() or card.name.hasFocus()
                for card in self.cards
            )
        ):
            self._schedule_save()
            return
        if (
            not self._dirty
            or self._autosave_blocked
            or self._pending_io is not None
            or self._mixer.snapshot()["mode"] == "recording"
        ):
            return
        path = self._session_path()
        if not self._get("project_path", "") and not self._run(
            lambda: path.parent.mkdir(parents=True, exist_ok=True)
        ):
            return
        self._submit_io("autosave", path, lambda: self._mixer.save_project(path))

    def _open_project(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, t("loop_mixer.project_open", "프로젝트 열기"), "", "Air Loop (*.airloop *.json)"
        )
        if not filename:
            return
        if self._dirty and not self._confirm(
            t(
                "loop_mixer.replace_project",
                "현재 프로젝트 대신 선택한 프로젝트를 열까요? 저장하지 않은 변경은 유지되지 않습니다.",
            )
        ):
            return
        self._stop()
        self._submit_io("open", filename, lambda: self._mixer.load_project(Path(filename)))
        self._refresh_face()

    def _save_project_as(self):
        filename, _ = QFileDialog.getSaveFileName(
            self,
            t("loop_mixer.project_save", "프로젝트 저장"),
            "Loop.airloop",
            "Air Loop (*.airloop)",
        )
        if filename and self._submit_io(
            "save", filename, lambda: self._mixer.save_project(Path(filename))
        ):
            self._refresh_face()

    def _export(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, t("loop_mixer.export", "WAV 내보내기"), "Loop-mix.wav", "WAV (*.wav)"
        )
        if filename and self._submit_io(
            "export", filename, lambda: self._mixer.export_wav(Path(filename))
        ):
            self._refresh_face()

    def _load_track(self, index):
        filename, _ = QFileDialog.getOpenFileName(
            self, t("loop_mixer.wav_load", "WAV 담기"), "", "PCM WAV (*.wav)"
        )
        if filename and self._submit_io(
            "load", filename, lambda: self._mixer.load_wav(index, Path(filename))
        ):
            self._refresh_face()

    def _confirm(self, text):
        return (
            QMessageBox.question(
                self,
                t("loop_mixer.title", "루프 믹서"),
                text,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )

    def _clear_track(self, index):
        if self._confirm(
            t("loop_mixer.clear_confirm", "트랙 {number}의 녹음을 비울까요?", number=index + 1)
        ) and self._run(lambda: self._mixer.clear_track(index)):
            self._mark_dirty()
            self._schedule_save()
            self._refresh_face()

    def _refresh_devices(self):
        try:
            devices = self._mixer.microphone_devices()
        except OSError as error:
            self._notice = t("loop_mixer.error", "확인 필요: {reason}", reason=str(error))
            return
        selected = self.mic_combo.currentData()
        self.mic_combo.clear()
        for identity, label in devices:
            self.mic_combo.addItem(
                t("loop_mixer.mic_default", "마이크 · 시스템 기본")
                if identity == "default"
                else label,
                identity,
            )
        self.mic_combo.setCurrentIndex(max(0, self.mic_combo.findData(selected)))
        self._microphone_selected()

    def _microphone_selected(self):
        self._run(lambda: self._mixer.set_microphone_device(self.mic_combo.currentData()))

    def _add_deck_menu(self):
        menu = QMenu(self)
        for bank, label in (
            ("drums", t("loop_mixer.add_drums", "드럼 키덱 추가")),
            ("melody", t("loop_mixer.add_melody", "멜로디 키덱 추가")),
        ):
            menu.addAction(label, lambda _checked=False, selected=bank: self._add_deck(selected))
        menu.exec(self.add_deck_button.mapToGlobal(QPoint(0, self.add_deck_button.height())))

    def _add_deck(self, bank):
        from calendar_app.presentation.widgets.keydeck.beatmaker import (
            BEATMAKER_TEMPLATE_ID,
            apply_beatmaker_preset,
        )
        from calendar_app.presentation.widgets.keydeck.model import build_template_deck

        manager = self._manager()
        if manager is None:
            return
        identity = manager.add_instance("launcher_deck")
        deck = manager.get_widget(identity)
        data = apply_beatmaker_preset(build_template_deck(BEATMAKER_TEMPLATE_ID), "neon", bank)
        deck._apply_deck(data)
        manager.show_instance(identity)
        for index, track in enumerate(self._mixer.snapshot()["tracks"]):
            if track.get("source") == "none":
                self._edit_track(index, source=identity)
                break
        self._source_options = self._sources()
        self._refresh_face()

    def _refresh_face(self):
        if self._mixer is None or not hasattr(self, "cards"):
            return
        snapshot = self._mixer.snapshot()
        self._complete_io(snapshot)
        busy = snapshot.get("busy", False)
        mode = snapshot["mode"]
        running = mode in ("playing", "recording")
        loop_frames = max(1, snapshot.get("loop_frames", 1))
        fraction = snapshot.get("position_frames", 0) / loop_frames
        self._source_refresh_ticks += 1
        if not self._source_options or self._source_refresh_ticks >= 20:
            self._source_options = self._sources()
            self._source_refresh_ticks = 0
        for card, track in zip(self.cards, snapshot["tracks"], strict=True):
            card.sync(track, self._source_options, fraction, running)
            card.setEnabled(not busy)
            card.arm.setEnabled(mode != "recording" and not busy)
        for control in (self.bpm, self.bars, self.mic_combo, self.mic_refresh, self.open_button):
            control.setEnabled(not running and not busy)
        self.record_button.setEnabled(mode != "recording" and not busy)
        self.play_button.setEnabled(not running and not busy)
        self.save_button.setEnabled(not busy and mode != "recording")
        self.export_button.setEnabled(not busy and mode != "recording")
        self.master.setEnabled(not busy)
        self.stop_button.setEnabled(running)
        with QSignalBlocker(self.bpm), QSignalBlocker(self.bars):
            self.bpm.setValue(snapshot.get("bpm", 120))
            self.bars.setCurrentIndex(max(0, self.bars.findData(snapshot.get("bars", 4))))
        if not self.master.isSliderDown():
            with QSignalBlocker(self.master):
                self.master.setValue(snapshot.get("master_volume", 80))
        self.master_value.setText(f"{snapshot.get('master_volume', 80)}%")
        levels = snapshot.get("output_levels", [0, 0])
        self.level.setValue(round(min(1, max(levels or [0])) * 1000))
        self.progress.setValue(round(fraction * 1000))
        recording_mic = mode == "recording" and any(
            track.get("armed") and track.get("source") == "mic" for track in snapshot["tracks"]
        )
        self.mic_badge.setText(
            t("loop_mixer.mic_recording", "● 마이크 녹음 중")
            if recording_mic
            else t("loop_mixer.mic_off", "마이크 꺼짐")
        )
        if self._last_mode == "recording" and mode != "recording":
            self._mark_dirty()
            self._schedule_save()
        self._last_mode = mode
        description = {
            "idle": t("loop_mixer.idle", "준비"),
            "playing": t("loop_mixer.playing", "반복 재생 중"),
            "recording": t("loop_mixer.recording", "한 바퀴 녹음 중"),
        }.get(mode, mode)
        count = sum(bool(track.get("has_audio")) for track in snapshot["tracks"])
        seconds = loop_frames / max(1, snapshot.get("sample_rate", 22050))
        summary = t(
            "loop_mixer.status",
            "{state} · {count}/6 트랙 · {seconds}초",
            state=description,
            count=count,
            seconds=f"{seconds:.1f}",
        )
        hint = (
            t(
                "loop_mixer.idle_hint",
                "입력 선택 → ● 대기 → 녹음. 마이크는 녹음할 때만 켜지며 내 목소리는 즉시 출력하지 않습니다.",
            )
            if not running
            else ""
        )
        self.status.setText(
            t("loop_mixer.file_busy", "파일 작업 중…")
            if busy
            else self._notice
            or (self._error_message(snapshot) if snapshot.get("error") else "")
            or f"{summary}\n{hint}".rstrip()
        )
        if not self.isVisible() and self._pending_io is None and hasattr(self, "_poll"):
            self._poll.stop()

    def _set_runtime_active(self, active):
        if not active and self._mixer is not None:
            for card in self.cards:
                if card.name.hasFocus():
                    card.name.clearFocus()
                card.volume.setSliderDown(False)
                card.pan.setSliderDown(False)
            self.master.setSliderDown(False)
            self._mixer.stop()
            if hasattr(self, "_save"):
                self._save.stop()
                self._autosave()
            if is_app_exiting():
                self._mixer.shutdown()
        if hasattr(self, "_poll"):
            self._poll.start() if (
                active and self.isVisible()
            ) or self._pending_io is not None else self._poll.stop()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if hasattr(self, "_poll"):
            self._poll.start()
        self._refresh_face()

    def hideEvent(self, event):  # noqa: N802
        self._set_runtime_active(False)
        super().hideEvent(event)

    def closeEvent(self, event):  # noqa: N802
        self._set_runtime_active(False)
        self.shutdown()
        super().closeEvent(event)
        event.accept()

    def save_position(self):
        self._resize_within_limits(self.width(), self.height())
        super().save_position()
        # Move/save never promotes Qt's DPI-transition geometry into user intent.
        self._autosave()

    def _open_settings(self, initial_tab=0):
        del initial_tab
        self.set_enabled(True)
        self.raise_()
        self.activateWindow()
        self.bpm.setFocus()

    def shutdown(self):
        if self._shutdown:
            return
        self._set_runtime_active(False)
        self._mixer.shutdown()
        self._poll.stop()
        self._save.stop()
        self._shutdown = True

    def clone_project_from(self, source):
        if not self._run(lambda: self._mixer.clone_from(source._mixer)):
            raise ValueError("Loop mixer project could not be copied")
        self._mark_dirty()
        self._schedule_save()
        self._refresh_face()

    def _show_context_menu(self, global_pos):
        menu = QMenu(self)
        menu.setStyleSheet(self._menu_style() + "QMenu::item {min-height:40px; padding:4px 16px;}")
        self._build_context_menu(menu)
        menu.addSeparator()
        pin = menu.addAction(
            t("widget.menu.always_on_top", "항상 위에"), self._toggle_always_on_top
        )
        pin.setCheckable(True)
        pin.setChecked(self.always_on_top())
        locked = menu.addAction(t("loop_mixer.lock_position", "위치 잠금"))
        locked.setCheckable(True)
        locked.setChecked(self.placement_is_locked())
        locked.toggled.connect(lambda value: self._set("placement_locked", value))
        opacity = menu.addMenu(t("loop_mixer.opacity", "투명도"))
        for value in (100, 90, 80, 70):
            action = opacity.addAction(
                f"{value}%",
                lambda _checked=False, percent=value: self._action_widget_opacity(percent),
            )
            action.setCheckable(True)
            action.setChecked(round(self.widget_opacity() * 100) == value)
        menu.addAction(
            t("loop_mixer.hide_label", "루프 믹서 숨기기"), lambda: self.set_enabled(False)
        )
        menu.exec(global_pos)

    def _build_context_menu(self, menu):
        menu.addAction(t("loop_mixer.stop", "■ 정지"), self._stop)
        menu.addAction(t("loop_mixer.project_open", "프로젝트 열기"), self._open_project)
        menu.addAction(t("loop_mixer.project_save", "저장"), self._save_project_as)
        menu.addAction(t("loop_mixer.export", "WAV 내보내기"), self._export)
