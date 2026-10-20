# -*- coding: utf-8 -*-
"""Fetch the immutable public previous release for isolated CI upgrade checks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from urllib.parse import unquote
from urllib.request import Request, urlopen
import zipfile

BASELINE_URL = "https://github.com/Namer-kimhyojin/DARK-CALENDAR/releases/download/v4.3.3/DarkCalendar-4.3.3-x64.msix"
BASELINE_SHA256 = "ccd82327a4a356555ef68accec20698a4f829a1e3a65d1db5b833279dcc882aa"


def decoded_member(name: str) -> PurePosixPath:
    """Decode MSIX URI names once without allowing writes outside extraction."""
    value = unquote(name, encoding="utf-8", errors="strict").replace("\\", "/")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or any(":" in part for part in path.parts):
        raise RuntimeError(f"Unsafe MSIX member: {name!r}")
    if not path.parts or "\x00" in value:
        raise RuntimeError(f"Empty or invalid MSIX member: {name!r}")
    return path


def extract_msix(archive: Path, destination: Path) -> dict[str, str]:
    hashes = {}
    names = set()
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            relative = decoded_member(member.filename)
            key = relative.as_posix().casefold()
            if key in names:
                raise RuntimeError(f"Duplicate decoded MSIX member: {member.filename}")
            names.add(key)
            target = destination.joinpath(*relative.parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if member.file_size > 512 * 1024 * 1024:
                raise RuntimeError("MSIX member exceeds the expected size bound")
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            hashes[relative.as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
    return hashes


def prepare(destination: Path) -> dict:
    destination = destination.resolve()
    if destination.exists():
        receipt = json.loads(
            (destination / "baseline-receipt.json").read_text(encoding="utf-8", errors="strict")
        )
        if receipt["archive_sha256"] != BASELINE_SHA256:
            raise RuntimeError("Existing baseline receipt differs from the pinned public release")
        for relative, expected in receipt["files"].items():
            # Receipt paths have already been URI-decoded during extraction.
            path = (destination / relative).resolve()
            if not path.is_relative_to(destination):
                raise RuntimeError("Existing baseline receipt leaves its payload directory")
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise RuntimeError(f"Existing baseline changed: {relative}")
        return {"passed": True, "reused": True, "payload": str(destination)}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="native-baseline-staging-", dir=destination.parent
    ) as name:
        staging = Path(name)
        archive = staging / "previous-release.msix"
        request = Request(
            BASELINE_URL, headers={"User-Agent": "AirCalendar-NativeReleaseSmoke/1.0"}
        )
        with urlopen(request, timeout=90) as source, archive.open("xb") as output:
            shutil.copyfileobj(source, output)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != BASELINE_SHA256:
            raise RuntimeError("Previous public release MSIX SHA-256 mismatch")
        payload = staging / "payload"
        payload.mkdir()
        hashes = extract_msix(archive, payload)
        if not (payload / "DarkCalendar.exe").is_file():
            raise RuntimeError("Previous public release has no native DarkCalendar.exe")
        receipt = {
            "version": "4.3.3",
            "url": BASELINE_URL,
            "archive_sha256": BASELINE_SHA256,
            "files": hashes,
        }
        (payload / "baseline-receipt.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8", errors="strict"
        )
        payload.rename(destination)
    return {"passed": True, "reused": False, "payload": str(destination)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = prepare(args.directory)
    except (OSError, RuntimeError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
