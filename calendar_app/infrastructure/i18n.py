# -*- coding: utf-8 -*-
import json
import logging
from pathlib import Path
import re
import shutil
import unicodedata

from PyQt6 import sip
from PyQt6.QtCore import QSettings, QTranslator

from calendar_app.app_paths import get_app_data_dir
from calendar_app.shared.encoding_utils import read_text_with_legacy_fallback

logger = logging.getLogger(__name__)

_BUNDLED_LOCALES_DIR = Path(__file__).resolve().parents[2] / "locales"
# Bundled values a user override was seeded from. A subfolder keeps the copies
# out of the "*.json" language scan of the user locale folder.
_USER_LOCALE_SNAPSHOT_DIR = ".base"
_QT_CATALOG_CODES = {"zh": "zh_CN", "zh-CN": "zh_CN", "zh-TW": "zh_TW", "pt": "pt_BR"}
# The app is written in Korean: those button words are authored, not machine
# translated, so they keep beating Qt's catalog exactly as written ("예"/"아니오").
_SOURCE_LANGUAGE = "ko"


def _is_latin_letter(ch: str) -> bool:
    try:
        return unicodedata.name(ch).startswith("LATIN ")
    except ValueError:
        return False


def _with_mnemonic(text: str, source: str) -> str:
    """Keep the Alt mnemonic of a Qt source label such as "&Yes" on its translation."""
    marker = source.find("&")
    if marker < 0 or marker + 1 >= len(source) or "&" in text:
        return text
    key = source[marker + 1]
    letters = [index for index, ch in enumerate(text) if ch.isalpha()]
    if not letters:
        return text
    if not _is_latin_letter(text[letters[0]]):
        # Same form as Qt's CJK catalogs ("是(&Y)"): the Latin key follows the word.
        return f"{text} (&{key.upper()})"
    index = next((i for i in letters if text[i].casefold() == key.casefold()), letters[0])
    return f"{text[:index]}&{text[index:]}"


class _StandardButtonTranslator(QTranslator):
    """Cover common buttons even when Qt ships no catalog for a bundled language."""

    def __init__(self, values, parent, mnemonics=True):
        super().__init__(parent)
        self._values = values
        self._mnemonics = mnemonics

    def isEmpty(self):  # noqa: N802 - Qt API
        return False

    def translate(self, context, sourceText, disambiguation=None, n=-1):  # noqa: N803
        if context in {"QPlatformTheme", "QDialogButtonBox", "QMessageBox"}:
            value = self._values.get(sourceText.replace("&", ""))
            if value and self._mnemonics:
                return _with_mnemonic(value, sourceText)
            return value or None
        # None maps to a null QString: Qt can try the next translator/source.
        # An empty Python string is a successful, blank translation instead.
        return None


def _system_locale():
    from PyQt6.QtCore import QLocale

    return QLocale.system()


def get_user_locales_dir(create: bool = False) -> Path:
    """Return user-editable locale directory under LOCALAPPDATA."""
    user_dir = get_app_data_dir() / "locales_user"
    if create:
        user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def _user_locale_snapshot_path(lang_code: str) -> Path:
    return get_user_locales_dir(create=False) / _USER_LOCALE_SNAPSHOT_DIR / f"{lang_code}.json"


def _drop_unedited_values(user: dict, snapshot: dict) -> dict:
    """Return *user* without the values still equal to the bundle it was seeded from."""
    kept = {}
    for key, value in user.items():
        if key in snapshot:
            seeded = snapshot[key]
            if isinstance(value, dict) and isinstance(seeded, dict):
                nested = _drop_unedited_values(value, seeded)
                if nested:
                    kept[key] = nested
                continue
            if value == seeded:
                continue
        kept[key] = value
    return kept


def _iter_locale_codes(locale_dir: Path) -> set[str]:
    if not locale_dir.exists():
        return set()
    return {path.stem for path in locale_dir.glob("*.json")}


def list_available_locale_codes() -> set[str]:
    """Return union of bundled locale codes and user override locale codes."""
    bundled = _iter_locale_codes(_BUNDLED_LOCALES_DIR)
    user = _iter_locale_codes(get_user_locales_dir(create=False))
    return bundled | user


