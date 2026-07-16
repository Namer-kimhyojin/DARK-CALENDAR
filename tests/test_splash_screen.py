# -*- coding: utf-8 -*-
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from calendar_app.bootstrap import (
    _STARTUP_PHASE_MIN_MS,
    _advance_phase_progress,
    _build_startup_phase_ranges,
    _phase_soft_cap,
)
from calendar_app.presentation.splash_screen import SplashScreen


class SplashScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_progress_chases_target_in_steps(self):
        splash = SplashScreen()
        self.addCleanup(splash.close)

        splash.set_status("Loading", 0.8)

        self.assertEqual(splash._progress, 0.8)
        self.assertEqual(splash._progress_anim, 0.0)

        splash._advance_progress_display()
        first_step = splash._progress_anim

        self.assertGreater(first_step, 0.0)
        self.assertLess(first_step, 0.8)

        for _ in range(200):
            splash._advance_progress_display()

        self.assertAlmostEqual(splash._progress_anim, 0.8, places=3)

    def test_bootstrap_phase_ranges_follow_weighted_distribution(self):
        ranges = _build_startup_phase_ranges()

        self.assertEqual(ranges["preparing_runtime"][0], 0.0)
        self.assertAlmostEqual(ranges["ready"][1], 1.0, places=6)
        self.assertGreater(
            ranges["initializing_db"][1] - ranges["initializing_db"][0],
            ranges["loading_font"][1] - ranges["loading_font"][0],
        )
        self.assertGreater(
            ranges["migrating_data"][1] - ranges["migrating_data"][0],
            ranges["loading_labels"][1] - ranges["loading_labels"][0],
        )
        self.assertLess(
            ranges["ready"][1] - ranges["ready"][0],
            ranges["starting_ui"][1] - ranges["starting_ui"][0],
        )

    def test_bootstrap_phase_progress_helper_stays_within_soft_cap(self):
        soft_cap = _phase_soft_cap(0.2, 0.6)
        progress = 0.2

        for _ in range(80):
            progress = _advance_phase_progress(progress, soft_cap)

        self.assertGreater(progress, 0.2)
        self.assertLess(progress, 0.6)
        self.assertAlmostEqual(progress, soft_cap, places=3)

    def test_startup_phase_minimum_holds_stay_below_one_second(self):
        self.assertLess(sum(_STARTUP_PHASE_MIN_MS.values()), 1000)

    def test_finish_hold_starts_only_after_progress_reaches_one(self):
        splash = SplashScreen()
        self.addCleanup(splash.close)

        splash.set_status("Starting", 0.95)
        for _ in range(200):
            splash._advance_progress_display()

        self.assertFalse(splash._finish_hold_timer.isActive())

        splash.set_status("Ready", 1.0)
        self.assertFalse(splash._finish_hold_timer.isActive())

        for _ in range(200):
            splash._advance_progress_display()
            if splash._finish_hold_timer.isActive():
                break

        self.assertTrue(splash._finish_hold_timer.isActive())


if __name__ == "__main__":
    unittest.main()
