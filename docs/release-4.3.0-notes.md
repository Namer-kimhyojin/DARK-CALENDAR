# Air Calendar 4.3.0

2026-10-19 · Windows x64

이번 업데이트는 개발 실행본의 전체 코드·리소스를 통합하고, 일정·동기화·위젯의 오류 복구와 데이터 보존을 보완합니다.

- Google·Outlook·CalDAV·ICS 연결에서 워커 시작 실패, 중복 실행, 오래된 응답과 로컬 수정·삭제가 겹치는 상황을 안전하게 처리합니다.
- 원격 생성 결과가 확인되기 전에 로컬 일정을 삭제한 경우의 기록을 보존하고, 확인이 끝난 뒤 기존 삭제 대기열과 연결합니다. 다른 서비스나 계정의 일정을 자동 복사하지 않습니다.
- 일부 일정만 포함하는 ICS 요청·취소 메시지를 전체 구독 목록으로 반영하지 않아 기존 일정이 지워지는 것을 방지합니다.
- 자연어 날짜·다음 주·시각 해석, 드래그 중 화면 갱신, 반복 일정의 날짜 경계를 보완합니다.
- 캘린더 이관과 체크리스트 가져오기의 중간 실패를 복구하고, 손상된 설정값과 시작 실패를 안전하게 처리합니다.
- 스톱워치 상태 기호를 지원하는 설치 글꼴을 선택해 기본 글꼴에 없는 기호가 누락되는 경우를 보완합니다.

현재 개발 폴더의 전체 실행 입력을 배포 대상으로 사용합니다. 개발 버전, GitHub 공개, Microsoft Store 심사·게시와 설치 버전은 각각 확인합니다. 서비스별 계정 준비와 권한 제한은 기존과 같습니다.

## English

This release integrates the current development runtime and improves recovery and data preservation across calendars, synchronization and desktop widgets.

- Handle worker launch failures, duplicate sync requests and stale responses without discarding newer local changes.
- Preserve unresolved remote-create deletions until a complete lookup can safely connect them to the existing delete queue.
- Reject partial ICS request/cancellation messages as full subscription snapshots.
- Improve natural-language dates and times, drag-time refresh, recurrence boundaries and transactional imports/migrations.
- Recover from malformed settings and startup failures, and choose installed fonts that contain stopwatch transport symbols.

Calendar services retain their existing account, permission and read-only restrictions. Store submission, certification, publication and installation are tracked separately.
