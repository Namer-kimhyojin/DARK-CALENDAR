# -*- Dark Calendar — CLAUDE.md -*-
# 이 파일은 Claude Code가 이 프로젝트에서 작업할 때 참조하던 지침서입니다.
# 현재 기준 문서는 AGENTS.md이며, 이 파일은 호환용 보조 지침으로 유지합니다.

## 프로젝트 개요

- **앱 이름**: Dark Calendar v2.8.3
- **플랫폼**: Windows (PyQt6 데스크톱 앱)
- **언어**: Python 3.x, PyQt6 6.10.2
- **UI 언어**: 한국어 (i18n 지원 — `infrastructure/i18n.py`)
- **진입점**: `main.py` → `calendar_app/bootstrap.py` → `OverlayApp`
- **설정 저장**: `QSettings("kimhyojin", "Dark Calendar")`
- **DB**: SQLite, 경로는 `calendar_app/app_paths.py`의 `DB_PATH`

---

## 기준 문서

Claude로 작업하더라도 최신 기준은 **[AGENTS.md](AGENTS.md)** 입니다.

이 파일에는 Claude 작업 중 자주 참고하던 보조 규칙과 UI 구현 지침을 함께 둡니다. 두 문서가 충돌하면 `AGENTS.md`와 `rules/` 하위 문서를 우선합니다.

---

## 아키텍처 핵심 구조

```
calendar_app/
  bootstrap.py                  — QApplication 생성, splash, DB init, 단일 인스턴스 잠금
  app_metadata.py               — APP_NAME, APP_VERSION 등 상수
  app_paths.py                  — DB_PATH, LOG_PATH, APP_ICON_PATH
  domain/                       — 순수 도메인 (모델, 정책, 유효성 검사)
  application/                  — 유스케이스 레이어
  infrastructure/
    db/                         — SQLite 레포지토리
    google_sync/                — Google Calendar 동기화 엔진
    ics/                        — ICS 구독 fetcher
    nlp/                        — KR/EN 자연어 태스크 파싱
    runtime/                    — 앱 인프라, 단축키, 시스템 연동
    sync/                       — google_sync 호환 래퍼
  presentation/
    main_window/                — 메인 윈도우 mixin 조립 구조
    panels/                     — 좌/우/하단 패널 렌더링
    dialogs/                    — 각종 설정/입력 다이얼로그
    widgets/                    — 오버레이 위젯 시스템
    calendar/                   — MonthRenderer
    theme/                      — UI 토큰, 스타일, 애니메이션
  shared/                       — 공유 유틸리티
```

세부 구조는 `AGENTS.md`와 `rules/architecture.md`를 우선 확인합니다.

---

## ActionHandlersMixin 조립 구조

`app_window.py`의 `OverlayApp`은 다음 순서로 mixin을 상속합니다.

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
    DialogActionsMixin,   # dialog_router.py
    TaskActionsMixin,     # 반드시 DialogActionsMixin 뒤
)
```

새 mixin을 추가할 때는 `action_handlers.py`의 `ActionHandlersMixin`에 포함하고 MRO 충돌을 확인합니다. `DialogActionsMixin`은 반드시 `TaskActionsMixin` 앞에 위치해야 합니다.

---

## 인코딩 정책 (필수 — CI + pre-commit 강제)

작성하거나 수정하는 **모든 `.py` 파일**은 아래 규칙을 준수합니다.

1. 파일 첫 줄은 반드시 `# -*- coding: utf-8 -*-`
2. `encoding=` 키워드는 항상 `"utf-8"` 사용
   - 예외: `calendar_app/preset_manager.py`의 `ascii`, `scripts/fix_encoding.py`의 `cp949`/`utf-8-sig`
3. `encoding="utf-8"`을 쓰면 반드시 `errors=`를 함께 명시
   - 내부 파일/깨끗한 데이터: `errors="strict"`
   - 외부 입력/API/사용자 데이터: `errors="replace"`
   - `errors="ignore"` 금지
