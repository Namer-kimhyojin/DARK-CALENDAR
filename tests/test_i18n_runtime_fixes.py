# -*- coding: utf-8 -*-
"""Runtime i18n fixes: Qt button catalogs, first-run language, QLocale region,
language menu check marks and user locale overrides."""

import json
import os
from pathlib import Path
from unittest.mock import patch

from PyQt6 import sip
from PyQt6.QtCore import QLibraryInfo, QLocale, QSettings, QTranslator
from PyQt6.QtWidgets import QApplication, QDialogButtonBox, QMessageBox, QVBoxLayout, QWidget
import pytest

from calendar_app.infrastructure import i18n as i18n_module
from calendar_app.infrastructure.i18n import (
    _QT_CATALOG_CODES,
    _SOURCE_LANGUAGE,
    I18nManager,
    _read_locale_dict,
    _with_mnemonic,
    ensure_user_locale_file,
    get_user_locales_dir,
    i18n,
    list_available_locale_codes,
    remove_user_locale_override,
)

ROOT = Path(__file__).resolve().parents[1]
QT_TRANSLATIONS = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
BUTTONS = (
    ("Ok", "OK", "dialog.common.ok"),
    ("Save", "Save", "common.save"),
    ("Yes", "&Yes", "dialog.common.yes"),
    ("No", "&No", "dialog.common.no"),
    ("Cancel", "Cancel", "common.cancel"),
    ("Apply", "Apply", "common.apply"),
    ("Close", "Close", "common.close"),
)


# One QApplication for the rest of the session: destroying it would also delete the
# translators the global manager installs on it in the teardown below.
_APPS = []


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    _APPS.append(application)
    yield application
    i18n.apply_application_locale()


@pytest.fixture
def no_app_translators(app):
    """Detach the global manager's translators; each test reinstalls them at the end."""
    _release(app, i18n)
    yield app


def _manager(code):
    manager = object.__new__(I18nManager)
    manager.lang = code
    manager.translations = _read_locale_dict(ROOT / "locales" / f"{code}.json", code)
    manager.bundled_translations = {}
    manager.fallback_translations = _read_locale_dict(ROOT / "locales" / "en.json", "en")
    return manager


def _release(app, manager):
    for name in ("_button_translator", "_qt_translator"):
        translator = getattr(manager, name, None)
        if translator is not None and not sip.isdeleted(translator):
            app.removeTranslator(translator)
            translator.deleteLater()
        setattr(manager, name, None)


def _button_texts():
    box = QMessageBox()
    buttons = QDialogButtonBox()
    texts = {}
    for name, _source, _key in BUTTONS:
        box.addButton(getattr(QMessageBox.StandardButton, name))
        buttons.addButton(getattr(QDialogButtonBox.StandardButton, name))
        texts[name] = box.button(getattr(QMessageBox.StandardButton, name)).text()
        # Both widgets read the same QPlatformTheme strings.
        assert buttons.button(getattr(QDialogButtonBox.StandardButton, name)).text() == texts[name]
    box.deleteLater()
    buttons.deleteLater()
    return texts


def _qt_catalog(code):
    catalog = QTranslator()
    return (
        catalog
        if catalog.load(f"qtbase_{_QT_CATALOG_CODES.get(code, code)}", QT_TRANSLATIONS)
        else None
    )


# --- H1: Qt's catalog wins and mnemonics survive (Korean source words stay) ---------


@pytest.mark.parametrize(
    "code", ["zh-CN", "zh-TW", "es", "fr", "ja", "de", "ko", "ru", "hi", "id", "th", "vi"]
)
def test_standard_buttons_prefer_qt_catalog_and_keep_mnemonics(no_app_translators, code):
    app = no_app_translators
    manager = _manager(code)
    manager.apply_application_locale()
    try:
        texts = _button_texts()
        catalog = _qt_catalog(code)
        if code == _SOURCE_LANGUAGE:
            # The app's own Korean words, exactly as before: no catalog word, no "&".
            for name, _source, key in BUTTONS:
                assert texts[name] == manager.get(key)
        elif code in {"hi", "id", "th", "vi"}:
            assert catalog is None, f"Qt now ships qtbase_{code}; drop it from this branch"
            for name, source, key in BUTTONS:
                assert texts[name] == _with_mnemonic(manager.get(key), source)
            for name in ("Yes", "No"):
                assert texts[name].count("&") == 1, texts[name]
        else:
            assert catalog is not None
            for name, source, _key in BUTTONS:
                assert texts[name] == catalog.translate("QPlatformTheme", source)
    finally:
        _release(app, manager)
        i18n.apply_application_locale()


