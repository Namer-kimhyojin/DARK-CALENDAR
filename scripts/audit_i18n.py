# -*- coding: utf-8 -*-
"""Read-only bundle/source audit. English matches are review candidates, not errors.

Quality findings (mojibake, stale English, dropped text, protected terms, Hangul source
literals, non-literal t() keys, English source drift and others) are review records,
not errors. A committed baseline lists the accepted findings, so tests fail only on new
ones; ``--update-baseline`` rewrites it from the current tree.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from string import Formatter
import unicodedata

try:
    from scripts.i18n_sync import (
        PENDING_REVIEW_PATH,
        PROJECT_ROOT,
        compare_locale,
        flatten_locale,
        has_whole_token,
        load_pending_review,
        normalize_locale_data,
        render_locale_json,
    )
except ModuleNotFoundError:
    from i18n_sync import (
        PENDING_REVIEW_PATH,
        PROJECT_ROOT,
        compare_locale,
        flatten_locale,
        has_whole_token,
        load_pending_review,
        normalize_locale_data,
        render_locale_json,
    )

ROOT = Path(__file__).resolve().parents[1]
HANGUL = re.compile(r"[\u3131-\u318e\uac00-\ud7a3]")
BASELINE_RELATIVE = Path("tests/fixtures/i18n_audit_baseline.json")
PENDING_REVIEW_RELATIVE = PENDING_REVIEW_PATH.relative_to(PROJECT_ROOT)
SOURCE_LOCALES = {"ko", "en"}
KOREAN_LENGTH_LIMITS = {"ja": 0.5, "zh": 0.32, "zh-CN": 0.32, "zh-TW": 0.32}
ENGLISH_LENGTH_LIMITS = {"ja": 0.25, "zh": 0.16, "zh-CN": 0.16, "zh-TW": 0.16}
# Findings listed for review only: never part of the baseline or the ratchet.
REPORT_ONLY_CHECKS = {"hangul_literal"}
T_FUNCTIONS = {"t", "_t", "i18n_t", "_translate"}

# Text that is not prose: placeholders, markup, links, code and quoted UI labels.
PLACEHOLDER_FIELD = re.compile(r"\{[^{}]*\}")
TAG = re.compile(r"</?([A-Za-z][A-Za-z0-9]*)\b[^<>]*>")
URL = re.compile(r"(?:https?://|www\.)\S+")
CODE_TOKEN = re.compile(r"`[^`]*`|\b\w+(?:[_./:]\w+)+\b|%[A-Za-z]")
QUOTED = re.compile(r"\"[^\"]*\"|“[^”]*”|„[^“”]*[“”]|«[^»]*»|‘[^’]*’|「[^」]*」|『[^』]*』")
BRAND_PHRASES = re.compile(
    r"Microsoft To Do|To Do\b|Air Calendar|Google Calendar|Sign in with Google", re.I
)

MOJIBAKE_INNER = re.compile(r"[^\W\d_]\?[^\W\d_]")
MOJIBAKE_WORD_END = re.compile(r"[^\W\d_]\?(?=[\s,.;:)\]]|$)")

FUNCTION_WORD = re.compile(
    r"(?<![\w'’-])(the|to|of|was|is|for|with|before|after|from|and)(?![\w'’-])", re.I
)
# Native words spelled like English ones; pt "for" is a verb form ("se for", "quando for").
# "default" is left out: Indonesian uses it as a loanword.
FUNCTION_WORDS_NATIVE = {
    "nl": {"is", "was", "of"},
    "de": {"was"},
    "vi": {"to"},
    "pt": {"for"},
}
NO_START_NATIVE = {"es", "it", "pt"}
ENGLISH_START = re.compile(r"^\s*(Next|No) ")
DUTCH_NEE = re.compile(r"\bNee [a-z]")

SCRIPT_RANGES = {
    "hangul": "\u1100-\u11ff\u3130-\u318f\ua960-\ua97f\uac00-\ud7af",
    "kana": "\u3040-\u30ff\u31f0-\u31ff\uff66-\uff9f",
    "han": "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff",
    "arabic": "\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff",
    "devanagari": "\u0900-\u097f",
    "thai": "\u0e00-\u0e7f",
    "cyrillic": "\u0400-\u04ff",
    "greek": "\u0370-\u03ff",
    "hebrew": "\u0590-\u05ff",
}
SCRIPT_PATTERNS = {name: re.compile(f"[{chars}]") for name, chars in SCRIPT_RANGES.items()}
LOCALE_SCRIPTS = {
    "ko": {"hangul", "han"},
    "ja": {"kana", "han"},
    "zh": {"han"},
    "zh-CN": {"han"},
    "zh-TW": {"han"},
    "ar": {"arabic"},
    "hi": {"devanagari"},
    "th": {"thai"},
    "ru": {"cyrillic"},
}

PROTECTED_PATTERNS = (
    ("brand", re.compile(r"Air Calendar")),
    (
        "file",
        re.compile(
            r"(?<![\w*.])[A-Za-z0-9_-]+\.(?:json|webp|ics|png|gif|svg|jpe?g|wav|mp3|exe|lnk|ini|airlayout)\b"
        ),
    ),
    ("code", re.compile(r"\b[a-z]+(?:_[a-z]+)+\b")),
    ("time_token", re.compile(r"\b(?:HH|hh):mm(?::ss)?\b")),
)
# Modifier names may be localized (Strg, Umschalt, Maj, Mayús); the key letter may not.
SHORTCUT = re.compile(
    r"\b(?:(?:Ctrl|Shift|Alt|Win|Cmd)\+)+([A-Z0-9]|F(?:[1-9]|1[0-2]))(?![A-Za-z0-9])"
)
MODIFIER = r"(?:Ctrl|Strg|Shift|Umschalt|Maj|Mayús|Maiusc|Alt|Win|Cmd)"
SHORTCUT_NON_LATIN = re.compile(MODIFIER + r"\+([^\x00-\x7f\s])")


def _non_latin_shortcut_keys(value):
    """Single non-Latin letters used as a key ("Ctrl+د"), not words ("Ctrl+클릭")."""
    keys = []
    for match in SHORTCUT_NON_LATIN.finditer(value):
        following = value[match.end() : match.end() + 1]
        if not following or unicodedata.category(following)[0] not in "LM":
            keys.append(match.group(1))
    return keys


QT_FORMAT_TOKEN = re.compile(
    r"'[^']*'|AP|ap|yyyy|yy|M{1,4}|d{1,4}|H{1,2}|h{1,2}|m{1,2}|s{1,2}|z{1,3}|A|a|t"
)
QT_TOKEN_CATEGORY = (
    ("yy", "year"),
    ("M", "month"),
    ("ddd", "weekday"),
    ("d", "day"),
    ("H", "hour"),
    ("h", "hour"),
    ("m", "minute"),
    ("s", "second"),
    ("z", "millisecond"),
    ("AP", "ampm"),
    ("ap", "ampm"),
    ("A", "ampm"),
    ("a", "ampm"),
    ("t", "timezone"),
)

WEEKDAY_KEYS = {}
for _index, _name in enumerate(("mon", "tue", "wed", "thu", "fri", "sat", "sun"), start=1):
    WEEKDAY_KEYS[f"weekday.{_name}"] = _index
    WEEKDAY_KEYS[f"widget_studio.day_{_name}"] = _index
    WEEKDAY_KEYS[f"calendar.weekdays[{_index - 1}]"] = _index
MONTH_KEYS = {
    f"month.{name}": index
    for index, name in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"),
        start=1,
    )
}
MONTH_KEYS.update({f"calendar.months[{index - 1}]": index for index in range(1, 13)})

UI_SINK_METHODS = {
    "setText",
    "setToolTip",
    "setWindowTitle",
    "setPlaceholderText",
    "addItem",
    "addItems",
    "insertItem",
    "setItemText",
    "setTitle",
    "setStatusTip",
    "setAccessibleName",
    "setTabText",
    "addTab",
    "insertTab",
    "setHeaderLabels",
    "setHorizontalHeaderLabels",
    "setSuffix",
    "setPrefix",
    "setSpecialValueText",
    "showMessage",
}
UI_SINK_CLASSES = {
    "QLabel",
    "QPushButton",
    "QToolButton",
    "QAction",
    "QCheckBox",
    "QRadioButton",
    "QGroupBox",
    "QMenu",
    "QListWidgetItem",
    "QTableWidgetItem",
    "QTreeWidgetItem",
}
MESSAGE_BOX_METHODS = {"information", "warning", "critical", "question", "about"}
LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical", "log"}
LOGGER_NAMES = {"logger", "logging", "log", "_logger", "LOGGER", "_log", "warnings"}


def format_signature(value):
    """Include format specs, conversions and nested width/precision fields."""
    fields = []
    for _, name, spec, conversion in Formatter().parse(value):
        if name is not None:
            fields.append((name, spec, conversion))
            if "{" in spec:
                fields.extend(format_signature(spec))
    return fields


def string_entries(value, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from string_entries(item, f"{prefix}.{key}" if prefix else key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from string_entries(item, f"{prefix}[{index}]")
    elif isinstance(value, str):
        yield prefix, value


def untranslated_candidates(target, english, korean):
    """Do not classify shared brand names, technical terms, or digits as untranslated."""
    return sorted(
        key
        for key, value in target.items()
        if isinstance(value, str)
        and value == english.get(key)
        and value != korean.get(key)
        and re.search(r"[A-Za-z]{3}", value)
    )


def parse_sources(source_dir):
    """Parse every module once; the audit never imports or runs application code."""
    trees, parse_errors = [], []
    for path in sorted(source_dir.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="strict"))
        except (SyntaxError, UnicodeError) as exc:
            parse_errors.append({"file": str(path), "error": str(exc)})
            continue
        trees.append((path.relative_to(source_dir).as_posix(), tree))
    return trees, parse_errors


def source_key_gaps(source_dir, keys, parsed=None):
    gaps = {}
    trees, parse_errors = parsed if parsed is not None else parse_sources(source_dir)
    for relative, tree in trees:
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"t", "_t"}
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                continue
            key = node.args[0].value
            if key not in keys:
                gaps.setdefault(key, []).append(f"{relative}:{node.lineno}")
    return gaps, parse_errors


def finding(check, locale, key, detail=""):
    return {"check": check, "locale": locale, "key": key, "detail": detail}


def _prose(value):
    """Remove text that must not be judged as translated prose."""
    for pattern in (URL, PLACEHOLDER_FIELD, TAG, QUOTED, BRAND_PHRASES, CODE_TOKEN):
        value = pattern.sub(" ", value)
    return value


def _visible_length(value):
    value = PLACEHOLDER_FIELD.sub("", TAG.sub("", value))
    return len(" ".join(value.split()))


def _is_latin_text(value):
    text = PLACEHOLDER_FIELD.sub(" ", value)
    if not re.search(r"[A-Za-z]{3,}", text):
        return False
    return not any(
        pattern.search(text) for name, pattern in SCRIPT_PATTERNS.items() if name != "greek"
    )


def check_mojibake(locales):
    """A '?' that replaced a letter (inside or at the end of a word) or U+FFFD."""
    english = locales.get("en", {})
    for code, strings in locales.items():
        for key, value in strings.items():
            if "\ufffd" in value:
                yield finding("mojibake", code, key, "U+FFFD replacement character")
                continue
            text = URL.sub(" ", PLACEHOLDER_FIELD.sub(" ", value))
            reference = URL.sub(" ", PLACEHOLDER_FIELD.sub(" ", english.get(key, "")))
            match = MOJIBAKE_INNER.search(text)
            if match and (code == "en" or not MOJIBAKE_INNER.search(reference)):
                yield finding("mojibake", code, key, f"letter?letter: {match.group()}")
                continue
            if code in SOURCE_LOCALES or "?" in reference or "¿" in text:
                continue
            match = MOJIBAKE_WORD_END.search(text)
            if match:
                yield finding("mojibake", code, key, f"'?' after a word: {match.group()}")


def check_stale_english(locales):
    """The same Latin text in 4+ translated locales that no longer matches English."""
    english = locales.get("en", {})
    vocabulary = {
        word.lower() for value in english.values() for word in re.findall(r"[A-Za-z]{3,}", value)
    }
    targets = [code for code in locales if code not in SOURCE_LOCALES]
    for key, english_value in english.items():
        groups = defaultdict(list)
        for code in targets:
            value = locales[code].get(key)
            if value is not None and value != english_value and _is_latin_text(value):
                groups[value].append(code)
        for value, codes in groups.items():
            if len(codes) < 4:
                continue
            words = [word.lower() for word in re.findall(r"[A-Za-z]{3,}", value)]
            if sum(word in vocabulary for word in words) < 0.8 * len(words):
                continue
            for code in codes:
                yield finding("stale_english", code, key, f"{len(codes)} locales share {value!r}")


def check_english_words(locales):
    english = locales.get("en", {})
    for code, strings in locales.items():
        if code in SOURCE_LOCALES:
            continue
        native = FUNCTION_WORDS_NATIVE.get(code, set())
        for key, value in strings.items():
            if value == english.get(key):
                continue
            prose = _prose(value)
            words = sorted(
                {
                    word
                    for word in FUNCTION_WORD.findall(prose)
                    if word.lower() not in native and not (word.isupper() and len(word) > 1)
                }
            )
            start = ENGLISH_START.match(value)
            if start and not (start.group(1) == "No" and code in NO_START_NATIVE):
                words.append(start.group().strip() + "…")
            if code == "nl" and DUTCH_NEE.search(value):
                words.append("Nee …")
            if words:
                yield finding("english_words", code, key, ", ".join(words))


def check_length_ratio(locales):
    """Translations far shorter than a long English source usually dropped a sentence.

    Limits are about half a language's usual length ratio. Japanese and Chinese are
    compared with the Korean source, whose density is close to theirs (ja/ko median 1.0,
    zh/ko 0.63); against English they overlap with correct short translations.
    """
    english, korean = locales.get("en", {}), locales.get("ko", {})
    for key, english_value in english.items():
        source_length = _visible_length(english_value)
        if source_length < 35:
            continue
        for code, strings in locales.items():
            if code in SOURCE_LOCALES or key not in strings or strings[key] == english_value:
                continue
            length = _visible_length(strings[key])
            korean_length = _visible_length(korean.get(key, ""))
            if code in KOREAN_LENGTH_LIMITS and korean_length and korean[key] != english_value:
                ratio, limit, source = (
                    length / korean_length,
                    KOREAN_LENGTH_LIMITS[code],
                    "Korean",
                )
            else:
                ratio, limit, source = (
                    length / source_length,
                    ENGLISH_LENGTH_LIMITS.get(code, 0.5),
                    "English",
                )
            if ratio < limit:
                yield finding("length_ratio", code, key, f"{ratio:.2f} of {source} length")


def check_markup_parity(locales):
    english = locales.get("en", {})
    for code, strings in locales.items():
        if code == "en":
            continue
        for key, value in strings.items():
            reference = english.get(key)
            if reference is None:
                continue
            problems = []
            expected = Counter(tag.lower() for tag in TAG.findall(reference))
            actual = Counter(tag.lower() for tag in TAG.findall(value))
            if expected != actual:
                missing = sorted((expected - actual).elements())
                extra = sorted((actual - expected).elements())
                problems.append(f"tags missing {missing} extra {extra}")
            if reference.count("\n") != value.count("\n"):
                problems.append(
                    f"newlines en={reference.count(chr(10))} {code}={value.count(chr(10))}"
                )
            if problems:
                yield finding("markup_parity", code, key, "; ".join(problems))


def qt_format_categories(value):
    """Return the token categories of a Qt date/time pattern, or None for prose."""
    categories, position = set(), 0
    for match in QT_FORMAT_TOKEN.finditer(value):
        gap = value[position : match.start()]
        if re.search(r"[A-Za-z]", gap):
            return None
        position = match.end()
        token = match.group()
        if token.startswith("'"):
            continue
        for prefix, category in QT_TOKEN_CATEGORY:
            if token.startswith(prefix):
                categories.add(category)
                break
    if re.search(r"[A-Za-z]", value[position:]):
        return None
    return categories


def check_qt_formats(locales):
    english = locales.get("en", {})
    for key, english_value in english.items():
        if not key.rsplit(".", 1)[-1].endswith("_format") or "{" in english_value:
            continue
        expected = qt_format_categories(english_value)
        if not expected:
            continue
        for code, strings in locales.items():
            if code == "en" or key not in strings:
                continue
            actual = qt_format_categories(strings[key])
            if actual is None:
                yield finding("qt_format", code, key, "letters outside Qt date/time tokens")
            elif actual != expected:
                yield finding(
                    "qt_format",
                    code,
                    key,
                    f"tokens {sorted(actual)} differ from English {sorted(expected)}",
                )


def check_foreign_script(locales):
    for code, strings in locales.items():
        allowed = LOCALE_SCRIPTS.get(code, set())
        for key, value in strings.items():
            scripts = sorted(
                name
                for name, pattern in SCRIPT_PATTERNS.items()
                if name not in allowed
                and any(
                    unicodedata.category(match.group())[0] in "LM"
                    for match in pattern.finditer(value)
                )
            )
            if scripts:
                yield finding("foreign_script", code, key, ", ".join(scripts))


def check_protected_terms(locales):
    english = locales.get("en", {})
    for key, english_value in english.items():
        source = PLACEHOLDER_FIELD.sub(" ", english_value)
        expected = {token for _, pattern in PROTECTED_PATTERNS for token in pattern.findall(source)}
        shortcuts = {match.group(): match.group(1) for match in SHORTCUT.finditer(source)}
        for code, strings in locales.items():
            if code == "en" or key not in strings:
                continue
            value = strings[key]
            # A whole token: "Air Calendario" or a glued prefix is a different word.
            missing = sorted(token for token in expected if not has_whole_token(value, token))
            missing += sorted(
                token
                for token, letter in shortcuts.items()
                if not re.search(
                    MODIFIER + r"\+\s*" + re.escape(letter) + r"(?![A-Za-z0-9])", value
                )
            )
            bad_keys = _non_latin_shortcut_keys(value)
            if missing or bad_keys:
                detail = f"missing {missing}" if missing else ""
                if bad_keys:
                    detail = (
                        detail + "; " if detail else ""
                    ) + f"non-Latin shortcut key {bad_keys}"
                yield finding("protected_terms", code, key, detail)


def _qt_names(code, index, months):
    from PyQt6.QtCore import QLocale

    locale = QLocale(code.replace("-", "_"))
    names = set()
    for fmt in (
        QLocale.FormatType.LongFormat,
        QLocale.FormatType.ShortFormat,
        QLocale.FormatType.NarrowFormat,
    ):
        if months:
            names.update((locale.monthName(index, fmt), locale.standaloneMonthName(index, fmt)))
        else:
            names.update((locale.dayName(index, fmt), locale.standaloneDayName(index, fmt)))
    return {_name_key(name) for name in names if name}


def _name_key(value):
    return value.strip().rstrip(".").replace(" ", "").casefold()


def check_calendar_names(locales):
    """Weekday and month name keys must match one of QLocale's forms for that language."""
    for code, strings in locales.items():
        for key, value in strings.items():
            for table, months in ((WEEKDAY_KEYS, False), (MONTH_KEYS, True)):
                if key in table and _name_key(value) not in _qt_names(code, table[key], months):
                    yield finding("calendar_names", code, key, f"{value!r} is not a QLocale name")


