# -*- coding: utf-8 -*-

from calendar_app.infrastructure.runtime.keyboard_shortcuts import SHORTCUTS, get_key
from calendar_app.presentation.dialogs.dialog_router import _DIALOG_ROUTE_MAP


def test_print_dialog_route_is_registered():
    assert _DIALOG_ROUTE_MAP["calendar_print_dialog"] == "open_calendar_print_dialog"


def test_ctrl_p_opens_calendar_print_dialog():
    shortcut = next(item for item in SHORTCUTS if item["id"] == "calendar_print")

    assert get_key("calendar_print") == "Ctrl+P"
    assert shortcut["action"] == "open_calendar_print_dialog"
