# Air Calendar 문서 색인

버전 증가 기준과 자동 등록은 [버전 규칙](../rules/versioning.md), 변경별 버전·일시·이벤트는 [버전 변경 이력](maintenance/version-history.md)을 참고합니다.

Store 4.3.3의 DB 초기화 오류 재발, 로컬 복구와 배포 검증 절차 수정은 [2026-10-20 장애 조사](maintenance/store-db-recurrence-20261020.md)에 기록했습니다. 안전한 SQLite 런타임을 포함한 새 배포는 별도 미완료 상태입니다.

329개 Python 파일의 점검 범위, 오류 수정과 217개 테스트 파일의 격리 검증은 [2026-10-08 파일별 코드 점검](maintenance/code-audit-20261008.md)에 기록했습니다.

외부 캘린더의 인증·악성 응답·로그·진단 내보내기·의존성·배포 입력 보안 보완은 [2026-10-20 연동 보안 점검](maintenance/external-sync-security-20261020.md)에 기록했습니다.

ICS 갱신 중 주소 수정, Outlook·CalDAV 연결 해제와 재인증의 상태 보존은 [2026-11-01 동기화·구독 안정화](maintenance/sync-subscription-stability-20261101.md)에 기록했습니다. 소스 수정과 격리 회귀 1,350건을 검증했으며 설치판 인수는 별도입니다.

후속 기능·개선의 우선순위, 기존 처리 재사용과 완료 기준은 [2026-10-21 외부 캘린더 개선 계획](maintenance/external-sync-roadmap-20261021.md)을 참고합니다. 계획 수립 상태이며 구현은 미착수입니다.

Outlook·Microsoft 365 최초 연결과 iCloud·네이버 확장 구조는 [Outlook 동기화 설정](outlook_sync_setup.md)을 참고합니다.

iCloud·네이버 연결 방법은 [CalDAV 설정](caldav_sync_setup.md), 공통 오류와 안전 계약은 [동기화 안전 점검](calendar_sync_safety.md)을 참고합니다.

Google·ICS·Outlook·CalDAV의 수신 검증, 원격 데이터 보호, 요청 제한·취소·부분 완료 개선은 [2026-10-07 외부 동기화 점검](ux-audit/external-sync-boundary-audit-20261007.md)에 기록했습니다.

계정 재인증·일시정지·재시도 대기, 설정 화면과 목록 초안 보존의 개선은 [2026-10-07 계정·동기화 UI/UX](ux-audit/account-sync-ui-ux-20261007.md)에 기록했습니다.

실제 Google 응답의 시작=종료 일정이 동기화를 중단하던 원인과 날짜 처리·오류 안내 수정은 [2026-10-07 Google 날짜 검증 오류](ux-audit/google-sync-zero-duration-20261007.md)에 기록했습니다.

내 캘린더 목록에서 새 일정의 기본 저장 위치를 바로 지정하는 통합 UI와 검증은 [2026-10-07 목록 기본 저장 지정](ux-audit/calendar-list-default-20261007.md)에 기록했습니다.

로컬 캘린더와 ICS 구독의 전용 탭, 추가·관리와 문제 해결 이동은 [2026-10-07 캘린더 관리 탭 개편](ux-audit/calendar-management-tabs-20261007.md)에 기록했습니다.

캘린더 툴바의 버튼 한 행 배치와 ‘사용 방법’ 제거는 [2026-10-07 툴바 정리](ux-audit/calendar-toolbar-one-row-20261007.md)에 기록했습니다.

공통 설정과 추가 계정 연결의 위치·역할 분리와 작은 창 개선은 [2026-10-07 연결 화면 버튼 정리](ux-audit/calendar-service-disclosures-20261007.md)에 기록했습니다.

이번 구현과 화면·회귀 검증 결과는 [2026-10-05 동기화 UI/UX 점검](ux-audit/calendar-sync-review-2026-10-05.md)에 기록했습니다.

공통 버튼·전체 캘린더 관리·자동 갱신·문제 해결 흐름은 [2026-10-05 동기화 기능 통합](ux-audit/calendar-sync-integration-2026-10-05.md)을 참고합니다.

CalDAV 변경분 다운로드·UID 주소 복구, 번역 누락 및 테스트 설정 격리의 최종 검증은 [2026-10-05 후속 개선](ux-audit/calendar-sync-followup-2026-10-05.md)에 기록했습니다.

주간 시간표의 드래그 생성·이동·기간 조절과 화면·회귀 검증은 [2026-10-07 주간 시간표](ux-audit/week-time-planner-20261007.md)에 기록했습니다.

주간 시간표의 투명도·시간 이동·선택 날짜·좁은 창 개선은 [2026-10-07 시간표 UI/UX](ux-audit/week-time-planner-ux-20261007.md)에 기록했습니다.

