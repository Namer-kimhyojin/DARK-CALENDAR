# 버전 변경 이력

제품 버전은 배포 단위로 결정한다. 변경 기록·Git/CI 빌드·공개·Store·설치 상태는 별도이며 변경 기록만으로 버전을 올리지 않는다.

기준 버전: `3.8.1` · 현재 제품 버전: **`5.5.0`**

| 버전 | 일시(KST) | 유형 | 변경 내용 | 이벤트 ID |
|---|---|---|---|---|
| 5.5.0 | 2026-11-14T07:42:48.984285+09:00 | release | Ship the complete current Air Calendar source with UI/UX, localization, synchronization and KeyDeck improvements | `release-5.5.0-20261114` |
| 5.3.0 | 2026-11-14T07:41:17.685311+09:00 | change | Apply AST-identical calendar renderer formatting before the 5.5.0 release | `release-5.5.0-formatting-20261114` |
| 5.3.0 | 2026-11-14T07:33:48.763306+09:00 | change | Record canonical locale paths for the six new UI/UX draft and keyboard messages | `uiux-improvements-20261114-locales` |
| 5.3.0 | 2026-11-14T07:33:04.158056+09:00 | change | Improve monthly calendar accessibility and small-window scrolling; protect unsaved task drafts, compact schedule editor and align footer buttons | `uiux-improvements-20261114` |
| 5.3.0 | 2026-11-14T04:03:13.298955+09:00 | change | 텍스트 위젯 도움말 예시의 한국어 오타 수정(곳 마감 → 곧 마감) | `i18n-ko-typo-20261114` |
| 5.3.0 | 2026-11-14T04:01:50.602545+09:00 | change | 다국어 E: 16개 언어 문맥 번역 초안(검토 대기), 용어집, 번역 도구 문맥·줄바꿈 보존. 원문 수정: 도움말 메뉴 경로를 실제 메뉴 키에서 생성, Google 설정 안내 경로, 개수·날짜 문장 키, 영어 원문 오타, 패널 도움말 제목 | `i18n-e-20261114` |
| 5.3.0 | 2026-11-14T03:15:36.150362+09:00 | change | 도움말 콘텐츠의 높이가 초기 창 크기를 늘리지 않도록 스크롤 영역 배치 조정 | `maintenance-20261114-help-center-scroll-page-height` |
| 5.3.0 | 2026-11-14T03:15:34.378398+09:00 | change | 러시아어 끌기 안내를 짧게 정리해 복사와 이동 설명을 한 줄에 표시 | `maintenance-20261114-russian-drag-hint-width` |
| 5.3.0 | 2026-11-14T03:15:32.563671+09:00 | change | Windows 테마에서 일정 선택 상자의 긴 문구가 표시 폭을 넘지 않도록 줄임 처리 | `maintenance-20261114-task-selector-native-label-fit` |
| 5.3.0 | 2026-11-13T23:33:04.107608+09:00 | change | 다국어 C: 영어·한국어 원문 정리, 새 번역 키 222개, 하드코딩 문자열 t() 전환, 남은 destroyed lambda 4곳 정리, 번역 도구의 파일 필터 보호 | `i18n-c-20261113` |
| 5.3.0 | 2026-11-13T21:19:02.922053+09:00 | change | destroyed 신호에 연결한 정리 함수를 공용 도우미(qt_lifetime)로 옮김: GC로 수거된 동기화 문제 알림 창이 사라지고 이후 알림이 다시 뜨지 않던 문제, 날씨 요청·루프 믹서·대화상자 정리 중 강제 종료 위험 | `destroyed-hooks-20261113` |
| 5.3.0 | 2026-11-13T20:24:58.642554+09:00 | change | i18n-abd-20261113 기록의 파일 목록 정정: 이름 끝에 줄바꿈 문자()가 붙어 68개 파일이 등록되지 않았던 것을 같은 변경 내용으로 다시 등록 | `i18n-abd-20261113-files` |
| 5.3.0 | 2026-11-13T20:24:08.687624+09:00 | change | 다국어 점검 후속(A·B·D): Qt 기본 버튼 번역 우선, 요일·월 이름을 Qt 로케일에서, 기본 캘린더 이름 번역, 글꼴 기본값·라벨 폭, 19개 언어 파일 기계적 수정, 번역 감사 기준선, 대화상자 수명 정리 슬롯이 GC에 지워져 테스트가 강제 종료되던 문제 | `i18n-abd-20261113` |
| 5.3.0 | 2026-11-13T11:44:35.448539+09:00 | change | 하위 페이지 보라색 테마와 고해상도 아이콘 통일 및 언어 선택 목록 개선 | `site-violet-subpages-20261113` |
| 5.3.0 | 2026-11-13T11:31:48.390528+09:00 | change | 앱 깃털 아이콘에 맞춘 보라색 홈페이지 테마 및 고해상도 아이콘 적용 | `homepage-violet-feather-20261113` |
| 5.3.0 | 2026-11-13T11:14:23.306234+09:00 | release | 5.3.0: KeyDeck 터치·오디오 반응, 루프 믹서 녹음 개선, process형 체크리스트, 전역 창 단축키, 동기화 안전장치, 감사 후속 수정 | `release-5.3.0-20261113` |
| 5.2.0 | 2026-11-13T11:04:45.093293+09:00 | change | 남은 실패·한계 정리: 24pt 레이아웃·버튼 글자색·날짜 카드 글꼴 회귀 수정, 중국어 번역 보충, ICS 조회 스레드 상한, 덱 삭제 시 오디오 장치 해제, 복원 세션 사전 디코딩 | `audit-20261113-remaining` |
| 5.2.0 | 2026-11-13T10:21:30.868350+09:00 | change | 창 표시/숨김 전역 단축키를 Office 리본 접기(Ctrl+F1)와 겹치지 않는 Ctrl+Alt+Shift+F1로 변경 | `show-hide-hotkey-20261113` |
| 5.2.0 | 2026-11-13T10:19:31.522625+09:00 | change | 홈페이지 배치 시연 카드와 화면 미리보기의 테마 색상 연결 | `homepage-theme-surfaces-20261113` |
| 5.2.0 | 2026-11-13T10:16:03.743761+09:00 | change | 커밋 검사(ruff, ruff format)가 적용한 import 순서·서식 정리 | `commit-format-20261113` |
| 5.2.0 | 2026-11-13T10:00:22.841987+09:00 | change | 감사 후속 결정 반영: 빈 ICS 피드 확인, 삭제 충돌 선택지와 읽기 전용 캘린더 삭제 차단, KeyDeck 출력 장치 유지, 루프 믹서 이벤트 깨우기·녹음 개선·사용자 소리 사전 디코딩, 집중 모드 지시사항, 전역 단축키, 버전 이력 축소 | `audit-20261113-decisions` |
| 5.2.0 | 2026-11-13T08:38:23.403404+09:00 | change | 저장소 감사 후속 조치: 자리비움 잠금·데이터 보존·동기화 시간대·빈 ICS 피드·루틴 반복·process형 체크리스트 복구·Esc/F12 단축키·KeyDeck 터치 반응과 루프 믹서 지연·죽은 코드와 미사용 번역 키 정리 | `audit-20261113-maintenance` |
| 5.2.0 | 2026-11-13T03:04:37.493600+09:00 | change | Outlook 인증의 네트워크·일시 서버 오류를 재로그인이 필요한 오류와 구분 | `maintenance-20261113-outlook-auth-transient-retry` |
| 5.2.0 | 2026-11-12T03:07:25.711952+09:00 | change | QApplication을 모의하는 시작 오류 테스트에서 실제 Qt 아이콘 로딩을 격리 | `maintenance-20261112-bootstrap-test-icon-isolation` |
| 5.2.0 | 2026-11-12T03:07:23.763047+09:00 | change | DB 복원 도중 실패하면 기존 파일을 제자리로 되돌리고 같은 시각의 기존 보존본을 유지 | `maintenance-20261112-db-restore-file-rollback` |
| 5.2.0 | 2026-11-11T18:10:01.290342+09:00 | change | 바탕화면 달력 개별 이동, 자석 도킹과 배경 투명도 GIF를 홈페이지 및 공식 홍보자료에 반영 | `homepage-desktop-arrangement-20261111` |
| 5.2.0 | 2026-11-11T17:03:15.113628+09:00 | change | 공식 홍보자료 개편, 홈페이지와 자료실의 배치 편집기 화면을 전체 업무 관리로 교체, 위젯 9종과 6트랙 루프 믹서 반영 | `official-media-kit-20261111` |
| 5.2.0 | 2026-11-11T16:08:41.025233+09:00 | change | 투명 배경 GIF를 활용한 플립북 시계 3종 추가 | `transparent-clock-flipbook-gifs-20261111` |
| 5.2.0 | 2026-11-11T14:12:26.734916+09:00 | change | 디지털 시계 플립북 디자인과 숫자 카드 전환 추가 | `digital-clock-flipbook-20261111` |
| 5.2.0 | 2026-11-11T12:51:40.283770+09:00 | change | 날씨 위젯의 상태별 해안 등대 GIF 13종과 갤러리 재생 미리보기 추가 | `weather-animated-gif-20261111` |
| 5.2.0 | 2026-11-11T12:44:08.744739+09:00 | change | Air Calendar 홍보 홈페이지 전면 개편, 다크 모드 및 위젯 배경색·불투명도 체험과 실제 시계 위젯 GIF 추가 | `homepage-interactive-showcase-20261111` |
| 5.2.0 | 2026-11-11T12:36:58.135823+09:00 | change | 날짜 카드 GIF 디자인 6종과 움직이는 미리보기 추가 | `date-card-animated-gif-20261111` |
| 5.2.0 | 2026-11-11T12:04:55.681891+09:00 | change | Brighten the homepage with a vivid violet and blue palette and a matching share image | `homepage-color-refresh-20261111` |
| 5.2.0 | 2026-11-11T10:59:38.311439+09:00 | change | Use the required publication date marker in the observed 5.2.0 release checklist | `release-5.2.0-publication-date-marker-20261111` |
| 5.2.0 | 2026-11-11T10:53:54.381554+09:00 | store | Published the native-tested Air Calendar 5.2.0 GitHub release and verified all six public asset byte hashes | `release-5.2.0-github-published-20261111` |
| 5.2.0 | 2026-11-11T10:48:40.998839+09:00 | change | Pin GET-only six-asset readback to the unchanged 5.2.0 native-tested candidate | `release-5.2.0-asset-readback-20261111` |
| 5.2.0 | 2026-11-11T10:42:00.128912+09:00 | change | Install Qt for isolated encoding tests and compare visible menu ampersands in locale-dependent QA | `release-5.2.0-ci-test-environment-20261111` |
| 5.2.0 | 2026-11-11T10:38:57.372651+09:00 | change | Refresh homepage around actual application UI, lilac/navy visual identity, multilingual editorial copy and real-screen sharing artwork | `homepage-redesign-20261111` |
| 5.2.0 | 2026-11-11T10:26:53.494626+09:00 | release | Release integrated toolbar auto-hide, verified DB backup and recovery, appearance and widget readability improvements, translations, checklist copy and NLP fixes | `release-5.2.0-20261111` |
| 5.1.1 | 2026-11-11T10:26:51.140359+09:00 | change | Complete reviewed locale translations before the current release | `release-locale-finalization-20261111` |
| 5.1.1 | 2026-11-11T02:58:32.763032+09:00 | change | 자연어 일정 입력에서 시각 뒤에 이어지는 차수·연도·분기 제목을 보존 | `maintenance-20261111-nlp-numbered-title` |
| 5.1.1 | 2026-11-10T03:05:05.261798+09:00 | change | 끌어서 복사할 때 일정과 루틴의 체크리스트를 미완료 상태로 복사하고 저장 실패 시 전체 복사를 되돌림 | `maintenance-20261110-task-drop-checklist-copy` |
| 5.1.1 | 2026-11-09T20:10:47.166663+09:00 | change | 다국어 번역 점검: 16개 언어의 미번역·영문 혼용 문구를 번역하고 영어 원문 대비 1.25배(+8자) 이내로 맞춤, 탭 이름 참조 통일, 음원 제품명 영문 유지, 한국어 미번역 항목 보정, 19개 locale 파일 표준 형식 복구 | `locale-translation-coverage-20261109` |
| 5.1.1 | 2026-11-09T18:41:11.241807+09:00 | change | 위젯 전용 모드: 배율이 다른 모니터 사이 끌기를 OS 이동으로 바꿔 멈춤·크기 증가 해소, 바탕 불투명도 하한·불투명 표면·글자 대비 하한으로 배경화면과 무관한 가독성 보장 | `widget-mode-readability-multimonitor-20261109` |
| 5.1.1 | 2026-11-09T17:09:54.545537+09:00 | change | 테두리색·글씨 투명도를 모든 팔레트 경로에 일괄 적용, 패널 경계 이중선과 바탕화면 비침 제거, 상단 바 투명도를 패널과 통일, 요일 표시 세로 가운데 정렬, 중복 포인트 색(바이올렛) 라임으로 교체·라이트 에메랄드 조정, 포인트 버튼 글자를 같은 계열 색으로, 테스트가 실제 앱 설정을 쓰지 않도록 격리 | `theme-consistency-borders-text-accents-20261109` |
| 5.1.1 | 2026-11-09T15:54:01.883661+09:00 | change | 오늘의 브리핑 모달을 다른 모달과 같은 단일 카드로 바꿔 4면 투명 띠 제거, 오늘 일정 패널 제목을 다른 패널 제목과 같은 위치·색·크기와 제목 뒤 메뉴 표시로 정리 | `briefing-frame-and-today-title-20261109` |
| 5.1.1 | 2026-11-09T15:47:00.842896+09:00 | change | 배경 및 투명도에 테두리색(자동 추천/직접 지정) 추가와 테두리 투명도 실제 적용, 글씨 투명도를 가독성 섹션으로 옮겨 실제 화면에 적용(최소 30%) | `appearance-border-color-text-opacity-20261109` |
| 5.1.1 | 2026-11-09T15:28:12.618705+09:00 | change | 상단 바 자동 숨김 시 손잡이 띠를 레이아웃 밖 오버레이로 바꿔 상단 여백 제거 | `top-bar-hidden-no-gap-20261109` |
| 5.1.1 | 2026-11-09T15:20:55.383661+09:00 | change | 모양 설정을 화면 모드/포인트 색상(프리셋 9개+직접 지정)/배경 및 투명도로 정리해 스타일·포인트 중복 제거, Qt 내부 생성 대화상자(색상 선택 등)의 공통 헤더·그림자가 래퍼 소멸로 멈춰 제목이 안 보이던 문제 수정 | `appearance-mode-accent-opacity-20261109` |
| 5.1.1 | 2026-11-09T14:02:10.139598+09:00 | change | 상단 바 숨기기를 자동 숨기기로 통합(Ctrl+Shift+B), 표시 시 패널을 밀어내는 방식으로 변경, 고정 버튼 상시 노출·숨김 중 가운데 고정 탭과 손잡이 띠 추가, 빠른 이동 Ctrl+Shift+R 단축키 | `top-bar-auto-hide-unified-20261109` |
| 5.1.1 | 2026-11-09T13:30:14.588285+09:00 | change | 개인 DB 일일 검증 스냅샷(7개 보관)과 손상 시 최근 백업 복구·자동 재시작 추가, 테스트 실행을 실제 앱 데이터에서 격리 | `database-snapshot-restore-20261109` |
| 5.1.1 | 2026-11-09T11:57:54.537744+09:00 | change | 체크리스트 관리 검색, 항목 중심 배치 및 편집 내용 보호 개선 | `checklist-manager-ux-20261109` |
| 5.1.1 | 2026-11-09T11:49:41.501196+09:00 | change | 상단 바 숨김 영역을 없애고 고정 버튼을 오른쪽으로 이동 | `main-top-bar-edge-no-gap-20261109` |
| 5.1.1 | 2026-11-09T11:20:53.056704+09:00 | change | 명령 팔레트에서 상단 바 표시 및 자동 숨김 토글 실행 연결 | `main-top-bar-palette-dispatch-20261109` |
| 5.1.1 | 2026-11-09T11:19:34.614291+09:00 | change | 메인 상단 바 자동 숨기기, 펼치기 및 고정 토글 추가 | `main-top-bar-auto-hide-20261109` |
| 5.1.1 | 2026-11-09T10:48:47.146447+09:00 | change | 전체 글꼴 하드코딩 점검: 인쇄 글꼴·가로 전환 미리보기 시계·메뉴 글꼴 2곳·단축키 도움말 본문을 사용자 글꼴로 변경하고, 나머지 고정 글꼴을 기본값·후보·폴백·고정폭·스플래시로 분류해 허용 목록과 가드 테스트 추가, 16개 로케일의 키 순서 캐논 정렬 | `hardcoded-font-audit-20261109` |
| 5.1.1 | 2026-11-09T10:44:37.455011+09:00 | change | 루프 믹서 채널 조작부, 박자 타임라인 및 스테레오 출력 미터 개선 | `loop-mixer-console-ui-20261109` |
| 5.1.1 | 2026-11-09T10:28:25.144381+09:00 | change | 글꼴 점검: 모달 위젯 1,613개 모두 앱 글꼴 확인, 고정 글꼴을 쓰던 명령 팔레트 검색창·호버 카드·잠금 시계·집중 모드 타이머·드래그 카드를 사용자가 고른 앱 글꼴로 변경하고 재발 방지 테스트 추가 | `modal-font-follow-app-font-20261109` |
| 5.1.1 | 2026-11-09T10:07:01.623006+09:00 | change | 모양 설정·세부 모양 조정: 시스템 기본 전환 지연(4.6초→0.12초)과 화면 깨짐 수정, 모든 스타일 보기 제거, 푸터 구분선 중복 제거, 둥근 창 모서리와 라이트/다크 그림자 구분, 헤더·그림자가 초안 테마를 따르도록 수정, 파일 메뉴 가독성, 미리보기 글자 대비, 프리셋 문구 번역 | `appearance-settings-hardening-20261109` |
| 5.1.1 | 2026-11-09T09:20:26.171646+09:00 | change | 5.1.1 GitHub 공개·Store 초안 검증 및 사용자 수정 후 재개 보류 기록 | `maintenance-20261109-release-published-store-deferred` |
| 5.1.1 | 2026-11-09T08:50:51.578898+09:00 | change | 전체 테스트 크래시 원인 수정: 삭제된 HoverInfoPopup·상세 카드 싱글턴 재사용으로 이벤트 필터 예외가 프로세스를 종료시키던 문제, 연결 안 된 시그널 disconnect 예외, build_theme_snapshot이 전달된 설정 대신 전역 설정의 사용자 지정 글자색을 읽던 문제 수정 | `test-suite-crash-root-cause-20261109` |
| 5.1.1 | 2026-11-09T07:41:54.500606+09:00 | change | 테스트 안정화: 비트메이커 모달 포커스 보정으로 전체 테스트 네이티브 종료(0xC0000409) 해소, 위젯 배치 카드 겹침(전역 QToolButton 높이 제한·줄바꿈 라벨 높이) 수정, 외관 설정 큰 글꼴 한 열 배치 보장, 루프 믹서·PowerShell 정책 테스트 보정 | `test-suite-stability-20261109` |
| 5.1.1 | 2026-11-09T06:45:22.510242+09:00 | change | UI/UX: 반복 주기·방식 선택 상자를 번역 문구 길이에 맞춰 18개 언어의 잘림 해소, 메뉴·탭·버튼·그룹 제목의 '&' 문자가 사라지던 문제 수정, 비정상 글자 크기 설정값으로 외관 설정이 열리지 않던 오류 수정 | `ui-ux-i18n-fit-20261109` |
| 5.1.1 | 2026-11-09T06:19:48.114174+09:00 | change | 런타임 로그 기반 오류 수정: 재렌더링으로 삭제된 일정 상세 카드 동작 크래시 방지, 오프라인 httplib2 오류를 네트워크 오류로 분류해 계정 확인 오판 방지, 작업 스레드 DB 연결 종료 로그를 DEBUG로 낮춤 | `runtime-error-audit-20261109` |
| 5.1.1 | 2026-11-09T03:36:30.566322+09:00 | change | 제품 입력 변경 없이 5.1.1 고정 자산을 원격에서 재다운로드 검증할 QA 해시 및 ID 연결 | `release-5.1.1-readback-pins-20261109` |
| 5.1.1 | 2026-11-09T03:23:29.140274+09:00 | change | 검증 후 공개할 5.1.1 배포 문서와 링크 준비 | `release-5.1.1-publication-docs-20261109` |
| 5.1.1 | 2026-11-09T03:22:40.215946+09:00 | release | 5.1.0 미공개 실패 후보를 보존하고 키덱 전체 패키징 수정과 현재 전체 실행 입력으로 재준비 | `release-5.1.1-20261109` |
| 5.1.0 | 2026-11-09T03:22:22.009323+09:00 | change | 키덱 진입점 전환 후 자동 수집에서 빠진 호환 다이얼로그를 포함하도록 전체 키덱 패키징 보장 | `maintenance-20261109-keydeck-package-completeness` |
| 5.1.0 | 2026-11-09T03:12:14.871687+09:00 | change | Prepare isolated 5.1.0 publication documents and preserve exact legacy QA Git bytes | `release-5.1.0-publication-docs-20261109` |
| 5.1.0 | 2026-11-09T03:11:34.592548+09:00 | change | 11월 9일 기타 오버레이 728건·Windows 화면 점검 및 기존 5.1.0 배포 재개 기록 | `maintenance-20261109-review-checkpoint` |
| 5.1.0 | 2026-11-09T01:09:30.520075+09:00 | release | 독립 루프믹서와 다중 키덱·마이크 레이어, 모양 설정 재구성, 모달·배율·시작 성능 개선 | `release-5.1.0-20261109` |
| 5.0.2 | 2026-11-08T03:15:59.869539+09:00 | change | 11월 8일 KeyDeck·루프 믹서 점검과 11월 16일 후보·검증 근거 기록 | `maintenance-20261108-review-checkpoint` |
| 5.0.2 | 2026-11-08T03:15:34.598438+09:00 | change | 루프 믹서 복원 검사를 충분한 작업 영역과 사용자 크기 변경 저장 경로로 격리 | `maintenance-20261108-loop-mixer-persistence-fixture` |
| 5.0.2 | 2026-11-08T03:15:32.931346+09:00 | change | 겹쳐 녹음 중간 정지 시 미녹음 구간의 기존 오디오 보존 및 저장·복원·WAV 회귀 검증 | `maintenance-20261108-partial-overdub-preservation` |
| 5.0.2 | 2026-11-07T03:26:50.169074+09:00 | change | 편집기 및 프리셋 425건 점검과 5.0.2 게시 설치 후속을 11월16일 계획에 기록 | `maintenance-20261107-review-checkpoint` |
| 5.0.2 | 2026-11-07T03:26:48.507113+09:00 | change | Restore published 5.0.2 release checklist with observed Store and installation evidence | `release-5-0-2-checklist-20261107` |
| 5.0.2 | 2026-11-07T03:26:46.896605+09:00 | change | Store 5.0.2 게시 확인 및 홈페이지 심사 대기 안내 해제 | `store-5-0-2-publication-20261107` |
| 5.0.2 | 2026-11-07T03:26:45.123860+09:00 | change | WYSIWYG 편집기에서 메인 테마 투명도 연동을 명시하고 적용 시 기존 설정 보존 | `maintenance-20261107-editor-linked-opacity` |
| 5.0.2 | 2026-11-06T17:47:53.898501+09:00 | change | 모양 설정과 세부 조정 재구성, 초안·라이트 대비·검색·미리보기 및 408건 격리 회귀 검증 | `appearance-settings-redesign-20261106` |
| 5.0.2 | 2026-11-06T17:28:06.300613+09:00 | change | 색상 선택창의 전체 폭 제목과 네이티브 경계, 하위 초안 테마 계승 및 알파 저장 왕복 보완 | `color-picker-modal-chrome-alpha-20261106` |
| 5.0.2 | 2026-11-06T17:28:04.472388+09:00 | change | 모양 설정 팔레트 아이콘과 단일 기어 아이콘의 여백 및 DPI별 잘림 개선 | `appearance-toolbar-icons-20261106` |
| 5.0.2 | 2026-11-06T17:28:02.662429+09:00 | change | 모달 사방의 대칭 그림자와 외곽 대비 강화 및 그림자 버퍼 상한 검증 | `modal-four-sided-shadow-20261106` |
| 5.0.2 | 2026-11-06T16:31:07.277759+09:00 | change | Document mixed-monitor verification, audio fixes, widget styling and the interrupted native recording check. | `loop-mixer-native-qa-report-20261106` |
| 5.0.2 | 2026-11-06T16:28:28.690969+09:00 | change | Remove the top-level mixer shortcut and refine widget-mode surfaces with compact radii while retaining main theme roles. | `widget-menu-surface-refinement-20261106` |
| 5.0.2 | 2026-11-06T16:28:27.140827+09:00 | change | Keep logical widget sizes stable across mixed-DPI monitors and bound restored geometry and native buffers. | `mixed-dpi-placement-fixes-20261106` |
| 5.0.2 | 2026-11-06T16:28:25.544714+09:00 | change | Prevent backing WAV amplification during overdubs and preserve WinMM microphone buffer order. | `loop-mixer-native-capture-fixes-20261106` |
| 5.0.2 | 2026-11-06T15:28:35.784938+09:00 | change | Expose the independent Loop Mixer directly in the top Widgets menu and every KeyDeck context menu. | `loop-mixer-visible-entrypoints-20261106` |
| 5.0.2 | 2026-11-06T15:28:33.948115+09:00 | change | Reduce Windows first font initialization latency with a process-local Qt startup policy while preserving explicit platform choices. | `startup-windows-font-initialization-20261106` |
| 5.0.2 | 2026-11-06T14:51:30.245915+09:00 | module | Add an independent touch loop mixer with multiple KeyDeck sources, opt-in microphone capture, six PCM layers, local projects, and source identity preservation | `loop-mixer-touch-widget-20261106` |
| 5.0.2 | 2026-11-06T07:19:48.326311+09:00 | change | 실제 GitHub 5.0.2 공개 및 Store33 심사 제출 관찰에 맞춰 홈페이지4언어·소스제공URL·마지막공개메타데이터를 갱신하고 가격·이벤트·이미지·제품718입력 보존 | `publication-5.0.2-store33-metadata-20261106` |
| 5.0.2 | 2026-11-06T06:59:22.708713+09:00 | change | 로컬 CDN 연결 제한에 대응해 고정 릴리스 6자산을 격리 CI에서 GET 재다운로드하고 draft/public 바이트와 공개 무인증 가시성을 검증하는 QA 보완 | `release-5.0.2-asset-readback-qa-20261106` |
| 5.0.2 | 2026-11-06T06:20:42.951359+09:00 | release | 현재 전체 5.0 UI UX 및 Loop Deck와 Qt 정상 종료 객체 수명 보완을 통합한 배포판 | `release-5.0.2-qt-shutdown-20261106` |
| 5.0.1 | 2026-11-06T06:20:40.524222+09:00 | store | 5.0 UI UX 및 종료 수명 정리 보완을 포함한 5.0.2 공개 릴리스 안내 준비 | `release-5.0.2-notes-20261106` |
| 5.0.1 | 2026-11-06T06:20:38.530989+09:00 | change | Qt 정상 종료 단계에서 저장 및 작업 중지 후 UI·그림자·네트워크 객체를 DeferredDelete로 정리하고 종료 중 cosmetic 재진입과 app 강참조를 해소하며 사용자 위젯 설정 보존 | `qt-runtime-deferred-cleanup-20261106` |
| 5.0.1 | 2026-11-06T05:40:07.535741+09:00 | release | 현재 전체 UI UX 및 4트랙 Loop Deck를 포함한 5.0 배포의 Qt Tool 모달 소유 관계 수정판 | `release-5.0.1-exit-owner-20261106` |
| 5.0.0 | 2026-11-06T05:39:55.507578+09:00 | store | 5.0 UI UX와 Loop Deck 및 종료 확인창 수정의 공개 릴리스 안내 준비 | `release-5.0.1-notes-20261106` |
| 5.0.0 | 2026-11-06T05:39:53.270628+09:00 | change | 공식 빌드의 동일 payload native 게이트에 검토된 owner 및 hosted surface 관측을 조립하며 원본 6회 실행 및 draft 차단 조건 유지 | `official-native-entry-composition-20261106` |
| 5.0.0 | 2026-11-06T05:39:51.275738+09:00 | change | Qt 6.12 Tool 메인 창에서 누락되는 모달 transient owner를 기존 네이티브 창 생성 후 복구하고 지정된 manager owner 및 모달 예외를 보존 | `dialog-tool-native-owner-fix-20261106` |
| 5.0.0 | 2026-11-06T05:12:49.488583+09:00 | change | 동일 clean 5.0.0 CI 페이로드의 고정 해시·입력 718개·QA 모듈 부재·6회 native 게이트를 검증하고 정확히 식별한 검증 VM 성능 옵션 창만 최소화 | `release-5.0.0-clean-native-qa-20261106` |
| 5.0.0 | 2026-11-06T05:12:37.670146+09:00 | change | Qt 소유 창의 Win32 검증을 추가하고 기존 종료·브리핑·물리 화면 게이트를 유지하는 QA 보완 | `release-5.0.0-owned-dialog-qa-20261106` |
| 5.0.0 | 2026-11-06T03:53:29.711124+09:00 | change | 진단 QA만: 해시고정된 기존오염 payload의새VM실행과실패전 실제화면·외부창 정체 수집; 엄격원본게이트와 배포부적격 유지 | `release-5.0.0-native-visibility-diagnostics-20261106` |
| 5.0.0 | 2026-11-06T03:49:30.868446+09:00 | change | QA만: 비검증 Python 자식의 QA검색경로 제거로 frozen sitecustomize 혼입 차단; 실제 최소PyInstaller 산출물 비포함과13회귀 검증, 제품718입력 보존 | `release-5.0.0-qa-loader-packaging-isolation-20261106` |
| 5.0.0 | 2026-11-06T03:24:36.759550+09:00 | change | 홈페이지5.0새인터페이스 실제화면과4언어소개, 반응형과확대보기 검증; 게시버전·Store상태와 출시미리보기 구분 | `release-5.0.0-homepage-ui-preview-20261106` |
| 5.0.0 | 2026-11-06T03:19:00.718453+09:00 | change | QA만: Python3.14 slice상수의 정규 직렬화 지원, 원본 검증기와 제품718입력 및 구현 불일치 차단 보존; 실패 CI42080904894 증거 유지 | `release-5.0.0-qa-slice-fingerprint-20261106` |
| 5.0.0 | 2026-11-06T03:01:23.649545+09:00 | change | QA만: immutable4.3.3 baseline과5.0 Python3.14/Qt6.12의 DLL·정확한 모달창 클래스 구분 및 원본 엄격 게이트 보존 | `release-5.0.0-qa-runtime-adapter-20261106` |
| 5.0.0 | 2026-11-06T02:45:25.031660+09:00 | release | 사용자 지정 5.0 배포: 통일된 UI·라이트 테마·글자와 입력 UX, 요일 표시, 위젯 테마 계승, 4트랙 루프덱 및 보안 런타임 통합; 미빌드 4.10.0 예약을 대체 | `release-5.0.0-integrated-20261106` |
| 4.10.0 | 2026-11-06T02:43:02.832653+09:00 | release | 통일된 모달·라이트 테마·글자/입력 UX, 요일 표시 선택, 위젯 테마 계승, 4트랙 루프덱, 보안 런타임 및 전체 현재 실행 입력 통합 | `release-4.10.0-integrated-20261106` |
| 4.9.2 | 2026-11-06T02:27:59.977195+09:00 | change | Diagnose first calendar startup with isolated Windows phase and font metrics timings: default first frame 31.4s versus diagnostic GDI 4.3s. Record launcher overhead and evidence limits without changing product runtime behavior. | `startup-performance-diagnosis-20261106` |
| 4.9.2 | 2026-11-06T01:55:53.832775+09:00 | change | Add a four-track sound-only loop deck with pad recording, shared-phase looping, overdub, mute/gain, quantization, persistence, Studio undo and WAV deck sharing. Preserve v1 recordings; verify full pads and tracks at Windows 100/125 percent with actual audio backend. | `beatmaker-loopdeck-four-tracks-20261106` |
| 4.9.2 | 2026-11-06T01:54:43.339015+09:00 | change | Unify typography, accent modal palette and shadows; fix title geometry, modal ownership and message visibility; cycle weekday placement and inherit main widget theme. Validate Windows 100/125 percent and 322 tests plus 69 subtests. | `unified-ui-typography-modal-weekday-20261106` |
| 4.9.2 | 2026-11-05T23:21:28.630424+09:00 | change | Pearl Lilac 라이트 시안과 공통 팔레트 적용, 모드 및 직접 색상 출처 보존, 상태·선택 안내 대비와 브리핑·인증 버튼 보완 | `light-mode-pearl-lilac-20261105` |
| 4.9.2 | 2026-11-05T22:34:25.475576+09:00 | change | Prevent wheel edits globally while preserving content scrolling, make modal reading surfaces opaque, fix management shell ownership and closing, unify widget subtabs and dock tab transparency, and repair keyboard and feedback lifetime UX. | `ui-usability-wheel-and-modal-20261105` |
| 4.9.2 | 2026-11-05T21:42:10.956204+09:00 | change | Unify native modal chrome and sizing, improve calendar and feedback surfaces, apply theme-aware feather branding and splash, and fix Qt callback lifetimes with physical Windows evidence. | `windows-modal-brand-system-20261105` |
| 4.9.2 | 2026-11-05T18:38:56.544909+09:00 | change | Audit fresh native dialog states and repair contrast, automatic theme resolution, tables, previews, modal actions, long alarms and focus feedback | `native-ui-consistency-audit-20261105` |
| 4.9.2 | 2026-11-05T17:43:12.997390+09:00 | change | Extend the selected theme across all native dialog paths, provider and widget settings, alarms, briefing and focus feedback while preserving custom colors and transparency | `shared-native-dialog-visual-system-20261105` |
| 4.9.2 | 2026-11-05T17:42:35.306301+09:00 | change | Fix duplicate schedule detail actions by reusing two buttons and publishing only fully prepared popup content | `detail-action-row-single-instance-20261105` |
| 4.9.2 | 2026-11-05T15:07:12.944526+09:00 | change | Native navy and lilac calendar and editor redesign with theme, opacity and free layout preserved | `navy-lilac-native-redesign-20261105` |
| 4.9.2 | 2026-11-05T12:21:06.467191+09:00 | change | Verify Google calendar-specific and service-wide failures separately | `calendar-subscription-google-failure-scope-tests-20261105` |
| 4.9.2 | 2026-11-05T12:19:08.702654+09:00 | change | Google first sign-in and incremental sync recovery, cross-provider retry and ICS worker safety | `calendar-subscription-google-recovery-20261105` |
| 4.9.2 | 2026-11-05T09:27:04.597737+09:00 | change | 실제 Windows 100%·125% 모니터 이동 12건 검증과 11월 16일 통합 배포 범위 기록 | `maintenance-20261105-monitor-physical-dpi-evidence` |
| 4.9.2 | 2026-11-05T08:45:05.665206+09:00 | change | Keep monthly context while inspecting a date and add a spacious monthly agenda layout | `main-month-agenda-ux-20261105` |
| 4.9.2 | 2026-11-05T08:07:33.583151+09:00 | change | Patch Qt networking, pyasn1, bundled OpenSSL and setuptools advisories | `dependency-security-qt612-20261105` |
| 4.9.2 | 2026-11-05T07:53:32.069004+09:00 | change | Move Air Calendar development and release runtime to security-patched CPython 3.14.10 | `python-security-runtime-3-14-10-20261105` |
| 4.9.2 | 2026-11-05T07:27:55.596490+09:00 | change | Verify locked release dependency archives with SHA-256 and update certifi and pip for certificate trust fixes | `release-dependency-integrity-20261105` |
| 4.9.2 | 2026-11-05T03:05:29.084961+09:00 | change | 이전·다음 모니터 단축키 방향 분리와 위젯 모드 4일차 점검 기록 | `maintenance-20261105-previous-monitor-shortcut` |
| 4.9.2 | 2026-11-04T23:53:52.329845+09:00 | change | Document UI UX risks and development environment modernization plan; no runtime changes | `ui-ux-dev-readiness-plan-20261104` |
| 4.9.2 | 2026-11-04T03:00:34.307691+09:00 | change | Store 4.9.2.0 설치 확인과 주간 보기·선택·키보드 점검 결과 기록 | `maintenance-20261104-store-installed-day03` |
| 4.9.2 | 2026-11-03T09:02:32.329855+09:00 | change | 상단 동기화 아이콘을 연결 및 구독으로 연결하고 활성 서비스와 필요한 조치를 카드 위주로 표시 | `sync-toolbar-connected-services-20261103` |
| 4.9.2 | 2026-11-03T03:22:48.049259+09:00 | change | 4.9.2 배포 확인표의 원래 출시일을 유지하고 Store 게시 후속 관찰일을 별도 표시 | `maintenance-20261103-preserve-release-date-contract` |
| 4.9.2 | 2026-11-03T03:18:49.003067+09:00 | change | Store 4.9.2 게시 확인에 따른 홈페이지 상태와 유지보수 후보·2일차 점검 인수 기록 정합화; 제품 버전 유지 | `maintenance-20261103-store-492-published-day02` |
| 4.9.2 | 2026-11-02T10:13:36.278627+09:00 | change | QA-only: preserve exact historical 4.3.3 SIP teardown failure as FAILED, independently validate its closed synthetic upgrade DB, and require all six unchanged 4.9.2 candidate exits zero | `native-legacy-upgrade-fixture-20261102` |
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
