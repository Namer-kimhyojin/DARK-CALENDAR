# Air Calendar 5.8.0 배포 확인표

**Date:** 2026-11-23

공개하지 않은 5.7.0 후보를 대신해, 5.7.0 내용과 위젯 전용 모드 지원 개선(날짜 선택·크기 조절·다중 모니터·아이콘·시계·투명도 연동·메뉴·트레이·배치 탭 재구성)을 묶어 기존 Microsoft Store 제품에 5.8.0을 게시한다. GitHub 5.7.0 draft와 태그는 공개하지 않고 그대로 둔다.

- [x] 5.8.0 버전 및 최종 입력 예약 (`prepare --bump minor`, 이벤트 `release-5.8.0`)
- [x] 로컬 사전 검사: 품질 게이트·인코딩 가드
- [x] 커밋·푸시, 태그 `v5.8.0` (`513fccc`)
- [x] CI 빌드·품질·인코딩 검사 (run 45099666599)
- [x] 동일 payload의 새/업그레이드 프로필 총 6회 기동·정상 종료·재시작, 6개 실제 화면 검토
- [x] GitHub draft를 재태그·재빌드 없이 공개, API digest가 draft와 일치 (2026-11-23)
- [x] Store 제출 파일: 이 PC에 Windows SDK가 없어 로컬 빌드 불가 → CI가 만든 공개 릴리스 msixupload 사용, SHA-256 `1f0d2dfa…2772c4e` 일치 확인
- [x] 변경 안내 언어별 보존형 갱신·fresh export 대조 (453행, ReleaseNotes 18셀만 변경)
- [x] 5.8.0.0 x64 패키지 Validated·제출 심사 접수(제출 38, 2026-11-23, 상태: Update in certification)
- [ ] Store 게시 확인
- [ ] 설치 앱 5.8.0.0 기동 확인

배포 증거: `artifacts/deployment/5.8.0/`.
