# -*- coding: utf-8 -*-
"""Test the CI-only guard and evidence rejection without launching any app."""

import json
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
    attach = Mock(side_effect=AssertionError("No debugger may attach during startup"))
    assert smoke._main_window([], tmp_path, ready=ready, before_uia=attach) is None
    attach.assert_not_called()
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


def test_owned_exit_modal_is_selected_from_win32_even_when_uia_root_list_omits_it():
    modal = {"handle": 4, "pid": 42, "parent": 3, "title": "Exit", "visible": True}
    unrelated = {**modal, "handle": 5, "parent": 99}
    assert smoke.select_exit_modal([modal, unrelated], 42, 3) == modal
    assert smoke.select_exit_modal([modal], 43, 3) is None
    with pytest.raises(RuntimeError, match="More than one"):
        smoke.select_exit_modal([modal, {**modal, "handle": 6}], 42, 3)


def test_normal_exit_uses_observed_owned_hwnd_instead_of_only_uia_desktop_roots(
    tmp_path, monkeypatch
):
    yes = Mock()
    yes.window_text.return_value = "&Yes"
    yes.element_info.control_type = "Button"
    dialog = Mock()
    dialog.descendants.return_value = [yes]
    exit_item = Mock()
    exit_item.window_text.return_value = "Exit"
    menu_owner = Mock()
    menu_owner.process_id.return_value = 42
    menu_owner.descendants.return_value = [exit_item]
    desktop = Mock()
    desktop.windows.return_value = [menu_owner]  # The actual Exit dialog is omitted.
    desktop.window.return_value.wrapper_object.return_value = dialog
    monkeypatch.setitem(sys.modules, "pywinauto", SimpleNamespace(Desktop=lambda **_kw: desktop))
    main = SimpleNamespace(handle=3, process_id=lambda: 42)
    monkeypatch.setattr(smoke, "system_button", lambda _window: Mock())
    monkeypatch.setattr(
        smoke,
        "_window_metadata",
        lambda _processes: [
            {"handle": 4, "pid": 42, "parent": 3, "title": "Exit", "visible": True}
        ],
    )
    monkeypatch.setattr(smoke, "_capture", lambda *_args, **_kw: {})
    monkeypatch.setattr(smoke.time, "sleep", lambda _seconds: None)
    phases = []
    smoke._normal_exit(main, [SimpleNamespace(pid=42)], tmp_path, phases.append)
    desktop.window.assert_called_once_with(handle=4)
    yes.click_input.assert_called_once_with()
    assert phases[-2:] == ["exit_confirmation_observed", "exit_yes_clicked"]


def main_controls(*, fixture=False):
    names = ["Main Calendar", "Today's Schedule", "No schedules posted for today."]
    names += [f"2026-10-{day:02d} date cell" for day in range(1, 29)]
    if fixture:
        names.append(smoke.FIXTURE_NAME)
    return [{"name": name, "control_type": "Text"} for name in names]


def test_main_evidence_requires_real_calendar_and_expected_task_content():
    assert smoke.validate_main_content(main_controls(), False)["date_cells"] == 28
    assert smoke.validate_main_content(main_controls(fixture=True), True)["fixture_visible"]
    with pytest.raises(RuntimeError, match="persisted schedule"):
        smoke.validate_main_content(main_controls(), True)
    with pytest.raises(RuntimeError, match="date cells"):
        smoke.validate_main_content([{"name": "Settings"}], False)


@pytest.mark.parametrize(
    "error",
    [
        "Windows fatal exception: access violation",
        "Windows fatal exception: code 0x8001010e",
        "Fatal Python error: segmentation fault",
        "[ERROR] database locked",
    ],
)
def test_pending_known_rpc_never_hides_another_fatal_or_database_error(error):
    text = "Windows fatal exception: code 0x8001010d\n" + error
    with pytest.raises(RuntimeError):
        smoke.check_runtime_log(text, pending=True)


