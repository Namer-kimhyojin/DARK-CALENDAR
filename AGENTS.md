# -*- Dark Calendar — AGENTS.md -*-
# Codex가 이 프로젝트에서 작업할 때 가장 먼저 참조하는 기준 지침서입니다.

## 프로젝트 개요

- **앱 이름**: Dark Calendar
- **플랫폼**: Windows 데스크톱 앱
- **언어/프레임워크**: Python 3.x, PyQt6 6.10.2
- **UI 언어**: 한국어 기본, i18n 지원 (`calendar_app/infrastructure/i18n.py`)
- **진입점**: `main.py` → `calendar_app/bootstrap.py` → `OverlayApp`
- **설정 저장**: `QSettings("kimhyojin", "Dark Calendar")`
- **DB**: SQLite, 기본 경로는 `calendar_app/app_paths.py`의 `DB_PATH`

---

## 작업 원칙

1. 변경 전에 관련 코드와 `rules/` 문서를 먼저 확인합니다.
2. 기존 아키텍처, mixin 조립, UI 스타일, 저장 방식에 맞춰 최소 범위로 수정합니다.
3. 사용자 변경분을 되돌리지 않습니다. dirty worktree에서는 내 작업 범위만 건드립니다.
4. `.py` 파일을 수정하면 인코딩 정책을 반드시 지킵니다.
5. DB/GCal/태스크 다이얼로그 변경은 회귀 위험이 크므로 관련 흐름을 함께 확인합니다.
6. 문서와 코드가 충돌하면 실제 코드와 `rules/` 하위 상세 문서를 우선합니다.

---

## 핵심 구조

```
calendar_app/
  bootstrap.py                  — QApplication, splash, DB init, 단일 인스턴스 잠금
  app_paths.py                  — DB_PATH, LOG_PATH, APP_ICON_PATH
  domain/                       — 순수 도메인 모델, 정책, 검증
  application/                  — 유스케이스 레이어
  infrastructure/
    db/                         — SQLite 레포지토리와 마이그레이션
    google_sync/                — Google Calendar 동기화 엔진
    ics/                        — ICS 구독 fetcher
    nlp/                        — KR/EN 자연어 태스크 파싱
    runtime/                    — 앱 인프라, 단축키, 시스템 연동
    sync/                       — google_sync 호환 래퍼
  presentation/
    main_window/                — OverlayApp, action mixin, 상단 메뉴, dock
    panels/                     — 좌/우/하단 패널 렌더링
    dialogs/                    — 태스크/설정/관리 다이얼로그
    widgets/                    — 오버레이 위젯 시스템
    calendar/                   — MonthRenderer
    theme/                      — UI 토큰, 스타일, 애니메이션
  shared/                       — 공용 유틸리티
```

레이어 의존 방향:

- `domain`: UI/DB 의존 없음
- `application`: domain 중심
- `infrastructure`: DB, Google, OS 연동 구현
- `presentation`: PyQt6 UI와 사용자 상호작용
- `shared`: 레이어 공용 유틸

---

## ActionHandlersMixin

`OverlayApp` 조립 순서:

```python
class OverlayApp(MainWindowUiActionsMixin, ActionHandlersMixin, WindowEventsMixin, QMainWindow)
```

`ActionHandlersMixin` 조립 순서:

```python
class ActionHandlersMixin(
    WindowShellActionsMixin,
    CalendarViewActionsMixin,
    RoutineActionsMixin,
    AwayLockMixin,
    ThemeActionsMixin,
    RefreshSchedulerMixin,
    GCalActionsMixin,
    DialogActionsMixin,   # dialog_router.py
    TaskActionsMixin,     # 반드시 DialogActionsMixin 뒤
)
```

새 action mixin을 추가할 때는 `calendar_app/presentation/main_window/action_handlers.py`에 포함하고 MRO 충돌을 확인합니다. `DialogActionsMixin`은 `TaskActionsMixin` 앞에 둡니다.

---

## 인코딩 정책 (필수)

작성하거나 수정하는 모든 `.py` 파일은 아래 규칙을 지킵니다.

- 첫 줄: `# -*- coding: utf-8 -*-`
- `encoding=` 값은 `"utf-8"`만 사용
- `encoding="utf-8"`을 쓰면 항상 `errors=`를 함께 명시
- 내부 파일/깨끗한 데이터: `errors="strict"`
- 외부 입력/API/사용자 데이터: `errors="replace"`
- `errors="ignore"` 금지
- 텍스트 모드 `open()`, `Path.read_text()`, `Path.write_text()`, `subprocess.*(text=True)`는 `encoding`과 `errors` 필수
- `.encode("utf-8")`, `.decode("utf-8")`에도 `errors=` 명시

