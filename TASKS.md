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
- [ ] 적용 완료된 `fix_*.py`, `patch_*.py`, `check_*.py`, `debug_*.py` 등 삭제
  - `.gitignore`에 이미 등록되어 git 추적에서는 제외됨
  - 물리적 파일 삭제는 별도 확인 후 진행

### 2-2. `scripts/` 정리
- [ ] `scripts/tmp_patch_*.py`, `scripts/inject_*.py` 등 일회성 스크립트 제거

---

## 3. 테마 토큰 완성 (Theme Token Completion)

- [~] `docs/theme_token_completion_process.md` 참조
- [ ] 미완성 토큰 적용 항목 확인 및 마무리

---

## 4. 기타 미결

- [ ] `docs/duplication_consolidation_plan.md` — 중복 로직 통합 계획 실행
- [ ] `requirements-dev.txt` 내용 검토 및 CI 연동 확인
