# -*- coding: utf-8 -*-
"""Keep per-dialog helper objects alive for the Qt dialog, not its Python wrapper.

Dialogs that Qt creates internally (``QColorDialog.getColor``, ``QMessageBox``
statics, ``QInputDialog.getText``) reach Python only through a temporary wrapper per
event. Attributes set on that wrapper, weak references to it, and Python children
that hang on it disappear when the event ends, which silently disabled the shared
header and shadow helpers. Helpers are therefore registered by the dialog's C++
address and released when the dialog itself is destroyed.
"""

from PyQt6 import sip
from PyQt6.QtWidgets import QDialog

from calendar_app.shared.qt_lifetime import call_when_destroyed

_HELPERS: dict[tuple[int, str], object] = {}
_WATCHED: set[int] = set()


def _address(dialog) -> int:
    return int(sip.unwrapinstance(dialog))


def dialog_helper(dialog, name: str):
    """Return the helper registered for ``dialog`` under ``name``, if any."""
    if dialog is None or sip.isdeleted(dialog):
        return None
    helper = _HELPERS.get((_address(dialog), name))
    if helper is not None and sip.isdeleted(helper):
        return None
    return helper


def keep_dialog_helper(dialog, name: str, helper):
    """Register ``helper`` until ``dialog`` is destroyed and return it."""
    address = _address(dialog)
    _HELPERS[(address, name)] = helper
    if address not in _WATCHED:
        _WATCHED.add(address)
        call_when_destroyed(dialog, _forget, address)
    return helper


def _forget(address: int) -> None:
    _WATCHED.discard(address)
    for key in [key for key in _HELPERS if key[0] == address]:
        _HELPERS.pop(key, None)


def owning_dialog(helper):
    """Resolve a helper's dialog through its Qt parent, which outlives any wrapper."""
    try:
        if helper is None or sip.isdeleted(helper):
            return None
        parent = helper.parent()
    except RuntimeError:
        return None
    if isinstance(parent, QDialog) and not sip.isdeleted(parent):
        return parent
    return None
