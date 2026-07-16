# -*- coding: utf-8 -*-
import json

from PyQt6.QtCore import QRect

from calendar_app.presentation.widgets.widget_mode_geometry import (
    clamp_rect,
    deserialize_geometry,
    restore_rect,
    serialize_geometry,
)


def test_geometry_round_trip_preserves_relative_screen_position():
    available = QRect(100, 50, 1200, 800)
    original = QRect(700, 350, 400, 300)

    payload = deserialize_geometry(serialize_geometry(original, available, "DISPLAY2"))

    assert payload is not None
    assert payload["screen"] == "DISPLAY2"
    assert restore_rect(payload, available) == original


def test_restore_clamps_oversized_widget_to_available_screen():
    payload = {
        "screen": "removed",
        "x_ratio": 1.0,
        "y_ratio": 1.0,
        "width": 4000,
        "height": 3000,
    }

    assert restore_rect(payload, QRect(0, 0, 1280, 720)) == QRect(0, 0, 1280, 720)


def test_invalid_or_old_geometry_payload_is_rejected():
    assert deserialize_geometry("not-json") is None
    assert deserialize_geometry(json.dumps({"version": 0})) is None


def test_offscreen_legacy_geometry_is_recovered():
    recovered = clamp_rect(QRect(9000, -4000, 420, 600), QRect(0, 0, 1920, 1080))

    assert recovered == QRect(1500, 0, 420, 600)