def test_known_qt_words_replace_the_machine_translated_values(no_app_translators):
    app = no_app_translators
    expected = {
        "zh-CN": {"Ok": "确定", "Save": "保存", "Yes": "是(&Y)", "No": "否(&N)"},
        "zh-TW": {"Ok": "確定", "Save": "儲存", "Yes": "是(&Y)", "No": "否(&N)"},
        "es": {"Ok": "Aceptar", "Yes": "&Sí"},
        "fr": {"Ok": "OK", "Save": "Enregistrer"},
        "ja": {"Ok": "OK", "Yes": "はい(&Y)", "No": "いいえ(&N)"},
        "ko": {"Ok": "확인", "Yes": "예", "No": "아니오"},
    }
    for code, words in expected.items():
        manager = _manager(code)
        manager.apply_application_locale()
        try:
            texts = _button_texts()
            assert {name: texts[name] for name in words} == words, code
        finally:
            _release(app, manager)
    i18n.apply_application_locale()


def test_korean_buttons_keep_todays_words_over_qt_catalog(no_app_translators):
    app = no_app_translators
    manager = _manager("ko")
    manager.apply_application_locale()
    try:
        assert _qt_catalog("ko").translate("QPlatformTheme", "&No") == "아니요(&N)"
        assert _button_texts() == {
            "Ok": "확인",
            "Save": "저장",
            "Yes": "예",
            "No": "아니오",
            "Cancel": "취소",
            "Apply": "적용",
            "Close": "닫기",
        }
    finally:
        _release(app, manager)
        i18n.apply_application_locale()


def test_reapplying_after_the_application_is_gone_does_not_raise(no_app_translators):
    app = no_app_translators
    manager = _manager("hi")
    manager.apply_application_locale()
    stale = manager._button_translator
    try:
        # What QApplication's destructor does to its child translators.
        app.removeTranslator(stale)
        sip.delete(stale)
        manager.apply_application_locale()
        assert manager._button_translator is not None
        assert manager._button_translator is not stale
    finally:
        _release(app, manager)
        i18n.apply_application_locale()


def test_reapplying_a_language_does_not_stack_translators(no_app_translators):
    app = no_app_translators
    manager = _manager("hi")
    manager.apply_application_locale()
    try:
        assert _button_texts()["Yes"] != "&Yes"
        manager.lang = "en"
        manager.translations = manager.fallback_translations
        manager.apply_application_locale()
        assert manager._button_translator is None
        texts = _button_texts()
        assert texts["Yes"] == "&Yes"
        assert texts["Ok"] == "OK"
    finally:
        _release(app, manager)
        i18n.apply_application_locale()


@pytest.mark.parametrize(
    "text,source,expected",
    [
        ("Ya", "&Yes", "&Ya"),
        ("Có", "&Yes", "&Có"),
        ("Tidak", "&No", "&Tidak"),
        ("Không", "&No", "Khô&ng"),
        ("हाँ", "&Yes", "हाँ (&Y)"),
        ("ไม่", "&No", "ไม่ (&N)"),
        ("ตกลง", "OK", "ตกลง"),
        ("Save && Close", "Save", "Save && Close"),
    ],
)
def test_mnemonic_follows_script(text, source, expected):
    assert _with_mnemonic(text, source) == expected


# --- H2 support: the weekday alias is gone -------------------------------------------


def test_weekday_keys_no_longer_alias_calendar_weekdays():
    manager = object.__new__(I18nManager)
    manager.translations = {"calendar": {"weekdays": ["X", "X", "X", "X", "X", "X", "X"]}}
    manager.bundled_translations = {}
    manager.fallback_translations = {}
    assert not hasattr(I18nManager, "_weekday_from_calendar")
    assert manager.get("weekday.mon", "월") == "월"


# --- L1: first run follows the display language --------------------------------------


class _FakeSystemLocale:
    def __init__(self, ui_languages, name):
        self._ui_languages = list(ui_languages)
        self._name = name

    def uiLanguages(self):  # noqa: N802 - Qt API
        return list(self._ui_languages)

    def name(self):
        return self._name


AVAILABLE = {p.stem for p in (ROOT / "locales").glob("*.json")}


