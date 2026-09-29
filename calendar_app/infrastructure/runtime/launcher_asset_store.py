# -*- coding: utf-8 -*-
"""Durable user asset storage for launcher-deck keycaps."""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil

from calendar_app.app_paths import get_app_data_dir

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".svg"}
_SOUND_SUFFIXES = {".wav"}
_MAX_ASSET_BYTES = 25 * 1024 * 1024


def import_launcher_asset(source: str, kind: str, *, root: Path | None = None) -> str:
    """Copy a validated user asset into app-managed storage and return its path."""
    source_path = Path(str(source)).expanduser()
    allowed = _SOUND_SUFFIXES if kind == "sound" else _IMAGE_SUFFIXES
    if not source_path.is_file() or source_path.suffix.lower() not in allowed:
        return ""
    try:
        if source_path.stat().st_size > _MAX_ASSET_BYTES:
            return ""
        digest = hashlib.sha256()
        with source_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        target_dir = (root or get_app_data_dir()) / "launcher_assets" / kind
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{digest.hexdigest()[:20]}{source_path.suffix.lower()}"
        if not target.exists():
            shutil.copy2(source_path, target)
        return str(target)
    except OSError:
        return ""


__all__ = ["import_launcher_asset"]
