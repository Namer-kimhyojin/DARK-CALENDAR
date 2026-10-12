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
    keys = [
        key
        for key in base
        if key.startswith(
            (
                "sync_unified.",
                "sync_recovery.",
                "sync_google.",
                "sync_disclosures.",
                "provider_ui.",
                "gcal_ux.",
            )
        )
        or key
        in {
            "sync_ui.ics_fetch",
            "sync_ui.partial",
            "sync_ui.calendar_timezone",
            "sync_ui.remote_event",
            "sync_ui.account_mismatch",
            "sync_ui.account_unverified",
        }
    ]
    assert len(keys) >= 40
    for key in keys:
        assert key in target, key
        assert isinstance(target[key], str) and target[key].strip(), key
        assert re.findall(r"\{[^{}]+\}", base[key]) == re.findall(r"\{[^{}]+\}", target[key]), key
        assert "\ufffd" not in target[key], key


@pytest.mark.parametrize("path", sorted(LOCALES.glob("*.json")), ids=lambda path: path.stem)
def test_main_calendar_and_google_settings_locale_contract(path):
    from scripts.i18n_sync import flatten_locale

    base = flatten_locale(
        json.loads((LOCALES / "ko.json").read_text(encoding="utf-8", errors="strict"))
    )
    target = flatten_locale(json.loads(path.read_text(encoding="utf-8", errors="strict")))
    keys = [
        key
        for key in base
        if key.startswith(
            (
                "calendar_controls.",
                "calendar_list_default.",
                "calendar_management_tabs.",
                "gcal_focus.",
            )
        )
        or key
        in {
            "dialog.task.calendar_paused",
            "dialog.task.calendar_paused_owner_hint",
            "dialog.task.calendar_import_paused",
            "dialog.task.calendar_import_paused_owner_hint",
        }
    ]
    assert len(keys) >= 45
    for key in keys:
        assert key in target, key
        assert isinstance(target[key], str) and target[key].strip(), key
        assert re.findall(r"\{[^{}]+\}", base[key]) == re.findall(r"\{[^{}]+\}", target[key]), key
        assert "\ufffd" not in target[key], key
