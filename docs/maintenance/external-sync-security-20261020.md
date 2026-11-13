# 외부 캘린더 연동 보안 보완 — 2026-10-20

Google, Outlook, CalDAV, ICS의 인증·응답 처리·표시·로그·진단 내보내기와 배포 입력을 점검했다.
실제 인증 파일, 사용자 일정 DB, 실제 계정의 원격 일정으로 공격 검증을 하지 않았다.
기존 동기화 엔진·계정 확인·오류 복구·배포 검증에 수정 사항을 연결했다.

## 재현한 문제와 조치

| 문제 | 조치와 호환성 |
|---|---|
| Google 원격 예외 본문과 URL이 로그·오류 기록에 포함될 수 있음 | 기존 오류 저장 함수에서 허용한 종류·HTTP 상태·quota 사유만 보존. 생성 로그의 일정 제목·날짜 제거. 403/429 재시도 구분 유지 |
| 과거 오류를 문제 화면에 원문으로 표시하고 진단 보고서에 계정·일정·원문 로그를 포함 | 안전한 오류 코드와 HTML escape 적용. 내보내기는 상태·오류 종류·건수로 축소. 로그 꼬리 읽기는 512KiB 제한. 원문 예외 메시지를 내보내지 않음 |
| 원격 이름 tooltip이 HTML로 해석될 수 있음 | 공통 `plain_tooltip()`으로 문자 그대로 표시. 합성 이미지 태그에 대한 Qt 리소스 요청이 발생하지 않음 확인 |
| ICS 서버가 상태줄·헤더·chunk 부가 데이터에 조금씩 응답하면 본문 전 마감 검사가 지연됨 | 기존 HTTP response의 읽기 경로에 동일한 절대 마감·취소 검사 연결. stdlib의 HTTP 프레이밍 유지 |
| Graph 본문 및 연속 페이지 수신의 메모리 사용이 충분히 제한되지 않음 | 요청당 8MiB, 목록 전체 32MiB·1만 항목·5분 제한. Graph·CalDAV는 동일한 제한 읽기 함수 사용. 응답 종료 보장 |
| CalDAV의 ASCII DTD 검사에서 UTF-16 내부 엔티티 선언이 통과 | XML parser의 doctype 단계에서 거부. 깊이 64·요소 10만 제한. 정상 UTF-16 문서는 유지. 외부 파일/네트워크 XXE 유출을 재현한 것은 아님 |
| 같은 custom TZID를 사용하는 피드가 다른 피드의 시간대를 재사용 | 기존 iCalendar parser hook 두 개로 호출별 TZP 사용. 실패한 피드·역순 입력·동시 파싱·forward reference도 격리. 기존 전역 캐시 조작 없음 |
| 라이브러리가 CalDAV 응답 문자열을 로컬 파일명으로 해석할 수 있음 | 공통 iCalendar 진입점이 bytes로 변환하여 내용으로만 파싱 |
| 구독 추가·해제 보조 API에 계정 확인 쓰기 차단 누락 | 기존 `_remote_writes_allowed()` 재사용. 계정 불일치·미확인 상태에서는 API 호출 없음 |
| 인증 파일이 강제로 추적되거나 배포물에 섞일 가능성 | 파일명 공통 판정을 소스 수집·배포 파일·ZIP 검사에 연결. 다운로드·기존 ZIP 교체 전에 차단. 경로 우회·민감 파일을 가리키는 링크도 검사. `.env.example`은 허용 |

기본 로그의 두 출력 경로는 같은 `PrivacyFormatter`로 전체 URL과 인식 가능한 인증 필드를 가린다.
따옴표·escape가 있는 Authorization/Cookie, 문자열 인수, 연결된 예외도 검증했다.
이 정규화가 임의의 모든 개인정보를 판별한다는 뜻은 아니며, 원격 응답은 발생 지점에서도 최소 기록한다.

## 기존 보호 장치 확인

- OAuth loopback 주소·state 검증, S256 PKCE, Google 인증 endpoint 제한.
- Windows DPAPI 저장 실패 시 평문 저장으로 우회하지 않으며 기존 인증 파일 보존.
- 다른 계정으로 연결된 상태에서 기존 캘린더 수정·삭제 차단.
- Graph nextLink origin 검사·리디렉션 차단, CalDAV 서비스별 호스트 제한.
- ICS 공개 IP 판정·DNS 응답 및 실제 peer 확인·TLS·프록시 차단·리디렉션 검증.
- 수신·파싱·취소 실패 시 기존 일정과 성공 시각 보존.

별도 동기화 작업자, 추가 삭제 큐, 새 자동 재시도 타이머, DB 스키마는 만들지 않았다.
HTTP 제한은 Graph·CalDAV가 공유하고, iCalendar 파서는 ICS·CalDAV가 공유한다.
기존 Google 오류 정규화와 계정 확인을 재사용했다.

