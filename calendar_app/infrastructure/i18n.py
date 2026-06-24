import json
import logging
from pathlib import Path
import re
import shutil

from PyQt6.QtCore import QSettings

from calendar_app.app_paths import get_app_data_dir
from calendar_app.shared.encoding_utils import read_text_with_legacy_fallback

logger = logging.getLogger(__name__)

_BUNDLED_LOCALES_DIR = Path(__file__).resolve().parents[2] / "locales"


def get_user_locales_dir(create: bool = False) -> Path:
    """Return user-editable locale directory under LOCALAPPDATA."""
    user_dir = get_app_data_dir() / "locales_user"
    if create:
        user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


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
    return True


def validate_user_locale_file(lang_code: str) -> tuple[bool, str]:
    """Validate user locale JSON format and root type for *lang_code*."""
    lang = str(lang_code or "").strip()
    if not lang:
        return False, "Language code is empty."
    path = get_user_locales_dir(create=False) / f"{lang}.json"
    if not path.exists():
        return True, f"No user override file exists: {path}"
    try:
        decoded = read_text_with_legacy_fallback(path)
        data = json.loads(decoded.text)
    except Exception as exc:
        return False, f"JSON parse failed: {exc}"
    if not isinstance(data, dict):
        return False, "Locale root JSON must be an object (dict)."

    bundled_path = resolve_locale_file_path(lang, prefer_user=False)
    if bundled_path and bundled_path.exists():
        bundled_data = _read_locale_dict(bundled_path, lang_hint=lang)
        missing_top = sorted(set(bundled_data.keys()) - set(data.keys()))
        if missing_top:
            return False, f"Missing top-level keys vs bundled locale: {', '.join(missing_top[:10])}"
    return True, f"Validation passed: {path}"


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

    def _load_translations(self):
        settings = QSettings("kimhyojin", "Dark Calendar")
        available = list_available_locale_codes()

        def canonicalize(lang_code):
            if not lang_code:
                return None
            normalized = str(lang_code).strip().replace("_", "-")
            if not normalized:
                return None
            lowered = normalized.lower()
            mapped = self._LANG_ALIASES.get(lowered, normalized)
            if mapped in available:
                return mapped
            if normalized in available:
                return normalized
            base = lowered.split("-")[0]
            mapped_base = self._LANG_ALIASES.get(base, base)
            if mapped_base in available:
                return mapped_base
            if base in available:
                return base
            return None

        # 1. Try to get saved language from settings
        saved_lang = canonicalize(settings.value("language"))

        if saved_lang:
            self.lang = saved_lang
        else:
            # 2. First run: detect from system locale
            from PyQt6.QtCore import QLocale

            system_locale = QLocale.system().name()  # e.g. "ko_KR", "en_US"
            detected = canonicalize(system_locale)
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
        else:
            self.bundled_translations = {}
        self.fallback_translations = self._load_locale_json(
            str(fallback_path) if fallback_path else "", "en"
        )

        self._warn_if_broken_locale(self.lang, self.translations)
        if self.lang != "en":
            self._warn_if_broken_locale("en", self.fallback_translations)

        # Set Qt default locale so QDateTime.toString("dddd") returns weekday
        # names in the current UI language (affects overlay widgets, panels, etc.)
        self._apply_qt_locale(self.lang)

    @staticmethod
    def _load_locale_json(path: str, lang: str) -> dict:
        if not path:
            return {}
        return _read_locale_dict(Path(path), lang_hint=lang)

    @staticmethod
    def _apply_qt_locale(lang: str):
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
        QLocale.setDefault(locale)

    def _resolve(self, dotted_key):
        parts = dotted_key.split(".")
        data = self.translations
        for part in parts:
            if isinstance(data, dict) and part in data:
                data = data[part]
            else:
                return None
        return data

    def _resolve_from(self, data, dotted_key):
        parts = dotted_key.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current

    def _weekday_from_calendar(self, key):
        weekday_index = {
            "weekday.mon": 0,
            "weekday.tue": 1,
            "weekday.wed": 2,
            "weekday.thu": 3,
            "weekday.fri": 4,
            "weekday.sat": 5,
            "weekday.sun": 6,
        }.get(key)
        if weekday_index is None:
            return None
        weekdays = self._resolve("calendar.weekdays")
        if isinstance(weekdays, list) and len(weekdays) > weekday_index:
            return weekdays[weekday_index]
        return None

    def _resolve_alias(self, key):
        # Legacy keys used in some dialogs
        if key.startswith("dialog.shortcut."):
            return self._resolve("shortcut." + key[len("dialog.shortcut.") :])
        if key.startswith("dialog.help."):
            return self._resolve("help." + key[len("dialog.help.") :])
        if key == "recurrence.finish":
            return self._resolve("recurrence.btn_finish")
        if key.startswith("common."):
            suffix = key[len("common.") :]
            for prefix in ("dialog.common.", "panel.common."):
                value = self._resolve(prefix + suffix)
                if value is not None:
                    return value
        if key.startswith("weekday."):
            return self._weekday_from_calendar(key)
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
        data = self._resolve(key)
        if data is None:
            data = self._resolve_alias(key)
        if data is None or self._looks_broken_text(data):
            # Try bundled locale before English fallback: recovers keys missing from
            # stale user locale files (e.g. emoji added after file was seeded).
            data = self._resolve_from(getattr(self, "bundled_translations", {}), key)
        if data is None or self._looks_broken_text(data):
            data = self._resolve_from(getattr(self, "fallback_translations", {}), key)
        if (data is None or self._looks_broken_text(data)) and key.startswith("common."):
            suffix = key[len("common.") :]
            for prefix in ("dialog.common.", "panel.common."):
                data = self._resolve_from(
                    getattr(self, "fallback_translations", {}), prefix + suffix
                )
                if data is not None and not self._looks_broken_text(data):
                    break
        if self._looks_broken_text(data):
            data = None
        if data is None:
            data = default or key

        if isinstance(data, str) and kwargs:
            try:
                return data.format(**kwargs)
            except Exception:
                pass
        return data


# Global access
i18n = I18nManager()


def t(key, default=None, **kwargs):
    return i18n.get(key, default, **kwargs)
