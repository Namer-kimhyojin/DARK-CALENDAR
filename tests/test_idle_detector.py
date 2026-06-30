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
