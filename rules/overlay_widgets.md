# 오버레이 위젯 시스템 규칙

## 위젯 종류 (7종)

| 타입 | 클래스 | 파일 |
|---|---|---|
| `clock` | `OverlayClockWidget` | `overlay_clock.py` |
| `stopwatch` | `OverlayStopwatchWidget` | `overlay_stopwatch.py` |
| `date_card` | `OverlayDateCardWidget` | `overlay_datecard.py` |
| `countdown` | `OverlayCountdownWidget` | `overlay_countdown.py` |
| `dday` | `OverlayDDayWidget` | `overlay_dday.py` |
| `text` | `OverlayTextWidget` | `overlay_text.py` |
| `weather` | `OverlayWeatherWidget` | `overlay_weather.py` |

## 인스턴스 관리 (`OverlayWidgetManager`)

```python
# overlay_manager.py
manager.add_instance(widget_type)      # → inst_id (예: "clock_0")
manager.remove_instance(inst_id)
manager.rename_instance(inst_id, name)
manager.show_instance(inst_id)
manager.hide_instance(inst_id)
manager.toggle_instance(inst_id)
manager.instances_of(widget_type)      # → [(id, name, widget), ...]
manager.all_instances()                # → [(id, name, type, widget), ...]
manager.restore_all()                  # 앱 시작 시 호출
manager.save_all()                     # 앱 종료 시 호출 (변경 시 자동 저장)
```

**영속화**: QSettings `"overlay_instances"` 키에 JSON으로 저장.

## 설정 prefix 규칙

```
인스턴스 ID:    clock_0
설정 prefix:   oi_clock_0_
설정 키 예:    oi_clock_0_font_size
               oi_clock_0_tz_offset_mins
```

`_SettingsProxy`를 통해 접근 — 직접 `QSettings`에 접근하지 말 것.

## 새 위젯 타입 추가 절차

1. `overlay_<type>.py` 파일 생성 (베이스: `overlay_base.py`)
2. `overlay_manager.py`의 `_WIDGET_TYPES` dict에 등록:
   ```python
   "new_type": {
       "label_key": "menu.widget_new_type",
       "label_default": "New Widget",
       "class": "OverlayNewWidget",
       "icon": ICON.WIDGET_NEW,
       "default_offset": QPoint(-230, 560),
       "init_method": "_init_new_type_instance",
   }
   ```
3. `app_initializer.py`에서 `init_overlay_manager()` 확인

## 위젯 베이스 패턴

모든 위젯은 다음을 구현해야 합니다:

```python
class OverlayXxxWidget(OverlayBaseWidget):
    def _open_settings(self, initial_tab: int = 0):
        """기본 탭 + 고급 템플릿 탭이 있는 설정 다이얼로그."""
        ...

    def _is_template_mode(self) -> bool:
        """템플릿 모드 활성화 여부."""
        ...
```

**컨텍스트 메뉴 패턴**: "⚙️ Settings...", "✏️ Advanced: Edit template...", 비활성화 모드 표시기.

**공유 스타일시트**: `_DLG_SS = OverlayClockWidget._DLG_SS` (모든 위젯이 Clock의 SS를 참조).

## 공통 표시 스타일 프리셋

- 레지스트리: `presentation/widgets/overlay_display_presets.py`
- 모든 7종 위젯은 같은 순서와 같은 값의 13개 디자인 프리셋을 제공합니다.
- 프리셋은 글꼴 후보, 글자색, 배경색, 테두리색, 각 색상의 알파, 여백, 모서리와 테두리 형태를 한 번에 적용합니다.
- 선택값은 인스턴스 설정의 `appearance_preset`에 저장합니다. 개별 색상·글꼴·투명도를 직접 바꾸면 `custom`으로 전환합니다.
- 위젯별 `display_style`은 콘텐츠 배치와 표시 형식을 위한 호환 설정입니다. 컨텍스트 메뉴에서는 `표시 형식`으로 분리하며, 공통 외관 프리셋과 서로 덮어쓰지 않습니다.
- 기존 사용자의 글꼴·색상·투명도 또는 `display_style` 값이 있으면 외관을 덮어쓰지 않고 `custom`으로 이관합니다. 외관 설정이 없는 새 위젯만 `midnight_glass`를 기본 적용합니다.
- 새 프리셋은 모든 위젯에서 의미가 같은 완결된 외관 토큰 세트로 추가하고, 특정 위젯의 시간/날짜/상태 표시 로직을 포함하지 않습니다.
- `pure_type`은 글자만 남기는 프리셋입니다. 배경과 테두리 알파를 0으로 저장하고 `background_type=transparent`로 그라데이션 합성도 차단하며, 조작 가능한 투명 영역은 기존 입력 표면 처리로 유지합니다.

