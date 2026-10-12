# -*- coding: utf-8 -*-
"""Atomic, Windows-user-encrypted credentials; never use QSettings for passwords."""

import json
import os
import re
import uuid

from calendar_app.app_paths import get_app_data_dir
from calendar_app.application.calendar_sync_contract import CalendarSyncError
from calendar_app.infrastructure.calendar_sync.secret_store import crypt

from .profiles import PROFILES, account_key, validate_url


class CalDAVCredentials:
    def __init__(self, folder=None):
        self.folder = folder or get_app_data_dir()

    def path(self, account):
        match = re.fullmatch(r"caldav::([a-z]+)::[a-f0-9]{24}", account)
        if not match or match[1] not in PROFILES:
            raise CalendarSyncError("account_mismatch")
        return self.folder / (account.replace("::", "-") + ".credential")

    def save(self, service, username, password, server_url=None):
        account = account_key(service, username)
        destination = self.path(account)
        temporary = destination.with_suffix("." + uuid.uuid4().hex + ".tmp")
        try:
            value = {"service": service, "username": username.strip(), "password": password}
            if server_url:
                value["server_url"] = validate_url(service, server_url)
            data = json.dumps(value).encode("utf-8", errors="strict")
            encrypted = crypt(data, True)
            temporary.write_bytes(encrypted)
            os.replace(temporary, destination)
        except OSError as exc:
            raise CalendarSyncError("credential_protection_failed") from exc
        finally:
            temporary.unlink(missing_ok=True)
        return account

    def load(self, account):
        try:
            value = json.loads(
                crypt(self.path(account).read_bytes(), False).decode("utf-8", errors="strict")
            )
            if account_key(value["service"], value["username"]) != account or not value["password"]:
                raise ValueError
            return value
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CalendarSyncError("login_required") from exc

    def remove(self, account):
        self.path(account).unlink(missing_ok=True)
