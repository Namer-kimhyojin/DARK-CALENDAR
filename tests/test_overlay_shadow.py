# -*- coding: utf-8 -*-
"""Text shadows preserve overlay content, instance settings and placement."""

from dataclasses import replace
from unittest.mock import patch

from PyQt6.QtCore import QPoint, QSettings
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QLabel,
    QWidget,
)
import pytest

from calendar_app.presentation.widgets.overlay_clock import OverlayClockWidget
from calendar_app.presentation.widgets.overlay_countdown import OverlayCountdownWidget
from calendar_app.presentation.widgets.overlay_datecard import OverlayDateCardWidget
from calendar_app.presentation.widgets.overlay_dday import OverlayDDayWidget
from calendar_app.presentation.widgets.overlay_manager import OverlayWidgetManager
from calendar_app.presentation.widgets.overlay_shadow import (
    TextShadow,
    TextShadowControls,
    TextShadowDialog,
    apply_text_shadow,
    read_text_shadow,
    store_text_shadow,
)
from calendar_app.presentation.widgets.overlay_stopwatch import OverlayStopwatchWidget
from calendar_app.presentation.widgets.overlay_text import OverlayTextWidget
from calendar_app.presentation.widgets.overlay_weather import OverlayWeatherWidget

KINDS = (
    OverlayClockWidget,
    OverlayStopwatchWidget,
    OverlayDateCardWidget,
    OverlayCountdownWidget,
    OverlayDDayWidget,
    OverlayTextWidget,
    OverlayWeatherWidget,
)


@pytest.fixture
def owner(tmp_path):
    app = QApplication.instance() or QApplication([])
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "shadows.ini"), QSettings.Format.IniFormat)
    yield owner
    for window in app.topLevelWidgets():
        if getattr(window, "owner", None) is owner:
            window.close()
    owner.close()
    app.processEvents()


def snapshot(owner):
    return {key: owner.settings.value(key) for key in owner.settings.allKeys()}


def shadow_targets(widget):
    targets = list(widget.face.findChildren(QLabel))
    if getattr(widget, "_grid_widget", None) is not None:
        targets.append(widget._grid_widget)
    return targets


@pytest.mark.parametrize(
    "values,expected",
    [
        ({}, TextShadow()),
        ({"enabled": "false"}, TextShadow()),
        ({"enabled": "true"}, TextShadow(True)),
        ({"enabled": "1"}, TextShadow(True)),
        ({"enabled": True, "opacity": "bad", "blur": None, "color": "bad"}, TextShadow(True)),
        (
            {"enabled": "yes", "opacity": 200, "blur": -10, "distance": 99, "color": "#FFAA00"},
            TextShadow(True, 100, 0, 12, "#ffaa00"),
        ),
    ],
)
def test_old_or_damaged_settings_have_bounded_safe_values(values, expected):
    data = {"text_shadow_" + key: value for key, value in values.items()}
    assert read_text_shadow(lambda key, default=None: data.get(key, default)) == expected


def test_foreign_effects_are_preserved_and_owned_effect_is_reused(owner):
    label = QLabel("18:47", owner)
    existing = QGraphicsOpacityEffect(label)
    existing.setOpacity(0.5)
    label.setGraphicsEffect(existing)
    apply_text_shadow(label, TextShadow(True))
    apply_text_shadow(label, TextShadow())
    assert label.graphicsEffect() is existing
    assert existing.opacity() == 0.5

    label.setGraphicsEffect(None)
    apply_text_shadow(label, TextShadow(True))
    shadow = label.graphicsEffect()
    assert isinstance(shadow, QGraphicsDropShadowEffect)
    apply_text_shadow(label, TextShadow(True, 80, 12, 3, "#102030"))
    assert label.graphicsEffect() is shadow
    assert shadow.blurRadius() == 12
    assert shadow.color().name() == "#102030"
    assert shadow.color().alpha() == 204
    apply_text_shadow(label, TextShadow(False))
    assert label.graphicsEffect() is shadow
    assert not shadow.isEnabled()
    apply_text_shadow(label, TextShadow(True, opacity=0))
    assert not shadow.isEnabled()
    apply_text_shadow(label, TextShadow(True))
    assert shadow.isEnabled()


