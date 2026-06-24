# -*- Dark Calendar — CLAUDE.md -*-
# 이 파일은 Claude Code가 이 프로젝트에서 작업할 때 항상 참조하는 지침서입니다.

## 프로젝트 개요

- **앱 이름**: Dark Calendar v2.8.3
- **플랫폼**: Windows (PyQt6 데스크톱 앱)
- **언어**: Python 3.x, PyQt6 6.10.2
- **UI 언어**: 한국어 (i18n 지원 — `infrastructure/i18n.py`)
- **진입점**: `main.py` → `calendar_app/bootstrap.py` → `OverlayApp`
- **설정 저장**: `QSettings("kimhyojin", "Dark Calendar")`
- **DB**: SQLite, 경로는 `calendar_app/app_paths.py`의 `DB_PATH`

---

## 아키텍처 핵심 구조

```
calendar_app/
  bootstrap.py                  — QApplication 생성, splash, DB init, 단일 인스턴스 잠금
  app_metadata.py               — APP_NAME, APP_VERSION 등 상수
  app_paths.py                  — DB_PATH, LOG_PATH, APP_ICON_PATH
  domain/                       — 순수 도메인 (모델, 정책, 유효성 검사)
    task_constants.py           — PRIORITY_MENU_ITEMS, STATUS_MENU_ITEMS, load_custom_labels()
    task_status_view.py         — normalize_status()
    task_validation.py
    routine_cycle.py            — cycle_display_name(), cycle_order_value()
    policies/routine_policy.py
  application/                  — 유스케이스 레이어
    task_usecases.py
    task_management_usecases.py
    task_delete_usecases.py
    task_dialog_usecases.py
    directive_management_usecases.py
    routine_usecases.py
    routine_management_usecases.py
    routine_advanced_service.py
    routine_batch_generator.py
    focus_usecases.py
    eod_usecases.py
    review_usecases.py
    pomodoro_engine.py
    common_status_usecases.py
    common_task_ops_usecases.py
  infrastructure/
    db/                         — SQLite 레포지토리
      database_unified.py       — 스키마 초기화 (테이블 생성/마이그레이션)
      db_repository.py          — 통합 레포지토리 진입점
      db_repository_unified.py  — GCal 구독 list/upsert/delete
      calendar_repo.py          — calendar 테이블 CRUD + GCal 마이그레이션
      task_repo.py
      routine_repo.py
      directive_repo.py         — delete_directives(ids)
      checklist_repo.py
      search_repo.py
      shared_db.py              — C:\Users\Public\DarkCalendar\shared.db
      unified_repo.py
      _adapter_proxy.py
    google_sync/                — Google Calendar 동기화 엔진
      engine.py                 — 핵심 동기화 로직
      service.py                — 서비스 래퍼
      repository.py             — GCal DB 어댑터
      common.py                 — is_gcal_enabled(), get_default_gcal_calendar_id()
      helpers.py                — sync_task_to_google(), delete_task_from_google()
    ics/
      ics_fetcher.py            — ICS 구독 fetcher
    nlp/
      nlp_engine.py             — parse_nlp_task() (KR/EN 자연어 → 태스크 파싱)
    i18n.py                     — t(), list_available_locale_codes(), resolve_locale_file_path()
    runtime/
      infra_manager.py          — setup_app_infrastructure()
      infra_wiring.py
      system_manager.py
      keyboard_shortcuts.py     — get_key(), build_shortcut_guide_html()
      crash_bootstrap.py
      idle_detector.py
      app_bar_handler.py
      network.py
    sync/
      calendar_sync_service.py  — google_sync/service.py 호환 래퍼
      gcal_db_adapter.py
      gcal_sync_helpers.py
      sync_handlers.py
  presentation/
    main_window/                — 메인 윈도우 (mixin 조립 구조)
      app_window.py             — OverlayApp (QMainWindow + 모든 mixin 조립)
      app_initializer.py        — initialize_overlay_app(): 앱 상태 변수 초기화
      window_ui_actions.py      — MainWindowUiActionsMixin (keyPressEvent, 폰트/레이블, 타이머)
      window_events.py          — WindowEventsMixin
      action_handlers.py        — ActionHandlersMixin (모든 action mixin 조립 루트)
      action_handlers_tasks.py  — TaskActionsMixin (태스크/디렉티브 액션)
      action_handlers_gcal.py   — GCalActionsMixin (GCal 동기화 타이머)
      away_lock_actions.py      — AwayLockMixin
      calendar_view_actions.py  — CalendarViewActionsMixin
      routine_actions.py        — RoutineActionsMixin
      theme_actions.py          — ThemeActionsMixin
      refresh_scheduler.py      — RefreshSchedulerMixin
      window_shell_actions.py   — WindowShellActionsMixin
      ui_builder.py             — setup_main_ui(), setup_idle_lock_ui()
      top_bar_builder.py
      top_bar_menu_factory.py
      dock_factory.py
      dock_sections/
        left_center_docks.py
        right_docks.py
        floating_dock_behavior.py
        dock_layout_presets.py
      top_menus/
        register_menu.py
        work_menu.py
        display_menu.py
        widgets_menu.py
        system_menu.py         — build_system_menu() (언어 선택 포함)
        common.py
    panels/
      side_panel_renderer.py    — 좌/우/하단 패널 렌더링 (3개 패널 전체)
    dialogs/
      task_dialog_unified.py    — UnifiedTaskDialog (태스크 생성/수정)
      task_dialog_base.py
      dialog_router.py          — DialogActionsMixin + _DIALOG_ROUTE_MAP
      gcal_settings_dialog.py   — GCalSettingsDialog (5탭)
      gcal_sync_issues_dialog.py
      directive_dialog.py
      management_dialogs.py
      modify_task_dialog_unified.py
      routine_recurrence_wizard.py
      routine_bulk_operations_dialog.py
      checklist_manager_dialog_advanced.py
      eod_report_dialog.py
      focus_log_dialog.py
      focus_completion_dialog.py
      focus_task_selector.py
      pomodoro_settings_dialog.py
      help_center_dialog.py
      panel_color_picker_dialog.py
      label_settings_dialog.py
      dialog_token_editor_dialog.py
      dialog_styles.py
      dialog_editor_styles.py
      away_settings_dialog.py
      color_swatch_widget.py
      time_picker_widget.py
      recurring_event_dialog.py
      dialog_emoji.py           — apply_dialog_title()
    widgets/
      overlay_manager.py        — OverlayWidgetManager (오버레이 인스턴스 관리)
      overlay_manager_dialog.py — 관리 다이얼로그
      overlay_base.py           — 공통 베이스 + _overlay_menu_style
      overlay_clock.py
      overlay_clock_widget.py   — 6종 위젯 구현체 (Clock, Stopwatch, DateCard, Countdown, DDday, Text)
      overlay_stopwatch.py
      overlay_countdown.py
      overlay_datecard.py
      overlay_dday.py
      overlay_text.py
      overlay_weather.py        — OverlayWeatherWidget (날씨 위젯, 7종)
      overlay_widgets.py
      overlay_template_utils.py
      overlay_color_utils.py
      overlay_measure_utils.py
      overlay_preset_logic.py
      overlay_preset_service.py
      overlay_preset_store.py
      overlay_preset_ui_service.py
      alarm_checker.py
      alarm_popup.py
      command_palette.py        — CommandPalette (Ctrl+Space)
      panel_widget_style.py
      panel_widget_mode.py
      ui_components.py          — install_hover_info()
    calendar/
      month_renderer.py         — MonthRenderer
    theme/
      ui_tokens.py              — get_ui_shape_tokens()
      style_builder.py
      animations.py
    layout_manager.py
    drag_drop_manager.py
    context_menu_manager.py
    focus_mode.py
  splash_screen.py              — SplashScreen
  shared/                       — 공유 유틸리티
    background_worker.py        — SyncWorker, AuthWorker, DbTaskWorker
    calendar_defaults.py
    color_utils.py
    datetime_utils.py           — parse_datetime_str(), timezone_offset_for_name()
    encoding_utils.py           — read_text_with_legacy_fallback()
    google_color_palette.py     — color_id_to_hex()
    i18n.py
    qt_helpers.py               — find_parent_dock()
    search_utils.py             — matches_search_query()
    tag_highlighter.py
    value_parsers.py
    ui_tokens.py                — get_ui_tokens()
    theme_settings.py           — get_theme_color(), fpt()
    theme_snapshot.py
    icon_map.py                 — ICON 상수, icon()
```

