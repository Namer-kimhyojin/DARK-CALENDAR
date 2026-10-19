# -*- coding: utf-8 -*-
"""Record logical changes and keep development version surfaces consistent."""

from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

CORE = ("calendar_app/app_metadata.py", "pyproject.toml", "AppxManifest.xml", "version_info.txt")
HISTORY = "version-history.json"
REPORT = "docs/maintenance/version-history.md"
TARGETS = {*CORE, HISTORY, REPORT}


def text(path):
    return path.read_text(encoding="utf-8", errors="strict")


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8", errors="strict")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def version_number(version):
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]\.[0-9]\.[0-9]", version):
        raise ValueError("Version must have three single-digit components")
    major, minor, patch = map(int, version.split("."))
    return major * 100 + minor * 10 + patch


def validate_override(version, published_version):
    if version_number(version) <= version_number(published_version):
        raise ValueError("Override version must be higher than the verified published version")


def next_version(current, kind):
    value = version_number(current)
    value = value + 1 if kind == "change" else (value // 10 + 1) * 10
    if value > 999:
        raise ValueError("Single-digit version space exhausted; a new numbering policy is required")
    return f"{value // 100}.{value // 10 % 10}.{value % 10}"


def replace_one(pattern, replacement, source):
    result, count = re.subn(pattern, replacement, source, flags=re.M)
    if count != 1:
        raise ValueError(f"Expected exactly one version field: {pattern}")
    return result


def current_version(root):
    match = re.search(r'^APP_VERSION = "([^"]+)"$', text(root / CORE[0]), re.M)
    if not match:
        raise ValueError("APP_VERSION missing")
    version = match[1]
    if not re.fullmatch(r"[0-9]\.[0-9]\.[0-9]", version):
        raise ValueError("Invalid development version")
    return version


def core_updates(root, version, date):
    metadata = replace_one(
        r'^APP_VERSION = "[^"]+"$', f'APP_VERSION = "{version}"', text(root / CORE[0])
    )
    metadata = replace_one(
        r'^APP_RELEASE_DATE = "[^"]+"$', f'APP_RELEASE_DATE = "{date}"', metadata
    )
    metadata = replace_one(
        r'^APP_RELEASE_CHANNEL = "[^"]+"$', 'APP_RELEASE_CHANNEL = "Dev"', metadata
    )
    project = replace_one(r'^version = "[^"]+"$', f'version = "{version}"', text(root / CORE[1]))
    manifest = replace_one(
        r'(<Identity\b[^>]*\bVersion=")[^"]+("[^>]*>)', rf"\g<1>{version}.0\2", text(root / CORE[2])
    )
    pe = text(root / CORE[3])
    number_tuple = "(" + ", ".join([*version.split("."), "0"]) + ")"
    for name in ("filevers", "prodvers"):
        pe = replace_one(rf"({name}\s*=\s*)\([^)]+\)", rf"\g<1>{number_tuple}", pe)
    for name in ("FileVersion", "ProductVersion"):
        pe = replace_one(rf"(StringStruct\('{name}',\s*')[^']+('\))", rf"\g<1>{version}.0\2", pe)
    return {
        name: value.encode("utf-8", errors="strict")
        for name, value in zip(CORE, (metadata, project, manifest, pe), strict=True)
    }


def verify(root, ledger):
    version = current_version(root)
    if ledger["current_version"] != version:
        raise ValueError("Version history and APP_VERSION disagree; do not edit versions manually")
    previous = ledger["baseline_version"]
    ids = set()
    for event in ledger["events"]:
        if (
            event["id"] in ids
            or event["kind"] not in {"change", "module", "store", "override"}
            or event["previous_version"] != previous
        ):
            raise ValueError("Version history chain is inconsistent")
        if event["kind"] == "override":
            validate_override(event["version"], event.get("published_version"))
        elif event["version"] != next_version(previous, event["kind"]):
            raise ValueError("Version history chain is inconsistent")
        ids.add(event["id"])
        previous = event["version"]
    if previous != version:
        raise ValueError("Version history endpoint is inconsistent")
    checks = (
        (CORE[1], rf'^version = "{re.escape(version)}"$'),
        (CORE[2], rf'<Identity\b[^>]*\bVersion="{re.escape(version)}\.0"'),
        (CORE[3], rf"StringStruct\('FileVersion',\s*'{re.escape(version)}\.0'\)"),
        (CORE[3], rf"StringStruct\('ProductVersion',\s*'{re.escape(version)}\.0'\)"),
        (CORE[3], rf"filevers\s*=\s*\({', '.join([*version.split('.'), '0'])}\)"),
        (CORE[3], rf"prodvers\s*=\s*\({', '.join([*version.split('.'), '0'])}\)"),
    )
    for name, pattern in checks:
        if not re.search(pattern, text(root / name), re.M):
            raise ValueError(f"Version metadata mismatch: {name}")
    return version


def input_hashes(root):
    paths = set()
    for folder in ("calendar_app", "infrastructure", "Assets", "locales", "scripts"):
        base = root / folder
        if base.exists():
            paths.update(
                path
                for path in base.rglob("*")
                if path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix not in {".pyc", ".log", ".db", ".sqlite", ".sqlite3"}
                and not path.name.endswith(("-wal", "-shm"))
                and path.name not in {"credentials.json", "token.json"}
                and not path.name.startswith("client_secret")
            )
    for pattern in ("*.spec", "requirements*.txt", "requirements*.lock"):
        paths.update(root.glob(pattern))
    paths.update(
        root / name
        for name in ("main.py", "run.bat", "build-release.bat", *CORE)
        if (root / name).is_file()
    )
    result = {}
    for path in sorted(paths):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f"Runtime input escapes project: {relative}")
        data = path.read_bytes()
        if path.suffix in {
            ".py",
            ".json",
            ".toml",
            ".xml",
            ".txt",
            ".lock",
            ".bat",
            ".ps1",
            ".spec",
        }:
            source = data.decode("utf-8", errors="strict").replace("\r\n", "\n")
            if relative in CORE:
                source = re.sub(
                    r'(?m)^(APP_VERSION|APP_RELEASE_DATE|APP_RELEASE_CHANNEL|APP_PUBLISHED_VERSION|APP_PUBLISHED_DATE) = "[^"]+"$',
                    r'\1 = "<managed>"',
                    source,
                )
                source = re.sub(r'(?m)^version = "[^"]+"$', 'version = "<managed>"', source)
                source = re.sub(r'(<Identity\b[^>]*\bVersion=")[^"]+', r"\1<managed>", source)
                source = re.sub(r"(filevers|prodvers)\s*=\s*\([^)]+\)", r"\1=<managed>", source)
                source = re.sub(
                    r"(StringStruct\('(?:FileVersion|ProductVersion)',\s*')[^']+",
                    r"\1<managed>",
                    source,
                )
            if relative == "requirements-runtime.lock":
                source = re.sub(
                    r"Air Calendar [0-9]+\.[0-9]+\.[0-9]+ release runtime lock",
                    "Air Calendar <managed> release runtime lock",
                    source,
                )
            data = source.encode("utf-8", errors="strict")
        result[relative] = digest(data)
    return result


