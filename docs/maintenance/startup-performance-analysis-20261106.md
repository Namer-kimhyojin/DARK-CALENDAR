# 메인 캘린더 첫 실행 지연 분석

2026-11-06 KST. 사용자가 확인한 대상은 비트메이커가 아니라 **앱 실행 → 메인 캘린더 표시**다. 제품 코드는 수정하지 않고 실행 경로, 기존 로그와 임시 환경의 실제 Windows 계측으로 분석했다.

주된 지연은 현재 PC에서 **Qt Windows 기본 글꼴 처리 경로의 최초 초기화**에 있다. 기본 경로의 최초 `QFontMetricsF.height()`는 23.893초였고 다음 호출은 0.015ms였다. GDI 임시 비교에서는 최초 호출이 0.527초였다. 전체 시작에서도 같은 방향의 차이를 확인했다. 특정 글꼴 손상, Windows 서비스 결함, 특정 Qt 버그까지 확정한 결과는 아니다.

## 실제 실행과 계측 조건

- 관찰된 사용자 실행은 설치판이 아니라 `run.bat → scripts/run_development.py → build/python-sqlite-x64/05254499f5a50d24148dcf54/python.exe → main.py`다. Python 3.14.10, SQLite 3.54.1인 정확한 fingerprint runtime으로 비교했다.
- 실제 기존 프로세스 생성 시각 기준 개발 launcher → main.py는 약 3.165초, batch → main.py는 약 3.566초다. 아래 앱 내부 측정과는 다른 실행의 값이므로 합산하여 전체 시간을 확정하지 않는다.
- Windows Qt, 기본 OS 배율, 임시 DB·INI, 계정·동기화·저장 위젯 없는 조건이다. 실제 앱을 종료·재시작하지 않았다. 독립 단일 인스턴스 잠금을 사용하고 네트워크·레지스트리 쓰기는 차단했다.
- 아래 기본/GDI 앱 비교는 각 1회다. OS 파일 캐시는 비우지 않았다. 시작 후 저장 위젯·실제 일정 데이터·원격 서비스 조건에 따른 차이는 별도다.
- `first-frame-eventloop-return`은 메인 창 첫 paint 뒤 이벤트 루프로 돌아온 시점이다. 모든 기능의 준비 완료나 원격 동기화 완료를 뜻하지 않는다. 계측 앱의 최종 종료 시간은 별도 이벤트이며 시작 시간에 포함하지 않았다.

## 확정된 측정

| 구간 | 기본 Windows 경로 | GDI 임시 비교 |
|---|---:|---:|
| 최초 15px·DemiBold·시스템 family의 `QFontMetricsF.height()` | 23,892.762ms | 527.146ms |
| 같은 프로세스 두 번째 height() | 0.0147ms | warm 호출은 각 JSON 참조 |
| 해당 최초 조회의 CPU 시간 | 1,656.250ms | 140.625ms |
| 해당 글꼴 height 결과 | 19.9375px | 19.9375px |
| 메인 첫 paint | 31.307초 | 4.166초 |
| 메인 첫 프레임 뒤 이벤트 루프 복귀 | 31.368초 | 4.297초 |
| QApplication 생성 | 77.409ms | 35.622ms |
| OverlayApp 생성 | 2.951초 | 2.608초 |

증거:

- [기본 글꼴 연산별 wall/CPU](../../artifacts/startup-performance-20261106/font-after-default-system/font-metric.json), [GDI 글꼴 연산별 wall/CPU](../../artifacts/startup-performance-20261106/font-after-gdi-system/font-metric.json)
- [기본 메인 시작](../../artifacts/startup-performance-20261106/bootstrap-private-system-fontdir/startup.json), [GDI 메인 시작](../../artifacts/startup-performance-20261106/bootstrap-private-gdi-comparison/startup.json)
- [QApplication 이전 fallback](../../artifacts/startup-performance-20261106/font-before-qapp/font-metric.json)

실제 기존 실행의 `crash.log` 내용에서도 main.py 프로세스 생성 01:58:07.800 → 첫 NetworkManager 로그 01:58:33.779의 약 25.98초 공백을 확인했다. DB 시작은 01:58:34.079, 초기화 완료는 01:58:34.101로 **22ms**였다. 파일의 LastWriteTime 메타데이터는 열린 로그의 최신 내용을 반영하지 않을 수 있어 내용의 타임스탬프와 구분했다.

## 지연이 드러나는 코드 경로

`bootstrap.run()`은 QApplication을 만든 뒤, 진행 단계가 시작되기 전에 SplashScreen을 생성한다.

```text
SplashScreen.__init__
  → get_dialog_theme_tokens()         # 스플래시 색상 요청
  → build_dialog_base_tokens()
  → build_theme_snapshot()
  → build_dialog_metric_tokens()
  → get_dialog_metric_defaults()
  → control_content_height()
  → QFontMetricsF.height()            # 최초 Qt 글꼴 engine/database 요청
```

따라서 색상을 준비하는 과정에서 실제 글꼴 치수 조회까지 실행되고, 스플래시가 표시되기 전에 긴 대기가 발생한다. 명시적인 `loading_font` 진행 단계는 이보다 뒤에 있다. 사용자에게는 진행 화면 자체가 늦게 나타나거나 처음부터 멈춘 것처럼 느껴질 수 있다.

