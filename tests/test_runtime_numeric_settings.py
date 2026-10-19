# -*- coding: utf-8 -*-
"""Startup idle worker and task segments tolerate corrupt numeric preferences."""

from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QObject
import pytest

from calendar_app.infrastructure.runtime.idle_detector import AlarmWorker
from calendar_app.presentation.widgets.ui_components import DraggableTaskButton


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, 5),
        ("bad", 5),
        ([], 5),
        (float("inf"), 5),
        (-1, 1),
        (0, 1),
        (1441, 1440),
        ("10", 10),
    ],
)
def test_idle_worker_recovers_saved_interval(value, expected):
    parent = QObject()
    parent.settings = SimpleNamespace(value=lambda *args: value)
    worker = AlarmWorker(parent)
    assert worker.idle_timeout_ms == expected * 60_000


@pytest.mark.parametrize(
    "value,expected", [("bad", 5), (None, 5), ("10", 10), (-1, 1), (2000, 1440)]
)
def test_idle_worker_update_uses_numeric_minutes(value, expected):
    worker = AlarmWorker()
    worker.update_idle_timeout(value)
    assert worker.idle_timeout_ms == expected * 60_000


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, 9),
        ("bad", 9),
        ([], 9),
        (float("inf"), 9),
        (-100, 7),
        (9999, 255),
        ("12", 11),
    ],
)
def test_multiday_title_style_recovers_font_size(monkeypatch, value, expected):
    monkeypatch.setattr(
        "PyQt6.QtCore.QSettings", lambda *args: SimpleNamespace(value=lambda *args: value)
    )
    owner = SimpleNamespace(_watermark_title=True, title_label=Mock())
    DraggableTaskButton._apply_title_label_style(owner)
    assert f"font-size: {expected}pt;" in owner.title_label.setStyleSheet.call_args.args[0]