def resolve_locale_file_path(lang_code: str, prefer_user: bool = True) -> Path | None:
    """Resolve locale path for *lang_code* with optional user override priority."""
    if not lang_code:
        return None
    lang = str(lang_code).strip()
    if not lang:
        return None

    user_path = get_user_locales_dir(create=False) / f"{lang}.json"
    bundled_path = _BUNDLED_LOCALES_DIR / f"{lang}.json"

    if prefer_user and user_path.exists():
        return user_path
    if bundled_path.exists():
        return bundled_path
    if user_path.exists():
        return user_path
    return None


def _read_locale_dict(path: Path, lang_hint: str = "") -> dict:
    if not path.exists():
        return {}
    try:
        decoded = read_text_with_legacy_fallback(path)
        if decoded.encoding != "utf-8":
            logger.warning(
                "i18n: locale %s loaded using legacy encoding %s (%s)",
                lang_hint or path.stem,
                decoded.encoding,
                path,
            )
        data = json.loads(decoded.text)
        if isinstance(data, dict):
            return data
        logger.warning("i18n: locale %s has non-dict root (%s)", lang_hint or path.stem, path)
    except Exception as exc:
        logger.warning("i18n: failed to load locale %s (%s): %s", lang_hint or path.stem, path, exc)
    return {}


def get_locale_display_name(lang_code: str) -> str:
    """Read display name (meta.language_name) for a locale code."""
    path = resolve_locale_file_path(lang_code, prefer_user=True)
    if path is None:
        return lang_code
    data = _read_locale_dict(path, lang_hint=lang_code)
    meta = data.get("meta", {}) if isinstance(data, dict) else {}
    name = meta.get("language_name") if isinstance(meta, dict) else None
    return str(name or lang_code)


