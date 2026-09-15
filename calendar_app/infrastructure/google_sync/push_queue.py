# -*- coding: utf-8 -*-
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
        # Dedup: task_id -> (first_enqueue_time, app, latest_task_data, kwargs)
        self._pending: dict[Any, tuple[float, Any, Any, dict]] = {}
        self._pending_lock = threading.Lock()
        self._atexit_registered = False

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
        if getattr(app, "_is_shutting_down", False):
            logger.debug("push_queue: enqueue ignored during application shutdown")
            return
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
                if prev is not None:
                    # A single queue token represents this task. Replace the
                    # payload that the worker will read, never just a side copy.
                    self._pending[task_id] = (prev[0], app, task_data, kwargs)
                    logger.debug("push_queue: dedup collapsed rapid edit for task %s", task_id)
                    return
                self._pending[task_id] = (time.monotonic(), app, task_data, kwargs)
            self._queue.put(("task", task_id))
            return

        self._queue.put(("raw", app, task_data, kwargs))

    def stop(self, timeout: float = 5.0) -> bool:
        """Signal the worker to stop, wait, and report whether it finished."""

        with self._lock:
            thread = self._thread
        if thread is None:
            return True
        if not self._stop_event.is_set():
            self._stop_event.set()
            # Unblock the worker if it is waiting on an empty queue.  Retries
            # wait on the same sentinel instead of growing the queue.
            self._queue.put(None)
        if thread.is_alive():
            thread.join(timeout=max(0.0, float(timeout)))
        if thread.is_alive():
            return False

        with self._lock:
            if self._thread is thread:
                self._thread = None
        with self._pending_lock:
            self._pending.clear()
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
            else:
                self._queue.task_done()
        return True

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
            if not self._atexit_registered:
                atexit.register(self.stop)
                self._atexit_registered = True
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
                self._queue.task_done()
                break

            if item[0] == "task":
                task_id = item[1]
                # Keep the token pending for the configured window so rapid
                # consecutive edits are guaranteed to coalesce to the latest.
                with self._pending_lock:
                    pending = self._pending.get(task_id)
                if pending is None:
                    self._queue.task_done()
                    continue
                wait_secs = max(0.0, pending[0] + DEDUP_WINDOW_SECS - time.monotonic())
                if wait_secs and self._stop_event.wait(wait_secs):
                    self._queue.task_done()
                    break
                with self._pending_lock:
                    pending = self._pending.pop(task_id, None)
                if pending is None:
                    self._queue.task_done()
                    continue
                _queued_at, app, task_data, kwargs = pending
            else:
                _kind, app, task_data, kwargs = item
                task_id = (task_data or {}).get("id")

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
