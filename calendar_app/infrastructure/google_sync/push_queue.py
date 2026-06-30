"""Single-worker push queue for Google Calendar sync.

Problem
-------
The previous approach spawned a new DbTaskWorker (QThread) for every task
save/update.  Multiple threads could call sync_task_to_google() concurrently
for *different* or even the *same* task, creating a race condition window
between the DB re-read and the GCal create_event() call that produced
duplicate calendar events.

Solution
--------
GcalPushQueue is a singleton, serialised worker:

  - A Python queue.Queue holds (app, task_data, kwargs) tuples.
  - A single daemon thread drains the queue one item at a time, so only ONE
    sync_task_to_google() call is in flight at any moment.
  - Callers use enqueue() instead of calling sync_task_to_google() directly.
  - A short *dedup window* (DEDUP_WINDOW_SECS, default 1 s) collapses rapid
    consecutive edits to the same task into a single push, cutting GCal API
    traffic and further reducing the duplicate window.

Usage
-----
From action_handlers_tasks.py (or anywhere that previously called
sync_task_to_google / DbTaskWorker):

    from calendar_app.infrastructure.google_sync.push_queue import gcal_push_queue
    gcal_push_queue.enqueue(self, task_data)

The queue is started automatically on first enqueue().  It is stopped cleanly
when the application exits (atexit handler registered on first start).
"""

from __future__ import annotations

import atexit
import logging
import queue
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

# Consecutive edits to the same task within this window are collapsed into one
# push.  Set to 0 to disable deduplication entirely.
DEDUP_WINDOW_SECS: float = 1.0


class GcalPushQueue:
    """Serialised, deduplicated push queue for Google Calendar sync."""

    def __init__(self) -> None:
        self._queue: queue.Queue[Any] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        # Dedup: task_id -> (enqueue_time, task_data, kwargs)
        self._pending: dict[Any, tuple[float, Any, dict]] = {}
        self._pending_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enqueue(
        self,
        app: Any,
        task_data: dict,
        *,
        create_if_missing: bool = True,
        commit: bool = True,
        target_calendar_id: str | None = None,
        recurring_scope: str | None = None,
    ) -> None:
        """Add a push job to the queue.

        If the same task_id was already enqueued within DEDUP_WINDOW_SECS the
        older entry is replaced with the latest task_data, so only the most
        recent version is sent to GCal.
        """
        self._ensure_started(app)

        task_id = (task_data or {}).get("id")
        kwargs = {
            "create_if_missing": create_if_missing,
            "commit": commit,
            "target_calendar_id": target_calendar_id,
            "recurring_scope": recurring_scope,
        }

        if task_id and DEDUP_WINDOW_SECS > 0:
            with self._pending_lock:
                prev = self._pending.get(task_id)
                if prev is not None and (time.monotonic() - prev[0]) < DEDUP_WINDOW_SECS:
                    # Still within the dedup window — replace with latest data
                    self._pending[task_id] = (prev[0], task_data, kwargs)
                    logger.debug("push_queue: dedup collapsed rapid edit for task %s", task_id)
                    return
                self._pending[task_id] = (time.monotonic(), task_data, kwargs)

        self._queue.put((app, task_data, kwargs))

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the worker to stop and wait for it to finish."""
        self._stop_event.set()
        # Unblock the worker if it is waiting on an empty queue
        self._queue.put(None)
        with self._lock:
            t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=timeout)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_started(self, app: Any) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            t = threading.Thread(
                target=self._worker,
                name="GcalPushWorker",
                daemon=True,
            )
            t.start()
            self._thread = t
            atexit.register(self.stop)
            logger.debug("push_queue: worker thread started")

    def _worker(self) -> None:
        """Drain the queue sequentially until stop() is called."""
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=2.0)
            except queue.Empty:
                continue

            if item is None:
                # Sentinel: stop requested
                break

            app, task_data, kwargs = item
            task_id = (task_data or {}).get("id")

            # Remove from pending dedup tracker
            if task_id:
                with self._pending_lock:
                    self._pending.pop(task_id, None)

            try:
                from calendar_app.infrastructure.google_sync.helpers import (
                    sync_task_to_google,
                )

                result = sync_task_to_google(app, task_data, **kwargs)
                if not result.success:
                    logger.warning(
                        "push_queue: sync_task_to_google failed for task %s: %s",
                        task_id,
                        result.error_kind,
                    )
            except Exception:
                logger.exception("push_queue: unhandled error processing task %s", task_id)
            finally:
                self._queue.task_done()

        logger.debug("push_queue: worker thread exiting")


# Module-level singleton — import and use directly.
gcal_push_queue = GcalPushQueue()
