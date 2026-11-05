# -*- coding: utf-8 -*-
"""An unavailable OAuth endpoint must not invalidate a saved Google connection."""

import json
import socket
from types import SimpleNamespace
from unittest.mock import Mock

from google.auth.exceptions import RefreshError, TransportError
from googleapiclient.errors import HttpError
from httplib2 import Response
import pytest

from calendar_app.infrastructure.google_sync import service, token_store
from calendar_app.infrastructure.google_sync.oauth import GoogleAuthError


@pytest.fixture
def expired_connection(monkeypatch, tmp_path):
    token = tmp_path / "token.json"
    original = b"DCTOK1synthetic-protected-token"
    token.write_bytes(original)
    monkeypatch.setattr(service, "TOKEN_PATH", str(token))
    client = tmp_path / "credentials.json"
    client.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "synthetic-client",
                    "client_secret": "synthetic-secret",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
        ),
        encoding="utf-8",
        errors="strict",
    )
    monkeypatch.setattr(service, "CREDENTIALS_PATH", str(client))
    load = Mock(return_value=json.dumps({"scopes": service.SCOPES}))
    monkeypatch.setattr(token_store, "load_token_json", load)
    creds = SimpleNamespace(
        valid=False,
        expired=True,
        refresh_token="synthetic",
        scopes=service.SCOPES,
        refresh=Mock(),
        to_json=lambda: "synthetic-refreshed-token",
    )
    monkeypatch.setattr(service.Credentials, "from_authorized_user_info", lambda *args: creds)
    login = Mock(
        return_value=SimpleNamespace(
            valid=True,
            scopes=service.SCOPES,
            refresh_token="synthetic",
            to_json=lambda: "synthetic-login-token",
        )
    )
    build, save = Mock(), Mock()
    monkeypatch.setattr(service, "run_desktop_auth", login)
    monkeypatch.setattr(service, "build", build)
    monkeypatch.setattr(token_store, "save_token_json", save)
    return SimpleNamespace(
        token=token, original=original, creds=creds, login=login, build=build, load=load, save=save
    )


@pytest.mark.parametrize("interactive", [False, True])
@pytest.mark.parametrize(
    "error, expected",
    [
        (TransportError("private-token https://private.invalid"), "network_unavailable"),
        (TimeoutError("private-token"), "network_unavailable"),
        (socket.gaierror("private-token"), "network_unavailable"),
        (RefreshError("private-token", retryable=True), "network_unavailable"),
        (
            RefreshError("private-token", {"error": "temporarily_unavailable"}),
            "network_unavailable",
        ),
        (RefreshError("private-token", {"error": "server_error"}), "network_unavailable"),
        (RefreshError("private-token", {"error": "invalid_client"}), "auth_client_invalid"),
        (RuntimeError("private-token"), "operation_failed"),
        (RefreshError("invalid_grant private-token"), "operation_failed"),
        (RefreshError("private-token", {"error": []}), "operation_failed"),
        (RefreshError("private-token", {"error": {}}), "operation_failed"),
    ],
)
def test_refresh_failure_preserves_connection_and_does_not_open_login(
    expired_connection, caplog, interactive, error, expected
):
    fixture = expired_connection
    fixture.creds.refresh.side_effect = error
    sync = service.CalendarSyncService()

    assert not sync.authenticate(interactive=interactive)

    assert sync.last_error_kind == expected
    assert sync.last_error_message == expected
    assert sync.last_error_status is None
    assert not sync.is_authenticated and sync.service is None
    assert fixture.token.read_bytes() == fixture.original
    fixture.login.assert_not_called()
    fixture.build.assert_not_called()
    fixture.save.assert_not_called()
    assert "private-token" not in caplog.text
    assert "private.invalid" not in caplog.text


