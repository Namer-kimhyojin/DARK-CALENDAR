# -*- coding: utf-8 -*-
"""Isolated regressions for the 2026-10-08 UI exception audit."""

from __future__ import annotations

import math
from types import SimpleNamespace

from PyQt6.QtCore import QDate, QObject, QSettings
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
import pytest

from calendar_app.presentation.dialogs.task_dialog_base import BaseTaskDialog
from calendar_app.presentation.main_window.refresh_scheduler import RefreshSchedulerMixin


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def isolated_settings(tmp_path):
    old_format = QSettings.defaultFormat()
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.SystemScope, str(tmp_path))
    yield
    QSettings.setDefaultFormat(old_format)


@pytest.mark.parametrize(
    ("stored", "selected"),
    [("10,bad,60", {10, 60}), ("bad", set()), ("0,-10,60,10080", {60, 10080}), ("", set())],
)
def test_alarm_section_tolerates_invalid_saved_default(qt_app, isolated_settings, stored, selected):
    settings = QSettings("DarkCalendar", "TaskDialog")
    settings.setValue("default_alarms", stored)
    dialog = BaseTaskDialog()
    dialog._init_common_state()
    dialog._update_alarm_summary = lambda: None
    try:
        section = dialog._build_alarm_section()
        assert {
            minutes for minutes, check in dialog.alarm_checks.items() if check.isChecked()
        } == selected
        assert settings.value("default_alarms") == stored
        section.deleteLater()
    finally:
        dialog.deleteLater()


def test_queued_panel_refresh_does_not_run_after_shutdown(qt_app):
    class Host(RefreshSchedulerMixin, QObject):
        def __init__(self):
            super().__init__()
            self.calls = []

        def load_left_panel(self, **kwargs):
            self.calls.append("left")

        def load_center_panel(self, **kwargs):
            self.calls.append("center")

        def load_right_panel(self, **kwargs):
            self.calls.append("right")

    host = Host()
    host.schedule_panel_refresh(left=True, center=True, right=True)
    # The queued start() can reach the event loop after shutdown stopped timers.
    host._is_shutting_down = True
    host._ui_refresh_timer.stop()
    QTest.qWait(60)
    assert host.calls == []
    assert not any(host._pending_refresh.values())
    host.deleteLater()


@pytest.mark.parametrize("stored", ["not-a-date", "2026-02-30", 20261008, "2026-10-07"])
def test_startup_working_date_is_valid_without_rewriting_settings(
    qt_app, isolated_settings, monkeypatch, tmp_path, stored
):
    from calendar_app.domain import task_constants
    from calendar_app.presentation.main_window import app_initializer

    settings = QSettings(str(tmp_path / "startup.ini"), QSettings.Format.IniFormat)
    settings.setValue("last_working_date", stored)
    observed = []

    class ReachedUi(Exception):
        pass

    class Host:
        def setWindowTitle(self, title):
            pass

        def setMouseTracking(self, enabled):
            pass

    def inspect_date(app):
        observed.append(app.current_date)
        raise ReachedUi

    monkeypatch.setattr(app_initializer, "QSettings", lambda *args: settings)
    monkeypatch.setattr(app_initializer, "ensure_gcal_startup_defaults", lambda settings: None)
    monkeypatch.setattr(app_initializer, "_initialize_focus_timer_defaults", lambda app: None)
    monkeypatch.setattr(app_initializer, "PresetManager", lambda app: None)
    monkeypatch.setattr(task_constants, "load_custom_labels", lambda: None)
    monkeypatch.setattr(app_initializer, "setup_main_ui", inspect_date)
    with pytest.raises(ReachedUi):
        app_initializer.initialize_overlay_app(Host())
    assert observed[0].isValid()
    assert observed[0] == (QDate(2026, 10, 7) if stored == "2026-10-07" else QDate.currentDate())
    assert settings.value("last_working_date") == stored


@pytest.mark.parametrize(
    ("size", "weight", "expected_size", "expected_weight"),
    [("bad", 500, 12, 500), (12, "bad", 12, 500), (10**50, 100000, 18, 500)],
)
def test_customization_font_controls_recover_invalid_settings(
    qt_app, isolated_settings, tmp_path, size, weight, expected_size, expected_weight
):
    from PyQt6.QtWidgets import QDialog, QWidget

    from calendar_app.presentation.dialogs.widget_customization_dialog import (
        WidgetCustomizationDialog,
        _DraftSettings,
    )

    settings = QSettings(str(tmp_path / "widget.ini"), QSettings.Format.IniFormat)
    settings.setValue("widget_mode_font_size", size)
    settings.setValue("widget_mode_font_weight", weight)
    dialog = WidgetCustomizationDialog.__new__(WidgetCustomizationDialog)
    QDialog.__init__(dialog)
    source_widget = QWidget(dialog)
    dialog.controller = SimpleNamespace(widget=source_widget)
    dialog.draft = _DraftSettings(settings)
    dialog._building = True
    try:
        tab = dialog._appearance_tab()
        assert dialog.font_size.value() == expected_size
        assert dialog.font_weight.currentData() == expected_weight
        dialog._sync_appearance_controls()
        assert dialog.font_size.value() == expected_size
        assert dialog.font_weight.currentData() == expected_weight
        assert settings.value("widget_mode_font_size") == size
        assert settings.value("widget_mode_font_weight") == weight
        tab.deleteLater()
    finally:
        dialog.deleteLater()


