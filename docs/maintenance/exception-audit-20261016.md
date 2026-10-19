# Air Calendar 전체 예외 경계 점검 · 2026-10-16

운영·도구 Python 소스 331개에 UTF-8 디코딩, AST 구문 분석, 컴파일 검사를 적용했다. 전체 운영 코드의 미정의 이름·잘못된 구문 검사와 수정 파일의 Ruff 검사도 통과했다. 시작과 종료, 저장 설정, 반복 날짜 계산, 체크리스트 가져오기의 입력·실패 경계를 상세 검토하고 아래 문제를 수정했다. 나머지 기능은 기존 회귀 검사로 확인하며, 모든 소스의 모든 실행 분기를 수동 검토했다는 의미는 아니다.

기존 미커밋 변경과 정기 유지보수 변경을 보존했다. 이번 구현 수정은 10개 소스 파일이며 신규 회귀 검사는 5개 파일, 92개 사례다.

## 확인한 오류와 수정

| 영역 | 재현한 오류 | 수정 |
|---|---|---|
| 일정 자동 색상 | 색상 이력에 `null`, 숫자, 불리언 등 배열이 아닌 JSON이 있으면 반복 처리 예외 발생 | 배열만 읽고 정상 색상 이력 유지 |
| 패널 색상 메뉴 | 최근 색상 설정의 비배열 JSON에서 메뉴 생성 실패 또는 잘못된 색상 추가 | 목록 타입을 확인하고 잘못된 루트는 빈 목록으로 복구 |
| 라벨 프리셋 | 잘못된 루트·항목·중첩 필드로 목록 표시와 적용 실패, 손상된 설정에서 새 저장도 무시됨 | 항목 구조를 검증하고 정상 프리셋은 유지하며 새 저장·삭제 복구 |
| 체크리스트 가져오기 | 항목 오류 뒤 템플릿과 앞선 항목만 남거나 DB 저장 실패를 성공으로 표시 | 파일 전체 사전 검증 후 SAVEPOINT로 일괄 저장·되돌림. 호출자의 바깥 트랜잭션 보존 |
| 반복 일정 규칙 | 잘못된 요일·순번·월 위치와 최대 날짜에서 예외 또는 엉뚱한 날짜 생성 | 날짜·정수 범위 검증, 다음 발생일이 없으면 `None` 반환 |
| 반복 일괄 생성 | 매일 일정이 하루씩 빠지고 마지막 표현 가능 날짜에서 결과 반환 전 오버플로 | 다음 날짜 계산의 기준을 마지막 발생일로 유지하고 종료 상한 보호 |
| 자리 비움 감지 | 손상된 간격으로 워커 생성 실패, 문자열 변경값의 반복 곱셈, 음수·과대 시간 수용 | 기존 설정창과 같은 1~1440분 범위와 기본값 적용 |
| 여러 날 일정 | 손상된 글꼴 크기를 정수로 변환하다 일정 제목 스타일 생성 실패 | 안전한 숫자 해석과 크기 제한 적용 |
| 시작·종료 | DB 초기화·이관 실패 결과를 무시하고 계속 시작, 시작 단계 예외에서 정리 누락 | 실패 시 시작 중단, DB 연결·단일 실행 잠금 등 공통 정리 실행. 이미 삭제된 시작 화면의 종료 경합도 방어 |

## 검증

현재 존재하는 테스트 **230개 파일, 4,172개 사례가 모두 통과**했다. 실패·오류·건너뜀은 0이다. 신규 회귀 92개와 인코딩 정책·유틸 12개를 포함한 수이며, 재실행한 검사를 중복 합산하지 않았다. 파일별 최신 완전한 JUnit과 정상 종료 결과, 원래 QSettings 보존 확인을 대조해 최종 집계했다. 한 프로세스에서 전체 파일을 실행한 결과와는 구분한다.

331개 운영·도구 소스의 UTF-8/AST/컴파일, 전체 주요 Ruff, 수정한 소스·검사의 전체 Ruff, 공식 인코딩 가드와 diff 검사가 통과했다. 마지막 버전 `scan`은 변경 없음·4.0.2를 반환했다.

