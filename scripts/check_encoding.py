#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
LOCALES_DIR = ROOT / "locales"
CODE_DIR = ROOT / "calendar_app"

SUSPICIOUS_QMARK_RE = re.compile(r"\?{2,}\s*[\w가-힣ぁ-んァ-ヶ一-龯]")
MOJIBAKE_RE = re.compile(r"[꾩뿉몃뒗釉먮폁쎾퐲熬곣뫖利당춯]{3,}")


def looks_broken_text(value: object) -> bool:
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped:
        return False
    if "\ufffd" in value:
        return True
    if all(ch in {"?", " ", "\t", "\n"} for ch in stripped):
        return True
    return bool(SUSPICIOUS_QMARK_RE.search(value))


def collect_broken_json(data: object, prefix: str = "") -> list[str]:
    broken: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            dotted = f"{prefix}.{key}" if prefix else str(key)
            broken.extend(collect_broken_json(value, dotted))
    elif isinstance(data, list):
        for idx, value in enumerate(data):
            dotted = f"{prefix}[{idx}]"
            broken.extend(collect_broken_json(value, dotted))
    elif looks_broken_text(data):
        broken.append(prefix)
    return broken


def scan_locales() -> list[str]:
    issues: list[str] = []
    for path in sorted(LOCALES_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="strict"))
        except Exception as exc:
            issues.append(f"{path.relative_to(ROOT)}: invalid JSON or encoding error: {exc}")
            continue
        broken = collect_broken_json(data)
        for key in broken:
            issues.append(f"{path.relative_to(ROOT)}: suspicious locale string at {key}")
    return issues


def scan_python_sources() -> list[str]:
    issues: list[str] = []
    for path in sorted(CODE_DIR.rglob("*.py")):
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            issues.append(f"{path.relative_to(ROOT)}: UTF-8 decode failed: {exc}")
            continue
        if "\ufffd" in text:
            issues.append(f"{path.relative_to(ROOT)}: contains replacement character U+FFFD")
        for lineno, line in enumerate(text.splitlines(), 1):
            if MOJIBAKE_RE.search(line):
                issues.append(
                    f"{path.relative_to(ROOT)}:{lineno}: suspicious mojibake comment/text"
                )
    return issues


def main() -> int:
    issues = []
    issues.extend(scan_locales())
    issues.extend(scan_python_sources())
    if issues:
        for issue in issues:
            print(issue)
        print(f"Found {len(issues)} encoding issue(s).", file=sys.stderr)
        return 1
    print("Encoding check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
