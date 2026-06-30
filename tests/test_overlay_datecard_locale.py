import unittest

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.overlay_datecard import _weekday_labels_mon_first


class OverlayDateCardLocaleTests(unittest.TestCase):
    def test_weekday_labels_follow_locale_keys(self):
        self.assertEqual(
            _weekday_labels_mon_first(),
            [
                t("weekday.mon", "월"),
                t("weekday.tue", "화"),
                t("weekday.wed", "수"),
                t("weekday.thu", "목"),
                t("weekday.fri", "금"),
                t("weekday.sat", "토"),
                t("weekday.sun", "일"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
