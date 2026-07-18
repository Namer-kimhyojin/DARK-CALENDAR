"""Application usecases for routine dialogs."""

from __future__ import annotations


def get_recent_routine_instances(repo, limit: int = 100):
    return repo.get_recent_routine_tasks(limit=limit)


def get_routine_detail(repo, routine_id: int):
    row = repo.get_routine_task(routine_id)
    if not row:
        return None
    # get_routine_task: id, template_id, name, target_date, ...
    return {
        "id": row[0],
        "name": row[2],
        "target_date": row[3],
    }


def get_routine_steps(repo, routine_id: int):
    return repo.get_routine_steps(routine_id)


def toggle_routine_step(repo, step_id: int):
    return repo.toggle_routine_step(step_id)


def delete_routine_instance(repo, routine_id: int):
    return repo.delete_routine_task(routine_id)


def get_routine_checklist(repo, routine_id: int):
    return repo.get_checklist_for("routine", routine_id)


def toggle_checklist_step(repo, step_id: int):
    return repo.toggle_checklist_item(step_id)
