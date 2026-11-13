# -*- coding: utf-8 -*-
"""Compare locale files with a base locale, fill gaps and manage translation review.

Machine translation (``--auto-translate``) translates English text only: it masks
protected tokens, keeps short UI labels in English, leaves keys without English text
unfilled (``no_english``) and records every key it did not finish in the pending review
list, which lives outside ``locales/`` because every JSON file there is loaded as a
language. The optional per-locale glossary (``scripts/i18n_glossary.json``) feeds the
review export context and flags machine or imported translations that miss a term.
"""

import argparse
import bisect
import copy
import json
from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCALES_DIR = PROJECT_ROOT / "locales"
SOURCE_DIR = PROJECT_ROOT / "calendar_app"
PENDING_REVIEW_PATH = PROJECT_ROOT / "scripts" / "i18n_pending_review.json"
GLOSSARY_PATH = PROJECT_ROOT / "scripts" / "i18n_glossary.json"
REVIEW_NEIGHBOR_LIMIT = 5
PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
SUSPICIOUS_QMARK_RE = re.compile(r"\?{2,}\s*[\w\u3131-\uD79D\uFF41-\uFF5A\u4E00-\u9FFF]")
HANGUL_RE = re.compile(r"[\u3131-\u318E\uAC00-\uD7A3]")
# Text a translator must never change: format fields, markup, links, the product name,
# file names, shortcuts, date/time patterns and code tokens such as OAuth error codes.
# Latin-only lookarounds instead of \b: CJK letters count as \w, so "Ctrl+Sで" or
# "credentials.jsonを" would lose the token, and "Air Calendario" must not match.
PROTECTED_TOKEN_RE = re.compile(
    r"\{[^{}]*\}"
    r"|\(\*[^()]*\)"  # file dialog filter patterns: (*), (*.json), (*.png *.jpg)
    r"|</?[A-Za-z][^<>]*>"
    r"|https?://\S+"
    r"|(?<![A-Za-z])Air Calendar(?![A-Za-z])"
    r"|(?<![A-Za-z0-9_.-])[A-Za-z0-9_-]+"
    r"\.(?:json|webp|ics|png|gif|svg|jpe?g|wav|mp3|exe|lnk|ini|airlayout)(?![A-Za-z0-9_])"
    r"|(?<![A-Za-z0-9])(?:(?:Ctrl|Shift|Alt|Win|Cmd)\+)+"
    r"(?:F\d{1,2}|Enter|Space|Tab|Esc|Delete|Backspace|[A-Z0-9])(?![A-Za-z0-9])"
    r"|(?<![A-Za-z0-9_])(?:HH|hh):mm(?::ss)?(?![A-Za-z0-9_])"
    r"|(?<![A-Za-z0-9_])yyyy[-./]MM[-./]dd(?![A-Za-z0-9_])|%[A-Za-z]"
    r"|(?<![A-Za-z0-9_])[a-z]+(?:_[a-z]+)+(?![A-Za-z0-9_])"
)
# Scripts written without spaces between words: their letters may touch a protected
# token ("まずcredentials.jsonを開く"); letters of other scripts may not ("وclear_day.webp").
UNSPACED_LETTER_RE = re.compile(
    "[\u0e00-\u0e7f\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
)
# Reviewers may localize modifier names (Strg, Umschalt, Maj, Mayús) and key names, and may
# reorder date patterns; the key letter of a shortcut must stay the same.
SHORTCUT_TOKEN_RE = re.compile(r"(?:(?:Ctrl|Shift|Alt|Win|Cmd)\+)+(?:([A-Z0-9]|F\d{1,2})|\w+)$")
LOCALIZED_MODIFIER = r"(?:Ctrl|Strg|Shift|Umschalt|Maj|Mayús|Maiusc|Alt|Win|Cmd)"
MASK_RE = re.compile(r"\u27E6\s*(\d+)\s*\u27E7")
SENTENCE_END_RE = re.compile(r"[.!?\u3002\uFF01\uFF1F](?:\s|$)")
TRANSLATOR_CODES = {"zh": "zh-CN", "pt-BR": "pt"}

_en_data_cache = None


