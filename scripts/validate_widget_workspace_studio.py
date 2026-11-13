# -*- coding: utf-8 -*-
"""Render workspace features with sample widgets, no live weather and isolated settings."""

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--theme", choices=("light", "dark"), default="dark")
    parser.add_argument("--suffix", default="")
    parser.add_argument("--lang", default="ko", help="Bundled locale code for isolated UI review.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    os.environ["QT_QPA_PLATFORM"] = "windows" if sys.platform == "win32" else "offscreen"
    with tempfile.TemporaryDirectory(prefix="air-studio-qa-", ignore_cleanup_errors=True) as tmp:
        os.environ["LOCALAPPDATA"] = tmp
        os.environ["APPDATA"] = tmp
        from scripts.isolated_settings import install_settings_sandbox

        Settings, verify = install_settings_sandbox(tmp)
        Settings("kimhyojin", "Dark Calendar").setValue("language", args.lang)
        from PyQt6.QtCore import QEvent, QSize, Qt
        from PyQt6.QtGui import QFont, QFontDatabase, QPainter, QPixmap
        from PyQt6.QtWidgets import QApplication
        from tests.test_widget_mode_ux import Host

        from calendar_app.infrastructure.i18n import i18n
        from calendar_app.presentation.dialogs.widget_desktop_layout_dialog import (
            WidgetDesktopLayoutDialog,
        )
        from calendar_app.presentation.dialogs.widget_workspace_options_dialog import (
            WidgetWorkspaceOptionsDialog,
        )
        from calendar_app.presentation.widgets.overlay_manager import OverlayWidgetManager
        from calendar_app.presentation.widgets.overlay_manager_dialog import OverlayManagerDialog
        from calendar_app.presentation.widgets.overlay_weather import OverlayWeatherWidget
        from calendar_app.presentation.widgets.widget_mode_coordinator import WidgetModeCoordinator
        from calendar_app.presentation.widgets.widget_workspace_panel import SaveWorkspaceDialog
        from calendar_app.presentation.widgets.widget_workspace_preview import workspace_thumbnail

        app = QApplication.instance() or QApplication([])
        i18n.apply_application_locale()
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
        host.settings.setValue("widget_mode_layout", "day_brief")
        host.settings.setValue("widget_mode_skin", "studio_porcelain")
        host.settings.setValue("widget_mode_always_top", False)
        host._latest_calendar_range_data["rows"][0].update(
            calendar_id=1, calendar_name="업무 캘린더"
        )
        coordinator = WidgetModeCoordinator(host)
        coordinator.controller.refresh_data = lambda: None
        host._widget_mode_coordinator = coordinator
        manager = OverlayWidgetManager(host)
        host.overlay_manager = manager
        with patch.object(OverlayWeatherWidget, "request_update", lambda self: None):
            ids = []
            for index, (kind, name) in enumerate(
                (
                    ("clock", "업무용 시계"),
                    ("weather", "포항 날씨"),
                    ("date_card", "오늘 날짜"),
                    ("countdown", "집중 시간"),
                    ("text", "이번 주 체크리스트"),
                    ("dday", "프로젝트 마감"),
                )
            ):
                iid = manager.add_instance(kind, name)
                ids.append(iid)
                widget = manager.get_widget(iid)
                if kind == "weather":
                    widget._weather_data.update(
                        city="포항",
                        temp="18",
                        unit="°C",
                        humidity="62",
                        wind="2.4",
                        desc="구름 조금",
                        _wmo=2,
                        _day_period="day",
                        fetched_at=datetime.now(UTC).isoformat(),
                        error="",
                    )
                if kind == "text":
                    widget._set("label_text", "회의 자료 정리\n사업 제안서 검토\n협조 요청 회신")
                widget.apply_graphic_collection("soft_object")
                manager.show_instance(iid)
                widget.move(60 + index % 3 * 350, 90 + index // 3 * 280)
                widget.save_position()
            service = manager.workspace_service()
            service.save_profile("업무용", thumbnail=workspace_thumbnail(manager))
            for index, iid in enumerate(ids):
                if index in {1, 2, 5}:
                    manager.hide_instance(iid)
            service.save_profile("집중용", thumbnail=workspace_thumbnail(manager))
            for index, iid in enumerate(ids):
                if index in {0, 1, 2}:
                    manager.show_instance(iid)
                else:
                    manager.hide_instance(iid)
            service.save_profile("퇴근 후", thumbnail=workspace_thumbnail(manager))
            service.apply_profile(service.state["profiles"][0]["id"])
            service.configure(
                {"motion": "balanced", "pause_fullscreen": False, "automatic": True},
                [
                    {
                        "profile": service.state["profiles"][0]["id"],
                        "days": [1, 2, 3, 4, 5],
                        "start": "09:00",
                        "end": "18:00",
                        "enabled": True,
                    }
                ],
            )
            dialog = OverlayManagerDialog(manager, host)
            host.show()
            dialog.show()
            dialog.resize(1120, 780)
            out = root / "artifacts/widget-studio-20261101/screens" / (args.suffix or args.theme)
            out.mkdir(parents=True, exist_ok=True)

            def capture(window, name):
                for _ in range(4):
                    app.processEvents()
                window.grab().save(str(out / f"{name}.png"))

            capture(dialog, "manager")
            dialog.view_combo.setCurrentIndex(1)
            capture(dialog, "gallery")
            dialog.gallery.list.setCurrentItem(dialog.gallery.items[ids[1]])
            capture(dialog, "weather-inspector")
            dialog.tabs.setCurrentIndex(2)
            capture(dialog, "workspaces")
            save = SaveWorkspaceDialog(service, parent=dialog)
            save.name_edit.setText("회의용 화면")
            save.show()
            capture(save, "save-workspace")
            save.reject()
            save.deleteLater()
            editor = WidgetDesktopLayoutDialog(service, dialog)
            editor.show()
            editor.items_by_id[ids[0]].setSelected(True)
            editor.items_by_id[ids[1]].setSelected(True)
            capture(editor, "desktop-editor")
            editor.reject()
            editor.deleteLater()
            options = WidgetWorkspaceOptionsDialog(service, dialog)
            options.show()
            capture(options, "options")
            options.reject()
            options.deleteLater()
            group_id = service.stacks.create(ids[:2], "시간과 날씨")
            service.stacks.select(group_id, 1)
            bar = service.stacks.bars[group_id]
            weather = manager.get_widget(ids[1])
            for _ in range(3):
                app.processEvents()
            bar_image, weather_image = bar.grab(), weather.grab()
            composite = QPixmap(
                max(bar.width(), weather.width()) + 20, bar.height() + weather.height() + 30
            )
            composite.fill(Qt.GlobalColor.transparent)
            painter = QPainter(composite)
            painter.drawPixmap(10, 5, bar_image)
            painter.drawPixmap(10, 15 + bar.height(), weather_image)
            painter.end()
            composite.save(str(out / "stack.png"))
            if dialog.gallery:
                dialog.tabs.setCurrentIndex(0)
                dialog.resize(QSize(760, 580))
                capture(dialog, "gallery-narrow")
            (out / "result.json").write_text(
                json.dumps(
                    {
                        "theme": args.theme,
                        "scale": os.environ.get("QT_SCALE_FACTOR", "1"),
                        "profiles": len(service.state["profiles"]),
                        "widgets": len(ids),
                        "source_only": True,
                    },
                    indent=2,
                ),
                encoding="utf-8",
                errors="strict",
            )
            dialog.close()
            manager.shutdown()
            coordinator.close_for_shutdown()
            for _, _, _, widget in manager.all_instances():
                widget.deleteLater()
            host.close()
            host.deleteLater()
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
        verify()
        print(out)


if __name__ == "__main__":
    main()
