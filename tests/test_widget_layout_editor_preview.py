# -*- coding: utf-8 -*-
"""Native preview geometry, synthetic content, source isolation and cleanup."""

from copy import deepcopy

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QDate, QEvent, QPoint, QSize, Qt
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import QAbstractScrollArea, QWidget
import pytest

from calendar_app.presentation.widgets.unified_widget_mode import ModernWeekDayButton
from calendar_app.presentation.widgets.widget_free_layout import seed_free_layout
from calendar_app.presentation.widgets.widget_layout_editor_preview import PreviewRenderer
from tests.test_widget_mode_ux import _APP, Settings  # noqa: F401


class ReadOnlySettings(Settings):
    def setValue(self, key, value):
        raise AssertionError(f"preview wrote source setting: {key}")


@pytest.fixture
def renderer():
    settings = ReadOnlySettings()
    settings.values.update({"widget_mode_filter": "work", "widget_mode_font_size": 15})
    preview = PreviewRenderer(settings)
    yield preview, settings
    preview.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("preset,mode", [("stacked", "week"), ("dashboard", "month")])
def test_native_calendar_geometry_and_source_settings_remain_isolated(renderer, preset, mode):
    preview, settings = renderer
    before = deepcopy(settings.values)
    data = seed_free_layout(preset)
    image = preview.render(data)
    canvas = preview.window._free_runtime
    assert image.size() == QSize(*data["canvas"])
    assert image.devicePixelRatio() == 1.0
    assert not image.isNull()
    assert canvas.data["calendar_mode"] == mode
    assert preview.window.cal_grid.findChildren(ModernWeekDayButton)
    for block in data["blocks"]:
        if block["enabled"]:
            assert canvas.frames[block["id"]].geometry().getRect() == tuple(block["rect"])
    assert settings.values == before
    assert preview.settings.value("widget_mode_font_size") == 15
    assert not preview.window.isVisible()
    assert preview.window.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    assert preview.window.toolbar.isHidden()


