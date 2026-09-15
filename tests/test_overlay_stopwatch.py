# -*- coding: utf-8 -*-
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QWidget

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.overlay_stopwatch import OverlayStopwatchWidget


class OverlayStopwatchTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.owner = QWidget()
        self.owner.settings = QSettings("codex_test", "dark_calendar_overlay_stopwatch")
        self.owner.settings.clear()

    def tearDown(self):
        self.owner.settings.clear()
        self.owner.close()
        super().tearDown()

    def test_status_label_uses_localized_text(self):
        widget = OverlayStopwatchWidget(self.owner)
        self.addCleanup(widget.close)
        widget._set("display_style", "neon")
        widget.set_display_text("00:12.3", running=True)
        self.assertEqual(widget._status_label.text(), t("widget.stopwatch.status_run", "RUN"))

        widget.set_display_text("00:12.3", running=False)
        self.assertEqual(widget._status_label.text(), t("widget.stopwatch.status_stop", "STOP"))

    def test_ticker_title_and_template_icon_use_localized_status(self):
        widget = OverlayStopwatchWidget(self.owner)
        self.addCleanup(widget.close)
        widget._set("display_style", "ticker")
        widget._apply_appearance()
        self.assertEqual(widget._title_label.text(), t("widget.stopwatch.short_title", "SW"))

        running_html = widget._resolve_sw_template("{status_icon} {status}", 1234, True)
        paused_html = widget._resolve_sw_template("{status_icon} {status}", 1234, False)
        self.assertIn(f"> {t('widget.stopwatch.status_run', 'RUN')}", running_html)
        self.assertIn(f"[] {t('widget.stopwatch.status_stop', 'STOP')}", paused_html)

    def test_stopwatch_uses_fixed_font_for_display(self):
        widget = OverlayStopwatchWidget(self.owner)
        self.addCleanup(widget.close)
        widget.font_family = lambda: "DefinitelyNotARealFont"
        widget._apply_appearance()

        self.assertNotEqual(widget._time_label.font().family(), "DefinitelyNotARealFont")
        self.assertNotEqual(widget._status_label.font().family(), "DefinitelyNotARealFont")

    def test_stopwatch_template_uses_fixed_font_family(self):
        widget = OverlayStopwatchWidget(self.owner)
        self.addCleanup(widget.close)
        widget.font_family = lambda: "DefinitelyNotARealFont"
        widget._set_template_label("{elapsed}")

        self.assertNotIn("DefinitelyNotARealFont", widget._template_label.text())

    def test_set_display_text_updates_time_and_ticker_title(self):
        widget = OverlayStopwatchWidget(self.owner)
        self.addCleanup(widget.close)
        widget._set("display_style", "ticker")
        widget.set_display_text("12:34.5", running=False)

        self.assertEqual(widget._time_label.text(), "12:34.5")
        self.assertEqual(widget._status_label.text(), t("widget.stopwatch.status_stop", "STOP"))
        self.assertEqual(widget._title_label.text(), t("widget.stopwatch.short_title", "SW"))

    def test_running_stopwatch_falls_back_to_wall_clock_after_reboot(self):
        widget = OverlayStopwatchWidget(self.owner)
        self.addCleanup(widget.close)
        widget._set("sw_elapsed_ms", 5_000.0)
        widget._set("sw_running", True)
        widget._set("sw_started_mono", 50_000.0)
        widget._set("sw_started_wall", 100_000.0)

        with (
            patch(
                "calendar_app.presentation.widgets.overlay_stopwatch.time.monotonic",
                return_value=100.0,
            ),
            patch(
                "calendar_app.presentation.widgets.overlay_stopwatch.time.time",
                return_value=100_010.0,
            ),
        ):
            self.assertEqual(widget._sw_elapsed_ms(), 15_000.0)

    def test_running_stopwatch_prefers_monotonic_clock_during_same_boot(self):
        widget = OverlayStopwatchWidget(self.owner)
        self.addCleanup(widget.close)
        widget._set("sw_elapsed_ms", 5_000.0)
        widget._set("sw_running", True)
        widget._set("sw_started_mono", 100.0)
        widget._set("sw_started_wall", 1_000.0)
        widget._set("sw_started_boot_epoch", 900.0)

        with (
            patch(
                "calendar_app.presentation.widgets.overlay_stopwatch.time.monotonic",
                return_value=110.0,
            ),
            patch(
                "calendar_app.presentation.widgets.overlay_stopwatch.time.time",
                return_value=1_010.0,
            ),
        ):
            self.assertEqual(widget._sw_elapsed_ms(), 15_000.0)
