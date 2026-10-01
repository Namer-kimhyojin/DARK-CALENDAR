# 오버레이 위젯 시스템 규칙

## 위젯 종류 (8종)

| 타입 | 클래스 | 파일 |
|---|---|---|
| `clock` | `OverlayClockWidget` | `overlay_clock.py` |
| `stopwatch` | `OverlayStopwatchWidget` | `overlay_stopwatch.py` |
| `date_card` | `OverlayDateCardWidget` | `overlay_datecard.py` |
| `countdown` | `OverlayCountdownWidget` | `overlay_countdown.py` |
| `dday` | `OverlayDDayWidget` | `overlay_dday.py` |
| `text` | `OverlayTextWidget` | `overlay_text.py` |
| `weather` | `OverlayWeatherWidget` | `overlay_weather.py` |
| `launcher_deck` | `OverlayLauncherDeckWidget` | `overlay_launcher_deck.py` |

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
- 시계·스톱워치·날짜 카드·카운트다운·D-Day·텍스트·날씨 7종 위젯은 같은 순서와 같은 값의 13개 디자인 프리셋을 제공합니다. 런처 덱은 키캡 전용 스타일과 배열 편집기를 사용합니다.
- 프리셋은 글꼴 후보, 글자색, 배경색, 테두리색, 각 색상의 알파, 여백, 모서리와 테두리 형태를 한 번에 적용합니다.
- 선택값은 인스턴스 설정의 `appearance_preset`에 저장합니다. 개별 색상·글꼴·투명도를 직접 바꾸면 `custom`으로 전환합니다.
- 위젯별 `display_style`은 콘텐츠 배치와 표시 형식을 위한 호환 설정입니다. 컨텍스트 메뉴에서는 `표시 형식`으로 분리하며, 공통 외관 프리셋과 서로 덮어쓰지 않습니다.
- 기존 사용자의 글꼴·색상·투명도 또는 `display_style` 값이 있으면 외관을 덮어쓰지 않고 `custom`으로 이관합니다. 외관 설정이 없는 새 위젯만 `midnight_glass`를 기본 적용합니다.
- 새 프리셋은 모든 위젯에서 의미가 같은 완결된 외관 토큰 세트로 추가하고, 특정 위젯의 시간/날짜/상태 표시 로직을 포함하지 않습니다.
- `pure_type`은 글자만 남기는 프리셋입니다. 배경과 테두리 알파를 0으로 저장하고 `background_type=transparent`로 그라데이션 합성도 차단하며, 조작 가능한 투명 영역은 기존 입력 표면 처리로 유지합니다.

### 공통 모양과 배치 편의 기능

- 모든 위젯은 표시 프리셋과 독립적인 `widget_shape=card|capsule|circle|poster` 값을 저장합니다.
- `card`는 기존 위젯/프리셋의 여백과 모서리를 보존합니다. 나머지 모양만 공통 비율과 여백을 적용합니다.
- 외관 탭은 색과 분위기를 직접 비교할 수 있는 프리셋 썸네일 갤러리를 제공합니다.
- `circle`과 `capsule`은 창 마스크를 적용해 투명 모서리를 실제 입력 영역에서도 제거합니다.
- 위젯 복제는 인스턴스 설정을 복사하고 위치만 `(24, 24)`만큼 이동합니다.
- 드래그 종료 시 `overlay_snap_enabled`가 켜져 있으면 화면과 다른 표시 위젯의 경계에 12px 이내로 맞춥니다.

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

### 날씨 일러스트 팩

- 번들 팩 레지스트리는 `presentation/widgets/weather_asset_packs.py`에서 관리합니다.
- 생성 에셋은 `Assets/weather/*-sprites.png`의 4×4 투명 스프라이트 시트로 포함합니다.
- 선택값은 인스턴스 설정 `weather_asset_pack`에 저장하며 `appearance_preset`과 `display_style`을 변경하지 않습니다.
- 상태 슬롯은 맑음 낮/밤, 구름 조금 낮/밤, 흐림, 안개, 이슬비, 비, 폭우, 눈, 폭설, 천둥, 우박, 알 수 없음의 14종입니다.
- MET Norway의 `_day`, `_night`, `_polartwilight` 접미사는 `_day_period`로 보존해 낮/밤 에셋 선택에 사용합니다.
- 에셋 로드에 실패하면 기존 qtawesome 날씨 아이콘으로 자동 대체합니다.

### 날짜·D-Day 장식 팩