@pytest.mark.parametrize("stored", ["bad", "nan", "inf", "-inf", -50, "1234.5"])
def test_legacy_stopwatch_recovers_invalid_elapsed(qt_app, tmp_path, stored):
    from calendar_app.presentation.main_window.window_ui_actions import MainWindowUiActionsMixin

    class Host(MainWindowUiActionsMixin, QObject):
        pass

    host = Host()
    host.settings = QSettings(str(tmp_path / "stopwatch.ini"), QSettings.Format.IniFormat)
    host.settings.setValue("stopwatch_elapsed_ms", stored)
    try:
        host._ensure_stopwatch_timer()
        elapsed = host._current_stopwatch_elapsed_ms()
        assert math.isfinite(elapsed)
        assert elapsed == (1234.5 if stored == "1234.5" else 0)
        assert host._format_stopwatch_elapsed(elapsed)
        assert host.settings.value("stopwatch_elapsed_ms") == stored
    finally:
        timer = getattr(host, "_stopwatch_timer", None)
        if timer is not None:
            timer.stop()
        host.deleteLater()


@pytest.mark.parametrize(
    ("stored", "interval", "opacity"),
    [("bad", 5, 100), (None, 5, 100), (10**50, 1440, 100), (-1, 1, 20)],
)
def test_away_settings_and_lock_ui_recover_invalid_numeric_settings(
    qt_app, isolated_settings, tmp_path, stored, interval, opacity
):
    from PyQt6.QtWidgets import QFrame, QLabel, QWidget

    from calendar_app.presentation.dialogs.away_settings_dialog import AwaySettingsDialog
    from calendar_app.presentation.main_window.away_lock_actions import AwayLockMixin

    class Host(AwayLockMixin, QWidget):
        pass

    host = Host()
    host.settings = QSettings(str(tmp_path / "away.ini"), QSettings.Format.IniFormat)
    host.settings.setValue("away_interval", stored)
    host.settings.setValue("away_bg_opacity", stored)
    host.settings.setValue("away_font_size", "bad")
    host.settings.setValue("font_size", "bad")
    host.settings.setValue("away_message", "Away")
    host.lock_frame = QFrame(host)
    host.lock_lbl = QLabel(host.lock_frame)
    dialog = None
    try:
        dialog = AwaySettingsDialog(host)
        assert dialog.interval_spin.value() == interval
        assert dialog.opacity_slider.value() == opacity
        host.refresh_idle_lock_ui()
        assert "Away" in host.lock_lbl.text()
        assert host.settings.value("away_interval") == stored
        assert host.settings.value("away_bg_opacity") == stored
    finally:
        if dialog is not None:
            dialog.close()
            dialog.deleteLater()
        host.deleteLater()


@pytest.mark.parametrize("stored", ["broken", 1234])
def test_window_restore_tolerates_invalid_saved_qt_blobs(
    qt_app, isolated_settings, monkeypatch, tmp_path, stored
):
    from PyQt6.QtGui import QAction
    from PyQt6.QtWidgets import QDockWidget, QMainWindow

    from calendar_app.presentation.main_window import window_restore_helpers as restore
    from calendar_app.presentation.main_window.dock_sections import dock_layout_presets

    window = QMainWindow()
    window.settings = QSettings(str(tmp_path / "layout.ini"), QSettings.Format.IniFormat)
    window.settings.setValue("last_geometry", stored)
    window.settings.setValue("last_state", stored)
    window.settings.setValue("layout_version", restore._LAYOUT_VERSION)
    window.ensure_window_on_screen = lambda: None
    for dock_attr, action_attr in (
        ("left_dock", "act_today"),
        ("center_dock", "act_calendar"),
        ("routine_dock", "act_routine"),
        ("directive_dock", "act_directive"),
    ):
        setattr(window, dock_attr, QDockWidget(window))
        setattr(window, action_attr, QAction(window))
    monkeypatch.setattr(restore, "install_dock_persist_signals", lambda app: None)
    monkeypatch.setattr(restore, "_sync_vertical_splits", lambda app: None)
    monkeypatch.setattr(dock_layout_presets, "_preset_all_docked", lambda app: None)
    try:
        restore.restore_window_and_bind_menu_state(window)
        assert window.size().width() == 1200
        assert window.size().height() == 700
        assert not window._layout_restore_succeeded
        assert window._layout_restore_source == "none"
    finally:
        window.deleteLater()


@pytest.mark.parametrize("stored", ["bad", None, 10**50, -1])
def test_appearance_opener_tolerates_invalid_numeric_settings(
    qt_app, isolated_settings, monkeypatch, tmp_path, stored
):
    from PyQt6.QtWidgets import QDialog

    from calendar_app.presentation.dialogs import panel_color_picker_dialog
    from calendar_app.presentation.main_window.window_ui_actions import MainWindowUiActionsMixin

    seen = []

    class DialogStub:
        DialogCode = QDialog.DialogCode

        def __init__(self, **kwargs):
            seen.append(kwargs)

        def exec(self):
            return self.DialogCode.Rejected

    host = SimpleNamespace(
        settings=QSettings(str(tmp_path / "appearance.ini"), QSettings.Format.IniFormat)
    )
    for key in ("font_size", "last_border_opacity", "last_text_opacity"):
        host.settings.setValue(key, stored)
    monkeypatch.setattr(panel_color_picker_dialog, "PanelColorPickerDialog", DialogStub)
    MainWindowUiActionsMixin.open_panel_background_color_dialog(host)
    assert 1 <= seen[0]["current_font_size"] <= 256
    assert 0 <= seen[0]["current_border_opacity"] <= 255
    assert 0 <= seen[0]["current_text_opacity"] <= 255
    for key in ("font_size", "last_border_opacity", "last_text_opacity"):
        assert host.settings.value(key) == stored