def ensure_user_locale_file(lang_code: str) -> Path:
    """Ensure user override file exists for *lang_code*, seeded from bundled locale."""
    lang = str(lang_code or "").strip() or "en"
    user_dir = get_user_locales_dir(create=True)
    target = user_dir / f"{lang}.json"
    if target.exists():
        return target

    source = resolve_locale_file_path(lang, prefer_user=False)
    if source and source.exists():
        # The snapshot tells untouched seeded values apart from edits, so later
        # bundled fixes still reach every string the user did not change.
        snapshot = _user_locale_snapshot_path(lang)
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, snapshot)
        shutil.copy2(source, target)
        return target

    target.write_text(
        json.dumps({"meta": {"language_name": lang}}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        errors="strict",
    )
    return target


def remove_user_locale_override(lang_code: str) -> bool:
    """Remove user override file for *lang_code* if it exists."""
    lang = str(lang_code or "").strip()
    if not lang:
        return False
    path = get_user_locales_dir(create=False) / f"{lang}.json"
    if not path.exists():
        return False
    path.unlink(missing_ok=True)
    _user_locale_snapshot_path(lang).unlink(missing_ok=True)
    return True


def validate_user_locale_file(lang_code: str) -> tuple[bool, str]:
    """Validate user locale JSON format and root type for *lang_code*.

    A partial override is valid: keys it leaves out fall back to the bundled file,
    so they are reported as information and never fail the check.
    """
    lang = str(lang_code or "").strip()
    if not lang:
        return False, t("menu.locale_validate_empty_code", "언어 코드가 비어 있습니다.")
    path = get_user_locales_dir(create=False) / f"{lang}.json"
    if not path.exists():
        return True, t(
            "menu.locale_validate_no_file",
            "사용자 오버라이드 파일이 없습니다: {path}",
            path=path,
        )
    try:
        decoded = read_text_with_legacy_fallback(path)
        data = json.loads(decoded.text)
    except Exception as exc:
        return False, t(
            "menu.locale_validate_parse_failed",
            "JSON을 읽지 못했습니다: {error}",
            error=exc,
        )
    if not isinstance(data, dict):
        return False, t(
            "menu.locale_validate_not_object",
            "로케일 파일의 최상위 JSON은 객체여야 합니다.",
        )

    message = t("menu.locale_validate_passed", "검증을 통과했습니다: {path}", path=path)
    bundled_path = resolve_locale_file_path(lang, prefer_user=False)
    if bundled_path and bundled_path.exists():
        bundled_data = _read_locale_dict(bundled_path, lang_hint=lang)
        missing_top = sorted(set(bundled_data.keys()) - set(data.keys()))
        if missing_top:
            shown = ", ".join(missing_top[:10]) + (", …" if len(missing_top) > 10 else "")
            message += "\n" + t(
                "menu.locale_validate_missing_keys",
                "오버라이드하지 않은 최상위 키 {count}개는 기본 번역을 사용합니다: {keys}",
                count=len(missing_top),
                keys=shown,
            )
    return True, message


class I18nManager:
    _instance = None
    _SUSPICIOUS_QMARK_RE = re.compile(r"\?{2,}\s*[\w\u3131-\uD79D\uFF41-\uFF5A\u4E00-\u9FFF]")
    _LANG_ALIASES = {
        "zh": "zh-CN",
        "zh-cn": "zh-CN",
        "zh-sg": "zh-CN",
        "zh-hans": "zh-CN",
        "zh-tw": "zh-TW",
        "zh-hk": "zh-TW",
        "zh-mo": "zh-TW",
        "zh-hant": "zh-TW",
        "jp": "ja",
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_translations()
        return cls._instance

    @classmethod
    def canonical_locale_code(cls, lang_code, available):
        """Match BCP 47 regional/script tags without losing Traditional Chinese."""
        normalized = str(lang_code or "").strip().replace("_", "-")
        if not normalized:
            return None
        if normalized in available:
            mapped = cls._LANG_ALIASES.get(normalized, normalized)
            return mapped if mapped in available else normalized
        parts = normalized.lower().split("-")
        for length in range(len(parts), 0, -1):
            prefix = "-".join(parts[:length])
            candidate = cls._LANG_ALIASES.get(prefix, prefix)
            if candidate in available:
                return candidate
        return None

    @classmethod
    def detect_system_language(cls, available, system_locale=None):
        """Pick the UI language from the display languages, then the regional format.

        QLocale.system().name() follows the Windows regional format, so a Korean
        display with US formats would otherwise start in English.
        """
        locale = _system_locale() if system_locale is None else system_locale
        for tag in [*locale.uiLanguages(), locale.name()]:
            detected = cls.canonical_locale_code(tag, available)
            if detected:
                return detected
        return None

    def _load_translations(self):
        settings = QSettings("kimhyojin", "Dark Calendar")
        available = list_available_locale_codes()

        # 1. Try to get saved language from settings
        raw_saved_lang = settings.value("language")
        saved_lang = self.canonical_locale_code(raw_saved_lang, available)

        if saved_lang:
            self.lang = saved_lang
            if raw_saved_lang != saved_lang:
                settings.setValue("language", saved_lang)
                settings.sync()
        else:
            # 2. First run: detect from the system display language
            detected = self.detect_system_language(available)
            self.lang = detected or "en"  # Fallback to English

            # Save the detected language so it's consistent on next run
            settings.setValue("language", self.lang)
            settings.sync()

        path = resolve_locale_file_path(self.lang, prefer_user=True)
        bundled_same_path = resolve_locale_file_path(self.lang, prefer_user=False)
        fallback_path = resolve_locale_file_path(
            "en", prefer_user=False
        ) or resolve_locale_file_path("en", prefer_user=True)

        self.translations = self._load_locale_json(str(path) if path else "", self.lang)
        # Bundled locale as intermediate fallback: fills gaps when user locale file is
        # outdated (e.g. missing emoji or new keys added since it was seeded).
        if bundled_same_path and bundled_same_path != path:
            self.bundled_translations = self._load_locale_json(str(bundled_same_path), self.lang)
            snapshot = _read_locale_dict(_user_locale_snapshot_path(self.lang), self.lang)
            if snapshot:
                self.translations = _drop_unedited_values(self.translations, snapshot)
        else:
            self.bundled_translations = {}
        self.fallback_translations = self._load_locale_json(
            str(fallback_path) if fallback_path else "", "en"
        )

        self._warn_if_broken_locale(self.lang, self.translations)
        if self.lang != "en":
            self._warn_if_broken_locale("en", self.fallback_translations)

        # Set Qt default locale so QLocale().toString(..., "dddd") returns weekday
        # names in the current UI language (affects overlay widgets, panels, etc.)
        self.apply_application_locale()

    def apply_application_locale(self):
        """Apply direction and standard Qt translations after QApplication exists."""
        from PyQt6.QtCore import QLibraryInfo
        from PyQt6.QtWidgets import QApplication

        self._apply_qt_locale(self.lang)
        app = QApplication.instance()
        if app is None:
            return
        # Re-applying a language replaces the earlier translators instead of stacking them.
        # A translator whose QApplication was destroyed is already gone.
        for name in ("_qt_translator", "_button_translator"):
            previous = getattr(self, name, None)
            if previous is not None and not sip.isdeleted(previous):
                app.removeTranslator(previous)
                previous.deleteLater()
            setattr(self, name, None)
        buttons = None
        if self.lang != "en":
            buttons = _StandardButtonTranslator(
                {
                    source: self.get(key, source)
                    for source, key in (
                        ("OK", "dialog.common.ok"),
                        ("Cancel", "common.cancel"),
                        ("Save", "common.save"),
                        ("Apply", "common.apply"),
                        ("Close", "common.close"),
                        ("Yes", "dialog.common.yes"),
                        ("No", "dialog.common.no"),
                    )
                },
                app,
                mnemonics=self.lang != _SOURCE_LANGUAGE,
            )
        # Qt asks the most recently installed translator first. Translated button
        # words go in before Qt's catalog, so Qt's reviewed words (with their
        # mnemonics) win and ours only cover languages Qt ships no catalog for.
        # The Korean source words go in after it and keep today's text.
        if buttons is not None and self.lang != _SOURCE_LANGUAGE:
            self._install_translator(app, "_button_translator", buttons)
        code = _QT_CATALOG_CODES.get(self.lang, self.lang)
        translator = QTranslator(app)
        directory = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        if translator.load(f"qtbase_{code}", directory):
            self._install_translator(app, "_qt_translator", translator)
        else:
            translator.deleteLater()
        if buttons is not None and self.lang == _SOURCE_LANGUAGE:
            self._install_translator(app, "_button_translator", buttons)

    def _install_translator(self, app, name, translator):
        if app.installTranslator(translator):
            setattr(self, name, translator)
        else:
            translator.deleteLater()

    @staticmethod
    def _load_locale_json(path: str, lang: str) -> dict:
        if not path:
            return {}
        return _read_locale_dict(Path(path), lang_hint=lang)

    @staticmethod
    def _apply_qt_locale(lang: str, system_locale=None):
        """Set Qt's default locale to match the UI language."""
        from PyQt6.QtCore import QLocale

        _LANG_TO_LOCALE = {
            "ko": QLocale(QLocale.Language.Korean, QLocale.Country.SouthKorea),
            "ja": QLocale(QLocale.Language.Japanese, QLocale.Country.Japan),
            "zh-CN": QLocale(QLocale.Language.Chinese, QLocale.Country.China),
            "zh-TW": QLocale(QLocale.Language.Chinese, QLocale.Country.Taiwan),
            "zh": QLocale(QLocale.Language.Chinese, QLocale.Country.China),
            "de": QLocale(QLocale.Language.German, QLocale.Country.Germany),
            "es": QLocale(QLocale.Language.Spanish, QLocale.Country.Spain),
            "fr": QLocale(QLocale.Language.French, QLocale.Country.France),
            "hi": QLocale(QLocale.Language.Hindi, QLocale.Country.India),
            "id": QLocale(QLocale.Language.Indonesian, QLocale.Country.Indonesia),
            "it": QLocale(QLocale.Language.Italian, QLocale.Country.Italy),
            "nl": QLocale(QLocale.Language.Dutch, QLocale.Country.Netherlands),
            "pt": QLocale(QLocale.Language.Portuguese, QLocale.Country.Brazil),
            "ru": QLocale(QLocale.Language.Russian, QLocale.Country.Russia),
            "th": QLocale(QLocale.Language.Thai, QLocale.Country.Thailand),
            "tr": QLocale(QLocale.Language.Turkish, QLocale.Country.Turkey),
            "vi": QLocale(QLocale.Language.Vietnamese, QLocale.Country.Vietnam),
            "ar": QLocale(QLocale.Language.Arabic, QLocale.Country.SaudiArabia),
        }
        locale = _LANG_TO_LOCALE.get(
            lang, QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)
        )
        # Keep the user's own region (en_GB dates, pt_PT words, ar_MA digits) when
        # it is the UI language in the same script; zh-TW never becomes Simplified.
        system = _system_locale() if system_locale is None else system_locale
        if system.language() == locale.language() and system.script() == locale.script():
            locale = QLocale(system.language(), system.script(), system.territory())
        QLocale.setDefault(locale)

        # Set layout direction for RTL languages (Arabic, Hebrew, etc.)
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            if lang in {"ar"}:
                app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            else:
                app.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

    def _resolve(self, dotted_key):
        return self._resolve_from(self.translations, dotted_key)

    def _resolve_from(self, data, dotted_key):
        if isinstance(data, dict) and dotted_key in data:
            return data[dotted_key]
        parts = dotted_key.split(".")
        current = data
        for idx, part in enumerate(parts):
            if isinstance(current, dict) and part in current:
                current = current[part]
                continue
            remaining = ".".join(parts[idx:])
            if isinstance(current, dict) and remaining in current:
                return current[remaining]
            return None
        return current

    def _resolve_alias(self, key, data=None):
        source = self.translations if data is None else data
        # Legacy keys used in some dialogs
        if key.startswith("dialog.shortcut."):
            return self._resolve_from(source, "shortcut." + key[len("dialog.shortcut.") :])
        if key.startswith("dialog.help."):
            return self._resolve_from(source, "help." + key[len("dialog.help.") :])
        if key == "recurrence.finish":
            return self._resolve_from(source, "recurrence.btn_finish")
        if key.startswith("common."):
            suffix = key[len("common.") :]
            for prefix in ("dialog.common.", "panel.common."):
                value = self._resolve_from(source, prefix + suffix)
                if value is not None:
                    return value
        return None

    @staticmethod
    def _looks_broken_text(value):
        if not isinstance(value, str):
            return False
        stripped = value.strip()
        if not stripped:
            return False
        if "\ufffd" in value:
            return True
        if all(ch in {"?", " ", "\t", "\n"} for ch in stripped):
            return True
        if value.count("?") >= 3:
            return True
        return bool(I18nManager._SUSPICIOUS_QMARK_RE.search(value))

    def _collect_broken_keys(self, data, prefix=""):
        broken = []
        if isinstance(data, dict):
            for key, value in data.items():
                dotted = f"{prefix}.{key}" if prefix else str(key)
                broken.extend(self._collect_broken_keys(value, dotted))
        elif isinstance(data, list):
            for idx, value in enumerate(data):
                dotted = f"{prefix}[{idx}]"
                broken.extend(self._collect_broken_keys(value, dotted))
        elif self._looks_broken_text(data):
            broken.append(prefix)
        return broken

    def _warn_if_broken_locale(self, lang, data):
        broken_keys = self._collect_broken_keys(data)
        if not broken_keys:
            return
        preview = ", ".join(broken_keys[:8])
        extra = ""
        if len(broken_keys) > 8:
            extra = f" (+{len(broken_keys) - 8} more)"
        logger.warning("i18n: suspicious locale strings detected in %s: %s%s", lang, preview, extra)

    def get(self, key, default=None, **kwargs):
        for source in (
            self.translations,
            getattr(self, "bundled_translations", {}),
            getattr(self, "fallback_translations", {}),
        ):
            data = self._resolve_from(source, key)
            if data is None:
                data = self._resolve_alias(key, source)
            if data is None or self._looks_broken_text(data):
                continue
            if isinstance(data, str) and kwargs:
                try:
                    return data.format(**kwargs)
                except (KeyError, IndexError, ValueError, AttributeError, TypeError):
                    # A malformed user override must not leak unformatted fields.
                    continue
            return data
        # An explicit empty string is a valid fallback for optional UI text.
        data = default if default is not None else key
        if isinstance(data, str) and kwargs:
            try:
                return data.format(**kwargs)
            except (KeyError, IndexError, ValueError, AttributeError, TypeError):
                pass
        return data


# Global access
i18n = I18nManager()


def t(key, default=None, **kwargs):
    return i18n.get(key, default, **kwargs)
