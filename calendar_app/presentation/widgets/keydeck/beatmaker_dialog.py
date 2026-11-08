# -*- coding: utf-8 -*-
"""Focused musical performance; editor text fields never become instrument keys."""

from copy import deepcopy

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
)

from calendar_app.domain.beatmaker_recording import MAX_RECORDING_MS, BeatmakerTimeline
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
)
from calendar_app.presentation.widgets.keydeck.beatmaker import BEATMAKER_KITS, beatmaker_state
from calendar_app.presentation.widgets.keydeck.canvas import KeyDeckCanvas
from calendar_app.presentation.widgets.keydeck.model import normalize_deck, option_label
from calendar_app.presentation.widgets.keydeck.resources import key_sound_paths


class BeatmakerPerformanceDialog(QDialog):
    """Record one sound-only take on a draft and return it to the caller on close."""

    def __init__(self, deck: dict, parent=None, *, clock=None, draft=False):
        super().__init__(parent)
        self.deck = normalize_deck(deepcopy(deck))
        options = {"clock": clock} if clock is not None else {}
        self.timeline = BeatmakerTimeline(self.deck.get("beatmaker_recording"), **options)
        self._missing_sounds = False
        self._finished = False
        self._status_ticks = 0
        self._draft = bool(draft)
        self._looper_dialog = None
        apply_dialog_title(self, t("beatmaker.performance", "연주·녹음"))
        apply_common_dialog_style(self, minimum_width=520, size=(580, 720))
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        hint = QLabel(
            t(
                "beatmaker.performance_hint",
                "1234 / QWER / ASDF / ZXCV로 연주하세요. 녹음은 첫 패드부터 시작하며, 최대 5분까지 기록합니다.",
            ),
            self,
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.page_combo = QComboBox(self)
        self.page_combo.setAccessibleName(t("beatmaker.bank", "연주 종류"))
        for index, page in enumerate(self.deck["pages"]):
            if state := beatmaker_state(page):
                kit = option_label(BEATMAKER_KITS, state["kit"])
                self.page_combo.addItem(f"{page['name']} · {kit}", index)
        selected = self.page_combo.findData(self.deck["page"])
        self.page_combo.setCurrentIndex(max(0, selected))
        if self.page_combo.count():
            self.deck["page"] = self.page_combo.currentData()
        self.page_combo.activated.connect(self._page_changed)
        bank_row = QHBoxLayout()
        bank_row.addWidget(self.page_combo, 1)
        self.looper_button = self._button(
            t("loop_mixer.open", "루프 믹서 위젯 열기"), self._open_looper
        )
        bank_row.addWidget(self.looper_button)
        root.addLayout(bank_row)

        self.canvas = KeyDeckCanvas(self)
        self.canvas.close_control_enabled = False
        self.canvas.set_geometry_overrides(scale=1.0, header=False)
        self.canvas.set_deck(self.deck)
        self.canvas.set_keyboard_performance(True)
        self.canvas.padTriggered.connect(self._record_pad)
        self.canvas.performanceStopped.connect(self.reject)
        self.canvas.pageRequested.connect(self._navigate_page)
        # Header editing and key actions deliberately have no handlers in this player.
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.canvas)
        root.addWidget(scroll, 1)

        transport = QHBoxLayout()
        self.record_button = self._button(t("beatmaker.record", "● 녹음"), self._record)
        self.record_button.setObjectName("danger_btn")
        self.play_button = self._button(t("beatmaker.play", "▶ 재생"), self._play)
        self.play_button.setObjectName("primary_btn")
        self.stop_button = self._button(t("beatmaker.stop", "■ 정지"), self._stop)
        self.clear_button = self._button(t("beatmaker.clear", "녹음 삭제"), self._clear)
        for button in (self.record_button, self.play_button, self.stop_button, self.clear_button):
            transport.addWidget(button)
        root.addLayout(transport)
        row = QHBoxLayout()
        self.loop_check = QCheckBox(t("beatmaker.repeat", "반복 재생"), self)
        self.loop_check.setChecked(True)
        self.loop_check.toggled.connect(self._repeat_changed)
        row.addWidget(self.loop_check)
        self.status = QLabel(self)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        row.addWidget(self.status, 1)
        root.addLayout(row)

        volume_row = QHBoxLayout()
        self.sound_check = QCheckBox(t("beatmaker.sound_on", "소리 켜기"), self)
        self.sound_check.setChecked(self.deck["sound_enabled"])
        self.sound_check.toggled.connect(self._sound_changed)
        volume_row.addWidget(self.sound_check)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.deck["sound_volume"])
        self.volume_slider.setAccessibleName(t("beatmaker.volume", "연주 음량"))
        self.volume_slider.valueChanged.connect(self._volume_changed)
        self.volume_slider.sliderReleased.connect(self._focus_pads)
        volume_row.addWidget(self.volume_slider, 1)
        self.volume_label = QLabel(self)
        volume_row.addWidget(self.volume_label)
        root.addLayout(volume_row)
        self.warning = QLabel(self)
        self.warning.setWordWrap(True)
        self.warning.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.warning)
        note = QLabel(
            t(
                "beatmaker.recording_draft_note",
                "패드 소리와 타이밍을 녹음합니다(마이크 녹음 아님). 마지막 녹음 1개를 보관하며, 스튜디오에서 적용해야 저장됩니다.",
            )
            if draft
            else t(
                "beatmaker.recording_note",
                "패드 소리와 타이밍을 녹음합니다(마이크 녹음 아님). 마지막 녹음 1개를 보관하며, 닫으면 녹음과 음량이 저장됩니다.",
            ),
            self,
        )
        note.setWordWrap(True)
        root.addWidget(note)
        footer, close_button, _ = build_dialog_footer(t("common.close", "닫기"), None)
        close_button.clicked.connect(self.accept)
        close_button.setAutoDefault(False)
        close_button.setDefault(False)
        root.addLayout(footer)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(10)
        self.timer.timeout.connect(self._tick)
        self._refresh()

    def _button(self, text, callback):
        button = QPushButton(text, self)
        button.setObjectName("ghost_btn")
        button.setAutoDefault(False)
        button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        button.clicked.connect(callback)
        return button

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self._focus_pads)

    def _focus_pads(self):
        if not self._finished and self.isVisible():
            self.canvas.setFocus(Qt.FocusReason.OtherFocusReason)

    def _page_changed(self):
        self.deck["page"] = self.page_combo.currentData()
        self.canvas.set_deck(self.deck)
        self._focus_pads()

    def _open_looper(self):
        from calendar_app.presentation.widgets.overlay_launcher_deck import open_loop_mixer_widget
        from calendar_app.shared.app_lifecycle import is_app_exiting

        if self._finished or is_app_exiting():
            return
        self._stop()
        open_loop_mixer_widget(self)

    def _navigate_page(self, index):
        selected = self.page_combo.findData(index)
        if selected >= 0:
            self.page_combo.setCurrentIndex(selected)
            self._page_changed()

    def _record(self):
        if self._finished:
            return
        if (
            self.timeline.take
            and QMessageBox.question(
                self,
                t("beatmaker.record", "● 녹음"),
                t(
                    "beatmaker.replace_recording",
                    "새 연주를 녹음할까요? 패드를 누른 뒤 정지하면 이전 녹음이 교체됩니다.",
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        if self._finished:
            return
        self._stop()
        self._missing_sounds = False
        self.timeline.start_recording()
        self.timer.start()
        self._refresh()
        self._focus_pads()

    def _record_pad(self, key_id):
        if self.timeline.mode != "recording":
            return
        key = next(
            (key for key in self.deck["pages"][self.deck["page"]]["keys"] if key["id"] == key_id),
            None,
        )
        if key is None:
            return
        sound = key["sound"]
        source = key
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
            self._refresh()
            return
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
        if self._finished:
            return
        self._stop()
        self._missing_sounds = False
        if self.timeline.play(repeat=self.loop_check.isChecked()):
            self.timer.start()
            self._tick()
        self._refresh()
        self._focus_pads()

    def _stop(self):
        self.timer.stop()
        self.timeline.stop()
        self.canvas.stop_sounds()
        self._refresh()
        self._focus_pads()

    def _clear(self):
        if self._finished:
            return
        if (
            QMessageBox.question(
                self,
                t("beatmaker.clear", "녹음 삭제"),
                t("beatmaker.clear_confirm", "저장된 녹음을 삭제할까요?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        if self._finished:
            return
        self._stop()
        self.timeline.clear()
        self._missing_sounds = False
        self._refresh()

    def _repeat_changed(self, enabled):
        self.timeline.repeat = enabled
        self._focus_pads()

    def _sound_changed(self, enabled):
        self.deck["sound_enabled"] = enabled
        if not enabled:
            self.canvas.stop_sounds()
        self._refresh()
        self._focus_pads()

    def _volume_changed(self, value):
        self.deck["sound_volume"] = value
        if not value:
            self.canvas.stop_sounds()
        self._refresh()

    def _tick(self):
        before = self.timeline.mode
        missing_before = self._missing_sounds
        for event in self.timeline.due_events():
            if not self.canvas.play_recorded_pad(event):
                self._missing_sounds = True
        if self.timeline.mode == "idle":
            self.timer.stop()
            if before != "idle":
                self.canvas.stop_sounds()
        self._status_ticks = (self._status_ticks + 1) % 10
        if (
            not self._status_ticks
            or before != self.timeline.mode
            or missing_before != self._missing_sounds
        ):
            self._refresh()

    def _refresh(self):
        mode = self.timeline.mode
        take = self.timeline.take
        labels = {
            "idle": t("beatmaker.ready", "대기"),
            "recording": t("beatmaker.recording", "녹음 중"),
            "playing": t("beatmaker.playing", "재생 중"),
        }
        duration = MAX_RECORDING_MS if mode == "recording" else take["duration_ms"] if take else 0
        count = self.timeline.event_count
        self.status.setText(
            t(
                "beatmaker.transport_status",
                "{state} · {position}s / {duration}s · {count}타",
                state=labels[mode],
                position=f"{self.timeline.position_ms / 1000:.1f}",
                duration=f"{duration / 1000:.1f}",
                count=count,
            )
        )
        self.record_button.setEnabled(mode != "recording")
        self.play_button.setEnabled(take is not None and mode == "idle")
        self.stop_button.setEnabled(mode != "idle")
        self.clear_button.setEnabled(take is not None and mode == "idle")
        # Repeat mode is selected before playback, so switching it never jumps in time.
        self.loop_check.setEnabled(mode == "idle")
        self.volume_label.setText(f"{self.deck['sound_volume']}%")
        if not self.deck["sound_enabled"] or not self.deck["sound_volume"]:
            message = t(
                "beatmaker.muted_hint",
                "소리가 꺼져 있습니다. ‘소리 켜기’를 켜고 음량을 높여주세요.",
            )
        elif self._missing_sounds:
            message = t(
                "beatmaker.missing_hint",
                "무음 패드 또는 사용할 수 없는 음원이 있습니다. 해당 패드의 소리 설정과 WAV 파일을 확인하세요.",
            )
        elif self.timeline.limited:
            message = t(
                "beatmaker.recording_limit",
                "녹음 한도(5분 또는 4,096타)에 도달해 자동 정지했습니다.",
            )
        else:
            message = ""
        self.warning.setText(message)
        self.warning.setVisible(bool(message))

    def result_performance(self):
        result = {
            "beatmaker_recording": deepcopy(self.timeline.take),
            "sound_enabled": self.deck["sound_enabled"],
            "sound_volume": self.deck["sound_volume"],
        }
        if self.deck.get("beatmaker_looper") is not None:
            result["beatmaker_looper"] = deepcopy(self.deck["beatmaker_looper"])
        return result

    def done(self, result):
        if not self._finished:
            self._finished = True
            if self._looper_dialog is not None:
                self._looper_dialog.reject()
            self._stop()
            self.canvas.set_keyboard_performance(False)
        super().done(result)

    def hideEvent(self, event):  # noqa: N802
        # Native hide/parent teardown must not leave a background loop running.
        if hasattr(self, "timer"):
            if self._looper_dialog is not None:
                self._looper_dialog.reject()
            self._stop()
        super().hideEvent(event)
