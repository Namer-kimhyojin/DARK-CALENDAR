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
  → engine.py: 인증 및 삭제 큐 처리
  → Google pull (풀 싱크 or 증분 싱크)
  → 원격/로컬 변경 충돌 판정
  → pull 결과 DB 반영 및 sync token 저장
  → 로컬 dirty 일정 Google push
  → 필요 시 고아 일정 검사
```

로컬 변경을 전송하기 전에 원격 변경을 먼저 확인합니다. 원격이 마지막 동기화 이후
변경됐다면 충돌 큐에 스냅샷을 저장하고 원격 버전을 우선 적용합니다. 원격이 변경되지
않은 로컬 dirty 일정은 pull에서 덮어쓰지 않고 이후 push 단계에서 전송합니다.

## 데이터 안전 규칙

- 페이지가 끝까지 조회되지 않은 결과는 적용하지 않습니다. 일부 페이지 결과로 전체
  동기화의 누락 일정을 판정하면 안 됩니다.
- 전체 동기화에서 원격에 없는 로컬 미러는 즉시 삭제하지 않고
  `gcal_deleted_task_archive`에 스냅샷을 저장한 뒤 보관 처리합니다.
- 기존 이벤트 수정은 pull에서 확인한 `updated` 값과 update 직전 원격 값을 비교합니다.
  값이 다르면 push를 중단하고 다음 pull에서 충돌로 처리합니다.
- Google update 요청에는 가능한 경우 원격 ETag를 `If-Match`로 전달합니다.
- ETag 조건을 적용할 수 없는 batch update는 사용하지 않습니다. 신규 일정 생성만
  결정적 event ID를 사용한 batch create를 허용합니다.
- pull 적용 실패가 있으면 해당 주기에는 로컬 push를 실행하지 않습니다.
- pull 적용이 3회 연속 실패하면 새 sync token으로 강제 진행하지 않고 기존 token을
  비워 다음 주기에 안전한 전체 동기화를 수행합니다.
- 삭제 큐는 최대 5회 자동 재시도합니다. 한도 초과 항목은 삭제하지 않고 진단 화면에
  보존하여 사용자가 오류를 확인하고 수동 재시도할 수 있게 합니다.

## 증분 동기화 설정

```python
_GCAL_DELETE_MAX_RETRIES = 5
_SYNC_TOKEN_FAIL_LIMIT = 3
_INCREMENTAL_BACKFILL_LOOKBACK_DAYS = 120
_INCREMENTAL_BACKFILL_LOOKAHEAD_DAYS = 400
```

sync token이 만료되거나 실패 카운트 초과 시 풀 싱크로 fallback.

증분 백필 검사는 실제 API 조회가 성공한 뒤에만 실행 날짜를 저장합니다. 네트워크
오류가 발생하면 같은 날 다음 동기화에서 다시 시도할 수 있어야 합니다.

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
| `gcal_apply_fail_streak::{calendar_id}` | pull DB 적용 연속 실패 횟수 |
| `gcal_incremental_backfill_probe::{calendar_id}` | 마지막 증분 백필 성공 날짜 |
| `gcal_auto_heal_orphans_last_run` | 마지막 고아 일정 자동 검사 시각 |

## 실패 상태와 사용자 조치

- push/pull/삭제 부분 실패는 `GCalSyncIssuesDialog`와 동기화 완료 메시지에 표시합니다.
- 충돌은 로컬/원격 스냅샷을 함께 저장하고 사용자가 `로컬 유지` 또는
  `구글 버전 적용`을 선택할 수 있게 합니다.
- 삭제 큐가 5회 실패하면 상태를 `재시도 한도 초과`로 표시합니다. `재시도`를 누르면
  오류와 재시도 횟수를 초기화하고 즉시 동기화를 요청합니다.

## GCalSettingsDialog

`presentation/dialogs/gcal_settings_dialog.py` — 5탭 설정 다이얼로그.
탭 구조를 변경할 때는 탭 인덱스에 의존하는 코드가 없는지 확인해야 합니다.
