# Air Calendar 해외 계정 연결 확대 계획

작성일: 2026-10-12. 범위: 서비스 후보 조사와 구현 계획. 앱 코드 변경·실계정 검증·배포는 수행하지 않았다.

## 1. 권고 방향

1. 공통 서비스 등록 구조와 계정별 상태를 먼저 마련한다.
2. Yahoo Calendar, Zoho Calendar, Fastmail을 CalDAV로 추가한다.
3. 일본은 LINE WORKS, 중국은 Feishu를 각각 기업 계정 파일럿으로 추진한다.
4. Garoon, DingTalk는 후속 기업용 연결로 검증한다.
5. 공개 연동 방법이 확인되지 않은 서비스는 연결 가능 목록에 노출하지 않는다.

국가별 시장점유율을 조사한 순위가 아니다. 공식 연동 근거, 현재 코드 재사용성, 개인용/기업용 적합성으로 정한 구현 우선순위다. 실제 수요는 서비스 요청과 연결 전환율로 보정한다.

## 2. 현재 구현과 변경 지점

- `calendar_sync_hub.py`: Google·Outlook·iCloud·네이버 카드와 추가 계정 요약이 고정되어 있다.
- `calendar_sync_coordinator.py`: PROVIDERS와 표시 이름이 고정되어 있다. 새 서비스 등록 시 동기화·오류·설정 진입도 함께 확장해야 한다.
- `caldav_sync/profiles.py`: iCloud와 네이버만 등록되어 있고 HTTPS 호스트 검증도 두 서비스 전용이다.
- `caldav_settings_dialog.py`: 서비스 선택과 안내가 iCloud/네이버 두 갈래다. 프로필만 추가해도 완성되는 구조는 아니다.
- `caldav_sync_controller.py`: 서비스별 QSettings prefix 아래 하나의 현재 account_id를 보유한다. 동일 서비스의 복수 계정은 별도 설계가 필요하다.
- `application/calendar_sync_contract.py`, `infrastructure/calendar_sync/engine.py`: 정규화한 이벤트와 CRUD 어댑터를 재사용할 기반이 있다. 모든 API가 이 계약의 revision/재시도 의미를 충족하는지는 검증해야 한다.
- DB calendar.type은 gcal/local/shared/ics/outlook/caldav다. CalDAV 서비스는 기존 타입과 공급자 메타데이터를 활용한다. 새 API 타입 필요 여부는 조회·쓰기·기본값·삭제 라우팅을 조사한 뒤 결정한다.

기존 dirty worktree가 많으므로 구현은 요청 범위를 분리하고 현재 변경분을 보존해야 한다.

## 3. 지역별 후보

| 대상 시장 | 서비스 | 연결 근거·방식 | 우선순위 | 출시 조건 |
|---|---|---|---|---|
| 미국 및 글로벌 개인용 | Yahoo Calendar | 공식 CalDAV 안내 | P1 | 인증 방식·앱 암호·읽기/쓰기·반복 일정 실계정 검증 |
| 글로벌 개인/업무용 | Zoho Calendar | 공식 CalDAV 안내 | P1 | 데이터센터별 주소·구독/공유 캘린더 권한·요금제 조건 확인 |
| 글로벌 개인용 | Fastmail | 공식 양방향 CalDAV 안내 | P1 | 해당 계정의 외부 클라이언트 사용 조건과 앱 암호 확인 |
| 일본 기업용 | LINE WORKS | Calendar API·일정 생성 API | P2 | 조직 관리자 동의·앱 등록·인증·읽기/쓰기 권한·요금제 확인 |
| 중국 기업용 | Feishu / 飞书 | 공식 Calendar v4 일정 생성 문서 | P2 | 사용자 위임·공개 앱 배포·조직 승인·조회/수정/삭제 기능 검증 |
| 일본 기업용 | Cybozu Garoon | 공식 일정 조회/생성/수정/삭제 REST API | P3 | 클라우드/패키지 버전·조직 인증·외부 접근 조건 확인 |
| 중국 기업용 | DingTalk / 钉钉 | 공식 플랫폼에서 일정 생성·조회 능력 확인 | P3 | 개별 API·범위·인증·외부 앱 심사·관리자 동의 PoC |
| 일본 개인용 | TimeTree | 기존 Connect App API 종료 | 보류 | 새로운 공식 제휴/공개 연동 수단을 확인한 경우 재평가 |
| 일본 개인용 | Yahoo! JAPAN Calendar | 미국 Yahoo와 별도 검토 대상 | 조사 | 미국 Yahoo CalDAV 설정을 그대로 적용하지 않음 |
| 중국 개인/기업용 | QQ Mail·163 Mail·WeCom | 본 조사에서 일정 연동 계약 미확정 | 조사 | 메일 API와 일정 API를 구분하여 공식 문서·계정으로 확인 |

