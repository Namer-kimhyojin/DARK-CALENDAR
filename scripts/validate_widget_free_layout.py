# -*- coding: utf-8 -*-
"""Isolated Windows Qt acceptance observations for freely arranged widget blocks.

Launch separate processes with QT_SCALE_FACTOR=1, 1.5, or 2. Uses only the
test Host, an isolated translation settings file and synthetic agenda caches.
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", default="final")
    parser.add_argument("--skip-editor", action="store_true")
    args = parser.parse_args()
    os.environ["QT_QPA_PLATFORM"] = "windows" if sys.platform == "win32" else "offscreen"
    scale = os.environ.get("QT_SCALE_FACTOR", "1")
    output = ROOT / "artifacts/widget-free-layout-20261001" / f"{args.phase}-scale-{scale}"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="air-free-layout-qa-", ignore_cleanup_errors=True
    ) as temp:
        os.environ["LOCALAPPDATA"] = temp
        os.environ["APPDATA"] = temp
        from PyQt6 import QtCore
        from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR, QDate, QPoint, QSettings, Qt
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QAbstractButton, QApplication, QCheckBox, QScrollArea

        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        isolated = QSettings(str(Path(temp) / "settings.ini"), QSettings.Format.IniFormat)
        isolated.setValue("language", "ko")
        isolated.setValue("text_theme", "light")
        isolated.setValue("panel_base_color", "#f3f6fb")
        isolated.setValue("theme_color", "#3a7bbf")
        isolated.sync()

        class IsolatedSettings(QSettings):
            """Keep indirect dialog/theme reads in the test INI, including new imports."""

            def __init__(self, *unused_args, **unused_kwargs):
                super().__init__(str(Path(temp) / "settings.ini"), QSettings.Format.IniFormat)

        with patch.object(QtCore, "QSettings", IsolatedSettings):
            from tests.test_widget_mode_ux import Host

            from calendar_app.infrastructure import i18n as translations
            from calendar_app.presentation.dialogs.widget_free_layout_editor import (
                WidgetFreeLayoutEditorDialog,
            )
            from calendar_app.presentation.widgets import widget_free_layout as model
            from calendar_app.presentation.widgets.unified_widget_mode import (
                AgendaItemWidget,
                UnifiedWidgetController,
            )

        translations.i18n.lang = "ko"
        translations.i18n.translations = json.loads(
            (ROOT / "locales/ko.json").read_text(encoding="utf-8", errors="strict")
        )
        translations.i18n.bundled_translations = {}
        translations.i18n.fallback_translations = json.loads(
            (ROOT / "locales/en.json").read_text(encoding="utf-8", errors="strict")
        )
        translations.i18n._apply_qt_locale("ko")
        report = {
            "environment": {
                "platform": platform.platform(),
                "python": sys.version,
                "qt": QT_VERSION_STR,
                "pyqt": PYQT_VERSION_STR,
                "qt_platform": app.platformName(),
                "scale_factor": scale,
                "production_settings_or_db_written": False,
            },
            "checks": [],
            "observations": [],
            "limits": [
                "Synthetic data and test-only settings.",
                "Separate Qt scale-factor processes; no physical mixed-DPI monitor move.",
                "No screen-reader or long-session acceptance.",
                "Representative arrangements; freely overlapping user rectangles are intentional.",
            ],
        }

        def check(name, passed, detail=None):
            report["checks"].append({"name": name, "passed": bool(passed), "detail": detail})

        def settle():
            for _ in range(3):
                app.processEvents()
            QTest.qWait(30)
            for _ in range(3):
                app.processEvents()

        def host_with_data():
            host = Host()
            host.current_date = QDate(2026, 10, 1)
            host._latest_calendar_range_data = {
                "range_start": "2026-09-01",
                "range_end": "2026-11-01",
                "rows": [
                    {"id": 1, "name": "회의 일정 · 자유 배치 QA", "deadline": "2026-10-01 14:00:00"}
                ],
            }
            host._latest_directive_data = {
                "context_date": "2026-10-01",
                "routine_rows": [
                    {
                        "id": 2,
                        "name": "자료 정리 · 긴 제목과 완료 동작 확인",
                        "target_date": "2026-10-01",
                        "status": "in_progress",
                    }
                ],
                "directive_rows": [(3, "검토 의견 전달", "pending", "", "2026-10-01")],
            }
            host.settings.values.update(
                {"widget_mode_always_top": False, "widget_mode_skin": "classic_light"}
            )
            return host

        def create(host, size):
            controller = UnifiedWidgetController(host)
            controller.show_widget()
            widget = controller.widget
            if size is not None:
                widget.resize(*size)
            widget.timer.stop()
            settle()
            return controller, widget

        def destroy(host, controller, widget):
            controller.prepare_shutdown()
            widget.close()
            widget.deleteLater()
            host.deleteLater()
            app.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
            settle()

        def geometry(widget, control):
            origin = control.mapTo(widget, QPoint())
            return [origin.x(), origin.y(), control.width(), control.height()]

        def capture(name, widget, extra=None):
            path = output / f"{name}.png"
            widget.grab().save(str(path))
            rows = widget.findChildren(AgendaItemWidget)
            scrolls = widget.findChildren(QScrollArea)
            buttons = widget.findChildren(QAbstractButton)
            observation = {
                "scenario": name,
                "actual_size": [widget.width(), widget.height()],
                "device_pixel_ratio": widget.devicePixelRatioF(),
                "screenshot": str(path.relative_to(ROOT)).replace("\\", "/"),
                "scrolls": [
                    {
                        "object_name": scroll.objectName(),
                        "visible": scroll.isVisible(),
                        "geometry": geometry(widget, scroll),
                        "viewport": [scroll.viewport().width(), scroll.viewport().height()],
                        "horizontal_max": scroll.horizontalScrollBar().maximum(),
                        "vertical_max": scroll.verticalScrollBar().maximum(),
                    }
                    for scroll in scrolls
                ],
                "rows": [
                    {"key": list(getattr(row, "item_key", ())), "geometry": geometry(widget, row)}
                    for row in rows
                    if row.isVisible()
                ],
                "buttons": [
                    {
                        "object_name": button.objectName(),
                        "text": button.text(),
                        "accessible_name": button.accessibleName(),
                        "geometry": geometry(widget, button),
                    }
                    for button in buttons
                    if button.isVisible()
                ],
            }
            if extra:
                observation.update(extra)
            report["observations"].append(observation)

        def rectangle_pairs(blocks):
            keys = list(blocks)
            return [
                [left, right]
                for index, left in enumerate(keys)
                for right in keys[index + 1 :]
                if QtCore.QRect(*blocks[left]).intersects(QtCore.QRect(*blocks[right]))
            ]

        single = model.seed_free_layout("stacked")
        split = model.seed_free_layout("stacked")
        split["canvas"] = [1100, 680]
        placements = {
            "date": [20, 12, 280, 48],
            "clock": [960, 12, 120, 48],
            "calendar": [20, 80, 1060, 150],
            "filters": [20, 250, 1060, 72],
            "schedule": [20, 342, 330, 318],
            "work": [385, 342, 330, 318],
            "directive": [750, 342, 330, 318],
        }
        for block in split["blocks"]:
            block["enabled"] = block["id"] in placements
            if block["enabled"]:
                block["rect"] = placements[block["id"]]
        split = model.validate_free_layout(split)
        check("saved_split_rectangles_disjoint", not rectangle_pairs(placements))

        for width, height in ((320, 480), (420, 520), (760, 600), (1100, 740)):
            for name, configuration in (("single", single), ("split", split)):
                host = host_with_data()
                host.settings.setValue("widget_mode_filter", "schedule")
                model.write_free_layout(host.settings, configuration)
                controller, widget = create(host, (width, height))
                runtime = widget._free_runtime
                configured = {
                    block["id"]: block["rect"]
                    for block in configuration["blocks"]
                    if block["enabled"]
                }
                actual = {
                    block_id: list(frame.geometry().getRect())
                    for block_id, frame in runtime.frames.items()
                    if frame.isVisible()
                }
                visible_rows = {
                    kind: [list(row.item_key) for row in panel.rows]
                    for kind, panel in runtime.panels.items()
                    if panel.isVisible()
                }
                check(
                    f"{name}_{width}_global_filter_preserved",
                    widget._active_filter == "schedule"
                    and host.settings.value("widget_mode_filter") == "schedule",
                )
                if name == "split":
                    check(
                        f"split_{width}_typed_projections_independent",
                        visible_rows
                        == {
                            "schedule": [["task", 1]],
                            "work": [["task", 2]],
                            "directive": [["directive", 3]],
                        },
                        visible_rows,
                    )
                capture(
                    f"{name}-{width}x{height}",
                    widget,
                    {
                        "requested_size": [width, height],
                        "configured_canvas": configuration["canvas"],
                        "configured_rectangles": configured,
                        "runtime_rectangles": actual,
                        "saved_overlaps": rectangle_pairs(configured),
                        "runtime_overlaps": rectangle_pairs(actual),
                        "typed_rows": visible_rows,
                        "active_filter": widget._active_filter,
                    },
                )
                destroy(host, controller, widget)

        for skin in ("classic_light", "classic_dark"):
            for width, height in ((320, 480), (420, 520)):
                for font_size in (12, 18):
                    host = host_with_data()
                    host.settings.values.update(
                        {
                            "widget_mode_skin": skin,
                            "widget_mode_font_size": font_size,
                            "widget_mode_layout": "stacked",
                        }
                    )
                    controller, widget = create(host, (width, height))
                    widget.cal_grid._buttons[3].setFocus()
                    settle()
                    crop = output / f"week-{skin}-{width}-font-{font_size}-calendar.png"
                    calendar_region = QtCore.QRect(
                        widget.cal_grid.mapTo(widget, QPoint()), widget.cal_grid.size()
                    )
                    widget.grab(calendar_region).save(str(crop))
                    capture(
                        f"week-{skin}-{width}-font-{font_size}",
                        widget,
                        {
                            "requested_size": [width, height],
                            "font_size": font_size,
                            "skin": skin,
                            "calendar_crop": str(crop.relative_to(ROOT)).replace("\\", "/"),
                            "calendar_geometry": geometry(widget, widget.cal_grid),
                            "days": [
                                {
                                    "geometry": geometry(widget.cal_grid, button),
                                    "accessible_name": button.accessibleName(),
                                    "focus": button.hasFocus(),
                                }
                                for button in widget.cal_grid._buttons
                            ],
                        },
                    )
                    target_day = widget.cal_grid._dates[4]
                    widget.cal_grid._buttons[4].setFocus()
                    QTest.keyClick(widget.cal_grid._buttons[4], Qt.Key.Key_Space)
                    settle()
                    check(
                        f"week_{skin}_{width}_{font_size}_keyboard_date_action",
                        host.current_date == target_day,
                    )
                    destroy(host, controller, widget)

        host = host_with_data()
        model.write_free_layout(host.settings, split)
        controller, widget = create(host, (1100, 740))
        runtime = widget._free_runtime
        filter_before = host.settings.value("widget_mode_filter", "all")
        work_row = runtime.panels["work"].rows[0]
        work_row.findChild(QAbstractButton, "agenda_item_title").click()
        settle()
        check(
            "split_work_title_routes_to_original_task_dialog",
            host.open_modify_task_dialog.called,
            repr(host.open_modify_task_dialog.call_args),
        )
        work_row = runtime.panels["work"].rows[0]
        work_row.findChild(QCheckBox, "agenda_complete").click()
        settle()
        check(
            "split_work_completion_uses_original_handler",
            host.handle_task_status_changed.called,
            repr(host.handle_task_status_changed.call_args),
        )
        check(
            "split_completion_does_not_mutate_global_filter",
            host.settings.value("widget_mode_filter", "all") == filter_before,
        )
        widget.undo_btn.click()
        settle()
        check(
            "split_undo_restores_in_progress",
            any(
                item.get("item_id") == 2 and item.get("status") == "in_progress"
                for item in widget._last_items
            ),
        )
        target = host.current_date.addDays(1)
        widget.cal_grid.dateClicked.emit(target)
        settle()
        check("free_calendar_updates_original_context", host.current_date == target)
        controller.set_target_date(QDate(2026, 10, 1))
        settle()
        saved_free = copy.deepcopy(model.read_free_layout(host.settings))
        controller.set_layout("stacked")
        settle()
        check(
            "preset_switch_restores_original_components",
            not widget._free_layout_active
            and widget._free_runtime is None
            and widget.cal_grid.isVisible()
            and widget.filter_section.isVisible()
            and widget.agenda_section.isVisible(),
        )
        check(
            "preset_switch_keeps_free_configuration",
            model.read_free_layout(host.settings) == saved_free,
        )
        widget.resize(760, 600)
        settle()
        capture("preset-weekly-760x600", widget)
        controller.apply_free_layout(saved_free)
        settle()
        check(
            "return_to_free_restores_split_blocks",
            widget._free_layout_active
            and {kind for kind, panel in widget._free_runtime.panels.items() if panel.isVisible()}
            == {"schedule", "work", "directive"},
        )
        restart_values = copy.deepcopy(host.settings.values)
        restart_geometry = list(widget.geometry().getRect())
        destroy(host, controller, widget)
        fresh_host = host_with_data()
        fresh_host.settings.values.update(restart_values)
        controller, widget = create(fresh_host, None)
        check(
            "restart_retains_free_configuration",
            widget._free_layout_active
            and model.read_free_layout(fresh_host.settings) == saved_free,
        )
        check(
            "restart_restores_saved_geometry",
            list(widget.geometry().getRect()) == restart_geometry,
            {"expected": restart_geometry, "actual": list(widget.geometry().getRect())},
        )
        capture("restart-free-restored", widget, {"expected_geometry": restart_geometry})
        destroy(fresh_host, controller, widget)

        if not args.skip_editor:
            host = host_with_data()
            controller, widget = create(host, (760, 600))
            before_settings = copy.deepcopy(host.settings.values)
            before_geometry = widget.geometry()
            editor = WidgetFreeLayoutEditorDialog(controller, widget)
            editor.show()
            settle()
            canvas = editor.canvas
            canvas.select_block("date")
            editor.snap_checkbox.setChecked(False)
            editor.guides_checkbox.setChecked(False)
            initial = canvas.block_rect("date")
            origin = initial.center()
            QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=origin)
            QTest.mouseMove(canvas, origin + QPoint(5, 1))
            QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=origin + QPoint(5, 1))
            settle()
            moved = canvas.block_rect("date")
            check(
                "editor_native_drag_exact_unsnapped",
                moved.topLeft() == initial.topLeft() + QPoint(5, 1),
                {"initial": list(initial.getRect()), "after": list(moved.getRect())},
            )
            origin = moved.bottomRight() - QPoint(5, 5)
            QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=origin)
            QTest.mouseMove(canvas, origin + QPoint(31, 17))
            QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=origin + QPoint(31, 17))
            settle()
            resized = canvas.block_rect("date")
            check(
                "editor_native_corner_resize",
                resized.width() == moved.width() + 31 and resized.height() == moved.height() + 17,
                {"before": list(moved.getRect()), "after": list(resized.getRect())},
            )
            before_numeric = canvas.block_rect("date")
            editor.preferences_tabs.setCurrentIndex(1)
            editor.rect_spins["x"].setValue(before_numeric.x() + 11)
            settle()
            check(
                "editor_numeric_position", canvas.block_rect("date").x() == before_numeric.x() + 11
            )
            numeric = copy.deepcopy(editor.draft)
            canvas.setFocus()
            QTest.keyClick(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
            settle()
            check("editor_keyboard_undo", canvas.block_rect("date") == before_numeric)
            editor.redo_btn.click()
            settle()
            check("editor_redo", editor.draft == numeric)
            old_x = canvas.block_rect("date").x()
            QTest.keyClick(canvas, Qt.Key.Key_Right)
            settle()
            check("editor_keyboard_one_pixel_nudge", canvas.block_rect("date").x() == old_x + 1)
            editor.snap_checkbox.setChecked(True)
            origin = canvas.block_rect("date").center()
            QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=origin)
            QTest.mouseMove(canvas, origin + QPoint(19, 13))
            QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=origin + QPoint(19, 13))
            settle()
            snapped = canvas.block_rect("date")
            check(
                "editor_optional_snap",
                snapped.x() % 8 == 0 and snapped.y() % 8 == 0,
                list(snapped.getRect()),
            )
            origin = snapped.center()
            QTest.mousePress(
                canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.AltModifier, origin
            )
            QTest.mouseMove(canvas, origin + QPoint(3, 5))
            QTest.mouseRelease(
                canvas,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.AltModifier,
                origin + QPoint(3, 5),
            )
            settle()
            check(
                "editor_alt_bypasses_snap",
                canvas.block_rect("date").topLeft() == snapped.topLeft() + QPoint(3, 5),
            )
            editor.canvas_width.setValue(1800)
            editor.canvas_height.setValue(1600)
            editor.preferences_tabs.setCurrentIndex(2)
            settle()
            check(
                "editor_large_canvas_scrolls",
                editor.canvas_scroll.horizontalScrollBar().maximum() > 0
                and editor.canvas_scroll.verticalScrollBar().maximum() > 0,
            )
            capture("editor-gestures", editor, {"draft": copy.deepcopy(editor.draft)})
            check(
                "editor_gestures_never_persist_before_apply",
                host.settings.values == before_settings and widget.geometry() == before_geometry,
            )
            editor.cancel_btn.click()
            settle()
            check(
                "editor_cancel_preserves_settings_and_geometry",
                host.settings.values == before_settings and widget.geometry() == before_geometry,
            )
            editor.deleteLater()
            settle()
            editor = WidgetFreeLayoutEditorDialog(controller, widget)
            editor.show()
            editor.canvas.select_block("date")
            editor.snap_checkbox.setChecked(False)
            editor.rect_spins["x"].setValue(43)
            editor.rect_spins["y"].setValue(31)
            editor.component_checks["agenda"].setChecked(False)
            editor.component_checks["work"].setChecked(True)
            editor.calendar_mode_combo.setCurrentIndex(editor.calendar_mode_combo.findData("month"))
            editor.preferences_tabs.setCurrentIndex(2)
            expected = copy.deepcopy(editor.draft)
            capture("editor-before-apply", editor, {"draft": expected})
            editor.apply_btn.click()
            settle()
            check(
                "editor_apply_uses_persisted_free_mode",
                widget._free_layout_active and model.read_free_layout(host.settings) == expected,
            )
            check(
                "editor_month_selection_reaches_live_calendar",
                widget.cal_grid.display_mode == "month",
            )
            capture("editor-applied-runtime", widget)
            editor.deleteLater()
            settle()
            destroy(host, controller, widget)

        report_path = output / "observations.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            errors="strict",
        )
        logging.shutdown()
        print(str(report_path), flush=True)
        if any(not item["passed"] for item in report["checks"]):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