def _get_en_fallback_value(dotted_key):
    global _en_data_cache
    if _en_data_cache is None:
        try:
            en_path = LOCALES_DIR / "en.json"
            if en_path.exists():
                with en_path.open("r", encoding="utf-8", errors="strict") as fh:
                    _en_data_cache = flatten_locale(json.load(fh))
            else:
                _en_data_cache = {}
        except Exception:
            _en_data_cache = {}
    return _en_data_cache.get(dotted_key)


def load_locale(path: Path):
    with path.open("r", encoding="utf-8", errors="strict") as fh:
        return json.load(fh)


def flatten_locale(data, prefix=""):
    out = {}
    if isinstance(data, dict):
        for key, value in data.items():
            dotted = f"{prefix}.{key}" if prefix else str(key)
            out.update(flatten_locale(value, dotted))
    elif isinstance(data, list):
        out[prefix] = data
    else:
        out[prefix] = data
    return out


def unflatten_locale(flat):
    root = {}
    for dotted_key, value in flat.items():
        current = root
        parts = dotted_key.split(".")
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = value
    return root


def sort_locale_tree(data):
    if isinstance(data, dict):
        return {key: sort_locale_tree(data[key]) for key in sorted(data)}
    if isinstance(data, list):
        return [sort_locale_tree(item) for item in data]
    return data


def normalize_locale_data(data):
    return sort_locale_tree(unflatten_locale(flatten_locale(data)))


def render_locale_json(data, indent=0):
    pad = "  " * indent
    if isinstance(data, dict):
        if not data:
            return "{}"
        items = list(data.items())
        lines = ["{"]
        for idx, (key, value) in enumerate(items):
            comma = "," if idx < len(items) - 1 else ""
            lines.append(
                f"{'  ' * (indent + 1)}{json.dumps(key, ensure_ascii=False)}: "
                f"{render_locale_json(value, indent + 1)}{comma}"
            )
        lines.append(f"{pad}}}")
        return "\n".join(lines)
    if isinstance(data, list):
        if not data:
            return "[]"
        if all(not isinstance(item, (dict, list)) for item in data):
            return "[" + ", ".join(json.dumps(item, ensure_ascii=False) for item in data) + "]"
        lines = ["["]
        for idx, item in enumerate(data):
            comma = "," if idx < len(data) - 1 else ""
            lines.append(f"{'  ' * (indent + 1)}{render_locale_json(item, indent + 1)}{comma}")
        lines.append(f"{pad}]")
        return "\n".join(lines)
    return json.dumps(data, ensure_ascii=False)


def _uses_crlf(path):
    """True when the existing file ends its first line with CRLF."""
    with Path(path).open("rb") as fh:
        head = fh.read(65536)
    index = head.find(b"\n")
    return index > 0 and head[index - 1 : index] == b"\r"


def write_text_keeping_newlines(path, text):
    """Write LF ``text`` in the existing file's line ending; new files get LF.

    Text mode would write the platform ending, flipping CRLF working-tree files on one
    platform and LF files on the other.
    """
    path = Path(path)
    if path.exists() and _uses_crlf(path):
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8", errors="strict"))


def save_locale(path: Path, data):
    write_text_keeping_newlines(path, render_locale_json(normalize_locale_data(data)) + "\n")


def placeholders(value):
    if not isinstance(value, str):
        return set()
    return set(PLACEHOLDER_RE.findall(value))


def looks_broken_text(value):
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
    return bool(SUSPICIOUS_QMARK_RE.search(value))


def clone_json_value(value):
    return copy.deepcopy(value)


def protected_tokens(value):
    return PROTECTED_TOKEN_RE.findall(value) if isinstance(value, str) else []


def _is_word_char(char):
    return char.isalnum() or char == "_"


def has_whole_token(text, token):
    """True when ``token`` occurs in ``text`` as itself, not glued to other letters.

    A Latin letter or digit right after it ("Air Calendario") or a letter of a spaced
    script right before it ("وclear_day.webp") makes a different word.
    """
    for match in re.finditer(re.escape(token), text):
        before = text[match.start() - 1 : match.start()]
        after = text[match.end() : match.end() + 1]
        if _is_word_char(token[-1]) and after.isascii() and after and _is_word_char(after):
            continue
        if (
            _is_word_char(token[0])
            and before
            and _is_word_char(before)
            and not UNSPACED_LETTER_RE.match(before)
        ):
            continue
        return True
    return False