4. 텍스트 모드 `open()`은 `encoding="utf-8", errors=...` 필수
5. `Path.read_text()` / `Path.write_text()`도 `encoding="utf-8", errors=...` 필수
6. `subprocess.run/Popen/check_output(text=True)`는 `encoding="utf-8", errors=...` 필수
7. `.encode("utf-8")` / `.decode("utf-8")`에는 `errors=` 인자를 명시

빠른 참조:

```python
open(path, "r", encoding="utf-8", errors="strict")
Path(p).read_text(encoding="utf-8", errors="strict")
some_bytes.decode("utf-8", errors="replace")
subprocess.run(cmd, text=True, encoding="utf-8", errors="strict")
```

강제 도구:

- Pre-commit: `.pre-commit-config.yaml` → `python scripts/run_encoding_guard.py`
- CI: `.github/workflows/encoding-policy.yml`
- 테스트: `tests/test_encoding_policy.py`, `tests/test_encoding_utils.py`

---

## 주요 구현 기능

### 패널 선택

- `app.selected_directive_ids = set()` — 디렉티브 다중 선택 상태
- `app._panel_task_frames = {}` — dict: tid → (QFrame, bg_color)
- `app._panel_directive_frames = {}` — dict: did → (QFrame, bg_color)
- `_PanelItemFilter(QObject)` — 클릭=선택, 더블클릭=편집
- keyPressEvent: ESC → `clear_panel_selections`, Del → 디렉티브 삭제 우선, 그 다음 태스크

### 오버레이 위젯 시스템

- `app.overlay_manager` (`OverlayWidgetManager`) — 인스턴스 JSON 영속화 (`QSettings["overlay_instances"]`)
- 인스턴스 ID 예: `"clock_0"`, 설정 prefix: `"oi_clock_0_font_size"` (via `_SettingsProxy`)
- 7종 위젯: `clock`, `stopwatch`, `date_card`, `countdown`, `dday`, `text`, `weather`
- 모든 위젯: `_open_settings(initial_tab)` → 기본 탭 + 고급 템플릿 탭
- `widget_registry()` → inst_id → widget dict (크로스 위젯 참조용)
- `refresh_all_texts(tier=)` — text 위젯 템플릿 갱신
- `set_app_data_provider(callback)` — 앱 데이터 변수 콜백 등록

### 텍스트 위젯 템플릿 엔진

갱신 계층:

- fast (100ms): `{stopwatch:id}`, `{time}`, `{time:tz=JST:%H:%M}`
- med (1s): `{countdown:id}`
- slow (60s): `{date}`, `{weekday}`, `{dday:id}`, `{task_count}`, `{directive_count}`, `{next_event}`, `{custom_var}`

지원 문법:

- 조건식: `{if cond}true{else}false{/if}` (`{else}` 선택, 중첩 불가)
- 인라인 스타일: `{var|size=36|bold|italic|color=#ff4da6}`

### i18n

- `infrastructure/i18n.py` — `t(key, fallback)` 번역 함수
- 번들 로케일: `locales/` (`ko.json`, `en.json` 등)
- 사용자 오버라이드: `LOCALAPPDATA/DarkCalendar/locales_user/`
- 런타임 언어 전환: `system_menu.py`의 언어 선택 메뉴

### NLP 태스크 생성

- `infrastructure/nlp/nlp_engine.py` — `parse_nlp_task(text)` (KR/EN)
- CommandPalette (`Ctrl+Space`) → `cmd_id="create_task_nlp"` → `app.handle_palette_command()`
- 상대 날짜, 요일, 시간, 자연어 제목 추출 지원

### 멀티 캘린더

- 캘린더 타입: `gcal` | `local` | `shared` | `ics`
- DB 테이블 `calendar`: `id TEXT PK`, `type`, `name`, `color`, `is_default`, `is_active`, `is_visible`, `sort_order`
- Shared DB: `C:\Users\Public\DarkCalendar\shared.db`
- `calendar_repo.py`: `migrate_from_gcal_subscription()` — bootstrap에서 최초 1회 실행

