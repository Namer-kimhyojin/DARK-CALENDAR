# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

from calendar_app.presentation.main_window import window_restore_helpers as wrh


class _SettingsStub:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.removed = []
        self.synced = 0

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value

    def remove(self, key):
        self.removed.append(key)
        self.values.pop(key, None)

    def sync(self):
        self.synced += 1


class _SignalStub:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)


class _DockStub:
    def __init__(self, hidden=False):
        self._hidden = hidden
        self.visibilityChanged = _SignalStub()

    def isHidden(self):
        return self._hidden

    def isVisible(self):
        return not self._hidden

    def setVisible(self, visible):
        self._hidden = not visible


class _ActionStub:
    def __init__(self):
        self.checked = None

    def setChecked(self, value):
        self.checked = value


class _FocusStub:
    def __init__(self):
        self.hidden = False

    def hide(self):
        self.hidden = True


class _PresetManagerStub:
    def __init__(self, restored):
        self.restored = restored
        self.calls = 0

    def apply_saved_default_on_startup(self):
        self.calls += 1
        return self.restored


class _AppStub:
    def __init__(self, settings_values=None, restore_ok=True):
        self.focus_frame = _FocusStub()
        self.settings = _SettingsStub(settings_values)
        self._restore_ok = restore_ok
        self.restored_geometry = []
        self.restored_state = []
        self.resize_calls = []
        self.ensure_calls = 0

        self.left_dock = _DockStub()
        self.center_dock = _DockStub()
        self.routine_dock = _DockStub()
        self.directive_dock = _DockStub()

        self.act_today = _ActionStub()
        self.act_calendar = _ActionStub()
        self.act_routine = _ActionStub()
        self.act_directive = _ActionStub()

    def restoreGeometry(self, geometry):
        self.restored_geometry.append(geometry)

    def resize(self, width, height):
        self.resize_calls.append((width, height))

    def restoreState(self, state):
        self.restored_state.append(state)
        return self._restore_ok

    def ensure_window_on_screen(self):
        self.ensure_calls += 1


class WindowRestoreHelperTests(unittest.TestCase):
    def test_shutdown_save_flushes_layout_and_overlay_positions(self):
        class _OverlayManagerStub:
            def __init__(self):
                self.save_calls = 0

            def save_all(self):
                self.save_calls += 1

        app = _AppStub()
        app._layout_saved = False
        app.overlay_manager = _OverlayManagerStub()
        app.saveGeometry = lambda: b"current-geometry"
        app.saveState = lambda: b"current-state"

        wrh.save_window_layout(app)

        self.assertEqual(b"current-geometry", app.settings.values["last_geometry"])
        self.assertEqual(b"current-state", app.settings.values["last_state"])
        self.assertEqual(wrh._LAYOUT_VERSION, app.settings.values["layout_version"])
        self.assertEqual(1, app.overlay_manager.save_calls)
        self.assertEqual(1, app.settings.synced)

    def test_restart_flush_refreshes_layout_even_after_a_prior_final_save(self):
        app = _AppStub()
        app._layout_saved = True
        app.saveGeometry = lambda: b"restart-geometry"
        app.saveState = lambda: b"restart-state"

        self.assertTrue(wrh.flush_window_layout(app))

        self.assertEqual(b"restart-geometry", app.settings.values["last_geometry"])
        self.assertEqual(b"restart-state", app.settings.values["last_state"])
        self.assertEqual(1, app.settings.synced)

    def test_successful_restore_keeps_saved_split_sizes(self):
        app = _AppStub(
            settings_values={
                "last_geometry": b"geom",
                "last_state": b"state",
                "layout_version": wrh._LAYOUT_VERSION,
            },
            restore_ok=True,
        )
        scheduled = []

        with patch.object(
            wrh.QTimer,
            "singleShot",
            side_effect=lambda delay, callback: scheduled.append((delay, callback)),
        ):
            wrh.restore_window_and_bind_menu_state(app)

        self.assertEqual([b"geom"], app.restored_geometry)
        self.assertEqual([b"state"], app.restored_state)
        self.assertEqual(1, app.ensure_calls)
        self.assertFalse(any(delay == 50 for delay, _ in scheduled))

    def test_failed_restore_reapplies_safe_split_normalization(self):
        app = _AppStub(
            settings_values={
                "last_geometry": b"geom",
                "last_state": b"state",
                "layout_version": wrh._LAYOUT_VERSION,
            },
            restore_ok=False,
        )
        scheduled = []

        with patch.object(
            wrh.QTimer,
            "singleShot",
            side_effect=lambda delay, callback: scheduled.append((delay, callback)),
        ):
            wrh.restore_window_and_bind_menu_state(app)

        self.assertEqual([b"state"], app.restored_state)
        self.assertTrue(any(delay == 0 for delay, _ in scheduled))
        self.assertTrue(any(delay == 50 for delay, _ in scheduled))

    def test_last_session_layout_takes_priority_over_saved_default(self):
        app = _AppStub(
            settings_values={
                "last_geometry": b"old-geom",
                "last_state": b"old-state",
                "layout_version": wrh._LAYOUT_VERSION,
            }
        )
        app.preset_manager = _PresetManagerStub(restored=True)
        scheduled = []

        with patch.object(
            wrh.QTimer,
            "singleShot",
            side_effect=lambda delay, callback: scheduled.append((delay, callback)),
        ):
            wrh.restore_window_and_bind_menu_state(app)

        self.assertEqual(0, app.preset_manager.calls)
        self.assertEqual([b"old-geom"], app.restored_geometry)
        self.assertEqual([b"old-state"], app.restored_state)
        self.assertTrue(app._layout_restore_succeeded)
        self.assertEqual("last_session", app._layout_restore_source)
        self.assertFalse(any(delay == 0 for delay, _ in scheduled))
        self.assertFalse(any(delay == 50 for delay, _ in scheduled))

    def test_saved_default_is_used_only_when_last_session_restore_fails(self):
        app = _AppStub(
            settings_values={
                "last_geometry": b"old-geom",
                "last_state": b"broken-state",
                "layout_version": wrh._LAYOUT_VERSION,
            },
            restore_ok=False,
        )
        app.preset_manager = _PresetManagerStub(restored=True)
        scheduled = []

        with patch.object(
            wrh.QTimer,
            "singleShot",
            side_effect=lambda delay, callback: scheduled.append((delay, callback)),
        ):
            wrh.restore_window_and_bind_menu_state(app)

        self.assertEqual([b"broken-state"], app.restored_state)
        self.assertEqual(1, app.preset_manager.calls)
        self.assertTrue(app._layout_restore_succeeded)
        self.assertEqual("saved_default", app._layout_restore_source)
        self.assertFalse(any(delay == 0 for delay, _ in scheduled))
        self.assertFalse(any(delay == 50 for delay, _ in scheduled))

    def test_successful_restore_preserves_explicitly_hidden_right_panels(self):
        app = _AppStub(
            settings_values={
                "last_state": b"state",
                "layout_version": wrh._LAYOUT_VERSION,
            }
        )
        app.routine_dock._hidden = True
        app.directive_dock._hidden = True

        with patch.object(wrh.QTimer, "singleShot"):
            wrh.restore_window_and_bind_menu_state(app)

        self.assertTrue(app.routine_dock.isHidden())
        self.assertTrue(app.directive_dock.isHidden())
        self.assertFalse(app.act_routine.checked)
        self.assertFalse(app.act_directive.checked)


if __name__ == "__main__":
    unittest.main()
