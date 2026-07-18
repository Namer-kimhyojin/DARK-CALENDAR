# 아키텍처 규칙

## 레이어 구조

```
domain/          ← 순수 Python, 외부 의존성 없음
application/     ← 유스케이스, domain만 참조
infrastructure/  ← DB·외부 API, application/domain 참조
presentation/    ← PyQt6 UI, 모든 레이어 참조 가능
shared/          ← 공통 유틸, 어느 레이어도 참조 가능
```

**의존성 방향**: `presentation → application → domain`
`infrastructure`는 `domain`/`application` 인터페이스를 구현하는 형태.

## OverlayApp Mixin 조립

```python
# app_window.py
class OverlayApp(MainWindowUiActionsMixin, ActionHandlersMixin, WindowEventsMixin, QMainWindow)

# action_handlers.py
class ActionHandlersMixin(
    WindowShellActionsMixin,
    CalendarViewActionsMixin,
    RoutineActionsMixin,
    AwayLockMixin,
    ThemeActionsMixin,
    RefreshSchedulerMixin,
    GCalActionsMixin,
    DialogActionsMixin,   # ← dialog_router.py
    TaskActionsMixin,     # ← 반드시 DialogActionsMixin 뒤
)
```

### 새 Mixin 추가 규칙
1. 기능 단위로 별도 `*_actions.py` 또는 `*_mixin.py` 파일 작성
2. `action_handlers.py`의 `ActionHandlersMixin` 상속 목록에 추가
3. MRO 충돌 여부 확인 — 특히 `DialogActionsMixin`은 `TaskActionsMixin` 앞에 위치해야 함

## 앱 상태 변수 초기화

모든 `app.*` 상태 변수는 `app_initializer.py`의 `initialize_overlay_app()` 안에서 초기화해야 합니다.

```python
# 올바른 패턴
def initialize_overlay_app(app):
    app.my_new_state = None          # ← 반드시 여기에 선언
    app.my_new_flag = False
```

**누락 시**: 앱 재시작 시 `AttributeError`로 크래시 발생.

## 다이얼로그 라우팅

새 다이얼로그를 추가할 때는 `dialog_router.py`의 `_DIALOG_ROUTE_MAP`에 등록합니다:

```python
_DIALOG_ROUTE_MAP = {
    "my_new_dialog": "open_my_new_dialog",
    ...
}
```

`open_*` 메서드는 `DialogActionsMixin`에 구현합니다.

## 백그라운드 작업

DB 작업이나 네트워크 요청은 UI 블로킹을 방지하기 위해 `shared/background_worker.py`의 워커 클래스를 사용합니다:

- `SyncWorker` — GCal 동기화
- `AuthWorker` — Google 인증
- `DbTaskWorker` — DB 무거운 쿼리

워커 인스턴스는 `app._bg_workers`에 추가하고, 완료 후 제거합니다.

## 설정 저장

앱 설정은 `QSettings("kimhyojin", "Dark Calendar")`를 통해 저장합니다.

오버레이 위젯 인스턴스별 설정은 prefix `"oi_<inst_id>_"` 를 사용합니다:
```
oi_clock_0_font_size
oi_clock_0_tz_offset_mins
```

`_SettingsProxy`를 통해 인스턴스별 설정에 접근합니다.
