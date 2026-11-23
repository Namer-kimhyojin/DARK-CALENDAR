# 오버레이 위젯 시스템 규칙

## 통합 작업 공간·갤러리·배치·자동 전환·스택

- 문서 검증·시간 규칙·배치 계산·일정 캘린더 범위는 `domain/widget_workspace.py`, Qt 실행은 `widget_workspace_runtime.py`로 나눕니다. manager의 `workspace_service()`를 공유하며 신규 app 상태 변수는 추가하지 않습니다.
- `widget_studio_state`는 표시·외관·배치·전용 모드 구성과 선택적 규칙/스택만 저장합니다. 인스턴스 설정은 widget의 `_get`·`_set`·기존 proxy로 접근합니다. 본문·목표·스톱워치 실행·날씨 요청 데이터·자유 구성 프리셋 목록·인증 값은 복원 대상으로 복사하지 않습니다.
- 일반 작업 공간 적용과 되돌리기는 모드 실행 여부를 유지합니다. 저장 모드로 열기만 기존 coordinator를 통해 이동합니다. 적용 실패는 직전 상태로 복원하며 삭제된 인스턴스는 재생성하지 않습니다.
- 미리보기는 기존 위젯의 읽기 전용 제한 크기 렌더링입니다. 뷰포트 주변만 갱신하고 화면 밖 아이콘·캐시·선택 미리보기 타이머를 제한합니다. 초안은 적용 전 실제 창에 쓰지 않습니다.
- 배치 편집은 잠금을 존중하며 적용 시 화면 범위·도형 비율·KeyDeck 비율을 기존 helper로 제한합니다. KeyDeck은 외관만 제자리 갱신하며 바인딩·음악 동작을 새 덱 초기화로 덮어쓰지 않습니다.
- 자동 전환은 명시적으로 켜고 위쪽 일치 규칙을 먼저 적용합니다. 자정 넘는 구간은 시작 요일 기준, 같은 시작/종료는 선택 요일 전체입니다. 직접 전환 후 한 시간과 모달 편집 중에는 대기합니다. 기존 일정 캐시 안에서만 캘린더 범위를 필터링합니다.
- 스택은 기존 네이티브 창을 재사용하고 다른 페이지는 사용 설정을 끄지 않고 숨깁니다. 대기는 관리창에서 구분합니다. 회전·전체 화면·규칙·시스템 움직임 정책은 단일 서비스 타이머로 처리합니다. 스택 변경 저장은 150ms 병합하고 종료 시 마칩니다.
- 통합 정적/일시정지 정책은 날씨·공통 그래픽·KeyDeck 장식만 제어합니다. KeyDeck 키 입력·스위치 소리·GIF 재생 조건과 Windows 절전·움직임 설정을 함께 확인합니다.
- 회귀: `tests/test_widget_workspace_model.py`, `tests/test_widget_workspace_studio.py` 및 기존 위젯·KeyDeck·mode 테스트. 화면 검증: `scripts/validate_widget_workspace_studio.py`. [구현·사용법·근거](../docs/ux-audit/widget-workspace-studio-20261101.md).

## 위젯 통합 관리창

- `overlay_manager_dialog.py`는 바탕화면 위젯과 위젯 전용 모드를 관리하는 비모달 허브입니다. 갤러리·전용 모드 패널은 `widget_management_ui.py`, 추가 의미 기반 스타일은 `widget_management_styles.py`에 둡니다.
- 검색·표시 필터는 현재 인스턴스의 메모리 목록만 조회하고 설정에 저장하지 않습니다. 전체 표시·숨김·삭제의 범위는 검색 결과와 관계없이 전체 인스턴스이며 삭제는 기존 확인 경로를 유지합니다.
- manager 알림은 단발 타이머로 병합하고 ID별 행을 재사용합니다. 편집 중 이름·스크롤을 보존하고 숨김·Esc·닫기에서 타이머와 listener를 해제합니다.
- 추가 갤러리는 수락할 때만 인스턴스를 생성합니다. 관리창 테마 토큰을 공유하고 밝은/어두운 테마·100%/200% 배율에서 카드 글자를 확인합니다.
- 전용 모드 편집은 `controller.ensure_widget()`로 숨긴 창만 준비합니다. 실행·복귀는 기존 coordinator를 통하며 트레이 복원 요청과 현재 창 표시 여부를 함께 읽습니다. 편집기 취소가 모드 진입이나 resume 저장으로 이어지면 안 됩니다.
- 회귀: `tests/test_widget_management_hub.py`. 화면 검증: `scripts/validate_widget_management.py`. [벤치마킹·사용법·검증](../docs/ux-audit/widget-management-hub-20261101.md).

## 위젯 전용 모드 화면 형태와 표면 모양

- 배치는 `stacked`(세로형)·`dashboard`(좌우형)·`work_board`(보드형)·`minimal`(목록형) 4종, 표면 모양은 `card`·`line`·`outline`·`compact` 4종(`widget_mode_surfaces.py`, 설정 `widget_mode_surface`)입니다. 색상은 메인 테마를 따르고 표면 모양은 모서리와 항목 테두리·배경만 바꿉니다. 이전 스킨 16종(`widget_mode_skin`)과 옛 배치 설정은 시작 시 한 번 이관합니다.
- `WidgetModeLayout`의 `calendar_mode`, `show_overview`, `searchable`은 배치별 표시 설정의 기본값일 뿐입니다. 실제 표시는 배치마다 `widget_mode_calendar_style_<id>`(`week`/`month`)·`widget_mode_show_overview_<id>`·`widget_mode_search_pinned_<id>`가 정하고(`widget_mode_display.py`의 `read_layout_display()`, 꾸미기 ▸ 표시 항목의 '선택한 배치'), 키가 없을 때만 배치 정의를 씁니다. `responsive_breakpoint`, `presentation`은 표시 방식을 정의합니다. `widget_layout_calendar_mode(layout, width, display)`, `widget_layout_is_compact()`, `widget_layout_has_columns()`로 UI·필터·크기 복원 판단을 일치시킵니다. 좁은 창에서도 저장된 배치 ID는 유지합니다.
- 표면 모양은 `WidgetModeSurface`(반지름·항목 반지름·항목 배경 `card|transparent`·항목 테두리 `full|bottom`)로 정의하며 `widget_workspace_styles.py`가 QSS에 합성합니다.
- 보드는 기존 `FreeAgendaPanel`·`AgendaItemWidget`과 원래 controller의 수정·완료·읽기 전용 흐름을 공유합니다. 보드 표시 중 숨겨진 일반 목록의 행을 중복 생성하지 않습니다.
- 검색은 선택일 캐시에서만 수행하고 입력을 120ms로 모읍니다. 검색어 지우기는 즉시 반영하며, 숨김에서 타이머를 멈춥니다. 검색어를 QSettings에 저장하거나 검색 때문에 새 DB/외부 요청을 만들지 않습니다.
- 꾸미기는 실제 렌더러의 격리 미리보기·초안·적용/취소 계약을 유지합니다. 새 배치 카드는 표시 항목만 모아 재배치하고 표면 모양 선택과 동기화합니다. 저장한 자유 구성·프리셋을 삭제하거나 표면 모양 선택 때문에 기본 배치로 바꾸지 않습니다.
- 회귀: `tests/test_widget_workspace_redesign.py`, 기존 widget-mode/free-layout/preset/opacity/geometry 테스트. 화면 검증: `scripts/validate_widget_workspace_redesign.py`. [벤치마킹·사용법](../docs/ux-audit/widget-workspace-redesign-20261101.md).

### 설정 이관

- `widget_mode_migration.py`의 `migrate_widget_mode_settings()` 하나가 옛 배치 11종·스킨 16종·사용자 배치(`user_layout_*`) 설정을 새 4종 카탈로그로 옮깁니다. 위젯 창을 처음 만들기 전(`UnifiedWidgetController.ensure_widget()`)과 작업 공간 프로필 복원 직후(`WidgetWorkspaceService._restore_mode()`)에 부릅니다.
- 멱등입니다. 값이 다를 때만 쓰므로 같은 설정에 다시 돌리면 아무것도 쓰지 않고 `False`를 돌려줍니다.
- 옛 키를 지우지 않습니다. 다시 쓰는 키는 `widget_mode_layout` 하나이며 옛 값은 `widget_mode_layout_legacy`에 남깁니다. 옮긴 배치의 창 위치·크기(`unified_widget_geometry_<id>`, `unified_widget_size_<id>`와 각 `_calendar_hidden`)와 달력 접기 상태(`widget_mode_calendar_visible_<id>`)는 새 ID 키로 복사합니다. 1단계 전에 보드형이던 옛 ID(`dashboard`·`magazine`·`month_focus`·`side_planner`)는 자기 접기 키가 없으면 달력을 펼친 상태로 옮깁니다(옛 앱의 기본값, `widget_mode_show_week` 미러를 따르지 않음). 배치별 표시 키는 비어 있을 때만 채웁니다.
- 예외 안전입니다. 두 호출부 모두 실패를 기록하고 창 생성·복원을 계속합니다. 손상된 `widget_mode_styles.json`(`placements`가 목록이 아니거나 항목이 잘못됨)은 배치 없음으로 보고 이관을 계속합니다. 사용자 배치의 `calendar_mode`가 `auto`이거나 없으면 주간입니다.
- 작업 중인 자유 구성(`widget_mode_free_layout`)이 내 배치 어느 것과도 같지 않으면 '이전 자유 구성'으로 추가합니다. 추가했거나 이미 내 배치와 같았던 자유 구성의 지문(정렬한 JSON의 SHA-256, 최근 50개, JSON 문자열)을 `widget_mode_preserved_free_layouts`에 남겨, 사용자가 그 항목을 지운 뒤 다시 추가하지 않습니다. 꾸미기 적용으로 내 배치가 지워지면 지운 항목의 구성 지문도 같은 키에 남깁니다(`remember_handled_free_layouts()`, 취소하면 남기지 않음). 이 키는 작업 공간 `MODE_KEYS`와 `mode_setting_allowed()` 접두어 밖에 있어 프로필 복원이 지우지 않습니다. 다른 자유 구성을 담은 옛 스냅샷을 복원하면 그 구성은 보존합니다.
- `widget_mode_show_week`는 이전 버전 호환을 위해 배치별 접기 키와 함께 계속 씁니다(계획서 5절과 다른 구현 판단).
- `read_widget_mode_surface()`는 `widget_mode_surface`가 비어 있으면 `widget_mode_skin`을 `SKIN_SURFACES`로 읽기만 합니다(쓰지 않음). 첫 창을 만들기 전 위젯 관리자도 이관 뒤와 같은 표면 모양을 보여 줍니다.
- 회귀: `tests/test_widget_mode_migration.py`, `tests/test_widget_mode_surfaces.py`.