Fastmail과 Zoho는 미국 기업이라는 의미가 아니라 글로벌 사용자 확장 후보다. Feishu와 글로벌 Lark 역시 같은 인증·호스트·앱 등록을 공유한다고 가정하지 않는다. 기업용 연결만 추가해서 중국·일본 개인용 시장을 확보했다고 평가하지 않는다.

## 4. 계정 연결 UX

- 추가 계정 영역의 요약은 등록된 서비스에서 자동 생성하고 연결된 계정을 먼저 보여준다.
- 펼친 목록은 검색과 개인용/업무용 구분을 제공한다. 언어별 추천 순서는 바꿀 수 있지만 모든 서비스를 찾을 수 있게 한다.
- 카드에 양방향 동기화/읽기 전용 구독/관리자 승인 필요를 표시한다. 연결 안내에서 앱 암호·조직 URL 등 필요한 입력을 설명한다.
- 서비스 선택 → 인증 → 캘린더 조회 → 가져올 캘린더 선택 → 저장 → 첫 동기화의 순서로 진행한다.
- 인증 성공, 선택 저장, 첫 동기화 성공을 다른 상태로 표시한다.
- 계정이 여러 개면 계정 표시명과 캘린더 소속을 함께 보여준다. 국가 추천을 위해 사용자의 실제 위치를 자동 수집하지 않는다.
- ICS URL 구독은 기존 ICS 탭으로 연결하고 계정 로그인과 구분한다. 파일 가져오기도 자동 동기화로 표현하지 않는다.
- 준비 중인 서비스에는 연결 버튼을 제공하지 않는다. 기능 플래그로 검증된 서비스만 노출한다.

## 5. 구현 설계

### 서비스 등록 구조

서비스 ID·번역 키·연결 방식·설정 진입·공식 도움말·지역 태그·기능 플래그를 한 곳에서 등록한다. DB type, provider_id, account_id는 서로 분리한다. UI 목록과 상태 이름은 이 등록 구조에서 생성한다.

읽기/생성/수정/삭제/반복 일정/초대/첨부 지원은 각각 capability로 표현한다. 계정 및 개별 캘린더의 실제 권한으로 좁힌다. 미지원 원격 필드를 지우지 않으며, 안전하게 보존할 수 없는 수정은 차단한다.

### 계정과 인증

계정 ID를 기준으로 인증 자료·동기화 상태·재시도·캘린더 선택을 격리한다. 기존 서비스 단일 계정 설정은 마이그레이션해 보존한다. 토큰·암호 저장 구현을 먼저 확인하고 OS 보호 저장을 재사용한다. QSettings에는 비밀값 대신 계정 참조와 사용자 설정을 둔다.

OAuth 연결은 데스크톱 공개 클라이언트 지원과 PKCE/리디렉션을 확인한다. 서버용 client secret이 필요한 API라면 배포 앱에 넣지 않고 인증 중계 또는 관리자가 등록하는 조직용 연결 방식의 필요성을 먼저 결정한다. 백엔드 도입은 별도 설계 범위로 산정한다.

### 동기화와 데이터

CalDAV는 발견 경로·최종 호스트·리디렉션·인증 전달 정책을 공급자별로 정의한다. 현재 호스트 제한을 전면 해제하지 않는다. 범용 사용자 지정 CalDAV는 로컬/사설 서버 허용과 인증서 정책이 필요한 별도 후속 기능으로 둔다.

새 REST 어댑터는 전체 페이지 수집, 취소, 재시도, 시간대 변환과 반복 예외를 정규화한다. ETag 또는 이에 준하는 revision이 없으면 쓰기 직전 원격 재조회와 충돌 검출 전략을 검증한다. 생성 타임아웃 후 재시도는 중복 생성 방지가 검증되어야 한다.

일정 식별자는 provider/account/calendar/event/recurrence 범위로 격리한다. 제목이나 시각이 같은 다른 계정의 일정은 합치지 않는다. 가져오기·표시·기본 저장 대상은 기존처럼 분리한다. 계정 연결은 서로 다른 서비스 사이에 일정을 자동 복제하지 않는다.

DB 확장은 기존 사용자 DB를 대상으로 마이그레이션하고 gcal_subscription을 보존한다. 새로운 앱 상태는 app_initializer에서 초기화한다. 기존 CalendarSyncEngine을 재사용하되 Google 엔진 통합은 이번 확대의 선행 조건으로 삼지 않는다.

