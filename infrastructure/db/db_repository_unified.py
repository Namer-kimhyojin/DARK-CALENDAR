"""Compatibility shim for the legacy infrastructure.db.db_repository_unified path.

The authoritative implementation lives in
`calendar_app.infrastructure.db.db_repository_unified`.
Keeping this module as a proxy prevents code drift between duplicated files.
"""

from __future__ import annotations

from calendar_app.infrastructure.db import db_repository_unified as _impl
from calendar_app.infrastructure.db.db_repository_unified import *  # noqa: F401,F403


def __getattr__(name: str):
    return getattr(_impl, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_impl)))
