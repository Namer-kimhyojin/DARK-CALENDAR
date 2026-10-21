# -*- coding: utf-8 -*-
"""Synthetic credentials and calendar data must not escape error boundaries."""

import base64
import hashlib
import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import httplib2
import pytest

from calendar_app.infrastructure.google_sync import service, token_store
from tests.test_gcal_oauth import DESKTOP_CONFIG

PRIVATE_MARKER = "synthetic-private-calendar-payload"


def _sync():
    sync = service.CalendarSyncService(calendar_id="team")
    sync.is_authenticated = True
    sync.service = Mock()
    return sync


def _remote_error(status=403, reason="forbidden"):
    return service.HttpError(
        httplib2.Response({"status": str(status)}),
        json.dumps(
            {
                "error": {
                    "message": PRIVATE_MARKER,
                    "errors": [{"reason": reason, "message": PRIVATE_MARKER}],
                },
            }
        ).encode("utf-8", errors="strict"),
        uri=f"https://www.googleapis.com/calendar/v3/events?syncToken={PRIVATE_MARKER}",
    )


@pytest.mark.parametrize("method", ["subscribe_calendar", "unsubscribe_calendar"])
@pytest.mark.parametrize("kind", ["account_unverified", "account_mismatch"])
def test_subscription_mutations_share_account_identity_write_guard(method, kind):
    sync = _sync()
    sync._account_identity_mismatch = True
    sync._account_identity_error_kind = kind
    assert not getattr(sync, method)("team")
    assert sync.last_error_kind == kind
    sync.service.calendarList.assert_not_called()


@pytest.mark.parametrize(
    "operation",
    [
        "fetch",
        "sync_fetch",
        "create",
        "update",
        "delete",
        "move",
        "list",
        "subscribe",
        "unsubscribe",
    ],
)
def test_remote_error_payload_is_neither_logged_nor_returned(
    monkeypatch, caplog, capsys, operation
):
    sync = _sync()
    monkeypatch.setattr(sync, "_execute_request", Mock(side_effect=_remote_error()))
    caplog.set_level(logging.DEBUG, logger=service.__name__)
    calls = {
        "fetch": lambda: sync.fetch_events("2026-10-20"),
        "sync_fetch": lambda: sync.fetch_sync_events(),
        "create": lambda: sync.create_event(
            PRIVATE_MARKER, "2026-10-20", "2026-10-20", all_day=True
        ),
        "update": lambda: sync.update_event(
            "evt", PRIVATE_MARKER, "2026-10-20", "2026-10-20", all_day=True
        ),
        "delete": lambda: sync.delete_event("evt"),
        "move": lambda: sync.move_event("evt", "team", "other"),
        "list": lambda: sync.list_accessible_calendars(),
        "subscribe": lambda: sync.subscribe_calendar("team"),
        "unsubscribe": lambda: sync.unsubscribe_calendar("team"),
    }
    calls[operation]()
    assert sync.last_error_message == "http_403"
    output = capsys.readouterr()
    assert PRIVATE_MARKER not in output.out + output.err + caplog.text


@pytest.mark.parametrize(
    "status,reason", [(403, "userRateLimitExceeded"), (429, "rateLimitExceeded")]
)
def test_safe_errors_preserve_retry_classification(monkeypatch, status, reason):
    sync = _sync()
    monkeypatch.setattr(sync, "_execute_request", Mock(side_effect=_remote_error(status, reason)))
    sync.fetch_events("2026-10-20")
    assert sync.last_error_message == "rateLimitExceeded"
    assert service.is_google_rate_limit_error(sync.last_error_status, sync.last_error_message)


def test_transient_retry_log_has_no_exception_payload(monkeypatch, caplog):
    sync = _sync()
    caplog.set_level(logging.DEBUG, logger=service.__name__)
    monkeypatch.setattr(service.time, "sleep", lambda _delay: None)
    request = Mock(side_effect=[TimeoutError(PRIVATE_MARKER), "ok"])
    assert sync._execute_request(request, retries=1) == "ok"
    assert request.call_count == 2
    assert PRIVATE_MARKER not in caplog.text


