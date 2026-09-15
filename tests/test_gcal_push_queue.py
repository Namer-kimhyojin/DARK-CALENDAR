# -*- coding: utf-8 -*-

import unittest
from unittest.mock import patch

from calendar_app.infrastructure.google_sync.helpers import SyncTaskResult
from calendar_app.infrastructure.google_sync.push_queue import GcalPushQueue


class GcalPushQueueTests(unittest.TestCase):
    def test_rapid_edits_sync_only_latest_payload(self):
        queue = GcalPushQueue()
        self.addCleanup(queue.stop)
        app = object()

        with (
            patch(
                "calendar_app.infrastructure.google_sync.push_queue.DEDUP_WINDOW_SECS",
                0.03,
            ),
            patch(
                "calendar_app.infrastructure.google_sync.helpers.sync_task_to_google",
                return_value=SyncTaskResult(success=True),
            ) as sync_task,
        ):
            queue.enqueue(app, {"id": 1, "name": "old"})
            queue.enqueue(app, {"id": 1, "name": "new"})
            queue._queue.join()

        sync_task.assert_called_once()
        self.assertEqual(sync_task.call_args.args[1]["name"], "new")

    def test_non_identified_payloads_are_not_deduplicated(self):
        queue = GcalPushQueue()
        self.addCleanup(queue.stop)
        app = object()

        with patch(
            "calendar_app.infrastructure.google_sync.helpers.sync_task_to_google",
            return_value=SyncTaskResult(success=True),
        ) as sync_task:
            queue.enqueue(app, {"name": "first"})
            queue.enqueue(app, {"name": "second"})
            queue._queue.join()

        self.assertEqual(sync_task.call_count, 2)

    def test_stop_before_first_enqueue_does_not_poison_the_queue(self):
        queue = GcalPushQueue()
        self.addCleanup(queue.stop)

        self.assertTrue(queue.stop())
        with patch(
            "calendar_app.infrastructure.google_sync.helpers.sync_task_to_google",
            return_value=SyncTaskResult(success=True),
        ) as sync_task:
            queue.enqueue(object(), {"name": "after-stop"})
            queue._queue.join()

        sync_task.assert_called_once()

    def test_queue_can_restart_cleanly_after_explicit_stop(self):
        queue = GcalPushQueue()
        self.addCleanup(queue.stop)

        with patch(
            "calendar_app.infrastructure.google_sync.helpers.sync_task_to_google",
            return_value=SyncTaskResult(success=True),
        ) as sync_task:
            queue.enqueue(object(), {"name": "first"})
            queue._queue.join()
            self.assertTrue(queue.stop())

            queue.enqueue(object(), {"name": "second"})
            queue._queue.join()

        self.assertEqual(sync_task.call_count, 2)

    def test_enqueue_is_ignored_after_application_shutdown_starts(self):
        class _App:
            _is_shutting_down = True

        queue = GcalPushQueue()
        self.addCleanup(queue.stop)

        queue.enqueue(_App(), {"id": 7, "name": "late update"})

        self.assertIsNone(queue._thread)
        self.assertTrue(queue._queue.empty())


if __name__ == "__main__":
    unittest.main()