def is_short_label(value):
    """Up to three words without sentence punctuation: too little context for MT."""
    text = PROTECTED_TOKEN_RE.sub(" ", value).strip()
    text = re.sub(r"(?:\.\.\.|…)$", "", text).rstrip(":： ")
    words = re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", text)
    return len(words) <= 3 and not SENTENCE_END_RE.search(text)


def mask_protected(value):
    tokens = []

    def replace(match):
        tokens.append(match.group())
        return f"⟦{len(tokens) - 1}⟧"

    return PROTECTED_TOKEN_RE.sub(replace, value), tokens


def unmask_protected(value, tokens):
    """Restore masked tokens; None when any marker was lost, duplicated or invented."""
    found = [int(index) for index in MASK_RE.findall(value)]
    if sorted(found) != list(range(len(tokens))):
        return None
    return MASK_RE.sub(lambda match: tokens[int(match.group(1))], value)


def translate_value(translator, value, glossary_check=None):
    """Return (text, review_reason); the English text is kept whenever MT is unsafe.

    Only English text is sent: a Korean value means en.json lacks the key, and the
    caller leaves such keys for review instead of translating or copying them.
    ``glossary_check(english, translation)`` returns warnings; a translation that misses
    a glossary term is kept but marked ``glossary_check`` instead of ``machine_translated``.
    """
    if HANGUL_RE.search(value):
        return value, "no_english"
    if is_short_label(value):
        return value, "short_label"
    masked, tokens = mask_protected(value)
    try:
        translated = translator.translate(masked)
    except Exception:
        return value, "translation_failed"
    if not translated:
        return value, "translation_failed"
    # unmask_protected() proves every marker came back exactly once.
    restored = unmask_protected(translated, tokens)
    if restored is None:
        return value, "protected_lost"
    if HANGUL_RE.search(restored):
        return value, "translation_failed"
    if glossary_check is not None and glossary_check(value, restored):
        return restored, "glossary_check"
    return restored, "machine_translated"


def load_glossary(path=None):
    """Return {"terms": {id: {"en", "ko", "note"}}, "locales": {code: {id: text}}}.

    The glossary file is optional; without it every glossary feature is a no-op.
    """
    path = Path(GLOSSARY_PATH if path is None else path)
    if not path.exists():
        return {"terms": {}, "locales": {}}
    data = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    terms = {
        term_id: term
        for term_id, term in (data.get("terms") or {}).items()
        if isinstance(term, dict) and isinstance(term.get("en"), str) and term["en"].strip()
    }
    locales = {
        code: values
        for code, values in (data.get("locales") or {}).items()
        if isinstance(values, dict)
    }
    return {"terms": terms, "locales": locales}


def _glossary_options(value):
    values = value if isinstance(value, list) else [value]
    return [item for item in values if isinstance(item, str) and item.strip()]


def glossary_matches(english, code, glossary):
    """Glossary terms whose English word occurs in ``english`` as a whole word.

    Matching ignores case and protected tokens, so "Air Calendar" or "{save}" never
    match a "calendar" or "save" term. Each match carries this locale's translation.
    """
    if not isinstance(english, str) or not glossary or not glossary.get("terms"):
        return []
    text = PROTECTED_TOKEN_RE.sub(" ", english)
    locale_terms = glossary.get("locales", {}).get(code) or {}
    matches = []
    for term_id, term in sorted(glossary["terms"].items()):
        words = r"\s+".join(re.escape(word) for word in term["en"].split())
        if not re.search(rf"(?<!\w){words}(?!\w)", text, re.IGNORECASE):
            continue
        translation = locale_terms.get(term_id, term.get(code))
        matches.append(
            {
                "term": term_id,
                "en": term["en"],
                "ko": term.get("ko"),
                "translation": translation,
                "note": term.get("note", ""),
            }
        )
    return matches


