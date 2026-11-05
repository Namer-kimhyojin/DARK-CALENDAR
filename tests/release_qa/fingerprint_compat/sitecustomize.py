# -*- coding: utf-8 -*-
"""Serialize CPython 3.14 constant slices only in the exact source verifier CLI.

This module is QA startup configuration, never application runtime code. It is
inert for -c/-m, PyInstaller, other scripts and a verifier outside this checkout.
Those processes also lose this QA-only search path before module analysis or
child startup; the parent build shell's environment is never modified.
"""

import json
import os
from pathlib import Path
import sys


def is_verifier_invocation(argv, repository):
    if not argv or not isinstance(argv[0], str) or not argv[0]:
        return False
    try:
        script = Path(argv[0]).resolve()
        expected = (Path(repository) / "scripts/verify_release_runtime.py").resolve()
        return (
            script.name == "verify_release_runtime.py"
            and script.parent == expected.parent
            and script == expected
            and script.is_file()
        )
    except (OSError, ValueError):
        return False


def prune_loader_search_path():
    """Hide only this QA directory from non-verifier processes and their children."""
    directory = Path(__file__).resolve().parent
    # If this file was nevertheless frozen, never remove the application's
    # runtime directory. This operation belongs only to the known QA layout.
    if tuple(path.name for path in (directory.parent.parent, directory.parent, directory)) != (
        "tests",
        "release_qa",
        "fingerprint_compat",
    ):
        return False
    own_path = os.path.normcase(str(directory))

    def owned(entry):
        try:
            return os.path.normcase(str(Path(entry).resolve())) == own_path
        except (OSError, TypeError, ValueError):
            return False

    sys.path[:] = [entry for entry in sys.path if not owned(entry)]
    if "PYTHONPATH" in os.environ:
        remaining = [
            entry for entry in os.environ["PYTHONPATH"].split(os.pathsep) if not owned(entry)
        ]
        if remaining:
            os.environ["PYTHONPATH"] = os.pathsep.join(remaining)
        else:
            del os.environ["PYTHONPATH"]
    return True


def install():
    repository = Path(__file__).resolve().parents[3]
    if not is_verifier_invocation(sys.argv, repository):
        prune_loader_search_path()
        return False
    original = json.JSONEncoder.default
    if getattr(original, "_air_calendar_slice_compat", False):
        return True

    def encode_slice(self, value):
        if isinstance(value, slice):
            # _stable already tags tuples/bytes/code separately. A type tag here
            # preserves slice semantics, including None and negative bounds.
            # JSON re-enters default for nested slices; all other types retain
            # their original failure behavior.
            return ["slice", value.start, value.stop, value.step]
        return original(self, value)

    encode_slice._air_calendar_slice_compat = True
    json.JSONEncoder.default = encode_slice
    return True


ACTIVE = install()
