# Air Calendar 3.7.3

Air Calendar 3.7.3은 숨김 처리한 Google 캘린더의 일정이 `오늘 일정` 패널에 계속 표시되던 문제를 해결한 Windows 데스크톱 패치 릴리스입니다.

## 주요 변경 사항

- `내 캘린더`에서 숨긴 캘린더의 일정을 메인 캘린더와 `오늘 일정` 패널 모두에서 제외합니다.
- Google 기본 캘린더의 레거시 별칭으로 저장된 일정도 실제 캘린더의 표시 상태를 따르도록 보완했습니다.
- 캘린더 표시/숨김을 바꾸면 메인 캘린더와 `오늘 일정` 패널을 함께 새로 고쳐 변경 결과를 즉시 반영합니다.
- 캘린더 별칭 및 표시 상태 회귀 테스트를 추가했습니다.

## 오픈소스 배포

- 라이선스: GNU General Public License v3.0 only (`GPL-3.0-only`)
- 전체 대응 소스: `DarkCalendar-3.7.3-corresponding-source.zip`
- 런타임 의존성 기준: `requirements-runtime.lock`
- 빌드 도구 기준: `requirements-build.lock`

## 배포 파일

- `DarkCalendar-3.7.3-x64.msix`
- `DarkCalendar-3.7.3.0-x64.msixupload`
- `DarkCalendar-3.7.3-corresponding-source.zip`
- 각 패키지의 SHA-256 체크섬

ARM64 패키지는 ARM64 Windows 빌드 머신에서 네이티브로 생성한 뒤 동일 버전의 Store 제출에 결합합니다.
