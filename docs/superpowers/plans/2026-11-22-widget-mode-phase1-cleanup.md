# 위젯 전용 모드 1단계(정리) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 위젯 전용 모드의 배치 11종을 4종으로, 스킨 16종을 표면 모양 4종으로 줄입니다. 구성 편집기·위젯 스타일 만들기·투명도 슬라이더·보기 버튼·옛 팔레트 명령을 없애고, 기존 사용자 설정은 자동으로 옮깁니다.

**Architecture:** 순수 모듈 세 개를 새로 만듭니다.
- `widget_mode_display.py`: 배치별 표시 옵션.
- `widget_mode_surfaces.py`: 표면 모양 카탈로그.
- `widget_mode_migration.py`: 저장값 이관.

위젯 창은 배치 정의의 고정 필드 대신 배치별 표시 옵션을 읽습니다. 이관은 위젯 창을 만들기 직전과 작업 공간을 복원한 직후에 실행하며, 몇 번을 돌려도 결과가 같습니다. 옛 키는 지우지 않습니다.

**Tech Stack:** Python 3.14, PyQt6 6.12, pytest(offscreen), QSettings(앱 코드에서는 레지스트리, 테스트에서는 메모리 대체물).

**Spec:** [docs/widget_only_mode_improvement_plan_20261122.md](../../widget_only_mode_improvement_plan_20261122.md) — 4.1절, 5절, 6절 1단계 행, 7절.

## Global Constraints

- 모든 `.py` 첫 줄은 `# -*- coding: utf-8 -*-`. 텍스트 입출력에는 `encoding="utf-8"`과 `errors=`를 함께 씁니다(내부 파일 `strict`, 외부 입력 `replace`, `ignore` 금지).
- 기존 키는 지우지 않습니다. 예외는 `widget_mode_layout` 하나로, 4종 ID로 다시 쓰고 옛 값은 `widget_mode_layout_legacy`에 남깁니다.
- 가독성 하한(`harden_widget_readability`: 배경 알파 242 이상, 대비 7 / 5.5 / 4.5:1)과 메인 테마 연동(`_main_theme_linked="true"`)은 바꾸지 않습니다.
- 사용자 문구는 모두 `t(key, 한국어 fallback)`로 씁니다. 새 키는 `locales/ko.json`과 `locales/en.json`에 추가하고, 다른 17개 로케일은 Task 9에서 영어 값으로 채웁니다(번역 완료로 기록하지 않음).
- 아이콘은 `calendar_app/shared/icon_map.py`의 `ICON` 상수만 씁니다. 이모지 금지.
- 테스트 실행(bash): `QT_QPA_PLATFORM=offscreen QT_QPA_FONTDIR="C:/Windows/Fonts" .venv/Scripts/python.exe -m pytest -o addopts="" -q <대상>`. 아래에서는 이 명령을 `PYTEST <대상>`으로 적습니다.
- 테스트에서 `QSettings("kimhyojin", "Dark Calendar")`를 만들지 않습니다. 실제 레지스트리에 씁니다. 순수 함수 테스트는 `value(key, default=None, type=None)`·`setValue(key, value)`만 있는 메모리 Settings를 씁니다(`tests/test_widget_mode_ux.py:21-29`와 같은 모양).
- 커밋: 다른 세션의 미커밋 변경이 같은 체크아웃에 있습니다. 반드시 경로를 지정해 커밋합니다. 예: `PATH="$PWD/.venv/Scripts:$PATH" git commit -m "..." -- <파일들>`. pre-commit의 ruff가 파일을 고치고 커밋을 중단하면 다시 add한 뒤 커밋합니다. 커밋 메시지 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`를 붙입니다.
- 4종 배치 ID와 표시 이름: `stacked` 세로형, `dashboard` 좌우형, `work_board` 보드형, `minimal` 목록형.
- 표면 모양 키와 이름: `card` 카드(기본), `line` 구분선, `outline` 테두리, `compact` 촘촘.

## Review Focus

테스트가 직접 다루지 않지만 사용자에게 가장 먼저 문제가 될 입력입니다. 각 줄의 고정 테스트는 담당 Task에 넣었습니다.

1. 레지스트리에 이상한 값이 남은 사용자: 없는 배치 ID, 대문자·공백이 섞인 ID, 빈 문자열. 기본 `stacked`로 열리고 예외가 없어야 합니다 → Task 2 `test_unknown_and_messy_layout_values`.
2. 이관 뒤 이전 버전을 다시 설치한 사용자: 옛 키(`widget_mode_skin`, `widget_mode_panel_theme`, 투명도)가 그대로 남아 있어야 합니다 → Task 2 `test_legacy_keys_are_left_untouched`.
3. 작업 공간을 2026-11-22 이전 스냅샷으로 복원: 스냅샷에 옛 배치 ID만 있어도 창이 4종 중 하나로 열리고, 표시 옵션이 옛 화면대로 채워져야 합니다 → Task 6 `test_restoring_old_snapshot_migrates_layout`.
4. `widget_mode_styles.json`이 손상됐거나 없는데 `user_layout_*`이 선택된 사용자: 기본 `stacked`로 열리고 파일은 그대로여야 합니다 → Task 2 `test_user_layout_with_missing_style_file`.
5. 꾸미기에서 표시 옵션을 바꾼 뒤 취소: 저장되지 않아야 합니다 → Task 7 `test_display_options_cancel_keeps_settings`.

---

### Task 1: 배치별 표시 옵션과 표면 모양 모듈

**Files:**
- Create: `calendar_app/presentation/widgets/widget_mode_display.py`
- Create: `calendar_app/presentation/widgets/widget_mode_surfaces.py`
- Test: `tests/test_widget_mode_display.py`, `tests/test_widget_mode_surfaces.py`

**Interfaces:**
- Produces (`widget_mode_display.py`):
  - `CALENDAR_STYLE_PREFIX = "widget_mode_calendar_style_"`, `SHOW_OVERVIEW_PREFIX = "widget_mode_show_overview_"`, `SEARCH_PINNED_PREFIX = "widget_mode_search_pinned_"`
  - `@dataclass(frozen=True) class LayoutDisplay: calendar_style: str; show_overview: bool; search_pinned: bool`. `calendar_style`은 `"week"` 또는 `"month"`입니다.
  - `display_key(prefix: str, layout_id: str) -> str`
  - `default_layout_display(layout: WidgetModeLayout) -> LayoutDisplay`: `calendar_mode`가 `"auto"`면 `dashboard`·`magazine`은 `"month"`, 나머지는 `"week"`입니다. `show_overview`·`searchable` 필드를 그대로 씁니다.
  - `read_layout_display(settings, layout: WidgetModeLayout) -> LayoutDisplay`: 키가 없거나 값이 이상하면 기본값을 씁니다. bool은 `"true"`/`True`만 참입니다.
  - `write_layout_display(settings, layout_id: str, display: LayoutDisplay) -> None`
- Produces (`widget_mode_surfaces.py`):
  - `SURFACE_SETTING_KEY = "widget_mode_surface"`, `DEFAULT_SURFACE = "card"`
  - `@dataclass(frozen=True) class WidgetModeSurface: key: str; label_key: str; label_default: str; radius: int; item_radius: int; item_background: str; item_border: str`. `item_background`은 `"card"` 또는 `"transparent"`, `item_border`는 `"full"` 또는 `"bottom"`입니다.
  - `widget_mode_surfaces() -> tuple[WidgetModeSurface, ...]`: 순서는 card, line, outline, compact.
  - `get_widget_mode_surface(key: object) -> WidgetModeSurface`: 모르는 키는 card입니다.
  - `read_widget_mode_surface(settings) -> str`, `write_widget_mode_surface(settings, key: object) -> str`

표면 값(현재 `widget_workspace_styles.py:25-38`과 같은 결과):

| key | label_key | label_default | radius | item_radius | item_background | item_border |
|---|---|---|---|---|---|---|
| card | `widget_mode.surface_card` | 카드 | 10 | 8 | card | full |
| line | `widget_mode.surface_line` | 구분선 | 6 | 2 | transparent | bottom |
| outline | `widget_mode.surface_outline` | 테두리 | 10 | 6 | transparent | full |
| compact | `widget_mode.surface_compact` | 촘촘 | 8 | 4 | card | full |

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_widget_mode_display.py
from calendar_app.presentation.widgets.widget_mode_display import (
    LayoutDisplay, default_layout_display, display_key, read_layout_display, write_layout_display,
)
from calendar_app.presentation.widgets.widget_mode_skins import get_widget_mode_layout

class Settings:  # value/setValue only
    ...

def test_defaults_follow_layout_definition():
    assert default_layout_display(get_widget_mode_layout("stacked")) == LayoutDisplay("week", False, False)
    assert default_layout_display(get_widget_mode_layout("dashboard")) == LayoutDisplay("month", False, False)

def test_round_trip_is_scoped_per_layout():
    s = Settings()
    write_layout_display(s, "stacked", LayoutDisplay("month", True, True))
    assert read_layout_display(s, get_widget_mode_layout("stacked")) == LayoutDisplay("month", True, True)
    assert read_layout_display(s, get_widget_mode_layout("dashboard")) == LayoutDisplay("month", False, False)
    assert display_key("widget_mode_calendar_style_", "stacked") == "widget_mode_calendar_style_stacked"

def test_bad_values_fall_back_to_defaults():
    s = Settings(); s.setValue("widget_mode_calendar_style_stacked", "yearly")
    s.setValue("widget_mode_show_overview_stacked", "maybe")
    assert read_layout_display(s, get_widget_mode_layout("stacked")) == LayoutDisplay("week", False, False)
```