## 템플릿 프리셋 관리 정책

- `widget_presets.json`과 `_PRESET_FALLBACK`의 기본 프리셋은 앱이 제공하는 고정 항목입니다. 사용자는 기본 항목을 수정·이름 변경·삭제하거나 같은 이름으로 덮어쓸 수 없습니다.
- 사용자가 저장한 프리셋만 수정·이름 변경·삭제할 수 있으며, 프리셋 목록에는 `기본`/`사용자` 유형을 함께 표시합니다.
- 이전 버전에서 숨긴 기본 프리셋은 다시 표시합니다. 기본 이름으로 저장했던 사용자 덮어쓰기는 삭제하지 않고 `<이름> (사용자 사본)`으로 자동 이전합니다.
- 저장·업데이트 전에 위젯 종류별 변수, 조건식, 정렬, 글자 크기·색상·줄 간격 힌트 문법을 검사합니다. 오류가 있으면 저장하지 않고 미리보기에도 첫 오류를 표시합니다.
- 내부 설정 prefix `overlay_date_card`는 프리셋 카탈로그 키 `datecard`로 정규화합니다.
- 기본 카탈로그 일부가 손상되면 해당 위젯의 전체 기본 목록을 `_PRESET_FALLBACK`으로 대체해 부분 누락을 방지합니다.

## 위젯별 상태 저장 키

| 위젯 | 상태 키 | 타이머 |
|---|---|---|
| Stopwatch | `sw_elapsed_ms`, `sw_running`, `sw_started_mono`, `sw_started_wall`, `sw_started_boot_epoch` | 100ms, 자체 관리 |
| Countdown | `cd_target_iso` | 1000ms, 자체 관리 |
| Clock | `tz_offset_mins` (None=로컬) | 1000ms |
| D-Day | `dd_target_date` (yyyy-MM-dd), `dd_label` | 60s, 자체 관리 |

**Stopwatch/Countdown/DDday 위젯**은 자체 디스플레이를 직접 관리합니다 — 공유 push refresh 없음.

- 실행 중 스톱워치는 같은 부팅 세션에서는 monotonic 시계를 사용하고, Windows 재부팅으로 monotonic 기준점이 바뀌면 wall-clock 시작값으로 복원합니다.
- 숨긴 위젯의 자체 타이머와 날씨 네트워크 갱신은 정지하고, 다시 표시할 때 재개합니다.
- 인스턴스 삭제 시 `oi_<inst_id>_`로 시작하는 전용 설정을 함께 제거해 ID 재사용 시 이전 설정이 섞이지 않게 합니다.
- 저장 좌표가 현재 모니터 범위를 벗어나면 사용 가능한 화면 안으로 보정합니다.

## 크로스 위젯 참조

```python
# widget_registry()로 다른 위젯 값 참조 가능
registry = manager.widget_registry()  # {inst_id: widget}
manager.refresh_all_texts(tier="fast")  # fast 변수를 쓰는 text 위젯만 갱신

# Text 위젯 템플릿에서 참조
{stopwatch:stopwatch_0}   # stopwatch_0 인스턴스 값
{countdown:countdown_0}  # countdown_0 인스턴스 값
{dday:dday_0}            # dday_0 인스턴스 값
```

## 앱 데이터 변수 등록

```python
# app_initializer.py에서 등록
manager.set_app_data_provider(lambda: {
    "task_count": ...,
    "directive_count": ...,
    "next_event": ...,
})
```

## 위젯 전용 모드 스킨

### 위젯 전용 모드 UI / 저장

