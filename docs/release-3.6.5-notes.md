# Dark Calendar 3.6.5

Dark Calendar 3.6.5는 GPL-3.0-only로 배포되는 Windows 데스크톱 릴리스입니다.

## 주요 변경 사항

- 시스템 트레이가 없거나 일시적으로 사용할 수 없는 환경에서도 창 종료 흐름이 안전하게 동작하도록 개선했습니다.
- 트레이, 단축키, 창 닫기 동작의 표시 상태를 하나의 흐름으로 정리하고 종료 수명주기 회귀 테스트를 추가했습니다.
- Google Calendar의 `primary` 캘린더 별칭을 앱별 설정에 맞게 해석해 이벤트 조회 및 증분 동기화의 안정성을 높였습니다.
- 패널 모양 설정에서 프리셋과 글꼴 UI를 필요할 때만 생성하고, 변경 전/후 미리보기와 선택 요약을 추가했습니다.
- 패널 투명도와 테마 스냅샷 동작을 보강하고 관련 UI 테스트를 확장했습니다.
- 다국어 리소스와 런타임 i18n 검증을 갱신했습니다.
- 홈페이지를 밝은 색상 체계로 정돈하고 오픈소스·라이선스·동일 버전 소스 링크를 3.6.5에 맞췄습니다.

## 오픈소스 배포

- 라이선스: GNU General Public License v3.0 only (`GPL-3.0-only`)
- 전체 대응 소스: `DarkCalendar-3.6.5-corresponding-source.zip`
- 런타임 의존성 기준: `requirements-runtime.lock`
- 빌드 도구 기준: `requirements-build.lock`
- 바이너리에는 GPLv3, 제3자 고지, 정확한 패키지 목록과 라이선스 번들이 포함됩니다.

## 배포 파일

- `DarkCalendar-3.6.5-x64.msix`
- `DarkCalendar-3.6.5.0-x64.msixupload`
- `DarkCalendar-3.6.5-corresponding-source.zip`
- 각 패키지의 SHA-256 체크섬

ARM64 패키지는 ARM64 Windows 빌드 머신에서 네이티브로 생성한 뒤 동일 버전의 Store 제출에 결합합니다.
