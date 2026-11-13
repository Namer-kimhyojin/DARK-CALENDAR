# Air Calendar UI·UX 및 개발환경 개선계획

작성일: 2026-11-04. 상태: 검토안, 구현 전.

## 판단

현재 구조는 최신 기술을 단계적으로 도입할 수 있다. Python/PyQt6 기반을 교체할 필요성은 이번 점검에서 확인되지 않았다. 다만 개발·CI·배포 환경의 일치, Windows 화면 회귀 검사, 성능 기준을 보강해야 도입 효과를 판단할 수 있다. 최적화 완료라고 판단할 측정 근거는 아직 없다.

이번 점검은 현재 소스·설정·설치 패키지 메타데이터와 공식 기술 문서를 근거로 한다. 실행 중인 Air Calendar 창이 없어 실제 화면 캡처·사용 흐름 감사는 수행하지 않았다. 화면 잘림과 조작성은 재현 후보이며, 설치판의 오류로 단정하지 않는다. 전체 테스트·빌드·설치·계정 동기화도 실행하지 않았다. 기존 dirty 파일과 사용자 DB·설정은 수정하지 않았다.

## 1. 현재 개발환경

| 항목 | 직접 확인 결과 | 판단 |
|---|---|---|
| 로컬 Python | `.venv` Python 3.13.15, Windows x64 | 배포 workflow의 3.13.15와 일치 |
| UI 런타임 | PyQt 6.10.2, 실행 중 Qt 라이브러리 `qVersion()` 6.10.2, SIP 13.12.0 | `QT_VERSION_STR` 6.10.0은 바인딩 빌드 시점 값이므로 실행 DLL 불일치로 오판하지 않음 |
| 의존성 | `pip check` 통과, 현재 플랫폼에 적용되는 runtime lock 항목의 설치 버전 불일치 없음 | 기본 일관성 양호. 보안 검사·동작 검증 통과를 뜻하지 않음 |
| 빌드 | PyInstaller 6.21.0, runtime/build lock 존재 | 버전 고정은 이미 구현됨. 새로 만들 과제가 아님 |
| SQLite | 개발 실행과 배포가 전용 검증 런타임 준비 경로 사용, lock은 SQLite 3.54.1/Python 3.13.15 지정 | Python 교체 시 이 계약도 함께 변경·검증해야 함. 이번에 실제 DLL 기동 검사하지 않음 |
| 품질 도구 | Ruff 0.16.9, mypy 2.3.1, pre-commit hook 설치 확인 | 도구는 있으나 CI 연결과 버전 통일 개선 필요 |
| 배포 검증 | Windows 빌드·네이티브 GUI 검증 workflow 존재, ARM64는 별도 native runner 선택 | 현재 workflow 실행 성공 여부는 재조회하지 않음 |
| 변경 이력 | 읽기 전용 `scan --strict` 통과, 제품 버전 4.9.2 | 기존 수정분을 새 작업으로 흡수하지 않음 |

근거: `pyproject.toml`, `requirements*.txt`, `requirements-runtime.lock`, `requirements-build.lock`, `.pre-commit-config.yaml`, `.github/workflows/`, `scripts/run_development.py`, `scripts/prepare_sqlite_build_runtime.py`, `scripts/sqlite-runtime-lock.json`.

## 2. 우선 해결할 개발환경 문제