예외:

- `calendar_app/preset_manager.py`: `ascii` 허용
- `scripts/fix_encoding.py`: `cp949`, `utf-8-sig` 허용

빠른 예:

```python
open(path, "r", encoding="utf-8", errors="strict")
Path(path).read_text(encoding="utf-8", errors="strict")
payload.decode("utf-8", errors="replace")
subprocess.run(cmd, text=True, encoding="utf-8", errors="strict")
```

검증:

```bash
python scripts/run_encoding_guard.py
pytest tests/test_encoding_policy.py tests/test_encoding_utils.py
```

---

## 상태 변수와 초기화

새 `app.*` 상태 변수를 추가하면 반드시 `calendar_app/presentation/main_window/app_initializer.py`의 `initialize_overlay_app()`에서 초기화합니다.

누락하면 재시작, 잠금 해제, 패널 재렌더링 등에서 `AttributeError`가 발생할 수 있습니다.

---

## 태스크 다이얼로그 주의사항

주요 파일:

- `calendar_app/presentation/dialogs/task_dialog_unified.py`
- `calendar_app/presentation/dialogs/task_dialog_base.py`
- `calendar_app/presentation/dialogs/dialog_router.py`
- `calendar_app/application/task_dialog_usecases.py`

규칙:

- `task_dialog_unified.py` 수정 시 create / move / copy 세 흐름을 모두 확인합니다.
- `calendar_id`를 `task_data`에서 누락하지 않습니다.
- 새 다이얼로그 route는 `dialog_router.py`의 `_DIALOG_ROUTE_MAP`과 `DialogActionsMixin` 흐름을 확인합니다.

---

## DB / 캘린더 규칙

주요 파일:

- `calendar_app/infrastructure/db/database_unified.py`
- `calendar_app/infrastructure/db/calendar_repo.py`
- `calendar_app/infrastructure/db/db_repository_unified.py`
- `calendar_app/infrastructure/db/shared_db.py`

규칙:

- 기존 테이블 DDL을 직접 고쳐 기존 사용자 DB를 깨뜨리지 않습니다.
- 컬럼 추가/변경은 `ALTER TABLE` 마이그레이션으로 처리합니다.
- `gcal_subscription` 테이블은 삭제하거나 rename하지 않습니다.
- `calendar` 테이블 마이그레이션은 `calendar_repo.migrate_from_gcal_subscription()`이 담당합니다.
- 캘린더 타입은 `gcal` | `local` | `shared` | `ics`입니다.
- Shared DB 경로는 `C:\Users\Public\DarkCalendar\shared.db`입니다.

---

## GCal 동기화 규칙

주요 파일:

- `calendar_app/infrastructure/google_sync/engine.py`
- `calendar_app/infrastructure/google_sync/service.py`
- `calendar_app/infrastructure/google_sync/repository.py`
- `calendar_app/infrastructure/google_sync/common.py`
- `calendar_app/infrastructure/google_sync/helpers.py`

## UI / 다이얼로그 규칙

공통 다이얼로그:

- 스타일: `calendar_app/presentation/dialogs/dialog_styles.py`
- 제목 정리: `calendar_app/presentation/dialogs/dialog_emoji.py`
- 가능한 `apply_common_dialog_style()`과 `build_dialog_footer()`를 사용합니다.
- 모달 실행은 `dialog.exec()`를 사용합니다.
- 공통 스타일을 직접 `setStyleSheet()`로 덮어쓰지 않습니다.
- 모든 사용자 표시 문자열은 `t(key, fallback)`를 사용합니다.

버튼 objectName:

- 기본/저장: `primary_btn`
- 취소/보조: `ghost_btn`
- 위험 작업: 새 코드에서는 `danger_btn` 권장
- 기존 코드의 `DangerBtn`은 레거시입니다. 수정 범위 밖이면 일부러 바꾸지 않습니다.

아이콘:

- `requirements.txt`에 `qtawesome>=1.4.2`가 있습니다.
- 아이콘 진입점은 `calendar_app/shared/icon_map.py`의 `ICON`, `icon()`, `strip_leading_emoji()`입니다.
- 아이콘 색상에는 `#RRGGBB` hex 값을 사용합니다.
- `rgba(...)` 값을 qtawesome 색상 인자로 넘기지 않습니다.
- `setIcon()`과 이모지 포함 번역 문자열을 함께 쓰면 `_se()`로 라벨 앞 이모지를 제거합니다.