def _call_name(func):
    if isinstance(func, ast.Name):
        return func.id, None
    if isinstance(func, ast.Attribute):
        base = func.value
        base_name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", None)
        return func.attr, base_name
    return None, None


def _is_translation_call(node):
    name, base = _call_name(node.func)
    if isinstance(node.func, ast.Name):
        return name in T_FUNCTIONS
    return name == "get" and base == "i18n"


def _is_log_call(node):
    name, base = _call_name(node.func)
    return isinstance(node.func, ast.Attribute) and name in LOG_METHODS and base in LOGGER_NAMES


def _ui_sink(node):
    name, base = _call_name(node.func)
    if isinstance(node.func, ast.Attribute) and name in UI_SINK_METHODS:
        return name
    if name in UI_SINK_CLASSES:
        return name
    if name in MESSAGE_BOX_METHODS and base == "QMessageBox":
        return f"QMessageBox.{name}"
    return None


def _literal_label(value):
    return " ".join(value.split())[:60]


def _statement_strings(tree):
    """Docstrings and bare string statements are comments, not UI text."""
    return {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }


def check_hangul_source(trees):
    """Hangul literals outside t() defaults, logging and docstrings.

    ``hangul_source``: the literal reaches a UI call (setText, QLabel, QMessageBox,
    an f-string ...). Ratcheted. ``hangul_literal``: any other literal, such as text
    passed through helpers or data tables, parser grammar, search keywords and stored
    values. Report-only, so editing non-UI Korean data never fails the gate; the
    Korean-leak smoke test checks what dialogs actually show.
    """
    for relative, tree in trees:
        comments, counts = _statement_strings(tree), Counter()
        hits = []
        stack = [(tree, None)]
        while stack:
            node, context = stack.pop()
            if isinstance(node, ast.Call):
                if _is_translation_call(node) or _is_log_call(node):
                    continue
                sink = _ui_sink(node)
                if sink or not (context and context[0] == "ui"):
                    name = _call_name(node.func)[0] or "call"
                    context = ("ui", sink) if sink else ("call", name)
            elif isinstance(node, ast.JoinedStr) and not (context and context[0] == "ui"):
                context = ("ui", "f-string")
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in comments
                and HANGUL.search(node.value)
            ):
                kind, sink = context or ("literal", "literal")
                hits.append((node.lineno, node.value, kind, sink))
            stack.extend((child, context) for child in ast.iter_child_nodes(node))
        for line, value, kind, sink in sorted(hits, key=lambda hit: hit[0]):
            check = "hangul_source" if kind == "ui" else "hangul_literal"
            label = f"{relative}::{_literal_label(value)}"
            counts[check, label] += 1
            suffix = f"#{counts[check, label]}" if counts[check, label] > 1 else ""
            yield finding(check, "source", label + suffix, f"{relative}:{line} {sink}")


