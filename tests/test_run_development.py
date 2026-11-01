# -*- coding: utf-8 -*-
"""Source launches must use the verified SQLite runtime without a fallback."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from scripts import run_development as launcher


@pytest.fixture
def environment(tmp_path, monkeypatch):
    root = tmp_path / "한글 source folder"
    root.mkdir()
    python = root / "private runtime" / "python.exe"
    python.parent.mkdir()
    python.write_bytes(b"synthetic executable, never run")
    monkeypatch.setattr(launcher, "ROOT", root)
    monkeypatch.setattr(launcher, "_host_architecture", lambda: "x64")
    prepare = Mock(return_value={"passed": True, "python_executable": str(python)})
    child = Mock(return_value=0)
    monkeypatch.setattr(launcher.prepare_sqlite_build_runtime, "prepare", prepare)
    monkeypatch.setattr(launcher.subprocess, "call", child)
    return root, python, prepare, child


def test_delegates_source_arguments_and_working_directory_to_verified_runtime(environment):
    root, python, prepare, child = environment
    arguments = ["--example", "한글 값", "value with spaces", "literal%value"]
    assert launcher.main(arguments) == 0
    prepare.assert_called_once_with(root / "build/python-sqlite-x64", "x64")
    child.assert_called_once_with([str(python), str(root / "main.py"), *arguments], cwd=root)
    assert python.read_bytes() == b"synthetic executable, never run"


@pytest.mark.parametrize("code", [0, 1, 7])
def test_preserves_application_exit_code(environment, code):
    _root, _python, _prepare, child = environment
    child.return_value = code
    assert launcher.main([]) == code


@pytest.mark.parametrize(
    "error", [RuntimeError("verification failed"), OSError("runtime unavailable")]
)
def test_preparation_failure_never_launches_an_unsafe_fallback(environment, capsys, error):
    _root, _python, prepare, child = environment
    prepare.side_effect = error
    assert launcher.main([]) == 1
    child.assert_not_called()
    assert "Development launch stopped" in capsys.readouterr().err


@pytest.mark.parametrize("report", [{"passed": False}, {"passed": "true"}, {}])
def test_invalid_preparation_result_stops_before_launch(environment, report):
    _root, _python, prepare, child = environment
    prepare.return_value = report
    assert launcher.main([]) == 1
    child.assert_not_called()


def test_missing_verified_python_does_not_fall_back_to_parent_python(environment):
    root, _python, prepare, child = environment
    prepare.return_value = {"passed": True, "python_executable": str(root / "missing.exe")}
    assert launcher.main([]) == 1
    child.assert_not_called()


def test_child_start_failure_is_reported(environment, capsys):
    _root, _python, _prepare, child = environment
    child.side_effect = OSError("cannot start verified executable")
    assert launcher.main([]) == 1
    child.assert_called_once()
    assert "cannot start verified executable" in capsys.readouterr().err


def test_interrupt_does_not_restart_or_use_another_interpreter(environment):
    _root, _python, _prepare, child = environment
    child.side_effect = KeyboardInterrupt
    assert launcher.main([]) == 130
    child.assert_called_once()


def test_run_bat_keeps_version_check_and_uses_safe_development_launcher():
    batch = (Path(__file__).resolve().parents[1] / "run.bat").read_text(
        encoding="utf-8", errors="strict"
    )
    assert '".venv\\Scripts\\python.exe" scripts\\manage_version.py check' in batch
    assert '".venv\\Scripts\\python.exe" scripts\\run_development.py %*' in batch
    assert '".venv\\Scripts\\python.exe" main.py' not in batch
