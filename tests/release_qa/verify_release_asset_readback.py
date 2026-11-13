# -*- coding: utf-8 -*-
"""GET-only actual draft/public release byte readback on a fresh hosted runner."""

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "Namer-kimhyojin/DARK-CALENDAR"
REPOSITORY_ID = 1195286732
RELEASE_ID = 441140736
TAG = "v5.2.0"
SOURCE_COMMIT = "731bca88a82bec5e200d315dec73321730ad0d96"
NATIVE_RUN_ID = 42940491243
EXPECTED_ASSETS = [
    {
        "id": 733702128,
        "name": "DarkCalendar-5.2.0-corresponding-source.zip",
        "size": 188835900,
        "sha256": "a62893df79bc2fdc225dafb443cf123813c75bd257ef9f263b4266cbd4e08463",
    },
    {
        "id": 733702127,
        "name": "DarkCalendar-5.2.0-corresponding-source.zip.sha256",
        "size": 109,
        "sha256": "03e223af4c417014cf818179bfe35d67bb43bdfed7d962702514d279027676e1",
    },
    {
        "id": 733702130,
        "name": "DarkCalendar-5.2.0-x64.msix",
        "size": 97257193,
        "sha256": "7bcfe89cb3d7bec5cd63ee7a93af8f692f87b170a3f13291bf531069a0e036a8",
    },
    {
        "id": 733702133,
        "name": "DarkCalendar-5.2.0-x64.msix.sha256",
        "size": 93,
        "sha256": "b649f3ffd64ab7929a6a71deda139e7603a465d6a2b5610e5dd70f951fbc7350",
    },
    {
        "id": 733702129,
        "name": "DarkCalendar-5.2.0.0-x64.msixupload",
        "size": 95293554,
        "sha256": "54b3888f4b5e69f9d826ca53c115f4afc36e2399bfda5a00c2586291854d9c5b",
    },
    {
        "id": 733702147,
        "name": "DarkCalendar-5.2.0.0-x64.msixupload.sha256",
        "size": 101,
        "sha256": "4cb634b49279c720e99692034c98cde48b3e43e25caece8db15517a59d68c4a6",
    },
]
EXPECTED_CI_ARTIFACTS = [
    {
        "id": 13820288007,
        "name": "darkcalendar-github-release-x64",
        "size": 378420923,
        "sha256": "eea2b36601f9770aaa3caefedd6888f37cc2fee46dda52f1ee769ffad3399000",
    },
    {
        "id": 13820148301,
        "name": "darkcalendar-dist-x64",
        "size": 94181542,
        "sha256": "76c3543f47e0e884ce1e16d82f006586fa14d8fc99843cbf90d698661a5398b7",
    },
    {
        "id": 13819534476,
        "name": "darkcalendar-msix-x64",
        "size": 95285078,
        "sha256": "69fdcc76cd4d3136c3a8f4dfe8e78b36d30934a2a9f441be224eec0c99557e73",
    },
]
EXPECTED_PRODUCT_DIGEST = "782db7b80e85affaf0810a6cb4aa81bc5412ec2a85bae4ff26763ab1970e10c6"
EXPECTED_CANONICALIZER_SHA256 = "38925dedfb1a81bb309e66d0a3ebb7637a09545c28214a47b58714d0d2ee9e39"
OFFICIAL_HOSTS = frozenset({"api.github.com", "github.com", "release-assets.githubusercontent.com"})


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def require_hosted_temp(output):
    required = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_OS": "Linux",
    }
    if sys.platform != "linux" or any(
        os.environ.get(key) != value for key, value in required.items()
    ):
        raise RuntimeError("Release byte readback requires a fresh hosted Linux runner")
    temporary = Path(os.environ["RUNNER_TEMP"]).resolve()
    if output.resolve() == temporary or not output.resolve().is_relative_to(temporary):
        raise ValueError("Readback output must be a child of RUNNER_TEMP")


def check_https(url):
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in OFFICIAL_HOSTS
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("Download target is not an approved official HTTPS host")
    return parsed.hostname


class GetOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, events):
        super().__init__()
        self.events = events

    def redirect_request(self, request, response, code, message, headers, url):
        if request.get_method() != "GET":
            raise ValueError("Only GET is allowed")
        host = check_https(url)
        redirected = super().redirect_request(request, response, code, message, headers, url)
        if redirected is None:
            raise ValueError("Unsupported download redirect")
        if host != "api.github.com":
            for container in (redirected.headers, redirected.unredirected_hdrs):
                for key in list(container):
                    if key.casefold() == "authorization":
                        del container[key]
        bearer_forwarded = any(
            key.casefold() == "authorization"
            for container in (redirected.headers, redirected.unredirected_hdrs)
            for key in container
        )
        self.events.append({"status": code, "host": host, "bearer_forwarded": bearer_forwarded})
        return redirected


