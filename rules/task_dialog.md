# 태스크 다이얼로그 규칙

## 핵심 파일

| 파일 | 역할 |
|---|---|
| `presentation/dialogs/task_dialog_unified.py` | `UnifiedTaskDialog` — 생성/수정 UI |
| `presentation/dialogs/task_dialog_base.py` | 공통 베이스 클래스 |
| `presentation/dialogs/dialog_router.py` | `DialogActionsMixin` + 라우팅 맵 |
| `application/task_dialog_usecases.py` | 다이얼로그 유스케이스 |

## 3가지 흐름 (반드시 모두 검증)

`task_dialog_unified.py`를 수정할 때는 세 흐름을 **모두 테스트**해야 합니다:

| 흐름 | 트리거 | 특이사항 |
|---|---|---|
| **create** | 빈 날짜 클릭 / 새 태스크 버튼 | `task_id` 없음 |
| **move** | 태스크를 다른 날짜로 이동 | 기존 `task_id` 유지 |
| **copy** | 태스크 복사 | 새 `task_id` 생성 |

`dialog_router.py`가 세 흐름을 조립하므로, **한 흐름만 수정하면 나머지가 깨집니다** (7454dc0).

## calendar_id 필수 전파

```python
# task_data에 반드시 포함 — 누락 시 DB에 NULL로 저장됨 (76988f5)
task_data = {
    "title": title,
    "date": date_str,
    "calendar_id": self._selected_calendar_id,   # ← 절대 누락 금지
    ...
}
```

## 캘린더 드롭다운

태스크 생성 시 캘린더 선택 드롭다운이 있습니다:
- 기본값: `calendar_repo`의 `is_default=1` 캘린더
- GCal, 로컬, 공유, ICS 구독 캘린더 모두 표시
- `calendar_id` 형식: `"gcal::primary"`, `"local::메모"` 등

## 다이얼로그 라우팅

새 다이얼로그 진입점은 `dialog_router.py`의 `_DIALOG_ROUTE_MAP`에 등록합니다:

```python
_DIALOG_ROUTE_MAP = {
    "task_dialog": "open_task_dialog",
    "modify_task_dialog": "open_modify_task_dialog",
    "directive_dialog": "open_directive_dialog",
    # 새 다이얼로그 추가 시 여기에 등록
}
```

## 수정 다이얼로그

- `modify_task_dialog_unified.py` — `ModifyTaskDialog`
- create와 달리 기존 `task_id`를 받아 DB에서 데이터를 로드합니다
- `recurring_event_dialog.py` — 반복 이벤트 수정 범위 선택 (이 항목만/이후 전체/전체)
