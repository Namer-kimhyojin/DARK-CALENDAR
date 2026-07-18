"""
Application service for batch generating routine instances.
"""

from datetime import datetime, timedelta

from calendar_app.domain.policies import routine_policy
from calendar_app.infrastructure.db import common_repo, task_repo


class RoutineBatchGenerator:
    def __init__(self, repo_unified):
        self.repo = repo_unified

    def generate_future_instances(self, template_id, start_date, end_date):
        """

        Generate routine instances from a template within a date range.

        Uses routine_policy for date calculations.

        """

        template = self.repo.get_routine_template(template_id)

        if not template:
            return []

        cycle_type = template.get("cycle_type")

        recurrence = template.get("recurrence")
        recurrence_rule = routine_policy.parse_recurrence_rule(recurrence)

        created_ids = []
        current_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        if current_date > end_dt.date():
            return created_ids

        create_task = getattr(self.repo, "create_unified_task", task_repo.create_unified_task)

        while current_date <= end_dt.date():
            # Use policy to find the first valid occurrence after current_date.
            occurrence = routine_policy.get_next_occurrence(
                current_date.strftime("%Y-%m-%d"), cycle_type, recurrence_rule
            )
            if not occurrence or datetime.strptime(occurrence, "%Y-%m-%d") > end_dt:
                break

            occurrence_date = datetime.strptime(occurrence, "%Y-%m-%d").date()
            # Safety valve: always force progress even if policy implementation regresses.
            if occurrence_date <= current_date:
                current_date = current_date + timedelta(days=1)
                continue

            # Create the instance
            task_data = {
                "name": template["name"],
                "type": "routine",
                "template_id": template_id,
                "target_date": occurrence,
                "cycle_type": cycle_type,
                "recurrence": recurrence,
                "priority": template.get("priority", "normal"),
                "icon": template.get("icon"),
                "bg_color": template.get("bg_color"),
                "description": template.get("description"),
                "deadline": f"{occurrence} 23:59:59",
            }

            if self._routine_exists_in_period(template_id, occurrence, cycle_type):
                current_date = occurrence_date + timedelta(days=1)
                continue

            new_id = create_task(task_data)
            if new_id:
                created_ids.append(new_id)

            current_date = occurrence_date + timedelta(days=1)

        return created_ids

    def _routine_exists_in_period(self, template_id, occurrence, cycle_type):
        get_routines_by_period = getattr(self.repo, "get_routines_by_period", None)
        if get_routines_by_period is None:
            return False

        period_start, period_end = common_repo.calculate_period_bounds(occurrence, cycle_type)
        rows = get_routines_by_period(cycle_type, period_start, period_end=period_end) or []
        for row in rows:
            row_template_id = self._row_get(row, "template_id")
            target_date = str(self._row_get(row, "target_date") or "")[:10]
            if row_template_id == template_id and target_date == occurrence:
                return True
        return False

    @staticmethod
    def _row_get(row, key):
        if isinstance(row, dict):
            return row.get(key)
        return None
