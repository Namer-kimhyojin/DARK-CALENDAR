# -*- coding: utf-8 -*-
from unittest.mock import patch

from calendar_app.presentation.widgets.alarm_popup import AlarmPopupWindow, winsound


def test_alarm_uses_native_nonblocking_windows_notification_sound():
    with patch.object(winsound, "PlaySound") as play_sound:
        AlarmPopupWindow._play_notification_sound(object())

    play_sound.assert_called_once_with(
        "SystemNotification",
        winsound.SND_ALIAS | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
    )