def test_revoked_refresh_token_still_requires_login(expired_connection):
    fixture = expired_connection
    fixture.creds.refresh.side_effect = RefreshError("private-token", {"error": "invalid_grant"})
    sync = service.CalendarSyncService()

    assert not sync.authenticate(interactive=False)

    assert sync.last_error_kind == "auth_required"
    assert sync.last_error_status == 401
    assert fixture.token.read_bytes() == fixture.original
    fixture.save.assert_not_called()


def test_explicit_sign_in_can_reconnect_a_revoked_token(expired_connection):
    fixture = expired_connection
    fixture.creds.refresh.side_effect = RefreshError("private-token", {"error": "invalid_grant"})
    sync = service.CalendarSyncService()

    assert sync.authenticate(interactive=True)
    assert sync.is_authenticated
    fixture.login.assert_called_once()
    fixture.save.assert_called_once_with("synthetic-login-token")


def test_recovered_endpoint_reuses_the_same_saved_connection(expired_connection):
    fixture = expired_connection
    fixture.creds.refresh.side_effect = TransportError("private-token")
    sync = service.CalendarSyncService()
    assert not sync.authenticate(interactive=False)
    fixture.load.assert_called_once_with(str(fixture.token))

    def recovered(_request):
        fixture.creds.valid = True

    fixture.creds.refresh.side_effect = recovered
    assert sync.authenticate(interactive=False)
    assert sync.is_authenticated
    assert sync.last_error_kind is None
    fixture.login.assert_not_called()
    fixture.save.assert_called_once_with("synthetic-refreshed-token")


def test_refresh_with_narrowed_grant_requires_sign_in_without_saving(expired_connection):
    fixture = expired_connection

    def narrowed(_request):
        fixture.creds.valid = True
        fixture.creds.granted_scopes = ["https://www.googleapis.com/auth/calendar.readonly"]

    fixture.creds.refresh.side_effect = narrowed
    sync = service.CalendarSyncService()

    assert not sync.authenticate(interactive=False)

    assert sync.last_error_kind == "auth_required"
    assert sync.last_error_status == 401
    assert fixture.token.read_bytes() == fixture.original
    fixture.save.assert_not_called()
    fixture.build.assert_not_called()


@pytest.mark.parametrize("kind", ["network_unavailable", "operation_failed", "auth_modules"])
def test_metadata_reader_preserves_the_actual_auth_failure(monkeypatch, kind):
    def failed(candidate, **kwargs):
        candidate._set_last_error(kind, kind)
        return False

    monkeypatch.setattr(service.CalendarSyncService, "authenticate", failed)
    with pytest.raises(GoogleAuthError) as caught:
        service.CalendarSyncService().create_metadata_reader()
    assert caught.value.kind == kind


def _forbidden_calendar_list(**structured_error):
    return HttpError(
        Response({"status": "403"}),
        json.dumps({"error": {"message": "private insufficient scope", **structured_error}}).encode(
            "utf-8", errors="strict"
        ),
    )


@pytest.mark.parametrize(
    "error, kind, remains_authenticated",
    [
        (TransportError("private-token"), "network_unavailable", True),
        (RefreshError("private-token", {"error": "invalid_grant"}), "auth_required", False),
        (_forbidden_calendar_list(), "calendar_list", True),
        (
            _forbidden_calendar_list(errors=[{"reason": "insufficientPermissions"}]),
            "reauth_required",
            False,
        ),
        (
            _forbidden_calendar_list(details=[{"reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}]),
            "reauth_required",
            False,
        ),
    ],
)
def test_calendar_metadata_distinguishes_refresh_and_scope_errors(
    monkeypatch, caplog, error, kind, remains_authenticated
):
    sync = service.CalendarSyncService()
    sync.service = object()
    sync.is_authenticated = True
    monkeypatch.setattr(sync, "_execute_request", Mock(side_effect=error))

    assert sync.list_accessible_calendars() == []

    assert sync.last_error_kind == kind
    assert sync.is_authenticated is remains_authenticated
    assert (sync.service is not None) is remains_authenticated
    assert "private-token" not in caplog.text
    assert "private insufficient scope" not in caplog.text
