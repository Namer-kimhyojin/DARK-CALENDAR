import argparse
import os
from pathlib import Path
import shutil
import subprocess

# Paths
CWD = Path(__file__).parent.absolute()
VENV_PYTHON = CWD / ".venv" / "Scripts" / "python.exe"
PYINSTALLER = CWD / ".venv" / "Scripts" / "pyinstaller.exe"
DIST_DIR = CWD / "dist" / "DarkCalendar"
MSIX_OUTPUT = CWD / "DarkCalendar.msix"

# SDK Paths search (for makeappx.exe)
MAKEAPPX_PATH = None
PROGRAM_FILES_X86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")  # noqa: SIM112
WINDOWS_KITS_DIR = Path(PROGRAM_FILES_X86) / "Windows Kits" / "10" / "bin"

if WINDOWS_KITS_DIR.exists():
    for arch in ["x64", "x86", "arm64"]:
        for match in WINDOWS_KITS_DIR.rglob(f"*/{arch}/makeappx.exe"):
            MAKEAPPX_PATH = str(match)
            break
        if MAKEAPPX_PATH:
            break


def run_command(cmd, shell=True):
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=shell, cwd=CWD)
    if result.returncode != 0:
        raise Exception(f"Command failed with code {result.returncode}")


def reset_release_state(purge_local_data=False, dry_run=False):
    script = CWD / "scripts" / "reset_release_state.py"
    if not script.exists():
        raise Exception(f"reset script not found: {script}")

    cmd = f'"{VENV_PYTHON}" "{script}" --project-dir "{CWD}"'
    if purge_local_data:
        cmd += " --purge-local-data"
    if dry_run:
        cmd += " --dry-run"
    run_command(cmd)


def build(reset_state=False, purge_local_data=False, dry_run_reset=False):
    if reset_state:
        reset_release_state(purge_local_data=purge_local_data, dry_run=dry_run_reset)

    # 1. Clear previous dist/build
    if (CWD / "dist").exists():
        shutil.rmtree(CWD / "dist")
    if (CWD / "build").exists():
        shutil.rmtree(CWD / "build")

    # 2. Run PyInstaller
    run_command(f'"{PYINSTALLER}" --noconfirm DarkCalendar.spec')

    # 3. Verify manifest
    manifest = CWD / "AppxManifest.xml"
    if not manifest.exists():
        raise Exception("AppxManifest.xml missing!")

    # Copy manifest and Assets to dist folder for packaging
    shutil.copy(manifest, DIST_DIR / "AppxManifest.xml")
    if (DIST_DIR / "Assets").exists():
        shutil.rmtree(DIST_DIR / "Assets")
    shutil.copytree(CWD / "Assets", DIST_DIR / "Assets")

    # 4. Create MSIX
    if MAKEAPPX_PATH:
        print(f"Packaging with: {MAKEAPPX_PATH}")
        if MSIX_OUTPUT.exists():
            MSIX_OUTPUT.unlink()
        run_command(f'"{MAKEAPPX_PATH}" pack /d "{DIST_DIR}" /p "{MSIX_OUTPUT}" /v')
        print(f"SUCCESS: MSIX created at {MSIX_OUTPUT}")
    else:
        print("WARNING: makeappx.exe not found. Build is complete in 'dist/DarkCalendar'.")
        print("Please use the MSIX Packaging Tool to package the 'dist/DarkCalendar' directory.")


def parse_args():
    parser = argparse.ArgumentParser(description="Build DarkCalendar and optionally package MSIX.")
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help="Reset project/runtime settings before build for clean release defaults.",
    )
    parser.add_argument(
        "--purge-local-data",
        action="store_true",
        help="With --reset-state, also delete LOCALAPPDATA runtime folders.",
    )
    parser.add_argument(
        "--dry-run-reset",
        action="store_true",
        help="With --reset-state, print reset actions without applying them.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        build(
            reset_state=args.reset_state,
            purge_local_data=args.purge_local_data,
            dry_run_reset=args.dry_run_reset,
        )
    except Exception as e:
        print(f"BUILD FAILED: {e}")
