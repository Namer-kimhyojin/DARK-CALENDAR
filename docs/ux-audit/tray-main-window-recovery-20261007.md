# 트레이에서 메인 창이 활성화되지 않는 문제 복구

확인일: 2026-10-07. 주간 시간표 작업 이후 프로그램이 트레이에만 표시되고 메인 창을 활성화할 수 없다는 사용자 제보를 확인했다.

## 실제 실행 상태와 복구

- 09:29 사용자 재실행 이후 `run.bat`로 시작한 개발 소스 프로세스의 Air Calendar 창을 Windows API로 확인했다. 창은 표시 상태였고 최소화 상태가 아니었지만 전경 창은 아니었다. 창 좌표는 `[1920, 0, 3840, 1032]`였다.
- 09:30 해당 Air Calendar 창에만 `ShowWindow`, `BringWindowToTop`, `SetForegroundWindow`를 적용한 뒤 전경 창이 된 것을 확인했다. 사용자 DB나 설정을 변경하지 않고 실행 중인 창을 활성화했다.
- 현재 로그에서 Python 시작 예외는 확인되지 않았다. 작업 중단이 최초 증상을 일으켰다는 인과관계는 확인되지 않았다. 실행 중인 프로세스와 창이 있었으므로 이번 현장 확인에서는 창 표시·활성화 경로를 우선 복구했다.

## 수정한 동작

