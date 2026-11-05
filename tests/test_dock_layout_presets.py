# -*- coding: utf-8 -*-
import unittest

from calendar_app.presentation.main_window.dock_sections import dock_layout_presets as dlp


class _PresetManagerStub:
    def __init__(self, presets=None, apply_ok=True):
        self._presets = presets or {}
        self.apply_ok = apply_ok
        self.loaded_names = []
        self.applied_payloads = []

    def _read_presets(self):
        return dict(self._presets)

    def _load_preset(self, name):
        self.loaded_names.append(name)

    def _apply_payload(self, payload):
        self.applied_payloads.append(payload)
        return self.apply_ok


class _AppStub:
    def __init__(self, preset_manager):
        self.preset_manager = preset_manager
        self.toasts = []

    def show_toast(self, title, message):
        self.toasts.append((title, message))


class DockLayoutPresetTests(unittest.TestCase):
    def test_embedded_release_payload_is_used_when_user_slot_is_missing(self):
        host = _AppStub(_PresetManagerStub())

        dlp.apply_layout_preset(host, 0)

        self.assertEqual([], host.preset_manager.loaded_names)
        self.assertEqual(1, len(host.preset_manager.applied_payloads))
        self.assertEqual(
            dlp._embedded_release_preset_payload(0)["dock_state_b64"],
            host.preset_manager.applied_payloads[0]["dock_state_b64"],
        )

    def test_embedded_release_payload_is_also_available_for_slot_five(self):
        host = _AppStub(_PresetManagerStub())

        dlp.apply_layout_preset(host, 4)

        self.assertEqual([], host.preset_manager.loaded_names)
        self.assertEqual(1, len(host.preset_manager.applied_payloads))
        self.assertEqual(
            dlp._embedded_release_preset_payload(4)["dock_state_b64"],
            host.preset_manager.applied_payloads[0]["dock_state_b64"],
        )

    def test_user_saved_slot_still_overrides_embedded_release_payload(self):
        slot_name = dlp.LAYOUT_PRESET_DEFS[0][0]
        host = _AppStub(_PresetManagerStub(presets={slot_name: {"dock_state_b64": "user"}}))

        dlp.apply_layout_preset(host, 0)

        self.assertEqual([slot_name], host.preset_manager.loaded_names)
        self.assertEqual([], host.preset_manager.applied_payloads)


def test_monthly_layout_gives_calendar_most_space_and_keeps_work_tabs(tmp_path):
    from PyQt6.QtCore import QSettings, Qt
    from PyQt6.QtWidgets import QApplication, QDockWidget, QMainWindow, QWidget

    from calendar_app.presentation.main_window.top_menus.display_menu import _toggle_dock

    class Host(QMainWindow):
        def __init__(self):
            super().__init__()
            self.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
            self.dock_manager = self
            self.view_mode_state = "weekly_1"

        def schedule_panel_refresh(self, **_panels):
            pass

        def sync_panel_menu_state(self):
            pass

        def show_toast(self, *_message):
            pass

    qt_app = QApplication.instance() or QApplication([])
    host = Host()
    for name in ("left_dock", "center_dock", "routine_dock", "directive_dock"):
        dock = QDockWidget(name, host)
        dock.setObjectName(name)
        dock.setWidget(QWidget())
        host.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        setattr(host, name, dock)
    host.resize(1200, 700)
    host.show()
    qt_app.processEvents()

    dlp.apply_monthly_centered_layout(host)
    qt_app.processEvents()

    assert host.view_mode_state == "monthly"
    assert host.settings.value("left_panel_mode") == "selected"
    assert host.settings.value("last_state")
    assert host.center_dock.width() >= host.left_dock.width() * 2
    assert set(host.tabifiedDockWidgets(host.left_dock)) == {
        host.routine_dock,
        host.directive_dock,
    }
    assert not host.left_dock.visibleRegion().isEmpty()
    host.routine_dock.raise_()
    qt_app.processEvents()
    assert not host.routine_dock.visibleRegion().isEmpty()
    assert not host.center_dock.visibleRegion().isEmpty()

    _toggle_dock(host, "left_dock", False)
    _toggle_dock(host, "left_dock", True)
    assert host.dockWidgetArea(host.left_dock) == Qt.DockWidgetArea.RightDockWidgetArea
    assert set(host.tabifiedDockWidgets(host.left_dock)) == {
        host.routine_dock,
        host.directive_dock,
    }
    host.close()


if __name__ == "__main__":
    unittest.main()