직접 재현한 수정 전 실패는 설정 23개, 체크리스트 3개, 반복 27개, 숫자 설정 17개, 시작 4개였다. 해당 경로는 수정 후 통과했다. 추가한 바깥 트랜잭션·재시도·autocommit·읽기 전용 DB 및 삭제된 Qt 시작 화면 검사도 통과했다. 별도 점검에서 정상 반복 규칙 8개와 DB 접근 전 잘못된 가져오기 차단 13개를 확인했다.

검사는 파일마다 별도 프로세스, 임시 INI 설정과 DB, 임시 APPDATA/LOCALAPPDATA를 사용한다. 고정 경로인 공용 DB는 `shared_db`의 경로·연결 캐시까지 임시 대상으로 교체했다. 각 완료 프로세스는 사용자 원래 QSettings가 바뀌지 않았는지도 확인한다. 실제 계정·인증 정보나 개인 DB에 저장 테스트를 하지 않았다.

Qt 화면 검사 2개는 처음의 420초 실행 제한을 넘겼다. 제한을 1200초로 늘려 재검사했고, 동기화 조정자 46개와 계정 설정 47개가 모두 정상 종료·통과했다. 최초 제한 초과를 기능 오류나 통과로 집계하지 않았다. 별도 진단으로 확인한 QtAwesome의 Windows 글꼴 설치 반복은 검사 환경에서 같은 번들 글꼴을 직접 읽도록 조정했다. 실제 아이콘 생성·렌더링은 유지하고 검사 과정의 시스템 글꼴 설치를 피했다. 초기 중단·제한 초과·수정 전 실패 기록과 최종 결과는 분리했다.

실제 계정 동기화, 설치판 UI의 장시간 조작, 빌드·배포·Store 설치 반영은 이번 검증에 포함하지 않는다. 저장 실패·비정상 응답을 넣은 격리 검사를 실제 서비스 조작과 구분한다.

## 변경 파일과 버전

- `calendar_app/bootstrap.py`
- `calendar_app/application/task_usecases.py`
- `calendar_app/application/routine_batch_generator.py`
- `calendar_app/domain/task_constants.py`
- `calendar_app/domain/policies/routine_policy.py`
- `calendar_app/infrastructure/db/checklist_template_repo.py`
- `calendar_app/infrastructure/runtime/idle_detector.py`
- `calendar_app/presentation/dialogs/checklist_manager_dialog_advanced.py`
- `calendar_app/presentation/main_window/window_ui_actions.py`
- `calendar_app/presentation/widgets/ui_components.py`

기존 개발 3.9.1에서 독립 수정과 검사 정합성 보완 이벤트를 등록해 **4.0.2 Dev**로 갱신했다. 사용자 지정 자리올림 규칙을 적용한 결과다. 마지막 공개 버전 메타데이터는 3.8.1로 유지하며, 새 버전 등록은 배포나 설치 완료를 의미하지 않는다. 이번 변경 이외의 DB 이관·NLP·갱신·Google 워커 변경은 원래 작업으로 보존한다.

기존 검사 2개 파일도 현재 계약에 맞췄다. `test_account_sync_ux.py`의 fake에 이미 구현된 공통 Google 워커 시작 메서드를 연결했고, `test_build_pipeline_contracts.py`는 홈페이지가 개발 번호가 아닌 `APP_PUBLISHED_VERSION`의 공개 소스 링크를 안내하는지 검사한다. 실제 기능의 성공·실패 및 공개 링크 검증 조건은 유지했다.

## 근거

- [최종 검사 집계](../../artifacts/exception-audit-20261016/final-summary.json)
- [파일별 최종 격리 테스트 결과](../../artifacts/exception-audit-20261016/final-test-results.json)
- [소스 구문·해시 목록](../../artifacts/exception-audit-20261016/static-inventory.json)
- [격리 실행기](../../artifacts/exception-audit-20261016/run_file_tests.py)
- [개인·공용 저장소 격리](../../artifacts/exception-audit-20261016/isolated_child.py)
- [인코딩 가드](../../artifacts/exception-audit-20261016/encoding-guard.txt) · [전체 주요 Ruff](../../artifacts/exception-audit-20261016/ruff-runtime.txt) · [수정 파일 Ruff](../../artifacts/exception-audit-20261016/ruff-changes.txt)
- [당일 재현·초기 실행 기록](../../artifacts/exception-audit-20261016/)
- [수정 전후 재현 기록](../../artifacts/exception-audit-20261015/)
- [버전 이력](version-history.md)
