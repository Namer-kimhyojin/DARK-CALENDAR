# -*- coding: utf-8 -*-
"""Pin and reuse the existing 5.0.0 artifact; never rebuild or publish anything."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

QA_FILES = frozenset(
    {
        ".github/workflows/verify-native-5-candidate.yml",
        "tests/release_qa/native_capture_diagnostics.py",
        "tests/release_qa/native_diagnostic_smoke.py",
        "tests/release_qa/verify_same_payload_candidate.py",
        "tests/release_qa/native-candidate-5.0.0.json",
        "tests/release_qa/test_native_capture_diagnostics.py",
        "tests/release_qa/test_same_payload_candidate.py",
    }
)
REQUIRED_QA_HASHES = frozenset(
    {
        "scripts/manage_version.py",
        "scripts/verify_native_candidate_inputs.py",
        "scripts/native_release_smoke.py",
        "scripts/native_exception_observer.py",
        "scripts/prepare_native_smoke_baseline.py",
        "scripts/verify_sqlite_runtime.py",
        "scripts/sqlite-runtime-lock.json",
        "tests/release_qa/native_release_smoke_adapter.py",
        "tests/release_qa/native_capture_diagnostics.py",
        "tests/release_qa/native_diagnostic_smoke.py",
        "tests/release_qa/verify_same_payload_candidate.py",
    }
)


def canonical_digest(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8", errors="strict")
    return hashlib.sha256(data).hexdigest()


def git_bytes(root, *arguments):
    return subprocess.run(["git", *arguments], cwd=root, capture_output=True, check=True).stdout


def read_commit_inputs(root, commit, input_hasher):
    """Use the original canonical hasher on an exact, temporary Git archive."""
    if re.fullmatch(r"[a-f0-9]{40}", commit) is None:
        raise ValueError("Reference commit must be a full SHA")
    archive = git_bytes(root, "archive", "--format=zip", commit)
    with tempfile.TemporaryDirectory(prefix="air-candidate-reference-") as name:
        directory = Path(name)
        with zipfile.ZipFile(io.BytesIO(archive)) as package:
            for member in package.infolist():
                name = member.orig_filename
                path = PurePosixPath(name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or ":" in name
                    or "\\" in name
                    or "\x00" in name
                    or stat.S_ISLNK(member.external_attr >> 16)
                ):
                    raise ValueError("Unsafe Git reference archive")
            package.extractall(directory)
        return input_hasher(directory)


def verify_product_inputs(root, policy, input_hasher, reference_reader=read_commit_inputs):
    expected_count = policy["product_input_count"]
    expected_digest = policy["product_inputs_sha256"]
    snapshots = {
        "immutable_source": reference_reader(root, policy["product_source_commit"], input_hasher),
        "artifact_build": reference_reader(root, policy["candidate_commit"], input_hasher),
        "qa_checkout": input_hasher(root),
    }
    for label, inputs in snapshots.items():
        if len(inputs) != expected_count or canonical_digest(inputs) != expected_digest:
            raise ValueError(f"Canonical product input mismatch: {label}")
    return {
        "count": expected_count,
        "sha256": expected_digest,
        "immutable_source_commit": policy["product_source_commit"],
        "artifact_build_commit": policy["candidate_commit"],
        "all_three_snapshots_equal": True,
    }


def verify_checkout(root, policy, qa_commit, original, input_hasher):
    for commit in (qa_commit, policy["candidate_commit"], policy["product_source_commit"]):
        if re.fullmatch(r"[a-f0-9]{40}", commit) is None:
            raise ValueError("Expected exact committed SHA values")
    if original.git(root, "rev-parse", "HEAD").strip() != qa_commit:
        raise ValueError("Checkout is not the requested QA commit")
    if original.git(root, "status", "--porcelain", "--untracked-files=all").strip():
        raise ValueError("Same-payload verification requires a clean QA checkout")
    original.git(
        root,
        "merge-base",
        "--is-ancestor",
        policy["product_source_commit"],
        policy["candidate_commit"],
    )
    original.git(root, "merge-base", "--is-ancestor", policy["candidate_commit"], qa_commit)
    changes = original.git(
        root, "diff", "--name-only", policy["candidate_commit"], qa_commit
    ).splitlines()
    unexpected = set(changes) - QA_FILES
    if unexpected:
        raise ValueError("Non-QA candidate changes: " + ", ".join(sorted(unexpected)))
    if set(policy["qa_sha256"]) != REQUIRED_QA_HASHES:
        raise ValueError("Policy must pin the exact executable QA dependency set")
    original.verify_qa_hashes(root, qa_commit, policy["qa_sha256"])
    # Pin the original canonicalizer to the immutable product source as well.
    for commit in (policy["product_source_commit"], policy["candidate_commit"]):
        source = git_bytes(root, "show", f"{commit}:scripts/manage_version.py")
        if hashlib.sha256(source).hexdigest() != policy["qa_sha256"]["scripts/manage_version.py"]:
            raise ValueError("Product canonicalizer differs from immutable source")
    return {
        "candidate_commit": policy["candidate_commit"],
        "qa_commit": qa_commit,
        "qa_only_changes": changes,
        "product_inputs": verify_product_inputs(root, policy, input_hasher),
    }


def verify_and_download(root, policy, qa_commit, evidence, payload, original, input_hasher):
    result = verify_checkout(root, policy, qa_commit, original, input_hasher)
    opener = urllib.request.build_opener(original.SafeRedirect())
    metadata = {}
    for role, expected in policy["artifacts"].items():
        with opener.open(original.api_request(policy, str(expected["id"])), timeout=60) as response:
            value = json.loads(response.read().decode("utf-8", errors="replace"))
        metadata[role] = original.validate_artifact(value, expected, policy)
    expected = policy["artifacts"]["payload"]
    archive = evidence / "candidate-payload.zip"
    with (
        opener.open(original.api_request(policy, f"{expected['id']}/zip"), timeout=60) as response,
        archive.open("xb") as output,
    ):
        while block := response.read(1024 * 1024):
            output.write(block)
    if original.sha256(archive) != expected["sha256"]:
        raise ValueError("Pinned raw artifact ZIP SHA256 mismatch")
    manifest = original.extract_payload(archive, payload)
    if (
        len(manifest) != policy["payload_file_count"]
        or canonical_digest(manifest) != policy["payload_manifest_sha256"]
    ):
        raise ValueError("Extracted payload differs from the original native-gate manifest")
    result.update(
        passed=True,
        candidate_version=policy["candidate_version"],
        candidate_run_id=policy["candidate_run_id"],
        artifacts=metadata,
        raw_payload_sha256=expected["sha256"],
        payload_manifest=manifest,
        payload_manifest_sha256=canonical_digest(manifest),
        payload_file_count=len(manifest),
        payload_rebuilt=False,
        auto_publication=False,
        diagnostic_only=bool(policy["diagnostic_only"]),
        publication_eligible=False,
    )
    return result


def check_payload_unchanged(payload, provenance, policy, manifest_reader):
    if not provenance.get("passed"):
        raise ValueError("No successful pinned-candidate provenance exists")
    current = manifest_reader(payload)
    if (
        current != provenance["payload_manifest"]
        or len(current) != policy["payload_file_count"]
        or canonical_digest(current) != policy["payload_manifest_sha256"]
    ):
        raise ValueError("Candidate payload changed during native validation")
    return {
        "passed": True,
        "payload_unchanged": True,
        "payload_manifest_sha256": canonical_digest(current),
    }


def require_hosted_output(paths):
    required = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_OS": "Windows",
    }
    if sys.platform != "win32" or any(
        os.environ.get(key) != value for key, value in required.items()
    ):
        raise RuntimeError("Same-payload QA runs only on a disposable hosted Windows VM")
    temporary = Path(os.environ["RUNNER_TEMP"]).resolve()
    for path in paths:
        resolved = path.resolve()
        if resolved == temporary or not resolved.is_relative_to(temporary):
            raise ValueError("QA output must remain in a child of RUNNER_TEMP")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "check"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--policy-sha256", required=True)
    parser.add_argument("--qa-commit", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--payload", type=Path, required=True)
    args = parser.parse_args(argv)
    require_hosted_output((args.evidence, args.payload))
    root = args.root.resolve()
    sys.path.insert(0, str(root))
    from scripts import manage_version
    from scripts import verify_native_candidate_inputs as original

    if original.sha256(args.policy) != args.policy_sha256:
        raise ValueError("Pinned QA policy SHA256 mismatch")
    policy = json.loads(args.policy.read_text(encoding="utf-8", errors="strict"))
    args.evidence.mkdir(parents=True, exist_ok=True)
    result = {"passed": False, "qa_commit": args.qa_commit}
    path = args.evidence / (
        "candidate-reuse-provenance.json"
        if args.operation == "prepare"
        else "payload-after-native.json"
    )
    try:
        if args.operation == "prepare":
            result = verify_and_download(
                root,
                policy,
                args.qa_commit,
                args.evidence,
                args.payload,
                original,
                manage_version.input_hashes,
            )
        else:
            from scripts.native_release_smoke import payload_manifest

            provenance = json.loads(
                (args.evidence / "candidate-reuse-provenance.json").read_text(
                    encoding="utf-8", errors="strict"
                )
            )
            result = check_payload_unchanged(args.payload, provenance, policy, payload_manifest)
        result["policy_sha256"] = args.policy_sha256
    except Exception as error:
        result["error_type"] = type(error).__name__
        if isinstance(error, ValueError):
            result["error"] = str(error)
        raise
    finally:
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", errors="strict")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
