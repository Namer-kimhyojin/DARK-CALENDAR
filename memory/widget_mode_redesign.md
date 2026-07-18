# -*- coding: utf-8 -*-
# 위젯모드 개편 계획 (이미지1 스타일)

## 1. UI/UX 개선 방향

### 1.1 리스트 중심 구조로 변경
- **캘린더 숨김/최소화**: 달력은 선택적으로 표시 (아이콘/토글로 숨길 수 있게)
  - 현재: 고정 높이(266~356px) → 변경: 토글로 숨기거나 콤팩트 헤더만 표시
  - 이점: 작은 창 크기에서 실제 일정 내용 더 많이 보임

### 1.2 섹션 기반 그룹화 (이미지1 스타일)
- TODAY / TOMORROW / DEC 27 (SAT) / DEC 29 (MON) ... 로 자동 구분
- 현재 구현: `_WidgetEntry` 객체에 `is_section=True` 플래그 있음 (이미 준비됨!)
  - 개선점: 자동 섹션 생성 로직 강화 필요

### 1.3 작업 카드 선택 가능성 개선
- Ctrl+Click 다중 선택 지원 (이미 구현됨)
- 더블 클릭으로 편집 (이미 구현됨)
- 개선: 시각적 하이라이트 더 명확하게 표현

---

## 2. 구현 체크리스트

### Phase 1: 구조 개선
- [ ] `_PanelWidget` 레이아웃 재정렬
  - 캘린더를 Optional/Compact 모드로 변경
  - 토글 버튼 추가 (헤더 바에)

- [ ] `_EntryListWidget` 섹션 자동 생성 강화
  - `_build_date_section_title()` 함수 활용
  - 오늘/내일/요일 기반 자동 섹션 분류

- [ ] 작업 카드 스타일 개선
  - 선택 상태 배경색 더 선명하게 (현재: subtle)
  - 호버 상태 추가 (마우스 over 시 약간 올라옴 등)

### Phase 2: 성능 & 버그 수정
- [ ] 패널 리사이징 시 캘린더 높이 갱신 버그 수정
  - 현재: `_apply_calendar_geometry(scale)` 호출 안 될 때 있음

- [ ] 섹션 제목 텍스트 길이 초과 시 줄바꿈 처리
  - 현재: 텍스트 cutoff 가능성

- [ ] 다중 선택 상태 저장/복원
  - 패널 창 다시 열 때 선택 상태 유지하는지 확인

### Phase 3: 사용성 향상
- [ ] 빠른 추가(Quick Add) UI 개선
  - 섹션별로 데이트 자동 설정

- [ ] 네비게이션 개선
  - 위/아래 화살표로 섹션 네비게이션
  - Page Up/Down으로 이전/다음 날짜 섹션 이동

---

## 3. 주요 버그 & 수정사항

### Bug 1: 캘린더 높이 리사이징 미반영
**현상**: 패널 창을 늘려도 캘린더 높이가 반영 안 됨
**원인**: `_apply_calendar_geometry()` 호출 시점 불명확
**수정**:
```python
# panel_widget_views.py - _PanelWidget
def resizeEvent(self, event):
    super().resizeEvent(event)
    # 현재: 없음 → 추가 필요
    scale = self.calculate_current_scale()
    self._apply_calendar_geometry(scale)
```

### Bug 2: 섹션 타이틀 텍스트 오버플로우
**현상**: "4월 6일 일  오늘" 텍스트가 창 폭이 좁으면 잘림
**원인**: QLabel에 `setWordWrap(False)` + 고정 너비 없음
**수정**:
```python
# panel_widget_views.py - _EntryListWidget._get_from_pool
section_label = QLabel(...)
section_label.setWordWrap(True)
section_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
```

### Bug 3: 빠른 추가 입력 후 포커스 손실
**현상**: 엔터 입력 후 패널이 포커스를 잃어서 다시 클릭해야 함
**원인**: `_QuickAddInput` 엔터 이벤트 처리 후 `setFocus()` 누락
**수정**:
```python
# panel_widget_views.py - _QuickAddInput
def _on_return_pressed(self):
    # 현재: 입력 처리만
    # 수정: self.setFocus() 추가
```

