# 창·모달·서브 탭 사용성 보완

2026-11-05, 개발 소스 4.9.2. 사용자 첨부 화면과 이번 실행에서 새로 캡처한 화면을 기준으로 검토했다. 전체 프로그램의 공통 입력·모달 정책을 수정하고, 아래 주요 사용자 흐름을 직접 확인했다.

## 점검 흐름과 결과

1. **메인 하단 탭 — 정상.** 탭 오른쪽 빈 영역과 기본 base 그리기를 제거했다. 탭 버튼의 배경·선택·호버는 유지한다. dark/light/custom 격리 픽셀 probe에서 빈 영역 19,592px 전부 alpha 0, 탭 내부 배경은 유지됐다. 이는 실제 gray fill 이전 화면을 재현한 증거가 아니라 현재 투명도 계약의 픽셀 확인이다. [결과](../../artifacts/ui_usability_followup_20261105/dock-tab-probe/pixels.json).
2. **일정 입력·본문 스크롤 — 정상.** QApplication 전역 필터가 날짜·시간·정수·소수·콤보·글꼴·슬라이더·다이얼·탭·달력 팝업의 휠 값 변경을 막는다. KeyDeck 페이지·파노라마 확대·위젯 스택도 같은 정책을 적용한다. 본문/표/열린 콤보 목록/스크롤바는 스크롤하고, 클릭·키보드·화살표로 값을 편집할 수 있다. 보호 입력 위의 휠은 가까운 스크롤 viewport로 한 번만 전달한다. 실제 125% Windows에서 날짜/시간 lineedit 위 휠 두 동작 동안 날짜 `2026-11-05`, 시간 `12:00`을 유지하고 스크롤 위치가 `0→240→120`으로 바뀌었다. 그 뒤의 별도 마우스 화살표 클릭으로 시간 값이 바뀐 것은 허용된 편집으로 구분했다. [입력 로그](../../artifacts/ui_usability_followup_20261105/native-wheel-input/interaction.jsonl).
3. **전체 업무 관리 3개 탭 — 정상.** 내부 관리 페이지의 제목줄을 바깥 모달 제목줄로 잘못 채택하던 원인을 수정했다. 바깥 제목/닫기 한 개가 탭 위에 배치된다. 임베디드 페이지는 개별 chrome을 만들지 않고 ESC도 바깥 모달을 닫는다. 조기 child.show를 제거해 부모 표시 수명을 따르도록 했다. X/ESC/window-close 3탭×3동작, 탭 재방문·새로고침·캘린더/상태 필터의 독립·조합 동작을 검사했다. 검색칸에 placeholder·접근성 이름도 추가했다.
4. **위젯 관리자 서브 탭 — 정상.** 바탕화면 위젯·위젯 전용 모드·작업 공간의 본문과 viewport를 공통 테마로 통일했다. 기본 검은 표면이 남던 원인은 이름/스타일이 없는 스크롤 viewport였다. 사용자가 따로 선택한 개별 위젯 스킨은 유지한다.
5. **브리핑과 모달 가독성 — 정상.** 브리핑 확장 설정 패널의 gradient 끝점이 사용자 투명도를 그대로 사용해 뒤 캘린더가 비쳤다. 모달 읽기 표면 7종은 실제 모달 배경과 합성한 불투명 색으로 통일했다. 메인·독립 위젯 투명도 및 모달 바깥 둥근 모서리 투명은 유지한다.
6. **도움말·체크리스트·연결 설정 — 정상.** 도움말 검색 Enter가 기본 닫기를 실행하지 않도록 했다. 체크리스트 Ctrl+Up/Down이 텍스트 입력 중 항목 순서를 바꾸던 단축키 범위를 표로 제한했다. Delete/Return도 표 범위로 명확히 했으나 두 키의 과거 입력 가로채기는 재현되지 않았으므로 별도 확정 결함으로 주장하지 않는다. 저장 피드백은 버튼 소유 타이머로 바꾸어 삭제 후 callback과 연속 저장 라벨 복원 오류를 막았다. 캘린더 5탭·Google 5탭도 같은 입력/모달 규칙으로 확인했다.

