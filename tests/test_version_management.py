# -*- coding: utf-8 -*-
"""Release-unit numbering preserves history, detects drift and survives retries."""

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from scripts import manage_version as versions

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def project(tmp_path):
    for name in versions.CORE:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    (tmp_path / "calendar_app/feature.py").write_bytes(b"VALUE = 1\n")
    version = versions.current_version(tmp_path)
    ledger = {
        "schema_version": 1,
        "baseline_version": version,
        "current_version": version,
        "events": [],
        "observed_inputs": versions.input_hashes(tmp_path),
    }
    (tmp_path / versions.HISTORY).write_bytes(versions.json_bytes(ledger))
    versions.migrate(tmp_path)
    return tmp_path


def ledger(root):
    return json.loads(versions.text(root / versions.HISTORY))


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def edit(root, name="calendar_app/feature.py"):
    path = root / name
    path.write_bytes(path.read_bytes() + b"VALUE = 2\n")


def record(root, kind="change", key="fix-1", files=("calendar_app/feature.py",)):
    return versions.record(root, kind, key, "Logical work", files)


def prepare(root, key="release-1", **kwargs):
    return versions.prepare(root, key, "Release scope", **(kwargs or {"bump": "patch"}))


def cli(root, *arguments):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/manage_version.py"), *arguments, "--root", str(root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=15,
    )


@pytest.mark.parametrize(
    ("current", "kind", "expected"),
    [
        ("4.6.9", "patch", "4.6.10"),
        ("4.9.12", "minor", "4.10.0"),
        ("4.6.10", "major", "5.0.0"),
        ("9.9.9", "patch", "9.9.10"),
    ],
)
def test_explicit_release_increment_has_no_decimal_carry(current, kind, expected):
    assert versions.next_version(current, kind) == expected


@pytest.mark.parametrize(
    "version",
    [
        "0.1.0",
        "04.6.1",
        "4.06.1",
        "4.6",
        "4.6.1.0",
        "4.6.-1",
        "65536.1.0",
        "4.65536.1",
        "4.6.65536",
    ],
)
def test_invalid_msix_versions(version):
    with pytest.raises(ValueError):
        versions.version_number(version)


def test_numeric_version_comparison_and_boundary():
    assert versions.version_number("4.6.10") > versions.version_number("4.6.9")
    assert versions.version_number("65535.65535.65535") == (65535, 65535, 65535)
    with pytest.raises(ValueError):
        versions.next_version("4.6.65535", "patch")
    with pytest.raises(ValueError):
        versions.next_version("4.6.9", "store")


@pytest.mark.parametrize("kind", ["change", "module", "store"])
def test_change_registration_never_changes_product_or_public_metadata(project, kind):
    before = {name: (project / name).read_bytes() for name in versions.CORE}
    initial = versions.current_version(project)
    edit(project)
    assert record(project, kind)["version"] == initial
    assert versions.verify(project, ledger(project)) == initial
    assert {name: (project / name).read_bytes() for name in versions.CORE} == before
    assert not versions.scan(project)["unrecorded_files"]


def test_event_retry_and_same_input_duplicate_are_idempotent(project):
    edit(project)
    assert record(project)["changed"]
    before = snapshot(project)
    assert not record(project)["changed"]
    assert not record(project, key="another-id")["changed"]
    assert snapshot(project) == before
    edit(project)
    with pytest.raises(ValueError, match="different inputs"):
        record(project)


def test_readonly_scan_detects_addition_edit_deletion_without_any_writes(project):
    edit(project)
    new = project / "calendar_app/new.py"
    new.write_bytes(b"VALUE = 1\n")
    before = snapshot(project)
    scan = versions.scan(project)
    assert scan["changed"] is False
    assert scan["unrecorded_files"] == ["calendar_app/feature.py", "calendar_app/new.py"]
    result = cli(project, "scan", "--strict")
    assert result.returncode == 2
    assert snapshot(project) == before
    record(project, key="all", files=())
    new.unlink()
    assert versions.scan(project)["unrecorded_files"] == ["calendar_app/new.py"]


def test_scoped_record_does_not_acknowledge_unrelated_edits(project):
    other = project / "calendar_app/other.py"
    other.write_bytes(b"VALUE = 3\n")
    edit(project)
    record(project)
    assert versions.scan(project)["unrecorded_files"] == ["calendar_app/other.py"]
    with pytest.raises(ValueError, match="Unrecorded"):
        prepare(project)


def test_database_tokens_caches_and_test_only_changes_are_not_runtime_drift(project):
    for name in (
        "personal.db",
        "personal.db-wal",
        "personal.db-shm",
        "token.json",
        "credentials.json",
        "client_secret_example.json",
    ):
        (project / "calendar_app" / name).write_bytes(b"private")
    tests = project / "tests"
    tests.mkdir()
    (tests / "test_example.py").write_bytes(b"assert True\n")
    assert not versions.scan(project)["unrecorded_files"]


def test_eol_and_managed_fields_do_not_create_false_input_drift(project):
    path = project / "calendar_app/feature.py"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    versions.sync(project, channel="Beta", date="2026-10-21")
    assert not versions.scan(project)["unrecorded_files"]


