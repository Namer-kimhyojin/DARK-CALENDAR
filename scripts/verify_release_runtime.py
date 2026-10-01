# -*- coding: utf-8 -*-
"""Verify frozen application code and resources against the build source."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import types

from PyInstaller.archive.readers import CArchiveReader


def _stable(value):
    if isinstance(value, types.CodeType):
        return {
            "bytecode": value.co_code.hex(),
            "constants": [_stable(item) for item in value.co_consts],
            "names": value.co_names,
            "varnames": value.co_varnames,
            "cellvars": value.co_cellvars,
            "freevars": value.co_freevars,
            "arguments": [value.co_argcount, value.co_posonlyargcount, value.co_kwonlyargcount],
            "flags": value.co_flags,
            "exception_table": value.co_exceptiontable.hex(),
        }
    if isinstance(value, bytes):
        return ["bytes", value.hex()]
    if isinstance(value, tuple):
        return ["tuple", [_stable(item) for item in value]]
    if isinstance(value, frozenset):
        return ["frozenset", sorted([_stable(item) for item in value], key=repr)]
    if value is Ellipsis:
        return ["ellipsis"]
    if isinstance(value, complex):
        return ["complex", repr(value)]
    return value


def _fingerprint(code):
    data = json.dumps(_stable(code), sort_keys=True, separators=(",", ":")).encode(
        "utf-8", errors="strict"
    )
    return hashlib.sha256(data).hexdigest()


def verify(source: Path, payload: Path, *, metadata_source: Path | None = None):
    archive = CArchiveReader(str(payload / "DarkCalendar.exe"))
    pyz = archive.open_embedded_archive(next(name for name in archive.toc if name.endswith(".pyz")))
    checks = []
    failures = []
    for module in sorted(pyz.toc):
        if not module.startswith("calendar_app"):
            continue
        relative = Path(*module.split("."))
        path = source / relative.with_suffix(".py")
        if not path.is_file():
            path = source / relative / "__init__.py"
        namespace_package = not path.is_file() and (source / relative).is_dir()
        if not path.is_file() and not namespace_package:
            failures.append("Frozen module has no current source: " + module)
            continue
        if module == "calendar_app.app_metadata" and metadata_source is not None:
            path = metadata_source
        expected = (
            None
            if namespace_package
            else compile(
                path.read_bytes(),
                str(path),
                "exec",
                dont_inherit=True,
                optimize=0,
            )
        )
        matches = _fingerprint(expected) == _fingerprint(pyz.extract(module))
        checks.append({"module": module, "implementation_matches": matches})
        if not matches:
            failures.append("Compiled implementation differs: " + module)

    required = {
        "calendar_app.bootstrap",
        "calendar_app.presentation.widgets.unified_widget_mode",
        "calendar_app.presentation.dialogs.widget_free_layout_editor",
        "calendar_app.presentation.dialogs.widget_customization_dialog",
        "calendar_app.presentation.widgets.widget_layout_presets",
    }
    keydeck = source / "calendar_app/presentation/widgets/keydeck"
    if keydeck.is_dir():
        required.update(
            "calendar_app.presentation.widgets.keydeck." + path.stem
            for path in keydeck.glob("*.py")
            if path.stem != "__init__"
        )
    if (source / "calendar_app/shared/app_lifecycle.py").is_file():
        required.add("calendar_app.shared.app_lifecycle")
    failures.extend(
        "Required current module missing: " + module for module in sorted(required - set(pyz.toc))
    )

    resource_checks = []
    for directory in ["Assets", "locales"]:
        for path in sorted((source / directory).rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            relative = path.relative_to(source)
            destination = payload / "_internal" / relative
            # The pipeline also supplies an external Assets directory.
            targets = [destination]
            if directory == "Assets" and (payload / relative).is_file():
                targets.append(payload / relative)
            matches = all(
                target.is_file() and target.read_bytes() == path.read_bytes() for target in targets
            )
            resource_checks.append({"file": relative.as_posix(), "matches": matches})
            if not matches:
                failures.append("Resource differs or is missing: " + relative.as_posix())
    return {
        "compiled_modules_checked": len(checks),
        "resources_checked": len(resource_checks),
        "failures": failures,
        "compiled_modules": checks,
        "resources": resource_checks,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--payload-root", required=True, type=Path)
    parser.add_argument("--metadata-source", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    report = verify(args.source_root, args.payload_root, metadata_source=args.metadata_source)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8", errors="strict")
    print(
        json.dumps(
            {
                key: value
                for key, value in report.items()
                if key not in {"compiled_modules", "resources"}
            }
        )
    )
    return bool(report["failures"])


if __name__ == "__main__":
    raise SystemExit(main())
