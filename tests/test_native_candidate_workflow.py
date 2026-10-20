# -*- coding: utf-8 -*-
"""The candidate-only workflow never rebuilds or publishes a release."""

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def workflow():
    return yaml.safe_load(
        (ROOT / ".github/workflows/verify-native-candidate.yml").read_text(
            encoding="utf-8", errors="strict"
        )
    )


def test_candidate_workflow_is_manual_read_only_on_fresh_hosted_vm():
    value = workflow()
    trigger = value.get("on", value.get(True))
    assert trigger == {"workflow_dispatch": None}
    assert value["permissions"] == {"contents": "read", "actions": "read"}
    assert len(value["jobs"]) == 1
    job = value["jobs"]["verify-native-candidate-x64"]
    assert job["runs-on"] == "windows-latest"
    assert job["env"]["CANDIDATE_VERSION"] == "4.6.4"
    checkout = next(
        step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@")
    )
    assert checkout["with"]["fetch-depth"] == 0


def test_disposable_vm_sets_exact_git_bytes_before_checkout():
    steps = workflow()["jobs"]["verify-native-candidate-x64"]["steps"]
    assert "git config --global core.autocrlf false" in steps[0]["run"]
    assert "git config --global core.eol lf" in steps[0]["run"]
    assert steps[1]["uses"].startswith("actions/checkout@")
    assert b"\r\n" not in (ROOT / "scripts/native-candidate-4.6.4.json").read_bytes()


def test_candidate_job_cannot_build_modify_payload_or_publish():
    commands = "\n".join(
        step.get("run", "") for job in workflow()["jobs"].values() for step in job["steps"]
    )
    for forbidden in (
        "build-release.bat",
        "build_pipeline.ps1",
        "pyinstaller",
        "prepare_sqlite_build_runtime",
        "gh release",
        "--clobber",
        "Stop-Process",
        "taskkill",
        "-ResetState",
        "-PurgeLocalData",
    ):
        assert forbidden not in commands
    assert "requirements-build.lock" not in commands
    assert "--expected-version $env:CANDIDATE_VERSION" in commands


def test_candidate_policy_hash_and_qa_helper_hashes_are_pinned():
    path = ROOT / "scripts/native-candidate-4.6.4.json"
    job = workflow()["jobs"]["verify-native-candidate-x64"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == job["env"]["CANDIDATE_POLICY_SHA256"]
    policy = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    assert policy["candidate_run_id"] == 39355773285
    assert policy["candidate_commit"] == "4748f903b3fcb312977a227d765d49c903b8a4c7"
    assert set(policy["artifacts"]) == {"payload", "msix", "release_assets"}
    assert "scripts/native_exception_observer.py" in policy["qa_sha256"]
    assert "scripts/verify_native_candidate_inputs.py" in policy["qa_sha256"]
    for name, digest in policy["qa_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest


def test_native_launch_is_after_provenance_and_evidence_is_always_preserved():
    steps = workflow()["jobs"]["verify-native-candidate-x64"]["steps"]
    checks = next(
        i
        for i, step in enumerate(steps)
        if "verify_native_candidate_inputs.py" in step.get("run", "")
    )
    launch = next(
        i for i, step in enumerate(steps) if "native_release_smoke.py" in step.get("run", "")
    )
    assert checks < launch
    assert "if ($LASTEXITCODE -ne 0)" in steps[checks]["run"]
    evidence = steps[-1]
    assert evidence["if"] == "always()"
    assert "candidate-reuse-provenance.json" in evidence["with"]["path"]
    assert "native-release-evidence" in evidence["with"]["path"]
