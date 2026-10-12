# -*- coding: utf-8 -*-
"""Rendering contracts for decorated date and D-Day content presets."""

import re

from PyQt6.QtCore import QDate, QDateTime, QLocale, QSettings, QSize, Qt, QTime, QTimer
from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import QApplication, QComboBox, QDialog, QWidget
import pytest

from calendar_app.presentation.widgets.moment_asset_packs import (
    EMPTY_MOMENT_ART,
    moment_art_size,
    moment_asset_html,
    remove_empty_moment_rows,
)
from calendar_app.presentation.widgets.overlay_datecard import OverlayDateCardWidget
from calendar_app.presentation.widgets.overlay_dday import OverlayDDayWidget
from calendar_app.presentation.widgets.overlay_template_validation import validate_widget_template


@pytest.fixture
def moment_widgets(tmp_path):
    app = QApplication.instance() or QApplication([])
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "moments.ini"), QSettings.Format.IniFormat)
    widgets = (OverlayDDayWidget(owner), OverlayDateCardWidget(owner))
    yield widgets
    for widget in widgets:
        for timer in widget.findChildren(QTimer):
            timer.stop()
        widget.close()
    owner.close()
    owner.deleteLater()
    app.processEvents()


def _plain(html):
    document = QTextDocument()
    document.setHtml(html)
    return document.toPlainText()


def _image_size(html):
    match = re.search(r'<img[^>]+width="(\d+)" height="(\d+)"', html)
    assert match is not None
    return tuple(map(int, match.groups()))


@pytest.mark.parametrize(
    ("hint", "base", "expected"),
    [
        ([], 24, 56),
        (["size=56"], 12, 28),
        (["size=56"], 48, 112),
        (["size=2x"], 24, 48),
        (["size=200%"], 24, 48),
        (["size=+10"], 24, 34),
        (["size=-4"], 24, 20),
        (["size=base"], 24, 24),
        (["size=56", "size=3x"], 24, 72),
        (["size=invalid"], 24, 56),
        (["size=inf"], 24, 56),
        (["size=99999999"], 24, 1536),
        (["size=1"], 24, 16),
    ],
)
def test_moment_art_follows_template_size_grammar(hint, base, expected):
    assert moment_art_size(hint, base) == expected


@pytest.mark.parametrize("kind,index", [("dday", 0), ("datecard", 1)])
def test_default_decorated_templates_pass_validator(moment_widgets, kind, index):
    widget = moment_widgets[index]
    assert not validate_widget_template(kind, widget._DEFAULT_TEMPLATE)


@pytest.mark.parametrize("kind,index", [("dday", 0), ("datecard", 1)])
def test_art_and_text_share_preview_and_live_scale(moment_widgets, kind, index):
    widget = moment_widgets[index]
    widget._set("font_size", 48)
    target = QDate(2026, 10, 20)
    now = QDateTime(target, QTime(12, 0))

    def render(template):
        if kind == "dday":
            return widget._resolve_dd_template(template, "D-14", "Project", target)
        return widget._resolve_dc_template(template, now)

    template = "{art|size=56}\n{date|size=36}"
    assert _image_size(render(template)) == (112, 112)
    original = widget._template_preview_base_size
    preferences = {key: widget._s().value(key) for key in widget._s().allKeys()}
    preview = widget._render_template_preview(render, template, QSize(320, 240), base_size=24)
    assert _image_size(preview) == (56, 56)
    assert "font-size:36pt" in preview
    assert widget._template_preview_base_size == original
    assert {key: widget._s().value(key) for key in widget._s().allKeys()} == preferences
    assert _image_size(render(template)) == (112, 112)


def test_preview_context_restores_after_renderer_failure(moment_widgets):
    widget = moment_widgets[0]
    widget._template_preview_base_size = 48

    def failing(_template):
        assert widget._template_render_font_size() == 18
        raise RuntimeError("offline renderer failure")

    with pytest.raises(RuntimeError, match="offline renderer failure"):
        widget._render_template_preview(failing, "{date}", QSize(320, 240), base_size=18)
    assert widget._template_render_font_size() == 48


