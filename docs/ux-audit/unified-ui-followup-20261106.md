# 공통 UI 후속 개선·검증 기록

2026-11-06. 글자·크기, 모달 색상과 외곽, 중첩 모달, 시간 입력, 요일 표시, 위젯 테마를 같은 기준으로 정리한 기록이다. 아래의 완료 표시는 해당 소스·회귀·격리 실행에서 확인한 범위다. 설치판 업데이트나 배포 완료를 뜻하지 않는다.

공통 수치는 [글자·컨트롤·모달 크기 가이드](../design/typography-and-sizing.md)를 따른다. 이전 결과는 [2026-11-05 모달 시스템](native-windows-modal-system-20261105.md), [사용성 후속 점검](ui-usability-followup-20261105.md), [밝은 테마](light-mode-pearl-lilac-20261105.md)와 구분한다. 새 음악 기능은 [루프덱 안내](keydeck-loopdeck-20261106.md)에 별도로 기록한다.

## 적용한 동작과 디자인

| 항목 | 적용 내용 | 확인 경계 |
|---|---|---|
| 글자 계층 | 새 기본 11pt, 기존 사용자 글꼴·크기 보존. 본문·보조·섹션·제목·주요 날짜를 공통 역할로 계산하고 pt/논리 px를 구분한다. | 모달·메인·패널·시간표의 실제 QFont와 글자 높이 회귀, Windows 100%·125% 캡처 |
| 24pt 모양 설정 | 큰 글자에서는 미리보기를 기본 접어 설정 공간을 확보하고 다시 펼칠 수 있게 한다. 스크롤 본문과 하단 적용·취소는 분리한다. | 실제 24pt·125%의 초기/폰트/하단 상태 7개, footer 직접 시각 검토 |
| 모달 색상 | 선택 색상의 accent, 입력·목록·선택 상태와 불투명 reading surface를 공통 palette로 맞춘다. 사용자 원본 색상·투명도 설정은 보존한다. | 밝은/네이비 모달·서브 탭 캡처 및 theme 회귀 |
| 외곽 그림자 | 모달 내부만 찍은 이미지와 창 바깥 compositor 그림자를 포함한 이미지를 함께 보존한다. | 상태별 `*-shadow.png`, 원래 native bounds/DPI와 확장 crop 메타데이터 |
| 피드백 | 표준 알림 아이콘과 inline 안내가 현재 palette를 따른다. 표준 메시지는 숨김 상태에서 부모 창의 항상 위 정책을 계승한다. | 실제 light100/navy125 각 5상태에서 캡처 전후 Win32 내부 5점의 소유권·모달 표시·그림자를 확인 |
| 제목 입력 경고 | `TaskTitleEdit`의 QSS `max-height: 16777215px`를 제거한다. Qt가 padding·border를 더하면서 widget 최대 크기를 넘기던 원인을 없앤다. | 동일 경고 6건 재현→6건 통과, 생성·수정·이동·복사 및 calendar_id 회귀 포함 83건 통과 |
| 관리창 안의 편집창 | 업무 context·저장 callback·편집 잠금은 원래 앱에 두고, native transient owner를 현재 관리 모달에 연결한다. | Windows 100%·125%에서 Qt owner/GW_OWNER·중첩 event loop·복귀·잠금 해제·행 보존 10개씩 확인 |
| 시작·종료 시간 | 같은 높이·너비의 입력을 작은 간격으로 연결하고, 좁은 폭에서는 세로 범위로 전환한다. | 10/11/14/24pt geometry 회귀와 native 일정 편집 화면 |
| 요일 표시 | 옵션 클릭마다 **상단만 → 날짜 옆만 → 둘 다 → 숨김**. 월간·여러 주 grid·1주 시간표가 같은 설정을 사용한다. | 월간·1주 시간표의 각 4모드 native 캡처. 시간표는 숨김에서도 날짜 유지 |
| 위젯 테마 | 색상·투명도는 메인 테마에 연결하고, 스킨은 모양·장식을 바꾼다. 종일 일정의 `all_day` 값은 사용자에게 번역된 **종일**로 표시한다. | 실제 bootstrap→위젯 모드 진입→DPI 안정화→캡처→메인 복귀, light100/navy125 각각 확인 |