```python
# tests/test_widget_mode_surfaces.py
def test_catalog_order_and_values():
    keys = [s.key for s in widget_mode_surfaces()]
    assert keys == ["card", "line", "outline", "compact"]
    line = get_widget_mode_surface("line")
    assert (line.radius, line.item_radius, line.item_background, line.item_border) == (6, 2, "transparent", "bottom")

def test_unknown_surface_reads_as_card():
    s = Settings(); s.setValue("widget_mode_surface", "glass")
    assert read_widget_mode_surface(s) == "card"
    assert write_widget_mode_surface(s, "OUTLINE ") == "outline"
```

- [ ] **Step 2: 실패 확인** — `PYTEST tests/test_widget_mode_display.py tests/test_widget_mode_surfaces.py` → `ModuleNotFoundError`
- [ ] **Step 3: 두 모듈을 위 Interfaces대로 구현**
- [ ] **Step 4: 통과 확인** — 같은 명령 → 모두 PASS
- [ ] **Step 5: 커밋** — `feat(widget-mode): add per-layout display options and surface catalog`

---

### Task 2: 저장값 이관 함수

**Files:**
- Create: `calendar_app/presentation/widgets/widget_mode_migration.py`
- Test: `tests/test_widget_mode_migration.py`

**Interfaces:**
- Consumes: Task 1의 `display_key`, `LayoutDisplay`, `write_layout_display`, `SURFACE_SETTING_KEY`. 그리고 기존 API:
  - `widget_mode_visibility.read_widget_calendar_visibility(settings, layout_id)`, `calendar_visibility_key(layout_id)`
  - `widget_mode_geometry.geometry_key(layout_id)`(`"unified_widget_geometry_<id>"`)
  - `widget_layout_presets.read_layout_presets / create_layout_preset / write_layout_presets`
  - `widget_free_layout.FREE_LAYOUT_SETTING_KEY`, `validate_free_layout`
- Produces:
  - `KEPT_LAYOUT_IDS = ("stacked", "dashboard", "work_board", "minimal")`
  - `RETIRED_LAYOUTS: dict[str, tuple[str, LayoutDisplay]]`(스펙 4.1절 표 그대로)
  - `SKIN_SURFACES: dict[str, str]`, `LEGACY_SKIN_LAYOUTS: dict[str, str]`
  - `LAYOUT_LEGACY_KEY = "widget_mode_layout_legacy"`
  - `migrate_widget_mode_settings(settings, *, user_styles_path: Path | None = None, preserved_name: str = "이전 자유 구성") -> bool`: 무엇이든 썼으면 True입니다.
  - `classify_user_layout(raw: Mapping) -> tuple[str, LayoutDisplay]`

이관표(스펙 4.1절):

| old | new | calendar | overview | search |
|---|---|---|---|---|
| day_brief | stacked | week | True | True |
| month_focus | stacked | month | False | True |
| week_navigator | stacked | week | False | True |
| agenda_first | stacked | week | False | False |
| side_planner | dashboard | month | True | True |
| magazine | dashboard | month | False | False |
| focus_dock | minimal | week | False | True |

