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

## 위젯별 상태 저장 키

| 위젯 | 상태 키 | 타이머 |
|---|---|---|
| Stopwatch | `sw_elapsed_ms`, `sw_running`, `sw_started_mono` | 100ms, 자체 관리 |
| Countdown | `cd_target_iso` | 1000ms, 자체 관리 |
| Clock | `tz_offset_mins` (None=로컬) | 1000ms |
| D-Day | `dd_target_date` (yyyy-MM-dd), `dd_label` | 60s, 자체 관리 |

**Stopwatch/Countdown/DDday 위젯**은 자체 디스플레이를 직접 관리합니다 — 공유 push refresh 없음.

## 크로스 위젯 참조

```python
# widget_registry()로 다른 위젯 값 참조 가능
registry = manager.widget_registry()  # {inst_id: widget}
manager.refresh_all_texts(tier="fast")  # text 위젯 전체 갱신

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