- 기본 진입점은 `WidgetModeCoordinator` → `UnifiedWidgetController`입니다.
- `메인 화면으로`는 메인 창을 표시하며, `트레이로 숨기기`는 메인 창을 열지 않습니다.
- `widget_mode_resume`는 정상 종료 후 모드 복원에 사용합니다. 위젯 전용모드에서 앱을 종료할 때 위젯을 숨기기 전에 현재 모드를 다시 저장하고 `QSettings.sync()`로 기록을 확정합니다. 다음 실행에서는 메인 창의 첫 paint 이후 복원하여 시작 화면이 남지 않게 합니다.
- `widget_mode_filter`, `widget_mode_always_top`, `widget_mode_show_completed`는 다시 열 때 유지합니다.
- 항상 위 플래그를 변경할 때 발생하는 임시 hide는 모드 종료로 처리하지 않습니다.
- 메인 창 소유의 편집 다이얼로그를 열 때만 항상 위 플래그를 잠시 해제하고, 사용자 설정은 유지합니다.
- 꾸미기는 `WidgetCustomizationDialog`의 독립 설정 초안과 실제 위젯 렌더링으로 미리 봅니다. 적용 전에는 실제 설정이나 창 좌표를 쓰지 않습니다.
- 배치와 색상 초안을 각각 초기화하여 색상 변경이 레이아웃의 이전 호환 기본값을 따라 바꾸지 않게 합니다.
- 전체 글자 크기, 시계/날짜 캘린더/보조 설명 표시는 `widget_mode_font_size`, `widget_mode_show_clock`, 레이아웃별 `widget_mode_calendar_visible_<layout>`, `widget_mode_show_hint`로 저장합니다. `widget_mode_show_week`는 이전 버전 호환용으로 함께 기록합니다. 기존 10~18 설정값은 호환 유지하되 날짜·버튼·캘린더·목록에 공통 타이포그래피 단계로 적용하며, 일정/업무 제목은 본문과 같은 크기에서 굵기로만 구분합니다.
- 글자/배경 불투명도는 `widget_mode_text_opacity`(20~100), `widget_mode_background_opacity`(0~100)로 독립 저장합니다. 기존 `widget_mode_opacity`는 배경의 기본값으로만 읽으며 글자는 기본 100%입니다.
- 창 전체의 `windowOpacity`는 1.0을 유지합니다. 글자색과 배경/테두리의 알파를 각기 적용하며 주간 날짜 버튼과 직접 그리는 체크박스 배경도 포함합니다. 조작 아이콘은 계속 표시합니다.
- 미리보기는 실제 위젯과 같은 알파 렌더링을 체크무늬 배경 위에 합성합니다. 전체 이미지에 불투명도를 다시 곱하지 않으며 취소 시 실제 설정을 변경하지 않습니다.
- 글꼴과 제목 굵기는 `widget_mode_font_family`, `widget_mode_font_weight`로 저장합니다. 미리보기에도 동일한 글꼴을 적용하며 취소 시 저장하지 않습니다.
- 조작부, 본문, 하단 상태/크기 조절은 하나의 `unified_surface` 안에 배치합니다. 대시보드/매거진 배치는 폭 640px 미만에서 세로로 전환하되 저장된 배치 선택은 유지합니다.
- 날짜 선택/오늘/고정/꾸미기는 한 줄 헤더로 통합하고 시계는 하단에 표시합니다. 세로·일정 우선형은 주간 날짜를, 좌우 대시보드·매거진형은 기본으로 펼쳐진 월간 캘린더를 표시합니다. 대시보드형은 달력을 왼쪽, 필터와 목록을 오른쪽에 두며 매거진형은 이를 반대로 배치합니다. 날짜 영역의 접기 상태는 레이아웃마다 독립 저장하고 더 보기 메뉴의 이전/다음 기간도 주간·월간에 맞춰 전환합니다.
- 월간 캘린더는 별도 불투명 패널처럼 보이지 않도록 셀 뷰포트를 투명하게 유지합니다. 요일 머리글과 선택일만 현재 스킨 색상을 낮은 알파로 합성하고, 주말은 고정 빨강 대신 스킨 강조색을 사용하며 글자/배경 불투명도 설정을 각각 따릅니다.
- 주간 날짜는 큰 타원형 캡슐 대신 작은 카드형 셀을 사용합니다. 기본/오늘/선택/호버/키보드 포커스 상태를 배경, 가는 테두리, 하단 강조선과 글자 굵기로 구분하며 현재 스킨과 글자·배경 불투명도 설정을 그대로 따릅니다.
- 보조 설명 설정은 모든 기본 배치와 미리보기에서 동일하게 동작합니다. 배치 내부 기본값 때문에 사용자가 켠 설정을 다시 숨기지 않습니다.
- 일정 강조 마커는 카드 위쪽이 아니라 제목 왼쪽 중앙에 맞춥니다. 주요 추가 버튼의 기본/호버/누름 상태는 모두 배경과 대비되는 글자색을 보장합니다.
- 목록 밀도는 `widget_mode_density=compact|standard|comfortable`로 저장합니다. 글꼴/글자 크기/불투명도/배치 설정은 변경하지 않고 행 여백과 시간 배치만 조절합니다. 빠른 메뉴에서는 즉시 저장, 꾸미기에서는 초안 미리보기 후 적용/취소합니다.
- 행마다 반복되는 일정/업무 유형 설명은 표시하지 않습니다. 전체 보기에서는 그룹 제목으로 구분하고 일정 필터에서는 중복 그룹 제목도 생략합니다. 원본 데이터와 ID, 완료/편집 동작은 유지합니다.
- `side_panel_renderer.load_right_panel()`은 패널 검색/상태 필터를 적용하기 전의 원본 업무 데이터를 `_latest_directive_data`로 게시해야 합니다. 메인 창이 숨겨진 상태에서도 위젯이 이 데이터를 받아야 합니다.
- 일부 데이터가 지연되어도 이미 불러온 일정/업무는 지우지 않습니다. 지연 안내와 재시도 동작을 목록 안에 함께 표시합니다.
- 목록에는 원본 `item_id`와 `source=task|directive`를 함께 전달합니다. 완료는 기존 상태 변경 처리기의 성공 응답 후 반영하며, 최근 상태 변경을 실행 취소할 수 있습니다.
- 불러오는 중과 불러오기 지연은 빈 목록과 구분합니다. 목록 개수 제한으로 항목을 생략하지 않습니다.
- 목록 교체 시 기존 행을 즉시 숨긴 후 지연 삭제합니다. 스크롤 내부 레이아웃의 최소 높이를 유지하여 작은 창에서 행이 겹치지 않게 합니다.
- 회귀 검증: `tests/test_widget_mode_ux.py`, `tests/test_unified_widget_mode.py`, `tests/test_widget_mode_coordinator.py`, `tests/test_widget_mode_geometry.py`.
- 밀도/압축 헤더/타이포그래피 회귀 검증: `tests/test_widget_mode_efficiency.py` (설정 재로드, 초안 취소, 역할별 글자 비율, 큰 글꼴·작은 창 포함).