트레이에서 메인 창을 표시·활성화하는 경로와 전체 앱 시작 검증은 [2026-10-07 메인 창 복원](ux-audit/tray-main-window-recovery-20261007.md)에 기록했습니다.

코딩 작업은 [AGENTS.md](../AGENTS.md) → [TASKS.md](../TASKS.md) → 관련 rules 문서 순서로 시작합니다. 전체 문서를 매번 읽을 필요는 없습니다.

## 문서 관리 기준

- rules/: 현재 구현에 적용할 상세 지침. 실제 코드와 충돌하면 호출부를 확인하고 함께 갱신합니다.
- TASKS.md: 진행·미완료·수동 검증 상태. 구현 완료와 배포 완료를 구분합니다.
- docs/: 설계 배경, 감사 결과, 버전별 배포 기록. 과거 성공 기록은 현재 검증을 대신하지 않습니다.
- memory/: 과거 프로젝트 제안. 현재 작업 지시나 구현 완료 증거로 사용하지 않습니다.
- marketing/ 및 법적 고지: 코딩 지침과 별도 관리하며, 문서 정리만으로 공개 고지의 내용을 바꾸지 않습니다.

## 전체 목록

| 문서 | 역할 |
|---|---|
| [AGENTS.md](../AGENTS.md) | 작업 진입점 |
| [CLAUDE.md](../CLAUDE.md) | Claude 진입 안내 |
| [design-qa.md](../design-qa.md) | 설계·감사 기록 |
| [docs\assets\screenshots\README.md](../docs/assets/screenshots/README.md) | 참고 문서 |
| [docs\dialog_datetime_ux_improvement_plan.md](../docs/dialog_datetime_ux_improvement_plan.md) | 설계·감사 기록 |
| [docs\dialog_usability_accessibility_audit.md](../docs/dialog_usability_accessibility_audit.md) | 설계·감사 기록 |
| [docs\google-oauth-verification-guide.md](../docs/google-oauth-verification-guide.md) | 참고 문서 |
| [docs\keydeck_v4_plan.md](../docs/keydeck_v4_plan.md) | 설계·감사 기록 |
| [docs\microsoft-store-gpl-release.md](../docs/microsoft-store-gpl-release.md) | 개인정보·라이선스·배포 고지 |
| [docs\panel_widget_mode_split_plan.md](../docs/panel_widget_mode_split_plan.md) | 설계·감사 기록 |
| [docs\privacy-policy.en.md](../docs/privacy-policy.en.md) | 개인정보·라이선스·배포 고지 |
| [docs\privacy-policy.ko.md](../docs/privacy-policy.ko.md) | 개인정보·라이선스·배포 고지 |
| [docs\release-3.6.1-checklist.md](../docs/release-3.6.1-checklist.md) | 버전별 배포 기록 |
| [docs\release-3.6.5-checklist.md](../docs/release-3.6.5-checklist.md) | 버전별 배포 기록 |
| [docs\release-3.6.5-notes.md](../docs/release-3.6.5-notes.md) | 버전별 배포 기록 |
| [docs\release-3.6.6-checklist.md](../docs/release-3.6.6-checklist.md) | 버전별 배포 기록 |
| [docs\release-3.6.6-notes.md](../docs/release-3.6.6-notes.md) | 버전별 배포 기록 |
| [docs\release-3.6.7-checklist.md](../docs/release-3.6.7-checklist.md) | 버전별 배포 기록 |
| [docs\release-3.6.7-notes.md](../docs/release-3.6.7-notes.md) | 버전별 배포 기록 |
| [docs\release-3.6.8-checklist.md](../docs/release-3.6.8-checklist.md) | 버전별 배포 기록 |
| [docs\release-3.6.8-notes.md](../docs/release-3.6.8-notes.md) | 버전별 배포 기록 |
| [docs\release-3.6.9-checklist.md](../docs/release-3.6.9-checklist.md) | 버전별 배포 기록 |
| [docs\release-3.6.9-notes.md](../docs/release-3.6.9-notes.md) | 버전별 배포 기록 |
| [docs\release-3.7.0-checklist.md](../docs/release-3.7.0-checklist.md) | 버전별 배포 기록 |
| [docs\release-3.7.0-notes.md](../docs/release-3.7.0-notes.md) | 버전별 배포 기록 |
| [docs\release-3.7.1-checklist.md](../docs/release-3.7.1-checklist.md) | 버전별 배포 기록 |
| [docs\release-3.7.1-notes.md](../docs/release-3.7.1-notes.md) | 버전별 배포 기록 |
| [docs\release-3.7.2-checklist.md](../docs/release-3.7.2-checklist.md) | 버전별 배포 기록 |
| [docs\release-3.7.2-notes.md](../docs/release-3.7.2-notes.md) | 버전별 배포 기록 |
| [docs\release-3.7.3-checklist.md](../docs/release-3.7.3-checklist.md) | 버전별 배포 기록 |
| [docs\release-3.7.3-notes.md](../docs/release-3.7.3-notes.md) | 버전별 배포 기록 |
| [docs\release-3.7.4-checklist.md](../docs/release-3.7.4-checklist.md) | 버전별 배포 기록 |
| [docs\release-3.7.4-notes.md](../docs/release-3.7.4-notes.md) | 버전별 배포 기록 |
| [docs\release-3.7.5-checklist.md](../docs/release-3.7.5-checklist.md) | 버전별 배포 기록 |
| [docs\release-3.7.5-notes.md](../docs/release-3.7.5-notes.md) | 버전별 배포 기록 |
| [docs\release-3.7.6-notes.md](../docs/release-3.7.6-notes.md) | 버전별 배포 기록 |
| [docs\release-3.7.7-checklist.md](../docs/release-3.7.7-checklist.md) | 버전별 배포 기록 |
| [docs\release-3.7.7-notes.md](../docs/release-3.7.7-notes.md) | 버전별 배포 기록 |
| [docs\ux-audit\figma-handoff\night-signal-philosophy.md](../docs/ux-audit/figma-handoff/night-signal-philosophy.md) | 설계·감사 기록 |
| [docs\ux-audit\homepage-ui-ux-improvement-plan.md](../docs/ux-audit/homepage-ui-ux-improvement-plan.md) | 설계·감사 기록 |
| [marketing\DARK_CALENDAR_PROMOTION_KIT.md](../marketing/DARK_CALENDAR_PROMOTION_KIT.md) | 홍보 자료·기록 |
| [marketing\GENERATED_PROMO_ASSETS.md](../marketing/GENERATED_PROMO_ASSETS.md) | 홍보 자료·기록 |
| [marketing\GLOBAL_PROMOTION_LOG.md](../marketing/GLOBAL_PROMOTION_LOG.md) | 홍보 자료·기록 |
| [marketing\LAUNCH_CAMPAIGN_2026-08-31.md](../marketing/LAUNCH_CAMPAIGN_2026-08-31.md) | 홍보 자료·기록 |
| [memory\widget_mode_redesign.md](../memory/widget_mode_redesign.md) | 설계·감사 기록 |
| [README.md](../README.md) | 제품·개발 시작 안내 |
| [rules\architecture.md](../rules/architecture.md) | 상세 지침 |
| [rules\database.md](../rules/database.md) | 상세 지침 |
| [rules\dialog_ui.md](../rules/dialog_ui.md) | 상세 지침 |
| [rules\duplication_consolidation_plan.md](../rules/duplication_consolidation_plan.md) | 설계·감사 기록 |
| [rules\encoding.md](../rules/encoding.md) | 상세 지침 |
| [rules\gcal_sync.md](../rules/gcal_sync.md) | 상세 지침 |
| [rules\i18n.md](../rules/i18n.md) | 상세 지침 |
| [rules\legacy-encoding-guideline.md](../rules/legacy-encoding-guideline.md) | 상세 지침 |
| [rules\overlay_widgets.md](../rules/overlay_widgets.md) | 상세 지침 |
| [rules\panel_selection.md](../rules/panel_selection.md) | 상세 지침 |
| [rules\store_release_process.md](../rules/store_release_process.md) | 상세 지침 |
| [rules\task_dialog.md](../rules/task_dialog.md) | 상세 지침 |
| [rules\template_engine.md](../rules/template_engine.md) | 상세 지침 |
| [rules\theme_token_completion_process.md](../rules/theme_token_completion_process.md) | 상세 지침 |
| [SOURCE_OFFER.md](../SOURCE_OFFER.md) | 개인정보·라이선스·배포 고지 |
| [TASKS.md](../TASKS.md) | 현재 작업 상태 |
| [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) | 개인정보·라이선스·배포 고지 |
| [docs\widget_only_mode_ux_plan.md](widget_only_mode_ux_plan.md) | 위젯 전용 모드 UI/UX 개선 계획 및 상태 |
| [docs\widget_only_mode_ux_results.md](widget_only_mode_ux_results.md) | 위젯 전용 모드 로컬 구현·검증 결과 |
| [docs\widget_free_layout_results.md](widget_free_layout_results.md) | 위젯 자유 구성·주간 보기 로컬 구현·검증 결과 |
| [docs\widget_layout_editor_advanced_results.md](widget_layout_editor_advanced_results.md) | WYSIWYG 구성 편집기 로컬 구현·검증 결과 |
