# -*- coding: utf-8 -*-
import json
import os
import socket
import threading
import time
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from oauthlib.oauth2 import InvalidClientError
from PyQt6.QtCore import QSettings, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QWidget
import pytest
from requests import Request, Response
from requests.exceptions import ConnectTimeout
from requests_oauthlib import OAuth2Session

from calendar_app.infrastructure.google_sync import oauth, service, token_store
from calendar_app.presentation.dialogs import gcal_settings_dialog as dialog_module

DESKTOP_CONFIG = {
    "installed": {
        "client_id": "test-client",
        "client_secret": "test-secret",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}


@pytest.mark.parametrize(
    "config,kind",
    [
        ({"web": DESKTOP_CONFIG["installed"]}, "auth_client_type"),
        ({"installed": {}}, "auth_client_invalid"),
        ([], "auth_client_invalid"),
        (
            {"installed": {**DESKTOP_CONFIG["installed"], "token_uri": "https://example.com"}},
            "auth_client_invalid",
        ),
    ],
)
def test_invalid_client_rejected(config, kind, tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps(config), encoding="utf-8", errors="strict")
    with pytest.raises(oauth.GoogleAuthError) as caught:
        oauth.load_desktop_client_config(path)
    assert caught.value.kind == kind


def test_desktop_client_accepted(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps(DESKTOP_CONFIG), encoding="utf-8", errors="strict")
    assert oauth.load_desktop_client_config(path) == DESKTOP_CONFIG


class FakeFlow:
    def __init__(self, fetch_error=None):
        self.credentials = object()
        self.fetch_calls = []
        self.fetch_error = fetch_error

    def authorization_url(self, **kwargs):
        return "https://accounts.google.com/test", "expected-state"

    def fetch_token(self, **kwargs):
        self.fetch_calls.append(kwargs)
        if self.fetch_error:
            raise self.fetch_error


@pytest.mark.parametrize(
    "error, fetch_error, kind",
    [
        (None, None, None),
        ("access_denied", None, "auth_denied"),
        ("redirect_uri_mismatch", None, "auth_redirect"),
        (None, InvalidClientError(description="private-response"), "auth_client_invalid"),
        (None, ConnectTimeout("private-response"), "network_unavailable"),
    ],
)
def test_loopback_state_validation_and_result(monkeypatch, error, fetch_error, kind, caplog):
    flow = FakeFlow(fetch_error)
    responses = []

    def browser_open(*args, **kwargs):
        def callback():
            for query in (
                "?state=wrong&code=bad",
                "?state=expected-state&code=one&code=two",
                "?state=expected-state&code=test-code&error=access_denied",
                "favicon.ico",
                "?state=expected-state&" + ("error=" + error if error else "code=test-code"),
            ):
                try:
                    with urlopen(flow.redirect_uri + query, timeout=2) as response:
                        responses.append(response.status)
                except HTTPError as exc:
                    responses.append(exc.code)

        thread = threading.Thread(target=callback)
        thread.start()
        threads.append(thread)
        return True

    threads = []
    monkeypatch.setattr(oauth.webbrowser, "open", browser_open)
    if kind:
        with pytest.raises(oauth.GoogleAuthError) as caught:
            oauth.run_desktop_auth(flow, timeout_seconds=2)
        assert caught.value.kind == kind
        assert "private-response" not in str(caught.value)
    else:
        assert oauth.run_desktop_auth(flow, timeout_seconds=2) is flow.credentials
    if error:
        assert flow.fetch_calls == []
    else:
        assert flow.fetch_calls[0]["timeout"] == 12
        assert flow.fetch_calls[0]["authorization_response"].startswith("https://127.0.0.1:")
    for thread in threads:
        thread.join(2)
        assert not thread.is_alive()
    assert responses == [400, 400, 400, 400, 200]
    assert "private-response" not in caplog.text
    port = int(flow.redirect_uri.split(":")[-1].rstrip("/"))
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0


@pytest.mark.parametrize(
    "case,kind",
    [("timeout", "auth_timeout"), ("cancel", "auth_cancelled"), ("browser", "auth_browser")],
)
def test_loopback_stops_without_browser_response(monkeypatch, case, kind):
    monkeypatch.setattr(oauth.webbrowser, "open", lambda *a, **k: case != "browser")
    deadline = time.monotonic() + 0.05

    def cancelled():
        return case == "cancel" and time.monotonic() >= deadline

    with pytest.raises(oauth.GoogleAuthError) as caught:
        oauth.run_desktop_auth(FakeFlow(), is_cancelled=cancelled, timeout_seconds=0.05)
    assert caught.value.kind == kind


def test_browser_launch_os_error_has_browser_recovery(monkeypatch):
    def cannot_open(*args, **kwargs):
        raise OSError("private-browser-error")

    monkeypatch.setattr(oauth.webbrowser, "open", cannot_open)
    with pytest.raises(oauth.GoogleAuthError, match="^auth_browser$"):
        oauth.run_desktop_auth(FakeFlow())


def test_service_rejects_web_before_browser_and_preserves_token(monkeypatch, tmp_path):
    client = tmp_path / "credentials.json"
    token = tmp_path / "token.json"
    client.write_text(
        json.dumps({"web": DESKTOP_CONFIG["installed"]}), encoding="utf-8", errors="strict"
    )
    token.write_bytes(b"existing-token")
    monkeypatch.setattr(service, "CREDENTIALS_PATH", str(client))
    monkeypatch.setattr(service, "TOKEN_PATH", str(token))
    monkeypatch.setattr(
        oauth.webbrowser, "open", lambda *a, **k: pytest.fail("Browser must not open")
    )
    sync = service.CalendarSyncService()
    assert not sync.authenticate(force_reauth=True)
    assert sync.last_error_kind == "auth_client_type"
    assert token.read_bytes() == b"existing-token"


def test_atomic_token_save_keeps_old_file_on_replace_failure(monkeypatch, tmp_path):
    path = tmp_path / "token.json"
    path.write_bytes(b"existing-token")
    monkeypatch.setattr(token_store, "_dpapi_crypt", lambda *a, **k: b"protected-token")

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(token_store.os, "replace", fail)
    with pytest.raises(OSError):
        token_store.save_token_json("{}", str(path))
    assert path.read_bytes() == b"existing-token"
    assert list(tmp_path.iterdir()) == [path]


def test_service_defers_token_save_until_dialog_accepts_result(monkeypatch, tmp_path):
    client = tmp_path / "credentials.json"
    client.write_text(json.dumps(DESKTOP_CONFIG), encoding="utf-8", errors="strict")
    monkeypatch.setattr(service, "CREDENTIALS_PATH", str(client))
    monkeypatch.setattr(service, "TOKEN_PATH", str(tmp_path / "token.json"))
    browser_threads = []

    def browser_open(url, **kwargs):
        query = parse_qs(urlsplit(url).query)
        assert query["access_type"] == ["offline"]
        assert query["code_challenge_method"] == ["S256"]
        redirect_uri = query["redirect_uri"][0]
        assert urlsplit(redirect_uri).hostname == "127.0.0.1"

        def callback():
            params = urlencode({"state": query["state"][0], "code": "synthetic-code"})
            with urlopen(f"{redirect_uri}?{params}", timeout=2) as response:
                assert response.status == 200

        thread = threading.Thread(target=callback)
        thread.start()
        browser_threads.append(thread)
        return True

    def request_token(session, method, url, **kwargs):
        assert method == "POST" and url == "https://oauth2.googleapis.com/token"
        assert kwargs["timeout"] == 12
        response = Response()
        response.status_code = 200
        response.request = session.prepare_request(Request(method, url, data=kwargs["data"]))
        response._content = json.dumps(
            {
                "access_token": "synthetic-access-token",
                "refresh_token": "synthetic-refresh-token",
                "scope": " ".join(service.SCOPES),
                "expires_in": 3600,
                "token_type": "Bearer",
            }
        ).encode("utf-8", errors="strict")
        return response

    monkeypatch.setattr(oauth.webbrowser, "open", browser_open)
    monkeypatch.setattr(OAuth2Session, "request", request_token)
    monkeypatch.setattr(service, "build", lambda *a, **k: object())
    monkeypatch.setattr(
        token_store, "save_token_json", lambda *a: pytest.fail("Must defer token save")
    )
    sync = service.CalendarSyncService()
    assert not sync.authenticate(interactive=False)
    assert sync.last_error_kind == "auth_required"
    assert not browser_threads
    assert sync.authenticate(force_reauth=True, persist_token=False)
    browser_threads[0].join(2)
    assert not browser_threads[0].is_alive()
    assert json.loads(sync._pending_token_json)["refresh_token"] == "synthetic-refresh-token"
    assert not (tmp_path / "token.json").exists()
    assert sync.is_authenticated


@pytest.mark.parametrize(
    "valid, refresh_token, granted_scopes",
    [
        (False, "synthetic", service.SCOPES),
        (True, None, service.SCOPES),
        (True, "synthetic", []),
    ],
)
def test_incomplete_sign_in_preserves_old_connection(
    monkeypatch, tmp_path, valid, refresh_token, granted_scopes
):
    client = tmp_path / "credentials.json"
    client.write_text(json.dumps(DESKTOP_CONFIG), encoding="utf-8", errors="strict")
    token = tmp_path / "token.json"
    original = b"DCTOK1synthetic-previous-token"
    token.write_bytes(original)
    monkeypatch.setattr(service, "CREDENTIALS_PATH", str(client))
    monkeypatch.setattr(service, "TOKEN_PATH", str(token))
    creds = SimpleNamespace(
        valid=valid,
        refresh_token=refresh_token,
        scopes=service.SCOPES,
        granted_scopes=granted_scopes,
    )
    monkeypatch.setattr(service, "run_desktop_auth", lambda *a, **k: creds)
    monkeypatch.setattr(service, "build", lambda *a, **k: pytest.fail("Invalid grant"))
    sync = service.CalendarSyncService()

    assert not sync.authenticate(force_reauth=True, persist_token=False)

    assert sync.last_error_kind == "auth_denied"
    assert sync._pending_token_json is None
    assert not sync.is_authenticated and sync.service is None
    assert token.read_bytes() == original


def test_service_requires_auth_when_legacy_token_protection_fails(monkeypatch, tmp_path):
    path = tmp_path / "token.json"
    raw = json.dumps({"token": "synthetic", "scopes": service.SCOPES}).encode(
        "utf-8", errors="strict"
    )
    path.write_bytes(raw)
    monkeypatch.setattr(service, "TOKEN_PATH", str(path))
    monkeypatch.setattr(token_store, "TOKEN_PATH", str(path))

    def fail(data, encrypt):
        raise OSError("synthetic encryption failure")

    monkeypatch.setattr(token_store, "_dpapi_crypt", fail)
    monkeypatch.setattr(
        service.Credentials,
        "from_authorized_user_info",
        lambda *a: pytest.fail("Unprotected credentials must not be used"),
    )
    monkeypatch.setattr(service, "build", lambda *a, **k: pytest.fail("Must require auth"))
    sync = service.CalendarSyncService()
    assert not sync.authenticate(interactive=False)
    assert sync.last_error_kind == "auth_required"
    assert not sync.is_authenticated
    assert sync.service is None
    assert path.read_bytes() == raw


def test_service_rejects_auth_when_token_encryption_fails(monkeypatch, tmp_path):
    client = tmp_path / "credentials.json"
    client.write_text(json.dumps(DESKTOP_CONFIG), encoding="utf-8", errors="strict")
    path = tmp_path / "token.json"
    previous = b"DCTOK1previous-encrypted-token"
    path.write_bytes(previous)
    monkeypatch.setattr(service, "CREDENTIALS_PATH", str(client))
    monkeypatch.setattr(service, "TOKEN_PATH", str(path))
    monkeypatch.setattr(token_store, "TOKEN_PATH", str(path))
    creds = SimpleNamespace(
        valid=True,
        scopes=service.SCOPES,
        refresh_token="synthetic",
        to_json=lambda: "synthetic-token",
    )
    monkeypatch.setattr(service, "run_desktop_auth", lambda *a, **k: creds)
    monkeypatch.setattr(service, "build", lambda *a, **k: object())

    def fail(data, encrypt):
        raise OSError("synthetic encryption failure")

    monkeypatch.setattr(token_store, "_dpapi_crypt", fail)
    sync = service.CalendarSyncService()
    assert not sync.authenticate(force_reauth=True)
    assert sync.last_error_kind == "auth_token_write"
    assert sync.last_error_message == "token_write_failed"
    assert not sync.is_authenticated
    assert sync.service is None
    assert sync._pending_token_json is None
    assert path.read_bytes() == previous
    assert sorted(item.name for item in tmp_path.iterdir()) == ["credentials.json", "token.json"]


def test_expired_token_refresh_uses_bounded_request_and_independent_metadata_reader(
    monkeypatch, tmp_path
):
    import json

    token = tmp_path / "token.json"
    token.write_text(json.dumps({"scopes": service.SCOPES}), encoding="utf-8", errors="strict")
    monkeypatch.setattr(service, "TOKEN_PATH", str(token))
    from calendar_app.infrastructure.google_sync import token_store

    monkeypatch.setattr(
        token_store,
        "load_token_json",
        lambda *args: token.read_text(encoding="utf-8", errors="strict"),
    )
    credentials = SimpleNamespace(
        valid=False,
        expired=True,
        refresh_token="synthetic",
        scopes=service.SCOPES,
        to_json=lambda: "{}",
    )
    requests = []

    def refresh(request):
        request("https://oauth2.googleapis.com/token", timeout=120)
        credentials.valid = True

    credentials.refresh = refresh
    monkeypatch.setattr(service.Credentials, "from_authorized_user_info", lambda *args: credentials)
    monkeypatch.setattr(service, "Request", lambda: lambda *args, **kwargs: requests.append(kwargs))
    monkeypatch.setattr(service, "build", lambda *args, **kwargs: object())
    original = service.CalendarSyncService(calendar_id="team", time_zone="UTC")
    original.service = object()
    original.is_authenticated = True
    reader = original.create_metadata_reader()
    assert reader is not original and reader.service is not original.service
    assert reader.calendar_id == "team" and reader.time_zone == "UTC"
    assert original.is_authenticated and reader.is_authenticated
    assert requests == [{"timeout": 12}]


class WaitingService:
    def __init__(self):
        self.started = threading.Event()
        self.last_error_kind = None
        self._pending_token_json = None

    def authenticate(self, **kwargs):
        self.started.set()
        while not kwargs["is_cancelled"]():
            time.sleep(0.005)
        self._set_last_error("auth_cancelled", "cancelled")
        return False

    def _set_last_error(self, kind, message):
        self.last_error_kind = kind


def wait_for_worker(dialog):
    for _ in range(200):
        QTest.qWait(10)
        if dialog._auth_worker is None:
            return
    pytest.fail("Auth worker did not finish")


@pytest.fixture
def dialog_metadata(monkeypatch):
    from calendar_app.infrastructure.db import calendar_repo, task_repo
    from calendar_app.infrastructure.google_sync import common

    monkeypatch.setattr(calendar_repo, "list_calendars", lambda **kwargs: [])
    monkeypatch.setattr(common, "get_default_gcal_calendar_id", lambda settings: "primary")
    for name in (
        "count_unified_task_gcal_errors",
        "count_gcal_delete_queue_errors",
        "count_gcal_sync_conflicts",
    ):
        monkeypatch.setattr(task_repo, name, lambda: 0)
    monkeypatch.setattr(task_repo, "get_gcal_delete_queue", lambda: [])


@pytest.mark.parametrize("close", [False, True])
def test_dialog_remains_responsive_and_preserves_connection(
    monkeypatch, tmp_path, close, dialog_metadata
):
    app = QApplication.instance() or QApplication([])
    parent = QWidget()
    parent.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    old_service = SimpleNamespace(is_authenticated=False, service=None)
    parent.gcal_sync = old_service
    parent._bg_workers = []
    candidate = WaitingService()
    monkeypatch.setattr(service, "prepare_calendar_sync_service", lambda *a, **k: candidate)
    monkeypatch.setattr(
        dialog_module.GCalSettingsDialog, "_copy_credentials_if_needed", lambda self: True
    )
    dialog = dialog_module.GCalSettingsDialog(parent)
    save_enabled = dialog.save_btn.isEnabled()
    dialog.show()
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(5)
    try:
        dialog.run_auth()
        assert dialog._auth_worker is not None
        assert not dialog.save_btn.isEnabled()
        for _ in range(100):
            QTest.qWait(10)
            if candidate.started.is_set() and len(ticks) >= 3:
                break
        assert candidate.started.is_set()
        assert len(ticks) >= 2
        if close:
            dialog.reject()
        else:
            dialog.cancel_operation_btn.click()
        wait_for_worker(dialog)
        assert parent.gcal_sync is old_service
        assert parent._bg_workers == []
        assert parent.settings.value("gcal_enabled") is None
        assert dialog.save_btn.isEnabled() == save_enabled
        if close:
            assert not dialog.isVisible()
            assert dialog.result() == QDialog.DialogCode.Rejected
        else:
            assert dialog.isVisible()
            # A cancelled attempt must release its worker and allow another attempt.
            dialog.run_auth()
            dialog.cancel_operation_btn.click()
            wait_for_worker(dialog)
    finally:
        timer.stop()
        if dialog._auth_worker is not None:
            dialog._auth_worker.requestInterruption()
            wait_for_worker(dialog)
        dialog.close()
        parent.close()
        app.processEvents()


def test_dialog_rejects_web_file_before_copy(monkeypatch, tmp_path, dialog_metadata):
    app = QApplication.instance() or QApplication([])
    old_file = tmp_path / "existing.json"
    old_file.write_bytes(b"existing-credentials")
    web_file = tmp_path / "web.json"
    web_file.write_text(
        json.dumps({"web": DESKTOP_CONFIG["installed"]}), encoding="utf-8", errors="strict"
    )
    parent = QWidget()
    parent.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    parent.gcal_sync = None
    dialog = dialog_module.GCalSettingsDialog(parent)
    dialog.creds_path_edit.setText(str(web_file))
    warnings = []
    monkeypatch.setattr(dialog_module, "CREDENTIALS_PATH", str(old_file))
    monkeypatch.setattr(dialog_module.QMessageBox, "warning", lambda *args: warnings.append(args))
    try:
        dialog.run_auth()
        assert dialog._auth_worker is None
        assert warnings == []
        assert dialog._feedback_code == "auth_client_type"
        assert "redirect_uri_mismatch" in dialog.connection_feedback.text()
        assert old_file.read_bytes() == b"existing-credentials"
    finally:
        dialog.close()
        parent.close()
        app.processEvents()
