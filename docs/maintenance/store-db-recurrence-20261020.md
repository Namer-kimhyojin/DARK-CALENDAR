# Store 4.3.3 DB 초기화 오류 재발 조사

조사일: 2026-10-20 (KST). 대상은 실제 설치된 `4.3.3.0`이다.
이 문서는 로컬 복구·소스 수정과 실제 배포 상태를 구분한다.

## 확인한 원인과 한계

| 항목 | 확인 결과 |
|---|---|
| 직접 실패 원인 | Store 사용자 DB가 `SQLITE_CORRUPT` / `database disk image is malformed`로 열리지 않았다. |
| 화면의 일반 오류 | DB 계층이 원래 예외를 `None`/`False`로 바꾸어 bootstrap이 `RuntimeError: Database initialization failed`만 표시했다. |
| 실제 사용자 프로필 | `Packages/Kimhyojin.DarkCalendar_e0fv83qccsz34/LocalCache/Local/kimhyojin/Dark Calendar`이다. 일반 개발 프로필과 별개다. |
| 설치 파일 | 설치 EXE·기본 DB와 `_internal` 1,711개 파일이 공개 4.3.3 MSIX와 일치했다. 패키지 업로드/설치 중 파일이 바뀌었다는 증거는 없다. |
| 실제 SQLite 엔진 | 같은 Store package identity에서 실제 DLL의 C export로 `3.50.4`를 확인했다. |
| 과거 기동 | 10/19 17:38 DB/트레이/워커 초기화와 18:00 정상 종료 로그가 있다. 10/20 09:02 재기동에서 손상이 드러났다. |

손상 DB의 SHA-256은
`58166b6f920787a97a715b30e628a0059e7eaa854e61e551715a4de358959a2f`이다.
오류 창을 닫은 뒤 별도 원본 사본에서 읽기 전용 무결성 검사도 같은 손상을 확인했다.
`desk_calendar.log`는 비어 있고 실제 관련 기록은 `crash.log`에 있었다.

