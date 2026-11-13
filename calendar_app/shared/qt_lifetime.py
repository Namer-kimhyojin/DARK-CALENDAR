# -*- coding: utf-8 -*-
"""Run Python code when a Qt object is destroyed, also when the cyclic GC frees it."""

_HOOKS: dict[int, "_DestroyedHook"] = {}


class _DestroyedHook:
    """One pending ``destroyed`` callback, kept in ``_HOOKS`` until it runs.

    A lambda or partial connected straight to ``destroyed`` is reachable only through
    the object that emits it. When the cyclic GC freed that object, PyQt either
    dropped the slot or called it after the GC had cleared it (defaults, closure,
    globals); the call then raised inside Qt and PyQt ended the process with qFatal
    (0xC0000409, no traceback). PyQt holds a bound method's instance weakly, so an
    instance kept here is neither dropped nor cleared.
    """

    def __init__(self, callback, args):
        self.callback = callback
        self.args = args

    def run(self, *_signal_args) -> None:
        _HOOKS.pop(id(self), None)
        self.callback(*self.args)


def call_when_destroyed(obj, callback, *args) -> None:
    """Call ``callback(*args)`` once when the Qt object behind ``obj`` is destroyed.

    ``callback`` and ``args`` stay referenced until then, so they must not refer to
    ``obj`` itself; pass a weak reference instead. Register the hook in the thread
    the object will be destroyed in: after ``moveToThread`` the call is dropped.
    """
    hook = _DestroyedHook(callback, args)
    _HOOKS[id(hook)] = hook
    obj.destroyed.connect(hook.run)