`SKIN_SURFACES`:
- `card`: classic_light, classic_dark, midnight_blue, forest_mist, sunset_glow, lavender_dream, studio_porcelain, studio_sage, studio_lilac, studio_midnight, studio_amethyst
- `line`: studio_linen, studio_forest
- `outline`: studio_arctic, studio_contrast
- `compact`: studio_graphite

`LEGACY_SKIN_LAYOUTS = {"midnight_blue": "dashboard", "forest_mist": "agenda_first", "sunset_glow": "magazine", "lavender_dream": "minimal"}`

**처리 순서** (`migrate_widget_mode_settings`):
1. 배치 ID를 정합니다. `widget_mode_layout`을 strip·lower합니다. 비어 있으면 `widget_mode_skin`으로 `LEGACY_SKIN_LAYOUTS`를 찾고, 없으면 `stacked`입니다.
2. `user_layout_*`이면 `user_styles_path`(기본값 `widget_mode_skins.USER_STYLES_PATH`)에서 해당 원본을 찾아 `classify_user_layout`에 넘깁니다. 파일을 못 읽거나 항목이 없으면 `stacked`, 기본 표시입니다.
3. 옛 ID(`RETIRED_LAYOUTS` 또는 `user_layout_*`)면 다음을 합니다.
   - `widget_mode_layout_legacy`에 옛 값을 씁니다.
   - 새 ID의 표시 키를 씁니다(이미 있으면 덮어쓰지 않음).
   - `unified_widget_geometry_<old>`, `unified_widget_geometry_<old>_calendar_hidden`, `unified_widget_size_<old>`, `unified_widget_size_<old>_calendar_hidden` 값이 있으면 새 ID 키로 복사합니다(덮어씀, 사용 중이던 배치가 우선).
   - `calendar_visibility_key(new)`에 `read_widget_calendar_visibility(settings, old)`를 씁니다.
   - `widget_mode_layout`을 새 ID로 씁니다.
   - 모르는 ID면 `stacked`로 씁니다(legacy 키는 쓰지 않음).
4. `KEPT_LAYOUT_IDS` 네 개 각각에 대해 표시 키가 없으면 `default_layout_display`로 채웁니다.
5. `widget_mode_surface`가 비어 있으면 `SKIN_SURFACES.get(skin_id, "card")`를 씁니다. `skin_id`가 없으면 `widget_mode_panel_theme`과 무관하게 card입니다.
6. `widget_mode_free_layout`이 유효한 자유 구성이고, 저장된 내 배치 중 `layout`이 같은 항목이 없으면 `preserved_name`으로 내 배치를 추가합니다. 프리셋이 100개로 꽉 찼으면 건너뛰고 경고 로그를 남깁니다. `widget_mode_layout_mode`는 건드리지 않습니다.

`classify_user_layout`: `presentation == "board"`면 work_board입니다. 그 외에는 placements에 `calendar`가 없으면 minimal, 어떤 구역이든 column > 0이면 dashboard, 나머지는 stacked입니다. 표시값은 원본의 `calendar_mode`·`show_overview`·`searchable`을 따르고, `auto`는 새 ID의 기본값입니다.

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/test_widget_mode_migration.py`)

```python
@pytest.mark.parametrize("old,new,display", [
    ("day_brief", "stacked", LayoutDisplay("week", True, True)),
    ("month_focus", "stacked", LayoutDisplay("month", False, True)),
    ("week_navigator", "stacked", LayoutDisplay("week", False, True)),
    ("agenda_first", "stacked", LayoutDisplay("week", False, False)),
    ("side_planner", "dashboard", LayoutDisplay("month", True, True)),
    ("magazine", "dashboard", LayoutDisplay("month", False, False)),
    ("focus_dock", "minimal", LayoutDisplay("week", False, True)),
])
def test_retired_layout_maps_with_display(old, new, display):
    s = Settings(); s.setValue("widget_mode_layout", old)
    assert migrate_widget_mode_settings(s, user_styles_path=MISSING) is True
    assert s.value("widget_mode_layout") == new
    assert s.value("widget_mode_layout_legacy") == old
    assert read_layout_display(s, get_widget_mode_layout(new)) == display

def test_kept_layouts_get_defaults_without_rewrite():
    s = Settings(); s.setValue("widget_mode_layout", "dashboard")
    migrate_widget_mode_settings(s, user_styles_path=MISSING)
    assert s.value("widget_mode_layout") == "dashboard" and s.value("widget_mode_layout_legacy") is None
    assert s.value("widget_mode_calendar_style_dashboard") == "month"
    assert s.value("widget_mode_show_overview_work_board") in (True, "true")

def test_geometry_size_and_calendar_visibility_follow_active_layout():
    s = Settings(); s.setValue("widget_mode_layout", "month_focus")
    s.setValue("unified_widget_geometry_month_focus", "G1")
    s.setValue("unified_widget_size_month_focus_calendar_hidden", "S1")
    s.setValue("unified_widget_geometry_stacked", "OLD")
    migrate_widget_mode_settings(s, user_styles_path=MISSING)
    assert s.value("unified_widget_geometry_stacked") == "G1"
    assert s.value("unified_widget_size_stacked_calendar_hidden") == "S1"
    assert str(s.value("widget_mode_calendar_visible_stacked")).lower() == "true"  # month_focus defaulted visible

def test_existing_display_keys_are_not_overwritten():
    s = Settings(); s.setValue("widget_mode_layout", "day_brief")
    s.setValue("widget_mode_show_overview_stacked", False)
    migrate_widget_mode_settings(s, user_styles_path=MISSING)
    assert s.value("widget_mode_show_overview_stacked") is False

def test_missing_layout_uses_legacy_skin_link():
    s = Settings(); s.setValue("widget_mode_skin", "forest_mist")
    migrate_widget_mode_settings(s, user_styles_path=MISSING)
    assert s.value("widget_mode_layout") == "stacked"
    assert s.value("widget_mode_surface") == "card"

@pytest.mark.parametrize("skin,surface", [("studio_linen", "line"), ("studio_contrast", "outline"),
                                          ("studio_graphite", "compact"), ("studio_lilac", "card"), (None, "card")])
def test_skin_maps_to_surface(skin, surface): ...

