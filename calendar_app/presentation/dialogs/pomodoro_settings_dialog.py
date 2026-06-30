"""Pomodoro/focus timer settings dialog."""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QSettings, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_editor_styles import (
    build_settings_style_bundle,
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
)
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import apply_common_dialog_style
from calendar_app.shared.value_parsers import as_bool


class WheelBlocker(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            event.ignore()
            return True
        return super().eventFilter(obj, event)


class _PremiumToggleBtn(QPushButton):
    """모던한 알약 형태의 프리미엄 토글 버튼 (from Widget Manager)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(54, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggled.connect(self._update_style)

    def _update_style(self):
        from calendar_app.presentation.dialogs.dialog_styles import get_dialog_theme_tokens

        on = self.isChecked()
        self.setText("ON" if on else "OFF")
        tokens = get_dialog_theme_tokens()
        bg = tokens.get("success_hex", "#47d27e") if on else tokens.get("surface_item", "#111116")
        color = tokens.get("text_primary", "#e1e1e6") if on else tokens.get("text_muted", "#9aa0ad")
        border = (
            "none" if on else f"1px solid {tokens.get('border_soft', 'rgba(255,255,255,0.10)')}"
        )
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                color: {color};
                border: {border};
                border-radius: 13px;
                font-weight: 800;
                font-size: 8pt;
                padding-bottom: 1px;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
        """)