@pytest.mark.parametrize(
    "kind,index,pack_key", [("dday", 0, "dday_asset_pack"), ("datecard", 1, "datecard_asset_pack")]
)
def test_text_only_pack_removes_art_only_row(moment_widgets, kind, index, pack_key):
    widget = moment_widgets[index]
    widget._set(pack_key, "none")
    target = QDate(2026, 10, 20)
    now = QDateTime.fromString("2026-10-20T12:00:00", Qt.DateFormat.ISODate)
    result = (
        widget._resolve_dd_template("{art}\n{date}", "D-14", "Project", target)
        if kind == "dday"
        else widget._resolve_dc_template("{art}\n{date}", now)
    )
    assert result == "2026.10.20"
    assert EMPTY_MOMENT_ART not in result


def test_empty_art_cleanup_preserves_text_rows_and_global_spacing():
    assert remove_empty_moment_rows(f"\n{EMPTY_MOMENT_ART}\nDate") == "\nDate"
    assert remove_empty_moment_rows(f"Title {EMPTY_MOMENT_ART}\nDate") == "Title \nDate"
    assert remove_empty_moment_rows(f"<lh 1.4>{EMPTY_MOMENT_ART}\nDate") == "<lh 1.4>Date"
    assert remove_empty_moment_rows(f"\x00ALIGN:center\x00{EMPTY_MOMENT_ART}\nDate") == "Date"


def test_dday_plain_formatted_dates_and_literal_label(moment_widgets):
    widget = moment_widgets[0]
    html = widget._resolve_dd_template(
        "{label|bold}\n{date}\n{date:%Y/%m/%d}",
        "D-14",
        "<수료> & 다음",
        QDate(2026, 10, 20),
    )
    assert _plain(html) == "<수료> & 다음\n2026.10.20\n2026/10/20"
    assert "&lt;수료&gt; &amp; 다음" in html


@pytest.mark.parametrize("target", [None, QDate()])
def test_unset_or_invalid_dday_does_not_look_completed(moment_widgets, target):
    widget = moment_widgets[0]
    html = widget._resolve_dd_template(
        "{dday}\n{days}\n{date}\n{date:%Y.%m.%d}\n{sign}",
        "D-?",
        "",
        target,
    )
    assert _plain(html).splitlines() == ["D-?", "?", "?", "?", "-"]
    html = widget._resolve_dd_template("{if days == 0}Unset{else}Future{/if}", "D-?", "", target)
    assert _plain(html) == "Unset"


def test_large_art_html_keeps_bounded_raster_cache(moment_widgets):
    small = moment_asset_html("air_moments", "birthday", 512)
    large = moment_asset_html("air_moments", "birthday", 1536)
    assert _image_size(large) == (1536, 1536)
    assert re.search(r'src="([^"]+)"', small).group(1) == re.search(r'src="([^"]+)"', large).group(
        1
    )


@pytest.mark.parametrize(
    "locale,expected",
    [
        (QLocale.Language.Korean, ["화요일", "화", "10월"]),
        (QLocale.Language.English, ["Tuesday", "Tue", "October"]),
    ],
)
def test_datecard_weekday_and_month_follow_locale(moment_widgets, locale, expected):
    original = QLocale()
    QLocale.setDefault(QLocale(locale))
    try:
        dday, datecard = moment_widgets
        now = QDateTime(QDate(2026, 10, 6), QTime(12, 0))
        html = datecard._resolve_dc_template("{weekday}\n{weekday:short}\n{month}", now)
        assert _plain(html).splitlines() == expected
        assert _plain(datecard._resolve_dc_template("{weekday:en}", now)) == "Tue"
        assert _plain(datecard._resolve_dc_template("{date:%B}", now)) == expected[2]
        assert (
            _plain(datecard._resolve_dc_template("{if month == 10}{month}{else}Other{/if}", now))
            == expected[2]
        )
        datecard._update_basic_display(now)
        assert datecard._labels["weekday"].text() == expected[0]
        assert _plain(dday._resolve_dd_template("{date:%A}", "D-0", "", now.date())) == expected[0]
    finally:
        QLocale.setDefault(original)


