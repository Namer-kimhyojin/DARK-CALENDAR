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


@pytest.mark.parametrize(
    "settings,shared,running", [(True, False, False), (False, True, False), (False, False, True)]
)
def test_preexisting_state_diagnostic_records_only_boolean_categories(
    tmp_path, monkeypatch, settings, shared, running
):
    monkeypatch.setattr(smoke, "require_hosted_runner", lambda *_args: tmp_path)
    monkeypatch.setattr(smoke, "_desktop_preflight", lambda: {"session_id": 2})
    monkeypatch.setattr(smoke, "_settings_exists", lambda: settings)
    monkeypatch.setattr(smoke, "Path", lambda _path: SimpleNamespace(exists=lambda: shared))
    process = SimpleNamespace(pid=1234, info={"name": "DarkCalendar.exe"})
    monkeypatch.setitem(
        sys.modules,
        "psutil",
        SimpleNamespace(process_iter=lambda _attributes: [process] if running else []),
    )
    summary = {}
    with pytest.raises(RuntimeError, match="refusing to reset"):
        smoke.run(SimpleNamespace(evidence=tmp_path), summary)
    assert summary["preexisting_state"] == {
        "settings_key_exists": settings,
        "shared_directory_exists": shared,
        "calendar_process_running": running,
    }
    assert all(isinstance(value, bool) for value in summary["preexisting_state"].values())


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
        "Windows fatal exception: code 0x8001010d",
        "Fatal Python error: access violation",
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


READY_LOG = (
    "Unified database initialized successfully.\n"
    "System tray and unified shortcuts initialized.\n"
    "Idle detector (AlarmWorker) initialized and started.\n"
)


@pytest.mark.parametrize("missing", READY_LOG.splitlines())
def test_runtime_readiness_requires_every_actual_native_marker(missing):
    assert smoke.runtime_ready(READY_LOG)
    assert not smoke.runtime_ready(READY_LOG.replace(missing, ""))


@pytest.mark.parametrize(
    "width,height,dpi,style,expected",
    [
        (560, 340, 96, 0x88, True),
        (840, 510, 144, 0x88, True),
        (1018, 700, 96, 0x80, False),
        (560, 340, 96, 0x80, False),
    ],
)
def test_splash_detection_uses_size_dpi_and_topmost_tool_flags(width, height, dpi, style, expected):
    metadata = [
        {"visible": True, "rectangle": [0, 0, width, height], "dpi": dpi, "extended_style": style}
    ]
    assert smoke.splash_visible(metadata) is expected


class NativeWindow:
    def __init__(self, handle, *, count=25, visible=True):
        self.handle = handle
        self.button = SimpleNamespace(window_text=lambda: " Settings", is_visible=lambda: visible)
        self.count = count

    def descendants(self, control_type=None):
        return [self.button] if control_type == "Button" else [self.button] * self.count


def test_only_actual_qualified_main_is_selected_among_startup_windows():
    splash = NativeWindow(1, count=0)
    main = NativeWindow(2)
    assert smoke.select_qualified_main([splash, main], lambda _a, _b: False) is main
    assert smoke.select_qualified_main([NativeWindow(3, count=19)], lambda _a, _b: False) is None


def test_independent_qualified_main_windows_still_fail():
    with pytest.raises(RuntimeError, match="independent qualified"):
        smoke.select_qualified_main([NativeWindow(1), NativeWindow(2)], lambda _a, _b: False)


def test_only_native_parent_child_duplicates_are_deduplicated():
    parent, child = NativeWindow(1), NativeWindow(2)
    assert smoke.select_qualified_main([child, parent], lambda a, b: (a, b) == (1, 2)) is parent


@pytest.mark.parametrize("ready,splash", [(False, False), (True, True)])
def test_uia_is_not_imported_before_runtime_ready_and_splash_gone(
    tmp_path, monkeypatch, ready, splash
):
    monkeypatch.setitem(sys.modules, "win32gui", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "pywinauto", None)
    monkeypatch.setattr(smoke, "_window_metadata", lambda _processes: [])
    monkeypatch.setattr(smoke, "splash_visible", lambda _windows: splash)
    assert smoke._main_window([], tmp_path, ready=ready) is None
    observation = __import__("json").loads(
        (tmp_path / "window-observation.json").read_text(encoding="utf-8", errors="strict")
    )
    assert observation["runtime_ready_log"] is ready


