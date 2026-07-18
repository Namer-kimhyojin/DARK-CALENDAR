import unittest

from calendar_app.application.pomodoro_engine import (
    PHASE_FOCUS,
    PHASE_LONG_BREAK,
    PHASE_SHORT_BREAK,
    PomodoroEngine,
)


class PomodoroEngineTests(unittest.TestCase):
    def test_focus_completion_moves_to_short_break(self):
        engine = PomodoroEngine(
            focus_minutes=1,
            short_break_minutes=1,
            long_break_minutes=2,
            long_break_every=3,
        )

        events = []
        for _ in range(60):
            events = engine.tick()

        self.assertEqual(engine.phase, PHASE_SHORT_BREAK)
        self.assertEqual(engine.focus_sessions_completed, 1)
        self.assertTrue(
            any(
                e.get("type") == "focus_session_completed" and e.get("duration_secs") == 60
                for e in events
            )
        )

    def test_long_break_occurs_after_configured_cycle(self):
        engine = PomodoroEngine(
            focus_minutes=1,
            short_break_minutes=1,
            long_break_minutes=2,
            long_break_every=2,
        )

        for _ in range(60):
            engine.tick()  # focus #1 -> short break
        for _ in range(60):
            engine.tick()  # short break -> focus #2

        events = []
        for _ in range(60):
            events = engine.tick()  # focus #2 -> long break

        self.assertEqual(engine.phase, PHASE_LONG_BREAK)
        self.assertEqual(engine.focus_sessions_completed, 2)
        self.assertTrue(
            any(
                e.get("type") == "phase_changed" and e.get("phase") == PHASE_LONG_BREAK
                for e in events
            )
        )

    def test_pause_stops_progress(self):
        engine = PomodoroEngine(
            focus_minutes=1, short_break_minutes=1, long_break_minutes=2, long_break_every=4
        )
        engine.pause()

        for _ in range(20):
            events = engine.tick()
            self.assertEqual(events, [])

        self.assertEqual(engine.phase, PHASE_FOCUS)
        self.assertEqual(engine.phase_elapsed_secs, 0)
        self.assertEqual(engine.focus_secs_total, 0)

    def test_skip_break_returns_to_focus_without_increment(self):
        engine = PomodoroEngine(
            focus_minutes=1, short_break_minutes=1, long_break_minutes=2, long_break_every=4
        )
        for _ in range(60):
            engine.tick()  # focus #1 -> short break

        events = engine.skip_phase()  # short break -> focus

        self.assertEqual(engine.phase, PHASE_FOCUS)
        self.assertEqual(engine.focus_sessions_completed, 1)
        self.assertTrue(
            any(e.get("type") == "phase_changed" and e.get("phase") == PHASE_FOCUS for e in events)
        )


if __name__ == "__main__":
    unittest.main()