---

## ActionHandlersMixin 조립 구조

`app_window.py`의 `OverlayApp`은 다음 순서로 mixin을 상속합니다:

```python
class OverlayApp(MainWindowUiActionsMixin, ActionHandlersMixin, WindowEventsMixin, QMainWindow)

class ActionHandlersMixin(
    WindowShellActionsMixin,
    CalendarViewActionsMixin,
    RoutineActionsMixin,
    AwayLockMixin,
    ThemeActionsMixin,
    RefreshSchedulerMixin,
    GCalActionsMixin,
    DialogActionsMixin,   # ← dialog_router.py
    TaskActionsMixin,
)
```

새 mixin을 추가할 때는 `action_handlers.py`의 `ActionHandlersMixin`에 포함해야 합니다.

---

## 인코딩 정책 (필수 — CI + pre-commit 강제)

> 작성하거나 수정하는 **모든 `.py` 파일**은 아래 규칙을 준수해야 합니다.
> 위반 시 pre-commit 및 CI가 차단됩니다.

### 규칙

1. **파일 첫 줄**: `# -*- coding: utf-8 -*-`

2. **`encoding=` 키워드** → 항상 `"utf-8"` (cp949, latin-1 등 금지)
   - 예외 화이트리스트: `calendar_app/preset_manager.py` (ascii), `scripts/fix_encoding.py` (cp949/utf-8-sig)