def test_only_directly_classified_rpc_may_leave_pending_state():
    text = "Windows fatal exception: code 0x8001010d\nCurrent thread 0x1234\n"
    assert smoke.check_runtime_log(text, pending=True) == 1
    with pytest.raises(RuntimeError):
        smoke.check_runtime_log(text)
    with pytest.raises(RuntimeError):
        smoke.check_runtime_log(text, observed_rpc={"classification": "handled_first_chance"})
    assert (
        smoke.check_runtime_log(
            text,
            observed_rpc={"classification": "handled_first_chance", "rpc_event_count": 1},
        )
        == 1
    )


@pytest.mark.parametrize("obscured", [False, True])
def test_capture_verifies_foreground_and_real_window_point_ownership(
    tmp_path, monkeypatch, obscured
):
    gui = Mock()
    gui.GetForegroundWindow.return_value = 3
    gui.WindowFromPoint.return_value = 44 if obscured else 3
    gui.GetAncestor.side_effect = lambda handle, _flag: handle
    gui.EnumWindows.side_effect = lambda _callback, _context: None
    monkeypatch.setitem(sys.modules, "win32gui", gui)
    monkeypatch.setitem(sys.modules, "win32con", SimpleNamespace(SW_MINIMIZE=6, SW_RESTORE=9))
    monkeypatch.setattr(smoke, "require_hosted_runner", lambda *_args: tmp_path)
    monkeypatch.setattr(smoke, "_dismiss_paging_notice", lambda *_args: None)
    monkeypatch.setattr(smoke.time, "sleep", lambda _seconds: None)
    window = SimpleNamespace(
        handle=3,
        rectangle=lambda: SimpleNamespace(left=0, top=0, right=1000, bottom=700),
    )
    if obscured:
        with pytest.raises(RuntimeError, match="obscured"):
            smoke._prepare_visible_main(window, tmp_path)
    else:
        assert not smoke._prepare_visible_main(window, tmp_path)["app_window_style_changed"]


