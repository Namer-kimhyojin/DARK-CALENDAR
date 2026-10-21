# -*- coding: utf-8 -*-
"""Build and verify Air Calendar open-source compliance artifacts."""

from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path, PureWindowsPath
import re
import shutil
import subprocess
import sys
from urllib.parse import quote
from urllib.request import Request, urlopen
import zipfile

_LICENSE_NAME_RE = re.compile(r"^(license|copying|copyright|notice|authors)(\..*)?$", re.IGNORECASE)
_PIN_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([^;\s]+)")
_USER_AGENT = "AirCalendar-ReleaseCompliance/1.0"
_FORBIDDEN_FOREIGN_ICU_PREFIXES = ("icudt", "icuin", "icuuc")
_REQUIRED_UNTRACKED_SOURCE_FILES = (
    Path("requirements-runtime.lock"),
    Path("requirements-build.lock"),
    Path("release-compliance.json"),
    Path("scripts/release_compliance.py"),
    Path("scripts/manage_version.py"),
    Path("scripts/verify_sqlite_runtime.py"),
    Path("scripts/prepare_sqlite_build_runtime.py"),
    Path("scripts/sqlite-runtime-lock.json"),
    Path("scripts/prepare_native_smoke_baseline.py"),
    Path("scripts/native_release_smoke.py"),
    Path("version-history.json"),
    Path("rules/versioning.md"),
    Path("docs/maintenance/version-history.md"),
)


def _canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8", errors="strict"))


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        errors="strict",
    )


def read_lock(path: Path) -> list[tuple[str, str]]:
    """Read exact package pins from a release lock file."""
    pins: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8", errors="strict").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-r "):
            continue
        match = _PIN_RE.match(line)
        if not match:
            raise ValueError(f"Release lock must use exact == pins: {raw_line}")
        name, version = match.groups()
        canonical = _canonical_name(name)
        if canonical in seen:
            raise ValueError(f"Duplicate release lock package: {name}")
        seen.add(canonical)
        pins.append((name, version))
    if not pins:
        raise ValueError(f"No package pins found: {path}")
    return pins


def verify_environment(lock_path: Path) -> list[dict[str, str]]:
    """Require every runtime package to match the release lock exactly."""
    resolved: list[dict[str, str]] = []
    failures: list[str] = []
    for name, expected in read_lock(lock_path):
        try:
            installed = metadata.version(name)
        except metadata.PackageNotFoundError:
            failures.append(f"{name}: missing (expected {expected})")
            continue
        if installed != expected:
            failures.append(f"{name}: installed {installed}, expected {expected}")
        resolved.append({"name": name, "version": installed})
    if failures:
        raise RuntimeError("Release environment mismatch:\n- " + "\n- ".join(failures))
    return resolved


def _is_private_calendar_file(path: str | Path) -> bool:
    """Recognize credential files by basename without reading their contents."""
    name = PureWindowsPath(str(path)).name.lower()
    if name in {"credentials.json", "token.json", "oauth.json", ".env"}:
        return True
    return (
        (name.startswith(".env.") and name != ".env.example")
        or (name.startswith("client_secret") and name.endswith(".json"))
        or name.endswith(".credential")
        or (name.startswith("outlook-") and name.endswith((".cache", ".tmp")))
        or (name.startswith("caldav-") and name.endswith(".tmp"))
        or name.startswith(("token.json.", "credentials.json.", "oauth.json."))
    )


def _validated_filename(filename: str) -> str:
    """Accept portable basenames, never metadata-provided path syntax."""
    if (
        not isinstance(filename, str)
        or not filename
        or filename in (".", "..")
        or filename != filename.rstrip(" .")
        or any(character in '/\\:<>"|?*' or ord(character) < 32 for character in filename)
        or PureWindowsPath(filename).is_reserved()
    ):
        raise ValueError(f"Unsafe compliance filename: {filename!r}")
    return filename


def _validate_config_filenames(config: dict) -> None:
    filenames = []
    for item in config.get("sourceOverrides", {}).values():
        if "filename" in item:
            filenames.append(item["filename"])
    for section in ("additionalSources", "commonLicenseTexts"):
        for item in config.get(section, []):
            filenames.append(item["filename"])
    for item in config.get("licenseFallbacks", {}).values():
        filenames.append(item["filename"])
    for filename in filenames:
        _validated_filename(filename)
        if _is_private_calendar_file(filename):
            raise ValueError(f"Private calendar file cannot be packaged: {filename}")


