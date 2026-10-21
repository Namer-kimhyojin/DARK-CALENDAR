# -*- coding: utf-8 -*-
"""Bounded reads for credential-bearing calendar HTTP clients."""

from time import monotonic

import requests
from urllib3.exceptions import HTTPError

from calendar_app.application.calendar_sync_contract import CalendarSyncError

MAX_RESPONSE_SECONDS = 60


def read_calendar_response(response, *, max_bytes, deadline, cancelled, invalid_code):
    """Read identity content without waiting to fill a large streaming chunk.

    The callers request identity encoding and own response cleanup. A socket read
    retains their finite read timeout; cancellation/deadline checks run between
    raw reads, including when a peer supplies only a few bytes at a time.
    """
    headers = requests.structures.CaseInsensitiveDict(response.headers)
    if headers.get("Content-Encoding", "").strip().lower() not in {"", "identity"}:
        raise CalendarSyncError(invalid_code)
    length = headers.get("Content-Length", "")
    if length.isdecimal() and (len(length) > 20 or int(length) > max_bytes):
        raise CalendarSyncError("calendar_response_too_large")
    content = bytearray()
    try:
        while True:
            if cancelled():
                raise CalendarSyncError("cancelled")
            if monotonic() >= deadline:
                raise CalendarSyncError("network_unavailable")
            chunk = response.raw.read1(
                min(65536, max_bytes - len(content) + 1), decode_content=False
            )
            if cancelled():
                raise CalendarSyncError("cancelled")
            if monotonic() >= deadline:
                raise CalendarSyncError("network_unavailable")
            if not isinstance(chunk, bytes):
                raise CalendarSyncError(invalid_code)
            if not chunk:
                return bytes(content)
            if len(content) + len(chunk) > max_bytes:
                raise CalendarSyncError("calendar_response_too_large")
            content.extend(chunk)
    except (HTTPError, requests.RequestException, OSError) as exc:
        raise CalendarSyncError("network_unavailable") from exc