def test_second_run_changes_nothing():
    s = Settings(); s.setValue("widget_mode_layout", "side_planner"); s.setValue("widget_mode_skin", "studio_arctic")
    migrate_widget_mode_settings(s, user_styles_path=MISSING)
    snapshot = dict(s.values)
    assert migrate_widget_mode_settings(s, user_styles_path=MISSING) is False
    assert s.values == snapshot

def test_unsaved_free_layout_is_preserved_once():
    s = Settings(); s.setValue("widget_mode_free_layout", json.dumps(seed_free_layout("stacked")))
    migrate_widget_mode_settings(s, user_styles_path=MISSING)
    presets = read_layout_presets(s)
    assert [p["name"] for p in presets] == ["이전 자유 구성"]
    migrate_widget_mode_settings(s, user_styles_path=MISSING)
    assert len(read_layout_presets(s)) == 1

def test_free_layout_equal_to_saved_preset_is_not_duplicated(): ...
def test_unknown_and_messy_layout_values():          # Review Focus 1
    for raw in ("", "  ", "NOPE", " Day_Brief "):
        s = Settings(); s.setValue("widget_mode_layout", raw)
        migrate_widget_mode_settings(s, user_styles_path=MISSING)
        assert s.value("widget_mode_layout") == "stacked"
def test_legacy_keys_are_left_untouched():           # Review Focus 2
    s = Settings()
    for key, value in {"widget_mode_skin": "studio_linen", "widget_mode_panel_theme": "dark",
                       "widget_mode_text_opacity": 80, "widget_mode_background_opacity": 70}.items():
        s.setValue(key, value)
    migrate_widget_mode_settings(s, user_styles_path=MISSING)
    assert s.value("widget_mode_skin") == "studio_linen" and s.value("widget_mode_panel_theme") == "dark"
    assert s.value("widget_mode_text_opacity") == 80 and s.value("widget_mode_background_opacity") == 70
def test_user_layout_classified_from_style_file(tmp_path): ...   # side-by-side placements → dashboard
def test_user_layout_with_missing_style_file(tmp_path):         # Review Focus 4
    s = Settings(); s.setValue("widget_mode_layout", "user_layout_abc123")
    bad = tmp_path / "widget_mode_styles.json"; bad.write_text("{broken", encoding="utf-8", errors="strict")
    migrate_widget_mode_settings(s, user_styles_path=bad)
    assert s.value("widget_mode_layout") == "stacked"
    assert bad.read_text(encoding="utf-8", errors="strict") == "{broken"
```

`" Day_Brief "`는 정규화 뒤 `day_brief`이므로 `stacked`로 옮겨집니다. 위 테스트의 기대값(`stacked`)과 일치합니다.

- [ ] **Step 2: 실패 확인** — `PYTEST tests/test_widget_mode_migration.py` → `ModuleNotFoundError`
- [ ] **Step 3: `widget_mode_migration.py` 구현**(위 처리 순서와 표)
- [ ] **Step 4: 통과 확인** — 같은 명령 → 모두 PASS
- [ ] **Step 5: 커밋** — `feat(widget-mode): migrate retired layouts and skins to the four-layout catalog`

---

### Task 3: 배치 카탈로그를 4종으로

**Files:**
- Modify: `calendar_app/presentation/widgets/widget_mode_skins.py`
  - `_register_builtin_layouts`(:367-465): `agenda_first`, `magazine` 정의를 삭제하고, `work_board` 정의를 여기로 옮깁니다(현재 catalog 값 그대로: placements는 세로, preferred_size (1080, 700), calendar_cell_size (42, 44), calendar_spacing 4, spacing 10, calendar_mode "week", presentation "board", show_overview True, searchable True, row_stretches ((3, 1),)).
  - label_default를 세로형 / 좌우형 / 보드형 / 목록형으로 바꿉니다. label_key는 `widget_mode.layout_stacked`, `widget_mode.layout_dashboard`, `widget_mode.layout_work_board`, `widget_mode.layout_minimal`입니다.
  - `widget_layout_calendar_mode(layout, width=None, display: LayoutDisplay | None = None) -> str`: display가 있으면 `display.calendar_style`을 기본으로 씁니다. `display.search_pinned`이고 width < 520이면 `"week"`입니다. display가 없으면 지금 동작 그대로입니다.
- Modify: `calendar_app/presentation/widgets/widget_workspace_catalog.py`: 배치 specs를 삭제합니다(스킨 팔레트는 Task 5에서 파일째 삭제).
- Modify: `calendar_app/presentation/widgets/widget_mode_visibility.py:6`: `BOARD_CALENDAR_LAYOUT_IDS = frozenset({"dashboard"})`
- Modify: `locales/ko.json`, `locales/en.json`: 위 네 label_key(en: Vertical, Side by side, Board, List)
- Test: `tests/test_widget_mode_skins.py`(갱신), `tests/test_widget_mode_display.py`(추가)

**Interfaces:**
- Consumes: Task 1의 `LayoutDisplay`
- Produces: `widget_mode_layouts()`는 정확히 `stacked, dashboard, work_board, minimal`(+ 사용자 배치)을 반환합니다. `widget_layout_calendar_mode(..., display=...)`.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_builtin_catalog_is_four_layouts():
    ids = [l.layout_id for l in widget_mode_layouts() if not l.layout_id.startswith("user_layout_")]
    assert sorted(ids) == sorted(KEPT_LAYOUT_IDS)  # stacked, dashboard, work_board, minimal
    assert get_widget_mode_layout("work_board").presentation == "board"

def test_calendar_mode_uses_display():
    stacked = get_widget_mode_layout("stacked")
    assert widget_layout_calendar_mode(stacked, 800, LayoutDisplay("month", False, False)) == "month"
    assert widget_layout_calendar_mode(stacked, 500, LayoutDisplay("month", False, True)) == "week"
    assert widget_layout_calendar_mode(stacked, 500, LayoutDisplay("month", False, False)) == "month"
```

- [ ] **Step 2: 실패 확인** — `PYTEST tests/test_widget_mode_skins.py tests/test_widget_mode_display.py`
- [ ] **Step 3: 구현.** `tests/test_widget_mode_skins.py`에서 지워진 배치 ID를 기대하던 테스트를 위 기대값으로 고칩니다. 옛 ID → 4종 동작은 Task 2 테스트가 맡습니다.
- [ ] **Step 4: 통과 확인** — 같은 명령, 그리고 `PYTEST tests/test_widget_mode_visibility.py tests/test_widget_week_strip.py`
- [ ] **Step 5: 커밋** — `refactor(widget-mode): reduce built-in layouts to four`