def _cache_path(cache_dir: Path, filename: str) -> Path:
    root = cache_dir.resolve()
    destination = root / _validated_filename(filename)
    if _is_private_calendar_file(filename):
        raise ValueError(f"Private calendar file cannot be packaged: {filename}")
    if not destination.resolve().is_relative_to(root):
        raise ValueError(f"Compliance file leaves cache directory: {destination}")
    return destination


def _validated_archive_member(member: str) -> str:
    # Check raw components before any path library can normalize away traversal.
    for component in member.split("/"):
        _validated_filename(component)
    if _is_private_calendar_file(member):
        raise ValueError(f"Private calendar file cannot be packaged: {member}")
    return member


def _download(url: str, cache_dir: Path, filename: str, expected_sha256: str) -> Path:
    destination = _cache_path(cache_dir, filename)
    partial = _cache_path(cache_dir, filename + ".part")
    destination.parent.mkdir(parents=True, exist_ok=True)
    expected = expected_sha256.lower()
    if destination.exists() and _sha256(destination) == expected:
        return destination

    if partial.exists():
        partial.unlink()
    request = Request(url, headers={"User-Agent": _USER_AGENT})
    with urlopen(request, timeout=120) as response, partial.open("wb") as target:
        shutil.copyfileobj(response, target)
    actual = _sha256(partial)
    if actual != expected:
        partial.unlink(missing_ok=True)
        raise RuntimeError(
            f"Downloaded hash mismatch for {destination.name}: {actual} != {expected}"
        )
    partial.replace(destination)
    return destination


def _pypi_sdist(name: str, version: str) -> dict[str, str]:
    url = f"https://pypi.org/pypi/{quote(name)}/{quote(version)}/json"
    request = Request(url, headers={"User-Agent": _USER_AGENT})
    with urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    candidates = [item for item in payload.get("urls", []) if item.get("packagetype") == "sdist"]
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one PyPI sdist for {name}=={version}, got {len(candidates)}")
    item = candidates[0]
    return {
        "name": name,
        "version": version,
        "filename": _validated_filename(item["filename"]),
        "url": str(item["url"]),
        "sha256": str(item["digests"]["sha256"]).lower(),
        "source": "PyPI sdist",
    }


def _license_files(distribution: metadata.Distribution) -> list[Path]:
    candidates: list[Path] = []
    for relative in distribution.files or []:
        if not _LICENSE_NAME_RE.match(relative.name):
            continue
        source = Path(distribution.locate_file(relative))
        if source.is_file():
            candidates.append(source)
    return sorted(set(candidates), key=lambda item: str(item).lower())


def bundle_licenses(
    lock_path: Path,
    config_path: Path,
    payload_dir: Path,
    cache_dir: Path,
) -> Path:
    """Copy all locked-distribution license texts into the frozen payload."""
    resolved = verify_environment(lock_path)
    config = _read_json(config_path)
    _validate_config_filenames(config)
    output_dir = payload_dir / "THIRD_PARTY_LICENSES"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    packages: list[dict[str, object]] = []
    common_license_configs = {
        str(item["filename"]): item for item in config.get("commonLicenseTexts", [])
    }
    license_fallbacks = {
        _canonical_name(name): value for name, value in config.get("licenseFallbacks", {}).items()
    }
    for item in resolved:
        name = item["name"]
        version = item["version"]
        distribution = metadata.distribution(name)
        sources = _license_files(distribution)
        if not sources:
            fallback = license_fallbacks.get(_canonical_name(name), {})
            fallback_filename = str(fallback.get("filename", ""))
            fallback_config = common_license_configs.get(fallback_filename)
            if fallback_config is None:
                raise RuntimeError(f"No bundled license text found for {name}=={version}")
            sources = [
                _download(
                    str(fallback_config["url"]),
                    cache_dir / "licenses",
                    fallback_filename,
                    str(fallback_config["sha256"]),
                )
            ]

        package_dir = output_dir / f"{_canonical_name(name)}-{version}"
        package_dir.mkdir(parents=True)
        copied: list[dict[str, str]] = []
        used_names: set[str] = set()
        for index, source in enumerate(sources, start=1):
            leaf = source.name
            destination_name = leaf
            if destination_name.lower() in used_names:
                destination_name = f"{index:02d}-{leaf}"
            used_names.add(destination_name.lower())
            destination = package_dir / destination_name
            shutil.copy2(source, destination)
            copied.append({"file": destination.name, "sha256": _sha256(destination)})

        package_metadata = distribution.metadata
        packages.append(
            {
                "name": name,
                "version": version,
                "license": package_metadata.get("License-Expression")
                or package_metadata.get("License")
                or "See bundled license text",
                "homepage": package_metadata.get("Home-page")
                or package_metadata.get("Project-URL")
                or "",
                "licenseFiles": copied,
            }
        )

    common_dir = output_dir / "common"
    common_dir.mkdir()
    common_licenses: list[dict[str, str]] = []
    for item in config.get("commonLicenseTexts", []):
        cached = _download(
            str(item["url"]),
            cache_dir / "licenses",
            item["filename"],
            str(item["sha256"]),
        )
        destination = common_dir / cached.name
        shutil.copy2(cached, destination)
        common_licenses.append(
            {
                "file": destination.name,
                "url": str(item["url"]),
                "sha256": _sha256(destination),
            }
        )

    manifest_path = payload_dir / "THIRD_PARTY_MANIFEST.json"
    _write_json(
        manifest_path,
        {
            "schemaVersion": 1,
            "lockFile": lock_path.name,
            "packages": packages,
            "commonLicenseTexts": common_licenses,
        },
    )
    return manifest_path