def test_foreground_preparation_cannot_run_on_local_desktop(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(RuntimeError, match="disposable"):
        smoke._prepare_visible_main(SimpleNamespace(handle=43380), tmp_path)


def test_ready_debugger_attach_precedes_first_uia_probe(tmp_path, monkeypatch):
    order = []
    monkeypatch.setitem(sys.modules, "win32gui", SimpleNamespace(IsChild=lambda *_args: False))

    def desktop(**_kwargs):
        order.append("uia")
        return Mock()

    monkeypatch.setitem(sys.modules, "pywinauto", SimpleNamespace(Desktop=desktop))
    monkeypatch.setattr(smoke, "_window_metadata", lambda _processes: [])
    monkeypatch.setattr(smoke, "select_qualified_main", lambda *_args: None)
    smoke._main_window([], tmp_path, ready=True, before_uia=lambda: order.append("attach_ready"))
    assert order == ["attach_ready", "uia"]


def test_repeated_readiness_probes_attach_debugger_only_once(tmp_path, monkeypatch):
    observed = Mock()
    constructor = Mock(return_value=observed)
    monkeypatch.setattr(smoke, "ExceptionObserver", constructor)
    log = tmp_path / "synthetic.log"
    log.write_text("clean startup", encoding="utf-8", errors="strict")
    diagnostic, phases = {}, []
    for _index in range(3):
        assert (
            smoke.start_ready_observer(
                SimpleNamespace(pid=42), tmp_path, log, diagnostic, phases.append
            )
            is observed
        )
    constructor.assert_called_once()
    observed.start.assert_called_once_with()
    assert phases == ["exception_observer_attached_before_first_uia"]


def test_pre_attach_rpc_stops_launch_before_any_debugger_or_uia(tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    log = profile / "kimhyojin/Dark Calendar/crash.log"
    log.parent.mkdir(parents=True)
    process = SimpleNamespace(pid=42, poll=lambda: None)

    def fake_popen(*_args, **_kwargs):
        log.write_text(
            "Windows fatal exception: code 0x8001010d\n", encoding="utf-8", errors="strict"
        )
        return process

    monkeypatch.setattr(smoke.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(smoke, "_reset_runner_idle", lambda *_args: {})
    monkeypatch.setattr(smoke, "_related_processes", lambda *_args: [process])
    constructor, uia = Mock(), Mock()
    monkeypatch.setattr(smoke, "ExceptionObserver", constructor)
    monkeypatch.setattr(smoke, "_main_window", uia)
    with pytest.raises(RuntimeError, match="Unclassified"):
        smoke._launch_cycle(
            tmp_path, profile, tmp_path / "evidence", version="4.6.4", sqlite_version="3.54.1"
        )
    constructor.assert_not_called()
    uia.assert_not_called()


def paging_metadata():
    return {
        "pid": 99,
        "executable": r"C:\Windows\System32\rundll32.exe",
        "title": "System Properties",
        "class_name": "#32770",
        "children": [
            {"class_name": "Static", "text": smoke.PAGING_NOTICE, "handle": 4, "control_id": 9},
            {"class_name": "Button", "text": "OK", "handle": 5, "control_id": 1},
        ],
    }


def test_only_exact_os_paging_information_notice_can_be_acknowledged(monkeypatch):
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    assert smoke.select_paging_notice(paging_metadata(), 42) == 5


@pytest.fixture
def observed_performance_paging_notice():
    # Exact synthetic-runner observation from run39360438071, not a user profile.
    return json.loads(
        r"""{
          "handle": 65682,
          "pid": 6816,
          "title": "System Properties",
          "class_name": "#32770",
          "executable": "C:\\Windows\\System32\\SystemPropertiesPerformance.exe",
          "children": [
            {"handle": 65684, "class_name": "Button", "text": "OK", "control_id": 2},
            {"handle": 65686, "class_name": "Static", "text": "", "control_id": 20},
            {"handle": 65690, "class_name": "Static", "text": "Windows created a temporary paging file on your computer because of a problem that occurred with your paging file configuration when you started your computer.  The total paging file size for all disk drives may be somewhat larger than the size you specified.", "control_id": 65535}
          ]
        }"""
    )


def test_observed_windows_performance_notice_has_ok_id_two(
    monkeypatch, observed_performance_paging_notice
):
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    assert smoke.select_paging_notice(observed_performance_paging_notice, 42) == 65684


@pytest.mark.parametrize(
    "change",
    [
        {"executable": r"C:\Windows\System32\rundll32.exe"},
        {"executable": r"C:\Temp\SystemPropertiesPerformance.exe"},
        {"pid": 42},
        {"title": "Other information"},
    ],
)
def test_observed_ok_id_two_exception_cannot_extend_to_other_fingerprints(
    monkeypatch, observed_performance_paging_notice, change
):
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    observed_performance_paging_notice.update(change)
    assert smoke.select_paging_notice(observed_performance_paging_notice, 42) is None


def test_observed_performance_notice_still_requires_unique_exact_ok(
    monkeypatch, observed_performance_paging_notice
):
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    observed_performance_paging_notice["children"].append(
        {"handle": 777, "class_name": "Button", "text": "OK", "control_id": 2}
    )
    assert smoke.select_paging_notice(observed_performance_paging_notice, 42) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("pid", 42),
        ("executable", r"C:\Temp\rundll32.exe"),
        ("executable", r"C:\Windows\System32\DarkCalendar.exe"),
        ("title", "Air Calendar Error"),
        ("class_name", "Qt6102QWindowIcon"),
    ],
)
def test_app_errors_or_untrusted_paging_lookalikes_are_never_closed(monkeypatch, field, value):
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    metadata = paging_metadata()
    metadata[field] = value
    assert smoke.select_paging_notice(metadata, 42) is None


def test_nonmatching_information_or_wrong_button_cannot_be_closed(monkeypatch):
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    metadata = paging_metadata()
    metadata["children"][0]["text"] = "Change virtual memory settings?"
    assert smoke.select_paging_notice(metadata, 42) is None
    metadata = paging_metadata()
    metadata["children"][1]["text"] = "Apply"
    assert smoke.select_paging_notice(metadata, 42) is None


@pytest.mark.parametrize("application_owns_dialog", [False, True])
def test_only_fingerprinted_foreign_os_information_receives_ok(
    tmp_path, monkeypatch, application_owns_dialog
):
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    gui = Mock()
    texts = {99: "System Properties", 4: smoke.PAGING_NOTICE, 5: "OK"}
    classes = {99: "#32770", 4: "Static", 5: "Button"}
    gui.GetWindowText.side_effect = texts.__getitem__
    gui.GetClassName.side_effect = classes.__getitem__
    gui.GetDlgCtrlID.side_effect = lambda handle: 1 if handle == 5 else 9
    gui.IsWindowVisible.return_value = True
    gui.IsWindow.return_value = False
    gui.EnumWindows.side_effect = lambda callback, context: callback(99, context)
    gui.EnumChildWindows.side_effect = lambda _owner, callback, context: [
        callback(handle, context) for handle in (4, 5)
    ]
    owner = 42 if application_owns_dialog else 99
    monkeypatch.setitem(sys.modules, "win32gui", gui)
    monkeypatch.setitem(
        sys.modules,
        "win32process",
        SimpleNamespace(GetWindowThreadProcessId=lambda _handle: (17, owner)),
    )
    monkeypatch.setitem(
        sys.modules,
        "psutil",
        SimpleNamespace(
            Process=lambda _pid: SimpleNamespace(exe=lambda: paging_metadata()["executable"])
        ),
    )
    desktop = Mock()
    desktop_type = Mock(return_value=desktop)
    monkeypatch.setitem(sys.modules, "pywinauto", SimpleNamespace(Desktop=desktop_type))
    monkeypatch.setattr(smoke, "require_hosted_runner", lambda *_args: tmp_path)
    smoke._dismiss_paging_notice(SimpleNamespace(process_id=lambda: 42), tmp_path)
    if application_owns_dialog:
        desktop_type.assert_not_called()
    else:
        desktop_type.assert_called_once_with(backend="win32")
        desktop.window.assert_called_once_with(handle=5)
        desktop.window.return_value.wrapper_object.return_value.click_input.assert_called_once()


def test_paging_notice_dismissal_cannot_operate_on_local_desktop(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(RuntimeError, match="disposable"):
        smoke._dismiss_paging_notice(SimpleNamespace(process_id=lambda: 43380), tmp_path)


def test_capture_grid_catches_center_popup_missed_by_previous_four_samples():
    samples = smoke.capture_points([6, 6, 1018, 706], [])
    assert len(samples) == 63
    assert {"source": "window_grid", "point": [512, 356]} in samples
    assert any(313 <= x <= 717 and 314 <= y <= 498 for x, y in [s["point"] for s in samples])


def test_required_calendar_task_content_rectangles_add_interior_samples():
    controls = [{"name": "Main Calendar", "rectangle": [100, 300, 500, 700]}]
    samples = smoke.capture_points([0, 0, 1000, 700], controls)
    assert {"source": "Main Calendar", "point": [300, 500]} in samples
    assert {"source": "Main Calendar", "point": [200, 400]} in samples


def test_capture_checks_visibility_both_immediately_before_and_after_pixels(tmp_path, monkeypatch):
    phases = []
    rendered = Mock()
    rendered.width, rendered.height = 1000, 700

    def capture():
        phases.append("pixels")
        return rendered

    window = SimpleNamespace(handle=3, capture_as_image=capture, process_id=lambda: 42)
    monkeypatch.setattr(smoke, "validate_capture", lambda _image: {})
    monkeypatch.setattr(smoke, "sha256", lambda _path: "f" * 64)
    smoke._capture(window, tmp_path / "main.png", verify_visible=phases.append)
    assert phases == ["before", "pixels", "after"]


def summary_metadata():
    return {
        "handle": 9,
        "pid": 42,
        "parent": 3,
        "visible": True,
        "title": "Today's Events & Due Tasks",
        "class_name": "Qt6102QWindow",
    }


def test_only_exact_owned_startup_summary_is_selected():
    summary = summary_metadata()
    assert smoke.select_startup_summary([summary], 42, 3) == summary
    for field, value in (
        ("pid", 99),
        ("parent", 99),
        ("visible", False),
        ("title", "Database initialization failed"),
        ("class_name", "Qt6102QWindowIcon"),
    ):
        assert smoke.select_startup_summary([{**summary, field: value}], 42, 3) is None
    with pytest.raises(RuntimeError, match="More than one"):
        smoke.select_startup_summary([summary, {**summary, "handle": 10}], 42, 3)


def briefing_button(name="Confirm", *, visible=True, enabled=True, identity="primary_btn"):
    return SimpleNamespace(
        window_text=lambda: name,
        is_visible=lambda: visible,
        is_enabled=lambda: enabled,
        element_info=SimpleNamespace(automation_id=f"DailySummaryDialog.{identity}"),
    )


def test_summary_uses_only_visible_primary_confirm_and_keeps_automatic_display_unchanged():
    confirm = briefing_button()
    disable = briefing_button("Stop automatic reminders", identity="disable_auto")
    dialog = SimpleNamespace(
        window_text=lambda: "Today's Briefing", descendants=lambda **_kw: [disable, confirm]
    )
    assert smoke.briefing_confirm(dialog, [{"name": smoke.FIXTURE_NAME}]) is confirm


@pytest.mark.parametrize(
    "button",
    [
        briefing_button(visible=False),
        briefing_button(enabled=False),
        briefing_button(identity="settings_save"),
        briefing_button("Stop automatic reminders"),
    ],
)
def test_summary_never_clicks_hidden_disabled_unidentified_or_settings_buttons(button):
    dialog = SimpleNamespace(
        window_text=lambda: "Today's Briefing", descendants=lambda **_kw: [button]
    )
    with pytest.raises(RuntimeError, match="primary Confirm"):
        smoke.briefing_confirm(dialog, [{"name": smoke.FIXTURE_NAME}])


def test_summary_requires_original_briefing_and_synthetic_schedule_content():
    dialog = SimpleNamespace(window_text=lambda: "Today's Briefing")
    with pytest.raises(RuntimeError, match="synthetic schedule"):
        smoke.briefing_confirm(dialog, [{"name": "Database error"}])


@pytest.mark.parametrize("hwnd_retained", [False, True])
@pytest.mark.parametrize("main_enabled", [False, True])
def test_startup_summary_normal_confirm_records_raw_evidence_and_releases_modal(
    tmp_path, monkeypatch, hwnd_retained, main_enabled
):
    monkeypatch.setattr(smoke, "require_hosted_runner", lambda *_args: tmp_path)
    gui = Mock()
    gui.WindowFromPoint.return_value = 9
    gui.GetAncestor.return_value = 9
    gui.IsWindow.return_value = hwnd_retained
    gui.IsWindowVisible.return_value = False
    monkeypatch.setitem(sys.modules, "win32gui", gui)
    confirm = Mock()
    state = {"clicked": False}

    class Element:
        @property
        def automation_id(self):
            if state["clicked"]:
                raise AssertionError("Closed UIA elements cannot be queried again")
            return "DailySummaryDialog.primary_btn"

    confirm.element_info = Element()
    confirm.click_input.side_effect = lambda: state.update(clicked=True)
    confirm.rectangle.return_value = SimpleNamespace(left=500, top=500, right=600, bottom=550)
    dialog = Mock()
    desktop = Mock()
    desktop.window.return_value.wrapper_object.return_value = dialog
    monkeypatch.setitem(sys.modules, "pywinauto", SimpleNamespace(Desktop=lambda **_kw: desktop))
    monkeypatch.setattr(smoke, "_window_metadata", lambda _processes: [summary_metadata()])
    monkeypatch.setattr(smoke, "_controls", lambda _dialog: [{"name": smoke.FIXTURE_NAME}])
    monkeypatch.setattr(smoke, "briefing_confirm", lambda *_args: confirm)
    monkeypatch.setattr(smoke, "_capture", lambda *_args, **_kw: {"path": "startup-briefing.png"})
    monkeypatch.setattr(
        smoke, "system_button", lambda _window: SimpleNamespace(is_enabled=lambda: main_enabled)
    )
    phases = []
    if not main_enabled:
        with pytest.raises(RuntimeError, match="regain enabled"):
            smoke._acknowledge_startup_summary(
                SimpleNamespace(handle=3, process_id=lambda: 42), [], tmp_path, True, phases.append
            )
        confirm.click_input.assert_called_once_with()
        return
    result = smoke._acknowledge_startup_summary(
        SimpleNamespace(handle=3, process_id=lambda: 42), [], tmp_path, True, phases.append
    )
    desktop.window.assert_called_once_with(handle=9)
    confirm.click_input.assert_called_once_with()
    assert not result["automatic_display_disabled"]
    assert not result["settings_changed_by_harness"]
    assert not result["visible_after_confirm"]
    assert result["hwnd_exists_after_confirm"] is hwnd_retained
    assert phases == ["startup_briefing_fixture_observed", "startup_briefing_confirmed"]
    assert (tmp_path / "startup-briefing-accessibility.json").is_file()
    assert (tmp_path / "startup-briefing-acknowledged.json").is_file()


def test_unknown_owned_popup_is_not_acknowledged(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke, "require_hosted_runner", lambda *_args: tmp_path)
    monkeypatch.setitem(sys.modules, "win32gui", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "pywinauto", None)
    monkeypatch.setattr(
        smoke,
        "_window_metadata",
        lambda _processes: [{**summary_metadata(), "title": "Unhandled exception"}],
    )
    result = smoke._acknowledge_startup_summary(
        SimpleNamespace(handle=3, process_id=lambda: 42), [], tmp_path, True, Mock()
    )
    assert result == {"seen": False, "settings_changed_by_harness": False}


def test_unexpected_summary_in_empty_profile_fails_before_any_click(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke, "require_hosted_runner", lambda *_args: tmp_path)
    monkeypatch.setitem(sys.modules, "win32gui", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "pywinauto", None)
    monkeypatch.setattr(smoke, "_window_metadata", lambda _processes: [summary_metadata()])
    with pytest.raises(RuntimeError, match="empty fresh profile"):
        smoke._acknowledge_startup_summary(
            SimpleNamespace(handle=3, process_id=lambda: 42), [], tmp_path, False, Mock()
        )


def test_owned_modal_disabling_main_does_not_prevent_main_identification():
    main = NativeWindow(3)
    main.button.is_enabled = lambda: False
    assert smoke.select_qualified_main([main], lambda *_args: False) is main


def test_daily_briefing_is_confirmed_before_main_foreground_semantics_and_capture(
    tmp_path, monkeypatch
):
    state = {"disabled": True, "active": False}
    order = []

    def acknowledge(*_args):
        assert state["disabled"]
        order.append("normal_confirm")
        state["disabled"] = False
        return {"seen": True}

    def foreground(*_args):
        assert not state["disabled"]
        state["active"] = True
        order.append("main_foreground")
        return {"foreground_handle": 3}

    def controls(_window):
        assert state["active"] and not state["disabled"]
        order.append("restored_fixture_semantics")
        return [*main_controls(fixture=True), {"name": "Settings"}]

    def visibility(_window, _evidence, _controls, stage):
        assert state["active"] and not state["disabled"]
        order.append(f"grid_{stage}")

    def capture(_window, _path, *, verify_visible):
        verify_visible("before")
        order.append("pixels")
        verify_visible("after")
        return {"path": "main-window.png"}

    monkeypatch.setattr(smoke, "_acknowledge_startup_summary", acknowledge)
    monkeypatch.setattr(smoke, "_prepare_visible_main", foreground)
    monkeypatch.setattr(smoke, "_controls", controls)
    monkeypatch.setattr(smoke, "_verify_capture_visibility", visibility)
    monkeypatch.setattr(smoke, "_capture", capture)
    result = smoke.prepare_main_capture(SimpleNamespace(handle=3), [], tmp_path, True, Mock())
    assert result[2]["fixture_visible"]
    assert order == [
        "normal_confirm",
        "main_foreground",
        "restored_fixture_semantics",
        "grid_before",
        "pixels",
        "grid_after",
    ]