---

### Task 4: 위젯 창이 배치별 표시 옵션을 읽게 하고 보기 버튼 제거

**Files:**
- Modify: `calendar_app/presentation/widgets/unified_widget_mode.py`
  - `_configure_workspace`(:1531-1545): `spec.show_overview` / `spec.searchable` 대신 `read_layout_display(settings, spec)`의 `show_overview` / `search_pinned`.
  - `apply_selected_layout`의 달력 형태(:1957)와 hero 표시(:1982-1986), `resizeEvent`(:3016): `widget_layout_calendar_mode(layout_spec, width, display)`.
  - 보기 버튼 생성(:1505-1512)과 `_fill_workspace_views`(:1521-1529), `view_btn`을 참조하는 폭 반응 코드(:2208 근처)를 삭제합니다.
  - Ctrl+F로 검색창을 여는 동작(:1847-1856)은 유지합니다.
- Test: `tests/test_widget_mode_ux.py`, `tests/test_widget_workspace_redesign.py`(갱신)

**Interfaces:**
- Consumes: Task 1의 `read_layout_display`, Task 3의 `widget_layout_calendar_mode(..., display)`

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/test_widget_mode_ux.py`의 `Host` 사용)

```python
def test_display_options_drive_overview_search_and_calendar(qapp):
    host = Host(); s = host.settings
    s.setValue("widget_mode_layout", "stacked")
    write_layout_display(s, "stacked", LayoutDisplay("month", True, True))
    window = UnifiedWidgetController(host).ensure_widget()
    window.resize(600, 700); window.apply_selected_layout(force=True)
    assert window.workspace_overview.isVisibleTo(window)
    assert window.search_input.isVisibleTo(window)
    assert window.cal_grid.display_mode == "month"

def test_view_button_is_gone(qapp):
    window = UnifiedWidgetController(Host()).ensure_widget()
    assert not hasattr(window, "view_btn")
```

- [ ] **Step 2: 실패 확인** — `PYTEST tests/test_widget_mode_ux.py -k "display_options or view_button"`
- [ ] **Step 3: 구현.** 보기 버튼을 기대하던 기존 테스트(`test_widget_workspace_redesign.py`의 보기 메뉴 검사)는 삭제합니다. 배치 전환은 더 보기 ▸ 배치가 맡습니다.
- [ ] **Step 4: 통과 확인** — `PYTEST tests/test_widget_mode_ux.py tests/test_unified_widget_mode.py tests/test_widget_workspace_redesign.py tests/test_widget_mode_efficiency.py`
- [ ] **Step 5: 커밋** — `feat(widget-mode): read per-layout display options; remove view button`

---

### Task 5: 스킨을 표면 모양으로 교체

**Files:**
- Modify: `calendar_app/presentation/widgets/widget_mode_skins.py`
  - `WidgetModeSkin`, `_SKINS`, `register_widget_mode_skin`, `widget_mode_skins`, `get_widget_mode_skin`, `read/write_widget_mode_skin_id`, `apply_widget_mode_skin`, `_register_builtin_skins`, 사용자 스킨 로딩을 삭제합니다.
  - `read_widget_mode_layout_id`의 스킨 대체(:216-225)는 `widget_mode_migration.LEGACY_SKIN_LAYOUTS`를 읽어 옛 ID를 구한 뒤 `RETIRED_LAYOUTS`로 4종에 맞춥니다. 저장된 값이 옛 ID일 때도 `RETIRED_LAYOUTS`로 맞춥니다. 이 경로는 이관이 아직 돌지 않은 화면(예: 위젯 관리자)을 위한 것이며, 아무것도 쓰지 않습니다. `widget_mode_migration`이 `widget_mode_skins`를 import하므로 함수 안에서 지역 import를 합니다(순환 import 방지).
  - `__all__`을 정리합니다.
- Delete: `calendar_app/presentation/widgets/widget_workspace_catalog.py`(Task 3 뒤 팔레트만 남은 파일), `widget_mode_skins.py`의 `register_workspace_presets` import·호출
- Modify: `calendar_app/presentation/widgets/widget_workspace_styles.py`: `workspace_styles(tokens, surface: WidgetModeSurface) -> str`. 카드/구분선/테두리/촘촘 CSS는 Task 1 표 값으로 만듭니다. card도 반경 규칙을 냅니다(legacy 분기 없음).
- Modify: `calendar_app/presentation/widgets/unified_widget_mode.py`
  - `_widget_theme_tokens`(:131-135): `_resolve_widget_mode_tokens(app=host)`만 반환합니다(스킨·색 덮어쓰기 호출 삭제. 연동 상태에서 둘 다 색을 바꾸지 않으므로 화면 동일).
  - `apply_theme`(:2057, 2076, 2149): `get_widget_mode_surface(read_widget_mode_surface(settings))`
  - 더 보기의 스킨 하위 메뉴(:2928-2937): 제목 `t("widget_mode.surface_title", "표면 모양")`, 항목은 `widget_mode_surfaces()`, 선택 시 `controller.set_surface(key)`
  - `UnifiedWidgetController.set_skin`(:3629) → `set_surface(self, key: str) -> None`. `widget_mode_panel_theme` 쓰기는 없앱니다.
- Modify: `calendar_app/presentation/dialogs/widget_customization_dialog.py`
  - 스킨 갤러리·숨은 콤보(:633-660, 669, 801) → 표면 4종 카드. 썸네일 반경은 `surface.radius`, 저장 키는 `SURFACE_SETTING_KEY`.
  - `_apply` 허용 목록: `"widget_mode_skin"` → `SURFACE_SETTING_KEY`. `:128`의 skin 초안 줄도 바꿉니다.
- Modify: `calendar_app/presentation/widgets/widget_management_ui.py:243, 261`: 스킨 이름 대신 표면 이름. 요약 문구는 `t("widget_hub.mode_catalog", "배치 {layouts}종 · 표면 모양 {surfaces}종", ...)`.
- Modify: `locales/ko.json`, `locales/en.json`: `widget_mode.surface_title`(표면 모양 / Surface), `surface_card`(카드 / Card), `surface_line`(구분선 / Divider), `surface_outline`(테두리 / Outline), `surface_compact`(촘촘 / Compact), `widget_hub.mode_catalog`
- Test: `tests/test_widget_main_theme.py`, `tests/test_widget_workspace_studio.py`, `tests/test_widget_workspace_redesign.py`, `tests/test_widget_mode_skins.py`, `tests/test_widget_management_hub.py`(갱신)

**Interfaces:**
- Consumes: Task 1의 surface API
- Produces: `UnifiedWidgetController.set_surface(key: str) -> None`, `workspace_styles(tokens, surface) -> str`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_surface_changes_item_border_style(qapp):
    host = Host(); write_widget_mode_surface(host.settings, "line")
    window = UnifiedWidgetController(host).ensure_widget(); window.apply_theme()
    assert "border-bottom: 1px solid" in window.styleSheet()
    window.controller.set_surface("outline")
    assert "border-bottom: 1px solid" not in window.styleSheet()

@pytest.mark.parametrize("surface", ["card", "line", "outline", "compact"])
@pytest.mark.parametrize("text_theme", ["light", "dark"])
def test_surfaces_keep_contrast_floor(surface, text_theme): ...   # 기존 스킨별 대비 검사(test_widget_workspace_redesign.py:113)를 표면 × 테마로 교체

def test_customization_gallery_offers_four_surfaces(qapp): ...     # 카드 4개, 선택 후 취소하면 widget_mode_surface 미변경
```