SQLite 3.50.4는 공식 WAL-reset 손상 버그의 영향 범위에 들어간다.
수정판은 3.51.3 이상 및 3.50.7/3.44.6 백포트다. 앱은 WAL과 여러 연결을
사용하므로 재출시 전에 반드시 제거해야 하는 위험이다. 그러나 이 DB가 손상된
순간의 경합 증거는 없어 **이번 손상을 해당 버그 하나로 확정하지 않았다**.
[SQLite 공식 WAL 문서](https://sqlite.org/wal.html#walreset),
[공식 변경 이력 및 3.52.0 철회 안내](https://sqlite.org/changes.html).

읽기 전용 Win32 핸들 조사에서는 Codex 개발 호스트의 일반 AppData DB 본체와
WAL/SHM이 서로 다른 실제 프로필로 해석되는 현상도 확인했다. Store identity에서는
복구 후 세 파일이 같은 Store 폴더에 있었고, 수정한 경로 해석 함수도 그 폴더를
선택했다. 개발 호스트의 현상을 과거 Store 손상의 확정 원인으로 옮겨 말하지 않는다.
기존 per-file legacy DB/WAL 복사에는 일관성 문제가 있었지만, 이번 프로필에는
해당 legacy 폴더가 없어 그 코드가 이번에 실행됐다는 근거도 없다.
[Microsoft MSIX 파일 가상화 문서](https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-behind-the-scenes).

## 이전 검증에서 부족했던 점

1. 이전 4.3.0의 개인 DB 복구와 한 번의 성공 기동이 shipping 결함의 영구 수정으로
   해석될 여지가 있었다. 4.3.3의 실제 설치 후 종료·재시작 증거는 별개여야 했다.
2. frozen 코드/PYZ·기본 DB·파일 해시 검사는 실제 EXE와 동봉 Qt/SQLite의
   새 프로필 및 업그레이드 기동을 대신하지 못했다.
3. 실제 동봉 SQLite C export와 알려진 손상 버그 수정 여부를 검사하지 않았다.
4. 태그 workflow가 검증 후보를 바로 공개하고 기존 release assets에 `--clobber`를
   사용할 수 있었다. 실제 기동 게이트 이전의 공개와 파일 교체를 막지 못했다.
5. Store 인증 실패 시 기본 현황까지 잃었고, 설치된 버전·기동·서버 게시 상태를
   독립적으로 판정할 도구가 부족했다.

## 이번 변경

- DB 경로: 실제 열린 main DB의 Windows 물리 경로를 고정한다. 기존 DB에는 legacy
  sidecar를 섞지 않는다. 신규 legacy/default DB는 SQLite backup API로 일관된 사본을
  만들고 검사한 뒤 기존 목적지를 덮어쓰지 않는 방식으로 게시한다. 손상·권한 오류가
  나면 원본을 보존하며 기본 DB로 조용히 대체하지 않는다.
- 시작 오류: DB 초기화 호출에서 원래 SQLite 오류를 보존한다. PID·앱 버전·SQLite·DB
  경로를 기록하고, 손상/잠금/접근 실패를 구분하는 번역 가능한 안내를 표시한 뒤
  기존 종료 정리를 수행한다. import 중 DB 준비 실패도 처리한다.
- 빌드: 선택한 Python과 최종 frozen payload 각각의 실제 SQLite C export·경로·PE
  architecture를 검사한다. 3.50.4, 철회된 3.52.0, 미확인 런타임은 차단한다.
- GitHub: 태그 workflow가 draft 후보만 생성한다. 공개 릴리스 교체를 거부하고,
  draft 재시도에는 동일 이름 파일을 다운로드해 현재 빌드와 SHA-256을 대조한 뒤
  누락 자산만 추가한다. 불일치하면 교체·혼합 없이 중단한다. native 검증 후 동일 후보를 공개한다.
- 배포 스킬: 새/업그레이드 격리 환경 각각에서 실제 EXE의 정상 종료→재시작을
  두 번 확인하도록 했다. QSettings·공유 DB 격리, 물리 DB/WAL/SHM 경로,
  원본 보존 및 SQLite 수정판 확인을 별도 필수 증거로 명시했다.
- 설치 관찰 helper: 목표 버전·PID·기동 시각·실제 프로필의 새 DB/트레이/워커 로그를
  연결한다. 예외 창, native fatal, 손상 조회 오류, 오래된 성공 로그를 통과시키지
  않는다. 이 도구는 DB를 열거나 앱을 실행·종료하지 않으며 전체 배포 완료를 선언하지 않는다.
- Store 점검: 인증 실패에도 기본 개발·설치 현황은 반환하고 서버 상태를 미확인으로 남긴다.

경로 수정은 기존 Store private DB를 선택하는 경우를 동일 identity에서 확인했다.
일반 AppData를 사용하는 다른 가상화 호스트의 신규 sidecar 생성까지 모든 환경에서
해결했다고 단정하지 않는다. backup snapshot의 원자적 게시는 hardlink를 지원하는
파일시스템이 필요하며 미지원이면 원본을 보존하고 실패한다.

## 현재 PC 복구 결과

사용자가 오류 창을 닫은 뒤 프로세스 종료와 원본 해시를 확인했다. 원본 DB와
복구 SQL은 저장소 밖 사용자 전용 폴더에 보관했다. `.recover` 결과에서 스키마 및
분류 가능한 기본 캘린더 행을 재구성하고, 후보의 integrity/FK 검사를 통과한 뒤
09:19:30에 원자 교체했다. 읽을 수 없었던 원본의 모든 과거 일정이 복구됐다고
보증할 수는 없다. 분류된 복구 결과는 일정 0건·캘린더 1건이다.

복구 후보 SHA-256:
`16fb9776a180878ec429ee27ef7f7a11d91a2725d233be522d7c1ec6fb7dc576`.

공식 설치 앱을 실행해 PID `43380`, 실제 WindowsApps 4.3.3 경로, 창 제목
`Air Calendar`와 09:19:31 DB 초기화·09:19:33 트레이/워커 시작 로그를 확인했다.
native UI 표면을 사용할 수 없어 실제 화면·사용자 데이터 육안 검사는 미완료다.
사용 중인 앱을 추가로 강제 종료하거나 반복 실행하지 않았다.

**설치된 4.3.3은 여전히 SQLite 3.50.4를 포함한다. 이번 로컬 복구는 임시 기동 복구이며,
수정 소스나 안전한 SQLite가 사용자에게 배포된 결과가 아니다.**

## 검증과 남은 단계

개인 프로필·QSettings·SQLite 경로를 격리한 회귀 검사의 상세 결과는
`artifacts/maintenance/20261020-store-db-incident/focused-regressions.xml`에 둔다.
인코딩 guard, Ruff, i18n 구조 검사도 수행했다. 스킬 fixture와 workflow의 stub-gh
회귀 검사는 실제 Store 기동 검증과 구분해 같은 증거 폴더에 기록한다.

다음 출시에는 안전한 실제 Python/SQLite 런타임 준비, 최종 payload 재빌드,
격리된 새/업그레이드 프로필의 native UI·종료·재시작 검증이 필요하다.
현재 Python 3.13.15의 SQLite 3.50.4는 새 preflight에서 차단되는 것이 올바른 결과다.
기존 공개 4.3.3 파일·태그·Store 제출을 교체하거나 새 버전을 게시하지 않았다.
Partner Center 서버 상태도 이 조사에서 재확인하지 않았으므로 과거 제출 상태를
현재 게시 상태로 올리지 않는다.
