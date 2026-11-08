# -*- coding: utf-8 -*-
"""Data-only same-payload provenance contracts; no app or network execution."""

from contextlib import nullcontext
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import stat
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock
import zipfile

import pytest
import yaml

_PATH = Path(__file__).with_name("verify_same_payload_candidate.py")
_SPEC = importlib.util.spec_from_file_location("air_same_payload_qa", _PATH)
candidate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(candidate)
ROOT = _PATH.parents[2]

# Recorded directly from the GitHub API for run 42083557480.
LIVE_ARTIFACT_METADATA = {
    "payload": {
        "id": 13442635125,
        "name": "darkcalendar-dist-x64",
        "digest": "sha256:1a85e998516fc269a17ac9b43fd09b91d8264731a595b60b204a8d5a2b3d0bed",
        "expired": False,
        "workflow_run": {
            "id": 42083557480,
            "repository_id": 1195286732,
            "head_repository_id": 1195286732,
            "head_branch": "release/5.0.0-integrated-20261106",
            "head_sha": "2557dd940015ee7a404966b6ed9ef76cd57e86f1",
        },
    },
    "msix": {
        "id": 13440664435,
        "name": "darkcalendar-msix-x64",
        "digest": "sha256:ed8df53b62effefc2047c0f060c9ca7c328b48a8ac63185cf1a0df7c0fa945d5",
        "expired": False,
        "workflow_run": {
            "id": 42083557480,
            "repository_id": 1195286732,
            "head_repository_id": 1195286732,
            "head_branch": "release/5.0.0-integrated-20261106",
            "head_sha": "2557dd940015ee7a404966b6ed9ef76cd57e86f1",
        },
    },
    "release_assets": {
        "id": 13440629566,
        "name": "darkcalendar-github-release-x64",
        "digest": "sha256:c21b96c70db3919f4da38dc81836641e62fc335fc4459c500d4d5b680ab69f84",
        "expired": False,
        "workflow_run": {
            "id": 42083557480,
            "repository_id": 1195286732,
            "head_repository_id": 1195286732,
            "head_branch": "release/5.0.0-integrated-20261106",
            "head_sha": "2557dd940015ee7a404966b6ed9ef76cd57e86f1",
        },
    },
}


def policy_fixture(inputs=None):
    inputs = {"main.py": "hash", "calendar_app/x.py": "hash2"} if inputs is None else inputs
    return {
        "product_source_commit": "a" * 40,
        "candidate_commit": "b" * 40,
        "product_input_count": len(inputs),
        "product_inputs_sha256": candidate.canonical_digest(inputs),
        "qa_sha256": dict.fromkeys(candidate.REQUIRED_QA_HASHES, "same-hash"),
    }, inputs


def test_every_product_snapshot_must_match_same_canonical_count_and_digest(tmp_path):
    policy, inputs = policy_fixture()
    reader = Mock(return_value=inputs)
    value = candidate.verify_product_inputs(tmp_path, policy, lambda _root: inputs, reader)
    assert value["all_three_snapshots_equal"] is True
    assert reader.call_count == 2


@pytest.mark.parametrize("snapshot", ["immutable_source", "artifact_build", "qa_checkout"])
def test_any_changed_added_or_removed_input_fails(tmp_path, snapshot):
    policy, inputs = policy_fixture()
    changed = {**inputs, "scripts/injected.py": "new"}

    def reader(_root, commit, _hasher):
        return (
            changed
            if (snapshot == "immutable_source" and commit == "a" * 40)
            or (snapshot == "artifact_build" and commit == "b" * 40)
            else inputs
        )

    with pytest.raises(ValueError, match=snapshot):
        candidate.verify_product_inputs(
            tmp_path, policy, lambda _root: changed if snapshot == "qa_checkout" else inputs, reader
        )


@pytest.mark.parametrize("change", ["changed", "added", "removed"])
def test_post_native_manifest_is_exact_and_not_just_executable_hash(tmp_path, change):
    manifest = {"DarkCalendar.exe": "exe", "_internal/Qt6Core.dll": "qt"}
    policy = {
        "payload_file_count": 2,
        "payload_manifest_sha256": candidate.canonical_digest(manifest),
    }
    provenance = {"passed": True, "payload_manifest": manifest}
    assert candidate.check_payload_unchanged(tmp_path, provenance, policy, lambda _path: manifest)[
        "passed"
    ]
    changed = dict(manifest)
    if change == "changed":
        changed["_internal/Qt6Core.dll"] = "tampered"
    elif change == "added":
        changed["extra.py"] = "new"
    else:
        del changed["_internal/Qt6Core.dll"]
    with pytest.raises(ValueError, match="changed"):
        candidate.check_payload_unchanged(tmp_path, provenance, policy, lambda _path: changed)


