# Air Calendar 5.8.5 배포 확인표

**Date:** 2026-11-25

한글 검색 입력 버벅임, 도크 제목줄 누수, 패널 갱신 시 설정 반복 읽기, 사이드 패널 경계, 시작 시 달력 중복 렌더링을 고친 patch 배포다. Store listing과 변경 안내는 바꾸지 않고 패키지만 교체한다.

- [x] 변경 이력 기록(`change-20261125-search-panels-startup`)과 5.8.5 최종 입력 예약 (`prepare --version 5.8.5`, 이벤트 `release-5.8.5`)
- [x] 로컬 사전 검사: 전체 테스트 7,409개·품질 게이트·인코딩 가드
- [x] 커밋·푸시, 태그 `v5.8.5` (`41dce82`)
- [x] CI 빌드·품질·인코딩 검사 (run 45515921426)
- [x] 동일 payload의 새/업그레이드 프로필 총 6회 기동·정상 종료·재시작, 6개 실제 화면 검토 (SQLite 3.54.1)
- [x] GitHub draft를 재태그·재빌드 없이 공개, API digest가 draft와 일치 (release 457490297, 2026-11-25)
- [x] Store 제출 파일: 이 PC에 Windows SDK가 없어 로컬 빌드 불가 → CI가 만든 공개 릴리스 msixupload 사용, SHA-256 `1b7c1820…eef23567` 일치 확인
- [x] 5.8.5.0 x64 패키지 Validated·제출 심사 접수(제출 39, 2026-11-25, 상태: Update in certification)
- [ ] Store 게시 확인
- [ ] 설치 앱 5.8.5.0 기동 확인

배포 증거: `artifacts/deployment/5.8.5/`.
