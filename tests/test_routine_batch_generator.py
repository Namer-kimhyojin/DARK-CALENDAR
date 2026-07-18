from pathlib import Path
import sys
import unittest
from unittest.mock import patch

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from calendar_app.application.routine_batch_generator import RoutineBatchGenerator  # noqa: E402


class _FakeRepo:
    def __init__(self):
        self.created = []
        self._period_call_count = 0

    def get_routine_template(self, template_id):
        return {
            "id": template_id,
            "name": "주간 점검",
            "cycle_type": "weekly",
            "recurrence": "weekday=0",
        }

    def get_routines_by_period(self, cycle_type, period_start, period_end=None):
        self._period_call_count += 1
        if self._period_call_count == 1:
            return [{"template_id": 7, "target_date": "2026-03-02"}]
        return []

    def create_unified_task(self, task_data):
        self.created.append(task_data)
        return len(self.created)


class RoutineBatchGeneratorTests(unittest.TestCase):
    def test_generate_future_instances_skips_existing_routine(self):
        repo = _FakeRepo()
        service = RoutineBatchGenerator(repo)

        created_ids = service.generate_future_instances(
            template_id=7,
            start_date="2026-03-01",
            end_date="2026-03-16",
        )

        self.assertEqual(created_ids, [1, 2])
        self.assertEqual([row["target_date"] for row in repo.created], ["2026-03-09", "2026-03-16"])

    def test_generate_future_instances_forces_progress_when_policy_returns_same_day(self):
        repo = _FakeRepo()
        service = RoutineBatchGenerator(repo)

        with patch(
            "calendar_app.application.routine_batch_generator.routine_policy.get_next_occurrence",
            side_effect=lambda current_date, cycle_type, rule: current_date[:10],
        ):
            created_ids = service.generate_future_instances(
                template_id=7,
                start_date="2026-03-01",
                end_date="2026-03-03",
            )

        self.assertEqual(created_ids, [])
        self.assertEqual(repo.created, [])


if __name__ == "__main__":
    unittest.main()
