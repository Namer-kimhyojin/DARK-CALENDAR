import unittest

from PyQt6.QtCore import QSettings

from calendar_app.shared.theme_settings import (
    OPACITY_STORAGE_UNIT_KEY,
    OPACITY_UNIT_BYTE,
    get_opacity_byte,
    get_opacity_factor,
    opacity_byte_to_percent,
    opacity_percent_to_byte,
    set_opacity_byte,
)


class ThemeSettingsOpacityTests(unittest.TestCase):
    def _settings(self, name: str) -> QSettings:
        settings = QSettings("CodexTests", name)
        settings.clear()
        self.addCleanup(settings.clear)
        return settings

    def test_theme_dialog_byte_opacity_under_100_round_trips_without_percent_reinterpretation(self):
        settings = self._settings("ThemeDialogByteOpacityUnder100")
        settings.setValue("last_opacity", 20)
        settings.setValue("last_border_opacity", 21)
        settings.setValue("last_text_opacity", 255)

        stored = get_opacity_byte(settings, persist_normalized=True)

        self.assertEqual(stored, 20)
        self.assertAlmostEqual(get_opacity_factor(settings), 20 / 255.0)
        self.assertEqual(settings.value("last_opacity", type=int), 20)
        self.assertEqual(settings.value(OPACITY_STORAGE_UNIT_KEY), OPACITY_UNIT_BYTE)

    def test_legacy_percent_opacity_migrates_to_byte_storage(self):
        settings = self._settings("LegacyPercentOpacityMigration")
        settings.setValue("last_opacity", 25)

        stored = get_opacity_byte(settings, persist_normalized=True)

        self.assertEqual(stored, opacity_percent_to_byte(25))
        self.assertEqual(settings.value("last_opacity", type=int), opacity_percent_to_byte(25))
        self.assertEqual(settings.value(OPACITY_STORAGE_UNIT_KEY), OPACITY_UNIT_BYTE)

    def test_set_opacity_byte_persists_explicit_byte_unit(self):
        settings = self._settings("ExplicitByteOpacityStorage")

        written = set_opacity_byte(settings, 42)

        self.assertEqual(written, 42)
        self.assertEqual(get_opacity_byte(settings), 42)
        self.assertEqual(settings.value(OPACITY_STORAGE_UNIT_KEY), OPACITY_UNIT_BYTE)

    def test_percent_byte_helpers_round_trip_menu_values(self):
        for percent in (25, 50, 75, 100):
            self.assertEqual(opacity_byte_to_percent(opacity_percent_to_byte(percent)), percent)


if __name__ == "__main__":
    unittest.main()
