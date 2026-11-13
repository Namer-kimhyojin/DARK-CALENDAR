# Windows 공통 모달·알림·브랜드 개선 검증

검토일: 2026-11-05. 대상: Air Calendar 4.9.2 개발 소스.

## 구성 원칙과 구현

[전체 구성 시안](../../artifacts/native-windows-ui-20261105/modal-design-system.png)은 선택된 네이비·라일락을 기준으로 내부 제목/닫기, 스크롤 본문, 고정 하단 동작을 정리한 디자인 참고 이미지다. 실제 기능과 필드, 저장 방식은 기존 프로그램을 따른다.

| 사용자 요청 | 구현 및 확인 범위 |
|---|---|
| 기본 타이틀바·중복 닫기 제거 | 앱 소유 QDialog에 공통 frameless 프레임 적용. 기존 편집 헤더와 닫기 핸들러를 재사용하고, 없는 창에 내부 제목·닫기·이동·크기 조절을 제공한다. ESC, Alt+F4, reject/closeEvent, QMessageBox 취소 의미를 보존한다. OS 기본 파일 선택기는 Windows 표준 창을 유지한다. |
| 전체 모달 크기 최적화 | 명시한 초기 크기를 숨은 탭의 최대 sizeHint로 확대하지 않는다. 작업 영역 안에서 초기 여백을 확보한다. 캘린더 관리 기본 960×680, 모양 설정 960×740 기준이며 실제 화면 높이에 맞춰 제한한다. |
| 모양 설정 사용성 | 넓은 창은 설정/미리보기 두 열, 좁은 창은 세로 배치. 미리보기는 필요한 높이만 사용한다. 프리셋 카드 높이를 명시해 썸네일 돌출을 수정했다. 모든 색상·투명도·초기화·취소 기능을 유지한다. |
| 일반업무 입력 오류 | 본문 표면을 선택 탭 색상과 분리하고 스크롤 viewport 배경, 하단 버튼 높이를 정리했다. 기본/상세/체크리스트 탭을 유지한다. |
| 숫자 입력 화살표 | 기존 실제 Windows 화면에서도 화살표는 보였다. 확인된 문제는 정수/소수 입력의 높이·배경 불일치였다. QDoubleSpinBox를 공통 스타일에 포함하고 화살표·비활성 상태를 명시했다. 클릭·길게 누르기·한계값·키보드 계약을 검사했다. |
| 스크롤 무늬 | Windows 기본 페이지/줄 부분의 패턴이 남던 스크롤바에 투명 표면을 명시했다. |
| 요일/일자 구분선 | 월간 요일 헤더 아래 1px 토큰 구분선을 복원했다. 5/7열 및 밝은/어두운/사용자 투명 색상에서 연속성을 검사했다. |
| 1주 시간표 | 날짜·선택일·오늘 표시, 종일 영역, 시간/반시간 선, 일정 카드 글자 계층을 정리했다. 드래그·이동·크기 조절·겹침 배치와 투명도 계약을 유지한다. |
| 일반 알림 | 일반 작업 피드백을 Air Calendar 자체 토스트로 변경했다. 한 카드 재사용, 연속 알림 교체, 자동 닫기와 마우스 오버 일시정지를 제공한다. 명시적 시스템 알림 경로와 실제 일정 알람은 유지한다. |
| 로고·스플래시 | 선택한 깃털 심벌과 Air Calendar 이름을 적용했다. 공용 알파 마스크를 현재 강조색으로 틴트하고 실제 배경 대비와 DPR을 반영한다. 상단 바·공통 모달·토스트·스플래시에서 재사용한다. 스플래시는 480×280, 표시 진행률과 막대를 일치시킨다. 정적 설치/패키지 아이콘은 동일 master에서 생성한다. |

## 실제 Windows 증거

모든 QA 앱은 임시 SQLite·shared DB·INI 설정을 사용한다. 사용자 앱을 종료하거나 개인 일정·계정·설정을 변경하지 않았다. Python 소켓·DNS·winreg 쓰기를 차단하고 QSettings를 임시 INI로 전환했다. 이는 OS 전체 네트워크 차단을 뜻하지 않는다. 종료 후 원래 설정 보존을 확인한다.

