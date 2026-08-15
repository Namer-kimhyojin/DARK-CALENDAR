# Dark Calendar 3.6.7

Dark Calendar 3.6.7은 다일 일정 등록, 반복 업무 편집, 주요 모달의 정보 인식성과 Google Calendar 동기화 안정성을 개선한 GPL-3.0-only Windows 데스크톱 릴리스입니다.

## 주요 변경 사항

- 메인 캘린더의 빈 날짜 범위를 드래그하거나 Shift로 선택해 포함 종료일 기준의 다일 종일 일정을 등록할 수 있습니다.
- 캘린더 재렌더링이나 창 비활성화 중에도 범위 드래그 상태와 미리보기가 안전하게 정리됩니다.
- 반복 일반업무 편집 시 `이 일정만` 또는 `이 일정 및 이후`를 선택할 수 있으며, 시리즈 분리·기간 단축·순번 재계산을 하나의 트랜잭션으로 처리합니다.
- 구독 캘린더의 종일 일정이 Google Calendar의 배타적 종료일 대신 사용자가 인식하는 마지막 포함 날짜로 표시됩니다.
- 일정 추가·수정·관리 모달의 제목, 설명, 버튼 계층, 포커스, 접근성 이름과 색상 대비를 공통 디자인 토큰에 맞춰 정돈했습니다.
- Google Calendar 푸시 큐와 전체 동기화의 중복 실행을 제거하고, 삭제 outbox의 일정·캘린더별 유일성과 휴지통 보존 정책을 강화했습니다.
- 집중 기록 패널을 공통 구성요소로 통합하고, 통계 조회를 날짜 인덱스 기반 범위 쿼리로 최적화했습니다.
- 19개 번역 리소스와 UI·DB·동기화 회귀 테스트를 확장했습니다.

## 오픈소스 배포

- 라이선스: GNU General Public License v3.0 only (`GPL-3.0-only`)
- 전체 대응 소스: `DarkCalendar-3.6.7-corresponding-source.zip`
- 런타임 의존성 기준: `requirements-runtime.lock`
- 빌드 도구 기준: `requirements-build.lock`
- 바이너리에는 GPLv3, 제3자 고지, 정확한 패키지 목록과 라이선스 번들이 포함됩니다.

## 배포 파일

- `DarkCalendar-3.6.7-x64.msix`
- `DarkCalendar-3.6.7.0-x64.msixupload`
- `DarkCalendar-3.6.7-corresponding-source.zip`
- 각 패키지의 SHA-256 체크섬

ARM64 패키지는 ARM64 Windows 빌드 머신에서 네이티브로 생성한 뒤 동일 버전의 Store 제출에 결합합니다.
