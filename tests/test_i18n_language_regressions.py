# -*- coding: utf-8 -*-
"""Locale precedence, startup direction, Qt buttons and date templates."""

from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QCoreApplication, QDate, QDateTime, QLocale, QSettings, Qt
from PyQt6.QtWidgets import QApplication, QDialogButtonBox, QWidget
import pytest
from scripts.i18n_sync import load_locale

from calendar_app.infrastructure.i18n import I18nManager, _StandardButtonTranslator, i18n
from calendar_app.presentation.widgets.overlay_text import OverlayTextWidget

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("context", ["AirCalendarUnmappedQtContext", "QMessageBox"])
def test_standard_button_override_preserves_unmapped_qt_messages(app, context):
    translator = _StandardButtonTranslator({"Yes": "예"}, app)
    app.installTranslator(translator)
    try:
        assert QCoreApplication.translate("QPlatformTheme", "Yes") == "예"
        assert QCoreApplication.translate(context, "Unmapped Qt text %1") == "Unmapped Qt text %1"
    finally:
        app.removeTranslator(translator)
        translator.deleteLater()


def manager_for(code):
    manager = object.__new__(I18nManager)
    manager.lang = code
    manager.translations = load_locale(ROOT / "locales" / f"{code}.json")
    manager.bundled_translations = {}
    manager.fallback_translations = load_locale(ROOT / "locales/en.json")
    return manager


@pytest.mark.parametrize(
    "tag,expected",
    [
        ("zh-Hant-TW", "zh-TW"),
        ("zh_Hant_HK", "zh-TW"),
        ("zh-Hans-SG", "zh-CN"),
        ("zh_HK", "zh-TW"),
        ("zh", "zh-CN"),
        ("jp", "ja"),
        ("EN_us", "en"),
        ("pt_BR", "pt"),
        ("ar_SA", "ar"),
        ("unknown", None),
        ("", None),
    ],
)
def test_region_and_script_aliases(tag, expected):
    available = {p.stem for p in (ROOT / "locales").glob("*.json")}
    assert I18nManager.canonical_locale_code(tag, available) == expected


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application
    i18n.apply_application_locale()


@pytest.mark.parametrize("layer", ["translations", "bundled_translations", "fallback_translations"])
def test_legacy_aliases_work_at_every_fallback_layer(layer):
    manager = object.__new__(I18nManager)
    manager.translations = {}
    manager.bundled_translations = {}
    manager.fallback_translations = {}
    setattr(
        manager,
        layer,
        {
            "shortcut": {"title": "Shortcuts"},
            "calendar": {"weekdays": ["M", "T", "W", "T", "F", "S", "S"]},
            "dialog": {"common": {"save": "Save"}},
            "recurrence": {"btn_finish": "Done"},
        },
    )
    assert manager.get("dialog.shortcut.title") == "Shortcuts"
    assert manager.get("weekday.mon") == "M"
    assert manager.get("common.save") == "Save"
    assert manager.get("recurrence.finish") == "Done"


def test_malformed_user_format_uses_bundled_then_english():
    manager = object.__new__(I18nManager)
    manager.translations = {"count": "{wrong}", "broken": "???"}
    manager.bundled_translations = {"count": "{count}개", "broken": "정상"}
    manager.fallback_translations = {"count": "{count} items"}
    assert manager.get("count", count=3) == "3개"
    assert manager.get("broken") == "정상"
    manager.bundled_translations["count"] = "{count:bad}"
    assert manager.get("count", count=3) == "3 items"
    assert manager.get("missing", "", count=3) == ""


@pytest.mark.parametrize("code", [p.stem for p in sorted((ROOT / "locales").glob("*.json"))])
def test_qt_direction_and_standard_buttons_follow_language(app, code):
    manager = manager_for(code)
    manager.apply_application_locale()
    try:
        assert app.layoutDirection() == (
            Qt.LayoutDirection.RightToLeft if code == "ar" else Qt.LayoutDirection.LeftToRight
        )
        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Close
            | QDialogButtonBox.StandardButton.Yes
            | QDialogButtonBox.StandardButton.No
        )
        for name, key in (
            ("Cancel", "common.cancel"),
            ("Save", "common.save"),
            ("Ok", "dialog.common.ok"),
            ("Apply", "common.apply"),
            ("Close", "common.close"),
            ("Yes", "dialog.common.yes"),
            ("No", "dialog.common.no"),
        ):
            assert box.button(getattr(QDialogButtonBox.StandardButton, name)).text().replace(
                "&", ""
            ) == manager.get(key).replace("&", "")
        box.deleteLater()
    finally:
        for name in ("_button_translator", "_qt_translator"):
            translator = getattr(manager, name, None)
            if translator is not None:
                app.removeTranslator(translator)
                translator.deleteLater()
        i18n.apply_application_locale()