def glossary_warnings(english, translation, code, glossary):
    """Glossary terms used in ``english`` whose locale wording is absent from ``translation``.

    A plain substring test, because inflection and compounds change the word ending;
    callers report these as warnings and never reject a translation for them.
    """
    if code == "en" or not isinstance(translation, str):
        return []
    folded = translation.casefold()
    warnings = []
    for match in glossary_matches(english, code, glossary):
        options = _glossary_options(match["translation"])
        if options and not any(option.casefold() in folded for option in options):
            warnings.append(
                f'glossary {match["term"]}: "{match["en"]}" should use "{" / ".join(options)}"'
            )
    return warnings


def load_pending_review(path=PENDING_REVIEW_PATH):
    """Return {locale: {key: reason}} for translations awaiting human review."""
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8", errors="strict"))


def save_pending_review(pending, path=PENDING_REVIEW_PATH):
    data = {code: dict(sorted(keys.items())) for code, keys in sorted(pending.items()) if keys}
    write_text_keeping_newlines(path, json.dumps(data, ensure_ascii=False, indent=1) + "\n")


def _needs_review(value, is_target_ko):
    return not is_target_ko and isinstance(value, str) and re.search(r"[^\W\d_]{2}", value)


def compare_locale(base, target, prefix=""):
    issues = {
        "missing": [],
        "extra": [],
        "type_mismatch": [],
        "placeholder_mismatch": [],
        "broken": [],
    }

    if isinstance(base, dict):
        if not isinstance(target, dict):
            issues["type_mismatch"].append(prefix or "<root>")
            return issues
        for key, base_value in base.items():
            path = f"{prefix}.{key}" if prefix else key
            if key not in target:
                issues["missing"].append(path)
                continue
            nested = compare_locale(base_value, target[key], path)
            merge_issues(issues, nested)
        for key in target.keys() - base.keys():
            path = f"{prefix}.{key}" if prefix else key
            issues["extra"].append(path)
        return issues

    if isinstance(base, list):
        if not isinstance(target, list):
            issues["type_mismatch"].append(prefix or "<root>")
            return issues
        for idx, (base_item, target_item) in enumerate(zip(base, target, strict=False)):
            path = f"{prefix}[{idx}]"
            nested = compare_locale(base_item, target_item, path)
            merge_issues(issues, nested)
        return issues

    if type(base) is not type(target):
        issues["type_mismatch"].append(prefix or "<root>")
        return issues

    if isinstance(base, str):
        if placeholders(base) != placeholders(target):
            issues["placeholder_mismatch"].append(prefix or "<root>")
        if looks_broken_text(target):
            issues["broken"].append(prefix or "<root>")
    return issues


def merge_issues(dest, src):
    for key, values in src.items():
        dest[key].extend(values)


def _record_untranslated(pending, dotted_key, value, is_target_ko):
    """Mark every non-string leaf copied without translation as pending review."""
    if pending is None:
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _record_untranslated(pending, f"{dotted_key}.{key}", item, is_target_ko)
    elif _needs_review(value, is_target_ko):
        pending[dotted_key] = "untranslated"