새 요일 설정은 `cal_weekday_display_mode=header|date|both|hidden`이다. 새 키가 없으면 기존 `cal_show_weekday`의 false를 상단만, true를 둘 다로 읽으며, 해당 키가 없는 오래된 설정에 한해 `cal_show_day_name`도 읽는다. 읽는 것만으로 기존 설정을 다시 쓰지 않는다. 전환은 한 번만 갱신하며, 새 상태는 앱 초기화와 렌더 캐시 서명에 포함한다.

요일 줄은 고정된 큰 여백 대신 선택 글꼴의 metrics와 작은 패딩으로 높이를 정한다. 1주 시간표의 날짜는 모든 모드에서 남기고, 요일만 위치를 바꾸거나 숨긴다. 서로 다른 배율을 글꼴에 수동으로 다시 곱하지 않는다.

## 채택한 실제 Windows 증거

상태 수는 캡처한 UI 상태의 수다. 그림자 파일은 같은 상태의 보조 캡처이므로 상태 수에 더하지 않는다. 아래 보고서에서 정상 완료·오류 0·임시 INI 쓰기 격리·native 설정 보존을 확인한 실행만 완료로 표시한다.

| 실행 | 상태 | 실제 DPI / 글자 | 결과와 증거 |
|---|---|---|---|
| 모달·서브 탭 light100 | 확인 완료 | 96 DPI / 11pt | 32상태, 각 client+shadow. [채택 보고서](../../artifacts/unified-ui-final-20261106/accepted-native-light-100-exec/subtab-audit.json) |
| 모달·서브 탭 navy125 | 확인 완료 | 120 DPI / 11pt | 31상태, 각 client+shadow. [채택 보고서](../../artifacts/unified-ui-final-20261106/accepted-native-navy-125/subtab-audit.json) |
| 큰 글자·모양 설정 | 확인 완료 | 120 DPI / 24pt | 7상태, 모양 설정 초기·폰트 하단 및 일정/일반업무. [보고서](../../artifacts/unified-ui-final-20261106/native-large-font-125-final/subtab-audit.json) |
| 중첩 모달 owner 100% | 확인 완료 | 96 DPI | 10개 check, 편집 후 관리창 복귀·편집 잠금 해제·기존 행 보존. [보고서](../../artifacts/modal-layering-20261106/native-100/probe.json) |
| 중첩 모달 owner 125% | 확인 완료 | 120 DPI | 같은 10개 check 확인. [보고서](../../artifacts/modal-layering-20261106/native-125/probe.json) |
| 메인 light100 | 확인 완료 | 96 DPI / 11pt | 전체/좁은 월간·주간 4상태+요일 8상태+위젯 1상태. [13상태 보고서](../../artifacts/unified-ui-final-20261106/native-main-light-100/main-captures.json). 종일 문구의 최신 재촬영은 아래 별도 실행을 따른다. |
| 메인 navy125 | 부분 확인 | 120 DPI / 11pt | 월간·주간·요일 12상태만 정상. 뒤의 위젯 mixed-DPI 배치 실패가 있어 전체 성공으로 채택하지 않는다. [실행 보고서](../../artifacts/unified-ui-final-20261106/native-main-navy-125-final/main-captures.json) |
| 위젯 light100 최신 | 확인 완료 | 96 DPI / 11pt | 위젯 상태 1개(`13-widget-workspace`)와 메인 복귀 정상. palette 상속·종일 문구 직접 확인. [보고서](../../artifacts/unified-ui-final-20261106/native-widget-light-100-final/main-captures.json) |
| 위젯 navy125 최신 | 확인 완료 | 120 DPI / 11pt | 같은 위젯 상태 1개와 메인 복귀 정상. [보고서](../../artifacts/unified-ui-final-20261106/native-widget-navy-125-final/main-captures.json) |
| 표준 메시지 표시 시점 비교 | 결함 재현 확인 | 실제 Windows / Win32 foreground gate | 자동 Show 스타일 경로 4종 실패, `exec()` 전 명시적 스타일 4종과 inline 1종 통과. [비교 보고서](../../artifacts/modal-palette-20261105/native-feedback-style-timing/feedback-probe.json). 수정 후 채택 증거는 아니다. |
| 피드백 light100 | 확인 완료 | 96 DPI / 11pt | 정보·경고·오류·질문·인라인 5상태, 오류 0·INI 격리·native 설정 보존. 재사용 ownerwatch 포함 [최종 보고서](../../artifacts/modal-palette-20261105/native-feedback-light-100-owner-watch-final/feedback-probe.json) |
| 피드백 navy125 | 확인 완료 | 120 DPI / 11pt | 같은 5상태, 오류 0·INI 격리·native 설정 보존. [최종 보고서](../../artifacts/modal-palette-20261105/native-feedback-navy-125-owner-watch-final/feedback-probe.json) |
| 루프덱 최종 배치 | 확인 완료 | 96 / 120 DPI · 11pt | light100 46개·navy125 47개 check, 각 5상태. 16패드와 4트랙 전체 및 고정 재생 상태를 직접 확인. 실제 오디오 백엔드 상태와 청취의 경계는 [루프덱 안내](keydeck-loopdeck-20261106.md)를 따른다. |