## 그래픽 컬렉션

- `widget_graphics.py`는 공통 렌더러, `widget_graphic_runtime.py`는 인스턴스 설정·원복, `widget_graphic_dialog.py`는 쓰기 없는 미리보기를 담당합니다. `widget_graphic_catalog.py`는 공통 3종과 위젯별 디자인 ID를 정의하고, `widget_graphic_layouts.py`는 추가 배치를 그립니다.
- `graphic_collections(kind)`는 해당 종류에서 선택 가능한 항목을 반환합니다. 신규 ID는 `<kind>_<layout>`이며 `slot`으로 같은 계열을 연결합니다. 전체 적용은 `collection_for_kind()`로 각 위젯에 맞는 ID를 선택합니다. 기존 공통 3개 ID는 변경하지 않습니다.
- 날씨의 추가 디자인은 숨겨진 정적 `WidgetGraphicSurface`로 공통 배치를 재사용하고 원래 `WeatherSceneSurface`에서 움직이는 그림·시간별 예보를 그립니다. 정적 보조 표면에는 런타임 타이머나 네트워크를 추가하지 않습니다.
- 기본값과 기존 저장 설정은 유지합니다. 컬렉션은 사용자가 적용할 때만 활성화하며 기본 적용 범위는 현재 위젯입니다. 전체 적용은 표시 중인 인스턴스에만 전달합니다.
- `graphic_collection`, `graphics_template`, `graphics_backup`, `graphics_applied`, `graphics_font_reference`는 기존 인스턴스 prefix 안에서 저장합니다. 복원은 현재 값이 컬렉션 적용값과 같은 외관 필드에만 적용하여 이후 사용자 편집을 보존합니다.
- 사용자 글꼴·크기·전체 불투명도·본문·목표·위치·키 동작은 컬렉션 선택으로 변경하지 않습니다. 별도 표시 형식이나 전용 디자인의 명시적 선택을 우선합니다.
- 일반 위젯의 상태 전환은 180ms이며 숨김·비활성화·움직임 끔에서 중단합니다. 별도 상시 타이머를 추가하지 않습니다. 날씨의 기존 움직임·절전 정책을 재사용합니다.
- 디지털 시계 우클릭 → `플립북 시계`는 `clock_flipbook` 컬렉션을 엽니다. 시계가 갱신될 때 바뀐 숫자만 중앙 축으로 360ms 동안 접힙니다. 시간대 변경 등 시간 차이가 크게 생기면 현재 시각을 즉시 표시합니다.
- 시계 우클릭 → `투명 플립북`은 벚꽃·오로라·별빛 디자인을 제공합니다. 숫자 카드 바깥은 투명하고 `Assets/flipbook`의 GIF를 숫자 전환과 함께 그립니다. 정지 중에는 첫 프레임을 사용하며, 별도 재생 타이머 없이 위젯 공통 움직임 정책을 따릅니다.
- 카운트다운 진행률은 `cd_duration_target`과 현재 목표가 같고 `cd_duration_seconds`가 양수일 때만 표시합니다. 기존 사용자 목표의 시작 길이를 임의로 추정하지 않습니다.
- KeyDeck 컬렉션은 시각 속성만 복사·적용합니다. 키 동작·그림·레이아웃·크기·비트메이커의 사운드 키 의미 색상을 보존합니다.
- 회귀: `tests/test_widget_graphic_collections.py`, `tests/test_widget_graphic_designs.py`. 실제 소스 화면: `scripts/validate_widget_graphic_collections.py` (`--all-designs`로 종류별 추가 10종). [기본 컬렉션](../docs/ux-audit/widget-graphic-collections-20261101.md), [추가 디자인](../docs/ux-audit/widget-graphic-designs-20261101.md).

## 위젯 종류 (9종)

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
| `loop_deck` | `OverlayLoopDeckWidget` | `overlay_loop_deck.py` |

## 내용 프리셋과 미리보기

- 7종 내용 프리셋은 `widget_presets.json`과 `overlay_base._PRESET_FALLBACK`에 같은
  76개 항목을 유지합니다. KeyDeck의 배치·테마 카탈로그는 별도 기존 경로를 사용합니다.
- 고급 설정의 프리셋 목록은 실제 렌더러와 현재 위젯 외관을 이용한 네이티브 썸네일을
  제공합니다. 미리보기용 frame·label에는 설정·타이머·네트워크 객체를 추가하지 않습니다.
- 기본 프리셋은 고정하며 사용자 프리셋의 새 저장·수정·이름 변경·삭제 흐름을 유지합니다.
- 새 위젯의 설정 키가 없을 때 기본 템플릿을 사용하고, 사용자가 명시적으로 비운 템플릿은
  기본 표시 모드로 전환합니다. 빈 문자열을 기본 템플릿으로 다시 치환하지 않습니다.
- 밝은 설정창에서도 위젯의 흰 글자가 보이도록 미리보기 배경은 위젯 배경과 공통
  데스크톱 샘플을 합성합니다. 오류 안내는 일반 텍스트와 줄바꿈으로 표시합니다.
- 다이얼로그 초안의 필드 참조는 확인·취소·예외 시 해제하고 미리보기 타이머를 멈춥니다.
  일러스트 초안은 임시 미리보기 크기 문맥에서만 읽으며 실제 위젯 tick은 저장값을 사용합니다.
- 검사: `test_widget_preset_preview.py`, `test_widget_preset_validation.py`,
  `test_widget_preset_rendering.py`, `test_widget_preset_contracts.py`,
  `test_overlay_template_runtime_bounds.py`, `test_overlay_template_validation.py`.

## 날짜 카드의 움직이는 GIF

- 날짜 카드 우클릭 → `움직이는 GIF 꾸미기`에서 내장 6종을 미리 보고 현재 인스턴스에 적용합니다. `표시 형식`에서 다른 형식을 선택하면 저장한 템플릿과 외관을 다시 사용합니다.
- `display_style=animated`, `datecard_animation`, `datecard_animation_motion`은 인스턴스 설정입니다. 기존 카드의 기본값은 유지하고, 작업 공간의 외관 저장·복원에 포함합니다.
- `datecard_animations.py`는 `Assets/date_animations`의 GIF 위에 날짜를 합성하지 않고 별도 텍스트로 그립니다. GIF는 QMovie의 전체 프레임 캐시를 사용하지 않으며 숨김·비활성화·움직임 정책에서 재생을 멈춥니다.
- 회귀: `tests/test_datecard_animations.py`. 격리된 화면 검증: `scripts/validate_datecard_animations.py`.

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
manager.instance_records()             # → [(id, name, type, enabled), ...] 위젯을 만들지 않음
manager.live_instances()               # → 이미 만든 위젯만 [(id, name, type, widget), ...]
manager.restore_all()                  # 앱 시작 시 호출, 꺼 둔 인스턴스는 처음 쓸 때 만든다
manager.save_all()                     # 앱 종료 시 호출 (변경 시 자동 저장)
manager.refresh_theme()                # 테마 적용 후 호출 — 이미 만든 위젯만 다시 그림
```

**영속화**: QSettings `"overlay_instances"` 키에 JSON으로 저장.

- 꺼 둔(`enabled=false`) 저장 인스턴스는 시작할 때 만들지 않고 `_pending`에 둡니다. 저장 목록과 `instance_records()`에는 그대로 남습니다. `show_instance`·`toggle_instance`·`get_widget`·`all_instances`·`instances_of`(그 종류만)·`duplicate_instance`(원본)·`show_all`에서 처음 만들고, `hide_instance`·`hide_all`·`remove_instance`·`rename_instance`는 만들지 않습니다. `widget_registry()`는 Text 템플릿이 값을 읽는 스톱워치·카운트다운·D-Day만 만들고, `refresh_all_texts()`는 그 단계에서 갱신할 Text 위젯이 있을 때만 registry를 만듭니다. 켜진 Text 위젯이 있으면 시작 직후 첫 갱신에서 이 세 종류가 만들어집니다. 시작·배경 경로(위젯 메뉴, 첫 실행 판단, 스택 복원·이름, 작업 공간 런타임, 자리비움 해제, 루프 믹서 입력 목록)는 `instance_records()`/`live_instances()`를 써서 숨긴 위젯을 만들지 않습니다. 단, 스택 멤버는 `stacks.refresh()`가 `get_widget()`으로 가져오므로 꺼 둔 멤버도 시작할 때 만들어집니다(스택을 만들 때 멤버를 켜므로 드묾). 새 코드에서 이름·종류·켜짐만 필요하면 `instance_records()`, 이미 만든 위젯만 필요하면 `live_instances()`를 쓰고, `all_instances()`는 모든 위젯이 실제로 필요할 때만 씁니다. 나중에 만든 위젯은 현재 고정 상태를 받고, `shutdown()` 뒤에는 만들지 않습니다. 만들기에 실패하면 시작 시 복원 실패처럼 저장 목록에서 빼고 리스너에 알려, 관리 허브(갤러리 포함)가 그 행을 바로 지웁니다. 관리 허브·갤러리·바탕화면 배치 대화상자·작업 공간 저장/적용·스택 만들기는 모든 위젯을 만들므로, 세션에서 허브를 처음 열 때 숨긴 위젯 수만큼 느려집니다. 회귀 검증: `tests/test_overlay_lazy_disabled_restore.py`.

## 설정 prefix 규칙

```
인스턴스 ID:    clock_0
설정 prefix:   oi_clock_0_
설정 키 예:    oi_clock_0_font_size
               oi_clock_0_tz_offset_mins
