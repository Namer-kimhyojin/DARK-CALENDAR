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

- Google 이벤트 identity는 원본 캘린더 ID와 이벤트 ID를 함께 사용합니다. 다른
  캘린더의 같은 이벤트 ID를 수정·보관·중복 제거·삭제 큐 판정의 근거로 사용하지 않습니다.
  소속이 모호하거나 원본 연결 DB를 읽지 못하면 새 원격 사본을 만들지 않고 보류합니다.
- 앱에 연결되지 않은 원격 일정은 관찰만 합니다. 연결 부재 또는 제목·날짜 일치만으로
  자동 연결하거나 원격 삭제 대기열에 넣지 않습니다. 사용자가 요청한 삭제는 기존 큐를 사용합니다.
- `primary` 별칭을 실제 계정 ID로 이전할 때 기존 일정·원본/대상 링크·표시/기본 설정·
  삭제 큐를 함께 보존하며, identity 충돌 시 savepoint 전체를 rollback합니다.
- 이전 실제 계정 ID와 별칭 소속 증거가 있으면 새 계정·확인 불능 상태에서 메타데이터와
  원격 쓰기를 진행하지 않습니다. 인증 완료 후 실제 primary를 확인하기 전에는 후보
  token을 저장하거나 기존 연결을 바꾸지 않으며, 실패·취소의 후보 token은 폐기합니다.
- 조회 404만으로 가져오기·표시 선택을 해제하지 않습니다. 삭제 409나 batch callback
  누락, 취소·삭제 완료의 로컬 저장 실패를 전체 성공으로 계산하지 않습니다.
- 페이지가 끝까지 조회되지 않은 결과는 적용하지 않습니다. 일부 페이지 결과로 전체
  동기화의 누락 일정을 판정하면 안 됩니다.
- 전체 동기화에서 원격에 없는 로컬 미러는 즉시 삭제하지 않고
  `gcal_deleted_task_archive`에 스냅샷을 저장한 뒤 보관 처리합니다.
- 기존 이벤트 수정은 pull에서 확인한 `updated` 값과 update 직전 원격 값을 비교합니다.
  값이 다르면 push를 중단하고 다음 pull에서 충돌로 처리합니다.
- 즉시 전송과 정기 전송은 DB에 저장된 마지막 서버 `updated` 값을 같은 기준으로 사용합니다.
  성공 시각을 원격 수정 시각으로 대신 저장하지 않습니다. 기준이 없는 과거 연결은 기존 전체
  조회 경로로 다시 확인하며, 확인 전 즉시 덮어쓰지 않습니다.
- 충돌 스냅샷 저장과 원격 내용 반영은 같은 DB 트랜잭션에 속합니다. 스냅샷 저장 실패 시
  원격 내용·sync token을 적용하지 않습니다. `로컬 유지`는 저장된 로컬 내용을 복원하고
  확인된 원격 기준을 유지한 채 기존 dirty 전송 경로에 다시 넣습니다.
- Google update 요청에는 가능한 경우 원격 ETag를 `If-Match`로 전달합니다.
- ETag 조건을 적용할 수 없는 batch update는 사용하지 않습니다. 신규 일정 생성만
  결정적 event ID를 사용한 batch create를 허용합니다.
- 개별·batch create는 공통 스냅샷 비교로 직전 현재 DB 행을 다시 확인합니다. 재조회 실패·로컬 삭제·스냅샷 변경은
  원격 생성을 보류하며 해당 주기의 개별 전송 fallback에 다시 넣지 않습니다.
- pull 적용 실패가 있으면 해당 주기에는 로컬 push를 실행하지 않습니다.
- pull 적용이 3회 연속 실패하면 새 sync token으로 강제 진행하지 않고 기존 token을
  비워 다음 주기에 안전한 전체 동기화를 수행합니다.
- 삭제 큐는 최대 5회 자동 재시도합니다. 한도 초과 항목은 삭제하지 않고 진단 화면에
  보존하여 사용자가 오류를 확인하고 수동 재시도할 수 있게 합니다.
- 사용자가 명시한 Google 일정 이동에 실패하면 선택한 대상과 dirty 상태를 보존합니다.
  원래 캘린더를 수정하거나 다른 캘린더에서 복구해 성공으로 처리하지 않습니다.
  원본이 없을 때는 이전 이동의 완료 여부를 선택한 대상에서만 확인합니다. 대상에서도
  확인할 수 없으면 새 사본을 생성하지 않고 이동 확인 필요 상태로 재시도합니다.
