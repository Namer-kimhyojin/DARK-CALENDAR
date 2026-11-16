# -*- coding: utf-8 -*-
"""Capture the actual widget manager using isolated settings and sample widgets."""

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
    parser.add_argument("--theme", choices=("light", "dark"), default="dark")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    os.environ["QT_QPA_PLATFORM"] = "windows" if sys.platform == "win32" else "offscreen"
    with tempfile.TemporaryDirectory(prefix="air-hub-qa-", ignore_cleanup_errors=True) as tmp:
        os.environ["LOCALAPPDATA"] = tmp
        os.environ["APPDATA"] = tmp
        from scripts.isolated_settings import install_settings_sandbox

        Settings, verify = install_settings_sandbox(tmp)
        from PyQt6.QtGui import QFont, QFontDatabase
        from PyQt6.QtWidgets import QApplication
        from tests.test_widget_mode_ux import Host

        from calendar_app.presentation.widgets.overlay_manager import OverlayWidgetManager
        from calendar_app.presentation.widgets.overlay_manager_dialog import OverlayManagerDialog
        from calendar_app.presentation.widgets.widget_mode_coordinator import WidgetModeCoordinator

        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        for name in ("malgun.ttf", "segoeui.ttf", "seguisb.ttf", "seguisym.ttf"):
            QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + name)
        app.setFont(QFont("Malgun Gothic", 10))
        host = Host()
        host.settings = Settings("kimhyojin", "Dark Calendar")
        host.settings.setValue("text_theme", args.theme)
        host.settings.setValue(
            "panel_base_color", "#f4f6f9" if args.theme == "light" else "#1e1e1e"
        )
        host.settings.setValue("widget_mode_skin", "studio_porcelain")
        host.settings.setValue("widget_mode_layout", "day_brief")
        coordinator = WidgetModeCoordinator(host)
        coordinator.controller.refresh_data = lambda: None
        host._widget_mode_coordinator = coordinator
        manager = OverlayWidgetManager(host)
        host.overlay_manager = manager
        for index, (kind, name) in enumerate(
            (
                ("clock", "업무용 시계"),
                ("date_card", "오늘 날짜"),
                ("text", "이번 주 체크리스트"),
                ("countdown", "집중 시간"),
                ("dday", "프로젝트 마감"),
                ("stopwatch", "작업 시간 측정"),
            )
        ):
            iid = manager.add_instance(kind, name)
            if index % 3:
                manager.show_instance(iid)
        dialog = OverlayManagerDialog(manager, host)
        host.show()
        dialog.show()
        out = root / "artifacts/widget-management-20261101" / args.phase
        if args.suffix:
            out /= args.suffix
        out.mkdir(parents=True, exist_ok=True)

        def capture(name):
            for _ in range(4):
                app.processEvents()
            dialog.grab().save(str(out / f"{name}.png"))

        capture("manager")
        if hasattr(dialog, "tabs"):
            dialog.search_edit.setText("마감")
            capture("search")
            dialog.search_edit.clear()
            dialog.resize(760, 580)
            capture("manager-narrow")
            dialog.tabs.setCurrentIndex(1)
            capture("workspace")
            dialog.mode_panel._enter()
            capture("workspace-active")
            dialog.mode_panel._return_main()
            from calendar_app.presentation.widgets.widget_management_ui import WidgetAddDialog

            gallery = WidgetAddDialog(dialog)
            gallery.show()
            app.processEvents()
            gallery.grab().save(str(out / "add-gallery.png"))
            gallery.reject()
            gallery.deleteLater()
        result = {
            "phase": args.phase,
            "scale": os.environ.get("QT_SCALE_FACTOR", "1"),
            "theme": args.theme,
            "cards": len(dialog._cards),
            "size": [dialog.width(), dialog.height()],
        }
        (out / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8", errors="strict"
        )
        dialog.close()
        coordinator.close_for_shutdown()
        for _, _, _, widget in manager.all_instances():
            widget.set_enabled(False)
            widget.deleteLater()
        host.close()
        app.processEvents()
        verify()
        print(out)


if __name__ == "__main__":
    main()
