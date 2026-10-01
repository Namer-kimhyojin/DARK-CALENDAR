# -*- coding: utf-8 -*-
"""Native Qt composition editor QA, with synthetic data and isolated settings.

Run in separate processes with QT_SCALE_FACTOR=1, 1.5, or 2. No application
database, user registry settings, calendar sync or network service is opened.
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import os
from pathlib import Path
import platform
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", default="final")
    parser.add_argument("--verify-appearance-reset", action="store_true")
    args = parser.parse_args()
    os.environ["QT_QPA_PLATFORM"] = "windows" if sys.platform == "win32" else "offscreen"
    scale = os.environ.get("QT_SCALE_FACTOR", "1")
    output = ROOT / "artifacts/widget-editor-advanced-20261001" / f"{args.phase}-scale-{scale}"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="air-editor-qa-", ignore_cleanup_errors=True) as temp:
        os.environ["LOCALAPPDATA"] = temp
        os.environ["APPDATA"] = temp
        from PyQt6 import QtCore
        from PyQt6.QtCore import (
            PYQT_VERSION_STR,
            QT_VERSION_STR,
            QDate,
            QEvent,
            QPoint,
            QPointF,
            QSettings,
            Qt,
        )
        from PyQt6.QtGui import QFont, QImage, QMouseEvent, QPainter
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import (
            QAbstractButton,
            QApplication,
            QLabel,
            QPushButton,
            QScrollArea,
            QStyle,
            QStyleOptionButton,
        )

        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        settings_path = str(Path(temp) / "settings.ini")
        isolated = QSettings(settings_path, QSettings.Format.IniFormat)
        for key, value in {
            "language": "ko",
            "text_theme": "light",
            "panel_base_color": "#f3f6fb",
            "theme_color": "#3a7bbf",
        }.items():
            isolated.setValue(key, value)
        isolated.sync()

        class IsolatedSettings(QSettings):
            def __init__(self, *unused_args, **unused_kwargs):
                super().__init__(settings_path, QSettings.Format.IniFormat)

        with patch.object(QtCore, "QSettings", IsolatedSettings):
            from tests.test_widget_mode_ux import Host

            from calendar_app.infrastructure import i18n as translations
            from calendar_app.presentation.dialogs.widget_free_layout_editor import (
                WidgetFreeLayoutEditorDialog,
            )
            from calendar_app.presentation.widgets import widget_free_layout as model
            from calendar_app.presentation.widgets.unified_widget_mode import (
                UnifiedWidgetController,
            )
            from calendar_app.presentation.widgets.widget_layout_editor_canvas import overlap_pairs

        report = {
            "environment": {
                "platform": platform.platform(),
                "python": sys.version,
                "qt": QT_VERSION_STR,
                "pyqt": PYQT_VERSION_STR,
                "qt_platform": app.platformName(),
                "scale_factor": scale,
                "screen_available": [
                    app.primaryScreen().availableGeometry().width(),
                    app.primaryScreen().availableGeometry().height(),
                ],
                "settings_and_appdata": "temporary test-only locations",
            },
            "checks": [],
            "observations": [],
            "limits": [
                "Synthetic static examples; no production data or database.",
                "Requested 1200x800/900x650 logical sizes can be clamped by the native window manager at high scale; actual and constructor sizes are recorded.",
                "Separate scale-factor processes; no physical mixed-DPI monitor transfer.",
                "No screen-reader or long-session acceptance.",
            ],
        }

        def check(name, passed, detail=None):
            report["checks"].append({"name": name, "passed": bool(passed), "detail": detail})

        def settle():
            for _ in range(3):
                app.processEvents()
            QTest.qWait(80)
            app.processEvents()

        def locale(language):
            translations.i18n.lang = language
            translations.i18n.translations = json.loads(
                (ROOT / f"locales/{language}.json").read_text(encoding="utf-8", errors="strict")
            )
            translations.i18n.bundled_translations = {}
            translations.i18n.fallback_translations = json.loads(
                (ROOT / "locales/en.json").read_text(encoding="utf-8", errors="strict")
            )
            translations.i18n._apply_qt_locale(language)

        def fixture():
            data = model.seed_free_layout("stacked")
            data["canvas"] = [1000, 720]
            data["snap"] = False
            placements = {
                "date": [60, 60, 220, 80],
                "clock": [400, 60, 140, 80],
                "calendar": [60, 180, 880, 140],
                "filters": [60, 350, 880, 80],
                "agenda": [60, 460, 880, 220],
            }
            for block in data["blocks"]:
                block["enabled"] = block["id"] in placements
                block["locked"] = False
                if block["enabled"]:
                    block["rect"] = placements[block["id"]]
            return model.validate_free_layout(data)

        def block(data, name):
            return next(item for item in data["blocks"] if item["id"] == name)

        def make(language="ko", theme="light", empty=False):
            locale(language)
            for key, value in {
                "text_theme": theme,
                "panel_base_color": "#f3f6fb" if theme == "light" else "#202630",
            }.items():
                isolated.setValue(key, value)
            isolated.sync()
            host = Host()
            host.current_date = QDate(2026, 10, 1)
            host._latest_calendar_range_data = {
                "range_start": "2026-09-01",
                "range_end": "2026-11-01",
                "rows": [{"id": 1, "name": "QA LIVE Schedule", "deadline": "2026-10-01 14:00:00"}],
            }
            host._latest_directive_data = {
                "context_date": "2026-10-01",
                "routine_rows": [
                    {
                        "id": 2,
                        "name": "QA LIVE Work",
                        "target_date": "2026-10-01",
                        "status": "in_progress",
                    }
                ],
                "directive_rows": [(3, "QA LIVE Directive", "pending", "", "2026-10-01")],
            }
            if empty:
                host._latest_calendar_range_data["rows"] = []
                host._latest_directive_data["routine_rows"] = []
                host._latest_directive_data["directive_rows"] = []
            host.settings.values.update(
                {"widget_mode_skin": f"classic_{theme}", "widget_mode_always_top": False}
            )
            model.write_free_layout(host.settings, fixture())
            controller = UnifiedWidgetController(host)
            controller.show_widget()
            controller.widget.timer.stop()
            controller.widget.resize(760, 600)
            settle()
            before = copy.deepcopy(host.settings.values)
            snapshot = copy.deepcopy(controller.widget._last_items)
            caches_before = copy.deepcopy(
                [host._latest_calendar_range_data, host._latest_directive_data]
            )
            with patch(
                "sqlite3.connect", side_effect=AssertionError("QA forbids database access")
            ) as db_spy:
                editor = WidgetFreeLayoutEditorDialog(controller)
                initial = [editor.width(), editor.height()]
                editor.move(app.primaryScreen().availableGeometry().topLeft() + QPoint(10, 10))
                editor.show()
                settle()
                editor._refresh_preview()
                check(f"{language}_{theme}_preview_no_database", db_spy.call_count == 0)
            check(
                f"{language}_{theme}_{empty}_preview_cached_titles",
                [item.get("title") for item in editor._renderer.window._last_items]
                == [item.get("title") for item in snapshot],
                [item.get("title") for item in editor._renderer.window._last_items],
            )
            check(
                f"{language}_{theme}_{empty}_preview_current_date",
                editor._renderer.host.current_date == host.current_date,
            )
            check(
                f"{language}_{theme}_{empty}_preview_cache_immutable",
                controller.widget._last_items == snapshot
                and [host._latest_calendar_range_data, host._latest_directive_data]
                == caches_before,
            )
            check(f"{language}_{theme}_preview_settings_unchanged", host.settings.values == before)
            check(
                f"{language}_{theme}_native_preview_present",
                editor.canvas._preview_image is not None
                and not editor.canvas._preview_image.isNull(),
            )
            return host, controller, editor, before, initial

        def close(host, controller, editor):
            editor.reject()
            editor.deleteLater()
            controller.prepare_shutdown()
            controller.widget.close()
            controller.widget.deleteLater()
            host.deleteLater()
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            settle()

        def rect(parent, child):
            point = child.mapTo(parent, QPoint())
            return [point.x(), point.y(), child.width(), child.height()]

        def text_width_available(control):
            option = QStyleOptionButton()
            option.initFrom(control)
            option.text = control.text()
            return (
                control.style()
                .subElementRect(QStyle.SubElement.SE_PushButtonContents, option, control)
                .width()
            )

        def capture(name, editor, extra=None):
            settle()
            path = output / f"{name}.png"
            editor.grab().save(str(path))
            buttons = [
                control for control in editor.findChildren(QAbstractButton) if control.isVisible()
            ]
            observation = {
                "scenario": name,
                "size": [editor.width(), editor.height()],
                "actual_screen": editor.screen().name(),
                "screen_available_rect": list(editor.screen().availableGeometry().getRect()),
                "device_pixel_ratio": editor.devicePixelRatioF(),
                "screenshot": str(path.relative_to(ROOT)).replace("\\", "/"),
                "zoom": editor.canvas.zoom,
                "selection": sorted(editor.canvas.selected_ids),
                "preview_titles": [
                    item.get("title") for item in editor._renderer.window._last_items
                ]
                if editor._renderer is not None
                else None,
                "appearance": copy.deepcopy(editor.appearance),
                "preview_source": editor.source_badge.text(),
                "status": editor.status_label.text(),
                "overlap_pairs": overlap_pairs(editor.draft),
                "controls_viewport": [
                    editor.controls_scroll.viewport().width(),
                    editor.controls_scroll.viewport().height(),
                ],
                "canvas_viewport": [
                    editor.canvas_scroll.viewport().width(),
                    editor.canvas_scroll.viewport().height(),
                ],
                "buttons": [
                    {
                        "text": control.text(),
                        "accessible_name": control.accessibleName(),
                        "rect": rect(editor, control),
                        "text_width": control.fontMetrics().horizontalAdvance(control.text()),
                        "content_width": text_width_available(control)
                        if isinstance(control, QPushButton)
                        else None,
                    }
                    for control in buttons
                ],
                "scrolls": [
                    {
                        "rect": rect(editor, control),
                        "h_max": control.horizontalScrollBar().maximum(),
                        "v_max": control.verticalScrollBar().maximum(),
                    }
                    for control in editor.findChildren(QScrollArea)
                ],
                "labels": [
                    {"text": control.text(), "rect": rect(editor, control)}
                    for control in editor.findChildren(QLabel)
                    if control.isVisible()
                ],
            }
            if extra:
                observation.update(extra)
            report["observations"].append(observation)
            clipped = [
                item
                for item in observation["buttons"]
                if item["content_width"] is not None and item["text_width"] > item["content_width"]
            ]
            check(f"{name}_button_text_fits", not clipped, clipped or None)

        locale("ko")
        check("initial_fixture_no_overlap", not overlap_pairs(fixture()))
        host, controller, editor, before, initial = make()
        if args.verify_appearance_reset:
            original = copy.deepcopy(editor.appearance)
            editor.canvas._preview_image.save(str(output / "appearance-before.png"))
            editor.font_size.setValue(18)
            editor.font_family.setCurrentFont(QFont("Arial"))
            editor.text_opacity.setValue(55)
            settle()
            editor.undo()
            editor.undo()
            editor.undo()
            settle()
            editor._refresh_preview()
            editor.canvas._preview_image.save(str(output / "appearance-after-undo.png"))
            areas = editor._renderer.window.findChildren(QScrollArea)
            check(
                "appearance_reset_scrollbars_zero",
                all(
                    area.verticalScrollBar().value() == 0
                    and area.horizontalScrollBar().value() == 0
                    for area in areas
                ),
            )
            check(
                "appearance_reset_controls_source_unchanged",
                editor.appearance == original and host.settings.values == before,
            )
            capture("appearance-undo-reset-final", editor)
            close(host, controller, editor)
            report["summary"] = {
                "checks": len(report["checks"]),
                "failed": sum(not item["passed"] for item in report["checks"]),
                "screenshots": len(report["observations"]),
            }
            (output / "appearance-reset-observations.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", errors="strict"
            )
            logging.shutdown()
            print(json.dumps({"output": str(output), **report["summary"]}))
            if report["summary"]["failed"]:
                raise SystemExit(1)
            return
        editor.resize(1200, 800)
        editor.activateWindow()
        editor.canvas.setFocus()
        settle()
        live_geometry = controller.widget.geometry()
        fixture_path = Path(temp) / "fixture.airlayout.json"

        def load(data=None):
            fixture_path.write_text(
                json.dumps(data or fixture(), ensure_ascii=False), encoding="utf-8", errors="strict"
            )
            editor.load_configuration(fixture_path)
            editor.guides_checkbox.setChecked(False)
            editor.canvas.set_zoom(0.5)
            editor.canvas_scroll.horizontalScrollBar().setValue(0)
            editor.canvas_scroll.verticalScrollBar().setValue(0)
            settle()

        def mouse(start, end, modifiers=Qt.KeyboardModifier.NoModifier, release=True):
            canvas = editor.canvas
            first = canvas.logical_to_screen(QPoint(*start))
            last = canvas.logical_to_screen(QPoint(*end))
            QTest.mousePress(canvas, Qt.MouseButton.LeftButton, modifiers, first)
            event = QMouseEvent(
                QEvent.Type.MouseMove,
                QPointF(last),
                QPointF(canvas.mapToGlobal(last)),
                Qt.MouseButton.NoButton,
                Qt.MouseButton.LeftButton,
                modifiers,
            )
            QApplication.sendEvent(canvas, event)
            if release:
                QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, modifiers, last)
                settle()

        load()
        canvas = editor.canvas
        canvas.set_zoom(1)
        canvas.set_selection(set())
        QApplication.sendEvent(canvas, QEvent(QEvent.Type.Leave))
        settle()
        native = canvas.grab().toImage()
        preview = QImage(native.size(), QImage.Format.Format_ARGB32)
        preview.fill(canvas.palette().base().color())
        painter = QPainter(preview)
        painter.drawPixmap(preview.rect(), canvas._preview_image)
        painter.end()
        ratio = canvas.devicePixelRatioF()
        pixels = [(61, 72), (270, 61), (64, 136)]
        check(
            "wysiwyg_unselected_wireframes_absent",
            all(
                native.pixelColor(round(x * ratio), round(y * ratio)).rgb()
                == preview.pixelColor(round(x * ratio), round(y * ratio)).rgb()
                for x, y in pixels
            ),
        )
        for zoom in (0.25, 0.5, 1, 1.5, 2):
            editor.zoom_combo.setCurrentIndex(editor.zoom_combo.findData(zoom))
            check(
                f"zoom_{zoom}_coordinate_mapping",
                canvas.screen_to_logical(canvas.logical_to_screen(QPoint(120, 80)))
                == QPoint(120, 80)
                and canvas.width() == round(1000 * zoom),
            )
        editor.fit_btn.click()
        settle()
        viewport = editor.canvas_scroll.viewport()
        check(
            "fit_canvas_in_viewport",
            canvas.width() <= viewport.width() and canvas.height() <= viewport.height(),
            [canvas.width(), canvas.height(), viewport.width(), viewport.height(), canvas.zoom],
        )

        load()
        QTest.mouseClick(
            canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            canvas.logical_to_screen(QPoint(170, 100)),
        )
        QTest.mouseClick(
            canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.ControlModifier,
            canvas.logical_to_screen(QPoint(470, 100)),
        )
        check("ctrl_additive_selection", canvas.selected_ids == {"date", "clock"})
        QTest.mouseClick(
            canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.ShiftModifier,
            canvas.logical_to_screen(QPoint(170, 100)),
        )
        check("shift_toggle_selection", canvas.selected_ids == {"clock"})
        canvas.set_selection(set())
        mouse((40, 40), (580, 150))
        check(
            "marquee_selects_two",
            canvas.selected_ids == {"date", "clock"},
            sorted(canvas.selected_ids),
        )
        mouse((170, 100), (186, 124))
        check(
            "group_move_preserves_relative_offset",
            block(editor.draft, "date")["rect"] == [76, 84, 220, 80]
            and block(editor.draft, "clock")["rect"] == [416, 84, 140, 80],
            [block(editor.draft, item)["rect"] for item in ("date", "clock")],
        )
        editor.undo_btn.click()
        check("group_move_single_undo", block(editor.draft, "date")["rect"] == [60, 60, 220, 80])
        editor.redo_btn.click()
        check("group_move_redo", block(editor.draft, "date")["rect"] == [76, 84, 220, 80])
        capture("interaction-multiple-selection", editor)

        for direction, delta, expected in (
            ("nw", (-16, -16), [44, 44, 236, 96]),
            ("n", (0, -16), [60, 44, 220, 96]),
            ("ne", (16, -16), [60, 44, 236, 96]),
            ("e", (16, 0), [60, 60, 236, 80]),
            ("se", (16, 16), [60, 60, 236, 96]),
            ("s", (0, 16), [60, 60, 220, 96]),
            ("sw", (-16, 16), [44, 60, 236, 96]),
            ("w", (-16, 0), [44, 60, 236, 80]),
        ):
            load()
            canvas.select_block("date")
            center = canvas.handle_rects()[direction].center()
            start = (round(center.x()), round(center.y()))
            mouse(start, (start[0] + delta[0], start[1] + delta[1]))
            check(
                f"resize_handle_{direction}",
                block(editor.draft, "date")["rect"] == expected,
                block(editor.draft, "date")["rect"],
            )
            editor.undo()
            check(
                f"resize_{direction}_undo", block(editor.draft, "date")["rect"] == [60, 60, 220, 80]
            )

        small = fixture()
        block(small, "date")["rect"] = [60, 60, 220, 48]
        load(small)
        canvas.set_zoom(0.25)
        canvas.select_block("date")
        mouse((170, 84), (186, 100))
        check(
            "minimum_height_zoom25_selected_center_moves",
            block(editor.draft, "date")["rect"] == [76, 76, 220, 48],
            block(editor.draft, "date")["rect"],
        )

        for kind in editor.align_buttons:
            data = fixture()
            block(data, "clock")["rect"][1] = 100
            load(data)
            canvas.set_selection({"date", "clock"}, "date")
            editor.preferences_tabs.setCurrentIndex(1)
            editor.align_buttons[kind].click()
            left = block(editor.draft, "date")["rect"]
            right = block(editor.draft, "clock")["rect"]
            position = {
                "left": lambda r: r[0],
                "center_x": lambda r: r[0] + r[2] / 2,
                "right": lambda r: r[0] + r[2],
                "top": lambda r: r[1],
                "center_y": lambda r: r[1] + r[3] / 2,
                "bottom": lambda r: r[1] + r[3],
            }[kind]
            check(f"align_{kind}", position(left) == position(right), [left, right])
            editor.undo()
            check(f"align_{kind}_undo", editor.draft == data)

        for axis in ("x", "y"):
            data = fixture()
            placements = {
                "date": [60, 60, 180, 64],
                "clock": [390, 300, 100, 64],
                "filters": [720, 580, 200, 80],
            }
            for item in data["blocks"]:
                item["enabled"] = item["id"] in placements
                if item["enabled"]:
                    item["rect"] = placements[item["id"]]
            load(data)
            canvas.set_selection(set(placements), "date")
            editor.distribute_buttons[axis].click()
            check(
                f"distribute_{axis}",
                block(editor.draft, "clock")["rect"][0 if axis == "x" else 1]
                == (430 if axis == "x" else 320),
                block(editor.draft, "clock")["rect"],
            )

        load()
        canvas.select_block("date")
        editor.preferences_tabs.setCurrentIndex(1)
        editor.rect_spins["x"].setValue(91)
        check("numeric_geometry_edit", block(editor.draft, "date")["rect"][0] == 91)
        canvas.setFocus()
        QTest.keyClick(canvas, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
        check("shift_keyboard_nudge", block(editor.draft, "date")["rect"][0] == 101)
        editor.activateWindow()
        QTest.keyClick(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        settle()
        check("ctrl_z_shortcut", block(editor.draft, "date")["rect"][0] == 91)

        load()
        editor.preferences_tabs.setCurrentIndex(2)
        editor.snap_checkbox.setChecked(True)
        canvas.select_block("date")
        mouse((170, 100), (175, 105))
        check(
            "grid_snap",
            block(editor.draft, "date")["rect"][:2] == [64, 64],
            block(editor.draft, "date")["rect"],
        )
        load()
        editor.snap_checkbox.setChecked(True)
        canvas.set_zoom(1)
        canvas.select_block("date")
        mouse((170, 100), (175, 105), Qt.KeyboardModifier.AltModifier)
        check(
            "alt_bypasses_grid",
            block(editor.draft, "date")["rect"][:2] == [65, 65],
            block(editor.draft, "date")["rect"],
        )
        for enabled, expected in ((False, 64), (True, 60)):
            load()
            editor.guides_checkbox.setChecked(enabled)
            canvas.set_zoom(1)
            canvas.select_block("date")
            mouse((170, 100), (174, 100))
            check(
                f"optional_smart_guides_{enabled}",
                block(editor.draft, "date")["rect"][0] == expected,
                block(editor.draft, "date")["rect"],
            )
        load()
        editor.guides_checkbox.setChecked(True)
        canvas.select_block("date")
        mouse((170, 100), (174, 100), release=False)
        check("smart_guide_visible_during_move", bool(canvas.active_guides), canvas.active_guides)
        capture("interaction-smart-guide", editor)
        QTest.mouseRelease(
            canvas, Qt.MouseButton.LeftButton, pos=canvas.logical_to_screen(QPoint(174, 100))
        )
        load()
        canvas.select_block("date")
        capture("interaction-eight-handles", editor)
        prior = copy.deepcopy(editor.draft)
        mouse((170, 100), (230, 130), release=False)
        QTest.keyClick(canvas, Qt.Key.Key_Escape)
        QTest.mouseRelease(
            canvas, Qt.MouseButton.LeftButton, pos=canvas.logical_to_screen(QPoint(230, 130))
        )
        check("escape_cancels_gesture", editor.draft == prior and not canvas.selected_ids)

        data = fixture()
        block(data, "clock")["rect"] = [100, 80, 140, 80]
        load(data)
        editor.preferences_tabs.setCurrentIndex(0)
        canvas.select_block("date")
        editor.front_btn.click()
        check("layer_front_order", editor.draft["order"][-1] == "date")
        QTest.mouseClick(
            canvas, Qt.MouseButton.LeftButton, pos=canvas.logical_to_screen(QPoint(170, 100))
        )
        check("layer_front_hit", canvas.selected_id == "date")
        editor.back_btn.click()
        check("layer_back_order", editor.draft["order"][0] == "date")
        QTest.mouseClick(
            canvas, Qt.MouseButton.LeftButton, pos=canvas.logical_to_screen(QPoint(170, 100))
        )
        check("layer_back_hit", canvas.selected_id == "clock")
        check(
            "overlap_status_visible",
            bool(overlap_pairs(editor.draft)) and "겹침" in editor.status_label.text(),
            editor.status_label.text(),
        )
        canvas.select_block("clock")
        editor.lock_btn.click()
        old = copy.deepcopy(block(editor.draft, "clock")["rect"])
        mouse((170, 100), (202, 116))
        QTest.keyClick(canvas, Qt.Key.Key_Right)
        check(
            "locked_drag_and_keyboard_inert",
            block(editor.draft, "clock")["rect"] == old
            and not editor.rect_spins["x"].isEnabled()
            and not canvas.handle_rects(),
            block(editor.draft, "clock")["rect"],
        )
        capture("interaction-overlap-locked", editor)

        load()
        export = Path(temp) / "export.airlayout.json"
        editor.save_configuration(export)
        check(
            "export_roundtrip_schema",
            model.validate_free_layout(
                json.loads(export.read_text(encoding="utf-8", errors="strict"))
            )
            == editor.draft
            and not list(Path(temp).glob(".export.airlayout.json.*.tmp")),
        )
        changed = fixture()
        block(changed, "date")["rect"][0] = 120
        old = copy.deepcopy(editor.draft)
        load(changed)
        check(
            "import_draft_only",
            editor.draft == changed
            and host.settings.values == before
            and controller.widget.geometry() == live_geometry,
        )
        editor.undo()
        check("import_single_undo", editor.draft == old)
        for case, mutate in (
            ("version", lambda d: d.update(version=2)),
            ("duplicate_block", lambda d: d["blocks"].append(copy.deepcopy(d["blocks"][0]))),
            ("locked_type", lambda d: d["blocks"][0].update(locked="yes")),
            ("duplicate_order", lambda d: d["order"].append(d["order"][0])),
            ("nan", lambda d: d["blocks"][0]["rect"].__setitem__(0, float("nan"))),
        ):
            invalid = fixture()
            mutate(invalid)
            fixture_path.write_text(json.dumps(invalid), encoding="utf-8", errors="strict")
            prior = copy.deepcopy(editor.draft)
            rejected = False
            try:
                editor.load_configuration(fixture_path)
            except (ValueError, TypeError, OverflowError):
                rejected = True
            check(f"invalid_import_{case}_atomic", rejected and editor.draft == prior)
        fixture_path.write_bytes(b" " * (256 * 1024 + 1))
        try:
            editor.load_configuration(fixture_path)
            rejected = False
        except ValueError:
            rejected = True
        check("oversize_import_rejected", rejected)
        editor.preview_checkbox.setChecked(False)
        check(
            "preview_toggle_off",
            editor.canvas._preview_image is None and not editor._preview_timer.isActive(),
        )
        editor.preview_checkbox.setChecked(True)
        settle()
        check(
            "preview_toggle_on",
            editor.canvas._preview_image is not None and not editor.canvas._preview_image.isNull(),
        )
        appearance_before = copy.deepcopy(editor.appearance)
        image_before = editor.canvas._preview_image.toImage().copy()
        editor.preferences_tabs.setCurrentIndex(3)
        editor.font_size.setValue(18)
        settle()
        check(
            "appearance_font_size_changes_actual_pixels",
            editor.appearance["widget_mode_font_size"] == 18
            and editor.canvas._preview_image.toImage() != image_before,
        )
        check("appearance_preview_does_not_write_live", host.settings.values == before)
        editor.undo()
        settle()
        restored_controls = (
            editor.appearance == appearance_before
            and editor.font_size.value() == appearance_before["widget_mode_font_size"]
        )
        image_before.save(str(output / "appearance-before.png"))
        editor.canvas._preview_image.save(str(output / "appearance-after-undo.png"))
        check(
            "appearance_undo_restores_controls_and_renderer",
            restored_controls
            and editor._renderer.settings.value("widget_mode_font_size")
            == appearance_before["widget_mode_font_size"],
            {
                "controls": restored_controls,
                "exact_pixel_match": editor.canvas._preview_image.toImage() == image_before,
            },
        )
        editor.redo()
        settle()
        check(
            "appearance_redo_restores_font_size",
            editor.font_size.value() == 18
            and editor._renderer.settings.value("widget_mode_font_size") == 18,
        )
        editor.font_family.setCurrentFont(QFont("Arial"))
        editor.font_weight.setCurrentIndex(editor.font_weight.findData(700))
        editor.text_opacity.setValue(55)
        editor.background_opacity.setValue(30)
        editor.skin_combo.setCurrentIndex(editor.skin_combo.findData("classic_dark"))
        settle()
        alpha = (
            editor.canvas._preview_image.toImage()
            .pixelColor(2, editor.draft["canvas"][1] - 2)
            .alpha()
        )
        check(
            "appearance_font_family_weight_rendered",
            editor._renderer.window.font().family() == "Arial"
            and editor._renderer.settings.value("widget_mode_font_weight") == 700,
        )
        check(
            "appearance_opacity_and_skin_rendered",
            0 < alpha < 255
            and editor._renderer.window._style_signature[-1] == (55, 30)
            and editor._renderer.settings.value("widget_mode_skin") == "classic_dark",
            {"alpha": alpha, "signature": editor._renderer.window._style_signature[-1]},
        )
        appearance_changed = copy.deepcopy(editor.appearance)
        canvas.select_block("date")
        editor.rect_spins["x"].setValue(140)
        editor.undo()
        check("geometry_undo_preserves_appearance", editor.appearance == appearance_changed)
        editor.undo()
        check(
            "same_history_undo_appearance",
            editor.appearance["widget_mode_skin"] == appearance_before["widget_mode_skin"],
        )
        editor.redo()
        check("same_history_redo_appearance", editor.appearance == appearance_changed)
        capture("appearance-draft-native-pixels", editor)
        check(
            "appearance_draft_settings_and_live_unchanged",
            host.settings.values == before and controller.widget.geometry() == live_geometry,
        )
        check(
            "preview_host_callbacks_inert",
            all(
                getattr(host, name).call_count == 0
                for name in (
                    "open_task_dialog",
                    "open_modify_task_dialog",
                    "handle_task_status_changed",
                    "handle_directive_status_changed",
                )
            ),
        )
        editor.reject()
        check(
            "cancel_preserves_settings_and_live_geometry",
            host.settings.values == before and controller.widget.geometry() == live_geometry,
        )
        close(host, controller, editor)

        host, controller, editor, before, _initial = make(empty=True)
        editor.fit_btn.click()
        settle()
        capture("current-cached-empty", editor)
        check("empty_cached_preview_contains_zero_rows", not editor._renderer.window._last_items)
        close(host, controller, editor)

        host, controller, editor, before, _initial = make()
        controller.widget.set_filter("work")
        controller.widget.clock_label.setText("09:41")
        editor._refresh_preview()
        check(
            "current_filter_and_clock_preserved",
            editor._renderer.window._active_filter == "work"
            and editor._renderer.window.clock_label.text() == "09:41",
        )
        check(
            "current_filter_rows_preserved",
            [row.item_key for row in editor._renderer.window._agenda_rows] == [("task", 2)],
            [list(row.item_key) for row in editor._renderer.window._agenda_rows],
        )
        capture("current-work-filter-clock", editor)
        check(
            "preview_filter_has_no_source_writes",
            host.settings.value("widget_mode_filter") == "work",
        )
        large = fixture()
        large["canvas"] = [2400, 1800]
        editor._replace(large)
        editor.resize(900, 650)
        settle()
        editor.fit_btn.click()
        settle()
        check(
            "large_canvas_fit_below_25_percent",
            0.1 <= editor.canvas.zoom < 0.25
            and editor.canvas.width() <= editor.canvas_scroll.viewport().width()
            and editor.canvas.height() <= editor.canvas_scroll.viewport().height(),
            {
                "zoom": editor.canvas.zoom,
                "canvas": [editor.canvas.width(), editor.canvas.height()],
                "viewport": [
                    editor.canvas_scroll.viewport().width(),
                    editor.canvas_scroll.viewport().height(),
                ],
            },
        )
        editor.canvas.set_zoom(0.1)
        check(
            "minimum_zoom_10_percent",
            editor.canvas.width() == 240 and editor.canvas.height() == 180,
        )
        capture("large-canvas-fit-10-percent", editor)
        close(host, controller, editor)

        for language, theme in (("ko", "light"), ("ko", "dark"), ("de", "light")):
            host, controller, editor, before, initial = make(language, theme)
            for width, height in ((1200, 800), (900, 650)):
                editor.resize(width, height)
                settle()
                editor.fit_btn.click()
                settle()
                for tab in range(4):
                    editor.preferences_tabs.setCurrentIndex(tab)
                    capture(
                        f"{language}-{theme}-{width}x{height}-tab{tab}",
                        editor,
                        {"constructor_size": initial, "requested_size": [width, height]},
                    )
                check(
                    f"{language}_{theme}_{width}_footer_reachable",
                    all(
                        editor.rect().contains(control.mapTo(editor, QPoint(1, 1)))
                        and editor.rect().contains(
                            control.mapTo(editor, QPoint(control.width() - 2, control.height() - 2))
                        )
                        for control in (
                            editor.apply_btn,
                            editor.cancel_btn,
                            editor.import_btn,
                            editor.export_btn,
                        )
                    ),
                )
                check(
                    f"{language}_{theme}_{width}_canvas_fit",
                    editor.canvas.width() <= editor.canvas_scroll.viewport().width()
                    and editor.canvas.height() <= editor.canvas_scroll.viewport().height(),
                )
            editor.canvas._preview_image.save(
                str(output / f"{language}-{theme}-native-preview.png")
            )
            split = fixture()
            block(split, "agenda")["enabled"] = False
            for name, x in (("schedule", 60), ("work", 360), ("directive", 660)):
                block(split, name).update(enabled=True, rect=[x, 460, 280, 220])
            editor._replace(split)
            editor.canvas.select_block("work")
            editor.preferences_tabs.setCurrentIndex(1)
            editor._refresh_preview()
            capture(f"{language}-{theme}-split-panels", editor)
            check(f"{language}_{theme}_split_preview_disjoint", not overlap_pairs(editor.draft))
            check(f"{language}_{theme}_matrix_cancel_isolated", host.settings.values == before)
            close(host, controller, editor)

        host, controller, editor, before, _initial = make()
        changed = fixture()
        block(changed, "date")["rect"][0] = 100
        fixture_path.write_text(json.dumps(changed), encoding="utf-8", errors="strict")
        editor.load_configuration(fixture_path)
        editor.font_size.setValue(18)
        editor.text_opacity.setValue(55)
        editor.background_opacity.setValue(30)
        expected_appearance = copy.deepcopy(editor.appearance)
        editor.apply_btn.click()
        settle()
        check(
            "apply_persists_and_updates_runtime",
            model.read_free_layout(host.settings) == changed
            and controller.widget._free_runtime.data == changed,
        )
        check(
            "appearance_apply_saves_known_keys",
            all(host.settings.value(key) == value for key, value in expected_appearance.items())
            and controller.widget._style_signature[-1] == (55, 30),
        )
        reopened = WidgetFreeLayoutEditorDialog(controller)
        reopened.show()
        settle()
        check(
            "reopen_restores_applied_appearance_and_layout",
            reopened.appearance == expected_appearance and reopened.draft == changed,
        )
        reopened.reject()
        reopened.deleteLater()
        close(host, controller, editor)
        report["summary"] = {
            "checks": len(report["checks"]),
            "failed": sum(not item["passed"] for item in report["checks"]),
            "screenshots": len(report["observations"]),
        }
        (output / "observations.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", errors="strict"
        )
        logging.shutdown()
        print(json.dumps({"output": str(output), **report["summary"]}))
        if report["summary"]["failed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
