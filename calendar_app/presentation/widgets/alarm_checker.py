"""Alarm checker: polls DB for due task alarms and shows popups.

Architecture
------------
- ``TaskAlarmChecker`` is instantiated once by ``initialize_overlay_app``.
- A QTimer fires every 60 s (configurable).  On each tick it queries
  ``unified_task`` for rows whose ``alarm_time`` is non-null, whose
  ``deadline`` is in the future (or near-past), and whose computed alarm
  trigger time has just passed.
- Already-fired alarms are tracked in a ``set`` (``_fired``) keyed by
  ``(task_id, alarm_offset_mins)`` so they never re-fire within the same
  session.
- Snoozed alarms are re-queued via a ``dict`` (``_snoozed``) mapping
  ``(task_id, offset_mins)`` → re-fire monotonic timestamp.
- When confirmed the entry is added to ``_confirmed`` and never fires again.

``alarm_time`` DB format: comma-separated integer minutes-before-deadline,
  e.g. ``"10,60,1440"`` means fire 10 min, 1 h, and 1 day before deadline.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
import time

from PyQt6.QtCore import QObject, QTimer, pyqtSlot

from calendar_app.infrastructure.i18n import t

logger = logging.getLogger(__name__)

_AlarmKey = tuple[int, int]  # (task_id, offset_mins)

# How often to poll (ms).  1 minute is accurate enough for minute-granular alarms.
_POLL_INTERVAL_MS = 60_000

# Grace window: an alarm is considered "due" if its trigger time is within
# the past _GRACE_PAST_SECS seconds (handles startup / missed alarms).
_GRACE_PAST_SECS = 7200

# How far into the future to consider: only the next poll interval.
# Keeps alarms from firing early; grace window covers missed/past alarms.
_LOOK_AHEAD_SECS = _POLL_INTERVAL_MS // 1000  # 60 s


class TaskAlarmChecker(QObject):
    """Periodic alarm checker attached to the main app object.

    Parameters
    ----------
    app:
        The ``OverlayApp`` main window instance.  Must have a ``show_toast``
        method and optionally an ``open_task_dialog`` / ``edit_task`` method.
    """

    def __init__(self, app, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._app = app
        self._fired: set[_AlarmKey] = set()
        self._confirmed: set[_AlarmKey] = set()
        # snoozed: key → monotonic timestamp when to re-fire
        self._snoozed: dict[_AlarmKey, float] = {}
        # Active popup windows (kept alive while visible)
        self._active_popups: list = []

        self._load_fired_alarms()

        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

        # First check after a short delay (app may still be loading)
        QTimer.singleShot(3_000, self._poll)

    def _load_fired_alarms(self) -> None:
        """Load previously fired alarms from database to prevent duplicates on restart."""
        try:
            from calendar_app.infrastructure.db import db_repository_unified as repo

            # Prune stale entries (older than 90 days) before loading
            repo.cleanup_fired_alarms(days=90)
            fired = repo.get_fired_alarms()
            for row in fired:
                tid = row.get("task_id")
                offs = row.get("offset_mins")
                if tid is not None and offs is not None:
                    self._fired.add((tid, offs))
        except Exception:
            logger.exception("TaskAlarmChecker._load_fired_alarms failed")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def stop(self) -> None:
        self._timer.stop()

    # ------------------------------------------------------------------
    # Core poll
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _poll(self) -> None:
        try:
            self._do_poll()
        except Exception:
            logger.exception("TaskAlarmChecker._poll error")

    def _do_poll(self) -> None:
        from calendar_app.infrastructure.db import db_repository_unified as repo

        now = datetime.now()
        mono_now = time.monotonic()

        # Fetch tasks with alarm_time set and a future (or near-past) deadline
        tasks = self._fetch_alarm_tasks(repo, now)

        for task in tasks:
            task_id = task.get("id")
            if task_id is None:
                continue
            deadline_str = task.get("deadline") or task.get("end_date") or ""
            if not deadline_str:
                continue
            try:
                deadline_dt = datetime.strptime(deadline_str[:16], "%Y-%m-%d %H:%M")
            except ValueError:
                # All-day tasks store only "YYYY-MM-DD" — treat as 09:00 that day
                try:
                    deadline_dt = datetime.strptime(deadline_str[:10], "%Y-%m-%d").replace(hour=9)
                except ValueError:
                    continue

            alarm_raw = task.get("alarm_time") or ""
            offsets = self._parse_offsets(alarm_raw)
            if not offsets:
                continue

            status = str(task.get("status") or "").lower()
            if status in ("done", "completed", "cancelled", "archived"):
                continue

            # Collect all due offsets for this task, then show only the one
            # whose trigger time is closest to now (most recent past or nearest
            # future).  This prevents multiple simultaneous popups for the same
            # task when several offsets fall inside the grace window at once
            # (e.g. app was restarted after missing both a 60-min and 10-min alarm).
            due_this_task: list[tuple[float, _AlarmKey]] = []  # (abs_delta, key)

            for offset_mins in offsets:
                key: _AlarmKey = (task_id, offset_mins)
                if key in self._confirmed:
                    continue
                if key in self._fired:
                    # Check if it was snoozed and now due again
                    if key in self._snoozed:
                        if mono_now < self._snoozed[key]:
                            continue  # still snoozing
                        del self._snoozed[key]
                        # Fall through to show again
                    else:
                        continue

                trigger_dt = deadline_dt - timedelta(minutes=offset_mins)
                delta_secs = (now - trigger_dt).total_seconds()

                if -_LOOK_AHEAD_SECS <= delta_secs <= _GRACE_PAST_SECS:
                    due_this_task.append((abs(delta_secs), key))

            if not due_this_task:
                continue

            # Mark ALL due offsets as fired (so they don't re-trigger next poll)
            # but only show a popup for the one closest to now.
            due_this_task.sort(key=lambda x: x[0])
            best_key = due_this_task[0][1]
            # Write to DB first so a crash between here and in-memory update
            # doesn't leave fired alarms unrecorded across restarts.
            for _, key in due_this_task:
                repo.record_fired_alarm(key[0], key[1])
                self._fired.add(key)
            self._show_popup(task, deadline_dt, best_key)

    # ------------------------------------------------------------------
    # DB query
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_alarm_tasks(repo, now: datetime) -> list:
        """Return unified_task rows that have alarm_time set."""
        try:
            from calendar_app.infrastructure.db.common_repo import get_connection

            conn = get_connection()
            if not conn:
                return []
            cur = conn.cursor()
            # Look at tasks whose deadline is within the next 8 days
            # (furthest alarm is 1 week = 7 days before deadline)
            look_ahead = (now + timedelta(days=8)).strftime("%Y-%m-%d %H:%M")
            look_back = (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")
            cur.execute(
                """
                SELECT *
                FROM unified_task
                WHERE alarm_time IS NOT NULL
                  AND trim(alarm_time) != ''
                  AND deadline >= ?
                  AND deadline <= ?
                  AND (status IS NULL OR status NOT IN ('done','completed','cancelled'))
                ORDER BY deadline ASC
                """,
                (look_back, look_ahead),
            )
            return [dict(row) for row in cur.fetchall()]
        except Exception:
            logger.exception("_fetch_alarm_tasks failed")
            return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_offsets(raw: str) -> list[int]:
        result = []
        for part in str(raw).split(","):
            part = part.strip()
            if part.isdigit():
                result.append(int(part))
        return result

    # ------------------------------------------------------------------
    # Popup display
    # ------------------------------------------------------------------

    def _show_popup(self, task: dict, deadline_dt: datetime, key: _AlarmKey) -> None:
        from calendar_app.presentation.widgets.alarm_popup import AlarmPopupWindow

        # Guard: do not open a second popup for the same alarm key
        for existing in list(self._active_popups):
            if getattr(existing, "_alarm_key", None) == key and existing.isVisible():
                return

        popup = AlarmPopupWindow(
            task=task,
            deadline_dt=deadline_dt,
            on_open_task=self._open_task,
            parent=None,
        )
        popup.confirmed.connect(lambda tid: self._on_confirmed(tid, key))
        popup.snoozed.connect(lambda tid, mins: self._on_snoozed(tid, key, mins))
        popup.completed.connect(self._on_completed)
        # Offset stacked popups upward
        popup._alarm_key = key  # used by dedup guard above
        # Append before stacking so _stack_popup sees the full list height
        self._active_popups.append(popup)
        popup.destroyed.connect(
            lambda: self._active_popups.remove(popup) if popup in self._active_popups else None
        )
        self._stack_popup(popup)
        popup.show()

    def _stack_popup(self, popup) -> None:
        """Offset new popup above existing ones so they don't overlap."""
        from PyQt6.QtWidgets import QApplication

        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        popup.adjustSize()
        margin = 16
        x = geo.right() - popup.width() - margin
        # Stack upward: each open popup takes space
        visible = [p for p in self._active_popups if p.isVisible()]
        offset = sum(p.height() + 8 for p in visible)
        y = geo.bottom() - popup.height() - margin - offset
        popup.move(x, max(geo.top() + margin, y))

    def _on_confirmed(self, task_id: int, key: _AlarmKey) -> None:
        self._confirmed.add(key)
        self._snoozed.pop(key, None)

    def _on_snoozed(self, task_id: int, key: _AlarmKey, minutes: int) -> None:
        self._snoozed[key] = time.monotonic() + minutes * 60

    def _on_completed(self, task_id: int) -> None:
        """Mark task as completed and clear fired history."""
        from calendar_app.application import task_usecases
        from calendar_app.infrastructure.db import db_repository_unified as repo

        if task_usecases.update_task_status(repo, task_id, "completed"):
            repo.delete_fired_alarms_for_task(task_id)
            # Remove from in-memory fired set so it doesn't stay there forever
            to_remove = [k for k in self._fired if k[0] == task_id]
            for k in to_remove:
                self._fired.discard(k)
            self._app.show_toast(
                t("common.notification", "알림"),
                t("alarm_popup.status_updated", "작업이 완료되었습니다."),
            )

    def _open_task(self, task_id: int) -> None:
        app = self._app
        if hasattr(app, "open_task_dialog"):
            app.open_task_dialog(task_id)
        elif hasattr(app, "edit_task"):
            app.edit_task(task_id)
