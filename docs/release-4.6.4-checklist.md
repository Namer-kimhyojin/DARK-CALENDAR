# Air Calendar 4.6.4 공개 확인표

**Date:** 2026-10-20

공개된 앱 후보는 4.6.4이며, main의 개발 버전 4.6.9와 구분한다. 아래 표는 실제 확인한 범위만 기록한다.

- [x] 공개 후보의 원본 commit은 `4748f903b3fcb312977a227d765d49c903b8a4c7`, build run은 39355773285이다. 원본 태그와 패키지를 다시 만들지 않았다.
- [x] QA commit `76a91f435a6801a1066ed23b2d77461c7d23b0a9`의 별도 Windows VM run 39361531935에서 동일 payload로 새 프로필 3회와 업그레이드 프로필 3회 실행을 통과했다. 모든 회차의 정상 종료 코드 0, DB integrity/foreign-key 검사와 합성 일정 보존을 확인했다.
- [x] 릴리스 조정 에이전트가 최종 메인 화면 PNG 6개를 직접 검토했고 해당 파일 해시를 기록했다. 별도 사용자 시각 승인이나 실제 Store 설치 시험을 수행했다고 주장하지 않는다.
- [x] 관련 회귀 검사는 XML identity 중복을 제외한 796개가 통과했다. 실제 EXE 6회 실행은 이 단위검사 건수에 더하지 않았다.
- [x] [GitHub 4.6.4 공개 릴리스](https://github.com/Namer-kimhyojin/DARK-CALENDAR/releases/tag/v4.6.4)는 release ID 417955820이며, 공개 파일 6개를 실제 재다운로드해 원본 Actions 자산과 크기·SHA-256을 대조했다.
- [x] 공개 MSIX와 EXE 버전은 4.6.4.0이다. 기존 제품 identity를 유지하며, 공개 msixupload 안의 MSIX도 공개 MSIX와 동일하다.
- [x] 동봉 SQLite DLL은 3.54.1이며 검증된 DLL·receipt와 일치한다.
- [x] [전체 대응 소스 ZIP](https://github.com/Namer-kimhyojin/DARK-CALENDAR/releases/download/v4.6.4/DarkCalendar-4.6.4-corresponding-source.zip)의 SHA-256은 `8dbea6e223058485ee9f5949424b87b0e2c04e5da393830f0aa50f632fb8bdc0`이다. 공개 파일은 검증한 원본과 동일하다.
- [x] README·SOURCE_OFFER·홈페이지의 공개 버전 안내와 `APP_PUBLISHED_VERSION/DATE`를 4.6.4/2026-10-20으로 맞췄다. 개발 버전 4.6.9와 Dev 채널, 기존 이벤트 설정은 보존했다.
- [ ] Microsoft Store의 기존 제품 `9MXQ08RF22K8`에 최종 패키지와 목록 변경을 제출한 결과를 확인한다. 이 문서 작성 시 Store 제출·인증·게시 확인은 대기 중이다.
- [ ] Store 인증과 실제 게시 상태를 각각 확인하고 결과를 보충한다.
- [ ] 현재 확인된 설치 버전은 4.3.3.0이다. Store를 통한 4.6.4.0 업데이트와 실제 설치 경로의 최초 기동·정상 종료·재시작·사용자 데이터 보존은 별도 확인이 필요하다.

증거: `artifacts/deployment/20261020-db-runtime-fix/checks/candidate-4.6.4-qa-4.6.9-provenance.json`, `checks/native-gate-4.6.4-qa-4.6.9-verification.json`, `public-roundtrip-verification-4.6.4.json`. 로컬 증거에는 계정 자격증명이나 실사용 DB를 포함하지 않는다. GitHub 공개 성공을 Store 인증·게시·설치 완료로 해석하지 않는다.
