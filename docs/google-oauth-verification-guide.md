# Google OAuth 앱 검증(Verification) 신청 가이드

## ⚠️ 현재 구조에서는 검증 불필요

Air Calendar는 **사용자가 각자 자신의 Google Cloud 프로젝트에서 OAuth 클라이언트
(credentials.json)를 만들어 등록하는 BYO 방식**입니다 (`build_store.py`가 배포 시
credentials.json을 제거하고, GCal 설정 다이얼로그에서 사용자가 직접 파일을 선택).

- 검증과 100명 사용자 제한은 **Google Cloud 프로젝트 단위**로 적용됨
- 각 사용자는 자기 프로젝트의 소유자이므로 개발자의 검증 대상이 없음
- 사용자는 자기 프로젝트의 OAuth 동의 화면에서 **자신을 테스트 사용자로 추가**하면
  경고 없이 본인 계정으로 로그인 가능

**따라서 이 가이드는 향후 개발자 클라이언트 ID를 앱에 내장(원클릭 로그인)하는
방식으로 전환할 경우에만 필요합니다.** 아래 내용은 그 시나리오 대비용입니다.

---

Air Calendar가 사용하는 `https://www.googleapis.com/auth/calendar`는 **민감(sensitive) 범위**이므로,
개발자 공용 클라이언트 ID를 배포하는 경우 검증 없이는 (1) 로그인 시 "확인되지 않은 앱" 경고 표시,
(2) 사용자 100명 제한이 적용됩니다.

## 사전 준비 체크리스트

- [x] 개인정보처리방침 작성 (`docs/privacy-policy.ko.md`, `docs/privacy-policy.en.md`)
- [x] 처리방침을 홈페이지에 게시: `https://namer-kimhyojin.github.io/DARK-CALENDAR/privacy.html` (`docs/privacy.html`, 홈페이지 `docs/index.html`에서 링크)
- [ ] 홈페이지에 앱 소개 + 기능 설명 존재 확인 (검증 심사관이 확인함)
- [ ] Google Cloud Console의 OAuth 동의 화면에 다음 등록:
  - 앱 이름: Air Calendar
  - 사용자 지원 이메일
  - 앱 홈페이지 링크
  - **개인정보처리방침 링크** (필수)
  - 승인된 도메인: `namer-kimhyojin.github.io`

## 신청 절차

1. [Google Cloud Console](https://console.cloud.google.com/) → 해당 프로젝트 → **API 및 서비스 → OAuth 동의 화면**
2. 게시 상태를 **프로덕션**으로 전환 (테스트 → 프로덕션)
3. 민감 범위(`auth/calendar`)가 포함되어 있으므로 **검증 제출** 버튼 활성화됨
4. 제출 양식 작성:
   - 범위 사용 정당화 (아래 문안 사용)
   - 데모 영상 (YouTube 비공개 링크): OAuth 로그인 → 동의 화면 → 캘린더 동기화 동작 순서로 녹화
5. 심사 기간: 통상 수 일 ~ 수 주. 심사관 이메일 회신은 영어로.

## 범위 정당화 문안 (제출 양식에 사용)

> Air Calendar is a Windows desktop calendar application. It requires the
> `https://www.googleapis.com/auth/calendar` scope because it provides two-way
> synchronization between the user's local calendar and Google Calendar:
>
> 1. Reading the user's calendar list (`calendarList.list`) so the user can
>    choose which calendars to sync.
> 2. Reading and writing events in the selected calendars for two-way sync
>    (`events.list`, `events.get`, `events.insert`, `events.update`,
>    `events.delete`, and `events.move` when an event is moved between the
>    user's calendars).
>
> The app does not create, delete or modify calendars or calendar list entries.
>
> All data received from Google APIs is stored only on the user's local device,
> is never transmitted to the developer or any third party, and is used solely
> to provide the user-facing calendar sync feature. The app complies with the
> Google API Services User Data Policy, including the Limited Use requirements.

## 참고: 현재 요청 범위와 축소 검토

- 코드가 요청하는 범위: `SCOPES = ["https://www.googleapis.com/auth/calendar"]` 하나뿐
  (`calendar_app/infrastructure/google_sync/service.py`). 저장된 토큰도 이 범위를 포함해야 유효로 판단.
- 실제 호출하는 API: `calendarList().list`(캘린더 목록 조회)와 `events()`의
  `list` / `get` / `insert` / `update` / `delete` / `move`. `calendarList.insert/delete`,
  `calendars.*`는 호출하지 않음.
- 따라서 현재 호출은 `https://www.googleapis.com/auth/calendar.events`(일정 읽기·쓰기)와
  `https://www.googleapis.com/auth/calendar.calendarlist.readonly`(캘린더 목록 조회)로 충족될 수 있음.
  검증 제출 전에 범위를 이 둘로 줄이는 방안을 먼저 검토할 것. 줄이면 `SCOPES`와 토큰 범위 확인 로직을
  함께 바꾸고, 기존 사용자 토큰의 재동의 흐름을 확인해야 함. 범위를 바꾸면 위 정당화 문안의 첫 문단도 수정.

## Limited Use 요구사항 준수 현황 (심사 대비)

| 요구사항 | 준수 내용 |
|---|---|
| 데이터를 사용자 대면 기능에만 사용 | 캘린더 동기화에만 사용, 분석/광고 없음 |
| 제3자 이전 금지 | 서버 없음, 로컬 저장만 |
| 인간 열람 금지 | 개발자 접근 경로 없음 |
| 광고 목적 사용 금지 | 광고 없음 |
| 보안 조치 | OAuth 토큰 DPAPI 암호화 저장 (token_store.py), 로그에 일정 내용 미기록 |
