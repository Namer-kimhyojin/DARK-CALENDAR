# -*- coding: utf-8 -*-
"""The native gate consumes the built payload in a separate disposable VM."""

from pathlib import Path

import yaml


def workflow():
    source = Path(__file__).resolve().parents[1] / ".github/workflows/build-release.yml"
    return yaml.safe_load(source.read_text(encoding="utf-8", errors="strict"))


def commands(job):
    return "\n".join(step.get("run", "") for step in job["steps"])


def test_native_validation_has_its_own_hosted_vm_after_build():
    jobs = workflow()["jobs"]
    native = jobs["verify-native-x64"]
    assert native["runs-on"] == "windows-latest"
    assert native["needs"] == ["build-x64"]
    assert "native_release_smoke.py" not in commands(jobs["build-x64"])
    assert "build-release.bat" not in commands(native)
    assert "prepare_sqlite_build_runtime.py" not in commands(native)


def test_native_job_downloads_the_same_workflow_payload_without_rebuilding():
    jobs = workflow()["jobs"]
    producers = [
        step
        for step in jobs["build-x64"]["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
        and step["with"].get("name") == "darkcalendar-dist-x64"
    ]
    consumers = [
        step
        for step in jobs["verify-native-x64"]["steps"]
        if step.get("uses", "").startswith("actions/download-artifact@")
    ]
    assert len(producers) == len(consumers) == 1
    assert producers[0]["with"]["name"] == consumers[0]["with"]["name"]
    assert consumers[0]["with"]["path"] == "native-payload"
    assert not {"run-id", "repository", "github-token"} & consumers[0]["with"].keys()
    assert "--payload native-payload" in commands(jobs["verify-native-x64"])


def test_native_job_uses_same_commit_and_pinned_python_only_for_qa_dependencies():
    configuration = workflow()
    native = configuration["jobs"]["verify-native-x64"]
    checkout = next(
        step for step in native["steps"] if step.get("uses", "").startswith("actions/checkout@")
    )
    assert "ref" not in checkout.get("with", {})
    python = next(
        step for step in native["steps"] if step.get("uses", "").startswith("actions/setup-python@")
    )
    assert python["with"]["python-version"] == "${{ env.PYTHON_VERSION }}"
    assert configuration["env"]["PYTHON_VERSION"] == "3.13.15"
    assert "python -m venv build\\native-smoke-venv" in commands(native)
    assert "pywinauto==0.6.9 Pillow==13.0.0 psutil==7.2.2" in commands(native)
    assert "requirements-build.lock" not in commands(native)


def test_native_failure_evidence_is_always_uploaded():
    native = workflow()["jobs"]["verify-native-x64"]
    evidence = next(
        step
        for step in native["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
    )
    assert evidence["if"] == "always()"
    assert evidence["with"]["name"] == "darkcalendar-native-runtime-evidence-x64"
    assert evidence["with"]["path"] == "${{ runner.temp }}/native-release-evidence"


def test_publishing_requires_successful_build_and_native_validation():
    publication = workflow()["jobs"]["publish-github-release"]
    assert set(publication["needs"]) == {"build-x64", "verify-native-x64"}
    assert "always()" not in publication.get("if", "")
    assert "--draft" in commands(publication)
    assert "--clobber" not in commands(publication)


def test_isolation_does_not_reset_existing_registry_database_or_processes():
    native = commands(workflow()["jobs"]["verify-native-x64"])
    for dangerous in (
        "Remove-Item",
        "reg delete",
        "Stop-Process",
        "taskkill",
        "-ResetState",
        "-PurgeLocalData",
    ):
        assert dangerous not in native
