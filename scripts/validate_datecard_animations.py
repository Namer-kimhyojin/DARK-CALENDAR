# -*- coding: utf-8 -*-
"""Capture the native date GIF cards and chooser with isolated app settings."""

from __future__ import annotations

import argparse
from contextlib import chdir
import json
import os
from pathlib import Path
import sys
import tempfile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="artifacts/date-animations")
    parser.add_argument("--scale", choices=("1", "2"), default="1")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    output = (root / args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)

    with (
        tempfile.TemporaryDirectory(prefix="air-date-gif-qa-", ignore_cleanup_errors=True) as temp,
        chdir(temp),
    ):
        os.environ["LOCALAPPDATA"] = temp
        scale = int(args.scale)
        width, height = (440, 470) if args.compact else (960, 700)
        Path("screen.json").write_text(
            json.dumps({"screens": [{"width": width * scale, "height": height * scale}]}),
            encoding="utf-8",
            errors="strict",
        )
        os.environ["QT_QPA_PLATFORM"] = "offscreen:configfile=screen.json"
        os.environ["QT_SCALE_FACTOR"] = args.scale

        from PyQt6 import QtCore
        from PyQt6.QtCore import QLocale, QRect, Qt
        from PyQt6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPixmap
        from PyQt6.QtWidgets import QApplication, QWidget

        real_settings = QtCore.QSettings

        class IsolatedSettings(real_settings):
            def __init__(self, *values, **kwargs):
                if len(values) >= 2 and values[1] == real_settings.Format.IniFormat:
                    super().__init__(*values, **kwargs)
                else:
                    super().__init__(str(Path(temp) / "air.ini"), real_settings.Format.IniFormat)

        QtCore.QSettings = IsolatedSettings
        settings = IsolatedSettings("kimhyojin", "Dark Calendar")
        settings.setValue("language", "ko")
        settings.setValue("text_theme", "dark")
        QLocale.setDefault(QLocale("ko_KR"))
        app = QApplication([])
        if sys.platform == "win32":
            for font in ("malgun.ttf", "malgunbd.ttf", "segoeui.ttf", "seguisb.ttf"):
                QFontDatabase.addApplicationFont(f"C:/Windows/Fonts/{font}")
        app.setFont(QFont("Malgun Gothic", 10))

        from calendar_app.presentation.widgets.datecard_animation_dialog import DateAnimationDialog
        from calendar_app.presentation.widgets.datecard_animations import DATE_ANIMATIONS
        from calendar_app.presentation.widgets.overlay_datecard import OverlayDateCardWidget

        owner = QWidget()
        owner.settings = settings
        widget = OverlayDateCardWidget(owner)
        widget._set("font_family", "Malgun Gothic")
        widget._set("fixed_w", 244)
        widget._set("fixed_h", 310)
        widget.set_enabled(True)
        canvas = QPixmap(860 * scale, 840 * scale)
        canvas.setDevicePixelRatio(scale)
        canvas.fill(QColor("#141722"))
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#c0addf"))
        painter.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        painter.drawText(40, 38, "AIR CALENDAR  /  ANIMATED DATE CARDS")
        painter.setPen(QColor("#f8f4ff"))
        painter.setFont(QFont("Malgun Gothic", 22, QFont.Weight.Bold))
        painter.drawText(40, 77, "움직이는 날짜 카드 6종")
        for index, animation in enumerate(DATE_ANIMATIONS):
            widget._set_date_animation(animation.animation_id, motion=False)
            app.processEvents()
            preview = widget.grab()
            row, col = divmod(index, 3)
            x, y = 40 + col * 268, 104 + row * 357
            painter.drawPixmap(x, y, preview)
            painter.setFont(QFont("Malgun Gothic", 11, QFont.Weight.DemiBold))
            painter.drawText(
                QRect(x, y + 318, 244, 26), Qt.AlignmentFlag.AlignCenter, animation.title()
            )
        painter.end()
        if not args.compact:
            assert canvas.save(str(output / f"six-designs-{scale}x.png"))

        for theme in ("dark", "light"):
            settings.setValue("text_theme", theme)
            dialog = DateAnimationDialog(widget)
            dialog.show()
            app.processEvents()
            assert dialog.rect().contains(dialog.preview.geometry())
            assert dialog.rect().contains(dialog.choices.geometry())
            suffix = "-compact" if args.compact else ""
            assert dialog.grab().save(str(output / f"chooser-{theme}-{scale}x{suffix}.png"))
            dialog.reject()
            dialog.deleteLater()
            app.processEvents()
        widget.set_enabled(False)
        widget.close()
        owner.close()


if __name__ == "__main__":
    main()