def _module_constants(tree):
    constants = {}
    for node in tree.body:
        targets, value = [], None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            for target in targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = value.value
    return constants


def _key_prefix(node, constants):
    """Leading literal text of an f-string or '+' key, with module constants inlined."""
    if isinstance(node, ast.JoinedStr):
        prefix = ""
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                prefix += part.value
            elif (
                isinstance(part, ast.FormattedValue)
                and isinstance(part.value, ast.Name)
                and part.value.id in constants
                and part.format_spec is None
                and part.conversion == -1
            ):
                prefix += constants[part.value.id]
            else:
                break
        return prefix or None
    if (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Add)
        and isinstance(node.left, ast.Constant)
        and isinstance(node.left.value, str)
    ):
        return node.left.value
    return None


def check_dynamic_t_calls(trees, english_keys):
    """Resolve non-literal t() keys where a constant or a literal prefix allows it."""
    known = set(english_keys)
    for key in english_keys:
        parts = key.split(".")
        known.update(".".join(parts[:index]) for index in range(1, len(parts)))
    stats = Counter()
    findings = []
    for relative, tree in trees:
        constants = _module_constants(tree)
        counts = Counter()
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _is_translation_call(node) and node.args):
                continue
            argument = node.args[0]
            name, _ = _call_name(node.func)
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                if name not in {"t", "_t"} and argument.value not in known:
                    findings.append(
                        finding(
                            "t_key_missing",
                            "source",
                            f"{relative}::{argument.value}",
                            f"{relative}:{node.lineno}",
                        )
                    )
                continue
            stats["total"] += 1
            expression = ast.unparse(argument)[:80]
            label = f"{relative}::{expression}"
            counts[label] += 1
            if counts[label] > 1:
                label += f"#{counts[label]}"
            where = f"{relative}:{node.lineno}"
            if isinstance(argument, ast.Name) and argument.id in constants:
                stats["resolved"] += 1
                if constants[argument.id] not in known:
                    findings.append(
                        finding(
                            "t_key_missing", "source", label, f"{where} -> {constants[argument.id]}"
                        )
                    )
                continue
            prefix = _key_prefix(argument, constants)
            if prefix and ("." in prefix or len(prefix) >= 3):
                stats["prefix"] += 1
                if not any(key.startswith(prefix) for key in english_keys):
                    findings.append(
                        finding(
                            "t_key_missing",
                            "source",
                            label,
                            f"{where}: no key starts with {prefix!r}",
                        )
                    )
                continue
            stats["unresolved"] += 1
            findings.append(finding("t_nonliteral", "source", label, where))
    return findings, dict(stats)


