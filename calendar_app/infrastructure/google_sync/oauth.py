# -*- coding: utf-8 -*-
"""Desktop OAuth validation and a cancellable loopback callback listener."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import time
from urllib.parse import parse_qs, urlsplit
import webbrowser

from calendar_app.infrastructure.i18n import t

AUTH_TIMEOUT_SECONDS = 180


class GoogleAuthError(Exception):
    def __init__(self, kind):
        self.kind = kind
        super().__init__(kind)


def load_desktop_client_config(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as source:
            config = json.load(source)
    except (OSError, ValueError):
        raise GoogleAuthError("auth_client_invalid") from None
    if isinstance(config, dict) and "web" in config:
        raise GoogleAuthError("auth_client_type")
    if not isinstance(config, dict):
        raise GoogleAuthError("auth_client_invalid")
    client = config.get("installed")
    if not isinstance(client, dict) or not all(
        isinstance(client.get(key), str) and client[key].strip()
        for key in ("client_id", "client_secret", "auth_uri", "token_uri")
    ):
        raise GoogleAuthError("auth_client_invalid")
    # A selected JSON file must never direct tokens to an arbitrary endpoint.
    if (
        client["auth_uri"] != "https://accounts.google.com/o/oauth2/auth"
        and client["auth_uri"] != "https://accounts.google.com/o/oauth2/v2/auth"
    ):
        raise GoogleAuthError("auth_client_invalid")
    if client["token_uri"] not in {
        "https://oauth2.googleapis.com/token",
        "https://accounts.google.com/o/oauth2/token",
    }:
        raise GoogleAuthError("auth_client_invalid")
    return config


def check_auth_cancelled(is_cancelled):
    if is_cancelled and is_cancelled():
        raise GoogleAuthError("auth_cancelled")


def _oauth_failure_kind(code):
    if not isinstance(code, str):
        return "auth"
    if code == "redirect_uri_mismatch":
        return "auth_redirect"
    if code in {"invalid_client", "unauthorized_client"}:
        return "auth_client_invalid"
    if code in {"server_error", "temporarily_unavailable"}:
        return "network_unavailable"
    if code in {"access_denied", "invalid_scope", "invalid_grant"}:
        return "auth_denied"
    return "auth"


def run_desktop_auth(flow, *, is_cancelled=None, timeout_seconds=AUTH_TIMEOUT_SECONDS):
    """Keep callback/state handling local; never log OAuth URLs or query values."""
    from oauthlib.oauth2 import OAuth2Error
    from requests.exceptions import ConnectionError as RequestConnectionError
    from requests.exceptions import Timeout

    check_auth_cancelled(is_cancelled)
    callback_query = None
    callback_error = None
    expected_state = None

    class CallbackHandler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(1)

        def log_message(self, *args):
            pass

        def do_GET(self):
            nonlocal callback_query, callback_error
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query, keep_blank_values=True)
            code = query.get("code", [])
            error = query.get("error", [])
            valid = (
                parsed.path == "/"
                and query.get("state") == [expected_state]
                and len(code) + len(error) == 1
                and bool((code or error)[0])
            )
            if valid:
                callback_query = parsed.query
                callback_error = error[0] if error else None
            self.send_response(200 if valid else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            message = t(
                "gcal_settings.auth_browser_return", "Air Calendar로 돌아가 인증 결과를 확인하세요."
            )
            self.wfile.write(message.encode("utf-8", errors="strict"))

    try:
        server = HTTPServer(("127.0.0.1", 0), CallbackHandler)
    except OSError:
        raise GoogleAuthError("auth_listener") from None
    with server:
        server.timeout = 0.2
        flow.redirect_uri = f"http://127.0.0.1:{server.server_port}/"
        auth_url, expected_state = flow.authorization_url(prompt="consent")
        check_auth_cancelled(is_cancelled)
        try:
            browser_opened = webbrowser.open(auth_url, new=1, autoraise=True)
        except (OSError, webbrowser.Error):
            raise GoogleAuthError("auth_browser") from None
        if not browser_opened:
            raise GoogleAuthError("auth_browser")
        deadline = time.monotonic() + timeout_seconds
        while callback_query is None:
            check_auth_cancelled(is_cancelled)
            if time.monotonic() >= deadline:
                raise GoogleAuthError("auth_timeout")
            server.handle_request()
        check_auth_cancelled(is_cancelled)
        if callback_error:
            raise GoogleAuthError(_oauth_failure_kind(callback_error))
        # oauthlib requires https when parsing, as in InstalledAppFlow.run_local_server.
        response = flow.redirect_uri.replace("http://", "https://", 1) + "?" + callback_query
        try:
            flow.fetch_token(authorization_response=response, timeout=12)
        except OAuth2Error as exc:
            raise GoogleAuthError(_oauth_failure_kind(exc.error)) from None
        except (RequestConnectionError, Timeout):
            raise GoogleAuthError("network_unavailable") from None
        except Warning as exc:
            # oauthlib reports a changed consent scope via a structured warning.
            if hasattr(exc, "new_scope"):
                raise GoogleAuthError("auth_denied") from None
            raise
        check_auth_cancelled(is_cancelled)
        return flow.credentials
