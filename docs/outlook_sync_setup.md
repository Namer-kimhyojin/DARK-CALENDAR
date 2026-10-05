# Outlook · Microsoft 365 연결

Air Calendar의 **시스템 → 캘린더 및 동기화 → Outlook · Microsoft 365 연결**에서 설정합니다.
Google 동기화와 별도 연결이며 기존 Google 계정이나 일정은 변경하지 않습니다.

## 최초 Microsoft Entra 앱 등록

앱 개발·배포 관리자가 한 번 등록하고 클라이언트 ID를 제공하는 구조입니다.
사용자가 각자 Entra 앱을 만들어야 하는 것이 아닙니다. 현재는 공용 앱 등록 전이므로
설정 화면에 관리자 등록의 클라이언트 ID를 입력합니다.

1. [Microsoft Entra 관리 센터](https://entra.microsoft.com/)에서 **앱 등록 → 새 등록**을 엽니다.
2. 이름을 `Air Calendar Calendar Sync` 등 Store 제출 자동화 앱과 구분되는 이름으로 입력합니다.
3. 지원 계정 유형은 **모든 조직 디렉터리의 계정 및 개인 Microsoft 계정**을 선택합니다.
4. 등록 후 **인증 → 플랫폼 추가 → 모바일 및 데스크톱 애플리케이션**에서
   `http://localhost` 리디렉션 URI를 등록합니다.
5. **API 권한 → Microsoft Graph → 위임된 권한**에서 `Calendars.ReadWrite`와
   `User.Read`를 추가합니다. 애플리케이션 권한이나 클라이언트 비밀 키는 사용하지 않습니다.
6. 조직 정책에서 요구하면 관리자가 동의합니다. 회사·학교의 MFA/접근 정책은 그대로 적용됩니다.
7. **개요 → 애플리케이션(클라이언트) ID**를 복사합니다. 테넌트 ID와 혼동하지 않습니다.
8. Air Calendar 설정에 ID를 넣고 **Microsoft 로그인**을 누릅니다.
9. 브라우저에서 계정을 선택하고 권한에 동의합니다. 이어서 동기화할 캘린더를 체크하고
   **선택 캘린더 저장 → 지금 동기화**를 누릅니다. 자동 동기화는 별도 체크합니다.

[Microsoft 앱 등록 문서](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app)
와 [MSAL 사용자 인증 문서](https://learn.microsoft.com/en-us/entra/msal/python/getting-started/acquiring-tokens)
를 참고하세요.

## 현재 지원 범위

- 한 개 Microsoft 계정의 여러 캘린더를 선택합니다.
- 일정 조회·생성·수정·삭제와 종일 일정을 지원합니다.
- 지난 120일부터 앞으로 400일까지 조회합니다. 수정된 기존 연결 일정은 범위 밖이어도 ID로 확인합니다.
- 반복 일정은 개별 회차로 표시하고 그 회차를 수정·삭제합니다. 반복 규칙 생성·수정과
  전체 시리즈 변경, 초대 응답, 서비스 간 일정 이동은 별도 후속 구현 대상입니다.
- 양쪽에서 수정된 일정은 충돌 목록에 보존하고 사용자 선택 후 처리합니다.
- 온라인 회의의 제목·시간을 바꿔도 회의 본문을 덮어쓰지 않습니다. 회의 링크 보호를 위해
  온라인 회의 본문 수정은 Outlook에서 진행하도록 안내합니다.
- 원격 삭제는 로컬 일정을 보존하고 문제 목록에 표시합니다. 임의로 다시 올리지 않습니다.
- 로컬 삭제는 DB 삭제 트리거가 원격 삭제 대기열에 기록합니다. 원격 내용이 변경됐으면
  자동 삭제를 보류합니다. 네트워크 실패는 최대 5회 재시도합니다.
  문제 목록에서 삭제 재시도 또는 삭제 취소(Outlook 일정 유지)를 선택할 수 있습니다.
- 토큰 캐시는 Windows 현재 사용자 계정의 DPAPI로 암호화합니다. 암호화 불가 시 평문 저장하지 않습니다.
- 연결 해제는 이 PC의 토큰 캐시를 지우고 해당 캘린더를 비활성화합니다. Microsoft 서버의
  앱 권한 철회는 Microsoft 계정/조직의 앱 관리 화면에서 별도로 할 수 있습니다.

실계정 로그인, 실제 Graph 통신 및 Store 배포판 동작은 앱 등록 후 별도 검증해야 합니다.

## iCloud · 네이버 확장 구조

`application/calendar_sync_contract.py`는 서비스별 어댑터의 공통 계약입니다.
`infrastructure/calendar_sync/`의 엔진·연결 기록·충돌·삭제 대기열은 서비스 공통입니다.
`infrastructure/outlook_sync/`는 Microsoft 인증·Graph 요청·일정 변환만 담당합니다.

CalDAV 어댑터가 같은 계약을 구현해 iCloud와 네이버를 연결합니다.
원격 이벤트는 서비스별로 유일한 `id`, 조건부 수정용 `etag`, 재시도 중복 방지용
`transaction_id`를 제공하고, 서비스별 시간·종일 종료일·반복 회차를 변환합니다.
CalDAV에서는 href/ETag, 서버 검색, 인증 방식과 sync-token 지원 여부를 확인해야 합니다.
공통 엔진을 쓸 수 있다고 해서 서비스별 인증·반복 일정 호환성이 자동 보장되지는 않습니다.

iCloud와 네이버 어댑터와 연결 UI가 구현되었습니다. [CalDAV 설정 안내](caldav_sync_setup.md)를 참고하세요.
실제 계정 검증은 별도이며 Google 기존 엔진은 그대로 유지합니다.
