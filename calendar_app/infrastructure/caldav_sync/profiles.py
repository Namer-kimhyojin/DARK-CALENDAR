# -*- coding: utf-8 -*-
"""Service-specific discovery, credential and capability policy."""

import hashlib
import re
from urllib.parse import urlparse

from calendar_app.application.calendar_sync_contract import CalendarSyncError

PROFILES = {
    "icloud": {
        "url": "https://caldav.icloud.com/",
        "writable": True,
        "help": "https://support.apple.com/en-us/102654",
    },
    "naver": {
        "url": "https://caldav.calendar.naver.com/",
        "writable": False,
        "help": "https://help.naver.com/service/5620/contents/2426?lang=ko&osType=COMMONOS",
    },
}


def validate_url(service, url):
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        valid_host = (
            (host == "caldav.icloud.com" or bool(re.fullmatch(r"p\d+-caldav\.icloud\.com", host)))
            if service == "icloud"
            else service == "naver" and host == "caldav.calendar.naver.com"
        )
        if (
            not valid_host
            or parsed.scheme != "https"
            or parsed.port not in (None, 443)
            or parsed.username
            or parsed.password
            or parsed.fragment
            or parsed.query
        ):
            raise ValueError
        return url
    except ValueError as exc:
        raise CalendarSyncError("unsafe_caldav_url") from exc


def account_key(service, username):
    if service not in PROFILES or not username.strip():
        raise CalendarSyncError("credentials_required")
    digest = hashlib.sha256(username.strip().lower().encode("utf-8", errors="strict")).hexdigest()[
        :24
    ]
    return f"caldav::{service}::{digest}"