@pytest.mark.parametrize(
    "ui_languages,name,expected",
    [
        (["ko-Kore-KR", "ko-KR", "ko"], "en_US", "ko"),
        (["zh-Hant-TW", "zh-TW"], "en_US", "zh-TW"),
        (["zh-Hans-CN"], "zh_TW", "zh-CN"),
        (["pt-BR"], "en_US", "pt"),
        (["en-US", "en"], "ko_KR", "en"),
        (["sv-SE"], "ko_KR", "ko"),
        ([], "de_DE", "de"),
        (["sv-SE"], "sv_SE", None),
    ],
)
def test_first_run_language_prefers_display_languages(ui_languages, name, expected):
    fake = _FakeSystemLocale(ui_languages, name)
    assert I18nManager.detect_system_language(AVAILABLE, fake) == expected


def test_first_run_saves_display_language_not_regional_format(tmp_path):
    settings = QSettings(str(tmp_path / "app.ini"), QSettings.Format.IniFormat)
    manager = object.__new__(I18nManager)
    with (
        patch("calendar_app.infrastructure.i18n.QSettings", return_value=settings),
        patch(
            "calendar_app.infrastructure.i18n._system_locale",
            return_value=_FakeSystemLocale(["ko-KR", "ko"], "en_US"),
        ),
        patch.object(I18nManager, "apply_application_locale"),
    ):
        manager._load_translations()
    assert manager.lang == "ko"
    assert settings.value("language") == "ko"


# --- L3: QLocale keeps the user's region when the language matches -------------------


@pytest.mark.parametrize(
    "lang,system,expected",
    [
        ("en", "en_GB", "en_GB"),
        ("en", "en_AU", "en_AU"),
        ("en", "en_IN", "en_IN"),
        ("pt", "pt_PT", "pt_PT"),
        ("ar", "ar_MA", "ar_MA"),
        ("zh-TW", "zh_HK", "zh_HK"),
        ("zh-TW", "zh_CN", "zh_TW"),
        ("zh-CN", "zh_TW", "zh_CN"),
        ("en", "ko_KR", "en_US"),
        ("ko", "en_GB", "ko_KR"),
        ("pt", "en_US", "pt_BR"),
    ],
)
def test_qt_locale_uses_system_region_for_the_same_language(lang, system, expected):
    original = QLocale()
    try:
        I18nManager._apply_qt_locale(lang, system_locale=QLocale(system))
        assert QLocale().name() == expected
        if lang == "zh-TW":
            assert QLocale().script() == QLocale.Script.TraditionalHanScript
    finally:
        QLocale.setDefault(original)
        i18n.apply_application_locale()


def test_region_specific_formats_survive():
    original = QLocale()
    try:
        I18nManager._apply_qt_locale("en", system_locale=QLocale("en_GB"))
        assert QLocale().dateFormat(QLocale.FormatType.ShortFormat) == "dd/MM/yyyy"
        I18nManager._apply_qt_locale("ar", system_locale=QLocale("ar_MA"))
        assert QLocale().toString(5) == "5"
        I18nManager._apply_qt_locale("ar", system_locale=QLocale("ko_KR"))
        assert QLocale().toString(5) == "٥"
    finally:
        QLocale.setDefault(original)
        i18n.apply_application_locale()


# --- L6: exclusive language menu ------------------------------------------------------


class _Settings:
    def __init__(self, language):
        self.values = {"language": language}

    def value(self, key, default=None, type=None):  # noqa: A002 - QSettings API
        return self.values.get(key, default)

    def setValue(self, key, value):  # noqa: N802 - QSettings API
        self.values[key] = value

    def sync(self):
        pass


class _MenuHost(QWidget):
    _NO_OP_SLOTS = (
        "open_label_settings_dialog",
        "open_away_settings_dialog",
        "open_daily_summary_dialog",
        "open_calendar_management",
        "open_calendar_sync_hub",
        "open_calendar_sync_issues",
        "open_current_locale_file",
        "open_locale_override_folder",
        "request_app_exit",
        "reset_current_locale_override",
        "show_shortcut_guide",
        "sync_calendars",
        "toggle_autostart",
        "validate_current_locale_override",
    )

    def __init__(self, language):
        super().__init__()
        self.settings = _Settings(language)
        self.requested = []
        for name in self._NO_OP_SLOTS:
            setattr(self, name, lambda *args: None)
        self.add_menu_btn = QWidget()

    def set_language(self, lang_code):
        self.requested.append(lang_code)


def _language_actions(host):
    return {action.data(): action for action in host.lang_action_group.actions()}


