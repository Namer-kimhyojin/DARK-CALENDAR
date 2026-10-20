# -*- coding: utf-8 -*-
"""Decode actual MSIX names while containing isolated baseline extraction."""

from pathlib import PurePosixPath
import zipfile

import pytest
from scripts.prepare_native_smoke_baseline import decoded_member, extract_msix


@pytest.mark.parametrize(
    "name", ["../escape", "%2e%2e/escape", "/root", "C:/escape", "ok/%2e%2e/escape", "%00bad"]
)
def test_rejects_paths_outside_baseline(name):
    with pytest.raises(RuntimeError):
        decoded_member(name)


def test_decodes_msix_spaces_and_unicode_once():
    assert decoded_member("_internal/Air%20Calendar/%ED%95%9C%EA%B8%80.txt") == PurePosixPath(
        "_internal/Air Calendar/한글.txt"
    )
    assert decoded_member("literal%2520name.txt") == PurePosixPath("literal%20name.txt")


def test_extracts_decoded_native_payload_and_returns_hashes(tmp_path):
    archive = tmp_path / "test.msix"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("DarkCalendar.exe", b"native")
        package.writestr("_internal/Air%20Calendar.txt", b"data")
    output = tmp_path / "payload"
    output.mkdir()
    hashes = extract_msix(archive, output)
    assert (output / "_internal/Air Calendar.txt").read_bytes() == b"data"
    assert set(hashes) == {"DarkCalendar.exe", "_internal/Air Calendar.txt"}


def test_rejects_case_insensitive_duplicate_decoded_member(tmp_path):
    archive = tmp_path / "test.msix"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("Same%20Name.txt", b"one")
        package.writestr("same name.TXT", b"two")
    output = tmp_path / "payload"
    output.mkdir()
    with pytest.raises(RuntimeError, match="Duplicate"):
        extract_msix(archive, output)