- 번들 팩 레지스트리는 `presentation/widgets/moment_asset_packs.py`, 파일은 `Assets/moments`에서 관리합니다.
- 날짜 카드는 현재 월을 봄/여름/가을/겨울 장면으로 자동 매핑합니다.
- D-Day는 생일, 기념일, 마감, 출시, 여행, 학습, 건강, 축하, 차분함, 반짝임 장면을 선택합니다.
- 템플릿의 `{art|size=N}` 토큰은 선택한 장식 팩의 투명 PNG를 렌더링합니다.

### 런처 덱 키캡 배열

- 저장 데이터는 인스턴스 설정 `launcher_deck_data`의 JSON이며, 열·행·간격과 각 키의 위치, 크기, 스타일, 동작을 포함합니다.
- 기본 배열은 `regular_3x3`, `mixed_4x3`, `category_rows`, `keyboard_cluster`, `sidebar_tools`, `command_strip` 6종입니다.
- 키 크기는 1U·2U·3U·세로 1×2를 지원하고 `reflow_deck()`이 겹치지 않게 다시 배치합니다.
- 키캡 효과는 `air_glass`, `mechanical_pbt`, `soft_clay`, `arcade_glow`, `minimal_mono` 5종이며, 다중 선택 키에 스타일·크기·조합 패턴을 일괄 적용할 수 있습니다.
- 상세 꾸미기는 선택 키의 윗면·옆면·테두리·글자 색상, 깊이, 모서리, 글자 크기, 아이콘과 아이콘/라벨 배치를 초안에서 편집하고 실제 키캡 렌더러로 미리 봅니다.
- 번들 데칼은 `Assets/keycaps`의 투명 PNG 21종이며 `launcher_keycap_assets.py`에서 등록합니다. 기본 벡터 아이콘은 자동·없음을 제외한 33종을 제공합니다. 사용자는 PNG·JPG·JPEG·WebP·BMP·SVG 아이콘과 GIF·Animated WebP를 직접 선택할 수 있습니다.
- 데칼은 키마다 에셋 종류·농도·크기를 저장하며, 사용자 이미지가 없거나 로드되지 않으면 번들 에셋 또는 무장식 상태로 안전하게 대체합니다.
- 인터랙션 스튜디오는 실행 버튼·토글·누르는 동안 활성의 세 상태 모델과 떼기·즉시·더블·길게 누르기 트리거를 제공합니다. 토글 상태는 같은 인스턴스의 `launcher_deck_data`에 즉시 저장합니다.
- 키마다 누름·호버·활성·성공·실패 효과, 모션 속도, 결과 표시 시간, 활성/비활성 색상, 상태 표시점, 모션 최소화를 저장합니다. 상태는 `비활성 → 대기 → 눌림/실행 중 → 활성/성공/실패` 의미가 시각적으로 겹치지 않게 표현되어야 합니다.
- 움직이는 에셋은 항상·호버·누름·활성 상태·첫 프레임 재생 조건을 지원하고 위젯이 숨겨지면 정지합니다. 번들 피드백 사운드는 `Assets/keycaps/sounds`의 WAV 12종이며 무음·시스템음·사용자 WAV와 함께 선택합니다. 재생 시점과 음량을 키마다 저장하고 편집기에서 미리 듣습니다.
- 사용자 에셋은 선택 즉시 형식과 25MB 제한을 검증하고 `%LOCALAPPDATA%/kimhyojin/Dark Calendar/launcher_assets` 아래에 콘텐츠 해시 이름으로 복사합니다. 원본 이동·이름 변경이나 중복 등록이 위젯을 깨뜨리지 않아야 합니다.
- 키보드 Enter·Space 조작도 마우스와 동일한 트리거 및 상태 피드백을 사용합니다. `모션 최소화`에서는 흔들림·펄스·브리딩을 정적 강조로 대체합니다.
- 기본 스타일이나 조합 패턴을 다시 적용하면 기존 사용자 색상·형태·아이콘·데칼 덮어쓰기를 지워 선택 결과가 즉시 보이게 합니다.
- 기본 배열은 번들 PNG 데칼과 큰 벡터 아이콘을 중심으로 구성하고 텍스트는 보조 캡션으로 표시합니다. 사용자 PNG/GIF/Animated WebP는 같은 시각 계층과 재생 조건을 따릅니다.
- 덱 전체 이미지 모드는 한 장의 PNG·JPG·WebP·GIF를 현재 열·행과 각 키의 span에 맞춰 잘라 표시합니다. 배열이 바뀌면 같은 원본에서 crop을 다시 계산하며 아이콘/이름 오버레이는 사용자가 켜고 끌 수 있습니다.
- 아이콘 팩은 Glass Line, Neon Cyan, Violet Glow, Warm Sunset, Mono Ink를 제공하고, 같은 덱 안의 벡터 아이콘 색상과 표현 톤을 일관되게 적용합니다. 개별 키에서는 검색 가능한 기본 아이콘과 사용자 이미지/GIF를 계속 자유롭게 선택할 수 있습니다.
- 배열 템플릿 적용, 배열 편집 적용, 드롭으로 인한 배열 재배치 때는 이전 수동 크기 값을 해제하고 새 그리드의 콘텐츠 크기로 창을 다시 맞춰 좌우·상하 잔여 여백을 남기지 않습니다.
- 실행 동작은 프로그램·파일·폴더 열기, `http`/`https` 웹 주소, Windows 전역 단축키, 허용 목록의 Air Calendar 내부 명령으로 제한합니다. 단축키는 수정자와 영숫자·기능키·탐색키·미디어키를 검증한 뒤 전송합니다. 스크립트 확장자(`.bat`, `.cmd`, `.ps1`, `.vbs`, `.js`, `.wsf`)는 실행하지 않습니다.
- 위젯에 로컬 파일이나 웹 주소를 드롭하면 새 키로 추가하고 배열을 다시 정렬합니다.
- 배열 편집기는 초안에서만 변경하며 `적용`한 경우에만 인스턴스 설정에 저장합니다.

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
- 날짜 영역을 접으면 달력 위젯만 숨기지 않고 남은 섹션을 한 열로 재배치하고 창 자체를 축소합니다. 펼침/접힘 크기와 화면 좌표는 레이아웃별로 구분해 저장하며 다시 펼칠 때 기존 펼침 크기를 복원합니다.
- 월간 캘린더는 별도 불투명 패널처럼 보이지 않도록 셀 뷰포트를 투명하게 유지합니다. 요일 머리글과 선택일만 현재 스킨 색상을 낮은 알파로 합성하고, 주말은 고정 빨강 대신 스킨 강조색을 사용하며 글자/배경 불투명도 설정을 각각 따릅니다.
- 주간 날짜는 큰 타원형 캡슐 대신 작은 카드형 셀을 사용합니다. 기본/오늘/선택/호버/키보드 포커스 상태를 배경, 가는 테두리, 하단 강조선과 글자 굵기로 구분하며 현재 스킨과 글자·배경 불투명도 설정을 그대로 따릅니다.
- 보조 설명 설정은 모든 기본 배치와 미리보기에서 동일하게 동작합니다. 배치 내부 기본값 때문에 사용자가 켠 설정을 다시 숨기지 않습니다.
- 일정 강조 마커는 카드 위쪽이 아니라 제목 왼쪽 중앙에 맞춥니다. 주요 추가 버튼의 기본/호버/누름 상태는 모두 배경과 대비되는 글자색을 보장합니다.
- 목록 밀도는 `widget_mode_density=compact|standard|comfortable`로 저장합니다. 글꼴/글자 크기/불투명도/배치 설정은 변경하지 않고 행 여백과 시간 배치만 조절합니다. 빠른 메뉴에서는 즉시 저장, 꾸미기에서는 초안 미리보기 후 적용/취소합니다.
- 행마다 반복되는 일정/업무 유형 설명은 표시하지 않습니다. 전체 보기에서는 그룹 제목으로 구분하고 일정 필터에서는 중복 그룹 제목도 생략합니다. 원본 데이터와 ID, 완료/편집 동작은 유지합니다.
- `side_panel_renderer.load_right_panel()`은 패널 검색/상태 필터를 적용하기 전의 원본 업무 데이터를 `_latest_directive_data`로 게시해야 합니다. 메인 창이 숨겨진 상태에서도 위젯이 이 데이터를 받아야 합니다.
- 일부 데이터가 지연되어도 이미 불러온 일정/업무는 지우지 않습니다. 지연 안내와 재시도 동작을 목록 안에 함께 표시합니다.
- 목록에는 원본 `item_id`와 `source=task|directive`를 함께 전달합니다. 완료는 기존 상태 변경 처리기의 성공 응답 후 반영하며, 최근 상태 변경을 실행 취소할 수 있습니다.
- 지시·협조 생성은 일반 태스크 다이얼로그의 `task_type`으로 우회하지 않고 전용 `open_directive_dialog()` 경로를 사용합니다. 추가 메뉴와 더 보기 메뉴에서는 지시·협조 관리 및 전체 업무 관리로 이동할 수 있어야 합니다.
- 통합 목록은 일정/업무/지시·협조 필터를 독립 제공하고, 항목의 빠른 메뉴에서 열기·완료·우선순위·삭제를 기존 메인 창 처리기에 위임합니다. 읽기 전용 구독 일정에는 변경·삭제 동작을 제공하지 않습니다.
- 필터와 실행 버튼은 의미상 분리합니다. 넓은 폭에서는 한 줄, 중간 폭에서는 두 줄, 초소형 폭에서는 현재 선택값이 보이는 메뉴형 필터로 전환하며 필터 이름을 `…`로 대체하지 않습니다.
- 목록 상단에는 현재 필터의 제목을 표시합니다. 완료 항목 노출은 주요 실행 버튼이 아닌 `완료 포함` 보조 필터로 제공하고, 완료된 행에는 취소선뿐 아니라 명시적인 완료 상태 배지를 함께 표시합니다.
- 오늘의 지시·협조 목록에는 오늘 마감뿐 아니라 미완료 상태의 기한 경과 및 기한 없음 항목을 별도 구역으로 표시합니다.
- 불러오는 중과 불러오기 지연은 빈 목록과 구분합니다. 목록 개수 제한으로 항목을 생략하지 않습니다.
- 목록 교체 시 기존 행을 즉시 숨긴 후 지연 삭제합니다. 스크롤 내부 레이아웃의 최소 높이를 유지하여 작은 창에서 행이 겹치지 않게 합니다.
- 회귀 검증: `tests/test_widget_mode_ux.py`, `tests/test_unified_widget_mode.py`, `tests/test_widget_mode_coordinator.py`, `tests/test_widget_mode_geometry.py`.
- 밀도/압축 헤더/타이포그래피 회귀 검증: `tests/test_widget_mode_efficiency.py` (설정 재로드, 초안 취소, 역할별 글자 비율, 큰 글꼴·작은 창 포함).

