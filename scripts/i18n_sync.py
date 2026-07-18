import argparse
import copy
import json
from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCALES_DIR = PROJECT_ROOT / "locales"
PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
SUSPICIOUS_QMARK_RE = re.compile(r"\?{2,}\s*[\w\u3131-\uD79D\uFF41-\uFF5A\u4E00-\u9FFF]")
HANGUL_RE = re.compile(r"[\u3131-\u318E\uAC00-\uD7A3]")

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


def save_locale(path: Path, data):
    with path.open("w", encoding="utf-8", errors="strict") as fh:
        fh.write(render_locale_json(normalize_locale_data(data)))
        fh.write("\n")


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


def fill_missing(base, target, translator=None, is_target_ko=False, prefix=""):
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

        is_broken = key in target and looks_broken_text(target[key])
        has_hangul_on_non_ko = (
            key in target
            and not is_target_ko
            and isinstance(target[key], str)
            and HANGUL_RE.search(target[key])
        )

        if key not in target or is_broken or has_hangul_on_non_ko:
            if translator and isinstance(resolved_value, str):
                try:
                    translated = translator.translate(resolved_value)
                    target[key] = translated if translated else resolved_value
                except Exception:
                    target[key] = resolved_value
            elif translator and isinstance(resolved_value, dict):
                target[key] = {}
                fill_missing(resolved_value, target[key], translator, is_target_ko, dotted_key)
            else:
                target[key] = resolved_value
            changed = True
            continue

        if (
            translator
            and isinstance(resolved_value, str)
            and target[key] == resolved_value
            and resolved_value.strip()
            and not (resolved_value.startswith("{") and resolved_value.endswith("}"))
        ):
            try:
                translated = translator.translate(resolved_value)
                if translated and translated != resolved_value:
                    target[key] = translated
                    changed = True
            except Exception:
                pass

        if (
            isinstance(base_value, dict)
            and isinstance(target[key], dict)
            and fill_missing(base_value, target[key], translator, is_target_ko, dotted_key)
        ):
            changed = True
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


def process_locale(base_data, target_path, fill, limit, auto_translate=False, base_lang="ko"):
    target_data = normalize_locale_data(load_locale(target_path))

    translator = None
    if fill and auto_translate:
        try:
            from deep_translator import GoogleTranslator

            lang_code = target_path.stem
            target_lang = "pt" if lang_code == "pt-BR" else lang_code
            translator = GoogleTranslator(source=base_lang, target=target_lang)
        except ImportError:
            print("  Warning: deep_translator is not installed. Auto-translate skipped.")
        except Exception:
            pass

    is_target_ko = target_path.name == "ko.json"
    changed = fill_missing(base_data, target_data, translator, is_target_ko) if fill else False
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
        "--limit",
        type=int,
        default=20,
        help="Maximum number of issue paths to print per category.",
    )
    args = parser.parse_args(argv)

    base_path, target_paths = locale_paths(args.base, args.locales)
    base_data = normalize_locale_data(load_locale(base_path))

    has_issues = False
    changed_any = False
    for target_path in target_paths:
        issues, changed = process_locale(
            base_data, target_path, args.fill_missing, args.limit, args.auto_translate, args.base
        )
        changed_any = changed_any or changed
        has_issues = has_issues or any(issues.values())

    if changed_any:
        print("Completed with locale updates.")
    elif has_issues:
        print("Completed with issues detected.")
    else:
        print("All locale files match the base structure.")

    return 1 if has_issues else 0


if __name__ == "__main__":
    sys.exit(main())
