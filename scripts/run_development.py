# -*- coding: utf-8 -*-
"""Run the current source with the same verified private SQLite runtime as builds.

Never replace DLLs in the developer's Python installation and never fall back to
an unverified runtime when preparation fails. App arguments, working directory,
profile and settings remain those of the ordinary development launch.
"""

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

if __package__:
    from scripts import prepare_sqlite_build_runtime
    from scripts.verify_sqlite_runtime import _host_architecture
else:
    import prepare_sqlite_build_runtime
    from verify_sqlite_runtime import _host_architecture


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        architecture = _host_architecture()
        prepared = prepare_sqlite_build_runtime.prepare(
            ROOT / "build" / f"python-sqlite-{architecture}", architecture
        )
        if prepared.get("passed") is not True:
            raise RuntimeError("Private SQLite runtime verification did not pass")
        python = Path(prepared["python_executable"])
        if not python.is_file():
            raise RuntimeError("Verified development Python is unavailable")
        return subprocess.call([str(python), str(ROOT / "main.py"), *arguments], cwd=ROOT)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        # CLI diagnostics must work even if Qt or application imports are broken.
        print(f"Development launch stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