- Qt에서는 최소화된 창도 `isVisible()`이 `True`일 수 있다. 기존 트레이 클릭·메뉴 전환은 이 창을 다시 숨겼다. 최소화 상태를 함께 확인하여 `showNormal()`으로 복원하도록 수정했다.
- 트레이의 일반 단일 클릭은 기존 표시·숨김 전환을 유지한다. 더블 클릭은 항상 표시하며, `Trigger`와 `DoubleClick` 이벤트가 연속으로 와도 다시 숨겨지지 않는다.
- [Qt 6.10.2의 Windows 트레이 구현](https://raw.githubusercontent.com/qt/qtbase/v6.10.2/src/plugins/platforms/windows/qwindowssystemtrayicon.cpp)에서도 더블 클릭 뒤의 마우스 해제 이벤트를 무시하는 처리를 확인했다. 회귀 테스트는 `Trigger → DoubleClick` 순서의 최종 표시 상태를 검증한다.
- 공통 표시 경로는 창을 올리고 활성화를 요청한다. 트레이 메뉴·단축키도 같은 표시 경로를 사용한다.
- 활성 위젯 모드에서 메인 화면으로 돌아갈 때 공개 `return_to_main()` 경로를 사용한다. 이전 숨김·최소화 상태에 머무르는 대신 메인 창을 표시한다.
- 트레이의 창 위치 복원은 안전한 화면 영역으로 위치를 조정한 뒤 창을 표시·활성화한다.
- 별도 시작 검증에서 발견한 잠재 오류도 수정했다. 시작 시간이 `None`인 종일 일정은 왼쪽 패널에서 `target_date`를 사용한다. 실제 사용자 DB의 읽기 전용 조사에서는 `NULL` 시작 시간 일정이 0개였으므로, 이 오류를 사용자가 겪은 증상의 원인으로 단정하지 않는다.
- 자동 실행과 저장된 위젯 모드의 시작 동작을 불필요하게 바꾸지 않도록 bootstrap의 일반 `window.show()` 경로와 전역 창 플래그는 유지했다.

주요 수정 파일은 `calendar_app/infrastructure/runtime/infra_wiring.py`, `calendar_app/presentation/main_window/window_shell_actions.py`, `calendar_app/presentation/main_window/window_events.py`, `calendar_app/presentation/panels/side_panel_renderer.py`다.

## 검증

- 트레이 복원 회귀 테스트 8개를 추가했다. 실제 Qt 창의 최소화 복원, 메뉴 복원·활성화, 단일 클릭 전환, `Trigger → DoubleClick`, 위젯에서 메인 화면 복귀를 확인했다.
- 메인 창·위젯·안전 영역 복원 테스트 4개와 종일 일정 시작 표시 테스트 3개를 추가했다. 최종 회귀 검증은 11개 테스트 파일을 각각 독립 프로세스로 실행했으며 **80개 통과, 실패·오류·건너뜀 0개**였다.
- 앞선 동일 프로세스 일괄 실행은 56개 진행 표시 후 결과 요약 없이 종료 코드 1로 끝났다. assertion 실패 traceback은 없었으며, 일괄 실행의 비정상 종료 원인은 확인되지 않았다. 따라서 일괄 실행을 통과로 기록하지 않고, 11개 파일을 모두 독립 실행한 결과를 최종 검증 근거로 사용한다.
- 별도 INI 설정을 명시하고 설정 fallback을 차단한 전체 `OverlayApp` 시작 검증에서 월간 보기, 주간 시간표, 주간 날짜별 보기 모두 통과했다. 임시 SQLite DB를 사용했고 도크 표시, 최소화·더블 클릭 복원, 오류 목록을 확인했다.
- 실제 Windows Qt 플랫폼의 주간 시간표 시작 검증도 통과했다. 창 활성화 `active=true`, 오류 목록 `[]`를 확인했다. offscreen 검증은 `active=false`였으며, 실제 창 활성화 판정은 Windows 플랫폼 검증을 근거로 했다.
- 수정 Python 8개 파일의 Ruff lint·format 검사와 수정 범위의 diff 검사가 통과했다. `scripts/run_encoding_guard.py`도 종료 코드 0으로 통과했다. 기존 접근 불가 캐시 폴더 두 곳의 compileall 경고는 있었으며 최종 인코딩 검증은 통과했다.

전체 앱 시작 재현 스크립트: [full_startup_probe.py](../../artifacts/tray-recovery-20261007/full_startup_probe.py).

| 검증 환경 | 결과 파일 |
|---|---|
| 월간 / offscreen | [probe-result.json](../../artifacts/tray-recovery-20261007/monthly-offscreen/probe-result.json) |
| 주간 시간표 / offscreen | [probe-result.json](../../artifacts/tray-recovery-20261007/weekly_time-offscreen/probe-result.json) |
| 주간 날짜별 / offscreen | [probe-result.json](../../artifacts/tray-recovery-20261007/weekly_date-offscreen/probe-result.json) |
| 주간 시간표 / Windows | [probe-result.json](../../artifacts/tray-recovery-20261007/weekly_time-windows/probe-result.json) |

파일별 회귀 검증 XML은 `artifacts/tray-recovery-20261007/test_*.xml`에 있다. 합산 근거는 [test-summary.json](../../artifacts/tray-recovery-20261007/test-summary.json)에 저장했다.

## 사용자 데이터와 적용 범위

- 사용자 DB 조사는 읽기 전용으로 수행했다. 실제 실행 창 복구는 창 상태만 변경했다.
- 샌드박스 기본 레지스트리는 실제 사용자 HKCU와 분리된 가상 저장소였다. 샌드박스 밖의 실제 HKCU 조회에서 220개 설정 키를 확인했다. 전후 대조한 `screen_fill_active=true`와 기존 위젯 인스턴스 5개는 유지되었고 주간 보기의 새 레이아웃 키는 원래대로 없었다. 실제 사용자 설정을 초기화하거나 백업으로 덮어쓰는 복원 작업은 수행하지 않았다.
- 수정은 개발 소스에 적용했다. 이미 실행 중인 Python 프로세스가 수정된 모듈을 자동으로 다시 읽지는 않으므로 코드 수정의 적용과 실행 중인 창의 Windows 활성화 조치를 구분한다.
- 릴리스 패키지·Store 설치판은 변경하지 않았다. Store 배포나 설치판 검증은 이번 복구에 포함하지 않았다.
