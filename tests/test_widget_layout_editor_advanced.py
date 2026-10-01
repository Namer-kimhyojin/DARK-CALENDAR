# -*- coding: utf-8 -*-
"""Editor-level history, zoom and portable configuration transaction contracts."""

from copy import deepcopy
import json
from unittest.mock import patch

import pytest

from calendar_app.presentation.widgets.widget_free_layout import (
    BLOCK_IDS,
    read_free_layout,
    seed_free_layout,
    validate_free_layout,
)
from calendar_app.presentation.widgets.widget_layout_editor_io import (
    MAX_LAYOUT_FILE_BYTES,
    load_layout_file,
    save_layout_file,
)
from tests.test_widget_free_layout_editor import editor  # noqa: F401
from tests.test_widget_mode_ux import _APP  # noqa: F401


def test_legacy_version_one_layout_loads_with_default_locks_and_layer_order():
    original = seed_free_layout("dashboard")
    original.pop("order")
    for block in original["blocks"]:
        block.pop("locked")
    before = deepcopy(original)
    normalized = validate_free_layout(original)
    assert normalized["order"] == list(BLOCK_IDS)
    assert all(not block["locked"] for block in normalized["blocks"])
    assert original == before


@pytest.mark.parametrize("bad", [[], ["date", "date"], ["missing"], [None], "date"])
def test_invalid_layer_order_is_rejected_or_completed(bad):
    data = seed_free_layout()
    data["order"] = bad
    if bad == []:
        assert validate_free_layout(data)["order"] == list(BLOCK_IDS)
    else:
        with pytest.raises(ValueError):
            validate_free_layout(data)


def test_portable_file_roundtrip_and_failed_atomic_write_preserve_target(tmp_path):
    target = tmp_path / "personal.airlayout.json"
    data = seed_free_layout("magazine")
    data["blocks"][0]["locked"] = True
    data["order"] = list(reversed(data["order"]))
    save_layout_file(target, data)
    assert load_layout_file(target) == validate_free_layout(data)
    previous = target.read_bytes()
    with (
        patch(
            "calendar_app.presentation.widgets.widget_layout_editor_io.os.replace",
            side_effect=OSError("denied"),
        ),
        pytest.raises(OSError),
    ):
        save_layout_file(target, seed_free_layout())
    assert target.read_bytes() == previous
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize(
    "content",
    [b"broken", b'{"version":9}', b"x" * (MAX_LAYOUT_FILE_BYTES + 1)],
    ids=["broken_json", "future_version", "oversized_file"],
)
def test_invalid_external_configuration_is_rejected(content, tmp_path):
    target = tmp_path / "bad.json"
    target.write_bytes(content)
    with pytest.raises(ValueError):
        load_layout_file(target)


def test_import_is_one_undoable_draft_change_and_export_never_applies(editor, tmp_path):
    dialog, settings, live = editor
    original = deepcopy(dialog.draft)
    saved = deepcopy(settings.values)
    geometry = live.geometry()
    path = tmp_path / "layout.airlayout.json"
    save_layout_file(path, seed_free_layout("minimal"))
    dialog.load_configuration(path)
    assert dialog.draft == load_layout_file(path)
    dialog.undo()
    assert dialog.draft == original
    dialog.redo()
    export_path = tmp_path / "export.json"
    dialog.save_configuration(export_path)
    assert json.loads(export_path.read_text(encoding="utf-8", errors="strict")) == dialog.draft
    assert settings.values == saved
    assert live.geometry() == geometry
    dialog.cancel_btn.click()
    assert settings.values == saved
    dialog.controller.apply_free_layout.assert_not_called()


def test_multi_alignment_layer_lock_and_history_do_not_write_live_settings(editor):
    dialog, settings, _ = editor
    saved = deepcopy(settings.values)
    dialog.component_checks["clock"].setChecked(True)
    assert dialog.canvas.selected_id == "clock"
    dialog.canvas.set_selection({"date", "clock"})
    dialog.preferences_tabs.setCurrentIndex(1)
    dialog.align_buttons["top"].click()
    selected = [block for block in dialog.draft["blocks"] if block["id"] in {"date", "clock"}]
    assert len({block["rect"][1] for block in selected}) == 1
    dialog.preferences_tabs.setCurrentIndex(0)
    dialog.front_btn.click()
    assert set(dialog.draft["order"][-2:]) == {"date", "clock"}
    dialog.lock_btn.click()
    assert all(
        block["locked"] for block in dialog.draft["blocks"] if block["id"] in {"date", "clock"}
    )
    assert all(not spin.isEnabled() for spin in dialog.rect_spins.values())
    dialog.undo()
    assert not any(block["locked"] for block in dialog.draft["blocks"])
    dialog.redo()
    assert settings.values == saved


