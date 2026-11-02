# -*- coding: utf-8 -*-
"""Read-only bundle/source audit. English matches are review candidates, not errors."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import re
from string import Formatter

try:
    from scripts.i18n_sync import (
        compare_locale,
        flatten_locale,
        normalize_locale_data,
        render_locale_json,
    )
except ModuleNotFoundError:
    from i18n_sync import (
        compare_locale,
        flatten_locale,
        normalize_locale_data,
        render_locale_json,
    )

ROOT = Path(__file__).resolve().parents[1]
HANGUL = re.compile(r"[\u3131-\u318e\uac00-\ud7a3]")


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


def source_key_gaps(source_dir, keys):
    gaps = {}
    parse_errors = []
    for path in sorted(source_dir.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="strict"))
        except (SyntaxError, UnicodeError) as exc:
            parse_errors.append({"file": str(path), "error": str(exc)})
            continue
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
                gaps.setdefault(key, []).append(
                    f"{path.relative_to(source_dir).as_posix()}:{node.lineno}"
                )
    return gaps, parse_errors


def audit(root=ROOT):
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
    gaps, parse_errors = source_key_gaps(root / "calendar_app", set(english_flat))
    errors = len(gaps) + len(parse_errors)
    for report in reports.values():
        errors += sum(len(values) for values in report["structure"].values())
        errors += sum(
            len(report[key])
            for key in ("duplicate_keys", "hangul", "format_errors", "format_mismatch")
        )
        errors += not report["canonical"]
    return {
        "locales": reports,
        "source_missing": gaps,
        "source_parse_errors": parse_errors,
        "errors": errors,
        "note": "English matches require context review; technical terms can be intentional. Static source coverage includes literal t/_t calls only.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="Save detailed audit results.")
    args = parser.parse_args(argv)
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
    return int(report["errors"] != 0)


if __name__ == "__main__":
    raise SystemExit(main())
