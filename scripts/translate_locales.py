"""Batch-translate untranslated strings in all locale JSON files using Claude API.

Usage:
    set ANTHROPIC_API_KEY=sk-ant-...
    python scripts/translate_locales.py [--lang ru] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

try:
    import anthropic
except ImportError:
    print("pip install anthropic", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
LOCALES_DIR = ROOT / "locales"

LANG_NAMES = {
    "ar": "Arabic",
    "de": "German",
    "es": "Spanish",
    "fr": "French",
    "hi": "Hindi",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "nl": "Dutch",
    "pt": "Portuguese (Brazilian)",
    "ru": "Russian",
    "th": "Thai",
    "tr": "Turkish",
    "vi": "Vietnamese",
    "zh": "Chinese (Simplified)",
    "zh-CN": "Chinese (Simplified)",
    "zh-TW": "Chinese (Traditional)",
}

INTENTIONAL_EN = {
    "alarm_popup.test_alarm_btn",
    "alarm_popup.test_sync_error_btn",
    "dialog.theme.preview.app_name",
    "dialog.token_editor.preview.btn_danger",
    "dialog.token_editor.preview.btn_disabled",
    "dialog.token_editor.preview.btn_ghost",
    "dialog.token_editor.preview.btn_primary",
    "dialog.token_editor.preview.btn_secondary",
    "dialog.token_editor.preview.btn_success",
    "gcal_settings.ics_url_label",
    "gcal_settings.ics_url_placeholder",
    "gcal_settings.type_gcal",
    "panel.deadline_label",
    "widget.dday.default_name",
}

CHUNK_SIZE = 60


def flatten(d: dict, prefix: str = "") -> dict:
    items: dict = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            items.update(flatten(v, key))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                items[f"{key}[{i}]"] = item
        else:
            items[key] = v
    return items


def set_nested(d: dict, dotted_key: str, value: str) -> None:
    """Set value in nested dict using dotted key (with list index support)."""
    import re

    parts = re.split(r"\.(?![^\[]*\])", dotted_key)
    current = d
    for _, part in enumerate(parts[:-1]):
        m = re.match(r"^(.+)\[(\d+)\]$", part)
        if m:
            name, idx = m.group(1), int(m.group(2))
            lst = current.setdefault(name, [])
            while len(lst) <= idx:
                lst.append({})
            current = lst[idx]
        else:
            current = current.setdefault(part, {})
    last = parts[-1]
    m = re.match(r"^(.+)\[(\d+)\]$", last)
    if m:
        name, idx = m.group(1), int(m.group(2))
        lst = current.setdefault(name, [])
        while len(lst) <= idx:
            lst.append("")
        lst[idx] = value
    else:
        current[last] = value


def translate_chunk(
    client: anthropic.Anthropic, lang_name: str, chunk: dict[str, str]
) -> dict[str, str]:
    """Translate a chunk of {key: english_value} -> {key: translated_value}."""
    lines = "\n".join(f"{k}\t{v}" for k, v in chunk.items())
    prompt = f"""You are a professional UI translator for a desktop calendar app called "Dark Calendar".
Translate the following UI strings from English to {lang_name}.

Rules:
- Keep emoji exactly as-is at the start of strings
- Keep {{placeholders}} like {{APP_VERSION}}, {{days}}, {{target}}, {{name}} exactly unchanged
- Keep \\n newlines as-is
- Translate only the text, not the keys (left side of tab)
- Keep translations concise — these are menu items and button labels
- Do NOT add explanations or notes
- Output ONLY the translated lines in the same TSV format: key TAB translated_value
- One line per entry, no extra blank lines

Strings to translate:
{lines}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    result: dict[str, str] = {}
    for line in response.content[0].text.strip().splitlines():
        if "\t" in line:
            k, _, v = line.partition("\t")
            k = k.strip()
            if k in chunk:
                result[k] = v.strip()
    return result


def process_locale(lang: str, dry_run: bool, client: anthropic.Anthropic) -> int:
    path = LOCALES_DIR / f"{lang}.json"
    if not path.exists():
        print(f"[skip] {lang}: file not found")
        return 0

    en_data = json.loads((LOCALES_DIR / "en.json").read_text(encoding="utf-8", errors="strict"))
    lang_data = json.loads(path.read_text(encoding="utf-8", errors="strict"))

    en_flat = flatten(en_data)
    lang_flat = flatten(lang_data)

    untranslated = {
        k: v
        for k, v in lang_flat.items()
        if k in en_flat
        and v == en_flat[k]
        and isinstance(v, str)
        and not v.startswith("{")
        and not k.startswith("meta")
        and len(v) > 2
        and k not in INTENTIONAL_EN
    }

    if not untranslated:
        print(f"[ok] {lang}: nothing to translate")
        return 0

    lang_name = LANG_NAMES.get(lang, lang)
    print(f"[{lang}] {lang_name}: {len(untranslated)} strings to translate...")

    if dry_run:
        for k, v in list(untranslated.items())[:5]:
            print(f"  {k}: {repr(v)[:60]}")
        if len(untranslated) > 5:
            print(f"  ... and {len(untranslated) - 5} more")
        return len(untranslated)

    keys = list(untranslated.keys())
    translated_count = 0
    for i in range(0, len(keys), CHUNK_SIZE):
        chunk_keys = keys[i : i + CHUNK_SIZE]
        chunk = {k: untranslated[k] for k in chunk_keys}
        print(
            f"  chunk {i // CHUNK_SIZE + 1}/{(len(keys) + CHUNK_SIZE - 1) // CHUNK_SIZE} ({len(chunk)} strings)..."
        )
        for attempt in range(3):
            try:
                result = translate_chunk(client, lang_name, chunk)
                for k, translated in result.items():
                    set_nested(lang_data, k, translated)
                    translated_count += 1
                break
            except Exception as exc:
                print(f"  [warn] attempt {attempt + 1} failed: {exc}")
                time.sleep(2**attempt)
        time.sleep(0.3)

    path.write_text(
        json.dumps(lang_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        errors="strict",
    )
    print(f"  [done] {translated_count}/{len(untranslated)} translated, saved {path.name}")
    return translated_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Translate untranslated locale strings using Claude API."
    )
    parser.add_argument("--lang", help="Specific language code (default: all)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be translated without changing files",
    )
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print("Error: set ANTHROPIC_API_KEY env var first", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key or "dummy")

    langs = [args.lang] if args.lang else sorted(LANG_NAMES.keys())

    total = 0
    for lang in langs:
        total += process_locale(lang, args.dry_run, client)

    print(f"\n[summary] total translated: {total}")


if __name__ == "__main__":
    main()