class PomodoroSettingsPanel(QWidget):
    """Reusable panel for Focus/Pomodoro timer settings."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings or QSettings("kimhyojin", "Dark Calendar")
        self._wheel_blocker = WheelBlocker(self)
        self._pomodoro_controls = []

        self._ui_tokens = get_dialog_theme_tokens()
        self._metrics = get_dialog_metric_tokens(apply_overrides=True)
        self._bundle = build_settings_style_bundle(self._ui_tokens, self._metrics)

        self._init_ui()
        self.load_values()

    @staticmethod
    def _safe_int(value, default: int, *, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, min(maximum, parsed))

    def _make_card(self, title: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(self._bundle["card"])
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 20, 20, 24)
        v.setSpacing(16)

        lbl = QLabel(title)
        lbl.setStyleSheet(self._bundle["card_title"])
        v.addWidget(lbl)
        v.addWidget(self._make_divider())
        return card

    def _make_divider(self) -> QFrame:
        f = QFrame()
        f.setObjectName("divider")
        f.setStyleSheet(self._bundle["divider"])
        return f

    def _make_row(self, label_text: str, widget: QWidget, helper_text: str = "") -> QWidget:
        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)

        v = QVBoxLayout()
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        lbl = QLabel(label_text)
        lbl.setStyleSheet(self._bundle["field_label"])
        v.addWidget(lbl)

        if helper_text:
            h_lbl = QLabel(helper_text)
            h_lbl.setStyleSheet(self._bundle["help"])
            h_lbl.setWordWrap(True)
            v.addWidget(h_lbl)

        h.addLayout(v, 1)
        h.addWidget(widget)
        return container

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setStyleSheet(self._bundle["scroll_shell"])
        scroll.setWidgetResizable(True)
        container = QWidget()
        container.setStyleSheet(self._bundle["content_area"])
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # 타이머 모드
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(t("dialog.pomodoro_settings.mode_pomodoro", "뽀모도로"), "pomodoro")
        self.mode_combo.addItem(
            t("dialog.pomodoro_settings.mode_stopwatch", "스톱워치"), "stopwatch"
        )
        self.mode_combo.setStyleSheet(self._bundle["input_combo"])
        self.mode_combo.setFixedWidth(200)

        mode_card = self._make_card(t("dialog.pomodoro_settings.mode_label", "타이머 모드"))
        mode_card.layout().addWidget(
            self._make_row(
                "실행 모드", self.mode_combo, "선택한 모드에 따라 타이머 동작 방식이 결정됩니다."
            )
        )
        layout.addWidget(mode_card)

        # 타이머 설정 그룹
        timers_card = self._make_card(t("dialog.pomodoro_settings.group_timers", "타이머 설정"))
        cl = timers_card.layout()

        self.focus_minutes_spin = QSpinBox()
        self.focus_minutes_spin.setStyleSheet(self._bundle["input_spin"])
        self.focus_minutes_spin.installEventFilter(self._wheel_blocker)
        self.focus_minutes_spin.setRange(1, 180)
        self.focus_minutes_spin.setFixedWidth(130)
        self.focus_minutes_spin.setSuffix(t("dialog.pomodoro_settings.minutes_suffix", " 분"))
        cl.addWidget(
            self._make_row(
                t("dialog.pomodoro_settings.focus_minutes", "집중 시간"), self.focus_minutes_spin
            )
        )
        cl.addWidget(self._make_divider())

        self.short_break_minutes_spin = QSpinBox()
        self.short_break_minutes_spin.setStyleSheet(self._bundle["input_spin"])
        self.short_break_minutes_spin.installEventFilter(self._wheel_blocker)
        self.short_break_minutes_spin.setRange(1, 60)
        self.short_break_minutes_spin.setFixedWidth(130)
        self.short_break_minutes_spin.setSuffix(t("dialog.pomodoro_settings.minutes_suffix", " 분"))
        cl.addWidget(
            self._make_row(
                t("dialog.pomodoro_settings.short_break_minutes", "짧은 휴식"),
                self.short_break_minutes_spin,
            )
        )
        cl.addWidget(self._make_divider())

        self.long_break_minutes_spin = QSpinBox()
        self.long_break_minutes_spin.setStyleSheet(self._bundle["input_spin"])
        self.long_break_minutes_spin.installEventFilter(self._wheel_blocker)
        self.long_break_minutes_spin.setRange(1, 120)
        self.long_break_minutes_spin.setFixedWidth(130)
        self.long_break_minutes_spin.setSuffix(t("dialog.pomodoro_settings.minutes_suffix", " 분"))
        cl.addWidget(
            self._make_row(
                t("dialog.pomodoro_settings.long_break_minutes", "긴 휴식"),
                self.long_break_minutes_spin,
            )
        )
        cl.addWidget(self._make_divider())

        self.long_break_every_spin = QSpinBox()
        self.long_break_every_spin.setStyleSheet(self._bundle["input_spin"])
        self.long_break_every_spin.installEventFilter(self._wheel_blocker)
        self.long_break_every_spin.setRange(2, 12)
        self.long_break_every_spin.setFixedWidth(130)
        self.long_break_every_spin.setSuffix(
            t("dialog.pomodoro_settings.cycle_suffix", " 세션마다")
        )
        cl.addWidget(
            self._make_row(
                t("dialog.pomodoro_settings.long_break_every", "긴 휴식 주기"),
                self.long_break_every_spin,
            )
        )
        cl.addWidget(self._make_divider())

        self.daily_goal_cycles_spin = QSpinBox()
        self.daily_goal_cycles_spin.setStyleSheet(self._bundle["input_spin"])
        self.daily_goal_cycles_spin.installEventFilter(self._wheel_blocker)
        self.daily_goal_cycles_spin.setRange(1, 20)
        self.daily_goal_cycles_spin.setFixedWidth(130)
        self.daily_goal_cycles_spin.setSuffix(t("dialog.pomodoro_settings.goal_suffix", " 세션"))
        cl.addWidget(
            self._make_row(
                t("dialog.pomodoro_settings.set_goal", "목표 세션 수"), self.daily_goal_cycles_spin
            )
        )

        layout.addWidget(timers_card)

        # 자동 진행 그룹
        behavior_card = self._make_card(t("dialog.pomodoro_settings.group_behavior", "자동 진행"))
        bl = behavior_card.layout()

        # Legacy uses QCheckBox, but we replace with _PremiumToggleBtn
        # However, to preserve compatibility with _bind_panel_fields returning a widget that supports .isChecked(),
        # _PremiumToggleBtn (inheriting QPushButton) works perfectly since it supports setChecked/isChecked.
        self.auto_start_break_cb = _PremiumToggleBtn()
        bl.addWidget(
            self._make_row(
                t("dialog.pomodoro_settings.auto_start_break", "집중 완료 후 자동으로 휴식 시작"),
                self.auto_start_break_cb,
                "집중 시간이 끝나면 휴식 타이머가 즉시 시작됩니다.",
            )
        )
        bl.addWidget(self._make_divider())

        self.auto_start_focus_cb = _PremiumToggleBtn()
        bl.addWidget(
            self._make_row(
                t(
                    "dialog.pomodoro_settings.auto_start_focus",
                    "휴식 완료 후 자동으로 다음 집중 시작",
                ),
                self.auto_start_focus_cb,
                "휴식 시간이 끝나면 다음 집중 사이클이 즉시 시작됩니다.",
            )
        )

        layout.addWidget(behavior_card)
        layout.addStretch(1)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        self._pomodoro_controls = [
            self.focus_minutes_spin,
            self.short_break_minutes_spin,
            self.long_break_minutes_spin,
            self.long_break_every_spin,
            self.daily_goal_cycles_spin,
            self.auto_start_break_cb,
            self.auto_start_focus_cb,
            timers_card,
            behavior_card,
        ]
        self.mode_combo.currentIndexChanged.connect(self._sync_mode_enabled_state)

    def load_values(self):
        mode_raw = (
            str(self.settings.value("focus_mode_type", "pomodoro") or "pomodoro").strip().lower()
        )
        mode = "stopwatch" if mode_raw == "stopwatch" else "pomodoro"
        index = self.mode_combo.findData(mode)
        self.mode_combo.setCurrentIndex(index if index >= 0 else 0)

        self.focus_minutes_spin.setValue(
            self._safe_int(
                self.settings.value("pomodoro_focus_minutes", 25), 25, minimum=1, maximum=180
            )
        )
        self.short_break_minutes_spin.setValue(
            self._safe_int(
                self.settings.value("pomodoro_short_break_minutes", 5), 5, minimum=1, maximum=60
            )
        )
        self.long_break_minutes_spin.setValue(
            self._safe_int(
                self.settings.value("pomodoro_long_break_minutes", 15), 15, minimum=1, maximum=120
            )
        )
        self.long_break_every_spin.setValue(
            self._safe_int(
                self.settings.value("pomodoro_long_break_every", 4), 4, minimum=2, maximum=12
            )
        )
        self.auto_start_break_cb.setChecked(
            as_bool(self.settings.value("pomodoro_auto_start_break", True), default=True)
        )
        self.auto_start_break_cb._update_style()
        self.auto_start_focus_cb.setChecked(
            as_bool(self.settings.value("pomodoro_auto_start_focus", True), default=True)
        )
        self.auto_start_focus_cb._update_style()
        self.daily_goal_cycles_spin.setValue(
            self._safe_int(
                self.settings.value("pomodoro_daily_goal_cycles", 4), 4, minimum=1, maximum=20
            )
        )
        self._sync_mode_enabled_state()

    def _sync_mode_enabled_state(self):
        enabled = self.mode_combo.currentData() == "pomodoro"
        for widget in self._pomodoro_controls:
            widget.setEnabled(enabled)

    def save_values(self):
        self.settings.setValue("focus_mode_type", self.mode_combo.currentData() or "pomodoro")
        self.settings.setValue("pomodoro_focus_minutes", self.focus_minutes_spin.value())
        self.settings.setValue(
            "pomodoro_short_break_minutes", self.short_break_minutes_spin.value()
        )
        self.settings.setValue("pomodoro_long_break_minutes", self.long_break_minutes_spin.value())
        self.settings.setValue("pomodoro_long_break_every", self.long_break_every_spin.value())
        self.settings.setValue("pomodoro_auto_start_break", self.auto_start_break_cb.isChecked())
        self.settings.setValue("pomodoro_auto_start_focus", self.auto_start_focus_cb.isChecked())
        self.settings.setValue("pomodoro_daily_goal_cycles", self.daily_goal_cycles_spin.value())
        if hasattr(self.settings, "sync"):
            self.settings.sync()


class PomodoroSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = getattr(parent, "settings", None) or QSettings("kimhyojin", "Dark Calendar")
        apply_dialog_title(self, t("dialog.pomodoro_settings.title", "Pomodoro Settings"))

        self._ui_tokens = get_dialog_theme_tokens()
        self._metrics = get_dialog_metric_tokens(apply_overrides=True)
        self._bundle = build_settings_style_bundle(self._ui_tokens, self._metrics)

        apply_common_dialog_style(self, minimum_width=560)
        self.setMinimumSize(560, 680)
        self._init_ui()
        self._bind_panel_fields()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.panel = PomodoroSettingsPanel(self.settings, self)
        layout.addWidget(self.panel, 1)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # Footer
        footer = QFrame()
        footer.setFixedHeight(64)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 0, 24, 0)

        cancel_btn = QPushButton(t("common.cancel", "Cancel"))
        cancel_btn.setObjectName("ghost_btn")
        cancel_btn.setMinimumWidth(100)
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton(t("common.save", "Save"))
        save_btn.setObjectName("primary_btn")
        save_btn.setMinimumWidth(100)
        save_btn.clicked.connect(self._save)

        footer_layout.addStretch(1)
        footer_layout.addWidget(cancel_btn)
        footer_layout.addWidget(save_btn)

        layout.addWidget(footer)

    def _save(self):
        self.panel.save_values()
        self.accept()

    def _bind_panel_fields(self):
        """Backwards-compatible field aliases for legacy callers/tests."""
        self.mode_combo = self.panel.mode_combo
        self.focus_minutes_spin = self.panel.focus_minutes_spin
        self.short_break_minutes_spin = self.panel.short_break_minutes_spin
        self.long_break_minutes_spin = self.panel.long_break_minutes_spin
        self.long_break_every_spin = self.panel.long_break_every_spin
        self.auto_start_break_cb = self.panel.auto_start_break_cb
        self.auto_start_focus_cb = self.panel.auto_start_focus_cb
        self.daily_goal_cycles_spin = self.panel.daily_goal_cycles_spin  # alias to panel field
