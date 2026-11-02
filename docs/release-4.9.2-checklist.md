# Air Calendar 4.9.2 배포 확인표

**Date:** 2026-11-02

사용자의 2026-11-02 누적 개선 통합 배포 요청을 수행한다. 4.8.0 이후의 위젯 그래픽·디자인·통합 관리·작업 공간, 다국어, 동기화·구독 개선을 모두 포함한다. 새 기능에 더해 배포 검증에서 확인한 Qt 문구 누락 수정과 SIP 런타임 갱신을 포함한다.

- [x] 4.9.0 사전 검사 예약과 4.9.1 실패 후보를 보존하고 공개하지 않음
- [x] native 종료 오류 덤프·원본/QA commit·패키지 해시 연결 및 미확인 범위 구분
- [x] SIP 13.11.1 → 13.12.0, Qt 미매핑 문구 대체 수정. PyQt6·Qt 6.10.2 및 SQLite 3.54.1 유지
- [x] 최종 입력 705개 기록·4.9.2 예약·126파일 3,168건 통과/권한 제한 4건 건너뜀·인코딩·공식 빌드 사전 검사
- [x] 커밋 입력 일치·태그 푸시·CI 단일 최종 패키지 빌드
- [x] 새/업그레이드 프로필 각각 3회, 총 6회 실제 EXE 기동·정상 종료/재시작과 화면 검토
- [x] 동일 draft 공개·공개 파일 재다운로드·코드/리소스·의존성·SQLite·클린 DB·라이선스·대응 소스 검증
- [x] 홈페이지 최신 버전·Store 상태 안내 반영과 공개 확인
- [x] Store 원본 listing 보존·18언어 변경 안내·패키지 업로드 검증·심사 제출
- [ ] Store 게시·공식 설치 업데이트·실제 설치 앱 인수

증거: `artifacts/deployment/4.9.2/20261102-0943/`. [4.9.1 종료 오류 진단](maintenance/native-shutdown-20261102.md)의 실패와 성공 결과를 모두 보존한다. 과거 패키지·태그·원본 증거는 변경하지 않는다.

초기 브라우저 연결 제한은 사용자 설정·로그인 후 해소됐다. 11/02 13시대 인증된 포털에서 기존 Submission 32를 재사용하여 4.9.2.0 x64를 제출했다. 화면은 ‘제품 업데이트: 인증 중’, 세부 단계는 ‘사전 처리 중’이다. 심사 통과 후 자동 게시를 유지하며, 현재 게시본 Submission 31·설치판 4.8.0.0과 구분한다.

## 공개 파일과 검증 연결

- [GitHub v4.9.2](https://github.com/Namer-kimhyojin/DARK-CALENDAR/releases/tag/v4.9.2), release ID `430981895`. 동일 draft의 자산 6개를 공개하고 전부 새로 다운로드하여 해시 일치를 확인했다.
- build commit `4818a7b8957c9f59af8e37fb6632256946bff5f3`, 단일 패키지 빌드 run `41369216042`. 이 run의 기존 native 작업 실패는 보존되어 전체 run은 성공으로 표시하지 않는다.
- QA commit `fba7fb1a231f496c5c79d53ff06cd84a841ab37e`, 별도 Windows VM run `41371580195` 성공. 원본 payload와 보호된 제품·의존성·패키징 입력의 불변을 대조했다. 현재 후보 6회 모두 exit 0, 이전 4.3.3 업그레이드 fixture도 정상 종료했다. 제한적 legacy 예외 분류는 이 최종 성공 run에서 사용하지 않았다.
- 실제 EXE 6개 화면을 Codex가 검토했다. 사용자 인수나 Store 설치판의 동작 검증과는 별개다. 원본 payload 1,874개 파일, 705개 실행 입력 및 신규 모듈의 PYZ 포함 여부, SIP 13.12.0 실제 바이너리까지 확인했다.
- MSIX SHA-256: `fb071e29eea7be8588f1d40e3050eaee6bee9de0b20ad9aa2e8ed5a5c426fe91`
- MSIXUPLOAD SHA-256: `781757c7e0e54a5c379149ec11f80a45e2216f8698feda74a56220a4bc9cdda7`
- 대응 소스 ZIP SHA-256: `cfefa9084804ba30e8e4bb6e288bae575bb26c6dd3526ce54a97bd2370184ca3`
- 기존 Submission 32 (`1152921505702292348`)의 18언어 변경 안내 저장·동일 패키지 Validated/Save·심사 제출 완료. 453행 원본에서 스크린샷 이미지 120행만 제외한 333행을 보존해 가져왔고, 새 전체 export의 429개 필드/ID·453행에서 의도한 ReleaseNotes 18셀 외 차이가 없다. 이미지·순서·캡션·가격·가용성·옵션을 보존했다. 새 빌드·버전 증가·새 초안 생성은 하지 않았다.
- 2026-11-02 읽기 전용 설치 조회: `Kimhyojin.DarkCalendar 4.8.0.0`, 서명 `Store`. 개인 DB·설정·설치 앱을 변경하지 않았다.

홈페이지 공개 확인: 기존 GitHub Pages의 index.html·app.js·site-config.json이 publication commit 53e532c661595096003675a9a57d8fef28798101의 원격 bytes와 일치한다. Pages run 41373493824 성공. 브라우저 UI 세션은 비활성화여서 HTTP 대조 범위로 기록한다.

Store 제출 증거: `artifacts/deployment/4.9.2/20261102-0943/store-submission-32/`의 `submission-receipt.json`, `submission-confirmed.jpg`, `package-upload-verification.json`, `listing-readback-verification.json`. 심사 접수를 확인했으므로 게시 대기는 다음 승인된 후속 조회에서 이어가며, 설치 완료로 보고하지 않는다.