- [ ] **Step 2: 실패 확인** — `PYTEST tests/test_widget_main_theme.py tests/test_widget_workspace_redesign.py`
- [ ] **Step 3: 구현.** 스킨 ID·개수를 고정하던 테스트는 표면 기준으로 고치거나 삭제합니다. 대상은 `test_widget_mode_skins.py`의 스킨 등록·사용자 스킨, `test_widget_workspace_studio.py`의 studio 팔레트, `test_widget_main_theme.py:94-124`의 스킨 색 무시 검사입니다. 스킨 색 무시 검사는 스킨이 없어졌으므로 삭제합니다.
- [ ] **Step 4: 통과 확인** — `PYTEST tests/test_widget_main_theme.py tests/test_widget_workspace_studio.py tests/test_widget_workspace_redesign.py tests/test_widget_mode_skins.py tests/test_widget_management_hub.py tests/test_widget_mode_ux.py tests/test_unified_widget_mode.py`
- [ ] **Step 5: 커밋** — `refactor(widget-mode): replace 16 skins with four surface styles`

---

### Task 6: 이관 연결과 작업 공간 호환

**Files:**
- Modify: `calendar_app/presentation/widgets/unified_widget_mode.py:3099-3104` `ensure_widget`: `UnifiedWidgetWindow(self)` 직전에 `migrate_widget_mode_settings(self.main_window.settings, preserved_name=t("widget_mode.preserved_free_layout", "이전 자유 구성"))`
- Modify: `calendar_app/presentation/widgets/widget_workspace_runtime.py:310-332` `_restore_mode`: 키를 쓴 직후, `apply_selected_layout` 전에 같은 호출
- Modify: `calendar_app/domain/widget_workspace.py`
  - `MODE_KEYS`(:47-70)에 `widget_mode_surface`, `widget_mode_layout_legacy` 추가(옛 키는 유지)
  - `mode_setting_allowed`(:73-80)의 접두사 목록에 `widget_mode_calendar_style_`, `widget_mode_show_overview_`, `widget_mode_search_pinned_` 추가
- Modify: `locales/ko.json`, `locales/en.json`: `widget_mode.preserved_free_layout`(이전 자유 구성 / Previous free layout)
- Test: `tests/test_widget_workspace_model.py`, `tests/test_widget_mode_migration.py`(추가)

**Interfaces:**
- Consumes: Task 2의 `migrate_widget_mode_settings`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_ensure_widget_migrates_before_first_layout(qapp):
    host = Host(); host.settings.setValue("widget_mode_layout", "side_planner")
    window = UnifiedWidgetController(host).ensure_widget()
    assert window.active_layout_id() == "dashboard"
    assert window.workspace_overview.isVisibleTo(window)

def test_restoring_old_snapshot_migrates_layout(tmp_path):   # Review Focus 3
    # 프로필 mode에 {"widget_mode_layout": "month_focus", "widget_mode_skin": "studio_linen"}만 담아 _restore_mode 호출
    assert settings.value("widget_mode_layout") == "stacked"
    assert settings.value("widget_mode_calendar_style_stacked") == "month"
    assert settings.value("widget_mode_surface") == "line"

def test_new_keys_are_captured_by_workspace():
    assert mode_setting_allowed("widget_mode_surface")
    assert mode_setting_allowed("widget_mode_search_pinned_dashboard")
