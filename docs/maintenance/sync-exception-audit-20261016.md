# 동기화 오류·예외 점검 — 2026-10-16

Google, Outlook, CalDAV, ICS의 전송·수신·삭제·재시도·워커 수명을 점검하고 아래 7개 독립 수정 작업을 반영했다. 기존 작업 트리의 변경과 사용자 데이터를 유지했다.

## 확인 및 수정

| 항목 | 재현된 문제 | 반영한 방어 |
|---|---|---|
| Google 일괄 생성의 DB 재조회 | 재조회 오류를 무시하거나 삭제·수정·이동 전의 행으로 원격 생성 | 재조회 실패는 오류로 보존하고 해당 주기의 fallback에서도 제외. 삭제·스냅샷 변경은 다음 주기로 보류. 이미 생성된 연결은 최신 행으로 개별 처리 |
| Google 중복 실행 | 진행 중 재호출의 finally가 원래 실행의 진행 플래그를 해제 | 플래그를 설정한 호출만 해제 |
| 외부 서비스의 실패 응답 경합 | 조회 중 이동·수정·취소된 일정에 오래된 404 결과를 기록 | 오류 저장 직전 DB 쓰기 잠금 안에서 현재 일정·연결·선택·취소 상태 재확인 |
| 삭제 결정 경합 | 원격 조회 중 사용자가 원격 유지로 대기열을 취소해도 DELETE 전송 | 전송 직전 삭제 대기열 스냅샷을 다시 비교 |
| 미확정 원격 생성 후 로컬 삭제 | 생성 성공 응답 유실 후 로컬 삭제가 다음 조회에서 복원됨 | 보조 테이블에 캘린더·transaction ID·원본 지문을 보존하고 완전 조회의 유일한 결과만 기존 삭제 큐에 연결. import 직전 동일 쓰기 잠금에서 재확인 |
| ICS 개별 일정 통지 | CANCEL·REQUEST 등 일부 일정 통지를 전체 구독으로 받아 다른 사본 삭제 | METHOD 없음 또는 PUBLISH만 전체 스냅샷으로 반영. 실패 시 이전 일정·수신 시각 유지 |
| Outlook·CalDAV·ICS 워커 시작 | 생성·신호 연결 예외 유출, 시작 후 예외에서 실행 중 QThread 삭제 가능 | 준비부터 시작까지 예외 포착. 미실행 인스턴스는 정리하고 실행 중 인스턴스는 취소·참조 유지 후 finished에서 정리. 실패 ICS 워커의 지연 결과 차단 |

미확정 삭제 보완은 기존 테이블 DDL을 변경하지 않고 `calendar_sync_pending_delete`와 삭제 캡처 trigger를 추가·갱신한다. 원격 내용이 바뀌었으면 `delete_conflict`로 남기며 읽기 전용 권한으로는 삭제하지 않는다. 계정·캘린더·서비스가 다른 연결은 분리한다. 같은 transaction ID를 공유하는 정상 반복 회차는 허용하되, 미확정 삭제 결과가 여러 개여서 식별이 모호하면 보류한다.

## 재현 및 검사 근거

증거 디렉터리: `artifacts/sync-audit-20261016/`

| 수정 전 증거 | 확인 내용 |
|---|---|
| `google-reread-guard-before.xml`, `google-reread-fallback-before.xml` | 재조회 실패 후 전송 및 fallback 재진입, 중복 실행 guard 해제 |
| `google-stale-before.xml` | 로컬 삭제·수정·이동 뒤 오래된 Google 생성 3건 |
| `external-404-before.xml` | 404 응답 중 이동·수정·취소 경합 3건 |
| `external-lost-create-before.xml` | 미확정 생성 뒤 로컬 삭제 복원 |
| `external-queue-before.xml` | 원격 유지 선택 후 DELETE 전송 |
| `external-merge-before.xml` | 삭제 receipt 확인과 import 사이의 로컬 삭제 경합 |
| `ics-repro.xml` | 개별 일정 통지와 워커 시작 경계 |
| `launch-before-clean.xml` | 외부 워커 생성·연결·부분 시작 9건 실패, 기존 start 오류 처리 3건 통과 |

최종 검사 결과는 **49개 파일, 1,037개 검사 통과, 실패·오류·건너뜀 0개**다. JUnit testcase 977개와 추가 unittest subTest 60개를 합산했으며 재실행은 중복 계산하지 않았다. 근거는 `artifacts/sync-audit-20261016/final-results.json`이다. 47개 파일은 파일별 독립 프로세스로 검사했고, 최종 소스 핵심 경로 9개 파일의 161개 검사를 다시 실행해 기존 수치에 대체·병합했다. 신규 경계 검사는 Google 8개, 공통 엔진 18개, 외부 워커 12개, ICS 워커 7개이며 ICS 기존 파일에 개별 통지 7개를 추가했다.

임시 LOCALAPPDATA·APPDATA·PUBLIC·TEMP·TMP, INI QSettings와 개인/공유 SQLite 경로를 사용한다. 소스 폴더의 구형 DB·token 복사는 차단하고 외부 소켓 연결을 차단했다. ICS 구독 통합 검사는 로컬 모의 HTTP 서버만 사용한다. 실제 QThread 시작 후 예외 및 finished 정리도 별도 검증했다. 인코딩 guard, 수정 파일 Ruff와 `git diff --check`를 실행했다.

## 검증 경계

실제 계정 로그인, 외부 서버의 원격 저장·삭제, 사용자 DB, 설치 앱, 빌드·Store 게시 상태는 이번 검사에 포함하지 않았다. 서버가 transaction ID를 제거하면 원격 생성 결과를 안전하게 확정할 수 없어 미확정 삭제 기록을 유지하고 자동 삭제하지 않는다. 모의 테스트 통과가 모든 서비스의 실제 응답 계약을 보장하지는 않는다.

ICS METHOD 구분의 규격 근거: [RFC 5546 section 3.2](https://www.rfc-editor.org/rfc/rfc5546.html#section-3.2).

## 버전

`rules/versioning.md`에 따라 독립 일반 수정 6건과 미확정 삭제 보존 모듈 1건을 고정 이벤트 ID로 등록했다. 현재 개발 버전은 **4.1.0 Dev**이며 마지막 `manage_version.py scan`은 `changed=false`로 미등록 실행 입력이 없음을 확인했다. 실제 공개 버전 및 설치·게시 완료 여부는 별도다.
