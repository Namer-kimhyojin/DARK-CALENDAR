# -*- coding: utf-8 -*-
"""Pure file/Git contracts for immutable candidate reuse; no app or DB access."""

import hashlib
import io
import json
import subprocess
import urllib.request
import zipfile

import pytest
from scripts import verify_native_candidate_inputs as candidate


def git(root, *args):
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, check=True)
    return result.stdout.decode("utf-8", errors="strict").strip()


@pytest.fixture
def repository(tmp_path):
    git(tmp_path, "init")
    git(tmp_path, "config", "user.name", "QA")
    git(tmp_path, "config", "user.email", "qa@example.invalid")
    (tmp_path / "calendar_app").mkdir()
    (tmp_path / "calendar_app/app_metadata.py").write_text(
        'APP_VERSION = "4.6.4"\nAPP_NAME = "Air Calendar"\n', encoding="utf-8", errors="strict"
    )
    (tmp_path / "requirements-runtime.lock").write_text(
        "pin==1\n", encoding="utf-8", errors="strict"
    )
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "candidate")
    return tmp_path, {"candidate_commit": git(tmp_path, "rev-parse", "HEAD"), "qa_sha256": {}}


def test_development_version_only_change_can_reuse_candidate(repository):
    root, policy = repository
    path = root / "calendar_app/app_metadata.py"
    path.write_text(
        path.read_text(encoding="utf-8", errors="strict").replace("4.6.4", "4.6.5"),
        encoding="utf-8",
        errors="strict",
    )
    git(root, "add", ".")
    git(root, "commit", "-m", "QA version")
    result = candidate.verify_inputs(root, policy, git(root, "rev-parse", "HEAD"))
    assert result["product_dependency_packaging_inputs_unchanged"]


@pytest.mark.parametrize(
    "name,contents",
    [
        ("requirements-runtime.lock", "pin==2\n"),
        ("calendar_app/app_metadata.py", 'APP_VERSION = "4.6.4"\nAPP_NAME = "Different"\n'),
        ("DarkCalendar.spec", "new packaging\n"),
        ("calendar_app/new_feature.py", "new feature\n"),
        (".github/workflows/build-release.yml", "new pipeline\n"),
    ],
)
def test_product_dependency_or_packaging_change_requires_rebuild(repository, name, contents):
    root, policy = repository
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8", errors="strict")
    git(root, "add", ".")
    git(root, "commit", "-m", "changed input")
    with pytest.raises(ValueError):
        candidate.verify_inputs(root, policy, git(root, "rev-parse", "HEAD"))


def test_dirty_checkout_and_changed_qa_hash_fail_closed(repository):
    root, policy = repository
    (root / "untracked.txt").write_text("dirty", encoding="utf-8", errors="strict")
    with pytest.raises(ValueError, match="clean QA checkout"):
        candidate.verify_inputs(root, policy, policy["candidate_commit"])
    (root / "untracked.txt").unlink()
    policy["qa_sha256"] = {"calendar_app/app_metadata.py": "0" * 64}
    with pytest.raises(ValueError, match="helper hash mismatch"):
        candidate.verify_inputs(root, policy, policy["candidate_commit"])


