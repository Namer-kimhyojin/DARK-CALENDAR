# -*- coding: utf-8 -*-
"""Stable IDs for three shared collections and ten additional designs per widget."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GraphicCollection:
    collection_id: str
    label: str
    description: str
    appearance: str
    background: str
    foreground: str
    accent: str
    widget_kind: str = ""
    layout: str = "classic"
    slot: int = -1
    weather_scene: str = "air_atmosphere"


COLLECTIONS = (
    GraphicCollection(
        "pure_air",
        "Pure Air",
        "글자 중심의 정돈된 구성과 은은한 그림자",
        "pure_type",
        "#101a28",
        "#f5f7fb",
        "#9ecbff",
    ),
    GraphicCollection(
        "soft_object",
        "Soft Object",
        "밝은 표면과 부드러운 입체 오브젝트",
        "pearl_mist",
        "#eef3f9",
        "#21354b",
        "#327caa",
        weather_scene="soft_object",
    ),
    GraphicCollection(
        "air_instrument",
        "Air Instrument",
        "정밀한 숫자와 눈금, 명확한 상태 표시",
        "graphite_minimal",
        "#17232d",
        "#f3f8ff",
        "#79d6d2",
    ),
)

# Each slot has a distinct composition. Kind-specific IDs keep future changes independent.
_RECIPES = (
    ("flip", "pearl_mist", "#e9edf2", "#243449", "#4779bb", "soft_object", "분할 패널과 큰 숫자"),
    (
        "orbit",
        "graphite_minimal",
        "#112731",
        "#edf9fa",
        "#70d6cc",
        "air_atmosphere",
        "원형 그래픽과 정돈된 정보",
    ),
    (
        "split",
        "pearl_mist",
        "#e9e5f2",
        "#342c4d",
        "#8064a8",
        "soft_object",
        "두 영역으로 나눈 정보 배치",
    ),
    (
        "ribbon",
        "paper_ivory",
        "#f7eddf",
        "#3d3030",
        "#bc604d",
        "editorial_mono",
        "색상 띠와 명확한 제목",
    ),
    (
        "glass",
        "pearl_mist",
        "#dcecf1",
        "#193e4b",
        "#328ba0",
        "soft_object",
        "부드러운 빛과 넓은 여백",
    ),
    (
        "terminal",
        "terminal_green",
        "#101e19",
        "#b9f2d1",
        "#66cb97",
        "air_atmosphere",
        "격자와 선으로 표현한 정보",
    ),
    (
        "editorial",
        "paper_ivory",
        "#f4f0e7",
        "#333731",
        "#b67b42",
        "editorial_mono",
        "큰 타이포그래피와 얇은 구분선",
    ),
    (
        "ticket",
        "pearl_mist",
        "#e5edf5",
        "#20384c",
        "#537fa6",
        "soft_object",
        "티켓 절취선과 보조 정보",
    ),
    (
        "arch",
        "paper_ivory",
        "#eee3d9",
        "#49392f",
        "#a77455",
        "editorial_mono",
        "아치 형태와 따뜻한 표면",
    ),
    (
        "compact",
        "graphite_minimal",
        "#202a3a",
        "#f5f0df",
        "#dbc285",
        "air_atmosphere",
        "가로 정보 띠와 절제한 장식",
    ),
)

_NAMES = {
    "clock": (
        "플립 스튜디오",
        "오비트 다이얼",
        "스플릿 타임",
        "리본 클록",
        "아이스 글라스",
        "터미널 타임",
        "에디토리얼 타임",
        "보딩 타임",
        "선라이즈 아치",
        "포켓 디지털",
    ),
    "date_card": (
        "플립 데이트",
        "데이 오비트",
        "듀얼 데이트",
        "리본 데이",
        "프로스트 데이트",
        "터미널 데이트",
        "데일리 에디션",
        "데이 패스",
        "선데이 아치",
        "포켓 데이트",
    ),
    "dday": (
        "플립 카운트",
        "마일스톤 오비트",
        "듀얼 마일스톤",
        "셀레브레이션 리본",
        "메모리 글라스",
        "미션 카운트",
        "마일스톤 에디션",
        "트래블 패스",
        "메모리 아치",
        "포켓 마일스톤",
    ),
    "stopwatch": (
        "플립 크로노",
        "레이싱 오비트",
        "스플릿 크로노",
        "스타트 리본",
        "프로스트 크로노",
        "터미널 크로노",
        "크로노 에디션",
        "랩 패스",
        "트랙 아치",
        "포켓 크로노",
    ),
    "countdown": (
        "플립 타이머",
        "프로그레스 오비트",
        "듀얼 타이머",
        "데드라인 리본",
        "포커스 글라스",
        "미션 타이머",
        "타이머 에디션",
        "타임 패스",
        "포커스 아치",
        "포켓 타이머",
    ),
    "text": (
        "인덱스 노트",
        "오비트 노트",
        "스플릿 메모",
        "리본 메모",
        "프로스트 노트",
        "터미널 메모",
        "에디터 노트",
        "메모 패스",
        "아치 노트",
        "포켓 메모",
    ),
    "weather": (
        "웨더 플립",
        "클라이밋 오비트",
        "스플릿 포캐스트",
        "모닝 리본",
        "클라우드 글라스",
        "웨더 터미널",
        "포캐스트 에디션",
        "웨더 패스",
        "스카이 아치",
        "포켓 포캐스트",
    ),
    "launcher_deck": (
        "폴라 키캡",
        "딥 씨 키캡",
        "라벤더 키캡",
        "코랄 키캡",
        "글레이셔 키캡",
        "포레스트 키캡",
        "에디터 키캡",
        "블루프린트 키캡",
        "테라코타 키캡",
        "미드나이트 골드 키캡",
    ),
}

DESIGNS_BY_KIND = {
    kind: tuple(
        GraphicCollection(
            f"{kind}_{layout}",
            label,
            description,
            appearance,
            bg,
            fg,
            accent,
            widget_kind=kind,
            layout=layout,
            slot=slot,
            weather_scene=scene,
        )
        for slot, (label, (layout, appearance, bg, fg, accent, scene, description)) in enumerate(
            zip(names, _RECIPES, strict=True)
        )
    )
    for kind, names in _NAMES.items()
}
_BY_ID = {
    item.collection_id: item
    for item in (*COLLECTIONS, *(item for designs in DESIGNS_BY_KIND.values() for item in designs))
}


def graphic_collection(value: object) -> GraphicCollection | None:
    return _BY_ID.get(str(value or ""))


def graphic_collections(kind: str) -> tuple[GraphicCollection, ...]:
    return COLLECTIONS + DESIGNS_BY_KIND.get(kind, ())


def collection_for_kind(value: object, kind: str) -> GraphicCollection | None:
    design = graphic_collection(value)
    if design and design.widget_kind and design.widget_kind != kind:
        return DESIGNS_BY_KIND.get(kind, ())[design.slot] if kind in DESIGNS_BY_KIND else None
    return design
