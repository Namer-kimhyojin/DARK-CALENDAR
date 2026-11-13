# -*- coding: utf-8 -*-
"""Deleting never reaches a calendar the user cannot write to."""

from calendar_app.application import task_delete_usecases


class _Repo:
    def __init__(self, tasks):
        self.tasks = {task["id"]: task for task in tasks}
        self.deleted = []

    def get_unified_task(self, task_id):
        return self.tasks.get(task_id)

    def delete_unified_task(self, task_id):
        self.deleted.append(task_id)
        return True


class _SearchRepo:
    def __init__(self, tasks):
        self.tasks = tasks

    def get_all_tasks_by_date(self, _date):
        return self.tasks


TASKS = [
    {"id": 1, "type": "schedule", "calendar_id": "local::default"},
    {"id": 2, "type": "schedule", "calendar_id": "caldav::naver-holidays"},
    {"id": 3, "type": "schedule", "calendar_id": "ics::team"},
]


def _read_only(calendar_id):
    return calendar_id in {"caldav::naver-holidays", "ics::team"}


def test_read_only_task_ids_names_tasks_on_read_only_calendars():
    repo = _Repo(TASKS)
    assert task_delete_usecases.read_only_task_ids(repo, [1, 2, 3], is_read_only=_read_only) == [
        2,
        3,
    ]


def test_delete_skips_tasks_on_read_only_calendars():
    repo = _Repo(TASKS)
    deleted = task_delete_usecases.delete_tasks_with_google_queue(
        repo, [1, 2, 3], queue_delete_fn=lambda *_args: True, is_read_only=_read_only
    )
    assert deleted == 1
    assert repo.deleted == [1]


def test_delete_by_date_skips_tasks_on_read_only_calendars():
    repo = _Repo(TASKS)
    deleted = task_delete_usecases.delete_tasks_on_date_with_google_queue(
        _SearchRepo(TASKS),
        repo,
        "2026-11-13",
        queue_delete_fn=lambda *_args: True,
        is_read_only=_read_only,
    )
    assert deleted == 1
    assert repo.deleted == [1]
