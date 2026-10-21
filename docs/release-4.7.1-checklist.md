# Air Calendar 4.7.1 공개 확인표

**Date:** 2026-10-21

제품 후보 4.7.1과 별도 QA 커밋을 연결해 검증했다. 이미 만든 태그·패키지·대응 소스는 재빌드하거나 교체하지 않았다.

- [x] 원본 commit은 `6329be6f8a0b91946837289f44d56637b9a91636`, build run은 `39536866518`이다. Windows x64 빌드 job `119015409190`이 성공했다.
- [x] QA commit `098995ae786a248817deae71894b47699d1495ea`의 별도 Windows VM run `39538692039`에서 원본 payload로 새 프로필 3회와 업그레이드 프로필 3회를 검증했다. 모두 정상 종료 코드 0이며, 재시작 후 합성 일정과 DB 무결성을 확인했다.
- [x] 릴리스 조정 에이전트가 메인 화면 PNG 6개를 직접 검토하고 파일 해시를 기록했다. 실제 사용자 시험이나 Store 설치 시험으로 표현하지 않는다.
- [x] 관련 회귀 검사 1,694개 고유 사례 중 1,690개 통과, 4개 환경 의존 건너뛰기, 실패 0개를 확인했다. 91개 unittest 하위 검사를 중복 합산하지 않았다.
- [x] [GitHub 4.7.1 릴리스](https://github.com/Namer-kimhyojin/DARK-CALENDAR/releases/tag/v4.7.1)는 release ID `419118434`이다. 초안 파일 6개를 실제 내려받아 원본 Actions 자산과 크기·SHA-256을 대조한 뒤 같은 초안을 공개했다.
- [x] 공개 파일 6개를 별도 재다운로드했으며 초안·원본과 크기·SHA-256이 모두 일치한다. 태그 커밋과 자산 ID도 유지됐다.
- [x] MSIX와 EXE 버전은 `4.7.1.0`이며 기존 제품 identity를 유지한다. msixupload 내부 MSIX도 동일하다.
- [x] 동봉 SQLite DLL `3.54.1`과 고정 receipt를 대조했다. 깨끗한 DB, 50개 라이선스 항목, 43개 상위 소스 아카이브를 검사했다.
- [x] [대응 소스 ZIP](https://github.com/Namer-kimhyojin/DARK-CALENDAR/releases/download/v4.7.1/DarkCalendar-4.7.1-corresponding-source.zip)의 SHA-256은 `a2fd9b72907a07c0d071fe34662716223a9ede730bbb3dfa0c5e98ef9e8fd53a`이다.
- [x] 홈페이지·README·SOURCE_OFFER·공개 버전 메타데이터를 확인된 4.7.1/2026-10-21로 맞췄다. 공개 안내 commit `cb9dbb44e4af297553ef379cd5c4310a8f0b5315`의 Quality·Encoding·Pages 검사가 성공했고, 실제 HTML·설정·JavaScript가 커밋과 바이트 단위로 일치한다. 소스·라이선스·제3자 고지 링크도 정상 응답했다.
- [x] Store 제출 30, ID `1152921505702186697`의 18개 언어별 변경 안내를 UI에서 저장하고 CSV 재내보내기로 확인했다. 8,151개 값 중 변경 안내 18개만 바뀌었고 나머지 8,133개 값과 항목 순서는 유지됐다. 비어 있는 기존 기본 언어 셀도 유지했다.
- [x] 공개 재다운로드로 해시를 확인한 동일 MSIXUPLOAD를 Store에 업로드했다. `DarkCalendar-4.7.1.0-x64.msixupload`의 `Validated` 표시와 저장을 확인한 뒤 제출 30의 인증 접수를 완료했다.
- [ ] 제출 후 상태는 `사전 처리 중`이다. 인증을 통과하면 자동 게시하도록 기존 설정을 유지했다. 인증 통과와 실제 게시는 아직 확인되지 않았다.
- [ ] 이 PC에서 확인한 설치 버전은 `4.3.3.0`이다. Store 업데이트와 실제 설치 앱의 최초 기동·정상 종료·재시작은 수행하지 않았다.

패키지 SHA-256:

- MSIX: `fa7cef2cfe006a4fbf7b93390f1117c9b623cc0a48e85d71026e9644000f46fa`
- MSIXUPLOAD: `f861689340c88b1722d562c162d8eb13edcad4fb24fca996a9802c2c9e2f9361`

증거 폴더: `artifacts/deployment/4.7.1/20261021-1208`. 원본 빌드의 첫 네이티브 검사 실패와 이전 4.7.0 빌드 전 실패 기록은 보존했다. 새 QA 검사 성공은 동일 4.7.1 payload의 결과이며 이전 실패를 성공으로 바꿔 기록하지 않는다. GitHub 공개·Store 제출·인증·게시·설치는 서로 다른 단계다.
