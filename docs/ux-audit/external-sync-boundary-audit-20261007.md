# 외부 캘린더 연동·동기화 오류 경계 점검

2026-10-07. Google Calendar, ICS 구독, Outlook/Microsoft Graph, iCloud·네이버 CalDAV와 공통 동기화 상태·재시도·Worker를 점검했다. 현재 개발 소스의 기존 변경을 유지하면서 발견한 오류를 보완했다.

## 보완한 동작

| 범위 | 재현 조건과 위험 | 변경 후 동작 |
|---|---|---|
| Google 이벤트 식별 | 다른 캘린더에 같은 이벤트 ID가 존재하거나 일정 이동 대상이 먼저 저장됨 | 원본 캘린더와 이벤트 ID를 함께 식별하고 이동 중 원본·미전송 변경을 보존 |
| Google 기본 별칭 | `primary`가 실제 계정 ID로 바뀔 때 캘린더 삭제 경로가 기존 링크를 해제함 | savepoint에서 별칭을 이전하고 소속·표시·기본값·삭제 대기열을 보존, 충돌 시 rollback |
| Google 계정 변경 | 과거 계정 ID와 다른 primary를 가져오면서 기존 `primary` 소속을 새 계정으로 해석 | 설정·메타데이터·원격 쓰기 전에 기존 소속 증거 확인, 불일치 시 일정·미전송 변경·삭제 대기열 유지 |
| Google 계정 확인 실패 | 인증 후 목록 조회 실패·빈 목록·primary 식별 실패에도 새 token 저장/연결 교체 진행 | 계정의 실제 primary 확인 전 기존 token·연결 유지, 실패·취소의 후보 token 폐기, 기존 소속 증거가 있는 동기화도 원격 쓰기 전에 보류 |
| Google 삭제·취소 반영 | 409 또는 일부 batch callback 누락, 취소 반영/삭제 완료 저장 실패 | 성공으로 계산하거나 token을 진행하지 않고 실패·재시도 정보를 보존 |
| Google 접근 실패 | events.list 404를 정상 조회 또는 캘린더 숨김·가져오기 해제로 처리 | 실패로 보고하고 기존 일정과 표시·가져오기 선택을 유지 |
| Google 미연결 원격 일정 | 로컬 연결 부재를 자동 삭제 근거로 사용하거나 제목·날짜만으로 다른 캘린더에 연결 | 미연결 일정은 관찰만 하고 자동 원격 삭제·추정 연결을 하지 않음 |
| Google 불량 수신 응답 | 빈 객체/잘못된 items·ID·token·시간을 정상 전체 목록으로 오인해 기존 일정 보관 또는 token 진행 | 모든 페이지와 캘린더 전체 이벤트를 반영 전에 검증, 불완전 응답에서 보관·token 진행·로컬 전송 차단 |
| Google 불량 캘린더 목록 | 문자열 primary를 참으로 바꾸거나 잘못된 목록·ID·문구·page token, 중복 ID·복수 primary를 정상 계정 정보로 처리 | 원격 primary의 bool 계약과 전체 목록을 검증, 정확히 하나의 실제 primary만 계정 확인에 사용하고 잘못된 증거·불완전 목록 적용 차단 |
| ICS 전체 수신 | HTTP 206/Content-Range, Content-Length 부족, stream 중단 | 부분 snapshot 적용을 거부하고 기존 일정을 유지 |
| ICS 반복·시간대 | 알 수 없는 TZID, 잘못된 DTEND/DURATION, COUNT+UNTIL, 잘못된 반복 예외 | 원본 검증 후 전체 snapshot을 보존하고 안전한 진단 코드 반환 |
| ICS 제외일·소유권 | 단일 일정의 EXDATE 누락, local_owned identity 충돌 | 제외일을 반영하고 보호된 일정 충돌 시 저장 transaction 전체 rollback |
| Outlook 응답 | 잘못된 목록/ID/권한 플래그·시간·본문·ETag·transactionId 또는 다른 ID의 GET/PATCH 응답 | DB·원격 수정 전에 응답 계약을 검증하고 기존 링크를 유지 |
| CalDAV 원격 쓰기 | PUT 이후 또는 412 생성 재확인 시 UID가 다른 응답 | 다른 일정을 연결하거나 덮어쓰지 않고 생성·식별 충돌로 보류 |
| 공통 쓰기 권한 | 네트워크 조회 도중 선택·계정·수정 권한 변경 | create/update/delete 직전에 현재 선택과 권한을 다시 확인 |
| 공통 결과 표시 | 일부 일정이 보류됐는데 전체 성공 시각을 갱신함 | 부분 완료를 명시하고 이전 전체 성공 시각을 보존, 문제 해결 목록과 상태 연결 |
| 공통 요청 제한 | Retry-After를 잃거나 수동 동기화가 서버 대기 시간을 우회함 | Worker가 검증된 지연을 전달하고 수동·자동 동기화/목록 갱신이 대기 시간을 준수 |
| Worker 취소·정리 | Outlook 목록 조회 중 취소 후에도 DB/결과 진행, 세션·인증 headers 미정리 | 조회 직후 취소 확인, DB·HTTP session·메모리 인증값 정리, cleanup 오류의 스레드 외 전파 차단 |
| 늦은 ICS 결과 | 수신 완료 후 queued 결과 처리 전에 구독 URL 변경·해제·삭제 | 현재 구독 ID와 URL을 다시 확인해 새 구독의 오류·성공 시각을 잘못 바꾸지 않음 |
| 목록 갱신의 메인 표시 | 목록 갱신에서 캘린더·권한이 바뀌었지만 성공/실패 후 메인 렌더링이 남음 | 갱신한 메타데이터를 성공·후속 실패 모두 메인 화면에 반영 |

