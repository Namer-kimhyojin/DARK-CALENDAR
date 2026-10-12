# -*- coding: utf-8 -*-
"""Curated weather faces: layout, common appearance, shape and illustration.

These immutable recipes describe appearance only.  They never read settings,
fetch a forecast or change the configured city, units or refresh interval.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WeatherDesign:
    design_id: str
    label_key: str
    label_default: str
    category: str
    description_key: str
    description_default: str
    appearance_preset_id: str
    asset_pack_id: str
    template: str
    shape: str = "card"
    font_size: int = 24


WEATHER_DESIGN_CATEGORIES = (
    ("glass", "widget.weather.design_category.glass", "글래스"),
    ("minimal", "widget.weather.design_category.minimal", "미니멀"),
    ("editorial", "widget.weather.design_category.editorial", "에디토리얼"),
    ("playful", "widget.weather.design_category.playful", "팝 · 일러스트"),
    ("neon", "widget.weather.design_category.neon", "네온 · 디지털"),
    ("nature", "widget.weather.design_category.nature", "내추럴"),
)


def _recipe(
    design_id: str,
    label: str,
    category: str,
    description: str,
    appearance: str,
    pack: str,
    template: str,
    shape: str = "card",
    font_size: int = 24,
) -> WeatherDesign:
    return WeatherDesign(
        design_id,
        f"widget.weather.design.{design_id}",
        label,
        category,
        f"widget.weather.design_description.{design_id}",
        description,
        appearance,
        pack,
        template,
        shape,
        font_size,
    )


_DESIGNS = (
    _recipe(
        "soft_cloud",
        "소프트 클라우드",
        "glass",
        "부드러운 입체 구름과 차분한 세로 카드",
        "midnight_glass",
        "air_soft",
        "{icon|size=64}\n{temp|size=36|bold}{unit|size=16}\n{city|size=13}\n{desc|size=11|color=muted}",
    ),
    _recipe(
        "moon_glass",
        "문 글래스",
        "glass",
        "둥근 유리 안에 담은 궤도 일러스트",
        "aurora_violet",
        "orbit_weather",
        "{icon|size=56}\n{temp|size=32|bold}{unit|size=14}\n{city|size=12}",
        "circle",
        20,
    ),
    _recipe(
        "crystal_band",
        "크리스탈 밴드",
        "glass",
        "가는 선 아이콘과 밝은 가로 캡슐",
        "pearl_mist",
        "outline_weather",
        "{icon|size=38}  {temp|size=26|bold}{unit|size=13}\n{city|size=11} · {desc|size=10}",
        "capsule",
        20,
    ),
    _recipe(
        "aurora_panel",
        "오로라 패널",
        "glass",
        "보랏빛 유리에 날씨와 습도를 담은 카드",
        "aurora_violet",
        "neon_weather",
        "{icon|size=56}\n{city|size=12}\n{temp|size=34|bold}{unit|size=15}\n{humidity|size=10}% · {wind|size=10} m/s",
    ),
    _recipe(
        "quiet_mono",
        "콰이어트 모노",
        "minimal",
        "단색 아이콘과 절제된 온도 중심 카드",
        "graphite_minimal",
        "mono_atmosphere",
        "{icon|size=42}\n{temp|size=34|bold}{unit|size=15}\n{city|size=11}",
    ),
    _recipe(
        "clear_line",
        "클리어 라인",
        "minimal",
        "배경 없이 이어지는 한 줄 날씨",
        "pure_type",
        "outline_weather",
        "{icon|size=34}  {temp|size=26|bold}{unit|size=13}  {city|size=13}",
        "capsule",
        20,
    ),
    _recipe(
        "temperature_type",
        "템퍼러처 타입",
        "minimal",
        "큰 숫자로 온도만 선명하게 보여 주는 배치",
        "pure_type",
        "classic",
        "{temp|size=48|bold}{unit|size=18}\n{city|size=13} · {desc|size=11}",
    ),
    _recipe(
        "contrast_card",
        "콘트라스트 카드",
        "minimal",
        "명확한 대비와 큼직한 평면 일러스트",
        "high_contrast",
        "flat_weather",
        "{icon|size=54}  {temp|size=34|bold}{unit|size=16}\n{city|size=13}\n{desc|size=11}",
    ),
    _recipe(
        "paper_weather",
        "페이퍼 웨더",
        "editorial",
        "겹쳐진 종이 아이콘과 세로 포스터",
        "paper_ivory",
        "paper_weather",
        "{align=left}{city|size=12|bold}\n{icon|size=72}\n{temp|size=38|bold}{unit|size=16}\n{desc|size=12}\n{humidity|size=10}% · {wind|size=10} m/s",
        "poster",
        20,
    ),
    _recipe(
        "ivory_ledger",
        "아이보리 레저",
        "editorial",
        "정보를 왼쪽에 정렬한 따뜻한 날씨 기록",
        "paper_ivory",
        "vintage_weather",
        "{align=left}{city|size=13|bold}\n{align=left}{icon|size=42}  {temp|size=30|bold}{unit|size=14}\n{align=left}{desc|size=11}\n{align=left}{humidity|size=10}% · {wind|size=10} m/s",
    ),
    _recipe(
        "gold_observatory",
        "골드 옵저버토리",
        "editorial",
        "금빛 테두리와 클래식 관측 배지",
        "champagne_gold",
        "vintage_weather",
        "{city|size=12}\n{icon|size=48}\n{temp|size=30|bold}{unit|size=14}",
        "circle",
        20,
    ),
    _recipe(
        "amber_bulletin",
        "앰버 불리틴",
        "editorial",
        "호박빛 활자와 픽셀 날씨가 있는 포스터",
        "retro_amber",
        "pixel_weather",
        "{city|size=12|bold}\n{icon|size=64}\n{temp|size=36|bold}{unit|size=15}\n{desc|size=11}",
        "poster",
        20,
    ),
    _recipe(
        "sticker_weather",
        "스티커 웨더",
        "playful",
        "큰 종이 일러스트를 중심에 둔 밝은 카드",
        "pearl_mist",
        "paper_weather",
        "{icon|size=88}\n{temp|size=28|bold}{unit|size=14}\n{city|size=12}",
    ),
    _recipe(
        "candy_cloud",
        "캔디 클라우드",
        "playful",
        "코랄색 원형 배지와 발랄한 평면 구름",
        "sunset_coral",
        "flat_weather",
        "{icon|size=58}\n{temp|size=28|bold}{unit|size=13}\n{city|size=11}",
        "circle",
        20,
    ),
    _recipe(
        "pixel_board",
        "픽셀 보드",
        "playful",
        "게임 화면처럼 간결한 픽셀 정보판",
        "retro_amber",
        "pixel_weather",
        "{icon|size=44}  {temp|size=30|bold}{unit|size=14}\n{city|size=12|bold}\n{desc|size=10}",
    ),
    _recipe(
        "soft_capsule",
        "소프트 캡슐",
        "playful",
        "입체 아이콘과 온도를 나란히 담은 밝은 캡슐",
        "pearl_mist",
        "air_soft",
        "{icon|size=46}  {temp|size=28|bold}{unit|size=14}\n{city|size=12}",
        "capsule",
        20,
    ),
    _recipe(
        "cyan_pulse",
        "시안 펄스",
        "neon",
        "청록 네온 아이콘과 선명한 야간 카드",
        "electric_cyan",
        "neon_weather",
        "{icon|size=64}\n{temp|size=36|bold}{unit|size=16}\n{city|size=12|bold}",
    ),
    _recipe(
        "violet_orbit",
        "바이올렛 오빗",
        "neon",
        "보라색 원형 화면과 궤도 아이콘",
        "aurora_violet",
        "orbit_weather",
        "{city|size=11}\n{icon|size=60}\n{temp|size=32|bold}{unit|size=14}",
        "circle",
        20,
    ),
    _recipe(
        "terminal_station",
        "터미널 스테이션",
        "neon",
        "초록 고정폭 글자로 읽는 작은 기상 관측소",
        "terminal_green",
        "pixel_weather",
        "{align=left}{city|size=12|bold}\n{align=left}{icon|size=36}  {temp|size=30|bold}{unit|size=14}\n{align=left}{desc|size=11}\n{align=left}{humidity|size=10}% · {wind|size=10} m/s",
    ),
    _recipe(
        "night_signal",
        "나이트 시그널",
        "neon",
        "빛나는 날씨 아이콘이 이어지는 어두운 가로 배치",
        "graphite_minimal",
        "neon_weather",
        "{icon|size=40}  {temp|size=28|bold}{unit|size=14}  {city|size=12}\n{desc|size=10}",
        "capsule",
        20,
    ),
    _recipe(
        "sage_card",
        "세이지 카드",
        "nature",
        "숲빛 바탕과 가는 선의 조용한 날씨 카드",
        "forest_moss",
        "outline_weather",
        "{icon|size=56}\n{city|size=12}\n{temp|size=34|bold}{unit|size=15}\n{desc|size=10}",
    ),
    _recipe(
        "coral_coast",
        "코랄 코스트",
        "nature",
        "따뜻한 해안색으로 정돈한 가로 정보 카드",
        "sunset_coral",
        "flat_weather",
        "{align=left}{icon|size=42}  {temp|size=30|bold}{unit|size=14}\n{align=left}{city|size=12|bold}\n{align=left}{desc|size=11}",
    ),
    _recipe(
        "ocean_window",
        "오션 윈도",
        "nature",
        "푸른 유리와 입체 날씨가 있는 세로 창",
        "midnight_glass",
        "air_soft",
        "{city|size=12|bold}\n{icon|size=72}\n{temp|size=36|bold}{unit|size=16}\n{desc|size=11}\n{humidity|size=10}% · {wind|size=10} m/s",
        "poster",
        20,
    ),
    _recipe(
        "desert_note",
        "데저트 노트",
        "nature",
        "빈티지 아이콘을 담은 모래색 날씨 메모",
        "paper_ivory",
        "vintage_weather",
        "{align=left}{city|size=12|bold}\n{icon|size=58}\n{temp|size=32|bold}{unit|size=14}\n{desc|size=11}",
        "poster",
        20,
    ),
)
_BY_ID = {design.design_id: design for design in _DESIGNS}


def weather_designs() -> tuple[WeatherDesign, ...]:
    return _DESIGNS


def weather_design(design_id: object) -> WeatherDesign | None:
    return _BY_ID.get(str(design_id or ""))


__all__ = [
    "WEATHER_DESIGN_CATEGORIES",
    "WeatherDesign",
    "weather_design",
    "weather_designs",
]
