# 패널 선택 시스템 규칙

## 개요

좌/우/하단 패널에서 태스크와 디렉티브를 클릭으로 선택하고,
키보드(ESC, Del)로 선택 해제 및 삭제할 수 있는 시스템입니다.

## 관련 파일

| 파일 | 역할 |
|---|---|
| `presentation/panels/side_panel_renderer.py` | 패널 렌더링 + `_PanelItemFilter` |
| `presentation/main_window/app_initializer.py` | 상태 변수 초기화 |
| `presentation/main_window/window_ui_actions.py` | `keyPressEvent` 처리 |
| `presentation/main_window/action_handlers_tasks.py` | `TaskActionsMixin` — 삭제 액션 |

## 앱 상태 변수

```python
# app_initializer.py에서 초기화됨
app.selected_task_ids = set()          # 센터 뷰 + 패널 공유
app.selected_directive_ids = set()    # 디렉티브 다중 선택
app._panel_task_frames = {}            # tid → (QFrame, bg_color)
app._panel_directive_frames = {}       # did → (QFrame, bg_color)
app._last_clicked_task_id = None
```

## _PanelItemFilter 동작

`side_panel_renderer.py`의 `_PanelItemFilter(QObject)`:

```
단일 클릭    → _handle_panel_item_click(app, id, is_directive, ctrl)
             → 선택 집합 업데이트 + 비주얼 갱신
더블 클릭    → 편집 다이얼로그 오픈
```

Ctrl+클릭으로 다중 선택 가능.

## 키보드 처리 (keyPressEvent)

```python
# window_ui_actions.py
ESC → clear_panel_selections(app)     # 선택 해제
Del → 디렉티브 삭제 우선
      → 선택된 디렉티브 없으면 태스크 삭제
```

## 주요 함수

```python
# side_panel_renderer.py
_handle_panel_item_click(app, item_id, is_directive, ctrl_held)
_refresh_panel_selection_visuals(app)   # 프레임 스타일 일괄 갱신

# action_handlers_tasks.py에서 가져옴
clear_panel_selections(app)             # ESC 핸들러, 변경 여부 반환

# TaskActionsMixin
delete_selected_directives()            # Del 키 / 컨텍스트 메뉴
```

## 비주얼 갱신 패턴

```python
def _refresh_panel_selection_visuals(app):
    for tid, (frame, bg_color) in app._panel_task_frames.items():
        try:
            if tid in app.selected_task_ids:
                frame.setStyleSheet("선택 스타일")
            else:
                frame.setStyleSheet(f"background-color: {bg_color};")
        except RuntimeError:
            pass  # 삭제된 위젯 — 무시
```

삭제된 위젯에 접근 시 `RuntimeError`가 발생하므로 `try/except`로 보호합니다.

## 태스크 선택 (센터 뷰 공유)

`app.selected_task_ids`는 센터 뷰의 `DraggableTaskButton`과 패널 프레임이 함께 사용합니다:

```python
_update_selection_visuals()         # DraggableTaskButton + 패널 프레임 동시 업데이트
update_task_selection_status()      # 태스크 + 디렉티브 합산 카운트 표시
handle_task_deleted(tid)            # 삭제 처리 + 다중 선택 해제 + 확인 다이얼로그
```
