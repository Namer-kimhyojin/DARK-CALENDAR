"""Helpers for building thin repository proxy modules."""

from __future__ import annotations

from collections.abc import Iterable
from types import ModuleType


def bind_proxy_exports(
    namespace: dict, source: ModuleType, names: Iterable[str]
) -> tuple[str, ...]:
    exported = tuple(names)
    for name in exported:
        namespace[name] = getattr(source, name)
    return exported
