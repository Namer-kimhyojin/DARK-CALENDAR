# 동기화 오류 점검 — 2026-10-06

## 실제 상태 확인

개인 데이터에는 쓰지 않고 로그와 기본 DB 스냅샷을 읽었다. DB는 `mode=ro&immutable=1`로 조회했고, 조회 당시 WAL 파일이 없었다.

- DB `quick_check`: `ok`.
- 저장된 일정 동기화 오류 0건, 삭제 대기 0건, 미해결 충돌 0건. 해결된 충돌 이력 2건은 오류로 세지 않았다.
- 조회한 DB에는 Google 캘린더 3개와 로컬 캘린더 1개가 있었으며 ICS 구독은 없었다.
- 10월 6일 19:46:33~34 Google 엔진의 누락 일정 보완 기록이 있었다(각 24개, 7개). 이는 처리 기록이며 전체 계정의 완전한 동기화를 입증하지는 않는다.
- 확인한 로그의 10월 5~6일 Google 동기화 관련 모듈에는 WARNING/ERROR/CRITICAL 기록이 없었다.
- 현재 인증 파일은 Desktop(`installed`) 유형이었다. 토큰 파일에는 앱의 암호화 헤더 `DCTOK1`이 있었다. JSON으로 열리지 않는다는 이유로 손상으로 판단하지 않았으며 복호화·토큰 유효성 확인은 하지 않았다.
- 샌드박스의 QSettings는 실사용 설정을 보여 주지 않으므로 빈 값에서 연결 해제나 설정 누락을 추정하지 않았다.

계정, 일정 제목, 구독 주소, 인증 키를 제외한 결과: [runtime-probe.json](../../artifacts/sync-error-audit/runtime-probe.json).

## 재현된 결함과 수정

| 범위 | 수정 전 문제 | 수정한 동작 |
|---|---|---|
| Google API 요청 제한 | 일시적인 `403 rateLimitExceeded`와 `userRateLimitExceeded`를 재시도하지 않고 권한 오류처럼 처리 | 일반 권한 거절과 구분해 제한 횟수 내에서 대기·재시도. 소진되면 각 작업 루프의 남은 전송·삭제 요청을 보류하고 미처리 작업을 보존 |
| Google 진단 화면 | 인증되지 않은 상태의 `auth_required` 등 오류를 `없음`으로 표시 | 로그인 상태와 별개로 실제 마지막 인증 오류를 표시 |
| Google 부분 실패 | 일부 전송·삭제·적용 실패에도 전체 성공 결과와 성공 시각이 기록될 수 있음 | 일부 실패를 완료 성공으로 기록하지 않고, 이미 반영된 일정은 화면에 갱신 |
| Outlook·iCloud·네이버 작업 시작 | 워커 시작 예외가 나면 작업 중 상태와 워커 참조가 남아 재시도 불가 | 워커와 공통 목록을 정리하고 기존 오류·재시도 간격 처리로 복귀. CalDAV의 시작되지 않은 워커 암호도 해제 |
| ICS 반복 일정 | 시간·분·초 단위 규칙의 필터를 고려하지 않아 정상 일정도 너무 많다고 거부 | 반복 간격과 필터의 상한을 독립적으로 계산하고 실제 회차 제한을 유지 |
| ICS 잘못된 반복 규칙 | 0 또는 음수 `COUNT`를 허용하여 기존 일정을 바꿀 수 있음 | 전체 검증 단계에서 거부하고 기존 일정·마지막 성공 시각 보존 |
| ICS 시간 초과 | 연결·다운로드의 `TimeoutError`를 일반 오류로 표시 | 연결 오류로 분류하고 기존 구독 일정을 보존 |
| iCloud·네이버 반복 일정 | CalDAV 변환에 같은 간격·필터 문제와 잘못된 반복 횟수·간격 처리 누락 | CalDAV의 반복 규칙 검증과 밀도 계산도 보완. 읽기 전용 반복 일정 정책과 회차 수 제한 유지 |

변경은 기존 아키텍처와 저장 방식을 유지했다. 사용자 DB, 토큰, 구독 주소를 초기화하거나 실제 일정에 요청을 보내지 않았다.

## 검증

