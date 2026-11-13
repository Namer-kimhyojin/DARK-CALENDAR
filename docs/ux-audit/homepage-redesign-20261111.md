# 홈페이지 전면 개편 · 2026-11-11

사용자가 개선된 앱 UI·UX와 어울리는 홍보 홈페이지를 요청했다. 기존 GitHub Pages의 `docs/`를 개편했다. Product Design의 `audit` 스킬에 따라 기존 화면을 먼저 촬영하고, 실제 앱 화면과 현재 소스의 모양 설정을 확인한 뒤 구현·검증했다.

## 1. 첫 화면과 홍보 내용 — 개편 완료

- 검정 배경·그리드·발광 장식·개념 이미지를 홈페이지에서 제거했다. 앱의 밝은 라일락과 네이비를 기준으로 색, 글자, 여백을 다시 구성했다.
- 큰 실제 달력을 첫 화면에 배치했다. 일정 입력 → 모양 → 위젯 전용 모드 → 화면 탐색 → 캘린더 연결 순서로 설명한다. 중복 기능 목록과 대형 영어 구호를 줄였다.
- 공유 미리보기는 실제 앱 캡처를 사용한 1200×630 브라우저 렌더로 교체했다. 기존 OG 경로와 소유 채널·공유 링크는 유지했다.
- 홈페이지 전용 `home.css`, `home-content.js`를 추가했다. 기존 `styles.css`를 사용하는 다른 가이드와 홍보 페이지는 영향을 받지 않는다.
- 변경 전/후 동일 기본 브라우저 폭: [변경 전](../../output/playwright/homepage-redesign/01-before-desktop.png), [변경 후](../../output/playwright/homepage-redesign/02-after-desktop.png). [최종 데스크톱](../../output/playwright/homepage-redesign/08-final-desktop.png).

## 2. 실제 화면과 사용 흐름 — 동작 확인

- 월간 달력·위젯 모드·모양 설정·일정 입력·캘린더 연결·날씨·4트랙 루프덱의 7개 탭을 실제 클릭했다.
- 방향키 탭 이동, 선택 상태·tabpanel 라벨, 이미지 확대, Esc 닫기·원래 버튼으로 포커스 복귀, 모바일 메뉴 펼침·탐색 후 닫힘, FAQ 펼침을 확인했다.
- [모양 설정 확대](../../output/playwright/homepage-redesign/05-appearance-lightbox.png), [캘린더 연결](../../output/playwright/homepage-redesign/06-sync.png).
- 58개 정적 참조의 로컬 파일·앵커가 존재한다. 중복 ID·없는 앵커가 없다. 실제 이미지 로딩 완료를 DOM에서 확인했다. 콘솔 JavaScript 오류가 없었다.
- 요청 게시판 마크업과 API 코드는 보존했다. 서비스 GET은 공식 Origin에서 HTTP 200이며 localhost Origin은 `origin_denied`다. 따라서 로컬 미리보기의 게시판 연결 오류는 기존 서버의 Origin 허용 정책이다. 등록·수정·삭제와 관리자 로그인은 수행하지 않았다.

## 3. 모바일과 다국어 — 16개 조합 확인

- 한국어·영어·일본어·중국어를 320·390·768·1440px에서 각각 전환했다. 모든 조합에서 문서 가로 넘침이 없다.
- [최종 모바일](../../output/playwright/homepage-redesign/10-final-mobile.png), [치수 확인 결과](../../output/playwright/homepage-redesign/responsive-checks.json).
- 글자 대비는 앱과 같은 차분한 보라·잉크 계열로 잡았다. 키보드 조작, 포커스, 의미 있는 라벨과 reduced-motion 경로를 유지했다. 스크린리더 전체 시나리오나 WCAG 전체 적합성 감사는 수행하지 않았다.

## 화면 출처와 배포 상태

- 기존 `docs/assets/screenshots/5.0/` 이미지는 샘플 데이터로 촬영한 실제 앱 캡처다. 이를 새 버전의 네이티브 인수 촬영이라고 주장하지 않는다.
- `current/appearance-light.png`는 2026-11-11 현재 소스를 Windows Qt 백엔드로 렌더했다. 다이얼로그에 별도 INI 설정·임시 QWidget을 전달했고 설정 적용·저장은 실행하지 않았다. 앱 bootstrap·운영 DB 연결을 실행한 인수 촬영이나 실행 중인 사용자 앱 화면의 캡처는 아니다. [재현 스크립트](../../output/playwright/homepage-redesign/render_appearance.py).
- GitHub API의 최신 공개 태그 `v5.1.1`을 확인했다. 홈페이지의 공개 버전·Store 진행 상태·이벤트 설정은 그대로 유지했다. 현재 개발 기준 버전 `5.2.0`은 올리지 않는다.
- 이 작업은 로컬 소스 개편이다. Git 커밋·push·GitHub Pages 게시·앱 빌드·Store 제출은 수행하지 않았다.
- 홈페이지 관련 기존 계약 검사 2건 통과. 인코딩 검사 12건 및 컴파일 가드 통과. 최종 버전 기록과 `scan --strict` 결과는 작업 종료 시 확인한다.

## 수정 범위

`docs/index.html`, `docs/app.js`, `docs/home.css`, `docs/home-content.js`, `docs/homepage_content.json`, `docs/assets/og-air-calendar.png`, `docs/assets/screenshots/current/appearance-light.png` 및 이 문서·색인·작업 기록. 기존 dirty 앱 코드, 사용자 데이터, 다른 페이지 스타일은 유지했다.
