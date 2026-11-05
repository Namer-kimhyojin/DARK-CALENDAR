# -*- coding: utf-8 -*-
"""Isolated final candidate contracts; no application, audio or remote execution."""

from contextlib import contextmanager
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock
import zipfile

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "air_final_candidate_qa", Path(__file__).with_name("verify_final_candidate.py")
)
candidate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(candidate)


def policy_fixture():
    inputs = {f"calendar_app/file{index}.py": "a" * 64 for index in range(718)}
    policy = {
        "schema_version": 1,
        "diagnostic_only": False,
        "publication_eligible": False,
        "qa_pins_finalized": True,
        "required_native_cycles": 6,
        "candidate_version": "5.0.0",
        "candidate_commit": "b" * 40,
        "product_source_commit": "a" * 40,
        "candidate_run_id": 1,
        "product_input_count": 718,
        "product_inputs_sha256": candidate.canonical_digest(inputs),
        "payload_file_count": 1877,
        "payload_manifest_sha256": "d" * 64,
        "payload_exe_sha256": "e" * 64,
        "pyinstaller_version": "6.21.0",
        "artifacts": {
            role: {"id": index + 1, "name": name, "sha256": "f" * 64}
            for index, (role, name) in enumerate(candidate.ARTIFACT_NAMES.items())
        },
        "qa_sha256": dict.fromkeys(candidate.REQUIRED_QA_HASHES, "c" * 64),
    }
    return policy, inputs


def test_final_mode_blocks_diagnostic_draft_and_premature_publication():
    policy, _ = policy_fixture()
    candidate.validate_policy(policy)
    for key, value in (
        ("diagnostic_only", True),
        ("publication_eligible", True),
        ("qa_pins_finalized", False),
        ("draft", True),
        ("required_native_cycles", 3),
        ("product_input_count", 717),
        ("payload_file_count", 1876),
    ):
        with pytest.raises(ValueError):
            candidate.validate_policy({**policy, key: value})


@pytest.mark.parametrize("bad", ["a" * 63, "a" * 65, "g" * 64, "A" * 64, None, 7])
def test_every_digest_must_be_exact_lowercase_64_hex(bad):
    policy, _ = policy_fixture()
    policy["artifacts"]["payload"]["sha256"] = bad
    with pytest.raises(ValueError, match="64 hex"):
        candidate.validate_policy(policy)


def test_exact_artifact_roles_and_executable_qa_set_are_required():
    policy, _ = policy_fixture()
    policy["artifacts"]["unexpected"] = policy["artifacts"]["payload"]
    with pytest.raises(ValueError, match="three"):
        candidate.validate_policy(policy)
    policy, _ = policy_fixture()
    policy["qa_sha256"].pop("scripts/native_release_smoke.py")
    with pytest.raises(ValueError, match="every executable"):
        candidate.validate_policy(policy)


def test_final_allowlist_contains_exact_ten_reviewed_qa_paths():
    expected = {
        ".github/workflows/verify-native-5-final.yml",
        "tests/release_qa/verify_final_candidate.py",
        "tests/release_qa/native_final_smoke.py",
        "tests/release_qa/native-final-5.0.0.json",
        "tests/release_qa/test_final_candidate.py",
        "tests/release_qa/native_capture_diagnostics.py",
        "tests/release_qa/native_modal_owner_adapter.py",
        "tests/release_qa/test_native_modal_owner_adapter.py",
        "tests/release_qa/native_runner_surface_adapter.py",
        "tests/release_qa/test_native_runner_surface_adapter.py",
    }
    assert expected == candidate.QA_FILES
    assert "tests/release_qa/native_runner_surface_adapter.py" in candidate.REQUIRED_QA_HASHES


