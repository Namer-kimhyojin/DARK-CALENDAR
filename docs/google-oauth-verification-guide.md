# Google OAuth 앱 검증(Verification) 신청 가이드

Dark Calendar가 사용하는 `https://www.googleapis.com/auth/calendar`는 **민감(sensitive) 범위**이므로,
검증 없이는 (1) 로그인 시 "확인되지 않은 앱" 경고 표시, (2) 사용자 100명 제한이 적용됩니다.
스토어 배포 앱이므로 검증 신청이 필요합니다.

## 사전 준비 체크리스트

- [x] 개인정보처리방침 작성 (`docs/privacy-policy.ko.md`, `docs/privacy-policy.en.md`)
- [ ] 처리방침을 홈페이지에 게시: `https://namer-kimhyojin.github.io/dark_calendar/privacy` (예시)
- [ ] 홈페이지에 앱 소개 + 기능 설명 존재 확인 (검증 심사관이 확인함)
- [ ] Google Cloud Console의 OAuth 동의 화면에 다음 등록:
  - 앱 이름: Dark Calendar
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

> Dark Calendar is a Windows desktop calendar application. It requires the
> `https://www.googleapis.com/auth/calendar` scope because it provides two-way
> synchronization between the user's local calendar and Google Calendar:
>
> 1. Reading and writing calendar events (create/update/delete) for two-way sync.
> 2. Managing the user's calendar list: the app lets users subscribe to and
>    unsubscribe from calendars by calendar ID (`calendarList.insert` /
>    `calendarList.delete`), which requires the full calendar scope — the
>    narrower `calendar.events` scope does not permit calendar list modification.
>
> All data received from Google APIs is stored only on the user's local device,
> is never transmitted to the developer or any third party, and is used solely
> to provide the user-facing calendar sync feature. The app complies with the
> Google API Services User Data Policy, including the Limited Use requirements.

## 참고: 왜 scope를 줄일 수 없는가

- `calendar.events`: 이벤트 CRUD만 가능 — 캘린더 목록 추가/삭제(`calendarList.insert/delete`) 불가
- 본 앱은 GCal 설정에서 "캘린더 ID로 구독 추가/제거" 기능을 제공하므로 전체 `auth/calendar` 필요
- 근거 코드: `calendar_app/infrastructure/google_sync/service.py` (calendarList().insert / .delete)

## Limited Use 요구사항 준수 현황 (심사 대비)

| 요구사항 | 준수 내용 |
|---|---|
| 데이터를 사용자 대면 기능에만 사용 | 캘린더 동기화에만 사용, 분석/광고 없음 |
| 제3자 이전 금지 | 서버 없음, 로컬 저장만 |
| 인간 열람 금지 | 개발자 접근 경로 없음 |
| 광고 목적 사용 금지 | 광고 없음 |
| 보안 조치 | OAuth 토큰 DPAPI 암호화 저장 (token_store.py), 로그에 일정 내용 미기록 |
