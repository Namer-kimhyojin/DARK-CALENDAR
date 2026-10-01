# -*- coding: utf-8 -*-
"""Portable free configurations, with validation before atomic file writes."""

import json
import os
from pathlib import Path
import tempfile

from calendar_app.presentation.widgets.widget_free_layout import validate_free_layout

MAX_LAYOUT_FILE_BYTES = 256 * 1024


def load_layout_file(path):
    layout_path = Path(path)
    with layout_path.open("rb") as handle:
        payload = handle.read(MAX_LAYOUT_FILE_BYTES + 1)
    if len(payload) > MAX_LAYOUT_FILE_BYTES:
        raise ValueError("layout file is too large")
    return validate_free_layout(json.loads(payload.decode("utf-8", errors="replace")))


def save_layout_file(path, data):
    validated = validate_free_layout(data)
    target = Path(path)
    payload = json.dumps(validated, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            errors="strict",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(payload)
        os.replace(temporary_path, target)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return validated