def _digest(value, length):
    return hashlib.sha1(value.encode("utf-8", errors="strict")).hexdigest()[:length]


def build_source_hashes(locales, previous=None, accept_drift=False):
    """Snapshot English hashes and per-locale value hashes for drift detection."""
    english = locales.get("en", {})
    codes = sorted(code for code in locales if code not in SOURCE_LOCALES)
    drift = (
        {}
        if accept_drift
        else {code: dict(keys) for code, keys in _drift_sources(locales, previous).items()}
    )
    return {
        "locales": codes,
        "keys": {
            key: _digest(value, 8)
            + " "
            + "".join(_digest(locales[code].get(key, ""), 2) for code in codes)
            for key, value in sorted(english.items())
        },
        "drift": {code: dict(sorted(keys.items())) for code, keys in sorted(drift.items()) if keys},
    }


def _drift_sources(locales, previous):
    """Return {locale: {key: English hash the unchanged translation was made from}}."""
    result = defaultdict(dict)
    if not previous or "keys" not in previous:
        return result
    english = locales.get("en", {})
    codes = previous.get("locales", [])
    stored_drift = previous.get("drift", {})
    for key, record in previous["keys"].items():
        if key not in english:
            continue
        english_hash, _, value_hashes = record.partition(" ")
        current_english = _digest(english[key], 8)
        for index, code in enumerate(codes):
            if code not in locales or key not in locales[code]:
                continue
            value = locales[code][key]
            source_hash = stored_drift.get(code, {}).get(key, english_hash)
            unchanged = _digest(value, 2) == value_hashes[index * 2 : index * 2 + 2]
            if source_hash != current_english and unchanged and value != english[key]:
                result[code][key] = source_hash
    return result