---

## UI/UX 아이콘 시스템 (qtawesome)

### 현황

- `requirements.txt`에 `qtawesome>=1.4.2`가 명시되어 있습니다.
- 진입점은 `calendar_app/shared/icon_map.py`입니다.
- `ICON` 상수와 `icon(key, color=None)` 헬퍼를 사용합니다.
- `qtawesome` import 실패 시 `icon()`은 빈 `QIcon()`으로 graceful fallback합니다.

### 아이콘 색상 규칙

- 아이콘 색상에는 `text_primary`처럼 `#RRGGBB` hex 문자열을 사용합니다.
- `text_secondary`는 `rgba(...)` 형식일 수 있어 qtawesome 색상 인자로 부적합합니다.
- `derive_text_palette()` 반환값을 쓸 때 `text_primary`는 아이콘 색상에 사용 가능하고, `text_secondary`는 직접 넘기지 않습니다.

```python
icon(ICON.LOCK, color=text_primary_hex)   # 권장
```

### 메뉴 라벨 이모지 중복 방지

- 로케일 문자열에 이모지가 포함될 수 있으므로 `setIcon()`과 함께 쓸 때는 텍스트를 정리합니다.
- `strip_leading_emoji()` 또는 `_se` alias를 사용합니다.

```python
from calendar_app.shared.icon_map import ICON, icon as _ic, strip_leading_emoji as _se

act = menu.addAction(_se(t("menu.some_key", "설정")), handler)
act.setIcon(_ic(ICON.SETTINGS))
```

- `top_menus/common.py`의 `format_top_menu_button_text()`는 상단 QToolButton 텍스트에 자동 적용됩니다.
- `infra_wiring.py`의 `_create_action()`도 글로벌 메뉴 액션에 자동 적용합니다.

---

## 모달 다이얼로그 구현 지침

새 다이얼로그 작성 시 아래 패턴을 기본으로 사용합니다.

```python
from PyQt6.QtWidgets import QDialog, QFrame, QVBoxLayout

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
)
from calendar_app.shared.icon_map import strip_leading_emoji as _se


class MyDialog(QDialog):
    def __init__(self, parent=None, theme_color=None):
        super().__init__(parent)
        apply_dialog_title(self, _se(t("dialog.my_title", "제목")))
        apply_common_dialog_style(self, minimum_width=480, theme_color=theme_color)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(8)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        footer_layout, self.ok_btn, self.cancel_btn = build_dialog_footer(
            t("btn.ok", "확인"),
            t("btn.cancel", "취소"),
        )
        root.addLayout(footer_layout)
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
```

핵심 규칙:

- 기반 클래스는 `QDialog` 또는 태스크 전용 `BaseTaskDialog(QDialog)` 사용
- 제목은 `apply_dialog_title()`로 설정
- 공통 스타일은 `apply_common_dialog_style()` 호출
- footer는 가능한 `build_dialog_footer()` 사용
- 모달 실행은 `dialog.exec()` 사용
- 직접 `setStyleSheet()`로 공통 스타일을 덮어쓰지 않기
- 모든 라벨/버튼 텍스트는 `t()` 사용

버튼 objectName:

- 기본/저장: `primary_btn`
- 취소/보조: `ghost_btn`
- 위험 작업: 새 코드에서는 `danger_btn` 권장
- 기존 코드에는 `DangerBtn` 레거시 사용처가 남아 있으므로, 수정 범위 밖이면 일부러 바꾸지 않습니다.

권장 최소 폭:

- 단순 확인/알림: `minimum_width=360`
- 폼 입력: `minimum_width=480`
- 복잡한 설정: `minimum_width=600`
- 전체 설정/다중 탭: `minimum_width=720` 이상

---

## 테스트