```python
from calendar_app.shared.icon_map import ICON, icon as _ic, strip_leading_emoji as _se

act = menu.addAction(_se(t("menu.settings", "설정")), handler)
act.setIcon(_ic(ICON.SETTINGS, color=text_primary_hex))
```

---

## 주요 기능 메모

패널 선택:

- `app.selected_directive_ids = set()`
- `app._panel_task_frames = {}`
- `app._panel_directive_frames = {}`
- ESC는 선택 해제, Del은 디렉티브 우선 삭제 후 태스크 삭제

오버레이 위젯:

- 관리 객체: `app.overlay_manager` (`OverlayWidgetManager`)
- 인스턴스 저장: `QSettings["overlay_instances"]`
- 설정 prefix: `oi_<inst_id>_`
- 종류: `clock`, `stopwatch`, `date_card`, `countdown`, `dday`, `text`, `weather`
- 텍스트 템플릿 갱신: fast 100ms, med 1s, slow 60s

i18n:

- 번역 함수: `calendar_app/infrastructure/i18n.py`의 `t()`
- 번들 로케일: `locales/`
- 사용자 오버라이드: `LOCALAPPDATA/DarkCalendar/locales_user/`
- 언어 전환 메뉴: `presentation/main_window/top_menus/system_menu.py`

NLP:

- `calendar_app/infrastructure/nlp/nlp_engine.py`의 `parse_nlp_task(text)`
- CommandPalette `cmd_id="create_task_nlp"`

---

## 테스트 / 빌드

테스트:

```bash
pytest
pytest tests/test_encoding_policy.py
python scripts/run_encoding_guard.py
```

빌드:

- `build-release.bat` — 로컬 빌드부터 MSIX/스토어 업로드 패키지까지 실행하는 단일 진입점
- `scripts/build_pipeline.ps1` — 통합 배치파일이 호출하는 내부 빌드 구현
- `build_store.py` — 배포 페이로드 정리와 기본 DB 생성
- `DarkCalendar.spec`, `Standalone.spec` — PyInstaller 스펙

---

## 상세 규칙 문서

작업 주제와 관련된 파일은 먼저 읽습니다.

| 파일 | 내용 |
|---|---|
| [rules/encoding.md](rules/encoding.md) | 인코딩 정책 |
| [rules/architecture.md](rules/architecture.md) | 레이어 구조, mixin, 상태 초기화 |
| [rules/database.md](rules/database.md) | 스키마 변경, 마이그레이션 |
| [rules/gcal_sync.md](rules/gcal_sync.md) | GCal 동기화 |
| [rules/task_dialog.md](rules/task_dialog.md) | 태스크 create/move/copy, `calendar_id` |
| [rules/overlay_widgets.md](rules/overlay_widgets.md) | 오버레이 위젯 |
| [rules/template_engine.md](rules/template_engine.md) | 텍스트 위젯 템플릿 |
| [rules/i18n.md](rules/i18n.md) | 번역 키와 로케일 |
| [rules/panel_selection.md](rules/panel_selection.md) | 패널 선택과 키보드 처리 |

현재 진행 상태는 [TASKS.md](TASKS.md)를 참고합니다.

---

## 수정 전 영향도 확인 파일

아래 파일은 결합도가 높으므로 수정 전에 호출부와 테스트를 함께 확인합니다.

| 파일 | 이유 |
|---|---|
| `calendar_app/infrastructure/db/database_unified.py` | 스키마 DDL과 마이그레이션 |
| `calendar_app/infrastructure/db/db_repository_unified.py` | GCal 구독 list/upsert/delete |
| `calendar_app/infrastructure/google_sync/engine.py` | GCal push/pull 핵심 로직 |
| `calendar_app/presentation/dialogs/gcal_settings_dialog.py` | 5탭 GCal 설정 다이얼로그 |
| `calendar_app/presentation/dialogs/task_dialog_unified.py` | 태스크 create/move/copy 흐름 |
| `calendar_app/presentation/dialogs/dialog_router.py` | 다이얼로그 라우팅 |
| `calendar_app/presentation/main_window/top_menus/system_menu.py` | 언어 선택과 시스템 메뉴 |
| `calendar_app/presentation/main_window/action_handlers.py` | action mixin MRO |
