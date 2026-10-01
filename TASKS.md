# Dark Calendar — 진행 중 작업 트래킹

> 이 파일은 여러 세션에 걸쳐 진행되는 작업의 현재 상태를 기록합니다.
> 완료된 항목은 `[x]`, 진행 중은 `[~]`, 미착수는 `[ ]`로 표시합니다.
> 마지막 업데이트: 2026-03-31

---

## 1. 멀티 캘린더 리팩터 (Multi-Calendar Refactor)

**목표**: 단일 GCal 연동 구조 → GCal / 로컬 / ICS 구독 / PC 공유 4종 캘린더 통합 관리

### 1-1. DB 레이어
- [x] `calendar` 테이블 DDL 설계 및 `database_unified.py` 스키마 추가
- [x] `calendar_repo.py` CRUD 구현 (`list_calendars`, `upsert_calendar`, `set_calendar_visible`, `set_calendar_default`, `delete_calendar` 등)
- [x] `migrate_from_gcal_subscription()` — gcal_subscription → calendar 마이그레이션 (bootstrap에서 최초 1회)
- [x] `auto-create default local calendar when none exist` (5ea7d0a)

### 1-2. 태스크 생성/수정 다이얼로그
- [x] `task_dialog_unified.py` — 캘린더 드롭다운 추가 (`_get_selected_calendar_id()`, `calendar_id` persist)
- [x] create / move / copy 흐름 호환성 강화 (7454dc0)

### 1-3. 캘린더 설정 다이얼로그
- [x] `gcal_settings_dialog.py` — "캘린더" 탭: 캘린더 카드 목록, 가시성 토글, 색상 선택, 기본 캘린더 지정

### 1-4. 월 캘린더 렌더러
- [x] `month_renderer.py` — `is_visible=0` 캘린더 이벤트 숨김 처리
- [x] 캘린더 가시성 토글 버튼 (month_renderer 내 컨텍스트 메뉴)

### 1-5. 상단바 옵션 메뉴 (system_menu / display_menu)
- [x] `display_menu.py` — 캘린더별 가시성 토글을 옵션 메뉴에 노출 (f126c8b)
  - "화면" 메뉴 → "캘린더 표시" 서브메뉴: 동적 캘린더 목록 + 색상 아이콘 + 체크박스

### 1-6. 패널 색상 연동
- [x] `side_panel_renderer.py` — 패널 프레임에 per-calendar color 적용
  - `_calendar_color_for_task()`: `calendar_id` → 캘린더 색상 캐시 조회 (GCal fallback 포함)
  - `create_task_box()` 호출 시 `bg_color=task.get('bg_color') or _calendar_color_for_task(task)` 적용
  - `invalidate_panel_calendar_cache()`: 캘린더 변경 시 캐시 무효화 (gcal_settings_dialog, month_renderer 연동)

### 1-7. ICS 구독 캘린더
- [ ] ICS fetcher (`ics_fetcher.py`) → `calendar` 테이블 `ics::*` 항목 연동
- [ ] 1시간 주기 자동 갱신 (`ics_last_fetched` 기반)
- [ ] 설정 다이얼로그 "캘린더" 탭에서 ICS URL 추가/삭제 UI

### 1-8. PC 공유 캘린더
- [ ] 공유 DB 경로: `C:\Users\Public\DarkCalendar\shared.db`
- [ ] 읽기/쓰기 권한 처리 (모든 PC 사용자 r/w)
- [ ] `shared` 타입 캘린더 CRUD 연동

---

## 2. 코드 정리 (Code Cleanup)

### 2-1. 루트 일회성 스크립트 정리
- [x] 적용 완료된 `check_*.py`, `debug_*.py`, `tmp_*.py`, `apply_*.py` 등 82개 파일 삭제
  - GIS 데이터 (`DAM_DAN.*`), 지도 HTML (`Pohang_*.html`), 테스트 출력 파일도 제거
  - `tests/test_encoding_policy.py`의 `_ROOT_SCRIPT_EXCLUSIONS` 제거 (파일 삭제 완료)

### 2-2. `scripts/` 정리
- [x] `scripts/tmp_patch_*.py`, `scripts/inject_*.py`, `scripts/*_fix_*.py` 등 10개 일회성 스크립트 제거

