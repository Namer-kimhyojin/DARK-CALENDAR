# Dark Calendar 3.6.6

Dark Calendar 3.6.6은 캘린더 인쇄, 집중 모드, 날짜·시간 입력, 주요 다이얼로그의 사용성과 접근성을 개선한 GPL-3.0-only Windows 데스크톱 릴리스입니다.

## 주요 변경 사항

- 단일 월과 기간 범위 캘린더를 인쇄하거나 PDF로 저장할 수 있습니다. 인쇄 미리보기, 상세 일정 페이지, 흑백·가독성·균형·용지 절약 프리셋을 같은 벡터 렌더링 경로로 제공합니다.
- 집중/포모도로 화면을 메인 창의 몰입형 캔버스로 개편했습니다. `F11`로 집중 화면만 전체 화면 전환하며, `Esc`는 세션을 종료하지 않고 전체 화면만 해제합니다.
- 날짜는 `YYYYMMDD`, 시간은 `HMM` 또는 `HHMM` 숫자열로 바로 입력할 수 있고 기존 달력 선택·스핀·빠른 설정 동작도 유지합니다.
- 공통 다이얼로그의 화면 맞춤, 키보드 포커스, 폼 라벨 연결, 접근성 이름과 버튼 크기를 보강했습니다.
- Google Calendar 설정, 도움말 센터, 자리 비움 설정, 체크리스트 편집, 일정·루틴 편집기의 작은 화면 및 고배율 사용성을 개선했습니다.
- 첫 실행 안내 배너와 패널 도움말 진입점을 추가하고, 오버레이 위젯 이름 입력 및 테마 반영 흐름을 다듬었습니다.
- 19개 번역 리소스의 구조와 placeholder를 동기화하고 관련 UI·인쇄·집중 모드 회귀 테스트를 확장했습니다.

## 오픈소스 배포

- 라이선스: GNU General Public License v3.0 only (`GPL-3.0-only`)
- 전체 대응 소스: `DarkCalendar-3.6.6-corresponding-source.zip`
- 런타임 의존성 기준: `requirements-runtime.lock`
- 빌드 도구 기준: `requirements-build.lock`
- 바이너리에는 GPLv3, 제3자 고지, 정확한 패키지 목록과 라이선스 번들이 포함됩니다.

## 배포 파일

- `DarkCalendar-3.6.6-x64.msix`
- `DarkCalendar-3.6.6.0-x64.msixupload`
- `DarkCalendar-3.6.6-corresponding-source.zip`
- 각 패키지의 SHA-256 체크섬

ARM64 패키지는 ARM64 Windows 빌드 머신에서 네이티브로 생성한 뒤 동일 버전의 Store 제출에 결합합니다.
