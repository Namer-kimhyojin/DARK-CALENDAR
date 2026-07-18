"""Compatibility adapter for search/query repository access."""

from importlib import import_module


def _legacy():
    return import_module("calendar_app.infrastructure.db.db_repository_unified")


def __getattr__(name):
    if name.startswith("_"):
        raise AttributeError(name)
    return getattr(_legacy(), name)


def __dir__():
    return sorted(globals())
