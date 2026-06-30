"""Deprecated compatibility shim for unified repository access.

Use concern-specific adapters instead:
- task_repo
- checklist_repo
- routine_repo
- search_repo
"""

from __future__ import annotations

from . import checklist_repo, routine_repo, search_repo, task_repo


def __getattr__(name):
    raise AttributeError(
        f"'unified_repo' has no attribute '{name}'. "
        "Use concern-specific adapters (task_repo/checklist_repo/routine_repo/search_repo)."
    )


def update_unified_task(task_id, updates):
    return task_repo.update_unified_task(task_id, updates)


def get_unified_task(task_id):
    return task_repo.get_unified_task(task_id)


def delete_unified_task(task_id):
    return task_repo.delete_unified_task(task_id)


# task domain
create_unified_task = task_repo.create_unified_task
update_unified_task_duration = task_repo.update_unified_task_duration
delete_all_tasks_by_date = task_repo.delete_all_tasks_by_date

# checklist domain
add_checklist_item = checklist_repo.add_checklist_item
toggle_checklist_item = checklist_repo.toggle_checklist_item
get_task_checklist_items = checklist_repo.get_task_checklist_items
get_task_checklist_items_for_owners = checklist_repo.get_task_checklist_items_for_owners
set_task_checklist_display_type = checklist_repo.set_task_checklist_display_type
get_task_checklist_progress = checklist_repo.get_task_checklist_progress
get_template_checklist_progress = checklist_repo.get_template_checklist_progress

# routine domain
get_routines_by_period = routine_repo.get_routines_by_period
get_all_routines_grouped_by_cycle = routine_repo.get_all_routines_grouped_by_cycle
mark_routine_completed = routine_repo.mark_routine_completed
mark_routine_incomplete = routine_repo.mark_routine_incomplete
get_routine_templates = routine_repo.get_routine_templates
get_routine_template = routine_repo.get_routine_template
get_routine_completion_stats = routine_repo.get_routine_completion_stats

# query/search domain
get_tasks_by_type = search_repo.get_tasks_by_type
get_tasks_by_type_with_progress = search_repo.get_tasks_by_type_with_progress
search_unified_tasks = search_repo.search_unified_tasks
get_all_tasks_by_date = search_repo.get_all_tasks_by_date
get_all_tasks_by_date_with_progress = search_repo.get_all_tasks_by_date_with_progress
get_schedule_tasks_overlapping_range_with_progress = (
    search_repo.get_schedule_tasks_overlapping_range_with_progress
)