- Google 이동 성공 후 로컬 링크 저장이 실패해도 동기화 성공으로 표시하지 않습니다.
  같은 대상에서 재확인하고 연결을 저장할 수 있도록 이동 연결 저장 필요 상태를 유지합니다.
- 실제 Google 이벤트 ID가 없는 로컬·ICS·공유 신규 일정의 오래된 Google 경로 필드는
  전송 근거로 사용하지 않습니다. 실제 이벤트와 연결된 기존 로컬 소유 일정은 호환합니다.

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
    # 1. 활성·쓰기 가능하며 is_default=1인 DB Google 캘린더
    # 2. 사용 가능한 기존 gcal_calendar_id 또는 Google 연결 fallback
    # 3. "primary"는 계정의 실제 primary ID로 resolve
    return get_default_gcal_calendar_id(app.settings)
```

앱의 기본 저장 대상은 `calendar.is_default`가 기준입니다. 메인 달력과 관리 화면은
`application/calendar_preferences.py`의 `set_default_calendar(..., repository=calendar_repo)`를
같이 사용합니다. 기본 선택은 기존 일정의 소속·원격 링크·삭제 대기열을 변경하지 않습니다.
로컬·다른 서비스 기본값은 해당 서비스에 저장하며, Google 연결 fallback과 분리합니다.
`gcal_primary_resolved_id`는 계정의 primary identity이므로 팀·가족 기본값 변경으로 덮어쓰지 않습니다.

## 설정 키

| QSettings 키 | 용도 |
|---|---|
| `gcal_calendar_id` | 기존 Google 연결 fallback·호환 저장 대상 (앱 기본값은 DB) |
| `gcal_import_selection_configured` | 가져오기 선택을 명시 저장했는지 여부 |
| `gcal_sync_token::{calendar_id}` | 증분 sync token |
| `gcal_sync_token_fails::{calendar_id}` | sync token 실패 카운트 |
| `gcal_bound_calendar_id` | 바인딩된 캘린더 ID |
| `gcal_apply_fail_streak::{calendar_id}` | pull DB 적용 연속 실패 횟수 |
| `gcal_incremental_backfill_probe::{calendar_id}` | 마지막 증분 백필 성공 날짜 |
| `gcal_auto_heal_orphans_last_run` | 마지막 고아 일정 자동 검사 시각 |

## 실패 상태와 사용자 조치

- 저장 토큰 갱신 중 전송·시간 초과·일시 서버 오류는 기존 토큰을 보존하고 재시도 가능한
  실패로 처리합니다. 이 오류를 401·재로그인 필요로 바꾸거나 로그인 창을 열지 않습니다.
  `invalid_grant` 등 확인된 OAuth 거부만 재인증으로 연결하며, 설정용 독립 조회 서비스도
  실제 실패 종류를 보존합니다. 응답 원문·설명·토큰은 진단 로그에 기록하지 않습니다.
- push/pull/삭제 부분 실패는 `GCalSyncIssuesDialog`와 동기화 완료 메시지에 표시합니다.
- 충돌은 로컬/원격 스냅샷을 함께 저장하고 사용자가 `로컬 유지` 또는
  `구글 버전 적용`을 선택할 수 있게 합니다.
- 삭제 큐가 5회 실패하면 상태를 `재시도 한도 초과`로 표시합니다. `재시도`를 누르면
  오류와 재시도 횟수를 초기화하고 즉시 동기화를 요청합니다.

## GCalSettingsDialog

`presentation/dialogs/gcal_settings_dialog.py` — 계정 연결·가져올 캘린더·동기화 설정·문제 해결·설정 도움말의 5개 섹션.
Google 설정에는 별도의 기본 저장 대상 선택이나 ICS/로컬 관리 UI를 두지 않습니다.
가져오기 선택은 초안으로 유지하고 저장 시 하나의 savepoint로 적용합니다. 읽기 전용 캘린더도
가져올 수 있습니다. 기본 저장 캘린더의 가져오기를 해제하거나 쓰기 권한이 사라지면 활성·쓰기 가능한
로컬 우선으로 기본값을 재지정합니다. 기존 기본값을 사용할 수 없고 대체 대상도 없으면 전체 선택을 보존하고 실패를 안내합니다.
명시 선택 저장 이후에는 표시 상태·이전 bound ID·주기적 목록 조회가 해제한 가져오기를 다시 켜지 않습니다.
명시 선택 목록의 DB 조회가 실패하면 해당 주기의 pull/push를 중단합니다. 과거 구독 목록으로
우회하거나 빈 선택에 이전 기본 Google 캘린더를 자동 추가하지 않습니다.
가져오기 해제는 이미 받은 일정을 보존하며, 기존 쓰기 가능한 일정의 수정 전송은 유지합니다.
메인 달력의 `CalendarQuickControls`에서 기본 저장 대상과 화면 표시를 직접 설정합니다.
표시 설정창은 메인 달력 재렌더링 중에도 유지되어 여러 캘린더를 연속 변경할 수 있습니다.
추가·색상 등 전체 관리는 `CalendarSyncHub`로 연결합니다. Google 연동 초기화는 ICS 구독을 보존합니다.
섹션 구조를 변경할 때는 인덱스와 `initial_tab="calendar"` 호출부를 함께 확인합니다.
인증·목록 조회·접근 테스트·토큰 취소의 네트워크 요청은 워커에서 실행하고,
닫기/취소 시 작업 종료 전에 QThread와 다이얼로그를 파괴하지 않습니다.

## 공통 동기화 UI와 호환 경계

- 통합 허브는 기본으로 **내 캘린더**를 엽니다. 연결 및 구독·내 캘린더·로컬 캘린더·ICS 구독·문제 해결 순서로 배치하며, 진입과 문제 제목 갱신은 `section_pages`의 위젯으로 해결합니다. 기존 `services`·`calendars`·`issues` 문자열 진입을 유지하고 `local`·`ics` 진입을 지원합니다. 숫자 인덱스에 의존하지 않습니다.
- 내 캘린더는 표시와 기본 저장 대상 선택을 담당하고 로컬·ICS 관리 링크는 해당 전용 탭의 같은 항목을 선택합니다. 추가 버튼은 각각 전용 탭에만 두고, `CalendarManagerPage`의 고정 범위 필터로 로컬·ICS 목록을 분리합니다. 등록·수정·삭제·갱신은 기존 저장·동기화 경로를 재사용합니다.
- 캘린더 표시와 구독 갱신은 독립 설정입니다. 읽기 전용·비활성 캘린더의 기본 저장 버튼에는 불가 이유를 함께 표시합니다.
- 화면 조회의 표시 판정은 `domain/calendar_visibility.py`를 사용합니다. Google 원격 미러는 실제 원본·대상 ID와 기본 별칭을 해결하고, `local_owned`는 현재 저장 소속을 유지합니다. SQL에서 과거 별칭의 표시 여부를 먼저 제외하지 않습니다. 기본 저장 대상·가져오기 활성 상태와 화면 표시를 분리하고, 같은 제목의 다른 소속 일정을 제거하지 않습니다.
- ICS 주소 형식 검사는 실제 수신 성공으로 표시하지 않습니다. 주소는 기본으로 숨기고, 선택을 바꾸면 노출 상태를 초기화합니다.
- 문제 해결은 활성 실패 구독의 이름과 구체적 원인을 보여주며, 같은 구독으로 이동·재시도합니다. 작업 시작 안내는 완료 시 제거하고 수신 시각은 현지 시간으로 표시합니다.
- 좁은 화면에서는 목록과 상세를 세로로 배치하고 구독·문제 본문을 스크롤합니다. 연결·시간대의 보조 설정은 접어서 첫 화면의 행동을 줄입니다.
- 상단 동기화 버튼은 통합 허브를 엽니다. 수동 실행·설정·문제 확인은 허브에서 처리하고,
  트레이·캘린더 툴바·명령 팔레트의 공통 동기화는 `sync_calendars()`를 호출합니다.
  Google 전용 설정은 통합 허브에서 엽니다.
- 저장된 단축키 ID `sync_gcal`와 KeyDeck 명령 ID `sync_google`는 유지하고 공통 실행으로 연결합니다.
- `sync_google_auto`는 자동 타이머·일정 저장 후 개별 push 큐를 함께 제어합니다. 꺼져 있어도 `gcal_enabled`와 계정 정보를 제거하지 않으며 명시적 수동 동기화는 가능합니다.
- 공통 상태는 인증·계정·선택·작업·오류를 서비스별로 집계합니다. ICS 갱신은 Google 성공 콜백에 종속시키지 않습니다.
- 시간대 저장 키 `gcal_timezone`은 기존 설정 호환을 위해 유지하며 Google·Outlook·CalDAV·공통 ICS 워커가 읽습니다.
- ICS는 공통 `sync_ics()` 워커만 사용합니다. 개별 새로고침에는 `calendar_ids`를 전달하고,
  재시도 결과는 구독별 오류 코드에 병합하여 다른 구독의 실패 기록을 지우지 않습니다.
- ICS 작업 중 주소 수정·추가로 요청한 개별 수동 갱신은 대상 ID를 병합해 기존 워커 종료 후
  실행합니다. 실행 직전에 최신 주소·활성 상태·존재 여부를 다시 조회하며, 자동/전체 중복
  실행은 추가하지 않습니다. 중단·종료 시 대기한 개별 요청도 비웁니다.
- 구독 주소는 공통 정규화 함수로 검사합니다. webcal은 HTTPS로 변환하고 서명된 query는 보존합니다.
- ICS 주소 수정은 `calendar_repo.update_ics_subscription()`으로 처리하며 ID·표시·색상·활성 상태와
  기존 일정은 보존합니다. 주소가 바뀌면 마지막 수신 시각을 비우고, 활성 구독만 개별 갱신합니다.
  다른 구독과 같은 정규화 주소는 거부하고, 수정 전 주소를 다시 추가해도 기존 ID를 덮어쓰지 않습니다.
- ICS 구독 해제는 `calendar_repo.archive_ics_subscription()`으로 처리합니다. 기존 일정은
  ID와 관련 데이터를 유지한 채 이름 있는 숨김 로컬 캘린더에 보관하고, 원격 링크·dirty 값은
  제거합니다. 빈 구독은 보관 캘린더를 만들지 않습니다. 해제·이동은 하나의 savepoint로 처리하며
  호출자의 트랜잭션을 commit하지 않습니다. 재등록 시 보관 사본을 자동 삭제·병합하지 않습니다.
  구독 해제 확인창에서 숨김 보관과 로컬 캘린더의 다시 표시 경로를 안내합니다.
- 구독 재개는 활성 상태 저장 성공 후 해당 구독만 즉시 갱신합니다. 전체 자동 갱신 설정은
  유지합니다. 허브의 추가·수정·재개·재시도는 같은 요청 경로로 진행·완료 안내를 갱신하고,
  개별 구독의 수신 시각과 오류로 결과를 판정해 다른 구독의 실패를 성공/실패로 혼동하지 않습니다.
- ICS HTTP 401/403·404/410·429·5xx는 접근 거부·주소 없음/만료·요청 제한·서버 오류로 구분합니다.
  응답 본문·주소의 접근 키는 오류 기록에 남기지 않으며 실패 시 기존 일정과 성공 시각을 보존합니다.
- ICS 파일은 크기·일정 수·스트림 시간 제한과 읽기 중 취소 검사를 적용한 뒤 전체 스냅샷을
  트랜잭션으로 반영합니다. 다운로드·파싱·DB 실패 시 기존 일정과 성공 시각을 보존합니다.
- ICS 전체 구독은 METHOD가 없거나 PUBLISH인 피드만 반영합니다. REQUEST·CANCEL 등
  개별 일정 통지를 전체 목록으로 취급하지 않으며 이전 일정과 성공 시각을 보존합니다.
- 상단은 작은 단일 버튼과 보조 상태 문구로 표시하며 즉시 닫히는 동기화 팝업 메뉴는 두지 않습니다.
  구형 상태 라벨은 레이아웃에서 제외하고 상태 문구는 한 번만 표시합니다.
  공통 상태 갱신은 아이콘·문구·스타일을 함께 적용합니다. 평상시와 로컬 모드는 중립 색상과
  일반 굵기, 실제 오류는 경고 아이콘으로 표시하고 테마·이전 Google 상태의 스타일을 남기지 않습니다.

## 외부 서비스의 오류 범위와 복구

- Outlook·CalDAV 연결 해제는 기존 워커에서 DB 쓰기 잠금과 계정 권한 해제를 먼저 처리한 뒤
  인증 파일을 제거합니다. 인증 파일 제거 실패 시 권한·선택 변경을 rollback하며 기존 일정과
  삭제 대기열을 보존합니다. UI의 완료 signal 수신 여부로 DB 안전성을 결정하지 않습니다.
  `CalendarSyncRepository.deactivate()`는 호출자의 기존 트랜잭션을 임의로 commit하지 않습니다.
- 같은 Outlook·CalDAV 계정 재인증은 미해결 캘린더 오류와 마지막 전체 성공 시각을 보존합니다.
  다른 계정 연결·연결 해제 시 이전 계정의 처리 요약·성공 시각을 비우며, 새 계정의 성공으로
  표시하지 않습니다. 화면은 워커 시작 전에 연결 해제의 DB·자동 설정을 변경하지 않습니다.
- Outlook·CalDAV는 `CalendarSyncEngine`의 기존 캘린더 순회 안에서 오류를 구분합니다.
  한 캘린더의 잘못된 데이터·접근 상실은 해당 캘린더에 표시하고 다른 캘린더를 계속 처리합니다.
  인증·네트워크·요청 제한·서버 장애는 서비스 작업을 멈추고 기존 지연 재시도 정책을 사용합니다.
  이때 개별 삭제 대기열의 재시도 횟수를 소모하지 않습니다.
- 전체 캘린더 목록의 권한 갱신은 `CalendarSyncRepository.refresh_calendar_metadata()`로
  처리합니다. 사라진 캘린더의 사용자 선택을 보존하고 쓰기를 막으며 재등장하면 권한을 회복합니다.
- 캘린더별 오류는 `calendar_sync/status.py`의 계정별 JSON으로 저장하며 컨트롤러·허브·설정창이
  같은 기록을 읽습니다. 목록 새로고침만으로 일정 데이터 오류를 해결 완료로 바꾸지 않습니다.
- 원격 생성 결과가 확인되지 않은 삭제 보류는 기존 `calendar_sync_pending_delete`를 그대로
  사용합니다. 서비스 상태와 문제 목록에 포함하고, `다시 확인`은 기존 수동 동기화를 호출합니다.
  UI에서 보류 기록을 지우거나 일치 여부가 확인되지 않은 원격 일정을 삭제하지 않습니다.
- ICS는 기존 공통 워커의 파싱 범위에 10초 계산 예산과 취소 검사를 적용합니다. 반복 일정의 첫
  결과가 나오기 전 계산도 검사하며 시간 초과 시 기존 일정·성공 시각을 보존합니다. 파이썬 추적
  훅은 해당 스레드에서만 적용하고 종료 시 복원합니다. 네트워크 제한은 기존 HTTP 경로가 담당합니다.

## 외부 입력·인증·진단 보안

- Google 오류는 기존 `_set_last_error()`에서 종류·HTTP 상태·제한 사유로 정규화합니다.
  API 응답 본문, 일정 제목·날짜, OAuth 값, 인증 포함 URL을 저장하거나 출력하지 않습니다.
  403 quota와 권한 오류의 구분은 유지합니다. 구독 추가·해제에도 기존 계정 확인 쓰기 차단을 적용합니다.
- 기본 파일·콘솔 로그는 공통 `PrivacyFormatter`로 인식 가능한 인증 필드와 전체 URL을 가립니다.
  Google 진단 내보내기는 계정·캘린더 식별자와 일정 내용 대신 상태·오류 코드·건수만 기록합니다.
  과거 원문 로그는 복사하지 않고 제한된 꼬리 구간의 로그 수준별 건수만 기록합니다.
- 원격 캘린더 이름을 tooltip에 넣을 때 `provider_settings_widgets.plain_tooltip()`을 사용합니다.
  QLabel의 PlainText 설정만으로 tooltip의 HTML 자동 해석을 막을 수는 없습니다.
- Outlook·CalDAV HTTP 본문은 `calendar_sync/http_response.py`로 크기·취소·진행 시간 제한을
  함께 검사합니다. 압축하지 않은 응답을 요청하고 지원하지 않는 Content-Encoding은 해제 전에 거부합니다.
  CalDAV XML은 인코딩과 관계없이 DTD를 거부하며 깊이·노드 수를 제한합니다.
- ICS HTTP 상태줄·헤더·chunk 확장·trailer도 본문과 같은 마감·취소 검사를 통과해야 합니다.
  공개 주소 검증·DNS 고정·TLS·리디렉션 검사는 기존 `subscription_http.py`가 담당합니다.
- ICS·CalDAV의 원격 iCalendar 입력은 공통 `calendar_sync/ical_parser.py`만 사용합니다.
  custom TZID 캐시는 파싱 호출별로 분리하고 전역 캐시를 비우거나 바꾸지 않습니다.
  문자열 응답은 bytes로 변환해 로컬 파일명으로 해석되지 않게 합니다.
  이 helper는 icalendar 7.2.0의 parser hook 두 개를 사용하므로 의존성을 정확히 고정하고,
  버전 변경 시 시간대·반복·forward reference·동시 파싱 회귀를 다시 검증합니다.