```

`_SettingsProxy`를 통해 접근 — 직접 `QSettings`에 접근하지 말 것.

- 앱 전체 설정(테마 색·글자 테마·패널 기본색·글자 불투명도·dialog token·타이포그래피)은 `_real_settings()`로 읽습니다. proxy(`_s()`)로 읽으면 `oi_clock_0_theme_color`처럼 접두사가 붙어 항상 기본값이 됩니다. 인스턴스 키만 `_get`·`_set`·proxy로 접근합니다. 회귀 검증: `tests/test_overlay_app_theme.py`.

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
4. `overlay_widgets.py`의 `__getattr__`에 새 클래스 이름의 정적 import 분기를 추가합니다. 위젯 모듈은 그 종류를 처음 만들 때(`_create_widget`) 불러오고, 위젯 메뉴는 열릴 때(`aboutToShow`) 다시 만듭니다. 회귀 검증: `tests/test_overlay_lazy_widget_import.py`.

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
- 시계·스톱워치·날짜 카드·카운트다운·D-Day·텍스트·날씨 7종 위젯은 같은 순서와 같은 값의 13개 디자인 프리셋을 제공합니다. 런처 덱(KeyDeck)은 케이스·키캡 테마와 KeyDeck Studio를 사용하며 공통 표시 프리셋 메뉴를 노출하지 않습니다.
- 프리셋은 글꼴 후보, 글자색, 배경색, 테두리색, 각 색상의 알파, 여백, 모서리와 테두리 형태를 한 번에 적용합니다.
- 선택값은 인스턴스 설정의 `appearance_preset`에 저장합니다. 개별 색상·글꼴·투명도를 직접 바꾸면 `custom`으로 전환합니다.
- 위젯별 `display_style`은 콘텐츠 배치와 표시 형식을 위한 호환 설정입니다. 컨텍스트 메뉴에서는 `표시 형식`으로 분리하며, 공통 외관 프리셋과 서로 덮어쓰지 않습니다.
- 기존 사용자의 글꼴·색상·투명도 또는 `display_style` 값이 있으면 외관을 덮어쓰지 않고 `custom`으로 이관합니다. 외관 설정이 없는 새 위젯만 `pure_type`을 기본 적용합니다.
- 새 프리셋은 모든 위젯에서 의미가 같은 완결된 외관 토큰 세트로 추가하고, 특정 위젯의 시간/날짜/상태 표시 로직을 포함하지 않습니다.
- `pure_type`은 글자만 남기는 프리셋입니다. 배경과 테두리 알파를 0으로 저장하고 `background_type=transparent`로 그라데이션 합성도 차단하며, 조작 가능한 투명 영역은 기존 입력 표면 처리로 유지합니다.
- 템플릿 색 별칭(`accent`·`muted` 등), 날짜 카드의 강조·토·일 색, 저장 색이 없는 날짜 카드의 글자·바탕·테두리는 앱 테마를 따릅니다(`_overlay_theme_snapshot`). 기본은 앱 테마 그대로입니다. 위젯 글자 톤(lightness ≥ 0.5면 밝음)과 앱 테마의 기본 글자(글자 불투명도 적용 후 `text_primary`) 톤이 반대일 때만 위젯 글자 톤에 맞는 글자 테마의 읽기·상태 역할을 씁니다. 밝은 글자 위젯은 라이트 모드(`text_theme=light`, 시스템이 라이트일 때의 `auto`, 어두운 custom 글자 테마)에서 다크 모드(`text_theme=dark`) 역할을, 어두운 글자 프리셋(Pearl Mist·Paper Ivory)은 다크 모드·밝은 custom 글자 테마에서 라이트 모드(`text_theme=light`) 역할을 씁니다(흐린 글자 대비 약 1.0 → 4.3). 이때 사용자 강조색은 유지하고, 계열 강조색(`appearance_accent_source=family`)은 그 톤 쪽 값을 씁니다. 프리셋이 저장한 글자·배경·테두리 색은 덮어쓰지 않으며, 주간 띠의 평일 칸은 이 스냅샷의 `text_primary`를 씁니다.
- 테마를 적용하면(`apply_theme_settings`) `overlay_manager.refresh_theme()`가 이미 만든 위젯(`_widgets`)의 `_apply_appearance()`만 다시 실행하고, 만든 텍스트 위젯이 있으면 `refresh_all_texts()`를 fast·med·slow 단계로 한 번씩 불러 `{task_count}` 같은 실시간 값을 다시 넣습니다. 위치·크기는 유지하고, 한 위젯에서 예외가 나면 로그만 남기고 나머지를 계속하며, 종료(`shutdown`) 뒤에는 실행하지 않습니다. 아직 만들지 않은 숨은 위젯은 처음 만들 때 현재 테마를 받습니다. 런처 덱(KeyDeck)은 앱 테마를 읽지 않습니다. 회귀 검증: `tests/test_overlay_app_theme.py`.

### 공통 글자 그림자

- 구현은 `presentation/widgets/overlay_shadow.py`에서 공유합니다. 일반 7종의 QLabel과 날짜 카드의 월간 표에 적용하며 KeyDeck의 자체 그림자는 유지합니다.
- 인스턴스 prefix 안에 `text_shadow_enabled`, `text_shadow_opacity`(0–100), `text_shadow_blur`(0–20px), `text_shadow_distance`(0–12px), `text_shadow_color`를 저장합니다. 외관 설정이 없는 새 위젯은 글자 그림자를 기본으로 켭니다. 기존 외관과 명시적인 그림자 끄기 설정은 유지하며, 기존 위젯에 그림자 설정이 없으면 꺼짐으로 읽습니다.
- 외관 프리셋·콘텐츠 형식·템플릿과 독립적이며 프리셋 전환, 복제와 재시작에서도 값을 보존합니다.
- 위젯 우클릭 → 외관에서 켜기/끄기와 그림자 설정을 제공하고 일반 설정의 외관 탭에도 같은 조절 UI를 사용합니다. 설정창은 미리보기만 변경하고 저장 시 반영하며 취소는 아무것도 저장하지 않습니다.
- 그림자는 최상위 투명 창이나 face에 적용하지 않습니다. 자식 콘텐츠 효과를 재사용하고 흐림과 거리만큼 내부 여백을 확보해 테두리·배경·입력 영역과 모양 마스크를 유지합니다.

### 공통 모양과 배치 편의 기능

- 모든 위젯은 표시 프리셋과 독립적인 `widget_shape=card|capsule|circle|poster` 값을 저장합니다.
- `card`는 기존 위젯/프리셋의 여백과 모서리를 보존합니다. 나머지 모양만 공통 비율과 여백을 적용합니다.
- 외관 탭은 색과 분위기를 직접 비교할 수 있는 프리셋 썸네일 갤러리를 제공합니다.
- `circle`과 `capsule`은 창 마스크를 적용해 투명 모서리를 실제 입력 영역에서도 제거합니다.
- 위젯 복제는 인스턴스 설정을 복사하고 위치만 `(24, 24)`만큼 이동합니다.
- 드래그 종료 시 `overlay_snap_enabled`가 켜져 있으면 화면과 다른 표시 위젯의 경계에 12px 이내로 맞춥니다.
- 크기 조절은 네 모서리와 네 변에서 제공합니다. `widget_placement.py`의 공통 hit-test·커서·기하 함수를 사용하며, 원형·캡슐은 실제 창 마스크 안의 곡선과 경계에서만 조절합니다. 표시도 동일한 모양의 경계를 따릅니다.
- KeyDeck과 원형·캡슐·포스터는 마우스 조절 시 현재 비율을 자동으로 유지합니다. 카드형 콘텐츠는 자유 크기를 유지하며 Shift로 비율을 고정합니다. 실제 콘텐츠 크기가 보정된 뒤 반대 모서리 또는 반대 변의 중심을 고정합니다.
- KeyDeck은 드래그 중에도 창·face·canvas를 실제 덱 기하 크기에 맞춥니다. 확대 범위는 60–220%이며, 임시 확대는 canvas 상태에만 유지하고 종료 시 저장합니다. 취소·잠금·입력 유실·되돌리기는 원래 확대와 배치를 복구합니다.
- KeyDeck의 조절 영역에는 renderer의 그림자 여백을 포함해 실제 케이스의 변에서도 크기 조절을 시작할 수 있습니다. 조절 표시는 케이스 바로 바깥에 놓고 중앙 콘텐츠·타이틀 이동 영역을 확보합니다.
- OS 드래그 거리보다 작은 클릭·흔들림은 저장과 배치 이력에 반영하지 않습니다. 크기 조절 중 창 밖으로 나가도 조절 커서를 유지하며 Esc로 취소할 수 있습니다. KeyDeck의 키·헤더 버튼은 가장자리 조절 영역보다 우선합니다.
- 포커스를 받지 않는 KeyDeck에서도 Esc를 처리할 수 있도록 활성 배치 중에만 임시 keyboard grab을 사용합니다. 종료·취소·입력 유실·잠금·숨김에서 자기 grab만 해제하며, 클릭·작은 흔들림·평소 키 동작은 키 입력을 가져오지 않습니다.

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
- 기존 일러스트 3종과 Classic 아이콘, `weather_vector_art.py`의 선화·네온·플랫·픽셀·궤도·빈티지 6종을 합쳐 10개 팩을 제공합니다. 벡터 팩은 리소스 파일 없이 Qt로 그립니다.
- 선택값은 인스턴스 설정 `weather_asset_pack`에 저장하며 `appearance_preset`과 `display_style`을 변경하지 않습니다.
- 상태 슬롯은 맑음 낮/밤, 구름 조금 낮/밤, 흐림, 안개, 이슬비, 비, 폭우, 눈, 폭설, 천둥, 우박, 알 수 없음의 14종입니다.
- MET Norway의 `_day`, `_night`, `_polartwilight` 접미사는 `_day_period`로 보존해 낮/밤 에셋 선택에 사용합니다.
- 에셋 로드에 실패하면 기존 qtawesome 날씨 아이콘으로 자동 대체합니다.
- 날씨 제공처 출처는 위젯 하단에 상시 표시하지 않습니다. 우클릭 → 날씨 데이터 출처와 설정창의 같은 버튼에서 MET Norway·GeoNames 원본/이용 안내, CC BY 4.0, 데이터 변환·비보증 안내를 확인합니다. 출처 화면은 읽기 전용이며 새로고침·설정 저장을 실행하지 않습니다.
- `weather_template.py`는 위젯과 디자인 미리보기의 공통 렌더러입니다. 그림과 글자는 같은 24pt 기준으로 비례 조절하며, 그림은 16–1536px로 제한합니다. 습도·바람 뒤의 `%`·`m/s`도 해당 값과 같은 크기를 사용합니다. 외부 날씨 값은 HTML escape하고 비유한 크기·줄 간격은 제거합니다.
- `weather_designs.py`의 28개 디자인(기존 24개와 프리미엄 4개)은 표시 템플릿·공통 외관·일러스트·모양을 함께 적용합니다. 기존 13개 공통 외관 프리셋의 의미와 독립 일러스트 선택 동작은 유지합니다.
- 우클릭 및 기본 설정의 디자인 버튼은 `weather_design_dialog.py`의 검색·분류·실제 미리보기 갤러리를 엽니다. 설정창 안에서 선택하면 초안만 바뀌고 부모 설정 저장 시 반영합니다. 갤러리 자체는 설정이나 네트워크에 쓰지 않습니다.
- 날씨 기본 표시 템플릿은 20개입니다. 디자인 적용은 도시·온도 단위·갱신 주기·날씨 캐시·위치·그림자 설정을 유지하고, 모양 전환은 공통 `_set_widget_shape` 정책을 따릅니다. 현재 선택 표시에는 저장된 디자인 ID보다 실제 템플릿·외관·일러스트·모양의 일치를 사용합니다.
- 복원·재표시 때 좌표·단위가 같은 인스턴스 날씨 캐시가 만료되었으면 요청을 보내면서 그 예보를 `불러오는 중` 상태로 먼저 표시하고, 응답·오류 후 기존 규칙대로 갱신합니다. 다른 좌표·단위의 캐시와 마지막 예보 시점이 이미 지난 캐시(`_forecast_expired`)는 먼저 표시하지 않습니다.
- 좌표 캐시가 없어 GeoNames 도시 조회(GUI 스레드에서 약 0.2초)가 필요한 새로 표시된 날씨 위젯은 `불러오는 중` 화면을 먼저 그리고 첫 페인트 직후(0ms 타이머) 조회합니다. 페인트가 오지 않으면 `_FIRST_PAINT_FALLBACK_MS`(2초) 뒤 조회하며, 비활성화되면 `_cancel_deferred_lookup()`으로 취소하고 조회 직전에 요청 키·도시가 바뀌었으면 건너뜁니다. 회귀 검증: `tests/test_weather_first_paint_order.py`.

### 프리미엄 날씨 카드와 움직임

- `weather_scene.py`의 `WeatherSceneSurface`를 실제 위젯과 갤러리에서 공유합니다. Air Atmosphere·Soft Object·Editorial Mono는 카드형 전용이며 기존 디자인·새 위젯의 `pure_type` 기본값을 덮어쓰지 않습니다. 템플릿을 직접 수정하거나 다른 모양을 선택하면 기존 HTML 렌더링으로 돌아갑니다.
- 작은 크기는 그림·온도·지역, 보통 크기는 습도·바람과 예보 범위, 폭 300px·높이 330px 이상은 앞으로 6시간 안의 실제 예보 시점을 최대 6개 표시합니다. 결측 시점을 보간하거나 6시간 강수량을 1시간 강수량으로 나누지 않습니다.
- GeoNames의 도시 시간대로 표시하며, `남은 오늘` 범위는 현재 예보 시점 이후 같은 도시 날짜의 예보 최고·최저입니다. 예보 시각과 서버 갱신 시각을 구분하고 만료·오류 시 이전 예보임을 표시합니다.
- `weather_motion=off|subtle|full`, `weather_show_hourly`, `weather_animation_dir`는 인스턴스별 설정입니다. 저장/취소와 기존 복제·재시작 경로를 사용합니다. 내장 그림·빛·비·눈·별·안개의 움직임은 20fps이고, 숨김·비활성화·종료 시 프레임 타이머를 중단합니다. Windows 애니메이션 끄기·배터리 절약 모드를 따르며 표시 중에는 정책 변경을 60초마다 확인합니다.
- 사용자 폴더의 상태별 `clear_day.webp` 등 14개 이름과 GIF를 지원합니다. 파일·디코딩 크기를 제한하고 프레임 전체 캐시는 사용하지 않습니다. 누락·손상 파일은 내장 그림과 움직임으로 대체합니다.
- `움직이는 날씨 · GIF`는 `Assets/weather/animations`의 날씨별 13개 GIF를 재생합니다. 현재 날씨를 읽고 같은 장면의 정지 프레임을 미리 그린 뒤, 위젯 또는 선택한 디자인 미리보기가 보일 때 재생합니다. 사용자 그림을 먼저 확인하고, 날씨를 아직 모르면 기본 일러스트로 표시합니다.
- 배경·글자·시간별 예보를 한 번 그린 뒤 프레임마다 그림 영역만 갱신합니다. 아트 캐시는 DPR을 포함해 최대 24MiB로 제한하고 프리미엄 크기 조절은 기존 HTML 글꼴 이진 탐색을 실행하지 않습니다.
- `infrastructure/weather/request_pool.py`는 같은 좌표의 요청과 원본 응답을 공유합니다. 단위는 위젯별로 변환하고 한 위젯의 취소는 다른 위젯의 요청을 중단하지 않습니다. `Expires`·조건부 요청과 기존 인스턴스별 디스크 캐시를 유지합니다.
- 날씨 로딩·오류 문구 크기는 앱 글꼴 크기와 관계없이 기본 단계(`DEFAULT_FONT_PT`, 14px)로 고정합니다.
- 검증: `tests/test_weather_premium.py`와 기존 날씨 회귀. 격리 렌더링: `.venv/Scripts/python.exe scripts/validate_weather_premium.py`. 사용자 설정 보존·외부 요청 0회·샘플 데이터 여부를 결과 JSON에 남깁니다.

### 날짜·D-Day 장식 팩

- 번들 팩 레지스트리는 `presentation/widgets/moment_asset_packs.py`, 파일은 `Assets/moments`에서 관리합니다.
- 날짜 카드는 현재 월을 봄/여름/가을/겨울 장면으로 자동 매핑합니다.
- D-Day는 생일, 기념일, 마감, 출시, 여행, 학습, 건강, 축하, 차분함, 반짝임 장면을 선택합니다.
- 템플릿의 `{art|size=N}` 토큰은 선택한 장식 팩의 투명 PNG를 렌더링합니다.

### 런처 덱 — Air KeyDeck v4

설계 배경과 단계별 계획은 `docs/keydeck_v4_plan.md`를 참조합니다.

- 기본 테마는 기존 7개를 포함한 24개이며 글래스·미니멀·파스텔·내추럴·네온·레트로 6계열에 각 4개를 제공합니다. ID와 기존 외관 레시피를 보존하고 모델의 `THEMES`/`THEME_CATEGORIES`에서 공유합니다.
- Studio의 테마 버튼은 `keydeck/theme_dialog.py`의 갤러리 모달을 엽니다. 검색·분류·정적 썸네일과 현재 페이지 미리보기에서 비교하고 덱 전체·현재 페이지·선택한 키 적용 범위를 선택합니다.
- 갤러리는 복사본만 수정하고 `(theme_id, scope)` 요청을 반환합니다. 확인해야 Studio 초안에 반영하며 한 번의 실행 취소로 복원합니다. 실제 위젯 저장은 기존 Studio의 최종 적용 흐름을 사용합니다.
- 페이지/선택 범위에서는 케이스와 다른 페이지·키를 보존하고 `custom`으로 표시합니다. 사용자 이미지·파노라마·키 배치·이름·실행 동작은 모든 테마 적용에서 유지합니다.
- 갤러리 콤보박스는 휠로 값이 바뀌지 않습니다. 썸네일은 고정 카드 크기를 먼저 확보하고 보이는 항목만 순차 렌더링하며 닫을 때 지연 타이머를 중지합니다.

- 모듈: `presentation/widgets/keydeck/` (`model`, `physics`, `resources`, `renderer`, `canvas`, `studio`, `studio_canvas`, `studio_inspector`) + 통합부 `overlay_launcher_deck.py`. 위젯 타입 ID `launcher_deck`, 클래스명, 설정 prefix는 유지합니다.
- 저장: 인스턴스 설정 `keydeck_data`(JSON v4, 페이지 목록). 없으면 구 `launcher_deck_data`(v3)를 `migrate_v3()`로 **비파괴 이관**하고 구 키는 지우지 않습니다. 로드 시 `normalize_deck()`이 색상·열거형·범위·ID 중복·겹침을 모두 검증합니다.
- 좌표는 u 단위(0.25u 스냅), 키 크기 1–6.25u × 1–4u, 배치 영역 최대 24u × 10u, 페이지 최대 12개·페이지당 키 112개(풀배열 104키 수용). 겹침은 `settle_layout()`이 앵커(방금 옮긴 키)를 유지한 채 가장 가까운 빈 칸으로 밀어냅니다.
- 렌더링은 **단일 캔버스**(`KeyDeckCanvas`)가 담당합니다. 키별 위젯·타이머를 만들지 않습니다. 배경(케이스·플레이트·스위치·정적 LED)과 키캡 윗면(인서트 아트·레전드·유리 효과)은 픽스맵으로 캐시하고, 애니메이션 프레임에는 합성만 합니다. 편집 후에는 `renderer.invalidate(ids)`로 해당 키만 무효화합니다.
- 애니메이션 타이머는 캔버스당 1개이며 스프링·LED·피드백이 모두 정지하면 **즉시 멈춰야 합니다**(유휴 CPU 0). 숨김/`_set_runtime_active(False)` 시 타이머와 GIF를 멈춥니다. 스프링·기울기가 움직이는 동안만 16ms 틱을 쓰고, LED가 흐려지는 구간과 피드백 깜빡임은 33ms, 숨쉬기 LED는 50ms 틱을 씁니다.
- 이미지·글리프·사운드는 `resources.py`의 프로세스 공유 캐시를 거칩니다. `paintEvent`에서 파일을 직접 열거나 `QSoundEffect`를 새로 만들지 않습니다.
- 배포판(Qt Multimedia 없음)의 WinMM 출력 장치는 소리가 켜진 덱이 보이고 활성인 동안 열어 둡니다(`SoundBank.hold_output`). 미리 불러오기는 장치를 열지 않고, 덱이 나타나면 미리 불러온 소리 형식마다 voice를 8개까지 미리 열며(형식 2개까지), 마지막 덱이 숨거나 비활성이 되면 닫고 종료 때 모두 닫습니다. 덱이 숨김 이벤트 없이 삭제되면(캔버스 자신의 `deleteLater`, 창 안의 부모 위젯 삭제, 가비지 수집) `SoundBank`가 캔버스의 `destroyed`를 `@pyqtSlot` 슬롯에 큐 연결로 받아 다음 이벤트 루프에서 놓습니다. `destroyed`에는 파이썬 호출 객체(람다·`functools.partial`)를 연결하지 않습니다(순환 GC 중 접근 위반으로 테스트 프로세스가 죽었음). voice는 같은 형식의 어떤 소리든 재생하며 같은 소리의 겹침 수만 제한합니다. 사용자 소리는 미리 불러올 때 키 음량으로 계산해 두어 첫 타에 게인 계산을 하지 않습니다.
- 타건 물리(`physics.py`): 누르는 순간 손가락 속도(`FINGER_SPEED`)로 출발해 손가락 힘으로 바닥까지 약 40ms에 닿고(`BOTTOM_BOUNCE` 반동), 떼면 스위치 스프링이 되돌려 윗 하우징에서 멈춥니다(레스트 위로 튀지 않음). `step()`은 `bump`(택타일)·`click`/`click_up`(클리키)·`bottom`·`top` 이벤트를 돌려줍니다. 누르는 소리(클릭, 없으면 바닥음)는 손가락이 닿는 순간 바로 내고 `mark_down_cues_played()`로 애니메이션의 같은 이벤트가 다시 소리 내지 않게 합니다. 떼는 소리는 이벤트에 맞춰 냅니다. 토글 키는 `LATCH_DEPTH`에 걸린 채 유지합니다.
- 빠른 클릭도 바닥(`_COMMIT_DEPTH`)까지 눌린 뒤 올라옵니다. 가장자리를 누르면 `TiltSpring`으로 그쪽으로 기울었다가 떼면 흔들리며 돌아오고, 2u 이상 키는 스태빌라이저처럼 거의 수평을 유지합니다. 호버는 키를 들어 올리지 않고 빛으로만 표시합니다. `모션 최소화`에서는 스프링·기울기를 즉시 스냅하고 바닥음·복귀음만 재생합니다.
- 렌더링: 눌림 깊이만큼 윗면이 원근으로 작아지고 기울어진 쪽이 짧아지며(`_top_quad`), 옆면은 우물 속으로 어두워지고, 접촉 그림자는 좁고 진해지며, 윗면 가장자리에 차폐광이 생깁니다.
- 사운드 `auto`(실제 타건음)는 `Assets/keycaps/switch/`의 합성 음원(`scripts/generate_keyswitch_sounds.py`로 재생성)을 씁니다. 톤은 키캡 재질과 케이스로 정해집니다(알루미늄 케이스·PC 키캡 → 밝은 딸깍, PBT·우드·아크릴 → 낮은 도각). 종류마다 변형 4개를 번갈아 재생하고 충돌 속도로 음량을 조절합니다. 다른 사운드 선택지는 누를 때 한 번 재생하는 기존 방식을 유지합니다.
- 오버레이 창은 `WindowDoesNotAcceptFocus`를 유지해야 합니다. 그래야 단축키·텍스트 붙여넣기가 사용자가 작업 중인 앱으로 전달됩니다.
- 실행 동작: 앱·파일·폴더(스크립트 확장자 차단: `.bat .cmd .ps1 .vbs .vbe .js .jse .wsf .wsh .hta .scr .msc`), `http/https` URL, 검증된 단축키, 텍스트 스니펫(클립보드 + 선택적 Ctrl+V), 허용 목록 명령 8종, 페이지 이동. 길게 누르기(550ms) 보조 동작을 지원합니다. 미지정 키는 `None`을 반환해 실패 피드백 대신 안내만 표시합니다.
- 캔버스 위 마우스 입력은 키·헤더 컨트롤 위에서는 캔버스가, 빈 영역·리사이즈 모서리에서는 베이스 위젯(드래그/리사이즈)이 처리합니다. 모서리 리사이즈는 글꼴 맞춤 대신 덱 배율(`scale`, 60–220%)만 바꿉니다.
- 키 위에 이미지 파일을 드롭하면 인서트 아트로, 빈 곳에 파일/URL을 드롭하면 새 키로 추가합니다. 사용자 에셋은 `import_launcher_asset()`으로 검증(25MB)·해시 복사합니다.
- KeyDeck Studio는 초안(`deepcopy`)만 편집하고 `적용`해야 저장합니다. 캔버스는 런타임과 같은 렌더러(WYSIWYG)를 쓰고, 다중 선택 시 스타일 필드만 일괄 적용하며 이름·동작은 단일 선택에서만 편집합니다. 실행 취소는 80단계이며 슬라이더 연속 변경은 0.9초 안에서 병합합니다. 인스펙터에서 마우스 휠은 페이지 스크롤에만 사용하고 콤보박스·슬라이더·인서트 미리보기 값을 변경하지 않습니다.
- 덱 파노라마(`deck.panorama`: `path`·`name`·`fit`(`cover`/`contain`)·`x`·`y`(-100~100 정렬)·`zoom`(100~400%))는 한 장의 이미지를 인서트 종류가 `panorama`인 키들에 나눠 끼웁니다. 배치 기준은 `DeckGeometry.content_rect`(실제 키가 놓인 범위)이며 스튜디오 편집 여백(`grid_min`)을 포함하지 않아야 스튜디오와 실제 위젯의 잘림이 같습니다. 계산은 `model.panorama_rect()` 하나로 렌더러와 미리보기가 공유합니다.
- 스튜디오에서 파노라마를 고르면 한 번의 실행 취소 단계로 선택한 키, 또는 (선택이 없고 이 페이지에 파노라마 키가 없으면) 현재 페이지 전체에 적용합니다. 기본 배치는 사진은 `cover`, 크게 잘리는 투명 그래픽(로고)은 `contain`입니다. `지우기`는 이미지와 함께 파노라마 키의 인서트를 `none`으로 바꿔 '이미지 없음' 자리표시가 남지 않게 합니다. 배치 미리보기는 드래그로 정렬, Ctrl+휠로 확대, 더블클릭으로 초기화합니다(그냥 휠은 인스펙터 스크롤).
- **레이아웃 저장·공유** (`keydeck/layout_library.py`, `keydeck/layout_dialog.py`): `.keydeck` 파일(UTF-8 JSON, `format=air-calendar-keydeck-layout`, `version=1`)은 `kind=page`(한 페이지 + 미리보기용 `look` + 파노라마) 또는 `kind=deck`(덱 전체)입니다. 이미지·사용자 소리·파노라마는 base64로 내장하고(합계 32MB, 파일 48MB 한도) 문서 안 경로는 `asset:<sha>`로 바꿉니다. 적용할 때만 `import_launcher_asset()`으로 자산 저장소에 복원하고 키 id는 새로 발급합니다. 앱·파일 대상 경로는 그대로 두므로 **가져오기 전에 키 동작 요약·열리는 대상 목록을 보여 주고 확인을 받습니다.** 일반 덱 JSON도 덱 레이아웃으로 받습니다.
- 내 레이아웃은 앱 데이터의 `keydeck_layouts/`에 파일 하나씩 저장합니다(라이브러리 파일 = 공유 파일 형식). 삭제는 이 폴더 안의 `.keydeck`만 허용합니다. 스튜디오 `레이아웃` 버튼(Ctrl+L)과 위젯 우클릭 `레이아웃 > 레이아웃 갤러리`가 같은 `LayoutLibraryDialog`를 열고, 창은 `request`만 돌려주며 적용은 `resolve_request()`(스튜디오는 실행 취소 가능, 위젯은 즉시 저장)가 합니다. 페이지 탭 우클릭에서 바로 저장·내보내기, `.keydeck` 파일을 캔버스·위젯에 끌어다 놓으면 가져오기가 시작됩니다.
- **기본 키보드 배열** 템플릿 3종(`keyboard_full` 104키 · `keyboard_tkl` 87키 · `keyboard_60` 61키, `KEYBOARD_TEMPLATE_IDS`)은 ANSI 위치에 두벌식 한글 자모를 보조 각인으로 넣고, 오른쪽 Alt·Ctrl 자리는 한/영(`Hangul`)·한자(`Hanja`)입니다. 모든 키는 `hotkey` 동작으로 해당 키를 보내며, 테마를 입혀도 그림 없는 각인 키캡(`corner` 레전드, 글리프 없음, 120%)을 유지합니다. 폭 1.75u 이상 키는 테마의 강조색을 받습니다.
- **고정 조합키**: `mode=toggle`이면서 동작이 조합키 하나(`Shift`/`Ctrl`/`Alt`/`Win`)인 키(`modifier_name()`)는 누르면 보내지 않고 켜 두었다가, 같은 페이지에서 다음에 누른 단축키 동작 앞에 붙여 보내고(`combine_hotkey()`) 자동으로 풀립니다. `hotkey_sender`는 문장부호(`Minus`·`Equal`·`Backquote`… 또는 `-`·`=` 같은 한 글자), 숫자패드(`Num0`–`Num9`, `NumAdd`…), `PrintScreen`·`ScrollLock`·`NumLock`·`Apps`·`Hangul`·`Hanja`를 지원하고 방향키·편집 키에는 확장 키 플래그를 붙입니다.
- 큰 배열을 적용해 덱이 화면보다 커지면 위젯이 `scale`을 줄여(최소 60%) 화면 안에 맞춥니다(`_fit_scale_to_screen`).
- 키캡 글자는 `renderer.fill_text()`로 윤곽선을 채워 그립니다. 불투명 키캡 위의 `drawText`는 ClearType 색 번짐(가는 획의 빨강·파랑 테두리)이 생기므로 레전드·헤더·빈 페이지 안내에 `drawText`를 쓰지 않습니다.
- 테마 적용은 사용자 이미지·파노라마 인서트를 보존합니다. 템플릿 적용은 현재 페이지만 바꾸고, 테마가 `custom`이면 페이지 첫 키의 스타일을 이어받습니다.
- **닫기·종료 규칙**: 헤더 오른쪽 `×`(헤더가 없으면 호버 시 모서리 배지)와 메뉴 `키덱 숨기기`는 `hide_from_user()`로 위젯을 숨기고(설정 `enabled=False`), 첫 1회만 상단 '위젯' 메뉴에서 다시 켜는 방법을 알립니다. 메뉴 `Air Calendar 종료...`는 메인 창의 `request_app_exit()` 흐름(확인창 포함)을 그대로 사용합니다.
- `closeEvent`는 저장 플러시·타이머 정지만 하고 **절대 닫기를 거부하지 않습니다**. Qt 6의 `quit()`은 창 하나라도 닫기를 거부하면 취소되어 트레이·메인 창이 사라진 채 프로세스가 남기 때문입니다.
- **누르기 체험**은 스튜디오를 잠그지 않습니다. 모든 도구가 그대로 동작하며, 배치를 바꾸는 동작(키 추가·복제·삭제·레이아웃·새 페이지)은 체험을 먼저 끝냅니다. 체험 중 누른 키는 선택되어 오른쪽에 설정이 열리므로 스위치·소리·재질을 바로 바꿔 비교할 수 있습니다. 체험 중 토글 전환은 끝낼 때 원래 상태로 되돌리고(초안이 더러워지지 않음), 키가 없는 페이지에서는 체험을 시작하지 않습니다. Esc 또는 `체험 끝내기`로 끝냅니다.
- **토글 키**(`mode=toggle`)는 켜지면 `LATCH_DEPTH`에 눌린 채 유지되고 `indicator`(`switch` 미니 스위치 · `bar` 불빛 막대 · `dot` 표시등 · `ring` 테두리 빛 · `none`)로 켜짐/꺼짐을 그리며, 켜진 동안 윗면에 켜짐 색(`led.color`) 틴트가 더해집니다. 밝은 키캡에서는 켜짐 색 대비를 자동 보정합니다. `indicator`는 스타일 필드라 모양 복사·붙여넣기에 포함됩니다.
- 키캡 프로필: `cylindrical`(체리) · `oem` · `spherical`(SA) · `mt3` · `flat`(DSA) · `xda` · `low`(로우 프로파일, 누름 거리도 짧음) · `round`(원형, 길쭉한 키는 알약 모양). 모양 차이는 `ProfileSpec`(옆면 높이·모서리·윗면 폭·음영)로 정의합니다.
- 새 페이지는 키 하나가 선택된 상태로 만들어져 바로 이름을 입력할 수 있습니다. '적용하지 않은 변경 사항' 확인창은 긴 문구가 잘리지 않도록 버튼을 세로로 쌓습니다(`UnsavedChangesDialog`).
- 앱 종료 중(`shared/app_lifecycle.is_app_exiting()`)에는 KeyDeck Studio가 '적용하지 않은 변경' 확인 없이 닫히고, 지연 실행된 키 동작과 스튜디오 열기는 무시합니다. 평상시 스튜디오 닫기는 `적용하고 닫기 / 변경 사항 버리기 / 계속 편집` 3선택이며 Esc는 계속 편집입니다. Ctrl+S·Ctrl+Enter는 적용 후 닫기입니다.
- 덱이 나타난 직후 0.35초 동안의 마우스 누름은 무시합니다(덱을 띄운 클릭이 키에 닿아 동작이 실행되는 것을 방지). 터치는 바로 받습니다.
- 시각 QA: `.venv\Scripts\python.exe scripts/render_launcher_deck_preview.py` (Windows 플랫폼 플러그인에서 실행 — offscreen에는 한글 글꼴이 없습니다).

### 비트메이커 녹음·루프

- 스튜디오와 위젯 메뉴의 `연주·녹음`은 별도 루프 믹서 위젯(`overlay_launcher_deck.open_loop_mixer_widget`)을 연다. 설정창 텍스트 입력은 연주하지 않는다.
- 현재 UI는 6트랙 루프 믹서(`domain/loop_mixer.py` `TRACK_COUNT = 6`)다. 스튜디오의 연주·루프 진입점(`studio.py` `open_beatmaker_performance`·`open_beatmaker_looper`)은 모두 `open_loop_mixer()`로 이어진다. 현재 사용 순서는 [루프 믹서 안내](../docs/ux-audit/loop-mixer-touch-20261106.md)를 참고한다. 아래 단일 녹음·4트랙 루프덱 항목은 보존되는 데이터 계약이다.
- `domain/beatmaker_recording.py`가 최대 5분·4,096타의 선택 필드 `deck.beatmaker_recording`을 검증한다. 음원 스냅샷만 재생하고 키 동작을 실행하지 않는다. 저장된 녹음을 자동 재생하지 않는다.
- 스튜디오는 초안·실행 취소·적용 흐름을 유지하며 위젯은 연주창을 닫을 때 저장한다. 빈 녹음은 기존 녹음을 유지하고, 교체·삭제는 확인한다. 닫기·숨김·종료·확인창 중 종료에서 재생과 타이머를 정리한다.
- 전체 덱 공유는 녹음의 사용자 WAV도 내장/복원한다. 페이지 공유 시 수신 덱의 기존 녹음을 보존한다. 단일 녹음의 데이터 계약·검증 이력은 `docs/ux-audit/keydeck-recording-loop-20261022.md`에 있다.
- `루프덱 · 4트랙`은 기존 단일 녹음과 분리된 `deck.beatmaker_looper`를 사용한다. `domain/beatmaker_looper.py`가 BPM 40~240, 1·2·4·8마디, 16분음표/끄기, 4트랙·트랙당 2,048타·총 8,192타를 검증한다. 기존 `beatmaker_recording` version 1은 변경하거나 자동 변환하지 않는다.
- 루프덱은 첫 패드부터 한 바퀴를 녹음한 뒤 반복한다. 다음 트랙과 오버더빙은 같은 monotonic epoch를 공유하고 다른 트랙의 반복을 유지한다. 라이브 입력을 녹음 중 중복 재생하지 않으며, 절전 후 지난 타격을 한꺼번에 재생하지 않는다. 닫기·숨김·종료에서는 타이머와 악기 입력을 정리한다.
- 루프 믹서 출력은 20ms 블록·버퍼 3개를 유지하고 `CALLBACK_EVENT` 이벤트로 깨어난다(`stop()`도 이벤트를 깨운다). 헤더 준비·해제·쓰기·위치 호출과 녹음 중 블록마다 하는 마이크 버퍼 재등록(`waveInAddBuffer`)은 GIL을 놓지 않고(x64·ARM64, 32비트는 기존처럼 놓음), 열기·초기화·닫기는 놓는다. 이벤트 핸들은 `waveOutClose`가 성공한 뒤에만 닫고, 정리에 실패하면 백엔드와 함께 보존한다(`_DRIVER_UNSAFE`). 출력 정지 판정 1초는 실제로 기다린 시간만 세며, 절전 복귀처럼 시계가 크게 뛰면 다시 센다.
- 마이크는 녹음할 때만 보조 스레드에서 열고(`waveInOpen`·버퍼 준비), 준비되면 오디오 루프가 넘겨받는다. 녹음 중 장치 오류는 정지와 같이 그때까지의 녹음을 남기고 `audio_device_error_take_saved`로 알린다. 녹음 위치는 출력 장치에 쌓인 프레임만큼(마이크는 입력 지연을 더해) 앞당겨 들린 자리에 기록하며, 한 테이크 안에서는 첫 소리 때 정한 값을 유지한다.
- 키덱은 미리 불러올 때 소리 목록을 `set_keydeck_sounds()`로 알리고, 그 키덱이 연결된 믹서는 오디오 스레드 밖에서 미리 디코딩한다. 세션·프로젝트를 불러올 때와 재생을 시작할 때도 연결된 키덱이 알린 소리를 디코딩한다. 오디오 스레드는 디코딩하지 않으며, 아직 준비되지 않은 타격은 0.25초 안에 준비되면 재생하고 아니면 버린다.
- 루프 믹서 콤보 8개(루프 길이·마이크·트랙 입력 소스 6개, `TouchMixerComboBox`)의 팝업 목록 스타일시트(행 최소 44px)와 터치 스크롤 제스처는 위젯을 만들 때가 아니라 처음 열 때 `showPopup()`에서 한 번만 적용한다(`_popup_prepared`). 만들 때 적용하면 믹서의 지연된 첫 polish 중에 44px 규칙 없이 행이 배치되어, 다음 외형 재적용 전까지 50px 행이 겹쳐 보인다(Windows 11 스타일에서 30–34px 간격). 팝업은 가상 함수 `showPopup()`으로만 열리므로(마우스·F4·Alt+↓·Space는 테스트로 확인, 접근성 열기 동작은 Qt 소스 기준) `QComboBox.showPopup(combo)` 직접 호출이나 `setView()`로 이 재정의를 우회하지 않는다. `before_popup`(입력 소스 목록 갱신)은 준비보다 먼저 실행한다. 회귀: `tests/test_loop_deck_launch_perf.py`.
- Studio의 초안·실행 취소·적용과 위젯의 닫을 때 저장 계약을 유지한다. 전체 덱 공유는 네 트랙의 사용자 WAV 스냅샷을 함께 내장/복원하고 페이지 가져오기는 수신 덱의 단일 녹음과 루프를 모두 보존한다.
- 회귀는 `tests/test_beatmaker_looper.py`, `tests/test_keydeck_looper_ui.py`, `tests/test_keydeck_looper_layouts.py` 및 기존 녹음/KeyDeck 공유 테스트를 포함한다. 현재 사용 순서는 [루프 믹서 안내](../docs/ux-audit/loop-mixer-touch-20261106.md)를 참고한다. [루프덱 안내](../docs/ux-audit/keydeck-loopdeck-20261106.md)는 4트랙 루프덱(`deck.beatmaker_looper`)의 데이터 계약·검증 이력으로만 참고한다.

## 크로스 위젯 참조

```python
# widget_registry()로 다른 위젯 값 참조 가능 — 이미 만든 위젯을 인스턴스 순서로 돌려준다.
# 꺼 둔 스톱워치·카운트다운·D-Day는 템플릿 값 때문에 여기서 만들고, 다른 종류는 만들지 않는다.
registry = manager.widget_registry()  # {inst_id: widget}
manager.refresh_all_texts(tier="fast")  # fast 변수를 쓰는 text 위젯만 갱신, 갱신할 위젯이 있을 때만 registry를 만든다

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

