# Air Calendar 파일별 코드 점검 · 2026-10-08

Python 운영·도구 소스 **329개 파일, 133,529줄**을 정적 점검했습니다. 관련 함수·호출부·입력/예외 흐름의 상세 검토는 **132개 파일**에서 수행했고, 나머지 **197개**는 정적 검사 수준입니다. 아래 파일별 표와 JSON에서 실제 검토 깊이를 구분합니다. 전체 실행 분기에서 오류가 없다는 보장은 아닙니다.

확인된 오류와 검사 도구 문제를 **39개 Python 소스 파일**에서 수정했습니다. 기존 작업 트리의 변경분을 보존했고, 수정은 입력 검증·예외 복구·저장 및 종료 경계에 한정했습니다.

## 확인한 문제와 개선

| 영역 | 문제와 개선 |
|---|---|
| 태스크·날짜 검증 | 문자열 `false`를 완료/종일로 해석하던 문제, 잘못된 시간이나 날짜 접미사를 자정/날짜로 잘라 수용하던 문제, 무한대·분수·과대 ID를 수정했습니다. 잘못된 쓰기를 거부하여 기존 일정 날짜를 보존합니다. |
| 공유 DB | 스키마 초기화 실패 연결을 닫고, 쓰기 실패를 롤백합니다. 부분 변경이 다음 성공한 쓰기로 확정되는 상황을 막습니다. |
| Google·CalDAV | 기본 기간과 일정 날짜의 DST를 적용합니다. 재시도 생성 ID를 안정화하고 409 응답의 실제 원격 내용을 확인합니다. 누락 callback과 로컬 저장 실패를 성공으로 집계하지 않습니다. 제목·날짜만 같은 로컬 행의 소유권을 추측해 바꾸던 경로를 제거했습니다. 해석할 수 없는 TZID는 명시적 오류로 처리합니다. |
| 설정·UI | 손상된 날짜·글꼴·굵기·투명도·잠금 설정과 창 위치/도킹 상태를 안전하게 복구합니다. 종료 후 큐에 남은 화면 갱신을 차단하고, 계정 상태 갱신 시 목록 위치를 보존합니다. |
| 위젯·알림 | 잘못된 색상·타입·좌표·크기·시간대·스톱워치·카운트다운 저장값을 처리합니다. 과대한 알람/다시 알림 값, NUL 이미지 경로, 날씨 숫자 오버플로를 복구하고 종료 시 첫 알람 타이머를 취소합니다. |
| 검사 도구 | 실제 소스 디렉터리와 루트 Python 파일만 컴파일합니다. 테스트가 의도적으로 만든 잘못된 임시 소스를 다시 검사하여 품질 검사가 실패하던 문제를 해결했습니다. |

## 검증

- 현재 테스트 파일 **217개**를 파일별 별도 프로세스에서 검사한 최종 결과: **3,930개 통과**, 실패 0, 오류 0, 건너뜀 0.
- 이번에 추가한 경계 회귀 사례 **155개** 포함. 초기 실패를 보존하고 수정 후 통과를 확인했습니다.
- 329개 소스 UTF-8/AST/compile 검사 및 전체 운영 코드의 주요 Ruff 오류 검사 통과. 수정한 39개 소스의 전체 Ruff·공백 검사 통과.
- 공식 인코딩 guard: 실제 소스 compileall 및 정책/유틸 테스트 **12개 통과**.
- UI 범위 **89개 모듈 import 통과**. Qt offscreen에서 기존 렌더링·상호작용 회귀 검사 포함.
- **19개 언어 파일**의 키 구조·타입·치환 변수·깨진 문자열 검사 통과. ko/en은 현재 canonical 직렬화로 서식만 정리했으며 파싱된 값의 동일성을 확인했습니다.

Google 인증 테스트 2개 파일의 fake/인라인 오류 안내/버튼 상태, 테마 규칙 문서 위치·지원 별칭, 날씨 갤러리의 폰트 의존 픽셀 좌표, 프리셋 fake의 스톱워치 파서를 실제 계약과 맞췄습니다. 색상·메시지·저장 동작의 기존 판정은 유지했습니다.

테스트는 설치된 CPython 3.13.14와 프로젝트 PyQt6 6.10.2 패키지로 실행했습니다. QSettings는 임시 INI, APPDATA/LOCALAPPDATA/TEMP 및 DB는 임시 경로로 격리했습니다. 현재 `.venv`는 삭제된 Python 3.13.15 경로를 가리켜 자체 실행이 실패합니다. 환경 복구 시도는 적용하지 않고 원래 pyvenv.cfg를 복원했으며 이 개발 환경 문제는 남아 있습니다.

전체 회귀 검사는 217개 파일을 한 프로세스에서 실행한 결과가 아니라 파일별 격리 결과의 합입니다. 최초 180초 제한에 걸린 두 UI 파일은 더 긴 제한으로 재검사하여 각각 46개·47개 모두 통과했습니다. 중간 집계기의 timeout 출력 처리 오류는 수정했고, 최종 집계는 현재 존재하는 테스트 파일별 최신 완전한 JUnit만 사용했습니다.

실제 계정·사용자 DB/레지스트리·날씨 실통신·물리 데스크톱 장시간 조작·빌드·설치·Store 검증은 이번 범위에 포함하지 않았습니다. 기존 TASKS.md의 수동 검증 항목을 완료로 바꾸지 않았습니다.

## 증거와 재현

- [최종 검사 집계](../../artifacts/code-audit-20261008/final-summary.json) · [테스트 파일별 JUnit 경로](../../artifacts/code-audit-20261008/final-test-results.json)
- [329개 파일 상세 JSON](../../artifacts/code-audit-20261008/file-review.json) · [파일 목록 CSV](../../artifacts/code-audit-20261008/file-review.csv)
- [동기화 검토](../../artifacts/code-audit-20261008/sync-review.md) · [UI 검토](../../artifacts/code-audit-20261008/ui-review.md) · [위젯·테마 검토](../../artifacts/code-audit-20261008/widgets-review.md)
- [인코딩 guard](../../artifacts/code-audit-20261008/encoding-guard-final.txt) · [전체 주요 Ruff](../../artifacts/code-audit-20261008/ruff-runtime-final.json) · [수정 소스 Ruff](../../artifacts/code-audit-20261008/ruff-changes-final.json) · [언어 검사](../../artifacts/code-audit-20261008/locale-structure.txt)
- [격리 테스트 실행기](../../artifacts/code-audit-20261008/run_file_tests.py), [구문·파일 인벤토리](../../artifacts/code-audit-20261008/audit_inventory.py), [최종 집계기](../../artifacts/code-audit-20261008/finalize_audit.py). Python 3.13에서 프로젝트 site-packages를 PYTHONPATH로 지정하고 실행합니다.