def check_source_drift(locales, previous):
    for code, keys in sorted(_drift_sources(locales, previous).items()):
        for key in sorted(keys):
            yield finding("source_drift", code, key, "English changed; translation did not")


def load_locales(root):
    locales = root / "locales"
    bundles, reports = {}, {}
    for path in sorted(locales.glob("*.json")):
        duplicates = []

        def pairs_hook(pairs, duplicate_keys=duplicates):
            data = {}
            for key, value in pairs:
                if key in data:
                    duplicate_keys.append(key)
                data[key] = value
            return data

        raw = path.read_text(encoding="utf-8", errors="strict")
        data = json.loads(raw, object_pairs_hook=pairs_hook)
        canonical = normalize_locale_data(data)
        bundles[path.stem] = canonical
        reports[path.stem] = {
            "duplicate_keys": duplicates,
            "canonical": raw == render_locale_json(canonical) + "\n",
        }
    return bundles, reports


def load_baseline(root=ROOT):
    path = root / BASELINE_RELATIVE
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8", errors="strict"))


def quality_findings(bundles, root=ROOT, parsed=None, baseline=None):
    """Return (findings, summary) for the review checks; nothing is written."""
    locales = {code: dict(string_entries(data)) for code, data in bundles.items()}
    english_keys = set(flatten_locale(bundles.get("en", {})))
    if parsed is None:
        parsed = parse_sources(root / "calendar_app")
    trees, _ = parsed
    if baseline is None:
        baseline = load_baseline(root)
    findings = []
    for check in (
        check_mojibake,
        check_stale_english,
        check_english_words,
        check_length_ratio,
        check_markup_parity,
        check_qt_formats,
        check_foreign_script,
        check_protected_terms,
        check_calendar_names,
    ):
        findings.extend(check(locales))
    findings.extend(check_hangul_source(trees))
    dynamic, dynamic_stats = check_dynamic_t_calls(trees, english_keys)
    findings.extend(dynamic)
    findings.extend(check_source_drift(locales, baseline.get("source_hashes")))
    pending = load_pending_review(root / PENDING_REVIEW_RELATIVE)
    summary = {
        "counts": dict(sorted(Counter(item["check"] for item in findings).items())),
        "dynamic_t_calls": dynamic_stats,
        "pending_review": sum(len(keys) for keys in pending.values()),
    }
    return findings, summary


