# -*- coding: utf-8 -*-
"""Salted scrypt hashes for the away-lock password stored in QSettings."""

import hashlib
import hmac
import os

_PREFIX = "scrypt"
_N, _R, _P = 2**14, 8, 1


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8", errors="strict"), salt=salt, n=n, r=r, p=p, dklen=32
    )


def is_password_hash(stored) -> bool:
    return str(stored or "").startswith(_PREFIX + "$")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = _derive(str(password), salt, _N, _R, _P)
    return f"{_PREFIX}${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored) -> bool:
    """Check a password against a stored hash, or a legacy plain-text value."""
    stored = str(stored or "")
    if not stored:
        return False
    if not is_password_hash(stored):
        return hmac.compare_digest(
            str(password).encode("utf-8", errors="strict"),
            stored.encode("utf-8", errors="strict"),
        )
    try:
        _, n, r, p, salt_hex, digest_hex = stored.split("$")
        expected = bytes.fromhex(digest_hex)
        digest = _derive(str(password), bytes.fromhex(salt_hex), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)