| ID/우선순위 | 확인된 문제와 영향 | 개선안 | 완료 기준 |
|---|---|---|---|
| DEV-01 / P1 | `pyproject.toml`의 `setuptools.backends.legacy:build`가 로컬 setuptools 83.0.0에서 import 실패. 표준 패키징·editable 설치의 장애 요인 | 패키징을 사용할 경우 `setuptools.build_meta`로 정리하고 패키지 탐색·데이터 파일·의존성 선언 검토. 패키징하지 않을 경우 해당 지원 범위를 명시 | 격리 환경에서 선택한 설치 경로 검증. 현재 PyInstaller EXE 빌드가 실패한다는 의미는 아님 |
| DEV-02 / P1 | 일반 quality CI는 Ubuntu/Python 3.13/requirements.txt, 배포는 Windows/Python 3.13.15/build lock 사용 | 플랫폼별 잠금 입력으로 안정 검증 경로 통일. 별도 최신 의존성 호환성 CI는 탐색용으로 유지 | 동일 변경에 대한 안정 CI의 Python·의존성 버전이 재현됨. Windows 전용 marker를 Linux에 무조건 적용하지 않음 |
| DEV-03 / P1 | `run_quality_gate.py`는 컴파일·선별 테스트 중심이며 Ruff/mypy 호출 없음. hook Ruff 0.15.9와 로컬 0.16.9가 다름 | dev 도구 버전 고정, CI와 hook 통일. domain/application부터 타입 검사 적용 | 변경 범위 lint/format 검사 및 선정 모듈 타입 검사가 PR 필수 항목으로 실행됨 |
| DEV-04 / P1 | PR 기본 CI가 Linux offscreen이며 Windows GUI 검사는 배포 쪽에 집중 | PR에 Windows 핵심 GUI 검사 추가. 네트워크 없는 임시 프로필과 테스트 DB 사용 | 날짜 입력·창 복귀·저장 취소·주요 다이얼로그를 Windows에서 확인 |
| DEV-05 / P2 | 확인한 CI에 시작 시간·월 전환·입력 지연·유휴 CPU의 성능 예산 없음 | 대표 데이터셋과 같은 머신에서 기준선 수집, 초기에는 추세 기록 후 임계값 도입 | cold/warm 구분, 30회 이상 표본의 중앙값/p95 및 메모리·유휴 CPU 보고. 실제 수치는 측정 후 확정 |
| DEV-06 / P2 | 빌드 lock은 버전 고정 방식. 저장소에 대량 untracked artifacts가 있어 탐색 시 배포 복사본까지 검색됨 | 의존성 hash 검증 도입 검토, 작업 검색은 소스 경로로 제한. 생성물 보관·검색 제외 규칙을 문서화 | 과거 배포 증거를 보존하면서 소스 검색·신규 환경 설치가 반복 가능 |

`project.dependencies=[]`는 requirements.txt를 별도로 설치하는 현재 운영에서는 의도된 설정이다. 다만 `pip install .`만으로 실행 환경이 완성된다고 안내해서는 안 된다. uv 프로젝트 방식으로 전환한다면 의존성 원본을 먼저 통합해야 한다.

## 3. UI·UX 오류 및 개선 우선순위

| ID/우선순위 | 근거·상태 | 개선안 | 검증 기준 |
|---|---|---|---|
| UX-01 / P1 | 코드상 동작 불일치: `keyboard_shortcuts.py`의 이전/다음 모니터 단축키가 모두 `move_to_next_monitor`에 연결됨. `window_events.py:487` 구현은 항상 인덱스 +1 | 이전/다음 순환을 분리하고 도움말 표현과 일치시킴. 물리적 좌/우 이동으로 바꾸려면 화면 좌표 기준 정책을 별도 결정 | 가상 화면 3개 이상에서 이전과 다음 목적지가 다름. 1개/2개/음수 좌표/혼합 배율에서도 창이 화면 안에 유지됨 |
| UX-02 / P1 | 잘림 위험: `task_dialog_unified.py:920` 반복 주기 86px, 방식 116px, 컨테이너 최대 210px·고정 높이 38px | 번역 텍스트 실측 폭 적용, 좁은 창에서는 다음 행 배치. 현재 반복값과 저장 의미 유지 | 한국어·영어·긴 번역/RTL 표본, 100/150/200%에서 선택값·푸터 접근 가능 |
| UX-03 / P2 | 조작성 후보: `top_bar_builder.py:178` 동기화 버튼 30×30, 잠금·자석·위젯 버튼 최대 36×36 | 아이콘 크기는 유지하면서 클릭 영역 36~40px 시안 비교. 전체 상단바 폭과 함께 조정 | 클릭 영역 중첩 없음, 작은 창에서도 검색·날짜 이동 접근 가능, Tab 포커스 확인 |
| UX-04 / P1 검증 | 일정 작성·이동·복사·수정은 고위험 흐름. 현재 오류를 재현한 것은 아님 | 기존 빠른 날짜/정확한 분 입력을 유지하고 오류 발생 지점에서 수정 방법과 포커스 제공 여부 확인 | 23:50→다음 날 00:10, 종일 여러 날, 종료<시작, 읽기 전용 대상, `calendar_id` 유지 및 취소 시 무변경 |
| UX-05 / P1 검증 | 동기화 허브와 상태 표시 구현 존재. 현재 관련 파일에 기존 수정분이 있음 | 연결/가져오기/표시/자동갱신의 차이를 사용자가 이해하는지 상태별 확인. 실패는 원인·재시도 경로·마지막 성공 시각으로 설명 | 로컬 모드·오프라인·인증 만료·부분 실패에서 다음 행동을 찾을 수 있고 기존 일정 보존 |
| UX-06 / P2 검증 | 월간 렌더러에 숨겨진 일정의 더보기와 일간 이동 이미 존재 | 밀집 일정·장문 제목·다일 일정에서 표시 누락과 숨김의 구분, 키보드로 더보기 접근 확인 | 0/5/20건 날짜 및 다일 일정에서 사용자가 전체 항목으로 이동 가능 |
| UX-07 / P2 검증 | 위젯 통합관리·작업공간·초안 취소는 최근 구현 영역 | 추가→꾸미기→적용→되돌리기→메인 복귀를 하나의 인수 시나리오로 검증 | 메모·스톱워치·KeyDeck 동작 보존, 취소 후 설정 불변, 재시작 후 배치 복구 |