def test_clicking_the_current_language_keeps_its_check_mark(app):
    from calendar_app.presentation.main_window.top_menus.system_menu import build_system_menu

    host = _MenuHost("ja")
    build_system_menu(host, QVBoxLayout(), "")
    actions = _language_actions(host)
    assert host.lang_action_group.isExclusive()
    assert [code for code, action in actions.items() if action.isChecked()] == ["ja"]
    assert "zh" not in actions

    actions["ja"].trigger()
    assert actions["ja"].isChecked()
    assert host.requested == ["ja"]

    actions["en"].trigger()
    assert actions["en"].isChecked() and not actions["ja"].isChecked()
    assert host.requested == ["ja", "en"]
    host.deleteLater()


def test_cancelled_language_restart_moves_check_mark_back(app):
    from calendar_app.presentation.main_window.action_handlers import ActionHandlersMixin
    from calendar_app.presentation.main_window.top_menus.system_menu import build_system_menu

    host = _MenuHost("ja")
    build_system_menu(host, QVBoxLayout(), "")
    actions = _language_actions(host)
    actions["en"].setChecked(True)  # what the menu click already did
    with (
        patch("calendar_app.presentation.main_window.action_handlers.QMessageBox.information"),
        patch("calendar_app.presentation.main_window.action_handlers.QMessageBox.warning"),
        patch(
            "calendar_app.presentation.main_window.window_restore_helpers.flush_window_layout",
            return_value=False,
        ),
    ):
        ActionHandlersMixin.set_language(host, "en")
    assert host.settings.values["language"] == "ja"
    assert actions["ja"].isChecked() and not actions["en"].isChecked()
    host.deleteLater()


# --- L2: seeded user overrides still receive bundled fixes ---------------------------


def _write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8", errors="strict")


def _user_dir(user):
    def get_user_locales_dir(create=False):
        if create:
            user.mkdir(parents=True, exist_ok=True)
        return user

    return get_user_locales_dir


def test_user_locale_dir_is_isolated_in_tests():
    isolated = Path(os.environ["LOCALAPPDATA"]).resolve()
    assert get_user_locales_dir().resolve().is_relative_to(isolated)


def test_seeded_override_keeps_edits_and_receives_later_bundle_fixes(tmp_path):
    bundle, user = tmp_path / "bundles", tmp_path / "user"
    bundle.mkdir()
    _write_json(bundle / "en.json", {"meta": {"language_name": "English"}, "a": "A"})
    _write_json(
        bundle / "ja.json",
        {
            "meta": {"language_name": "日本語"},
            "a": "古いA",
            "b": "古いB",
            "nested": {"c": "古いC", "keep": "同じ"},
            "list": ["月", "火"],
        },
    )
    settings = QSettings(str(tmp_path / "app.ini"), QSettings.Format.IniFormat)
    settings.setValue("language", "ja")
    with (
        patch("calendar_app.infrastructure.i18n._BUNDLED_LOCALES_DIR", bundle),
        patch("calendar_app.infrastructure.i18n.get_user_locales_dir", side_effect=_user_dir(user)),
        patch("calendar_app.infrastructure.i18n.QSettings", return_value=settings),
        patch.object(I18nManager, "apply_application_locale"),
    ):
        target = ensure_user_locale_file("ja")
        snapshot = i18n_module._user_locale_snapshot_path("ja")
        assert target == user / "ja.json"
        assert snapshot.exists() and snapshot.parent != user
        # The snapshot is not a language of its own.
        assert list_available_locale_codes() == {"en", "ja"}

        edited = json.loads(target.read_text(encoding="utf-8", errors="strict"))
        edited["b"] = "私のB"
        _write_json(target, edited)
        _write_json(
            bundle / "ja.json",
            {
                "meta": {"language_name": "日本語"},
                "a": "新しいA",
                "b": "新しいB",
                "nested": {"c": "新しいC", "keep": "同じ"},
                "list": ["月曜", "火曜"],
                "d": "追加",
            },
        )

        manager = object.__new__(I18nManager)
        manager._load_translations()
        assert manager.get("a") == "新しいA"
        assert manager.get("b") == "私のB"
        assert manager.get("nested.c") == "新しいC"
        assert manager.get("nested.keep") == "同じ"
        assert manager.get("list") == ["月曜", "火曜"]
        assert manager.get("d") == "追加"

        # Overrides seeded before snapshots existed behave as before.
        snapshot.unlink()
        legacy = object.__new__(I18nManager)
        legacy._load_translations()
        assert legacy.get("a") == "古いA"
        assert legacy.get("b") == "私のB"

        ensure_user_locale_file("ja")  # existing override: no re-seed
        assert not snapshot.exists()
        _write_json(snapshot, {"a": "古いA"})
        assert remove_user_locale_override("ja")
        assert not target.exists() and not snapshot.exists()