`.venv` cProfile 표본에서는 `SplashScreen.__init__`의 누적 시간이 31.560초였다. 이는 profiler 관측 비용이 있는 별도 표본이며 위 기본/GDI 표의 비프로파일 시간과 섞지 않는다. [프로파일](../../artifacts/startup-performance-20261106/bootstrap-profile-1/profile.txt)

Qt 6.12의 height()는 font engine을 요청하며, 최초 font DB 요청은 플랫폼 DB를 동기적으로 구성할 수 있다. Windows의 기본 DirectWrite 경로와 GDI 경로가 다르다는 공식 소스 구조 및 이번 비교 결과가 일치한다. 네이티브 내부의 system collection 취득·family 열거·font face 생성 중 정확한 하위 대기 함수는 추가 네이티브 trace가 필요하다. [Qt metric 소스](https://github.com/qt/qtbase/blob/v6.12.0/src/gui/text/qfontmetrics.cpp#L1093-L1098), [Windows backend 선택 소스](https://github.com/qt/qtbase/blob/v6.12.0/src/plugins/platforms/windows/qwindowsintegration.cpp#L444-L460), [공식 자료 검토](../../artifacts/startup-performance-20261106/qt-windows-font-research.md).

## 단순 캐시 추가로 해결된다고 판단하지 않은 이유

진단 프로세스에서만 `control_content_height()`를 산술 추정식으로 대체한 비교도 했다. 첫 화면은 여전히 약 28.2초였고 진행 단계 시작 전 약 24.4초가 남았다. 최초 글꼴 준비가 다른 첫 텍스트 그리기 지점으로 이동할 수 있으므로, 함수 호출을 줄이거나 글꼴을 미리 읽는 것만으로 전체 대기가 사라진다고 주장하지 않는다. 제품에는 이 추정식 변경을 적용하지 않았다. [반례 실험](../../artifacts/startup-performance-20261106/bootstrap-private-estimated-counterfactual/startup.json)

`QT_QPA_FONTDIR`를 Windows Fonts 폴더로 강제한 초기 QA와 달리, 최종 기본/GDI 비교는 해당 변수를 제거한 실제 기본 환경이다. 기본 환경에서도 긴 지연이 재현됐으므로 그 QA 변수 하나로 현상을 설명할 수 없다. 시스템 기본 family인 **맑은 고딕**에서도 재현되어 영문 family 이름 하나만의 문제로 단정하지 않는다.

## 부차적 비용

1. **개발 launcher의 약 3.2초:** 매 실행 원본·복제 runtime 629개씩, 합계 최소 79.23MiB의 해시와 검증 subprocess를 수행한다. 빌드용 PyInstaller hook discovery와 WAL smoke도 일반 실행에 포함된다. 다운로드·복제는 cache가 없거나 fingerprint가 바뀐 경우에만 한다. [launcher 감사](../../artifacts/startup-performance-20261106/launcher-readonly-audit.md)
2. **초기 UI 구성 약 3초:** 첫 메뉴·아이콘·패널·테마·초기 복원을 동기로 구성한다. profile 표본의 qtawesome 최초 폰트 준비는 약 1.3초였다. 저장 위젯이 많으면 추가 비용 가능성이 있지만 사용자 위젯 구성별 시간은 이번에 측정하지 않았다.
3. **모듈 import:** headless 안전 가드 이후 import 합계 중앙값은 source 257.9ms, 실제 private runtime 519.2ms였다. Qt/font/첫 paint 비용을 포함하지 않는 수치다. 현재의 24초 이상 주 지연과 구분한다. [import 분석](../../artifacts/startup-performance-20261106/import-findings.md)

## 개선 우선순위

1. **Windows 글꼴 backend 호환성 검증을 우선한다.** GDI의 시작 시간 개선은 확인했지만, 한국어·영문·emoji·아이콘·다국어·100/125/200%·사용자 글꼴·인쇄·위젯을 검증한 뒤 적용 범위를 정해야 한다. 프로세스 단위 진단 옵션은 [Qt 공식 문서](https://doc.qt.io/qt-6/qguiapplication.html#QGuiApplication)에 있으며, 현재 앱과 설치판에는 영구 적용하지 않았다.
2. **스플래시의 색상과 글꼴 metric 준비를 분리한다.** 먼저 빠르게 표시하고 준비 상황을 알릴 수 있도록 구성한다. 이것만으로 총 글꼴 초기화 대기까지 해결됐다고 계산하지 않는다.
3. **개발 실행의 cache 재사용 경로를 정리한다.** 필수 SQLite 안전·무결성 검증은 유지하고, 빌드용 검사와 전체 smoke를 cache 생성/변경 및 CI 시점으로 옮길 수 있는지 검토한다.
4. **남은 UI 구성·위젯 import를 순차적으로 줄인다.** 첫 화면에 필요하지 않은 class import와 숨긴 위젯 복원을 지연하는 방안을 검토한다. 위젯·키 동작·소리·설정 보존 계약을 먼저 확인한다.

이 문서는 원인 분석과 격리 비교 결과다. 제품 소스, 실제 앱의 backend, 설치판, 사용자 DB·계정·글꼴·캐시·환경 설정은 변경하지 않았다. 첫 source profile 중 실사용 앱의 `last_successful_sync`가 외부에서 갱신된 감사 기록은 보존했으며, 모든 계측 앱의 쓰기는 임시 INI로 격리됐다.
