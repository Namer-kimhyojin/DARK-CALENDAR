# -*- coding: utf-8 -*-
"""Deterministic widget-mode rendering observations with isolated sample data.

Run from the repository: python scripts/validate_widget_mode_ux_plan.py --phase final
QT_SCALE_FACTOR may be set externally before launch for separate DPI runs.
This renders synthetic data; it does not exercise a production database.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def samples(count: int, revision: int = 0) -> list[dict]:
    items = []
    for index in range(count):
        kind = ("schedule", "work", "directive")[index % 3]
        items.append(
            {
                "title": (
                    f"{index + 1:03d} 검토 의견과 일정 확인 / Review long agenda title "
                    "자료 제출과 협조 요청을 포함한 긴 제목입니다"
                    if index % 7 == 0
                    else f"{index + 1:03d} {kind} 항목"
                )
                + (f" · {revision}" if index == 0 else ""),
                "time": "10월 1일 14:00" if index % 4 else "기한 없음",
                "is_task": kind != "schedule",
                "item_kind": kind,
                "item_id": index + 1,
                "source": "directive" if kind == "directive" else "task",
                "read_only": kind == "schedule" and index % 6 == 0,
                "completed": kind != "schedule" and index % 5 == 0,
                "status": "completed" if index % 5 == 0 else "in_progress",
            }
        )
    return items


def percentile(values: list[float], percentile_value: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * percentile_value) - 1)]


def summarize(values: list[float]) -> dict:
    return {
        "samples": len(values),
        "p50_ms": round(statistics.median(values), 3),
        "p95_ms": round(percentile(values, 0.95), 3),
        "max_ms": round(max(values), 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", default="final")
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--skip-benchmark", action="store_true")
    parser.add_argument("--skip-matrix", action="store_true")
    parser.add_argument("--benchmark-counts", nargs="+", type=int, default=[0, 3, 30, 100, 300])
    args = parser.parse_args()
    if args.repeats < 10:
        parser.error("--repeats must be at least 10")
    os.environ["QT_QPA_PLATFORM"] = "windows" if sys.platform == "win32" else "offscreen"
    scale = os.environ.get("QT_SCALE_FACTOR", "1")
    output = ROOT / "artifacts/widget-mode-ux-improvement-20261001" / f"{args.phase}-scale-{scale}"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="air-widget-qa-", ignore_cleanup_errors=True) as temp:
        # Isolate user skin discovery and translation overrides before app imports.
        os.environ["LOCALAPPDATA"] = temp
        os.environ["APPDATA"] = temp
        from PyQt6 import QtCore
        from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR, QDate, QPoint, QSettings
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QAbstractButton, QApplication, QLabel

        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        isolated = QSettings(str(Path(temp) / "settings.ini"), QSettings.Format.IniFormat)
        isolated.setValue("language", "ko")
        with patch.object(QtCore, "QSettings", return_value=isolated):
            from calendar_app.infrastructure import i18n as translations
        from tests.test_widget_mode_ux import Host

        from calendar_app.presentation.dialogs.widget_customization_dialog import (
            WidgetCustomizationDialog,
        )
        from calendar_app.presentation.widgets.unified_widget_mode import (
            AgendaItemWidget,
            UnifiedWidgetController,
            UnifiedWidgetWindow,
        )
        from calendar_app.presentation.widgets.widget_mode_skins import (
            WidgetModeSkin,
            register_widget_mode_skin,
            widget_mode_layouts,
        )

        register_widget_mode_skin(
            WidgetModeSkin(
                "qa_custom",
                "widget_mode.qa_custom",
                "QA custom",
                base_theme="dark",
                token_overrides={"accent": "#86b7ff", "text_primary": "#f0f4ff"},
            )
        )

        en = json.loads((ROOT / "locales/en.json").read_text(encoding="utf-8", errors="strict"))

        def language(code):
            translations.i18n.lang = code
            translations.i18n.translations = json.loads(
                (ROOT / f"locales/{code}.json").read_text(encoding="utf-8", errors="strict")
            )
            translations.i18n.bundled_translations = {}
            translations.i18n.fallback_translations = en
            translations.i18n._apply_qt_locale(code)

        def settle():
            for _ in range(3):
                app.processEvents()

        def create(
            size=(420, 520), skin="classic_light", layout="stacked", density="standard", count=3
        ):
            host = Host()
            host.current_date = QDate(2026, 10, 1)
            host.settings.values.update(
                {
                    "widget_mode_skin": skin,
                    "widget_mode_layout": layout,
                    "widget_mode_density": density,
                    "widget_mode_always_top": False,
                }
            )
            controller = UnifiedWidgetController(host)
            controller.refresh_data = lambda: None
            controller.widget = UnifiedWidgetWindow(controller)
            widget = controller.widget
            widget.update_header(host.current_date)
            widget.resize(*size)
            widget.show()
            widget.update_agenda(samples(count))
            widget.timer.stop()
            settle()
            return host, controller, widget

        def destroy(host, controller, widget):
            controller.prepare_shutdown()
            widget.close()
            widget.deleteLater()
            host.deleteLater()
            app.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
            settle()

        def geometry(widget, control):
            point = control.mapTo(widget, QPoint(0, 0))
            return [point.x(), point.y(), control.width(), control.height()]

        def live_rows(widget):
            return [
                widget.scroll_layout.itemAt(index).widget()
                for index in range(widget.scroll_layout.count())
                if isinstance(widget.scroll_layout.itemAt(index).widget(), AgendaItemWidget)
            ]

        def observe(widget, requested):
            controls = {}
            for name in (
                "restore_btn",
                "date_picker_btn",
                "today_btn",
                "pin_btn",
                "customize_btn",
                "more_btn",
                "week_toggle_btn",
                "add_btn",
                "compact_filter_btn",
                "completed_btn",
            ):
                control = getattr(widget, name, None)
                if control is not None:
                    controls[name] = {
                        "visible": control.isVisible(),
                        "text": control.text(),
                        "accessible_name": control.accessibleName(),
                        "geometry": geometry(widget, control),
                        "label_width": control.fontMetrics().horizontalAdvance(control.text()),
                        "tool_button_style": control.toolButtonStyle().name,
                        "text_wider_than_control": control.toolButtonStyle().name
                        != "ToolButtonIconOnly"
                        and control.fontMetrics().horizontalAdvance(control.text())
                        > control.width(),
                    }
            filters = {}
            for mode, control in widget._filter_buttons.items():
                filters[mode] = {
                    "visible": control.isVisible(),
                    "text": control.text(),
                    "geometry": geometry(widget, control),
                    "label_width": control.fontMetrics().horizontalAdvance(control.text()),
                    "text_wider_than_control": control.fontMetrics().horizontalAdvance(
                        control.text()
                    )
                    > control.width(),
                }
            rows = live_rows(widget)
            clashes = []
            title_time_clashes = []
            row_details = []
            for row in rows[:8]:
                title = row.findChild(QAbstractButton, "agenda_item_title")
                more = row.findChild(QAbstractButton, "agenda_item_more")
                time_label = row.findChild(QLabel, "agenda_item_time")
                detail = {"height": row.height(), "title": title.toolTip() if title else ""}
                if title and more:
                    title_rect = title.geometry()
                    menu_rect = more.geometry()
                    if title_rect.intersects(menu_rect):
                        clashes.append(detail["title"])
                    detail.update(
                        {
                            "title_geometry": [
                                title_rect.x(),
                                title_rect.y(),
                                title_rect.width(),
                                title_rect.height(),
                            ],
                            "menu_geometry": [
                                menu_rect.x(),
                                menu_rect.y(),
                                menu_rect.width(),
                                menu_rect.height(),
                            ],
                        }
                    )
                if time_label:
                    detail["time_geometry"] = geometry(row, time_label)
                    if (
                        title
                        and time_label.isVisible()
                        and title.geometry().intersects(time_label.geometry())
                    ):
                        title_time_clashes.append(detail["title"])
                row_details.append(detail)
            return {
                "requested_size": list(requested),
                "actual_size": [widget.width(), widget.height()],
                "viewport": [widget.scroll.viewport().width(), widget.scroll.viewport().height()],
                "device_pixel_ratio": widget.devicePixelRatioF(),
                "filter_layout": widget._filter_layout_mode,
                "filters": filters,
                "active_filter": widget._active_filter,
                "controls": controls,
                "rows": len(rows),
                "row_details": row_details,
                "title_menu_overlaps": clashes,
                "title_time_overlaps": title_time_clashes,
                "horizontal_scroll_maximum": widget.scroll.horizontalScrollBar().maximum(),
            }

        report = {
            "environment": {
                "platform": platform.platform(),
                "python": sys.version,
                "qt": QT_VERSION_STR,
                "pyqt": PYQT_VERSION_STR,
                "qt_platform": app.platformName(),
                "scale_factor": scale,
                "screen_dpi": app.primaryScreen().logicalDotsPerInch(),
                "logical_screen_size": [
                    app.primaryScreen().size().width(),
                    app.primaryScreen().size().height(),
                ],
                "synthetic_data": True,
                "production_settings_or_db_written": False,
            },
            "observations": [],
            "benchmarks": [],
            "benchmark_conditions": {
                "size": [420, 520],
                "skin": "classic_light",
                "layout": "stacked",
                "density": "standard",
                "changed": "Only the first item's title changes; stable identity for other rows.",
                "initial": "Fresh empty window, first list render; excludes window construction.",
                "filter": "All to work on a populated window.",
                "repeats": args.repeats,
            },
            "limits": [
                "Synthetic Host data; no real DB, Google sync or Store package.",
                "Separate QT_SCALE_FACTOR processes simulate scale; no physical mixed-DPI monitor move.",
                "No screen-reader, long-session or human comprehension acceptance.",
                "Representative pair coverage, not every skin/layout/density/locale Cartesian combination.",
                "Rendering timings include Qt event/layout processing, exclude filesystem/DB fetching.",
            ],
        }
        language("ko")
        scenarios = [
            (f"ko-{w}x{h}", (w, h), "ko", "classic_light", "stacked", "standard", "ready", 3)
            for w, h in ((320, 480), (360, 560), (420, 520), (760, 600))
        ]
        layouts = [layout.layout_id for layout in widget_mode_layouts()]
        for index, layout in enumerate(layouts):
            scenarios.append(
                (
                    f"layout-{layout}",
                    (760, 600),
                    "ko",
                    "classic_dark",
                    layout,
                    ("compact", "standard", "comfortable")[index % 3],
                    "ready",
                    30,
                )
            )
        for code in ("en", "de", "ja", "zh-CN", "ar"):
            scenarios.append(
                (
                    f"locale-{code}",
                    (360, 560),
                    code,
                    "classic_light",
                    "stacked",
                    "standard",
                    "ready",
                    3,
                )
            )
        scenarios += [
            (
                f"state-{state}",
                (420, 520),
                "ko",
                "forest_mist",
                "stacked",
                "comfortable",
                state,
                count,
            )
            for state, count in (("ready", 0), ("loading", 0), ("delayed", 3))
        ]
        scenarios.append(
            (
                "custom-skin-collapsed",
                (360, 560),
                "ko",
                "qa_custom",
                "stacked",
                "standard",
                "ready",
                30,
            )
        )
        scenarios.append(
            ("long-feedback", (320, 480), "ko", "classic_light", "stacked", "standard", "ready", 3)
        )
        for name, size, code, skin, layout, density, state, count in (
            [] if args.skip_matrix else scenarios
        ):
            language(code)
            host, controller, widget = create(size, skin, layout, density, count)
            if name == "custom-skin-collapsed":
                widget.week_toggle_btn.click()
                widget.resize(*size)
            widget.set_data_state(state)
            if name == "long-feedback":
                widget.show_feedback(
                    "검토 의견 전달과 자료 제출 및 협조 요청을 포함한 매우 긴 항목 " * 12 + "완료",
                    undo=True,
                )
            settle()
            QTest.qWait(30)
            settle()
            observation = observe(widget, size)
            observation.update(
                {
                    "scenario": name,
                    "locale": code,
                    "skin": skin,
                    "layout": layout,
                    "density": density,
                    "data_state": state,
                }
            )
            if name == "long-feedback":
                observation["feedback_geometry"] = geometry(widget, widget.feedback_label)
                observation["feedback_accessible_name"] = widget.feedback_label.accessibleName()
            image_path = output / f"{name}.png"
            widget.grab().save(str(image_path))
            observation["screenshot"] = str(image_path.relative_to(ROOT)).replace("\\", "/")
            report["observations"].append(observation)
            destroy(host, controller, widget)

        if not args.skip_matrix:
            for code in ("ko", "de"):
                language(code)
                host, controller, widget = create()
                before = dict(host.settings.values)
                dialog = WidgetCustomizationDialog(controller, widget)
                dialog.show()
                for index in range(3):
                    dialog.preferences_tabs.setCurrentIndex(index)
                    settle()
                    QTest.qWait(30)
                    settle()
                    image_path = output / f"customize-{code}-tab-{index}.png"
                    dialog.grab().save(str(image_path))
                    layout_controls = {}
                    layout_overlaps = []
                    if index == 0:
                        candidates = dict(dialog.layout_buttons)
                        candidates["all_layouts"] = dialog.all_layouts_btn
                        layout_controls = {
                            key: geometry(dialog, control)
                            for key, control in candidates.items()
                            if control.isVisible()
                        }
                        keys = list(layout_controls)
                        for left_index, left in enumerate(keys):
                            for right in keys[left_index + 1 :]:
                                if QtCore.QRect(*layout_controls[left]).intersects(
                                    QtCore.QRect(*layout_controls[right])
                                ):
                                    layout_overlaps.append([left, right])
                    report["observations"].append(
                        {
                            "scenario": f"customize-{code}-tab-{index}",
                            "locale": code,
                            "actual_size": [dialog.width(), dialog.height()],
                            "preferences_viewport": [
                                dialog.controls_scroll.viewport().width(),
                                dialog.controls_scroll.viewport().height(),
                            ],
                            "preferences_scroll_max": dialog.controls_scroll.verticalScrollBar().maximum(),
                            "layout_controls": layout_controls,
                            "layout_control_overlaps": layout_overlaps,
                            "screenshot": str(image_path.relative_to(ROOT)).replace("\\", "/"),
                        }
                    )
                dialog.reject()
                report["observations"][-1]["cancel_preserved_settings"] = (
                    host.settings.values == before
                )
                dialog.deleteLater()
                settle()
                destroy(host, controller, widget)

        language("ko")
        if not args.skip_benchmark:
            for count in args.benchmark_counts:
                timings = {"initial": [], "changed": [], "unchanged": [], "filter": []}
                unchanged_retained = []
                for repeat in range(args.repeats):
                    host, controller, widget = create(count=0)
                    widget._last_render_key = None
                    start = time.perf_counter()
                    widget.update_agenda(samples(count, repeat))
                    settle()
                    timings["initial"].append((time.perf_counter() - start) * 1000)
                    start = time.perf_counter()
                    widget.update_agenda(samples(count, repeat + 1))
                    settle()
                    timings["changed"].append((time.perf_counter() - start) * 1000)
                    before_rows = live_rows(widget)
                    before = [id(row) for row in before_rows]
                    start = time.perf_counter()
                    widget.update_agenda(samples(count, repeat + 1))
                    settle()
                    timings["unchanged"].append((time.perf_counter() - start) * 1000)
                    after = [id(row) for row in live_rows(widget)]
                    unchanged_retained.append(before == after)
                    start = time.perf_counter()
                    widget.set_filter("work")
                    settle()
                    timings["filter"].append((time.perf_counter() - start) * 1000)
                    destroy(host, controller, widget)
                report["benchmarks"].append(
                    {
                        "count": count,
                        "timings": {key: summarize(values) for key, values in timings.items()},
                        "unchanged_rows_retained": all(unchanged_retained),
                        "changed_is_noop_for_zero_items": count == 0,
                    }
                )
                print(json.dumps(report["benchmarks"][-1], ensure_ascii=True), flush=True)
        report_path = output / "observations.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            errors="strict",
        )
        print(str(report_path), flush=True)
        logging.shutdown()


if __name__ == "__main__":
    main()
