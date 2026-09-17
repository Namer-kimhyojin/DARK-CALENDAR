# Air Calendar 3.7.5

Air Calendar 3.7.5는 메인 캘린더와 보조 패널의 시각적 일관성, 공개 브랜드 표기, 시작 화면 다국어 지원을 보강한 Windows 데스크톱 릴리스입니다.

## 주요 변경 사항

- 메인 캘린더, 오른쪽 업무·지시 패널, 상단 툴바가 같은 표면 색상과 투명도 규칙을 사용하도록 정리했습니다.
- 반투명 레이어가 중첩되어 일부 패널과 툴바가 지나치게 밝거나 어둡게 보이던 문제를 수정했습니다.
- 일정 상세 팝업의 기간·설명 영역에 표시되던 불필요한 내부 테두리를 제거했습니다.
- 시스템 메뉴의 종료 아이콘을 다른 메뉴 아이콘과 같은 단색 규칙으로 통일했습니다.
- 사용자에게 노출되는 개인 이름 표기를 `Zinz-Soft`로 정리하면서 기존 Store 패키지·설정 호환 식별자는 유지했습니다.
- 시작 화면의 “오늘을 정리하는 중” 문구를 19개 번들 언어에 맞게 번역하고, 제한된 화면 폭에서도 잘리지 않도록 문구 길이를 검증했습니다.

## 오픈소스 배포

- 라이선스: GNU General Public License v3.0 only (`GPL-3.0-only`)
- 전체 대응 소스: `DarkCalendar-3.7.5-corresponding-source.zip`
- 런타임 의존성 기준: `requirements-runtime.lock`
- 빌드 도구 기준: `requirements-build.lock`

## 배포 파일

- `DarkCalendar-3.7.5-x64.msix`
- `DarkCalendar-3.7.5.0-x64.msixupload`
- `DarkCalendar-3.7.5-corresponding-source.zip`
- 각 패키지의 SHA-256 체크섬

ARM64 패키지는 ARM64 Windows 빌드 머신에서 네이티브로 생성한 뒤 동일 버전의 Store 제출에 결합합니다.
