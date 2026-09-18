# Air Calendar 3.7.6

Air Calendar 3.7.6은 메인 캘린더의 월 이동 UI와 다국어 완성도를 다듬고, 배포 폴더를 최신 통합본 기준으로 정리한 Windows 데스크톱 릴리스입니다.

## 주요 변경 사항

- 메인 캘린더 상단을 `오늘` 버튼과 `이전 · 월 제목 · 다음` 통합 탐색 그룹으로 재구성했습니다.
- 월 제목을 현재 언어의 월 표기 방식으로 표시하고, 제목을 눌러 이전·현재·다음 연도의 원하는 달로 바로 이동할 수 있게 했습니다.
- 오늘 날짜를 보고 있을 때 `오늘` 버튼이 비활성화되도록 해 현재 상태를 더 분명하게 표시합니다.
- 월 이동 버튼과 월 제목에 접근성 이름과 도움말을 추가했습니다.
- 달력 월 제목·이전/다음 기간·오늘 이동 안내 문구를 19개 번들 언어에 맞게 보완했습니다.
- 오늘 브리핑과 노출 설정에 누락돼 있던 번역 항목을 17개 언어에 추가해 모든 로케일 구조를 동기화했습니다.
- 이전 빌드, 구형 Store 업로드 패키지, 임시 작업물과 백업 사본을 정리하고 현재 통합본만 새로 생성하도록 배포 폴더를 초기화했습니다.

## 오픈소스 배포

- 라이선스: GNU General Public License v3.0 only (`GPL-3.0-only`)
- 전체 대응 소스: `DarkCalendar-3.7.6-corresponding-source.zip`
- 런타임 의존성 기준: `requirements-runtime.lock`
- 빌드 도구 기준: `requirements-build.lock`

## 배포 파일

- `DarkCalendar-3.7.6-x64.msix`
- `DarkCalendar-3.7.6.0-x64.msixupload`
- `DarkCalendar-3.7.6-corresponding-source.zip`
- 각 패키지의 SHA-256 체크섬

ARM64 패키지는 ARM64 Windows 빌드 머신에서 네이티브로 생성한 뒤 동일 버전의 Store 제출에 결합합니다.