@pytest.mark.parametrize("code", ["ja", "de", "ar", "ko"])
def test_template_weekday_and_strftime_names_follow_ui_language(app, code, tmp_path):
    original = QLocale()
    I18nManager._apply_qt_locale(code)
    fixed = QDateTime(QDate(2026, 11, 2), QDateTime.currentDateTime().time())
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "widget.ini"), QSettings.Format.IniFormat)
    widget = OverlayTextWidget(owner)
    try:
        with patch("calendar_app.presentation.widgets.overlay_text.QDateTime") as date_time:
            date_time.currentDateTime.return_value = fixed
            raw = "{weekday} | {weekday:short} | {date:%B} | {weekday:en}"
            actual = OverlayTextWidget.resolve_template(widget, override_text=raw)
        locale = QLocale()
        for pattern in ("dddd", "ddd", "MMMM"):
            assert locale.toString(fixed, pattern) in actual
        assert "Mon" in actual  # Explicit :en keeps its documented meaning.
    finally:
        widget.close()
        widget.deleteLater()
        owner.close()
        owner.deleteLater()
        QLocale.setDefault(original)
        i18n.apply_application_locale()


def test_bootstrap_applies_language_after_application_creation():
    source = (ROOT / "calendar_app/bootstrap.py").read_text(encoding="utf-8", errors="strict")
    assert source.index("app = QApplication(") < source.index(
        "i18n.apply_application_locale()"
    )


def test_partial_user_override_keeps_bundle_and_english_fallbacks(app, tmp_path):
    import json

    bundle, user = tmp_path / "bundles", tmp_path / "user"
    bundle.mkdir()
    user.mkdir()
    documents = {
        bundle / "ja.json": {"message": "標準", "new": "新しい文言", "count": "{count}件"},
        bundle / "en.json": {
            "message": "Default",
            "new": "New copy",
            "only_en": "English fallback",
        },
        user / "ja.json": {"message": "カスタム", "count": "{wrong}"},
    }
    for path, data in documents.items():
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8", errors="strict")
    before = (user / "ja.json").read_bytes()
    settings = QSettings(str(tmp_path / "app.ini"), QSettings.Format.IniFormat)
    settings.setValue("language", "ja_JP")
    manager = object.__new__(I18nManager)
    with (
        patch("calendar_app.infrastructure.i18n.QSettings", return_value=settings),
        patch("calendar_app.infrastructure.i18n._BUNDLED_LOCALES_DIR", bundle),
        patch("calendar_app.infrastructure.i18n.get_user_locales_dir", return_value=user),
    ):
        manager._load_translations()
    try:
        assert manager.lang == "ja"
        assert settings.value("language") == "ja"
        assert manager.get("message") == "カスタム"
        assert manager.get("new") == "新しい文言"
        assert manager.get("only_en") == "English fallback"
        assert manager.get("count", count=2) == "2件"
        assert (user / "ja.json").read_bytes() == before
    finally:
        for name in ("_button_translator", "_qt_translator"):
            translator = getattr(manager, name, None)
            if translator is not None:
                app.removeTranslator(translator)
                translator.deleteLater()
        i18n.apply_application_locale()


def test_light_workspace_scroll_surfaces_remain_readable(app, tmp_path):
    from calendar_app.presentation.dialogs.widget_workspace_options_dialog import (
        WidgetWorkspaceOptionsDialog,
    )
    from calendar_app.presentation.widgets.overlay_manager import OverlayWidgetManager
    from calendar_app.presentation.widgets.overlay_manager_dialog import (
        OverlayManagerDialog,
        _load_tokens,
    )

    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "workspace.ini"), QSettings.Format.IniFormat)
    owner.settings.setValue("text_theme", "light")
    owner.settings.setValue("panel_base_color", "#f4f6f9")
    manager = OverlayWidgetManager(owner)
    manager.workspace_service().save_profile("Arbeitsbereiche")
    tokens = _load_tokens(owner.settings)
    with patch(
        "calendar_app.presentation.widgets.overlay_manager_dialog._load_tokens", return_value=tokens
    ):
        dialog = OverlayManagerDialog(manager, owner)
        dialog.show()
        dialog.tabs.setCurrentIndex(2)
        options = WidgetWorkspaceOptionsDialog(manager.workspace_service(), dialog)
        options.show()
        app.processEvents()
        for surface in (dialog.workspace_panel, options.controls_scroll.widget()):
            assert surface.grab().toImage().pixelColor(2, 2).lightness() > 180
        item = dialog.workspace_panel.list.item(0)
        assert item.sizeHint().width() >= 240
        assert item.toolTip() == "Arbeitsbereiche"
        options.reject()
        options.deleteLater()
        dialog.close()
        dialog.deleteLater()
    manager.shutdown()
    owner.close()
    owner.deleteLater()
