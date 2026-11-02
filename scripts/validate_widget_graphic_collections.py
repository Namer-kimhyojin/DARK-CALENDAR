# -*- coding: utf-8 -*-
"""Capture the eight real widgets and collection dialog using temporary settings."""

from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock, patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="artifacts/widget-graphics-20261101")
    parser.add_argument(
        "--all-designs",
        action="store_true",
        help="Capture ten additional designs for each of eight widget types",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    os.environ["QT_QPA_PLATFORM"] = "windows" if sys.platform == "win32" else "offscreen"
    from PyQt6 import QtCore
    from PyQt6.QtCore import QDate, QDateTime, QRect, Qt
    from PyQt6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPixmap
    from PyQt6.QtWidgets import QApplication, QWidget

    native = QtCore.QSettings
    original = native("kimhyojin", "Dark Calendar")
    before = {key: original.value(key) for key in original.allKeys()}
    previous_local = os.environ.get("LOCALAPPDATA")
    out = root / args.out
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="widget-graphic-qa-", ignore_cleanup_errors=True
    ) as temporary:
        os.environ["LOCALAPPDATA"] = temporary

        class Sandbox(native):
            def __init__(self, *values, **kwargs):
                if len(values) >= 2 and values[1] == native.Format.IniFormat:
                    super().__init__(*values, **kwargs)
                else:
                    org, name = values[:2] if len(values) >= 2 else ("kimhyojin", "Dark Calendar")
                    path = Path(temporary) / str(org) / (str(name) + ".ini")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    super().__init__(str(path), native.Format.IniFormat)

        QtCore.QSettings = Sandbox
        app = QApplication([])
        if sys.platform == "win32":
            QFontDatabase.addApplicationFont("C:/Windows/Fonts/malgun.ttf")
            QFontDatabase.addApplicationFont("C:/Windows/Fonts/seguisb.ttf")
        app.setFont(QFont("Malgun Gothic", 10))
        settings = Sandbox("kimhyojin", "Dark Calendar")
        settings.setValue("language", "ko")
        settings.setValue("text_theme", "dark")
        from calendar_app.infrastructure.i18n import t
        from calendar_app.presentation.widgets.widget_graphic_catalog import DESIGNS_BY_KIND
        from calendar_app.presentation.widgets.widget_graphic_dialog import GraphicCollectionDialog
        from calendar_app.presentation.widgets.widget_graphics import COLLECTIONS

        owner = QWidget()
        owner.settings = settings
        widgets = []
        samples = (
            ("시계", "clock", "Clock"),
            ("날짜", "datecard", "DateCard"),
            ("D-Day", "dday", "DDay"),
            ("스톱워치", "stopwatch", "Stopwatch"),
            ("카운트다운", "countdown", "Countdown"),
            ("텍스트", "text", "Text"),
            ("날씨", "weather", "Weather"),
            ("KeyDeck", "launcher_deck", "LauncherDeck"),
        )
        network = Mock()
        with patch(
            "calendar_app.presentation.widgets.overlay_weather.get_network_manager",
            return_value=network,
        ):
            for label, module, name in samples:
                cls = getattr(
                    importlib.import_module("calendar_app.presentation.widgets.overlay_" + module),
                    "Overlay" + name + "Widget",
                )
                widget = cls(owner)
                if module == "dday":
                    widget._set("dd_label", "제주 여행")
                    widget._set(
                        "dd_target_date", QDate.currentDate().addDays(23).toString("yyyy-MM-dd")
                    )
                    widget._set("dday_moment", "travel")
                elif module == "stopwatch":
                    widget._set("sw_elapsed_ms", 1_422_150)
                elif module == "countdown":
                    target = (
                        QDateTime.currentDateTime().addSecs(1500).toString(Qt.DateFormat.ISODate)
                    )
                    widget._set("cd_target_iso", target)
                    widget._set("cd_duration_target", target)
                    widget._set("cd_duration_seconds", 1500)
                elif module == "text":
                    widget._set(
                        "label_text",
                        "오늘의 집중\n중요한 일부터 하나씩\n완료한 일은 가볍게 정리하세요.",
                    )
                elif module == "weather":
                    widget._weather_data.update(
                        city="포항",
                        temp="18.2",
                        unit="°C",
                        desc="구름 조금",
                        humidity="62",
                        wind="2.4",
                        _wmo=2,
                        _day_period="day",
                        forecast_high="21",
                        forecast_low="15",
                        hourly=[
                            {
                                "label": f"{15 + hour}:00",
                                "temp": str(19 - hour),
                                "_wmo": 2,
                                "_day_period": "day",
                                "precip_mm": 0.0,
                            }
                            for hour in range(6)
                        ],
                    )
                if getattr(widget, "_TEMPLATE_KEY", None) and module not in ("text", "weather"):
                    widget._set(widget._TEMPLATE_KEY, widget._DEFAULT_TEMPLATE)
                if module != "launcher_deck":
                    widget._set("fixed_w", 300)
                    widget._set("fixed_h", 220)
                widgets.append((label, widget))
            for collection in () if args.all_designs else COLLECTIONS:
                board = QPixmap(1320, 620)
                board.fill(QColor("#101a28"))
                painter = QPainter(board)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                painter.setPen(QColor("#eef5ff"))
                painter.setFont(QFont("Malgun Gothic", 15, QFont.Weight.Bold))
                painter.drawText(24, 34, collection.label + " · 실제 위젯 / 고정 예시 데이터")
                for i, (label, widget) in enumerate(widgets):
                    widget.apply_graphic_collection(collection.collection_id, motion=False)
                    widget._set_runtime_active(False)
                    capture = widget.grab()
                    x, y = 24 + i % 4 * 324, 60 + i // 4 * 278
                    ratio = min(300 / capture.width(), 220 / capture.height())
                    width, height = capture.width() * ratio, capture.height() * ratio
                    painter.drawPixmap(
                        QRect(
                            round(x + (300 - width) / 2),
                            round(y + (220 - height) / 2),
                            round(width),
                            round(height),
                        ),
                        capture,
                    )
                    painter.setPen(QColor("#eef5ff"))
                    painter.setFont(QFont("Malgun Gothic", 11))
                    painter.drawText(x + 4, y + 246, label)
                painter.end()
                board.save(str(out / (collection.collection_id + ".png")))

            if args.all_designs:
                for label, widget in widgets:
                    kind = widget._graphic_kind()
                    board = QPixmap(1660, 620)
                    board.fill(QColor("#101a28"))
                    painter = QPainter(board)
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                    painter.setPen(QColor("#eef5ff"))
                    painter.setFont(QFont("Malgun Gothic", 15, QFont.Weight.Bold))
                    painter.drawText(24, 34, label + " · 추가 디자인 10종 / 고정 예시 데이터")
                    for index, design in enumerate(DESIGNS_BY_KIND[kind]):
                        widget.apply_graphic_collection(design.collection_id, motion=False)
                        widget._set_runtime_active(False)
                        capture = widget.grab()
                        x, y = 24 + index % 5 * 328, 60 + index // 5 * 278
                        ratio = min(300 / capture.width(), 220 / capture.height())
                        width, height = capture.width() * ratio, capture.height() * ratio
                        painter.drawPixmap(
                            QRect(
                                round(x + (300 - width) / 2),
                                round(y + (220 - height) / 2),
                                round(width),
                                round(height),
                            ),
                            capture,
                        )
                        painter.setPen(QColor("#eef5ff"))
                        painter.setFont(QFont("Malgun Gothic", 11))
                        painter.drawText(
                            x + 4,
                            y + 246,
                            t("widget_graphics.designs." + design.collection_id, design.label),
                        )
                    painter.end()
                    board.save(str(out / (kind + "-10-designs.png")))
                    gallery = GraphicCollectionDialog(widget, allow_group=True)
                    gallery.grab().save(str(out / (kind + "-gallery.png")))
                    gallery.reject()
                    gallery.deleteLater()

            dialog = GraphicCollectionDialog(widgets[0][1], allow_group=True)
            dialog.resize(800, 560)
            dialog.grab().save(str(out / "collection-dialog.png"))
            dialog.reject()
            for label, widget in widgets:
                if label in {"시계", "스톱워치", "카운트다운", "텍스트", "날씨"}:
                    for width, height in ((160, 120), (320, 220), (480, 360)):
                        widget._set("fixed_w", width)
                        widget._set("fixed_h", height)
                        widget._fit_font_to_size(width, height)
                        widget.grab().save(str(out / f"{widget._graphic_kind()}-{width}.png"))
                widget._set_runtime_active(False)
                widget.close()
            owner.close()
            app.processEvents()
            assert network.get.call_count == 0
        original.sync()
        assert {key: original.value(key) for key in original.allKeys()} == before
        result = {
            "settings_preserved": True,
            "network_requests": 0,
            "collections_per_widget": 13,
            "additional_designs": 80 if args.all_designs else 0,
            "widget_types": 8,
            "sample_data": True,
            "device_pixel_ratio": app.primaryScreen().devicePixelRatio(),
        }
        (out / "results.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8", errors="strict"
        )
        print(json.dumps(result))
        QtCore.QSettings = native
    if previous_local is None:
        os.environ.pop("LOCALAPPDATA", None)
    else:
        os.environ["LOCALAPPDATA"] = previous_local


if __name__ == "__main__":
    main()