@pytest.mark.parametrize("kind", KINDS)
def test_every_overlay_reuses_shadows_for_all_text_and_template_content(owner, kind):
    widget = kind(owner)
    try:
        widget.apply_initial_settings()
        widget._set_text_shadow_enabled(True)
        targets = shadow_targets(widget)
        assert targets
        effects = [target.graphicsEffect() for target in targets]
        assert all(isinstance(effect, QGraphicsDropShadowEffect) for effect in effects)
        assert all(effect.isEnabled() for effect in effects)
        assert widget.graphicsEffect() is None
        assert widget.face.graphicsEffect() is None

        if widget._TEMPLATE_KEY is not None:
            widget._set(
                widget._TEMPLATE_KEY, "<b>Review</b>\n<span style='color:#ff8800'>Tomorrow</span>"
            )
            widget._apply_and_resize()
        for _ in range(3):
            widget._apply_appearance()
        assert [target.graphicsEffect() for target in targets] == effects

        widget._set_text_shadow_enabled(False)
        assert [target.graphicsEffect() for target in targets] == effects
        assert all(not effect.isEnabled() for effect in effects)
    finally:
        widget.close()


def test_shadow_does_not_change_rich_text_styles_or_appearance_preset(owner):
    widget = OverlayClockWidget(owner)
    widget._set_display_preset("pure_type")
    widget._set("clock_template", "<b>18:47</b>\n<span style='color:#ffaa00'>2026.10.06</span>")
    widget._apply_and_resize()
    original_html = widget._template_label.text()
    colors = (widget.text_color_rgba(), widget.bg_color_rgba(), widget.border_color_rgba())
    widget._set_text_shadow_enabled(True)
    assert widget._template_label.text() == original_html
    assert colors == (widget.text_color_rgba(), widget.bg_color_rgba(), widget.border_color_rgba())
    assert widget.display_preset_id() == "pure_type"
    config = read_text_shadow(widget._get)
    widget._set_display_preset("pearl_mist")
    assert read_text_shadow(widget._get) == config
    assert widget.display_preset_id() == "pearl_mist"
    widget.close()


def test_instance_restore_and_duplicate_keep_shadows_independent(owner):
    manager = OverlayWidgetManager(owner)
    restored = None
    try:
        first_id = manager.add_instance("clock")
        second_id = manager.add_instance("clock")
        first = manager.get_widget(first_id)
        second = manager.get_widget(second_id)
        config = TextShadow(True, 72, 7, 4, "#123456")
        store_text_shadow(first._set, config)
        first._apply_and_resize()
        first.move(60, 60)
        assert read_text_shadow(second._get) == TextShadow(True)

        copy_id = manager.duplicate_instance(first_id)
        duplicate = manager.get_widget(copy_id)
        assert read_text_shadow(duplicate._get) == config
        assert duplicate.pos() == first.pos() + QPoint(24, 24)
        duplicate._set_text_shadow_enabled(False)
        assert read_text_shadow(first._get) == config
        assert not read_text_shadow(duplicate._get).enabled
        manager.save_all()

        restored = OverlayWidgetManager(owner)
        restored.restore_all()
        assert read_text_shadow(restored.get_widget(first_id)._get) == config
        assert read_text_shadow(restored.get_widget(second_id)._get) == TextShadow(True)
        assert not read_text_shadow(restored.get_widget(copy_id)._get).enabled
        assert restored.get_widget(first_id)._template_label.graphicsEffect().isEnabled()
    finally:
        if restored is not None:
            restored.remove_all()
        manager.remove_all()


@pytest.mark.parametrize("result", [QDialog.DialogCode.Rejected, QDialog.DialogCode.Accepted])
def test_dedicated_dialog_keeps_changes_as_draft_until_save(owner, result):
    widget = OverlayClockWidget(owner)
    widget.apply_initial_settings()
    before = snapshot(owner)
    config = TextShadow(True, 40, 5, 1, "#123456")

    def edit_and_close(dialog):
        dialog.controls.set_values(config)
        assert snapshot(owner) == before
        return result

    with patch.object(TextShadowDialog, "exec", edit_and_close):
        widget._action_open_shadow_dialog()
    if result == QDialog.DialogCode.Rejected:
        assert snapshot(owner) == before
    else:
        assert read_text_shadow(widget._get) == config
        assert widget._template_label.graphicsEffect().isEnabled()
    widget.close()


