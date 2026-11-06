# Air Calendar 5.0.2 배포 확인표

**Date:** 2026-11-06

게시·설치 후속 확인: 2026-11-07. 출시일과 후속 관찰일을 구분한다.

- [x] 최종 전체 실행 입력 718개와 대응 소스 확인. 이전 5.0.0·5.0.1 실패 증거 보존
- [x] 최종 CI 빌드·정적 검증·실제 Windows 화면 검토 통과
- [x] 동일 payload의 새 프로필 3회·업그레이드 프로필 3회 기동·정상 종료·재시작 통과
- [x] GitHub 자산 6개 공개 및 별도 원격 재다운로드 해시 검증 통과
- [x] 홈페이지 5.0.2 안내 공개 확인
- [x] 기존 Store Submission 33의 5.0.2.0 x64 패키지 검증·심사 제출
- [x] Store listing 18개 언어·언어별 스크린샷 6장 및 기존 필드 보존 확인
- [x] 11/07 인증된 Partner Center에서 Submission 33 게시 및 공개 패키지 5.0.2.0 확인
- [x] 이 PC의 Store 서명 5.0.2.0 x64 설치 확인. EXE·SQLite DLL 해시가 최종 CI payload와 일치
- [ ] 실제 설치 앱의 정상 재시작·핵심 화면·사용자 데이터 유지 인수

## 배포 식별 정보

- [GitHub v5.0.2](https://github.com/Namer-kimhyojin/DARK-CALENDAR/releases/tag/v5.0.2), release ID `435765529`
- build commit `39b335c54d4a944d32ecd1d7ebe76628e4bbe753`
- 최종 [빌드·native 검사 run 42112237912](https://github.com/Namer-kimhyojin/DARK-CALENDAR/actions/runs/42112237912): 성공, native 6회 통과
- 공개 파일 재다운로드 run `42118407199`: 성공. 로컬 CDN 연결 시간 초과 기록은 보존하고 원격 검증과 구분
- MSIXUPLOAD SHA-256: `fdd2df33bf88a32113c8fde04967342f79a345f764b2b4dc0a98c2e2e444e525`
- EXE SHA-256: `526c9967671ebd481814010f37eaa9f0f435ed43cd44cc795e7481534330a9f0`
- SQLite DLL SHA-256: `4b59d3cded9dc1608544160f3b4b10ac974c6ac0d6ffc23064e5f4c8dbd05aea`
- 기존 제품 `9MXQ08RF22K8`, 공개 제출 `33 / 1152921505702325950`

배포 원본 증거는 `artifacts/deployment/5.0.2/20261106-0620/`의 `final-facts.json`, `DEPLOYMENT_RESULT.md`, `final-ci/validation/final/summary.json`, `root-screen-review.json`, `release-readback-qa/complete-draft-and-public-readback.json`에 있다. 원본의 당시 심사 대기 기록을 덮어쓰지 않는다.

11/07 게시·설치 근거는 `artifacts/maintenance/20261107-0301/`의 `partner-center-observation.yml`, `store33-published-packages.yml`, `store-installation.json`이다. 이번 실행 전에 공식 Store 설치가 이미 갱신되어 있었으며 새 설치·제출·패키지 재빌드는 하지 않았다. 별도 Submission 34 초안은 보존했다.

설치 경로에서 앱 프로세스와 자체 자리 비움 화면은 관찰했으나 UI 제어 도구가 대상 창을 활성화하지 못했다. 정상 종료·재시작 및 개인 데이터 비교는 미완료다. 격리 프로필 native 검사 6회와 사용자 프로필 인수는 별개다. 앱을 강제 종료하거나 개인 DB·계정·설정을 조작하지 않았다.
