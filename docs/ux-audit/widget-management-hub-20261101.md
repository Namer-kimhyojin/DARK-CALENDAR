# 위젯 통합 관리 UI·UX 개선

2026-11-01 · Air Calendar 개발 소스 · 제품 버전 4.8.0 유지

## 벤치마킹과 적용 판단

공식 제품 문서를 비교하고 기존 관리창을 임시 설정·예시 위젯으로 직접 렌더링했다. 다른 제품의 바이너리를 설치하거나 스킨을 복제하지 않았다.

| 비교 대상·근거 | 발굴한 요소 | 이번 적용 |
|---|---|---|
| [Windows Widgets](https://learn.microsoft.com/en-us/windows/apps/design/widgets/)의 위젯 보드·선택기·목적 중심 동작 | 추가할 종류를 먼저 탐색하고 자주 쓰는 동작으로 바로 이동 | 8종 선택 갤러리, 종류별 용도 설명, 위젯별 꾸미기 바로가기 |
| [Rainmeter Manage](https://docs.rainmeter.net/manual/user-interface/manage/)의 Skins·Layouts 탭, 활성 목록, Load/Unload·설정 | 독립 위젯의 표시 관리와 전체 작업 공간 관리 구분 | 바탕화면 위젯·위젯 전용 모드 두 탭, 표시 상태·배치 잠금 안내, 표시/숨김 필터 |
| [PowerToys Workspaces](https://learn.microsoft.com/en-us/windows/powertoys/workspaces)의 편집·실행 진입점과 실행 상태 안내 | 구성 편집과 실행을 별도 동작으로 드러내고 현재 상태 표시 | 전용 모드 실행 전 꾸미기, 실행 중·트레이 숨김·메인 화면 상태, 다시 보기·메인 복귀 |

검색·행 재사용·알림 병합은 현행 코드에서 확인한 목록 재생성 문제에 대한 자체 개선이다. 외부 제품의 성능과 비교한 수치는 아니다.

## 기존 화면에서 확인한 문제

- 종류 선택·이름 입력이 항상 상단을 차지하고 종류별 용도를 미리 알기 어려웠다.
- 위젯마다 내부 ID와 작은 아이콘 5개가 표시되어 설정·찾기·복제·삭제를 구분하려면 도움말에 의존했다.
- 이름이나 표시 상태가 바뀔 때 목록 전체를 삭제·재생성했다. 전체 표시/숨김에서는 각 인스턴스 알림마다 이 경로가 반복됐다.
- 위젯 전용 모드의 실행·꾸미기·복귀가 독립 위젯 관리와 떨어져 있었다.

## 적용한 흐름

### 바탕화면 위젯

1. 기존 **위젯 관리자**를 열고 **바탕화면 위젯** 탭을 선택한다.
2. **위젯 추가**를 누른다. 8종 카드에서 종류를 고르고 이름을 입력한 뒤 **위젯 추가**로 확정한다. 이름은 비워도 된다. 취소하면 인스턴스를 생성하지 않는다.
3. 이름·위젯 종류로 검색하고 **전체 상태 / 표시 중 / 숨김**을 조합해 찾는다. 검색 조건은 설정에 저장하지 않는다.
4. 각 행에서 **표시 중 / 숨김**으로 전환하고, **찾기**로 관리창이 있는 화면 중앙에 가져온다. **꾸미기**는 기존 디자인 컬렉션을 연다.
5. **더보기**에서 설정·위치/크기 잠금·위치 초기화·복제·삭제를 실행한다. 삭제와 전체 삭제는 기존 확인 절차를 거친다.

이름은 행 안에서 편집하며 Enter 또는 편집 종료 시 저장된다. 빈 이름은 이전 이름으로 복원한다. 동일한 이름으로 편집을 끝내면 다시 저장하지 않는다. 종류·표시 상태·잠금 상태는 이름 아래에 표시하며 내부 ID는 도움말로 남긴다.

**전체 표시 / 전체 숨김 / 전체 삭제**는 현재 검색 결과와 관계없이 전체 독립 위젯에 적용된다. 버튼 이름의 ‘전체’로 범위를 표시한다. 전체 삭제는 상단 **더보기** 안에 배치했다.

### 위젯 전용 모드

- **위젯 전용 모드** 탭에서 현재 화면 형태·스킨과 제공 목록 수를 확인한다. 기존 11종 기본 형태·16종 스킨·저장한 자유 구성을 사용한다.
- **화면·스킨 꾸미기**는 기존 미리보기·초안·적용/취소 다이얼로그를 연다. **자유 구성 편집**도 기존 편집기를 사용한다.
- 모드가 닫혀 있으면 편집용 창만 숨김 상태로 준비한다. 편집기를 여는 동작만으로 모드를 실행하거나 다음 실행 시 복원 설정을 변경하지 않는다.
- **위젯 전용 모드 열기**는 기존 coordinator를 통해 실행한다. 실행 중이거나 트레이에 숨겨진 경우에는 **다시 보기**를 제공한다.
- **메인 화면으로 돌아가기**는 기존 복귀 경로를 따른다. 트레이 숨김 상태에서도 사용할 수 있다.
- 전용 모드의 **더보기** 메뉴 첫 항목에 **위젯 관리자**를 추가했다. 기존 하위 메뉴도 유지한다.

## 갱신·테마·설정 계약

- 인스턴스 ID별 행을 재사용하고 없어진 행만 제거한다. 편집 중인 이름과 검색·스크롤 상태를 보존한다.
- manager 알림은 단발 QTimer로 같은 이벤트 루프 안에서 병합한다. 회귀 테스트에서 연속 알림 30회를 목록 갱신 1회로 처리하는지 확인한다.
- 숨김·Esc·닫기에서 대기 갱신과 listener를 해제하며, 다시 표시할 때 한 번만 연결한다.
- 기존 QSettings prefix·삭제 확인·그래픽 컬렉션·배치 잠금·mode coordinator를 사용한다. 새 사용자 DB 구조나 별도 영구 저장 포맷은 추가하지 않았다.
- 스타일은 기존 의미 기반 테마 토큰을 사용한다. 추가 갤러리는 관리창의 토큰을 공유하고 스크롤 배경·맞춤 체크박스의 밝은 테마 가독성을 명시한다.
- `widget_hub` 신규 키 50개: 한국어·영어 제공, 나머지 17개 번들 언어는 영어 fallback을 넣었다.

## 검증 결과

- 관련 테스트 **39개 파일, 716건 통과**. 신규 관리창 회귀 17건과 기존 독립 위젯·디자인·전용 모드·자유 구성·프리셋·테마·i18n·인코딩을 포함한다.
- 최초 실행에서 `test_dialog_editor_widgets.py`의 29건은 통과했지만 임시 디렉터리 삭제 시 SQLite 연결이 남아 프로세스가 종료 코드 1을 반환했다. 검증 harness에서 해당 sandbox 연결과 로그를 닫은 뒤 같은 29건을 재실행해 종료 코드 0을 확인했다. 제품 DB 코드는 변경하지 않았다.
- 원본·재실행 로그와 JUnit을 보존한 [최종 결과](../../artifacts/widget-management-20261101/final-results.json), [통합 JUnit](../../artifacts/widget-management-20261101/final-combined.xml).
- Windows 실제 Qt 렌더링: 100%·200% 배율, 최소 폭 760, 검색 결과, 모드 실행/복귀, 추가 갤러리, 밝은/어두운 테마를 확인했다. 배율 200%에서 항목이 많으면 스크롤로 접근한다.
- `scripts/run_encoding_guard.py`, 범위 내 Ruff, `git diff --check` 통과. 실제 사용자 QSettings의 전후 값 일치 확인.

화면 검증 재실행:

```powershell
.venv/Scripts/python.exe scripts/validate_widget_management.py --phase after
.venv/Scripts/python.exe scripts/validate_widget_management.py --phase after --theme light --suffix light
$env:QT_SCALE_FACTOR = '2'
.venv/Scripts/python.exe scripts/validate_widget_management.py --phase after --suffix dpi-200
```

| 화면 | 근거 |
|---|---|
| 개선 전 | [기존 관리창](../../artifacts/widget-management-20261101/before/manager.png) |
| 개선 후 | [통합 관리창](../../artifacts/widget-management-20261101/after/manager.png), [검색](../../artifacts/widget-management-20261101/after/search.png) |
| 추가 | [8종 갤러리](../../artifacts/widget-management-20261101/after/add-gallery.png) |
| 전용 모드 관리 | [현재 구성](../../artifacts/widget-management-20261101/after/workspace.png), [실행 중](../../artifacts/widget-management-20261101/after/workspace-active.png) |
| 화면 조건 | [최소 폭](../../artifacts/widget-management-20261101/after/manager-narrow.png), [밝은 테마](../../artifacts/widget-management-20261101/after/light/manager.png), [200% 갤러리](../../artifacts/widget-management-20261101/after/dpi-200/add-gallery.png) |

화면은 임시 설정·예시 위젯으로 만든 소스 실행 결과다. 설치판·Store 패키지 교체와 실제 사용자 환경 인수는 이번 작업에 포함하지 않았다.