## 6. 단계별 일정과 완료 기준

기간은 개발자 1명 기준 초기 추정이며 누적 확정 일정이 아니다. 계정 제공·관리자 승인·앱 심사 대기와 인증 백엔드 신규 구축은 제외한다.

| 단계 | 예상 작업 기간 | 산출물 | 완료 기준 |
|---|---|---|---|
| 0. 연결 가능성 검증 | 3~5일 | 서비스별 인증·권한·지원 기능 표, 테스트 계정 목록 | P1 각 서비스 목록 조회, 일본/중국 기업용 인증 경로 확인 |
| 1. 확장 기반 | 1~2주 | 서비스 등록 구조, 계정별 상태, 카드/설정 일반화 | 기존 Google/Outlook/iCloud/네이버/ICS 흐름 회귀 통과 |
| 2. CalDAV 3종 | 2~3주 | Yahoo·Zoho·Fastmail 연결 및 도움말 | 서비스별 실계정 생성/수정/삭제·반복 예외·권한 확인 |
| 3. 지역 파일럿 | 서비스당 2~4주 | LINE WORKS·Feishu 읽기 전용 파일럿 후 쓰기 확대 | 조직 계정 승인, 재인증·충돌·삭제 검증 후 제한 출시 |
| 4. 기업용 확대 | 서비스당 2~4주 | Garoon·DingTalk 어댑터 | 앞선 파일럿의 수요와 서비스별 승인 가능성 확인 |

3단계의 읽기 전용 파일럿도 만료·재연결·동기화 실패 시 데이터 보존 기준을 만족해야 한다. 외부 조직 일정은 관리자가 동의한 범위만 가져온다.

## 7. 검증과 출시 기준

- 기존 사용자 DB와 단일 계정 설정의 마이그레이션, 계정별 ID 충돌 및 선택/기본값 분리.
- 종일 일정·DST·서머타임 경계·반복 일정 예외·삭제된 반복 회차·공유 캘린더 권한.
- 401/403 재인증·429 대기·5xx·오프라인·부분 페이지 실패·작업 중 취소·동기화 중 로컬 수정.
- 생성 요청의 응답 유실 후 재시도에서 중복이 생기지 않는지 확인.
- 연결 해제는 원격 삭제와 분리하고, 실패 시 기존 일정과 마지막 성공 시각을 유지.
- 미지원 초대/첨부/회의 필드 보존과 의도치 않은 초대 메일 발송 여부.
- 계정별 실서비스 검증과 Windows 배포 빌드의 인증 복귀/비밀 저장 검증을 각각 기록.
- 모든 표시 문자열은 t()로 처리하고 en/ja/zh-CN 안내를 검수. Python 수정 시 프로젝트 인코딩 검사 수행.

출시 성과는 연결 성공률·첫 동기화 성공률·7일 유지 연결·서비스별 오류율·지원 요청으로 평가한다. 분석 수집을 도입할 경우 일정 제목·본문·참석자·인증 자료를 수집하지 않는다.

## 8. 공식 근거와 남은 확인

- Yahoo CalDAV: https://help.yahoo.com/kb/SLN4707.html
- Zoho CalDAV 설정: https://www.zoho.com/calendar/help/setup-caldav-sync.html
- Fastmail 양방향 CalDAV: https://www.fastmail.help/hc/en-us/articles/1500000278342-Server-names-and-ports
- LINE WORKS Calendar API: https://developers.worksmobile.com/kr/docs/calendar
- LINE WORKS 일정 생성: https://developers.worksmobile.com/en/docs/calendar-event-user-create
- Feishu Calendar v4 일정 생성: https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event/create
- DingTalk 공식 능력 소개: https://open.dingtalk.com/orgapp
- Garoon 일정 REST API 목록: https://cybozu.dev/ja/garoon/docs/rest-api/
- TimeTree 기존 API 종료: https://timetreeapp.com/intl/en/newsroom/2023-07-23/connectapp-api
- Yahoo! JAPAN 앱 정책: https://calendar.yahoo.co.jp/info/notice/renewal/20250213_1.html

Feishu 문서는 동적 페이지라 이번 도구에서 상세 본문을 읽지 못했다. DingTalk는 능력 소개까지만 확인했으며 개별 엔드포인트·배포 앱 인증 적합성은 미확정이다. 모든 서비스의 요금제·권한·심사 조건과 실제 계정 동작은 0단계에서 검증한다.