@pytest.mark.parametrize("changed", ["immutable_source", "artifact_build", "qa_checkout"])
def test_all_three_canonical_718_snapshots_must_match(tmp_path, changed):
    policy, inputs = policy_fixture()
    reader = Mock(return_value=inputs)
    assert candidate.verify_product_inputs(tmp_path, policy, lambda _root: inputs, reader)[
        "all_three_snapshots_equal"
    ]
    modified = {**inputs, "calendar_app/file0.py": "different"}

    def reference(_root, commit, _hasher):
        if (changed == "immutable_source" and commit == "a" * 40) or (
            changed == "artifact_build" and commit == "b" * 40
        ):
            return modified
        return inputs

    with pytest.raises(ValueError, match=changed):
        candidate.verify_product_inputs(
            tmp_path,
            policy,
            lambda _root: modified if changed == "qa_checkout" else inputs,
            reference,
        )


def test_final_checkout_rejects_product_or_unlisted_qa_changes_before_download(tmp_path):
    policy, inputs = policy_fixture()
    for changed in (
        "calendar_app/bootstrap.py",
        "scripts/native_release_smoke.py",
        "tests/release_qa/unknown.py",
        "tests/release_qa/test_native_capture_diagnostics.py",
        ".github/workflows/build-release.yml",
    ):

        def git(_root, *arguments, changed=changed):
            return (
                "c" * 40
                if arguments[0] == "rev-parse"
                else changed
                if arguments[0] == "diff"
                else ""
            )

        with pytest.raises(ValueError, match="allowlist"):
            candidate.verify_checkout(
                tmp_path, policy, "c" * 40, SimpleNamespace(git=git), lambda _root: inputs
            )


@pytest.mark.parametrize(
    "name", ["../escape.py", "/absolute.py", "C:/escape.py", "nested\\escape.py"]
)
def test_exact_git_reference_cannot_escape_temporary_root(tmp_path, monkeypatch, name):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        package.writestr(name, b"data")
    archive = output.getvalue()
    if "\\" in name:
        archive = archive.replace(
            name.replace("\\", "/").encode("utf-8", errors="strict"),
            name.encode("utf-8", errors="strict"),
        )
    monkeypatch.setattr(candidate, "git_bytes", lambda *_args: archive)
    hasher = Mock()
    with pytest.raises(ValueError, match="Unsafe"):
        candidate.read_commit_inputs(tmp_path, "a" * 40, hasher)
    hasher.assert_not_called()


def test_exact_git_reference_rejects_symlink(tmp_path, monkeypatch):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        link = zipfile.ZipInfo("calendar_app/link.py")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        package.writestr(link, "../../outside")
    monkeypatch.setattr(candidate, "git_bytes", lambda *_args: output.getvalue())
    with pytest.raises(ValueError, match="Unsafe"):
        candidate.read_commit_inputs(tmp_path, "a" * 40, Mock())