### Bug 4: 다중 선택 상태 패널 재열 시 미복원
**현상**: 여러 작업 선택 후 패널 닫고 다시 열면 선택 해제됨
**원인**: `selected_task_ids` 상태가 패널 위젯 (QSettings)에 저장 안 됨
**수정**:
```python
# panel_widget_mode.py - PanelWidgetModeController
def close_panel(self):
    # QSettings에 선택 상태 저장
    selected = self._app.selected_task_ids
    self._settings.setValue("panel_last_selected_ids", list(selected))

def open_panel(self):
    # 저장된 상태 복원
    saved = self._settings.value("panel_last_selected_ids", [])
    self._app.selected_task_ids = set(saved)
```

### Bug 5: 아이콘 색상 오류 (text_secondary 사용)
**현상**: 작업 카드의 우선순위/상태 아이콘이 검은색으로 렌더링됨
**원인**: CLAUDE.md에 명시된 대로 `text_secondary` (rgba) 사용하면 안 됨
**파일**: `panel_widget_theme.py` 의 `_widget_mode_entry_style_bundle()`
**현재**:
```python
"icon_color": text_secondary,  # ← 틀림! rgba 형식
```
**수정**:
```python
"icon_color": text_primary,  # ← 맞음! hex 형식 (#RRGGBB)
```

---

## 4. 파일별 변경 사항

| 파일 | 수정 내용 | 우선순위 |
|------|---------|---------|
| `panel_widget_views.py` | `_PanelWidget.resizeEvent()` 추가, 텍스트 오버플로우 수정 | ⭐⭐⭐ |
| `panel_widget_theme.py` | 아이콘 색상 `text_primary`로 수정 | ⭐⭐⭐ |
| `panel_widget_mode.py` | 캘린더 토글 로직 추가, 선택 상태 저장/복원 | ⭐⭐ |
| `panel_widget_common.py` | 섹션 자동 생성 로직 강화 | ⭐⭐ |
| 로케일 파일 | "DEMO" 헤더 텍스트 추가 (구성상 선택사항) | ⭐ |

---

## 5. 실제 코드 변경 예시

### 예1: 캘린더 토글 기능
```python
# panel_widget_shell.py에서 헤더 버튼 추가
class _FloatingWidgetBase:
    def __init__(self, app, title, handle_char):
        # 기존 코드...
        # 토글 버튼 추가
        self.toggle_calendar_btn = QToolButton(self.header_bar)
        self.toggle_calendar_btn.setText("📅")  # 또는 ICON.CALENDAR
        self.toggle_calendar_btn.clicked.connect(self.toggle_calendar)
        self.header_layout.insertWidget(2, self.toggle_calendar_btn)
```

### 예2: 선택 상태 저장/복원
```python
# panel_widget_mode.py
def show_panel(self):
    self._panel.show()
    # 저장된 선택 복원
    saved_ids = self._settings.value("panel_selected_ids", set())
    self._app.selected_task_ids = set(saved_ids)

def hide_panel(self):
    # 선택 상태 저장
    self._settings.setValue("panel_selected_ids", list(self._app.selected_task_ids))
    self._panel.hide()
```

---

## 6. 테스트 케이스

- [ ] 캘린더 토글 + 패널 리사이징 확인
- [ ] 섹션 자동 그룹화 (TODAY/TOMORROW/DATE)
- [ ] Ctrl+Click 다중 선택 시 패널 닫고 다시 열 때 상태 복원
- [ ] 작업 카드 아이콘 색상 정상 표시
- [ ] 작은 창(300px 폭)에서 텍스트 오버플로우 테스트
- [ ] 빠른 추가 후 포커스 유지 확인

---

## 7. 마이그레이션 전략

1. **단계 1** (이번): 버그 수정 (아이콘 색상, 캘린더 리사이징)
2. **단계 2** (다음): UI 개선 (섹션 자동화, 토글 추가)
3. **단계 3** (나중): 선택 상태 영속화 (세션별 저장)

이렇게 하면 기존 기능 안정성 유지하면서 점진적으로 개선 가능.
