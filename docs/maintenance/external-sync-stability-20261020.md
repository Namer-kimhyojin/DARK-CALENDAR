# 외부 캘린더 연동 안정화 — 2026-10-20

## 변경 범위

사용자가 승인한 연동 안정화와 기존 처리와의 충돌·중복 방지 요구에 따라 Google, Outlook, CalDAV, ICS의 기존 경로를 보완했다. 별도 동기화 작업자, 새 삭제 큐, 새 자동 재시도 타이머는 추가하지 않았다.

| 대상 | 보완한 동작 | 재사용한 기존 경로 |
|---|---|---|
| Google 수정 | 마지막 서버 수정 기준을 비교하고 실제 응답의 수정 시각을 저장 | 즉시 전송 helper와 정기 sync engine |
| Google 생성 | 전송 직전 DB 상태 재확인, 요청 중 로컬 삭제 경합 시 생성 결과 보존 | 공통 snapshot 비교와 기존 삭제 큐 |
| Google 충돌 | 로컬 스냅샷 저장 실패 시 원격 적용·토큰 진행 중단, 로컬 유지 시 스냅샷 복원 | 기존 충돌 테이블과 해결 함수 |
| Outlook·CalDAV | 캘린더별 데이터 오류 격리, 네트워크·인증·서버 장애는 서비스 단위 중단 | 공통 CalendarSyncEngine과 컨트롤러의 지연 재시도 |
| 캘린더 접근 | 접근 상실 후 사용자 선택·기존 일정 보존, 권한 회복 시 정상 재개 | 공통 repository 메타데이터 갱신 |
| ICS | 반복 계산의 첫 결과 전에도 취소·10초 계산 제한 적용 | 기존 snapshot 처리와 공통 ICS 워커 |
| 복구 화면 | 생성 결과 미확인 삭제 보류와 캘린더별 오류를 이름·시각·원인과 함께 표시 | 기존 문제 목록과 수동 동기화 버튼 |

## 공통 처리와 호환성

- `google_push_snapshot()`과 비교 함수를 즉시·정기 생성 검사에서 같이 사용한다. 성공한 원격 수정 시각과 로컬 동기화 실행 시각을 구분한다.
- `CalendarSyncRepository.refresh_calendar_metadata()`를 Outlook·CalDAV 양쪽에서 사용한다. 접근 상실은 선택 해제로 처리하지 않는다.
- `calendar_sync/status.py`가 계정별 진단 저장·조회·목록 갱신 시 오류 보존을 담당한다. 계정을 바꾸면 이전 계정의 오류를 표시하지 않는다.
- `calendar_recovery_issues()`, `recovery_issue_label()`, `recovery_issue_text()`를 두 서비스 설정창에서 공유한다. ‘다시 확인’은 기존 `sync(force=True)`를 호출한다.
- 생성 결과 미확인 삭제 보류는 `calendar_sync_pending_delete`를 유지한다. UI에서 지우거나 원격 일치를 추측해 삭제하지 않는다. 같은 문자열의 삭제 큐 ID·보류 ID가 목록 선택을 바꾸지 않도록 종류를 구분한다.
- `created_at`은 기존 테이블에 `ALTER TABLE`로 추가하며 과거 시각은 NULL로 남긴다. 새 기록만 삭제 트리거에서 UTC 시각을 기록한다.
- 새 안내 문구는 한국어·영어로 작성하고 나머지 17개 로케일은 프로젝트 규칙에 따라 영어 기본 문구를 포함한다.

## 검증

개인 DB·QSettings·공유 DB·임시 폴더를 격리하고 외부 소켓 연결을 막아 회귀 테스트를 실행했다. 과거 검증 결과를 이번 통과 건수로 합산하지 않는다. 작업 도중 실패한 초기 XML은 최종 성공 근거와 구분한다.

- 설정·허브·문제 화면, 기존 UI 및 로케일: 126건 통과 (`ui-tests.xml`).
- 동일 ID 선택 경합과 허브 캘린더별 오류 상세: 2건 통과 (`selection-and-hub-tests.xml`).
- 삭제 보류의 기존 DB 마이그레이션·재시작·계정 분리·복구: 19건 통과 (`migration-tests.xml`).
- Outlook·CalDAV 공통 엔진·권한·컨트롤러·종료 경계: 223건 통과 (`provider-final-tests.xml`).
- 인코딩 정책·유틸리티: 12건 통과 (`encoding-tests.xml`), 인코딩 가드 통과.

- ICS 계산 제한·전체 스냅샷·시간대·요청 보안·워커 시작 복구: 181건 통과. 대상 파일은 `test_ics_processing_budget.py`, `test_ics_snapshot_safety.py`, `test_ics_boundary_safety.py`, `test_ics_timezones.py`, `test_ics_request_security.py`, `test_ics_worker_launch_recovery.py`이며 에이전트 실행 결과(종료 코드 0)로 확인했다.

- Google 전송·충돌·삭제·이동·증분 조회·서비스 공존: 262개 테스트와 82개 하위 사례 통과 (`google-final.xml`).
- 충돌 해결 화면·로컬 유지·서버 기준 보존·저장 실패 rollback·동시 쓰기 차단: JUnit 20개 사례(하위 사례 포함) 통과 (`keep-local-dialog-tests.xml`).

검사 묶음끼리 겹치는 테스트가 있으므로 위 수치를 단순 합산하지 않는다. `로컬 유지`는 복원과 충돌 해결 상태를 같은 쓰기 잠금·트랜잭션 안에서 저장한다. 가져오기 해제 캘린더의 과거 연결은 해당 일정만 기존 pull 처리로 재확인하며 다른 일정·선택·증분 token은 변경하지 않는다.

증거 디렉터리: `artifacts/sync-stability-20261020/`.

## 검증 범위

실제 Google·Microsoft·iCloud·네이버 계정의 원격 일정은 변경하지 않았다. 실계정 OAuth·서버별 권한·설치 앱·배포 패키지 검증은 이번 자동 회귀 테스트에 포함하지 않는다. ICS 계산 제한은 파이썬 파싱·반복 계산을 대상으로 하며 블로킹 C 호출을 강제로 중단하지 않는다. HTTP 요청은 기존 네트워크 제한을 유지한다.

제품 버전 4.6.9를 유지하고 `external-sync-stability-20261020` 변경 이력에 실행 입력 38개만 등록했다. 변경 실행 코드 19개 파일의 Ruff 검사와 최종 인코딩 가드가 통과했다. 배포·Store 제출·설치 갱신은 수행하지 않았다.