3. **`encoding="utf-8"`** → 반드시 `errors=` 함께 명시
   - `errors="strict"` — 내부 파일/데이터 (반드시 깨끗한 UTF-8 보장 시)
   - `errors="replace"` — 외부 입력 (API 응답, 사용자 데이터 등)
   - `errors="ignore"` **금지**

4. **`open()` 텍스트 모드** → `encoding="utf-8", errors=...` 필수
   바이너리 모드 (`"rb"`, `"wb"`) 는 면제

5. **`Path.read_text()` / `Path.write_text()`** → `encoding="utf-8", errors=...` 필수

6. **`subprocess.run/Popen/check_output(text=True)`** → `encoding="utf-8", errors=...` 필수

7. **`.encode("utf-8")` / `.decode("utf-8")`** → `errors=` 두 번째 인자 필수
   예: `.decode("utf-8", errors="replace")`

### 빠른 참조

```python
# 파일 I/O
open(path, "r", encoding="utf-8", errors="strict")
Path(p).read_text(encoding="utf-8", errors="strict")

# 외부/API 데이터
some_bytes.decode("utf-8", errors="replace")

# subprocess
subprocess.run(cmd, text=True, encoding="utf-8", errors="strict")
```

### 강제 도구
- Pre-commit: `.pre-commit-config.yaml` → `python scripts/run_encoding_guard.py`
- CI: `.github/workflows/encoding-policy.yml`
- 테스트: `tests/test_encoding_policy.py`, `tests/test_encoding_utils.py`

---

## 주요 구현 기능 (참조용)

### 패널 선택 (Panel Selection)
- `app.selected_directive_ids = set()` — 디렉티브 다중 선택 상태
- `app._panel_task_frames = {}` — dict: tid → (QFrame, bg_color)
- `app._panel_directive_frames = {}` — dict: did → (QFrame, bg_color)
- `_PanelItemFilter(QObject)` — 클릭=선택, 더블클릭=편집
- keyPressEvent: ESC → `clear_panel_selections`, Del → 디렉티브 삭제 우선, 그 다음 태스크

