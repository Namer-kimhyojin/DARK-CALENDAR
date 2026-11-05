# -*- coding: utf-8 -*-
"""Compose reviewed QA adapters around the unchanged original six native gates."""

from pathlib import Path
import sys


def main(argv=None):
    directory = Path(__file__).resolve().parent
    sys.path.insert(0, str(directory.parents[1]))
    sys.path.insert(0, str(directory))
    from native_capture_diagnostics import install_diagnostics
    from native_modal_owner_adapter import install_owner_adapter
    from native_release_smoke_adapter import install_adapter
    from native_runner_surface_adapter import install_runner_surface_adapter
    from scripts import native_release_smoke

    with (
        install_adapter(native_release_smoke),
        install_owner_adapter(native_release_smoke),
        install_runner_surface_adapter(native_release_smoke),
        install_diagnostics(native_release_smoke),
    ):
        return native_release_smoke.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
