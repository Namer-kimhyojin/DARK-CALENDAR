from unittest import TestCase

from calendar_app.infrastructure.runtime.idle_detector import AlarmWorker


class IdleDetectorTests(TestCase):
    def test_resumed_activity_when_elapsed_drops_below_previous_value(self):
        worker = AlarmWorker()
        worker._last_elapsed_ms = 480_000

        self.assertTrue(worker._has_activity_resumed(120_000))

    def test_resumed_activity_when_elapsed_is_recent(self):
        worker = AlarmWorker()
        worker._last_elapsed_ms = 480_000

        self.assertTrue(worker._has_activity_resumed(1_000))

    def test_no_resumed_activity_while_elapsed_keeps_growing(self):
        worker = AlarmWorker()
        worker._last_elapsed_ms = 480_000

        self.assertFalse(worker._has_activity_resumed(481_000))

    def test_suppressed_unlock_still_sleeps_between_polls(self):
        from unittest.mock import patch

        from calendar_app.infrastructure.runtime import idle_detector

        worker = AlarmWorker()
        worker._is_idle = True
        worker.suppress_unlock = True
        polls = []

        def _input_tick():
            polls.append(1)
            if len(polls) >= 3:
                worker.is_running = False
            return 9_000

        with (
            patch.object(idle_detector, "HAS_WIN32", True),
            patch.object(idle_detector, "_safe_last_input_tick", side_effect=_input_tick),
            patch.object(idle_detector, "_safe_tick_count", return_value=10_000),
            patch.object(idle_detector, "_safe_cursor_pos", return_value=(1, 1)),
            patch.object(worker, "msleep") as msleep,
        ):
            worker.run()

        self.assertEqual(len(polls), 3)
        self.assertGreaterEqual(msleep.call_count, 2)
        self.assertTrue(worker._is_idle)