---

## 3. 테마 토큰 완성 (Theme Token Completion)

- [~] `docs/theme_token_completion_process.md` 참조
- [ ] 미완성 토큰 적용 항목 확인 및 마무리

---

## 4. 기타 미결

- [ ] `docs/duplication_consolidation_plan.md` — 중복 로직 통합 계획 실행
- [ ] `requirements-dev.txt` 내용 검토 및 CI 연동 확인

## 6. 위젯 전용 모드 UI/UX 개선

계획: [docs/widget_only_mode_ux_plan.md](docs/widget_only_mode_ux_plan.md)（2026-10-01）

- [x] 현재 코드·테스트 데이터 기반 화면 확인 및 개선 계획 수립
- [x] 의미·탐색 개선(B) 및 목록 위치·처리 피드백 안정화(C) 구현
- [x] 정보 위계·꾸미기 정돈(D), 성능 및 배율·다국어 샘플 검증(E 일부)
- [ ] 실제 데이터·장시간·스크린 리더·물리 혼합 DPI 인수 확인, 대량 목록 최초 생성 후속 평가
- 결과: [docs/widget_only_mode_ux_results.md](docs/widget_only_mode_ux_results.md)

## 7. 위젯 자유 구성·주간 보기 개선

- [x] 기존 프리셋을 유지하며 독립 자유 구성 모델·저장·복원 구현
- [x] 구성 요소 선택, 드래그 이동·크기 조절, 수치 입력, 선택적 정렬, 실행 취소/다시 실행, 주간/월간 선택
- [x] 독립 목록의 원본 데이터·처리기 공유, 프리셋/자유 구성 창 크기 보존, 꾸미기와 초안 취소 호환
- [x] 동일 너비의 주간 날짜, 요일/날짜 위계, 오늘·선택·호버·키보드 상태 및 불투명도 적용
- [x] 19개 로케일 새 문구 24개 번역, 관련 테스트 18파일 253개 통과, 3개 배율 화면/상호작용 검사 132개 통과
- [ ] 실제 데이터·장시간·스크린 리더·물리 혼합 DPI 인수 확인
- 결과: [docs/widget_free_layout_results.md](docs/widget_free_layout_results.md)

## 8. WYSIWYG 위젯 구성 편집기 고도화

- [x] 실제 위젯 렌더링과 현재 캐시·날짜·필터·시계의 읽기 전용 미리보기
- [x] 다중 선택·그룹 이동·8방향 크기 조절·정렬 가이드·간격 맞춤·잠금·요소 순서
- [x] 같은 화면의 글꼴·스킨·불투명도 편집 및 배치/모양 공통 실행 취소·적용/취소
- [x] 확대/화면 맞춤, 4개 설정 탭과 스크롤, 배치 구성 불러오기/내보내기
- [x] 관련 테스트 21파일 321개, 3배율 포함 네이티브 화면/회귀 검사 635개, Ruff·인코딩·19개 로케일 신규 문구 검사 통과
- [ ] 실제 사용자 데이터·장시간·스크린 리더·물리 혼합 DPI 인수 확인
- 결과: [docs/widget_layout_editor_advanced_results.md](docs/widget_layout_editor_advanced_results.md)

## 9. 사용자 배치 프리셋 관리

- [x] 독립 QSettings 목록, UUID ID, 자유 구성 검증, 저장·재시작 복원
- [x] 구성 편집의 새 저장·덮어쓰기·이름 변경·삭제, 공통 실행 취소·적용/취소
- [x] 꾸미기의 내 배치 썸네일·수정·이름 변경·삭제, 중첩 편집 부모 초안 호환
- [x] 더 보기 배치 메뉴 연결, 기본 배치 전환 시 목록 보존, 삭제 시 현재 자유 구성 유지
- [x] 100%·200% 네이티브 화면·임시 INI 재시작 검사 104개 통과
- [x] 관련 테스트 25파일 368개, 인코딩 guard·Ruff·19개 로케일 신규 문구 검사 통과
- 결과: [docs/widget_layout_editor_advanced_results.md](docs/widget_layout_editor_advanced_results.md#후속-사용자-배치-프리셋)
