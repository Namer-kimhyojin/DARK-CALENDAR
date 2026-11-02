# -*- coding: utf-8 -*-
"""Regression checks for reproducible, read-only translation quality audits."""

import json
from pathlib import Path

from scripts.audit_i18n import (
    audit,
    format_signature,
    source_key_gaps,
    untranslated_candidates,
)


def test_format_signature_includes_specs_and_nested_fields():
    assert format_signature("{value!r:>{width}}") == [
        ("value", ">{width}", "r"),
        ("width", "", None),
    ]
    assert format_signature("{{literal}}") == []


def test_candidate_detection_ignores_shared_brands_and_digits():
    target = {"title": "Workspaces", "brand": "Air Calendar", "digits": "1234", "short": "OK"}
    korean = {"title": "작업 공간", "brand": "Air Calendar", "digits": "1234", "short": "확인"}
    assert untranslated_candidates(target, target, korean) == ["title"]


def test_literal_source_audit_does_not_execute_source(tmp_path):
    path = tmp_path / "example.py"
    path.write_text(
        'raise RuntimeError("must not execute")\nt("known", "fallback")\n_t("missing", "fallback")\nt(f"dynamic.{kind}", "fallback")\n',
        encoding="utf-8",
        errors="strict",
    )
    gaps, errors = source_key_gaps(tmp_path, {"known"})
    assert gaps == {"missing": ["example.py:3"]}
    assert not errors


def test_audit_detects_duplicate_keys_and_invalid_formats_without_writes(tmp_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    (tmp_path / "calendar_app").mkdir()
    for code in ("ko", "en"):
        (locales / f"{code}.json").write_text(
            '{"value": "{count:02d}"}\n',
            encoding="utf-8",
            errors="strict",
        )
    (locales / "de.json").write_text(
        '{"value": "old", "value": "{count:03d}"}\n',
        encoding="utf-8",
        errors="strict",
    )
    before = {p.name: p.read_bytes() for p in locales.glob("*.json")}
    result = audit(tmp_path)
    assert result["locales"]["de"]["duplicate_keys"] == ["value"]
    assert result["locales"]["de"]["format_mismatch"] == ["value"]
    assert result["errors"] > 0
    assert before == {p.name: p.read_bytes() for p in locales.glob("*.json")}


def test_bundled_translation_quality_contract():
    result = audit()
    assert result["errors"] == 0, json.dumps(
        {
            code: {
                key: value
                for key, value in report.items()
                if key not in {"english_candidates", "keys"}
            }
            for code, report in result["locales"].items()
        },
        ensure_ascii=False,
    )
    assert len(result["locales"]) == 19
    assert not result["source_missing"]


def test_recent_workspace_ui_is_localized():
    from scripts.i18n_sync import flatten_locale, load_locale

    root = Path(__file__).resolve().parents[1] / "locales"
    english = flatten_locale(load_locale(root / "en.json"))
    keys = [
        key
        for key, value in english.items()
        if (
            key.startswith(("widget_studio.", "widget_hub."))
            or key == "widget_manager.snap_enabled"
        )
        and isinstance(value, str)
        and len(value) > 25
    ]
    # Technical terms and catalog brand names are deliberately outside this assertion.
    assert all(key in english for key in keys)
    assert len(keys) > 30
    for path in root.glob("*.json"):
        if path.stem in {"en", "ko"}:
            continue
        data = flatten_locale(load_locale(path))
        for key in keys:
            assert data[key] != english[key], (path.stem, key)
