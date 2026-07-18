"""Usecases for task-dialog save flows."""


def persist_added_task(task_data, db_repo):
    """Persist non-unified task payload and return saved task_data."""
    if "type" in task_data:
        # Unified task is already persisted in dialog path.
        return task_data

    success = db_repo.insert_task(task_data, None)
    if not success:
        raise RuntimeError("Failed to save task to local database.")

    task_data["id"] = success

    checklist_items = task_data.get("checklist_items", [])
    if checklist_items:
        db_repo.save_checklist_items_for("task", success, checklist_items)

    return task_data