### 자유 구성 편집

- 프리셋은 `widget_mode_layout`에 유지합니다. 표시 방식은 별도 `widget_mode_layout_mode=preset|free`, 자유 구성은 `widget_mode_free_layout`의 version 1 JSON으로 저장합니다. 프리셋 선택은 자유 구성을 삭제하지 않습니다.
- 모델과 검증: `widget_free_layout.py`. 캔버스 논리 좌표와 요소별 `enabled` / `[x,y,width,height]`, 선택적 8px 정렬 `snap`, `calendar_mode=week|month`를 저장합니다. version 1의 선택 필드 `order`(뒤에서 앞으로)와 요소별 `locked`를 지원하며 이전 파일의 누락값은 기본 순서·잠금 해제로 채웁니다. 알려지지 않은 요소·중복·유효하지 않은 버전/좌표는 거부하고 범위 밖 좌표는 캔버스 안으로 제한합니다. 읽기는 설정을 변경하지 않습니다.
- 구성 요소는 날짜, 시계, 달력, 통합 목록 필터, 통합 목록, 일정 목록, 업무 목록, 지시·협조 목록입니다. 사용자가 선택하지 않은 요소를 강제로 표시하지 않습니다. 전체 해제와 의도한 겹침도 허용합니다.
- `WidgetFreeLayoutEditorDialog`는 독립 초안과 실제 네이티브 위젯 렌더링을 사용합니다. 현재 위젯의 항목·선택 날짜·필터·시계 표시를 읽기 전용으로 반영하며 현재 항목이 없으면 빈 목록을 그대로 표시합니다. 캐시가 없는 호출에서만 예시 항목을 사용합니다. 미리보기는 원본 데이터 처리기·DB를 호출하지 않습니다.
- 미리보기 위에서 선택·드래그 이동·8방향 크기 조절을 합니다. Ctrl·Shift 다중 선택, 빈 영역 드래그 선택, 선택/호버 윤곽, 선택 이름·잠금 배지를 제공합니다. 수치 입력·정렬·간격 맞춤·순서·잠금과 글꼴·스킨·불투명도는 공통 실행 취소/다시 실행 기록을 사용하며 적용 전 실제 설정/창 좌표를 변경하지 않습니다. 잠긴 요소는 이동·크기 조절·Delete 숨기기에서 제외합니다.
- Alt는 격자·요소 맞춤을 건너뛰며 방향키는 1px, Shift+방향키는 10px 이동합니다. 10~200% 확대와 화면 맞춤은 편집 화면에만 적용합니다. 입력 위의 휠은 편집기 설정 영역을 스크롤합니다.
- 구성 파일 `.airlayout.json`은 배치·요소 표시·순서·잠금만 저장하며 모양 설정은 포함하지 않습니다. 불러오기는 한 번의 초안 변경으로 기록합니다. 파일 크기 제한과 검증 후 원자적으로 저장하며 설정/원본 파일을 먼저 지우지 않습니다.
- 사용자 프리셋은 `widget_layout_presets.py`에서 관리합니다. `widget_mode_user_layout_presets`의 version 1 JSON에 `{id,name,layout}` 목록을 저장하고 `widget_mode_user_layout_id`는 선택한 프리셋을 가리킵니다. 기본 grid 배치 레지스트리와 분리하며 각 `layout`은 자유 구성 검증을 통과해야 합니다. 색상·글꼴과 실제 데이터/창 위치는 프리셋에 포함하지 않습니다.
- 이름은 앞뒤 공백을 정리한 1~80자, 대소문자 무시 중복 금지이며 ID는 UUID입니다. 최대 100개, JSON 2MiB를 제한합니다. 읽기·CRUD는 분리된 데이터를 반환하며 손상/미래 버전 읽기는 원본 설정을 덮어쓰지 않습니다.
- 구성 편집기의 `내 배치`에서 새 저장·선택 프리셋 덮어쓰기·이름 변경·삭제를 합니다. 이 변경도 공통 실행 취소와 적용/취소 흐름에 포함합니다. `preset_id`로 명시적 프리셋 수정 화면을 열면 적용 시 그 프리셋의 배치를 갱신합니다. 새 이름으로 저장하거나 삭제한 경우 원래 프리셋을 다시 만들거나 덮어쓰지 않습니다.
- 꾸미기의 `내 배치`는 썸네일 목록과 수정·이름 변경·삭제를 제공합니다. 중첩 구성 편집기 적용은 부모 초안에만 반영하고 부모 적용에서 영구 저장합니다. 기본 배치로 전환해도 사용자 프리셋 목록은 유지하며 선택 ID만 해제합니다. 프리셋 삭제는 현재 자유 구성 좌표를 지우지 않습니다.
- 런타임 `FreeLayoutCanvas`는 저장 좌표의 비율로 배치합니다. 작은 창에서 데이터 요소 내용은 내부 스크롤, 날짜/시계는 글꼴 맞춤으로 표시하며 전체 내용은 도움말/접근성 이름에도 제공합니다. 좁은 창에 여러 열을 배치하면 각 요소의 조작부에 내부 스크롤이 필요할 수 있습니다.
- 유형별 목록은 기존 캐시·원본 ID·처리기를 공유합니다. 통합 목록 필터는 통합 목록에만 적용합니다. 통합 목록과 유형별 목록을 함께 표시할 수 있으며 원본 데이터 복제나 별도 완료 저장은 하지 않습니다.
- 자유 구성의 창 좌표·크기는 `free` 키로 분리합니다. 달력 요소의 표시 여부로 창 좌표 키를 바꾸지 않습니다. 꾸미기의 글꼴/색상/달력·시계 표시를 적용해도 명시적으로 프리셋을 선택하기 전에는 자유 구성을 유지합니다.
- 주간 버튼은 동일 너비이며 요일/날짜를 별도 타이포그래피로 그립니다. 선택일은 은은한 배경과 짧은 강조선, 오늘은 점, 키보드 포커스는 윤곽선으로 구분하며 글자/배경 불투명도를 따릅니다.
- 회귀: `test_widget_free_layout_model.py`, `test_widget_free_layout_editor.py`, `test_widget_free_layout_runtime.py`, `test_widget_week_strip.py`, `test_widget_layout_editor_canvas.py`, `test_widget_layout_editor_preview.py`, `test_widget_layout_editor_advanced.py`. 화면 검증: `scripts/validate_widget_free_layout.py`, `scripts/validate_widget_layout_editor_advanced.py`.
- 프리셋 회귀: `test_widget_layout_presets.py`, `test_widget_layout_presets_editor.py`, `test_widget_layout_presets_controller.py`, `test_widget_layout_presets_customization.py`. 화면·임시 INI 재시작 검증: `scripts/validate_widget_layout_presets.py`.

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