```

- [ ] **Step 2: 실패 확인** — `PYTEST tests/test_widget_workspace_model.py tests/test_widget_mode_migration.py`
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — 같은 명령, 그리고 `PYTEST tests/test_widget_workspace_redesign.py tests/test_widget_mode_coordinator.py`
- [ ] **Step 5: 커밋** — `feat(widget-mode): run settings migration on window creation and workspace restore`

---

### Task 7: 꾸미기 표시 탭 옵션, 투명도 슬라이더 제거

**Files:**
- Modify: `calendar_app/presentation/dialogs/widget_customization_dialog.py`
  - `_visibility_tab`(:856-928) 맨 위에 '선택한 배치' 묶음을 추가합니다.
    - 달력 형태 `QComboBox`(주간 `week` / 월간 `month`)
    - `요약 줄 표시` `QCheckBox`
    - `검색창 항상 표시` `QCheckBox`
    - 도움말 `선택한 배치에만 적용됩니다.`
  - 초안 배치(`read_widget_mode_layout_id(self.draft)`)가 바뀌면 세 값을 그 배치 값으로 다시 읽습니다.
  - 초안 배치가 `minimal`이거나 자유 구성이면 달력 형태 줄을 숨깁니다(요약·검색은 유지).
  - 값은 `self.draft`의 `display_key(...)`로 씁니다.
  - `_apply` 저장 조건에 세 접두사를 추가합니다.
  - 투명도 슬라이더 두 개(:750-788)와 그 초안·허용 키(`TEXT_OPACITY_KEY`, `BACKGROUND_OPACITY_KEY`, :1113-1114)를 삭제합니다. 그 자리에는 안내 `t("widget_mode.surface_help", "색과 투명도는 모양 설정을 따릅니다.")`와 링크 버튼 `t("widget_mode.open_appearance", "모양 설정 열기")`(objectName `open_appearance_btn`)를 둡니다. 링크는 `self.controller.main_window.open_panel_background_color_dialog()`를 호출합니다. 메서드가 없으면 버튼을 숨깁니다.
- Modify: `locales/ko.json`, `locales/en.json`
  - `widget_mode.display_group`(선택한 배치 / This layout)
  - `widget_mode.calendar_style`(달력 형태 / Calendar)
  - `widget_mode.show_overview`(요약 줄 표시 / Show summary)
  - `widget_mode.search_pinned`(검색창 항상 표시 / Always show search)
  - `widget_mode.display_scope_help`(선택한 배치에만 적용됩니다. / Applies to this layout only.)
  - `widget_mode.surface_help`, `widget_mode.open_appearance`
  - 주간·월간은 기존 `widget_mode.week_toggle` / `widget_mode.month_toggle`을 재사용합니다.
- Test: `tests/test_widget_layout_presets_customization.py` 또는 새 `tests/test_widget_customization_display.py`

**Interfaces:**
- Consumes: Task 1의 `display_key`, `read_layout_display`, prefix 상수

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_display_options_apply_to_selected_layout_only(qapp): ...
    # stacked 선택 상태에서 월간·요약 켬 → 적용 → stacked 키만 바뀌고 dashboard 키는 그대로
def test_display_options_cancel_keeps_settings(qapp):        # Review Focus 5
    dialog = WidgetCustomizationDialog(controller); dialog.calendar_style_combo.setCurrentIndex(1)
    dialog.reject()
    assert settings.value("widget_mode_calendar_style_stacked") == before
def test_calendar_style_hidden_for_list_layout(qapp): ...
def test_opacity_sliders_removed(qapp):
    dialog = WidgetCustomizationDialog(controller)
    assert not [w for w in dialog.findChildren(QSlider) if "투명" in w.accessibleName()]
    assert dialog.findChild(QPushButton, "open_appearance_btn") is not None
```

- [ ] **Step 2: 실패 확인** — `PYTEST tests/test_widget_customization_display.py`
- [ ] **Step 3: 구현.** 슬라이더를 기대하던 `tests/test_widget_mode_opacity.py`의 꾸미기 검사는 삭제합니다. `read_widget_opacities` 자체 테스트는 함수가 남으므로 유지합니다.
- [ ] **Step 4: 통과 확인** — `PYTEST tests/test_widget_customization_display.py tests/test_widget_mode_opacity.py tests/test_widget_layout_presets_customization.py tests/test_widget_mode_ux.py`
- [ ] **Step 5: 커밋** — `feat(widget-mode): add per-layout display options to customization; drop dead opacity sliders`

---

### Task 8: 구성 편집기·위젯 스타일 만들기·옛 팔레트 명령 제거

**Files:**
- Delete:
  - `calendar_app/presentation/dialogs/widget_free_layout_editor.py`, `calendar_app/presentation/dialogs/widget_style_editor_dialog.py`
  - `calendar_app/presentation/widgets/widget_layout_editor_canvas.py`, `widget_layout_editor_preview.py`, `widget_layout_editor_io.py`
  - `tests/test_widget_free_layout_editor.py`, `tests/test_widget_layout_editor_advanced.py`, `tests/test_widget_layout_editor_preview.py`, `tests/test_widget_layout_presets_editor.py`
  - `scripts/validate_widget_layout_editor_advanced.py`
- Modify: `calendar_app/presentation/widgets/unified_widget_mode.py`
  - 더 보기의 `구성 편집…`(:2876-2878), `위젯 스타일 만들기` 항목과 처리(:2939, 2960-2970)
  - `UnifiedWidgetController.open_free_layout_editor`(:3673-3680)
- Modify: `calendar_app/presentation/dialogs/widget_customization_dialog.py`: `free_layout_btn`(:188-197), `_open_free_layout_editor`(:1150-1152), 내 배치 `수정` 버튼과 `_edit_user_layout`(:498-530 근처). 이름 변경·삭제는 유지합니다.
- Modify: `calendar_app/presentation/widgets/widget_management_ui.py`: `자유 구성 편집` 버튼(:195)과 `_edit_free`(:322-335)
- Modify: `calendar_app/presentation/widgets/widget_mode_skins.py`: `create_user_widget_skin`, `create_user_widget_layout`, `load_user_widget_styles`와 모듈 끝 호출(:591). `_read_user_style_document`와 `USER_STYLES_PATH`는 이관이 쓰므로 유지합니다.
- Modify: `calendar_app/presentation/widgets/command_palette_runtime.py:715-738`: `open_schedule_widget_panel`, `open_work_widget_panel`, `open_all_widget_panels` 항목. 같은 메서드를 가리키는 다른 호출부(`window_shell_actions.py:627-637`)가 팔레트 전용이면 함께 삭제하고, 다른 호출부가 있으면 남깁니다.
- Modify: `scripts/validate_widget_free_layout.py`, `scripts/validate_widget_layout_presets.py`, `scripts/validate_widget_workspace_redesign.py`, `scripts/validate_widget_mode_ux_plan.py`, `scripts/validate_widget_workspace_studio.py`, `scripts/validate_widget_management.py`: 삭제한 모듈·배치·스킨을 import하거나 참조하면 그 부분을 지웁니다. 검증 주제 전체가 사라진 스크립트는 삭제합니다.
- Test: `tests/test_widget_free_layout_runtime.py`, `tests/test_widget_free_layout_model.py`, `tests/test_widget_layout_presets.py`, `tests/test_command_palette.py`(갱신)

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_more_menu_has_no_editor_entries(qapp): ...   # 메뉴 액션 텍스트에 "구성 편집", "위젯 스타일 만들기" 없음
def test_saved_free_layout_still_opens_without_editor(qapp):
    # 내 배치 1개 저장 → controller.apply_layout_preset(id) → window._free_layout_active is True, 블록 렌더
