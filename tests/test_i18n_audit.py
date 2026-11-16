# -*- coding: utf-8 -*-
"""Regression checks for reproducible, read-only translation quality audits."""

import json
from pathlib import Path

import pytest
from scripts.audit_i18n import (
    BASELINE_RELATIVE,
    audit,
    check_calendar_names,
    check_dynamic_t_calls,
    check_english_words,
    check_foreign_script,
    check_hangul_source,
    check_length_ratio,
    check_markup_parity,
    check_mojibake,
    check_protected_terms,
    check_qt_formats,
    check_source_drift,
    check_stale_english,
    format_findings,
    format_signature,
    load_baseline,
    load_locales,
    new_findings,
    parse_sources,
    quality_findings,
    source_key_gaps,
    stale_baseline_entries,
    string_entries,
    untranslated_candidates,
    write_baseline,
)


@pytest.fixture(scope="module")
def bundled_audit():
    """The bundled audit takes several seconds; run it once for this module."""
    return audit()


def keys_of(findings):
    return {(item["locale"], item["key"]) for item in findings}


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


def test_bundled_translation_quality_contract(bundled_audit):
    result = bundled_audit
    assert result["errors"] == 0, json.dumps(
        {
            "source_missing": result["source_missing"],
            **{
                code: {
                    key: value
                    for key, value in report.items()
                    if key not in {"english_candidates", "keys"}
                }
                for code, report in result["locales"].items()
            },
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


def test_bundled_findings_do_not_grow_beyond_baseline(bundled_audit):
    """Ratchet: accepted findings live in the baseline; only new ones fail here.

    After a reviewed change, regenerate with
    ``python scripts/audit_i18n.py --update-baseline``.
    """
    baseline = load_baseline()
    fresh = new_findings(bundled_audit["findings"], baseline)
    assert not fresh, (
        f"{len(fresh)} new i18n audit findings (not in {BASELINE_RELATIVE.as_posix()}):\n"
        + format_findings(fresh)
    )
    stale = stale_baseline_entries(bundled_audit["findings"], baseline)
    assert not stale, (
        f"{len(stale)} fixed findings are still accepted in {BASELINE_RELATIVE.as_posix()}; "
        "run `python scripts/audit_i18n.py --update-baseline` so they cannot come back:\n"
        + "\n".join(stale[:200])
    )


def test_mojibake_and_stale_english_checks():
    locales = {
        "en": {
            "device": "Device",
            "settings": "Settings",
            "delete": "Delete",
            "url": "Open example.com/page?x=1",
            "menu": "Appearance...",
            "old": "UI Theme Settings...",
        },
        "de": {
            "device": "Ger?t",
            "settings": "Einstellungen?",
            "url": "Öffne example.com/page?x=1",
        },
        "es": {"delete": "¿Borrar?", "bad": "\ufffd"},
    }
    for code in ("fr", "it", "nl", "ru", "de"):
        locales.setdefault(code, {})["menu"] = "UI Theme Settings..."
    found = keys_of(check_mojibake(locales))
    assert {("de", "device"), ("de", "settings"), ("es", "bad")} <= found
    assert ("es", "delete") not in found
    assert ("de", "url") not in found
    stale = keys_of(check_stale_english(locales))
    assert {(code, "menu") for code in ("fr", "it", "nl", "ru", "de")} == stale


def test_english_function_words_respect_native_words():
    english = {
        "load": "Failed to load calendars",
        "ok": "This is fine",
        "none": "No tasks",
        "same": "Go to settings",
        "quoted": "Click Sign in",
        "alarm": "10 minutes before",
        "overnight": "If the end is before the start, the rule continues the next day.",
    }
    locales = {
        "en": english,
        "nl": {"load": "Mislukt to load calendars", "ok": "Dit is goed", "none": "Nee tasks"},
        "it": {"load": "Giorno of Anno", "same": "Go to settings", "alarm": "10 minuti before"},
        "es": {"none": "No hay tareas"},
        "de": {"none": "No Aufgaben", "quoted": 'Klicken Sie auf "Sign in with Google"'},
        "pt": {"overnight": "Se o término for antes do início, a regra segue no dia seguinte."},
    }
    found = {(item["locale"], item["key"]): item["detail"] for item in check_english_words(locales)}
    assert found[("nl", "load")] == "to"
    assert found[("it", "load")] == "of"
    assert found[("it", "alarm")] == "before"
    assert "Nee …" in found[("nl", "none")]
    assert "No…" in found[("de", "none")]
    for key in (
        ("nl", "ok"),
        ("es", "none"),
        ("it", "same"),
        ("de", "quoted"),
        ("pt", "overnight"),
    ):
        assert key not in found


def test_length_markup_and_qt_format_checks():
    english = {
        "warn": "This permanently deletes every event on the selected date.",
        "html": "Line<br><b>Bold</b><hr>End",
        "lines": "One\nTwo",
        "lock.date_format": "yyyy.MM.dd (ddd)",
        "widget.time_format": "Time format:",
    }
    locales = {
        "en": english,
        "de": {"warn": "Löschen?", "html": "Zeile<br><b>Fett</b><hr>Ende", "lines": "Eins\nZwei"},
        "ja": {"warn": "選択した日の予定をすべて削除します。", "html": "行<br><b>太字</b><h>終"},
        "es": {"lines": "Uno Dos"},
        "it": {"lock.date_format": "aaaa.MM.gg (gg)", "widget.time_format": "Formato:"},
        "fr": {"lock.date_format": "dd.MM.yyyy (ddd)"},
        "zh": {"lock.date_format": "yyyy年M月d日 (ddd)"},
        "id": {"lock.date_format": "yyyy.MM.dd (dd)"},
    }
    assert keys_of(check_length_ratio(locales)) == {("de", "warn")}
    # Japanese and Chinese are measured against the Korean source when it exists.
    two_sentences = "This permanently deletes every event on the selected date. Linked checklists are deleted too."
    dense = {
        "en": {"warn": two_sentences},
        "ko": {
            "warn": "선택한 날짜의 모든 일정을 영구 삭제합니다. 연결된 체크리스트도 함께 삭제됩니다."
        },
        "ja": {"warn": "選択した日の予定をすべて完全に削除します。"},
        "zh-CN": {"warn": "永久删除所选日期的所有日程。关联的清单也会被删除。"},
    }
    assert keys_of(check_length_ratio(dense)) == {("ja", "warn")}
    del dense["ko"]
    assert keys_of(check_length_ratio(dense)) == {("ja", "warn")}
    assert keys_of(check_markup_parity(locales)) == {("ja", "html"), ("es", "lines")}
    assert keys_of(check_qt_formats(locales)) == {
        ("it", "lock.date_format"),
        ("id", "lock.date_format"),
    }


def test_script_protected_term_and_weekday_checks():
    locales = {
        "en": {
            "running": "Air Calendar is already running.",
            "unlock": "Unlock (Ctrl+Shift+L)",
            "delete": "Delete (Ctrl+D)",
            "creds": "Choose credentials.json",
            "oauth": "Error: redirect_uri_mismatch",
            "clock": "Minimal HH:mm",
            "weekday.mon": "Mon",
            "weekday.sat": "Sat",
            "widget_studio.day_wed": "Wed",
            "app_name": "Air Calendar",
            "night": "Add clear_night.webp",
        },
        "de": {
            "running": "Läuft bereits.",
            "unlock": "Entsperren (Strg+Umschalt+L)",
            "clock": "Mindesthöhe: mm",
            "weekday.mon": "Mo",
        },
        "ar": {"delete": "حذف (Ctrl+د)", "night": "أضف وclear_night.webp"},
        "es": {
            "creds": "Elija credenciales.json",
            "oauth": "Error: redirect_uri_desajuste",
            "widget_studio.day_wed": "Casarse",
            "unlock": "Desbloquear (Ctrl+Mayús+L)",
        },
        "hi": {"unlock": "अनलॉक करें (Ctrl+Shift+L) سلام"},
        "ja": {
            "unlock": "ロック解除 (Ctrl+Shift+L)",
            "running": "Air Calendarはすでに実行中です。",
            "creds": "まずcredentials.jsonを選択",
        },
        "zh": {"unlock": "解锁 ロック (Ctrl+Shift+L)"},
        "th": {"unlock": "ปลดล็อก (Ctrl+คลิก Ctrl+Shift+L)"},
        "tr": {"weekday.sat": "Doygunluk", "weekday.mon": "Pzt"},
        "pt": {"app_name": "Air Calendario"},
        "it": {"app_name": "Air Calendar", "night": "Aggiungi clear_night.webp"},
    }
    assert keys_of(check_protected_terms(locales)) == {
        ("de", "running"),
        ("de", "clock"),
        ("ar", "delete"),
        ("ar", "night"),
        ("es", "creds"),
        ("es", "oauth"),
        ("pt", "app_name"),
    }
    assert keys_of(check_foreign_script(locales)) == {("hi", "unlock"), ("zh", "unlock")}
    assert keys_of(check_calendar_names(locales)) == {
        ("tr", "weekday.sat"),
        ("es", "widget_studio.day_wed"),
    }


def test_source_scans_skip_translated_defaults_logs_and_docstrings(tmp_path):
    source = tmp_path / "calendar_app"
    source.mkdir()
    lines = [
        '"""모듈 설명"""',
        "PREFIX = 'menu'",
        "KEY = 'menu.save'",
        "def build(label, logger, kind, name):",
        "    label.setText(t('menu.save', '저장'))",
        "    label.setToolTip('직접 쓴 문구')",
        "    label.setText(f'{name} 개')",
        "    logger.warning('로그 %s', name)",
        "    row('실행 모드')",
        "    re.compile('(오전|오후)')",
        "    t(KEY)",
        "    t(f'{PREFIX}.{kind}')",
        "    t(f'missing.{kind}')",
        "    t(kind)",
    ]
    (source / "view.py").write_text("\n".join(lines) + "\n", encoding="utf-8", errors="strict")
    trees, errors = parse_sources(source)
    assert not errors
    hangul = {(item["check"], item["key"]): item["detail"] for item in check_hangul_source(trees)}
    assert set(hangul) == {
        ("hangul_source", "view.py::직접 쓴 문구"),
        ("hangul_source", "view.py::개"),
        ("hangul_literal", "view.py::실행 모드"),
        ("hangul_literal", "view.py::(오전|오후)"),
    }
    assert hangul["hangul_source", "view.py::직접 쓴 문구"].endswith("setToolTip")
    assert hangul["hangul_source", "view.py::개"].endswith("setText")
    assert hangul["hangul_literal", "view.py::실행 모드"].endswith("row")
    findings, stats = check_dynamic_t_calls(trees, {"menu.save", "menu.open"})
    assert {(item["check"], item["key"]) for item in findings} == {
        ("t_key_missing", "view.py::f'missing.{kind}'"),
        ("t_nonliteral", "view.py::kind"),
    }
    assert stats == {"total": 4, "resolved": 1, "prefix": 2, "unresolved": 1}


def _write_locales(root, data):
    from scripts.i18n_sync import save_locale

    (root / "locales").mkdir(exist_ok=True)
    (root / "calendar_app").mkdir(exist_ok=True)
    for code, values in data.items():
        save_locale(root / "locales" / f"{code}.json", values)


def test_source_drift_survives_baseline_updates_until_translation_changes(tmp_path):
    korean = {"a": "가", "b": "나"}
    french = {"a": "Ouvrir un fichier de calendrier", "b": "Fermer"}
    _write_locales(
        tmp_path,
        {
            "ko": korean,
            "en": {"a": "Open file", "b": "Close"},
            "de": {"a": "Datei öffnen", "b": "Schließen"},
            "fr": {"a": "Ouvrir le fichier", "b": "Fermer"},
        },
    )
    write_baseline(tmp_path)
    english = {"a": "Open a calendar file", "b": "Close"}
    _write_locales(tmp_path, {"en": english, "fr": french})

    def drift():
        bundles, _ = load_locales(tmp_path)
        locales = {code: dict(string_entries(data)) for code, data in bundles.items()}
        return keys_of(check_source_drift(locales, load_baseline(tmp_path)["source_hashes"]))

    assert drift() == {("de", "a")}
    write_baseline(tmp_path)  # Accepting other findings keeps the drift visible.
    assert drift() == {("de", "a")}
    assert "de|a" in load_baseline(tmp_path)["findings"]["source_drift"]
    _write_locales(tmp_path, {"de": {"a": "Kalenderdatei öffnen", "b": "Schließen"}})
    assert drift() == set()
    write_baseline(tmp_path)
    assert "source_drift" not in load_baseline(tmp_path)["findings"]


def test_baseline_ratchet_reports_only_new_findings(tmp_path):
    english = {"warn": "Air Calendar deletes every event on the selected date."}
    korean = {"warn": "Air Calendar가 선택한 날짜의 일정을 모두 삭제합니다."}
    _write_locales(tmp_path, {"ko": korean, "en": english, "de": {"warn": "Löschen."}})
    baseline = write_baseline(tmp_path)
    assert baseline["counts"] == {"length_ratio": 1, "protected_terms": 1}
    bundles, _ = load_locales(tmp_path)
    findings, summary = quality_findings(bundles, tmp_path)
    assert new_findings(findings, load_baseline(tmp_path)) == []
    assert summary["pending_review"] == 0
    _write_locales(tmp_path, {"de": {"warn": "Ger?t löschen."}})
    bundles, _ = load_locales(tmp_path)
    findings, _ = quality_findings(bundles, tmp_path)
    fresh = new_findings(findings, load_baseline(tmp_path))
    assert [item["check"] for item in fresh] == ["mojibake"]
    assert "[mojibake] de warn: letter?letter: r?t" in format_findings(fresh)
    assert stale_baseline_entries(findings, load_baseline(tmp_path)) == []


def test_fixed_findings_must_leave_the_baseline(tmp_path):
    """A fixed defect stays reported until the baseline drops it, so it cannot return."""
    english = {"warn": "Delete the device."}
    _write_locales(tmp_path, {"ko": {"warn": "장치 삭제"}, "en": english, "de": {"warn": "Ger?t."}})
    write_baseline(tmp_path)
    _write_locales(tmp_path, {"de": {"warn": "Gerät."}})
    bundles, _ = load_locales(tmp_path)
    findings, _ = quality_findings(bundles, tmp_path)
    assert stale_baseline_entries(findings, load_baseline(tmp_path)) == ["mojibake: de|warn"]
    write_baseline(tmp_path)
    _write_locales(tmp_path, {"de": {"warn": "Ger?t."}})
    bundles, _ = load_locales(tmp_path)
    findings, _ = quality_findings(bundles, tmp_path)
    assert keys_of(new_findings(findings, load_baseline(tmp_path))) == {("de", "warn")}


def test_hangul_literals_outside_ui_calls_are_report_only(tmp_path):
    source = tmp_path / "calendar_app"
    source.mkdir()
    (source / "nlp.py").write_text(
        "import re\nPATTERN = re.compile('(?:에는|에도|까지)?')\n",
        encoding="utf-8",
        errors="strict",
    )
    trees, _ = parse_sources(source)
    findings = list(check_hangul_source(trees))
    assert {item["check"] for item in findings} == {"hangul_literal"}
    assert new_findings(findings, {}) == []
    assert stale_baseline_entries(findings, {}) == []


def test_pending_review_count_is_reported(tmp_path):
    _write_locales(tmp_path, {"ko": {"a": "가"}, "en": {"a": "Open"}, "de": {"a": "Open"}})
    pending = tmp_path / "scripts" / "i18n_pending_review.json"
    pending.parent.mkdir()
    pending.write_text(json.dumps({"de": {"a": "short_label"}}), encoding="utf-8", errors="strict")
    bundles, _ = load_locales(tmp_path)
    _, summary = quality_findings(bundles, tmp_path)
    assert summary["pending_review"] == 1
