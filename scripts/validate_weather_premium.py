# -*- coding: utf-8 -*-
"""Render premium weather cards and measure cached native painting in isolation."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
from unittest.mock import Mock, patch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="artifacts/weather-premium-20261031")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    out = (root / args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ["QT_QPA_PLATFORM"] = "windows" if sys.platform == "win32" else "offscreen"

    from PyQt6 import QtCore
    from PyQt6.QtCore import QRect, QSize, Qt
    from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
    from PyQt6.QtWidgets import QApplication, QWidget

    native_settings = QtCore.QSettings
    original = native_settings("kimhyojin", "Dark Calendar")
    before = {key: original.value(key) for key in original.allKeys()}
    previous_local = os.environ.get("LOCALAPPDATA")
    with tempfile.TemporaryDirectory(
        prefix="air-weather-qa-", ignore_cleanup_errors=True
    ) as temporary:
        os.environ["LOCALAPPDATA"] = temporary

        class SandboxSettings(native_settings):
            def __init__(self, *settings_args, **kwargs):
                if len(settings_args) >= 2 and settings_args[1] == native_settings.Format.IniFormat:
                    super().__init__(*settings_args, **kwargs)
                else:
                    organization, application = (
                        settings_args[:2]
                        if len(settings_args) >= 2
                        else ("kimhyojin", "Dark Calendar")
                    )
                    path = Path(temporary) / str(organization) / (str(application) + ".ini")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    super().__init__(str(path), native_settings.Format.IniFormat)

        QtCore.QSettings = SandboxSettings
        app = QApplication([])
        app.setFont(QFont("Malgun Gothic", 10))
        settings = SandboxSettings("kimhyojin", "Dark Calendar")
        settings.setValue("language", "ko")
        settings.setValue("lang_code", "ko")
        settings.setValue("text_theme", "dark")

        from calendar_app.infrastructure.weather.met_norway import parse_locationforecast
        from calendar_app.presentation.widgets.overlay_weather import OverlayWeatherWidget
        from calendar_app.presentation.widgets.weather_design_dialog import (
            WeatherDesignGalleryDialog,
            weather_design_preview_pixmap,
        )
        from calendar_app.presentation.widgets.weather_designs import weather_design
        from calendar_app.presentation.widgets.weather_scene import SCENE_IDS, WeatherSceneSurface

        now = datetime(2026, 10, 31, 6, tzinfo=UTC)
        payload = {
            "properties": {
                "timeseries": [
                    {
                        "time": (now + timedelta(hours=i)).isoformat(),
                        "data": {
                            "instant": {
                                "details": {
                                    "air_temperature": 18.2 - i * 0.6,
                                    "relative_humidity": 62,
                                    "wind_speed": 2.4,
                                }
                            },
                            "next_1_hours": {
                                "summary": {
                                    "symbol_code": "partlycloudy_day" if i < 3 else "rain_night"
                                },
                                "details": {"precipitation_amount": 0 if i < 3 else 0.4},
                            },
                        },
                    }
                    for i in range(8)
                ]
            }
        }
        sample = parse_locationforecast(payload, "포항", now=now, timezone_name="Asia/Seoul")
        sample.update(desc="구름 조금", fetched_at=now.isoformat(), error="")

        def board(width, height, title):
            image = QPixmap(width, height)
            image.fill(QColor("#101b2b"))
            painter = QPainter(image)
            painter.setPen(QColor("#eef4ff"))
            painter.setFont(QFont("Malgun Gothic", 14, QFont.Weight.Bold))
            painter.drawText(24, 34, title)
            return image, painter

        def draw_card(painter, x, y, width, height, *, scene_id="air_atmosphere", data=None):
            surface = WeatherSceneSurface()
            surface.resize(width, height)
            recipe = weather_design(scene_id)
            surface.configure(
                scene_id=scene_id,
                data=data or sample,
                pack=recipe.asset_pack_id,
                family="Malgun Gothic",
                motion="off",
            )
            image = surface.grab()
            painter.drawPixmap(QRect(x, y, width, height), image)
            surface.deleteLater()

        image, painter = board(1170, 455, "프리미엄 날씨 카드 3종 · 고정 예시 데이터")
        for i, scene_id in enumerate(SCENE_IDS):
            draw_card(painter, 24 + i * 382, 62, 358, 350, scene_id=scene_id)
            painter.setFont(QFont("Malgun Gothic", 10))
            painter.drawText(30 + i * 382, 438, weather_design(scene_id).label_default)
        painter.end()
        image.save(str(out / "premium-designs.png"))

        image, painter = board(990, 450, "크기에 따라 정보 구성이 바뀝니다 · 고정 예시 데이터")
        x = 24
        for width, height in ((180, 140), (320, 240), (380, 350)):
            draw_card(painter, x, 66, width, height)
            painter.setFont(QFont("Malgun Gothic", 10))
            painter.drawText(x, 55, f"{width} × {height}")
            x += width + 24
        painter.end()
        image.save(str(out / "responsive-sizes.png"))

        image, painter = board(1376, 790, "날씨별 화면 · 낮과 밤 · 고정 예시 데이터")
        states = (
            (0, "day", "맑음"),
            (2, "day", "구름 조금"),
            (3, "day", "흐림"),
            (61, "day", "비"),
            (71, "day", "눈"),
            (95, "day", "뇌우"),
            (45, "day", "안개"),
            (0, "night", "맑은 밤"),
        )
        for i, (code, period, label) in enumerate(states):
            data = dict(sample, _wmo=code, _day_period=period, desc=label)
            draw_card(painter, 20 + (i % 4) * 340, 58 + (i // 4) * 360, 320, 340, data=data)
        painter.end()
        image.save(str(out / "weather-states.png"))

        gallery = WeatherDesignGalleryDialog(sample, current_design_id="air_atmosphere")
        gallery.resize(1040, 720)
        for row in range(gallery.grid.count()):
            item = gallery.grid.item(row)
            recipe = weather_design(item.data(Qt.ItemDataRole.UserRole))
            pixmap = weather_design_preview_pixmap(recipe, sample, QSize(168, 104), dpr=2)
            icon = QIcon(pixmap)
            icon.addPixmap(pixmap, QIcon.Mode.Selected)
            item.setIcon(icon)
        gallery.grab().save(str(out / "gallery.png"))
        gallery.close()

        owner = QWidget()
        owner.settings = settings
        network = Mock()
        with patch(
            "calendar_app.presentation.widgets.overlay_weather.get_network_manager",
            return_value=network,
        ):
            overlay = OverlayWeatherWidget(owner)
        overlay._weather_data.update(sample)
        overlay._apply_weather_design("air_atmosphere")
        overlay.render(QPixmap(overlay.size()))
        assert not overlay._scene_surface._timer.isActive()
        overlay._set_runtime_active(False)
        overlay.close()
        owner.close()
        assert network.get.call_count == 0

        surface = WeatherSceneSurface()
        surface.resize(360, 350)
        surface.configure(
            scene_id="air_atmosphere",
            data=dict(sample, _wmo=61, desc="비"),
            family="Malgun Gothic",
            motion="subtle",
        )
        surface.grab()
        timings = []
        for _ in range(100):
            start = time.perf_counter()
            surface.grab()
            timings.append((time.perf_counter() - start) * 1000)
        frames = out / "animation-frames"
        frames.mkdir(exist_ok=True)
        surface._timer.start()
        for i in range(60):
            surface._started = time.monotonic() - i / 20
            surface.grab().save(str(frames / f"{i:03}.png"))
        surface._timer.stop()
        surface.close()
        app.processEvents()
        original.sync()
        assert {key: original.value(key) for key in original.allKeys()} == before
        results = {
            "settings_preserved": True,
            "weather_requests": network.get.call_count,
            "sample_data": True,
            "render_platform": os.environ["QT_QPA_PLATFORM"],
            "cached_card_render_ms_median": round(statistics.median(timings), 3),
            "cached_card_render_ms_p95": round(sorted(timings)[94], 3),
            "animated_preview_frames": 60,
            "animated_preview_fps": 20,
            "note": "Native render timing only; not installed-app CPU or power measurement.",
        }
        (out / "results.json").write_text(
            json.dumps(results, indent=2) + "\n", encoding="utf-8", errors="strict"
        )
        print(json.dumps(results))
        QtCore.QSettings = native_settings
    if previous_local is None:
        os.environ.pop("LOCALAPPDATA", None)
    else:
        os.environ["LOCALAPPDATA"] = previous_local


if __name__ == "__main__":
    main()
