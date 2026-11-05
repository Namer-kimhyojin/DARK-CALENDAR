# -*- coding: utf-8 -*-
"""QA compatibility is scoped to one exact verifier process, never the product."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from PyInstaller.archive.writers import CArchiveWriter, ZlibArchiveWriter
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
LOADER = ROOT / "tests/release_qa/fingerprint_compat/sitecustomize.py"
SPEC = importlib.util.spec_from_file_location("fingerprint_compat_test", LOADER)
compat = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compat)


def copy_loader(repository):
    folder = repository / "tests/release_qa/fingerprint_compat"
    folder.mkdir(parents=True)
    shutil.copyfile(LOADER, folder / "sitecustomize.py")
    return folder


def run_child(argv, *, cwd, loader=None):
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    if loader is not None:
        environment["PYTHONPATH"] = str(loader)
    return subprocess.run(
        [sys.executable, "-B", *map(str, argv)],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
    )


def make_archive_fixture(tmp_path):
    """A data-only CArchive, never an executable app or native process."""
    repository = tmp_path / "fixture-repo"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True)
    shutil.copyfile(
        ROOT / "scripts/verify_release_runtime.py", scripts / "verify_release_runtime.py"
    )
    loader = copy_loader(repository)
    modules = {
        "calendar_app.bootstrap",
        "calendar_app.presentation.widgets.unified_widget_mode",
        "calendar_app.presentation.dialogs.widget_free_layout_editor",
        "calendar_app.presentation.dialogs.widget_customization_dialog",
        "calendar_app.presentation.widgets.widget_layout_presets",
    }
    code, entries = {}, []
    for name in sorted(modules):
        path = repository.joinpath(*name.split(".")).with_suffix(".py")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "def select(items):\n    return items[1:3]\n", encoding="utf-8", errors="strict"
        )
        code[name] = compile(path.read_bytes(), str(path), "exec", dont_inherit=True, optimize=0)
        assert any(isinstance(value, slice) for value in code[name].co_consts[0].co_consts)
        entries.append((name, str(path), "PYMODULE"))
    pyz = tmp_path / "fixture.pyz"
    ZlibArchiveWriter(str(pyz), entries, code_dict=code)
    payload = tmp_path / "payload"
    payload.mkdir()
    CArchiveWriter(
        str(payload / "DarkCalendar.exe"), [("PYZ.pyz", str(pyz), False, "z")], "python314.dll"
    )
    arguments = [
        scripts / "verify_release_runtime.py",
        "--source-root",
        repository,
        "--payload-root",
        payload,
        "--report",
        tmp_path / "verification.json",
    ]
    return repository, loader, arguments


def test_exact_verifier_process_serializes_real_314_slice_constants(tmp_path):
    repository, loader, arguments = make_archive_fixture(tmp_path)
    original = (ROOT / "scripts/verify_release_runtime.py").read_bytes()
    assert arguments[0].read_bytes() == original
    without = run_child(arguments, cwd=repository)
    assert without.returncode != 0
    assert "Object of type slice is not JSON serializable" in without.stderr
    with_loader = run_child(arguments, cwd=repository, loader=loader)
    assert with_loader.returncode == 0, with_loader.stderr
    report = json.loads(arguments[-1].read_text(encoding="utf-8", errors="strict"))
    assert report["failures"] == []
    assert report["compiled_modules_checked"] == 5
    assert arguments[0].read_bytes() == original


def test_slice_bounds_mismatch_still_fails_frozen_source_comparison(tmp_path):
    repository, loader, arguments = make_archive_fixture(tmp_path)
    target = repository / "calendar_app/bootstrap.py"
    target.write_text(
        "def select(items):\n    return items[2:4]\n", encoding="utf-8", errors="strict"
    )
    result = run_child(arguments, cwd=repository, loader=loader)
    assert result.returncode != 0
    report = json.loads(arguments[-1].read_text(encoding="utf-8", errors="strict"))
    assert "Compiled implementation differs: calendar_app.bootstrap" in report["failures"]


@pytest.mark.parametrize("script_name", ["pyinstaller.py", "other.py", "main.py"])
def test_other_script_processes_keep_default_json_behavior(tmp_path, script_name):
    loader = copy_loader(tmp_path)
    script = tmp_path / script_name
    script.write_text(
        "import json, sitecustomize\n"
        "assert sitecustomize.ACTIVE is False\n"
        "try: json.dumps(slice(1, 3))\n"
        "except TypeError: print('unchanged')\n"
        "else: raise AssertionError('unexpected compatibility patch')\n",
        encoding="utf-8",
        errors="strict",
    )
    result = run_child([script], cwd=tmp_path, loader=loader)
    assert result.returncode == 0 and result.stdout.strip() == "unchanged", result.stderr


def test_dash_c_and_wrong_repository_verifier_are_not_patched(tmp_path):
    loader = copy_loader(tmp_path / "owner")
    command = "import json,sitecustomize; assert not sitecustomize.ACTIVE; json.dumps(slice(1,3))"
    result = run_child(["-c", command], cwd=tmp_path, loader=loader)
    assert result.returncode != 0 and "slice is not JSON serializable" in result.stderr
    other = tmp_path / "other/scripts/verify_release_runtime.py"
    other.parent.mkdir(parents=True)
    other.write_text(command, encoding="utf-8", errors="strict")
    result = run_child([other], cwd=tmp_path, loader=loader)
    assert result.returncode != 0 and "slice is not JSON serializable" in result.stderr


def test_real_pyinstaller_entrypoint_keeps_default_json_behavior(tmp_path):
    loader = copy_loader(tmp_path)
    command = (
        "import json,sitecustomize\n"
        "from PyInstaller.__main__ import run\n"
        "assert sitecustomize.ACTIVE is False\n"
        "try: run(['--version'])\n"
        "except SystemExit as error: assert error.code in (0,None)\n"
        "try: json.dumps(slice(1,3))\n"
        "except TypeError: print('pyinstaller-json-unchanged')\n"
        "else: raise AssertionError('unexpected compatibility patch')\n"
    )
    result = run_child(["-c", command], cwd=tmp_path, loader=loader)
    assert result.returncode == 0 and "pyinstaller-json-unchanged" in result.stdout, result.stderr


def test_canonical_nested_slice_and_other_unsupported_types_remain_strict(tmp_path):
    repository = tmp_path / "repo"
    loader = copy_loader(repository)
    target = repository / "scripts/verify_release_runtime.py"
    target.parent.mkdir()
    target.write_text(
        "import json,sitecustomize\n"
        "assert sitecustomize.ACTIVE\n"
        "default=json.JSONEncoder.default\n"
        "assert sitecustomize.install() and json.JSONEncoder.default is default\n"
        "assert json.loads(json.dumps(slice(slice(None,-2,-1),None,2))) == "
        "['slice',['slice',None,-2,-1],None,2]\n"
        "try: json.dumps(object())\n"
        "except TypeError: print('strict')\n"
        "else: raise AssertionError('unexpected type relaxation')\n",
        encoding="utf-8",
        errors="strict",
    )
    result = run_child([target], cwd=repository, loader=loader)
    assert result.returncode == 0 and result.stdout.strip() == "strict", result.stderr


def test_loader_guard_and_workflow_scope_are_exact(tmp_path):
    expected = tmp_path / "scripts/verify_release_runtime.py"
    expected.parent.mkdir()
    expected.touch()
    assert compat.is_verifier_invocation([str(expected)], tmp_path)
    for argument in (
        "-c",
        "-m",
        "",
        str(tmp_path / "verify_release_runtime.py"),
        str(ROOT / "scripts/verify_release_runtime.py"),
    ):
        assert not compat.is_verifier_invocation([argument], tmp_path)
    assert compat.ACTIVE is False
    workflow = (ROOT / ".github/workflows/build-release.yml").read_text(
        encoding="utf-8", errors="strict"
    )
    assert workflow.count("PYTHONPATH:") == 1
    assert "${{ github.workspace }}/tests/release_qa/fingerprint_compat" in workflow
    configuration = yaml.safe_load(workflow)
    assert "PYTHONPATH" not in configuration.get("env", {})
    scoped = [
        (job_name, step["name"], step["env"]["PYTHONPATH"])
        for job_name, job in configuration["jobs"].items()
        for step in job["steps"]
        if "PYTHONPATH" in step.get("env", {})
    ]
    assert scoped == [
        (
            "build-x64",
            "Build x64 release",
            "${{ github.workspace }}/tests/release_qa/fingerprint_compat",
        )
    ]
