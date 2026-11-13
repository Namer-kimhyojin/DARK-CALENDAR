# -*- coding: utf-8 -*-
"""Visible dialog roles follow saved points without a second pt-to-px conversion."""

from pathlib import Path
import re
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PyQt6.QtCore import QCoreApplication, QEvent, QSettings
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
import pytest

from calendar_app.presentation import focus_mode
from calendar_app.presentation.dialogs.calendar_sync_style import build_sync_workspace_styles
from calendar_app.presentation.dialogs.daily_summary_dialog import DailySummaryDialog
from calendar_app.presentation.dialogs.dialog_editor_styles import build_settings_style_bundle
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_preview_stylesheet,
    get_dialog_metric_tokens,
    get_dialog_theme_tokens,
    set_dialog_metric_overrides,
)
from calendar_app.presentation.dialogs.focus_completion_dialog import FocusCompletionDialog
from calendar_app.presentation.dialogs.help_center_dialog import HelpCenterDialog
from calendar_app.presentation.dialogs.management_dialogs import _management_header_style
from calendar_app.presentation.widgets.alarm_popup import (
    _alarm_popup_style_bundle,
    _alarm_time_label_style,
    _build_alarm_popup_stylesheet,
)
from calendar_app.presentation.widgets.command_palette_runtime import (
    _build_command_palette_stylesheet,
    _command_palette_style_bundle,
)
from calendar_app.presentation.widgets.overlay_base import (
    _build_overlay_dialog_stylesheet,
    _overlay_group_label_style,
)
from calendar_app.presentation.widgets.overlay_manager_dialog import (
    _build_manager_css,
    _load_tokens,
    _overlay_manager_style_bundle,
    _ToggleBtn,
)
from calendar_app.presentation.widgets.widget_management_styles import management_styles
from calendar_app.shared.typography import get_typography_scale


@pytest.fixture
def settings():
    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory() as temporary:
        cfg = QSettings(str(Path(temporary) / "typography.ini"), QSettings.Format.IniFormat)
        cfg.setValue("font_size", 11)
        cfg.setValue("text_theme", "light")
        cfg.setValue("panel_base_color", "#f6f7fb")
        yield cfg
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


@pytest.mark.parametrize("base_pt", [11, 14, 24])
@pytest.mark.parametrize("mode", ["light", "dark"])
def test_common_roles_and_controls_use_logical_pixels_and_inherit_family(settings, base_pt, mode):
    settings.setValue("font_size", base_pt)
    settings.setValue("text_theme", mode)
    scale = get_typography_scale(settings)
    dialog = QDialog()
    dialog.setFont(QFont("Arial", base_pt))
    layout = QVBoxLayout(dialog)
    body = QLabel("본문 내용")
    title = QLabel("일정 설정")
    title.setProperty("role", "dialogTitle")
    caption = QLabel("보조 설명")
    caption.setProperty("role", "dialogSubtitle")
    field = QLineEdit("09:00")
    button = QPushButton("저장")
    for widget in (title, caption, body, field, button):
        layout.addWidget(widget)
    apply_common_dialog_style(dialog, settings=settings)
    dialog.show()
    QApplication.processEvents()
    assert body.font().pixelSize() == scale.body_px
    assert title.font().pixelSize() == scale.title_px
    assert caption.font().pixelSize() == scale.caption_px
    assert title.font().family() == dialog.font().family() == "Arial"
    assert title.font().pixelSize() > body.font().pixelSize() > caption.font().pixelSize()
    for widget in (field, button):
        assert widget.height() >= widget.fontMetrics().height() + 8
    dialog.close()
    dialog.deleteLater()


@pytest.mark.parametrize("base_pt", [11, 24])
def test_sync_management_and_widget_styles_consume_legacy_metric_names_as_px(settings, base_pt):
    settings.setValue("font_size", base_pt)
    metrics = get_dialog_metric_tokens(settings=settings)
    tokens = get_dialog_theme_tokens(settings=settings)
    title_px = metrics["title_font_pt"]
    sync = build_sync_workspace_styles(tokens, metrics)
    assert f"font-size: {title_px}px" in sync
    assert f"font-size: {title_px}px" in _management_header_style(tokens, metrics)
    assert (
        "font-size: 19px" in _overlay_manager_style_bundle(tokens, {"base_font_pt": 19})["row_name"]
    )
    tok = _load_tokens(settings)
    for stylesheet in (sync, _build_manager_css(tok), management_styles(tok)):
        assert not re.search(r"font-size:\s*[\d.]+pt", stylesheet)
        assert f"font-size: {title_px}px" in stylesheet
    bundle = build_settings_style_bundle(tokens, metrics)
    assert f"font-size: {metrics['subtitle_font_pt']}px" in bundle["help"]
    assert f"font-size: {metrics['base_font_pt']}px" in bundle["field_label"]