def test_typed_lists_use_synthetic_rows_and_render_large_canvas_without_clipping(renderer):
    preview, settings = renderer
    data = seed_free_layout("stacked")
    data["canvas"] = [1600, 1200]
    for index, block in enumerate(data["blocks"]):
        block["enabled"] = True
        block["rect"] = [20 + index % 2 * 780, 20 + index // 2 * 280, 720, 240]
    image = preview.render(data)
    assert image.size() == QSize(1600, 1200)
    panels = preview.window._free_runtime.panels
    assert {kind: [row.item_key for row in panel.rows] for kind, panel in panels.items()} == {
        "schedule": [("task", 101)],
        "work": [("task", 102)],
        "directive": [("directive", 103)],
    }
    assert all(panel.rows[0].parent() is panel.content for panel in panels.values())
    assert settings.values["widget_mode_filter"] == "work"
    assert not preview.window.timer.isActive()
    assert not preview.controller._load_timer.isActive()


def test_parent_cleanup_is_idempotent_and_rejects_further_rendering():
    parent = QWidget()
    preview = PreviewRenderer(ReadOnlySettings(), parent)
    preview.render(seed_free_layout("stacked"))
    parent.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    preview.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(preview.window)
    assert sip.isdeleted(preview.host)
    with pytest.raises(RuntimeError, match="closed"):
        preview.render(seed_free_layout("stacked"))


def test_source_appearance_and_fitted_readouts_are_used_in_native_image(renderer):
    preview, settings = renderer
    settings.values.update(
        {
            "widget_mode_font_family": "Arial",
            "widget_mode_font_size": 18,
            "widget_mode_text_opacity": 70,
            "widget_mode_background_opacity": 30,
        }
    )
    data = seed_free_layout("stacked")
    for block in data["blocks"]:
        if block["id"] == "date":
            block["rect"] = [0, 0, 160, 48]
        elif block["id"] == "clock":
            block["enabled"] = True
            block["rect"] = [180, 0, 100, 48]
    original = deepcopy(data)
    image = preview.render(data)
    assert data == original
    assert preview.window.font().family() == "Arial"
    assert preview.window._style_signature[-1] == (70, 30)
    # An empty canvas pixel includes the parent's translucent surface, rather
    # than a black or fully transparent QWidget.grab() background.
    alpha = image.toImage().pixelColor(1, image.height() - 2).alpha()
    assert 0 < alpha < 255
    for kind in ("date", "clock"):
        control = preview.window._free_runtime.contents[kind]
        metrics = QFontMetrics(control.font())
        assert metrics.horizontalAdvance(control.text()) <= control.width() - 8
        assert metrics.height() <= control.height() - 4


def test_cleanup_handles_qt_host_already_destroyed():
    preview = PreviewRenderer(ReadOnlySettings())
    preview.host.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(preview.controller._load_timer)
    preview.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(preview.window)


def test_current_item_snapshot_date_and_draft_appearance_are_rendered_read_only(renderer):
    preview, settings = renderer
    before = deepcopy(settings.values)
    data = seed_free_layout("stacked")
    for block in data["blocks"]:
        block["enabled"] = True
    items = [
        {
            "source": "task",
            "item_id": 501,
            "item_kind": "schedule",
            "title": "Current meeting",
            "time": "09:30",
            "is_task": False,
            "metadata": {"calendar_id": "local-8"},
        },
        {
            "source": "task",
            "item_id": 502,
            "item_kind": "work",
            "title": "Current work",
            "time": "",
            "is_task": True,
            "status": "in_progress",
            "completed": False,
        },
        {
            "source": "directive",
            "item_id": 503,
            "item_kind": "work",
            "title": "Current review",
            "time": "",
            "is_task": True,
            "status": "pending",
            "completed": False,
        },
    ]
    original = deepcopy(items)
    selected_date = QDate(2027, 3, 12)
    preview.settings.setValue("widget_mode_font_family", "Arial")
    preview.settings.setValue("widget_mode_font_size", 18)
    preview.render(data, items=items, current_date=selected_date)
    assert preview.host.current_date == selected_date
    assert preview.controller._current_date() == selected_date
    assert preview.window._last_items == original
    panels = preview.window._free_runtime.panels
    assert {kind: [row.item_key for row in panel.rows] for kind, panel in panels.items()} == {
        "schedule": [("task", 501)],
        "work": [("task", 502)],
        "directive": [("directive", 503)],
    }
    assert preview.host._latest_calendar_range_data["rows"][0]["deadline"] == "2027-03-12 09:30"
    assert preview.window.font().family() == "Arial"
    assert preview.window._style_signature[3].preference == 18
    assert items == original
    items[0]["metadata"]["calendar_id"] = "changed-after-render"
    assert preview.window._last_items[0]["metadata"]["calendar_id"] == "local-8"
    assert settings.values == before


def test_empty_current_snapshot_replaces_examples_and_invalid_date_preserves_selection(renderer):
    preview, _settings = renderer
    data = seed_free_layout("stacked")
    for block in data["blocks"]:
        block["enabled"] = True
    selected_date = QDate(2028, 2, 29)
    preview.render(data, current_date=selected_date)
    assert len(preview.window._last_items) == 3
    preview.render(data, items=[], current_date=QDate())
    assert preview.host.current_date == selected_date
    assert preview.window._last_items == []
    assert preview.host._latest_calendar_range_data["rows"] == []
    assert preview.host._latest_directive_data["routine_rows"] == []
    assert preview.host._latest_directive_data["directive_rows"] == []
    assert all(not panel.rows for panel in preview.window._free_runtime.panels.values())
    preview.render(data, items=None)
    assert len(preview.window._last_items) == 3


@pytest.mark.parametrize(
    "requested,expected,visible_key",
    [
        ("schedule", "schedule", ("task", 101)),
        ("work", "work", ("task", 102)),
        ("directive", "directive", ("directive", 103)),
        ("unknown", "all", None),
    ],
)
def test_current_filter_and_clock_match_snapshot_without_source_writes(
    renderer, requested, expected, visible_key
):
    preview, settings = renderer
    before = deepcopy(settings.values)
    data = seed_free_layout("stacked")
    snapshot = preview._example_items()
    preview.render(data, items=snapshot, active_filter=requested, clock_text="09:47:12")
    assert preview.window._active_filter == expected
    assert preview.window.clock_label.text() == "09:47:12"
    row_keys = [row.item_key for row in preview.window._agenda_rows]
    assert row_keys == (
        [visible_key] if visible_key else [("task", 101), ("task", 102), ("directive", 103)]
    )
    assert preview.window._last_items == snapshot
    assert settings.values == before
    preview.render(data, active_filter=requested, clock_text="09:47:12")
    assert preview.window._active_filter == "all"
    assert preview.window.clock_label.text() == "14:00"


def test_current_filter_defaults_to_source_after_sample_mode(renderer):
    preview, settings = renderer
    data = seed_free_layout("stacked")
    preview.render(data)
    assert preview.window._active_filter == "all"
    preview.render(data, items=[], clock_text="")
    assert preview.window._active_filter == "work"
    assert preview.window.clock_label.text() == ""
    assert settings.values["widget_mode_filter"] == "work"


def test_appearance_undo_restores_first_rows_and_resets_all_scrollbars(renderer):
    preview, _settings = renderer
    data = seed_free_layout("stacked")
    for block in data["blocks"]:
        block["enabled"] = True
    items = [
        {
            "source": "task",
            "item_id": index,
            "item_kind": "schedule",
            "is_task": False,
            "title": f"Meeting {index}",
            "time": "09:00",
        }
        for index in range(20)
    ]
    initial_appearance = {
        "widget_mode_font_family": "Arial",
        "widget_mode_font_size": 12,
        "widget_mode_text_opacity": 100,
        "widget_mode_background_opacity": 100,
    }
    for key, value in initial_appearance.items():
        preview.settings.setValue(key, value)
    initial = preview.render(data, items=items, active_filter="all").toImage()
    _APP.processEvents()
    for area in preview.window.findChildren(QAbstractScrollArea):
        area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())
    preview.settings.setValue("widget_mode_font_family", "Courier New")
    preview.settings.setValue("widget_mode_font_size", 18)
    preview.settings.setValue("widget_mode_text_opacity", 50)
    preview.settings.setValue("widget_mode_background_opacity", 40)
    preview.render(data, items=items, active_filter="all")
    _APP.processEvents()
    areas = preview.window.findChildren(QAbstractScrollArea)
    for area in areas:
        area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())
    assert any(area.verticalScrollBar().value() > 0 for area in areas)
    for key, value in initial_appearance.items():
        preview.settings.setValue(key, value)
    restored = preview.render(data, items=items, active_filter="all").toImage()
    assert restored.size() == initial.size()
    first_row = preview.window._agenda_rows[0]
    assert first_row.item_key == ("task", 0)
    assert first_row.mapTo(preview.window.scroll.viewport(), QPoint()).y() == 0
    assert all(
        area.verticalScrollBar().value() == area.horizontalScrollBar().value() == 0
        for area in preview.window.findChildren(QAbstractScrollArea)
    )
