# Air Calendar 3.7.1

Air Calendar 3.7.1은 기존 Microsoft Store 구매 및 자동 업데이트 호환성을 유지하면서 제품 표시 이름을 Air Calendar로 개편한 Windows 데스크톱 릴리스입니다.

## 주요 변경 사항

- 앱, 시작 메뉴, 도움말, 인쇄물, 웹사이트와 19개 언어의 고객 표시 이름을 Air Calendar로 통일했습니다.
- 기존 Store 패키지 ID `Kimhyojin.DarkCalendar`, 실행 파일명, 설정 저장소와 사용자 데이터 경로는 유지해 기존 설치가 그대로 업데이트되도록 했습니다.
- 언어 변경이나 앱 재실행 후에도 마지막 화면 레이아웃, 패널 상태, 위젯 전용모드, 위젯 설정과 개별 위치가 유지되도록 복원 순서를 수정했습니다.
- 월간 인쇄에서 여러 날 일정이 날짜마다 중복 표기되지 않도록 주간 연결 막대로 표시하고, 넘치는 일정만 별도 상세 페이지에 정리했습니다.
- 인쇄 달력의 정보 위계, 날짜 표시, 여백, 색상과 상세 목록을 읽기 쉬운 현대적 형식으로 개선했습니다.
- 배포 환경의 외부 PDF 도구에서 ICU DLL이 잘못 혼입되어 QtCore가 실행되지 않던 문제를 수정했습니다.
- 배포 검증 단계가 외부 ICU DLL을 자동 차단하고, QtCore·QtGui·QtWidgets·QtPrintSupport 포함 여부와 민감 파일 제외 여부를 확인합니다.

## 오픈소스 배포

- 라이선스: GNU General Public License v3.0 only (`GPL-3.0-only`)
- 전체 대응 소스: `DarkCalendar-3.7.1-corresponding-source.zip`
- 런타임 의존성 기준: `requirements-runtime.lock`
- 빌드 도구 기준: `requirements-build.lock`

## 배포 파일

- `DarkCalendar-3.7.1-x64.msix`
- `DarkCalendar-3.7.1.0-x64.msixupload`
- `DarkCalendar-3.7.1-corresponding-source.zip`
- 각 패키지의 SHA-256 체크섬

ARM64 패키지는 ARM64 Windows 빌드 머신에서 네이티브로 생성한 뒤 동일 버전의 Store 제출에 결합합니다.