def test_dday_compact_uses_one_row_and_fixed_or_long_content_wraps(moment_widgets):
    widget = moment_widgets[0]
    widget._set("dd_template", "{dday|size=28|bold}  {label|size=11|color=muted}")
    widget._set("dd_target_date", "2026-10-20")
    widget._set("dd_label", "프로젝트 발표")
    widget._tick_dd()
    assert not widget._template_label.wordWrap()
    widget._set("fixed_w", 300)
    widget._set("fixed_h", 100)
    widget._tick_dd()
    assert widget._template_label.wordWrap()
    widget._set("fixed_w", None)
    widget._set("fixed_h", None)
    widget._set("dd_label", "매우 긴 프로젝트 이름 " * 200)
    widget._tick_dd()
    assert widget._template_label.wordWrap()
    widget._set("dd_label", "프로젝트 발표")
    widget._set("dd_template", widget._DEFAULT_TEMPLATE)
    widget._tick_dd()
    assert widget._template_label.wordWrap()


def test_dday_compact_font_measurement_preserves_wrapping(moment_widgets):
    widget = moment_widgets[0]
    widget._set("dd_template", "{dday|size=28|bold} {label|size=11}")
    widget._measuring = True
    try:
        widget._tick_dd()
        assert widget._template_label.wordWrap()
    finally:
        widget._measuring = False


@pytest.mark.parametrize(
    "kind,index,pack_key", [("dday", 0, "dday_asset_pack"), ("datecard", 1, "datecard_asset_pack")]
)
def test_moment_draft_is_used_only_inside_preview_context(moment_widgets, kind, index, pack_key):
    widget = moment_widgets[index]
    widget._set("font_size", 24)
    widget._set(pack_key, "air_moments")
    pack = QComboBox(widget)
    pack.addItem("Paper", "paper_seasons")
    fields = {pack_key: pack}
    if kind == "dday":
        widget._set("dday_moment", "celebration")
        moment = QComboBox(widget)
        moment.addItem("Study", "study")
        fields["dday_moment"] = moment
    widget._active_settings_widgets = fields
    target = QDate(2026, 10, 20)
    now = QDateTime(target, QTime(12, 0))

    def render(template):
        if kind == "dday":
            return widget._resolve_dd_template(template, "D-14", "Project", target)
        return widget._resolve_dc_template(template, now)

    baseline = render("{art}")
    assert widget._selected_dialog_asset_pack() == "air_moments"
    if kind == "dday":
        assert widget._selected_dialog_moment() == "celebration"
    preferences = {key: widget._s().value(key) for key in widget._s().allKeys()}
    preview = widget._render_template_preview(render, "{art}", QSize(320, 240), base_size=24)
    assert re.search(r'src="([^"]+)"', baseline).group(1) != re.search(
        r'src="([^"]+)"', preview
    ).group(1)
    # An old, uncommitted dialog reference must not influence actual rendering.
    assert render("{art}") == baseline
    assert widget._template_preview_base_size is None
    assert {key: widget._s().value(key) for key in widget._s().allKeys()} == preferences


@pytest.mark.parametrize(
    "kind,index,pack_key", [("dday", 0, "dday_asset_pack"), ("datecard", 1, "datecard_asset_pack")]
)
def test_cancelled_moment_settings_leave_actual_art_unchanged(
    moment_widgets, monkeypatch, kind, index, pack_key
):
    widget = moment_widgets[index]
    widget._set(pack_key, "air_moments")
    widget._set(widget._TEMPLATE_KEY, "{art}")
    if kind == "dday":
        widget._set("dday_moment", "celebration")
    widget._refresh_face()
    baseline = widget._template_label.text()
    preferences = {key: widget._s().value(key) for key in widget._s().allKeys()}

    def reject(_dialog):
        fields = widget._active_settings_widgets
        pack = fields[pack_key]
        pack.setCurrentIndex(pack.findData("paper_seasons"))
        if kind == "dday":
            moment = fields["dday_moment"]
            moment.setCurrentIndex(moment.findData("study"))
        assert widget._selected_dialog_asset_pack() == "air_moments"
        widget._refresh_face()
        assert widget._template_label.text() == baseline
        widget._template_preview_base_size = 24
        try:
            assert widget._selected_dialog_asset_pack() == "paper_seasons"
            if kind == "dday":
                assert widget._selected_dialog_moment() == "study"
        finally:
            widget._template_preview_base_size = None
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", reject)
    widget._open_settings()
    widget._refresh_face()
    assert widget._template_label.text() == baseline
    assert widget._selected_dialog_asset_pack() == "air_moments"
    if kind == "dday":
        assert widget._selected_dialog_moment() == "celebration"
    assert {key: widget._s().value(key) for key in widget._s().allKeys()} == preferences