제외한 오진: 도움말 `label_ko` 필드는 이름과 달리 `get_shortcut_guide_entries()`에서 `t()`로 번역된다. 한국어 고정 오류로 등록하지 않는다. 공통 화면 맞춤·접근성 이름·빠른 날짜 입력·월간 더보기·위젯 관리도 기존 기능을 확인한 뒤 개선한다.

실제 화면 검증 순서: ① 앱 기동/메인 → ② 일정 작성/오류 입력/취소 → ③ 수정·이동·복사 → ④ 동기화 상태 → ⑤ 위젯 관리/복귀 → ⑥ 종료·재시작. 현재 여섯 단계 모두 시각적 판정은 미실시이며, 단계별 전후 캡처와 재현 조건을 후속 구현 작업에 붙인다.

## 4. 최신 기술 도입 가능성

2026-11-04 공식 자료 조회 기준. 최신 버전의 존재와 이 프로젝트에서의 호환성 검증은 별개다.

| 기술 | 반영 가능성 및 실제 기대효과 | 진입 조건·권고 |
|---|---|---|
| uv | 기존 requirements/lock을 유지한 설치·동기화 실험 가능. 환경 준비 시간 단축 가능성 | 먼저 별도 venv에서 `uv pip` 경로 비교. dev lock 정리 후 측정. `dependencies=[]`인 상태에서 `uv sync`를 바로 대체 명령으로 쓰지 않음 |
| Python 3.15 계열 | 공식 3.15.2 존재. lazy imports 등 신규 기능 검토 가능 | 현재 private SQLite 준비 코드가 Python 3.13.15를 강제함. Python만 교체하면 실패. 바이너리 wheel·SIP·SQLite·PyInstaller·MSIX를 한 후보 환경으로 검증 |
| Python 유지보수 갱신 | 현재 3.13.15보다 최신 3.13.18 보안 릴리스 존재 | 공식 3.13.18은 소스 전용으로 안내됨. 설치 명령 한 줄로 교체 가능하다고 가정하지 않음. 신뢰 가능한 빌드 확보와 지원 중인 새 계열 전환 비용 비교 |
| PyQt/Qt 6.12 | 2026-10-28 PyQt 6.12.0 발표, QRhi 등 렌더링 관련 클래스 지원 | 현재 QWidget 화면을 유지한 별도 호환성 후보로 시작. SIP 수명주기·종료·DPI·투명창·IME·트레이·윈도우 포커스 통과가 선행 |
| Qt Quick/QML | 시각 효과가 중요한 독립 위젯/미리보기에서 시범 도입 가능 | QQuickWidget 혼합은 추가 렌더링 비용과 threaded render loop 제약이 있으므로 한 화면만 비교. DB/설정/입력 계약은 기존 Python 계층 사용 |
| 점진적 타입 검사 | 현재 mypy 설정·도구를 활용해 바로 강화 가능 | 새 검사기 추가보다 domain/application 공개 인터페이스부터 검사 수준 강화. 동적 Qt mixin 전체를 한 번에 강제하지 않음 |
| AI 일정 입력·요약 | application 유스케이스 경계로 초안 생성 기능을 분리할 구조적 여지가 있음 | 별도 서비스/비용/개인정보 요구를 정의한 뒤 검토. 취소·시간초과·출력 검증과 저장 전 사용자 검토를 거치게 함. 이번에 SDK 호환성은 검사하지 않음 |