def finding_ids(findings):
    ids = defaultdict(set)
    for item in findings:
        if item["check"] not in REPORT_ONLY_CHECKS:
            ids[item["check"]].add(f"{item['locale']}|{item['key']}")
    return ids


def new_findings(findings, baseline):
    """Findings absent from the baseline: the only ones a test should fail on."""
    accepted = {check: set(ids) for check, ids in baseline.get("findings", {}).items()}
    return [
        item
        for item in findings
        if item["check"] not in REPORT_ONLY_CHECKS
        and f"{item['locale']}|{item['key']}" not in accepted.get(item["check"], set())
    ]


def stale_baseline_entries(findings, baseline):
    """Accepted entries no longer found: fixed defects the baseline would let back in.

    Returns ["check: locale|key", ...]; ``--update-baseline`` drops them.
    """
    current = finding_ids(findings)
    return sorted(
        f"{check}: {entry}"
        for check, entries in baseline.get("findings", {}).items()
        for entry in entries
        if entry not in current.get(check, set())
    )


def build_baseline(root=ROOT, accept_drift=False):
    bundles, _ = load_locales(root)
    previous = load_baseline(root)
    findings, summary = quality_findings(bundles, root, baseline=previous)
    locales = {code: dict(string_entries(data)) for code, data in bundles.items()}
    return {
        "note": (
            "Accepted i18n audit findings. Regenerate with "
            "`python scripts/audit_i18n.py --update-baseline`; tests fail on new entries "
            "and on accepted entries that are no longer found."
        ),
        "counts": {
            check: count
            for check, count in summary["counts"].items()
            if check not in REPORT_ONLY_CHECKS
        },
        "findings": {check: sorted(ids) for check, ids in sorted(finding_ids(findings).items())},
        "source_hashes": build_source_hashes(
            locales, previous.get("source_hashes"), accept_drift=accept_drift
        ),
    }


