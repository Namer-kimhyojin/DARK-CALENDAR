# -*- coding: utf-8 -*-
"""Version increments must follow change semantics and survive retries/crashes."""

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
    (tmp_path / "calendar_app/feature.py").write_text(
        "# -*- coding: utf-8 -*-\nVALUE = 1\n", encoding="utf-8", errors="strict"
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/site-config.json").write_text(
        '{"appVersion":"3.8.1"}', encoding="utf-8", errors="strict"
    )
    return tmp_path


def register(root, kind="change", key="fix-1"):
    return versions.record(root, kind, key, "A logical change", ["calendar_app/feature.py"])


@pytest.mark.parametrize(
    ("current", "kind", "expected"),
    [
        ("3.8.1", "change", "3.8.2"),
        ("3.8.9", "change", "3.9.0"),
        ("3.9.9", "change", "4.0.0"),
        ("3.8.7", "module", "3.9.0"),
        ("3.9.1", "module", "4.0.0"),
        ("3.8.7", "store", "3.9.0"),
        ("3.9.0", "store", "4.0.0"),
        ("9.8.9", "change", "9.9.0"),
    ],
)
def test_increment_and_carry(current, kind, expected):
    assert versions.next_version(current, kind) == expected


@pytest.mark.parametrize("current", ["9.9.9", "3.8.10", "3.8", "3.8.1.0"])
def test_invalid_or_exhausted_versions_stop(current):
    with pytest.raises(ValueError):
        versions.next_version(current, "change")


def test_record_syncs_all_core_versions_without_advertising_a_public_release(project):
    initial = versions.current_version(project)
    public_before = (project / "docs/site-config.json").read_bytes()
    result = register(project)
    ledger = json.loads(versions.text(project / versions.HISTORY))
    assert result["version"] == versions.next_version(initial, "change")
    assert versions.verify(project, ledger) == result["version"]
    assert 'APP_RELEASE_CHANNEL = "Dev"' in versions.text(project / versions.CORE[0])
    assert (project / "docs/site-config.json").read_bytes() == public_before
    assert result["version"] in versions.text(project / versions.REPORT)
    assert not (project / ".versioning/transaction.json").exists()


def test_same_event_and_same_files_with_another_id_do_not_bump_twice(project):
    first = register(project)
    assert not register(project)["changed"]
    assert not register(project, key="same-fix-another-key")["changed"]
    assert versions.current_version(project) == first["version"]


def test_same_id_with_new_file_content_is_rejected(project):
    register(project)
    with (project / "calendar_app/feature.py").open(
        "a", encoding="utf-8", errors="strict"
    ) as stream:
        stream.write("VALUE = 2\n")
    with pytest.raises(ValueError, match="different inputs"):
        register(project)


def test_unchanged_launch_does_not_bump_but_edit_and_revert_each_do(project):
    first = register(project)["version"]
    assert not versions.scan(project)["changed"]
    path = project / "calendar_app/feature.py"
    original = path.read_bytes()
    path.write_bytes(original + b"VALUE = 2\n")
    second = versions.scan(project)["version"]
    assert second == versions.next_version(first, "change")
    assert not versions.scan(project)["changed"]
    path.write_bytes(original)
    assert versions.scan(project)["version"] == versions.next_version(second, "change")


def test_added_and_deleted_runtime_inputs_are_seen(project):
    register(project)
    new = project / "calendar_app/new.py"
    new.write_text("# -*- coding: utf-8 -*-\n", encoding="utf-8", errors="strict")
    assert versions.scan(project)["changed"]
    new.unlink()
    assert versions.scan(project)["changed"]


def test_version_date_channel_and_line_endings_do_not_create_false_changes(project):
    register(project)
    path = project / "calendar_app/feature.py"
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert not versions.scan(project)["changed"]
    metadata = project / versions.CORE[0]
    source = versions.text(metadata).replace(
        'APP_RELEASE_CHANNEL = "Dev"', 'APP_RELEASE_CHANNEL = "Stable"'
    )
    metadata.write_text(source, encoding="utf-8", errors="strict")
    assert not versions.scan(project)["changed"]


def test_same_store_payload_and_upload_retry_keep_reserved_version(project):
    first = register(project, "store", "release-cycle-1")
    assert not register(project, "store", "release-cycle-1")["changed"]
    assert not register(project, "store", "release-cycle-1-retry")["changed"]
    assert versions.current_version(project) == first["version"]
    (project / "calendar_app/feature.py").write_bytes(b"VALUE = 3\n")
    with pytest.raises(ValueError, match="different inputs"):
        register(project, "store", "release-cycle-1")
    assert register(project, "store", "release-cycle-2")["changed"]


def test_scan_excludes_user_database_credentials_and_test_only_changes(project):
    register(project)
    for name in ("desk_calendar.db", "desk_calendar.db-wal", "token.json", "credentials.json"):
        (project / "calendar_app" / name).write_bytes(b"not a runtime input")
    (project / "tests").mkdir()
    (project / "tests/test_demo.py").write_bytes(b"assert True\n")
    assert not versions.scan(project)["changed"]


def test_interrupted_write_recovers_same_event_without_double_increment(project, monkeypatch):
    initial = versions.current_version(project)
    writer = versions.atomic_write

    def interrupt(path, data):
        if path == project / "pyproject.toml":
            raise OSError("simulated interruption")
        writer(path, data)

    with monkeypatch.context() as local:
        local.setattr(versions, "atomic_write", interrupt)
        with pytest.raises(OSError):
            register(project)
    assert (project / ".versioning/transaction.json").exists()
    with versions.locked(project):
        assert not register(project)["changed"]
    assert versions.current_version(project) == versions.next_version(initial, "change")
    assert len(json.loads(versions.text(project / versions.HISTORY))["events"]) == 1


def test_recovery_never_overwrites_newer_user_edits(project, monkeypatch):
    writer = versions.atomic_write

    def interrupt(path, data):
        if path == project / "pyproject.toml":
            raise OSError("simulated interruption")
        writer(path, data)

    with monkeypatch.context() as local:
        local.setattr(versions, "atomic_write", interrupt)
        with pytest.raises(OSError):
            register(project)
    target = project / "pyproject.toml"
    target.write_bytes(target.read_bytes() + b"\n# newer user edit\n")
    snapshot = target.read_bytes()
    with pytest.raises(ValueError, match="newer user changes"):
        versions.recover(project)
    assert target.read_bytes() == snapshot


def test_exclusive_lock_blocks_second_version_writer(project):
    register(project)
    with versions.locked(project):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/manage_version.py"),
                "check",
                "--root",
                str(project),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=10,
        )
    assert result.returncode != 0
    assert "Version management failed" in result.stderr


def test_manual_version_edits_are_rejected(project):
    register(project)
    path = project / "pyproject.toml"
    path.write_text(
        versions.replace_one(r'^version = "[^"]+"$', 'version = "0.0.0"', versions.text(path)),
        encoding="utf-8",
        errors="strict",
    )
    ledger = json.loads(versions.text(project / versions.HISTORY))
    with pytest.raises(ValueError, match="mismatch"):
        versions.verify(project, ledger)


def test_history_chain_cannot_silently_skip_a_version_event(project):
    register(project)
    ledger = json.loads(versions.text(project / versions.HISTORY))
    ledger["events"][0]["previous_version"] = "0.0.0"
    with pytest.raises(ValueError, match="chain"):
        versions.verify(project, ledger)