def _tracked_files(project_root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=project_root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"git ls-files failed: {message}")
    values = result.stdout.decode("utf-8", errors="strict").split("\0")
    files = {Path(value) for value in values if value}
    # Local builds use current files, including runtime inputs not yet in Git.
    # Keep corresponding source complete for that same working-directory build.
    for directory, pattern in (("calendar_app", "*.py"), ("Assets", "*"), ("locales", "*.json")):
        for source in project_root.joinpath(directory).rglob(pattern):
            if source.is_file() and "__pycache__" not in source.parts:
                if not source.resolve().is_relative_to(project_root.resolve()):
                    raise RuntimeError(f"Runtime source leaves project directory: {source}")
                files.add(source.relative_to(project_root))
    for relative in _REQUIRED_UNTRACKED_SOURCE_FILES:
        if project_root.joinpath(relative).is_file():
            files.add(relative)
    return sorted(files, key=lambda item: item.as_posix().lower())


def build_corresponding_source(
    project_root: Path,
    version: str,
    lock_path: Path,
    config_path: Path,
    output_path: Path,
    cache_dir: Path,
) -> Path:
    """Create one release asset containing application and upstream source."""
    config = _read_json(config_path)
    _validate_config_filenames(config)
    prefix = _validated_filename(f"DarkCalendar-{version}")
    # Freeze and validate the source inventory before any downloads, output
    # replacement or ZIP writes. Do not partially package a rejected inventory.
    root = project_root.resolve()
    source_files = []
    for relative in _tracked_files(project_root):
        member = _validated_archive_member(f"{prefix}/application-source/{relative.as_posix()}")
        source = project_root / relative
        resolved_source = source.resolve()
        if not resolved_source.is_relative_to(root):
            raise ValueError(f"Application source leaves project directory: {relative}")
        if _is_private_calendar_file(resolved_source):
            raise ValueError(f"Private calendar file cannot be packaged: {relative}")
        source_files.append((source, member))
    overrides = {
        _canonical_name(name): value for name, value in config.get("sourceOverrides", {}).items()
    }
    archives: list[dict[str, str]] = []

    for name, package_version in read_lock(lock_path):
        override = overrides.get(_canonical_name(name))
        if override and "filename" not in override:
            archives.append(
                {
                    "name": name,
                    "version": package_version,
                    "replacedBy": str(override.get("reason", "See additional source archives")),
                }
            )
            continue
        if override:
            item = {
                "name": name,
                "version": package_version,
                "filename": str(override["filename"]),
                "url": str(override["url"]),
                "sha256": str(override["sha256"]).lower(),
                "source": "Pinned source override",
            }
        else:
            item = _pypi_sdist(name, package_version)
        cached = _download(
            item["url"],
            cache_dir / "sources",
            item["filename"],
            item["sha256"],
        )
        item["bytes"] = str(cached.stat().st_size)
        archives.append(item)

    for raw_item in config.get("additionalSources", []):
        item = {str(key): str(value) for key, value in raw_item.items()}
        item["source"] = "Pinned upstream source"
        cached = _download(
            item["url"],
            cache_dir / "sources",
            item["filename"],
            item["sha256"],
        )
        item["bytes"] = str(cached.stat().st_size)
        archives.append(item)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    source_manifest = {
        "schemaVersion": 1,
        "version": version,
        "applicationSource": "application-source/",
        "runtimeLock": lock_path.name,
        "upstreamSources": archives,
    }

    with zipfile.ZipFile(output_path, "w", allowZip64=True) as archive:
        for source, member in source_files:
            if source.is_file():
                archive.write(
                    source,
                    member,
                    compress_type=zipfile.ZIP_DEFLATED,
                )
        archive.writestr(
            _validated_archive_member(f"{prefix}/SOURCE_BUNDLE_MANIFEST.json"),
            json.dumps(source_manifest, ensure_ascii=False, indent=2) + "\n",
            compress_type=zipfile.ZIP_DEFLATED,
        )
        for item in archives:
            filename = item.get("filename")
            if filename is None:
                continue
            source = _cache_path(cache_dir / "sources", filename)
            archive.write(
                source,
                _validated_archive_member(f"{prefix}/upstream-sources/{filename}"),
                compress_type=zipfile.ZIP_STORED,
            )
        for item in config.get("commonLicenseTexts", []):
            cached = _download(
                str(item["url"]),
                cache_dir / "licenses",
                item["filename"],
                str(item["sha256"]),
            )
            archive.write(
                cached,
                _validated_archive_member(f"{prefix}/common-license-texts/{cached.name}"),
                compress_type=zipfile.ZIP_DEFLATED,
            )
    return output_path


