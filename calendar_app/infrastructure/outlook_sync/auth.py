# -*- coding: utf-8 -*-
"""Public-client OAuth with an encrypted, per-user MSAL cache."""

import os
from pathlib import Path
import uuid

from calendar_app.app_paths import get_app_data_dir
from calendar_app.application.calendar_sync_contract import CalendarSyncError
from calendar_app.infrastructure.calendar_sync.secret_store import crypt as _dpapi_crypt

SCOPES = ["Calendars.ReadWrite", "User.Read"]


class OutlookError(CalendarSyncError):
    """A safe diagnostic code, never containing tokens or server responses."""


class MicrosoftAuth:
    def __init__(self, client_id: str, cache_dir: Path | None = None):
        try:
            self.client_id = str(uuid.UUID(client_id.strip()))
        except (ValueError, AttributeError) as exc:
            raise OutlookError("client_id_required") from exc
        import msal

        self.cache_path = (cache_dir or get_app_data_dir()) / f"outlook-{self.client_id}.cache"
        self.cache = msal.SerializableTokenCache()
        if self.cache_path.exists():
            try:
                self.cache.deserialize(
                    _dpapi_crypt(self.cache_path.read_bytes(), encrypt=False).decode(
                        "utf-8", errors="strict"
                    )
                )
            except (OSError, ValueError, UnicodeError) as exc:
                raise OutlookError("cache_unavailable") from exc
        self.app = msal.PublicClientApplication(
            self.client_id,
            authority="https://login.microsoftonline.com/common",
            token_cache=self.cache,
        )

    def _save(self):
        if self.cache.has_state_changed:
            encrypted = _dpapi_crypt(
                self.cache.serialize().encode("utf-8", errors="strict"), encrypt=True
            )
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.cache_path.with_suffix(".tmp")
            temporary.write_bytes(encrypted)
            os.replace(temporary, self.cache_path)

    def token(self, interactive: bool = False, account_home_id: str = "") -> str:
        accounts = self.app.get_accounts()
        self.account_home_id = account_home_id
        if interactive:
            result = self.app.acquire_token_interactive(
                scopes=SCOPES, timeout=120, prompt="select_account"
            )
        else:
            selected = next((a for a in accounts if a["home_account_id"] == account_home_id), None)
            if selected is None and len(accounts) == 1 and not account_home_id:
                selected = accounts[0]
            result = self.app.acquire_token_silent(SCOPES, account=selected) if selected else None
        self._save()
        if not result or "access_token" not in result:
            raise OutlookError("login_required")
        if interactive:
            claims = result.get("id_token_claims") or {}
            accounts = self.app.get_accounts()
            selected = next(
                (
                    a
                    for a in accounts
                    if a.get("local_account_id") == claims.get("oid")
                    and a.get("realm") == claims.get("tid")
                ),
                None,
            )
            if selected is None:
                selected = next(
                    (
                        a
                        for a in accounts
                        if a.get("username")
                        and a.get("username") == claims.get("preferred_username")
                    ),
                    None,
                )
            if selected is None and len(accounts) == 1:
                selected = accounts[0]
            if selected is None:
                raise OutlookError("account_selection_required")
            self.account_home_id = selected["home_account_id"]
        return result["access_token"]

    def disconnect(self):
        for account in self.app.get_accounts():
            self.app.remove_account(account)
        self._save()