def test_batch_callback_retains_only_bounded_error_code(caplog):
    sync = _sync()
    caplog.set_level(logging.DEBUG, logger=service.__name__)
    for error, expected in [
        (RuntimeError(PRIVATE_MARKER), "batch_failed"),
        (_remote_error(403, "rateLimitExceeded"), "rateLimitExceeded"),
    ]:

        def new_batch(*, callback, error=error):
            return SimpleNamespace(
                add=lambda *args, **kwargs: None,
                execute=lambda: callback("0", None, error),
            )

        sync.service.new_batch_http_request.side_effect = new_batch
        results = sync.batch_delete_events([{"local_task_id": 1, "event_id": "evt"}])
        assert results[0]["error"] == expected
        assert PRIVATE_MARKER not in json.dumps(results)
    assert PRIVATE_MARKER not in caplog.text


def test_create_diagnostics_do_not_include_event_content_or_remote_keys(monkeypatch, caplog):
    sync = _sync()
    caplog.set_level(logging.DEBUG, logger=service.__name__)
    monkeypatch.setattr(sync, "_execute_request", lambda _request: {PRIVATE_MARKER: PRIVATE_MARKER})
    assert sync.create_event(PRIVATE_MARKER, "2026-10-20", "2026-10-20", all_day=True) is None
    assert sync.last_error_message == "missing_id_in_response"
    assert PRIVATE_MARKER not in caplog.text


def test_authentication_constructs_s256_pkce_without_network(monkeypatch, tmp_path):
    client = tmp_path / "credentials.json"
    client.write_text(json.dumps(DESKTOP_CONFIG), encoding="utf-8", errors="strict")
    monkeypatch.setattr(service, "CREDENTIALS_PATH", str(client))
    captured = {}

    def local_auth(flow, **_kwargs):
        url, state = flow.authorization_url()
        captured.update(
            query=parse_qs(urlsplit(url).query), verifier=flow.code_verifier, state=state
        )
        return SimpleNamespace(valid=True, to_json=lambda: "{}")

    monkeypatch.setattr(service, "run_desktop_auth", local_auth)
    monkeypatch.setattr(service, "build", lambda *args, **kwargs: object())
    assert service.CalendarSyncService().authenticate(force_reauth=True, persist_token=False)
    query = captured["query"]
    expected = (
        base64.urlsafe_b64encode(
            hashlib.sha256(captured["verifier"].encode("utf-8", errors="strict")).digest()
        )
        .decode("utf-8", errors="strict")
        .rstrip("=")
    )
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"] == [expected]
    assert query["state"] == [captured["state"]]
    assert len(captured["state"]) >= 20


def test_token_decode_failure_does_not_log_decrypted_bytes(monkeypatch, tmp_path, caplog):
    path = tmp_path / "token.json"
    path.write_bytes(b"DCTOK1synthetic-encrypted-blob")
    monkeypatch.setattr(
        token_store,
        "_dpapi_crypt",
        lambda *_args, **_kwargs: PRIVATE_MARKER.encode("utf-8", errors="strict") + b"\xff",
    )
    assert token_store.load_token_json(str(path)) is None
    assert PRIVATE_MARKER not in caplog.text


def test_revocation_form_preserves_exact_token_value(monkeypatch, tmp_path):
    from urllib import request

    path = tmp_path / "token.json"
    path.write_bytes(b"synthetic-placeholder")
    monkeypatch.setattr(service, "TOKEN_PATH", str(path))
    value = "synthetic+token&token=other"
    monkeypatch.setattr(token_store, "load_token_json", lambda: json.dumps({"token": value}))
    sent = []

    def urlopen(req, **_kwargs):
        sent.append(req)
        context = Mock()
        context.__enter__ = Mock(return_value=SimpleNamespace(status=200))
        context.__exit__ = Mock(return_value=False)
        return context

    monkeypatch.setattr(request, "urlopen", urlopen)
    assert service.CalendarSyncService().revoke_token()
    assert parse_qs(sent[0].data.decode("utf-8", errors="strict")) == {"token": [value]}