def fill_missing(
    base,
    target,
    translator=None,
    is_target_ko=False,
    prefix="",
    pending=None,
    copy_korean=True,
    glossary_check=None,
):
    """Fill absent or broken keys; ``pending`` ({key: reason}) collects keys to review.

    With ``copy_korean=False`` (auto-translate) a key without English text is left as
    it is and recorded as ``no_english``: Korean is never copied into another language.
    ``glossary_check`` is passed to translate_value() for every machine translation.
    """
    changed = False
    if not isinstance(base, dict) or not isinstance(target, dict):
        return changed
    for key, base_value in base.items():
        dotted_key = f"{prefix}.{key}" if prefix else key

        resolved_value = clone_json_value(base_value)
        if not is_target_ko and isinstance(base_value, str) and HANGUL_RE.search(base_value):
            en_val = _get_en_fallback_value(dotted_key)
            if en_val is not None:
                resolved_value = en_val
        no_english = (
            not is_target_ko
            and isinstance(resolved_value, str)
            and bool(HANGUL_RE.search(resolved_value))
        )

        is_broken = key in target and looks_broken_text(target[key])
        has_hangul_on_non_ko = (
            key in target
            and not is_target_ko
            and isinstance(target[key], str)
            and HANGUL_RE.search(target[key])
        )

        if key not in target or is_broken or has_hangul_on_non_ko:
            if no_english and not copy_korean:
                if pending is not None:
                    pending[dotted_key] = "no_english"
                continue
            if translator and isinstance(resolved_value, str):
                target[key], reason = translate_value(translator, resolved_value, glossary_check)
                if pending is not None and _needs_review(resolved_value, is_target_ko):
                    pending[dotted_key] = reason
            elif isinstance(resolved_value, dict) and (translator or not copy_korean):
                target[key] = {}
                fill_missing(
                    resolved_value,
                    target[key],
                    translator,
                    is_target_ko,
                    dotted_key,
                    pending,
                    copy_korean,
                    glossary_check,
                )
            else:
                target[key] = resolved_value
                _record_untranslated(pending, dotted_key, resolved_value, is_target_ko)
            changed = True
            continue

        if (
            translator
            and isinstance(resolved_value, str)
            and target[key] == resolved_value
            and resolved_value.strip()
            and not (resolved_value.startswith("{") and resolved_value.endswith("}"))
        ):
            translated, reason = translate_value(translator, resolved_value, glossary_check)
            if translated != resolved_value:
                target[key] = translated
                changed = True
            if pending is not None and _needs_review(resolved_value, is_target_ko):
                pending[dotted_key] = reason

        if (
            isinstance(base_value, dict)
            and isinstance(target[key], dict)
            and fill_missing(
                base_value,
                target[key],
                translator,
                is_target_ko,
                dotted_key,
                pending,
                copy_korean,
                glossary_check,
            )
        ):
            changed = True
    return changed


def repair_placeholder_mismatches(base, target, fallback, prefix=""):
    """Replace unsafe translated format strings with a placeholder-safe fallback."""
    changed = False
    if not isinstance(base, dict) or not isinstance(target, dict):
        return changed

    for key, base_value in base.items():
        dotted_key = f"{prefix}.{key}" if prefix else key
        if key not in target:
            continue
        target_value = target[key]

        if isinstance(base_value, dict) and isinstance(target_value, dict):
            fallback_value = fallback.get(key, {}) if isinstance(fallback, dict) else {}
            if repair_placeholder_mismatches(
                base_value,
                target_value,
                fallback_value,
                dotted_key,
            ):
                changed = True
            continue

        if not isinstance(base_value, str) or not isinstance(target_value, str):
            continue
        if placeholders(base_value) == placeholders(target_value):
            continue

        fallback_value = fallback.get(key) if isinstance(fallback, dict) else None
        if isinstance(fallback_value, str) and placeholders(fallback_value) == placeholders(
            base_value
        ):
            target[key] = fallback_value
            changed = True
            continue

        raise ValueError(
            f"No placeholder-safe fallback for {dotted_key}: "
            f"expected {sorted(placeholders(base_value))}"
        )
    return changed


def locale_paths(base_lang, target_langs):
    base_path = LOCALES_DIR / f"{base_lang}.json"
    if not base_path.exists():
        raise FileNotFoundError(f"Base locale not found: {base_path}")

    if target_langs:
        paths = [LOCALES_DIR / f"{lang}.json" for lang in target_langs]
    else:
        paths = sorted(
            path for path in LOCALES_DIR.glob("*.json") if path.name != f"{base_lang}.json"
        )
    missing_files = [str(path) for path in paths if not path.exists()]
    if missing_files:
        raise FileNotFoundError(f"Target locale not found: {', '.join(missing_files)}")
    return base_path, paths


def print_issue_block(label, items, limit):
    print(f"  {label}: {len(items)}")
    for item in items[:limit]:
        print(f"    - {item}")
    if len(items) > limit:
        print(f"    ... +{len(items) - limit} more")


