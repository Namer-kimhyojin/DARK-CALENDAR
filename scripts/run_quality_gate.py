"""Run the app-wide quality gate for major regression surfaces."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
PYTEST = [PYTHON, "-m", "pytest", "-q"]
CHECKS: list[tuple[str, list[str]]] = [
    ("Compile Python files", [PYTHON, "-m", "compileall", "-q", "."]),
    (
        "Run core management and sync-helper tests",
        [
            *PYTEST,
            "tests/test_schedule_management_scenarios.py",
            "tests/test_work_management_regressions.py",
            "tests/test_routine_advanced_service.py",
            "tests/test_task_validation_pipeline.py",
            "tests/test_review_usecases.py",
            "tests/test_eod_usecases.py",
            "tests/test_directive_management_usecases.py",
            "tests/test_directive_schema_compat.py",
            "tests/test_db_repository_hooks.py",
            "tests/test_gcal_sync_helpers.py",
        ],
    ),
    (
        "Run widget, locale, and menu smoke tests",
        [
            *PYTEST,
            "tests/test_panel_widget_mode_ui.py",
            "tests/test_i18n_runtime_support.py",
            "tests/test_shared_i18n_compat.py",
            "tests/test_domain_i18n_adapter.py",
            "tests/test_background_worker_helpers.py",
            "tests/test_system_menu_layout.py",
        ],
    ),
    (
        "Run Google sync integration and diagnostics smoke tests",
        [
            *PYTEST,
            "tests/test_gcal_sync_integration.py",
            "tests/test_gcal_sync_issues_dialog.py",
        ],
    ),
    (
        "Run focus and overlay smoke tests",
        [
            *PYTEST,
            "tests/test_pomodoro_engine.py",
            "tests/test_pomodoro_settings_dialog.py",
            "tests/test_overlay_countdown.py",
            "tests/test_overlay_stopwatch.py",
        ],
    ),
]


def run_check(label: str, cmd: list[str]) -> None:
    print(f"[quality-gate] {label}: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> int:
    for label, cmd in CHECKS:
        run_check(label, cmd)
    print("[quality-gate] All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