def archive_fixture(tmp_path, *, location=None):
    payload = tmp_path / "payload"
    (payload / "_internal").mkdir(parents=True)
    executable = payload / "DarkCalendar.exe"
    executable.write_bytes(b"synthetic-executable-never-execute")
    with zipfile.ZipFile(payload / "_internal/base_library.zip", "w") as library:
        library.writestr("site.pyc", b"test")
        if location == "base_library":
            library.writestr("sitecustomize.pyc", b"test")
    if location == "disk":
        (payload / "_internal/fingerprint_compat.py").write_bytes(b"test")
    archive = SimpleNamespace(toc={"PYZ.pyz": None, "main": None})
    if location == "carchive":
        archive.toc["tests.release_qa.loader"] = None
    pyz = SimpleNamespace(toc={"site": None})
    if location == "pyz":
        pyz.toc["sitecustomize"] = None
    archive.open_embedded_archive = lambda _name: pyz
    policy, _ = policy_fixture()
    policy["payload_exe_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    return payload, policy, lambda _path: archive


def test_clean_archives_are_read_without_executing_executable(tmp_path):
    payload, policy, reader = archive_fixture(tmp_path)
    result = candidate.inspect_no_qa_modules(
        payload, policy, archive_reader=reader, version_reader=lambda _name: "6.21.0"
    )
    assert result["passed"] and not result["exe_executed"]
    assert not any(result["matches"].values())


@pytest.mark.parametrize("location", ["carchive", "pyz", "base_library", "disk"])
def test_any_qa_module_blocks_native_launch(tmp_path, location):
    payload, policy, reader = archive_fixture(tmp_path, location=location)
    with pytest.raises(ValueError, match="QA-only"):
        candidate.inspect_no_qa_modules(
            payload, policy, archive_reader=reader, version_reader=lambda _name: "6.21.0"
        )


def test_wrong_archive_reader_or_executable_is_rejected(tmp_path):
    payload, policy, reader = archive_fixture(tmp_path)
    with pytest.raises(ValueError, match="PyInstaller"):
        candidate.inspect_no_qa_modules(
            payload, policy, archive_reader=reader, version_reader=lambda _name: "6.20.0"
        )
    policy["payload_exe_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="executable"):
        candidate.inspect_no_qa_modules(
            payload, policy, archive_reader=reader, version_reader=lambda _name: "6.21.0"
        )


@pytest.mark.parametrize("change", ["changed", "added", "removed"])
def test_post_native_check_compares_entire_manifest(tmp_path, change):
    manifest = {"DarkCalendar.exe": "exe", "_internal/Qt6Core.dll": "qt"}
    policy = {
        "payload_file_count": 2,
        "payload_manifest_sha256": candidate.canonical_digest(manifest),
    }
    provenance = {
        "passed": True,
        "diagnostic_only": False,
        "no_qa_modules": {"passed": True},
        "payload_manifest": manifest,
    }
    assert candidate.check_payload_unchanged(tmp_path, provenance, policy, lambda _path: manifest)[
        "passed"
    ]
    other = dict(manifest)
    if change == "changed":
        other["_internal/Qt6Core.dll"] = "different"
    elif change == "added":
        other["extra"] = "new"
    else:
        del other["_internal/Qt6Core.dll"]
    with pytest.raises(ValueError, match="changed"):
        candidate.check_payload_unchanged(tmp_path, provenance, policy, lambda _path: other)


def native_summary_fixture():
    policy, _ = policy_fixture()
    summary = {"passed": True, "candidate_payload_unchanged": True, "cycles": []}
    for scenario in ("fresh", "upgrade"):
        for launch in (1, 2, 3):
            summary["cycles"].append(
                {
                    "scenario": scenario,
                    "launch": launch,
                    "passed": True,
                    "normal_exit": True,
                    "exit_code": 0,
                    "force_killed": False,
                    "exe_sha256": policy["payload_exe_sha256"],
                    "database": {
                        "integrity_check": "ok",
                        "foreign_key_violations": 0,
                        "fixture_preserved": scenario == "upgrade" or launch > 1,
                    },
                }
            )
    return summary, policy


def test_successful_six_cycles_do_not_claim_publication_or_human_screen_review():
    summary, policy = native_summary_fixture()
    result = candidate.verify_six_cycles(summary, policy)
    assert result["native_gate_passed"] and result["native_cycles"] == 6
    assert not result["publication_eligible"] and not result["release_complete"]
    assert not result["screenshots_reviewed"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("passed", False),
        ("normal_exit", False),
        ("exit_code", 1),
        ("exit_code", False),
        ("force_killed", True),
        ("exe_sha256", "different"),
    ],
)
def test_failed_or_wrong_byte_cycle_cannot_be_accepted(field, value):
    summary, policy = native_summary_fixture()
    summary["cycles"][0][field] = value
    with pytest.raises(ValueError):
        candidate.verify_six_cycles(summary, policy)


@pytest.mark.parametrize(
    "problem",
    ["missing", "duplicate", "summary_failed", "payload_changed", "db_bad", "fixture_lost"],
)
def test_six_cycle_shape_database_and_preservation_are_mandatory(problem):
    summary, policy = native_summary_fixture()
    if problem == "missing":
        summary["cycles"].pop()
    elif problem == "duplicate":
        summary["cycles"][-1] = summary["cycles"][0]
    elif problem == "summary_failed":
        summary["passed"] = False
    elif problem == "payload_changed":
        summary["candidate_payload_unchanged"] = False
    elif problem == "db_bad":
        summary["cycles"][0]["database"]["integrity_check"] = "bad"
    else:
        summary["cycles"][-1]["database"]["fixture_preserved"] = False
    with pytest.raises(ValueError):
        candidate.verify_six_cycles(summary, policy)


def test_final_entrypoint_composes_runtime_owner_runner_surface_capture_and_original_main(
    monkeypatch,
):
    spec = importlib.util.spec_from_file_location(
        "air_final_smoke_qa", Path(__file__).with_name("native_final_smoke.py")
    )
    entrypoint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entrypoint)
    events = []
    smoke = SimpleNamespace(main=lambda argv: events.append(("main", argv)) or 0)

    def factory(name):
        @contextmanager
        def install(target):
            assert target is smoke
            events.append(name + " enter")
            yield
            events.append(name + " exit")

        return install

    import scripts

    monkeypatch.setattr(sys, "path", sys.path[:])
    monkeypatch.setattr(scripts, "native_release_smoke", smoke, raising=False)
    monkeypatch.setitem(
        sys.modules,
        "native_release_smoke_adapter",
        SimpleNamespace(install_adapter=factory("runtime")),
    )
    monkeypatch.setitem(
        sys.modules,
        "native_modal_owner_adapter",
        SimpleNamespace(install_owner_adapter=factory("owner")),
    )
    monkeypatch.setitem(
        sys.modules,
        "native_capture_diagnostics",
        SimpleNamespace(install_diagnostics=factory("capture")),
    )
    monkeypatch.setitem(
        sys.modules,
        "native_runner_surface_adapter",
        SimpleNamespace(install_runner_surface_adapter=factory("runner_surface")),
    )
    assert entrypoint.main(["synthetic"]) == 0
    assert events == [
        "runtime enter",
        "owner enter",
        "runner_surface enter",
        "capture enter",
        ("main", ["synthetic"]),
        "capture exit",
        "runner_surface exit",
        "owner exit",
        "runtime exit",
    ]


