# -*- coding: utf-8 -*-
"""token_store.py — Google OAuth 토큰의 암호화 저장/로드.

Windows DPAPI(CryptProtectData)로 현재 사용자 계정에 바인딩해 암호화한다.
- 저장: 항상 암호화 (매직 헤더 ``DCTOK1`` + DPAPI blob)
- 로드: 암호화 파일 우선, 기존 평문 token.json은 읽은 뒤 즉시 암호화로 마이그레이션
- DPAPI 사용 불가 환경(비 Windows 테스트 등)에서는 평문으로 폴백
"""

from __future__ import annotations

import contextlib
import logging
import os

from calendar_app.app_paths import TOKEN_PATH

logger = logging.getLogger(__name__)

_MAGIC = b"DCTOK1"


def _dpapi_available() -> bool:
    return os.name == "nt"


def _dpapi_crypt(data: bytes, encrypt: bool) -> bytes:
    import ctypes
    import ctypes.wintypes as wt

    class _DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    buf = ctypes.create_string_buffer(data, len(data))
    in_blob = _DataBlob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    out_blob = _DataBlob()
    fn = (
        ctypes.windll.crypt32.CryptProtectData
        if encrypt
        else ctypes.windll.crypt32.CryptUnprotectData
    )
    if not fn(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
        raise OSError(f"DPAPI {'encrypt' if encrypt else 'decrypt'} failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def save_token_json(token_json: str, token_path: str | None = None) -> None:
    """토큰 JSON 문자열을 암호화하여 저장한다. 실패 시 OSError 전파."""
    path = token_path or TOKEN_PATH
    raw = token_json.encode("utf-8", errors="strict")
    if _dpapi_available():
        try:
            payload = _MAGIC + _dpapi_crypt(raw, encrypt=True)
        except OSError:
            logger.warning("DPAPI encryption unavailable; storing token unencrypted")
            payload = raw
    else:
        payload = raw
    with open(path, "wb") as fh:
        fh.write(payload)


def load_token_json(token_path: str | None = None) -> str | None:
    """토큰 JSON 문자열을 로드한다. 파일 없음/해독 실패 시 None.

    기존 평문 token.json을 발견하면 읽은 뒤 암호화 형식으로 재저장한다.
    """
    path = token_path or TOKEN_PATH
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as fh:
            payload = fh.read()
    except OSError as exc:
        logger.warning("token read failed: %s", exc)
        return None

    if payload.startswith(_MAGIC):
        if not _dpapi_available():
            logger.warning("encrypted token found but DPAPI unavailable")
            return None
        try:
            return _dpapi_crypt(payload[len(_MAGIC) :], encrypt=False).decode(
                "utf-8", errors="strict"
            )
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("token decryption failed: %s", exc)
            return None

    # 레거시 평문 token.json → 암호화로 마이그레이션
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        logger.warning("token file is neither encrypted nor valid UTF-8 JSON")
        return None
    if _dpapi_available():
        with contextlib.suppress(OSError):
            save_token_json(text, path)
            logger.info("legacy plaintext token migrated to encrypted storage")
    return text