def process_locale(
    base_data,
    target_path,
    fill,
    limit,
    auto_translate=False,
    base_lang="ko",
    repair_placeholders=False,
    fallback_data=None,
    pending=None,
    glossary=None,
):
    target_data = normalize_locale_data(load_locale(target_path))

    is_target_ko = target_path.name == "ko.json"
    translator_target = TRANSLATOR_CODES.get(target_path.stem, target_path.stem)
    translator = None
    # Only English text is sent (keys without English stay pending as no_english), so
    # English is the source language and en.json itself is never machine-translated.
    if fill and auto_translate and not is_target_ko and translator_target != "en":
        try:
            from deep_translator import GoogleTranslator

            translator = GoogleTranslator(source="en", target=translator_target)
        except ImportError:
            print("  Warning: deep_translator is not installed. Auto-translate skipped.")
        except Exception:
            pass

    glossary_check = None
    if translator is not None:
        locale_glossary = load_glossary() if glossary is None else glossary

        def glossary_check(english, translation):
            return glossary_warnings(english, translation, target_path.stem, locale_glossary)

    changed = False
    if repair_placeholders:
        changed = repair_placeholder_mismatches(
            base_data,
            target_data,
            fallback_data or {},
        )
    if fill and fill_missing(
        base_data,
        target_data,
        translator,
        is_target_ko,
        pending=pending,
        copy_korean=not auto_translate,
        glossary_check=glossary_check,
    ):
        changed = True
    if changed:
        save_locale(target_path, target_data)
    issues = compare_locale(base_data, target_data)
    print(target_path.name)
    print_issue_block("missing", issues["missing"], limit)
    print_issue_block("extra", issues["extra"], limit)
    print_issue_block("type_mismatch", issues["type_mismatch"], limit)
    print_issue_block("placeholder_mismatch", issues["placeholder_mismatch"], limit)
    print_issue_block("broken", issues["broken"], limit)
    if changed:
        print("  updated: yes")
    else:
        print("  updated: no")
    return issues, changed


def source_locations(keys, source_dir=SOURCE_DIR):
    """Map each key to the code lines that spell it as a string literal."""
    wanted = set(keys)
    found = {key: [] for key in wanted}
    literal = re.compile(r"[\"']([A-Za-z0-9_.\-]+)[\"']")
    for path in sorted(Path(source_dir).rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="strict")
        relative = path.relative_to(Path(source_dir).parent).as_posix()
        for number, line in enumerate(text.splitlines(), start=1):
            for match in literal.finditer(line):
                if match.group(1) in wanted:
                    found[match.group(1)].append(f"{relative}:{number}")
    return found


def screen_hint(key, locations, limit=3):
    """Name the source files that use a key, as a hint of the screen it appears on."""
    names = list(dict.fromkeys(Path(location.rsplit(":", 1)[0]).name for location in locations))
    if not names:
        return f"{key.split('.')[0]} (no literal key in code)"
    more = f" (+{len(names) - limit} more)" if len(names) > limit else ""
    return ", ".join(names[:limit]) + more


def sibling_index(keys):
    """Map each parent key to the sorted child keys under it."""
    siblings = {}
    for key in sorted(keys):
        siblings.setdefault(key.rpartition(".")[0], []).append(key)
    return siblings


