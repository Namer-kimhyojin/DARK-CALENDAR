# -*- coding: utf-8 -*-
"""Narrow native Qt user-layout-library QA using temporary QSettings INI files."""

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
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", default="final")
    parser.add_argument("--skip-ui", action="store_true")
    parser.add_argument("--verify-explicit-edit", action="store_true")
    args = parser.parse_args()
    os.environ["QT_QPA_PLATFORM"] = "windows" if sys.platform == "win32" else "offscreen"
    scale = os.environ.get("QT_SCALE_FACTOR", "1")
    output = ROOT / "artifacts/widget-layout-presets-20261001" / f"{args.phase}-scale-{scale}"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="air-preset-qa-", ignore_cleanup_errors=True) as temp:
        os.environ["LOCALAPPDATA"] = temp
        os.environ["APPDATA"] = temp
        from PyQt6 import QtCore
        from PyQt6.QtCore import QT_VERSION_STR, QEvent, QPoint, QSettings
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QAbstractButton, QApplication, QMenu

        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        theme_path = str(Path(temp) / "theme.ini")
        theme_settings = QSettings(theme_path, QSettings.Format.IniFormat)
        for key, value in {
            "language": "ko",
            "text_theme": "light",
            "panel_base_color": "#f3f6fb",
        }.items():
            theme_settings.setValue(key, value)
        theme_settings.sync()

        class IsolatedSettings(QSettings):
            def __init__(self, *unused_args, **unused_kwargs):
                super().__init__(theme_path, QSettings.Format.IniFormat)

        with patch.object(QtCore, "QSettings", IsolatedSettings):
            from tests.test_widget_mode_ux import Host

            from calendar_app.infrastructure import i18n as translations
            from calendar_app.presentation.dialogs.widget_customization_dialog import (
                WidgetCustomizationDialog,
            )
            from calendar_app.presentation.dialogs.widget_free_layout_editor import (
                WidgetFreeLayoutEditorDialog,
            )
            from calendar_app.presentation.widgets import widget_layout_presets as presets
            from calendar_app.presentation.widgets.unified_widget_mode import (
                UnifiedWidgetController,
            )
            from calendar_app.presentation.widgets.widget_free_layout import (
                read_free_layout,
                seed_free_layout,
            )

        report = {
            "environment": {
                "platform": platform.platform(),
                "qt": QT_VERSION_STR,
                "qt_platform": app.platformName(),
                "scale_factor": scale,
                "settings": "temporary QSettings INI",
                "production_db_or_settings_used": False,
            },
            "checks": [],
            "observations": [],
            "limits": [
                "Synthetic cached items; no database or production settings.",
                "100% and 200% on one fixed primary display; no physical mixed-DPI transfer.",
                "Representative Korean/German screens; other locales covered by root translation checks.",
            ],
        }

        def check(name, passed, detail=None):
            report["checks"].append({"name": name, "passed": bool(passed), "detail": detail})

        def snapshot(settings):
            settings.sync()
            return {key: settings.value(key) for key in settings.allKeys()}

        def settle():
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

        first = seed_free_layout("stacked")
        second = copy.deepcopy(first)
        next(block for block in second["blocks"] if block["id"] == "date")["rect"][0] = 43
        library_path = str(Path(temp) / "library.ini")
        settings = QSettings(library_path, QSettings.Format.IniFormat)
        original = []
        with patch.object(presets, "uuid4", side_effect=[UUID(int=1), UUID(int=2)]):
            library, first_id = presets.create_layout_preset(original, "  나의 주간 배치  ", first)
            library, second_id = presets.create_layout_preset(
                library, "Meine eigene Wochenübersicht", second
            )
        check(
            "create_detached_trimmed_unique_ids",
            original == [] and library[0]["name"] == "나의 주간 배치" and first_id != second_id,
        )
        written = presets.write_layout_presets(settings, library)
        settings.sync()
        fresh = QSettings(library_path, QSettings.Format.IniFormat)
        check("ini_restart_reads_exact_library", presets.read_layout_presets(fresh) == written)
        updated = presets.update_layout_preset(library, first_id, second)
        renamed = presets.rename_layout_preset(updated, first_id, "내 집중 배치")
        deleted = presets.delete_layout_preset(renamed, second_id)
        check(
            "update_rename_delete_are_staged",
            presets.read_layout_presets(fresh) == library
            and len(deleted) == 1
            and deleted[0]["name"] == "내 집중 배치"
            and deleted[0]["layout"] == second,
        )
        presets.write_layout_presets(settings, deleted)
        settings.sync()
        check(
            "ini_restart_retains_updated_library",
            presets.read_layout_presets(QSettings(library_path, QSettings.Format.IniFormat))
            == deleted,
        )
        for name in ("", " " * 3, "x" * 81, "bad\nname", "bad\x00name", library[0]["name"].upper()):
            before = snapshot(settings)
            rejected = False
            try:
                presets.create_layout_preset(library, name, first)
            except ValueError:
                rejected = True
            check(f"invalid_name_{repr(name[:16])}", rejected and snapshot(settings) == before)
        before = snapshot(settings)
        try:
            presets.delete_layout_preset(library, "user_" + "f" * 32)
            rejected = False
        except ValueError:
            rejected = True
        check("unknown_delete_rejected_without_write", rejected and snapshot(settings) == before)
        settings.setValue(presets.USER_LAYOUT_PRESETS_KEY, '{"version":2,"presets":[]}')
        before = snapshot(settings)
        check(
            "invalid_persistent_library_read_does_not_rewrite",
            presets.read_layout_presets(settings) == [] and snapshot(settings) == before,
        )
        presets.write_layout_presets(settings, library)
        settings.sync()

        def make(language="ko"):
            locale(language)
            host = Host()
            host.settings = QSettings(
                str(Path(temp) / f"host-{language}.ini"), QSettings.Format.IniFormat
            )
            host.settings.clear()
            host.settings.setValue("widget_mode_always_top", False)
            host.settings.setValue("widget_mode_skin", "classic_light")
            presets.write_layout_presets(host.settings, library)
            controller = UnifiedWidgetController(host)
            with patch("sqlite3.connect", side_effect=AssertionError("QA forbids database access")):
                controller.show_widget()
                controller.widget.timer.stop()
                settle()
            return host, controller

        def editor_for(controller, preset_id=None):
            editor = WidgetFreeLayoutEditorDialog(controller, preset_id=preset_id)
            editor.move(app.primaryScreen().availableGeometry().topLeft() + QPoint(10, 10))
            editor.show()
            settle()
            return editor

        def capture(name, editor):
            settle()
            editor.grab().save(str(output / f"{name}.png"))
            report["observations"].append(
                {
                    "scenario": name,
                    "actual_size": [editor.width(), editor.height()],
                    "device_pixel_ratio": editor.devicePixelRatioF(),
                    "screen": editor.screen().name(),
                    "screen_available_rect": list(editor.screen().availableGeometry().getRect()),
                    "buttons": [
                        {
                            "text": button.text(),
                            "accessible_name": button.accessibleName(),
                            "visible": button.isVisible(),
                        }
                        for button in editor.findChildren(QAbstractButton)
                    ],
                    "canvas_viewport": [
                        editor.canvas_scroll.viewport().width(),
                        editor.canvas_scroll.viewport().height(),
                    ]
                    if hasattr(editor, "canvas_scroll")
                    else None,
                    "user_presets": [
                        {
                            "text": editor.user_layout_list.item(index).text(),
                            "tooltip": editor.user_layout_list.item(index).toolTip(),
                        }
                        for index in range(editor.user_layout_list.count())
                    ]
                    if hasattr(editor, "user_layout_list")
                    else None,
                }
            )

        def close(host, controller):
            controller.prepare_shutdown()
            controller.widget.close()
            controller.widget.deleteLater()
            host.deleteLater()
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            settle()

        if not args.skip_ui:
            if args.verify_explicit_edit:
                host, controller = make()
                controller.apply_layout_preset(first_id)
                editor = editor_for(controller, first_id)
                editor.canvas.select_block("date")
                editor.rect_spins["x"].setValue(editor.rect_spins["x"].value() + 5)
                expected = copy.deepcopy(editor.draft)
                editor.apply_btn.click()
                settle()
                host.settings.sync()
                restart_settings = QSettings(host.settings.fileName(), QSettings.Format.IniFormat)
                check(
                    "explicit_preset_edit_apply_overwrites_without_update_button",
                    presets.get_layout_preset(
                        presets.read_layout_presets(restart_settings), first_id
                    )["layout"]
                    == expected
                    and controller.widget._free_runtime.data == expected
                    and restart_settings.value(presets.SELECTED_LAYOUT_PRESET_KEY) == first_id,
                )
                editor.deleteLater()
                close(host, controller)
                report["summary"] = {
                    "checks": len(report["checks"]),
                    "failed": sum(not item["passed"] for item in report["checks"]),
                    "screenshots": 0,
                }
                (output / "explicit-edit-observations.json").write_text(
                    json.dumps(report, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                    errors="strict",
                )
                logging.shutdown()
                print(json.dumps({"output": str(output), **report["summary"]}))
                if report["summary"]["failed"]:
                    raise SystemExit(1)
                return
            host, controller = make()
            check(
                "controller_applies_persistent_user_preset",
                controller.apply_layout_preset(first_id) is not False
                and read_free_layout(host.settings) == first,
            )
            original_geometry = controller.widget.geometry()
            before = snapshot(host.settings)
            editor = editor_for(controller, first_id)
            editor.preferences_tabs.setCurrentIndex(editor.presets_tab_index)
            check(
                "constructor_preset_is_detached_draft",
                editor.draft == first
                and editor.selected_preset_id == first_id
                and snapshot(host.settings) == before,
            )
            with patch.object(presets, "uuid4", return_value=UUID(int=3)):
                new_id = editor.save_as_preset("QA 새 배치")
            check(
                "save_as_staged_library_only",
                len(editor.presets) == 3 and snapshot(host.settings) == before,
            )
            editor.undo_btn.click()
            check(
                "save_as_undo", len(editor.presets) == 2 and editor.selected_preset_id == first_id
            )
            editor.redo_btn.click()
            check("save_as_redo", len(editor.presets) == 3 and editor.selected_preset_id == new_id)
            editor.canvas.select_block("date")
            editor.rect_spins["x"].setValue(editor.rect_spins["x"].value() + 5)
            editor.preset_update_btn.click()
            check(
                "overwrite_updates_selected_draft_only",
                presets.get_layout_preset(editor.presets, new_id)["layout"] == editor.draft
                and snapshot(host.settings) == before,
            )
            editor.rename_selected_preset("QA 저장한 집중 배치")
            check(
                "rename_updates_draft_name",
                presets.get_layout_preset(editor.presets, new_id)["name"] == "QA 저장한 집중 배치",
            )
            staged = copy.deepcopy(editor.presets)
            try:
                editor.rename_selected_preset(library[0]["name"])
                rejected = False
            except ValueError:
                rejected = True
            check("duplicate_editor_rename_atomic", rejected and editor.presets == staged)
            capture("ko-selected-preset-editor", editor)
            editor.reject()
            editor.deleteLater()
            settle()
            check(
                "editor_all_crud_cancel_preserves_ini_and_geometry",
                snapshot(host.settings) == before
                and controller.widget.geometry() == original_geometry,
            )

            customization = WidgetCustomizationDialog(controller)
            customization.move(app.primaryScreen().availableGeometry().topLeft() + QPoint(10, 10))
            customization.show()
            settle()
            customization.user_layout_list.setCurrentRow(0)
            customization.controls_scroll.verticalScrollBar().setValue(
                customization.controls_scroll.verticalScrollBar().maximum()
            )
            settle()
            capture("ko-customization-user-presets", customization)
            customization.reject()
            customization.deleteLater()
            settle()
            check("korean_customization_cancel_isolated", snapshot(host.settings) == before)

            editor = editor_for(controller, first_id)
            editor.preferences_tabs.setCurrentIndex(editor.presets_tab_index)
            with patch.object(presets, "uuid4", return_value=UUID(int=3)):
                new_id = editor.save_as_preset("QA 저장한 집중 배치")
            editor.canvas.select_block("date")
            editor.rect_spins["x"].setValue(editor.rect_spins["x"].value() + 5)
            editor.update_selected_preset()
            applied_layout = copy.deepcopy(editor.draft)
            applied_library = copy.deepcopy(editor.presets)
            editor.apply_btn.click()
            settle()
            check(
                "apply_persists_library_selected_and_live_layout",
                presets.read_layout_presets(host.settings) == applied_library
                and host.settings.value(presets.SELECTED_LAYOUT_PRESET_KEY) == new_id
                and controller.widget._free_runtime.data == applied_layout,
            )
            host_path = host.settings.fileName()
            saved_geometry = list(controller.widget.geometry().getRect())
            editor.deleteLater()
            close(host, controller)

            host = Host()
            host.settings = QSettings(host_path, QSettings.Format.IniFormat)
            controller = UnifiedWidgetController(host)
            controller.show_widget()
            controller.widget.timer.stop()
            settle()
            check(
                "restart_uses_ini_library_and_selected_layout",
                presets.read_layout_presets(host.settings) == applied_library
                and host.settings.value(presets.SELECTED_LAYOUT_PRESET_KEY) == new_id
                and controller.widget._free_runtime.data == applied_layout,
            )
            check(
                "restart_restores_saved_geometry",
                list(controller.widget.geometry().getRect()) == saved_geometry,
            )
            before_library = presets.read_layout_presets(host.settings)
            controller.set_layout("dashboard")
            settle()
            check(
                "builtin_switch_clears_selection_preserves_library",
                host.settings.value(presets.SELECTED_LAYOUT_PRESET_KEY) == ""
                and presets.read_layout_presets(host.settings) == before_library
                and not controller.widget._free_layout_active,
            )
            controller.apply_layout_preset(new_id)
            settle()
            before_geometry = controller.widget.geometry()
            editor = editor_for(controller, new_id)
            editor.preferences_tabs.setCurrentIndex(editor.presets_tab_index)
            editor.delete_selected_preset()
            check(
                "selected_delete_keeps_draft_and_live_geometry",
                editor.draft == applied_layout and controller.widget.geometry() == before_geometry,
            )
            editor.undo()
            check(
                "delete_undo_restores_selected_entry",
                editor.selected_preset_id == new_id
                and presets.get_layout_preset(editor.presets, new_id) is not None,
            )
            editor.redo()
            editor.apply_btn.click()
            settle()
            check(
                "delete_apply_preserves_live_geometry_and_layout",
                host.settings.value(presets.SELECTED_LAYOUT_PRESET_KEY) == ""
                and presets.get_layout_preset(presets.read_layout_presets(host.settings), new_id)
                is None
                and controller.widget.geometry() == before_geometry
                and controller.widget._free_runtime.data == applied_layout,
            )
            editor.deleteLater()
            before = snapshot(host.settings)
            check(
                "unknown_controller_preset_does_not_mutate",
                controller.apply_layout_preset("user_" + "f" * 32) is False
                and snapshot(host.settings) == before,
            )
            menu_records = []

            def inspect_menu(menu, _position):
                for action in menu.actions():
                    if action.menu() is not None:
                        menu_records.extend(
                            {"text": child.text(), "checked": child.isChecked()}
                            for child in action.menu().actions()
                        )
                return None

            with patch.object(QMenu, "exec", inspect_menu):
                controller.widget._open_menu(QPoint(20, 20))
            check(
                "menu_keeps_remaining_custom_presets",
                all(
                    any(record["text"] == preset["name"] for record in menu_records)
                    for preset in library
                ),
            )
            close(host, controller)

            host, controller = make("de")
            controller.apply_layout_preset(second_id)
            before = snapshot(host.settings)
            editor = editor_for(controller, second_id)
            editor.preferences_tabs.setCurrentIndex(editor.presets_tab_index)
            editor.fit_btn.click()
            capture("de-selected-preset-editor", editor)
            editor.reject()
            editor.deleteLater()
            settle()
            check("german_editor_cancel_isolated", snapshot(host.settings) == before)

            customization = WidgetCustomizationDialog(controller)
            customization.move(app.primaryScreen().availableGeometry().topLeft() + QPoint(10, 10))
            customization.show()
            settle()
            customization.user_layout_list.setCurrentRow(0)
            customization.controls_scroll.verticalScrollBar().setValue(
                customization.controls_scroll.verticalScrollBar().maximum()
            )
            settle()
            check(
                "customization_user_selection_is_staged",
                customization.draft.value(presets.SELECTED_LAYOUT_PRESET_KEY) == first_id
                and snapshot(host.settings) == before,
            )
            capture("de-customization-user-presets", customization)
            viewport = customization.controls_scroll.viewport()
            check(
                "customization_management_actions_reachable",
                all(
                    viewport.rect().contains(button.mapTo(viewport, QPoint(1, 1)))
                    and viewport.rect().contains(
                        button.mapTo(viewport, QPoint(button.width() - 2, button.height() - 2))
                    )
                    for button in (
                        customization.preset_edit_btn,
                        customization.preset_rename_btn,
                        customization.preset_delete_btn,
                    )
                ),
            )

            def accept_child(child):
                child.canvas.select_block("date")
                child.rect_spins["x"].setValue(child.rect_spins["x"].value() + 5)
                child.update_selected_preset()
                child._apply()
                return child.DialogCode.Accepted

            with patch.object(WidgetFreeLayoutEditorDialog, "exec", accept_child):
                customization._edit_user_layout()
            check(
                "nested_editor_apply_only_parent_draft",
                presets.get_layout_preset(
                    presets.read_layout_presets(customization.draft), first_id
                )["layout"]
                != first
                and snapshot(host.settings) == before,
            )
            customization._rename_user_layout("QA 부모 초안 배치")
            check(
                "customization_rename_is_staged",
                presets.get_layout_preset(
                    presets.read_layout_presets(customization.draft), first_id
                )["name"]
                == "QA 부모 초안 배치"
                and snapshot(host.settings) == before,
            )
            customization._delete_user_layout(confirmed=True)
            check(
                "customization_delete_is_staged",
                presets.get_layout_preset(
                    presets.read_layout_presets(customization.draft), first_id
                )
                is None
                and snapshot(host.settings) == before,
            )
            customization.reject()
            customization.deleteLater()
            settle()
            check("parent_cancel_discards_child_crud", snapshot(host.settings) == before)

            customization = WidgetCustomizationDialog(controller)
            customization.move(app.primaryScreen().availableGeometry().topLeft() + QPoint(10, 10))
            customization.show()
            settle()
            customization.user_layout_list.setCurrentRow(1)
            customization._rename_user_layout("QA 이름 저장")
            customized = presets.read_layout_presets(customization.draft)
            customization.apply_btn.click()
            settle()
            check(
                "customization_apply_persists_selected_library",
                presets.read_layout_presets(host.settings) == customized
                and host.settings.value(presets.SELECTED_LAYOUT_PRESET_KEY) == second_id,
            )
            customization.deleteLater()
            close(host, controller)

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
