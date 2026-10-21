# -*- coding: utf-8 -*-
"""Google OAuth credentials must never fall back to plaintext persistence."""

import os
from types import SimpleNamespace

import pytest

from calendar_app.infrastructure.calendar_sync import secret_store
from calendar_app.infrastructure.google_sync import token_store

TOKEN_TEXT = '{"token":"synthetic-access","refresh_token":"synthetic-refresh"}'
TOKEN_BYTES = TOKEN_TEXT.encode("utf-8", errors="strict")
PROTECTED = b"synthetic-protected-token"


@pytest.fixture
def protected_store(monkeypatch):
    def crypt(data, encrypt):
        if encrypt:
            assert data == TOKEN_BYTES
            return PROTECTED
        assert data == PROTECTED
        return TOKEN_BYTES

    monkeypatch.setattr(token_store, "_dpapi_crypt", crypt)


@pytest.mark.parametrize("existing", [None, b"DCTOK1previous-encrypted-token"])
def test_encryption_failure_never_writes_plaintext(monkeypatch, tmp_path, existing):
    path = tmp_path / "token.json"
    if existing is not None:
        path.write_bytes(existing)

    def fail(data, encrypt):
        assert encrypt
        raise OSError("synthetic encryption failure")

    monkeypatch.setattr(token_store, "_dpapi_crypt", fail)
    with pytest.raises(OSError, match="synthetic encryption failure"):
        token_store.save_token_json(TOKEN_TEXT, str(path))
    if existing is None:
        assert list(tmp_path.iterdir()) == []
    else:
        assert path.read_bytes() == existing
        assert list(tmp_path.iterdir()) == [path]


def test_plaintext_is_not_returned_when_migration_encryption_fails(monkeypatch, tmp_path):
    path = tmp_path / "token.json"
    path.write_bytes(TOKEN_BYTES)

    def fail(data, encrypt):
        assert encrypt
        raise OSError("synthetic migration failure")

    monkeypatch.setattr(token_store, "_dpapi_crypt", fail)
    assert token_store.load_token_json(str(path)) is None
    assert path.read_bytes() == TOKEN_BYTES
    assert list(tmp_path.iterdir()) == [path]


def test_plaintext_is_not_returned_when_migration_replace_fails(
    monkeypatch, tmp_path, protected_store
):
    path = tmp_path / "token.json"
    path.write_bytes(TOKEN_BYTES)

    def fail(*args):
        raise OSError("synthetic replacement failure")

    monkeypatch.setattr(token_store.os, "replace", fail)
    assert token_store.load_token_json(str(path)) is None
    assert path.read_bytes() == TOKEN_BYTES
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("legacy", [False, True])
def test_credentials_are_protected_before_being_returned(tmp_path, protected_store, legacy):
    path = tmp_path / "token.json"
    if legacy:
        path.write_bytes(TOKEN_BYTES)
    else:
        token_store.save_token_json(TOKEN_TEXT, str(path))
    assert token_store.load_token_json(str(path)) == TOKEN_TEXT
    assert path.read_bytes() == token_store._MAGIC + PROTECTED
    assert list(tmp_path.iterdir()) == [path]


def test_decryption_failure_does_not_modify_encrypted_file(monkeypatch, tmp_path):
    path = tmp_path / "token.json"
    encrypted = token_store._MAGIC + PROTECTED
    path.write_bytes(encrypted)

    def fail(data, encrypt):
        assert not encrypt
        raise OSError("synthetic decryption failure")

    monkeypatch.setattr(token_store, "_dpapi_crypt", fail)
    assert token_store.load_token_json(str(path)) is None
    assert path.read_bytes() == encrypted


@pytest.mark.parametrize("encrypted", [False, True])
def test_invalid_utf8_is_not_returned(monkeypatch, tmp_path, encrypted):
    path = tmp_path / "token.json"
    payload = token_store._MAGIC + PROTECTED if encrypted else b"\xff"
    path.write_bytes(payload)
    monkeypatch.setattr(token_store, "_dpapi_crypt", lambda *a, **k: b"\xff")
    assert token_store.load_token_json(str(path)) is None
    assert path.read_bytes() == payload


@pytest.mark.parametrize("existing", [None, TOKEN_BYTES, b"DCTOK1previous-encrypted-token"])
def test_dpapi_unavailable_fails_closed(monkeypatch, tmp_path, existing):
    path = tmp_path / "token.json"
    if existing is not None:
        path.write_bytes(existing)
    monkeypatch.setattr(secret_store, "os", SimpleNamespace(name="posix"))
    with pytest.raises(OSError, match="Windows credential protection unavailable"):
        token_store.save_token_json(TOKEN_TEXT, str(path))
    assert token_store.load_token_json(str(path)) is None
    if existing is None:
        assert list(tmp_path.iterdir()) == []
    else:
        assert path.read_bytes() == existing
        assert list(tmp_path.iterdir()) == [path]


@pytest.mark.skipif(os.name != "nt", reason="Windows CurrentUser DPAPI check")
@pytest.mark.parametrize("legacy", [False, True])
def test_real_windows_dpapi_round_trip(tmp_path, legacy):
    path = tmp_path / "token.json"
    text = '{"token":"synthetic-access","account":"테스트"}'
    raw = text.encode("utf-8", errors="strict")
    if legacy:
        path.write_bytes(raw)
    else:
        token_store.save_token_json(text, str(path))
    assert token_store.load_token_json(str(path)) == text
    encrypted = path.read_bytes()
    assert encrypted.startswith(token_store._MAGIC)
    assert raw not in encrypted
    assert b"synthetic-access" not in encrypted
    assert token_store.load_token_json(str(path)) == text
    assert path.read_bytes() == encrypted
