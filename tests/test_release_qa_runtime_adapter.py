# -*- coding: utf-8 -*-
"""Pure payload/adapter contracts; no frozen process, UI or native API is run."""

import hashlib
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

_PATH = Path(__file__).parent / "release_qa/native_release_smoke_adapter.py"
_SPEC = importlib.util.spec_from_file_location("air_release_qa_adapter", _PATH)
adapter = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(adapter)


def payload(tmp_path, *, baseline=False):
    root = tmp_path / ("baseline" if baseline else "candidate")
    internal = root / "_internal"
    internal.mkdir(parents=True)
    python = internal / ("python313.dll" if baseline else "python314.dll")
    qt = internal / "PyQt6/Qt6/bin/Qt6Core.dll"
    qt.parent.mkdir(parents=True)
    python.write_bytes(b"python-fixture")
    qt.write_bytes(b"qt-fixture")
    versions = {
        python: (3, 13, 7) if baseline else (3, 14, 10),
        qt: (6, 10, 2) if baseline else (6, 12, 0),
    }
    return root, python, qt, versions


def row(*, cls="Qt6120QWindow", **changes):
    return {
        "visible": True,
        "pid": 123,
        "parent": 50,
        "title": "Today's Events & Due Tasks",
        "class_name": cls,
        "handle": 200,
        **changes,
    }


@pytest.mark.parametrize("baseline", [False, True])
def test_payload_runtime_uses_verified_pe_versions(tmp_path, baseline):
    root, python, qt, versions = payload(tmp_path, baseline=baseline)
    info = adapter.inspect_payload_runtime(
        root, baseline=baseline, version_reader=versions.__getitem__
    )
    assert info["python_dll"] == python.name
    assert info["qt_window_class"] == ("Qt6102QWindow" if baseline else "Qt6120QWindow")
    assert info["modules"]["qt"]["path"] == str(qt)


@pytest.mark.parametrize(
    "kind,version", [("python", (3, 13, 7)), ("qt", (6, 10, 2)), ("python", (3, 14, 9))]
)
def test_candidate_rejects_wrong_or_legacy_runtime(tmp_path, kind, version):
    root, python, qt, versions = payload(tmp_path)
    versions[python if kind == "python" else qt] = version
    with pytest.raises(RuntimeError, match="Unexpected"):
        adapter.inspect_payload_runtime(root, baseline=False, version_reader=versions.__getitem__)


def test_baseline_rejects_new_qt_and_ambiguous_dlls(tmp_path):
    root, python, qt, versions = payload(tmp_path, baseline=True)
    versions[qt] = (6, 12, 0)
    with pytest.raises(RuntimeError, match="Unexpected qt"):
        adapter.inspect_payload_runtime(root, baseline=True, version_reader=versions.__getitem__)
    versions[qt] = (6, 10, 2)
    (python.parent / "python314.dll").write_bytes(b"extra")
    with pytest.raises(RuntimeError, match="exactly one"):
        adapter.inspect_payload_runtime(root, baseline=True, version_reader=versions.__getitem__)


