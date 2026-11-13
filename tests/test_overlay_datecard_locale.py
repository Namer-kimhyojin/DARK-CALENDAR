# -*- coding: utf-8 -*-
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QLocale

from calendar_app.presentation.widgets.overlay_datecard import _weekday_labels_mon_first


class OverlayDateCardLocaleTests(unittest.TestCase):
    def setUp(self):
        self._original_locale = QLocale()

    def tearDown(self):
        QLocale.setDefault(self._original_locale)

    def test_weekday_labels_are_qt_narrow_names_monday_first(self):
        for language in (
            QLocale.Language.Korean,
            QLocale.Language.English,
            QLocale.Language.Russian,
            QLocale.Language.Arabic,
            QLocale.Language.Vietnamese,
        ):
            locale = QLocale(language)
            QLocale.setDefault(locale)
            expected = [
                locale.standaloneDayName(day, QLocale.FormatType.NarrowFormat)
                for day in range(1, 8)
            ]
            with self.subTest(language=language.name):
                self.assertEqual(_weekday_labels_mon_first(), expected)

    def test_korean_labels_stay_single_syllables(self):
        QLocale.setDefault(QLocale(QLocale.Language.Korean, QLocale.Country.SouthKorea))
        self.assertEqual(_weekday_labels_mon_first(), ["월", "화", "수", "목", "금", "토", "일"])


if __name__ == "__main__":
    unittest.main()
