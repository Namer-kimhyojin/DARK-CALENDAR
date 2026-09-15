# Dark Calendar 3.6.8

Dark Calendar 3.6.8은 Windows 로그인 자동 실행과 재시작 후 위젯·레이아웃 복원 신뢰성을 개선하고, 모양 설정의 추천 스타일 선택을 더 직관적으로 다듬은 GPL-3.0-only Windows 데스크톱 릴리스입니다.

## 주요 변경 사항

- Microsoft Store 패키지는 Windows StartupTask로, 독립 실행본은 현재 사용자 Run 등록으로 자동 시작을 실제 Windows에 연결합니다.
- 이전 버전에서 자동 시작을 켠 사용자의 저장값을 새 Windows 등록 방식으로 한 번 이관합니다.
- Windows에서 사용자가 시작 앱을 차단한 경우 설정 상태를 실제 Windows 상태와 맞추고 직접 허용해야 한다는 안내를 표시합니다.
- 재실행 시 메인 창의 마지막 화면 위치를 유지하면서 사용자가 저장한 기본 프리셋의 도크 레이아웃을 자동으로 적용합니다.
- 프리셋을 직접 불러올 때 저장된 창 좌표, 패널 표시 상태, 투명도와 보기 모드를 함께 복원하고 즉시 현재 상태로 백업합니다.
- D-day를 포함한 모든 오버레이 위젯이 생성될 때 저장된 `항상 위에 표시` 값을 창 플래그에 반영합니다.
- 모양 설정의 추천 스타일을 색상 미리보기 카드로 재구성해 선택 상태와 스타일 차이를 빠르게 파악할 수 있습니다.
- Windows Runtime 의존성과 라이선스 번들 검증을 릴리스 파이프라인에 추가했습니다.

## 오픈소스 배포

- 라이선스: GNU General Public License v3.0 only (`GPL-3.0-only`)
- 전체 대응 소스: `DarkCalendar-3.6.8-corresponding-source.zip`
- 런타임 의존성 기준: `requirements-runtime.lock`
- 빌드 도구 기준: `requirements-build.lock`
- 바이너리에는 GPLv3, 제3자 고지, 정확한 패키지 목록과 라이선스 번들이 포함됩니다.

## 배포 파일

- `DarkCalendar-3.6.8-x64.msix`
- `DarkCalendar-3.6.8.0-x64.msixupload`
- `DarkCalendar-3.6.8-corresponding-source.zip`
- 각 패키지의 SHA-256 체크섬

ARM64 패키지는 ARM64 Windows 빌드 머신에서 네이티브로 생성한 뒤 동일 버전의 Store 제출에 결합합니다.
