# 다이얼로그와 아이콘 구현 규칙

현재 UI 구현의 상세 지침입니다. 공통 작업 원칙은 [AGENTS.md](../AGENTS.md), 테마 계약은 [theme_token_completion_process.md](theme_token_completion_process.md)를 참조합니다.

## UI/UX 아이콘 시스템 (qtawesome)

### 현황

- `requirements.txt`에 `qtawesome>=1.4.2`가 명시되어 있습니다.
- 진입점은 `calendar_app/shared/icon_map.py`입니다.
- `ICON` 상수와 `icon(key, color=None)` 헬퍼를 사용합니다.
- `qtawesome` import 실패 시 `icon()`은 빈 `QIcon()`으로 graceful fallback합니다.

### 아이콘 색상 규칙

- 아이콘 색상에는 `text_primary`처럼 `#RRGGBB` hex 문자열을 사용합니다.
- `text_secondary`는 `rgba(...)` 형식일 수 있어 qtawesome 색상 인자로 부적합합니다.
- `derive_text_palette()` 반환값을 쓸 때 `text_primary`는 아이콘 색상에 사용 가능하고, `text_secondary`는 직접 넘기지 않습니다.

```python
icon(ICON.LOCK, color=text_primary_hex)   # 권장
```

### 메뉴 라벨 이모지 중복 방지

- 로케일 문자열에 이모지가 포함될 수 있으므로 `setIcon()`과 함께 쓸 때는 텍스트를 정리합니다.
- `strip_leading_emoji()` 또는 `_se` alias를 사용합니다.

```python
from calendar_app.shared.icon_map import ICON, icon as _ic, strip_leading_emoji as _se

act = menu.addAction(_se(t("menu.some_key", "설정")), handler)
act.setIcon(_ic(ICON.SETTINGS))
```

- `top_menus/common.py`의 `format_top_menu_button_text()`는 상단 QToolButton 텍스트에 자동 적용됩니다.
- `infra_wiring.py`의 `_create_action()`도 글로벌 메뉴 액션에 자동 적용합니다.

---

## 모달 다이얼로그 구현 지침

새 다이얼로그 작성 시 아래 패턴을 기본으로 사용합니다.

```python
from PyQt6.QtWidgets import QDialog, QFrame, QVBoxLayout

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
)
from calendar_app.shared.icon_map import strip_leading_emoji as _se


class MyDialog(QDialog):
    def __init__(self, parent=None, theme_color=None):
        super().__init__(parent)
        apply_dialog_title(self, _se(t("dialog.my_title", "제목")))
        apply_common_dialog_style(self, minimum_width=480, theme_color=theme_color)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(8)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        footer_layout, self.ok_btn, self.cancel_btn = build_dialog_footer(
            t("btn.ok", "확인"),
            t("btn.cancel", "취소"),
        )
        root.addLayout(footer_layout)
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
```

핵심 규칙:

- 기반 클래스는 `QDialog` 또는 태스크 전용 `BaseTaskDialog(QDialog)` 사용
- 제목은 `apply_dialog_title()`로 설정
- 공통 스타일은 `apply_common_dialog_style()` 호출
- footer는 가능한 `build_dialog_footer()` 사용
- 모달 실행은 `dialog.exec()` 사용
- 직접 `setStyleSheet()`로 공통 스타일을 덮어쓰지 않기
- 모든 라벨/버튼 텍스트는 `t()` 사용

버튼 objectName:

- 기본/저장: `primary_btn`
- 취소/보조: `ghost_btn`
- 위험 작업: 새 코드에서는 `danger_btn` 권장
- 기존 코드에는 `DangerBtn` 레거시 사용처가 남아 있으므로, 수정 범위 밖이면 일부러 바꾸지 않습니다.

권장 최소 폭:

- 단순 확인/알림: `minimum_width=360`
- 폼 입력: `minimum_width=480`
- 복잡한 설정: `minimum_width=600`
- 전체 설정/다중 탭: `minimum_width=720` 이상

---


## 추가 코드 품질 규칙

- Python 파일은 BOM 없이 UTF-8로 저장합니다.
- 변수명 l, O, I는 사용하지 않습니다(ruff E741).
- GCal 핵심 필터 변경은 [gcal_sync.md](gcal_sync.md)를 먼저 확인합니다.
