# 텍스트 위젯 템플릿 엔진

## 개요

`OverlayTextWidget` (`overlay_text.py`)은 변수·조건식을 포함한 템플릿 문자열을 렌더링합니다.
타이머는 `window_ui_actions.py`가 관리하고, 위젯은 `refresh_template(tier, registry, app_data)`를 받아 처리합니다.

## 갱신 계층 (Tier)

| Tier | 주기 | 포함 변수 |
|---|---|---|
| `fast` | 100ms | `{stopwatch:id}`, `{time}`, `{time:tz=...}` |
| `med` | 1s | `{countdown:id}` |
| `slow` | 60s | `{date}`, `{weekday}`, `{dday:id}`, `{task_count}`, `{directive_count}`, `{next_event}`, `{custom_var}` |

빠른 변수를 slow tier로 호출하면 업데이트가 지연됩니다.

## 변수 문법

### 기본 변수
```
{time}              현재 시각 (기본 포맷)
{date}              오늘 날짜
{weekday}           요일 이름
{task_count}        오늘 태스크 수
{directive_count}   디렉티브 수
{next_event}        다음 일정 제목
{custom_var}        사용자 정의 변수 (기본 키)
{custom_var:key}    사용자 정의 변수 (특정 키)
```

### 시간대 지정
```
{time:tz=JST:%H:%M}      JST 시간대, HH:MM 포맷
{time:tz=UTC+9:%H:%M}    UTC+9, HH:MM 포맷
{time:tz=EST:%I:%M %p}   EST, 12시간제
```

### 크로스 위젯 참조
```
{stopwatch:stopwatch_0}   stopwatch_0 인스턴스의 경과시간
{countdown:countdown_0}   countdown_0 인스턴스의 남은시간
{dday:dday_0}             dday_0 인스턴스의 D-Day 문자열
```

인스턴스 ID는 `overlay_manager.widget_registry()`에서 확인합니다.

## 위젯별 템플릿 변수

### Clock (`clock_template`)
```
{time:%H:%M}    시각 (커스텀 포맷)
{date}          날짜
{weekday}       요일
{tz_label}      시간대 약어 (예: KST, JST)
```

### Stopwatch (`sw_template`)
```
{elapsed}       HH:MM:SS.T 전체 문자열
{hours}         시간 (숫자)
{minutes}       분 (숫자)
{seconds}       초 (숫자)
{tenths}        1/10초
{status}        "running" / "paused" / "stopped"
{status_icon}   ▶ / ⏸ / ⏹
```

### DateCard (`dc_template`)
```
{weekday}         요일 전체 이름
{weekday:short}   요일 약어 (Mon, Tue ...)
{day}             일 (숫자)
{date}            YYYY-MM-DD
{month}           월 이름
{year}            연도
{doy}             연중 몇 번째 날
```

### Countdown (`cd_template`)
```
{remaining}         HH:MM:SS 남은시간 문자열
{days}              남은 일수
{hours}             남은 시간
{minutes}           남은 분
{seconds}           남은 초
{target}            목표 일시 (기본 포맷)
{target:YYYY-MM-DD} 목표 일시 (커스텀 포맷)
```

### D-Day (`dd_template`)
```
{dday}          "D-42" 형태 문자열
{days}          숫자만 (42)
{sign}          "-" 또는 "+"
{label}         사용자 지정 이름
{date:fmt}      목표 날짜 (커스텀 포맷)
{date_short}    M/D 형태 약식 날짜
```

## 조건식

```
{if cond}참일때{/if}
{if cond}참일때{else}거짓일때{/if}
```

- `{else}` 는 선택 사항
- 중첩 불가
- 비교 연산자: `== != < > <= >=`
- RHS 시간 단위: `1h` (1시간), `30m` (30분), `90s` (90초)

### 예시
```
{if countdown:countdown_0 < 30m}⚠️ 곧 종료{else}정상{/if}
{if task_count > 0}{task_count}개 남음{else}완료!{/if}
{if dday:dday_0 == D-0}오늘이에요!{/if}
```

## 인라인 스타일

변수에 `|` 로 스타일 힌트를 추가합니다:

```
{time|size=36|bold}                → 36pt 볼드
{date|color=#ff4da6|italic}        → 핑크 이탤릭
{task_count|size=24|bold|color=#0f0}
```

렌더링 결과: `<span style="font-size:36pt; font-weight:bold;">22:30</span>`

줄바꿈: `\n` → `<br>`

## resolve_template 함수 시그니처

```python
def resolve_template(
    template: str,
    countdown_remaining,   # 현재 countdown 값
    stopwatch_text,        # 현재 stopwatch 값
    app_data: dict,        # task_count, next_event 등
    widget_registry: dict, # inst_id → widget
) -> str:
```

`overlay_template_utils.py`에 구현되어 있습니다.

## 라이브 프리뷰 에디터

`_action_edit_text()` 에서 열리는 템플릿 편집기:
- `QSplitter`: 좌측 에디터 + 우측 프리뷰 레이블
- 300ms debounce QTimer로 변경마다 프리뷰 갱신
- 힌트 패널: 변수 카테고리 + 조건식 예시 표시