@pytest.mark.parametrize("result", [QDialog.DialogCode.Rejected, QDialog.DialogCode.Accepted])
def test_common_appearance_dialog_keeps_shadow_edits_draft_until_save(owner, result):
    widget = OverlayClockWidget(owner)
    widget.apply_initial_settings()
    before = snapshot(owner)
    config = TextShadow(True, 35, 4, 2, "#203040")

    def edit_and_close(dialog):
        controls = dialog.findChild(TextShadowControls)
        assert controls is not None
        controls.set_values(config)
        assert snapshot(owner) == before
        return result

    with patch.object(QDialog, "exec", edit_and_close):
        widget._open_standard_settings_dialog("Shadow test", has_template=False)
    if result == QDialog.DialogCode.Rejected:
        assert snapshot(owner) == before
    else:
        assert read_text_shadow(widget._get) == config
        assert widget._template_label.graphicsEffect().isEnabled()
    widget.close()


def test_controls_preview_uses_the_same_effect_and_retains_values_when_disabled(owner):
    config = TextShadow(True, 57, 9, 3, "#203040")
    controls = TextShadowControls(config, owner)
    assert controls.values() == config
    effect = controls.preview.graphicsEffect()
    assert effect.isEnabled()
    assert controls.fields.isEnabled()
    controls.enabled.setChecked(False)
    assert controls.values() == replace(config, enabled=False)
    assert not controls.fields.isEnabled()
    assert controls.preview.graphicsEffect() is effect
    assert not effect.isEnabled()
    controls.enabled.setChecked(True)
    controls.sliders["blur"].setValue(12)
    assert controls.preview.graphicsEffect() is effect
    assert effect.isEnabled() and effect.blurRadius() == 12
    controls.close()


@pytest.mark.parametrize("shape", ["card", "circle", "capsule", "poster"])
def test_shadow_changes_preserve_fixed_box_position_and_shape_mask(owner, shape):
    widget = OverlayClockWidget(owner)
    widget._set_widget_shape(shape)
    widget._set("fixed_w", 300)
    widget._set("fixed_h", 300 if shape == "circle" else 150)
    widget._apply_and_resize()
    widget.move(100, 80)
    widget.show()
    QApplication.processEvents()
    before_pos = QPoint(widget.pos())
    before_size = widget.size()
    before_mask = widget.mask()
    widget._set_text_shadow_enabled(True)
    assert widget.pos() == before_pos
    assert widget.size() == before_size
    assert widget.mask() == before_mask
    widget._set_text_shadow_enabled(False)
    assert widget.pos() == before_pos
    assert widget.size() == before_size
    assert widget.mask() == before_mask
    widget.close()


def test_pure_type_shadow_renders_visible_depth_without_a_frame_or_edge_clipping(owner):
    widget = OverlayClockWidget(owner)
    try:
        widget._set_display_preset("pure_type")
        widget._set("clock_template", "<b>18:47</b>\n2026.10.06")
        widget._set("font_size", 42)
        widget._set("fixed_w", 520)
        widget._set("fixed_h", 230)
        widget._timer.stop()
        widget._apply_and_resize()
        widget.show()
        QApplication.processEvents()
        before = widget.grab().toImage()
        store_text_shadow(widget._set, TextShadow(True, 80, 12, 3))
        widget._apply_and_resize()
        QApplication.processEvents()
        after = widget.grab().toImage()
        assert after != before
        assert "background: transparent" in widget.face.styleSheet()
        assert "border: none" in widget.face.styleSheet()
        dark_before = dark_after = 0
        for y in range(after.height()):
            for x in range(after.width()):
                old = before.pixelColor(x, y)
                new = after.pixelColor(x, y)
                dark_before += old.alpha() > 10 and max(old.red(), old.green(), old.blue()) < 70
                dark_after += new.alpha() > 10 and max(new.red(), new.green(), new.blue()) < 70
                if x < 2 or y < 2 or x >= after.width() - 2 or y >= after.height() - 2:
                    assert new.alpha() <= 2
        assert dark_after > dark_before + 100
    finally:
        widget.close()
