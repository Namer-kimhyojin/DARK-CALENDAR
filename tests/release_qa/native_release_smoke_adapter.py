# -*- coding: utf-8 -*-
"""Payload-aware QA adapter; preserve the reserved product smoke implementation.

The immutable 4.3.3 baseline uses Python 3.13 / Qt 6.10.2, while this candidate
uses Python 3.14.10 / Qt 6.12.0. Only the smoke module's expected DLL name and
exact briefing window class are adapted. Hosted-runner, ownership, exception,
normal-exit, DB, content and immutable-payload gates remain the original ones.
"""

from __future__ import annotations

from collections import namedtuple
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
from pathlib import Path
import re
import sys

_VERSION = re.compile(r"([0-9]+)\.([0-9]+)\.([0-9]+)(?:\.[0-9]+)?")
_PYTHON_DLL = re.compile(r"python[0-9]{2,}\.dll", re.IGNORECASE)
_VersionInfo = namedtuple("_VersionInfo", "major minor micro releaselevel serial")
CANDIDATE_PYTHON = (3, 14, 10)
CANDIDATE_QT = (6, 12, 0)
BASELINE_PYTHON = (3, 13)
BASELINE_QT = (6, 10, 2)


def read_pe_product_version(path: Path) -> tuple[int, int, int]:
    """Read ProductVersion, not CPython's differently encoded fixed file version."""
    import win32api

    translations = win32api.GetFileVersionInfo(str(path), r"\VarFileInfo\Translation")
    versions = set()
    for language, codepage in translations:
        key = rf"\StringFileInfo\{language:04x}{codepage:04x}\ProductVersion"
        value = win32api.GetFileVersionInfo(str(path), key).strip()
        match = _VERSION.fullmatch(value)
        if match is None:
            raise RuntimeError(f"Unrecognized PE ProductVersion for {path.name}: {value!r}")
        versions.add(tuple(int(part) for part in match.groups()))
    if len(versions) != 1:
        raise RuntimeError(f"Missing or inconsistent PE ProductVersion: {path.name}")
    return versions.pop()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_payload_runtime(
    payload: Path, *, baseline: bool, version_reader=read_pe_product_version
):
    payload = Path(payload).resolve()
    internal = payload / "_internal"
    if not internal.is_dir():
        raise RuntimeError("Payload has no _internal runtime directory")
    files = [path for path in internal.rglob("*") if path.is_file()]
    python = [path for path in files if _PYTHON_DLL.fullmatch(path.name)]
    qt = [path for path in files if path.name.casefold() == "qt6core.dll"]
    if len(python) != 1 or len(qt) != 1:
        raise RuntimeError("Payload must contain exactly one versioned Python DLL and Qt6Core DLL")
    expected_python = BASELINE_PYTHON if baseline else CANDIDATE_PYTHON
    expected_qt = BASELINE_QT if baseline else CANDIDATE_QT
    result = {"baseline": baseline, "modules": {}}
    for kind, path, expected in (
        ("python", python[0], expected_python),
        ("qt", qt[0], expected_qt),
    ):
        resolved = path.resolve()
        if not resolved.is_relative_to(internal.resolve()):
            raise RuntimeError("Runtime DLL resolves outside the payload")
        version = tuple(version_reader(resolved))
        if len(version) != 3 or version[: len(expected)] != expected:
            raise RuntimeError(
                f"Unexpected {kind} PE ProductVersion: {version}; expected {expected}"
            )
        result["modules"][kind] = {
            "path": str(resolved),
            "version": version,
            "sha256": _sha256(resolved),
        }
    py_version = result["modules"]["python"]["version"]
    expected_name = f"python{py_version[0]}{py_version[1]}.dll"
    if python[0].name.casefold() != expected_name:
        raise RuntimeError("Python DLL filename differs from its verified PE ProductVersion")
    result["python_dll"] = expected_name
    result["qt_window_class"] = "Qt" + "".join(map(str, expected_qt)) + "QWindow"
    return result


def verify_loaded_modules(record, runtime):
    loaded = record.get("bundled_modules", {})
    for kind, name in (("python", runtime["python_dll"]), ("qt", "qt6core.dll")):
        expected = runtime["modules"][kind]
        observed = loaded.get(name)
        if (
            not observed
            or Path(observed["path"]).resolve() != Path(expected["path"])
            or observed.get("sha256") != expected["sha256"]
        ):
            raise RuntimeError(f"Observed loaded {name} differs from the PE-verified payload DLL")


@contextmanager
def install_adapter(smoke, *, version_reader=read_pe_product_version):
    """Adapt one sequential smoke run without changing the actual host sys module."""
    original_launch = smoke._launch_cycle
    original_selector = smoke.select_startup_summary
    original_sys = smoke.sys
    current = ContextVar("native_release_payload_runtime", default=None)

    class PayloadSys:
        @property
        def version_info(self):
            runtime = current.get()
            if runtime is None:
                return original_sys.version_info
            return _VersionInfo(*runtime["modules"]["python"]["version"], "final", 0)

        def __getattr__(self, name):
            # sys.platform and the real environment/runner guard stay unchanged.
            return getattr(original_sys, name)

    def launch(payload, profile, evidence, **options):
        baseline = options.get("baseline", False)
        if type(baseline) is not bool:
            raise RuntimeError("Baseline flag must be explicit boolean")
        runtime = inspect_payload_runtime(payload, baseline=baseline, version_reader=version_reader)
        token = current.set(runtime)
        try:
            record = original_launch(payload, profile, evidence, **options)
            verify_loaded_modules(record, runtime)
            record["qa_payload_runtime"] = runtime
            return record
        finally:
            current.reset(token)

    def select_startup_summary(metadata, pid, main_handle):
        runtime = current.get()
        if runtime is None:
            raise RuntimeError("Briefing identification requires a PE-verified payload runtime")
        dialogs = [
            item
            for item in metadata
            if item["visible"]
            and item["pid"] == pid
            and item["parent"] == main_handle
            and item["title"] == "Today's Events & Due Tasks"
            and item["class_name"] == runtime["qt_window_class"]
        ]
        if len(dialogs) > 1:
            raise RuntimeError("More than one owned startup daily briefing exists")
        return dialogs[0] if dialogs else None

    smoke.sys = PayloadSys()
    smoke._launch_cycle = launch
    smoke.select_startup_summary = select_startup_summary
    try:
        yield smoke
    finally:
        smoke.sys = original_sys
        smoke._launch_cycle = original_launch
        smoke.select_startup_summary = original_selector


def main(argv=None):
    repository = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repository))
    from scripts import native_release_smoke

    with install_adapter(native_release_smoke):
        return native_release_smoke.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
