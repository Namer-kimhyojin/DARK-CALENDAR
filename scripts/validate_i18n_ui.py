# -*- coding: utf-8 -*-
"""Capture localized manager/options with isolated settings and no network widgets."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locales", nargs="*", help="Default: all bundled catalogs.")
    parser.add_argument("--theme", choices=("dark", "light"), default="dark")
    parser.add_argument("--scale", choices=("1", "2"), default="1")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    os.environ["QT_QPA_PLATFORM"] = "windows" if sys.platform == "win32" else "offscreen"
    os.environ["QT_SCALE_FACTOR"] = args.scale
    with tempfile.TemporaryDirectory(
        prefix="air-i18n-ui-", ignore_cleanup_errors=True
    ) as temporary:
        os.environ["LOCALAPPDATA"] = temporary
        os.environ["APPDATA"] = temporary
        from scripts.isolated_settings import install_settings_sandbox

        Settings, verify = install_settings_sandbox(temporary)
        Settings("kimhyojin", "Dark Calendar").setValue("language", "en")
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QFont, QFontDatabase
        from PyQt6.QtWidgets import QApplication, QLabel
        from tests.test_widget_mode_ux import Host

        from calendar_app.infrastructure.i18n import i18n, t
        from calendar_app.presentation.dialogs.widget_workspace_options_dialog import (
            WidgetWorkspaceOptionsDialog,
        )
        from calendar_app.presentation.widgets.overlay_manager import OverlayWidgetManager
        from calendar_app.presentation.widgets.overlay_manager_dialog import OverlayManagerDialog

        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        for name in ("segoeui.ttf", "malgun.ttf", "seguisym.ttf"):
            QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + name)
        app.setFont(QFont("Segoe UI", 10))
        codes = args.locales or sorted(path.stem for path in (root / "locales").glob("*.json"))
        out = root / "artifacts/i18n-audit-20261101/screens" / f"{args.theme}-{args.scale}"
        out.mkdir(parents=True, exist_ok=True)
        results = []
        for code in codes:
            settings = Settings("kimhyojin", "Dark Calendar")
            settings.clear()
            settings.setValue("language", code)
            settings.setValue("text_theme", args.theme)
            settings.setValue("panel_base_color", "#f4f6f9" if args.theme == "light" else "#1e1e1e")
            i18n._load_translations()
            i18n.apply_application_locale()
            host = Host()
            host.settings = settings
            manager = OverlayWidgetManager(host)
            host.overlay_manager = manager
            service = manager.workspace_service()
            profile = service.save_profile(t("widget_studio.workspace", "Workspace"))
            service.configure(
                {"automatic": False, "pause_fullscreen": False, "motion": "balanced"},
                [
                    {
                        "profile": profile,
                        "days": [1, 2, 3, 4, 5],
                        "start": "09:00",
                        "end": "18:00",
                        "enabled": True,
                    }
                ],
            )
            dialog = OverlayManagerDialog(manager, host)
            dialog.show()
            available = dialog.screen().availableGeometry()
            dialog.resize(min(1100, available.width() - 30), min(780, available.height() - 30))

            def capture(window, name, locale_code=code, screen_rect=available):
                for _ in range(4):
                    app.processEvents()
                path = out / f"{locale_code}-{name}.png"
                assert window.grab().save(str(path))
                return {
                    "image": str(path.relative_to(root)),
                    "width": window.width(),
                    "height": window.height(),
                    "fits_screen": window.width() <= screen_rect.width()
                    and window.height() <= screen_rect.height(),
                }

            entry = {
                "locale": code,
                "resolved_locale": i18n.lang,
                "rtl": app.layoutDirection() == Qt.LayoutDirection.RightToLeft,
                "manager": capture(dialog, "manager"),
            }
            dialog.tabs.setCurrentIndex(2)
            entry["workspaces"] = capture(dialog, "workspaces")
            options = WidgetWorkspaceOptionsDialog(service, dialog)
            options.show()
            entry["options"] = capture(options, "options")
            # Check static source strings only; screenshots contain no user data.
            entry["replacement_text"] = [
                label.objectName()
                for label in dialog.findChildren(QLabel)
                if "\ufffd" in label.text()
            ]
            results.append(entry)
            options.reject()
            options.deleteLater()
            dialog.close()
            dialog.deleteLater()
            manager.shutdown()
            host.close()
            host.deleteLater()
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
            print(code, "captured", flush=True)
        verify()
        (out / "results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            errors="strict",
        )
        assert all(
            not entry["replacement_text"]
            and all(entry[key]["fits_screen"] for key in ("manager", "workspaces", "options"))
            for entry in results
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
