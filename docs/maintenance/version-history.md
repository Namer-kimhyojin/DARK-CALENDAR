# 버전 변경 이력

제품 버전은 배포 단위로 결정한다. 변경 기록·Git/CI 빌드·공개·Store·설치 상태는 별도이며 변경 기록만으로 버전을 올리지 않는다.

기준 버전: `3.8.1` · 현재 제품 버전: **`4.9.2`**

| 버전 | 일시(KST) | 유형 | 변경 내용 | 이벤트 ID |
|---|---|---|---|---|
| 4.9.2 | 2026-11-02T09:48:07.711805+09:00 | release | All post-4.8.0 widget, workspace, localization and calendar-sync improvements plus reviewed SIP 13.12.0 shutdown runtime and Qt message fallback correction | `release-4.9.2-integrated-20261102` |
| 4.9.1 | 2026-11-02T09:45:28.645852+09:00 | module | Keep source-run and CI dependency installation on the same reviewed PyQt6-sip 13.12.0 as the release runtime lock | `qt-sip-development-pin-20261102` |
| 4.9.1 | 2026-11-02T09:43:46.857816+09:00 | module | Pin PyQt6-sip 13.12.0 instead of 13.11.1 after a native second-chance shutdown dump in SIP; retain PyQt6 and Qt 6.10.2 and revalidate complete source and final native EXE | `qt-sip-runtime-shutdown-fix-20261102` |
| 4.9.1 | 2026-11-02T09:39:26.063325+09:00 | change | Preserve unmapped Qt source strings by returning null QString from the standard-button translator; reproduced blank Qt text and verified fallback in 44 isolated tests | `qt-standard-button-translation-fallback-20261102` |
| 4.9.1 | 2026-11-02T09:30:43.122086+09:00 | change | QA-only: retain second-chance exception address and read-only crash dump on disposable VM; pin unchanged 4.9.1 candidate for diagnostic revalidation | `release-4.9.1-native-diagnostics-20261102` |
| 4.9.1 | 2026-11-02T09:14:32.969950+09:00 | change | Make preset timezone expectations locale-independent and modal automation test independent of the real weekday and current time | `release-4.9-test-determinism-20261102` |
| 4.9.1 | 2026-11-02T09:12:30.268229+09:00 | release | All post-4.8.0 widget, workspace, multilingual and sync improvements; final source formatting included; 4.9.0 preflight reservation not built or published | `release-4.9.1-integrated-20261102` |
| 4.9.0 | 2026-11-02T09:12:27.327987+09:00 | change | Normalize final release source import and formatting; AST unchanged across all changed Python files | `release-4.9-source-format-20261102` |
| 4.9.0 | 2026-11-02T09:10:15.907217+09:00 | release | Widget graphic collections and designs, workspace and management features, multilingual improvements, calendar subscription and sync stability | `release-4.9.0-integrated-20261102` |
| 4.8.0 | 2026-11-02T07:12:17.027314+09:00 | change | ICS 구독 해제 사본 보관, 재개 즉시 갱신, 복구 결과와 다국어 안내 개선 | `sync-subscription-ux-20261102` |
| 4.8.0 | 2026-11-02T03:30:36.221925+09:00 | change | Fix the website release-status notice remaining visible despite its hidden attribute and refresh CSS/JS cache keys after verified Store publication | `maintenance-20261102-store-published-notice-hidden` |
| 4.8.0 | 2026-11-02T03:25:47.991384+09:00 | change | Verify official Store 4.8.0 installation and fresh runtime/profile data, retain UI/restart acceptance limits, and repair read-only live-log sharing in the local deployment observer | `maintenance-20261102-official-store-installation` |
| 4.8.0 | 2026-11-02T03:15:15.668749+09:00 | change | Confirm Store 4.8.0 publication, update public availability metadata, record day01 startup checks, and track post-release development separately for the next integration cycle | `maintenance-20261102-store-publication-cycle-handoff` |
| 4.8.0 | 2026-11-01T21:35:24.657149+09:00 | change | 19개 로케일 번역·위젯 관리 문구·RTL·날짜·Qt 버튼·사용자 번역 대체 처리 보완, 400건 회귀 및 다국어 화면 검증 | `i18n-support-audit-20261101` |
| 4.8.0 | 2026-11-01T18:56:45.438842+09:00 | change | 위젯 확장 7종: 통합 작업 공간, 실제 미리보기, 모니터 배치, 상황별 전환, 통합 절전, 상태 안내, 네이티브 스택 및 관리창 재사용 | `widget-workspace-studio-20261101` |
| 4.8.0 | 2026-11-01T15:36:56.072548+09:00 | change | 위젯 통합 관리 허브: 추가 갤러리, 검색·상태 필터, 표시·찾기·꾸미기, 전용 모드 실행·복귀·편집, 행 재사용과 갱신 병합 | `widget-management-hub-20261101` |
| 4.8.0 | 2026-11-01T15:15:05.952146+09:00 | change | ICS 수신 중 개별 갱신 보존, Outlook·CalDAV 연결 해제의 트랜잭션·종료 안전성 및 계정별 오류·성공 상태 보완; 관련 회귀 1,350건 검증 | `calendar-sync-subscription-stability-20261101` |
| 4.8.0 | 2026-11-01T15:09:53.561209+09:00 | change | 캘린더 5종 공식 문서 벤치마킹 기반 위젯 전용 스킨 10종·화면 6종·3영역 보드·캐시 검색·스킨 갤러리·빠른 보기 전환 | `widget-mode-workspace-redesign-20261101` |
| 4.8.0 | 2026-11-01T14:33:58.405325+09:00 | change | 위젯 8종별 디자인 10종씩 총 80종 추가, 13종 스크롤 갤러리와 종류별 일괄 매핑·큰 날씨 카드 예보 통합 | `widget-designs-80-20261101` |
| 4.8.0 | 2026-11-01T12:37:16.952881+09:00 | change | 고배율 위젯 검증 보드 축소 캡처의 부드러운 샘플링 보완 | `widget-graphic-qa-dpi-20261101` |
| 4.8.0 | 2026-11-01T12:36:38.487876+09:00 | change | 위젯 8종 그래픽 컬렉션·전용 숫자/계기판·짧은 상태 전환·복원·대비 및 Qt 회귀 수명 개선 | `widget-graphic-collections-20261101` |
| 4.8.0 | 2026-11-01T10:56:40.859176+09:00 | change | Record Store Submission 31 certification acceptance and update the public four-language review notice without changing the package or product version | `release-4.8.0-store-submission31-20261101` |
| 4.8.0 | 2026-11-01T10:01:44.084498+09:00 | change | 홈페이지에서 GitHub 4.8.0 공개와 Store 제출 준비 상태를 네 언어로 구분하고 최신 배포 링크 제공 | `release-4.8.0-store-availability-notice-20261101` |
| 4.8.0 | 2026-11-01T09:55:59.517823+09:00 | change | 4.8.0 GitHub·홈페이지 완료와 Store 로그인/설치 후속을 유지보수 계획에 구분해 인계 | `release-4.8.0-maintenance-handoff-20261101` |
| 4.8.0 | 2026-11-01T09:54:20.286716+09:00 | change | 공개 확인표 날짜 형식을 배포 계약과 일치시키고 실제 홈페이지 공개 검증 상태 반영 | `release-4.8.0-public-checklist-date-20261101` |
| 4.8.0 | 2026-11-01T09:49:48.281033+09:00 | change | 검증된 GitHub 4.8.0 공개 정보, 새 기능 홈페이지 화면 4개와 다국어 설명·반응형 탭 반영; Store 상태는 별도 유지 | `release-4.8.0-public-metadata-20261101` |
| 4.8.0 | 2026-11-01T09:29:09.049279+09:00 | change | Git 체크아웃에서 SVG와 자산 설명 파일 4개의 개발 원본 바이트 보존; 예약된 실행 입력은 동일 | `release-4.8.0-asset-byte-preservation-20261101` |
| 4.8.0 | 2026-11-01T09:24:40.339589+09:00 | release | 현재 전체 실행 입력: 비트메이커 녹음·루프, 날씨 프리미엄 UI, Google 갱신 복구, 완료 복사/NLP/아이콘 대비 및 안전한 개발 실행 통합 | `release-4.8.0-integrated-20261101` |
| 4.7.1 | 2026-11-01T09:24:38.830003+09:00 | change | 권한 제한 심볼릭 링크 검사를 Ubuntu Quality Gate에 포함하고 4.8.0 변경 안내 준비 | `release-4.8.0-symlink-ci-coverage-20261101` |
| 4.7.1 | 2026-11-01T09:24:37.920970+09:00 | change | 커밋 서식 검사에 맞춘 9개 파일 정리; AST와 제품 동작 유지 | `release-4.8.0-source-format-20261101` |
| 4.7.1 | 2026-11-01T03:10:31.997203+09:00 | change | 14일차 홈페이지·게시판·이미지·릴리스 경로 점검과 11월 2일 전체 입력 배포 인계 문서 갱신; 제품 코드와 버전 유지 | `maintenance-20261101-homepage-release-review` |
| 4.7.1 | 2026-10-31T03:12:44.139669+09:00 | change | 모양 설정 동작 아이콘의 테마 대비 보완, 13일차 검증 및 최근 개발 변경의 통합 배포 범위 연결 | `maintenance-20261031-appearance-icon-theme-contrast` |
| 4.7.1 | 2026-10-31T03:12:43.130240+09:00 | change | 명령 검색의 검색·결과 아이콘을 앱 글자색에 맞추고 테마 전환 후 재열기에서 색상을 갱신 | `maintenance-20261031-palette-icon-theme-contrast` |
| 4.7.1 | 2026-10-31T00:56:29.651628+09:00 | change | 날씨 프리미엄 카드 3종·시간별 예보·애니메이션·공유 캐시와 부분 렌더링 구현 | `weather-premium-ui-20261031` |
| 4.7.1 | 2026-10-30T21:45:48.870934+09:00 | change | Google 토큰 갱신의 일시 오류와 실제 인증 거부를 구분하고 설정 조회의 오류 원인 및 재시도 경로 보존 | `fix-google-refresh-retry-classification-20261030` |
| 4.7.1 | 2026-10-30T03:09:36.065227+09:00 | change | 12일차 Google 동기화·인증·오프라인 격리 검증과 UI 확인, 주기 및 배포 잔여 작업 기록(제품 코드·번호 유지) | `maintenance-20261030-google-review-checkpoint` |
| 4.7.1 | 2026-10-29T09:03:25.077876+09:00 | change | 11월 2일 전체 배포 입력과 미배포 후보 확인, 남은 일정·검증 조건 및 개발 실행 문서 정리(제품 코드·번호 유지) | `release-readiness-20261102-audit-20261029` |
| 4.7.1 | 2026-10-29T03:19:17.691041+09:00 | change | Use the verified private SQLite runtime for current-source run.bat launches; fail closed without replacing the developer Python; validate SQLite/shared/ICS preservation and pinned Qt compatibility | `maintenance-20261029-safe-development-sqlite-launcher` |
| 4.7.1 | 2026-10-28T03:08:11.359161+09:00 | change | Pass the displayed 09:00 default time through natural-language schedule creation; record day-ten algorithm and performance review | `maintenance-20261028-nlp-preview-default-time` |
| 4.7.1 | 2026-10-28T03:07:40.083048+09:00 | change | Preserve malformed numeric date expressions instead of partially changing titles and dates; retain supported month-day formats | `maintenance-20261028-nlp-date-token-boundaries` |
| 4.7.1 | 2026-10-27T03:05:52.153892+09:00 | change | Reset completion flag and timestamp when copying completed schedules or routines; preserve originals and moved completion metadata; record day-nine review | `maintenance-20261027-completed-task-copy` |
| 4.7.1 | 2026-10-26T09:18:07.986135+09:00 | change | 누락된 5~7일차와 당일 8일차 검증, 미배포 비트메이커 후보 및 Store 후속 기록 정렬(제품 코드·번호 유지) | `maintenance-20261026-catchup-area-checkpoints` |
| 4.7.1 | 2026-10-22T11:57:58.879294+09:00 | module | 비트메이커 전용 연주창, 패드 녹음과 루프 재생, 저장·공유·종료 보호 추가 | `keydeck-beatmaker-recording-loop-20261022` |
| 4.7.1 | 2026-10-22T08:49:53.811700+09:00 | change | 정기 자동화의 버전 규칙을 현행화하고 4.7.1 공개·설치 후속 기록을 일치시킴(제품 코드와 버전 유지) | `maintenance-20261022-automation-version-policy-and-checkpoints` |
| 4.7.1 | 2026-10-21T12:43:03.608549+09:00 | store | Publish verified 4.7.1 assets and synchronize public release metadata | `github-publication-4.7.1-20261021` |
| 4.7.1 | 2026-10-21T12:26:35.906763+09:00 | change | Activate and verify the exact disposable Windows paging notice before clicking OK; revalidate the unchanged 4.7.1 payload with pinned QA provenance | `native-qa-focus-4.7.1-20261021` |
| 4.7.1 | 2026-10-21T12:06:24.011310+09:00 | release | Unified date and time entry, external calendar reliability and security, and bounded sparse ICS recurrence processing | `release-4.7.1-20261021` |
| 4.7.0 | 2026-10-21T12:06:21.818732+09:00 | change | Preserve sparse ICS recurrence results within the existing processing budget and keep exact input bytes in hosted Windows release jobs | `sparse-ics-and-release-checkout-20261021` |
| 4.7.0 | 2026-10-21T11:51:42.154128+09:00 | store | Keep source and homepage on the verified last public release while 4.7.0 candidate is being validated; packaged build metadata remains release-specific | `release-4.7.0-pending-publication-20261021` |
| 4.7.0 | 2026-10-21T11:47:48.318505+09:00 | change | Normalize release regression test formatting and preserve cancellation trace coverage for commit quality checks | `release-4.7.0-test-format-20261021` |
| 4.7.0 | 2026-10-21T11:41:32.507067+09:00 | release | Unified date/time input across schedules, directives and routines with keyboard improvements and accumulated calendar sync reliability and security fixes | `release-4.7.0-20261021` |
| 4.6.9 | 2026-10-21T11:35:00.161574+09:00 | change | Fix date/time keyboard entry, popup traversal, live schedule summaries and consistent task editor controls after native Windows QA | `schedule-datetime-native-20261021` |
| 4.6.9 | 2026-10-21T11:05:36.254885+09:00 | change | 일정 날짜 통합·시간 목록·일정 길이 입력 및 지시협조·일반업무 디자인 통일, 생성수정이동복사 검증 | `schedule-datetime-input-20261021` |
| 4.6.9 | 2026-10-21T10:16:25.713305+09:00 | change | 외부 캘린더 후속 계획: 설치 인수·보안 자동화, 통합 상태/진단, 갱신 효율과 다중 계정 단계 수립 | `external-sync-roadmap-20261021` |
| 4.6.9 | 2026-10-21T09:04:23.615635+09:00 | change | 주간 시간표에서 키보드로 선택한 일정 카드가 화면 위아래에 잘리는 스크롤 보정 | `maintenance-20261021-weekly-keyboard-scroll-visibility` |
| 4.6.9 | 2026-10-21T09:02:49.593361+09:00 | change | 주간 보기에서 선택 해제 후 위·왼쪽 방향키가 마지막 일정을 건너뛰는 오류 수정 | `maintenance-20261021-weekly-reverse-key-selection` |
| 4.6.9 | 2026-10-20T18:29:06.940591+09:00 | change | 외부 캘린더 인증·로그·진단 보호, 악성 응답과 시간대 격리, 의존성 취약점 및 배포 민감 파일 차단 | `external-sync-security-20261020` |
| 4.6.9 | 2026-10-20T18:04:43.350267+09:00 | change | 외부 캘린더 충돌·생성 경합·오류 격리·ICS 계산 중단 및 공통 복구 진단 안정화 | `external-sync-stability-20261020` |
| 4.6.9 | 2026-10-20T17:21:30.331938+09:00 | change | Default new text overlay widgets to Pure Type with text shadows while preserving saved appearance | `text-widget-pure-shadow-defaults-20261020` |
| 4.6.9 | 2026-10-20T17:01:42.114894+09:00 | change | Bound checklist JSON imports before parsing and database access; validate schema and preserve atomic imports | `20261020-security-checklist-import-limits` |
| 4.6.9 | 2026-10-20T16:49:01.818167+09:00 | change | Restrict ICS requests and redirects to pinned public destinations, validate peers, and reject HTTPS downgrades | `security-ics-redirect-public-destinations-20261020` |
| 4.6.9 | 2026-10-20T16:37:48.315078+09:00 | change | Render calendar detail fields and imported checklist text as plain text before assigning content; add resource-resolution regression checks. | `20261020-security-untrusted-label-text` |
| 4.6.9 | 2026-10-20T16:31:29.873707+09:00 | change | Google OAuth token protection fails closed; preserve encrypted credentials and reject failed plaintext migration | `security-google-oauth-dpapi-fail-closed-20261020` |
| 4.6.9 | 2026-10-20T15:14:33.102984+09:00 | change | Reject unsafe release compliance filenames and ZIP members; constrain cache downloads and partial files. | `security-compliance-filename-path-traversal-20261020` |
| 4.6.9 | 2026-10-20T15:06:55.361398+09:00 | module | 배포 단위 제품 버전과 변경 기록을 분리하고 읽기 전용 검사·명시적 배포 준비·원본 기준 동기화 적용 | `release-unit-version-policy-20261020` |
| 4.6.9 | 2026-10-20T15:06:26.907050+09:00 | change | Reject unsafe manifest asset paths before release staging and revalidate before MSIX packaging | `security-manifest-asset-containment-20261020` |
| 4.6.9 | 2026-10-20T15:06:26.084262+09:00 | policy | 배포 단위 버전 체계로 전환; 기존 번호·이력·공개 패키지 보존 | `policy:release-unit-v2` |
| 4.6.9 | 2026-10-20T11:53:24.438016+09:00 | change | 실제 Windows 시스템 정보창의 OK 버튼 ID 2 변형을 정확한 지문과 함께 인식 | `native-observed-system-notice-ok-id2-20261020` |
| 4.6.8 | 2026-10-20T11:42:15.224369+09:00 | change | 정상 오늘 일정 요약을 명시적 Confirm으로 닫고 데이터·화면 검증을 이어가는 실제 재시작 흐름 보완 | `native-owned-startup-briefing-20261020` |
| 4.6.7 | 2026-10-20T11:28:17.801160+09:00 | change | 기동 로그는 엄격히 검사하고 첫 UIA 직전에 예외를 관찰하며 CI 시스템 알림과 화면 가림을 검증 | `native-observation-boundary-and-os-notice-20261020` |
| 4.6.6 | 2026-10-20T11:16:11.991124+09:00 | change | Windows 검증 VM의 줄바꿈 변환을 차단하고 실제 QA 파일과 Git blob 해시를 함께 검증 | `native-candidate-exact-checkout-bytes-20261020` |
| 4.6.5 | 2026-10-20T11:12:31.369927+09:00 | change | 검증 하네스의 종료 모달·화면·Windows 예외 관찰을 보완하고 동일 후보 패키지를 새 VM에서 재검증 | `native-owned-modal-exception-observer-and-candidate-reuse-20261020` |
| 4.6.4 | 2026-10-20T10:50:12.414162+09:00 | change | 격리 Windows 검증에서 실제 입력·메인 창 준비·정상 종료와 오류 증거를 확인 | `native-main-selection-and-runner-idle-20261020` |
| 4.6.3 | 2026-10-20T10:32:02.317807+09:00 | change | 별도 Windows VM에서 동일 배포 페이로드의 native 기동·재시작 검증 실행 | `isolated-native-validation-job-20261020` |
| 4.6.2 | 2026-10-20T10:21:06.865568+09:00 | change | Keep dependency lock bytes stable during release version sync and retain CI runtime diagnostics | `ci-lock-comment-stability-20261020` |
| 4.6.1 | 2026-10-20T10:10:26.659642+09:00 | change | 전용 Python 빌드에서 pywin32 등 원본 .pth 초기화를 보존해 Windows 통합 모듈 누락 방지 | `private-build-runtime-pth-initialization-20261020` |
| 4.6.0 | 2026-10-20T10:07:08.345455+09:00 | store | DB 손상 재발 방지와 최신 KeyDeck 전체 입력의 Store 릴리스 준비 | `store-db-runtime-fix-20261020` |
| 4.5.0 | 2026-10-20T10:07:07.158355+09:00 | module | 공식 SQLite 3.54.1 전용 빌드 런타임과 CI 네이티브 기동·재시작 검증 추가 | `pinned-sqlite-native-release-runtime-20261020` |
| 4.4.2 | 2026-10-20T09:31:12.752304+09:00 | change | Store DB 손상 재발 진단·물리 경로와 일관된 이관 보완, 실제 SQLite 및 native 재기동 배포 게이트 강화 | `store-startup-diagnostics-native-sqlite-gate-20261020` |
| 4.4.1 | 2026-10-20T09:06:17.092327+09:00 | change | KeyDeck 갤러리에서 Lo-fi·Neon·8-bit 키트를 별도 카드로 선택하고 이름 전체 표시 | `keydeck-beatmaker-kit-gallery-20261020` |
| 4.4.0 | 2026-10-19T18:08:22.531866+09:00 | module | KeyDeck 4x4 비트메이커, 3개 음원 키트, 드럼·멜로디 및 키보드 연주 추가 | `keydeck-beatmaker-20261019` |
| 4.3.3 | 2026-10-19T15:56:29.412985+09:00 | override | 사용자 지정 4.3.3 유지: 실제 Windows 스톱워치 글꼴 검사 강제종료 수정 및 최종 검증 입력 확정 | `user-release-4.3.3-safe-font-final-20261019` |
| 4.3.3 | 2026-10-19T15:50:30.426904+09:00 | override | 사용자 지정 4.3.3 유지: 영어·한국어 번역 파일의 기존 표준 키 배치 정규화(값 변경 없음) | `user-release-4.3.3-final-locales-20261019` |
| 4.3.3 | 2026-10-19T15:39:24.867720+09:00 | override | 사용자 지정 4.3.3 유지: DB 초기화 실패 연결 정리와 시작 오류 회귀 검사 반영 | `user-release-4.3.3-db-startup-20261019` |
| 4.3.3 | 2026-10-19T15:26:03.767491+09:00 | override | 사용자 명시 요청에 따른 미공개 Store 배포 버전 4.3.3 교정 | `user-release-4.3.3-20261019` |
| 4.5.0 | 2026-10-19T15:15:55.905503+09:00 | store | 키덱 전체·개별 효과음 및 Windows 네이티브 재생 모듈을 포함한 Store 릴리스 준비 | `store-keydeck-sound-20261019` |
| 4.4.0 | 2026-10-19T14:23:52.443998+09:00 | module | 키덱 전체·개별 효과음 설정 및 Windows 재생 경로 복구, 내장 효과음 24종 제공 | `keydeck-sound-controls-native-20261019` |
| 4.3.0 | 2026-10-19T10:06:07.235171+09:00 | store | 커밋 훅 서식 정규화의 AST·기존 frozen 구현 일치 검증을 마친 최종 2주 릴리스 입력 예약 | `store-cycle-20261005-final-inputs` |
| 4.2.0 | 2026-10-19T10:01:53.256108+09:00 | store | 2026-10-05 시작 2주 주기의 전체 실행 입력 통합 검증 후 Microsoft Store 릴리스 준비 | `store-cycle-20261005` |
| 4.1.2 | 2026-10-19T09:57:22.525754+09:00 | change | 기본 UI 글꼴에 없는 스톱워치 상태 기호를 지원 글꼴로 표시하고 기호별 선택 결과 캐시 | `20261019-stopwatch-supported-status-font` |
| 4.1.1 | 2026-10-19T09:46:05.497186+09:00 | change | Windows 글꼴의 지연 줄바꿈 재배치를 기다린 후 긴 동기화 안내문의 스크롤·버튼 접근성을 검증 | `20261019-sync-long-guidance-layout-wait` |
| 4.1.0 | 2026-10-16T21:44:09.547047+09:00 | module | 미확정 원격 생성의 로컬 삭제를 DB에 보존하고 완전 조회 후 기존 삭제 큐에 안전하게 연결 | `20261016-sync-pending-create-delete` |
| 4.0.8 | 2026-10-16T21:44:06.901010+09:00 | change | Outlook·CalDAV·ICS 워커 생성·신호 연결·시작 실패 복구와 실행 중 스레드 수명 보존 | `20261016-sync-worker-launch-boundaries` |
| 4.0.7 | 2026-10-16T21:44:04.153654+09:00 | change | ICS 개별 일정 요청·취소·응답을 전체 구독 스냅샷으로 반영하지 않도록 차단 | `20261016-sync-ics-snapshot-method` |
| 4.0.6 | 2026-10-16T21:44:01.632976+09:00 | change | 원격 삭제 직전 대기열 결정을 재확인하여 조회 중 원격 유지 선택 보존 | `20261016-sync-external-delete-decision` |
| 4.0.5 | 2026-10-16T21:43:58.850117+09:00 | change | 외부 동기화 요청 오류 후 최신 일정·연결·취소 상태를 재확인하여 잘못된 원격 삭제 상태 기록 방지 | `20261016-sync-external-stale-error` |
| 4.0.4 | 2026-10-16T21:43:56.363653+09:00 | change | 중복 동기화 요청이 실행 중인 Google 동기화 플래그를 해제하지 않도록 실행 소유권 보존 | `20261016-sync-google-active-guard` |
| 4.0.3 | 2026-10-16T21:42:42.643447+09:00 | change | Google 일괄 생성 전 DB 재조회 실패와 삭제·이동·수정 경합을 보류하고 개별 전송 재진입 차단 | `20261016-sync-google-batch-snapshot` |
| 4.0.2 | 2026-10-16T10:42:43.335442+09:00 | change | 전체 회귀 검사의 Google 런타임 fake와 홈페이지 공개 버전 기준 정합성 보완 | `20261016-audit-regression-contracts` |
| 4.0.1 | 2026-10-16T10:38:33.710841+09:00 | change | 시작 화면이 이미 삭제된 종료 경합에서도 원래 오류와 종료 결과 보존 | `20261016-audit-splash-cleanup-lifetime` |
| 4.0.0 | 2026-10-16T10:38:06.467861+09:00 | change | DB 초기화와 이관 실패 시 시작 중단 및 시작 단계 예외의 자원 정리 보완 | `20261016-audit-startup-failure-cleanup` |
| 3.9.9 | 2026-10-16T10:36:24.453917+09:00 | change | 여러 날 일정 제목의 손상 글꼴 크기 예외 방어 | `20261016-audit-multiday-font` |
| 3.9.8 | 2026-10-16T10:36:22.580454+09:00 | change | 자리 비움 감지 초기화와 시간 변경의 손상값 및 범위 보호 | `20261016-audit-idle-interval` |
| 3.9.7 | 2026-10-16T10:36:20.382390+09:00 | change | 매일 반복 일괄 생성의 날짜 누락과 마지막 날짜 오버플로 수정 | `20261016-audit-routine-batch-progress` |
| 3.9.6 | 2026-10-16T10:36:18.004250+09:00 | change | 반복 규칙 범위와 날짜 상한 검증으로 미리보기 예외 방어 | `20261016-audit-recurrence-boundaries` |
| 3.9.5 | 2026-10-16T10:36:16.159063+09:00 | change | 체크리스트 가져오기 사전 검증과 원자 저장 및 실패 복구 | `20261016-audit-checklist-import-atomic` |
| 3.9.4 | 2026-10-16T10:36:13.931072+09:00 | change | 라벨 프리셋 구조 검증과 손상 항목 분리 및 저장 복구 | `20261016-audit-label-preset-json` |
| 3.9.3 | 2026-10-16T10:36:11.275996+09:00 | change | 패널 최근 색상 목록의 비배열 JSON 예외 방어 | `20261016-audit-panel-color-json` |
| 3.9.2 | 2026-10-16T10:36:09.256763+09:00 | change | 자동 일정 색상 이력의 비배열 JSON 복구 | `20261016-audit-auto-color-json` |
| 3.9.1 | 2026-10-16T09:17:14.908386+09:00 | change | Google 동기화·인증·캘린더 목록 워커 시작 실패의 안전 복구와 재시도 보완 | `20261016-google-worker-launch-recovery` |
| 3.9.0 | 2026-10-15T09:12:14.811967+09:00 | module | 개별·모듈·Store 버전 규칙, 변경 이력·개발 실행 감지·스케줄러 연동 | `20261015-version-management-module` |
| 3.8.4 | 2026-10-15T09:12:13.963008+09:00 | change | 캘린더 이관 실패의 원자 복구와 바깥 트랜잭션 보존 | `20261015-calendar-migration-atomicity` |
| 3.8.3 | 2026-10-15T09:12:13.175858+09:00 | change | 드래그 중 예약 갱신과 오른쪽 패널 갱신 유실 보완 | `20261014-drag-refresh-preservation` |
| 3.8.2 | 2026-10-15T09:12:12.391061+09:00 | change | 자연어 날짜·주차·시각·제목 경계 오류 수정 | `20261014-nlp-date-time-boundaries` |
