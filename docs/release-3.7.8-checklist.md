# Air Calendar 3.7.8 Deploy Checklist

**Date:** 2026-10-01
**Target:** GitHub GPLv3 릴리스 및 Windows x64 Store 업로드 패키지

## 배포 전 확인

- [x] 사용자 배포 요청에 따라 다음 Stable 버전을 3.7.8로 정했습니다.
- [x] 위젯 전용 모드·자유 배치·WYSIWYG 편집·주간 보기·사용자 배치 프리셋 범위를 별도 릴리스 작업 폴더로 준비했습니다.
- [x] 기능 개발 단계에서 관련 테스트 368개가 통과했습니다.
- [x] 3.7.8 앱·패키지·웹사이트·전체 대응 소스 링크의 버전 일치 검사와 release-compliance 테스트 8개를 통과했습니다.
- [x] 릴리스 작업 폴더의 최종 테스트 134개 파일·1,087개 테스트가 모두 통과했습니다.
- [x] Quality Gate에 해당하는 22개 파일·179개 테스트가 통과했습니다.
- [x] Ruff, compileall, 인코딩 guard·정책 테스트 12개가 통과했고, 19개 로케일의 i18n 검사에서 문제가 없었습니다.
- [x] 공식 `build-release.bat -ValidateOnly`가 Python 3.13.15와 잠금 의존성 37개(runtime)·7개(build) 검증을 통과했습니다.
- [x] 릴리스 변경 71개 파일의 추적·staging을 확인했고, 로컬 미리보기 `artifacts/`는 stage에서 제외했습니다.

## 로컬 빌드 증거

- [ ] `build-release.bat -Arch x64 -Version 3.7.8 -PackageVersion 3.7.8.0 -ReleaseDate 2026-10-01 -Channel Stable -NoBanner`로 네이티브 x64 패키지를 빌드합니다.
- [ ] x64 MSIX, Store 업로드, 전체 대응 소스 ZIP과 SHA-256 체크섬을 검사합니다.
- [ ] manifest의 `Kimhyojin.DarkCalendar / 3.7.8.0 / x64`, 표시 이름 `Air Calendar`, 게시자 `Kim,hyojin`을 확인합니다.
- [ ] Store 업로드에 포함된 MSIX와 독립 MSIX의 SHA-256이 일치합니다.
- [ ] payload compliance 검사와 정리된 기본 DB·전체 대응 소스 구성을 확인합니다.

## 공개 배포

- [ ] 버전이 일치하는 소스와 `v3.7.8` 태그를 push합니다.
- [ ] Build Release, Quality Gate, Encoding Policy 및 Pages 워크플로 성공을 확인합니다.
- [ ] 공개 GitHub 릴리스의 패키지·소스·체크섬을 확인합니다.
- [ ] 공개 Pages의 `appVersion=3.7.8`과 `v3.7.8` 라이선스·소스 링크를 확인합니다.
- [ ] 공개 자산을 다시 내려받아 함께 공개한 SHA-256과 비교하고, 업로드 내부 MSIX가 공개 MSIX와 일치하는지 확인합니다.
- [ ] Partner Center 업로드·인증 제출은 별도 승인과 제출 결과를 확인합니다.
- [ ] 설치된 Microsoft Store 패키지 버전은 GitHub 공개 상태와 별도로 확인합니다.

## 롤백 기준

- 앱 시작·종료 실패 또는 필수 Qt DLL 누락
- 기존 설정·위젯·사용자 배치·캘린더 데이터 복원 실패
- 필수 앱 소스·자산 또는 GPLv3 전체 대응 소스 누락
- 공개 패키지·Store 업로드·체크섬 간 불일치
