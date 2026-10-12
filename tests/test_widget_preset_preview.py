# -*- coding: utf-8 -*-
"""Preset thumbnails use the real renderer without altering widget settings."""

import json
from pathlib import Path
import re

from PyQt6.QtCore import QDateTime, QLocale, QSettings, QSize, Qt
from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import QApplication, QDialog, QTabWidget, QVBoxLayout, QWidget
import pytest

from calendar_app.presentation.dialogs.dialog_styles import apply_common_dialog_style
from calendar_app.presentation.widgets.overlay_base import _PRESET_FALLBACK, _get_widget_presets
from calendar_app.presentation.widgets.overlay_clock import OverlayClockWidget
from calendar_app.presentation.widgets.overlay_countdown import OverlayCountdownWidget
from calendar_app.presentation.widgets.overlay_datecard import OverlayDateCardWidget
from calendar_app.presentation.widgets.overlay_dday import OverlayDDayWidget
from calendar_app.presentation.widgets.overlay_stopwatch import OverlayStopwatchWidget
from calendar_app.presentation.widgets.overlay_text import OverlayTextWidget
from calendar_app.presentation.widgets.overlay_weather import OverlayWeatherWidget

_CLASSES = {
    "clock": OverlayClockWidget,
    "stopwatch": OverlayStopwatchWidget,
    "countdown": OverlayCountdownWidget,
    "datecard": OverlayDateCardWidget,
    "dday": OverlayDDayWidget,
    "text": OverlayTextWidget,
    "weather": OverlayWeatherWidget,
}


@pytest.fixture
def clock():
    app = QApplication.instance() or QApplication([])
    owner = QWidget()
    owner.settings = QSettings("codex_test", "widget_preset_preview")
    owner.settings.clear()
    widget = OverlayClockWidget(owner)
    yield app, widget
    widget.close()
    owner.settings.clear()
    owner.close()


def _plain(html):
    document = QTextDocument()
    document.setHtml(html)
    return document.toPlainText()


@pytest.mark.parametrize("hour, expected", [(0, "12:47"), (12, "12:47"), (18, "06:47")])
def test_ampm_preset_formats_12_hour_time_in_a_separate_token(clock, hour, expected):
    _app, widget = clock
    now = QDateTime.fromString(f"2026-10-07T{hour:02d}:47:09", Qt.DateFormat.ISODate)
    html = widget._resolve_clock_template("{time:%p}\n{time:%I:%M}", now, "")
    text = _plain(html)
    assert expected in text
    assert "%I" not in text and "%p" not in text


def test_render_context_is_restored_when_preview_raises(clock):
    _app, widget = clock
    widget._template_preview_base_size = 31

    def failing(_template):
        assert widget._template_render_font_size() == 12
        raise ValueError("broken custom renderer")

    with pytest.raises(ValueError):
        widget._render_template_preview(failing, "{time}", QSize(320, 240), base_size=12)
    assert widget._template_render_font_size() == 31


def test_clock_weekday_and_retro_hour_match_locale_and_ampm(clock):
    _app, widget = clock
    previous = QLocale()
    QLocale.setDefault(QLocale("ko_KR"))
    try:
        now = QDateTime.fromString("2026-10-07T18:47:09", Qt.DateFormat.ISODate)
        assert "수요일" in _plain(widget._resolve_clock_template("{weekday}", now, ""))
        widget._set("display_style", "retro")
        widget._set("clock_template", "")
        widget._now_tz = lambda: now
        widget._tick()
        assert widget._time_label.text() == "06:47:09"
        assert widget._ampm_label.text().startswith("오후")
    finally:
        QLocale.setDefault(previous)


@pytest.mark.parametrize("shape", ["card", "capsule", "circle", "poster"])
def test_native_thumbnail_is_read_only_and_contains_rendered_content(clock, shape):
    _app, widget = clock
    widget._set("widget_shape", shape)
    before = {key: widget._s().value(key) for key in widget._s().allKeys()}
    icon = widget._template_preset_icon(
        "{time:%H:%M|size=36|bold}",
        lambda template: widget._resolve_clock_template(template, widget._now_tz(), ""),
    )
    pixmap = icon.pixmap(QSize(104, 56))
    assert not pixmap.isNull()
    image = pixmap.toImage()
    background = image.pixelColor(0, 0)
    assert any(
        image.pixelColor(x, y) != background
        for x in range(image.width())
        for y in range(image.height())
    )
    assert widget._template_preview_base_size is None
    assert {key: widget._s().value(key) for key in widget._s().allKeys()} == before


@pytest.mark.parametrize(
    "kind,index",
    [(kind, index) for kind in _CLASSES for index in range(len(_PRESET_FALLBACK[kind]))],
)
def test_every_shipped_preset_has_a_read_only_native_thumbnail(clock, monkeypatch, kind, index):
    _app, clock_widget = clock
    monkeypatch.setattr(OverlayWeatherWidget, "request_update", lambda _self: None)
    widget = _CLASSES[kind](clock_widget.owner)
    now = QDateTime.fromString("2026-10-07T18:47:09", Qt.DateFormat.ISODate)
    renderers = {
        "clock": lambda template: widget._resolve_clock_template(template, now, "KST"),
        "stopwatch": lambda template: widget._resolve_sw_template(template, 754500, False),
        "countdown": lambda template: widget._resolve_cd_template(
            template, "02:03:04", now.addSecs(7384)
        ),
        "datecard": lambda template: widget._resolve_dc_template(template, now),
        "dday": lambda template: widget._resolve_dd_template(
            template, "D-14", "프로젝트 발표", now.date().addDays(14)
        ),
        "text": lambda template: widget.resolve_template(
            override_text=template,
            app_data={"task_count": 3, "next_event": "검토", "custom_var": "집중"},
        ),
        "weather": lambda template: widget._resolve_weather_template(
            template,
            {
                "city": "서울",
                "temp": "18.2",
                "unit": "°C",
                "desc": "흐림",
                "humidity": "72",
                "wind": "2.8",
                "_wmo": 3,
                "error": "",
            },
        ),
    }
    template = _PRESET_FALLBACK[kind][index]["template"]
    if template == "__DEFAULT__":
        template = widget._DEFAULT_TEMPLATE
    before = {key: widget._s().value(key) for key in widget._s().allKeys()}
    try:
        assert not widget._template_preset_icon(template, renderers[kind]).isNull(), (kind, index)
        assert {key: widget._s().value(key) for key in widget._s().allKeys()} == before
    finally:
        widget.close()