대표 화면은 [light 모양 설정](../../artifacts/unified-ui-final-20261106/accepted-native-light-100-exec/26-appearance-initial.png), [light 일정 편집](../../artifacts/unified-ui-final-20261106/accepted-native-light-100-exec/32-schedule-initial.png), [navy 일반업무](../../artifacts/unified-ui-final-20261106/accepted-native-navy-125/28-routine-tab-0.png), [위젯 light](../../artifacts/unified-ui-final-20261106/native-widget-light-100-final/13-widget-workspace.png), [위젯 navy](../../artifacts/unified-ui-final-20261106/native-widget-navy-125-final/13-widget-workspace.png)다.

OS 픽셀은 `native_observation.py`로 수집한다. 창 내부 캡처와 별개로, 외곽 캡처는 원래 Win32 client bounds에 실제 DPR 기준 여백을 더한 desktop compositor crop이다. 모니터 경계에서 제한된 crop 여부를 JSON에 남긴다. 원래 창의 bounds·투명성·DPI 관찰은 그대로 유지한다. QA용 불투명 backing과 foreground 조건이 포함되므로 사용자 바탕화면의 모든 가림·배경 조합을 검증한 것으로 확대하지 않는다.

## 자동 회귀와 정상 종료

| 묶음 | 확인 결과 | 근거 |
|---|---|---|
| 최종 공통 UI·루프덱 통합 | **322 passed, 69 subtests**, 정상 종료·INI 격리·native 설정 보존 | [최종 XML](../../artifacts/unified-ui-final-20261106/integrated-accepted-v2.xml), [감사](../../artifacts/unified-ui-final-20261106/integrated-accepted-v2.settings.json) |
| 공통 UI 통합 기준선 | 280 passed, 65 subtests, 정상 종료·INI 격리·native 설정 보존 | [통합 XML](../../artifacts/unified-ui-final-20261106/integrated-final.xml) — 루프덱 재배치 전 기준선 |
| 제목 입력 경고·태스크 흐름 | 83 passed, 정상 종료. 경고 재현 6건은 별도 6 passed | [통합](../../artifacts/typography-system-20261105/task-title-warning-final.xml), [동일 재현의 수정 후](../../artifacts/typography-system-20261105/task-title-warning-after-six.xml) |
| 시간 범위 geometry·일정 | 66 passed, 정상 종료 | [보고서](../../artifacts/typography-system-20261105/time-range-final.xml) |
| 요일·캘린더·글자·초기화·인코딩 | 181 passed, 정상 종료 | [보고서](../../artifacts/typography-system-20261105/weekday-display-accepted.xml) |
| 요일·번들 후속 확인 | 43 passed, 정상 종료·native 설정 보존 | [보고서](../../artifacts/typography-system-20261105/weekday-locale-accepted.xml) |
| 모달 피드백 실행·큰 글자 | root 확인 9 passed. 11/24pt 실제 `exec()` footer case 포함 | `tests/test_modal_validation_feedback.py` |
| 메시지 owner 재사용 | 86 passed, 11 subtests, 정상 종료. 같은 메시지를 두 번 실행하며 항상 위 해제·유지·원래 명시 정책 확인 | [XML](../../artifacts/modal-palette-20261105/message-owner-reuse-final.xml) |

묶음은 테스트가 겹치므로 합산하지 않는다. 테스트의 소스·임시 DB·INI 검증은 실제 Windows 화면·입력과 구분한다. `QSettings` 생성자를 mock하는 기존 fixture도 실제 타입 판정을 유지하도록 별도 Qt 타입 alias를 사용한다. 실제 런타임의 설정 생성 방식은 바꾸지 않는다.

