# -*- coding: utf-8 -*-
from unittest.mock import Mock

import pytest
from requests.exceptions import ConnectionError

from calendar_app.infrastructure.outlook_sync.auth import MicrosoftAuth, OutlookError


def auth():
    value = MicrosoftAuth.__new__(MicrosoftAuth)
    value.app = Mock()
    value._save = Mock()
    return value


def test_silent_login_uses_selected_account_instead_of_first_cached_account():
    value = auth()
    first = {"home_account_id": "first"}
    selected = {"home_account_id": "chosen"}
    value.app.get_accounts.return_value = [first, selected]
    value.app.acquire_token_silent_with_error.return_value = {"access_token": "synthetic-token"}
    assert value.token(account_home_id="chosen") == "synthetic-token"
    assert value.app.acquire_token_silent_with_error.call_args.kwargs["account"] == selected


def test_missing_selected_account_never_uses_another_account():
    value = auth()
    value.app.get_accounts.return_value = [{"home_account_id": "other"}]
    with pytest.raises(OutlookError, match="login_required"):
        value.token(account_home_id="missing")
    value.app.acquire_token_silent_with_error.assert_not_called()


def test_login_button_always_opens_account_selector():
    value = auth()
    value.app.get_accounts.return_value = [
        {"home_account_id": "chosen", "local_account_id": "oid", "realm": "tenant"}
    ]
    value.app.acquire_token_interactive.return_value = {
        "access_token": "synthetic-token",
        "id_token_claims": {"oid": "oid", "tid": "tenant"},
    }
    assert value.token(interactive=True) == "synthetic-token"
    assert value.account_home_id == "chosen"
    value.app.acquire_token_silent_with_error.assert_not_called()
    assert value.app.acquire_token_interactive.call_args.kwargs["prompt"] == "select_account"


def test_invalid_client_id_stops_before_network_or_cache(tmp_path):
    with pytest.raises(OutlookError, match="client_id_required"):
        MicrosoftAuth("invalid-id", tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_authority_discovery_offline_reports_network_failure(monkeypatch, tmp_path):
    factory = Mock(side_effect=ConnectionError("synthetic transport error"))
    monkeypatch.setattr("msal.PublicClientApplication", factory)
    with pytest.raises(OutlookError, match="^network_unavailable$"):
        MicrosoftAuth("12345678-1234-1234-1234-123456789abc", tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("interactive", [False, True])
def test_token_transport_failure_reports_network_failure_without_saving(interactive):
    value = auth()
    value.app.get_accounts.return_value = [{"home_account_id": "chosen"}]
    method = (
        value.app.acquire_token_interactive
        if interactive
        else value.app.acquire_token_silent_with_error
    )
    method.side_effect = ConnectionError("synthetic transport error")

    with pytest.raises(OutlookError, match="^network_unavailable$"):
        value.token(interactive=interactive, account_home_id="chosen")

    value._save.assert_not_called()
    assert value.account_home_id == "chosen"


@pytest.mark.parametrize(
    ("oauth_error", "expected"),
    [
        ("temporarily_unavailable", "operation_failed"),
        ("server_error", "operation_failed"),
        ("invalid_grant", "login_required"),
    ],
)
def test_silent_refresh_separates_temporary_failure_from_reauthentication(oauth_error, expected):
    value = auth()
    value.app.get_accounts.return_value = [{"home_account_id": "chosen"}]
    value.app.acquire_token_silent_with_error.return_value = {"error": oauth_error}

    with pytest.raises(OutlookError, match=f"^{expected}$"):
        value.token(account_home_id="chosen")

    value.app.acquire_token_interactive.assert_not_called()
    assert value.account_home_id == "chosen"
