# -*- coding: utf-8 -*-
"""Capture widget-only workspaces with synthetic data and temporary preferences."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("before", "after"), default="after")
    parser.add_argument("--suffix", default="")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    os.environ["QT_QPA_PLATFORM"] = "windows" if sys.platform == "win32" else "offscreen"
    from PyQt6 import QtCore
    from PyQt6.QtCore import QDate, QEvent, QRect, QSize
    from PyQt6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPixmap
    from PyQt6.QtWidgets import QApplication

    native = QtCore.QSettings
    original = native("kimhyojin", "Dark Calendar")
    before = {key: original.value(key) for key in original.allKeys()}
    out = root / "artifacts/widget-workspace-20261101" / args.phase
    if args.suffix:
        out = out / args.suffix
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="air-workspace-qa-", ignore_cleanup_errors=True
    ) as temporary:
        os.environ["LOCALAPPDATA"] = temporary
        os.environ["APPDATA"] = temporary

        class Sandbox(native):
            def __init__(self, *args, **kwargs):
                if len(args) > 1 and args[1] == native.Format.IniFormat:
                    super().__init__(*args, **kwargs)
                else:
                    org, name = args[:2] if len(args) > 1 else ("kimhyojin", "Dark Calendar")
                    path = Path(temporary) / str(org) / (str(name) + ".ini")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    super().__init__(str(path), native.Format.IniFormat)

        QtCore.QSettings = Sandbox
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        for name in ("malgun.ttf", "segoeui.ttf", "seguisb.ttf", "seguisym.ttf"):
            QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + name)
        app.setFont(QFont("Malgun Gothic", 10))
        from tests.test_widget_mode_ux import Host

        from calendar_app.infrastructure.i18n import t
        from calendar_app.presentation.dialogs.widget_customization_dialog import (
            WidgetCustomizationDialog,
        )
        from calendar_app.presentation.widgets.unified_widget_mode import (
            UnifiedWidgetController,
            UnifiedWidgetWindow,
        )
        from calendar_app.presentation.widgets.widget_mode_skins import (
            widget_mode_layouts,
            widget_mode_skins,
        )

        host = Host()
        host.settings.values.update(language="ko", widget_mode_always_top=False)
        controller = UnifiedWidgetController(host)
        controller.refresh_data = lambda: None
        controller.widget = widget = UnifiedWidgetWindow(controller)
        items = [
            {
                "title": title,
                "time": time,
                "is_task": kind != "schedule",
                "item_kind": kind,
                "item_id": index + 1,
                "source": "directive" if kind == "directive" else "task",
                "completed": False,
                "status": "in_progress",
                "read_only": False,
            }
            for index, (title, time, kind) in enumerate(
                (
                    ("주간 프로젝트 회의", "09:30", "schedule"),
                    ("신규 사업 설명회", "14:00", "schedule"),
                    ("사업 제안서 검토", "오늘 마감", "work"),
                    ("회의 자료 정리", "16:00", "work"),
                    ("연구소 방문 일정 확정", "17:00", "work"),
                    ("협조 요청 회신", "오늘 마감", "directive"),
                )
            )
        ]
        widget.update_header(QDate.currentDate())
        widget.show()
        widget.timer.stop()
        layouts = (
            widget_mode_layouts()
            if args.phase == "after"
            else [
                spec
                for spec in widget_mode_layouts()
                if spec.layout_id in {"stacked", "dashboard", "minimal"}
            ]
        )
        for spec in layouts:
            host.settings.values.update(
                widget_mode_layout=spec.layout_id,
                widget_mode_skin="studio_porcelain" if spec.searchable else "classic_light",
            )
            widget.apply_selected_layout(force=True)
            widget.apply_theme()
            widget.resize(QSize(*spec.preferred_size))
            widget.update_agenda(items)
            for _ in range(3):
                app.processEvents()
            widget.grab().save(str(out / (spec.layout_id + ".png")))
        skins = widget_mode_skins()
        board = QPixmap(1480, ((len(skins) + 3) // 4) * 520 + 50)
        board.fill(QColor("#142131"))
        painter = QPainter(board)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setPen(QColor("#f2f6ff"))
        painter.setFont(QFont("Malgun Gothic", 15))
        painter.drawText(20, 30, "위젯 전용 모드 · 실제 렌더링 / 예시 데이터")
        for index, skin in enumerate(skins):
            host.settings.values.update(
                widget_mode_skin=skin.skin_id,
                widget_mode_layout="day_brief" if args.phase == "after" else "stacked",
            )
            widget.apply_selected_layout(force=True)
            widget.apply_theme()
            widget.resize(420, 620)
            widget.update_agenda(items)
            app.processEvents()
            capture = widget.grab()
            x, y = 20 + index % 4 * 365, 50 + index // 4 * 520
            painter.drawPixmap(QRect(x, y, 320, 472), capture)
            painter.setPen(QColor("#f2f6ff"))
            painter.setFont(QFont("Malgun Gothic", 10))
            painter.drawText(x, y + 500, t(skin.label_key, skin.label_default))
        painter.end()
        board.save(str(out / "skins.png"))
        dialog = WidgetCustomizationDialog(controller)
        for index in (0, 1):
            dialog.preferences_tabs.setCurrentIndex(index)
            app.processEvents()
            dialog.grab().save(str(out / f"customize-{index}.png"))
        dialog.reject()
        dialog.deleteLater()
        controller.prepare_shutdown()
        widget.close()
        widget.deleteLater()
        host.close()
        host.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        original.sync()
        assert {key: original.value(key) for key in original.allKeys()} == before
        result = {
            "skins": len(skins),
            "layouts": len(widget_mode_layouts()),
            "settings_preserved": True,
            "sample_data": True,
            "dpr": app.primaryScreen().devicePixelRatio(),
        }
        (out / "results.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8", errors="strict"
        )
        print(json.dumps(result))
        QtCore.QSettings = native


if __name__ == "__main__":
    main()