def test_large_font_metric_preview_and_saved_overrides_are_not_clamped(settings):
    settings.setValue("font_size", 24)
    scale = get_typography_scale(settings)
    set_dialog_metric_overrides(
        {"base_font_pt": scale.body_px, "title_font_pt": scale.title_px}, settings
    )
    metrics = get_dialog_metric_tokens(settings=settings)
    assert metrics["base_font_pt"] == 32
    assert metrics["title_font_pt"] == 39
    preview = build_dialog_preview_stylesheet(
        metric_overrides={"base_font_pt": 32, "title_font_pt": 39}, settings=settings
    )
    assert "font-size: 39px" in preview


def test_large_widget_visibility_toggle_fits_its_caption(settings):
    settings.setValue("font_size", 24)
    toggle = _ToggleBtn(True, _load_tokens(settings))
    toggle.setText("표시 중")
    toggle.ensurePolished()
    toggle.resize(toggle.sizeHint())
    assert toggle.minimumHeight() >= toggle.fontMetrics().height() + 2
    assert toggle.sizeHint().width() >= toggle.fontMetrics().horizontalAdvance(toggle.text()) + 2
    toggle.close()
    toggle.deleteLater()


def test_large_font_help_and_daily_briefing_keep_readable_role_hierarchy(settings):
    settings.setValue("font_size", 24)
    parent = QWidget()
    parent.settings = settings
    scale = get_typography_scale(settings)
    with (
        patch.object(DailySummaryDialog, "_load_schedule", return_value=[]),
        patch.object(DailySummaryDialog, "_load_due_routines", return_value=[]),
    ):
        daily = DailySummaryDialog(parent)
    help_dialog = HelpCenterDialog(parent)
    daily.ensurePolished()
    help_dialog.ensurePolished()
    daily_titles = [
        label for label in daily.findChildren(QLabel) if label.property("role") == "title"
    ]
    assert daily_titles
    assert all(label.font().pixelSize() == scale.title_px for label in daily_titles)
    assert help_dialog.findChild(QLabel, "helpCenterTitle").font().pixelSize() == scale.title_px
    assert (
        help_dialog.findChild(QLabel, "helpCenterSubtitle").font().pixelSize() >= scale.caption_px
    )
    for dialog in (daily, help_dialog, parent):
        dialog.close()
        dialog.deleteLater()


@pytest.mark.parametrize("base_pt", [11, 24])
def test_alarm_and_overlay_settings_do_not_reinterpret_px_metrics_as_points(settings, base_pt):
    settings.setValue("font_size", base_pt)
    metrics = get_dialog_metric_tokens(settings=settings)
    tokens = get_dialog_theme_tokens(settings=settings)
    alarm = _alarm_popup_style_bundle(metrics=metrics, settings=settings)
    alarm_css = _build_alarm_popup_stylesheet(alarm)
    assert f"font-size: {metrics['title_font_pt']}px" in alarm_css
    assert f"font-size: {metrics['subtitle_font_pt']}px" in _alarm_time_label_style("normal", alarm)
    assert not re.search(r"font-size:\s*[\d.]+pt", alarm_css)
    overlay_css = _build_overlay_dialog_stylesheet(tokens=tokens, metrics=metrics)
    for selector in ("sectionLabel", "previewCaption", "previewMeta"):
        role_css = re.findall(r"QLabel#" + selector + r"\s*\{([^}]+)\}", overlay_css)[-1]
        assert f"font-size: {metrics['subtitle_font_pt']}px" in role_css
    assert f"font-size:{metrics['subtitle_font_pt']}px" in _overlay_group_label_style(
        tokens, metrics
    )
    palette = _command_palette_style_bundle(settings=settings)
    assert f"font-size: {metrics['subtitle_font_pt']}px" in _build_command_palette_stylesheet(
        palette
    )


def test_focus_completion_and_phase_toast_follow_title_section_body_roles(settings):
    settings.setValue("font_size", 24)
    parent = QWidget()
    parent.settings = settings
    scale = get_typography_scale(settings)
    completion = FocusCompletionDialog(parent)
    completion.ensurePolished()
    assert (
        completion.findChild(QLabel, "focusCompletionHeading").font().pixelSize() == scale.title_px
    )
    before = set(focus_mode._active_phase_toasts)
    focus_mode._announce_phase_change(
        parent, "다음 집중", "이제 다음 작업을 시작합니다.", "pomodoro"
    )
    created = focus_mode._active_phase_toasts - before
    assert len(created) == 1
    popup = created.pop()
    labels = {label.text(): label for label in popup.findChildren(QLabel)}
    assert labels["다음 집중"].font().pixelSize() == scale.section_px
    assert labels["이제 다음 작업을 시작합니다."].font().pixelSize() == scale.body_px
    for widget in (popup, completion, parent):
        widget.close()
        widget.deleteLater()