def test_checkout_rejects_non_qa_change_before_download(tmp_path):
    policy, inputs = policy_fixture()

    def git(_root, *args):
        if args[0] == "rev-parse":
            return "c" * 40
        if args[0] == "diff":
            return "calendar_app/presentation/main_window/app_window.py\n"
        return ""

    original = SimpleNamespace(git=git)
    with pytest.raises(ValueError, match="Non-QA candidate changes"):
        candidate.verify_checkout(tmp_path, policy, "c" * 40, original, lambda _root: inputs)


def test_local_host_guard_cannot_be_bypassed_by_importing_adapter(tmp_path):
    with pytest.raises(RuntimeError, match="disposable hosted"):
        candidate.require_hosted_output((tmp_path,))


@pytest.mark.parametrize("name", ["../escape.py", "/absolute.py", "C:/escape.py", "x\\escape.py"])
def test_reference_archive_cannot_escape_its_temporary_directory(tmp_path, monkeypatch, name):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        package.writestr(name, b"data")
    archive = output.getvalue()
    if "\\" in name:
        # Windows ZipInfo normalizes separators while writing; simulate external ZIP bytes.
        archive = archive.replace(
            name.replace("\\", "/").encode("utf-8", errors="strict"),
            name.encode("utf-8", errors="strict"),
        )
    monkeypatch.setattr(candidate, "git_bytes", lambda *_args: archive)
    hasher = Mock()
    with pytest.raises(ValueError, match="Unsafe Git reference"):
        candidate.read_commit_inputs(tmp_path, "a" * 40, hasher)
    hasher.assert_not_called()


def test_reference_archive_reuses_original_canonicalizer_without_importing_product(
    tmp_path, monkeypatch
):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        package.writestr("calendar_app/example.py", b"first\r\nsecond\r\n")
    monkeypatch.setattr(candidate, "git_bytes", lambda *_args: output.getvalue())

    def hasher(directory):
        assert (directory / "calendar_app/example.py").read_bytes() == b"first\r\nsecond\r\n"
        return {"from_original_hasher": "normalized"}

    assert candidate.read_commit_inputs(tmp_path, "a" * 40, hasher) == {
        "from_original_hasher": "normalized"
    }


def test_reference_archive_canonicalizes_temporary_root_for_original_hasher(tmp_path, monkeypatch):
    from scripts.manage_version import input_hashes

    contents = b"<Package />\n"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        package.writestr("AppxManifest.xml", contents)
    monkeypatch.setattr(candidate, "git_bytes", lambda *_args: output.getvalue())
    directory = tmp_path / "relative-reference"
    directory.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        candidate.tempfile,
        "TemporaryDirectory",
        lambda **_kwargs: nullcontext("relative-reference"),
    )
    observed = []

    def original_hasher(root):
        observed.append(root)
        return input_hashes(root)

    assert candidate.read_commit_inputs(tmp_path, "a" * 40, original_hasher) == {
        "AppxManifest.xml": hashlib.sha256(contents).hexdigest()
    }
    assert observed == [directory.resolve()]
    assert observed[0].is_absolute()


def test_canonical_reference_root_still_rejects_archive_symlink(tmp_path, monkeypatch):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        link = zipfile.ZipInfo("calendar_app/escape.py")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        package.writestr(link, "../../outside.py")
    monkeypatch.setattr(candidate, "git_bytes", lambda *_args: output.getvalue())
    hasher = Mock()
    with pytest.raises(ValueError, match="Unsafe Git reference"):
        candidate.read_commit_inputs(tmp_path, "a" * 40, hasher)
    hasher.assert_not_called()


def test_policy_pins_existing_build_artifact_and_diagnostic_only():
    path = _PATH.with_name("native-candidate-5.0.0.json")
    assert b"\r" not in path.read_bytes(), "Pinned policy must use exact Git LF bytes"
    policy = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    assert policy["candidate_version"] == "5.0.0"
    assert policy["candidate_run_id"] == 42083557480
    assert policy["candidate_commit"] == "2557dd940015ee7a404966b6ed9ef76cd57e86f1"
    assert policy["product_source_commit"] == "d2b89277c07384e8fbe032ba68754f6212ccda4e"
    assert policy["product_input_count"] == 718
    assert policy["diagnostic_only"] is True
    assert policy["artifacts"]["payload"] == {
        "id": 13442635125,
        "name": "darkcalendar-dist-x64",
        "sha256": "1a85e998516fc269a17ac9b43fd09b91d8264731a595b60b204a8d5a2b3d0bed",
    }
    assert set(policy["qa_sha256"]) == candidate.REQUIRED_QA_HASHES


