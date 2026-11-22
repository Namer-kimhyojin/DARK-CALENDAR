# Air Calendar 5.7.0 배포 확인표

**Date:** 2026-11-22

중요도·상태 미지정과 라벨 색·아이콘, 위젯 전용 모드 1단계 정리(배치 4종·표면 4종·설정 이관), 달력 표시·성능 개선을 담아 기존 Microsoft Store 제품에 5.7.0을 게시한다.

- [x] 5.7.0 버전 및 최종 입력 예약 (`prepare --bump minor`, 이벤트 `release-5.7.0`)
- [ ] 로컬 사전 검사: 품질 게이트·인코딩 가드
- [ ] 커밋·푸시, 태그 `v5.7.0`
- [ ] CI 빌드·품질·인코딩 검사
- [ ] 동일 payload의 새/업그레이드 프로필 총 6회 기동·정상 종료·재시작, 6개 실제 화면 검토
- [ ] GitHub draft를 재태그·재빌드 없이 공개, API digest가 draft와 일치
- [ ] Store 제출용 msixupload 로컬 빌드(태그 커밋·깨끗한 작업 트리), SHA-256 기록
- [ ] 변경 안내 18개 언어 보존형 갱신·fresh export 대조
- [ ] 5.7.0.0 x64 패키지 Validated·제출 심사 접수
- [ ] Store 게시 확인
- [ ] 설치 앱 5.7.0.0 기동 확인

배포 증거: `artifacts/deployment/5.7.0/` (`resume-checkpoint.json`).