class Reader:
    def __init__(self, output):
        require_hosted_temp(output)
        self.token = os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise RuntimeError("An existing repository Actions token is required")
        self.redirects = []
        self.opener = urllib.request.build_opener(GetOnlyRedirect(self.redirects))

    def request(self, url, *, authenticated, binary):
        check_https(url)
        headers = {
            "Accept": "application/octet-stream" if binary else "application/vnd.github+json",
            "User-Agent": "AirCalendar-release-readback",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if authenticated:
            if urllib.parse.urlsplit(url).hostname != "api.github.com":
                raise ValueError("Bearer authentication is restricted to api.github.com")
            headers["Authorization"] = "Bearer " + self.token
        request = urllib.request.Request(url, headers=headers, method="GET")
        return self.opener.open(request, timeout=90)

    def api(self, suffix):
        with self.request(
            f"https://api.github.com/repos/{REPOSITORY}/{suffix}", authenticated=True, binary=False
        ) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))

    def body(self, asset, phase):
        if phase == "draft":
            url = f"https://api.github.com/repos/{REPOSITORY}/releases/assets/{asset['id']}"
            return self.request(url, authenticated=True, binary=True)
        expected = f"https://github.com/{REPOSITORY}/releases/download/{TAG}/{asset['name']}"
        if asset.get("browser_download_url") != expected:
            raise ValueError("Unexpected public browser download URL")
        return self.request(expected, authenticated=False, binary=True)


def verify_release(value, phase):
    if (
        phase not in {"draft", "public"}
        or value.get("id") != RELEASE_ID
        or value.get("tag_name") != TAG
        or value.get("draft") is not (phase == "draft")
        or value.get("prerelease") is not False
    ):
        raise ValueError("Release ID, phase or tag differs from the fixed reviewed candidate")
    return {
        key: value.get(key)
        for key in ("id", "tag_name", "draft", "prerelease", "target_commitish", "published_at")
    }


def verify_assets(values):
    if len(values) != 6 or len({item.get("id") for item in values}) != 6:
        raise ValueError("Exactly six distinct reviewed assets are required")
    expected = {item["id"]: item for item in EXPECTED_ASSETS}
    if set(expected) != {item.get("id") for item in values}:
        raise ValueError("Release asset IDs differ from the reviewed six")
    for item in values:
        pin = expected[item["id"]]
        if (
            item.get("name") != pin["name"]
            or item.get("state") != "uploaded"
            or item.get("size") != pin["size"]
            or item.get("digest") != "sha256:" + pin["sha256"]
        ):
            raise ValueError("Release asset name, state, size or digest mismatch")
    return sorted(values, key=lambda item: item["name"])


def verify_native_lineage(reader):
    run = reader.api(f"actions/runs/{NATIVE_RUN_ID}")
    if (
        run.get("id") != NATIVE_RUN_ID
        or run.get("head_sha") != SOURCE_COMMIT
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("repository", {}).get("id") != REPOSITORY_ID
    ):
        raise ValueError("Original successful native build run does not match")
    jobs = reader.api(f"actions/runs/{NATIVE_RUN_ID}/jobs?per_page=100")["jobs"]
    native = [job for job in jobs if job.get("name") == "verify-native-x64"]
    if (
        len(native) != 1
        or native[0].get("conclusion") != "success"
        or native[0].get("status") != "completed"
        or native[0].get("run_id") != NATIVE_RUN_ID
    ):
        raise ValueError("Original native six-cycle job did not succeed")
    verified = []
    for pin in EXPECTED_CI_ARTIFACTS:
        value = reader.api(f"actions/artifacts/{pin['id']}")
        workflow = value.get("workflow_run", {})
        if (
            value.get("id") != pin["id"]
            or value.get("name") != pin["name"]
            or value.get("size_in_bytes") != pin["size"]
            or value.get("digest") != "sha256:" + pin["sha256"]
            or value.get("expired") is not False
            or workflow.get("id") != NATIVE_RUN_ID
            or workflow.get("head_sha") != SOURCE_COMMIT
            or workflow.get("repository_id") != REPOSITORY_ID
            or workflow.get("head_repository_id") != REPOSITORY_ID
        ):
            raise ValueError("Original CI artifact provenance mismatch")
        verified.append(pin)
    ref = reader.api(f"git/ref/tags/{TAG}")["object"]
    for _ in range(5):
        if ref["type"] == "commit":
            break
        if ref["type"] != "tag":
            raise ValueError("Unexpected release tag object type")
        ref = reader.api("git/tags/" + ref["sha"])["object"]
    if ref.get("type") != "commit" or ref.get("sha") != SOURCE_COMMIT:
        raise ValueError("Release tag no longer points to the reviewed source commit")
    return {
        "run_id": NATIVE_RUN_ID,
        "source_commit": SOURCE_COMMIT,
        "native_job_id": native[0]["id"],
        "native_job_conclusion": "success",
        "artifacts": verified,
        "tag_commit": ref["sha"],
    }


def verify_product_inputs():
    if sha(ROOT / "scripts/manage_version.py") != EXPECTED_CANONICALIZER_SHA256:
        raise ValueError("Product canonicalizer differs from the reviewed CI source")
    sys.path.insert(0, str(ROOT))
    from scripts.manage_version import input_hashes

    inputs = input_hashes(ROOT)
    digest = hashlib.sha256(
        json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode("utf-8", errors="strict")
    ).hexdigest()
    if len(inputs) != 726 or digest != EXPECTED_PRODUCT_DIGEST:
        raise ValueError("The reviewed 726 product inputs changed")
    return {"count": len(inputs), "sha256": digest}