def test_bad_default_expansion_does_not_publish_an_invalid_preset():
    presets = _get_widget_presets("dday", lambda _key, fallback: fallback, "{elapsed}")
    assert all(template != "{elapsed}" for _label, template in presets)
    assert len(presets) == 7


def test_all_shipped_preset_names_are_defined_in_bundled_locales():
    for path in Path("locales").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8", errors="strict"))
        for kind in _CLASSES:
            for entry in _PRESET_FALLBACK[kind]:
                value = data
                for key in entry["label_key"].split("."):
                    value = value.get(key, {}) if isinstance(value, dict) else {}
                assert isinstance(value, str) and value.strip(), (path.name, entry["label_key"])


def test_actual_dday_default_expansion_is_available():
    presets = _get_widget_presets(
        "dday", lambda _key, fallback: fallback, OverlayDDayWidget._DEFAULT_TEMPLATE
    )
    assert len(presets) == 8
    assert presets[0][1] == OverlayDDayWidget._DEFAULT_TEMPLATE


def test_explicit_empty_template_restores_basic_mode(clock):
    _app, widget = clock
    widget._s().remove(widget._pref() + "_clock_template")
    assert widget._widget_template() == widget._DEFAULT_TEMPLATE
    widget._set("clock_template", "")
    assert widget._widget_template() == ""
    assert not widget._is_template_mode()


def test_cancelled_settings_discard_field_drafts_and_preview_timer(clock, monkeypatch):
    _app, clock_widget = clock
    widget = OverlayDDayWidget(clock_widget.owner)
    widget._set("dd_label", "원래 이름")
    before = {key: widget._s().value(key) for key in widget._s().allKeys()}

    def reject(_dialog):
        widget._active_settings_widgets["dd_label"].setText("취소한 이름")
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", reject)
    try:
        widget._open_settings()
        assert widget._active_settings_widgets == {}
        assert {key: widget._s().value(key) for key in widget._s().allKeys()} == before
    finally:
        widget.close()


def test_accepted_settings_commit_fields_after_releasing_drafts(clock, monkeypatch):
    _app, clock_widget = clock
    widget = OverlayDDayWidget(clock_widget.owner)

    def accept(_dialog):
        widget._active_settings_widgets["dd_label"].setText("저장한 이름")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", accept)
    try:
        widget._open_settings()
        assert widget._active_settings_widgets == {}
        assert widget._get("dd_label") == "저장한 이름"
    finally:
        widget.close()


def test_weather_preview_images_and_text_use_the_same_reference(clock, monkeypatch):
    _app, clock_widget = clock
    monkeypatch.setattr(OverlayWeatherWidget, "request_update", lambda _self: None)
    widget = OverlayWeatherWidget(clock_widget.owner)
    data = {"city": "서울", "temp": "18.2", "unit": "°C", "_wmo": 3, "error": ""}
    try:
        html = widget._render_template_preview(
            lambda template: widget._resolve_weather_template(template, data),
            "{icon|size=64}{temp|size=28}",
            QSize(104, 56),
            base_size=24,
        )
        assert re.search(r'<img[^>]+width="64"', html)
        assert "font-size:28pt" in html
        assert widget._template_preview_base_size is None
    finally:
        widget.close()


def test_advanced_manager_has_thumbnails_and_wrapped_error_feedback(clock):
    app, widget = clock
    dialog = QDialog()
    apply_common_dialog_style(dialog)
    root = QVBoxLayout(dialog)
    tabs = QTabWidget(dialog)
    root.addWidget(tabs)
    advanced = widget._build_advanced_template_tab(
        tabs,
        dialog,
        current_template="{time}",
        default_template=widget._DEFAULT_TEMPLATE,
        presets=[("Base", "{time}")],
        placeholder="",
        hint_text="",
        render_preview=lambda template: widget._resolve_clock_template(
            template, widget._now_tz(), ""
        ),
    )
    dialog.show()
    app.processEvents()
    combo = dialog.findChild(QWidget, "presetCombo")
    assert not combo.itemIcon(1).isNull()
    assert combo.maxVisibleItems() == 6
    assert combo.height() >= combo.iconSize().height() + 6
    advanced["editor"].setPlainText("{unsupported_variable|size=40}")
    advanced["update_preview"]()
    assert advanced["preview_meta"].wordWrap()
    assert advanced["preview_meta"].textFormat() == Qt.TextFormat.PlainText
    assert "unsupported_variable" in advanced["preview_meta"].text()
    assert "{" not in _plain(advanced["preview_label"].text())
    advanced["preview_timer"].stop()
    dialog.close()