## 의존성 보안

런타임 42개와 빌드 7개 고정 의존성을 [OSV 공식 API](https://google.github.io/osv.dev/api/)로 조회했다.
외부에는 공개 패키지명·버전만 보냈다.

| 라이브러리 | 변경 | 확인한 보안 공지 |
|---|---|---|
| httplib2 | 0.31.2 → 0.32.0 | [압축 응답 처리](https://github.com/httplib2/httplib2/security/advisories/GHSA-j5g9-f88f-gfj3) |
| urllib3 | 2.7.0 → 2.8.0 | [2.8.0 보안 수정: 프록시 TLS·압축 스트림·chunk header](https://github.com/urllib3/urllib3/releases/tag/2.8.0) |
| oauthlib | 3.3.1 → 4.0.0 | [4.0.0 보안 수정](https://github.com/oauthlib/oauthlib/releases/tag/v4.0.0) |
| cryptography | 49.0.0 → 50.0.0 | [PKCS7 복호화 보안 공지](https://github.com/pyca/cryptography/security/advisories/GHSA-g6cj-pr64-35w5) |

oauthlib 공지의 서버 기능과 cryptography 공지의 PKCS7 복호화 API를 앱에서 사용한다는 증거는 없다.
패키지에 알려진 문제와 앱의 실제 공격 가능성을 구분했다. 호환되는 수정 버전으로 함께 갱신했다.
개발 환경과 런타임·빌드 lock 일치, `pip check` 통과. 갱신 후 49개 재조회에서 알려진 취약점 0건.
이는 조회 시점 공개 목록의 결과이며 모든 취약점 부재를 보증하지 않는다.
icalendar는 검증한 hook과의 호환성을 위해 `7.2.0`으로 정확히 고정했다.

## 검증 결과

최종 JUnit 파일의 classname·name 중복을 제거하면 **1,258건 통과, 4건 건너뜀, 실패 0건**이다.
4건은 기존 Windows 심볼릭 링크 생성 권한에 따른 사례이며, 경로 판정 자체는 별도 합성 경로 테스트로 검증했다.
Google의 추가 하위 사례 82건은 이 합계에 별도로 더하지 않았다.

| 묶음 | 통과 | 최종 근거 |
|---|---:|---|
| Google 인증·전송·충돌·삭제·이동·계정·문제 화면 | 393 | `artifacts/sync-stability-20261020/google-security-verified.xml` |
| ICS 시간·크기·주소·파서·스냅샷 | 214 | `artifacts/sync-security-20261020/ics-security-tests.xml` |
| Outlook·CalDAV 및 공통 엔진 | 239 | `artifacts/sync-security-20261020/provider-security-final.xml` |
| 추가 provider 보안·서비스 주소 | 56 | `artifacts/sync-security-20261020/provider-security-and-hosts.xml` |
| 배포 입력·파일명·경로 | 298 | `artifacts/sync-stability-20261020/release-private-files.xml` |
| 로그·진단·tooltip·기존 설정 UX | 90 | `artifacts/sync-security-20261020/diagnostics-security.xml` |
| 시작 실패 정리 | 8 | `artifacts/sync-security-20261020/bootstrap-security.xml` |
| 인코딩 정책·유틸리티 | 12 | `artifacts/sync-security-20261020/encoding.xml` |

묶음별 표에는 중복이 있다. 합계 근거는 `artifacts/sync-security-20261020/test-summary.json`.
초기 재현 실패와 중간 실행 결과는 최종 통과에 포함하지 않았다.
시작 실패 테스트는 실제 QApplication을 유지하는 별도 offscreen 프로세스에서 통과했다.
인코딩 가드, 변경 파일 Ruff, diff 검사와 읽기 전용 버전 검사를 수행했다.

## 범위와 제한

- 단위·통합·합성 악성 응답·로컬 OAuth callback 검증이다. 실제 서비스 계정 로그인, 설치 앱, 배포 패키지 검증은 별도다.
- Graph·CalDAV 진행 제한은 읽기 사이에 검사하며 진행 중 단일 socket read는 기존 30초 제한을 따른다.
  ICS의 OS 동기 DNS 조회나 파이썬 외부의 긴 C 호출을 강제 중단하는 기능은 추가하지 않았다.
- 원격 캘린더 일정은 escape된 schedule tooltip 경로를 사용한다. 일반 routine/directive의 별도 tooltip fallback은 이번 외부 캘린더 직접 경로로 확인되지 않아 수정 범위에 넣지 않았다.
- 제품 버전은 4.6.9 유지. `external-sync-security-20261020` 변경 이력으로 실행 입력 19개를 등록했다.
  Store 제출·빌드·설치 갱신은 수행하지 않았다.
