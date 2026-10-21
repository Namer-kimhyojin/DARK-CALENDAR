# -*- coding: utf-8 -*-
"""Record changes without bumping; explicitly prepare release-unit versions."""

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
    if not isinstance(version, str) or not re.fullmatch(
        r"[1-9][0-9]*\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version
    ):
        raise ValueError("Version must be MAJOR.MINOR.PATCH without leading zeros")
    parts = tuple(map(int, version.split(".")))
    if any(part > 65535 for part in parts):
        raise ValueError("MSIX version components cannot exceed 65535")
    return parts


def validate_override(version, published_version):
    if version_number(version) <= version_number(published_version):
        raise ValueError("Override version must be higher than the verified published version")


def next_version(current, kind):
    major, minor, patch = version_number(current)
    if kind == "patch":
        patch += 1
    elif kind == "minor":
        minor, patch = minor + 1, 0
    elif kind == "major":
        major, minor, patch = major + 1, 0, 0
    else:
        raise ValueError("Only an explicit patch, minor or major release changes the version")
    result = f"{major}.{minor}.{patch}"
    version_number(result)
    return result


def legacy_next_version(current, kind):
    """Validate historical v1 events with their original single-digit policy."""
    if not re.fullmatch(r"[0-9]\.[0-9]\.[0-9]", current):
        raise ValueError("Invalid legacy version")
    major, minor, patch = map(int, current.split("."))
    value = major * 100 + minor * 10 + patch
    value = value + 1 if kind == "change" else (value // 10 + 1) * 10
    if value > 999:
        raise ValueError("Invalid legacy version event")
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
    version_number(version)
    return version


def core_updates(root, version, date, channel="Dev", *, for_build=False):
    version_number(version)
    if channel not in {"Dev", "Beta", "Stable"}:
        raise ValueError("Channel must be Dev, Beta or Stable")
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", date):
        raise ValueError("Release date must be YYYY-MM-DD")
    datetime.strptime(date, "%Y-%m-%d")
    metadata = replace_one(
        r'^APP_VERSION = "[^"]+"$', f'APP_VERSION = "{version}"', text(root / CORE[0])
    )
    metadata = replace_one(
        r'^APP_RELEASE_DATE = "[^"]+"$', f'APP_RELEASE_DATE = "{date}"', metadata
    )
    metadata = replace_one(
        r'^APP_RELEASE_CHANNEL = "[^"]+"$', f'APP_RELEASE_CHANNEL = "{channel}"', metadata
    )
    if for_build:
        for name, value in (("APP_PUBLISHED_VERSION", version), ("APP_PUBLISHED_DATE", date)):
            metadata = replace_one(rf'^{name} = "[^"]+"$', f'{name} = "{value}"', metadata)
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


def verify(root, ledger, *, check_surfaces=True):
    version = ledger["current_version"]
    version_number(version)
    if check_surfaces and current_version(root) != version:
        raise ValueError("Version history and APP_VERSION disagree; do not edit versions manually")
    previous = ledger["baseline_version"]
    ids = set()
    schema = ledger.get("schema_version", 1)
    if schema not in {1, 2}:
        raise ValueError("Unsupported version history schema")
    legacy_count = len(ledger["events"]) if schema == 1 else ledger["legacy_event_count"]
    if not isinstance(legacy_count, int) or not 0 <= legacy_count <= len(ledger["events"]):
        raise ValueError("Invalid legacy event boundary")
    for index, event in enumerate(ledger["events"]):
        if event["id"] in ids or event["previous_version"] != previous:
            raise ValueError("Version history chain is inconsistent")
        if index < legacy_count:
            if event["kind"] == "override":
                validate_override(event["version"], event.get("published_version"))
            elif event["kind"] not in {"change", "module", "store"} or event[
                "version"
            ] != legacy_next_version(previous, event["kind"]):
                raise ValueError("Version history chain is inconsistent")
        elif event["kind"] == "release":
            if version_number(event["version"]) < version_number(previous):
                raise ValueError("Release version cannot move backwards")
            if event.get("bump") and event["version"] != next_version(previous, event["bump"]):
                raise ValueError("Release increment does not match its recorded scope")
            validate_override(event["version"], event["published_version"])
        elif (
            event["kind"] not in {"change", "module", "store", "policy"}
            or event["version"] != previous
        ):
            raise ValueError("Change records must not increment the product version")
        ids.add(event["id"])
        previous = event["version"]
    if previous != version:
        raise ValueError("Version history endpoint is inconsistent")
    if not check_surfaces:
        return version
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
    if schema == 2:
        if ledger["release"]["channel"] not in {"Dev", "Beta", "Stable"}:
            raise ValueError("Invalid release channel")
        date = ledger["release"]["date"]
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", date):
            raise ValueError("Release date must be YYYY-MM-DD")
        datetime.strptime(date, "%Y-%m-%d")
        for name, value in (
            ("APP_RELEASE_DATE", ledger["release"]["date"]),
            ("APP_RELEASE_CHANNEL", ledger["release"]["channel"]),
        ):
            if f'{name} = "{value}"' not in text(root / CORE[0]):
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
        "제품 버전은 배포 단위로 결정한다. 변경 기록·Git/CI 빌드·공개·Store·설치 상태는 별도이며 변경 기록만으로 버전을 올리지 않는다.",
        "",
        f"기준 버전: `{ledger['baseline_version']}` · 현재 제품 버전: **`{ledger['current_version']}`**",
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


def load_ledger(root, *, check_surfaces=True):
    if not (root / HISTORY).exists():
        raise ValueError("Version history missing; restore it before managing releases")
    ledger = json.loads(text(root / HISTORY))
    verify(root, ledger, check_surfaces=check_surfaces)
    return ledger


def adopt_release_policy(root, ledger):
    if ledger.get("schema_version") == 2:
        return False
    metadata = text(root / CORE[0])
    ledger.update(
        schema_version=2,
        legacy_event_count=len(ledger["events"]),
        release={
            "date": re.search(r'^APP_RELEASE_DATE = "([^"]+)"$', metadata, re.M)[1],
            "channel": re.search(r'^APP_RELEASE_CHANNEL = "([^"]+)"$', metadata, re.M)[1],
        },
    )
    ledger["events"].append(
        {
            "id": "policy:release-unit-v2",
            "created_at": datetime.now(timezone(timedelta(hours=9))).isoformat(),
            "kind": "policy",
            "previous_version": ledger["current_version"],
            "version": ledger["current_version"],
            "summary": "배포 단위 버전 체계로 전환; 기존 번호·이력·공개 패키지 보존",
            "files": [],
            "scoped_hashes": {},
            "inputs": input_hashes(root),
        }
    )
    return True


def save_ledger(root, ledger, updates=None):
    changes = dict(updates or {})
    changes[HISTORY] = json_bytes(ledger)
    changes[REPORT] = render_history(ledger)
    transaction(root, changes)


def migrate(root):
    ledger = load_ledger(root)
    changed = adopt_release_policy(root, ledger)
    if changed:
        save_ledger(root, ledger)
    return {"changed": changed, "version": ledger["current_version"], "schema_version": 2}


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
    adopt_release_policy(root, ledger)
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
    version = current
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
    observed = dict(ledger.get("observed_inputs", inputs))
    if not scopes:
        observed = inputs
    else:
        for name in scopes:
            if name in inputs:
                observed[name] = inputs[name]
            else:
                observed.pop(name, None)
    ledger["observed_inputs"] = observed
    save_ledger(root, ledger)
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
    if ledger.get("schema_version") == 2:
        raise ValueError("Use prepare for release-unit versions; published versions are immutable")
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
    ledger = load_ledger(root)
    current = ledger["current_version"]
    inputs = input_hashes(root)
    previous = ledger["observed_inputs"]
    changed = sorted(
        name for name in inputs.keys() | previous.keys() if inputs.get(name) != previous.get(name)
    )
    return {"changed": False, "version": current, "unrecorded_files": changed}


def prepare(root, event_id, summary, *, version=None, bump=None):
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", event_id or "") or not summary.strip():
        raise ValueError("prepare requires --event-id and --summary")
    if bool(version) == bool(bump):
        raise ValueError("prepare requires exactly one of --version or --bump")
    ledger = load_ledger(root)
    adopt_release_policy(root, ledger)
    if scan(root)["unrecorded_files"]:
        raise ValueError("Unrecorded inputs; record the scoped changes before preparing a release")
    inputs = input_hashes(root)
    existing = next((event for event in ledger["events"] if event["id"] == event_id), None)
    if existing:
        if (
            existing["kind"] != "release"
            or existing["inputs"] != inputs
            or (version is not None and existing["version"] != version)
            or existing.get("bump") != bump
        ):
            raise ValueError("Release ID already belongs to different parameters or inputs")
        return {"changed": False, "version": existing["version"], "event_id": event_id}
    current = ledger["current_version"]
    selected = version or next_version(current, bump)
    metadata = text(root / CORE[0])
    published = re.search(r'^APP_PUBLISHED_VERSION = "([^"]+)"$', metadata, re.M)[1]
    validate_override(selected, published)
    if version_number(selected) < version_number(current):
        raise ValueError("Release version cannot move backwards")
    reservation = next(
        (
            event
            for event in reversed(ledger["events"])
            if event["kind"] == "release" and event["version"] == selected
        ),
        None,
    )
    if reservation:
        if reservation["inputs"] != inputs:
            raise ValueError(
                "Reserved version has different inputs; choose a higher release version"
            )
        return {"changed": False, "version": selected, "event_id": reservation["id"]}
    timestamp = datetime.now(timezone(timedelta(hours=9)))
    ledger["events"].append(
        {
            "id": event_id,
            "kind": "release",
            "created_at": timestamp.isoformat(),
            "previous_version": current,
            "version": selected,
            "published_version": published,
            "bump": bump,
            "summary": summary,
            "files": [],
            "scoped_hashes": {},
            "inputs": inputs,
        }
    )
    ledger["current_version"] = selected
    ledger["release"] = {"date": timestamp.date().isoformat(), "channel": "Dev"}
    save_ledger(root, ledger, core_updates(root, selected, ledger["release"]["date"]))
    return {"changed": True, "previous_version": current, "version": selected, "event_id": event_id}


def sync(root, *, expected=None, date=None, channel=None, for_build=False):
    ledger = load_ledger(root, check_surfaces=False)
    adopt_release_policy(root, ledger)
    version = ledger["current_version"]
    if expected and version != expected:
        raise ValueError("Build version differs from the prepared release version")
    if for_build:
        verify_prepared(root, ledger)
    date = date or ledger["release"]["date"]
    channel = channel or ledger["release"]["channel"]
    updates = core_updates(root, version, date, channel, for_build=for_build)
    ledger["release"] = {"date": date, "channel": channel}
    save_ledger(root, ledger, updates)
    return {"changed": True, "version": version, "channel": channel, "date": date}


def verify_prepared(root, ledger):
    reservation = next(
        (
            event
            for event in reversed(ledger["events"])
            if event["kind"] == "release" and event["version"] == ledger["current_version"]
        ),
        None,
    )
    if reservation is None:
        raise ValueError("Prepare the release explicitly before building a new package")
    if reservation["inputs"] != input_hashes(root):
        raise ValueError("Prepared release inputs changed; prepare a new version before rebuilding")
    return reservation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("record", "override", "scan", "check", "status", "migrate", "prepare", "sync"),
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--kind", choices=("change", "module", "store"), default="change")
    parser.add_argument("--event-id")
    parser.add_argument("--summary", default="")
    parser.add_argument("--files", nargs="*", default=[])
    parser.add_argument("--expected")
    parser.add_argument("--version")
    parser.add_argument("--published-version")
    parser.add_argument("--bump", choices=("patch", "minor", "major"))
    parser.add_argument("--date")
    parser.add_argument("--channel", choices=("Dev", "Beta", "Stable"))
    parser.add_argument("--for-build", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Fail on unrecorded runtime inputs")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        from contextlib import nullcontext

        reading = args.command in {"scan", "check", "status"}
        if reading and (root / ".versioning/transaction.json").exists():
            raise ValueError(
                "Interrupted transaction pending; recover with a mutating command first"
            )
        with nullcontext() if reading else locked(root):
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
            elif args.command == "migrate":
                result = migrate(root)
            elif args.command == "prepare":
                result = prepare(
                    root, args.event_id, args.summary, version=args.version, bump=args.bump
                )
            elif args.command == "sync":
                result = sync(
                    root,
                    expected=args.expected,
                    date=args.date,
                    channel=args.channel,
                    for_build=args.for_build,
                )
            else:
                ledger = json.loads(text(root / HISTORY))
                version = verify(root, ledger)
                if args.expected and args.expected != version:
                    raise ValueError(
                        "Build version is not the prepared product version; use prepare explicitly"
                    )
                result = {
                    "version": version,
                    "events": len(ledger["events"]),
                    "latest_event": ledger["events"][-1]["id"] if ledger["events"] else None,
                }
                if args.strict:
                    result["unrecorded_files"] = scan(root)["unrecorded_files"]
                if args.for_build:
                    verify_prepared(root, ledger)
        print(json.dumps(result))
        if args.strict and result.get("unrecorded_files"):
            return 2
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"Version management failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