### 오버레이 위젯 시스템
- `app.overlay_manager` (OverlayWidgetManager) — 인스턴스 JSON 영속화 (`QSettings["overlay_instances"]`)
- 인스턴스 ID 예: `"clock_0"`, 설정 prefix: `"oi_clock_0_font_size"` (via `_SettingsProxy`)
- **7종 위젯**: `clock`, `stopwatch`, `date_card`, `countdown`, `dday`, `text`, **`weather`**
- 모든 위젯: `_open_settings(initial_tab)` → 기본탭 + 고급 템플릿 탭
- `widget_registry()` → inst_id → widget dict (크로스 위젯 참조용)
- `refresh_all_texts(tier=)` — text 위젯 템플릿 갱신
- `set_app_data_provider(callback)` — 앱 데이터 변수 콜백 등록

### 텍스트 위젯 템플릿 엔진
계층별 갱신 (`window_ui_actions.py`가 타이머 관리):
- fast (100ms): `{stopwatch:id}`, `{time}`, `{time:tz=JST:%H:%M}`
- med (1s): `{countdown:id}`
- slow (60s): `{date}`, `{weekday}`, `{dday:id}`, `{task_count}`, `{directive_count}`, `{next_event}`, `{custom_var}`

조건식: `{if cond}true{else}false{/if}` (중첩 불가, `{else}` 선택)

인라인 스타일: `{var|size=36|bold|italic|color=#ff4da6}` → `<span style="...">value</span>`

### i18n (국제화)
- `infrastructure/i18n.py` — `t(key, fallback)` 번역 함수
- 번들 로케일: `locales/` 디렉터리 (`ko.json`, `en.json` 등)
- 사용자 오버라이드: `LOCALAPPDATA/DarkCalendar/locales_user/`
- 런타임 언어 전환: `system_menu.py`에서 언어 선택 가능

### NLP 태스크 생성
- `infrastructure/nlp/nlp_engine.py` — `parse_nlp_task(text)` (KR/EN)
- CommandPalette (`Ctrl+Space`) → `cmd_id="create_task_nlp"` → `app.handle_palette_command()`
- 지원: 상대 날짜 (내일/tomorrow), 요일, 시간 (오후/AM/PM), 자연어 제목 추출

### 멀티 캘린더
`memory/multi_calendar_design.md` 참조.
- 캘린더 타입: `gcal` | `local` | `shared` | `ics`
- DB 테이블 `calendar` (personal DB): `id TEXT PK`, `type`, `name`, `color`, `is_default`, `is_active`, `is_visible`, `sort_order`
- Shared DB: `C:\Users\Public\DarkCalendar\shared.db` (all PC users r/w)
- `calendar_repo.py`: `migrate_from_gcal_subscription()` — bootstrap에서 최초 1회 실행

### UI/UX 아이콘 시스템 (qtawesome)

**의존성**: `qtawesome>=1.4.2` — `requirements.txt`에 명시됨. 미설치 시 `icon()` 전부 빈 `QIcon()` 반환.

**진입점**: `shared/icon_map.py`
- `ICON` 열거형 — 모든 아이콘 상수 정의
- `icon(key, color=None)` → `QIcon` 반환 (ImportError 시 빈 아이콘으로 graceful fallback)
- `strip_leading_emoji(text)` — 메뉴 레이블 앞 이모지/특수문자 제거

**아이콘 색상 규칙 (필수)**:
- 항상 `text_primary` (hex `#RRGGBB`) 사용
- `text_secondary` **절대 금지** → `rgba(r,g,b,a)` 형식은 `QColor` 파싱 실패 → qtawesome이 `#000000`(검정)으로 렌더링
- `derive_text_palette()` 반환값: `text_primary`=hex, `text_secondary`=rgba — 둘은 절대 혼용 금지

