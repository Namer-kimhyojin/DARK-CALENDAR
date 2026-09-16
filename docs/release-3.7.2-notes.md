# Air Calendar 3.7.2

Air Calendar 3.7.2는 일정 정보 표시 체계를 통합하고, 좁은 일정 영역과 화면 하단에서도 상세 내용을 읽고 조작할 수 있도록 개선한 Windows 데스크톱 패치 릴리스입니다.

## 주요 변경 사항

- 오늘 일정 패널과 메인 캘린더의 마우스 오버 정보가 같은 정보 구조를 사용하도록 통합했습니다.
- 일정 종류에 따라 시간 또는 기간, 캘린더, 장소, 담당자, 설명을 중복 없이 표시합니다.
- 종일 일정처럼 추가 정보가 없는 오늘 일정 항목은 불필요한 마우스 오버 팝업을 표시하지 않습니다.
- 일정 클릭 상세창에 전체 제목, 주요 정보, 체크리스트, 일정 수정 및 완료 상태 버튼을 정돈해 표시합니다.
- 좁은 캘린더 셀에서도 상세창은 최소 가독 폭을 확보하며, 화면 하단에서는 작업 표시줄에 가리지 않도록 일정 위쪽으로 펼쳐집니다.
- 상세창을 열 때 마우스 오버 팝업을 닫고, Escape 또는 외부 클릭으로 상세창을 닫을 수 있습니다.

## 오픈소스 배포

- 라이선스: GNU General Public License v3.0 only (`GPL-3.0-only`)
- 전체 대응 소스: `DarkCalendar-3.7.2-corresponding-source.zip`
- 런타임 의존성 기준: `requirements-runtime.lock`
- 빌드 도구 기준: `requirements-build.lock`

## 배포 파일

- `DarkCalendar-3.7.2-x64.msix`
- `DarkCalendar-3.7.2.0-x64.msixupload`
- `DarkCalendar-3.7.2-corresponding-source.zip`
- 각 패키지의 SHA-256 체크섬

ARM64 패키지는 ARM64 Windows 빌드 머신에서 네이티브로 생성한 뒤 동일 버전의 Store 제출에 결합합니다.
