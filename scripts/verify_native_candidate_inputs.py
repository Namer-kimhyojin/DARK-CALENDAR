# -*- coding: utf-8 -*-
"""Verify a pinned built candidate before a separate disposable native QA job."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import urllib.parse
import urllib.request
import zipfile

QA_FILES = frozenset(
    {
        ".github/workflows/verify-native-candidate.yml",
        "scripts/verify_native_candidate_inputs.py",
        "scripts/native-candidate-4.6.4.json",
        "scripts/native-candidate-4.7.1.json",
        "scripts/native_release_smoke.py",
        "scripts/native_exception_observer.py",
        "tests/test_native_release_smoke.py",
        "tests/test_native_exception_observer.py",
        "tests/test_native_candidate_workflow.py",
        "tests/test_verify_native_candidate_inputs.py",
        "rules/store_release_process.md",
    }
)
VERSION_FILES = frozenset(
    {"calendar_app/app_metadata.py", "pyproject.toml", "AppxManifest.xml", "version_info.txt"}
)
HISTORY_FILES = frozenset({"version-history.json", "docs/maintenance/version-history.md"})
REQUIRED_QA_HASHES = frozenset(
    {
        "scripts/verify_native_candidate_inputs.py",
        "scripts/native_release_smoke.py",
        "scripts/native_exception_observer.py",
        "scripts/prepare_native_smoke_baseline.py",
        "scripts/verify_sqlite_runtime.py",
        "scripts/sqlite-runtime-lock.json",
    }
)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(["git", *arguments], cwd=root, capture_output=True, check=True)
    return result.stdout.decode("utf-8", errors="strict").replace("\r\n", "\n")


def version_normalized(name: str, text: str) -> str:
    if name == "calendar_app/app_metadata.py":
        patterns = [r'(?m)^APP_VERSION = "[0-9]+\.[0-9]+\.[0-9]+"$']
    elif name == "pyproject.toml":
        patterns = [r'(?m)^version = "[0-9]+\.[0-9]+\.[0-9]+"$']
    elif name == "AppxManifest.xml":
        matches = list(
            re.finditer(r'<Identity\b[^>]*\bVersion="([0-9]+\.[0-9]+\.[0-9]+\.0)"', text)
        )
        if len(matches) != 1:
            raise ValueError(f"Cannot identify exact managed version fields: {name}")
        start, end = matches[0].span(1)
        return text[:start] + "<managed-version>" + text[end:]
    else:
        patterns = [
            r"(?:filevers|prodvers)\s*=\s*\([0-9]+, [0-9]+, [0-9]+, 0\)",
            r"StringStruct\('(?:FileVersion|ProductVersion)', '[0-9]+\.[0-9]+\.[0-9]+\.0'\)",
        ]
    for pattern in patterns:
        text, count = re.subn(pattern, "<managed-version>", text)
        expected = 2 if name == "version_info.txt" else 1
        if count != expected:
            raise ValueError(f"Cannot identify exact managed version fields: {name}")
    return text


def is_release_note(name: str) -> bool:
    return bool(re.fullmatch(r"docs/release-[0-9]+\.[0-9]+\.[0-9]+-notes\.md", name))


def verify_qa_hashes(root: Path, qa_commit: str, hashes: dict) -> None:
    for name, expected in hashes.items():
        if sha256(root / name) != expected:
            raise ValueError(f"QA helper hash mismatch: {name}")
        blob = subprocess.run(
            ["git", "show", f"{qa_commit}:{name}"], cwd=root, capture_output=True, check=True
        ).stdout
        if hashlib.sha256(blob).hexdigest() != expected:
            raise ValueError(f"QA checkout differs from committed Git bytes: {name}")


def verify_inputs(root: Path, policy: dict, qa_commit: str) -> dict:
    candidate = policy["candidate_commit"]
    if not re.fullmatch(r"[a-f0-9]{40}", candidate) or not re.fullmatch(r"[a-f0-9]{40}", qa_commit):
        raise ValueError("Candidate and QA commits must be full SHA values")
    if git(root, "rev-parse", "HEAD").strip() != qa_commit:
        raise ValueError("Checkout is not the requested QA commit")
    if git(root, "status", "--porcelain", "--untracked-files=all").strip():
        raise ValueError("Candidate verification requires a clean QA checkout")
    git(root, "merge-base", "--is-ancestor", candidate, qa_commit)
    changed = git(root, "diff", "--name-only", candidate, qa_commit).splitlines()
    explained = {}
    for name in changed:
        if name in QA_FILES:
            explained[name] = "explicit QA-only file"
        elif name in VERSION_FILES:
            old = git(root, "show", f"{candidate}:{name}")
            new = git(root, "show", f"{qa_commit}:{name}")
            if version_normalized(name, old) != version_normalized(name, new):
                raise ValueError(f"Non-version application or packaging change: {name}")
            explained[name] = (
                "managed development version fields only; payload remains candidate version"
            )
        elif name in HISTORY_FILES or is_release_note(name):
            explained[name] = "version history or release documentation"
        else:
            raise ValueError(f"Candidate build input changed outside QA allowlist: {name}")
    if "version-history.json" in changed:
        old = json.loads(git(root, "show", f"{candidate}:version-history.json"))
        new = json.loads(git(root, "show", f"{qa_commit}:version-history.json"))
        if new["events"][: len(old["events"])] != old["events"]:
            raise ValueError("Existing version events were rewritten")
        for event in new["events"][len(old["events"]) :]:
            if any(
                name not in QA_FILES
                and name not in VERSION_FILES
                and name not in HISTORY_FILES
                and not is_release_note(name)
                for name in event["files"]
            ):
                raise ValueError("Version event includes a non-QA product change")
    verify_qa_hashes(root, qa_commit, policy["qa_sha256"])
    return {
        "candidate_commit": candidate,
        "qa_commit": qa_commit,
        "explained_changes": explained,
        "unexplained_input_changes": [],
        "qa_sha256": policy["qa_sha256"],
        "product_dependency_packaging_inputs_unchanged": True,
    }


def validate_artifact(metadata: dict, expected: dict, policy: dict) -> dict:
    run = metadata.get("workflow_run", {})
    checks = (
        metadata.get("id") == expected["id"],
        metadata.get("name") == expected["name"],
        metadata.get("digest") == "sha256:" + expected["sha256"],
        metadata.get("expired") is False,
        run.get("id") == policy["candidate_run_id"],
        run.get("head_sha") == policy["candidate_commit"],
        run.get("repository_id") == policy["repository_id"],
        run.get("head_repository_id") == policy["repository_id"],
    )
    if not all(checks):
        raise ValueError(f"Pinned artifact provenance mismatch: {expected['name']}")
    return {
        "id": expected["id"],
        "name": expected["name"],
        "sha256": expected["sha256"],
        "run_id": run["id"],
        "head_sha": run["head_sha"],
    }


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https":
            raise ValueError("Artifact download redirected outside HTTPS")
        redirected = super().redirect_request(request, response, code, message, headers, url)
        if parsed.hostname != "api.github.com":
            redirected.remove_header("Authorization")
        return redirected


def api_request(policy: dict, suffix: str):
    repository = policy["repository"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid repository name")
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("Read-only Actions token is required")
    return urllib.request.Request(
        f"https://api.github.com/repos/{repository}/actions/artifacts/{suffix}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )


def extract_payload(archive: Path, destination: Path) -> dict:
    if destination.exists():
        raise ValueError("Payload destination must be new")
    with zipfile.ZipFile(archive) as package:
        names = set()
        for member in package.infolist():
            path = PurePosixPath(member.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts or ":" in str(path):
                raise ValueError("Unsafe payload ZIP path")
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError("Payload ZIP cannot contain symlinks")
            normalized = str(path).casefold().rstrip("/")
            if normalized in names:
                raise ValueError("Duplicate payload ZIP path")
            names.add(normalized)
        if "darkcalendar.exe" not in names:
            raise ValueError("Pinned archive has no root DarkCalendar.exe")
        destination.mkdir(parents=True)
        package.extractall(destination)
    return {
        str(path.relative_to(destination)).replace("\\", "/"): sha256(path)
        for path in sorted(destination.rglob("*"))
        if path.is_file()
    }


def verify_and_download(
    root: Path, policy: dict, qa_commit: str, evidence: Path, payload: Path
) -> dict:
    result = verify_inputs(root, policy, qa_commit)
    opener = urllib.request.build_opener(SafeRedirect())
    artifacts = {}
    for role, expected in policy["artifacts"].items():
        with opener.open(api_request(policy, str(expected["id"])), timeout=60) as response:
            metadata = json.loads(response.read().decode("utf-8", errors="replace"))
        artifacts[role] = validate_artifact(metadata, expected, policy)
    expected = policy["artifacts"]["payload"]
    archive = evidence / "candidate-payload.zip"
    with (
        opener.open(api_request(policy, f"{expected['id']}/zip"), timeout=60) as response,
        archive.open("xb") as output,
    ):
        while block := response.read(1024 * 1024):
            output.write(block)
    if sha256(archive) != expected["sha256"]:
        raise ValueError("Raw candidate artifact SHA256 mismatch; payload was not extracted")
    manifest = extract_payload(archive, payload)
    result.update(
        passed=True,
        candidate_version=policy["candidate_version"],
        candidate_run_id=policy["candidate_run_id"],
        artifacts=artifacts,
        raw_payload_sha256=sha256(archive),
        payload_manifest=manifest,
        payload_file_count=len(manifest),
        payload_rebuilt=False,
        release_assets_downloaded=False,
        auto_publication=False,
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--policy-sha256", required=True)
    parser.add_argument("--qa-commit", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--payload", type=Path, required=True)
    args = parser.parse_args(argv)
    required = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_OS": "Windows",
    }
    if any(os.environ.get(key) != value for key, value in required.items()):
        raise RuntimeError("Candidate verification runs only in a disposable hosted Windows job")
    temporary = Path(os.environ["RUNNER_TEMP"]).resolve()
    for path in (args.evidence, args.payload):
        if path.resolve() == temporary or not path.resolve().is_relative_to(temporary):
            raise ValueError("Candidate outputs must stay in child directories of RUNNER_TEMP")
    args.evidence.mkdir(parents=True, exist_ok=True)
    result = {"passed": False, "candidate_commit": None, "qa_commit": args.qa_commit}
    try:
        if sha256(args.policy) != args.policy_sha256:
            raise ValueError("Pinned candidate policy SHA256 mismatch")
        policy = json.loads(args.policy.read_text(encoding="utf-8", errors="strict"))
        if not policy["qa_sha256"].keys() >= REQUIRED_QA_HASHES:
            raise ValueError(
                "Candidate policy must pin every executable QA helper and SQLite policy"
            )
        result = verify_and_download(
            args.root.resolve(), policy, args.qa_commit, args.evidence, args.payload
        )
        result["policy_sha256"] = args.policy_sha256
    except Exception as error:
        # Never serialize tokens, request headers, redirects or signed download URLs.
        result["error_type"] = type(error).__name__
        if isinstance(error, ValueError):
            result["error"] = str(error)
        raise
    finally:
        (args.evidence / "candidate-reuse-provenance.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8", errors="strict"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