```python
# 올바름
icon(ICON.LOCK, color=_tb_text)       # _tb_text = text_primary (hex)

# 틀림 — 검정 아이콘 버그 발생
icon(ICON.LOCK, color=_tb_text2)      # _tb_text2 = text_secondary (rgba, 무효)
```

**메뉴 레이블 이모지 중복 방지**:
- 모든 로케일 파일(`locales/*.json`)의 메뉴 키는 이모지 접두사를 포함함
- `setIcon()` + 이모지 텍스트 동시 사용 시 아이콘이 중복 표시됨
- 반드시 `strip_leading_emoji()` (또는 `_se` alias)로 텍스트 전처리 후 사용

```python
from calendar_app.shared.icon_map import strip_leading_emoji as _se

act = menu.addAction(_se(t("menu.some_key")), handler)
act.setIcon(_ic(ICON.SOME_ICON))
```

- `format_top_menu_button_text()` (`top_menus/common.py`) — 탑바 QToolButton 텍스트에 자동 적용
- `_create_action()` (`infra_wiring.py`) — 트레이 메뉴 액션에 자동 적용

---

## 테스트

```bash
pytest                          # 전체 테스트
pytest tests/test_encoding_policy.py   # 인코딩 정책 검사
python scripts/run_encoding_guard.py   # pre-commit 체크와 동일
```

- `pytest.ini`: `testpaths = tests`, `norecursedirs = backups build dist .venv`
- UI 위젯 테스트는 `QApplication` 픽스처 필요 (`tests/support.py` 참조)

---

## 빌드 / 배포

- `build.ps1` — 로컬 빌드
- `build_store.py` — MSIX 스토어 빌드
- `bundle-msix.ps1` — MSIX 번들링
- `build-store-release.ps1` — 스토어 릴리스 패키지
- `DarkCalendar.spec`, `Standalone.spec` — PyInstaller 스펙
- `AppxManifest.xml` — MSIX 매니페스트
- `release/store/DarkCalendar_x64.msixupload` — 스토어 제출 아티팩트

---

## 세부 규칙 (rules/)

각 주제별 상세 규칙은 `rules/` 폴더의 개별 파일을 참조하세요.

| 파일 | 내용 |
|---|---|
| [rules/encoding.md](rules/encoding.md) | 인코딩 정책 전체 규칙 + 빠른 참조 |
| [rules/architecture.md](rules/architecture.md) | 레이어 구조, Mixin 조립, 상태 변수 초기화 |
| [rules/database.md](rules/database.md) | 스키마 변경 원칙, 마이그레이션, calendar 테이블 |
| [rules/gcal_sync.md](rules/gcal_sync.md) | GCal 동기화 흐름, 금지 사항, 설정 키 |
| [rules/task_dialog.md](rules/task_dialog.md) | create/move/copy 3가지 흐름, calendar_id 전파 |
| [rules/overlay_widgets.md](rules/overlay_widgets.md) | 위젯 종류, 인스턴스 관리, 새 위젯 추가 절차 |
| [rules/template_engine.md](rules/template_engine.md) | 템플릿 변수 문법, 조건식, 인라인 스타일 |
| [rules/i18n.md](rules/i18n.md) | 번역 키 사용법, 로케일 파일 구조 |
| [rules/panel_selection.md](rules/panel_selection.md) | 패널 선택 상태, 키보드 처리, 비주얼 갱신 |

---

## 진행 중 작업

→ 현재 작업 상태 및 미완료 항목은 **[TASKS.md](TASKS.md)** 참조

---

## 절대 하지 말 것

실제 버그 이력 기반 규칙입니다. 아래 실수들은 모두 과거에 실제로 발생했습니다.

### DB 스키마
- `database_unified.py`의 기존 테이블 DDL을 직접 수정하지 말 것
  → 컬럼 추가/변경은 반드시 `ALTER TABLE` 마이그레이션으로 (기존 유저 DB 보존)