합성 Google 오류·ICS/CalDAV 데이터, 격리 SQLite DB 및 테스트 설정을 사용했다. 워커 시작 실패 후 수동 재시도, 요청 제한 시 남은 작업 보존, 잘못된 반복 규칙의 기존 일정 보존을 검사했다.

| 검증 범위 | 통과 | 파일별 증거 |
|---|---:|---|
| Google 엔진·인증·진단·관련 UI | 106 | [Google 회귀](../../artifacts/sync-error-audit/google-regression.json) |
| 공통 상태·Outlook/CalDAV 시작·설정 UI | 84 | [공통 회귀](../../artifacts/sync-error-audit/common-regression.json) |
| ICS 스냅샷·시간대·CalDAV 변환 및 변경분 보존 | 110 | [ICS/CalDAV 회귀](../../artifacts/sync-error-audit/ics-caldav-regression.json) |
| Google 자동·수동 부분 실패의 화면 반영·성공 시각 보존 | 12 | [완료 콜백 회귀](../../artifacts/sync-error-audit/google-feedback-regression.json) |
| 인코딩 정책·유틸리티 | 12 | [정적·인코딩 검사](../../artifacts/sync-error-audit/root-static-checks.json) |

동기화 관련 고유 검사 **312개**, 인코딩 검사 **12개**가 통과했다. 재검증과 인코딩 가드 내부의 반복 실행은 이 수에 중복으로 세지 않았다. 변경 소스·새 테스트의 Ruff와 변경 범위 `git diff --check`도 통과했다. OAuth 로컬 콜백 소켓 검사 6개는 이번 실행에서 제외했다.

추가로 부분 다운로드 후 다른 캘린더 조회가 실패해도 이미 반영된 일정의 갱신 플래그와 성공한 캘린더의 토큰이 보존되는 것을 검증했다. 삭제 큐의 요청 제한은 전체 작업의 미완료로 집계하되 DB의 영구 실패 재시도 횟수는 소모하지 않는다. 부분 실패 사이클에서는 추가 자동 복구 요청을 보류한다.

Google의 초기 회귀 실행 중 기존 QSettings 기본 생성자가 임시 INI 설정을 사용하지 않는 검사 도구 문제를 발견했다. 명시적인 INI 생성자로 교정한 뒤, 수정 전 엔진의 격리 복사에서도 기존 중복 일정 검사 2개가 통과하는 것을 확인했다. 해당 2개 실패는 앱의 중복 처리 결함으로 기록하지 않았다. 검사 환경의 기본 설정 키는 시작·종료 모두 비어 있었고 실제 DB와 토큰은 임시 경로로 격리했다.

인코딩 가드의 첫 실행은 샌드박스 기본 임시 디렉터리 생성 실패로 끝났다. 테스트 임시 디렉터리를 작업 폴더로 지정한 뒤 인코딩 검사 12개와 가드 전체가 통과했다. 기존 읽기 제한 캐시 폴더 2개의 compileall 안내는 남았으나 가드 종료 코드는 0이었다.

## 적용 범위와 남은 확인

소스 수정과 로컬 검증 결과다. Store 설치본 업데이트 및 실제 Google·Outlook·iCloud·네이버 계정의 로그인·양방향 동기화는 이번 점검에서 수행하지 않았다. 실제 ICS 주소도 제공되지 않아 외부 구독 서버 연결은 검증하지 않았다.

이전에 제공된 Google 로그인 화면의 `403 access_denied`는 OAuth 앱의 테스트 사용자 제한이다. 이번에 보완한 Calendar API 요청 제한 403과 다른 원인이다. 해당 로그인 화면이 다시 나타나면 Google Cloud의 **Audience → Test users**에서 로그인할 계정이 등록되어 있는지 확인해야 한다. Google Cloud 설정은 변경하지 않았다.

공식 근거: [Calendar API 오류와 요청 제한 처리](https://developers.google.com/workspace/calendar/api/guides/errors), [Google OAuth 앱 대상 및 테스트 사용자](https://support.google.com/cloud/answer/15549945?hl=en), [Google 로그인 access_denied 안내](https://support.google.com/accounts/answer/16668185?hl=en).
