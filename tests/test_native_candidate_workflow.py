# -*- coding: utf-8 -*-
"""The candidate-only workflow never rebuilds or publishes a release."""

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "scripts/native-candidate-4.7.1.json"


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
    assert job["env"]["CANDIDATE_VERSION"] == "4.7.1"
    assert value["concurrency"] == {
        "group": "verify-native-candidate-4.7.1",
        "cancel-in-progress": False,
    }
    checkout = next(
        step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@")
    )
    assert checkout["with"]["fetch-depth"] == 0


def test_disposable_vm_sets_exact_git_bytes_before_checkout():
    steps = workflow()["jobs"]["verify-native-candidate-x64"]["steps"]
    assert "git config --global core.autocrlf false" in steps[0]["run"]
    assert "git config --global core.eol lf" in steps[0]["run"]
    assert steps[1]["uses"].startswith("actions/checkout@")
    assert b"\r\n" not in POLICY.read_bytes()


def test_previous_candidate_policy_is_preserved_as_historical_evidence():
    original = ROOT / "scripts/native-candidate-4.6.4.json"
    assert hashlib.sha256(original.read_bytes()).hexdigest() == (
        "2da9c6e400ad876797fd886c6c58104605bff8bd66eb64c6633521fdf8d31bbd"
    )


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
    job = workflow()["jobs"]["verify-native-candidate-x64"]
    assert hashlib.sha256(POLICY.read_bytes()).hexdigest() == job["env"]["CANDIDATE_POLICY_SHA256"]
    policy = json.loads(POLICY.read_text(encoding="utf-8", errors="strict"))
    assert policy["candidate_version"] == job["env"]["CANDIDATE_VERSION"] == "4.7.1"
    assert policy["repository"] == "Namer-kimhyojin/DARK-CALENDAR"
    assert policy["repository_id"] == 1195286732
    assert policy["candidate_run_id"] == 39536866518
    assert policy["candidate_commit"] == "6329be6f8a0b91946837289f44d56637b9a91636"
    assert policy["artifacts"] == {
        "payload": {
            "id": 12318496336,
            "name": "darkcalendar-dist-x64",
            "sha256": "c5342ecbd38f20b126818738b7a58b1940e5c6cbb253d8a949dbda4c2f02b337",
        },
        "msix": {
            "id": 12318441527,
            "name": "darkcalendar-msix-x64",
            "sha256": "f483c06b9871233450cc9af60e7616b485a5ec1973f7aec08a78b2979e541129",
        },
        "release_assets": {
            "id": 12318456483,
            "name": "darkcalendar-github-release-x64",
            "sha256": "ae63dbcc8d268e6c21bef445aede7498cba41b55462aa8ba94fd274348f3873c",
        },
    }
    assert set(policy["qa_sha256"]) == {
        "scripts/native_exception_observer.py",
        "scripts/native_release_smoke.py",
        "scripts/prepare_native_smoke_baseline.py",
        "scripts/sqlite-runtime-lock.json",
        "scripts/verify_native_candidate_inputs.py",
        "scripts/verify_sqlite_runtime.py",
    }
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
    assert "--policy scripts\\native-candidate-4.7.1.json" in steps[checks]["run"]
    assert "if ($LASTEXITCODE -ne 0)" in steps[checks]["run"]
    evidence = steps[-1]
    assert evidence["if"] == "always()"
    assert evidence["with"]["name"] == "darkcalendar-native-candidate-4.7.1-evidence-x64"
    assert "candidate-reuse-provenance.json" in evidence["with"]["path"]
    assert "native-release-evidence" in evidence["with"]["path"]
