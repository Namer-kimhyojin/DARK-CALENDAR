"""Legacy routine adapter for staged migration."""

from __future__ import annotations

from calendar_app.infrastructure.db import db_repository as _legacy
from calendar_app.infrastructure.db._adapter_proxy import bind_proxy_exports

__all__ = bind_proxy_exports(
    globals(),
    _legacy,
    [
        "get_routine_templates",
        "instantiate_routine",
    ],
)