```bash
pytest
pytest tests/test_encoding_policy.py
python scripts/run_encoding_guard.py
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

## 세부 규칙

주제별 상세 규칙은 `rules/` 폴더를 우선 참조합니다.

| 파일 | 내용 |
|---|---|
| [rules/encoding.md](rules/encoding.md) | 인코딩 정책 전체 규칙 |
| [rules/architecture.md](rules/architecture.md) | 레이어 구조, Mixin 조립, 상태 변수 초기화 |
| [rules/database.md](rules/database.md) | 스키마 변경 원칙, 마이그레이션 |
| [rules/gcal_sync.md](rules/gcal_sync.md) | GCal 동기화 흐름, 금지 사항 |
| [rules/task_dialog.md](rules/task_dialog.md) | create/move/copy 흐름, calendar_id 전파 |
| [rules/overlay_widgets.md](rules/overlay_widgets.md) | 오버레이 위젯 추가 절차 |
| [rules/template_engine.md](rules/template_engine.md) | 템플릿 변수 문법 |
| [rules/i18n.md](rules/i18n.md) | 번역 키 사용법 |
| [rules/panel_selection.md](rules/panel_selection.md) | 패널 선택 상태와 키보드 처리 |

현재 작업 상태 및 미완료 항목은 [TASKS.md](TASKS.md)를 참조합니다.

---

## 절대 하지 말 것

### DB 스키마

- `database_unified.py`의 기존 테이블 DDL을 직접 수정하지 말 것
- 컬럼 추가/변경은 반드시 `ALTER TABLE` 마이그레이션으로 처리
- `gcal_subscription` 테이블을 삭제하거나 rename하지 말 것
- `calendar` 테이블로의 마이그레이션은 `calendar_repo.migrate_from_gcal_subscription()`이 담당

### task_dialog_unified.py

- 수정 시 create / move / copy 세 흐름을 모두 검증할 것
- `calendar_id`를 `task_data`에서 누락하지 말 것

### GCal 동기화

- `google_sync/engine.py`의 `_active_sync_calendar_ids` 로직을 임의로 변경하지 말 것
- `_push_local_changes_to_google` 수정 시 중복 생성, 대상 캘린더 필터링, delete queue drain을 반드시 확인할 것

### 인코딩

- `.py` 파일 저장 시 BOM(UTF-8-sig) 없이 순수 UTF-8로 저장할 것
- `errors="ignore"`는 절대 사용하지 말 것
- 변수명 `l`, `O`, `I` 사용 금지 (ruff E741)

### UI/UX 아이콘

- `icon()` 색상 인자로 `rgba(...)` 값을 넘기지 말 것
- 메뉴 action text에 이모지가 포함될 수 있으면 `_se()`를 적용할 것

### app_initializer.py

- 새 상태 변수 추가 시 `initialize_overlay_app()` 안에 초기화 코드를 넣을 것

### action_handlers.py

- 새 mixin 추가 시 MRO 순서를 확인할 것
- `DialogActionsMixin`은 반드시 `TaskActionsMixin` 앞에 위치해야 함

---

## 주의사항 (건드리면 안 되는 파일)

아래 파일은 기존 기능과 강하게 결합되어 있으므로 수정 전 전체 영향을 파악합니다.

| 파일 | 이유 |
|---|---|
| `infrastructure/db/database_unified.py` | 스키마 DDL 전체, 특히 `gcal_subscription` 테이블 |
| `infrastructure/db/db_repository_unified.py` | GCal 구독 list/upsert/delete |
| `infrastructure/google_sync/engine.py` | `_active_sync_calendar_ids`, `_push_local_changes_to_google` |
| `presentation/dialogs/gcal_settings_dialog.py` | 5탭 GCal 설정 다이얼로그 |
| `presentation/dialogs/task_dialog_unified.py` | UnifiedTaskDialog (create/move/copy 흐름) |
| `presentation/dialogs/dialog_router.py` | `_DIALOG_ROUTE_MAP` + `DialogActionsMixin` |
| `presentation/main_window/top_menus/system_menu.py` | 언어 선택 + 옵션 메뉴 |
| `presentation/main_window/action_handlers.py` | `ActionHandlersMixin` MRO 조립 |
