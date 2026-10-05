# -*- coding: utf-8 -*-
"""All bundled locales expose common sync flows with matching placeholders."""

import json
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "locales"


@pytest.mark.parametrize("path", sorted(LOCALES.glob("*.json")), ids=lambda path: path.stem)
def test_unified_sync_locale_contract(path):
    from scripts.i18n_sync import flatten_locale

    base = flatten_locale(
        json.loads((LOCALES / "ko.json").read_text(encoding="utf-8", errors="strict"))
    )
    target = flatten_locale(json.loads(path.read_text(encoding="utf-8", errors="strict")))
    keys = [key for key in base if key.startswith("sync_unified.") or key == "sync_ui.ics_fetch"]
    assert len(keys) >= 40
    for key in keys:
        assert key in target, key
        assert isinstance(target[key], str) and target[key].strip(), key
        assert re.findall(r"\{[^{}]+\}", base[key]) == re.findall(r"\{[^{}]+\}", target[key]), key
        assert "\ufffd" not in target[key], key