def test_local_host_guard_runs_before_any_native_import(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(RuntimeError, match="disposable hosted"):
        candidate.require_hosted_output((tmp_path,))


def test_hosted_output_guard_still_rejects_temp_root_and_paths_outside_it(tmp_path, monkeypatch):
    monkeypatch.setattr(candidate.sys, "platform", "win32")
    for key, value in {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_OS": "Windows",
        "RUNNER_TEMP": str(tmp_path),
    }.items():
        monkeypatch.setenv(key, value)
    candidate.require_hosted_output((tmp_path / "evidence", tmp_path / "payload"))
    for path in (tmp_path, tmp_path.parent / "outside"):
        with pytest.raises(ValueError, match="child directories"):
            candidate.require_hosted_output((path,))


@pytest.mark.parametrize("problem", ["none", "raw_zip_hash", "payload_manifest", "qa_module"])
def test_download_cannot_reach_native_ready_provenance_before_all_checks(
    tmp_path, monkeypatch, problem
):
    policy, _ = policy_fixture()
    manifest = {f"file{index}": "a" * 64 for index in range(1877)}
    policy["payload_manifest_sha256"] = candidate.canonical_digest(manifest)
    archive = b"synthetic-zip-stream"
    policy["artifacts"]["payload"]["sha256"] = hashlib.sha256(archive).hexdigest()
    if problem == "raw_zip_hash":
        policy["artifacts"]["payload"]["sha256"] = "f" * 64
    if problem == "payload_manifest":
        policy["payload_manifest_sha256"] = "f" * 64
    monkeypatch.setattr(candidate, "verify_checkout", lambda *_args: {"qa_commit": "c" * 40})

    def open_response(request, timeout):
        assert timeout == 60
        return io.BytesIO(archive if request.endswith("/zip") else b'{"metadata": true}')

    monkeypatch.setattr(
        candidate.urllib.request, "build_opener", lambda *_args: SimpleNamespace(open=open_response)
    )
    extract = Mock(return_value=manifest)
    clean = Mock(
        side_effect=ValueError("QA-only test module") if problem == "qa_module" else None,
        return_value={"passed": True},
    )
    monkeypatch.setattr(candidate, "inspect_no_qa_modules", clean)
    validate = Mock(side_effect=lambda metadata, expected, _policy: {"id": expected["id"]})
    original = SimpleNamespace(
        SafeRedirect=lambda: None,
        api_request=lambda _policy, suffix: suffix,
        validate_artifact=validate,
        sha256=lambda path: hashlib.sha256(path.read_bytes()).hexdigest(),
        extract_payload=extract,
    )
    if problem == "none":
        result = candidate.verify_and_download(
            tmp_path, policy, "c" * 40, tmp_path, tmp_path / "payload", original, Mock()
        )
        assert result["passed"] and result["no_qa_modules"]["passed"]
        assert result["diagnostic_only"] is False and result["publication_eligible"] is False
        assert validate.call_count == 3 and clean.call_count == 1
    else:
        with pytest.raises(ValueError):
            candidate.verify_and_download(
                tmp_path, policy, "c" * 40, tmp_path, tmp_path / "payload", original, Mock()
            )
        if problem == "raw_zip_hash":
            extract.assert_not_called()
        if problem in ("raw_zip_hash", "payload_manifest"):
            clean.assert_not_called()


def test_policy_and_workflow_pin_clean_build_and_keep_original_six_gate(tmp_path):
    policy_path = Path(__file__).with_name("native-final-5.0.0.json")
    policy = json.loads(policy_path.read_text(encoding="utf-8", errors="strict"))
    candidate.validate_policy(policy)
    assert policy["candidate_commit"] == "b526f5671bc6a844da4ef1b534c5a465675dadae"
    assert policy["candidate_run_id"] == 42088226591
    assert policy["product_source_commit"] == "d2b89277c07384e8fbe032ba68754f6212ccda4e"
    assert {role: item["id"] for role, item in policy["artifacts"].items()} == {
        "payload": 13443832079,
        "msix": 13444631618,
        "release_assets": 13442559639,
    }
    assert b"\r" not in policy_path.read_bytes()
    for name, digest in policy["qa_sha256"].items():
        raw = (ROOT / name).read_bytes()
        if name == "requirements-build.lock":
            # Local checkout uses CRLF; the disposable final checkout preserves Git LF.
            committed = subprocess.check_output(
                ["git", "show", f"{policy['candidate_commit']}:{name}"], cwd=ROOT
            )
            assert raw.replace(b"\r\n", b"\n") == committed
            assert hashlib.sha256(committed).hexdigest() == digest
        else:
            assert hashlib.sha256(raw).hexdigest() == digest, name
    lock = (ROOT / "requirements-build.lock").read_text(encoding="utf-8", errors="strict")
    assert f"pyinstaller=={policy['pyinstaller_version']} --hash=sha256:" in lock
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/verify-native-5-final.yml").read_text(
            encoding="utf-8", errors="strict"
        )
    )
    assert workflow["permissions"] == {"contents": "read", "actions": "read"}
    job = workflow["jobs"]["verify-final-clean-x64"]
    assert (
        job["env"]["CANDIDATE_POLICY_SHA256"]
        == hashlib.sha256(policy_path.read_bytes()).hexdigest()
    )
    steps = job["steps"]
    input_check = next(
        i
        for i, step in enumerate(steps)
        if "verify_final_candidate.py inputs" in step.get("run", "")
    )
    dependencies = next(
        i for i, step in enumerate(steps) if "python -m venv" in step.get("run", "")
    )
    preparation = next(i for i, step in enumerate(steps) if step.get("id") == "provenance")
    native = next(i for i, step in enumerate(steps) if step.get("id") == "native")
    assert input_check < dependencies < preparation < native
    check = next(step for step in steps if step.get("id") == "payload_after")
    assert "always()" in check["if"]
    text = "\n".join(step.get("run", "") for step in steps)
    assert "native_final_smoke.py" in text and "--require-hashes" in text
    assert "build-release.bat" not in text and "gh release" not in text and "PYTHONPATH" not in text
