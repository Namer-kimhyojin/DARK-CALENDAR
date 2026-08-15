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


if __name__ == "__main__":
    unittest.main()