동기화 개별 보고서의 533개 최초 실행 중 진단 fake 1건 실패는 후속 UI 회귀에서 해결되었습니다. 초기 실패 증거를 덮어쓰지 않았으며 최종 성공 결과는 위 집계와 JUnit 경로를 기준으로 합니다.

## 파일별 점검 범위

`상세`는 관련 함수·호출부·예외 경계를 읽은 파일, `정적`은 전체 소스 구문과 위험 패턴 검사, `정적+import`는 모듈 로딩까지 확인한 파일입니다. 상세 파일도 모든 UI 상태나 실행 분기를 검증한 것은 아닙니다. 구문 검사는 전 파일 통과했으며, 추가 수정 여부와 실제 소스 해시는 JSON/CSV에 기록했습니다.

| 파일 | 줄 | 검토 수준 | 이번 수정 |
|---|---:|---|---|
| [build_store.py](<D:/00. Dev_Folder/Dark Calendar/build_store.py>) | 462 | 정적 | — |
| [calendar_app/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/__init__.py>) | 1 | 정적 | — |
| [calendar_app/app_metadata.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/app_metadata.py>) | 25 | 정적 | — |
| [calendar_app/app_paths.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/app_paths.py>) | 141 | 정적 | — |
| [calendar_app/application/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/application/__init__.py>) | 1 | 정적 | — |
| [calendar_app/application/calendar_preferences.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/application/calendar_preferences.py>) | 52 | 정적 | — |
| [calendar_app/application/calendar_print_service.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/application/calendar_print_service.py>) | 405 | 정적 | — |
| [calendar_app/application/calendar_sync_contract.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/application/calendar_sync_contract.py>) | 29 | 정적 | — |
| [calendar_app/application/common_status_usecases.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/application/common_status_usecases.py>) | 25 | 정적 | — |
| [calendar_app/application/common_task_ops_usecases.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/application/common_task_ops_usecases.py>) | 40 | 정적 | — |
| [calendar_app/application/directive_management_usecases.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/application/directive_management_usecases.py>) | 101 | 정적 | — |
| [calendar_app/application/eod_usecases.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/application/eod_usecases.py>) | 50 | 정적 | — |
| [calendar_app/application/focus_usecases.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/application/focus_usecases.py>) | 292 | 정적 | — |
| [calendar_app/application/pomodoro_engine.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/application/pomodoro_engine.py>) | 189 | 정적 | — |
| [calendar_app/application/review_usecases.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/application/review_usecases.py>) | 179 | 정적 | — |
| [calendar_app/application/routine_advanced_service.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/application/routine_advanced_service.py>) | 339 | 정적 | — |
| [calendar_app/application/routine_batch_generator.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/application/routine_batch_generator.py>) | 101 | 정적 | — |
| [calendar_app/application/routine_management_usecases.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/application/routine_management_usecases.py>) | 39 | 정적 | — |
| [calendar_app/application/routine_usecases.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/application/routine_usecases.py>) | 39 | 정적 | — |
| [calendar_app/application/task_delete_usecases.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/application/task_delete_usecases.py>) | 113 | 정적 | — |
| [calendar_app/application/task_dialog_usecases.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/application/task_dialog_usecases.py>) | 20 | 정적 | — |
| [calendar_app/application/task_management_usecases.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/application/task_management_usecases.py>) | 108 | 정적 | — |
| [calendar_app/application/task_usecases.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/application/task_usecases.py>) | 210 | 정적 | — |
| [calendar_app/application/week_planner_usecases.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/application/week_planner_usecases.py>) | 252 | 정적 | — |
| [calendar_app/bootstrap.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/bootstrap.py>) | 469 | 상세 | 수정·검증 |
| [calendar_app/domain/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/domain/__init__.py>) | 1 | 정적 | — |
| [calendar_app/domain/calendar_visibility.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/domain/calendar_visibility.py>) | 96 | 정적 | — |
| [calendar_app/domain/date_range.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/domain/date_range.py>) | 38 | 정적 | — |
| [calendar_app/domain/i18n.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/domain/i18n.py>) | 44 | 정적 | — |
| [calendar_app/domain/models/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/domain/models/__init__.py>) | 4 | 정적 | — |
| [calendar_app/domain/policies/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/domain/policies/__init__.py>) | 1 | 정적 | — |
| [calendar_app/domain/policies/routine_policy.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/domain/policies/routine_policy.py>) | 186 | 정적 | — |
| [calendar_app/domain/routine_cycle.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/domain/routine_cycle.py>) | 60 | 정적 | — |
| [calendar_app/domain/services/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/domain/services/__init__.py>) | 4 | 정적 | — |
| [calendar_app/domain/task_constants.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/domain/task_constants.py>) | 338 | 정적 | — |
| [calendar_app/domain/task_status_view.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/domain/task_status_view.py>) | 41 | 정적 | — |
| [calendar_app/domain/task_validation.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/domain/task_validation.py>) | 283 | 상세 | 수정·검증 |
| [calendar_app/infrastructure/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/__init__.py>) | 1 | 정적 | — |
| [calendar_app/infrastructure/caldav_sync/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/caldav_sync/__init__.py>) | 2 | 상세 | — |
| [calendar_app/infrastructure/caldav_sync/client.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/caldav_sync/client.py>) | 457 | 상세 | — |
| [calendar_app/infrastructure/caldav_sync/conversion.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/caldav_sync/conversion.py>) | 247 | 상세 | 수정·검증 |
| [calendar_app/infrastructure/caldav_sync/credentials.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/caldav_sync/credentials.py>) | 54 | 상세 | — |
| [calendar_app/infrastructure/caldav_sync/profiles.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/caldav_sync/profiles.py>) | 54 | 상세 | — |
| [calendar_app/infrastructure/caldav_sync/resource_cache.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/caldav_sync/resource_cache.py>) | 50 | 상세 | — |
| [calendar_app/infrastructure/calendar_sync/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/calendar_sync/__init__.py>) | 2 | 상세 | — |
| [calendar_app/infrastructure/calendar_sync/engine.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/calendar_sync/engine.py>) | 465 | 상세 | — |
| [calendar_app/infrastructure/calendar_sync/http_retry.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/calendar_sync/http_retry.py>) | 26 | 상세 | — |
| [calendar_app/infrastructure/calendar_sync/repository.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/calendar_sync/repository.py>) | 291 | 상세 | — |
| [calendar_app/infrastructure/calendar_sync/secret_store.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/calendar_sync/secret_store.py>) | 29 | 상세 | — |
| [calendar_app/infrastructure/db/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/__init__.py>) | 1 | 정적 | — |
| [calendar_app/infrastructure/db/_adapter_proxy.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/_adapter_proxy.py>) | 15 | 정적 | — |
| [calendar_app/infrastructure/db/calendar_print_repository.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/calendar_print_repository.py>) | 100 | 정적 | — |
| [calendar_app/infrastructure/db/calendar_repo.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/calendar_repo.py>) | 683 | 정적 | — |
| [calendar_app/infrastructure/db/checklist_repo.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/checklist_repo.py>) | 21 | 정적 | — |
| [calendar_app/infrastructure/db/checklist_repository.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/checklist_repository.py>) | 1062 | 정적 | — |
| [calendar_app/infrastructure/db/checklist_template_repo.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/checklist_template_repo.py>) | 1064 | 정적 | — |
| [calendar_app/infrastructure/db/common_repo.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/common_repo.py>) | 17 | 정적 | — |
| [calendar_app/infrastructure/db/database_unified.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/database_unified.py>) | 1537 | 정적 | — |
| [calendar_app/infrastructure/db/db_repository.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/db_repository.py>) | 2015 | 정적 | — |
| [calendar_app/infrastructure/db/db_repository_unified.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/db_repository_unified.py>) | 2467 | 상세 | 수정·검증 |
| [calendar_app/infrastructure/db/directive_repo.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/directive_repo.py>) | 414 | 정적 | — |
| [calendar_app/infrastructure/db/legacy_focus_repo.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/legacy_focus_repo.py>) | 22 | 정적 | — |
| [calendar_app/infrastructure/db/legacy_report_repo.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/legacy_report_repo.py>) | 14 | 정적 | — |
| [calendar_app/infrastructure/db/legacy_routine_repo.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/legacy_routine_repo.py>) | 15 | 정적 | — |
| [calendar_app/infrastructure/db/legacy_task_repo.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/legacy_task_repo.py>) | 17 | 정적 | — |
| [calendar_app/infrastructure/db/legacy_ui_repo.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/legacy_ui_repo.py>) | 59 | 정적 | — |
| [calendar_app/infrastructure/db/period_utils.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/period_utils.py>) | 105 | 정적 | — |
| [calendar_app/infrastructure/db/routine_repo.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/routine_repo.py>) | 20 | 정적 | — |
| [calendar_app/infrastructure/db/search_repo.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/search_repo.py>) | 17 | 정적 | — |
| [calendar_app/infrastructure/db/shared_db.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/shared_db.py>) | 289 | 상세 | 수정·검증 |
| [calendar_app/infrastructure/db/task_repo.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/task_repo.py>) | 17 | 정적 | — |
| [calendar_app/infrastructure/db/unified_repo.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/db/unified_repo.py>) | 65 | 정적 | — |
| [calendar_app/infrastructure/google_sync/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/google_sync/__init__.py>) | 56 | 상세 | — |
| [calendar_app/infrastructure/google_sync/common.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/google_sync/common.py>) | 281 | 상세 | 수정·검증 |
| [calendar_app/infrastructure/google_sync/engine.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/google_sync/engine.py>) | 2322 | 상세 | 수정·검증 |
| [calendar_app/infrastructure/google_sync/helpers.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/google_sync/helpers.py>) | 641 | 상세 | 수정·검증 |
| [calendar_app/infrastructure/google_sync/oauth.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/google_sync/oauth.py>) | 116 | 상세 | 수정·검증 |
| [calendar_app/infrastructure/google_sync/push_queue.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/google_sync/push_queue.py>) | 231 | 상세 | — |
| [calendar_app/infrastructure/google_sync/repository.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/google_sync/repository.py>) | 564 | 상세 | — |
| [calendar_app/infrastructure/google_sync/service.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/google_sync/service.py>) | 1756 | 상세 | 수정·검증 |
| [calendar_app/infrastructure/google_sync/token_store.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/google_sync/token_store.py>) | 113 | 상세 | — |
| [calendar_app/infrastructure/i18n.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/i18n.py>) | 412 | 정적 | — |
| [calendar_app/infrastructure/ics/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/ics/__init__.py>) | 0 | 상세 | — |
| [calendar_app/infrastructure/ics/ics_fetcher.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/ics/ics_fetcher.py>) | 444 | 상세 | — |
| [calendar_app/infrastructure/ics/subscriptions.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/ics/subscriptions.py>) | 70 | 상세 | — |
| [calendar_app/infrastructure/nlp/nlp_engine.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/nlp/nlp_engine.py>) | 143 | 정적 | — |
| [calendar_app/infrastructure/outlook_sync/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/outlook_sync/__init__.py>) | 2 | 상세 | — |
| [calendar_app/infrastructure/outlook_sync/auth.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/outlook_sync/auth.py>) | 101 | 상세 | — |
| [calendar_app/infrastructure/outlook_sync/conversion.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/outlook_sync/conversion.py>) | 101 | 상세 | — |
| [calendar_app/infrastructure/outlook_sync/graph.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/outlook_sync/graph.py>) | 225 | 상세 | — |
| [calendar_app/infrastructure/runtime/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/runtime/__init__.py>) | 1 | 정적 | — |
| [calendar_app/infrastructure/runtime/app_bar_handler.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/runtime/app_bar_handler.py>) | 124 | 정적 | — |
| [calendar_app/infrastructure/runtime/crash_bootstrap.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/runtime/crash_bootstrap.py>) | 92 | 정적 | — |
| [calendar_app/infrastructure/runtime/hotkey_sender.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/runtime/hotkey_sender.py>) | 153 | 정적 | — |
| [calendar_app/infrastructure/runtime/idle_detector.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/runtime/idle_detector.py>) | 171 | 정적 | — |
| [calendar_app/infrastructure/runtime/infra_manager.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/runtime/infra_manager.py>) | 11 | 정적 | — |
| [calendar_app/infrastructure/runtime/infra_wiring.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/runtime/infra_wiring.py>) | 468 | 정적 | — |
| [calendar_app/infrastructure/runtime/keyboard_shortcuts.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/runtime/keyboard_shortcuts.py>) | 1142 | 정적 | — |
| [calendar_app/infrastructure/runtime/launcher_asset_store.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/runtime/launcher_asset_store.py>) | 40 | 정적 | — |
| [calendar_app/infrastructure/runtime/network.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/runtime/network.py>) | 34 | 정적 | — |
| [calendar_app/infrastructure/runtime/system_manager.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/runtime/system_manager.py>) | 227 | 정적 | — |
| [calendar_app/infrastructure/sync/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/sync/__init__.py>) | 3 | 상세 | — |
| [calendar_app/infrastructure/sync/calendar_sync_service.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/sync/calendar_sync_service.py>) | 3 | 상세 | — |
| [calendar_app/infrastructure/sync/gcal_db_adapter.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/sync/gcal_db_adapter.py>) | 3 | 상세 | — |
| [calendar_app/infrastructure/sync/gcal_sync_helpers.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/sync/gcal_sync_helpers.py>) | 14 | 상세 | — |
| [calendar_app/infrastructure/sync/sync_handlers.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/sync/sync_handlers.py>) | 3 | 상세 | — |
| [calendar_app/infrastructure/task_drop_service.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/task_drop_service.py>) | 301 | 정적 | — |
| [calendar_app/infrastructure/weather/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/weather/__init__.py>) | 7 | 정적 | — |
| [calendar_app/infrastructure/weather/geonames.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/weather/geonames.py>) | 102 | 정적 | — |
| [calendar_app/infrastructure/weather/met_norway.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/infrastructure/weather/met_norway.py>) | 115 | 정적 | — |
| [calendar_app/presentation/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/__init__.py>) | 1 | 정적 | — |
| [calendar_app/presentation/calendar/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/calendar/__init__.py>) | 5 | 상세 | — |
| [calendar_app/presentation/calendar/calendar_controls.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/calendar/calendar_controls.py>) | 303 | 정적+import | — |
| [calendar_app/presentation/calendar/month_renderer.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/calendar/month_renderer.py>) | 2726 | 정적+import | — |
| [calendar_app/presentation/calendar/week_planner_controller.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/calendar/week_planner_controller.py>) | 158 | 상세 | — |
| [calendar_app/presentation/calendar/week_time_grid.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/calendar/week_time_grid.py>) | 1035 | 정적+import | — |
| [calendar_app/presentation/context_menu_manager.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/context_menu_manager.py>) | 485 | 정적 | — |
| [calendar_app/presentation/dialogs/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/__init__.py>) | 15 | 상세 | — |
| [calendar_app/presentation/dialogs/away_settings_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/away_settings_dialog.py>) | 1133 | 상세 | 수정·검증 |
| [calendar_app/presentation/dialogs/caldav_settings_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/caldav_settings_dialog.py>) | 701 | 상세 | — |
| [calendar_app/presentation/dialogs/calendar_manager_page.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/calendar_manager_page.py>) | 890 | 상세 | 수정·검증 |
| [calendar_app/presentation/dialogs/calendar_print_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/calendar_print_dialog.py>) | 700 | 상세 | — |
| [calendar_app/presentation/dialogs/calendar_sync_hub.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/calendar_sync_hub.py>) | 749 | 상세 | — |
| [calendar_app/presentation/dialogs/calendar_sync_style.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/calendar_sync_style.py>) | 79 | 정적+import | — |
| [calendar_app/presentation/dialogs/checklist_manager_dialog_advanced.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/checklist_manager_dialog_advanced.py>) | 1498 | 정적+import | — |
| [calendar_app/presentation/dialogs/color_swatch_widget.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/color_swatch_widget.py>) | 449 | 정적+import | — |
| [calendar_app/presentation/dialogs/daily_summary_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/daily_summary_dialog.py>) | 975 | 정적+import | — |
| [calendar_app/presentation/dialogs/dialog_editor_styles.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/dialog_editor_styles.py>) | 856 | 정적+import | — |
| [calendar_app/presentation/dialogs/dialog_emoji.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/dialog_emoji.py>) | 19 | 상세 | — |
| [calendar_app/presentation/dialogs/dialog_router.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/dialog_router.py>) | 457 | 상세 | — |
| [calendar_app/presentation/dialogs/dialog_styles.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/dialog_styles.py>) | 1781 | 정적+import | — |
| [calendar_app/presentation/dialogs/dialog_token_editor_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/dialog_token_editor_dialog.py>) | 1956 | 정적+import | — |
| [calendar_app/presentation/dialogs/directive_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/directive_dialog.py>) | 469 | 상세 | — |
| [calendar_app/presentation/dialogs/eod_report_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/eod_report_dialog.py>) | 98 | 상세 | — |
| [calendar_app/presentation/dialogs/focus_completion_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/focus_completion_dialog.py>) | 292 | 정적+import | — |
| [calendar_app/presentation/dialogs/focus_history_panel.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/focus_history_panel.py>) | 246 | 정적+import | — |
| [calendar_app/presentation/dialogs/focus_log_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/focus_log_dialog.py>) | 80 | 정적+import | — |
| [calendar_app/presentation/dialogs/focus_task_selector.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/focus_task_selector.py>) | 425 | 정적+import | — |
| [calendar_app/presentation/dialogs/gcal_auth_worker.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/gcal_auth_worker.py>) | 95 | 상세 | — |
| [calendar_app/presentation/dialogs/gcal_settings_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/gcal_settings_dialog.py>) | 2448 | 상세 | — |
| [calendar_app/presentation/dialogs/gcal_sync_issues_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/gcal_sync_issues_dialog.py>) | 1153 | 정적+import | — |
| [calendar_app/presentation/dialogs/help_center_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/help_center_dialog.py>) | 932 | 정적+import | — |
| [calendar_app/presentation/dialogs/ics_subscription_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/ics_subscription_dialog.py>) | 374 | 정적+import | — |
| [calendar_app/presentation/dialogs/label_settings_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/label_settings_dialog.py>) | 1051 | 정적+import | — |
| [calendar_app/presentation/dialogs/management_dialogs.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/management_dialogs.py>) | 1221 | 정적+import | — |
| [calendar_app/presentation/dialogs/modify_task_dialog_unified.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/modify_task_dialog_unified.py>) | 18 | 상세 | — |
| [calendar_app/presentation/dialogs/outlook_settings_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/outlook_settings_dialog.py>) | 728 | 상세 | — |
| [calendar_app/presentation/dialogs/panel_color_picker_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/panel_color_picker_dialog.py>) | 3245 | 정적+import | — |
| [calendar_app/presentation/dialogs/pomodoro_settings_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/pomodoro_settings_dialog.py>) | 442 | 정적+import | — |
| [calendar_app/presentation/dialogs/provider_settings_widgets.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/provider_settings_widgets.py>) | 109 | 정적+import | — |
| [calendar_app/presentation/dialogs/recurring_event_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/recurring_event_dialog.py>) | 114 | 상세 | — |
| [calendar_app/presentation/dialogs/routine_bulk_operations_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/routine_bulk_operations_dialog.py>) | 654 | 정적+import | — |
| [calendar_app/presentation/dialogs/routine_modify_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/routine_modify_dialog.py>) | 585 | 정적+import | — |
| [calendar_app/presentation/dialogs/routine_recurrence_wizard.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/routine_recurrence_wizard.py>) | 476 | 정적+import | — |
| [calendar_app/presentation/dialogs/sync_feedback.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/sync_feedback.py>) | 367 | 상세 | — |
| [calendar_app/presentation/dialogs/sync_recovery.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/sync_recovery.py>) | 71 | 상세 | — |
| [calendar_app/presentation/dialogs/task_dialog_base.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/task_dialog_base.py>) | 1060 | 상세 | 수정·검증 |
| [calendar_app/presentation/dialogs/task_dialog_unified.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/task_dialog_unified.py>) | 2219 | 상세 | — |
| [calendar_app/presentation/dialogs/time_picker_widget.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/time_picker_widget.py>) | 225 | 정적+import | — |
| [calendar_app/presentation/dialogs/widget_customization_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/widget_customization_dialog.py>) | 964 | 상세 | 수정·검증 |
| [calendar_app/presentation/dialogs/widget_free_layout_editor.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/widget_free_layout_editor.py>) | 1048 | 상세 | — |
| [calendar_app/presentation/dialogs/widget_style_editor_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/dialogs/widget_style_editor_dialog.py>) | 138 | 정적+import | — |
| [calendar_app/presentation/drag_drop_manager.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/drag_drop_manager.py>) | 208 | 정적 | — |
| [calendar_app/presentation/focus_mode.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/focus_mode.py>) | 1253 | 정적 | — |
| [calendar_app/presentation/layout_manager.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/layout_manager.py>) | 62 | 정적 | — |
| [calendar_app/presentation/main_window/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/__init__.py>) | 32 | 상세 | — |
| [calendar_app/presentation/main_window/action_handlers.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/action_handlers.py>) | 538 | 상세 | — |
| [calendar_app/presentation/main_window/action_handlers_gcal.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/action_handlers_gcal.py>) | 986 | 정적+import | — |
| [calendar_app/presentation/main_window/action_handlers_tasks.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/action_handlers_tasks.py>) | 779 | 상세 | — |
| [calendar_app/presentation/main_window/app_initializer.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/app_initializer.py>) | 278 | 상세 | 수정·검증 |
| [calendar_app/presentation/main_window/app_window.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/app_window.py>) | 122 | 상세 | — |
| [calendar_app/presentation/main_window/away_lock_actions.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/away_lock_actions.py>) | 1202 | 상세 | 수정·검증 |
| [calendar_app/presentation/main_window/caldav_sync_controller.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/caldav_sync_controller.py>) | 316 | 정적+import | — |
| [calendar_app/presentation/main_window/calendar_sync_actions.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/calendar_sync_actions.py>) | 44 | 상세 | — |
| [calendar_app/presentation/main_window/calendar_sync_coordinator.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/calendar_sync_coordinator.py>) | 580 | 정적+import | — |
| [calendar_app/presentation/main_window/calendar_view_actions.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/calendar_view_actions.py>) | 313 | 상세 | — |
| [calendar_app/presentation/main_window/dock_factory.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/dock_factory.py>) | 131 | 정적+import | — |
| [calendar_app/presentation/main_window/dock_sections/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/dock_sections/__init__.py>) | 14 | 상세 | — |
| [calendar_app/presentation/main_window/dock_sections/dock_layout_presets.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/dock_sections/dock_layout_presets.py>) | 283 | 정적+import | — |
| [calendar_app/presentation/main_window/dock_sections/floating_dock_behavior.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/dock_sections/floating_dock_behavior.py>) | 237 | 정적+import | — |
| [calendar_app/presentation/main_window/dock_sections/left_center_docks.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/dock_sections/left_center_docks.py>) | 64 | 상세 | — |
| [calendar_app/presentation/main_window/dock_sections/right_docks.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/dock_sections/right_docks.py>) | 64 | 상세 | — |
| [calendar_app/presentation/main_window/first_run_banner.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/first_run_banner.py>) | 162 | 정적+import | — |
| [calendar_app/presentation/main_window/idle_lock_ui_builder.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/idle_lock_ui_builder.py>) | 96 | 정적+import | — |
| [calendar_app/presentation/main_window/outlook_sync_controller.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/outlook_sync_controller.py>) | 297 | 정적+import | — |
| [calendar_app/presentation/main_window/refresh_scheduler.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/refresh_scheduler.py>) | 152 | 상세 | 수정·검증 |
| [calendar_app/presentation/main_window/routine_actions.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/routine_actions.py>) | 50 | 상세 | — |
| [calendar_app/presentation/main_window/theme_actions.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/theme_actions.py>) | 404 | 정적+import | — |
| [calendar_app/presentation/main_window/top_bar_builder.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/top_bar_builder.py>) | 300 | 정적+import | — |
| [calendar_app/presentation/main_window/top_bar_menu_factory.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/top_bar_menu_factory.py>) | 36 | 상세 | — |
| [calendar_app/presentation/main_window/top_menus/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/top_menus/__init__.py>) | 15 | 상세 | — |
| [calendar_app/presentation/main_window/top_menus/common.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/top_menus/common.py>) | 59 | 상세 | — |
| [calendar_app/presentation/main_window/top_menus/display_menu.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/top_menus/display_menu.py>) | 402 | 정적+import | — |
| [calendar_app/presentation/main_window/top_menus/register_menu.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/top_menus/register_menu.py>) | 41 | 상세 | — |
| [calendar_app/presentation/main_window/top_menus/system_menu.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/top_menus/system_menu.py>) | 165 | 정적+import | — |
| [calendar_app/presentation/main_window/top_menus/widgets_menu.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/top_menus/widgets_menu.py>) | 50 | 상세 | — |
| [calendar_app/presentation/main_window/top_menus/work_menu.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/top_menus/work_menu.py>) | 46 | 정적+import | — |
| [calendar_app/presentation/main_window/ui_builder.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/ui_builder.py>) | 139 | 정적+import | — |
| [calendar_app/presentation/main_window/window_events.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/window_events.py>) | 533 | 상세 | — |
| [calendar_app/presentation/main_window/window_restore_helpers.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/window_restore_helpers.py>) | 256 | 상세 | 수정·검증 |
| [calendar_app/presentation/main_window/window_shell_actions.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/window_shell_actions.py>) | 683 | 정적+import | — |
| [calendar_app/presentation/main_window/window_ui_actions.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/main_window/window_ui_actions.py>) | 875 | 상세 | 수정·검증 |
| [calendar_app/presentation/panels/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/panels/__init__.py>) | 5 | 상세 | — |
| [calendar_app/presentation/panels/side_panel_renderer.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/panels/side_panel_renderer.py>) | 2043 | 상세 | — |
| [calendar_app/presentation/printing/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/printing/__init__.py>) | 2 | 정적 | — |
| [calendar_app/presentation/printing/calendar_print_renderer.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/printing/calendar_print_renderer.py>) | 946 | 정적 | — |
| [calendar_app/presentation/splash_screen.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/splash_screen.py>) | 269 | 정적 | — |
| [calendar_app/presentation/theme/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/theme/__init__.py>) | 27 | 상세 | — |
| [calendar_app/presentation/theme/animations.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/theme/animations.py>) | 44 | 상세 | — |
| [calendar_app/presentation/theme/style_builder.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/theme/style_builder.py>) | 507 | 상세 | 수정·검증 |
| [calendar_app/presentation/theme/ui_tokens.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/theme/ui_tokens.py>) | 24 | 상세 | — |
| [calendar_app/presentation/widgets/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/__init__.py>) | 1 | 정적 | — |
| [calendar_app/presentation/widgets/alarm_checker.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/alarm_checker.py>) | 325 | 상세 | 수정·검증 |
| [calendar_app/presentation/widgets/alarm_popup.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/alarm_popup.py>) | 693 | 상세 | 수정·검증 |
| [calendar_app/presentation/widgets/command_palette.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/command_palette.py>) | 7 | 정적 | — |
| [calendar_app/presentation/widgets/command_palette_runtime.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/command_palette_runtime.py>) | 1468 | 상세 | — |
| [calendar_app/presentation/widgets/keydeck/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/keydeck/__init__.py>) | 2 | 정적 | — |
| [calendar_app/presentation/widgets/keydeck/canvas.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/keydeck/canvas.py>) | 985 | 정적 | — |
| [calendar_app/presentation/widgets/keydeck/layout_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/keydeck/layout_dialog.py>) | 764 | 정적 | — |
| [calendar_app/presentation/widgets/keydeck/layout_library.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/keydeck/layout_library.py>) | 565 | 정적 | — |
| [calendar_app/presentation/widgets/keydeck/model.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/keydeck/model.py>) | 2186 | 상세 | 수정·검증 |
| [calendar_app/presentation/widgets/keydeck/physics.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/keydeck/physics.py>) | 295 | 정적 | — |
| [calendar_app/presentation/widgets/keydeck/renderer.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/keydeck/renderer.py>) | 1817 | 정적 | — |
| [calendar_app/presentation/widgets/keydeck/resources.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/keydeck/resources.py>) | 391 | 상세 | 수정·검증 |
| [calendar_app/presentation/widgets/keydeck/studio.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/keydeck/studio.py>) | 1403 | 정적 | — |
| [calendar_app/presentation/widgets/keydeck/studio_canvas.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/keydeck/studio_canvas.py>) | 498 | 정적 | — |
| [calendar_app/presentation/widgets/keydeck/studio_inspector.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/keydeck/studio_inspector.py>) | 2159 | 정적 | — |
| [calendar_app/presentation/widgets/keydeck/theme_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/keydeck/theme_dialog.py>) | 498 | 정적 | — |
| [calendar_app/presentation/widgets/launcher_keycap_assets.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/launcher_keycap_assets.py>) | 68 | 정적 | — |
| [calendar_app/presentation/widgets/launcher_keycap_icons.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/launcher_keycap_icons.py>) | 184 | 정적 | — |
| [calendar_app/presentation/widgets/launcher_keycap_sounds.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/launcher_keycap_sounds.py>) | 50 | 정적 | — |
| [calendar_app/presentation/widgets/moment_asset_packs.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/moment_asset_packs.py>) | 260 | 정적 | — |
| [calendar_app/presentation/widgets/overlay_base.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_base.py>) | 4882 | 상세 | 수정·검증 |
| [calendar_app/presentation/widgets/overlay_clock.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_clock.py>) | 378 | 상세 | 수정·검증 |
| [calendar_app/presentation/widgets/overlay_clock_widget.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_clock_widget.py>) | 3 | 정적 | — |
| [calendar_app/presentation/widgets/overlay_color_utils.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_color_utils.py>) | 58 | 상세 | 수정·검증 |
| [calendar_app/presentation/widgets/overlay_countdown.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_countdown.py>) | 425 | 상세 | 수정·검증 |
| [calendar_app/presentation/widgets/overlay_datecard.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_datecard.py>) | 788 | 상세 | — |
| [calendar_app/presentation/widgets/overlay_dday.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_dday.py>) | 406 | 상세 | — |
| [calendar_app/presentation/widgets/overlay_display_presets.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_display_presets.py>) | 213 | 상세 | — |
| [calendar_app/presentation/widgets/overlay_launcher_deck.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_launcher_deck.py>) | 745 | 상세 | — |
| [calendar_app/presentation/widgets/overlay_manager.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_manager.py>) | 884 | 상세 | 수정·검증 |
| [calendar_app/presentation/widgets/overlay_manager_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_manager_dialog.py>) | 768 | 정적 | — |
| [calendar_app/presentation/widgets/overlay_measure_utils.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_measure_utils.py>) | 195 | 상세 | — |
| [calendar_app/presentation/widgets/overlay_preset_logic.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_preset_logic.py>) | 229 | 정적 | — |
| [calendar_app/presentation/widgets/overlay_preset_service.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_preset_service.py>) | 106 | 상세 | — |
| [calendar_app/presentation/widgets/overlay_preset_store.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_preset_store.py>) | 66 | 상세 | — |
| [calendar_app/presentation/widgets/overlay_preset_ui_service.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_preset_ui_service.py>) | 138 | 상세 | — |
| [calendar_app/presentation/widgets/overlay_shadow.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_shadow.py>) | 216 | 상세 | — |
| [calendar_app/presentation/widgets/overlay_stopwatch.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_stopwatch.py>) | 374 | 상세 | 수정·검증 |
| [calendar_app/presentation/widgets/overlay_template_utils.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_template_utils.py>) | 193 | 상세 | — |
| [calendar_app/presentation/widgets/overlay_template_validation.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_template_validation.py>) | 298 | 상세 | — |
| [calendar_app/presentation/widgets/overlay_text.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_text.py>) | 447 | 상세 | — |
| [calendar_app/presentation/widgets/overlay_weather.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_weather.py>) | 923 | 상세 | 수정·검증 |
| [calendar_app/presentation/widgets/overlay_widgets.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/overlay_widgets.py>) | 33 | 정적 | — |
| [calendar_app/presentation/widgets/panel_widget_common.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/panel_widget_common.py>) | 196 | 상세 | — |
| [calendar_app/presentation/widgets/panel_widget_mode.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/panel_widget_mode.py>) | 1216 | 정적 | — |
| [calendar_app/presentation/widgets/panel_widget_shell.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/panel_widget_shell.py>) | 676 | 상세 | 수정·검증 |
| [calendar_app/presentation/widgets/panel_widget_style.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/panel_widget_style.py>) | 709 | 정적 | — |
| [calendar_app/presentation/widgets/panel_widget_theme.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/panel_widget_theme.py>) | 406 | 정적 | — |
| [calendar_app/presentation/widgets/panel_widget_views.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/panel_widget_views.py>) | 1165 | 정적 | — |
| [calendar_app/presentation/widgets/schedule_info.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/schedule_info.py>) | 241 | 정적 | — |
| [calendar_app/presentation/widgets/ui_components.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/ui_components.py>) | 2345 | 상세 | — |
| [calendar_app/presentation/widgets/unified_widget_mode.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/unified_widget_mode.py>) | 3465 | 상세 | 수정·검증 |
| [calendar_app/presentation/widgets/weather_asset_packs.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/weather_asset_packs.py>) | 384 | 상세 | — |
| [calendar_app/presentation/widgets/weather_design_dialog.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/weather_design_dialog.py>) | 492 | 상세 | — |
| [calendar_app/presentation/widgets/weather_designs.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/weather_designs.py>) | 205 | 정적 | — |
| [calendar_app/presentation/widgets/weather_template.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/weather_template.py>) | 178 | 상세 | — |
| [calendar_app/presentation/widgets/weather_vector_art.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/weather_vector_art.py>) | 402 | 정적 | — |
| [calendar_app/presentation/widgets/week_day_button.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/week_day_button.py>) | 85 | 정적 | — |
| [calendar_app/presentation/widgets/widget_free_layout.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/widget_free_layout.py>) | 196 | 상세 | — |
| [calendar_app/presentation/widgets/widget_free_layout_runtime.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/widget_free_layout_runtime.py>) | 387 | 정적 | — |
| [calendar_app/presentation/widgets/widget_layout_editor_canvas.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/widget_layout_editor_canvas.py>) | 627 | 정적 | — |
| [calendar_app/presentation/widgets/widget_layout_editor_io.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/widget_layout_editor_io.py>) | 44 | 상세 | — |
| [calendar_app/presentation/widgets/widget_layout_editor_preview.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/widget_layout_editor_preview.py>) | 218 | 상세 | — |
| [calendar_app/presentation/widgets/widget_layout_presets.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/widget_layout_presets.py>) | 145 | 상세 | — |
| [calendar_app/presentation/widgets/widget_mode_coordinator.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/widget_mode_coordinator.py>) | 179 | 상세 | — |
| [calendar_app/presentation/widgets/widget_mode_density.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/widget_mode_density.py>) | 27 | 상세 | — |
| [calendar_app/presentation/widgets/widget_mode_geometry.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/widget_mode_geometry.py>) | 96 | 상세 | — |
| [calendar_app/presentation/widgets/widget_mode_opacity.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/widget_mode_opacity.py>) | 47 | 상세 | — |
| [calendar_app/presentation/widgets/widget_mode_skins.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/widget_mode_skins.py>) | 582 | 상세 | 수정·검증 |
| [calendar_app/presentation/widgets/widget_mode_typography.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/widget_mode_typography.py>) | 51 | 상세 | 수정·검증 |
| [calendar_app/presentation/widgets/widget_mode_visibility.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/widget_mode_visibility.py>) | 33 | 정적 | — |
| [calendar_app/presentation/widgets/widget_placement.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/widget_placement.py>) | 482 | 정적 | — |
| [calendar_app/presentation/widgets/widget_preset_preview.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/widget_preset_preview.py>) | 85 | 정적 | — |
| [calendar_app/presentation/widgets/widget_shapes.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/presentation/widgets/widget_shapes.py>) | 44 | 상세 | — |
| [calendar_app/preset_manager.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/preset_manager.py>) | 437 | 정적 | — |
| [calendar_app/shared/__init__.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/shared/__init__.py>) | 1 | 정적 | — |
| [calendar_app/shared/app_lifecycle.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/shared/app_lifecycle.py>) | 55 | 정적 | — |
| [calendar_app/shared/background_worker.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/shared/background_worker.py>) | 181 | 정적 | — |
| [calendar_app/shared/calendar_defaults.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/shared/calendar_defaults.py>) | 3 | 정적 | — |
| [calendar_app/shared/color_utils.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/shared/color_utils.py>) | 342 | 정적 | — |
| [calendar_app/shared/datetime_utils.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/shared/datetime_utils.py>) | 185 | 상세 | 수정·검증 |
| [calendar_app/shared/encoding_utils.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/shared/encoding_utils.py>) | 35 | 정적 | — |
| [calendar_app/shared/google_color_palette.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/shared/google_color_palette.py>) | 118 | 정적 | — |
| [calendar_app/shared/i18n.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/shared/i18n.py>) | 97 | 정적 | — |
| [calendar_app/shared/icon_map.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/shared/icon_map.py>) | 428 | 정적 | — |
| [calendar_app/shared/qt_helpers.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/shared/qt_helpers.py>) | 45 | 정적 | — |
| [calendar_app/shared/search_utils.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/shared/search_utils.py>) | 125 | 정적 | — |
| [calendar_app/shared/system_theme.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/shared/system_theme.py>) | 84 | 정적 | — |
| [calendar_app/shared/tag_highlighter.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/shared/tag_highlighter.py>) | 25 | 정적 | — |
| [calendar_app/shared/theme_settings.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/shared/theme_settings.py>) | 159 | 정적 | — |
| [calendar_app/shared/theme_snapshot.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/shared/theme_snapshot.py>) | 942 | 정적 | — |
| [calendar_app/shared/ui_tokens.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/shared/ui_tokens.py>) | 84 | 정적 | — |
| [calendar_app/shared/value_parsers.py](<D:/00. Dev_Folder/Dark Calendar/calendar_app/shared/value_parsers.py>) | 26 | 상세 | 수정·검증 |
| [infrastructure/db/db_repository_unified.py](<D:/00. Dev_Folder/Dark Calendar/infrastructure/db/db_repository_unified.py>) | 19 | 정적 | — |
| [main.py](<D:/00. Dev_Folder/Dark Calendar/main.py>) | 26 | 정적 | — |
| [patch_detail_test.py](<D:/00. Dev_Folder/Dark Calendar/patch_detail_test.py>) | 50 | 정적 | — |
| [scripts/check_encoding.py](<D:/00. Dev_Folder/Dark Calendar/scripts/check_encoding.py>) | 91 | 정적 | — |
| [scripts/fix_encoding.py](<D:/00. Dev_Folder/Dark Calendar/scripts/fix_encoding.py>) | 114 | 정적 | — |
| [scripts/gcal_dedupe.py](<D:/00. Dev_Folder/Dark Calendar/scripts/gcal_dedupe.py>) | 211 | 정적 | — |
| [scripts/generate_brand_assets.py](<D:/00. Dev_Folder/Dark Calendar/scripts/generate_brand_assets.py>) | 86 | 정적 | — |
| [scripts/generate_icons.py](<D:/00. Dev_Folder/Dark Calendar/scripts/generate_icons.py>) | 193 | 정적 | — |
| [scripts/generate_keycap_assets.py](<D:/00. Dev_Folder/Dark Calendar/scripts/generate_keycap_assets.py>) | 311 | 정적 | — |
| [scripts/generate_keycap_sounds.py](<D:/00. Dev_Folder/Dark Calendar/scripts/generate_keycap_sounds.py>) | 131 | 정적 | — |
| [scripts/generate_keyswitch_sounds.py](<D:/00. Dev_Folder/Dark Calendar/scripts/generate_keyswitch_sounds.py>) | 210 | 정적 | — |
| [scripts/i18n_sync.py](<D:/00. Dev_Folder/Dark Calendar/scripts/i18n_sync.py>) | 430 | 정적 | — |
| [scripts/release_compliance.py](<D:/00. Dev_Folder/Dark Calendar/scripts/release_compliance.py>) | 488 | 정적 | — |
| [scripts/render_launcher_deck_preview.py](<D:/00. Dev_Folder/Dark Calendar/scripts/render_launcher_deck_preview.py>) | 121 | 정적 | — |
| [scripts/render_widget_visual_upgrade_preview.py](<D:/00. Dev_Folder/Dark Calendar/scripts/render_widget_visual_upgrade_preview.py>) | 66 | 정적 | — |
| [scripts/reset_release_state.py](<D:/00. Dev_Folder/Dark Calendar/scripts/reset_release_state.py>) | 130 | 정적 | — |
| [scripts/run_encoding_guard.py](<D:/00. Dev_Folder/Dark Calendar/scripts/run_encoding_guard.py>) | 52 | 상세 | 수정·검증 |
| [scripts/run_quality_gate.py](<D:/00. Dev_Folder/Dark Calendar/scripts/run_quality_gate.py>) | 88 | 상세 | 수정·검증 |
| [scripts/translate_locales.py](<D:/00. Dev_Folder/Dark Calendar/scripts/translate_locales.py>) | 241 | 정적 | — |
| [scripts/validate_widget_free_layout.py](<D:/00. Dev_Folder/Dark Calendar/scripts/validate_widget_free_layout.py>) | 561 | 정적 | — |
| [scripts/validate_widget_layout_editor_advanced.py](<D:/00. Dev_Folder/Dark Calendar/scripts/validate_widget_layout_editor_advanced.py>) | 970 | 정적 | — |
| [scripts/validate_widget_layout_presets.py](<D:/00. Dev_Folder/Dark Calendar/scripts/validate_widget_layout_presets.py>) | 573 | 정적 | — |
| [scripts/validate_widget_mode_ux_plan.py](<D:/00. Dev_Folder/Dark Calendar/scripts/validate_widget_mode_ux_plan.py>) | 513 | 정적 | — |
| [scripts/verify_release_runtime.py](<D:/00. Dev_Folder/Dark Calendar/scripts/verify_release_runtime.py>) | 151 | 정적 | — |