## 위젯 전용 모드 배치와 표면 모양

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
- 위젯 전용 모드의 글자/배경 불투명도 슬라이더는 2026-11-22에 제거했습니다. 색상은 메인 테마를 따르고 투명도는 메인 창의 `모양` 설정(아래 가독성 보정 포함)을 따릅니다. 이전 `widget_mode_text_opacity`·`widget_mode_background_opacity`·`widget_mode_opacity` 값은 메인 테마 연동 중에는 적용하지 않으며 새로 쓰지도 않습니다.
- 창 전체의 `windowOpacity`는 1.0을 유지합니다. 조작 아이콘은 항상 표시합니다.
- 미리보기는 실제 위젯과 같은 알파 렌더링을 체크무늬 배경 위에 합성합니다. 전체 이미지에 불투명도를 다시 곱하지 않으며 취소 시 실제 설정을 변경하지 않습니다.
- 글꼴과 제목 굵기는 `widget_mode_font_family`, `widget_mode_font_weight`로 저장합니다. 미리보기에도 동일한 글꼴을 적용하며 취소 시 저장하지 않습니다.
- 툴바 끌기는 `windowHandle().startSystemMove()`로 OS가 창을 옮깁니다. 배율이 다른 모니터 사이에서 Qt 논리 좌표가 연속되지 않아, `move(커서 - 오프셋)` 방식은 경계에서 창이 튀며 마우스 이벤트마다 DPI가 번갈아 바뀌어 멈춤과 크기 증가를 일으켰습니다. 이동 종료(`WM_EXITSIZEMOVE`, 시작 실패 시 마우스 놓기)에서 시작 크기를 복원하고 도착 화면 안으로 맞춘 뒤 가장자리 맞춤과 저장을 한 번만 합니다. 이동은 크기를 바꾸지 않습니다. PyQt6 6.12에서 `nativeEvent` 재정의 안의 `super().nativeEvent()` 호출은 접근 위반으로 종료되므로 `(False, 0)`을 직접 반환합니다.
- 창 가장자리 4변·4모서리에는 보이지 않는 6px 크기 조절 띠(`_EdgeResizeHandle`)가 있고 `windowHandle().startSystemResize(edges)`로 OS가 크기를 바꿉니다(배율이 다른 모니터에서도 이동과 같은 이유로 안정적). 종료는 이동과 같은 `WM_EXITSIZEMOVE`에서 한 번 저장합니다. 네이티브 핸들이 없으면 띠가 직접 크기를 바꿉니다. 위치·크기 잠금 중에는 띠를 숨깁니다. 기존 오른쪽 아래 크기 조절 손잡이(Shift 비율 유지)는 그대로입니다.
- 모니터 분리(`screenRemoved`): 창을 남은 화면 안으로 옮기되 저장된 위치(원래 모니터 이름)는 덮어쓰지 않습니다(`controller._displaced_home`). 그 모니터가 다시 연결되면(`screenAdded`, 0.8초 뒤) 저장된 위치로 돌아갑니다. 사용자가 그 사이 창을 옮기거나 크기를 바꾸면 그 화면이 새 위치가 되어 복귀하지 않습니다. 해상도·배율·작업 표시줄 변경(`availableGeometryChanged`)에는 창을 화면 안으로 맞춥니다. 모니터가 둘 이상이면 더 보기 ▸ 창 관리에 '다른 모니터로 이동'(상대 위치·크기 유지)이 나옵니다.
- 날짜 선택은 `WidgetDatePickerPopup`(`widget_date_picker.py`) 팝업입니다. 제목을 누르면 일 → 월(12개) → 연(12년 단위)으로 올라가고, 연·월을 고르면 다시 내려와 어느 날짜든 세 번 안에 고릅니다. 키보드: 방향키·PageUp/PageDown(월)·Home(오늘)·Enter, 일 화면 휠은 월 이동. 월간 달력 제목을 눌러도 같은 팝업이 열립니다. 툴바의 이전·다음 버튼은 월간 표시 중에는 한 달, 그 밖에는 한 주를 옮깁니다.
- 툴바·푸터 버튼은 `ICON` 아이콘(16px, 꾸미기만 18px)을 쓰고, 툴팁은 '이름 — 하는 일' 형식이며 메인 화면 버튼에는 F12를 적습니다(`_apply_button_help`).
- 시계 옵션: `widget_mode_clock_format`(`24h`/`12h`), `widget_mode_clock_seconds`, `widget_mode_clock_size`(`small` 하단 / `large` 툴바 아래 큰 시계, 끌어서 창 이동 가능), `widget_mode_clock_show_date`. 초 표시 중에만 1초마다 갱신합니다. 자유 구성은 큰 시계를 쓰지 않습니다. 작업 공간 `MODE_KEYS`에 포함됩니다.
- 메인 테마 연동 색은 `harden_widget_readability()`가 위젯용으로 보정합니다. 바탕 불투명도 최소 95%, 불투명 표면 단계, 배경화면과 무관한 글자 대비 하한을 지킵니다([테마 계약](theme_token_completion_process.md#widget-only-mode-readability-contract)).
- 42칸 월 캘린더는 처음 쓸 때(`month_calendar` 속성) 만들고, 그 전에 받은 크기·테마·선택 날짜는 저장했다가 생성 시 적용합니다. 주간 표시 중에는 월 그리드 렌더를 미룹니다. 테마 토큰은 `apply_theme` 한 번마다 `controller._theme_tokens`에 저장해 완료 체크박스 그리기에 재사용합니다. 회귀 검증: `tests/test_widget_mode_launch_perf.py`.
- 조작부, 본문, 하단 상태/크기 조절은 하나의 `unified_surface` 안에 배치합니다. 열이 둘인 좌우형(`dashboard`)은 폭 640px 미만에서 세로로 전환하되 저장된 배치 선택은 유지합니다.
- 날짜 선택/이전·다음/오늘/고정/꾸미기는 한 줄 헤더로 통합하고 시계는 기본으로 하단에 표시합니다(큰 시계 옵션은 헤더 아래). 배치는 4종입니다. 세로형(`stacked`)은 달력·필터·목록을 위에서 아래로, 좌우형(`dashboard`)은 달력을 왼쪽에 필터와 목록을 오른쪽에, 보드형(`work_board`)은 달력 아래에 일정·업무 보드를 두고, 목록형(`minimal`)은 달력 없이 필터와 목록만 둡니다. 기본 달력 형태는 세로형·보드형 주간, 좌우형 월간이며 배치별 `widget_mode_calendar_style_<id>`로 바꿉니다. 날짜 영역의 접기 상태는 레이아웃마다 독립 저장하고 더 보기 메뉴의 이전/다음 기간도 주간·월간에 맞춰 전환합니다.
- 날짜 영역을 접으면 달력 위젯만 숨기지 않고 남은 섹션을 한 열로 재배치하고 창 자체를 축소합니다. 펼침/접힘 크기와 화면 좌표는 레이아웃별로 구분해 저장하며 다시 펼칠 때 기존 펼침 크기를 복원합니다.
- 월간 캘린더는 별도 불투명 패널처럼 보이지 않도록 셀 뷰포트를 투명하게 유지합니다. 요일 머리글과 선택일만 메인 테마 색상을 낮은 알파로 합성하고, 주말은 고정 빨강 대신 테마 강조색을 사용합니다.
- 주간 날짜는 큰 타원형 캡슐 대신 작은 카드형 셀을 사용합니다. 기본/오늘/선택/호버/키보드 포커스 상태를 배경, 가는 테두리, 하단 강조선과 글자 굵기로 구분하며 메인 테마와 모양 설정의 불투명도를 그대로 따릅니다.
- 보조 설명 설정은 모든 기본 배치와 미리보기에서 동일하게 동작합니다. 배치 내부 기본값 때문에 사용자가 켠 설정을 다시 숨기지 않습니다.
- 일정 강조 마커는 카드 위쪽이 아니라 제목 왼쪽 중앙에 맞춥니다. 주요 추가 버튼의 기본/호버/누름 상태는 모두 배경과 대비되는 글자색을 보장합니다.
- 목록 밀도는 `widget_mode_density=compact|standard|comfortable`로 저장합니다. 글꼴/글자 크기/불투명도/배치 설정은 변경하지 않고 행 여백과 시간 배치만 조절합니다. 빠른 메뉴에서는 즉시 저장, 꾸미기에서는 초안 미리보기 후 적용/취소합니다.
- 행마다 반복되는 일정/업무 유형 설명은 표시하지 않습니다. 전체 보기에서는 그룹 제목으로 구분하고 일정 필터에서는 중복 그룹 제목도 생략합니다. 원본 데이터와 ID, 완료/편집 동작은 유지합니다.
- `side_panel_renderer.load_right_panel()`은 패널 검색/상태 필터를 적용하기 전의 원본 업무 데이터를 `_latest_directive_data`로 게시해야 합니다. 메인 창이 숨겨진 상태에서도 위젯이 이 데이터를 받아야 합니다. 지시 행은 DB가 돌려주는 `sqlite3.Row`를 `tuple`로 바꿔 게시합니다. 위젯은 tuple·list 행만 읽으므로, 그대로 넘기면 지시가 위젯에 하나도 표시되지 않습니다(3.6.0부터 있던 결함, 회귀 검증: `test_directives_from_the_database_are_listed_in_widget_mode`). 게시 데이터의 `routine_rows`에는 미완료 루틴과 그날(`context_date`) 루틴 외에, 그날이 마감일(`period_end`, 없으면 `deadline`, 없으면 `target_date`)이면서 그날 또는 실제 오늘 완료한(`unified_task.completed_at`) 루틴도 들어갑니다(`_merged_routine_rows()`의 두 번째 반환값. 메인 패널은 첫 번째 값만 사용하므로 바뀌지 않음). `completed_directive_ids`에는 그날 완료한 지시 ID(`task_directive.completed_at`, `directive_repo.directive_ids_completed_on`)가 들어갑니다.
- 지시 행은 `get_recent_directives(limit)`(오른쪽 패널·위젯은 기본 200)로 읽습니다. 완료(`completed`/`done`)가 아닌 지시는 보류·상태 없음까지 모두 불러오고, 완료된 지시는 마감이 늦은 순으로 limit개만 불러오며(마감 없는 완료 지시는 가장 오래된 것으로 칩니다), 오늘 완료한 지시(`status='completed'`이고 `completed_at`이 오늘)는 limit과 상관없이 항상 함께 불러옵니다. 반환 순서(마감 오름차순, 같은 마감은 id 내림차순)와 7열 행 모양은 그대로입니다. 마감 순 LIMIT만 쓰면 지우지 않고 쌓인 오래된 완료 지시가 오늘·기한 지남·기한 없음 지시를 밀어내 위젯, 오른쪽 패널, 명령 팔레트, `{directive_count}`, 초집중 후보에서 사라졌습니다. 그보다 오래된 완료 지시는 패널의 전체·완료 필터와 검색, 지난 날짜 위젯의 완료 포함 목록에 나오지 않으며 지시·협조 관리에서 모두 볼 수 있습니다. 회귀 검증: `tests/test_recent_directives.py`.
- 위젯 전용 모드에서 루틴·지시 프레임이 모두 보이지 않으면 `load_right_panel()`은 `publish_right_panel_data()`로 같은 데이터만 게시하고 패널 생성을 미룹니다. 미룬 생성은 두 프레임 중 하나의 Show 이벤트에서 첫 페인트 전에 실행하고, 새 패널을 즉시 표시하며 교체된 패널은 숨깁니다. 클릭 처리 중 창이 표시되면 대기 중인 표시 호출보다 페인트가 먼저 오기 때문입니다(떠 있는 오른쪽 dock이 보이면 미루지 않음). 앱 종료가 시작된 뒤의 Show에서는 만들지 않고, 생성이 실패하면 대기 상태를 유지해 다음 `load_right_panel()`이 시그니처와 상관없이 다시 만듭니다. 상태 변경(`handle_task_status_changed`)은 그 유형을 나열하는 패널만 갱신합니다: 일정·Google 원격 미러는 좌측·중앙, 루틴은 오른쪽, 알 수 없는 유형은 전체. 회귀 검증: `tests/test_widget_completion_refresh.py`.
- 일부 데이터가 지연되어도 이미 불러온 일정/업무는 지우지 않습니다. 지연 안내와 재시도 동작을 목록 안에 함께 표시합니다.
- 목록에는 원본 `item_id`와 `source=task|directive`를 함께 전달합니다. 완료는 기존 상태 변경 처리기의 성공 응답 후 반영하며, 최근 상태 변경을 실행 취소할 수 있습니다.
- 일정·루틴은 완료→대기 직접 전환이 막혀 있으므로(`domain/task_status_view.py`) 완료 체크를 해제하면 `진행 중`으로 저장하고, 실행 취소가 막힌 전환이면 `진행 중`을 거쳐 이전 상태로 두 번 저장합니다. 두 번째 저장이 실패하면 위젯은 `진행 중`을 표시하고 다시 실행 취소할 수 있습니다. 지시·협조는 이 정책이 없어 체크 해제 시 `대기`로 저장합니다. 체크 해제 후 실행 취소로 다시 완료하면 상태와 함께 체크 해제가 지운 원래 완료 시각(`completed_at`, 일정·루틴은 `unified_task`, 지시·협조는 `task_directive`, NULL 포함)도 되돌립니다(`_COMPLETED_AT_BEFORE`, `restore_task_completed_at`·`restore_directive_completed_at`). 이 값은 휴지통 목록과, `완료 포함`일 때 그날 완료한 루틴·지시를 위젯에 남길지 판단할 때 읽으므로, 실행 취소 시각으로 기록하면 다른 날 완료한 항목이 오늘 완료한 것으로 나타났습니다(회귀 검증: `tests/test_widget_keeps_completed_today.py`). 체크 해제 뒤 다시 체크하면 그때 시각으로 기록합니다. 저장 실패 시 자유 배치·보드의 체크박스도 되돌리며, 실패한 항목이 대기 중인 실행 취소 대상이 아니면 그 실행 취소는 버립니다. 회귀 검증: `tests/test_widget_completion_refresh.py`.
- 지시·협조 생성은 일반 태스크 다이얼로그의 `task_type`으로 우회하지 않고 전용 `open_directive_dialog()` 경로를 사용합니다. 추가 메뉴와 더 보기 메뉴에서는 지시·협조 관리 및 전체 업무 관리로 이동할 수 있어야 합니다.
- 통합 목록은 일정/업무/지시·협조 필터를 독립 제공하고, 항목의 빠른 메뉴에서 열기·완료·우선순위·삭제를 기존 메인 창 처리기에 위임합니다. 읽기 전용 구독 일정에는 변경·삭제 동작을 제공하지 않습니다.
- 필터와 실행 버튼은 의미상 분리합니다. 넓은 폭에서는 한 줄, 중간 폭에서는 두 줄, 초소형 폭에서는 현재 선택값이 보이는 메뉴형 필터로 전환하며 필터 이름을 `…`로 대체하지 않습니다.
- 목록 상단에는 현재 필터의 제목을 표시합니다. 완료 항목 노출은 주요 실행 버튼이 아닌 `완료 포함` 보조 필터로 제공하고, 완료된 행에는 취소선뿐 아니라 명시적인 완료 상태 배지를 함께 표시합니다.
- 오늘의 지시·협조 목록에는 오늘 마감뿐 아니라 미완료 상태의 기한 경과 및 기한 없음 항목을 별도 구역으로 표시합니다. `완료 포함`(`widget_mode_show_completed`)이 켜져 있으면 그날 완료한 기한 경과·기한 없음 지시도 같은 구역에 체크된 상태로 남깁니다(`task_directive.completed_at` 기준이라 위젯·메인 패널 메뉴·지시 다이얼로그·관리 화면 어디서 완료했든, 같은 날 재시작해도 유지). 위젯에서 방금 체크한 행은 데이터가 다시 게시되기 전에도 사라지지 않습니다. 다른 날 완료했거나 완료 시각이 없는(NULL, 컬럼 추가 전 완료) 지시는 표시하지 않습니다. 그날 마감인 루틴도 그날 완료하면 체크된 상태로 남고, 전에 완료한 루틴은 마감일이 되어도 다시 나타나지 않습니다. 다른 날을 보면서 그날 마감 루틴을 완료해도 완료 시각이 오늘이므로 그 날 목록에 남습니다. `get_recent_directives()`는 오늘 완료한 지시를 완료 200건 제한과 상관없이 포함하므로 오래된 기한·기한 없는 지시도 남습니다. 회귀 검증: `tests/test_widget_keeps_completed_today.py`.
- 불러오는 중과 불러오기 지연은 빈 목록과 구분합니다. 목록 개수 제한으로 항목을 생략하지 않습니다.
- 목록 교체 시 기존 행을 즉시 숨긴 후 지연 삭제합니다. 스크롤 내부 레이아웃의 최소 높이를 유지하여 작은 창에서 행이 겹치지 않게 합니다.
- 회귀 검증: `tests/test_widget_mode_ux.py`, `tests/test_unified_widget_mode.py`, `tests/test_widget_mode_coordinator.py`, `tests/test_widget_mode_geometry.py`.
- 밀도/압축 헤더/타이포그래피 회귀 검증: `tests/test_widget_mode_efficiency.py` (설정 재로드, 초안 취소, 역할별 글자 비율, 큰 글꼴·작은 창 포함).

### 저장한 자유 구성과 내 배치

- 구성 편집기(`WidgetFreeLayoutEditorDialog`)는 2026-11-22에 제거했습니다. 새 자유 구성을 만들거나 고치는 화면은 없지만, 이미 저장한 자유 구성과 `내 배치`는 계속 표시하고 적용·이름 변경·삭제할 수 있습니다. 설정 이관은 작업 중이던 자유 구성을 `이전 자유 구성` 내 배치로 보존합니다.
- 프리셋은 `widget_mode_layout`에 유지합니다. 표시 방식은 별도 `widget_mode_layout_mode=preset|free`, 자유 구성은 `widget_mode_free_layout`의 version 1 JSON으로 저장합니다. 프리셋 선택은 자유 구성을 삭제하지 않습니다.
- 모델과 검증: `widget_free_layout.py`. 캔버스 논리 좌표와 요소별 `enabled` / `[x,y,width,height]`, 선택적 8px 정렬 `snap`, `calendar_mode=week|month`, 선택 필드 `order`와 요소별 `locked`를 읽습니다. 알려지지 않은 요소·중복·유효하지 않은 버전/좌표는 거부하고 범위 밖 좌표는 캔버스 안으로 제한합니다. 읽기는 설정을 변경하지 않습니다.
- 구성 요소는 날짜, 시계, 달력, 통합 목록 필터, 통합 목록, 일정 목록, 업무 목록, 지시·협조 목록입니다. 사용자가 선택하지 않은 요소를 강제로 표시하지 않습니다.
- 사용자 프리셋은 `widget_layout_presets.py`에서 관리합니다. `widget_mode_user_layout_presets`의 version 1 JSON에 `{id,name,layout}` 목록을 저장하고 `widget_mode_user_layout_id`는 선택한 프리셋을 가리킵니다. 기본 배치 레지스트리와 분리하며 각 `layout`은 자유 구성 검증을 통과해야 합니다. 색상·글꼴과 실제 데이터/창 위치는 프리셋에 포함하지 않습니다.
- 이름은 앞뒤 공백을 정리한 1~80자, 대소문자 무시 중복 금지이며 ID는 UUID입니다. 최대 100개, JSON 2MiB를 제한합니다. 읽기·CRUD는 분리된 데이터를 반환하며 손상/미래 버전 읽기는 원본 설정을 덮어쓰지 않습니다.
- 꾸미기의 `내 배치`는 썸네일 목록과 이름 변경·삭제를 제공합니다. 기본 배치로 전환해도 사용자 프리셋 목록은 유지하며 선택 ID만 해제합니다. 프리셋 삭제는 현재 자유 구성 좌표를 지우지 않습니다.
- 런타임 `FreeLayoutCanvas`는 저장 좌표의 비율로 배치합니다. 작은 창에서 데이터 요소 내용은 내부 스크롤, 날짜/시계는 글꼴 맞춤으로 표시하며 전체 내용은 도움말/접근성 이름에도 제공합니다.
- 유형별 목록은 기존 캐시·원본 ID·처리기를 공유합니다. 통합 목록 필터는 통합 목록에만 적용합니다. 원본 데이터 복제나 별도 완료 저장은 하지 않습니다.
- 자유 구성의 창 좌표·크기는 `free` 키로 분리합니다. 달력 요소의 표시 여부로 창 좌표 키를 바꾸지 않습니다. 꾸미기의 글꼴/달력·시계 표시를 적용해도 명시적으로 프리셋을 선택하기 전에는 자유 구성을 유지합니다.
- 주간 버튼은 동일 너비이며 요일/날짜를 별도 타이포그래피로 그립니다. 선택일은 은은한 배경과 짧은 강조선, 오늘은 점, 키보드 포커스는 윤곽선으로 구분하며 글자/배경 불투명도를 따릅니다.
- 회귀: `test_widget_free_layout_model.py`, `test_widget_free_layout_runtime.py`, `test_widget_week_strip.py`, `test_widget_editor_removal.py`. 화면 검증: `scripts/validate_widget_free_layout.py`.
- 프리셋 회귀: `test_widget_layout_presets.py`, `test_widget_layout_presets_controller.py`, `test_widget_layout_presets_customization.py`. 화면·임시 INI 재시작 검증: `scripts/validate_widget_layout_presets.py`.

- 배치 레지스트리: `presentation/widgets/widget_mode_skins.py`(파일 이름은 이전 호환을 위해 유지), 표면 모양: `presentation/widgets/widget_mode_surfaces.py`
- 선택 설정: 표면 모양 `QSettings["widget_mode_surface"]`, 배치 `QSettings["widget_mode_layout"]`
- 색상은 메인 테마를 따르며 위젯 전용 모드에서 따로 덮어쓰지 않습니다. 표면 모양은 색을 바꾸지 않습니다.
- 레이아웃은 `WidgetModeLayout`의 grid 배치표, 권장 크기, 행/열 stretch, 섹션별 UI 밀도를 정의합니다.
- 배치와 표면 모양 선택은 서로 변경하지 않습니다.
- 배치 메뉴는 레지스트리를 순회하므로 새 배치 등록 시 셸이나 컨트롤러를 수정하지 않습니다.
- 기존 `widget_mode_panel_theme` 설정은 읽지 않으며 메인 창의 테마를 따릅니다.
- 토큰 합성 순서: 메인 테마 토큰 → 표면 모양(모서리·항목 모양) → 가독성 보정.

```python
from calendar_app.presentation.widgets.widget_mode_skins import (
    WidgetModeLayout,
    register_widget_mode_layout,
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
```