- `gcal_subscription` 테이블을 삭제하거나 rename하지 말 것
  → `calendar` 테이블로의 마이그레이션은 `calendar_repo.migrate_from_gcal_subscription()`이 담당

### task_dialog_unified.py
- 수정 시 **create / move / copy** 3가지 흐름을 모두 검증할 것
  → `dialog_router.py`가 세 흐름을 조립하며, 한 곳만 고치면 나머지가 깨진다 (7454dc0)
- `calendar_id`를 `task_data`에서 누락하지 말 것
  → DB 저장 시 `calendar_id=NULL`이 되어 마이그레이션 전 상태로 퇴행 (76988f5)

### GCal 동기화
- `google_sync/engine.py`의 `_active_sync_calendar_ids` 로직을 임의로 변경하지 말 것
  → GCal push 대상 캘린더 필터링에 직접 영향, 잘못 건드리면 전체 이벤트 중복 생성

### 인코딩
- `.py` 파일 저장 시 BOM(UTF-8-sig) 없이 순수 UTF-8로 저장할 것
  → BOM이 포함되면 `# -*- coding: utf-8 -*-` 헤더가 인식되지 않아 CI 실패 (c61b43f)
- `errors="ignore"` 절대 사용 금지 → 데이터 무결성 침해, pre-commit이 차단함
- pre-commit ruff가 파일을 auto-fix/reformat한 경우 커밋이 실패함
  → `git add` 재실행 후 다시 `git commit` 해야 함 (자동 수정본이 스테이징 안 됨)
- 변수명 `l`, `O`, `I` 사용 금지 (ruff E741: ambiguous variable name)
  → lambda 캡처 변수도 포함: `lambda checked, l=x:` → `lambda checked, lc=x:` 로

### UI/UX 아이콘
- `qtawesome` 미설치 시 `icon()` 전부 빈 박스로 렌더링됨 → `requirements.txt` 확인 필수
- 아이콘 색상으로 `text_secondary` (rgba 형식) 절대 금지 → 검정 아이콘 버그
  → `text_primary` (hex `#RRGGBB`) 만 사용 (289290c, 33da571)
- 메뉴 action text에 `t()` 결과 그대로 쓰면 이모지 + qtawesome 아이콘 중복 렌더링
  → `strip_leading_emoji()` / `_se()` 적용 필수 (33da571)

### app_initializer.py
- 새 상태 변수 추가 시 `initialize_overlay_app()` 안에 초기화 코드를 넣을 것
  → 빠뜨리면 앱 재시작 시 `AttributeError`로 크래시

### action_handlers.py
- 새 mixin을 `ActionHandlersMixin`에 추가할 때 MRO 순서에 주의할 것
  → `DialogActionsMixin`은 반드시 `TaskActionsMixin` 앞에 위치해야 한다

---

## 주의사항 (건드리면 안 되는 파일)

아래 파일들은 기존 기능과 강하게 결합되어 있어 수정 시 반드시 전체 영향을 파악해야 합니다.

| 파일 | 이유 |
|------|------|
| `infrastructure/db/database_unified.py` | 스키마 DDL 전체, 특히 gcal_subscription 테이블 |
| `infrastructure/db/db_repository_unified.py` | GCal 구독 list/upsert/delete |
| `infrastructure/google_sync/engine.py` | `_active_sync_calendar_ids`, `_push_local_changes_to_google` |
| `presentation/dialogs/gcal_settings_dialog.py` | 5탭 GCal 설정 다이얼로그 |
| `presentation/dialogs/task_dialog_unified.py` | UnifiedTaskDialog (create/move/copy 3가지 흐름) |
| `presentation/dialogs/dialog_router.py` | `_DIALOG_ROUTE_MAP` + `DialogActionsMixin` |
| `presentation/main_window/top_menus/system_menu.py` | `build_system_menu` (언어 선택 + 옵션 메뉴) |
| `presentation/main_window/action_handlers.py` | `ActionHandlersMixin` MRO 조립 |
