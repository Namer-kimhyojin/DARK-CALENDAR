# 캘린더 관리 버튼 동작 수정 — 2026-10-07

## 원인과 수정

캘린더 관리 화면의 버튼에서 실제 Qt 클릭 신호를 보내면 로컬 추가·ICS 추가·이름 변경·색상 변경·기본 저장 대상·구독 수정·제거가 실행 전에 `TypeError`로 중단됐다.
`clicked(bool)`의 체크 상태가 `guard_calendar_action`의 가변 인자 래퍼를 통해 인자를 받지 않는 원래 메서드까지 전달되는 것이 원인이다.
예를 들어 로컬 추가 버튼은 `_add_local() takes 1 positional argument but 2 were given`을 발생시켰다.
이전의 핸들러 직접 호출 검사는 이 Qt 신호 경계를 지나지 않아 오류를 발견하지 못했다.

`CalendarManagerPage._button()`에서 클릭 상태를 명시적으로 제거한 뒤 콜백을 실행하도록 수정했다.
실제 체크 상태가 필요한 표시 여부·구독 갱신 체크박스의 `toggled(bool)` 연결은 유지한다.
같은 오류 보호 래퍼를 사용하는 Outlook·CalDAV의 버튼은 이미 명시적 신호 어댑터를 사용하고 있었다.
Google 설정·전체 허브의 동기화·닫기 연결도 함께 확인했다.

읽기 전용 캘린더의 기본 저장 대상, 현재 기본 대상의 재선택, 갱신 중 구독 수정 등 기존 제한은 유지한다.
Google 캘린더의 이름 변경은 기존 설계대로 Google Calendar에서 변경하도록 버튼을 비활성화하고 안내한다.

## 검증 근거

- 수정 전 실제 마우스 회귀 검사 12개 중 11개에서 같은 인자 오류를 재현했다. 표시 여부 체크박스는 정상 동작했다.
- 수정 후 로컬·Google·ICS의 활성 버튼을 실제 Qt 마우스 신호로 실행해 콜백·전달 값·성공 반영을 확인한다.
- 이름·색상·기본 저장 대상·표시 여부는 임시 SQLite DB에 실제로 저장한 뒤 목록과 상세 화면에 반영되는지 확인한다.
- 실제 Windows Qt에서 밝은·어두운 테마별로 로컬 추가·이름 변경·색상 변경·ICS 추가·수정 폼을 열고 실제 취소 버튼으로 닫았다. 총 10개 폼의 표시·모달 활성화·허브 복귀가 정상이다. 허브 닫기도 양쪽 테마에서 정상이다.
- 위 실제 폼 검사에서 처리되지 않은 예외 0건, 네트워크 호출 0건이며 임시 DB 및 원본 사용자 설정은 변경되지 않았다.
- 전역 이벤트 필터·잠금 오버레이·다이얼로그 진입 가드는 이 화면의 클릭을 차단하지 않았다. 허브 → Google 설정 호출 경로 → 허브 복귀도 별도로 확인했다.

실제 클릭 회귀 12개를 포함한 관련 검사 **74개가 통과**했다. 실패·오류·건너뜀은 0건이다.
대상은 `test_calendar_sync_redesign.py`, `test_calendar_sync_coordinator.py`,
`test_common_sync_error_audit.py`, `test_gcal_calendar_visibility_ui.py`이다.
compileall·인코딩 정책/유틸 검사 12개·수정 범위 Ruff·diff 검사를 통과했다.
인코딩 가드는 샌드박스 기본 임시 디렉터리 생성 제한 때문에 최초 실행에서 환경 오류가 났고,
프로젝트 내부 `--basetemp`로 재실행하여 전체 통과했다.

보고서와 화면:

- [수정 전 오류 재현](../../artifacts/calendar-manager-clicks-20261007/before.xml)
- [수정 후 회귀 검사](../../artifacts/calendar-manager-clicks-20261007/after.xml)
- [실제 폼 검사](../../artifacts/calendar-click-audit-20261007/real-forms/observations.json)
- [어두운 캘린더 관리 화면](../../artifacts/calendar-click-audit-20261007/real-forms/dark-calendar-manager.png)
- [밝은 ICS 추가 창](../../artifacts/calendar-click-audit-20261007/real-forms/light-add-ics.png)
- [모달 복귀 검사](../../artifacts/calendar-click-audit-20261007/modal-observations.json)

## 적용 단계

현재 개발 소스에 반영했다. 사용자 DB·인증 파일을 변경하거나 사용 중인 앱을 종료하지 않았다.
실제 계정 동기화·Store 패키지 반영 및 설치 업데이트는 이번 버튼 검사와 별도 단계다.