## 새 실화면 증거

Qt windows 플랫폼, 실제 96/120 DPI, 강제 배율 환경변수 없이 OS HWND/desktop을 캡처했다. 이번 audit의 채택 결과는 100% 네이비 24상태와 125% 사용자 색상·낮은 투명도 24상태, 각각 오류 0·작업 영역 내 배치·정상 종료다. [100%](../../artifacts/ui_usability_followup_20261105/accepted-native-100-navy/subtab-audit.json), [125%](../../artifacts/ui_usability_followup_20261105/accepted-native-125-custom/subtab-audit.json).

### 2. 입력과 스크롤

![휠 후 값이 유지되고 본문만 스크롤된 화면](../../artifacts/ui_usability_followup_20261105/native-wheel-input/after-wheel.png)

### 3. 제목 아래에 배치된 관리 탭

![전체 업무 관리](../../artifacts/ui_usability_followup_20261105/accepted-native-100-navy/01-work-management-tab-0.png)

### 4. 공통 배경으로 정리한 위젯 전용 모드 탭

![위젯 관리자 서브 탭](../../artifacts/ui_usability_followup_20261105/accepted-native-125-custom/06-widget-manager-tab-1.png)

### 5. 뒤 글자가 비치지 않는 브리핑 확장 패널

![브리핑 가독성 보완](../../artifacts/ui_usability_followup_20261105/accepted-native-125-custom/09-daily-summary-settings-open.png)

### 6. 도움말 검색 후 결과 유지

![도움말 검색](../../artifacts/ui_usability_followup_20261105/accepted-native-100-navy/12-help-center-search-enter.png)

초기 125% 관리창의 native HWND가 숨겨진 캡처 3장은 채택하지 않았다. Qt isVisible만으로 성공 처리하지 않고 오류 JSON을 남겼으며, 조기 자식 표시 제거 후 같은 parented 실행에서 3개 탭이 모두 실제 HWND 캡처에 성공했다. `native-125-custom`의 실패와 `accepted-native-125-custom`의 성공을 구분한다.

## 자동 검사와 데이터 경계

- 휠·태스크 create/modify/move/copy·calendar_id·시작 실패 정리: **86 passed, 15 subtests**, 정상 종료.
- 모달 표면·테마·위젯 관리자·작업 공간·KeyDeck: **177 passed, 12 subtests**, 정상 종료.
- 관리창 shell·닫기·필터: **20 passed, 13 subtests**, 정상 종료.
- 도움말·체크리스트 키보드/피드백: **30 passed, 4 subtests**, 정상 종료.
- Ruff·diff·인코딩/컴파일 가드 통과. 각 묶음의 XML과 `.settings.json`은 `artifacts/ui_usability_followup_20261105`에 보관한다. 테스트 수는 묶음별 실행 결과다.

QA의 SQLite/shared DB와 설정은 임시 경로다. QSettings 인스턴스가 임시 INI만 쓰도록 생성자와 쓰기 시 format/path를 감사했다. 거부된 쓰기 0건이다. 동시에 실행 중인 실제 앱의 native 스냅샷에서 `last_successful_sync`가 바뀐 실행은 별도로 기록했고, 사용자 설정을 복원하지 않았다. 최종 native 48상태 실행은 스냅샷 변화도 없었다. 사용자 실제 앱을 닫거나 계정 연결·일정·배포본을 바꾸지 않았다.

화면 캡처는 모든 보조기술·계정 오류·데이터 크기 조합을 검증하지 않는다. Google/ICS 캡처는 임시 계정 없는 설정 화면이며 실제 동기화 성공 증거가 아니다. 개별 위젯 스킨의 별도 시각 선택도 전체 테마와 구분한다. 이 개선 다음 단계로 요청한 [라이트 모드 시안과 구현 검증](light-mode-pearl-lilac-20261105.md)을 진행했다.
