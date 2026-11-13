# -*- coding: utf-8 -*-
"""Token editor row labels are looked up per key; the Korean tables stay the source.

The color and size/spacing rows used to show the Korean ``_TOKEN_LABELS`` and
``_METRIC_LABELS`` text in every language. Each row now reads
``dialog.token_editor.token.<key>`` or ``dialog.token_editor.metric.<key>`` with the
Korean label as the default, so the Korean UI is unchanged and other languages can
translate every row label.
"""

import re
from unittest.mock import patch

from PyQt6.QtCore import QCoreApplication, QEvent, QSettings
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QToolButton,
)
import pytest

from calendar_app.infrastructure.i18n import i18n
from calendar_app.presentation.dialogs import dialog_token_editor_dialog as module
from calendar_app.presentation.dialogs.dialog_styles import (
    DIALOG_METRIC_DEFAULTS,
    DIALOG_TOKEN_EDITABLE_KEYS,
)

_APP = QApplication.instance() or QApplication([])
HANGUL = re.compile(r"[ᄀ-ᇿ㄰-㆏가-힯]")
SECTIONS = (
    ("token", module._TOKEN_LABELS, module._token_label),
    ("metric", module._METRIC_LABELS, module._metric_label),
)


def _build_dialog(monkeypatch, tmp_path):
    # Model a real desktop, independently of the offscreen plugin's 800px monitor.
    monkeypatch.setattr(
        "calendar_app.presentation.dialogs.dialog_styles._available_dialog_bounds",
        lambda _dialog: (1888, 976),
    )
    settings = QSettings(str(tmp_path / "tokens.ini"), QSettings.Format.IniFormat)
    settings.setValue("font_size", 11)
    return module.DialogTokenEditorDialog(
        settings=settings,
        persist_on_apply=False,
        initial_color_overrides={},
        initial_metric_overrides={},
    )


def _dispose(dialog):
    dialog._preview_timer.stop()
    dialog.close()
    dialog.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _row_texts(dialog):
    """(key, row label, field accessible name, reset accessible name) for every row."""
    out = []
    for rows, field_type in ((dialog._color_rows, QLineEdit), (dialog._metric_rows, QSpinBox)):
        for key, row in rows.items():
            labels = row.findChildren(QLabel)
            assert len(labels) == 1, key
            field = dialog._color_edits.get(key) or dialog._metric_spins[key]
            assert isinstance(field, field_type)
            reset = [
                button
                for button in row.findChildren(QToolButton)
                if button.toolTip() == module.t("dialog.token_editor.reset_one", "기본값")
            ]
            assert len(reset) == 1, key
            out.append((key, labels[0].text(), field.accessibleName(), reset[0].accessibleName()))
    return out


@pytest.mark.parametrize(("section", "table", "helper"), SECTIONS, ids=["token", "metric"])
def test_every_label_entry_is_looked_up_through_t_with_its_own_key(section, table, helper):
    calls = []

    def recording_t(key, default=None, **kwargs):
        calls.append((key, default, kwargs))
        return default

    with patch.object(module, "t", recording_t):
        for key, korean in table.items():
            # The dict key is one JSON key-path segment: no dots, nothing to escape.
            assert re.fullmatch(r"[a-z0-9_]+", key), key
            assert helper(key) == korean
    assert calls == [
        (f"dialog.token_editor.{section}.{key}", korean, {}) for key, korean in table.items()
    ]


def test_a_key_without_a_table_entry_keeps_the_english_fallback():
    with patch.object(module, "t", side_effect=AssertionError("no key to look up")):
        assert module._token_label("future_token_bg") == "Future Token Bg"
        assert module._metric_label("future_metric_px") == "Future Metric Px"


def test_korean_dialog_shows_exactly_the_korean_table_labels(monkeypatch, tmp_path):
    assert i18n.lang == "ko"
    dialog = _build_dialog(monkeypatch, tmp_path)
    try:
        rows = _row_texts(dialog)
        assert {key for key, *_ in rows} == set(DIALOG_TOKEN_EDITABLE_KEYS) | set(
            DIALOG_METRIC_DEFAULTS
        )
        for key, label, field_name, reset_name in rows:
            korean = module._TOKEN_LABELS.get(key) or module._METRIC_LABELS[key]
            assert label == korean
            assert field_name == korean
            assert reset_name == korean + " · 기본값"
        # The Korean name stays searchable, as before.
        dialog.search_edit.setText("강조")
        assert not dialog._color_rows["accent"].isHidden()
        assert dialog._color_rows["surface_bg"].isHidden()
    finally:
        _dispose(dialog)