def neighbor_keys(key, siblings, limit=REVIEW_NEIGHBOR_LIMIT):
    """Up to ``limit`` sibling keys nearest to ``key`` in sorted order, itself excluded."""
    others = [item for item in siblings.get(key.rpartition(".")[0], []) if item != key]
    start = max(0, min(bisect.bisect_left(others, key) - limit // 2, len(others) - limit))
    return others[start : start + limit]


def export_review(
    output_path,
    locales=None,
    locales_dir=LOCALES_DIR,
    pending_path=PENDING_REVIEW_PATH,
    source_dir=SOURCE_DIR,
    glossary_path=None,
):
    """Write pending keys with en/ko text, code locations and context for review.

    ``context`` holds a screen hint from the code locations, nearby sibling keys with
    their English and current text, and the glossary terms the English text uses.
    """
    pending = load_pending_review(pending_path)
    english = flatten_locale(load_locale(Path(locales_dir) / "en.json"))
    korean = flatten_locale(load_locale(Path(locales_dir) / "ko.json"))
    glossary = load_glossary(glossary_path)
    keys = {key for code, items in pending.items() for key in items}
    locations = source_locations(keys, source_dir)
    siblings = sibling_index(
        key for key, value in {**korean, **english}.items() if isinstance(value, str)
    )
    entries = []
    for code in sorted(pending):
        if locales and code not in locales:
            continue
        current = flatten_locale(load_locale(Path(locales_dir) / f"{code}.json"))
        for key, reason in sorted(pending[code].items()):
            if key not in english and key not in korean:
                continue
            entries.append(
                {
                    "locale": code,
                    "key": key,
                    "reason": reason,
                    # None for no_english keys: the English text is written first.
                    "en": english.get(key),
                    "ko": korean.get(key),
                    "current": current.get(key),
                    "locations": locations.get(key, []),
                    "context": {
                        "screen": screen_hint(key, locations.get(key, [])),
                        "neighbors": [
                            {"key": item, "en": english.get(item), "current": current.get(item)}
                            for item in neighbor_keys(key, siblings)
                        ],
                        "glossary": glossary_matches(english.get(key), code, glossary),
                    },
                    "translation": "",
                }
            )
    Path(output_path).write_text(
        json.dumps(entries, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
        errors="strict",
    )
    return entries


def review_problem(english, translation, code):
    """Return why a reviewed translation cannot be applied, or None."""
    if not isinstance(translation, str) or not translation.strip():
        return "empty translation"
    if placeholders(english) != placeholders(translation):
        return (
            f"placeholders {sorted(placeholders(translation))} != {sorted(placeholders(english))}"
        )
    missing = []
    for token in sorted(set(protected_tokens(english))):
        if has_whole_token(translation, token):
            continue
        shortcut = SHORTCUT_TOKEN_RE.match(token)
        if token.startswith("yyyy") or (shortcut and not shortcut.group(1)):
            continue
        if shortcut and re.search(
            LOCALIZED_MODIFIER + r"\+\s*" + re.escape(shortcut.group(1)) + r"(?![A-Za-z0-9])",
            translation,
        ):
            continue
        missing.append(token)
    if missing:
        return f"protected terms changed: {missing}"
    if code != "ko" and HANGUL_RE.search(translation):
        return "Hangul in a non-Korean translation"
    if looks_broken_text(translation):
        return "broken text"
    return None


def import_review(
    input_path,
    locales_dir=LOCALES_DIR,
    pending_path=PENDING_REVIEW_PATH,
    review_status=None,
    glossary_path=None,
):
    """Apply reviewed translations; returns (applied, rejected) entry lists.

    Without ``review_status`` an applied key leaves the pending list (a person reviewed
    it). With a status such as ``machine_translated`` the value is written but the key
    stays pending under that status, so machine or AI drafts still get human review.
    Each applied entry carries ``warnings`` for glossary terms its translation misses.
    """
    # A hand-edited file is external input: undecodable bytes become U+FFFD, which
    # review_problem() rejects as broken text instead of writing it to a locale.
    entries = json.loads(Path(input_path).read_text(encoding="utf-8", errors="replace"))
    pending = load_pending_review(pending_path)
    english = flatten_locale(load_locale(Path(locales_dir) / "en.json"))
    korean = flatten_locale(load_locale(Path(locales_dir) / "ko.json"))
    glossary = load_glossary(glossary_path)
    applied, rejected, updates = [], [], {}
    for entry in entries:
        code, key = entry.get("locale"), entry.get("key")
        translation = entry.get("translation")
        if not translation:
            continue
        path = Path(locales_dir) / f"{code}.json"
        # English text for a no_english key is checked against the Korean source;
        # other languages wait until en.json has the key.
        reference = english.get(key, korean.get(key) if code == "en" else None)
        if reference is None or not path.exists():
            rejected.append({**entry, "problem": "unknown locale or key, or no English text yet"})
            continue
        problem = review_problem(reference, translation, code)
        if problem:
            rejected.append({**entry, "problem": problem})
            continue
        updates.setdefault(code, {})[key] = translation
        warnings = glossary_warnings(english.get(key), translation, code, glossary)
        applied.append({**entry, "warnings": warnings})
    for code, values in updates.items():
        path = Path(locales_dir) / f"{code}.json"
        flat = flatten_locale(normalize_locale_data(load_locale(path)))
        flat.update(values)
        save_locale(path, unflatten_locale(flat))
        for key in values:
            if review_status:
                pending.setdefault(code, {})[key] = review_status
            else:
                pending.get(code, {}).pop(key, None)
    if updates:
        save_pending_review(pending, pending_path)
    return applied, rejected


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compare locale files against a base locale and optionally fill missing keys."
    )
    parser.add_argument("--base", default="ko", help="Base locale file name without .json")
    parser.add_argument(
        "--locales",
        nargs="*",
        default=None,
        help="Target locale names without .json. Default: all locales except base.",
    )
    parser.add_argument(
        "--fill-missing",
        action="store_true",
        help="Copy missing keys from the base locale into target locale files.",
    )
    parser.add_argument(
        "--auto-translate",
        action="store_true",
        help="Automatically translate filled missing keys using deep_translator (requires pip install deep-translator)",
    )
    parser.add_argument(
        "--repair-placeholders",
        action="store_true",
        help="Replace placeholder-mismatched strings with the matching English fallback.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of issue paths to print per category.",
    )
    parser.add_argument(
        "--export-review",
        type=Path,
        help="Write pending review keys (en, ko, current text, code locations) to a JSON file.",
    )
    parser.add_argument(
        "--import-review",
        type=Path,
        help="Apply the 'translation' values of a reviewed export after validation.",
    )
    parser.add_argument(
        "--review-status",
        metavar="STATUS",
        help=(
            "With --import-review: keep applied keys in the pending review list under STATUS "
            "(e.g. machine_translated for machine or AI drafts) instead of removing them."
        ),
    )
    args = parser.parse_args(argv)
    if args.review_status and not args.import_review:
        parser.error("--review-status requires --import-review")

    if args.export_review:
        entries = export_review(args.export_review, args.locales)
        print(f"Exported {len(entries)} pending review entries to {args.export_review}")
        return 0
    if args.import_review:
        applied, rejected = import_review(args.import_review, review_status=args.review_status)
        warned = [entry for entry in applied if entry.get("warnings")]
        print(
            f"Applied {len(applied)} reviewed translations; rejected {len(rejected)}; "
            f"glossary warnings {len(warned)}."
        )
        if args.review_status and applied:
            print(f"  Applied keys stay pending review as {args.review_status}.")
        for entry in rejected[: args.limit]:
            print(f"  - {entry.get('locale')} {entry.get('key')}: {entry['problem']}")
        for entry in warned[: args.limit]:
            for warning in entry["warnings"]:
                print(f"  ! {entry.get('locale')} {entry.get('key')}: {warning}")
        return 1 if rejected else 0

    base_path, target_paths = locale_paths(args.base, args.locales)
    base_data = normalize_locale_data(load_locale(base_path))
    fallback_data = normalize_locale_data(load_locale(LOCALES_DIR / "en.json"))
    pending = load_pending_review()
    glossary = load_glossary() if args.fill_missing and args.auto_translate else None

    def pending_snapshot():
        return json.dumps({code: keys for code, keys in pending.items() if keys}, sort_keys=True)

    pending_before = pending_snapshot()

    has_issues = False
    changed_any = False
    for target_path in target_paths:
        issues, changed = process_locale(
            base_data,
            target_path,
            args.fill_missing,
            args.limit,
            args.auto_translate,
            args.base,
            args.repair_placeholders,
            fallback_data,
            pending.setdefault(target_path.stem, {}),
            glossary,
        )
        changed_any = changed_any or changed
        has_issues = has_issues or any(issues.values())
    if pending_snapshot() != pending_before:
        save_pending_review(pending)
        count = sum(len(keys) for keys in pending.values())
        print(f"Pending translation review: {count} keys ({PENDING_REVIEW_PATH.name})")

    if changed_any:
        print("Completed with locale updates.")
    elif has_issues:
        print("Completed with issues detected.")
    else:
        print("All locale files match the base structure.")

    return 1 if has_issues else 0


if __name__ == "__main__":
    sys.exit(main())
