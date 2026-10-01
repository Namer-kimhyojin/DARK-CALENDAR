# -*- coding: utf-8 -*-
"""Bundled insert-pattern decals (white line art) for KeyDeck keycaps."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from calendar_app.app_paths import get_resource_path


@dataclass(frozen=True, slots=True)
class KeycapAsset:
    asset_id: str
    label_key: str
    label_default: str
    filename: str

    def path(self) -> Path:
        return Path(get_resource_path(f"Assets/keycaps/{self.filename}"))


KEYCAP_ASSETS = (
    KeycapAsset("none", "widget.launcher.asset.none", "없음", ""),
    KeycapAsset("spark", "widget.launcher.asset.spark", "스파크", "spark.png"),
    KeycapAsset("orbit", "widget.launcher.asset.orbit", "오비트", "orbit.png"),
    KeycapAsset("grid", "widget.launcher.asset.grid", "그리드", "grid.png"),
    KeycapAsset("waves", "widget.launcher.asset.waves", "웨이브", "waves.png"),
    KeycapAsset("circuit", "widget.launcher.asset.circuit", "서킷", "circuit.png"),
    KeycapAsset("blossom", "widget.launcher.asset.blossom", "블라썸", "blossom.png"),
    KeycapAsset("speed", "widget.launcher.asset.speed", "스피드 라인", "speed.png"),
    KeycapAsset("pixels", "widget.launcher.asset.pixels", "픽셀 크로스", "pixels.png"),
    KeycapAsset(
        "constellation",
        "widget.launcher.asset.constellation",
        "별자리",
        "constellation.png",
    ),
    KeycapAsset("rings", "widget.launcher.asset.rings", "리듬 링", "rings.png"),
    KeycapAsset("hexmesh", "widget.launcher.asset.hexmesh", "헥사 메시", "hexmesh.png"),
    KeycapAsset("chevrons", "widget.launcher.asset.chevrons", "셰브론", "chevrons.png"),
    KeycapAsset("equalizer", "widget.launcher.asset.equalizer", "이퀄라이저", "equalizer.png"),
    KeycapAsset("scanlines", "widget.launcher.asset.scanlines", "스캔 라인", "scanlines.png"),
    KeycapAsset("prism", "widget.launcher.asset.prism", "프리즘", "prism.png"),
    KeycapAsset("target", "widget.launcher.asset.target", "타깃", "target.png"),
    KeycapAsset("confetti", "widget.launcher.asset.confetti", "컨페티", "confetti.png"),
    KeycapAsset("rain", "widget.launcher.asset.rain", "디지털 레인", "rain.png"),
    KeycapAsset("sunburst", "widget.launcher.asset.sunburst", "선버스트", "sunburst.png"),
    KeycapAsset("portal", "widget.launcher.asset.portal", "포털", "portal.png"),
    KeycapAsset("blocks", "widget.launcher.asset.blocks", "모듈 블록", "blocks.png"),
)
_ASSET_BY_ID = {asset.asset_id: asset for asset in KEYCAP_ASSETS}


def keycap_asset(asset_id: object) -> KeycapAsset:
    return _ASSET_BY_ID.get(str(asset_id or "none"), _ASSET_BY_ID["none"])


def keycap_asset_ids() -> set[str]:
    return set(_ASSET_BY_ID)


__all__ = [
    "KEYCAP_ASSETS",
    "KeycapAsset",
    "keycap_asset",
    "keycap_asset_ids",
]
