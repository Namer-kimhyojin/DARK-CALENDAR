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


def run_desktop_auth(flow, *, is_cancelled=None, timeout_seconds=AUTH_TIMEOUT_SECONDS):
    """Keep callback/state handling local; never log OAuth URLs or query values."""
    check_auth_cancelled(is_cancelled)
    callback_query = None
    expected_state = None

    class CallbackHandler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(1)

        def log_message(self, *args):
            pass

        def do_GET(self):
            nonlocal callback_query
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            valid = (
                parsed.path == "/"
                and query.get("state") == [expected_state]
                and bool(query.get("code") or query.get("error"))
            )
            if valid:
                callback_query = parsed.query
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
        if not webbrowser.open(auth_url, new=1, autoraise=True):
            raise GoogleAuthError("auth_browser")
        deadline = time.monotonic() + timeout_seconds
        while callback_query is None:
            check_auth_cancelled(is_cancelled)
            if time.monotonic() >= deadline:
                raise GoogleAuthError("auth_timeout")
            server.handle_request()
        check_auth_cancelled(is_cancelled)
        error = parse_qs(callback_query).get("error", [None])[0]
        if error:
            kind = "auth_redirect" if error == "redirect_uri_mismatch" else "auth_denied"
            raise GoogleAuthError(kind)
        # oauthlib requires https when parsing, as in InstalledAppFlow.run_local_server.
        response = flow.redirect_uri.replace("http://", "https://", 1) + "?" + callback_query
        flow.fetch_token(authorization_response=response, timeout=12)
        check_auth_cancelled(is_cancelled)
        return flow.credentials
