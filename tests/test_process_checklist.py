# -*- coding: utf-8 -*-
"""Process checklists: steps go in order, and the last step completes the task."""

from types import SimpleNamespace
import unittest

from PyQt6.QtWidgets import QApplication, QCheckBox, QVBoxLayout, QWidget

from calendar_app.application import routine_advanced_service, task_usecases
from calendar_app.infrastructure.db import checklist_repo, task_repo
from tests.support import TemporaryDatabaseTestCase


class ProcessChecklistTests(TemporaryDatabaseTestCase):
    def _routine(self, target_date="2026-03-24"):
        return task_repo.create_unified_task(
            {
                "name": "Morning routine",
                "type": "routine",
                "cycle_type": "daily",
                "target_date": target_date,
                "deadline": f"{target_date} 09:30:00",
                "status": "in_progress",
            }
        )

    def _steps(self, owner_id, display_type="process", count=3):
        return [
            task_repo.add_checklist_item(
                owner_id, f"step-{i + 1}", item_order=i, display_type=display_type
            )
            for i in range(count)
        ]

    def _toggle(self, link_id):
        return task_usecases.toggle_checklist_item(checklist_repo, task_repo, link_id)

    def _done(self, owner_id):
        return [item["is_completed"] for item in checklist_repo.get_task_checklist_items(owner_id)]

    def _routines(self):
        return [
            row
            for row in routine_advanced_service.search_routines(cycle_type="daily")
            if row.get("name") == "Morning routine"
        ]

    def test_list_checklist_toggles_any_item(self):
        owner = self._routine()
        steps = self._steps(owner, display_type="list")

        self.assertTrue(self._toggle(steps[2]))

        self.assertEqual(self._done(owner), [0, 0, 1])

    def test_process_step_cannot_be_checked_before_earlier_steps(self):
        owner = self._routine()
        steps = self._steps(owner)

        self.assertFalse(self._toggle(steps[1]))

        self.assertEqual(self._done(owner), [0, 0, 0])

    def test_unchecking_a_process_step_unchecks_the_steps_after_it(self):
        owner = self._routine()
        steps = self._steps(owner)
        self._toggle(steps[0])
        self._toggle(steps[1])

        self.assertTrue(self._toggle(steps[0]))

        self.assertEqual(self._done(owner), [0, 0, 0])

    def test_last_process_step_completes_routine_and_creates_next_occurrence(self):
        owner = self._routine()
        for link_id in self._steps(owner):
            self.assertTrue(self._toggle(link_id))

        routine = task_repo.get_unified_task(owner)
        self.assertEqual(routine["status"], "completed")
        self.assertEqual(int(routine["is_completed"]), 1)

        rows = self._routines()
        self.assertEqual(len(rows), 2)
        next_row = next(row for row in rows if row["id"] != owner)
        self.assertEqual(next_row["target_date"], "2026-03-25")
        self.assertEqual(self._done(next_row["id"]), [0, 0, 0])

    def test_unchecking_after_completion_reopens_without_duplicate_next_occurrence(self):
        owner = self._routine()
        steps = self._steps(owner)
        for link_id in steps:
            self._toggle(link_id)

        self.assertTrue(self._toggle(steps[2]))

        self.assertEqual(task_repo.get_unified_task(owner)["status"], "in_progress")
        for link_id in steps[2:]:
            self._toggle(link_id)
        self.assertEqual(task_repo.get_unified_task(owner)["status"], "completed")
        self.assertEqual(len(self._routines()), 2)

    def test_last_process_step_completes_a_schedule(self):
        owner = task_repo.create_unified_task(
            {
                "name": "Release",
                "type": "schedule",
                "target_date": "2026-03-24",
                "deadline": "2026-03-24 18:00:00",
                "status": "pending",
            }
        )
        for link_id in self._steps(owner, count=2):
            self._toggle(link_id)

        self.assertEqual(task_repo.get_unified_task(owner)["status"], "completed")

    def test_list_checklist_does_not_complete_its_task(self):
        owner = self._routine()
        for link_id in self._steps(owner, display_type="list"):
            self._toggle(link_id)

        self.assertEqual(task_repo.get_unified_task(owner)["status"], "in_progress")
        self.assertEqual(len(self._routines()), 1)

    def test_focus_mode_checkboxes_follow_process_rules(self):
        from calendar_app.presentation import focus_mode

        self._app = QApplication.instance() or QApplication([])
        owner = self._routine()
        self._steps(owner)
        host = QWidget()
        focus_mode._build_focus_checklist_panel(
            SimpleNamespace(settings=None, _focus_task_id=owner), QVBoxLayout(host)
        )
        boxes = host.findChildren(QCheckBox)
        self.assertEqual(len(boxes), 3)

        boxes[1].setChecked(True)
        self.assertEqual([box.isChecked() for box in boxes], [False, False, False])

        boxes[0].setChecked(True)
        boxes[1].setChecked(True)
        boxes[0].setChecked(False)
        self.assertEqual([box.isChecked() for box in boxes], [False, False, False])
        self.assertEqual(self._done(owner), [0, 0, 0])


if __name__ == "__main__":
    unittest.main()
