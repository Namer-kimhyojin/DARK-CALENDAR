import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDateTime, QSettings, Qt
from PyQt6.QtWidgets import QApplication, QWidget

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.overlay_countdown import OverlayCountdownWidget


class OverlayCountdownResizeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.owner = QWidget()
        self.owner.settings = QSettings("codex_test", "dark_calendar_overlay_countdown")
        self.owner.settings.clear()
        self.owner.resize(1200, 800)
        self.owner.show()
        self.__class__._app.processEvents()

    def tearDown(self):
        self.owner.settings.clear()
        self.owner.close()
        super().tearDown()

    def test_target_label_wraps_for_narrow_widths(self):
        widget = OverlayCountdownWidget(self.owner)
        self.addCleanup(widget.close)
        future = QDateTime.currentDateTime().addDays(10)
        widget._set("cd_target_iso", future.toString(Qt.DateFormat.ISODate))
        widget._tick_cd()
        widget._set("fixed_w", 120)
        widget._set("fixed_h", 120)
        widget._fit_font_to_size(120, 120)
        widget.resize(120, 120)
        widget.show()
        self.__class__._app.processEvents()

        one_line_height = widget._target_label.fontMetrics().height()

        self.assertTrue(widget._target_label.wordWrap())
        self.assertEqual(widget.width(), 120)
        self.assertGreater(widget._target_label.height(), one_line_height)

    def test_countdown_title_and_empty_hint_use_localized_strings(self):
        widget = OverlayCountdownWidget(self.owner)
        self.addCleanup(widget.close)

        self.assertEqual(widget._title_label.text(), t("widget.countdown.title", "COUNTDOWN"))

        widget._update_basic_display("--:--:--", "")
        self.assertEqual(
            widget._target_label.text(), t("widget.countdown.set_target", "Set target")
        )
