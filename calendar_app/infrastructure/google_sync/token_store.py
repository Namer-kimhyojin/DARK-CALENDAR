# -*- coding: utf-8 -*-
"""token_store.py — Google OAuth 토큰의 암호화 저장/로드.

Windows DPAPI(CryptProtectData)로 현재 사용자 계정에 바인딩해 암호화한다.
- 저장: 항상 암호화 (매직 헤더 ``DCTOK1`` + DPAPI blob)
- 로드: 기존 평문 token.json은 암호화 마이그레이션에 성공한 경우에만 반환
- DPAPI 사용 불가 또는 암호화 실패 시 저장을 중단하고 기존 파일을 보존
"""

from __future__ import annotations

import logging
import os
import tempfile

from calendar_app.app_paths import TOKEN_PATH
from calendar_app.infrastructure.calendar_sync.secret_store import crypt as _dpapi_crypt

logger = logging.getLogger(__name__)

_MAGIC = b"DCTOK1"


def save_token_json(token_json: str, token_path: str | None = None) -> None:
    """토큰 JSON 문자열을 암호화하여 저장한다. 실패 시 OSError 전파."""
    path = token_path or TOKEN_PATH
    raw = token_json.encode("utf-8", errors="strict")
    # Protect credentials before creating even a temporary file. Failure must
    # leave any previous token untouched, never downgrade it to plaintext.
    payload = _MAGIC + _dpapi_crypt(raw, encrypt=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=os.path.dirname(os.path.abspath(path)), delete=False
        ) as fh:
            temp_path = fh.name
            fh.write(payload)
        os.replace(temp_path, path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def load_token_json(token_path: str | None = None) -> str | None:
    """토큰 JSON 문자열을 로드한다. 파일 없음/해독·마이그레이션 실패 시 None.

    기존 평문 token.json은 암호화 형식으로 재저장한 뒤에만 반환한다.
    """
    path = token_path or TOKEN_PATH
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as fh:
            payload = fh.read()
    except OSError:
        logger.warning("token read failed")
        return None

    if payload.startswith(_MAGIC):
        try:
            return _dpapi_crypt(payload[len(_MAGIC) :], encrypt=False).decode(
                "utf-8", errors="strict"
            )
        except (OSError, UnicodeDecodeError):
            logger.warning("token decryption failed")
            return None

    # 레거시 평문 token.json → 암호화로 마이그레이션
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        logger.warning("token file is neither encrypted nor valid UTF-8 JSON")
        return None
    try:
        save_token_json(text, path)
    except OSError:
        logger.warning("legacy token protection failed; re-authentication required")
        return None
    logger.info("legacy plaintext token migrated to encrypted storage")
    return text
