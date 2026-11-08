# -*- coding: utf-8 -*-
"""GET readback negative contracts only; no network, application or real token."""

import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import urllib.error
import urllib.request

import pytest
import yaml

PATH = Path(__file__).with_name("verify_release_asset_readback.py")
SPEC = importlib.util.spec_from_file_location("asset_readback_qa", PATH)
readback = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(readback)


@pytest.fixture
def sample(monkeypatch):
    bodies = {"example.zip": b"source", "example.msix": b"package", "example.msixupload": b"upload"}
    for name, raw in list(bodies.items()):
        bodies[name + ".sha256"] = (hashlib.sha256(raw).hexdigest().upper() + "  " + name).encode(
            "utf-8", errors="strict"
        )
    pins = [
        {
            "id": 100 + index,
            "name": name,
            "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        for index, (name, raw) in enumerate(sorted(bodies.items()))
    ]
    monkeypatch.setattr(readback, "EXPECTED_ASSETS", pins)
    assets = [
        {
            "id": item["id"],
            "name": item["name"],
            "size": item["size"],
            "digest": "sha256:" + item["sha256"],
            "state": "uploaded",
            "browser_download_url": f"https://github.com/{readback.REPOSITORY}/releases/download/{readback.TAG}/{item['name']}",
        }
        for item in pins
    ]
    return bodies, assets


class Response(io.BytesIO):
    status = 200

    def geturl(self):
        return "https://release-assets.githubusercontent.com/example"


class FakeReader:
    def __init__(self, bodies, assets, phase):
        self.bodies, self.assets, self.phase = bodies, assets, phase
        self.redirects = []
        self.downloads = []
        self.problem = None

    def api(self, suffix):
        if suffix == f"actions/runs/{readback.NATIVE_RUN_ID}":
            return {
                "id": readback.NATIVE_RUN_ID,
                "head_sha": "wrong" if self.problem == "head" else readback.SOURCE_COMMIT,
                "status": "completed",
                "conclusion": "success",
                "repository": {"id": readback.REPOSITORY_ID},
            }
        if suffix.endswith("/jobs?per_page=100"):
            return {
                "jobs": [
                    {
                        "id": 99,
                        "name": "verify-native-x64",
                        "status": "completed",
                        "conclusion": "failure" if self.problem == "native" else "success",
                        "run_id": readback.NATIVE_RUN_ID,
                    }
                ]
            }
        if suffix.startswith("actions/artifacts/"):
            pin = next(
                item
                for item in readback.EXPECTED_CI_ARTIFACTS
                if str(item["id"]) == suffix.split("/")[-1]
            )
            return {
                "id": pin["id"],
                "name": pin["name"],
                "size_in_bytes": pin["size"],
                "digest": "wrong" if self.problem == "artifact" else "sha256:" + pin["sha256"],
                "expired": False,
                "workflow_run": {
                    "id": readback.NATIVE_RUN_ID,
                    "head_sha": readback.SOURCE_COMMIT,
                    "repository_id": readback.REPOSITORY_ID,
                    "head_repository_id": readback.REPOSITORY_ID,
                },
            }
        if suffix.startswith("git/ref/"):
            return {
                "object": {
                    "type": "commit",
                    "sha": "wrong" if self.problem == "tag" else readback.SOURCE_COMMIT,
                }
            }
        if suffix.endswith("/assets?per_page=100"):
            return copy.deepcopy(self.assets)
        if suffix == f"releases/{readback.RELEASE_ID}":
            return {
                "id": readback.RELEASE_ID,
                "tag_name": readback.TAG,
                "draft": self.phase == "draft",
                "prerelease": False,
            }
        raise AssertionError("Unexpected endpoint")

    def body(self, asset, phase):
        self.downloads.append((asset["id"], phase))
        return Response(self.bodies[asset["name"]])


@pytest.mark.parametrize("phase", ["draft", "public"])
def test_actual_six_bodies_and_three_raw_sidecars_are_verified(sample, tmp_path, phase):
    bodies, assets = sample
    client = FakeReader(bodies, assets, phase)
    result = readback.readback(client, phase, tmp_path)
    assert result["passed"] and len(client.downloads) == 6
    assert len(result["assets"]) == 6 and len(result["retained_sidecars"]) == 3
    assert all(
        (tmp_path / item["name"]).read_bytes() == bodies[item["name"]] for item in result["assets"]
    )
    assert not result["release_mutated"] and not result["publication_performed"]
    for sidecar in result["retained_sidecars"]:
        raw = (tmp_path / sidecar["name"]).read_bytes()
        assert raw == bodies[sidecar["name"]] and not raw.endswith(b"\n")
        assert raw[:64] == raw[:64].upper()


@pytest.mark.parametrize(
    "field,value",
    [("id", 1), ("name", "wrong"), ("state", "new"), ("size", 0), ("digest", "sha256:" + "0" * 64)],
)
def test_any_changed_asset_identity_state_size_or_digest_fails(sample, field, value):
    _, assets = sample
    assets[0][field] = value
    with pytest.raises(ValueError):
        readback.verify_assets(assets)


def test_extra_missing_duplicate_asset_is_never_accepted(sample):
    _, assets = sample
    for invalid in (assets[:-1], assets + [assets[0]], [assets[0]] * 6):
        with pytest.raises(ValueError):
            readback.verify_assets(invalid)


@pytest.mark.parametrize("problem", ["head", "native", "artifact", "tag"])
def test_native_source_job_artifact_and_tag_lineage_are_mandatory(sample, problem):
    bodies, assets = sample
    client = FakeReader(bodies, assets, "draft")
    client.problem = problem
    with pytest.raises(ValueError):
        readback.verify_native_lineage(client)


@pytest.mark.parametrize(
    "field,value", [("id", 1), ("tag_name", "v0.0.0"), ("draft", False), ("prerelease", True)]
)
def test_fixed_release_and_phase_cannot_be_changed(field, value):
    release = {
        "id": readback.RELEASE_ID,
        "tag_name": readback.TAG,
        "draft": True,
        "prerelease": False,
    }
    release[field] = value
    with pytest.raises(ValueError):
        readback.verify_release(release, "draft")


def test_actual_download_corruption_fails_even_when_metadata_matches(sample, tmp_path):
    bodies, assets = sample
    client = FakeReader({**bodies, assets[0]["name"]: b"corrupt"}, assets, "draft")
    with pytest.raises(ValueError):
        readback.download_asset(client, assets[0], "draft", tmp_path)
    assert not (tmp_path / assets[0]["name"]).exists()


def test_existing_file_is_never_replaced(sample, tmp_path):
    bodies, assets = sample
    path = tmp_path / assets[0]["name"]
    path.write_bytes(b"keep-existing")
    client = FakeReader(bodies, assets, "draft")
    with pytest.raises(ValueError, match="never replaces"):
        readback.download_asset(client, assets[0], "draft", tmp_path)
    assert path.read_bytes() == b"keep-existing" and not client.downloads


def test_three_actual_ci_uppercase_no_newline_sidecar_fixtures_are_preserved(tmp_path):
    pins = {item["name"]: item for item in readback.EXPECTED_ASSETS}
    downloaded = [
        {"name": item["name"], "downloaded_sha256": item["sha256"]} for item in pins.values()
    ]
    for name, pin in pins.items():
        if name.endswith(".sha256"):
            target = name.removesuffix(".sha256")
            raw = (pins[target]["sha256"].upper() + "  " + target).encode("utf-8", errors="strict")
            assert len(raw) == pin["size"] and hashlib.sha256(raw).hexdigest() == pin["sha256"]
            (tmp_path / name).write_bytes(raw)
    assert len(readback.verify_sidecars(tmp_path, downloaded)) == 3


@pytest.mark.parametrize("problem", ["filename", "target_hash"])
def test_sidecar_semantics_reject_wrong_filename_or_target_hash(sample, tmp_path, problem):
    bodies, assets = sample
    result = readback.readback(FakeReader(bodies, assets, "draft"), "draft", tmp_path)
    name = result["retained_sidecars"][0]["name"]
    raw = (tmp_path / name).read_bytes()
    (tmp_path / name).write_bytes(
        raw[:64] + b"  wrong-name" if problem == "filename" else b"0" * 64 + raw[64:]
    )
    with pytest.raises(ValueError):
        readback.verify_sidecars(tmp_path, result["assets"])


def test_public_route_uses_browser_url_without_bearer_and_draft_uses_api(sample):
    _, assets = sample
    client = readback.Reader.__new__(readback.Reader)
    client.request = Mock(return_value="response")
    assert client.body(assets[0], "public") == "response"
    client.request.assert_called_once_with(
        assets[0]["browser_download_url"], authenticated=False, binary=True
    )
    client.request.reset_mock()
    client.body(assets[0], "draft")
    assert client.request.call_args.kwargs["authenticated"] is True
    invalid = {**assets[0], "browser_download_url": "https://evil.example/asset"}
    with pytest.raises(ValueError):
        client.body(invalid, "public")


def test_public_request_contains_no_auth_header_and_token_never_goes_to_cdn():
    client = readback.Reader.__new__(readback.Reader)
    client.token = "synthetic-never-log"
    client.opener = SimpleNamespace(open=Mock(return_value=None))
    client.request("https://github.com/example", authenticated=False, binary=True)
    request = client.opener.open.call_args.args[0]
    assert request.get_method() == "GET"
    assert not any(key.casefold() == "authorization" for key in request.headers)
    with pytest.raises(ValueError):
        client.request(
            "https://release-assets.githubusercontent.com/example", authenticated=True, binary=True
        )


def test_redirect_strips_both_auth_header_stores_and_reports_observed_auth():
    events = []
    handler = readback.GetOnlyRedirect(events)
    request = urllib.request.Request(
        "https://api.github.com/example",
        headers={"Authorization": "Bearer synthetic"},
        method="GET",
    )
    request.add_unredirected_header("Authorization", "Bearer synthetic")
    target = handler.redirect_request(
        request, None, 302, "redirect", {}, "https://release-assets.githubusercontent.com/example"
    )
    assert not any(
        key.casefold() == "authorization"
        for store in (target.headers, target.unredirected_hdrs)
        for key in store
    )
    assert events[-1]["bearer_forwarded"] is False
    public = urllib.request.Request("https://github.com/example", method="GET")
    handler.redirect_request(public, None, 302, "redirect", {}, "https://api.github.com/example")
    assert events[-1]["bearer_forwarded"] is False


@pytest.mark.parametrize(
    "url",
    [
        "http://release-assets.githubusercontent.com/example",
        "https://evil.example/example",
        "https://user:password@github.com/example",
        "https://github.com:8443/example",
    ],
)
def test_nonofficial_or_insecure_redirect_is_rejected(url):
    request = urllib.request.Request("https://api.github.com/example", method="GET")
    with pytest.raises(ValueError):
        readback.GetOnlyRedirect([]).redirect_request(request, None, 302, "redirect", {}, url)


def test_non_get_redirect_is_rejected():
    request = urllib.request.Request("https://api.github.com/example", method="POST")
    with pytest.raises(ValueError, match="Only GET"):
        readback.GetOnlyRedirect([]).redirect_request(
            request, None, 302, "redirect", {}, "https://github.com/example"
        )


def test_local_execution_is_rejected_before_output_or_network(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    output = tmp_path / "must-not-exist"
    with pytest.raises(RuntimeError):
        readback.main(["--phase", "draft", "--out", str(output)])
    assert not output.exists()


def test_sanitized_failure_report_does_not_contain_token_or_signed_url(tmp_path, monkeypatch):
    monkeypatch.setattr(readback.sys, "platform", "linux")
    for key, value in {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_OS": "Linux",
        "RUNNER_TEMP": str(tmp_path),
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(readback, "verify_product_inputs", lambda: {"count": 722})
    monkeypatch.setattr(
        readback,
        "Reader",
        Mock(
            side_effect=urllib.error.HTTPError(
                "https://example.invalid/?secret-token", 403, "secret-token", {}, None
            )
        ),
    )
    output = tmp_path / "readback"
    assert readback.main(["--phase", "draft", "--out", str(output)]) == 1
    text = (output / "readback.json").read_text(encoding="utf-8", errors="strict")
    assert "secret-token" not in text
    assert json.loads(text)["http_status"] == 403


def test_fixed_pins_and_manual_workflow_never_build_publish_or_upload_large_files():
    assert readback.RELEASE_ID == 438437417 and readback.NATIVE_RUN_ID == 42509937063
    assert readback.SOURCE_COMMIT == "86b0ba9350ea24d8641d657b628d6d9177607860"
    assert {item["id"] for item in readback.EXPECTED_ASSETS} == {
        724824820,
        724824819,
        724824814,
        724824818,
        724824816,
        724824837,
    }
    assert len(readback.EXPECTED_CI_ARTIFACTS) == 3
    assert all(
        len(item["sha256"]) == 64
        for item in readback.EXPECTED_ASSETS + readback.EXPECTED_CI_ARTIFACTS
    )
    workflow = yaml.safe_load(
        (readback.ROOT / ".github/workflows/verify-release-assets-5.0.2.yml").read_text(
            encoding="utf-8", errors="strict"
        )
    )
    assert set(workflow.get("on", workflow.get(True))) == {"workflow_dispatch"}
    job = workflow["jobs"]["readback"]
    assert job["runs-on"] == "ubuntu-latest"
    assert job["permissions"] == {"contents": "write", "actions": "read"}
    checkout = next(
        step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@")
    )
    assert checkout["with"]["persist-credentials"] is False
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    for forbidden in ("build-release", "gh release", "--clobber", "pip install", "Stop-Process"):
        assert forbidden not in commands
    artifact = job["steps"][-1]
    assert artifact["if"] == "always()"
    assert "readback.json" in artifact["with"]["path"] and "*.sha256" in artifact["with"]["path"]
    assert "*.msix" not in artifact["with"]["path"] and "*.zip" not in artifact["with"]["path"]