- 스킨 레지스트리: `presentation/widgets/widget_mode_skins.py`
- 선택 설정: 색상 `QSettings["widget_mode_skin"]`, 배치 `QSettings["widget_mode_layout"]`
- 색상 스킨은 `WidgetModeSkin`의 `base_theme`과 semantic token override만 정의합니다.
- 레이아웃은 `WidgetModeLayout`의 grid 배치표, 권장 크기, 행/열 stretch, 섹션별 UI 밀도를 정의합니다.
- 색상과 레이아웃 선택은 서로 변경하지 않습니다.
- 스킨/레이아웃 메뉴는 레지스트리를 순회하므로 새 항목 등록 시 셸이나 컨트롤러를 수정하지 않습니다.
- 기존 `widget_mode_panel_theme=light|dark` 설정은 클래식 라이트/다크로 자동 호환됩니다.
- 토큰 합성 순서: 기본 토큰 → light/dark 기반 → 스킨 override → 사용자 강조색 → 투명도.

```python
from calendar_app.presentation.widgets.widget_mode_skins import (
    WidgetModeLayout,
    WidgetModeSkin,
    register_widget_mode_layout,
    register_widget_mode_skin,
)

register_widget_mode_layout(
    WidgetModeLayout(
        "my_layout",
        "widget_mode.layout_my_layout",
        "내 레이아웃",
        placements=(
            ("hero", 0, 0, 1, 2),
            ("calendar", 1, 0, 1, 1),
            ("agenda", 1, 1, 1, 1),
            ("filters", 2, 0, 1, 2),
        ),
        preferred_size=(720, 520),
    )
)

register_widget_mode_skin(
    WidgetModeSkin(
        "my_skin",
        "widget_mode.skin_my_skin",
        "내 스킨",
        base_theme="dark",
        token_overrides={"accent": "#65a7ff"},
    )
)
```
