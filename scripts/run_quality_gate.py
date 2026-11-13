# -*- coding: utf-8 -*-
"""Run the app-wide quality gate for major regression surfaces."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
PYTEST = [PYTHON, "-m", "pytest", "-q"]
SOURCE_PATHS = [path.name for path in sorted(ROOT.glob("*.py"))] + [
    "calendar_app",
    "scripts",
    "tests",
]
CHECKS: list[tuple[str, list[str]]] = [
    ("Compile Python files", [PYTHON, "-m", "compileall", "-q", *SOURCE_PATHS]),
    (
        "Check product version and recorded inputs",
        [PYTHON, "scripts/manage_version.py", "scan", "--strict"],
    ),
    (
        "Run release version contracts",
        [
            *PYTEST,
            "tests/test_version_management.py",
            "tests/test_build_version_sync_lock_stability.py",
            "tests/test_build_pipeline_contracts.py",
            "tests/test_release_compliance.py",
            "tests/test_release_compliance_paths.py",
        ],
    ),
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
            "tests/test_gcal_sync_helpers.py",
        ],
    ),
    (
        "Run widget, locale, and menu smoke tests",
        [
            *PYTEST,
            "tests/test_i18n_runtime_support.py",
            "tests/test_domain_i18n_adapter.py",
            "tests/test_background_worker_helpers.py",
            "tests/test_system_menu_layout.py",
            "tests/test_dialog_lifetime_gc.py",
            "tests/test_qt_destroyed_hooks.py",
        ],
    ),
    (
        "Run i18n audit ratchet, locale contracts and Korean-leak smoke tests",
        [
            *PYTEST,
            "tests/test_i18n_audit.py",
            "tests/test_i18n_sync.py",
            "tests/test_calendar_sync_locales.py",
            "tests/test_i18n_language_regressions.py",
            "tests/test_i18n_leak_smoke.py",
            "tests/test_i18n_runtime_fixes.py",
            "tests/test_locale_weekday_sources.py",
            "tests/test_i18n_calendar_names_and_keys.py",
            "tests/test_i18n_label_widths.py",
            "tests/test_i18n_c_shell.py",
            "tests/test_i18n_c_token_editor.py",
            "tests/test_i18n_c_sync.py",
            "tests/test_i18n_c_small_ui.py",
            "tests/test_i18n_c_misc.py",
            "tests/test_i18n_count_placeholders.py",
            "tests/test_help_menu_paths.py",
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


def gate_environment() -> dict[str, str]:
    """Run Qt tests offscreen, as CI does, so no real window opens on a desktop."""
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    if sys.platform == "win32" and fonts.is_dir():
        env.setdefault("QT_QPA_FONTDIR", str(fonts))
    return env


def run_check(label: str, cmd: list[str]) -> None:
    print(f"[quality-gate] {label}: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        env=gate_environment(),
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
