"""Run encoding guard checks used by both local and CI workflows."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
CHECKS: list[tuple[str, list[str]]] = [
    ("Compile Python files", [PYTHON, "-m", "compileall", "-q", "."]),
    (
        "Run encoding policy tests",
        [
            PYTHON,
            "-m",
            "pytest",
            "-q",
            "tests/test_encoding_policy.py",
            "tests/test_encoding_utils.py",
        ],
    ),
]


def run_check(label: str, cmd: list[str]) -> None:
    print(f"[encoding-guard] {label}: {' '.join(cmd)}")
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
    print("[encoding-guard] All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
