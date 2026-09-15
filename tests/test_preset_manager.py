import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from calendar_app.infrastructure.i18n import t
from calendar_app.preset_manager import PresetManager


class _FakeSettings:
    def __init__(self, payload):
        self.values = {PresetManager.SETTINGS_KEY: payload}

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value

    def remove(self, key):
        self.values.pop(key, None)

    def sync(self):
        pass


class _PresetHost(QWidget):
    def __init__(self, payload):
        super().__init__()
        self.settings = _FakeSettings(payload)
        self.preset_load_menu = QMenu(self)


class _DockStub:
    def __init__(self):
        self.visible = True

    def isVisible(self):
        return self.visible

    def setVisible(self, visible):
        self.visible = bool(visible)


class _DockManagerStub:
    def __init__(self):
        self.restored = []

    def restoreState(self, state):
        self.restored.append(bytes(state))
        return True

    def saveState(self):
        from PyQt6.QtCore import QByteArray

        return QByteArray(b"active-state")


class _ApplyHost(QWidget):
    def __init__(self, payload):
        super().__init__()
        self.settings = _FakeSettings(payload)
        self.dock_manager = _DockManagerStub()
        self.restored_geometry = []
        for name in PresetManager.DOCK_NAMES:
            setattr(self, name, _DockStub())

    def restoreGeometry(self, geometry):
        self.restored_geometry.append(bytes(geometry))
        return True

    def saveGeometry(self):
        from PyQt6.QtCore import QByteArray

        return QByteArray(b"active-geometry")

    def ensure_window_on_screen(self):
        return None


class PresetManagerMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    @staticmethod
    def _refresh_layout_preset_names():
        from calendar_app.infrastructure.i18n import t as _t
        from calendar_app.presentation.main_window.dock_sections.dock_layout_presets import (
            LAYOUT_PRESET_DEFS,
        )

        for i, key in enumerate(["layout.p1", "layout.p2", "layout.p3", "layout.p4", "layout.p5"]):
            LAYOUT_PRESET_DEFS[i][0] = _t(key)

    def setUp(self):
        from PyQt6.QtCore import QSettings

        from calendar_app.infrastructure.i18n import I18nManager

        settings = QSettings("kimhyojin", "Dark Calendar")
        self._orig_lang = settings.value("language")
        settings.setValue("language", "ko")
        I18nManager()._load_translations()
        self._refresh_layout_preset_names()

    def tearDown(self):
        from PyQt6.QtCore import QSettings

        from calendar_app.infrastructure.i18n import I18nManager

        settings = QSettings("kimhyojin", "Dark Calendar")
        if self._orig_lang is not None:
            settings.setValue("language", self._orig_lang)
        else:
            settings.remove("language")
        I18nManager()._load_translations()
        self._refresh_layout_preset_names()

    def test_load_menu_hides_builtin_slot_presets_from_history(self):
        payload = (
            '{"프리셋1": {"dock_state_b64": "a"}, '
            '"프리셋2": {"dock_state_b64": "b"}, '
            '"내 업무 레이아웃": {"dock_state_b64": "c"}}'
        )
        host = _PresetHost(payload)
        self.addCleanup(host.close)

        manager = PresetManager(host)
        manager.update_load_menu()

        texts = [
            action.text() for action in host.preset_load_menu.actions() if not action.isSeparator()
        ]

        self.assertIn(t("layout.default_name"), texts)
        self.assertIn("내 업무 레이아웃", texts)
        self.assertNotIn("프리셋1", texts)
        self.assertNotIn("프리셋2", texts)

    def test_load_menu_shows_empty_message_when_only_builtin_slots_exist(self):
        payload = '{"프리셋1": {"dock_state_b64": "a"}, "프리셋5": {"dock_state_b64": "b"}}'
        host = _PresetHost(payload)
        self.addCleanup(host.close)

        manager = PresetManager(host)
        manager.update_load_menu()

        texts = [
            action.text() for action in host.preset_load_menu.actions() if not action.isSeparator()
        ]

        self.assertIn(t("layout.default_name"), texts)
        self.assertIn(t("layout.none_saved"), texts)
        self.assertNotIn("프리셋1", texts)
        self.assertNotIn("프리셋5", texts)

    def test_loaded_default_restores_window_geometry_and_becomes_active_state(self):
        from PyQt6.QtCore import QByteArray

        geometry_b64 = PresetManager._encode_qbytearray(QByteArray(b"saved-geometry"))
        state_b64 = PresetManager._encode_qbytearray(QByteArray(b"saved-state"))
        payload = {
            PresetManager.DEFAULT_PRESET_KEY: {
                "window_geometry_b64": geometry_b64,
                "dock_state_b64": state_b64,
                "visibility": {"directive_dock": False},
            }
        }
        host = _ApplyHost(payload)
        self.addCleanup(host.close)

        manager = PresetManager(host)
        self.assertTrue(manager._apply_payload(payload[PresetManager.DEFAULT_PRESET_KEY]))

        self.assertEqual([b"saved-geometry"], host.restored_geometry)
        self.assertEqual([b"saved-state"], host.dock_manager.restored)
        self.assertFalse(host.directive_dock.visible)
        self.assertEqual(b"active-geometry", bytes(host.settings.values["last_geometry"]))
        self.assertEqual(b"active-state", bytes(host.settings.values["last_state"]))
        self.assertEqual("false", host.settings.values["screen_fill_active"])

    def test_startup_default_keeps_last_window_position(self):
        from PyQt6.QtCore import QByteArray

        payload = {
            PresetManager.DEFAULT_PRESET_KEY: {
                "window_geometry_b64": PresetManager._encode_qbytearray(
                    QByteArray(b"preset-geometry")
                ),
                "dock_state_b64": PresetManager._encode_qbytearray(QByteArray(b"saved-state")),
            }
        }
        host = _ApplyHost(payload)
        self.addCleanup(host.close)

        manager = PresetManager(host)
        self.assertTrue(manager.apply_saved_default_on_startup())

        self.assertEqual([], host.restored_geometry)
        self.assertEqual([b"saved-state"], host.dock_manager.restored)


if __name__ == "__main__":
    unittest.main()
