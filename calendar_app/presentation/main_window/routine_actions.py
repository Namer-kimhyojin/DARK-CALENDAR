"""Routine-related UI action mixin."""


class RoutineActionsMixin:
    def generate_today_routines(self):
        from calendar_app.infrastructure.db import routine_repo, task_repo
        from calendar_app.shared.background_worker import DbTaskWorker

        today_str = self.current_date.toString("yyyy-MM-dd")

        def _task():
            templates = routine_repo.get_routine_templates(active_only=True)
            count = 0
            for tmpl in templates:
                template_id = tmpl["id"]
                cycle_type = tmpl.get("cycle_type", "monthly")
                # 해당 주기 내에 이미 인스턴스가 있으면 건너뜀
                from calendar_app.infrastructure.db.period_utils import calculate_period_bounds

                period_start, period_end = calculate_period_bounds(today_str, cycle_type)
                existing = (
                    routine_repo.get_routines_by_period(
                        cycle_type, period_start, period_end=period_end
                    )
                    or []
                )
                if any(r.get("template_id") == template_id for r in existing):
                    continue
                task_data = {
                    "name": tmpl["name"],
                    "type": "routine",
                    "template_id": template_id,
                    "target_date": today_str,
                    "cycle_type": cycle_type,
                    "recurrence": tmpl.get("recurrence"),
                    "priority": tmpl.get("priority", "normal"),
                    "icon": tmpl.get("icon"),
                    "bg_color": tmpl.get("bg_color"),
                    "description": tmpl.get("description"),
                    "deadline": f"{today_str} 23:59:59",
                }
                new_id = task_repo.create_unified_task(task_data)
                if new_id:
                    count += 1
            return count

        worker = DbTaskWorker(_task)
        self._run_worker(
            worker, lambda success, _: self.schedule_panel_refresh(right=True) if success else None
        )
