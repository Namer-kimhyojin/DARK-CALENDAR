# -*- coding: utf-8 -*-
"""A previous Google route must never override another service's ownership."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from calendar_app.infrastructure.google_sync import helpers
from calendar_app.infrastructure.google_sync.common import resolve_task_target_calendar_id


@pytest.mark.parametrize("namespace", ["outlook", "caldav"])
def test_other_provider_with_stale_google_fields_is_not_routed_to_google(namespace, monkeypatch):
    task = {
        "name": "Fixture",
        "calendar_id": namespace + "::fixture",
        "gcal_target_calendar_id": "primary",
        "gcal_source_calendar_id": "old@example.invalid",
        "gcal_event_id": "old-event",
    }
    assert resolve_task_target_calendar_id(task, "primary") is None
    sync = Mock(is_authenticated=True)
    app = SimpleNamespace(settings=Mock(), gcal_sync=sync)
    monkeypatch.setattr(helpers, "_is_gcal_enabled", lambda _: True)
    result = helpers.sync_task_to_google(app, task)
    assert result.success and result.error_kind == "skipped_non_gcal"
    sync.create_event.assert_not_called()
    sync.update_event.assert_not_called()
