# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

from calendar_app.infrastructure.runtime import system_manager


class _SettingsStub:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.synced = 0

    def value(self, key, default=None, type=None):  # noqa: A002
        value = self.values.get(key, default)
        return type(value) if type is not None else value

    def setValue(self, key, value):
        self.values[key] = value

    def sync(self):
        self.synced += 1


class _State:
    def __init__(self, name):
        self.name = name


class _Task:
    def __init__(self, state_name):
        self.state = _State(state_name)


class SystemManagerAutostartTests(unittest.TestCase):
    def test_packaged_status_comes_from_windows_task(self):
        settings = _SettingsStub({system_manager._KEY: False})
        task = _Task("ENABLED")

        with (
            patch.object(system_manager, "_new_settings", return_value=settings),
            patch.object(system_manager, "_get_packaged_startup_task", return_value=task),
        ):
            self.assertTrue(system_manager.is_autostart_enabled())

        self.assertTrue(settings.values[system_manager._KEY])
        self.assertGreater(settings.synced, 0)

    def test_legacy_enabled_preference_is_migrated_to_packaged_task(self):
        settings = _SettingsStub(
            {
                system_manager._KEY: True,
                system_manager._MIGRATION_KEY: False,
            }
        )
        task = _Task("DISABLED")

        with (
            patch.object(system_manager, "_new_settings", return_value=settings),
            patch.object(system_manager, "_get_packaged_startup_task", return_value=task),
            patch.object(system_manager, "_enable_packaged_task", return_value=True) as enable,
        ):
            self.assertTrue(system_manager.is_autostart_enabled())

        enable.assert_called_once_with(task)
        self.assertTrue(settings.values[system_manager._MIGRATION_KEY])

    def test_frozen_standalone_uses_current_user_run_registration(self):
        settings = _SettingsStub()

        with (
            patch.object(system_manager, "_new_settings", return_value=settings),
            patch.object(system_manager, "_get_packaged_startup_task", return_value=None),
            patch.object(system_manager, "_has_package_identity", return_value=False),
            patch.object(system_manager, "_is_frozen", return_value=True),
            patch.object(system_manager, "_set_registry_autostart", return_value=True) as register,
            patch.object(system_manager, "_registry_autostart_enabled", return_value=True),
        ):
            self.assertTrue(system_manager.set_autostart(True))

        register.assert_called_once_with(True)
        self.assertTrue(settings.values[system_manager._KEY])

    def test_packaged_enable_uses_completed_request_state(self):
        settings = _SettingsStub()
        task = _Task("DISABLED")

        with (
            patch.object(system_manager, "_new_settings", return_value=settings),
            patch.object(system_manager, "_get_packaged_startup_task", return_value=task),
            patch.object(system_manager, "_enable_packaged_task", return_value=True),
        ):
            self.assertTrue(system_manager.set_autostart(True))

        self.assertTrue(settings.values[system_manager._KEY])

    def test_source_run_does_not_install_development_path(self):
        settings = _SettingsStub()

        with (
            patch.object(system_manager, "_new_settings", return_value=settings),
            patch.object(system_manager, "_get_packaged_startup_task", return_value=None),
            patch.object(system_manager, "_has_package_identity", return_value=False),
            patch.object(system_manager, "_is_frozen", return_value=False),
            patch.object(system_manager, "_set_registry_autostart") as register,
        ):
            self.assertTrue(system_manager.set_autostart(True))

        register.assert_not_called()
        self.assertTrue(settings.values[system_manager._KEY])


if __name__ == "__main__":
    unittest.main()