def safe_target(root, name):
    if name not in TARGETS:
        raise ValueError("Unexpected version transaction target")
    path = root / name
    if not path.resolve().is_relative_to(root):
        raise ValueError("Version target escapes project")
    return path


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".version-tmp")
    with temporary.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def recover(root):
    journal = root / ".versioning/transaction.json"
    if not journal.exists():
        return
    entries = json.loads(text(journal))
    prepared = []
    for entry in entries:
        path = safe_target(root, entry["path"])
        after = base64.b64decode(entry["after"], validate=True)
        current = digest(path.read_bytes()) if path.exists() else None
        if current not in {entry["before"], digest(after)}:
            raise ValueError(
                "An interrupted version transaction has newer user changes; resolve before retry"
            )
        prepared.append((path, after))
    for path, after in prepared:
        atomic_write(path, after)
    journal.unlink()


def transaction(root, updates):
    entries = []
    for name, after in updates.items():
        path = safe_target(root, name)
        entries.append(
            {
                "path": name,
                "before": digest(path.read_bytes()) if path.exists() else None,
                "after": base64.b64encode(after).decode("utf-8", errors="strict"),
            }
        )
    atomic_write(root / ".versioning/transaction.json", json_bytes(entries))
    recover(root)


@contextmanager
def locked(root):
    directory = root / ".versioning"
    directory.mkdir(exist_ok=True)
    with (directory / "lock").open("a+b") as stream:
        stream.seek(0)
        if not stream.read(1):
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            recover(root)
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def render_history(ledger):
    lines = [
        "# 버전 변경 이력",
        "",
        "개발 변경 버전과 실제 공개·설치 상태는 별도로 관리한다. 버전 부여는 검증·게시 완료를 의미하지 않는다.",
        "",
        f"기준 버전: `{ledger['baseline_version']}` · 현재 개발 버전: **`{ledger['current_version']}`**",
        "",
        "| 버전 | 일시(KST) | 유형 | 변경 내용 | 이벤트 ID |",
        "|---|---|---|---|---|",
    ]
    for item in reversed(ledger["events"]):
        summary = item["summary"].replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {item['version']} | {item['created_at']} | {item['kind']} | {summary} | `{item['id']}` |"
        )
    return ("\n".join(lines) + "\n").encode("utf-8", errors="strict")