def test_preset_feedback_names_the_preset_as_the_combo_shows_it(monkeypatch, tmp_path):
    assert i18n.lang == "ko"
    dialog = _build_dialog(monkeypatch, tmp_path)
    try:
        seen = []
        for combo, apply, template in (
            (
                dialog.metric_preset_combo,
                dialog._apply_selected_metric_preset,
                module.t("dialog.token_editor.metric_preset_applied", "크기 프리셋 적용됨: {name}"),
            ),
            (
                dialog.color_preset_combo,
                dialog._apply_selected_color_preset,
                module.t("dialog.token_editor.preset_applied", "프리셋 적용됨: {name}"),
            ),
        ):
            for index in range(combo.count()):
                combo.setCurrentIndex(index)
                shown = combo.currentText()
                apply()
                assert dialog.feedback_label.text() == template.format(name=shown)
                seen.append(shown)
        # Before the fix these read the internal English keys ("Compact Dense" ...).
        assert {"촘촘하게", "여유 있게", "시스템 기본값"} <= set(seen)
    finally:
        _dispose(dialog)


def test_preview_primary_button_default_differs_from_the_default_button(monkeypatch, tmp_path):
    # ko.json used to give "Primary" the same text as "Default" ("기본"); the code
    # default now carries the distinct Korean name the locale gets in integration.
    def defaults_only(key, default=None, **kwargs):
        return default.format(**kwargs) if kwargs else default

    with patch.object(module, "t", defaults_only):
        dialog = _build_dialog(monkeypatch, tmp_path)
    try:
        buttons = dialog.findChildren(QPushButton)
        variants = {}
        for button in buttons:
            variant = button.property("previewVariant")
            if variant in ("primary", "secondary", "ghost"):
                variants[variant] = button.text()
        assert variants == {"primary": "주요", "secondary": "보조", "ghost": "고스트"}
        default_texts = [b.text() for b in buttons if b.text() == "기본"]
        assert default_texts, "the plain preview button keeps its name"
    finally:
        _dispose(dialog)


@pytest.fixture
def english():
    """Switch the UI to English in-process; supply row labels en.json does not have yet."""
    store = QSettings("kimhyojin", "Dark Calendar")  # the isolated store from conftest
    original = store.value("language")
    store.setValue("language", "en")
    i18n._load_translations()
    try:
        assert i18n.lang == "en"
        translations = dict(i18n.translations)
        expected = {}
        for section, table, _helper in SECTIONS:
            for key in table:
                dotted = f"dialog.token_editor.{section}.{key}"
                value = i18n._resolve_from(translations, dotted)
                if value is None:
                    value = translations[dotted] = module._fallback_token_label(key)
                expected[key] = value
        # A name that shares no word with its key proves search reads the shown label.
        translations["dialog.token_editor.token.surface_bg"] = "Canvas fill"
        expected["surface_bg"] = "Canvas fill"
        i18n.translations = translations
        yield expected
    finally:
        store.setValue("language", original if original is not None else "ko")
        i18n._load_translations()


def test_english_dialog_rows_show_no_hangul(english, monkeypatch, tmp_path):
    dialog = _build_dialog(monkeypatch, tmp_path)
    try:
        rows = _row_texts(dialog)
        assert rows
        for key, label, field_name, reset_name in rows:
            assert label == english[key]
            assert field_name == english[key]
            assert reset_name.startswith(english[key] + " · ")
            for text in (label, field_name, reset_name):
                assert not HANGUL.search(text), (key, text)
        dialog.search_edit.setText("canvas")
        assert not dialog._color_rows["surface_bg"].isHidden()
        assert dialog._color_rows["accent"].isHidden()
    finally:
        _dispose(dialog)