## 제외·재현 이력

- `artifacts/unified-ui-final-20261106/native-light-100/`의 업무 관리 3상태는 `.show()` fixture에서 창이 숨겨져 캡처에 실패했다. 캡처 실패 JSON과 오류 3개를 남기고, 실제 `exec()` 경로의 `accepted-native-light-100-exec`만 최종 모달 증거로 채택했다.
- `native-main-navy-125-final`은 앞의 12개 메인/요일 캡처와 뒤의 위젯 실패를 분리한다. 이후 `native-widget-navy-125-final`에서 coordinator 진입 후 DPI·위치를 안정화한 위젯 실행을 별도로 채택했다.
- 피드백 light/navy 10컷은 다른 외부 창에 가려져 판정에서 제외했다. 같은 파일을 성공 증거로 재사용하지 않고 새 경로를 추가한다.
- Win32 내부 5점 소유권으로 표준 QMessageBox 4종이 자동 스타일 경로에서 항상 위 부모 창 뒤로 숨는 결함을 재현했다. `exec()` 전 명시적 스타일 적용과 비교하면 자동 4건 실패·명시적 4건 통과·inline 1건 통과였다. `Polish`로 전체 스타일 시점을 옮기는 실험만으로는 해결되지 않아 그 변경은 되돌렸다. 숨김 QMessageBox가 부모·조상 창의 명시적 항상 위 정책을 계승하도록 보완한 뒤 위 light100/navy125 실행에서 모두 확인했다. 다른 창에 입력 중일 수 있는 foreground HWND는 관찰값이고, 실제 내부 5점의 대상 창 소유권을 필수 조건으로 삼는다. 비교·실패 보고서는 `native-feedback-style-timing`, `native-feedback-light-100-polish-final`에 보존한다.
- 제목 입력 경고는 [수정 전 6건 실패](../../artifacts/typography-system-20261105/task-title-warning-before.xml)를 보존한다. `bootstrap.py`의 로그 위치는 Qt 경고를 받은 곳이며, 실제 원인은 제목 입력창 QSS의 content 최대 높이와 padding·border 합산이었다.
- 초기 locale canonical 실패와 부족한 `common.search`를 분리해 확인한 뒤, 공유 정렬 도구로 순서만 정리하고 필요한 키를 추가했다. [기존 키·값 보존](../../artifacts/typography-system-20261105/weekday-locale-format-preservation.json), [위젯 문구 추가의 값 보존](../../artifacts/typography-system-20261105/widget-inheritance-locale-preservation.json)을 남겼다. 한국어 외 신규 문구의 영어 fallback은 번역 완료로 계산하지 않는다.

첫 최종 통합 실행의 2건 실패는 [원본 XML](../../artifacts/unified-ui-final-20261106/integrated-accepted.xml)에 보존한다. 테마 적용 테스트가 남긴 QApplication 전역 QSS·font·palette를 복원하고, 진행 막대에는 전역 선택색보다 우선하는 로컬 accent 역할을 지정했다. 단독 루프덱 fixture에서 빠졌던 공통 제목 영역도 실제 bootstrap과 같이 설치했다. 설정 그룹 내부 여백을 줄여 제목이 있는 880×736에서도 16패드와 4트랙 전체를 확인한 뒤, 위 322개 통합 실행을 다시 검증했다.

최종 native 근거 12개와 설정 감사는 [채택 목록](../../artifacts/unified-ui-final-20261106/native-acceptance-summary.json)에 정리했다. 루프덱 최종 실행에는 메인 창의 실제 global/tooltip stylesheet builder도 적용했다. 관련 Python Ruff, 전체 encoding guard와 diff check가 통과했고, [i18n 감사](../../artifacts/unified-ui-final-20261106/i18n-accepted.json)는 source key 누락 0·오류 0이다.

## 후속 갱신 기준

재촬영 결과를 추가할 때는 새 경로, 실제 DPI·font_size, 캡처 상태 수, 정상 종료, 오류 배열, INI 쓰기 감사, native 설정 변화 여부를 먼저 확인한다. 그 뒤 직접 검토한 화면·입력 범위를 표에 적는다. 실패 fixture·가림·mixed-DPI 배치 실패는 삭제하거나 정상 결과에 합치지 않는다. 설치·배포·사람의 오디오 청취 확인은 해당 절차의 별도 근거가 생겼을 때만 추가한다.
