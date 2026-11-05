# -*- coding: utf-8 -*-
"""Four sound-only pad layers with an explicit, shared loop transport."""

from copy import deepcopy

from PyQt6.QtCore import QEvent, QSignalBlocker, Qt, QTimer
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QBoxLayout,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from calendar_app.domain.beatmaker_looper import (
    TICKS_PER_BEAT,
    TRACK_COUNT,
    BeatmakerLooperTimeline,
    default_looper,
    normalize_looper,
)
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
    get_dialog_theme_tokens,
)
from calendar_app.presentation.widgets.keydeck.beatmaker import BEATMAKER_KITS, beatmaker_state
from calendar_app.presentation.widgets.keydeck.canvas import KeyDeckCanvas
from calendar_app.presentation.widgets.keydeck.model import normalize_deck, option_label
from calendar_app.presentation.widgets.keydeck.resources import key_sound_paths
from calendar_app.shared.app_lifecycle import is_app_exiting
from calendar_app.shared.icon_map import ICON
from calendar_app.shared.icon_map import icon as _ic


class BeatmakerLooperDialog(QDialog):
    """Edit loop layers on a private draft; audio starts only after user input."""

    def __init__(self, deck, parent=None, *, clock=None, draft=False):
        super().__init__(parent)
        self.deck = normalize_deck(deepcopy(deck))
        self._had_looper = normalize_looper(self.deck.get("beatmaker_looper")) is not None
        self.timeline = BeatmakerLooperTimeline(
            self.deck.get("beatmaker_looper"), **({"clock": clock} if clock is not None else {})
        )
        self._selected_track = 0
        self._finished = False
        self._missing_sounds = False
        self._status_ticks = 0
        self._last_mode = "idle"
        apply_dialog_title(self, t("beatmaker.looper.title", "루프덱"))
        apply_common_dialog_style(self, minimum_width=560, size=(880, 900))
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(8)
        scroll = QScrollArea(self)
        scroll.setObjectName("beatmakerLooperScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.workspace_scroll = scroll
        scroll.viewport().setObjectName("beatmakerLooperViewport")
        scroll.viewport().installEventFilter(self)
        body = QWidget(scroll)
        body.setObjectName("beatmakerLooperBody")
        self.workspace_body = body
        content = QBoxLayout(QBoxLayout.Direction.LeftToRight, body)
        self.workspace_layout = content
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(12)
        hint = QLabel(
            t(
                "beatmaker.looper.hint",
                "트랙을 선택하고 녹음을 누른 뒤 패드를 연주하세요. 다음 트랙에 소리를 더해 루프를 쌓습니다.",
            ),
            body,
        )
        hint.setWordWrap(True)
        root.addWidget(hint)
        self.page_combo = QComboBox(body)
        self.page_combo.setObjectName("looperBank")
        self.page_combo.setAccessibleName(t("beatmaker.bank", "연주 종류"))
        for index, page in enumerate(self.deck["pages"]):
            if state := beatmaker_state(page):
                self.page_combo.addItem(
                    f"{page['name']} · {option_label(BEATMAKER_KITS, state['kit'])}", index
                )
        self.page_combo.setCurrentIndex(max(0, self.page_combo.findData(self.deck["page"])))
        if self.page_combo.count():
            self.deck["page"] = self.page_combo.currentData()
        self.page_combo.activated.connect(self._page_changed)
        self._build_grid_controls(root, self)
        self.canvas = KeyDeckCanvas(body)
        self.canvas.setObjectName("looperPadCanvas")
        self.canvas.close_control_enabled = False
        self.canvas.set_geometry_overrides(scale=1.0, header=False)
        self.canvas.set_deck(self.deck)
        self.canvas.set_keyboard_performance(True)
        self.canvas.padTriggered.connect(self._record_pad)
        self.canvas.performanceStopped.connect(self.reject)
        self.canvas.pageRequested.connect(self._navigate_page)
        content.addWidget(self.canvas, 1)
        self._build_tracks(content, body)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)
        transport = QGridLayout()
        self.transport_layout = transport
        self._transport_inline = True
        self.record_button = self._button(
            t("beatmaker.looper.record", "선택 트랙 녹음"), self._record
        )
        self.record_button.setObjectName("danger_btn")
        self.play_button = self._button(t("beatmaker.play", "▶ 재생"), self._play)
        self.play_button.setObjectName("primary_btn")
        self.stop_button = self._button(t("beatmaker.stop", "■ 정지"), self._stop)
        for column, button in enumerate((self.record_button, self.play_button, self.stop_button)):
            transport.addWidget(button, 0, column)
            transport.setColumnStretch(column, 1)
        self.overdub_check = QCheckBox(t("beatmaker.looper.overdub", "겹쳐 녹음"), body)
        self.overdub_check.setObjectName("looperOverdub")
        self.overdub_check.setChecked(True)
        transport.addWidget(self.overdub_check, 0, 3)
        root.addLayout(transport)
        auto_note = t(
            "beatmaker.looper.auto_loop_note",
            "첫 패드부터 한 바퀴 녹음하면 자동으로 반복 재생합니다.",
        )
        self.record_button.setToolTip(auto_note)
        self.record_button.setAccessibleDescription(auto_note)
        self.progress = QProgressBar(body)
        self.progress.setObjectName("looperPosition")
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        root.addWidget(self.progress)
        self.status = QLabel(body)
        self.status.setObjectName("looperStatus")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        volume = QHBoxLayout()
        self.sound_check = QCheckBox(t("beatmaker.sound_on", "소리 켜기"), body)
        self.sound_check.setChecked(self.deck["sound_enabled"])
        self.sound_check.toggled.connect(self._sound_changed)
        volume.addWidget(self.sound_check)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal, body)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.deck["sound_volume"])
        self.volume_slider.setAccessibleName(t("beatmaker.volume", "연주 음량"))
        self.volume_slider.valueChanged.connect(self._volume_changed)
        self.volume_slider.sliderReleased.connect(self._focus_pads)
        volume.addWidget(self.volume_slider, 1)
        self.volume_label = QLabel(body)
        volume.addWidget(self.volume_label)
        self.warning = QLabel(body)
        self.warning.setTextFormat(Qt.TextFormat.PlainText)
        self.warning.setWordWrap(True)
        root.addWidget(self.warning)
        note = (
            t(
                "beatmaker.looper.draft_note",
                "마이크 입력 없이 패드 소리와 박자를 겹칩니다. 스튜디오에서 적용하면 루프와 음량이 저장됩니다.",
            )
            if draft
            else t(
                "beatmaker.looper.note",
                "마이크 입력 없이 패드 소리와 박자를 겹칩니다. 닫으면 루프와 음량이 저장됩니다.",
            )
        )
        footer, close_button, _ = build_dialog_footer(t("common.close", "닫기"), None)
        self.close_button = close_button
        close_button.setToolTip(note)
        close_button.setAccessibleDescription(note)
        if footer.count() and footer.itemAt(0).spacerItem() is not None:
            footer.takeAt(0)
        footer.insertLayout(0, volume, 1)
        close_button.setAutoDefault(False)
        close_button.setDefault(False)
        close_button.clicked.connect(self.accept)
        root.addLayout(footer)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(10)
        self.timer.timeout.connect(self._tick)
        self._apply_reading_surface()
        self._refresh()

    def _apply_reading_surface(self):
        tokens = get_dialog_theme_tokens(settings=getattr(self, "_dc_chrome_settings", None))
        background = tokens["content_bg"]
        self.workspace_scroll.setStyleSheet(
            "QScrollArea#beatmakerLooperScroll, QWidget#beatmakerLooperViewport, "
            "QWidget#beatmakerLooperBody {"
            f"background-color: {background}; border: none;"
            "} QWidget#looperPadCanvas { background: transparent; border: none; }"
        )
        for widget in (self.workspace_scroll.viewport(), self.workspace_body):
            palette = widget.palette()
            color = QColor(background)
            if color.isValid():
                palette.setColor(QPalette.ColorRole.Window, color)
                palette.setColor(QPalette.ColorRole.Base, color)
            widget.setPalette(palette)
            widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.canvas.setAutoFillBackground(False)
        foreground = QColor(tokens["text_primary"])
        icon_color = foreground.name() if foreground.isValid() else "#6b7482"
        for *_controls, clear in self.track_controls:
            clear.setIcon(_ic(ICON.DELETE, color=icon_color))
        self.progress.setStyleSheet(
            "QProgressBar#looperPosition {"
            f"background-color: {tokens['input_bg']}; border: 1px solid {tokens['border_soft']}; "
            f"selection-background-color: {tokens['accent']}; "
            "border-radius: 3px; padding: 0;"
            "} QProgressBar#looperPosition::chunk {"
            f"background-color: {tokens['accent']}; border: none; border-radius: 2px;"
            "}"
        )
        palette = self.progress.palette()
        palette.setColor(QPalette.ColorRole.Highlight, QColor(tokens["accent"]))
        palette.setColor(QPalette.ColorRole.Base, QColor(tokens["input_bg"]))
        palette.setColor(QPalette.ColorRole.Window, QColor(tokens["input_bg"]))
        self.progress.setPalette(palette)

    def _fit_workspace(self):
        if not hasattr(self, "workspace_layout") or not hasattr(self, "_mixer_group"):
            return
        self._fit_settings()
        self._fit_transport()
        minimum_width = (
            self.canvas.sizeHint().width()
            + self._mixer_group.minimumSizeHint().width()
            + self.workspace_layout.spacing()
        )
        direction = (
            QBoxLayout.Direction.LeftToRight
            if self.workspace_scroll.viewport().width() >= minimum_width
            else QBoxLayout.Direction.TopToBottom
        )
        self.workspace_layout.setDirection(direction)
        self.canvas.setMinimumSize(self.canvas.sizeHint())

    def _fit_transport(self):
        if not hasattr(self, "overdub_check"):
            return
        buttons = (self.record_button, self.play_button, self.stop_button)
        minimum = sum(button.minimumSizeHint().width() for button in buttons)
        minimum += self.overdub_check.minimumSizeHint().width() + 24
        inline = self.width() - 32 >= minimum
        if inline != self._transport_inline:
            self._transport_inline = inline
            self.transport_layout.removeWidget(self.overdub_check)
            if inline:
                self.transport_layout.addWidget(self.overdub_check, 0, 3)
            else:
                self.transport_layout.addWidget(self.overdub_check, 1, 0, 1, 3)

    def _fit_settings(self):
        minimum_width = sum(
            max(label.minimumSizeHint().width(), control.minimumSizeHint().width())
            for label, control in self._settings_items
        )
        columns = 4 if self.width() - 64 >= minimum_width + 24 else 2
        if columns == self._settings_columns:
            return
        self._settings_columns = columns
        while self._settings_grid.count():
            self._settings_grid.takeAt(0)
        for column in range(4):
            self._settings_grid.setColumnStretch(column, 0)
        for index, (label, control) in enumerate(self._settings_items):
            row, column = 2 * (index // columns), index % columns
            self._settings_grid.addWidget(label, row, column)
            self._settings_grid.addWidget(control, row + 1, column)
            self._settings_grid.setColumnStretch(column, 1)

    def eventFilter(self, watched, event):
        if (
            hasattr(self, "workspace_scroll")
            and watched is self.workspace_scroll.viewport()
            and event.type() == QEvent.Type.Resize
        ):
            self._fit_workspace()
        return super().eventFilter(watched, event)

    def _button(self, text, callback):
        button = QPushButton(text, self)
        button.setObjectName("ghost_btn")
        button.setAutoDefault(False)
        button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        button.clicked.connect(callback)
        return button

    def _build_grid_controls(self, layout, parent):
        group = QGroupBox(t("beatmaker.looper.settings", "루프 설정"), parent)
        form = QGridLayout(group)
        form.setContentsMargins(12, 6, 12, 6)
        form.setVerticalSpacing(4)
        self._settings_grid = form
        self._settings_items = []
        self._settings_columns = 4
        self.bpm_spin = QSpinBox(group)
        self.bpm_spin.setObjectName("looperBpm")
        self.bpm_spin.setRange(40, 240)
        self.bpm_spin.setKeyboardTracking(False)
        self.bpm_spin.setValue(self.timeline.data["bpm"])
        self.bars_combo = QComboBox(group)
        self.bars_combo.setObjectName("looperBars")
        for count in (1, 2, 4, 8):
            self.bars_combo.addItem(
                t("beatmaker.looper.bars_value", "{count}마디", count=count), count
            )
        self.bars_combo.setCurrentIndex(self.bars_combo.findData(self.timeline.data["bars"]))
        self.quantize_combo = QComboBox(group)
        self.quantize_combo.setObjectName("looperQuantize")
        self.quantize_combo.addItem(t("beatmaker.looper.quantize_sixteenth", "16분음표"), "1/16")
        self.quantize_combo.addItem(t("beatmaker.looper.quantize_off", "끄기"), "off")
        self.quantize_combo.setCurrentIndex(
            self.quantize_combo.findData(self.timeline.data["quantize"])
        )
        for column, (text, control) in enumerate(
            (
                (t("beatmaker.looper.bpm", "BPM"), self.bpm_spin),
                (t("beatmaker.looper.bars", "길이"), self.bars_combo),
                (t("beatmaker.looper.quantize", "박자 맞춤"), self.quantize_combo),
                (t("beatmaker.bank", "연주 종류"), self.page_combo),
            )
        ):
            label = QLabel(text, group)
            label.setBuddy(control)
            control.setAccessibleName(text)
            form.addWidget(label, 0, column)
            form.addWidget(control, 1, column)
            form.setColumnStretch(column, 1)
            self._settings_items.append((label, control))
        self.bpm_spin.valueChanged.connect(self._grid_changed)
        self.bars_combo.activated.connect(self._grid_changed)
        self.quantize_combo.activated.connect(self._grid_changed)
        layout.addWidget(group)

    def _build_tracks(self, layout, parent):
        group = QGroupBox(t("beatmaker.looper.tracks", "트랙"), parent)
        self._mixer_group = group
        rows = QVBoxLayout(group)
        self.track_group = QButtonGroup(self)
        self.track_controls = []
        for index in range(TRACK_COUNT):
            row = QFrame(group)
            row.setObjectName("looperTrackRow")
            grid = QGridLayout(row)
            grid.setContentsMargins(4, 4, 4, 4)
            grid.setHorizontalSpacing(6)
            select = QRadioButton(self._track_name(index), row)
            select.setObjectName(f"looperTrackSelect{index}")
            self.track_group.addButton(select, index)
            select.setChecked(index == 0)
            summary = QLabel(row)
            summary.setObjectName(f"looperTrackCount{index}")
            mute = QCheckBox(t("beatmaker.looper.mute", "음소거"), row)
            mute.setObjectName(f"looperTrackMute{index}")
            clear = QToolButton(row)
            clear.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            clear.clicked.connect(lambda _checked=False, track=index: self._clear_track(track))
            clear.setObjectName(f"looperTrackClear{index}")
            clear.setAccessibleName(
                t("beatmaker.looper.clear_named", "{track} 지우기", track=self._track_name(index))
            )
            clear.setToolTip(clear.accessibleName())
            gain = QSlider(Qt.Orientation.Horizontal, row)
            gain.setObjectName(f"looperTrackVolume{index}")
            gain.setRange(0, 100)
            gain.setMinimumWidth(56)
            gain.setAccessibleName(
                t("beatmaker.looper.track_volume", "{track} 음량", track=self._track_name(index))
            )
            value = QLabel(row)
            grid.addWidget(select, 0, 0)
            grid.addWidget(summary, 0, 1)
            grid.addWidget(mute, 0, 2)
            grid.addWidget(gain, 0, 3)
            grid.addWidget(value, 0, 4)
            grid.addWidget(clear, 0, 5)
            grid.setColumnStretch(3, 1)
            mute.toggled.connect(lambda enabled, track=index: self._track_muted(track, enabled))
            gain.valueChanged.connect(lambda level, track=index: self._track_volume(track, level))
            gain.sliderReleased.connect(self._focus_pads)
            self.track_controls.append((select, summary, mute, gain, value, clear))
            rows.addWidget(row)
        self.track_group.idClicked.connect(self._select_track)
        rows.addStretch(1)
        layout.addWidget(group)

    def _track_name(self, index):
        return t("beatmaker.looper.track_name", "트랙 {number}", number=index + 1)

    def _select_track(self, index):
        self._selected_track = index
        self._refresh()

    def _grid_changed(self, *_args):
        options = dict(
            bpm=self.bpm_spin.value(),
            bars=self.bars_combo.currentData(),
            quantize=self.quantize_combo.currentData(),
        )
        if not self.timeline.configure(**options) and (
            self.timeline.mode == "idle"
            and QMessageBox.question(
                self,
                t("beatmaker.looper.shorten_title", "루프 길이 줄이기"),
                t(
                    "beatmaker.looper.shorten_confirm",
                    "새 길이를 벗어난 소리는 삭제됩니다. 길이를 줄일까요?",
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
            and not self._finished
            and not is_app_exiting()
        ):
            self.timeline.configure(**options, truncate=True)
        if self._finished or is_app_exiting():
            return
        self._sync_grid_controls()
        self._refresh()

    def _sync_grid_controls(self):
        for control, value, combo in (
            (self.bpm_spin, self.timeline.data["bpm"], False),
            (self.bars_combo, self.timeline.data["bars"], True),
            (self.quantize_combo, self.timeline.data["quantize"], True),
        ):
            blocker = QSignalBlocker(control)
            if combo:
                control.setCurrentIndex(control.findData(value))
            else:
                control.setValue(value)
            del blocker

    def _record(self):
        if self._finished or is_app_exiting():
            return
        track = self.timeline.data["tracks"][self._selected_track]
        if (
            track["events"]
            and not self.overdub_check.isChecked()
            and (
                QMessageBox.question(
                    self,
                    t("beatmaker.looper.replace_title", "트랙 다시 녹음"),
                    t(
                        "beatmaker.looper.replace_confirm",
                        "{track}을 새 연주로 바꿀까요? 빈 녹음은 기존 연주를 유지합니다.",
                        track=self._track_name(self._selected_track),
                    ),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                != QMessageBox.StandardButton.Yes
            )
        ):
            return
        if self._finished or is_app_exiting():
            return
        self._missing_sounds = False
        self.timeline.arm_recording(self._selected_track, overdub=self.overdub_check.isChecked())
        self.timer.start()
        self._tick()
        self._focus_pads()

    def _record_pad(self, key_id):
        if self.timeline.mode not in {"armed", "recording"}:
            return
        key = next(
            (key for key in self.deck["pages"][self.deck["page"]]["keys"] if key["id"] == key_id),
            None,
        )
        if key is None:
            return
        sound, source = key["sound"], key
        if sound == "auto":
            sound, source = self.deck["sound"], self.deck
        path, _release = key_sound_paths(key, self.deck)
        if (
            not path
            or sound in {"none", "auto", "switch"}
            or not self.deck["sound_enabled"]
            or not self.deck["sound_volume"]
            or not key["sound_volume"]
        ):
            self._missing_sounds = True
        else:
            self.timeline.append(
                {
                    "sound": sound,
                    "sound_path": source["sound_path"] if sound == "custom" else "",
                    "volume": key["sound_volume"],
                    "key_id": key_id,
                }
            )
        self._refresh()

    def _play(self):
        if not self._finished and not is_app_exiting() and self.timeline.play():
            self.timer.start()
            self._tick()
            self._focus_pads()

    def _stop(self):
        self.timer.stop()
        self.timeline.stop()
        self.canvas.stop_sounds()
        self._refresh()
        self._focus_pads()

    def _clear_track(self, index):
        if self._finished or is_app_exiting():
            return
        if (
            QMessageBox.question(
                self,
                t("beatmaker.looper.clear", "지우기"),
                t(
                    "beatmaker.looper.clear_confirm",
                    "{track}의 모든 소리를 지울까요?",
                    track=self._track_name(index),
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
            and not self._finished
            and not is_app_exiting()
        ):
            self.timeline.clear_track(index)
            self._refresh()

    def _track_muted(self, index, enabled):
        self.timeline.set_track_muted(index, enabled)
        self._refresh()

    def _track_volume(self, index, value):
        self.timeline.set_track_volume(index, value)
        self._refresh()

    def _sound_changed(self, enabled):
        self.deck["sound_enabled"] = enabled
        if not enabled:
            self.canvas.stop_sounds()
        self._refresh()

    def _volume_changed(self, value):
        self.deck["sound_volume"] = value
        if not value:
            self.canvas.stop_sounds()
        self._refresh()

    def _page_changed(self):
        self.deck["page"] = self.page_combo.currentData()
        self.canvas.set_deck(self.deck)
        self._fit_workspace()
        self._focus_pads()

    def _navigate_page(self, index):
        selected = self.page_combo.findData(index)
        if selected >= 0:
            self.page_combo.setCurrentIndex(selected)
            self._page_changed()

    def _tick(self):
        before = self._last_mode
        for event in self.timeline.due_events():
            if not self.canvas.play_recorded_pad(event):
                self._missing_sounds = True
        if self.timeline.mode == "idle":
            self.timer.stop()
        self._status_ticks = (self._status_ticks + 1) % 10
        if not self._status_ticks or before != self.timeline.mode:
            self._refresh()
        self.progress.setValue(int(self.timeline.position_ticks))

    def _refresh(self):
        if not hasattr(self, "timer"):
            return
        mode = self.timeline.mode
        self._last_mode = mode
        capturing = mode in {"armed", "recording"}
        has_events = any(track["events"] for track in self.timeline.data["tracks"])
        for control in (self.bpm_spin, self.bars_combo, self.quantize_combo):
            control.setEnabled(mode == "idle")
        self.record_button.setEnabled(not capturing and bool(self.page_combo.count()))
        self.play_button.setEnabled(mode == "idle" and has_events)
        self.stop_button.setEnabled(mode != "idle")
        self.overdub_check.setEnabled(not capturing)
        for index, (select, summary, mute, gain, value, clear) in enumerate(self.track_controls):
            track = self.timeline.data["tracks"][index]
            select.setEnabled(not capturing)
            count = self.timeline.track_event_count(index)
            summary.setText(
                t("beatmaker.looper.hit_count", "{count}타", count=count)
                if count
                else t("beatmaker.looper.empty", "비어 있음")
            )
            for control, setting in ((mute, track["muted"]), (gain, track["volume"])):
                blocker = QSignalBlocker(control)
                if isinstance(control, QCheckBox):
                    control.setChecked(setting)
                else:
                    control.setValue(setting)
                del blocker
            value.setText(f"{track['volume']}%")
            clear.setEnabled(bool(track["events"]) and not capturing)
        track_name = self._track_name(self.timeline.record_track or 0)
        state = {
            "idle": t("beatmaker.ready", "대기"),
            "armed": t("beatmaker.looper.armed", "첫 패드를 기다리는 중"),
            "recording": t("beatmaker.looper.recording", "{track} 녹음 중", track=track_name),
            "playing": t("beatmaker.looper.playing", "루프 재생 중"),
        }[mode]
        position = int(self.timeline.position_ticks)
        self.progress.setRange(0, self.timeline.loop_ticks)
        self.progress.setValue(position)
        self.status.setText(
            t(
                "beatmaker.looper.status",
                "{state} · {bar}/{bars}마디 · {beat}/4박 · {count}타",
                state=state,
                bar=position // (4 * TICKS_PER_BEAT) + 1,
                bars=self.timeline.data["bars"],
                beat=position // TICKS_PER_BEAT % 4 + 1,
                count=self.timeline.event_count,
            )
        )
        self.volume_label.setText(f"{self.deck['sound_volume']}%")
        if not self.deck["sound_enabled"] or not self.deck["sound_volume"]:
            warning = t(
                "beatmaker.muted_hint",
                "소리가 꺼져 있습니다. ‘소리 켜기’를 켜고 음량을 높여주세요.",
            )
        elif self._missing_sounds:
            warning = t(
                "beatmaker.missing_hint",
                "무음 패드 또는 사용할 수 없는 음원이 있습니다. 해당 패드의 소리 설정과 WAV 파일을 확인하세요.",
            )
        elif self.timeline.limited:
            warning = t(
                "beatmaker.looper.limit",
                "한도에 도달해 녹음을 마쳤습니다. 다른 트랙을 사용하거나 정리한 뒤 다시 녹음하세요.",
            )
        else:
            warning = ""
        self.warning.setText(warning)
        self.warning.setVisible(bool(warning))

    def result_performance(self):
        data = deepcopy(self.timeline.data)
        return {
            "beatmaker_looper": data if self._had_looper or data != default_looper() else None,
            "sound_enabled": self.deck["sound_enabled"],
            "sound_volume": self.deck["sound_volume"],
        }

    def _focus_pads(self):
        if not self._finished and self.isVisible():
            self.canvas.setFocus(Qt.FocusReason.OtherFocusReason)

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if not self._finished:
            self.canvas.set_keyboard_performance(True)
        self._fit_workspace()
        QTimer.singleShot(0, self._focus_pads)

    def done(self, result):
        if not self._finished:
            self._finished = True
            self._stop()
            self.canvas.set_keyboard_performance(False)
        super().done(result)

    def hideEvent(self, event):  # noqa: N802
        if hasattr(self, "timer"):
            self._stop()
            self.canvas.set_keyboard_performance(False)
        super().hideEvent(event)
