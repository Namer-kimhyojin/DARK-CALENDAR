import unittest

from scripts import run_quality_gate


class QualityGateScriptTests(unittest.TestCase):
    def test_quality_gate_covers_major_feature_surfaces(self):
        labels = [label for label, _cmd in run_quality_gate.CHECKS]
        self.assertIn("Run core management and sync-helper tests", labels)
        self.assertIn("Run widget, locale, and menu smoke tests", labels)
        self.assertIn("Run Google sync integration and diagnostics smoke tests", labels)
        self.assertIn("Run focus and overlay smoke tests", labels)

        all_args = " ".join(" ".join(cmd) for _label, cmd in run_quality_gate.CHECKS)
        for path in (
            "tests/test_schedule_management_scenarios.py",
            "tests/test_routine_advanced_service.py",
            "tests/test_panel_widget_mode_ui.py",
            "tests/test_i18n_runtime_support.py",
            "tests/test_eod_usecases.py",
            "tests/test_directive_management_usecases.py",
            "tests/test_gcal_sync_integration.py",
            "tests/test_gcal_sync_issues_dialog.py",
            "tests/test_pomodoro_engine.py",
            "tests/test_overlay_countdown.py",
        ):
            self.assertIn(path, all_args)


if __name__ == "__main__":
    unittest.main()