def test_runner_input_records_real_event_and_last_input_change(tmp_path, monkeypatch):
    user, kernel = Mock(), Mock()
    last_times = iter([640000, 999990])

    def last_input(pointer):
        pointer._obj.dwTime = next(last_times)
        return True

    user.GetLastInputInfo.side_effect = last_input
    user.SendInput.return_value = 1
    kernel.GetTickCount64.return_value = 1000000
    monkeypatch.setattr(
        smoke.ctypes, "WinDLL", lambda name, **_kwargs: user if name == "user32" else kernel
    )
    monkeypatch.setattr(smoke, "require_hosted_runner", lambda *_args: tmp_path)
    monkeypatch.setattr(smoke.time, "sleep", lambda _seconds: None)
    assert smoke._reset_runner_idle(tmp_path) == {
        "before_idle_ms": 360000,
        "after_idle_ms": 10,
        "real_mouse_input_events": 1,
    }
    user.SendInput.assert_called_once()
    assert user.SendInput.call_args.args[0] == 1


def test_runner_input_failure_cannot_continue(tmp_path, monkeypatch):
    user = Mock()
    user.SendInput.return_value = 0
    monkeypatch.setattr(smoke.ctypes, "WinDLL", lambda *_args, **_kwargs: user)
    monkeypatch.setattr(smoke, "require_hosted_runner", lambda *_args: tmp_path)
    monkeypatch.setattr(smoke, "_idle_ms", lambda *_args: 10000)
    with pytest.raises(RuntimeError, match="real mouse input"):
        smoke._reset_runner_idle(tmp_path)


@pytest.mark.parametrize(
    "window,button,valid",
    [
        ([0, 0, 1018, 700], [900, 0, 1000, 40], True),
        ([0, 0, 1200, 700], [1080, 0, 1180, 40], False),
        ([0, 0, 1018, 700], [1000, 0, 1100, 40], False),
        ([-10, 0, 1000, 700], [900, 0, 990, 40], False),
    ],
)
def test_window_and_system_button_must_be_inside_actual_display(window, button, valid):
    def control(rect):
        return SimpleNamespace(
            rectangle=lambda: SimpleNamespace(
                **dict(zip(["left", "top", "right", "bottom"], rect, strict=True))
            )
        )

    if valid:
        assert (
            smoke.validate_window_bounds(control(window), control(button), 1024, 768)["window"]
            == window
        )
    else:
        with pytest.raises(RuntimeError, match="outside"):
            smoke.validate_window_bounds(control(window), control(button), 1024, 768)


def test_failure_records_remaining_process_and_exit_code_without_terminating(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke, "require_hosted_runner", lambda *_args: tmp_path)
    parent = SimpleNamespace(pid=42, poll=lambda: None)

    def failed_launch(_payload, _profile, _evidence, *, diagnostic, **_options):
        diagnostic.update(parent=parent, executable=tmp_path / "DarkCalendar.exe", started=100.0)
        raise RuntimeError("observed UI failure")

    monkeypatch.setattr(smoke, "_launch_cycle", failed_launch)
    monkeypatch.setattr(smoke, "_related_processes", lambda *_args: [SimpleNamespace(pid=42)])
    monkeypatch.setattr(smoke, "_window_metadata", lambda _processes: [])
    with pytest.raises(RuntimeError, match="observed UI"):
        smoke.launch_cycle(tmp_path, tmp_path / "profile", tmp_path / "evidence")
    state = __import__("json").loads(
        (tmp_path / "evidence/failure-process-state.json").read_text(
            encoding="utf-8", errors="strict"
        )
    )
    assert state == {
        "launched_parent_pid": 42,
        "parent_exit_code": None,
        "remaining_native_pids": [42],
        "force_killed": False,
    }
