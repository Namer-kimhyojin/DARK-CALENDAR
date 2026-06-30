# 데이터베이스 규칙

## 스키마 변경 원칙

### 절대 하지 말 것
- `database_unified.py`의 **기존 테이블 DDL을 직접 수정**하지 말 것
- `gcal_subscription` 테이블을 **삭제하거나 rename**하지 말 것

### 올바른 변경 방법
컬럼 추가/변경은 반드시 **`ALTER TABLE` 마이그레이션**으로 처리합니다:

```python
# database_unified.py 내 마이그레이션 예시
def _migrate_v3(conn):
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN calendar_id TEXT")
    except Exception:
        pass  # 이미 컬럼이 있으면 무시
```

이유: 기존 유저 DB 보존 — DDL 직접 수정 시 기존 설치본에서 테이블 재생성이 안 됨.

## 주요 테이블

| 테이블 | 파일 | 비고 |
|---|---|---|
| `tasks` | `task_repo.py` | 태스크 메인 테이블 |
| `directives` | `directive_repo.py` | 디렉티브 (지시사항) |
| `routines` | `routine_repo.py` | 루틴 정의 |
| `calendar` | `calendar_repo.py` | 멀티 캘린더 (personal DB) |
| `gcal_subscription` | `db_repository_unified.py` | **삭제 금지** — `calendar`로 마이그레이션 중 |
| `checklists` | `checklist_repo.py` | 체크리스트 항목 |

## calendar 테이블 스키마

```sql
CREATE TABLE calendar (
    id              TEXT PRIMARY KEY,   -- "gcal::primary", "local::메모", "ics::hash"
    type            TEXT NOT NULL,      -- 'gcal' | 'local' | 'shared' | 'ics'
    name            TEXT,
    color           TEXT,
    is_default      INTEGER DEFAULT 0,
    is_active       INTEGER DEFAULT 1,
    is_visible      INTEGER DEFAULT 1,
    gcal_calendar_id TEXT,              -- type='gcal'인 경우만
    ics_url         TEXT,               -- type='ics'인 경우만
    ics_last_fetched TEXT,
    sort_order      INTEGER DEFAULT 0
)
```

## GCal 구독 → calendar 마이그레이션

`calendar_repo.py`의 `migrate_from_gcal_subscription()`이 bootstrap에서 최초 1회 실행됩니다.

- `gcal_subscription` 테이블 데이터를 읽어 `calendar` 테이블에 삽입
- 이미 마이그레이션된 경우 재실행 방지 플래그 확인

```python
# bootstrap.py에서 호출됨
from calendar_app.infrastructure.db.calendar_repo import migrate_from_gcal_subscription
migrate_from_gcal_subscription()
```

## 기본 캘린더 자동 생성

`calendar` 테이블이 비어있을 때 기본 로컬 캘린더를 자동 생성합니다 (5ea7d0a).
`calendar_repo.py`의 `ensure_default_calendar()` 참조.

## calendar_id 필수 전파

태스크 생성/수정 시 `calendar_id`를 `task_data`에서 누락하지 말 것.
→ DB 저장 시 `calendar_id=NULL`이 되어 마이그레이션 전 상태로 퇴행 (76988f5).

```python
# task_data에 반드시 포함
task_data = {
    "title": ...,
    "calendar_id": calendar_id,   # ← 필수
    ...
}
```

## DB 경로

```python
# calendar_app/app_paths.py
DB_PATH          # 개인 DB (기본 경로)
SHARED_DB_PATH   # C:\Users\Public\DarkCalendar\shared.db (PC공유 캘린더)
```

## 레포지토리 진입점

- `infrastructure/db/db_repository.py` — 통합 레포지토리 진입점 (대부분의 코드는 여기서 임포트)
- 레포지토리를 직접 임포트할 때는 `infrastructure/db/` 하위 모듈에서 직접 가져옵니다:
  ```python
  from calendar_app.infrastructure.db import task_repo, directive_repo
  ```
