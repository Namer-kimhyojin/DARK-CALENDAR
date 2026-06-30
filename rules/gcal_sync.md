# Google Calendar 동기화 규칙

## 핵심 파일

| 파일 | 역할 |
|---|---|
| `infrastructure/google_sync/engine.py` | 동기화 핵심 로직 |
| `infrastructure/google_sync/service.py` | 서비스 래퍼 |
| `infrastructure/google_sync/repository.py` | GCal DB 어댑터 |
| `infrastructure/google_sync/common.py` | `is_gcal_enabled()`, `get_default_gcal_calendar_id()` |
| `infrastructure/google_sync/helpers.py` | `sync_task_to_google()`, `delete_task_from_google()` |
| `infrastructure/db/db_repository_unified.py` | `gcal_subscription` 테이블 CRUD |

## GCal 동기화 흐름

```
앱 시작
  → app_initializer.py: app.init_gcal_sync_timer()
  → action_handlers_gcal.py: GCalActionsMixin
  → refresh_gcal_sync_state(authenticate_silently=True)
  → background_worker.py: SyncWorker (비동기)
  → engine.py: 풀 싱크 or 증분 싱크
```

## 증분 동기화 설정

```python
_GCAL_DELETE_MAX_RETRIES = 5
_SYNC_TOKEN_FAIL_LIMIT = 3
_INCREMENTAL_BACKFILL_LOOKBACK_DAYS = 120
_INCREMENTAL_BACKFILL_LOOKAHEAD_DAYS = 400
```

sync token이 만료되거나 실패 카운트 초과 시 풀 싱크로 fallback.

## GCal 캘린더 ID 해결 순서

```python
def _get_default_gcal_id(app) -> str:
    # 1. app.settings의 gcal_calendar_id 확인
    # 2. "primary" alias → 실제 ID로 resolve
    # 3. 없으면 DB 기본 gcal 캘린더 사용
    return get_default_gcal_calendar_id()
```

## 설정 키

| QSettings 키 | 용도 |
|---|---|
| `gcal_calendar_id` | 기본 GCal 캘린더 ID |
| `gcal_sync_token::{calendar_id}` | 증분 sync token |
| `gcal_sync_token_fails::{calendar_id}` | sync token 실패 카운트 |
| `gcal_bound_calendar_id` | 바인딩된 캘린더 ID |

## GCalSettingsDialog

`presentation/dialogs/gcal_settings_dialog.py` — 5탭 설정 다이얼로그.
탭 구조를 변경할 때는 탭 인덱스에 의존하는 코드가 없는지 확인해야 합니다.