@pytest.mark.parametrize("baseline", [False, True])
def test_adapter_keeps_host_and_strict_briefing_identity(tmp_path, baseline):
    root, python, qt, versions = payload(tmp_path, baseline=baseline)
    observed = []
    host_version = sys.version_info
    expected_class = "Qt6102QWindow" if baseline else "Qt6120QWindow"
    smoke = SimpleNamespace(sys=sys, select_startup_summary=lambda *_args: None)

    def original(_payload, _profile, _evidence, **options):
        observed.append((smoke.sys.version_info.major, smoke.sys.version_info.minor))
        assert smoke.sys.platform == sys.platform
        assert sys.version_info is host_version
        valid = row(cls=expected_class)
        assert smoke.select_startup_summary([valid], 123, 50) is valid
        for changes in (
            {"pid": 999},
            {"parent": 999},
            {"visible": False},
            {"title": "Other"},
            {"class_name": "Qt999QWindow"},
            {"class_name": "Qt6120QWindow" if baseline else "Qt6102QWindow"},
        ):
            assert (
                smoke.select_startup_summary([row(cls=expected_class, **changes)], 123, 50) is None
            )
        with pytest.raises(RuntimeError, match="More than one"):
            smoke.select_startup_summary([valid, {**valid, "handle": 201}], 123, 50)
        return {
            "bundled_modules": {
                path.name.lower(): {
                    "path": str(path),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
                for path in (python, qt)
            }
        }

    smoke._launch_cycle = original
    selector = smoke.select_startup_summary
    with adapter.install_adapter(smoke, version_reader=versions.__getitem__):
        with pytest.raises(RuntimeError, match="requires"):
            smoke.select_startup_summary([], 123, 50)
        result = smoke._launch_cycle(root, tmp_path, tmp_path, baseline=baseline)
        assert result["qa_payload_runtime"]["qt_window_class"] == expected_class
    assert observed == [(3, 13) if baseline else (3, 14)]
    assert smoke.sys is sys
    assert smoke._launch_cycle is original
    assert smoke.select_startup_summary is selector


@pytest.mark.parametrize("mismatch", ["path", "hash"])
def test_loaded_paths_and_hashes_must_match_preverified_payload(tmp_path, mismatch):
    root, python, qt, versions = payload(tmp_path)
    info = adapter.inspect_payload_runtime(
        root, baseline=False, version_reader=versions.__getitem__
    )
    record = {
        "bundled_modules": {
            path.name.lower(): {
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in (python, qt)
        }
    }
    record["bundled_modules"][python.name]["path" if mismatch == "path" else "sha256"] = (
        str(tmp_path / python.name) if mismatch == "path" else "different"
    )
    with pytest.raises(RuntimeError, match="Observed loaded"):
        adapter.verify_loaded_modules(record, info)


def test_adapter_restores_references_after_original_failure(tmp_path):
    root, _python, _qt, versions = payload(tmp_path)

    def failure(*_args, **_kwargs):
        raise RuntimeError("original hosted/runtime gate rejected")

    def selector(*_args):
        return None

    smoke = SimpleNamespace(sys=sys, _launch_cycle=failure, select_startup_summary=selector)
    with (
        pytest.raises(RuntimeError, match="original hosted"),
        adapter.install_adapter(smoke, version_reader=versions.__getitem__),
    ):
        smoke._launch_cycle(root, tmp_path, tmp_path)
    assert smoke.sys is sys and smoke._launch_cycle is failure
    assert smoke.select_startup_summary is selector


def test_original_product_smoke_stays_the_workflow_delegation_target():
    source = _PATH.read_text(encoding="utf-8", errors="strict")
    workflow = (_PATH.parents[2] / ".github/workflows/build-release.yml").read_text(
        encoding="utf-8", errors="strict"
    )
    assert "native_release_smoke.main(argv)" in source
    assert "tests\\release_qa\\native_release_smoke_adapter.py" in workflow


def test_adapter_preserves_original_hosted_runner_rejection(tmp_path):
    from scripts.native_release_smoke import require_hosted_runner

    root, _python, _qt, versions = payload(tmp_path)
    smoke = SimpleNamespace(sys=sys, select_startup_summary=lambda *_args: None)

    def original(*_args, **_kwargs):
        require_hosted_runner({}, smoke.sys.platform, tmp_path)

    smoke._launch_cycle = original
    with adapter.install_adapter(smoke, version_reader=versions.__getitem__), pytest.raises(
        RuntimeError, match="only on disposable GitHub-hosted"
    ):
        smoke._launch_cycle(root, tmp_path, tmp_path)


def test_pe_reader_uses_product_version_not_cpython_fixed_file_version(monkeypatch):
    calls = []

    def get_info(_path, key):
        calls.append(key)
        if key == r"\VarFileInfo\Translation":
            return [(0x0409, 0x04B0)]
        if key.endswith(r"\ProductVersion"):
            return "3.14.10"
        raise AssertionError("No fixed FileVersion fallback is permitted")

    monkeypatch.setitem(sys.modules, "win32api", SimpleNamespace(GetFileVersionInfo=get_info))
    assert adapter.read_pe_product_version(Path("python314.dll")) == (3, 14, 10)
    assert calls == [r"\VarFileInfo\Translation", r"\StringFileInfo\040904b0\ProductVersion"]


@pytest.mark.parametrize("translations,value", [([], "3.14.10"), ([(1033, 1200)], "unknown")])
def test_pe_reader_fails_closed_on_missing_or_unknown_metadata(monkeypatch, translations, value):
    def get_info(_path, key):
        return translations if key == r"\VarFileInfo\Translation" else value

    monkeypatch.setitem(sys.modules, "win32api", SimpleNamespace(GetFileVersionInfo=get_info))
    with pytest.raises(RuntimeError, match="PE ProductVersion"):
        adapter.read_pe_product_version(Path("python314.dll"))
