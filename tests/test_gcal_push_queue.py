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

    def _run_failed_push(self, error_kind, token_exists):
        queue = GcalPushQueue()
        self.addCleanup(queue.stop)
        module = "calendar_app.infrastructure.google_sync.push_queue"
        with (
            patch(
                "calendar_app.infrastructure.google_sync.helpers.sync_task_to_google",
                return_value=SyncTaskResult(success=False, error_kind=error_kind),
            ),
            patch(f"{module}._waiting_for_sign_in", return_value=not token_exists),
            patch(f"{module}.logger") as logger,
        ):
            queue.enqueue(object(), {"name": "x"})
            queue._queue.join()
        return logger.log.call_args.args[0]

    def test_auth_required_without_token_logs_debug_only(self):
        import logging

        self.assertEqual(self._run_failed_push("auth_required", token_exists=False), logging.DEBUG)

    def test_auth_required_with_token_still_warns(self):
        import logging

        self.assertEqual(self._run_failed_push("auth_required", token_exists=True), logging.WARNING)

    def test_other_failures_still_warn_without_token(self):
        import logging

        self.assertEqual(self._run_failed_push("network", token_exists=False), logging.WARNING)

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