ICS의 구독 파일 시간대 오류는 앱의 시간대 선택 오류와 구분한다. 공통 UI에서 보류 항목·서비스 응답 형식·구독 시간대의 복구 안내를 제공하고 19개 locale bundle에 키를 보완했다. 한국어·영어 문구를 제공하며 다른 17개 locale의 신규 문구는 영어 fallback이다.

Google 설정 화면의 직접 목록 갱신·조회 완료·인증 완료에 같은 계정 검증을 적용한다. 확인된 불일치는 `account_mismatch`, 확인할 수 없는 계정은 `account_unverified`로 안내한다. 원래 계정의 실제 ID를 다시 확인하면 해당 차단과 안내를 해제하며, 정상 목록 조회·인증 완료·버튼 복귀도 함께 검증했다.

Retry-After는 양수 정수 초 또는 HTTP-date를 받아 UTC 기준으로 계산한다. 잘못되거나 만료된 값은 기존 지수 backoff를 사용한다. 지원 상한은 Qt의 signed 32-bit 밀리초 timer 범위에 맞춘 2,147,483초이며, 현재 실행 중의 대기 상태를 단조 시계로 관리한다. 계정 연결·해제는 이 대기로 막지 않는다.

재시도 timer는 PreciseTimer와 올림 계산을 사용한다. 만료 전에 깨어났으면 남은 시간만 재예약하고, 만료 후 작업을 시작할 때 정상 간격으로 복귀한다. 긴 지연 전체를 다시 기다리거나 1ms 간격으로 재시도하는 동작을 방지한다. [Qt timer accuracy](https://doc.qt.io/qt-6/qtimer.html#accuracy-and-timer-resolution).

## 근거와 판단

Google의 이벤트 ID는 캘린더 안에서 식별한다. 다른 캘린더에서 같은 ID를 발견했다는 사실만으로 같은 일정이라고 판단하지 않는다. [Google Events reference](https://developers.google.com/workspace/calendar/api/v3/reference/events).

캘린더 목록의 `primary`는 생략 시 false인 boolean이다. 문자열을 `bool()`로 강제 변환해서 계정 확인 근거로 쓰지 않는다. ID·이름·시간대·역할의 문자열 타입과 목록 페이지 구조도 검증한다. 역할 문자열의 종류는 과거 목록으로 제한하지 않으며 현재 미지원 역할은 쓰기 권한으로 승격하지 않는다. [Google CalendarList resource](https://developers.google.com/workspace/calendar/api/v3/reference/calendarList), [CalendarList list response](https://developers.google.com/workspace/calendar/api/v3/reference/calendarList/list).

Google 404는 존재하지 않음과 접근 불가 모두 가능하며 409는 작업 충돌일 수 있다. 따라서 조회 실패만으로 사용자 선택을 숨기거나 삭제 요청을 완료 처리하지 않는 방어를 적용했다. [Google API error guidance](https://developers.google.com/workspace/calendar/api/guides/errors). 증분 token은 완전한 결과를 적용했을 때만 진행하며, 만료는 기존 전체 재조회 경로를 유지한다. [Google incremental sync](https://developers.google.com/workspace/calendar/api/guides/sync).

Microsoft는 429 응답에서 Retry-After 대기를 준수하도록 안내한다. 응답 header를 보존하고 controller에서 재시도 시점을 제한하는 변경은 이 계약을 따른다. [Microsoft Graph throttling](https://learn.microsoft.com/graph/throttling). 목록은 모든 페이지가 정상적으로 완료된 경우만 처리한다. [Graph paging](https://learn.microsoft.com/en-us/graph/paging).

ICS 시간대·종료일·반복 집합·예외 유형은 [RFC 5545](https://www.rfc-editor.org/rfc/rfc5545.html), HTTP 부분 응답은 [RFC 9110 §15.3.7](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.3.7)을 대조했다. 해석할 수 없는 입력을 기존 전체 snapshot 대신 적용하지 않는 것은 이 앱의 데이터 보존을 위한 구현 판단이다.

## 검증·격리

재현 테스트는 정상 응답 외에 부분 수신, 변경된 권한·ID, 충돌, DB 저장 실패, 취소, 오래된 Worker 결과, 요청 제한, 잘못된 반복 일정·시간대를 포함한다. 최초 실패 증거와 최종 XML을 `artifacts/external-sync-audit-20261007/`에 보관한다. 실제 testcase 수를 집계하며 동일 테스트의 선별 재실행은 중복 집계하지 않는다.

- Google: `tests/test_google_sync_boundary_safety.py`와 기존 동기화·설정·이동·표시 회귀.
- ICS: `tests/test_ics_boundary_safety.py` 포함 77개; 마지막 시간대 진단 구분 5개는 이 77개 안의 선별 재실행이다.
- Outlook·CalDAV: `tests/test_external_provider_boundary_safety.py`와 기존 provider·공통 engine 회귀.
- 상태·재시도·구독 경합: `tests/test_external_sync_controller_safety.py`와 기존 controller·coordinator·설정·locale 회귀.
- Worker: `tests/test_external_worker_retry_safety.py` 신규 48개; 실제 QThread 목록/engine 중 취소와 session.close 오류 포함.
- Google 인증 Worker: `tests/test_gcal_auth_worker_safety.py` 신규 12개; 조회 실패·401·인증/목록 조회 중 취소, 실패한 후보 token 폐기와 정상 완료 포함.

별도 읽기 감사에서 Google의 합성 수신 응답을 service 26회·engine 31회 진단하고, 수정 후 같은 57회와 정상 호환성 10회를 재확인했다. 잘못된 응답의 engine 26회에서 기존 일정·token 보존, 보관 0회·push 0회를 확인했다. 이 진단 실행 횟수는 pytest testcase 수에 더하지 않는다. 빈 items omission+유효한 최종 token, optional text 누락/None, ID-only 취소 이벤트 및 정상 pagination은 허용한다. `ics/GOOGLE_PULL_READONLY_AUDIT.md`, `ics/google-pull-final-comparison.json`에 before/final 증거를 기록했다.

앱 모듈을 import하기 전에 QSettings를 artifact INI로 연결하고 TEMP/TMP/LOCALAPPDATA를 작업 폴더로 격리했다. SQLite 임시 DB와 모의 HTTP·인증만 사용했으며, 실행 전후 사용자 QSettings의 모든 키·값이 유지됐음을 확인했다. 실제 개인 DB·캘린더·인증 정보를 변경하지 않았다.

최종 결과는 **중복 제외 동기화·관련 회귀 827개와 인코딩 12개 통과**, 실패·오류·skip 0개다. JUnit의 `(classname, name)`을 기준으로 같은 테스트의 재실행을 제외했다. 원인 재현용 실패 XML은 합계에 넣지 않았으며, 최종 성공 XML과 선별 재검증을 순서대로 병합했다. 실행 목록·파일별 수·변경된 제품 파일 20개의 SHA-256은 `artifacts/external-sync-audit-20261007/summary.json`에 기록했다.

Google 전체 회귀 `google/final-broad.xml`은 320개 통과한 단계이며, 이후 목록 타입·중복·계정 확인·인증 마무리 보완은 `google/metadata-ambiguity-final.xml` 208개 통과로 재검증했다. 정상 인증 및 후보 token 저장 실패·취소·닫기 경계는 `root/auth-lifecycle-closed.xml`에서도 14개 선별 검사로 확인했다. 이 단계들의 중복을 다시 세지 않았다.

변경한 제품·회귀 파일의 Ruff와 공백 검사를 통과했다. 프로젝트 인코딩 guard의 compileall 및 인코딩 검사 12개를 마지막 소스에서 다시 통과했다. 기존 접근 불가 pytest 임시 폴더 2개에 대한 열거 경고만 있었으며 변경 소스의 컴파일·정책 검사는 정상이다.

## 실제 사용 환경의 남은 검증

소스·격리 테스트 결과와 실제 계정·배포 결과를 구분한다. 이번 작업에서 실제 Google/Microsoft/iCloud/네이버 계정 로그인, 외부 ICS feed, 릴리스 빌드, Store 설치판 적용은 수행하지 않았다. 실제 서비스의 계정 등록·권한·인증 정책과 서버별 CalDAV 호환성은 별도 확인이 필요하다. 현재 ICS 조회 범위·네이버 읽기 전용 정책·삭제 대기열 재시도 한도 등 기존 계약을 유지했다.

이번 보완은 재현한 오류와 경계의 방어를 확인한 결과이며 모든 외부 서버 입력에서 오류가 발생하지 않는다는 보장을 의미하지 않는다. 실패 시 기존 일정·미전송 변경·재시도 정보가 보존되는지가 검증 기준이다.

과거 `primary` 일정에 이전 실제 계정 ID가 저장되지 않은 경우에는 소속 계정을 역으로 확정할 증거가 없다. 이번 계정 변경 방어는 이전 실제 ID와 남은 별칭 소속 증거가 있는 경계 및 인증 완료 전 계정 확인을 검증했다. 오래된 계정 소속을 복원하거나 계정을 완전히 교체하는 전체 cache 정책까지 검증한 결과로 해석하지 않는다.