def test_zoom_and_fit_change_only_editor_view_and_close_stops_preview(editor):
    dialog, settings, _ = editor
    before = deepcopy(dialog.draft)
    saved = deepcopy(settings.values)
    dialog.zoom_combo.setCurrentIndex(dialog.zoom_combo.findData(2.0))
    assert dialog.canvas.width() == before["canvas"][0] * 2
    dialog.fit_btn.click()
    assert 0.1 <= dialog.canvas.zoom <= 2
    assert dialog.draft == before
    assert settings.values == saved
    dialog._refresh_preview()
    renderer = dialog._renderer
    dialog.preview_checkbox.setChecked(False)
    assert dialog.canvas._preview_image is None
    dialog.cancel_btn.click()
    assert renderer._closed
    assert not dialog._preview_timer.isActive()
    assert read_free_layout(settings) == before


def test_appearance_and_geometry_share_history_and_cancel_is_transactional(editor):
    dialog, settings, _ = editor
    saved = deepcopy(settings.values)
    appearance = deepcopy(dialog.appearance)
    original = deepcopy(dialog.draft)
    dialog.preferences_tabs.setCurrentIndex(3)
    dialog.font_size.setValue(18)
    assert dialog.appearance["widget_mode_font_size"] == 18
    dialog.canvas.select_block("date")
    dialog.rect_spins["x"].setValue(72)
    moved = deepcopy(dialog.draft)
    dialog.undo()
    assert dialog.draft == original
    assert dialog.font_size.value() == 18
    dialog.undo()
    assert dialog.appearance == appearance
    dialog.redo()
    dialog.redo()
    assert dialog.draft == moved
    assert dialog.font_size.value() == 18
    dialog._refresh_preview()
    assert dialog._renderer.settings.value("widget_mode_font_size") == 18
    assert settings.values == saved
    dialog.cancel_btn.click()
    assert settings.values == saved


def test_appearance_updates_native_pixels_and_only_apply_writes_preferences(editor):
    dialog, settings, _ = editor
    dialog.canvas.set_selection(set())
    dialog._refresh_preview()
    before = dialog.canvas._preview_image.toImage()
    dialog.skin_combo.setCurrentIndex(dialog.skin_combo.findData("classic_dark"))
    dialog.text_opacity.setValue(75)
    dialog.background_opacity.setValue(60)
    dialog._refresh_preview()
    assert dialog.canvas._preview_image.toImage() != before
    expected = deepcopy(dialog.appearance)
    dialog.apply_btn.click()
    assert all(settings.value(key) == value for key, value in expected.items())
    assert read_free_layout(settings) == dialog.draft
    dialog.controller.apply_free_layout.assert_called_once()


def test_current_widget_cache_date_filter_and_clock_are_previewed_without_mutating(editor):
    from PyQt6.QtCore import QDate
    from PyQt6.QtWidgets import QLabel

    dialog, settings, live = editor
    items = [
        {
            "id": "live-task",
            "title": "CURRENT TASK",
            "item_kind": "work",
            "source": "task",
            "metadata": {"tags": ["unchanged"]},
        }
    ]
    live._last_items = deepcopy(items)
    live._active_filter = "work"
    live.clock_label = QLabel("08:42", live)
    dialog.controller._current_date = lambda: QDate(2026, 10, 1)
    saved = deepcopy(settings.values)
    dialog._refresh_preview()
    preview = dialog._renderer.window
    assert preview._last_items == items
    assert preview._active_filter == "work"
    assert preview.clock_label.text() == "08:42"
    assert dialog._renderer.host.current_date == QDate(2026, 10, 1)
    preview._last_items[0]["metadata"]["tags"].append("preview-only")
    assert live._last_items == items
    assert settings.values == saved
    live._last_items = []
    dialog._refresh_preview()
    assert preview._last_items == []
    assert dialog._renderer.host._latest_calendar_range_data["rows"] == []
    assert dialog._renderer.host._latest_directive_data["routine_rows"] == []
    assert dialog._renderer.host._latest_directive_data["directive_rows"] == []