def write_baseline(root=ROOT, accept_drift=False):
    baseline = build_baseline(root, accept_drift=accept_drift)
    path = root / BASELINE_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
        errors="strict",
    )
    return baseline


def format_findings(findings, limit=200):
    lines = [
        f"[{item['check']}] {item['locale']} {item['key']}: {item['detail']}"
        for item in findings[:limit]
    ]
    if len(findings) > limit:
        lines.append(f"... +{len(findings) - limit} more")
    return "\n".join(lines)


def audit(root=ROOT):
    bundles, reports = load_locales(root)
    base, english = bundles["ko"], bundles["en"]
    base_strings = dict(string_entries(base))
    english_flat, korean_flat = flatten_locale(english), flatten_locale(base)
    for code, data in bundles.items():
        report = reports[code]
        report["structure"] = compare_locale(base, data)
        report["hangul"] = []
        report["format_errors"] = []
        report["format_mismatch"] = []
        for key, value in string_entries(data):
            if code != "ko" and HANGUL.search(value):
                report["hangul"].append(key)
            try:
                signature = format_signature(value)
                reference = format_signature(base_strings.get(key, ""))
                if Counter(signature) != Counter(reference):
                    report["format_mismatch"].append(key)
            except ValueError:
                report["format_errors"].append(key)
        report["keys"] = len(flatten_locale(data))
        report["english_candidates"] = (
            untranslated_candidates(flatten_locale(data), english_flat, korean_flat)
            if code not in {"ko", "en"}
            else []
        )
    parsed = parse_sources(root / "calendar_app")
    gaps, parse_errors = source_key_gaps(root / "calendar_app", set(english_flat), parsed)
    errors = len(gaps) + len(parse_errors)
    for report in reports.values():
        errors += sum(len(values) for values in report["structure"].values())
        errors += sum(
            len(report[key])
            for key in ("duplicate_keys", "hangul", "format_errors", "format_mismatch")
        )
        errors += not report["canonical"]
    findings, summary = quality_findings(bundles, root, parsed)
    return {
        "locales": reports,
        "source_missing": gaps,
        "source_parse_errors": parse_errors,
        "errors": errors,
        "findings": findings,
        "finding_summary": summary,
        "note": "English matches require context review; technical terms can be intentional. Static source coverage includes literal t/_t calls only; findings are review records compared against the committed baseline.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="Save detailed audit results.")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help=f"Rewrite {BASELINE_RELATIVE.as_posix()} with the current findings.",
    )
    parser.add_argument(
        "--accept-drift",
        action="store_true",
        help="With --update-baseline, also accept translations made from older English text.",
    )
    parser.add_argument(
        "--check-baseline",
        action="store_true",
        help=(
            "Exit non-zero when findings absent from the baseline exist, or when accepted "
            "findings are no longer found (run --update-baseline to drop them)."
        ),
    )
    args = parser.parse_args(argv)
    if args.update_baseline:
        baseline = write_baseline(accept_drift=args.accept_drift)
        total = sum(baseline["counts"].values())
        print(f"Baseline written: {BASELINE_RELATIVE.as_posix()} ({total} findings)")
        for check, count in baseline["counts"].items():
            print(f"  {check}: {count}")
    report = audit()
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            errors="strict",
        )
    for code, data in report["locales"].items():
        print(
            f"{code}: {data['keys']} keys; English review candidates: {len(data['english_candidates'])}"
        )
    print(f"Source key gaps: {len(report['source_missing'])}; errors: {report['errors']}")
    summary = report["finding_summary"]
    print("Review findings: " + ", ".join(f"{k}={v}" for k, v in summary["counts"].items()))
    print(f"Non-literal t() calls: {summary['dynamic_t_calls']}")
    print(f"Pending translation review: {summary['pending_review']}")
    baseline = load_baseline()
    fresh = new_findings(report["findings"], baseline)
    print(f"New findings vs baseline: {len(fresh)}")
    if fresh:
        print(format_findings(fresh, limit=50))
    stale = stale_baseline_entries(report["findings"], baseline)
    print(f"Fixed findings still accepted in the baseline: {len(stale)}")
    for entry in stale[:50]:
        print(f"  {entry}")
    failed = report["errors"] != 0 or (args.check_baseline and bool(fresh or stale))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
