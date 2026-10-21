# -*- coding: utf-8 -*-
"""Remove credential-bearing diagnostics before either log handler writes them."""

import copy
import logging
import re

_REDACTED = "[redacted]"
_URL = re.compile(r"""(?i)\b(?:https?|webcals?)://[^\s<>"']+""")
_SECRET = re.compile(
    r"""(?ix)
    (["']?\b(?:access_token|refresh_token|id_token|client_secret|client_assertion|
    code_verifier|authorization_code|password|app_password|api_key|secret|
    token|code|state)["']?\s*[:=]\s*)
    (?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,;&}\]]+)
    """
)
_AUTH = re.compile(
    r"""(?i)(\b(?:authorization|proxy-authorization)\b["']?\s*[:=]\s*)
    (?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\r\n,}]+)""",
    re.VERBOSE,
)
_BEARER = re.compile(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+")
_COOKIE = re.compile(
    r"""(?i)(\b(?:set-cookie|cookie)\b["']?\s*[:=]\s*)
    (?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\r\n]+)""",
    re.VERBOSE,
)


def redact_diagnostic_text(value):
    """Hide full URLs (including secret paths) and recognizable credential fields."""
    text = str(value)
    text = _URL.sub("[redacted-url]", text)
    text = _AUTH.sub(lambda match: match[1] + _REDACTED, text)
    text = _COOKIE.sub(lambda match: match[1] + _REDACTED, text)
    text = _SECRET.sub(lambda match: match[1] + _REDACTED, text)
    return _BEARER.sub(lambda match: match[1] + " " + _REDACTED, text)


class PrivacyFormatter(logging.Formatter):
    """Cover message arguments and chained exceptions without mutating other handlers."""

    def format(self, record):
        isolated = copy.copy(record)
        isolated.exc_text = None
        return redact_diagnostic_text(super().format(isolated))
