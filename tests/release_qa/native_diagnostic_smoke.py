# -*- coding: utf-8 -*-
"""Run all original six native cycles with runtime adaptation and extra evidence."""

from pathlib import Path
import sys


def main(argv=None):
    directory = Path(__file__).resolve().parent
    sys.path.insert(0, str(directory.parents[1]))
    sys.path.insert(0, str(directory))
    from native_capture_diagnostics import install_diagnostics
    from native_release_smoke_adapter import install_adapter
    from scripts import native_release_smoke

    with install_adapter(native_release_smoke), install_diagnostics(native_release_smoke):
        return native_release_smoke.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