def test_release_bundles_several_changes_and_bumps_only_once(project):
    initial = versions.current_version(project)
    for index in range(3):
        edit(project)
        record(project, key=f"fix-{index}")
    result = prepare(project)
    assert result["version"] == versions.next_version(initial, "patch")
    assert versions.verify(project, ledger(project)) == result["version"]
    assert not prepare(project)["changed"]
    assert (
        cli(project, "check", "--strict", "--for-build", "--expected", result["version"]).returncode
        == 0
    )


def test_changed_candidate_cannot_be_rebuilt_or_overwrite_release_id(project):
    first = prepare(project)
    edit(project)
    record(project, key="candidate-fix")
    with pytest.raises(ValueError, match="different parameters or inputs"):
        prepare(project)
    with pytest.raises(ValueError, match="Reserved version"):
        prepare(project, key="same-version-new-id", version=first["version"])
    with pytest.raises(ValueError, match="inputs changed"):
        versions.sync(project, for_build=True)
    assert prepare(project, key="new-release")["version"] == versions.next_version(
        first["version"], "patch"
    )


def test_prepare_rejects_nonincreasing_or_published_target_without_writes(project):
    before = snapshot(project)
    for version in ("1.0.0", "4.6.4"):
        with pytest.raises(ValueError):
            prepare(project, version=version)
        assert snapshot(project) == before


def test_build_requires_explicit_preparation_and_exact_version(project):
    with pytest.raises(ValueError, match="Prepare the release explicitly"):
        versions.sync(project, for_build=True)
    first = prepare(project)
    with pytest.raises(ValueError, match="differs"):
        versions.sync(project, expected="1.0.0", for_build=True)
    versions.sync(
        project, expected=first["version"], for_build=True, date="2026-10-21", channel="Stable"
    )
    assert versions.verify(project, ledger(project)) == first["version"]
    assert f'APP_PUBLISHED_VERSION = "{first["version"]}"' in versions.text(
        project / versions.CORE[0]
    )


def test_sync_repairs_generated_surface_from_ledger_without_a_new_version(project):
    initial = versions.current_version(project)
    path = project / "pyproject.toml"
    path.write_text(
        versions.replace_one(r'^version = "[^"]+"$', 'version = "0.0.0"', versions.text(path)),
        encoding="utf-8",
        errors="strict",
    )
    with pytest.raises(ValueError, match="mismatch"):
        versions.verify(project, ledger(project))
    versions.sync(project)
    assert versions.verify(project, ledger(project)) == initial


def test_migration_preserves_legacy_events_and_product_version(project):
    for name, content in versions.core_updates(project, "4.3.3", "2026-10-19").items():
        (project / name).write_bytes(content)
    events = []
    previous = "4.3.0"
    for index, (kind, version) in enumerate(
        (("module", "4.4.0"), ("store", "4.5.0"), ("override", "4.3.3"))
    ):
        events.append(
            {
                "id": f"legacy-{index}",
                "kind": kind,
                "created_at": "2026-10-19",
                "previous_version": previous,
                "version": version,
                "summary": "Legacy",
                "published_version": "4.3.0",
                "files": [],
                "scoped_hashes": {},
                "inputs": {},
            }
        )
        previous = version
    old = {
        "schema_version": 1,
        "baseline_version": "4.3.0",
        "current_version": "4.3.3",
        "events": copy.deepcopy(events),
        "observed_inputs": versions.input_hashes(project),
    }
    (project / versions.HISTORY).write_bytes(versions.json_bytes(old))
    core_before = {name: (project / name).read_bytes() for name in versions.CORE}
    assert versions.migrate(project)["changed"]
    updated = ledger(project)
    assert updated["events"][:3] == events
    assert updated["legacy_event_count"] == 3
    assert versions.verify(project, updated) == "4.3.3"
    assert {name: (project / name).read_bytes() for name in versions.CORE} == core_before
    assert not versions.migrate(project)["changed"]
    updated["events"][0]["version"] = "4.4.1"
    with pytest.raises(ValueError, match="chain"):
        versions.verify(project, updated)


def test_transaction_retry_does_not_bump_twice_or_overwrite_user_edit(project, monkeypatch):
    writer = versions.atomic_write

    def interrupt(path, data):
        if path == project / "pyproject.toml":
            raise OSError("simulated interruption")
        writer(path, data)

    with monkeypatch.context() as local:
        local.setattr(versions, "atomic_write", interrupt)
        with pytest.raises(OSError):
            prepare(project)
    assert cli(project, "scan").returncode == 1
    with versions.locked(project):
        assert not prepare(project)["changed"]
    assert len([event for event in ledger(project)["events"] if event["kind"] == "release"]) == 1
    edit(project)
    record(project, key="next-fix")
    with monkeypatch.context() as local:
        local.setattr(versions, "atomic_write", interrupt)
        with pytest.raises(OSError):
            prepare(project, key="release-2")
    target = project / "pyproject.toml"
    target.write_bytes(target.read_bytes() + b"\n# new user edit\n")
    before = target.read_bytes()
    with pytest.raises(ValueError, match="newer user changes"):
        versions.recover(project)
    assert target.read_bytes() == before


def test_writer_lock_blocks_other_writer_but_readonly_check_does_not_write(project):
    before = snapshot(project)
    with versions.locked(project):
        result = cli(project, "record", "--event-id", "second", "--summary", "Second writer")
        assert result.returncode != 0
        assert cli(project, "check").returncode == 0
    # The lock file may be created; no product/history file changes.
    assert {name: snapshot(project)[name] for name in before} == before