def record(root, kind, event_id, summary, files=()):
    if kind not in {"change", "module", "store"} or not re.fullmatch(
        r"[A-Za-z0-9_.:-]{1,160}", event_id
    ):
        raise ValueError("Invalid version event kind or ID")
    history_path = root / HISTORY
    ledger = (
        json.loads(text(history_path))
        if history_path.exists()
        else {
            "schema_version": 1,
            "baseline_version": current_version(root),
            "current_version": current_version(root),
            "events": [],
        }
    )
    current = verify(root, ledger)
    inputs = input_hashes(root)
    scopes = sorted(set(files))
    scoped = {}
    for name in scopes:
        path = root / name
        if not path.resolve().is_relative_to(root):
            raise ValueError("Changed file escapes project")
        scoped[name] = (
            inputs[name]
            if name in inputs
            else digest(path.read_bytes())
            if path.is_file()
            else None
        )
    existing = next((item for item in ledger["events"] if item["id"] == event_id), None)
    if existing:
        compare = inputs if kind == "store" else scoped
        expected = existing["inputs"] if kind == "store" else existing["scoped_hashes"]
        if existing["kind"] != kind or compare != expected:
            raise ValueError(
                "Event ID already belongs to different inputs; use a new logical change ID"
            )
        return {"changed": False, "version": current, "event_version": existing["version"]}
    if kind != "store" and scopes and inputs == ledger.get("observed_inputs"):
        duplicate = next(
            (
                item
                for item in reversed(ledger["events"])
                if item["kind"] == kind and item["scoped_hashes"] == scoped
            ),
            None,
        )
        if duplicate:
            return {"changed": False, "version": current, "event_version": duplicate["version"]}
    if kind == "store":
        previous = next(
            (item for item in reversed(ledger["events"]) if item["kind"] in {"store", "override"}),
            None,
        )
        if previous and previous["inputs"] == inputs:
            return {"changed": False, "version": current, "event_version": previous["version"]}
    timestamp = datetime.now(timezone(timedelta(hours=9)))
    version = next_version(current, kind)
    event = {
        "id": event_id,
        "created_at": timestamp.isoformat(),
        "kind": kind,
        "previous_version": current,
        "version": version,
        "summary": summary,
        "files": scopes,
        "scoped_hashes": scoped,
        "inputs": inputs,
    }
    ledger["events"].append(event)
    ledger.update({"current_version": version, "observed_inputs": inputs})
    updates = core_updates(root, version, timestamp.date().isoformat())
    updates[HISTORY] = json_bytes(ledger)
    updates[REPORT] = render_history(ledger)
    transaction(root, updates)
    return {"changed": True, "version": version, "previous_version": current, "event_id": event_id}