def test_policy_raw_bytes_equal_git_clean_bytes_before_pinning():
    git = shutil.which("git")
    if git is None:
        pytest.skip("Git is unavailable")
    name = "tests/release_qa/native-candidate-5.0.0.json"
    data = (ROOT / name).read_bytes()
    raw = subprocess.run(
        [git, "hash-object", "--no-filters", "--stdin"],
        cwd=ROOT,
        input=data,
        capture_output=True,
        check=True,
    ).stdout
    committed = subprocess.run(
        [git, "hash-object", "--path", name, "--stdin"],
        cwd=ROOT,
        input=data,
        capture_output=True,
        check=True,
    ).stdout
    assert raw == committed, "Git clean filters would change the policy after its SHA256 was pinned"


def test_new_workflow_is_manual_read_only_no_rebuild_and_always_preserves_evidence():
    value = yaml.safe_load(
        (ROOT / ".github/workflows/verify-native-5-candidate.yml").read_text(
            encoding="utf-8", errors="strict"
        )
    )
    assert value.get("on", value.get(True)) == {"workflow_dispatch": None}
    assert value["permissions"] == {"contents": "read", "actions": "read"}
    job = value["jobs"]["diagnose-native-5-x64"]
    assert job["runs-on"] == "windows-latest"
    assert job["env"]["PYTHON_VERSION"] == "3.14.10"
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    for forbidden in (
        "build-release.bat",
        "build_pipeline.ps1",
        "pyinstaller",
        "prepare_sqlite_build_runtime",
        "gh release",
        "taskkill",
        "Stop-Process",
        "--clobber",
        "-ResetState",
    ):
        assert forbidden not in commands
    assert "native_diagnostic_smoke.py" in commands
    assert "prepare_native_smoke_baseline.py" in commands
    assert "--expected-version 5.0.0" in commands
    assert "check-payload" not in commands  # Use the strict check operation on the same verifier.
    post = next(step for step in job["steps"] if step.get("id") == "payload_after")
    assert post["if"] == "always() && steps.provenance.outcome == 'success'"
    assert "verify_same_payload_candidate.py check" in post["run"]
    assert job["steps"][-1]["if"] == "always()"
    assert "diagnostic-only" in job["steps"][-1]["with"]["name"]
    policy_path = _PATH.with_name("native-candidate-5.0.0.json")
    assert (
        hashlib.sha256(policy_path.read_bytes()).hexdigest()
        == job["env"]["CANDIDATE_POLICY_SHA256"]
    )
    policy = json.loads(policy_path.read_text(encoding="utf-8", errors="strict"))
    for name, expected in policy["qa_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected


def _pinned_policy():
    return json.loads(
        _PATH.with_name("native-candidate-5.0.0.json").read_text(encoding="utf-8", errors="strict")
    )


@pytest.mark.parametrize(
    "path",
    [("product_inputs_sha256",), ("payload_manifest_sha256",)]
    + [("artifacts", role, "sha256") for role in _pinned_policy()["artifacts"]]
    + [("qa_sha256", name) for name in _pinned_policy()["qa_sha256"]],
)
def test_65_character_policy_pin_fails_before_checkout_network_or_app(tmp_path, monkeypatch, path):
    policy = _pinned_policy()
    target = policy
    for name in path[:-1]:
        target = target[name]
    target[path[-1]] = "a" * 65
    checkout = Mock()
    opener = Mock()
    original = Mock()
    input_hasher = Mock()
    monkeypatch.setattr(candidate, "verify_checkout", checkout)
    monkeypatch.setattr(candidate.urllib.request, "build_opener", opener)
    with pytest.raises(ValueError, match="Invalid SHA256 policy pin"):
        candidate.verify_and_download(
            tmp_path, policy, "c" * 40, tmp_path, tmp_path, original, input_hasher
        )
    checkout.assert_not_called()
    opener.assert_not_called()
    input_hasher.assert_not_called()
    assert original.mock_calls == []


@pytest.mark.parametrize("invalid", ["a" * 63, "A" * 64, "g" * 64, None, 123])
def test_policy_pin_requires_exact_lowercase_sha256(invalid):
    policy = _pinned_policy()
    policy["artifacts"]["msix"]["sha256"] = invalid
    with pytest.raises(ValueError, match="artifacts.msix.sha256"):
        candidate.validate_policy_digests(policy)


def test_all_three_policy_artifacts_match_recorded_live_api_metadata():
    from scripts.verify_native_candidate_inputs import validate_artifact

    policy = _pinned_policy()
    candidate.validate_policy_digests(policy)
    assert set(LIVE_ARTIFACT_METADATA) == set(policy["artifacts"])
    for role, metadata in LIVE_ARTIFACT_METADATA.items():
        expected = policy["artifacts"][role]
        result = validate_artifact(metadata, expected, policy)
        assert result["id"] == expected["id"]
        assert result["sha256"] == metadata["digest"].removeprefix("sha256:")