def download_asset(reader, asset, phase, output):
    name = asset["name"]
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,180}", name) is None:
        raise ValueError("Unsafe release asset filename")
    target = output / name
    partial = output / (name + ".download")
    if target.exists() or partial.exists() or not target.resolve().is_relative_to(output.resolve()):
        raise ValueError("Readback never replaces an existing file")
    digest, count = hashlib.sha256(), 0
    with reader.body(asset, phase) as response, partial.open("xb") as destination:
        if response.status != 200:
            raise ValueError("Release binary download did not return 200")
        final_host = check_https(response.geturl())
        while block := response.read(1024 * 1024):
            destination.write(block)
            digest.update(block)
            count += len(block)
            if count > asset["size"]:
                raise ValueError("Release binary exceeds reviewed byte length")
    actual = digest.hexdigest()
    if count != asset["size"] or asset["digest"] != "sha256:" + actual:
        raise ValueError("Actual downloaded bytes differ from reviewed size or SHA256")
    partial.rename(target)
    return {
        "id": asset["id"],
        "name": name,
        "downloaded_bytes": count,
        "downloaded_sha256": actual,
        "expected_api_digest": asset["digest"],
        "matches": True,
        "download_route": "authenticated asset API"
        if phase == "draft"
        else "unauthenticated browser_download_url",
        "initial_bearer_used": phase == "draft",
        "final_host": final_host,
    }


def verify_sidecars(output, downloaded):
    actual = {item["name"]: item for item in downloaded}
    sidecars = []
    for name in sorted(actual):
        if not name.endswith(".sha256"):
            continue
        raw = (output / name).read_bytes()
        match = re.fullmatch(
            r"([a-fA-F0-9]{64})\s+\*?([^\r\n]+)", raw.decode("utf-8", errors="strict").strip()
        )
        target = name.removesuffix(".sha256")
        if (
            not match
            or match[2] != target
            or target not in actual
            or match[1].lower() != actual[target]["downloaded_sha256"]
        ):
            raise ValueError("Downloaded raw sidecar does not describe the downloaded binary")
        sidecars.append(
            {
                "name": name,
                "retained_raw_bytes": len(raw),
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
                "target": target,
                "target_sha256": match[1].lower(),
            }
        )
    if len(sidecars) != 3:
        raise ValueError("Exactly three raw sidecars must be retained")
    return sidecars


def readback(reader, phase, output):
    lineage = verify_native_lineage(reader)
    before = verify_release(reader.api(f"releases/{RELEASE_ID}"), phase)
    assets = verify_assets(reader.api(f"releases/{RELEASE_ID}/assets?per_page=100"))
    downloaded = [download_asset(reader, item, phase, output) for item in assets]
    sidecars = verify_sidecars(output, downloaded)
    after = verify_release(reader.api(f"releases/{RELEASE_ID}"), phase)
    verify_assets(reader.api(f"releases/{RELEASE_ID}/assets?per_page=100"))
    return {
        "passed": True,
        "phase": phase,
        "release_id": RELEASE_ID,
        "tag": TAG,
        "native_lineage": lineage,
        "release_before": before,
        "release_after": after,
        "assets": downloaded,
        "retained_sidecars": sidecars,
        "redirects": reader.redirects,
        "release_mutated": False,
        "publication_performed": False,
        "application_or_audio_executed": False,
        "summary_ko": "고정된 여섯 릴리스 자산의 실제 다운로드 바이트와 원시 sidecar를 확인했습니다. 릴리스 상태는 변경하지 않았습니다.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("draft", "public"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.out.resolve()
    require_hosted_temp(output)
    if output.exists():
        raise ValueError("Readback output must be new")
    output.mkdir(parents=True)
    result = {
        "passed": False,
        "phase": args.phase,
        "release_id": RELEASE_ID,
        "tag": TAG,
        "source_commit": SOURCE_COMMIT,
        "native_run_id": NATIVE_RUN_ID,
        "release_mutated": False,
        "summary_ko": "릴리스 실제 바이트 재다운로드 검증을 완료하지 못했습니다.",
    }
    try:
        product = verify_product_inputs()
        result = readback(Reader(output), args.phase, output)
        result["product_inputs"] = product
        result["qa_commit"] = os.environ.get("GITHUB_SHA")
        result["runner_os"] = os.environ.get("RUNNER_OS")
    except Exception as error:
        result["error_type"] = type(error).__name__
        if isinstance(error, ValueError):
            result["error"] = str(error)
        if isinstance(error, urllib.error.HTTPError):
            result["http_status"] = error.code
    result["finished_utc"] = datetime.now(UTC).isoformat()
    (output / "readback.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="strict"
    )
    print(
        json.dumps(
            {
                "passed": result["passed"],
                "phase": args.phase,
                "release_id": RELEASE_ID,
                "assets_verified": len(result.get("assets", [])),
            }
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