def override(root, version, published_version, event_id, summary):
    """Record a user's explicit unpublished-version correction without deleting history."""
    validate_override(version, published_version)
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", event_id) or not summary.strip():
        raise ValueError("override requires a valid event ID and summary")
    history_path = root / HISTORY
    if not history_path.exists():
        raise ValueError("Version history missing; restore it before correcting a version")
    ledger = json.loads(text(history_path))
    current = verify(root, ledger)
    inputs = input_hashes(root)
    existing = next((item for item in ledger["events"] if item["id"] == event_id), None)
    if existing:
        if (
            existing["kind"] != "override"
            or existing["version"] != version
            or existing["published_version"] != published_version
            or existing["inputs"] != inputs
        ):
            raise ValueError(
                "Event ID already belongs to different correction parameters or inputs"
            )
        return {"changed": False, "version": current, "event_version": existing["version"]}
    timestamp = datetime.now(timezone(timedelta(hours=9)))
    ledger["events"].append(
        {
            "id": event_id,
            "created_at": timestamp.isoformat(),
            "kind": "override",
            "previous_version": current,
            "version": version,
            "published_version": published_version,
            "summary": summary,
            "files": [],
            "scoped_hashes": {},
            "inputs": inputs,
        }
    )
    ledger.update({"current_version": version, "observed_inputs": inputs})
    updates = core_updates(root, version, timestamp.date().isoformat())
    updates[HISTORY] = json_bytes(ledger)
    updates[REPORT] = render_history(ledger)
    transaction(root, updates)
    return {"changed": True, "version": version, "previous_version": current, "event_id": event_id}


def scan(root):
    if not (root / HISTORY).exists():
        raise ValueError("Version history missing; restore it before running the development app")
    ledger = json.loads(text(root / HISTORY))
    current = verify(root, ledger)
    inputs = input_hashes(root)
    previous = ledger["observed_inputs"]
    changed = sorted(
        name for name in inputs.keys() | previous.keys() if inputs.get(name) != previous.get(name)
    )
    if not changed:
        return {"changed": False, "version": current}
    fingerprint = digest(json_bytes(inputs))[:24]
    return record(
        root,
        "change",
        f"auto:{current}:{fingerprint}",
        "개발 실행 전 미등록 실행 입력 변경 감지(검증 상태 별도)",
        changed,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("record", "override", "scan", "check", "status"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--kind", choices=("change", "module", "store"), default="change")
    parser.add_argument("--event-id")
    parser.add_argument("--summary", default="")
    parser.add_argument("--files", nargs="*", default=[])
    parser.add_argument("--expected")
    parser.add_argument("--version")
    parser.add_argument("--published-version")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        with locked(root):
            if args.command == "record":
                if not args.event_id or not args.summary:
                    raise ValueError("record requires --event-id and --summary")
                result = record(root, args.kind, args.event_id, args.summary, args.files)
            elif args.command == "override":
                if not all((args.version, args.published_version, args.event_id, args.summary)):
                    raise ValueError(
                        "override requires --version, --published-version, --event-id and --summary"
                    )
                result = override(
                    root, args.version, args.published_version, args.event_id, args.summary
                )
            elif args.command == "scan":
                result = scan(root)
            else:
                ledger = json.loads(text(root / HISTORY))
                version = verify(root, ledger)
                if args.expected and args.expected != version:
                    raise ValueError(
                        "Build version is not the registered development version; record a change/store event first"
                    )
                result = {
                    "version": version,
                    "events": len(ledger["events"]),
                    "latest_event": ledger["events"][-1]["id"] if ledger["events"] else None,
                }
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"Version management failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
