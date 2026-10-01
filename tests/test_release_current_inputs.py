# -*- coding: utf-8 -*-
"""Uncommitted runtime input must not disappear from corresponding source."""

from pathlib import Path
import subprocess

from scripts.release_compliance import _tracked_files


def test_current_runtime_inputs_include_new_files_without_collecting_private_artifacts(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    tracked = tmp_path / "main.py"
    tracked.write_text("# -*- coding: utf-8 -*-\n", encoding="utf-8", errors="strict")
    subprocess.run(["git", "-C", str(tmp_path), "add", "main.py"], check=True)
    runtime_paths = ["calendar_app/new_feature.py", "Assets/switch.wav", "locales/ko.json"]
    for relative in runtime_paths:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"runtime input")
    private = tmp_path / "artifacts/credentials.json"
    private.parent.mkdir(parents=True)
    private.write_text("{}", encoding="utf-8", errors="strict")
    cached = tmp_path / "calendar_app/__pycache__/temporary.py"
    cached.parent.mkdir()
    cached.write_bytes(b"cache")
    files = _tracked_files(tmp_path)
    assert {Path(relative) for relative in runtime_paths}.issubset(files)
    assert Path("main.py") in files
    assert Path("artifacts/credentials.json") not in files
    assert Path("calendar_app/__pycache__/temporary.py") not in files