PyInstaller 6.21.0 자체는 공식 changelog상 Python 3.15 지원을 포함한다. 따라서 단순히 패키저가 구버전이라 불가능한 상태는 아니다. 다만 전체 앱과 네이티브 의존성의 호환성을 보장하지 않는다.

전면 웹/Electron/Tauri 전환이나 free-threaded/JIT 적용은 이번 우선과제로 권하지 않는다. 현재 드러난 오류는 이벤트 연결·레이아웃·검증 환경에서 해결 가능하고, 새 기술의 이득을 입증할 성능 기준선이 먼저 필요하다.

## 5. 실행 순서와 산출물

1. 환경 기준 정리: DEV-01~03. 설치 방법·지원 Python 범위·도구 버전·플랫폼별 lock/CI를 정리하고 깨끗한 체크아웃에서 검증한다.
2. UI 위험 확인 및 소규모 수정: UX-01~03을 먼저 재현·수정하고 UX-04~07을 화면 인수 시나리오로 실행한다. 실사용 DB·QSettings·공유 DB·캐시·계정 연결은 격리한다.
3. 검증 자동화: Windows PR 검사와 배율·테마·언어 대표 조합의 화면 캡처, 시작/입력/월 전환 성능 기록을 추가한다. 전체 조합은 야간/배포 검사로 분리한다.
4. 기술 후보 비교: 기존 환경을 기준으로 uv 설치 경로 → Python 후보 → Qt 후보를 각각 비교한다. 한 번에 모두 올리지 않는다.
5. 도입 결정: 기능 회귀 0건, 반복 기동/종료 정상, 기존 데이터·설정 보존, 성능이 측정 오차 이상 악화되지 않는 후보만 배포 검토한다. 이 단계에서 배포 범위와 제품 버전을 결정한다.

첫 구현 묶음 제안: 패키징 설정 정리 + CI 의존성/도구 통일 + 이전 모니터 동작 수정 + 반복 설정 반응형 처리. UI 프레임워크 업그레이드는 별도 후보로 유지한다.

예상 기간은 현재 성능 기준선·Windows CI 실행 시간·후보 wheel 확보 여부가 없어 확정하지 않는다. 각 단계 완료 조건으로 진행 여부를 판단한다.

## 6. 검증 및 공식 근거

이번 실행: `.venv` 버전 조회, Qt 실행 버전 조회, 설치된 runtime lock 항목 대조, `pip check`, 잘못된 backend import 재현, pre-commit hook 존재/연결 확인, 읽기 전용 버전 scan. 앱 테스트·build·dependency upgrade는 하지 않음.

- [Python 3.15.2](https://www.python.org/downloads/release/python-3152/)
- [Python 3.15 기능](https://www.python.org/downloads/release/python-3150/)
- [Python 3.13.18 및 배포 형태](https://www.python.org/downloads/release/python-31318/)
- [PyQt 6.12 발표](https://riverbankcomputing.com/news/PyQt_v6.12.0_Released)
- [PyInstaller 변경 이력](https://pyinstaller.org/en/stable/CHANGES.html)
- [uv lock 및 환경 동기화](https://docs.astral.sh/uv/pip/compile/)
- [setuptools 표준 backend](https://setuptools.pypa.io/en/latest/build_meta.html)
- [QQuickWidget 성능·통합 제약](https://doc.qt.io/qt-6.11/qquickwidget.html)