Qt `windows` 플랫폼에서 `GetDpiForWindow`, 실제 Win32 창/작업 영역과 Qt DPR을 함께 기록한다. 배율 환경변수는 제거한다. 현재 장비에서는 96 DPI/100%, 120 DPI/125%가 확인된다. 각 JSON의 `physical_scale_evidence`, `native_frame_inside_work_area`, `native_preferences_preserved`를 판정 근거로 사용한다.

캡처는 실제 OS 표면이다. 일반 HWND는 `QScreen.grabWindow(HWND)`, 투명 layered 창은 실제 모니터 desktop 캡처를 Win32 물리 좌표로 잘라 저장한다. QWidget.render/grab을 실화면 증거로 사용하지 않는다. Qt 공식 문서도 Windows layered 창에 desktop capture를 안내한다: [QScreen.grabWindow](https://doc.qt.io/qt-6/qscreen.html#grabWindow).

초기 `matrix-native-100/125`의 토스트·스플래시 검은 이미지는 캡처 방식의 실패로 제외한다. `final-native-125-navy`의 장치 이름 매칭 실패 JSON도 보존한다. 수정 후 별도 final 경로를 사용한다. 기존 before의 `routine-125` 폴더는 이름과 달리 실제 96 DPI이므로 100% 증거로만 해석한다.

| 채택한 실행 증거 | 상태 수 | 실제 DPI | 판정 |
|---|---:|---:|---|
| [100% 네이비](../../artifacts/native-windows-ui-20261105/accepted-native-100-navy/matrix.json) | 23 | 96 | 완료, 오류 0, 작업 영역 내 배치, 설정 보존 |
| [125% 네이비](../../artifacts/native-windows-ui-20261105/accepted-native-125-navy/matrix.json) | 23 | 120 | 완료, 오류 0, 작업 영역 내 배치, 설정 보존 |
| [125% 밝은 테마](../../artifacts/native-windows-ui-20261105/accepted-native-125-light/matrix.json) | 23 | 120 | 완료, 오류 0, 작업 영역 내 배치, 설정 보존 |
| [125% 사용자 색상·투명도](../../artifacts/native-windows-ui-20261105/accepted-native-125-custom/matrix.json) | 23 | 120 | 완료, 오류 0, 작업 영역 내 배치, 설정 보존 |
| [메인 월간·주간 100%](../../artifacts/native-windows-ui-20261105/main-native-100-navy/main-captures.json) | 4 | 96 | bootstrap→OverlayApp, 전체/좁은 폭, 정상 종료 |
| [메인 월간·주간 125%](../../artifacts/native-windows-ui-20261105/accepted-main-125-custom-settled/main-captures.json) | 4 | 120 | bootstrap→OverlayApp, 전체/좁은 폭, 정상 종료 |

대표 실화면: [모양 설정](../../artifacts/native-windows-ui-20261105/accepted-native-125-navy/10-appearance-initial.png), [캘린더 관리 4개 목록](../../artifacts/native-windows-ui-20261105/accepted-native-125-navy/13-calendar-hub-tab-1.png), [알림](../../artifacts/native-windows-ui-20261105/accepted-native-125-navy/21-feedback-visible.png), [네이비 스플래시](../../artifacts/native-windows-ui-20261105/accepted-native-125-navy/23-splash-startup.png), [사용자 색상 스플래시](../../artifacts/native-windows-ui-20261105/accepted-native-125-custom/23-splash-startup.png), [투명 월간 화면과 구분선](../../artifacts/native-windows-ui-20261105/accepted-main-125-custom-settled/01-monthly-full.png), [1주 시간표](../../artifacts/native-windows-ui-20261105/main-native-100-navy/02-weekly-full.png).

메인 QA helper의 초기 125% 이동은 첫 paint 중 직접 HWND/DPR를 바꾸어 실패했다. QA callback을 queued로 바꾸고 앱 DPI 핸들러가 끝난 후 임시 뷰포트를 맞춘 실행만 채택한다. 제품의 모니터 이동 코드를 바꾼 결과로 주장하지 않는다. 메인 증거는 다른 창에 가리지 않도록 해당 QA 창만 topmost로 올린 상태이며 JSON에 이를 명시한다.

실제 Windows 입력도 별도로 확인했다. 100%에서 제목줄을 끌어 native 원점이 `(610,186)→(670,216)`으로 이동했고 내부 닫기 버튼으로 정상 종료했다. 125%에서는 `(1541,1178)→(1591,1198)`으로 이동한 뒤 크기를 논리 700×660에서 650×620으로 줄였다. 하단 동작이 유지되고 Alt+F4로 정상 종료했다. [조작 후 화면](../../artifacts/native-windows-ui-20261105/interaction/final-routine-125-confirmed/after-move-resize.png), [WGC 관찰값](../../artifacts/native-windows-ui-20261105/interaction/final-routine-125-confirmed/sky-observations.json), 같은 폴더의 `interaction.jsonl`에 native DPI·bounds·마우스 대상을 기록했다. ESC도 별도 임시 세션에서 정상 종료했다.

Windows frameless 모달에서 시스템 이동/크기 조절 루프가 입력을 받아도 실제 좌표를 바꾸지 않는 현상을 확인해, 공통 제목줄과 기존 QSizeGrip의 Qt 이동/크기 조절 경로로 보완했다. 최소·최대 크기와 RTL 기준점을 검사한다. 위 실화면 조작은 한 모니터 안의 이동이며 Aero Snap·서로 다른 DPI 경계를 가로지르는 연속 드래그를 검증한 것으로 확대하지 않는다. 조작용 fixture는 임시 대화창을 독립 UI 자동화 대상으로 노출한 상태이며 실제 앱의 모달 소유 관계는 바꾸지 않는다.

## 회귀 검사와 발견한 종료 오류

아래 자동 UI 회귀는 Qt offscreen 검사다. 실제 Windows 마우스 조작과 위 OS 캡처 증거를 별도로 구분한다.

- 최종 공통 프레임/제어/크기/편집·피드백 수명 묶음: 80 passed, 18 subtests passed, 정상 종료. [결과](../../artifacts/native-windows-ui-20261105/final-dialog-manual-drag-resize.exit.json).
- 브랜드·알림·외관·월간/주간 묶음: 256 passed, 31 subtests passed, 정상 종료.
- 캘린더 관리 제목 중복 및 서비스 흐름: 39 passed, 정상 종료.
- 태스크 생성/수정/이동/복사·calendar_id·날짜/시간: 40 passed, 15 subtests passed, 정상 종료. 피드백 수명 회귀 3 passed, 2 subtests passed.
- 정적 브랜드 파생 리소스 114개(111 PNG, 2 ICO, 1 ICNS)의 크기·알파·원본 픽셀 대조 실패 0. [자산 감사](../../artifacts/native-windows-ui-20261105/brand-source-export-audit-final.json). 기존 Python 3.13/Pillow 13 환경에서 생성기 회귀 5개 통과.
- 인코딩 정책·컴파일 가드와 관련 파일 Ruff/diff 검사를 수행한다.

공통 프레임 도입 중 창을 반복해 닫는 검사에서 Qt fatal 종료를 실제 재현했다. Python GC가 필터의 속성을 정리한 뒤 들어온 Qt 이벤트가 원인이었다. 약한 창 참조, 종료·삭제·속성 소실 가드로 수정했고 정상 프로세스 종료를 재검증했다. 강제 성공 종료를 사용하지 않았다. [실패와 원인 증거](../../artifacts/native-windows-ui-20261105/chrome-gc-failure-evidence.md)를 보존한다.

추가 묶음에서는 이전에 닫힌 일정 창의 지연 피드백 callback이 삭제된 QLabel을 호출해 `0xC0000409`로 종료했다. label 소유 QTimer로 수명을 연결하고 새 메시지마다 만료 시간을 재설정했다. 계측으로 예외를 삼킨 실행 대신 원래 runner의 정상 종료와 XML로 검증했다. [재현·원인·수정 후 결과](../../artifacts/native-windows-ui-20261105/task-flow-diagnostic/findings.md).

## 적용 경계

이는 개발 소스와 격리 Windows 실행 검증이다. GitHub/Store 배포, 설치본 업데이트, 사용자 실계정 Google 동기화 재인증 성공으로 확대해 해석하지 않는다. 실행 중인 기존 사용자 앱은 강제로 재시작하지 않았으며 변경 화면은 소스를 다시 실행할 때 적용된다. 제품 버전은 4.9.2다. 독립 변경 기록 ID는 `windows-modal-brand-system-20261105`이며 배포용 제품 버전 증가는 포함하지 않는다.
