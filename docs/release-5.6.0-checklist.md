# Air Calendar 5.6.0 배포 확인표

**Date:** 2026-11-17

일정 칩 통일, 벡터 아이콘, 다이얼로그·테마 정리를 담아 기존 Microsoft Store 제품에 5.6.0을 게시한다.

- [x] 5.6.0 버전 및 최종 입력 예약·커밋·푸시 (입력 commit `d2f2571e9f7ecddb64bfaa4cb46e74968a3f7416`, 태그 `v5.6.0`)
- [x] 로컬 사전 검사: ValidateOnly 통과, 동봉 SQLite 3.54.1
- [x] CI 빌드 `43984144454`, 품질 검사 `43984144602`, 인코딩 검사 `43984144531` 통과
- [x] 동일 payload의 새/업그레이드 프로필 총 6회 기동·정상 종료·재시작, 6개 실제 화면 검토
- [x] GitHub draft를 재태그·재빌드 없이 공개 (2026-11-17 01:14Z), API digest가 draft와 일치
- [ ] 공개 자산 재다운로드·MSIX payload 대조: 사용자 요청으로 생략 (이 PC에서 `*.githubusercontent.com` 접근 불가)
- [x] 변경 안내 18개 언어 보존형 갱신·fresh export 대조
- [x] 5.6.0.0 x64 패키지 Validated·제출 36 심사 접수
- [ ] Store 게시 확인
- [ ] 설치 앱 5.6.0.0 기동 확인

배포 증거: `artifacts/deployment/5.6.0/20261117-0901/` (`resume-checkpoint.json`).

확인 결과: GitHub 5.6.0 공개 완료. 공개 자산 digest는 MSIX `e524e32a…`, msixupload `38e5337f…`, 대응 소스 ZIP `84a3b42e…`이다. native 게이트 후보 EXE `a8b1aba0…`, 동봉 `sqlite3.dll` `4b59d3cd…`.

Store 제출 36(`1152921505702422736`)을 2026-11-17 11:16 KST에 접수했다. 제출 파일은 `DarkCalendar-5.6.0.0-x64.msixupload`(SHA-256 `38e5337f15398d434bf1a2020a9467eb15fa332f17b96b455ac30f5b89125194`)이다. 목록 453행 중 스크린샷 이미지 행 120개를 제외한 333행을 가져왔고, fresh export에서 ReleaseNotes 18셀만 바뀐 것을 확인했다. 확인 시점의 상태는 사전 처리 중이다. Store 게시와 설치 업데이트는 아직 완료되지 않았다.
