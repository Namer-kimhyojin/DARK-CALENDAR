# -*- coding: utf-8 -*-
"""Validate the existing clean 5.0.0 bytes without rebuilding or publishing."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
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
        ".github/workflows/verify-native-5-final.yml",
        "tests/release_qa/verify_final_candidate.py",
        "tests/release_qa/native_final_smoke.py",
        "tests/release_qa/native-final-5.0.0.json",
        "tests/release_qa/test_final_candidate.py",
        "tests/release_qa/native_capture_diagnostics.py",
        "tests/release_qa/native_modal_owner_adapter.py",
        "tests/release_qa/test_native_modal_owner_adapter.py",
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
        "requirements-build.lock",
        "tests/release_qa/native_release_smoke_adapter.py",
        "tests/release_qa/native_capture_diagnostics.py",
        "tests/release_qa/native_modal_owner_adapter.py",
        "tests/release_qa/native_final_smoke.py",
        "tests/release_qa/verify_final_candidate.py",
    }
)
ARTIFACT_NAMES = {
    "payload": "darkcalendar-dist-x64",
    "msix": "darkcalendar-msix-x64",
    "release_assets": "darkcalendar-github-release-x64",
}
QA_MODULE_PATTERNS = ("sitecustomize", "release_qa", "fingerprint_compat", "qa_loader", "qaloader")


def canonical_digest(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8", errors="strict")
    return hashlib.sha256(data).hexdigest()


def validate_policy(policy):
    if (
        policy.get("schema_version") != 1
        or policy.get("diagnostic_only") is not False
        or policy.get("publication_eligible") is not False
        or policy.get("qa_pins_finalized") is not True
        or policy.get("draft", False) is not False
        or policy.get("required_native_cycles") != 6
    ):
        raise ValueError("Final policy must be frozen clean mode with publication blocked")
    if set(policy.get("artifacts", {})) != set(ARTIFACT_NAMES):
        raise ValueError("Final policy must pin exactly three build artifacts")
    for role, name in ARTIFACT_NAMES.items():
        artifact = policy["artifacts"][role]
        if artifact.get("name") != name or type(artifact.get("id")) is not int:
            raise ValueError("Unexpected final artifact role or ID")
    if set(policy.get("qa_sha256", {})) != REQUIRED_QA_HASHES:
        raise ValueError("Final policy must pin every executable QA dependency exactly")
    if policy.get("product_input_count") != 718 or policy.get("payload_file_count") != 1877:
        raise ValueError("Unexpected clean final product or payload input count")
    digests = {
        "product_inputs_sha256": policy["product_inputs_sha256"],
        "payload_manifest_sha256": policy["payload_manifest_sha256"],
        "payload_exe_sha256": policy["payload_exe_sha256"],
        **{f"artifacts.{key}": value["sha256"] for key, value in policy["artifacts"].items()},
        **{f"qa.{key}": value for key, value in policy["qa_sha256"].items()},
    }
    if any(
        not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
        for value in digests.values()
    ):
        raise ValueError("Invalid final SHA256 pin; every digest must have 64 hex characters")
    for name in ("candidate_commit", "product_source_commit"):
        if re.fullmatch(r"[0-9a-f]{40}", policy.get(name, "")) is None:
            raise ValueError("Final policy requires exact Git commit IDs")


def git_bytes(root, *arguments):
    return subprocess.run(["git", *arguments], cwd=root, capture_output=True, check=True).stdout


def read_commit_inputs(root, commit, input_hasher):
    archive = git_bytes(root, "archive", "--format=zip", commit)
    with tempfile.TemporaryDirectory(prefix="air-final-reference-") as temporary:
        directory = Path(temporary).resolve()
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
                    or not (directory / name).resolve().is_relative_to(directory)
                ):
                    raise ValueError("Unsafe final reference Git archive")
            package.extractall(directory)
        return input_hasher(directory)


def verify_product_inputs(root, policy, input_hasher, reference_reader=read_commit_inputs):
    snapshots = {
        "immutable_source": reference_reader(root, policy["product_source_commit"], input_hasher),
        "artifact_build": reference_reader(root, policy["candidate_commit"], input_hasher),
        "qa_checkout": input_hasher(root),
    }
    for label, values in snapshots.items():
        if (
            len(values) != policy["product_input_count"]
            or canonical_digest(values) != policy["product_inputs_sha256"]
        ):
            raise ValueError(f"Canonical final product input mismatch: {label}")
    return {
        "count": policy["product_input_count"],
        "sha256": policy["product_inputs_sha256"],
        "all_three_snapshots_equal": True,
    }


def verify_checkout(root, policy, qa_commit, original, input_hasher):
    validate_policy(policy)
    if re.fullmatch(r"[0-9a-f]{40}", qa_commit) is None:
        raise ValueError("Exact final QA commit is required")
    if original.git(root, "rev-parse", "HEAD").strip() != qa_commit:
        raise ValueError("Checkout differs from requested final QA commit")
    if original.git(root, "status", "--porcelain", "--untracked-files=all").strip():
        raise ValueError("Final validation requires a clean committed QA checkout")
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
    if set(changes) - QA_FILES:
        raise ValueError("Final checkout contains changes outside the exact final QA allowlist")
    original.verify_qa_hashes(root, qa_commit, policy["qa_sha256"])
    for commit in (policy["product_source_commit"], policy["candidate_commit"]):
        canonicalizer = git_bytes(root, "show", f"{commit}:scripts/manage_version.py")
        if (
            hashlib.sha256(canonicalizer).hexdigest()
            != policy["qa_sha256"]["scripts/manage_version.py"]
        ):
            raise ValueError("Canonical product hasher differs from an immutable commit")
    return {
        "candidate_commit": policy["candidate_commit"],
        "qa_commit": qa_commit,
        "qa_only_changes": changes,
        "product_inputs": verify_product_inputs(root, policy, input_hasher),
    }


def inspect_no_qa_modules(
    payload, policy, *, archive_reader=None, version_reader=importlib.metadata.version
):
    if version_reader("pyinstaller") != policy["pyinstaller_version"]:
        raise ValueError("Archive reader differs from pinned build-lock PyInstaller")
    if archive_reader is None:
        from PyInstaller.archive.readers import CArchiveReader

        archive_reader = CArchiveReader
    executable = payload / "DarkCalendar.exe"
    if hashlib.sha256(executable.read_bytes()).hexdigest() != policy["payload_exe_sha256"]:
        raise ValueError("Clean executable differs from final policy")
    archive = archive_reader(str(executable))
    pyz_names = [name for name in archive.toc if name.casefold().endswith(".pyz")]
    if len(pyz_names) != 1:
        raise ValueError("Final executable must contain exactly one PYZ archive")
    pyz = archive.open_embedded_archive(pyz_names[0])
    with zipfile.ZipFile(payload / "_internal/base_library.zip") as library:
        names = {
            "carchive": list(archive.toc),
            "pyz": list(pyz.toc),
            "base_library": library.namelist(),
            "disk": [
                path.relative_to(payload).as_posix()
                for path in payload.rglob("*")
                if path.is_file()
            ],
        }
    matches = {
        kind: [
            name
            for name in values
            if any(pattern in name.casefold() for pattern in QA_MODULE_PATTERNS)
        ]
        for kind, values in names.items()
    }
    if any(matches.values()):
        raise ValueError("QA-only module found in final CArchive, PYZ, base library or disk")
    return {
        "passed": True,
        "exe_sha256": policy["payload_exe_sha256"],
        "counts": {kind: len(values) for kind, values in names.items()},
        "matches": matches,
        "exe_executed": False,
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
        raise ValueError("Final raw artifact ZIP SHA256 mismatch")
    manifest = original.extract_payload(archive, payload)
    if (
        len(manifest) != policy["payload_file_count"]
        or canonical_digest(manifest) != policy["payload_manifest_sha256"]
    ):
        raise ValueError("Final payload differs from the original 1877-file manifest")
    no_qa = inspect_no_qa_modules(payload, policy)
    result.update(
        passed=True,
        candidate_version=policy["candidate_version"],
        candidate_run_id=policy["candidate_run_id"],
        artifacts=metadata,
        raw_payload_sha256=expected["sha256"],
        payload_manifest=manifest,
        payload_manifest_sha256=canonical_digest(manifest),
        payload_file_count=len(manifest),
        no_qa_modules=no_qa,
        payload_rebuilt=False,
        diagnostic_only=False,
        publication_eligible=False,
        auto_publication=False,
    )
    return result


def check_payload_unchanged(payload, provenance, policy, manifest_reader):
    if (
        provenance.get("passed") is not True
        or provenance.get("diagnostic_only") is not False
        or provenance.get("no_qa_modules", {}).get("passed") is not True
    ):
        raise ValueError("No successful clean final provenance exists")
    manifest = manifest_reader(payload)
    if (
        manifest != provenance["payload_manifest"]
        or len(manifest) != policy["payload_file_count"]
        or canonical_digest(manifest) != policy["payload_manifest_sha256"]
    ):
        raise ValueError("Final payload changed during native validation")
    return {
        "passed": True,
        "payload_unchanged": True,
        "payload_file_count": len(manifest),
        "payload_manifest_sha256": canonical_digest(manifest),
        "diagnostic_only": False,
        "publication_eligible": False,
    }


def verify_six_cycles(summary, policy):
    expected = {(scenario, launch) for scenario in ("fresh", "upgrade") for launch in (1, 2, 3)}
    cycles = summary.get("cycles", [])
    if (
        summary.get("passed") is not True
        or summary.get("candidate_payload_unchanged") is not True
        or len(cycles) != 6
        or {(cycle.get("scenario"), cycle.get("launch")) for cycle in cycles} != expected
    ):
        raise ValueError("The exact original six successful native cycles are required")
    for cycle in cycles:
        database = cycle.get("database", {})
        if (
            cycle.get("passed") is not True
            or cycle.get("normal_exit") is not True
            or type(cycle.get("exit_code")) is not int
            or cycle["exit_code"] != 0
            or cycle.get("force_killed") is not False
            or cycle.get("exe_sha256") != policy["payload_exe_sha256"]
            or database.get("integrity_check") != "ok"
            or database.get("foreign_key_violations") != 0
        ):
            raise ValueError(
                "Native cycle lacks clean normal exit, correct bytes or database integrity"
            )
        fixture = cycle["scenario"] == "upgrade" or cycle["launch"] > 1
        if database.get("fixture_preserved") is not fixture:
            raise ValueError(
                "Native synthetic data preservation differs from the original scenario"
            )
    return {
        "passed": True,
        "native_gate_passed": True,
        "native_cycles": 6,
        "diagnostic_only": False,
        "publication_eligible": False,
        "release_complete": False,
        "screenshots_reviewed": False,
        "summary_ko": "동일 clean 페이로드의 여섯 native 게이트를 통과했습니다. 실제 화면 검토와 게시 단계는 별도입니다.",
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
        raise RuntimeError("Final validation runs only in a disposable hosted Windows job")
    temporary = Path(os.environ["RUNNER_TEMP"]).resolve()
    if any(
        path.resolve() == temporary or not path.resolve().is_relative_to(temporary)
        for path in paths
    ):
        raise ValueError("Final outputs must remain in child directories of RUNNER_TEMP")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("inputs", "prepare", "check", "accept"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--policy-sha256", required=True)
    parser.add_argument("--qa-commit", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--native-summary", type=Path)
    args = parser.parse_args(argv)
    require_hosted_output((args.evidence, args.payload))
    root = args.root.resolve()
    sys.path.insert(0, str(root))
    from scripts import manage_version
    from scripts import verify_native_candidate_inputs as original

    if original.sha256(args.policy) != args.policy_sha256:
        raise ValueError("Pinned final policy SHA256 mismatch")
    policy = json.loads(args.policy.read_text(encoding="utf-8", errors="strict"))
    args.evidence.mkdir(parents=True, exist_ok=True)
    filenames = {
        "inputs": "candidate-input-provenance.json",
        "prepare": "candidate-reuse-provenance.json",
        "check": "payload-after-native.json",
        "accept": "final-native-acceptance.json",
    }
    result = {
        "passed": False,
        "diagnostic_only": False,
        "publication_eligible": False,
        "qa_commit": args.qa_commit,
        "summary_ko": "clean 후보 검증을 완료하지 못했습니다.",
    }
    try:
        validate_policy(policy)
        if args.operation == "inputs":
            result = {
                "passed": True,
                **verify_checkout(
                    root, policy, args.qa_commit, original, manage_version.input_hashes
                ),
            }
        elif args.operation == "prepare":
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
            original.verify_qa_hashes(root, args.qa_commit, policy["qa_sha256"])
            current_inputs = manage_version.input_hashes(root)
            if (
                len(current_inputs) != policy["product_input_count"]
                or canonical_digest(current_inputs) != policy["product_inputs_sha256"]
            ):
                raise ValueError("Canonical product inputs changed during final native validation")
            from scripts.native_release_smoke import payload_manifest

            provenance = json.loads(
                (args.evidence / "candidate-reuse-provenance.json").read_text(
                    encoding="utf-8", errors="strict"
                )
            )
            if (
                provenance.get("policy_sha256") != args.policy_sha256
                or provenance.get("qa_commit") != args.qa_commit
            ):
                raise ValueError("Final provenance belongs to a different policy or QA commit")
            result = check_payload_unchanged(args.payload, provenance, policy, payload_manifest)
            if args.operation == "accept":
                if not args.native_summary:
                    raise ValueError("Final acceptance requires the native summary")
                summary = json.loads(
                    args.native_summary.read_text(encoding="utf-8", errors="strict")
                )
                result.update(verify_six_cycles(summary, policy))
        result.update(
            policy_sha256=args.policy_sha256,
            qa_commit=args.qa_commit,
            diagnostic_only=False,
            publication_eligible=False,
        )
        result.setdefault(
            "summary_ko",
            "동일 clean 후보의 해당 검증 단계를 통과했습니다. 게시 완료를 의미하지 않습니다.",
        )
    except Exception as error:
        result.update(passed=False, error_type=type(error).__name__)
        if isinstance(error, ValueError):
            result["error"] = str(error)
        raise
    finally:
        (args.evidence / filenames[args.operation]).write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            errors="strict",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
