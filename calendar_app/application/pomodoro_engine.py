from dataclasses import dataclass
import time

PHASE_FOCUS = "focus"
PHASE_SHORT_BREAK = "short_break"
PHASE_LONG_BREAK = "long_break"


@dataclass(frozen=True)
class PomodoroSnapshot:
    phase: str
    phase_elapsed_secs: int
    phase_remaining_secs: int
    focus_sessions_completed: int
    focus_secs_total: int
    cycle_size: int
    current_focus_index: int
    paused: bool


class PomodoroEngine:
    """Simple, deterministic Pomodoro state machine."""

    def __init__(
        self,
        *,
        focus_minutes: int = 25,
        short_break_minutes: int = 5,
        long_break_minutes: int = 15,
        long_break_every: int = 4,
        goal_sessions: int = 4,
    ) -> None:
        self.focus_secs = self._to_secs(focus_minutes, default_minutes=25)
        self.short_break_secs = self._to_secs(short_break_minutes, default_minutes=5)
        self.long_break_secs = self._to_secs(long_break_minutes, default_minutes=15)
        self.long_break_every = max(2, int(long_break_every or 4))
        self.goal_sessions = max(1, int(goal_sessions or 4))

        self.phase = PHASE_FOCUS
        self.phase_elapsed_secs = 0
        self.focus_sessions_completed = 0
        self.focus_secs_total = 0
        self.paused = False
        self._last_tick_time = time.time()

    @staticmethod
    def _to_secs(value, *, default_minutes: int) -> int:
        try:
            minutes = int(value)
        except (TypeError, ValueError):
            minutes = default_minutes
        minutes = max(1, minutes)
        return minutes * 60

    @property
    def phase_duration_secs(self) -> int:
        if self.phase == PHASE_FOCUS:
            return self.focus_secs
        if self.phase == PHASE_LONG_BREAK:
            return self.long_break_secs
        return self.short_break_secs

    @property
    def phase_remaining_secs(self) -> int:
        remaining = self.phase_duration_secs - self.phase_elapsed_secs
        return max(0, remaining)

    @property
    def current_focus_index(self) -> int:
        if self.focus_sessions_completed <= 0:
            return 1
        if self.phase == PHASE_FOCUS:
            return (self.focus_sessions_completed % self.long_break_every) + 1
        current = self.focus_sessions_completed % self.long_break_every
        return current if current else self.long_break_every

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False
        self._last_tick_time = time.time()

    def toggle_pause(self) -> bool:
        self.paused = not self.paused
        if not self.paused:
            self._last_tick_time = time.time()
        return self.paused

    def skip_phase(self) -> list[dict]:
        """Skip current phase and immediately transition to the next phase.
        Skipping a Focus phase only records a session if meaningful time was spent (>= 60s).
        Skipping a break phase simply advances to the next Focus phase.
        """
        if self.phase == PHASE_FOCUS and self.phase_elapsed_secs < 60:
            # Not enough focus time — just advance the phase without recording a session
            next_phase = PHASE_SHORT_BREAK
            if (
                self.focus_sessions_completed % self.long_break_every == 0
                and self.focus_sessions_completed > 0
            ):
                next_phase = PHASE_LONG_BREAK
            self.phase = next_phase
            self.phase_elapsed_secs = 0
            self._last_tick_time = __import__("time").time()
            return [{"type": "phase_changed", "phase": self.phase}]
        return self._complete_current_phase()

    def tick(self) -> list[dict]:
        """Advance actual elapsed time and return transition events."""
        now = time.time()
        delta = max(1, int(now - self._last_tick_time))
        self._last_tick_time = now

        if self.paused:
            return []

        self.phase_elapsed_secs += delta
        if self.phase == PHASE_FOCUS:
            self.focus_secs_total += delta

        if self.phase_elapsed_secs < self.phase_duration_secs:
            return []
        return self._complete_current_phase()

    def _complete_current_phase(self) -> list[dict]:
        events: list[dict] = []
        previous_phase = self.phase
        spent_secs = self.phase_elapsed_secs

        if previous_phase == PHASE_FOCUS:
            # Record spent time if any (even if skipped early, guarantee at least 1 sec for DB)
            duration_to_record = max(1, spent_secs)
            self.focus_sessions_completed += 1

            events.append(
                {
                    "type": "focus_session_completed",
                    "duration_secs": duration_to_record,
                    "focus_sessions_completed": self.focus_sessions_completed,
                }
            )

            # Determine next phase (Short or Long break)
            if self.focus_sessions_completed >= self.goal_sessions:
                # Goal Reached for this ENTIRE RUN (Set)
                events.append(
                    {
                        "type": "pomodoro_set_completed",
                        "total_focus_secs": self.focus_secs_total,
                        "sessions_completed": self.focus_sessions_completed,
                    }
                )
                # We stay in Focus or transition to Long Break for visual feedback,
                # but the UI will catch this event and pause everything.
                next_phase = PHASE_LONG_BREAK
            elif self.focus_sessions_completed % self.long_break_every == 0:
                next_phase = PHASE_LONG_BREAK
            else:
                next_phase = PHASE_SHORT_BREAK
        else:
            # From break back to focus
            next_phase = PHASE_FOCUS

        self.phase = next_phase
        self.phase_elapsed_secs = 0
        self._last_tick_time = time.time()

        events.append({"type": "phase_changed", "phase": self.phase})
        return events

    def start_long_break(self) -> list[dict]:
        """Manually force transition into Long Break phase."""
        self.phase = PHASE_LONG_BREAK
        self.phase_elapsed_secs = 0
        self._last_tick_time = time.time()
        return [{"type": "phase_changed", "phase": self.phase}]

    def snapshot(self) -> PomodoroSnapshot:
        return PomodoroSnapshot(
            phase=self.phase,
            phase_elapsed_secs=self.phase_elapsed_secs,
            phase_remaining_secs=self.phase_remaining_secs,
            focus_sessions_completed=self.focus_sessions_completed,
            focus_secs_total=self.focus_secs_total,
            cycle_size=self.long_break_every,
            current_focus_index=self.current_focus_index,
            paused=self.paused,
        )
