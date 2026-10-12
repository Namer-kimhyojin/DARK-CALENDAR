# -*- coding: utf-8 -*-
"""Authentication must not publish failed metadata or cancelled work as success."""

import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from calendar_app.infrastructure.google_sync.oauth import GoogleAuthError
from calendar_app.presentation.dialogs.gcal_auth_worker import GCalAuthWorker

PRIMARY = [{"id": "synthetic@example.invalid", "primary": True}]


def make_service():
    service = SimpleNamespace(
        is_authenticated=True,
        last_error_kind=None,
        last_error_status=None,
        _pending_token_json="synthetic-pending-json",
        authenticate=Mock(return_value=True),
        list_accessible_calendars=Mock(return_value=PRIMARY),
    )

    def set_error(kind, message):
        service.last_error_kind = kind

    service._set_last_error = Mock(side_effect=set_error)
    return service


def test_successful_auth_and_metadata_are_published_without_persisting_token():
    service = make_service()
    worker = GCalAuthWorker(service)
    worker.run()
    assert worker.success
    assert worker.calendars == PRIMARY
    assert service._pending_token_json == "synthetic-pending-json"
    assert service.authenticate.call_args.kwargs["persist_token"] is False
    assert service.authenticate.call_args.kwargs["force_reauth"] is True


def test_failed_auth_does_not_query_metadata():
    service = make_service()
    del service._pending_token_json
    service.authenticate.return_value = False
    worker = GCalAuthWorker(service)
    worker.run()
    assert not worker.success
    service.list_accessible_calendars.assert_not_called()
    assert not hasattr(service, "_pending_token_json")


def test_empty_successful_metadata_is_left_to_ui_identity_validation():
    service = make_service()
    service.list_accessible_calendars.return_value = []
    worker = GCalAuthWorker(service)
    worker.run()
    assert worker.success
    assert worker.calendars == []
    assert service._pending_token_json == "synthetic-pending-json"


@pytest.mark.parametrize(("kind", "status"), [("fetch", None), ("auth_required", 401)])
def test_metadata_error_is_not_auth_success(kind, status):
    service = make_service()

    def fail_metadata(**kwargs):
        service.last_error_kind = kind
        service.last_error_status = status
        return None

    service.list_accessible_calendars.side_effect = fail_metadata
    worker = GCalAuthWorker(service)
    worker.run()
    assert not worker.success
    assert worker.calendars == []
    assert service.last_error_kind == kind
    assert service.last_error_status == status
    assert service._pending_token_json is None


def test_metadata_invalidated_authentication_is_not_success():
    service = make_service()

    def invalidate_auth(**kwargs):
        service.is_authenticated = False
        return PRIMARY

    service.list_accessible_calendars.side_effect = invalidate_auth
    worker = GCalAuthWorker(service)
    worker.run()
    assert not worker.success
    assert service._pending_token_json is None


def test_interruption_after_authentication_prevents_metadata_and_success():
    service = make_service()
    worker = GCalAuthWorker(service)

    def cancelled_auth(**kwargs):
        worker.requestInterruption()
        return True

    service.authenticate.side_effect = cancelled_auth
    worker.run()
    assert not worker.success
    service.list_accessible_calendars.assert_not_called()
    assert service._pending_token_json is None


def test_interruption_during_real_thread_metadata_waits_and_never_publishes_success():
    service = make_service()
    worker = GCalAuthWorker(service)
    entered = threading.Event()
    release = threading.Event()

    def blocked_metadata(**kwargs):
        entered.set()
        assert release.wait(2), "Synthetic metadata release timed out"
        return PRIMARY

    service.list_accessible_calendars.side_effect = blocked_metadata
    worker.start()
    try:
        assert entered.wait(2), "Worker did not enter synthetic metadata query"
        worker.requestInterruption()
    finally:
        release.set()
        assert worker.wait(2000), "Cancelled metadata worker did not terminate"
    assert worker.is_cancelled()
    assert not worker.success
    assert service._pending_token_json is None


def test_interruption_before_start_does_not_attempt_authentication():
    service = make_service()
    worker = GCalAuthWorker(service)
    worker.requestInterruption()
    worker.run()
    assert not worker.success
    service.authenticate.assert_not_called()
    service.list_accessible_calendars.assert_not_called()
    assert service._pending_token_json is None


@pytest.mark.parametrize("kind", ["auth_cancelled", "auth_timeout"])
def test_auth_exception_preserves_error_kind_and_failure(kind):
    service = make_service()
    service.authenticate.side_effect = GoogleAuthError(kind)
    worker = GCalAuthWorker(service)
    worker.run()
    assert not worker.success
    assert service.last_error_kind == kind
    service.list_accessible_calendars.assert_not_called()
    assert service._pending_token_json is None


def test_unexpected_metadata_exception_stays_in_worker_failure_result():
    service = make_service()
    service.list_accessible_calendars.side_effect = RuntimeError("Synthetic failure")
    worker = GCalAuthWorker(service)
    worker.run()
    assert not worker.success
    assert service.last_error_kind == "auth"
    assert service._pending_token_json is None