def test_crlf_checkout_cannot_match_a_different_committed_qa_blob(repository):
    root, policy = repository
    git(root, "config", "core.autocrlf", "true")
    path = root / "scripts/native_release_smoke.py"
    path.parent.mkdir()
    path.write_bytes(b"# QA fixture\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "QA fixture")
    path.write_bytes(b"# QA fixture\r\n")
    policy["qa_sha256"] = {
        "scripts/native_release_smoke.py": hashlib.sha256(path.read_bytes()).hexdigest()
    }
    with pytest.raises(ValueError, match="committed Git bytes"):
        candidate.verify_qa_hashes(root, git(root, "rev-parse", "HEAD"), policy["qa_sha256"])


@pytest.fixture
def artifact():
    expected = {"id": 12, "name": "payload", "sha256": "a" * 64}
    policy = {"candidate_run_id": 20, "candidate_commit": "b" * 40, "repository_id": 30}
    metadata = {
        "id": 12,
        "name": "payload",
        "digest": "sha256:" + "a" * 64,
        "expired": False,
        "workflow_run": {
            "id": 20,
            "head_sha": "b" * 40,
            "repository_id": 30,
            "head_repository_id": 30,
        },
    }
    return metadata, expected, policy


@pytest.mark.parametrize(
    "field,value",
    [("id", 13), ("name", "other"), ("digest", "sha256:" + "0" * 64), ("expired", True)],
)
def test_artifact_metadata_mismatch_is_rejected(artifact, field, value):
    metadata, expected, policy = artifact
    metadata[field] = value
    with pytest.raises(ValueError, match="provenance mismatch"):
        candidate.validate_artifact(metadata, expected, policy)


def test_valid_artifact_records_exact_build_provenance(artifact):
    metadata, expected, policy = artifact
    assert (
        candidate.validate_artifact(metadata, expected, policy)["head_sha"]
        == policy["candidate_commit"]
    )


@pytest.mark.parametrize(
    "field,value",
    [("id", 21), ("head_sha", "c" * 40), ("repository_id", 31), ("head_repository_id", 31)],
)
def test_wrong_run_commit_or_fork_artifact_is_rejected(artifact, field, value):
    metadata, expected, policy = artifact
    metadata["workflow_run"][field] = value
    with pytest.raises(ValueError, match="provenance mismatch"):
        candidate.validate_artifact(metadata, expected, policy)


@pytest.mark.parametrize(
    "name",
    ["../DarkCalendar.exe", "C:/DarkCalendar.exe", "/DarkCalendar.exe", "a\\..\\DarkCalendar.exe"],
)
def test_payload_zip_paths_cannot_escape_destination(tmp_path, name):
    archive = tmp_path / "payload.zip"
    with zipfile.ZipFile(archive, "w") as content:
        content.writestr(name, b"fixture")
    with pytest.raises(ValueError, match="Unsafe"):
        candidate.extract_payload(archive, tmp_path / "payload")
    assert not (tmp_path / "payload").exists()


def test_extraction_preserves_payload_bytes_and_refuses_existing_destination(tmp_path):
    archive = tmp_path / "payload.zip"
    with zipfile.ZipFile(archive, "w") as content:
        content.writestr("DarkCalendar.exe", b"unchanged fixture")
        content.writestr("_internal/sqlite3.dll", b"unchanged library")
    output = tmp_path / "payload"
    manifest = candidate.extract_payload(archive, output)
    assert manifest["DarkCalendar.exe"] == hashlib.sha256(b"unchanged fixture").hexdigest()
    with pytest.raises(ValueError, match="must be new"):
        candidate.extract_payload(archive, output)


def test_redirect_never_forwards_api_token_to_artifact_storage():
    request = urllib.request.Request(
        "https://api.github.com/artifact", headers={"Authorization": "Bearer test-only"}
    )
    redirected = candidate.SafeRedirect().redirect_request(
        request, None, 302, "found", {}, "https://storage.example.invalid/archive.zip"
    )
    assert not redirected.has_header("Authorization")
    with pytest.raises(ValueError, match="HTTPS"):
        candidate.SafeRedirect().redirect_request(
            request, None, 302, "found", {}, "http://unsafe.invalid"
        )


def test_raw_archive_hash_mismatch_prevents_extraction(tmp_path, monkeypatch, artifact):
    metadata, expected, base_policy = artifact
    policy = {
        **base_policy,
        "repository": "owner/repo",
        "candidate_version": "4.6.4",
        "artifacts": {"payload": expected},
        "qa_sha256": {},
    }
    monkeypatch.setattr(candidate, "verify_inputs", lambda *_args: {})
    monkeypatch.setenv("GITHUB_TOKEN", "test-only")

    class Opener:
        def open(self, request, timeout):
            return io.BytesIO(
                b"wrong archive"
                if request.full_url.endswith("/zip")
                else json.dumps(metadata).encode("utf-8", errors="strict")
            )

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_args: Opener())
    monkeypatch.setattr(
        candidate, "extract_payload", lambda *_args: pytest.fail("must not extract")
    )
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        candidate.verify_and_download(tmp_path, policy, "c" * 40, tmp_path, tmp_path / "payload")