def verify_payload(
    payload_dir: Path,
    lock_path: Path,
    config_path: Path,
    source_bundle: Path | None,
) -> None:
    """Fail release packaging when GPL/source/license artifacts are incomplete."""
    required = (
        "LICENSE",
        "README.md",
        "SOURCE_OFFER.md",
        "THIRD_PARTY_NOTICES.md",
        "THIRD_PARTY_MANIFEST.json",
        "THIRD_PARTY_LICENSES",
    )
    missing = [name for name in required if not (payload_dir / name).exists()]
    if missing:
        raise RuntimeError("Payload compliance files missing: " + ", ".join(missing))

    manifest = _read_json(payload_dir / "THIRD_PARTY_MANIFEST.json")
    actual = {
        _canonical_name(str(item["name"])): str(item["version"])
        for item in manifest.get("packages", [])
    }
    expected = {_canonical_name(name): version for name, version in read_lock(lock_path)}
    if actual != expected:
        raise RuntimeError("THIRD_PARTY_MANIFEST.json does not match requirements-runtime.lock")

    config = _read_json(config_path)
    forbidden = {str(name).lower() for name in config.get("forbiddenPayloadFiles", [])}
    hits = sorted(
        str(path.relative_to(payload_dir))
        for path in payload_dir.rglob("*")
        if path.is_file()
        and (
            path.name.lower() in forbidden
            or _is_private_calendar_file(path)
            or (
                path.suffix.lower() == ".dll"
                and path.name.lower().startswith(_FORBIDDEN_FOREIGN_ICU_PREFIXES)
            )
        )
    )
    if hits:
        raise RuntimeError("Unapproved runtime payload files found:\n- " + "\n- ".join(hits))

    if source_bundle is not None and not source_bundle.is_file():
        raise RuntimeError(f"Corresponding-source bundle missing: {source_bundle}")
    if source_bundle is not None:
        with zipfile.ZipFile(source_bundle) as archive:
            for member in archive.infolist():
                _validated_archive_member(member.orig_filename)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify = subparsers.add_parser("verify-env")
    verify.add_argument("--lock", required=True, type=Path)

    licenses = subparsers.add_parser("bundle-licenses")
    licenses.add_argument("--lock", required=True, type=Path)
    licenses.add_argument("--config", required=True, type=Path)
    licenses.add_argument("--payload-dir", required=True, type=Path)
    licenses.add_argument("--cache-dir", required=True, type=Path)

    sources = subparsers.add_parser("build-source-bundle")
    sources.add_argument("--project-root", required=True, type=Path)
    sources.add_argument("--version", required=True)
    sources.add_argument("--lock", required=True, type=Path)
    sources.add_argument("--config", required=True, type=Path)
    sources.add_argument("--output", required=True, type=Path)
    sources.add_argument("--cache-dir", required=True, type=Path)

    payload = subparsers.add_parser("verify-payload")
    payload.add_argument("--payload-dir", required=True, type=Path)
    payload.add_argument("--lock", required=True, type=Path)
    payload.add_argument("--config", required=True, type=Path)
    payload.add_argument("--source-bundle", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "verify-env":
            packages = verify_environment(args.lock)
            print(f"release environment OK: {len(packages)} locked packages")
        elif args.command == "bundle-licenses":
            result = bundle_licenses(args.lock, args.config, args.payload_dir, args.cache_dir)
            print(result)
        elif args.command == "build-source-bundle":
            result = build_corresponding_source(
                args.project_root,
                args.version,
                args.lock,
                args.config,
                args.output,
                args.cache_dir,
            )
            print(result)
        elif args.command == "verify-payload":
            verify_payload(args.payload_dir, args.lock, args.config, args.source_bundle)
            print("payload compliance OK")
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
