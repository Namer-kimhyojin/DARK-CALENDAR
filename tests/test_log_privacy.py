# -*- coding: utf-8 -*-
"""Credential diagnostics never reach console or file log handlers verbatim."""

import logging
import sys

import pytest

from calendar_app.shared.log_privacy import PrivacyFormatter, redact_diagnostic_text


@pytest.mark.parametrize(
    "message",
    [
        '{"access_token": "SYNTHETIC_PRIVATE_VALUE"}',
        "{'refresh_token': 'SYNTHETIC_PRIVATE_VALUE'}",
        "client_secret=SYNTHETIC_PRIVATE_VALUE&scope=calendar",
        "code_verifier: SYNTHETIC_PRIVATE_VALUE",
        "Authorization: Bearer SYNTHETIC_PRIVATE_VALUE",
        "{'Authorization': 'Basic SYNTHETIC_PRIVATE_VALUE'}",
        "Proxy-Authorization: Basic SYNTHETIC_PRIVATE_VALUE",
        "Cookie: session=SYNTHETIC_PRIVATE_VALUE; other=hidden",
        "Set-Cookie: session=SYNTHETIC_PRIVATE_VALUE",
        "{'Cookie': 'session=SYNTHETIC_PRIVATE_VALUE'}",
        '{"Set-Cookie": "session=SYNTHETIC_PRIVATE_VALUE"}',
        r'{"Cookie": "session=\"SYNTHETIC_PRIVATE_VALUE\""}',
        r'{"Authorization": "Bearer \"SYNTHETIC_PRIVATE_VALUE\""}',
        "https://user:SYNTHETIC_PRIVATE_VALUE@example.invalid/private-feed?token=hidden#fragment",
        "webcal://example.invalid/SYNTHETIC_PRIVATE_VALUE/feed",
        "password='SYNTHETIC_PRIVATE_VALUE with spaces'",
    ],
)
def test_sensitive_diagnostics_are_redacted(message):
    result = redact_diagnostic_text(message)
    assert "SYNTHETIC_PRIVATE_VALUE" not in result
    assert "redacted" in result


def test_formatter_covers_chained_exceptions_and_preserves_record():
    try:
        try:
            raise ValueError("https://example.invalid/SYNTHETIC_PRIVATE_VALUE")
        except ValueError as exc:
            raise RuntimeError("refresh_token=SYNTHETIC_SECOND_VALUE") from exc
    except RuntimeError:
        record = logging.LogRecord(
            "network",
            logging.ERROR,
            __file__,
            1,
            "Failure %s",
            ("Bearer SYNTHETIC_THIRD_VALUE",),
            sys.exc_info(),
        )
    rendered = PrivacyFormatter("%(levelname)s %(message)s").format(record)
    assert all(
        value not in rendered
        for value in (
            "SYNTHETIC_PRIVATE_VALUE",
            "SYNTHETIC_SECOND_VALUE",
            "SYNTHETIC_THIRD_VALUE",
        )
    )
    assert "ValueError" in rendered and "RuntimeError" in rendered
    assert "SYNTHETIC_THIRD_VALUE" in record.getMessage()
    assert record.exc_text is None


def test_both_startup_handlers_use_privacy_formatter(tmp_path, monkeypatch):
    from calendar_app.infrastructure.runtime import crash_bootstrap

    configured = {}
    monkeypatch.setattr(logging, "basicConfig", lambda **kwargs: configured.update(kwargs))
    monkeypatch.setattr(crash_bootstrap.faulthandler, "enable", lambda **kwargs: None)
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    stream = crash_bootstrap.setup_crash_logging(str(tmp_path / "isolated.log"))
    try:
        assert len(configured["handlers"]) == 2
        for handler in configured["handlers"]:
            assert isinstance(handler.formatter, PrivacyFormatter)
            record = logging.LogRecord(
                "network",
                logging.WARNING,
                __file__,
                1,
                "access_token=%s",
                ("SYNTHETIC_PRIVATE_VALUE",),
                None,
            )
            assert "SYNTHETIC_PRIVATE_VALUE" not in handler.format(record)
    finally:
        if stream:
            stream.close()
        for handler in configured["handlers"]:
            handler.close()


def test_safe_error_codes_remain_diagnostic():
    message = "network_unavailable; HTTP 429; sqlite SQLITE_BUSY"
    assert redact_diagnostic_text(message) == message
