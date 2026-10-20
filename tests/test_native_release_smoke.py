# -*- coding: utf-8 -*-
"""Test the CI-only guard and evidence rejection without launching any app."""

from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from scripts import native_release_smoke as smoke


def hosted_environment(temporary):
    return {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_OS": "Windows",
        "RUNNER_TEMP": str(temporary),
    }


@pytest.mark.parametrize(
    "key", ["GITHUB_ACTIONS", "RUNNER_ENVIRONMENT", "RUNNER_OS", "RUNNER_TEMP"]
)
def test_guard_rejects_missing_runner_identity(tmp_path, key):
    environment = hosted_environment(tmp_path)
    del environment[key]
    with pytest.raises(RuntimeError):
        smoke.require_hosted_runner(environment, "win32", tmp_path / "evidence")


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_guard_rejects_other_platforms(tmp_path, platform):
    with pytest.raises(RuntimeError):
        smoke.require_hosted_runner(hosted_environment(tmp_path), platform, tmp_path / "evidence")


@pytest.mark.parametrize("relative", ["", "../outside"])
def test_guard_rejects_unowned_evidence_directory(tmp_path, relative):
    with pytest.raises(RuntimeError):
        smoke.require_hosted_runner(hosted_environment(tmp_path), "win32", tmp_path / relative)


def test_guard_accepts_only_nested_hosted_evidence(tmp_path):
    assert (
        smoke.require_hosted_runner(hosted_environment(tmp_path), "win32", tmp_path / "evidence")
        == tmp_path
    )


def test_local_main_refuses_before_imports_or_file_writes(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    mutation = Mock(side_effect=AssertionError("Local app state must never be touched"))
    monkeypatch.setattr(smoke, "run", mutation)
    evidence = tmp_path / "never-created"
    assert (
        smoke.main(
            [
                "--payload",
                ".",
                "--baseline-payload",
                ".",
                "--expected-version",
                "4.5.0",
                "--evidence",
                str(evidence),
            ]
        )
        == 1
    )
    mutation.assert_not_called()
    assert not evidence.exists()


@pytest.mark.parametrize(
    "existing", [(True, False, []), (False, True, []), (False, False, [43380])]
)
def test_existing_state_is_refused_instead_of_reset(existing):
    with pytest.raises(RuntimeError, match="refusing to reset"):
        smoke.require_fresh_state(*existing)


def test_process_scan_skips_inaccessible_creation_time(tmp_path, monkeypatch):
    class ProcessError(Exception):
        pass

    executable = tmp_path / "DarkCalendar.exe"
    inaccessible = SimpleNamespace(info={"create_time": None, "exe": str(executable)})
    expected = SimpleNamespace(info={"create_time": 100.0, "exe": str(executable)})
    unrelated = SimpleNamespace(info={"create_time": 100.0, "exe": None})
    monkeypatch.setitem(
        sys.modules,
        "psutil",
        SimpleNamespace(
            Error=ProcessError,
            process_iter=lambda _attributes: [inaccessible, expected, unrelated],
        ),
    )
    assert smoke._related_processes(executable, 100.0) == [expected]


class Capture:
    def __init__(self, values, width=800, height=600):
        self.width, self.height = width, height
        self.values = values
        self.size = (width, height)

    def convert(self, _mode):
        return self

    def getextrema(self):
        return [(min(self.values), max(self.values))] * 3

    def histogram(self):
        histogram = [0] * 256
        for value in self.values:
            histogram[value] += 1
        return histogram * 3


@pytest.mark.parametrize("values", [[0] * 10, [8, 12] * 5, [255] * 10, [80, 81] * 5])
def test_black_blank_and_nearly_uniform_captures_fail(values):
    with pytest.raises(RuntimeError):
        smoke.validate_capture(Capture(values))


def test_small_capture_fails_even_with_visible_pixels():
    with pytest.raises(RuntimeError, match="small"):
        smoke.validate_capture(Capture([0, 255], width=200))


def test_nonblank_capture_records_quality_metrics():
    assert smoke.validate_capture(Capture([0, 64, 128, 255]))["stddev"][0] > 30


def launch_log(database, *, version="4.5.0", sqlite="3.54.1"):
    return f"Database startup: pid=123 app_version={version} sqlite={sqlite} db={database}\n"


def test_log_requires_actual_version_database_and_sqlite(tmp_path):
    database = tmp_path / "desk_calendar.db"
    smoke.validate_launch_log(launch_log(database), "4.5.0", database, "3.54.1")
    for text in [
        "",
        launch_log(database, version="4.3.3"),
        launch_log(database, sqlite="3.50.4"),
        launch_log(tmp_path / "wrong.db"),
    ]:
        with pytest.raises(RuntimeError):
            smoke.validate_launch_log(text, "4.5.0", database, "3.54.1")


@pytest.mark.parametrize(
    "error",
    [
        "[ERROR] connection failed",
        "Database startup aborted",
        "Unhandled exception",
        "database disk image is malformed",
        "Traceback (most recent call last)",
    ],
)
def test_fresh_error_cannot_be_hidden_by_success_marker(tmp_path, error):
    database = tmp_path / "desk_calendar.db"
    with pytest.raises(RuntimeError, match="error|traceback"):
        smoke.validate_launch_log(launch_log(database) + error, "4.5.0", database, "3.54.1")


class SyntheticEngine:
    def __init__(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute(
            "CREATE TABLE calendar(id TEXT PRIMARY KEY,type TEXT,name TEXT,is_active INTEGER,is_visible INTEGER)"
        )
        self.connection.execute(
            "CREATE TABLE unified_task(name TEXT,type TEXT,deadline TEXT,end_date TEXT,all_day INTEGER,calendar_id TEXT REFERENCES calendar(id))"
        )

    def query(self, _database, sql, *, writable=False):
        rows = self.connection.execute(sql).fetchall()
        self.connection.commit()
        return [[None if value is None else str(value) for value in row] for row in rows]


def test_synthetic_seed_and_preservation_checks_execute_real_sql():
    engine = SyntheticEngine()
    try:
        smoke.seed_fixture(engine, Path("unused-synthetic-only.db"))
        assert smoke.inspect_database(engine, Path("unused-synthetic-only.db"), True)[
            "fixture_preserved"
        ]
        engine.connection.execute("DELETE FROM unified_task")
        with pytest.raises(RuntimeError, match="lost"):
            smoke.inspect_database(engine, Path("unused-synthetic-only.db"), True)
    finally:
        engine.connection.close()


@pytest.mark.parametrize(
    "responses,error", [([[["bad"]]], "integrity"), ([[["ok"]], [["1"]]], "foreign-key")]
)
def test_corrupt_or_invalid_database_fails(responses, error):
    engine = Mock()
    engine.query.side_effect = responses
    with pytest.raises(RuntimeError, match=error):
        smoke.inspect_database(engine, Path("unused.db"), False)