def test_customization_keeps_rename_and_delete_only(qapp): ...
def test_palette_has_single_widget_mode_command(): ...  # command_id 목록에 open_*_widget_panel(s) 없음
```

- [ ] **Step 2: 실패 확인** — `PYTEST tests/test_widget_free_layout_runtime.py tests/test_command_palette.py`
- [ ] **Step 3: 구현.** 삭제 뒤 `grep -rn -E "widget_free_layout_editor|widget_style_editor_dialog|widget_layout_editor_(canvas|preview|io)|create_user_widget_|open_free_layout_editor" calendar_app tests scripts`가 0건이어야 합니다.
- [ ] **Step 4: 통과 확인** — `PYTEST tests/test_widget_free_layout_runtime.py tests/test_widget_free_layout_model.py tests/test_widget_layout_presets.py tests/test_widget_layout_presets_customization.py tests/test_command_palette.py tests/test_widget_management_hub.py tests/test_keyboard_shortcuts.py`
- [ ] **Step 5: 커밋** — `refactor(widget-mode): remove free layout editor, style editor and legacy palette commands`

---

### Task 9: 쓰이지 않는 스타일 코드 정리, 번역 채우기, 전체 검증

**Files:**
- Modify: `calendar_app/presentation/widgets/panel_widget_theme.py`
  - 삭제 후보: `_apply_widget_color_override`(:96), `_apply_configured_widget_color`(:276), `_apply_widget_background_opacity`(:287), `_apply_panel_theme_override`(:357), `_apply_registered_widget_mode_skin`(:361), `_widget_mode_*_stylesheet` 래퍼(:347-409, `_widget_mode_menu_stylesheet` 포함), `_read_widget_color_mode_from_settings`·`_normalize_widget_color_mode`·`_widget_color_mode_accent`
- Modify: `calendar_app/presentation/widgets/panel_widget_style.py:86-672`: 위 래퍼에서만 닿던 `apply_dark_theme`과 패널·항목·빠른 추가·달력·칩·런처 스타일 함수
- Modify: `calendar_app/presentation/widgets/widget_mode_skins.py`: 읽히지 않는 배치 필드는 남깁니다(사용자 JSON `asdict` 호환, 스펙 5절)
- Modify: 17개 로케일(`locales/*.json`), `scripts/i18n_pending_review.json`, `tests/fixtures/i18n_audit_baseline.json`

삭제 규칙: 각 함수에 대해 `grep -rn "<이름>" calendar_app scripts`(정의 제외)가 0건일 때만 지웁니다. 테스트에서만 쓰이면 함수와 그 테스트를 함께 지웁니다. 하나라도 앱 호출부가 있으면 남기고, 결과 메모에 이유를 적습니다.

- [ ] **Step 1: 후보별 호출부 확인 후 삭제.** 각 후보에 대해 위 grep을 실행하고, 0건인 함수만 지웁니다.
- [ ] **Step 2: 회귀 확인** — `PYTEST tests/test_widget_main_theme.py tests/test_widget_mode_ux.py tests/test_unified_widget_mode.py`, 그리고 `grep -rl -E "panel_widget_theme|panel_widget_style" tests`로 찾은 테스트 파일 → PASS
- [ ] **Step 3: 번역 채우기** — `.venv/Scripts/python.exe scripts/i18n_sync.py --base ko --fill-missing`(`--auto-translate` 없이). 그다음 `.venv/Scripts/python.exe scripts/audit_i18n.py --update-baseline`. 배치 이름 4개는 원문이 바뀌었으므로 다른 언어 값도 영어로 바꿔 검토 대기에 남깁니다. 남은 원문 변경 항목은 `--accept-drift` 없이 그대로 둡니다.
- [ ] **Step 4: 위젯·i18n 관련 테스트 전체** — `PYTEST tests/test_widget_*.py tests/test_unified_widget_mode.py tests/test_command_palette.py tests/test_keyboard_shortcuts.py tests/test_i18n_audit.py tests/test_i18n_c_misc.py tests/test_i18n_runtime_support.py` → 실패 0건. 파일을 한 프로세스에서 돌리다 요약 없이 끝나면(qFatal) 파일별로 나눠 돌리고, 메모리의 qFatal 진단 절차를 따릅니다.
- [ ] **Step 5: 정적 검사** — `.venv/Scripts/python.exe scripts/run_encoding_guard.py`, `.venv/Scripts/ruff.exe check calendar_app tests scripts`, `PYTEST tests/test_encoding_policy.py tests/test_encoding_utils.py`
- [ ] **Step 6: 전체 테스트(백그라운드 약 16분)** — `PYTEST tests -v > artifacts/widget-mode-phase1/full-suite.log 2>&1`. 실패를 이번 변경 탓과 기존 실패로 나눠 기록합니다.
- [ ] **Step 7: 화면 확인** — 임시 INI로 위젯 창을 띄웁니다(`scripts/isolated_settings.py`). 세로형·좌우형·보드형·목록형 × 카드·구분선 × 다크·라이트를 폭 360px과 1280px에서 `grab()`으로 `artifacts/widget-mode-phase1/`에 저장해 겹침·잘림이 없는지 봅니다. 화면 전체 캡처는 쓰지 않습니다.
- [ ] **Step 8: 변경 기록** — `.venv/Scripts/python.exe scripts/manage_version.py record --kind change --event-id widget-mode-phase1-cleanup-20261122 --summary "위젯 전용 모드 1단계: 배치 4종·표면 4종, 편집기·스타일 만들기·투명도 슬라이더 제거, 설정 이관" --files <이번에 바꾼 실행 파일들>`, 그다음 `scan --strict`. 이번 범위 밖의 미등록 파일(예: `month_renderer.py`)은 흡수하지 않습니다.
- [ ] **Step 9: 문서 갱신과 커밋** — `TASKS.md`의 1단계 항목을 `[x]`로 바꾸고 검증 수치를 적습니다. 스펙 문서 머리의 상태를 '1단계 구현 완료'로 바꿉니다. 커밋 메시지는 `chore(widget-mode): phase 1 cleanup verification, translations and records`.

---

## Self-Review 메모

- 스펙 4.1절의 배치 표는 Task 2(이관)·Task 3(카탈로그)·Task 4(창), 표면 표는 Task 1·2·5, 자유 구성 보존은 Task 2·8, 제거 목록은 Task 4·7·8·9, 5절 이관 규칙은 Task 2·6, 7절 검증은 Task 9가 맡습니다.
- 스펙 6절 1단계의 '표시 탭 옵션을 1단계에 포함'은 Task 7이 맡습니다.
- 2–4단계(꾸미기 3탭 재구성, 더 보기 메뉴 재구성, 토큰화, 용어 통합)는 이 계획 밖입니다. 1단계 결과를 보고 따로 계획합니다.
